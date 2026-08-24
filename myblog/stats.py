"""访问统计工具：IP 属地解析（缓存 + 在线接口兜底）、访问/搜索/阅读记录、汇总统计。

设计要点：
- 访问记录为同步写入（极快），IP 属地解析放在后台线程里做，绝不阻塞页面响应；
- 属地解析结果缓存到 IpRegion 表，避免每个访客都请求在线接口；
- 对外提供 compute_summary()，同时供 /api/stats/summary 与后台统计页使用。
"""
import datetime
import ipaddress
import json
import threading
import time
import urllib.parse
import urllib.request

from models import db, Post, VisitLog, ReadLog, SearchLog, IpRegion, Comment

_LOCAL_IPS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


def today_str():
    return datetime.date.today().isoformat()


def client_ip():
    """取客户端真实 IP：Nginx 反代后优先 X-Forwarded-For 第一个值。

    全量审计加固：旧实现无条件取 XFF 首段，攻击者可伪造
    `X-Forwarded-For: 127.0.0.1` 或任意值循环变化，绕过限流（注册/登录/评论/点赞）、
    刷爆视图/阅读/搜索埋点。改为**只接受合法公网 IP**（不合法则回退 remote_addr，
    remote_addr 是 Nginx 与本服务 TCP 直连地址，不可伪造）——限流/埋点/属地全部收口，
    杜绝伪造 XFF。
    """
    from flask import request
    xff = request.headers.get("X-Forwarded-For", "")
    cand = xff.split(",")[0].strip() if xff else ""
    if cand and _is_safe_public_ip(cand):
        return cand
    return request.remote_addr or ""


# 常见英文国家 / 地区名 → 中文（属地字段最终展示用，统一中文更清爽）
# 同时收录 ISO 3166-1 alpha-2 两位码（ipinfo.io 等源返回 "CN"/"US"），
# 归一后再做整词替换，杜绝 "CN广东" 这类不干净结果（v3.4.7 修复）。
_REGION_EN2CN = {
    "CN": "中国", "China": "中国", "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾",
    "US": "美国", "USA": "美国", "United States": "美国", "UnitedStates": "美国",
    "CA": "加拿大", "Canada": "加拿大",
    "GB": "英国", "UK": "英国", "United Kingdom": "英国", "England": "英格兰", "Scotland": "苏格兰",
    "JP": "日本", "Japan": "日本", "Tokyo": "东京",
    "KR": "韩国", "Korea": "韩国", "South Korea": "韩国",
    "SG": "新加坡", "Singapore": "新加坡",
    "AU": "澳大利亚", "Australia": "澳大利亚",
    "DE": "德国", "Germany": "德国", "FR": "法国", "France": "法国",
    "RU": "俄罗斯", "Russia": "俄罗斯", "IN": "印度", "India": "印度",
    "BR": "巴西", "Brazil": "巴西",
    "California": "加利福尼亚", "Guangdong": "广东", "Beijing": "北京",
    "Shanghai": "上海", "Zhejiang": "浙江", "New York": "纽约",
}
# 英文 state/region 常见后缀（仅用于信息性清理，不影响展示主体）
_REGION_EN_SUFFIX = ("State", "Province", "Prefecture", "County", "City", "Region", "District")

def short_region(raw):
    """把"浙江省 杭州市"缩成"浙江·杭州"；英文属地统一转中文，排行展示更清爽。

    v3.4.7 修复：旧实现只剥中文字尾（省/市/...），对国外 IP 返回的英文
    "United States California" 仅去掉空格变成 "UnitedStatesCalifornia"，
    既难看又会把英文塞进前端「📍 属地」展示。改为先做英文→中文归一
    （含 ISO2 码如 CN→中国），再剥中文字尾，最终拿到干净的中文属地
    （如「美国加利福尼亚」「广东广州」）。
    """
    if not raw:
        return ""
    raw = raw.replace("·", " ")
    # 逐词英文→中文归一（国家名、州/省名优先整词替换）
    for en, cn in _REGION_EN2CN.items():
        raw = raw.replace(en, cn)
    # 清理残留的英文州/省后缀标签（如 "California State" 已转"加利福尼亚"后无残留，
    # 这里兜底处理未收录的英文地区名后缀）
    for suf in _REGION_EN_SUFFIX:
        raw = raw.replace(suf, "")
    raw = raw.replace(" ", "")
    for suf in ("壮族自治区", "回族自治区", "维吾尔自治区", "特别行政区",
                "自治区", "省", "市", "区", "县"):
        raw = raw.replace(suf, "")
    return raw


def _looks_corrupted(text):
    """启发式判断属地文本是否乱码（GBK 字节被当 UTF-8 吞掉的历史脏数据）。

    正常属地（short_region 归一后）只含常用区汉字（U+4E00–U+9FFF）、数字、
    空格与常见标点；GBK 误解码产物（如 `㽭ʡ` U+3F6D + U+02A1）落在 CJK
    扩展区/IPA 等稀有区，会被识别为脏。命中则忽略缓存、在线重查并覆盖旧值，
    实现历史乱码自愈（v3.4.9 修复）。
    """
    if not text:
        return False
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF:          # 常用汉字：正常
            continue
        if ch in " 0123456789·・（）、，。,.·-":  # 数字/空格/常见标点：正常
            continue
        return True                         # 出现稀有区/IPA/拉丁残留：判定脏
    return False


def _is_safe_public_ip(ip):
    """仅允许合法、且为公网可查的 IP 进入外部查询。

    v3.4.7 加固：在格式校验(_is_valid_ip)基础上，额外排除私网/环回/链路本地/
    保留/多播地址，避免把内网 IP（10.x / 192.168.x / 100.64.x 等）无意义地
    发给外部地理库，也消除「内网 IP 查询泄密」的顾虑。
    注意：100.64.0.0/10（CGNAT，RFC 6598）部分 Python 版本的 ipaddress 未归入
    is_private，这里用 is_global 反向判断更稳（非全局可达即不查）。
    """
    try:
        a = ipaddress.ip_address(ip)
    except Exception:
        return False
    return a.is_global and not a.is_loopback and not a.is_multicast


def _http_get_json(url, timeout=4):
    """GET 并解析 JSON；兼容 UTF-8 与 GBK（太平洋 IP 库返回 GBK 编码）。

    v3.4.9 修复：旧实现优先 `decode("utf-8","ignore")`——ignore 模式**永不抛错**，
    中文被吞成乱码（`浙江省`→`㽭ʡ`）后 `json.loads` 照常成功，GBK 兜底分支
    永远走不到，属地图/评论属地全是乱码。改为：先用**严格** UTF-8 解码探测
    （遇非法字节抛 UnicodeDecodeError），失败再走 GBK；两种解析都失败才抛错，
    由调用方整体降级（不缓存乱码）。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (blog stats)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # 严格 UTF-8 解码，失败（GBK 字节）再回退 GBK；禁止 ignore 吞字节
    last_err = None
    for encoding in ("utf-8", "gbk"):
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue                  # 该编码无法解码，尝试下一个
        try:
            return json.loads(text)
        except Exception as e:
            last_err = e              # 解码成功但 JSON 非法：记下继续试下一个编码
            continue
    if last_err is not None:
        raise last_err from None
    raise UnicodeDecodeError("utf-8", raw, 0, len(raw), "GBK/UTF-8 均无法解码")


def _is_valid_ip(ip):
    """仅允许合法、且为公网可查的 IP 进入外部查询，杜绝 XFF 可控时的参数污染
    与内网 IP 被无意义外发。等价于 _is_safe_public_ip。"""
    return _is_safe_public_ip(ip)


# 失败节流：同一 IP 解析失败后 _FAIL_TTL 秒内不再打外部接口，避免接口全挂时狂打。
# _RECENT_FAIL 设容量护栏 + 过期清理，防止公网被扫描/DoS 时字典无界增长拖垮内存。
_RECENT_FAIL = {}
_FAIL_TTL = 3600
_FAIL_MAX = 5000


def _record_recent_fail(ip, now):
    """记录某 IP 解析失败，并做容量/过期裁剪（GIL 下 dict 操作原子，无需加锁）。"""
    _RECENT_FAIL[ip] = now
    if len(_RECENT_FAIL) > _FAIL_MAX:
        expired = [k for k, t in _RECENT_FAIL.items() if now - t >= _FAIL_TTL]
        for k in expired:
            _RECENT_FAIL.pop(k, None)
        while len(_RECENT_FAIL) > _FAIL_MAX:
            _RECENT_FAIL.pop(next(iter(_RECENT_FAIL)))


def _lookup_region(ip):
    """在线查询 IP 属地；多源兜底，全部失败返回 None。

    v3.4.7 修复：原实现只依赖 api.vore.top 与 ip-api.com 两个源，二者相继
    失效（vore.top 超时、ip-api.com 403）后，所有评论/访问的 region 恒为空，
    前台「📍 评论者属地」消失。改为国内源优先 + 国际源依次兜底的方案，并对
    XFF 可控的 ip 做格式校验（仅合法 IP 才查询），降低注入面。
    """
    if not _is_valid_ip(ip) or ip in _LOCAL_IPS:
        return None
    for fn in (_lookup_pconline, _lookup_ipwho, _lookup_ipsb, _lookup_ipinfo):
        try:
            r = fn(ip)
            if r:
                return r
        except Exception:
            continue
    return None


def _lookup_pconline(ip):
    """太平洋电脑网 IP 库：国内源，对 CN IP 返回中文省/市；外国 IP 返回空（交国际源）。"""
    d = _http_get_json("https://whois.pconline.com.cn/ipJson.jsp?ip=%s&json=true" % urllib.parse.quote(ip))
    if not isinstance(d, dict):
        return None
    pro = (d.get("pro") or "").strip()
    city = (d.get("city") or "").strip()
    if not pro and not city:
        return None
    return short_region((pro + " " + city).strip())


def _lookup_ipwho(ip):
    d = _http_get_json("https://ipwho.is/%s" % urllib.parse.quote(ip))
    if not isinstance(d, dict) or not d.get("success"):
        return None
    country = (d.get("country") or "").strip()
    region = (d.get("region") or "").strip()
    city = (d.get("city") or "").strip()
    raw = (region + " " + city).strip() if country == "China" else (country + " " + region).strip()
    return short_region(raw) if raw else None


def _lookup_ipsb(ip):
    d = _http_get_json("https://api.ip.sb/geoip/%s" % urllib.parse.quote(ip))
    if not isinstance(d, dict):
        return None
    country = (d.get("country") or "").strip()
    region = (d.get("region") or "").strip()
    city = (d.get("city") or "").strip()
    raw = (region + " " + city).strip() if country == "China" else (country + " " + region).strip()
    return short_region(raw) if raw else None


def _lookup_ipinfo(ip):
    d = _http_get_json("https://ipinfo.io/%s/json" % urllib.parse.quote(ip))
    if not isinstance(d, dict):
        return None
    country = (d.get("country") or "").strip()
    region = (d.get("region") or "").strip()
    city = (d.get("city") or "").strip()
    raw = (region + " " + city).strip() if country == "China" else (country + " " + region).strip()
    return short_region(raw) if raw else None


def _ensure_region(ip):
    """查缓存 → 在线解析 → 写缓存，返回区域字符串（可能为空）。

    v3.4.7 修复：旧实现把『解析失败(空)』也写进 IpRegion 缓存，导致外部源全挂时
    空结果被永久缓存、永不重试，属地彻底消失且无法自愈。改为：仅缓存成功的非空
    结果；失败不写入（并进入节流窗口），外部源恢复后下次访问即自动回填
    （含历史空属地评论）。
    """
    if not _is_valid_ip(ip) or ip in _LOCAL_IPS:
        return ""
    row = IpRegion.query.filter_by(ip=ip).first()
    if row and row.region:
        if not _looks_corrupted(row.region):
            return row.region      # 缓存结果干净：直接信任
        # 缓存疑似乱码（GBK 误解码遗留）：忽略，走在线重查覆盖（自愈）
        row.region = ""
    now = time.time()
    if ip in _RECENT_FAIL and now - _RECENT_FAIL[ip] < _FAIL_TTL:
        return ""                  # 节流：近期刚失败过，避免接口全挂时狂打
    region = _lookup_region(ip) or ""
    if region:
        if row:
            row.region = region
        else:
            db.session.add(IpRegion(ip=ip, region=region))
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        _record_recent_fail(ip, now)   # 记录失败时刻，进入节流窗口（含容量护栏）
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
    if row and row.region and not _looks_corrupted(row.region):
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
