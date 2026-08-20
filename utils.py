"""小工具函数。"""
import re


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
