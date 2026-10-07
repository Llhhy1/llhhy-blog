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
import re

from flask import session

from models import db, User, AuditLog
from utils import get_client_ip
from _time import utcnow


# R115 审计：detail 的脱敏原先**只靠写入方自律**（docstring 立了规矩，
# 实测当前唯一生产者 `config_rollback.snapshot_settings()` 的 key 列表也确实无密钥）。
# 但 `log_audit()` 自己不做任何检查 —— 将来任何一个新调用方把
# `password=hunter2` 写进 detail，就是一条**可导出、可截图**的凭据泄漏。
# 这里加一道与 `mcp_diag._redact()` 同款的兜底：宁可误伤（把长串打码），
# 也不能让凭据进日志。**这是纵深防御，不是替代上面那条纪律。**
_DETAIL_REDACT = [
    (re.compile(r"(?i)((?:secret[_-]?key|password|passwd|pwd|token|api[_-]?key)\s*[=:]\s*)([^\s,;'\"]+)"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})"), r"\1***"),
    (re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})"), "sk-***"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})"), "gh*_***"),
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})"), "AKIA***"),
    (re.compile(r"\b(bkenc\$[A-Za-z0-9_\-]{20,})"), "bkenc$***"),
]


def _redact_detail(text):
    """对 audit detail 做兜底脱敏（不抛异常，失败原样返回——审计不该因脱敏而丢日志）。"""
    if not text:
        return text
    s = str(text)
    for pat, rep in _DETAIL_REDACT:
        s = pat.sub(rep, s)
    return s



def log_audit(action, target="", target_id=None, detail="", user=None, ip="", success=True,
              payload=None):
    """记录一条后台操作审计日志（v3.0.0 功能4）。

    自动填操作人（传入 user 或当前会话用户）、用户名、来源 IP。
    所有后台写操作（增删改文章/评论/用户/设置/友链等）调用本函数，便于事后追溯。
    success：是否成功（登录失败/操作失败时为 False）。
    异常静默：单条日志失败不影响主流程。

    **payload（v3.25.2）**：结构化载荷（dict 或 str），序列化后进 `AuditLog.payload`。
    目前**只用于配置快照**（见 config_rollback.snapshot_settings）。

    ⚠️ **payload 里可以放配置值，detail 里绝不可以** —— detail 会出现在审计列表页、
    CSV 导出、并在超管屏幕上显示；把密码/SMTP 授权码/token 写进 detail 等于
    把凭据抄进了可导出、可截图的日志。**detail 只放「改了哪几个 key」这类摘要。**
    另注意 payload 同样会进 CSV 导出的实现范围，导出时必须排除该列。
    """
    try:
        if user is None:
            # v3.25.2：**必须先判 has_request_context()**。
            # `session.get()` 在无请求上下文（CLI / 定时任务 / 单元测试）时抛
            # RuntimeError: Working outside of request context —— 而这个调用在
            # 旧版里位于**最外层 try 内**，异常被 `except Exception: pass`
            # 静默吞掉，结果是**整条审计一条都没写**、且无任何迹象。
            # 配置回滚（config_rollback）在保存设置时先拍快照，走的正是这条路；
            # 测试里没有请求上下文，于是「快照功能看起来完全失效」。
            # 判断顺序：无请求上下文 → 不取会话用户（user 保持 None），继续写日志。
            try:
                from flask import has_request_context
                if has_request_context():
                    uid = session.get("user_id")
                    user = db.session.get(User, uid) if uid else None
            except Exception:
                user = None
        # v3.18.5：审计日志的 IP 必须走 get_client_ip()（与 stats/mcp_write/client_key
        # 同一收口）——原先直接取 X-Forwarded-For 最左段，爆破者可在审计日志里写入
        # 任意 IP（含内网/他人 IP），导致事件追溯与人工封禁决策失效。
        try:
            ip = ip or get_client_ip()
        except Exception:
            ip = ""
        snap = None
        if payload is not None:
            if isinstance(payload, str):
                snap = payload
            else:
                import json as _json
                try:
                    # ensure_ascii=False：快照里有中文值（站点标题/公告等），
                    # 转成 \uXXXX 会让排障时肉眼不可读。
                    snap = _json.dumps(payload, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    return          # 序列化不了就不写这条 —— 半截快照比没有更危险
        db.session.add(AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=action, target=target, target_id=target_id,
            # R115 审计：落库前**兜底脱敏**（先脱敏再截断，避免截断把
            # `password=xxx` 切成 `password=xx` 后打码规则匹配不到）。这是纵深防御，
            # 不替代上面「detail 只放摘要」的纪律。
            detail=_redact_detail(detail or "")[:300], ip=ip[:64], success=success,
            payload=snap,
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
    # 顺带清理超过保留周期的旧审计日志（含登录日志），避免表无限膨胀
    # （v3.1.0；v3.1.6 周期可配；v3.25.8 起后台「系统设置」可改 → DB → env → 默认 90）
    try:
        from utils import flag_num
        days = flag_num("audit_log_days", "AUDIT_LOG_DAYS", 90, int)
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
