# -*- coding: utf-8 -*-
"""v3.17.3：评论表情回应（👍 ❤️ 😂 🎉 🤔 👏）。

设计（**不改表结构**，符合项目「能不改表就不改」纪律）：
- 计数存 Setting KV（键 ``react_<comment_id>``，值为 JSON ``{"👍": 3}``）——
  与 v3.17.0 的 ``ai_summary_<id>`` 同一模式，零迁移。
- 每条评论一个独立 key：并发回应不同评论互不干扰，避免「整表 JSON 读-改-写」竞态。
- GET 支持批量 ``ids=1,2,3``（上限 300），避免前端 N+1 请求。
- POST 有 IP 限流（40 次/分钟）；仅允许对「已审核」评论回应；匿名可用（与评论一致）。
"""
import json

from flask import request, jsonify

from .common import api_bp
from models import db, Comment, Setting
from utils import rate_limit, client_key

ALLOWED = ["\U0001F44D", "\u2764\uFE0F", "\U0001F602", "\U0001F389", "\U0001F914", "\U0001F44F"]
_MAX_PER_EMOJI = 9999


def _key(cid):
    return "react_%d" % cid


def _load(cid):
    row = Setting.query.filter_by(key=_key(cid)).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(cid, counts):
    val = json.dumps(counts, ensure_ascii=False)
    row = Setting.query.filter_by(key=_key(cid)).first()
    if row:
        row.value = val
    else:
        db.session.add(Setting(key=_key(cid), value=val))
    db.session.commit()


@api_bp.route("/comments/reactions")
def comment_reactions_get():
    raw = (request.args.get("ids") or "").strip()
    cids = [int(x) for x in raw.split(",") if x.strip().isdigit()][:300]
    items = {}
    if cids:
        rows = Setting.query.filter(Setting.key.in_([_key(c) for c in cids])).all()
        mp = {r.key: r.value for r in rows}
        for c in cids:
            v = mp.get(_key(c)) or ""
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
