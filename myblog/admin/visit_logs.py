# -*- coding: utf-8 -*-
"""访客日志（v4.2.0）：分页查看每一次真实访问，并按 IP 拉黑 / 解黑。

数据源是既有 `VisitLog`（每次访问都已记录 IP / 属地 / 路径 / 来源 / 是否爬虫）
—— **零表结构变更**；拉黑写入既有 `BotBlock`，复用反爬封禁原语。
⚠️ 生效链路见 `bot_guard.check_bot_guard()`：手动黑名单**独立于**「反爬限流」
开关（开关默认关，旧实现下黑名单会形同虚设）；且只覆盖前台蓝图（main_bp）
的请求，`/api/` 与 `/admin/` 有各自的鉴权与限流，不在此列。
"""
from flask import flash, redirect, render_template, request, url_for

from ._helpers import (admin_bp, admin_required, super_required, log_audit,
                       _current_user_or_none)
from models import BotBlock, VisitLog
from stats import DEFAULT_RANGE, RANGE_PRESETS, resolve_range
import bot_guard
from utils import fmt_bj
from _time import utcnow

_PER_PAGE = 50


def _like(raw):
    """把用户输入转成安全的 LIKE 模式：转义 `%` `_` `\\`，避免筛选词被当成通配符。"""
    esc = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + esc + "%"


def _back_url():
    """操作后跳回列表并保留当时的筛选条件（只接受站内 /admin/visit-logs 路径）。"""
    nxt = (request.form.get("next") or "").strip()
    if nxt.startswith("/admin/visit-logs"):
        return nxt
    return url_for("admin.visit_logs")


@admin_bp.route("/visit-logs")
@admin_required
def visit_logs():
    """访客日志列表：分页 + 区间 / 真人·爬虫 / IP / 属地 / 路径 筛选。"""
    page = request.args.get("page", 1, type=int)
    rng = (request.args.get("range") or "").strip() or DEFAULT_RANGE
    typ = (request.args.get("type") or "").strip()
    ip_q = (request.args.get("ip") or "").strip()[:64]
    region_q = (request.args.get("region") or "").strip()[:64]
    path_q = (request.args.get("path") or "").strip()[:120]

    eff_key, start, end, label = resolve_range(rng)
    q = VisitLog.query.filter(VisitLog.date >= start.isoformat(),
                              VisitLog.date <= end.isoformat())
    if typ == "human":
        q = q.filter(VisitLog.is_bot.is_(False))
    elif typ == "bot":
        q = q.filter(VisitLog.is_bot.is_(True))
    if ip_q:
        q = q.filter(VisitLog.ip.ilike(_like(ip_q), escape="\\"))
    if region_q:
        q = q.filter(VisitLog.region.ilike(_like(region_q), escape="\\"))
    if path_q:
        q = q.filter(VisitLog.path.ilike(_like(path_q), escape="\\"))

    pagination = (q.order_by(VisitLog.id.desc())
                   .paginate(page=page, per_page=_PER_PAGE, error_out=False))

    # 当前页出现过的 IP 哪些正处于封禁期（决定按钮显示「拉黑」还是「解封」）
    blocked = {}
    ips = sorted({r.ip for r in pagination.items if r.ip})
    if ips:
        now = utcnow()
        for rec in BotBlock.query.filter(BotBlock.ip.in_(ips),
                                         BotBlock.active.is_(True)).all():
            if rec.blocked_until and rec.blocked_until > now:
                blocked[rec.ip] = rec

    return render_template(
        "admin/visit_logs.html",
        logs=pagination.items, pagination=pagination,
        ranges=RANGE_PRESETS, cur_range=eff_key, range_label=label,
        range_start=start.isoformat(), range_end=end.isoformat(),
        f_type=typ, f_ip=ip_q, f_region=region_q, f_path=path_q,
        blocked=blocked, fmt_bj=fmt_bj)


@admin_bp.route("/visit-logs/block", methods=["POST"])
@super_required
def visit_logs_block():
    """拉黑 IP（默认永久）。仅超管可操作；写审计日志。"""
    ip = (request.form.get("ip") or "").strip()
    ok, msg = bot_guard.block_ip(ip)
    if ok:
        log_audit("block_ip", "visit_log", None, msg, user=_current_user_or_none())
    flash(msg)
    return redirect(_back_url())


@admin_bp.route("/visit-logs/unblock", methods=["POST"])
@super_required
def visit_logs_unblock():
    """解封 IP。仅超管可操作；写审计日志。"""
    ip = (request.form.get("ip") or "").strip()
    ok = bot_guard.unblock_ip(ip)
    flash("已解封 " + ip if ok else "未找到该 IP 的封禁记录")
    if ok:
        log_audit("unblock_ip", "visit_log", None, "解封 " + ip,
                  user=_current_user_or_none())
    return redirect(_back_url())
