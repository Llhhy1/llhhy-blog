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


@pytest.fixture(autouse=True)
def _reset_media_sync_throttle():
    """每条测试结束后清零「磁盘同步节流」计时。

    `admin.media.collect_media()` 为省 IO，60 秒内只扫一次 uploads 目录、
    把没有表记录的历史文件补登记（`_SYNC_AT`）。本文件里
    「媒体库页面显示素材所属相册」那条会调用 `/admin/media`，因而**消耗掉
    这一次同步**；随后 60 秒内手工写进 uploads 的文件就不会登记进
    `media_asset`，把 `test_api_mobile.py::test_媒体库删除需_force_且路径穿越无效`
    打挂（实测复现：`StopIteration`，它靠真实文件断言）。

    正常上传不走这条路（`media_service.save_single()` 直接登记一行），
    所以这是**测试之间的互扰**，不是线上缺陷。谁污染谁清理。
    """
    yield
    try:
        from admin.media import _SYNC_AT
        _SYNC_AT[0] = 0.0
    except Exception:      # noqa: BLE001  清理失败不该让测试变红
        pass


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


def test_相册列表的封面按封面媒体id取(app, client):
    """回归 v5.2.0：列表页把**相册 id** 当封面媒体 id 去查（`[a.id for a in rows]`），
    而相册 id 与媒体 id 是两套自增序列 —— 除偶然相等外一定查不到，
    于是「编排页设好封面 → 回列表还是无封面」（用户实测反馈）。

    这里刻意让两者**错开**（相册 id=1，封面媒体 id=2），
    否则「相册 id == 媒体 id」时旧代码会碰巧取到一张图，测试假通过。
    """
    _login_admin(app, client)
    _media(app, "first.webp")            # 媒体 id=1，谁都别当封面
    m2 = _media(app, "cover.webp")       # 媒体 id=2 → 相册封面
    aid = _album(app, cover_media_id=m2)
    with app.app_context():
        assert aid != m2, "相册 id 与封面媒体 id 必须不同，否则测不出这个 bug"

    r = client.get("/admin/albums")
    body = r.data.decode("utf-8")
    assert "/static/uploads/cover.webp" in body, "列表页应渲染封面图"
    assert "无封面" not in body


def test_相册列表_没有封面时显示占位(app, client):
    """上一条的对照：真没封面时必须显示「无封面」，
    否则「无封面 not in body」这种断言会因为文案改了就假通过。"""
    _login_admin(app, client)
    _album(app)
    r = client.get("/admin/albums")
    assert "无封面" in r.data.decode("utf-8")


def test_相册编排页显示当前封面(app, client):
    """编排页的 cover_url 与列表页取数口径必须一致（都认 cover_media_id）。"""
    _login_admin(app, client)
    m = _media(app, "cover.webp")
    aid = _album(app, cover_media_id=m)
    r = client.get("/admin/albums/%d/edit" % aid)
    body = r.data.decode("utf-8")
    assert "当前封面" in body
    assert "/static/uploads/cover.webp" in body


def test_相册编排页能渲染(app, client):
    """编辑页是最容易悄悄坏的地方：Jinja 的 Undefined 不报错，
    页面「看起来正常但某块空白」。所以必须真的渲染一次。

    v5.2.1 起每张图的输入框显示的是**素材标题**（名字只有一份），
    不再是 album_item.caption —— 后者已冻结、不再写入。
    """
    _login_admin(app, client)
    aid = _album(app)
    mid = _media(app, "gujie.webp")      # 素材标题 = "gujie"
    with app.app_context():
        s = AlbumSection(album_id=aid, title="D1 畲乡之窗", summary="婚嫁表演 14:30", sort=1)
        db.session.add(s)
        db.session.commit()
        sid = s.id
        db.session.add(AlbumItem(album_id=aid, section_id=sid, media_id=mid, sort=1))
        db.session.add(AlbumItem(album_id=aid, section_id=None, media_id=mid, sort=2))
        db.session.commit()

    r = client.get("/admin/albums/%d/edit" % aid)
    assert r.status_code == 200, r.data[:600]
    body = r.data.decode("utf-8")
    assert "D1 畲乡之窗" in body, "章节没渲染"
    assert 'value="gujie"' in body, "素材标题没渲染进输入框"
    assert "行程概览" in body and "小提示" in body, "游记区块没渲染"


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


# ---------------------------------------------------------------- 保存端点双模式
# v5.1.3 上线后实测：编排页「保存相册信息」是**传统表单提交**，而 album_update
# 当时无条件返回 JSON —— 浏览器把响应体当页面渲染，用户看到一串
# {"ok":true,"slug":"album-1793152410"}，既没返回入口也不知道成没成。
# 下面三条锁住「表单走重定向、fetch 走 JSON」这个契约。


def test_保存相册信息_表单提交应重定向而不是返回JSON(app, client):
    """浏览器表单提交（非 JSON 请求）必须 302 回编排页，不能把 JSON 当页面。"""
    tok = _login_admin(app, client)
    aid = _album(app, slug="form-mode")

    r = client.post("/admin/albums/%d/update" % aid,
                    data={"title": "改过的标题", "slug": "form-mode", "summary": "新摘要"},
                    headers={"X-CSRF-Token": tok})

    assert r.status_code == 302, "表单提交应重定向，实际 %d（%s）" % (
        r.status_code, r.data[:120])
    assert "/admin/albums/%d/edit" % aid in r.headers.get("Location", ""), \
        "重定向应回到编排页，实际 Location=%s" % r.headers.get("Location")
    assert b'"ok"' not in r.data, "响应体不该是 JSON"

    with app.app_context():
        a = Album.query.filter_by(id=aid).first()
        assert a.title == "改过的标题", "标题没保存进去"
        assert a.summary == "新摘要"

    # 跟随重定向：用户必须看到「已保存」的反馈，否则点完不知道成没成
    r2 = client.get(r.headers["Location"])
    assert r2.status_code == 200, r2.data[:200]
    body = r2.get_data(as_text=True)
    assert "相册信息已保存" in body, "重定向后的页面没有渲染出保存提示"
    assert 'class="flash"' in body, "flash 容器没出现"


def test_保存相册信息_JSON提交仍返回JSON(app, client):
    """编排页其余操作走 fetch（application/json），契约不能改坏。"""
    tok = _login_admin(app, client)
    aid = _album(app, slug="json-mode")

    r = client.post("/admin/albums/%d/update" % aid,
                    json={"title": "fetch 存的", "slug": "json-mode"},
                    headers={"X-CSRF-Token": tok})

    assert r.status_code == 200, r.data[:200]
    d = r.get_json()
    assert d["ok"] is True
    assert d["slug"] == "json-mode"
    with app.app_context():
        assert Album.query.filter_by(id=aid).first().title == "fetch 存的"


def test_保存相册信息_表单校验失败也重定向(app, client):
    """校验失败时同样不能返回 JSON——否则用户看到 {"ok":false,...} 卡在那。"""
    tok = _login_admin(app, client)
    aid = _album(app, slug="form-bad")

    # 标题为空
    r = client.post("/admin/albums/%d/update" % aid, data={"title": "  "},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 302, "校验失败也应重定向，实际 %d" % r.status_code
    assert b'"ok"' not in r.data

    # slug 被别的相册占用
    _album(app, slug="taken-slug")
    r = client.post("/admin/albums/%d/update" % aid,
                    data={"title": "正常标题", "slug": "taken-slug"},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 302, "slug 冲突也应重定向，实际 %d" % r.status_code

    with app.app_context():
        assert Album.query.filter_by(id=aid).first().slug == "form-bad", "冲突时不该改动 slug"


# ---------------------------------------------------------------- 媒体库 ↔ 相册
# v5.2.0 打通两个页面。这里的断言重点不是「接口能调通」，而是
# **不产生第二份数据** —— 相册只引用 media_id，图注留空时不复制素材标题，
# 由前端回退显示。


def test_媒体库页面显示素材所属相册(app, client):
    """媒体库每行要能看出「这张图用在哪个相册」，否则只能凭记忆找。"""
    _login_admin(app, client)
    aid = _album(app, slug="bridge-list", title="被引用的相册")
    mid = _media(app, name="bridge.webp")
    with app.app_context():
        db.session.add(AlbumItem(album_id=aid, media_id=mid, sort=1))
        db.session.commit()

    r = client.get("/admin/media")
    assert r.status_code == 200, r.data[:200]
    body = r.get_data(as_text=True)
    assert "被引用的相册" in body, "媒体库没有显示素材所属相册"
    assert "media-album-tag" in body
    assert "to-album" in body, "缺少「加入相册」入口"


def test_媒体库加入相册_成功且图注留空(app, client):
    """加入 = 只写一条引用。不许把素材标题抄进 caption（否则改标题不同步）。"""
    tok = _login_admin(app, client)
    aid = _album(app, slug="bridge-add", title="目标相册")
    mid = _media(app, name="to-add.webp")
    with app.app_context():
        MediaAsset.query.filter_by(id=mid).first().title = "原素材标题"
        db.session.commit()

    r = client.post("/admin/media/%d/to-album" % mid, json={"album_id": aid},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.data[:200]
    d = r.get_json()
    assert d["ok"] is True and d["album_id"] == aid
    assert d["album_title"] == "目标相册"

    with app.app_context():
        it = AlbumItem.query.filter_by(album_id=aid, media_id=mid).first()
        assert it is not None
        assert it.caption == "", "caption 必须留空（前台回退显示素材标题，不复制）"


def test_媒体库加入相册_章节必须属于该相册(app, client):
    tok = _login_admin(app, client)
    aid = _album(app, slug="bridge-sec")
    other = _album(app, slug="bridge-other")
    with app.app_context():
        s = AlbumSection(album_id=other, title="别人的章节", sort=1)
        db.session.add(s)
        db.session.commit()
        sid = s.id
    mid = _media(app, name="sec.webp")

    r = client.post("/admin/media/%d/to-album" % mid,
                    json={"album_id": aid, "section_id": sid},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 400, "跨相册的章节必须拒绝"
    with app.app_context():
        assert AlbumItem.query.filter_by(album_id=aid).count() == 0


def test_媒体库加入相册_相册不存在(app, client):
    tok = _login_admin(app, client)
    mid = _media(app, name="noalbum.webp")
    r = client.post("/admin/media/%d/to-album" % mid, json={"album_id": 999999},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 404


def test_相册详情_图注留空时素材标题可取(app, client):
    """前端 capOf() 用 media.title 兜底，所以后端必须把标题带出来。"""
    aid = _album(app, slug="caption-fallback", public=True)
    mid = _media(app, name="fallback.webp")
    with app.app_context():
        MediaAsset.query.filter_by(id=mid).first().title = "梯田晨雾"
        db.session.add(AlbumItem(album_id=aid, media_id=mid, caption="", sort=1))
        db.session.commit()

    d = client.get("/api/albums/caption-fallback").get_json()
    assert len(d["items"]) == 1
    it = d["items"][0]
    assert it["caption"] == "", "caption 应保持空（不复制素材标题）"
    assert it["media"]["title"] == "梯田晨雾", "media.title 必须带出来供前端回退"


# ---------------------------------------------------------------- 名字只有一份（v5.2.1）

def test_编排页改名写进素材标题_而不是另存副本(app, client):
    """用户实测反馈：「相册里改了文件名称，媒体库的名称不会跟着改」。

    v5.2.0 把名字拆成两处（album_item.caption 与 media_asset.title），
    用户不认这个区分。v5.2.1 起名字只存在 media_asset.title：
    在编排页改名 = 改媒体库标题，不允许再往 caption 里存一份副本。
    """
    tok = _login_admin(app, client)
    mid = _media(app, name="orig.webp")            # 标题初始为 "orig"
    aid = _album(app, slug="one-name")
    with app.app_context():
        it = AlbumItem(album_id=aid, media_id=mid, sort=1)
        db.session.add(it)
        db.session.commit()
        iid = it.id

    r = client.post("/admin/albums/%d/items/%d" % (aid, iid),
                    json={"media_title": "意溪渡口"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.data[:200]

    with app.app_context():
        m = MediaAsset.query.filter_by(id=mid).first()
        assert m.title == "意溪渡口", "改名必须落到素材标题上（媒体库才会跟着变）"
        assert AlbumItem.query.filter_by(id=iid).first().caption == "", "不得再存副本"


def test_媒体库改名后编排页显示新名字(app, client):
    """反方向也要通：媒体库改标题 → 编排页输入框跟着变。

    编排页读的是 media_asset.title 本身（不是加入相册时抄的副本），
    所以这条其实在测「没有副本」。
    """
    _login_admin(app, client)
    mid = _media(app, name="reverse.webp")
    aid = _album(app, slug="reverse-one")
    with app.app_context():
        db.session.add(AlbumItem(album_id=aid, media_id=mid, sort=1))
        MediaAsset.query.filter_by(id=mid).first().title = "潮州1"
        db.session.commit()

    r = client.get("/admin/albums/%d/edit" % aid)
    assert 'value="潮州1"' in r.data.decode("utf-8")


def test_旧页面发caption也落到素材标题(app, client):
    """v5.2.0 的输入框发的是 caption 字段。

    浏览器缓存未过期时旧页面还会这么发 —— 不能让它在库里另存一份，
    否则刚消灭的「两份名字」又从旧页面长回来。
    """
    tok = _login_admin(app, client)
    mid = _media(app, name="legacy.webp")
    aid = _album(app, slug="legacy-cap")
    with app.app_context():
        it = AlbumItem(album_id=aid, media_id=mid, sort=1)
        db.session.add(it)
        db.session.commit()
        iid = it.id

    r = client.post("/admin/albums/%d/items/%d" % (aid, iid),
                    json={"caption": "小猫"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.data[:200]
    with app.app_context():
        assert MediaAsset.query.filter_by(id=mid).first().title == "小猫"
        assert AlbumItem.query.filter_by(id=iid).first().caption == ""


# ---------------------------------------------------------------- 样式回归守卫（v5.2.2）
#
# 这两条防的都是「看着像 CSS 小改，实际把功能裁掉」的事故 —— 页面上不报错，
# 只是某些元素看不见，靠肉眼看截图很难复现，所以钉死在测试里。

import io as _io            # noqa: E402
import os as _os            # noqa: E402
import re as _re            # noqa: E402

_CSS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                     "myblog", "static", "admin.css")
_TPL = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                     "myblog", "templates", "admin", "album_edit.html")


def test_编辑器容器不能被药丸圆角命中(app):
    """`.md-stage` 的 class 是 `md-stage view-split` —— `view-split` 是**视图状态**。

    v5.2.0 的观感层把 `.view-split` 和按钮类 `.md-vw` 并列写成一条
    `border-radius: 999px` 规则，于是整个 62vh 高的编辑器容器被设成药丸圆角：
    浏览器把半径压到高度的一半，工具栏左右各几百 px 落进圆角裁切区，
    「B」「粗体」和右侧的视图切换按钮全部看不见（用户实测「编辑功能显示不全」）。

    守卫：`view-split` 只能作为后代选择器的前缀出现在 `view-*` 状态规则里，
    不能出现在任何给自身画圆角/边框的选择器列表中。
    """
    css = _io.open(_CSS, encoding="utf-8").read()
    assert ".view-split, .md-vw" not in css, "view-split 是 md-stage 的状态类，不能混进按钮选择器"
    # 只允许 `.view-split .xxx` 这种后代写法，不允许 `.view-split {` / `.view-split,`
    bad = _re.findall(r"\.view-split\s*[,{]", css)
    assert not bad, "发现把 .view-split 当元素本身选择的地方：%r" % bad


def test_选图格子有行高兜底与名字(app):
    """手机端「已上传的图片堆叠在一起、很容易选错」的回归守卫。

    实测根因：`.album-picker-grid` 的 `grid-auto-rows: auto` 按 min-content 算高度，
    而格子高度来自 `aspect-ratio`（min-content 里算不出），四行被均分容器后
    每行只剩 85px，图片被 `overflow:hidden` 裁成一条条。

    两道防线缺一不可：
      1. `grid-auto-rows: minmax(96px, auto)` —— 不依赖比例的确定下限；
      2. 每格压一条名字（`.album-picker-name`）—— 一屏七八张缩略图，
         只靠画面分不清哪张是哪张。
    """
    css = _io.open(_CSS, encoding="utf-8").read()
    assert "grid-auto-rows: minmax(" in css, "选图网格必须给行高下限，否则会被压扁"
    assert ".album-picker-name" in css, "选图格子必须有名字层"

    tpl = _io.open(_TPL, encoding="utf-8").read()
    assert "album-picker-thumb" in tpl, "缩略图要包一层 thumb，比例与裁切由它负责"
    assert "album-picker-name" in tpl, "渲染逻辑要输出名字"
    assert "readJson" in tpl, "上传链路必须用 readJson，否则 500/413 会抛 Unexpected token '<'"
