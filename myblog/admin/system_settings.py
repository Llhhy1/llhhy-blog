# -*- coding: utf-8 -*-
"""后台「系统设置」——运营开关集中配置（v3.25.8）。

**为什么有这一页**：一批功能开关只能改环境变量再重启（2FA、开放注册、验证码、
强密码、登录延迟、审计保留）。实测生产 `/www/server/python_project/vhost/env/myblog.env`
里**一个 `BLOG_TWOFA_ENABLED` 都没有** → 2FA 从 v3.21.0 上线起一直是关着的，
而页面上只写着一句「需设置环境变量 BLOG_TWOFA_ENABLED=true 并重启」——
**告诉人怎么改服务器，却不给入口**。这与 v3.25.7 修的第三方登录是同款缺陷。

**哪些开关该进这里，哪些不该**（判据：运营会不会频繁改 × 读取频率）：

| 该进（低频读、要常改） | 不该进 |
|---|---|
| 2FA / 开放注册 / 验证码 / 强密码 / 登录延迟 / 审计保留 | `SECRET_KEY` `ADMIN_PASSWORD` `DATABASE_URL` `MCP_*_TOKEN`（**根信任**，进 DB 等于让数据面泄露=伪造会话） |
| | `COOKIE_SECURE` `CORS_ORIGIN` `TRUSTED_PROXIES` `SESSION_IDLE_MINUTES`（每请求都要判断，进 DB 是拿查询换配置） |
| | `ENABLED_PLUGINS`（启动时读，进 DB 照样要重启） |

**每个开关都显示「当前生效值 + 来源」**（数据库 / 环境变量 / 系统默认）：
只显示结果不显示来源的话，运营改了没生效根本无从查起。

**审计记录改动前后值**（`config_rollback` 的快照也会拍到，`audit_log.detail`
只写值的安全；本模块的开关**都不是密钥**，可明文记录以便回溯）。
"""
import contextlib

from ._helpers import log_audit, super_required, admin_bp     # 同一蓝图对象
from flask import flash, redirect, render_template, request, url_for
from models import Setting, db
from utils import flag_bool, flag_num, get_setting


# 每个开关：Setting key、config 属性名、类型、取值范围、说明、是否建议开启。
# 顺序 = 页面展示顺序（按「安全 → 注册 → 运维」分组，危险的在前）。
SPECS = [
    {"group": "安全", "key": "twofa_enabled", "config": "TWOFA_ENABLED",
     "env": "BLOG_TWOFA_ENABLED", "type": "bool", "default": False,
     "label": "两步验证（2FA / TOTP）",
     "hint": "所有登录者都要过一次 TOTP 动态码。**你需要先给自己绑定**（后台 → 两步验证），"
             "否则打开后你自己会被挡在门外。忘记动态码可用恢复码。"},
    {"group": "安全", "key": "strong_password", "config": "STRONG_PASSWORD",
     "env": "STRONG_PASSWORD", "type": "bool", "default": True,
     "label": "强密码策略",
     "hint": "注册与改密时要求密码至少 8 位且含字母 + 数字。关闭会显著降低抗撞库能力。"},
    {"group": "安全", "key": "strong_password_mixed_case", "config": "STRONG_PASSWORD_MIXED_CASE",
     "env": "STRONG_PASSWORD_MIXED_CASE", "type": "bool", "default": False,
     "label": "密码还需同时含大小写字母",
     "hint": "在强密码之上再收紧一层。个人博客通常不必，两根以上才值得。"},
    {"group": "安全", "key": "login_delay_seconds", "config": "LOGIN_DELAY_SECONDS",
     "env": "LOGIN_DELAY_SECONDS", "type": "num", "default": 1.0,
     "lo": 0.0, "hi": 30.0, "step": "0.5",
     "label": "登录失败后统一延迟（秒）",
     "hint": "登录失败时先等这么久再回错误，消除「用户名存在与否」的时间差，防用户名枚举。"
             "**置 0 会关掉这层防护**。"},

    {"group": "注册", "key": "open_register", "config": "BLOG_OPEN_REGISTER",
     "env": "BLOG_OPEN_REGISTER", "type": "bool", "default": True,
     "label": "开放公开注册",
     "hint": "关闭后注册接口与注册页一并关闭（已注册用户不受影响）。"},
    {"group": "注册", "key": "captcha_enabled", "config": "CAPTCHA_ENABLED",
     "env": "CAPTCHA_ENABLED", "type": "bool", "default": True,
     "label": "图形验证码",
     "hint": "注册 / 留言 / 评论需要过验证码。关掉等于开放机器刷量。"},

    {"group": "运维", "key": "audit_log_days", "config": "AUDIT_LOG_DAYS",
     "env": "AUDIT_LOG_DAYS", "type": "int", "default": 90,
     "lo": 1, "hi": 3650, "step": "1",
     "label": "操作日志保留天数",
     "hint": "超期记录由每日定时任务清理。调小可省空间，调大要评估审计追溯需求。"},
]

_BY_KEY = {s["key"]: s for s in SPECS}


def _source(spec):
    """当前值的来源：`db` / `env` / `default`，以及生效值。

    **来源必须显式展示**：只显示生效值的话，运营在后台改了却发现没生效
    （多半是值写进了数据库、但某个读点还在读环境变量）根本无从查起。
    """
    key, ck = spec["key"], spec["config"]
    raw = get_setting(key)
    has_db = raw is not None and str(raw).strip() != ""
    if has_db:
        src = "db"
    else:
        src = "default"
        with contextlib.suppress(Exception):
            from flask import current_app
            if current_app.config.get(ck) is not None:
                src = "env"
    if spec["type"] == "bool":
        val = flag_bool(key, ck, spec["default"])
    elif spec["type"] == "int":
        val = flag_num(key, ck, spec["default"], int)
    else:
        val = flag_num(key, ck, spec["default"], float)
    return val, src, (raw if has_db else None)


def _coerce(spec, raw):
    """表单字符串 → 目标类型；非法返回 (None, 错误文案)。"""
    txt = (raw or "").strip()
    if spec["type"] == "bool":
        if txt in ("true", "1", "on", "yes"):
            return True, None
        if txt in ("false", "0", "off", "no", ""):
            return False, None
        return None, "请选择开或关"
    if txt == "":
        return None, "不能为空"
    try:
        num = float(txt)
    except ValueError:
        return None, "请填数字"
    lo, hi = spec.get("lo"), spec.get("hi")
    if lo is not None and num < lo:
        return None, "不能小于 %s" % lo
    if hi is not None and num > hi:
        return None, "不能大于 %s" % hi
    return (int(num) if spec["type"] == "int" else num), None


def _write(key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))


def _drop(key):
    row = Setting.query.filter_by(key=key).first()
    if row is None:
        return False
    db.session.delete(row)
    return True


@admin_bp.route("/system-settings", methods=["GET", "POST"])
@super_required
def system_settings():
    """运营开关配置。

    CSRF 由 `app._csrf_protect` 全局钩子强制（模板放 `csrf_input()`），此处不重复校验。
    """
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "reset":
            key = (request.form.get("key") or "").strip()
            spec = _BY_KEY.get(key)
            if spec is None:
                flash("未知的开关", "error")
                return redirect(url_for("admin.system_settings"))
            before, _, _ = _source(spec)
            _drop(key)
            db.session.commit()
            log_audit("system_settings_reset", "config", None,
                      f"恢复默认：{spec['label']}（{before} → {spec['default']}，改回环境变量/默认）")
            flash(f"「{spec['label']}」已恢复默认（若环境变量有设，将以环境变量为准）")
            return redirect(url_for("admin.system_settings"))

        changed, errs = [], []
        for spec in SPECS:
            if ("k_" + spec["key"]) not in request.form:
                continue          # 页面上没提交这一项（部分提交/被改过表单）
            val, err = _coerce(spec, request.form.get("k_" + spec["key"]))
            if err:
                errs.append(f"{spec['label']}：{err}")
                continue
            before, src, _ = _source(spec)
            if before == val and src == "db":
                continue          # 没变就不写，省一次 UPDATE 与一条审计
            _write(spec["key"], "true" if val is True else ("false" if val is False else str(val)))
            changed.append(f"{spec['label']} {before} → {val}")
        db.session.commit()
        # 这些开关都不是密钥，明文记值才能回溯「谁在什么时候把 2FA 关了」
        if changed:
            log_audit("system_settings_save", "config", None,
                      "修改系统设置：" + "；".join(changed))
        if errs:
            for e in errs:
                flash(e, "error")
        if changed:
            flash("已保存并**立即生效**（无需重启）：" + "；".join(changed))
        if not changed and not errs:
            flash("没有改动")
        return redirect(url_for("admin.system_settings"))

    rows = []
    for spec in SPECS:
        val, src, raw = _source(spec)
        rows.append(dict(spec, value=val, source=src, raw=raw))
    return render_template("admin/system_settings.html", rows=rows)
