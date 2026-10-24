"""v4.10.0 SPA 列表路径服务端 SEO 壳页（ROADMAP §3.1）。

此前 `/archive`、`/category/<slug>`、`/tag/<slug>` 这些路径对爬虫是一张
**共用同一套站点级默认 meta 的空壳**——搜索引擎看到的是一堆标题相同、
且没有任何实质内容的页面。本模块给它们补上服务端渲染的标题 / 描述 /
canonical / 文章列表。

覆盖的红线（每条单独可证伪）：

1. 认识的路径给 200 + index + **canonical 指向公开地址**（不是 /api/ 地址）。
2. **不认识的路径一律 404 + noindex** —— 绝不给通用兜底页，否则等于
   给爬虫无限多个内容雷同的 URL（重复内容是 SEO 自伤）。
3. **可见性口径与前台列表一致**：草稿 / 定时未到 / 回收站 / 隐私文章
   不得出现在任何列表里（漏一条就是隐私泄露 + 收录脏数据）。
4. 直敲 API（无 ?seo=1）→ 302；真人被误判 → 200 但 noindex（与文章页同闸门）。
5. 友链是外站 → `nofollow`（不能拿自己的权重给可编辑外链背书）。
"""

import secrets

import pytest

from models import (Category, FriendLink, Post, Series, Tag, db)
from _time import utcnow

UA_BAIDU = "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"
UA_WX_HUMAN = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
               "Mobile/15E148 MicroMessenger/8.0.40(0x18002823) NetType/WIFI Language/zh_CN")
HUMAN_HDRS = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
              "Sec-Fetch-Mode": "navigate"}


def _uid():
    return secrets.token_hex(4)


def _get(client, path, ua=UA_BAIDU, seo=True, headers=None):
    url = "/api/og/page/" + path.strip("/")
    if seo:
        url += "?seo=1"
    return client.get(url, headers=dict({"User-Agent": ua}, **(headers or {})))


def _mkpost(app, title=None, **kw):
    with app.app_context():
        p = Post(title=title or ("列表页探针-" + _uid()),
                 slug="sp-" + _uid(), content="正文", summary="摘要",
                 published=kw.pop("published", True),
                 in_trash=kw.pop("in_trash", False),
                 is_private=kw.pop("is_private", False), **kw)
        db.session.add(p)
        db.session.commit()
        pid, slug, t = p.id, p.slug, p.title
    return pid, slug, t


@pytest.fixture
def post(app):
    pid, slug, title = _mkpost(app)
    yield pid, slug, title
    with app.app_context():
        Post.query.filter(Post.id == pid).delete(synchronize_session=False)
        db.session.commit()


def test_归档页可被索引且列出文章标题(app, client, post):
    """判据是「标题真的在 HTML 里」，不是「返回 200」—— 空壳也返回 200。"""
    _pid, slug, title = post
    r = _get(client, "archive")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    body = r.get_data(as_text=True)
    assert "index" in (r.headers.get("X-Robots-Tag") or ""), "列表页必须可索引"
    assert title in body, "归档页没列出文章标题（等于还是空壳）"
    assert "/post/%s" % slug in body
    assert 'rel="canonical"' not in body


def test_canonical指向公开地址而非api地址(app, client, post):
    """canonical 若指向 /api/og/page/...，搜索引擎会把 API 地址当规范页收录。"""
    r = _get(client, "archive")
    body = r.get_data(as_text=True)
    assert "rel='canonical' href='/" in body or 'rel="canonical" href="/' in body, \
        "canonical 缺失或不是站内相对根路径：%s" % body[:200]
    assert "/api/og/page/" not in body, "canonical 指向了 API 地址"


def test_每个列表页有各自的标题和描述(app, client, post):
    """修的就是「所有列表页共用一套 meta」—— 三条路径的 title 必须互不相同。"""
    titles = set()
    for path in ("archive", "about", "links"):
        body = _get(client, path).get_data(as_text=True)
        t = body.split("<title>")[1].split("</title>")[0]
        titles.add(t)
    assert len(titles) == 3, "列表页标题重复：%s" % titles


def test_分类页用分类名做标题(app, client, post):
    pid, _slug, _title = post
    cslug = "cat-" + _uid()
    with app.app_context():
        c = Category(name="探针分类-" + _uid(), slug=cslug)
        db.session.add(c)
        db.session.commit()
        db.session.refresh(c)
        p = db.session.get(Post, pid)
        p.category_id = c.id
        db.session.commit()
        cname, cid = c.name, c.id
    try:
        r = _get(client, "category/" + cslug)
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert cname in body, "分类页没用分类名做标题"
        assert "分类" in body
    finally:
        with app.app_context():
            p = db.session.get(Post, pid)
            if p:
                p.category_id = None
            db.session.delete(db.session.get(Category, cid))
            db.session.commit()


def test_标签页与系列页(app, client, post):
    pid, _slug, _title = post
    tslug, sslug = "tag-" + _uid(), "ser-" + _uid()
    with app.app_context():
        t = Tag(name="探针标签-" + _uid(), slug=tslug)
        s = Series(name="探针系列-" + _uid(), slug=sslug)
        db.session.add_all([t, s])
        db.session.commit()
        db.session.refresh(t)
        db.session.refresh(s)
        p = db.session.get(Post, pid)
        p.tags.append(t)
        p.series_id = s.id
        db.session.commit()
        tname, sname, tid, sid = t.name, s.name, t.id, s.id
    try:
        assert tname in _get(client, "tag/" + tslug).get_data(as_text=True)
        assert sname in _get(client, "series/" + sslug).get_data(as_text=True)
    finally:
        with app.app_context():
            p = db.session.get(Post, pid)
            if p:
                p.series_id = None
                p.tags = []
            db.session.delete(db.session.get(Tag, tid))
            db.session.delete(db.session.get(Series, sid))
            db.session.commit()


# ------------------------------------------------------------- 不认识的路径


@pytest.mark.parametrize("path", [
    "unknown-page", "category", "tag", "series",
    "api/og/post/x", "admin/dashboard", "category/nonexistent-slug",
])
def test_不认识的路径返回404且noindex(client, path):
    """绝不给通用兜底页 —— 那会造出无限多个内容雷同的可索引 URL。"""
    r = _get(client, path)
    assert r.status_code == 404, "「%s」不该被服务（实得 %s）" % (path, r.status_code)
    assert "noindex" in (r.headers.get("X-Robots-Tag") or "")


# ------------------------------------------------------------- 可见性红线


@pytest.mark.parametrize("flag", ["published", "in_trash", "is_private"])
def test_不可见文章不出现在任何列表页(app, client, flag):
    """列表页与前台列表必须同一口径：草稿 / 回收站 / 隐私一律不露出。

    为什么单列一条：列表页是**新增**的出口，最容易漏掉可见性过滤——
    写完 `visible_posts_query()` 之后顺手加个 `.limit()` 看起来没问题，
    但只要哪天有人改成 `Post.query`，隐私文章标题就上了公网并被收录。
    """
    pid, slug, title = _mkpost(app, **{flag: True} if flag != "published" else {"published": False})
    try:
        body = _get(client, "archive").get_data(as_text=True)
        assert title not in body, "「%s」的文章出现在列表页（可见性口径不一致）" % flag
        assert slug not in body
    finally:
        with app.app_context():
            Post.query.filter(Post.id == pid).delete(synchronize_session=False)
            db.session.commit()


def test_定时未到的文章不出现(app, client):
    import datetime
    pid, slug, title = _mkpost(app, published=True,
                               scheduled_at=utcnow() + datetime.timedelta(days=3))
    try:
        body = _get(client, "archive").get_data(as_text=True)
        assert title not in body, "未来定时的文章提前出现在归档页"
    finally:
        with app.app_context():
            Post.query.filter(Post.id == pid).delete(synchronize_session=False)
            db.session.commit()


# ------------------------------------------------------------------ 闸门


def test_直敲api地址302回公开页(app, client, post):
    """无 ?seo=1 → 302。否则同一内容有两个可索引地址，canonical 会被稀释。"""
    r = _get(client, "archive", seo=False)
    assert r.status_code == 302, "不带 seo=1 的直敲应 302（实得 %s）" % r.status_code


def test_真人被误判时给可读页但noindex(app, client, post):
    """微信内置浏览器真人：能读到内容，但不进索引；且**绝不能 3xx**（会成环）。"""
    r = _get(client, "archive", ua=UA_WX_HUMAN, headers=HUMAN_HDRS)
    assert r.status_code == 200, "真人被误判时不能 3xx（nginx 会 rewrite 回来成环）"
    assert "noindex" in (r.headers.get("X-Robots-Tag") or ""), \
        "真人误判页必须 noindex，否则污染索引"


def test_友链外链带nofollow(app, client):
    """友链是站长可编辑的外站链接 —— 不给它传权重。"""
    fid = None
    with app.app_context():
        f = FriendLink(name="外链-" + _uid(), url="https://example.com/" + _uid(),
                       description="d", sort=0)
        db.session.add(f)
        db.session.commit()
        fid, fname = f.id, f.name
    try:
        body = _get(client, "links").get_data(as_text=True)
        assert fname in body
        assert "nofollow" in body, "友链外链没加 nofollow"
    finally:
        with app.app_context():
            db.session.delete(db.session.get(FriendLink, fid))
            db.session.commit()


def test_列表页有jsonld结构化数据(app, client, post):
    body = _get(client, "archive").get_data(as_text=True)
    assert "application/ld+json" in body
    assert "CollectionPage" in body, "列表页应声明为 CollectionPage 而非 BlogPosting"


def test_壳页禁止中间层缓存(app, client, post):
    """v4.10.1 线上事故回归：壳页**绝不能**允许缓存层缓存。

    壳页与真人 SPA 是**同一个 URL 的两种表示**，只靠 `Vary: User-Agent` 区分 —— 而
    `Vary` 只是建议，CDN 可以不理。v4.10.0 上线后实测：EdgeOne 明显不按 Vary 分桶，
    爬虫抓一次 `/archive` 后，**所有真人访客在 5 分钟里拿到的都是无样式壳页**
    （`eo-cache-status: HIT`、`age: 151`、响应里没有 `<div id="app">`）。

    判据：既要求 `no-store`，也要求**不出现** `public` / `max-age` —— 只查前者的话，
    将来有人写回 `public, max-age=300, no-store`（互相矛盾但含 no-store）会假绿。
    """
    r = _get(client, "archive")
    cc = (r.headers.get("Cache-Control") or "").lower()
    assert "no-store" in cc, "壳页必须 no-store，实得 %r" % cc
    assert "public" not in cc, "壳页不得声明 public（允许共享缓存）：%r" % cc
    assert "max-age" not in cc, "壳页不得声明 max-age：%r" % cc
    # Vary 仍要保留（对遵守规范的缓存层是双保险）
    assert "user-agent" in (r.headers.get("Vary") or "").lower(), "Vary 丢了 User-Agent"
