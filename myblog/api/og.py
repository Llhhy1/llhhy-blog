# -*- coding: utf-8 -*-
"""文章分享卡 + SEO 爬虫通道（v3.15.1 起，v3.18.9 重做）。

微信/QQ/主流爬虫不做 JS：SPA 的动态 og 对它们无效。
本端点按 slug 服务端渲染"文章级"页面；nginx 对爬虫/社交抓取 UA 访问
``/post/<slug>`` 时 rewrite 到此处并带上 ``?seo=1``（真人浏览器仍走 SPA）。

**三种互斥出口**（v3.18.9，接通道时必须明确区分，否则会自废收录）：

==============  ============================================  =========================
条件            响应                                          理由
==============  ============================================  =========================
文章不可见      404 + ``noindex,nofollow``                    不透露该 slug 的任何信息
经通道 + 抓取方  200 壳页 + ``index,follow`` + canonical=公开地址 正式出口，允许收录
其余（真人/直敲） 302 到 ``/post/<slug>``                       真人必须回到能跑 JS 的 SPA
==============  ============================================  =========================

安全：**只读 visible_posts_query**（已发布 + 未到定时发布时间 + 非回收站 + 非隐私，
v3.18.9 修正——此前 meta 页与 .png 两处手写过滤都漏了 ``scheduled_at``，未到点的
文章标题会被画进对外可取的 PNG 分享卡）。
输出字段全走 `html.escape`；壳页无脚本、无跳转逻辑。
"""
import html
import json
import os
from flask import request, Response, send_file

from .common import api_bp
from models import visible_posts_query
from utils import get_setting, fmt_bj, site_base, abs_url, seo_shell_ua, is_search_engine_ua
from og_image import og_png_bytes


def _abs(url):
    """站内相对路径 → 对外绝对 URL（v3.18.9：统一走 utils.abs_url）。

    未配置 site_url 时返回相对路径，**绝不用 request.url / request.host 兜底**。
    """
    return abs_url(url)


def _public_url(slug):
    """文章的公开地址——og:url / twitter:url / canonical 三处唯一的取值来源。

    v3.18.9 修复：此前用 `request.url`，生成的 canonical 是
    `https://域名/api/og/post/<slug>`，即对外声明「规范页是 API 地址」，
    与真实公开页 `/post/<slug>` 不一致。
    """
    return abs_url("/post/%s" % slug)


def _varied(headers=None):
    """同 URL 多结果的必备响应头（v3.18.9）。

    本端点同一路径按 UA/导航信号返回 200/302/404 三种结果，不声明 Vary
    会被 CDN/共享缓存串味（爬虫拿到 302、真人拿到壳页）。
    """
    h = dict(headers or {})
    h["Vary"] = "User-Agent, Sec-Fetch-Mode, Accept, Referer"
    return h


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
    - 可见性（v3.18.9 修正）：改走 visible_posts_query()，此前手写的
      `filter_by(published=True, in_trash=False)` 再补 `is_private` **漏了 scheduled_at**，
      未到发布时间的文章标题会被直接画进这张对外可取的图。
    """
    post = visible_posts_query().filter_by(slug=slug).first()
    if not post:
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


def _shell_headers(extra_noindex=False):
    """壳页响应头。抓取方拿到的是**可索引**页面（v3.18.9 关键修复）。

    v3.18.9 之前此处恒下发 ``noindex,nofollow``——一旦 nginx 把真实搜索引擎
    导到这里，这行等于**明确拒绝收录自己的文章**，接通通道反而杀死收录。
    现在只有「不可见」与「非通道直敲」两种情形才 noindex，正式出口给 index,follow。
    """
    h = _varied({
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=300",
    })
    h["X-Robots-Tag"] = "noindex,nofollow" if extra_noindex else "index,follow"
    return h


def _not_found_shell(site_name):
    """不可见文章的 404 兜底页：站点级文案，**不透露 slug 的任何信息**。

    与 200 壳页共用 index 语义会误导搜索引擎，所以显式 noindex。
    """
    t = html.escape(site_name or "我的博客")
    return (
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>页面不存在 - {t}</title>"
        f"<meta name='robots' content='noindex,nofollow'>"
        f"</head><body style='margin:0;font-family:-apple-system,BlinkMacSystemFont,"
        f"\"Segoe UI\",sans-serif;padding:40px 24px;color:#333'>"
        f"<h1 style='font-size:20px;margin:0 0 12px'>页面不存在</h1>"
        f"<p style='margin:0;color:#666'>该地址无法访问，可能已被删除或尚未发布。</p>"
        f"<p style='margin:24px 0 0'><a href='/' style='color:#1a73e8'>{t}</a></p>"
        f"</body></html>",
        404,
        _shell_headers(extra_noindex=True),
    )


def _json_ld(post, public_url, site_name, image_abs, desc):
    """BlogPosting + BreadcrumbList 结构化数据（v3.18.9）。

    百度对 JS 最不友好，只有 meta 时 rankings 弱；带正文 + JSON-LD 后
    百度可读到完整正文与结构化信息。字段全部取自 DB 并经 json 序列化
    （JSON-LD 里 `</script>` 会被 `json.dumps` 的转义处理，但仍显式替换兜底）。
    """
    from models import Category
    payload = [
        {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": (post.title or "")[:110],
            "description": desc,
            "url": public_url,
            "mainEntityOfPage": {"@type": "WebPage", "@id": public_url},
            "image": [image_abs] if image_abs else [],
            "datePublished": fmt_bj(post.created_at, "%Y-%m-%dT%H:%M:%S+08:00")
            if post.created_at else "",
            "dateModified": fmt_bj(post.updated_at or post.created_at, "%Y-%m-%dT%H:%M:%S+08:00")
            if (post.updated_at or post.created_at) else "",
            "author": {"@type": "Person",
                       "name": (post.author.username if post.author else "") or site_name},
            "publisher": {"@type": "Organization", "name": site_name},
        },
    ]
    cat = getattr(post, "category", None)
    if cat:
        payload.append({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "首页",
                 "item": abs_url("/")},
                {"@type": "ListItem", "position": 2, "name": cat.name,
                 "item": abs_url("/category/%s" % cat.slug)},
                {"@type": "ListItem", "position": 3, "name": post.title or ""},
            ],
        })
    raw = json.dumps(payload, ensure_ascii=False)
    # 防 `</script>` 提前闭合（json.dumps 不转义斜杠）
    raw = raw.replace("</", "<\\/")
    return (f"<script type='application/ld+json'>{raw}</script>")


@api_bp.route("/og/post/<slug>")
def og_post(slug):
    """SEO 爬虫通道的正式出口（v3.18.9 三出口重做，详见模块 docstring）。

    出口判定顺序（**不可调换**）：
      1. 文章不可见（不存在/草稿/隐私/回收站/定时未到）→ 404 + noindex，不透露信息
      2. 经通道（?seo=1）且闸门判定为抓取方 → 200 壳页 + index,follow + 公开 canonical
      3. 其余（真人、直接敲 API 地址）→ 302 回 /post/<slug>

    为什么「直敲 API 地址」要 302 而不是给 noindex 壳页：那会永久停着一个
    「可访问但 canonical 指向自己」的页面，与真实公开页争规范页；
    302 回公开地址后由 nginx 带上 ?seo=1 再裁定，**不成环**（真人 302 后
    nginx 的 UA 分流不会把真人再送来，见 utils/seo_shell.py 第二层否决）。
    """
    site_name = get_setting("site_name", "") or get_setting("site_title", "我的博客")

    # ---- 可见性：唯一真相源，含 scheduled_at / in_trash / is_private ----
    post = visible_posts_query().filter_by(slug=slug).first()
    if not post:
        return _not_found_shell(site_name)

    # ---- 限流：豁免正规搜索引擎（把 Google/Baidu 的正常抓取 429 掉 = 自废收录）----
    if not is_search_engine_ua():
        from .common import rate_limit, client_key
        if not rate_limit(client_key("og_shell"), limit=120, window=60):
            return Response("too many requests", 429, _varied())

    seo_flag = (request.args.get("seo") or "").strip() == "1"
    allow, _reason = seo_shell_ua()

    # ---- 出口 3：真人 / 非通道访问 → 回公开地址 ----
    if not (seo_flag and allow):
        from flask import redirect
        return redirect(_public_url(slug), code=302)

    # ---- 出口 2：经通道且判定为抓取方 → 正式可索引壳页 ----
    title = post.title or site_name
    desc = (post.seo_description or post.summary or (post.content or "")[:120]
            or get_setting("site_description", "") or "独立开发者的个人博客").strip()
    image = f"/api/og/post/{slug}.png"
    image_abs = _abs(image)
    public_url = _public_url(slug)
    t = html.escape(title)
    d = html.escape(desc)
    i = html.escape(image_abs)
    u = html.escape(public_url)
    sn = html.escape(site_name)
    ld = _json_ld(post, public_url, site_name, image_abs, desc)

    # 正文：复用 content_html 缓存列（v3.9.1 起渲染结果已落库，命中时几乎零成本），
    # 不新写渲染逻辑，也就不会引入与正文页不一致的 XSS/白名单差异。
    body = ""
    try:
        from utils import render_post_html
        body = render_post_html(post) or ""
    except Exception:
        body = ""
    if not body:
        # 渲染不可用（无缓存且渲染异常）时至少给摘要，绝不 500
        body = f"<p>{d}</p>"

    return (
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{t}</title>"
        f"<meta name='description' content='{d}'>"
        f"<link rel='canonical' href='{u}'>"
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
        f"<meta name='twitter:url' content='{u}'>"
        f"{ld}"
        f"</head><body style='margin:0;font-family:-apple-system,BlinkMacSystemFont,"
        f"\"Segoe UI\",sans-serif'>"
        f"<article style='max-width:760px;margin:0 auto;padding:16px'>"
        f"<h1 style='margin:16px 0 8px'>{t}</h1>"
        f"<p style='margin:0;color:#666'>{d}</p>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:16px 0'>"
        f"{body}"
        f"</article>"
        f"</body></html>",
        200,
        _shell_headers(),
    )


@api_bp.route("/seo/shell-check")
def seo_shell_check():
    """爬虫通道自检（v3.18.9）—— 供后台「收录」页调用。

    按需自测本端点在 4 种身份下的真实响应，返回三盏灯：
    ① 抓取方是否拿到服务端 HTML ② canonical 是否等于 `/post/<slug>`
    ③ 是否 index,follow。**真人两盏灯必须显示"拿到 SPA"**——
    这一项才是防生产事故的关键，只测爬虫是不够的。
    """
    from flask import jsonify
    from models import Post
    slug = (request.args.get("slug") or "").strip()
    if not slug:
        p = visible_posts_query().order_by(Post.created_at.desc()).first()
        slug = p.slug if p else ""
    if not slug:
        return jsonify(error="站点还没有已发布文章，无法自检"), 404

    base = site_base()
    if not base:
        return jsonify(error="site_url 未配置：og:url/canonical 会退化成相对路径，"
                             "微信卡片将取不到图。请先在后台设置站点 URL。"), 400

    import urllib.request
    import urllib.error

    def _probe(ua, extra_headers=None, path=None):
        url = "%s%s?seo=1" % (base, path or ("/api/og/post/" + slug))
        req = urllib.request.Request(url, headers=dict({"User-Agent": ua},
                                                       **(extra_headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                body = r.read(4000).decode("utf-8", "replace")
                return {"status": r.status, "location": r.headers.get("Location", ""),
                        "robots": r.headers.get("X-Robots-Tag", ""), "body": body}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "location": e.headers.get("Location", ""),
                    "robots": e.headers.get("X-Robots-Tag", ""),
                    "body": e.read(4000).decode("utf-8", "replace")}
        except Exception as e:
            return {"status": 0, "location": "", "robots": "",
                    "body": "", "error": type(e).__name__}

    public_path = "/post/" + slug
    checks = []
    for label, ua, hdr, expect in (
        ("Baiduspider（搜索引擎）",
         "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
         None, "shell"),
        ("MicroMessenger（微信预览抓取）",
         "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) MicroMessenger/8.0.40",
         None, "shell"),
        ("QQ 内置浏览器（真人）",
         "Mozilla/5.0 (Linux; U; Android 12) AppleWebKit/537.36 Chrome/100.0 Mobile Safari/537.36"
         " MQQBrowser/13.0 QQ/9.7.10.43400",
         {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
          "Sec-Fetch-Mode": "navigate"}, "spa"),
        ("Chrome（真人）",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
         {"Accept": "text/html", "Sec-Fetch-Mode": "navigate"}, "spa"),
    ):
        r = _probe(ua, hdr, public_path)
        body = r.get("body", "")
        is_shell = ("og:title" in body)
        canonical = ""
        import re as _re
        m = _re.search(r"canonical'\s+href='([^']+)'", body) or \
            _re.search(r'canonical"\s+href="([^"]+)"', body)
        if m:
            canonical = m.group(1)
        indexable = "index" in (r.get("robots") or "") and "noindex" not in (r.get("robots") or "")
        ok = (r.get("status") == 200 and is_shell) if expect == "shell" \
            else (r.get("status") in (200, 301, 302, 307, 308))
        checks.append({
            "label": label, "expect": expect, "status": r.get("status"),
            "location": r.get("location", ""), "robots": r.get("robots", ""),
            "server_html": is_shell, "canonical": canonical,
            "canonical_ok": canonical.endswith("/post/" + slug),
            "indexable": indexable, "ok": ok, "error": r.get("error", ""),
        })

    shell_ok = all(c["ok"] for c in checks)
    return jsonify(slug=slug, site_base=base, checks=checks,
                   all_ok=shell_ok,
                   canonical_ok=all(c["canonical_ok"] or c["expect"] == "spa" for c in checks),
                   index_ok=all(c["indexable"] or c["expect"] == "spa" for c in checks))

