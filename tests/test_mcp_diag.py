"""只读诊断 MCP 端点冒烟测试（v3.10.0，v4.11.0 扩到 8 个工具）。

覆盖：
1. 未配置 token 时端点整体关闭（fail-closed，绝不裸奔）；
2. MCP 握手（initialize / tools/list / tools/call / notification）；
3. 认证与 Origin 校验（防 DNS 重绑定）；
4. 八个只读工具均可执行；
5. 日志脱敏（密钥/口令/Token 不出现在返回里）；
6. 不支持的方法与工具返回标准 JSON-RPC 错误码；
7. GET /mcp 被拒绝（本实现不提供 SSE 流）；
8. 只读保证：源码层不含任何写操作。

运行：仓库根目录 `python -m pytest tests/ -q`
"""
import json
import os

TOKEN = "test-mcp-token-0123456789"

# v4.11.0：v3.10.0 的 5 个工具 + 诊断扩展的 3 个（issues / health_score / run_check）。
# 集合写死是**故意的**：加工具必须顺手改这里，避免「新工具上线但文档/测试都不知道」。
TOOL_NAMES = {
    "health_overview", "health_score", "issues", "run_check",
    "db_status", "version_info", "recent_errors", "content_stats",
}


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
    assert set(names) == TOOL_NAMES
    for t in tools:
        assert t["description"] and "inputSchema" in t


def test_every_tool_runs(app):
    """八个工具逐个执行，都不应报错（isError 为真即失败）。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()
    args = {"run_check": {"check": "database"}}
    for name in TOOL_NAMES:
        r = _rpc(client, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                          "params": {"name": name,
                                     "arguments": args.get(name, {})}}, _auth())
        assert r.status_code == 200, name
        result = r.get_json()["result"]
        assert not result.get("isError"), name + ": " + str(result)
        assert result["content"][0]["type"] == "text"


def _call(client, name, arguments=None, rid=11):
    r = _rpc(client, {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments or {}}}, _auth())
    assert r.status_code == 200
    body = r.get_json()["result"]
    assert not body.get("isError"), body
    return json.loads(body["content"][0]["text"])


def test_issues_tool_shape(app):
    """issues 必须给出评分、总数与可定位的条目（key 能喂回 run_check）。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    data = _call(app.test_client(), "issues")
    assert isinstance(data["score"], int) and 0 <= data["score"] <= 100
    assert "issue_total" in data and isinstance(data["issue_total"], int)
    for it in data["issues"]:
        assert it["level"] in ("error", "warn")
        assert it["key"] and it["dimension"] and it["label"]


def test_issues_level_filter(app):
    """level=error 只回 error 级；这是「先看硬伤」的主路径，不能静默返回全部。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    data = _call(app.test_client(), "issues", {"level": "error"})
    assert all(i["level"] == "error" for i in data["issues"])


def test_health_score_dimensions_match_checks(app):
    """dimensions 的 key 必须覆盖 diagnostics.CHECKS_BY_KEY 的全部维度。

    这条防的是「加了 checker 但 MCP 看不到」：两处不一致时 AI 会以为维度不存在。
    """
    import diagnostics
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    data = _call(app.test_client(), "health_score")
    keys = {d["key"] for d in data["dimensions"]}
    assert keys == set(diagnostics.CHECKS_BY_KEY.keys())
    assert len(keys) == len(diagnostics.CHECKS)


def test_run_check_unknown_and_missing(app):
    """未知维度要报错并给出可选值，而不是返回空结果假装成功。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    client = app.test_client()
    bad = _call(client, "run_check", {"check": "nope"})
    assert bad["error"] and bad["available"]
    missing = _call(client, "run_check", {})
    assert missing["error"] and missing["available"]


def test_run_check_returns_full_items(app):
    """run_check 的明细不做裁剪：正常项（level=ok/info）也要在。"""
    app.config["MCP_AUTH_TOKEN"] = TOKEN
    data = _call(app.test_client(), "run_check", {"check": "database"})
    assert data["check"] == "database"
    assert data["items"], "应返回明细行"
    assert any(i["level"] in ("info", "ok") for i in data["items"])


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
    with open(path, encoding="utf-8") as _f:
        src = _f.read()
    forbidden = ("db.session.commit", "db.session.add", "db.session.delete",
                 "os.remove", "os.rename", "os.unlink", "shutil.", "subprocess",
                 "eval(", "exec(")
    leaked = [w for w in forbidden if w in src]
    assert not leaked, "MCP 模块出现写操作/危险调用：" + str(leaked)
