"""API 蓝图共享辅助模块（api 包内部用，不定义任何路由）。

存放原本集中在 myblog/api.py 顶部的：
- 顶层导入（models / utils / stats / admin.log_login_attempt）
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
    ReadLog, visible_posts_query, LinkApplication, AuditLog, PostHistory, RecycleBin
from utils import (render_markdown, clean_html, render_post_html,
                   rate_limit, client_key, fmt_bj, to_beijing, BEIJING_TZ)
import stats
# v3.1.0：记录登录审计（log_login_attempt 定义在 admin 模块，admin 不依赖 api，无循环）
from admin import log_login_attempt


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


def _login_user(u):
    """登录：Flask session 与前端通过 header X-User-Id 共用同一会话。
    v3.1.6：登录后会话变化，响应带新 csrf_token 供前端立即更新缓存。
    """
    session["user_id"] = u.id
    session["session_version"] = u.session_version or 0  # v3.1.6：会话版本绑定，改密码/踢下线后旧会话失效
    return jsonify({"ok": True, "user": _user_pub(u), "csrf_token": _csrf_token()})


def _login_delay():
    """v3.1.6：登录失败统一延迟（LOGIN_DELAY_SECONDS 默认 1 秒），
    让「用户不存在」与「密码错误」耗时一致，杜绝通过响应时间枚举用户名。
    仅对失败路径生效，不影响正常登录体验。异常静默。
    """
    try:
        import time as _t
        from flask import current_app
        delay = current_app.config.get("LOGIN_DELAY_SECONDS", 1.0)
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
    }


def _is_visible(p):
    """判断单篇文章当前是否对访客可见（已发布且未到定时发布时间）。"""
    if not p or not p.published:
        return False
    if p.scheduled_at is not None and p.scheduled_at > datetime.utcnow():
        return False
    return True


def _comment(c):
    return {
        "id": c.id,
        "author": c.author,
        "content": c.content,
        "created_at": fmt_bj(c.created_at, "%Y-%m-%d %H:%M"),
        "region": c.region or "",        # 归属地（前台展示；IP 原文不返回）
        "device": c.device or "",        # 设备信息
        "parent_id": c.parent_id or 0,   # 嵌套回复：父评论 id（0=顶层）
        "reply_to": c.reply_to or "",    # 被回复者昵称（@ 显示）
        "likes": c.likes or 0,           # 评论点赞数
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