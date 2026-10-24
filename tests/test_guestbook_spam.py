"""v4.9.0 留言墙敏感词过滤（ROADMAP §3.1「评论 / 留言内容审核增强」）。

缺口是怎么来的：评论侧自 v3.0.0 就有 `comment_spam_keywords` 过滤，
**留言墙一直完全没有** —— 同样是匿名可提交、且直接公开展示在留言墙上，
暴露面其实比评论更大。这是典型的「改了一处忘了另一处」的规则漂移。

修法是抽公共函数 `common.find_spam_hit()`，两边共用同一份词表与同一套
匹配语义，从此不可能再漂移。

测试要点（正反双向，避免空守门员）：

1. `find_spam_hit` 命中 / 未命中 / 空词表放行 / 大小写不敏感。
2. **留言命中 → 400 且一条都没落库**（只验状态码会假绿：若返回 400 却
   仍然写库，等于过滤形同虚设）。
3. 留言未命中 → 201 正常入库。
4. 评论侧行为不变（回归：别为了补留言把评论改坏）。
"""

import pytest

from models import db, Guestbook, Setting
from utils.net import _RATE

SPAM_KEY = "comment_spam_keywords"


@pytest.fixture
def spam_words(app):
    """写入敏感词表，用完清掉。留言 / 评论共用同一份。"""
    with app.app_context():
        Setting.query.filter_by(key=SPAM_KEY).delete()
        db.session.add(Setting(key=SPAM_KEY, value="博彩,代刷,Viagra"))
        db.session.commit()
    yield
    with app.app_context():
        Setting.query.filter_by(key=SPAM_KEY).delete()
        db.session.commit()


@pytest.fixture(autouse=True)
def _no_rate():
    """留言接口 60 秒 10 次限流，测试里多条提交会撞上，先清表。"""
    _RATE.clear()
    yield
    _RATE.clear()


@pytest.fixture(autouse=True)
def _no_captcha(monkeypatch):
    """测试库里验证码默认开启，会挡下**所有**提交（命中不命中都一样 400），
    那样就验不出敏感词过滤是否真在生效。这里关掉，聚焦过滤本身。

    之所以能 monkeypatch：posts/guestbook 都是在函数体内
    `from security import captcha_required`，每次调用重新取模块属性。
    """
    import security
    monkeypatch.setattr(security, "captcha_required", lambda: False)


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _post_gb(client, content):
    return client.post("/api/guestbook", json={"author": "访客", "content": content},
                       headers={"X-CSRF-Token": _csrf(client)})


# ---------- 1. 公共函数 ----------

def test_命中与未命中(app, spam_words):
    from api.common import find_spam_hit
    with app.app_context():
        assert find_spam_hit("欢迎来我的博彩网站") == "博彩"
        assert find_spam_hit("这篇文章写得很好") is None
        # 大小写不敏感
        assert find_spam_hit("cheap viagra here") == "viagra"


def test_空词表放行(app):
    """词表为空 = 功能关闭，不该误伤正常内容。"""
    from api.common import find_spam_hit
    with app.app_context():
        Setting.query.filter_by(key=SPAM_KEY).delete()
        db.session.commit()
        assert find_spam_hit("博彩代刷") is None


# ---------- 2~3. 留言墙 ----------

def test_留言命中敏感词被拒且不落库(client, app, spam_words):
    with app.app_context():
        Guestbook.query.delete()
        db.session.commit()

    r = _post_gb(client, "加我微信，博彩稳赚")
    assert r.status_code == 400, r.get_data(as_text=True)

    with app.app_context():
        assert Guestbook.query.count() == 0, "返回 400 却仍然落库 = 过滤形同虚设"


def test_留言正常内容可提交(client, app, spam_words):
    with app.app_context():
        Guestbook.query.delete()
        db.session.commit()

    r = _post_gb(client, "博客写得很棒，学习了")
    assert r.status_code == 201, r.get_data(as_text=True)

    with app.app_context():
        assert Guestbook.query.count() == 1


# ---------- 4. 评论侧回归 ----------

def test_评论侧过滤仍然生效(client, app, spam_words):
    """补留言的同时不能把评论改坏 —— 评论的过滤是 v3.0.0 的老能力。"""
    with app.app_context():
        from models import Post, Category
        Post.query.filter_by(slug="spam-probe-post").delete()
        db.session.commit()
        cat = Category.query.first()
        # 注意：Post 用 `published` 布尔表示发布态，**没有** status 字段
        p = Post(title="spam probe", slug="spam-probe-post", content="正文",
                 summary="摘要", published=True)
        if cat is not None:
            p.category_id = cat.id
        db.session.add(p)
        db.session.commit()

    r = client.post("/api/post/spam-probe-post/comment",
                    json={"author": "访客", "content": "代刷流量联系我"},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 400, r.get_data(as_text=True)
