"""认证接口（注册 / 登录 / 登出 / 当前用户 / CSRF / 图形验证码）。

共享辅助（_user_pub/_login_user/_login_delay/_csrf_token 等）统一来自 .common，
本模块不重复定义，避免命名覆盖与行为漂移。
"""
from flask import request, jsonify, session, Response, current_app

from .common import (api_bp, db, User, ROLE_USER, _current_user_or_none, _user_pub, _login_user, _login_delay, _csrf_token, rate_limit, client_key, log_login_attempt)

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

