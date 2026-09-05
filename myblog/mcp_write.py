"""写能力 MCP 服务端（v3.12.2）。

让 AI 助手能远程创建博客文章——补的是「只读诊断 MCP（/mcp）」缺失的那一环：
AI 既能读健康状态，也能在授权下自动发文。

设计红线（与只读 /mcp 完全隔离，缺一不可）：
1. **独立端点 / 独立 token / 独立配置**：Blueprint 名 mcp_write_bp、端点 /mcp-write，
   认证读 MCP_WRITE_TOKEN；MCP_WRITE_TOKEN 缺失时整体 404（fail-closed，绝不暴露端点存在），
   且必须与只读 MCP_AUTH_TOKEN 取不同值，缩小泄露影响面。
2. **默认草稿**：publish 未显式为 true 时不发布。
3. **强制草稿开关**：MCP_WRITE_DEFAULT_PUBLISH != "1" 时，即使传 publish=true 也强制存草稿。
4. **禁止提权字段**：is_pinned/is_private/reward_enabled/reward_qr/author_id/views/likes
   一律不接受 MCP 传入；仅 MCP_WRITE_ALLOW_SUPER_FIELDS == "1" 时才接受前四个（且校验目标用户存在）。
5. **群发默认关闭**：仅 MCP_WRITE_ALLOW_NOTIFY == "1" 且显式传 notify_subscribers=true
   才触发订阅者邮件群发（防 AI 循环失控反复骚扰订阅者）。
6. **幂等**：同 idempotency_key（或同标题+当日）24h 内重复调用返回已存在文章，不新建。
7. **slug 冲突不覆盖**：apply_slug_template 后若 slug 已存在追加 -2/-3 后缀，绝不覆盖既有文章。
8. **审计**：每次调用写一条 AuditLog（action=mcp_create_post，username=mcp，token 前 8 位，来源 IP）。
9. **正文上限**：content 超 200000 字符直接拒绝，不落库。
10. **XSS**：正文渲染走既有管线（content_html 缓存机制），本模块不自己拼 HTML、不绕过清洗。

传输：沿用只读 MCP 的「Streamable HTTP 最小子集」——只 POST、application/json 单响应、
initialize/tools/list/tools/call 三方法、非 POST 一律 405。安全骨架（_token_ok / _origin_ok /
限流 / JSON-RPC 编排）照抄 mcp_diag.py。
"""
import datetime
import hmac
import json as _json
import time

from flask import Blueprint, request, jsonify, current_app

from models import db, Post, Category, AuditLog
from admin._helpers import create_post_core
from utils import rate_limit, client_key, get_client_ip, _redis

# 无 url_prefix：端点就是 /mcp-write（与 /mcp 对称，MCP 客户端按约定路径访问）
mcp_write_bp = Blueprint("mcp_write", __name__)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "llhhy-blog-write", "version": "1.0.0"}

# 正文硬上限（字符），超出直接拒绝不落库
MAX_CONTENT = 200000

# 幂等兜底存储（单进程内存；配置了 REDIS_URL 时走 Redis，跨 worker 一致）
_IDEM = {}


# ---------------------------------------------------------------------------
# 安全前置（照抄 mcp_diag，认证/Origin 各自独立配置）
# ---------------------------------------------------------------------------
def _token_ok():
    """校验 Authorization: Bearer <token>。未配置 token 时一律拒绝（fail-closed）。"""
    expected = current_app.config.get("MCP_WRITE_TOKEN", "")
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth[7:].strip(), expected)


def _origin_ok():
    """MCP 规范要求：带 Origin 头时必须校验，防 DNS 重绑定（白名单复用 MCP_ALLOWED_ORIGINS）。"""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    allowed = {f"{request.scheme}://{request.host}"}
    cfg = (current_app.config.get("MCP_ALLOWED_ORIGINS") or "").strip()
    allowed.update(o.strip() for o in cfg.split(",") if o.strip())
    return origin in allowed


def _token_prefix():
    """token 前 8 位（审计用，不记完整 token）。"""
    t = current_app.config.get("MCP_WRITE_TOKEN", "")
    return t[:8] if t else ""


def _idem_check(key):
    """返回 24h 内已落库的文章 id（幂等命中），否则 None。"""
    now = time.time()
    r = _redis()
    if r is not None:
        try:
            v = r.get("blog:mcpw:idem:" + key)
            if v:
                return int(v)
        except Exception:
            pass
    item = _IDEM.get(key)
    if item and now - item[1] < 86400:
        return item[0]
    return None


def _idem_mark(key, post_id):
    """记录 idempotency_key → post_id（24h TTL）。"""
    try:
        r = _redis()
        if r is not None:
            r.set("blog:mcpw:idem:" + key, post_id, ex=86400)
    except Exception:
        pass
    _IDEM[key] = (post_id, time.time())


def _write_audit(target_id, ok, detail):
    """审计：每次调用（含失败）都写一条 AuditLog，username 固定为 mcp。"""
    ip = get_client_ip() or ""
    try:
        db.session.add(AuditLog(
            user_id=None, username="mcp",
            action="mcp_create_post", target="post",
            target_id=target_id, detail=(detail or "")[:300],
            ip=ip[:64], success=ok,
        ))
        db.session.commit()
    except Exception:
        pass


def _parse_iso(s):
    """把 ISO8601（UTC，支持 Z/偏移）解析为 naive UTC datetime。"""
    s = (s or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
def tool_create_post(args):
    args = args or {}
    title = (args.get("title") or "").strip()
    content = args.get("content") or ""

    # 输入校验（失败直接抛错 → 由端点包装成 isError，不落库）
    if not title:
        raise ValueError("标题不能为空（1-200 字符）")
    if len(title) > 200:
        raise ValueError("标题超过 200 字符上限")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("正文不能为空（Markdown）")
    if len(content) > MAX_CONTENT:
        raise ValueError(f"正文超过 {MAX_CONTENT} 字符上限，已拒绝，不落库")
    summary = (args.get("summary") or "").strip()[:400]
    cover = (args.get("cover") or "").strip()
    seo_description = (args.get("seo_description") or "").strip()
    seo_keywords = (args.get("seo_keywords") or "").strip()

    # category_id：需校验存在，不存在则报错不猜
    category_id = args.get("category_id")
    if category_id not in (None, ""):
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise ValueError("category_id 必须是整数")
        if Category.query.get(category_id) is None:
            raise ValueError("category_id 不存在（不猜，请传入有效分类 id）")
    else:
        category_id = None

    # series_id
    series_id = args.get("series_id")
    if series_id not in (None, ""):
        try:
            series_id = int(series_id)
        except (TypeError, ValueError):
            raise ValueError("series_id 必须是整数")
    else:
        series_id = None

    tags = args.get("tags") or ""

    # —— 发布闸门 ——
    publish = bool(args.get("publish", False))
    default_publish = current_app.config.get("MCP_WRITE_DEFAULT_PUBLISH", "0") == "1"
    warnings = []
    if publish and not default_publish:
        publish = False
        warnings.append("已按配置强制存为草稿（MCP_WRITE_DEFAULT_PUBLISH != '1'）")

    # 定时发布：ISO8601 UTC
    scheduled_at = None
    sched_raw = args.get("scheduled_at")
    if sched_raw:
        try:
            scheduled_at = _parse_iso(sched_raw)
        except Exception:
            raise ValueError("scheduled_at 必须是 ISO8601(UTC) 时间字符串")

    # —— 提权字段闸门（默认一律忽略）——
    allow_super = current_app.config.get("MCP_WRITE_ALLOW_SUPER_FIELDS", "0") == "1"
    is_pinned = is_private = reward_enabled = False
    reward_qr = ""
    author_id = None
    if allow_super:
        is_pinned = bool(args.get("is_pinned", False))
        is_private = bool(args.get("is_private", False))
        reward_enabled = bool(args.get("reward_enabled", False))
        reward_qr = (args.get("reward_qr") or "").strip() if reward_enabled else ""
        aid = args.get("author_id")
        if aid not in (None, ""):
            try:
                aid = int(aid)
            except (TypeError, ValueError):
                raise ValueError("author_id 必须是整数")
            from models import User
            if User.query.get(aid) is None:
                raise ValueError("author_id 不存在（不猜）")
            author_id = aid
    else:
        # 任何提权字段（含被恶意传入）一律忽略，并写入 warnings 提示
        for f in ("is_pinned", "is_private", "reward_enabled", "reward_qr", "author_id"):
            v = args.get(f)
            if v not in (None, False, "", 0):
                warnings.append(f"已忽略提权字段 {f}（MCP_WRITE_ALLOW_SUPER_FIELDS != '1'）")

    # —— 群发闸门 ——
    notify_subscribers = bool(args.get("notify_subscribers", False))
    if notify_subscribers and current_app.config.get("MCP_WRITE_ALLOW_NOTIFY", "0") != "1":
        notify_subscribers = False
        warnings.append("已忽略订阅者群发（MCP_WRITE_ALLOW_NOTIFY != '1'）")

    # —— 幂等：同 idempotency_key 或 同标题+当日 24h 内 → 返回已存在，不新建 ——
    idem_key = (args.get("idempotency_key") or "").strip()
    existing_id = _idem_check(idem_key) if idem_key else None
    if existing_id is None and title:
        start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ex = Post.query.filter(Post.title == title, Post.created_at >= start).order_by(
            Post.created_at.desc()).first()
        if ex is not None:
            existing_id = ex.id
    if existing_id is not None:
        post = Post.query.get(existing_id)
        if post is not None:
            _write_audit(post.id, True,
                         f"幂等命中：{title[:120]} | token={_token_prefix()}")
            return _post_result(post, warnings=warnings, deduplicated=True)

    # —— 落库（复用发文唯一入口）——
    try:
        post = create_post_core(
            title=title, content=content, summary=summary, cover=cover,
            category_id=category_id, tags=tags, series_id=series_id,
            seo_description=seo_description, seo_keywords=seo_keywords,
            published=publish, scheduled_at=scheduled_at, author_id=author_id,
            is_pinned=is_pinned, is_private=is_private,
            reward_enabled=reward_enabled, reward_qr=reward_qr,
            notify_subscribers=notify_subscribers,
        )
    except Exception as e:
        _write_audit(None, False, f"创建失败：{title[:120]} | {type(e).__name__}: {e}")
        raise

    if idem_key:
        _idem_mark(idem_key, post.id)
    _write_audit(post.id, True,
                 f"{title[:120]} | published={post.published} | token={_token_prefix()}")
    return _post_result(post, warnings=warnings, deduplicated=False)


def tool_list_recent_posts(args):
    """列出最近 N 篇文章（不含正文），供发文前查重。"""
    args = args or {}
    try:
        limit = int(args.get("limit", 10))
    except Exception:
        limit = 10
    limit = max(1, min(limit, 100))
    posts = Post.query.filter_by(in_trash=False).order_by(
        Post.created_at.desc()).limit(limit).all()
    return {
        "posts": [
            {"id": p.id, "title": p.title, "slug": p.slug,
             "published": bool(p.published),
             "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in posts
        ]
    }


def _post_result(post, warnings, deduplicated):
    return {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "published": bool(post.published),
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "url": "/post/" + (post.slug or ""),
        "word_count": post.word_count,
        "reading_minutes": post.reading_minutes,
        "warnings": warnings,
        "deduplicated": deduplicated,
    }


TOOLS = {
    "create_post": {
        "description": ("创建一篇博客文章。默认存草稿；仅当 MCP_WRITE_DEFAULT_PUBLISH=1 且显式 "
                        "publish=true 才发布。不接收任何提权字段（is_pinned/is_private/reward_*/"
                        "author_id）除非 MCP_WRITE_ALLOW_SUPER_FIELDS=1。返回 id/slug/url 等。"),
        "inputSchema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "标题，1-200 字符，必填"},
            "content": {"type": "string", "description": "Markdown 正文，上限 200000 字符，必填"},
            "summary": {"type": "string", "description": "摘要，≤400 字符"},
            "cover": {"type": "string", "description": "封面图 URL"},
            "category_id": {"type": "integer", "description": "分类 id，需存在"},
            "tags": {"type": "string", "description": "逗号分隔标签"},
            "series_id": {"type": "integer", "description": "系列 id"},
            "seo_description": {"type": "string", "description": "页面 meta description"},
            "seo_keywords": {"type": "string", "description": "页面 meta keywords"},
            "publish": {"type": "boolean", "description": "是否发布（受 MCP_WRITE_DEFAULT_PUBLISH 闸门约束）"},
            "scheduled_at": {"type": "string", "description": "ISO8601 UTC 定时发布时间"},
            "idempotency_key": {"type": "string", "description": "幂等键，防重复发文（建议必传）"},
            "notify_subscribers": {"type": "boolean", "description": "是否群发订阅者邮件（受 MCP_WRITE_ALLOW_NOTIFY 闸门约束）"},
            "is_pinned": {"type": "boolean", "description": "仅 SUPER_FIELDS=1 时接受"},
            "is_private": {"type": "boolean", "description": "仅 SUPER_FIELDS=1 时接受"},
            "reward_enabled": {"type": "boolean", "description": "仅 SUPER_FIELDS=1 时接受"},
            "reward_qr": {"type": "string", "description": "仅 SUPER_FIELDS=1 时接受"},
            "author_id": {"type": "integer", "description": "仅 SUPER_FIELDS=1 时接受"}}},
        "fn": tool_create_post,
    },
    "list_recent_posts": {
        "description": "列出最近 N 篇文章（id/title/slug/published/created_at），不含正文，供发文前查重。",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "返回条数，1-100，默认 10"}}},
        "fn": tool_list_recent_posts,
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


@mcp_write_bp.route("/mcp-write", methods=["POST"])
def mcp_write_endpoint():
    # ⓪ 后台「MCP 服务」面板总开关：停止 → 对外 404（与未配 token 同口径，不暴露存在），即时生效
    try:
        from utils import get_setting
        if (get_setting("mcp_write_disabled") or "").strip().lower() == "true":
            return jsonify({"error": "not found"}), 404
    except Exception:
        pass  # 开关读取失败按未设置处理（默认开启），不影响端点自身可用性
    # ① Origin 校验（MCP 规范强制，防 DNS 重绑定）
    if not _origin_ok():
        return jsonify({"error": "Origin 不被允许"}), 403
    # ② 独立 token；缺失 → 404（绝不暴露端点存在）
    if not current_app.config.get("MCP_WRITE_TOKEN"):
        return jsonify({"error": "not found"}), 404
    if not _token_ok():
        return jsonify({"error": "未授权：需要有效的 Bearer Token"}), 401
    # ③ 限流（比只读更严：10/60s，异常时放行以免误伤自己）
    try:
        if not rate_limit(client_key("mcp_write"), limit=10, window=60):
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
            text = _json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            # 输入校验/落库异常一律以 isError 返回，正文不落库由调用方保证
            return _result(rid, {"content": [
                {"type": "text", "text": f"工具执行失败：{type(e).__name__}: {e}"}],
                "isError": True})
        return _result(rid, {"content": [{"type": "text", "text": text}]})

    return _error(rid, -32601, f"不支持的方法：{method}")


@mcp_write_bp.route("/mcp-write", methods=["GET", "PUT", "DELETE", "PATCH"])
def mcp_write_method_not_allowed():
    """本实现不使用 SSE GET 流与会话删除，明确拒绝。"""
    return jsonify({"error": "本 MCP 端点仅支持 POST（JSON-RPC 单响应，不提供 SSE 流）"}), 405
