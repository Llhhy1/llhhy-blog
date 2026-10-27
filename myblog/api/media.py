"""公开媒体接口（v4.14.0）：前台图库 / 视频集的数据源。

## 只暴露「公开」资源

`is_public=False` 的资源**永不出现**在这个接口里 —— 哪怕知道 id 也查不到。
过滤写在 SQL 层（`.filter(MediaAsset.is_public == True)`），不是取回来再筛：
后者一旦有人加了分页就会算错 `total`，而且容易在未来的重构里漏掉。

## 不返回的东西

- `filename`（磁盘文件名）：对读者没意义，且会暴露上传时间的秒级精度；
- `uploaded_by`（上传者 id）：个人博客的读者不需要知道；
- `storage`（存在本地还是云上）：属于部署细节。

需要这些的是后台，走 `/admin/media`。
"""
from flask import jsonify, request

from .common import api_bp
from models import MediaAsset
from utils import fmt_bj


def _item(a):
    return {
        "id": a.id,
        "kind": a.kind,
        # source=embed 时 url 是播放器地址（B站/YouTube），前台必须用 iframe 而不是 <video>
        "source": a.source,
        "url": a.url,
        "title": a.title or "",
        "folder": a.folder or "",
        "mime": a.mime or "",
        "size": a.size or 0,
        "width": a.width,
        "height": a.height,
        "duration": a.duration,
        "poster": a.poster or "",
        "created_at": fmt_bj(a.created_at, "%Y-%m-%d") if a.created_at else "",
    }


@api_bp.route("/media/list")
def media_list():
    """分页列出公开媒体。`kind`=image/video，`folder`=归档分类，`size` 上限 60。"""
    kind = (request.args.get("kind") or "").strip()
    folder = (request.args.get("folder") or "").strip()
    page = max(1, request.args.get("page", 1, type=int) or 1)
    size = min(60, max(1, request.args.get("size", 24, type=int) or 24))

    q = MediaAsset.query.filter(MediaAsset.is_public == True)  # noqa: E712  SQL 层过滤，非取回再筛
    if kind in ("image", "video"):
        q = q.filter(MediaAsset.kind == kind)
    if folder:
        q = q.filter(MediaAsset.folder == folder)

    total = q.count()
    rows = (q.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
             .offset((page - 1) * size).limit(size).all())
    return jsonify({"total": total, "page": page, "size": size,
                    "items": [_item(a) for a in rows]})


@api_bp.route("/media/folders")
def media_folders():
    """公开资源用到的归档分类（含计数），给前台的分类筛选用。"""
    rows = (MediaAsset.query
            .with_entities(MediaAsset.folder)
            .filter(MediaAsset.is_public == True)  # noqa: E712
            .filter(MediaAsset.folder.isnot(None), MediaAsset.folder != "")
            .all())
    counts = {}
    for (f,) in rows:
        counts[f] = counts.get(f, 0) + 1
    return jsonify([{"folder": k, "count": v}
                    for k, v in sorted(counts.items(), key=lambda x: -x[1])])


@api_bp.route("/media/<int:aid>")
def media_detail(aid):
    """单条公开资源（视频播放页用）。非公开或不存在一律 404，不区分两者。"""
    a = MediaAsset.query.filter_by(id=aid, is_public=True).first()
    if not a:
        return jsonify({"error": "资源不存在"}), 404
    return jsonify(_item(a))
