# -*- coding: utf-8 -*-
"""v5.1.0 相册管理：把已上传的媒体编排成可发布的图文集合。

## 与媒体库的分工

- **媒体库**（`/admin/media`）：管素材 —— 上传、删除、改标题分类、云存储。
- **相册**（本模块）：管编排 —— 哪些素材、按什么顺序、分成几组、每张配什么说明。

相册**不存文件**，只存 `media_id` 引用。所以这里没有上传逻辑，
加照片 = 从 `media_asset` 里挑一条出来建 `AlbumItem`。

## 为什么删除媒体时不级联删相册项

`AlbumItem.media_id` 不设外键（见迁移说明）。后台删掉一张图后，
相册里那条会变成空引用，接口用 inner join 自动跳过，相册其余部分照常显示。
这比「删一张图导致整篇游记少一段」安全得多 —— 也符合项目一贯口径：
**内容不该因为素材的删除而连带消失**。

## 路由形态

页面两个（列表 / 编辑），其余全是 JSON 接口 —— 编排操作（改说明、拖排序、
换分组）用整页表单提交体验很差，也容易丢未保存的编辑。
"""
from ._helpers import (_current_user_or_none, admin_required, log_audit,
                       admin_bp)
from flask import flash, jsonify, redirect, render_template, request, url_for
from _time import utcnow
from models import (Album, AlbumItem, AlbumSection, MediaAsset, db)
from utils import fmt_bj
import datetime
import re

_SLUG_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fa5_-]{1,120}$")


def _uid():
    u = _current_user_or_none()
    return getattr(u, "id", None) if u else None


def _album_or_404(aid):
    return Album.query.filter_by(id=aid).first()


def _ok(**kw):
    kw.setdefault("ok", True)
    return jsonify(kw)


def _fail(msg, code=400):
    return jsonify({"ok": False, "msg": msg}), code


def _unique_slug(base):
    """生成不冲突的 slug：重名就加 -2 / -3 …（与文章 slug 同一口径）。"""
    base = (base or "").strip() or "album"
    if not Album.query.filter_by(slug=base).first():
        return base
    for i in range(2, 999):
        cand = "%s-%d" % (base, i)
        if not Album.query.filter_by(slug=cand).first():
            return cand
    return "%s-%d" % (base, int(datetime.datetime.now().timestamp()))


# ---------------------------------------------------------------- 页面


@admin_bp.route("/albums")
@admin_required
def album_list():
    """相册列表：所有相册（含私密），管理员视角。"""
    rows = Album.query.order_by(Album.event_date.desc().nullslast(),
                                Album.created_at.desc()).all()
    counts = {}
    for aid, n in (db.session.query(AlbumItem.album_id,
                                    db.func.count(AlbumItem.id))
                   .group_by(AlbumItem.album_id).all()):
        counts[aid] = n
    covers = {}
    ids = [a.id for a in rows if a.cover_media_id]
    if ids:
        for m in MediaAsset.query.filter(MediaAsset.id.in_(ids)).all():
            covers[m.id] = m.url
    items = [{
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "summary": a.summary or "",
        "event_date": a.event_date.strftime("%Y-%m-%d") if a.event_date else "",
        "location": a.location or "",
        "is_public": a.is_public,
        "count": counts.get(a.id, 0),
        "cover": covers.get(a.cover_media_id, ""),
        "created_at": fmt_bj(a.created_at, "%Y-%m-%d %H:%M") if a.created_at else "",
    } for a in rows]
    return render_template("admin/album_list.html", albums=items)


@admin_bp.route("/albums/create", methods=["POST"])
@admin_required
def album_create():
    """新建相册：只需要标题，slug 自动生成（编辑页可改）。"""
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("请填写相册标题")
        return redirect(url_for("admin.album_list"))
    a = Album(
        slug=_unique_slug("album-%d" % int(datetime.datetime.now().timestamp())),
        title=title[:200],
        summary=(request.form.get("summary") or "").strip(),
        is_public=request.form.get("is_public") == "1",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    log_audit("create", "album", a.id, "新建相册：%s" % title[:60], user=_uid())
    flash("相册已创建，去添加照片吧")
    return redirect(url_for("admin.album_edit", aid=a.id))


@admin_bp.route("/albums/<int:aid>/edit")
@admin_required
def album_edit(aid):
    """相册编辑页：元信息 + 分组 + 照片编排 + 媒体选择器。"""
    a = _album_or_404(aid)
    if not a:
        flash("相册不存在")
        return redirect(url_for("admin.album_list"))

    items = (db.session.query(AlbumItem, MediaAsset)
             .outerjoin(MediaAsset, AlbumItem.media_id == MediaAsset.id)
             .filter(AlbumItem.album_id == aid)
             .order_by(AlbumItem.sort, AlbumItem.id).all())
    sections = (AlbumSection.query.filter_by(album_id=aid)
                .order_by(AlbumSection.sort, AlbumSection.id).all())

    grouped = []
    loose = []
    for it, m in items:
        row = _item_json(it, m)
        if it.section_id:
            grouped.append((it.section_id, row))
        else:
            loose.append(row)
    sec_rows = []
    for s in sections:
        sec_rows.append({
            "id": s.id,
            "title": s.title or "",
            "summary": s.summary or "",
            "items": [r for sid, r in grouped if sid == s.id],
        })

    return render_template(
        "admin/album_edit.html",
        album=a,
        sections=sec_rows,
        loose_items=loose,
        event_date=a.event_date.strftime("%Y-%m-%d") if a.event_date else "",
        cover_url=(MediaAsset.query.filter_by(id=a.cover_media_id).first().url
                   if a.cover_media_id and
                   MediaAsset.query.filter_by(id=a.cover_media_id).first() else ""),
    )


def _item_json(it, m):
    return {
        "id": it.id,
        "media_id": it.media_id,
        "caption": it.caption or "",
        "section_id": it.section_id,
        "sort": it.sort or 0,
        "url": (m.url if m else ""),
        "kind": (m.kind if m else ""),
        "thumb": (m.url if m and m.kind == "image" else (m.poster if m else "")),
        "missing": m is None,      # 媒体已被删除 → 前端标红提示
    }


# ---------------------------------------------------------------- 元信息


@admin_bp.route("/albums/<int:aid>/update", methods=["POST"])
@admin_required
def album_update(aid):
    """保存相册元信息（标题 / slug / 摘要 / 日期 / 地点 / 公开 / 封面）。"""
    a = _album_or_404(aid)
    if not a:
        return _fail("相册不存在", 404)
    data = request.get_json(silent=True) or request.form

    title = (data.get("title") or "").strip()
    if not title:
        return _fail("标题不能为空")

    slug = (data.get("slug") or "").strip()
    if slug:
        if not _SLUG_RE.match(slug):
            return _fail("slug 只能包含中英文、数字、下划线和连字符")
        other = Album.query.filter(Album.slug == slug, Album.id != aid).first()
        if other:
            return _fail("slug 已被其他相册占用")
        a.slug = slug

    a.title = title[:200]
    a.summary = (data.get("summary") or "").strip()
    # 游记页三块：留空即不渲染对应区块（纯照片相册仍然轻）
    a.trip_days = (data.get("trip_days") or "").strip()[:40]
    a.intro = (data.get("intro") or "").strip()
    a.tips = (data.get("tips") or "").strip()
    a.location = (data.get("location") or "").strip()[:120]
    a.is_public = str(data.get("is_public")) in ("1", "true", "True")

    d = (data.get("event_date") or "").strip()
    if d:
        try:
            a.event_date = datetime.datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            return _fail("日期格式应为 YYYY-MM-DD")
    else:
        a.event_date = None

    cover = data.get("cover_media_id")
    if cover is not None:
        try:
            a.cover_media_id = int(cover) or None
        except (TypeError, ValueError):
            a.cover_media_id = None

    a.updated_at = utcnow()
    db.session.commit()
    log_audit("update", "album", a.id, "编辑相册：%s" % a.title[:60], user=_uid())
    return _ok(slug=a.slug)


@admin_bp.route("/albums/<int:aid>/delete", methods=["POST"])
@admin_required
def album_delete(aid):
    """删除相册：连同分组与条目一起删（**不动 media_asset**，文件保留）。"""
    a = _album_or_404(aid)
    if not a:
        return _fail("相册不存在", 404)
    title = a.title
    AlbumItem.query.filter_by(album_id=aid).delete(synchronize_session=False)
    AlbumSection.query.filter_by(album_id=aid).delete(synchronize_session=False)
    db.session.delete(a)
    db.session.commit()
    log_audit("delete", "album", aid, "删除相册：%s" % title[:60], user=_uid())
    return _ok(msg="已删除（媒体文件保留在媒体库中）")


# ---------------------------------------------------------------- 分组


@admin_bp.route("/albums/<int:aid>/sections", methods=["POST"])
@admin_required
def album_section_create(aid):
    """新建分组。新分组排在当前所有分组之后。"""
    a = _album_or_404(aid)
    if not a:
        return _fail("相册不存在", 404)
    data = request.get_json(silent=True) or request.form
    title = (data.get("title") or "").strip()
    if not title:
        return _fail("分组标题不能为空")
    mx = db.session.query(db.func.max(AlbumSection.sort)).filter(
        AlbumSection.album_id == aid).scalar() or 0
    s = AlbumSection(album_id=aid, title=title[:200],
                     summary=(data.get("summary") or "").strip(),
                     sort=int(mx) + 1)
    db.session.add(s)
    db.session.commit()
    return _ok(id=s.id, title=s.title)


@admin_bp.route("/albums/<int:aid>/sections/<int:sid>", methods=["POST"])
@admin_required
def album_section_update(aid, sid):
    """改分组标题 / 说明 / 排序。"""
    s = AlbumSection.query.filter_by(id=sid, album_id=aid).first()
    if not s:
        return _fail("分组不存在", 404)
    data = request.get_json(silent=True) or request.form
    if "title" in data:
        t = (data.get("title") or "").strip()
        if not t:
            return _fail("分组标题不能为空")
        s.title = t[:200]
    if "summary" in data:
        s.summary = (data.get("summary") or "").strip()
    if "sort" in data:
        try:
            s.sort = int(data.get("sort") or 0)
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return _ok()


@admin_bp.route("/albums/<int:aid>/sections/<int:sid>/delete", methods=["POST"])
@admin_required
def album_section_delete(aid, sid):
    """删除分组：其下条目**不删除**，改挂到「未分组」（与详情接口的兜底一致）。"""
    s = AlbumSection.query.filter_by(id=sid, album_id=aid).first()
    if not s:
        return _fail("分组不存在", 404)
    AlbumItem.query.filter_by(section_id=sid).update(
        {"section_id": None}, synchronize_session=False)
    db.session.delete(s)
    db.session.commit()
    return _ok(msg="分组已删除，其中照片已移到「未分组」")


# ---------------------------------------------------------------- 条目


@admin_bp.route("/albums/<int:aid>/items", methods=["POST"])
@admin_required
def album_item_add(aid):
    """添加条目：从 media_asset 挑一个已上传的媒体进相册。

    `media_ids` 支持批量（媒体选择器里多选一次加进来）。
    同一张图重复添加**允许** —— 同一张照片在相册里出现两次（不同配文）
    是合理需求，接口不去重，由使用者自己把握。
    """
    a = _album_or_404(aid)
    if not a:
        return _fail("相册不存在", 404)
    data = request.get_json(silent=True) or request.form
    raw = data.get("media_ids") or data.get("media_id")
    if isinstance(raw, str):
        ids = [p for p in re.split(r"[,\s]+", raw) if p]
    elif isinstance(raw, list):
        ids = [str(p) for p in raw]
    else:
        ids = []
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return _fail("媒体 id 无效")
    if not ids:
        return _fail("请先选择要添加的照片")

    sec = data.get("section_id")
    try:
        sec = int(sec) if sec not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        sec = None
    if sec and not AlbumSection.query.filter_by(id=sec, album_id=aid).first():
        return _fail("分组不存在")

    mx = db.session.query(db.func.max(AlbumItem.sort)).filter(
        AlbumItem.album_id == aid).scalar() or 0
    added = []
    for i, mid in enumerate(ids):
        m = MediaAsset.query.filter_by(id=mid).first()
        if not m:
            continue
        it = AlbumItem(album_id=aid, section_id=sec, media_id=mid,
                       caption="", sort=int(mx) + i + 1)
        db.session.add(it)
        added.append(it)
    if not added:
        return _fail("所选媒体都不存在")
    db.session.commit()
    log_audit("update", "album", aid, "相册添加 %d 张" % len(added), user=_uid())
    return _ok(count=len(added))


@admin_bp.route("/albums/<int:aid>/items/<int:iid>", methods=["POST"])
@admin_required
def album_item_update(aid, iid):
    """改条目的说明文字 / 所属分组 / 排序。"""
    it = AlbumItem.query.filter_by(id=iid, album_id=aid).first()
    if not it:
        return _fail("条目不存在", 404)
    data = request.get_json(silent=True) or request.form
    if "caption" in data:
        it.caption = (data.get("caption") or "").strip()
    if "section_id" in data:
        sec = data.get("section_id")
        try:
            sec = int(sec) if sec not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            sec = None
        if sec and not AlbumSection.query.filter_by(id=sec, album_id=aid).first():
            return _fail("分组不存在")
        it.section_id = sec
    if "sort" in data:
        try:
            it.sort = int(data.get("sort") or 0)
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return _ok()


@admin_bp.route("/albums/<int:aid>/items/<int:iid>/delete", methods=["POST"])
@admin_required
def album_item_delete(aid, iid):
    """从相册移除条目（**不删媒体文件**，素材仍在媒体库里）。"""
    it = AlbumItem.query.filter_by(id=iid, album_id=aid).first()
    if not it:
        return _fail("条目不存在", 404)
    db.session.delete(it)
    db.session.commit()
    return _ok()


@admin_bp.route("/albums/<int:aid>/items/sort", methods=["POST"])
@admin_required
def album_item_sort(aid):
    """批量重排：`ids` 按最终顺序给出，从 1 开始重编号。"""
    data = request.get_json(silent=True) or request.form
    ids = data.get("ids") or []
    if isinstance(ids, str):
        ids = [p for p in re.split(r"[,\s]+", ids) if p]
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return _fail("id 列表无效")
    for idx, iid in enumerate(ids):
        it = AlbumItem.query.filter_by(id=iid, album_id=aid).first()
        if it:
            it.sort = idx + 1
    db.session.commit()
    return _ok(count=len(ids))


# ---------------------------------------------------------------- 媒体选择器数据源


@admin_bp.route("/albums/media-picker")
@admin_required
def album_media_picker():
    """给编辑页的「添加照片」弹层用：分页返回媒体库素材。

    与 `/admin/media` 页面同源（都是 media_asset 表），只是输出 JSON。
    支持 `kind` 与 `q`（标题/文件名模糊）筛选。
    """
    kind = (request.args.get("kind") or "").strip()
    q = (request.args.get("q") or "").strip()
    page = max(1, request.args.get("page", 1, type=int) or 1)
    size = min(60, max(1, request.args.get("size", 24, type=int) or 24))

    query = MediaAsset.query
    if kind:
        query = query.filter_by(kind=kind)
    if q:
        like = "%%%s%%" % q
        query = query.filter(db.or_(MediaAsset.title.like(like),
                                    MediaAsset.filename.like(like)))
    total = query.count()
    rows = (query.order_by(MediaAsset.created_at.desc())
            .offset((page - 1) * size).limit(size).all())
    return jsonify({
        "items": [{
            "id": m.id,
            "url": m.url,
            "thumb": m.url if m.kind == "image" else (m.poster or ""),
            "kind": m.kind,
            "title": m.title or "",
            "created_at": fmt_bj(m.created_at, "%Y-%m-%d") if m.created_at else "",
        } for m in rows],
        "page": page, "size": size, "total": total,
    })
