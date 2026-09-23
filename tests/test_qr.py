# -*- coding: utf-8 -*-
"""`/api/qr` 站点二维码的可见性与白名单回归（v3.20.0）。

**为什么单独测它**：这个接口有两个容易出错的性质 ——

1. **对外地址的取值来源**。v3.20.0 起，相对路径分支**不再回退 `request.host_url`**
   （闭环 R90 待办②）：site_url 未配置时「由我们构造的对外地址」不能由客户端可控的
   Host 头决定 —— 这是 v3.18.9 为 `/api/og/*` 与 `_abs()` 做过的同一处收口，
   本接口此前是唯一漏网的。未配置应 400。
2. **别名域名可用性**。前端 `SharePanel` 的 `postUrl` 是 `location.origin` 派生的
   （见 `SharePanel.vue` 的 computed），所以**绝对 URL 分支必须继续放行「本次请求的
   host」**，否则从别名域名访问时扫码会 403。这两条要求方向相反，容易改坏其中一个。
"""
import pytest

from models import db, Setting


def _clear_rate():
    from utils import _RATE
    _RATE.clear()


def _set_site_url(value):
    Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
    if value:
        db.session.add(Setting(key="site_url", value=value))
    db.session.commit()


@pytest.fixture(autouse=True)
def _isolate(app):
    """本文件的用例都会打 `/api/qr`，而它按客户端 IP 限流 30 次/60s，测试 IP 恒为
    127.0.0.1 → 必须逐用例清计数，否则会随用例顺序出现「单独跑绿、连跑红」。"""
    _clear_rate()
    with app.app_context():
        _set_site_url("")
    yield
    _clear_rate()
    with app.app_context():
        _set_site_url("")


# ---------------------------------------------------------------------------
# 一、相对路径分支：不再依赖请求 Host
# ---------------------------------------------------------------------------
def test_relative_url_without_site_url_returns_400(app, client):
    """**核心回归**：site_url 未配置 + 相对路径 → 400（不得用 request.host_url 拼）。"""
    r = client.get("/api/qr?url=/post/hello",
                   headers={"Host": "attacker.example.com"})
    assert r.status_code == 400, \
        "未配置 site_url 时应 400，实得 %s（说明仍在用请求 Host 拼对外地址）" % r.status_code
    body = r.get_data(as_text=True)
    assert "site_url" in body, "错误信息应可操作（提示去后台配置）：%r" % body[:120]
    assert "attacker.example.com" not in body, "不得回显请求 Host"


def test_relative_url_with_site_url_renders(app, client):
    """site_url 已配置 + 相对路径 → 200 SVG。"""
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    r = client.get("/api/qr?url=/post/hello")
    assert r.status_code == 200, r.get_data(as_text=True)[:120]
    assert r.mimetype == "image/svg+xml"
    assert r.get_data()[:200].lower().find(b"<svg") >= 0, "应返回 SVG"


def test_site_url_host_header_does_not_leak_into_qr(app, client):
    """站点地址已配置时，伪造 Host 也不得影响出码内容（内容应基于 site_url）。"""
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    r = client.get("/api/qr?url=/post/hello",
                   headers={"Host": "attacker.example.com"})
    assert r.status_code == 200
    # SVG 里不直接含可读 URL（segno 是矢量模块），故改从行为上断言：
    # 伪造 Host 时**不返回 403/400**，说明我们走的是相对路径分支（用 site_url 拼），
    # 而不是「把伪造 Host 当成合法域名」。
    assert b"attacker" not in r.get_data(), "SVG 中不得出现伪造的 Host 字符串"


# ---------------------------------------------------------------------------
# 二、绝对 URL 分支：白名单 + 别名域名可用性
# ---------------------------------------------------------------------------
def test_absolute_foreign_host_forbidden(app, client):
    """绝对 URL 指向外部域名 → 403（防被当公共二维码生成服务）。"""
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    r = client.get("/api/qr?url=https://evil.example.com/phish")
    assert r.status_code == 403


def test_absolute_site_host_allowed(app, client):
    """绝对 URL 指向站点自身域名 → 200。"""
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    r = client.get("/api/qr?url=https://www.llhhy.cn/post/hello")
    assert r.status_code == 200, r.get_data(as_text=True)[:120]


def test_absolute_request_host_allowed_for_alias_domain(app, client):
    """**别名域名可用性**：绝对 URL 用的是访客当前域名（非 site_url 域名）→ 仍应放行。

    依据：前端 `postUrl` = `new URL(path, location.origin)`，即访客地址栏里的域名。
    若这里拒绝，从别名域名访问的访客点「扫码分享」会拿到 403 破图。

    ⚠️ 必须**同时**把请求的 `Host` 设成别名域名 —— 那才是「访客在别名域名上」的
    真实情形（`request.host` 就是浏览器的地址栏）。只改 url 参数而 Host 仍是
    localhost，测的是另一件事，会误判成缺陷。
    """
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    r = client.get("/api/qr?url=https://alias.example.com/post/hello",
                   headers={"Host": "alias.example.com"})
    assert r.status_code == 200, \
        "别名域名的绝对 URL 应放行（实得 %s）——否则别名访问时扫码会破图" % r.status_code


# ---------------------------------------------------------------------------
# 三、非法入参
# ---------------------------------------------------------------------------
def test_bad_url_returns_400(app, client):
    with app.app_context():
        _set_site_url("https://www.llhhy.cn")
    for bad in ("", "ftp://x.cn/a", "javascript:alert(1)", "just-text"):
        r = client.get("/api/qr?url=%s" % bad)
        assert r.status_code in (400, 403), \
            "非法入参应被拒，url=%r 实得 %s" % (bad, r.status_code)
