"""v3.25.12：第三方登录 × 两步验证的交叉路径。

**起因（线上实测，2026-10-05 23:34）**：账号密码登录能跳到二步验证，用已绑定的
GitHub 账号登录却「报 401」。访问日志显示 `/?oauth=ok` 之后 `/api/site`、
`/api/posts`、`/api/stats/summary` 等 17 个请求全部 401。

根因是两条登录路径**契约不一致**：
- 密码登录：`/api/auth/login` 只挂起（`twofa_pending_*`），返回 200 +
  `twofa_required`，前端据此弹动态码框 —— 第二因素通过前会话里没有 `user_id`。
- OAuth 登录：回调直接写下 `session["user_id"]` 并置 `twofa_ok=False`，会话因此
  落在「已登录但没过第二因素」。SSR 页面会被 `enforce_twofa` 赶去 `/twofa`，
  而 SPA 的每个 `/api/*` 都是 401 —— 前端不认这个信号，于是整页接口全红。

本文件钉住「OAuth 与密码登录同一契约」：需要第二因素时只挂起，不建立登录态。
"""
import contextlib
import secrets
import time

import pytest

from models import db, User, Setting, UserTwoFactor, OAuthAccount, ROLE_USER

PASSWORD = "Passw0rd!23"
PROVIDER = "github"
SUB = "gh-sub-"


@pytest.fixture(autouse=True)
def _cleanup(app):
    """两件事都得清：限流计数（跨用例累积）+ `twofa_enabled` 开关。

    后者更关键：pytest 库是全 session 共享的，留一行 `true` 会让
    `test_oauth.py` 里「回调直接登录」的用例假红，而那种红会被误判成
    「我把 OAuth 改坏了」。
    """
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete()
        db.session.commit()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete()
        db.session.commit()


def _enable_2fa(app):
    with app.app_context():
        db.session.add(Setting(key="twofa_enabled", value="true"))
        db.session.commit()


def _configure(app, provider=PROVIDER):
    app.config["OAUTH_GITHUB_CLIENT_ID"] = "cid-test"
    app.config["OAUTH_GITHUB_CLIENT_SECRET"] = "sec-test"


def _mkuser_with_2fa(app, secret):
    """建一个**已确认生效**两步验证的用户（enabled=True，与只 enroll 不同）。"""
    uname = "o2fa_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com", role=ROLE_USER)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.flush()
        from backup_settings import encrypt_secret
        db.session.add(UserTwoFactor(user_id=u.id, secret_enc=encrypt_secret(secret),
                                     enabled=True, last_counter=0))
        db.session.commit()
        return u.id, uname


def _bind(app, uid, sub=None):
    """sub 默认随机：pytest 库全 session 共享，`(provider, sub)` 有唯一约束，
    写死同一个 sub 会让第二个用例建账号时撞 UNIQUE。"""
    sub = sub or SUB + secrets.token_hex(3)
    with app.app_context():
        db.session.add(OAuthAccount(provider=PROVIDER, sub=sub, user_id=uid))
        db.session.commit()
    return sub


def _callback(client, sub, monkeypatch, state="st1"):
    monkeypatch.setattr("oauth.exchange_code",
                        lambda *a, **k: {"sub": sub, "email": "gh@example.com",
                                         "name": "gh", "email_verified": True})
    with client.session_transaction() as sess:
        sess["oauth_provider"] = PROVIDER
        sess["oauth_state"] = state
        sess["oauth_state_at"] = int(time.time())
    return client.get(f"/api/auth/oauth/{PROVIDER}/callback?code=C&state={state}")


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


@pytest.fixture
def fake_clock(monkeypatch):
    """固定 TOTP 时间窗：否则「生成码」与「校验码」撞进同一窗会被防重放正确拒绝。"""
    st = {"c": 4242}
    monkeypatch.setattr("twofa.counter_at", lambda ts=None: st["c"])
    return st


# ---------- 核心回归：OAuth 登录不得带着「未过二步」的登录态落地 ----------

def test_oauth_login_with_2fa_pends_instead_of_logging_in(app, client, monkeypatch):
    """开了 2FA 的账号走第三方登录：只挂起，-session 里不出现 user_id。"""
    _configure(app)
    _enable_2fa(app)
    import twofa
    secret = twofa.generate_secret()
    uid, _ = _mkuser_with_2fa(app, secret)
    sub = _bind(app, uid)

    r = _callback(client, sub, monkeypatch)
    assert r.status_code == 302
    loc = r.headers.get("Location") or ""
    # 落点必须把用户带回「输动态码」那一步。此前是 ?oauth=ok（直接回首页 →
    # 全页 401），所以这里同时断言**不再是** oauth=ok。
    # ⚠️ 落点是 `/login?twofa=1` 而**不是** `/twofa`：生产 nginx 把 `/twofa`
    # 当 SPA 静态页、而 SPA 路由表里没有它 → 跳过去是死循环（见 api/auth.py 注释）。
    assert "twofa=1" in loc, "应回到登录页的二步验证步骤，实际落点 %s" % loc
    assert "/login" in loc
    assert "/twofa" not in loc
    assert "?oauth=ok" not in loc

    # 挂起态要能被前端查到：登录页就是靠它决定「弹码框」还是「请重新登录」
    st = client.get("/api/auth/2fa/status").get_json() or {}
    assert st.get("pending") is True, "挂起态必须能被前端查到，否则登录页会弹一个必然超时的框"

    with client.session_transaction() as sess:
        assert sess.get("user_id") is None, "第二因素通过前不得建立登录态"
        assert sess.get("twofa_pending_uid") == uid
        assert sess.get("twofa_pending_at")


def test_no_api_401_after_oauth_2fa_is_verified(app, client, monkeypatch, fake_clock):
    """完整走一遍：OAuth 挂起 → 验码 → 之后访问 /api/* 不得再 401。

    这条用例直接对应线上现象（17 个 /api/* 全 401），断言里**不用**
    `/api/auth/me` —— 它在闸门白名单里，拿它断言会假绿。
    """
    _configure(app)
    _enable_2fa(app)
    import twofa
    secret = twofa.generate_secret()
    uid, _ = _mkuser_with_2fa(app, secret)
    sub = _bind(app, uid)

    _callback(client, sub, monkeypatch)
    # 挂起态下访问 API：无登录态 → 走各自的匿名行为，绝不是 401 twofa_required
    r = client.get("/api/posts?limit=1")
    assert (r.get_json() or {}).get("twofa_required") is not True, \
        "挂起态不该产生 twofa_required —— 那就说明登录态被提前写下了"

    code = twofa.totp_at(secret)
    v = client.post("/api/auth/2fa/verify", json={"code": code},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert v.status_code == 200, "正码必须放行，实际 %s %s" % (v.status_code, v.get_json())

    with client.session_transaction() as sess:
        assert sess.get("user_id") == uid
        assert sess.get("twofa_ok") is True

    after = client.get("/api/posts?limit=1")
    assert after.status_code != 401, "验码通过后不得再 401（线上正是卡在这里）"

    st = client.get("/api/auth/2fa/status").get_json() or {}
    assert st.get("pending") is False, "验码通过后挂起态必须清掉"


def test_oauth_login_without_2fa_still_lands_on_home(app, client, monkeypatch):
    """反向：没开 2FA（或该账号未绑定二步）时行为不变 —— 直接登录回首页。"""
    _configure(app)
    import twofa
    secret = twofa.generate_secret()
    uid, _ = _mkuser_with_2fa(app, secret)   # 账号绑了二步，但全局开关没开
    sub = _bind(app, uid)

    r = _callback(client, sub, monkeypatch)
    assert r.status_code == 302
    assert (r.headers.get("Location") or "").endswith("?oauth=ok")
    with client.session_transaction() as sess:
        assert sess.get("user_id") == uid


def test_oauth_user_without_2fa_enrollment_logs_in_directly(app, client, monkeypatch):
    """全局开关开着、但该账号**没绑**二步 → 直接登录（2FA 是自愿的）。"""
    _configure(app)
    _enable_2fa(app)
    uname = "plain_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com", role=ROLE_USER)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    sub = _bind(app, uid, SUB + "2")

    r = _callback(client, sub, monkeypatch)
    assert (r.headers.get("Location") or "").endswith("?oauth=ok")
    with client.session_transaction() as sess:
        assert sess.get("user_id") == uid


def test_bind_flow_is_unaffected_by_the_pending_change(app, client, monkeypatch):
    """绑定流程（已登录去绑新身份）不受影响：保留登录态、回绑定页。"""
    _configure(app)
    _enable_2fa(app)
    import twofa
    secret = twofa.generate_secret()
    uid, _ = _mkuser_with_2fa(app, secret)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        # 必须带 twofa_ok：没过第二因素的会话连回调本身都会被闸门 401（/api/* 一律挡），
        # 那是 v3.21.2 的既定设计。生产里走到绑定页的人必然已过二步。
        sess["twofa_ok"] = True
        sess["oauth_bind_flow"] = PROVIDER

    r = _callback(client, SUB + "3", monkeypatch, state="st9")
    assert r.status_code == 302
    assert "/admin/oauth" in (r.headers.get("Location") or ""), "绑定结果要回到绑定页"
    with client.session_transaction() as sess:
        assert sess.get("user_id") == uid, "绑定不得把人踢下线"
    with app.app_context():
        assert OAuthAccount.query.filter_by(provider=PROVIDER, sub=SUB + "3").first() is not None


# ---------- 审计：第二因素通过才算登录成功 ----------

def test_successful_2fa_login_is_written_to_login_audit(app, client, monkeypatch, fake_clock):
    """v3.21.2 要求「密码对但未过第二因素不得记成功」，但**通过之后必须记**。

    此前 `twofa_verify` 不写审计，于是开了 2FA 的账号无论密码登录还是第三方
    登录都**一条成功记录都没有** —— 恰恰是最该看的一类。
    """
    from models import AuditLog
    _configure(app)
    _enable_2fa(app)
    import twofa
    secret = twofa.generate_secret()
    uid, uname = _mkuser_with_2fa(app, secret)
    sub = _bind(app, uid, SUB + "4")

    with app.app_context():
        db.session.query(AuditLog).filter(AuditLog.username == uname).delete()
        db.session.commit()

    _callback(client, sub, monkeypatch)
    with app.app_context():
        assert AuditLog.query.filter(AuditLog.username == uname,
                                     AuditLog.action == "login").count() == 0, \
            "挂起态不算登录成功"

    code = twofa.totp_at(secret)
    client.post("/api/auth/2fa/verify", json={"code": code},
                headers={"X-CSRF-Token": _csrf(client)})
    with app.app_context():
        rows = AuditLog.query.filter(AuditLog.username == uname,
                                     AuditLog.action == "login",
                                     AuditLog.success.is_(True)).all()
    assert rows, "第二因素通过后必须落一条成功登录审计"
