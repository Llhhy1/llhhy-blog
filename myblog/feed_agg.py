"""友链 RSS 聚合：抓取友链站点的 RSS，按时间混排成「博客圈」流。

安全措施：
- SSRF 防护：仅允许 http/https，拦截私有地址（127.0.0.1 / 192.168.* / 10.* / 172.16-31.* / 169.254.*）。
- 外部内容清洗：摘要 HTML 经 bleach 白名单清理，避免 XSS。
- 缓存：聚合结果内存缓存 15 分钟，避免每次请求都抓取（慢且易被限流）。
"""
import sys
import time
import socket
import urllib.parse
import datetime

from models import FriendLink
from utils import clean_html, fmt_bj, to_beijing, BEIJING_TZ

# 内存缓存（单进程有效；多 worker 下各进程独立缓存，足够个人博客使用）
_CACHE = {"items": [], "ts": 0}
_CACHE_TTL = 900  # 秒
# v3.10.4：博客圈 RSS 抓取超时（秒）。防止不可达/超慢的源（如被墙的外站）卡死整个
# 聚合、甚至拖垮 gunicorn worker。运行时从 current_app.config["FEED_FETCH_TIMEOUT"] 读取（默认 8）。
FEED_FETCH_TIMEOUT = 8

# v3.8.6：自诊断（让前端/用户无需登服务器即可看到「博客圈为何为空」）
_LAST_DIAG = {
    "total_links": 0,
    "links_with_rss": 0,
    "feedparser_ok": True,
    "fetched": 0,
    "skipped": 0,
    "last_run": "",
    "notes": [],
    "per_link": [],
}


def get_last_diag():
    """返回最近一次聚合的诊断信息（供 /api/feed/circle 附在响应里）。"""
    return dict(_LAST_DIAG)


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


def _safe_url_fail_reason(url):
    """返回 _safe_url 拒绝的原因（仅供日志排查用，与 _safe_url 判定逻辑一一对应）。"""
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return "URL 无法解析"
    if p.scheme not in ("http", "https"):
        return f"协议 {p.scheme!r} 非 http/https"
    host = (p.hostname or "").lower()
    if not host:
        return "缺少主机名"
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return "主机为回环地址"
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return "主机为内网地址"
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return "主机为内网地址"
        except (ValueError, IndexError):
            pass
    import socket
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = {info[4][0] for info in infos}
        for ip in ips:
            if _is_private_ip(ip):
                return f"域名解析到内网/保留 IP（{ip}）"
        if not ips:
            return "域名解析结果为空"
    except OSError as e:
        return f"DNS 解析失败（{e}）——检查服务器出网/DNS"
    return "未知原因"


def validate_feed_url(url, timeout=8):
    """轻量校验：URL 是否可抓取且返回合法 RSS/Atom。返回 (ok, reason)，绝不抛异常。

    用途：后台保存友链 RSS 时做软校验（非阻塞，保存照常），提前暴露
    类似「/feed/ 被当首页返回 HTML」「域名不可达/被墙」这类问题。
    """
    if not url:
        return False, "RSS 地址为空"
    if not _safe_url(url):
        return False, _safe_url_fail_reason(url)
    import socket as _sock
    _old = _sock.getdefaulttimeout()
    _sock.setdefaulttimeout(timeout)
    try:
        import feedparser
        parsed = feedparser.parse(url)
        if getattr(parsed, "bozo", 0) and not parsed.entries:
            return False, "非合法 RSS/Atom（解析失败）"
        if not parsed.entries:
            return False, "RSS 合法但解析到 0 条"
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    finally:
        _sock.setdefaulttimeout(_old)


def get_circle_feed(force=False):
    """返回聚合后的博客圈条目（按时间倒序，最多 40 条）。force=True 忽略缓存。"""
    now = time.time()
    if not force and _CACHE["items"] and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["items"]

    # v3.10.4：抓取前设置全局 socket 超时，避免坏源卡死（finally 还原）。
    import socket as _sock
    try:
        from flask import current_app
        _timeout = int(current_app.config.get("FEED_FETCH_TIMEOUT", FEED_FETCH_TIMEOUT))
    except Exception:
        _timeout = FEED_FETCH_TIMEOUT
    _old_to = _sock.getdefaulttimeout()
    _sock.setdefaulttimeout(_timeout)
    try:
        # v3.8.6：重置诊断
        diag = {"total_links": 0, "links_with_rss": 0, "feedparser_ok": True,
                "fetched": 0, "skipped": 0, "last_run": "", "notes": []}

        items = []
        all_links = FriendLink.query.all()
        diag["total_links"] = len(all_links)
        links = [l for l in all_links if l.rss_url]
        diag["links_with_rss"] = len(links)
        diag["last_run"] = fmt_bj(datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc), "%Y-%m-%d %H:%M:%S")

        if not links:
            # v3.8.4：可观测性——聚合为空时区分「没填 RSS」与「抓取失败」，日志可查
            total_links = diag["total_links"]
            note = (f"共 {total_links} 条友链，其中 0 条填写了 RSS 地址"
                    f"（后台「友链管理」给友链填 RSS 地址即可聚合）")
            print(f"[FEED AGG] 博客圈聚合：{note}")
            diag["notes"].append(note)
        diag["per_link"] = []
        for link in links:
            rec = {"name": link.name, "url": link.url, "rss_url": link.rss_url,
                   "safe": None, "entries": 0, "status": "", "reason": ""}
            if not _safe_url(link.rss_url):
                reason = _safe_url_fail_reason(link.rss_url)
                print(f"[FEED AGG] 跳过友链「{link.name}」：RSS 地址未通过安全校验（{reason}）")
                diag["skipped"] += 1
                diag["notes"].append(f"跳过友链「{link.name}」：RSS 地址未过安全校验（{reason}）")
                rec["safe"] = False
                rec["reason"] = reason
                rec["status"] = "skipped"
                diag["per_link"].append(rec)
                continue
            rec["safe"] = True
            try:
                import feedparser
                parsed = feedparser.parse(link.rss_url)
            except ImportError:
                print("[FEED AGG] feedparser 未安装！请在服务器上执行: pip install feedparser==6.0.11 后重启服务")
                diag["feedparser_ok"] = False
                diag["notes"].append("feedparser 未安装：pip install feedparser==6.0.11 后重启服务")
                rec["status"] = "error"
                rec["reason"] = "feedparser 未安装"
                diag["per_link"].append(rec)
                break
            except Exception as e:
                # 抓取/解析失败跳过该源，不影响其它源
                print(f"[FEED AGG] 抓取友链「{link.name}」RSS 失败: {type(e).__name__}: {e}")
                diag["skipped"] += 1
                diag["notes"].append(f"抓取友链「{link.name}」RSS 失败：{type(e).__name__}: {e}")
                rec["status"] = "error"
                rec["reason"] = f"{type(e).__name__}: {e}"
                diag["per_link"].append(rec)
                continue
            entries = parsed.entries or []
            rec["entries"] = len(entries)
            if not entries:
                bozo = getattr(parsed, "bozo", 0)
                print(f"[FEED AGG] 友链「{link.name}」RSS 解析到 0 条（bozo={bozo}，地址：{link.rss_url}）")
                diag["notes"].append(f"友链「{link.name}」RSS 解析到 0 条（地址：{link.rss_url}）")
                rec["status"] = "empty"
            else:
                rec["status"] = "ok"
            diag["per_link"].append(rec)
            for e in entries[:10]:
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
                    "published_at": fmt_bj(datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc), "%Y-%m-%d %H:%M"),
                    "ts": int(ts),
                })
            diag["fetched"] += 1

        items.sort(key=lambda x: x["ts"], reverse=True)
        items = items[:40]
        _CACHE["items"] = items
        _CACHE["ts"] = now
        # v3.8.6：写回诊断（供 API 返回）
        for k, v in diag.items():
            _LAST_DIAG[k] = v
    finally:
        _sock.setdefaulttimeout(_old_to)
    return items
