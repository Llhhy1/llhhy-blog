"""访问统计工具：IP 属地解析（缓存 + 在线接口兜底）、访问/搜索/阅读记录、汇总统计。

设计要点：
- 访问记录为同步写入（极快），IP 属地解析放在后台线程里做，绝不阻塞页面响应；
- 属地解析结果缓存到 IpRegion 表，避免每个访客都请求在线接口；
- 对外提供 compute_summary()，同时供 /api/stats/summary 与后台统计页使用。
"""
import datetime
import json
import threading
import urllib.parse
import urllib.request

from models import db, Post, VisitLog, ReadLog, SearchLog, IpRegion, Comment

_LOCAL_IPS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


def today_str():
    return datetime.date.today().isoformat()


def client_ip():
    """取客户端真实 IP：Nginx 反代后优先 X-Forwarded-For 第一个值。"""
    from flask import request
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def short_region(raw):
    """把"浙江省 杭州市"缩成"浙江·杭州"，排行展示更清爽。"""
    if not raw:
        return ""
    raw = raw.replace(" ", "").replace("·", "")
    for suf in ("壮族自治区", "回族自治区", "维吾尔自治区", "特别行政区",
                "自治区", "省", "市", "区", "县"):
        raw = raw.replace(suf, "")
    return raw


def _fetch_json(url, timeout=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (blog stats)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _lookup_region(ip):
    """在线查询 IP 属地；全部失败返回 None。"""
    if not ip or ip in _LOCAL_IPS:
        return None
    # 1) vore.top（国内可访问，返回 code=200 + ipdata.info1.{province,city}）
    try:
        d = _fetch_json("https://api.vore.top/api/IPdata?ip=" + urllib.parse.quote(ip))
        if isinstance(d, dict) and d.get("code") == 200:
            info = (d.get("ipdata") or {}).get("info1") or {}
            province = (info.get("province") or "").strip()
            city = (info.get("city") or "").strip()
            if province:
                return short_region(province + " " + city) or short_region(province)
    except Exception:
        pass
    # 2) ip-api.com（国际通用，status=success，lang=zh-CN）
    try:
        d = _fetch_json("https://ip-api.com/json/" + urllib.parse.quote(ip) + "?lang=zh-CN")
        if isinstance(d, dict) and d.get("status") == "success":
            country = (d.get("country") or "").strip()
            region = (d.get("regionName") or "").strip()
            city = (d.get("city") or "").strip()
            raw = (region + " " + city).strip() if country == "中国" else (country + " " + region).strip()
            if raw:
                return short_region(raw)
    except Exception:
        pass
    return None


def _ensure_region(ip):
    """查缓存 → 在线解析 → 写缓存，返回区域字符串（可能为空）。"""
    if not ip or ip in _LOCAL_IPS:
        return ""
    row = IpRegion.query.filter_by(ip=ip).first()
    if row and row.region:
        return row.region
    region = _lookup_region(ip) or ""
    if row:
        row.region = region
    else:
        db.session.add(IpRegion(ip=ip, region=region))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return region


def _resolve_region_async(ip):
    """后台线程：解析属地并回填此前该 IP 的访问记录与评论记录。"""
    def _work():
        try:
            from app import app  # 延迟导入，避免循环依赖
            with app.app_context():
                region = _ensure_region(ip)
                if not region:
                    return
                try:
                    VisitLog.query.filter_by(ip=ip)\
                        .filter(VisitLog.region.in_(["", "未知"]))\
                        .update({"region": region})
                    Comment.query.filter_by(ip=ip)\
                        .filter(Comment.region.in_(["", "未知"]))\
                        .update({"region": region})
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        except Exception:
            pass
    if ip and ip not in _LOCAL_IPS:
        threading.Thread(target=_work, daemon=True).start()


def cached_region(ip):
    """同步取 IP 属地缓存；未命中则触发后台解析（稍后回填），本次返回空。"""
    if not ip or ip in _LOCAL_IPS:
        return ""
    row = IpRegion.query.filter_by(ip=ip).first()
    if row and row.region:
        return row.region
    _resolve_region_async(ip)
    return ""


def record_visit(path, post_id=None):
    """记录一次访问；属地解析异步回填。任何异常都不影响页面本身。"""
    try:
        ip = client_ip()
        db.session.add(VisitLog(
            date=today_str(), hour=datetime.datetime.now().hour,
            ip=ip, region="", path=(path or "")[:255], post_id=post_id,
        ))
        db.session.commit()
        _resolve_region_async(ip)
    except Exception:
        db.session.rollback()


def record_search(keyword):
    """记录一次搜索词。异常静默。"""
    kw = (keyword or "").strip()[:120]
    if not kw:
        return
    try:
        db.session.add(SearchLog(keyword=kw, date=today_str()))
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_read(post_id, ip):
    """文章阅读 +1；同一访客重复读同一篇会累加 read_count（"反复阅读"）。异常静默。"""
    if not post_id:
        return
    try:
        row = ReadLog.query.filter_by(post_id=post_id, ip=ip).first()
        if row:
            row.read_count += 1
        else:
            db.session.add(ReadLog(post_id=post_id, ip=ip, read_count=1))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _top_region(limit=10, date=None):
    q = db.session.query(VisitLog.region, db.func.count(VisitLog.id).label("c"))
    if date:
        q = q.filter(VisitLog.date == date)
    q = q.filter(VisitLog.region != "")
    rows = q.group_by(VisitLog.region).order_by(db.desc("c")).limit(limit).all()
    return [{"region": r[0], "count": r[1]} for r in rows]


def _hourly():
    rows = db.session.query(VisitLog.hour, db.func.count(VisitLog.id)).group_by(VisitLog.hour).all()
    buckets = [0] * 24
    for h, c in rows:
        if 0 <= h <= 23:
            buckets[h] = c
    return [{"hour": i, "count": buckets[i]} for i in range(24)]


def _hot_posts(limit=10):
    rows = db.session.query(
        ReadLog.post_id,
        db.func.sum(ReadLog.read_count).label("reads"),
        db.func.count(ReadLog.id).label("readers"),
    ).group_by(ReadLog.post_id).order_by(db.desc("reads")).limit(limit).all()
    result = []
    for post_id, reads, readers in rows:
        p = db.session.get(Post, post_id)
        if not p:
            continue
        result.append({"slug": p.slug, "title": p.title,
                       "reads": int(reads), "readers": int(readers)})
    return result


def _hot_searches(limit=10):
    rows = db.session.query(SearchLog.keyword, db.func.count(SearchLog.id).label("c"))\
        .group_by(SearchLog.keyword)\
        .order_by(db.desc("c"), db.desc(SearchLog.id)).limit(limit).all()
    return [{"keyword": r[0], "count": r[1]} for r in rows]


def compute_trend(days=30):
    """访客趋势数据（v3.0.0 功能9）：返回最近 N 天每天的总访问次数（PV）与独立访客（UV）。

    用于前台/后台「访客趋势图」可视化。按 VisitLog.date 聚合，缺失日期补 0，
    保证前端拿到的是连续日期序列（便于画折线/柱状图）。
    """
    try:
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days - 1)
        # 取区间内所有访问日志的 (date, ip)
        rows = (db.session.query(VisitLog.date, VisitLog.ip)
                .filter(VisitLog.date >= start.isoformat(),
                        VisitLog.date <= end.isoformat()).all())
        pv = {}
        uv = {}
        for d, ip in rows:
            pv[d] = pv.get(d, 0) + 1
            uv.setdefault(d, set()).add(ip)
        result = []
        cur = start
        while cur <= end:
            ds = cur.isoformat()
            result.append({"date": ds, "pv": pv.get(ds, 0), "uv": len(uv.get(ds, set()))})
            cur += datetime.timedelta(days=1)
        return result
    except Exception as e:
        print("compute_trend 失败:", e)
        return []


def compute_summary():
    """统计汇总：供 /api/stats/summary 与后台统计页使用。"""
    return {
        "total_visits": VisitLog.query.count(),
        "today_visits": VisitLog.query.filter_by(date=today_str()).count(),
        "today_date": today_str(),
        "regions_today": _top_region(date=today_str()),
        "regions_all": _top_region(),
        "hot_posts": _hot_posts(),
        "hot_searches": _hot_searches(),
        "hourly": _hourly(),
        "trend": compute_trend(30),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
