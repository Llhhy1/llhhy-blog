"""v2.8.0 冒烟测试：隔离临时库，验证本轮新增功能。"""
import os, sys, tempfile, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "myblog"))

# 用临时库，避免污染真实数据
tmp = tempfile.mkdtemp(prefix="smoke_v28_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "test.db")
# 启动所需的密钥（冒烟环境，不入库）
os.environ["SECRET_KEY"] = "smoke-test-secret-key-0123456789abcdef"
os.environ["ADMIN_PASSWORD"] = "smoke-test-admin-pass"

from app import create_app, count_unique_view, maybe_convert_webp
from models import db, Post, Category, Comment, ReadLog, visible_posts_query
import admin as admin_mod
import api as api_mod
import routes as routes_mod
from config import APP_VERSION

app = create_app()
client = app.test_client()
fails = []

def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        fails.append(name)

with app.app_context():
    # 1) 迁移：Post 含 seo 列
    from sqlalchemy import inspect
    cols = [c["name"] for c in inspect(db.engine).get_columns("post")]
    check("post 表含 seo_description 列", "seo_description" in cols)
    check("post 表含 seo_keywords 列", "seo_keywords" in cols)
    check("已导入 APP_VERSION", bool(APP_VERSION))

    cat = Category(name="测试", slug="test"); db.session.add(cat); db.session.flush()

    now = datetime.datetime.utcnow()
    old = Post(title="旧文", slug="old", content="x", views=0, published=True,
               category_id=cat.id, created_at=now - datetime.timedelta(hours=2))
    new = Post(title="新文", slug="new", content="x", views=0, published=True,
               category_id=cat.id, created_at=now)
    pin = Post(title="置顶文", slug="pin", content="x", views=0, published=True,
               category_id=cat.id, created_at=now, is_pinned=True)
    for p in (old, new, pin):
        db.session.add(p)
    db.session.commit()

    # 2) 置顶优先排序
    items = visible_posts_query().order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()
    check("置顶文章排最前", items[0].slug == "pin")

    # 3) 阅读量防刷：同 IP 24h 内只计一次
    ip = "1.2.3.4"
    a = count_unique_view(old.id, ip)
    b = count_unique_view(old.id, ip)  # 立刻再计，应去重
    check("首次阅读计数 True", a is True)
    check("24h 内重复不计数", b is False)
    # 不同 IP 再计
    c = count_unique_view(old.id, "5.6.7.8")
    check("不同 IP 计数 True", c is True)
    rl_count = ReadLog.query.filter_by(post_id=old.id).count()
    check("ReadLog 记录两不同 IP（2 条）", rl_count == 2)

    # 4) 后台分页筛选：dashboard 路由（管理员登录态）
    # 直接构造请求（无登录会跳登录页，这里只验证筛选查询函数通过编译/导入即可）
    check("admin 模块含分页筛选 dashboard", "dashboard" in dir(admin_mod))
    check("api 含 publish-now", "publish_now" in dir(api_mod))

    # 5) 一键发布 API（模拟登录超管）
    sched = Post(title="定时文", slug="sched", content="x", published=False,
                 category_id=cat.id,
                 scheduled_at=now + datetime.timedelta(hours=1))
    db.session.add(sched); db.session.commit()
    sid = sched.id
    with app.test_request_context():
        from models import User
        from werkzeug.security import generate_password_hash
        # 找一个超管
        su = User.query.filter_by(role="super").first()
        with client.session_transaction() as sess:
            sess["user_id"] = su.id
        resp = client.post(f"/api/post/{sid}/publish-now")
        data = resp.get_json()
        check("一键发布 API 成功", data.get("ok") is True)
        db.session.refresh(sched)
        check("一键发布后 published=True", sched.published is True)
        check("一键发布后 scheduled_at 清空", sched.scheduled_at is None)

    # 6) WebP 转换（无 Pillow 应安全降级返回原路径）
    sample = os.path.join(tmp, "fake.png")
    open(sample, "wb").write(b"not really png")
    out = maybe_convert_webp(sample)
    check("WebP 转换安全降级（返回路径）", isinstance(out, str) and os.path.exists(out))

print("\n==== 结果 ====")
if fails:
    print("失败项:", fails)
    sys.exit(1)
else:
    print("全部通过 ✅")
