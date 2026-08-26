"""小工具函数。"""
import re
import time
import hmac
import hashlib
import secrets

import bleach
from markdown import markdown
from markupsafe import Markup


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
    s = s.replace("</", "<\\/")
    return s


# ---------- HTML 清理（防 XSS）----------
# 文章/关于页的 Markdown 渲染结果会直接 innerHTML/v-html 进页面，
# 必须经过白名单清理，剥离 <script>、on* 事件属性、javascript: 等危险内容。
_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "img", "hr", "span", "del",
}
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
    "*": ["class"],
}


def clean_html(html):
    """白名单清理 HTML，去除脚本与危险属性。"""
    cleaned = bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    # 图片懒加载（v2.8.0）：给正文图片统一加 loading="lazy"，首屏外图片延迟加载省流量。
    # 用正则补属性，避免污染 bleach 白名单（loading 非标准白名单属性会被剥离）。
    if "<img" in cleaned:
        cleaned = re.sub(
            r"<img(?![^>]*\bloading=)",
            '<img loading="lazy"',
            cleaned,
        )
    return cleaned


def render_markdown(content):
    """把 Markdown 渲染为 HTML 并清理（统一出口，避免 XSS）。"""
    raw = markdown(content or "", extensions=["fenced_code", "tables"])
    return clean_html(raw)


# ---------- 安全重定向（防开放重定向）----------
def safe_redirect(target, default="/"):
    """仅允许站内相对路径跳转；以 // 开头的协议相对路径会被拒绝。"""
    if not target:
        return default
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


# ---------- 限流（Redis 全局 / 内存回退）----------
# 单进程内有效；多 worker 部署下作为纵深防御，不替代专业限流组件。
# v3.1.6（高优）：配置 REDIS_URL 后改用 Redis 滑动窗口计数（多 worker 全局一致），
# 未配置自动回退内存计数（单进程）。Redis 连接异常时静默回退内存，不影响主流程。
_RATE = {}
_REDIS_KEY_PREFIX = "blog:rl:"


def _redis():
    """按需创建 Redis 客户端（懒加载，失败返回 None）。"""
    try:
        from flask import current_app
        import redis as _redis_mod
        url = current_app.config.get("REDIS_URL", "")
        if not url:
            return None
        return _redis_mod.from_url(url, socket_connect_timeout=2, socket_timeout=2,
                                   decode_responses=True)
    except Exception:
        return None


def rate_limit(key, limit=20, window=60):
    """返回 True 表示允许；超出则 False。key 通常含 IP。

    Redis 模式：用 INCR + EXPIRE 做固定窗口计数（首请求建键，超限返回 False）。
    内存模式：滑动窗口时间戳列表（旧逻辑）。
    """
    now = time.time()
    r = _redis()
    if r is not None:
        try:
            rk = _REDIS_KEY_PREFIX + str(key)
            # 固定窗口：计数 + 过期（窗口长度秒）。首请求 INCR=1 后设一次过期。
            c = r.incr(rk)
            if c == 1:
                r.expire(rk, window)
            return int(c) <= limit
        except Exception:
            pass  # Redis 异常回退内存
    hits = _RATE.get(key, [])
    hits = [t for t in hits if now - t < window]
    if len(hits) >= limit:
        _RATE[key] = hits
        return False
    hits.append(now)
    _RATE[key] = hits
    return True


def client_key(prefix):
    """基于客户端真实 IP 生成限流 key（服务端统一收口，防伪造 XFF 绕过限流）。"""
    from flask import request
    ip = request.remote_addr or "unknown"
    xff = request.headers.get("X-Forwarded-For", "")
    cand = xff.split(",")[0].strip() if xff else ""
    # 与 stats.client_ip 同口径：仅接受合法公网 XFF 首段，否则用 TCP 直连地址
    try:
        import ipaddress as _ipa
        if cand and not _ipa.ip_address(cand).is_private and \
                not _ipa.ip_address(cand).is_loopback and \
                not _ipa.ip_address(cand).is_link_local and \
                not _ipa.ip_address(cand).is_reserved and \
                _ipa.ip_address(cand).is_global:
            ip = cand
    except Exception:
        pass
    return f"{prefix}:{ip}"


def make_slug(text):
    """把标题转成网址短名（slug）。
    保留中英文、数字和下划线，其它字符替换为减号。
    例如：'我的第一篇文章！' -> '我的第一篇文章'
    """
    s = re.sub(r"[^\w一-鿿]+", "-", (text or "").strip()).strip("-")
    return s or "post"


# v3.5.2：链接后缀全局模板支持的占位符与其取值来源。
# 仅这些键可作为 {xxx} 占位符；其余字面量原样保留（经 make_slug 清洗）。
SLUG_TEMPLATE_TOKENS = ("slug", "id", "date", "category")

# 预制模板（key -> 模板串）。key 同时作为 Setting.slug_mode 的取值。
# 顺序即下拉展示顺序；"title" 为默认（与旧行为一致）。
SLUG_PRESETS = {
    "title": "{slug}",          # 仅标题短名（旧默认行为）
    "slug-date": "{slug}-{date}",
    "id": "post-{id}",
    "date-slug": "{date}-{slug}",
    "category-slug": "{category}-{slug}",
}


def render_slug_template(template, *, slug, post_id=None, date=None, category=None):
    """把模板串里的 {slug}/{id}/{date}/{category} 替换成对应值，再整体清洗为合法 slug。

    - 各占位符单独经 make_slug 清洗（中英文/数字/下划线，其它转连字符）；
      空缺（如未选分类、date 为 None）则用空串，避免生成 'None' 这种脏串。
    - 字面量（模板里的固定文字）也随整体 make_slug 处理，保证最终仅含合法 slug 字符。
    - 返回清洗后的串；若清洗后为空则返回 None（调用方回退）。
    """
    def piece(token):
        val = {
            "slug": slug,
            "id": str(post_id) if post_id is not None else "",
            "date": (date or ""),
            "category": (category or ""),
        }.get(token, "")
        return make_slug(val) if val else ""

    rendered = template
    # 依次替换已知占位符（顺序无关，因互不嵌套）
    for tok in SLUG_TEMPLATE_TOKENS:
        rendered = rendered.replace("{" + tok + "}", piece(tok))
    # 去掉未识别的 {xxx}
    rendered = re.sub(r"\{[^}]*\}", "", rendered)
    return make_slug(rendered) or None


def apply_slug_template(post, title):
    """按全局 Setting 的 slug_mode / slug_template 生成 base slug。

    调用时机：新建或编辑文章、且用户未手动填单篇 slug 覆盖时。
    - mode='title'（默认）：等价于旧行为 unique_slug(title)。
    - 其它预制/自定义：用 render_slug_template 拼装后，用 unique_slug 做唯一化
      （冲突追加 -2/-3，绝不写出重复 slug 触发路由冲突）。
    返回最终 slug 字符串。
    """
    mode = (get_setting("slug_mode", "title") or "title").strip()
    if mode == "title":
        return _unique_slug_local(title, post.id)
    if mode == "custom":
        template = get_setting("slug_template", "") or ""
    else:
        template = SLUG_PRESETS.get(mode, SLUG_PRESETS["title"])
    if not template:
        return _unique_slug_local(title, post.id)
    # 取分类短名（有分类则取 category.slug，否则取空）
    category_slug = ""
    if getattr(post, "category", None) is not None:
        category_slug = post.category.slug or ""
    date_str = ""
    ca = getattr(post, "created_at", None)
    if ca is not None:
        date_str = ca.strftime("%Y%m%d")
    base = render_slug_template(
        template,
        slug=make_slug(title),
        post_id=post.id,
        date=date_str,
        category=category_slug,
    )
    if not base:
        return _unique_slug_local(title, post.id)
    return _unique_slug_local(base, post.id)


def _unique_slug_local(base, post_id=None):
    """本地唯一化 slug（避免 utils 顶层反向导入 admin 造成循环）。

    与 admin.unique_slug 逻辑一致：base 冲突（排除自身）时追加 -2/-3。
    """
    from models import Post  # 延迟导入，规避循环依赖

    slug = make_slug(base) or "post"
    i = 2
    while True:
        q = Post.query.filter_by(slug=slug)
        if post_id:
            q = q.filter(Post.id != post_id)
        if not q.first():
            break
        slug = f"{make_slug(base)}-{i}"
        i += 1
    return slug




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


def get_setting(key, default=None):
    """读取站点设置（Setting 表键值对）。返回字符串；不存在返回 default。
    用于后台可动态调整的开关（如评论审核），优先级高于环境变量默认值。
    """
    try:
        from models import Setting
        s = Setting.query.filter_by(key=key).first()
        return s.value if s and s.value is not None else default
    except Exception:
        return default


def setting_bool(key, default=False):
    """读取布尔型站点设置（'true'/'1'/'yes' 视为真）。"""
    v = get_setting(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("true", "1", "yes", "on")


# ---------- 弱密码黑名单 + 复杂度校验（v3.1.6 中优）----------
# 常见弱口令黑名单：直接命中拒绝；变体（如 123456a / password123）靠复杂度规则兜底。
_WEAK_PASSWORDS = {
    "123456", "123456789", "12345678", "1234567", "123123", "111111",
    "000000", "666666", "888888", "password", "passw0rd", "qwerty",
    "qwerty123", "abc123", "abc123456", "123qwe", "qwe123", "123abc",
    "admin123", "admin888", "admin666", "root123", "password1",
    "qq123456", "a123456", "woaini1314", "iloveyou", "1qaz2wsx",
    "zxcvbnm", "asdfgh", "5201314", "aa123456", "a12345678", "pp123456",
}
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")


def validate_password(raw, min_len=8, strong=None, mixed_case=None):
    """校验密码强度。返回 (ok, 错误信息)。

    - 基础：长度 >= min_len（默认 8）
    - strong=True（默认，可用环境变量 STRONG_PASSWORD 关闭）：至少含字母 + 数字；
      且不在弱密码黑名单（大小写不敏感比较）
    - mixed_case=True（STRONG_PASSWORD_MIXED_CASE）：再要求同时含大写与小写字母
    - 以上开关均可在 config 配置，此处默认按最严格（调用方可传入 config 值覆盖）
    """
    pwd = raw or ""
    if len(pwd) < min_len:
        return False, f"密码至少 {min_len} 位"
    if strong is None:
        strong = True
    if mixed_case is None:
        mixed_case = False
    if strong:
        if pwd.strip().lower() in _WEAK_PASSWORDS:
            return False, "该密码过于常见，请换一个更复杂的密码"
        if not (_LOWER_RE.search(pwd) or _UPPER_RE.search(pwd)) or not _DIGIT_RE.search(pwd):
            return False, "密码需同时包含字母和数字"
        if mixed_case and (_LOWER_RE.search(pwd) is None or _UPPER_RE.search(pwd) is None):
            return False, "密码需同时包含大写和小写字母"
    return True, ""


# ---------- CSRF Token 双因子防护（v3.1.6 中优）----------
# 在既有 SameSite=Lax + Origin 同源校验之上，增加「会话绑定的一次性 CSRF Token」：
#   每个登录会话生成 token（哈希型，HMAC(SECRET_KEY, session_id+user_id)），
#   写进 session 并在模板里注入 <input type="hidden" name="csrf_token">；
#   POST 请求校验表单字段或请求体 csrf_token 必须与会话 token 一致（恒定时间比较）。
# 前端（Vue SPA）通过 /api/auth/me 响应头拿到 token，后续 POST 自动带 X-CSRF-Token。


def generate_csrf_token():
    """生成本会话的 CSRF Token（惰性，无则创建）。返回 (token, 是否新建)。

    v3.4.6 修复（多 worker 下 token 反复轮换 → 前端 403「抽风」）：
    旧实现用进程级 _CSRF_CACHE 判断 token 是否「新鲜」，但 gunicorn 多 worker 时
    每个 worker 各自持有一份缓存，落到不同 worker 的请求会认为「缓存里没有当前
    token」从而重新生成并覆盖 session 里的 token，导致前端缓存的 token 失效 → 403。
    改为：只要 session 中已有**签名有效**的 token 就直接复用（签名由本服务
    SECRET_KEY 经 HMAC 生成，天然防伪造/防跨服务复用），token 在整段会话内保持稳定，
    不再随 worker 切换而轮换。仅当 token 缺失或签名失效（被篡改/SECRET_KEY 已轮换）
    时才重新生成。
    """
    from flask import session
    tok = session.get("csrf_token")
    if tok:
        # 复用既有 token，但先校验签名仍有效（防 session 被篡改或跨服务伪造）
        parts = str(tok).split(".")
        if len(parts) == 2 and hmac.compare_digest(_sign_csrf(parts[0]), parts[1]):
            return tok, False
        # 既有 token 签名无效 → 重新生成（不沿用被污染的值）
    raw = secrets.token_hex(24)
    # 会话绑定：token 本身存 session；签名部分用于校验 token 确由本服务签发
    tok = raw + "." + _sign_csrf(raw)
    session["csrf_token"] = tok
    return tok, True


def _sign_csrf(raw):
    """HMAC(SECRET_KEY, 'csrf:' + raw) 生成校验签名。"""
    from flask import current_app
    key = (current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    return hmac.new(key, ("csrf:" + raw).encode("utf-8"), hashlib.sha256).hexdigest()


def check_csrf_token(tok):
    """校验提交的 CSRF Token 是否等于会话 token（恒定时间比较）。返回 True/False。

    双重校验：
    1. 签名有效性：token 的签名部分必须由本服务 SECRET_KEY 生成（防伪造任意 token）；
    2. 与会话一致：提交的 token 必须等于当前会话里存的 token。
    """
    from flask import session
    session_tok = session.get("csrf_token") or ""
    if not tok or not session_tok:
        return False
    parts = str(tok).split(".")
    if len(parts) != 2:
        return False
    raw, sig = parts
    expect = _sign_csrf(raw)
    if not hmac.compare_digest(sig, expect):
        return False
    return hmac.compare_digest(str(tok), session_tok)


def csrf_input():
    """渲染隐藏域用（模板里写 {{ csrf_input() }}）。

    必须返回 Markup（安全 HTML）：Jinja2 默认 autoescape，若返回普通字符串，
    <input> 会被转义成 &lt;input&gt;，导致登录后台页面直接显示这段源码（乱码）。
    """
    tok, _ = generate_csrf_token()
    return Markup(f'<input type="hidden" name="csrf_token" value="{tok}">')


def notify_mentioned(content, link, from_author, post_id=None):
    """解析评论/动态内容里的 @username，给被提及的注册用户生成站内通知。
    - content: 评论原文；link: 点击通知跳转地址；from_author: 提及者昵称（文案用）
    - 仅给存在的注册用户发通知，不重复，自己@自己不发
    """
    try:
        from models import db, User, Notification
        names = set(re.findall(r"@([A-Za-z0-9_\u4e00-\u9fa5]{2,40})", content or ""))
        if not names:
            return
        for name in names:
            u = User.query.filter_by(username=name).first()
            if u and u.username != from_author:
                db.session.add(Notification(
                    user_id=u.id,
                    content=f"{from_author} 在评论中提到了你：{(content or '')[:80]}",
                    link=link or "",
                ))
        db.session.commit()
    except Exception:
        pass  # 通知失败不影响评论主流程
