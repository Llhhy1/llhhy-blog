"""
"""


from flask import request, jsonify, session

from .common import (api_bp, db, Guestbook, User, _current_user, _gb, rate_limit, client_key)
import stats  # myblog/stats.py：client_ip / cached_region（留言归属地）

# ---------- 留言墙（C1）----------
@api_bp.route("/guestbook")
def guestbook():
    page = request.args.get("page", 1, type=int)
    pagination = Guestbook.query.order_by(Guestbook.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return jsonify({"items": [_gb(g) for g in pagination.items],
                    "page": pagination.page, "pages": pagination.pages, "total": pagination.total})


@api_bp.route("/guestbook", methods=["POST"])
def post_guestbook():
    if not rate_limit(client_key("api_guestbook"), limit=10, window=60):
        return jsonify({"error": "留言过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    # v3.1.6 可选增强：留言验证码（CAPTCHA_ENABLED=true 时要求通过验证码或直接带验证码文本）
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if captcha_required():
        passed = consume_captcha_pass()  # 一次性票据（先验票再消费）
        if not passed:
            code = (data.get("captcha") or "").strip()
            if not code or not verify_captcha(code):
                return jsonify({"error": "请先完成验证码校验"}), 400
            consume_captcha_pass()  # 直接带文本校验通过后消费票据防重放
    content = (data.get("content") or "").strip()
    u = _current_user()
    author = (u.username if u else (data.get("author") or "").strip())
    if not author or not content:
        return jsonify({"error": "昵称和留言内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"error": "留言最多 500 字"}), 400
    from utils import parse_device
    ip = stats.client_ip()
    g = Guestbook(author=author[:80], content=content, user_id=u.id if u else None,
                  ip=ip, region=stats.cached_region(ip),
                  device=parse_device(request.headers.get("User-Agent", ""))[:120])
    db.session.add(g)
    db.session.commit()
    return jsonify({"ok": True, "guestbook": _gb(g)}), 201


@api_bp.route("/guestbook/<int:gid>/like", methods=["POST"])
def like_guestbook(gid):
    g = Guestbook.query.get_or_404(gid)
    if not rate_limit(client_key("api_gblike:" + str(gid)), limit=20, window=60):
        return jsonify({"likes": g.likes})
    g.likes += 1
    db.session.commit()
    return jsonify({"likes": g.likes})

