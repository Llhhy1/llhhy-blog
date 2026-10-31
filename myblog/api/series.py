"""
"""


from flask import jsonify, abort

from .common import (api_bp, Series, Post, visible_posts_query, _post_summary)
from utils.taxonomy_slug import resolve_taxonomy

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
    s, legacy = resolve_taxonomy(Series, slug)
    if s is None:
        abort(404)
    posts = visible_posts_query().filter_by(series_id=s.id).order_by(Post.created_at.asc()).all()
    payload = {
        "slug": s.slug, "name": s.name, "description": s.description or "",
        "cover": s.cover or "",
        "posts": [_post_summary(p) for p in posts],
    }
    if legacy:
        payload["moved"] = True
    return jsonify(payload)

