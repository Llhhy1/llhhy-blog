"""联系卡片插件（v3.9.0 demo）。

全栈插件 M0 示例：自带独立数据模型 + 独立 Blueprint + /api/plugins footer 槽位。
与核心零耦合（核心已有 FriendLink / Announcement，故 demo 选独立模型，避免冲突）。

前端渲染约定：App.vue 调 GET /api/plugins，遍历 footer 数组，用结构化 <a> 渲染，
不使用 v-html（防 XSS）。
"""
from flask import Blueprint, jsonify, request, session

from models import db


class PluginContactCard(db.Model):
    __tablename__ = "plugin_contact_card"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), default="")
    text = db.Column(db.String(300), default="")
    link = db.Column(db.String(500), default="")
    link_text = db.Column(db.String(120), default="")
    enabled = db.Column(db.Boolean, default=True)
    sort = db.Column(db.Integer, default=0)


bp = Blueprint("plugin_contact_card", __name__, url_prefix="/api/plugin/contact_card")


def _require_admin():
    """仅管理员/超管可写。未登录 401，权限不足 403。"""
    from models import User
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    u = db.session.get(User, uid)
    if not u or not (getattr(u, "is_super", False) or getattr(u, "is_admin_role", False)):
        return jsonify({"error": "需要管理员权限"}), 403
    return None


def _serialize(c):
    return {
        "id": c.id,
        "title": c.title,
        "text": c.text,
        "link": c.link,
        "link_text": c.link_text,
        "enabled": c.enabled,
    }


@bp.get("/list")
def list_cards():
    """公开：返回已启用的联系卡片（页脚渲染用）。"""
    cards = (PluginContactCard.query.filter_by(enabled=True)
             .order_by(PluginContactCard.sort).all())
    return jsonify([_serialize(c) for c in cards])


@bp.post("/upsert")
def upsert_card():
    r = _require_admin()
    if r:
        return r
    data = request.get_json(silent=True) or {}
    cid = data.get("id")
    c = db.session.get(PluginContactCard, cid) if cid else None
    if c is None:
        c = PluginContactCard()
    c.title = (data.get("title") or "").strip()
    c.text = (data.get("text") or "").strip()
    c.link = (data.get("link") or "").strip()
    c.link_text = (data.get("link_text") or "").strip()
    c.enabled = bool(data.get("enabled", True))
    c.sort = int(data.get("sort") or 0)
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "card": _serialize(c)})


@bp.post("/delete")
def delete_card():
    r = _require_admin()
    if r:
        return r
    data = request.get_json(silent=True) or {}
    c = db.session.get(PluginContactCard, data.get("id")) if data.get("id") else None
    if not c:
        return jsonify({"error": "卡片不存在"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


def _footer_provider():
    cards = (PluginContactCard.query.filter_by(enabled=True)
             .order_by(PluginContactCard.sort).all())
    return [_serialize(c) for c in cards]


def register(app, cfg):
    # 建表（此时已在 create_app 的 app_context 内，幂等）。
    try:
        db.create_all()
    except Exception as e:
        print(f"[contact_card] 建表跳过：{e}")
    app.register_blueprint(bp)
    return {
        "name": "联系卡片",
        "version": "1.0.0",
        "author": "Llhhy",
        "slots": ["footer"],
        "footer_provider": _footer_provider,
    }
