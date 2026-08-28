"""前台公开页面 + 评论提交接口。"""
import json
import urllib.request
import urllib.parse

from flask import (Blueprint, render_template, request, redirect, url_for,
                   abort, flash, current_app, Response, jsonify, session)
from markupsafe import escape

from models import db, Post, Category, Tag, Comment, Setting, User, ROLE_USER, visible_posts_query
from utils import (make_slug, render_post_html, safe_redirect, rate_limit,
                   client_key, validate_password, get_setting)
# v3.1.0：登录审计（log_login_attempt 定义于 admin 模块，admin 不依赖 routes，无循环）
from admin import log_login_attempt

main_bp = Blueprint("main", __name__)


# ---------- 反爬限流保护（v3.8.0）----------
@main_bp.before_request
def _bot_guard_before():
    """前台请求进入前做反爬限流检查；放行返回 None，拦截返回 429 响应。"""
    try:
        from bot_guard import check_bot_guard
        res = check_bot_guard()
    except Exception:
        return None
    if res:
        from flask import make_response
        resp = make_response("429 Too Many Requests", 429)
        resp.headers["Retry-After"] = "60"
        return resp


# ---------- 用户注册 / 登录 / 登出 ----------
@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """前台注册：任何人可注册普通用户，注册后自动登录。"""
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    if request.method == "POST":
        # 限流：同一 IP 60 秒内最多 10 次注册尝试
        if not rate_limit(client_key("register"), limit=10, window=60):
            flash("操作过于频繁，请稍后再试")
            return redirect(url_for("main.register"))
        # 注册开关：生产可设 BLOG_OPEN_REGISTER=false 关闭公开注册
        if not current_app.config.get("BLOG_OPEN_REGISTER"):
            flash("本站已关闭公开注册")
            return redirect(url_for("main.register"))
        # 验证码：与 /api/auth/register 一致，杜绝绕过 SPA 直打本路由跳过验证码（独立复审 M1）
        cap_err = _captcha_fail("register")
        if cap_err:
            flash(cap_err)
            return redirect(url_for("main.register"))
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username or not password:
            flash("用户名和密码不能为空")
        elif len(username) < 2 or len(username) > 20:
            flash("用户名长度需在 2-20 个字符")
        elif _weak_password_text(password):
            flash(_weak_password_text(password))
        elif password != confirm:
            flash("两次输入的密码不一致")
        elif User.query.filter_by(username=username).first():
            flash("该用户名已被注册")
        else:
            u = User(username=username, email=email, role=ROLE_USER)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"] = u.id
            flash("注册成功，欢迎你！")
            return redirect(url_for("main.index"))
    return render_template("register.html",
                           captcha_on=_captcha_required("register"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    """前台登录：普通用户/管理员/超级管理员都能登录（后台权限另有判定）。"""
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    if request.method == "POST":
        # 全量审计加固：登录限流（同 IP 60 秒最多 10 次尝试，防暴力破解）
        if not rate_limit(client_key("login"), limit=10, window=60):
            flash("尝试过于频繁，请稍后再试")
            return render_template("login.html"), 429
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password", "")
        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            log_login_attempt(username, True)
            session["user_id"] = u.id
            flash(f"欢迎回来，{u.username}！")
            nxt = safe_redirect(request.args.get("next"), url_for("main.index"))
            return redirect(nxt)
        log_login_attempt(username, False)
        flash("用户名或密码错误")
    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("main.index"))


def _weak_password_text(raw):
    """v3.1.6：前台注册密码强度校验（弱密码黑名单 + 复杂度）。返回错误文案，通过返回空串。"""
    try:
        from flask import current_app as _app
        cfg = _app.config
        ok, err = validate_password(
            raw or "", min_len=8,
            strong=cfg.get("STRONG_PASSWORD", True),
            mixed_case=cfg.get("STRONG_PASSWORD_MIXED_CASE", False),
        )
        return "" if ok else err
    except Exception:
        return "" if len(raw or "") >= 8 else "密码至少 8 位"


def _captcha_required(scope=None):
    """当前场景是否需要图形验证码（与 API 路由口径一致）。"""
    try:
        from security import captcha_required as _cr
        return bool(_cr(scope))
    except Exception:
        return False


def _captcha_fail(scope):
    """校验 SSR 表单提交的验证码。

    与 /api/auth/register、/api/post/<slug>/comment 保持一致的判定：
    未启用验证码 → 返回 None（放行）；已通过一次性票据或答案校验 → None（放行）；
    否则返回错误文案，由调用方 flash 并跳回。注意 fail-closed，异常即视为未通过。
    """
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if not captcha_required(scope):
        return None
    if consume_captcha_pass():
        return None
    code = (request.form.get("captcha") or "").strip()
    if code and verify_captcha(code):
        return None
    return "请先完成验证码校验"


def _render(post):
    """把文章的 Markdown 正文渲染成 HTML（已做 XSS 白名单清理），挂到 post.html 上。

    v3.9.1：走渲染缓存（post.content_html），正文未变时不再重复渲染。
    """
    post.html = render_post_html(post)
    return post


@main_bp.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["POSTS_PER_PAGE"]
    pagination = (
        visible_posts_query()
        .order_by(Post.is_pinned.desc(), Post.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    posts = [_render(p) for p in pagination.items]
    return render_template("index.html", posts=posts, pagination=pagination)


@main_bp.route("/post/<slug>")
def post(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 阅读量 +1（防刷：同 IP 24h 内只计一次真实阅读）
    from app import count_unique_view
    from stats import client_ip
    if count_unique_view(p.id, client_ip()):
        p.views += 1
        db.session.commit()
    _render(p)
    comments = p.comments.filter_by(approved=True).order_by(Comment.created_at.asc()).all()
    # SEO：JSON-LD 结构化数据 + Open Graph（v3.8.0）
    base = (current_app.config.get("SITE_URL") or request.url_root.rstrip("/")).rstrip("/")
    author_name = (p.author.username if p.author
                   else get_setting("site_name", current_app.config.get("SITE_TITLE", "我的博客")))
    json_ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": p.title,
        "datePublished": p.created_at.isoformat(),
        "dateModified": (p.updated_at or p.created_at).isoformat(),
        "author": {"@type": "Person", "name": author_name},
        "publisher": {"@type": "Organization",
                      "name": current_app.config.get("SITE_TITLE", "我的博客")},
        "description": (p.seo_description or p.summary or "")[:200],
        "url": f"{base}/post/{p.slug}",
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{base}/post/{p.slug}"},
    }
    if p.cover:
        json_ld["image"] = [p.cover]
    og = {
        "title": p.title,
        "description": (p.seo_description or p.summary or "")[:200],
        "url": f"{base}/post/{p.slug}",
        "image": p.cover or "",
        "type": "article",
    }
    return render_template("post.html", post=p, comments=comments, json_ld=json_ld, og=og,
                           comment_captcha_on=_captcha_required("comment"))


@main_bp.route("/post/<slug>/comment", methods=["POST"])
def add_comment(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 限流：同一 IP 60 秒内最多 10 条评论
    if not rate_limit(client_key("comment"), limit=10, window=60):
        flash("评论过于频繁，请稍后再试")
        return redirect(url_for("main.post", slug=slug) + "#comments")
    # 验证码：与 /api/post/<slug>/comment 一致，杜绝绕过 SPA 直打本路由跳过验证码（独立复审 M1）
    cap_err = _captcha_fail("comment")
    if cap_err:
        flash(cap_err)
        return redirect(url_for("main.post", slug=slug) + "#comments")
    # 已登录用户自动用其用户名，否则用表单里的昵称
    author = ""
    uid = session.get("user_id")
    if uid:
        u = db.session.get(User, uid)
        if u:
            author = u.username
    author = author or (request.form.get("author") or "").strip() or "匿名"
    content = (request.form.get("content") or "").strip()
    if not content:
        flash("评论内容不能为空")
        return redirect(url_for("main.post", slug=slug) + "#comments")
    from utils import parse_device
    from stats import client_ip, cached_region
    ip = client_ip()
    c = Comment(post_id=p.id, author=author[:80], content=content,
                ip=ip, region=cached_region(ip),
                device=parse_device(request.headers.get("User-Agent", ""))[:120])
    db.session.add(c)
    db.session.commit()
    # v3.9.0 M1：新评论写入 → 触发插件事件（订阅者异常已隔离）
    try:
        from plugins.signals import emit_comment_created
        emit_comment_created(c)
    except Exception:
        pass
    flash("评论成功，感谢留言！")
    return redirect(url_for("main.post", slug=slug) + "#comments")


@main_bp.route("/post/<slug>/like", methods=["POST"])
def like_post(slug):
    """文章点赞：服务端计数 +1（前端用 localStorage 去重，防止同一浏览器重复点）。"""
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 限流：同一 IP 对单篇文章 60 秒内最多 20 次点赞（防刷量）
    if not rate_limit(client_key("like:" + slug), limit=20, window=60):
        return jsonify(likes=p.likes)
    p.likes = (p.likes or 0) + 1
    db.session.commit()
    return jsonify(likes=p.likes)


@main_bp.route("/category/<slug>")
def category(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    posts = [_render(p) for p in visible_posts_query().filter_by(category_id=cat.id).order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()]
    return render_template("archive.html", title=cat.name, posts=posts, kind="分类")


@main_bp.route("/tag/<slug>")
def tag(slug):
    t = Tag.query.filter_by(slug=slug).first_or_404()
    posts = [_render(p) for p in visible_posts_query().filter(Post.tags.any(id=t.id)).order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()]
    return render_template("archive.html", title=t.name, posts=posts, kind="标签")


@main_bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    results = []
    if q:
        like = f"%{q}%"
        rows = (
            visible_posts_query().filter(db.or_(Post.title.like(like), Post.content.like(like)))
            .order_by(Post.is_pinned.desc(), Post.created_at.desc())
            .all()
        )
        results = [_render(p) for p in rows]
    return render_template("search.html", q=q, results=results)


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/links")
def links():
    return render_template("links.html")


@main_bp.route("/archive")
def archive():
    """归档时间线：全部已发布文章按「年 → 月」分组倒序展示。"""
    posts = visible_posts_query().order_by(Post.is_pinned.desc(), Post.created_at.desc()).all()
    groups = {}  # {年份: {月份: [文章...]}}
    for p in posts:
        groups.setdefault(p.created_at.year, {}).setdefault(p.created_at.month, []).append(p)
    timeline = []
    for y in sorted(groups.keys(), reverse=True):
        months = [
            {"month": m, "posts": groups[y][m]}
            for m in sorted(groups[y].keys(), reverse=True)
        ]
        timeline.append({"year": y, "months": months})
    return render_template("archive_timeline.html", timeline=timeline, total=len(posts))


# 天气代码 → 中文描述（Open-Meteo WMO 编码）
_WEATHER_TEXT = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴",
}


_WTTR_TEXT = {
    113: "晴", 116: "多云", 119: "阴", 122: "阴", 143: "雾", 149: "霾",
    176: "小雨", 179: "雨夹雪", 182: "雨夹雪", 185: "冻雨",
    200: "雷阵雨", 227: "小雪", 230: "大雪", 248: "雾",
    260: "冻雾", 263: "毛毛雨", 266: "毛毛雨", 281: "冻毛毛雨",
    284: "冻毛毛雨", 293: "小雨", 296: "小雨", 299: "中雨", 302: "中雨",
    305: "大雨", 308: "大雨", 311: "冻雨", 314: "冻雨",
    317: "雨夹雪", 320: "雨夹雪", 323: "小雪", 326: "小雪",
    329: "大雪", 332: "大雪", 335: "大雪", 338: "大雪",
    350: "冰粒", 353: "阵雨", 356: "阵雨", 359: "强阵雨",
    362: "阵雨夹雪", 365: "阵雨夹雪", 368: "阵雪", 371: "阵雪",
    374: "冰粒", 377: "冰粒", 386: "雷阵雨", 389: "雷阵雨",
    392: "雷阵雪", 395: "雷阵雪",
}


@main_bp.route("/api/weather")
def api_weather():
    """天气接口（双源容灾，全部免费无需 Key）：
    - 主源 wttr.in：国内通常可直连、响应快、支持中文城市名与坐标；
    - 兜底 Open-Meteo：主源失败时用坐标查天气（WMO code）。
    传参：
    - city=城市名（手动查询 / 默认城市）
    - lat&lon（浏览器定位）
    - 都不传：用后台设置的默认坐标与城市名
    返回：{name, city, temp, code, description, lat, lon}
    """
    # 限流：公开 GET 接口，防止被滥用为放大/探测（独立复审 M4 纵深防御）
    if not rate_limit(client_key("weather"), limit=60, window=60):
        return jsonify(error="请求过于频繁，请稍后再试"), 429

    # ---- 坐标校验：必须是合法浮点且落在合理经纬度范围，否则拒绝 ----
    # 防止未校验的用户输入直接拼进出站 URL 造成 SSRF / CRLF 注入（独立复审 M4）
    def _safe_coord(v, lo, hi):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if lo <= f <= hi:
            return f
        return None

    lat_raw = request.args.get("lat")
    lon_raw = request.args.get("lon")
    city = (request.args.get("city") or "").strip()
    if city and len(city) > 80:
        return jsonify(error="城市名过长"), 400
    # 仅当两者都提供且合法时才进入坐标模式；否则置空走默认/城市模式
    lat = _safe_coord(lat_raw, -90.0, 90.0) if lat_raw is not None else None
    lon = _safe_coord(lon_raw, -180.0, 180.0) if lon_raw is not None else None
    if (lat is None) != (lon is None):
        lat = lon = None

    def _http_json(url, timeout=6):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))

    def _wttr(q):
        """wttr.in 查询：q 为城市名或「纬度,经度」。返回 (temp, desc_zh, code)。"""
        d = _http_json(
            f"https://wttr.in/{urllib.parse.quote(str(q))}?format=j1&lang=zh", timeout=7
        )
        cc = (d.get("current_condition") or [{}])[0]
        temp = float(cc["temp_C"])
        wcode = cc.get("weatherCode")
        desc = _WTTR_TEXT.get(int(wcode)) if wcode else None
        if not desc:
            try:
                desc = cc["lang_zh"][0]["value"]
            except Exception:
                desc = (cc.get("weatherDesc") or [{"value": "未知"}])[0].get("value", "未知")
        return temp, desc, wcode

    # ---- 1) 手动输入城市名：wttr.in 直接查 ----
    if city:
        try:
            temp, desc, code = _wttr(city)
            return jsonify(name=city, city=city, temp=temp, code=code,
                           description=desc, lat=None, lon=None)
        except Exception:
            return jsonify(error="找不到该城市或天气获取失败"), 502

    # ---- 2) 坐标模式（浏览器定位）：wttr.in 坐标查询优先，Open-Meteo 兜底 ----
    if lat and lon:
        name = "我的位置"
        try:
            g = _http_json(
                f"https://api.bigdatacloud.net/data/reverse-geocode-client"
                f"?latitude={urllib.parse.quote(str(lat))}"
                f"&longitude={urllib.parse.quote(str(lon))}&localityLanguage=zh",
                timeout=5,
            )
            nm = g.get("city") or g.get("locality") or g.get("principalSubdivision")
            ctry = g.get("countryName")
            if nm:
                name = nm + (f"·{ctry}" if ctry else "")
        except Exception:
            pass  # 反查失败就保留「我的位置」
        try:
            temp, desc, code = _wttr(f"{lat},{lon}")
            return jsonify(name=name, city=name, temp=temp, code=code,
                           description=desc, lat=lat, lon=lon)
        except Exception:
            pass  # wttr 失败 → open-meteo 兜底
    # ---- 3) 默认模式：后台设置的城市/坐标 ----
    else:
        s = {s.key: s.value for s in Setting.query.all()}
        # 注意：用 `or` 兜底——键存在但值为空串时也要用默认值（保存设置页可能清空过）
        lat = s.get("weather_lat") or "39.9042"
        lon = s.get("weather_lon") or "116.4074"
        name = s.get("weather_city") or "北京"
        if name != "本地":
            try:
                temp, desc, code = _wttr(name)
                return jsonify(name=name, city=name, temp=temp, code=code,
                               description=desc, lat=lat, lon=lon)
            except Exception:
                pass  # wttr 失败 → open-meteo 兜底

    # ---- 兜底：Open-Meteo（WMO code）----
    try:
        d = _http_json(
            f"https://api.open-meteo.com/v1/forecast?latitude={urllib.parse.quote(str(lat))}"
            f"&longitude={urllib.parse.quote(str(lon))}"
            f"&current=temperature_2m,weather_code",
            timeout=5,
        )
        temp = d["current"]["temperature_2m"]
        code = d["current"]["weather_code"]
    except Exception:
        return jsonify(error="天气获取失败"), 502
    return jsonify(
        name=name, city=name, temp=temp, code=code,
        description=_WEATHER_TEXT.get(code, "未知"),
        lat=lat, lon=lon,
    )


def _site_base():
    """返回站点对外绝对地址前缀（去尾部斜杠）。"""
    return (current_app.config.get("SITE_URL") or request.url_root.rstrip("/")).rstrip("/")


@main_bp.route("/feed.xml")
def feed():
    """RSS 2.0 订阅源：取最近 20 篇已发布文章。"""
    posts = (visible_posts_query()
             .order_by(Post.is_pinned.desc(), Post.created_at.desc()).limit(20).all())
    base = _site_base()
    site_title = current_app.config.get("SITE_TITLE", "我的博客")
    desc_row = Setting.query.filter_by(key="site_description").first()
    desc = desc_row.value if desc_row else site_title

    items = []
    for p in posts:
        link = f"{base}/post/{p.slug}"
        pub = p.created_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        summary = (p.summary or (p.content or "")[:200]).strip()
        author = (p.author.username if p.author else site_title)
        cat = p.category.name if p.category else ""
        items.append(
            "    <item>\n"
            f"      <title>{escape(p.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid>{escape(link)}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <dc:creator>{escape(author)}</dc:creator>\n"
            f"      <category>{escape(cat)}</category>\n"
            f"      <description>{escape(summary)}</description>\n"
            "    </item>"
        )
    last = posts[0].created_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if posts else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <channel>\n"
        f"    <title>{escape(site_title)}</title>\n"
        f"    <link>{escape(base + '/')}</link>\n"
        f"    <description>{escape(desc)}</description>\n"
        f"    <lastBuildDate>{last}</lastBuildDate>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n"
        "</rss>\n"
    )
    return Response(xml, mimetype="application/rss+xml")


@main_bp.route("/sitemap.xml")
def sitemap():
    """站点地图（v3.8.0 增强：lastmod / changefreq / priority / 封面图）。"""
    base = _site_base()
    urls = [
        (base + "/", "daily", "1.0"),
        (base + "/about", "monthly", "0.5"),
        (base + "/links", "weekly", "0.6"),
    ]
    for p in visible_posts_query().all():
        urls.append((f"{base}/post/{p.slug}", "weekly", "0.8",
                     (p.updated_at or p.created_at).strftime("%Y-%m-%d"), p.cover))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for item in urls:
        u, freq, prio = item[0], item[1], item[2]
        extra = ""
        if len(item) > 3 and item[3]:
            extra += f"<lastmod>{item[3]}</lastmod>"
        if len(item) > 4 and item[4]:
            extra += f'<image:image><image:loc>{escape(item[4])}</image:loc></image:image>'
        lines.append(f"  <url><loc>{escape(u)}</loc>{extra}"
                     f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


@main_bp.route("/robots.txt")
def robots():
    """告诉搜索引擎抓取规则（v3.8.0 增强：可屏蔽指定坏 Bot）。"""
    base = _site_base()
    lines = ["User-agent: *", "Allow: /"]
    bad_bots = get_setting("seo_block_bots", "")
    if bad_bots:
        for b in [x.strip() for x in bad_bots.split(",") if x.strip()]:
            lines.append(f"User-agent: {b}")
            lines.append("Disallow: /")
    lines.append(f"Sitemap: {base}/sitemap.xml")
    return Response("\n".join(lines), mimetype="text/plain")
