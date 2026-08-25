"""前后端分离用的 JSON 接口蓝图（/api/*）。

前端（Astro 静态站）通过这里拿数据；后台管理仍走原 admin 蓝图（服务端渲染）。
所有返回均为 JSON；跨域头由 app.py 的 after_request 统一加。
"""
import json
import os
import datetime
import threading

from flask import Blueprint, request, jsonify, current_app, session, Response
from markupsafe import escape

# 在线更新防重入：进程内锁（消除「两请求同时读到 idle 各自 Popen」的 TOCTOU）。
# 锁不跨 worker，但 update.sh 还会写 data/update_status.json 文件锁，双保险；
# 同一 worker 内并发触发必然只有一个能拿到锁。
_UPDATE_LOCK = threading.Lock()

from models import db, Post, Category, Tag, Comment, FriendLink, Setting, User, ROLE_USER, \
    Moment, MomentComment, SocialAccount, Series, Announcement, Guestbook, Subscriber, Notification, \
    ReadLog, visible_posts_query, LinkApplication, AuditLog, PostHistory, RecycleBin
from utils import render_markdown, clean_html, rate_limit, client_key
import stats
# v3.1.0：记录登录审计（log_login_attempt 定义在 admin 模块，admin 不依赖 api，无循环）
from admin import log_login_attempt

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _current_user_or_none():
    """取当前登录用户对象（用于隐私空间可见性判断），未登录返回 None。"""
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


# ---------- 认证接口（注册 / 登录 / 登出 / 当前用户）----------
def _user_pub(u):
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "role_label": u.role_label,
        "is_super": u.is_super,
        "is_admin": u.is_admin_role,
        "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
    }


def _login_user(u):
    """登录：Flask session 与 Astro 前端通过 header X-User-Id 共用同一会话。
    v3.1.6：登录后会话变化，响应带新 csrf_token 供前端立即更新缓存。
    """
    session["user_id"] = u.id
    session["session_version"] = u.session_version or 0  # v3.1.6：会话版本绑定，改密码/踢下线后旧会话失效
    return jsonify({"ok": True, "user": _user_pub(u), "csrf_token": _csrf_token()})


@api_bp.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次注册尝试
    if not rate_limit(client_key("api_register"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    # 注册开关：生产可设 BLOG_OPEN_REGISTER=false 关闭公开注册
    if not current_app.config.get("BLOG_OPEN_REGISTER"):
        return jsonify({"error": "本站已关闭公开注册"}), 403
    # v3.1.6 可选增强：注册验证码（CAPTCHA_ENABLED=true 时要求通过验证码或直接带验证码文本）
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if captcha_required():
        passed = consume_captcha_pass()  # 一次性票据（先验票再消费）
        if not passed:
            code = (data.get("captcha") or "").strip()
            if not code or not verify_captcha(code):
                return jsonify({"error": "请先完成验证码校验"}), 400
            consume_captcha_pass()  # 直接带文本校验通过后消费票据防重放
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 20:
        return jsonify({"error": "用户名长度需在 2-20 个字符"}), 400
    # v3.1.6 中优：弱密码黑名单 + 复杂度校验（STRONG_PASSWORD 开关，见 config）
    from utils import validate_password
    cfg = current_app.config
    ok_pwd, pwd_err = validate_password(
        password, min_len=8,
        strong=cfg.get("STRONG_PASSWORD", True),
        mixed_case=cfg.get("STRONG_PASSWORD_MIXED_CASE", False),
    )
    if not ok_pwd:
        return jsonify({"error": pwd_err}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "该用户名已被注册"}), 409
    u = User(username=username, email=email, role=ROLE_USER)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return _login_user(u), 201


@api_bp.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次登录尝试，缓解暴力破解
    if not rate_limit(client_key("api_login"), limit=10, window=60):
        return jsonify({"error": "尝试过于频繁，请稍后再试"}), 429
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        # v3.1.0：记录失败的登录尝试（含尝试的用户名与 IP，便于发现爆破）
        log_login_attempt(username, False)
        # v3.1.6 中优：消除用户名枚举——失败统一文案（无论用户是否存在）+ 统一延迟，防时序侧信道
        _login_delay()
        return jsonify({"error": "用户名或密码错误"}), 401
    log_login_attempt(username, True)
    return _login_user(u)


def _login_delay():
    """v3.1.6：登录失败统一延迟（LOGIN_DELAY_SECONDS 默认 1 秒），
    让「用户不存在」与「密码错误」耗时一致，杜绝通过响应时间枚举用户名。
    仅对失败路径生效，不影响正常登录体验。异常静默。
    """
    try:
        import time as _t
        from flask import current_app
        delay = current_app.config.get("LOGIN_DELAY_SECONDS", 1.0)
        if delay > 0:
            _t.sleep(delay)
    except Exception:
        pass


@api_bp.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@api_bp.route("/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None, "csrf_token": _csrf_token()}), 200
    u = db.session.get(User, uid)
    if not u:
        session.pop("user_id", None)
        return jsonify({"user": None, "csrf_token": _csrf_token()}), 200
    return jsonify({"user": _user_pub(u), "csrf_token": _csrf_token()}), 200


@api_bp.route("/csrf")
def csrf():
    """获取当前会话的 CSRF Token（Vue 前端在 apiPost 前调用，放入 X-CSRF-Token 头）。"""
    return jsonify({"csrf_token": _csrf_token()}), 200


def _csrf_token():
    """从会话取 CSRF Token；不存在则生成（每次生成都会写入会话）。"""
    from utils import generate_csrf_token
    try:
        tok, _ = generate_csrf_token()
        return tok
    except Exception:
        return ""


# ---------- 图形验证码（v3.1.6 可选增强：可开关；v3.2.0 后台可单独配置）----------
@api_bp.route("/captcha/config")
def captcha_config():
    """返回验证码配置快照（全局启用 / PIL 是否可用 / 各场景开关），供前端分场景显隐。"""
    from security import get_captcha_config
    return jsonify(get_captcha_config())


@api_bp.route("/captcha")
def captcha_image():
    """获取注册/评论/留言验证码图片（GET）。返回 PNG 图；该场景未启用或全局关闭时返回 404。
    生成后答案存会话（captcha_answer），前端刷新图片时可重新生成。"""
    from security import generate_captcha, captcha_required
    scope = request.args.get("from")
    if not captcha_required(scope):
        return jsonify({"error": "验证码未启用"}), 404
    img, _ = generate_captcha()
    if img is None:
        # PIL 不可用降级：返回纯文本模式（前端显示为普通输入，不校验——零依赖稳妥）
        return jsonify({"captcha": "off", "message": "服务器未安装图像库，验证码已降级停用"}), 200
    return Response(img.getvalue(), mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


@api_bp.route("/captcha/verify", methods=["POST"])
def captcha_verify():
    """前端提交验证码文本，校验通过后会话标记 captcha_passed（一次性票据）。
    注册/评论提交时随请求携带该票据（或直接把验证码文本带上由注册接口自行校验）。"""
    data = request.get_json(silent=True) or request.form
    code = (data.get("captcha") or "").strip()
    from security import verify_captcha, consume_captcha_pass
    if not code:
        return jsonify({"error": "请输入验证码"}), 400
    if not verify_captcha(code):
        return jsonify({"error": "验证码错误，请重新输入"}), 400
    return jsonify({"ok": True, "captcha_passed": True}), 200


# ---------- 小工具 ----------
def _render_html(content):
    """把 Markdown 正文渲染成 HTML（已做 XSS 白名单清理）。"""
    return render_markdown(content)


def _settings_map():
    return {s.key: s.value for s in Setting.query.all()}


def _post_summary(p):
    return {
        "slug": p.slug,
        "title": p.title,
        "author": p.author.username if p.author else "",  # 作者身份（普通用户发表的文章记录作者；管理员/旧文章为空）
        "summary": p.summary or "",
        "cover": p.cover or "",
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M"),
        "views": p.views,
        "likes": p.likes,
        "is_pinned": bool(p.is_pinned),  # 是否置顶（首页/列表优先展示）
        # SEO 单独字段（v2.8.0）：独立描述/关键词，缺省回退
        "seo_description": p.seo_description or p.summary or "",
        "seo_keywords": p.seo_keywords or "",
        "category": {"name": p.category.name, "slug": p.category.slug} if p.category else None,
        "tags": [{"name": t.name, "slug": t.slug} for t in p.tags],
        # v3.0.0 新增字段
        "word_count": p.word_count or 0,
        "reading_minutes": p.reading_minutes or 0,
        "reward_enabled": bool(p.reward_enabled),
        "is_private": bool(p.is_private),
    }


def _is_visible(p):
    """判断单篇文章当前是否对访客可见（已发布且未到定时发布时间）。"""
    if not p or not p.published:
        return False
    if p.scheduled_at is not None and p.scheduled_at > datetime.utcnow():
        return False
    return True


def _comment(c):
    return {
        "id": c.id,
        "author": c.author,
        "content": c.content,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        "region": c.region or "",        # 归属地（前台展示；IP 原文不返回）
        "device": c.device or "",        # 设备信息
        "parent_id": c.parent_id or 0,   # 嵌套回复：父评论 id（0=顶层）
        "reply_to": c.reply_to or "",    # 被回复者昵称（@ 显示）
        "likes": c.likes or 0,           # 评论点赞数
    }


# ---------- 站点公共信息（导航 / 页脚 / 侧边栏用）----------
@api_bp.route("/site")
def site():
    s = _settings_map()
    return jsonify({
        "site_name": s.get("site_name") or s.get("site_title", "我的博客"),
        "site_title": s.get("site_title", "我的博客"),
        "site_note": s.get("site_note", ""),
        "site_description": s.get("site_description", ""),
        "about_content": clean_html(s.get("about_content", "")),
        "footer_text": s.get("footer_text", ""),
        "beian_code": s.get("beian_code", ""),
        "accent_color": s.get("accent_color", "#1a73e8"),
        "weather_city": s.get("weather_city", "北京"),
        "weather_lat": s.get("weather_lat", "39.9042"),
        "weather_lon": s.get("weather_lon", "116.4074"),
        "theme_mode": s.get("theme_mode", "system"),
        "theme_radius": s.get("theme_radius", "md"),
        "theme_font": s.get("theme_font", "md"),
        "nav_style": s.get("nav_style", "light"),
        "custom_css": s.get("custom_css", ""),
        "reward_qr_default": s.get("reward_qr_default", ""),
        "site_lang": s.get("site_lang", "zh"),
        "categories": [
            {"name": c.name, "slug": c.slug,
             "count": visible_posts_query().filter_by(category_id=c.id).count()}
            for c in Category.query.order_by(Category.id).all()
        ],
        "tags": [
            {"name": t.name, "slug": t.slug, "count": len(t.posts)}
            for t in Tag.query.order_by(Tag.id).all()
        ],
        "links": [
            {"name": l.name, "url": l.url, "description": l.description or ""}
            for l in FriendLink.query.order_by(FriendLink.sort).all()
        ],
        "stats": {
            "posts": visible_posts_query().count(),
            "views": db.session.query(db.func.sum(Post.views)).scalar() or 0,
            "comments": Comment.query.count(),
        },
    })


# ---------- 文章列表（分页 + 搜索）----------
@api_bp.route("/posts")
def posts():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("POSTS_PER_PAGE", 8)
    q = (request.args.get("q") or "").strip()

    query = visible_posts_query()
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Post.title.ilike(like), Post.summary.ilike(like), Post.content.ilike(like))
        )
    query = query.order_by(Post.is_pinned.desc(), Post.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [_post_summary(p) for p in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
        "per_page": pagination.per_page,
    })


# ---------- 文章详情（含渲染后的 HTML 与评论）----------
@api_bp.route("/post/<slug>")
def post_detail(slug):
    # v3.0.0 功能13：登录的超级管理员可查看自己的隐私文章；其余人（含未登录）一律 404
    _u = _current_user_or_none()
    p = visible_posts_query(user=_u).filter_by(slug=slug).first_or_404()
    # 阅读量 +1（防刷：同 IP 24h 内只计一次真实阅读）
    from app import count_unique_view
    if count_unique_view(p.id, stats.client_ip()):
        p.views += 1
        db.session.commit()

    data = _post_summary(p)
    data["html"] = _render_html(p.content)
    # 审核流：前台只展示已通过审核的评论（approved=True）
    data["comments"] = [_comment(c) for c in p.comments.filter_by(approved=True).order_by(Comment.created_at.asc())]
    # 系列上下篇导航
    if p.series_id and p.series:
        s_posts = visible_posts_query().filter_by(series_id=p.series_id).order_by(Post.created_at.asc()).all()
        idx = next((i for i, x in enumerate(s_posts) if x.id == p.id), -1)
        data["series"] = {
            "slug": p.series.slug, "name": p.series.name,
            "prev": {"slug": s_posts[idx - 1].slug, "title": s_posts[idx - 1].title}
                    if idx > 0 else None,
            "next": {"slug": s_posts[idx + 1].slug, "title": s_posts[idx + 1].title}
                    if idx < len(s_posts) - 1 else None,
        }
    else:
        data["series"] = None
    return jsonify(data)


# ---------- 分类 / 标签 ----------
@api_bp.route("/categories")
def categories():
    return jsonify([
        {"name": c.name, "slug": c.slug,
         "count": visible_posts_query().filter_by(category_id=c.id).count()}
        for c in Category.query.order_by(Category.id).all()
    ])


@api_bp.route("/tags")
def tags():
    return jsonify([
        {"name": t.name, "slug": t.slug, "count": len(t.posts)}
        for t in Tag.query.order_by(Tag.id).all()
    ])


@api_bp.route("/hot-tags")
def hot_tags():
    """热门标签（v3.0.0 功能7）：按文章数排序取前 N，并附带总阅读量便于热度加权。

    前端「热门标签页」展示；排序权重 = 文章数 * 2 + floor(总阅读量 / 1000)，
    既体现使用广度也体现受欢迎程度。仅统计前台可见文章（不含隐私/回收站）。
    """
    limit = request.args.get("limit", 20, type=int)
    if limit <= 0 or limit > 50:
        limit = 20
    rows = []
    for t in Tag.query.all():
        posts = [p for p in t.posts if not p.in_trash and p.published
                 and (not p.is_private) and (p.scheduled_at is None or p.scheduled_at <= datetime.utcnow())]
        if not posts:
            continue
        views = sum(p.views or 0 for p in posts)
        weight = len(posts) * 2 + views // 1000
        rows.append({"name": t.name, "slug": t.slug, "count": len(posts),
                     "views": views, "weight": weight})
    rows.sort(key=lambda x: x["weight"], reverse=True)
    return jsonify({"items": rows[:limit]})


@api_bp.route("/category/<slug>")
def posts_by_category(slug):
    c = Category.query.filter_by(slug=slug).first_or_404()
    items = visible_posts_query().filter_by(category_id=c.id)\
        .order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()
    return jsonify({"name": c.name, "slug": c.slug,
                    "items": [_post_summary(p) for p in items]})


@api_bp.route("/tag/<slug>")
def posts_by_tag(slug):
    t = Tag.query.filter_by(slug=slug).first_or_404()
    items = visible_posts_query().filter(Post.tags.any(id=t.id)).order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()
    return jsonify({"name": t.name, "slug": t.slug,
                    "items": [_post_summary(p) for p in items]})


# ---------- RSS 按分类 / 标签订阅（v3.0.0 功能10）----------
def _rss_xml(posts, title, desc, base):
    """把文章列表拼成 RSS 2.0 XML（复用 routes.py 的 feed() 逻辑，纯本地、无外部依赖）。"""
    items = []
    for p in posts:
        link = f"{base}/post/{p.slug}"
        pub = p.created_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        summary = escape((p.summary or (p.content or "")[:200]).strip())
        items.append(
            "    <item>\n"
            f"      <title>{escape(p.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid>{escape(link)}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{summary}</description>\n"
            "    </item>"
        )
    last = posts[0].created_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if posts else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <link>{escape(base + '/')}</link>\n"
        f"    <description>{escape(desc)}</description>\n"
        f"    <lastBuildDate>{last}</lastBuildDate>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n"
        "</rss>\n"
    )
    return Response(xml, mimetype="application/rss+xml")


@api_bp.route("/rss/category/<slug>")
def rss_category(slug):
    """分类 RSS：该分类下已发布文章的订阅源。"""
    c = Category.query.filter_by(slug=slug).first_or_404()
    posts = visible_posts_query().filter_by(category_id=c.id)\
        .order_by(Post.is_pinned.desc(), Post.created_at.desc()).limit(20).all()
    base = (current_app.config.get("SITE_URL") or request.url_root.rstrip("/")).rstrip("/")
    return _rss_xml(posts, f"{c.name} - RSS", f"{c.name} 分类文章更新", base)


@api_bp.route("/rss/tag/<slug>")
def rss_tag(slug):
    """标签 RSS：带该标签的已发布文章的订阅源。"""
    t = Tag.query.filter_by(slug=slug).first_or_404()
    posts = visible_posts_query().filter(Post.tags.any(id=t.id))\
        .order_by(Post.is_pinned.desc(), Post.created_at.desc()).limit(20).all()
    base = (current_app.config.get("SITE_URL") or request.url_root.rstrip("/")).rstrip("/")
    return _rss_xml(posts, f"{t.name} - RSS", f"标签「{t.name}」相关文章更新", base)


# ---------- 归档时间线 ----------
@api_bp.route("/archive")
def archive():
    posts = visible_posts_query().order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()
    timeline = {}
    for p in posts:
        y = p.created_at.strftime("%Y")
        m = p.created_at.strftime("%m")
        timeline.setdefault(y, {}).setdefault(m, []).append(_post_summary(p))
    # 转成有序列表，方便前端渲染
    result = []
    for y in sorted(timeline.keys(), reverse=True):
        months = []
        for m in sorted(timeline[y].keys(), reverse=True):
            months.append({"month": m, "posts": timeline[y][m]})
        result.append({"year": y, "months": months})
    return jsonify(result)


# ---------- 友情链接 ----------
@api_bp.route("/links")
def links():
    return jsonify([
        {"name": l.name, "url": l.url, "description": l.description or ""}
        for l in FriendLink.query.order_by(FriendLink.sort).all()
    ])


@api_bp.route("/link-apply", methods=["POST"])
def link_apply():
    """友情链接自助申请（v3.0.0 功能6）。

    前台访客提交友链申请，进入待审核队列（不直接写 FriendLink 表，避免 spam）。
    限流 + 基础校验（名称/URL 必填、URL 格式、同 URL 24h 内不可重复申请）。
    审核通过后由后台写入 FriendLink 列表。
    """
    if not rate_limit(client_key("api_link_apply"), limit=10, window=86400):
        return jsonify({"error": "申请过于频繁，请 24 小时后再试"}), 429
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    description = (data.get("description") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not url:
        return jsonify({"error": "站点名称和链接不能为空"}), 400
    import re as _re
    if not _re.match(r"^https?://[^\s]+$", url):
        return jsonify({"error": "链接格式不正确（需以 http:// 或 https:// 开头）"}), 400
    # 同一 URL 未处理的申请不重复接收
    dup = LinkApplication.query.filter_by(url=url, status="pending").first()
    if dup:
        return jsonify({"ok": True, "message": "该链接已在审核队列中，请耐心等待"}), 201
    ip = stats.client_ip()
    app_row = LinkApplication(name=name[:100], url=url[:300], description=description[:200],
                              email=email[:160], status="pending", applicant_ip=ip)
    db.session.add(app_row)
    db.session.commit()
    return jsonify({"ok": True, "message": "申请已提交，管理员审核通过后会展示在友情链接"}), 201


# ---------- 点赞 ----------
@api_bp.route("/post/<slug>/like", methods=["POST"])
def like(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 限流：同一 IP 对单篇文章 60 秒内最多 20 次点赞（防刷量）
    if not rate_limit(client_key("api_like:" + slug), limit=20, window=60):
        return jsonify({"likes": p.likes})
    p.likes += 1
    db.session.commit()
    return jsonify({"likes": p.likes})


# ---------- 评论提交 ----------
@api_bp.route("/post/<slug>/comment", methods=["POST"])
def comment(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 限流：同一 IP 60 秒内最多 10 条评论
    if not rate_limit(client_key("api_comment"), limit=10, window=60):
        return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    # v3.1.6 可选增强：评论验证码（CAPTCHA_ENABLED=true 时要求通过验证码或直接带验证码文本）
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if captcha_required():
        passed = consume_captcha_pass()  # 一次性票据（先验票再消费）
        if not passed:
            code = (data.get("captcha") or "").strip()
            if not code or not verify_captcha(code):
                return jsonify({"error": "请先完成验证码校验"}), 400
            consume_captcha_pass()  # 直接带文本校验通过后消费票据防重放
    content = (data.get("content") or "").strip()
    # 已登录用户自动用其用户名；否则需填昵称
    author = ""
    uid = session.get("user_id")
    if uid:
        u = db.session.get(User, uid)
        if u:
            author = u.username
    author = author or (data.get("author") or "").strip()
    if not author or not content:
        return jsonify({"error": "昵称和评论内容不能为空"}), 400
    # v3.0.0 功能2：垃圾评论关键词过滤（站点设置 comment_spam_keywords 逗号分隔）。
    # 命中任一关键词直接拒绝提交，避免垃圾评论进入审核队列。关键词大小写不敏感。
    spam_kw = (Setting.query.filter_by(key="comment_spam_keywords").first())
    if spam_kw and spam_kw.value:
        kw_list = [k.strip().lower() for k in spam_kw.value.replace("，", ",").split(",") if k.strip()]
        low = content.lower()
        hit = next((k for k in kw_list if k and k in low), None)
        if hit:
            return jsonify({"error": "评论包含不被允许的词汇，已被过滤"}), 400
    # 嵌套回复：parent_id 必须属于同一篇文章，reply_to 默认取父评论作者
    parent_id = data.get("parent_id") or 0
    reply_to = (data.get("reply_to") or "").strip()
    if parent_id:
        parent = Comment.query.filter_by(id=parent_id, post_id=p.id).first()
        if not parent:
            return jsonify({"error": "回复的评论不存在"}), 400
        if not reply_to:
            reply_to = parent.author
    # 记录评论者 IP 属地与设备（属地缓存命中即返回，未命中后台线程稍后回填）
    from utils import parse_device, setting_bool, notify_mentioned
    ip = stats.client_ip()
    # 审核流：后台站点设置 comment_require_approval 优先于环境变量默认
    require_approval = setting_bool("comment_require_approval", current_app.config.get("COMMENT_REQUIRE_APPROVAL", False))
    c = Comment(post_id=p.id, author=author[:80], content=content, approved=not require_approval,
                ip=ip, region=stats.cached_region(ip),
                device=parse_device(request.headers.get("User-Agent", ""))[:120],
                parent_id=parent_id or None, reply_to=reply_to[:80])
    db.session.add(c)
    db.session.commit()
    # A4 站内 @ 通知：解析评论内容里 @username，给注册用户发通知
    notify_mentioned(content, f"/post/{p.slug}", author, post_id=p.id)
    return jsonify({"ok": True, "comment": _comment(c),
                    "pending": require_approval}), 201


# ---------- 访问统计（埋点 + 汇总）----------
@api_bp.route("/stats/visit", methods=["POST"])
def stats_visit():
    """前端每次路由变化时上报一次访问（fire-and-forget）。
    全量审计加固：加限流防脚本刷库；超限静默丢弃，不影响正常访客。"""
    if not rate_limit(client_key("api_stats_visit"), limit=60, window=60):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "")[:255]
    if path.startswith("/admin"):
        return jsonify({"ok": True, "skipped": True})
    post_id = data.get("post_id")
    if post_id is not None:
        try:
            post_id = int(post_id)
        except (TypeError, ValueError):
            post_id = None
    stats.record_visit(path, post_id)
    return jsonify({"ok": True})


@api_bp.route("/stats/search", methods=["POST"])
def stats_search():
    """记录搜索词。全量审计加固：120 次/小时 限流防刷库。"""
    if not rate_limit(client_key("api_stats_search"), limit=120, window=3600):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    stats.record_search(data.get("keyword") or "")
    return jsonify({"ok": True})


@api_bp.route("/stats/read", methods=["POST"])
def stats_read():
    """记录一次文章阅读（同一访客重复读会累加）。全量审计加固：60 次/分钟 限流防刷库。"""
    if not rate_limit(client_key("api_stats_read"), limit=60, window=60):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    slug = (data.get("slug") or "").strip()
    p = Post.query.filter_by(slug=slug).first() if slug else None
    if p:
        stats.record_read(p.id, stats.client_ip())
    return jsonify({"ok": True})


@api_bp.route("/stats/summary")
def stats_summary():
    """统计汇总（累计访问 / 区域排行 / 热读文章 / 常搜词 / 时段分布 / 访客趋势）。"""
    return jsonify(stats.compute_summary())


@api_bp.route("/stats/trend")
def stats_trend():
    """访客趋势（v3.0.0 功能9）：最近 N 天 PV/UV，供访客趋势图使用。"""
    days = request.args.get("days", 30, type=int)
    if days <= 0 or days > 90:
        days = 30
    return jsonify({"trend": stats.compute_trend(days)})


# ---------- 社交聚合页（广场）----------
def _current_user():
    """从会话取当前登录用户对象（未登录返回 None）。"""
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


def _moment(m):
    return {
        "id": m.id,
        "author": m.author.username if m.author else "匿名",
        "content": m.content,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
        "likes": m.likes,
        "comments": [_mcomment(c) for c in m.comments.order_by(MomentComment.created_at.asc())],
    }


def _mcomment(c):
    return {
        "id": c.id,
        "author": c.author,
        "content": c.content,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
        "region": c.region or "",
    }


@api_bp.route("/moments")
def moments():
    """微动态列表（倒序分页）。"""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    pagination = Moment.query.order_by(Moment.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [_moment(m) for m in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
    })


@api_bp.route("/moment", methods=["POST"])
def post_moment():
    """发布一条微动态（需登录，限流，纯文本存储，前端渲染时自动转义防 XSS）。"""
    u = _current_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    if not rate_limit(client_key("api_moment"), limit=20, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "动态内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"error": "动态最多 500 字"}), 400
    m = Moment(author_id=u.id, content=content)
    db.session.add(m)
    db.session.commit()
    return jsonify({"ok": True, "moment": _moment(m)}), 201


@api_bp.route("/moment/<int:mid>/like", methods=["POST"])
def like_moment(mid):
    """微动态点赞（限流防刷）。"""
    m = Moment.query.get_or_404(mid)
    if not rate_limit(client_key("api_mlike:" + str(mid)), limit=20, window=60):
        return jsonify({"likes": m.likes})
    m.likes += 1
    db.session.commit()
    return jsonify({"likes": m.likes})


@api_bp.route("/moment/<int:mid>/comment", methods=["POST"])
def comment_moment(mid):
    """微动态评论（需昵称；已登录自动用用户名）。"""
    m = Moment.query.get_or_404(mid)
    if not rate_limit(client_key("api_mcomment"), limit=10, window=60):
        return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    content = (data.get("content") or "").strip()
    author = ""
    u = _current_user()
    if u:
        author = u.username
    author = author or (data.get("author") or "").strip()
    if not author or not content:
        return jsonify({"error": "昵称和评论内容不能为空"}), 400
    from utils import parse_device
    ip = stats.client_ip()
    c = MomentComment(moment_id=m.id, author=author[:80], content=content,
                      ip=ip, region=stats.cached_region(ip),
                      device=parse_device(request.headers.get("User-Agent", ""))[:120])
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "comment": _mcomment(c)}), 201


@api_bp.route("/feed/circle")
def feed_circle():
    """博客圈：抓取友链站点 RSS，按时间混排（带缓存 + SSRF 防护）。"""
    try:
        import feed_agg
        force = request.args.get("refresh") == "1"
        items = feed_agg.get_circle_feed(force=force)
    except Exception as e:
        print("博客圈聚合失败:", e)
        items = []
    return jsonify({"items": items})


@api_bp.route("/social-accounts")
def social_accounts():
    """作者的社交账号墙（广场页「关注」标签用）。"""
    accs = SocialAccount.query.order_by(SocialAccount.sort).all()
    return jsonify([
        {"id": a.id, "platform": a.platform, "handle": a.handle, "url": a.url}
        for a in accs
    ])


# ---------- 文章系列 / 专栏（B4）----------
@api_bp.route("/series")
def series_list():
    sers = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return jsonify([
        {"slug": s.slug, "name": s.name, "description": s.description or "",
         "cover": s.cover or "", "count": visible_posts_query().filter_by(series_id=s.id).count()}
        for s in sers
    ])


@api_bp.route("/series/<slug>")
def series_detail(slug):
    s = Series.query.filter_by(slug=slug).first_or_404()
    posts = visible_posts_query().filter_by(series_id=s.id).order_by(Post.created_at.asc()).all()
    return jsonify({
        "slug": s.slug, "name": s.name, "description": s.description or "",
        "cover": s.cover or "",
        "posts": [_post_summary(p) for p in posts],
    })


# ---------- 相关文章推荐（按标签重合度 + 同分类，纯算法零依赖，B1）----------
@api_bp.route("/post/<slug>/related")
def related_posts(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    p_tags = set(t.id for t in p.tags)
    scored = []
    for c in visible_posts_query().filter(Post.id != p.id).all():
        c_tags = set(t.id for t in c.tags)
        score = len(p_tags & c_tags)
        if p.category_id and p.category_id == c.category_id:
            score += 1
        if score <= 0:
            continue
        scored.append((score, c))
    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    return jsonify({"items": [_post_summary(c) for _, c in scored[:5]]})


@api_bp.route("/post/<slug>/also-viewed")
def also_viewed(slug):
    """「看了又看」协同过滤推荐（v3.0.0 功能8）。

    思路（零外部依赖、纯共现）：
    1. 找出读过当前文章 slug 的访客 IP 集合；
    2. 这些访客还读过哪些其他文章，按「共同阅读人数」打分（协同过滤核心）；
    3. 再叠加一层「相似标签」加权（同标签/同分类），冷启动（无共现）时退化为基础相似推荐；
    4. 仅返回前台可见文章，按分数倒序取前 5。
    """
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 当前文章的访客 IP
    base_readers = {r.ip for r in ReadLog.query.filter_by(post_id=p.id).all()}
    scored = {}
    if base_readers:
        # 这些访客读过的其它文章
        other = (ReadLog.query.filter(ReadLog.post_id != p.id,
                                       ReadLog.ip.in_(list(base_readers)))
                 .with_entities(ReadLog.post_id).all())
        for (pid,) in other:
            scored[pid] = scored.get(pid, 0) + 1
    # 相似度加权（标签/分类）
    p_tags = set(t.id for t in p.tags)
    for c in visible_posts_query().filter(Post.id != p.id).all():
        c_tags = set(t.id for t in c.tags)
        sim = len(p_tags & c_tags)
        if p.category_id and p.category_id == c.category_id:
            sim += 1
        if sim > 0:
            scored[c.id] = scored.get(c.id, 0) + sim * 0.5
    # 排序
    ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:5]
    items = []
    for pid, _ in ranked:
        post = db.session.get(Post, pid)
        if post and post.id != p.id and _is_visible(post):
            items.append(_post_summary(post))
    return jsonify({"items": items})


# ---------- 站点公告 / 置顶（D4）----------
@api_bp.route("/announcements")
def announcements():
    items = Announcement.query.filter_by(active=True).order_by(Announcement.created_at.desc()).all()
    return jsonify({"items": [
        {"id": a.id, "content": clean_html(render_markdown(a.content)),
         "level": a.level, "dismissible": a.dismissible}
        for a in items
    ]})


# ---------- 留言墙（C1）----------
def _gb(g):
    return {
        "id": g.id, "author": g.author, "content": g.content,
        "created_at": g.created_at.strftime("%Y-%m-%d %H:%M"),
        "likes": g.likes or 0,
        "region": g.region or "", "device": g.device or "",
    }


@api_bp.route("/guestbook")
def guestbook():
    page = request.args.get("page", 1, type=int)
    pagination = Guestbook.query.order_by(Guestbook.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return jsonify({"items": [_gb(g) for g in pagination.items],
                    "page": pagination.page, "pages": pagination.pages, "total": pagination.total})


@api_bp.route("/guestbook", methods=["POST"])
def post_guestbook():
    if not rate_limit(client_key("api_guestbook"), limit=10, window=60):
        return jsonify({"error": "留言过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    # v3.1.6 可选增强：留言验证码（CAPTCHA_ENABLED=true 时要求通过验证码或直接带验证码文本）
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if captcha_required():
        passed = consume_captcha_pass()  # 一次性票据（先验票再消费）
        if not passed:
            code = (data.get("captcha") or "").strip()
            if not code or not verify_captcha(code):
                return jsonify({"error": "请先完成验证码校验"}), 400
            consume_captcha_pass()  # 直接带文本校验通过后消费票据防重放
    content = (data.get("content") or "").strip()
    u = _current_user()
    author = (u.username if u else (data.get("author") or "").strip())
    if not author or not content:
        return jsonify({"error": "昵称和留言内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"error": "留言最多 500 字"}), 400
    from utils import parse_device
    ip = stats.client_ip()
    g = Guestbook(author=author[:80], content=content, user_id=u.id if u else None,
                  ip=ip, region=stats.cached_region(ip),
                  device=parse_device(request.headers.get("User-Agent", ""))[:120])
    db.session.add(g)
    db.session.commit()
    return jsonify({"ok": True, "guestbook": _gb(g)}), 201


@api_bp.route("/guestbook/<int:gid>/like", methods=["POST"])
def like_guestbook(gid):
    g = Guestbook.query.get_or_404(gid)
    if not rate_limit(client_key("api_gblike:" + str(gid)), limit=20, window=60):
        return jsonify({"likes": g.likes})
    g.likes += 1
    db.session.commit()
    return jsonify({"likes": g.likes})


# ---------- 邮件订阅 / 退订（Newsletter，C3）----------
@api_bp.route("/subscribe", methods=["POST"])
def subscribe():
    if not rate_limit(client_key("api_subscribe"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    import re as _re
    if not email or not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "邮箱格式不正确"}), 400
    import secrets as _sec
    sub = Subscriber.query.filter_by(email=email).first()
    if sub:
        if not sub.unsub_token:  # 旧数据补 token
            sub.unsub_token = _sec.token_hex(16)
            db.session.commit()
        return jsonify({"ok": True, "message": "你已经订阅过啦"})
    sub = Subscriber(email=email[:160], unsub_token=_sec.token_hex(16))
    db.session.add(sub)
    db.session.commit()
    return jsonify({"ok": True, "message": "订阅成功，新文章发布时会邮件通知你"}), 201


@api_bp.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    """邮件退订：凭邮箱 + 退订令牌取消订阅（无需登录）。
    用法：/api/unsubscribe?email=xxx&token=yyy，GET 返回状态，POST 执行退订。
    安全：统一错误信息避免邮箱枚举；POST 退订按 IP 限流。
    """
    email = (request.args.get("email") or "").strip().lower()
    token = (request.args.get("token") or "").strip()
    if not email or not token:
        return jsonify({"error": "退订链接不完整"}), 400
    sub = Subscriber.query.filter_by(email=email).first()
    import hmac
    # 统一错误信息（无论邮箱不存在还是 token 错误都返回同样提示，避免枚举有效邮箱）
    valid = bool(sub and sub.unsub_token and hmac.compare_digest(token, sub.unsub_token))
    if not valid:
        return jsonify({"error": "退订链接无效或已失效"}), 404
    if request.method == "POST":
        if not rate_limit(client_key("api_unsub"), limit=10, window=60):
            return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
        sub.active = False
        db.session.commit()
        return jsonify({"ok": True, "message": "已退订，不再发送新文章邮件"})
    return jsonify({"ok": True, "email": email, "active": sub.active,
                    "message": "确认退订？请用 POST 请求确认"})


# ---------- 全文搜索（FTS5 优先，失败回退 LIKE，B5；v3.0.0 功能3 增加分页 + 高亮）----------
@api_bp.route("/search")
def search_api():
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    if per_page <= 0 or per_page > 50:
        per_page = 10
    if not q:
        return jsonify({"items": [], "total": 0, "pages": 0, "page": page, "engine": "none",
                        "query": ""})
    # 高亮命中词：取摘要里包含 q 的片段，用 <mark> 包裹（前端渲染时信任该结构——
    # 内容本身来自本站数据库、q 已转义，无 XSS 风险）
    def make_highlight(p):
        text = (p.summary or (p.content or "")).replace("\n", " ").strip()
        idx = text.lower().find(q.lower())
        if idx < 0:
            snippet = text[:120]
        else:
            start = max(0, idx - 30)
            end = min(len(text), idx + len(q) + 60)
            snippet = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
        # 转义后高亮（先 escape 全文，再替换命中词为 <mark>）
        esc_text = escape(snippet)
        esc_q = escape(q)
        # 大小写不敏感地包裹命中词
        import re as _re
        esc_text = _re.sub(_re.escape(esc_q), lambda m: f"<mark>{m.group(0)}</mark>",
                           esc_text, flags=_re.IGNORECASE)
        return esc_text

    try:
        import fts as fts_mod
        ids = fts_mod.search(q)
    except Exception:
        ids = None
    # 注意：FTS5 可用但查询无命中时会返回空列表 []（不是 None）。
    # 旧逻辑用 `if ids is not None` 判断，导致「有结果」与「无结果」都被当成 FTS 命中，
    # 中文等 FTS 无法分词/无匹配的查询就再也回退不到 LIKE 模糊匹配。
    # 改为 `if ids`：仅在 FTS 真正返回了命中（非空列表）时才用 FTS 结果；
    # 空列表（无命中）或 None（FTS 不可用）都回退到 LIKE 子串匹配（Issue② 修复）。
    if ids:
        posts = [db.session.get(Post, i) for i in ids]
        posts = [p for p in posts if _is_visible(p)]
        engine = "fts5"
    else:
        like = f"%{q}%"
        posts = (visible_posts_query()
                 .filter(db.or_(Post.title.ilike(like), Post.summary.ilike(like), Post.content.ilike(like)))
                 .order_by(Post.is_pinned.desc(), Post.created_at.desc()).all())
        engine = "like"
    total = len(posts)
    pages = (total + per_page - 1) // per_page if per_page else 1
    start = (page - 1) * per_page
    page_items = posts[start:start + per_page]
    items = []
    for p in page_items:
        s = _post_summary(p)
        s["highlight"] = make_highlight(p)
        items.append(s)
    return jsonify({"items": items, "total": total, "pages": pages, "page": page,
                    "engine": engine, "query": q})


# ---------- 站内通知（A4 评论 @ 通知）----------
@api_bp.route("/notifications")
def notifications():
    """当前登录用户的未读通知数 + 最近通知列表。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"items": [], "unread": 0})
    unread = Notification.query.filter_by(user_id=uid, is_read=False).count()
    rows = (Notification.query.filter_by(user_id=uid)
            .order_by(Notification.created_at.desc()).limit(20).all())
    return jsonify({
        "unread": unread,
        "items": [{
            "id": n.id, "content": n.content, "link": n.link or "",
            "is_read": n.is_read,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
        } for n in rows],
    })


@api_bp.route("/notification/<int:nid>/read", methods=["POST"])
def read_notification(nid):
    """标记单条通知已读。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    n = Notification.query.filter_by(id=nid, user_id=uid).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/notifications/read-all", methods=["POST"])
def read_all_notifications():
    """当前用户全部通知标记已读。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    Notification.query.filter_by(user_id=uid, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


# ---------- 版本自检与在线更新（后台一键更新，v2.5.0）----------
_VER_CHECK_CACHE = {"ts": 0, "latest": ""}  # 进程内缓存 GitHub 最新版本（10 分钟）


@api_bp.route("/version/check")
def version_check():
    """后台登录后检测是否有新版本：对比 GitHub latest tag 与本地 APP_VERSION。
    仅查询 GitHub（10 分钟缓存），不做任何写操作；未配置 WH_DEPLOY_SECRET 也能查。
    """
    import json as _json
    import urllib.request
    import time as _time
    from config import APP_VERSION as _VER

    latest = ""
    now = _time.time()
    # 命中缓存直接返回（避免每次登录都请求 GitHub）
    if _VER_CHECK_CACHE["latest"] and (now - _VER_CHECK_CACHE["ts"]) < 600:
        latest = _VER_CHECK_CACHE["latest"]
    else:
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/Llhhy1/llhhy-blog/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "llhhy-blog"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            latest = (data.get("tag_name") or "").strip()
            _VER_CHECK_CACHE["latest"] = latest
            _VER_CHECK_CACHE["ts"] = now
        except Exception:
            latest = _VER_CHECK_CACHE.get("latest", "")  # 网络失败回退缓存
    current = _VER or ""
    # 规范化版本号：去 v/V 前缀，拆成 tuple 数字比较（修复字符串比较 'v2.5.0' > '2.5.0' 恒 True 的 bug）
    def _v_tuple(s):
        s = (s or "").strip()
        if s and s[0] in "vV":
            s = s[1:]
        try:
            return tuple(int(x) for x in s.split(".") if x.isdigit())
        except (ValueError, TypeError):
            return None
    c_t, l_t = _v_tuple(current), _v_tuple(latest)
    update_available = bool(c_t and l_t and l_t > c_t)
    return jsonify({
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "check_ok": True,
    })


def _do_version_update():
    """在 _UPDATE_LOCK 保护下执行更新触发：校验脚本存在 → 状态文件防重入 → Popen。

    与 version_update 分离以缩小锁内临界区（只包「检查+启动」原子段）。
    """
    import config as _cfg_mod
    script = _cfg_mod.Config.DEPLOY_SCRIPT or os.path.join(_cfg_mod.BASE_DIR, "update.sh")
    script = os.path.normpath(script)
    if not os.path.exists(script):
        return jsonify({"error": f"未找到更新脚本 {script}，请先上传 update.sh 到服务器"}), 400
    try:
        import json as _json
        status_file = os.path.join(_cfg_mod.DATA_DIR, "update_status.json")
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                st = _json.load(f).get("status", "")
            if st in ("started", "downloading", "backing_up", "deploying", "restarting"):
                return jsonify({"error": "更新正在进行中，请稍候"}), 409
    except Exception:
        pass
    # 异步执行（nohup 风格：脱离父进程，输出重定向到日志，不阻塞请求）
    try:
        import subprocess
        log_path = os.path.join(_cfg_mod.DATA_DIR, "update_log.txt")
        with open(log_path, "ab") as logf:
            subprocess.Popen(["bash", script], stdout=logf, stderr=logf,
                             start_new_session=True, close_fds=True)
    except Exception as e:
        return jsonify({"error": f"更新脚本启动失败: {e}"}), 500
    return jsonify({"ok": True, "message": "已开始后台更新，完成后会提示刷新"})


@api_bp.route("/version/update", methods=["POST"])
def version_update():
    """触发在线更新：异步执行 update.sh（下载→备份→覆盖→自动重启）。
    仅超管可触发（全量审计修复：原为 is_admin_role，普通管理员也能触发服务器
    脚本执行——运维级 RCE 被暴露给非超管，收窄为 is_super）；正在更新时拒绝
    重复触发（防重入锁，含进程内锁消除 TOCTOU）。
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    u = db.session.get(User, uid) if uid else None
    if not u or not u.is_super:
        return jsonify({"error": "没有权限执行更新（仅超级管理员）"}), 403
    if not rate_limit(client_key("api_version_update"), limit=3, window=3600):
        return jsonify({"error": "更新触发过于频繁，请稍后再试"}), 429
    # 防重入：进程内锁（消除 TOCTOU）+ 状态文件双保险
    if not _UPDATE_LOCK.acquire(blocking=False):
        return jsonify({"error": "更新正在进行中，请稍候"}), 409
    try:
        return _do_version_update()
    finally:
        _UPDATE_LOCK.release()


# ---------- 在线更新状态查询 ----------


@api_bp.route("/version/status")
def version_status():
    """读取在线更新状态（后台轮询用）。仅超管可读（全量审计修复：原无鉴权，任何人可读 \n    更新进度，且可配合 update 的防重入锁制造 409 DoS；收窄为 is_super）。"""
    uid = session.get("user_id")
    u = db.session.get(User, uid) if uid else None
    if not u or not u.is_super:
        return jsonify({"error": "没有权限"}), 403
    import config as _cfg_mod
    status_file = os.path.join(_cfg_mod.DATA_DIR, "update_status.json")
    default = {"status": "idle", "version": "", "ts": "", "message": ""}
    try:
        import json as _json
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                return jsonify(_json.load(f))
    except Exception:
        pass
    return jsonify(default)


# ---------- Webhook 自动部署（GitHub push → 服务器自动更新，D3）----------
@api_bp.route("/webhook/deploy", methods=["POST"])
def webhook_deploy():
    """密钥鉴权 + 触发服务器部署脚本。
    配置环境变量 WH_DEPLOY_SECRET（鉴权）与 DEPLOY_SCRIPT（部署脚本路径）。
    GitHub Webhook 在 Header 带 X-Deploy-Token 或在 URL 带 ?token=。
    校验通过后，若配置了 DEPLOY_SCRIPT 则异步执行该脚本（如 git pull / 解压 zip / 重启）。"""
    secret = current_app.config.get("WH_DEPLOY_SECRET")
    if not secret:
        return jsonify({"error": "服务器未配置部署密钥 WH_DEPLOY_SECRET"}), 403
    token = request.headers.get("X-Deploy-Token") or request.args.get("token") or ""
    import hmac
    if not hmac.compare_digest(token, secret):
        return jsonify({"error": "密钥错误"}), 403
    # v3.1.6 可选增强：timestamp 防重放（WH_REPLAY_WINDOW，默认 300 秒；设 0 关闭）
    # 要求请求头携带 X-Deploy-Time（Unix 秒），与服务器时间偏差超过窗口即拒绝，
    # 防止攻击者截获合法 webhook 请求后在窗口外重放触发部署。
    window = current_app.config.get("WH_REPLAY_WINDOW", 300)
    if window > 0:
        try:
            import time as _t
            ts = int(request.headers.get("X-Deploy-Time") or "")
            if abs(_t.time() - ts) > window:
                return jsonify({"error": "部署请求时间戳过期或缺失，已拒绝（防重放）"}), 403
        except (TypeError, ValueError):
            return jsonify({"error": "缺少有效的 X-Deploy-Time 时间戳，已拒绝（防重放）"}), 403
    script = current_app.config.get("DEPLOY_SCRIPT", "")
    triggered = False
    if script:
        try:
            import subprocess
            # 异步触发部署脚本（不等待、不阻塞请求）；DEVNULL 重定向输出避免 hang，无 fd 泄漏
            subprocess.Popen(["bash", script], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            triggered = True
        except Exception as e:
            return jsonify({"ok": True, "triggered": False, "error": f"部署脚本启动失败: {e}"}), 500
    return jsonify({"ok": True, "triggered": triggered,
                    "message": "部署已触发" if triggered else "授权通过但未配置 DEPLOY_SCRIPT，请手动部署"})


# ---------- 定时文章一键提前公开（v2.8.0）----------
@api_bp.route("/post/<int:post_id>/publish-now", methods=["POST"])
def publish_now(post_id):
    """立即发布一篇「定时待发布」的文章（清空 scheduled_at 并翻 published）。

    鉴权：登录用户且对文章有编辑权（管理员全部 / 普通用户仅自己文章）。
    立即发布后触发新文章推送（Telegram/企业微信）+ 邮件群发订阅者（均静默失败）。
    安全：未授权返回 403；普通用户只能操作自己 author_id 的文章。
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    u = db.session.get(User, uid)
    if not u:
        return jsonify({"error": "请先登录"}), 401
    p = db.session.get(Post, post_id)
    if not p:
        return jsonify({"error": "文章不存在"}), 404
    # 权限：管理员全部可操作；普通用户仅自己文章
    if not u.is_admin_role and not (p.author_id is not None and p.author_id == u.id):
        return jsonify({"error": "没有权限操作这篇文章"}), 403
    if p.published:
        return jsonify({"ok": True, "message": "文章已处于发布状态", "published": True})
    p.published = True
    p.scheduled_at = None  # 清空定时，避免后台线程重复触发
    db.session.commit()
    # 发布后推送 + 邮件（与正常发布一致，全部静默）
    try:
        import notify as _notify
        _notify.notify_new_post(p, current_app.config.get("SITE_URL", ""))
    except Exception:
        pass
    try:
        import mail_notify as _mail
        _mail.notify_subscribers_async(p)
    except Exception:
        pass
    return jsonify({"ok": True, "message": "已立即发布", "published": True})
