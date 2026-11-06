# -*- coding: utf-8 -*-
"""主题中心 API（v3.16.0）。

GET  /api/theme  —— 公开：返回预设主题包列表 + 当前激活 pack_id（供后台主题中心预览用）
POST /api/theme  —— 仅超管：应用预设包（pack_id）或自定义主题（custom JSON），
                   也可单独提交 wallpaper；写 Setting 并审计

安全：POST 必须有登录超管会话 + 全局 CSRF（app 层 POST 统一校验）。自定义主题走
      `themes.normalize_custom_theme()`：**键必须在 token 白名单内、值必须匹配该键的语法**
      （颜色 / 长度 / 数值 / 字体族 / 阴影），缺的键由基准主题补齐，非法键值 400 并回文案。
      这些 token 会被前台逐个 `setProperty` 写进 `:root`，所以「挡住 url() 之类的外联值」
      不是洁癖 —— 那是让每个访客的浏览器替站主去请求第三方地址。
"""
import json

from .common import api_bp, jsonify
from flask import request, session
from models import User, Setting, db
from themes import THEME_PRESETS, PRESET_MAP, current_theme, normalize_custom_theme
# v5.5.0 主题包：纯 JSON 分发单元（含布局/章节配色/动效），与预设包并存。
# 只在这里 import，避免 themes.py ↔ theme_bundles.py 形成包级循环。
import theme_bundles as bundles
# v5.5.0 ②③：站主主题库（自建/导入）与「上一套外观」快照，均存 Setting KV。
import theme_library as library
# v3.25.0：审计写入搬到顶层 `audit.py` 后，本模块**可以正常顶层导入**了 ——
# 原先 `from admin import log_audit` 只能塞进函数里延迟导入，因为
# `admin.ai_summary → api` 构成包级循环，模块顶层导出会直接 ImportError。
from audit import log_audit
import contextlib


# ---------- 壁纸配置（v4.5.0）----------
# 存在 Setting KV 而不建表：壁纸只有「亮/暗各一张 + 遮罩强度 + 开关」几个标量，
# 与项目「能不改表就不改表」的纪律一致。
WALLPAPER_KEY = "home_wallpaper"


def _clamp(v, lo, hi, default):
    """把用户输入夹到 [lo, hi]。非法输入回落 default，不抛错。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _safe_wp_url(v):
    """只接受本站 `/static/uploads/` 下的单层相对文件名，其余一律丢弃。

    ⚠️ 这个限制不是洁癖，有两个真实的攻击面：

    1. 壁纸 URL 会进 inline style 的 `background-image`。允许任意外部 URL，
       等于让每个访客的浏览器替站主向第三方发请求 —— 读者的 IP/UA 就此泄漏；
       `data:` 前缀还能把任意内容塞进样式。
    2. **路径穿越**：只判 `startswith("/static/uploads/")` 是不够的 ——
       `/static/uploads/../../config.py` 同样以该前缀开头。浏览器会把
       `..` 规范化掉，于是请求打到 `/static/config.py`。所以这里额外
       拒绝 `..`，并挡掉 `?`/`#`（否则可拼出 query 绕过命名空间）。
    """
    s = (v or "").strip()
    if ".." in s or "?" in s or "#" in s or "\\" in s:
        return ""
    return s if s.startswith("/static/uploads/") else ""


def _wallpaper():
    """读当前壁纸配置（任何缺失/损坏字段都补默认值，不抛错）。"""
    row = Setting.query.filter_by(key=WALLPAPER_KEY).first()
    try:
        d = json.loads(row.value) if row and row.value else {}
    except (TypeError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    light = _safe_wp_url(d.get("light"))
    dark = _safe_wp_url(d.get("dark"))
    return {
        # enabled 必须同时有一张图，否则前台会渲染出一片纯色空区
        "enabled": bool(d.get("enabled")) and bool(light or dark),
        "light": light,
        "dark": dark,
        "overlay": _clamp(d.get("overlay"), 0.0, 0.8, 0.35),
    }


def wallpaper_uses(filename):
    """该文件是否正被首屏壁纸引用（v4.7.4）。

    v4.7.4 起壁纸**可以直接引用媒体库里已有的图片**（不必每次重新上传），
    于是「媒体库文件」与「首屏壁纸」之间产生了**引用关系** ——
    把正在用的那张删掉，首屏的 `background-image` 就会直接 404。

    媒体库删除文件前需要问一句，所以这个判定放在**壁纸的 owner 模块**里
    （单一真相源），由 `admin/media.py` 调用。

    只认 `/static/uploads/<name>` 形态 —— 与 `_safe_wp_url` 的白名单一致，
    不接受任何站外 URL（站外壁纸不是媒体库的文件，删媒体库删不到它）。
    """
    name = (filename or "").strip()
    if not name:
        return False
    wp = _wallpaper()
    prefix = "/static/uploads/"
    for slot in ("light", "dark"):
        v = wp.get(slot) or ""
        if v.startswith(prefix) and v[len(prefix):] == name:
            return True
    return False


@api_bp.route("/theme", methods=["GET"])
def theme_get():
    # v5.5.0：内置主题包摘要（不含整套 token / CSS，列表响应保持轻量）。
    # 主题包与「预设 / 自定义」互斥：当前激活哪一个由 Setting.theme_bundle_id 决定。
    try:
        from utils import get_setting
        active_id = (get_setting(bundles.ACTIVE_KEY) or "").strip()
    except Exception:  # 无 DB 上下文时按未激活处理，绝不让主题中心 500
        active_id = ""
    return jsonify({
        "presets": THEME_PRESETS,
        "bundles": [bundles.summary(b) for b in bundles.list_bundles()],
        "current": {"pack_id": current_theme()["pack_id"], "bundle_id": active_id},
        "wallpaper": _wallpaper(),
    })


@api_bp.route("/theme", methods=["POST"])
def theme_post():
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    if not user or not user.is_super:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    pack_id = (data.get("pack_id") or "").strip()
    custom = data.get("custom")
    bundle_id = (data.get("bundle_id") or "").strip()
    wallpaper = data.get("wallpaper")   # v4.5.0：可只带 wallpaper（纯壁纸请求）

    # ⚠️ 快照必须在这里拍：下面任何 set_kv 一旦执行，Setting.query 在同一
    # session 里就会读到尚未提交的新值，晚一步拍到的就是「新外观」而非「上一套」。
    old_look = library.capture_look()
    changing = bool(pack_id or custom is not None or bundle_id or wallpaper is not None)

    def set_kv(key, val):
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = val
        else:
            db.session.add(Setting(key=key, value=val))

    # v5.5.0：选预设 / 自定义 ⇒ 退出主题包。必须显式清空，否则前台会继续
    # 按上一份包的 layout 渲染「分章」结构，而颜色已经换成新预设 —— 半新半旧。
    if custom is not None or pack_id:
        set_kv(bundles.ACTIVE_KEY, "")

    bundle_applied = ""
    if bundle_id:
        # 只能引用「内置目录」或「站主主题库」里已通过 schema 校验的包，
        # 不接受客户端在应用请求里直接塞整包内容（新增包走 /api/theme/library）。
        b = bundles.resolve_bundle(bundle_id)
        if not b:
            return jsonify({"error": "unknown bundle_id"}), 400
        set_kv(bundles.ACTIVE_KEY, bundle_id)
        set_kv("theme_pack", "bundle:" + bundle_id)
        set_kv("accent_color", b["tokens"]["light"]["accent"])
        set_kv("theme_tokens", json.dumps(b["tokens"], ensure_ascii=False))
        bundle_applied = bundle_id
        pack_id = ""      # 下面不再走预设分支
        custom = None
    elif custom is not None:
        # 自定义主题：{light:{...}, dark?:{...}} 或单层 {accent:..., ...}
        # v5.4.x 加固：以前只判「light.accent 存不存在」，任意键值都会落库并被前台
        # `setProperty("--"+k, v)` 写进 :root。现在走白名单 + 逐类取值校验，
        # 缺的键由基准主题补齐（避免半套主题），非法键/值直接 400。
        light, dark, errors = normalize_custom_theme(custom)
        if errors:
            return jsonify({"error": "invalid custom theme", "details": errors[:20]}), 400
        set_kv("theme_pack", "custom")
        set_kv("accent_color", light["accent"])
        set_kv("theme_tokens", json.dumps({"light": light, "dark": dark}, ensure_ascii=False))
    elif pack_id in PRESET_MAP:
        p = PRESET_MAP[pack_id]
        set_kv("theme_pack", pack_id)
        set_kv("accent_color", p["light"]["accent"])
        set_kv("theme_tokens", json.dumps({"light": p["light"], "dark": p["dark"]}, ensure_ascii=False))
    elif pack_id or custom is not None:
        # ⚠️ 只有「什么都没传、且带了 wallpaper」才是合法的纯壁纸请求。
        # 走到这里说明既没有可用的 pack_id 也没有 custom —— 必须报错，
        # 不能因为下面有壁纸分支就静默吞掉一个拼错的 pack_id。
        return jsonify({"error": "unknown pack_id"}), 400
    # 走到这里且 pack_id/custom 皆空 = 纯壁纸请求，主题部分原样不动

    if wallpaper is not None:
        if not isinstance(wallpaper, dict):
            return jsonify({"error": "invalid wallpaper"}), 400
        wp = {
            "enabled": bool(wallpaper.get("enabled")),
            "light": _safe_wp_url(wallpaper.get("light")),
            "dark": _safe_wp_url(wallpaper.get("dark")),
            "overlay": _clamp(wallpaper.get("overlay"), 0.0, 0.8, 0.35),
        }
        # 拒绝「打开开关但没图」：那会让首屏变成一片没有任何内容的纯色
        if wp["enabled"] and not (wp["light"] or wp["dark"]):
            return jsonify({"error": "启用壁纸前请先上传至少一张图片"}), 400
        set_kv(WALLPAPER_KEY, json.dumps(wp, ensure_ascii=False))

    if changing:
        library.set_prev(old_look)
    db.session.commit()
    # 审计失败不该让主题应用失败；`log_audit` 自身已全异常静默，这里只是双保险
    with contextlib.suppress(Exception):
        if wallpaper is not None and not pack_id and custom is None and not bundle_applied:
            log_audit("theme", target="设置首页壁纸",
                      detail="启用" if _wallpaper()["enabled"] else "关闭")
        elif bundle_applied:
            log_audit("theme", target="应用主题包", detail=bundle_applied)
        else:
            log_audit("theme", target="应用主题", detail=pack_id or "custom")
    t = current_theme()
    try:
        from utils import get_setting
        active_id = (get_setting(bundles.ACTIVE_KEY) or "").strip()
    except Exception:
        active_id = bundle_applied
    return jsonify({
        "ok": True,
        "pack_id": pack_id or current_theme()["pack_id"],
        "bundle_id": active_id,
        "theme_tokens": t["light"],
        "theme_dark_tokens": t["dark"],
        "wallpaper": _wallpaper(),
        "prev": library.prev_summary(),
    })


# ---------------------------------------------------------------------------
# v5.5.0 ②③：站主主题库 / 主题市场 / 外观回滚
# ---------------------------------------------------------------------------

def _super_user():
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    return user if (user and user.is_super) else None


@api_bp.route("/theme/library", methods=["GET"])
def theme_library_get():
    """超管读取主题市场全量数据：内置包 + 站内自建/导入包 + 回滚目标。"""
    if not _super_user():
        return jsonify({"error": "forbidden"}), 403
    try:
        from utils import get_setting
        active_id = (get_setting(bundles.ACTIVE_KEY) or "").strip()
    except Exception:
        active_id = ""
    items = []
    for it in library.library_data()["items"]:
        s = library.item_summary(it)
        s["bundle"] = it["bundle"]      # 编辑器需要完整包，不是摘要
        items.append(s)
    return jsonify({
        "builtins": bundles.list_bundles(),
        "items": items,
        "active_id": active_id,
        "prev": library.prev_summary(),
        "limits": {
            "max_items": library.MAX_ITEMS,
            "max_item_kb": library.MAX_ITEM_BYTES // 1024,
            "max_total_kb": library.MAX_TOTAL_BYTES // 1024,
        },
    })


@api_bp.route("/theme/library", methods=["POST"])
def theme_library_post():
    """主题库操作（单端点 + action，避免为四个小动作各开一条鉴权/CSRF 分支）。

    ``save`` 站主编辑器保存（信任级别 = 站主本人）、``import`` 第三方导入
    （**强制剥离 CSS**）、``delete`` 删除站内条目、``rollback`` 恢复上一套外观。
    """
    if not _super_user():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip()

    if action == "save":
        overwrite = (data.get("overwrite_id") or "").strip() or None
        item, errors = library.save_item(data.get("bundle"), overwrite_id=overwrite,
                                         origin="own")
        if errors:
            return jsonify({"error": "invalid theme bundle", "details": errors[:20]}), 400
        detail = item["id"]
        payload = {"ok": True, "item": library.item_summary(item),
                   "bundle": item["bundle"]}
    elif action == "import":
        raw = data.get("bundle")
        if raw is None and isinstance(data.get("text"), str):
            try:
                raw = json.loads(data["text"])
            except (TypeError, ValueError):
                return jsonify({"error": "invalid json"}), 400
        item, errors = library.import_item(raw)
        if errors:
            return jsonify({"error": "invalid theme bundle", "details": errors[:20]}), 400
        detail = item["id"] + "（已禁用 CSS）"
        payload = {"ok": True, "item": library.item_summary(item),
                   "bundle": item["bundle"]}
    elif action == "delete":
        iid = (data.get("id") or "").strip()
        ok, errors = library.delete_item(iid)
        if not ok:
            return jsonify({"error": "delete failed", "details": errors}), 400
        detail = iid
        payload = {"ok": True}
    elif action == "rollback":
        label = library.rollback()
        if not label:
            return jsonify({"error": "nothing to rollback"}), 400
        detail = label
        payload = {"ok": True, "label": label}
    else:
        return jsonify({"error": "unknown action"}), 400

    with contextlib.suppress(Exception):
        log_audit("theme", target="主题库/" + action, detail=detail)
    payload["prev"] = library.prev_summary()
    payload["active_id"] = _active_id()
    return jsonify(payload)


def _active_id():
    try:
        from utils import get_setting
        return (get_setting(bundles.ACTIVE_KEY) or "").strip()
    except Exception:
        return ""
