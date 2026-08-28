"""
"""

import datetime
import re as _re
from flask import request, jsonify, current_app, session, Response
from markupsafe import escape

from .common import (api_bp, db, Post, Category, Tag, Comment, ReadLog, Setting, User, visible_posts_query, _current_user_or_none, _post_summary, _is_visible, _comment, _render_html, rate_limit, client_key)
import stats  # myblog/stats.py：client_ip / cached_region（浏览量去重与评论归属地）

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
    """把文章列表拼成 RSS 2.0 XML（纯本地、无外部依赖），含作者/分类元数据。"""
    items = []
    for p in posts:
        link = f"{base}/post/{p.slug}"
        pub = p.created_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        summary = escape((p.summary or (p.content or "")[:200]).strip())
        author = (p.author.username if p.author
                  else current_app.config.get("SITE_TITLE", "站长"))
        cat = p.category.name if p.category else ""
        items.append(
            "    <item>\n"
            f"      <title>{escape(p.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid>{escape(link)}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <dc:creator>{escape(author)}</dc:creator>\n"
            f"      <category>{escape(cat)}</category>\n"
            f"      <description>{summary}</description>\n"
            "    </item>"
        )
    last = posts[0].created_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if posts else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
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
    # v3.9.0 M1：新评论写入 → 触发插件事件（订阅者异常已隔离）
    try:
        from plugins.signals import emit_comment_created
        emit_comment_created(c)
    except Exception:
        pass
    # A4 站内 @ 通知：解析评论内容里 @username，给注册用户发通知
    notify_mentioned(content, f"/post/{p.slug}", author, post_id=p.id)
    return jsonify({"ok": True, "comment": _comment(c),
                    "pending": require_approval}), 201

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
    try:
        import mail_notify as _mail
        _mail.notify_subscribers_async(p)
    except Exception:
        pass
    return jsonify({"ok": True, "message": "已立即发布", "published": True})
