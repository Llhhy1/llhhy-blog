"""API 蓝图共享辅助模块（api 包内部用，不定义任何路由）。

存放原本集中在 myblog/api.py 顶部的：
- 顶层导入（models / utils / stats / audit.log_login_attempt）
- 模块级常量（_UPDATE_LOCK、_VER_CHECK_CACHE）
- 各功能模块共用的辅助函数（序列化、登录会话、CSRF、可见性判断等）

设计意图：功能模块只 `from .common import ...` 按需取用，
不互相 import，避免循环依赖；本模块不 import 任何 api 子模块。
"""
import json
import os
import datetime
import threading

from flask import Blueprint, request, jsonify, current_app, session, Response
from markupsafe import escape

# API 蓝图的唯一事实来源（原 myblog/api.py 第 27 行）。
# 所有功能模块 `from .common import api_bp` 取用；__init__.py 聚合后，
# app.py 的 `from api import api_bp` 保持兼容，url_prefix="/api" 不变。
api_bp = Blueprint("api", __name__, url_prefix="/api")

# 在线更新防重入：进程内锁（消除「两请求同时读到 idle 各自 Popen」的 TOCTOU）。
# 锁不跨 worker，但 update.sh 还会写 data/update_status.json 文件锁，双保险；
# 同一 worker 内并发触发必然只有一个能拿到锁。
_UPDATE_LOCK = threading.Lock()

# 版本自检缓存（v2.5.0 起）：进程内缓存 GitHub 最新版本（10 分钟）
_VER_CHECK_CACHE = {"ts": 0, "latest": ""}

from models import db, Post, Category, Tag, Comment, FriendLink, Setting, User, ROLE_USER, \
    Moment, MomentComment, SocialAccount, Series, Announcement, Guestbook, Subscriber, Notification, \
    ReadLog, visible_posts_query, LinkApplication, AuditLog, PostHistory, RecycleBin, PostTag
from utils import (render_markdown, clean_html, render_post_html,
                   rate_limit, client_key, fmt_bj, to_beijing, BEIJING_TZ)
# 刻意保留的**再导出**：本模块按 docstring 的约定集中存放顶层导入，供各功能模块
# `from .common import ...` 取用（避免循环依赖）。故这些导入在本文件内「未使用」
# 是设计使然，不是死代码 —— 删掉会破坏下游的 `from .common import X`。
import stats  # noqa: F401
# v3.1.0：记录登录审计。v3.25.0 起实现位于顶层 `audit.py` —— 原先从 `admin` 取，
# 与 `admin.ai_summary → api` 一起把 admin 与 api 拉进同一个 21 模块强连通分量。
from audit import log_login_attempt
from _time import utcnow


def _current_user_or_none():
    """取当前登录用户对象（用于隐私空间可见性判断），未登录返回 None。"""
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def _user_pub(u):
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "role_label": u.role_label,
        "is_super": u.is_super,
        "is_admin": u.is_admin_role,
        "created_at": fmt_bj(u.created_at, "%Y-%m-%d"),
    }


def _login_user(u, twofa_ok=False):
    """登录：Flask session 与前端通过 header X-User-Id 共用同一会话。
    v3.1.6：登录后会话变化，响应带新 csrf_token 供前端立即更新缓存。

    v3.21.2 审计：**每次建立登录态都必须把 `twofa_ok` 显式写回**（默认 False）。
    2FA 是否放行由全局闸门 `app.enforce_twofa` 依据该标记判定；若沿用上一轮会话
    留下的 True，改密码/换账号后就能带着旧的「已过第二因素」直接进后台。
    """
    session["user_id"] = u.id
    session["session_version"] = u.session_version or 0  # v3.1.6：会话版本绑定，改密码/踢下线后旧会话失效
    session["twofa_ok"] = bool(twofa_ok)
    return jsonify({"ok": True, "user": _user_pub(u), "csrf_token": _csrf_token()})


def _login_delay():
    """v3.1.6：登录失败统一延迟（LOGIN_DELAY_SECONDS 默认 1 秒），
    让「用户不存在」与「密码错误」耗时一致，杜绝通过响应时间枚举用户名。
    仅对失败路径生效，不影响正常登录体验。异常静默。
    """
    try:
        import time as _t
        from utils import flag_num
        delay = flag_num("login_delay_seconds", "LOGIN_DELAY_SECONDS", 1.0, float)
        if delay > 0:
            _t.sleep(delay)
    except Exception:
        pass


def _csrf_token():
    """从会话取 CSRF Token；不存在则生成（每次生成都会写入会话）。"""
    from utils import generate_csrf_token
    try:
        tok, _ = generate_csrf_token()
        return tok
    except Exception:
        return ""


def _render_html(post):
    """渲染文章正文为 HTML（已做 XSS 白名单清理）。

    v3.9.1：参数由「正文字符串」改为「Post 对象」，走渲染缓存（post.content_html），
    正文未变时不再重复渲染。仅 api/posts.py 的文章详情使用。
    """
    return render_post_html(post)


def _settings_map():
    return {s.key: s.value for s in Setting.query.all()}


def _post_summary(p):
    return {
        "slug": p.slug,
        "title": p.title,
        "author": p.author.username if p.author else "",  # 作者身份（普通用户发表的文章记录作者；管理员/旧文章为空）
        "summary": p.summary or "",
        "cover": p.cover or "",
        "created_at": fmt_bj(p.created_at, "%Y-%m-%d %H:%M"),
        "views": p.views,
        "likes": p.likes,
        "is_pinned": bool(p.is_pinned),  # 是否置顶（首页/列表优先展示）
        # SEO 单独字段（v2.8.0）：独立描述/关键词，缺省回退
        "seo_description": p.seo_description or p.summary or "",
        "seo_keywords": p.seo_keywords or "",
        "category": {"name": p.category.name, "slug": p.category.slug} if p.category else None,
        "tags": [{"name": t.name, "slug": t.slug} for t in p.tags],
        # v3.0.0 新增字段
        "word_count": p.word_count or 0,
        "reading_minutes": p.reading_minutes or 0,
        "reward_enabled": bool(p.reward_enabled),
        "is_private": bool(p.is_private),
        # v3.21.0 内容多语言：语言代码 + 译文组标识（前端语言切换器与 hreflang 用）
        "lang": p.lang or "zh",
        "translation_group": p.translation_group or "",
    }


def lang_dedup(posts, lang):
    """列表按语言展示：同一 translation_group 优先返回 lang 版本，否则返回默认（首个）版本。

    用于首页/分类/标签列表在 `?lang=` 下避免同组多语言重复出现。posts 须为已按
    展示顺序排好的列表（调用方先 order_by）；返回的列表保持原顺序（按首现顺序）。
    """
    if not lang:
        return posts
    by_group = {}
    order = []
    for p in posts:
        g = p.translation_group or ("__solo__%d" % p.id)
        if g not in by_group:
            by_group[g] = []
            order.append(g)
        by_group[g].append(p)
    out = []
    for g in order:
        members = by_group[g]
        variant = next((x for x in members if x.lang == lang), None)
        out.append(variant if variant else members[0])
    return out


# ---------- v4.0.0：列表分页下推 SQL ----------
# 展示顺序的唯一真相源。置顶优先 → 时间倒序 → id 兜底。
# ⚠️ 必须带 `Post.id` 兜底：OFFSET 分页要求**全序**，若两条 (is_pinned, created_at)
# 完全相同，数据库返回顺序未定义，翻页时同一条可能出现在两页、另一条被跳过。
_DISPLAY_ORDER = (Post.is_pinned.desc(), Post.created_at.desc(), Post.id.asc())


def _translation_group_key():
    """分组键 SQL 表达式：同 translation_group 一组；无组（独立文章）按 id 自成一組。

    与 Python 版 `lang_dedup()` 的 `p.translation_group or ("__solo__%d" % p.id)` 对齐：
    空字符串视为无组，用 id 兜底保证独立文章不会互相并组。
    """
    return db.func.coalesce(
        db.func.nullif(Post.translation_group, ""),
        "solo:" + db.cast(Post.id, db.String),
    )


def paged_posts(query, page=1, per_page=10, lang=""):
    """把「可见文章查询」按页取出，**SQL 侧 LIMIT/OFFSET，绝不物化全表**。

    返回 `(items, total)`；items 已按展示顺序排好。

    改造动机（审计【低危 7】）：原实现 `lang_dedup(query.all(), lang)` 先把**全部**
    可见文章物化成 ORM 对象（含 identity map 与关系惰性加载），再在 Python 里切片 ——
    文章越多越慢、内存无上限。这里把两件事都下推到数据库：

    1. 无 `?lang=`（绝大多数请求）：直接 `LIMIT/OFFSET`，数据库只返回一页。
    2. 带 `?lang=`：用窗口函数在同组内选出代表行，**同时**把「组在列表中的先后」
       也算进 SQL —— 否则只能先取全量再分页，等于没改。

    **为什么必须 `FIRST_VALUE` 而不是 `MAX()`**：`lang_dedup()` 的组顺序是「组内
    首个成员在展示顺序中的位置」，即 (is_pinned, created_at, id) 的**字典序 argmax**。
    对两列分别取 MAX 会得到 (1, t_late) 这种**不属于任何一行**的组合（首成员是
    (1, t_early) 时），排序就错了。`FIRST_VALUE(...) OVER (PARTITION BY 组 ORDER BY
    展示顺序)` 取的正是首成员**同一行**的各列，语义精确等价。
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = 10
    page = max(1, page)
    per_page = max(1, per_page)
    offset = (page - 1) * per_page

    if not lang:
        total = query.count()
        items = query.order_by(*_DISPLAY_ORDER).limit(per_page).offset(offset).all()
        return items, total

    grp = _translation_group_key()
    # 一次聚合同时拿到「文章数」与「组数」（grp 是 `COALESCE(NULLIF(group,''), 'solo:'||id)`，
    # 独立文章各自成组，故 `组数 == 文章数` ⟺ **每个组恰好一篇** ⟺ 去重是恒等操作）。
    # 这条判据顺带省掉了「先探一次有没有译文组」的额外查询：直接普通分页即可。
    rows_n, total = query.with_entities(
        db.func.count(), db.func.count(db.func.distinct(grp))).one()
    total = total or 0
    if not total:
        return [], 0
    if rows_n == total:
        items = query.order_by(*_DISPLAY_ORDER).limit(per_page).offset(offset).all()
        return items, total
    disp = list(_DISPLAY_ORDER)
    # 代表行：优先 lang 命中的成员，其次按展示顺序取首个。
    rep = [db.case((Post.lang == lang, 0), else_=1)] + disp
    ranked = query.with_entities(
        Post.id.label("id"),
        db.func.row_number().over(partition_by=grp, order_by=rep).label("rn"),
        db.func.first_value(Post.is_pinned).over(partition_by=grp, order_by=disp).label("g_pinned"),
        db.func.first_value(Post.created_at).over(partition_by=grp, order_by=disp).label("g_created"),
        db.func.first_value(Post.id).over(partition_by=grp, order_by=disp).label("g_id"),
    ).subquery()
    ids = [r[0] for r in
           db.session.query(ranked.c.id).filter(ranked.c.rn == 1)
           .order_by(ranked.c.g_pinned.desc(), ranked.c.g_created.desc(), ranked.c.g_id.asc())
           .limit(per_page).offset(offset).all()]
    if not ids:
        return [], total
    by_id = {p.id: p for p in Post.query.filter(Post.id.in_(ids)).all()}
    return [by_id[i] for i in ids if i in by_id], total


def _comment(c, depth=0):
    return {
        "id": c.id,
        "author": c.author,
        "content": c.content,
        "created_at": fmt_bj(c.created_at, "%Y-%m-%d %H:%M"),
        "region": c.region or "",        # 归属地（前台展示；IP 原文不返回）
        "device": c.device or "",        # 设备信息
        "parent_id": c.parent_id or 0,   # 嵌套回复：父评论 id（0=顶层）
        "depth": depth,                  # v3.25.2：0=顶层；前端据此缩进 / 折叠「继续回复」
        "reply_to": c.reply_to or "",    # 被回复者昵称（@ 显示）
        "likes": c.likes or 0,           # 评论点赞数
        "avatar": ("https://cn.cravatar.com/avatar/" + c.email_hash + "?d=mp&s=80") if c.email_hash else "",
    }


def _current_user():
    """从会话取当前登录用户对象（未登录返回 None）。"""
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


def _moment(m):
    return {
        "id": m.id,
        "author": m.author.username if m.author else "匿名",
        "content": m.content,
        "created_at": fmt_bj(m.created_at, "%Y-%m-%d %H:%M"),
        "likes": m.likes,
        "comments": [_mcomment(c) for c in m.comments.order_by(MomentComment.created_at.asc())],
    }


def _mcomment(c):
    return {
        "id": c.id,
        "author": c.author,
        "content": c.content,
        "created_at": fmt_bj(c.created_at, "%Y-%m-%d %H:%M"),
        "region": c.region or "",
    }


def _gb(g):
    return {
        "id": g.id, "author": g.author, "content": g.content,
        "created_at": fmt_bj(g.created_at, "%Y-%m-%d %H:%M"),
        "likes": g.likes or 0,
        "region": g.region or "", "device": g.device or "",
    }