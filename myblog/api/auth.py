"""认证接口（注册 / 登录 / 登出 / 当前用户 / CSRF / 图形验证码）。

共享辅助（_user_pub/_login_user/_login_delay/_csrf_token 等）统一来自 .common，
本模块不重复定义，避免命名覆盖与行为漂移。
"""
import time

from flask import request, jsonify, session, Response, current_app, redirect

import twofa   # v3.21.0 2FA：业务操作统一走 twofa 服务层（后台页与 API 共用同一套）

from .common import (api_bp, db, User, Setting, ROLE_USER, _current_user_or_none, _user_pub, _login_user, _login_delay, _csrf_token, rate_limit, client_key, log_login_attempt)

# ---------- 认证接口（注册 / 登录 / 登出 / 当前用户）----------
@api_bp.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次注册尝试
    if not rate_limit(client_key("api_register"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    # 注册开关：生产可设 BLOG_OPEN_REGISTER=false 关闭公开注册
    if not current_app.config.get("BLOG_OPEN_REGISTER"):
        return jsonify({"error": "本站已关闭公开注册"}), 403
    # v3.1.6 可选增强：注册验证码（CAPTCHA_ENABLED=true 时要求通过验证码或直接带验证码文本）
    from security import captcha_required, consume_captcha_pass, verify_captcha
    if captcha_required():
        passed = consume_captcha_pass()  # 一次性票据（先验票再消费）
        if not passed:
            code = (data.get("captcha") or "").strip()
            if not code or not verify_captcha(code):
                return jsonify({"error": "请先完成验证码校验"}), 400
            consume_captcha_pass()  # 直接带文本校验通过后消费票据防重放
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 20:
        return jsonify({"error": "用户名长度需在 2-20 个字符"}), 400
    # v3.1.6 中优：弱密码黑名单 + 复杂度校验（STRONG_PASSWORD 开关，见 config）
    from utils import validate_password
    cfg = current_app.config
    ok_pwd, pwd_err = validate_password(
        password, min_len=8,
        strong=cfg.get("STRONG_PASSWORD", True),
        mixed_case=cfg.get("STRONG_PASSWORD_MIXED_CASE", False),
    )
    if not ok_pwd:
        return jsonify({"error": pwd_err}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "该用户名已被注册"}), 409
    u = User(username=username, email=email, role=ROLE_USER)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return _login_user(u), 201


@api_bp.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次登录尝试，缓解暴力破解
    if not rate_limit(client_key("api_login"), limit=10, window=60):
        return jsonify({"error": "尝试过于频繁，请稍后再试"}), 429
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        # v3.1.0：记录失败的登录尝试（含尝试的用户名与 IP，便于发现爆破）
        log_login_attempt(username, False)
        # v3.1.6 中优：消除用户名枚举——失败统一文案（无论用户是否存在）+ 统一延迟，防时序侧信道
        _login_delay()
        return jsonify({"error": "用户名或密码错误"}), 401
    log_login_attempt(username, True)
    # v3.21.0 2FA：该账号已绑定两步验证且全局开启 → 先不建立登录态，要求二次验证码。
    # 挂起态只记「待验证的用户 id + 起始时间戳」，5 分钟内有效（见 _TWOFA_PENDING_TTL）。
    if _twofa_on() and _twofa_active(u.id):
        session["twofa_pending_uid"] = u.id
        session["twofa_pending_at"] = int(time.time())
        return jsonify({"twofa_required": True, "username": u.username}), 200
    return _login_user(u)


@api_bp.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@api_bp.route("/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None, "csrf_token": _csrf_token()}), 200
    u = db.session.get(User, uid)
    if not u:
        session.pop("user_id", None)
        return jsonify({"user": None, "csrf_token": _csrf_token()}), 200
    return jsonify({"user": _user_pub(u), "csrf_token": _csrf_token()}), 200


@api_bp.route("/csrf")
def csrf():
    """获取当前会话的 CSRF Token（Vue 前端在 apiPost 前调用，放入 X-CSRF-Token 头）。"""
    return jsonify({"csrf_token": _csrf_token()}), 200


# ---------- 图形验证码（v3.1.6 可选增强：可开关；v3.2.0 后台可单独配置）----------
@api_bp.route("/captcha/config")
def captcha_config():
    """返回验证码配置快照（全局启用 / PIL 是否可用 / 各场景开关），供前端分场景显隐。"""
    from security import get_captcha_config
    return jsonify(get_captcha_config())


@api_bp.route("/comment/config")
def comment_config():
    """v3.15.3 功能1：返回评论配置（邮箱是否必填），供前端动态显隐邮箱输入框的 required 属性。"""
    row = Setting.query.filter_by(key="comment_email_required").first()
    email_required = (row.value == "true") if row else False
    return jsonify({"email_required": email_required})


@api_bp.route("/captcha")
def captcha_image():
    """获取注册/评论/留言验证码图片（GET）。返回 PNG 图；该场景未启用或全局关闭时返回 404。
    生成后答案存会话（captcha_answer），前端刷新图片时可重新生成。"""
    from security import generate_captcha, captcha_required
    scope = request.args.get("from")
    if not captcha_required(scope):
        return jsonify({"error": "验证码未启用"}), 404
    img, _ = generate_captcha()
    if img is None:
        # PIL 不可用降级：返回纯文本模式（前端显示为普通输入，不校验——零依赖稳妥）
        return jsonify({"captcha": "off", "message": "服务器未安装图像库，验证码已降级停用"}), 200
    return Response(img.getvalue(), mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


@api_bp.route("/captcha/verify", methods=["POST"])
def captcha_verify():
    """前端提交验证码文本，校验通过后会话标记 captcha_passed（一次性票据）。
    注册/评论提交时随请求携带该票据（或直接把验证码文本带上由注册接口自行校验）。"""
    data = request.get_json(silent=True) or request.form
    code = (data.get("captcha") or "").strip()
    from security import verify_captcha, consume_captcha_pass
    if not code:
        return jsonify({"error": "请输入验证码"}), 400
    if not verify_captcha(code):
        return jsonify({"error": "验证码错误，请重新输入"}), 400
    return jsonify({"ok": True, "captcha_passed": True}), 200


# ---------- v3.21.0 OAuth 第三方登录（config-gated，未配凭据则休眠）----------

@api_bp.route("/auth/oauth/providers")
def oauth_providers():
    """返回当前已配置的 provider 列表（前端据此显隐登录按钮）。"""
    from oauth import configured_providers
    return jsonify({"providers": configured_providers()})


@api_bp.route("/auth/oauth/<provider>/start")
def oauth_start(provider):
    from oauth import is_configured, build_authorize_url, new_state
    if provider not in ("github", "google") or not is_configured(provider):
        return jsonify({"error": "provider_not_configured"}), 503
    redirect_uri = request.url_root.rstrip("/") + "/api/auth/oauth/" + provider + "/callback"
    state = new_state()
    session["oauth_provider"] = provider
    session["oauth_state"] = state
    return jsonify({"authorize_url": build_authorize_url(provider, redirect_uri, state)})


@api_bp.route("/auth/oauth/<provider>/callback")
def oauth_callback(provider):
    from oauth import is_configured, exchange_code, find_or_create_user
    home = request.url_root.rstrip("/") + "/"
    if session.get("oauth_provider") != provider or not is_configured(provider):
        return redirect(home + "?oauth=error")
    req_state = request.args.get("state") or ""
    if not req_state or req_state != session.get("oauth_state"):
        return redirect(home + "?oauth=error")
    code = request.args.get("code") or ""
    if not code:
        return redirect(home + "?oauth=error")
    try:
        info = exchange_code(
            provider, code,
            request.url_root.rstrip("/") + "/api/auth/oauth/" + provider + "/callback",
        )
        u = find_or_create_user(provider, info["sub"], info.get("email"),
                                info.get("name"), info.get("email_verified", False))
    except Exception:# noqa: BLE001  OAuth 回调绝不向外泄漏异常细节，统一重定向到 ?oauth=error
        return redirect(home + "?oauth=error")
    finally:
        session.pop("oauth_provider", None)
        session.pop("oauth_state", None)
    session["user_id"] = u.id
    session["session_version"] = u.session_version or 0
    return redirect(home + "?oauth=ok")


# ---------- v3.21.0 双因素认证 2FA / TOTP（config-gated：TWOFA_ENABLED=false 时整体休眠）----------

_TWOFA_PENDING_TTL = 300   # 登录挂起态有效期（秒）：超时必须重新走用户名密码


def _twofa_on():
    """全局开关（休眠闸门）。未开启时所有 2FA 入口短路，登录流程完全不变。"""
    return bool(current_app.config.get("TWOFA_ENABLED"))


def _twofa_active(uid):
    """该用户是否已**确认生效**的两步验证（仅 enrolled 未 confirm 不算）。"""
    return twofa.is_active(uid)


def _cur_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


@api_bp.route("/auth/2fa/status")
def twofa_status():
    """全局开关 + 当前用户绑定状态（前端据此显隐入口）。"""
    u = _cur_user()
    st = {"enabled": _twofa_on(), "enrolled": False, "recovery_codes_left": 0}
    if u:
        st.update(twofa.status_for(u))
    return jsonify(st)


@api_bp.route("/auth/2fa/enroll", methods=["POST"])
def twofa_enroll():
    """生成/重置 TOTP 密钥，返回 otpauth URI 与明文密钥（仅此一次展示）。"""
    if not _twofa_on():
        return jsonify({"error": "2FA 未启用"}), 404
    u = _cur_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    # 限流：enroll 会写库生成新密钥，防被刷成写放大（与 confirm/disable 分开计数，互不挤占）
    if not rate_limit(client_key("api_2fa_enroll"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    status, secret, uri = twofa.enroll(u)
    if status != "ok":
        return jsonify({"error": "密钥加密失败，请联系管理员检查 cryptography 依赖"}), 500
    return jsonify({"secret": secret, "provisioning_uri": uri})


@api_bp.route("/auth/2fa/confirm", methods=["POST"])
def twofa_confirm():
    """用验证器 App 的 6 位码确认绑定；成功后启用并**一次性**返回恢复码。"""
    if not _twofa_on():
        return jsonify({"error": "2FA 未启用"}), 404
    u = _cur_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    # 限流：6 位码空间仅 10^6，必须防在线爆破（confirm 成功前 enabled 仍为 False）
    if not rate_limit(client_key("api_2fa_confirm"), limit=10, window=60):
        return jsonify({"error": "尝试过于频繁，请稍后再试"}), 429
    code = ((request.get_json(silent=True) or request.form).get("code") or "").strip()
    status, plain = twofa.confirm(u, code)
    if status == "no_enroll":
        return jsonify({"error": "请先获取绑定密钥"}), 400
    if status == "error":
        return jsonify({"error": "密钥读取失败"}), 500
    if status == "bad_code":
        return jsonify({"error": "验证码错误或已过期"}), 400
    return jsonify({"ok": True, "recovery_codes": plain})


@api_bp.route("/auth/2fa/disable", methods=["POST"])
def twofa_disable():
    """关闭两步验证：需密码 + 动态码（或恢复码），防会话劫持后被直接关掉。"""
    if not _twofa_on():
        return jsonify({"error": "2FA 未启用"}), 404
    u = _cur_user()
    if not u:
        return jsonify({"error": "请先登录"}), 401
    # 限流：关闭需「密码 + 动态码」，同样防爆破（否则劫持会话后可离线试码关掉 2FA）
    if not rate_limit(client_key("api_2fa_disable"), limit=10, window=60):
        return jsonify({"error": "尝试过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or request.form
    status = twofa.disable(u, data.get("password") or "", (data.get("code") or "").strip())
    if status == "not_enabled":
        return jsonify({"error": "未启用两步验证"}), 400
    if status == "bad_password":
        return jsonify({"error": "密码错误"}), 400
    if status == "bad_code":
        return jsonify({"error": "验证码或恢复码错误"}), 400
    return jsonify({"ok": True})


@api_bp.route("/auth/2fa/verify", methods=["POST"])
def twofa_verify():
    """登录第二步：校验挂起态用户的动态码 / 恢复码，通过才建立登录态。"""
    if not _twofa_on():
        return jsonify({"error": "2FA 未启用"}), 404
    started = session.get("twofa_pending_at") or 0
    if not started or (int(time.time()) - int(started)) > _TWOFA_PENDING_TTL:
        session.pop("twofa_pending_uid", None)
        session.pop("twofa_pending_at", None)
        return jsonify({"error": "验证已超时，请重新登录"}), 400
    u = db.session.get(User, session.get("twofa_pending_uid"))
    if not u:
        return jsonify({"error": "验证已超时，请重新登录"}), 400
    # 二步码同样限流：6 位码空间小，必须防在线爆破
    if not rate_limit(client_key("api_2fa"), limit=10, window=60):
        return jsonify({"error": "尝试过于频繁，请稍后再试"}), 429
    code = ((request.get_json(silent=True) or request.form).get("code") or "").strip()
    if not twofa.verify_login(u, code):
        return jsonify({"error": "验证码或恢复码错误"}), 400
    session.pop("twofa_pending_uid", None)
    session.pop("twofa_pending_at", None)
    return _login_user(u)

