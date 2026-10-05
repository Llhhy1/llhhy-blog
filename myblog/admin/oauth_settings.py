# -*- coding: utf-8 -*-
"""后台「第三方登录」配置页（v3.25.7）。

**为什么必须补这个页面**：v3.21.0 把 GitHub / Google 登录的后端（`oauth.py`）
与前端（`LoginView.vue` 按钮）都写完了，**唯独没留配置入口** —— 凭据只能改
环境变量再重启。结果这个功能从上线起**一次都没活过**：生产实测
`/api/auth/oauth/providers` 返回 `{"providers":[]}`，而登录页的
`v-if="state.oauthProviders.length"` 为假 → 整个第三方登录区块不渲染，
页面上一个按钮都没有（`curl /login | grep -c -i oauth` = 0）。绑定页只写了一句
「需设置 `OAUTH_GITHUB_CLIENT_ID/SECRET` 并重启」，**没说去哪儿注册、
回调地址填什么** —— 这就是「太难用」的真正来源。

设计取舍（写下来，避免后人改回去）：

1. **凭据存 Setting 表，DB 优先于环境变量。** 「后台能改」是本项目既定语义
   （同 `site_base()` / SMTP 设置）；环境变量**保留兜底**，老部署不受影响。
2. **ClientSecret 用 Fernet 加密落库**（复用 `backup_settings.encrypt_secret`，
   与 IndexNow token / 备份密码同一套），页面只回显掩码；**留空 = 保持原值**，
   清除要走**显式动作**（同邮件设置范式）。ClientId 不是秘密，明文回显便于核对。
3. **审计只写 provider 名，绝不写值** —— `detail` 会进 CSV 导出。
4. **页面直接把回调地址摆出来**（`oauth.callback_url()` 纯函数推导）：
   回调地址填错是 OAuth 最常见的失败原因，不该让人去猜。
5. `@super_required` + 全局 CSRF：改这里等于改「谁能登进这个站点」。
"""
from ._helpers import log_audit, super_required, admin_bp     # 同一蓝图对象
from flask import flash, redirect, render_template, request, url_for
from models import Setting, db


def _read_raw(key):
    """读 Setting 原始值（client_secret 存的是 `bkenc$` 密文）。"""
    row = Setting.query.filter_by(key=key).first()
    return (row.value or "") if row else ""


def _write(key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))


def _drop(key):
    """删除某个 key（清除凭据）。返回是否真的删掉了。"""
    row = Setting.query.filter_by(key=key).first()
    if row is None:
        return False
    db.session.delete(row)
    return True


def _mask(v):
    """掩码：非空且长度 > 4 显示前 2 后 2（与 `backup_settings.mask_value` 同规则）。"""
    if not v:
        return ""
    if len(v) <= 4:
        return "****"
    return v[:2] + "****" + v[-2:]


def _rows():
    """每个 provider 的展示数据：状态 / 回显值 / 回调地址 / 注册引导。

    状态刻意分三档而不是「已配置 / 未配置」两档：**只填了一半**是最常见的
    失败态（复制 ClientId 时把 Secret 漏了），两档模型下它会显示成「未启用」，
    让人反复检查自己是不是漏了哪一步。
    """
    from oauth import CRED_KEYS, ENV_KEYS, PROVIDERS, _cred, callback_url
    from utils import site_base

    base = site_base() or ""
    out = []
    for name, meta in PROVIDERS.items():
        keys = CRED_KEYS[name]
        cid = _read_raw(keys["client_id"]).strip()
        secret_enc = _read_raw(keys["client_secret"]).strip()
        # **实际生效值**（含环境变量兜底）——「我填了但没生效」和「我没填」必须分得开
        eff_id = _cred(name, "client_id")
        eff_secret = _cred(name, "client_secret")
        if eff_id and eff_secret:
            state = "ok"
        elif eff_id or eff_secret:
            state = "half"
        else:
            state = "off"
        out.append({
            "name": name,
            "label": meta.get("label", name),
            "console_url": meta.get("console", ""),
            "doc_url": meta.get("doc", ""),
            "state": state,
            "state_text": {"ok": "已启用", "half": "只填了一半 · 不生效",
                           "off": "未启用"}[state],
            "client_id": cid,
            "secret_set": bool(eff_secret),
            "secret_mask": _mask(eff_secret),
            # 凭据来自环境变量时明确提示「去库里改没用」，免得白折腾
            "from_env": bool(eff_secret and not secret_enc),
            "env_names": (ENV_KEYS[name]["client_id"], ENV_KEYS[name]["client_secret"]),
            "callback": callback_url(name, base),
        })
    return out, base


@admin_bp.route("/oauth-settings", methods=["GET", "POST"])
@super_required
def oauth_settings():
    """第三方登录凭据配置。

    CSRF 由 `app._csrf_protect` 全局钩子强制（模板放 `csrf_input()`），此处不重复校验。
    """
    import oauth as oauth_svc

    if request.method == "POST":
        action = request.form.get("action", "save")
        name = (request.form.get("provider") or "").strip()
        if name not in oauth_svc.CRED_KEYS:
            flash("未知的第三方登录渠道", "error")
            return redirect(url_for("admin.oauth_settings"))
        keys = oauth_svc.CRED_KEYS[name]

        if action == "clear":
            n = (_drop(keys["client_id"]) or 0) + (_drop(keys["client_secret"]) or 0)
            db.session.commit()
            log_audit("oauth_settings_clear", "oauth", None,
                      f"清除 {name} 第三方登录凭据（{n} 项）")
            flash(f"已清除 {name} 的凭据，前台登录按钮会随之消失")
            return redirect(url_for("admin.oauth_settings"))

        cid = (request.form.get("client_id") or "").strip()
        secret = (request.form.get("client_secret") or "").strip()
        _write(keys["client_id"], cid)
        # Secret：留空 = 保持原值（页面不回显明文，留空才是「不打算改」）
        if secret:
            from backup_settings import encrypt_secret
            _write(keys["client_secret"], encrypt_secret(secret))
        db.session.commit()
        # ⚠️ 审计只记 provider 名 —— 绝不能把凭据写进 detail（它会进 CSV 导出）
        log_audit("oauth_settings_save", "oauth", None,
                  f"保存 {name} 第三方登录凭据"
                  f"（client_id={'已填' if cid else '未填'}，"
                  f"client_secret={'已更新' if secret else '未改动'}）")
        if cid and secret:
            flash(f"{name} 凭据已保存并启用")
        elif cid or secret:
            flash(f"{name} 只保存了一半 —— Client ID 与 Client Secret 都齐了才会启用")
        else:
            flash(f"{name} 凭据已清空（等同于未启用）")
        return redirect(url_for("admin.oauth_settings"))

    rows, base = _rows()
    return render_template("admin/oauth_settings.html", rows=rows, site_base=base)
