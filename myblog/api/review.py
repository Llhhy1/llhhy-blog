# -*- coding: utf-8 -*-
"""v3.17.0：年度回顾 + 访客地域榜（公开只读聚合，供 /annual 页面使用）。

约束与设计：
- 纯读、无写、无表结构变更（符合「能不改表就不改」项目纪律）。
- 年份口径：文章按 created_at（UTC）经 strftime('%Y') 归年；访客按 VisitLog.date 前缀。
- 地域榜以「条形列表」呈现，**不渲染地图**——规避地图数据合规问题与重依赖。
- 任何聚合异常都降级为空列表，绝不 500。
"""
import datetime

from flask import request, jsonify
from sqlalchemy import func

from .common import api_bp
from models import db, Post, Comment, Category, Tag, VisitLog


def _visible_posts():
    now = datetime.datetime.utcnow()
    return Post.query.filter(
        Post.published.is_(True),
        db.or_(Post.scheduled_at.is_(None), Post.scheduled_at <= now),
    )


@api_bp.route("/review/annual")
def annual_review():
    try:
        year = int(request.args.get("year") or datetime.datetime.utcnow().year)
    except (TypeError, ValueError):
        year = datetime.datetime.utcnow().year
    ymd = str(year)

    posts = _visible_posts().filter(func.strftime("%Y", Post.created_at) == ymd).all()
    post_count = len(posts)
    view_count = sum((p.views or 0) for p in posts)
    word_count = sum((p.word_count or 0) for p in posts)
    comment_count = 0
    if posts:
        comment_count = Comment.query.filter(
            Comment.post_id.in_([p.id for p in posts])).count()

    months = [0] * 12
    for p in posts:
        if p.created_at and 0 <= (p.created_at.month - 1) < 12:
            months[p.created_at.month - 1] += 1

    hot = sorted(posts, key=lambda x: (x.views or 0), reverse=True)[:5]

    cat_counter = {}
    for p in posts:
        if p.category_id:
            cat_counter[p.category_id] = cat_counter.get(p.category_id, 0) + 1
    cats = []
    if cat_counter:
        for c in Category.query.filter(Category.id.in_(list(cat_counter))).all():
            cats.append({"name": c.name, "slug": c.slug, "count": cat_counter[c.id]})
        cats.sort(key=lambda x: x["count"], reverse=True)

    tag_counter = {}
    for p in posts:
        for t in (getattr(p, "tags", None) or []):
            tag_counter[t.id] = tag_counter.get(t.id, 0) + 1
    tags = []
    if tag_counter:
        for t in Tag.query.filter(Tag.id.in_(list(tag_counter))).all():
            tags.append({"name": t.name, "slug": t.slug, "count": tag_counter[t.id]})
        tags.sort(key=lambda x: x["count"], reverse=True)
        tags = tags[:8]

    regions = []
    try:
        rows = (db.session.query(VisitLog.region, func.count(VisitLog.id))
                .filter(VisitLog.date.like(ymd + "%"),
                        VisitLog.is_bot.is_(False),
                        VisitLog.region != "")
                .group_by(VisitLog.region)
                .order_by(func.count(VisitLog.id).desc())
                .limit(8).all())
        regions = [{"region": r or "未知", "count": n} for r, n in rows]
    except Exception:
        regions = []

    try:
        visitors = (db.session.query(func.count(func.distinct(VisitLog.ip)))
                    .filter(VisitLog.date.like(ymd + "%"), VisitLog.is_bot.is_(False))
                    .scalar() or 0)
    except Exception:
        visitors = 0

    try:
        years = sorted({p.created_at.year for p in _visible_posts().all() if p.created_at},
                       reverse=True)
    except Exception:
        years = [year]

    return jsonify({
        "year": year,
        "posts": post_count,
        "views": view_count,
        "comments": comment_count,
        "words": word_count,
        "visitors": visitors,
        "months": months,
        "hot_posts": [{"title": p.title, "slug": p.slug, "views": p.views or 0}
                      for p in hot],
        "categories": cats,
        "tags": tags,
        "regions": regions,
        "years": years,
    })


@api_bp.route("/milestones")
def milestones():
    """v3.17.2：站点里程碑 / 成就徽章（公开只读，纯聚合，无表结构变更、无新依赖）。"""
    posts = _visible_posts().all()
    post_count = len(posts)
    views = sum((p.views or 0) for p in posts)
    try:
        comments = Comment.query.count()
    except Exception:
        comments = 0

    days_sorted = sorted({p.created_at.date() for p in posts if p.created_at}, reverse=True)
    day_set = set(days_sorted)
    streak = 0
    if days_sorted:
        cur = days_sorted[0]
        while cur in day_set:
            streak += 1
            cur = cur - datetime.timedelta(days=1)
    first_day = min(day_set) if day_set else None
    running_days = ((datetime.date.today() - first_day).days + 1) if first_day else 0

    defs = [
        ("sprout", "\U0001F331", "起步", "发布第一篇文章", post_count >= 1, post_count, 1),
        ("writer", "\u270D\uFE0F", "勤笔不辍", "累计发文 10 篇", post_count >= 10, post_count, 10),
        ("author", "\U0001F4DA", "著作等身", "累计发文 50 篇", post_count >= 50, post_count, 50),
        ("read1k", "\U0001F440", "千人共读", "累计阅读 1,000", views >= 1000, views, 1000),
        ("read10k", "\U0001F525", "万人瞩目", "累计阅读 10,000", views >= 10000, views, 10000),
        ("talk", "\U0001F4AC", "热络互动", "评论累计 50 条", comments >= 50, comments, 50),
        ("streak7", "\U0001F4C5", "坚持更新", "连续更新 7 天", streak >= 7, streak, 7),
        ("longrun", "\u23F3", "长期主义", "开博满 365 天", running_days >= 365, running_days, 365),
    ]
    items = [{
        "id": i, "icon": ic, "name": n, "desc": d,
        "unlocked": bool(ok), "current": cur, "target": t,
    } for (i, ic, n, d, ok, cur, t) in defs]

    return jsonify({
        "posts": post_count,
        "views": views,
        "comments": comments,
        "streak": streak,
        "running_days": running_days,
        "unlocked": sum(1 for x in items if x["unlocked"]),
        "total": len(items),
        "items": items,
    })
