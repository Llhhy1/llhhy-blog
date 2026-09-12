"""
"""


from flask import request, jsonify

from .common import (api_bp, rate_limit, client_key, Post)
import stats  # 顶层 stats 模块（myblog/stats.py）：record_visit / record_search / record_read / compute_summary / compute_trend / client_ip
import datetime
import urllib.parse
from sqlalchemy import func
from models import db, VisitLog, Setting
from _time import utcnow

# ---------- 访问统计（埋点 + 汇总）----------
@api_bp.route("/stats/visit", methods=["POST"])
def stats_visit():
    """前端每次路由变化时上报一次访问（fire-and-forget）。
    全量审计加固：加限流防脚本刷库；超限静默丢弃，不影响正常访客。"""
    if not rate_limit(client_key("api_stats_visit"), limit=60, window=60):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "")[:255]
    if path.startswith("/admin"):
        return jsonify({"ok": True, "skipped": True})
    # v3.17.3：来源上报（前端传 document.referrer，后端只保留 origin 存库）
    referrer = (data.get("referrer") or "")[:500]
    post_id = data.get("post_id")
    if post_id is not None:
        try:
            post_id = int(post_id)
        except (TypeError, ValueError):
            post_id = None
    stats.record_visit(path, post_id, referrer)
    return jsonify({"ok": True})


@api_bp.route("/stats/search", methods=["POST"])
def stats_search():
    """记录搜索词。全量审计加固：120 次/小时 限流防刷库。"""
    if not rate_limit(client_key("api_stats_search"), limit=120, window=3600):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    stats.record_search(data.get("keyword") or "")
    return jsonify({"ok": True})


@api_bp.route("/stats/read", methods=["POST"])
def stats_read():
    """记录一次文章阅读（同一访客重复读会累加）。全量审计加固：60 次/分钟 限流防刷库。"""
    if not rate_limit(client_key("api_stats_read"), limit=60, window=60):
        return jsonify({"ok": True, "skipped": True})
    data = request.get_json(silent=True) or {}
    slug = (data.get("slug") or "").strip()
    p = Post.query.filter_by(slug=slug).first() if slug else None
    if p:
        stats.record_read(p.id, stats.client_ip())
    return jsonify({"ok": True})


@api_bp.route("/stats/referrers")
def stats_referrers():
    """v3.17.3：访客来源 TOP（referrer origin 聚合；排除 bot 与本站自引用）。公开只读。"""
    days = request.args.get("days", type=int) or 30
    days = max(1, min(365, days))
    since = (utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    # 本站 origin 集合（site_url 设置 + 当前请求 host），来源命中即视为自引用，不进榜
    hosts = set()
    try:
        su = Setting.query.filter_by(key="site_url").first()
        if su and su.value:
            hosts.add(urllib.parse.urlsplit(su.value).netloc.lower())
    except Exception:
        pass
    try:
        hosts.add((request.host or "").lower())
    except Exception:
        pass
    hosts.discard("")

    rows = (db.session.query(VisitLog.referrer, func.count(VisitLog.id))
            .filter(VisitLog.date >= since, VisitLog.is_bot.is_(False), VisitLog.referrer != "")
            .group_by(VisitLog.referrer)
            .order_by(func.count(VisitLog.id).desc()).limit(50).all())
    items = []
    for ref, n in rows:
        try:
            netloc = urllib.parse.urlsplit(ref).netloc.lower()
        except Exception:
            netloc = ""
        if not netloc or netloc in hosts:
            continue
        items.append({"source": ref, "count": n})
        if len(items) >= 10:
            break
    try:
        direct = (db.session.query(func.count(VisitLog.id))
                  .filter(VisitLog.date >= since, VisitLog.is_bot.is_(False), VisitLog.referrer == "")
                  .scalar() or 0)
    except Exception:
        direct = 0
    return jsonify({"days": days, "direct": direct, "items": items})


@api_bp.route("/stats/summary")
def stats_summary():
    """统计汇总（累计访问 / 区域排行 / 热读文章 / 常搜词 / 时段分布 / 访客趋势）。"""
    return jsonify(stats.compute_summary())


@api_bp.route("/stats/dashboard")
def stats_dashboard():
    """运营驾驶舱聚合（UI清单 B · P0）：核心指标 + 环比 + 区间趋势。只读、限流、降级。

    支持 ?range= 查询参数（7 / 30 / 90 天，默认 30），仅改变趋势序列区间，
    不影响卡片指标（卡片恒为「今日」快照 + vs 昨日 / vs 上周同期环比）。
    """
    if not rate_limit(client_key("api_stats_dashboard"), limit=30, window=60):
        return jsonify({"error": "too_many_requests"}), 429
    try:
        range_days = request.args.get("range", 30, type=int)
        if range_days not in (7, 30, 90):
            range_days = 30
        return jsonify(stats.compute_dashboard(range_days=range_days))
    except Exception as e:
        return jsonify({"error": "dashboard_failed", "detail": str(e)}), 500


@api_bp.route("/stats/trend")
def stats_trend():
    """访客趋势（v3.0.0 功能9）：最近 N 天 PV/UV，供访客趋势图使用。"""
    days = request.args.get("days", 30, type=int)
    if days <= 0 or days > 90:
        days = 30
    return jsonify({"trend": stats.compute_trend(days)})

