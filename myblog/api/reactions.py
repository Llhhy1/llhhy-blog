# -*- coding: utf-8 -*-
"""v3.17.3：评论表情回应（👍 ❤️ 😂 🎉 🤔 👏）。

v3.24.0 存储改造（Setting 治理）：
- **旧**：计数存 Setting KV（键 `react_<comment_id>`）——把 UGC 当设置存，随评论数
  无限增长，且被 6 处 `Setting.query.all()` 全表加载一起拖出来。
- **新**：存**评论自己的行**上的 `Comment.reactions`（JSON `{"👍": 3}`）。
  评论本来就有一行，UGC 归到自己的行即可，**不需要新表**，也天然保持
  「每条评论独立、并发回应不同评论互不干扰」这一原有优点（无需整表 JSON 读改写）。

其余行为不变：
- GET 支持批量 `ids=1,2,3`（上限 300），避免前端 N+1 请求。
- POST 有 IP 限流（40 次/分钟）；仅允许对「已审核」评论回应；匿名可用（与评论一致）。
"""
import json

from flask import request, jsonify

from .common import api_bp
from models import db, Comment, visible_posts_query
from utils import rate_limit, client_key

ALLOWED = ["\U0001F44D", "\u2764\uFE0F", "\U0001F602", "\U0001F389", "\U0001F914", "\U0001F44F"]
_MAX_PER_EMOJI = 9999


def _readable_comment(cid):
    """取评论并校验其所属文章**当前可见**。

    R114 审计：`/api/comments/reactions` 允许按 cid 批量回读表情计数，
    而这里此前只按 `Comment.id` 取——于是私密/未发布/回收站文章的评论
    也能被打表情、被读出计数，成了「该文章（及其评论）存在」的存在性侧信道。
    可见性统一由 `visible_posts_query()` 判定。
    """
    c = db.session.get(Comment, cid)
    if not c:
        return None
    try:
        post_id = c.post_id
    except AttributeError:
        return None
    if post_id is None:
        return None
    if not visible_posts_query().filter_by(id=post_id).first():
        return None
    return c


def _load(cid):
    """读取某条评论的表情计数（坏数据一律当空，不让前端炸）。"""
    c = _readable_comment(cid)
    if not c or not c.reactions:
        return {}
    try:
        data = json.loads(c.reactions)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(cid, counts):
    """写回某条评论的表情计数。"""
    c = _readable_comment(cid)
    if not c:
        return
    c.reactions = json.dumps(counts, ensure_ascii=False)
    db.session.commit()


@api_bp.route("/comments/reactions")
def comment_reactions_get():
    raw = (request.args.get("ids") or "").strip()
    cids = [int(x) for x in raw.split(",") if x.strip().isdigit()][:300]
    items = {}
    if cids:
        rows = Comment.query.filter(Comment.id.in_(cids)).all()
        mp = {c.id: c.reactions for c in rows}
        for c in cids:
            v = mp.get(c) or ""
            try:
                items[str(c)] = json.loads(v) if v else {}
            except Exception:
                items[str(c)] = {}
    return jsonify({"allowed": ALLOWED, "items": items})


@api_bp.route("/comments/<int:cid>/reactions", methods=["POST"])
def comment_reactions_post(cid):
    # 限流：同一 IP 60 秒内最多 40 次表情操作（防刷）
    if not rate_limit(client_key("api_react"), limit=40, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    c = db.session.get(Comment, cid)
    if not c or not getattr(c, "approved", True):
        return jsonify({"error": "评论不存在"}), 404
    data = request.get_json(silent=True) or {}
    emoji = (data.get("emoji") or "").strip()
    action = (data.get("action") or "add").strip()
    if emoji not in ALLOWED:
        return jsonify({"error": "不支持的表情"}), 400
    counts = _load(cid)
    n = int(counts.get(emoji, 0) or 0)
    if action == "remove":
        n = max(0, n - 1)
    else:
        n = min(_MAX_PER_EMOJI, n + 1)
    if n > 0:
        counts[emoji] = n
    else:
        counts.pop(emoji, None)
    _save(cid, counts)
    return jsonify({"ok": True, "counts": counts})
