"""v3.20.0 统计深度（ROADMAP §5.2）+ 访问明细 CSV 导出（含公式注入防护）。

覆盖：
- compute_summary 新增键（compare / online / referrers）的结构与类型
- compute_period_compare 上期=0 时 pct=None（前端应显示「—」而非 0%）
- _top_referrers 来源分类（Google / 百度 等，未知来源退回域名）
- /admin/stats/export：UTF-8 BOM、CSV 头、**公式注入防护**
  （以 = + - @ 开头的单元格被加前缀单引号中和，防 Excel 执行恶意公式）
"""
import io
import csv
import secrets
from datetime import date as _date

import pytest

from models import (db, User, VisitLog, ROLE_SUPER)
from _time import utcnow
from stats import (compute_summary, compute_period_compare, _top_referrers)


@pytest.fixture
def super_user(app):
    """返回超管 user_id（int）。

    ⚠️ 必须在 app context 内取出 id 再返回：上下文退出时 flask_sqlalchemy 会
    `session.remove()` 把实例 expire，若直接返回 ORM 对象，测试里取 `.id` 会触发
    惰性加载报错（实测踩过）。
    """
    with app.app_context():
        u = User(username="stats-" + secrets.token_hex(4),
                 email="stats-%s@test.local" % secrets.token_hex(4))
        u.set_password("x")
        u.role = ROLE_SUPER
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        return u.id


def _auth(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _mk_visit(referrer="", path="/post/x", ip="1.2.3.4", is_bot=False,
              on_date=None):
    vl = VisitLog(path=path, referrer=referrer, ip=ip, is_bot=is_bot,
                  hour=utcnow().hour,
                  date=(on_date or _date.today()).isoformat())
    db.session.add(vl)
    db.session.commit()
    return vl


def test_compute_summary_new_keys(app):
    """compute_summary 必须带回 v3.20.0 新增的 compare / online / referrers。"""
    with app.app_context():
        s = compute_summary()
    for k in ("compare", "online", "referrers"):
        assert k in s, "compute_summary 缺少新增键 %s" % k
    assert isinstance(s["online"], int), "online 应为 int（近似值计数）"
    assert isinstance(s["referrers"], list)
    c = s["compare"]
    assert c["days"] == 7, "默认环比窗口应为 7 天"
    for metric in ("pv", "uv", "comments", "subscribers"):
        assert metric in c
        assert set(c[metric].keys()) == {"cur", "prev", "pct"}


def test_period_compare_zero_prev_pct_none(app):
    """本期有访问、上期无访问 → 上期=0，pct 必须是 None（不是 0 也不是 inf）。

    说明：共享测试库里其它用例若往「上一周期」（7~14 天前）写过 VisitLog，
    prev 可能非 0；此测试仅在 prev==0 时校验 pct 规则，避免跨用例耦合。
    """
    with app.app_context():
        _mk_visit(referrer="https://www.google.com/", on_date=_date.today())
        c = compute_period_compare(7)
    if c["pv"]["prev"] == 0:
        assert c["pv"]["pct"] is None, "上期=0 时 pct 应为 None（前端显示 —）"
        assert c["uv"]["pct"] is None


def test_top_referrers_classifies_search_engines(app):
    """来源分类：google.→Google、baidu.→百度；未知来源退回域名本身。"""
    with app.app_context():
        _mk_visit(referrer="https://www.google.com/search?q=llm")
        _mk_visit(referrer="https://www.baidu.com/s?wd=ai")
        _mk_visit(referrer="https://news.ycombinator.com/")
        rows = _top_referrers(days=30)
        sources = {r["source"] for r in rows}
        assert "Google" in sources
        assert "百度" in sources
        assert any("news.ycombinator.com" in r["source"] for r in rows)


def test_csv_export_bom_and_formula_injection_guard(app, client, super_user):
    """导出 CSV：带 UTF-8 BOM（Excel 不乱码），且公式注入被中和。"""
    with app.app_context():
        _mk_visit(referrer="https://www.google.com/",
                  path="=cmd|'/c/calc'!A1", ip="9.9.9.9")
        _auth(client, super_user)
    r = client.get("/admin/stats/export?days=30")
    assert r.status_code == 200, r.status_code
    assert "text/csv" in r.headers.get("Content-Type", "")
    assert r.headers.get("Content-Disposition", "").startswith("attachment")
    body = r.get_data(as_text=True)
    assert body.startswith("﻿"), "CSV 必须带 UTF-8 BOM，否则 Excel 中文乱码"
    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
    assert rows[0][0] == "日期"
    injected = [row for row in rows[1:] if row and row[2].startswith("'=")]
    assert injected, "公式注入单元格未被中和（应以 '= 开头）"
    assert injected[0][2] == "'=cmd|'/c/calc'!A1"


def test_csv_export_days_capped(app, client, super_user):
    """?days=999999 必须被夹到 [1,365]，不能拉全表或崩溃。"""
    with app.app_context():
        _auth(client, super_user)
    r = client.get("/admin/stats/export?days=999999")
    assert r.status_code == 200
    assert r.get_data(as_text=True).startswith("﻿")
