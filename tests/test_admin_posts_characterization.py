"""后台文章管理（myblog/admin/posts.py）回归 / 特征测试（v3.17.14 为「超长文件拆分」建立安全网）。

目的：在拆分 admin/posts.py（851 行）之前，先用测试锁死其最高风险、最易在重构中漂移的
行为，使后续拆分可安全进行（R76/R77 技术债③：先补测试再排期）。
覆盖：
1. 新建文章路由：标题/正文落库、默认发布态、不进回收站。
2. 编辑文章路由：正文更新生效。
3. 软删除路由：in_trash=True 且生成 RecycleBin 快照（restored=False）。
4. 回收站还原路由：in_trash 清回 False、deleted_at 清空、RecycleBin.restored=True。
5. 一键发布路由：翻 published=True 并清空 scheduled_at。

运行：仓库根目录 `python -m pytest tests/ -q`。
说明：测试库为仓库内持久化 myblog/data/blog.db（gitignored），用户名用 uuid 保唯一，
每个用例 finally 清理自建数据，避免唯一约束冲突与污染。
"""
import secrets
import uuid
from datetime import timedelta

from models import db, User, Post, RecycleBin, ROLE_SUPER
from utils import _sign_csrf
from admin._helpers import create_post_core
from _time import utcnow


def _uid():
    return uuid.uuid4().hex[:12]


def _mkuser(role=ROLE_SUPER):
    u = User(username="ap-" + _uid(), email="ap-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False  # 否则 login_required 会把超管跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    """登录（写入 session user_id）并生成与会话绑定的有效 CSRF token。"""
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def _mkpost(author_id, title="特征测试文章", scheduled=False):
    sched = (utcnow() + timedelta(hours=1)) if scheduled else None
    return create_post_core(
        title=title, content="初始正文内容", author_id=author_id,
        published=not scheduled, scheduled_at=sched,
    ).id


def _cleanup(pids=(), rids=(), uids=()):
    RecycleBin.query.filter(RecycleBin.id.in_(list(rids))).delete(synchronize_session=False)
    Post.query.filter(Post.id.in_(list(pids))).delete(synchronize_session=False)
    for u in uids:
        usr = db.session.get(User, u)
        if usr:
            db.session.delete(usr)
    db.session.commit()


def test_new_post_route_creates_published_post(app, client):
    """POST /admin/post/new 落库标题/正文，默认发布、不进回收站。"""
    with app.app_context():
        u = _mkuser()
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/post/new",
                            data={"csrf_token": tok, "title": "新建特征文",
                                  "content": "正文ABC", "published": "on"})
            assert r.status_code in (200, 302), r.status_code
            p = Post.query.filter_by(title="新建特征文").first()
            assert p is not None, "文章未落库"
            assert p.content == "正文ABC"
            assert p.published is True
            assert p.in_trash is False
            _cleanup([p.id], [], [u.id])
        finally:
            _cleanup([], [], [u.id])


def test_edit_post_route_updates_content(app, client):
    """POST /admin/post/<id>/edit 更新正文生效。"""
    with app.app_context():
        u = _mkuser()
        pid = _mkpost(u.id)
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/post/%d/edit" % pid,
                            data={"csrf_token": tok, "title": "特征测试文章",
                                  "content": "改后的正文"})
            assert r.status_code in (200, 302), r.status_code
            assert db.session.get(Post, pid).content == "改后的正文", "正文未更新"
        finally:
            _cleanup([pid], [], [u.id])


def test_soft_delete_moves_to_trash_and_recycle_bin(app, client):
    """POST /admin/post/<id>/delete 标记 in_trash 并生成未还原的 RecycleBin 快照。"""
    with app.app_context():
        u = _mkuser()
        pid = _mkpost(u.id)
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/post/%d/delete" % pid, data={"csrf_token": tok})
            assert r.status_code in (200, 302), r.status_code
            p = db.session.get(Post, pid)
            assert p.in_trash is True, "应标记 in_trash"
            rb = RecycleBin.query.filter_by(post_id=pid, restored=False).first()
            assert rb is not None, "应生成回收站快照"
            _cleanup([pid], [rb.id] if rb else [], [u.id])
        finally:
            _cleanup([], [], [u.id])


def test_restore_from_recycle_bin_clears_trash(app, client):
    """回收站还原：in_trash 清回 False、deleted_at 清空、快照标记 restored。"""
    with app.app_context():
        u = _mkuser()
        pid = _mkpost(u.id)
        tok = _auth(client, u.id)
        client.post("/admin/post/%d/delete" % pid, data={"csrf_token": tok})
        rb = RecycleBin.query.filter_by(post_id=pid, restored=False).first()
        assert rb is not None
        try:
            r = client.post("/admin/recycle-bin/%d/restore" % rb.id, data={"csrf_token": tok})
            assert r.status_code in (200, 302), r.status_code
            p = db.session.get(Post, pid)
            assert p.in_trash is False, "还原后应收回 in_trash"
            assert p.deleted_at is None, "还原后 deleted_at 应清空"
            assert db.session.get(RecycleBin, rb.id).restored is True
        finally:
            _cleanup([pid], [rb.id], [u.id])


def test_publish_now_clears_schedule_and_publishes(app, client):
    """POST /admin/post/<id>/publish-now：翻 published=True 并清空 scheduled_at。"""
    with app.app_context():
        u = _mkuser()
        pid = _mkpost(u.id, scheduled=True)
        try:
            p0 = db.session.get(Post, pid)
            assert p0.published is False and p0.scheduled_at is not None, "前置：应为定时未发布"
            tok = _auth(client, u.id)
            r = client.post("/admin/post/%d/publish-now" % pid,
                            data={"csrf_token": tok}, query_string={"back": "admin.dashboard"})
            assert r.status_code in (200, 302), r.status_code
            p1 = db.session.get(Post, pid)
            assert p1.published is True, "应翻为已发布"
            assert p1.scheduled_at is None, "应清空定时时间"
        finally:
            _cleanup([pid], [], [u.id])
