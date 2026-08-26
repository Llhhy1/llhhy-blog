"""v3.7.0 smoke — slug 强制全局设置验证。

覆盖：
1. new_post 语义：slug 占位→flush→apply_slug_template，最终 slug 完全由全局设置生成。
2. edit_post 语义：标题不变→保持原 slug（不破坏旧 URL）；标题变→按全局模板重建。
3. 不同 slug_mode（title / id / category-slug）真正生效；id 模式应忽略标题（强制全局）。
4. 前端 edit_post.html 已无 name="slug" 输入框、草稿 fields 已无 "slug"。

Run with: ./venv/Scripts/python smoke_v370.py
"""
import os
import sys
import tempfile

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name + "?timeout=30"
os.environ["SECRET_KEY"] = "smoke-slug-secret"
os.environ["ADMIN_PASSWORD"] = "SmokeAdmin123"
os.environ["SESSION_IDLE_MINUTES"] = "60"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import app, db
from models import User, ROLE_SUPER, Setting, Post, Category
from utils import apply_slug_template, make_slug

failures = []
def check(name, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)

# 在当前 app_context 的 session 内直接改 Setting（避免嵌套 context 触发 SQLite 锁）
def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s is None:
        s = Setting(key=key, value=value)
        db.session.add(s)
    else:
        s.value = value
    db.session.commit()

# 复刻 new_post 的 Post 构造（与 admin.py 完全一致）
def make_post(title, cat_id):
    return Post(
        title=title, slug=title, summary="", content="demo",
        cover="", category_id=cat_id, published=True,
        scheduled_at=None, is_pinned=False,
        seo_description="", seo_keywords="",
        series_id=None, author_id=1,
        word_count=4, reading_minutes=1,
        is_private=False, reward_enabled=False, reward_qr="",
    )

with app.app_context():
    db.create_all()
    cat = Category(name="技术", slug="tech")
    db.session.add(cat)
    db.session.commit()

    print("== A. title 模式（slug = 标题短名）==")
    set_setting("slug_mode", "title")
    p = make_post("我的第一篇文章", cat.id)
    db.session.add(p)
    db.session.flush()
    p.slug = apply_slug_template(p, p.title)  # 强制全局（用户无输入入口）
    db.session.commit()
    check("new → slug == 标题短名", p.slug == make_slug("我的第一篇文章"))

    old = p.slug
    if make_slug(p.title) != p.slug:  # 标题不变 → 不触发
        p.slug = apply_slug_template(p, p.title)
    check("编辑标题不变 → slug 保持（不破坏旧 URL）", p.slug == old)

    p.title = "全新的标题文章"
    if make_slug(p.title) != p.slug:  # 标题变 → 重建
        p.slug = apply_slug_template(p, p.title)
    db.session.commit()
    check("编辑标题变 → slug 重建为新标题短名", p.slug == make_slug("全新的标题文章"))
    check("编辑标题变 → slug 已不同于旧值", p.slug != old)

    print("== B. id 模式（slug = post-{id}，应忽略标题）==")
    set_setting("slug_mode", "id")
    p2 = make_post("第二篇测试", cat.id)
    db.session.add(p2)
    db.session.flush()
    p2.slug = apply_slug_template(p2, p2.title)
    db.session.commit()
    check("new → slug == post-{id}", p2.slug == f"post-{p2.id}")

    p2.title = "改了标题但 id 模式忽略它"
    if make_slug(p2.title) != p2.slug:
        p2.slug = apply_slug_template(p2, p2.title)
    db.session.commit()
    check("编辑标题变 → slug 仍 == post-{id}（强制全局，忽略用户输入）", p2.slug == f"post-{p2.id}")

    print("== C. category-slug 模式（{category}-{slug}）==")
    set_setting("slug_mode", "category-slug")
    p3 = make_post("第三篇测试", cat.id)
    db.session.add(p3)
    db.session.flush()
    p3.slug = apply_slug_template(p3, p3.title)
    db.session.commit()
    check("new → slug 以分类前缀开头", p3.slug.startswith("tech-"))

print("== D. 前端模板：无 slug 输入框、无 slug 草稿字段 ==")
tpl_path = os.path.join("myblog", "templates", "admin", "edit_post.html")
with open(tpl_path, encoding="utf-8") as f:
    html = f.read()
check("模板无 name=\"slug\" 输入框", 'name="slug"' not in html)
fields_line = html.split("var fields = [")[1].split("]")[0]
check("草稿 fields 无 \"slug\"", '"slug"' not in fields_line)

print("\n== 结果 ==", "全部通过 ✅" if not failures else f"失败项: {failures}")
sys.exit(1 if failures else 0)
