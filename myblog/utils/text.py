# -*- coding: utf-8 -*-
"""文本工具：JS 转义、字数统计、UA 设备解析、爬虫识别。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re



def js_escape(raw):
    """把字符串放进 JS 单引号字符串上下文时使用的转义（防 JS 注入）。

    用于模板里 `onsubmit="return confirm('...{{ js_escape(v) }}...')"` 这类
    **JS 字符串属性**插值。Jinja 在 HTML 属性上下文的 autoescape 不转义单引号，
    用户可控值（username/email/备份文件名等）含 `'` 或 `</script>` 会逃出字符串
    执行任意 JS（存储型 XSS，后台浏览即触发）。本函数转义反斜杠、单引号、
    换行与 `</script>` 闭合，保证安全。
    """
    if raw is None:
        return ""
    s = str(raw)
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    # 防 </script> 提前闭合内联脚本块（HTML 解析在 JS 转义之前发生）
    return s.replace("</", "<\\/")




def count_words(content):
    """粗略统计正文字数（v3.0.0 功能12）。

    规则：中文字符每个算 1 字；连续的英文字母/数字按「词」计数（空格分隔），
    每个词算 1 字；标点/空白不计。无依赖、纯正则，足够用于阅读时长估算。
    返回 (字数, 预计阅读分钟数（按 300 字/分钟，最小 1 分钟）)。
    """
    text = (content or "").strip()
    if not text:
        return 0, 0
    # 中文字符数
    cjk = len(re.findall(r"[一-鿿]", text))
    # 非中文的「词」（英文/数字连续串）数
    words = re.findall(r"[A-Za-z0-9]+", text)
    total = cjk + len(words)
    minutes = max(1, round(total / 300))
    return total, minutes


def parse_device(ua):
    """从 User-Agent 解析设备信息，返回如「手机 · Android · Chrome」。"""
    ua = ua or ""
    u = ua.lower()

    # 设备类型
    if "ipad" in u:
        device = "平板"
    elif "mobile" in u or "android" in u or "iphone" in u or "ipod" in u:
        device = "手机"
    elif "bot" in u or "spider" in u or "crawler" in u:
        device = "爬虫"
    else:
        device = "电脑"

    # 操作系统
    if "windows" in u:
        os_name = "Windows"
    elif "android" in u:
        os_name = "Android"
    elif "iphone" in u or "ipad" in u or "ios" in u:
        os_name = "iOS"
    elif "mac os" in u or "macintosh" in u:
        os_name = "macOS"
    elif "linux" in u:
        os_name = "Linux"
    else:
        os_name = "未知系统"

    # 浏览器 / 应用
    if "micromessenger" in u or "wechat" in u:
        browser = "微信"
    elif "edg/" in u or "edge" in u:
        browser = "Edge"
    elif "chrome" in u and "chromium" not in u:
        browser = "Chrome"
    elif "firefox" in u:
        browser = "Firefox"
    elif "safari" in u and "chrome" not in u:
        browser = "Safari"
    elif "qq/" in u or "qqbrowser" in u:
        browser = "QQ浏览器"
    else:
        browser = "其他"

    return f"{device} · {os_name} · {browser}"


def detect_bot(ua):
    """从 User-Agent 识别爬虫 / Bot，返回 (is_bot, bot_name, bot_category)。

    bot_category 取值：
      - "search" : 搜索引擎爬虫（Google/Bing/Baidu/Sogou/360/Yandex/DuckDuckGo/字节搜索/Apple/Petal 等）
      - "ai"     : AI / LLM 爬虫（GPTBot/CCBot/ClaudeBot/Google-Extended/PerplexityBot/Anthropic/Meta/Cohere 等）
      - "tool"   : 工具 / SEO 类 bot（Ahrefs/Semrush/MJ12/DotBot/python-requests/curl/Scrapy 及社交抓取等）
      - "unknown": 含 bot/spider/crawler 但没匹配到具体名称的未知爬虫
      - ""       : 非 bot（真人浏览器）
    分类优先级：ai > search > tool > 兜底，避免多重命名词义冲突。
    """
    ua = (ua or "").lower()
    if not ua:
        return (False, "", "")

    # AI / LLM 爬虫（优先，避免与搜索引擎混淆）
    ai_rules = [
        ("gptbot", "GPTBot"),
        ("ccbot", "CCBot"),
        ("claudebot", "ClaudeBot"),
        ("google-extended", "Google-Extended"),
        ("perplexitybot", "PerplexityBot"),
        ("anthropic", "AnthropicBot"),
        ("meta-external", "MetaBot"),
        ("cohere", "CohereBot"),
        ("chatgpt-user", "ChatGPT-User"),
        ("oai-searchbot", "OAI-SearchBot"),
    ]
    # 搜索引擎爬虫
    search_rules = [
        ("googlebot", "Googlebot"),
        ("bingbot", "Bingbot"),
        ("baiduspider", "Baiduspider"),
        ("sogou", "Sogou"),
        ("360spider", "360Spider"),
        ("yandex", "YandexBot"),
        ("duckduckbot", "DuckDuckBot"),
        ("bytespider", "Bytespider"),
        ("applebot", "Applebot"),
        ("qwantbot", "QwantBot"),
        ("petalbot", "PetalBot"),
        ("naver", "NaverBot"),
        ("seznambot", "SeznamBot"),
    ]
    # 工具 / SEO / 脚本 / 社交预览类
    tool_rules = [
        ("ahrefsbot", "AhrefsBot"),
        ("semrushbot", "SemrushBot"),
        ("mj12bot", "MJ12Bot"),
        ("dotbot", "DotBot"),
        ("dataforseo", "DataForSeoBot"),
        ("python-requests", "python-requests"),
        ("axios", "axios"),
        ("curl/", "curl"),
        ("go-http-client", "go-http-client"),
        ("java/", "Java"),
        ("okhttp", "OkHttp"),
        ("scrapy", "Scrapy"),
        ("feedfetcher", "FeedFetcher"),
        ("facebookexternalhit", "FacebookBot"),
        ("whatsapp", "WhatsAppBot"),
        ("telegrambot", "TelegramBot"),
        ("twitterbot", "TwitterBot"),
    ]

    for key, name in ai_rules:
        if key in ua:
            return (True, name, "ai")
    for key, name in search_rules:
        if key in ua:
            return (True, name, "search")
    for key, name in tool_rules:
        if key in ua:
            return (True, name, "tool")
    if "bot" in ua or "spider" in ua or "crawler" in ua or "crawl" in ua:
        return (True, "未知爬虫", "unknown")
    return (False, "", "")
