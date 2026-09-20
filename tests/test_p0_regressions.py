"""v3.18.5 P0 回归测试 —— 独立审计报告第 1 章八项 + 两处连带缺陷。

背景：2026-09-20 的第三方独立审计（对象 tag v3.18.4）报告了 8 项「现在就是坏的」
缺陷。本文件为每一项补一条回归测试；修复前这些断言全部失败，修复后全绿。

覆盖：
  1.1 app.py 未导入 redirect → 会话失效即 500（非 /api/ 路径）
  1.2 前台 SSR 登录/注册不写 session_version → 改密后被永久踢出
  1.3 `return app` 之后的 CLI 命令从未注册
  1.4 /api/review/annual 泄露隐私空间 + 回收站文章
  1.5 /api/ai/summary/<slug> 无可见性过滤（+ 后台 AI 摘要页提权）
  1.6 bleach 白名单缺表格标签 → Markdown 表格被静默剥空
  1.7 零错误处理器 → first_or_404() 对 JSON 客户端返回 HTML
  1.8 测试跑在真实开发库 myblog/data/blog.db 上
  2.2 审计日志来源 IP 取 XFF 最左段 → 可任意伪造
  2.10 后台仪表盘 ?category_id=abc → 500 / 未鉴权接口回显异常详情
"""
import secrets

from models import db, User, Post, AuditLog, ROLE_ADMIN
from utils import _sign_csrf


# ---------- 公共小工具 ----------
def _uid():
    return secrets.token_hex(4)


def _mkuser(role=ROLE_ADMIN):
    name = "p0-" + _uid()
    u = User(username=name, email=name + "@test.local")
    u.set_password("test-pass-123")
    u.role = role
    u.must_change_password = False  # 否则会被引导到 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _auth(app, client, user_id, version=0):
    """写入会话（user_id + session_version + 有效 CSRF token）。"""
    with app.app_context():          # _sign_csrf 需要应用上下文取 SECRET_KEY
        raw = secrets.token_hex(24)
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["session_version"] = version
        sess["csrf_token"] = tok
    return tok


def _csrf_only(app, client):
    with app.app_context():
        raw = secrets.token_hex(24)
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["csrf_token"] = tok
    return tok


# ---------- 1.1 redirect 未导入 ----------
def test_session_version_mismatch_redirects_instead_of_500(app, client):
    """过期的 session_version（改密/被踢下线后的旧会话）访问非 /api/ 路径应 302 到登录页。

    修复前 app.py 三处 `return redirect(...)` 里 redirect 未导入 → NameError → 500。
    """
    with app.app_context():
        u = _mkuser()
        uid, ver = u.id, (u.session_version or 0)
    _auth(app, client, uid, version=ver + 1)  # 会话里的版本号已过期
    r = client.get("/about")
    assert r.status_code == 302, "应为 302 跳登录，实际 %s" % r.status_code
    assert "/login" in (r.headers.get("Location") or "")


# ---------- 1.2 前台登录不写 session_version ----------
def test_ssr_login_writes_session_version(app, client):
    """SSR 表单登录必须把 session_version 写进会话，否则改过密码的用户登录后立刻被判失效。"""
    with app.app_context():
        u = _mkuser()
        u.session_version = 1  # 模拟「改过密码 / 被踢过线」的用户
        db.session.commit()
        uid, name = u.id, u.username
    tok = _csrf_only(app, client)
    r = client.post("/login", data={"csrf_token": tok, "username": name,
                                    "password": "test-pass-123"})
    assert r.status_code == 302, r.status_code
    with client.session_transaction() as sess:
        assert sess.get("user_id") == uid
        assert sess.get("session_version") == 1, "登录未写入 session_version"
    # 登录后访问后台不应被踢回登录页（修复前此处会被 enforce_session_version 清会话）
    r2 = client.get("/admin/")
    assert r2.status_code != 500
    assert "/login" not in (r2.headers.get("Location") or "")


# ---------- 1.3 return app 之后的死代码 ----------
def test_seed_cli_command_is_registered(app):
    """`flask seed` 必须真的注册成功（修复前 CLI 定义在 return app 之后，永不执行）。"""
    assert "seed" in app.cli.commands


# ---------- 1.4 年度回顾泄露隐私/回收站文章 ----------
def test_annual_review_hides_private_and_trashed_posts(app, client):
    """隐私空间与回收站文章不得出现在 /api/review/annual 的任何字段里。

    两篇都设 views=999999，确保它们「若不是被过滤就必然占据 hot_posts 前二」。
    """
    s_priv = "p0-private-" + _uid()
    s_trash = "p0-trashed-" + _uid()
    with app.app_context():
        db.session.add(Post(title="P0 隐私标题", slug=s_priv, content="secret",
                            published=True, is_private=True, views=999999))
        db.session.add(Post(title="P0 回收站标题", slug=s_trash, content="secret",
                            published=True, in_trash=True, views=999999))
        db.session.commit()
    try:
        d = client.get("/api/review/annual").get_json()
        leaks = {h["slug"] for h in d.get("hot_posts", [])}
        assert s_priv not in leaks, "隐私文章 slug 被匿名泄露"
        assert s_trash not in leaks, "回收站文章 slug 被匿名泄露"
        titles = {h["title"] for h in d.get("hot_posts", [])}
        assert "P0 隐私标题" not in titles
        assert "P0 回收站标题" not in titles
    finally:
        with app.app_context():
            Post.query.filter(Post.slug.in_([s_priv, s_trash])).delete(synchronize_session=False)
            db.session.commit()


# ---------- 1.5 AI 摘要泄露 + 后台提权 ----------
def test_ai_summary_api_hides_private_post(app, client):
    """隐私文章的 AI 摘要/标签不得被匿名读取（修复前任意 slug 都能读到）。"""
    from api.ai import _setting_set
    s = "p0-ai-private-" + _uid()
    with app.app_context():
        p = Post(title="P0 私密摘要", slug=s, content="secret", published=True, is_private=True)
        db.session.add(p)
        db.session.commit()
        pid = p.id
        _setting_set("ai_summary_%d" % pid, "SECRET-SUMMARY-CONTENT")
        db.session.commit()
    try:
        r = client.get("/api/ai/summary/" + s)
        assert r.status_code == 404, "隐私文章摘要被泄露：%s" % r.status_code
    finally:
        with app.app_context():
            Post.query.filter_by(slug=s).delete()
            from models import Setting
            Setting.query.filter(Setting.key.in_(
                ["ai_summary_%d" % pid, "ai_tags_%d" % pid])).delete(synchronize_session=False)
            db.session.commit()


def test_ai_summary_admin_page_requires_super(app, client):
    """AI 摘要管理页已提权为超管专属：普通管理员应 403（它会把正文外发到自设 LLM Base）。"""
    with app.app_context():
        u = _mkuser(role=ROLE_ADMIN)
        uid = u.id
    _auth(app, client, uid, version=0)
    r = client.get("/admin/ai-summary")
    assert r.status_code == 403, "普通管理员仍可访问 AI 摘要页：%s" % r.status_code


# ---------- 1.6 Markdown 表格被剥空 ----------
def test_markdown_table_survives_sanitize():
    """markdown 的 tables 扩展产出必须能通过 bleach 白名单（修复前整表被 strip 掉）。"""
    from utils import render_markdown
    html = render_markdown("| 列A | 列B |\n| --- | --- |\n| 1 | 2 |")
    for tag in ("<table", "<thead", "<tbody", "<tr", "<th", "<td"):
        assert tag in html, "表格标签 %s 被剥掉了：%s" % (tag, html)


# ---------- 1.7 错误处理器 ----------
def test_api_404_returns_json_not_html(client):
    """JSON 客户端拿到 first_or_404 时必须是 JSON 信封（修复前是 Werkzeug HTML 错误页）。"""
    r = client.get("/api/post/zztest-no-such-slug-" + _uid())
    assert r.status_code == 404
    assert r.is_json, "API 404 未返回 JSON：%s" % r.headers.get("Content-Type")
    assert "error" in (r.get_json() or {})


def test_html_404_uses_template(client):
    """浏览器路径的 404 应走模板页（404.html），不再是裸 Werkzeug 页面。"""
    r = client.get("/no-such-page-" + _uid())
    assert r.status_code == 404
    assert "text/html" in (r.headers.get("Content-Type") or "")
    assert "页面不存在" in r.get_data(as_text=True)


# ---------- 1.8 测试库隔离 ----------
def test_tests_run_on_isolated_database(app):
    """测试必须跑在临时库上，绝不碰 myblog/data/blog.db。"""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "blog.db" not in uri, "测试仍在用开发库：%s" % uri
    assert "llhhy-blog-pytest" in uri, uri


# ---------- 2.2 审计日志 IP 收口 ----------
def test_audit_log_ip_ignores_forged_xff(app):
    """伪造的 XFF 左段不得进入审计日志（修复前取 XFF 最左段，可写入任意 IP）。"""
    from admin._helpers import log_audit
    with app.test_request_context(
        "/admin/",
        environ_base={"REMOTE_ADDR": "203.0.113.9",
                      "HTTP_X_FORWARDED_FOR": "1.2.3.4, 203.0.113.9"},
    ):
        log_audit("p0_xff_probe", "post", None, "XFF 收口回归测试")
    with app.app_context():
        try:
            row = (AuditLog.query.filter_by(action="p0_xff_probe")
                   .order_by(AuditLog.id.desc()).first())
            assert row is not None, "审计日志未写入"
            assert row.ip == "203.0.113.9", "审计 IP 被伪造的 XFF 污染：%s" % row.ip
        finally:
            AuditLog.query.filter_by(action="p0_xff_probe").delete(synchronize_session=False)
            db.session.commit()


# ---------- 2.10 两处 500 / 信息泄露 ----------
def test_admin_dashboard_bad_category_id_no_500(app, client):
    """?category_id=abc 应被忽略而不是抛 ValueError → 500。"""
    with app.app_context():
        u = _mkuser()
        uid = u.id
    _auth(app, client, uid, version=0)
    r = client.get("/admin/?category_id=abc")
    assert r.status_code == 200, "非法 category_id 触发 %s" % r.status_code


def test_stats_dashboard_does_not_leak_exception_detail(app, client, monkeypatch):
    """未鉴权的 /api/stats/dashboard 出错时不得回显 str(e)（可能含路径/库结构）。"""
    import api.stats as api_stats

    def _boom(**kwargs):
        raise RuntimeError("internal path /www/wwwroot/llhhy/data/blog.db")

    monkeypatch.setattr(api_stats.stats, "compute_dashboard", _boom)
    r = client.get("/api/stats/dashboard")
    assert r.status_code == 500
    body = r.get_json() or {}
    assert body.get("error") == "dashboard_failed"
    assert "detail" not in body, "异常详情被回显：%s" % body
    assert "blog.db" not in r.get_data(as_text=True)
