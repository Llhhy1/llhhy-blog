# -*- coding: utf-8 -*-
"""SEO 爬虫通道闸门（v3.18.9）。

**为什么需要独立于 `detect_bot()`**（v3.18.9 实测结论，别重新发现一遍）：

1. `detect_bot()` **认不出微信**。实测 `detect_bot("…MicroMessenger/8.0.40")`
   返回 `(False, "", "")` —— 微信 UA 里根本没有 bot/spider/crawler 字样。
   任何拿 `detect_bot(...)[2] == "search"` 当闸门的做法，微信卡片必然失效。
2. `detect_bot()` 把**社交抓取器**（facebookexternalhit/TelegramBot 等）与
   **Ahrefs/Semrush/curl 等工具**混在同一个 `tool` 类里。所以既不能只放行
   `search`（微信失效），也不能整体放行 `tool`（等于给第三方 SEO 蜘蛛送全文入口）。
3. 反方向更危险：**QQ 内置浏览器里的真人** UA 常带 `QQ/9.7.x`
   （如 `…MQQBrowser/13.0 QQ/9.7.10.43400…`）。**纯 UA 分流一定会误伤真人**，
   而真人看到一张几乎空白的壳页，比爬虫少抓一次严重得多。

因此本模块的闸门是**两层**：
- 第一层（放行候选）：搜索引擎 UA ∨ 社交/IM 预览抓取器 UA。
- 第二层（真人否决）：只要出现**真人信号**就一律否决，即使第一层命中。
  真人信号 = `Sec-Fetch-Mode: navigate`（现代浏览器导航必送）或
              `Accept` 含 `text/html`（浏览器文档请求必送；抓取器一般不送）。
- 另有**来源否决**：站内 Referer（站内跳转一定是真人在站内点链接，不是抓取器）。

判定结果只用于「能否把服务端壳页给出去」。UA 完全可以伪造，所以调用方
**必须**只输出公开内容（走 `visible_posts_query()`），见 `api/og.py`。
"""
import re

# --- 第一层：搜索引擎爬虫（与 detect_bot 的 search 类保持一致，避免两套语义漂移）---
SEARCH_BOT_UA = re.compile(
    r"googlebot|bingbot|baiduspider|sogou|360spider|yandex|duckduckbot"
    r"|bytespider|applebot|qwantbot|petalbot|naver|seznambot"
    r"|yisouspider|google-inspectiontool|shenmaspider|toutiaospider",
    re.I,
)

# --- 第一层：社交 / IM 的链接预览抓取器 ---
# 这些 UA 里通常**不含** bot/spider/crawler 字样，detect_bot 也识别不出，必须单列。
# ⚠️ 绝对不要加 `QQBrowser` / `MQQBrowser` —— 那是 QQ 内置浏览器里的真人，会执行 JS。
_SOCIAL_PREVIEW_UA = re.compile(
    r"micromessenger|weixin|qq/|qqtool|weibo"
    r"|twitterbot|facebookexternalhit|facebot|telegrambot|linkedinbot"
    r"|slackbot|whatsapp|skypeuripreview|discordbot|embedly|pinterest"
    r"|line-poker|vkshare|w3c_validator|outbrain|nuzzel|bitlybot",
    re.I,
)

# 真人信号：现代浏览器发起的「顶级导航」请求必带。抓取器通常不带。
_NAV_FETCH_MODES = ("navigate",)

# 明确不给通道的「第三方 SEO 蜘蛛 / 脚本客户端」——它们能索引即可，
# 不该被当成「社交预览」享受壳页；且给它们壳页等于提供批量抓取入口。
_TOOL_BOT_UA = re.compile(
    r"ahrefsbot|semrushbot|mj12bot|dotbot|dataforseo|blexbot|serpstatbot"
    r"|python-requests|python-urllib|aiohttp|httpx|axios|curl/|wget"
    r"|go-http-client|java/|okhttp|scrapy|libwww-perl|httpclient",
    re.I,
)


def _header(name):
    """安全读取请求头（无请求上下文时返回空串，便于纯函数测试）。"""
    try:
        from flask import request
        return request.headers.get(name, "") or ""
    except Exception:
        return ""


def is_human_navigation():
    """是否存在**真人导航信号**（第二层否决的依据）。

    - `Sec-Fetch-Mode: navigate`：Chrome/Edge/Safari 等现代浏览器发起页面导航时必送。
      微信/QQ 内置浏览器（X5/系统 WebView）同样会送。
    - `Accept` 含 `text/html`：浏览器文档请求必送；纯抓取器（curl/爬虫库）一般只送 `*/*`。
    - `Sec-Fetch-Dest: document`：与 navigate 同源的另一个强信号。

    任一命中即认定为真人 → 通道必须放他回 SPA。
    """
    mode = _header("Sec-Fetch-Mode").strip().lower()
    if mode in _NAV_FETCH_MODES:
        return True
    if _header("Sec-Fetch-Dest").strip().lower() == "document":
        return True
    accept = _header("Accept").lower()
    if "text/html" in accept:
        # ⚠️ 这一条会把「curl -H 'Accept: text/html'」也判成真人，宁可错杀：
        # 误判成真人的代价 = 爬虫拿不到壳页（少收录一篇）；
        # 误判成爬虫的代价 = 真人在微信里看到空白页（生产事故）。两者不对称。
        return True
    return False


def is_internal_referer():
    """Referer 指向本站 → 是站内跳转的真人（不是外部抓取器）。

    抓取器一般不带 Referer，或带自己的来源；站内 Referer 说明用户是从站内
    某个页面点进来的，必然要能看到可执行的页面。

    比对基准用 `site_base()`；未配置时退用本次请求的 Host（这里读 Host 是
    **用于「是不是自己家」的判断**，不参与对外 URL 生成，无 Host 注入风险）。
    """
    ref = _header("Referer").strip()
    if not ref:
        return False
    try:
        from urllib.parse import urlparse
        from utils import site_base
        host = urlparse(ref).netloc.lower()
        if not host:
            return False
        base_host = urlparse(site_base() or "").netloc.lower()
        if not base_host:
            try:
                from flask import request
                base_host = (request.host or "").lower()
            except Exception:
                base_host = ""
        return bool(base_host) and host == base_host
    except Exception:
        return False


def seo_shell_ua():
    """返回 `(allow, reason)` —— 是否允许把服务端壳页给出去。

    allow=True 仅当：命中搜索引擎/社交预览 UA **且** 无真人信号 **且** 非站内 Referer。
    明确排除第三方 SEO 蜘蛛与脚本客户端（Ahrefs/curl 等）。

    reason 仅用于日志/测试断言，不对外暴露。
    """
    ua = _header("User-Agent").strip()
    if not ua:
        return False, "no-ua"

    # 明确的黑名单优先（即便 UA 里同时混了 bot 词也不放行）
    if _TOOL_BOT_UA.search(ua):
        return False, "tool-bot"

    is_search = bool(SEARCH_BOT_UA.search(ua))
    is_social = bool(_SOCIAL_PREVIEW_UA.search(ua))
    if not (is_search or is_social):
        return False, "not-crawler"

    # ===== 第二层：真人否决（必须在 UA 命中之后判，否则真人 UA 不会走到这里）=====
    if is_human_navigation():
        return False, "human-navigation"
    if is_internal_referer():
        return False, "internal-referer"

    return True, ("search" if is_search else "social")


def is_search_engine_ua():
    """是否正规搜索引擎（用于**限流豁免**：把 Google/Baidu 的正常抓取 429 掉等于自废收录）。"""
    return bool(SEARCH_BOT_UA.search(_header("User-Agent").strip()))
