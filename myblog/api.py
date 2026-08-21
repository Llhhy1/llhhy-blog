"""前后端分离用的 JSON 接口蓝图（/api/*）。

前端（Astro 静态站）通过这里拿数据；后台管理仍走原 admin 蓝图（服务端渲染）。
所有返回均为 JSON；跨域头由 app.py 的 after_request 统一加。
"""
import json

from flask import Blueprint, request, jsonify, current_app, session
from markupsafe import escape

from models import db, Post, Category, Tag, Comment, FriendLink, Setting, User, ROLE_USER, \
    Moment, MomentComment, SocialAccount, Series, Announcement, Guestbook, Subscriber
from utils import render_markdown, clean_html, rate_limit, client_key
import stats

api_bp = Blueprint("api", __name__, url_prefix="/api")


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
    """登录：Flask session 与 Astro 前端通过 header X-User-Id 共用同一会话。"""
    session["user_id"] = u.id
    return jsonify({"ok": True, "user": _user_pub(u)})


@api_bp.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次注册尝试
    if not rate_limit(client_key("api_register"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    # 注册开关：生产可设 BLOG_OPEN_REGISTER=false 关闭公开注册
    if not current_app.config.get("BLOG_OPEN_REGISTER"):
        return jsonify({"error": "本站已关闭公开注册"}), 403
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 20:
        return jsonify({"error": "用户名长度需在 2-20 个字符"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
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
        return jsonify({"error": "用户名或密码错误"}), 401
    return _login_user(u)


@api_bp.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@api_bp.route("/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None}), 200
    u = db.session.get(User, uid)
    if not u:
        session.pop("user_id", None)
        return jsonify({"user": None}), 200
    return jsonify({"user": _user_pub(u)}), 200


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
        "category": {"name": p.category.name, "slug": p.category.slug} if p.category else None,
        "tags": [{"name": t.name, "slug": t.slug} for t in p.tags],
    }


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
        "categories": [
            {"name": c.name, "slug": c.slug,
             "count": c.posts.filter_by(published=True).count()}
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
            "posts": Post.query.filter_by(published=True).count(),
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

    query = Post.query.filter_by(published=True)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Post.title.ilike(like), Post.summary.ilike(like), Post.content.ilike(like))
        )
    query = query.order_by(Post.created_at.desc())
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
    p = Post.query.filter_by(slug=slug, published=True).first_or_404()
    # 阅读量 +1
    p.views += 1
    db.session.commit()

    data = _post_summary(p)
    data["html"] = _render_html(p.content)
    data["comments"] = [_comment(c) for c in p.comments.order_by(Comment.created_at.asc())]
    # 系列上下篇导航
    if p.series_id and p.series:
        s_posts = p.series.posts.filter_by(published=True).order_by(Post.created_at.asc()).all()
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
         "count": c.posts.filter_by(published=True).count()}
        for c in Category.query.order_by(Category.id).all()
    ])


@api_bp.route("/tags")
def tags():
    return jsonify([
        {"name": t.name, "slug": t.slug, "count": len(t.posts)}
        for t in Tag.query.order_by(Tag.id).all()
    ])


@api_bp.route("/category/<slug>")
def posts_by_category(slug):
    c = Category.query.filter_by(slug=slug).first_or_404()
    items = Post.query.filter_by(category_id=c.id, published=True)\
        .order_by(Post.created_at.desc()).all()
    return jsonify({"name": c.name, "slug": c.slug,
                    "items": [_post_summary(p) for p in items]})


@api_bp.route("/tag/<slug>")
def posts_by_tag(slug):
    t = Tag.query.filter_by(slug=slug).first_or_404()
    items = [p for p in t.posts if p.published]
    items.sort(key=lambda p: p.created_at, reverse=True)
    return jsonify({"name": t.name, "slug": t.slug,
                    "items": [_post_summary(p) for p in items]})


# ---------- 归档时间线 ----------
@api_bp.route("/archive")
def archive():
    posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).all()
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


# ---------- 点赞 ----------
@api_bp.route("/post/<slug>/like", methods=["POST"])
def like(slug):
    p = Post.query.filter_by(slug=slug, published=True).first_or_404()
    # 限流：同一 IP 对单篇文章 60 秒内最多 20 次点赞（防刷量）
    if not rate_limit(client_key("api_like:" + slug), limit=20, window=60):
        return jsonify({"likes": p.likes})
    p.likes += 1
    db.session.commit()
    return jsonify({"likes": p.likes})


# ---------- 评论提交 ----------
@api_bp.route("/post/<slug>/comment", methods=["POST"])
def comment(slug):
    p = Post.query.filter_by(slug=slug, published=True).first_or_404()
    # 限流：同一 IP 60 秒内最多 10 条评论
    if not rate_limit(client_key("api_comment"), limit=10, window=60):
        return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
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
    from utils import parse_device
    ip = stats.client_ip()
    c = Comment(post_id=p.id, author=author[:80], content=content, approved=True,
                ip=ip, region=stats.cached_region(ip),
                device=parse_device(request.headers.get("User-Agent", ""))[:120],
                parent_id=parent_id or None, reply_to=reply_to[:80])
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "comment": _comment(c)}), 201


# ---------- 访问统计（埋点 + 汇总）----------
@api_bp.route("/stats/visit", methods=["POST"])
def stats_visit():
    """前端每次路由变化时上报一次访问（fire-and-forget）。"""
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
    """记录搜索词。"""
    data = request.get_json(silent=True) or {}
    stats.record_search(data.get("keyword") or "")
    return jsonify({"ok": True})


@api_bp.route("/stats/read", methods=["POST"])
def stats_read():
    """记录一次文章阅读（同一访客重复读会累加）。"""
    data = request.get_json(silent=True) or {}
    slug = (data.get("slug") or "").strip()
    p = Post.query.filter_by(slug=slug).first() if slug else None
    if p:
        stats.record_read(p.id, stats.client_ip())
    return jsonify({"ok": True})


@api_bp.route("/stats/summary")
def stats_summary():
    """统计汇总（累计访问 / 区域排行 / 热读文章 / 常搜词 / 时段分布）。"""
    return jsonify(stats.compute_summary())


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
         "cover": s.cover or "", "count": s.posts.filter_by(published=True).count()}
        for s in sers
    ])


@api_bp.route("/series/<slug>")
def series_detail(slug):
    s = Series.query.filter_by(slug=slug).first_or_404()
    posts = s.posts.filter_by(published=True).order_by(Post.created_at.asc()).all()
    return jsonify({
        "slug": s.slug, "name": s.name, "description": s.description or "",
        "cover": s.cover or "",
        "posts": [_post_summary(p) for p in posts],
    })


# ---------- 相关文章推荐（按标签重合度 + 同分类，纯算法零依赖，B1）----------
@api_bp.route("/post/<slug>/related")
def related_posts(slug):
    p = Post.query.filter_by(slug=slug, published=True).first_or_404()
    p_tags = set(t.id for t in p.tags)
    scored = []
    for c in Post.query.filter(Post.published == True, Post.id != p.id).all():
        c_tags = set(t.id for t in c.tags)
        score = len(p_tags & c_tags)
        if p.category_id and p.category_id == c.category_id:
            score += 1
        if score <= 0:
            continue
        scored.append((score, c))
    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    return jsonify({"items": [_post_summary(c) for _, c in scored[:5]]})


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


# ---------- 邮件订阅（Newsletter，C3）----------
@api_bp.route("/subscribe", methods=["POST"])
def subscribe():
    if not rate_limit(client_key("api_subscribe"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    import re as _re
    if not email or not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "邮箱格式不正确"}), 400
    if Subscriber.query.filter_by(email=email).first():
        return jsonify({"ok": True, "message": "你已经订阅过啦"})
    db.session.add(Subscriber(email=email[:160]))
    db.session.commit()
    return jsonify({"ok": True, "message": "订阅成功，新文章发布时会邮件通知你"}), 201


# ---------- 全文搜索（FTS5 优先，失败回退 LIKE，B5）----------
@api_bp.route("/search")
def search_api():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"items": [], "total": 0, "engine": "none"})
    try:
        import fts as fts_mod
        ids = fts_mod.search(q)
    except Exception:
        ids = None
    if ids is not None:
        posts = [db.session.get(Post, i) for i in ids]
        posts = [p for p in posts if p and p.published]
        return jsonify({"items": [_post_summary(p) for p in posts], "total": len(posts), "engine": "fts5"})
    like = f"%{q}%"
    rows = (Post.query.filter(Post.published == True,
                              db.or_(Post.title.ilike(like), Post.summary.ilike(like), Post.content.ilike(like)))
            .order_by(Post.created_at.desc()).limit(30).all())
    return jsonify({"items": [_post_summary(p) for p in rows], "total": len(rows), "engine": "like"})


# ---------- Webhook 自动部署（GitHub push → 宝塔拉取，D3）----------
@api_bp.route("/webhook/deploy", methods=["POST"])
def webhook_deploy():
    """仅做密钥鉴权 + 返回成功；真正的 git pull / 重启由宝塔 Webhook 或计划任务完成。
    配置环境变量 WH_DEPLOY_SECRET；GitHub Webhook 在 Header 带 X-Deploy-Token 或在 URL 带 ?token=。"""
    secret = current_app.config.get("WH_DEPLOY_SECRET")
    if not secret:
        return jsonify({"error": "服务器未配置部署密钥 WH_DEPLOY_SECRET"}), 403
    token = request.headers.get("X-Deploy-Token") or request.args.get("token") or ""
    import hmac
    if not hmac.compare_digest(token, secret):
        return jsonify({"error": "密钥错误"}), 403
    return jsonify({"ok": True, "message": "部署触发已授权，请在服务器侧配置 git pull 拉取最新代码"})
