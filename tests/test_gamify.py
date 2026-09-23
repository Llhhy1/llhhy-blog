"""读者积分勋章（v3.21.0 gamification）测试。"""
import pytest
from models import db, Post, Reader, Badge
from gamify import (current_reader, award, seed_badges,
                    _check_badges, READER_COOKIE)


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield


def test_seed_badges_idempotent(app_ctx):
    seed_badges()
    n1 = Badge.query.count()
    assert n1 >= 5
    seed_badges()  # 再跑一次应不重复插入
    assert Badge.query.count() == n1


def test_award_dedup_per_day(app_ctx):
    r = Reader(token="t1")
    db.session.add(r)
    db.session.commit()
    assert award(r, "read", 1) is True
    assert r.points == 2
    # 同日同文章再 award 应去重
    assert award(r, "read", 1) is False
    assert r.points == 2
    # 不同文章可再得
    assert award(r, "read", 2) is True
    assert r.points == 4
    # 评论（不同 reason）可叠加
    assert award(r, "comment", 1) is True
    assert r.points == 9


def test_badge_threshold(app_ctx):
    seed_badges()
    r = Reader(token="t2")
    db.session.add(r)
    db.session.commit()
    r.points = 60
    db.session.commit()
    _check_badges(r)
    keys = {rb.badge.key for rb in r.badges.all()}
    assert "novice" in keys      # 阈值 10
    assert "reader" in keys      # 阈值 50
    assert "critic" not in keys  # 阈值 120（未达）


def test_current_reader_create_and_reuse(app):
    with app.test_request_context("/", headers={"Cookie": ""}):
        r1, is_new = current_reader()
        assert is_new is True
        tok = r1.token
    with app.test_request_context("/", headers={"Cookie": f"{READER_COOKIE}={tok}"}):
        r2, is_new2 = current_reader()
        assert is_new2 is False
        assert r2.token == tok


def test_reader_me_sets_cookie(client):
    resp = client.get("/api/reader/me")
    assert resp.status_code == 200
    assert "reader" in resp.get_json()
    # 新读者应写入 reader_token cookie
    assert resp.headers.get("Set-Cookie")


def test_read_awards_points(client, app):
    # 建一篇可见文章
    with app.app_context():
        p = Post(title="积分测试", slug="gamify-points", content="正文", published=True)
        db.session.add(p)
        db.session.commit()
    # 拿读者 cookie
    first = client.get("/api/reader/me")
    cookie = first.headers.get("Set-Cookie")
    headers = {"Cookie": cookie}
    # 读文章（真实阅读触发加积分）
    resp = client.get("/api/post/gamify-points", headers=headers)
    assert resp.status_code == 200
    # 再查 reader/me，积分应 >= 2（read=2）
    me = client.get("/api/reader/me", headers=headers).get_json()
    assert me["reader"]["points"] >= 2


def test_leaderboard_endpoint(client):
    resp = client.get("/api/reader/leaderboard")
    assert resp.status_code == 200
    assert "items" in resp.get_json()
