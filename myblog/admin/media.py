# -*- coding: utf-8 -*-
# v4.14.0：媒体库从「扫目录」改为「查 media_asset 表 + 磁盘同步」，
# 并新增分块上传（视频 500MB）、归档元数据编辑、云存储后端设置。
from ._helpers import (_current_user_or_none, admin_required, log_audit,
                       login_required, admin_bp)
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_
from models import db, Post, MediaAsset
from utils import fmt_bj
import datetime
import os
import time

import media_service
import media_storage


# ---------------------------------------------------------------- 上传（单发）

@admin_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """单请求上传（图片 ≤50MB / 视频 ≤16MB）。更大文件走 `/admin/upload/chunk/*`。

    校验链全部在 `media_service.save_single()`：后缀白名单 → 魔数 → 大小 → 磁盘余量。
    这里只负责把异常翻译成 HTTP 响应。
    """
    file = request.files.get("file")
    try:
        asset = media_service.save_single(file, user_id=_uid(),
                                          folder=(request.form.get("folder") or "").strip())
    except media_service.MediaError as e:
        return jsonify({"error": e.message}), e.status
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("[media] 上传异常")
        return jsonify({"error": "上传失败：%s" % str(e)[:120]}), 500

    return jsonify({
        "url": asset.url, "id": asset.id, "kind": asset.kind,
        "title": asset.title, "size": asset.size,
        "cloud_error": getattr(asset, "cloud_error", ""),
    })


# ---------------------------------------------------------------- 上传（分块）

@admin_bp.route("/upload/chunk/init", methods=["POST"])
@login_required
def upload_chunk_init():
    """开一个分块会话。前端按返回的 `chunk_size` 切片，逐块 POST。"""
    body = request.get_json(silent=True) or {}
    try:
        info = media_service.chunk_init(body.get("filename"), body.get("size"),
                                        user_id=_uid(),
                                        folder=(body.get("folder") or "").strip())
    except media_service.MediaError as e:
        return jsonify({"error": e.message}), e.status
    return jsonify(info)


@admin_bp.route("/upload/chunk", methods=["POST"])
@login_required
def upload_chunk_part():
    """接收第 N 块。**每块 8MB**，单请求耗时远低于 gunicorn 的 30s timeout。"""
    part = request.files.get("chunk")
    data = part.read() if part else request.get_data()
    try:
        info = media_service.chunk_save(request.form.get("upload_id"),
                                        request.form.get("index"), data)
    except media_service.MediaError as e:
        return jsonify({"error": e.message}), e.status
    return jsonify(info)


@admin_bp.route("/upload/chunk/complete", methods=["POST"])
@login_required
def upload_chunk_complete():
    """合并分块 → 复核大小与魔数 → 落盘/上云 → 登记。"""
    body = request.get_json(silent=True) or request.form
    try:
        asset = media_service.chunk_complete(body.get("upload_id"), user_id=_uid())
    except media_service.MediaError as e:
        return jsonify({"error": e.message}), e.status
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("[media] 分块合并异常")
        return jsonify({"error": "合并失败：%s" % str(e)[:120]}), 500
    return jsonify({"url": asset.url, "id": asset.id, "kind": asset.kind,
                    "title": asset.title, "size": asset.size,
                    "cloud_error": getattr(asset, "cloud_error", "")})


@admin_bp.route("/upload/chunk/abort", methods=["POST"])
@login_required
def upload_chunk_abort():
    """取消上传：删临时目录。前端在用户取消或重试前调用。"""
    body = request.get_json(silent=True) or request.form
    try:
        media_service.chunk_abort(body.get("upload_id"))
    except media_service.MediaError as e:
        return jsonify({"error": e.message}), e.status
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 引用判定

def media_refs_for(name, posts=None):
    """列出**疑似**引用某上传文件的在库文章（封面 / 正文），完整返回、不截断。

    判据与抽出前的 `collect_media` 行内实现逐字一致：
      · 封面：`p.cover` 里出现整个文件名（含时间戳前缀）；
      · 正文：Markdown 里出现**去掉时间戳前缀**后的 `bare` 片段 —— 正文一般写整条
        `/static/uploads/<ts>-<name>`，但历史数据里也有改名后只留 basename 的写法，
        用 `bare` 匹配是「宁可多报」：多报只多一次确认，漏报就是删图后文章图裂。

    抽成独立函数的第二个理由：移动端删除前只要判断**一个**文件有没有被引用，
    不该为这件事付整目录的扫描代价（见 `/api/mobile/media/<name>/delete`）。
    显示用的截断交给调用方，总数请用本函数返回的 `len()` —— 原实现先截断再取
    `len()`，`ref_total` 永远不超过 6，是个「看起来像总数」的假数。
    """
    if posts is None:
        posts = Post.query.filter(Post.in_trash == False).all()  # noqa: E712  (与既有实现一致)
    bare = name.split("-", 1)[-1] if "-" in name else name
    refs = []
    for p in posts:
        kind = ""
        if p.cover and name in p.cover:
            kind = "封面"
        elif bare and (p.content or "").count(bare):
            kind = "正文"
        if kind:
            refs.append({"id": p.id, "title": p.title, "kind": kind})
    return refs


# ---------------------------------------------------------------- 清单

_SYNC_AT = [0.0]          # 上次磁盘同步时间（秒）；节流用，避免每次进页面都扫目录


def collect_media(folder=None, kind=None, q=None):
    """媒体库清单的唯一实现（后台页面 / 移动端 / 主题中心壁纸选择器共用）。

    v4.14.0 改为**查表**：`media_asset` 是元数据真相源，磁盘只负责存字节。
    返回键名与旧实现保持兼容（`name/url/size/ts/time_str/refs/ref_total`），
    额外补 `id/kind/title/folder/storage/is_public/created_str`。

    **磁盘同步节流**：v4.14.0 之前上传的图片没有表记录，首次进页面必须补登记，
    否则它们在媒体库里会「集体消失」。但每次进页面都扫目录没必要，故 60s 内只做一次。
    """
    now = time.time()
    if now - _SYNC_AT[0] > 60:
        try:
            media_service.sync_from_disk()
        except Exception as e:  # noqa: BLE001  同步失败不该让页面打不开
            current_app.logger.warning("[media] 磁盘同步失败：%s", str(e)[:120])
        _SYNC_AT[0] = now

    query = MediaAsset.query.filter(MediaAsset.source == "local")
    if kind in ("image", "video"):
        query = query.filter(MediaAsset.kind == kind)
    if folder:
        query = query.filter(MediaAsset.folder == folder)
    if q:
        like = "%" + q + "%"
        query = query.filter(or_(MediaAsset.title.like(like), MediaAsset.filename.like(like)))

    rows = query.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc()).all()
    posts = Post.query.filter(Post.in_trash == False).all()  # noqa: E712  (与既有实现一致)

    items = []
    for a in rows:
        name = a.filename or ""
        ts = 0
        head = name.split("-", 1)[0]
        if head.isdigit():
            ts = int(head)
        refs = media_refs_for(name, posts) if name else []
        created = a.created_at or (datetime.datetime.utcfromtimestamp(ts) if ts else None)
        items.append({
            # —— 旧键（后台模板 / 移动端 / 主题中心依赖，不要改名）——
            "name": name,
            "url": a.url,
            "size": a.size or 0,
            "ts": ts,
            "time_str": fmt_bj(created, "%Y-%m-%d %H:%M") if created else "",
            "refs": refs[:6],
            "ref_total": len(refs),
            # —— v4.14.0 新增 ——
            "id": a.id,
            "kind": a.kind,
            "title": a.title or "",
            "folder": a.folder or "",
            "storage": a.storage or "local",
            "is_public": bool(a.is_public),
            "width": a.width,
            "height": a.height,
            "duration": a.duration,
            "poster": a.poster or "",
            "mime": a.mime or "",
            "size_str": media_service.human_size(a.size),
        })
    return items


def folders():
    """已用过的归档分类（给筛选下拉与编辑时的候选）。"""
    rows = db.session.query(MediaAsset.folder).filter(
        MediaAsset.folder.isnot(None), MediaAsset.folder != "").distinct().all()
    return sorted({r[0] for r in rows if r[0]})


# ---------------------------------------------------------------- 页面

@admin_bp.route("/media", methods=["GET"])
@admin_required
def media_lib():
    """媒体库：图片 / 视频分栏、归档分类筛选、关键词搜索、元数据编辑。"""
    u = _current_user_or_none()
    kind = (request.args.get("kind") or "").strip()
    folder = (request.args.get("folder") or "").strip()
    q = (request.args.get("q") or "").strip()
    return render_template(
        "admin/media_lib.html",
        items=collect_media(folder=folder or None, kind=kind or None, q=q or None),
        folders=folders(), cur_kind=kind, cur_folder=folder, cur_q=q,
        is_super=bool(u and getattr(u, "is_super", False)),
        storage=media_storage.status(),
        image_max=media_service.human_size(media_service.max_bytes_for("image")),
        video_max=media_service.human_size(media_service.max_bytes_for("video")),
        chunk_size=media_service.human_size(
            current_app.config.get("UPLOAD_CHUNK_SIZE", 8 * 1024 * 1024)),
        single_max=media_service.human_size(
            current_app.config.get("UPLOAD_SINGLE_SHOT_MAX", 16 * 1024 * 1024)),
        # JS 需要的是字节数（用来判断走单发还是分块），不是给用户看的字符串
        single_max_bytes=current_app.config.get("UPLOAD_SINGLE_SHOT_MAX", 16 * 1024 * 1024),
        chunk_bytes=current_app.config.get("UPLOAD_CHUNK_SIZE", 8 * 1024 * 1024),
    )


@admin_bp.route("/media/update", methods=["POST"])
@admin_required
def update_media():
    """编辑归档元数据：标题 / 分类 / 是否公开展示 / 视频封面。"""
    aid = request.form.get("id", type=int)
    a = db.session.get(MediaAsset, aid) if aid else None
    if not a:
        flash("资源不存在")
        return redirect(url_for("admin.media_lib"))
    a.title = (request.form.get("title") or "").strip()[:200]
    a.folder = (request.form.get("folder") or "").strip()[:60]
    a.is_public = request.form.get("is_public") == "1"
    poster = (request.form.get("poster") or "").strip()
    if poster and not (poster.startswith("/static/uploads/") or poster.startswith("https://")):
        flash("封面地址必须是本站 /static/uploads/ 或 https 地址")
        return redirect(url_for("admin.media_lib"))
    a.poster = poster[:800]
    db.session.commit()
    log_audit("update", "media", a.id, "编辑媒体元数据：%s" % (a.title or a.filename),
              user=_current_user_or_none())
    flash("已保存")
    return redirect(url_for("admin.media_lib"))


# ---------------------------------------------------------------- 删除

def delete_media_core(name):
    """删除一个媒体文件 → `(是否成功, 说明)`。路径校验与既有实现逐条一致。

    五道防护：①`basename` 剥掉一切目录成分 ②拒空串 / `.` / `..`
    ③绝对路径必须落在 uploads **那一层内** ④必须是普通文件 ⑤才敢 `os.remove`。
    v4.14.0 追加：同时删掉 `media_asset` 行；云存储后端会尝试删远端对象（尽力而为）。
    """
    safe = os.path.basename((name or "").strip())
    if not safe or safe in (".", ".."):
        return False, "文件名不合法"
    # v4.7.4：壁纸可以直接引用媒体库里的已有图片，于是产生了引用关系 ——
    # 删掉正在当壁纸用的那张，首屏 background-image 会直接 404。
    # 这里拦一道，提示先去主题中心换掉壁纸。
    # ⚠️ 这里**故意 fail-open**：检查挂了不该让管理员完全删不了文件；
    #   误放行的后果只是壁纸裂图（首页退化成纯色底），不是安全问题。
    try:
        from api.theme import wallpaper_uses
        if wallpaper_uses(safe):
            return False, "该图片正被首屏壁纸引用，请先到「主题中心」更换或清除壁纸再删除"
    except Exception as e:  # noqa: BLE001 （检查挂了不该让管理员完全删不了文件）
        current_app.logger.warning("[media] 壁纸引用检查失败，放行删除：%s", str(e)[:120])

    asset = MediaAsset.query.filter_by(filename=safe).first()
    folder = current_app.config["UPLOAD_FOLDER"]
    fp = os.path.join(folder, safe)
    existed = os.path.isfile(fp) and os.path.abspath(fp).startswith(os.path.abspath(folder) + os.sep)
    if existed:
        try:
            os.remove(fp)
        except OSError as e:
            return False, "删除失败：" + str(e)[:120]
    elif not asset:
        return False, "文件不存在"

    if asset:
        storage = asset.storage or "local"
        try:
            media_storage.delete_remote(asset.filename, storage)
        except Exception as e:  # noqa: BLE001  远端删不掉不该阻断本地清理
            current_app.logger.warning("[media] 远端删除失败：%s", str(e)[:120])
        db.session.delete(asset)
        db.session.commit()
    return True, safe


@admin_bp.route("/media/delete", methods=["POST"])
@admin_required
def delete_media():
    """删除媒体库文件：仅管理员；只接受 uploads 目录内的文件名（路径穿越防护用 basename）。"""
    ok, msg = delete_media_core(request.form.get("name"))
    if ok:
        log_audit("delete", "media", None, f"删除媒体文件：{msg}", user=_current_user_or_none())
        flash(f"已删除：{msg}")
    else:
        flash(msg)
    return redirect(url_for("admin.media_lib"))


# ---------------------------------------------------------------- 外链 / 同步 / 云存储

@admin_bp.route("/media/embed", methods=["POST"])
@admin_required
def media_embed():
    """登记一条外链播放器（B 站 / YouTube / Vimeo），不占磁盘。"""
    try:
        asset = media_service.register_embed(
            request.form.get("url"), title=(request.form.get("title") or "").strip(),
            folder=(request.form.get("folder") or "").strip(), user_id=_uid())
    except media_service.MediaError as e:
        flash(e.message)
        return redirect(url_for("admin.media_lib"))
    flash("已登记外链视频")
    log_audit("create", "media", asset.id, "登记外链视频：%s" % asset.url,
              user=_current_user_or_none())
    return redirect(url_for("admin.media_lib"))


@admin_bp.route("/media/sync", methods=["POST"])
@admin_required
def media_sync():
    """手动把 uploads/ 里未登记的文件补进表（升级后第一次进媒体库会自动做一次）。"""
    n = media_service.sync_from_disk()
    flash("已补登记 %d 个文件" % n)
    return redirect(url_for("admin.media_lib"))


_STORAGE_KEYS = (
    "media_backend", "media_oss_bucket", "media_oss_region", "media_oss_endpoint",
    "media_oss_key", "media_oss_public_base", "media_oss_prefix",
    "media_webdav_url", "media_webdav_user", "media_webdav_public_base",
    "media_webdav_prefix",
)
_SECRET_KEYS = ("media_oss_secret", "media_webdav_password")


@admin_bp.route("/media/storage", methods=["POST"])
@admin_required
def media_storage_save():
    """保存云存储后端配置。

    **超管专属**：这里能改的是「文件往哪写」，普通管理员改了等于接管存储。
    密钥走 Fernet 加密后落库；表单里留空 = 保持原值（页面上只显示掩码）。
    """
    u = _current_user_or_none()
    if not (u and getattr(u, "is_super", False)):
        flash("只有超级管理员可以修改存储后端")
        return redirect(url_for("admin.media_lib"))

    from models import Setting
    from backup_settings import encrypt_secret

    if request.form.get("action") == "test":
        ok, msg = media_storage.test_connection()
        flash(("连接成功：" if ok else "连接失败：") + str(msg)[:160])
        return redirect(url_for("admin.media_lib"))

    for k in _STORAGE_KEYS:
        if k in request.form:
            _put_setting(Setting, k, (request.form.get(k) or "").strip()[:500])
    for k in _SECRET_KEYS:
        v = (request.form.get(k) or "").strip()
        if v:                       # 留空 = 不修改
            _put_setting(Setting, k, encrypt_secret(v)[:1000])
    log_audit("update", "settings", None, "修改媒体存储后端为：%s"
              % (request.form.get("media_backend") or "local"), user=u)
    flash("存储配置已保存")
    return redirect(url_for("admin.media_lib"))


def _put_setting(Setting, key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _uid():
    u = _current_user_or_none()
    return getattr(u, "id", None) if u else None
