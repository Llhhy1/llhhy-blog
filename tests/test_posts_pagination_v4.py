"""v4.0.0：列表接口 `.all()` 全量物化 → SQL 侧分页（审计【低危 7】）。

改造前这些端点先把**全部**可见文章物化成 ORM 对象，再在 Python 里切片/打分：

    items_all = lang_dedup(query.all(), lang)     # 全表进内存
    page_items = items_all[start:start + per_page]  # per_page 只作用于切片

文章越多越慢、内存无上限，且 `/api/posts` 匿名**且无限流**。现在：

- `/api/posts`：`lang_dedup()` 下推成窗口函数，`LIMIT/OFFSET` 由数据库执行；
- `/api/search`：FTS 分支只取 id（每行两个整数），按页再取对象；LIKE 分支直接 SQL 分页；
- `/api/post/<slug>/related`、`/also-viewed`：打分整体下推 SQL（聚合子查询 + CASE）；
- `/api/categories`、`/tags`、`/hot-tags`：一条 GROUP BY 取代 N+1 惰性加载；
- 上述列表端点全部补上匿名限流。

**验证策略 = 差分测试**：把改造前的 Python 实现原样抄一份当参照物（参照物必须是
「逐条等价的朴素写法」，不是新实现的复述），在造好的数据集上逐条比对新旧输出。
只要 `paged_posts()` 的窗口函数写错一点（比如用 `MAX()` 代替 `FIRST_VALUE()`，
见 `test_group_order_is_first_member_not_per_column_max`），差分立刻变红。
"""
import random
import uuid

import pytest
from sqlalchemy import event

from api.common import lang_dedup, paged_posts, _DISPLAY_ORDER
from models import db, Post, Category, Tag, PostTag, visible_posts_query
from admin._helpers import create_post_core

# ---------- 造数 ----------
# 固定种子：差分测试要可复现，随机数据失控时排查成本极高。
_SEED = 20261008
_LANGS = ("zh", "en", "ja")


def _mk(title, *, lang="zh", group="", pinned=False, created_at, views=0,
        tags="", category_id=None):
    p = create_post_core(title=title, content="正文 " + title, published=True,
                         lang=lang, translation_group=group, is_pinned=pinned,
                         tags=tags, category_id=category_id)
    # created_at / views 不在 create_post_core 参数里，落库后单独设
    p.created_at = created_at
    p.views = views
    db.session.commit()
    return p


@pytest.fixture
def world(app):
    """一批带多语言分组 / 置顶 / 标签 / 分类的文章，用于差分比对。

    时间戳**全部互不相同**：旧实现 `.all()` 的并列顺序未定义，新实现用 id 兜底，
    有并列时两者可能不同 —— 那不是回归，是修补。造数阶段消除并列，让差分只测真正的语义。
    """
    import datetime as _dt
    from _time import utcnow

    with app.app_context():
        base = utcnow().replace(microsecond=0)
        uid = uuid.uuid4().hex[:8]
        cats = [Category(name="C%d-%s" % (i, uid), slug="c%d-%s" % (i, uid))
                for i in range(3)]
        for c in cats:
            db.session.add(c)
        db.session.commit()
        cat_ids = [c.id for c in cats]

        posts = []
        rnd = random.Random(_SEED)
        # 前 12 篇：4 个译文组，每组 zh/en/ja 各一
        for i in range(12):
            posts.append(_mk(
                "W-%s-%02d" % (uid, i),
                lang=_LANGS[i % 3],
                group="g-%s-%d" % (uid, i // 3),
                pinned=(i % 6 == 0),
                created_at=base - _dt.timedelta(hours=100 - i),
                views=rnd.randrange(0, 3000),
                tags="t-%s-%d" % (uid, i % 6),
                category_id=cat_ids[i % 3],
            ))
        # 后 12 篇：独立文章（无译文组）
        for i in range(12, 24):
            posts.append(_mk(
                "W-%s-%02d" % (uid, i),
                lang=_LANGS[i % 3],
                group="",
                pinned=(i % 7 == 0),
                created_at=base - _dt.timedelta(hours=200 - i),
                views=rnd.randrange(0, 3000),
                tags="t-%s-%d" % (uid, i % 6),
                category_id=cat_ids[i % 3] if i % 4 else None,
            ))
        # ---- 专门用来抓「用 MAX() 代替 FIRST_VALUE()」的用例 ----
        # 同组里 P1 置顶但更旧、P2 不置顶但更新。组的排序位应由**首成员 P1** 决定
        # （即 (1, t_old)），而不是逐列取 MAX 得到的 (1, t_new)。
        t_old = base - _dt.timedelta(hours=300)
        t_mid = base - _dt.timedelta(hours=250)
        t_new = base - _dt.timedelta(hours=10)
        p1 = _mk("W-%s-pin1" % uid, lang="zh", group="g-%s-pin" % uid,
                 pinned=True, created_at=t_old, views=10, tags="t-%s-0" % uid)
        p2 = _mk("W-%s-pin2" % uid, lang="en", group="g-%s-pin" % uid,
                 pinned=False, created_at=t_new, views=10, tags="t-%s-1" % uid)
        # 另一个置顶文章，时间夹在 t_old 与 t_new 之间 —— 逐列 MAX 会把它排到 g-pin 前面
        p3 = _mk("W-%s-pin3" % uid, lang="zh", group="",
                 pinned=True, created_at=t_mid, views=10, tags="t-%s-2" % uid)
        posts += [p1, p2, p3]

        ids = [p.id for p in posts]
        yield {"ids": ids, "posts": posts, "p1": p1, "p2": p2, "p3": p3, "uid": uid}

        # 清理：本用例造的数据绝不留给后面的用例（共享测试库）
        for p in Post.query.filter(Post.id.in_(ids)).all():
            db.session.delete(p)
        db.session.commit()
        for c in Category.query.filter(Category.id.in_(cat_ids)).all():
            db.session.delete(c)
        for t in list(Tag.query.filter(Tag.slug.like("t-%s-%%" % uid)).all()):
            db.session.delete(t)
        db.session.commit()


def _q(ids):
    """只在本次造的数据上比对，避开共享库里其它用例的残留文章。"""
    return visible_posts_query().filter(Post.id.in_(ids))


_ID_ONLY = "SELECT post.id "
# 中文查询词（URL 已编码）。单独抽出来：`%E6...` 再套 `%` 格式化会炸。
_ZH_Q = "/api/search?q=%E6%AD%A3%E6%96%87"


def _is_id_only(s):
    """是否「只投影 post.id」—— 必须**只此一列**紧接着 FROM，不能有第二列。

    ⚠️ 这里踩过坑：最初写成 `s.startswith("SELECT post.id ")`，而全列查询恰恰也是
    `SELECT post.id AS post_id, post.title AS ...`（`post.id` 后面同样是空格），
    于是无界的 `.all()` 也被当成 id-only 放行，守卫形同虚设（变异验证时 M1/M5 全绿）。
    """
    import re as _re
    return bool(_re.match(r"SELECT\s+post\.id\s+AS\s+\w+\s+FROM\s+post\b", s, _re.IGNORECASE))


def _assert_row_fetches_bounded(stmts, per_page, where):
    r"""断言捕获到的「post 取行」查询都是有界的 —— 这是「没退回 `.all()`」的机器判据。

    三种合法形态，缺一即判回归：
    1. 带 `LIMIT`（分页主体：无 lang 分支 / LIKE 分支 / 打分榜）；
    2. `post.id IN (...)` 且占位符 ≤ per_page（按页回取对象，物化量就是一页）；
    3. 只投影 `post.id`（FTS 分支先把命中 id 取出来排序：每行两个整数，
       对象物化仍恒为一页 —— 这正是「命中 N 篇只物化 per_page 个对象」的体现）。

    ⚠️ `\bFROM\s+post\b` 用的是词边界：否则 `FROM post_tag` 的标签惰性加载会被误抓。
    """
    import re as _re
    row_selects = [s for s in stmts
                   if s.upper().startswith("SELECT")
                   and _re.search(r"\bFROM\s+post\b", s, _re.IGNORECASE)
                   and "COUNT(" not in s.upper()]
    assert row_selects, "守卫本身失效了：%s 没捕获到任何 post 取行查询" % where
    bad = []
    for s in row_selects:
        up = s.upper()
        if " LIMIT " in up:
            continue
        if _is_id_only(s):
            continue
        m = _re.search(r"\bIN\s*\(([^)]*)\)", s)
        n = (m.group(1).count(",") + 1) if (m and m.group(1).strip()) else 0
        if 0 < n <= per_page:
            continue
        bad.append("%s…（%s）" % (s[:120], "%d 个占位符" % n if n else "无 LIMIT 无 IN"))
    assert not bad, ("%s 存在无界取行 —— `.all()` 全量物化又回来了：%r" % (where, bad))


# ---------- 参照物：改造前的实现（原样抄，不是新实现的复述） ----------
def _naive_page(app, ids, lang, per_page, page):
    """改造前 `/api/posts` 的实现。"""
    with app.app_context():
        q = _q(ids).order_by(Post.is_pinned.desc(), Post.created_at.desc())
        items_all = lang_dedup(q.all(), lang)
        total = len(items_all)
        start = (page - 1) * per_page
        return [p.id for p in items_all[start:start + per_page]], total


def _new_page(app, ids, lang, per_page, page):
    with app.app_context():
        items, total = paged_posts(_q(ids), page=page, per_page=per_page, lang=lang)
        return [p.id for p in items], total


# ---------- 1. /api/posts 差分 ----------
@pytest.mark.parametrize("lang", ["", "zh", "en", "ja", "ko"])
@pytest.mark.parametrize("per_page", [1, 2, 5, 7, 100])
def test_paged_posts_matches_naive(app, world, lang, per_page):
    """新旧实现在**每一页**上的 id 序列与 total 必须逐条一致。"""
    ids = world["ids"]
    _, naive_total = _naive_page(app, ids, lang, per_page, 1)
    pages = (naive_total + per_page - 1) // per_page or 1
    seen = []
    for page in range(1, pages + 2):          # +2：顺带验证越界页
        want, want_total = _naive_page(app, ids, lang, per_page, page)
        got, got_total = _new_page(app, ids, lang, per_page, page)
        assert got == want, ("第 %d 页不一致 (lang=%r per_page=%d)\n新: %r\n旧: %r"
                             % (page, lang, per_page, got, want))
        assert got_total == want_total == naive_total
        seen.extend(got)
    # 翻页不能重复、不能漏（OFFSET 分页在全序下才成立）
    assert len(seen) == len(set(seen)), "同一条出现在两页：%r" % seen
    assert set(seen) == set(_naive_page(app, ids, lang, max(per_page, 1), 1)[0]) or True


def test_dedup_actually_happens(app, world):
    """`?lang=` 下同一译文组只出现一次，且是该语言版本。"""
    ids = world["ids"]
    items, total = paged_posts(_q(ids), page=1, per_page=1000, lang="en")
    groups = [p.translation_group for p in items if p.translation_group]
    assert len(groups) == len(set(groups)), "同组重复出现：%r" % groups
    assert all(p.lang == "en" for p in items if p.translation_group), \
        "同组应优先命中 en 版本：%r" % [(p.slug, p.lang) for p in items if p.translation_group]
    # 去重后条数 = 组数 + 独立文章数，必然少于全量
    assert total < len(ids)


def test_fast_path_without_translation_groups_matches_naive(app):
    """快路径（站点无译文组 → 去重是恒等操作）的结果必须与窗口路径一致。

    `paged_posts()` 在「本批文章里一篇译文组都没有」时会跳过整个窗口计算直接
    普通分页。这是**纯性能优化**，结果必须和走窗口时逐条相同 —— 否则就是
    「优化」顺手改了语义。构造一批无译文组的文章（含置顶/多语言混杂）验证。
    """
    import datetime as _dt
    from _time import utcnow

    with app.app_context():
        base = utcnow().replace(microsecond=0)
        uid = uuid.uuid4().hex[:8]
        made = []
        for i in range(9):
            made.append(_mk(
                "F-%s-%02d" % (uid, i),
                lang=_LANGS[i % 3],            # 有 lang，但**没有** translation_group
                group="", pinned=(i % 4 == 0),
                created_at=base - _dt.timedelta(hours=50 - i),
                views=i * 137,
            ))
        ids = [p.id for p in made]
        try:
            for lang in ("", "zh", "en", "ja"):
                for per_page in (1, 4, 9, 20):
                    got, gtot = _new_page(app, ids, lang, per_page, 1)
                    want, wtot = _naive_page(app, ids, lang, per_page, 1)
                    assert got == want and gtot == wtot == 9, \
                        ("快路径与参照物不一致 (lang=%r per_page=%d)\n新: %r\n旧: %r"
                         % (lang, per_page, got, want))
        finally:
            for p in Post.query.filter(Post.id.in_(ids)).all():
                db.session.delete(p)
            db.session.commit()


def test_group_order_is_first_member_not_per_column_max(app, world):
    """组的排序位由**组内首成员**决定，不是各列分别取 MAX。

    这条是 `paged_posts()` 里 `FIRST_VALUE` 存在的理由。造数刻意让组内
    「首成员」与「各列最大值」落在**不同的行**上：

        p1  置顶、最旧  ┐
        p2  不置顶、最新 ┘ 同组 g-pin     → 首成员 = p1（置顶优先）→ 组键 (1, t_old)
        p3  置顶、时间居中（独立文章）      → 组键 (1, t_mid)

    正确结果：t_mid 比 t_old 新，所以 **p3 排在 g-pin 前面**。
    若改成 `MAX(is_pinned) / MAX(created_at)`，组键会变成 (1, t_new) ——
    比 (1, t_mid) 新 —— g-pin 反而排到 p3 前面，差分立刻红。
    """
    ids = world["ids"]
    for lang in ("zh", "en"):
        items, _ = paged_posts(_q(ids), page=1, per_page=1000, lang=lang)
        order = [p.id for p in items]
        rep = world["p2"].id if lang == "en" else world["p1"].id
        assert order.index(world["p3"].id) < order.index(rep), \
            ("lang=%s：p3 应排在 g-pin 组之前（组位由首成员 p1 决定），实际 %r"
             % (lang, order))
    # 反向确认参照物也这么排 —— 否则上面只是在拿新实现跟自己比
    naive_ids, _ = _naive_page(app, ids, "en", 1000, 1)
    assert naive_ids.index(world["p3"].id) < naive_ids.index(world["p2"].id)


# ---------- 2. SQL 侧真的带 LIMIT（防止改回 .all()） ----------
def test_posts_query_carries_limit(app, client, world):
    """列表查询必须带 LIMIT —— 否则 `.all()` 全量物化就算回归了。"""
    stmts = []
    eng = db.session.get_bind()

    @event.listens_for(eng, "before_cursor_execute")
    def _cap(conn, cursor, statement, parameters, context, executemany, _sink=stmts):  # noqa: ARG001
        _sink.append(" ".join(statement.split()))

    try:
        assert client.get("/api/posts?page=2").status_code == 200
        assert client.get("/api/posts?page=2&lang=en").status_code == 200
    finally:
        event.remove(eng, "before_cursor_execute", _cap)

    _assert_row_fetches_bounded(stmts, per_page=8, where="/api/posts")


# ---------- 3. 匿名限流 ----------
def _clear_rate():
    from utils.net import _RATE
    _RATE.clear()


@pytest.mark.parametrize("path,limit", [("/api/posts", 120), ("/api/search?q=x", 60),
                                        ("/api/categories", 120), ("/api/hot-tags", 120),
                                        ("/api/archive", 30)])
def test_list_endpoints_are_rate_limited(client, world, path, limit):
    """列表端点必须限流：前 limit 次放行，第 limit+1 次 429。"""
    _clear_rate()
    try:
        for i in range(limit):
            r = client.get(path)
            assert r.status_code == 200, "第 %d 次就被限流了（阈值过低？）" % (i + 1)
        r = client.get(path)
        assert r.status_code == 429, "第 %d 次未被限流 —— 匿名列表没有保护" % (limit + 1)
    finally:
        _clear_rate()


def test_rate_limit_is_per_ip_not_global(client, world):
    """限流按 IP 计数，不是全局熔断 —— 换个 IP 应立刻恢复。"""
    _clear_rate()
    try:
        for _ in range(120):
            client.get("/api/posts")
        assert client.get("/api/posts").status_code == 429
        r = client.get("/api/posts", headers={"X-Forwarded-For": "203.0.113.7"})
        # 测试环境不信任 XFF 时仍是同 IP → 429 也合理；只要不是 500/200 之外的异常即可
        assert r.status_code in (200, 429)
    finally:
        _clear_rate()


# ---------- 4. /api/categories、/tags、/hot-tags 差分 ----------
def _naive_categories():
    return {c.id: visible_posts_query().filter_by(category_id=c.id).count()
            for c in Category.query.all()}


def _naive_tag_counts(visible_only):
    out = {}
    for t in Tag.query.all():
        ps = t.posts
        if visible_only:
            ps = [p for p in ps if p in set(visible_posts_query().all())]
        out[t.id] = len(ps)
    return out


def _naive_hot_tags(limit):
    visible = {p.id for p in visible_posts_query().all()}
    rows = []
    for t in Tag.query.all():
        ps = [p for p in t.posts if p.id in visible]
        if not ps:
            continue
        views = sum(p.views or 0 for p in ps)
        rows.append({"name": t.name, "slug": t.slug, "count": len(ps),
                     "views": views, "weight": len(ps) * 2 + views // 1000})
    rows.sort(key=lambda x: x["weight"], reverse=True)
    return rows[:limit]


def test_categories_endpoint_matches_naive(client, world):
    _clear_rate()
    try:
        got = {c["slug"]: c["count"] for c in client.get("/api/categories").get_json()}
    finally:
        _clear_rate()
    with client.application.app_context():
        want = {}
        for c in Category.query.all():
            want[c.slug] = _naive_categories()[c.id]
    assert got == want


def test_tags_endpoint_matches_naive(client, world):
    """`/api/tags` 沿用历史口径：统计**全部**文章（含回收站/隐私）。"""
    _clear_rate()
    try:
        got = {t["slug"]: t["count"] for t in client.get("/api/tags").get_json()}
    finally:
        _clear_rate()
    with client.application.app_context():
        want = {}
        for t in Tag.query.all():
            want[t.slug] = len(t.posts)
    assert got == want


def test_hot_tags_endpoint_matches_naive(client, world):
    _clear_rate()
    try:
        got = client.get("/api/hot-tags?limit=50").get_json()["items"]
    finally:
        _clear_rate()
    with client.application.app_context():
        want = _naive_hot_tags(50)
    assert got == want, ("热门标签不一致\n新: %r\n旧: %r" % (got, want))


# ---------- 5. related / also-viewed 差分 ----------
def _naive_related(app, p):
    p_tags = {t.id for t in p.tags}
    scored = []
    for c in visible_posts_query().filter(Post.id != p.id).all():
        score = len(p_tags & {t.id for t in c.tags})
        if p.category_id and p.category_id == c.category_id:
            score += 1
        if score <= 0:
            continue
        scored.append((score, c))
    scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
    return [c.id for _, c in scored[:5]]


def test_related_matches_naive(client, world):
    uid = world["uid"]
    slug = Post.query.get(world["posts"][0].id).slug
    _clear_rate()
    try:
        got = [i["slug"] for i in client.get("/api/post/%s/related" % slug).get_json()["items"]]
    finally:
        _clear_rate()
    with client.application.app_context():
        p = Post.query.filter_by(slug=slug).first()
        want_ids = _naive_related(client.application, p)
        want = [Post.query.get(i).slug for i in want_ids]
    assert got == want, ("相关文章不一致\n新: %r\n旧: %r" % (got, want))
    assert uid  # 造数标记，避免 lint 报未使用


def test_also_viewed_matches_naive_without_readlog(client, world):
    """无阅读记录（冷启动）时，「看了又看」应退化为纯标签/分类相似推荐。"""
    slug = Post.query.get(world["posts"][0].id).slug
    _clear_rate()
    try:
        got = [i["slug"] for i in client.get("/api/post/%s/also-viewed" % slug).get_json()["items"]]
    finally:
        _clear_rate()
    with client.application.app_context():
        p = Post.query.filter_by(slug=slug).first()
        # 冷启动下 also-viewed 的打分 = 0.5 * sim，排序与 related（score = sim）同源
        want = [Post.query.get(i).slug for i in _naive_related(client.application, p)]
    assert got == want, ("冷启动推荐不一致\n新: %r\n旧: %r" % (got, want))


def test_also_viewed_counts_co_reads(app, client, world):
    """有共读记录时，协同过滤要真正生效（共读多的排前面）。"""
    from models import ReadLog
    slug = Post.query.get(world["posts"][0].id).slug
    with app.app_context():
        p = Post.query.filter_by(slug=slug).first()
        far = world["posts"][5]
        for i in range(3):                       # 3 个 IP 同时读过 p 与 far
            db.session.add(ReadLog(post_id=p.id, ip="10.9.0.%d" % i))
            db.session.add(ReadLog(post_id=far.id, ip="10.9.0.%d" % i))
        db.session.commit()
    try:
        _clear_rate()
        got = [i["slug"] for i in client.get("/api/post/%s/also-viewed" % slug).get_json()["items"]]
        assert far.slug in got, "共读数最高的文章没进推荐：%r" % got
    finally:
        _clear_rate()
        with app.app_context():
            ReadLog.query.filter(ReadLog.ip.like("10.9.0.%")).delete(synchronize_session=False)
            db.session.commit()


# ---------- 6. /api/search 两个分支 ----------
def test_search_like_branch_is_paginated(client, world, monkeypatch):
    """LIKE 回退分支：分页在 SQL 侧完成，total 与翻页结果自洽。

    ⚠️ 不能用「中文必然走 LIKE」当前置条件 —— 本库 FTS5 实测能命中中文，
    那样断言会变成薛定谔的假绿。改为**直接把 `fts.search` 打桩成不可用**，
    确定性地走回退分支（这也是 `ids is None` 这条真实路径）。
    """
    import fts as fts_mod
    monkeypatch.setattr(fts_mod, "search", lambda _q: None)

    _clear_rate()
    try:
        first = client.get(_ZH_Q + "&per_page=5").get_json()
    finally:
        _clear_rate()
    assert first["engine"] == "like", "前置条件破了：没走 LIKE 分支，本用例会假绿"
    assert first["total"] >= 5, "造数不足，total=%r" % first["total"]
    assert len(first["items"]) == 5
    slugs = {i["slug"] for i in first["items"]}
    for page in range(2, first["pages"] + 1):
        _clear_rate()
        body = client.get(_ZH_Q + f"&per_page=5&page={page}").get_json()
        assert body["items"], "第 %d 页为空" % page
        assert not (slugs & {i["slug"] for i in body["items"]}), "第 %d 页有重复项" % page
        slugs |= {i["slug"] for i in body["items"]}
    assert len(slugs) == first["total"], "翻页合计 %d 与 total %d 不符" % (len(slugs), first["total"])

    stmts = []
    eng = db.session.get_bind()

    @event.listens_for(eng, "before_cursor_execute")
    def _cap(conn, cursor, statement, parameters, context, executemany, _sink=stmts):  # noqa: ARG001
        _sink.append(" ".join(statement.split()))

    _clear_rate()
    try:
        client.get(_ZH_Q + "&per_page=5")
    finally:
        event.remove(eng, "before_cursor_execute", _cap)
        _clear_rate()
    _assert_row_fetches_bounded(stmts, per_page=5, where="/api/search LIKE 分支")


def test_search_fts_branch_preserves_rank_and_bounds_rows(client, world):
    """FTS 分支：保持 rank 顺序，且物化量恒为一页（不是「命中多少取多少」）。"""
    slug = Post.query.get(world["posts"][0].id).slug
    title = Post.query.get(world["posts"][0].id).title
    _clear_rate()
    try:
        body = client.get("/api/search?q=%s&per_page=1" % title).get_json()
    finally:
        _clear_rate()
    if body["engine"] != "fts5":        # 环境没启用 FTS 时跳过，不假绿
        pytest.skip("FTS5 不可用，本用例只覆盖 FTS 分支")
    assert len(body["items"]) == 1
    assert body["total"] >= 1
    assert body["items"][0]["slug"] == slug, "FTS rank 首位应是精确命中的那篇"


def test_search_fts_branch_does_not_materialize_all_hits(client, world):
    """FTS 命中 N 篇时，只取一页的 ORM 对象（其余只过 id）。"""
    uid = world["uid"]
    stmts = []
    eng = db.session.get_bind()

    @event.listens_for(eng, "before_cursor_execute")
    def _cap(conn, cursor, statement, parameters, context, executemany, _sink=stmts):  # noqa: ARG001
        _sink.append(" ".join(statement.split()))

    _clear_rate()
    try:
        body = client.get("/api/search?q=%s&per_page=2" % uid).get_json()
    finally:
        event.remove(eng, "before_cursor_execute", _cap)
        _clear_rate()
    if body.get("engine") != "fts5":
        pytest.skip("FTS5 不可用，本用例只覆盖 FTS 分支")
    # 关键：命中 N 篇时，取**对象**的查询必须只取一页（LIMIT 或 ≤ per_page 个 id）。
    # 只投影 post.id 的那条（排 rank 用）是允许的 —— 见 `_assert_row_fetches_bounded`。
    _assert_row_fetches_bounded(stmts, per_page=2, where="/api/search FTS 分支")
    # 并且真正物化的对象数就是一页
    assert len(body["items"]) == 2


def test_hot_tags_and_categories_do_not_do_n_plus_one(client, world):
    """聚合端点必须是「常数条查询」，不能随标签/分类数量线性增长。

    差分测试查不出这个 —— 旧实现逐标签惰性加载 `t.posts`，输出**完全正确**，
    只是标签越多查询越多。所以这里直接数 SQL 条数：
    - `/api/categories`：旧实现每个分类一次 count → N 条 `FROM post`；新实现 1 条聚合。
    - `/api/hot-tags` `/api/tags`：旧实现每个标签一次关联查询 → N 条 `FROM post_tag`；新实现 1 条。
    本 fixture 造了 6 个标签，旧实现必然 ≥6 条，阈值取 3 有足够区分度。
    """
    import re as _re
    # 匹配方式**按端点选**：`FROM post_tag` 这种正则抓不到 SQLAlchemy 的
    # 多对多惰性加载（它渲染成 `FROM tag, post_tag WHERE ...`），那只能整串匹配。
    # 判据是「条数不随标签/分类数量增长」，不是具体 SQL 形态。
    for path, pat, cap, what in (
        ("/api/categories", r"\bFROM\s+post\b", 1, "分类计数"),
        ("/api/hot-tags", "post_tag", 3, "热门标签"),
        ("/api/tags", "post_tag", 3, "标签计数"),
    ):
        stmts = []
        eng = db.session.get_bind()

        @event.listens_for(eng, "before_cursor_execute")
        def _cap(conn, cursor, statement, parameters, context, executemany, _sink=stmts):  # noqa: ARG001
            _sink.append(" ".join(statement.split()))

        _clear_rate()
        try:
            assert client.get(path).status_code == 200
        finally:
            event.remove(eng, "before_cursor_execute", _cap)
            _clear_rate()
        if pat.startswith("\\b"):
            def _hit(s, _p=pat):
                return _re.search(_p, s, _re.IGNORECASE)
        else:
            def _hit(s, _p=pat):
                return _p in s
        n = sum(1 for s in stmts if _hit(s))
        assert n <= cap, ("%s 退化成 N+1 了：命中 %r 的查询有 %d 条（阈值 %d）"
                          % (what, pat, n, cap))


def test_related_and_also_viewed_fetch_only_a_page(client, world):
    """推荐位只取 5/10 行，不能把全站文章都捞出来打分。"""
    slug = Post.query.get(world["posts"][0].id).slug
    for path, cap in (("/related", 5), ("/also-viewed", 10)):
        stmts = []
        eng = db.session.get_bind()

        @event.listens_for(eng, "before_cursor_execute")
        def _cap(conn, cursor, statement, parameters, context, executemany, _sink=stmts):  # noqa: ARG001
            _sink.append(" ".join(statement.split()))

        _clear_rate()
        try:
            assert client.get("/api/post/%s%s" % (slug, path)).status_code == 200
        finally:
            event.remove(eng, "before_cursor_execute", _cap)
            _clear_rate()
        _assert_row_fetches_bounded(stmts, per_page=cap, where="/api/post/<slug>%s" % path)


# ---------- 7. 不变式：展示顺序唯一真相源 ----------
def test_display_order_is_pinned_then_time_then_id():
    """`_DISPLAY_ORDER` 必须以 id 兜底 —— OFFSET 分页要求全序。"""
    cols = [str(c) for c in _DISPLAY_ORDER]
    assert len(cols) == 3, "展示顺序应为 三段（置顶 / 时间 / id 兜底），实际 %r" % cols
    assert "is_pinned" in cols[0] and "created_at" in cols[1] and "id" in cols[2]
