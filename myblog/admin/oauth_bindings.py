# -*- coding: utf-8 -*-
"""后台「第三方账号绑定」管理（补 R94 §94.8-7 的可发现性缺口）。

背景（为什么必须有这一页）：v3.22.0 把 OAuth 认领既有账号的入口收敛为「本账号
已登录」之后，安全侧不再会被接管；但**历史上已经形成的绑定没有任何后台入口可查、
可解绑**——受害者只能改库自救。本模块提供「查看 + 解绑」，把自救路径补上。

设计取舍（都写下来，避免后人改回去）：

1. **默认只作用于当前登录账号**；超管可带 `?user_id=` 处理他人账号（救助受害者用），
   但同样要用**超管自己的密码**确认，并写审计。
2. **解绑必须输密码**——这不是形式，它同时是「该账号仍有可用登录方式」的证明。
   OAuth 新建的本地账号密码是 `secrets.token_hex(24)` 随机串（见
   `oauth.find_or_create_user`），用户根本不知道；解掉唯一绑定就会把人永久锁在门外。
   要求输密码之后，输不对的人（= 没有可用密码的人）自然被挡住。
3. **超管不许解掉他人账号的最后一个绑定**：超管用自己的密码能证明的是超管身份，
   不能证明对方还有别的登录方式，所以这条单独挡掉。
4. 零表结构变更（只删 `o_auth_account` 行）。
"""
import contextlib

from ._helpers import log_audit, login_required, admin_bp     # 同一蓝图对象
from flask import flash, redirect, render_template, request, session, url_for
from models import User, db
from models import OAuthAccount


def _target_user():
    """确定操作对象：(target, actor)。

    target=被查看/被解绑的账号，actor=当前登录账号。默认二者相同；
    仅超管可用 `?user_id=` 指定他人（表单里也接受 user_id，便于 POST 回传）。
    """
    actor = db.session.get(User, session["user_id"])
    raw = request.args.get("user_id") or request.form.get("user_id") or ""
    if raw and actor is not None and actor.is_super:
        with contextlib.suppress(ValueError, TypeError):
            other = db.session.get(User, int(raw))
            if other is not None:
                return other, actor
    return actor, actor


def _back_url(target, actor):
    """解绑后回到列表页；超管查看他人时保留 user_id，避免跳回自己的页面。"""
    return url_for("admin.oauth_bindings",
                   **({"user_id": target.id} if target.id != actor.id else {}))


@admin_bp.route("/oauth")
@login_required
def oauth_bindings():
    """当前账号的第三方绑定列表。"""
    target, actor = _target_user()
    links = (OAuthAccount.query.filter_by(user_id=target.id)
             .order_by(OAuthAccount.provider).all())
    configured, all_providers = [], []
    try:
        import oauth as oauth_svc
        configured = oauth_svc.configured_providers()
        # v3.25.7：把「支持哪些渠道」也交给模板渲染，别在模板里写死 provider 名 ——
        # 加新渠道时这里不会漏。
        # v3.25.10：标出每个渠道的绑定状态，模板据此决定「绑定按钮 / 已绑定 / 去配置」。
        linked = {l.provider for l in links}
        all_providers = [{"name": n, "label": m.get("label", n),
                          "configured": n in configured, "linked": n in linked}
                         for n, m in oauth_svc.PROVIDERS.items()]
    except Exception:  # noqa: BLE001  provider 未配置/未安装时只降级提示，不该让整页 500
        pass
    return render_template("admin/oauth_bindings.html", links=links,
                           target=target, actor=actor, configured=configured,
                           all_providers=all_providers)


@admin_bp.route("/oauth/bind/<provider>", methods=["POST"])
@login_required
def oauth_bind(provider):
    """开始「把第三方账号绑到当前账号」的流程（v3.25.10）。

    **为什么必须是 POST + CSRF，不能做成 GET 链接**：
    真正的 OAuth 授权发生在 provider 那边（用户要点确认），所以单靠 GET 链接
    不足以被静默利用；但绑定目标取自服务端 session 的 `user_id`，
    一旦做成 `<a href>`，任何人都能构造链接诱导他人发起绑定。
    POST + 全局 CSRF 钩子把「发起绑定」这个动作纳入站内意图，
    与项目内其它特权操作（解绑、改设置）保持同一口径。

    这里只做三件事：校验渠道存在且已启用 → 在会话里标记「本次是绑定流程」
    → 转发到既有 `oauth_start`。**不碰任何凭据、不建账号**，真正的绑定由
    `api/auth.py::oauth_callback` 完成（那里才有 (provider, sub) 唯一约束）。
    """
    import oauth as oauth_svc
    if provider not in oauth_svc.PROVIDERS:
        flash("未知的第三方登录渠道", "error")
        return redirect(url_for("admin.oauth_bindings"))
    if not oauth_svc.is_configured(provider):
        flash("该渠道尚未配置凭据，请先在「第三方登录」页填写后再绑定", "error")
        return redirect(url_for("admin.oauth_settings"))
    if OAuthAccount.query.filter_by(user_id=session["user_id"],
                                    provider=provider).first() is not None:
        flash("已经绑定过该渠道了，如需更换请先解绑", "error")
        return redirect(url_for("admin.oauth_bindings"))
    # 标记流程类型：callback 据此把结果 flash 回本页，而不是甩到首页让人看不见
    session["oauth_bind_flow"] = provider
    # `redirect=1`：走无 JS 降级，直接 302 到 provider（start 默认返回 JSON 给前端消费）
    return redirect(url_for("api.oauth_start", provider=provider, redirect=1))


@admin_bp.route("/oauth/unbind", methods=["POST"])
@login_required
def oauth_unbind():
    """解绑一条第三方账号。

    CSRF 由 `app._csrf_protect` 全局钩子强制（模板放 `csrf_input()`），此处不再重复校验。
    """
    target, actor = _target_user()
    link_id = request.form.get("link_id") or ""
    password = request.form.get("password") or ""

    link = None
    with contextlib.suppress(ValueError, TypeError):
        link = db.session.get(OAuthAccount, int(link_id))

    if link is None:
        flash("绑定记录不存在（可能已解绑）")
        log_audit("oauth_unbind", "oauth", None, "解绑失败：记录不存在", success=False)
        return redirect(_back_url(target, actor))

    if link.user_id != target.id:
        flash("只能解绑当前查看账号的绑定")
        log_audit("oauth_unbind", "oauth", link.id, "解绑失败：越权（非目标账号）",
                  success=False)
        return redirect(_back_url(target, actor))

    if target.id != actor.id and OAuthAccount.query.filter_by(user_id=target.id).count() <= 1:
        flash("不能解绑他人账号的最后一个第三方登录方式——会把对方锁在门外")
        log_audit("oauth_unbind", "oauth", link.id,
                  "解绑失败：他人账号仅剩一个绑定", success=False)
        return redirect(_back_url(target, actor))

    if not actor.check_password(password):
        flash("密码错误，未解绑")
        log_audit("oauth_unbind", "oauth", link.id, "解绑失败：密码错误", success=False)
        return redirect(_back_url(target, actor))

    provider, sub, uname = link.provider, link.sub, target.username
    db.session.delete(link)
    db.session.commit()
    log_audit("oauth_unbind", "oauth", None,
              f"解绑 {provider} 第三方账号（sub={sub}，归属 {uname}）")
    flash(f"已解绑 {provider} 账号")
    return redirect(_back_url(target, actor))
