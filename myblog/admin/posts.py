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
        # v3.14.0：就地新建分类/系列（编辑页「＋新建…」随表单提交，同名自动复用）
        new_category_name = (request.form.get("new_category_name") or "").strip()
        if new_category_name:
            category_id = _ensure_category_by_name(new_category_name)
        else:
            category_id = request.form.get("category_id") or None
            if category_id:
                category_id = int(category_id)
        published = request.form.get("published") == "on"
        scheduled_at = _parse_scheduled(request.form.get("scheduled_at"))
        # 置顶权限分层（v2.8.1）：仅管理员/超管可直接置顶；普通用户表单里的 is_pinned 一律忽略（防绕过）
        user = db.session.get(User, session.get("user_id"))
        is_pinned = (request.form.get("is_pinned") == "on") and bool(user and user.is_admin_role)
        new_series_name = (request.form.get("new_series_name") or "").strip()
        if new_series_name:
            series_id = _ensure_series_by_name(new_series_name)
        else:
            series_id = request.form.get("series_id") or None
            series_id = int(series_id) if series_id else None
        seo_description = (request.form.get("seo_description") or "").strip()
        seo_keywords = (request.form.get("seo_keywords") or "").strip()
        # v3.0.0 功能13/14：隐私空间 + 打赏（仅超管可设置）
        is_private = (request.form.get("is_private") == "on") and bool(user and user.is_super)
        reward_enabled = (request.form.get("reward_enabled") == "on") and bool(user and user.is_super)
        reward_qr = (request.form.get("reward_qr") or "").strip() if reward_enabled else ""
        # v3.12.2：复用发文唯一入口 create_post_core（与 /mcp-write 同源，行为一致）
        post = create_post_core(
            title=title, content=content, summary=summary, cover=cover,
            category_id=category_id, tags=request.form.get("tags", ""),
            series_id=series_id, seo_description=seo_description, seo_keywords=seo_keywords,
            published=published, scheduled_at=scheduled_at,
            author_id=session.get("user_id"),
            is_pinned=is_pinned, is_private=is_private,
            reward_enabled=reward_enabled, reward_qr=reward_qr,
        )
        # 普通用户发布后回到「我的文章」，管理员回仪表盘
        user = db.session.get(User, session.get("user_id"))
        if post.scheduled_at is not None and not post.published:
            flash("已设为定时发布，到点自动公开")
        else:
            flash("文章已发布" if post.published else "草稿已保存")
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
        # v3.14.0：编辑时就地新建分类/系列（同名自动复用）
        new_cat = (request.form.get("new_category_name") or "").strip()
        if new_cat:
            cid = _ensure_category_by_name(new_cat)
        post.category_id = int(cid) if cid else None
        new_ser = (request.form.get("new_series_name") or "").strip()
        if new_ser:
            sid = _ensure_series_by_name(new_ser)
        else:
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
        cleanup_orphan_tags()  # v3.15.0：提交后清 0 使用标签
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
    # v3.14.0：未发布且非隐私 → 生成免登录预览链接（24h 有效，URL 签名防猜）
    preview_token = ""
    if not post.published and not post.is_private and not post.in_trash:
        preview_token = _preview_token(post.id)
    # scheduled_at 转 datetime-local 输入框格式（YYYY-MM-DDTHH:MM）；按 UTC 显示
    scheduled_local = ""
    if post.scheduled_at:
        scheduled_local = fmt_bj(post.scheduled_at, "%Y-%m-%dT%H:%M")
    return render_template("admin/edit_post.html", post=post, cats=cats, series=series,
                           tag_names=tag_names, scheduled_local=scheduled_local,
                           now_local=fmt_bj(datetime.datetime.utcnow(), "%Y-%m-%dT%H:%M"),
                           preview_token=preview_token,
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
    back = request.args.get("back") or (
        "admin.my_posts" if user and not user.is_admin_role else "admin.dashboard")
    return redirect(url_for(back))

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
            p.deleted_at = datetime.datetime.utcnow()
            try:
                fts.delete_post(p.id)
            except Exception:
                pass
        db.session.commit()
        flash(f"已批量移入回收站 {len(posts)} 篇（可还原）")
    else:
        flash("未知操作")
    return redirect(url_for("admin.my_posts"))

@admin_bp.route("/post/<int:post_id>/autosave", methods=["POST"])
@login_required
def autosave_post(post_id):
    """云端草稿自动保存（v3.14.0）：编辑页防抖调用，仅更新内容类字段。

    刻意不做的事：不记版本历史、不触发发布/订阅/站内通知、不改发布状态与定时时间
    ——避免把用户未勾选的动作悄悄执行。新建文章在首次手动「保存」前没有 post_id，
    此接口不适用（前端只对已有 id 的文章启用云端自动保存）。
    """
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        return jsonify({"ok": False, "error": "无权编辑"}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "标题不能为空"}), 400
    post.title = title
    if data.get("content") is not None:
        post.content = data.get("content")
    if data.get("summary") is not None:
        post.summary = (data.get("summary") or "").strip()
    if data.get("cover") is not None:
        post.cover = (data.get("cover") or "").strip()
    new_cat = (data.get("new_category_name") or "").strip()
    if new_cat:
        post.category_id = _ensure_category_by_name(new_cat)
    elif "category_id" in data:
        v = data.get("category_id")
        post.category_id = int(v) if str(v).isdigit() else None
    new_ser = (data.get("new_series_name") or "").strip()
    if new_ser:
        post.series_id = _ensure_series_by_name(new_ser)
    elif "series_id" in data:
        v = data.get("series_id")
        post.series_id = int(v) if str(v).isdigit() else None
    if data.get("tags") is not None:
        _sync_tags(post, data.get("tags", ""))
    if data.get("seo_description") is not None:
        post.seo_description = (data.get("seo_description") or "").strip()
    if data.get("seo_keywords") is not None:
        post.seo_keywords = (data.get("seo_keywords") or "").strip()
    wc, rm = count_words(post.content)
    post.word_count = wc
    post.reading_minutes = rm
    db.session.commit()
    cleanup_orphan_tags()  # v3.15.0：提交后清 0 使用标签
    return jsonify({"ok": True, "saved_at": fmt_bj(datetime.datetime.utcnow(), "%H:%M:%S")})

@admin_bp.route("/post/<int:post_id>/history/diff")
@login_required
def post_diff(post_id):
    """版本对比（v3.14.0）：?a=<历史版本 id>，与当前正文做逐行 diff。

    不指定 a 时默认与最近的上一版本对比。仅差异行 + 少量上下文渲染，避免长文整页刷屏。
    """
    post = Post.query.get_or_404(post_id)
    user = _current_user_or_none()
    if not _can_edit_post(user, post):
        flash("只能查看自己文章的版本对比")
        return redirect(url_for("admin.my_posts"))
    versions = PostHistory.query.filter_by(post_id=post_id) \
        .order_by(PostHistory.created_at.desc()).all()
    a_id = request.args.get("a", type=int)
    base_ver = None
    if a_id:
        base_ver = PostHistory.query.filter_by(id=a_id, post_id=post_id).first()
    if base_ver is None and versions:
        base_ver = versions[0]
    if base_ver is None:
        flash("暂无历史版本可对比")
        return redirect(url_for("admin.post_history", post_id=post_id))
    rows = _line_diff(base_ver.content or "", post.content or "")
    return render_template("admin/post_diff.html", post=post, base_ver=base_ver,
                           current_title=post.title, rows=rows, versions=versions,
                           selected_a=base_ver.id)

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
    """删除分类（v3.14.0 升级）：可带 move_to=<目标分类 id> 先转移文章再删除，避免文章变无分类。"""
    cat = Category.query.get_or_404(cid)
    move_to = request.form.get("move_to") or ""
    if str(move_to).isdigit() and int(move_to) != cid:
        target = Category.query.get(int(move_to))
        if target:
            for p in cat.posts.all():
                p.category_id = target.id
            db.session.flush()  # 先落库转移：否则 SQLAlchemy 删除父行前会把子外键统一置 NULL，覆盖转移结果
    db.session.delete(cat)
    db.session.commit()
    flash("分类已删除")
    return redirect(url_for("admin.categories"))

@admin_bp.route("/tags", methods=["GET", "POST"])
@admin_required
def tags():
    from utils import normalize_tag_key
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "merge":
            merged = merge_duplicate_tags()
            cleaned = cleanup_orphan_tags()
            flash(f"标签整理完成：合并重复 {merged} 个，清理 0 使用 {cleaned} 个")
            log_audit("merge", "tag", 0, f"合并重复 {merged} + 清理未使用 {cleaned}", user=_current_user_or_none())
            return redirect(url_for("admin.tags"))
        name = (request.form.get("name") or "").strip()
        if name:
            key = normalize_tag_key(name)
            exists = next((t for t in Tag.query.all() if normalize_tag_key(t.name) == key), None)
            if exists:
                flash(f"标签「{exists.name}」已存在（含大小写/空白变体），未重复添加")
            else:
                db.session.add(Tag(name=name, slug=unique_model_slug(Tag, name, max_len=90)))
                db.session.commit()
                flash("标签已添加")
        return redirect(url_for("admin.tags"))
    rows = []
    orphan_count = 0
    for t in Tag.query.order_by(Tag.id).all():
        used = len(list(t.posts))
        if used == 0:
            orphan_count += 1
        rows.append((t, used))
    return render_template("admin/tags.html", tags=rows, orphan_count=orphan_count)

@admin_bp.route("/tag/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_tag(tid):
    tag = Tag.query.get_or_404(tid)
    used = len(list(tag.posts))
    if used:
        flash(f"标签「{tag.name}」正被 {used} 篇文章使用：请先移除文章里的该标签，或用「一键整理」合并")
        return redirect(url_for("admin.tags"))
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
                name=name, slug=unique_model_slug(Series, name, max_len=100),
                description=(request.form.get("description") or "").strip(),
                cover=(request.form.get("cover") or "").strip(),
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("系列已添加")
        return redirect(url_for("admin.manage_series"))
    series = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return render_template("admin/series.html", series=series)

@admin_bp.route("/series/<int:sid>/rename", methods=["POST"])
@admin_required
def rename_series(sid):
    """系列编辑（v3.14.0）：改名（slug 自动重算并保持唯一）/简介/封面/排序。"""
    s = Series.query.get_or_404(sid)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("系列名称不能为空")
        return redirect(url_for("admin.manage_series"))
    s.name = name
    s.slug = unique_model_slug(Series, name, exclude_id=s.id, max_len=100)
    s.description = (request.form.get("description") or "").strip()
    s.cover = (request.form.get("cover") or "").strip()
    s.sort = request.form.get("sort", s.sort or 0, type=int)
    db.session.commit()
    flash(f"系列已更新：{name}")
    return redirect(url_for("admin.manage_series"))

@admin_bp.route("/series/<int:sid>/delete", methods=["POST"])
@admin_required
def delete_series(sid):
    s = Series.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash("系列已删除")
    return redirect(url_for("admin.manage_series"))


# ---------- v3.14.0：就地新建 / 预览令牌 / 版本 diff 辅助 ----------

def _ensure_category_by_name(name):
    """就地新建分类：Category.name 唯一 → 同名自动复用；slug 全局唯一。返回分类 id。"""
    cat = Category.query.filter_by(name=name).first()
    if not cat:
        cat = Category(name=name, slug=unique_model_slug(Category, name, max_len=80))
        db.session.add(cat)
        db.session.flush()
    return cat.id


def _ensure_series_by_name(name):
    """就地新建系列：Series.name 无唯一约束，必须按名显式查重；slug 全局唯一。返回系列 id。"""
    ser = Series.query.filter_by(name=name).first()
    if not ser:
        ser = Series(name=name, slug=unique_model_slug(Series, name, max_len=100), sort=0)
        db.session.add(ser)
        db.session.flush()
    return ser.id


def _preview_token(post_id, ttl=86400):
    """生成未发布稿预览签名令牌：post_id:过期时间戳:HMAC 摘要（默认 24h 有效）。"""
    import hashlib as _hashlib
    import hmac as _hmac
    import time as _time
    exp = int(_time.time()) + ttl
    raw = f"{post_id}:{exp}"
    key = (current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    sig = _hmac.new(key, ("pv:" + raw).encode("utf-8"), _hashlib.sha256).hexdigest()[:20]
    return f"{raw}:{sig}"


def _check_preview_token(token):
    """校验预览令牌：签名不符或已过期一律返回 None（视为不存在）。"""
    import hashlib as _hashlib
    import hmac as _hmac
    import time as _time
    parts = (token or "").split(":")
    if len(parts) != 3:
        return None
    post_id, exp, sig = parts
    try:
        exp = int(exp)
    except (TypeError, ValueError):
        return None
    key = (current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    expect = _hmac.new(key, ("pv:" + f"{post_id}:{exp}").encode("utf-8"),
                       _hashlib.sha256).hexdigest()[:20]
    if not _hmac.compare_digest(sig, expect):
        return None
    if exp < int(_time.time()):
        return None
    try:
        return int(post_id)
    except (TypeError, ValueError):
        return None


@admin_bp.route("/md-preview", methods=["POST"])
@login_required
def md_preview():
    """写作面板实时预览接口（v3.14.0）：与前台共用 render_markdown（同一渲染+清洗管线）。"""
    from utils import render_markdown as _render_md
    content = request.form.get("content", "")
    return _render_md(content)


@admin_bp.route("/preview/<token>")
def preview_post(token):
    """未发布稿免登录预览（v3.14.0）：带签名 + 24h 有效期，适合发给朋友先睹为快。

    仅对「未发布 + 非隐私」的文章签发；已在回收站的直接 404。前台布局复用 style.css。
    """
    from utils import render_post_html as _render_html
    post_id = _check_preview_token(token)
    if post_id is None:
        abort(404)
    post = Post.query.get_or_404(post_id)
    if post.in_trash or post.is_private or post.published:
        abort(404)
    html = _render_html(post)
    return render_template("admin/preview.html", post=post, content_html=html)


def _line_diff(old_text, new_text, context=2):
    """逐行 diff（v3.14.0）：用 difflib.SequenceMatcher 生成 opcodes，等值段只留上下文。

    返回 [(kind, old_line, new_line)]，kind ∈ equal/del/add（add 行 old 为空，反之亦然）。
    """
    import difflib
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    sm = difflib.SequenceMatcher(None, old_lines, new_lines)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            chunk = old_lines[i1:i2]
            if len(chunk) > context * 2 + 1:
                for line in chunk[:context]:
                    rows.append(("equal", line, line))
                rows.append(("skip", "", ""))
                for line in chunk[-context:]:
                    rows.append(("equal", line, line))
            else:
                for line in chunk:
                    rows.append(("equal", line, line))
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                rows.append(("del", line, ""))
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                rows.append(("add", "", line))
        else:  # replace
            for line in old_lines[i1:i2]:
                rows.append(("del", line, ""))
            for line in new_lines[j1:j2]:
                rows.append(("add", "", line))
    return rows
