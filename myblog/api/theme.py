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


@api_bp.route("/theme", methods=["GET"])
def theme_get():
    return jsonify({
        "presets": THEME_PRESETS,
        "current": {"pack_id": current_theme()["pack_id"]},
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
    else:
        return jsonify({"error": "unknown pack_id"}), 400

    db.session.commit()
    try:
        from admin import log_audit
        log_audit("theme", target="应用主题", detail=pack_id or "custom")
    except Exception:
        pass
    t = current_theme()
    return jsonify({
        "ok": True,
        "pack_id": pack_id or "custom",
        "theme_tokens": t["light"],
        "theme_dark_tokens": t["dark"],
    })
