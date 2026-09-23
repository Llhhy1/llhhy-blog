"""读者积分勋章（v3.21.0 gamification）测试。"""
import pytest
from models import db, Post, Reader, Badge
from gamify import (current_reader, award, seed_badges,
                    _check_badges, READER_COOKIE, DEFAULT_BADGES)


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


def test_badges_seeded_even_when_tables_already_exist(app):
    """回归（v3.21.1）：`create_app` 里的 `db.create_all()` 会**先**把新表建好，
    于是 `_migrate_new_tables_v3()` 算出的 `need` 恒为空 —— 若把 `seed_badges()`
    写在 `if need:` 分支内，勋章就**永远播不进去**，线上表现为「勋章表建好了但
    一条数据都没有，读者永远拿不到勋章」的静默降级（v3.21.0 首发即踩）。

    本用例先清空勋章再跑迁移，精确复现「表已存在」这一路径。
    """
    from app import _migrate_new_tables_v3
    with app.app_context():
        Badge.query.delete()
        db.session.commit()
        assert Badge.query.count() == 0
        _migrate_new_tables_v3()          # 表都已存在 → need 为空
        assert Badge.query.count() >= 5, "表已存在时也必须完成勋章播种"


def test_seed_badges_partial_and_race_safe(app_ctx):
    """回归（v3.21.2）：按 key 逐枚幂等 —— 部分播种 / 多 worker 竞态都不出错。

    旧实现「`Badge.query.count()==0` 才整批插入」有两个坑：
    ① 表里有任意一行就整体跳过 → 缺的勋章永远补不齐；
    ② gunicorn 多 worker 同时启动都看到空表、都去插入，后提交的撞 UNIQUE 键
       （v3.21.1 上线日志实测出现假警报「播种失败」，会掩盖真失败）。
    """
    # ① 部分播种：清空后只手工插 1 枚 → seed 后应补齐到默认枚数，且不覆盖已有项
    # （测试库跨用例共享，前面用例可能已播种，必须先清掉才能构造「部分播种」场景）
    Badge.query.delete()
    db.session.commit()
    db.session.add(Badge(key="novice", name="外部插入", icon="🌱", threshold=10))
    db.session.commit()
    seed_badges()
    assert Badge.query.count() == len(DEFAULT_BADGES)
    assert Badge.query.filter_by(key="novice").one().name == "外部插入"

    # ② 再跑一次仍幂等（不重复插入）
    seed_badges()
    assert Badge.query.count() == len(DEFAULT_BADGES)


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
