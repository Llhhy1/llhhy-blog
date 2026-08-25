"""
"""

import re as _re
import secrets as _sec
from flask import request, jsonify

from .common import (api_bp, db, Subscriber, rate_limit, client_key)

# ---------- 邮件订阅 / 退订（Newsletter，C3）----------
@api_bp.route("/subscribe", methods=["POST"])
def subscribe():
    if not rate_limit(client_key("api_subscribe"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    import re as _re
    if not email or not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "邮箱格式不正确"}), 400
    import secrets as _sec
    sub = Subscriber.query.filter_by(email=email).first()
    if sub:
        if not sub.unsub_token:  # 旧数据补 token
            sub.unsub_token = _sec.token_hex(16)
            db.session.commit()
        return jsonify({"ok": True, "message": "你已经订阅过啦"})
    sub = Subscriber(email=email[:160], unsub_token=_sec.token_hex(16))
    db.session.add(sub)
    db.session.commit()
    return jsonify({"ok": True, "message": "订阅成功，新文章发布时会邮件通知你"}), 201


@api_bp.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    """邮件退订：凭邮箱 + 退订令牌取消订阅（无需登录）。
    用法：/api/unsubscribe?email=xxx&token=yyy，GET 返回状态，POST 执行退订。
    安全：统一错误信息避免邮箱枚举；POST 退订按 IP 限流。
    """
    email = (request.args.get("email") or "").strip().lower()
    token = (request.args.get("token") or "").strip()
    if not email or not token:
        return jsonify({"error": "退订链接不完整"}), 400
    sub = Subscriber.query.filter_by(email=email).first()
    import hmac
    # 统一错误信息（无论邮箱不存在还是 token 错误都返回同样提示，避免枚举有效邮箱）
    valid = bool(sub and sub.unsub_token and hmac.compare_digest(token, sub.unsub_token))
    if not valid:
        return jsonify({"error": "退订链接无效或已失效"}), 404
    if request.method == "POST":
        if not rate_limit(client_key("api_unsub"), limit=10, window=60):
            return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
        sub.active = False
        db.session.commit()
        return jsonify({"ok": True, "message": "已退订，不再发送新文章邮件"})
    return jsonify({"ok": True, "email": email, "active": sub.active,
                    "message": "确认退订？请用 POST 请求确认"})

