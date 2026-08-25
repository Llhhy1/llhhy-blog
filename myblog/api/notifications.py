"""
"""


from flask import jsonify, session

from .common import (api_bp, db, Notification, User)

# ---------- 站内通知（A4 评论 @ 通知）----------
@api_bp.route("/notifications")
def notifications():
    """当前登录用户的未读通知数 + 最近通知列表。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"items": [], "unread": 0})
    unread = Notification.query.filter_by(user_id=uid, is_read=False).count()
    rows = (Notification.query.filter_by(user_id=uid)
            .order_by(Notification.created_at.desc()).limit(20).all())
    return jsonify({
        "unread": unread,
        "items": [{
            "id": n.id, "content": n.content, "link": n.link or "",
            "is_read": n.is_read,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
        } for n in rows],
    })


@api_bp.route("/notification/<int:nid>/read", methods=["POST"])
def read_notification(nid):
    """标记单条通知已读。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    n = Notification.query.filter_by(id=nid, user_id=uid).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/notifications/read-all", methods=["POST"])
def read_all_notifications():
    """当前用户全部通知标记已读。"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    Notification.query.filter_by(user_id=uid, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})

