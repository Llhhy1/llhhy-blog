"""后台管理：登录、写文章、分类/标签/友链/设置/评论管理、修改密码、用户管理。"""
import functools
import os
import time

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, current_app, abort, jsonify)
from werkzeug.utils import secure_filename

from models import (db, Post, Category, Tag, Comment, FriendLink, Setting,
                    User, ROLE_SUPER, ROLE_ADMIN, ROLE_USER, SocialAccount,
                    Series, Announcement, Guestbook, Subscriber)
from utils import make_slug
from config import APP_VERSION
import fts
import notify
import mail_notify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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


def _can_edit_post(user, post):
    """判断当前用户能否编辑/删除该文章：管理员可编辑全部；普通用户只能编辑自己的。"""
    if user.is_admin_role:
        return True
    return post.author_id is not None and post.author_id == user.id


def unique_slug(base, post_id=None):
    """生成不重复的 slug，重复时追加 -2, -3 ..."""
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
            session["user_id"] = user.id
            if user.is_super and user.must_change_password:
                return redirect(url_for("admin.setup"))
            # 按角色分流
            return redirect(url_for("admin.dashboard") if user.is_admin_role
                            else url_for("admin.new_post"))
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
        elif len(new_password) < 6:
            flash("新密码至少 6 位")
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
                db.session.commit()
                flash("账号设置完成，欢迎使用后台！")
                return redirect(url_for("admin.dashboard"))
    return render_template("admin/setup.html", user=user)


@admin_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("admin", None)
    return redirect(url_for("main.index"))


@admin_bp.route("/")
@admin_required
def dashboard():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    pending = Comment.query.filter_by(approved=False).count()
    recent_comments = Comment.query.order_by(Comment.created_at.desc()).limit(6).all()
    from stats import compute_summary
    summary = compute_summary()
    return render_template("admin/dashboard.html", posts=posts, pending=pending,
                           summary=summary, recent_comments=recent_comments)


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
        series_id = request.form.get("series_id") or None
        post = Post(
            title=title, slug=unique_slug(title), summary=summary, content=content,
            cover=cover, category_id=category_id, published=published,
            series_id=int(series_id) if series_id else None,
            author_id=session.get("user_id"),  # 记录作者：普通用户发表的文章归属自己
        )
        db.session.add(post)
        db.session.flush()  # 先把文章放进会话，避免标签关联警告
        _sync_tags(post, request.form.get("tags", ""))
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
        flash("文章已发布" if published else "草稿已保存")
        # 普通用户发布后回到「我的文章」，管理员回仪表盘
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    return render_template("admin/edit_post.html", post=None, cats=cats, series=series)


@admin_bp.route("/my-posts")
@login_required
def my_posts():
    """「我的文章」：普通用户查看/管理自己发表的文章。"""
    user = db.session.get(User, session.get("user_id"))
    posts = Post.query.filter_by(author_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template("admin/my_posts.html", posts=posts)


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
        post.published = request.form.get("published") == "on"
        _sync_tags(post, request.form.get("tags", ""))
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
        flash("已保存修改")
        user = db.session.get(User, session.get("user_id"))
        return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                        else url_for("admin.dashboard"))
    cats = Category.query.order_by(Category.id).all()
    series = Series.query.order_by(Series.sort).all()
    tag_names = ", ".join(t.name for t in post.tags)
    return render_template("admin/edit_post.html", post=post, cats=cats, series=series, tag_names=tag_names)


@admin_bp.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session.get("user_id"))
    if not _can_edit_post(user, post):
        flash("只能删除自己发表的文章")
        return redirect(url_for("admin.my_posts"))
    try:
        fts.delete_post(post.id)
    except Exception:
        pass
    db.session.delete(post)
    db.session.commit()
    flash("文章已删除")
    user = db.session.get(User, session.get("user_id"))
    return redirect(url_for("admin.my_posts") if user and not user.is_admin_role
                    else url_for("admin.dashboard"))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


@admin_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """接收后台上传的图片，保存到 static/uploads，返回可访问的 URL。"""
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "只支持 png/jpg/jpeg/gif/webp 图片"}), 400
    filename = secure_filename(file.filename)
    # 用时间戳前缀避免重名覆盖
    filename = f"{int(time.time())}-{filename}"
    save_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(save_dir, exist_ok=True)
    file.save(os.path.join(save_dir, filename))
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


@admin_bp.route("/settings", methods=["GET", "POST"])
@super_required
def settings():
    if request.method == "POST":
        fields = ["site_title", "site_name", "site_note", "site_description", "about_content", "footer_text",
                  "beian_code", "weather_lat", "weather_lon", "weather_city",
                  "accent_color",
                  "theme_mode", "theme_radius", "theme_font", "nav_style", "custom_css"]
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
        elif len(new) < 6:
            flash("新密码至少 6 位")
        elif new != confirm:
            flash("两次输入的新密码不一致")
        else:
            user.set_password(new)
            db.session.commit()
            flash("密码修改成功，下次登录请使用新密码")
            return redirect(url_for("admin.dashboard"))
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
    elif len(password) < 6:
        flash("密码至少 6 位")
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
    if len(new) < 6:
        flash("新密码至少 6 位")
    else:
        target.set_password(new)
        db.session.commit()
        flash(f"已重置 {target.username} 的密码")
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
