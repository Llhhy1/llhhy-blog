"""后台「系统设置」守卫（v3.25.8）。

**这个页面解决的是同款缺陷的第二次出现**：第三方登录（v3.25.7 已修）之后，
2FA 又被投诉「还得我去配置服务器」。根因一样 —— 功能开关只能读环境变量，
改完必须重启 gunicorn，而后台**没有入口**。生产实测 env 文件里
`BLOG_TWOFA_ENABLED` 根本不存在 → 2FA 从 v3.21.0 上线起一直是关着的。

**核心断言是「改了立刻生效」**：每个开关都要证明
`Setting` 表里的值能直接改变**真实读点**的判定，而不是只在页面上显示。
"""
import contextlib
import secrets

import pytest

from models import db, User, Setting, ROLE_SUPER, ROLE_USER

PASSWORD = "Passw0rd!23"

FLAG_KEYS = ("twofa_enabled", "strong_password", "strong_password_mixed_case",
             "login_delay_seconds", "open_register", "captcha_enabled",
             "audit_log_days")


def _r():
    return secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _clean(app):
    """前后都清干净这些 key —— pytest 库是全 session 共享的。

    尤其 `twofa_enabled`：留一行 `true` 会让 `test_twofa.py` 里
    「未启用时整页拒绝绑定」的用例假红，而那种红会被误判成「我改坏了 2FA」。
    """
    def _wipe():
        with app.app_context():
            db.session.query(Setting).filter(Setting.key.in_(FLAG_KEYS)).delete(
                synchronize_session=False)
            db.session.commit()
    _wipe()
    yield
    _wipe()


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


@pytest.fixture()
def super_client(client, app):
    uname = "su_" + _r()
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    d = client.get("/api/csrf").get_json() or {}
    assert client.post("/api/auth/login",
                       json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}
                       ).status_code == 200
    return client


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _save(client, **flags):
    payload = {"action": "save"}
    for k, v in flags.items():
        payload["k_" + k] = v
    return client.post("/admin/system-settings", data=payload,
                       headers=_csrf(client), follow_redirects=True)


# ---------- 取值优先级：DB → env → default ----------

def test_flag_bool_priority_db_over_env(app):
    from utils import flag_bool
    with app.app_context():
        db.session.add(Setting(key="twofa_enabled", value="true"))
        db.session.commit()
        app.config["TWOFA_ENABLED"] = False          # 环境变量那一层
        assert flag_bool("twofa_enabled", "TWOFA_ENABLED", False) is True


def test_flag_bool_falls_back_to_env(app):
    from utils import flag_bool
    with app.app_context():
        app.config["TWOFA_ENABLED"] = True
        assert flag_bool("twofa_enabled", "TWOFA_ENABLED", False) is True


def test_flag_bool_default(app):
    from utils import flag_bool
    with app.app_context():
        app.config.pop("TWOFA_ENABLED", None)
        assert flag_bool("twofa_enabled", "TWOFA_ENABLED", False) is False


def test_flag_num_invalid_value_falls_back_to_default(app):
    """配置页是运营手填的，填错不该让整个流程 500。"""
    from utils import flag_num
    with app.app_context():
        db.session.add(Setting(key="audit_log_days", value="不是数字"))
        db.session.commit()
        app.config["AUDIT_LOG_DAYS"] = 30
        assert flag_num("audit_log_days", "AUDIT_LOG_DAYS", 90, int) == 30


# ---------- 核心：改了立刻生效，不用重启 ----------

def _enrolled_2fa_user(app, uname, password):
    """建一个**已绑定且已启用** 2FA 的用户，返回 (user_id, username)。

    直接造行而不是走 enroll→confirm：那条路要算 TOTP 动态码，
    而这里要验的是**闸门**，不是绑定流程本身。
    """
    import twofa
    from backup_settings import encrypt_secret
    from models import UserTwoFactor
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()
        db.session.add(UserTwoFactor(user_id=u.id,
                                     secret_enc=encrypt_secret(twofa.generate_secret()),
                                     enabled=True, last_counter=0))
        db.session.commit()
        return u.id, uname


def test_before_request_gate_actually_honors_the_switch(client, app):
    """🔑 **本文件最关键的一条**：验 `before_request` 那道闸门，而不只是 `api.auth._twofa_on()`。

    闸门代码在 `app.py` 里，和登录流程的 `_twofa_on()` 是**两处独立读点**。
    早期版本的守卫只测了后者，把闸门退回成读 `app.config`（v3.21.0 原行为）时
    **测试全绿** —— 而攻击者走的正是闸门，绕过它等于 2FA 形同虚设。
    变异测试抓到了这个漏洞，补上这条才真正锁死。
    """
    uid, uname = _enrolled_2fa_user(app, "e2fa_" + _r(), PASSWORD)
    d = client.get("/api/csrf").get_json() or {}
    assert client.post("/api/auth/login",
                       json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}
                       ).status_code == 200
    # 开关关着（默认）→ 闸门休眠，放行
    assert client.get("/admin/").status_code == 200
    # 后台打开开关 —— 同一进程，不重启
    with app.app_context():
        db.session.add(Setting(key="twofa_enabled", value="true"))
        db.session.commit()
    r = client.get("/admin/")
    assert r.status_code == 302, "已绑定 2FA 的用户未过二步，应被闸门重定向"
    assert "twofa" in (r.headers.get("Location") or "").lower()
    # API 路径则是 401 JSON。
    # ⚠️ 别用 `/api/auth/me` —— 它在闸门白名单里（前端靠它判断当前会话身份，
    # 无特权，放行是刻意的），拿它断言会假绿。
    r = client.get("/api/posts?limit=1")
    assert r.status_code == 401, "已绑定 2FA 的用户调 API 应返 401，实际 %s" % r.status_code
    assert (r.get_json() or {}).get("twofa_required") is True
    # 复位后恢复放行
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete()
        db.session.commit()
    assert client.get("/admin/").status_code == 200
    assert uid


def test_2fa_switch_takes_effect_without_restart(super_client, app):
    """**本文件存在的理由**。

    v3.21.0 起 2FA 只能靠环境变量开 → 改一次要 SSH + 重启 → 于是它
    从上线起就没启用过。这里证明：后台存一个值，**同一进程内**登录流程的
    2FA 闸门立刻改变判定。

    ⚠️ 不能拿「访问 /admin/ 被打回 302」当断言：未绑定 2FA 的用户本来
    就该放行（2FA 是自愿的），那样断言会假红。真正要证明的是**闸门本身**变了。
    """
    from api.auth import _twofa_on
    with app.app_context():
        assert _twofa_on() is False
    _save(super_client, twofa_enabled="true")
    with app.app_context():
        assert _twofa_on() is True, "存了就要立刻生效，不能等重启"
    # 绑定页也要跟着变（否则会出现「后台说开着、页面说没开」的矛盾）
    html = super_client.get("/admin/2fa").get_data(as_text=True)
    assert "两步验证未启用。" not in html, "全局开关已开，页面不该还显示「未启用」"
    assert 'value="enroll"' in html, "开关打开后应出现绑定入口"
    _save(super_client, twofa_enabled="false")
    with app.app_context():
        assert _twofa_on() is False


def test_open_register_switch_takes_effect(super_client, app):
    from utils import flag_bool
    with app.app_context():
        assert flag_bool("open_register", "BLOG_OPEN_REGISTER", True) is True
    _save(super_client, open_register="false")
    with app.app_context():
        assert flag_bool("open_register", "BLOG_OPEN_REGISTER", True) is False


def test_strong_password_switch_takes_effect(super_client, app):
    """弱密码（无数字）在强密码开启时应被拒；关掉后应放行。"""
    weak = "abcdefgh"
    with app.app_context():
        from admin._helpers import _weak_password
        assert _weak_password(weak) != ""      # 默认开启 → 拒绝
    _save(super_client, strong_password="false")
    with app.app_context():
        from admin._helpers import _weak_password
        assert _weak_password(weak) == ""      # 关掉后放行


def test_audit_days_switch_takes_effect(super_client, app):
    from utils import flag_num
    _save(super_client, audit_log_days="7")
    with app.app_context():
        assert flag_num("audit_log_days", "AUDIT_LOG_DAYS", 90, int) == 7


# ---------- 权限与安全 ----------

def test_page_requires_super(app):
    c = app.test_client()
    uname = "u_" + _r()
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_USER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    d = c.get("/api/csrf").get_json() or {}
    c.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
           headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""})
    assert c.get("/admin/system-settings").status_code == 403


def test_save_requires_csrf(super_client):
    r = super_client.post("/admin/system-settings",
                          data={"action": "save", "k_twofa_enabled": "true"})
    assert r.status_code == 403


def test_audit_records_before_and_after(super_client, app):
    """改安全开关必须能回溯「谁在什么时候把 2FA 关了」。"""
    import json
    _save(super_client, twofa_enabled="true")
    _save(super_client, twofa_enabled="false")
    with app.app_context():
        from models import AuditLog
        rows = AuditLog.query.filter(AuditLog.action == "system_settings_save").all()
    assert rows, "改开关必须留审计"
    blob = json.dumps([r.detail for r in rows], ensure_ascii=False)
    assert "两步验证" in blob, "审计要写清是哪个开关"
    low = blob.lower()
    assert "true" in low and "false" in low, "审计要含改动前后值"


# ---------- 页面本身 ----------

def test_page_shows_source_and_default(super_client):
    """只显示生效值不显示来源，运营改了没生效根本无从查起。"""
    html = super_client.get("/admin/system-settings").get_data(as_text=True)
    assert "两步验证" in html
    assert "来源：" in html
    assert "恢复默认" in html


def test_page_explains_what_is_deliberately_excluded(super_client):
    """刻意不放进来的（根信任 / 高频 / 启动时读）要在页面上讲清为什么，
    否则下次又会有人来问「为什么 SECRET_KEY 没有开关」。"""
    html = super_client.get("/admin/system-settings").get_data(as_text=True)
    assert "SECRET_KEY" in html and "根信任" in html
    assert "ENABLED_PLUGINS" in html


def test_reset_removes_override_and_hands_back_to_env(super_client, app):
    app.config["TWOFA_ENABLED"] = False
    _save(super_client, twofa_enabled="true")
    client = super_client
    client.post("/admin/system-settings",
                data={"action": "reset", "key": "twofa_enabled"},
                headers=_csrf(client), follow_redirects=True)
    with app.app_context():
        assert Setting.query.filter_by(key="twofa_enabled").first() is None
        from utils import flag_bool
        assert flag_bool("twofa_enabled", "TWOFA_ENABLED", False) is False


def test_out_of_range_value_is_rejected(super_client, app):
    _save(super_client, audit_log_days="99999")
    with app.app_context():
        from utils import flag_num
        assert flag_num("audit_log_days", "AUDIT_LOG_DAYS", 90, int) == 90, "超范围应拒绝"


def test_twofa_page_no_longer_tells_you_to_edit_server(super_client):
    """v3.21.0 的提示是「需设置环境变量 BLOG_TWOFA_ENABLED=true 并重启」。"""
    html = super_client.get("/admin/2fa").get_data(as_text=True)
    assert "BLOG_TWOFA_ENABLED" not in html, "不该再让用户去改服务器"
    assert "系统设置" in html, "要指向新入口"
