"""读者积分勋章接口（v3.21.0 gamification）。

- GET /api/reader/me      当前读者积分与勋章（匿名靠 cookie，登录绑定 user_id）
- GET /api/reader/leaderboard  公开积分排行榜
"""
from flask import request, jsonify

from .common import api_bp, db, _current_user_or_none, rate_limit, client_key
from gamify import (current_reader, reader_summary, leaderboard,
                    READER_COOKIE, READER_COOKIE_MAXAGE)


@api_bp.route("/reader/me")
def reader_me():
    """当前读者积分/勋章。

    ⚠️ 必须限流：`current_reader()` 对**没有 cookie 的请求**会新建一行 Reader 并
    commit（这是它的设计，用于匿名积分）。未鉴权 + 无限流 = 任何人用「每次都不带
    cookie」的 GET 洪水就能无上限往 SQLite 里灌行；本仓库其它匿名写接口
    （如 `/api/stats/visit`）都有 `rate_limit`，这里此前是唯一漏项。
    """
    if not rate_limit(client_key("api_reader_me"), limit=60, window=60):
        return jsonify({"error": "too_many_requests"}), 429
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
    # 未鉴权 + 全表排序（`Reader.points` 无索引），不限流就是一个便宜的放大入口
    if not rate_limit(client_key("api_reader_leaderboard"), limit=30, window=60):
        return jsonify({"error": "too_many_requests"}), 429
    limit = request.args.get("limit", 10, type=int)
    if limit <= 0 or limit > 50:
        limit = 10
    return jsonify({"items": leaderboard(limit)})
