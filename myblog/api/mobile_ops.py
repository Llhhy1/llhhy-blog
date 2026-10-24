"""移动端管理接口 · 第二批「数据与设置」（D8.3 ②，v4.10.0）。

D8.3 把移动端第二批拆成两块：
  ① 前台浏览（文章列表 / 正文 / 搜索 / 归档 / 微动态 / 博客圈…）——
     **纯 App 侧界面**，基本不需要新端点，不在本仓库范围内；
  ② 数据与设置（统计报表 / 审计日志 / 备份 / 站点设置 / SEO 推送 / 证书 / 用户角色）——
     需要服务端 JSON，就是本文件。

## 权限口径（D8.3 明确要求「每加一批都要重新判」，不许沿用「管理员可读」）

逐条对齐后台页面，而不是图省事统统给 `admin`：

| 端点 | 后台对应页 | 该页装饰器 | 这里 |
| --- | --- | --- | --- |
| `/mobile/stats/report` | `admin.stats`（访问统计） | `@admin_required` | `admin=True` |
| `/mobile/audit-logs` | `admin.audit_logs` | `@login_required @super_required` | `super_only=True` |
| `/mobile/backups` | `admin.backup` | `@super_required` | `super_only=True` |
| `/mobile/settings` | `admin.settings`（站点设置） | `@super_required` | `super_only=True` |
| `/mobile/seo/summary` | `admin.seo_console`（收录） | `@super_required` | `super_only=True` |
| `/mobile/cert` | 证书看护（诊断页） | 超管 | `super_only=True` |
| `/mobile/users` | `admin.users` | `@login_required @super_required` | `super_only=True` |

**为什么审计 / 用户 / 设置不能只给 `admin`**：这三处能拼出「谁在什么时候从哪个 IP
改了什么」以及全部站点配置。内容管理员需要的是内容，不是这些 —— 与 R121.4 /
R122 的既有界线一致。

## 只读优先

除「改角色」外全部只读。**刻意不做**的写操作及理由：
- 备份触发 / 恢复：`create_backup()` 内含 scp/curl 远程同步（`_run(timeout=300)`），
  同步占并发槽会拖垮整站 —— 后台页也早就改成「后台任务 + 轮询」了，移动端没有
  任务轮询通道，硬做只会做出一个必超时的接口。
- 站点设置写入：30+ 个键各有校验规则，漏一条就是配置损坏。网页端已有完整表单，
  App 端先把「看」做好比做一个半成品写入更实在。
"""
from flask import jsonify, request

from models import AuditLog, SeoSubmission, User, db
from utils import fmt_bj, get_setting

from .common import api_bp
from .mobile import _page_args, _paged, _role

# 站点设置里**可以对外展示**的键（白名单）。凭据类（SMTP 密码 / OSS Secret /
# 推送 token / 各类 *_key）一律不在其中 —— 白名单而不是黑名单，是因为黑名单
# 会在「新增一个密钥键」时静默泄漏，白名单最坏只是漏显示。
_SETTING_KEYS = [
    ("site_name", "站点名称"),
    ("site_title", "首页标题"),
    ("site_description", "站点描述"),
    ("site_url", "站点地址"),
    ("about_content", "关于内容"),
    ("comment_require_approval", "评论需审核"),
    ("comment_email_required", "评论必填邮箱"),
    ("captcha_enabled", "验证码总开关"),
    ("og_template", "分享卡模板"),
    ("accent_color", "主题色"),
    ("beian_code", "备案号"),
]

# 用户角色白名单（与 models.ROLE_* 一致）
_ROLES = ("user", "admin", "super")


# --------------------------------------------------------------- 统计多维报表


@api_bp.route("/mobile/stats/report")
def mobile_stats_report():
    """访问统计多维报表：区间汇总 + 日趋势 + 设备 / 浏览器 / 来源分布。

    复用 `stats.compute_range_stats()`（后台统计页同一实现），只额外补两样它没有的：
    **日趋势序列**（App 画折线用）与**设备 / 浏览器分布**（v4.9.0 新增的两列）。
    """
    _user, err = _role(admin=True)
    if err:
        return err
    import stats as stats_mod

    range_key = (request.args.get("range") or "").strip()
    data = stats_mod.compute_range_stats(range_key)

    # 日趋势：区间内每天 PV / 真人 PV / UV
    trend = []
    try:
        from models import VisitLog
        from sqlalchemy import func
        rows = (db.session.query(
                    VisitLog.date,
                    func.count(VisitLog.id),
                    func.sum(func.cast(VisitLog.is_bot.is_(False), db.Integer)))
                .filter(VisitLog.date >= data["start"], VisitLog.date <= data["end"])
                .group_by(VisitLog.date).order_by(VisitLog.date.asc()).all())
        for day, pv, human in rows:
            trend.append({"date": day, "pv": int(pv or 0), "human_pv": int(human or 0)})
    except Exception:  # noqa: BLE001  趋势是附加信息，失败不该让整张报表 500
        trend = []

    return jsonify({
        "range": {k: data[k] for k in ("key", "label", "start", "end", "days")},
        "summary": {k: data[k] for k in ("pv", "uv", "human_pv", "human_uv",
                                        "bot_pv", "bot_uv", "new_comments")},
        "trend": trend,
        "top_paths": data.get("top_paths", []),
        "top_regions": data.get("top_regions", []),
        "top_referrers": data.get("top_referrers", []),
        # 设备 / 浏览器沿用固定 30 天窗口（_top_devices/_top_browsers 的既有口径），
        # 不跟 range 走 —— 两套窗口混用会让人误读，这里在字段名上写明。
        "devices_30d": stats_mod._top_devices(limit=10, days=30),
        "browsers_30d": stats_mod._top_browsers(limit=10, days=30),
    })


# ------------------------------------------------------------------- 审计日志


@api_bp.route("/mobile/audit-logs")
def mobile_audit_logs():
    """后台操作审计日志（分页，可按 action / 成败过滤）。

    ⚠️ 超管专属：`ip` 是原文（后台审计页也只给超管看）。`payload` 里可能有
    配置变更前的快照，**不返回** —— 快照可能含密钥类键的历史值。
    """
    _user, err = _role(super_only=True)
    if err:
        return err
    page, per_page = _page_args(default=50)
    q = AuditLog.query
    action = (request.args.get("action") or "").strip()
    if action:
        q = q.filter(AuditLog.action == action)
    ok = (request.args.get("success") or "").strip().lower()
    if ok in ("1", "true", "yes"):
        q = q.filter(AuditLog.success.is_(True))
    elif ok in ("0", "false", "no"):
        q = q.filter(AuditLog.success.is_(False))
    q = q.order_by(AuditLog.created_at.desc())

    def _ser(a):
        return {
            "id": a.id,
            "username": a.username,
            "action": a.action,
            "target": a.target,
            "target_id": a.target_id,
            "detail": a.detail,
            "ip": a.ip,
            "success": bool(a.success),
            "created_at": fmt_bj(a.created_at, "%Y-%m-%d %H:%M:%S"),
        }

    # ⚠️ `_paged()` 内部已经 `jsonify()` —— 外面**不能**再包一层，
    # 否则就是把 Response 塞进 jsonify，运行期报 "not JSON serializable"（500）。
    return _paged(q, page, per_page, _ser)


# --------------------------------------------------------------------- 备份


@api_bp.route("/mobile/backups")
def mobile_backups():
    """备份文件列表 + 远端同步状态（**只读**，不提供触发/恢复，理由见模块 docstring）。"""
    _user, err = _role(super_only=True)
    if err:
        return err
    import backup as backup_mod
    try:
        backups = backup_mod.list_backups()
    except Exception:  # noqa: BLE001  备份目录不可读时给空列表 + 明确提示，不 500
        return jsonify({"backups": [], "remote": {}, "error": "备份目录不可读"}), 200

    items = []
    for b in backups:
        items.append({
            "file": b.get("file"),
            "size": b.get("size") or 0,
            "size_h": backup_mod.fmt_size(b.get("size") or 0),
            "stamp": backup_mod.backup_stamp(b.get("file")),
        })
    try:
        remote = backup_mod.remote_status()
    except Exception:  # noqa: BLE001  远端探测是附加信息
        remote = {}
    return jsonify({"backups": items, "total": len(items), "remote": remote})


# ----------------------------------------------------------------- 站点设置


@api_bp.route("/mobile/settings")
def mobile_settings():
    """站点设置**只读**（白名单键 + 是否已配置），凭据类键完全不出现。"""
    _user, err = _role(super_only=True)
    if err:
        return err
    items = []
    for key, label in _SETTING_KEYS:
        val = get_setting(key)
        items.append({
            "key": key,
            "label": label,
            "value": "" if val is None else str(val),
            "configured": val not in (None, ""),
        })
    # 顺带告诉客户端「哪些凭据已配置」——只给布尔，不给值。
    # 页面上原先看不到这些，App 至少能显示「SMTP 已配置 / 未配置」。
    from push_settings import resolve_all as _push_all
    try:
        push = _push_all()
        channels = {
            "telegram": bool(push.get("push_telegram_token") and push.get("push_telegram_chat")),
            "wecom": bool(push.get("push_wecom_webhook")),
        }
    except Exception:  # noqa: BLE001  推送配置读取失败只影响状态显示
        channels = {"telegram": False, "wecom": False}
    return jsonify({"settings": items, "push_channels": channels})


# ---------------------------------------------------------------- SEO 收录


@api_bp.route("/mobile/seo/summary")
def mobile_seo_summary():
    """收录概览：按引擎统计各状态条数 + 最近 20 条提交记录。

    只读。真正的推送动作仍走网页端「收录」控制台 —— 主动推送有配额
    （百度按日限额）与不可逆性，移动端点一下就可能把配额打完。
    """
    _user, err = _role(super_only=True)
    if err:
        return err
    from sqlalchemy import func
    rows = (db.session.query(SeoSubmission.engine, SeoSubmission.status,
                             func.count(SeoSubmission.id))
            .group_by(SeoSubmission.engine, SeoSubmission.status).all())
    by_engine = {}
    for engine, status, cnt in rows:
        by_engine.setdefault(engine, {})[status] = int(cnt or 0)

    recent = (SeoSubmission.query.order_by(SeoSubmission.id.desc()).limit(20).all())
    items = []
    for r in recent:
        items.append({
            "id": r.id,
            "post_id": r.post_id,
            "engine": r.engine,
            "status": r.status,
            "updated_at": fmt_bj(getattr(r, "updated_at", None) or getattr(r, "created_at", None),
                                 "%Y-%m-%d %H:%M"),
        })
    return jsonify({"by_engine": by_engine, "recent": items})


# ------------------------------------------------------------------- 证书


@api_bp.route("/mobile/cert")
def mobile_cert():
    """证书看护状态（读 `cert_watch` 的持久化状态，**不触发新的探测**）。

    为什么不在这个接口里实时探测：探测要连外站 TLS（6s 超时），移动端下拉刷新
    会变成「每次都等 6 秒」。巡检由后台定时任务做，这里只读结果。
    """
    _user, err = _role(super_only=True)
    if err:
        return err
    import cert_watch
    try:
        state = cert_watch.read_state() or {}
    except Exception:  # noqa: BLE001  状态文件损坏时给空态，不 500
        state = {}
    level = ""
    try:
        level = cert_watch.status_level(state.get("status"))
    except Exception:  # noqa: BLE001
        level = ""
    return jsonify({"state": state, "level": level, "warn_days": cert_watch.WARN_DAYS})


# --------------------------------------------------------------- 用户与角色


@api_bp.route("/mobile/users")
def mobile_users():
    """用户列表（分页，可按角色过滤）。**不含 password_hash / 邮箱全文**。

    邮箱按 R122 的 PII 分层口径遮敏：超管也给遮敏形态 —— 用户管理页需要的是
    「这是谁」，不是「他的完整邮箱」；真要联系用户走网页端。
    """
    _user, err = _role(super_only=True)
    if err:
        return err
    page, per_page = _page_args()
    q = User.query
    role = (request.args.get("role") or "").strip()
    if role in _ROLES:
        q = q.filter(User.role == role)
    kw = (request.args.get("q") or "").strip()
    if kw:
        q = q.filter(User.username.like("%" + kw + "%"))
    q = q.order_by(User.id.asc())

    def _ser(u):
        return {
            "id": u.id,
            "username": u.username,
            "email_masked": _mask_email(u.email),
            "role": u.role,
            "role_label": u.role_label,
            "must_change_password": bool(u.must_change_password),
            "created_at": fmt_bj(u.created_at, "%Y-%m-%d"),
        }

    return _paged(q, page, per_page, _ser)


def _mask_email(email):
    """邮箱遮敏：`ab***@ex***.com`。空值返回空串。"""
    e = (email or "").strip()
    if "@" not in e:
        return ""
    name, domain = e.split("@", 1)
    head = name[:2] if len(name) > 2 else name[:1]
    dmain = domain.split(".")[0]
    dhead = dmain[:2] if len(dmain) > 2 else dmain[:1]
    tld = "." + domain.split(".")[-1] if "." in domain else ""
    return "%s***@%s***%s" % (head, dhead, tld)


@api_bp.route("/mobile/user/<int:uid>/role", methods=["POST"])
def mobile_user_set_role(uid):
    """改用户角色（超管专属）。

    三条硬约束（任何一条放宽都会造成「把自己锁在门外」）：
    1. **不能改自己的角色** —— 超管把自己降成 admin 后，若系统里没有第二个超管，
       就再没有任何人能改回来（网页端也是同一限制）。
    2. 目标角色必须在白名单内（防止拼错成 "Super" 这种既不是 super 也不是 admin 的值，
       落库后该账号**既进不了后台也不满足任何角色判断**）。
    3. 改角色必须 `session_version + 1`：否则目标用户已登录的会话仍带着旧权限缓存，
       降级不生效（与改密码踢下线的处置一致）。
    """
    user, err = _role(super_only=True)
    if err:
        return err
    target = db.session.get(User, uid)
    if not target:
        return jsonify({"error": "用户不存在"}), 404
    if target.id == user.id:
        return jsonify({"error": "不能修改自己的角色（避免把自己锁在后台外）"}), 400

    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    if role not in _ROLES:
        return jsonify({"error": "角色只能是 %s 之一" % " / ".join(_ROLES)}), 400

    old = target.role
    if old == role:
        return jsonify({"ok": True, "user": {"id": target.id, "role": role}})
    target.role = role
    target.session_version = (target.session_version or 0) + 1
    db.session.commit()

    from audit import log_audit
    log_audit("user_role", target="user", target_id=target.id,
              detail="%s → %s" % (old, role))
    return jsonify({"ok": True, "user": {"id": target.id, "role": role}})
