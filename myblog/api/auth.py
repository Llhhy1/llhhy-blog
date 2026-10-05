"""认证接口（注册 / 登录 / 登出 / 当前用户 / CSRF / 图形验证码）。

共享辅助（_user_pub/_login_user/_login_delay/_csrf_token 等）统一来自 .common，
本模块不重复定义，避免命名覆盖与行为漂移。
"""
import hmac
import time

from flask import (request, jsonify, session, Response, current_app, redirect, flash,
                   url_for)

import twofa   # v3.21.0 2FA：业务操作统一走 twofa 服务层（后台页与 API 共用同一套）

from .common import (api_bp, db, User, Setting, ROLE_USER, _current_user_or_none, _user_pub, _login_user, _login_delay, _csrf_token, rate_limit, client_key, log_login_attempt)

# ---------- 认证接口（注册 / 登录 / 登出 / 当前用户）----------
@api_bp.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or request.form
    # 限流：同一 IP 60 秒内最多 10 次注册尝试
    if not rate_limit(client_key("api_register"), limit=10, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    # 注册开关：后台「系统设置」可改（DB → 环境变量 BLOG_OPEN_REGISTER → 默认 true）
    from utils import flag_bool
    if not flag_bool("open_register", "BLOG_OPEN_REGISTER", True):
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
    # v3.1.6 中优：弱密码黑名单 + 复杂度校验；v3.25.8 起可在「系统设置」页切换
    from utils import validate_password, flag_bool
    ok_pwd, pwd_err = validate_password(
        password, min_len=8,
        strong=flag_bool("strong_password", "STRONG_PASSWORD", True),
        mixed_case=flag_bool("strong_password_mixed_case", "STRONG_PASSWORD_MIXED_CASE", False),
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
    # v3.21.2 审计：密码对但**尚未通过第二因素**时不得记成登录成功——否则针对
    # 2FA 挑战的爆破在审计日志里全都显示为「成功登录」，正好掩盖了最需要看的信号。
    if _twofa_on() and _twofa_active(u.id):
        session["twofa_pending_uid"] = u.id
        session["twofa_pending_at"] = int(time.time())
        return jsonify({"twofa_required": True, "username": u.username}), 200
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

_OAUTH_STATE_TTL = 600   # state 有效期（秒）：与 _TWOFA_PENDING_TTL 同理，不给整会话期重放


@api_bp.route("/auth/oauth/providers")
def oauth_providers():
    """返回当前已配置的 provider 列表（前端据此显隐登录按钮）。"""
    from oauth import configured_providers
    return jsonify({"providers": configured_providers()})


@api_bp.route("/auth/oauth/<provider>/start")
def oauth_start(provider):
    from oauth import is_configured, build_authorize_url, new_state
    if not rate_limit(client_key("api_oauth"), limit=20, window=60):
        return jsonify({"error": "操作过于频繁，请稍后再试"}), 429
    if provider not in ("github", "google") or not is_configured(provider):
        return jsonify({"error": "provider_not_configured"}), 503
    redirect_uri = _oauth_redirect_uri(provider)
    state = new_state()
    session["oauth_provider"] = provider
    session["oauth_state"] = state
    session["oauth_state_at"] = int(time.time())
    url = build_authorize_url(provider, redirect_uri, state)
    # v3.25.10：**无 JS 降级**。默认返回 JSON 给前��� store.js 消费（行为不变）；
    # 带 `?redirect=1` 时直接 302 到 provider —— 后台「绑定」按钮是普通表单跳转，
    # 没有 JS 帮它读 JSON，否则用户点下去只会看到一片 JSON。
    if request.args.get("redirect") == "1":
        return redirect(url)
    return jsonify({"authorize_url": url})


def _oauth_redirect_uri(provider):
    """回调地址由 `oauth.callback_url()` 从 `site_base()` 派生（v3.25.7 收口到一处）。

    与 `/api/og/*`、`_abs()` 在 v3.18.9 定下的「对外 URL 只走 `site_base()`」一致
    （`utils/settings.py` 把 `request.url_root` 列为禁用项，而本站未配
    `trusted_hosts` / `SERVER_NAME`）。
    **只有** `site_base()` 为空时才退回本次请求的 Host：
    ① 现网存在只靠域名别名跑的部署（同 R90 待办② 的结论）；
    ② 硬失败会从 `oauth_start` 冒成 500；
    ③ 这里不构成 Host 注入面——provider 只会在**其登记的回调白名单**内跳转，
      伪造 Host 顶多让自己拿不到 code。若真要收得更紧，应配 SITE_URL 而非在此
      拒绝服务。
    """
    from oauth import callback_url
    from utils import site_base
    u = callback_url(provider, site_base())
    if u:
        return u
    return (request.url_root or "").rstrip("/") + "/api/auth/oauth/" + provider + "/callback"


@api_bp.route("/auth/oauth/<provider>/callback")
def oauth_callback(provider):
    from oauth import is_configured, exchange_code, find_or_create_user
    home = (request.url_root or "/").rstrip("/") + "/"
    if not rate_limit(client_key("api_oauth_cb"), limit=20, window=60):
        return redirect(home + "?oauth=rate_limited")
    if session.get("oauth_provider") != provider or not is_configured(provider):
        return redirect(home + "?oauth=error")
    req_state = request.args.get("state") or ""
    exp_state = session.get("oauth_state") or ""
    # 常量时间比较 + 有效期：`!=` 会留下时序侧信道，且没有 TTL 的话一次下发的 state
    # 在整个会话生命周期内都可重放（下面 :185 的「缺 code 提前 return」正好绕开了
    # finally 的清理，所以那条路径上的 state 会一直留在会话里）。
    issued_at = session.get("oauth_state_at") or 0
    expired = (int(time.time()) - int(issued_at)) > _OAUTH_STATE_TTL
    if not req_state or not exp_state or expired or \
            not hmac.compare_digest(str(req_state), str(exp_state)):
        return redirect(home + "?oauth=error")
    code = request.args.get("code") or ""
    if not code:
        session.pop("oauth_provider", None)
        session.pop("oauth_state", None)
        session.pop("oauth_state_at", None)
        return redirect(home + "?oauth=error")
    try:
        info = exchange_code(provider, code, _oauth_redirect_uri(provider))
        # 已登录时回调 = 用户主动把第三方身份**绑到自己这个账号**；未登录时才走
        # 「命中已有绑定 / 新建账号」。绝不按邮箱认领别人的账号（见 oauth.py 注释）。
        u = find_or_create_user(provider, info["sub"], info.get("email"),
                                info.get("name"), info.get("email_verified", False),
                                bind_user_id=session.get("user_id"))
    except ValueError as e:
        # v3.25.10：绑定冲突是**用户可理解**的失败（"这个第三方账号已绑给别人"），
        # 值得明确告知；其余异常仍旧一律收敛成通用 error，绝不外泄细节。
        current_app.logger.info("OAuth 绑定被拒：%s", e)
        if session.pop("oauth_bind_flow", None):
            flash(str(e), "error")
            return redirect(url_for("admin.oauth_bindings"))
        return redirect(home + "?oauth=error")
    except Exception:
        # OAuth 回调绝不向外泄漏异常细节（库结构 / 路径 / provider 原文），统一 error
        current_app.logger.exception("OAuth 回调失败")
        if session.pop("oauth_bind_flow", None):
            flash("绑定失败：授权未完成或 provider 拒绝了请求，请重试", "error")
            return redirect(url_for("admin.oauth_bindings"))
        return redirect(home + "?oauth=error")
    finally:
        session.pop("oauth_provider", None)
        session.pop("oauth_state", None)
        session.pop("oauth_state_at", None)
    if u is None:
        # 绑定的目标用户已被删除：当作失败处理，不得冒成未捕获的 AttributeError
        if session.pop("oauth_bind_flow", None):
            flash("绑定失败：目标账号已不存在", "error")
            return redirect(url_for("admin.oauth_bindings"))
        return redirect(home + "?oauth=error")
    bind_flow = session.pop("oauth_bind_flow", None)
    if bind_flow:
        # 绑定流程：结果要回到绑定页看得见。`twofa_ok=False` 是刻意复位 ——
        # 身份凭据刚变更，须重新过第二因素（开了 2FA 的人会立刻被要求输动态码）。
        # 注意：绑定**不算一次登录**，因此不写登录审计（登录成功只记真正的登录）。
        session["user_id"] = u.id
        session["session_version"] = u.session_version or 0
        session["twofa_ok"] = False
        flash(f"已绑定 {provider} 账号。"
              + ("若你已开启两步验证，接下来需重新输入一次动态码（这是安全设计）。"
                 if _twofa_on() else ""))
        return redirect(url_for("admin.oauth_bindings"))
    # v3.25.12：与「账号密码登录」同一契约 —— 目标账号开了两步验证时，OAuth 回调
    # **不得**直接建立登录态。此前这里照写 `session["user_id"]` 并置 `twofa_ok=False`，
    # 会话因此落在「已登录但没过第二因素」：SSR 页面会被 `enforce_twofa` 赶去 `/twofa`，
    # 而 SPA 的每个 `/api/*` 都拿到 401 + `twofa_required` —— 前端只认
    # `/api/auth/login` 返回的 `twofa_required`，对 401 没有任何处理，于是整页接口
    # 全 401、登录看起来就是「失败」（线上 2026-10-05 23:34 实测：`/?oauth=ok` 之后
    # `/api/site`、`/api/posts`、`/api/stats/summary` 等 17 个请求全部 401）。
    # 改为只挂起（`twofa_pending_*`）、由 `/api/auth/2fa/verify` 收尾：与 `auth_login`
    # 完全一致，**第二因素通过之前会话里根本不出现 user_id**。
    # ⚠️ 落点是 `/login?twofa=1`（**不是** `/twofa`）：生产 nginx 的
    # `location / { try_files $uri $uri/ /index.html }` 把 `/login`、`/twofa`
    # 都当成 SPA 静态页（实测 2026-10-05：`/twofa` 在访问日志里**零次**），
    # 而 SPA 路由表里**没有 `/twofa`**（命中 `/:pathMatch(.*)*` → redirect `/`），
    # 跳过去等于「首页 → 401 → 再跳」的死循环。`/login` 是 SPA 真实路由。
    # 挂起态是否真的存在由 `/api/auth/2fa/status` 的 `pending` 回答，
    # 前端**不靠 URL 参数盲信**（该落点由两条路径共用，见 `twofa_status`）。
    if not session.get("user_id") and _twofa_on() and _twofa_active(u.id):
        session["twofa_pending_uid"] = u.id
        session["twofa_pending_at"] = int(time.time())
        return redirect(url_for("main.login", twofa="1"))
    log_login_attempt(u.username, True)   # v3.21.2：OAuth 登录此前完全不进登录审计
    session["user_id"] = u.id
    session["session_version"] = u.session_version or 0
    session["twofa_ok"] = False
    return redirect(home + "?oauth=ok")


# ---------- v3.21.0 双因素认证 2FA / TOTP（config-gated：TWOFA_ENABLED=false 时整体休眠）----------

_TWOFA_PENDING_TTL = 300   # 登录挂起态有效期（秒）：超时必须重新走用户名密码


def _twofa_on():
    """全局开关（休眠闸门）。未开启时所有 2FA 入口短路，登录流程完全不变。

    v3.25.8：改由 `flag_bool` 取值 —— 后台「系统设置」可开关，
    **不必再改环境变量 + 重启**。这是 2FA 从 v3.21.0 起第一次真正可用。
    """
    from utils import flag_bool
    return flag_bool("twofa_enabled", "TWOFA_ENABLED", False)


def _twofa_active(uid):
    """该用户是否已**确认生效**的两步验证（仅 enrolled 未 confirm 不算）。"""
    return twofa.is_active(uid)


def _cur_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


@api_bp.route("/auth/2fa/status")
def twofa_status():
    """全局开关 + 当前用户绑定状态（前端据此显隐入口）。

    v3.25.12 新增 `pending`：**本会话是否正卡在「第一因素已过、等动态码」**。
    它必须是服务端的回答而不是前端猜 —— 落点 `/login?twofa=1` 由两条路径共用
    （OAuth 回调的挂起、以及「已登录但没过二因素」被闸门判 401 后的兜底跳转），
    **只有前者真的有挂起态**。前端若只认 URL 参数，后者会弹出一个必然报
    「验证已超时」的输入框。
    """
    u = _cur_user()
    st = {"enabled": _twofa_on(), "enrolled": False, "recovery_codes_left": 0,
          "pending": bool(session.get("twofa_pending_uid"))}
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
    status, secret, uri = twofa.enroll(u, ((request.get_json(silent=True) or request.form)
                                           .get("code") or "").strip())
    if status == "requires_code":
        return jsonify({"error": "重置已生效的两步验证需要当前动态码或恢复码"}), 403
    if status != "ok":
        return jsonify({"error": "密钥加密失败，请联系管理员检查 cryptography 依赖"}), 500
    resp = jsonify({"secret": secret, "provisioning_uri": uri})
    # 响应体含**明文 TOTP 密钥**：不留任何可被浏览器/代理缓存的副本
    # （与同文件其它敏感响应一致；provisioning_uri 里同样带着密钥）。
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
    # confirm 成功即「当场证明持有第二因素」，因此本会话直接算已过 2FA。
    # 不做这一步的话，用户刚绑定完就会被 `enforce_twofa` 挡在所有接口之外——
    # 而 `/api/auth/2fa/verify` 是登录第二步、要求挂起态，此时并无挂起态可用。
    session["twofa_ok"] = True
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
    # v3.25.12：第二因素通过才算登录成功 —— 审计要记在这里。此前只有「不需要 2FA」
    # 的登录会落审计（v3.21.2 的要求「密码对但未过第二因素不得记成功」），结果开了
    # 2FA 的账号**无论账号密码还是第三方登录都一条成功记录都没有**，恰恰是最该看的一类。
    log_login_attempt(u.username, True)
    return _login_user(u, twofa_ok=True)

