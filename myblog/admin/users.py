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
    """停用用户（v3.21.2 审计：由「物理删行」改为「就地停用」）。

    为什么不能删行：`Post.author_id` 是**裸整数、不是外键**（`models.py:20`，注释里
    写明了原因），而 SQLite 在删掉最大 rowid 后会把它**复用**给下一个新用户。于是
    「删一个管理员曾经发过文的账号」= 把这些文章连 `author_id` 一起送给下一个注册者，
    而 `_can_edit_post()`（`admin/_helpers.py:112-116`）只比 `post.author_id == user.id`
    —— 新人因此获得编辑 / 删除 / 再发布旧人全部文章的权限。同类隐患还有
    `Notification` / `RecycleBin.author_id` / `OAuthAccount.user_id`（后者会留下孤儿
    绑定，OAuth 回调取到 None 后直接冒成 500）。
    保留行就一次性根除整类问题，且不需要改表结构。
    """
    target = db.session.get(User, uid)
    if not target:
        abort(404)
    if target.is_super:
        flash("超级管理员不能被删除")
        return redirect(url_for("admin.users"))
    me = _current_user_or_none()
    if me and me.id == target.id:
        flash("不能停用自己（请用「踢下线」或直接改密码）")
        return redirect(url_for("admin.users"))

    import secrets as _secrets
    from models import OAuthAccount
    name = target.username
    # 断开第三方绑定：否则该 sub 仍指向这个已废弃的行
    for acct in OAuthAccount.query.filter_by(user_id=target.id).all():
        db.session.delete(acct)
    target.role = ROLE_USER                    # 收回后台权限（is_admin_role 变 False）
    target.email = ""                          # 释放邮箱占用，避免后续误匹配
    target.username = "disabled_%d_%s" % (target.id, _secrets.token_hex(4))
    target.set_password(_secrets.token_urlsafe(48))   # 随机密码：无人能再用密码登录
    target.bump_session_version()                # 现有会话全部失效
    log_audit("disable", "user", target.id,
              f"停用用户：{name}（原 {target.id} 号行保留，防 id 复用继承其文章）",
              user=me)
    flash(f"已停用用户 {name}（其文章保留原归属；如需彻底清除，请先在文章里改作者或删除）")
    return redirect(url_for("admin.users"))
