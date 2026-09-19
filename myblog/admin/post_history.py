# -*- coding: utf-8 -*-
"""版本历史：历史列表 / 回滚 / 版本对比。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import *   # 复用导入、辅助函数与装饰器  # noqa: F401,F403
from . import admin_bp     # 同一蓝图对象
from _time import utcnow


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
