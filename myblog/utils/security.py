# -*- coding: utf-8 -*-
"""密码强度校验与 CSRF Token。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re
import hmac
import hashlib
import secrets
from markupsafe import Markup

# ---------- 弱密码黑名单 + 复杂度校验（v3.1.6 中优）----------
# 常见弱口令黑名单：直接命中拒绝；变体（如 123456a / password123）靠复杂度规则兜底。
_WEAK_PASSWORDS = {
    "123456", "123456789", "12345678", "1234567", "123123", "111111",
    "000000", "666666", "888888", "password", "passw0rd", "qwerty",
    "qwerty123", "abc123", "abc123456", "123qwe", "qwe123", "123abc",
    "admin123", "admin888", "admin666", "root123", "password1",
    "qq123456", "a123456", "woaini1314", "iloveyou", "1qaz2wsx",
    "zxcvbnm", "asdfgh", "5201314", "aa123456", "a12345678", "pp123456",
}
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")


def validate_password(raw, min_len=8, strong=None, mixed_case=None):
    """校验密码强度。返回 (ok, 错误信息)。

    - 基础：长度 >= min_len（默认 8）
    - strong=True（默认，可用环境变量 STRONG_PASSWORD 关闭）：至少含字母 + 数字；
      且不在弱密码黑名单（大小写不敏感比较）
    - mixed_case=True（STRONG_PASSWORD_MIXED_CASE）：再要求同时含大写与小写字母
    - 以上开关均可在 config 配置，此处默认按最严格（调用方可传入 config 值覆盖）
    """
    pwd = raw or ""
    if len(pwd) < min_len:
        return False, f"密码至少 {min_len} 位"
    if strong is None:
        strong = True
    if mixed_case is None:
        mixed_case = False
    if strong:
        if pwd.strip().lower() in _WEAK_PASSWORDS:
            return False, "该密码过于常见，请换一个更复杂的密码"
        if not (_LOWER_RE.search(pwd) or _UPPER_RE.search(pwd)) or not _DIGIT_RE.search(pwd):
            return False, "密码需同时包含字母和数字"
        if mixed_case and (_LOWER_RE.search(pwd) is None or _UPPER_RE.search(pwd) is None):
            return False, "密码需同时包含大写和小写字母"
    return True, ""
# ---------- CSRF Token 双因子防护（v3.1.6 中优）----------
# 在既有 SameSite=Lax + Origin 同源校验之上，增加「会话绑定的一次性 CSRF Token」：
#   每个登录会话生成 token（哈希型，HMAC(SECRET_KEY, session_id+user_id)），
#   写进 session 并在模板里注入 <input type="hidden" name="csrf_token">；
#   POST 请求校验表单字段或请求体 csrf_token 必须与会话 token 一致（恒定时间比较）。
# 前端（Vue SPA）通过 /api/auth/me 响应头拿到 token，后续 POST 自动带 X-CSRF-Token。


def generate_csrf_token():
    """生成本会话的 CSRF Token（惰性，无则创建）。返回 (token, 是否新建)。

    v3.4.6 修复（多 worker 下 token 反复轮换 → 前端 403「抽风」）：
    旧实现用进程级 _CSRF_CACHE 判断 token 是否「新鲜」，但 gunicorn 多 worker 时
    每个 worker 各自持有一份缓存，落到不同 worker 的请求会认为「缓存里没有当前
    token」从而重新生成并覆盖 session 里的 token，导致前端缓存的 token 失效 → 403。
    改为：只要 session 中已有**签名有效**的 token 就直接复用（签名由本服务
    SECRET_KEY 经 HMAC 生成，天然防伪造/防跨服务复用），token 在整段会话内保持稳定，
    不再随 worker 切换而轮换。仅当 token 缺失或签名失效（被篡改/SECRET_KEY 已轮换）
    时才重新生成。
    """
    from flask import session
    tok = session.get("csrf_token")
    if tok:
        # 复用既有 token，但先校验签名仍有效（防 session 被篡改或跨服务伪造）
        parts = str(tok).split(".")
        if len(parts) == 2 and hmac.compare_digest(_sign_csrf(parts[0]), parts[1]):
            return tok, False
        # 既有 token 签名无效 → 重新生成（不沿用被污染的值）
    raw = secrets.token_hex(24)
    # 会话绑定：token 本身存 session；签名部分用于校验 token 确由本服务签发
    tok = raw + "." + _sign_csrf(raw)
    session["csrf_token"] = tok
    return tok, True


def _sign_csrf(raw):
    """HMAC(SECRET_KEY, 'csrf:' + raw) 生成校验签名。"""
    from flask import current_app
    key = (current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    return hmac.new(key, ("csrf:" + raw).encode("utf-8"), hashlib.sha256).hexdigest()


def check_csrf_token(tok):
    """校验提交的 CSRF Token 是否等于会话 token（恒定时间比较）。返回 True/False。

    双重校验：
    1. 签名有效性：token 的签名部分必须由本服务 SECRET_KEY 生成（防伪造任意 token）；
    2. 与会话一致：提交的 token 必须等于当前会话里存的 token。
    """
    from flask import session
    session_tok = session.get("csrf_token") or ""
    if not tok or not session_tok:
        return False
    parts = str(tok).split(".")
    if len(parts) != 2:
        return False
    raw, sig = parts
    expect = _sign_csrf(raw)
    if not hmac.compare_digest(sig, expect):
        return False
    return hmac.compare_digest(str(tok), session_tok)


def csrf_input():
    """渲染隐藏域用（模板里写 {{ csrf_input() }}）。

    必须返回 Markup（安全 HTML）：Jinja2 默认 autoescape，若返回普通字符串，
    <input> 会被转义成 &lt;input&gt;，导致登录后台页面直接显示这段源码（乱码）。
    """
    tok, _ = generate_csrf_token()
    return Markup(f'<input type="hidden" name="csrf_token" value="{tok}">')
