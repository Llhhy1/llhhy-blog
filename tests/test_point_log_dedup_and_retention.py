"""#47 改表批次：point_log 去重索引 + reader.points 索引 + 保留策略。

钉死的不变量：
- 模型里声明的两个索引**真的被 create_all() 建出来**（单一真相源，不靠迁移脚本二次描述）。
- DB 层唯一索引能拦重复，**包括 post_id IS NULL 的行** —— 朴素 UNIQUE 拦不住这类行
  （SQLite/Postgres 把 NULL 视作互不相同），这正是本批次改用 COALESCE 的原因。
- `award()` 撞唯一键时**返回 False 而非抛异常**，且**回滚掉同一事务里已执行的积分
  UPDATE**：否则「静默重复积分」会变成公开读路径上的 500，或积分被重复加。
- 保留策略：point_log 只删 2 年前的；reader_badge 只清孤儿；**reader 永久保留**。
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

import gamify
from _time import utcnow
from models import db, Badge, PointLog, Reader, ReaderBadge


@pytest.fixture(autouse=True)
def _clean_gamify(app):
    """每个用例前清空积分相关表。

    conftest 让整场测试共用**同一个**临时库文件，且不清数据；不清的话前面用例留下的
    行会让后面用例的全局 `count()` 断言随机翻红（且结果与执行顺序耦合）。
    """
    with app.app_context():
        db.session.execute(db.text("DELETE FROM point_log"))
        db.session.execute(db.text("DELETE FROM reader_badge"))
        db.session.execute(db.text("DELETE FROM reader"))
        db.session.execute(db.text("DELETE FROM badge"))
        db.session.commit()
    yield


def _mk_reader(tok):
    r = Reader(token=tok)
    db.session.add(r)
    db.session.commit()
    return r


def _mk_badge(key):
    b = Badge(key=key, name=key, description="", icon="🏅", threshold=0)
    db.session.add(b)
    db.session.commit()
    return b


# ---------------------------------------------------------------- 索引存在性


def test_indexes_created_from_model(app):
    """两个索引由模型声明 → create_all() 建出（不依赖迁移脚本二次描述）。"""
    with app.app_context():
        names = {r[0] for r in db.session.execute(
            db.text("SELECT name FROM sqlite_master WHERE type = 'index'")).fetchall()}
        assert "uq_pointlog_dedup" in names
        assert "ix_reader_points" in names


# ---------------------------------------------------------------- DB 层去重


def test_unique_index_blocks_null_post_id(app):
    """核心：post_id 为空的重复行也要被拦住（朴素 UNIQUE 拦不住，必须用 COALESCE）。"""
    with app.app_context():
        r = _mk_reader("tok-null-dup")
        db.session.add(PointLog(reader_id=r.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-01"))
        db.session.commit()
        db.session.add(PointLog(reader_id=r.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-01"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_unique_index_blocks_same_post(app):
    with app.app_context():
        r = _mk_reader("tok-post-dup")
        db.session.add(PointLog(reader_id=r.id, reason="read", post_id=7,
                                delta=2, day="2026-01-01"))
        db.session.commit()
        db.session.add(PointLog(reader_id=r.id, reason="read", post_id=7,
                                delta=2, day="2026-01-01"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_same_key_different_day_allowed(app):
    """换一天应能再记一次（去重键含 day，不是永久唯一）。"""
    with app.app_context():
        r = _mk_reader("tok-day")
        db.session.add(PointLog(reader_id=r.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-01"))
        db.session.commit()
        db.session.add(PointLog(reader_id=r.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-02"))
        db.session.commit()
        assert PointLog.query.filter_by(reader_id=r.id).count() == 2


def test_different_reader_or_reason_allowed(app):
    with app.app_context():
        r1 = _mk_reader("tok-r1")
        r2 = _mk_reader("tok-r2")
        db.session.add(PointLog(reader_id=r1.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-01"))
        db.session.add(PointLog(reader_id=r2.id, reason="visit", post_id=None,
                                delta=1, day="2026-01-01"))
        db.session.add(PointLog(reader_id=r1.id, reason="share", post_id=None,
                                delta=3, day="2026-01-01"))
        db.session.commit()
        assert PointLog.query.count() == 3


# ---------------------------------------------------------------- award 行为


def test_award_second_call_returns_false_and_points_once(app):
    with app.app_context():
        r = _mk_reader("tok-award")
        assert gamify.award(r, "visit") is True
        assert gamify.award(r, "visit") is False
        db.session.refresh(r)
        assert (r.points or 0) == gamify.POINT_RULES["visit"]


def test_award_swallows_integrity_error_and_rolls_back(app):
    """制造「先查通过、插入撞键」的并发竞态窗口，断言不抛异常且积分被回滚。

    做法：先插一行 post_id = -1 的哨兵行。它在唯一索引里等价于 NULL
    （COALESCE(post_id, -1)），但 `award()` 的 `post_id IS NULL` 先查**看不见**它，
    于是走到 INSERT 撞键 —— 效果与真实并发竞态一致，且不依赖任何 mock。

    断言两点：
    1. 返回 False 而不是把 IntegrityError 抛出去（否则公开读路径 500）；
    2. 同一事务里已执行的 `UPDATE reader SET points = ...` 被一起回滚，积分没被加。
    """
    with app.app_context():
        r = _mk_reader("tok-race")
        day = gamify._today()
        db.session.execute(db.text(
            "INSERT INTO point_log (reader_id, reason, post_id, delta, day, created_at) "
            "VALUES (:r, 'visit', -1, 1, :d, :c)"),
            {"r": r.id, "d": day, "c": utcnow()})
        db.session.commit()

        assert gamify.award(r, "visit") is False      # 不抛异常
        db.session.refresh(r)
        assert (r.points or 0) == 0                   # UPDATE 已随事务回滚


# ---------------------------------------------------------------- 保留策略


def test_prune_deletes_only_point_log_older_than_two_years(app):
    with app.app_context():
        r = _mk_reader("tok-retention")
        now = utcnow()
        db.session.add(PointLog(reader_id=r.id, reason="visit", post_id=None,
                                delta=1, day="2023-01-01",
                                created_at=now - datetime.timedelta(days=731)))
        db.session.add(PointLog(reader_id=r.id, reason="read", post_id=1,
                                delta=2, day="2026-01-01",
                                created_at=now - datetime.timedelta(days=30)))
        db.session.commit()

        n = gamify.prune_retention()
        assert n["point_log"] == 1
        left = PointLog.query.all()
        assert len(left) == 1 and left[0].day == "2026-01-01"


def test_prune_never_deletes_reader(app):
    """reader 永久保留 —— 本用例是这条产品决策的回归护栏。"""
    with app.app_context():
        _mk_reader("tok-permanent")
        gamify.prune_retention()
        assert Reader.query.filter_by(token="tok-permanent").first() is not None


def test_prune_deletes_orphan_reader_badge_only(app):
    """reader_badge 随 reader：只清「所属 reader 已不存在」的孤儿行。

    能造出孤儿是因为 SQLite 未开 `PRAGMA foreign_keys=ON`（app.py 只设 WAL /
    busy_timeout / synchronous），FK 不级联 —— 与 SECURITY_AUDIT 记录一致。
    """
    with app.app_context():
        r = _mk_reader("tok-orphan")
        b = _mk_badge("orphan-badge")
        db.session.add(ReaderBadge(reader_id=r.id, badge_id=b.id))
        # 孤儿行：指向一个不存在的 reader
        db.session.execute(db.text(
            "INSERT INTO reader_badge (reader_id, badge_id, earned_at) "
            "VALUES (999999, :b, :c)"), {"b": b.id, "c": utcnow()})
        db.session.commit()
        assert ReaderBadge.query.count() == 2

        n = gamify.prune_retention()
        assert n["reader_badge"] == 1
        left = ReaderBadge.query.all()
        assert len(left) == 1 and left[0].reader_id == r.id


def test_prune_is_idempotent(app):
    with app.app_context():
        _mk_reader("tok-idem")
        assert gamify.prune_retention()["point_log"] == 0
        assert gamify.prune_retention()["point_log"] == 0
