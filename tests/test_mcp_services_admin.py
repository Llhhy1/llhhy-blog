"""MCP 服务管理面板回归测试（v3.13.0 新增功能）。

覆盖（myblog/admin/mcp_services.py + mcp_diag/mcp_write 的面板开关）：
1. 权限：未登录 → 跳登录页；普通管理员（role=admin）→ 403；超管 → 200。
2. 内置端点启停即时生效：面板「停止」→ /mcp 与 /mcp-write 对外 404
   （即使带对 token），「开启」→ 恢复正常鉴权口径（401/200）。
3. 外部服务 CRUD：登记后 JSON 落 Setting；token 以 Fernet 密文落库
   （bkenc$ 前缀，库里无明文）；更新/启停/删除（连 token 键一并清）。
4. URL 校验：javascript: 等非法 scheme 被拒。
5. AI 接入指令：脱敏版不含真实 token（占位符）；完整版含真实 token
   且每次查看写审计（action=mcp_full）。
6. 面板页渲染：显示 token 掩码而非明文。

运行：仓库根目录 `python -m pytest tests/ -q`
注意：测试库为仓库内持久化的 myblog/data/blog.db（gitignored），用户名 /
服务名用 uuid 保证唯一，每个用例 finally 清理自建数据，避免污染与冲突。
"""
import uuid

import pytest

from models import db, User, Setting, AuditLog, ROLE_SUPER, ROLE_ADMIN
from utils import _sign_csrf
from backup_settings import decrypt_secret

import mcp_diag
import mcp_write


def _uid():
    return uuid.uuid4().hex[:10]


def _mkuser(role=ROLE_SUPER):
    u = User(username="mcps-" + _uid(), email="mcps-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False  # 否则会被跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    """登录（写 session）并生成与会话绑定的有效 CSRF token（与 test_moments_admin 同法）。

    _sign_csrf 依赖 current_app（SECRET_KEY），自带 app context，调用方无须嵌套。
    """
    import secrets
    raw = secrets.token_hex(24)
    with client.application.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def _cleanup(uids=(), setting_keys=()):
    for k in setting_keys:
        s = Setting.query.filter_by(key=k).first()
        if s:
            db.session.delete(s)
    # 外部服务 JSON：只剔除本文件登记的测试条目（按名称前缀），不动真实数据
    raw = Setting.query.filter_by(key="mcp_external_services").first()
    if raw:
        import json as _json
        try:
            rows = _json.loads(raw.value or "[]")
            kept = [x for x in rows if not str(x.get("name", "")).startswith("mcps-test-")]
            if len(kept) != len(rows):
                raw.value = _json.dumps(kept, ensure_ascii=False)
        except Exception:
            pass
    # 审计：按操作人（本测试建的用户）清 MCP 面板动作
    if uids:
        AuditLog.query.filter(AuditLog.user_id.in_(list(uids))).filter(
            AuditLog.action.in_(
                ("mcp_add", "mcp_update", "mcp_toggle", "mcp_delete", "mcp_full", "mcp_base"))
        ).delete(synchronize_session=False)
    for u in uids:
        usr = db.session.get(User, u)
        if usr:
            db.session.delete(usr)
    db.session.commit()


@pytest.fixture(autouse=True)
def _disable_ratelimit_in_tests(monkeypatch):
    """与 test_mcp_write 同口径：固定放行，避免连续请求触发 429 让套件不稳定。

    mcp_write 顶层已 import 绑定 → patch mcp_write.rate_limit；
    mcp_diag 在函数内 import → patch utils.rate_limit（每次请求重新取）。
    """
    import utils
    monkeypatch.setattr(mcp_write, "rate_limit", lambda *a, **k: True)
    monkeypatch.setattr(utils, "rate_limit", lambda *a, **k: True)


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------

def test_panel_requires_super(app, client):
    """未登录（super_required 直接 403，不暴露面板存在）；普通管理员 403；超管 200。"""
    assert client.get("/admin/mcp-services").status_code == 403

    with app.app_context():
        admin = _mkuser(role=ROLE_ADMIN)
        superu = _mkuser(role=ROLE_SUPER)
        aid, sid = admin.id, superu.id
    try:
        tok = _auth(client, aid)
        assert client.get("/admin/mcp-services").status_code == 403
        _auth(client, sid)
        assert client.get("/admin/mcp-services").status_code == 200
    finally:
        with app.app_context():
            _cleanup(uids=(aid, sid))


# ---------------------------------------------------------------------------
# 内置端点启停即时生效
# ---------------------------------------------------------------------------

def test_builtin_toggle_stops_endpoints(app, client):
    """面板停止 → /mcp 与 /mcp-write 对外 404（带对 token 也 404）；开启 → 恢复。"""
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        _auth(client, sid)
        app.config["MCP_AUTH_TOKEN"] = "mcps-test-diag-token"
        app.config["MCP_WRITE_TOKEN"] = "mcps-test-write-token"
        hdr = {"Authorization": "Bearer mcps-test-diag-token",
               "Accept": "application/json, text/event-stream"}

        # 基线：运行中（无禁用 Setting）→ 带对 token 正常（tools/list 200）
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert client.post("/mcp", json=payload, headers=hdr).status_code == 200

        # 面板「停止」diag → 404（不暴露端点存在），即时生效
        r = client.post("/admin/mcp-services/toggle/diag",
                        data={"csrf_token": tok_local(client), "enable": "0"})
        assert r.status_code in (200, 302)
        assert client.post("/mcp", json=payload, headers=hdr).status_code == 404

        # 面板「开启」→ 恢复 200
        r = client.post("/admin/mcp-services/toggle/diag",
                        data={"csrf_token": tok_local(client), "enable": "1"})
        assert client.post("/mcp", json=payload, headers=hdr).status_code == 200

        # write 端点同理
        whdr = {"Authorization": "Bearer mcps-test-write-token",
                "Accept": "application/json, text/event-stream"}
        assert client.post("/mcp-write", json=payload, headers=whdr).status_code == 200
        client.post("/admin/mcp-services/toggle/write",
                    data={"csrf_token": tok_local(client), "enable": "0"})
        assert client.post("/mcp-write", json=payload, headers=whdr).status_code == 404
        client.post("/admin/mcp-services/toggle/write",
                    data={"csrf_token": tok_local(client), "enable": "1"})
        assert client.post("/mcp-write", json=payload, headers=whdr).status_code == 200
    finally:
        with app.app_context():
            _cleanup(uids=(sid,), setting_keys=("mcp_diag_disabled", "mcp_write_disabled"))
        app.config.pop("MCP_AUTH_TOKEN", None)
        app.config.pop("MCP_WRITE_TOKEN", None)


def tok_local(client):
    """复用会话中已写入的 CSRF token（_auth 时存的 raw+签名）。"""
    with client.session_transaction() as sess:
        return sess["csrf_token"]


# ---------------------------------------------------------------------------
# 外部服务 CRUD + 密文落库
# ---------------------------------------------------------------------------

def test_ext_service_crud_encrypted_token(app, client):
    """登记 → JSON 落库 + token 密文落库（无明文）；启停、更新、删除联动清 token 键。"""
    name = "mcps-test-" + _uid()
    url = "https://example.org/mcp"
    token = "mcps-plain-secret-" + _uid()
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    keys = ("mcp_external_services", "mcp_base_url")
    try:
        _auth(client, sid)
        # 登记
        r = client.post("/admin/mcp-services/add", data={
            "csrf_token": tok_local(client),
            "name": name, "url": url, "header": "Authorization",
            "token": token, "desc": "回归测试服务",
        })
        assert r.status_code in (200, 302)

        with app.app_context():
            import json
            rows = json.loads(Setting.query.filter_by(key="mcp_external_services").first().value)
            row = next(x for x in rows if x["name"] == name)
            assert row["url"] == url and row["enabled"] is True
            tk = Setting.query.filter_by(key="mcp_service_token_%s" % row["id"]).first()
            assert tk is not None
            assert token not in tk.value            # 库里无明文
            assert decrypt_secret(tk.value) == token  # 密文可解回原值

        # 脱敏指令不含真实 token；面板页只显示掩码
        r = client.get("/admin/mcp-services/instruction/%s" % row["id"])
        assert r.status_code == 200 and token.encode() not in r.data
        r = client.get("/admin/mcp-services")
        assert token.encode() not in r.data

        # 完整指令含真实 token，且写审计 mcp_full
        r = client.get("/admin/mcp-services/instruction/%s?full=1" % row["id"])
        assert r.status_code == 200 and token.encode() in r.data
        with app.app_context():
            assert AuditLog.query.filter_by(action="mcp_full").filter(
                AuditLog.detail.like("%" + name + "%")).count() == 1

        # 停用 → JSON enabled=false；更新（不带 token = 保留原值）
        client.post("/admin/mcp-services/update/%s" % row["id"],
                    data={"csrf_token": tok_local(client), "enable": "0"})
        with app.app_context():
            import json
            rows = json.loads(Setting.query.filter_by(key="mcp_external_services").first().value)
            row = next(x for x in rows if x["name"] == name)
            assert row["enabled"] is False

        # ?edit=<sid> → 面板切换为编辑态渲染（预填表单、action 指向 update）
        r = client.get("/admin/mcp-services?edit=%s" % row["id"])
        assert r.status_code == 200 and name.encode() in r.data and b"save-update" not in r.data

        # 删除 → JSON 清空 + token 键一并清除
        client.post("/admin/mcp-services/delete/%s" % row["id"],
                    data={"csrf_token": tok_local(client)})
        with app.app_context():
            import json
            rows = json.loads(Setting.query.filter_by(key="mcp_external_services").first().value)
            assert all(x["name"] != name for x in rows)
            assert Setting.query.filter_by(key="mcp_service_token_%s" % row["id"]).first() is None
    finally:
        with app.app_context():
            _cleanup(uids=(sid,), setting_keys=keys)


def test_ext_service_url_validation(app, client):
    """javascript: / 非法 scheme 被拒，不落库。"""
    name = "mcps-test-bad-" + _uid()
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        _auth(client, sid)
        for bad in ("javascript:alert(1)", "ftp://x/y", "not-a-url", ""):
            client.post("/admin/mcp-services/add", data={
                "csrf_token": tok_local(client),
                "name": name, "url": bad, "header": "Authorization",
                "token": "", "desc": "",
            })
        with app.app_context():
            import json
            raw = Setting.query.filter_by(key="mcp_external_services").first()
            rows = json.loads(raw.value) if raw else []
            assert all(x["name"] != name for x in rows)
    finally:
        with app.app_context():
            _cleanup(uids=(sid,), setting_keys=("mcp_external_services",))


def test_full_instruction_view_audited_for_builtin(app, client):
    """内置端点完整指令：含真实 token（从 config），查看记审计。"""
    token = "mcps-builtin-diag-token-" + _uid()
    with app.app_context():
        superu = _mkuser()
        sid = superu.id
    try:
        _auth(client, sid)
        app.config["MCP_AUTH_TOKEN"] = token
        r = client.get("/admin/mcp-services/instruction/diag?full=1")
        assert r.status_code == 200 and token.encode() in r.data
        # 脱敏版不含
        r = client.get("/admin/mcp-services/instruction/diag")
        assert token.encode() not in r.data
        with app.app_context():
            assert AuditLog.query.filter_by(action="mcp_full").filter(
                AuditLog.detail.like("%/mcp%")).count() >= 1
    finally:
        with app.app_context():
            _cleanup(uids=(sid,))
        app.config.pop("MCP_AUTH_TOKEN", None)
