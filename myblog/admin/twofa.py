# -*- coding: utf-8 -*-
"""后台「两步验证」（v3.21.0 2FA / TOTP）。

与 `/api/auth/2fa/*` 共用 `twofa` 服务层（同一套 enroll/confirm/disable 逻辑），
本模块只负责表单交互与页面渲染，绝不另写一份安全逻辑。

全局开关 config.TWOFA_ENABLED=false（默认）时整页提示「未启用」，绑定动作全部拒绝。
"""
import io

from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象


def _qr_svg(uri):
    """把 otpauth URI 生成内联 SVG 二维码；segno 缺失时返回 None（页面降级为手动输入密钥）。"""
    try:
        import segno
        buf = io.BytesIO()
        segno.make(uri, error="m").save(buf, kind="svg", scale=8, border=2,
                                        dark="#111", light="white")
        return buf.getvalue().decode("utf-8")
    except Exception:# noqa: BLE001  segno 为可选依赖：缺失时降级为手动输入密钥
        return None


@admin_bp.route("/2fa", methods=["GET", "POST"])
@login_required
def twofa():
    """两步验证绑定/管理页。

    action: enroll（生成密钥）/ confirm（验证码确认）/ disable（密码+验证码关闭）。
    """
    import twofa as twofa_svc
    from flask import current_app

    user = db.session.get(User, session["user_id"])
    enabled = bool(current_app.config.get("TWOFA_ENABLED"))
    st = twofa_svc.status_for(user)
    ctx = {"enabled": enabled, "enrolled": st["enrolled"],
           "recovery_codes_left": st["recovery_codes_left"],
           "secret": None, "uri": None, "qr": None, "recovery_codes": None}

    if request.method == "POST":
        action = request.form.get("action", "")
        if not enabled:
            flash("两步验证未启用（需设置环境变量 BLOG_TWOFA_ENABLED=true 并重启）")
        elif action == "enroll":
            status, secret, uri = twofa_svc.enroll(user)
            if status == "ok":
                ctx.update(secret=secret, uri=uri, qr=_qr_svg(uri))
                flash("已生成新密钥：请用验证器 App 扫码或手抄密钥，然后输入 6 位码确认绑定")
            else:
                flash("密钥加密失败：请检查 cryptography 依赖是否已安装")
        elif action == "confirm":
            code = (request.form.get("code") or "").strip()
            status, plain = twofa_svc.confirm(user, code)
            if status == "ok":
                ctx["recovery_codes"] = plain
                flash("绑定成功！请立即保存下方恢复码（每个只能用一次），手机丢失时靠它救回账号")
            elif status == "no_enroll":
                flash("请先点击「生成密钥」")
            elif status == "error":
                flash("密钥读取失败，请重新生成密钥")
            else:
                flash("验证码错误或已过期，请输入验证器 App 当前显示的 6 位码")
        elif action == "disable":
            status = twofa_svc.disable(user, request.form.get("password") or "",
                                       (request.form.get("code") or "").strip())
            if status == "ok":
                flash("已关闭两步验证")
            elif status == "not_enabled":
                flash("当前未启用两步验证")
            elif status == "bad_password":
                flash("密码错误")
            else:
                flash("验证码或恢复码错误")
        st = twofa_svc.status_for(user)
        ctx.update(enrolled=st["enrolled"], recovery_codes_left=st["recovery_codes_left"])

    return render_template("admin/twofa.html", **ctx)
