"""后台「站点对外地址（site_url）」配置入口守卫（v3.25.5）。

**这个测试存在的理由**：`site_url` 是全站绝对地址的**唯一真相源**
（canonical / og:url / sitemap / 分享卡片 / 邮件里的文章链接 / 证书到期监控
全靠它），但后台**从来没有输入框** —— SEO 页却一直红字警告「未配置」并
**链接到站点设置页**，把人指进死胡同（只剩改环境变量或直接改库两条路）。
2026-10-05 上线证书监控时实测踩到：生产 `site_base()` 为空 → 监控报的 host
是本机名 `llhhy1`（v3.25.4 已改成明确报 unknown）。

**判据不是"能不能存"，而是"存进去的是不是能用的地址"**：
`site_url` 写坏（带路径 / 带参数 / 非 http(s)）**不报错**，只会静默让全站对外
声明漂移 —— canonical 指向错页、二维码内容错、sitemap 域名错。等发现时外链
已经散出去了。所以保存前必须清洗 + 拒绝，且**拒绝时不能丢掉整张表单的其它编辑**。
"""
import contextlib
import json
import secrets

import pytest

from models import db, User, Setting, ROLE_SUPER

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


@pytest.fixture()
def super_client(client, app):
    """以超管身份登录的 client；并把 SITE_URL 置空，让断言只反映 DB 里的 site_url。

    ⚠️ `SITE_URL` 必须置空：`site_base()` 的优先级是 DB → 环境变量 → 空串，
    环境变量有残留时会让「清空后应未配置」的断言假绿。
    """
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


def _post_settings(client, **extra):
    payload = {"site_title": "T", "site_name": "N", "site_url": "https://www.example.com"}
    payload.update(extra)
    return client.post("/admin/settings", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


def _get_setting(app, key):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        return row.value if row else None


# ---------- 1. 输入框必须存在（本次修复的缺口本身） ----------

def test_settings_page_has_site_url_input(super_client):
    """站点设置页必须有 site_url 输入框 —— 否则 SEO 页的「前往填写」是死链。"""
    html = super_client.get("/admin/settings").get_data(as_text=True)
    assert 'name="site_url"' in html, "后台缺 site_url 输入框：唯一配置入口不存在"
    assert 'id="site_url"' in html
    # 必须配 label（`for` 指向它），否则屏幕阅读器读不出这是什么
    assert 'for="site_url"' in html


def test_seo_page_link_points_at_the_input(super_client):
    """SEO 页的告警链接必须能直接落到那个字段上（带锚点）。"""
    html = super_client.get("/admin/seo").get_data(as_text=True)
    assert "#site_url" in html, "SEO 页告警应直接锚到 site_url 输入框，别让人再找一遍"


# ---------- 2. 清洗：写进去的必须是能用的地址 ----------

@pytest.mark.parametrize("raw, want", [
    ("https://www.example.com", "https://www.example.com"),
    ("https://www.example.com/", "https://www.example.com"),     # 尾部斜杠
    ("  https://www.example.com  ", "https://www.example.com"),  # 前后空白
    ("http://localhost:8686", "http://localhost:8686"),          # 本地/端口
    ("https://u:p@www.example.com", "https://www.example.com"),  # userinfo 不该进站点地址
    ("", ""),                                                    # 清空 = 未配置
])
def test_normalize_accepts(raw, want):
    from admin.settings import _normalize_site_url
    val, err = _normalize_site_url(raw)
    assert err is None, f"{raw!r} 应被接受，却被拒：{err}"
    assert val == want


@pytest.mark.parametrize("raw", [
    "www.example.com",                 # 没协议
    "//www.example.com",
    "javascript:alert(1)",             # 非 http(s) scheme
    "file:///etc/passwd",
    "https://www.example.com/blog",    # 带路径
    "https://www.example.com/?a=1",    # 带参数
    "https://www.example.com#x",       # 带锚点
    "https://",                        # 没域名
    "https://www.example.com:notaport",
])
def test_normalize_rejects(raw):
    from admin.settings import _normalize_site_url
    val, err = _normalize_site_url(raw)
    assert val is None and err, f"{raw!r} 应被拒绝（写坏会静默污染全站绝对地址）"


# ---------- 3. 端到端：保存 / 拒绝 / 清空 ----------

def test_post_saves_site_url_and_site_base_sees_it(super_client, app):
    r = _post_settings(super_client, site_url="https://www.llhhy.cn/")
    assert r.status_code == 200
    assert _get_setting(app, "site_url") == "https://www.llhhy.cn"
    with app.app_context():
        from utils import site_base
        assert site_base() == "https://www.llhhy.cn"


def test_bad_site_url_is_not_saved_but_other_fields_are(super_client, app):
    """一个字段填错**不能**丢掉整张表单的其它编辑 —— 那样比不校验还糟。

    ⚠️ 先写一个合法值做基线，再断言「非法值提交后它没被改掉」。
    不能断言 `is None`：测试库在整个 session 内共享，前面用例写的值还在，
    断言 None 会在换顺序时假红/假绿。
    """
    _post_settings(super_client, site_url="https://before.example.com")
    r = _post_settings(super_client, site_url="www.example.com", site_name="好好博客")
    assert r.status_code == 200
    assert _get_setting(app, "site_url") == "https://before.example.com", "非法地址绝不能写库"
    assert _get_setting(app, "site_name") == "好好博客", "其它字段必须照常保存"
    assert "site_url" in r.get_data(as_text=True), "应把「未保存」提示给用户，不能静默丢弃"


def test_clearing_site_url_disables_it(super_client, app):
    _post_settings(super_client, site_url="https://www.example.com")
    assert _get_setting(app, "site_url") == "https://www.example.com"
    _post_settings(super_client, site_url="")
    assert _get_setting(app, "site_url") == ""
    with app.app_context():
        from utils import site_base
        assert site_base() == "", "清空后 site_base() 必须为空（未配置），而不是回退请求 Host"


def test_settings_page_shows_effective_base(super_client, app):
    """页面要显示**实际生效**的地址，不是只回显输入框里那个值。"""
    html = super_client.get("/admin/settings").get_data(as_text=True)
    assert "未配置" in html, "未配置时应明确显示「未配置」，别让人以为生效了"
    _post_settings(super_client, site_url="https://www.llhhy.cn")
    html = super_client.get("/admin/settings").get_data(as_text=True)
    assert "https://www.llhhy.cn" in html


def test_site_url_is_in_rollback_snapshot(super_client, app):
    """site_url 必须进配置快照 —— 改错后能回滚，否则补了输入框也白补。"""
    _post_settings(super_client, site_url="https://a.example.com")
    _post_settings(super_client, site_url="https://b.example.com")
    with app.app_context():
        import config_rollback as cr
        snaps = cr.list_snapshots()
        assert snaps, "保存时应拍快照"
        # 直接看快照**记了什么**（`list_snapshots()` 返回的是 ORM 对象不是 dict）。
        # 不用 `diff_snapshot()`：它只列「有变化」的项，值没变时会静默缺项。
        payload = json.loads(snaps[0].payload or "{}")
    assert "site_url" in payload, "site_url 必须在快照里，否则改错无从回滚"
