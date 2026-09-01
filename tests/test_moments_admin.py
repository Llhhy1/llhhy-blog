"""微动态（广场 / 个人动态）后台管理回归测试（v3.12.0 新增功能）。

守护：此前 /api/moment 只提供发布/点赞/评论，动态发布后无法编辑、无法删除。
本测试锁死后台管理（`myblog/admin/moments.py`）的四条关键行为：
1. 编辑正文生效并写审计日志；空内容 / 超 500 字被拒（与前台发布口径一致）。
2. 删除动态级联删除其下评论，且不影响其它动态。
3. 跨动态删评论（mid 与 cid 不匹配）必须 404 —— 防改 id 越权删除。
4. 普通用户（role=user）访问后台微动态页被拦截。

运行：仓库根目录 `python -m pytest tests/ -q`
注意：测试库为仓库内持久化的 myblog/data/blog.db（gitignored），故用户名用
uuid 保证唯一、且每个用例 finally 清理自建数据，避免污染与唯一约束冲突。
"""
import secrets
import uuid

from models import db, User, Moment, MomentComment, AuditLog, ROLE_SUPER, ROLE_USER
from utils import _sign_csrf


def _uid():
    return uuid.uuid4().hex[:12]


def _mkuser(role=ROLE_SUPER):
    u = User(username="mom-" + _uid(), email="mom-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False  # 否则 login_required 会把超管跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _mk(user_id, content="原始动态内容"):
    m = Moment(author_id=user_id, content=content)
    db.session.add(m)
    db.session.commit()
    return m.id


def _mkcomment(moment_id, author="路人", content="评论内容"):
    c = MomentComment(moment_id=moment_id, author=author, content=content)
    db.session.add(c)
    db.session.commit()
    return c.id


def _cleanup(mids=(), uids=()):
    MomentComment.query.filter(MomentComment.moment_id.in_(list(mids))).delete(
        synchronize_session=False)
    Moment.query.filter(Moment.id.in_(list(mids))).delete(synchronize_session=False)
    for u in uids:
        usr = db.session.get(User, u)
        if usr:
            db.session.delete(usr)
    db.session.commit()


def _auth(client, user_id):
    """登录（写入 session user_id）并生成与会话绑定的有效 CSRF token。

    不调用 generate_csrf_token()（其内部访问 session 代理，在无完整请求上下文的
    session_transaction 里会报 RuntimeError），改用同一套 _sign_csrf 手写 token，
    直接写入会话，逻辑与 check_csrf_token 对称。
    """
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def test_edit_moment_updates_content_and_logs_audit(app, client):
    """编辑正文生效，并写入一条 action=edit / target=moment 的审计日志。"""
    with app.app_context():
        u = _mkuser()
        mid = _mk(u.id)
        try:
            tok = _auth(client, u.id)
            before = AuditLog.query.filter_by(target="moment", action="edit").count()
            r = client.post("/admin/moment/%d/edit" % mid,
                            data={"csrf_token": tok, "content": "修改后的动态内容"})
            assert r.status_code in (200, 302), r.status_code
            assert db.session.get(Moment, mid).content == "修改后的动态内容"
            assert AuditLog.query.filter_by(target="moment", action="edit").count() == before + 1
        finally:
            _cleanup([mid], [u.id])


def test_edit_moment_rejects_empty_and_too_long(app, client):
    """空内容与超过 500 字都被拒（与前台 post_moment 口径一致）。"""
    with app.app_context():
        u = _mkuser()
        mid = _mk(u.id)
        try:
            tok = _auth(client, u.id)
            client.post("/admin/moment/%d/edit" % mid,
                        data={"csrf_token": tok, "content": "   "})
            assert db.session.get(Moment, mid).content == "原始动态内容", "空内容不得保存"

            client.post("/admin/moment/%d/edit" % mid,
                        data={"csrf_token": tok, "content": "字" * 501})
            assert db.session.get(Moment, mid).content == "原始动态内容", "超 500 字不得保存"

            client.post("/admin/moment/%d/edit" % mid,
                        data={"csrf_token": tok, "content": "字" * 500})
            assert db.session.get(Moment, mid).content == "字" * 500, "正好 500 字应放行"
        finally:
            _cleanup([mid], [u.id])


def test_delete_moment_cascades_comments(app, client):
    """删除动态级联删除其下评论，且不影响其它动态的评论。"""
    with app.app_context():
        u = _mkuser()
        m1 = _mk(u.id, "待删除的动态")
        m2 = _mk(u.id, "保留的动态")
        c1 = _mkcomment(m1, "A", "会跟着删")
        c2 = _mkcomment(m2, "B", "必须保留")
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/moment/%d/delete" % m1, data={"csrf_token": tok})
            assert r.status_code in (200, 302), r.status_code
            assert db.session.get(Moment, m1) is None
            assert db.session.get(MomentComment, c1) is None, "评论必须级联删除"
            assert db.session.get(MomentComment, c2) is not None, "其它动态评论不受影响"
        finally:
            _cleanup([m1, m2], [u.id])


def test_delete_comment_from_other_moment_is_404(app, client):
    """跨动态删评论（改 mid 删别家的 cid）必须 404，防越权。"""
    with app.app_context():
        u = _mkuser()
        m1 = _mk(u.id, "动态一")
        m2 = _mk(u.id, "动态二")
        cid = _mkcomment(m2, "C", "属于动态二")
        try:
            tok = _auth(client, u.id)
            r = client.post("/admin/moment/%d/comment/%d/delete" % (m1, cid),
                            data={"csrf_token": tok})
            assert r.status_code == 404, "跨动态删评论必须 404，实际 %s" % r.status_code
            assert db.session.get(MomentComment, cid) is not None, "越权删除不得生效"
        finally:
            _cleanup([m1, m2], [u.id])


def test_moments_admin_page_requires_admin_role(app, client):
    """普通用户（role=user）访问后台微动态页被拦截，且改不动数据。"""
    with app.app_context():
        u = _mkuser()
        mid = _mk(u.id)
        plain = _mkuser(ROLE_USER)
        try:
            _auth(client, plain.id)
            r = client.get("/admin/moments")
            assert r.status_code == 302, "普通用户应被重定向，实际 %s" % r.status_code
            r2 = client.post("/admin/moment/%d/delete" % mid, data={"csrf_token": "x"})
            assert db.session.get(Moment, mid) is not None, "普通用户不得删除动态"
        finally:
            _cleanup([mid], [u.id, plain.id])
