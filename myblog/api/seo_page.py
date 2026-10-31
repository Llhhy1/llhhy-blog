"""SPA 列表路径的服务端 SEO 壳页（v4.10.0，ROADMAP §3.1）。

## 要解决什么

前台是 Vue SPA，**不执行 JS 的爬虫抓 `/archive`、`/category/tech` 这类路径时
拿到的永远是 `index.html` 里那套站点级默认 meta** —— 所有列表页共用同一个
标题和同一段描述。结果就是：这些页面在搜索引擎眼里是**一堆内容相同、且都
没实质内容的页面**（重复内容 + 空壳），既不会被好好收录，还会稀释文章页权重。

v3.18.9 已经给**文章页**开了服务端通道（`/api/og/post/<slug>?seo=1`）。
本模块把同一条通道延伸到**列表页**。

## 为什么不再做「通用预渲染」

可选的另一条路是构建期预渲染 / 通用 SSR。没选它，理由很实在：
本站在用形态是**单人博客**，列表页内容全部来自数据库且随时会变，
预渲染必然要处理「什么时候重新生成」以及「生成期间的新文章怎么办」——
为一个人的博客维护一套构建期渲染流水线，收益远小于成本。
服务端按需渲染（带 5 分钟 HTTP 缓存）就已经解决了爬虫侧的全部问题。

## 三条硬约束

1. **只对认识的路径服务**。不认识 → 404 + noindex，**绝不给通用兜底页**
   （那等于给爬虫无限多个内容雷同的 URL，是 SEO 上的自伤）。
2. **只输出「可见」的内容**：走 `visible_posts_query()`，草稿 / 定时未到 /
   回收站 / 隐私文章一律不出现在列表里 —— 与前台列表完全同一口径。
3. **闸门与文章页共用**：`_shell_gate()`，判定只写一份。
"""
import html
import json

from flask import Response, redirect

from models import (Category, FriendLink, Post, PostTag, Series, Tag,
                    visible_posts_query)
from utils import get_setting
from utils.taxonomy_slug import resolve_taxonomy

from .common import api_bp
from .og import _shell_gate, _shell_headers, _varied

# 单页最多列多少条。列表页对爬虫的价值是「链接发现 + 标题可读」，
# 堆 500 条只会让页面变成另一个意义不明的庞然大物。
MAX_ITEMS = 50

# 认识的路径（第一级段）
_KNOWN_ROOTS = ("archive", "about", "links", "category", "tag", "series")


def _site_name():
    return get_setting("site_name", "") or get_setting("site_title", "我的博客")


def _posts_for(kind, slug):
    """按路径类型取可见文章（最新在前）。返回 ``(query, None)`` 或 ``(None, 原因)``。"""
    base = visible_posts_query()
    if kind == "archive":
        return base.order_by(Post.created_at.desc()), None
    if kind == "category":
        cat = Category.query.filter_by(slug=slug).first()
        if not cat:
            return None, "分类不存在"
        return base.filter(Post.category_id == cat.id).order_by(Post.created_at.desc()), None
    if kind == "tag":
        tag = Tag.query.filter_by(slug=slug).first()
        if not tag:
            return None, "标签不存在"
        return (base.join(PostTag, PostTag.post_id == Post.id)
                .filter(PostTag.tag_id == tag.id)
                .order_by(Post.created_at.desc())), None
    if kind == "series":
        s = Series.query.filter_by(slug=slug).first()
        if not s:
            return None, "系列不存在"
        return base.filter(Post.series_id == s.id).order_by(Post.created_at.desc()), None
    return None, "不支持的路径"


def page_meta(raw_path):
    """把 SPA 路径解析成壳页数据；**不认识的路径返回 None**（调用方 404）。

    返回 dict：``{title, desc, canonical, heading, items:[(url,title,summary)]}``
    """
    path = (raw_path or "").strip().strip("/")
    segs = [s for s in path.split("/") if s]
    if not segs or segs[0] not in _KNOWN_ROOTS:
        return None
    kind = segs[0]
    site = _site_name()
    canon = "/" + path

    # —— 两个非列表的静态页 ——
    if kind == "about":
        desc = (get_setting("site_description", "") or "").strip()
        return {
            "title": "关于 - %s" % site,
            "desc": desc or ("%s：独立开发者的个人博客。" % site),
            "canonical": canon,
            "heading": "关于" if not site else "关于 %s" % site,
            "items": [],
            "kind": "about",
        }
    if kind == "links":
        # FriendLink 没有「可见性」列（模型里只有 name/url/description/sort/rss_url），
        # 全表即公开列表，与前台友链页同源，无需再过滤。
        rows = FriendLink.query.order_by(FriendLink.sort.asc()).limit(MAX_ITEMS).all()
        items = [(r.url or "", r.name or "", r.description or "") for r in rows]
        return {
            "title": "友情链接 - %s" % site,
            "desc": "与本博客互换友链的站点：%s" % "、".join(i[1] for i in items[:8] if i[1]),
            "canonical": canon,
            "heading": "友情链接",
            "items": items,
            "kind": "links",
        }

    # ⚠️ `archive` 是**单段**路径，而 category/tag/series 是两段。
    # 若把「少于两段就 404」写在前面，归档页会被这条规则误杀（v4.10.0 实测踩到）。
    if kind == "archive":
        q, why = _posts_for("archive", "")
        if q is None:
            return None
        rows = q.limit(MAX_ITEMS).all()
        total = q.count()
        items = [("/post/%s" % p.slug, p.title or "",
                  (p.seo_description or p.summary or "").strip()) for p in rows]
        return {
            "title": "文章归档 - %s" % site,
            "desc": "按时间倒序列出 %s 的全部文章，共 %d 篇。" % (site, total),
            "canonical": canon,
            "heading": "文章归档",
            "items": items,
            "kind": "archive",
            "total": total,
        }

    if len(segs) < 2:
        # /category 这种没有 slug 的路径：不是真实页面（前台也是 404）
        return None
    slug = segs[1]

    label = ""
    extra = ""
    redirect_to = ""
    if kind == "category":
        c, legacy = resolve_taxonomy(Category, slug)
        label = c.name if c else slug
        if legacy:
            slug, redirect_to = c.slug, "/category/" + c.slug
    elif kind == "tag":
        t, legacy = resolve_taxonomy(Tag, slug)
        label = t.name if t else slug
        if legacy:
            slug, redirect_to = t.slug, "/tag/" + t.slug
    elif kind == "series":
        s, legacy = resolve_taxonomy(Series, slug)
        if s is not None:
            label = s.name
            extra = s.description or ""
            if legacy:
                slug, redirect_to = s.slug, "/series/" + s.slug
        else:
            label = slug

    q, why = _posts_for(kind, slug)
    if q is None:
        return None
    rows = q.limit(MAX_ITEMS).all()
    total = q.count()
    items = [("/post/%s" % p.slug, p.title or "",
              (p.seo_description or p.summary or "").strip()) for p in rows]

    kind_cn = {"category": "分类", "tag": "标签", "series": "系列"}[kind]
    title = "%s：%s - %s" % (kind_cn, label, site)
    desc = (extra.strip() or ("%s「%s」下的全部文章，共 %d 篇。"
                              % (kind_cn, label, total)))
    heading = "%s：%s" % (kind_cn, label)
    # v5.4.0：canonical 用**解析后的** slug（旧中文/大小写旧写法不再产生第二个可索引地址）
    canon = "/%s/%s" % (kind, slug)
    return {
        "title": title,
        "desc": desc,
        "canonical": canon,
        "heading": heading,
        "items": items,
        "kind": kind,
        "total": total,
        "redirect": redirect_to,
    }


def _json_ld_list(meta, site_name, abs_canonical):
    """CollectionPage + BreadcrumbList。列表页给结构化数据的意义是
    **让爬虫看懂「这是一组文章的索引」**，而不是又一篇内容。"""
    items = [
        {"@type": "ListItem", "position": i + 1, "url": _abs(u), "name": t}
        for i, (u, t, _s) in enumerate(meta["items"])
    ]
    payload = [{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": meta["title"],
        "description": meta["desc"],
        "url": abs_canonical,
        "isPartOf": {"@type": "WebSite", "name": site_name, "url": _abs("/")},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }]
    raw = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return "<script type='application/ld+json'>%s</script>" % raw


def _abs(u):
    from utils import abs_url
    return abs_url(u)


@api_bp.route("/og/page/<path:page_path>")
def og_page(page_path):
    """列表页壳页（爬虫通道出口）。

    nginx 侧把爬虫的 `/archive`、`/category/<slug>` 等请求
    rewrite 到这里（带 `?seo=1`）；真人照旧走 SPA，见 `deploy_guide.md` 第 4b 步。
    """
    site_name = _site_name()

    # 限流：豁免正规搜索引擎（把 Google/Baidu 的正常抓取 429 掉 = 自废收录）
    if not _is_search_engine():
        from .common import client_key, rate_limit
        if not rate_limit(client_key("og_shell"), limit=120, window=60):
            return Response("too many requests", 429, _varied())

    meta = page_meta(page_path)
    if not meta:
        # 不认识的路径 → 404 + noindex。绝不给通用兜底页（会产生大量重复内容）。
        return Response(_render_404(site_name), 404,
                        _shell_headers(extra_noindex=True))

    # v5.4.0：旧地址（中文 slug / 大小写旧写法）→ 301 到新地址。
    # 这是真正的 HTTP 301：nginx 的爬虫通道 rewrite 到这里，搜索引擎拿到的是跳转指令，
    # 而不是「200 页面里用 canonical 暗示」。
    if meta.get("redirect"):
        return redirect(meta["redirect"], code=301)

    resp, indexable = _shell_gate(_abs(meta["canonical"]), site_name)
    if resp is not None:
        return resp

    return Response(_render(meta, site_name), 200,
                    _shell_headers(extra_noindex=not indexable))


def _is_search_engine():
    from utils.seo_shell import is_search_engine_ua
    return is_search_engine_ua()


def _render_404(site_name):
    t = html.escape(site_name)
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>页面不存在 - %s</title>"
        "<meta name='robots' content='noindex,nofollow'>"
        "</head><body style='margin:0;font-family:sans-serif;padding:40px 24px'>"
        "<h1 style='font-size:20px;margin:0 0 12px'>页面不存在</h1>"
        "<p style='color:#666'><a href='/' style='color:#1a73e8'>%s</a></p>"
        "</body></html>" % (t, t)
    )


def _render(meta, site_name):
    t = html.escape(meta["title"])
    d = html.escape(meta["desc"])
    u = html.escape(_abs(meta["canonical"]))
    sn = html.escape(site_name)
    h = html.escape(meta["heading"])
    ld = _json_ld_list(meta, site_name, _abs(meta["canonical"]))

    lis = []
    # 友链是外站：**必须 nofollow**。否则等于用自己的站点权重给任意外链背书，
    # 而友链是站长可编辑的（谁能保证每条都值得背书）。
    rel = " rel='nofollow noopener'" if meta.get("kind") == "links" else ""
    for url, title, summary in meta["items"]:
        eu = html.escape(_abs(url) if meta.get("kind") != "links" else (url or ""))
        et = html.escape(title or "（无标题）")
        es = html.escape(summary or "")
        lis.append(
            "<li style='margin:0 0 14px'><a href='%s'%s style='color:#1a73e8;"
            "font-size:16px;font-weight:600;text-decoration:none'>%s</a>"
            "%s</li>" % (eu, rel, et,
                         ("<div style='color:#666;font-size:14px'>%s</div>" % es) if es else "")
        )
    body = ("<ul style='list-style:none;padding:0;margin:16px 0'>" + "".join(lis) + "</ul>") if lis else ""

    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>%s</title>"
        "<meta name='description' content='%s'>"
        "<link rel='canonical' href='%s'>"
        "<meta property='og:type' content='website'>"
        "<meta property='og:site_name' content='%s'>"
        "<meta property='og:title' content='%s'>"
        "<meta property='og:description' content='%s'>"
        "<meta property='og:url' content='%s'>"
        "<meta name='twitter:card' content='summary'>"
        "<meta name='twitter:title' content='%s'>"
        "<meta name='twitter:description' content='%s'>"
        "%s"
        "</head><body style='margin:0;font-family:-apple-system,BlinkMacSystemFont,"
        "\"Segoe UI\",sans-serif'>"
        "<main style='max-width:760px;margin:0 auto;padding:16px'>"
        "<h1 style='margin:16px 0 8px'>%s</h1>"
        "<p style='margin:0;color:#666'>%s</p>"
        "%s"
        "<p style='margin:24px 0 0'><a href='/' style='color:#1a73e8'>%s</a></p>"
        "</main></body></html>"
        % (t, d, u, sn, t, d, u, t, d, ld, h, d, body, sn)
    )
