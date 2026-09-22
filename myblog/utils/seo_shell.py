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
- 第二层（真人否决）：**按桶区分作用域**（v3.19.1 修正，别再把两者混用）：
  * `Sec-Fetch-Mode: navigate` / `Sec-Fetch-Dest: document`：浏览器专有头，
    搜索引擎不送 → **两类桶都否决**。
  * `Accept` 含 `text/html`：**搜索引擎正常也会送**（Googlebot 就送），
    所以**只对社交桶否决**；对搜索引擎用它否决会与 nginx 的 UA 粗筛组成 302 环。
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
# （`seo_shell_ua()` 里这条判定最优先，即便 UA 同时混了 bot 词也不放行。）
_TOOL_BOT_UA = re.compile(
    r"ahrefsbot|semrushbot|mj12bot|dotbot|dataforseo|blexbot|serpstatbot"
    r"|python-requests|python-urllib|aiohttp|httpx|axios|curl/|wget"
    r"|go-http-client|java/|okhttp|scrapy|libwww-perl|httpclient",
    re.I,
)

# 真人否决的**原因集合**——单一真相源。
# 调用方据此分流处置（见 `api/og.py` 出口 3b）：
#   * 在集合内（真人）→ 给**可读的 noindex 页**（人需要看到内容）
#   * 不在集合内（tool-bot / not-crawler / no-ua）→ **不给正文**
# 两类都不得 3xx（经通道 3xx = nginx 再 rewrite = 302 环）。
HUMAN_VETO_REASONS = frozenset({
    "human-fetch-metadata", "human-accept", "internal-referer",
})


def _header(name):
    """安全读取请求头（无请求上下文时返回空串，便于纯函数测试）。"""
    try:
        from flask import request
        return request.headers.get(name, "") or ""
    except Exception:
        return ""


def has_fetch_metadata_signal():
    """**浏览器专有**的 Fetch Metadata 头 → 真人导航信号。

    `Sec-Fetch-Mode: navigate` / `Sec-Fetch-Dest: document` 是现代浏览器发起
    页面导航时必送的头，**搜索引擎抓取器一律不送**。因此它对两类桶都是可靠否决依据。
    """
    mode = _header("Sec-Fetch-Mode").strip().lower()
    if mode in _NAV_FETCH_MODES:
        return True
    return _header("Sec-Fetch-Dest").strip().lower() == "document"


def has_html_accept():
    """`Accept` 含 `text/html`。

    ⚠️ **搜索引擎抓取器正常也会送这个头**（Googlebot 送
    `text/html,application/xhtml+xml,…`），所以它**只能对社交桶作否决依据**，
    绝不能用来否决搜索引擎——见 `seo_shell_ua()` 里那段说明。
    """
    return "text/html" in _header("Accept").lower()


def is_human_navigation():
    """是否存在**任一**真人导航信号（两个信号的并集）。

    ⚠️ **不要拿这个函数当单一闸门**：它把 `Accept: text/html` 也算作真人信号，
    而搜索引擎抓取器会送该头。给搜索引擎套用它 = 与 nginx 的 UA 粗筛组成 302 环。
    正确用法见 `seo_shell_ua()`——按桶区分作用域。
    """
    return has_fetch_metadata_signal() or has_html_accept()


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
    #
    # ⚠️ **两个信号的否决作用域必须分开**（v3.19.1 修复的线上事故）：
    #
    # v3.19.0 把「任一真人信号」无差别地套在两类桶上。结果与 nginx 的 UA 粗筛
    # 组成一个 302 环：nginx 只按 UA rewrite（看不到请求头），后端却因
    # `Accept: text/html` 否决 → 302 回 /post/<slug> → nginx 又按同一个 UA
    # rewrite → 无限循环。线上实测：Googlebot / Baiduspider / QQ 内置浏览器真人
    # **三者都在 12 次重定向后仍是 302**——搜索引擎彻底抓不到正文（收录归零），
    # QQ 用户看到 `ERR_TOO_MANY_REDIRECTS`。
    #
    # 根因是把「社交桶的歧义」外推到了搜索引擎：社交桶（尤其 QQ/微信内置浏览器）
    # 的 UA 与自家抓取器**无法用 UA 区分**，才需要 `Accept` 来兜；而
    # **搜索引擎的 UA 是自证的**（`Baiduspider` 不会是浏览器），抓取器送
    # `Accept: text/html` 属正常行为，不该否决。
    if has_fetch_metadata_signal():
        # Sec-Fetch-* 是浏览器专有头，搜索引擎不送 → 两类桶都否决
        return False, "human-fetch-metadata"
    if is_social and has_html_accept():
        # Accept 只对社交桶否决（搜索引擎送它是正常的）
        return False, "human-accept"
    if is_internal_referer():
        return False, "internal-referer"

    return True, ("search" if is_search else "social")


def is_search_engine_ua():
    """是否正规搜索引擎（用于**限流豁免**：把 Google/Baidu 的正常抓取 429 掉等于自废收录）。"""
    return bool(SEARCH_BOT_UA.search(_header("User-Agent").strip()))
