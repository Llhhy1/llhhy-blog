# -*- coding: utf-8 -*-
"""微动态（广场 / 个人动态）后台管理：列表检索、编辑、删除（含评论管理）。

背景：v3.12.0 之前 `/api/moment` 只提供「发布 / 点赞 / 评论」，动态一旦发布
在后台与前台都无处编辑、无处删除，只能直接改数据库。本模块补齐后台管理能力。

设计约束：
- **不新增数据库列、不改表结构**：编辑痕迹走 `log_audit`（审计日志）而非加 `edited_at`，
  避免 Alembic 基线 `f8f1f29b6ddf` 漂移与线上迁移风险。
- **删除走 ORM 级联**：`Moment.comments` 关系带 `cascade="all, delete-orphan"`，
  `db.session.delete(m)` 会自动清掉其下 `MomentComment`，不留孤儿行。
- 字数上限与前台 `api/social.py::post_moment` 保持一致（500 字）。
"""
from sqlalchemy import func

from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

MOMENT_MAX_LEN = 500
PER_PAGE = 20


@admin_bp.route("/moments", methods=["GET"])
@admin_required
def moments():
    """微动态列表：关键词搜索 + 按作者筛选 + 分页。"""
    page = request.args.get("page", 1, type=int)
    kw = (request.args.get("q") or "").strip()
    author_id = request.args.get("author_id", type=int)

    q = Moment.query
    if kw:
        q = q.filter(Moment.content.like("%" + kw + "%"))
    if author_id:
        q = q.filter(Moment.author_id == author_id)
    pagination = q.order_by(Moment.created_at.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False)
    rows = pagination.items

    # 评论数用一条 group_by 取回，避免每行一条 count 查询
    ids = [m.id for m in rows]
    if ids:
        comment_counts = dict(
            db.session.query(MomentComment.moment_id, func.count(MomentComment.id))
            .filter(MomentComment.moment_id.in_(ids))
            .group_by(MomentComment.moment_id).all()
        )
    else:
        comment_counts = {}

    # 作者下拉：只列真正发过动态的用户
    author_ids = db.session.query(Moment.author_id).filter(
        Moment.author_id.isnot(None)).distinct().all()
    authors = (User.query.filter(User.id.in_([a[0] for a in author_ids])).all()
               if author_ids else [])

    return render_template(
        "admin/moments.html", rows=rows, pagination=pagination,
        comment_counts=comment_counts, authors=authors,
        kw=kw, author_id=author_id,
        total_moments=Moment.query.count(),
        total_comments=MomentComment.query.count(),
    )


@admin_bp.route("/moment/<int:mid>/edit", methods=["GET", "POST"])
@admin_required
def edit_moment(mid):
    """编辑微动态正文（原样保留作者/发布时间/点赞数）。"""
    m = Moment.query.get_or_404(mid)
    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("动态内容不能为空")
            return redirect(url_for("admin.edit_moment", mid=mid))
        if len(content) > MOMENT_MAX_LEN:
            flash("动态最多 %d 字，当前 %d 字" % (MOMENT_MAX_LEN, len(content)))
            return redirect(url_for("admin.edit_moment", mid=mid))
        old = m.content or ""
        if old != content:
            m.content = content
            db.session.commit()
            log_audit("edit", "moment", m.id,
                      "编辑微动态：%s → %s" % (old[:40], content[:40]),
                      user=_current_user_or_none())
            flash("动态已保存")
        else:
            flash("内容没有变化")
        return redirect(url_for("admin.edit_moment", mid=mid))

    comments = m.comments.order_by(MomentComment.created_at.asc()).all()
    return render_template("admin/moment_edit.html", m=m, comments=comments,
                           max_len=MOMENT_MAX_LEN)


@admin_bp.route("/moment/<int:mid>/delete", methods=["POST"])
@admin_required
def delete_moment(mid):
    """删除微动态（级联删除其下评论）。"""
    m = Moment.query.get_or_404(mid)
    n_comments = m.comments.count()
    preview = (m.content or "")[:40]
    db.session.delete(m)
    db.session.commit()
    log_audit("delete", "moment", mid,
              "删除微动态（含 %d 条评论）：%s" % (n_comments, preview),
              user=_current_user_or_none())
    flash("动态已删除（含 %d 条评论）" % n_comments)
    return redirect(url_for("admin.moments"))


@admin_bp.route("/moment/<int:mid>/comment/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_moment_comment(mid, cid):
    """删除某条动态下的单条评论（cid 必须属于 mid，防越权改 id）。"""
    c = MomentComment.query.filter_by(id=cid, moment_id=mid).first_or_404()
    who = c.author or ""
    db.session.delete(c)
    db.session.commit()
    log_audit("delete", "moment_comment", cid,
              "删除微动态 #%d 的评论（%s）" % (mid, who[:40]),
              user=_current_user_or_none())
    flash("评论已删除")
    return redirect(url_for("admin.edit_moment", mid=mid))


@admin_bp.route("/moments/batch-delete", methods=["POST"])
@admin_required
def batch_delete_moments():
    """批量删除微动态：表单传入 moment id 列表（name=ids，多选）。"""
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if not ids:
        flash("请先勾选要删除的动态")
        return redirect(url_for("admin.moments"))
    deleted = 0
    n_comments = 0
    for mid in ids:
        m = Moment.query.get(mid)
        if m:
            n_comments += m.comments.count()
            db.session.delete(m)
            deleted += 1
    db.session.commit()
    log_audit("batch_delete", "moment", None,
              "批量删除 %d 条微动态（含 %d 条评论）" % (deleted, n_comments),
              user=_current_user_or_none())
    flash("已批量删除 %d 条动态（含 %d 条评论）" % (deleted, n_comments))
    return redirect(url_for("admin.moments"))
