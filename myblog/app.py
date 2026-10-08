"""应用入口。
- create_app(): 创建并配置 Flask 应用
- app = create_app(): 模块加载时直接创建实例，方便 `flask run` / gunicorn 启动
"""
import os
import datetime
import logging

from flask import (Flask, render_template, request, session, jsonify,
                   redirect, url_for)

from models import (db, Post, Category, Tag, Comment, FriendLink, Setting, User,
                   ROLE_SUPER, Moment, MomentComment, SocialAccount,
                   Series, Announcement, Guestbook, Subscriber, Notification,
                   AuditLog, RecycleBin, LinkApplication, PostHistory,
                   visible_posts_query)
from utils import make_slug, safe_redirect
from routes import main_bp
from admin import admin_bp
from api import api_bp
from mcp_diag import mcp_bp  # v3.10.0：只读诊断 MCP（端点 /mcp）
from mcp_write import mcp_write_bp  # v3.12.2：写能力 MCP（端点 /mcp-write，未配置 MCP_WRITE_TOKEN 时自动关闭）
from _time import utcnow
import contextlib

# v3.11.0：Flask-Migrate（可选依赖）—— 数据库迁移工具，便于未来 schema 演进。
# 未安装时静默跳过（降级范式：绝不因缺依赖导致应用无法启动）。
try:
    from flask_migrate import Migrate
except Exception:
    Migrate = None


# v3.23.0：模块级 logger。全仓 print( 分批迁移到 logger，第一批是 app.py 自身
# （启动/迁移/定时发布/播种的诊断信息）。格式化与级别由 logging_setup 统一配置。
logger = logging.getLogger(__name__)

_PRAGMAS_INSTALLED = False


def _install_sqlite_pragmas():
    """v3.9.1：给每个新建的 SQLite 连接设置 WAL / busy_timeout / synchronous。

    背景：SQLite 默认是 rollback journal + 无等待（撞锁即报 "database is locked"）。
    本博客每位访客都会触发写操作（阅读量/统计埋点），gunicorn 多 worker 并发下
    读写互相阻塞，偶发 500。WAL 让「读不阻塞写、写不阻塞读」，busy_timeout 让
    写并发自动排队等待 5 秒而不是立刻报错，synchronous=NORMAL 是 WAL 下的常规折中。

    注意：
    - PRAGMA 是**连接级**的，故挂 SQLAlchemy 的 connect 事件逐个设置（只设一次不够）。
    - 非 SQLite（Postgres/MySQL）自动跳过；内存库（:memory:）不支持 WAL，异常静默忽略。
    - 幂等：模块级开关保证多次 create_app（测试常见）只注册一次监听。
    - 副作用：数据库目录会多出 blog.db-wal / blog.db-shm 两个文件（正常，勿手删），
      备份必须用一致性快照（见 backup.py 与 update.sh 的配套改动）。
    """
    global _PRAGMAS_INSTALLED
    if _PRAGMAS_INSTALLED:
        return
    try:
        import sqlite3
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            if not isinstance(dbapi_conn, sqlite3.Connection):
                return
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass  # 内存库/只读库不支持 WAL，忽略即可
            finally:
                with contextlib.suppress(Exception):
                    cur.close()

        _PRAGMAS_INSTALLED = True
    except Exception as e:
        logger.warning("SQLite PRAGMA 初始化跳过: %s", e)


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
        # ===== v4.1.0 前台「自定义外部入口」（v4.0.0 单条 → 多条） =====
        # 旧四件套仍写入，是为了保证**老配置可读**（迁移会读它们）；
        # 真正被前台使用的是 nav_entries（JSON 数组），由下方迁移即时生成。
        # ⚠️ 地址**必须**是 http/https 绝对地址 —— 前台用 :href 直接绑定，
        #    其它 scheme（javascript: 等）会变成存储型 XSS（见 utils.is_http_url）。
        "entry_enabled": "true",
        "entry_label": "百宝箱",
        "entry_url": "https://box.llhhy.cn",
        "entry_icon": "🧰",
    }
    for k, v in defaults.items():
        if not Setting.query.filter_by(key=k).first():
            db.session.add(Setting(key=k, value=v))
    db.session.commit()

    # v4.1.0：把 v4.0.0 的四件套迁成 nav_entries 数组（只迁一次，幂等）。
    # 生产不用迁移脚本 —— 这是**数据**搬运不是表结构变更，且必须对用户透明：
    # 升级后打开后台，之前配的那个入口已经在列表里了，不需要手工补。
    try:
        import nav_entries
        nav_entries.migrate_legacy()
    except Exception as e:  # noqa: BLE001  迁移失败不能拖垮启动
        logger.warning("遗留外部入口迁移失败（不影响启动）: %s", e)


def _seed_default_badges():
    """播种默认勋章（幂等；失败不得拖垮启动）。

    v3.24.0：原先挂在 `_migrate_new_tables_v3()` 里，随 9 个 `_migrate_*` 一起退役，
    这里单独拆出来 —— 播种是**数据**初始化，不是表结构，不能跟着一起删。

    ⚠️ 必须**无条件**调用：不能写成「只在刚建好新表时才播种」。因为 `db.create_all()`
    先跑过，表在进本函数前就已存在，加那个判断会导致勋章永远播不进去 —— 表现为
    「勋章表建好了但一条数据没有，读者永远拿不到勋章」的静默降级。
    """
    try:
        from gamify import seed_badges
        seed_badges()
    except Exception as e:  # noqa: BLE001  播种失败不能拖垮启动（下次启动会重试）
        logger.warning("默认勋章播种失败（可忽略，下次启动重试）: %s", e)


def count_unique_view(post_id, ip):
    """阅读量防刷（v2.8.0）。

    同一访客 IP 在 24 小时内对同一篇文章只累加一次真实阅读量（Post.views），
    但保留 ReadLog 的「反复阅读」累计（用于统计深度阅读，不污染公开阅读数）。
    返回 True 表示本次应 +1（新访客 / 超 24h 未读），False 表示已计过、不重复加。

    使用说明：调用方在文章详情页先调用本函数，返回 True 时再 p.views += 1。
    """
    from models import ReadLog, db as _db
    import datetime as _dt
    cutoff = utcnow() - _dt.timedelta(hours=24)
    recent = (ReadLog.query.filter_by(post_id=post_id, ip=ip)
              .filter(ReadLog.updated_at >= cutoff).first())
    if recent:
        return False
    # 记录/更新去重计数
    rec = ReadLog.query.filter_by(post_id=post_id, ip=ip).first()
    if rec:
        rec.read_count += 1
        rec.updated_at = utcnow()
    else:
        rec = ReadLog(post_id=post_id, ip=ip, read_count=1)
        _db.session.add(rec)
    _db.session.commit()
    return True


def maybe_convert_webp(path, max_side=1600):
    """上传图片若体积较大则转 WebP 以省流量（v2.8.0）。

    v3.17.0：若 Pillow 带 AVIF 支持，额外生成同名 .avif 旁路文件（体积通常再省
    20%~40%），前端以 <picture> 优先 AVIF、回退 WebP；avif 生成失败静默跳过，
    不影响主流程与返回值。返回的仍是 .webp 路径（兼容既有调用方）。

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
        base = _os.path.splitext(path)[0]
        new_path = base + ".webp"
        im.save(new_path, "WEBP", quality=82)
        # v3.17.0：AVIF 旁路（Pillow 未编译 AVIF 时自动跳过，零新增依赖）
        try:
            from PIL import features as _feat
            if _feat.check("avif"):
                im.save(base + ".avif", "AVIF", quality=62)
        except Exception:
            pass
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
    existing = User.query.filter_by(role=_SUPER).first()
    if existing:
        # 已存在超管：若从未设置过账号密码（旧库迁移后该列为空/True），保持待设置
        if existing.must_change_password is None:
            existing.must_change_password = True
            db.session.commit()
            logger.info("超级管理员 %s 需在后台设置新用户名/密码", existing.username)
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
    logger.info("已创建唯一超级管理员账号: %s（首次登录后台需设置新用户名/密码）", username)


_HTTP_ERROR_TEXT = {
    400: "请求参数有误",
    403: "没有访问权限",
    404: "页面或资源不存在",
    405: "请求方法不被允许",
    422: "请求内容无法处理",
    410: "该页面已由前端 SPA 渲染，服务端不再输出 HTML",
    500: "服务器内部错误",
}


def _http_error_text(code):
    """把 HTTP 状态码翻成面向用户的中文短句（错误页与 JSON 信封共用）。"""
    return _HTTP_ERROR_TEXT.get(code, "请求失败")


def _is_json_client():
    """当前请求是否应返回 JSON 错误而非 HTML 错误页。

    - `/api/*` 与 MCP 端点（`/mcp`、`/mcp-write`）：客户端本来就是 JSON 协议；
    - 其他路径仅在显式只接受 JSON（Accept 含 application/json 且不含 text/html）时。
    """
    try:
        path = request.path or ""
    except Exception:
        return False
    if path.startswith("/api/") or path in ("/mcp", "/mcp-write"):
        return True
    acc = (request.headers.get("Accept") or "").lower()
    return "application/json" in acc and "text/html" not in acc


def claim_scheduled_post(post_id):
    """原子认领一篇到点文章：跨进程、跨线程**只有一个**调用者能拿到 True。

    背景：gunicorn 开 N 个 worker，而 `create_app()` 给每个 worker 各起一条调度线程，
    于是同一篇定时文章会被 N 条线程同时扫到。原实现是「先查（published != True）
    后改（赋 True 再 commit）」，两条线程都能通过查询，结果是同一篇文章被发布 N 次、
    并触发 N 份 Telegram/邮件/新文推送 —— 对订阅者是实打实的 N 倍骚扰。

    做法：把「判断 + 修改」合并成**一条 UPDATE**，用 `WHERE` 里的未发布条件做认领。
    SQLite 的写操作本身串行，`rowcount == 1` 即抢到，其余为 0 直接跳过。

    为什么不选「选主 + 心跳」（只让一个 worker 跑调度）：
    `tasks.py` 的锁过期是 `LOCK_STALE = 3600`，若持锁进程被杀，要等最多 1 小时才有人
    接管 —— 那等于定时发布停摆一小时，是新的可用性故障。原子认领没有持锁者概念，
    因而没有这个失效窗口；代价是 N 条线程仍会各自扫一遍（一次带索引的小查询，可忽略）。
    """
    res = db.session.execute(
        db.text("UPDATE post SET published = 1, scheduled_at = NULL "
                "WHERE id = :id AND COALESCE(published, 0) != 1"),
        {"id": post_id})
    db.session.commit()
    return res.rowcount == 1


def _validate_required_env(app, migrate_only):
    """安全启动校验：缺少关键密钥/管理员密码则直接拒绝启动，禁止使用弱默认值。

    迁移模式（`migrate_only`）下不需要管理员凭据：见 create_app 的 BLOG_MIGRATE_ONLY 说明。"""
    # 安全启动校验：缺少关键密钥/管理员密码则直接拒绝启动，禁止使用弱默认值。
    if migrate_only:
        # 仅用于命令行迁移，不会处理任何请求/会话；给一次性随机值即可，绝不落盘。
        if not app.config.get("SECRET_KEY"):
            app.config["SECRET_KEY"] = os.urandom(24).hex()
    elif not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "缺少环境变量 SECRET_KEY。请设置随机长字符串后再启动，例如：\n"
            "  export SECRET_KEY=$(python -c 'import secrets;print(secrets.token_hex(32))')"
        )
    if not migrate_only and not app.config.get("ADMIN_PASSWORD"):
        raise RuntimeError(
            "缺少环境变量 ADMIN_PASSWORD。请设置初始管理员密码后再启动，例如：\n"
            "  export ADMIN_PASSWORD=$(python -c 'import secrets;print(secrets.token_hex(16))')"
        )

def _setup_core(app):
    """装配核心：结构化日志 → SQLite PRAGMA → db/Migrate → 蓝图 → Jinja 过滤器。

    必须在 `_bootstrap_database()` 之前（`db.init_app` 要先于任何建表/查询）。"""
    # v3.23.0：结构化日志 + request_id（必须早于任何 logger 使用——否则迁移/启动
    # 阶段的日志拿不到 rid，且 root 无 handler 时 INFO 级会被直接丢弃）。
    import logging_setup
    logging_setup.init_request_id(app)
    logging_setup.setup_logging(app)

    # v3.9.1：SQLite WAL + busy_timeout（必须在建连/建表之前装好监听）
    _install_sqlite_pragmas()
    db.init_app(app)
    # v3.11.0：登记 Flask-Migrate。
    # v3.24.0 起 **Alembic 就是唯一的结构变更路径**：部署脚本（update.sh 的
    # `apply_db_migrations`）会在覆盖代码后、重启前跑 `flask db upgrade`；
    # 原先 9 个 `_migrate_*` 启动自愈函数已退役（改为迁移 `d4a7f08c2e91` 兜底补列）。
    # `db.create_all()` 仍然保留，但它只负责「建缺失的表」（新建库 / 补齐新表），
    # **不会**给已有表加列 —— 加列一律写迁移。
    # directory 显式指到本文件同级的 migrations/，使 `flask db` 在任意 cwd 下
    # 都能定位（部署后该目录随后端包落到运行目录，与开发态一致）。
    if Migrate is not None:
        _migrate_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "migrations"
        )
        Migrate(app, db, directory=_migrate_dir)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(mcp_bp)  # v3.10.0：/mcp（只读诊断，未配置 MCP_AUTH_TOKEN 时自动关闭）
    app.register_blueprint(mcp_write_bp)  # v3.12.2：/mcp-write（写能力，未配置 MCP_WRITE_TOKEN 时自动关闭）

    # v3.10.5：北京时间 Jinja 过滤器（后台模板用 {{ dt | bj('fmt') }} 显示北京时间）
    from utils import fmt_bj
    app.jinja_env.filters["bj"] = fmt_bj

def _register_request_hooks(app):
    """注册 after/before_request 钩子。

    ⚠️ Flask 的 `before_request` **按注册顺序执行**，因此本函数内部必须保持原
    文本顺序：同源校验 → 预检放行 → 会话版本 → 闲置超时 → 2FA 闸门。"""
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
        # - webhook/deploy、captcha：自带独立鉴权/验证码，不走会话
        # - /api/stats/read|visit|search：匿名埋点信标（SPA 每次路由变化/阅读即上报），
        #   不携带任何特权状态、仅累加计数，跨站 POST 至多污染统计，无安全风险，故豁免 CSRF，
        #   否则匿名访客首屏上报会被 403 拦截（既报控制台错误又丢失访问统计）。
        # /mcp 与 /mcp-write：自带 Bearer Token 鉴权（**非会话**），MCP 客户端没有 Cookie
        #   也拿不到 CSRF token，若不豁免则合法调用会被 403 拦死（R115 审计 修复：
        #   此前只豁免了 /mcp，导致 /mcp-write 实际不可用）。
        #   ⚠️ 用精确匹配而非 startswith 粗放：写成 "/mcp" 会把 "/mcp-write" 之外的
        #   未来子路径一并放行；"/mcp-write" 单独列出，两端都不含通配。
        exempt = ("/api/webhook/deploy", "/api/captcha", "/api/captcha/verify",
                  "/api/stats/read", "/api/stats/visit", "/api/stats/search",
                  "/mcp", "/mcp-write")
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
    @app.before_request   # noqa: RET503 —— 隐式返回 None = 放行（Flask 钩子语义）
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
            return redirect(safe_redirect(url_for("main.login", next=request.path)))
        sess_ver = session.get("session_version", 0)
        if sess_ver != (u.session_version or 0):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "登录已失效（密码已更改或已被管理员踢下线），请重新登录"}), 401
            return redirect(safe_redirect(url_for("main.login", next=request.path)))
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
        now = utcnow()
        if last:
            try:
                last_dt = datetime.datetime.fromisoformat(last)
            except Exception:
                last_dt = None
            if last_dt and (now - last_dt).total_seconds() > idle_min * 60:
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "会话已超时，请重新登录"}), 401
                return redirect(safe_redirect(url_for("main.login", next=request.path)))
        session["last_active"] = now.isoformat()
        return None

    # v3.21.2 审计（R93 复审）：2FA 必须是**会话级闸门**，不能只在某一条登录路径里判。
    # 此前只有 `/api/auth/login` 检查了第二因素，而 `POST /login`（routes.py）、
    # `POST /admin/login`（admin/auth.py）与 OAuth 回调（api/auth.py）都是直接写
    # `session["user_id"]` 放行；所有权限装饰器又只看 `user_id` —— 结果是用密码
    # 走前台/后台登录框就能拿到完整后台（含超管），第二因素形同装饰。
    # 收口在这里而不是补到各条登录路径：闸门与 `enforce_session_version` 同层，
    # 今后**新增**任何登录入口都自动被覆盖，不会再一次「漏了一条」。
    # 放行清单只放「第二因素流程自身」与只读的身份探针：
    # - `/twofa`：SSR 挑战页；`/api/auth/2fa/verify`：SPA 挑战接口
    # - `/api/auth/2fa/status`：前端要据此决定要不要弹挑战框（只读，不改状态）
    # - `/api/auth/logout`、`/logout`：必须允许「放弃并退出」
    # - `/api/auth/me`、`/api/csrf`：无特权，前端拿它们判断当前会话身份
    # ⚠️ 刻意**不放** `/api/auth/2fa/enroll|confirm|disable` —— 放行就等于让一个
    # 只过了密码的会话去改动第二因素本身（v3.21.2 审计 C2 的同一条路径）。
    _TWOFA_ALLOW = ("/twofa", "/static/", "/favicon.ico",
                    "/api/auth/2fa/verify", "/api/auth/2fa/status",
                    "/api/auth/logout", "/api/auth/me", "/api/csrf", "/logout")

    @app.before_request
    def enforce_twofa():
        # v3.25.8：改由 `flag_bool` 取值（DB → 环境变量 → 默认 false），
        # 后台「系统设置」可开关、不必改服务器。**这里每请求多一次 Setting
        # 单行查询** —— SQLite 主键命中微秒级，换来「2FA 能从后台开」；
        # 反过来做（启动时读一次）是 v3.21.0 的老问题：开关在代码里，却只能
        # 改服务器 + 重启，于是它从上线起就没被启用过。
        from utils import flag_bool
        if not flag_bool("twofa_enabled", "TWOFA_ENABLED", False):
            return None                              # 全局开关关 → 整条闸门休眠
        uid = session.get("user_id")
        if not uid or session.get("twofa_ok"):
            return None
        path = request.path
        if any(path == p or path.startswith(p) for p in _TWOFA_ALLOW):
            return None
        import twofa as _twofa
        if not _twofa.is_active(uid):
            return None                              # 该账号未绑定第二因素：不改变原有行为
        if path.startswith("/api/"):
            return jsonify({"error": "twofa_required", "twofa_required": True}), 401
        return redirect(url_for("main.twofa_challenge", next=path))

def _bootstrap_database(app, migrate_only):
    """首次运行自举：建缺失的表 → 播种勋章 → FTS → 默认设置 → 超管 → 插件。

    `migrate_only` 时整块跳过（迁移命令不得产生任何业务副作用）。"""
    # 首次运行时建表并写入默认设置、创建超级管理员
    if migrate_only:
        logger.info("迁移模式（BLOG_MIGRATE_ONLY=1）：跳过建表 / 超管兜底 / 设置播种 / FTS / 插件加载")
    else:
        with app.app_context():
            db.create_all()
            _seed_default_badges()
            try:
                import fts
                fts.ensure()
            except Exception as e:
                logger.warning("FTS 初始化跳过: %s", e)
            _ensure_settings(app)
            _ensure_super_admin(app)

            # v3.9.0：插件系统（M0）— 核心表/设置/超管就绪后加载；单插件崩溃不拖垮博客
            try:
                from plugins import load_plugins
                load_plugins(app, app.config)
            except Exception as e:
                logger.warning("插件系统加载失败（已跳过，不影响博客启动）: %s", e)

def _register_template_context(app):
    """注册模板上下文处理器 `inject_globals` 及其两个私有助手。"""
    # v3.1.6：确保每个请求都生成会话 CSRF Token（未登录访客也有，用于游客提交表单/API）
    def _csrf_generate():
        from utils import generate_csrf_token
        with contextlib.suppress(Exception):
            generate_csrf_token()

    def _safe_css(css):
        r"""v3.17.11（审计 R76-B3）：自定义 CSS 注入 <style> 前转义闭合序列。

        原实现把 custom_css 直接 `| safe` 注入 <style>，内容含 `</style><script>…` 时可
        逃逸出样式上下文执行脚本（当前 custom_css 仅超管可写，属低危，但转义为零成本加固）。
        `<\/style` 在 CSS 中无意义、不会闭合标签，因此不影响任何正常样式。
        """
        if not css:
            return ""
        return str(css).replace("</style", "<\\/style").replace("<!--", "<\\!--")

    @app.context_processor
    def inject_globals():
        """把每个页面都需要的公共数据注入模板（侧边栏 / 页脚用）。

        ## 关于「每次渲染 8 条查询」——审计点名项，评估后**决定不加缓存**

        审计指出本函数每次模板渲染固定 8 条查询。2026-09-23 实测后判断
        **不值得为此引入缓存**，依据有两条：

        1. **影响面比审计描述的小得多**。v3.18.6 SSR 退役后，全项目只剩 2 个模板
           extend `base.html`（`login.html` / `register.html`），其余 45 处渲染
           全是 `admin/*`。也就是说这 8 条查询只发生在**后台页面与登录页**上；
           公开文章页由 nginx 直出 SPA + `/api/*` 返回 JSON，**根本不经过本函数**。
        2. **缓存会引入过期语义，而收益极小**。全项目有 **20 处**直接写 `Setting`
           （admin/settings.py 8 处，其余散落在 9 个文件），没有单一写入收口点；
           要保证一致就得做 TTL + 失效钩子，代价是「改完主题/设置后一段时间内
           页面仍显示旧值」——而换来的只是省掉后台点击时的 8 条小表查询。

        结论：**保持简单**。若日后后台渲染变慢，先量 `EXPLAIN`/耗时再决定，
        不要凭「查询条数多」就上缓存（见 ROADMAP §5.9 A 的同类判断）。
        """
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
        )
        # v3.17.0 修复「深色模式顶部白条」：导航配色（nav_style，独立设置）原先无条件注入
        # :root，与 tokens.css 的 dark 规则同特异性且后定义 → 深色下把导航背景压回白色。
        # v3.17.1：属性选择器**不要加引号**——Jinja autoescape 会把引号转义成 &#34;/&#39;，
        # 致选择器失效（曾渲染为 html:not([data-theme=&#34;dark&#34;])，修复实际不生效）。
        theme_nav_css = (
            "html:not([data-theme=dark]) { "
            f"--nav-bg: {nav_bg}; --nav-fg: {nav_fg}; --nav-border: {nav_border}; }}"
        )
        # v3.1.6：CSRF Token 注入模板（表单页用 {{ csrf_input() }} 生成隐藏域）
        from utils import csrf_input as _csrf_input
        from flask import session as _session
        _csrf_generate()
        return dict(   # noqa: C408 —— 20 键上下文，dict() 更易读且避免手写 20 对引号出错
            cats=cats, tags=tags, links=links, recent=recent,
            total_posts=total_posts, total_views=total_views,
            total_comments=total_comments, settings=settings,
            site_title=settings.get("site_title", "我的博客"),

            current_user=current_user,
            admin_css_v=admin_css_v,
            theme_css=theme_css,
            theme_nav_css=theme_nav_css,
            custom_css=_safe_css(settings.get("custom_css", "")),
            csrf_input=_csrf_input,
            csrf_token=_session.get("csrf_token", ""),
        )

def _register_cli(app):
    """注册 CLI 命令。⚠️ 必须在 `create_app` return 之前注册，否则永不生效。"""
    # v3.18.5：CLI 命令必须在 return 之前注册，否则永不生效（此处曾是 return 之后的死代码）。
    @app.cli.command("seed")
    def seed_command():
        """插入示例数据：flask seed（仅首次演示用）"""
        if Post.query.count() > 0:
            logger.info("已有文章，跳过示例数据。")
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
        logger.info("已插入示例文章、分类、标签和一条友情链接。")

def _register_error_handlers(app):
    """统一错误处理：`/api/` 前缀返回 JSON 信封，其余返回模板页。"""
    # v3.18.5：统一错误处理——/api/ 前缀返回 JSON 信封，其余返回模板页。
    # 修复前全仓 0 个 errorhandler，first_or_404() 对 JSON 客户端返回 Werkzeug
    # 默认 HTML 错误页，前端 resp.json() 解析失败，用户只看到「网络错误」。
    def _render_error_page(code):
        """渲染错误页；模板渲染本身再失败（如上下文处理器因库故障抛错）时兜底纯 HTML。"""
        text = _http_error_text(code)
        tpl = {404: "404.html", 403: "403.html", 500: "500.html"}.get(code, "error.html")
        try:
            return render_template(tpl, error_code=code, error_text=text), code
        except Exception:
            return ("<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
                    "<title>%d</title><h1>%d</h1><p>%s</p>"
                    "<p><a href=\"/\">返回首页</a></p></html>"
                    % (code, code, text)), code

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(410)
    @app.errorhandler(422)
    def _handle_client_error(e):
        code = getattr(e, "code", 500) or 500
        if _is_json_client():
            return jsonify({"error": _http_error_text(code)}), code
        return _render_error_page(code)

    @app.errorhandler(500)
    def _handle_server_error(e):
        # 原始异常交给 Flask 记录（含 traceback），对外只回不透明信息，避免泄露内部细节。
        with contextlib.suppress(Exception):
            app.logger.exception("未捕获的服务端异常: %s", e)
        if _is_json_client():
            return jsonify({"error": "服务器内部错误，请稍后重试"}), 500
        return _render_error_page(500)

def _start_scheduler(app):
    """启动定时发布 + 保留策略清理的守护线程（每 60s 一轮）。"""
    # ---------- 定时发布后台线程（v2.7.0）----------
    # 守护线程每 60s 扫描「已设 scheduled_at 且到点、但尚未 published」的文章，
    # 翻成 published 并触发新文章推送（Telegram/企业微信）+ 邮件群发订阅者。
    # 线程内独立 app_context，避免与请求上下文冲突；所有异常静默，不影响主流程。
    _last_prune_day = [None]   # 闭包内记录上次执行保留策略的日期（每日一次）
    _last_verify_day = [None]  # v3.25.2：备份自动巡检同上（每日一次，刻意分开记日期）
    _last_cert_day = [None]    # v3.25.3：证书到期检查同上

    def _scheduler_loop():
        import time as _time
        while True:
            _time.sleep(60)
            try:
                with app.app_context():
                    now = utcnow()
                    due = Post.query.filter(
                        Post.scheduled_at.isnot(None),
                        Post.scheduled_at <= now,
                        Post.published != True,
                    ).all()
                    for p in due:
                        # 原子认领：N 个 worker 的调度线程同时扫到同一篇时，只有一个能拿到
                        # True，其余跳过 —— 避免重复发布与 N 倍推送（见 claim_scheduled_post）。
                        if not claim_scheduled_post(p.id):
                            continue
                        db.session.refresh(p)   # 让 ORM 看到 published / scheduled_at 的新值
                        # 定时发布是**唯一**没有人工介入的发布路径，漏同步就等于这篇
                        # 永久不在 FTS 索引里（ensure() 只在表空时回填，不会自愈）。
                        import fts as _fts
                        _fts.sync_post_quiet(p)
                        # v3.9.0 M1：文章定时到点发布 → 触发插件事件（订阅者异常已隔离）
                        try:
                            from plugins.signals import emit_post_published
                            emit_post_published(p)
                        except Exception:
                            pass
                        try:
                            import notify as _notify
                            _notify.notify_new_post(p, app.config.get("SITE_URL", ""))
                        except Exception:
                            pass
                        # v3.20.0：新文自动推送（默认关闭，见 seo_push.maybe_auto_push 的说明）
                        try:
                            import seo_push
                            seo_push.maybe_auto_push(p)
                        except Exception:  # noqa: BLE001, S110  (自动推送失败绝不影响发布主流程)
                            pass
                        try:
                            import mail_notify as _mail
                            _mail.notify_subscribers_async(p)
                        except Exception:
                            pass
                    if due:
                        logger.info("[定时发布] 已自动发布 %d 篇到点文章", len(due))
                    # v3.24.0：保留策略每日清理一次（point_log 2 年 / reader_badge 随
                    # reader / reader 永久保留）。复用定时发布线程，失败只记日志。
                    today = utcnow().date()
                    if _last_prune_day[0] != today:
                        _last_prune_day[0] = today
                        try:
                            import gamify as _gamify
                            n = _gamify.prune_retention()
                            if n["point_log"] or n["reader_badge"]:
                                logger.info("[保留策略] 清理 point_log=%d reader_badge=%d",
                                            n["point_log"], n["reader_badge"])
                        except Exception as e:  # noqa: BLE001  清理失败绝不影响定时发布主流程
                            logger.warning("[保留策略] 清理失败（已忽略，下一日重试）: %s", e)
                    # v3.25.2：备份自动巡检（每日一次，与保留策略同一轮）。
                    # **为什么必须有**：`backup verify` 一直只能手动跑，于是「备份能不能
                    # 恢复」这个属性在真出事之前**永远是未知的** —— 而磁盘故障那天正是
                    # 最需要备份的一天。零新表（结果落 data/backup_verify.json）。
                    # 失败**必须响**：logger.error + 状态文件标红 + 后台页显示，
                    # 静默的巡检等于没做。
                    if _last_verify_day[0] != today:
                        _last_verify_day[0] = today
                        try:
                            import backup as _bk
                            vr = _bk.verify_latest()
                            if vr["status"] == "bad":
                                logger.error("[备份巡检] %s", vr["message"])
                            elif vr["status"] == "empty":
                                logger.warning("[备份巡检] %s", vr["message"])
                            else:
                                logger.info("[备份巡检] %s", vr["message"])
                        except Exception as e:  # noqa: BLE001  巡检失败绝不影响定时发布主流程
                            logger.error("[备份巡检] 巡检本身失败（不影响定时发布）: %s", e)
                    # v3.25.3：SSL 证书到期检查（每日一次，第三个用同一循环的任务）。
                    # **为什么必须自动查**：证书过期 = 全站直接不可访问
                    # （HTTP 80 → 301 跳 HTTPS → 浏览器拒绝）。2026-10-02 22:59 到期，
                    # 10-05 才发现 —— 「记得看」对有硬期限的基础设施是失效的。
                    # 只提醒不续签：签发涉及域名验证/CA 授权，不是应用层该做的事。
                    if _last_cert_day[0] != today:
                        _last_cert_day[0] = today
                        try:
                            import cert_watch as _cw
                            cs = _cw.check_once()
                            if cs["status"] in ("expired", "critical"):
                                logger.error("[证书监控] %s", cs["message"])
                            elif cs["status"] == "warn":
                                logger.warning("[证书监控] %s", cs["message"])
                            elif cs["status"] == "unknown":
                                logger.warning("[证书监控] %s", cs["message"])
                            else:
                                logger.info("[证书监控] %s", cs["message"])
                        except Exception as e:  # noqa: BLE001  监控失败绝不影响定时发布主流程
                            logger.error("[证书监控] 检查本身失败（不影响定时发布）: %s", e)
            except Exception as e:
                # 单轮异常不致命，下一轮继续；打印便于排查
                logger.warning("[定时发布线程] 异常（已忽略，继续下一轮）: %s", e)
    # 是否启用由调用方决定（create_app 的 enable_scheduler）：测试传 False 可避免
    # 每个用例都起一个守护线程（原实现 99 个测试最多 99 个后台线程）。
    import threading as _threading
    _sched_thread = _threading.Thread(target=_scheduler_loop, name="scheduled-publish", daemon=True)
    _sched_thread.start()


def create_app(enable_scheduler=True):
    """应用工厂：装配扩展 → 请求钩子 → 建库自举 → 模板上下文 → CLI → 错误页 → 定时线程。

    v3.24.0：本函数原为 510 行的上帝函数，按职责拆成上面一组 `_setup_*` / `_register_*`。
    **拆分是纯搬运，不动任何一行逻辑**，两条顺序约束必须守住：
    - `_setup_core()`（含 `db.init_app`）必须早于 `_bootstrap_database()`；
    - `before_request` 的执行顺序 = 注册顺序，故钩子集中在 `_register_request_hooks()`
      内按原顺序注册（见该函数 docstring）。
    """
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # v3.24.0：迁移专用模式（`BLOG_MIGRATE_ONLY=1`）。
    # `flask db upgrade` 必须构造出 app 才能拿到 Flask-Migrate 的扩展，但正常路径会做
    # 一堆副作用（建表 / 超管兜底 / 设置播种 / FTS / 勋章播种），并且缺 SECRET_KEY、
    # ADMIN_PASSWORD 就直接拒绝启动 —— 部署脚本里通常没有这两个变量，硬塞一个假的
    # ADMIN_PASSWORD 又有「万一库里恰好没有超管，就用已知密码造出一个」的风险。
    # 迁移模式一律跳过这些副作用：只保留 app + db + Migrate，不动任何业务数据。
    migrate_only = os.environ.get("BLOG_MIGRATE_ONLY") == "1"

    _validate_required_env(app, migrate_only)
    _setup_core(app)
    _register_request_hooks(app)
    _bootstrap_database(app, migrate_only)
    _register_template_context(app)
    _register_cli(app)
    _register_error_handlers(app)

    # v3.18.5：测试可传 enable_scheduler=False 关掉定时发布线程
    # （原实现每个 create_app() 都起一个守护线程 → 99 个测试最多 99 个后台线程）。
    if enable_scheduler:
        _start_scheduler(app)

    return app



# 模块被导入时直接创建应用实例（供 flask run / gunicorn 使用）
app = create_app()


# 直接运行 `python app.py` 仅用于本地开发预览；生产请用 gunicorn 启动（不启用 debug）。
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)