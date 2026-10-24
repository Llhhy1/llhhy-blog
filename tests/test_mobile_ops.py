"""移动端第二批「数据与设置」端点（D8.3 ②，v4.10.0）回归。

断言优先级是**权限**与**不泄漏**，不是字段好不好看 —— 这批端点把「审计日志、
全部站点配置、用户列表」开成了 JSON，风险面比内容管理更大：

1. **未登录 401、角色不足 403，且必须是 JSON**（不能是 302 登录页）。
2. **逐条对齐后台页面装饰器**：审计 / 备份 / 设置 / SEO / 证书 / 用户 = 超管，
   统计报表 = 管理员（后台 `admin.stats` 就是 `@admin_required`）。
3. **凭据类键一律不出现在响应里**（`mail_password` / `backup_oss_secret` /
   推送 token …）—— 用「整个响应文本不含敏感值」来断言，而不是只看字段名。
4. **邮箱遮敏**：超管拿到的也是 `ab***@ex***.com`，不是完整邮箱。
5. **改角色三条硬约束**：不能改自己、角色白名单、改后 `session_version+1`。
"""
import secrets

import pytest

from models import User, AuditLog, db, ROLE_ADMIN, ROLE_SUPER, ROLE_USER
from utils import _sign_csrf

SUPER_ONLY = [
    "/api/mobile/audit-logs",
    "/api/mobile/backups",
    "/api/mobile/settings",
    "/api/mobile/seo/summary",
    "/api/mobile/cert",
    "/api/mobile/users",
]


@pytest.fixture(autouse=True)
def _isolate_rate_limit():
    from utils.net import _RATE
    _RATE.clear()
    yield
    _RATE.clear()


def _mkuser(role=ROLE_SUPER, email=None):
    u = User(username="mops-" + secrets.token_hex(5),
             email=email or ("mops-%s@example.com" % secrets.token_hex(4)))
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def _req(client, method, path, tok=None, payload=None):
    headers = {"X-CSRF-Token": tok} if tok else {}
    return getattr(client, method)(path, json=payload, headers=headers)


def _drop(users=()):
    for uid in users:
        u = db.session.get(User, uid)
        if u:
            db.session.delete(u)
    db.session.commit()


# ------------------------------------------------------------------ 权限闸门


def test_未登录一律401且是json(client):
    for path in SUPER_ONLY + ["/api/mobile/stats/report"]:
        r = client.get(path)
        assert r.status_code == 401, (path, r.status_code)
        assert "error" in (r.get_json() or {}), path
        assert (r.content_type or "").startswith("application/json"), path


def test_管理员进不了超管专属端点(app, client):
    """这批里只有统计报表对管理员开放，其余全部超管。

    **为什么必须逐条测**：`_role(super_only=True)` 写漏一个参数时端点照样返回 200，
    而泄漏的内容是「全站配置 + 谁在什么时候从哪个 IP 改了什么」。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        aid = admin.id
        try:
            _auth(client, aid)
            for path in SUPER_ONLY:
                r = client.get(path)
                assert r.status_code == 403, "管理员竟能访问 %s（%s）" % (path, r.status_code)
        finally:
            _drop([aid])


def test_超管能访问全部端点(app, client):
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        try:
            _auth(client, sid)
            for path in SUPER_ONLY:
                r = client.get(path)
                assert r.status_code == 200, "%s 返回 %s: %s" % (
                    path, r.status_code, r.get_data(as_text=True)[:200])
        finally:
            _drop([sid])


def test_统计报表对管理员开放(app, client):
    """对齐后台 `admin.stats` 的 `@admin_required` —— 聚合数据不含 PII，管理员该看得到。"""
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        aid = admin.id
        try:
            _auth(client, aid)
            r = client.get("/api/mobile/stats/report")
            assert r.status_code == 200, r.get_data(as_text=True)[:300]
            d = r.get_json()
            for k in ("range", "summary", "trend", "top_paths",
                      "devices_30d", "browsers_30d"):
                assert k in d, "报表缺字段 %s" % k
        finally:
            _drop([aid])


# ------------------------------------------------------------------ 不泄漏


def test_设置端点不含任何凭据键(app, client):
    """断言的是**响应全文**里没有这些键名，而不是逐个字段检查 ——
    新增字段时若顺手把凭据带出来，逐字段断言会漏。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        try:
            _auth(client, sid)
            body = client.get("/api/mobile/settings").get_data(as_text=True)
            for bad in ("mail_password", "backup_oss_secret", "backup_scp_key",
                        "push_telegram_token", "push_wecom_webhook",
                        "password_hash", "unsub_token"):
                assert bad not in body, "设置响应里出现了凭据键：%s" % bad
            d = client.get("/api/mobile/settings").get_json()
            assert "settings" in d and isinstance(d["settings"], list)
            assert "push_channels" in d
        finally:
            _drop([sid])


def test_用户列表邮箱遮敏(app, client):
    """超管拿到的也是遮敏形态：用户管理要的是「这是谁」，不是完整邮箱。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        victim = _mkuser(ROLE_USER, email="zhangsan@example.com")
        vid = victim.id
        try:
            _auth(client, sid)
            body = client.get("/api/mobile/users").get_data(as_text=True)
            assert "zhangsan@example.com" not in body, "完整邮箱出现在用户列表里"
            assert "***" in body, "邮箱根本没遮敏（应形如 zh***@ex***.com）"
        finally:
            _drop([sid, vid])


def test_审计日志不含配置快照(app, client):
    """`payload` 里可能有配置变更前快照（含历史密钥值），一律不返回。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        a = AuditLog(username="x", action="setting", target="setting",
                     detail="改配置", payload='{"mail_password": "leak-me"}')
        db.session.add(a)
        db.session.commit()
        aid = a.id
        try:
            _auth(client, sid)
            body = client.get("/api/mobile/audit-logs").get_data(as_text=True)
            assert "leak-me" not in body, "审计 payload 里的快照泄漏了"
            assert "payload" not in body
        finally:
            AuditLog.query.filter(AuditLog.id == aid).delete(synchronize_session=False)
            db.session.commit()
            _drop([sid])


# ------------------------------------------------------------------ 改角色


def test_改角色_不能改自己(app, client):
    """把自己降级后，若系统里没有第二个超管就再也改不回来 —— 直接 400。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        try:
            tok = _auth(client, sid)
            r = _req(client, "post", "/api/mobile/user/%d/role" % sid, tok,
                     {"role": "admin"})
            assert r.status_code == 400
            assert "自己" in (r.get_json() or {}).get("error", "")
        finally:
            _drop([sid])


def test_改角色_白名单校验(app, client):
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        other = _mkuser(ROLE_USER)
        oid = other.id
        try:
            tok = _auth(client, sid)
            # 注意：**不测 "admin "（带尾空格）** —— 服务端 `strip()` 后是合法角色，
            # 接受它是正确行为（客户端从剪贴板粘贴常带空格）。要测的是真正的非法值。
            for bad in ("Super", "root", "", "superadmin", "ADMIN"):
                r = _req(client, "post", "/api/mobile/user/%d/role" % oid, tok,
                         {"role": bad})
                assert r.status_code == 400, "非法角色 %r 被接受了" % bad
        finally:
            _drop([sid, oid])


def test_改角色成功且失效旧会话(app, client):
    """改角色必须 `session_version+1`：否则目标用户已登录的会话仍带旧权限。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        other = _mkuser(ROLE_USER)
        oid, before = other.id, other.session_version or 0
        try:
            tok = _auth(client, sid)
            r = _req(client, "post", "/api/mobile/user/%d/role" % oid, tok,
                     {"role": "admin"})
            assert r.status_code == 200, r.get_data(as_text=True)[:200]
            db.session.expire_all()
            u = db.session.get(User, oid)
            assert u.role == "admin"
            assert (u.session_version or 0) == before + 1, "改角色没让旧会话失效"
        finally:
            _drop([sid, oid])


# ------------------------------------------------------------------ 结构正确


def test_备份列表结构与空态(app, client):
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        try:
            _auth(client, sid)
            r = client.get("/api/mobile/backups")
            assert r.status_code == 200
            d = r.get_json()
            assert "backups" in d and isinstance(d["backups"], list)
            assert "remote" in d
        finally:
            _drop([sid])


def test_证书接口读取持久化状态(app, client):
    """只读状态文件，**不做实时探测** —— 否则下拉刷新每次等 6 秒。"""
    with app.app_context():
        sup = _mkuser(ROLE_SUPER)
        sid = sup.id
        try:
            _auth(client, sid)
            r = client.get("/api/mobile/cert")
            assert r.status_code == 200
            d = r.get_json()
            assert "state" in d and "warn_days" in d
        finally:
            _drop([sid])
