"""反爬限流保护（v3.8.0）。

设计原则：
- 默认关闭（bot_guard_enabled=false），由后台开关控制，避免误伤正常访客。
- 搜索引擎（search 类）默认白名单豁免，保证 SEO 抓取不受影响。
- tool/unknown 类 Bot 与普通高频 IP 用不同阈值；AI 类与真人同档。
- 超限先记录，达到封禁次数阈值才封禁一段时间；封禁期可后台解封。
- 不拦截静态资源 / robots.txt / sitemap.xml / 后台 / 接口（避免误伤与自锁）。
"""
from datetime import datetime, timedelta
from flask import request

from models import db, BotBlock
from utils import detect_bot, get_setting, setting_bool, rate_limit, client_key
from stats import client_ip

# 不参与限流的路径前缀（搜索引擎必须能抓 robots/sitemap；静态资源不计；
# 后台 / 接口各自已有 rate_limit，避免被 bot_guard 误伤或自锁）。
_SKIP_PREFIXES = ("/static/", "/robots.txt", "/sitemap.xml", "/admin/", "/api/")


def guard_enabled():
    return setting_bool("bot_guard_enabled", False)


def is_blocked(ip):
    """查询该 IP 是否处于封禁期内。返回 BotBlock 记录或 None。"""
    now = datetime.utcnow()
    rec = BotBlock.query.filter_by(ip=ip, active=True).first()
    if rec and rec.blocked_until and rec.blocked_until > now:
        return rec
    return None


def check_bot_guard():
    """在 before_request 调用。返回 None=放行；dict=应拦截（含 code/reason/category）。"""
    if not guard_enabled():
        return None
    path = request.path or ""
    if any(path.startswith(p) for p in _SKIP_PREFIXES):
        return None

    ip = client_ip()  # 真实公网 IP（与访问记录口径一致）
    blocked = is_blocked(ip)
    if blocked:
        return {"code": 429, "reason": "blocked", "category": blocked.bot_category}

    ua = request.headers.get("User-Agent", "")
    is_bot, bot_name, category = detect_bot(ua)

    # 搜索引擎白名单豁免（保证 SEO 正常抓取）
    if category == "search" and setting_bool("bot_guard_search_whitelist", True):
        return None

    # 阈值选择：坏 Bot（tool/unknown）更严格
    if is_bot and category in ("tool", "unknown"):
        limit = int(get_setting("bot_guard_tool_limit", "20"))
        reason = "rate_tool"
    else:
        limit = int(get_setting("bot_guard_threshold", "120"))
        reason = "rate_human" if not is_bot else "rate_ai"
    window = int(get_setting("bot_guard_window", "60"))

    allowed = rate_limit(client_key("guard"), limit=limit, window=window)
    if allowed:
        return None

    _record_block(ip, bot_name, category, reason)
    return {"code": 429, "reason": reason, "category": category}


def _record_block(ip, bot_name, category, reason):
    now = datetime.utcnow()
    rec = BotBlock.query.filter_by(ip=ip).first()
    if not rec:
        rec = BotBlock(ip=ip, bot_name=bot_name, bot_category=category,
                       hit_count=1, reason=reason)
        db.session.add(rec)
    else:
        rec.hit_count += 1
        if bot_name:
            rec.bot_name = bot_name
        if category:
            rec.bot_category = category
        rec.reason = reason
        rec.active = True
    # 达到封禁次数阈值才封禁一段时间（默认 3 次 → 封 30 分钟）
    block_hits = int(get_setting("bot_guard_block_hits", "3"))
    if rec.hit_count >= block_hits:
        mins = int(get_setting("bot_guard_block_minutes", "30"))
        rec.blocked_until = now + timedelta(minutes=mins)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def unblock_ip(ip):
    """后台解封：清除封禁期并标记 inactive。"""
    rec = BotBlock.query.filter_by(ip=ip).first()
    if not rec:
        return False
    rec.active = False
    rec.blocked_until = None
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def guard_stats():
    """供后台看板使用的风控统计。表尚未建立时返回安全默认值（避免边缘 500）。"""
    try:
        now = datetime.utcnow()
        total = BotBlock.query.count()
        active_blocks = BotBlock.query.filter_by(active=True).count()
        blocked_now = BotBlock.query.filter(
            BotBlock.active.is_(True),
            BotBlock.blocked_until.isnot(None),
            BotBlock.blocked_until > now,
        ).count()
        by_cat = {}
        for rec in BotBlock.query.all():
            c = rec.bot_category or "human"
            by_cat[c] = by_cat.get(c, 0) + 1
        recent = BotBlock.query.order_by(BotBlock.last_seen.desc()).limit(20).all()
        return {
            "total": total,
            "active_blocks": active_blocks,
            "blocked_now": blocked_now,
            "by_category": by_cat,
            "recent": recent,
            "enabled": guard_enabled(),
        }
    except Exception:
        return {
            "total": 0, "active_blocks": 0, "blocked_now": 0,
            "by_category": {}, "recent": [], "enabled": guard_enabled(),
        }
