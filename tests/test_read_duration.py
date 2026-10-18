"""v4.5.0 阅读时长（`read_log.duration`）全链路。

三处最容易写错的地方，都是本文件的存在理由：

1. **`add_read_duration` 绝不能动 `read_count`**。停留时长会在切后台、
   跳下一篇文章时多次补报，若复用同一入口累加，读者读一次会被记成两三次，
   热门文章榜与「反复阅读」榜双双虚高。
2. **平均值的分母是 `SUM(read_count)` 而不是 `COUNT(*)`**。`ReadLog` 一行代表
   「一个访客对一篇的累计」，行数是访客数；用 `COUNT(*)` 会把均值压到 1/N。
3. **`duration = 0` 的行不得进分母**。升级前的历史阅读 duration 全为 0，
   计进去会让"人均阅读时长"刚上线就是 0.3 秒。

⚠️ 最后一条测试直接渲染 `/admin/stats` 断言页面上真的有那张卡：
v4.2.0 曾把三张卡写在 `{% block content %}` 外，Jinja 子模板里 block 外的
内容**不渲染** —— 静默丢失、无报错无日志，只测接口永远发现不了。
"""
import secrets

import pytest

from models import db, Post, ReadLog, User, ROLE_SUPER
from stats import (record_read, add_read_duration, _avg_read_seconds,
                   _clamp_read_seconds)

_MAX_SECONDS = 7200


@pytest.fixture
def super_user(app):
    with app.app_context():
        u = User(username="rd-" + secrets.token_hex(4),
                 email="rd-%s@test.local" % secrets.token_hex(4))
        u.set_password("x")
        u.role = ROLE_SUPER
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        return u.id


def _mk_post():
    slug = "rd-" + secrets.token_hex(4)
    p = Post(title="阅读时长测试", slug=slug, content="body", published=True)
    db.session.add(p)
    db.session.commit()
    return p


def _wipe_durations():
    """测试库全 session 共享，清掉全部时长避免跨用例耦合。"""
    ReadLog.query.delete()
    db.session.commit()


# ---------- 钳制：客户端上报不可信 ----------


def test_clamp_rejects_and_bounds():
    assert _clamp_read_seconds(None) == 0
    assert _clamp_read_seconds("abc") == 0
    assert _clamp_read_seconds(-5) == 0
    assert _clamp_read_seconds(0) == 0
    assert _clamp_read_seconds(120) == 120
    # 伪造的超大值必须被夹住，否则一个请求就能把均值抬到任意值
    assert _clamp_read_seconds(999999) == _MAX_SECONDS


# ---------- 累加语义 ----------


def test_record_read_accumulates_duration(app):
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        ip = "10.1.1.1"
        record_read(p.id, ip, 30)
        record_read(p.id, ip, 45)
        row = ReadLog.query.filter_by(post_id=p.id, ip=ip).first()
        assert row.read_count == 2, "两次阅读应累加 read_count"
        assert row.duration == 75, "时长应累加（30+45）"
        _wipe_durations()


def test_add_read_duration_never_touches_read_count(app):
    """守卫 1：补报时长**不得**增加 read_count。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        ip = "10.2.2.2"
        record_read(p.id, ip)          # 打开一次，不带时长
        before = ReadLog.query.filter_by(post_id=p.id, ip=ip).first().read_count
        add_read_duration(p.id, ip, 60)
        add_read_duration(p.id, ip, 30)
        row = ReadLog.query.filter_by(post_id=p.id, ip=ip).first()
        assert row.read_count == before, \
            "补报时长把 read_count 从 %s 改成了 %s" % (before, row.read_count)
        assert row.duration == 90, "两次分段补报应累加成 90"
        _wipe_durations()


def test_add_read_duration_ignores_missing_row(app):
    """没有阅读记录就不该凭空造行 —— 否则时长会挂在不存在的阅读上。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        add_read_duration(p.id, "10.3.3.3", 120)
        assert ReadLog.query.filter_by(post_id=p.id, ip="10.3.3.3").count() == 0
        _wipe_durations()


def test_add_read_duration_ignores_tiny_and_absurd(app):
    """钳制在补报路径上同样生效：0 秒不写，超上限被夹。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        ip = "10.4.4.4"
        record_read(p.id, ip)
        add_read_duration(p.id, ip, 0)
        assert ReadLog.query.filter_by(post_id=p.id, ip=ip).first().duration == 0
        add_read_duration(p.id, ip, 10 ** 9)
        assert ReadLog.query.filter_by(
            post_id=p.id, ip=ip).first().duration == _MAX_SECONDS
        _wipe_durations()


# ---------- 均值口径 ----------


def test_avg_uses_sum_read_count_not_row_count(app):
    """守卫 2：分母必须是 SUM(read_count)。

    A 读 3 次共 30 秒，B 读 1 次 30 秒 → 正确均值 60/4 = 15 秒。
    若误用 COUNT(*)=2 行，会得 60/2 = 30 秒 —— 恰好是这个值。
    """
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        for _ in range(3):
            record_read(p.id, "10.5.5.1", 10)
        record_read(p.id, "10.5.5.2", 30)
        assert _avg_read_seconds() == 15, \
            "分母用了行数而不是阅读次数，均值翻倍了"
        _wipe_durations()


def test_avg_excludes_zero_duration_rows(app):
    """守卫 3：duration=0 的历史行不得进分母。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        record_read(p.id, "10.6.6.1")            # 老数据：10 次阅读，0 秒
        for _ in range(10):
            record_read(p.id, "10.6.6.1")
        record_read(p.id, "10.6.6.2", 60)       # 新数据：1 次，60 秒
        assert _avg_read_seconds() == 60, \
            "零时长历史行进了分母，把均值压了下来"
        _wipe_durations()


def test_avg_zero_when_no_timing_data(app):
    """纯计数（无任何时长上报）时返回 0，而不是崩溃或返回 None。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        record_read(p.id, "10.7.7.1")
        assert _avg_read_seconds() == 0
        _wipe_durations()


# ---------- API 层：only_duration ----------


def test_api_only_duration_does_not_add_read(app, client):
    """走 HTTP 接口补报时长，read_count 必须不变（守卫 1 的端到端版）。"""
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        slug = p.slug
        ip_before = ReadLog.query.filter_by(post_id=p.id).count()
    r = client.post("/api/stats/read", json={"slug": slug})
    assert r.status_code == 200
    with app.app_context():
        pid = Post.query.filter_by(slug=slug).first().id
        after_open = ReadLog.query.filter_by(post_id=pid).first().read_count
        client.post("/api/stats/read", json={
            "slug": slug, "duration": 45, "only_duration": True})
        row = ReadLog.query.filter_by(post_id=pid).first()
        assert row.read_count == after_open, \
            "only_duration=True 却把 read_count 加了"
        assert row.duration == 45
        assert ReadLog.query.filter_by(post_id=pid).count() == ip_before + 1
        _wipe_durations()


# ---------- 页面渲染（v4.2.0 的静默丢失就栽在这里）----------


def test_stats_page_renders_avg_read_card(app, client, super_user):
    with app.app_context():
        _wipe_durations()
        p = _mk_post()
        record_read(p.id, "10.8.8.1", 125)   # 2 分 5 秒
        with client.session_transaction() as sess:
            sess["user_id"] = super_user
        html = client.get("/admin/stats").get_data(as_text=True)
        _wipe_durations()
    assert "平均单次阅读时长" in html, \
        "统计页没有渲染平均阅读时长卡片（模板可能写在 block 之外）"
    assert "2分5秒" in html, "时长应格式化成 X分Y秒"