# -*- coding: utf-8 -*-
"""文章分享卡 SSR meta（v3.15.1 分享卡根治）。

微信/QQ/主流爬虫不做 JS：SPA 的动态 og 对它们无效。
本端点按 slug 服务端渲染“文章级”meta 页；nginx 对爬虫 UA 访问
/post/<slug> 时反代到此处（真人浏览器仍走 SPA）。

安全：只读 visible_posts_query（已发布/非回收站/非隐私），
输出字段全走 {{ }} 自动转义；无脚本执行、无跳转逻辑。
"""
import html
from flask import request

from .common import api_bp
from models import Post
from utils import get_setting


def _abs(url):
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    site = (get_setting("site_url", "") or "").rstrip("/")
    return site + (url if url.startswith("/") else "/" + url)


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
        if post.cover:
            image = post.cover
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
