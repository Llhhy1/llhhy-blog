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

from models import db, Post, VisitLog, ReadLog, SearchLog, IpRegion, Comment, Subscriber, visible_posts_query
from flask import request
from utils import detect_bot, fmt_bj, to_beijing, BEIJING_TZ, parse_device
from _time import utcnow
import logging

# v3.23.0：print → logger（格式/级别见 logging_setup）
logger = logging.getLogger(__name__)

_LOCAL_IPS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


def today_str():
    return datetime.date.today().isoformat()


def client_ip():
    """取客户端真实 IP：Nginx 反代后优先 X-Forwarded-For，但仅当请求确由可信代理转发。

    安全加固：旧实现（含 v3.4.7「只接受合法公网 XFF 首段」）仍可被攻击者伪造任意
    公网 XFF 首段并轮换，绕过注册/登录/评论/点赞限流与访问埋点。改为：XFF 仅在
    TCP 直连对端 remote_addr 为可信代理（内部地址，经 Nginx 转发）时才采纳，且取
    XFF 最右端真实客户端 IP；公网直连请求一律忽略 XFF，以不可伪造的 remote_addr
    为准。统一收口逻辑见 utils.get_client_ip。
    """
    from utils import get_client_ip
    return get_client_ip()


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


def _split_device(ua):
    """把 UA 解析成 (设备类型, 浏览器) 两个粗分类，**不返回原始 UA**。

    parse_device() 固定返回「设备 · 系统 · 浏览器」三段，取首尾两段。
    系统（OS）刻意不落库：它与设备类型高度相关（Android→手机、Windows /
    macOS→电脑），单独成列对分布统计没有增量信息。
    """
    parts = (parse_device(ua) or "").split(" · ")
    device = parts[0].strip()[:40] if parts else ""
    browser = parts[2].strip()[:40] if len(parts) > 2 else ""
    return device, browser


def record_visit(path, post_id=None, referrer=""):
    """记录一次访问；属地解析异步回填。任何异常都不影响页面本身。"""
    try:
        ip = client_ip()
        ua = request.headers.get("User-Agent", "")
        is_bot, bot_name, bot_category = detect_bot(ua)
        # v3.17.3：referrer 只保留 origin（协议+域名），不落完整 URL，
        # 避免把外链 query 里的 token/隐私参数写进日志。
        origin = ""
        r = (referrer or "").strip()
        if r.startswith(("http://", "https://")):
            try:
                pr = urllib.parse.urlsplit(r)
                origin = ((pr.scheme or "https") + "://" + pr.netloc)[:300] if pr.netloc else ""
            except Exception:
                origin = ""
        # v4.9.0：只落解析后的设备类型与浏览器，**不存原始 UA**（可指纹化）。
        # parse_device 固定返回「设备 · 系统 · 浏览器」三段，切片取首尾即可。
        device, browser = _split_device(ua)
        db.session.add(VisitLog(
            date=today_str(), hour=datetime.datetime.now().hour,
            ip=ip, region="", path=(path or "")[:255], post_id=post_id,
            is_bot=is_bot, bot_name=bot_name, bot_category=bot_category,
            referrer=origin, device=device, browser=browser,
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


# 单次阅读停留秒数的合理上限：封顶 2 小时。
# duration 完全由客户端上报、**不可信** —— 不钳制的话一个伪造请求
# (`{"slug":"x","duration":999999}`) 就能把「平均阅读时间」抬到任意值。
# 超过 2 小时基本是客户端时钟异常或页面被挂起整夜，不该计入均值。
_MAX_READ_SECONDS = 7200


def _clamp_read_seconds(raw):
    """把客户端上报的时长夹到 [0, 7200] 秒；非法输入一律当 0（不上报）。"""
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return 0 if v <= 0 else min(v, _MAX_READ_SECONDS)


def record_read(post_id, ip, duration=0):
    """文章阅读 +1；同一访客重复读同一篇会累加 read_count 与 duration。

    `duration`（秒，v4.5.0）由前端在页面隐藏/离开时上报，经 `_clamp_read_seconds`
    钳制后再累加。异常静默（同旧行为：埋点失败不该影响读者读文章）。
    """
    if not post_id:
        return
    secs = _clamp_read_seconds(duration)
    try:
        row = ReadLog.query.filter_by(post_id=post_id, ip=ip).first()
        if row:
            row.read_count += 1
            row.duration = (row.duration or 0) + secs
        else:
            db.session.add(ReadLog(post_id=post_id, ip=ip, read_count=1,
                                    duration=secs))
        db.session.commit()
    except Exception:
        db.session.rollback()


def add_read_duration(post_id, ip, duration=0):
    """只累加停留时长，**不动 read_count**（v4.5.0）。

    为什么必须与 `record_read` 分开：`read_count` 的语义是「打开了几次」，
    而停留时长会在切后台、跳下一篇文章时多次补报。若两者复用同一入口，
    读者一次阅读会被记成两三次 —— 热门文章榜与「反复阅读」榜双双虚高。

    `read_count` 为 0 的时段（钳制后）直接跳过：低于 3 秒的秒开秒关没有
    统计意义，留着只会把均值往 0 拉。

    记录不存在时**不凭空造行**：时长必须挂在一次真实阅读上，否则
    `SUM(duration)/SUM(read_count)` 的分母里会多出没有阅读的时长。
    """
    if not post_id:
        return
    secs = _clamp_read_seconds(duration)
    if not secs:
        return
    try:
        row = ReadLog.query.filter_by(post_id=post_id, ip=ip).first()
        if row is None:
            return
        row.duration = (row.duration or 0) + secs
        db.session.commit()
    except Exception:
        db.session.rollback()


def _top_region(limit=10, date=None):
    """访客属地排行（**仅真人**，爬虫不计入）。

    ⚠️ v4.5.0 修复：此前只过滤空属地，漏了 `is_bot`。爬虫多为境外机房 IP，
    属地异步回填后会挤占真人省份的名次（榜单里混进"美国· fremont"这类机房）。
    前台公开接口 `/api/geo/visitors`（`api/review.py`）一直都有
    `is_bot.is_(False)`，此处属**遗漏而非设计**，现与之一致。
    """
    q = db.session.query(VisitLog.region, db.func.count(VisitLog.id).label("c"))
    if date:
        q = q.filter(VisitLog.date == date)
    q = q.filter(VisitLog.region != "", VisitLog.is_bot.is_(False))
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
    # ReadLog.post_id 是任意历史 id：隐私/回收站文章的标题与 slug 会顺着
    # `/api/stats/summary`（未鉴权）直接外泄，所以按访客可见性取回。
    ids = [r[0] for r in rows if r[0] is not None]
    by_id = {p.id: p for p in visible_posts_query().filter(Post.id.in_(ids)).all()}
    result = []
    for post_id, reads, readers in rows:
        p = by_id.get(post_id)
        if not p:
            continue
        result.append({"slug": p.slug, "title": p.title,
                       "reads": int(reads), "readers": int(readers)})
    return result


def _avg_read_seconds():
    """v4.5.0：平均单次阅读时长（秒）。无有效数据返回 0。

    两个口径上的坑，都必须避开：

    1. **分母用 `SUM(read_count)` 而不是 `COUNT(*)`**。`ReadLog` 一行代表
       「一个访客对一篇的累计」，行数是访客数而非阅读次数 —— 同一访客读了
       5 次，用 COUNT(*) 当分母会把均值压到 1/5。
    2. **只算 `duration > 0` 的行**。升级前的历史阅读 duration 全是 0，
       把它们计进分母，均值会被拉到接近 0（真实数据一进来就"人均 0.3 秒"）。
    """
    row = (db.session.query(
        db.func.coalesce(db.func.sum(ReadLog.duration), 0),
        db.func.coalesce(db.func.sum(ReadLog.read_count), 0))
        .filter(ReadLog.duration > 0).first())
    if not row or not row[1]:
        return 0
    return int(round(row[0] / row[1]))


def _hot_searches(limit=10):
    rows = db.session.query(SearchLog.keyword, db.func.count(SearchLog.id).label("c"))\
        .group_by(SearchLog.keyword)\
        .order_by(db.desc("c"), db.desc(SearchLog.id)).limit(limit).all()
    return [{"keyword": r[0], "count": r[1]} for r in rows]


def _bot_breakdown(limit=20):
    """爬虫来源排行：按 bot_name + category 分组计数（仅 is_bot=True）。"""
    try:
        rows = (db.session.query(VisitLog.bot_name, VisitLog.bot_category,
                                 db.func.count(VisitLog.id).label("c"))
                .filter(VisitLog.is_bot == True)
                .group_by(VisitLog.bot_name, VisitLog.bot_category)
                .order_by(db.desc("c")).limit(limit).all())
        return [{"name": r[0], "category": r[1], "count": r[2]} for r in rows]
    except Exception:
        return []


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
        logger.warning("compute_trend 失败: %s", e)
        return []


def compute_dashboard_trend(days=30):
    """驾驶舱趋势序列（v3.11.0 二期）：在 PV/UV 之上叠加每日新增评论量与新文量。

    与 compute_trend 保持同样的「连续日期补齐」语义（缺失日期补 0），便于前端
    画连续折线。评论量按 Comment.created_at 当日新增计数、新文量按
    Post.created_at 当日发布计数，二者与 PV/UV 量级差异大，前端用独立刻度绘制。
    """
    try:
        days = max(1, min(int(days), 90))
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days - 1)

        vrows = (db.session.query(VisitLog.date, VisitLog.ip)
                 .filter(VisitLog.date >= start.isoformat(),
                         VisitLog.date <= end.isoformat()).all())
        pv = {}
        uv = {}
        for d, ip in vrows:
            pv[d] = pv.get(d, 0) + 1
            uv.setdefault(d, set()).add(ip)

        crows = (db.session.query(db.func.date(Comment.created_at))
                 .filter(db.func.date(Comment.created_at) >= start.isoformat(),
                         db.func.date(Comment.created_at) <= end.isoformat()).all())
        comments = {}
        for (cd,) in crows:
            comments[cd] = comments.get(cd, 0) + 1

        prows = (db.session.query(db.func.date(Post.created_at))
                 .filter(db.func.date(Post.created_at) >= start.isoformat(),
                         db.func.date(Post.created_at) <= end.isoformat()).all())
        posts = {}
        for (pd,) in prows:
            posts[pd] = posts.get(pd, 0) + 1

        result = []
        cur = start
        while cur <= end:
            ds = cur.isoformat()
            result.append({
                "date": ds,
                "pv": pv.get(ds, 0),
                "uv": len(uv.get(ds, set())),
                "comments": comments.get(ds, 0),
                "posts": posts.get(ds, 0),
            })
            cur += datetime.timedelta(days=1)
        return result
    except Exception as e:
        logger.warning("compute_dashboard_trend 失败: %s", e)
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
        "avg_read_seconds": _avg_read_seconds(),
        "hourly": _hourly(),
        "trend": compute_trend(30),
        "bot_visits": VisitLog.query.filter_by(is_bot=True).count(),
        "human_visits": VisitLog.query.filter_by(is_bot=False).count(),
        "bot_today": VisitLog.query.filter_by(date=today_str(), is_bot=True).count(),
        "bot_breakdown": _bot_breakdown(),
        # v3.20.0：统计深度（ROADMAP §5.2）—— 全部复用既有字段，**零表结构变更**
        "referrers": _top_referrers(),
        # v4.9.0：设备 / 浏览器分布（ROADMAP §3.1）—— 只加两列，无新表
        "devices": _top_devices(),
        "browsers": _top_browsers(),
        "online": compute_online(),
        "compare": compute_period_compare(),
        "updated_at": fmt_bj(utcnow(), "%Y-%m-%d %H:%M:%S"),
    }


# ---------- v3.20.0 统计深度（ROADMAP §5.2）----------
# 设计前提：**不改表结构**。因此只使用 VisitLog 既有字段：
#   * `referrer`（v3.17.3 起**只存 origin**，不含 query/path）→ 可做来源渠道，且天然不泄隐私
#   * `date` / `hour` / `ip`（均有索引）→ 可做趋势与环比
#   * `created_at` → 可做「实时在线」的近似值
# ⚠️ **设备/浏览器分布本批不做**：VisitLog 没有 UA 字段，要实现必须新增列 ——
#    与项目「能不改表结构就不改」的原则冲突，故列在 ROADMAP 待办而非强做。

_REFERRER_LABELS = (
    ("google.", "Google"), ("bing.", "Bing"), ("baidu.", "百度"),
    ("duckduckgo.", "DuckDuckGo"), ("so.com", "360搜索"), ("sogou.", "搜狗"),
    ("sm.cn", "神马搜索"), ("yandex.", "Yandex"),
    ("mp.weixin.", "微信"), ("weibo.", "微博"), ("zhihu.", "知乎"),
    ("x.com", "X / Twitter"), ("twitter.", "X / Twitter"),
    ("facebook.", "Facebook"), ("linkedin.", "LinkedIn"),
    ("juejin.", "掘金"), ("csdn.", "CSDN"), ("v2ex.", "V2EX"), ("github.", "GitHub"),
)


def _label_referrer(ref):
    """把来源 origin 映射成可读名字；未知来源退回域名本身。"""
    if not ref:
        return "直接访问"
    low = ref.lower()
    for key, name in _REFERRER_LABELS:
        if key in low:
            return name
    return ref.split("//")[-1].split("/")[0]


def _top_referrers(limit=10, days=30):
    """来源渠道 TOP N。空 referrer 视为「直接访问」，不参与聚合（由前端另算）。"""
    try:
        end = datetime.date.today()
        start = (end - datetime.timedelta(days=days - 1)).isoformat()
        rows = (db.session.query(VisitLog.referrer, db.func.count(VisitLog.id).label("c"))
                .filter(VisitLog.referrer != "",
                        VisitLog.date >= start, VisitLog.date <= end.isoformat())
                .group_by(VisitLog.referrer)
                .order_by(db.desc("c")).limit(limit).all())
        return [{"source": _label_referrer(r[0]), "count": r[1]} for r in rows]
    except Exception:  # noqa: BLE001  (来源聚合失败不应拖垮统计页)
        return []


def _top_field(field, limit=10, days=30):
    """按 VisitLog 的某个分类列做 TOP N 聚合（设备 / 浏览器共用同一套逻辑）。

    **空串不参与聚合**：空串表示「v4.9.0 之前的老访问没采集」，若计入会
    聚成一大坨「未知」档，把升级后的真实分布压扁。宁可样本少也要分布准。
    """
    try:
        end = datetime.date.today()
        start = (end - datetime.timedelta(days=days - 1)).isoformat()
        rows = (db.session.query(field, db.func.count(VisitLog.id).label("c"))
                .filter(field != "",
                        VisitLog.date >= start, VisitLog.date <= end.isoformat())
                .group_by(field)
                .order_by(db.desc("c")).limit(limit).all())
        return [{"name": r[0], "count": r[1]} for r in rows]
    except Exception:  # noqa: BLE001  (分布聚合失败不应拖垮统计页)
        return []


def _top_devices(limit=10, days=30):
    """设备类型 TOP N（手机 / 平板 / 电脑 / 爬虫）。"""
    return _top_field(VisitLog.device, limit=limit, days=days)


def _top_browsers(limit=10, days=30):
    """浏览器 TOP N（Chrome / Safari / 微信…）。"""
    return _top_field(VisitLog.browser, limit=limit, days=days)


def compute_online(minutes=10):
    """「实时在线」**近似值**：最近 N 分钟内的独立 IP 数。

    ⚠️ 它是近似值不是精确在线人数：本项目没有会话表，只能按 VisitLog 的
    独立 IP 推算 —— NAT / 换网络会重复计数，反之短时无请求会被漏掉。
    取名 `online` 而不是 `online_users` 就是为了避免被误当成精确值。
    """
    try:
        cutoff = utcnow() - datetime.timedelta(minutes=minutes)
        n = (db.session.query(db.func.count(db.func.distinct(VisitLog.ip)))
             .filter(VisitLog.created_at >= cutoff)
             .filter(VisitLog.is_bot.is_(False)).scalar())
        return int(n or 0)
    except Exception:  # noqa: BLE001  (在线数估算失败不应拖垮统计页)
        return 0


def compute_period_compare(days=7):
    """本期 vs 上一期**环比**（PV / UV / 评论 / 订阅）。

    分母为 0 时 `pct` 返回 `None`（而不是 0 或无穷大）——
    环比在上期为 0 时**没有百分比意义**，前端应显示为「—」而不是 0%。
    """
    def _delta(cur, prev):
        pct = None if prev == 0 else round((cur - prev) * 100.0 / prev, 1)
        return {"cur": cur, "prev": prev, "pct": pct}

    try:
        end = datetime.date.today()
        cur_start = (end - datetime.timedelta(days=days - 1)).isoformat()
        prev_end = (end - datetime.timedelta(days=days)).isoformat()
        prev_start = (end - datetime.timedelta(days=days * 2 - 1)).isoformat()

        def _agg(a, b):
            rows = (db.session.query(VisitLog.date, VisitLog.ip)
                    .filter(VisitLog.date >= a, VisitLog.date <= b).all())
            return {"pv": len(rows), "uv": len({ip for _, ip in rows})}

        cur, prev = _agg(cur_start, end.isoformat()), _agg(prev_start, prev_end)
        return {
            "days": days,
            "pv": _delta(cur["pv"], prev["pv"]),
            "uv": _delta(cur["uv"], prev["uv"]),
            # 评论 / 订阅：按创建时间区间统计（两者都有 created_at）
            "comments": _delta(
                Comment.query.filter(Comment.created_at >= _dt(cur_start),
                                     Comment.created_at < _dt_tomorrow(end)).count(),
                Comment.query.filter(Comment.created_at >= _dt(prev_start),
                                     Comment.created_at < _dt(prev_end + "T24")).count()),
            "subscribers": _delta(
                Subscriber.query.filter(Subscriber.created_at >= _dt(cur_start),
                                        Subscriber.created_at < _dt_tomorrow(end)).count(),
                Subscriber.query.filter(Subscriber.created_at >= _dt(prev_start),
                                        Subscriber.created_at < _dt(prev_end + "T24")).count()),
        }
    except Exception:  # noqa: BLE001  (环比计算失败不应拖垮统计页)
        return {"days": days, "pv": _delta(0, 0), "uv": _delta(0, 0),
                "comments": _delta(0, 0), "subscribers": _delta(0, 0)}


def _dt(date_str):
    """'YYYY-MM-DD' → 当日 00:00 的 naive datetime（与库里 utcnow() 同一口径）。"""
    return datetime.datetime.strptime(date_str, "%Y-%m-%d")


def _dt_tomorrow(end_date):
    """'YYYY-MM-DD' → 次日 00:00（用作半开区间上界）。"""
    return _dt((end_date + datetime.timedelta(days=1)).isoformat())


def compute_dashboard(range_days=30):
    """运营驾驶舱聚合（UI清单 B · P0 运营驾驶舱）。

    在 compute_summary() 的只读聚合之上，追加核心运营指标与「环比」
    （vs 昨日 / vs 上周同日）。全部查询为只读，单指标失败静默降级为 0，
    不拖垮整个端点（沿用项目「降级范式」）。

    range_days：趋势序列区间（7/30/90 天，默认 30），仅影响 trend，不影响
    卡片指标（卡片永远是「今日」快照 + vs 昨日 / vs 上周同期环比）。
    """
    base = compute_summary()
    today = today_str()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    last_week = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

    def _since(model, day):
        try:
            return model.query.filter(db.func.date(model.created_at) == day).count()
        except Exception:
            return 0

    def _deltapct(cur, prev):
        if prev is None or prev == 0:
            return None  # 无基数：前端展示「新」而不是百分比
        return round((cur - prev) / prev * 100, 1)

    # —— 访问 PV / UV（UV=去重 IP，排除 Bot）——
    try:
        today_uv = db.session.query(
            db.func.count(db.func.distinct(VisitLog.ip))
        ).filter(VisitLog.date == today, VisitLog.is_bot == False).scalar() or 0
        yest_uv = db.session.query(
            db.func.count(db.func.distinct(VisitLog.ip))
        ).filter(VisitLog.date == yesterday, VisitLog.is_bot == False).scalar() or 0
        lw_uv = db.session.query(
            db.func.count(db.func.distinct(VisitLog.ip))
        ).filter(VisitLog.date == last_week, VisitLog.is_bot == False).scalar() or 0
    except Exception:
        today_uv = yest_uv = lw_uv = 0
    today_pv = base.get("today_visits", 0)
    yest_pv = _safe_count(VisitLog, date=yesterday)
    lw_pv = _safe_count(VisitLog, date=last_week)

    # —— 订阅 ——
    subs_total = _safe_count(Subscriber)
    new_subs_today = _since(Subscriber, today)
    new_subs_week = _since(Subscriber, last_week)

    # —— 评论（未读=待审核 approved=False）——
    comments_total = _safe_count(Comment)
    comments_unread = _safe_count(Comment, approved=False)
    new_comments_today = _since(Comment, today)
    new_comments_week = _since(Comment, last_week)

    # —— 文章 ——
    posts_total = _safe_count(Post)
    new_posts_today = _since(Post, today)
    new_posts_week = _since(Post, last_week)

    metrics = {
        "pv_today": today_pv, "uv_today": today_uv,
        "subs_total": subs_total, "comments_total": comments_total,
        "comments_unread": comments_unread,
        "posts_total": posts_total,
        "new_subs_today": new_subs_today, "new_subs_week": new_subs_week,
        "new_comments_today": new_comments_today, "new_comments_week": new_comments_week,
        "new_posts_today": new_posts_today, "new_posts_week": new_posts_week,
    }
    deltas = {
        "pv_dod": _deltapct(today_pv, yest_pv), "pv_wow": _deltapct(today_pv, lw_pv),
        "uv_dod": _deltapct(today_uv, yest_uv), "uv_wow": _deltapct(today_uv, lw_uv),
        "subs_dod": _deltapct(new_subs_today, _since(Subscriber, yesterday)),
        "subs_wow": _deltapct(new_subs_today, new_subs_week),
        "comments_dod": _deltapct(new_comments_today, _since(Comment, yesterday)),
        "comments_wow": _deltapct(new_comments_today, new_comments_week),
        "posts_dod": _deltapct(new_posts_today, _since(Post, yesterday)),
        "posts_wow": _deltapct(new_posts_today, new_posts_week),
    }
    return {
        "generated_at": fmt_bj(utcnow(), "%Y-%m-%d %H:%M:%S"),
        "metrics": metrics,
        "deltas": deltas,
        "hot_reads": (base.get("hot_posts") or [])[:5],
        "hot_searches": (base.get("hot_searches") or [])[:5],
        "active_regions": (base.get("regions_today") or [])[:5],
        # 驾驶舱趋势：按所选区间（7/30/90 天）叠加 PV/UV + 评论量 + 新文量
        "trend": compute_dashboard_trend(range_days),
        "hourly": base.get("hourly", []),
        "regions_today": base.get("regions_today", []),
        "regions_all": base.get("regions_all", []),
        "total_visits": base.get("total_visits", 0),
        "today_visits": today_pv,
        "today_date": today,
    }


def _safe_count(model, **filters):
    """安全计数：任一过滤条件抛错都返回 0（降级范式）。"""
    try:
        q = model.query
        for k, v in filters.items():
            q = q.filter(getattr(model, k) == v)
        return q.count()
    except Exception:
        return 0


# ---------- v4.2.0 访客数据多区间（后台运营精细化）----------
# 设计前提（延续 v3.20.0）：**零表结构变更** —— 只用 VisitLog 既有字段：
#   `date`（"YYYY-MM-DD" 字符串，字典序 = 日期序，有索引）、`ip`、`is_bot`、
#   `region`、`path`、`referrer`、`hour`。
# ⚠️ 区间边界按**本地日期**（与 VisitLog.date 同口径）切，不用 created_at（UTC）——
#    否则 UTC+8 下「今天」会少算 8 小时、跨日边界对不上。
RANGE_PRESETS = (
    ("today", "今天"),
    ("yesterday", "昨天"),
    ("7d", "近 7 天"),
    ("15d", "近半月"),
    ("30d", "近 1 月"),
    ("90d", "近 3 月"),
    ("180d", "近 6 月"),
    ("365d", "近 1 年"),
    ("730d", "近 2 年"),
)
DEFAULT_RANGE = "7d"
_RANGE_DAYS = {"7d": 7, "15d": 15, "30d": 30, "90d": 90, "180d": 180,
               "365d": 365, "730d": 730}


def resolve_range(key):
    """区间 key → (生效key, start, end, label)。非法 key 回落 DEFAULT_RANGE。

    返回 date 对象（调用方自行 isoformat），label 供界面展示。
    「今天 / 昨天」是单日区间（start == end）；其余为「近 N 天」含今天。
    """
    today = datetime.date.today()
    key = (key or "").strip()
    if key == "today":
        return "today", today, today, "今天"
    if key == "yesterday":
        y = today - datetime.timedelta(days=1)
        return "yesterday", y, y, "昨天"
    days = _RANGE_DAYS.get(key)
    if not days:
        key, days = DEFAULT_RANGE, _RANGE_DAYS[DEFAULT_RANGE]
    return (key, today - datetime.timedelta(days=days - 1), today,
            dict(RANGE_PRESETS)[key])


def _range_top(field, start_iso, end_iso, limit=10, exclude_empty=True,
               human_only=False):
    """区间内某字段 TOP N（按次数降序）。字段名受本模块内部控制，不可外部注入。

    `human_only=True` 排除爬虫（v4.5.0）。**只在属地维度开启**：
    属地榜是"读者来自哪"，混入机房 IP 没有意义；而 `path`（热门页面）里
    爬虫抓取本身就是真实热度，来源渠道榜的爬虫 referrer 则是其自身来源、
    本就没有读者信息 —— 两者都不该跟着属地一起被过滤。
    """
    col = getattr(VisitLog, field)
    q = db.session.query(col, db.func.count(VisitLog.id).label("c"))
    q = q.filter(VisitLog.date >= start_iso, VisitLog.date <= end_iso)
    if human_only:
        q = q.filter(VisitLog.is_bot.is_(False))
    if exclude_empty:
        q = q.filter(col != "")
    rows = q.group_by(col).order_by(db.desc("c")).limit(limit).all()
    return [{"key": r[0], "count": r[1]} for r in rows]


def _range_top_referrers(start_iso, end_iso, limit=10):
    """来源渠道 TOP N：先按 origin 聚合，再按可读名**归一合并**。

    ⚠️ 不能先分组后各自改名就完事 —— 同一引擎常有多个域名
    （www.baidu.com / m.baidu.com / sp0.baidu.com），不合并会被拆成
    多行、每行计数偏小，排行失去意义。故先多取一些原始分组（limit×5），
    按标签求和后再截断到 limit。
    """
    merged = {}
    for r in _range_top("referrer", start_iso, end_iso, limit=limit * 5):
        label = _label_referrer(r["key"])
        merged[label] = merged.get(label, 0) + r["count"]
    return [{"key": k, "count": v}
            for k, v in sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _range_distinct_ip(start_iso, end_iso, human_only=False, bot_only=False):
    """区间内独立 IP 数（UV）。human_only / bot_only 二选一（都不传 = 全部）。

    ⚠️ bot_only 必须**直接查**而不是「全部 UV - 真人 UV」：同一个 IP 完全可能
    既以真人身份访问、又被识别为爬虫（如共享出口 / 云主机），减法会把这种
    混合 IP 错算成「爬虫独立 IP」。
    """
    q = db.session.query(db.func.count(db.func.distinct(VisitLog.ip)))
    q = q.filter(VisitLog.date >= start_iso, VisitLog.date <= end_iso)
    if human_only:
        q = q.filter(VisitLog.is_bot.is_(False))
    elif bot_only:
        q = q.filter(VisitLog.is_bot.is_(True))
    return int(q.scalar() or 0)


def compute_range_stats(range_key=DEFAULT_RANGE):
    """按预设区间聚合访客数据（v4.2.0，后台「访问统计」页区间切换用）。

    输出：PV / UV（分真人·爬虫）/ 区间新增评论 / TOP 路径·属地·来源。
    每个子查询独立降级（失败返回 0 或 []），不拖垮整页（降级范式）。
    """
    eff_key, start, end, label = resolve_range(range_key)
    s, e = start.isoformat(), end.isoformat()

    def _guard(fn, default):
        try:
            return fn()
        except Exception as err:  # noqa: BLE001 —— 单指标失败不应拖垮统计页
            logger.warning("compute_range_stats 子查询失败: %s", err)
            return default

    return {
        "key": eff_key, "label": label, "start": s, "end": e,
        "days": (end - start).days + 1,
        "pv": _guard(lambda: VisitLog.query.filter(
            VisitLog.date >= s, VisitLog.date <= e).count(), 0),
        "uv": _guard(lambda: _range_distinct_ip(s, e), 0),
        "human_pv": _guard(lambda: VisitLog.query.filter(
            VisitLog.date >= s, VisitLog.date <= e,
            VisitLog.is_bot.is_(False)).count(), 0),
        "human_uv": _guard(lambda: _range_distinct_ip(s, e, human_only=True), 0),
        "bot_pv": _guard(lambda: VisitLog.query.filter(
            VisitLog.date >= s, VisitLog.date <= e,
            VisitLog.is_bot.is_(True)).count(), 0),
        "bot_uv": _guard(lambda: _range_distinct_ip(s, e, bot_only=True), 0),
        "new_comments": _guard(lambda: Comment.query.filter(
            Comment.created_at >= _dt(s),
            Comment.created_at < _dt_tomorrow(end)).count(), 0),
        "top_paths": _guard(lambda: _range_top("path", s, e, limit=10), []),
        "top_regions": _guard(
            lambda: _range_top("region", s, e, limit=10, human_only=True), []),
        "top_referrers": _guard(lambda: _range_top_referrers(s, e, limit=10), []),
    }

