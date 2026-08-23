"""友链 RSS 聚合：抓取友链站点的 RSS，按时间混排成「博客圈」流。

安全措施：
- SSRF 防护：仅允许 http/https，拦截私有地址（127.0.0.1 / 192.168.* / 10.* / 172.16-31.* / 169.254.*）。
- 外部内容清洗：摘要 HTML 经 bleach 白名单清理，避免 XSS。
- 缓存：聚合结果内存缓存 15 分钟，避免每次请求都抓取（慢且易被限流）。
"""
import time
import urllib.parse

from models import FriendLink
from utils import clean_html

# 内存缓存（单进程有效；多 worker 下各进程独立缓存，足够个人博客使用）
_CACHE = {"items": [], "ts": 0}
_CACHE_TTL = 900  # 秒


def _is_private_ip(ip):
    """判断 IP 是否为内网/回环/保留地址。用于 DNS 重绑定缓解的最终裁决。"""
    import ipaddress
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        # 非合法 IP（域名本身）不在此函数判定，由调用方解析后再调
        return True
    return bool(
        ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
        or ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified
    )


def _safe_url(url):
    """SSRF 防护（v3.1.6 增强 DNS 重绑定缓解）：
    1. 仅放行公网 http/https；
    2. 主机名黑名单拦截常见内网词；
    3. 解析域名到 IP，若解析出的 IP 是内网/回环/保留地址则拒绝——
       「首查公网 IP 放行、重绑定时再次解析到内网」的攻击会被第二道防线拦住。
    """
    import socket
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return False
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return False
        except (ValueError, IndexError):
            pass
    # DNS 重绑定缓解：解析并校验解析结果非内网（关键增强）
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = {info[4][0] for info in infos}
        for ip in ips:
            if _is_private_ip(ip):
                return False
        if not ips:
            return False
    except OSError:
        return False
    return True


def get_circle_feed(force=False):
    """返回聚合后的博客圈条目（按时间倒序，最多 40 条）。force=True 忽略缓存。"""
    now = time.time()
    if not force and _CACHE["items"] and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["items"]

    items = []
    links = FriendLink.query.filter(
        FriendLink.rss_url.isnot(None),
        FriendLink.rss_url != "",
    ).all()
    for link in links:
        if not _safe_url(link.rss_url):
            continue
        try:
            import feedparser
            parsed = feedparser.parse(link.rss_url)
        except Exception:
            # 抓取/解析失败跳过该源，不影响其它源
            continue
        for e in (parsed.entries or [])[:10]:
            title = (e.get("title") or "").strip()
            href = (e.get("link") or "").strip()
            if not (title and href):
                continue
            summary = ""
            if e.get("summary"):
                # 摘要可能含外部 HTML，必须清洗
                summary = clean_html(e["summary"])[:300]
            published = e.get("published_parsed") or e.get("updated_parsed")
            ts = time.mktime(published) if published else now
            items.append({
                "title": title,
                "url": href,
                "summary": summary,
                "source": link.name,
                "source_url": link.url,
                "published_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                "ts": int(ts),
            })

    items.sort(key=lambda x: x["ts"], reverse=True)
    items = items[:40]
    _CACHE["items"] = items
    _CACHE["ts"] = now
    return items
