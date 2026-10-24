"""v4.7.5 生态统计（站点注册表）+ 本站在线数接口。

这个功能能成立的前提是**信任边界**，所以测试的重点不是「能不能收到心跳」，
而是「不该收的收下、该关的关着」：

1. **默认开启、可关闭**：v4.7.6 起默认值改为「开」（不上报就永远统计不到），
   但取消勾选必须**真的一个请求都不发** —— 这是这个功能能被接受的前提。
2. **上报内容受限**：只认 site_key / url / version / listed 四项，
   坏格式一律拒收。
3. **中心地址必须公网**：否则这个设置会变成「让服务器请求任意地址」的后门。
4. **去重**：同一站点多次心跳只算一个（site_key 唯一）。
5. **不公开列出 = 匿名**：心跳**不带 url**，且中心端要把已存的 url 清掉。
6. **在线数是近似值**：接口必须如实标 `approx`，不能装作精确值。
"""
import secrets

import pytest

from models import db, Setting
import ecosystem


def _set(key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _wipe():
    Setting.query.filter(Setting.key.like("ecosystem%")).delete()
    db.session.commit()


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.remove()
        Setting.query.filter(Setting.key.like("ecosystem%")).delete()
        try:
            from models import EcosystemSite
            EcosystemSite.query.delete()
        except Exception:  # noqa: BLE001, S110 （表可能还不存在，忽略即可）
            pass
        db.session.commit()


# ---------- 客户端：默认开启、可关闭 ----------


def test_默认参与(app):
    """v4.7.6：**默认开启** —— 不上报就永远统计不到使用量。"""
    with app.app_context():
        _wipe()
        assert ecosystem.opt_in() is True


def test_取消参与后不上报(app, monkeypatch):
    """勾选框是**真的开关**：取消后必须一个请求都不发。"""
    import outbound
    sent = []
    monkeypatch.setattr(outbound, "open_url", lambda *a, **k: sent.append(a))
    with app.app_context():
        _wipe()
        _set("ecosystem_opt_in", "false")
        _set("ecosystem_center", "https://example.com")
        assert ecosystem.report_heartbeat() is False, "已取消参与却发出了请求"
    assert sent == [], "取消参与后不应产生任何出站请求"


def test_没有中心地址时回退默认中心(app):
    """「默认开启」要生效，就必须有默认中心 —— 否则 opt-in 开着也发不出去。"""
    with app.app_context():
        _wipe()
        assert ecosystem.center_url() == ecosystem.DEFAULT_CENTER
        assert ecosystem.DEFAULT_CENTER.startswith("https://")


def test_中心地址为内网时不上报(app):
    """中心地址走 SSRF 白名单 —— 否则它就是内网探测后门。"""
    with app.app_context():
        _wipe()
        _set("ecosystem_opt_in", "true")
        _set("ecosystem_center", "http://127.0.0.1:8080")
        assert ecosystem.report_heartbeat() is False


# ---------- 测试态护栏（v4.7.6 回归）----------


def test_pytest_里绝不发出真实心跳(app, monkeypatch):
    """回归：默认开启 + 真实默认中心后，pytest/CI 会往生产发真实心跳。

    实测一次 CI + 两次本地全量测试注入了 5 条假站点（其中含 CI 机器）。
    护栏必须钉死：默认路径下一个请求都不许发。
    """
    import outbound
    sent = []
    monkeypatch.setattr(outbound, "open_url", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(outbound, "safe_public_url", lambda u: True)
    with app.app_context():
        _wipe()
        assert ecosystem.opt_in() is True, "前提是默认开启"
        assert ecosystem.report_heartbeat() is False, "pytest 里发出了真实心跳"
    assert sent == [], "pytest 里不应产生任何出站请求"


def test_护栏本身是唯一拦路者(app, monkeypatch):
    """变异验证：摘掉护栏后必须**真的会发** —— 否则上一条是假绿。"""
    sent = _capture(monkeypatch)
    with app.app_context():
        _wipe()
        assert ecosystem.report_heartbeat() is True
    assert len(sent) == 1, "摘掉护栏后仍未发出，说明上一条测试是假绿"


# ---------- 客户端：url 只在愿意公开时才带 ----------


def _capture(monkeypatch):
    """把出站请求接住，返回 (记录列表,)。避免测试依赖真实网络。"""
    import outbound
    sent = []

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake(url, **kw):
        sent.append((url, kw))
        return _Resp()

    monkeypatch.setattr(outbound, "open_url", _fake)
    # 默认中心是真实域名，测试环境不保证能解析 —— 校验本身另有测试覆盖
    monkeypatch.setattr(outbound, "safe_public_url", lambda u: True)
    # 本组用例**就是要验发送逻辑**，所以要显式摘掉测试态护栏
    monkeypatch.setattr(ecosystem, "_is_test_runtime", lambda: False)
    return sent


def _payload(sent):
    import json
    assert len(sent) == 1, "应恰好发出一次心跳"
    return json.loads(sent[0][1]["data"].decode("utf-8"))


def test_默认公开时心跳带_url(app, monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setattr(ecosystem, "own_site_url", lambda: "https://mine.example.com")
    with app.app_context():
        _wipe()
        assert ecosystem.report_heartbeat() is True
    p = _payload(sent)
    assert p["url"] == "https://mine.example.com"
    assert p["listed"] is True


def test_不愿公开时心跳不带_url(app, monkeypatch):
    """「不公开列出」= 匿名：URL 对个人博客就是身份，这时连发都不该发。"""
    sent = _capture(monkeypatch)
    monkeypatch.setattr(ecosystem, "own_site_url", lambda: "https://mine.example.com")
    with app.app_context():
        _wipe()
        _set("ecosystem_listed", "false")
        assert ecosystem.report_heartbeat() is True
    p = _payload(sent)
    assert p["url"] == "", "不愿公开却仍然上报了 url"
    assert p["listed"] is False
    assert p["site_key"], "仍然要发 site_key（否则中心端无法去重）"


def test_关闭公开展示后中心端清空_url(app):
    """遗忘：只留 `url or 旧值` 会让人以为关掉了，旧地址其实还躺着。"""
    from models import EcosystemSite
    with app.app_context():
        _wipe()
        d = _hb(url="https://was-public.example.com", listed=True)
        ecosystem.receive_heartbeat(d)
        row = EcosystemSite.query.filter_by(site_key=d["site_key"]).first()
        assert row.url == "https://was-public.example.com"
        ecosystem.receive_heartbeat(_hb(site_key=d["site_key"], url="", listed=False))
        row = EcosystemSite.query.filter_by(site_key=d["site_key"]).first()
        assert row.url == "", "关闭公开展示后，中心端应把 url 清掉"
        assert row.listed is False


# ---------- 客户端：site_key 稳定且随机 ----------


def test_site_key_稳定且不重复(app):
    with app.app_context():
        _wipe()
        k1 = ecosystem.site_key()
        k2 = ecosystem.site_key()
        assert k1 == k2, "同一台机器每次应拿到同一个 key（否则中心端会去重失败）"
        assert len(k1) >= 16
        assert all(c in "0123456789abcdef" for c in k1), "应是十六进制随机串"


def test_site_key_落库后可复用(app):
    with app.app_context():
        _wipe()
        k = ecosystem.site_key()
        assert Setting.query.filter_by(key="ecosystem_site_key").first() is not None
        assert ecosystem.site_key() == k


# ---------- 中心端：接收与校验 ----------


def _hb(**kw):
    d = {"site_key": secrets.token_hex(16), "url": "https://a.example.com",
         "version": "4.7.5", "listed": True}
    d.update(kw)
    return d


def test_接收心跳成功(app):
    with app.app_context():
        _wipe()
        ok, why = ecosystem.receive_heartbeat(_hb())
        assert ok is True, why


def test_同站点重复心跳不重复计数(app):
    """去重靠 site_key —— 否则「每小时一次」的心跳会把站点数刷爆。"""
    from models import EcosystemSite
    with app.app_context():
        _wipe()
        d = _hb()
        ecosystem.receive_heartbeat(d)
        ecosystem.receive_heartbeat(d)
        ecosystem.receive_heartbeat(d)
        assert EcosystemSite.query.count() == 1


def test_拒绝非法_site_key(app):
    with app.app_context():
        _wipe()
        for bad in ("", "xyz", "ZZZZ", "'; DROP TABLE--", "a" * 200):
            ok, _ = ecosystem.receive_heartbeat(_hb(site_key=bad))
            assert ok is False, "应拒绝 site_key=%r" % bad


def test_拒绝非_http_协议(app):
    with app.app_context():
        _wipe()
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"):
            ok, _ = ecosystem.receive_heartbeat(_hb(url=bad))
            assert ok is False, "应拒绝 url=%r" % bad


def test_拒绝非字典(app):
    with app.app_context():
        _wipe()
        assert ecosystem.receive_heartbeat(None)[0] is False
        assert ecosystem.receive_heartbeat("x")[0] is False


# ---------- 中心端：统计 ----------


def test_统计总站点与活跃数(app):
    from models import EcosystemSite
    from _time import utcnow
    import datetime
    with app.app_context():
        _wipe()
        now = utcnow()
        db.session.add(EcosystemSite(site_key="a" * 32, url="https://a.example.com",
                                     version="4.7.5", listed=True,
                                     first_seen=now, last_seen=now))
        # 40 天前的心跳 = 陈旧站点：仍计数，但不该出现在公开展示列表里
        db.session.add(EcosystemSite(site_key="b" * 32, url="https://b.example.com",
                                     version="4.7.5", listed=True,
                                     first_seen=now - datetime.timedelta(days=40),
                                     last_seen=now - datetime.timedelta(days=40)))
        db.session.commit()
        s = ecosystem.stats()
        assert s["total"] == 2
        assert s["active"] == 1, "24 小时内有活动的才算活跃"
        assert len(s["sites"]) == 1, "只列出 30 天内有心跳的站点（陈旧的只计数不展示）"
        assert s["sites"][0]["url"] == "https://a.example.com"


def test_不愿公开的站点只计数不展示(app):
    from models import EcosystemSite
    from _time import utcnow
    with app.app_context():
        _wipe()
        now = utcnow()
        db.session.add(EcosystemSite(site_key="c" * 32, url="https://c.example.com",
                                     version="4.7.5", listed=False,
                                     first_seen=now, last_seen=now))
        db.session.commit()
        s = ecosystem.stats()
        assert s["total"] == 1, "仍然计数"
        assert s["sites"] == [], "但不出现在公开展示列表里"


# ---------- API ----------


def test_online_接口公开可用(app, client):
    """在线数要能**公开**给访客看 —— 不能要求登录。"""
    r = client.get("/api/stats/online")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert "online" in d
    assert d["approx"] is True, "在线数是近似值，接口必须如实标注"


def test_ecosystem_stats_接口(app, client):
    r = client.get("/api/ecosystem/stats")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    for k in ("total", "active", "sites"):
        assert k in d


def test_heartbeat_接口(app, client):
    r = client.post("/api/ecosystem/heartbeat", json=_hb())
    assert r.status_code == 200, r.get_data(as_text=True)[:200]


def test_heartbeat_接口拒坏数据(app, client):
    r = client.post("/api/ecosystem/heartbeat", json={"site_key": "bad"})
    assert r.status_code == 400


def test_heartbeat_接口需要_json(app, client):
    r = client.post("/api/ecosystem/heartbeat", data="not json",
                    content_type="text/plain")
    assert r.status_code in (400, 415), r.status_code


# ---------- 设置页 ----------


def test_设置页含生态统计配置区():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    with open(os.path.join(root, "myblog", "templates", "admin", "settings.html"),
              encoding="utf-8") as f:
        src = f.read()
    assert 'name="ecosystem_opt_in"' in src, "缺少「参与生态统计」开关"
    assert 'name="ecosystem_center"' in src, "缺少生态中心地址输入"
    assert 'name="ecosystem_listed"' in src, "缺少「是否公开展示」开关"
    # 开关必须写明「默认开启且可关闭」与「不含访客数据」
    assert "默认开启" in src, "设置页必须如实写明默认是开的"
    assert "可随时关闭" in src
    assert "不含任何访客数据" in src
    # 匿名路径必须写清楚：取消公开展示 = 心跳不带 URL
    assert "匿名" in src


def test_中心地址保存时校验为公网():
    """源码级断言：中心地址必须过 SSRF 白名单（内网地址要能当场拒绝）。"""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    with open(os.path.join(root, "myblog", "admin", "settings.py"), encoding="utf-8") as f:
        src = f.read()
    assert "safe_public_url" in src, "生态中心地址必须过 SSRF 白名单"
    assert "ecosystem_center" in src
