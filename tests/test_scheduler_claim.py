"""定时发布「随 gunicorn worker 翻倍」的修复：到点文章原子认领。

背景：gunicorn 开 N 个 worker，`create_app()` 给每个 worker 各起一条调度线程，
于是同一篇定时文章会被 N 条线程同时扫到。原实现「先查后改」，N 条线程都能通过查询，
结果是同一篇被发布 N 次、并触发 N 份订阅推送/邮件。

钉死的不变量：
- 同一篇到点文章**只有一次**认领能成功，其余返回 False（N 个并发者里恰好一个赢家）。
- 赢家才把文章翻成已发布并清空 `scheduled_at`；输家**不改变任何数据**。
- 已发布的文章不会被重复认领（幂等，重复跑调度不会二次推送）。
"""
import datetime

from app import claim_scheduled_post
from _time import utcnow
from models import db, Post, User, ROLE_SUPER


def _mk_due_post(tag):
    """建一篇「已到点但未发布」的文章（模拟调度线程扫到的对象）。"""
    u = User(username="author-" + tag, password_hash="x", role=ROLE_SUPER)
    db.session.add(u)
    db.session.commit()
    p = Post(title="t-" + tag, slug="s-" + tag, summary="summary",
             content="content", author_id=u.id, published=False)
    p.scheduled_at = utcnow() - datetime.timedelta(minutes=5)
    db.session.add(p)
    db.session.commit()
    return p


def test_exactly_one_winner_among_concurrent_claimers(app):
    with app.app_context():
        p = _mk_due_post("win")
        # 模拟 N 个 worker 的调度线程先后/同时认领同一篇：只有第一个赢
        results = [claim_scheduled_post(p.id) for _ in range(4)]
        assert results == [True, False, False, False]
        db.session.refresh(p)
        assert p.published is True
        assert p.scheduled_at is None


def test_loser_leaves_post_untouched(app):
    """输家不能改动数据 —— 否则「已发布」状态会被第二条线程重复写。"""
    with app.app_context():
        p = _mk_due_post("loser")
        assert claim_scheduled_post(p.id) is True
        before = (p.published, p.scheduled_at)
        assert claim_scheduled_post(p.id) is False
        db.session.refresh(p)
        assert (p.published, p.scheduled_at) == before


def test_already_published_post_is_never_claimed(app):
    """幂等：已手动发布的文章不会被调度重复认领（避免二次推送）。"""
    with app.app_context():
        p = _mk_due_post("published")
        p.published = True
        p.scheduled_at = None
        db.session.commit()
        assert claim_scheduled_post(p.id) is False


def test_claim_only_affects_target_post(app):
    with app.app_context():
        a = _mk_due_post("a")
        b = _mk_due_post("b")
        assert claim_scheduled_post(a.id) is True
        db.session.refresh(b)
        assert b.published is False          # 别被顺带发布
        assert claim_scheduled_post(b.id) is True
