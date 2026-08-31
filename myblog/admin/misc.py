# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Category(name=name, slug=make_slug(name)))
            db.session.commit()
            flash("分类已添加")
        return redirect(url_for("admin.categories"))
    cats = Category.query.order_by(Category.id).all()
    return render_template("admin/categories.html", cats=cats)

@admin_bp.route("/social", methods=["GET", "POST"])
@admin_required
def social():
    """社交账号管理（广场页「我的社交账号」墙）。"""
    if request.method == "POST":
        platform = (request.form.get("platform") or "").strip()
        url = (request.form.get("url") or "").strip()
        if platform and url:
            db.session.add(SocialAccount(
                platform=platform,
                handle=(request.form.get("handle") or "").strip(),
                url=url,
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("社交账号已添加")
        return redirect(url_for("admin.social"))
    accounts = SocialAccount.query.order_by(SocialAccount.sort).all()
    return render_template("admin/social.html", accounts=accounts)

@admin_bp.route("/social/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_social(aid):
    acc = SocialAccount.query.get_or_404(aid)
    db.session.delete(acc)
    db.session.commit()
    flash("社交账号已删除")
    return redirect(url_for("admin.social"))

@admin_bp.route("/bot-guard", methods=["GET", "POST"])
@super_required
def bot_guard_view():
    """反爬限流保护看板 + 封禁管理（v3.8.0）。"""
    if request.method == "POST":
        action = request.form.get("action")
        ip = (request.form.get("ip") or "").strip()
        if action == "unblock" and ip:
            ok = bot_guard.unblock_ip(ip)
            flash("已解封 " + ip if ok else "未找到该 IP 的封禁记录")
        return redirect(url_for("admin.bot_guard_view"))
    data = bot_guard.guard_stats()
    return render_template("admin/bot_guard.html", stats=data, now=datetime.utcnow())

@admin_bp.route("/announcements", methods=["GET", "POST"])
@admin_required
def manage_announcements():
    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if content:
            db.session.add(Announcement(
                content=content,
                level=(request.form.get("level") or "info"),
                active=request.form.get("active", "on") == "on",
                dismissible=request.form.get("dismissible", "on") == "on",
            ))
            db.session.commit()
            flash("公告已添加")
        return redirect(url_for("admin.manage_announcements"))
    items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", items=items)

@admin_bp.route("/announcement/<int:aid>/toggle", methods=["POST"])
@admin_required
def toggle_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    a.active = not a.active
    db.session.commit()
    return redirect(url_for("admin.manage_announcements"))

@admin_bp.route("/announcement/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    flash("公告已删除")
    return redirect(url_for("admin.manage_announcements"))

@admin_bp.route("/guestbook", methods=["GET"])
@admin_required
def manage_guestbook():
    rows = Guestbook.query.order_by(Guestbook.created_at.desc()).all()
    return render_template("admin/guestbook.html", rows=rows)

@admin_bp.route("/guestbook/<int:gid>/read", methods=["POST"])
@admin_required
def mark_guestbook_read(gid):
    """单条留言标记为已读。"""
    g = Guestbook.query.get_or_404(gid)
    g.is_read = True
    db.session.commit()
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/guestbook/read-all", methods=["POST"])
@admin_required
def mark_all_guestbook_read():
    """全部留言标记为已读。"""
    Guestbook.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("全部留言已标记为已读")
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/guestbook/<int:gid>/delete", methods=["POST"])
@admin_required
def delete_guestbook(gid):
    g = Guestbook.query.get_or_404(gid)
    db.session.delete(g)
    db.session.commit()
    flash("留言已删除")
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/subscribers", methods=["GET"])
@admin_required
def manage_subscribers():
    rows = Subscriber.query.order_by(Subscriber.created_at.desc()).all()
    return render_template("admin/subscribers.html", rows=rows)

@admin_bp.route("/subscribers/delete/<int:sid>", methods=["POST"])
@admin_required
def delete_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    email = sub.email
    db.session.delete(sub)
    db.session.commit()
    flash(f"已删除订阅者：{email}")
    return redirect(url_for("admin.manage_subscribers"))

@admin_bp.route("/subscribers/toggle/<int:sid>", methods=["POST"])
@admin_required
def toggle_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    sub.active = not sub.active
    db.session.commit()
    flash(f"已{'启用' if sub.active else '停用'}订阅者：{sub.email}")
    return redirect(url_for("admin.manage_subscribers"))

@admin_bp.route("/feed-diag", methods=["GET", "POST"])
@super_required
def feed_diag():
    """全站健康体检中心（仅超管）：汇总数据库/依赖/配置/备份/SEO/待办/前端构建/存储/RSS 聚合。

    POST 触发强制重新聚合（force=True），刷新 RSS 诊断；其余维度每次加载实时计算。
    诊断逻辑见 myblog/diagnostics.py（run_all）。
    """
    if request.method == "POST":
        try:
            feed_agg.get_circle_feed(force=True)
            flash("已强制刷新博客圈聚合与诊断")
        except Exception as e:
            flash("刷新失败：" + str(e)[:200])
        return redirect(url_for("admin.feed_diag"))
    result = diagnostics.run_all()
    return render_template("admin/feed_diag.html", result=result)

@admin_bp.route("/plugins")
@admin_required
def plugins():
    """插件管理页：列出已配置插件及其运行状态，支持运行时启停与整体重载。

    启停写 disabled 标记文件 + 内存覆盖，前端槽位即时生效；路由级启停需重启 gunicorn。
    """
    from plugins import (PLUGIN_REGISTRY, RUNTIME_DISABLED, _marker_path, _parse_list)
    cfg = current_app.config
    enabled = _parse_list(cfg.get("ENABLED_PLUGINS", ""))
    items = []
    for slug in enabled:
        m = PLUGIN_REGISTRY.get(slug, {})
        mp = _marker_path(cfg, slug)
        disabled = (slug in RUNTIME_DISABLED) or (mp and os.path.exists(mp))
        items.append({
            "slug": slug,
            "name": m.get("name", slug),
            "version": m.get("version", ""),
            "author": m.get("author", ""),
            "description": m.get("description", ""),
            "slots": m.get("slots", []) or [],
            "loaded": slug in PLUGIN_REGISTRY,
            "disabled": bool(disabled),
        })
    return render_template("admin/plugins.html", plugins=items, app_version=APP_VERSION)
