"""v4.8.6 后台「常搜词汇」重置按钮（/admin/stats/reset-searches）回归。

聚焦三件事，全部对齐既有的 /admin/audit-logs/clear 网关（同文件 stats.py
line 174-176 的 @login_required + @super_required）：

1. 匿名访问必须被 @login_required 拦截（跳转登录），不能动库。
2. 普通管理员（ROLE_ADMIN，非超管）必须被 @super_required 拦成 403。
3. 超管 + 合法 CSRF 才能清空 SearchLog，且跳转回 stats 页、有审计落库。

外加一道**正反双向**校验（审计组方法论：只验「能拦」会假绿）：
4. 超管但**缺 CSRF token** 必须被全局钩子拒掉，且 SearchLog 一条不删 ——
   证明 CSRF 是真在生效，而不是「永远放行」的空守门员。
"""

import secrets

import pytest

from models import AuditLog, db, SearchLog, User, ROLE_SUPER, ROLE_ADMIN

PASSWORD = "Passw0rd!23"


def _make_user(app, role):
    uname = "u_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=role, must_change_password=False)
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


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _seed_searches(app, n=3):
    # 先清空再插，保证每个用例独立（本会话 DB 跨用例共享，否则计数会累加）。
    with app.app_context():
        SearchLog.query.delete()
        db.session.commit()
        for i in range(n):
            db.session.add(SearchLog(keyword="kw-%d" % i))
        db.session.commit()
        return SearchLog.query.count()


@pytest.fixture()
def admin_client(client, app):
    """普通管理员（非超管），用于断言 403。"""
    uname = _make_user(app, ROLE_ADMIN)
    return _login(client, uname)


@pytest.fixture()
def super_client(client, app):
    uname = _make_user(app, ROLE_SUPER)
    return _login(client, uname)


def test_anon_cannot_reset_searches(client, app):
    """匿名必须被拦截（CSRF 钩子先于登录校验返回 403），且库一条不删。"""
    before = _seed_searches(app, 3)
    r = client.post("/admin/stats/reset-searches")
    # CSRF 钩子对无 token 请求直接 403；无论何种拒绝码，关键是不能删数据。
    assert r.status_code != 200, "匿名竟成功到达路由：%s" % r.status_code
    with app.app_context():
        assert SearchLog.query.count() == before, "匿名把搜索记录删了"


def test_normal_admin_forbidden(admin_client, app):
    """普通管理员须被 @super_required 拦成 403，且库不删。"""
    before = _seed_searches(app, 3)
    r = admin_client.post("/admin/stats/reset-searches", headers=_csrf(admin_client))
    assert r.status_code == 403, "非超管未被拦：%s" % r.status_code
    with app.app_context():
        assert SearchLog.query.count() == before, "非超管把搜索记录删了"


def test_super_admin_clears_searches(super_client, app):
    """超管 + 合法 CSRF 才能清空，并落审计、跳回 stats。"""
    before = _seed_searches(app, 3)
    assert before == 3
    r = super_client.post("/admin/stats/reset-searches",
                          headers=_csrf(super_client), follow_redirects=False)
    assert r.status_code in (302, 303), "超管清空未成功：%s" % r.status_code
    with app.app_context():
        assert SearchLog.query.count() == 0, "超管清空后仍有残留"
        audit = db.session.query(AuditLog).filter(
            AuditLog.action == "clear", AuditLog.target == "search_log"
        ).order_by(AuditLog.id.desc()).first()
        assert audit is not None, "清空操作未落审计"


def test_csrf_required_even_for_super(super_client, app):
    """正反双向：超管但缺 CSRF token 必须被全局钩子拒掉，库不删。

    这是防「空守门员」的关键反例——若 CSRF 校验是空的，这道用例会变红，
    证明防护真实存在。
    """
    before = _seed_searches(app, 3)
    r = super_client.post("/admin/stats/reset-searches")  # 不带 X-CSRF-Token
    assert r.status_code != 200, "缺 CSRF 竟放行了"
    with app.app_context():
        assert SearchLog.query.count() == before, "缺 CSRF token 仍删了数据"


def test_stats_page_renders_reset_button(super_client):
    """渲染测试：stats 页必须 200，且含重置表单（action + csrf + 按钮）。

    防止「写了路由但模板没渲染出按钮」或「页面 500」。
    """
    r = super_client.get("/admin/stats")
    assert r.status_code == 200, "stats 页渲染失败：%s" % r.status_code
    body = r.get_data(as_text=True)
    assert "reset-searches" in body, "页面未渲染出重置按钮表单"
    assert "stats-reset-btn" in body, "重置按钮样式类缺失"
    assert "csrf_token" in body, "表单缺少 CSRF token 隐藏域"
