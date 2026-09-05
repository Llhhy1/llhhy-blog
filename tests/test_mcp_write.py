"""写能力 MCP 端点冒烟测试（v3.12.2）。

覆盖：
1. 未配置 token 时端点整体 404（fail-closed）；
2. token 错误 → 401；
3. 正常调用 → 落成草稿（published is False）；
4. publish=true 但 MCP_WRITE_DEFAULT_PUBLISH=0 → 仍为草稿且 warnings 非空；
5. 传 is_pinned=true 被忽略，落库为 False（禁止提权）；
6. 默认不触发订阅者群发（monkeypatch 断言未被调用）；
7. 幂等：同 idempotency_key 连调两次，Post 只 +1，第二次 deduplicated=true；
8. slug 冲突：预置同名文章，新文章 slug 带后缀，旧文章正文未被改动；
9. 每次调用都落一条 AuditLog（action=mcp_create_post）；
10. 空标题 / 超长正文 → 拒绝且不落库；
11. initialize / tools/list / GET 405 / Origin 校验。

注意：测试库为仓库内持久化的 myblog/data/blog.db（gitignored），标题用唯一前缀、
finally 清理自建数据，避免污染与唯一约束冲突。
"""
import json

import pytest

from models import db, Post, PostHistory, AuditLog
from app import create_app

TOKEN = "test-mcp-write-token-0123456789"


@pytest.fixture(autouse=True)
def _disable_ratelimit_in_tests(monkeypatch):
    """限流阈值（10/60s）来自文档安全闸门，底层 utils.rate_limit 机制本身可信；
    测试中固定放行，避免连续请求触发 429 让套件不稳定（不测限流本身）。"""
    import mcp_write
    monkeypatch.setattr(mcp_write, "rate_limit", lambda *a, **k: True)


@pytest.fixture(scope="session", autouse=True)
def _purge_mcpw_posts():
    """运行前后清掉以 MCPW 开头的测试残留文章，避免跨次运行污染（仅匹配测试标题前缀）。"""
    import os as _os
    _os.environ.setdefault("SECRET_KEY", "test-secret-key")
    _os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
    from app import create_app
    from models import db, Post

    def _purge():
        app = create_app()
        with app.app_context():
            Post.query.filter(Post.title.like("MCPW%")).delete()
            db.session.commit()

    _purge()
    yield
    _purge()


def _rpc(client, payload, extra_headers=None):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/mcp-write", json=payload, headers=headers)


def _auth():
    return {"Authorization": "Bearer " + TOKEN}


def _content(r):
    return json.loads(r.get_json()["result"]["content"][0]["text"])


def _cleanup(app, pids):
    with app.app_context():
        for pid in pids:
            PostHistory.query.filter_by(post_id=pid).delete()
            p = db.session.get(Post, pid)
            if p:
                db.session.delete(p)
            AuditLog.query.filter_by(action="mcp_create_post", target_id=pid).delete()
        db.session.commit()


def _make_post_direct(app, title, content="正文", published=False):
    """直接落库一篇同名文章（用于 slug 冲突测试），返回 (id, slug)。"""
    with app.app_context():
        p = Post(title=title, slug=title, content=content, published=published)
        db.session.add(p)
        db.session.commit()
        return p.id, p.slug


# ---------------------------------------------------------------------------
# 认证 / 关闭态
# ---------------------------------------------------------------------------
def test_closed_when_token_not_configured(app):
    """未配置 MCP_WRITE_TOKEN → 整体 404（fail-closed，不暴露端点存在）。"""
    app.config["MCP_WRITE_TOKEN"] = ""
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
             {"Authorization": "Bearer anything"})
    assert r.status_code == 404


def test_wrong_token_rejected(app):
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    client = app.test_client()
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    assert _rpc(client, call, {"Authorization": "Bearer wrong"}).status_code == 401
    assert _rpc(client, call).status_code == 401
    assert _rpc(client, call, _auth()).status_code == 200


def test_origin_validation_blocks_dns_rebinding(app):
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    client = app.test_client()
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
    evil = dict(_auth(), **{"Origin": "https://evil.example.com"})
    assert _rpc(client, call, evil).status_code == 403
    assert _rpc(client, call, _auth()).status_code == 200


# ---------------------------------------------------------------------------
# 握手 / 工具清单
# ---------------------------------------------------------------------------
def test_initialize_handshake(app):
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                         "clientInfo": {"name": "pytest", "version": "1"}}}, _auth())
    assert r.status_code == 200
    result = r.get_json()["result"]
    assert result["serverInfo"]["name"] == "llhhy-blog-write"
    assert "tools" in result["capabilities"]


def test_tools_list(app):
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}, _auth())
    names = [t["name"] for t in r.get_json()["result"]["tools"]]
    assert set(names) == {"create_post", "list_recent_posts"}


def test_get_not_allowed(app):
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    r = app.test_client().get("/mcp-write", headers=_auth())
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# 发文行为 + 安全闸门
# ---------------------------------------------------------------------------
def test_create_default_draft(app):
    """正常调用（不传 publish）→ 落成草稿。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    pids = []
    try:
        with app.app_context():
            before = Post.query.count()
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW草稿测试一",
                                           "content": "# hello",
                                           "idempotency_key": "idem-draft-1"}}}, _auth())
        assert r.status_code == 200
        assert r.get_json()["result"].get("isError") is not True
        res = _content(r)
        assert res["published"] is False
        pids.append(res["id"])
        with app.app_context():
            assert Post.query.count() == before + 1
            assert db.session.get(Post, res["id"]).published is False
    finally:
        _cleanup(app, pids)


def test_publish_forced_draft_when_default_off(app):
    """publish=true 但 MCP_WRITE_DEFAULT_PUBLISH=0 → 仍草稿且 warnings 非空。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    app.config["MCP_WRITE_DEFAULT_PUBLISH"] = "0"
    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW强转草稿测试",
                                           "content": "x",
                                           "publish": True,
                                           "idempotency_key": "idem-force-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        assert res["published"] is False
        assert res["warnings"], "应给出强制草稿的 warnings"
        pids.append(res["id"])
    finally:
        _cleanup(app, pids)


def test_super_fields_ignored_by_default(app):
    """默认不接受提权字段：is_pinned=true 被忽略，落库为 False。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    app.config["MCP_WRITE_ALLOW_SUPER_FIELDS"] = "0"
    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW提权忽略测试",
                                           "content": "x",
                                           "is_pinned": True,
                                           "is_private": True,
                                           "idempotency_key": "idem-super-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        assert res["published"] is False
        pids.append(res["id"])
        with app.app_context():
            p = db.session.get(Post, res["id"])
            assert p.is_pinned is False
            assert p.is_private is False
    finally:
        _cleanup(app, pids)


def test_super_fields_accepted_when_enabled(app):
    """MCP_WRITE_ALLOW_SUPER_FIELDS=1 时才接受提权字段。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    app.config["MCP_WRITE_ALLOW_SUPER_FIELDS"] = "1"
    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW提权接受测试",
                                           "content": "x",
                                           "is_pinned": True,
                                           "idempotency_key": "idem-super-on-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        pids.append(res["id"])
        with app.app_context():
            assert db.session.get(Post, res["id"]).is_pinned is True
    finally:
        _cleanup(app, pids)


def test_notify_not_triggered_by_default(app, monkeypatch):
    """默认不触发订阅者群发：monkeypatch mail_notify.notify_subscribers_async 断言未被调用。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    app.config["MCP_WRITE_ALLOW_NOTIFY"] = "0"
    called = {"n": 0}

    import mail_notify as mn
    def _fake(post):
        called["n"] += 1
    monkeypatch.setattr(mn, "notify_subscribers_async", _fake)

    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW群发测试",
                                           "content": "x",
                                           "publish": True,
                                           "notify_subscribers": True,
                                           "idempotency_key": "idem-notify-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        pids.append(res["id"])
        assert called["n"] == 0, "默认不应触发订阅者群发"
    finally:
        _cleanup(app, pids)


def test_notify_triggered_when_allowed(app, monkeypatch):
    """MCP_WRITE_ALLOW_NOTIFY=1 且显式 notify_subscribers=true → 触发群发。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    app.config["MCP_WRITE_ALLOW_NOTIFY"] = "1"
    app.config["MCP_WRITE_DEFAULT_PUBLISH"] = "1"
    called = {"n": 0}

    import mail_notify as mn
    def _fake(post):
        called["n"] += 1
    monkeypatch.setattr(mn, "notify_subscribers_async", _fake)

    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW群发允许测试",
                                           "content": "x",
                                           "publish": True,
                                           "notify_subscribers": True,
                                           "idempotency_key": "idem-notify-on-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        pids.append(res["id"])
        assert called["n"] == 1, "ALLOW_NOTIFY=1 时应触发一次群发"
    finally:
        _cleanup(app, pids)


def test_idempotency(app):
    """同 idempotency_key 连调两次 → Post 只 +1，第二次 deduplicated=true。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    pids = []
    try:
        with app.app_context():
            before = Post.query.count()
        payload = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                   "params": {"name": "create_post",
                              "arguments": {"title": "MCPW幂等测试",
                                            "content": "x",
                                            "idempotency_key": "idem-same-key"}}}
        r1 = _rpc(app.test_client(), payload, _auth())
        res1 = _content(r1)
        pids.append(res1["id"])
        r2 = _rpc(app.test_client(), payload, _auth())
        res2 = _content(r2)
        assert res2["deduplicated"] is True
        assert res2["id"] == res1["id"]
        with app.app_context():
            assert Post.query.count() == before + 1
    finally:
        _cleanup(app, pids)


def test_slug_collision_not_overwritten(app):
    """预置一篇 slug 为 X 的文章后，MCP 用不同标题但 slugify 同为 X 创建 → 新 slug 带后缀，
    旧文章正文未被改动。（注意：故意用不同标题，避免触发「同标题+当日」幂等去重。）"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    # 旧文章标题含空格 → slug "MCPWslug-abc"；新文章标题含连字符 → slug 同为 "MCPWslug-abc"
    old_id, old_slug = _make_post_direct(app, "MCPWslug abc", content="原始正文")
    pids = [old_id]
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPWslug-abc",
                                           "content": "新正文",
                                           "idempotency_key": "idem-slug-1"}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        new_id = res["id"]
        pids.append(new_id)
        assert new_id != old_id
        assert res["slug"] != old_slug, "新文章 slug 应带后缀，不与旧冲突"
        with app.app_context():
            old = db.session.get(Post, old_id)
            assert old.content == "原始正文", "旧文章正文不可被覆盖"
    finally:
        _cleanup(app, pids)


def test_audit_log_written_each_call(app):
    """每次调用（含成功）都落一条 AuditLog（action=mcp_create_post, username=mcp）。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    pids = []
    try:
        with app.app_context():
            before = AuditLog.query.filter_by(action="mcp_create_post").count()
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                  "params": {"name": "create_post",
                             "arguments": {"title": "MCPW审计测试",
                                           "content": "x",
                                           "idempotency_key": "idem-audit-1"}}}, _auth())
        res = _content(r)
        pids.append(res["id"])
        with app.app_context():
            after = AuditLog.query.filter_by(action="mcp_create_post").count()
            assert after == before + 1
            log = AuditLog.query.filter_by(action="mcp_create_post",
                                           target_id=res["id"]).first()
            assert log is not None
            assert log.username == "mcp"
            assert log.success is True
            assert _token_prefix_in(log.detail)
    finally:
        _cleanup(app, pids)


def _token_prefix_in(detail):
    return ("token=" + TOKEN[:8]) in detail


def test_reject_empty_title_and_oversized_content(app):
    """空标题 / 超长正文 → 拒绝（isError）且不落库。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    pids = []
    try:
        with app.app_context():
            before = Post.query.count()
        # 空标题
        r1 = _rpc(app.test_client(),
                  {"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                   "params": {"name": "create_post",
                              "arguments": {"title": "   ", "content": "x",
                                            "idempotency_key": "idem-empty-1"}}}, _auth())
        assert r1.get_json()["result"].get("isError") is True
        # 超长正文（>200000）
        r2 = _rpc(app.test_client(),
                  {"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                   "params": {"name": "create_post",
                              "arguments": {"title": "MCPW超长测试",
                                            "content": "x" * 200001,
                                            "idempotency_key": "idem-long-1"}}}, _auth())
        assert r2.get_json()["result"].get("isError") is True
        with app.app_context():
            assert Post.query.count() == before, "拒绝的请求不应落库"
    finally:
        _cleanup(app, pids)


def test_list_recent_posts_no_body(app):
    """list_recent_posts 返回最近文章元数据，不含正文。"""
    app.config["MCP_WRITE_TOKEN"] = TOKEN
    pids = []
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                  "params": {"name": "list_recent_posts",
                             "arguments": {"limit": 5}}}, _auth())
        assert r.status_code == 200
        res = _content(r)
        assert "posts" in res
        if res["posts"]:
            first = res["posts"][0]
            assert set(first.keys()) == {"id", "title", "slug", "published", "created_at"}
            assert "content" not in first
    finally:
        _cleanup(app, pids)
