"""v4.5.0 访客属地排行排除爬虫。

背景：`_top_region()` 与 `_range_top("region", ...)` 此前只过滤空属地，漏了
`is_bot`。爬虫多为境外机房 IP，属地异步回填后会挤占真人省份的名次
（榜单里混进「美国· fremont」这类机房）。前台公开接口 `/api/geo/visitors`
（`api/review.py`）一直都有 `is_bot.is_(False)`，此处属**遗漏而非设计**。

⚠️ 两条纪律在本文件里是硬要求：
1. 测试库全 session 共享（见 conftest），断言一律用「包含 / 不包含」而非
   精确计数，避免跨用例耦合；
2. **必须写反向守卫**：只测正向时，「永远返回空列表」也能全绿。
   反向用例证明过滤真的来自 `human_only` 参数 / `is_bot` 条件本身。
"""
import secrets
from datetime import date as _date

from models import db, VisitLog
from _time import utcnow
from stats import _top_region, _range_top, compute_range_stats

# 刻意用现实中不存在的地名，避免与真实数据/其它用例撞名。
_HUMAN_REGION = "测试省·测试市"
_BOT_REGION = "测试邦·测试堡"


def _mk_visit(region, is_bot, on_date=None, path="/post/x"):
    vl = VisitLog(
        region=region, is_bot=is_bot, path=path,
        ip="10.%d.%d.%d" % (secrets.randbelow(255), secrets.randbelow(255),
                            secrets.randbelow(255)),
        hour=utcnow().hour,
        date=(on_date or _date.today()).isoformat())
    db.session.add(vl)
    db.session.commit()
    return vl


def _today():
    return _date.today().isoformat()


def test_top_region_excludes_bot(app):
    """属地 TOP（全部时间）：真人上榜、爬虫不上榜。"""
    with app.app_context():
        _mk_visit(_HUMAN_REGION, is_bot=False)
        _mk_visit(_BOT_REGION, is_bot=True)
        keys = {r["region"] for r in _top_region(limit=50)}
    assert _HUMAN_REGION in keys, "真人属地必须在榜，否则过滤条件写反了"
    assert _BOT_REGION not in keys, "爬虫属地不得进榜（本次修复的核心）"


def test_top_region_today_excludes_bot(app):
    """按日期过滤的属地 TOP 同样要排除爬虫（regions_today 走这条路径）。"""
    with app.app_context():
        _mk_visit(_HUMAN_REGION, is_bot=False, on_date=_date.today())
        _mk_visit(_BOT_REGION, is_bot=True, on_date=_date.today())
        keys = {r["region"] for r in
                _top_region(limit=50, date=_today())}
    assert _HUMAN_REGION in keys
    assert _BOT_REGION not in keys


def test_range_top_regions_excludes_bot(app):
    """v4.2.0 多区间统计的 top_regions 也必须排除爬虫。"""
    with app.app_context():
        _mk_visit(_HUMAN_REGION, is_bot=False)
        _mk_visit(_BOT_REGION, is_bot=True)
        keys = {r["key"] for r in compute_range_stats("today")["top_regions"]}
    assert _HUMAN_REGION in keys, "真人属地应在区间榜里"
    assert _BOT_REGION not in keys, "区间属地榜混入了爬虫"


def test_human_only_flag_is_effective(app):
    """反向守卫：同一个查询，不传 human_only 时爬虫属地**会**出现。

    没有这条，`human_only=True` 写成恒真（例如条件写反成 `is_bot == False`
    却因别处恒不成立而全绿）同样能通过正向用例。
    """
    with app.app_context():
        _mk_visit(_BOT_REGION, is_bot=True)
        s = e = _today()
        assert _BOT_REGION in {r["key"] for r in
                               _range_top("region", s, e, limit=50)}, \
            "不传 human_only 时应当不过滤，说明开关真的有作用"
        assert _BOT_REGION not in {r["key"] for r in
                                  _range_top("region", s, e, limit=50,
                                             human_only=True)}


def test_range_top_path_keeps_bot(app):
    """反向守卫：热门页面**不**排除爬虫。

    爬虫抓取本身就是真实热度（SEO 流量），跟着属地一起被过滤会低估
    热门文章 —— 过滤只应开在属地这一个维度上。
    """
    with app.app_context():
        _mk_visit(_BOT_REGION, is_bot=True, path="/post/bot-hit")
        s = e = _today()
        keys = {r["key"] for r in _range_top("path", s, e, limit=50)}
    assert "/post/bot-hit" in keys, "热门页面榜不应排除爬虫"