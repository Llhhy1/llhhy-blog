# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

@admin_bp.route("/comments", methods=["GET"])
@admin_required
def comments():
    # 审核流：支持 ?status=pending 只看待审核
    status = request.args.get("status", "")
    q = Comment.query
    if status == "pending":
        q = q.filter_by(approved=False)
    elif status == "approved":
        q = q.filter_by(approved=True)
    rows = q.order_by(Comment.created_at.desc()).all()
    pending_count = Comment.query.filter_by(approved=False).count()
    return render_template("admin/comments.html", comments=rows, status=status, pending_count=pending_count)

@admin_bp.route("/comment/<int:cid>/approve", methods=["POST"])
@admin_required
def approve_comment(cid):
    """审核通过评论。"""
    c = Comment.query.get_or_404(cid)
    c.approved = True
    db.session.commit()
    flash("评论已通过审核")
    return redirect(url_for("admin.comments", status="pending"))

@admin_bp.route("/comment/<int:cid>/reject", methods=["POST"])
@admin_required
def reject_comment(cid):
    """驳回评论（删除，相当于拒绝显示）。"""
    c = Comment.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("评论已驳回并删除")
    return redirect(url_for("admin.comments", status="pending"))

@admin_bp.route("/comment/<int:cid>/read", methods=["POST"])
@admin_required
def mark_comment_read(cid):
    """单条评论标记为已读。"""
    c = Comment.query.get_or_404(cid)
    c.is_read = True
    db.session.commit()
    return redirect(url_for("admin.comments"))

@admin_bp.route("/comments/read-all", methods=["POST"])
@admin_required
def mark_all_comments_read():
    """全部评论标记为已读。"""
    Comment.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("全部评论已标记为已读")
    return redirect(url_for("admin.comments"))

@admin_bp.route("/comment/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_comment(cid):
    c = Comment.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("评论已删除")
    return redirect(url_for("admin.comments"))

@admin_bp.route("/comments/batch-approve", methods=["POST"])
@admin_required
def batch_approve_comments():
    """批量通过评论：表单传入待审 comment id 列表（name=ids，多选）。"""
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if not ids:
        flash("请先勾选要通过的评论")
        return redirect(url_for("admin.comments"))
    approved = 0
    for cid in ids:
        c = Comment.query.get(cid)
        if c and not c.approved:
            c.approved = True
            approved += 1
    db.session.commit()
    log_audit("batch_approve", "comment", None, f"批量通过 {approved} 条评论", user=_current_user_or_none())
    flash(f"已批量通过 {approved} 条评论")
    return redirect(url_for("admin.comments"))

@admin_bp.route("/comments/batch-delete", methods=["POST"])
@admin_required
def batch_delete_comments():
    """批量删除评论：表单传入 comment id 列表（name=ids，多选）。"""
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if not ids:
        flash("请先勾选要删除的评论")
        return redirect(url_for("admin.comments"))
    deleted = 0
    for cid in ids:
        c = Comment.query.get(cid)
        if c:
            db.session.delete(c)
            deleted += 1
    db.session.commit()
    log_audit("batch_delete", "comment", None, f"批量删除 {deleted} 条评论", user=_current_user_or_none())
    flash(f"已批量删除 {deleted} 条评论")
    return redirect(url_for("admin.comments"))
