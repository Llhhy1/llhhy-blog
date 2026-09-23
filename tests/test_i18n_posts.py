"""内容多语言（M1 翻译配对，v3.21.0）测试。

覆盖：
1. hreflang_alternates：独立文章仅 x-default；同组译文输出各语言 + x-default。
2. lang_dedup：列表按 ?lang= 优先返回该语言版本（避免同组重复）。
3. 详情 ?lang= 解析：落到同组译文，回退规则正确；translations 字段列出其它语言。
4. 列表 ?lang= 去重：同组只出现一次且为请求语言。
5. sitemap / OG 壳页：输出 hreflang 互链 + 正确 <html lang>。
6. 后台表单：new_post / edit_post 落库 lang + translation_group；API 摘要携带两字段。
"""
import secrets
import uuid

import pytest

from models import db, User, Post, ROLE_SUPER, hreflang_alternates
from utils import _sign_csrf
from admin._helpers import create_post_core


def _uid():
    return uuid.uuid4().hex[:12]


def _mkuser(role=ROLE_SUPER):
    u = User(username="i18n-" + _uid(), email="i18n-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


@pytest.fixture
def group(app):
    with app.app_context():
        zh = create_post_core(title="I18N Hello", content="中文正文", published=True,
                              lang="zh", translation_group="g-i18n")
        en = create_post_core(title="I18N Hello EN", content="English body", published=True,
                              lang="en", translation_group="g-i18n")
        db.session.commit()
        yield {"zh": zh, "en": en}


# ---------- 1. hreflang_alternates ----------
def test_hreflang_standalone(app):
    with app.app_context():
        p = create_post_core(title="Solo Post", content="x", published=True)
        alts = hreflang_alternates(p, "https://example.com")
        assert alts == [("x-default", "https://example.com/post/" + p.slug)]


def test_hreflang_group(app):
    with app.app_context():
        zh = create_post_core(title="G zh", content="x", published=True, lang="zh", translation_group="g-alt")
        en = create_post_core(title="G en", content="y", published=True, lang="en", translation_group="g-alt")
        alts = {(h, u.rsplit("/post/", 1)[1]) for h, u in hreflang_alternates(zh, "https://example.com")}
        assert ("zh", zh.slug) in alts
        assert ("en", en.slug) in alts
        assert ("x-default", zh.slug) in alts  # x-default 优先 zh
        # 仅一个 x-default
        assert sum(1 for h, _ in hreflang_alternates(zh, "x") if h == "x-default") == 1


# ---------- 2. lang_dedup ----------
def test_lang_dedup_prefers_requested(app):
    from api.common import lang_dedup
    with app.app_context():
        zh = create_post_core(title="D zh", content="x", published=True, lang="zh", translation_group="g-ded")
        en = create_post_core(title="D en", content="y", published=True, lang="en", translation_group="g-ded")
        allp = [zh, en]
        out_en = lang_dedup(allp, "en")
        assert len(out_en) == 1 and out_en[0].lang == "en"
        out_zh = lang_dedup(allp, "zh")
        assert out_zh[0].lang == "zh"
        assert lang_dedup(allp, "") == allp  # 无 ?lang= 原样返回


# ---------- 3. 详情 ?lang= 解析 ----------
def test_detail_lang_resolution(client, group):
    zh, en = group["zh"], group["en"]
    r = client.get("/api/post/%s?lang=en" % zh.slug)
    assert r.status_code == 200
    d = r.get_json()
    assert d["slug"] == en.slug
    assert d["lang"] == "en"
    # translations 列出同组其它语言
    slugs = {t["slug"] for t in d["translations"]}
    assert zh.slug in slugs
    # 无 ?lang= 返回默认 zh
    assert client.get("/api/post/%s" % zh.slug).get_json()["lang"] == "zh"
    # ?lang= 与当前相同 → 仍是当前
    assert client.get("/api/post/%s?lang=zh" % zh.slug).get_json()["slug"] == zh.slug
    # ?lang= 指向不存在的语言 → 回退当前
    assert client.get("/api/post/%s?lang=ja" % zh.slug).get_json()["slug"] == zh.slug


# ---------- 4. 列表 ?lang= 去重 ----------
def test_list_lang_dedup(client, group):
    en = group["en"]
    items = client.get("/api/posts?lang=en").get_json()["items"]
    g = [i for i in items if i["translation_group"] == "g-i18n"]
    assert len(g) == 1
    assert g[0]["lang"] == "en"
    assert g[0]["slug"] == en.slug
    # 摘要携带 lang / translation_group
    assert "lang" in g[0] and "translation_group" in g[0]


# ---------- 5. sitemap / OG hreflang ----------
def test_sitemap_hreflang(client, group):
    zh, en = group["zh"], group["en"]
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "xhtml:link" in body and "hreflang" in body
    assert "/post/%s" % zh.slug in body
    assert "/post/%s" % en.slug in body
    assert "x-default" in body


def test_og_shell_hreflang(client, group):
    en = group["en"]
    # Googlebot UA → 闸门放行，壳页渲染含 hreflang + 正确 <html lang>
    body = client.get("/api/og/post/%s?seo=1" % en.slug,
                      headers={"User-Agent": "Googlebot"}).get_data(as_text=True)
    assert "hreflang" in body
    assert "lang='en'" in body
    assert "/post/%s" % en.slug in body


# ---------- 6. 后台表单 lang + translation_group ----------
def test_new_post_form_sets_lang(app, client):
    with app.app_context():
        u = _mkuser()
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/post/new", data={
                "csrf_token": tok, "title": "表单语种文", "content": "正文",
                "published": "on", "lang": "en", "translation_group": "g-form",
            })
            assert r.status_code in (200, 302), r.status_code
            p = Post.query.filter_by(title="表单语种文").first()
            assert p is not None
            assert p.lang == "en"
            assert p.translation_group == "g-form"
            _cleanup(p.id, u.id)
        finally:
            _cleanup(None, u.id)


def test_edit_post_form_updates_lang(app, client):
    with app.app_context():
        u = _mkuser()
        p = create_post_core(title="编辑语种文", content="正文", published=True,
                             lang="zh", translation_group="")
        db.session.commit()
        pid = p.id
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/post/%d/edit" % pid, data={
                "csrf_token": tok, "title": "编辑语种文", "content": "改后",
                "lang": "ja", "translation_group": "g-edit",
            })
            assert r.status_code in (200, 302), r.status_code
            p2 = db.session.get(Post, pid)
            assert p2.lang == "ja"
            assert p2.translation_group == "g-edit"
            _cleanup(pid, u.id)
        finally:
            _cleanup(pid, u.id)


def _cleanup(pid, uid):
    if pid is not None:
        pp = db.session.get(Post, pid)
        if pp:
            db.session.delete(pp)
    if uid is not None:
        uu = db.session.get(User, uid)
        if uu:
            db.session.delete(uu)
    db.session.commit()
