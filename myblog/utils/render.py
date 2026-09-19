# -*- coding: utf-8 -*-
"""Markdown 渲染与 HTML 白名单清洗（含正文渲染缓存与指纹）。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re
import hashlib
import bleach
from markdown import markdown
import os

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


def _upgrade_img_avif(html):
    """v3.17.0：把站内 .webp 图片包成 <picture>，优先 AVIF、回退 WebP。

    - 仅当磁盘上确实存在同名 .avif 时才插入 <source>（避免 404）；
    - 只处理 /static/ 开头的站内相对路径（不碰外链，避免跨域/SSRF 复杂度）；
    - 任何异常或无匹配都原样返回，零副作用。
    """
    if not html or ".webp" not in html:
        return html
    import os as _os, re as _re
    try:
        from flask import current_app
        static_folder = current_app.static_folder
    except Exception:
        return html
    if not static_folder:
        return html

    def _avif_url(src):
        if not src.startswith("/static/"):
            return None
        disk = _os.path.join(static_folder, src[len("/static/"):])
        if not disk.lower().endswith(".webp"):
            return None
        if _os.path.isfile(disk[:-5] + ".avif"):
            return src[:-5] + ".avif"
        return None

    def _repl(m):
        tag = m.group(0)
        sm = _re.search(r'src\s*=\s*"([^"]+)"', tag)
        if not sm:
            return tag
        avif = _avif_url(sm.group(1))
        if not avif:
            return tag
        return '<picture><source type="image/avif" srcset="%s">%s</picture>' % (avif, tag)

    try:
        return _re.sub(r"<img\b[^>]*>", _repl, html)
    except Exception:
        return html


def render_markdown(content):
    """把 Markdown 渲染为 HTML 并清理（统一出口，避免 XSS）。

    v3.17.0：清洗后追加 AVIF <picture> 升级（存在同名 .avif 时）。
    """
    raw = markdown(content or "", extensions=["fenced_code", "tables"])
    return _upgrade_img_avif(clean_html(raw))
# ---------- 正文渲染缓存（v3.9.1）----------
# Markdown 渲染 + bleach 清洗是 CPU 密集操作，长文单次可达数百毫秒；以前每次
# 打开文章、每次渲染首页列表都要重算一遍。这里把结果落到 post 表的 content_html
# 列，用正文指纹（sha256，混入渲染版本号）判断是否失效——正文一改指纹就变，
# 缓存自动失效，无需在保存文章的各处手工清理。
# 渲染版本号：若将来调整 Markdown 扩展或 clean_html 白名单，把 _RENDER_VERSION
# +1 即可让全部历史缓存一次性失效，避免旧 HTML 与新的白名单不一致。
_RENDER_VERSION = "2"


def content_digest(content, html=""):
    """渲染缓存指纹：版本号 + 正文 + 渲染结果 的 sha256。

    把 HTML 本身也算进指纹，好处是缓存列若被**外部改坏**（手工改库、备份错乱回档），
    指纹立刻对不上 → 自动重新渲染自愈，而不是把脏 HTML 一直吐给访客。
    """
    import hashlib
    basis = "%s|%s|%s" % (_RENDER_VERSION, content or "", html or "")
    return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()


def render_post_html(post):
    """渲染文章正文为 HTML（已做 XSS 白名单清理），命中缓存则不再重复计算。

    - 命中：`post.content_hash` 与「正文 + 缓存 HTML」的指纹一致 → 直接返回缓存。
    - 未命中：渲染 → 用**独立连接** UPDATE 写回缓存（不碰当前会话事务，避免把
      调用方尚未提交的改动一起提交；也避免读请求里出现意外的 session.commit）。
    - 写回失败（数据库锁定/列不存在/无 app 上下文等）一律静默回退：本次仍返回
      正确 HTML，只是下次还要重算，不影响正确性。
    """
    content = post.content or ""
    cached = getattr(post, "content_html", None)
    if cached and getattr(post, "content_hash", None) == content_digest(content, cached):
        return cached

    html = render_markdown(content)
    try:
        from models import db as _db
        from sqlalchemy import text as _sql_text
        if getattr(post, "id", None):
            digest = content_digest(content, html)
            conn = _db.engine.connect()
            try:
                # 缓存写回是「锦上添花」：撞锁就快速放弃（800ms），绝不能让读请求排队等锁
                conn.execute(_sql_text("PRAGMA busy_timeout=800"))
                conn.execute(
                    _sql_text("UPDATE post SET content_html=:h, content_hash=:d WHERE id=:i"),
                    {"h": html, "d": digest, "i": post.id},
                )
                conn.commit()
                # 同步内存态：同一请求内再次渲染不再重复计算（DB 已写入，值一致）
                post.content_html = html
                post.content_hash = digest
            finally:
                try:
                    conn.execute(_sql_text("PRAGMA busy_timeout=5000"))  # 归还连接池前复原
                except Exception:
                    pass
                conn.close()
    except Exception:
        pass
    return html
