# -*- coding: utf-8 -*-
"""v5.3.3 审计回归：登出必须清掉第二因素状态，登录必须复位它。

漏洞场景（本次修复前）：
  已通过 2FA 的用户在共用浏览器里登出 → `session` 只 pop 了 `user_id`，
  `twofa_ok=True` 仍留在 Cookie 里 → 知道密码的人再走 `/login` 或
  `/admin/login`，全局闸门看到旧标记直接放行，完全不需要 TOTP。

判据：
  1. 三种登出入口（/logout、/admin/logout、/api/auth/logout）都必须清整份鉴权会话；
  2. `/login`、`/admin/login`、注册、首次设置密码都必须把 `twofa_ok` 显式写成 False；
  3. 复位后仅密码会话访问后台必须被赶到 /twofa；
  4. /admin/login 与前台登录同额度（10 次/60 秒）。
"""
import contextlib
import secrets

import pytest

import twofa
from backup_settings import encrypt_secret
from models import db, User, UserTwoFactor, Setting, ROLE_SUPER

PASSWORD = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _clean_state(app):
    """限流计数与 2FA 开关都跨用例共享，必须逐个清理。"""
    app.config["LOGIN_DELAY_SECONDS"] = 0     # 失败延迟会让 10 次用例睡 10 秒
    _clear_rate()
    yield
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.commit()
    _clear_rate()


def _clear_rate():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


def _set_twofa_on(app):
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.add(Setting(key="twofa_enabled", value="true"))
        db.session.commit()
    app.config["TWOFA_ENABLED"] = True


def _mk_bound_user(app):
    """建一个已确认 2FA 的超管，返回 (uid, username)。"""
    uname = "sess_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
        uid = u.id
        db.session.add(UserTwoFactor(
            user_id=uid,
            secret_enc=encrypt_secret(twofa.generate_secret()),
            enabled=True))
        db.session.commit()
    return uid, uname


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _post_form(client, path, data):
    return client.post(path, data=data,
                       headers={"X-CSRF-Token": _csrf(client)})


def test_admin_logout_clears_whole_auth_session(app, client):
    _set_twofa_on(app)
    uid, uname = _mk_bound_user(app)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["twofa_ok"] = True
        s["session_version"] = 0

    r = client.get("/admin/logout")
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert "user_id" not in s
        assert "twofa_ok" not in s, "登出后 twofa_ok 仍在 — 下一次仅凭密码即可跳过 TOTP"


def test_api_logout_clears_whole_auth_session(app, client):
    _set_twofa_on(app)
    uid, _ = _mk_bound_user(app)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["twofa_ok"] = True

    r = client.post("/api/auth/logout", headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200
    with client.session_transaction() as s:
        assert "user_id" not in s
        assert "twofa_ok" not in s, "API 登出后 twofa_ok 仍在 — 第二因素可被绕过"


def test_ssr_logout_clears_whole_auth_session(app, client):
    _set_twofa_on(app)
    uid, _ = _mk_bound_user(app)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["twofa_ok"] = True

    r = client.get("/logout")
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert "user_id" not in s
        assert "twofa_ok" not in s


def test_admin_login_resets_stale_flag_and_gate_challenges(app, client):
    """核心回归：登出→仅密码重登后台，必须落到 /twofa，而不是直接进后台。"""
    _set_twofa_on(app)
    uid, uname = _mk_bound_user(app)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["twofa_ok"] = True
    client.get("/admin/logout")

    r = _post_form(client, "/admin/login",
                   {"username": uname, "password": PASSWORD})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert s.get("user_id") == uid
        assert s.get("twofa_ok") is False, "后台登录没有复位 twofa_ok"

    r = client.get("/admin/dashboard")
    assert r.status_code == 302, "未过第二因素的会话竟拿到后台页面"
    assert "/twofa" in r.headers.get("Location", "")


def test_ssr_login_resets_stale_flag(app, client):
    _set_twofa_on(app)
    uid, uname = _mk_bound_user(app)
    with client.session_transaction() as s:
        s["twofa_ok"] = True       # 模拟上一轮会话残留

    r = _post_form(client, "/login", {"username": uname, "password": PASSWORD})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert s.get("user_id") == uid
        assert s.get("twofa_ok") is False, "前台登录没有复位 twofa_ok"

    r = client.get("/twofa")
    assert r.status_code == 200, "仅密码会话应停在二步验证挑战页"


def test_admin_logout_reachable_before_second_factor(app, client):
    """只过了密码的会话也必须能退出——否则用户被卡在 /twofa 里出不来。"""
    _set_twofa_on(app)
    _, uname = _mk_bound_user(app)
    _post_form(client, "/admin/login", {"username": uname, "password": PASSWORD})

    r = client.get("/admin/logout")
    assert r.status_code == 302
    assert "/twofa" not in r.headers.get("Location", "")


def test_admin_login_is_rate_limited(app, client):
    _set_twofa_on(app)
    for _ in range(10):
        r = _post_form(client, "/admin/login",
                       {"username": "nobody", "password": "wrong-pass"})
        assert r.status_code == 200, "前 10 次应正常返回登录页（含失败提示）"
    r = _post_form(client, "/admin/login",
                   {"username": "nobody", "password": "wrong-pass"})
    assert r.status_code == 429, "第 11 次必须被限流，否则后台可无限猜密码"
