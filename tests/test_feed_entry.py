# -*- coding: utf-8 -*-
"""v5.3.0「订阅入口」守卫。

## 这个文件在防什么

后端早就有 `/feed.xml` 与 `/feed.atom`（`routes.py`），但**前台一个入口都没有** ——
页脚只有备案号、侧栏那个「订阅」是邮件订阅。结果就是：源是好的，别人找不到。
这次补的是「入口」，不是「源」。

入口类改动最典型的三种退化，每条对应下面一组断言：

1. **页面在，入口不在**（路由加了，没人链过去）→ 页脚/侧栏必须都指向 `/feed`；
2. **英文界面漏键** → `t()` 会静默退回中文，界面一半英文一半中文，
   而「漏一个键」不会报错、不会构建失败 —— 只能靠把**用到的键**与词典对起来；
3. **入口指向的源没了** → 两个源必须都还在、且内容一致（否则订阅者拿到半份）。

## 判据为什么先剥注释

模板注释里会写到 `/feed`、`/feed.xml` 这些字符串（说明「为什么不直接链 XML」），
直接 `in` 匹配会把**注释里的说明**当成真的入口。同类坑在本项目已踩 3 次。
"""
import io
import os
import re
import secrets

from models import db, Post

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_VUE = "vue-frontend/src/App.vue"
SIDEBAR = "vue-frontend/src/components/Sidebar.vue"
ROUTER = "vue-frontend/src/router.js"
SUB_VIEW = "vue-frontend/src/views/SubscribeView.vue"
STORE = "vue-frontend/src/store.js"

_BLOCK_RE = re.compile(r"/\*.*?\*/", re.S)
_HTML_RE = re.compile(r"<!--.*?-->", re.S)


def _read(rel):
    with io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def _code_only(src: str) -> str:
    """剥掉注释再匹配（块注释 / 行注释 / HTML 注释）。"""
    src = _BLOCK_RE.sub("", src)
    src = _HTML_RE.sub("", src)
    return "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith(("//", "*"))
    )


def _i18n_block(lang: str) -> str:
    """取出 I18N 里某个语言的词典原文（用于判「键在不在这一份里」）。"""
    src = _read(STORE)
    start = src.index("  %s: {" % lang)
    end = src.index("  en: {", start + 1) if lang == "zh" else src.index("\n};", start)
    return src[start:end]


def _rss_keys_used() -> set:
    """从三个用到订阅入口的文件里，把实际调用 `t('rss_*')` 的键全抠出来。

    这样以后**再加一个键而只写了中文**，这条测试会立刻变红 ——
    比手写一份键清单强：清单会过期，源码不会。
    """
    keys = set()
    for rel in (SUB_VIEW, APP_VUE, SIDEBAR):
        keys |= set(re.findall(r"t\(\s*'(rss_[a-z0-9_]+)'", _read(rel)))
    return keys


# ---------------------------------------------------------------- 入口

def test_路由表有订阅页():
    src = _code_only(_read(ROUTER))
    assert 'path: "/feed"' in src, "缺 /feed 路由"
    assert "SubscribeView.vue" in src, "/feed 必须指向订阅页组件"


def test_页脚有订阅入口():
    src = _code_only(_read(APP_VUE))
    assert 'to="/feed"' in src, "页脚没有链到 /feed —— 别人找不到订阅入口"


def test_侧栏也有订阅入口():
    """侧栏那个 widget 是邮件订阅，RSS 入口必须**单独**有一块。

    只留页脚的话，浏览文章时（侧栏就在手边）根本看不到订阅入口。
    """
    src = _code_only(_read(SIDEBAR))
    assert 'to="/feed"' in src, "侧栏没有 RSS 订阅入口"


def test_订阅页列出两个源(app):
    """两个源都要列：`/feed.xml`（RSS 2.0）与 `/feed.atom`（Atom）。

    只给一个的后果是一部分人的阅读器订阅失败 —— 而他们**不会回来告诉你**，
    只是默默不订了。
    """
    src = _code_only(_read(SUB_VIEW))
    assert "/feed.xml" in src and "/feed.atom" in src


def test_订阅页地址用同源拼接而不是写死域名():
    """硬编码域名在换域名/多域名后必然指错 —— 且是**静默**指错（页面上看着正常）。"""
    src = _code_only(_read(SUB_VIEW))
    assert "window.location.origin" in src
    assert "https://www.llhhy.cn" not in src, "不要把站点域名写死在订阅页里"


# ---------------------------------------------------------------- i18n

def test_用到的订阅文案中英文都有():
    keys = _rss_keys_used()
    assert keys, "没抠到任何 rss_* 键 —— 判据失效了，检查正则"
    zh, en = _i18n_block("zh"), _i18n_block("en")
    for k in sorted(keys):
        assert '"%s":' % k in zh, "中文词典缺 %s" % k
        assert '"%s":' % k in en, (
            "英文词典缺 %s —— t() 会静默退回中文，界面变成中英混排" % k
        )


# ---------------------------------------------------------------- 源本身

def test_两个源都在且条目一致(app, client):
    """入口指向的两个源必须都活着、内容同源 —— 否则「能订阅」是假的。"""
    slug = "feed-entry-" + secrets.token_hex(4)
    with app.app_context():
        db.session.add(Post(title="订阅入口测试文", slug=slug, content="正文",
                            summary="摘要", published=True))
        db.session.commit()

    try:
        rss = client.get("/feed.xml")
        atom = client.get("/feed.atom")
        assert rss.status_code == 200
        assert atom.status_code == 200
        rbody = rss.get_data(as_text=True)
        abody = atom.get_data(as_text=True)
        assert slug in rbody, "RSS 2.0 源里没有这篇文章"
        assert slug in abody, "Atom 源里没有这篇文章"
        assert rbody.count("<item>") == abody.count("<entry>"), (
            "两个源的条目数不一致（RSS %d / Atom %d）—— 订阅者会拿到半份内容"
            % (rbody.count("<item>"), abody.count("<entry>"))
        )
    finally:
        with app.app_context():
            Post.query.filter_by(slug=slug).delete(synchronize_session=False)
            db.session.commit()
