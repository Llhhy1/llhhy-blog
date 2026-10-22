"""迁移插件后台路由：/admin/migrate/（仅管理员，CSRF 由全局中间件校验）。

大文件解析在请求内完成（几十 MB 的 WXR 通常 1~3 秒）；**落库放到后台任务**，
原因和备份/LLM 审计一致：图片下载 + 几百篇文章可能跑几分钟，同步跑会长期占住
gunicorn 的并发槽（4 worker × 2 线程 = 8 槽，几个这样的请求就会把站点拖成 502）。
"""
from flask import Blueprint, jsonify, render_template, request, url_for

from admin._helpers import admin_required, _current_user_or_none
from .importer import import_items
from .parsers import ParseError, parse_any
import tasks

MAX_UPLOAD = 64 * 1024 * 1024       # 64MB；再大请在导出端按年份拆分

bp = Blueprint("content_migrate", __name__, url_prefix="/admin/migrate",
               template_folder="templates")


def _opt(name, default=""):
    """取一个导入选项。

    ⚠️ **选项在 query string 里，不在 form 里** —— 前台用原始字节流提交文件
    （见 `_read_upload()` 的说明），body 已经被文件占满，表单字段无处可放，
    所以前台把 `publish` / `preserve_slug` / `download_images` / `source_base`
    全部拼在 URL 的查询串上。

    之前这里读的是 `request.form`，于是三个选项**静默失效**：
    `publish` 永远取默认值、`download_images` 永远为假（旧站图片一张都不下载）、
    `source_base` 永远为空（旧站的相对路径补不出完整地址 → 图片下载必然失败）。
    而且原来的路由测试传的参数**恰好等于默认值**，所以一直是假绿。

    这里 query string 优先，form 作为兜底（万一将来改回 multipart 提交也能用）。
    `request.form_content_type` 为空时**不碰** `request.form`：
    非表单类型的请求里访问 `request.form` 没有意义，还可能触发不必要的解析。
    """
    v = request.args.get(name)
    if v is None and request.mimetype in ("application/x-www-form-urlencoded",
                                          "multipart/form-data"):
        v = request.form.get(name)
    return default if v is None else v


def _read_upload():
    """读上传的原始字节流并强制大小上限。返回 (bytes, filename)。

    ⚠️ 为什么不用 multipart/form-data：全局 CSRF 中间件会先执行
    `request.form.get("csrf_token")`，而解析 multipart 时会立刻套用全局
    `MAX_CONTENT_LENGTH`（5MB）—— 本路由即使随后把上限改成 64MB 也已经晚了，
    大文件会在进入视图前就 413。前台因此以原始字节流提交（Content-Type:
    application/octet-stream），CSRF token 走 `X-CSRF-Token` 头；非表单请求不会
    触发 `request.form` 解析，本函数才有机会设置并执行 64MB 上限。
    """
    request.max_content_length = MAX_UPLOAD
    from werkzeug.exceptions import RequestEntityTooLarge
    try:
        raw = request.get_data(cache=False)
    except RequestEntityTooLarge as e:
        raise ParseError("文件超过 %dMB；请先在导出工具里按年份拆分" % (MAX_UPLOAD // (1024 * 1024))) from e
    if not raw:
        raise ParseError("请求里没有文件内容")
    if len(raw) > MAX_UPLOAD:
        raise ParseError("文件超过 %dMB；请先在导出工具里按年份拆分" % (MAX_UPLOAD // (1024 * 1024)))
    name = (request.args.get("name") or "").strip()[:200]
    return raw, name


@bp.route("/", methods=["GET"])
@admin_required
def index():
    return render_template("content_migrate.html", max_mb=MAX_UPLOAD // (1024 * 1024))


@bp.route("/preview", methods=["POST"])
@admin_required
def preview():
    """只解析并回报统计，不写库。"""
    try:
        result = parse_any(*_read_upload())
    except ParseError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result.summary())


@bp.route("/import", methods=["POST"])
@admin_required
def do_import():
    """解析后交给后台任务落库；返回 task_id 供页面轮询。"""
    try:
        result = parse_any(*_read_upload())
    except ParseError as e:
        return jsonify({"error": str(e)}), 400
    mode = _opt("publish", "source")
    publish = {"source": None, "publish": True, "draft": False}.get(mode)
    user = _current_user_or_none()
    tid, err = tasks.submit(
        "content_migrate", import_items, result,
        publish=publish,
        preserve_slug=_opt("preserve_slug", "1") in ("1", "on", "true"),
        download_images=_opt("download_images", "") in ("1", "on", "true"),
        source_base=_opt("source_base", "").strip()[:500],
        author_id=user.id if user else None,
    )
    if err:
        return jsonify({"error": err}), 409
    return jsonify({"ok": True, "task_id": tid,
                    "poll": url_for("content_migrate.task_status", tid=tid)})


@bp.route("/task/<tid>", methods=["GET"])
@admin_required
def task_status(tid):
    """本插件专用的任务轮询：**带 result**。

    通用的 `/admin/task/<id>` 刻意只回状态、不回 result（其它长任务的 result 可能很大）。
    迁移的 result 就是「新建/跳过/失败/图片」这几个计数与警告，正是页面要展示的东西。
    """
    st = tasks.status(tid)
    if not st or st.get("name") != "content_migrate":
        return jsonify({"state": "unknown", "message": "任务不存在或已过期"}), 404
    return jsonify({k: st.get(k) for k in ("id", "state", "message", "error", "result")})
