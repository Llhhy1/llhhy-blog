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
