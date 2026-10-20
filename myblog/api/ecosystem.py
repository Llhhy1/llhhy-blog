"""v4.7.5 生态统计 API（公开只读 + 心跳接收）。

- `POST /api/ecosystem/heartbeat`：部署实例向**中心端**发心跳（公开、限流）。
- `GET  /api/ecosystem/stats`：站点注册表统计（公开、只读）。

⚠️ **这两个端点都是公开的**，因此：
- 限流防刷（心跳端点每 IP 每分钟 30 次）；
- 心跳内容严格白名单（`site_key` 格式、`url` 协议与长度）；
- **绝不代收任何访客数据** —— 本功能只统计「站点」，不统计「人」。
"""
from flask import request, jsonify

from .common import api_bp, rate_limit, client_key
import ecosystem


@api_bp.route("/ecosystem/heartbeat", methods=["POST"])
def ecosystem_heartbeat():
    """接收一次部署实例心跳。

    ⚠️ 心跳数据是**自报**的，任何人都能伪造 → 展示时必须如实标注
    「以下站点自报在使用本系统」。不做 URL 可达性验证：那是 SSRF。
    """
    if not rate_limit(client_key("eco_hb"), limit=30, window=60):
        return jsonify({"error": "rate limited"}), 429
    data = request.get_json(silent=True) or {}
    ok, why = ecosystem.receive_heartbeat(data)
    if not ok:
        return jsonify({"error": why}), 400
    return jsonify({"ok": True})


@api_bp.route("/ecosystem/stats")
def ecosystem_stats():
    """站点注册表统计（供前台展示「有多少个站点在用本系统」）。"""
    if not rate_limit(client_key("eco_stats"), limit=60, window=60):
        return jsonify({"total": 0, "active": 0, "sites": []})
    return jsonify(ecosystem.stats())
