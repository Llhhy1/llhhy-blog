# -*- coding: utf-8 -*-
"""后台长任务（v3.23.0，#48）：把「长期占住请求线程」的慢操作挪到后台。

## 为什么需要它

gunicorn 是 gthread（4 worker × 2 线程 = 8 个并发槽），而后台有三个操作会长期
占住一个槽：立即备份 300s（scp/curl 远程同步）、游戏 LLM 审计 120s、AI 摘要 90s。
一个这样的请求就吃掉 1/8 的并发，几个就能把整站拖成 502。

## 关键约束（设计由它们决定，改之前先读懂）

1. **状态必须落盘，不能只放内存**：4 个 worker 是**独立进程**，任务在 A 提交、
   轮询请求很可能打到 B —— 内存 dict 会「查无此任务」。故状态写
   `data/tasks/<id>.json`（原子写：tmp + os.replace）。
2. **不引 Celery / Redis**：Redis 缓存层已在 v3.10.7 revert，单人维护的项目
   不值得再加一个要运维的组件。用 daemon 线程 + 文件状态即可。
3. **同名任务不并发**：备份连跑两次会撞同一批文件。用**锁文件**做跨进程互斥
   （O_EXCL 原子创建），并带过期清理防止进程被杀后死锁。
4. **线程内必须有 app context**：仿 `notify.py` 与 `stats._resolve_region_async`。
   app 对象在 submit 时从 current_app 捕获（而不是线程里再 import app），
   这样测试里的 `create_app()` 实例也能被正确使用。
5. **任务只做「尽力而为」**：任何异常写进状态文件，绝不抛回请求线程。

## 用法

    from tasks import submit, status
    tid, err = submit("backup", backup_mod.create_backup)   # err 非空=被防重入挡下
    st = status(tid)   # {"state": "running|done|error", ...}
"""
import contextlib
import json
import os
import threading
import time
import uuid

# 同名任务锁的过期时间：进程被强杀后锁文件会残留，超时即视为可抢占。
LOCK_STALE = 3600.0
# 状态文件保留时长（prune 用）
TASK_TTL = 86400.0


def _task_dir():
    from config import DATA_DIR
    d = os.path.join(DATA_DIR, "tasks")
    os.makedirs(d, exist_ok=True)
    return d


def _write_json(path, obj):
    """原子写：先写 tmp 再 replace，避免轮询读到写了一半的 JSON。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001  状态文件读失败（写一半/损坏/不存在）一律当作「无状态」：轮询与提交方都不能因它崩掉
        return None


def _lock_path(name):
    return os.path.join(_task_dir(), ".lock_" + name)


def _acquire_lock(name):
    """跨进程互斥：O_EXCL 原子创建锁文件。拿不到返回 False。"""
    lp = _lock_path(name)
    try:
        if os.path.exists(lp) and (time.time() - os.path.getmtime(lp)) > LOCK_STALE:
            with open(lp, "a", encoding="utf-8"):
                pass
            os.remove(lp)      # 过期锁：清掉重来（进程被杀后残留的兜底）
    except OSError:
        pass
    try:
        fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _release_lock(name):
    """释放同名任务锁（进程内任何一步失败都要保证最终释放，故静默）。"""
    with contextlib.suppress(OSError):
        os.remove(_lock_path(name))


def _jsonable(out):
    """结果可能含路径元组等，不能直接 JSON 序列化 → 尽力转，转不了就 str()。"""
    try:
        json.dumps(out)
        return out
    except (TypeError, ValueError):
        return str(out)[:500]


def submit(name, fn, *args, **kwargs):
    """提交一个后台任务，返回 (task_id, err)；err 非空表示被防重入挡下。"""
    d = _task_dir()
    if not _acquire_lock(name):
        return None, "「%s」正在运行中，请等它结束后再触发" % name

    tid = uuid.uuid4().hex[:12]
    now = time.time()
    _write_json(os.path.join(d, tid + ".json"), {
        "id": tid, "name": name, "state": "running",
        "message": "已开始", "result": None, "error": "",
        "started_at": now, "updated_at": now,
    })

    # app 对象在提交时捕获：线程里再 import app 会拿到模块级那个实例，
    # 与测试中的 create_app() 不是同一个。
    try:
        from flask import current_app
        app_obj = current_app._get_current_object()
    except Exception:  # noqa: BLE001  非请求上下文（CLI/定时任务）时 current_app 不可用，属预期路径，降级用模块级实例
        from app import app as app_obj   # 非请求上下文（CLI / 定时任务）兜底

    def _work():
        try:
            with app_obj.app_context():
                out = fn(*args, **kwargs)
            _update(tid, state="done", message="完成", result=_jsonable(out))
        except Exception as e:      # noqa: BLE001  任务只做尽力而为：异常必须落进状态文件，绝不外抛
            _update(tid, state="error", message="失败", error=str(e)[:500])
        finally:
            _release_lock(name)

    threading.Thread(target=_work, daemon=True, name="task-" + name).start()
    return tid, None


def _update(tid, **fields):
    path = os.path.join(_task_dir(), tid + ".json")
    st = _read_json(path) or {"id": tid}
    st.update(fields)
    st["updated_at"] = time.time()
    _write_json(path, st)
    return st


def status(tid):
    """读任务状态；不存在返回 None。"""
    if not tid or not str(tid).isalnum():
        return None          # 防路径穿越：task id 只接受字母数字
    return _read_json(os.path.join(_task_dir(), str(tid) + ".json"))


def prune(max_age=TASK_TTL):
    """清理过期状态文件（启动或定时任务调用）。返回清理数量。"""
    d = _task_dir()
    n = 0
    now = time.time()
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if fn.startswith(".lock_"):
            continue
        try:
            if now - os.path.getmtime(p) > max_age:
                os.remove(p)
                n += 1
        except OSError:
            continue
    return n
