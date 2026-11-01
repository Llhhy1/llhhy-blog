# -*- coding: utf-8 -*-
"""档 1「访客自选主题」的契约测试（v5.4.x）。

这一档把「主题」从只有站主能改，变成访客也能在自己设备上挑一套。风险点全在
**边界**上，所以本文件钉的是边界而不是好看：

1. 默认必须**关** —— 未经真机验证的能力不默认开；关着时前台连清单请求都不该发；
2. 开关只有超管能动（普通管理员/匿名都不行）；
3. 值只能是真正的 true/false —— `"yes"`、`1` 这种拼错必须 400，
   否则「界面显示已开放、库里其实没写」这类静默失败又会回来；
4. 纯开关请求**不许顺手改写**当前主题（pack_id/accent/theme_tokens 原样不动）；
5. `/api/site` 与 `/api/theme` 两处读值必须同源（都是 themes.visitor_theme_allowed），
   两套口径的话前后台会出现「一边显示选择器一边不显示」。
"""
import json
import pathlib
import re
import uuid

import pytest
from models import db, Setting, User, AuditLog, ROLE_SUPER, ROLE_ADMIN

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEYS = ("allow_visitor_theme", "theme_pack", "accent_color", "theme_tokens")


def _set_kv(key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    elif value is not None:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _get_kv(key):
    row = Setting.query.filter_by(key=key).first()
    return row.value if row else None


@pytest.fixture
def restore(app):
    with app.app_context():
        before = {k: _get_kv(k) for k in KEYS}
    yield
    with app.app_context():
        for k, v in before.items():
            row = Setting.query.filter_by(key=k).first()
            if row:
                if v is None:
                    db.session.delete(row)
                else:
                    row.value = v
        db.session.commit()


def _mkuser(app, role):
    """建一个测试用户（用完由 _drop_user 清掉）。"""
    name = "vtheme-" + uuid.uuid4().hex[:8]
    with app.app_context():
        u = User(username=name, email=name + "@test.local", role=role)
        u.set_password("test-pass")
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, uid=None):
    """写会话并取一张与会话绑定的 CSRF token；uid=None 即匿名。"""
    if uid is not None:
        with client.session_transaction() as s:
            s["user_id"] = uid
            s["session_version"] = 0
    return client.get("/api/csrf").get_json()["csrf_token"]


def _drop_user(app, uid):
    with app.app_context():
        AuditLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
        u = db.session.get(User, uid)
        if u:
            db.session.delete(u)
        db.session.commit()


def _post_theme(client, tok, payload):
    return client.post("/api/theme", json=dict(payload, csrf_token=tok))


# ---------- 1. 默认关 + 两处读值同源 ----------

def test_default_off_and_exposed_in_both_apis(app, client, restore):
    site = client.get("/api/site").get_json()
    theme = client.get("/api/theme").get_json()
    assert site["allow_visitor_theme"] is False, "档 1 默认必须是关"
    assert theme["allow_visitor_theme"] is False
    # 清单要够前端渲染：每套都要带亮/暗两套 token（暗色由后端 derive_dark 统一推导）
    assert len(theme["presets"]) >= 10
    one = theme["presets"][0]
    assert {"id", "name", "light", "dark"} <= set(one)


def test_site_and_theme_agree_after_enable(app, client, restore):
    with app.app_context():
        _set_kv("allow_visitor_theme", "true")
    assert client.get("/api/site").get_json()["allow_visitor_theme"] is True
    assert client.get("/api/theme").get_json()["allow_visitor_theme"] is True


@pytest.mark.parametrize("raw", ["1", "yes", "on", "", 1, 0, [], {}])
def test_only_real_booleans_are_accepted(app, client, restore, raw):
    """只认真正的 bool 与 "true"/"false" 字符串（大小写不敏感）。

    `null` 不在列表里：它表示「这次没带这个字段」（与 wallpaper/custom 同一约定），
    而不是一个非法值。
    """
    uid = _mkuser(app, ROLE_SUPER)
    tok = _login(client, uid)
    try:
        r = _post_theme(client, tok, {"visitor_theme": raw})
        assert r.status_code == 400, "%r 不该被当成开关" % (raw,)
    finally:
        _drop_user(app, uid)


@pytest.mark.parametrize("raw", [True, False, "true", "TRUE", "false"])
def test_boolean_forms_persist_as_lowercase_words(app, client, restore, raw):
    """落库形态统一 small true/false —— setting_bool 与后台表单都按这个口径读。"""
    uid = _mkuser(app, ROLE_SUPER)
    tok = _login(client, uid)
    try:
        r = _post_theme(client, tok, {"visitor_theme": raw})
        assert r.status_code == 200
        want = str(raw).lower()
        assert r.get_json()["allow_visitor_theme"] == (want == "true")
        with app.app_context():
            assert _get_kv("allow_visitor_theme") == want
    finally:
        _drop_user(app, uid)


def test_dirty_db_value_reads_as_off(app, client, restore):
    """库里躺着垃圾值时读侧要回落「关」，不能让前台因为一个坏字符串渲染出选择器。"""
    with app.app_context():
        _set_kv("allow_visitor_theme", "maybe")
    assert client.get("/api/theme").get_json()["allow_visitor_theme"] is False


# ---------- 2. 权限 ----------

@pytest.mark.parametrize("role", [ROLE_ADMIN, None])
def test_only_super_can_toggle(app, client, restore, role):
    uid = _mkuser(app, role) if role else None
    tok = _login(client, uid)
    try:
        with app.app_context():
            before = _get_kv("allow_visitor_theme")
        r = _post_theme(client, tok, {"visitor_theme": True})
        assert r.status_code == 403
        with app.app_context():
            assert _get_kv("allow_visitor_theme") == before
    finally:
        if uid:
            _drop_user(app, uid)


# ---------- 3. 纯开关请求不动主题 ----------

def test_toggle_alone_keeps_current_theme(app, client, restore):
    with app.app_context():
        _set_kv("theme_pack", "aurora-green")
        _set_kv("accent_color", "#0d7f5d")
        _set_kv("theme_tokens", json.dumps(
            {"light": {"accent": "#0d7f5d"}, "dark": {"accent": "#0d7f5d"}}))
        before = {k: _get_kv(k) for k in ("theme_pack", "accent_color", "theme_tokens")}
    uid = _mkuser(app, ROLE_SUPER)
    tok = _login(client, uid)
    try:
        r = _post_theme(client, tok, {"visitor_theme": True})
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.get_json()["allow_visitor_theme"] is True
        with app.app_context():
            assert {k: _get_kv(k) for k in before} == before, "开关请求顺手改了主题"
    finally:
        _drop_user(app, uid)


def test_toggle_is_audited(app, client, restore):
    uid = _mkuser(app, ROLE_SUPER)
    tok = _login(client, uid)
    try:
        _post_theme(client, tok, {"visitor_theme": True})
        with app.app_context():
            row = (AuditLog.query.filter_by(user_id=uid)
                   .order_by(AuditLog.id.desc()).first())
        assert row and "访客自选主题" in (row.target or ""), \
            "开放访客换肤是对外可见的行为变更，必须能追溯到谁开的"
    finally:
        _drop_user(app, uid)


# ---------- 4. 后台开关 UI ----------

def test_admin_page_reflects_toggle_state(app, client, restore):
    """主题中心的开关必须显示**服务端真实值**，否则站主会以为已经开放了。"""
    uid = _mkuser(app, ROLE_SUPER)
    tok = _login(client, uid)
    try:
        off = client.get("/admin/theme-center").get_data(as_text=True)
        assert re.search(r'id="tvEnabled"\s*>', off), "默认状态没渲染成未勾选"
        assert _post_theme(client, tok, {"visitor_theme": True}).status_code == 200
        on = client.get("/admin/theme-center").get_data(as_text=True)
        assert re.search(r'id="tvEnabled"\s+checked>', on), "开放后后台仍显示关"
    finally:
        _drop_user(app, uid)


# ---------- 5. 前端契约（源码级，与既有 design 守卫同一风格）----------

def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_picker_is_gated_and_state_is_local_only():
    app_vue = _read("vue-frontend/src/App.vue")
    assert 'state.site.allow_visitor_theme' in app_vue, "选择器没受总开关控制"
    picker = _read("vue-frontend/src/components/ThemePicker.vue")
    assert "var(--text-soft" not in picker
    store = _read("vue-frontend/src/store.js")
    # 访客的选择只进 localStorage：写成 cookie/会话就变成服务端状态，
    # 同浏览器多人共用时会互相顶掉，还要为它新增一条 CSRF 面。
    assert "localStorage.setItem(VISITOR_THEME_KEY" in store
    assert "document.cookie" not in store


def test_visitor_pack_falls_back_when_switch_off():
    """开关被站主关掉后，访客残留的 localStorage 选择必须立即失效（而不是继续换肤）。"""
    store = _read("vue-frontend/src/store.js")
    assert "state.site.allow_visitor_theme" in store, "换肤前没判总开关"
    assert "state.themePacks.find" in store, "没在清单里核对 pack id"
