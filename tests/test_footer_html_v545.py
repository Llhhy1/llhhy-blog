# -*- coding: utf-8 -*-
"""v5.4.5 两件事的回归守卫：「自定义页脚代码」上线 +「访客自选主题」下架。

## A. 自定义页脚代码（`footer_html`）

这个字段的**产品定义就是「原样输出」**：站主要往页脚塞统计代码、自定义链接、
版权行。任何清洗（转义 `<`、剥掉 `<script>`）都会让头号用途失效 —— 所以这里
测的**不是**「有没有防住 HTML」，而是这三条边界有没有守住：

1. **谁能写**：只有超级管理员。`/admin/settings` 是 `@super_required`，且
   `footer_html` **不在**任何 API 写端点的白名单里（移动端 `_SETTING_KEYS` 只读）。
   等于「在访客浏览器里跑任意 JS」的权力只有一份，且锁在超管会话里。
2. **能写多大**：它进的是**每个前台页面**的页脚，必须有上限（`FOOTER_HTML_MAX`）。
3. **有没有留痕**：改了要有一条审计日志；没改不该刷日志。

前端侧还有一条容易踩空的：**由 `innerHTML` 插进去的 `<script>` 不会执行**
（HTML 规范如此，不是 bug）。所以 `store.js` 必须在插入后把 script 节点换成
新建的元素，否则「贴了统计代码却不生效」会变成只能靠人肉排查的问题。
本文件用源码断言钉住这条实现细节 —— 它没有别的可观测出口。

## B. 访客自选主题下架

站主判断「访客能自己换主题」是多余功能，v5.4.5 整体拆掉（开关、接口字段、
选择器组件、localStorage 键、i18n 键）。留一组**缺席断言**是因为这个项目由 AI
协助维护：只要代码里还有 `allow_visitor_theme` 的残影，下一次改动就可能把它
接回去。断言扫的是代码目录，不含历史文档（文档要留下「曾经做过又下架」的记录）。
"""
import contextlib
import os
import secrets

import pytest

from models import AuditLog, ROLE_ADMIN, ROLE_SUPER, Setting, User, db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "Passw0rd!23"

SAMPLE = '<script>console.log("footer-ok")</script><p>本站由我维护 · <a href="/about">关于</a></p>'


def _r():
    return secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


@pytest.fixture(autouse=True)
def _no_cert_recheck(monkeypatch):
    """保存 site_url 会触发证书复检 —— 它会真的连 443，测试绝不能出网。"""
    from admin import settings as admin_settings
    monkeypatch.setattr(admin_settings, "_trigger_cert_recheck", lambda: None)


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password},
                       headers={"X-CSRF-Token": _csrf(client)})


def _mkuser(app, role):
    uname = "fh_%s_%s" % ("su" if role == ROLE_SUPER else "ad", _r())
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=role, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    return uname


@pytest.fixture()
def super_client(client, app):
    assert _login(client, _mkuser(app, ROLE_SUPER)).status_code == 200
    return client


@pytest.fixture()
def admin_client(client, app):
    """普通管理员：能进后台内容页，但**进不了**站点设置。"""
    assert _login(client, _mkuser(app, ROLE_ADMIN)).status_code == 200
    return client


def _post_settings(client, **extra):
    payload = {"site_title": "T", "site_name": "N", "site_url": "https://www.example.com"}
    payload.update(extra)
    return client.post("/admin/settings", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


def _get_setting(app, key):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        return row.value if row else None


# ---------- A1. 读取侧：前台拿得到，且是原样 ----------

def test_api_site_exposes_footer_html(super_client, app):
    """/api/site 是 SPA 唯一的站点信息来源。"""
    _post_settings(super_client, footer_html=SAMPLE)
    assert super_client.get("/api/site").get_json()["footer_html"] == SAMPLE


def test_api_site_defaults_footer_html_to_empty_string(super_client):
    """键必须**恒在**：前端直接读 `state.site.footer_html`，缺键会变 undefined，
    `injectFooterCode(undefined)` 与「站主主动清空」就区分不开了。"""
    assert "footer_html" in super_client.get("/api/site").get_json()


def test_ssr_footer_outputs_footer_html_raw(super_client, app):
    """SSR 页（登录/注册）也带页脚，必须原样输出而不是转义成 `&lt;script&gt;`。

    ⚠️ 用**匿名** client 取页面：`super_client` 已登录，`/login` 会 302 回首页，
    根本渲染不出模板（第一版就在这里假红）。
    """
    _post_settings(super_client, footer_html=SAMPLE)
    html = app.test_client().get("/login").get_data(as_text=True)
    assert "<footer" in html, "拿到的不是模板页（断言会假绿）"
    assert SAMPLE in html, "SSR 页脚把页脚代码转义了 —— 统计代码会变成一屏可见的文本"


def test_cleared_footer_html_renders_nothing(super_client, app):
    _post_settings(super_client, footer_html=SAMPLE)
    _post_settings(super_client, footer_html="")
    html = app.test_client().get("/login").get_data(as_text=True)
    assert "<footer" in html, "拿到的不是模板页（断言会假绿）"
    assert 'console.log("footer-ok")' not in html
    assert super_client.get("/api/site").get_json()["footer_html"] == ""


# ---------- A2. 写入侧：入口、上限、权限、留痕 ----------

def test_settings_page_has_the_field(super_client):
    """没有输入框 = 功能不存在（本站踩过一次同类坑：SEO 页把人指向一个不存在的字段）。"""
    html = super_client.get("/admin/settings").get_data(as_text=True)
    assert 'name="footer_html"' in html
    assert 'id="footer_html"' in html and 'for="footer_html"' in html
    assert "script" in html, "提示里要说明脚本会执行，别让人以为只能填纯文本"


def test_saved_verbatim(super_client, app):
    """原样存：不转义、不折叠空白（站主贴的代码缩进本来就有意义）。"""
    _post_settings(super_client, footer_html="  <p>a</p>\n\n<b>b</b>  ")
    assert _get_setting(app, "footer_html") == "  <p>a</p>\n\n<b>b</b>  "


def test_overlong_is_rejected_but_other_fields_still_save(super_client, app):
    from admin.settings import FOOTER_HTML_MAX
    _post_settings(super_client, footer_html="<p>before</p>")
    junk = "x" * (FOOTER_HTML_MAX + 1)
    r = _post_settings(super_client, footer_html=junk, site_name="改名成功")
    assert _get_setting(app, "footer_html") == "<p>before</p>", "超限的值绝不能写库"
    assert _get_setting(app, "site_name") == "改名成功", "一个字段填错不该丢掉整张表单"
    assert "页脚代码" in r.get_data(as_text=True), "要告诉用户为什么没保存，不能静默丢弃"


def test_exactly_at_limit_is_saved(super_client, app):
    """边界：上限本身合法（上限只在「明显是误粘贴」时才起作用）。"""
    from admin.settings import FOOTER_HTML_MAX
    body = "<p>" + "y" * (FOOTER_HTML_MAX - 7) + "</p>"   # <p> + </p> 共 7 字符
    assert len(body) == FOOTER_HTML_MAX
    _post_settings(super_client, footer_html=body)
    assert _get_setting(app, "footer_html") == body


def test_plain_admin_cannot_write_it(admin_client, app):
    """这条是整个设计的承重墙：字段内容会被原样注入**所有访客**的页面并执行脚本。
    普通管理员（role=admin）能进后台管内容，但必须连这个字段都改不了。"""
    marker = "<p>super-only-" + _r() + "</p>"
    r = admin_client.post("/admin/settings",
                          data={"footer_html": marker, "site_name": "不该被改"},
                          headers={"X-CSRF-Token": _csrf(admin_client)})
    assert r.status_code == 403, "站点设置必须是超管专属 —— 页脚代码等于任意 JS"
    assert _get_setting(app, "footer_html") != marker


def test_footer_html_not_writable_through_api(admin_client):
    """设置类 API 只读（移动端 `_SETTING_KEYS` 是展示白名单）。
    这里断言它**没有**变成 JSON 写入口 —— 否则 CSRF + 会话 SameSite 的保护面就变小了。"""
    r = admin_client.post("/api/site", json={"footer_html": "<script>1</script>"},
                          headers={"X-CSRF-Token": _csrf(admin_client)})
    assert r.status_code in (401, 403, 404, 405), "不该存在能写 footer_html 的公开 API 端点"


def test_changing_it_writes_audit_log(super_client, app):
    _post_settings(super_client, footer_html="<p>audit-" + _r() + "</p>")
    with app.app_context():
        rows = AuditLog.query.filter_by(target="自定义页脚代码").all()
    assert rows, "页脚代码会执行脚本，改动必须留痕"


def test_unchanged_value_does_not_repeat_audit(super_client, app):
    val = "<p>same-" + _r() + "</p>"
    _post_settings(super_client, footer_html=val)
    with app.app_context():
        before = AuditLog.query.filter_by(target="自定义页脚代码").count()
    _post_settings(super_client, footer_html=val)
    with app.app_context():
        assert AuditLog.query.filter_by(target="自定义页脚代码").count() == before, \
            "每次保存都刷一条 = 日志里查不到真正的那次改动"


def test_footer_html_is_in_rollback_snapshot(super_client, app):
    """写坏了要能回滚 —— 配置快照没记它，等于把唯一的安全网留空。"""
    _post_settings(super_client, footer_html="<p>snap-" + _r() + "</p>")
    with app.app_context():
        import config_rollback as cr
        snaps = cr.list_snapshots()
        assert snaps, "保存设置时应拍快照"
        import json
        payload = json.loads(snaps[0].payload or "{}")
    assert "footer_html" in payload


# ---------- A3. 前端契约：脚本真的会跑 ----------

def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_spa_has_the_footer_code_mount():
    assert 'id="site-footer-code"' in _read("vue-frontend/src/App.vue")


def test_spa_rebuilds_script_nodes():
    """innerHTML 里的 `<script>` **不会执行**，必须重建元素。
    这条一旦回归，症状是「统计代码贴上去没数据」，肉眼完全查不出来。"""
    store = _read("vue-frontend/src/store.js")
    assert 'createElement("script")' in store
    assert "replaceWith(" in store
    assert "injectFooterCode(s.footer_html)" in store, "站点设置加载后没注入页脚代码"


def test_spa_footer_code_injection_is_idempotent():
    """SPA 换路由不该把统计脚本再跑一遍（PV 会翻倍）。"""
    store = _read("vue-frontend/src/store.js")
    assert 'data-src' in store


# ---------- B. 档 1 下架：缺席断言 ----------

_BANNED = ("allow_visitor_theme", "visitor_theme", "visitorTheme", "visitorPack",
           "themePacks", "ThemePicker", "theme_picker", "theme_follow_site",
           "ALLOW_VISITOR_KEY")
_SCAN_DIRS = ("myblog", os.path.join("vue-frontend", "src"), "tests", "tools")
_SCAN_SUFFIX = (".py", ".js", ".vue", ".html", ".css")


def test_visitor_theme_switch_is_gone_from_code():
    here = os.path.basename(__file__)   # 本文件的断言里必然出现这些词，跳过自己
    hits = []
    for d in _SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = [x for x in dirnames if x not in ("node_modules", "__pycache__", "_vite_build30")]
            for fn in filenames:
                if not fn.endswith(_SCAN_SUFFIX) or fn == here:
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding="utf-8") as f:
                        text = f.read()
                except (UnicodeDecodeError, OSError):
                    continue
                for token in _BANNED:
                    if token in text:
                        hits.append("%s: %s" % (os.path.relpath(p, ROOT), token))
    assert not hits, "访客自选主题已下架，代码里不该再有残影：\n" + "\n".join(hits)


def test_api_theme_get_no_longer_reports_the_switch(super_client):
    d = super_client.get("/api/theme").get_json()
    assert "allow_visitor_theme" not in d
    assert {"presets", "current", "wallpaper"} <= set(d)


def test_api_theme_post_ignores_the_old_switch(super_client, app):
    """老客户端（或缓存里的旧前端）仍可能提交 `visitor_theme` —— 必须**静默忽略**
    而不是重新写回那个 Setting 键。"""
    tok = _csrf(super_client)
    super_client.post("/api/theme", json={"visitor_theme": True}, headers={"X-CSRF-Token": tok})
    assert _get_setting(app, "allow_visitor_theme") is None
