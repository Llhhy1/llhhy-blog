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
