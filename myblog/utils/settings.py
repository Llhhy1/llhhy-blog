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


_TRUE = ("true", "1", "yes", "on")


def flag_bool(key, config_key="", default=False):
    """**运营开关**取值：`Setting` 表 → `app.config`（环境变量派生）→ `default`。

    v3.25.8 新增。三层各司其职，缺一层都会坑人：

    1. **`Setting` 表优先** —— 后台能改、**改完不用重启**（本项目既定语义，
       同 `site_base()`）。这是「运营开关该进后台」的前提。
    2. **`app.config` 兜底** —— 老部署把值写在环境变量里，不能因为改了优先级
       就让它们的登录/注册行为突然变样（env 里的值仍然被 `config.py` 读成
       config 属性，行为与改动前完全一致）。
    3. **`default` 兜底** —— 全新部署。

    ⚠️ **不要用它读「每请求都要判断」的高频参数**（会话超时、`COOKIE_SECURE`、
    `TRUSTED_PROXIES` …）—— 那是拿一次 DB 查询换一行配置，判据是
    「运营会不会频繁改」×「读取频率」，两者都高的才适合进 Setting。
    本项目里唯一的例外是 `enforce_twofa`（`before_request`），
    因为 2FA 总闸门一旦不能用就是**安全功能形同虚设**，宁可多一次单行查询
    （SQLite 主键命中，微秒级；个人博客量级无压力）。

    ⚠️ `key` 与 `config_key` **不是同一个名字**（`twofa_enabled` vs
    `TWOFA_ENABLED`），因为 `config.py` 会把 `BLOG_TWOFA_ENABLED` 改名成
    `TWOFA_ENABLED`。两个都传，别指望只传一个。
    """
    v = get_setting(key)
    if v is not None and str(v).strip() != "":
        return str(v).strip().lower() in _TRUE
    if config_key:
        try:
            from flask import current_app
            c = current_app.config.get(config_key)
        except Exception:
            c = None
        if c is not None:
            return bool(c)
    return default


def flag_num(key, config_key="", default=0, cast=float):
    """`flag_bool` 的数值版（`LOGIN_DELAY_SECONDS` / `AUDIT_LOG_DAYS` 这类）。

    **DB 里的值非法时当作「没设」继续往下走**（env → default），而不是直接
    回落 `default` —— 因为页面显示的「来源」标签走的是同一个函数：若非法值
    直接回落 default，页面会显示「来源：数据库」而实际生效的是 default，
    **标签与行为不一致**。继续往下走则两者天然一致（页面显示「环境变量」）。
    """
    v = get_setting(key)
    if v is not None and str(v).strip() != "":
        try:
            return cast(v)
        except (TypeError, ValueError):
            pass                      # 非法 → 视同未设，继续下一层
    if config_key:
        try:
            from flask import current_app
            c = current_app.config.get(config_key)
        except Exception:
            c = None
        if c is not None:
            try:
                return cast(c)
            except (TypeError, ValueError):
                return default
    return default


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
