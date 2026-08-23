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
                    AuditLog, RecycleBin, LinkApplication, PostHistory)
from utils import make_slug, count_words, validate_password
from config import APP_VERSION
import stats as stats_mod
import fts
import notify
import mail_notify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _parse_scheduled(form_val):
    """把编辑页 datetime-local 输入（YYYY-MM-DDTHH:MM，视为服务器本地时间）转成 UTC datetime。

    为空或非法则返回 None（=立即/已发布，不定时）。返回的值会与 utcnow 比较，
    故必须存 UTC；这里把本地输入按服务器时区转 UTC，避免定时时间偏差。
    """
    if not form_val:
        return None
    try:
        local = datetime.datetime.fromisoformat(form_val)  # naive 本地时间
        if local.tzinfo is None:
            # 视为服务器本地时区，转 UTC
            local = local.replace(tzinfo=datetime.timezone.utc).astimezone(datetime.timezone.utc)
            # 上面直接当 UTC 处理：因 gunicorn 容器多 UTC，简单以 UTC 解读输入更可预期
            local = datetime.datetime.fromisoformat(form_val).replace(tzinfo=datetime.timezone.utc)
        return local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
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


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """后台登录（普通用户与管理员共用，已与前台统一登录融合）。
    登录成功后按角色分流：管理员/超管 → 仪表盘；普通用户 → 写作区（我的文章）。
    """
    uid = session.get("user_id")
    if uid:
        u = db.session.get(User, uid)
        if u:
            # 超级管理员首次登录：还没设置过账号密码 → 强制进设置页
            if u.is_super and u.must_change_password:
                return redirect(url_for("admin.setup"))
            # 管理员进仪表盘，普通用户进写作区（直接到写文章编辑器）
            return redirect(url_for("admin.dashboard") if u.is_admin_role
                            else url_for("admin.new_post"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            log_login_attempt(username, True)
            session["user_id"] = user.id
            session["session_version"] = user.session_version or 0  # v3.1.6：会话版本绑定
            if user.is_super and user.must_change_password:
                return redirect(url_for("admin.setup"))
            # 按角色分流
            return redirect(url_for("admin.dashboard") if user.is_admin_role
                            else url_for("admin.new_post"))
        log_login_attempt(username, False)
        flash("用户名或密码错误")
        return render_template("admin/login.html")
    # GET 未登录：跳转到前台统一登录页（同一会话，登录后按权限自动回到对应页面）
    return redirect("/login?next=/admin")


@admin_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """首次进入后台：强制超级管理员设置新的用户名与密码。
    注意：不能用 login_required（它会在 must_change_password=True 时把这里死循环重定向）。
    """
    if not session.get("user_id"):
        return redirect(url_for("admin.login"))
    user = db.session.get(User, session.get("user_id"))
    if not user or not user.is_super:
        abort(403)
    if request.method == "POST":
        new_username = (request.form.get("username") or "").strip()
        new_password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not new_username or len(new_username) < 2 or len(new_username) > 20:
            flash("用户名长度需在 2-20 个字符")
        elif _weak_password(new_password):
            flash(_weak_password(new_password))
        elif new_password != confirm:
            flash("两次输入的新密码不一致")
        else:
            dup = User.query.filter(User.username == new_username, User.id != user.id).first()
            if dup:
                flash("该用户名已被使用")
            else:
                user.username = new_username
                user.set_password(new_password)
                user.must_change_password = False
                user.session_version = (user.session_version or 0) + 1  # v3.1.6：改密码销毁旧会话
                db.session.commit()
                # 重新登录：用新密码建立新会话（旧会话版本已失效）
                session["user_id"] = user.id
                session["session_version"] = user.session_version
                flash("账号设置完成，欢迎使用后台！")
                return redirect(url_for("admin.dashboard"))
    return render_template("admin/setup.html", user=user)


@admin_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop("user_id", None)
    session.pop("admin", None)
    return redirect(url_for("main.index"))


@admin_bp.route("/")
@admin_required
def dashboard():
    # 后台文章列表分页 + 状态/分类/关键词筛选（v2.8.0）
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    cat_id = request.args.get("category_id", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12
    query = Post.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if status == "published":
        query = query.filter(Post.published == True, Post.scheduled_at.is_(None))
    elif status == "draft":
        query = query.filter(Post.published == False, Post.scheduled_at.is_(None))
    elif status == "scheduled":
        query = query.filter(Post.scheduled_at.isnot(None), Post.published == False)
    elif status == "pinned":
        query = query.filter(Post.is_pinned == True)
    if cat_id:
        query = query.filter(Post.category_id == int(cat_id))
    pagination = query.order_by(Post.is_pinned.desc(), Post.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    pending = Comment.query.filter_by(approved=False).count()
    recent_comments = Comment.query.order_by(Comment.created_at.desc()).limit(6).all()
    from stats import compute_summary
    summary = compute_summary()
    cats = Category.query.order_by(Category.id).all()
    return render_template("admin/dashboard.html", posts=pagination.items,
                           pagination=pagination, filter_q=q, filter_status=status,
                           filter_cat=cat_id, cats=cats, pending=pending,
                           summary=summary, recent_comments=recent_comments)


@admin_bp.route("/post/<int:post_id>/publish-now", methods=["POST"])
@login_required
def publish_now(post_id):
    """定时文章一键提前公开（后台 SSR，v2.8.0）。

    校验登录与编辑权限（管理员全部 / 普通用户仅自己文章），立即翻 published 并清空
    scheduled_at。成功后回退到来源页（dashboard / my_posts），并提示已发布。
    """
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能操作自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if not post.published:
        post.published = True
        post.scheduled_at = None
        db.session.commit()
        try:
            notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
        except Exception:
            pass
        try:
            mail_notify.notify_subscribers_async(post)
        except Exception:
            pass
        flash("已立即发布该文章")
    else:
        flash("该文章已处于发布状态")
    # 回到来源页（后台一键发布入口可能在 dashboard 或 my_posts）
    back = request.args.get("back") or "admin.dashboard"
    return redirect(url_for(back))


# ---------- 置顶权限分层（v2.8.1）----------
# 规则：仅管理员/超管可直接置顶；普通用户须向超管「申请置顶」，由超管批准/拒绝。
# 超管可对任意文章「取消置顶」。所有操作均 POST + 登录/权限校验。
@admin_bp.route("/post/<int:post_id>/request-pin", methods=["POST"])
@login_required
def request_pin(post_id):
    """普通用户向超管申请置顶自己的文章。"""
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能申请自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if post.is_pinned:
        flash("该文章已置顶，无需申请")
    elif post.pin_requested:
        flash("已提交置顶申请，等待超管审批")
    else:
        post.pin_requested = True
        db.session.commit()
        flash("置顶申请已提交，等待超管审批")
    return redirect(url_for("admin.my_posts"))


@admin_bp.route("/post/<int:post_id>/cancel-pin-request", methods=["POST"])
@login_required
def cancel_pin_request(post_id):
    """普通用户撤回自己的置顶申请。"""
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能操作自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if post.pin_requested and not post.is_pinned:
        post.pin_requested = False
        db.session.commit()
        flash("已撤回置顶申请")
    return redirect(url_for("admin.my_posts"))


@admin_bp.route("/post/<int:post_id>/approve-pin", methods=["POST"])
@super_required
def approve_pin(post_id):
    """超管批准置顶申请：翻 is_pinned=True 并清申请态。"""
    post = Post.query.get_or_404(post_id)
    post.is_pinned = True
    post.pin_requested = False
    db.session.commit()
    flash(f"已批准置顶：{post.title}")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/post/<int:post_id>/reject-pin", methods=["POST"])
@super_required
def reject_pin(post_id):
    """超管拒绝置顶申请：清申请态，不置顶。"""
    post = Post.query.get_or_404(post_id)
    post.pin_requested = False
    db.session.commit()
    flash(f"已拒绝置顶申请：{post.title}")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/post/<int:post_id>/unpin", methods=["POST"])
@super_required
def unpin(post_id):
    """超管取消任意文章的置顶。"""
    post = Post.query.get_or_404(post_id)
    post.is_pinned = False
    db.session.commit()
    flash(f"已取消置顶：{post.title}")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("标题不能为空")
            return render_template("admin/edit_post.html", post=None)
        content = request.form.get("content", "")
        summary = (request.form.get("summary") or "").strip()
        cover = (request.form.get("cover") or "").strip()
        category_id = request.form.get("category_id") or None
        if category_id:
            category_id = int(category_id)
        published = request.form.get("published") == "on"
        scheduled_at = _parse_scheduled(request.form.get("scheduled_at"))
        # 定时发布：填了未来时间则先存为未发布，后台线程到点自动翻 published
        if scheduled_at is not None and scheduled_at > datetime.datetime.utcnow():
            published = False
        # 置顶权限分层（v2.8.1）：仅管理员/超管可直接置顶；普通用户表单里的 is_pinned 一律忽略（防绕过）
        user = db.session.get(User, session.get("user_id"))
        is_pinned = (request.form.get("is_pinned") == "on") and bool(user and user.is_admin_role)
        series_id = request.form.get("series_id") or None
        seo_description = (request.form.get("seo_description") or "").strip()
        seo_keywords = (request.form.get("seo_keywords") or "").strip()
        # v3.0.0 功能13/14：隐私空间 + 打赏（仅超管可设置）
        is_private = (request.form.get("is_private") == "on") and bool(user and user.is_super)
        reward_enabled = (request.form.get("reward_enabled") == "on") and bool(user and user.is_super)
        reward_qr = (request.form.get("reward_qr") or "").strip() if reward_enabled else ""
        # v3.0.0 功能12：字数统计 + 阅读时长
        wc, rm = count_words(content)
        post = Post(
            title=title, slug=unique_slug(title), summary=summary, content=content,
            cover=cover, category_id=category_id, published=published,
            scheduled_at=scheduled_at, is_pinned=is_pinned,
            seo_description=seo_description, seo_keywords=seo_keywords,
            series_id=int(series_id) if series_id else None,
            author_id=session.get("user_id"),  # 记录作者：普通用户发表的文章归属自己
            word_count=wc, reading_minutes=rm,
            is_private=is_private, reward_enabled=reward_enabled, reward_qr=reward_qr,
        )
        db.session.add(post)
        db.session.flush()  # 先把文章放进会话，避免标签关联警告
        _sync_tags(post, request.form.get("tags", ""))
        # v3.0.0 功能5：保存首个版本历史（新建即 v1）
        _save_post_history(post, user.username if user else "")
        db.session.commit()
        try:
            fts.sync_post(post)
        except Exception:
            pass
        if published:
            try:
                notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
            except Exception:
                pass
            # C3 邮件群发：新文章发布时异步通知所有订阅者（未配置 SMTP 自动跳过）
            try:
                mail_notify.notify_subscribers_async(post)
            except Exception:
                pass
        if scheduled_at is not None and not published:
            flash("已设为定时发布，到点自动公开")
        else:
            flash("文章已发布" if published else "草稿已保存")
        # 普通用户发布后回到「我的文章」，管理员回仪表盘
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    user = db.session.get(User, session.get("user_id"))
    return render_template("admin/edit_post.html", post=None, cats=cats, series=series,
                           current_user=user)


@admin_bp.route("/my-posts")
@login_required
def my_posts():
    """「我的文章」：普通用户查看/管理自己发表的文章（支持分页+筛选，v2.8.0）。"""
    user = db.session.get(User, session.get("user_id"))
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12
    query = Post.query.filter_by(author_id=user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if status == "published":
        query = query.filter(Post.published == True, Post.scheduled_at.is_(None))
    elif status == "draft":
        query = query.filter(Post.published == False, Post.scheduled_at.is_(None))
    elif status == "scheduled":
        query = query.filter(Post.scheduled_at.isnot(None), Post.published == False)
    elif status == "pinned":
        query = query.filter(Post.is_pinned == True)
    pagination = query.order_by(Post.is_pinned.desc(), Post.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return render_template("admin/my_posts.html", posts=pagination.items,
                           pagination=pagination, filter_q=q, filter_status=status)


@admin_bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能编辑自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    if request.method == "POST":
        was_published = post.published
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("标题不能为空")
            return render_template("admin/edit_post.html", post=post)
        post.title = title
        if make_slug(title) != post.slug:
            post.slug = unique_slug(title, post.id)
        post.summary = (request.form.get("summary") or "").strip()
        post.content = request.form.get("content", "")
        post.cover = (request.form.get("cover") or "").strip()
        cid = request.form.get("category_id") or None
        post.category_id = int(cid) if cid else None
        sid = request.form.get("series_id") or None
        post.series_id = int(sid) if sid else None
        scheduled_at = _parse_scheduled(request.form.get("scheduled_at"))
        published = request.form.get("published") == "on"
        # 定时发布：填了未来时间则先存为未发布，后台线程到点自动翻 published
        if scheduled_at is not None and scheduled_at > datetime.datetime.utcnow():
            published = False
        else:
            scheduled_at = None  # 立即发布/草稿：清空定时，避免历史脏值
        post.published = published
        post.scheduled_at = scheduled_at
        # 置顶权限分层（v2.8.1）：仅管理员/超管可改置顶；普通用户即便提交 is_pinned 也被忽略（防绕过）
        if user.is_admin_role:
            post.is_pinned = request.form.get("is_pinned") == "on"
            post.pin_requested = False  # 管理员直接操作置顶，无需申请态
        post.seo_description = (request.form.get("seo_description") or "").strip()
        post.seo_keywords = (request.form.get("seo_keywords") or "").strip()
        # v3.0.0 功能13/14：隐私空间 + 打赏（仅超管可设置）
        if user.is_super:
            post.is_private = request.form.get("is_private") == "on"
            post.reward_enabled = request.form.get("reward_enabled") == "on"
            if post.reward_enabled:
                post.reward_qr = (request.form.get("reward_qr") or "").strip()
            else:
                post.reward_qr = ""
        # v3.0.0 功能12：字数统计 + 阅读时长
        wc, rm = count_words(post.content)
        post.word_count = wc
        post.reading_minutes = rm
        _sync_tags(post, request.form.get("tags", ""))
        # v3.0.0 功能5：内容/标题有变化时保存版本历史
        if post.content != content or post.title != title:
            _save_post_history(post, user.username if user else "")
        post.content = content
        post.title = title
        db.session.commit()
        try:
            fts.sync_post(post)
        except Exception:
            pass
        if post.published and not was_published:
            try:
                notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
            except Exception:
                pass
            # C3 邮件群发：草稿转发布时也通知订阅者
            try:
                mail_notify.notify_subscribers_async(post)
            except Exception:
                pass
        if scheduled_at is not None and not published:
            flash("已更新为定时发布，到点自动公开")
        else:
            flash("已保存修改")
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    tag_names = ", ".join(t.name for t in post.tags)
    # scheduled_at 转 datetime-local 输入框格式（YYYY-MM-DDTHH:MM）；按 UTC 显示
    scheduled_local = ""
    if post.scheduled_at:
        scheduled_local = post.scheduled_at.strftime("%Y-%m-%dT%H:%M")
    return render_template("admin/edit_post.html", post=post, cats=cats, series=series,
                           tag_names=tag_names, scheduled_local=scheduled_local,
                           now_local=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M"),
                           current_user=user)


@admin_bp.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    """删除文章（v3.0.0 软删除：进入回收站，可还原）。

    权限：管理员全部可操作；普通用户仅自己文章。删除时把文章快照存入回收站
    （RecycleBin）并标记 post.in_trash=True（前台/列表不可见），不真正从 post 表移除。
    彻底删除请在回收站页操作（仅管理员）。
    """
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能删除自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    # 入回收站：存快照 + 标记软删除
    try:
        db.session.add(RecycleBin(
            post_id=post.id, title=post.title or "", slug=post.slug or "",
            summary=post.summary or "", content=post.content or "", cover=post.cover or "",
            category_id=post.category_id, author_id=post.author_id, series_id=post.series_id,
            deleted_by=user.username if user else "",
        ))
    except Exception:
        pass
    post.in_trash = True
    post.deleted_at = datetime.datetime.utcnow()
    db.session.commit()
    try:
        fts.delete_post(post.id)  # 同步从 FTS 索引移除，避免搜索命中已删文章
    except Exception:
        pass
    log_audit("delete", "post", post.id, f"移入回收站：{post.title}", user=user)
    flash("文章已移入回收站（可在回收站还原）")
    return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                    else url_for("admin.dashboard"))


# ---------- 回收站（v3.0.0 功能5）----------
@admin_bp.route("/recycle-bin")
@login_required
@admin_required
def recycle_bin():
    """回收站列表：展示被软删除的文章，可还原或彻底删除。"""
    rows = RecycleBin.query.filter_by(restored=False).order_by(RecycleBin.created_at.desc()).all()
    return render_template("admin/recycle_bin.html", rows=rows)


@admin_bp.route("/recycle-bin/<int:rid>/restore", methods=["POST"])
@login_required
@admin_required
def restore_post(rid):
    """从回收站还原：找到原 post（未被彻底删除）则清 in_trash；否则用快照重建。"""
    rb = RecycleBin.query.get_or_404(rid)
    if rb.restored:
        flash("该记录已还原过")
        return redirect(url_for("admin.recycle_bin"))
    post = None
    if rb.post_id:
        post = Post.query.get(rb.post_id)
    if post and post.in_trash:
        post.in_trash = False
        post.deleted_at = None
        db.session.commit()
        log_audit("restore", "post", post.id, f"从回收站还原：{rb.title}", user=_current_user_or_none())
        flash(f"已还原文章：{rb.title}")
    else:
        # 原 post 已彻底删除或不存在：用快照重建一篇新文章
        new_post = Post(
            title=rb.title, slug=unique_slug(rb.title + "-" + str(rb.id)),
            summary=rb.summary, content=rb.content, cover=rb.cover,
            category_id=rb.category_id, published=False, author_id=rb.author_id,
            series_id=rb.series_id,
        )
        db.session.add(new_post)
        db.session.flush()
        try:
            fts.sync_post(new_post)
        except Exception:
            pass
        log_audit("restore", "post", new_post.id, f"从回收站快照重建：{rb.title}", user=_current_user_or_none())
        flash(f"已用快照重建文章：{rb.title}（草稿状态，请检查后发布）")
    rb.restored = True
    db.session.commit()
    return redirect(url_for("admin.recycle_bin"))


@admin_bp.route("/recycle-bin/<int:rid>/purge", methods=["POST"])
@login_required
@admin_required
def purge_post(rid):
    """彻底删除：从 post 表真正移除（若仍在）+ 删除回收站记录 + 删 FTS。"""
    rb = RecycleBin.query.get_or_404(rid)
    if rb.post_id:
        post = Post.query.get(rb.post_id)
        if post:
            try:
                fts.delete_post(post.id)
            except Exception:
                pass
            db.session.delete(post)
    db.session.delete(rb)
    db.session.commit()
    log_audit("purge", "post", rb.post_id, f"彻底删除：{rb.title}", user=_current_user_or_none())
    flash(f"已彻底删除：{rb.title}")
    return redirect(url_for("admin.recycle_bin"))


# ---------- 文章版本历史（v3.0.0 功能5）----------
@admin_bp.route("/post/<int:post_id>/history")
@login_required
def post_history(post_id):
    """查看某文章的版本历史列表（可对比 / 回滚）。"""
    post = Post.query.get_or_404(post_id)
    user = _current_user_or_none()
    if not _can_edit_post(user, post):
        flash("只能查看自己文章的版本历史")
        return redirect(url_for("admin.my_posts"))
    versions = PostHistory.query.filter_by(post_id=post_id)\
        .order_by(PostHistory.created_at.desc()).all()
    return render_template("admin/post_history.html", post=post, versions=versions)


@admin_bp.route("/post/<int:post_id>/history/<int:hid>/rollback", methods=["POST"])
@login_required
def rollback_post(post_id, hid):
    """把文章回滚到指定历史版本（写回 title/summary/content 并保存新历史）。"""
    post = Post.query.get_or_404(post_id)
    user = _current_user_or_none()
    if not _can_edit_post(user, post):
        flash("只能回滚自己文章的版本")
        return redirect(url_for("admin.my_posts"))
    h = PostHistory.query.filter_by(id=hid, post_id=post_id).first_or_404()
    # 回滚前先存当前版本，便于再撤销回滚
    _save_post_history(post, user.username if user else "")
    post.title = h.title
    post.summary = h.summary
    post.content = h.content
    db.session.commit()
    try:
        fts.sync_post(post)
    except Exception:
        pass
    log_audit("rollback", "post", post.id, f"回滚到版本 {hid}", user=user)
    flash("已回滚到该历史版本")
    return redirect(url_for("admin.post_history", post_id=post_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# v3.1.6 高优：上传文件魔数（magic bytes）校验，不只依赖后缀名。
# 魔数表：png/jpg/jpeg/gif/webp 的真实文件头。不匹配即拒绝，防伪装成图片的脚本/HTML 上传。
_MAGIC_PATTERNS = {
    b"\x89PNG\r\n\x1a\n": ("png", "png"),
    b"\xff\xd8\xff": ("jpg", "jpeg"),
    b"GIF87a": ("gif", "gif"),
    b"GIF89a": ("gif", "gif"),
    b"RIFF": ("webp", None),  # RIFF....WEBP：进一步精验
}


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


@admin_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """接收后台上传的图片，保存到 static/uploads，返回可访问的 URL。

    v3.1.6 安全加固：不仅要后缀名在白名单，还须校验文件内容魔数（magic bytes），
    防「伪装成 .png/.jpg 的脚本或 HTML」上传后被访问执行（XSS/钓鱼）。
    """
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "只支持 png/jpg/jpeg/gif/webp 图片"}), 400
    # v3.1.6：读文件头 16 字节做魔数校验（不落盘判断，防后缀伪装）
    header = file.stream.read(16)
    file.stream.seek(0)  # 读完回卷，让 file.save 能从头保存
    if not _detect_image_magic(header, file.filename.rsplit(".", 1)[1].lower()):
        return jsonify({"error": "文件内容与图片格式不符，已拒绝（仅允许真实图片）"}), 400
    filename = secure_filename(file.filename)
    # 用时间戳前缀避免重名覆盖
    filename = f"{int(time.time())}-{filename}"
    save_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    file.save(save_path)
    # 图片优化：体积较大时转 WebP 省流量（Pillow 未装则零依赖降级，保持原格式）
    try:
        from app import maybe_convert_webp
        new_path = maybe_convert_webp(save_path)
        if new_path != save_path:
            filename = os.path.basename(new_path)
    except Exception:
        pass
    url = url_for("static", filename=f"uploads/{filename}")
    return jsonify({"url": url})


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


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Category(name=name, slug=make_slug(name)))
            db.session.commit()
            flash("分类已添加")
        return redirect(url_for("admin.categories"))
    cats = Category.query.order_by(Category.id).all()
    return render_template("admin/categories.html", cats=cats)


@admin_bp.route("/category/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_category(cid):
    cat = Category.query.get_or_404(cid)
    db.session.delete(cat)
    db.session.commit()
    flash("分类已删除")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/tags", methods=["GET", "POST"])
@admin_required
def tags():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Tag(name=name, slug=make_slug(name)))
            db.session.commit()
            flash("标签已添加")
        return redirect(url_for("admin.tags"))
    tags = Tag.query.order_by(Tag.id).all()
    return render_template("admin/tags.html", tags=tags)


@admin_bp.route("/tag/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_tag(tid):
    tag = Tag.query.get_or_404(tid)
    db.session.delete(tag)
    db.session.commit()
    flash("标签已删除")
    return redirect(url_for("admin.tags"))


@admin_bp.route("/links", methods=["GET", "POST"])
@admin_required
def links():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        url = (request.form.get("url") or "").strip()
        if name and url:
            db.session.add(FriendLink(
                name=name, url=url,
                description=(request.form.get("description") or "").strip(),
                sort=request.form.get("sort", 0, type=int),
                rss_url=(request.form.get("rss_url") or "").strip(),
            ))
            db.session.commit()
            flash("友链已添加")
        return redirect(url_for("admin.links"))
    links = FriendLink.query.order_by(FriendLink.sort).all()
    return render_template("admin/links.html", links=links)


@admin_bp.route("/link/<int:lid>/rss", methods=["POST"])
@admin_required
def set_link_rss(lid):
    """保存某条友链的 RSS 地址（用于「博客圈」聚合）。"""
    link = FriendLink.query.get_or_404(lid)
    link.rss_url = (request.form.get("rss_url") or "").strip()
    db.session.commit()
    flash("已保存 RSS 地址")
    return redirect(url_for("admin.links"))


@admin_bp.route("/link/<int:lid>/delete", methods=["POST"])
@admin_required
def delete_link(lid):
    link = FriendLink.query.get_or_404(lid)
    db.session.delete(link)
    db.session.commit()
    flash("友链已删除")
    return redirect(url_for("admin.links"))


# ---------- 友情链接自助申请审核（v3.0.0 功能6）----------
@admin_bp.route("/link-applications")
@admin_required
def link_applications():
    """友链申请列表：默认看待审核，可按状态筛选。"""
    status = request.args.get("status", "pending")
    q = LinkApplication.query
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(LinkApplication.created_at.desc()).all()
    pending_count = LinkApplication.query.filter_by(status="pending").count()
    return render_template("admin/link_applications.html", rows=rows,
                           status=status, pending_count=pending_count)


@admin_bp.route("/link-application/<int:aid>/approve", methods=["POST"])
@admin_required
def approve_link_application(aid):
    """通过友链申请：写入 FriendLink 列表，标记申请为 approved。"""
    app_row = LinkApplication.query.get_or_404(aid)
    if app_row.status != "approved":
        # 写入友链表（避免重复：同 URL 已存在则跳过）
        existing = FriendLink.query.filter_by(url=app_row.url).first()
        if not existing:
            db.session.add(FriendLink(name=app_row.name, url=app_row.url,
                                      description=app_row.description or "",
                                      sort=99))
        app_row.status = "approved"
        app_row.reviewer = (_current_user_or_none().username if _current_user_or_none() else "")
        app_row.reviewed_at = datetime.datetime.utcnow()
        db.session.commit()
        log_audit("approve", "link_application", aid, f"通过友链申请：{app_row.name}", user=_current_user_or_none())
        flash(f"已通过友链申请：{app_row.name}")
    return redirect(url_for("admin.link_applications"))


@admin_bp.route("/link-application/<int:aid>/reject", methods=["POST"])
@admin_required
def reject_link_application(aid):
    """拒绝友链申请：仅标记状态，不写入友链表。"""
    app_row = LinkApplication.query.get_or_404(aid)
    app_row.status = "rejected"
    app_row.reviewer = (_current_user_or_none().username if _current_user_or_none() else "")
    app_row.reviewed_at = datetime.datetime.utcnow()
    note = (request.form.get("note") or "").strip()
    if note:
        app_row.review_note = note
    db.session.commit()
    log_audit("reject", "link_application", aid, f"拒绝友链申请：{app_row.name}", user=_current_user_or_none())
    flash(f"已拒绝友链申请：{app_row.name}")
    return redirect(url_for("admin.link_applications"))


@admin_bp.route("/social", methods=["GET", "POST"])
@admin_required
def social():
    """社交账号管理（广场页「我的社交账号」墙）。"""
    if request.method == "POST":
        platform = (request.form.get("platform") or "").strip()
        url = (request.form.get("url") or "").strip()
        if platform and url:
            db.session.add(SocialAccount(
                platform=platform,
                handle=(request.form.get("handle") or "").strip(),
                url=url,
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("社交账号已添加")
        return redirect(url_for("admin.social"))
    accounts = SocialAccount.query.order_by(SocialAccount.sort).all()
    return render_template("admin/social.html", accounts=accounts)


@admin_bp.route("/social/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_social(aid):
    acc = SocialAccount.query.get_or_404(aid)
    db.session.delete(acc)
    db.session.commit()
    flash("社交账号已删除")
    return redirect(url_for("admin.social"))


@admin_bp.route("/comments", methods=["GET"])
@admin_required
def comments():
    # 审核流：支持 ?status=pending 只看待审核
    status = request.args.get("status", "")
    q = Comment.query
    if status == "pending":
        q = q.filter_by(approved=False)
    elif status == "approved":
        q = q.filter_by(approved=True)
    rows = q.order_by(Comment.created_at.desc()).all()
    pending_count = Comment.query.filter_by(approved=False).count()
    return render_template("admin/comments.html", comments=rows, status=status, pending_count=pending_count)


@admin_bp.route("/comment/<int:cid>/approve", methods=["POST"])
@admin_required
def approve_comment(cid):
    """审核通过评论。"""
    c = Comment.query.get_or_404(cid)
    c.approved = True
    db.session.commit()
    flash("评论已通过审核")
    return redirect(url_for("admin.comments", status="pending"))


@admin_bp.route("/comment/<int:cid>/reject", methods=["POST"])
@admin_required
def reject_comment(cid):
    """驳回评论（删除，相当于拒绝显示）。"""
    c = Comment.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("评论已驳回并删除")
    return redirect(url_for("admin.comments", status="pending"))


@admin_bp.route("/comment/<int:cid>/read", methods=["POST"])
@admin_required
def mark_comment_read(cid):
    """单条评论标记为已读。"""
    c = Comment.query.get_or_404(cid)
    c.is_read = True
    db.session.commit()
    return redirect(url_for("admin.comments"))


@admin_bp.route("/comments/read-all", methods=["POST"])
@admin_required
def mark_all_comments_read():
    """全部评论标记为已读。"""
    Comment.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("全部评论已标记为已读")
    return redirect(url_for("admin.comments"))


@admin_bp.route("/comment/<int:cid>/delete", methods=["POST"])
@admin_required
def delete_comment(cid):
    c = Comment.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("评论已删除")
    return redirect(url_for("admin.comments"))


# ---------- 评论批量管理（v3.0.0 功能2）----------
@admin_bp.route("/comments/batch-approve", methods=["POST"])
@admin_required
def batch_approve_comments():
    """批量通过评论：表单传入待审 comment id 列表（name=ids，多选）。"""
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if not ids:
        flash("请先勾选要通过的评论")
        return redirect(url_for("admin.comments"))
    approved = 0
    for cid in ids:
        c = Comment.query.get(cid)
        if c and not c.approved:
            c.approved = True
            approved += 1
    db.session.commit()
    log_audit("batch_approve", "comment", None, f"批量通过 {approved} 条评论", user=_current_user_or_none())
    flash(f"已批量通过 {approved} 条评论")
    return redirect(url_for("admin.comments"))


@admin_bp.route("/comments/batch-delete", methods=["POST"])
@admin_required
def batch_delete_comments():
    """批量删除评论：表单传入 comment id 列表（name=ids，多选）。"""
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if not ids:
        flash("请先勾选要删除的评论")
        return redirect(url_for("admin.comments"))
    deleted = 0
    for cid in ids:
        c = Comment.query.get(cid)
        if c:
            db.session.delete(c)
            deleted += 1
    db.session.commit()
    log_audit("batch_delete", "comment", None, f"批量删除 {deleted} 条评论", user=_current_user_or_none())
    flash(f"已批量删除 {deleted} 条评论")
    return redirect(url_for("admin.comments"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@super_required
def settings():
    if request.method == "POST":
        fields = ["site_title", "site_name", "site_note", "site_description", "about_content", "footer_text",
                  "beian_code", "weather_lat", "weather_lon", "weather_city",
                  "accent_color",
                  "theme_mode", "theme_radius", "theme_font", "nav_style", "custom_css",
                  # v3.0.0 功能2：垃圾评论关键词（逗号分隔）；功能11：前台默认语言
                  "comment_spam_keywords", "site_lang", "reward_qr_default"]
        for f in fields:
            val = request.form.get(f, "")
            row = Setting.query.filter_by(key=f).first()
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=f, value=val))
        # 评论审核开关（checkbox：勾选=true，不勾选=空）
        cap = Setting.query.filter_by(key="comment_require_approval").first()
        cap_val = "true" if request.form.get("comment_require_approval") else "false"
        if cap:
            cap.value = cap_val
        else:
            db.session.add(Setting(key="comment_require_approval", value=cap_val))
        db.session.commit()
        flash("站点设置已保存")
        return redirect(url_for("admin.settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=settings)


@admin_bp.route("/captcha-settings", methods=["GET", "POST"])
@super_required
def captcha_settings():
    """验证码独立设置页（v3.2.0）：全局开关 + 长度 + 难度 + 排除易混字符 + 各场景开关，存 Setting 表。"""
    keys = ["captcha_enabled", "captcha_length", "captcha_difficulty", "captcha_exclude_ambiguous",
            "captcha_on_register", "captcha_on_comment", "captcha_on_guestbook"]
    bool_keys = {"captcha_enabled", "captcha_exclude_ambiguous",
                 "captcha_on_register", "captcha_on_comment", "captcha_on_guestbook"}
    if request.method == "POST":
        for k in keys:
            val = "true" if (k in bool_keys and request.form.get(k)) else (
                request.form.get(k, "").strip() if k not in bool_keys else "false")
            row = Setting.query.filter_by(key=k).first()
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=k, value=val))
        db.session.commit()
        flash("验证码设置已保存")
        return redirect(url_for("admin.captcha_settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    defaults = {
        "captcha_enabled": "true", "captcha_length": "4", "captcha_difficulty": "normal",
        "captcha_exclude_ambiguous": "true", "captcha_on_register": "true",
        "captcha_on_comment": "true", "captcha_on_guestbook": "true",
    }
    for k, v in defaults.items():
        settings.setdefault(k, v)
    from security import get_captcha_config
    return render_template("admin/captcha_settings.html", settings=settings,
                           captcha_cfg=get_captcha_config())


@admin_bp.route("/backup", methods=["GET", "POST"])
@super_required
def backup():
    """数据备份管理（v3.3.0）：列表 / 立即备份 / 下载 / 恢复。

    恢复是高危操作：仅超管（@super_required）+ 全局 CSRF 校验 + 表单二次确认
    （confirm=yes）+ 恢复前自动快照 + 写审计日志。密钥只走环境变量，页面不回显。
    """
    import backup as backup_mod
    remote_status = {
        "local_dir": backup_mod.BACKUP_ROOT,
        "oss": bool(os.environ.get("BACKUP_OSS_BUCKET")),
        "scp": bool(os.environ.get("BACKUP_SCP_HOST")),
        "webdav": bool(os.environ.get("BACKUP_WEBDAV_URL")),
    }
    backups = backup_mod.list_backups()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "backup_now":
            try:
                arc, man, sync = backup_mod.create_backup()
                msg = "备份成功：%s（%d 个文件）" % (os.path.basename(arc), man["file_count"])
                for name, ok, s in sync:
                    msg += "；远程[%s]%s" % (name, "✅" if ok else "⚠️" + s)
                add_audit("backup", target="创建备份", detail=msg, success=True)
                flash(msg)
            except Exception as e:
                add_audit("backup", target="创建备份", detail=str(e)[:200], success=False)
                flash("备份失败：" + str(e)[:200])
            return redirect(url_for("admin.backup"))
        fn = request.form.get("file", "")
        fp = os.path.join(backup_mod.BACKUP_ROOT, fn) if fn else ""
        safe = bool(fn and os.path.basename(fn) == fn and fn.startswith("blog_backup_")
                    and os.path.exists(fp))
        if action == "download":
            if safe:
                return send_file(fp, as_attachment=True, download_name=fn)
            flash("备份文件不存在")
            return redirect(url_for("admin.backup"))
        if action == "restore":
            if request.form.get("confirm") != "yes":
                flash("恢复是高危操作，需勾选二次确认")
                return redirect(url_for("admin.backup"))
            if not safe:
                flash("备份文件不存在")
                return redirect(url_for("admin.backup"))
            try:
                r = backup_mod.restore(fp, yes=True, tag="admin")
                flash("已从 %s 恢复（恢复前快照 %s）。请到宝塔「停止」再「启动」站点使数据库生效。"
                      % (fn, os.path.basename(r["snapshot"])))
                add_audit("backup_restore", target="恢复备份", target_id=fn,
                          detail="快照 %s" % os.path.basename(r["snapshot"]), success=True)
            except Exception as e:
                add_audit("backup_restore", target="恢复备份", target_id=fn,
                          detail=str(e)[:200], success=False)
                flash("恢复失败：" + str(e)[:200])
            return redirect(url_for("admin.backup"))
    return render_template("admin/backup.html", backups=backups, remote_status=remote_status,
                           retention=backup_mod.RETENTION_DAYS)


@admin_bp.route("/email-settings", methods=["GET", "POST"])
@super_required
def email_settings():
    """邮件群发设置（C3）：SMTP 配置存 Setting 表，mail_notify.py 读取时优先库值、回退环境变量。
    密码不回显：保存时密码留空 = 保持不变。提供「发送测试邮件」验证配置。
    """
    from utils import rate_limit, client_key
    mail_keys = ["mail_host", "mail_port", "mail_username", "mail_password", "mail_from", "mail_use_ssl"]
    if request.method == "POST":
        action = request.form.get("action", "save")
        # 保存配置
        if action == "save":
            host = (request.form.get("mail_host") or "").strip()
            vals = {
                "mail_host": host,
                "mail_port": (request.form.get("mail_port") or "465").strip() or "465",
                "mail_username": (request.form.get("mail_username") or "").strip(),
                "mail_from": (request.form.get("mail_from") or "").strip(),
                "mail_use_ssl": "true" if request.form.get("mail_use_ssl") else "false",
            }
            # 密码：仅当输入了非空值才更新（不回显、留空保持原值）
            pwd = request.form.get("mail_password") or ""
            if pwd.strip():
                vals["mail_password"] = pwd.strip()
            for k, v in vals.items():
                row = Setting.query.filter_by(key=k).first()
                if row:
                    row.value = v
                else:
                    db.session.add(Setting(key=k, value=v))
            db.session.commit()
            flash("邮件设置已保存")
            return redirect(url_for("admin.email_settings"))
        # 发送测试邮件（限流防滥用）
        if action == "test":
            if not rate_limit(client_key("admin_mail_test"), limit=5, window=300):
                flash("测试邮件发送过于频繁，请 5 分钟后再试", "error")
                return redirect(url_for("admin.email_settings"))
            to = (request.form.get("test_to") or "").strip()
            if not to:
                flash("请填写测试收件人邮箱", "error")
                return redirect(url_for("admin.email_settings"))
            # 用表单当前值（含新填密码）+ 库中已存值组装测试配置，不落库
            import mail_notify
            cfg = mail_notify.load_mail_config()
            cfg["host"] = (request.form.get("mail_host") or cfg["host"]).strip()
            cfg["port"] = int((request.form.get("mail_port") or str(cfg["port"])).strip() or 465)
            cfg["username"] = (request.form.get("mail_username") or cfg["username"]).strip()
            cfg["from"] = (request.form.get("mail_from") or cfg["from"]).strip()
            if request.form.get("mail_use_ssl") is not None:
                cfg["use_ssl"] = True
            pwd = request.form.get("mail_password") or ""
            if pwd.strip():
                cfg["password"] = pwd.strip()
            ok = mail_notify.send_test_mail(cfg, to)
            if ok:
                flash(f"测试邮件已发送到 {to}，请查收（含垃圾箱）")
            else:
                flash("发送失败：请检查 SMTP 配置（主机/端口/授权码/SSL 开关），错误详情见后端日志", "error")
            return redirect(url_for("admin.email_settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/email_settings.html", settings=settings)


@admin_bp.route("/stats")
@admin_required
def stats():
    """访问统计页（服务端渲染，含区域/时段/热读/常搜图表）。"""
    from stats import compute_summary
    summary = compute_summary()
    # 时段分布转成带百分比的行，供模板画横向条形图
    total_hour = sum(b["count"] for b in summary["hourly"]) or 1
    max_hour = max([b["count"] for b in summary["hourly"]] or [1]) or 1
    for b in summary["hourly"]:
        b["pct"] = round(b["count"] * 100 / max_hour)
    max_region = max([r["count"] for r in summary["regions_all"]] or [1]) or 1
    for r in summary["regions_all"]:
        r["pct"] = round(r["count"] * 100 / max_region)
    max_reads = max([p["reads"] for p in summary["hot_posts"]] or [1]) or 1
    for p in summary["hot_posts"]:
        p["pct"] = round(p["reads"] * 100 / max_reads)
    max_search = max([s["count"] for s in summary["hot_searches"]] or [1]) or 1
    for s in summary["hot_searches"]:
        s["pct"] = round(s["count"] * 100 / max_search)
    return render_template("admin/stats.html", summary=summary)


@admin_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """修改当前登录用户的密码（需验证原密码）。"""
    user = db.session.get(User, session["user_id"])
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not user.check_password(old):
            flash("原密码错误")
        elif _weak_password(new):
            flash(_weak_password(new))
        elif new != confirm:
            flash("两次输入的新密码不一致")
        else:
            user.set_password(new)
            user.session_version = (user.session_version or 0) + 1  # v3.1.6：改密码销毁全部旧会话
            db.session.commit()
            # 销毁当前会话，强制用新密码重新登录（含其它已登录设备一并失效）
            session.clear()
            flash("密码修改成功，所有旧会话已失效，请使用新密码重新登录")
            return redirect(url_for("admin.login"))
    return render_template("admin/change_password.html")


# ---------- 用户管理（仅超级管理员）----------
@admin_bp.route("/users")
@login_required
@super_required
def users():
    rows = User.query.order_by(User.role, User.id).all()
    return render_template("admin/users.html", users=rows)


@admin_bp.route("/users/add", methods=["POST"])
@login_required
@super_required
def add_user():
    """新增用户：超级管理员可建管理员/普通用户。"""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", ROLE_USER)
    if not username or not password:
        flash("用户名和密码不能为空")
    elif User.query.filter_by(username=username).first():
        flash("用户名已存在")
    elif role not in (ROLE_ADMIN, ROLE_USER):
        flash("无效的角色")
    elif _weak_password(password):
        flash(_weak_password(password))
    else:
        u = User(username=username, role=role, email=(request.form.get("email") or "").strip())
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash(f"已创建用户 {username}（{u.role_label}）")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/role", methods=["POST"])
@login_required
@super_required
def set_role(uid):
    """调整用户角色。规则：不能改自己的角色；不能把超级管理员降级；至少保留一个超级管理员。"""
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    if target.id == session["user_id"]:
        flash("不能修改自己的角色")
        return redirect(url_for("admin.users"))
    if target.is_super:
        flash("不能修改超级管理员的角色")
        return redirect(url_for("admin.users"))
    role = request.form.get("role", ROLE_USER)
    if role not in (ROLE_ADMIN, ROLE_USER):
        flash("无效的角色")
        return redirect(url_for("admin.users"))
    target.role = role
    db.session.commit()
    flash(f"{target.username} 的角色已改为 {target.role_label}")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/password", methods=["POST"])
@login_required
@super_required
def reset_password(uid):
    """超级管理员重置任意用户密码（超级管理员本身除外，他应自己改）。"""
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    if target.is_super:
        flash("超级管理员的密码请使用「修改密码」自行修改")
        return redirect(url_for("admin.users"))
    new = request.form.get("new_password", "")
    if _weak_password(new):
        flash(_weak_password(new))
    else:
        target.set_password(new)
        target.session_version = (target.session_version or 0) + 1  # v3.1.6：重置密码同样销毁旧会话
        db.session.commit()
        flash(f"已重置 {target.username} 的密码（其旧会话已全部失效）")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/kick", methods=["POST"])
@login_required
@super_required
def kick_user(uid):
    """超管踢下线（v3.1.6 中优·会话管理）：使目标用户所有会话立即失效（session_version+1），
    不清除密码、不删除账号。超级管理员本人不可被踢（避免误操作锁死自己）。"""
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    if target.is_super:
        flash("超级管理员不能被踢下线（请直接改密码注销旧会话）")
        return redirect(url_for("admin.users"))
    ver = target.bump_session_version()
    db.session.commit()
    log_audit("kick", "user", uid, f"踢下线用户：{target.username}（会话版本 {ver}）", user=_current_user_or_none())
    flash(f"已踢下线：{target.username}，其所有登录会话已失效")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/delete", methods=["POST"])
@login_required
@super_required
def delete_user(uid):
    """删除用户。超级管理员不能被删除（包括自己）。"""
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    if target.is_super:
        flash("超级管理员不能被删除")
        return redirect(url_for("admin.users"))
    db.session.delete(target)
    db.session.commit()
    flash(f"已删除用户 {target.username}")
    return redirect(url_for("admin.users"))


# ---------- 后台操作日志（审计 trail，v3.0.0 功能4）----------
@admin_bp.route("/audit-logs")
@login_required
@super_required
def audit_logs():
    """操作日志列表（仅超管可见）：分页展示，按时间倒序。

    v3.1.6 中优：支持 ?from= / ?to= 时间筛选（导出与页面共用同一过滤）。
    """
    from flask import request as _req
    q, frm, to = _audit_log_query_with_filters()
    page = _req.args.get("page", 1, type=int)
    pagination = q.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False)
    try:
        from flask import current_app as _app
        keep_days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        keep_days = 90
    from utils import csrf_input as _csrf_input  # 模板用 {{ csrf_input() }}
    return render_template("admin/audit_logs.html", logs=pagination.items,
                           pagination=pagination, filter_from=frm, filter_to=to,
                           keep_days=keep_days, csrf_input=_csrf_input)


@admin_bp.route("/audit-logs/export")
@login_required
@super_required
def export_audit_logs():
    """打包下载审计日志（v3.1.0 新增；v3.1.6 中优支持 ?from=/&to= 时间筛选）：
    生成 CSV + 可读 TXT 的 zip，内存打包不落盘。"""
    import io
    import csv
    import zipfile
    import datetime as _dt
    q, frm, to = _audit_log_query_with_filters()
    logs = q.order_by(AuditLog.created_at.desc()).all()

    # ---- CSV 公式注入防护 ----
    # 单元格以 = + - @ 开头时，Excel/Numbers 会当成公式执行（如 "=cmd|..." 或 "=1+1"），
    # 攻击者可通过审计日志里用户可控字段（用户名/说明）注入。前缀单引号可 neutral 化。
    def _csv_guard(v):
        s = "" if v is None else str(v)
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
            return "'" + s
        return s

    # ---- CSV ----
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["时间", "操作人", "动作", "对象", "结果", "说明", "来源IP"])
    for l in logs:
        writer.writerow([
            _csv_guard(l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""),
            _csv_guard(l.username or ""),
            _csv_guard(l.action or ""),
            _csv_guard((l.target or "") + (f"#{l.target_id}" if l.target_id else "")),
            "成功" if l.success else "失败",
            _csv_guard(l.detail or ""),
            _csv_guard(l.ip or ""),
        ])
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")  # BOM 让 Excel 正确识别中文

    # ---- TXT（人类可读）----
    try:
        from flask import current_app as _app
        keep_days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        keep_days = 90
    scope = f"时间范围：{frm or '起始'} → {to or '最新'}" if (frm or to) else f"保留 {keep_days} 天内的全部记录"
    lines = ["llhhy-blog 后台审计日志导出", "生成时间：" + _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "共 %d 条记录（%s）" % (len(logs), scope), "=" * 60]
    for l in logs:
        ts = l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "?"
        obj = (l.target or "") + (f"#{l.target_id}" if l.target_id else "")
        res = "成功" if l.success else "失败"
        lines.append(f"[{ts}] {l.username or '—'} {l.action} {obj} {res} | {l.detail or ''} | IP:{l.ip or '—'}")
    txt_bytes = ("\n".join(lines)).encode("utf-8")

    # ---- 内存打包 zip ----
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit_logs.csv", csv_bytes)
        zf.writestr("audit_logs.txt", txt_bytes)
    zip_buf.seek(0)

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"audit_logs_{stamp}.zip",
    )


@admin_bp.route("/audit-logs/clear", methods=["POST"])
@login_required
@super_required
def clear_audit_logs():
    """清空操作日志（谨慎操作，不可恢复）。保留最近 AUDIT_LOG_DAYS 天（v3.1.0；v3.1.6 保留周期可配）。"""
    try:
        from flask import current_app as _app
        days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        days = 90
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete()
    db.session.commit()
    log_audit("clear", "audit_log", None, f"清空 {days} 天前的审计日志 {deleted} 条", user=_current_user_or_none())
    flash(f"已清理 {deleted} 条 {days} 天前的旧日志（近 {days} 天记录保留）")
    return redirect(url_for("admin.audit_logs"))


# ---------- 文章系列 / 专栏管理（B4）----------
@admin_bp.route("/series", methods=["GET", "POST"])
@admin_required
def manage_series():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            db.session.add(Series(
                name=name, slug=make_slug(name),
                description=(request.form.get("description") or "").strip(),
                cover=(request.form.get("cover") or "").strip(),
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("系列已添加")
        return redirect(url_for("admin.manage_series"))
    series = Series.query.order_by(Series.sort, Series.created_at.desc()).all()
    return render_template("admin/series.html", series=series)


@admin_bp.route("/series/<int:sid>/delete", methods=["POST"])
@admin_required
def delete_series(sid):
    s = Series.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash("系列已删除")
    return redirect(url_for("admin.manage_series"))


# ---------- 站点公告管理（D4）----------
@admin_bp.route("/announcements", methods=["GET", "POST"])
@admin_required
def manage_announcements():
    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if content:
            db.session.add(Announcement(
                content=content,
                level=(request.form.get("level") or "info"),
                active=request.form.get("active", "on") == "on",
                dismissible=request.form.get("dismissible", "on") == "on",
            ))
            db.session.commit()
            flash("公告已添加")
        return redirect(url_for("admin.manage_announcements"))
    items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", items=items)


@admin_bp.route("/announcement/<int:aid>/toggle", methods=["POST"])
@admin_required
def toggle_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    a.active = not a.active
    db.session.commit()
    return redirect(url_for("admin.manage_announcements"))


@admin_bp.route("/announcement/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    flash("公告已删除")
    return redirect(url_for("admin.manage_announcements"))


# ---------- 留言墙管理（C1）----------
@admin_bp.route("/guestbook", methods=["GET"])
@admin_required
def manage_guestbook():
    rows = Guestbook.query.order_by(Guestbook.created_at.desc()).all()
    return render_template("admin/guestbook.html", rows=rows)


@admin_bp.route("/guestbook/<int:gid>/read", methods=["POST"])
@admin_required
def mark_guestbook_read(gid):
    """单条留言标记为已读。"""
    g = Guestbook.query.get_or_404(gid)
    g.is_read = True
    db.session.commit()
    return redirect(url_for("admin.manage_guestbook"))


@admin_bp.route("/guestbook/read-all", methods=["POST"])
@admin_required
def mark_all_guestbook_read():
    """全部留言标记为已读。"""
    Guestbook.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("全部留言已标记为已读")
    return redirect(url_for("admin.manage_guestbook"))


@admin_bp.route("/guestbook/<int:gid>/delete", methods=["POST"])
@admin_required
def delete_guestbook(gid):
    g = Guestbook.query.get_or_404(gid)
    db.session.delete(g)
    db.session.commit()
    flash("留言已删除")
    return redirect(url_for("admin.manage_guestbook"))


# ---------- 邮件订阅者管理（C3）----------
@admin_bp.route("/subscribers", methods=["GET"])
@admin_required
def manage_subscribers():
    rows = Subscriber.query.order_by(Subscriber.created_at.desc()).all()
    return render_template("admin/subscribers.html", rows=rows)


@admin_bp.route("/subscribers/delete/<int:sid>", methods=["POST"])
@admin_required
def delete_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    email = sub.email
    db.session.delete(sub)
    db.session.commit()
    flash(f"已删除订阅者：{email}")
    return redirect(url_for("admin.manage_subscribers"))


@admin_bp.route("/subscribers/toggle/<int:sid>", methods=["POST"])
@admin_required
def toggle_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    sub.active = not sub.active
    db.session.commit()
    flash(f"已{'启用' if sub.active else '停用'}订阅者：{sub.email}")
    return redirect(url_for("admin.manage_subscribers"))
