"""OAuth 第三方登录（v3.21.0，config-gated）测试。

核心断言：
- 未配置凭据时整体休眠（providers 空、start 503）。
- 配置后 start 返回 authorize_url 并落会话 state。
- callback 校验 state、换 token（mock）、新建/绑定本地用户并写入登录态。
- state 不匹配 / 无会话 → 安全重定向到 ?oauth=error（绝不泄漏异常）。
"""
import contextlib
import pytest
import secrets
import time

from models import db, User, OAuthAccount, ROLE_USER


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """清空内存限流计数（同 test_twofa.py）：OAuth 三个端点现在都带 rate_limit，
    而 `_RATE` 是 utils.net 的模块级字典，跨用例累积会让后跑的回调用例被判 429。"""
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


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
        sess["oauth_state_at"] = int(time.time())
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
        sess["oauth_state_at"] = int(time.time())
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
        sess["oauth_state_at"] = int(time.time())

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


def test_callback_does_not_claim_existing_account_by_email(app, client, monkeypatch):
    """未登录的 OAuth 回调**绝不**按邮箱认领既有账号，即使 provider 说邮箱已验证。"""
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
    # 生产代码：邮箱已验证，但**未登录的回调不得按邮箱认领既有账号**
    # （v3.21.2 审计：本地注册对 email 零验证，见 test_oauth_email_preclaim_cannot_takeover）

    with client.session_transaction() as sess:
        sess["oauth_provider"] = "google"
        sess["oauth_state"] = "s3"
        sess["oauth_state_at"] = int(time.time())

    resp = client.get("/api/auth/oauth/google/callback?code=C&state=s3")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("?oauth=ok")

    with client.session_transaction() as sess:
        new_id = sess.get("user_id")
        assert new_id and new_id != existing_id, "不得静默落进别人按邮箱认领的账号"

    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="google", sub="gsub-9").first()
        assert link is not None
        assert link.user_id == new_id
        assert db.session.get(User, existing_id) is not None


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
        sess["oauth_state_at"] = int(time.time())
    resp = client.get("/api/auth/oauth/github/callback?code=C&state=st1")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        uid = sess.get("user_id")

    with app.app_context():
        assert uid != victim_id, "未验证邮箱绝不能命中既有账号"
        new_user = db.session.get(User, uid)
        assert new_user.email == "", "未验证邮箱不应落到账号上"
        assert OAuthAccount.query.filter_by(provider="github", sub="999").first().user_id == uid


def test_oauth_email_preclaim_cannot_takeover(app, client, monkeypatch):
    """**先占邮箱**不得换来到手账号（v3.21.2 审计 High，接管类）。

    R93 §93.1 修的是「第三方返回的邮箱不可信」这一半；另一半是**本地库里存的邮箱
    同样没验证过**：`auth_register` / `routes.register` 对 email 只做 strip()，
    无格式校验、无唯一约束、无所有权验证。于是攻击者可以：

      1) 用受害者邮箱注册一个本地账号（密码自己知道）；
      2) 等受害者第一次点「用 GitHub 登录」；
      3) 旧实现 `User.query.filter_by(email=email).first()` 命中**攻击者**那个账号，
         并把受害者的 provider sub 永久绑上去（sub 命中在邮箱匹配之前，之后每次
         OAuth 登录都落进攻击者账号，且再也解不开）。

    现在认领既有账号只保留「该账号已登录」这一个入口，所以未登录回调只会新建账号。
    """
    _configure(app, "github")
    with app.app_context():
        victim_id, victim_email = _mkvictim()
        attacker = User(username="attacker_" + secrets.token_hex(3),
                        email=victim_email, role=ROLE_USER)   # 抢先把受害者邮箱注册成自己的
        attacker.set_password("known-to-attacker")
        db.session.add(attacker)
        db.session.commit()
        attacker_id = attacker.id
        assert attacker_id != victim_id

    _github_flow(monkeypatch, verified=True, sub=1001, target_email=victim_email)
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "st2"
        sess["oauth_state_at"] = int(time.time())
    client.get("/api/auth/oauth/github/callback?code=C&state=st2")

    with client.session_transaction() as sess:
        uid = sess.get("user_id")
        assert uid and uid not in (attacker_id, victim_id), \
            "既不得落进抢先注册的账号，也不得凭空认领受害者账号"
    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="github", sub="1001").first()
        assert link.user_id == uid
        assert db.session.get(User, attacker_id).email == victim_email   # 攻击者账号未被绑走
        assert OAuthAccount.query.filter_by(user_id=attacker_id).count() == 0


def test_oauth_binds_to_currently_logged_in_account(app, client, monkeypatch):
    """认领既有账号的唯一入口：**该账号当前已登录**（身份已由密码/第二因素证明）。"""
    _configure(app, "github")
    with app.app_context():
        victim_id, victim_email = _mkvictim()
        u = db.session.get(User, victim_id)
        u.set_password("pw-for-login")
        db.session.commit()
        victim_name = u.username          # 出上下文即 detached，先取成标量
        assert victim_name

    client.post("/api/auth/login", json={"username": victim_name, "password": "pw-for-login"},
                headers={"X-CSRF-Token": client.get("/api/csrf").get_json()["csrf_token"]})
    with client.session_transaction() as sess:
        assert sess.get("user_id") == victim_id
        sess["oauth_provider"] = "github"
        sess["oauth_state"] = "st2b"
        sess["oauth_state_at"] = int(time.time())

    _github_flow(monkeypatch, verified=True, sub=1002, target_email=victim_email)
    client.get("/api/auth/oauth/github/callback?code=C&state=st2b")

    with client.session_transaction() as sess:
        assert sess.get("user_id") == victim_id, "已登录会话应绑到自己这个账号"
    with app.app_context():
        link = OAuthAccount.query.filter_by(provider="github", sub="1002").first()
        assert link is not None and link.user_id == victim_id


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
        sess["oauth_state_at"] = int(time.time())
    client.get("/api/auth/oauth/google/callback?code=C&state=st3")

    with client.session_transaction() as sess:
        assert sess.get("user_id") != victim_id
