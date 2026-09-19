# -*- coding: utf-8 -*-
"""文章管理：列表 / 批量操作 / 定时发布 / 置顶申请与审批 / 软删除。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import *   # 复用导入、辅助函数与装饰器  # noqa: F401,F403
from . import admin_bp     # 同一蓝图对象
from _time import utcnow


@admin_bp.route("/post/<int:post_id>/publish-now", methods=["POST"])
@login_required
def publish_now(post_id):
    """定时文章一键提前公开（后台 SSR，v2.8.0）。

    校验登录与编辑权限（管理员全部 / 普通用户仅自己文章），立即翻 published 并清空
    scheduled_at。成功后回退到来源页（dashboard / my_posts），并提示已发布。
    """
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能操作自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if not post.published:
        post.published = True
        post.scheduled_at = None
        db.session.commit()
        # v3.9.0 M1：文章发布 → 触发插件事件（订阅者异常已隔离）
        try:
            from plugins.signals import emit_post_published
            emit_post_published(post)
        except Exception:
            pass
        try:
            notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
        except Exception:
            pass
        try:
            mail_notify.notify_subscribers_async(post)
        except Exception:
            pass
        flash("已立即发布该文章")
    else:
        flash("该文章已处于发布状态")
    # 回到来源页（后台一键发布入口可能在 dashboard 或 my_posts）
    back = request.args.get("back") or "admin.dashboard"
    return redirect(url_for(back))

@admin_bp.route("/post/<int:post_id>/request-pin", methods=["POST"])
@login_required
def request_pin(post_id):
    """普通用户向超管申请置顶自己的文章。"""
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能申请自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if post.is_pinned:
        flash("该文章已置顶，无需申请")
    elif post.pin_requested:
        flash("已提交置顶申请，等待超管审批")
    else:
        post.pin_requested = True
        db.session.commit()
        flash("置顶申请已提交，等待超管审批")
    return redirect(url_for("admin.my_posts"))

@admin_bp.route("/post/<int:post_id>/cancel-pin-request", methods=["POST"])
@login_required
def cancel_pin_request(post_id):
    """普通用户撤回自己的置顶申请。"""
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能操作自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if post.pin_requested and not post.is_pinned:
        post.pin_requested = False
        db.session.commit()
        flash("已撤回置顶申请")
    return redirect(url_for("admin.my_posts"))

@admin_bp.route("/post/<int:post_id>/approve-pin", methods=["POST"])
@super_required
def approve_pin(post_id):
    """超管批准置顶申请：翻 is_pinned=True 并清申请态。"""
    post = Post.query.get_or_404(post_id)
    post.is_pinned = True
    post.pin_requested = False
    db.session.commit()
    flash(f"已批准置顶：{post.title}")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/post/<int:post_id>/reject-pin", methods=["POST"])
@super_required
def reject_pin(post_id):
    """超管拒绝置顶申请：清申请态，不置顶。"""
    post = Post.query.get_or_404(post_id)
    post.pin_requested = False
    db.session.commit()
    flash(f"已拒绝置顶申请：{post.title}")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/post/<int:post_id>/unpin", methods=["POST"])
@super_required
def unpin(post_id):
    """超管取消任意文章的置顶。"""
    post = Post.query.get_or_404(post_id)
    post.is_pinned = False
    db.session.commit()
    flash(f"已取消置顶：{post.title}")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/my-posts")
@login_required
def my_posts():
    """文章管理（v3.14.0 升级）：管理员看全站文章（回收站除外），普通用户仅自己的。

    支持关键词 / 状态 / 分类 / 系列 筛选、多列排序、分页；批量操作见 bulk_posts。
    """
    user = db.session.get(User, session.get("user_id"))
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    cat_id = request.args.get("category_id", type=int)
    ser_id = request.args.get("series_id", type=int)
    sort = request.args.get("sort", "").strip() or "created"
    order = request.args.get("order", "").strip() or "desc"
    page = request.args.get("page", 1, type=int)
    per_page = 15
    base = Post.query.filter(Post.in_trash == False)
    if not (user and user.is_admin_role):
        base = base.filter(Post.author_id == user.id)
    if q:
        like = f"%{q}%"
        base = base.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if status == "published":
        base = base.filter(Post.published == True, Post.scheduled_at.is_(None))
    elif status == "draft":
        base = base.filter(Post.published == False, Post.scheduled_at.is_(None))
    elif status == "scheduled":
        base = base.filter(Post.scheduled_at.isnot(None), Post.published == False)
    elif status == "pinned":
        base = base.filter(Post.is_pinned == True)
    if cat_id:
        base = base.filter(Post.category_id == cat_id)
    if ser_id:
        base = base.filter(Post.series_id == ser_id)
    col_map = {"updated": Post.updated_at, "views": Post.views,
               "words": Post.word_count, "title": Post.title,
               "created": Post.created_at}
    col = col_map.get(sort, Post.created_at)
    direction = col.asc() if order == "asc" else col.desc()
    if sort == "title":
        query = base.order_by(direction)
    else:
        query = base.order_by(Post.is_pinned.desc(), direction)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return render_template(
        "admin/my_posts.html", posts=pagination.items, pagination=pagination,
        filter_q=q, filter_status=status, cats=cats, series=series,
        filter_category=cat_id, filter_series=ser_id, sort=sort, order=order,
        is_admin_view=bool(user and user.is_admin_role),
    )

@admin_bp.route("/posts/bulk", methods=["POST"])
@login_required
def bulk_posts():
    """文章列表批量操作（v3.14.0）：publish / unpublish / category / series / delete。

    权限沿用单篇规则：管理员可操作全站；普通用户仅自己的。删除为软删除（入回收站）。
    批量「发布」刻意不触发订阅邮件群发与站内推送，避免一次操作带来几十封打扰；
    需要推送的单篇发布请用「立即发布」。
    """
    user = db.session.get(User, session.get("user_id"))
    action = (request.form.get("action") or "").strip()
    ids = [int(x) for x in request.form.getlist("ids") if str(x).isdigit()]
    if not ids:
        flash("请先勾选要操作的文章")
        return redirect(url_for("admin.my_posts"))
    posts = Post.query.filter(Post.id.in_(ids), Post.in_trash == False).all()
    if not (user and user.is_admin_role):
        posts = [p for p in posts if p.author_id == user.id]
    if not posts:
        flash("没有可操作的文章（或没有权限）")
        return redirect(url_for("admin.my_posts"))
    if action == "publish":
        for p in posts:
            if not p.published:
                p.published = True
                p.scheduled_at = None
        db.session.commit()
        flash(f"已批量发布 {len(posts)} 篇（未触发订阅推送）")
    elif action == "unpublish":
        for p in posts:
            if p.published:
                p.published = False
                p.scheduled_at = None
        db.session.commit()
        flash(f"已批量转为草稿 {len(posts)} 篇")
    elif action in ("category", "series"):
        val = (request.form.get("value") or "").strip()
        if not str(val).isdigit():
            flash("请选择要移入的分类/系列")
            return redirect(url_for("admin.my_posts"))
        target_id = int(val)
        if action == "category":
            target = Category.query.get(target_id)
            for p in posts:
                p.category_id = target.id if target else None
        else:
            target = Series.query.get(target_id)
            for p in posts:
                p.series_id = target.id if target else None
        db.session.commit()
        flash(f"已移动 {len(posts)} 篇文章")
    elif action == "delete":
        for p in posts:
            try:
                db.session.add(RecycleBin(
                    post_id=p.id, title=p.title or "", slug=p.slug or "",
                    summary=p.summary or "", content=p.content or "", cover=p.cover or "",
                    category_id=p.category_id, author_id=p.author_id, series_id=p.series_id,
                    deleted_by=user.username if user else "",
                ))
            except Exception:
                pass
            p.in_trash = True
            p.deleted_at = utcnow()
            try:
                fts.delete_post(p.id)
            except Exception:
                pass
        db.session.commit()
        flash(f"已批量移入回收站 {len(posts)} 篇（可还原）")
    else:
        flash("未知操作")
    return redirect(url_for("admin.my_posts"))

@admin_bp.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    """删除文章（v3.0.0 软删除：进入回收站，可还原）。

    权限：管理员全部可操作；普通用户仅自己文章。删除时把文章快照存入回收站
    （RecycleBin）并标记 post.in_trash=True（前台/列表不可见），不真正从 post 表移除。
    彻底删除请在回收站页操作（仅管理员）。
    """
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能删除自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    # 入回收站：存快照 + 标记软删除
    try:
        db.session.add(RecycleBin(
            post_id=post.id, title=post.title or "", slug=post.slug or "",
            summary=post.summary or "", content=post.content or "", cover=post.cover or "",
            category_id=post.category_id, author_id=post.author_id, series_id=post.series_id,
            deleted_by=user.username if user else "",
        ))
    except Exception:
        pass
    post.in_trash = True
    post.deleted_at = utcnow()
    db.session.commit()
    try:
        fts.delete_post(post.id)  # 同步从 FTS 索引移除，避免搜索命中已删文章
    except Exception:
        pass
    log_audit("delete", "post", post.id, f"移入回收站：{post.title}", user=user)
    flash("文章已移入回收站（可在回收站还原）")
    back = request.args.get("back") or (
        "admin.my_posts" if user and not user.is_admin_role else "admin.dashboard")
    return redirect(url_for(back))
