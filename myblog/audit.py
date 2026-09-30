"""审计日志写入（v3.25.0 从 `admin/_helpers.py` 拆出）。

**为什么拆**：审计写入是**横切关注点** —— 不止后台在用，前台 API 的主题应用
（`api/theme.py`）、登录审计（`routes.py`）、SEO 推送回执（`seo_push.py`）都要写。
原先它住在 `admin/_helpers.py`，于是产生 `api → admin` 与 `admin → api` 两条顶层边，
把 admin 与 api 拉进**同一个 21 模块强连通分量**（`api.common → admin`、
`admin.ai_summary → api`）——即包级循环依赖。

**为什么放顶层而不是 `utils/`**：`utils/` 包是**刻意的纯工具层**（实测零本地顶层依赖，
`models` 也只依赖 `_time`）。审计写入必须碰 `models.AuditLog` / `models.User`，
塞进 `utils/` 会新增 `utils → models` 重边，破坏那层定位。独立顶层模块只新增
`audit → models` 与 `audit → utils` 两条边，与 `admin/_helpers` 自身同构，不引入新环。

**依赖面刻意收窄**：本模块只依赖 `flask.session`、`models`、`utils.get_client_ip`、
`_time.utcnow` —— **零 admin 依赖**，所以任何层都能安全导入。
"""
import datetime

from flask import session

from models import db, User, AuditLog
from utils import get_client_ip
from _time import utcnow


def log_audit(action, target="", target_id=None, detail="", user=None, ip="", success=True):
    """记录一条后台操作审计日志（v3.0.0 功能4）。

    自动填操作人（传入 user 或当前会话用户）、用户名、来源 IP。
    所有后台写操作（增删改文章/评论/用户/设置/友链等）调用本函数，便于事后追溯。
    success：是否成功（登录失败/操作失败时为 False）。
    异常静默：单条日志失败不影响主流程。
    """
    try:
        if user is None:
            uid = session.get("user_id")
            user = db.session.get(User, uid) if uid else None
        # v3.18.5：审计日志的 IP 必须走 get_client_ip()（与 stats/mcp_write/client_key
        # 同一收口）——原先直接取 X-Forwarded-For 最左段，爆破者可在审计日志里写入
        # 任意 IP（含内网/他人 IP），导致事件追溯与人工封禁决策失效。
        try:
            ip = ip or get_client_ip()
        except Exception:
            ip = ""
        db.session.add(AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=action, target=target, target_id=target_id,
            detail=(detail or "")[:300], ip=ip[:64], success=success,
        ))
        db.session.commit()
    except Exception:
        pass


def log_login_attempt(username, success, ip=""):
    """记录一次后台登录尝试（v3.1.0 新增）。

    无论成功失败都写入审计日志（action='login'），便于追溯异常登录与爆破。
    success=True 记 target='成功'，False 记 target='失败'（含尝试的用户名）。
    无请求上下文时（如离线脚本）安全降级，不抛异常。
    """
    if not ip:
        try:
            # v3.18.5：同 log_audit——不再信任 XFF 最左段（可伪造），走统一收口。
            ip = get_client_ip()
        except Exception:
            ip = ""
    try:
        db.session.add(AuditLog(
            user_id=None, username=(username or "")[:40],
            action="login", target=("成功" if success else "失败"),
            target_id=None, detail=(f"登录尝试：{username}" if not success else "后台登录"),
            ip=ip[:64], success=success,
        ))
        db.session.commit()
    except Exception:
        pass
    # 顺带清理超过保留周期的旧审计日志（含登录日志），避免表无限膨胀（v3.1.0；v3.1.6 周期可配）
    try:
        from flask import current_app as _app
        days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        days = 90
    _purge_audit_logs_older_than(days)


def _purge_audit_logs_older_than(days):
    """清理超过 N 天的审计日志（含登录日志）。轻量：仅当存在时才删除。"""
    try:
        cutoff = utcnow() - datetime.timedelta(days=days)
        deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete()
        if deleted:
            db.session.commit()
    except Exception:
        pass
