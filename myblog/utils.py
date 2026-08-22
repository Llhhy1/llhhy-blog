"""小工具函数。"""
import re
import time

import bleach
from markdown import markdown


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


# ---------- 简单内存限流（防爆破/刷接口）----------
# 注：单进程内有效；多 worker 部署下作为纵深防御，不替代专业限流组件。
_RATE = {}


def rate_limit(key, limit=20, window=60):
    """返回 True 表示允许；超出则 False。key 通常含 IP。"""
    now = time.time()
    hits = _RATE.get(key, [])
    hits = [t for t in hits if now - t < window]
    if len(hits) >= limit:
        _RATE[key] = hits
        return False
    hits.append(now)
    _RATE[key] = hits
    return True


def client_key(prefix):
    """基于客户端真实 IP 生成限流 key（Nginx 反代后取 X-Forwarded-For 首段）。"""
    from flask import request
    xff = request.headers.get("X-Forwarded-For", "")
    ip = xff.split(",")[0].strip() if xff else (request.remote_addr or "unknown")
    return f"{prefix}:{ip}"


def make_slug(text):
    """把标题转成网址短名（slug）。
    保留中英文、数字和下划线，其它字符替换为减号。
    例如：'我的第一篇文章！' -> '我的第一篇文章'
    """
    s = re.sub(r"[^\w一-鿿]+", "-", (text or "").strip()).strip("-")
    return s or "post"


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
