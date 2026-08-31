# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

@admin_bp.route("/")
@admin_required
def dashboard():
    # 后台文章列表分页 + 状态/分类/关键词筛选（v2.8.0）
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    cat_id = request.args.get("category_id", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12
    query = Post.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if status == "published":
        query = query.filter(Post.published == True, Post.scheduled_at.is_(None))
    elif status == "draft":
        query = query.filter(Post.published == False, Post.scheduled_at.is_(None))
    elif status == "scheduled":
        query = query.filter(Post.scheduled_at.isnot(None), Post.published == False)
    elif status == "pinned":
        query = query.filter(Post.is_pinned == True)
    if cat_id:
        query = query.filter(Post.category_id == int(cat_id))
    pagination = query.order_by(Post.is_pinned.desc(), Post.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    pending = Comment.query.filter_by(approved=False).count()
    recent_comments = Comment.query.order_by(Comment.created_at.desc()).limit(6).all()
    from stats import compute_summary
    summary = compute_summary()
    cats = Category.query.order_by(Category.id).all()
    return render_template("admin/dashboard.html", posts=pagination.items,
                           pagination=pagination, filter_q=q, filter_status=status,
                           filter_cat=cat_id, cats=cats, pending=pending,
                           summary=summary, recent_comments=recent_comments)

@admin_bp.route("/stats")
@admin_required
def stats():
    """访问统计页（服务端渲染，含区域/时段/热读/常搜图表）。"""
    from stats import compute_summary
    summary = compute_summary()
    guard = bot_guard.guard_stats()
    # 时段分布转成带百分比的行，供模板画横向条形图
    total_hour = sum(b["count"] for b in summary["hourly"]) or 1
    max_hour = max([b["count"] for b in summary["hourly"]] or [1]) or 1
    for b in summary["hourly"]:
        b["pct"] = round(b["count"] * 100 / max_hour)
    max_region = max([r["count"] for r in summary["regions_all"]] or [1]) or 1
    for r in summary["regions_all"]:
        r["pct"] = round(r["count"] * 100 / max_region)
    max_reads = max([p["reads"] for p in summary["hot_posts"]] or [1]) or 1
    for p in summary["hot_posts"]:
        p["pct"] = round(p["reads"] * 100 / max_reads)
    max_search = max([s["count"] for s in summary["hot_searches"]] or [1]) or 1
    for s in summary["hot_searches"]:
        s["pct"] = round(s["count"] * 100 / max_search)
    return render_template("admin/stats.html", summary=summary, guard=guard)

@admin_bp.route("/audit-logs")
@login_required
@super_required
def audit_logs():
    """操作日志列表（仅超管可见）：分页展示，按时间倒序。

    v3.1.6 中优：支持 ?from= / ?to= 时间筛选（导出与页面共用同一过滤）。
    """
    from flask import request as _req
    q, frm, to = _audit_log_query_with_filters()
    page = _req.args.get("page", 1, type=int)
    pagination = q.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False)
    try:
        from flask import current_app as _app
        keep_days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        keep_days = 90
    from utils import csrf_input as _csrf_input  # 模板用 {{ csrf_input() }}
    return render_template("admin/audit_logs.html", logs=pagination.items,
                           pagination=pagination, filter_from=frm, filter_to=to,
                           keep_days=keep_days, csrf_input=_csrf_input)

@admin_bp.route("/audit-logs/export")
@login_required
@super_required
def export_audit_logs():
    """打包下载审计日志（v3.1.0 新增；v3.1.6 中优支持 ?from=/&to= 时间筛选）：
    生成 CSV + 可读 TXT 的 zip，内存打包不落盘。"""
    import io
    import csv
    import zipfile
    import datetime as _dt
    q, frm, to = _audit_log_query_with_filters()
    logs = q.order_by(AuditLog.created_at.desc()).all()

    # ---- CSV 公式注入防护 ----
    # 单元格以 = + - @ 开头时，Excel/Numbers 会当成公式执行（如 "=cmd|..." 或 "=1+1"），
    # 攻击者可通过审计日志里用户可控字段（用户名/说明）注入。前缀单引号可 neutral 化。
    def _csv_guard(v):
        s = "" if v is None else str(v)
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
            return "'" + s
        return s

    # ---- CSV ----
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["时间", "操作人", "动作", "对象", "结果", "说明", "来源IP"])
    for l in logs:
        writer.writerow([
            _csv_guard(fmt_bj(l.created_at, "%Y-%m-%d %H:%M:%S")),
            _csv_guard(l.username or ""),
            _csv_guard(l.action or ""),
            _csv_guard((l.target or "") + (f"#{l.target_id}" if l.target_id else "")),
            "成功" if l.success else "失败",
            _csv_guard(l.detail or ""),
            _csv_guard(l.ip or ""),
        ])
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")  # BOM 让 Excel 正确识别中文

    # ---- TXT（人类可读）----
    try:
        from flask import current_app as _app
        keep_days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        keep_days = 90
    scope = f"时间范围：{frm or '起始'} → {to or '最新'}" if (frm or to) else f"保留 {keep_days} 天内的全部记录"
    lines = ["llhhy-blog 后台审计日志导出", "生成时间：" + fmt_bj(datetime.datetime.utcnow(), "%Y-%m-%d %H:%M:%S"),
             "共 %d 条记录（%s）" % (len(logs), scope), "=" * 60]
    for l in logs:
        ts = fmt_bj(l.created_at, "%Y-%m-%d %H:%M:%S")
        obj = (l.target or "") + (f"#{l.target_id}" if l.target_id else "")
        res = "成功" if l.success else "失败"
        lines.append(f"[{ts}] {l.username or '—'} {l.action} {obj} {res} | {l.detail or ''} | IP:{l.ip or '—'}")
    txt_bytes = ("\n".join(lines)).encode("utf-8")

    # ---- 内存打包 zip ----
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit_logs.csv", csv_bytes)
        zf.writestr("audit_logs.txt", txt_bytes)
    zip_buf.seek(0)

    stamp = fmt_bj(datetime.datetime.utcnow(), "%Y%m%d_%H%M%S")
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"audit_logs_{stamp}.zip",
    )

@admin_bp.route("/audit-logs/clear", methods=["POST"])
@login_required
@super_required
def clear_audit_logs():
    """清空操作日志（谨慎操作，不可恢复）。保留最近 AUDIT_LOG_DAYS 天（v3.1.0；v3.1.6 保留周期可配）。"""
    try:
        from flask import current_app as _app
        days = _app.config.get("AUDIT_LOG_DAYS", 90)
    except Exception:
        days = 90
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete()
    db.session.commit()
    log_audit("clear", "audit_log", None, f"清空 {days} 天前的审计日志 {deleted} 条", user=_current_user_or_none())
    flash(f"已清理 {deleted} 条 {days} 天前的旧日志（近 {days} 天记录保留）")
    return redirect(url_for("admin.audit_logs"))
