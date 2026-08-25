"""
"""


from flask import jsonify

from .common import (api_bp, Series, Post, visible_posts_query, _post_summary)

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

