# -*- coding: utf-8 -*-
"""回收站：列出 / 还原 / 彻底清除。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import (_current_user_or_none, admin_required, log_audit, login_required,
                       unique_slug, admin_bp)     # 同一蓝图对象
from flask import flash, redirect, render_template, url_for
from models import Post, RecycleBin, db
import fts
import contextlib


def restore_recycle_core(rb, user=None):
    """回收站还原的**唯一**实现（后台视图 + 移动端 `/api/mobile/trash/<id>/restore` 共用）。

    两个分支都必须保留：
    - 原 post 仍在（只被标记 `in_trash`）→ 清标记并**重新同步 FTS**。⚠️ 入回收站时已
      `fts.delete_post()`（见 `trash_post_core`），还原不重新同步这篇就永久搜不到。
    - 原 post 已被彻底删除 → 用快照重建一篇**草稿**（不自动公开，交人工检查）。

    返回 `(提示文案, 还原后的 post_id)`。
    """
    if rb.restored:
        return "该记录已还原过", None
    post = db.session.get(Post, rb.post_id) if rb.post_id else None
    if post and post.in_trash:
        post.in_trash = False
        post.deleted_at = None
        db.session.commit()
        fts.sync_post_quiet(post)
        log_audit("restore", "post", post.id, f"从回收站还原：{rb.title}", user=user)
        return f"已还原文章：{rb.title}", post.id
    new_post = Post(
        title=rb.title, slug=unique_slug(rb.title + "-" + str(rb.id)),
        summary=rb.summary, content=rb.content, cover=rb.cover,
        category_id=rb.category_id, published=False, author_id=rb.author_id,
        series_id=rb.series_id,
    )
    db.session.add(new_post)
    db.session.flush()
    with contextlib.suppress(Exception):
        fts.sync_post(new_post)
    log_audit("restore", "post", new_post.id, f"从回收站快照重建：{rb.title}", user=user)
    return f"已用快照重建文章：{rb.title}（草稿状态，请检查后发布）", new_post.id


def purge_recycle_core(rb, user=None):
    """彻底删除的**唯一**实现：删 post 表行 + 删回收站记录 + 移出 FTS + 清收录记录。

    ⚠️ `SeoSubmission` 必须显式删：SQLite 默认不开外键（未设 `PRAGMA foreign_keys=ON`），
    不删就留下 `post_id` 悬空行。
    """
    if rb.post_id:
        post = db.session.get(Post, rb.post_id)
        if post:
            with contextlib.suppress(Exception):
                fts.delete_post(post.id)
            try:
                from models import db as _db, SeoSubmission
                SeoSubmission.query.filter_by(post_id=post.id).delete(
                    synchronize_session=False)
                _db.session.flush()
            except Exception:  # noqa: BLE001 —— 与 v4.2.0 原实现一致：清收录记录失败不该阻断删除
                pass
            db.session.delete(post)
    db.session.delete(rb)
    db.session.commit()
    log_audit("purge", "post", rb.post_id, f"彻底删除：{rb.title}", user=user)
    return f"已彻底删除：{rb.title}"


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
    # v4.3.0：逻辑抽到 restore_recycle_core（移动端 API 复用，避免两套还原行为）
    msg, _pid = restore_recycle_core(rb, user=_current_user_or_none())
    if rb.restored is False:
        rb.restored = True
        db.session.commit()
    flash(msg)
    return redirect(url_for("admin.recycle_bin"))

@admin_bp.route("/recycle-bin/<int:rid>/purge", methods=["POST"])
@login_required
@admin_required
def purge_post(rid):
    """彻底删除：委托 `purge_recycle_core`（v4.3.0 抽出，与移动端共用同一实现）。"""
    rb = RecycleBin.query.get_or_404(rid)
    flash(purge_recycle_core(rb, user=_current_user_or_none()))
    return redirect(url_for("admin.recycle_bin"))
