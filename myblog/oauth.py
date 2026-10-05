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
        "label": "GitHub",
        "console": "https://github.com/settings/applications/new",
        "doc": "https://docs.github.com/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app",
    },
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "label": "Google",
        "console": "https://console.cloud.google.com/apis/credentials",
        "doc": "https://developers.google.com/identity/protocols/oauth2/web-server",
    },
}

# 凭据存放位置（v3.25.7 新增后台配置入口）。
#
# 优先级：**Setting 表 → 环境变量**。DB 优先是因为「后台能改」是本项目的既定语义
# （同 `site_base()` / SMTP 设置）；环境变量**保留**是为了不破坏既有部署
# （老部署把凭据写在 env 里，改了优先级会让它们的登录突然失效）。
#
# ⚠️ 传了 `cfg` 就**只**读 cfg、不查库 —— 测试用它注入假凭据，也顺带避免
# 「pytest 库全 session 共享」把库里的真值带进断言。
CRED_KEYS = {
    "github": {"client_id": "oauth.github.client_id",
               "client_secret": "oauth.github.client_secret"},
    "google": {"client_id": "oauth.google.client_id",
               "client_secret": "oauth.google.client_secret"},
}
ENV_KEYS = {
    "github": {"client_id": "OAUTH_GITHUB_CLIENT_ID",
               "client_secret": "OAUTH_GITHUB_CLIENT_SECRET"},
    "google": {"client_id": "OAUTH_GOOGLE_CLIENT_ID",
               "client_secret": "OAUTH_GOOGLE_CLIENT_SECRET"},
}


def _cfg(cfg=None):
    """取配置对象（默认当前 app 的 config，便于测试注入）。"""
    if cfg is None:
        from flask import current_app
        cfg = current_app.config
    return cfg


def _cred(name, kind, cfg=None):
    """取一个凭据（`client_id` / `client_secret`）。

    Setting 表里 `client_secret` 存的是 **Fernet 密文**（复用
    `backup_settings.encrypt_secret`，与 IndexNow token / 备份密码同一套），
    这里透明解密。
    """
    if name not in CRED_KEYS:
        return ""
    if cfg is None:
        raw = ""
        with contextlib.suppress(Exception):
            from utils import get_setting
            raw = (get_setting(CRED_KEYS[name][kind], "") or "").strip()
        if raw:
            if kind == "client_secret":
                from backup_settings import decrypt_secret
                raw = decrypt_secret(raw)
            if raw.strip():
                return raw.strip()
        cfg = _cfg()          # 库里没有 → 回退环境变量
    return str(_cfg(cfg).get(ENV_KEYS[name][kind]) or "").strip()


def is_configured(name, cfg=None):
    """provider 是否已配置凭据（缺任一即休眠）。"""
    if name not in PROVIDERS or name not in CRED_KEYS:
        return False
    return bool(_cred(name, "client_id", cfg)) and bool(_cred(name, "client_secret", cfg))


def configured_providers(cfg=None):
    return [n for n in PROVIDERS if is_configured(n, cfg)]


def callback_url(name, base=None):
    """该 provider 的回调地址（绝对 URL）；`site_base()` 未配置时返回**空串**。

    纯函数（不碰 `request`），后台配置页与 `api/auth.py` 共用同一份推导逻辑 ——
    两处各写一遍必然漂移，而回调地址写错是 OAuth 最常见的失败原因。
    """
    if name not in PROVIDERS:
        return ""
    b = str(base if base is not None else _site_base() or "").rstrip("/")
    return (b + "/api/auth/oauth/" + name + "/callback") if b else ""


def _site_base():
    """对外地址真相源（DB site_url → env SITE_URL → 空串）。"""
    with contextlib.suppress(Exception):
        from utils import site_base
        return site_base()
    return ""


def build_authorize_url(name, redirect_uri, state, cfg=None):
    p = PROVIDERS[name]
    q = urlencode({
        "client_id": _cred(name, "client_id", cfg),
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
    token = _http_json(
        p["token"],
        data=urlencode({
            "client_id": _cred(name, "client_id", cfg),
            "client_secret": _cred(name, "client_secret", cfg),
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


def find_or_create_user(provider, sub, email, name, email_verified=False, bind_user_id=None):
    """按 (provider, sub) 命中已绑账号；否则新建本地账号，或在**已登录会话**内认领。

    安全边界（v3.21.2 审计收紧，别改回去）：

    1. `email_verified=False` 时绝不按邮箱匹配 —— 这是 R93 §93.1 修的那一半。
    2. **即使 provider 已验证邮箱，也不按邮箱静默认领本地账号** —— 另一半：不可信
       的不只是第三方给的邮箱，**本地库里存的邮箱同样没被验证过**。本站注册路径
       （`api/auth.py::auth_register`、`routes.py::register`）对 email 只做 `strip()`，
       无格式校验、无唯一约束、无所有权验证。于是原先的
       `User.query.filter_by(email=email).first()` 可被这样利用：攻击者先用受害者
       邮箱注册一个自己知道密码的账号 → 受害者首次「用 Google 登录」→ 按邮箱匹配
       把他/她的 provider 身份**永久**绑到攻击者那个账号（此后每次 OAuth 登录都落进
       攻击者的账号，且 `OAuthAccount` 命中在先，再也改不回来）。
    3. 认领既有账号只保留一个入口：该账号**当前已登录**（`bind_user_id` 取自服务端
       session，身份已由密码 / 第二因素证明）。绑到自己账号是用户本人的决定。
    4. 未验证邮箱不作为本地账号的 `email` 落库（避免占位与后续误匹配）。
    """
    link = OAuthAccount.query.filter_by(provider=provider, sub=sub).first()
    if link:
        return db.session.get(User, link.user_id)
    if bind_user_id:
        u = db.session.get(User, bind_user_id)
        if u is not None:
            try:
                db.session.add(OAuthAccount(user_id=u.id, provider=provider, sub=sub,
                                            email=email if email_verified else ""))
                db.session.commit()
            except Exception:
                # 并发回调抢同一 (provider, sub)：唯一约束 `uq_oauth_provider_sub`
                # 会拒掉后来者。回滚后按已存在的绑定走，不让它冒成 500。
                db.session.rollback()
                link = OAuthAccount.query.filter_by(provider=provider, sub=sub).first()
                if link:
                    return db.session.get(User, link.user_id)
                raise
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
