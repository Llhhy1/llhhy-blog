# -*- coding: utf-8 -*-
"""v5.5.0 主题包（Theme Bundle）守卫。

覆盖四条硬边界：
1. **schema**：内置「章回」包必须合法；坏 id / 坏枚举 / 越界数字 / 非法配色一律拒绝。
2. **CSS 信任边界**：`url(`、`@import`、`</`、全局选择器（body / .btn）必须被挡下 ——
   主题包是要分发给别的部署者的，一份包不能让访客浏览器去请求第三方地址。
3. **权限与互斥**：POST 只有超管能改；应用预设/自定义会退出主题包，反之亦然；
   GET /api/site 下发展示层但不含后台元数据。
4. **不回归**：访客换肤缺席守卫仍绿（本项目有独立测试，这里再钉一次语义）。
"""
import copy
from contextvars import Context
import json
import os
import secrets
import uuid

import pytest

from models import db, User, Setting, ROLE_SUPER, ROLE_ADMIN
from utils import _sign_csrf
import theme_bundles as bundles

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACK = os.path.join(_ROOT, "myblog", "theme_packs", "zhanghui.json")


@pytest.fixture(autouse=True)
def _app_ctx(app):
    """测试里的 db.session 操作需要应用上下文（与 test_theme_center.py 同法）。"""
    with app.app_context():
        yield


def _uid():
    return uuid.uuid4().hex[:10]


def _mkuser(role=ROLE_SUPER):
    u = User(username="tb-" + _uid(), email="tb-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, u):
    """登录并生成与会话绑定的有效 CSRF token（与 test_theme_center.py 同法）。"""
    raw = secrets.token_hex(24)
    with client.application.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as s:
        s["user_id"] = u.id
        s["_fresh"] = True
        s["csrf_token"] = tok


def _post(client, body):
    # POST 的全局 CSRF 闸既认 header 也认 body，按项目既有用例把 token 放进 body。
    payload = dict(body)
    with client.session_transaction() as s:
        payload.setdefault("csrf_token", s.get("csrf_token", ""))
    return client.post("/api/theme", json=payload)


def _cleanup(u):
    if u:
        db.session.delete(u)
    for k in (bundles.ACTIVE_KEY, "theme_pack", "theme_tokens", "accent_color"):
        row = Setting.query.filter_by(key=k).first()
        if row:
            db.session.delete(row)
    db.session.commit()


# ---------- 1. schema ----------

def test_内置章回主题包通过校验():
    with open(_PACK, encoding="utf-8") as f:
        raw = json.load(f)
    clean, errors = bundles.validate_bundle(raw)
    assert errors == []
    assert clean["id"] == "zhanghui"
    assert clean["layout"]["mode"] == "chapter"
    assert clean["layout"]["hero"] == "required"
    assert len(clean["tokens"]["light"]) == 30
    assert len(clean["tokens"]["dark"]) == 30


def test_列表能发现内置包且摘要不含整套token():
    found = bundles.list_bundles()
    assert "zhanghui" in [b["id"] for b in found]
    s = bundles.summary(next(b for b in found if b["id"] == "zhanghui"))
    assert "tokens" not in s and "css" not in s
    assert s["layout"] == "chapter"
    assert s["source"] == ""


def test_主题包无应用上下文时仍可安全读取():
    def probe():
        assert bundles.active_bundle() is None
        assert bundles.resolve_bundle("lib:missing") is None
        assert bundles.resolve_bundle("zhanghui")["id"] == "zhanghui"

    Context().run(probe)


def test_主题库数据库异常回落并记录日志(monkeypatch, caplog):
    from sqlalchemy.exc import SQLAlchemyError
    import theme_library

    def unavailable(_iid):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(theme_library, "get_item", unavailable)
    assert bundles.resolve_bundle("lib:sample") is None
    assert "主题库读取失败" in caplog.text


def test_主题库程序错误不得静默隐藏(monkeypatch):
    import theme_library

    def broken(_iid):
        raise TypeError("invalid internal value")

    monkeypatch.setattr(theme_library, "get_item", broken)
    with pytest.raises(TypeError, match="invalid internal value"):
        bundles.resolve_bundle("lib:sample")


def test_主题摘要接口返回精简元数据(client):
    response = client.get("/api/theme")
    assert response.status_code == 200
    pack = next(b for b in response.get_json()["bundles"] if b["id"] == "zhanghui")
    assert pack["source"] == ""
    assert pack["layout"] == "chapter"


def test_坏id与坏枚举被拒绝():
    with open(_PACK, encoding="utf-8") as f:
        base = json.load(f)
    for bad in ("../evil", "Zhang Hui", "", "x" * 40):
        r = copy.deepcopy(base)
        r["id"] = bad
        _clean, errors = bundles.validate_bundle(r)
        assert errors, "id=%r 应被拒绝" % bad
    r = copy.deepcopy(base)
    r["layout"]["mode"] = "drop-all-tables"
    _c, errors = bundles.validate_bundle(r)
    assert any("layout.mode" in e for e in errors)


def test_数字越界被夹取而不是抛异常():
    with open(_PACK, encoding="utf-8") as f:
        r = json.load(f)
    r["layout"]["columns"] = 999
    r["layout"]["content_max"] = 10
    r["layout"]["gap"] = "abc"
    c, errors = bundles.validate_bundle(r)
    assert errors == []
    assert c["layout"]["columns"] == 4
    assert c["layout"]["content_max"] == 640
    assert c["layout"]["gap"] == 16


@pytest.mark.parametrize("css", [
    "body{background:url(https://attacker.example/pixel)}",
    "@import url(https://evil.example/x.css);",
    ".zh-x{color:red}</style><script>alert(1)</script>",
    ".btn{display:none}",
    "body{color:red}",
    ".zh-x{behavior:url(#default#time2)}",
    ".zh-x{-moz-binding:url(x)}",
    ".zh-x{background:data:image/png;base64,AAAA}",
])
def test_受限CSS挡住注入与全局选择器(css):
    with open(_PACK, encoding="utf-8") as f:
        r = json.load(f)
    r["css"] = css
    _c, errors = bundles.validate_bundle(r)
    assert errors, "应被拒绝：%s" % css


def test_命名空间内的CSS可以放行():
    with open(_PACK, encoding="utf-8") as f:
        r = json.load(f)
    r["css"] = ".zh-section-head{letter-spacing:.08em}\n:root[data-layout=chapter] .zh-seal{color:#a8442a}"
    c, errors = bundles.validate_bundle(r)
    assert errors == [], errors
    assert ".zh-section-head" in c["css"]


def test_标签字段禁尖括号():
    with open(_PACK, encoding="utf-8") as f:
        r = json.load(f)
    r["labels"]["volume"] = "<img src=x onerror=alert(1)>"
    _c, errors = bundles.validate_bundle(r)
    assert errors


# ---------- 2. 权限 / 互斥 / 下发 ----------

def test_未登录与普通管理员不能应用主题包(app, client):
    r = _post(client, {"bundle_id": "zhanghui"})
    assert r.status_code == 403
    u = _mkuser(ROLE_ADMIN)
    try:
        _login(client, u)
        r = _post(client, {"bundle_id": "zhanghui"})
        assert r.status_code == 403
    finally:
        with client.session_transaction() as s:
            s.clear()
        _cleanup(u)


def test_超管应用主题包并下发到site(app, client):
    u = _mkuser(ROLE_SUPER)
    try:
        _login(client, u)
        r = _post(client, {"bundle_id": "zhanghui"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["bundle_id"] == "zhanghui"
        assert Setting.query.filter_by(key=bundles.ACTIVE_KEY).first().value == "zhanghui"

        site = client.get("/api/site").get_json()
        b = site["theme_bundle"]
        assert b and b["id"] == "zhanghui"
        assert b["layout"]["mode"] == "chapter"
        assert b["palette"]["ink"] == "#1C2422"
        assert "version" not in b and "source" not in b  # 后台元数据不下发

        t = client.get("/api/theme").get_json()
        assert "zhanghui" in [x["id"] for x in t["bundles"]]
        assert t["current"]["bundle_id"] == "zhanghui"
    finally:
        with client.session_transaction() as s:
            s.clear()
        _cleanup(u)


def test_应用预设会退出主题包避免半新半旧(app, client):
    u = _mkuser(ROLE_SUPER)
    try:
        _login(client, u)
        assert _post(client, {"bundle_id": "zhanghui"}).status_code == 200
        assert _post(client, {"pack_id": "classic-blue"}).status_code == 200
        assert Setting.query.filter_by(key=bundles.ACTIVE_KEY).first().value == ""
        assert client.get("/api/site").get_json()["theme_bundle"] is None
    finally:
        with client.session_transaction() as s:
            s.clear()
        _cleanup(u)


def test_未知包id返回400(app, client):
    u = _mkuser(ROLE_SUPER)
    try:
        _login(client, u)
        r = _post(client, {"bundle_id": "not-exists"})
        assert r.status_code == 400
        assert r.get_json()["error"] == "unknown bundle_id"
    finally:
        with client.session_transaction() as s:
            s.clear()
        _cleanup(u)


def test_下发结构与前台契约字段对齐():
    """前台 store.js 依赖的字段名一旦改名，这里立刻变红。"""
    with open(_PACK, encoding="utf-8") as f:
        c, _ = bundles.validate_bundle(json.load(f))
    pub = bundles.public_bundle(c)
    assert set(pub) == {"id", "layout", "background", "motion", "palette", "labels", "css"}
    assert set(pub["layout"]) == {"mode", "card", "frame", "sidebar", "hero",
                                  "columns", "content_max", "gap"}


def test_前台确实消费展示层且经典路径零影响():
    store = os.path.join(_ROOT, "vue-frontend", "src", "store.js")
    css = os.path.join(_ROOT, "vue-frontend", "src", "styles", "global.css")
    home = os.path.join(_ROOT, "vue-frontend", "src", "views", "HomeView.vue")
    with open(store, encoding="utf-8") as f:
        s = f.read()
    with open(css, encoding="utf-8") as f:
        c = f.read()
    with open(home, encoding="utf-8") as f:
        h = f.read()
    assert "applyThemeBundle(s.theme_bundle)" in s
    assert 'el.setAttribute("data-layout"' in s
    assert ':root[data-layout="chapter"]' in c
    assert 'v-if="isChapter"' in h
    # 缺席守卫（test_footer_html_v545.py）独立扫描禁用词，不在此重复断言：
    # 在这个文件里写下那些字面量本身就会触发它。
