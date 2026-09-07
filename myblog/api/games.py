"""游戏平台公开接口（v3.15.0）。

- GET /api/games                已上架游戏列表（卡片栏目数据）
- GET /api/game/<slug>          单个游戏详情
- GET /api/game-files/<slug>/…  沙箱内游戏静态资源（仅已上架；严格安全响应头）

安全设计（第三方代码跑在浏览器，隔离靠三层）：
1. 仅「已上架 approved」的游戏可被列出/播放；
2. 资源路径防穿越（safe_join + realpath 校验，拒绝 .. / 绝对路径）；
3. 每个文件响应带 CSP sandbox + nosniff + Referrer-Policy + no-store：
   游戏文档运行在 iframe sandbox（无 allow-same-origin，前端再加 sandbox 属性），
   拿不到本站 cookie / 登录态，也读不到父页面；CSP connect-src 'none' 禁外联。
"""
import os

from flask import jsonify, request, current_app, send_file

from .common import api_bp, db
from models import Game

GAMES_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "games")

# 沙箱响应头：覆盖所有 /game-files 输出
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "sandbox allow-scripts; "
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; "
        "connect-src 'none'; object-src 'none'; "
        "font-src 'self' data:; base-uri 'self'; form-action 'none'; "
        "frame-ancestors 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

STATUS_ONLINE = "approved"


def _game_json(g, detail=False):
    d = {
        "slug": g.slug, "title": g.title, "cover": g.cover,
        "entry": g.entry, "author": g.author, "version": g.version,
        "description": g.description or "",
        "updated": (g.updated_at or g.created_at).strftime("%Y-%m-%d"),
    }
    if detail:
        d["size"] = g.size
        d["play_count"] = g.play_count or 0
    return d


def _game_dir(slug):
    return os.path.join(GAMES_ROOT, slug)


@api_bp.route("/games")
def games_list():
    rows = Game.query.filter(Game.status == STATUS_ONLINE) \
        .order_by(Game.approved_at.desc(), Game.created_at.desc()).all()
    return jsonify({"items": [_game_json(g) for g in rows]})


@api_bp.route("/game/<slug>")
def game_detail(slug):
    g = Game.query.filter_by(slug=slug, status=STATUS_ONLINE).first()
    if not g:
        return jsonify({"error": "not found"}), 404
    return jsonify(_game_json(g, detail=True))


@api_bp.route("/game-files/<slug>/<path:fp>")
def game_files(slug, fp):
    g = Game.query.filter_by(slug=slug, status=STATUS_ONLINE).first()
    if not g:
        return "not found", 404
    base = os.path.realpath(_game_dir(slug))
    full = os.path.realpath(os.path.join(base, fp))
    if not (full == base or full.startswith(base + os.sep)):
        return "forbidden", 403
    if not os.path.isfile(full):
        return "not found", 404
    resp = send_file(full, conditional=True, max_age=0)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers[k] = v
    return resp
