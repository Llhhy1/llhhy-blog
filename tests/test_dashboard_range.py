"""运营驾驶舱 二期回归：/api/stats/dashboard 的 range 参数与趋势序列增量字段。

锁定两点：
1. ?range= 仅改变趋势序列长度（7/30/90），且非法值回退 30；
2. 趋势序列每条在 PV/UV 之上额外带 comments / posts 字段。
"""
import stats


def test_compute_dashboard_trend_enriched(app):
    with app.app_context():
        trend = stats.compute_dashboard_trend(7)
        assert len(trend) == 7
        pt = trend[0]
        assert set(pt.keys()) == {"date", "pv", "uv", "comments", "posts"}
        # 上限钳制到 90 天
        assert len(stats.compute_dashboard_trend(999)) == 90
        # 下限钳制到 1 天
        assert len(stats.compute_dashboard_trend(0)) == 1


def test_dashboard_range_param(client):
    r7 = client.get("/api/stats/dashboard?range=7")
    assert r7.status_code == 200
    data7 = r7.get_json()
    assert len(data7["trend"]) == 7
    for pt in data7["trend"]:
        assert {"date", "pv", "uv", "comments", "posts"} <= set(pt.keys())

    r30 = client.get("/api/stats/dashboard?range=30")
    assert r30.status_code == 200
    assert len(r30.get_json()["trend"]) == 30

    # 非法 range 回退默认 30 天
    rbad = client.get("/api/stats/dashboard?range=999")
    assert rbad.status_code == 200
    assert len(rbad.get_json()["trend"]) == 30

    # 默认（不带参数）也是 30 天
    rdef = client.get("/api/stats/dashboard")
    assert rdef.status_code == 200
    assert len(rdef.get_json()["trend"]) == 30


def test_dashboard_wow_delta_present(client):
    """卡片环比含 vs 上周同期（wow）字段，前端「vs 上周」维度依赖它。"""
    r = client.get("/api/stats/dashboard?range=30")
    assert r.status_code == 200
    d = r.get_json()
    assert "deltas" in d
    for k in ("pv_wow", "uv_wow", "subs_wow", "comments_wow", "posts_wow"):
        assert k in d["deltas"]
