# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

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
    # 全量审计加固：用户名长度上限（模型层 username 字段 String(40)，入库前截断并提示）
    username = (request.form.get("username") or "").strip()[:40]
    password = request.form.get("password", "")
    role = request.form.get("role", ROLE_USER)
    if not username or not password:
        flash("用户名和密码不能为空")
    elif len(username) > 40:
        flash("用户名最长 40 字符")
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
