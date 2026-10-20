# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import (_current_user_or_none, _detect_image_magic, admin_required, allowed_file,
                       log_audit, login_required, admin_bp)     # 同一蓝图对象
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename
from models import Post
from utils import fmt_bj
import datetime
import os
import time

@admin_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """接收后台上传的图片，保存到 static/uploads，返回可访问的 URL。

    v3.1.6 安全加固：不仅要后缀名在白名单，还须校验文件内容魔数（magic bytes），
    防「伪装成 .png/.jpg 的脚本或 HTML」上传后被访问执行（XSS/钓鱼）。
    """
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "只支持 png/jpg/jpeg/gif/webp 图片"}), 400
    # v3.1.6：读文件头 16 字节做魔数校验（不落盘判断，防后缀伪装）
    header = file.stream.read(16)
    file.stream.seek(0)  # 读完回卷，让 file.save 能从头保存
    if not _detect_image_magic(header, file.filename.rsplit(".", 1)[1].lower()):
        return jsonify({"error": "文件内容与图片格式不符，已拒绝（仅允许真实图片）"}), 400
    filename = secure_filename(file.filename)
    # 用时间戳前缀避免重名覆盖
    filename = f"{int(time.time())}-{filename}"
    save_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    file.save(save_path)
    # 图片优化：体积较大时转 WebP 省流量（Pillow 未装则零依赖降级，保持原格式）
    try:
        from app import maybe_convert_webp
        new_path = maybe_convert_webp(save_path)
        if new_path != save_path:
            filename = os.path.basename(new_path)
    except Exception:
        pass
    url = url_for("static", filename=f"uploads/{filename}")
    return jsonify({"url": url})


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


def collect_media(folder=None):
    """媒体库清单的唯一实现（v4.4.0 抽出，后台页面与 `/api/mobile/media` 共用）。

    返回按上传时间倒序的 dict 列表，键名与既有模板保持一致（`name/url/size/ts/time_str/
    refs/ref_total`），后台模板不用改。

    两个已知代价，写在这里而不是藏在调用方：
      · 一次读全目录，**引用判定是 O(文件数 × 文章数)** 的字符串包含 —— 上传目录大了会慢，
        但引用信息正是「删这张图会不会让文章图裂」的唯一依据，砍掉它就等于没有提醒。
      · 时间取文件名前缀的 unix 秒（上传时 `f"{int(time.time())}-{name}"` 写进去的），
        不是 `st_mtime`：移动/恢复文件不会改变显示顺序，比 mtime 稳。
    """
    folder = folder or current_app.config["UPLOAD_FOLDER"]
    items = []
    try:
        names = [n for n in os.listdir(folder) if not n.startswith(".")]
    except OSError:
        names = []
    posts = Post.query.filter(Post.in_trash == False).all()  # noqa: E712  (与既有实现一致)
    for n in names:
        fp = os.path.join(folder, n)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        if not os.path.isfile(fp):
            continue
        ts = 0
        head = n.split("-", 1)[0]
        if head.isdigit():
            ts = int(head)
        refs = media_refs_for(n, posts)
        items.append({
            "name": n,
            "url": url_for("static", filename="uploads/" + n),
            "size": st.st_size,
            "ts": ts,
            "time_str": fmt_bj(datetime.datetime.utcfromtimestamp(ts), "%Y-%m-%d %H:%M") if ts else "",
            "refs": refs[:6],
            "ref_total": len(refs),
        })
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items


def delete_media_core(name):
    """删除 uploads 里的一个文件 → `(是否成功, 说明)`。路径校验与既有实现逐条一致。

    五道防护：①`basename` 剥掉一切目录成分 ②拒空串 / `.` / `..`
    ③绝对路径必须落在 uploads **那一层内** ④必须是普通文件 ⑤才敢 `os.remove`。
    副作用沿用现状：只删点名的那个文件，`maybe_convert_webp` 生成的同名 `.avif` 旁路
    会留成孤儿（不在本次改动范围内，需要的话另开一条清孤儿文件的维护接口）。
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
    folder = current_app.config["UPLOAD_FOLDER"]
    fp = os.path.join(folder, safe)
    if not os.path.abspath(fp).startswith(os.path.abspath(folder) + os.sep) or not os.path.isfile(fp):
        return False, "文件不存在"
    try:
        os.remove(fp)
    except OSError as e:
        return False, "删除失败：" + str(e)[:120]
    return True, safe


@admin_bp.route("/media", methods=["GET"])
@admin_required
def media_lib():
    """媒体库（v3.14.0）：浏览 / 复用 / 删除 static/uploads 下已上传的图片（仅管理员）。

    按文件名里的时间戳前缀倒序（后上传在前）。每张图标注文件大小、归属类型与
    「疑似引用它的文章」，删除前有明确提醒，避免误删正在使用的封面/插图。
    """
    # v4.7.4：「设为壁纸」是**超管**操作（写壁纸走 /api/theme，那边要求 is_super），
    # 而本页是管理员可进 —— 权限不同，所以按钮只对超管显示，
    # 否则普通管理员点了只会拿到一个 403 白板。
    u = _current_user_or_none()
    return render_template("admin/media_lib.html", items=collect_media(),
                           is_super=bool(u and getattr(u, "is_super", False)))


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
