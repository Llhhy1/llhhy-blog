# -*- coding: utf-8 -*-
"""v5.3.3 审计回归：公开读路径不得泄露隐藏文章的译文/评论/计数。

覆盖四个曾经漏过滤的出口：
1. `GET /api/post/<slug>` 的 `translations[]`（同组私密/草稿/回收站译文）；
2. `hreflang_alternates()` → feed / sitemap 互链；
3. `GET /api/comments/reactions` 对私密文章评论的读取；
4. `/api/tags`、`/api/site` 的标签与统计计数。
"""
import uuid

from models import db, Post, Comment, Tag
from admin._helpers import create_post_core


def _uid():
    return uuid.uuid4().hex[:10]


def _post(**kw):
    kw.setdefault("content", "x")
    return create_post_core(**kw)


def _make_group():
    """公开 zh + 公开 en + 私密/草稿/回收站各一篇，同一 translation_group。"""
    g = "vis-" + _uid()
    zh = _post(title="PUB zh " + _uid(), published=True, lang="zh", translation_group=g)
    en = _post(title="PUB en " + _uid(), published=True, lang="en", translation_group=g)
    priv = _post(title="SECRET priv " + _uid(), published=True, lang="fr",
                 translation_group=g, is_private=True)
    draft = _post(title="SECRET draft " + _uid(), published=False, lang="de",
                  translation_group=g)
    trash = _post(title="SECRET trash " + _uid(), published=True, lang="ja",
                  translation_group=g)
    trash.in_trash = True
    db.session.commit()
    return {"g": g, "zh": zh.slug, "en": en.slug,
            "hidden": {priv.slug, draft.slug, trash.slug}}


def test_detail_translations_excludes_invisible_siblings(app, client):
    with app.app_context():
        ctx = _make_group()
    r = client.get("/api/post/" + ctx["zh"])
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    got = {t["slug"] for t in (r.get_json().get("translations") or [])}
    assert ctx["en"] in got, "公开译文应正常出现"
    assert not (got & ctx["hidden"]), "私密/草稿/回收站译文的 slug 泄露：%r" % (got & ctx["hidden"])


def test_hreflang_excludes_invisible_siblings(app):
    from models import hreflang_alternates
    with app.app_context():
        ctx = _make_group()
        p = Post.query.filter_by(slug=ctx["zh"]).first()
        urls = " ".join(u for _h, u in hreflang_alternates(p, "https://example.com"))
        for slug in ctx["hidden"]:
            assert slug not in urls, "hreflang 泄露隐藏译文：%s" % slug
        assert ctx["en"] in urls


def test_feed_and_sitemap_do_not_emit_hidden_translation(app, client):
    with app.app_context():
        ctx = _make_group()
    for path in ("/feed.xml", "/feed.atom", "/sitemap.xml"):
        body = client.get(path).get_data(as_text=True)
        for slug in ctx["hidden"]:
            assert slug not in body, "%s 泄露隐藏译文 slug：%s" % (path, slug)


def test_reactions_get_excludes_comments_on_hidden_posts(app, client):
    with app.app_context():
        pub = _post(title="REACT pub " + _uid(), published=True)
        priv = _post(title="REACT priv " + _uid(), published=True, is_private=True)
        c_pub = Comment(post_id=pub.id, author="a", content="public", approved=True)
        c_priv = Comment(post_id=priv.id, author="b", content="private", approved=True)
        db.session.add_all([c_pub, c_priv])
        db.session.commit()
        pub_id, priv_id = c_pub.id, c_priv.id

    r = client.get("/api/comments/reactions?ids=%d,%d" % (pub_id, priv_id))
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert str(pub_id) in items
    assert str(priv_id) not in items, "私密文章下的评论表情被匿名读取"


def test_tag_counts_only_include_visible_posts(app, client):
    name = "v533tag-" + _uid()
    with app.app_context():
        _post(title="TAG hidden " + _uid(), published=True, is_private=True, tags=name)
        tag = Tag.query.filter_by(name=name).first()
        assert tag is not None

    tags = client.get("/api/tags").get_json()
    row = next((t for t in tags if t["name"] == name), None)
    assert row is not None
    assert row["count"] == 0, "标签计数包含私密文章"

    with app.app_context():
        _post(title="TAG public " + _uid(), published=True, tags=name)
    tags2 = client.get("/api/tags").get_json()
    row2 = next(t for t in tags2 if t["name"] == name)
    assert row2["count"] == 1, "可见文章没有被计入标签数"


def test_site_stats_only_include_visible_posts(app, client):
    before = client.get("/api/site").get_json()
    b_posts = before["stats"]["posts"]
    b_views = before["stats"]["views"]
    b_comments = before["stats"]["comments"]
    with app.app_context():
        priv = _post(title="STAT priv " + _uid(), published=True, is_private=True)
        priv.views = 12345
        db.session.add(Comment(post_id=priv.id, author="x", content="hidden", approved=True))
        db.session.commit()
    after = client.get("/api/site").get_json()
    assert after["stats"]["posts"] == b_posts, "文章总数包含隐藏文章"
    assert after["stats"]["views"] == b_views, "总阅读量包含隐藏文章"
    assert after["stats"]["comments"] == b_comments, "评论总数包含隐藏文章下的评论"
