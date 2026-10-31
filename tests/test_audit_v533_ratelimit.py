# -*- coding: utf-8 -*-
"""v5.3.3 审计回归：限流键不可伪造，博客圈强制刷新不可被匿名放大。

1. `client_key()` 必须忽略未签名的 `EO-Client-IP`（否则轮换假头即可绕过所有
   登录/2FA/评论/上传额度）；统计用的 `get_client_ip()` 保持宽松档。
2. `GET /api/feed/circle?refresh=1`：匿名 5 分钟最多 1 次，超出静默回落缓存；
   管理员不受此限。
"""
import contextlib
import secrets

import pytest

from models import db, User, ROLE_SUPER


@pytest.fixture(autouse=True)
def _clear_rate():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


def test_client_key_ignores_unsigned_eo_header(app):
    """未配 EO_AUTH_KEY：限流键必须用不可伪造的 remote_addr。"""
    from utils.net import client_key, get_client_ip
    app.config["EO_AUTH_KEY"] = ""
    with app.test_request_context(
            "/", headers={"EO-Client-IP": "1.2.3.4"},
            environ_base={"REMOTE_ADDR": "9.9.9.9"}):
        assert client_key("login").endswith(":9.9.9.9"), \
            "限流键采信了未签名头 — 轮换 EO-Client-IP 即可绕过额度"
        # 统计口径保持宽松：有头就用头
        assert get_client_ip() == "1.2.3.4"


def test_client_key_trusts_signed_eo_header(app):
    from utils.net import client_key, get_client_ip
    app.config["EO_AUTH_KEY"] = "unit-test-key"
    headers = {"EO-Client-IP": "1.2.3.4", "X-EO-Auth": "unit-test-key"}
    with app.test_request_context(
            "/", headers=headers, environ_base={"REMOTE_ADDR": "9.9.9.9"}):
        assert client_key("login").endswith(":1.2.3.4")
        assert get_client_ip() == "1.2.3.4"


def test_client_key_rejects_wrong_eo_signature(app):
    from utils.net import client_key, get_client_ip
    app.config["EO_AUTH_KEY"] = "unit-test-key"
    headers = {"EO-Client-IP": "1.2.3.4", "X-EO-Auth": "guessed"}
    with app.test_request_context(
            "/", headers=headers, environ_base={"REMOTE_ADDR": "9.9.9.9"}):
        assert client_key("login").endswith(":9.9.9.9")
        assert get_client_ip() == "9.9.9.9"


def _super_session(app, client):
    name = "rl_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=name, email=name + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password("Passw0rd!23")
        db.session.add(u)
        db.session.commit()
        uid, ver = u.id, u.session_version or 0
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["session_version"] = ver


def test_circle_force_refresh_is_throttled_for_anonymous(app, client, monkeypatch):
    import feed_agg
    calls = []
    monkeypatch.setattr(feed_agg, "get_circle_feed",
                        lambda force=False: calls.append(force) or [])
    monkeypatch.setattr(feed_agg, "get_last_diag", lambda: {})

    r1 = client.get("/api/feed/circle?refresh=1")
    r2 = client.get("/api/feed/circle?refresh=1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert calls == [True, False], "匿名第二次强制刷新未被降级为缓存读取"
    assert (r2.get_json().get("debug") or {}).get("refresh_throttled") is True


def test_circle_force_refresh_allowed_for_admin(app, client, monkeypatch):
    _super_session(app, client)
    import feed_agg
    calls = []
    monkeypatch.setattr(feed_agg, "get_circle_feed",
                        lambda force=False: calls.append(force) or [])
    monkeypatch.setattr(feed_agg, "get_last_diag", lambda: {})

    client.get("/api/feed/circle?refresh=1")
    client.get("/api/feed/circle?refresh=1")
    assert calls == [True, True], "管理员不应被匿名额度限制"
