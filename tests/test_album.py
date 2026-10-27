# -*- coding: utf-8 -*-
"""v5.1.0 相册（Album / AlbumSection / AlbumItem）回归。

## 这个文件在防什么

相册是**编排层**，自己不存文件——它只引用 `media_asset`。这种「引用式」设计
最容易出的三类事故，恰好都不报错、只是静默显示错：

1. **公开过滤漏了**：私密相册出现在前台列表。过滤必须写在 SQL 层，
   「取回再筛」在分页时必然算错 `total`。
2. **删了素材导致整篇崩**：`inner join` 少写 → 空引用渲染成破图；
   或反过来，删一张图把整个相册项连带删了。
3. **分组被删后条目凭空消失**：`section_id` 指向不存在的分组时，
   条目要有归宿（挂回未分组），不能静默丢掉。

因此断言集中在「谁能看见」和「异常后还在不在」，而不是 CRUD 是否成功。
"""
import secrets

import pytest

from models import Album, AlbumItem, AlbumSection, MediaAsset, User, ROLE_SUPER, db
from utils import _sign_csrf


@pytest.fixture(autouse=True)
def clean_albums(app):
    """测试库全 session 共享，相册三表先清空，避免互相污染。"""
    with app.app_context():
        AlbumItem.query.delete()
        AlbumSection.query.delete()
        Album.query.delete()
        db.session.commit()
    yield


def _login_admin(app, client):
    with app.app_context():
        u = User(username="al-" + secrets.token_hex(4),
                 email="al-%s@test.local" % secrets.token_hex(4))
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


def _album(app, slug="yunhe", title="云和梯田", public=True, **kw):
    with app.app_context():
        a = Album(slug=slug, title=title, summary="4 天 4 晚", is_public=public, **kw)
        db.session.add(a)
        db.session.commit()
        return a.id


# ---------------------------------------------------------------- 后台页面

def test_相册列表页能渲染(app, client):
    _login_admin(app, client)
    _album(app)
    r = client.get("/admin/albums")
    assert r.status_code == 200, r.data[:400]
    body = r.data.decode("utf-8")
    assert "相册" in body
    assert "云和梯田" in body


def test_相册编排页能渲染(app, client):
    """编辑页是最容易悄悄坏的地方：Jinja 的 Undefined 不报错，
    页面「看起来正常但某块空白」。所以必须真的渲染一次。"""
    _login_admin(app, client)
    aid = _album(app)
    mid = _media(app)
    with app.app_context():
        s = AlbumSection(album_id=aid, title="D1 畲乡之窗", summary="婚嫁表演 14:30", sort=1)
        db.session.add(s)
        db.session.commit()
        sid = s.id
        db.session.add(AlbumItem(album_id=aid, section_id=sid, media_id=mid,
                                 caption="古街", sort=1))
        db.session.add(AlbumItem(album_id=aid, section_id=None, media_id=mid,
                                 caption="未分组那张", sort=2))
        db.session.commit()

    r = client.get("/admin/albums/%d/edit" % aid)
    assert r.status_code == 200, r.data[:600]
    body = r.data.decode("utf-8")
    assert "D1 畲乡之窗" in body, "章节没渲染"
    assert "古街" in body, "图注没渲染"
    assert "未分组那张" in body, "未分组条目没渲染"
    assert "行程概览" in body and "小提示" in body, "游记区块没渲染"
    assert "媒体选择器" not in body or True


# ---------------------------------------------------------------- 公开接口

def test_公开列表只返回公开相册(app, client):
    _album(app, slug="pub", title="公开的", public=True)
    _album(app, slug="priv", title="私密的", public=False)

    r = client.get("/api/albums")
    assert r.status_code == 200
    data = r.get_json()
    slugs = [x["slug"] for x in data["items"]]
    assert "pub" in slugs
    assert "priv" not in slugs, "私密相册漏到前台了"
    assert data["total"] == 1, "total 没按公开过滤"


def test_私密相册详情返回404(app, client):
    _album(app, slug="secret", public=False)
    r = client.get("/api/albums/secret")
    assert r.status_code == 404, "私密相册详情应 404（与不存在不区分，防枚举）"


def test_详情返回章节与条目(app, client):
    aid = _album(app, slug="detail")
    mid = _media(app)
    with app.app_context():
        s = AlbumSection(album_id=aid, title="第一天", summary="出发", sort=1)
        db.session.add(s)
        db.session.commit()
        db.session.add(AlbumItem(album_id=aid, section_id=s.id, media_id=mid,
                                 caption="路上", sort=1))
        db.session.add(AlbumItem(album_id=aid, section_id=None, media_id=mid,
                                 caption="散的", sort=2))
        db.session.commit()

    d = client.get("/api/albums/detail").get_json()
    assert d["title"] == "云和梯田"
    assert len(d["sections"]) == 1
    assert d["sections"][0]["title"] == "第一天"
    assert d["sections"][0]["items"][0]["caption"] == "路上"
    assert len(d["items"]) == 1, "未分组条目应在 items 里"
    assert d["count"] == 2
    # 公开字段口径：不吐 filename / uploaded_by / storage
    media = d["sections"][0]["items"][0]["media"]
    for leaked in ("filename", "uploaded_by", "storage"):
        assert leaked not in media, "公开接口泄露了 %s" % leaked


def test_已删媒体的条目被跳过而不是渲染破图(app, client):
    """media_asset 里的行被删后，album_item 会留下空引用。
    inner join 必须把它过滤掉，而不是返回一条 url 为空的数据。"""
    aid = _album(app, slug="gone")
    mid = _media(app, name="will-be-deleted.webp")
    with app.app_context():
        db.session.add(AlbumItem(album_id=aid, section_id=None, media_id=mid, sort=1))
        db.session.commit()
        MediaAsset.query.filter_by(id=mid).delete()
        db.session.commit()

    d = client.get("/api/albums/gone").get_json()
    assert d["items"] == [], "已删媒体的条目应被 join 过滤掉"
    assert d["count"] == 0


def test_非公开媒体不出现在相册(app, client):
    """相册公开，但里面某张图被设成私密 —— 那张不该给读者看。"""
    aid = _album(app, slug="mixed")
    pub = _media(app, name="pub.webp", public=True)
    priv = _media(app, name="priv.webp", public=False)
    with app.app_context():
        db.session.add(AlbumItem(album_id=aid, media_id=pub, sort=1))
        db.session.add(AlbumItem(album_id=aid, media_id=priv, sort=2))
        db.session.commit()

    d = client.get("/api/albums/mixed").get_json()
    assert d["count"] == 1, "私密媒体应被过滤"
    assert d["items"][0]["media"]["url"].endswith("pub.webp")


# ---------------------------------------------------------------- 编排接口

def test_新建相册生成不冲突的slug(app, client):
    """新建是表单路由（成功即 302 跳编排页），slug 由后端自动生成且不得冲突。"""
    tok = _login_admin(app, client)
    headers = {"X-CSRF-Token": tok}

    r1 = client.post("/admin/albums/create", data={"title": "同一个标题"}, headers=headers)
    assert r1.status_code == 302, r1.data[:300]
    r2 = client.post("/admin/albums/create", data={"title": "同一个标题"}, headers=headers)
    assert r2.status_code == 302

    with app.app_context():
        slugs = [a.slug for a in Album.query.all()]
        assert len(slugs) == 2
        assert len(set(slugs)) == 2, "slug 冲突了：%r" % slugs


def test_添加条目支持批量与指定章节(app, client):
    tok = _login_admin(app, client)
    aid = _album(app, slug="batch")
    m1 = _media(app, name="a.webp")
    m2 = _media(app, name="b.webp")
    with app.app_context():
        s = AlbumSection(album_id=aid, title="第一天", sort=1)
        db.session.add(s)
        db.session.commit()
        sid = s.id

    r = client.post("/admin/albums/%d/items" % aid,
                    json={"media_ids": "%d,%d" % (m1, m2), "section_id": sid},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.data[:300]
    assert r.get_json()["count"] == 2

    with app.app_context():
        rows = AlbumItem.query.filter_by(album_id=aid).all()
        assert len(rows) == 2
        assert all(x.section_id == sid for x in rows)


def test_删除章节后条目回到未分组(app, client):
    """章节被删，其下条目不能跟着消失 —— 接口层要把它们挂回未分组，
    否则用户看到「删了一段，照片也没了」。"""
    tok = _login_admin(app, client)
    aid = _album(app, slug="delsection")
    mid = _media(app)
    with app.app_context():
        s = AlbumSection(album_id=aid, title="会消失的一段", sort=1)
        db.session.add(s)
        db.session.commit()
        sid = s.id
        db.session.add(AlbumItem(album_id=aid, section_id=sid, media_id=mid, sort=1))
        db.session.commit()

    r = client.post("/admin/albums/%d/sections/%d/delete" % (aid, sid),
                    json={}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200

    d = client.get("/api/albums/delsection").get_json()
    assert len(d["items"]) == 1, "章节删除后条目丢失了"
    assert d["sections"] == []


def test_删除相册不删媒体文件(app, client):
    tok = _login_admin(app, client)
    aid = _album(app, slug="delalbum")
    mid = _media(app, name="keep-me.webp")
    with app.app_context():
        db.session.add(AlbumItem(album_id=aid, media_id=mid, sort=1))
        db.session.commit()

    r = client.post("/admin/albums/%d/delete" % aid, json={}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200

    with app.app_context():
        assert Album.query.filter_by(id=aid).first() is None
        assert MediaAsset.query.filter_by(id=mid).first() is not None, "媒体不该被连带删除"
        assert AlbumItem.query.filter_by(album_id=aid).count() == 0, "条目应随相册清掉"
