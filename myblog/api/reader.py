"""读者积分勋章接口（v3.21.0 gamification）。

- GET /api/reader/me      当前读者积分与勋章（匿名靠 cookie，登录绑定 user_id）
- GET /api/reader/leaderboard  公开积分排行榜
"""
from flask import request, jsonify

from .common import api_bp, db, _current_user_or_none
from gamify import (current_reader, reader_summary, leaderboard,
                    READER_COOKIE, READER_COOKIE_MAXAGE)


@api_bp.route("/reader/me")
def reader_me():
    r, is_new = current_reader()
    # 登录用户：绑定 user_id 并同步展示名（仅首次）
    u = _current_user_or_none()
    if u and r.user_id != u.id:
        r.user_id = u.id
        if not r.display_name:
            r.display_name = u.username
        db.session.commit()
    data = reader_summary(r)
    resp = jsonify({"reader": data})
    if is_new:
        resp.set_cookie(READER_COOKIE, r.token, max_age=READER_COOKIE_MAXAGE,
                        httponly=True, samesite="Lax", path="/")
    return resp


@api_bp.route("/reader/leaderboard")
def reader_leaderboard():
    limit = request.args.get("limit", 10, type=int)
    if limit <= 0 or limit > 50:
        limit = 10
    return jsonify({"items": leaderboard(limit)})
