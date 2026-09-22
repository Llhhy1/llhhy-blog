# -*- coding: utf-8 -*-
"""回收站：列出 / 还原 / 彻底清除。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import *   # 复用导入、辅助函数与装饰器  # noqa: F401,F403
from . import admin_bp     # 同一蓝图对象
from _time import utcnow
from .post_editor import new_post
from .post_manage import delete_post


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
            # 清掉这篇的收录推送记录（v3.19.1）。
            # SQLite 默认不启用外键（未设 PRAGMA foreign_keys=ON），
            # 所以 seo_submission 的 FK 不会级联——不显式删就留下 post_id 悬空行。
            try:
                from models import db as _db, SeoSubmission
                SeoSubmission.query.filter_by(post_id=post.id).delete(
                    synchronize_session=False)
                _db.session.flush()
            except Exception:
                pass
            db.session.delete(post)
    db.session.delete(rb)
    db.session.commit()
    log_audit("purge", "post", rb.post_id, f"彻底删除：{rb.title}", user=_current_user_or_none())
    flash(f"已彻底删除：{rb.title}")
    return redirect(url_for("admin.recycle_bin"))
