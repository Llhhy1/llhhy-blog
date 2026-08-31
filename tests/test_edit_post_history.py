"""edit_post 版本历史回归测试（v3.10.6 评审 P0 修复）。

守护：编辑文章时「只改标题」「只改正文」都必须触发 _save_post_history。
历史 bug：post.title 已在赋值后比较，导致只改标题时 `post.title != title` 恒为假，
永不存历史（「只改标题」恰恰是最常见的修订场景之一，却丢失版本）。

运行：仓库根目录 `python -m pytest tests/ -q`
注意：测试库为仓库内持久化的 myblog/data/blog.db（gitignored），故用户名/slug 用
uuid 保证唯一、且每个用例 finally 清理自建数据，避免污染与唯一约束冲突。
"""
import secrets
import uuid

from models import db, User, Post, PostHistory, ROLE_SUPER
from utils import _sign_csrf


def _uid():
    return uuid.uuid4().hex[:12]


def _make_admin(app):
    u = User(username="edithist-" + _uid(), email="edithist@test.local")
    u.set_password("test-pass")
    u.role = ROLE_SUPER
    u.must_change_password = False  # 否则 login_required 会把超管跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _make_post(app, title="原标题", content="原正文"):
    p = Post(title=title, slug="edithist-" + _uid(), summary="摘要",
             content=content, published=True)
    db.session.add(p)
    db.session.commit()
    return p.id


def _cleanup(pid, uid):
    PostHistory.query.filter_by(post_id=pid).delete()
    p = db.session.get(Post, pid)
    if p:
        db.session.delete(p)
    u = db.session.get(User, uid)
    if u:
        db.session.delete(u)
    db.session.commit()


def _auth_and_token(client, user_id):
    """登录（写入 session user_id）并生成与会话绑定的有效 CSRF token。

    不调用 generate_csrf_token()（其内部访问 session 代理，在无完整请求上下文的
    session_transaction 里会报 RuntimeError），改为用同一套 _sign_csrf 手写 token，
    直接写入会话，逻辑与 check_csrf_token 对称。
    """
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def _edit(client, pid, token, title=None, content=None):
    data = {"csrf_token": token}
    if title is not None:
        data["title"] = title
    if content is not None:
        data["content"] = content
    return client.post(f"/admin/post/{pid}/edit", data=data)


def test_edit_only_title_saves_history(app, client):
    """P0 核心回归：只改标题必须触发版本历史。"""
    with app.app_context():
        u = _make_admin(app)
        pid = _make_post(app, title="原标题", content="原正文")
        try:
            tok = _auth_and_token(client, u.id)
            before = PostHistory.query.filter_by(post_id=pid).count()
            r = _edit(client, pid, tok, title="新标题", content="原正文")
            after = PostHistory.query.filter_by(post_id=pid).count()
            assert r.status_code in (200, 302), r.status_code
            assert after == before + 1, "只改标题必须触发版本历史（P0 修复）"
            assert db.session.get(Post, pid).title == "新标题"
        finally:
            _cleanup(pid, u.id)


def test_edit_only_content_saves_history(app, client):
    """只改正文也必须触发版本历史（本就应有，作对照）。"""
    with app.app_context():
        u = _make_admin(app)
        pid = _make_post(app, title="标题A", content="原正文")
        try:
            tok = _auth_and_token(client, u.id)
            before = PostHistory.query.filter_by(post_id=pid).count()
            r = _edit(client, pid, tok, title="标题A", content="新正文")
            after = PostHistory.query.filter_by(post_id=pid).count()
            assert r.status_code in (200, 302), r.status_code
            assert after == before + 1, "只改正文必须触发版本历史"
        finally:
            _cleanup(pid, u.id)


def test_edit_no_change_no_history(app, client):
    """无任何变化不应产生多余版本历史。"""
    with app.app_context():
        u = _make_admin(app)
        pid = _make_post(app, title="标题B", content="正文B")
        try:
            tok = _auth_and_token(client, u.id)
            before = PostHistory.query.filter_by(post_id=pid).count()
            r = _edit(client, pid, tok, title="标题B", content="正文B")
            after = PostHistory.query.filter_by(post_id=pid).count()
            assert r.status_code in (200, 302), r.status_code
            assert after == before, "无任何变化不应产生多余版本历史"
        finally:
            _cleanup(pid, u.id)
