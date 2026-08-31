# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

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
