# -*- coding: utf-8 -*-
"""读取站点设置（Setting 表）。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""



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


def site_base():
    """站点对外绝对地址前缀（去尾部斜杠）—— **全站唯一真相源**（v3.18.9）。

    优先级：DB `Setting.site_url` → 环境变量 `SITE_URL` → 空串。

    为什么必须收敛到一处：此前 canonical / og:url / sitemap / feed / 邮件链接
    各自取值（有的只读 DB、有的回退 `request.url_root`），接上爬虫通道后直接
    表现为同一篇文章对外有多个不同 URL——SEO 上是硬伤，且 canonical 指向漂移
    会让搜索引擎选错规范页。

    **绝不回退到 `request.url_root` / `request.host`**：那等于让请求方提供
    Host 决定我们对外声明的 URL，攻击者可用 `Host: evil.example.com` 诱导
    生成指向外部域名的 canonical（首轮审计 2.9 遗留项）。未配置时宁可返回
    空串，由调用方拼接出相对路径，并由诊断页红字提示未配置。
    """
    try:
        from flask import current_app
        db_url = get_setting("site_url")
        if db_url:
            return str(db_url).strip().rstrip("/")
        return str(current_app.config.get("SITE_URL") or "").rstrip("/")
    except Exception:
        # 无 app 上下文（CLI / 后台线程）时只读 DB
        db_url = get_setting("site_url")
        if db_url:
            return str(db_url).strip().rstrip("/")
        import os
        return str(os.environ.get("SITE_URL") or "").rstrip("/")


def abs_url(path):
    """把站内相对路径拼成对外绝对 URL（v3.18.9）。

    `site_base()` 为空（未配置）时**原样返回相对路径**，绝不猜测域名。
    传绝对 URL 时原样返回。
    """
    if not path:
        return ""
    p = str(path)
    if p.startswith("http://") or p.startswith("https://"):
        return p
    if not p.startswith("/"):
        p = "/" + p
    base = site_base()
    return (base + p) if base else p
