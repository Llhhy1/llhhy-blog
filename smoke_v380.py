"""v3.8.0 冒烟测试：反爬限流保护 + SEO 服务增强（端到端）。

自建临时 SQLite + 最小 Flask app，注册 main_bp，覆盖：
- BotBlock 新表自动创建
- 反爬限流：默认关闭放行 / 搜索引擎白名单豁免 / 普通高频限流 / 坏 Bot 更严+封禁 / 解封 / 已封禁拦截
- SEO：sitemap.xml(lastmod/changefreq/priority) / robots.txt(屏蔽坏 Bot) / feed.xml(dc:creator) / 文章页 JSON-LD
"""
import os
import sys
import datetime
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
os.environ.setdefault("SECRET_KEY", "smoke-test-secret-key-0123456789abcdef")
os.environ.setdefault("ADMIN_PASSWORD", "smoke-test-admin-password-0123456789")

from flask import Flask, request
from models import db, Post, Setting, BotBlock, Category
import utils
import bot_guard
from routes import main_bp
from admin import admin_bp

MYBLOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog")
app = Flask(__name__,
            template_folder=os.path.join(MYBLOG, "templates"),
            static_folder=os.path.join(MYBLOG, "static"))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "blog.db")
app.config["TESTING"] = True
app.config["SERVER_NAME"] = "localhost"
db.init_app(app)


@app.context_processor
def _smoke_inject_globals():
    """模拟项目 inject_globals，提供模板渲染所需的全局变量。"""
    settings = {s.key: s.value for s in Setting.query.all()}
    return dict(
        settings=settings,
        site_title=settings.get("site_title", "我的博客"),
        current_user=None,
        theme_css="",
        custom_css="",
        csrf_input=lambda: "",
        csrf_token="",
        cats=[], tags=[], links=[], recent=[],
        total_posts=0, total_views=0, total_comments=0,
        now_year=2026, admin_css_v="0",
    )


app.register_blueprint(main_bp)
app.register_blueprint(admin_bp)

PASS = []
def check(name, cond):
    assert cond, f"FAIL: {name}"
    PASS.append(name)
    print("  ✓", name)

with app.app_context():
    db.create_all()
    from sqlalchemy import inspect
    check("bot_block 表自动创建", "bot_block" in inspect(db.engine).get_table_names())

    def set_setting(key, value):
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()

    # 1) 默认关闭 → 放行
    with app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "203.0.113.5"}):
        check("防护默认关闭时放行", bot_guard.check_bot_guard() is None)

    # 2) 开启 + 搜索引擎白名单豁免
    set_setting("bot_guard_enabled", "true")
    set_setting("bot_guard_search_whitelist", "true")
    with app.test_request_context("/", headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
                                  environ_overrides={"REMOTE_ADDR": "203.0.113.5"}):
        check("搜索引擎(Googlebot)白名单豁免", bot_guard.check_bot_guard() is None)

    # 3) 普通 UA 高频触发限流（阈值 2 / 窗口 60，不封禁仅记录）
    utils._RATE.clear()
    set_setting("bot_guard_threshold", "2")
    set_setting("bot_guard_window", "60")
    set_setting("bot_guard_block_hits", "5")
    ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/120 Safari/537"
    ctx = app.test_request_context("/", headers={"User-Agent": ua},
                                   environ_overrides={"REMOTE_ADDR": "198.51.100.7"})
    ctx.push()
    try:
        r1 = bot_guard.check_bot_guard()
        r2 = bot_guard.check_bot_guard()
        r3 = bot_guard.check_bot_guard()
        check("真人前两次放行", r1 is None and r2 is None)
        check("真人第三次被限流(429/rate_human)",
              r3 is not None and r3["code"] == 429 and r3["reason"] == "rate_human")
    finally:
        ctx.pop()

    # 4) 风控统计
    st = bot_guard.guard_stats()
    check("guard_stats 返回且 total>=1", st["total"] >= 1 and "blocked_now" in st)

    # 5) 坏 Bot 更严格阈值 + 立即封禁
    utils._RATE.clear()
    set_setting("bot_guard_tool_limit", "1")
    set_setting("bot_guard_block_hits", "1")
    ctx = app.test_request_context("/", headers={"User-Agent": "AhrefsBot/1.0"},
                                   environ_overrides={"REMOTE_ADDR": "192.0.2.9"})
    ctx.push()
    try:
        r1 = bot_guard.check_bot_guard()  # 第1次放行（rate_limit 首次要累计）
        r2 = bot_guard.check_bot_guard()  # 第2次限流
        check("坏 Bot(AhrefsBot)第1次放行", r1 is None)
        check("坏 Bot(AhrefsBot)第2次触发 tool 限流",
              r2 is not None and r2["reason"] == "rate_tool")
        rec = BotBlock.query.filter_by(bot_name="AhrefsBot").first()
        check("坏 Bot 被封禁(blocked_until 非空)",
              rec is not None and rec.blocked_until is not None)
    finally:
        ctx.pop()

    # 6) 解封
    rec = BotBlock.query.first()
    check("unblock_ip 成功", bot_guard.unblock_ip(rec.ip) is True)
    check("unblock 未知 IP 返回 False", bot_guard.unblock_ip("9.9.9.9") is False)

    # 7) 已封禁 IP 拦截
    b = BotBlock(ip="203.0.113.99", active=True,
                 blocked_until=datetime.datetime.utcnow() + datetime.timedelta(minutes=10))
    db.session.add(b)
    db.session.commit()
    with app.test_request_context("/", headers={"User-Agent": ua},
                                  environ_overrides={"REMOTE_ADDR": "203.0.113.99"}):
        rb = bot_guard.check_bot_guard()
        check("已封禁 IP 被拦截(reason=blocked)", rb is not None and rb["reason"] == "blocked")

    # 8) SEO 端到端
    cat = Category(name="技术", slug="tech")
    db.session.add(cat)
    db.session.commit()
    p = Post(title="SEO测试文章", slug="seo-test", content="正文内容", published=True,
             category_id=cat.id, summary="这是摘要")
    db.session.add(p)
    db.session.commit()

    client = app.test_client()
    r = client.get("/sitemap.xml")
    check("sitemap 含 lastmod/changefreq/priority",
          b"lastmod" in r.data and b"changefreq" in r.data and b"priority" in r.data)
    r = client.get("/robots.txt")
    check("robots 指向 sitemap", b"Sitemap:" in r.data)
    set_setting("seo_block_bots", "AhrefsBot")
    r = client.get("/robots.txt")
    check("robots 屏蔽指定坏 Bot",
          b"User-agent: AhrefsBot" in r.data and b"Disallow: /" in r.data)
    r = client.get("/feed.xml")
    check("feed.xml 含 dc:creator", b"dc:creator" in r.data)
    r = client.get("/post/seo-test")
    check("文章页含 JSON-LD(BlogPosting)",
          b"application/ld+json" in r.data and b"BlogPosting" in r.data)

    # 9) 关闭防护后不再拦截
    set_setting("bot_guard_enabled", "false")
    utils._RATE.clear()
    with app.test_request_context("/", headers={"User-Agent": ua},
                                  environ_overrides={"REMOTE_ADDR": "198.51.100.7"}):
        check("关闭防护后放行", bot_guard.check_bot_guard() is None)

print(f"\n通过 {len(PASS)}/{len(PASS)} 项断言 ✅")
print("ALL SMOKE V3.8.0 TESTS PASSED")
