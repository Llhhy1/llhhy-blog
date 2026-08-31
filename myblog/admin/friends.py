# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

@admin_bp.route("/links", methods=["GET", "POST"])
@admin_required
def links():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        if name and url:
            db.session.add(FriendLink(
                name=name, url=url,
                description=(request.form.get("description") or "").strip(),
                sort=request.form.get("sort", 0, type=int),
                rss_url=(request.form.get("rss_url") or "").strip(),
            ))
            db.session.commit()
            flash("友链已添加")
        return redirect(url_for("admin.links"))
    links = FriendLink.query.order_by(FriendLink.sort).all()
    return render_template("admin/links.html", links=links)

@admin_bp.route("/link/<int:lid>/rss", methods=["POST"])
@admin_required
def set_link_rss(lid):
    """保存某条友链的 RSS 地址（用于「博客圈」聚合）。"""
    link = FriendLink.query.get_or_404(lid)
    link.rss_url = (request.form.get("rss_url") or "").strip()
    db.session.commit()
    flash("已保存 RSS 地址")
    # v3.10.4：软校验 RSS 可达性（非阻塞，保存照常）。提前暴露「/feed/ 返回 HTML」
    # 这类填错——之前用户填了首页路径当 RSS，博客圈悄无声息为空。
    if link.rss_url:
        try:
            import feed_agg
            ok, reason = feed_agg.validate_feed_url(link.rss_url)
            if not ok:
                flash("⚠️ 该 RSS 地址可能不可用（%s），博客圈将无法聚合此源。" % reason, "warning")
        except Exception:
            pass
    return redirect(url_for("admin.links"))

@admin_bp.route("/link/<int:lid>/delete", methods=["POST"])
@admin_required
def delete_link(lid):
    link = FriendLink.query.get_or_404(lid)
    db.session.delete(link)
    db.session.commit()
    flash("友链已删除")
    return redirect(url_for("admin.links"))

@admin_bp.route("/link-applications")
@admin_required
def link_applications():
    """友链申请列表：默认看待审核，可按状态筛选。"""
    status = request.args.get("status", "pending")
    q = LinkApplication.query
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(LinkApplication.created_at.desc()).all()
    pending_count = LinkApplication.query.filter_by(status="pending").count()
    return render_template("admin/link_applications.html", rows=rows,
                           status=status, pending_count=pending_count)

@admin_bp.route("/link-application/<int:aid>/approve", methods=["POST"])
@admin_required
def approve_link_application(aid):
    """通过友链申请：写入 FriendLink 列表，标记申请为 approved。"""
    app_row = LinkApplication.query.get_or_404(aid)
    if app_row.status != "approved":
        # 写入友链表（避免重复：同 URL 已存在则跳过）
        existing = FriendLink.query.filter_by(url=app_row.url).first()
        if not existing:
            db.session.add(FriendLink(name=app_row.name, url=app_row.url,
                                      description=app_row.description or "",
                                      sort=99))
        app_row.status = "approved"
        app_row.reviewer = (_current_user_or_none().username if _current_user_or_none() else "")
        app_row.reviewed_at = datetime.datetime.utcnow()
        db.session.commit()
        log_audit("approve", "link_application", aid, f"通过友链申请：{app_row.name}", user=_current_user_or_none())
        flash(f"已通过友链申请：{app_row.name}")
    return redirect(url_for("admin.link_applications"))

@admin_bp.route("/link-application/<int:aid>/reject", methods=["POST"])
@admin_required
def reject_link_application(aid):
    """拒绝友链申请：仅标记状态，不写入友链表。"""
    app_row = LinkApplication.query.get_or_404(aid)
    app_row.status = "rejected"
    app_row.reviewer = (_current_user_or_none().username if _current_user_or_none() else "")
    app_row.reviewed_at = datetime.datetime.utcnow()
    note = (request.form.get("note") or "").strip()
    if note:
        app_row.review_note = note
    db.session.commit()
    log_audit("reject", "link_application", aid, f"拒绝友链申请：{app_row.name}", user=_current_user_or_none())
    flash(f"已拒绝友链申请：{app_row.name}")
    return redirect(url_for("admin.link_applications"))
