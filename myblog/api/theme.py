# -*- coding: utf-8 -*-
"""主题中心 API（v3.16.0）。

GET  /api/theme  —— 公开：返回预设主题包列表 + 当前激活 pack_id（供前台主题选择器/后台预览用）
POST /api/theme  —— 仅超管：应用预设包（pack_id）或自定义主题（custom JSON）；写 Setting 并审计

安全：POST 必须有登录超管会话 + 全局 CSRF（app 层 POST 统一校验）；自定义主题 JSON 仅接受
      {light:{...}, dark?:{...}} 或单层 token 对象，非法结构直接 400，绝不执行任意代码。
"""
import json

from .common import api_bp, jsonify
from flask import request, session
from models import User, Setting, db
from themes import THEME_PRESETS, PRESET_MAP, current_theme, derive_dark
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
    return jsonify({
        "presets": THEME_PRESETS,
        "current": {"pack_id": current_theme()["pack_id"]},
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
    wallpaper = data.get("wallpaper")   # v4.5.0：可只带 wallpaper（纯壁纸请求）

    def set_kv(key, val):
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = val
        else:
            db.session.add(Setting(key=key, value=val))

    if custom is not None:
        # 自定义主题：接受 {light:{...}, dark?:{...}} 或单层 {accent:..., ...}
        if not isinstance(custom, dict):
            return jsonify({"error": "invalid custom theme"}), 400
        light = custom.get("light") if isinstance(custom.get("light"), dict) else custom
        if not isinstance(light, dict) or not light.get("accent"):
            return jsonify({"error": "custom theme requires light.accent"}), 400
        dark = custom.get("dark") if isinstance(custom.get("dark"), dict) else derive_dark(light)
        set_kv("theme_pack", "custom")
        set_kv("accent_color", str(light.get("accent", "#1a73e8")))
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

    db.session.commit()
    # 审计失败不该让主题应用失败；`log_audit` 自身已全异常静默，这里只是双保险
    with contextlib.suppress(Exception):
        if wallpaper is not None and not pack_id and custom is None:
            log_audit("theme", target="设置首页壁纸",
                      detail="启用" if _wallpaper()["enabled"] else "关闭")
        else:
            log_audit("theme", target="应用主题", detail=pack_id or "custom")
    t = current_theme()
    return jsonify({
        "ok": True,
        "pack_id": pack_id or current_theme()["pack_id"],
        "theme_tokens": t["light"],
        "theme_dark_tokens": t["dark"],
        "wallpaper": _wallpaper(),
    })
