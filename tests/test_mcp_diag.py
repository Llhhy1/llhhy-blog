"""只读诊断 MCP 端点冒烟测试（v3.10.0）。

覆盖：
1. 未配置 token 时端点整体关闭（fail-closed，绝不裸奔）；
2. MCP 握手（initialize / tools/list / tools/call / notification）；
3. 认证与 Origin 校验（防 DNS 重绑定）；
4. 五个只读工具均可执行；
5. 日志脱敏（密钥/口令/Token 不出现在返回里）；
6. 不支持的方法与工具返回标准 JSON-RPC 错误码；
7. GET /mcp 被拒绝（本实现不提供 SSE 流）；
8. 只读保证：源码层不含任何写操作。

运行：仓库根目录 `python -m pytest tests/ -q`
"""
import os

TOKEN = "test-mcp-token-0123456789"


def _rpc(client, payload, extra_headers=None):
    """发一个 JSON-RPC 请求到 /mcp。"""
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/mcp", json=payload, headers=headers)


def _auth():
    return {"Authorization": "Bearer " + TOKEN}


def test_closed_when_token_not_configured(app):
    """未配置 MCP_AUTH_TOKEN → 一律 401（fail-closed）。"""
    app.config["MCP_AUTH_TOKEN"] = ""
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
             {"Authorization": "Bearer anything"})
    assert r.status_code == 401


def test_initialize_handshake(app):
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                         "clientInfo": {"name": "pytest", "version": "1"}}},
             _auth())
    assert r.status_code == 200
    result = r.get_json()["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["serverInfo"]["name"] == "llhhy-blog-diag"
    assert "tools" in result["capabilities"]


def test_auth_required(app):
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    assert _rpc(client, call, {"Authorization": "Bearer wrong"}).status_code == 401
    assert _rpc(client, call).status_code == 401
    assert _rpc(client, call, _auth()).status_code == 200


def test_origin_validation_blocks_dns_rebinding(app):
    """带 Origin 时必须同源或被白名单允许（MCP 规范要求）。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
    evil = dict(_auth(), **{"Origin": "https://evil.example.com"})
    assert _rpc(client, call, evil).status_code == 403
    # 不带 Origin 的非浏览器客户端（curl / MCP 客户端）应放行
    assert _rpc(client, call, _auth()).status_code == 200


def test_tools_list(app):
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
             _auth())
    tools = r.get_json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert set(names) == {"health_overview", "db_status", "version_info",
                          "recent_errors", "content_stats"}
    for t in tools:
        assert t["description"] and "inputSchema" in t


def test_every_tool_runs(app):
    """五个工具逐个执行，都不应报错（isError 为真即失败）。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()
    for name in ("health_overview", "db_status", "version_info",
                 "recent_errors", "content_stats"):
        r = _rpc(client, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                          "params": {"name": name, "arguments": {}}}, _auth())
        assert r.status_code == 200, name
        result = r.get_json()["result"]
        assert not result.get("isError"), name + ": " + str(result)
        assert result["content"][0]["type"] == "text"


def test_log_redaction(app, tmp_path):
    """recent_errors 返回的日志里，密钥/口令/Token 必须被打码。"""
    log = tmp_path / "app.log"
    log.write_text(
        "normal line keep me\n"
        "SECRET_KEY=supersecretvalue123\n"
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcd\n"
        "password=hunter2\n",
        encoding="utf-8",
    )
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    app.config["MCP_LOG_FILES"] = str(log)
    try:
        r = _rpc(app.test_client(),
                 {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                  "params": {"name": "recent_errors", "arguments": {"lines": 20}}},
                 _auth())
        text = r.get_json()["result"]["content"][0]["text"]
        assert "normal line keep me" in text      # 普通日志保留
        assert "supersecretvalue123" not in text
        assert "eyJhbGciOiJIUzI1NiJ9abcd" not in text
        assert "hunter2" not in text
    finally:
        app.config["MCP_LOG_FILES"] = ""


def test_recent_errors_without_config(app):
    """未配置 MCP_LOG_FILES 时给出明确提示，而不是去猜路径/遍历目录。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    app.config["MCP_LOG_FILES"] = ""
    r = _rpc(app.test_client(),
             {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
              "params": {"name": "recent_errors", "arguments": {}}}, _auth())
    result = r.get_json()["result"]
    assert not result.get("isError")
    assert "\"configured\": false" in result["content"][0]["text"]


def test_jsonrpc_error_codes(app):
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()

    r = _rpc(client, {"jsonrpc": "2.0", "id": 8, "method": "no/such", "params": {}}, _auth())
    assert r.get_json()["error"]["code"] == -32601

    r = _rpc(client, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                      "params": {"name": "nope", "arguments": {}}}, _auth())
    assert r.get_json()["error"]["code"] == -32602

    # notification（无 id）→ 202 空响应
    r = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized",
                      "params": {}}, _auth())
    assert r.status_code == 202


def test_get_not_allowed(app):
    """本实现不提供 SSE GET 流，应明确 405。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    r = app.test_client().get("/mcp", headers=_auth())
    assert r.status_code == 405


def test_mcp_source_is_readonly():
    """静态审查：MCP 模块不得出现任何写操作（这是本功能的安全红线）。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "myblog", "mcp_diag.py")
    src = open(path, encoding="utf-8").read()
    forbidden = ("db.session.commit", "db.session.add", "db.session.delete",
                 "os.remove", "os.rename", "os.unlink", "shutil.", "subprocess",
                 "eval(", "exec(")
    leaked = [w for w in forbidden if w in src]
    assert not leaked, "MCP 模块出现写操作/危险调用：" + str(leaked)
