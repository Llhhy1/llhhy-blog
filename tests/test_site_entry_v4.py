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


@pytest.fixture(autouse=True)
def _fresh_nav_entries(app):
    """每条测试前清空入口列表。

    **为什么必须清**：测试库是**整个 session 共享**的（`%TEMP%/llhhy-blog-pytest/test.db`），
    不清的话上一条测试新增的入口会留到下一条，`items[0]` 就指到了别的对象上 ——
    表现为「断言里的期望值和实际值都是合法数据，但不是同一条」，最难查的那种假失败。
    """
    import nav_entries
    with app.app_context():
        nav_entries.save([])
    yield


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


def _entries(client):
    return (client.get("/api/site").get_json() or {}).get("entries") or []


def _mk(url, label="百宝箱", icon="🧰", enabled=True):
    import nav_entries
    return {"id": nav_entries.new_id(), "label": label, "url": url,
            "icon": icon, "enabled": enabled}


def _save_entries(app, *items):
    """**绕过后台表单**直接写库。

    这是刻意的：要验证的是「**出口过滤**」这条防线本身。
    写入侧（后台）已经拦过一次，但如果哪天它被绕过 —— 迁移脚本、备份还原、
    或后续改动 —— 出口必须是能独立兜住的那一个。**不能两条防线一起失效。**
    """
    import nav_entries
    with app.app_context():
        nav_entries.save(list(items))


def _load_entries(app):
    import nav_entries
    with app.app_context():
        return nav_entries.load()


def _post_settings(client, **extra):
    payload = {"site_title": "T", "site_name": "N"}
    payload.update(extra)
    return client.post("/admin/settings", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


def _post_entry(client, **fields):
    payload = {"label": "工具箱", "url": "https://box.llhhy.cn", "icon": "🧰"}
    payload.update(fields)
    return client.post("/admin/nav-entries/add", data=payload,
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
    _save_entries(app, _mk("https://box.llhhy.cn"))
    e = _entry(client)
    assert e["enabled"] is True
    assert e["url"] == "https://box.llhhy.cn"
    assert e["label"] == "百宝箱"
    assert e["icon"] == "🧰"
    # v4.1.0：同一批入口的列表形态也要可用（前台工具箱下拉读它）
    assert len(_entries(client)) == 1


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "//evil.example.com",
    "file:///etc/passwd",
])
def test_api_site_never_emits_unsafe_href(client, app, bad):
    """**核心断言**：前台拿到的 url 必须为空 —— 不清洗就会变成存储型 XSS。

    v4.1.0 起这条比原来更硬：地址是**绕过后台表单直接写进库**的，
    模拟「写入侧被绕过」的最坏情况。单一防线不够，这里是第二道。
    """
    _save_entries(app, _mk(bad))
    e = _entry(client)
    assert e["enabled"] is False, "地址非法时必须整个禁用，而不是只清 label"
    assert e["url"] == "", f"非法地址 {bad!r} 绝不能出现在前台 JSON 里"
    assert e["label"] == ""
    assert _entries(client) == [], "列表形态同样不能泄漏非法地址"


def test_entry_can_be_switched_off(client, app):
    _save_entries(app, _mk("https://box.llhhy.cn", enabled=True))
    assert _entry(client)["enabled"] is True
    _save_entries(app, _mk("https://box.llhhy.cn", enabled=False))
    assert _entry(client)["enabled"] is False


def test_entry_defaults_to_off_when_never_configured(client, app):
    """没配过 → 不显示。宁可入口消失，也不要显示一个空链接。"""
    _save_entries(app)                       # 空列表
    assert _entry(client)["enabled"] is False
    assert _entries(client) == []


# ---------- 3. 后台：管理页 / 新增 / 拒绝 / 回滚 ----------

def test_management_page_has_all_entry_inputs(super_client):
    html = super_client.get("/admin/nav-entries").get_data(as_text=True)
    for name in ("label", "url", "icon"):
        assert 'name="%s"' % name in html, f"管理页缺 {name} 输入框"
    # 新增表单必须真的指向 add 路由，否则页面只是摆设
    assert "/admin/nav-entries/add" in html


def test_settings_page_points_to_management_page(super_client):
    """v4.1.0：站点设置里不再维护入口，但要留**明确的指路**，不能让人找不到。"""
    html = super_client.get("/admin/settings").get_data(as_text=True)
    assert "/admin/nav-entries" in html, "站点设置必须指向新的入口管理页"
    # 且确实不再有那四个输入框（避免两处都能改导致以哪边为准的困惑）
    for name in ("entry_label", "entry_url", "entry_icon", "entry_enabled"):
        assert 'name="%s"' % name not in html, f"站点设置里不应再能改 {name}"


def test_add_saves_entry(super_client, app):
    r = _post_entry(super_client)
    assert r.status_code == 200
    items = _load_entries(app)
    assert len(items) == 1
    assert items[0]["label"] == "工具箱"
    assert items[0]["url"] == "https://box.llhhy.cn"
    assert items[0]["icon"] == "🧰"
    assert items[0]["enabled"] is True


def test_toggle_really_switches_entry(super_client, app):
    """开关必须真的生效 —— 「后台可配」不是半个功能。"""
    _post_entry(super_client)
    eid = _load_entries(app)[0]["id"]
    for expected in (False, True):
        r = super_client.post("/admin/nav-entries/%s/toggle" % eid,
                              headers={"X-CSRF-Token": _csrf(super_client)},
                              follow_redirects=True)
        assert r.status_code == 200
        assert _load_entries(app)[0]["enabled"] is expected
        assert _entry(super_client)["enabled"] is expected


def test_bad_entry_url_is_not_saved_but_page_still_works(super_client, app):
    """非法地址一条都不许进库，且必须提示用户（不能静默丢弃让人以为存了）。"""
    r = _post_entry(super_client, url="javascript:alert(1)")
    assert r.status_code == 200
    assert _load_entries(app) == [], "非法地址绝不能写库"
    html = r.get_data(as_text=True)
    assert "必须以 http" in html, "应提示用户「未保存」，不能静默丢弃"


def test_edit_keeps_url_when_new_url_is_bad(super_client, app):
    """编辑时地址填错 → 保留旧地址，名称/图标照常改。

    同 site_url 的取舍：一个字段填错不该让人丢掉整张表单的输入。
    """
    r0 = _post_entry(super_client, label="原名", url="https://before.example.com")
    assert r0.status_code == 200
    eid = _load_entries(app)[0]["id"]
    r = super_client.post("/admin/nav-entries/%s/edit" % eid,
                          data={"label": "新名", "icon": "🔧",
                                "url": "javascript:alert(1)"},
                          headers={"X-CSRF-Token": _csrf(super_client)},
                          follow_redirects=True)
    assert r.status_code == 200
    it = _load_entries(app)[0]
    assert it["url"] == "https://before.example.com", "非法地址不能覆盖掉旧地址"
    assert it["label"] == "新名", "名称必须照常保存"
    assert it["icon"] == "🔧", "图标必须照常保存"
    assert "地址未保存" in r.get_data(as_text=True)


def test_nav_entries_is_in_rollback_snapshot(super_client, app):
    """入口必须进快照 —— 误删了要能回滚，否则「后台可配」是半个功能。"""
    _post_entry(super_client)
    _post_entry(super_client, label="第二个", url="https://b.example.com")
    with app.app_context():
        import config_rollback as cr
        snaps = cr.list_snapshots()
        assert snaps
        payload = json.loads(snaps[0].payload or "{}")
    assert "nav_entries" in payload


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
