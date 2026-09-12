# -*- coding: utf-8 -*-
"""v3.17.0：年度回顾 + 访客地域榜（公开只读聚合，供 /annual 页面使用）。

约束与设计：
- 纯读、无写、无表结构变更（符合「能不改表就不改」项目纪律）。
- 年份口径：文章按 created_at（UTC）经 strftime('%Y') 归年；访客按 VisitLog.date 前缀。
- 地域榜以「条形列表」呈现，**不渲染地图**——规避地图数据合规问题与重依赖。
- 任何聚合异常都降级为空列表，绝不 500。
"""
import datetime
import os
import time
import urllib.parse
import urllib.request

from flask import Response, request, jsonify
from sqlalchemy import func

from .common import api_bp
from models import db, Post, Comment, Category, Tag, VisitLog
from _time import utcnow


def _visible_posts():
    now = utcnow()
    return Post.query.filter(
        Post.published.is_(True),
        db.or_(Post.scheduled_at.is_(None), Post.scheduled_at <= now),
    )


@api_bp.route("/review/annual")
def annual_review():
    try:
        year = int(request.args.get("year") or utcnow().year)
    except (TypeError, ValueError):
        year = utcnow().year
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


# ---------- v3.17.3：访客地图（省份聚合 + 合规行政区划底图） ----------
# 省份简称 → 行政区划全称（阿里 DataV GeoJSON 的 properties.name 用全称）
_PROV_ALIAS = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "河北": "河北省", "山西": "山西省", "辽宁": "辽宁省", "吉林": "吉林省",
    "黑龙江": "黑龙江省", "江苏": "江苏省", "浙江": "浙江省", "安徽": "安徽省",
    "福建": "福建省", "江西": "江西省", "山东": "山东省", "河南": "河南省",
    "湖北": "湖北省", "湖南": "湖南省", "广东": "广东省", "海南": "海南省",
    "四川": "四川省", "贵州": "贵州省", "云南": "云南省", "陕西": "陕西省",
    "甘肃": "甘肃省", "青海": "青海省", "台湾": "台湾省",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
}
_GEO_DATA_URL = "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json"


@api_bp.route("/geo/visitors")
def geo_visitors():
    """v3.17.3：访客省份分布（按 VisitLog.region 省级部分聚合，排除 bot）。公开只读。

    隐私：仅返回**省级聚合计数**，不含 IP、不含任何个人位置数据（符合 PIPL 要求）。
    """
    days = request.args.get("days", type=int) or 30
    days = max(1, min(365, days))
    since = (utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (db.session.query(VisitLog.region, func.count(VisitLog.id))
            .filter(VisitLog.date >= since, VisitLog.is_bot.is_(False), VisitLog.region != "")
            .group_by(VisitLog.region)
            .order_by(func.count(VisitLog.id).desc()).limit(500).all())
    prov = {}
    for region, n in rows:
        name = (region or "").split("·")[0].strip()
        full = _PROV_ALIAS.get(name)
        if full:
            prov[full] = prov.get(full, 0) + n
    items = sorted(prov.items(), key=lambda x: x[1], reverse=True)
    return jsonify({
        "days": days,
        "provinces": [{"name": k, "count": v} for k, v in items],
    })


def _geo_cache_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # myblog/
    return os.path.join(base, "data", "geo_china.json")


@api_bp.route("/geo/china.json")
def geo_china_json():
    """中国省级行政区划 GeoJSON（阿里云 DataV，含港澳台与南海诸岛，审图号合规数据）。

    后端磁盘缓存 7 天（避免每次访客都拉 CDN）；异常时返回 503，前端降级为地域榜。
    """
    cache = _geo_cache_path()
    try:
        if os.path.isfile(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400:
            with open(cache, "rb") as f:
                body = f.read()
        else:
            req = urllib.request.Request(_GEO_DATA_URL, headers={"User-Agent": "llhhy-blog"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, cache)
    except Exception:
        return jsonify({"error": "底图数据暂不可用"}), 503
    return Response(body, mimetype="application/json",
                    headers={"Cache-Control": "public, max-age=86400"})
