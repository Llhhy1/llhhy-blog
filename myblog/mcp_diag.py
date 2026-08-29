"""只读诊断 MCP 服务端（v3.10.0）。

把博客的「应用层健康状态」以 MCP（Model Context Protocol）方式暴露出来，
供 AI 助手远程诊断——补的是云主机监控看不到的那一层：体检结果、应用日志、
数据库状态、渲染缓存命中率、版本与迁移是否一致。

传输：MCP Streamable HTTP 的**最小子集**
- 只支持 POST，响应一律 `application/json`（不流式）。规范允许服务器对每个
  请求自行选择返回单 JSON 或 SSE 流；这里的工具都是一问一答的快速查询，
  没有流式必要，因此用 Flask 即可实现，无需 ASGI / 额外依赖。
- 方法：`initialize`、`tools/list`、`tools/call`、`notifications/*`。
- 未使用会话（MCP 2026-07 修订后会话为可选），无状态更好运维。

安全红线（缺一不可）：
1. **只读**：所有工具只做查询，代码层面不开放任何写操作；
2. ** Bearer Token 认证**：未配置 `MCP_AUTH_TOKEN` 时端点整体关闭（fail-closed）；
3. **Origin 校验**：MCP 规范要求，防 DNS 重绑定攻击；
4. **限流**：按 IP 限流，异常返回 429；
5. **日志脱敏**：读取的日志内容统一打码密钥/口令/Token。
"""
import os
import re
import hmac
import platform

from flask import Blueprint, request, jsonify, current_app

# 无 url_prefix：端点就是 /mcp（不要塞进 /api 前缀，MCP 客户端按约定路径访问）
mcp_bp = Blueprint("mcp", __name__)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "llhhy-blog-diag", "version": "1.0.0"}

# 日志脱敏：把这些值统一替换成 ***，避免密钥经 MCP 外泄
_REDACT_RULES = [
    (re.compile(r"(?i)(secret[_-]?key\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(password\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(token\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})"), r"\1***"),
]


def _redact(text):
    for pat, rep in _REDACT_RULES:
        text = pat.sub(rep, text)
    return text


# ---------------------------------------------------------------------------
# 安全前置
# ---------------------------------------------------------------------------
def _token_ok():
    """校验 Authorization: Bearer <token>。未配置 token 时一律拒绝（fail-closed）。"""
    expected = current_app.config.get("MCP_AUTH_TOKEN", "")
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth[7:].strip(), expected)


def _origin_ok():
    """MCP 规范要求：带 Origin 头时必须校验，防 DNS 重绑定。

    非浏览器客户端（curl / MCP 客户端）通常不带 Origin，放行；
    带 Origin 则必须同源或在 MCP_ALLOWED_ORIGINS 白名单内。
    """
    origin = request.headers.get("Origin")
    if not origin:
        return True
    allowed = {f"{request.scheme}://{request.host}"}
    cfg = (current_app.config.get("MCP_ALLOWED_ORIGINS") or "").strip()
    allowed.update(o.strip() for o in cfg.split(",") if o.strip())
    return origin in allowed


# ---------------------------------------------------------------------------
# 只读工具实现（每个都必须能在异常时自己兜住，返回结构化信息而不是抛出去）
# ---------------------------------------------------------------------------
def tool_health_overview(args):
    """全站体检摘要：各维度状态 + 异常/警告条目。"""
    import diagnostics
    data = diagnostics.run_all()
    only = (args.get("section") or "").strip()
    sections = []
    for sec in data.get("sections", []):
        if only and sec.get("key") != only and sec.get("title") != only:
            continue
        rows = sec.get("rows") or sec.get("items") or []
        bad = [r for r in rows if r.get("level") in ("error", "warn")]
        sections.append({
            "key": sec.get("key"),
            "title": sec.get("title"),
            "status": sec.get("status"),
            "issues": [{"label": r.get("label"), "value": r.get("value"),
                        "level": r.get("level")} for r in bad][:20],
            "notes": (sec.get("notes") or [])[:5],
        })
    return {
        "generated_at": data.get("generated_at"),
        "summary": data.get("summary"),
        "sections": sections,
        "hint": "status 取值 ok/warn/error；issues 只列异常与警告项。",
    }


def tool_db_status(args):
    """数据库状态：WAL 是否生效、库体积、渲染缓存命中率。"""
    from models import db, Post, Comment, User
    from sqlalchemy import text
    out = {}
    try:
        out["journal_mode"] = db.session.execute(text("PRAGMA journal_mode")).scalar()
        out["busy_timeout_ms"] = db.session.execute(text("PRAGMA busy_timeout")).scalar()
    except Exception as e:
        out["pragma_error"] = f"{type(e).__name__}: {e}"

    try:
        path = db.engine.url.database
        if path and os.path.exists(path):
            out["db_path"] = path
            out["db_size_kb"] = round(os.path.getsize(path) / 1024, 1)
            for suf in ("-wal", "-shm"):
                p = path + suf
                if os.path.exists(p):
                    out[f"size{suf.replace('-', '_')}_kb"] = round(os.path.getsize(p) / 1024, 1)
    except Exception as e:
        out["size_error"] = f"{type(e).__name__}: {e}"

    try:
        total = Post.query.count()
        cached = Post.query.filter(Post.content_html.isnot(None)).count()
        out["posts"] = total
        out["render_cache_filled"] = cached
        out["render_cache_pct"] = round(cached * 100.0 / total, 1) if total else 0.0
        out["comments"] = Comment.query.count()
        out["users"] = User.query.count()
    except Exception as e:
        out["query_error"] = f"{type(e).__name__}: {e}"

    out["hint"] = ("render_cache_pct 低是正常的——文章首次访问才填充缓存；"
                   "journal_mode 应为 wal（显示 delete 说明 data/ 目录不可写）。")
    return out


def tool_version_info(args):
    """版本与迁移一致性：代码版本、缓存列是否已迁移、插件启用情况。"""
    import config as cfg_mod
    from models import db
    from sqlalchemy import inspect
    out = {"app_version": getattr(cfg_mod, "APP_VERSION", "unknown"),
           "python": platform.python_version()}
    try:
        import flask
        out["flask"] = flask.__version__
    except Exception:
        pass

    # 迁移一致性：检查 v3.9.1 的渲染缓存列是否已补上
    try:
        cols = [c["name"] for c in inspect(db.engine).get_columns("post")]
        out["post_columns_ok"] = {"content_html": "content_html" in cols,
                                  "content_hash": "content_hash" in cols}
    except Exception as e:
        out["post_columns_error"] = f"{type(e).__name__}: {e}"

    # 插件启用情况（只读，不触发加载）
    try:
        out["enabled_plugins"] = (current_app.config.get("ENABLED_PLUGINS") or "").strip()
        out["disabled_plugins"] = (current_app.config.get("DISABLED_PLUGINS") or "").strip()
        out["mcp_enabled"] = bool(current_app.config.get("MCP_AUTH_TOKEN"))
    except Exception:
        pass
    return out


def _tail_lines(path, n):
    """读文件末尾 n 行（最多回看 512KB，避免超大日志把内存打满）。"""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        back = min(size, 512 * 1024)
        f.seek(size - back)
        chunk = f.read(back)
    text = chunk.decode("utf-8", "replace")
    return text.splitlines()[-n:]


def tool_recent_errors(args):
    """最近错误日志尾部。只读取 MCP_LOG_FILES 显式配置的日志文件。"""
    files = [p.strip() for p in (current_app.config.get("MCP_LOG_FILES") or "").split(",")
             if p.strip()]
    if not files:
        return {
            "configured": False,
            "hint": ("未配置 MCP_LOG_FILES，无法读取日志。"
                     "在环境变量里填绝对路径（逗号分隔），例如 "
                     "MCP_LOG_FILES=/www/wwwroot/xxx/logs/error.log"),
        }
    try:
        n = int(args.get("lines", 50))
    except Exception:
        n = 50
    n = max(1, min(n, 200))

    result = {}
    for p in files:
        if not os.path.isfile(p):
            result[p] = {"error": "文件不存在或不是普通文件"}
            continue
        try:
            result[p] = {"lines": [_redact(l) for l in _tail_lines(p, n)]}
        except Exception as e:
            result[p] = {"error": f"{type(e).__name__}: {e}"}
    return {"configured": True, "lines_per_file": n, "files": result,
            "note": "内容已自动打码密钥/口令/Token。"}


def tool_content_stats(args):
    """内容统计：文章分布、待审核评论、未读留言等运营侧数字。"""
    from models import (db, Post, Comment, Guestbook, Subscriber,
                        LinkApplication, Notification)
    try:
        return {
            "posts": {
                "total": Post.query.count(),
                "published": Post.query.filter_by(published=True, in_trash=False).count(),
                "draft": Post.query.filter_by(published=False, in_trash=False).count(),
                "private": Post.query.filter_by(is_private=True).count(),
                "in_trash": Post.query.filter_by(in_trash=True).count(),
                "scheduled": Post.query.filter(Post.scheduled_at.isnot(None)).count(),
            },
            "comments": {
                "total": Comment.query.count(),
                "pending": Comment.query.filter_by(approved=False).count(),
            },
            "guestbook_unread": Guestbook.query.filter_by(is_read=False).count(),
            "subscribers": Subscriber.query.count(),
            "link_applications_pending": LinkApplication.query.filter_by(status="pending").count(),
            "notifications_unread": Notification.query.filter_by(is_read=False).count(),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


TOOLS = {
    "health_overview": {
        "description": ("运行全站体检，返回各维度状态与异常/警告条目。"
                        "可传 section 只看某一维（如 database、backup、feed_agg）。"),
        "inputSchema": {"type": "object", "properties": {
            "section": {"type": "string", "description": "可选，只返回指定维度的 key 或标题"}}},
        "fn": tool_health_overview,
    },
    "db_status": {
        "description": ("数据库状态：journal_mode 是否为 WAL、库与 WAL 文件体积、"
                        "文章数与正文渲染缓存命中率。"),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": tool_db_status,
    },
    "version_info": {
        "description": "代码版本、Python/Flask 版本、数据库迁移列是否齐全、插件启用情况。",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": tool_version_info,
    },
    "recent_errors": {
        "description": ("读取最近的应用错误日志尾部（仅 MCP_LOG_FILES 配置的文件）。"
                        "内容自动打码密钥/口令/Token。"),
        "inputSchema": {"type": "object", "properties": {
            "lines": {"type": "integer", "description": "每个文件读取的末尾行数，1-200，默认 50"}}},
        "fn": tool_recent_errors,
    },
    "content_stats": {
        "description": "内容统计：文章分布（发布/草稿/隐私/回收站/定时）、待审核评论、未读留言等。",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": tool_content_stats,
    },
}


# ---------------------------------------------------------------------------
# JSON-RPC 端点
# ---------------------------------------------------------------------------
def _result(rid, result):
    return jsonify({"jsonrpc": "2.0", "id": rid, "result": result})


def _error(rid, code, message):
    return jsonify({"jsonrpc": "2.0", "id": rid,
                    "error": {"code": code, "message": message}})


@mcp_bp.route("/mcp", methods=["POST"])
def mcp_endpoint():
    # ① Origin 校验（MCP 规范强制，防 DNS 重绑定）
    if not _origin_ok():
        return jsonify({"error": "Origin 不被允许"}), 403
    # ② 认证：未配置 token 时整站关闭（fail-closed）
    if not _token_ok():
        return jsonify({"error": "未授权：需要有效的 Bearer Token"}), 401
    # ③ 限流（与全站一致的 IP 限流，异常时放行以免误伤自己）
    try:
        from utils import rate_limit, client_key
        if not rate_limit(client_key("mcp"), limit=60, window=60):
            return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    except Exception:
        pass

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(None, -32600, "请求体必须是 JSON 对象")
    method = body.get("method")
    rid = body.get("id")
    params = body.get("params") or {}

    # notification（无 id）：返回 202 空响应
    if rid is None:
        return ("", 202)

    if method == "initialize":
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        return _result(rid, {"tools": [
            {"name": name,
             "description": spec["description"],
             "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ]})

    if method == "tools/call":
        name = (params or {}).get("name")
        arguments = (params or {}).get("arguments") or {}
        spec = TOOLS.get(name)
        if not spec:
            return _error(rid, -32602, f"未知工具：{name}")
        try:
            data = spec["fn"](arguments if isinstance(arguments, dict) else {})
            import json as _json
            text = _json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return _result(rid, {"content": [
                {"type": "text", "text": f"工具执行失败：{type(e).__name__}: {e}"}],
                "isError": True})
        return _result(rid, {"content": [{"type": "text", "text": text}]})

    return _error(rid, -32601, f"不支持的方法：{method}")


@mcp_bp.route("/mcp", methods=["GET", "PUT", "DELETE", "PATCH"])
def mcp_method_not_allowed():
    """本实现不使用 SSE GET 流与会话删除（只读一问一答），明确拒绝。"""
    return jsonify({"error": "本 MCP 端点仅支持 POST（JSON-RPC 单响应，不提供 SSE 流）"}), 405
