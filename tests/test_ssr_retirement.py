"""v3.18.6 回归：公共 SSR 页面退役（410 Gone）+ endpoint 名保留 + 认证/机器接口不受影响。

背景：生产 Nginx 只把 `/api/` `/admin` `/static/` `/mcp*` 与 feed.xml / sitemap.xml /
robots.txt / feed/comments 反代给 Flask，其余路径由 Vue SPA 兜底（`location /` →
`try_files … /index.html`）。因此 8 个「页面级」SSR 路由在生产**从未被访问**，
且与 SPA 同名页面各自演化（v3.18.5 修的模板时区 bug 就只存在于这些死模板里）。

本文件锁死退役后的契约：
1. 退役页面返回 410（不是 500、不是 404、不是把 SPA 的 index.html 吐回来）；
2. **endpoint 名必须保留** —— `base.html`（仍被 /login、/register 使用）里有
   `url_for('main.post')` 等，删路由会让登录页渲染直接 BuildError；
3. 认证页（/login、/register）与机器接口（feed / sitemap / robots）不受影响；
4. 退役模板文件真的删掉了（留着就会继续漂移），认证与错误页未被误删。
"""
import os

from flask import url_for

RETIRED_PATHS = ["/", "/archive", "/about", "/links", "/search",
                 "/post/zztest-any", "/category/zztest-any", "/tag/zztest-any"]

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "myblog", "templates")
RETIRED_TEMPLATES = ["index.html", "post.html", "archive.html", "archive_timeline.html",
                     "about.html", "links.html", "search.html"]
KEPT_TEMPLATES = ["base.html", "login.html", "register.html", "404.html", "403.html",
                  "500.html", "error.html", "_error_base.html"]


def test_retired_public_pages_return_410(client):
    """8 个公共 SSR 页面一律 410 Gone——服务端不再输出 HTML。"""
    for path in RETIRED_PATHS:
        r = client.get(path)
        assert r.status_code == 410, "%s 期望 410，实际 %s" % (path, r.status_code)


def test_retired_pages_keep_endpoint_names(app):
    """endpoint 名必须保留：删路由会让 base.html 的 url_for 抛 BuildError（登录页直接挂）。"""
    with app.test_request_context():
        assert url_for("main.index") == "/"
        assert url_for("main.post", slug="abc") == "/post/abc"
        assert url_for("main.category", slug="c") == "/category/c"
        assert url_for("main.tag", slug="t") == "/tag/t"
        assert url_for("main.search") == "/search"
        assert url_for("main.about") == "/about"
        assert url_for("main.links") == "/links"
        assert url_for("main.archive") == "/archive"


def test_login_register_still_ssr(client):
    """认证页保留为 SSR：app.py 的会话失效跳转依赖 main.login，且 Nginx 未反代它。"""
    r = client.get("/login")
    assert r.status_code == 200, r.status_code
    assert "登录" in r.get_data(as_text=True)
    r2 = client.get("/register")
    assert r2.status_code == 200, r2.status_code


def test_post_interaction_endpoints_kept(app):
    """两个 POST 交互入口保留（DocsView 公开文档里的 API，且不渲染模板）。"""
    with app.test_request_context():
        assert url_for("main.like_post", slug="x") == "/post/x/like"
        assert url_for("main.add_comment", slug="x") == "/post/x/comment"


def test_machine_endpoints_untouched(client):
    """feed / sitemap / robots / 评论 feed 必须仍然 200（它们是 Nginx 明确反代的路径）。"""
    for path in ["/feed.xml", "/sitemap.xml", "/robots.txt", "/feed/comments"]:
        r = client.get(path)
        assert r.status_code == 200, "%s -> %s" % (path, r.status_code)


def test_api_404_is_still_json(client):
    """退役不影响 API 侧的 JSON 错误信封。"""
    r = client.get("/api/definitely-not-exist")
    assert r.status_code == 404
    assert r.is_json


def test_retired_templates_removed_and_kept_ones_intact():
    for name in RETIRED_TEMPLATES:
        assert not os.path.exists(os.path.join(TEMPLATE_DIR, name)), \
            "退役模板仍残留（会继续与 SPA 漂移）: " + name
    for name in KEPT_TEMPLATES:
        assert os.path.exists(os.path.join(TEMPLATE_DIR, name)), "被误删: " + name
