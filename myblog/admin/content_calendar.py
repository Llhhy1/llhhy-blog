# -*- coding: utf-8 -*-
"""内容日历（v4.9.0 · ROADMAP §3.1）。

把**草稿 / 定时发布 / 已发布**三类文章按日期铺到一张月历上，回答的问题是
「这个月我哪天发了东西、哪天还欠着」。

设计取舍：

- **只读页**：不提供「拖动改期」。改期要处理时区、发布态翻转、并发冲突，
  而本站 post 量级是两位数 —— 点标题进编辑页改，成本更低且不会引入新的
  写入路径（写入路径越多，审计面越大）。
- **归属日期的判定**：有 `scheduled_at` 的（定时 / 已到点发布）以它为准，
  否则用 `created_at`。两者都是 UTC 存储，展示前统一转北京时间。
- **SQL 粗筛 + Python 精筛**：先按 (created_at OR scheduled_at) 落在
  「本月 ±1 天」拉候选，再在 Python 里按**北京时间**精确定档。之所以要
  ±1 天缓冲并二次精筛：UTC 与北京时间差 8 小时，直接用本地月初做 SQL 边界
  会把月初/月末那几天漏掉。
"""

import calendar

from ._helpers import admin_bp, login_required
from flask import render_template, request, session
from models import Post, User, db
from _time import utcnow
from utils import to_beijing

# 每天格子里最多列出几条标题（超出折叠为「还有 N 篇」，避免格子撑爆）
_MAX_PER_DAY = 3


def _belongs_to_month(post, year, month):
    """返回该文章在本月应归属的（北京时间）日期；不属于本月则返回 None。"""
    when = post.scheduled_at or post.created_at
    if when is None:
        return None
    local = to_beijing(when)
    if local.year == year and local.month == month:
        return local
    return None


def _status_of(post, now_local):
    """三态：定时（未到点）/ 草稿 / 已发布。"""
    # scheduled_at 到点后由后台线程翻 published，此处以本地时间为准判「待发」
    if post.scheduled_at is not None and to_beijing(post.scheduled_at) > now_local:
        return "scheduled"
    return "published" if post.published else "draft"


@admin_bp.route("/content-calendar")
@login_required
def content_calendar():
    now_local = to_beijing(utcnow())
    year = request.args.get("year", type=int) or now_local.year
    month = request.args.get("month", type=int) or now_local.month
    if not 1 <= month <= 12:
        month = now_local.month

    # 本月首日 / 次月首日（本地），SQL 侧前后各放宽 1 天作时区缓冲
    def _month_start(y, m):
        import datetime as _dt
        return _dt.datetime(y, m, 1)

    import datetime as _dt
    start = _month_start(year, month) - _dt.timedelta(days=1)
    nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
    end = _month_start(nxt_y, nxt_m) + _dt.timedelta(days=1)

    # ⚠️ 权限口径必须与 `admin.my_posts` 完全一致（v4.9.0 审计）：
    # 非管理员角色**只能看自己的文章**。日历会把**草稿标题**铺在格子里，
    # 若沿用「管理员可读全站」的默认值，普通作者就能看到别人的未发布草稿 ——
    # 这正是 ROADMAP §3.1 D8.3 那条警告（每加一批都要重新判权限）的实例。
    user = db.session.get(User, session.get("user_id"))
    base = Post.query.filter(Post.in_trash == False)
    if not (user and user.is_admin_role):
        base = base.filter(Post.author_id == user.id)

    rows = base.filter(
        db.or_(
            db.and_(Post.created_at >= start, Post.created_at < end),
            db.and_(Post.scheduled_at >= start, Post.scheduled_at < end),
        )
    ).all()

    day_map = {}
    for p in rows:
        local = _belongs_to_month(p, year, month)
        if local is None:
            continue
        day_map.setdefault(local.day, []).append({
            "id": p.id,
            "title": p.title,
            "status": _status_of(p, now_local),
            "time": local.strftime("%H:%M"),
        })
    for items in day_map.values():
        items.sort(key=lambda x: x["time"])

    cal = calendar.Calendar(firstweekday=0)  # 周一为首列（国内习惯）
    weeks = cal.monthdayscalendar(year, month)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    counts = {"draft": 0, "scheduled": 0, "published": 0}
    for items in day_map.values():
        for it in items:
            counts[it["status"]] = counts.get(it["status"], 0) + 1

    return render_template(
        "admin/content_calendar.html",
        year=year, month=month, weeks=weeks, day_map=day_map,
        prev_year=prev_y, prev_month=prev_m,
        next_year=next_y, next_month=next_m,
        counts=counts, max_per_day=_MAX_PER_DAY,
        weekday_names=["一", "二", "三", "四", "五", "六", "日"],
        total=sum(len(v) for v in day_map.values()),
    )
