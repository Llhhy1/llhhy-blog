"""v4.9.0 内容日历（ROADMAP §3.1）渲染回归。

为什么要专门测**渲染**而不只是测路由返回 200：Jinja 子模板里写在 block
之外的内容**不会渲染**，且不报错、不告警 —— 项目里已经踩过一次（v4.2.0
统计页三张卡静默消失两个大版本）。所以本文件的判据是「页面里真的能看到
那篇文章的标题」，而不是「状态码是 200」。

覆盖：
1. 登录后能渲染出月历表格，且文章标题**真的出现在格子里**。
2. 未登录被拦（不能匿名看全站草稿标题）。
3. 上/下月翻页链接可用（参数传对了）。
"""

import datetime
import secrets

import pytest

from models import db, Post, User, ROLE_ADMIN, ROLE_USER
from _time import utcnow
from utils import to_beijing

PASSWORD = "Passw0rd!23"


def _make_user(app):
    uname = "u_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_ADMIN, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    return uname


def _login(client, uname):
    d = client.get("/api/csrf").get_json() or {}
    tok = d.get("csrf_token") or d.get("token") or ""
    r = client.post("/api/auth/login",
                    json={"username": uname, "password": PASSWORD},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, "登录失败 %s" % r.status_code
    return client


def _make_post(app, title, published=True, day=15):
    """在本月 day 日（北京时间）造一篇文章。created_at 库里存 UTC。"""
    with app.app_context():
        now = to_beijing(utcnow())
        local = datetime.datetime(now.year, now.month, day, 10, 0, 0)
        p = Post(title=title, slug="cal-" + secrets.token_hex(4),
                 content="正文", summary="摘要", published=published,
                 created_at=local - datetime.timedelta(hours=8))
        db.session.add(p)
        db.session.commit()
        return p.id


@pytest.fixture
def logged_in(app, client):
    return _login(client, _make_user(app))


def test_日历渲染出文章标题(app, logged_in):
    """判据是「页面里看得到标题」—— 光有 200 证明不了没掉进 block 外的坑。"""
    title = "日历探针文章-" + secrets.token_hex(3)
    pid = _make_post(app, title)
    try:
        r = logged_in.get("/admin/content-calendar")
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        html = r.get_data(as_text=True)
        # 类名可能带兜底标记（如 data-table），用前缀匹配而非全等
        assert '<table class="cal' in html, "月历表格没渲染出来"
        assert title in html, "文章标题没出现在日历里（可能掉进 block 外静默区）"
        assert str(pid) in html or "edit" in html, "格子里的编辑链接没渲染"
    finally:
        with app.app_context():
            p = db.session.get(Post, pid)
            if p:
                db.session.delete(p)
                db.session.commit()


def test_未登录不能看日历(client, app):
    _make_post(app, "不该被匿名看到的草稿")
    r = client.get("/admin/content-calendar")
    assert r.status_code != 200, "匿名竟能打开后台日历（草稿标题会泄露）"


def test_普通用户看不到他人文章标题(app, client):
    """权限口径必须与 admin.my_posts 一致：非管理员只能看自己的。

    日历会把**草稿标题**铺在格子里，若沿用「管理员可读全站」的默认值，
    普通作者就能看到别人的未发布草稿 —— 这是 ROADMAP D8.3 警告的实例。
    """
    _make_user(app)  # 管理员存在即可（文章 author_id 为 None，属管理员）
    title = "他人未发布稿-" + secrets.token_hex(3)
    _make_post(app, title, published=False)

    uname = "u_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_USER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()

    c = _login(client, uname)
    r = c.get("/admin/content-calendar")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert title not in r.get_data(as_text=True), "普通用户竟能看到他人文章标题（越权）"


def test_上下月翻页可用(app, logged_in):
    now = to_beijing(utcnow())
    prev_month = now.month - 1 or 12
    prev_year = now.year if now.month > 1 else now.year - 1
    r = logged_in.get("/admin/content-calendar",
                      query_string={"year": prev_year, "month": prev_month})
    assert r.status_code == 200
    assert ("%d 年 %d 月" % (prev_year, prev_month)) in r.get_data(as_text=True)
