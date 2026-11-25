# -*- coding: utf-8 -*-
"""v5.14.0 SSE 实时推送守卫。

守的不是「代码长什么样」，而是四条**线上会出事**的不变量：

1. **名额必须归还**：断线 / 异常 / 关闭都要 `_release()`。漏一条 → 上限被永久吃掉，
   表现为「用一会儿就永远降级成轮询」，且重启前不自愈。
2. **超限必须快速失败**：503 + `fallback: polling`，**不能阻塞等待**线程。
3. **事件不能串人**：A 的通知绝不能出现在 B 的流里（游标查询必须带 user_id）。
4. **未登录只能收到 online**：公开连接不查任何用户表。

另有一条部署契约：响应头必须带 `X-Accel-Buffering: no`，否则 Nginx 会攒缓冲区，
前端看到的是「隔几秒一次性吐一堆」，实时性名存实亡。
"""

import itertools
import secrets

import pytest

import realtime
from models import ROLE_ADMIN, ROLE_USER, Notification, User, db


# ---------- 工具 ----------


def _mk_user(app, role=ROLE_USER):
    with app.app_context():
        u = User(username="rt-" + secrets.token_hex(4),
                 email="rt-%s@test.local" % secrets.token_hex(4))
        u.set_password("test-pass")
        u.role = role
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        return u.id


def _mk_notification(app, user_id, content="有人回复了你"):
    with app.app_context():
        n = Notification(user_id=user_id, content=content, link="/post/x")
        db.session.add(n)
        db.session.commit()
        return n.id


def _fast(app):
    """把 tick 压到下限（0.5s），避免测试真的等 2 秒一轮。"""
    app.config["SSE_TICK_SECONDS"] = 0.5
    app.config["SSE_ONLINE_INTERVAL"] = 5
    return app


def _take(gen, n):
    """取前 n 帧后**立刻关闭**生成器（不 close 会把名额漏在池子里）。"""
    try:
        return list(itertools.islice(gen, n))
    finally:
        gen.close()


@pytest.fixture(autouse=True)
def _reset_active():
    """每条用例前后把连接计数清零 —— 一条用例漏归还不能污染后面所有用例。"""
    yield
    realtime._active_count = 0


# ---------- 帧格式 ----------


def test_frame_格式符合SSE规范():
    out = realtime.frame("online", {"online": 3, "approx": True})
    assert out.startswith("event: online\ndata: ")
    assert out.endswith("\n\n"), "帧必须以空行结尾，否则浏览器不会派发事件"
    assert "online" in out


def test_frame_中文被转义且不含裸换行():
    out = realtime.frame("notification", {"content": "第一行\n第二行"})
    # ensure_ascii=True：中文转 \uXXXX，换行转 \n 转义 —— 帧内绝不允许出现裸换行，
    # 否则一条通知会被 SSE 解析成两个事件。
    body = out.split("data: ", 1)[1]
    assert "\n\n" not in body.rstrip("\n")
    assert body.count("\n") == 2, "只应有结尾的两个换行"
    assert "\\u7b2c" in out


# ---------- 连接名额 ----------


def test_超限返回503且提示降级_polling(app, client):
    _fast(app)
    app.config["SSE_MAX_CONNECTIONS"] = 0
    r = client.get("/api/realtime/stream")
    assert r.status_code == 503
    assert r.get_json()["fallback"] == "polling"
    assert r.headers.get("Retry-After")
    assert r.headers.get("Cache-Control") == "no-store"


def test_关闭开关时也降级而不是报错(app, client):
    app.config["SSE_ENABLED"] = False
    r = client.get("/api/realtime/stream")
    assert r.status_code == 503
    assert r.get_json()["fallback"] == "polling"


def test_响应头是事件流且要求Nginx不缓冲(app, client):
    _fast(app)
    app.config["SSE_MAX_CONNECTIONS"] = 4
    r = client.get("/api/realtime/stream", buffered=False)
    try:
        assert r.status_code == 200
        assert r.mimetype == "text/event-stream"
        assert r.headers["X-Accel-Buffering"] == "no", (
            "少了这条 Nginx 会缓冲事件流，实时性名存实亡")
        assert "no-transform" in r.headers["Cache-Control"]
        first = next(iter(r.response))
        assert b"event: ready" in (first.encode() if isinstance(first, str) else first)
    finally:
        r.close()
    assert realtime.active_connections() == 0, "断开后名额必须归还"


def test_断流后名额归还_可再次建连(app, client):
    _fast(app)
    app.config["SSE_MAX_CONNECTIONS"] = 1
    for _ in range(3):
        r = client.get("/api/realtime/stream", buffered=False)
        try:
            assert r.status_code == 200, "前一条断流未归还名额，第 2 次就该 503 了"
            next(iter(r.response))
        finally:
            r.close()
        assert realtime.active_connections() == 0


def test_生成器异常中断也归还名额(app):
    _fast(app)
    with app.app_context():
        release = realtime.acquire(4)
        assert release is not None
        gen = realtime.event_stream(user_id=None, is_admin=False, release=release)
        assert realtime.active_connections() == 1
        next(gen)
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("模拟客户端异常"))
        assert realtime.active_connections() == 0


def test_名额回调幂等_重复调用只减一次(app):
    with app.app_context():
        release = realtime.acquire(4)
        assert realtime.active_connections() == 1
        release()
        release()
        release()
        assert realtime.active_connections() == 0, "重复 release 不能把计数减成负数或有残留"


# ---------- 事件隔离 ----------


def test_未登录只收到ready与online(app):
    _fast(app)
    with app.app_context():
        # 取 2 帧就够：ready + online 即首轮全部内容。第 3 帧要等 15 秒心跳，
        # 而本用例验证的是「不该出现的事件」—— 不为等心跳把测试拖慢 15 秒。
        frames = _take(realtime.event_stream(user_id=None, is_admin=False), 2)
    joined = "".join(frames)
    assert "event: ready" in joined
    assert "event: online" in joined
    assert "event: notification" not in joined
    assert "event: pending" not in joined


def test_通知只推给自己的用户(app):
    alice = _mk_user(app)
    bob = _mk_user(app)
    _mk_notification(app, alice, "回复了 Alice")

    with app.app_context():
        items_a, _ = realtime._fetch_notifications(alice, 0)
        items_b, _ = realtime._fetch_notifications(bob, 0)

    assert [i["content"] for i in items_a] == ["回复了 Alice"]
    assert items_b == [], "B 绝不能收到 A 的通知（越权读的另一副面孔）"


def test_游标只取连接之后的新通知(app):
    uid = _mk_user(app)
    _mk_notification(app, uid, "旧通知")

    with app.app_context():
        cursor = realtime._notification_cursor(uid)
        items, _ = realtime._fetch_notifications(uid, cursor)
        assert items == [], "连接建立时应以当前最大 id 为起点，不回放历史"

        _mk_notification(app, uid, "新通知")
        items2, new_cursor = realtime._fetch_notifications(uid, cursor)
    assert [i["content"] for i in items2] == ["新通知"]
    assert new_cursor > cursor


def test_管理员才收到pending事件(app):
    admin_id = _mk_user(app, role=ROLE_ADMIN)
    user_id = _mk_user(app, role=ROLE_USER)

    with app.app_context():
        admin_frames = "".join(_take(
            realtime.event_stream(user_id=admin_id, is_admin=True), 3))
        # 普通用户流只有 ready + online 两帧（无 pending），取 3 帧会白等 15 秒心跳
        user_frames = "".join(_take(
            realtime.event_stream(user_id=user_id, is_admin=False), 2))

    assert "event: pending" in admin_frames
    assert "event: pending" not in user_frames


def test_pending口径与后台角标一致(app):
    with app.app_context():
        counts = realtime._pending_counts()
    assert set(counts) == {"comments", "guestbook"}
    assert all(isinstance(v, int) and v >= 0 for v in counts.values())
