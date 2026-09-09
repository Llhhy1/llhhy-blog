# -*- coding: utf-8 -*-
"""主题中心回归测试（v3.16.0）。

覆盖（myblog/api/theme.py + myblog/admin/theme_center.py + themes.py）：
1. 权限：GET /api/theme 公开（200）；POST 未登录 / 普通管理员 → 403；超管 → 200。
2. 预设包：POST {pack_id} → 写 Setting（theme_pack / theme_tokens / accent_color），
   并返回亮/暗完整 token；/api/site 同步暴露新主题（pack_id + 双套 token）。
3. 自定义主题：POST {custom:{light:{accent:...}}} → theme_pack="custom" 接受；
   缺 accent / 非 dict → 400。
4. 未知 pack_id → 400。
5. 后台页：未登录 / 普通管理员 403；超管 200 且渲染了预设与「应用此主题」。

运行：仓库根目录 `python -m pytest tests/ -q`
测试库为仓库内持久化的 myblog/data/blog.db（gitignored）；用户名按 uuid 唯一，
每个用例 finally 清理自建用户、Setting 与审计，避免污染与冲突。
"""
import json
import uuid

import pytest

from models import db, User, Setting, AuditLog, ROLE_SUPER, ROLE_ADMIN
from utils import _sign_csrf


def _uid():
    return uuid.uuid4().hex[:10]


def _mkuser(role=ROLE_SUPER):
    u = User(username="theme-" + _uid(), email="theme-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False  # 否则会被跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    """登录（写 session）并生成与会话绑定的有效 CSRF token（与 test_mcp_services_admin 同法）。"""
    import secrets
    raw = secrets.token_hex(24)
    with client.application.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def tok_local(client):
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def _cleanup(uids=(), setting_keys=("theme_pack", "accent_color", "theme_tokens")):
    for k in setting_keys:
        s = Setting.query.filter_by(key=k).first()
        if s:
            db.session.delete(s)
    if uids:
        AuditLog.query.filter_by(action="theme").filter(
            AuditLog.user_id.in_(list(uids))).delete(synchronize_session=False)
    for u in uids:
        usr = db.session.get(User, u)
        if usr:
            db.session.delete(usr)
    db.session.commit()


# ---------------------------------------------------------------------------
# 公开读取 + 预设结构
# ---------------------------------------------------------------------------

def test_theme_get_public(client):
    assert client.get("/api/theme").status_code == 200


def test_theme_get_lists_presets(client):
    data = client.get("/api/theme").get_json()
    assert "presets" in data and len(data["presets"]) == 14
    ids = [p["id"] for p in data["presets"]]
    assert len(ids) == len(set(ids))        # id 唯一
    assert "classic-blue" in ids            # 首包存在
    assert "current" in data                # 含当前激活 pack_id
    # 每套预设都带亮/暗完整 token 且 accent 为合法 hex
    for p in data["presets"]:
        assert p["light"]["accent"].startswith("#")
        assert p["dark"]["bg"].startswith("#")


# ---------------------------------------------------------------------------
# 权限：POST 必须登录超管
# ---------------------------------------------------------------------------

def test_theme_post_requires_super(app, client):
    # 未登录（无会话）→ 403（被 CSRF / 权限闸拦）
    assert client.post("/api/theme",
                       json={"pack_id": "aurora-green"}).status_code == 403

    with app.app_context():
        admin = _mkuser(role=ROLE_ADMIN)
        superu = _mkuser(role=ROLE_SUPER)
        aid, sid = admin.id, superu.id
    try:
        # 普通管理员（带合法 CSRF + 会话）→ 角色闸 403
        tok = _auth(client, aid)
        r = client.post("/api/theme",
                        json={"pack_id": "aurora-green", "csrf_token": tok})
        assert r.status_code == 403
        # 超管（带合法 CSRF + 会话）→ 200
        tok = _auth(client, sid)
        assert client.post("/api/theme",
                           json={"pack_id": "aurora-green", "csrf_token": tok}).status_code == 200
    finally:
        with app.app_context():
            _cleanup(uids=(aid, sid))


# ---------------------------------------------------------------------------
# 应用预设包：写 Setting + 返回 /site 联动
# ---------------------------------------------------------------------------

def test_apply_preset_writes_settings(app, client):
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        tok = _auth(client, sid)
        r = client.post("/api/theme",
                        json={"pack_id": "aurora-green", "csrf_token": tok})
        assert r.status_code == 200
        data = r.get_json()
        assert data["pack_id"] == "aurora-green"
        assert data["theme_tokens"]["accent"] == "#12b886"
        assert data["theme_dark_tokens"]["bg"].startswith("#")

        with app.app_context():
            # Setting 落库三项
            assert Setting.query.filter_by(key="theme_pack").first().value == "aurora-green"
            assert Setting.query.filter_by(key="accent_color").first().value == "#12b886"
            toks = json.loads(Setting.query.filter_by(key="theme_tokens").first().value)
            assert toks["light"]["accent"] == "#12b886"
            assert toks["dark"]["bg"].startswith("#")

            # /api/site 同步暴露新主题（前端整体换肤依赖）
            s = client.get("/api/site").get_json()
            assert s["theme_pack"] == "aurora-green"
            assert s["theme_tokens"]["accent"] == "#12b886"
            assert s["theme_dark_tokens"]["bg"].startswith("#")
    finally:
        with app.app_context():
            _cleanup(uids=(sid,))


# ---------------------------------------------------------------------------
# 自定义主题
# ---------------------------------------------------------------------------

def test_apply_custom_theme(app, client):
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        tok = _auth(client, sid)
        r = client.post("/api/theme", json={
            "custom": {"light": {"accent": "#abcdef"}},
            "csrf_token": tok,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["pack_id"] == "custom"
        assert data["theme_tokens"]["accent"] == "#abcdef"
        # 未给 dark → 由 OKLCH 自动推导、非空
        assert data["theme_dark_tokens"]["bg"].startswith("#")

        with app.app_context():
            assert Setting.query.filter_by(key="theme_pack").first().value == "custom"
            assert Setting.query.filter_by(key="accent_color").first().value == "#abcdef"
    finally:
        with app.app_context():
            _cleanup(uids=(sid,))


def test_custom_invalid_400(app, client):
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        tok = _auth(client, sid)
        # 缺 accent
        r1 = client.post("/api/theme", json={
            "custom": {"light": {}}, "csrf_token": tok})
        assert r1.status_code == 400
        # 非 dict
        r2 = client.post("/api/theme", json={
            "custom": "not-a-dict", "csrf_token": tok})
        assert r2.status_code == 400
    finally:
        with app.app_context():
            _cleanup(uids=(sid,))


def test_unknown_pack_400(app, client):
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        tok = _auth(client, sid)
        r = client.post("/api/theme", json={
            "pack_id": "does-not-exist", "csrf_token": tok})
        assert r.status_code == 400
    finally:
        with app.app_context():
            _cleanup(uids=(sid,))


# ---------------------------------------------------------------------------
# 后台页面
# ---------------------------------------------------------------------------

def test_theme_center_page_requires_super(app, client):
    # 未登录 → 403（super_required 不暴露页面存在）
    assert client.get("/admin/theme-center").status_code == 403

    with app.app_context():
        admin = _mkuser(role=ROLE_ADMIN)
        superu = _mkuser(role=ROLE_SUPER)
        aid, sid = admin.id, superu.id
    try:
        tok = _auth(client, aid)
        assert client.get("/admin/theme-center").status_code == 403

        _auth(client, sid)
        r = client.get("/admin/theme-center")
        assert r.status_code == 200
        # 渲染了标题与「应用此主题」按钮（预设网格由 JS 在模板内已生成 data-pack）
        assert "主题中心".encode("utf-8") in r.data
        assert "应用此主题".encode("utf-8") in r.data
        # 至少第一个预设包 id 出现在 data-pack 上
        assert b'data-pack="classic-blue"' in r.data
    finally:
        with app.app_context():
            _cleanup(uids=(aid, sid))
