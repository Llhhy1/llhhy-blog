"""后台「第三方账号绑定」列表与解绑测试（R94 §94.8-7 可发现性缺口）。

覆盖的边界（每条对着一条真实风险，不是凑数）：
- 列表页能看到自己的绑定（缺口本身：原先无处可查）。
- 正确密码可解绑。
- **密码错误不解绑**（密码确认同时是「仍有可用登录方式」的闸门）。
- **不能解绑别人的绑定**（改 link_id 越权）。
- **超管不能解掉他人最后一个绑定**（否则把对方锁在门外）。
- 超管在对方还有多个绑定时可以解（保留救助能力）。

⚠️ 建数据一律放在 `with app.app_context()` 内，出上下文前把 id/username 取成标量
（ORM 实例出上下文即 detached，这是本项目测试的既有约定）。
"""
import contextlib
import secrets

import pytest

from models import db, User, OAuthAccount, ROLE_USER, ROLE_SUPER

PASSWORD = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _clear_rate_limit():
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


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password},
                       headers={"X-CSRF-Token": _csrf(client)})


def _form_post(client, path, payload):
    return client.post(path, data=payload, headers={"X-CSRF-Token": _csrf(client)})


def _mkuser(role=ROLE_USER):
    """建用户；返回 (id, username)。必须在 app_context 内调用。"""
    u = User(username="uob_" + secrets.token_hex(4),
             email="uob_" + secrets.token_hex(4) + "@example.com",
             role=role, must_change_password=False)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    return u.id, u.username


def _bind(uid, provider="github", sub=None):
    """建绑定；返回 link id。必须在 app_context 内调用。"""
    link = OAuthAccount(user_id=uid, provider=provider,
                        sub=sub or ("sub_" + secrets.token_hex(4)), email="a@b.com")
    db.session.add(link)
    db.session.commit()
    return link.id


def _count(uid):
    """该账号的绑定数。必须在 app_context 内调用。"""
    return OAuthAccount.query.filter_by(user_id=uid).count()


def _exists(lid):
    return db.session.get(OAuthAccount, lid) is not None


# ---------- 访问与列表 ----------

def test_bindings_page_requires_login(client):
    resp = client.get("/admin/oauth")
    assert resp.status_code in (302, 401, 403)


def test_bindings_page_lists_own_links(app, client):
    with app.app_context():
        uid, uname = _mkuser()
        _bind(uid, "github", "gh-1")
        _bind(uid, "google", "gg-1")
    assert _login(client, uname).status_code == 200

    resp = client.get("/admin/oauth")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "gh-1" in body and "gg-1" in body


# ---------- 解绑主路径 ----------

def test_unbind_with_correct_password(app, client):
    with app.app_context():
        uid, uname = _mkuser()
        lid = _bind(uid, "github", "gh-del")
    _login(client, uname)

    resp = _form_post(client, "/admin/oauth/unbind", {"link_id": lid, "password": PASSWORD})
    assert resp.status_code == 302
    with app.app_context():
        assert _count(uid) == 0


def test_unbind_wrong_password_keeps_binding(app, client):
    """密码错误 = 没能证明「仍有可用登录方式」 ⇒ 不解绑，避免把人锁在门外。"""
    with app.app_context():
        uid, uname = _mkuser()
        lid = _bind(uid, "github", "gh-keep")
    _login(client, uname)

    resp = _form_post(client, "/admin/oauth/unbind",
                      {"link_id": lid, "password": "totally-wrong"})
    assert resp.status_code == 302
    with app.app_context():
        assert _count(uid) == 1
        assert _exists(lid)


def test_unbind_only_removes_target_link(app, client):
    with app.app_context():
        uid, uname = _mkuser()
        keep_id = _bind(uid, "github", "gh-stay")
        drop_id = _bind(uid, "google", "gg-go")
    _login(client, uname)

    _form_post(client, "/admin/oauth/unbind", {"link_id": drop_id, "password": PASSWORD})
    with app.app_context():
        assert _count(uid) == 1
        assert _exists(keep_id)


# ---------- 越权与锁死保护 ----------

def test_cannot_unbind_other_users_link(app, client):
    """改 link_id 指向他人绑定 ⇒ 拒绝，对方绑定原样保留。"""
    with app.app_context():
        my_uid, my_name = _mkuser()
        victim_uid, _ = _mkuser()
        victim_lid = _bind(victim_uid, "github", "gh-victim")
    _login(client, my_name)

    _form_post(client, "/admin/oauth/unbind", {"link_id": victim_lid, "password": PASSWORD})
    with app.app_context():
        assert _exists(victim_lid)
        assert _count(victim_uid) == 1


def test_super_cannot_remove_others_last_binding(app, client):
    """超管密码只能证明超管身份，不能证明对方还有别的登录方式 ⇒ 挡掉。"""
    with app.app_context():
        su_uid, su_name = _mkuser(role=ROLE_SUPER)
        target_uid, _ = _mkuser()
        only_lid = _bind(target_uid, "github", "gh-only")
    _login(client, su_name)

    _form_post(client, "/admin/oauth/unbind",
               {"link_id": only_lid, "password": PASSWORD, "user_id": target_uid})
    with app.app_context():
        assert _exists(only_lid), "他人仅剩一个绑定时不得解绑，否则把对方永久锁在门外"


def test_super_can_unbind_other_when_multiple_bindings(app, client):
    """对方还有别的绑定时超管可以解 —— 保留救助受害者的能力。"""
    with app.app_context():
        su_uid, su_name = _mkuser(role=ROLE_SUPER)
        target_uid, _ = _mkuser()
        drop_id = _bind(target_uid, "github", "gh-a")
        stay_id = _bind(target_uid, "google", "gg-b")
    _login(client, su_name)

    _form_post(client, "/admin/oauth/unbind",
               {"link_id": drop_id, "password": PASSWORD, "user_id": target_uid})
    with app.app_context():
        assert not _exists(drop_id)
        assert _exists(stay_id)


def test_missing_link_id_is_not_a_500(app, client):
    with app.app_context():
        uid, uname = _mkuser()
        _bind(uid, "github", "gh-x")
    _login(client, uname)

    resp = _form_post(client, "/admin/oauth/unbind", {"link_id": "", "password": PASSWORD})
    assert resp.status_code == 302
    with app.app_context():
        assert _count(uid) == 1
