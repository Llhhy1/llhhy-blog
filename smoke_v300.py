"""v3.0.0 smoke test — isolated temp DB, exercises new models/migrations/routes.

Run with: DATABASE_URL=sqlite:///<temp> SECRET_KEY=test python smoke_v300.py
"""
import os
import sys
import tempfile

# 隔离临时库
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["SECRET_KEY"] = "smoke-test-secret-key-1234567890"
os.environ["ADMIN_PASSWORD"] = "smoke-admin-password-1234567890"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import app, db
from models import (User, Post, AuditLog, RecycleBin, LinkApplication,
                    PostHistory, ROLE_SUPER, ROLE_USER, visible_posts_query,
                    Category, Tag, Setting)
from utils import count_words

failures = []
def check(name, cond):
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        failures.append(name)

with app.app_context():
    db.create_all()
    # 触发 v3 迁移
    import app as _appmod
    _appmod._migrate_post_table()
    _appmod._migrate_new_tables_v3()

    # 新建超管
    su = User(username="su", role=ROLE_SUPER)
    su.set_password("pw")
    su.must_change_password = False
    db.session.add(su)
    db.session.commit()
    print("== 模型 / 迁移 ==")
    check("AuditLog 表存在", AuditLog.__tablename__ in
          __import__("sqlalchemy").inspect(db.engine).get_table_names())
    check("RecycleBin 表存在", RecycleBin.__tablename__ in
          __import__("sqlalchemy").inspect(db.engine).get_table_names())
    check("LinkApplication 表存在", LinkApplication.__tablename__ in
          __import__("sqlalchemy").inspect(db.engine).get_table_names())
    check("PostHistory 表存在", PostHistory.__tablename__ in
          __import__("sqlalchemy").inspect(db.engine).get_table_names())

    # 建分类（供 RSS 测试）
    from models import Category, Tag
    cat = Category(name="技术", slug="tech")
    db.session.add(cat)
    db.session.commit()
    tag = Tag(name="Python", slug="python")
    db.session.add(tag)
    db.session.commit()

    # 建文章（含 v3.字段）
    p = Post(title="测试文章", slug="test-post", content="# 你好\n\n这是一篇测试文章 about python。",
             author_id=su.id, category_id=cat.id, word_count=0, reading_minutes=0)
    p.tags.append(tag)
    p.word_count, p.reading_minutes = count_words(p.content)
    db.session.add(p)
    db.session.commit()
    # 同步 FTS 索引（生产环境在 admin 新建/编辑文章时自动同步，这里手动补）
    import fts as fts_mod
    try:
        fts_mod.sync_post(p)
    except Exception:
        pass
    check("count_words 字数>0", p.word_count > 0)
    check("reading_minutes>=1", p.reading_minutes >= 1)

    # 搜索分页 + 高亮
    client = app.test_client()
    r = client.get("/api/search?q=python&page=1&per_page=5")
    j = r.get_json()
    print("== 功能3 搜索 ==")
    check("search 返回 pages", "pages" in j and "items" in j)
    check("search 高亮命中词", any("<mark>" in it.get("highlight", "") for it in j["items"]))

    # 隐私空间（功能13）：匿名看不到隐私文章；超管登录后能看到
    p.is_private = True
    db.session.commit()
    r_anon = client.get("/api/post/test-post")
    check("匿名看不到隐私文章(404)", r_anon.status_code == 404)
    # 超管登录后可见
    client.post("/admin/login", data={"username": "su", "password": "pw"})
    r_su = client.get("/api/post/test-post")
    check("超管可见自己隐私文章", r_su.status_code == 200 and r_su.get_json().get("slug") == "test-post")
    p.is_private = False
    db.session.commit()

    # 热门标签
    r = client.get("/api/hot-tags")
    print("== 功能7 热门标签 ==")
    check("hot-tags 返回 list", isinstance(r.get_json().get("items"), list))

    # 趋势图
    r = client.get("/api/stats/trend?days=7")
    print("== 功能9 趋势图 ==")
    check("trend 返回 list", isinstance(r.get_json().get("trend"), list))

    # 看了又看
    r = client.get("/api/post/test-post/also-viewed")
    print("== 功能8 看了又看 ==")
    check("also-viewed 返回 list", isinstance(r.get_json().get("items"), list))

    # 友链申请（公开）
    r = client.post("/api/link-apply", json={"name": "友站", "url": "https://example.com",
                                             "description": "好站", "email": "a@b.com"})
    print("== 功能6 友链申请 ==")
    check("link-apply 提交成功", r.status_code in (200, 201) and r.get_json().get("ok"))
    check("LinkApplication 入库", LinkApplication.query.count() == 1)
    # 垃圾关键词过滤（comment）—— 先写入站点设置
    db.session.add(Setting(key="comment_spam_keywords", value="刷钻,加微信,免费"))
    db.session.commit()
    r = client.post(f"/api/post/{p.slug}/comment", json={"content": "免费刷钻 加微信"})
    print("== 功能2 垃圾过滤 ==")
    check("垃圾评论被拒(400)", r.status_code == 400)

    # 登录超管后访问受保护路由
    with client.session_transaction() as s:
        # 模拟登录（直接构造 session 较复杂，改用 test client 登录接口）
        pass
    lr = client.post("/admin/login", data={"username": "su", "password": "pw"},
                     follow_redirects=False)
    print("== 登录后受保护路由 ==")
    check("admin 登录 302", lr.status_code in (302, 200))

    # audit_logs 页面（超管）
    r = client.get("/admin/audit-logs")
    check("audit_logs 页面可访问", r.status_code == 200)
    r = client.get("/admin/recycle-bin")
    check("recycle_bin 页面可访问", r.status_code == 200)
    r = client.get("/admin/link-applications")
    check("link_applications 页面可访问", r.status_code == 200)
    r = client.get(f"/admin/post/{p.id}/history")
    check("post_history 页面可访问", r.status_code == 200)

    # 软删除 -> 回收站
    r = client.post(f"/admin/post/{p.id}/delete", follow_redirects=False)
    check("删除文章写入回收站", RecycleBin.query.count() == 1)
    # 回收站中文章前台不可见
    visible = visible_posts_query().all()
    check("软删除后前台不可见", all(x.slug != "test-post" for x in visible))

    # RSS 按分类/标签
    r = client.get("/api/rss/category/tech")
    print("== 功能10 RSS ==")
    check("rss/category 返回 xml", "xml" in r.content_type or r.data[:5] == b"<?xml")
    r = client.get("/api/rss/tag/python")
    check("rss/tag 返回 xml", "xml" in r.content_type or r.data[:5] == b"<?xml")

print()
if failures:
    print(f"SMOKE TEST FAILED: {len(failures)} 项 -> {failures}")
    sys.exit(1)
else:
    print("SMOKE TEST PASSED ✅ (all v3.0.0 features boot & respond)")
# 临时库由系统自动回收，跳过显式 unlink 避免 Windows 文件锁报错
