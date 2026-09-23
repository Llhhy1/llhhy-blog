"""读者积分勋章服务（v3.21.0 gamification）。

职责：
- 从请求 cookie 取/建读者档案（匿名访客用 reader_token，登录读者绑定 user_id）。
- 统一发放积分 award()，带「同读者 + 同 reason + 同 post + 同一天」去重，避免刷量。
- 按累计积分阈值自动授予勋章（_check_badges）。
- 提供 reader_summary / leaderboard 供接口与前端展示。

设计约束：
- 本模块不直接 import app（避免循环依赖）；仅在函数内 `from flask import request`。
- award() 失败不影响主流程（路由侧用 award_interaction 包一层兜底）。
- 积分规则与勋章阈值集中在此文件，便于运营调整。
"""
import contextlib
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
    """首次建表后播种默认勋章（幂等：已有则跳过）。"""
    if Badge.query.count() == 0:
        for key, name, desc, icon, thr in DEFAULT_BADGES:
            db.session.add(Badge(key=key, name=name, description=desc, icon=icon, threshold=thr))
        db.session.commit()


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
    """给读者加积分（带去重：同 reader+reason+post+当天只计一次）。返回是否实际加分。"""
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
    reader.points = (reader.points or 0) + delta
    reader.updated_at = utcnow()
    db.session.commit()
    _check_badges(reader)
    return True


def _check_badges(reader):
    """按累计积分自动授予已达阈值的勋章（已得的跳过）。"""
    earned = {rb.badge_id for rb in reader.badges.all()}
    for b in Badge.query.filter(Badge.threshold <= (reader.points or 0)).all():
        if b.id not in earned:
            db.session.add(ReaderBadge(reader_id=reader.id, badge_id=b.id))
    if db.session.new:
        db.session.commit()


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
