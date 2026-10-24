"""v4.9.0 设备 / 浏览器分布（ROADMAP §3.1）。

这条待办此前挂了很久，卡在「需新表」的判断上。实测 `parse_device()` 早就
存在，只需给 `visit_log` 加 `device` / `browser` 两列即可 —— 无新表。

测试聚焦三件事：

1. **解析正确**：UA 被解析成粗分类落库（`手机` / `Chrome`），而不是整串。
2. **隐私收口（反向断言）**：原始 UA 里的可指纹化片段（设备型号 `SM-S918B`、
   系统小版本 `Android 13`）**不得**出现在落库的任何一列。本文件只存分类，
   不存 UA —— 若哪天改回存整串，第 2 条必须变红。
3. **聚合排除空值**：`_top_devices` / `_top_browsers` 把空串（v4.9.0 之前
   未采集的历史行）排除在外，否则会聚成一大坨「未知」压扁真实分布。

属地解析 `_resolve_region_async` 会发外网，测试里一律挡掉。
"""

import pytest

from models import db, VisitLog
import stats as stats_mod

UA_MOBILE = ("Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
UA_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1")


@pytest.fixture
def clean_visits(app):
    """清空 visit_log 并挡掉属地外网解析。测试库全 session 共享，必须先清。"""
    with app.app_context():
        VisitLog.query.delete()
        db.session.commit()
    yield
    with app.app_context():
        VisitLog.query.delete()
        db.session.commit()


def _record(app, monkeypatch, ua):
    monkeypatch.setattr(stats_mod, "_resolve_region_async", lambda ip: None)
    with app.test_request_context("/", headers={"User-Agent": ua},
                                  environ_base={"REMOTE_ADDR": "203.0.113.7"}):
        stats_mod.record_visit("/", post_id=None, referrer="")


def test_手机UA解析为粗分类且不含可指纹片段(app, monkeypatch, clean_visits):
    _record(app, monkeypatch, UA_MOBILE)
    with app.app_context():
        row = VisitLog.query.first()
        assert row is not None, "record_visit 没有落库"
        assert row.device == "手机"
        assert row.browser == "Chrome"
        # 反向：原始 UA 型号 / 系统小版本不得落库（这是隐私收口的判据）
        stored = (row.device or "") + (row.browser or "")
        assert "SM-S918B" not in stored
        assert "Android 13" not in stored
        assert "Mozilla" not in stored


def test_桌面与iOS各自归类正确(app, monkeypatch, clean_visits):
    _record(app, monkeypatch, UA_DESKTOP)
    _record(app, monkeypatch, UA_IPHONE)
    with app.app_context():
        got = {(r.device, r.browser) for r in VisitLog.query.all()}
    assert ("电脑", "Chrome") in got, got
    assert ("手机", "Safari") in got, got


def test_聚合排除未采集的空值(app, monkeypatch, clean_visits):
    """空串代表 v4.9.0 之前的老访问，必须排除，否则聚成「未知」档压扁分布。"""
    with app.app_context():
        # 2 条手机 Chrome + 1 条电脑 Chrome + 1 条历史行（device/browser 均为空）
        for _ in range(2):
            db.session.add(VisitLog(date=stats_mod.today_str(), hour=10, ip="203.0.113.1",
                                    path="/", device="手机", browser="Chrome"))
        db.session.add(VisitLog(date=stats_mod.today_str(), hour=11, ip="203.0.113.2",
                                path="/", device="电脑", browser="Chrome"))
        db.session.add(VisitLog(date=stats_mod.today_str(), hour=12, ip="203.0.113.3",
                                path="/", device="", browser=""))
        db.session.commit()

        devs = stats_mod._top_devices()
        brs = stats_mod._top_browsers()

    dev_map = {d["name"]: d["count"] for d in devs}
    assert dev_map.get("手机") == 2, dev_map
    assert dev_map.get("电脑") == 1, dev_map
    assert "" not in dev_map, "空设备不得进入聚合"
    # 浏览器侧两条手机 + 一条电脑都是 Chrome → 3
    assert {b["name"]: b["count"] for b in brs} == {"Chrome": 3}, brs


def test_汇总含设备与浏览器键(app, monkeypatch, clean_visits):
    """统计页 summary 必须带上新键，否则模板永远走「暂无数据」分支。"""
    _record(app, monkeypatch, UA_DESKTOP)
    with app.app_context():
        s = stats_mod.compute_summary()
    assert "devices" in s and "browsers" in s, sorted(s.keys())
    assert any(d["name"] == "电脑" for d in s["devices"]), s["devices"]
    assert any(b["name"] == "Chrome" for b in s["browsers"]), s["browsers"]
