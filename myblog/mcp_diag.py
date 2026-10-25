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

工具清单（v4.11.0 起 8 个，与体检的 19 个维度对齐）：
- `health_overview`：全站体检摘要（只列异常/警告项，可传 section 缩到一维）
- `health_score`：评分（0-100）+ 各维度状态一览
- `issues`：跨维度问题清单，按严重度排序（先问「哪里坏了」用这个）
- `run_check`：只跑单维，返回**不裁剪**的完整明细（排障看实际值用这个）
- `db_status` / `version_info` / `recent_errors` / `content_stats`：数据库、版本、日志、内容统计

⚠️ 新增工具的两条硬约定：
- 明细一律复用 `diagnostics.*` 的 checker，**不在 MCP 层另写一套统计**（两套口径必然漂移）；
- 新维度只需要在 `diagnostics.CHECKS` / `diagnostics.CHECKS_BY_KEY` 登记，
  `run_check` 的可选值随之自动扩展 —— 不要在 `inputSchema` 里手写枚举后忘记更新。
"""
import os
import re
import hmac
import platform

from flask import Blueprint, request, jsonify, current_app

# 无 url_prefix：端点就是 /mcp（不要塞进 /api 前缀，MCP 客户端按约定路径访问）
mcp_bp = Blueprint("mcp", __name__)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "llhhy-blog-diag", "version": "1.1.0"}

# 日志脱敏：把这些值统一替换成 ***，避免密钥经 MCP 外泄
_REDACT_RULES = [
    (re.compile(r"(?i)(secret[_-]?key\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)((?:pass(?:word|wd)|pwd)\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(token\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})"), r"\1***"),
    # R115 审计：上面 5 条都要求「key 与值之间只有空白」，于是**裸令牌**漏网——
    # 而日志里 `用 token sk-abc123... 调接口` 这种写法极常见。补常见前缀的裸值规则。
    (re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})"), "sk-***"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})"), "gh*_***"),
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})"), "AKIA***"),
    # Fernet 密文（bkenc$ 前缀）本体也不该出现在日志/诊断输出里
    (re.compile(r"\b(bkenc\$[A-Za-z0-9_\-]{20,})"), "bkenc$***"),
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
    # R114 审计：`hmac.compare_digest(str, str)` 遇到**非 ASCII** 会抛
    # `TypeError: comparing strings with non-ASCII characters is not supported`，
    # 而本函数只被 `except (HTTPException, redis.RedisError)` 包裹 → 匿名发一个
    # `Authorization: Bearer 💥` 就能拿到 **500**（未审计错误路径 + 错误信息分类错乱）。
    # 统一按 UTF-8 编码成 bytes 再比：既能处理任意字节，又是恒定时间。
    token = auth[7:].strip().encode("utf-8", "surrogatepass")
    return hmac.compare_digest(token, expected.encode("utf-8"))


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


def tool_db_status(args):  # noqa: ARG001  签名由调用方/接口约定决定，不能删改
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


def tool_version_info(args):  # noqa: ARG001  签名由调用方/接口约定决定，不能删改
    """版本与迁移一致性：代码版本、缓存列是否已迁移、插件启用情况。"""
    import config as cfg_mod
    from models import db
    from sqlalchemy import inspect
    out = {"app_version": getattr(cfg_mod, "APP_VERSION", "unknown"),
           "python": platform.python_version()}
    try:
        import flask
        out["flask"] = flask.__version__
    except Exception:  # noqa: S110  旁路/兜底路径，失败按降级处理，不影响主流程
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
    except Exception:  # noqa: S110  配置读取失败按默认值处理，不影响端点可用性
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


def tool_content_stats(args):  # noqa: ARG001  签名由调用方/接口约定决定，不能删改
    """内容统计：文章分布、待审核评论、未读留言等运营侧数字。"""
    from models import (Post, Comment, Guestbook, Subscriber,
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


def tool_issues(args):
    """跨维度问题清单（error 优先），v4.11.0。

    比 `health_overview` 更适合「先告诉我哪里坏了」这种问法：它把 19 个维度里的
    error/warn 项拉平成一张按严重度排序的清单，AI 不需要自己遍历 sections 再筛。
    """
    import diagnostics
    data = diagnostics.run_all()
    level = (args.get("level") or "").strip().lower()
    try:
        limit = int(args.get("limit") or 50)
    except (TypeError, ValueError):   # 参数类型不对就用默认值，不值得让整个调用失败
        limit = 50
    limit = max(1, min(limit, 200))
    issues = data.get("issues") or []
    if level in ("error", "warn"):
        issues = [i for i in issues if i.get("level") == level]
    return {
        "generated_at": data.get("generated_at"),
        "score": data.get("score"),
        "issue_total": data.get("issue_total"),
        "returned": min(len(issues), limit),
        "issues": issues[:limit],
        "hint": ("level 可传 error / warn 只看某一级；每项含 key（维度标识，可传给 "
                 "run_check 或 health_overview.section 看详情）。"),
    }


def tool_health_score(args):  # noqa: ARG001  签名由调用方/接口约定决定，不能删改
    """健康评分与各维度状态一览（不含明细行）。"""
    import diagnostics
    data = diagnostics.run_all()
    return {
        "generated_at": data.get("generated_at"),
        "score": data.get("score"),
        "summary": data.get("summary"),
        "issue_total": data.get("issue_total"),
        "dimensions": [{"key": s.get("key"), "title": s.get("title"),
                        "status": s.get("status"),
                        "issues": len([r for r in (s.get("items") or [])
                                       if r.get("level") in ("error", "warn")])}
                       for s in (data.get("sections") or [])],
        "hint": ("score 为维度均分（异常 0 / 警告 0.5 / 正常 1）。"
                 "先看 status != ok 的维度，再用 run_check 取该维明细。"),
    }


def tool_run_check(args):
    """只跑单个体检维度，返回该项的全部明细行。

    为什么单独给工具而不复用 `health_overview(section=...)`：后者的返回被裁成
    「只列异常项」，而排障时经常需要看**正常项的实际值**（比如 db 体积、WAL 模式、
    证书到期日）。这里返回完整 items，不做裁剪。
    """
    import diagnostics
    key = (args.get("check") or "").strip()
    available = sorted(diagnostics.CHECKS_BY_KEY)
    if not key:
        return {"error": "需要 check 参数", "available": available}
    fn = diagnostics.CHECKS_BY_KEY.get(key)
    if not fn:
        return {"error": f"未知维度：{key}", "available": available}
    try:
        sec = diagnostics._normalize(fn())
    except Exception as e:  # noqa: BLE001  checker 可能抛任意异常（第三方库/IO），此处必须转成结构化错误而不是让 MCP 崩掉
        return {"check": key, "status": "error",
                "error": f"{type(e).__name__}: {e}"}
    return {
        "check": key,
        "title": sec.get("title"),
        "status": sec.get("status"),
        "items": sec.get("items") or [],
        "notes": sec.get("notes") or [],
        "per_link": sec.get("per_link") or [],
    }


TOOLS = {
    "health_overview": {
        "description": ("运行全站体检，返回各维度状态与异常/警告条目。"
                        "可传 section 只看某一维（如 database、backup、feed_agg）。"),
        "inputSchema": {"type": "object", "properties": {
            "section": {"type": "string", "description": "可选，只返回指定维度的 key 或标题"}}},
        "fn": tool_health_overview,
    },
    "health_score": {
        "description": ("健康评分（0-100）与 19 个维度的状态一览，不含明细行。"
                        "适合先快速判断「整体到底有多糟」。"),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": tool_health_score,
    },
    "issues": {
        "description": ("跨维度问题清单，按严重度排序（error 在前）。"
                        "每项含 key/dimension/label/value/level，可直接指出该怎么修。"),
        "inputSchema": {"type": "object", "properties": {
            "level": {"type": "string", "description": "可选，error 或 warn，只看某一级"},
            "limit": {"type": "integer", "description": "返回条数上限，1-200，默认 50"}}},
        "fn": tool_issues,
    },
    "run_check": {
        "description": ("只跑单个体检维度，返回该维全部明细（不裁剪，含正常项实际值）。"
                        "check 取值见 health_score 的 dimensions[].key。"),
        "inputSchema": {"type": "object", "properties": {
            "check": {"type": "string",
                      "description": ("维度 key：database / dependencies / config / security / "
                                      "feed_agg / backup / certificate / seo / pending / "
                                      "frontend / storage / render_cache / plugins / "
                                      "search_index / scheduler / outbound / "
                                      "content_quality / disk / mcp")}},
         "required": ["check"]},
        "fn": tool_run_check,
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
    # ⓪ 后台「MCP 服务」面板总开关：停止 → 对外 404（不暴露端点存在），即时生效
    try:
        from utils import get_setting
        if (get_setting("mcp_diag_disabled") or "").strip().lower() == "true":
            return jsonify({"error": "not found"}), 404
    except Exception:  # noqa: S110  可选依赖/可选模块，缺了就跳过这条增强路径
        pass  # 开关读取失败按未设置处理（默认开启），不影响端点自身可用性
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
    except Exception:  # noqa: S110  可选依赖/可选模块，缺了就跳过这条增强路径
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
