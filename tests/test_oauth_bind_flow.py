"""第三方账号「绑定」流程守卫（v3.25.10）。

**这个功能此前完全不存在**：`/admin/oauth` 页只有查看 + 解绑，没有任何"开始绑定"
的入口 —— 机制是通的（`api/auth.py::oauth_callback` 里已登录状态下会
`bind_user_id=session["user_id"]`），但用户无从触发。

🔴 **本文件最核心的一条是 `test_binding_a_provider_owned_by_another_user_is_refused`**：
它锁的是 v3.25.10 顺手修掉的一个**存量**缺陷 —— `find_or_create_user` 原先在
`(provider, sub)` 命中已有绑定时**无条件返回那个用户**，于是「已登录的 X 授权了一个
其实绑给 Y 的第三方账号」会被**静默切成 Y 的身份**。加绑定入口会让这条路径从边缘情况
变成常见路径，所以必须挡住，且必须有守卫。
"""
import contextlib
import secrets

import pytest

from models import db, User, OAuthAccount, Setting, ROLE_SUPER, ROLE_USER

PASSWORD = "Passw0rd!23"
GITHUB_SUB = "gh-sub-shared-0001"


def _r():
    return secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _clean(app):
    def _wipe():
        with app.app_context():
            db.session.query(OAuthAccount).delete()
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


def _mkuser(app, role=ROLE_USER):
    """建用户；返回 (id, username) 标量。

    ⚠️ ORM 实现在 app_context 之外会 detached（本项目既有约定），
    所以这里在上下文内建、只把标量带出来。
    """
    uname = "ob_" + _r()
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com", role=role,
                 must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
        return u.id, uname


def _login(client, uname):
    d = client.get("/api/csrf").get_json() or {}
    r = client.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
                    headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""})
    assert r.status_code == 200


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _configure_github(app, cid="cid-x", sec="sec-x"):
    app.config["OAUTH_GITHUB_CLIENT_ID"] = cid
    app.config["OAUTH_GITHUB_CLIENT_SECRET"] = sec


def _mock_exchange(monkeypatch, sub=GITHUB_SUB, email="owner@example.com",
                   verified=True):
    monkeypatch.setattr("oauth.exchange_code",
                        lambda *a, **k: {"sub": sub, "email": email,
                                         "name": "octo", "email_verified": verified})


def _start_binding(client, provider="github"):
    """走完「POST 绑定 → 转发 start」，把 session 里的 state 准备好。

    ⚠️ `start` 默认返回 **JSON**（前端 store.js 消费 `authorize_url`），
    绑定流程靠 `?redirect=1` 走无 JS 降级才 302 到 provider —— 断言要对准这条。
    """
    r = client.post("/admin/oauth/bind/%s" % provider, headers=_csrf(client))
    assert r.status_code == 302
    start = client.get("/api/auth/oauth/%s/start?redirect=1" % provider)
    assert start.status_code == 302, "带 redirect=1 应直接 302 到 provider"
    assert "github.com/login/oauth/authorize" in (start.headers.get("Location") or "")
    with client.session_transaction() as sess:
        return sess.get("oauth_state")


# ---------- 入口：必须是 POST + CSRF ----------

def test_bind_start_requires_post(client, app):
    """⚠️ 绝不能做成 GET 链接：绑定目标取自 session 的 user_id，
    GET 会让任何人构造链接诱导他人发起绑定。"""
    uid, uname = _mkuser(app)
    _login(client, uname)
    _configure_github(app)
    r = client.get("/admin/oauth/bind/github")
    assert r.status_code == 405, "绑定入口必须只接受 POST"


def test_bind_start_requires_csrf(client, app):
    uid, uname = _mkuser(app)
    _login(client, uname)
    _configure_github(app)
    r = client.post("/admin/oauth/bind/github")
    assert r.status_code == 403, "缺 CSRF 必须被全局钩子拦下"


def test_bind_start_requires_login(app):
    _configure_github(app)
    r = app.test_client().post("/admin/oauth/bind/github")
    assert r.status_code in (302, 401, 403)


# ---------- 核心：绑定到当前账号 ----------

def test_binding_attaches_provider_to_current_user(client, app, monkeypatch):
    uid, uname = _mkuser(app)
    _login(client, uname)
    _configure_github(app)
    _mock_exchange(monkeypatch)
    state = _start_binding(client)
    r = client.get("/api/auth/oauth/github/callback?code=X&state=%s" % state)
    assert r.status_code == 302
    assert "/admin/oauth" in (r.headers.get("Location") or ""), "绑定结果应回到绑定页"
    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="github", sub=GITHUB_SUB).first()
        assert link is not None and link.user_id == uid
        assert OAuthAccount.query.filter_by(user_id=uid).count() == 1


def test_binding_page_shows_button_for_configured_provider(client, app):
    uid, uname = _mkuser(app)
    _login(client, uname)
    _configure_github(app)
    html = client.get("/admin/oauth").get_data(as_text=True)
    assert "/admin/oauth/bind/github" in html, "已配置未绑定的渠道要有绑定按钮"
    assert "绑定 GitHub" in html


def test_binding_page_shows_config_hint_when_not_configured(client, app):
    """没配置凭据时**不能**给绑定按钮（点了只会报错），只给指引。

    且指引要**按权限分层**：超管能拿到配置页入口，普通用户只看得到
    「站点尚未启用」—— 不该把超管专属的入口透给普通用户。
    """
    uid, uname = _mkuser(app)
    _login(client, uname)
    html = client.get("/admin/oauth").get_data(as_text=True)
    assert "尚未启用" in html
    assert "/admin/oauth-settings" not in html, "普通用户不该看到配置页入口"
    assert "/admin/oauth/bind/github" not in html, "没配置就不该给绑定按钮（点了只会报错）"


def test_super_sees_config_link_when_provider_not_configured(client, app):
    su_id, su_name = _mkuser(app, ROLE_SUPER)
    _login(client, su_name)
    html = client.get("/admin/oauth").get_data(as_text=True)
    assert "未配置" in html and "/admin/oauth-settings" in html
    assert "/admin/oauth/bind/github" not in html


def test_already_bound_provider_has_no_bind_button(client, app):
    uid, uname = _mkuser(app)
    with app.app_context():
        db.session.add(OAuthAccount(user_id=uid, provider="github", sub="s-old"))
        db.session.commit()
    _login(client, uname)
    _configure_github(app)
    html = client.get("/admin/oauth").get_data(as_text=True)
    assert "已绑定" in html
    assert "/admin/oauth/bind/github" not in html


# ---------- 🔴 核心安全守卫：不得静默切换身份 ----------

def test_binding_a_provider_owned_by_another_user_is_refused(client, app, monkeypatch):
    """X 已登录，去授权一个**已经绑给 Y** 的第三方账号 → 必须被拒绝，
    且 **X 的 session 仍然是 X**（不能被悄悄切成 Y）。

    原实现这里 `if link: return db.session.get(User, link.user_id)`，
    于是 X 的 `session["user_id"]` 会被 callback 改写成 Y —— 「我明明绑自己的
    账号，怎么登录成了别人」。加绑定入口后这条路径会从边缘情况变成常见路径。
    """
    y_id, y_name = _mkuser(app)
    x_id, x_name = _mkuser(app)
    with app.app_context():
        db.session.add(OAuthAccount(user_id=y_id, provider="github", sub=GITHUB_SUB))
        db.session.commit()
    _login(client, x_name)
    _configure_github(app)
    _mock_exchange(monkeypatch)
    state = _start_binding(client)
    r = client.get("/api/auth/oauth/github/callback?code=X&state=%s" % state)
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_id"] == x_id, "❌ 会话被换成了别人"
    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="github", sub=GITHUB_SUB).first()
        assert link.user_id == y_id, "❌ 原有绑定被改写"
        assert OAuthAccount.query.filter_by(user_id=x_id).count() == 0, "❌ X 反而被绑上了"


def test_rebind_refused_at_entry_point(client, app):
    """入口层就挡住重复绑定，不必走到 provider 那边再被拒。"""
    uid, uname = _mkuser(app)
    with app.app_context():
        db.session.add(OAuthAccount(user_id=uid, provider="github", sub="s-1"))
        db.session.commit()
    _login(client, uname)
    _configure_github(app)
    r = client.post("/admin/oauth/bind/github", headers=_csrf(client),
                    follow_redirects=True)
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert "oauth_bind_flow" not in sess, "不该标记绑定流程"


def test_super_cannot_bind_on_behalf_of_another_user(client, app):
    """超管代他人绑定 = 拿别人的身份往一个账号上靠，没有正当场景，
    而且它正是静默身份切换最容易发生的地方 → 不给入口。"""
    su_id, su_name = _mkuser(app, ROLE_SUPER)
    other_id, other_name = _mkuser(app)
    _login(client, su_name)
    _configure_github(app)
    html = client.get("/admin/oauth?user_id=%d" % other_id).get_data(as_text=True)
    assert "/admin/oauth/bind/github" not in html, "超管代绑不应有入口"


def test_unknown_provider_rejected(client, app):
    uid, uname = _mkuser(app)
    _login(client, uname)
    r = client.post("/admin/oauth/bind/wechat", headers=_csrf(client),
                    follow_redirects=True)
    assert r.status_code == 200


# ---------- 未登录走同一流程仍是「登录」而不是「绑定」 ----------

def test_login_flow_unchanged_when_not_using_bind_page(client, app, monkeypatch):
    """普通 OAuth 登录（未点绑定入口）行为必须**完全不变**：
    start 仍返回 JSON、callback 仍回首页 `?oauth=ok`。"""
    _configure_github(app)
    _mock_exchange(monkeypatch)
    s = client.get("/api/auth/oauth/github/start")
    assert s.status_code == 200, "默认仍返回 JSON（前端 store.js 依赖它）"
    assert s.get_json()["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    with client.session_transaction() as sess:
        state = sess.get("oauth_state")
    r = client.get("/api/auth/oauth/github/callback?code=X&state=%s" % state)
    assert r.headers.get("Location", "").endswith("?oauth=ok"), "非绑定流程不得改落点"


def test_start_without_redirect_param_still_returns_json(client, app):
    """`?redirect=1` 是**新增的降级参数**，不能改变既有调用方的返回形态。"""
    _configure_github(app)
    s = client.get("/api/auth/oauth/github/start")
    assert s.status_code == 200
    assert "authorize_url" in (s.get_json() or {})
