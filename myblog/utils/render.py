# -*- coding: utf-8 -*-
"""Markdown 渲染与 HTML 白名单清洗（含正文渲染缓存与指纹）。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re
import bleach
import contextlib
from markdown import markdown

# ---------- HTML 清理（防 XSS）----------
# 文章/关于页的 Markdown 渲染结果会直接 innerHTML/v-html 进页面，
# 必须经过白名单清理，剥离 <script>、on* 事件属性、javascript: 等危险内容。
# v3.18.5：补齐表格标签——render_markdown 已开启 markdown 的 "tables" 扩展，
# 但白名单原先不含 table 系标签，strip=True 会把整张表格的标签连同排版一起剥掉
# （不报错，所以长期没被发现）。改本白名单必须同步 bump _RENDER_VERSION。
_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "img", "hr", "span", "del",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "colgroup", "col",
    # v4.14.0 视频播放：没有这两个标签，正文里的视频会被 strip=True 整个剥掉
    "video", "source",
}
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
    "th": ["colspan", "rowspan", "align", "scope"],
    "td": ["colspan", "rowspan", "align"],
    "col": ["span"],
    "colgroup": ["span"],
    # ⚠️ 只放「播放控制」类属性，`src` 由 `_img_to_video()` 生成，不接受作者手写外域
    "video": ["src", "poster", "controls", "preload", "playsinline", "loop", "muted",
              "width", "height"],
    "source": ["src", "type"],
    "*": ["class"],
}


# v4.14.0 视频：Markdown 里 `![](/static/uploads/x.mp4)` 会生成 `<img src=...mp4>`，
# 浏览器把它当裂图。清洗前先换成 `<video>` —— 这样才能「写图片语法，播放视频」。
_VIDEO_SRC_RE = re.compile(r"\.(?:mp4|m4v|mov|webm)(?:[?#].*)?$", re.I)


def _img_to_video(html):
    """把 src 指向视频文件的 `<img>` 换成 `<video controls>`。

    只认**视频后缀**，不碰普通图片；`src` 里的引号做转义，防止有人用
    `![](x.mp4" onerror="alert(1))` 这类写法在标签里注入属性
    —— 虽然 bleach 之后还会再洗一遍，但「构造合法 HTML」不该依赖下游兜底。

    `preload="metadata"` 而不是 `auto`：正文可能有多段视频，auto 会把整文件下下来
    拖垮首屏；metadata 只取时长/首帧尺寸。
    """
    if not html or "<img" not in html:
        return html

    def _repl(m):
        tag = m.group(0)
        sm = re.search(r'src\s*=\s*"([^"]+)"', tag)
        if not sm or not _VIDEO_SRC_RE.search(sm.group(1)):
            return tag
        src = sm.group(1).replace('"', "%22")
        return ('<video controls preload="metadata" playsinline src="%s"></video>' % src)

    return re.sub(r"<img\b[^>]*>", _repl, html)


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
    v4.14.0：清洗**前**先把「src 指向视频」的 img 换成 video，并把 video/source
             加进白名单 —— 顺序不能反，否则 video 标签会先被剥掉。
    v5.3.0：**相册卡片不在这里渲染**。卡片内容依赖相册当前数据（标题/封面/
             是否公开），而本函数的产出会被 `content_html` 缓存 —— 若在这里渲染，
             改一次相册标题就得让所有引用它的文章缓存失效，代价远大于收益。
             卡片由 `inject_album_cards()` 在缓存**之外**注入。
    """
    raw = markdown(content or "", extensions=["fenced_code", "tables"])
    return _upgrade_img_avif(clean_html(_img_to_video(raw)))


# ---------------------------------------------------------------- 相册卡片（v5.3.0）

# 写法：正文里**独占一段**写 `@album[slug]`（前后空行），渲染成一张「打开相册」的链接卡片。
#
# 为什么选 `@album[slug]` 而不是 `{% album "slug" %}` 之类：
#   * 手写成本最低 —— 只要记得 slug，8 个字符搞定，不用记属性名；
#   * `@` + 方括号在块级位置几乎不与正常正文冲突（不像 `$` / `%` 常用于正文）；
#   * Markdown 不会转义它（实测 `@album[xianguang]` → `<p>@album[xianguang]</p>`，
#     方括号后面没有 `(` 所以不会被当成链接语法）。
#
# 🔴 判据必须匹配 **Markdown 渲染后**的形态：独占一行会被包成
#    `<p>@album[slug]</p>`，不是裸的 `@album[slug]`。
#    第一版只写了 `^@album[...]$`，结果**一处都匹配不到**（卡片永远不出现）。
#    这两种形态都要认：`<p>` 包裹（正常路径）与行首（有人手写 HTML 的兜底）。
_ALBUM_CARD_RE = re.compile(
    r"<p>\s*@album\[\s*(?P<slug>[^\]\s]+)\s*\]\s*</p>"
    r"|^@album\[\s*(?P<slug2>[^\]\s]+)\s*\]\s*$",
    re.M,
)

# 卡片用到的 class 都在 `post-album-card` 命名空间下，避免与主题样式打架
_ALBUM_CARD_TPL = (
    '<div class="post-album-card" data-album-slug="{slug}">'
    '{cover_html}'
    '<div class="post-album-body">'
    '<div class="post-album-title">{title}</div>'
    '{summary_html}'
    '{meta_html}'
    '<a class="post-album-link" href="/album/{slug}">查看相册 →</a>'
    "</div>"
    "</div>"
)


def _esc(s):
    """HTML 转义（卡片里的所有动态文本必须过这一道）。"""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _album_card_html(album, cover_url=""):
    """生成一张相册卡片的 HTML。**所有动态内容都转义**，不接受任何 HTML 输入。"""
    cover_html = ""
    if cover_url:
        # 封面 URL 来自 media_asset.url（站内路径），仍做属性转义防引号截断
        cover_html = ('<img class="post-album-cover" src="%s" alt="%s" loading="lazy">'
                      % (_esc(cover_url), _esc(album.title or album.slug)))
    summary = (album.summary or "").strip()
    summary_html = ('<div class="post-album-summary">%s</div>' % _esc(summary[:100])
                    if summary else "")
    meta = []
    if getattr(album, "event_date", None):
        meta.append(_esc(album.event_date.isoformat()))
    if getattr(album, "location", ""):
        meta.append(_esc(album.location))
    meta_html = ('<div class="post-album-meta">%s</div>' % " · ".join(meta)) if meta else ""
    return _ALBUM_CARD_TPL.format(
        slug=_esc(album.slug),
        cover_html=cover_html,
        title=_esc(album.title or album.slug),
        summary_html=summary_html,
        meta_html=meta_html,
    )


def inject_album_cards(html):
    """把正文里的 `@album[slug]` 渲染成相册链接卡片。

    ## 为什么不放在 render_markdown() 里

    `render_markdown()` 的产出会被 `post.content_html` 缓存（指纹只认
    「渲染版本 | 正文 | HTML」）。若在这里渲染卡片，改一次相册标题/封面，
    所有引用它的文章缓存都不会失效 —— 表现为「相册改了，文章里的卡片还是旧的」。

    放在缓存之外（本函数由各出口在拿到 HTML 后调用），代价是每次请求多一次
    带索引的相册查询，换来卡片永远反映相册当前状态。文章正文的 Markdown 渲染
    （真正的 CPU 大头）仍然命中缓存。

    ## 安全

    - 卡片 HTML **完全由服务端生成**，动态内容一律 `_esc()` 转义；
    - **不经过 bleach**，也因此**不需要**扩大 `_ALLOWED_TAGS` ——
      作者可写的标签集保持不变（这是刻意的选择：扩大白名单会让作者能写 `<div>`，
      那是作者不该拥有的能力）；
    - **私密相册（is_public=0）不渲染成卡片**。文章可能是公开的而相册是私密的，
      若渲染出卡片就等于泄露「存在一个叫 X 的私密相册」。降级策略是整段移除；
    - 相册不存在 / slug 为空 / 无 app 上下文 → 同样整段移除，不留残缺标签。
    """
    if not html or "@album[" not in html:
        return html
    try:
        from models import Album, AlbumItem, MediaAsset, db
    except Exception:
        return re.sub(_ALBUM_CARD_RE, "", html)

    slugs = [m.group("slug") or m.group("slug2")
             for m in _ALBUM_CARD_RE.finditer(html)]
    slugs = [s for s in slugs if s]
    if not slugs:
        return html
    try:
        found = {a.slug: a for a in Album.query.filter(Album.slug.in_(slugs)).all()}
    except Exception:
        # 查询失败（无上下文/表不存在等）：宁可不显示卡片，也不能让正文渲染失败
        return re.sub(_ALBUM_CARD_RE, "", html)

    def _repl(m):
        slug = m.group("slug") or m.group("slug2")
        album = found.get(slug)
        # 私密相册：整段移除，不泄露存在性（也不写「相册不存在」之类提示）
        if album is None or not album.is_public:
            return ""
        cover_url = ""
        try:
            if album.cover_media_id:
                m_ = MediaAsset.query.get(album.cover_media_id)
                if m_:
                    cover_url = m_.url
            if not cover_url:
                # 没指定封面就取相册里第一张图片素材
                first = (db.session.query(MediaAsset)
                         .join(AlbumItem, AlbumItem.media_id == MediaAsset.id)
                         .filter(AlbumItem.album_id == album.id,
                                 MediaAsset.kind == "image")
                         .order_by(AlbumItem.sort.asc()).first())
                cover_url = first.url if first else ""
        except Exception:
            cover_url = ""
        return _album_card_html(album, cover_url)

    return _ALBUM_CARD_RE.sub(_repl, html)
# ---------- 正文渲染缓存（v3.9.1）----------
# Markdown 渲染 + bleach 清洗是 CPU 密集操作，长文单次可达数百毫秒；以前每次
# 打开文章、每次渲染首页列表都要重算一遍。这里把结果落到 post 表的 content_html
# 列，用正文指纹（sha256，混入渲染版本号）判断是否失效——正文一改指纹就变，
# 缓存自动失效，无需在保存文章的各处手工清理。
# 渲染版本号：若将来调整 Markdown 扩展或 clean_html 白名单，把 _RENDER_VERSION
# +1 即可让全部历史缓存一次性失效，避免旧 HTML 与新的白名单不一致。
# v3.18.5：2 → 3（白名单新增表格标签，必须让历史表格文章的旧缓存失效后重渲染）。
# v4.7.7：3 → 4（markdown 3.8.1 → 3.11.1）。**升级 markdown 库也算「渲染器变了」** ——
#   不 bump 的话，已缓存的 content_html 指纹依然匹配（指纹只认「版本|正文|HTML」），
#   于是老文章继续吐旧库渲染的 HTML，新文章用新库渲染，两套结果静默混着且不会报错。
# v4.14.0：4 → 5（白名单加 video/source + img→video 转换）。不加的话，
#   带视频的老文章会一直吐「旧的、视频已被剥掉」的缓存 HTML，表现为「改了代码但视频还是不见」。
_RENDER_VERSION = "5"


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

    v5.3.0：**相册卡片在取到 HTML 之后才注入**（`inject_album_cards`）。
    缓存里存的是**不含卡片**的纯 Markdown 渲染结果 —— 这样改相册标题/封面时
    不必让引用它的文章缓存失效，卡片永远反映相册当前状态。
    """
    content = post.content or ""
    cached = getattr(post, "content_html", None)
    if cached and getattr(post, "content_hash", None) == content_digest(content, cached):
        return inject_album_cards(cached)

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
                # v3.25.9：SIM105（ruff 不修 finally 内的写法，语义判定保守）。
                # 行为等价：busy_timeout 复原失败也必须继续走到 conn.close()。
                with contextlib.suppress(Exception):
                    conn.execute(_sql_text("PRAGMA busy_timeout=5000"))  # 归还连接池前复原
                conn.close()
    except Exception:  # noqa: S110  旁路/兜底路径，失败按降级处理，不影响主流程
        pass
    return inject_album_cards(html)
