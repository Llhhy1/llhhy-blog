"""
"""

import re as _re
from flask import request, jsonify, current_app

from .common import (api_bp, db, Post, Category, Tag, Comment, FriendLink, Setting, LinkApplication, Announcement, visible_posts_query, _settings_map, clean_html, render_markdown, rate_limit, client_key)
import stats  # myblog/stats.py：client_ip（友链申请归属地）

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

# ---------- 站点公告 / 置顶（D4）----------
@api_bp.route("/announcements")
def announcements():
    items = Announcement.query.filter_by(active=True).order_by(Announcement.created_at.desc()).all()
    return jsonify({"items": [
        {"id": a.id, "content": clean_html(render_markdown(a.content)),
         "level": a.level, "dismissible": a.dismissible}
        for a in items
    ]})

