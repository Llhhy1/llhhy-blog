# -*- coding: utf-8 -*-
"""`/feed.atom`（Atom 1.0）回归测试（v3.20.0）。

**为什么用 XML 解析器而不是字符串断言**：Atom 是 XML，字符串 `in` 检查无法发现
「标签未闭合 / 属性引号错 / `&` 未转义」这类**会让阅读器直接解析失败**的问题。
这里用 `xml.etree.ElementTree` 真正解析一遍 —— 只要能 parse 成功，就排除了整类
「看起来像 XML 其实不是」的缺陷。

同时锁住两件与安全/可见性相关的事：
1. **可见性真相源**：草稿 / 隐私 / 回收站 / 未到点定时的文章**不得**出现在订阅源里
   （否则等于把未发布内容主动推给订阅者）。
2. **XML 转义**：标题/摘要里的 `&` / `<` 必须被转义，否则会破坏 XML 结构
   （注入点）。
"""
import secrets
import xml.etree.ElementTree as ET
from datetime import timedelta

from models import db, Post, Setting
from _time import utcnow

ATOM = "{http://www.w3.org/2005/Atom}"


def _mkpost(**kw):
    p = Post(title=kw.pop("title", "Atom 测试标题"),
             slug="atom-" + secrets.token_hex(4),
             content=kw.pop("content", "正文内容"),
             summary=kw.pop("summary", "摘要"),
             published=kw.pop("published", True),
             in_trash=kw.pop("in_trash", False),
             is_private=kw.pop("is_private", False),
             **kw)
    db.session.add(p)
    db.session.commit()
    return p


def _set_base(value="https://www.llhhy.cn"):
    """设置 site_url（先删后插 —— Setting.key 有唯一约束，直接 add 会冲突）。"""
    Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
    if value:
        db.session.add(Setting(key="site_url", value=value))
    db.session.commit()


def _cleanup(ids, slugs):
    Post.query.filter(Post.id.in_(list(ids))).delete(synchronize_session=False)
    Post.query.filter(Post.slug.in_(list(slugs))).delete(synchronize_session=False)
    db.session.commit()


def test_atom_is_wellformed_and_has_required_elements(app, client):
    """Atom 基本契约：良构 XML + feed 级必需元素（title/id/updated）。"""
    with app.app_context():
        _set_base()
        p = _mkpost()
        ids, slugs = [p.id], [p.slug]
    try:
        r = client.get("/feed.atom")
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        assert r.mimetype == "application/atom+xml", r.mimetype
        root = ET.fromstring(r.get_data())          # ← 不抛异常即良构
        assert root.tag == "%sfeed" % ATOM
        for tag in ("title", "id", "updated"):
            el = root.find("%s%s" % (ATOM, tag))
            assert el is not None and (el.text or "").strip(), \
                "Atom feed 缺少必需的 <%s>" % tag
        # updated 必须是 RFC3339（Atom 规范要求）
        upd = root.find("%supdated" % ATOM).text
        assert "T" in upd and upd.endswith("+08:00"), \
            "updated 应为 RFC3339 且带时区，实得 %r" % upd
    finally:
        with app.app_context():
            _cleanup(ids, slugs)


def test_atom_contains_published_post(app, client):
    """已发布文章应作为 entry 出现，且 title/link/id/updated 齐全。"""
    with app.app_context():
        _set_base()
        title = "Atom 条目标题-" + secrets.token_hex(3)
        p = _mkpost(title=title)
        ids, slugs = [p.id], [p.slug]
    try:
        root = ET.fromstring(client.get("/feed.atom").get_data())
        titles = [(e.find("%stitle" % ATOM).text or "") for e in root.findall("%sentry" % ATOM)]
        assert title in titles, "已发布文章应出现在 Atom 里"
        entry = [e for e in root.findall("%sentry" % ATOM)
                 if (e.find("%stitle" % ATOM).text or "") == title][0]
        link = entry.find("%slink" % ATOM)
        assert link is not None and link.get("href"), "entry 缺 <link href>"
        assert "/post/%s" % slugs[0] in link.get("href"), \
            "link 必须指向公开地址 /post/<slug>，实得 %r" % link.get("href")
        assert entry.find("%sid" % ATOM) is not None
        assert entry.find("%supdated" % ATOM) is not None
    finally:
        with app.app_context():
            _cleanup(ids, slugs)


def test_atom_hides_unpublished_states(app, client):
    """**可见性红线**：草稿 / 隐私 / 回收站 / 未到点定时 都不得出现在订阅源。"""
    marker = "ATOM-LEAK-MARKER-" + secrets.token_hex(4)
    with app.app_context():
        _set_base()
        posts = [
            _mkpost(title=marker + " 草稿", published=False),
            _mkpost(title=marker + " 隐私", is_private=True),
            _mkpost(title=marker + " 回收站", in_trash=True),
            _mkpost(title=marker + " 定时未到",
                    scheduled_at=utcnow() + timedelta(days=7)),
        ]
        ids = [p.id for p in posts]
        slugs = [p.slug for p in posts]
    try:
        r = client.get("/feed.atom")
        body = r.get_data(as_text=True)
        assert marker not in body, \
            "未发布状态的文章泄露进了 Atom 订阅源（可见性必须走 visible_posts_query）"
    finally:
        with app.app_context():
            _cleanup(ids, slugs)


def test_atom_escapes_special_chars(app, client):
    """标题/摘要里的 `&` `<` 必须被转义，否则会破坏 XML 结构（注入点）。"""
    with app.app_context():
        _set_base()
        p = _mkpost(title="A & B <script>alert(1)</script>",
                    summary="摘要含 & 与 <b> 标签")
        ids, slugs = [p.id], [p.slug]
    try:
        raw = client.get("/feed.atom").get_data()
        ET.fromstring(raw)                      # 仍可解析 → 转义正确
        text = raw.decode("utf-8")
        assert "<script>alert(1)</script>" not in text, \
            "标题里的原始标签被原样写入 Atom —— XML 转义没做"
        assert "&amp;" in text or "&lt;" in text, "应出现被转义的实体"
    finally:
        with app.app_context():
            _cleanup(ids, slugs)
