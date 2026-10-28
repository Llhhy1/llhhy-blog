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
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
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
    # 取的是**封面媒体的 id**（cover_media_id），不是相册自己的 id。
    # 写成 a.id 会去查「id 恰好等于相册 id 的那个媒体」—— 相册 id 与媒体 id 是两套
    # 自增序列，除了偶然相等之外一定查不到，列表页就永远显示「无封面」。
    ids = [a.cover_media_id for a in rows if a.cover_media_id]
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

    # 封面只查一次：原本写成「条件里查一次、取值又查一次」，同一行读两遍数据库。
    cover = (MediaAsset.query.filter_by(id=a.cover_media_id).first()
             if a.cover_media_id else None)

    return render_template(
        "admin/album_edit.html",
        album=a,
        sections=sec_rows,
        loose_items=loose,
        event_date=a.event_date.strftime("%Y-%m-%d") if a.event_date else "",
        # 编排页内可直接上传（选片 → 传完自动入册），前端据此判断走单请求还是分块。
        # 与媒体库用同一个配置口径，避免两处阈值不一致。
        single_max_bytes=current_app.config.get("UPLOAD_SINGLE_SHOT_MAX", 16 * 1024 * 1024),
        cover_url=(cover.url if cover else ""),
    )


def _item_json(it, m):
    return {
        "id": it.id,
        "media_id": it.media_id,
        "caption": it.caption or "",
        # 名字只有一份（v5.2.1 起）：这里给的是 media_asset.title 的**真实值**，
        # 空就是空 —— 空着不代表没法显示，前台与后台展示都会回退到文件名。
        # 给「回退后的值」会让用户以为已经起过名，反而不知道自己在改什么。
        "media_title": ((m.title or "").strip() if m else ""),
        "media_filename": ((m.filename or "").strip() if m else ""),
        "media_display": ((m.title or m.filename or "").strip() if m else ""),
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
    """保存相册元信息（标题 / slug / 摘要 / 日期 / 地点 / 公开 / 封面）。

    **两种提交方式共用一个端点**，靠请求类型区分：

    - 编排页其余操作（章节 / 条目 / 排序 / 设封面）都是 fetch，返回 JSON；
    - 「保存相册信息」是传统表单提交，**必须回跳并提示** ——
      否则浏览器会把 JSON 当页面渲染，用户看到一串
      `{"ok":true,"slug":"..."}`，既没有返回入口也不知道成没成
      （v5.1.3 上线后实测踩到）。

    判据用 `request.is_json` 而不是「谁调的」：顺带让无 JS 环境也能保存。
    """
    form_mode = not request.is_json

    def fail(msg, code=400):
        if form_mode:
            flash(msg)
            return redirect(url_for("admin.album_edit", aid=aid))
        return _fail(msg, code)

    a = _album_or_404(aid)
    if not a:
        return fail("相册不存在", 404)
    data = request.get_json(silent=True) or request.form

    title = (data.get("title") or "").strip()
    if not title:
        return fail("标题不能为空")

    slug = (data.get("slug") or "").strip()
    if slug:
        if not _SLUG_RE.match(slug):
            return fail("slug 只能包含中英文、数字、下划线和连字符")
        other = Album.query.filter(Album.slug == slug, Album.id != aid).first()
        if other:
            return fail("slug 已被其他相册占用")
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
            return fail("日期格式应为 YYYY-MM-DD")
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
    if form_mode:
        flash("相册信息已保存")
        return redirect(url_for("admin.album_edit", aid=a.id))
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
    """改条目的**名字** / 所属分组 / 排序。

    ## 为什么名字写进 media_asset.title，而不是 album_item.caption

    v5.2.0 把图注（caption）设计成「相册语境的说明」，与素材标题并存 ——
    实测下来用户不认这个区分：在相册里给照片起了名，回媒体库还是一串
    `1000142174_1_1_7212616`，于是「改一处、另一处不动」又变成两份要维护的数据。

    所以从 v5.2.1 起**名字只有一份**，就存在 `media_asset.title`：
    在这里改 = 改媒体库标题，媒体库卡片、其他相册、前台一起变；
    反过来在媒体库改名，这里与前台也立刻跟着变（回退读取，不是副本）。

    `caption` 列保留（不改表结构），但不再写入 —— 历史值由迁移合并进 title 后清空。
    """
    it = AlbumItem.query.filter_by(id=iid, album_id=aid).first()
    if not it:
        return _fail("条目不存在", 404)
    data = request.get_json(silent=True) or request.form

    # 新字段名是 media_title；旧页面（v5.2.0 的输入框）发的是 caption ——
    # 两者语义已统一，都落到 media_asset.title，避免又分叉成两份。
    key = ("media_title" if "media_title" in data
           else ("caption" if "caption" in data else None))
    if key:
        name = (data.get(key) or "").strip()
        m = MediaAsset.query.filter_by(id=it.media_id).first()
        if m:
            m.title = name[:200]
        it.caption = ""          # 单一数据源：不再留相册私有的副本
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
    album_id = request.args.get("album_id", type=int) or 0
    page = max(1, request.args.get("page", 1, type=int) or 1)
    size = min(60, max(1, request.args.get("size", 24, type=int) or 24))

    # v5.3.0：写文章时「从相册拉素材」—— 加了 album_id 就只返回该相册内的素材，
    # 且**按相册内的编排顺序**（sort）返回，而不是按素材创建时间。
    # 写作者的心智模型是「我在翻某个相册」，不是「我在翻整个媒体库」，
    # 顺序跟着相册走才不会出现「挑了第 3 张，列表里它却在第 20 位」。
    if album_id:
        base = (db.session.query(MediaAsset)
                .join(AlbumItem, AlbumItem.media_id == MediaAsset.id)
                .filter(AlbumItem.album_id == album_id))
        order_by = (AlbumItem.section_id.asc(), AlbumItem.sort.asc(),
                    MediaAsset.id.asc())
        if kind:
            base = base.filter(MediaAsset.kind == kind)
        if q:
            like = "%%%s%%" % q
            base = base.filter(db.or_(MediaAsset.title.like(like),
                                      MediaAsset.filename.like(like)))
        total = base.count()
        rows = base.order_by(*order_by).offset((page - 1) * size).limit(size).all()
    else:
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


@admin_bp.route("/albums/picker-list")
@admin_required
def album_picker_list():
    """v5.3.0：给写文章页的「插入相册卡片」用 —— 返回可选相册列表。

    与 `/admin/albums/media-picker` 是两件事：
      * 前者挑**素材**（往正文插图片/视频）
      * 本接口挑**相册**（往正文插一张「打开相册」的链接卡片）

    **包含私密相册**（is_public 全量返回）—— 后台写作者看得见自己的全部
    相册，卡片是否对读者可见由**渲染侧**按 is_public 决定（见
    `utils/render.py` 的 `_album_card_html`）。若在这里就过滤掉私密相册，
    作者会遇到「我明明有这个相册，插入面板里却没有」的困惑。
    """
    rows = (Album.query.order_by(Album.event_date.desc(), Album.id.desc()).all())
    covers = {}
    ids = [a.cover_media_id for a in rows if a.cover_media_id]
    if ids:
        for m in MediaAsset.query.filter(MediaAsset.id.in_(ids)).all():
            covers[m.id] = m
    return jsonify({"items": [{
        "id": a.id,
        "slug": a.slug,
        "title": a.title or a.slug,
        "summary": (a.summary or "")[:120],
        "is_public": bool(a.is_public),
        "event_date": a.event_date.isoformat() if a.event_date else "",
        "location": a.location or "",
        # 封面：优先相册自己的 cover_media_id，没有就用相册里第一张图
        "cover": (covers[a.cover_media_id].url if a.cover_media_id in covers else ""),
        "count": AlbumItem.query.filter_by(album_id=a.id).count(),
    } for a in rows]})
