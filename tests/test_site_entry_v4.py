"""前台「自定义外部入口」（v4.0.0）守卫测试。

**这个测试存在的理由**：入口地址由后台填写、前台用 ``:href`` **直接绑定**。
这意味着它是一个「存储型 XSS 的候选入口」—— 只要哪天有人（或某次数据迁移）
把 ``entry_url`` 写成 ``javascript:...``，页面一加载就在访客浏览器里执行，
而且**不报错**：导航栏看起来一切正常，链接也点得动。

所以判据不是「能不能存/能不能显示」，而是：
1. **非 http/https 的地址绝不能出现在前台拿到的 JSON 里**（后端出口过滤）；
2. 保存时也拒绝入库，且**不能因此丢掉整张表单的其它编辑**；
3. 入口能被关掉（开关真的生效），也能改名改图标（自定义是真的自定义）。
"""
import contextlib
import json
import secrets

import pytest

from models import db, User, Setting, ROLE_SUPER

PASSWORD = "Passw0rd!23"
APP_VUE = "vue-frontend/src/App.vue"


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


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password},
                       headers={"X-CSRF-Token": _csrf(client)})


@pytest.fixture()
def cert_recheck(monkeypatch):
    """拦掉「保存 site_url 后重跑证书检查」—— 它会真去连 443，测试绝不能出网。"""
    calls = []
    from admin import settings as admin_settings
    monkeypatch.setattr(admin_settings, "_trigger_cert_recheck", lambda: calls.append(True))
    return calls


@pytest.fixture()
def super_client(client, app, cert_recheck):
    app.config["SITE_URL"] = ""
    uname = "su_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    assert _login(client, uname).status_code == 200
    return client


def _set(app, key, value):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()


def _get(app, key):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        return row.value if row else None


def _entry(client):
    return (client.get("/api/site").get_json() or {}).get("entry") or {}


def _post_settings(client, **extra):
    payload = {"site_title": "T", "site_name": "N"}
    payload.update(extra)
    return client.post("/admin/settings", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


# ---------- 1. URL 白名单本身 ----------

@pytest.mark.parametrize("raw", [
    "https://box.llhhy.cn",
    "http://box.llhhy.cn",
    "https://box.llhhy.cn/",
    "https://box.llhhy.cn/#/lots",
    "https://example.com:8443/x?a=1",
])
def test_is_http_url_accepts(raw):
    from utils import is_http_url
    assert is_http_url(raw), f"{raw!r} 是正常外站地址，应放行"


@pytest.mark.parametrize("raw", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "//evil.example.com",          # 协议相对：会继承本站协议并指向外域
    "www.example.com",             # 没协议
    "https://",                    # 没域名
    "",
    "https://example.com/a b",     # 含空白
])
def test_is_http_url_rejects(raw):
    from utils import is_http_url
    assert not is_http_url(raw), f"{raw!r} 放进 href 会出事，必须拒绝"


# ---------- 2. 出口过滤：非法地址绝不能到达前台 ----------

def test_api_site_returns_entry_when_configured(client, app):
    _set(app, "entry_enabled", "true")
    _set(app, "entry_label", "百宝箱")
    _set(app, "entry_url", "https://box.llhhy.cn")
    _set(app, "entry_icon", "🧰")
    e = _entry(client)
    assert e["enabled"] is True
    assert e["url"] == "https://box.llhhy.cn"
    assert e["label"] == "百宝箱"
    assert e["icon"] == "🧰"


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "//evil.example.com",
    "file:///etc/passwd",
])
def test_api_site_never_emits_unsafe_href(client, app, bad):
    """**核心断言**：前台拿到的 url 必须为空 —— 不清洗就会变成存储型 XSS。"""
    _set(app, "entry_enabled", "true")
    _set(app, "entry_label", "百宝箱")
    _set(app, "entry_url", bad)
    e = _entry(client)
    assert e["enabled"] is False, "地址非法时必须整个禁用，而不是只清 label"
    assert e["url"] == "", f"非法地址 {bad!r} 绝不能出现在前台 JSON 里"
    assert e["label"] == ""


def test_entry_can_be_switched_off(client, app):
    _set(app, "entry_url", "https://box.llhhy.cn")
    _set(app, "entry_enabled", "false")
    assert _entry(client)["enabled"] is False
    _set(app, "entry_enabled", "true")
    assert _entry(client)["enabled"] is True


def test_entry_defaults_to_off_when_never_configured(client, app):
    """没配过 → 不显示。宁可入口消失，也不要显示一个空链接。"""
    _set(app, "entry_url", "")
    _set(app, "entry_enabled", "true")
    assert _entry(client)["enabled"] is False


# ---------- 3. 后台：输入框 / 保存 / 拒绝 ----------

def test_settings_page_has_all_entry_inputs(super_client):
    html = super_client.get("/admin/settings").get_data(as_text=True)
    for name in ("entry_enabled", "entry_label", "entry_url", "entry_icon"):
        assert 'name="%s"' % name in html, f"后台缺 {name} 输入框"
    # 文本类必须有 label（for 指向），否则读屏读不出这是什么
    for name in ("entry_label", "entry_url", "entry_icon"):
        assert 'id="%s"' % name in html
        assert 'for="%s"' % name in html
    # 开关是 checkbox：与站内其它开关一致，用**包裹式 label** 提供可访问名
    # （不需要 for/id 配对，但必须真的被 label 包着，不能是裸 input）。
    i = html.index('name="entry_enabled"')
    assert "<label" in html[max(0, i - 300):i], "开关必须被 label 包裹，否则读屏读不出名字"


def test_post_saves_entry_fields(super_client, app):
    r = _post_settings(super_client, entry_enabled="on", entry_label="工具箱",
                       entry_url="https://box.llhhy.cn", entry_icon="🧰")
    assert r.status_code == 200
    assert _get(app, "entry_enabled") == "true"
    assert _get(app, "entry_label") == "工具箱"
    assert _get(app, "entry_url") == "https://box.llhhy.cn"
    assert _get(app, "entry_icon") == "🧰"


def test_post_saves_entry_disabled_when_unchecked(super_client, app):
    _post_settings(super_client, entry_enabled="on", entry_url="https://box.llhhy.cn")
    assert _get(app, "entry_enabled") == "true"
    _post_settings(super_client, entry_url="https://box.llhhy.cn")   # 不带 checkbox
    assert _get(app, "entry_enabled") == "false", "取消勾选必须真的关掉入口"


def test_bad_entry_url_is_not_saved_but_other_fields_are(super_client, app):
    """同 site_url 的取舍：一个字段填错不能丢掉整张表单。"""
    _post_settings(super_client, entry_enabled="on", entry_url="https://before-%s.example.com" % _r())
    r = _post_settings(super_client, entry_url="javascript:alert(1)", site_name="好好博客")
    assert r.status_code == 200
    assert _get(app, "entry_url").startswith("https://before-"), "非法地址绝不能写库"
    assert _get(app, "site_name") == "好好博客", "其它字段必须照常保存"
    assert "入口" in r.get_data(as_text=True), "应提示用户「未保存」，不能静默丢弃"


def test_entry_enabled_is_in_rollback_snapshot(super_client, app):
    """开关必须进快照 —— 误关了要能回滚，否则「后台可配」是半个功能。"""
    _post_settings(super_client, entry_enabled="on", entry_url="https://a.example.com")
    _post_settings(super_client, entry_url="https://a.example.com")
    with app.app_context():
        import config_rollback as cr
        snaps = cr.list_snapshots()
        assert snaps
        payload = json.loads(snaps[0].payload or "{}")
    assert "entry_enabled" in payload


# ---------- 4. 前台：外域链接必须带 noopener ----------

def test_front_renders_entry_with_noopener():
    """静态扫描：入口是外域链接，``rel="noopener"`` 掉了就等于把 opener 交给对方。

    只扫源码（不渲染 SPA）：这个断言守的是「写法别被后人改掉」，跑得快也够用。
    """
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, APP_VUE), "r", encoding="utf-8") as f:
        src = f.read()
    lines = [ln for ln in src.splitlines() if "site-entry-link" in ln and "<a" in ln]
    assert len(lines) >= 2, "入口应同时出现在桌面导航与移动端抽屉"
    for ln in lines:
        assert 'rel="noopener"' in ln, f"外域入口必须带 noopener：{ln.strip()}"
        assert 'target="_blank"' in ln
        assert ":href" in ln
