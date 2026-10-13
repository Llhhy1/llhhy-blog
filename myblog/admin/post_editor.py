# -*- coding: utf-8 -*-
"""写作面板：新建 / 编辑 / 自动保存 / 免登录预览 / 正文预览。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import _can_edit_post, _parse_scheduled, _sync_tags, cleanup_orphan_tags, create_post_core, login_required, update_post_core, admin_bp     # 同一蓝图对象
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from models import Category, Post, Series, User, db
from utils import count_words, fmt_bj
from _time import utcnow
from .taxonomy import _ensure_category_by_name, _ensure_series_by_name


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
        # v3.21.0 内容多语言：语言 + 译文组标识（任何角色都可为文章配对译文）
        lang = (request.form.get("lang") or "zh").strip() or "zh"
        translation_group = (request.form.get("translation_group") or "").strip()
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
            lang=lang, translation_group=translation_group,
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

@admin_bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能编辑自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if request.method == "POST":
        # v4.3.0：字段落库整块交给 update_post_core（后台与移动端 `/api/mobile/post/<id>` 共用
        # 同一实现）。原本这里是 80 行内联逻辑，移动端接口若要同样的编辑能力就得再抄一遍。
        err = update_post_core(post, request.form, user)
        if err:
            flash(err)
            return render_template("admin/edit_post.html", post=post)
        if post.scheduled_at is not None and not post.published:
            flash("已更新为定时发布，到点自动公开")
        else:
            flash("已保存修改")
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
                           now_local=fmt_bj(utcnow(), "%Y-%m-%dT%H:%M"),
                           preview_token=preview_token,
                           current_user=user)

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
    if data.get("lang") is not None:
        post.lang = (data.get("lang") or "zh").strip() or "zh"
    if data.get("translation_group") is not None:
        post.translation_group = (data.get("translation_group") or "").strip()
    wc, rm = count_words(post.content)
    post.word_count = wc
    post.reading_minutes = rm
    db.session.commit()
    cleanup_orphan_tags()  # v3.15.0：提交后清 0 使用标签
    return jsonify({"ok": True, "saved_at": fmt_bj(utcnow(), "%H:%M:%S")})


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