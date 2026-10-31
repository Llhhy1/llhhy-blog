# -*- coding: utf-8 -*-
"""媒体资源服务层（v4.14.0）：类型判定 / 魔数校验 / 大小闸门 / 落盘登记 / 分块合并。

## 为什么要单独成模块

上传校验链有三处入口：后台单发 `/admin/upload`、后台分块 `/admin/upload/chunk/*`、
移动端 `/api/mobile/upload`。三份拷贝必然漂移 —— 曾经就是这样：图片白名单在
`admin/_helpers.allowed_file()`，魔数在 `_detect_image_magic()`，大小靠全局
`MAX_CONTENT_LENGTH`，三者在不同文件里，加一种格式要改三处。这个模块把它们收成
**一条函数链**，新格式只改这里。

## 校验顺序（顺序本身就是安全边界，别调换）

1. **后缀**白名单 → 决定 `kind`（image/video）；不在白名单直接拒，不读文件；
2. **单文件大小**按 kind 上限（图片 50MB / 视频 500MB）；
3. **磁盘余量** ≥ 文件大小 + `MEDIA_DISK_RESERVE_BYTES`，否则拒（防打满盘）；
4. **文件头魔数**与后缀**必须互相匹配**（防「.mp4 里塞 HTML」）；
5. 落盘 → 登记 `MediaAsset`。

第 4 步刻意比旧实现更严：旧 `_detect_image_magic(header, ext)` **忽略 ext 参数**，
只判断「是不是某种图片」—— 于是把 PNG 改名成 .jpg 也能过。这里要求「声明的后缀」
与「真实的类型」一致，不一致就拒。

## 视频为什么不做转码

转码要 ffmpeg（服务器上没有，装了也吃 CPU，2 核机器转 500MB 视频会把整站拖死）。
所以只收浏览器能原生播放的容器：mp4/m4v/mov（H.264）与 webm。
代价是 **`.avi`/`.wmv`/`.flv` 这类收不了** —— 这是刻意的，收进来也播不了。
同理，视频时长需要读容器元数据，没有 ffmpeg 就**留空**，绝不为此引入重依赖。
"""
import json
import mimetypes
import os
import re
import shutil
import time
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

# 与 config.ALLOWED_EXTENSIONS / ALLOWED_VIDEO_EXTENSIONS 保持一致；
# 这里再写一份是为了「未配置该键的老 Config 子类」也能工作（测试里常见）。
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
_VIDEO_EXTS = {"mp4", "m4v", "mov", "webm"}

_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_STALE_CHUNK_SECONDS = 24 * 3600


class MediaError(Exception):
    """校验/落盘失败。`status` 直接用作 HTTP 状态码，`message` 直接展示给用户。"""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _cfg(key, default):
    try:
        return current_app.config.get(key, default)
    except RuntimeError:  # 无应用上下文（脚本/测试直接调）
        return default


# ---------------------------------------------------------------- 类型与上限

def ext_of(filename):
    """取小写后缀（不含点）。没有后缀返回空串。"""
    name = (filename or "").strip()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[1].lower()


def kind_of(filename):
    """按后缀判定资源类型，返回 `image` / `video` / `None`（不支持）。"""
    ext = ext_of(filename)
    if ext in _cfg("ALLOWED_EXTENSIONS", _IMAGE_EXTS):
        return "image"
    if ext in _cfg("ALLOWED_VIDEO_EXTENSIONS", _VIDEO_EXTS):
        return "video"
    return None


def max_bytes_for(kind):
    """该类型的单文件上限（字节）。"""
    if kind == "video":
        return int(_cfg("VIDEO_MAX_BYTES", 500 * 1024 * 1024))
    return int(_cfg("IMAGE_MAX_BYTES", 50 * 1024 * 1024))


def human_size(n):
    """字节 → 人类可读。模板里不要自己算，口径要一致。"""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n


# ---------------------------------------------------------------- 魔数校验

def detect_magic(header):
    """从文件头判断真实类型，返回 `(kind, subtype)`；认不出返回 `(None, None)`。

    `header` 至少 16 字节（调用方负责）。subtype 是给「后缀与内容是否一致」比对用的
    规范名：png/jpeg/gif/webp/mp4/webm。
    """
    if not header:
        return None, None
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image", "jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image", "gif"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image", "webp"
    # ISO BMFF（mp4 / m4v / mov）：第 4~8 字节固定是 'ftyp'，前面 4 字节是 box 长度
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video", "mp4"
    # Matroska / WebM 的 EBML 头
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", "webm"
    return None, None


# 后缀 → 允许的规范 subtype（jpeg 的两种后缀都归一到 jpeg；mov/m4v 都落在 mp4 容器）
_EXT_TO_SUBTYPE = {
    "png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp",
    "mp4": "mp4", "m4v": "mp4", "mov": "mp4", "webm": "webm",
}


def validate_magic(header, filename):
    """校验「文件头真实类型」与「声明的后缀」是否一致。

    返回 `(ok, message)`。不一致一律拒 —— 攻击面正是「用无害后缀骗过白名单，
    再靠服务器或浏览器按内容嗅探执行」。
    """
    ext = ext_of(filename)
    expect = _EXT_TO_SUBTYPE.get(ext)
    if not expect:
        return False, "不支持的文件类型"
    real_kind, real_sub = detect_magic(header)
    if real_kind is None:
        return False, "文件内容无法识别为图片或视频，已拒绝"
    if real_sub != expect:
        return False, "文件内容与扩展名不符（声明 .%s，实际是 %s），已拒绝" % (ext, real_sub or "未知")
    return True, ""


# ---------------------------------------------------------------- 磁盘闸门

def check_disk_room(size):
    """剩余空间是否够放下 `size` 并保留 `MEDIA_DISK_RESERVE_BYTES` 余量。

    返回 `(ok, message)`。**这一步在写盘之前**：等到写满再失败，
    数据库已经写不进去了（SQLite 需要空间做 WAL 与回滚日志）。
    """
    try:
        folder = _cfg("UPLOAD_FOLDER", ".")
        free = shutil.disk_usage(folder).free
    except OSError:
        # 取不到磁盘信息不该阻断上传（fail-open），但要留痕
        return True, ""
    reserve = int(_cfg("MEDIA_DISK_RESERVE_BYTES", 2 * 1024 * 1024 * 1024))
    need = int(size or 0) + reserve
    if free < need:
        return False, ("服务器剩余空间不足：需要约 %s（文件 %s + 安全余量 %s），"
                       "当前仅剩 %s。请先清理旧文件或调低上传上限。"
                       % (human_size(need), human_size(size), human_size(reserve), human_size(free)))
    return True, ""


# ---------------------------------------------------------------- 落盘与登记

def safe_disk_name(original):
    """生成落盘文件名：`<unix_ts>-<ascii 化原名>.<ext>`。

    为什么不用 `secure_filename` 的结果直接当名字：它会把中文整段剥掉
    （`旅行照片.png` → `.png`），落盘后无法辨认。这里保留 ASCII 部分、中文丢弃，
    原名完整保留在 `MediaAsset.title` 里给界面看。
    """
    ext = ext_of(original)
    # 先取**原始**文件名的词干再做 ASCII 化：`secure_filename("旅行照片.png")`
    # 会把中文剥掉只剩 "png"，再把 "png" 当词干就会得到 `-png.png` 这种鬼名字。
    stem_src = original.rsplit(".", 1)[0] if "." in (original or "") else (original or "")
    base = secure_filename(stem_src) or ""
    stem = re.sub(r"[^A-Za-z0-9_\-]+", "", base)[:60] or "file"
    return "%d-%s.%s" % (int(time.time()), stem, ext)


def _probe_image_size(path):
    """用 Pillow 读图片宽高；未安装或读不出返回 `(None, None)`。

    Pillow 的 `Image.open()` 是惰性的，只读文件头，不会把 50MB 全解进内存。
    但超大图会触发 `DecompressionBombWarning` 甚至 Error —— 一并吞掉，
    尺寸只是展示信息，不该让上传失败。
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0], im.size[1]
    except Exception:  # noqa: BLE001  可选依赖/坏图，尺寸拿不到就算了
        return None, None


def mime_of(filename, kind):
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed:
        return guessed
    return "video/mp4" if kind == "video" else "image/jpeg"


def register_local(filename, kind, size, user_id=None, title="", folder="",
                   storage="local", url=None, mime=None, width=None, height=None):
    """把已落盘的 `uploads/<filename>` 登记进 `media_asset`；已登记则返回旧行。

    调用方必须**先**完成后缀/大小/磁盘/魔数四道校验 —— 本函数只管登记，
    不再重复校验（避免「校验散在两处」的老问题）。

    `storage` / `url` 用于云存储后端：上传成功且本地副本已删除时，
    `url` 是云端公网地址、`storage` 是 oss/webdav。
    """
    from models import db, MediaAsset

    url = url or ("/static/uploads/" + filename)
    exist = MediaAsset.query.filter_by(filename=filename).first()
    if exist:
        # 同一文件重复登记时只补空字段，不覆盖用户已填的标题/分类
        if not exist.url:
            exist.url = url
        db.session.commit()
        return exist

    # 尺寸优先用调用方传入的（云存储场景：本地副本已删，这里读不到文件）
    if kind == "image" and width is None and height is None:
        width, height = _probe_image_size(os.path.join(_cfg("UPLOAD_FOLDER", "."), filename))
    asset = MediaAsset(
        filename=filename,
        kind=kind,
        source="local",
        storage=storage,
        url=url,
        title=(title or "").strip()[:200],
        folder=(folder or "").strip()[:60],
        mime=mime or mime_of(filename, kind),
        size=int(size or 0),
        width=width,
        height=height,
        is_public=True,
        uploaded_by=user_id,
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def save_single(file_storage, user_id=None, folder=""):
    """处理一次「单请求」上传，返回 `MediaAsset`；失败抛 `MediaError`。

    ⚠️ 只适合 ≤ `UPLOAD_SINGLE_SHOT_MAX`（16MB）的文件。更大的文件必须走分块：
    单请求传 500MB 会撞 gunicorn 的 30s timeout 被 kill，用户看到的是「传一半 502」。
    """
    from flask import current_app as _app

    filename = getattr(file_storage, "filename", "") or ""
    if not filename:
        raise MediaError("没有选择文件")

    kind = kind_of(filename)
    if not kind:
        raise MediaError("只支持图片（png/jpg/jpeg/gif/webp）或视频（mp4/m4v/mov/webm）")

    # 先读文件头做魔数校验（不落盘判断，防后缀伪装）
    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    ok, msg = validate_magic(header, filename)
    if not ok:
        raise MediaError(msg)

    # 大小：优先用 Content-Length 之外的真实长度 —— 通过 seek 到尾端取
    size = _stream_size(file_storage.stream)
    limit = max_bytes_for(kind)
    if size > limit:
        raise MediaError("文件过大：%s 超过 %s 上限（%s）"
                         % (human_size(size), kind, human_size(limit)), 413)
    ok, msg = check_disk_room(size)
    if not ok:
        raise MediaError(msg, 507)

    name = safe_disk_name(filename)
    save_dir = _cfg("UPLOAD_FOLDER", ".")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, name)
    file_storage.stream.seek(0)
    file_storage.save(save_path)

    # 图片保留原有 WebP 优化（视频不碰：视频转码需要 ffmpeg）
    if kind == "image":
        try:
            from app import maybe_convert_webp
            new_path = maybe_convert_webp(save_path)
            if new_path and new_path != save_path:
                name = os.path.basename(new_path)
                save_path = new_path
        except Exception:  # noqa: S110  可选增强路径，失败保持原格式
            _app.logger.debug("WebP 转换跳过：%s", name)

    real_size = os.path.getsize(save_path) if os.path.exists(save_path) else size
    title = os.path.splitext(os.path.basename(filename))[0][:200]
    return _register_published(save_path, name, kind, real_size, user_id, title, folder)


def _register_published(local_path, name, kind, size, user_id, title, folder):
    """落盘 → 送云存储 → 登记。云端失败时**保留本地副本**并回传提示。

    为什么失败不直接抛错：用户的诉求是「把这张图传上去写文章」。云端挂了
    不该让整篇内容卡住 —— 存本地、明确告诉他「云端失败，已存本地」，
    他能继续写；反过来直接 500，他会以为文件丢了。
    """
    storage, url, cloud_error = "local", None, ""
    try:
        from media_storage import backend, publish
        ok, msg = publish(local_path, name, mime_of(name, kind))
        if ok:
            storage = backend()
            url = msg if storage != "local" else None
        else:
            cloud_error = msg
    except Exception as e:  # noqa: BLE001  云存储异常不该阻断上传
        cloud_error = str(e)[:160]

    # 尺寸要在送云之前读 —— 云后端成功后会删掉本地副本
    width = height = None
    if kind == "image":
        width, height = _probe_image_size(local_path)

    asset = register_local(name, kind, size, user_id=user_id, title=title, folder=folder,
                           storage=storage, url=url, width=width, height=height)
    if cloud_error:
        asset.cloud_error = cloud_error
    return asset


def _stream_size(stream):
    """取流长度（不依赖 Content-Length，Werkzeug 的 SpooledTemporaryFile 支持 seek）。"""
    try:
        cur = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(cur)
        return size
    except (OSError, ValueError):
        return 0


# ---------------------------------------------------------------- 分块上传

def chunk_dir(upload_id):
    """校验并返回分块临时目录。`upload_id` 必须是 32 位小写 hex —— 这是路径穿越的唯一入口。"""
    if not _UPLOAD_ID_RE.match(upload_id or ""):
        raise MediaError("上传会话 ID 不合法")
    root = _cfg("UPLOAD_TMP_DIR", os.path.join(_cfg("UPLOAD_FOLDER", "."), "..", "upload_tmp"))
    root = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, upload_id))
    if not path.startswith(root + os.sep):
        raise MediaError("上传会话 ID 不合法")
    return path


def chunk_init(filename, size, user_id=None, folder=""):
    """开一个分块会话，返回 `{upload_id, chunk_size, received}`。

    `size` 一定是**客户端声明**的总大小 —— 它只用于「预先拒绝明显超限的请求」，
    最终仍以合并后的真实字节数为准（`chunk_complete` 会复核）。
    """
    kind = kind_of(filename)
    if not kind:
        raise MediaError("只支持图片（png/jpg/jpeg/gif/webp）或视频（mp4/m4v/mov/webm）")
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise MediaError("文件大小不合法") from None
    if size <= 0:
        raise MediaError("文件大小不合法")
    limit = max_bytes_for(kind)
    if size > limit:
        raise MediaError("文件过大：%s 超过 %s 上限（%s）"
                         % (human_size(size), kind, human_size(limit)), 413)

    ok, msg = check_disk_room(size)
    if not ok:
        raise MediaError(msg, 507)

    cleanup_stale_chunks()
    upload_id = uuid.uuid4().hex
    d = chunk_dir(upload_id)
    meta = {"filename": filename, "size": size, "kind": kind, "user_id": user_id,
            "folder": folder or "", "created": int(time.time())}
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except OSError as e:
        # 目录不可写 / 属主不对 / 磁盘满。
        #
        # 🔴 这里**必须**翻成 MediaError：任何漏出去的异常都会变成 Flask 的 500
        # HTML 错误页，而前端是用 `r.json()` 解析的 —— 用户看到的是
        # 「Unexpected token '<', "<!DOCTYPE "... is not valid JSON」，
        # 完全不知道发生了什么（v5.2.1 线上实测：data/upload_tmp 属主是 root，
        # worker 是 www，>16MB 的视频走分块必炸，图片却正常）。
        shutil.rmtree(d, ignore_errors=True)
        raise MediaError(
            "服务器无法写入上传临时目录（%s）。请检查 %s 的属主与权限是否与运行用户一致"
            % (str(e)[:80], os.path.dirname(d.rstrip("/")) or d), 507) from e
    return {"upload_id": upload_id, "chunk_size": int(_cfg("UPLOAD_CHUNK_SIZE", 8 * 1024 * 1024)),
            "received": 0}


def _read_meta(d):
    path = os.path.join(d, "meta.json")
    if not os.path.isfile(path):
        raise MediaError("上传会话不存在或已过期，请重新选择文件", 410)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise MediaError("上传会话已损坏，请重新选择文件", 410) from None


def chunk_save(upload_id, index, data):
    """写入第 `index` 块（从 0 开始），返回已接收块数。

    校验：会话必须存在；index 必须是 [0, 9999] 的整数；单块不超过 2×chunk_size
    （留出 multipart 边界与客户端按块重试的余量）。
    """
    d = chunk_dir(upload_id)
    meta = _read_meta(d)
    try:
        index = int(index)
    except (TypeError, ValueError):
        raise MediaError("分块序号不合法") from None
    if index < 0 or index > 9999:
        raise MediaError("分块序号不合法")
    chunk_size = int(_cfg("UPLOAD_CHUNK_SIZE", 8 * 1024 * 1024))
    if data is None or len(data) == 0:
        raise MediaError("空分块")
    if len(data) > chunk_size * 2:
        raise MediaError("分块过大（单块上限 %s）" % human_size(chunk_size * 2), 413)

    with open(os.path.join(d, "%05d.part" % index), "wb") as f:
        f.write(data)

    parts = [n for n in os.listdir(d) if n.endswith(".part")]
    return {"received": len(parts), "expected": _expected_parts(meta["size"], chunk_size)}


def _expected_parts(size, chunk_size):
    if not chunk_size:
        return 0
    return (int(size) + chunk_size - 1) // chunk_size


def chunk_complete(upload_id, user_id=None):
    """合并所有分块 → 校验 → 落盘 → 登记，返回 `MediaAsset`。

    三道复核，缺一不可：
    1. **块数齐全**（缺块说明有请求失败，客户端应重试而不是让残缺文件入库）；
    2. **合并后总字节数 == 初始化声明的 size**（防少传/多传）；
    3. **文件头魔数**与后缀一致（分块阶段没读文件头，这里是唯一机会）。
    """
    d = chunk_dir(upload_id)
    meta = _read_meta(d)
    filename = meta.get("filename") or ""
    kind = meta.get("kind") or kind_of(filename)
    if not kind:
        raise MediaError("上传会话类型不合法")

    chunk_size = int(_cfg("UPLOAD_CHUNK_SIZE", 8 * 1024 * 1024))
    expected = _expected_parts(meta["size"], chunk_size)
    parts = sorted(n for n in os.listdir(d) if n.endswith(".part"))
    if len(parts) < expected:
        raise MediaError("分块不完整（已收到 %d/%d），请重试缺失的块" % (len(parts), expected), 409)

    save_dir = _cfg("UPLOAD_FOLDER", ".")
    os.makedirs(save_dir, exist_ok=True)
    name = safe_disk_name(filename)
    final_path = os.path.join(save_dir, name)
    tmp_path = final_path + ".merging"

    total = 0
    with open(tmp_path, "wb") as out:
        for n in parts[:expected]:
            p = os.path.join(d, n)
            with open(p, "rb") as src:
                while True:
                    buf = src.read(1024 * 1024)
                    if not buf:
                        break
                    out.write(buf)
                    total += len(buf)

    try:
        if total != int(meta["size"]):
            raise MediaError("合并后大小不符（收到 %s，声明 %s），请重新上传"
                             % (human_size(total), human_size(meta["size"])), 409)

        with open(tmp_path, "rb") as f:
            header = f.read(16)
        ok, msg = validate_magic(header, filename)
        if not ok:
            raise MediaError(msg)

        os.replace(tmp_path, final_path)
    except Exception:
        # 失败时清掉半成品，绝不留一个「看起来存在但内容不对」的文件
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    asset = _register_published(final_path, name, kind, total,
                                user_id or meta.get("user_id"),
                                os.path.splitext(os.path.basename(filename))[0][:200],
                                meta.get("folder") or "")
    shutil.rmtree(d, ignore_errors=True)
    return asset


def chunk_abort(upload_id):
    """放弃一个会话并删除临时目录。客户端取消/出错时调用，避免垃圾堆积。"""
    d = chunk_dir(upload_id)
    shutil.rmtree(d, ignore_errors=True)
    return True


def cleanup_stale_chunks(max_age=_STALE_CHUNK_SECONDS):
    """清理超过 `max_age` 的残留会话（用户关页面/断网留下的）。

    在每次 `chunk_init` 时顺手调用一次 —— 不需要额外定时任务，
    而且「有人上传」正是最需要空间的时候。
    """
    root = _cfg("UPLOAD_TMP_DIR", "")
    if not root or not os.path.isdir(root):
        return 0
    now = time.time()
    removed = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if not os.path.isdir(p) or not _UPLOAD_ID_RE.match(name):
            continue
        try:
            if now - os.path.getmtime(p) > max_age:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


# ---------------------------------------------------------------- 外链资源

_EMBED_HOSTS = {
    "player.bilibili.com": "video",
    "www.youtube.com": "video",
    "youtube.com": "video",
    "player.vimeo.com": "video",
}


def normalize_embed(url):
    """校验外链嵌入地址，返回 `(url, kind)`；不合法抛 `MediaError`。

    只放行**播放器域名**（不是「任何 http 地址」）：一个任意外链 iframe 等于
    把页面控制权交给第三方，而且 `javascript:` / 内网地址都必须挡在外面。
    """
    from urllib.parse import urlparse

    raw = (url or "").strip()
    if not raw:
        raise MediaError("请填写视频地址")
    p = urlparse(raw)
    if p.scheme not in ("http", "https"):
        raise MediaError("只支持 http/https 地址")
    host = (p.hostname or "").lower()
    if host not in _EMBED_HOSTS:
        raise MediaError("暂只支持 B 站 / YouTube / Vimeo 的播放器地址")
    return raw, _EMBED_HOSTS[host]


def register_embed(url, title="", folder="", user_id=None):
    """登记一条外链视频（不占磁盘）。"""
    from models import db, MediaAsset

    raw, kind = normalize_embed(url)
    exist = MediaAsset.query.filter_by(source="embed", url=raw).first()
    if exist:
        return exist
    asset = MediaAsset(filename="", kind=kind, source="embed", url=raw,
                       title=(title or "")[:200], folder=(folder or "")[:60],
                       mime="text/html", size=0, is_public=True, uploaded_by=user_id)
    db.session.add(asset)
    db.session.commit()
    return asset


# ---------------------------------------------------------------- 磁盘同步

def sync_from_disk():
    """把 `uploads/` 里**尚未登记**的文件补进 `media_asset`，返回新增条数。

    存在的意义：v4.14.0 之前的图片全都没登记过（那时媒体库靠扫目录）。
    升级后如果只认表，老图片会在「媒体库」里集体消失 —— 那是数据事故。
    所以首次进入媒体库时调用一次，把历史文件补齐。幂等，可反复调用。
    """
    folder = _cfg("UPLOAD_FOLDER", ".")
    try:
        names = [n for n in os.listdir(folder) if not n.startswith(".")]
    except OSError:
        return 0

    from models import MediaAsset

    added = 0
    for n in names:
        fp = os.path.join(folder, n)
        if not os.path.isfile(fp):
            continue
        kind = kind_of(n)
        if kind is None:
            continue          # .avif 旁路/杂项文件不登记
        if MediaAsset.query.filter_by(filename=n).first():
            continue
        try:
            register_local(n, kind, os.path.getsize(fp),
                           title=os.path.splitext(n.split("-", 1)[-1])[0][:200])
            added += 1
        except Exception:  # noqa: BLE001  单个坏文件不该阻断整批
            continue
    return added
