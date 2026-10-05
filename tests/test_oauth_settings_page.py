"""后台「第三方登录」配置页守卫（v3.25.7）。

**这个功能此前从未启用过**：v3.21.0 写完了后端（`oauth.py`）与前端按钮
（`LoginView.vue`），却**只留了环境变量一个入口**。生产实测
`/api/auth/oauth/providers` 返回 `{"providers":[]}`，登录页
`v-if="state.oauthProviders.length"` 为假 → 页面上一个按钮都没有。

所以这里最核心的断言是**端到端**的：「后台存完凭据 → 前台接口开始报这个 provider」。
中间任何一环断了，功能就还是死的，而单测各自的函数都照样绿。
"""
import contextlib
import json
import secrets

import pytest

from models import db, User, Setting, ROLE_SUPER, ROLE_USER

PASSWORD = "Passw0rd!23"


def _r():
    return secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _site_url(app):
    """固定站点对外地址。

    回调地址由 `site_base()` 派生，而测试库是共享的、**没有** site_url ——
    不固定的话「页面上要能看到回调地址」这条断言就取决于别的用例跑没跑过。
    teardown 删掉，避免把 `site_url` 泄漏给后续文件。
    """
    def _set(v):
        with app.app_context():
            db.session.query(Setting).filter_by(key="site_url").delete(
                synchronize_session=False)
            if v:
                db.session.add(Setting(key="site_url", value=v))
            db.session.commit()
    _set("https://www.llhhy.cn")
    yield
    _set(None)


@pytest.fixture(autouse=True)
def _clean_oauth_settings(app):
    """**前后都清** `oauth.*` 设置行。

    pytest 库是全 session 共享的（conftest 固定 `%TEMP%/llhhy-blog-pytest/test.db`），
    留一行 `oauth.github.client_id` 就会让 `test_oauth.py::test_providers_empty_when_unconfigured`
    在别的文件跑完之后假红 —— 而那种红会被误判成「我改坏了 OAuth」。
    """
    def _wipe():
        with app.app_context():
            db.session.query(Setting).filter(Setting.key.like("oauth.%")).delete(
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


@pytest.fixture()
def plain_client(app):
    """普通用户：配置页必须对他不可见（改那里等于改谁能登进本站）。

    ⚠️ 必须**独立** `app.test_client()`，不能复用 `client` fixture —— 同一个
    test_client 共享 cookie jar，普通用户一登录就把超管的会话顶掉，
    断言会得到「超管也 403」这种完全误导的失败。
    """
    c = app.test_client()
    uname = "u_" + _r()
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_USER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    d = c.get("/api/csrf").get_json() or {}
    assert c.post("/api/auth/login",
                  json={"username": uname, "password": PASSWORD},
                  headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}
                  ).status_code == 200
    return c


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _save(client, provider="github", client_id="cid-1", secret="sec-1"):
    return client.post("/admin/oauth-settings",
                       data={"action": "save", "provider": provider,
                             "client_id": client_id, "client_secret": secret},
                       headers=_csrf(client), follow_redirects=True)


# ---------- 权限 ----------

def test_settings_page_requires_super(super_client, plain_client):
    assert super_client.get("/admin/oauth-settings").status_code == 200
    assert plain_client.get("/admin/oauth-settings").status_code == 403


def test_save_requires_csrf(super_client):
    """全局 CSRF 钩子必须仍然拦住裸 POST（改凭据 = 改谁能登进站点）。"""
    r = super_client.post("/admin/oauth-settings",
                          data={"action": "save", "provider": "github",
                                "client_id": "x", "client_secret": "y"})
    assert r.status_code == 403


# ---------- 核心：端到端「存完就能用了」 ----------

def test_saving_credentials_activates_provider_for_public(super_client):
    """后台存完 → 前台接口立刻报出这个 provider（**功能从死到活的全过程**）。

    这一条是本文件存在的理由：任何一环断了（取值优先级、加密、Setting 读写、
    providers 接口）功能都还是死的，而各自的单测都可能照样绿。
    """
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == []
    _save(super_client, "github", "cid-abc", "sec-xyz")
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == ["github"]


def test_half_configured_does_not_activate(super_client):
    """只填一半**不启用**：最常见的失败态，不能让它显示成「已启用」。"""
    _save(super_client, "github", "cid-abc", "")
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == []
    html = super_client.get("/admin/oauth-settings").get_data(as_text=True)
    assert "只填了一半" in html, "必须明确告诉用户还差一个，否则会去反复检查自己漏了哪步"


def test_secret_blank_keeps_previous(super_client, app):
    """Secret 不回显，所以「留空」必须表示「不打算改」而不是「清空」。"""
    _save(super_client, "github", "cid-abc", "sec-xyz")
    _save(super_client, "github", "cid-abc", "")     # 只改 client_id
    with app.app_context():
        from oauth import _cred
        assert _cred("github", "client_secret") == "sec-xyz"
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == ["github"]


def test_secret_is_encrypted_at_rest(super_client, app):
    """Secret 必须 Fernet 加密落库 —— 明文进 Setting 表会被 CSV 导出带走。"""
    _save(super_client, "github", "cid-abc", "sec-PLAINTEXT-CANARY")
    with app.app_context():
        raw = Setting.query.filter_by(key="oauth.github.client_secret").first()
        assert raw is not None
        assert "sec-PLAINTEXT-CANARY" not in (raw.value or ""), "Secret 落库必须是密文"
        assert (raw.value or "").startswith("bkenc$")


def test_audit_never_records_credential_values(super_client, app):
    """审计 detail 会进 CSV 导出 —— 绝不能把凭据写进去。"""
    _save(super_client, "github", "cid-CANARY-ID", "sec-CANARY-SECRET")
    with app.app_context():
        from models import AuditLog
        rows = AuditLog.query.filter(AuditLog.action == "oauth_settings_save").all()
    assert rows, "保存凭据必须留审计"
    blob = json.dumps([{"action": r.action, "detail": r.detail} for r in rows],
                      ensure_ascii=False)
    assert "CANARY" not in blob, "审计里出现了凭据明文"
    assert "github" in blob, "审计要能看出改的是哪个渠道"


def test_clear_removes_credentials(super_client):
    _save(super_client, "github", "cid-abc", "sec-xyz")
    r = super_client.post("/admin/oauth-settings",
                          data={"action": "clear", "provider": "github"},
                          headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code == 200
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == []


def test_unknown_provider_rejected(super_client):
    _save(super_client, "wechat", "cid", "sec")
    assert super_client.get("/api/auth/oauth/providers").get_json()["providers"] == []


# ---------- 页面必须回答「去哪儿注册、回调地址填什么」 ----------

def test_page_shows_callback_url_and_signup_link(super_client):
    """回调地址填错是 OAuth 最常见的失败原因 —— 必须直接摆出来让人照抄。"""
    html = super_client.get("/admin/oauth-settings").get_data(as_text=True)
    assert "https://www.llhhy.cn/api/auth/oauth/github/callback" in html
    assert "github.com/settings/applications/new" in html, "要给出注册入口链接"
    assert "Authorization callback URL" in html, "要说清回调地址填在哪个字段"


def test_page_warns_when_site_url_missing(super_client, app):
    """site_url 没配 → 回调地址生成不出来，必须说清并指向设置页（否则死胡同）。"""
    app.config["SITE_URL"] = ""
    with app.app_context():
        db.session.query(Setting).filter_by(key="site_url").delete(synchronize_session=False)
        db.session.commit()
    html = super_client.get("/admin/oauth-settings").get_data(as_text=True)
    assert "站点对外地址" in html
    assert "#site_url" in html, "要能一键跳到该填的地方"

def test_bindings_page_links_to_settings(super_client):
    """绑定页原先只说「改环境变量并重启」—— 必须改成指向配置页。"""
    html = super_client.get("/admin/oauth").get_data(as_text=True)
    assert "/admin/oauth-settings" in html, "绑定页应能跳到配置页"
    assert "OAUTH_GITHUB_CLIENT_ID" not in html, "别再让用户去改环境变量"


# ---------- 向后兼容：环境变量仍然有效 ----------

def test_env_credentials_still_work(app, client):
    """老部署把凭据写在 env 里 —— 改了优先级会让它们的登录突然失效。"""
    app.config["OAUTH_GITHUB_CLIENT_ID"] = "env-cid"
    app.config["OAUTH_GITHUB_CLIENT_SECRET"] = "env-sec"
    assert client.get("/api/auth/oauth/providers").get_json()["providers"] == ["github"]


def test_db_wins_over_env(app, super_client):
    """DB 优先于 env（后台能改是既定语义），且页面要提示「去库里改才有用」。"""
    app.config["OAUTH_GITHUB_CLIENT_ID"] = "env-cid"
    app.config["OAUTH_GITHUB_CLIENT_SECRET"] = "env-sec"
    _save(super_client, "github", "db-cid", "db-sec")
    with app.app_context():
        from oauth import _cred
        assert _cred("github", "client_id") == "db-cid"
    html = super_client.get("/admin/oauth-settings").get_data(as_text=True)
    assert "环境变量" in html, "凭据来自 env 时要提示，否则改了没反应会白折腾"


def test_callback_url_is_pure_function():
    """回调地址推导必须是纯函数（不碰 request），配置页与登录流程共用一份逻辑。"""
    from oauth import callback_url
    assert callback_url("github", "https://x.example.com") == \
        "https://x.example.com/api/auth/oauth/github/callback"
    assert callback_url("github", "") == "", "未配置对外地址时必须返回空串，不猜域名"
    assert callback_url("wechat", "https://x.example.com") == ""
