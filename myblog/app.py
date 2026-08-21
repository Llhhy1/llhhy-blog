"""应用入口。
- create_app(): 创建并配置 Flask 应用
- app = create_app(): 模块加载时直接创建实例，方便 `flask run` / gunicorn 启动
"""
import os
import re
import datetime

from flask import Flask, render_template, request, session, jsonify
from werkzeug.security import generate_password_hash

from models import (db, Post, Category, Tag, Comment, FriendLink, Setting, User,
                   ROLE_SUPER, Moment, MomentComment, SocialAccount,
                   Series, Announcement, Guestbook, Subscriber)
from utils import make_slug
from routes import main_bp
from admin import admin_bp
from api import api_bp


def _ensure_settings(app):
    """保证站点设置表有默认值（首次运行时写入）。"""
    defaults = {
        "site_title": app.config.get("SITE_TITLE", "我的博客"),
        "site_name": "我的博客",        # 博客名称（前台 logo / 浏览器标签页）
        "site_note": "",                # 浏览器便签（前台顶部公告条，留空不显示）
        "site_description": "欢迎来到我的博客，这里记录我的生活、技术与想法。",
        "about_content": "这里是关于本站的描述，你可以在后台「站点设置」里修改这段文字。",
        "footer_text": "© " + str(datetime.datetime.now().year) + " 我的博客 · 由 Flask 驱动",
        "beian_code": "",
        "weather_lat": "39.9042",   # 默认北京纬度
        "weather_lon": "116.4074",  # 默认北京经度
        "weather_city": "北京",     # 天气组件默认显示的城市名
        "accent_color": "#1a73e8",  # 站点主题色（导航高亮、按钮、链接等）
        # ===== 主题美化系统 =====
        "theme_mode": "system",     # 前台默认主题：light / dark / system（跟随系统）
        "theme_radius": "md",       # 圆角风格：sm / md / lg
        "theme_font": "md",         # 字号：sm / md / lg
        "nav_style": "light",       # 前台导航栏样式：light / dark
        "custom_css": "",           # 自定义 CSS（前后台都注入，可写覆盖样式）
    }
    for k, v in defaults.items():
        if not Setting.query.filter_by(key=k).first():
            db.session.add(Setting(key=k, value=v))
    db.session.commit()


def _migrate_user_table():
    """旧库的 user 表可能缺少 must_change_password 列，这里做轻量迁移（SQLite 加列）。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "user" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("user")]
        if "must_change_password" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text(
                    "ALTER TABLE user ADD COLUMN must_change_password BOOLEAN DEFAULT 1"
                ))
            print("已迁移 user 表：新增 must_change_password 列")


def _migrate_post_table():
    """旧库的 post 表可能缺少 author_id / series_id 列，轻量加列。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "post" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("post")]
        specs = {"author_id": "INTEGER", "series_id": "INTEGER"}
        need = [c for c in specs if c not in cols]
        if need:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                for c in need:
                    conn.execute(db.text(f"ALTER TABLE post ADD COLUMN {c} {specs[c]}"))
            print(f"已迁移 post 表：新增 {', '.join(need)} 列")


def _migrate_comment_table():
    """旧库的 comment 表补 ip / region / device / parent_id / reply_to / likes 列。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "comment" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("comment")]
        specs = {
            "ip": "VARCHAR(64) DEFAULT ''",
            "region": "VARCHAR(64) DEFAULT ''",
            "device": "VARCHAR(120) DEFAULT ''",
            "parent_id": "INTEGER",
            "reply_to": "VARCHAR(80) DEFAULT ''",
            "likes": "INTEGER DEFAULT 0",
        }
        need = [c for c in specs if c not in cols]
        if need:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                for c in need:
                    conn.execute(db.text(f"ALTER TABLE comment ADD COLUMN {c} {specs[c]}"))
            print(f"已迁移 comment 表：新增 {', '.join(need)} 列")


def _migrate_friendlink_table():
    """旧库的 friend_link 表补 rss_url 列（友链 RSS 聚合用）。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "friend_link" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("friend_link")]
        if "rss_url" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text("ALTER TABLE friend_link ADD COLUMN rss_url VARCHAR(300) DEFAULT ''"))
            print("已迁移 friend_link 表：新增 rss_url 列")


def _ensure_super_admin(app):
    """确保「全局唯一」的超级管理员存在（按角色判断，不按用户名）。

    设计要点：
    - 超级管理员全局只能有 1 个，不可创建第二个、不可把其他人升为超级管理员。
    - 用 config 的 ADMIN_USERNAME/ADMIN_PASSWORD 作为“兜底恢复账号”：
      仅当「当前没有任何超级管理员」时才用 config 账号新建一个；否则绝不重复创建。
      这样即使超管在 setup 里改了用户名，重启也不会再冒出一个 admin 超管。
    - 首次创建时标记 must_change_password=True，登录后台后强制先设置新用户名/密码。
    """
    from models import ROLE_SUPER as _SUPER
    _migrate_user_table()
    existing = User.query.filter_by(role=_SUPER).first()
    if existing:
        # 已存在超管：若从未设置过账号密码（旧库迁移后该列为空/True），保持待设置
        if existing.must_change_password is None:
            existing.must_change_password = True
            db.session.commit()
            print(f"超级管理员 {existing.username} 需在后台设置新用户名/密码")
        return

    # 没有任何超管：用 config 兜底账号新建唯一一个
    username = app.config["ADMIN_USERNAME"]
    # 若该用户名已被普通/管理员占用，则复用此账号并升为超管，避免重名冲突
    holder = User.query.filter_by(username=username).first()
    if holder:
        holder.role = _SUPER
        holder.must_change_password = True
        holder.set_password(app.config["ADMIN_PASSWORD"])
        u = holder
    else:
        u = User(username=username, role=_SUPER, must_change_password=True)
        u.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(u)
    db.session.commit()
    print(f"已创建唯一超级管理员账号: {username}（首次登录后台需设置新用户名/密码）")


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # 安全启动校验：缺少关键密钥/管理员密码则直接拒绝启动，禁止使用弱默认值。
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "缺少环境变量 SECRET_KEY。请设置随机长字符串后再启动，例如：\n"
            "  export SECRET_KEY=$(python -c 'import secrets;print(secrets.token_hex(32))')"
        )
    if not app.config.get("ADMIN_PASSWORD"):
        raise RuntimeError(
            "缺少环境变量 ADMIN_PASSWORD。请设置初始管理员密码后再启动，例如：\n"
            "  export ADMIN_PASSWORD=$(python -c 'import secrets;print(secrets.token_hex(16))')"
        )

    # 把管理员密码预先哈希，登录时比对哈希值（不存明文）——旧版兼容保留
    app.config["ADMIN_HASH"] = generate_password_hash(app.config["ADMIN_PASSWORD"])

    db.init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # 前后端分离：仅在显式配置了 CORS_ORIGIN 时才允许跨域，且精确匹配来源（默认同源，不开通配）
    @app.after_request
    def add_cors_headers(resp):
        allowed = (app.config.get("CORS_ORIGIN") or "").strip()
        if allowed:
            origin = request.headers.get("Origin")
            origins = [o.strip() for o in allowed.split(",") if o.strip()]
            if origin and origin in origins:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    # 同源校验（CSRF 纵深防御）：对会改变数据的请求，若带 Origin 头则必须同源或已配置的跨域来源。
    # 同源的 fetch/表单提交 Origin 等于本站；跨站攻击请求会被 403 拒绝。
    # 缺失 Origin 头的旧浏览器请求由 SameSite=Lax 的会话 Cookie 兜底防护。
    @app.before_request
    def enforce_same_origin():
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            if origin:
                allowed = {f"{request.scheme}://{request.host}"}
                cfg = (app.config.get("CORS_ORIGIN") or "").strip()
                if cfg:
                    allowed.update(o.strip() for o in cfg.split(",") if o.strip())
                if origin not in allowed:
                    return jsonify({"error": "跨站请求被拒绝"}), 403

    # 跨域预检（OPTIONS）直接放行，否则浏览器 POST 会被拦
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return ("", 204)

    # 首次运行时建表并写入默认设置、创建超级管理员
    with app.app_context():
        db.create_all()
        _migrate_user_table()
        _migrate_post_table()
        _migrate_comment_table()
        _migrate_friendlink_table()
        try:
            import fts
            fts.ensure()
        except Exception as e:
            print("FTS 初始化跳过:", e)
        _ensure_settings(app)
        _ensure_super_admin(app)

    @app.context_processor
    def inject_globals():
        """把每个页面都需要的公共数据注入模板（侧边栏/页脚用）。"""
        cats = Category.query.order_by(Category.id).all()
        tags = Tag.query.order_by(Tag.id).all()
        links = FriendLink.query.order_by(FriendLink.sort).all()
        recent = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).limit(5).all()
        total_posts = Post.query.filter_by(published=True).count()
        total_views = db.session.query(db.func.sum(Post.views)).scalar() or 0
        total_comments = Comment.query.count()
        settings = {s.key: s.value for s in Setting.query.all()}
        # 当前登录用户（后台用 user_id，前台也可用它判断登录态）
        current_user = None
        uid = session.get("user_id")
        if uid:
            current_user = db.session.get(User, uid)
        # 静态资源版本戳（按 mtime 变化）—— 模板里 ?v=... 加在 CSS/JS 链接后，
        # 强制浏览器重新拉取，避免部署新版本后被 ETag/Cache-Control 拦截仍是旧 CSS 导致全文本。
        import os
        try:
            admin_css_v = int(os.path.getmtime(os.path.join(app.static_folder, "admin.css")))
        except OSError:
            admin_css_v = 0
        # 主题美化：把后台设置转成 CSS 变量，注入所有模板（后台 shell + 前台 SSR 页）
        radius_map = {"sm": "8px", "md": "12px", "lg": "20px"}
        font_map = {"sm": "14px", "md": "15px", "lg": "17px"}
        radius = radius_map.get(settings.get("theme_radius", "md"), "12px")
        font_size = font_map.get(settings.get("theme_font", "md"), "15px")
        nav_style = settings.get("nav_style", "light")
        nav_bg = "#1d2025" if nav_style == "dark" else "#ffffff"
        nav_fg = "#e6e8eb" if nav_style == "dark" else "#555555"
        nav_border = "#2a2e35" if nav_style == "dark" else "#ececec"
        theme_css = (
            f"--theme-radius: {radius}; --theme-font-size: {font_size}; "
            f"--nav-bg: {nav_bg}; --nav-fg: {nav_fg}; --nav-border: {nav_border};"
        )
        return dict(
            cats=cats, tags=tags, links=links, recent=recent,
            total_posts=total_posts, total_views=total_views,
            total_comments=total_comments, settings=settings,
            site_title=settings.get("site_title", "我的博客"),
            now_year=datetime.datetime.now().year,
            current_user=current_user,
            admin_css_v=admin_css_v,
            theme_css=theme_css,
            custom_css=settings.get("custom_css", ""),
        )

    @app.cli.command("init-db")
    def init_db_command():
        """初始化数据库：flask init-db"""
        db.create_all()
        _ensure_settings(app)
        _ensure_super_admin(app)
        print("数据库已初始化。")

    @app.cli.command("seed")
    def seed_command():
        """插入示例数据：flask seed（仅首次演示用）"""
        if Post.query.count() > 0:
            print("已有文章，跳过示例数据。")
            return
        cat = Category(name="随笔", slug=make_slug("随笔"))
        db.session.add(cat)
        db.session.flush()
        tag = Tag(name="生活", slug=make_slug("生活"))
        db.session.add(tag)
        db.session.flush()
        post = Post(
            title="欢迎来到我的博客",
            slug=make_slug("欢迎来到我的博客"),
            summary="这是第一篇文章，介绍这个博客都能做什么。",
            content=(
                "## 你好，世界！\n\n"
                "这是用 **Flask + SQLite** 搭建的博客，支持以下能力：\n\n"
                "- 写文章（支持 Markdown 语法）\n"
                "- 分类与标签\n"
                "- 站内搜索\n"
                "- 评论区\n"
                "- 阅读量统计\n"
                "- 天气小组件\n"
                "- 关于本站 / 友情链接\n\n"
                "登录 `/admin` 即可在浏览器里写新文章。"
            ),
            category_id=cat.id, published=True, views=1,
        )
        post.tags.append(tag)
        db.session.add(post)
        db.session.add(FriendLink(name="WorkBuddy", url="https://www.workbuddy.cn", description="你的 AI 助手", sort=0))
        db.session.commit()
        print("已插入示例文章、分类、标签和一条友情链接。")

    return app


# 模块被导入时直接创建应用实例（供 flask run / gunicorn 使用）
app = create_app()


# 直接运行 `python app.py` 仅用于本地开发预览；生产请用 gunicorn 启动（不启用 debug）。
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
