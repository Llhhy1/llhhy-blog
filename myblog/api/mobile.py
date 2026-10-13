# -*- coding: utf-8 -*-
"""移动端管理接口（v4.3.0）：把后台管理能力以 JSON 暴露给原生 App / 第三方客户端。

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
- **限流**：写接口按客户端 IP 限流（`utils.rate_limit`），超限 `429`。只读接口沿用
  `/api/stats/*` 的口径（30/分钟）或不限流。
"""
import contextlib

from flask import current_app, jsonify, request, url_for

from models import (BotBlock, Category, Comment, FriendLink, LinkApplication, Moment,
                    Notification, Post, RecycleBin, Series, Tag, User, VisitLog, db)
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


def _iso(dt):
    return fmt_bj(dt, "%Y-%m-%d %H:%M") if dt else ""


def _like(raw):
    """转义 LIKE 通配符（与 `admin/visit_logs.py::_like` 同语义：防筛选词被当通配符）。"""
    esc = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + esc + "%"


# ---------------------------------------------------------------- 序列化


def _post_admin(p):
    """管理视角文章摘要：公开 `_post_summary` 之外补上「只有后台需要」的状态位。

    ⚠️ 不带 `content` —— 列表只需标题与状态，正文留给详情接口，
    避免一次列表拖回几百 KB 正文（手机网络下最明显）。
    """
    d = _post_summary(p)
    d.update({
        "id": p.id,
        "published": bool(p.published),
        "in_trash": bool(p.in_trash),
        "pin_requested": bool(p.pin_requested),
        "scheduled_at": _iso(p.scheduled_at),
        "updated_at": _iso(p.updated_at),
        "comment_count": p.comments.count(),
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
    return _paged(q, page, per_page, _post_admin)


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
    user, deny = _role(admin=True)
    if deny:
        return deny
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({"error": "文章不存在"}), 404
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
    want = _flag(_body(), "pinned")
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
    """
    user, deny = _role(admin=True)
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
    """正在生效的 IP 封禁列表（App 侧「谁被我拉黑了 / 解封」入口）。"""
    user, deny = _role(admin=True)
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
    filename = f"{int(time.time())}-{secure_filename(f.filename)}"
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
