"""后台「文章管理」批量操作回归（v4.8.1 修「批量管理没有作用」）。

背景（真实故障）：
1. 批量条 `<form id="bulk-form">` 在表格**之前**就闭合了，而行复选框在 `<table>` 里
   → 复选框**不在表单内** → JS 的 `form.querySelectorAll('.row-check')` 永远是空集合
   → 全选失效、「已选 N 篇」永远为空、点「执行」必定弹「请先勾选要操作的文章」
   并 `preventDefault()`；即便提交，`ids` 也一个都带不上。
   修法：复选框加 HTML5 `form="bulk-form"` 关联（表格里每篇还有发布/删除等内联表单，
   **不能**把表格包进批量表单 —— 会造成表单嵌套，HTML 非法、浏览器丢弃内层）。
2. 「分类」「分区」两个下拉原本都叫 `name="value"`，后端 `request.form.get("value")`
   只取第一个 → 「移入分区」永远拿到「分类」的空值而报「请选择目标」。
   修法：分别命名 `category_value` / `series_value`，按 action 取（保留 `value` 兜底）。

测试数据现场生成、用完清理；不联网。
"""
import datetime
import re
import secrets

import pytest

from models import Category, Post, Series, User, ROLE_SUPER, db

PASSWORD = "Passw0rd!23"


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


@pytest.fixture()
def admin_client(client, app):
    uname = "bulkadm_" + secrets.token_hex(4)
    uid = None
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    r = client.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    yield client
    with app.app_context():
        row = db.session.get(User, uid)
        if row:
            db.session.delete(row)
        db.session.commit()


@pytest.fixture()
def two_posts(app, admin_client):
    """两篇草稿 + 一个分类 + 一个分区；用例结束清理。"""
    tag = secrets.token_hex(4)
    now = datetime.datetime.utcnow()
    with app.app_context():
        cat = Category(name="批量测试分类_" + tag, slug="bulk-cat-" + tag)
        ser = Series(name="批量测试分区_" + tag, slug="bulk-ser-" + tag)
        db.session.add_all([cat, ser])
        db.session.flush()
        ids = []
        for i in (1, 2):
            p = Post(title="批量测试文章%d-%s" % (i, tag), slug="bulk-post-%d-%s" % (i, tag),
                     content="正文", summary="摘要", published=False,
                     created_at=now, updated_at=now)
            db.session.add(p)
            db.session.flush()
            ids.append(p.id)
        db.session.commit()
        data = {"cat_id": cat.id, "ser_id": ser.id, "ids": ids}
    yield data
    with app.app_context():
        from models import RecycleBin
        for row in RecycleBin.query.filter(RecycleBin.post_id.in_(data["ids"])).all():
            db.session.delete(row)
        for pid in data["ids"]:
            row = db.session.get(Post, pid)
            if row:
                db.session.delete(row)
        for mid, model in ((data["cat_id"], Category), (data["ser_id"], Series)):
            obj = db.session.get(model, mid)
            if obj:
                db.session.delete(obj)
        db.session.commit()


def _post_bulk(client, action, ids, **fields):
    """提交批量表单。`ids` 是**多个同名键**（真实表单就是这样），必须用 MultiDict。"""
    from werkzeug.datastructures import MultiDict
    payload = MultiDict()
    payload.add("action", action)
    for i in ids:
        payload.add("ids", i)
    for k, v in fields.items():
        payload.add(k, v)
    return client.post("/admin/posts/bulk", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)})


# ---------- ① 结构性回归：复选框必须关联到批量表单 ----------

def test_row_checkboxes_are_associated_with_bulk_form(admin_client, two_posts):
    """核心回归：**每个**行复选框都必须带 `form="bulk-form"`。

    复选框不在 <form> 内（表格里还有每篇的内联表单，包进来会表单嵌套非法），
    只能靠 HTML5 的 form 属性关联。缺了它 → 前端查不到勾选、提交也不带 ids
    → 表现就是「批量管理没有作用」。
    """
    r = admin_client.get("/admin/my-posts")
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    html = r.get_data(as_text=True)
    assert 'id="bulk-form"' in html, "页面上没有批量表单"

    inputs = re.findall(r'<input[^>]*class="row-check"[^>]*>', html)
    assert len(inputs) >= 2, "没渲染出行复选框（页面结构变了？）"
    for i in inputs:
        assert 'form="bulk-form"' in i, \
            "行复选框没有用 form 属性关联批量表单（批量操作会完全失效）：%s" % i


# ---------- ② 批量操作真的生效 ----------

def test_bulk_publish_sets_published(admin_client, app, two_posts):
    ids = two_posts["ids"]
    r = _post_bulk(admin_client, "publish", ids)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    with app.app_context():
        for pid in ids:
            assert db.session.get(Post, pid).published is True, "批量发布没生效"


def test_bulk_unpublish_sets_draft(admin_client, app, two_posts):
    ids = two_posts["ids"]
    with app.app_context():
        for pid in ids:
            db.session.get(Post, pid).published = True
        db.session.commit()
    r = _post_bulk(admin_client, "unpublish", ids)
    assert r.status_code == 302
    with app.app_context():
        for pid in ids:
            assert db.session.get(Post, pid).published is False, "批量转草稿没生效"


# ---------- ③ 两个下拉同名导致的「移入分区」失效 ----------

def test_bulk_move_to_series_ignores_empty_category_value(admin_client, app, two_posts):
    """「移入分区」必须真的生效。

    变异验证：把后端改回 `request.form.get("value")`（两个下拉同名，取到排前面的
    分类空值）→ 此题应变红。这里刻意同时提交空的 category_value，模拟真实表单。
    """
    ids = two_posts["ids"]
    r = _post_bulk(admin_client, "series", ids,
                   category_value="", series_value=two_posts["ser_id"])
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    with app.app_context():
        for pid in ids:
            p = db.session.get(Post, pid)
            assert p.series_id == two_posts["ser_id"], \
                "移入分区没生效（又取到分类的空值了）：series_id=%s" % p.series_id


def test_bulk_move_to_category_ignores_empty_series_value(admin_client, app, two_posts):
    """「移入分类」同理：不能因为分区下拉排在后面就取错。"""
    ids = two_posts["ids"]
    r = _post_bulk(admin_client, "category", ids,
                   category_value=two_posts["cat_id"], series_value="")
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    with app.app_context():
        for pid in ids:
            p = db.session.get(Post, pid)
            assert p.category_id == two_posts["cat_id"], \
                "移入分类没生效：category_id=%s" % p.category_id


def test_bulk_delete_moves_to_trash(admin_client, app, two_posts):
    ids = two_posts["ids"]
    r = _post_bulk(admin_client, "delete", ids)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    with app.app_context():
        for pid in ids:
            assert db.session.get(Post, pid).in_trash is True, "批量移入回收站没生效"


def test_bulk_series_survives_both_selects_submitted(admin_client, app, two_posts):
    """最坏情况兜底：JS 没生效、两个下拉**都带着值**被提交时，也必须按 action 取对那个。

    这是「后端按 action 取」相对「只靠前端 disabled」的价值 —— 前端失效也不至于静默做错。
    """
    ids = two_posts["ids"]
    r = _post_bulk(admin_client, "series", ids,
                   category_value=two_posts["cat_id"], series_value=two_posts["ser_id"])
    assert r.status_code == 302
    with app.app_context():
        p = db.session.get(Post, ids[0])
        assert p.series_id == two_posts["ser_id"], "两个下拉都提交时取错了字段"
        assert p.category_id != two_posts["cat_id"], "不该顺手改分类"


def test_bulk_without_ids_does_nothing(admin_client, app, two_posts):
    """没勾选时应给出提示并原样返回，不能误伤文章。"""
    r = _post_bulk(admin_client, "publish", [])
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Post, two_posts["ids"][0]).published is False
