# -*- coding: utf-8 -*-
"""分类 / 标签 / 系列治理：改名、删除、就地新建、一键整理。（v3.18.1 由 admin/posts.py 拆出，路由与行为不变）。"""
from ._helpers import *   # 复用导入、辅助函数与装饰器  # noqa: F401,F403
from . import admin_bp     # 同一蓝图对象
from _time import utcnow


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
