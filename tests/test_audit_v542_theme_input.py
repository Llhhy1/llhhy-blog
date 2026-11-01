# -*- coding: utf-8 -*-
"""v5.4.x 批次 D：自定义主题/输入校验加固的回归测试。

覆盖 v5.3.3 审计里的 4 个 P2（它们是「开放访客自定义主题」的前置）：
1. `custom_css` 的 `</style` 逃逸 —— 旧转义只做**小写**，`</StYlE>` 可绕过；
2. `accent_color` 原样进 SSR `<style>` —— 可注入任意 CSS 规则；
3. 自定义主题 token 无白名单 —— 任意键/值都会被 `setProperty` 写进 `:root`，
   `url(...)` 之类的值等于让每个访客的浏览器替站主外联；
4. `post.lang` 未校验 —— 脏值会进 `<html lang='…'>` 与 XML `hreflang="…"`。

**为什么多数用例走「先写脏值进库、再看渲染」**：写入侧校验管不到备份还原、
直接改库、老版本存量。渲染/输出侧的清洗是第二道防线，必须单独钉住。
"""
import json
import re
import time
import uuid

import pytest
from models import db, Setting
from utils import css_context_escape, normalize_lang
from themes import (THEME_PRESETS, _BASE_LIGHT, _FUNC_COLOR_RE, _token_value_ok,
                    current_theme, normalize_custom_theme, sanitize_theme_tokens,
                    validate_accent)

DIRTY_CSS = "a{color:red}</StYlE><script>evil()</script>"
DIRTY_ACCENT = "red;} html{display:none} :root{--accent:blue"


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
def restore_settings(app):
    """用例结束后把碰到的 Setting 键恢复原值，别污染共享测试库。"""
    keys = ("custom_css", "accent_color", "theme_pack", "theme_tokens")
    with app.app_context():
        before = {k: _get_kv(k) for k in keys}
    yield
    with app.app_context():
        for k, v in before.items():
            _set_kv(k, v if v is not None else "")


# ---------- 1. CSS 闭合序列转义 ----------

def test_css_escape_is_case_insensitive():
    out = css_context_escape(DIRTY_CSS)
    assert "</StYlE>" not in out, "大小写混合的 </style 未被转义，可逃逸出样式上下文"
    assert "<\\/style" in out
    assert "<script>" in out  # 留在 CSS 文本里无害，关键是它闭合不了 <style>


def test_css_escape_handles_comment_and_spacing():
    assert "</" not in css_context_escape("< /style x").replace("<\\/style", "")
    assert "<\\!--" in css_context_escape("body{color:red}<!--p-->")


def test_ssr_neutralizes_dirty_custom_css(app, client, restore_settings):
    with app.app_context():
        _set_kv("custom_css", DIRTY_CSS)
    body = client.get("/login").get_data(as_text=True)
    assert re.search(r"(?i)</\s*style\s*>", body)  # 页面自身的 <style> 收尾仍在
    assert "</StYlE>" not in body
    assert "<\\/style" in body
    # 真正要钉住的是「逃逸」：`</style>` 后紧跟注入的 script = 样式上下文已被关掉。
    # `<style>` 是 raw text 元素，留在其中的 `<script>…</script>` 只是无效 CSS 文本。
    assert not re.search(r"(?i)</\s*style\s*>\s*<script>evil", body)


# ---------- 2. accent_color ----------

@pytest.mark.parametrize("bad", ["red;} html{display:none}", "#12", "#gggggg", "url(x)", ""])
def test_validate_accent(bad):
    val, err = validate_accent(bad)
    if bad == "":
        assert err is None and val == ""      # 留空 = 清除，前台回落默认色
    else:
        assert val is None and err, "非法主题色被放行：%r" % bad


def test_validate_accent_accepts_hex_forms():
    for good in ("#abc", "#abcdef", "#ABCDEF"):
        val, err = validate_accent(good)
        assert err is None and val == good


def test_ssr_replaces_invalid_accent(app, client, restore_settings):
    with app.app_context():
        _set_kv("accent_color", DIRTY_ACCENT)
    body = client.get("/login").get_data(as_text=True)
    assert "--accent: #196ddd" in body, "脏 accent 没回落到默认色"
    assert DIRTY_ACCENT not in body


# ---------- 3. 自定义主题 token 白名单 ----------

def test_token_whitelist_rejects_unknown_key():
    clean, errors = sanitize_theme_tokens({"accent": "#123456", "evil": "x"})
    assert clean == {"accent": "#123456"}
    assert any("evil" in e for e in errors)


@pytest.mark.parametrize("key,value", [
    ("bg", "url(https://evil.example/beacon)"),
    ("accent", "red"),
    ("radius_md", "12px; body{display:none}"),
    ("line_height_base", "1.7px"),
    ("font_sans", "x{position:absolute}"),
    ("shadow_sm", "0 0 0 url(http://evil)"),
])
def test_token_values_are_typed(key, value):
    clean, errors = sanitize_theme_tokens({key: value})
    assert key not in clean and errors, "%s=%r 应被拒绝" % (key, value)


@pytest.mark.parametrize("good", [
    "rgba(25, 109, 221, .10)", "rgb(25,109,221)", "hwb(180 20% 30%)", "hsla(0 0% 0% / .5)",
])
def test_function_colors_still_pass(good):
    """改正则不能把合法写法一起改掉：空格、`/` 分隔、百分号都要收。"""
    assert _token_value_ok("color", good), good


def test_color_regex_has_no_overlapping_quantifiers():
    """CodeQL 在 v5.4.x 这里报过**多项式回溯**（ReDoS）：`\\(\\s*[\\s…]*\\)` 里相邻两个
    量词都能吃掉同一批空白字符。空白类只能出现一次，且输入规模要先被钉住。"""
    assert r"(\s*" not in _FUNC_COLOR_RE.pattern, "函数色正则不要再放 `\\s*`：字符类已含空白"
    start = time.perf_counter()
    for bad in ("hwb(" + "\t" * 200 + "x", "rgb(" + " " * 200 + "x"):
        assert _token_value_ok("color", bad) is False
    assert time.perf_counter() - start < 0.5, "校验函数被回溯拖住了"


def test_overlong_token_value_is_rejected_before_matching():
    assert _token_value_ok("color", "#fff" + "a" * 400) is False
    assert _token_value_ok("family", "A" * 5000) is False


def test_normalize_custom_theme_completes_base_tokens():
    light, dark, errors = normalize_custom_theme({"light": {"accent": "#ff6600"}})
    assert not errors
    missing = set(_BASE_LIGHT) - set(light)
    assert not missing, "自定义主题缺键：%r（前台会拿到半套 token）" % missing
    assert light["accent"] == "#ff6600"
    # 主色变了，配套的 hover/soft/info 必须重算，不能留着旧蓝色
    assert light["info"] == "#ff6600"
    assert light["accent_hover"] != _BASE_LIGHT["accent_hover"]
    assert dark["accent"].startswith("#")


def test_normalize_custom_theme_rejects_payloads():
    _, _, errors = normalize_custom_theme({
        "light": {"accent": "#ff6600", "surface": "url(http://evil/x)"}})
    assert errors
    _, _, errors2 = normalize_custom_theme({"light": {"accent": "#ff6600", "xss": "</style>"}})
    assert errors2


def test_current_theme_sanitizes_dirty_db_tokens(app, restore_settings):
    dirty = {"light": {"accent": "#123456", "bg": "url(https://evil/beacon)"},
             "dark": {"bg": "#101010\"><script>"}}
    with app.app_context():
        _set_kv("theme_pack", "custom")
        _set_kv("theme_tokens", json.dumps(dirty))
        t = current_theme()
    assert t["light"]["accent"] == "#123456"
    assert t["light"]["bg"] == _BASE_LIGHT["bg"], "脏值没被剔除、也没回落基准"
    assert "url(" not in json.dumps(t["light"]) + json.dumps(t["dark"])


def _mk_super(app):
    from models import User, ROLE_SUPER
    name = "themeval-" + uuid.uuid4().hex[:8]
    with app.app_context():
        u = User(username=name, email=name + "@test.local", role=ROLE_SUPER)
        u.set_password("test-pass")
        u.must_change_password = False      # 否则会被闸门赶去 /admin/setup
        db.session.add(u)
        db.session.commit()
        return u.id


def _login_super(client, uid):
    """写会话（user_id + session_version），再取一张与会话绑定的 CSRF token。"""
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["session_version"] = 0            # 新建用户的版本就是默认 0
    return client.get("/api/csrf").get_json()["csrf_token"]


def _send_theme(client, payload, tok):
    return client.post("/api/theme", json=dict(payload, csrf_token=tok))


def test_theme_api_url_value_is_400(app, client, restore_settings):
    uid = _mk_super(app)
    tok = _login_super(client, uid)
    with app.app_context():
        before = _get_kv("theme_tokens")
    r = _send_theme(client, {"custom": {"light": {"accent": "#ff6600",
                                                  "bg": "url(https://evil/beacon)"}}}, tok)
    assert r.status_code == 400
    body = r.get_json()
    assert body.get("details"), "400 必须回文案，否则导入者不知道哪一条错了"
    with app.app_context():
        assert _get_kv("theme_tokens") == before, "非法主题被落库了"


def test_theme_api_valid_custom_is_persisted_complete(app, client, restore_settings):
    uid = _mk_super(app)
    tok = _login_super(client, uid)
    r = _send_theme(client, {"custom": {"light": {"accent": "#ff6600"}}}, tok)
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    with app.app_context():
        saved = json.loads(_get_kv("theme_tokens"))
    assert set(_BASE_LIGHT) <= set(saved["light"])
    assert saved["light"]["accent"] == "#ff6600"
    assert "url(" not in json.dumps(saved)


# ---------- 4. post.lang ----------

@pytest.mark.parametrize("raw,want", [
    ("zh", "zh"), ("zh-CN", "zh-CN"), ("en", "en"),
    ("x'><script>alert(1)</script>", "zh"),
    ("", "zh"), ("   ", "zh"), ("zh_cn", "zh"),
])
def test_normalize_lang(raw, want):
    assert normalize_lang(raw) == want


def test_create_post_core_whitelists_lang(app):
    from admin._helpers import create_post_core
    payload = "x'><script>alert(1)</script>"
    with app.app_context():
        p = create_post_core(title="lang-" + uuid.uuid4().hex[:6], content="x",
                             published=True, lang=payload)
        assert p.lang == "zh"
        pid = p.id
    with app.app_context():
        from models import Post
        db.session.delete(db.session.get(Post, pid))
        db.session.commit()


def test_feed_escapes_legacy_dirty_lang(app, client):
    """存量脏 lang（直接改库）不得原样进 XML —— 那会破坏 feed 结构。"""
    from admin._helpers import create_post_core
    from models import Post
    group = "langleak-" + uuid.uuid4().hex[:6]
    with app.app_context():
        p = create_post_core(title="lang ok " + group, content="x", published=True,
                             lang="en", translation_group=group)
        bad = db.session.get(Post, p.id)
        bad.lang = "en' onerror=\"alert(1)\""      # 模拟存量脏值
        db.session.commit()
        ids = [p.id]
    try:
        body = client.get("/feed.xml").get_data(as_text=True)
        assert "onerror=\"alert" not in body, "脏 lang 原样进 feed，可注入 XML 属性"
        assert "onerror=&#34;alert" in body or "onerror=&#39;alert" in body or "onerror=" not in body
    finally:
        with app.app_context():
            for i in ids:
                q = db.session.get(Post, i)
                if q:
                    db.session.delete(q)
            db.session.commit()


# ---------- 5. 预设包仍然可用（校验不能把 14 套预设挡掉）----------

def test_all_presets_pass_own_whitelist():
    for p in THEME_PRESETS:
        clean, errors = sanitize_theme_tokens(p["light"])
        assert not errors, "%s 的预设 token 过不了自家白名单：%r" % (p["id"], errors)
        clean_d, errors_d = sanitize_theme_tokens(p["dark"])
        assert not errors_d, "%s 暗色 token 过不了白名单：%r" % (p["id"], errors_d)
