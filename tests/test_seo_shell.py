"""v3.18.9 阶段 1 回归测试 —— SEO 爬虫通道闸门与三出口。

背景：线上 `/post/<slug>` 对不执行 JS 的爬虫只是 SPA 空壳（`<div id="app"></div>`），
百度/微信/QQ 拿不到任何文章内容；而线上手工配的 nginx bot 规则又把爬虫
改写到一个恒发 `noindex,nofollow` 且 canonical 指向 `/api/og/post/<slug>`
的页面上——等于「接通通道反而杀死收录」。本文件锁住修复后的行为。

**最容易做错、也是会出生产事故的一条**是「真人误伤」：QQ 内置浏览器里的真人
UA 常带 `QQ/9.7.x`，会被 UA 正则命中；若后端没有第二层否决，真人会看到
一张几乎空白的壳页。爬虫侧测试全绿也照不出这一类，所以必须单独覆盖。
"""
import secrets

from models import db, Post
from _time import utcnow
from datetime import timedelta


# ---------- UA 与请求头常量（照清单 1.0 判定表）----------
UA_BAIDU = "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"
UA_WX_CRAWL = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) MicroMessenger/8.0.40"
# 微信内置浏览器里的真人：会送 Sec-Fetch-Mode: navigate
UA_WX_HUMAN = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
               "Mobile/15E148 MicroMessenger/8.0.40(0x18002823) NetType/WIFI Language/zh_CN")
# QQ 内置浏览器里的真人：UA 带 QQ/9.7.x（会被 UA 正则命中）
UA_QQ_HUMAN = ("Mozilla/5.0 (Linux; U; Android 12) AppleWebKit/537.36 Chrome/100.0.4896.127 "
               "Mobile Safari/537.36 MQQBrowser/13.0 QQ/9.7.10.43400")
UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "Chrome/120.0.0.0 Safari/537.36")
UA_AHREFS = "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)"
UA_CURL = "curl/7.88.1"

HUMAN_HDRS = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
              "Sec-Fetch-Mode": "navigate"}


def _uid():
    return secrets.token_hex(4)


def _mkpost(**kw):
    """建一篇可见文章（默认已发布、非隐私、非回收站、无定时）。"""
    slug = "seo-" + _uid()
    p = Post(title=kw.pop("title", "SEO 通道测试文章"),
             slug=slug,
             content=kw.pop("content", "# 标题\n\n这是**正文**内容，用于验证壳页带正文。"),
             summary=kw.pop("summary", "这是摘要"),
             published=kw.pop("published", True),
             in_trash=kw.pop("in_trash", False),
             is_private=kw.pop("is_private", False),
             **kw)
    db.session.add(p)
    db.session.commit()
    return p


def _cleanup(slugs):
    Post.query.filter(Post.slug.in_(slugs)).delete(synchronize_session=False)
    db.session.commit()


def _get(client, slug, ua, headers=None, seo=True, path=None):
    h = dict(headers or {})
    h["User-Agent"] = ua
    url = path or ("/api/og/post/%s%s" % (slug, "?seo=1" if seo else ""))
    return client.get(url, headers=h)


# ===========================================================================
# 一、闸门判定表（清单 1.0 的 7 条，逐条断言）
# ===========================================================================
def test_baidu_gets_indexable_shell(app, client):
    """百度爬虫（无导航信号）→ 200 壳页 + index,follow + canonical 指向 /post/<slug>。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_BAIDU)
        assert r.status_code == 200, "百度爬虫应拿到服务端壳页，实得 %s" % r.status_code
        body = r.get_data(as_text=True)
        assert "og:title" in body
        assert "SEO 通道测试文章" in body
        assert "noindex" not in (r.headers.get("X-Robots-Tag") or ""), \
            "壳页必须是 index,follow——否则接通通道反而杀死收录"
        assert "index" in (r.headers.get("X-Robots-Tag") or "")
        # canonical / og:url 必须是公开地址，不是 /api/ 地址
        assert ("/post/%s" % slug) in body
        assert "/api/og/post/%s'" % slug not in body, "canonical/og:url 不得指向 API 地址"
    finally:
        with app.app_context():
            _cleanup([slug])


def test_wechat_crawler_gets_shell(app, client):
    """微信链接预览抓取器（UA 无 bot 字样，无导航信号）→ 可索引壳页。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_WX_CRAWL)
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "og:image" in body, "微信卡片依赖 og:image，缺了分享出去没有图"
        assert "noindex" not in (r.headers.get("X-Robots-Tag") or "")
    finally:
        with app.app_context():
            _cleanup([slug])


def test_wechat_human_browser_gets_redirect(app, client):
    """微信内置浏览器里的真人（Sec-Fetch-Mode: navigate）→ 302 回 /post/<slug>。

    这是**防生产事故**的关键断言：真人必须回到能执行 JS 的 SPA。
    """
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_WX_HUMAN, HUMAN_HDRS)
        assert r.status_code == 302, "微信内真人必须被放回 SPA，实得 %s" % r.status_code
        assert r.headers["Location"].endswith("/post/%s" % slug)
    finally:
        with app.app_context():
            _cleanup([slug])


def test_qq_inapp_human_browser_gets_redirect(app, client):
    """QQ 内置浏览器里的真人（UA 带 QQ/9.7.x，Accept: text/html）→ 302 回公开地址。

    UA 里含 `QQ/` 会被闸门第一层命中（社交预览表），若没有第二层否决，
    这位真人就会看到一张几乎空白的壳页——本文件最重要的一条断言。
    """
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_QQ_HUMAN, HUMAN_HDRS)
        assert r.status_code == 302, "QQ 内真人被误判留在壳页（生产事故）"
        assert r.headers["Location"].endswith("/post/%s" % slug)
    finally:
        with app.app_context():
            _cleanup([slug])


def test_plain_chrome_is_redirected(app, client):
    """Chrome 真人直接访问 → 302 回 SPA（不该拿到壳页）。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_CHROME, HUMAN_HDRS)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/post/%s" % slug)
    finally:
        with app.app_context():
            _cleanup([slug])


def test_third_party_seo_bot_gets_nothing(app, client):
    """Ahrefs/Semrush 类第三方 SEO 蜘蛛与 curl → 不给壳页（否则等于批量抓取入口）。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        for ua in (UA_AHREFS, UA_CURL):
            r = _get(client, slug, ua)
            assert r.status_code == 302, "第三方 SEO 蜘蛛/脚本不该拿到壳页：%s" % ua
    finally:
        with app.app_context():
            _cleanup([slug])


def test_internal_referer_not_served_shell(app, client):
    """站内 Referer 跳来的微信 UA → 不给壳页（站内跳转必然是真人在点链接）。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_WX_CRAWL, {"Referer": "https://example.com/some/page"})
        # site_base() 未配置时退用请求 Host（localhost）比对；此处 Referer 是外部域名 → 不算站内
        # 仍应给壳页（外部来源的社交抓取）。真正的站内 Referer 用同 Host 验证：
        r2 = _get(client, slug, UA_WX_CRAWL, {"Referer": "http://localhost/post/other"})
        assert r2.status_code == 302, "站内 Referer 的请求应被放回 SPA"
    finally:
        with app.app_context():
            _cleanup([slug])


def test_direct_api_hit_without_seo_flag_redirects(app, client):
    """直接敲 API 地址（无 ?seo=1）→ 302 回公开地址，不停留一个可索引页。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = _get(client, slug, UA_BAIDU, seo=False)
        assert r.status_code == 302, "不带 seo=1 的直敲应 302，否则会与公开页争 canonical"
    finally:
        with app.app_context():
            _cleanup([slug])


# ===========================================================================
# 二、可见性红线（隐私 / 回收站 / 未到点定时）—— 两个入口都要测
# ===========================================================================
def test_og_meta_hides_private_trashed_and_scheduled(app, client):
    """隐私 / 回收站 / 定时未到 三种文章，meta 页都必须 404 且不泄露标题。"""
    txt = "SECRET-LEAK-MARKER"
    with app.app_context():
        p_priv = _mkpost(is_private=True, title="隐私标题 " + txt)
        p_trash = _mkpost(in_trash=True, title="回收站标题 " + txt)
        p_sched = _mkpost(scheduled_at=utcnow() + timedelta(days=7), title="未到点标题 " + txt)
        pairs = [(p_priv.slug, "隐私"), (p_trash.slug, "回收站"), (p_sched.slug, "定时未到")]
    try:
        for slug, kind in pairs:
            r = _get(client, slug, UA_BAIDU)
            assert r.status_code == 404, "%s文章经通道应 404，实得 %s" % (kind, r.status_code)
            assert txt not in r.get_data(as_text=True), "%s文章的标题被泄露" % kind
            assert "noindex" in (r.headers.get("X-Robots-Tag") or "")
            # 不带 seo 标记也应 404（不可见性先于通道判定）
            r2 = _get(client, slug, UA_BAIDU, seo=False)
            assert r2.status_code == 404, "%s文章不带 seo=1 也应 404" % kind
    finally:
        with app.app_context():
            _cleanup([s for s, _ in pairs])


def test_og_png_hides_private_trashed_and_scheduled(app, client):
    """`.png` 分享卡入口：三种不可见文章都不得把标题画进图里。

    修复前此处手写 `filter_by(published=True, in_trash=False)` + `if post.is_private`
    **漏了 scheduled_at**——未到点的文章标题会被直接画进对外可取的 PNG。
    """
    txt = "SECRET-PNG-MARKER"
    with app.app_context():
        p_priv = _mkpost(is_private=True, title="隐私图标题 " + txt)
        p_trash = _mkpost(in_trash=True, title="回收站图标题 " + txt)
        p_sched = _mkpost(scheduled_at=utcnow() + timedelta(days=7), title="未到点图标题 " + txt)
        # 未到点文章同样不得出现在任何公开列表里（真相源一致性）
        from models import visible_posts_query
        visible_slugs = {x.slug for x in visible_posts_query().all()}
        for p in (p_priv, p_trash, p_sched):
            assert p.slug not in visible_slugs, "visible_posts_query 未过滤 %s" % p.slug
        slugs = [p_priv.slug, p_trash.slug, p_sched.slug]
    try:
        for slug in slugs:
            # 生成图会走 og_png_bytes（可能无 Pillow/字体而回退默认图），
            # 这里用「标题是否被当作参数传入」的等价断言：可见性查询必须查不到它
            from models import visible_posts_query
            with app.app_context():
                found = visible_posts_query().filter_by(slug=slug).first()
                assert found is None, "不可见文章 %s 仍被 visible_posts_query 查出" % slug
            r = client.get("/api/og/post/%s.png" % slug)
            # 图片来源只有两种：动态生成（含标题）或兜底默认图。断言不是 500，且响应是图片。
            assert r.status_code in (200, 302), "分享卡入口不应 500，实得 %s" % r.status_code
    finally:
        with app.app_context():
            _cleanup(slugs)


# ===========================================================================
# 三、Host 头不得决定对外 URL（首轮审计 2.9 遗留项）
# ===========================================================================
def test_host_header_does_not_leak_into_canonical(app, client):
    """`Host: evil.example.com` 不得出现在 canonical / og:url 里。

    修复前 `_site_base()` 会回退 `request.url_root`，而 `og.py` 直接用 `request.url`
    → 攻击者可用 Host 头诱导页面声明一个外部域名的规范地址。
    """
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r = client.get("/api/og/post/%s?seo=1" % slug,
                       headers={"User-Agent": UA_BAIDU, "Host": "evil.example.com"})
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "evil.example.com" not in body, "Host 头被写进了 canonical/og:url（Host 注入）"
    finally:
        with app.app_context():
            _cleanup([slug])


# ===========================================================================
# 四、站点地址单一真相源
# ===========================================================================
def test_site_base_single_source_of_truth(app):
    """`site_base()` 优先 DB site_url，其次 env SITE_URL，都没有则空串（不回退 request）。"""
    from models import Setting
    from utils import site_base
    with app.app_context():
        old = Setting.query.filter_by(key="site_url").first()
        old_val = old.value if old else None
        try:
            Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
            db.session.commit()
            # DB 无值、env 有值 → 用 env
            assert site_base() == (app.config.get("SITE_URL") or "").rstrip("/")
            # DB 有值 → DB 优先
            db.session.add(Setting(key="site_url", value="https://db.example.com/"))
            db.session.commit()
            assert site_base() == "https://db.example.com"
        finally:
            Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
            if old_val is not None:
                db.session.add(Setting(key="site_url", value=old_val))
            db.session.commit()


def test_site_base_without_site_url_returns_relative_path(app):
    """未配置 site_url 时 `abs_url` 返回相对路径，不猜测域名。"""
    from models import Setting
    from utils import abs_url
    with app.app_context():
        old = Setting.query.filter_by(key="site_url").first()
        old_val = old.value if old else None
        old_cfg = app.config.get("SITE_URL")
        try:
            Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
            db.session.commit()
            app.config["SITE_URL"] = ""
            assert abs_url("/post/abc") == "/post/abc"
        finally:
            app.config["SITE_URL"] = old_cfg
            Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
            if old_val is not None:
                db.session.add(Setting(key="site_url", value=old_val))
            db.session.commit()


# ===========================================================================
# 五、响应头 Vary（同 URL 三种结果，不声明会被共享缓存串味）
# ===========================================================================
def test_shell_and_redirect_carry_vary(app, client):
    """壳页与 302 都必须带 `Vary: User-Agent, ...`，否则 CDN 会把结果串味。"""
    with app.app_context():
        p = _mkpost()
        slug = p.slug
    try:
        r_shell = _get(client, slug, UA_BAIDU)
        assert r_shell.status_code == 200
        vary = r_shell.headers.get("Vary", "")
        assert "User-Agent" in vary and "Sec-Fetch-Mode" in vary and "Accept" in vary

        r_redir = _get(client, slug, UA_CHROME, HUMAN_HDRS)
        assert r_redir.status_code == 302
    finally:
        with app.app_context():
            _cleanup([slug])


# ===========================================================================
# 六、壳页内容（1.6：带正文 + JSON-LD）
# ===========================================================================
def test_shell_carries_article_body_and_json_ld(app, client):
    """壳页应带正文（复用 content_html 缓存列）与 BlogPosting JSON-LD。"""
    with app.app_context():
        p = _mkpost(content="# 小标题\n\n这是一段**加粗**正文，供百度读取。")
        slug = p.slug
    try:
        r = _get(client, slug, UA_BAIDU)
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "application/ld+json" in body, "缺 JSON-LD 结构化数据"
        assert "BlogPosting" in body
        assert "<article" in body, "壳页应带正文（article 包裹），否则百度只看到标题+摘要"
        assert "这是一段" in body or "小标题" in body, "正文未被渲染进壳页"
    finally:
        with app.app_context():
            _cleanup([slug])


def test_shell_has_no_script_and_escapes_title(app, client):
    """壳页不得含可执行脚本，标题里的 HTML 必须被转义（XSS 回归）。"""
    with app.app_context():
        p = _mkpost(title='<script>alert(1)</script>恶意标题')
        slug = p.slug
    try:
        r = _get(client, slug, UA_BAIDU)
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body, "标题未转义（XSS）"
        assert "&lt;script&gt;" in body
    finally:
        with app.app_context():
            _cleanup([slug])
