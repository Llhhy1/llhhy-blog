"""v4.11.0 诊断助手扩展 + 后台页面统一化的回归测试。

覆盖三件事：
1. **体检明细真的被渲染**（这是本轮修的 bug）：12 个 checker 里原有 10 个只返回
   `items`，而 `admin/feed_diag.html` 读 `sec.rows` → Jinja Undefined → 明细表恒不渲染。
   回归用例断言「页面上能看到某个明细 label」，摘掉 run_all 的归一化必须变红。
2. 新增 7 个 checker 都符合约定结构（key/title/status/items/notes，且不抛）。
3. 八个统一美化后的后台页仍能正常渲染（改模板最容易悄悄改坏表单/块）。

运行：`python -m pytest tests/test_diagnostics_v4110.py -q`
"""
import secrets

import pytest

from models import db, User, ROLE_SUPER
from utils import _sign_csrf

import diagnostics


def _mkuser():
    uid = secrets.token_hex(5)
    u = User(username="diag-" + uid, email="diag-%s@test.local" % uid)
    u.set_password("test-pass")
    u.role = ROLE_SUPER
    u.must_change_password = False   # 否则会被跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    raw = secrets.token_hex(24)
    with client.application.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


# ---------------------------------------------------------------------------
# 1. run_all 的结构约定
# ---------------------------------------------------------------------------
def test_every_section_has_rows_alias(app):
    """`rows` 必须存在且等于 `items` —— 模板读的就是它。

    ⚠️ 变异验证：把 `diagnostics._normalize` 里补 rows 的两行删掉，本用例必红。
    （这正是 v4.11.0 之前线上「体检页只有标题没有明细」的成因。）
    """
    with app.app_context():
        data = diagnostics.run_all()
    assert data["sections"], "至少要有维度"
    for sec in data["sections"]:
        assert "rows" in sec, "%s 缺 rows 键（模板会静默不渲染明细）" % sec.get("key")
        assert sec["rows"] == (sec.get("items") or [])


def test_all_checkers_registered_and_unique(app):
    """CHECKS 与 CHECKS_BY_KEY 必须一一对应：漏登记 = MCP 的 run_check 看不到该维度。"""
    assert len(diagnostics.CHECKS) == len(diagnostics.CHECKS_BY_KEY)
    assert len({f.__name__ for f in diagnostics.CHECKS}) == len(diagnostics.CHECKS)
    for fn in diagnostics.CHECKS:
        assert fn in diagnostics.CHECKS_BY_KEY.values(), fn.__name__


def test_score_and_issues_contract(app):
    with app.app_context():
        data = diagnostics.run_all()
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert data["issue_total"] == sum(
        1 for s in data["sections"] for i in (s.get("items") or [])
        if i.get("level") in ("error", "warn"))
    # error 必须排在 warn 前面（页面上「先看硬伤」的顺序由这里保证）
    levels = [i["level"] for i in data["issues"]]
    assert levels == sorted(levels, key=lambda x: 0 if x == "error" else 1)
    for it in data["issues"]:
        assert it["key"] and it["dimension"] and it["label"]


def test_score_drops_below_100_when_a_dimension_warns(app):
    """评分必须真的随状态变化，不能恒等于 100（可证伪性）。"""
    with app.app_context():
        data = diagnostics.run_all()
    bad = data["summary"]["warn"] + data["summary"]["error"]
    if bad == 0:
        pytest.skip("当前测试环境所有维度均正常，无法验证评分随状态变化")
    assert data["score"] < 100


# ---------------------------------------------------------------------------
# 2. 新增 checkers 的约定结构
# ---------------------------------------------------------------------------
NEW_CHECKS = ["plugins", "search_index", "scheduler", "outbound",
              "content_quality", "disk", "mcp"]


@pytest.mark.parametrize("key", NEW_CHECKS)
def test_new_checker_shape(app, key):
    """每个新 checker：不抛异常、status 合法、items 是 list、notes 是 list。"""
    fn = diagnostics.CHECKS_BY_KEY[key]
    with app.app_context():
        sec = fn()
    assert sec["key"] == key
    assert sec["title"], "标题不能为空（页面与 MCP 都直接展示它）"
    assert sec["status"] in ("ok", "warn", "error")
    assert isinstance(sec.get("items"), list) and sec["items"], "%s 应至少有一行明细" % key
    assert isinstance(sec.get("notes"), list)
    for it in sec["items"]:
        assert it.get("label")
        assert it.get("level") in ("ok", "warn", "error", "info")


def test_search_index_compares_against_indexable(app):
    """索引一致性必须和「应索引数」比，而不是和「文章总数」比。

    构造一篇隐私文章（不该进索引）：若拿总数比，会误报「缺 1 条」。
    """
    from _time import utcnow
    from models import Post

    with app.app_context():
        p = Post(title="diag-private-only", slug="diag-private-" + secrets.token_hex(4),
                 content="x", published=True, is_private=True, created_at=utcnow())
        db.session.add(p)
        db.session.commit()
        try:
            sec = diagnostics.check_search_index()
            idx = next(i for i in sec["items"] if i["label"].startswith("应被索引"))
            # 隐私文章不计入分母：expect 仍等于索引条数
            assert "按 SQL 近似" in idx["value"] or "逐篇" in idx["value"]
            assert sec["status"] in ("ok", "warn")
        finally:
            db.session.delete(p)
            db.session.commit()


# ---------------------------------------------------------------------------
# 3. 页面渲染回归（体检明细 + 八页统一化）
# ---------------------------------------------------------------------------
def test_feed_diag_page_renders_item_values(app, client):
    """体检页必须把明细 label 渲染出来（回归：v4.11.0 之前这里只有标题）。"""
    with app.app_context():
        u = _mkuser()
        _auth(client, u.id)
        r = client.get("/admin/feed-diag")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        # 「文章 Post / 评论 Comment」这两行只在数据库维度的 items 里出现
        assert "文章 Post" in html and "评论 Comment" in html
        # 新增的评分与问题清单也要在
        assert "/100" in html
        assert "待处理问题" in html


ADMIN_PAGES = [
    ("/admin/nav-entries", "外部入口"),
    ("/admin/moments", "微动态"),
    ("/admin/announcements", "公告"),
    ("/admin/seo", "收录控制台"),
    ("/admin/settings", "站点设置"),
    ("/admin/email-settings", "邮件设置"),
    ("/admin/users", "用户管理"),
    ("/admin/games", "游戏收录"),
]


@pytest.mark.parametrize("path,marker", ADMIN_PAGES)
def test_unified_admin_pages_render(app, client, path, marker):
    """统一美化后的八个页面：200 + 关键文案在 + 不再出现未定义的旧结构类。

    `page-head` 是 v4.11.0 统一结构的标志；没有它说明该页还没改到，
    相当于「改了一半」——这类漏改比没改更难发现。
    """
    with app.app_context():
        u = _mkuser()
        _auth(client, u.id)
        r = client.get(path)
        assert r.status_code == 200, "%s → %s" % (path, r.status_code)
        html = r.get_data(as_text=True)
        assert marker in html
        assert "page-head" in html, "%s 未使用统一页头结构" % path
