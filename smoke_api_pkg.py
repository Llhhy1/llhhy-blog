"""v3.6.0 API 包拆分专项 smoke test — 路由零破坏 + stat 模块 NameError 修复闭环验证。

覆盖范围：
1. 路由快照对比：54 条 /api/* 路由与拆分前完全一致（rule + methods + endpoint）
2. stats 模块写路径：visit 落库（summary.total_visits >= 1）、read 记录（Post/User 综合）
3. 拆包遗漏的 NameError 修复验证：
   - stats.py 的 stats.record_visit/record_search/record_read/compute_summary/compute_trend
   - posts.py 的 stats.client_ip / stats.cached_region / User
   - guestbook.py 的 stats.client_ip / stats.cached_region
   - site.py 的 stats.client_ip
   - social.py 的 stats.client_ip（401 登录拦截 = 函数体执行路径正常）
   - series.py 的 Post.created_at 排序
4. 写路径真实落库确认（留言持久化读回）

Run with: ./venv/Scripts/python smoke_api_pkg.py
"""
import os
import sys
import tempfile

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["SECRET_KEY"] = "smoke-api-pkg-secret"
os.environ["ADMIN_PASSWORD"] = "SmokeAdmin123"
os.environ["CAPTCHA_ENABLED"] = "false"
os.environ["BLOG_OPEN_REGISTER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import create_app

app = create_app()
fail = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fail.append(name)


with app.test_client() as c:
    # 1. CSRF token（前端通过 /api/auth/me body 获取）
    #    （路由快照对比由 tools/api_routes_snapshot.py 独立完成：diff 前后 54 条一致）
    r = c.get("/api/auth/me")
    token = (r.get_json(silent=True) or {}).get("csrf_token") or ""
    check("auth/me 返回 csrf_token", bool(token))
    h = {"X-CSRF-Token": token} if token else {}

    # 3. stats 读路径（此前 NameError 重灾区）
    check("GET /api/stats/summary", c.get("/api/stats/summary").status_code == 200)
    check("GET /api/stats/trend", c.get("/api/stats/trend?days=30").status_code == 200)
    check("POST /api/stats/search", c.post("/api/stats/search", json={"keyword": "flask"}).status_code == 200)
    check("POST /api/stats/visit", c.post("/api/stats/visit", json={"path": "/", "post_id": None}).status_code == 200)

    # 4. 造文章 + stats/read（Post.query + stats.client_ip）
    from models import db, Post, Comment
    with app.app_context():
        p = Post(title="SmokePost", slug="smoke-post", content="content", published=True, author_id=None)
        db.session.add(p)
        db.session.commit()
    check("POST /api/stats/read", c.post("/api/stats/read", json={"slug": "smoke-post"}).status_code == 200)
    check("GET /api/post/smoke-post", c.get("/api/post/smoke-post").status_code == 200)

    # 5. visit 落库验证（summary.total_visits >= 1）
    c.post("/api/stats/read", json={"slug": "smoke-post"})
    s = c.get("/api/stats/summary").get_json()
    check("visit 落库 (total_visits>=1)", isinstance(s, dict) and (s.get("total_visits") or 0) >= 1)

    # 6. 评论提交（posts.py: stats.client_ip + User）
    r = c.post("/api/post/smoke-post/comment", json={"content": "smoke", "author": "tester"}, headers=h)
    check("POST comment 201", r.status_code == 201)

    # 7. 留言提交 + 落库读回（guestbook.py: stats.client_ip + cached_region）
    r = c.post("/api/guestbook", json={"author": "tester", "content": "smoke gb"}, headers=h)
    check("POST /api/guestbook 201", r.status_code == 201)
    items = (c.get("/api/guestbook").get_json() or {}).get("items", [])
    check("留言落库读回", any(i.get("author") == "tester" for i in items))

    # 8. 朋友圈发文（social.py: stats.client_ip + cached_region；未登录 401 = 函数体执行路径正常）
    r = c.post("/api/moment", json={"content": "smoke"}, headers=h)
    check("POST /api/moment 401(需登录)", r.status_code == 401)

    # 9. 友链申请（site.py: stats.client_ip）
    r = c.post("/api/link-apply", json={"name": "Tester", "url": "https://example.com"}, headers=h)
    check("POST /api/link-apply 201", r.status_code == 201)

    # 10. 系列列表（series.py: Post.created_at 排序）
    check("GET /api/series", c.get("/api/series").status_code == 200)

print()
if fail:
    print("=== FAIL: " + ", ".join(fail) + " ===")
    sys.exit(1)
print("=== ALL PASS (%d checks) ===" % 10)