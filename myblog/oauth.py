"""OAuth 第三方登录（v3.21.0，config-gated）。

设计：
- 仅 GitHub / Google 两 provider；凭据来自 config（环境变量），**未配置则整体休眠**。
- 出站请求一律走白名单固定 URL + **禁止跟随重定向**（与 seo_push._NoRedirect 一致，
  避免半盲 SSRF / 令牌泄漏到跳转地址）。
- 流程：start 生成 state 存会话 → 前端跳转到 provider → callback 校验 state、换 token、
  拉 userinfo → 按 (provider, sub) 或邮箱命中/新建本地用户 → 登录。
- 本模块不直接 import app；仅在函数内取 current_app.config，便于测试注入 cfg。
"""
import contextlib
import json
import secrets
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

from models import db, User, OAuthAccount, ROLE_USER


# 禁止跟随重定向（出网请求的安全基线）
class _NoRedirect(HTTPRedirectHandler):
    # 形参名必须对齐基类签名；req/msg 本实现用不到，加下划线前缀声明为占位
    def redirect_request(self, _req, fp, code, _msg, headers, newurl):  # noqa: ARG002
        raise HTTPError(newurl, code, "redirect forbidden", headers, fp)


_opener = build_opener(_NoRedirect())


# provider 注册表（URL 全部为常量白名单，不接受任何外部输入拼接）
PROVIDERS = {
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "scope": "read:user user:email",
        "client_id": lambda c: c.get("OAUTH_GITHUB_CLIENT_ID"),
        "client_secret": lambda c: c.get("OAUTH_GITHUB_CLIENT_SECRET"),
    },
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "client_id": lambda c: c.get("OAUTH_GOOGLE_CLIENT_ID"),
        "client_secret": lambda c: c.get("OAUTH_GOOGLE_CLIENT_SECRET"),
    },
}


def _cfg(cfg=None):
    """取配置对象（默认当前 app 的 config，便于测试注入）。"""
    if cfg is None:
        from flask import current_app
        cfg = current_app.config
    return cfg


def is_configured(name, cfg=None):
    """provider 是否已配置凭据（缺任一即休眠）。"""
    p = PROVIDERS.get(name)
    if not p:
        return False
    c = _cfg(cfg)
    return bool(p["client_id"](c)) and bool(p["client_secret"](c))


def configured_providers(cfg=None):
    return [n for n in PROVIDERS if is_configured(n, cfg)]


def build_authorize_url(name, redirect_uri, state, cfg=None):
    p = PROVIDERS[name]
    c = _cfg(cfg)
    q = urlencode({
        "client_id": p["client_id"](c),
        "redirect_uri": redirect_uri,
        "scope": p["scope"],
        "state": state,
        "response_type": "code",
    })
    return p["authorize"] + "?" + q


def _http_json(url, data=None, headers=None, method="GET"):
    req = Request(url, data=data, headers=headers or {}, method=method)
    with _opener.open(req, timeout=8) as r:
        return json.loads(r.read().decode())


def exchange_code(name, code, redirect_uri, cfg=None):
    """用授权码换 token + userinfo，归一化为 {sub, email, name, email_verified}。失败抛异常。

    ⚠️ `email_verified` 是安全边界，不是可选元数据：GitHub `/user` 的 `email` 是用户可
    自填的**公开邮箱（未经验证）**——若拿它去匹配已有账号，攻击者注册一个 GitHub 账号、
    把公开邮箱改成受害者的邮箱即可**接管受害者本地账号**（典型 OAuth 账号接管）。
    因此：只有 provider 明确断言「已验证」的邮箱才允许参与账号绑定。
    """
    p = PROVIDERS[name]
    c = _cfg(cfg)
    token = _http_json(
        p["token"],
        data=urlencode({
            "client_id": p["client_id"](c),
            "client_secret": p["client_secret"](c),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode(),
        headers={"Accept": "application/json"},
        method="POST",
    )
    access = token.get("access_token")
    if not access:
        raise ValueError("oauth: no access_token in response")
    info = _http_json(
        p["userinfo"],
        headers={"Authorization": "Bearer " + access, "Accept": "application/json"},
    )
    if name == "github":
        sub = str(info.get("id"))
        name_ = info.get("name") or info.get("login") or "github_user"
        # GitHub 的已验证邮箱只能从 /user/emails 拿（/user 的 email 是公开自填字段）
        email, verified = "", False
        with contextlib.suppress(Exception):   # 拿不到邮箱列表就当无已验证邮箱（不影响按 sub 登录）
            for e in _http_json("https://api.github.com/user/emails",
                                headers={"Authorization": "Bearer " + access,
                                         "Accept": "application/json"}):
                if e.get("verified") and e.get("primary"):
                    email = e.get("email") or ""
                    verified = bool(email)
                    break
        if not verified and info.get("email"):
            # 保留作展示名来源，但**明确标记为未验证** → 不参与账号绑定
            email, verified = info.get("email") or "", False
    else:
        sub = str(info.get("sub"))
        email = info.get("email") or ""
        verified = bool(info.get("email_verified")) and bool(email)   # Google 显式给 email_verified
        name_ = info.get("name") or info.get("email") or "google_user"
    return {"sub": sub, "email": (email or "").lower(), "name": name_,
            "email_verified": verified}


def _unique_username(base):
    base = (base or "user").split("@")[0].strip().lower()[:30] or "user"
    cand = base
    i = 1
    while User.query.filter_by(username=cand).first():
        cand = "%s%d" % (base, i)
        i += 1
    return cand


def find_or_create_user(provider, sub, email, name, email_verified=False):
    """按 (provider, sub) 命中已绑账号；否则按**已验证**邮箱匹配；都没有则新建本地用户。

    安全边界：`email_verified=False` 时**绝不按邮箱匹配已有账号**（防 OAuth 账号接管），
    只按 provider 侧不可伪造的 `sub` 命中，或干脆新建一个独立账号。
    """
    link = OAuthAccount.query.filter_by(provider=provider, sub=sub).first()
    if link:
        return db.session.get(User, link.user_id)
    # 仅已验证邮箱可命中既有账号；未验证邮箱只作为新账号的展示信息（且不落 email，避免占位）
    if email and email_verified:
        u = User.query.filter_by(email=email).first()
        if u:
            db.session.add(OAuthAccount(user_id=u.id, provider=provider, sub=sub, email=email))
            db.session.commit()
            return u
    u = User(username=_unique_username(name or email or provider),
             email=email if email_verified else "", role=ROLE_USER)
    u.set_password(secrets.token_hex(24))  # 随机密码：该账号仅走 OAuth 登录
    db.session.add(u)
    db.session.flush()
    db.session.add(OAuthAccount(user_id=u.id, provider=provider, sub=sub,
                                email=email if email_verified else ""))
    db.session.commit()
    return u


def new_state():
    return secrets.token_urlsafe(24)
