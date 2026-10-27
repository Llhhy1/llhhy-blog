"""公开相册接口（v5.1.0）：前台「图库」改版后的数据源。

## 与 /api/media 的分工

- `/api/media/list`：**素材视角** —— 所有公开媒体平铺，按类型/分类筛选。
  后台写文章插图、挑封面时用它。
- `/api/albums`：编排视角 —— 相册是「一次旅行 / 一个主题」的集合，
  有封面、标题、日期、说明文字与内部分组。读者浏览用它。

两者都只吐 `is_public` 的资源，过滤都在 **SQL 层**。

## 查询次数

列表页刻意只用 **2 次查询**：相册一次 + 这些相册的条目（join 媒体）一次，
在 Python 里按 album_id 分组截断出预览图。
不用「每个相册各查一次预览」的写法 —— 那是 N+1，相册一多列表页就变慢。

## 已删除媒体的处理

`AlbumItem.media_id` 不设外键（见迁移说明），媒体被删后条目会留下空引用。
这里用 **inner join** `media_asset` —— 空引用在 SQL 层就被过滤掉，
相册其余部分照常显示，不会渲染出一个破图占位。
"""
from flask import jsonify, request

from .common import api_bp
from models import Album, AlbumItem, AlbumSection, MediaAsset, db
from utils import fmt_bj

# 列表页每个相册最多回传几张预览图（对齐参考站卡片下方那条预览图带）
_PREVIEW_MAX = 6
_LIST_SIZE_MAX = 24


def _media_row(m):
    """媒体资源的公开字段。与 /api/media 保持同口径：不吐 filename / uploaded_by / storage。"""
    return {
        "id": m.id,
        "kind": m.kind,
        "source": m.source,
        "url": m.url,
        "title": m.title or "",
        "width": m.width,
        "height": m.height,
        "duration": m.duration,
        "poster": m.poster or "",
    }


def _item_row(item, m):
    return {
        "id": item.id,
        "caption": item.caption or "",
        "sort": item.sort or 0,
        "media": _media_row(m),
    }


def _cover_of(album, first_media):
    """封面：优先用指定的 cover_media_id，没设就退回相册第一张图。

    没指定封面时退回首图，是参考站的行为 —— 新建相册还没挑封面时，
    卡片也不该是空白的。
    """
    if album.cover_media_id:
        m = MediaAsset.query.filter_by(id=album.cover_media_id, is_public=True).first()
        if m:
            return _media_row(m)
    return _media_row(first_media) if first_media else None


@api_bp.route("/albums")
def album_list():
    """分页列出公开相册，按事件日期倒序。

    每项含：封面、标题、日期、地点、张数、预览图（前 6 张）。
    无事件日期的相册排在最后（按创建时间倒序）。
    """
    page = max(1, request.args.get("page", 1, type=int) or 1)
    size = min(_LIST_SIZE_MAX, max(1, request.args.get("size", 12, type=int) or 12))

    q = Album.query.filter(Album.is_public == True)  # noqa: E712  SQL 层过滤
    total = q.count()
    rows = (q.order_by(Album.event_date.desc().nullslast(), Album.created_at.desc())
             .offset((page - 1) * size).limit(size).all())

    ids = [a.id for a in rows]

    # 一次取出这些相册的全部条目（inner join 顺带过滤掉已删除/非公开的媒体）
    pairs = []
    if ids:
        pairs = (db.session.query(AlbumItem, MediaAsset)
                 .join(MediaAsset, AlbumItem.media_id == MediaAsset.id)
                 .filter(AlbumItem.album_id.in_(ids),
                         MediaAsset.is_public == True)  # noqa: E712
                 .order_by(AlbumItem.album_id, AlbumItem.sort, AlbumItem.id)
                 .all())

    grouped = {}
    for item, m in pairs:
        grouped.setdefault(item.album_id, []).append((item, m))

    out = []
    for a in rows:
        items = grouped.get(a.id, [])
        first_media = items[0][1] if items else None
        out.append({
            "id": a.id,
            "slug": a.slug,
            "title": a.title or "",
            "summary": a.summary or "",
            "trip_days": a.trip_days or "",
            "event_date": a.event_date.strftime("%Y-%m-%d") if a.event_date else "",
            "location": a.location or "",
            "count": len(items),
            "cover": _cover_of(a, first_media),
            "preview": [_media_row(m) for _, m in items[:_PREVIEW_MAX]],
            "created_at": fmt_bj(a.created_at, "%Y-%m-%d") if a.created_at else "",
        })

    return jsonify({"items": out, "page": page, "size": size, "total": total})


@api_bp.route("/albums/<slug>")
def album_detail(slug):
    """相册详情：元信息 + 分组（若有）+ 条目（含说明文字）。

    - `sections`：相册内的分组，按 sort 排。没有分组就是空数组。
    - `items`：**未归入任何分组**的条目。分组是可选的 —— 不分组的相册
      全部条目都在这里，前端就是一个扁平照片墙。

    私密相册（is_public=False）返回 404，与「不存在」不区分，避免枚举。
    """
    a = Album.query.filter_by(slug=slug, is_public=True).first()  # noqa: E712
    if not a:
        return jsonify({"error": "not found"}), 404

    pairs = (db.session.query(AlbumItem, MediaAsset)
             .join(MediaAsset, AlbumItem.media_id == MediaAsset.id)
             .filter(AlbumItem.album_id == a.id,
                     MediaAsset.is_public == True)  # noqa: E712
             .order_by(AlbumItem.sort, AlbumItem.id)
             .all())

    sections = (AlbumSection.query.filter_by(album_id=a.id)
                .order_by(AlbumSection.sort, AlbumSection.id).all())
    by_section = {}
    loose = []
    for item, m in pairs:
        if item.section_id:
            by_section.setdefault(item.section_id, []).append(_item_row(item, m))
        else:
            loose.append(_item_row(item, m))

    sec_out = []
    for s in sections:
        sec_out.append({
            "id": s.id,
            "title": s.title or "",
            "summary": s.summary or "",
            "count": len(by_section.get(s.id, [])),
            "items": by_section.get(s.id, []),
        })
    # 指向不存在分组的条目（分组被删了）不该凭空消失 —— 挂回未分组区
    known = {s.id for s in sections}
    for sid, rows in by_section.items():
        if sid not in known:
            loose.extend(rows)

    first_media = pairs[0][1] if pairs else None
    return jsonify({
        "id": a.id,
        "slug": a.slug,
        "title": a.title or "",
        "summary": a.summary or "",
        "trip_days": a.trip_days or "",
        "intro": a.intro or "",
        "tips": a.tips or "",
        "event_date": a.event_date.strftime("%Y-%m-%d") if a.event_date else "",
        "location": a.location or "",
        "count": len(pairs),
        "cover": _cover_of(a, first_media),
        "sections": sec_out,
        "items": loose,
        "created_at": fmt_bj(a.created_at, "%Y-%m-%d") if a.created_at else "",
    })
