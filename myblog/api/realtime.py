# -*- coding: utf-8 -*-
"""SSE 实时推送接口（v5.14.0）。

单端点 `GET /api/realtime/stream`，一条连接同时承载三类事件：

| 事件 | 谁能收到 | 内容 |
|---|---|---|
| `online` | 所有人（含未登录） | 近 10 分钟独立 IP 数（**近似值**，与 `/api/stats/online` 同口径） |
| `notification` | 已登录用户 | 该用户**连接之后**新产生的站内通知（被回复 / 被 @） |
| `pending` | 管理员 | 未读评论 / 未读留言数（后台导航角标同口径） |

## 为什么一个端点而不是三个

每条 SSE 连接独占一个 gthread 线程。管理员若同时订阅「通知流 + 待审流」就是两条连接、
两个线程 —— 而这两类事件都不高频、都在同一个会话里，合成一条只花一个线程。
代价是**未登录访客也会占一个线程**（只收 online），这是刻意的：在线数是公开信息，
而「登录后才有的内容」一个字节都不会进未登录连接的流。

## 权限

- 未登录：只发 `online`。会话里没有 user_id 时**不查任何用户相关表**。
- 登录：额外发自己的 `notification`（查询强制 `user_id == 自己`，不存在越权读别人通知的路径）。
- 管理员：再加 `pending`。权限在**握手期**算一次；长连接期间被降权不会即时生效，
  但流里从不含敏感正文（只有计数与自己的通知），且前端下次重连会重新判定。

## 与 CSRF / 限流的关系

纯 `GET` 且无副作用：不触发 CSRF 校验（本项目的 CSRF 只作用于写方法），
也不需要 CSRF token —— `EventSource` 无法自定义请求头，靠浏览器自动带同源会话 Cookie。
`api_bp` 上的 bot_guard 钩子照常生效（一条连接 = 一次请求，天然低配额消耗）。
"""

from flask import current_app, jsonify, session, stream_with_context

import realtime
from models import User, db

from .common import api_bp


def _cfg():
    """把 app.config 里的三个开关收成字典。0 是合法值，不能被 `or` 吃掉。"""
    c = current_app.config
    try:
        max_conn = int(c.get("SSE_MAX_CONNECTIONS", 4))
    except (TypeError, ValueError):
        max_conn = 4
    try:
        tick = float(c.get("SSE_TICK_SECONDS", 2))
    except (TypeError, ValueError):
        tick = 2.0
    return {
        "enabled": bool(c.get("SSE_ENABLED", True)),
        "max_connections": max(0, max_conn),
        "tick": max(0.5, tick),
    }


def _degraded(reason, retry_after):
    """统一的「请改用轮询」响应：503 + Retry-After。

    用 503 而非 429：语义是「这条长连接暂时拿不到线程/被关闭」，
    前端据此进入轮询降级；报错或白屏都不是这个场景该有的表现。
    """
    resp = jsonify({
        "error": reason,
        "fallback": "polling",
        "retry_after": retry_after,
    })
    resp.status_code = 503
    resp.headers["Retry-After"] = str(int(retry_after))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@api_bp.route("/realtime/stream")
def realtime_stream():
    """SSE 事件流。超连接上限时返回 503（前端降级为轮询）。"""
    cfg = _cfg()
    if not cfg["enabled"]:
        return _degraded("实时推送已关闭", retry_after=300)

    uid = session.get("user_id")
    try:
        user_id = int(uid) if uid else None
    except (TypeError, ValueError):
        user_id = None

    is_admin = False
    if user_id:
        user = db.session.get(User, user_id)
        # is_admin_role() 与后台蓝图同一判据：普通作者只发自己的通知，不发待审角标
        is_admin = bool(user and user.is_admin_role)

    release = realtime.acquire(cfg["max_connections"])
    if release is None:
        # 名额耗尽：立即回 503，**绝不等待**。等待会把 gthread 线程一起堵住，
        # 把「实时不可用」升级成「整站不可用」。
        return _degraded("实时连接数已达上限，请使用轮询模式",
                         retry_after=max(10, int(cfg["tick"] * 15)))

    gen = realtime.event_stream(user_id=user_id, is_admin=is_admin, release=release)
    resp = realtime.build_response(stream_with_context(gen))
    # 双保险：客户端在首字节前就断开时，生成器函数体从未进入，finally 不会执行 ——
    # 这条回调保证名额照样归还（release 幂等，两条路径都调也只减一次）。
    resp.call_on_close(release)
    return resp
