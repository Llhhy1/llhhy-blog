# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import (_current_user_or_none, admin_required, log_audit, reorder_friend_links_core,
                       save_friend_link_core, admin_bp)     # 同一蓝图对象
from flask import flash, redirect, render_template, request, url_for
from models import FriendLink, LinkApplication, db
from _time import utcnow
import adopter_stats

@admin_bp.route("/links", methods=["GET", "POST"])
@admin_required
def links():
    if request.method == "POST":
        # v4.4.0：新增/编辑统一走 `save_friend_link_core`（URL 归一 + 同 URL 查重 + RSS 软校验），
        # 后台原先这条路径不查重，同一站点能连加两次。
        err, note, link = save_friend_link_core(None, request.form)
        if err:
            flash(err)
        else:
            flash("友链已添加" + (f"（{note}）" if note else ""))
            log_audit("create", "friend_link", link.id if link else None,
                      f"新增友链：{(request.form.get('name') or '').strip()}",
                      user=_current_user_or_none())
        return redirect(url_for("admin.links"))
    links = FriendLink.query.order_by(FriendLink.sort).all()
    return render_template("admin/links.html", links=links,
                           repo_stats=adopter_stats.cached_stats())

@admin_bp.route("/link/<int:lid>/update", methods=["POST"])
@admin_required
def update_link(lid):
    """编辑友链（v4.4.0 新增）。

    后台原本只能「新增 / 存 RSS / 删除」，`name/url/description/sort` **没有任何编辑入口**，
    改一个字就得删了重建。移动端同样需要，所以补这条路由，与新增共用同一个 core。
    """
    link = FriendLink.query.get_or_404(lid)
    err, note, _ = save_friend_link_core(link, request.form)
    flash(err or ("友链已更新" + (f"（{note}）" if note else "")))
    if not err:
        log_audit("update", "friend_link", lid, f"编辑友链：{link.name}",
                  user=_current_user_or_none())
    return redirect(url_for("admin.links"))

@admin_bp.route("/links/reorder", methods=["POST"])
@admin_required
def reorder_links():
    """友链排序（v4.4.0 新增）：`ids` 为逗号分隔的目标顺序（越靠前越先显示）。"""
    ids = [x for x in (request.form.get("ids") or "").split(",") if x.strip()]
    moved = reorder_friend_links_core(ids)
    log_audit("reorder", "friend_link", None, f"友链重排：改动 {moved} 条",
              user=_current_user_or_none())
    flash(f"排序已更新（改动 {moved} 条）")
    return redirect(url_for("admin.links"))

@admin_bp.route("/link/<int:lid>/rss", methods=["POST"])
@admin_required
def set_link_rss(lid):
    """只改某条友链的 RSS 地址（旧入口）。

    v4.4.0：页面把 RSS 收进了「编辑」行，本路由不再被模板引用，但**留着** —— 它是个
    有用的窄入口（只想挂个源、不想重填名称网址时）。落库改走 `save_friend_link_core`：
    原先这里自己写了一遍「存 rss + 软校验可达性」，与编辑路径各有一套判据，正是本仓库
    反对的两套逻辑；现在整行字段从库里回填、只覆盖 rss_url，校验与软提示只剩一份。
    """
    link = FriendLink.query.get_or_404(lid)
    form = {"name": link.name, "url": link.url, "description": link.description or "",
            "sort": link.sort or 0, "rss_url": request.form.get("rss_url") or ""}
    err, note, saved = save_friend_link_core(link, form)
    if err:
        flash(err)
        return redirect(url_for("admin.links"))
    flash("已保存 RSS 地址" + (f"（{note}）" if note else ""))
    log_audit("update", "friend_link", lid, f"设置友链 RSS：{saved.name}",
              user=_current_user_or_none())
    return redirect(url_for("admin.links"))

@admin_bp.route("/link/<int:lid>/delete", methods=["POST"])
@admin_required
def delete_link(lid):
    link = FriendLink.query.get_or_404(lid)
    name = link.name
    db.session.delete(link)
    db.session.commit()
    log_audit("delete", "friend_link", lid, f"删除友链：{name}", user=_current_user_or_none())
    flash("友链已删除")
    return redirect(url_for("admin.links"))

@admin_bp.route("/links/adopter-stats/refresh", methods=["POST"])
@admin_required
def refresh_adopter_stats():
    """刷新「谁在用」面板里的 GitHub 客观指标（stars / forks / Release 下载数）。

    为什么是个手动按钮而不是自动定时：这是本仓库**唯一**会主动出网拉 GitHub 的
    运营动作，放在管理员显式操作上，`/api/adopters` 才能只读缓存不出网
    （匿名接口触发出站 = 放大入口，见 v3.19.0 的 shell-check 教训）。
    """
    ok, msg = adopter_stats.refresh()
    flash(msg)
    log_audit("refresh", "adopter_stats", None, msg, user=_current_user_or_none())
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
                                      sort=99, uses_llhhy=bool(app_row.uses_llhhy)))
        elif app_row.uses_llhhy and not existing.uses_llhhy:
            # 同 URL 早就在友链里：申请带了「在用」标记就补上。
            # 反过来**不撤销**已有标记 —— 一次重复申请不该把登记抹掉。
            existing.uses_llhhy = True
        app_row.status = "approved"
        app_row.reviewer = (_current_user_or_none().username if _current_user_or_none() else "")
        app_row.reviewed_at = utcnow()
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
    app_row.reviewed_at = utcnow()
    note = (request.form.get("note") or "").strip()
    if note:
        app_row.review_note = note
    db.session.commit()
    log_audit("reject", "link_application", aid, f"拒绝友链申请：{app_row.name}", user=_current_user_or_none())
    flash(f"已拒绝友链申请：{app_row.name}")
    return redirect(url_for("admin.link_applications"))
