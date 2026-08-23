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
                   Series, Announcement, Guestbook, Subscriber, Notification,
                   AuditLog, RecycleBin, LinkApplication, PostHistory,
                   visible_posts_query)
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
        # v3.1.6：会话版本号列（改密码/踢下线用），旧库自动补
        if "session_version" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text(
                    "ALTER TABLE user ADD COLUMN session_version INTEGER DEFAULT 0"
                ))
            print("已迁移 user 表：新增 session_version 列")
            db.session.remove()
            db.engine.dispose()
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
        specs = {"author_id": "INTEGER", "series_id": "INTEGER", "scheduled_at": "DATETIME",
                  "is_pinned": "BOOLEAN", "seo_description": "TEXT", "seo_keywords": "VARCHAR(300)",
                  "pin_requested": "BOOLEAN",
                  # v3.0.0 新增列
                  "word_count": "INTEGER DEFAULT 0", "reading_minutes": "INTEGER DEFAULT 0",
                  "reward_enabled": "BOOLEAN DEFAULT 0", "reward_qr": "VARCHAR(500) DEFAULT ''",
                  "is_private": "BOOLEAN DEFAULT 0", "in_trash": "BOOLEAN DEFAULT 0",
                  "deleted_at": "DATETIME"}
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
            "is_read": "BOOLEAN DEFAULT 0",
            "approved": "BOOLEAN DEFAULT 1",  # 审核流：1=已通过显示，0=待审核
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


def _migrate_guestbook_table():
    """旧库的 guestbook 表补 is_read 列（新消息提醒）。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "guestbook" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("guestbook")]
        if "is_read" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text("ALTER TABLE guestbook ADD COLUMN is_read BOOLEAN DEFAULT 0"))
            print("已迁移 guestbook 表：新增 is_read 列")


def _migrate_subscriber_table():
    """旧库的 subscriber 表补 unsub_token 列（邮件退订用）。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "subscriber" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("subscriber")]
        if "unsub_token" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text("ALTER TABLE subscriber ADD COLUMN unsub_token VARCHAR(64) DEFAULT ''"))
            print("已迁移 subscriber 表：新增 unsub_token 列")


def _migrate_audit_log_table():
    """v3.1.0：audit_log 表补 success 列（登录成功/失败区分）。"""
    from sqlalchemy import inspect
    ins = inspect(db.engine)
    if "audit_log" in ins.get_table_names():
        cols = [c["name"] for c in ins.get_columns("audit_log")]
        if "success" not in cols:
            db.session.remove()
            db.engine.dispose()
            with db.engine.begin() as conn:
                conn.execute(db.text("ALTER TABLE audit_log ADD COLUMN success BOOLEAN DEFAULT 1"))
            print("已迁移 audit_log 表：新增 success 列")


def _migrate_new_tables_v3():
    """v3.0.0 新增表：若数据库中尚不存在这些表，则建表（幂等，可重复调用）。

    新增：audit_log（审计日志）、recycle_bin（回收站）、link_application（友链申请）、
    post_history（文章版本历史）。旧库升级时自动补建，无需手动 SQL。
    """
    from sqlalchemy import inspect
    from models import (AuditLog, RecycleBin, LinkApplication, PostHistory)
    ins = inspect(db.engine)
    existing = set(ins.get_table_names())
    new_tables = [AuditLog, RecycleBin, LinkApplication, PostHistory]
    need = [t for t in new_tables if t.__tablename__ not in existing]
    if need:
        try:
            db.create_all()
            print("已迁移：新建 v3.0.0 数据表（" + ", ".join(t.__tablename__ for t in need) + "）")
        except Exception as e:
            print("v3.0.0 建表失败（可忽略，下次启动重试）:", e)


def count_unique_view(post_id, ip):
    """阅读量防刷（v2.8.0）。

    同一访客 IP 在 24 小时内对同一篇文章只累加一次真实阅读量（Post.views），
    但保留 ReadLog 的「反复阅读」累计（用于统计深度阅读，不污染公开阅读数）。
    返回 True 表示本次应 +1（新访客 / 超 24h 未读），False 表示已计过、不重复加。

    使用说明：调用方在文章详情页先调用本函数，返回 True 时再 p.views += 1。
    """
    from models import ReadLog, db as _db
    import datetime as _dt
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=24)
    recent = (ReadLog.query.filter_by(post_id=post_id, ip=ip)
              .filter(ReadLog.updated_at >= cutoff).first())
    if recent:
        return False
    # 记录/更新去重计数
    rec = ReadLog.query.filter_by(post_id=post_id, ip=ip).first()
    if rec:
        rec.read_count += 1
        rec.updated_at = _dt.datetime.utcnow()
    else:
        rec = ReadLog(post_id=post_id, ip=ip, read_count=1)
        _db.session.add(rec)
    _db.session.commit()
    return True


def maybe_convert_webp(path, max_side=1600):
    """上传图片若体积较大则转 WebP 以省流量（v2.8.0）。

    需要 Pillow；未安装（零依赖降级）则直接返回原路径，不做转换。
    转换成功会原地替换文件为 .webp 并返回新路径。失败/非图片也安全回退原路径。
    """
    try:
        from PIL import Image
        import os as _os
        if not _os.path.exists(path):
            return path
        # 仅处理常见位图；gif 动图不转（会丢帧）
        ext = _os.path.splitext(path)[1].lower()
        if ext in (".webp", ".gif"):
            return path
        im = Image.open(path)
        im = im.convert("RGB")
        # 超长边等比缩放，避免超大图直接转 WebP 仍占用过多存储
        if max(im.size) > max_side:
            ratio = max_side / max(im.size)
            im = im.resize((int(im.size[0] * ratio), int(im.size[1] * ratio)),
                           Image.LANCZOS)
        new_path = _os.path.splitext(path)[0] + ".webp"
        im.save(new_path, "WEBP", quality=82)
        # 释放原文件，避免上传目录堆积
        try:
            if _os.path.abspath(new_path) != _os.path.abspath(path):
                _os.remove(path)
        except Exception:
            pass
        return new_path
    except Exception:
        return path


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
        # 后台静态资源（admin.css/script.js）禁用强缓存：微信 X5 内核可能忽略 ?v 把旧 CSS 强缓存住，
        # 导致深色主题等前端更新永远不生效（v2.6.14 修复）。no-cache 让微信每次向服务器验证，
        # 文件变了（ETag/mtime）即返回新内容。前台 Vue 资源由 Nginx 服务，不经过此处。
        if request.path.endswith("/static/admin.css") or request.path.endswith("/static/script.js"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    # v3.1.6：安全响应头（X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy）
    if app.config.get("SECURITY_HEADERS", True):
        from security import security_headers as _sec_headers
        _orig_after = app.after_request_funcs.get(None)
        @app.after_request
        def add_security_headers(resp):
            _sec_headers(resp)
            return resp

    # 同源校验（CSRF 纵深防御）：对会改变数据的请求，若带 Origin 头则必须同源或已配置的跨域来源。
    # 同源的 fetch/表单提交 Origin 等于本站；跨站攻击请求会被 403 拒绝。
    # 缺失 Origin 头的旧浏览器请求由 SameSite=Lax 的会话 Cookie 兜底防护。
    # v3.1.6 增强：再叠加「CSRF Token 双重校验」，见 csrf_protect。
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
        return _csrf_protect()

    # v3.1.6：CSRF Token 校验（中优）——对所有会改变数据的请求，要求携带会话绑定的 token。
    # 豁免：API 密钥鉴权类（webhook/deploy）不走会话、验证码接口自身、以及无会话的无状态接口。
    # 校验不通过返回 403，前端统一走 apiPost 拦截重新登录或刷新页面获取新 token。
    def _csrf_protect():
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        # 豁免清单（这些接口不依赖会话或自带独立鉴权）：
        exempt = ("/api/webhook/deploy", "/api/captcha", "/api/captcha/verify")
        path = request.path
        if any(path.startswith(e) for e in exempt):
            return None
        # 严格模式：对「服务端表单渲染的后台/前台页面」与「Vue API」都要求 token。
        # 无会话用户（游客点赞/评论未登录场景）也要求 token——前端每次会话都有 token。
        from utils import check_csrf_token
        tok = ""
        if request.is_json:
            body = request.get_json(silent=True) or {}
            tok = body.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        else:
            tok = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        if not check_csrf_token(tok):
            # 所有状态变更请求都必须携带有效 token（无会话也不豁免——token 在渲染页面/GET /api/csrf 时已生成）。
            # 例外：仅当会话确实从未生成过 token（如纯 API 客户端绕过页面流程）时，才放行并自动生成，
            # 避免影响已被外部系统调用的公开 POST 接口（如 RSS 阅读器触发之类的旧场景）。
            return jsonify({"error": "CSRF 校验失败，请刷新页面后重试"}), 403
        return None

    # 跨域预检（OPTIONS）直接放行，否则浏览器 POST 会被拦
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return ("", 204)

    # v3.1.6：会话版本校验——改密码 / 超管踢下线后 session_version +1，
    # 旧会话里存的版本号过期即失效（实现「改密码销毁全部旧会话」+「踢下线」）。
    @app.before_request
    def enforce_session_version():
        uid = session.get("user_id")
        if not uid:
            return None
        u = db.session.get(User, uid)
        if not u:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "账号不存在，请重新登录"}), 401
            return redirect("/login?next=" + request.path)
        sess_ver = session.get("session_version", 0)
        if sess_ver != (u.session_version or 0):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "登录已失效（密码已更改或已被管理员踢下线），请重新登录"}), 401
            return redirect("/login?next=" + request.path)
        return None

    # v3.1.6：闲置会话超时（可选）——SESSION_IDLE_MINUTES 分钟内无活动则清除登录态。
    # 对「已登录且超时」的请求返回 401 JSON 或跳登录页，前端收到后自动重新登录。
    @app.before_request
    def enforce_session_idle_timeout():
        idle_min = app.config.get("SESSION_IDLE_MINUTES") or 0
        if idle_min <= 0:
            return None
        uid = session.get("user_id")
        if not uid:
            return None
        last = session.get("last_active")
        now = datetime.datetime.utcnow()
        if last:
            try:
                last_dt = datetime.datetime.fromisoformat(last)
            except Exception:
                last_dt = None
            if last_dt and (now - last_dt).total_seconds() > idle_min * 60:
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "会话已超时，请重新登录"}), 401
                return redirect("/login?next=" + request.path)
        session["last_active"] = now.isoformat()
        return None

    # 首次运行时建表并写入默认设置、创建超级管理员
    with app.app_context():
        db.create_all()
        _migrate_user_table()
        _migrate_post_table()
        _migrate_comment_table()
        _migrate_friendlink_table()
        _migrate_guestbook_table()
        _migrate_subscriber_table()
        _migrate_audit_log_table()
        _migrate_new_tables_v3()
        try:
            import fts
            fts.ensure()
        except Exception as e:
            print("FTS 初始化跳过:", e)
        _ensure_settings(app)
        _ensure_super_admin(app)

    # v3.1.6：确保每个请求都生成会话 CSRF Token（未登录访客也有，用于游客提交表单/API）
    def _csrf_generate():
        from utils import generate_csrf_token
        try:
            generate_csrf_token()
        except Exception:
            pass

    @app.context_processor
    def inject_globals():
        """把每个页面都需要的公共数据注入模板（侧边栏/页脚用）。"""
        cats = Category.query.order_by(Category.id).all()
        tags = Tag.query.order_by(Tag.id).all()
        links = FriendLink.query.order_by(FriendLink.sort).all()
        recent = visible_posts_query().order_by(Post.created_at.desc()).limit(5).all()
        total_posts = visible_posts_query().count()
        total_views = db.session.query(db.func.sum(Post.views)).scalar() or 0
        total_comments = Comment.query.count()
        settings = {s.key: s.value for s in Setting.query.all()}
        # 当前登录用户（后台用 user_id，前台也可用它判断登录态）
        current_user = None
        uid = session.get("user_id")
        if uid:
            current_user = db.session.get(User, uid)
        # 静态资源版本戳：改用 APP_VERSION（每次发版必变），模板里 ?v=... 加在 CSS/JS 链接后。
        # 不用 mtime：宝塔 update.sh 用 rsync -a 保留 mtime，可能导致 ?v 不变；
        # 且微信 X5 内核对带 query 的静态资源可能强缓存旧文件，故双保险（见下方 no-cache 响应头）。
        try:
            import config as _cfg_ver
            admin_css_v = _cfg_ver.APP_VERSION
        except Exception:
            admin_css_v = "0"
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
        # v3.1.6：CSRF Token 注入模板（表单页用 {{ csrf_input() }} 生成隐藏域）
        from utils import csrf_input as _csrf_input
        from flask import session as _session
        _csrf_generate()
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
            csrf_input=_csrf_input,
            csrf_token=_session.get("csrf_token", ""),
        )

    # ---------- 定时发布后台线程（v2.7.0）----------
    # 守护线程每 60s 扫描「已设 scheduled_at 且到点、但尚未 published」的文章，
    # 翻成 published 并触发新文章推送（Telegram/企业微信）+ 邮件群发订阅者。
    # 线程内独立 app_context，避免与请求上下文冲突；所有异常静默，不影响主流程。
    def _scheduler_loop():
        import time as _time
        while True:
            _time.sleep(60)
            try:
                with app.app_context():
                    now = datetime.datetime.utcnow()
                    due = Post.query.filter(
                        Post.scheduled_at.isnot(None),
                        Post.scheduled_at <= now,
                        Post.published != True,
                    ).all()
                    for p in due:
                        p.published = True
                        p.scheduled_at = None  # 发布后清空，避免重复触发
                        db.session.commit()
                        try:
                            import notify as _notify
                            _notify.notify_new_post(p, app.config.get("SITE_URL", ""))
                        except Exception:
                            pass
                        try:
                            import mail_notify as _mail
                            _mail.notify_subscribers_async(p)
                        except Exception:
                            pass
                    if due:
                        print(f"[定时发布] 已自动发布 {len(due)} 篇到点文章")
            except Exception as e:
                # 单轮异常不致命，下一轮继续；打印便于排查
                print("[定时发布线程] 异常（已忽略，继续下一轮）:", e)

    import threading as _threading
    _sched_thread = _threading.Thread(target=_scheduler_loop, name="scheduled-publish", daemon=True)
    _sched_thread.start()

    return app
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
