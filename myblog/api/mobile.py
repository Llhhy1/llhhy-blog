# -*- coding: utf-8 -*-
"""移动端管理接口（v4.3.0 起，v4.4.0 补齐内容管理全套，共 66 个端点）：把后台管理能力以
JSON 暴露给原生 App / 第三方客户端。

## 为什么要有这个模块

`/admin/*` 是 Jinja2 服务端渲染页面：手机上要么用浏览器缩放，要么用 WebView 套壳。
两条路都把「桌面多列表格」原样搬进 5 寸屏，而且壳除了登录保活拿不到任何原生能力
（通知角标、下拉刷新、滑动操作、离线草稿都没有）。本模块把**同一条业务逻辑**改成
JSON 输出，客户端可以用列表 / 卡片 / 滑动操作原生生成，排版与站点解耦。

## 三条设计约束（改动前请读）

1. **零业务复制**：发文 / 编辑 / 发布 / 软删 / 还原 / 拉黑等写入全部复用后台既有实现
   （`create_post_core` / `update_post_core` / `publish_post_core` / `trash_post_core` /
   `restore_recycle_core` / `bot_guard.block_ip` / `audit.log_audit`）。本模块只做
   「取参 → 鉴权 → 调既有核心 → 序列化」。两套逻辑漂移是本仓库明确反对的
   （见 `admin/_helpers.py::create_post_core` 的 docstring）。
2. **不能复用 `admin._helpers` 的权限装饰器**：`admin_required` / `super_required` 未登录时
   是 **302 跳登录页**（HTML 语义），客户端会拿到一页登录 HTML 而不是错误码。
   故本文件用自己的 `_role()`，一律返回 `401/403 + {"error": "…"}`。
3. **对 `admin` 包的引用必须写在函数里**：`admin/ai_summary.py` 顶层已有
   `from api.ai import ...` 这条 `admin → api` 边，本文件若再顶层 `from admin...` 就构成
   `api ↔ admin` 强连通分量，`tests/test_no_module_import_cycles.py` 直接红。
   函数内 import 不进模块级 import 图（该测试 docstring 建图口径第 1 条），
   这也是 `api/theme.py` / `seo_push.py` 既有做法。

## 鉴权 / CSRF / 2FA 的实际链路（客户端必读）

- **登录**：`POST /api/auth/login` → 服务端写 Flask 会话并 `Set-Cookie: session=...`。
  该 cookie **没有 Expires/Max-Age（会话级）**，客户端必须自行持久化并在重启后回填，
  详见 `API.md`「移动端管理接口」。
- **CSRF**：本模块所有写方法（POST/PUT/DELETE）都受 `app.py` 全局闸门保护，需带
  `X-CSRF-Token`（登录后 `GET /api/csrf` 取，或直接用登录响应里的 `csrf_token`）。
  缺失/错误 → `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`。
- **2FA**：账号启用第二因素而会话未通过时，全局闸门对 `/api/` 返回
  `401 {"error": "twofa_required", "twofa_required": true}`，客户端应引导走
  `/api/auth/2fa/verify` 后重试。
- **角色**：只读运营数据 = 管理员（super/admin）；发文与编辑 = 任意登录用户（普通用户
  只能看/改自己 `author_id` 的文章，沿用 `_can_edit_post`）；直改置顶、拉黑/解封 = 超管。
  **v4.3.1 例外**：`/mobile/visit-logs` 与 `/mobile/blocked` 也是超管专属 —— 它们输出访客
  IP 原文，且解封本就是超管动作（理由与残留风险见 SECURITY_AUDIT R120.5 / R121）。
  **v4.4.0 内容全套**（公告 / 留言 / 订阅 / 分类·标签·系列 / 友链本体 / 版本历史 / 媒体库）
  与对应后台页面同级 = 管理员，版本历史与回滚 = 可编辑者。
- **PII 分层（v4.4.0，判据见 SECURITY_AUDIT R122）**：同一字段可以按角色给不同形态 ——
  留言 `ip` 只出现在超管响应里（管理员拿 `region`/`device`）；订阅 `email` 对管理员遮敏、
  对超管全量；`Subscriber.unsub_token` **任何角色都不返回**（拿到就能替别人免登录退订）。
  审计 `detail` 里不写 IP / 设备 / 完整邮箱。
- **状态类写接口收显式目标值**（`{"active": true|false}`），不收「翻转」：网页按钮的翻转
  语义在弱网重发下会来回横跳。缺该字段报 400，不静默按 `False` 落库（`_need_flag`）。
- **限流**：写接口按客户端 IP 限流（`utils.rate_limit`），超限 `429`。只读接口沿用
  `/api/stats/*` 的口径（30/分钟）或不限流。
"""
import contextlib

from flask import current_app, jsonify, request, url_for
from sqlalchemy import func

from models import (Announcement, BotBlock, Category, Comment, FriendLink, Guestbook,
                    LinkApplication, Moment, Notification, Post, PostHistory, RecycleBin,
                    Series, Subscriber, Tag, User, VisitLog, db)
from utils import client_key, fmt_bj, rate_limit
from _time import utcnow

from .common import api_bp, _comment, _post_summary
from audit import log_audit
import bot_guard
import stats

_PER_PAGE_MAX = 100
_DEFAULT_PER_PAGE = 20
# 「永久封禁」在 BotBlock 里是 blocked_until = 9999-12-31（见 bot_guard.block_ip），
# 用一个远大于合理年份的阈值判定，避免依赖具体字面量。
_PERMANENT_YEAR = 9000


# ---------------------------------------------------------------- 闸门与通用


def _role(admin=False, super_only=False):
    """JSON 版权限闸门。放行返回 `(user, None)`，拦截返回 `(None, 响应)`。

    与后台装饰器的差异**只在响应形态**：判定条件保持一致
    （未登录 / 超管未改默认密码 / 角色不足），不漏任何一条。
    """
    from flask import session
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    if not user:
        return None, (jsonify({"error": "请先登录"}), 401)
    if user.is_super and user.must_change_password:
        return None, (jsonify({"error": "请先完成账号安全设置（修改默认密码）"}), 403)
    if super_only and not user.is_super:
        return None, (jsonify({"error": "仅超级管理员可执行该操作"}), 403)
    if admin and not user.is_admin_role:
        return None, (jsonify({"error": "需要管理员权限"}), 403)
    return user, None


def _limit(name, limit, window=60):
    """写接口统一限流。超限返回 429 响应，未超限返回 None。"""
    if rate_limit(client_key("api_mobile_" + name), limit=limit, window=window):
        return None
    return jsonify({"error": "操作过于频繁，请稍后再试"}), 429


def _body():
    """取 JSON 请求体（空体 / 非 JSON 一律归一成 dict，不抛 400）。"""
    return request.get_json(silent=True) or {}


def _flag(data, key):
    """勾选框 / 布尔字段的统一取值（委托 `admin._helpers.form_flag`，两处同一判据）。"""
    from admin._helpers import form_flag
    return form_flag(data, key)


def _tri(name):
    """筛选参数的三态：缺省 / 空串 → `None`（不筛），其余按 `form_flag` 判据取 bool。

    列表接口写 `?active=` 时「没带参数」和「带了 0」必须是两件事：前者不看状态，
    后者只看停用的。用 `None` 区分，别让 `bool(request.args.get(...))` 把 `"0"` 当真。
    """
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None
    return _flag({name: raw}, name)


def _need_flag(body, key):
    """请求体里的**必填**布尔：键缺失返回 `None`（调用方给 400），存在则按 `form_flag` 取值。

    与 `_flag` 的差别只在于「缺键」：`form_flag` 缺键返回 `False`，这对整单表单是对的
    （后台表单没勾就是没勾），但用在「设置单个状态」的接口上就等于
    「客户端漏传字段 → 静默改成停用」。这类接口宁可显式报错。
    """
    if not isinstance(body, dict) or key not in body:
        return None
    return _flag(body, key)


def _page_args(default=_DEFAULT_PER_PAGE):
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", default, type=int) or default
    return max(1, page), max(1, min(_PER_PAGE_MAX, per_page))


def _paged(query, page, per_page, serializer):
    """统一分页信封 `items / total / page / pages`（与 `/api/search` 同形）。"""
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [serializer(x) for x in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


def _comment_counts(posts):
    """一次 GROUP BY 取当前页所有文章的评论数，返回 {post_id: count}。"""
    ids = [p.id for p in posts]
    if not ids:
        return {}
    rows = (db.session.query(Comment.post_id, func.count(Comment.id))
            .filter(Comment.post_id.in_(ids))
            .group_by(Comment.post_id)
            .all())
    return dict(rows)


def _paged_posts(query, page, per_page):
    """文章列表分页：评论数批量回填，避免每行 `p.comments.count()` 的 N+1。"""
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    counts = _comment_counts(pagination.items)
    return jsonify({
        "items": [_post_admin(p, counts.get(p.id, 0)) for p in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


def _iso(dt):
    return fmt_bj(dt, "%Y-%m-%d %H:%M") if dt else ""


def _like(raw):
    """转义 LIKE 通配符（与 `admin/visit_logs.py::_like` 同语义：防筛选词被当通配符）。"""
    esc = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + esc + "%"


# ---------------------------------------------------------------- 序列化


def _post_admin(p, comment_count=None):
    """管理视角文章摘要：公开 `_post_summary` 之外补上「只有后台需要」的状态位。

    ⚠️ 不带 `content` —— 列表只需标题与状态，正文留给详情接口，
    避免一次列表拖回几百 KB 正文（手机网络下最明显）。

    `comment_count` 由列表批量传入（`_comment_counts`）；单篇详情不传时回退到
    逐条 count。
    """
    d = _post_summary(p)
    d.update({
        "id": p.id,
        "published": bool(p.published),
        "in_trash": bool(p.in_trash),
        "pin_requested": bool(p.pin_requested),
        "scheduled_at": _iso(p.scheduled_at),
        "updated_at": _iso(p.updated_at),
        "comment_count": p.comments.count() if comment_count is None else comment_count,
        "category_id": p.category_id,
        "series_id": p.series_id,
    })
    return d


def _comment_admin(c):
    d = _comment(c)
    d.update({
        "approved": bool(c.approved),
        "is_read": bool(c.is_read),
        "post_id": c.post_id,
        "post_title": c.post.title if c.post else "",
        "ip": c.ip or "",
    })
    return d


def _link_application_json(a):
    return {
        "id": a.id, "name": a.name, "url": a.url,
        "description": a.description or "", "email": a.email or "",
        "status": a.status or "pending", "reviewer": a.reviewer or "",
        "review_note": a.review_note or "",
        "created_at": _iso(a.created_at), "reviewed_at": _iso(a.reviewed_at),
    }


def _moment_json(m):
    return {
        "id": m.id,
        "author": m.author.username if m.author else "匿名",
        "content": m.content,
        "created_at": _iso(m.created_at),
        "likes": m.likes or 0,
        "comment_count": m.comments.count(),
    }


def _trash_json(rb):
    return {
        "id": rb.id, "post_id": rb.post_id, "title": rb.title or "",
        "slug": rb.slug or "", "summary": rb.summary or "",
        "deleted_by": rb.deleted_by or "", "restored": bool(rb.restored),
        "created_at": _iso(rb.created_at),
    }


def _visit_log_json(r, blocked_ips):
    return {
        "id": r.id,
        "time": fmt_bj(r.created_at, "%m-%d %H:%M") if r.created_at else "",
        "ip": r.ip or "",
        "region": r.region or "",
        "path": r.path or "",
        "referrer": r.referrer or "",
        "is_bot": bool(r.is_bot),
        "bot_name": r.bot_name or "",
        "bot_category": r.bot_category or "",
        "blocked": bool(r.ip) and r.ip in blocked_ips,
    }


def _blocked_ips_for(ips):
    """给定 IP 列表，返回其中「正处于封禁期」的集合（与后台访客日志页同判据）。"""
    uniq = sorted({i for i in ips if i})
    if not uniq:
        return set()
    now = utcnow()
    return {rec.ip for rec in BotBlock.query.filter(BotBlock.ip.in_(uniq),
                                                    BotBlock.active.is_(True)).all()
            if rec.blocked_until and rec.blocked_until > now}


# ---------------------------------------------------------------- 首屏概览


@api_bp.route("/mobile/overview")
def mobile_overview():
    """App 首屏：今天的数据 + 还欠多少事，一次请求拿齐。

    刻意只给「计数 + 最近 5 条评论」：明细走各自分页接口，首屏不拖全表。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    summary = stats.compute_summary()
    counts = {
        "pending_comments": Comment.query.filter_by(approved=False).count(),
        "unread_comments": Comment.query.filter_by(is_read=False).count(),
        "unread_notifications": Notification.query.filter_by(
            user_id=user.id, is_read=False).count(),
        "drafts": Post.query.filter(Post.in_trash.is_(False), Post.published.is_(False),
                                    Post.scheduled_at.is_(None)).count(),
        "scheduled": Post.query.filter(Post.in_trash.is_(False), Post.published.is_(False),
                                       Post.scheduled_at.isnot(None)).count(),
        "pending_links": LinkApplication.query.filter_by(status="pending").count(),
        "pin_requests": Post.query.filter_by(pin_requested=True).count(),
        "trash": RecycleBin.query.filter_by(restored=False).count(),
        # v4.4.0：留言未读数。后台导航角标早就有它（`inject_notification_counts` 的
        # `pending_guestbook`），App 侧此前只能自己再打一次列表接口才能知道有没有新留言，
        # 而首屏本来就要请求 overview —— 补在这里，两端同一个数据源。
        "unread_guestbook": Guestbook.query.filter_by(is_read=False).count(),
    }
    keys = ("today_visits", "bot_today", "online", "total_visits", "today_date")
    return jsonify({
        "ok": True,
        "user": {"id": user.id, "username": user.username,
                 "is_admin": user.is_admin_role, "is_super": user.is_super},
        "counts": counts,
        "today": {k: summary.get(k) for k in keys},
        "recent_comments": [_comment_admin(c) for c in
                            Comment.query.order_by(Comment.created_at.desc()).limit(5).all()],
    })


# ---------------------------------------------------------------- 文章


@api_bp.route("/mobile/posts")
def mobile_posts():
    """文章管理列表（与 `/admin/my-posts` 同筛选口径：关键词 / 状态 / 分类 / 系列 / 排序）。"""
    user, deny = _role()
    if deny:
        return deny
    page, per_page = _page_args(15)
    q = Post.query.filter(Post.in_trash.is_(False))
    if not user.is_admin_role:
        q = q.filter(Post.author_id == user.id)
    kw = (request.args.get("q") or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    status = (request.args.get("status") or "").strip()
    if status == "published":
        q = q.filter(Post.published.is_(True), Post.scheduled_at.is_(None))
    elif status == "draft":
        q = q.filter(Post.published.is_(False), Post.scheduled_at.is_(None))
    elif status == "scheduled":
        q = q.filter(Post.scheduled_at.isnot(None), Post.published.is_(False))
    elif status == "pinned":
        q = q.filter(Post.is_pinned.is_(True))
    cat_id = request.args.get("category_id", type=int)
    if cat_id:
        q = q.filter(Post.category_id == cat_id)
    ser_id = request.args.get("series_id", type=int)
    if ser_id:
        q = q.filter(Post.series_id == ser_id)
    sort = (request.args.get("sort") or "created").strip()
    order = (request.args.get("order") or "desc").strip()
    col_map = {"updated": Post.updated_at, "views": Post.views, "words": Post.word_count,
               "title": Post.title, "created": Post.created_at}
    col = col_map.get(sort, Post.created_at)
    direction = col.asc() if order == "asc" else col.desc()
    # title 排序不再叠加置顶（否则置顶永远挤在最前，A→Z 就失效）——与后台同处理
    q = q.order_by(col) if sort == "title" else q.order_by(Post.is_pinned.desc(), direction)
    return _paged_posts(q, page, per_page)


@api_bp.route("/mobile/post/<int:post_id>")
def mobile_post_detail(post_id):
    """文章详情（含 Markdown 原文，供编辑器载入）。"""
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能查看自己发表的文章"}), 403
    d = _post_admin(post)
    d.update({
        "content": post.content or "",
        "reward_qr": post.reward_qr or "",
        # `_post_summary` 里的 `seo_description` 是「独立描述**或**回退到摘要」的展示值，
        # 无法反推库里的原值。而 `update_post_core` 的表单语义是「缺省即清空」，客户端
        # 必须回传完整表单 —— 于是拿展示值回传会把「本来没填」写成「等于摘要」，
        # 以后改摘要就带不动 SEO 描述了。所以详情额外给一份**未回退**的原值。
        "seo_description_raw": post.seo_description or "",
        "tag_names": ", ".join(t.name for t in post.tags),
        "url": "/post/" + (post.slug or ""),
        "previewable": bool(not post.published and not post.is_private and not post.in_trash),
    })
    return jsonify(d)


@api_bp.route("/mobile/post", methods=["POST"])
def mobile_post_create():
    """新建文章（草稿 / 直接发布 / 定时）。发文动作走后台唯一入口 `create_post_core`。

    请求体：`title` 必填；可选 `content / summary / cover / category_id /
    new_category_name / tags / series_id / new_series_name / seo_description /
    seo_keywords / published / scheduled_at / is_pinned / is_private / reward_enabled /
    reward_qr / notify_subscribers / lang / translation_group`。
    `scheduled_at` 用北京时间 `YYYY-MM-DDTHH:MM`（与后台 datetime-local 输入同格式）。
    """
    user, deny = _role()
    if deny:
        return deny
    blocked = _limit("post_create", 20)
    if blocked:
        return blocked
    data = _body()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "标题不能为空"}), 400
    from admin._helpers import create_post_core
    from admin.taxonomy import _ensure_category_by_name, _ensure_series_by_name
    new_cat = (data.get("new_category_name") or "").strip()
    category_id = _ensure_category_by_name(new_cat) if new_cat else (data.get("category_id") or None)
    new_ser = (data.get("new_series_name") or "").strip()
    series_id = _ensure_series_by_name(new_ser) if new_ser else (data.get("series_id") or None)
    # 提权字段按后台同规则收紧：客户端传什么都不越权
    is_pinned = _flag(data, "is_pinned") and user.is_admin_role
    is_private = _flag(data, "is_private") and user.is_super
    reward_enabled = _flag(data, "reward_enabled") and user.is_super
    reward_qr = (data.get("reward_qr") or "").strip() if reward_enabled else ""
    scheduled_at = _parse_scheduled(data.get("scheduled_at"))
    post = create_post_core(
        title=title, content=data.get("content") or "",
        summary=(data.get("summary") or "").strip(),
        cover=(data.get("cover") or "").strip(),
        category_id=int(category_id) if category_id else None,
        tags=data.get("tags") or "",
        series_id=int(series_id) if series_id else None,
        seo_description=(data.get("seo_description") or "").strip(),
        seo_keywords=(data.get("seo_keywords") or "").strip(),
        published=_flag(data, "published"),
        scheduled_at=scheduled_at,
        author_id=user.id, is_pinned=is_pinned, is_private=is_private,
        reward_enabled=reward_enabled, reward_qr=reward_qr,
        notify_subscribers=_flag(data, "notify_subscribers") and user.is_admin_role,
        lang=(data.get("lang") or "zh").strip() or "zh",
        translation_group=(data.get("translation_group") or "").strip(),
    )
    log_audit("mobile_create", "post", post.id, f"移动端发文：{post.title}", user=user)
    return jsonify({"ok": True, "id": post.id, "slug": post.slug,
                    "published": bool(post.published),
                    "scheduled_at": _iso(post.scheduled_at)}), 201


@api_bp.route("/mobile/post/<int:post_id>", methods=["PUT", "POST"])
def mobile_post_update(post_id):
    """修改文章（含发布/定时状态）。字段与权限分层全在 `update_post_core` 里。

    未提供的字段沿用 `update_post_core` 的表单语义：缺省即「清空」，所以客户端应
    **回传完整表单**（先 `GET /api/mobile/post/<id>` 取全量再提交），别发增量。
    """
    user, deny = _role()
    if deny:
        return deny
    blocked = _limit("post_update", 30)
    if blocked:
        return blocked
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post, update_post_core
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能编辑自己发表的文章"}), 403
    data = dict(_body())
    data.setdefault("title", post.title)
    err = update_post_core(post, data, user)
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_update", "post", post.id, f"移动端改文：{post.title}", user=user)
    return jsonify({"ok": True, "id": post.id, "slug": post.slug,
                    "published": bool(post.published),
                    "scheduled_at": _iso(post.scheduled_at)})


def _parse_scheduled(raw):
    """北京时间 `YYYY-MM-DDTHH:MM` → UTC naive（与后台编辑页同一换算，直接复用）。"""
    from admin._helpers import _parse_scheduled as impl
    return impl(raw)


@api_bp.route("/mobile/post/<int:post_id>/publish", methods=["POST"])
def mobile_post_publish(post_id):
    """发布（草稿/定时 → 已发布）。副作用与后台「立即发布」一致：索引、推送、群发。"""
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import publish_post_core
    if not publish_post_core(post, user):
        return jsonify({"error": "只能操作自己发表的文章"}), 403
    log_audit("mobile_publish", "post", post.id, f"移动端发布：{post.title}", user=user)
    return jsonify({"ok": True, "published": True, "id": post.id})


@api_bp.route("/mobile/post/<int:post_id>/unpublish", methods=["POST"])
def mobile_post_unpublish(post_id):
    """撤回为草稿（同时清空定时，否则到点会被后台线程再次翻回已发布）。"""
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能操作自己发表的文章"}), 403
    if not post.published and post.scheduled_at is None:
        return jsonify({"ok": True, "published": False, "message": "已是草稿"})
    post.published = False
    post.scheduled_at = None
    db.session.commit()
    import fts
    fts.sync_post_quiet(post)   # 转草稿必须同步索引，否则 /api/search 仍能命中已撤回文章
    log_audit("mobile_unpublish", "post", post.id,
              f"移动端转草稿：{post.title}", user=user)
    return jsonify({"ok": True, "published": False, "id": post.id})


@api_bp.route("/mobile/post/<int:post_id>/pin", methods=["POST"])
def mobile_post_pin(post_id):
    """置顶 / 取消置顶（仅超管，与后台 `approve_pin` / `unpin` 同权限）。"""
    user, deny = _role(super_only=True)
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    want = _need_flag(_body(), "pinned")
    if want is None:
        return jsonify({"error": "请带上 pinned（true/false）"}), 400
    post.is_pinned = want
    if want:
        post.pin_requested = False
    db.session.commit()
    log_audit("mobile_pin", "post", post.id,
              ("移动端置顶：" if want else "移动端取消置顶：") + (post.title or ""), user=user)
    return jsonify({"ok": True, "pinned": want, "id": post.id})


@api_bp.route("/mobile/post/<int:post_id>/trash", methods=["POST"])
def mobile_post_trash(post_id):
    """移入回收站（软删除，可在 `/api/mobile/trash` 还原）。"""
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import trash_post_core
    if not trash_post_core(post, user):
        return jsonify({"error": "只能删除自己发表的文章"}), 403
    log_audit("mobile_trash", "post", post.id,
              f"移动端移入回收站：{post.title}", user=user)
    return jsonify({"ok": True, "in_trash": True, "id": post.id})


@api_bp.route("/mobile/taxonomy")
def mobile_taxonomy():
    """编辑器需要的分类 / 系列 / 标签候选（后台编辑页同数据源）。"""
    user, deny = _role()
    if deny:
        return deny
    return jsonify({
        "categories": [{"id": c.id, "name": c.name, "slug": c.slug}
                       for c in Category.query.order_by(Category.id).all()],
        "series": [{"id": s.id, "name": s.name, "slug": s.slug}
                   for s in Series.query.order_by(Series.sort, Series.created_at.desc()).all()],
        "tags": [{"id": t.id, "name": t.name, "slug": t.slug}
                 for t in Tag.query.order_by(Tag.name).limit(300).all()],
    })


# ---------------------------------------------------------------- 回收站


@api_bp.route("/mobile/trash")
def mobile_trash():
    """回收站列表（未还原的软删除文章）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    q = (RecycleBin.query.filter_by(restored=False)
         .order_by(RecycleBin.created_at.desc()))
    return _paged(q, page, per_page, _trash_json)


@api_bp.route("/mobile/trash/<int:rid>/restore", methods=["POST"])
def mobile_trash_restore(rid):
    """从回收站还原：原文章还在就清标记，否则按快照重建为草稿。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    rb = db.session.get(RecycleBin, rid)
    if not rb:
        return jsonify({"error": "回收站记录不存在"}), 404
    from admin.post_trash import restore_recycle_core
    msg, post_id = restore_recycle_core(rb, user=user)
    if not rb.restored:
        rb.restored = True
        db.session.commit()
    log_audit("mobile_restore", "post", post_id or rb.post_id,
              f"移动端还原：{rb.title}", user=user)
    return jsonify({"ok": True, "restored": True, "message": msg, "post_id": post_id})


@api_bp.route("/mobile/trash/<int:rid>/purge", methods=["POST"])
def mobile_trash_purge(rid):
    """彻底删除（仅管理员，与后台回收站同实现）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    rb = db.session.get(RecycleBin, rid)
    if not rb:
        return jsonify({"error": "回收站记录不存在"}), 404
    from admin.post_trash import purge_recycle_core
    msg = purge_recycle_core(rb, user=user)
    return jsonify({"ok": True, "message": msg})


# ---------------------------------------------------------------- 评论审核


@api_bp.route("/mobile/comments")
def mobile_comments():
    """评论列表：`?status=pending|approved`、`?unread=1` 只看未读。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    status = (request.args.get("status") or "").strip()
    q = Comment.query
    if status == "pending":
        q = q.filter_by(approved=False)
    elif status == "approved":
        q = q.filter_by(approved=True)
    if _flag(request.args, "unread"):
        q = q.filter(Comment.is_read.is_(False))
    return _paged(q.order_by(Comment.created_at.desc()), page, per_page, _comment_admin)


@api_bp.route("/mobile/comment/<int:cid>/<action>", methods=["POST"])
def mobile_comment_action(cid, action):
    """单条评论动作：`approve`（通过并标已读）/ `reject`（驳回即删除）/ `read`。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("comment_action", 60)
    if blocked:
        return blocked
    if action not in ("approve", "reject", "read"):
        return jsonify({"error": "未知操作"}), 400
    c = db.session.get(Comment, cid)
    if not c:
        return jsonify({"error": "评论不存在"}), 404
    post_title = c.post.title if c.post else ""
    if action == "approve":
        c.approved = True
        c.is_read = True
        db.session.commit()
        log_audit("mobile_approve", "comment", c.id,
                  f"移动端通过评论（{post_title}）", user=user)
        return jsonify({"ok": True, "id": c.id, "approved": True})
    if action == "read":
        c.is_read = True
        db.session.commit()
        return jsonify({"ok": True, "id": c.id, "is_read": True})
    db.session.delete(c)
    db.session.commit()
    log_audit("mobile_reject", "comment", c.id,
              f"移动端驳回并删除评论（{post_title}）", user=user)
    return jsonify({"ok": True, "deleted": True})


@api_bp.route("/mobile/comments/read-all", methods=["POST"])
def mobile_comments_read_all():
    """全部评论标记已读（对应后台「全部已读」按钮）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    n = Comment.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    log_audit("mobile_read_all", "comment", None, f"移动端全部已读（{n} 条）", user=user)
    return jsonify({"ok": True, "updated": n})


@api_bp.route("/mobile/comments/batch", methods=["POST"])
def mobile_comments_batch():
    """批量审核：`{"ids":[1,2],"action":"approve|delete"}`，与后台批量同口径（上限 500 条）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("comment_batch", 30)
    if blocked:
        return blocked
    data = _body()
    action = (data.get("action") or "").strip()
    if action not in ("approve", "delete"):
        return jsonify({"error": "未知操作"}), 400
    ids = [int(x) for x in (data.get("ids") or []) if str(x).isdigit()]
    if not ids:
        return jsonify({"error": "请先选择要操作的评论"}), 400
    changed = 0
    for cid in ids[:500]:
        c = db.session.get(Comment, cid)
        if not c:
            continue
        if action == "approve":
            if not c.approved:
                changed += 1
            c.approved = True
            c.is_read = True
        else:
            db.session.delete(c)
            changed += 1
    db.session.commit()
    log_audit("mobile_batch", "comment", None,
              f"移动端批量{action} {changed} 条评论", user=user)
    return jsonify({"ok": True, "changed": changed, "action": action})


# ---------------------------------------------------------------- 访客日志与封禁


@api_bp.route("/mobile/visit-logs")
def mobile_visit_logs():
    """访客日志（`/admin/visit-logs` 的 JSON 版）：区间 / 类型 / IP / 属地 / 路径 组合筛选。

    区间 key 直接复用 `stats.RANGE_PRESETS`（今天/昨天/近 7 天…九档），并随响应回给
    客户端，App 不必自己算日期。

    ⚠️ **v4.3.1 起收成超管专属**（原与后台页面同级 = 管理员）。理由见 SECURITY_AUDIT R120.5：
    这个端点输出**访客 IP 原文**，权限本身没比后台页面宽，但出口从「一个人一页一页看的页面」
    变成「一个可以被脚本翻页批量抓的 JSON 接口」—— 风险不是「谁能看」，而是「能多快地全拿走」。
    拉黑/解封本来就是超管专属，日志页与它配套，收成同级也更一致：
    **能决定封谁的人，才应该能拿到那份 IP 清单**。
    """
    user, deny = _role(super_only=True)
    if deny:
        return deny
    page, per_page = _page_args()
    rng = (request.args.get("range") or "").strip() or stats.DEFAULT_RANGE
    typ = (request.args.get("type") or "").strip()
    ip_q = (request.args.get("ip") or "").strip()[:64]
    region_q = (request.args.get("region") or "").strip()[:64]
    path_q = (request.args.get("path") or "").strip()[:120]

    eff_key, start, end, label = stats.resolve_range(rng)
    q = VisitLog.query.filter(VisitLog.date >= start.isoformat(),
                              VisitLog.date <= end.isoformat())
    if typ == "human":
        q = q.filter(VisitLog.is_bot.is_(False))
    elif typ == "bot":
        q = q.filter(VisitLog.is_bot.is_(True))
    if ip_q:
        q = q.filter(VisitLog.ip.ilike(_like(ip_q), escape="\\"))
    if region_q:
        q = q.filter(VisitLog.region.ilike(_like(region_q), escape="\\"))
    if path_q:
        q = q.filter(VisitLog.path.ilike(_like(path_q), escape="\\"))

    pagination = q.order_by(VisitLog.id.desc()).paginate(page=page, per_page=per_page,
                                                         error_out=False)
    blocked_ips = _blocked_ips_for([r.ip for r in pagination.items if r.ip])
    return jsonify({
        "items": [_visit_log_json(r, blocked_ips) for r in pagination.items],
        "total": pagination.total, "page": pagination.page, "pages": pagination.pages,
        "range": {"key": eff_key, "label": label,
                  "start": start.isoformat(), "end": end.isoformat()},
        "ranges": [{"key": k, "label": v} for k, v in stats.RANGE_PRESETS],
    })


@api_bp.route("/mobile/blocked")
def mobile_blocked():
    """正在生效的 IP 封禁列表（App 侧「谁被我拉黑了 / 解封」入口）。

    v4.3.1：与 `/mobile/visit-logs` 同步收成**超管专属** —— 内容同样是 IP 原文，
    且解封本就是超管动作，列表与操作权限必须同级。
    """
    user, deny = _role(super_only=True)
    if deny:
        return deny
    now = utcnow()
    rows = (BotBlock.query.filter(BotBlock.active.is_(True), BotBlock.blocked_until > now)
            .order_by(BotBlock.blocked_until.desc()).limit(300).all())
    return jsonify({
        "items": [{
            "ip": r.ip, "reason": r.reason or "", "bot_name": r.bot_name or "",
            "hit_count": r.hit_count or 0, "blocked_until": _iso(r.blocked_until),
            "permanent": bool(r.blocked_until and r.blocked_until.year >= _PERMANENT_YEAR),
        } for r in rows],
        "total": len(rows),
    })


@api_bp.route("/mobile/ip/block", methods=["POST"])
def mobile_ip_block():
    """拉黑 IP（默认永久）。仅超管；写审计；与后台访客日志页同一个 `bot_guard.block_ip`。"""
    user, deny = _role(super_only=True)
    if deny:
        return deny
    blocked = _limit("ip_block", 20)
    if blocked:
        return blocked
    ip = (_body().get("ip") or "").strip()
    ok, msg = bot_guard.block_ip(ip)
    if not ok:
        return jsonify({"error": msg}), 400
    log_audit("mobile_block_ip", "visit_log", None, msg, user=user)
    return jsonify({"ok": True, "ip": ip, "message": msg})


@api_bp.route("/mobile/ip/unblock", methods=["POST"])
def mobile_ip_unblock():
    """解封 IP。仅超管。"""
    user, deny = _role(super_only=True)
    if deny:
        return deny
    ip = (_body().get("ip") or "").strip()
    if not bot_guard.unblock_ip(ip):
        return jsonify({"error": "未找到该 IP 的封禁记录"}), 404
    log_audit("mobile_unblock_ip", "visit_log", None, "解封 " + ip, user=user)
    return jsonify({"ok": True, "ip": ip})


# ---------------------------------------------------------------- 统计


@api_bp.route("/mobile/stats")
def mobile_stats():
    """统计数据（管理员）。`?detail=1` 额外带 30 天趋势（`days` 可指定 1~90）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("stats", 30)
    if blocked:
        return blocked
    try:
        summary = stats.compute_summary()
    except Exception:  # noqa: BLE001  (与 /api/stats/summary 同口径：聚合细节不外泄，只进日志)
        current_app.logger.exception("mobile stats summary 失败")
        return jsonify({"error": "internal_error"}), 500
    out = {"ok": True, "summary": summary}
    if _flag(request.args, "detail"):
        days = request.args.get("days", 30, type=int) or 30
        out["trend"] = stats.compute_trend(max(1, min(90, days)))
    return jsonify(out)


# ---------------------------------------------------------------- 微动态


@api_bp.route("/mobile/moments")
def mobile_moments():
    """微动态列表（含评论数，便于手机上先看有没有人回复）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    q = Moment.query
    kw = (request.args.get("q") or "").strip()
    if kw:
        q = q.filter(Moment.content.ilike(f"%{kw}%"))
    return _paged(q.order_by(Moment.created_at.desc()), page, per_page, _moment_json)


@api_bp.route("/mobile/moment", methods=["POST"])
def mobile_moment_create():
    """发微动态（登录即可，与前台 `/api/moment` 同一权限位、同一限流强度）。"""
    user, deny = _role()
    if deny:
        return deny
    blocked = _limit("moment_create", 5)
    if blocked:
        return blocked
    content = (_body().get("content") or "").strip()
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    m = Moment(content=content, author_id=user.id)
    db.session.add(m)
    db.session.commit()
    log_audit("mobile_moment", "moment", m.id, "移动端发微动态", user=user)
    return jsonify({"ok": True, "id": m.id}), 201


@api_bp.route("/mobile/moment/<int:mid>/delete", methods=["POST"])
def mobile_moment_delete(mid):
    """删除微动态（级联删其评论，与后台 `delete_moment` 同行为）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    m = db.session.get(Moment, mid)
    if not m:
        return jsonify({"error": "动态不存在"}), 404
    preview = (m.content or "")[:40]
    db.session.delete(m)
    db.session.commit()
    log_audit("mobile_del_moment", "moment", mid, f"移动端删除微动态：{preview}", user=user)
    return jsonify({"ok": True, "deleted": True})


# ---------------------------------------------------------------- 友链申请


@api_bp.route("/mobile/link-applications")
def mobile_link_applications():
    """友链申请列表（默认只看待审）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    status = request.args.get("status", "pending")
    q = LinkApplication.query
    if status:
        q = q.filter_by(status=status)
    return jsonify({
        "items": [_link_application_json(a) for a in
                  q.order_by(LinkApplication.created_at.desc()).limit(200).all()],
        "status": status,
        "pending_count": LinkApplication.query.filter_by(status="pending").count(),
    })


@api_bp.route("/mobile/link-application/<int:aid>/approve", methods=["POST"])
def mobile_link_approve(aid):
    """通过友链申请：写入 FriendLink（同 URL 已存在则跳过），与后台同逻辑。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    row = db.session.get(LinkApplication, aid)
    if not row:
        return jsonify({"error": "申请不存在"}), 404
    if row.status == "approved":
        return jsonify({"ok": True, "message": "该申请已通过"})
    if not FriendLink.query.filter_by(url=row.url).first():
        db.session.add(FriendLink(name=row.name, url=row.url,
                                  description=row.description or "", sort=99))
    row.status = "approved"
    row.reviewer = user.username
    row.reviewed_at = utcnow()
    db.session.commit()
    log_audit("approve", "link_application", aid,
              f"移动端通过友链申请：{row.name}", user=user)
    return jsonify({"ok": True, "status": "approved"})


@api_bp.route("/mobile/link-application/<int:aid>/reject", methods=["POST"])
def mobile_link_reject(aid):
    """拒绝友链申请（可带 `note` 备注）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    row = db.session.get(LinkApplication, aid)
    if not row:
        return jsonify({"error": "申请不存在"}), 404
    row.status = "rejected"
    row.reviewer = user.username
    row.reviewed_at = utcnow()
    note = (_body().get("note") or "").strip()
    if note:
        row.review_note = note
    db.session.commit()
    log_audit("reject", "link_application", aid,
              f"移动端拒绝友链申请：{row.name}", user=user)
    return jsonify({"ok": True, "status": "rejected"})


# ---------------------------------------------------------------- 图片上传


@api_bp.route("/mobile/upload", methods=["POST"])
def mobile_upload():
    """上传图片（封面 / 正文插图），返回可访问 URL。

    multipart 字段名固定 `file`；校验链与 `/admin/upload` 完全一致（后缀白名单 +
    文件头 16 字节魔数），因为「伪装成 .png 的 HTML/脚本」在手机相册里同样能出现。
    限流比后台更紧（手机连点误触）。
    """
    user, deny = _role()
    if deny:
        return deny
    blocked = _limit("upload", 10)
    if blocked:
        return blocked
    import os
    import time
    from admin._helpers import _detect_image_magic, allowed_file
    from werkzeug.utils import secure_filename
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"error": "没有选择文件"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": "只支持 png/jpg/jpeg/gif/webp 图片"}), 400
    header = f.stream.read(16)
    f.stream.seek(0)
    if not _detect_image_magic(header, f.filename.rsplit(".", 1)[1].lower()):
        return jsonify({"error": "文件内容与图片格式不符，已拒绝（仅允许真实图片）"}), 400
    filename = f"{time.time_ns()}-{secure_filename(f.filename)}"
    save_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    f.save(save_path)
    # 大图转 WebP 省流量（Pillow 缺失时保持原格式）——与后台同一函数
    with contextlib.suppress(Exception):
        from app import maybe_convert_webp
        converted = maybe_convert_webp(save_path)
        if converted != save_path:
            filename = os.path.basename(converted)
    return jsonify({"ok": True, "name": filename,
                    "url": url_for("static", filename=f"uploads/{filename}")}), 201


# ---------------------------------------------------------------- 公告 / 留言 / 订阅（v4.4.0）


def _announcement_json(a):
    """公告行：`content` 是**库里的 Markdown 原文**，不是公开 `/api/announcements` 的渲染 HTML。

    两套表示不能混：公开接口给前台横幅用（已清洗过的 HTML），这里给编辑器载入用。
    `levels` 每条都带一份（就 3 个短字符串，列表最多 100 条），这样客户端只要拉过一次
    列表就能渲染档位选择器，不必再猜服务端支持哪些 level。
    """
    from admin._helpers import ANNOUNCEMENT_LEVELS
    return {
        "id": a.id, "content": a.content or "", "level": a.level or "info",
        "levels": list(ANNOUNCEMENT_LEVELS), "active": bool(a.active),
        "dismissible": bool(a.dismissible), "created_at": _iso(a.created_at),
        "preview": (a.content or "")[:60],
    }


@api_bp.route("/mobile/announcements")
def mobile_announcements():
    """公告列表（管理员）：`active=1/0` 只看启用/停用，按创建时间倒序分页。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    q = Announcement.query.order_by(Announcement.created_at.desc(), Announcement.id.desc())
    tri = _tri("active")
    if tri is not None:
        q = q.filter(Announcement.active.is_(tri))
    return _paged(q, page, per_page, _announcement_json)


@api_bp.route("/mobile/announcement/<int:aid>")
def mobile_announcement_detail(aid):
    """公告详情（编辑器载入用）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    ann = db.session.get(Announcement, aid)
    if ann is None:
        return jsonify({"error": "公告不存在"}), 404
    return jsonify(_announcement_json(ann))


@api_bp.route("/mobile/announcement", methods=["POST"])
def mobile_announcement_create():
    """新建公告（管理员），走 `create_announcement_core`。

    请求体：`content` 必填；`level` ∈ info/warning/success（其它值归一为 info，与后台同）；
    `active` / `dismissible` 按 `form_flag` 判据取值（JSON 用 `true/false`）。
    公告是**全站顶部横幅**，写错了前台每个人都能看到，所以 App 侧应该先给预览再提交。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("announcement_write", 20)
    if blocked:
        return blocked
    from admin._helpers import create_announcement_core
    ann, err = create_announcement_core(_body())
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_ann_create", "announcement", ann.id,
              f"移动端新增公告：{(ann.content or '')[:60]}", user=user)
    return jsonify({"ok": True, "id": ann.id, "item": _announcement_json(ann)}), 201


@api_bp.route("/mobile/announcement/<int:aid>", methods=["POST", "PUT"])
def mobile_announcement_update(aid):
    """整单修改公告（管理员），走 `update_announcement_core`。

    ⚠️ **要回传完整表单**（`content/level/active/dismissible`）：核心函数的语义与后台表单
    一致 —— 没带的布尔字段等同「没勾选」，会被写成 False。先 GET 详情再改再整体回传。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("announcement_write", 20)
    if blocked:
        return blocked
    ann = db.session.get(Announcement, aid)
    if ann is None:
        return jsonify({"error": "公告不存在"}), 404
    from admin._helpers import update_announcement_core
    err = update_announcement_core(ann, _body())
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_ann_update", "announcement", aid,
              f"移动端修改公告：{(ann.content or '')[:60]}", user=user)
    return jsonify({"ok": True, "item": _announcement_json(ann)})


@api_bp.route("/mobile/announcement/<int:aid>/active", methods=["POST"])
def mobile_announcement_active(aid):
    """设置启用状态：`{"active": true|false}` —— **显式目标值，不是反转**。

    后台的 `/announcement/<id>/toggle` 是翻转语义，手机上不能照搬：弱网下客户端重发
    同一个请求，翻转会来回横跳（用户以为停用了，实际又启用），而显式值重发多少次
    结果都一样。写类接口一律取这个形态（同 `/mobile/post/<id>/pin`）。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("announcement_write", 20)
    if blocked:
        return blocked
    ann = db.session.get(Announcement, aid)
    if ann is None:
        return jsonify({"error": "公告不存在"}), 404
    want = _need_flag(_body(), "active")
    if want is None:
        return jsonify({"error": "请带上 active（true/false）"}), 400
    ann.active = want
    db.session.commit()
    log_audit("mobile_ann_active", "announcement", aid,
              f"移动端公告{'启用' if want else '停用'}", user=user)
    return jsonify({"ok": True, "item": _announcement_json(ann)})


@api_bp.route("/mobile/announcement/<int:aid>/delete", methods=["POST"])
def mobile_announcement_delete(aid):
    """删除公告（管理员）。⚠️ 硬删除，公告没有回收站。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("announcement_write", 20)
    if blocked:
        return blocked
    ann = db.session.get(Announcement, aid)
    if ann is None:
        return jsonify({"error": "公告不存在"}), 404
    preview = (ann.content or "")[:60]
    db.session.delete(ann)
    db.session.commit()
    log_audit("mobile_ann_delete", "announcement", aid,
              f"移动端删除公告：{preview}", user=user)
    return jsonify({"ok": True})


def _guestbook_json(g, with_ip=False):
    d = {
        "id": g.id, "author": g.author or "", "content": g.content or "",
        "created_at": _iso(g.created_at), "likes": g.likes or 0,
        "is_read": bool(g.is_read), "region": g.region or "", "device": g.device or "",
    }
    if with_ip:
        d["ip"] = g.ip or ""
    return d


@api_bp.route("/mobile/guestbook")
def mobile_guestbook():
    """留言墙（管理员）：`q` 搜昵称与内容、`unread=1` 只看未读，时间倒序分页。

    权限分层沿用 v4.3.1 对访客日志的口径（SECURITY_AUDIT R120.5）：**IP 原文只给超管**，
    管理员拿到 `region` / `device` 足够巡检。后台页面本来连 IP 都不显示，这里给超管
    是「手机上处理骚扰留言时不用再回电脑上查」，不是放宽普通管理员的可见范围。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    q = Guestbook.query.order_by(Guestbook.created_at.desc(), Guestbook.id.desc())
    unread = _tri("unread")
    if unread is not None:
        q = q.filter(Guestbook.is_read.is_(not unread))
    kw = (request.args.get("q") or "").strip()
    if kw:
        like = _like(kw)
        q = q.filter(db.or_(Guestbook.author.ilike(like), Guestbook.content.ilike(like)))
    serializer = lambda g: _guestbook_json(g, user.is_super)  # noqa: E731  (角色决定字段可见性)
    return _paged(q, page, per_page, serializer)


@api_bp.route("/mobile/guestbook/<int:gid>/read", methods=["POST"])
def mobile_guestbook_read(gid):
    """标为已读（管理员）。幂等：重复调用结果不变，弱网重试安全。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    g = db.session.get(Guestbook, gid)
    if g is None:
        return jsonify({"error": "留言不存在"}), 404
    g.is_read = True
    db.session.commit()
    log_audit("mobile_guest_read", "guestbook", gid, "移动端留言标已读", user=user)
    return jsonify({"ok": True, "item": _guestbook_json(g, user.is_super)})


@api_bp.route("/mobile/guestbook/read-all", methods=["POST"])
def mobile_guestbook_read_all():
    """全部留言标已读（管理员）。返回实际改动条数，客户端据此提示。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("guestbook_batch", 10)
    if blocked:
        return blocked
    n = Guestbook.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    log_audit("mobile_guest_read_all", "guestbook", None,
              f"移动端留言全部已读（{n} 条）", user=user)
    return jsonify({"ok": True, "updated": n})


@api_bp.route("/mobile/guestbook/<int:gid>/delete", methods=["POST"])
def mobile_guestbook_delete(gid):
    """删除留言（管理员）。

    ⚠️ **硬删除、不进回收站**：`RecycleBin` 只登记文章，留言删了就没有下一步。
    App 侧必须二次确认，文案要写明「删除后无法恢复」。审计只记内容前 60 字，
    不记 IP / 设备 —— 审计表是长期留存的，没必要为一条被删的留言再留一份定位信息。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("guestbook_delete", 30)
    if blocked:
        return blocked
    g = db.session.get(Guestbook, gid)
    if g is None:
        return jsonify({"error": "留言不存在"}), 404
    preview = (g.content or "")[:60]
    db.session.delete(g)
    db.session.commit()
    log_audit("mobile_guest_delete", "guestbook", gid, f"移动端删除留言：{preview}", user=user)
    return jsonify({"ok": True})


def _mask_email(raw):
    """邮箱遮敏：保留用户名前 2 位与整个域名，中间固定 `***`。

    默认遮的两个理由：`Subscriber.email` 是可直接群发的 PII；而 App 会把列表留在本地
    缓存、也会在非私密场合打开。超管拿全量是为了联系/导出（`reveal=True`）。
    ⚠️ `Subscriber.unsub_token` **任何角色都不返回**：`/unsubscribe/<token>` 免登录校验，
    泄露它等于任何人都能替博主的订阅者退订。
    """
    e = (raw or "").strip()
    if "@" not in e:
        return (e[:2] + "***") if e else ""
    local, _, domain = e.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}"


def _subscriber_json(s, reveal=False):
    return {
        "id": s.id,
        "email": (s.email or "") if reveal else _mask_email(s.email),
        "email_masked": not reveal,
        "active": bool(s.active),
        "created_at": _iso(s.created_at),
    }


@api_bp.route("/mobile/subscribers")
def mobile_subscribers():
    """订阅者（管理员）：`q` 搜邮箱、`active=1/0` 筛生效/退订，时间倒序分页。

    邮箱对管理员**遮敏**、对超管全量（见 `_mask_email`）。总数 `total` 是精确值 ——
    统计口径不受遮敏影响，客户端不用自己数。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    page, per_page = _page_args()
    q = Subscriber.query.order_by(Subscriber.created_at.desc(), Subscriber.id.desc())
    tri = _tri("active")
    if tri is not None:
        q = q.filter(Subscriber.active.is_(tri))
    kw = (request.args.get("q") or "").strip()
    if kw:
        q = q.filter(Subscriber.email.ilike(_like(kw)))
    reveal = user.is_super
    serializer = lambda s: _subscriber_json(s, reveal)  # noqa: E731  (角色决定邮箱形态)
    return _paged(q, page, per_page, serializer)


@api_bp.route("/mobile/subscriber/<int:sid>/active", methods=["POST"])
def mobile_subscriber_active(sid):
    """设置订阅状态：`{"active": true|false}`（管理员），显式目标值、幂等。

    `active=False` 就**不再收到发文邮件**（`mail_notify` 只取 `active=True` 的订阅者），
    但记录留着 —— 比删除可逆得多，处理投诉时应该先用它而不是删人。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("subscriber_write", 20)
    if blocked:
        return blocked
    sub = db.session.get(Subscriber, sid)
    if sub is None:
        return jsonify({"error": "订阅者不存在"}), 404
    want = _need_flag(_body(), "active")
    if want is None:
        return jsonify({"error": "请带上 active（true/false）"}), 400
    sub.active = want
    db.session.commit()
    log_audit("mobile_sub_active", "subscriber", sid,
              f"移动端订阅者{'恢复接收' if want else '停止发送'}", user=user)
    return jsonify({"ok": True, "item": _subscriber_json(sub, user.is_super)})


@api_bp.route("/mobile/subscriber/<int:sid>/delete", methods=["POST"])
def mobile_subscriber_delete(sid):
    """删除订阅者（管理员）。⚠️ 硬删除，且**下次同一邮箱再订阅会拿到新的 unsub_token**。

    审计 `detail` 不写邮箱（PII 不进长期留存的审计表），只记 id；真要追溯回后台页面看。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("subscriber_write", 20)
    if blocked:
        return blocked
    sub = db.session.get(Subscriber, sid)
    if sub is None:
        return jsonify({"error": "订阅者不存在"}), 404
    db.session.delete(sub)
    db.session.commit()
    log_audit("mobile_sub_delete", "subscriber", sid, f"移动端删除订阅者 #{sid}", user=user)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 分类 / 标签 / 系列（v4.4.0）


def _category_json(c):
    return {
        "id": c.id, "name": c.name, "slug": c.slug,
        "post_count": c.posts.count(), "url": "/category/" + (c.slug or ""),
    }


def _tag_json(t, used=None):
    """标签行。`used` 由调用方给（`tag_usage_counts()` 一次查完），没给才退回单独数一次。"""
    if used is None:
        from models import PostTag
        used = PostTag.query.filter_by(tag_id=t.id).count()
    return {"id": t.id, "name": t.name, "slug": t.slug,
            "post_count": used, "url": "/tag/" + (t.slug or "")}


def _series_json(s):
    return {
        "id": s.id, "name": s.name, "slug": s.slug, "description": s.description or "",
        "cover": s.cover or "", "sort": s.sort or 0,
        "post_count": Post.query.filter_by(series_id=s.id).count(),
        "created_at": _iso(s.created_at), "url": "/series/" + (s.slug or ""),
    }


@api_bp.route("/mobile/categories")
def mobile_categories():
    """分类清单（管理员）：每行带 `post_count`，删除前就知道会影响几篇。

    与只读的 `/mobile/taxonomy`（编辑器下拉数据源）不同，这里是**治理视角**：
    多给了文章数与访问地址，少不起「这个分类还有没有文章用」。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    rows = Category.query.order_by(Category.name).all()
    return jsonify({"items": [_category_json(c) for c in rows], "total": len(rows)})


@api_bp.route("/mobile/category", methods=["POST"])
def mobile_category_create():
    """新建分类（管理员），走 `create_category_core`：`{"name": "…"}`。

    同名精确判重（`Category.name` 有唯一约束），与编辑器里的「就地新建」同一判据 ——
    两边口径不同就会出现「App 建一个、编辑器再建一个」的双胞胎分类。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    from admin.taxonomy import create_category_core
    cid, err = create_category_core((_body().get("name") or ""))
    if err:
        return jsonify({"error": err}), 400
    cat = db.session.get(Category, cid)
    log_audit("mobile_cat_create", "category", cid, f"移动端新建分类：{cat.name}", user=user)
    return jsonify({"ok": True, "item": _category_json(cat)}), 201


@api_bp.route("/mobile/category/<int:cid>", methods=["POST", "PUT"])
def mobile_category_rename(cid):
    """分类改名（管理员），走 `rename_category_core`：`{"name": "…"}`。

    ⚠️ 返回里的 `note` 会说「地址已由 /category/旧 改为 /category/新，此前发出去的旧链接会失效」。
    这是**沿用后台既有行为**（改名无条件重算 slug），本次没有改判据，只是把结果如实回传，
    让 App 能在提交前把它显示出来。站点没有 slug 别名表也没有 301，所以这条提醒不是客套话。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    cat = db.session.get(Category, cid)
    if cat is None:
        return jsonify({"error": "分类不存在"}), 404
    from admin.taxonomy import rename_category_core
    err, note = rename_category_core(cat, (_body().get("name") or ""))
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_cat_rename", "category", cid, f"移动端分类改名：{cat.name}｜{note}", user=user)
    return jsonify({"ok": True, "note": note, "item": _category_json(cat)})


@api_bp.route("/mobile/category/<int:cid>/delete", methods=["POST"])
def mobile_category_delete(cid):
    """删除分类（管理员），走 `delete_category_core`：可选 `{"move_to": 目标分类 id}`。

    两种结果都必须让调用方知道：
      · 给了可用的 `move_to` → 文章整体转移（`moved` = 转移篇数）；
      · 不给 → 文章**留着但变成无分类**（`moved=0`，`affected` 就是受影响篇数）。
    所以响应同时返回 `affected` 与 `moved`，App 的确认框要按这两个数说人话。
    `move_to` 指向不存在的分类或自身时直接 400，而不是静默退化成「无分类」。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    cat = db.session.get(Category, cid)
    if cat is None:
        return jsonify({"error": "分类不存在"}), 404
    body = _body()
    move_to = body.get("move_to")
    if move_to not in (None, "", 0, "0"):
        try:
            target = db.session.get(Category, int(move_to))
        except (TypeError, ValueError):
            target = None
        if target is None or target.id == cid:
            return jsonify({"error": "move_to 必须是另一个存在的分类 id"}), 400
    affected = cat.posts.count()
    from admin.taxonomy import delete_category_core
    moved, name = delete_category_core(cat, move_to)
    log_audit("mobile_cat_delete", "category", cid,
              f"移动端删除分类：{name}（转移 {moved}/{affected} 篇）", user=user)
    return jsonify({"ok": True, "name": name, "affected": affected, "moved": moved})


@api_bp.route("/mobile/tags")
def mobile_tags():
    """标签清单（管理员）：带每个标签的使用篇数与 `orphan_count`（0 使用的标签数）。

    与后台 `/admin/tags` 同一份计数（`tag_usage_counts()` 一条 GROUP BY，不逐标签拖文章）。
    `orphan_count > 0` 时 App 可以提示「可用一键整理」。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    from admin.taxonomy import tag_usage_counts
    counts = tag_usage_counts()
    rows = Tag.query.order_by(Tag.name).all()
    items = [_tag_json(t, counts.get(t.id, 0)) for t in rows]
    return jsonify({"items": items, "total": len(items),
                    "orphan_count": sum(1 for i in items if not i["post_count"])})


@api_bp.route("/mobile/tag", methods=["POST"])
def mobile_tag_create():
    """新建标签（管理员），走 `create_tag_core`：`{"name": "…"}`。

    查重按 `normalize_tag_key`（小写 + 去空白）扫全表，所以 `AI` / `ai` / `a i`
    只会留一个 —— 这条判据和后台「一键整理」合并重复标签用的是同一个函数。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    from admin.taxonomy import create_tag_core
    tid, err = create_tag_core((_body().get("name") or ""))
    if err:
        return jsonify({"error": err}), 400
    tag = db.session.get(Tag, tid)
    log_audit("mobile_tag_create", "tag", tid, f"移动端新建标签：{tag.name}", user=user)
    return jsonify({"ok": True, "item": _tag_json(tag)}), 201


@api_bp.route("/mobile/tag/<int:tid>/delete", methods=["POST"])
def mobile_tag_delete(tid):
    """删除标签（管理员），走 `delete_tag_core`。

    被文章用着就**拒绝**（400，不是 409：这是业务规则而不是并发冲突）。标签是文章的
    属性，级联清理等于悄悄改文章；要合并请走 `/mobile/tags/merge`。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    tag = db.session.get(Tag, tid)
    if tag is None:
        return jsonify({"error": "标签不存在"}), 404
    from admin.taxonomy import delete_tag_core
    err = delete_tag_core(tag)
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_tag_delete", "tag", tid, f"移动端删除标签：{tag.name}", user=user)
    return jsonify({"ok": True})


@api_bp.route("/mobile/tags/merge", methods=["POST"])
def mobile_tags_merge():
    """一键整理标签（管理员）：合并大小写/空白变体 + 清理 0 使用的标签。

    与后台 `/admin/tags` 的 merge 按钮同一对函数（`merge_duplicate_tags` /
    `cleanup_orphan_tags`）。这里单独成一条 POST 而不是塞进 `DELETE /mobile/tags`：
    它会改动多篇文章的标签关联，属于「先看清单再按」的动作，App 侧应二次确认。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("tags_merge", 5)
    if blocked:
        return blocked
    from admin._helpers import cleanup_orphan_tags, merge_duplicate_tags
    merged = merge_duplicate_tags()
    cleaned = cleanup_orphan_tags()
    log_audit("mobile_tags_merge", "tag", None,
              f"移动端标签整理：合并 {merged} 个，清理未使用 {cleaned} 个", user=user)
    return jsonify({"ok": True, "merged": merged, "cleaned": cleaned})


@api_bp.route("/mobile/series")
def mobile_series():
    """系列清单（管理员）：按后台同排序口径（`sort` 升序、再按创建时间倒序），带文章数。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    rows = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    items = [_series_json(s) for s in rows]
    return jsonify({"items": items, "total": len(items)})


@api_bp.route("/mobile/series", methods=["POST"])
def mobile_series_create():
    """新建系列（管理员），走 `create_series_core`：`{"name": "…", "description", "cover", "sort"}`。

    `Series.name` **没有唯一约束**（与 `Category` 不同），所以重名不会被拒 —— 核心的查重
    只在编辑器「就地新建」那条路径上按名精确定位复用。App 里想避免重复系列，先拉清单比对。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    from admin.taxonomy import create_series_core
    sid, err = create_series_core(_body())
    if err:
        return jsonify({"error": err}), 400
    ser = db.session.get(Series, sid)
    log_audit("mobile_series_create", "series", sid, f"移动端新建系列：{ser.name}", user=user)
    return jsonify({"ok": True, "item": _series_json(ser)}), 201


@api_bp.route("/mobile/series/<int:sid>", methods=["POST", "PUT"])
def mobile_series_update(sid):
    """编辑系列（管理员），走 `rename_series_core`：`name` 必填，`description/cover/sort` 给了才改。

    「给了才改」是后台原行为，移动端整单回传时等于全量覆盖；只想改简介就别带 `cover`
    以外的字段？—— 不必小心翼翼：本接口的缺省语义就是「保持原值」，与 `/mobile/post/<id>`
    的「缺省即清空」**相反**，两个接口的表单语义不同，写客户端时别看串行。
    改名同样会换 slug 并在 `note` 里说明旧链接失效。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    ser = db.session.get(Series, sid)
    if ser is None:
        return jsonify({"error": "系列不存在"}), 404
    from admin.taxonomy import rename_series_core
    err, note = rename_series_core(ser, _body())
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_series_update", "series", sid,
              f"移动端编辑系列：{ser.name}｜{note}", user=user)
    return jsonify({"ok": True, "note": note, "item": _series_json(ser)})


@api_bp.route("/mobile/series/<int:sid>/delete", methods=["POST"])
def mobile_series_delete(sid):
    """删除系列（管理员），走 `delete_series_core`：可选 `{"move_to": 目标系列 id}`。

    不给 `move_to` 与后台原行为一致：文章留着、只是脱离系列（上/下篇导航随之消失）。
    转移是这次为手机端**新增的可选去路**，不是改默认行为。`affected` / `moved` 的含义
    同分类删除。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("taxonomy_write", 20)
    if blocked:
        return blocked
    ser = db.session.get(Series, sid)
    if ser is None:
        return jsonify({"error": "系列不存在"}), 404
    body = _body()
    move_to = body.get("move_to")
    if move_to not in (None, "", 0, "0"):
        try:
            target = db.session.get(Series, int(move_to))
        except (TypeError, ValueError):
            target = None
        if target is None or target.id == sid:
            return jsonify({"error": "move_to 必须是另一个存在的系列 id"}), 400
    affected = Post.query.filter_by(series_id=sid).count()
    from admin.taxonomy import delete_series_core
    moved, name = delete_series_core(ser, move_to)
    log_audit("mobile_series_delete", "series", sid,
              f"移动端删除系列：{name}（转移 {moved}/{affected} 篇）", user=user)
    return jsonify({"ok": True, "name": name, "affected": affected, "moved": moved})


# ---------------------------------------------------------------- 友链本体（v4.4.0）


def _friend_link_json(f):
    return {
        "id": f.id, "name": f.name, "url": f.url, "description": f.description or "",
        "sort": f.sort or 0, "rss_url": f.rss_url or "",
    }


@api_bp.route("/mobile/links")
def mobile_links():
    """友链清单（管理员）：按 `sort` 升序，与前台展示顺序一致（排序界面直接用这个顺序）。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    rows = FriendLink.query.order_by(FriendLink.sort).all()
    items = [_friend_link_json(f) for f in rows]
    return jsonify({"items": items, "total": len(items)})


@api_bp.route("/mobile/link", methods=["POST"])
def mobile_link_create():
    """新增友链（管理员），走 `save_friend_link_core`：`{"name","url","description","sort","rss_url"}`。

    URL 归一与校验都在核心里（补 `https://`、只放行 http/https、拒 `javascript:` 等伪协议
    与站内相对路径），同 URL 会查重。后台原先**不查重**，这次统一到审核路径已有的那套口径。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("link_write", 20)
    if blocked:
        return blocked
    from admin._helpers import save_friend_link_core
    err, note, link = save_friend_link_core(None, _body())
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_link_create", "friend_link", link.id,
              f"移动端新增友链：{link.name}", user=user)
    return jsonify({"ok": True, "note": note, "item": _friend_link_json(link)}), 201


@api_bp.route("/mobile/link/<int:lid>", methods=["POST", "PUT"])
def mobile_link_update(lid):
    """编辑友链（管理员），走同一个 `save_friend_link_core`。

    这条能力后台原本也没有：只能删了重建，而重建会把 `sort` 位置弄丢。
    `note` 非空表示 RSS 软校验没通过（**保存已成功**，只是博客圈可能聚合不到），
    客户端要把它当提示而不是错误 —— 对方源可能临时抽风，硬拦会把能用的友链挡在门外。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("link_write", 20)
    if blocked:
        return blocked
    link = db.session.get(FriendLink, lid)
    if link is None:
        return jsonify({"error": "友链不存在"}), 404
    from admin._helpers import save_friend_link_core
    err, note, saved = save_friend_link_core(link, _body())
    if err:
        return jsonify({"error": err}), 400
    log_audit("mobile_link_update", "friend_link", lid, f"移动端编辑友链：{saved.name}", user=user)
    return jsonify({"ok": True, "note": note, "item": _friend_link_json(saved)})


@api_bp.route("/mobile/link/<int:lid>/delete", methods=["POST"])
def mobile_link_delete(lid):
    """删除友链（管理员）。⚠️ 硬删除；下次想加回来要重新填，`sort` 位置也保不住。"""
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("link_write", 20)
    if blocked:
        return blocked
    link = db.session.get(FriendLink, lid)
    if link is None:
        return jsonify({"error": "友链不存在"}), 404
    name = link.name
    db.session.delete(link)
    db.session.commit()
    log_audit("mobile_link_delete", "friend_link", lid, f"移动端删除友链：{name}", user=user)
    return jsonify({"ok": True})


@api_bp.route("/mobile/links/reorder", methods=["POST"])
def mobile_links_reorder():
    """友链排序（管理员）：`{"ids": [id, id, …]}`，数组顺序即展示顺序。

    走 `reorder_friend_links_core`：`sort` 按 `(i+1)*10` 重算（留空档便于以后插位），
    **只有列出来的 id 会动**，没列的保持原位 —— 半提交时把未列出的甩到末尾才是更危险的行为。
    上限 500 条：手机上一次拖完整个列表，超过这个数量说明应该去后台分页处理。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("link_reorder", 10)
    if blocked:
        return blocked
    ids = _body().get("ids")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids 必须是非空数组"}), 400
    from admin._helpers import reorder_friend_links_core
    moved = reorder_friend_links_core(ids[:500])
    log_audit("mobile_link_reorder", "friend_link", None,
              f"移动端友链重排：改动 {moved} 条", user=user)
    return jsonify({"ok": True, "moved": moved})


# ---------------------------------------------------------------- 文章版本历史（v4.4.0）


def _history_json(h, full=False):
    d = {
        "id": h.id, "post_id": h.post_id, "title": h.title or "",
        "summary": h.summary or "", "author": h.author or "",
        "created_at": _iso(h.created_at), "size": len(h.content or ""),
    }
    if full:
        d["content"] = h.content or ""
    return d


@api_bp.route("/mobile/post/<int:post_id>/history")
def mobile_post_history(post_id):
    """版本历史列表（可编辑者）：时间倒序，**不含正文**（`size` 是正文字符数）。

    权限沿用后台同一条 `_can_edit_post`：普通用户只能看自己的文章，管理员看全部。
    列表不返回正文是有意的 —— 一次历史可能十几版，每版几十 KB。
    """
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if post is None:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能查看自己文章的版本历史"}), 403
    rows = (PostHistory.query.filter_by(post_id=post_id)
            .order_by(PostHistory.created_at.desc()).all())
    return jsonify({"items": [_history_json(h) for h in rows], "total": len(rows),
                    "post_id": post_id, "post_title": post.title,
                    "current": {"title": post.title, "summary": post.summary or "",
                                "size": len(post.content or "")}})


@api_bp.route("/mobile/post/<int:post_id>/history/<int:hid>")
def mobile_post_history_detail(post_id, hid):
    """某个历史版本的完整正文（供预览 / 逐字比对）。"""
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if post is None:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能查看自己文章的版本历史"}), 403
    h = PostHistory.query.filter_by(id=hid, post_id=post_id).first()
    if h is None:
        return jsonify({"error": "历史版本不存在"}), 404
    return jsonify(_history_json(h, full=True))


@api_bp.route("/mobile/post/<int:post_id>/history/diff")
def mobile_post_history_diff(post_id):
    """版本对比（可编辑者）：`?a=<历史 id>` 与**当前正文**做逐行 diff。

    实现直接复用后台的 `_line_diff`（等值段只留 2 行上下文），所以手机上看到的差异
    与后台页面逐字一致；不指定 `a` 时与最近一版比。没有历史时返回 404，而不是空数组
    —— 客户端需要区分「没差异」和「没历史」。
    """
    user, deny = _role()
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if post is None:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能查看自己文章的版本对比"}), 403
    from admin.post_history import _line_diff
    versions = PostHistory.query.filter_by(post_id=post_id) \
        .order_by(PostHistory.created_at.desc()).all()
    a_id = request.args.get("a", type=int)
    base = None
    if a_id:
        base = PostHistory.query.filter_by(id=a_id, post_id=post_id).first()
    if base is None and versions:
        base = versions[0]
    if base is None:
        return jsonify({"error": "暂无历史版本可对比"}), 404
    rows = [{"kind": k, "old": o, "new": n}
            for k, o, n in _line_diff(base.content or "", post.content or "")]
    return jsonify({"post_id": post_id, "base": _history_json(base), "rows": rows})


@api_bp.route("/mobile/post/<int:post_id>/history/<int:hid>/rollback", methods=["POST"])
def mobile_post_rollback(post_id, hid):
    """回滚到指定历史版本（可编辑者），走 `rollback_post_core`。

    ⚠️ **只写回 `title` / `summary` / `content`**：不动 slug、封面、分类、标签、系列、
    发布态、SEO —— 所以回滚不会破坏已分发的 URL，也不会把已发布文章悄悄变草稿。
    回滚前会先把当前版本存进历史，因此这一步本身还能再撤销（App 侧可以据此写文案）。
    """
    user, deny = _role()
    if deny:
        return deny
    blocked = _limit("rollback", 20)
    if blocked:
        return blocked
    post = db.session.get(Post, post_id)
    if post is None:
        return jsonify({"error": "文章不存在"}), 404
    from admin._helpers import _can_edit_post, rollback_post_core
    if not _can_edit_post(user, post):
        return jsonify({"error": "只能回滚自己文章的版本"}), 403
    h = PostHistory.query.filter_by(id=hid, post_id=post_id).first()
    if h is None:
        return jsonify({"error": "历史版本不存在"}), 404
    err = rollback_post_core(post, h, user)
    if err:
        return jsonify({"error": err}), 403
    log_audit("mobile_rollback", "post", post_id, f"移动端回滚到版本 {hid}", user=user)
    return jsonify({"ok": True, "title": post.title, "size": len(post.content or "")})


# ---------------------------------------------------------------- 媒体库（v4.4.0）


@api_bp.route("/mobile/media")
def mobile_media():
    """媒体库（管理员）：`static/uploads` 清单，`q` 搜文件名、`only_free=1` 只看疑似无引用。

    数据源是**目录列举**而不是数据库（上传不入库，这是本站既有设计），所以分页在内存里切，
    `total` 是文件数。代价见 `admin.media.collect_media`：引用判定是 O(文件数 × 文章数) 的
    字符串包含，第一次拉全量会有点慢；`per_page` 请传 20~30，别一次 100。
    每项 `refs` 是最多 6 条「疑似引用它的文章」，`ref_total` 是**完整**篇数。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    import os
    from admin.media import collect_media
    page, per_page = _page_args(20)
    kw = (request.args.get("q") or "").strip().lower()
    only_free = _tri("only_free")
    items = collect_media()
    if kw:
        items = [i for i in items if kw in i["name"].lower()]
    if only_free:
        items = [i for i in items if not i["ref_total"]]
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (min(page, pages) - 1) * per_page
    return jsonify({"items": items[start:start + per_page], "total": total,
                    "page": min(page, pages), "pages": pages})


@api_bp.route("/mobile/media/delete", methods=["POST"])
def mobile_media_delete():
    """删除上传文件（管理员）：`{"name": "文件名", "force": true}`。

    走 `delete_media_core` 的五道路径防护（basename / 拒空与 `.` `..` / 必须落在 uploads 层内 /
    必须是普通文件 / 才 remove），所以 `../` 之类的穿越在这里一律无效。

    被引用时默认 **409 + 引用清单**，必须再发一次带 `force: true` 的请求才会真删：
    删图不会进回收站，也没有「恢复上一版」，而文章里的 `![](/static/uploads/x.png)`
    会当场图裂 —— 这是本模块唯一一个用 409 表达「请先确认」的接口。
    副作用照旧：只删点名的文件，转格式生成的同名 `.avif` 旁路会留成孤儿。
    """
    user, deny = _role(admin=True)
    if deny:
        return deny
    blocked = _limit("media_delete", 20)
    if blocked:
        return blocked
    import os
    from admin.media import delete_media_core, media_refs_for
    body = _body()
    name = os.path.basename((body.get("name") or "").strip())
    if not name or name in (".", ".."):
        return jsonify({"error": "参数不合法"}), 400
    refs = media_refs_for(name)
    if refs and not _flag(body, "force"):
        return jsonify({"error": f"该文件疑似被 {len(refs)} 篇文章引用，删除后文章图片会失效",
                        "refs": refs[:6], "ref_total": len(refs), "need_force": True}), 409
    ok, msg = delete_media_core(name)
    if not ok:
        return jsonify({"error": msg}), 404 if msg == "文件不存在" else 400
    log_audit("mobile_media_delete", "media", None,
              f"移动端删除文件：{name}（引用 {len(refs)} 篇）", user=user)
    return jsonify({"ok": True, "name": msg, "ref_total": len(refs)})


# ---------------------------------------------------------------- 通知


@api_bp.route("/mobile/notifications")
def mobile_notifications():
    """站内通知（薄封装）。既有 `/api/notifications` 是同一数据源，这里只是为省一次往返。

    注意：「谁评论了我」写的是 `Notification`，而「待审评论 / 未读评论」是 `Comment`
    表上的 `approved` / `is_read` 两个标记（见 `/api/mobile/overview` 的 counts）。
    App 角标要同时看这两处，只看 notifications 会漏掉新评论。
    """
    user, deny = _role()
    if deny:
        return deny
    limit = request.args.get("limit", 20, type=int) or 20
    limit = max(1, min(50, limit))
    rows = (Notification.query.filter_by(user_id=user.id)
            .order_by(Notification.created_at.desc()).limit(limit).all())
    unread_comments = Comment.query.filter_by(is_read=False).count() if user.is_admin_role else 0
    return jsonify({
        "unread": Notification.query.filter_by(user_id=user.id, is_read=False).count(),
        "unread_comments": unread_comments,
        "items": [{
            "id": n.id, "content": n.content, "link": n.link or "",
            "is_read": bool(n.is_read), "created_at": _iso(n.created_at),
        } for n in rows],
    })
