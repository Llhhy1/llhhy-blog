"""
"""

import datetime
import hashlib
import logging
import re as _re
from flask import request, jsonify, current_app, session, Response
from markupsafe import escape

logger = logging.getLogger(__name__)

from .common import (api_bp, db, Post, PostTag, Category, Tag, Comment, ReadLog, Setting, User, visible_posts_query, _current_user_or_none, _post_summary, _comment, _render_html, rate_limit, client_key, lang_dedup, paged_posts, _DISPLAY_ORDER)
from models import hreflang_alternates
import stats  # myblog/stats.py：client_ip / cached_region（浏览量去重与评论归属地）
from utils import fmt_bj, to_beijing, BEIJING_TZ, site_base

# ---------- 文章列表（分页 + 搜索）----------
# v4.0.0：匿名列表接口限流（审计【低危 7】）。此前首页列表**匿名且无限流**，
# 而它又是全站 QPS 最高的一类端点，任意脚本都能无成本地把全表文章刷出来。
# 阈值按「真人翻页」给足余量：60 秒 120 次 ≈ 每秒 2 次，正常浏览/翻页打不到。
_LIST_RATE = (120, 60)


@api_bp.route("/posts")
def posts():
    if not rate_limit(client_key("api_posts"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("POSTS_PER_PAGE", 8)
    q = (request.args.get("q") or "").strip()

    query = visible_posts_query()
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Post.title.ilike(like), Post.summary.ilike(like), Post.content.ilike(like))
        )
    # v3.21.0 内容多语言：?lang= 下按语言去重，避免同组多语言重复出现。
    # v4.0.0：去重与分页一起在 SQL 侧完成（见 common.paged_posts），
    # 不再 `.all()` 全量物化后在 Python 切片。
    lang = (request.args.get("lang") or "").strip()
    page_items, total = paged_posts(query, page=page, per_page=per_page, lang=lang)
    pages = (total + per_page - 1) // per_page if per_page else 1
    return jsonify({
        "items": [_post_summary(p) for p in page_items],
        "page": max(1, page or 1),
        "pages": pages,
        "total": total,
        "per_page": per_page,
    })

# ---------- 文章详情（含渲染后的 HTML 与评论）----------
@api_bp.route("/post/<slug>")
def post_detail(slug):
    # v3.0.0 功能13：登录的超级管理员可查看自己的隐私文章；其余人（含未登录）一律 404
    _u = _current_user_or_none()
    p = visible_posts_query(user=_u).filter_by(slug=slug).first_or_404()
    # v3.21.0 内容多语言：?lang= 请求同组译文（不可见则回退当前文章）
    req_lang = (request.args.get("lang") or "").strip()
    if req_lang and req_lang != (p.lang or "zh") and p.translation_group:
        alt = visible_posts_query(user=_u).filter_by(
            translation_group=p.translation_group, lang=req_lang).first()
        if alt:
            p = alt
    # 阅读量 +1（防刷：同 IP 24h 内只计一次真实阅读）
    from app import count_unique_view
    from gamify import award_interaction, READER_COOKIE, READER_COOKIE_MAXAGE
    _reader_cookie = None
    if count_unique_view(p.id, stats.client_ip()):
        p.views += 1
        db.session.commit()
        # v3.21.0 gamification：真实阅读加积分（匿名/登录读者，cookie 标识）
        _reader_cookie = award_interaction("read", p.id)

    data = _post_summary(p)
    data["html"] = _render_html(p)  # v3.9.1：走正文渲染缓存（content_html）
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
    # v3.21.0 内容多语言：本篇语言 + 同组其他语言入口（前端切换器 / hreflang 用）
    data["lang"] = p.lang or "zh"
    data["translation_group"] = p.translation_group or ""
    data["translations"] = (
        [{"lang": m.lang, "slug": m.slug, "title": m.title}
         for m in Post.in_group(p.translation_group) if m.id != p.id]
        if p.translation_group else []
    )
    resp = jsonify(data)
    if _reader_cookie:
        resp.set_cookie(READER_COOKIE, _reader_cookie, max_age=READER_COOKIE_MAXAGE,
                        httponly=True, samesite="Lax", path="/")
    return resp

# ---------- 分类 / 标签 ----------
def _count_by(assoc_col, visible_only):
    """返回 {tag_id: (文章数, 总阅读量)} —— 一条 GROUP BY 取代 N+1 次惰性加载。

    v4.0.0（审计【低危 7】）：原实现逐个 `for t in Tag.query.all(): len(t.posts)`，
    每个标签触发一次 `post_tag` 关联查询 + 一次全量 posts 惰性加载，标签越多越慢，
    且 `hot-tags` 还会在 Python 里把每篇文章的 ORM 对象都摊开求和。

    `assoc_col` 传 `PostTag.tag_id`；`visible_only=True` 时只统计前台可见文章
    （与 `visible_posts_query()` 同口径），False 则统计全部（含回收站/隐私，
    用于 `/api/tags` 保持其历史口径）。
    """
    q = db.session.query(
        assoc_col.label("tid"),
        db.func.count(db.distinct(PostTag.post_id)).label("n"),
        db.func.coalesce(db.func.sum(db.func.coalesce(Post.views, 0)), 0).label("v"),
    ).join(Post, Post.id == PostTag.post_id)
    if visible_only:
        q = q.filter(Post.id.in_(visible_posts_query().with_entities(Post.id)))
    return {r[0]: (r[1], r[2] or 0) for r in q.group_by(assoc_col).all()}


@api_bp.route("/categories")
def categories():
    if not rate_limit(client_key("api_categories"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    # v4.0.0：一条 GROUP BY 取代「每个分类一次 count 查询」的 N+1。
    # 无可见文章的分类仍要列出（count=0），所以用 dict.get(id, 0) 兜底。
    counts = dict(visible_posts_query().filter(Post.category_id.isnot(None))
                  .with_entities(Post.category_id, db.func.count(Post.id))
                  .group_by(Post.category_id).all())
    return jsonify([
        {"name": c.name, "slug": c.slug, "count": counts.get(c.id, 0)}
        for c in Category.query.order_by(Category.id).all()
    ])


@api_bp.route("/tags")
def tags():
    if not rate_limit(client_key("api_tags"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    # 口径沿用历史行为：`len(t.posts)` 统计的是**全部**文章（含回收站/隐私）。
    counts = {tid: n for tid, (n, _v) in _count_by(PostTag.tag_id, visible_only=False).items()}
    return jsonify([
        {"name": t.name, "slug": t.slug, "count": counts.get(t.id, 0)}
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
    if not rate_limit(client_key("api_hot_tags"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    # v4.0.0：一条聚合查询取代「逐标签惰性加载全部文章再 Python 求和」。
    agg = _count_by(PostTag.tag_id, visible_only=True)
    if not agg:
        return jsonify({"items": []})
    # 排序前先按 tag id 归位：原实现遍历 `Tag.query.all()`（id 升序），
    # `rows.sort(key=weight, reverse=True)` 是**稳定排序**，同权重时 id 小的在前。
    # 这里先排 id 再用稳定排序，保证同权重下的相对顺序与旧实现一致。
    by_id = {t.id: t for t in Tag.query.filter(Tag.id.in_(list(agg))).all()}
    rows = []
    for tid in sorted(by_id):
        n, views = agg[tid]
        if n <= 0:
            continue
        t = by_id[tid]
        rows.append({"name": t.name, "slug": t.slug, "count": n,
                     "views": views, "weight": n * 2 + views // 1000})
    rows.sort(key=lambda x: x["weight"], reverse=True)
    return jsonify({"items": rows[:limit]})


@api_bp.route("/category/<slug>")
def posts_by_category(slug):
    if not rate_limit(client_key("api_by_category"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    c = Category.query.filter_by(slug=slug).first_or_404()
    # 分类页语义就是「列出该分类全部文章」，不做分页；物化量由分类自身规模封顶。
    items = visible_posts_query().filter_by(category_id=c.id)\
        .order_by(*_DISPLAY_ORDER).all()
    lang = (request.args.get("lang") or "").strip()
    items = lang_dedup(items, lang)
    return jsonify({"name": c.name, "slug": c.slug,
                    "items": [_post_summary(p) for p in items]})


@api_bp.route("/tag/<slug>")
def posts_by_tag(slug):
    if not rate_limit(client_key("api_by_tag"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    t = Tag.query.filter_by(slug=slug).first_or_404()
    items = visible_posts_query().filter(Post.tags.any(id=t.id)).order_by(*_DISPLAY_ORDER).all()
    lang = (request.args.get("lang") or "").strip()
    items = lang_dedup(items, lang)
    return jsonify({"name": t.name, "slug": t.slug,
                    "items": [_post_summary(p) for p in items]})

# ---------- RSS 按分类 / 标签订阅（v3.0.0 功能10）----------
def _rss_xml(posts, title, desc, base):
    """把文章列表拼成 RSS 2.0 XML（纯本地、无外部依赖），含作者/分类元数据。"""
    items = []
    for p in posts:
        link = f"{base}/post/{p.slug}"
        pub = fmt_bj(p.created_at, "%a, %d %b %Y %H:%M:%S") + " +0800"
        summary = escape((p.summary or (p.content or "")[:200]).strip())
        author = (p.author.username if p.author
                  else current_app.config.get("SITE_TITLE", "站长"))
        cat = p.category.name if p.category else ""
        # v3.21.0 内容多语言：译文组 hreflang 互链
        alts = "".join(
            f"      <atom:link rel='alternate' hreflang='{h}' href='{escape(u)}'/>\n"
            for h, u in hreflang_alternates(p, base)
        )
        items.append(
            "    <item>\n"
            f"      <title>{escape(p.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid>{escape(link)}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <dc:creator>{escape(author)}</dc:creator>\n"
            f"      <category>{escape(cat)}</category>\n"
            f"      <description>{summary}</description>\n"
            + alts +
            "    </item>"
        )
    last = fmt_bj(posts[0].created_at, "%a, %d %b %Y %H:%M:%S") + " +0800" if posts else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
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
    base = site_base()
    return _rss_xml(posts, f"{c.name} - RSS", f"{c.name} 分类文章更新", base)


@api_bp.route("/rss/tag/<slug>")
def rss_tag(slug):
    """标签 RSS：带该标签的已发布文章的订阅源。"""
    t = Tag.query.filter_by(slug=slug).first_or_404()
    posts = visible_posts_query().filter(Post.tags.any(id=t.id))\
        .order_by(Post.is_pinned.desc(), Post.created_at.desc()).limit(20).all()
    base = site_base()
    return _rss_xml(posts, f"{t.name} - RSS", f"标签「{t.name}」相关文章更新", base)
# ---------- 归档时间线 ----------
@api_bp.route("/archive")
def archive():
    # 归档页语义就是「按月列出全部文章」，无法分页；这里只加匿名限流封住刷取。
    if not rate_limit(client_key("api_archive"), limit=30, window=60):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    posts = visible_posts_query().order_by(*_DISPLAY_ORDER).all()
    timeline = {}
    for p in posts:
        y = fmt_bj(p.created_at, "%Y")
        m = fmt_bj(p.created_at, "%m")
        timeline.setdefault(y, {}).setdefault(m, []).append(_post_summary(p))
    # 转成有序列表，方便前端渲染
    result = []
    for y in sorted(timeline.keys(), reverse=True):
        months = []
        for m in sorted(timeline[y].keys(), reverse=True):
            months.append({"month": m, "posts": timeline[y][m]})
        result.append({"year": y, "months": months})
    return jsonify(result)

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
# R114 审计：单条评论正文上限。超出即拒，不截断——截断会让用户
# 以为提交成功却丢了内容，静默拒绝更诚实。
_MAX_COMMENT_LEN = 2000


@api_bp.route("/post/<slug>/comment", methods=["POST"])
def comment(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    # 限流：同一 IP 60 秒内最多 10 条评论
    if not rate_limit(client_key("api_comment"), limit=10, window=60):
        return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
    # R114 审计：限流挡不住「单条超长评论」——10 条/分钟仍可塞 5MB/条，
    # 而每条会被 `notify_mentioned()` 拆成上百条通知（每条一次 SELECT）。
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
    # R114 审计：评论正文**必须限长**。此前无上限，匿名可提交 5MB 正文
    # → 一条评论扇出成百上千条 @提及通知（每条一次 SELECT），并让通知表无限膨胀。
    if len(content) > _MAX_COMMENT_LEN:
        return jsonify({"error": "评论最多 %d 字" % _MAX_COMMENT_LEN}), 400
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
    # v3.15.3 功能1：邮箱字段处理（仅存 MD5 哈希，明文不落库）
    from utils import setting_bool as _setting_bool
    email_required = _setting_bool("comment_email_required", False)
    raw_email = (data.get("email") or "").strip()
    email_hash = ""
    if raw_email:
        if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", raw_email):
            return jsonify({"error": "请填写有效的电子邮箱"}), 400
        email_hash = hashlib.md5(raw_email.lower().encode()).hexdigest()
    elif email_required:
        return jsonify({"error": "请填写有效的电子邮箱"}), 400
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
                parent_id=parent_id or None, reply_to=reply_to[:80],
                email_hash=email_hash)
    db.session.add(c)
    db.session.commit()
    # v3.21.0 gamification：发表评论加积分（匿名/登录读者，cookie 标识）
    from gamify import award_interaction, READER_COOKIE, READER_COOKIE_MAXAGE
    _reader_cookie = award_interaction("comment", p.id)
    # v3.9.0 M1：新评论写入 → 触发插件事件（订阅者异常已隔离）
    try:
        from plugins.signals import emit_comment_created
        emit_comment_created(c)
    except Exception:
        pass
    # A4 站内 @ 通知：解析评论内容里 @username，给注册用户发通知
    notify_mentioned(content, f"/post/{p.slug}", author, post_id=p.id)
    resp = jsonify({"ok": True, "comment": _comment(c), "pending": require_approval})
    if _reader_cookie:
        resp.set_cookie(READER_COOKIE, _reader_cookie, max_age=READER_COOKIE_MAXAGE,
                        httponly=True, samesite="Lax", path="/")
    return resp, 201


@api_bp.route("/post/<slug>/comments")
def post_comments(slug):
    """评论分页 + 完整嵌套（v3.25.2 重写）。

    **v3.25.2 修掉一个真实的数据丢失缺陷**：原实现只查两层
    （`for t in tops: ... Comment.query.filter_by(parent_id=t.id)`），
    于是「回复的回复」—— 第三层及更深——**永远不会出现在返回里**。
    `Comment.parent_id` 是指向任意评论的自关联外键，前端也支持对回复再回复，
    所以**用户能创建、但 API 读不回来**：写进去了、界面上看不见，等于静默丢数据。
    实测造 5 层链 + 1 个分叉共 6 条，旧实现只返回 3 条（L0 + L1 + L1b）。

    现在改为：一次性取出该文全部已批准评论 → 内存建 parent_id→children 索引 →
    从顶层做深度优先遍历。**为什么一次性取全量而不是逐层递归查**：
    评论量小（生产库 comment 表 2 行），而 N+1 的查询次数会随深度线性增长。

    **排序**（`sort` 参数，v3.25.2）：`old`（默认，正序）/ `new`（倒序）/ `hot`（最热）。
    ⚠️ 走**白名单映射**而非把用户输入拼进 `order_by` —— 后者虽然此处
    （SQLAlchemy 表达式）不构成注入面，但白名单是唯一能同时挡住「未知排序键」
    与「未来有人改成字符串拼接」的做法。
    顶层与**每个子树内部**都按同一规则排（讨论串整体有序，不只是顶层）。

    **深度封顶**（`max_depth`，默认 4，上限 8）：**只作为「折叠阈值」回传给前端，
    后端绝不据此裁剪数据**。裁剪等于把「丢评论」从三层挪到四层，治标不治本；
    正确做法是全量返回 + 逐条带 `depth`，由前端决定显示到第几层、
    超出时渲染成「继续回复」而不是无限缩进。
    """
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    per_page = request.args.get("per_page", 20, type=int)
    if per_page <= 0 or per_page > 50:
        per_page = 20
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    if not rate_limit(client_key("api_post_comments"), limit=60, window=60):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429

    sort_key = (request.args.get("sort") or "old").strip().lower()
    if sort_key not in _COMMENT_SORTS:
        sort_key = "old"                       # 未知排序键回落默认，绝不把输入喂给 order_by
    max_depth = request.args.get("max_depth", 4, type=int)
    if max_depth <= 0 or max_depth > 8:
        max_depth = 4

    # total 只统计**顶层**：它驱动「共 N 条」与「加载更多」的终止条件。
    # 若把回复也计入，per_page=20 而顶层只有 2 条时，has_more 永远为真 → 死循环。
    total = Comment.query.filter_by(post_id=p.id, approved=True, parent_id=None).count()
    tops = (Comment.query.filter_by(post_id=p.id, approved=True, parent_id=None)
            .order_by(*_COMMENT_SORTS[sort_key])
            .paginate(page=page, per_page=per_page, error_out=False))

    all_rows = (Comment.query.filter_by(post_id=p.id, approved=True)
                .order_by(*_COMMENT_SORTS[sort_key]).all())
    children = {}
    for c in all_rows:
        if c.parent_id:
            children.setdefault(c.parent_id, []).append(c)

    items = []
    for t in tops.items:
        items.append(_comment(t, depth=0))
        _walk_thread(children, t.id, 1, items)
    return jsonify({
        "items": items,
        "page": tops.page,
        "per_page": tops.per_page,
        "total": total,
        "pages": tops.pages,
        "has_more": tops.has_next,
        "sort": sort_key,
        "max_depth": max_depth,
    })


# 排序白名单：键是 API 暴露的字符串，值是 SQLAlchemy 排序表达式。
# **绝不**用字符串拼 order_by（那是注入面）；也绝不在这里放用户可控的列名。
_COMMENT_SORTS = {
    "old": (Comment.created_at.asc(), Comment.id.asc()),     # id 兜底：同秒评论也稳定
    "new": (Comment.created_at.desc(), Comment.id.desc()),
    "hot": (Comment.likes.desc(), Comment.created_at.asc()),
}

# 遍历深度硬上限。正常讨论串远小于此；超过说明 parent_id 数据异常
#（成环或误操作），此时停止展开并记日志 —— 宁可少显示，也不把栈/响应撑爆。
_COMMENT_MAX_WALK = 24


def _walk_thread(children, parent_id, depth, out):
    """把 parent_id 的全部后代按深度优先追加到 out（每项带 depth）。

    `children` 是 parent_id → [Comment] 的索引（在调用方一次性建好）。
    用**显式栈**而非递归：深度不可控的链（脏数据）下递归会撞 Python 递归上限。
    """
    stack = [(parent_id, depth)]
    while stack:
        pid, d = stack.pop()
        if d > _COMMENT_MAX_WALK:
            logger.warning("[评论] 嵌套超过 %d 层，停止展开（parent_id=%s）——"
                           "请检查 parent_id 是否成环", _COMMENT_MAX_WALK, pid)
            return
        kids = children.get(pid) or []
        # 逆序入栈：栈是后进先出，逆序放才能让输出保持正序
        for k in reversed(kids):
            out.append(_comment(k, depth=d))
            stack.append((k.id, d + 1))


# ---------- 相关文章推荐（按标签重合度 + 同分类，纯算法零依赖，B1）----------
def _tag_overlap_subquery(tag_ids, exclude_post_id):
    """返回「与给定标签集合有交集的 (post_id, 重合数)」聚合子查询。

    一条 `GROUP BY post_id` 取代「把全部文章取出来、逐篇展开标签集合求交集」。
    """
    return (db.session.query(PostTag.post_id.label("pid"), db.func.count().label("n"))
            .filter(PostTag.post_id != exclude_post_id)
            .filter(PostTag.tag_id.in_(tag_ids))
            .group_by(PostTag.post_id).subquery())


def _category_bonus(category_id):
    """同分类加 1 分。⚠️ category_id 为空时必须返回常量 0 —— `Post.category_id == None`
    在 SQLAlchemy 里会编译成 `IS NULL`，会把**所有无分类文章**都算成同分类。"""
    if not category_id:
        return 0
    return db.case((Post.category_id == category_id, 1), else_=0)


# 打分榜内部的次级排序：同分时新的在前（与旧 Python `sort(reverse=True)` 同口径），
# id 兜底保证全序。**不**带 is_pinned —— 推荐位是「相关度」排序，不该被置顶污染。
_SCORE_TIEBREAK = (Post.created_at.desc(), Post.id.asc())


@api_bp.route("/post/<slug>/related")
def related_posts(slug):
    p = visible_posts_query().filter_by(slug=slug).first_or_404()
    if not rate_limit(client_key("api_related"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    # v4.0.0（审计【低危 7】）：原实现 `visible_posts_query().filter(Post.id != p.id).all()`
    # 把**全站可见文章**物化成 ORM 对象（每篇还要惰性加载 tags 集合）再在 Python 打分，
    # 只为取 5 篇。现在打分整体下推 SQL：标签重合数走聚合子查询、同分类加 1 分走
    # CASE，数据库只返回 5 行。
    # score = 标签重合数 + 同分类1分；只取 score > 0 的前 5 篇（与旧实现同口径）。
    p_tags = [t.id for t in p.tags]
    if not p_tags and p.category_id is None:
        return jsonify({"items": []})
    q = visible_posts_query().filter(Post.id != p.id)
    if p_tags:
        ov = _tag_overlap_subquery(p_tags, p.id)
        q = q.outerjoin(ov, ov.c.pid == Post.id)
        overlap = db.func.coalesce(ov.c.n, 0)
    else:
        overlap = 0
    score = overlap + _category_bonus(p.category_id)
    rows = (q.filter(score > 0)
            .order_by(score.desc(), *_SCORE_TIEBREAK)
            .limit(5).all())
    return jsonify({"items": [_post_summary(c) for c in rows]})


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
    if not rate_limit(client_key("api_also_viewed"), limit=_LIST_RATE[0], window=_LIST_RATE[1]):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    # v4.0.0（审计【低危 7】）：原实现有两个无上限的物化 ——
    #   a) `ReadLog.query.filter_by(post_id=p.id).all()`：把本篇**全部**访客 IP 取进内存；
    #   b) `visible_posts_query().filter(Post.id != p.id).all()`：把全站可见文章取出来求标签交集。
    # 两者都改成 SQL 聚合：共现计数走 `(post_id, COUNT(*)) GROUP BY`，共读访客集合用
    # 子查询 `ip IN (SELECT ip FROM read_log WHERE post_id = :pid)` 表达，IP 一行都不进 Python。
    #
    # ⚠️ 一处**刻意的行为修正**：旧代码先按 score 取 top10、再按可见性过滤、最后取 top5，
    # 于是 top10 里若混着不可见文章，最终可能只返回 3 篇。现在可见性是 SQL 的 WHERE 条件，
    # 取的就是「可见文章里的 top10」，最后 5 篇一定是满的 —— 与函数 docstring 里
    # 「多取名额以补足被过滤掉的项」的意图一致。
    p_tags = [t.id for t in p.tags]
    # 1) 协同过滤：读过本篇的访客还读过哪些文章（ReadLog 有 UNIQUE(post_id, ip)，
    #    故 COUNT(*) 即「共同阅读人数」，与旧实现逐行 +1 完全等价）。
    readers = db.session.query(ReadLog.ip).filter(ReadLog.post_id == p.id)
    co = (db.session.query(ReadLog.post_id.label("pid"), db.func.count().label("n"))
          .filter(ReadLog.post_id != p.id, ReadLog.ip.in_(readers))
          .group_by(ReadLog.post_id).subquery())

    q = visible_posts_query().filter(Post.id != p.id).outerjoin(co, co.c.pid == Post.id)
    if p_tags:
        ov = _tag_overlap_subquery(p_tags, p.id)
        q = q.outerjoin(ov, ov.c.pid == Post.id)
        overlap = db.func.coalesce(ov.c.n, 0)
    else:
        overlap = 0
    # 2) 相似度加权（标签/分类）0.5 倍，冷启动（无共现）时退化为基础相似推荐。
    score = db.func.coalesce(co.c.n, 0) + (overlap + _category_bonus(p.category_id)) * 0.5
    rows = (q.filter(score > 0)
            .order_by(score.desc(), *_SCORE_TIEBREAK)
            .limit(10).all())
    return jsonify({"items": [_post_summary(pp) for pp in rows[:5]]})
# ---------- 全文搜索（FTS5 优先，失败回退 LIKE，B5；v3.0.0 功能3 增加分页 + 高亮）----------
@api_bp.route("/search")
def search_api():
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    if per_page <= 0 or per_page > 50:
        per_page = 10
    # v4.0.0（审计【低危 7】）：搜索会打全表 LIKE / 拉 FTS 全量命中，匿名且无限流
    # 时是最便宜的放大面。搜索比翻页稀疏，阈值给 60 次/60 秒。
    if not rate_limit(client_key("api_search"), limit=60, window=60):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    if page < 1:
        page = 1
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
        return _re.sub(_re.escape(esc_q), lambda m: f"<mark>{m.group(0)}</mark>",
                       esc_text, flags=_re.IGNORECASE)

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
    start = (page - 1) * per_page
    if ids:
        # 可见性只能由 `visible_posts_query()` 判定：FTS 索引按 rowid 命中，而索引里
        # 可能存在隐私/回收站/定时未到的行；`_post_summary()` 会把标题、摘要连正文
        # 片段一起返回，漏一次就是正文外泄。保留 FTS 的 rank 顺序。
        #
        # v4.0.0（审计【低危 7】）：原来把 `ids` 里每条都 `db.session.get(Post, i)`
        # 物化成 ORM 对象后再切片 —— 命中多少篇就物化多少篇。现在**只取 id**
        # （一行两个整数），排好序后按页把这一页的对象取出来，物化量恒为 per_page。
        visible = [r[0] for r in visible_posts_query()
                   .filter(Post.id.in_(ids)).with_entities(Post.id).all()]
        rank = {pid: i for i, pid in enumerate(ids)}
        visible.sort(key=rank.__getitem__)     # 恢复 FTS rank 顺序
        total = len(visible)
        page_ids = visible[start:start + per_page]
        by_id = {p.id: p for p in Post.query.filter(Post.id.in_(page_ids)).all()} if page_ids else {}
        posts = [by_id[i] for i in page_ids if i in by_id]
        engine = "fts5"
    else:
        like = f"%{q}%"
        # v4.0.0：LIKE 回退同样改成 SQL 侧分页（原来 `.all()` 全量命中再切片）。
        query = (visible_posts_query()
                 .filter(db.or_(Post.title.ilike(like), Post.summary.ilike(like),
                                Post.content.ilike(like)))
                 .order_by(*_DISPLAY_ORDER))
        total = query.count()
        posts = query.limit(per_page).offset(start).all()
        engine = "like"
    pages = (total + per_page - 1) // per_page if per_page else 1
    items = []
    for p in posts:
        s = _post_summary(p)
        s["highlight"] = make_highlight(p)
        items.append(s)
    return jsonify({"items": items, "total": total, "pages": pages, "page": page,
                    "engine": engine, "query": q})

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
    import fts as _fts
    _fts.sync_post_quiet(p)
    # v3.9.0 M1：文章发布 → 触发插件事件（订阅者异常已隔离）
    try:
        from plugins.signals import emit_post_published
        emit_post_published(p)
    except Exception:
        pass
    # 发布后推送 + 邮件（与正常发布一致，全部静默）
    try:
        import notify as _notify
        _notify.notify_new_post(p, current_app.config.get("SITE_URL", ""))
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
    return jsonify({"ok": True, "message": "已立即发布", "published": True})
