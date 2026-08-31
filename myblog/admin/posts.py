# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

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

@admin_bp.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("标题不能为空")
            return render_template("admin/edit_post.html", post=None)
        content = request.form.get("content", "")
        summary = (request.form.get("summary") or "").strip()
        cover = (request.form.get("cover") or "").strip()
        category_id = request.form.get("category_id") or None
        if category_id:
            category_id = int(category_id)
        published = request.form.get("published") == "on"
        scheduled_at = _parse_scheduled(request.form.get("scheduled_at"))
        # 定时发布：填了未来时间则先存为未发布，后台线程到点自动翻 published
        if scheduled_at is not None and scheduled_at > datetime.datetime.utcnow():
            published = False
        # 置顶权限分层（v2.8.1）：仅管理员/超管可直接置顶；普通用户表单里的 is_pinned 一律忽略（防绕过）
        user = db.session.get(User, session.get("user_id"))
        is_pinned = (request.form.get("is_pinned") == "on") and bool(user and user.is_admin_role)
        series_id = request.form.get("series_id") or None
        seo_description = (request.form.get("seo_description") or "").strip()
        seo_keywords = (request.form.get("seo_keywords") or "").strip()
        # v3.0.0 功能13/14：隐私空间 + 打赏（仅超管可设置）
        is_private = (request.form.get("is_private") == "on") and bool(user and user.is_super)
        reward_enabled = (request.form.get("reward_enabled") == "on") and bool(user and user.is_super)
        reward_qr = (request.form.get("reward_qr") or "").strip() if reward_enabled else ""
        # v3.7.0：链接后缀（slug）强制由后台全局设置（slug_mode/slug_template）决定，不再允许单篇覆盖。
        # 构造时先用标题占位（保证 nullable），flush 拿到 id/category 后统一按全局模板生成最终 slug。
        # v3.0.0 功能12：字数统计 + 阅读时长
        wc, rm = count_words(content)
        post = Post(
            title=title, slug=title, summary=summary, content=content,
            cover=cover, category_id=category_id, published=published,
            scheduled_at=scheduled_at, is_pinned=is_pinned,
            seo_description=seo_description, seo_keywords=seo_keywords,
            series_id=int(series_id) if series_id else None,
            author_id=session.get("user_id"),  # 记录作者：普通用户发表的文章归属自己
            word_count=wc, reading_minutes=rm,
            is_private=is_private, reward_enabled=reward_enabled, reward_qr=reward_qr,
        )
        db.session.add(post)
        db.session.flush()  # 先把文章放进会话，避免标签关联警告
        # flush 后 post.id / post.category 可用：按全局模板生成最终 slug（用户无法手工干预）
        post.slug = apply_slug_template(post, title)
        _sync_tags(post, request.form.get("tags", ""))
        # v3.0.0 功能5：保存首个版本历史（新建即 v1）
        _save_post_history(post, user.username if user else "")
        db.session.commit()
        try:
            fts.sync_post(post)
        except Exception:
            pass
        if published:
            try:
                notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
            except Exception:
                pass
            # C3 邮件群发：新文章发布时异步通知所有订阅者（未配置 SMTP 自动跳过）
            try:
                mail_notify.notify_subscribers_async(post)
            except Exception:
                pass
        if scheduled_at is not None and not published:
            flash("已设为定时发布，到点自动公开")
        else:
            flash("文章已发布" if published else "草稿已保存")
        # 普通用户发布后回到「我的文章」，管理员回仪表盘
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    user = db.session.get(User, session.get("user_id"))
    return render_template("admin/edit_post.html", post=None, cats=cats, series=series,
                           current_user=user)

@admin_bp.route("/my-posts")
@login_required
def my_posts():
    """「我的文章」：普通用户查看/管理自己发表的文章（支持分页+筛选，v2.8.0）。"""
    user = db.session.get(User, session.get("user_id"))
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12
    query = Post.query.filter_by(author_id=user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if status == "published":
        query = query.filter(Post.published == True, Post.scheduled_at.is_(None))
    elif status == "draft":
        query = query.filter(Post.published == False, Post.scheduled_at.is_(None))
    elif status == "scheduled":
        query = query.filter(Post.scheduled_at.isnot(None), Post.published == False)
    elif status == "pinned":
        query = query.filter(Post.is_pinned == True)
    pagination = query.order_by(Post.is_pinned.desc(), Post.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return render_template("admin/my_posts.html", posts=pagination.items,
                           pagination=pagination, filter_q=q, filter_status=status)

@admin_bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能编辑自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if request.method == "POST":
        was_published = post.published
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("标题不能为空")
            return render_template("admin/edit_post.html", post=post)
        old_title = post.title  # 保留旧标题，用于版本历史判断（与 old_content 对称；v3.10.6 评审发现：未捕获则"只改标题"永不触发历史）
        post.title = title
        # v3.7.0：链接后缀（slug）强制由后台全局设置（slug_mode/slug_template）决定，用户无法手工覆盖。
        # 标题 slug 未变 → 保持原 slug 不动（不破坏已有 URL / SEO）；
        # 标题 slug 变了（或原 slug 为空）→ 套用全局模板重新生成。
        if make_slug(title) != post.slug:
            post.slug = apply_slug_template(post, title)
        post.summary = (request.form.get("summary") or "").strip()
        content = request.form.get("content", "")  # 新内容（局部变量，供后面比较/保存）
        old_content = post.content  # 保留旧内容，用于版本历史判断（v3.0.0 功能5）
        post.content = content
        post.cover = (request.form.get("cover") or "").strip()
        cid = request.form.get("category_id") or None
        post.category_id = int(cid) if cid else None
        sid = request.form.get("series_id") or None
        post.series_id = int(sid) if sid else None
        scheduled_at = _parse_scheduled(request.form.get("scheduled_at"))
        published = request.form.get("published") == "on"
        # 定时发布：填了未来时间则先存为未发布，后台线程到点自动翻 published
        if scheduled_at is not None and scheduled_at > datetime.datetime.utcnow():
            published = False
        else:
            scheduled_at = None  # 立即发布/草稿：清空定时，避免历史脏值
        post.published = published
        post.scheduled_at = scheduled_at
        # 置顶权限分层（v2.8.1）：仅管理员/超管可改置顶；普通用户即便提交 is_pinned 也被忽略（防绕过）
        if user.is_admin_role:
            post.is_pinned = request.form.get("is_pinned") == "on"
            post.pin_requested = False  # 管理员直接操作置顶，无需申请态
        post.seo_description = (request.form.get("seo_description") or "").strip()
        post.seo_keywords = (request.form.get("seo_keywords") or "").strip()
        # v3.0.0 功能13/14：隐私空间 + 打赏（仅超管可设置）
        if user.is_super:
            post.is_private = request.form.get("is_private") == "on"
            post.reward_enabled = request.form.get("reward_enabled") == "on"
            if post.reward_enabled:
                post.reward_qr = (request.form.get("reward_qr") or "").strip()
            else:
                post.reward_qr = ""
        # v3.0.0 功能12：字数统计 + 阅读时长
        wc, rm = count_words(post.content)
        post.word_count = wc
        post.reading_minutes = rm
        _sync_tags(post, request.form.get("tags", ""))
        # v3.0.0 功能5：内容/标题有变化时保存版本历史
        # 注意：post.content 已是新值，必须与修复前保留的旧值比较（旧 bug：引用未定义的 content 导致 NameError→500）
        # 标题同理用 old_title 比较（v3.10.6 评审修复：post.title 已被上方赋为新值，直接比 title 恒为假）
        if post.content != old_content or old_title != title:
            _save_post_history(post, user.username if user else "")
        db.session.commit()
        try:
            fts.sync_post(post)
        except Exception:
            pass
        if post.published and not was_published:
            try:
                notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
            except Exception:
                pass
            # C3 邮件群发：草稿转发布时也通知订阅者
            try:
                mail_notify.notify_subscribers_async(post)
            except Exception:
                pass
        if scheduled_at is not None and not published:
            flash("已更新为定时发布，到点自动公开")
        else:
            flash("已保存修改")
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    tag_names = ", ".join(t.name for t in post.tags)
    # scheduled_at 转 datetime-local 输入框格式（YYYY-MM-DDTHH:MM）；按 UTC 显示
    scheduled_local = ""
    if post.scheduled_at:
        scheduled_local = fmt_bj(post.scheduled_at, "%Y-%m-%dT%H:%M")
    return render_template("admin/edit_post.html", post=post, cats=cats, series=series,
                           tag_names=tag_names, scheduled_local=scheduled_local,
                           now_local=fmt_bj(datetime.datetime.utcnow(), "%Y-%m-%dT%H:%M"),
                           current_user=user)

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
    post.deleted_at = datetime.datetime.utcnow()
    db.session.commit()
    try:
        fts.delete_post(post.id)  # 同步从 FTS 索引移除，避免搜索命中已删文章
    except Exception:
        pass
    log_audit("delete", "post", post.id, f"移入回收站：{post.title}", user=user)
    flash("文章已移入回收站（可在回收站还原）")
    return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                    else url_for("admin.dashboard"))

@admin_bp.route("/recycle-bin")
@login_required
@admin_required
def recycle_bin():
    """回收站列表：展示被软删除的文章，可还原或彻底删除。"""
    rows = RecycleBin.query.filter_by(restored=False).order_by(RecycleBin.created_at.desc()).all()
    return render_template("admin/recycle_bin.html", rows=rows)

@admin_bp.route("/recycle-bin/<int:rid>/restore", methods=["POST"])
@login_required
@admin_required
def restore_post(rid):
    """从回收站还原：找到原 post（未被彻底删除）则清 in_trash；否则用快照重建。"""
    rb = RecycleBin.query.get_or_404(rid)
    if rb.restored:
        flash("该记录已还原过")
        return redirect(url_for("admin.recycle_bin"))
    post = None
    if rb.post_id:
        post = Post.query.get(rb.post_id)
    if post and post.in_trash:
        post.in_trash = False
        post.deleted_at = None
        db.session.commit()
        log_audit("restore", "post", post.id, f"从回收站还原：{rb.title}", user=_current_user_or_none())
        flash(f"已还原文章：{rb.title}")
    else:
        # 原 post 已彻底删除或不存在：用快照重建一篇新文章
        new_post = Post(
            title=rb.title, slug=unique_slug(rb.title + "-" + str(rb.id)),
            summary=rb.summary, content=rb.content, cover=rb.cover,
            category_id=rb.category_id, published=False, author_id=rb.author_id,
            series_id=rb.series_id,
        )
        db.session.add(new_post)
        db.session.flush()
        try:
            fts.sync_post(new_post)
        except Exception:
            pass
        log_audit("restore", "post", new_post.id, f"从回收站快照重建：{rb.title}", user=_current_user_or_none())
        flash(f"已用快照重建文章：{rb.title}（草稿状态，请检查后发布）")
    rb.restored = True
    db.session.commit()
    return redirect(url_for("admin.recycle_bin"))

@admin_bp.route("/recycle-bin/<int:rid>/purge", methods=["POST"])
@login_required
@admin_required
def purge_post(rid):
    """彻底删除：从 post 表真正移除（若仍在）+ 删除回收站记录 + 删 FTS。"""
    rb = RecycleBin.query.get_or_404(rid)
    if rb.post_id:
        post = Post.query.get(rb.post_id)
        if post:
            try:
                fts.delete_post(post.id)
            except Exception:
                pass
            db.session.delete(post)
    db.session.delete(rb)
    db.session.commit()
    log_audit("purge", "post", rb.post_id, f"彻底删除：{rb.title}", user=_current_user_or_none())
    flash(f"已彻底删除：{rb.title}")
    return redirect(url_for("admin.recycle_bin"))

@admin_bp.route("/post/<int:post_id>/history")
@login_required
def post_history(post_id):
    """查看某文章的版本历史列表（可对比 / 回滚）。"""
    post = Post.query.get_or_404(post_id)
    user = _current_user_or_none()
    if not _can_edit_post(user, post):
        flash("只能查看自己文章的版本历史")
        return redirect(url_for("admin.my_posts"))
    versions = PostHistory.query.filter_by(post_id=post_id)\
        .order_by(PostHistory.created_at.desc()).all()
    return render_template("admin/post_history.html", post=post, versions=versions)

@admin_bp.route("/post/<int:post_id>/history/<int:hid>/rollback", methods=["POST"])
@login_required
def rollback_post(post_id, hid):
    """把文章回滚到指定历史版本（写回 title/summary/content 并保存新历史）。"""
    post = Post.query.get_or_404(post_id)
    user = _current_user_or_none()
    if not _can_edit_post(user, post):
        flash("只能回滚自己文章的版本")
        return redirect(url_for("admin.my_posts"))
    h = PostHistory.query.filter_by(id=hid, post_id=post_id).first_or_404()
    # 回滚前先存当前版本，便于再撤销回滚
    _save_post_history(post, user.username if user else "")
    post.title = h.title
    post.summary = h.summary
    post.content = h.content
    db.session.commit()
    try:
        fts.sync_post(post)
    except Exception:
        pass
    log_audit("rollback", "post", post.id, f"回滚到版本 {hid}", user=user)
    flash("已回滚到该历史版本")
    return redirect(url_for("admin.post_history", post_id=post_id))

@admin_bp.route("/category/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_category(cid):
    cat = Category.query.get_or_404(cid)
    db.session.delete(cat)
    db.session.commit()
    flash("分类已删除")
    return redirect(url_for("admin.categories"))

@admin_bp.route("/tags", methods=["GET", "POST"])
@admin_required
def tags():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Tag(name=name, slug=make_slug(name)))
            db.session.commit()
            flash("标签已添加")
        return redirect(url_for("admin.tags"))
    tags = Tag.query.order_by(Tag.id).all()
    return render_template("admin/tags.html", tags=tags)

@admin_bp.route("/tag/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_tag(tid):
    tag = Tag.query.get_or_404(tid)
    db.session.delete(tag)
    db.session.commit()
    flash("标签已删除")
    return redirect(url_for("admin.tags"))

@admin_bp.route("/series", methods=["GET", "POST"])
@admin_required
def manage_series():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Series(
                name=name, slug=make_slug(name),
                description=(request.form.get("description") or "").strip(),
                cover=(request.form.get("cover") or "").strip(),
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("系列已添加")
        return redirect(url_for("admin.manage_series"))
    series = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return render_template("admin/series.html", series=series)

@admin_bp.route("/series/<int:sid>/delete", methods=["POST"])
@admin_required
def delete_series(sid):
    s = Series.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash("系列已删除")
    return redirect(url_for("admin.manage_series"))
