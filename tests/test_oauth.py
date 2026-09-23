"""OAuth 第三方登录（v3.21.0，config-gated）测试。

核心断言：
- 未配置凭据时整体休眠（providers 空、start 503）。
- 配置后 start 返回 authorize_url 并落会话 state。
- callback 校验 state、换 token（mock）、新建/绑定本地用户并写入登录态。
- state 不匹配 / 无会话 → 安全重定向到 ?oauth=error（绝不泄漏异常）。
"""
import secrets

from models import db, User, OAuthAccount, ROLE_USER


def _configure(app, provider="github"):
    if provider == "github":
        app.config["OAUTH_GITHUB_CLIENT_ID"] = "cid-test"
        app.config["OAUTH_GITHUB_CLIENT_SECRET"] = "sec-test"
    else:
        app.config["OAUTH_GOOGLE_CLIENT_ID"] = "cid-google"
        app.config["OAUTH_GOOGLE_CLIENT_SECRET"] = "sec-google"


def test_providers_empty_when_unconfigured(client):
    resp = client.get("/api/auth/oauth/providers")
    assert resp.status_code == 200
    assert resp.get_json()["providers"] == []


def test_providers_lists_configured(app, client):
    _configure(app, "github")
    resp = client.get("/api/auth/oauth/providers")
    assert resp.get_json()["providers"] == ["github"]


def test_start_503_when_not_configured(client):
    resp = client.get("/api/auth/oauth/github/start")
    assert resp.status_code == 503


def test_start_unknown_provider_503(client):
    resp = client.get("/api/auth/oauth/discord/start")
    assert resp.status_code == 503


def test_start_returns_authorize_url_and_state(app, client):
    _configure(app, "github")
    resp = client.get("/api/auth/oauth/github/start")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "authorize_url" in body
    assert "github.com/login/oauth/authorize" in body["authorize_url"]
    assert "state=" in body["authorize_url"]
    with client.session_transaction() as sess:
        assert sess.get("oauth_state")
        assert sess.get("oauth_provider") == "github"


def test_callback_state_mismatch_returns_error(app, client):
    _configure(app, "github")
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "expected"
    resp = client.get("/api/auth/oauth/github/callback?code=X&state=wrong")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=error")


def test_callback_no_session_returns_error(app, client):
    _configure(app, "github")
    resp = client.get("/api/auth/oauth/github/callback?code=X&state=Y")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=error")


def test_callback_exchange_failure_returns_error(app, client, monkeypatch):
    _configure(app, "github")
    monkeypatch.setattr("oauth.exchange_code", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "s1"
    resp = client.get("/api/auth/oauth/github/callback?code=X&state=s1")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=error")


def test_callback_creates_user_and_logs_in(app, client, monkeypatch):
    _configure(app, "github")
    # 仅 mock 网络调用；find_or_create_user 走生产代码（含新建用户 + 落 OAuthAccount 绑定）
    monkeypatch.setattr(
        "oauth.exchange_code",
        lambda *a, **k: {"sub": "uid-12345", "email": "gh@example.com", "name": "ghuser"},
    )

    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "s2"

    resp = client.get("/api/auth/oauth/github/callback?code=CODE&state=s2")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=ok")

    with client.session_transaction() as sess:
        user_id = sess.get("user_id")
        assert user_id, "登录态应写入 user_id"
        assert "oauth_provider" not in sess  # 登录后清理临时态
        assert "oauth_state" not in sess

    with app.app_context():
        assert db.session.get(User, user_id) is not None
        link = OAuthAccount.query.filter_by(provider="github", sub="uid-12345").first()
        assert link is not None
        assert link.user_id == user_id


def test_callback_binds_existing_email(app, client, monkeypatch):
    _configure(app, "google")
    with app.app_context():
        existing = User(username="preuser", email="pre@example.com", role=ROLE_USER)
        existing.set_password("x")
        db.session.add(existing)
        db.session.commit()
        existing_id = existing.id

    monkeypatch.setattr(
        "oauth.exchange_code",
        lambda *a, **k: {"sub": "gsub-9", "email": "pre@example.com",
                         "name": "Pre User", "email_verified": True},
    )
    # 不 mock find_or_create_user：走生产代码，验证按**已验证**邮箱命中已有用户并绑定

    with client.session_transaction() as sess:
        sess["oauth_provider"] = "google"
        sess["oauth_state"] = "s3"

    resp = client.get("/api/auth/oauth/google/callback?code=C&state=s3")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=ok")

    with client.session_transaction() as sess:
        assert sess.get("user_id") == existing_id

    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="google", sub="gsub-9").first()
        assert link is not None
        assert link.user_id == existing_id


# ---------- 邮箱验证边界（OAuth 账号接管防线）----------
# 这批用例 mock 的是**网络层** _http_json，让 exchange_code 的真实判定逻辑跑起来
# （只 mock exchange_code 会把它本身的验证逻辑一起替掉，等于没测）。

def _mkvictim():
    """建一个用户名+邮箱都随机的既有账号（临时库跨用例共享，避免互相命中）。"""
    u = User(username="victim_" + secrets.token_hex(3),
             email="victim_" + secrets.token_hex(3) + "@example.com", role=ROLE_USER)
    u.set_password("x")
    db.session.add(u)
    db.session.commit()
    return u.id, u.email


def _github_flow(monkeypatch, login="attacker", target_email="victim@example.com",
                 verified=False, sub=999):
    def fake_http(url, data=None, headers=None, method="GET"):
        if url.endswith("/access_token"):
            return {"access_token": "tok"}
        if url.endswith("/user"):
            return {"id": sub, "login": login, "email": target_email}
        if url.endswith("/user/emails"):
            return [{"email": target_email, "primary": True, "verified": verified}]
        return {}
    monkeypatch.setattr("oauth._http_json", fake_http)


def test_github_unverified_email_cannot_bind_existing_account(app, client, monkeypatch):
    """未验证邮箱绝不绑定既有账号 —— 防 OAuth 账号接管。

    攻击者注册 GitHub 账号、把公开邮箱填成受害者邮箱，若照单全收即可接管受害者账号。
    """
    _configure(app, "github")
    with app.app_context():
        victim_id, victim_email = _mkvictim()

    _github_flow(monkeypatch, verified=False, target_email=victim_email)
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "st1"
    resp = client.get("/api/auth/oauth/github/callback?code=C&state=st1")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        uid = sess.get("user_id")

    with app.app_context():
        assert uid != victim_id, "未验证邮箱绝不能命中既有账号"
        new_user = db.session.get(User, uid)
        assert new_user.email == "", "未验证邮箱不应落到账号上"
        assert OAuthAccount.query.filter_by(provider="github", sub="999").first().user_id == uid


def test_github_verified_email_binds_existing_account(app, client, monkeypatch):
    """已验证邮箱（/user/emails 明确 verified+primary）才允许绑定既有账号。"""
    _configure(app, "github")
    with app.app_context():
        victim_id, victim_email = _mkvictim()

    _github_flow(monkeypatch, verified=True, sub=1001, target_email=victim_email)
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "st2"
    client.get("/api/auth/oauth/github/callback?code=C&state=st2")

    with client.session_transaction() as sess:
        assert sess.get("user_id") == victim_id
    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="github", sub="1001").first()
        assert link.user_id == victim_id


def test_google_unverified_email_not_bound(app, client, monkeypatch):
    """Google 侧等价防线：email_verified=false 时不按邮箱命中既有账号。"""
    _configure(app, "google")
    with app.app_context():
        victim_id, victim_email = _mkvictim()

    def fake_http(url, data=None, headers=None, method="GET"):
        if url.endswith("/token"):
            return {"access_token": "tok"}
        return {"sub": "g1", "email": victim_email,
                "email_verified": False, "name": "Attacker"}
    monkeypatch.setattr("oauth._http_json", fake_http)

    with client.session_transaction() as sess:
        sess["oauth_provider"] = "google"
        sess["oauth_state"] = "st3"
    client.get("/api/auth/oauth/google/callback?code=C&state=st3")

    with client.session_transaction() as sess:
        assert sess.get("user_id") != victim_id
