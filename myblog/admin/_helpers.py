"""后台管理：登录、写文章、分类/标签/友链/设置/评论管理、修改密码、用户管理。"""
import functools
import os
import time
import datetime

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, current_app, abort, jsonify, send_file)
from werkzeug.utils import secure_filename

from models import (db, Post, Category, Tag, Comment, FriendLink, Setting,
                    User, ROLE_SUPER, ROLE_ADMIN, ROLE_USER, SocialAccount,
                    Series, Announcement, Guestbook, Subscriber,
                    AuditLog, RecycleBin, LinkApplication, PostHistory,
                    Moment, MomentComment)
from utils import make_slug, count_words, validate_password, apply_slug_template, fmt_bj, BEIJING_TZ
from config import APP_VERSION
import stats as stats_mod
import fts
import notify
import bot_guard
import mail_notify
import feed_agg
import diagnostics

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")



def _parse_scheduled(form_val):
    """把编辑页 datetime-local 输入（YYYY-MM-DDTHH:MM，视为北京时间）转成 UTC datetime 存储。

    为空或非法则返回 None（=立即/已发布，不定时）。编辑页输入框与表单默认值均按北京时间
    展示（见 edit_post 视图的 scheduled_local / now_local），此处把用户输入当北京时间，
    换算回 UTC 存储，保证「所见即北京、所存即 UTC」，定时发布不再错位 8 小时。
    """
    if not form_val:
        return None
    try:
        bj = datetime.datetime.fromisoformat(form_val)  # naive 北京时间
        if bj.tzinfo is None:
            bj = bj.replace(tzinfo=BEIJING_TZ)
        return bj.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    except Exception:
        return None

def login_required(view):
    """登录即可访问（普通注册用户也能进来——拥有「发表文章」权限）。

    登录体系前后台已融合：前台 /login 与后台共用同一 Flask 会话；
    未登录统一引导到前台登录页，登录成功后按权限回到对应页面。
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if not user:
            # 未登录：去前台统一登录页，登录后按 next 回到原页面
            return redirect("/login?next=" + request.path)
        # 首次进入后台：超级管理员还没设置过账号密码 → 强制去设置页
        if user.is_super and user.must_change_password:
            return redirect(url_for("admin.setup"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    """管理员及以上（super / admin）专属：普通用户（user）只被引导到写文章页。"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if not user:
            return redirect("/login?next=" + request.path)
        if not user.is_admin_role:
            # 普通用户没有管理权限：引导到「写文章」（他们能用的功能）
            return redirect(url_for("admin.new_post"))
        if user.is_super and user.must_change_password:
            return redirect(url_for("admin.setup"))
        return view(*args, **kwargs)
    return wrapped

def super_required(view):
    """超级管理员专属装饰器：其他角色（含普通管理员）一律 403。"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or not user.is_super:
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def _weak_password(raw):
    """v3.1.6 中优：弱密码统一校验（黑名单 + 复杂度）。返回错误文案；通过返回空字符串。"""
    try:
        from flask import current_app as _app
        cfg = _app.config
        ok, err = validate_password(
            raw or "", min_len=8,
            strong=cfg.get("STRONG_PASSWORD", True),
            mixed_case=cfg.get("STRONG_PASSWORD_MIXED_CASE", False),
        )
        return "" if ok else err
    except Exception:
        return "" if len(raw or "") >= 8 else "密码至少 8 位"

def _can_edit_post(user, post):
    """判断当前用户能否编辑/删除该文章：管理员可编辑全部；普通用户只能编辑自己的。"""
    if user.is_admin_role:
        return True
    return post.author_id is not None and post.author_id == user.id

def log_audit(action, target="", target_id=None, detail="", user=None, ip="", success=True):
    """记录一条后台操作审计日志（v3.0.0 功能4）。

    自动填操作人（传入 user 或当前会话用户）、用户名、来源 IP。
    所有后台写操作（增删改文章/评论/用户/设置/友链等）调用本函数，便于事后追溯。
    success：是否成功（登录失败/操作失败时为 False）。
    异常静默：单条日志失败不影响主流程。
    """
    try:
        if user is None:
            uid = session.get("user_id")
            user = db.session.get(User, uid) if uid else None
        ip = ip or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                    or request.remote_addr or "")
        db.session.add(AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=action, target=target, target_id=target_id,
            detail=(detail or "")[:300], ip=ip[:64], success=success,
        ))
        db.session.commit()
    except Exception:
        pass

def log_login_attempt(username, success, ip=""):
    """记录一次后台登录尝试（v3.1.0 新增）。

    无论成功失败都写入审计日志（action='login'），便于追溯异常登录与爆破。
    success=True 记 target='成功'，False 记 target='失败'（含尝试的用户名）。
    无请求上下文时（如离线脚本）安全降级，不抛异常。
    """
    if not ip:
        try:
            ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                  or request.remote_addr or "")
        except Exception:
            ip = ""
    try:
        db.session.add(AuditLog(
            user_id=None, username=(username or "")[:40],
            action="login", target=("成功" if success else "失败"),
            target_id=None, detail=(f"登录尝试：{username}" if not success else "后台登录"),
            ip=ip[:64], success=success,
        ))
        db.session.commit()
    except Exception:
        pass
    # 顺带清理超过保留周期的旧审计日志（含登录日志），避免表无限膨胀（v3.1.0；v3.1.6 周期可配）
    try:
        from flask import current_app as _app
        days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        days = 90
    _purge_audit_logs_older_than(days)

def _purge_audit_logs_older_than(days):
    """清理超过 N 天的审计日志（含登录日志）。轻量：仅当存在时才删除。"""
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete()
        if deleted:
            db.session.commit()
    except Exception:
        pass

def _audit_log_query_with_filters():
    """按 query 参数（from / to）构造审计日志查询（v3.1.6 中优·导出时间筛选）。

    支持 ?from=YYYY-MM-DD 与 ?to=YYYY-MM-DD（均为本地日期，按 UTC 存储比较）。
    无参数时返回全部（保留周期内）。
    """
    q = AuditLog.query
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    if frm:
        try:
            d = datetime.datetime.strptime(frm, "%Y-%m-%d")
            q = q.filter(AuditLog.created_at >= d)
        except ValueError:
            pass
    if to:
        try:
            d = datetime.datetime.strptime(to, "%Y-%m-%d") + datetime.timedelta(days=1)
            q = q.filter(AuditLog.created_at < d)
        except ValueError:
            pass
    return q, frm, to

def _current_user_or_none():
    """取当前登录用户对象（用于审计日志等），未登录返回 None。"""
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def unique_slug(base, post_id=None):
    base_slug = make_slug(base)
    slug = base_slug
    i = 2
    while True:
        q = Post.query.filter_by(slug=slug)
        if post_id:
            q = q.filter(Post.id != post_id)
        if not q.first():
            break
        slug = f"{base_slug}-{i}"
        i += 1
    return slug

@admin_bp.context_processor
def inject_notification_counts():
    """向所有后台模板注入未读评论/未读留言数量，用于导航角标和仪表盘提醒。"""
    try:
        pending_comments = Comment.query.filter_by(is_read=False).count()
        pending_guestbook = Guestbook.query.filter_by(is_read=False).count()
    except Exception:
        # 表尚未创建时（首次启动）不报错
        pending_comments = 0
        pending_guestbook = 0
    return {
        "pending_comments": pending_comments,
        "pending_guestbook": pending_guestbook,
        "app_version": APP_VERSION,
    }

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]

def _detect_image_magic(header, ext):
    """根据文件头魔数 + 期望后缀判断是否匹配。返回 False 拒绝，True 通过。
    对 webp 追加 RIFF 后的 'WEBP' 四个字节精验；其余按魔数前缀匹配。
    """
    for magic, (mtype, _) in _MAGIC_PATTERNS.items():
        if header.startswith(magic):
            if mtype == "webp":
                if len(header) >= 12 and header[8:12] == b"WEBP":
                    return True
                return False
            return True
    return False

def _sync_tags(post, raw):
    """把表单里 '生活, 技术' 这样的标签字符串同步到文章。"""
    names = [n.strip() for n in (raw or "").split(",") if n.strip()]
    post.tags = []
    for name in names:
        slug = make_slug(name)
        tag = Tag.query.filter_by(slug=slug).first()
        if not tag:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
            db.session.flush()
        post.tags.append(tag)

def _save_post_history(post, author=""):
    """保存当前文章的版本快照（v3.0.0 功能5）。

    每次有内容/标题变化时调用，存一份 title/summary/content/author 快照。
    仅保留最近 20 个版本（超出删最旧），避免无限增长。
    """
    try:
        db.session.add(PostHistory(
            post_id=post.id, title=post.title or "", summary=post.summary or "",
            content=post.content or "", author=author or "",
        ))
        # 限制每个文章最多 20 个历史版本
        old = PostHistory.query.filter_by(post_id=post.id).order_by(PostHistory.created_at.asc()).all()
        if len(old) > 20:
            for h in old[:len(old) - 20]:
                db.session.delete(h)
    except Exception:
        pass

# 让 from ._helpers import *（各业务子模块与包 __init__）也导出下划线辅助函数
# （Python 默认 star-import 跳过下划线命名，会导致 edit_post 等视图调用的
#  _can_edit_post / _save_post_history 等私有 helper 在子模块内 NameError）。
__all__ = [n for n in globals() if not n.startswith("__")]
