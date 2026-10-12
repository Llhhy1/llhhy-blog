# -*- coding: utf-8 -*-
"""v4.2.0 访客数据多区间 + 访客日志页 + 手动拉黑。

**本文件的核心是两条正确性回归**（都是「代码写了 ≠ 生效了」的高危形态）：

🔴 R1 `bot_guard_enabled=false`（默认关）时，手动拉黑的 IP 依然被 429 拦下。
     旧实现把 `check_bot_guard()` 整体放在 `if not guard_enabled(): return None`
     之后 → 开关默认关 → 后台「拉黑」按钮形同虚设。
🔴 R2 自动限流 `_record_block()` 不得把**手动永久拉黑**记录改短
     （否则永久封禁被一次限流触发悄悄降级成 30 分钟，reason 还被改写）。

其余覆盖：九档区间聚合的 PV/UV 边界、非法区间 key 回落、访客日志页
筛选/分页/权限、block_ip 拒绝非法 IP。
"""
import contextlib
import datetime
import secrets

import pytest

from models import db, User, Setting, VisitLog, BotBlock, ROLE_SUPER, ROLE_ADMIN
from stats import compute_range_stats, resolve_range, RANGE_PRESETS, DEFAULT_RANGE
import bot_guard

# 本文件专用 IP（TEST-NET-3 文档段 + 两个公网示例段），避免与其它用例冲突
_IPS = ("203.0.113.1", "203.0.113.2", "203.0.113.3", "203.0.113.4",
        "203.0.113.5", "203.0.113.6", "203.0.113.7", "203.0.113.77",
        "203.0.113.78", "203.0.113.9", "9.9.9.9", "8.8.8.8", "198.51.100.7")


@pytest.fixture(autouse=True)
def _clean_state(app):
    """会话级共享测试库：只清理本文件用到的 IP / 开关 / 限流计数，不污染其它用例。

    特别把 `bot_guard_enabled` 删掉（= 回落默认 false）：R1 要的就是
    「开关关闭」这个真实默认态，留一行 true 会让用例假红。
    """
    def _wipe():
        with app.app_context():
            BotBlock.query.filter(BotBlock.ip.in_(_IPS)).delete(
                synchronize_session=False)
            db.session.query(Setting).filter(
                Setting.key == "bot_guard_enabled").delete(
                synchronize_session=False)
            db.session.commit()
            with contextlib.suppress(Exception):
                from utils.net import _RATE
                _RATE.clear()
    _wipe()
    yield
    _wipe()


def _mkuser(app, role):
    with app.app_context():
        u = User(username="vl-" + secrets.token_hex(4),
                 email="vl-%s@t.local" % secrets.token_hex(4),
                 role=role, must_change_password=False)
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _mk_visit(**kw):
    vl = VisitLog(hour=kw.pop("hour", 12), post_id=None, **kw)
    db.session.add(vl)
    return vl


# ---------------------------------------------------------------- 区间聚合
def test_resolve_range_boundaries(app):
    """九档 key 的边界：今天/昨天是单日；近 N 天含今天；非法 key 回落默认。"""
    with app.app_context():
        today = datetime.date.today()
        k, s, e, label = resolve_range("today")
        assert (k, s, e) == ("today", today, today)
        k, s, e, label = resolve_range("yesterday")
        assert (k, e) == ("yesterday", today - datetime.timedelta(days=1))
        k, s, e, label = resolve_range("7d")
        assert (k, (e - s).days) == ("7d", 6) and e == today
        k, s, e, label = resolve_range("730d")
        assert (k, (e - s).days) == ("730d", 729)
        k, s, e, label = resolve_range("不存在的key")
        assert k == DEFAULT_RANGE == "7d"
        assert dict(RANGE_PRESETS)["15d"] == "近半月"


def test_range_stats_pv_uv_boundaries(app):
    """PV/UV 按区间精确切分；同 IP 重复访问 PV+1、UV+0；爬虫单独计数。

    用**增量**断言（先快照后加数据再比差值）—— 测试库全 session 共享，
    其它用例可能已写入今天的 VisitLog，绝对值不可信。
    """
    today = datetime.date.today()
    plan = [
        (today, "203.0.113.1", False),
        (today, "203.0.113.2", False),
        (today, "203.0.113.2", False),                        # 同 IP 第二次
        (today, "203.0.113.3", True),                         # 爬虫
        (today, "203.0.113.1", True),                         # 混合 IP：同一个 .1 又以爬虫身份来过
        (today - datetime.timedelta(days=6), "203.0.113.4", False),    # 7 天内
        (today - datetime.timedelta(days=7), "203.0.113.5", False),    # 7 天外/15 天内
        (today - datetime.timedelta(days=729), "203.0.113.6", False),  # 2 年内
        (today - datetime.timedelta(days=730), "203.0.113.7", False),  # 2 年外
    ]
    with app.app_context():
        b7, b15, b2y = (compute_range_stats(k) for k in ("7d", "15d", "730d"))
        by = compute_range_stats("yesterday")
        made = [_mk_visit(date=d.isoformat(), ip=ip, path="/vl-t", is_bot=bot)
                for d, ip, bot in plan]
        db.session.commit()
        ids = [v.id for v in made]
        try:
            a7, a15, a2y = (compute_range_stats(k) for k in ("7d", "15d", "730d"))
            ay = compute_range_stats("yesterday")
            # 近 7 天 = 今天 5 条 + 6 天前 1 条
            assert a7["pv"] - b7["pv"] == 6
            assert a7["uv"] - b7["uv"] == 4          # 4 个不同 IP
            assert a7["human_pv"] - b7["human_pv"] == 4
            assert a7["human_uv"] - b7["human_uv"] == 3
            assert a7["bot_pv"] - b7["bot_pv"] == 2
            # 混合 IP：.1 同时出现在真人与爬虫两侧 → bot_uv 必须是 2（.1 和 .3）。
            # 用「全部 UV - 真人 UV」减法会得到 4-3=1，正是这条断言要防的。
            assert a7["bot_uv"] - b7["bot_uv"] == 2
            # 昨天：本计划没有昨天的行 → 增量 0
            assert ay["pv"] - by["pv"] == 0
            # 近半月 = 近 7 天 + 7 天前 1 条
            assert a15["pv"] - b15["pv"] == 7
            assert a15["uv"] - b15["uv"] == 5
            # 近 2 年 = 近半月 + 729 天前 1 条（730 天前那条必须在窗外）
            assert a2y["pv"] - b2y["pv"] == 8
            assert a2y["uv"] - b2y["uv"] == 6
        finally:
            VisitLog.query.filter(VisitLog.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()


def test_range_stats_top_lists(app):
    """区间 TOP：路径 / 属地 / 来源（来源走 _label_referrer 归一）。"""
    today = datetime.date.today()
    with app.app_context():
        made = [
            _mk_visit(date=today.isoformat(), ip="203.0.113.1",
                      path="/vl-hot", region="广东", referrer=""),
            _mk_visit(date=today.isoformat(), ip="203.0.113.2",
                      path="/vl-hot", region="广东",
                      referrer="https://www.baidu.com/s?wd=x"),
            _mk_visit(date=today.isoformat(), ip="203.0.113.3",
                      path="/vl-hot", region="广东",
                      referrer="https://www.baidu.com/"),
        ]
        db.session.commit()
        ids = [v.id for v in made]
        try:
            a = compute_range_stats("7d")
            paths = {p["key"]: p["count"] for p in a["top_paths"]}
            regions = {r["key"]: r["count"] for r in a["top_regions"]}
            refs = {r["key"]: r["count"] for r in a["top_referrers"]}
            assert paths.get("/vl-hot", 0) >= 3
            assert regions.get("广东", 0) >= 3
            # 两条百度来源（不同 path）归一成同一个「百度」并合并计数
            assert refs.get("百度", 0) >= 2
        finally:
            VisitLog.query.filter(VisitLog.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()


# ---------------------------------------------------------------- 访客日志页
def test_visit_logs_requires_login(client):
    """未登录访问后台页 → 302 引导登录（与其它后台页一致）。"""
    assert client.get("/admin/visit-logs").status_code == 302


def test_visit_logs_lists_and_filters(app, client):
    """列表展示 + IP 筛选 + 类型筛选 + 区间筛选。"""
    admin = _mkuser(app, ROLE_ADMIN)
    _login(client, admin)
    today = datetime.date.today().isoformat()
    with app.app_context():
        made = [
            _mk_visit(date=today, ip="203.0.113.77", path="/vl-demo",
                      region="广东", is_bot=False, referrer=""),
            _mk_visit(date=today, ip="203.0.113.78", path="/vl-botpage",
                      is_bot=True, bot_name="VLBot", bot_category="tool"),
        ]
        db.session.commit()
        ids = [v.id for v in made]
    try:
        r = client.get("/admin/visit-logs?range=7d")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "203.0.113.77" in body and "/vl-demo" in body and "广东" in body

        r = client.get("/admin/visit-logs?range=7d&ip=203.0.113.77")
        assert r.status_code == 200 and "203.0.113.77" in r.get_data(as_text=True)

        r = client.get("/admin/visit-logs?range=7d&type=bot")
        assert r.status_code == 200
        assert "203.0.113.77" not in r.get_data(as_text=True)   # 真人行被滤掉
        assert "VLBot" in r.get_data(as_text=True)

        r = client.get("/admin/visit-logs?range=yesterday")
        assert r.status_code == 200
        assert "/vl-demo" not in r.get_data(as_text=True)       # 今天的行不在「昨天」
    finally:
        with app.app_context():
            VisitLog.query.filter(VisitLog.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()


def test_stats_page_renders_range_card(app, client):
    """`/admin/stats` 页面本身必须能渲染（含区间切换卡）。

    这条补的是覆盖盲区：此前只有 `/admin/stats/export` 被测试打过，
    **统计页模板本身从未被渲染过** —— 模板里一个语法错误就能让页面 500，
    而所有测试都是绿的。区间卡的关键元素（九档按钮、区间起止、六个指标）
    任一缺失都算回归。
    """
    admin = _mkuser(app, ROLE_ADMIN)
    _login(client, admin)
    r = client.get("/admin/stats?range=15d")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "区间访客数据" in body                      # 区间卡标题
    assert "近半月" in body and "近 2 年" in body       # 九档按钮（含默认回落项）
    assert "独立访客 UV（去重 IP）" in body             # 指标行
    assert "真人独立 IP" in body and "爬虫访问 PV" in body
    assert "/admin/visit-logs?range=15d" in body       # 去访客日志的联动链接
    assert "导出当前区间（15 天）" in body              # 导出按钮跟随区间
    # v4.2.0 顺带修掉的隐藏 bug：这三张卡原先放在 block 外，从未渲染过
    assert "环比（最近" in body
    assert "来源渠道 TOP（最近 30 天）" in body
    assert "导出访问明细" in body
    # 非法区间 key 必须回落默认 7d 而不是 500
    assert client.get("/admin/stats?range=乱码").status_code == 200


def test_block_via_admin_route_permissions(app, client):
    """超管可拉黑；普通管理员 403；写库 reason=manual。"""
    super_uid = _mkuser(app, ROLE_SUPER)
    _login(client, super_uid)
    r = client.post("/admin/visit-logs/block",
                    data={"ip": "203.0.113.5", "next": "/admin/visit-logs?range=7d"},
                    headers=_csrf(client))
    assert r.status_code == 302
    with app.app_context():
        rec = BotBlock.query.filter_by(ip="203.0.113.5").first()
        assert rec is not None and rec.reason == "manual" and rec.active is True
        assert rec.blocked_until == bot_guard._PERMANENT_UNTIL

    # 普通管理员（非超管）拉黑 → 403
    admin_uid = _mkuser(app, ROLE_ADMIN)
    _login(client, admin_uid)
    r = client.post("/admin/visit-logs/block",
                    data={"ip": "203.0.113.6"}, headers=_csrf(client))
    assert r.status_code == 403


# ---------------------------------------------------------------- 拉黑生效链路
def test_manual_block_effective_when_guard_disabled(app, client):
    """🔴 R1：反爬开关关闭（默认态）时，手动拉黑的 IP 依然 429。

    这条是旧实现的回归防线：`check_bot_guard()` 曾在 `guard_enabled()`
    判断之后才执行，开关默认 false → 黑名单从未生效过。
    """
    with app.app_context():
        assert bot_guard.guard_enabled() is False, "前置条件：开关必须是关闭态"
        ok, msg = bot_guard.block_ip("9.9.9.9")
        assert ok, msg

    r = client.get("/login", headers={"X-Forwarded-For": "9.9.9.9"})
    assert r.status_code == 429, "开关关闭时手动拉黑必须生效"
    assert r.headers.get("Retry-After") == "60"

    # 对照：没拉黑的 IP 正常放行（证明 429 确实来自黑名单而非全局故障）
    r2 = client.get("/login", headers={"X-Forwarded-For": "198.51.100.7"})
    assert r2.status_code == 200


def test_unblock_restores_access(app, client):
    """解封后同一 IP 恢复访问。"""
    with app.app_context():
        assert bot_guard.block_ip("8.8.8.8")[0]
    assert client.get("/login",
                      headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 429
    with app.app_context():
        assert bot_guard.unblock_ip("8.8.8.8") is True
    assert client.get("/login",
                      headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 200


def test_manual_block_not_shortened_by_auto_limit(app):
    """🔴 R2：自动限流不得把永久拉黑改短 / 改写 reason。"""
    with app.app_context():
        ok, _ = bot_guard.block_ip("203.0.113.9")
        assert ok
        before = BotBlock.query.filter_by(ip="203.0.113.9").first()
        assert before.reason == "manual"
        assert before.blocked_until == bot_guard._PERMANENT_UNTIL
        # 把命中次数推到封禁阈值（默认 3）以上：若没有「手动记录保护」，
        # 下面这次限流会把 blocked_until 覆盖成 now+30min（永久封禁被降级）。
        before.hit_count = max(int(before.hit_count), 5)
        db.session.commit()
        before_hits = int(before.hit_count)   # 先取 int：ORM 身份映射下前后是同一实例

        # 模拟该 IP 随后触发一次自动限流（tool 类阈值）
        bot_guard._record_block("203.0.113.9", "EvilBot", "tool", "rate_tool")

        after = BotBlock.query.filter_by(ip="203.0.113.9").first()
        assert after.reason == "manual", "自动限流不得改写手动拉黑的 reason"
        assert after.blocked_until == bot_guard._PERMANENT_UNTIL, \
            "永久封禁不得被自动限流改短"
        assert after.active is True
        assert int(after.hit_count) == before_hits + 1, "命中次数仍应累计（可观测）"


def test_block_ip_rejects_invalid(app):
    """非法 / 空 IP 拒绝入库。"""
    with app.app_context():
        ok, msg = bot_guard.block_ip("not-an-ip")
        assert ok is False and "203.0.113" not in msg
        assert BotBlock.query.filter_by(ip="not-an-ip").first() is None
        assert bot_guard.block_ip("")[0] is False
        assert bot_guard.block_ip("   ")[0] is False
