"""
"""


from flask import request, jsonify

from .common import (api_bp, rate_limit, client_key, Post)
import stats  # 顶层 stats 模块（myblog/stats.py）：record_visit / record_search / record_read / compute_summary / compute_trend / client_ip

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
    post_id = data.get("post_id")
    if post_id is not None:
        try:
            post_id = int(post_id)
        except (TypeError, ValueError):
            post_id = None
    stats.record_visit(path, post_id)
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


@api_bp.route("/stats/summary")
def stats_summary():
    """统计汇总（累计访问 / 区域排行 / 热读文章 / 常搜词 / 时段分布 / 访客趋势）。"""
    return jsonify(stats.compute_summary())


@api_bp.route("/stats/dashboard")
def stats_dashboard():
    """运营驾驶舱聚合（UI清单 B · P0）：核心指标 + 环比。只读聚合、加限流、异常降级。"""
    if not rate_limit(client_key("api_stats_dashboard"), limit=30, window=60):
        return jsonify({"error": "too_many_requests"}), 429
    try:
        return jsonify(stats.compute_dashboard())
    except Exception as e:
        return jsonify({"error": "dashboard_failed", "detail": str(e)}), 500


@api_bp.route("/stats/trend")
def stats_trend():
    """访客趋势（v3.0.0 功能9）：最近 N 天 PV/UV，供访客趋势图使用。"""
    days = request.args.get("days", 30, type=int)
    if days <= 0 or days > 90:
        days = 30
    return jsonify({"trend": stats.compute_trend(days)})

