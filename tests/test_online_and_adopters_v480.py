"""v4.8.0 回归：在线人数接口 + 「谁在用 llhhy-blog」自愿登记链路。

覆盖三条容易做错的地方：
1. 在线数的**口径**（窗口内、排除爬虫、去重 IP）与**缓存**（前台刷得再勤也不该
   每刷一次就打一次库）；
2. `uses_llhhy` 的**默认值语义**：客户端没带这个字段时不得把已有登记抹掉
   （HTML 复选框未勾选压根不提交，靠隐藏位区分「明确取消」与「没带字段」）；
3. `/api/adopters` **不出网**：GitHub 指标只读 Setting 缓存，取数只发生在后台
   显式刷新时（匿名接口触发出站是本项目反复踩过的放大面）。
"""
import datetime
import json

import pytest

from models import db, FriendLink, LinkApplication, Setting, User, VisitLog, ROLE_SUPER

PASSWORD = "Passw0rd!23"


@pytest.fixture()
def fresh_online_cache():
    """清掉在线快照的进程内缓存（否则用例会读到上一条用例留下的数字）。"""
    import stats
    stats._ONLINE_SNAPSHOT["ts"] = 0.0
    stats._ONLINE_SNAPSHOT["data"] = None
    yield
    stats._ONLINE_SNAPSHOT["ts"] = 0.0
    stats._ONLINE_SNAPSHOT["data"] = None


def _mk_visit(ip, minutes_ago=0, is_bot=False):
    from _time import utcnow
    row = VisitLog(ip=ip, date=datetime.date.today().isoformat(),
                   path="/post/x", is_bot=is_bot,
                   created_at=utcnow() - datetime.timedelta(minutes=minutes_ago))
    db.session.add(row)
    db.session.commit()
    return row


@pytest.fixture()
def super_client(client, app):
    import secrets
    uname = "su_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com", role=ROLE_SUPER,
                 must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    tok = (client.get("/api/csrf").get_json() or {})
    assert client.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": tok.get("csrf_token") or tok.get("token") or ""}
                       ).status_code == 200
    return client


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


# ---------- 1. 在线人数 ----------

def test_online_endpoint_counts_window_and_excludes_bot(app, client, fresh_online_cache):
    with app.app_context():
        _mk_visit("1.1.1.1", minutes_ago=1)            # 窗口内真人 → 计入
        _mk_visit("2.2.2.2", minutes_ago=2)            # 窗口内另一 IP → 计入
        _mk_visit("3.3.3.3", minutes_ago=1, is_bot=True)   # 爬虫 → 不计
        _mk_visit("1.1.1.1", minutes_ago=3)            # 同 IP 再来一次 → 去重不重复计
        _mk_visit("4.4.4.4", minutes_ago=120)          # 窗口外 → 不计

    d = client.get("/api/stats/online").get_json()
    assert d["online"] == 2, d
    assert d["approx"] is True, "响应必须自带「近似值」标记，前端据此挂角标"
    assert d["window_min"] == 10
    assert d["today_uv"] >= 2 and d["today_pv"] >= 4
    # 公开接口绝不回单条访客数据
    body = json.dumps(d, ensure_ascii=False)
    assert "1.1.1.1" not in body and "ip" not in {k.lower() for k in d}


def test_online_endpoint_serves_cached_snapshot(app, client, fresh_online_cache):
    """20 秒内的第二次请求不该重算 —— 前台每访客都会刷这个接口。"""
    with app.app_context():
        _mk_visit("5.5.5.5", minutes_ago=1)
        first = client.get("/api/stats/online").get_json()["online"]
        _mk_visit("6.6.6.6", minutes_ago=1)
        second = client.get("/api/stats/online").get_json()["online"]
        assert second == first, "缓存在 TTL 内失效了（前台刷一次就打一次库）"

        import stats
        stats._ONLINE_SNAPSHOT["ts"] = 0.0            # 手动让缓存过期
        third = client.get("/api/stats/online").get_json()["online"]
        assert third == first + 1, third


def test_online_snapshot_degrades_without_rows(app, fresh_online_cache):
    import stats
    with app.app_context():
        db.session.query(VisitLog).delete()
        db.session.commit()
        snap = stats.online_snapshot(force=True)
    assert snap["online"] == 0 and snap["today_pv"] == 0 and snap["today_uv"] == 0


# ---------- 2. /api/adopters：只读缓存、不出网 ----------

def test_adopters_lists_only_flagged_links(app, client):
    with app.app_context():
        db.session.query(FriendLink).delete()
        db.session.add(FriendLink(name="用本站搭的", url="https://a.example",
                                  description="自述在用", sort=1, uses_llhhy=True))
        db.session.add(FriendLink(name="普通友链", url="https://b.example",
                                  description="", sort=2, uses_llhhy=False))
        db.session.commit()
    d = client.get("/api/adopters").get_json()
    assert [x["url"] for x in d["sites"]] == ["https://a.example"]
    assert d["self_reported"] is True
    assert d["repo"] is None, "没刷新过就该是 null，不许显示 0 之类的假数据"


def test_adopters_reads_repo_cache_without_egress(app, client, monkeypatch):
    """打这个接口**不允许出网**：任何真实 HTTP 请求都不该发生。"""
    import adopter_stats

    def _boom(*_a, **_kw):
        raise AssertionError("/api/adopters 不该触发出站请求")

    monkeypatch.setattr(adopter_stats, "open_public", _boom)
    with app.app_context():
        row = Setting.query.filter_by(key=adopter_stats.REPO_STATS_KEY).first()
        if row is None:
            row = Setting(key=adopter_stats.REPO_STATS_KEY)
            db.session.add(row)
        row.value = json.dumps({"stars": 3, "forks": 1, "release_downloads": 42,
                                "refreshed_at": "2026-10-20 23:00 UTC"})
        db.session.commit()
    d = client.get("/api/adopters").get_json()
    assert d["repo"]["release_downloads"] == 42
    assert d["repo"]["stars"] == 3


def test_adopters_ignores_corrupt_cache(app, client):
    import adopter_stats
    with app.app_context():
        row = Setting.query.filter_by(key=adopter_stats.REPO_STATS_KEY).first()
        if row is None:
            row = Setting(key=adopter_stats.REPO_STATS_KEY)
            db.session.add(row)
        row.value = "{ 不是 JSON"
        db.session.commit()
    assert client.get("/api/adopters").get_json()["repo"] is None


# ---------- 3. 登记标记的写入链路 ----------

def test_link_apply_records_voluntary_flag(client, app):
    r = client.post("/api/link-apply", json={
        "name": "小站", "url": "https://c.example", "description": "",
        "email": "", "uses_llhhy": True}, headers=_csrf(client))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        row = LinkApplication.query.filter_by(url="https://c.example").first()
        assert row is not None and row.uses_llhhy is True


def test_link_apply_defaults_to_unmarked(client, app):
    client.post("/api/link-apply", json={"name": "小站2", "url": "https://d.example"},
                headers=_csrf(client))
    with app.app_context():
        row = LinkApplication.query.filter_by(url="https://d.example").first()
        assert row is not None and row.uses_llhhy is False


def test_approve_copies_flag_into_friend_link(super_client, app):
    with app.app_context():
        db.session.query(LinkApplication).delete()
        db.session.query(FriendLink).delete()
        db.session.add(LinkApplication(name="登记站", url="https://e.example",
                                       status="pending", uses_llhhy=True))
        db.session.commit()
        aid = LinkApplication.query.filter_by(url="https://e.example").first().id
    r = super_client.post("/admin/link-application/%d/approve" % aid,
                          headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        link = FriendLink.query.filter_by(url="https://e.example").first()
        assert link is not None and link.uses_llhhy is True


def test_approve_duplicate_does_not_unmark_existing(super_client, app):
    """同 URL 已在友链里：后续一次**没勾选**的申请不该把已登记的标记抹掉。"""
    with app.app_context():
        db.session.query(LinkApplication).delete()
        db.session.query(FriendLink).delete()
        db.session.add(FriendLink(name="已在用", url="https://f.example", uses_llhhy=True, sort=1))
        db.session.add(LinkApplication(name="重复申请", url="https://f.example",
                                       status="pending", uses_llhhy=False))
        db.session.commit()
        aid = LinkApplication.query.filter_by(url="https://f.example").first().id
    super_client.post("/admin/link-application/%d/approve" % aid,
                      headers=_csrf(super_client), follow_redirects=True)
    with app.app_context():
        assert FriendLink.query.filter_by(url="https://f.example").first().uses_llhhy is True


def test_save_core_keeps_flag_when_field_absent(app):
    """`save_friend_link_core` 的两个分支：没带字段=不动，带隐藏位且未勾=取消。"""
    from admin._helpers import save_friend_link_core
    with app.app_context():
        db.session.query(FriendLink).delete()
        db.session.commit()
        err, _n, link = save_friend_link_core(None, {"name": "G", "url": "https://g.example",
                                                     "uses_llhhy": "1"})
        assert not err and link.uses_llhhy is True
        # 移动端常见的「只传部分字段」：两个 key 都没有 → 保持原值
        err, _n, same = save_friend_link_core(link, {"name": "G2", "url": "https://g.example"})
        assert not err and same.uses_llhhy is True, "未带字段的编辑把登记抹掉了"
        # 后台表单（带 uses_llhhy_form 但复选框未勾）→ 明确取消
        err, _n, same = save_friend_link_core(
            link, {"name": "G3", "url": "https://g.example", "uses_llhhy_form": "1"})
        assert not err and same.uses_llhhy is False


# ---------- 4. 后台刷新：成功写缓存、失败不覆盖 ----------

def test_refresh_writes_cache(app, monkeypatch):
    import adopter_stats

    payload = {
        "https://api.github.com/repos/" + adopter_stats.REPO:
            {"stargazers_count": 7, "forks_count": 2, "subscribers_count": 1,
             "open_issues_count": 5},
        "https://api.github.com/repos/%s/releases?per_page=100" % adopter_stats.REPO:
            [{"assets": [{"download_count": 10}, {"download_count": 3}]},
             {"assets": [{"download_count": 1}]}],
    }

    class _Resp:
        def __init__(self, body):
            self._body = json.dumps(body).encode("utf-8")

        def read(self, *_a):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(adopter_stats, "open_public",
                        lambda req, timeout=None: _Resp(payload[req.full_url]))
    with app.app_context():
        ok, msg = adopter_stats.refresh()
        assert ok, msg
        cached = adopter_stats.cached_stats()
        assert cached["stars"] == 7 and cached["release_downloads"] == 14
        assert cached["refreshed_at"].endswith("UTC")


def test_refresh_keeps_old_cache_when_github_unreachable(app, monkeypatch):
    """出网失败**不覆盖**旧缓存：把「GitHub 暂时不可达」显示成「指标全 0」更糟。"""
    import adopter_stats

    monkeypatch.setattr(adopter_stats, "fetch_repo_stats",
                        lambda: (_ for _ in ()).throw(OSError("network down")))
    with app.app_context():
        row = Setting.query.filter_by(key=adopter_stats.REPO_STATS_KEY).first()
        if row is None:
            row = Setting(key=adopter_stats.REPO_STATS_KEY)
            db.session.add(row)
        row.value = json.dumps({"stars": 9, "forks": 3, "release_downloads": 14,
                                "refreshed_at": "2026-10-20 00:00 UTC"})
        db.session.commit()
        before = adopter_stats.cached_stats()
        ok, msg = adopter_stats.refresh()
        assert ok is False and "network down" in msg
        assert adopter_stats.cached_stats() == before, "刷新失败把旧缓存写坏了"
