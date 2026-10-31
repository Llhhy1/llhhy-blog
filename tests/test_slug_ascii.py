# -*- coding: utf-8 -*-
"""v5.4.0：分类 / 标签 / 系列 slug 可读化（纯 ASCII + 旧地址兼容）。

背景：`make_slug()` 保留汉字，历史上 46 个标签的 slug 都是 `智能体安全` 这种，
浏览器请求时被百分号编码成 `%e6%99%ba...`，分享链接与访问日志都不可读。

本文件盯住四条红线：
1. 新建/迁移后的 slug **必须全部是 ASCII**；
2. 旧地址（中文名 / 旧大小写写法 / 旧自动拼音）**仍能解析到同一行**；
3. 列表接口对旧地址返回 `moved` + 新 slug（前端据此换地址栏）；
4. RSS 与爬虫壳页对旧地址发 **301**（不是 200 + canonical 暗示）。
"""

import secrets
from urllib.parse import quote

from models import Category, Series, Tag, db
from utils.slug import ascii_slug
from utils.taxonomy_slug import resolve_taxonomy

UA_BAIDU = "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"


def _uid():
    return secrets.token_hex(4)


def _is_ascii(s):
    return all(ord(ch) < 128 for ch in s)


# ---------------------------------------------------------------- 转换本身

def test_汉字转拼音():
    assert ascii_slug("智能体安全") == "zhi-neng-ti-an-quan"
    assert ascii_slug("AI周报") == "ai-zhou-bao"


def test_符号折叠与大小写():
    assert ascii_slug("纳维-斯托克斯") == "na-wei-si-tuo-ke-si"
    assert ascii_slug("  Claude   Opus 5.5  ") == "claude-opus-5-5"
    assert ascii_slug("AI Agent") == "ai-agent"


def test_空值与纯符号有兜底():
    assert ascii_slug("") == "item"
    assert ascii_slug("   ") == "item"
    assert ascii_slug("!!!") == "item"
    assert ascii_slug("", fallback="x") == "x"


def test_超长截断且不以连字符结尾():
    s = ascii_slug("很长" * 60, max_len=20)
    assert 0 < len(s) <= 20 and not s.endswith("-")


# ---------------------------------------------------------------- 后台写入

def test_新建标签默认用拼音地址(app):
    from admin.taxonomy import create_tag_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, err = create_tag_core(name)
        assert err == "", err
        t = db.session.get(Tag, tid)
        assert _is_ascii(t.slug), "标签 slug 仍是中文：%r" % t.slug
        assert t.slug == ascii_slug(name)


def test_新建标签可指定英文地址(app):
    from admin.taxonomy import create_tag_core

    want = "agent-security-" + _uid()
    with app.app_context():
        tid, err = create_tag_core("智能体安全" + _uid(), want)
        assert err == "", err
        assert db.session.get(Tag, tid).slug == want


def test_改标签地址(app):
    from admin.taxonomy import create_tag_core, set_tag_slug_core

    with app.app_context():
        tid, _ = create_tag_core("智能体安全" + _uid())
        t = db.session.get(Tag, tid)
        old = t.slug
        want = "agent-security-" + _uid()
        err, note = set_tag_slug_core(t, want)
        assert err == "" and t.slug == want
        assert old in note and want in note, "提示里要说清旧 → 新"


def test_新建系列默认拼音地址(app):
    from admin.taxonomy import create_series_core

    name = "新闻" + _uid()
    with app.app_context():
        sid, err = create_series_core({"name": name})
        assert err == "", err
        s = db.session.get(Series, sid)
        assert _is_ascii(s.slug) and s.slug == ascii_slug(name)


def test_分类改名不再自动换地址(app):
    from admin.taxonomy import create_category_core, rename_category_core

    with app.app_context():
        cid, _ = create_category_core("分类甲" + _uid())
        c = db.session.get(Category, cid)
        old = c.slug
        err, note = rename_category_core(c, "分类乙" + _uid())
        assert err == "" and c.slug == old, "改名不应改动对外地址"
        assert note == "", "地址没变就不该提示旧链接失效"


def test_分类显式给地址才改(app):
    from admin.taxonomy import create_category_core, rename_category_core

    want = "new-cat-" + _uid()
    with app.app_context():
        cid, _ = create_category_core("分类甲" + _uid())
        c = db.session.get(Category, cid)
        err, note = rename_category_core(c, c.name, want)
        assert err == "" and c.slug == want
        assert note, "换了地址必须提示"


# ---------------------------------------------------------------- 旧地址兼容

def test_旧中文地址解析为同一行(app):
    from admin.taxonomy import create_tag_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, _ = create_tag_core(name)
        t = db.session.get(Tag, tid)

        obj, legacy = resolve_taxonomy(Tag, name)          # 旧中文 slug == name
        assert obj is not None and obj.id == tid and legacy is True

        obj2, legacy2 = resolve_taxonomy(Tag, t.slug)      # 新地址：不是 legacy
        assert obj2 is not None and obj2.id == tid and legacy2 is False


def test_旧大小写写法也能解析(app):
    from admin.taxonomy import create_tag_core

    with app.app_context():
        base = "AgentSec" + _uid()
        tid, _ = create_tag_core(base, base.lower())
        obj, legacy = resolve_taxonomy(Tag, base)
        assert obj is not None and obj.id == tid and legacy is True


def test_旧自动拼音地址也能解析(app):
    from admin.taxonomy import create_tag_core, set_tag_slug_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, _ = create_tag_core(name)
        t = db.session.get(Tag, tid)
        old_pinyin = t.slug                       # 自动拼音
        set_tag_slug_core(t, "agent-security-" + _uid())
        obj, legacy = resolve_taxonomy(Tag, old_pinyin)
        assert obj is not None and obj.id == tid and legacy is True


# ---------------------------------------------------------------- 接口行为

def test_列表接口对旧地址返回moved(app, client):
    from admin.taxonomy import create_tag_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, _ = create_tag_core(name)
        t = db.session.get(Tag, tid)
        new_slug = t.slug

        r = client.get("/api/tag/" + quote(name))
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        data = r.get_json()
        assert data["moved"] is True and data["slug"] == new_slug
        assert data["name"] == name

        r2 = client.get("/api/tag/" + quote(new_slug))
        assert r2.status_code == 200
        assert "moved" not in r2.get_json(), "已经是正确地址就不该再跳"


def test_RSS对旧地址发301(app, client):
    from admin.taxonomy import create_tag_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, _ = create_tag_core(name)
        new_slug = db.session.get(Tag, tid).slug

        r = client.get("/api/rss/tag/" + quote(name))
        assert r.status_code == 301
        assert r.headers["Location"].endswith("/api/rss/tag/" + new_slug)


def test_爬虫壳页对旧地址发301(app, client):
    from admin.taxonomy import create_tag_core

    name = "智能体安全" + _uid()
    with app.app_context():
        tid, _ = create_tag_core(name)
        new_slug = db.session.get(Tag, tid).slug

        r = client.get("/api/og/page/tag/" + quote(name) + "?seo=1",
                       headers={"User-Agent": UA_BAIDU})
        assert r.status_code == 301
        assert r.headers["Location"].endswith("/tag/" + new_slug)
