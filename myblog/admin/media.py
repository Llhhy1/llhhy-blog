# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

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


@admin_bp.route("/media", methods=["GET"])
@admin_required
def media_lib():
    """媒体库（v3.14.0）：浏览 / 复用 / 删除 static/uploads 下已上传的图片（仅管理员）。

    按文件名里的时间戳前缀倒序（后上传在前）。每张图标注文件大小、归属类型与
    「疑似引用它的文章」，删除前有明确提醒，避免误删正在使用的封面/插图。
    """
    folder = current_app.config["UPLOAD_FOLDER"]
    items = []
    try:
        names = [n for n in os.listdir(folder) if not n.startswith(".")]
    except OSError:
        names = []
    posts = Post.query.filter(Post.in_trash == False).all()
    for n in names:
        fp = os.path.join(folder, n)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        ts = 0
        head = n.split("-", 1)[0]
        if head.isdigit():
            ts = int(head)
        # 疑似引用判定：封面 URL 含文件名 / 正文 Markdown 含去时间戳后的文件名片段
        bare = n.split("-", 1)[-1] if "-" in n else n
        refs = []
        for p in posts:
            kind = ""
            if p.cover and n in p.cover:
                kind = "封面"
            elif bare and (p.content or "").count(bare):
                kind = "正文"
            if kind:
                refs.append({"id": p.id, "title": p.title, "kind": kind})
            if len(refs) >= 6:
                break
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
    return render_template("admin/media_lib.html", items=items)


@admin_bp.route("/media/delete", methods=["POST"])
@admin_required
def delete_media():
    """删除媒体库文件：仅管理员；只接受 uploads 目录内的文件名（路径穿越防护用 basename）。"""
    name = os.path.basename((request.form.get("name") or "").strip())
    if not name or name in (".", ".."):
        flash("参数不合法")
        return redirect(url_for("admin.media_lib"))
    folder = current_app.config["UPLOAD_FOLDER"]
    fp = os.path.join(folder, name)
    if not os.path.abspath(fp).startswith(os.path.abspath(folder) + os.sep) or not os.path.isfile(fp):
        flash("文件不存在")
        return redirect(url_for("admin.media_lib"))
    try:
        os.remove(fp)
        flash(f"已删除：{name}")
    except OSError as e:
        flash("删除失败：" + str(e)[:120])
    return redirect(url_for("admin.media_lib"))
