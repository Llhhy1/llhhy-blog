# -*- coding: utf-8 -*-
"""分类 / 标签 / 系列治理：改名、删除、就地新建、一键整理。

（v3.18.1 由 admin/posts.py 拆出，路由与行为不变。）

v4.4.0：把「怎么建、怎么改名、删的时候文章怎么办」抽成本文件的 `*_core` 函数，
后台 SSR 路由与移动端 JSON（`api/mobile.py` 函数内导入）共用同一套判据 —— 理由与
`create_post_core` 一致：两套实现迟早漂移，而这里漂移的后果是文章被静默置成无分类。
"""
from ._helpers import (_current_user_or_none, admin_required, cleanup_orphan_tags, log_audit,
                       merge_duplicate_tags, unique_model_slug, admin_bp)   # 同一蓝图对象
from flask import flash, redirect, render_template, request, url_for
from models import Category, Post, PostTag, Series, Tag, db


# ---------------------------------------------------------------- 写入核心


def _sort_of(form, default=0):
    """排序字段取值：非数字一律回落到 `default`（后台原先靠 `type=int` 静默给 0）。"""
    try:
        return int(form.get("sort") or default)
    except (TypeError, ValueError):
        return default


def create_category_core(name, slug=""):
    """新建分类 → `(id, "")`；校验不过 → `(None, 错误文案)`。

    判据与后台原实现逐字一致：`Category.name` 唯一，**精确同名**拒绝。
    （`_ensure_category_by_name` 也是精确名 —— 两处同判据才不会「App 建一个、
    编辑器再建一个」双胞胎。）

    v5.4.0：`slug` 可选；留空则由名字自动转 ASCII（汉字转拼音）。
    """
    name = (name or "").strip()
    if not name:
        return None, "分类名称不能为空"
    if Category.query.filter_by(name=name).first():
        return None, f"已存在同名分类「{name}」，请勿重复添加"
    cat = Category(name=name, slug=unique_model_slug(Category, name, max_len=80, explicit=slug))
    db.session.add(cat)
    db.session.commit()
    return cat.id, ""


def rename_category_core(cat, name, slug=None):
    """分类改名 → `(错误文案, slug 变化说明)`。错误文案非空即未改动。

    v5.4.0 起**改名不再自动重算 slug**。slug 是对外地址、名字是给人看的；
    改名顺带换地址会让所有已发出去的 `/category/<旧slug>` 直接 404（本站没有别名表）。
    因此只有显式传 `slug`（后台表单的「地址 slug」输入框）才会改地址，
    返回的说明会告诉 UI「旧链接会失效」。
    """
    name = (name or "").strip()
    if not name:
        return "分类名称不能为空", ""
    dup = Category.query.filter(Category.name == name, Category.id != cat.id).first()
    if dup:
        return (f"已存在同名分类「{name}」，未修改"
                "（如需合并：删除本分类并把文章转移到目标分类）"), ""
    cat.name = name
    note = _apply_slug_change(cat, Category, slug, 80, "/category")
    db.session.commit()
    return "", note


def delete_category_core(cat, move_to=None):
    """删除分类 → `(转移走的文章数, 分类名)`；篇数为 0 表示文章全部变成「无分类」。

    ⚠️ 必须 `db.session.flush()`：不先落库转移，SQLAlchemy 删父行前会把子表外键统一
    置 NULL，把刚转移好的结果又覆盖掉（原实现行内注释就记着这条）。
    """
    target = _resolve_target(Category, cat.id, move_to)
    moved = 0
    if target:
        for p in cat.posts.all():
            p.category_id = target.id
            moved += 1
        db.session.flush()
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    return moved, name


def tag_usage_counts():
    """一次查询得到 `{标签 id: 使用篇数}`（后台标签页与 `/api/mobile/tags` 共用）。

    见 `delete_tag_core` 里那段关于 `Tag.posts` 的说明：列表页要给几十个标签各数一次
    用量，逐行 `len(t.posts)` 等于把每张关联表都拖进内存一遍。
    """
    rows = (db.session.query(PostTag.tag_id, db.func.count(PostTag.post_id))
            .group_by(PostTag.tag_id).all())
    return dict(rows)   # 每行是 (tag_id, count) 二元组，直接喂 dict() 即可


def create_tag_core(name, slug=""):
    """新建标签 → `(id, "")`；校验不过 → `(None, 错误文案)`。

    查重用 `normalize_tag_key`（小写 + 去所有空白）扫全表 —— 与后台一致，
    否则 `AI` / `ai` / `a i` 会加成三个标签，前台标签页出现近似重复项。

    v5.4.0：`slug` 可选。留空则由名字自动转纯 ASCII（汉字走 pypinyin），
    所以新建「智能体安全」默认得到 `zhi-neng-ti-an-quan`，而不是中文地址。
    """
    from utils import normalize_tag_key
    name = (name or "").strip()
    if not name:
        return None, "标签名称不能为空"
    key = normalize_tag_key(name)
    exists = next((t for t in Tag.query.all() if normalize_tag_key(t.name) == key), None)
    if exists:
        return None, f"标签「{exists.name}」已存在（含大小写/空白变体），未重复添加"
    tag = Tag(name=name, slug=unique_model_slug(Tag, name, max_len=90, explicit=slug))
    db.session.add(tag)
    db.session.commit()
    return tag.id, ""


def set_tag_slug_core(tag, slug):
    """改标签地址 → `(错误文案, 说明)`；成功时错误文案为 ""。

    标签没有「改名」入口（改名等于换个标签，用合并/删除更清楚），
    这里只解决「中文 slug 想换成更可读的英文」。旧地址仍会被
    `/api/tag/<旧slug>` 按 `name` 反查并跳转，所以换 slug 不会立刻打死外链。
    """
    raw = (slug or "").strip()
    if not raw:
        return "地址不能为空", ""
    old = tag.slug
    tag.slug = unique_model_slug(Tag, tag.name, exclude_id=tag.id, max_len=90, explicit=raw)
    db.session.commit()
    if tag.slug == old:
        return "", ""
    return "", f"地址已由 /tag/{old} 改为 /tag/{tag.slug}（旧地址会自动跳转）"


def delete_tag_core(tag):
    """删除标签 → 错误文案（成功为 ""）。

    被文章用着就**拒绝**（与后台同行为）：标签是文章的属性，级联清理等于悄悄改文章。
    要合并请用「一键整理」`merge_duplicate_tags`。

    ⚠️ 计数走关联表而不是 `tag.posts`：`Tag.posts` 是 `Post.tags` 的 secondary 反向引用，
    默认 `lazy="select"` 返回**列表** —— `tag.posts.count()` 会抛
    `list.count() takes exactly one argument`（500 而不是 400），`len(tag.posts)` 又能
    把这个标签下的全部文章对象读出来。只有 `Category.posts` 是 `lazy="dynamic"`，
    那里 `.count()` 才对。
    """
    used = PostTag.query.filter_by(tag_id=tag.id).count()
    if used:
        return (f"标签「{tag.name}」正被 {used} 篇文章使用：请先移除文章里的该标签，"
                "或用「一键整理」合并")
    db.session.delete(tag)
    db.session.commit()
    return ""


def create_series_core(form):
    """新建系列 → `(id, "")`；校验不过 → `(None, 错误文案)`。"""
    name = (form.get("name") or "").strip()
    if not name:
        return None, "系列名称不能为空"
    ser = Series(
        name=name, slug=unique_model_slug(Series, name, max_len=100,
                                          explicit=(form.get("slug") or "")),
        description=(form.get("description") or "").strip(),
        cover=(form.get("cover") or "").strip(), sort=_sort_of(form),
    )
    db.session.add(ser)
    db.session.commit()
    return ser.id, ""


def rename_series_core(ser, form):
    """系列编辑 → `(错误文案, slug 变化说明)`。

    与后台原实现一致：`name` 为空则整次拒绝；`description/cover/sort` **给了才改**
    （移动端编辑器载入过全量字段，所以总是会给；后台表单缺字段时保持原值，
    避免「只想改简介却把封面清空」）。

    v5.4.0：**改名不再自动重算 slug**，只有表单显式给了 `slug` 才改地址
    （理由同 `rename_category_core`：换地址会让已发出的链接 404）。
    """
    name = (form.get("name") or "").strip()
    if not name:
        return "系列名称不能为空", ""
    ser.name = name
    note = _apply_slug_change(ser, Series, form.get("slug"), 100, "/series")
    if form.get("description") is not None:
        ser.description = (form.get("description") or "").strip()
    if form.get("cover") is not None:
        ser.cover = (form.get("cover") or "").strip()
    if form.get("sort") is not None:
        ser.sort = _sort_of(form, ser.sort or 0)
    db.session.commit()
    return "", note


def delete_series_core(ser, move_to=None):
    """删除系列 → `(转移篇数, 系列名)`。不给 `move_to` 时与后台原行为一致：文章留着、脱离系列。

    转移是这次**新加的可选路径**（不是改默认行为）：手机端误触成本高，给一条
    不至于让文章失去上下篇导航的去路。`Series.name` 不唯一，所以按 id 定位。
    """
    target = _resolve_target(Series, ser.id, move_to)
    moved = 0
    if target:
        for p in Post.query.filter(Post.series_id == ser.id).all():
            p.series_id = target.id
            moved += 1
        db.session.flush()
    name = ser.name
    db.session.delete(ser)
    db.session.commit()
    return moved, name


def _resolve_target(model, self_id, move_to):
    """把 `move_to` 解析成目标行：必须是数字、不等于自身、且真实存在，否则 None。"""
    try:
        tid = int(move_to)
    except (TypeError, ValueError):
        return None
    if not tid or tid == self_id:
        return None
    return db.session.get(model, tid)


def _apply_slug_change(obj, model, raw_slug, max_len, prefix):
    """显式给了 `raw_slug` 才改地址；空/未给 → 保持原 slug。返回「旧→新」提示。

    v5.4.0 起「改名不再自动换地址」，所有换地址的入口都收敛到这里：
    只有表单里那个可留空的「地址 slug」输入框真的填了东西才动。
    """
    raw = (raw_slug or "").strip()
    if not raw:
        return ""
    old = obj.slug
    obj.slug = unique_model_slug(model, obj.name, exclude_id=obj.id,
                                 max_len=max_len, explicit=raw)
    return _slug_note(prefix, old, obj.slug)


def _slug_note(prefix, old, new):
    """slug 变了的提示文案；没变返回 ""。"""
    if old == new:
        return ""
    return (f"地址已由 {prefix}/{old} 改为 {prefix}/{new}。"
            "旧地址若是中文名或自动拼音会自动跳转；自己改过的历史地址会失效，"
            "请确认没有外部引用")


# ---------------------------------------------------------------- 后台路由


@admin_bp.route("/category/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_category(cid):
    """删除分类（v3.14.0 升级）：可带 move_to=<目标分类 id> 先转移文章再删除，避免文章变无分类。"""
    cat = Category.query.get_or_404(cid)
    moved, name = delete_category_core(cat, request.form.get("move_to") or "")
    log_audit("delete", "category", cid, f"删除分类：{name}（转移 {moved} 篇）",
              user=_current_user_or_none())
    flash("分类已删除" + (f"，{moved} 篇文章已转移到目标分类" if moved else ""))
    return redirect(url_for("admin.categories"))


@admin_bp.route("/tags", methods=["GET", "POST"])
@admin_required
def tags():
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "merge":
            merged = merge_duplicate_tags()
            cleaned = cleanup_orphan_tags()
            flash(f"标签整理完成：合并重复 {merged} 个，清理 0 使用 {cleaned} 个")
            log_audit("merge", "tag", 0, f"合并重复 {merged} + 清理未使用 {cleaned}", user=_current_user_or_none())
            return redirect(url_for("admin.tags"))
        if action == "setslug":
            tid = request.form.get("tid", type=int)
            tag = Tag.query.get_or_404(tid)
            err, note = set_tag_slug_core(tag, request.form.get("slug"))
            if err:
                flash(err)
            else:
                flash(note or f"「{tag.name}」的地址未变：/tag/{tag.slug}")
                log_audit("update", "tag", tid, f"改标签地址：{tag.slug}", user=_current_user_or_none())
            return redirect(url_for("admin.tags"))
        tid, err = create_tag_core(request.form.get("name"), (request.form.get("slug") or ""))
        if err:
            flash(err)
        else:
            flash("标签已添加")
            log_audit("create", "tag", tid, "新建标签", user=_current_user_or_none())
        return redirect(url_for("admin.tags"))
    counts = tag_usage_counts()
    rows = []
    orphan_count = 0
    for t in Tag.query.order_by(Tag.id).all():
        used = counts.get(t.id, 0)
        if used == 0:
            orphan_count += 1
        rows.append((t, used))
    return render_template("admin/tags.html", tags=rows, orphan_count=orphan_count)


@admin_bp.route("/tag/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_tag(tid):
    tag = Tag.query.get_or_404(tid)
    err = delete_tag_core(tag)
    if err:
        flash(err)
        return redirect(url_for("admin.tags"))
    log_audit("delete", "tag", tid, f"删除标签：{tag.name}", user=_current_user_or_none())
    flash("标签已删除")
    return redirect(url_for("admin.tags"))


@admin_bp.route("/series", methods=["GET", "POST"])
@admin_required
def manage_series():
    if request.method == "POST":
        sid, err = create_series_core(request.form)
        if err:
            flash(err)
        else:
            flash("系列已添加")
            log_audit("create", "series", sid, "新建系列", user=_current_user_or_none())
        return redirect(url_for("admin.manage_series"))
    series = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return render_template("admin/series.html", series=series)


@admin_bp.route("/series/<int:sid>/rename", methods=["POST"])
@admin_required
def rename_series(sid):
    """系列编辑（v3.14.0）：改名（slug 自动重算并保持唯一）/简介/封面/排序。"""
    s = Series.query.get_or_404(sid)
    err, note = rename_series_core(s, request.form)
    if err:
        flash(err)
        return redirect(url_for("admin.manage_series"))
    log_audit("rename", "series", sid, f"系列改名：{s.name}；{note}" if note else
              f"系列改名：{s.name}", user=_current_user_or_none())
    flash(f"系列已更新：{s.name}" + (f"（{note}）" if note else ""))
    return redirect(url_for("admin.manage_series"))


@admin_bp.route("/series/<int:sid>/delete", methods=["POST"])
@admin_required
def delete_series(sid):
    s = Series.query.get_or_404(sid)
    moved, name = delete_series_core(s, request.form.get("move_to") or "")
    log_audit("delete", "series", sid, f"删除系列：{name}（转移 {moved} 篇）",
              user=_current_user_or_none())
    flash("系列已删除" + (f"，{moved} 篇文章已并入目标系列" if moved else ""))
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
