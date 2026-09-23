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
import re
from flask import request, Response, send_file

from .common import api_bp
from models import visible_posts_query, hreflang_alternates
from utils import (get_setting, fmt_bj, site_base, abs_url, seo_shell_ua,
                   is_search_engine_ua, HUMAN_VETO_REASONS)
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


def _plain_preview(text, n=120):
    """Markdown → 纯文本预览（v3.19.1，`og:description` 兜底用）。

    不引入渲染依赖，只剥「语法噪音」：图片整段丢弃、链接留文字、代码反引号去掉、
    标题/引用/列表符号去掉、HTML 标签丢弃，最后压平空白。

    修的是纯观感问题：此前兜底直接 `post.content[:120]`，`## ` 和 `![图](…)`
    这类源码痕迹会原样进分享卡文案。
    """
    s = str(text or "")
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)        # 图片：整段丢弃
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)    # 链接：只留文字
    s = re.sub(r"`{1,3}", "", s)                      # 行内 / 围栏代码反引号
    s = re.sub(r"<[^>]+>", "", s)                     # HTML 标签
    s = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", s, flags=re.M)  # 行首标记
    s = re.sub(r"[*_~]{1,}", "", s)                   # 强调符号
    s = " ".join(s.split())
    return s[:n]


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

    v3.20.0 收口（闭环 R90 待办②）：相对路径分支**不再回退 `request.host_url`**。
    此前 site_url 未配置时会用请求 Host 拼二维码内容 —— 「对外地址由客户端可控的
    请求头决定」，与 v3.18.9 为 `/api/og/*` / `_abs()` 做的收口原则相冲突。
    现在未配置即返回 400（带可操作提示），与 `/api/og/*` 行为一致。
    绝对 URL 分支仍放行「本次请求的 host」（那是访客地址栏里的域名，且 URL 由客户端
    显式传入、我们只做白名单校验），以保证别名域名访问时扫码仍然可用。
    """
    import io
    from flask import Response
    from .common import rate_limit, client_key
    if not rate_limit(client_key("qr"), limit=30, window=60):
        return Response("too many requests", 429)
    url = (request.args.get("url") or "").strip()
    site = (get_setting("site_url", "") or "").rstrip("/")
    # 允许的 host = site_url 的 host ∪ **本次请求的 host**。
    # 为什么留着 request.host：这一支是「客户端**显式传入**一个绝对 URL，我们只校验
    # 它是不是我们的域名」。而 request.host 正是访客浏览器地址栏里的域名，
    # 放行它不会带来任何「攻击者决定的对外地址」——别名域名访问也能正常出码。
    # （反过来，**由我们构造**对外地址的分支见下方，那里禁止用 Host。）
    from urllib.parse import urlparse
    allowed = set()
    for h in (urlparse(site).netloc if site else "", request.host or ""):
        h = (h or "").strip().lower()
        if h:
            allowed.add(h)
    if url.startswith("/"):
        # v3.20.0（闭环 R90 待办②）：**不再回退 `request.host_url`**。
        # 「对外声明什么地址」必须由 site_url / site_base() 决定，**不能由客户端可控的
        # Host 头决定** —— 这是 v3.18.9 已为 `/api/og/*` 与 `_abs()` 做过的同一处收口，
        # 本接口此前是唯一漏网的。未配置时直接 400 并给出可操作的提示，
        # 与 `/api/og/*` 在 site_base() 为空时的行为保持一致。
        if not site:
            return Response(
                "site_url 未配置：请先在后台「站点设置」填站点 URL（否则二维码地址会随请求头变化）",
                400)
        absu = site + url
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
      3. 其余 → 见下面两小类（v3.19.1 拆分）

    **出口 3 为什么拆成 3a/3b（v3.19.1 修复的线上事故）**：
      - 3a「直敲 API 地址」（无 ?seo=1）→ 302 回 /post/<slug>。安全：该请求没有
        nginx 的通道标记，即便 UA 会被 rewrite，下一次请求带 ?seo=1 走 2/3b，只有一跳。
      - 3b「经通道但闸门否决」（有 ?seo=1）→ **不得 3xx**，按否决原因两分：
        * 真人信号（微信 / QQ 内置浏览器）→ 200 + `noindex,nofollow` 的**可读页**
          （人能读到正文，索引不受污染）
        * `tool-bot` / `not-crawler` → 404 + noindex，**不给正文**
        为什么不能 302：nginx 的 map 只按 UA 粗筛、**看不见请求头**，
        会把这个 UA 再次 rewrite 回来 → 无限 302 环。
        v3.19.0 线上实测：Googlebot / Baiduspider（送 Accept: text/html）与
        QQ 内置浏览器真人**三者都在 12 次重定向后仍是 302**——搜索引擎彻底抓不到
        正文（收录归零），真人看到 ERR_TOO_MANY_REDIRECTS。
    """
    site_name = get_setting("site_name", "") or get_setting("site_title", "我的博客")

    # ---- 可见性：唯一真相源，含 scheduled_at / in_trash / is_private ----
    post = visible_posts_query().filter_by(slug=slug).first()
    if not post:
        return _not_found_shell(site_name)

    # v3.21.0 内容多语言：?lang= 解析到同组译文（不可见则回退）
    req_lang = (request.args.get("lang") or "").strip()
    if req_lang and req_lang != (post.lang or "zh") and post.translation_group:
        alt = visible_posts_query().filter_by(
            translation_group=post.translation_group, lang=req_lang).first()
        if alt:
            post = alt

    # ---- 限流：豁免正规搜索引擎（把 Google/Baidu 的正常抓取 429 掉 = 自废收录）----
    if not is_search_engine_ua():
        from .common import rate_limit, client_key
        if not rate_limit(client_key("og_shell"), limit=120, window=60):
            return Response("too many requests", 429, _varied())

    seo_flag = (request.args.get("seo") or "").strip() == "1"
    allow, reason = seo_shell_ua()

    # ---- 出口 3a：直敲 API 地址（未经 nginx 通道）→ 回公开地址 ----
    # 只在**没有**通道标记时 302：该请求没有 nginx 的通道标记，即使 UA 会被
    # rewrite，下一次请求会带 ?seo=1 走出口 2/3b，只有一跳。
    if not seo_flag:
        from flask import redirect
        resp = redirect(_public_url(slug), code=302)
        # 302 同样要带 Vary：否则 CDN 可能把「给爬虫的 302」缓存下来发给真人。
        # （v3.19.1：原实现漏了，由 test_shell_and_redirect_carry_vary 抓出）
        resp.headers.update(_varied())
        return resp

    # ---- 出口 3b：经通道但闸门否决 ----
    # ⚠️ **绝不能 3xx**：nginx 的 map 只按 UA 粗筛、看不见请求头，会把这个 UA
    # 再次 rewrite 回来 → 无限 302 环。线上实测 Googlebot / Baiduspider /
    # QQ 内置浏览器真人三者都在 12 次重定向后仍是 302。
    # 按否决原因分两种处置（都不 3xx）：
    if not allow:
        if reason not in HUMAN_VETO_REASONS:
            # tool-bot / not-crawler：本就不该出现在通道上（nginx 不会 rewrite
            # 它们，走到这里多半是手拼 ?seo=1）。**不给正文**，也不 3xx。
            return _not_found_shell(site_name)
        # 真人（微信 / QQ 内置浏览器等）：给可读页面但 noindex—— 人能读到文章，
        # 索引不受污染，环被断掉。这是唯一「既不误伤真人又不成环」的处置。
        indexable = False
    else:
        indexable = True

    title = post.title or site_name
    desc = (post.seo_description or post.summary or _plain_preview(post.content, 120)
            or get_setting("site_description", "") or "独立开发者的个人博客").strip()
    image = f"/api/og/post/{post.slug}.png"
    image_abs = _abs(image)
    public_url = _public_url(post.slug)
    t = html.escape(title)
    d = html.escape(desc)
    i = html.escape(image_abs)
    u = html.escape(public_url)
    sn = html.escape(site_name)
    ld = _json_ld(post, public_url, site_name, image_abs, desc)
    # v3.21.0 内容多语言：hreflang 互链（防重复内容）+ 正确 <html lang>
    base = public_url.rsplit("/post/", 1)[0]
    alt_links = "".join(
        f"<link rel='alternate' hreflang='{h}' href='{html.escape(u_)}'>"
        for h, u_ in hreflang_alternates(post, base)
    )
    html_lang = "zh-CN" if (post.lang or "zh") == "zh" else post.lang

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
        f"<!DOCTYPE html><html lang='{html_lang}'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{t}</title>"
        f"<meta name='description' content='{d}'>"
        f"<link rel='canonical' href='{u}'>"
        f"{alt_links}"
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
        _shell_headers(extra_noindex=not indexable),
    )


@api_bp.route("/seo/shell-check")
def seo_shell_check():
    """爬虫通道自检（v3.18.9 建；**v3.19.1 改为本地直调、零出网**）。

    两个 v3.19.0 的缺陷在这里一并修掉：

    ① **自请求放大面**：v3.19.0 用 `urllib` 回打 `site_base()` 的公网地址——
       即从 Flask worker 内部再发起一个到自己的请求，且是**匿名可调**的。
       一个请求占住一个 worker 并串行等 4 个自请求返回；生产是 gunicorn gthread
       4 worker × 2 线程，持续并发即可把可用槽吃满（可用性事故面）。
       改为 `test_request_context()` 注入请求头后**直接调 `og_post()`**：
       自检的目的本来只是验证闸门判定，不需要绕一圈公网。
       「线上 nginx 有没有配好」这一层交给 `deploy_guide.md` 里的 curl 人工核验。

    ② **假绿**：v3.19.0 的探针给搜索引擎**只送 UA、不送 `Accept`**，而真实
       Googlebot / Baiduspider 会送 `Accept: text/html`。正因为漏测这个头，
       线上那个 302 环在自检里**全绿**——假绿了一整轮。现在探针送真实请求头。

    判定预期分**三档**（v3.19.1），**三档都不允许 3xx**：
      `shell`   = 抓取方 → 200 + 可索引壳页
      `noindex` = 真人（QQ 内置浏览器）→ 200 + 不可索引的**可读页**（不再期望 302）
      `404`     = 非通道候选（Chrome）→ 404，不给内容
    经通道的请求若被否决，返回 200/404（而**不是 302**）是断掉 302 环的唯一办法，
    见 `og_post` docstring 出口 3b。
    """
    from flask import jsonify, current_app
    from models import Post
    from .common import rate_limit, client_key, _current_user_or_none

    # 鉴权：本端点会渲染文章正文，只给超管（v3.19.1 补）
    u = _current_user_or_none()
    if not u or not getattr(u, "is_super", False):
        return Response("forbidden", 403, _varied())
    if not rate_limit(client_key("seo_shell_check"), limit=30, window=60):
        return Response("too many requests", 429, _varied())

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

    app = current_app._get_current_object()

    def _probe(ua, extra_headers=None):
        """在本地请求上下文里直调 `og_post()` —— **零网络**。"""
        hdrs = {"User-Agent": ua}
        hdrs.update(extra_headers or {})
        with app.test_request_context("/api/og/post/%s?seo=1" % slug, headers=hdrs):
            r = og_post(slug)
        if isinstance(r, tuple):              # (body, status, headers)
            body = r[0] if isinstance(r[0], str) else ""
            status = r[1] if len(r) > 1 else 200
            h = r[2] if len(r) > 2 and hasattr(r[2], "get") else {}
        else:                                 # Response（如 redirect）
            status = r.status_code
            h = r.headers
            body = r.get_data(as_text=True) if hasattr(r, "get_data") else ""
        return {"status": status, "location": (h.get("Location") or ""),
                "robots": (h.get("X-Robots-Tag") or ""), "body": body}

    cases = (
        # ⚠️ 搜索引擎探针**必须送 `Accept: text/html`** —— 真实 Googlebot / Baiduspider
        #    就送它。v3.19.0 漏测这个头，导致线上 302 环在自检里**全绿**（假绿一整轮）。
        ("Baiduspider（搜索引擎）",
         "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
         {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
         "shell"),
        ("Googlebot（搜索引擎）",
         "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
         {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
         "shell"),
        ("MicroMessenger（微信预览抓取）",
         "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) MicroMessenger/8.0.40",
         None, "shell"),
        ("QQ 内置浏览器（真人）",
         "Mozilla/5.0 (Linux; U; Android 12) AppleWebKit/537.36 Chrome/100.0 Mobile Safari/537.36"
         " MQQBrowser/13.0 QQ/9.7.10.43400",
         {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
          "Sec-Fetch-Mode": "navigate"}, "noindex"),
        ("Chrome（真人）",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
         {"Accept": "text/html", "Sec-Fetch-Mode": "navigate"}, "404"),
    )
    checks = []
    for label, ua, hdr, expect in cases:
        r = _probe(ua, hdr)
        body = r.get("body", "")
        is_shell = ("og:title" in body)
        m = re.search(r"canonical'\s+href='([^']+)'", body) or \
            re.search(r'canonical"\s+href="([^"]+)"', body)
        canonical = m.group(1) if m else ""
        robots = r.get("robots") or ""
        indexable = ("noindex" not in robots) and ("index" in robots)
        status = r.get("status")
        is_3xx = isinstance(status, int) and 300 <= status < 400
        # 三档预期，**都不允许 3xx**（经通道 3xx = nginx 再 rewrite = 302 环）
        if expect == "shell":
            # 抓取方：200 + 可索引 + 确实是壳页
            ok = (status == 200 and is_shell and indexable)
        elif expect == "noindex":
            # 真人：200 + 不可索引（内容照给，人能读）
            ok = (status == 200 and not indexable and not is_3xx)
        else:
            # 非通道候选（tool-bot / 普通浏览器）：404 + 不可索引 + 不给正文
            ok = (status == 404 and not indexable and not is_shell)
        checks.append({
            "label": label, "expect": expect, "status": status,
            "location": r.get("location", ""), "robots": robots,
            "server_html": is_shell, "canonical": canonical,
            "canonical_ok": canonical.endswith("/post/" + slug),
            "indexable": indexable, "ok": ok,
            "would_loop": is_3xx,
        })

    return jsonify(slug=slug, site_base=base, checks=checks,
                   all_ok=all(c["ok"] for c in checks),
                   canonical_ok=all(c["canonical_ok"] or c["expect"] != "shell"
                                    for c in checks),
                   index_ok=all(c["indexable"] for c in checks if c["expect"] == "shell"))

