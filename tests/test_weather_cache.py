"""`/api/weather` 出站缓存测试（v3.23.0，#48 同步外网调用移出请求路径）。

为什么钉死这些：该接口是**公开**端点，原先每次请求都真打外部 API（坐标模式串行
最坏约 17s），gunicorn gthread 只有 8 个并发槽，几个慢请求就能把整站拖成 502。

覆盖：
- 同源第二次请求**不再出网**（缓存命中）。
- 不同城市互不串味（key 隔离）。
- 过期后重新拉取（TTL 生效）。
- 上游全失败且**有**过期数据 → 回吐旧数据 200（宁可旧，不要 502）。
- 上游全失败且**无**缓存 → 502。
"""
import contextlib
import json

import pytest
import urllib.request

import routes as routes_mod


@pytest.fixture(autouse=True)
def _clean():
    """清缓存与限流计数，保证用例互不污染。"""
    routes_mod._WEATHER_CACHE.clear()
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    routes_mod._WEATHER_CACHE.clear()
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


class _FakeResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


@pytest.fixture
def net(monkeypatch):
    """拦截出网：记录调用次数，可控成功/失败。"""
    state = {"calls": 0, "fail": False, "temp": "21"}

    def fake_urlopen(req, *a, **kw):
        state["calls"] += 1
        if state["fail"]:
            raise OSError("upstream down")
        return _FakeResp({"current_condition": [{
            "temp_C": state["temp"], "weatherCode": "113",
            "weatherDesc": [{"value": "晴"}],
        }]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return state


def test_second_identical_request_does_not_hit_network(client, net):
    r1 = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    r2 = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    assert r1.status_code == 200 and r2.status_code == 200
    assert net["calls"] == 1, "第二次必须命中缓存，不再出网"
    assert r1.get_json()["temp"] == r2.get_json()["temp"]


def test_different_city_not_shared(client, net):
    client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    client.get("/api/weather?city=%E4%B8%8A%E6%B5%B7")
    assert net["calls"] == 2, "不同城市不能共用缓存"


def test_expired_entry_refetches(client, net, monkeypatch):
    client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    assert net["calls"] == 1
    monkeypatch.setattr(routes_mod, "_WEATHER_TTL", -1.0)  # 立即过期
    resp = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    assert resp.status_code == 200
    assert net["calls"] == 2, "TTL 过期后必须重新拉取"


def test_stale_served_when_upstream_fails(client, net, monkeypatch):
    """有旧数据时，上游挂了也回吐旧数据（stale-while-error），不 502。"""
    first = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC").get_json()
    monkeypatch.setattr(routes_mod, "_WEATHER_TTL", -1.0)
    net["fail"] = True
    resp = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    assert resp.status_code == 200, "有过期数据时必须回吐旧值而不是 502"
    assert resp.get_json()["temp"] == first["temp"]


def test_502_when_upstream_fails_without_cache(client, net):
    net["fail"] = True
    resp = client.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    assert resp.status_code == 502


def test_cache_is_capped(monkeypatch):
    """city 是用户可控字符串 → 缓存必须限容，不能无界增长。"""
    monkeypatch.setattr(routes_mod, "_WEATHER_CACHE_MAX", 5)
    for i in range(50):
        routes_mod._weather_cache_put("city:c%d" % i, {"temp": i})
    assert len(routes_mod._WEATHER_CACHE) <= 5, "超容必须清理，防内存无界增长"
