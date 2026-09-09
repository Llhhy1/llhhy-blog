# -*- coding: utf-8 -*-
"""文章分享卡 SSR meta（v3.15.1 分享卡根治）。

微信/QQ/主流爬虫不做 JS：SPA 的动态 og 对它们无效。
本端点按 slug 服务端渲染“文章级”meta 页；nginx 对爬虫 UA 访问
/post/<slug> 时反代到此处（真人浏览器仍走 SPA）。

安全：只读 visible_posts_query（已发布/非回收站/非隐私），
输出字段全走 {{ }} 自动转义；无脚本执行、无跳转逻辑。
"""
import html
import os
from flask import request, Response, send_file

from .common import api_bp
from models import Post
from utils import get_setting, fmt_bj
from og_image import og_png_bytes


def _abs(url):
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    site = (get_setting("site_url", "") or "").rstrip("/")
    return site + (url if url.startswith("/") else "/" + url)


def _og_default_response():
    """兜底静态图（生成降级 / 文章不可见时）。

    og-default.png 的物理位置在前端 public/（生产由前端静态根/nginx 提供），
    后端 zip 内没有它——所以：本地找得到就回文件；找不到 302 交给前端静态根。
    """
    for p in (
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "static", "og-default.png"),
        # 开发机：仓库根的 vue-frontend/public/
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "vue-frontend", "public", "og-default.png"),
    ):
        if os.path.isfile(p):
            try:
                resp = send_file(p, mimetype="image/png")
                resp.headers["Cache-Control"] = "public, max-age=3600"
                return resp
            except Exception:
                break
    from flask import redirect
    return redirect("/og-default.png", code=302)


@api_bp.route("/og/post/<slug>.png")
def og_post_image(slug):
    """动态生成文章分享卡 PNG（v3.16.0 分享卡重做）。

    - 缓存：og_image 内部按 slug+updated_at+主题色 hash 落盘（myblog/data/og_cache/）
    - 降级：Pillow/中文字体缺失或绘制异常时回退 og-default.png，绝不 500
    - 封面：仅站内路径参与合成；外链不下载（防 SSRF/防延迟）
    """
    post = Post.query.filter_by(slug=slug, published=True, in_trash=False).first()
    if not post or post.is_private:
        return _og_default_response()
    site_name = get_setting("site_name", "") or get_setting("site_title", "我的博客")
    accent = get_setting("accent_color", "#1a73e8") or "#1a73e8"
    desc = (post.seo_description or post.summary or "").strip()[:120]
    category = post.category.name if getattr(post, "category", None) else ""
    stamp = str(post.updated_at or post.created_at or "")
    data, _hit = og_png_bytes(
        slug=slug, stamp=stamp,
        title=(post.title or site_name)[:80],
        desc=desc, site_name=site_name[:24], accent=accent,
        date_str=fmt_bj(post.created_at, "%Y-%m-%d") if post.created_at else "",
        read_min=max(1, round((post.word_count or 0) / 400.0)),
        category=category, cover=post.cover,
    )
    if not data:
        return _og_default_response()
    resp = Response(data, mimetype="image/png")
    # 图随文章更新与主题色变化而变，缓存 1 天 + 必须带 ETag 语义（用内容 hash 由缓存层保证）
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@api_bp.route("/qr")
def qr_image():
    """站点 URL 二维码（v3.16.0，微信扫码分享用），输出 SVG（矢量小体积）。

    安全：**仅允许本站 URL**（site_url 前缀或站内相对路径）——否则本接口会被
    当作公共二维码生成服务，给钓鱼链接批量生成码。附 60s/30 次限流。
    """
    import io
    from flask import Response
    from .common import rate_limit, client_key
    if not rate_limit(client_key("qr"), limit=30, window=60):
        return Response("too many requests", 429)
    url = (request.args.get("url") or "").strip()
    site = (get_setting("site_url", "") or "").rstrip("/")
    # 允许的 host = site_url 的 host ∪ 本次请求的 host（生产即真实域名，未配 site_url 也可用）
    from urllib.parse import urlparse
    allowed = set()
    for h in (urlparse(site).netloc if site else "", request.host or ""):
        h = (h or "").strip().lower()
        if h:
            allowed.add(h)
    if url.startswith("/"):
        absu = (site + url) if site else request.host_url.rstrip("/") + url
    elif url.startswith(("http://", "https://")):
        if urlparse(url).netloc.lower() not in allowed:
            return Response("forbidden", 403)
        absu = url
    else:
        return Response("bad request", 400)
    try:
        import segno
        q = segno.make(absu, error="m")
        buf = io.BytesIO()
        dark = get_setting("accent_color", "#1a73e8") or "#1a73e8"
        q.save(buf, kind="svg", scale=8, border=2, dark=dark, light="white")
    except Exception:
        return Response("", 404)
    resp = Response(buf.getvalue(), mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@api_bp.route("/og/post/<slug>")
def og_post(slug):
    post = Post.query.filter_by(slug=slug, published=True, in_trash=False).first()
    site_name = get_setting("site_name", "") or get_setting("site_title", "我的博客")
    title = site_name
    desc = get_setting("site_description", "") or "独立开发者的个人博客"
    image = "/og-default.png"
    url = request.url
    if post and not post.is_private:
        title = post.title
        desc = (post.seo_description or post.summary or (post.content or "")[:120] or desc)
        # v3.16.0：og:image 指向动态分享卡（路由内含降级兜底，永远有图）
        image = f"/api/og/post/{slug}.png"
    image_abs = _abs(image)
    t = html.escape(title)
    d = html.escape(desc)
    i = html.escape(image_abs)
    u = html.escape(url)
    sn = html.escape(site_name)
    return (
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{t}</title>"
        f"<meta name='description' content='{d}'>"
        f"<meta property='og:type' content='article'>"
        f"<meta property='og:site_name' content='{sn}'>"
        f"<meta property='og:title' content='{t}'>"
        f"<meta property='og:description' content='{d}'>"
        f"<meta property='og:image' content='{i}'>"
        f"<meta property='og:url' content='{u}'>"
        f"<meta name='twitter:card' content='summary_large_image'>"
        f"<meta name='twitter:title' content='{t}'>"
        f"<meta name='twitter:description' content='{d}'>"
        f"<meta name='twitter:image' content='{i}'>"
        f"<link rel='canonical' href='{u}'>"
        f"</head><body style='margin:0;font-family:-apple-system,sans-serif'>"
        f"<h1 style='margin:16px'>{t}</h1>"
        f"<p style='margin:0 16px'>{d}</p>"
        f"</body></html>",
        200,
        {"Content-Type": "text/html; charset=utf-8",
         "X-Robots-Tag": "noindex,nofollow",
         "Cache-Control": "public, max-age=300"},
    )
