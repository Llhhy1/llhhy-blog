"""文章 / 搜索 API 冒烟测试（v3.17.11 · 审计 R76-R4 补测）。

背景：全项目审查发现测试分布偏斜——MCP / 主题中心 / 插件系统有专测，而**影响面最大的
公开内容面（articles / search）此前无专测**。本文件覆盖该面最小必要集：

1. `/api/posts` 分页边界夹取（per_page > 50 或 <= 0 → 回落默认 10，防止拉全表）；
2. 不存在的 slug → 404；
3. 空关键词搜索 → 空结果（不报错）；
4. **搜索高亮 XSS 防护**：关键词里的 HTML 必须被转义，不得原样进入前端 `v-html` 出口；
5. 草稿文章（published=False）对匿名用户不可见（404）。

数据卫生：仅第 5 项写入一条 `ZZTEST` 前缀草稿并在 `finally` 清理，其余为只读断言。
"""
from models import db, Post


def test_posts_per_page_is_server_controlled(client):
    """`/api/posts` 的 per_page 固定取服务端配置，**完全忽略客户端传参** → 无法借参数一次拉全量。"""
    base = client.get("/api/posts").get_json()
    assert isinstance(base.get("per_page"), int) and 0 < base["per_page"] <= 50
    for qs in ("per_page=999", "per_page=0", "per_page=-3"):
        d = client.get("/api/posts?" + qs).get_json()
        assert d.get("per_page") == base["per_page"], qs


def test_search_per_page_clamped(client):
    """`/api/search` 接受 per_page，但超界（>50 或 <=0）会被夹取为 10。

    响应体不返回 per_page 字段，因此从「条目数不超过 10」验证夹取生效
    （即客户端无法借参数一次拉取全量文章）。
    """
    for qs in ("per_page=999", "per_page=0", "per_page=-3"):
        d = client.get("/api/search?q=a&" + qs).get_json()
        assert isinstance(d.get("items"), list), qs
        assert len(d["items"]) <= 10, qs


def test_post_detail_missing_slug_404(client):
    r = client.get("/api/post/zztest-does-not-exist-9f8e7d6c")
    assert r.status_code == 404


def test_search_empty_query_returns_empty(client):
    d = client.get("/api/search?q=").get_json()
    assert d.get("items") == []
    assert d.get("total") == 0


def test_search_highlight_does_not_leak_raw_html(client):
    """高亮实现为「先 escape 全文 → 再正则包裹 <mark>」，注入标签不得原样进入高亮字段。

    注意：响应里的 `query` 字段会回显搜索词（JSON 文本，前端不做 v-html 渲染），
    因此只针对 `highlight`（真正走 v-html 的字段）断言。
    """
    payload = "<img src=x onerror=alert(1)>"
    r = client.get("/api/search", query_string={"q": payload})
    assert r.status_code == 200
    for it in (r.get_json() or {}).get("items", []):
        h = it.get("highlight") or ""
        assert "<img" not in h, h
        assert "onerror" not in h, h


def test_draft_post_hidden_from_anonymous(app, client):
    """草稿（published=False）匿名访问应 404，不得因 slug 命中而泄露内容。"""
    slug = "zztest-draft-hidden-9f8e7d"
    with app.app_context():
        db.session.add(Post(title="ZZTEST 草稿不可见", slug=slug, content="secret-body", published=False))
        db.session.commit()
    try:
        assert client.get("/api/post/" + slug).status_code == 404
    finally:
        with app.app_context():
            Post.query.filter_by(slug=slug).delete()
            db.session.commit()
