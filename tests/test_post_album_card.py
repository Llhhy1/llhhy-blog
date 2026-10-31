# -*- coding: utf-8 -*-
"""v5.3.0 文章正文里的「相册链接卡片」与写文章页取素材接口。

## 这个文件在防什么

卡片是**渲染器给作者的语法糖**（`@album[slug]`），不是作者能写出来的 HTML ——
bleach 白名单没扩（作者仍然写不出 `<div>`），卡片 HTML 由服务端生成。
这类「语法 → 服务端生成 HTML」的东西有三类静默故障，都不报错：

1. **语法匹配口径错**：判据写得过窄 → 作者说「我写了但没出现」。
   （首版只认行首 `@album[...]`，而 Markdown 会把它包成 `<p>@album[...]</p>`，
   实测一处都匹配不到。）
2. **渲染位置错（缓存吞卡片）**：卡片若渲染在 `render_markdown()` 里，
   会被 `content_html` 缓存住 —— 改一次相册标题，所有引用它的文章都还是旧卡片。
   所以卡片必须**在缓存之外**注入。
3. **泄露私密相册的存在**：文章是公开的而相册是私密的，渲染出卡片就等于
   「告诉读者存在一个叫 X 的私密相册」。降级策略是整段移除。

另外两条接口（`/admin/albums/picker-list`、`media-picker?album_id=`）是写文章
页两个弹层的数据源，只断言**顺序与可见性**这两件最容易错的事。
"""
import secrets

import pytest

from models import ROLE_SUPER, Album, AlbumItem, MediaAsset, Post, User, db
from utils import _sign_csrf, inject_album_cards, render_post_html


@pytest.fixture(autouse=True)
def _clean(app):
    """测试库全 session 共享：进出各清一次，避免污染别的文件。

    `media_asset` **不清** —— 别的测试文件可能依赖自己建的记录，全删会连坐。
    代价是「素材总数」类断言必须先用基线做差（见下面的 total 断言）。
    """
    with app.app_context():
        AlbumItem.query.delete()
        Album.query.delete()
        db.session.commit()
    yield
    with app.app_context():
        Post.query.filter(Post.slug.like("zzcard-%")).delete(synchronize_session=False)
        db.session.commit()


def _login_admin(app, client):
    with app.app_context():
        u = User(username="ac-" + secrets.token_hex(4),
                 email="ac-%s@test.local" % secrets.token_hex(4))
        u.set_password("test-pass")
        u.role = ROLE_SUPER
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        uid = u.id
    raw = secrets.token_hex(24)
    with app.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["csrf_token"] = tok
    return tok


def _media(app, name="m.webp", kind="image", public=True):
    with app.app_context():
        m = MediaAsset(filename=name, kind=kind, source="local",
                       url="/static/uploads/" + name, title=name.split(".")[0],
                       is_public=public, size=1024)
        db.session.add(m)
        db.session.commit()
        return m.id


def _album(app, slug="yunhe", title="云和梯田", public=True,
           summary="4 天 4 晚", **kw):
    with app.app_context():
        a = Album(slug=slug, title=title, summary=summary, is_public=public, **kw)
        db.session.add(a)
        db.session.commit()
        return a.id


def _post(app, content, title="T", slug=None):
    with app.app_context():
        p = Post(title=title, slug=slug or ("zzcard-" + secrets.token_hex(4)),
                 content=content, published=True)
        db.session.add(p)
        db.session.commit()
        return p.id


# ---------------------------------------------------------------- 卡片渲染

def test_独占一段的卡片语法渲染成卡片(app):
    """`@album[slug]` 独占一段 → 卡片（含封面 / 标题 / 跳相册的链接）。"""
    with app.app_context():
        cover = _media(app, "cover.webp")
        _album(app, slug="yunhe", title="云和梯田", cover_media_id=cover)
        pid = _post(app, "前面的正文\n\n@album[yunhe]\n\n后面的正文")

    with app.app_context():
        html = render_post_html(Post.query.get(pid))

    assert "post-album-card" in html, "卡片没渲染出来"
    assert "/album/yunhe" in html
    assert "云和梯田" in html
    assert "/static/uploads/cover.webp" in html, "应带上封面图"
    assert "前面的正文" in html and "后面的正文" in html, "卡片不该吃掉前后正文"
    assert "@album[" not in html, "语法本身不该留在页面上"


def test_写在行内的卡片语法不渲染(app):
    """对照：不独占一段就不该变成卡片（判据必须锚定块级形态）。

    少了这条，「正则太宽把正文里的普通 @xxx[yyy] 也吃掉」会一直没人发现。
    """
    with app.app_context():
        _album(app, slug="yunhe")
    html = inject_album_cards("<p>联系我：@album[yunhe] 谢谢</p>")
    assert "post-album-card" not in html
    assert "@album[yunhe]" in html, "行内写法应原样保留，不能凭空消失"


def test_私密相册不渲染卡片也不泄露存在性(app):
    """文章公开 + 相册私密：卡片整段移除，连标题和 slug 都不许出现。"""
    with app.app_context():
        _album(app, slug="secret", title="私密旅行", public=False)
        pid = _post(app, "@album[secret]\n")

    with app.app_context():
        html = render_post_html(Post.query.get(pid))

    assert "post-album-card" not in html
    assert "secret" not in html, "私密相册的 slug 不该出现在公开文章里"
    assert "私密旅行" not in html


def test_相册不存在时整段移除不留残字(app):
    with app.app_context():
        pid = _post(app, "开头\n\n@album[nope]\n\n结尾")
    with app.app_context():
        html = render_post_html(Post.query.get(pid))
    assert "@album[" not in html, "不存在的相册应整段移除，不能把语法原样露出"
    assert "开头" in html and "结尾" in html


def test_相册标题里的_html_被转义(app):
    """卡片内容全部由服务端拼 HTML → 动态文本必须转义（这是唯一的 XSS 面）。"""
    with app.app_context():
        _album(app, slug="xss", title="<script>alert(1)</script>",
               summary="<img src=x onerror=alert(1)>")
        pid = _post(app, "@album[xss]\n")
    with app.app_context():
        html = render_post_html(Post.query.get(pid))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html, "标题必须转义（卡片 HTML 是服务端拼的，这是唯一的 XSS 面）"
    # 摘要里的 <img ...> 被转义成文本：断言「标签没成形」而不是「子串不存在」
    # —— `onerror=` 这几个字符作为**纯文本**留着是无害的，判 `<img src=x` 才是判据。
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_没指定封面时取相册里第一张图(app):
    with app.app_context():
        m1 = _media(app, "first.webp")
        _media(app, "second.webp")
        aid = _album(app, slug="yunhe")
        db.session.add(AlbumItem(album_id=aid, media_id=m1, sort=1))
        db.session.commit()
        pid = _post(app, "@album[yunhe]\n")
    with app.app_context():
        html = render_post_html(Post.query.get(pid))
    assert "/static/uploads/first.webp" in html


def test_改相册标题后卡片跟着变_缓存不吞卡片(app):
    """卡片必须在**缓存之外**注入：改一次相册，文章里的卡片要立刻跟着变。

    反证：若 injected 在 `render_markdown()` 里，`content_html` 会把旧卡片
    缓存住，第二次渲染命中缓存 → 标题永远是旧的（且不报错）。
    """
    with app.app_context():
        _album(app, slug="yunhe", title="旧标题")
        pid = _post(app, "@album[yunhe]\n")

    with app.app_context():
        first = render_post_html(Post.query.get(pid))
    assert "旧标题" in first

    with app.app_context():
        a = Album.query.filter_by(slug="yunhe").first()
        a.title = "新标题"
        db.session.commit()

    with app.app_context():
        p = Post.query.get(pid)
        second = render_post_html(p)
        cached = p.content_html or ""

    assert "新标题" in second, "改了相册标题，文章卡片还是旧的 —— 卡片被缓存吞了"
    assert "旧标题" not in second
    assert "post-album-card" not in cached, "缓存里存的是纯 Markdown 渲染结果，不该含卡片"


# ---------------------------------------------------------------- 后台预览 / 接口

def test_实时预览也渲染卡片(app, client):
    """写作者在后台预览里看不到卡片，会以为语法没生效（预览与前台必须同口径）。"""
    _login_admin(app, client)
    with app.app_context():
        _album(app, slug="yunhe", title="云和梯田")
    with client.session_transaction():
        pass
    r = client.post("/admin/md-preview",
                    data={"content": "@album[yunhe]\n"},
                    headers={"X-CSRF-Token": _csrf_of(client)})
    assert r.status_code == 200, r.data[:300]
    body = r.get_data(as_text=True)
    assert "post-album-card" in body
    assert "/album/yunhe" in body


def _csrf_of(client):
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def test_相册列表接口包含私密相册并给出条目数(app, client):
    """后台作者要能看见自己**全部**相册（含私密）—— 卡片对读者可见与否由渲染侧决定。
    在这里过滤掉私密，作者会遇到「我明明有这个相册，插入面板里却没有」。
    """
    _login_admin(app, client)
    with app.app_context():
        aid = _album(app, slug="pub", public=True)
        _album(app, slug="priv", title="私密的", public=False)
        m = _media(app, "a.webp")
        db.session.add(AlbumItem(album_id=aid, media_id=m, sort=1))
        db.session.commit()

    d = client.get("/admin/albums/picker-list").get_json()
    items = {i["slug"]: i for i in d["items"]}
    assert "pub" in items and "priv" in items, "私密相册也必须列出来"
    assert items["priv"]["is_public"] is False
    assert items["pub"]["count"] == 1, "条目数用于面板上显示「共 N 项」"
    assert items["pub"]["slug"] == "pub"


def test_素材接口按相册内顺序返回而非创建时间(app, client):
    """写作者的心智模型是「我在翻某个相册」：顺序必须跟相册编排走，
    否则「挑了第 3 张，列表里它却在第 20 位」。
    """
    _login_admin(app, client)
    with app.app_context():
        old = _media(app, "old.webp")     # 先进媒体库
        new = _media(app, "new.webp")
        aid = _album(app, slug="yunhe")
        # 相册里刻意倒过来排：新图在前
        db.session.add(AlbumItem(album_id=aid, media_id=new, sort=1))
        db.session.add(AlbumItem(album_id=aid, media_id=old, sort=2))
        _media(app, "other.webp")         # 不属于这个相册
        db.session.commit()
        aid_real = aid

    d = client.get("/admin/albums/media-picker?album_id=%d" % aid_real).get_json()
    urls = [i["url"] for i in d["items"]]
    assert urls == ["/static/uploads/new.webp", "/static/uploads/old.webp"], urls
    assert d["total"] == 2, "不该把相册外的素材算进来"


def test_素材接口不带相册id时是全部素材(app, client):
    """上一条的对照：不带 album_id 仍是原来的全库行为（不能改坏相册编排页）。"""
    _login_admin(app, client)
    base = client.get("/admin/albums/media-picker").get_json()["total"]
    with app.app_context():
        aid = _album(app, slug="yunhe")
        m = _media(app, "a.webp")
        db.session.add(AlbumItem(album_id=aid, media_id=m, sort=1))
        _media(app, "b.webp")
        db.session.commit()

    # 测试库全 session 共享（media_asset 不清），所以用「增加 2」而不是「等于 2」
    d = client.get("/admin/albums/media-picker").get_json()
    assert d["total"] == base + 2


# ---------------------------------------------------------------- 写文章页入口

def test_写文章页有相册素材与卡片入口():
    """两个入口是纯前端拼装，后端测不到 —— 至少守住「按钮还在」。

    少了这条，有人动了模板（比如合并按钮区）不会有任何测试变红。
    """
    import io
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with io.open(os.path.join(root, "myblog", "templates", "admin", "edit_post.html"),
                 encoding="utf-8") as f:
        src = f.read()
    for frag in ('id="album-pick-btn"', 'id="album-card-btn"',
                 'id="amp-mask"', 'id="acp-mask"', "@album["):
        assert frag in src, "写文章页缺了 %s" % frag


def test_写文章页真能渲染出这两个入口(app, client):
    """上一条读的是模板源码；这条渲染真实页面 —— 顺便守住 Jinja 语法没写坏。

    Jinja 的 Undefined 不报错，模板里少一个变量只是「那块空白」，
    所以必须真的 GET 一次。
    """
    _login_admin(app, client)
    r = client.get("/admin/post/new")
    assert r.status_code == 200, r.data[:400]
    body = r.get_data(as_text=True)
    assert 'id="album-pick-btn"' in body
    assert 'id="album-card-btn"' in body
    assert 'id="amp-mask"' in body and 'id="acp-mask"' in body
    assert "album_media_picker" in body or "/admin/albums/media-picker" in body, (
        "弹层的取数地址没渲染出来（url_for 写错会在 JS 里变空串）"
    )
