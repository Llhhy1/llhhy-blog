"""友链 RSS 聚合：抓取友链站点的 RSS，按时间混排成「博客圈」流。

安全措施：
- SSRF 防护：仅允许 http/https，拦截私有地址（127.0.0.1 / 192.168.* / 10.* / 172.16-31.* / 169.254.*）。
  **R114 审计 加固**：`_safe_url()` 只在抓取**前**校验一次，而 `feedparser.parse(url)`
  会自建 urllib 会话重新解析 DNS **并自动跟随 3xx跳转** —— 于是「首查公网 IP 放行 →
  302 跳内网 / DNS 重绑定」两条绕过都成立。现改为**我们自己用禁重定向的opener 抓取**，
  跳转一律不跟随（重定向响应视为失败），再把字节喂给 feedparser 解析。
- 条目链接协议白名单：**R114 审计** —— RSS 条目的 `<link>` 此前只判空，
  `javascript:...` 会原样进前端 `:href`（存储型 XSS）。现只放行 http/https。
- 外部内容清洗：摘要 HTML 经 bleach 白名单清理，避免 XSS。
- 缓存：聚合结果内存缓存 15 分钟，避免每次请求都抓取（慢且易被限流）。
"""
import io
import time
import urllib.parse
import urllib.request
import urllib.error
import datetime

from models import FriendLink
from utils import clean_html, fmt_bj
# v4.7.4：SSRF 判据与出站机制**全部**收敛到 outbound。
# 此前本模块还自带一份 `_NoRedirect` 和一份私网判断（字符串前缀 + 自己的
# getaddrinfo）—— 与 `games.py` 的实现各说各话，改一处就漂移。
from outbound import (check_public_url, open_url, read_limited,
                      resolve_public_ex, safe_public_url as _safe_url)
import logging

# v3.23.0：print → logger（格式/级别见 logging_setup）
logger = logging.getLogger(__name__)

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


# `_safe_url` / `_is_private_ip` 的实现已抽到 `outbound.py`（上面的 import 保留同名
# 模块属性，不破坏既有调用方与测试）；SSRF 判据只有一份，避免多处口径漂移。

# ---------- R114 审计：禁重定向抓取器（堵 SSRF 绕过）----------
# 为什么不能直接 `feedparser.parse(url)`：它自建 urllib 会话，会**重新解析 DNS**
# （`_safe_url()` 的预检查结果因此失效 → DNS 重绑定）**并自动跟随 3xx**
# （攻击者用公网 302 跳 `http://100.100.100.200/` 元数据或内网服务，
#   跳转变量从不被复检）。所以抓取必须由我们自己发起、且**不跟随任何跳转**。
_FEED_MAX_BYTES = 5 * 1024 * 1024  # 单个 RSS 上限 5MB，防内存打爆


def _fetch_feed_bytes(url, timeout, pinned_ips=None):
    """抓取 RSS 字节：禁重定向 + **固定已校验的 IP** + 限大小。

    失败抛异常，由调用方按「跳过该源」处理。

    v4.7.4：改走 `outbound.open_url()` —— 一次完成
    「校验 → **把已校验过的 IP 固定在连接上** → 禁跟随 3xx」。

    ⚠️ 关键在**固定 IP**：旧实现是「先 `_safe_url()` 校验一次，再把 URL 交给
    urllib 去连」，而 urllib 会**重新解析一次 DNS** —— 两次解析之间 DNS 可被
    改指内网（DNS rebinding），重复校验消除不了这个窗口。
    `open_url` 之后不再解析，DNS 再怎么变都无所谓。
    """
    req_headers = {
        "User-Agent": "llhhy-blog-feed-aggregator/1.0",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    with open_url(url, timeout=timeout, headers=req_headers,
                  pinned_ips=pinned_ips) as resp:
        # 只读 Content-Length 声明的长度做上限控制（不信任，仅用于提前拒绝）
        try:
            declared = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > _FEED_MAX_BYTES:
            raise ValueError("RSS 响应体超过 %d 字节上限" % _FEED_MAX_BYTES)
        data, _truncated = read_limited(resp, _FEED_MAX_BYTES)
        return data


def _safe_item_url(href):
    """RSS **条目**链接的协议白名单（R114 审计）。

    `_safe_url()` 只管 RSS **源地址**的 SSRF，管不到条目里的 `<link>`。
    此前只判空，`javascript:fetch(...)` 会原样进前端 `:href` → 存储型 XSS
    （`target="_blank"` 不阻止 `javascript:` 执行）。这里只放行 http/https。
    """
    try:
        p = urllib.parse.urlparse(href)
    except (ValueError, TypeError):
        # urlparse 对畸形 IPv6 字面量（如 "http://[::1"）抛 ValueError，
        # 非字符串入参抛 TypeError —— 不需要裸 except Exception。
        return ""
    if p.scheme.lower() not in ("http", "https"):
        return ""
    if not p.netloc:
        return ""
    return href


def _safe_url_fail_reason(url):
    """为什么没通过安全校验 —— **只做解释，不参与放行决策**。

    v4.7.4：本函数原先**自己实现了一遍**私网判断（字符串前缀 `10.` / `192.168.` /
    `169.254.` / `172.16-31` + 自己的 `getaddrinfo`），与 `outbound` 的
    「纯 IP global 判据」是两套逻辑 —— 会出现「放行是一套标准、提示语是另一套」。
    现在直接问统一层要原因，判据只有一份。

    ⚠️ 注意它**不再**是「放行判据」：真正的放行由 `_safe_url()`（→ `outbound`）决定。
    """
    _ok, reason = check_public_url(url)
    return reason or "未知原因"


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
        # R114 审计：与 get_circle_feed 同一手法——自己抓（禁重定向+限大小）
        # 再喂 feedparser。`feedparser.parse(url)` 会跟随 302 绕过私网过滤。
        parsed = feedparser.parse(io.BytesIO(_fetch_feed_bytes(url, timeout=timeout)))
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
            logger.info("[FEED AGG] 博客圈聚合：%s", note)
            diag["notes"].append(note)
        diag["per_link"] = []
        for link in links:
            rec = {"name": link.name, "url": link.url, "rss_url": link.rss_url,
                   "safe": None, "entries": 0, "status": "", "reason": ""}
            # v4.7.4：**一次解析**同时拿到「能不能放行」和「用哪个 IP」。
            # 之前是「先 `_safe_url()` 校验一次，再由 urllib 重新解析一次 DNS 去连」——
            # 两次解析之间 DNS 可被改指内网（DNS rebinding），而固定连接必须用
            # **被校验过的那一批 IP**，否则固定的可能是根本没检查过的内网地址。
            _ok, reason, _h, _p, _ips = resolve_public_ex(link.rss_url)
            if not _ok:
                reason = reason or _safe_url_fail_reason(link.rss_url)
                logger.warning("[FEED AGG] 跳过友链「%s」：RSS 地址未通过安全校验（%s）", link.name, reason)
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
                # v3.17.12（审计 R77）：单源抓取加 socket 超时——feedparser.parse 内部走 urllib，
                # 默认无超时；当某个友链 RSS 挂起（慢速响应/黑洞）时，会把整个博客圈聚合请求
                # 连同 gunicorn worker 一起拖住（前台 /api/feed/circle 会卡死）。
                # 与 _probe_rss（上方诊断探针）保持同一手法。
                import socket as _sock_agg
                # ⚠️ 变量名不得复用外层的 `_old_to`：外层在 :174 存了**真实**原值、
                # 本处读到的却是外层刚设进去的 `_timeout`，若覆盖它，函数出口的
                # `finally: _sock.setdefaulttimeout(_old_to)` 就会把进程级默认超时
                # 永久留在 `_timeout` 上（gunicorn worker 里所有后续 socket 一起中招）。
                _old_to_src = _sock_agg.getdefaulttimeout()
                _sock_agg.setdefaulttimeout(12)
                try:
                    # R114 审计：**自己抓**（禁重定向 + 限大小），再把字节喂给 feedparser。
                    # 不再 `feedparser.parse(url)`——那会让它自建会话重新解析 DNS 并跟随 302，
                    # 把上面 `_safe_url()` 的私网过滤整条绕开。
                    _raw = _fetch_feed_bytes(link.rss_url, timeout=12,
                                            pinned_ips=_ips)
                    parsed = feedparser.parse(io.BytesIO(_raw))
                finally:
                    _sock_agg.setdefaulttimeout(_old_to_src)
            except ImportError:
                logger.warning("[FEED AGG] feedparser 未安装！请在服务器上执行: pip install feedparser==6.0.11 后重启服务")
                diag["feedparser_ok"] = False
                diag["notes"].append("feedparser 未安装：pip install feedparser==6.0.11 后重启服务")
                rec["status"] = "error"
                rec["reason"] = "feedparser 未安装"
                diag["per_link"].append(rec)
                break
            except Exception as e:
                # 抓取/解析失败跳过该源，不影响其它源
                logger.warning("[FEED AGG] 抓取友链「%s」RSS 失败: %s: %s", link.name, type(e).__name__, e)
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
                logger.info("[FEED AGG] 友链「%s」RSS 解析到 0 条（bozo=%s，地址：%s）", link.name, bozo, link.rss_url)
                diag["notes"].append(f"友链「{link.name}」RSS 解析到 0 条（地址：{link.rss_url}）")
                rec["status"] = "empty"
            else:
                rec["status"] = "ok"
            diag["per_link"].append(rec)
            for e in entries[:10]:
                title = (e.get("title") or "").strip()
                # R114 审计：条目链接必须过协议白名单。
                # 此前只判空 → `javascript:...` 原样进前端 `:href`（存储型 XSS）。
                href = _safe_item_url((e.get("link") or "").strip())
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
