"""双因素认证 2FA / TOTP（v3.21.0，config-gated）测试。

覆盖：
- 算法正确性：RFC 6238 官方测试向量（SHA-1，8 位码）——不依赖第三方库的自证。
- config-gated 休眠：TWOFA_ENABLED=false 时所有入口短路、登录流程不变。
- 绑定流程：enroll → confirm（错码拒绝、正码通过、发恢复码）→ 登录需二步。
- 防重放：同一时间窗的码用过即失效；恢复码一次性消费。
- 关闭：需密码 + 动态码双确认。

测试约定（与 test_api_auth.py 一致）：
- 所有 POST 必须带 X-CSRF-Token（全局 CSRF 校验在 before_request 生效）。
- 用户名随机化（同一临时库内 username 唯一，避免跨测试冲突）。
- 每个用例前清空内存限流计数，避免登录限流（10/60s）跨用例互相干扰。
"""
import base64
import contextlib
import json as _json
import secrets

import pytest
from models import db, User, UserTwoFactor, ROLE_USER
from twofa import (generate_secret, totp_at, verify, hotp, provisioning_uri,
                   generate_recovery_codes, consume_recovery_code,
                   get_secret, TOTP_PERIOD)


RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
# RFC 6238 Appendix B（SHA-1）官方测试向量：时间 T → 期望 8 位码
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]

PASSWORD = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """清空内存限流计数（登录 10/60s、2FA 10/60s 会跨用例累积）。"""
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _post(client, path, payload=None):
    return client.post(path, json=payload or {}, headers={"X-CSRF-Token": _csrf(client)})


def _mkuser(password=PASSWORD):
    """建一个用户名随机的普通用户（避免 username 唯一约束跨用例冲突）。"""
    u = User(username="u2fa_" + secrets.token_hex(4),
             email="u2fa_" + secrets.token_hex(4) + "@example.com",
             role=ROLE_USER)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username, password=PASSWORD):
    return _post(client, "/api/auth/login", {"username": username, "password": password})


@pytest.fixture
def fake_clock(monkeypatch):
    """把 TOTP 时间窗变成可控整数。

    不加控制时，confirm 与「登录二步」经常落在同一个 30 秒窗内，而防重放逻辑
    （同一窗的码用过即失效）会**正确**拒绝第二次——测试从而依赖真实时钟、随机翻车。
    这里把 counter_at 换成可变整数：fake_clock["c"] = n 即「当前在第 n 个窗口」。
    """
    state = {"c": 1000}
    monkeypatch.setattr("twofa.counter_at", lambda ts=None: state["c"])
    return state


# ---------- 算法层 ----------

def test_rfc6238_vectors():
    """用 RFC 官方向量自证 TOTP 实现正确（零依赖实现的关键防线）。"""
    for ts, expect in RFC_VECTORS:
        assert totp_at(RFC_SECRET, ts, digits=8) == expect


def test_secret_format_and_hotp():
    s = generate_secret()
    assert len(s) == 32 and "=" not in s      # 160-bit → base32 32 字符
    assert hotp(s, 1) == hotp(s, 1)           # 同 counter 稳定
    assert hotp(s, 1) != hotp(s, 2)
    assert len(hotp(s, 1)) == 6 and hotp(s, 1).isdigit()


def test_verify_accepts_current_and_skew_window():
    s = generate_secret()
    assert verify(s, totp_at(s)) is not None                       # 当前窗口
    now = 1_700_000_000
    assert verify(s, totp_at(s, now - TOTP_PERIOD), ts=now) is not None  # 上一窗口（±30s）


def test_verify_rejects_malformed():
    s = generate_secret()
    assert verify(s, "") is None
    assert verify(s, "abc123") is None
    assert verify(s, "12345") is None
    assert verify(s, "1234567") is None


def test_verify_replay_protection():
    """同一时间窗的码用过即失效（last_counter 防重放）。"""
    s = generate_secret()
    ts = 1_700_000_000
    code = totp_at(s, ts)
    hit = verify(s, code, ts=ts)
    assert hit is not None
    assert verify(s, code, ts=ts, last_counter=hit) is None


def test_provisioning_uri_format():
    s = generate_secret()
    uri = provisioning_uri(s, "alice", issuer="llhhy-blog")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" + s in uri
    assert "issuer=llhhy-blog" in uri
    assert "period=30" in uri and "digits=6" in uri


def test_recovery_codes_single_use():
    plain, hashed = generate_recovery_codes()
    stored = _json.dumps(hashed)
    assert len(plain) == 8
    ok1, left1 = consume_recovery_code(stored, plain[0])
    assert ok1 is True and len(_json.loads(left1)) == 7
    assert consume_recovery_code(left1, plain[0])[0] is False      # 同码不可复用
    ok3, left3 = consume_recovery_code(left1, plain[1])
    assert ok3 is True and len(_json.loads(left3)) == 6


# ---------- 接口 / 流程层 ----------

def test_endpoints_dormant_when_disabled(app, client):
    """未开全局开关：status.enabled=false，enroll/verify 404，登录流程完全不变。"""
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    st = client.get("/api/auth/2fa/status").get_json()
    assert st["enabled"] is False
    assert _post(client, "/api/auth/2fa/enroll").status_code == 404
    assert _post(client, "/api/auth/2fa/verify", {"code": "123456"}).status_code == 404
    # 登录不受影响（哪怕该用户其实绑了 2FA，也不触发二步）
    r = _login(client, uname)
    assert r.status_code == 200


def test_enroll_requires_login(app, client):
    app.config["TWOFA_ENABLED"] = True
    assert _post(client, "/api/auth/2fa/enroll").status_code == 401


def test_enroll_and_confirm_flow(app, client):
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname, uid = u.username, u.id   # 出上下文后实例即 detached，先取成标量
    assert _login(client, uname).status_code == 200

    en = _post(client, "/api/auth/2fa/enroll").get_json()
    assert "secret" in en and en["provisioning_uri"].startswith("otpauth://totp/")
    secret = en["secret"]

    # 未确认前不算启用
    st = client.get("/api/auth/2fa/status").get_json()
    assert st["enabled"] is True and st["enrolled"] is False

    assert _post(client, "/api/auth/2fa/confirm", {"code": "000000"}).status_code == 400

    ok = _post(client, "/api/auth/2fa/confirm", {"code": totp_at(secret)})
    assert ok.status_code == 200
    assert len(ok.get_json()["recovery_codes"]) == 8

    st2 = client.get("/api/auth/2fa/status").get_json()
    assert st2["enrolled"] is True and st2["recovery_codes_left"] == 8

    with app.app_context():
        row = UserTwoFactor.query.filter_by(user_id=uid).first()
        assert row.enabled is True
        assert row.secret_enc != secret        # 绝不落明文
        assert get_secret(row) == secret       # 且能解密回明文


def test_login_requires_second_step(app, client, fake_clock):
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    secret = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    fake_clock["c"] = 1000
    _post(client, "/api/auth/2fa/confirm", {"code": totp_at(secret)})   # 消费窗口 1000
    _post(client, "/api/auth/logout")

    r = _login(client, uname)
    body = r.get_json()
    assert body.get("twofa_required") is True
    assert "user" not in body                                  # 此时未建立登录态
    assert client.get("/api/auth/me").get_json()["user"] is None

    assert _post(client, "/api/auth/2fa/verify", {"code": "000000"}).status_code == 400

    fake_clock["c"] = 1001                                     # 换到下一个窗口
    ok = _post(client, "/api/auth/2fa/verify", {"code": totp_at(secret)})
    assert ok.status_code == 200
    assert ok.get_json()["user"]["username"] == uname
    assert client.get("/api/auth/me").get_json()["user"]["username"] == uname


def test_second_step_dynamic_code_not_replayable(app, client, fake_clock):
    """登录二步用过的码立刻失效（同一 30 秒窗内不能重放）。"""
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    secret = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    fake_clock["c"] = 1000
    _post(client, "/api/auth/2fa/confirm", {"code": totp_at(secret)})
    _post(client, "/api/auth/logout")

    fake_clock["c"] = 1001
    _login(client, uname)
    code = totp_at(secret)
    assert _post(client, "/api/auth/2fa/verify", {"code": code}).status_code == 200
    # 登出后仍在同一窗口，用同一个码 → 被防重放拒绝
    _post(client, "/api/auth/logout")
    _login(client, uname)
    assert _post(client, "/api/auth/2fa/verify", {"code": code}).status_code == 400


def test_login_with_recovery_code(app, client):
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    secret = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    codes = _post(client, "/api/auth/2fa/confirm",
                  {"code": totp_at(secret)}).get_json()["recovery_codes"]
    _post(client, "/api/auth/logout")

    _login(client, uname)
    assert _post(client, "/api/auth/2fa/verify", {"code": codes[0]}).status_code == 200
    # 一次性：再用一次失败
    _post(client, "/api/auth/logout")
    _login(client, uname)
    assert _post(client, "/api/auth/2fa/verify", {"code": codes[0]}).status_code == 400


def test_disable_requires_password_and_code(app, client, fake_clock):
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    secret = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    fake_clock["c"] = 1000
    _post(client, "/api/auth/2fa/confirm", {"code": totp_at(secret)})

    fake_clock["c"] = 1001
    code = totp_at(secret)
    assert _post(client, "/api/auth/2fa/disable",
                 {"password": "wrong-pwd", "code": code}).status_code == 400
    assert _post(client, "/api/auth/2fa/disable",
                 {"password": PASSWORD, "code": "000000"}).status_code == 400
    ok = _post(client, "/api/auth/2fa/disable", {"password": PASSWORD, "code": code})
    assert ok.status_code == 200
    assert client.get("/api/auth/2fa/status").get_json()["enrolled"] is False


def test_enroll_reset_disables_until_reconfirmed(app, client):
    """重新 enroll 会打回未确认，避免「换了密钥但没验证」把用户锁在门外。"""
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    s1 = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    _post(client, "/api/auth/2fa/confirm", {"code": totp_at(s1)})
    assert client.get("/api/auth/2fa/status").get_json()["enrolled"] is True
    _post(client, "/api/auth/2fa/enroll")
    assert client.get("/api/auth/2fa/status").get_json()["enrolled"] is False


def test_admin_page_registered_and_renders(app, client):
    """后台页必须真实可达（历史教训：模块漏注册到 admin/__init__.py 会静默 404）。"""
    with app.app_context():
        u = _mkuser()
        uid = u.id
    assert "admin.twofa" in [r.endpoint for r in app.url_map.iter_rules()]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["session_version"] = 0
    r = client.get("/admin/2fa")
    assert r.status_code == 200
    assert "两步验证" in r.get_data(as_text=True)


def test_admin_page_shows_disabled_and_blocks_enroll(app, client):
    """全局未开启时：页面提示未启用，且表单提交绑定被拒（不会生成密钥）。"""
    with app.app_context():
        u = _mkuser()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["session_version"] = 0
    body = client.get("/admin/2fa").get_data(as_text=True)
    assert "未启用" in body
    tok = _csrf(client)
    client.post("/admin/2fa", data={"csrf_token": tok, "action": "enroll"})
    with app.app_context():
        assert UserTwoFactor.query.filter_by(user_id=uid).first() is None


def test_admin_enroll_and_confirm_flow(app, client):
    """后台表单走通：生成密钥 → 输入动态码 → 启用成功。"""
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["session_version"] = 0
    tok = _csrf(client)
    r = client.post("/admin/2fa", data={"csrf_token": tok, "action": "enroll"})
    assert r.status_code == 200
    # 页面回显明文密钥（otpauth URI 只用于生成二维码，不直接展示）
    with app.app_context():
        row = UserTwoFactor.query.filter_by(user_id=uid).first()
        assert row is not None and row.enabled is False   # 未确认不算启用
        secret = get_secret(row)
    assert secret in r.get_data(as_text=True)

    r2 = client.post("/admin/2fa",
                     data={"csrf_token": _csrf(client), "action": "confirm",
                           "code": totp_at(secret)})
    assert r2.status_code == 200
    with app.app_context():
        assert UserTwoFactor.query.filter_by(user_id=uid).first().enabled is True


def test_pending_state_expires(app, client):
    """挂起态超时后必须重新登录（不能拿旧挂起态无限试码）。"""
    app.config["TWOFA_ENABLED"] = True
    with app.app_context():
        u = _mkuser()
        uname = u.username   # 出上下文后实例即 detached，先取成标量
    _login(client, uname)
    secret = _post(client, "/api/auth/2fa/enroll").get_json()["secret"]
    _post(client, "/api/auth/2fa/confirm", {"code": totp_at(secret)})
    _post(client, "/api/auth/logout")
    _login(client, uname)

    with client.session_transaction() as sess:
        sess["twofa_pending_at"] = 1   # 很久以前
    assert _post(client, "/api/auth/2fa/verify", {"code": totp_at(secret)}).status_code == 400
    assert client.get("/api/auth/me").get_json()["user"] is None
