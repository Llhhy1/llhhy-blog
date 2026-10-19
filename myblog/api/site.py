"""
"""

import re as _re
from flask import request, jsonify, current_app

from .common import (api_bp, db, Post, Category, Tag, Comment, FriendLink, Setting, LinkApplication, Announcement, visible_posts_query, _settings_map, clean_html, render_markdown, rate_limit, client_key)
from themes import current_theme
# v4.5.0 首页壁纸。单向依赖（theme 不引用 site），不构成包级循环。
from .theme import _wallpaper
import stats  # myblog/stats.py：client_ip（友链申请归属地）

def _nav_entry_items():
    """v4.1.0：多条外部入口（过滤「未启用」与「地址非法」的条目）。

    为什么读出口还要再判一次：这些值是后台填的、前台用 ``:href`` 绑的，
    ``javascript:`` 之类 scheme 会在访客浏览器里执行（存储型 XSS）。
    写一侧已经拦过一次，这里是第二次 —— 写一侧可能被后续改动绕过、
    也可能是迁移/备份还原进来的脏数据。**宁可入口消失，也不输出危险 href**：
    入口消失是可见的、好修的；XSS 是静默的。
    """
    import nav_entries as _ne
    from utils import is_http_url
    out = []
    for e in _ne.load():
        if not e.get("enabled"):
            continue
        url = (e.get("url") or "").strip()
        if not is_http_url(url):
            continue
        out.append({
            "label": (e.get("label") or "").strip()[:20],
            "url": url,
            "icon": (e.get("icon") or "").strip()[:8],
        })
    return out


def _public_entry():
    """v4.0.0 遗留字段，保持形状不变：取**第一条**合法入口，无则「未配置」。

    保留它是为了让外部依赖（含既有测试）不必为一个纯增量的改动改一遍。
    """
    items = _nav_entry_items()
    if not items:
        return {"enabled": False, "label": "", "url": "", "icon": ""}
    return dict(items[0], enabled=True)


# ---------- v4.7.0 开站时间 ----------
# ⚠️ 这是**近似值**：最早一篇可见文章的发布时间未必等于真实建站日（可能先写了
# 几篇草稿、换过域名、迁移过旧站）。所以后台提供 `site_since` 让站主手工覆盖，
# 这里只在它为空/非法时才回退 —— 有配置的永远以配置为准。
_SINCE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_since(v):
    """`YYYY-MM-DD` 且必须是真实存在的日期（否则 `2026-02-30` 这类会被放行）。"""
    s = (v or "").strip()
    if not _SINCE_RE.match(s):
        return ""
    import datetime as _dt
    try:
        y, m, d = (int(x) for x in s.split("-"))
        _dt.date(y, m, d)
    except (ValueError, TypeError):
        return ""
    return s


def _site_since(s):
    """开站日期（`YYYY-MM-DD`）。优先后台配置 `site_since`，否则取最早一篇
    可见文章的发布时间；都没有则返回空串（前台据此不显示该项）。

    只取**可见**文章：不可见/未发布的草稿时间更早，用它会把开站日期算早。
    """
    v = _valid_since(s.get("site_since", ""))
    if v:
        return v
    row = (visible_posts_query()
           .with_entities(Post.created_at)
           .order_by(Post.created_at.asc())
           .first())
    if not row or not row[0]:
        return ""
    d = row[0].strftime("%Y-%m-%d")
    return d


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
        # v4.0.0：前台自定义外链入口（后台可配；地址非法则 enabled=false）
        "entry": _public_entry(),
        # v4.1.0：同一批入口的**列表**形态（前台「工具箱」下拉用；已过滤非法地址）
        "entries": _nav_entry_items(),
        # v3.16.0 主题中心：当前激活主题的完整 token（亮/暗），前台据此整体换肤
        "theme_pack": current_theme()["pack_id"],
        "theme_tokens": current_theme()["light"],
        "theme_dark_tokens": current_theme()["dark"],
        # v4.5.0 首页壁纸（存 Setting KV，零表结构变更；URL 已限定本站 uploads）
        "wallpaper": _wallpaper(),
        # v4.7.0 开站时间（后台可配，未配时回退最早可见文章的发布时间）
        "site_since": _site_since(s),
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

