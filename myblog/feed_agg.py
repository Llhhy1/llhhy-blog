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


def _safe_url(url):
    """SSRF 防护：仅放行公网 http/https，拦截内网/回环地址。"""
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
