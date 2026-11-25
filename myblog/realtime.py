# -*- coding: utf-8 -*-
"""SSE 实时推送内核（v5.14.0）。

## 为什么是「数据库游标 + SSE」而不是「进程内发布订阅」

gunicorn 的 gthread 模型下 `workers=N` 是 **N 个独立进程**，各自的内存订阅者表互不相通 ——
A worker 里 `publish()` 推不到连在 B worker 上的浏览器。要让「谁写库谁通知」跨进程生效，
只有两条路：

1. 引入 Redis pub/sub —— 本项目 Redis 是**可选依赖**（未配置自动回退内存限流），
   为一个锦上添花的实时性把 Redis 变成硬依赖，不值得。
2. **让每条连接自己盯着库的游标** —— 事件源就是数据库行本身，`id > 游标` 即「新事件」。

本模块选 2：天然跨进程、天然幂等、断线重连不丢事件（游标在连接里，重连后以当前最大 id
为起点）。代价是最坏 `SSE_TICK_SECONDS`（默认 2 秒）的延迟，以及每连接每轮一次轻量 SELECT。

## 线程预算：为什么必须有连接上限

gthread 下**一条 SSE 连接独占一个线程**直到断开。`workers=2 × threads=16` = 32 个线程；
不设限的话，32 个开着的标签页就能把整站线程吃干净，表现为「网站打不开」—— 比没有实时
推送严重得多。故每进程设 `SSE_MAX_CONNECTIONS`（默认 4）上限，超限**立即**返回 503，
前端据此降级为轮询（有界降级，不是报错也不是白屏）。

## 事件协议

```
event: ready         data: {"tick": 2.0, "interval": 20.0}          连接建立
event: online        data: {"online": 12, "approx": true}           在线数（近似值）
event: notification  data: {"id": 33, "content": "...", "link": "...", "unread": 2}
event: pending       data: {"comments": 3, "guestbook": 1}          仅管理员
: hb                                                              心跳注释行（15s）
```
"""

import json
import threading
import time

from flask import Response, current_app

# 每进程活跃连接计数。**小写**命名是刻意的：它是可变状态，不是常量
# （曾经叫 _ACTIVE，SIM300 会把它当常量报 Yoda 条件误报）。
# 用模块级变量 + 锁而非 Flask 扩展：
# 计数天然是「进程内」语义，跨进程聚合没有意义（每个 worker 管自己的线程预算）。
_LOCK = threading.Lock()
_active_count = 0

# 心跳间隔（秒）。Nginx 默认 proxy_read_timeout 60s，15s 一行注释足够续命；
# 也顺带让客户端能在 socket 半开时及时发现断开。
_HEARTBEAT_SECONDS = 15.0


def active_connections():
    """当前进程内活跃的 SSE 连接数（诊断 / 测试用）。"""
    with _LOCK:
        return _active_count


def acquire(limit):
    """占一个连接名额。

    成功返回**幂等的 release 回调**，失败返回 None（调用方回 503，绝不阻塞等待）。

    为什么返回回调而不是让调用方自己 `release()`：名额的归还点有三个 ——
    客户端断开（生成器 finally）、响应对象被关闭（`call_on_close`）、
    以及**生成器根本没被消费就被废弃**（此时 finally 不会执行，因为函数体从未进入）。
    三处都调同一个幂等回调，才不会有任何一条路径漏掉名额。
    """
    global _active_count
    with _LOCK:
        if _active_count >= limit:
            return None
        _active_count += 1

    released = False
    lock = threading.Lock()

    def release():
        nonlocal released
        global _active_count
        with lock:
            if released:
                return
            released = True
        with _LOCK:
            if _active_count > 0:
                _active_count -= 1

    return release


def frame(event, payload, retry=None):
    """拼一个 SSE 帧。

    `json.dumps` 默认 `ensure_ascii=True`：非 ASCII 会被转义成 \\uXXXX，
    这样帧内绝不会出现裸换行（SSE 用双换行分隔事件），也避开部分代理对
    非 ASCII body 的错误处理。前端 `JSON.parse` 后的中文与原文一致。

    `retry`（毫秒）只在握手帧里给：告诉浏览器断线后隔多久重连。默认 3 秒对
    「连接名额已满」的场景太急（一屋子人同时重连又是一次冲击），放宽到 5 秒。
    """
    head = "retry: %d\n" % int(retry) if retry is not None else ""
    return "%sevent: %s\ndata: %s\n\n" % (head, event, json.dumps(payload, ensure_ascii=True))


def build_response(generator):
    """把生成器包成 SSE 响应。

    `X-Accel-Buffering: no` 是给 Nginx 的：它会让 Nginx 对本响应关闭缓冲
    （等价于 `proxy_buffering off`），因此**不需要改 Nginx 配置** —— 少了这条，
    Nginx 会攒够缓冲区才下发，前端看到的将是「隔几秒一次性收到一堆事件」。
    `no-transform` 阻止运营商/CDN 的转码压缩改写流。
    """
    resp = Response(generator, mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache, no-transform"
    resp.headers["Connection"] = "keep-alive"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


# ---------- 事件源 ----------


def _float_cfg(key, default):
    """读浮点配置，坏值回落默认。

    刻意写成显式 try 而不是 `float(cfg.get(key) or default)`：`0` 是**合法值**
    （把 tick 配到下限、或 `SSE_MAX_CONNECTIONS=0` 应急停掉全部连接都用得上），
    而 `0 or default` 会把它悄悄改成默认值 —— 「配了等于没配」是最难查的一类问题。
    """
    raw = current_app.config.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _notification_cursor(user_id):
    """连接建立时的起点：该用户当前最大通知 id。只推**此后**产生的通知。"""
    from models import db, Notification
    try:
        return db.session.query(db.func.max(Notification.id)).filter(
            Notification.user_id == user_id).scalar() or 0
    except Exception:  # noqa: BLE001 —— 表未建好时从头开始，不影响连接建立
        return 0


def _fetch_notifications(user_id, cursor):
    """取游标之后的通知（升序，最多 20 条），并算未读总数。"""
    from models import Notification
    rows = (Notification.query
            .filter(Notification.user_id == user_id, Notification.id > cursor)
            .order_by(Notification.id.asc()).limit(20).all())
    if not rows:
        return [], None
    unread = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    items = [{
        "id": n.id,
        "content": n.content,
        "link": n.link or "",
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
        "unread": unread,
    } for n in rows]
    return items, rows[-1].id


def _pending_counts():
    """后台待审数（未读评论 / 未读留言）。与后台导航角标同一口径。"""
    from models import Comment, Guestbook
    return {
        "comments": Comment.query.filter_by(is_read=False).count(),
        "guestbook": Guestbook.query.filter_by(is_read=False).count(),
    }


def _online():
    from stats import compute_online
    return compute_online()


def event_stream(user_id, is_admin, release=None):
    """SSE 事件生成器。

    `release` 是 `acquire()` 返回的幂等回调。生成器**可能从未被消费**就随响应对象
    一起被丢弃（客户端在首字节前断开），那时函数体从未进入、finally 不会执行 ——
    所以路由层还会把同一个回调挂到 `Response.call_on_close`，两条路径都调、只生效一次。

    `user_id` / `is_admin` 由**请求期**算好传进来，生成器内部不再读 session ——
    长连接期间会话可能被登出/踢下线，这里有意不复查：一条只读推送流，
    断开由前端在收到 401 的轮询请求时自行处理。要看新权限请重连。

    每轮开头 `db.session.remove()` 是必须的：长连接会把 SQLAlchemy 的会话
    （及其连接）一直攥在手里，不释放会耗尽连接池 —— 一个「只读推送」把整站
    拖垮，是最不该出现的故障模式。
    """
    from models import db

    # 配置读法走 `_float_cfg`：不用 `float(cfg or 2.0)` —— `0` 是合法值（压测时想让
    # 轮询尽可能快），而 `0 or 2.0` 会把它悄悄改成 2。真正的下限由下面的 max() 兜底。
    tick = max(0.5, min(_float_cfg("SSE_TICK_SECONDS", 2.0), 30.0))  # 下限 0.5s 防忙轮询
    online_every = max(5.0, _float_cfg("SSE_ONLINE_INTERVAL", 20.0))

    cursor = _notification_cursor(user_id) if user_id else 0
    last_online_at = 0.0
    last_online_value = None
    last_pending = None
    last_beat_at = time.monotonic()

    try:
        yield frame("ready", {"tick": tick, "interval": online_every}, retry=5000)
        while True:
            now = time.monotonic()
            try:
                db.session.remove()

                # ① 站内通知（仅登录用户）
                if user_id:
                    items, new_cursor = _fetch_notifications(user_id, cursor)
                    if new_cursor:
                        cursor = new_cursor
                    for it in items:
                        yield frame("notification", it)

                # ② 在线人数（所有人，按 SSE_ONLINE_INTERVAL 节流）
                if now - last_online_at >= online_every:
                    last_online_at = now
                    value = _online()
                    if value != last_online_value:
                        last_online_value = value
                        yield frame("online", {"online": value, "approx": True})

                # ③ 待审角标（仅管理员，每轮都查 —— 两条 count 走 is_read 索引/全表，
                #    当前表规模为百级，成本可忽略；规模上来后应并入前面的聚合查询）
                if is_admin:
                    counts = _pending_counts()
                    if counts != last_pending:
                        last_pending = counts
                        yield frame("pending", counts)
            except GeneratorExit:
                raise
            except Exception as e:  # noqa: BLE001 —— 单轮失败不该断流
                current_app.logger.warning("[sse] 轮询失败：%s", str(e)[:160])

            # 心跳：注释行不触发前端事件，只用于续命与探测半开连接
            if now - last_beat_at >= _HEARTBEAT_SECONDS:
                last_beat_at = now
                yield ": hb\n\n"

            time.sleep(tick)
    finally:
        # 客户端断开（GeneratorExit）、异常退出、正常结束都走这里 —— 名额必须归还，
        # 否则「断线不释放」会把上限永久吃掉，表现为「用一会儿就永远降级成轮询」。
        db.session.remove()
        if release is not None:
            release()
