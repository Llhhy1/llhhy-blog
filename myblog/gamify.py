"""读者积分勋章服务（v3.21.0 gamification）。

职责：
- 从请求 cookie 取/建读者档案（匿名访客用 reader_token，登录读者绑定 user_id）。
- 统一发放积分 award()，带「同读者 + 同 reason + 同 post + 同一天」去重，避免刷量。
- 按累计积分阈值自动授予勋章（_check_badges）。
- 提供 reader_summary / leaderboard 供接口与前端展示。
- 按保留策略清理过期数据 prune_retention()（见 POINT_LOG_RETENTION_DAYS）。

设计约束：
- 本模块不直接 import app（避免循环依赖）；仅在函数内 `from flask import request`。
- award() 失败不影响主流程（路由侧用 award_interaction 包一层兜底）。
- 积分规则与勋章阈值集中在此文件，便于运营调整。
"""
import contextlib
import datetime
import secrets

from models import db, Reader, PointLog, Badge, ReaderBadge
from _time import utcnow
from utils import to_beijing

READER_COOKIE = "reader_token"
READER_COOKIE_MAXAGE = 60 * 60 * 24 * 365  # 1 年

# 积分规则：每类互动的基准分值
POINT_RULES = {
    "read": 2,      # 真实阅读（24h 同文章去重）
    "comment": 5,   # 发表评论
    "visit": 1,     # 每日访问（按天去重）
    "share": 3,     # 分享（预留）
}

# 默认勋章（首次建表时播种；threshold=累计积分阈值）
DEFAULT_BADGES = [
    ("novice", "初来乍到", "累计 10 积分", "🌱", 10),
    ("reader", "阅读达人", "累计 50 积分", "📚", 50),
    ("critic", "热心评论", "累计 120 积分", "💬", 120),
    ("fan", "忠实读者", "累计 300 积分", "⭐", 300),
    ("legend", "博客传奇", "累计 800 积分", "👑", 800),
]


def seed_badges():
    """播种默认勋章（幂等；多 worker 并发启动也安全）。

    按 key 逐枚跳过已有项，而不是「表空才整批插」：
    - 旧写法①：表里有任意一行就整体跳过 → 缺的勋章永远补不齐；
    - 旧写法②：gunicorn 多 worker 同时启动都看到空表、都去插入，后提交的撞
      UNIQUE 键（v3.21.1 上线日志实测出现假警报「播种失败」，会掩盖真失败）。
    撞键 = 另一 worker 已抢先完成播种 → 回滚放弃即可，**不算失败、不必报警**。
    """
    from sqlalchemy.exc import IntegrityError
    existing = {k for (k,) in Badge.query.with_entities(Badge.key).all()}
    for key, name, desc, icon, thr in DEFAULT_BADGES:
        if key in existing:
            continue
        db.session.add(Badge(key=key, name=name, description=desc, icon=icon, threshold=thr))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()   # 竞态窗口内另一 worker 先 commit 成功 → 放弃本次即可


def _today():
    bj = to_beijing(utcnow())
    return bj.strftime("%Y-%m-%d") if bj else ""


def current_reader():
    """从 cookie 取/建读者档案，返回 (reader, is_new)。"""
    from flask import request
    tok = request.cookies.get(READER_COOKIE)
    if tok:
        r = Reader.query.filter_by(token=tok).first()
        if r:
            return r, False
    r = Reader(token=secrets.token_hex(24))
    db.session.add(r)
    db.session.commit()
    return r, True


def award(reader, reason, post_id=None, delta=None):
    """给读者加积分（带去重：同 reader+reason+post+当天只计一次）。返回是否实际加分。

    去重有两层，缺一不可：
    - 应用层「先查后插」有 TOCTOU 竞态：4 worker × 2 线程下两个并发请求都能通过
      `exists` 判断，于是都去 INSERT；
    - 数据库层唯一索引 `uq_pointlog_dedup` 兜底，后来者撞键抛 IntegrityError。
      这里**必须捕获并回滚**，否则「静默重复积分」会变成公开读路径上的 500。
      回滚同时撤销本事务里已经执行的 `UPDATE reader SET points = ...`，避免重复加分。
    """
    from sqlalchemy.exc import IntegrityError
    if delta is None:
        delta = POINT_RULES.get(reason, 0)
    if delta <= 0:
        return False
    day = _today()
    exists = PointLog.query.filter_by(
        reader_id=reader.id, reason=reason, post_id=post_id, day=day).first()
    if exists:
        return False
    db.session.add(PointLog(reader_id=reader.id, reason=reason,
                            post_id=post_id, delta=delta, day=day))
    # 用 SQL 级 `points = points + :d`，不在 Python 侧读改写：4 worker × 2 线程下
    # 两个并发事件会各自读到同一个旧值，后提交的把前一个覆盖掉（丢积分）。
    db.session.execute(db.text(
        "UPDATE reader SET points = COALESCE(points, 0) + :d, updated_at = :u "
        "WHERE id = :r"), {"d": delta, "u": utcnow(), "r": reader.id})
    try:
        db.session.commit()
    except IntegrityError:
        # 并发下另一 worker 先记了同一条 → 本次放弃即可，不算失败（与 seed_badges 同策略）。
        db.session.rollback()
        return False
    db.session.refresh(reader)   # 让下面的阈值判定看到累加后的值
    _check_badges(reader)
    return True


def _check_badges(reader):
    """按累计积分自动授予已达阈值的勋章（已得的跳过）。"""
    from sqlalchemy.exc import IntegrityError
    earned = {rb.badge_id for rb in reader.badges.all()}
    for b in Badge.query.filter(Badge.threshold <= (reader.points or 0)).all():
        if b.id not in earned:
            db.session.add(ReaderBadge(reader_id=reader.id, badge_id=b.id))
    if not db.session.new:
        return
    try:
        db.session.commit()
    except IntegrityError:
        # 并发授予同一枚时 `uq_reader_badge` 会拒掉后来者，这不算错误。
        # 但**必须回滚**：否则会话停在失败状态，同一请求里紧接着的取库操作
        # （评论流程随后还要写 ReadLog）会连带炸成 500。
        # 这正是 v3.21.1/v3.21.2 在 `seed_badges()` 上踩过的同一个坑。
        db.session.rollback()


def reader_summary(reader):
    """返回读者积分与已得勋章（前端展示用）。"""
    badges = [{
        "key": rb.badge.key, "name": rb.badge.name,
        "icon": rb.badge.icon, "description": rb.badge.description,
    } for rb in reader.badges.all()]
    return {"points": reader.points or 0, "badges": badges, "name": reader.name}


def leaderboard(limit=10):
    """公开积分排行榜（前 N 名，仅含有积分的读者）。"""
    rows = (Reader.query.filter(Reader.points > 0)
            .order_by(Reader.points.desc()).limit(limit).all())
    return [{
        "name": r.name, "points": r.points or 0,
        "badges": [rb.badge.icon for rb in r.badges.all()],
    } for r in rows]


def award_interaction(reason, post_id=None):
    """路由侧便捷封装：给当前读者加积分，返回需要写入响应的新 cookie token（无则 None）。

    用 try 包一层，确保积分系统异常时**不影响**主流程（阅读/评论/访问照常成功）。
    """
    try:
        from flask import current_app
        r, is_new = current_reader()
        award(r, reason, post_id)
        return r.token if is_new else None
    except Exception as e:  # noqa: BLE001  积分是旁路功能：任何异常都必须吞掉，绝不影响主流程
        # 日志本身打不出来也不能让主流程崩掉
        with contextlib.suppress(Exception):
            from flask import current_app
            current_app.logger.warning("gamify award failed: %s", e)
        return None


# ----------------------------------------------------------------------
# 保留策略（2026-09-29 产品决策）
#
#   reader       —— **永久保留**。积分档案是读者的长期身份，不因时间删除。
#                   本函数对它不做任何删除（下面刻意没有 reader 的 DELETE 语句）。
#   point_log    —— 保留 2 年。流水只用于当日去重与对账，过期后不再有价值，
#                   而它随匿名访客长期增长，是最需要设上限的一张表。
#   reader_badge —— **随 reader**。不做时间维度删除，只在所属 reader 已不存在时
#                   清理孤儿行（ORM 侧 `cascade="all, delete-orphan"` 已覆盖正常
#                   删除路径，这里兜的是历史脏数据与不走 ORM 的删除）。
# ----------------------------------------------------------------------
POINT_LOG_RETENTION_DAYS = 730


def prune_retention(point_log_days=POINT_LOG_RETENTION_DAYS):
    """按保留策略清理过期/孤儿数据，返回各表删除行数。

    幂等、可重复执行，由调度线程每日调用一次。**reader 永久保留，本函数不删。**
    """
    cutoff = utcnow() - datetime.timedelta(days=point_log_days)
    n_logs = db.session.execute(
        db.text("DELETE FROM point_log WHERE created_at < :cut"), {"cut": cutoff}
    ).rowcount or 0
    n_badges = db.session.execute(
        db.text("DELETE FROM reader_badge WHERE reader_id NOT IN (SELECT id FROM reader)")
    ).rowcount or 0
    db.session.commit()
    return {"point_log": n_logs, "reader_badge": n_badges}
