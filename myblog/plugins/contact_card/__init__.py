"""联系卡片插件（v3.9.0 demo，覆盖 M0/M2/M3）。

全栈插件示例：
- 自带独立数据模型 + 独立 API 蓝图（/api/plugin/contact_card）+ 独立页面（/plugin/contact_card）。
- footer 槽位（M0）：页脚渲染联系卡片。
- nav 槽位（M2）：前台导航新增「联系」入口（指向插件自有页面）。
- html 槽位（M3）：提供一段富文本徽标，前端须 DOMPurify 消毒后渲染。
- remote_components（M3）：声明一个预构建远程组件（/static/plugins/contact_card/widget.js）。

与核心零耦合（核心已有 FriendLink / Announcement，故 demo 选独立模型，避免冲突）。
前端渲染约定：App.vue 调 GET /api/plugins，遍历 nav/footer/html/remote 数组分别渲染。
"""
from flask import Blueprint, jsonify, request, session, Response

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

# 插件自有页面（独立蓝图，避免与 /api 前缀混淆；GET 不受 CSRF 限制）
page_bp = Blueprint("plugin_contact_card_page", __name__, url_prefix="/plugin/contact_card")


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


@page_bp.get("/")
def contact_page():
    """插件自有页面：列出已启用的联系卡片。"""
    cards = (PluginContactCard.query.filter_by(enabled=True)
             .order_by(PluginContactCard.sort).all())
    items = []
    for c in cards:
        s = _serialize(c)
        link = f'<a href="{s["link"]}" target="_blank" rel="noopener">{s["link_text"] or s["link"]}</a>' if s["link"] else ""
        items.append(f'<li><strong>{s["title"]}</strong>{"： " + s["text"] if s["text"] else ""} {link}</li>')
    html = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>联系 · 插件页</title></head><body style='font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px'>"
        f"<h1>📮 联系卡片</h1><ul>{''.join(items) or '<li>暂无卡片</li>'}</ul>"
        "<p><a href='/'>← 返回首页</a></p></body></html>"
    )
    return Response(html, mimetype="text/html")


def _footer_provider():
    cards = (PluginContactCard.query.filter_by(enabled=True)
             .order_by(PluginContactCard.sort).all())
    return [_serialize(c) for c in cards]


def _nav_provider():
    """M2：前台导航新增「联系」入口（指向插件自有页面）。"""
    return [{"label": "联系", "href": "/plugin/contact_card", "icon": "📮"}]


def _html_provider():
    """M3：富文本徽标（前端须 DOMPurify 消毒后 v-html）。"""
    return '<span class="plugin-contact-badge">📮 联系卡片 v1.0.0</span>'


def register(app, cfg):
    # 建表（此时已在 create_app 的 app_context 内，幂等）。
    try:
        db.create_all()
    except Exception as e:
        print(f"[contact_card] 建表跳过：{e}")
    # 幂等注册：运行时重载（set_plugin_enabled/reload）可能再次调用 register，
    # 蓝图已存在则跳过，避免 Flask 抛出「重复注册」异常。
    if bp.name not in app.blueprints:
        app.register_blueprint(bp)
    if page_bp.name not in app.blueprints:
        app.register_blueprint(page_bp)
    return {
        "name": "联系卡片",
        "version": "1.0.0",
        "author": "Llhhy",
        "description": "页脚展示可配置的联系卡片，并提供独立「联系」页面、导航入口与富文本徽标。",
        "slots": ["footer", "html"],
        "footer_provider": _footer_provider,
        "nav_provider": _nav_provider,
        "html_provider": _html_provider,
        "remote_components": [
            {"name": "contact_card_widget", "url": "/static/plugins/contact_card/widget.js"}
        ],
    }
