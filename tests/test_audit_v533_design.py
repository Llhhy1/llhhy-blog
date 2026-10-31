# -*- coding: utf-8 -*-
"""v5.3.4 设计系统守卫：把「看得见但容易被改回去」的配色/排版修复钉住。

对应 v5.3.3 审计的 6 个根因：
1. `--accent: var(--accent)` 自引用（CSS 循环，注入前品牌色全失效）；
2. 文章代码块深底配浅色高亮主题（深灰字压深灰底）；
3. 三个默认 accent 常量不一致（#1a73e8 vs #196ddd）；
4. 元信息 13px --text-faint 只有 3.81:1；
5. 标签 chip 文字只有 4.38:1；
6. SquareView / StatsView 的深色字面量在暗色模式下不翻转。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    vals = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        vals.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def _ratio(fg, bg):
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_no_self_referential_accent():
    """`--accent: var(--accent)` 会形成 CSS 循环，整条品牌色链失效。"""
    for rel in ("vue-frontend/src/styles/global.css", "myblog/static/style.css"):
        css = _strip_comments(_read(rel))
        assert "--accent: var(--accent)" not in css, rel
        assert "var(--accent, var(--accent))" not in css, rel


def test_post_code_block_matches_dark_highlight_theme():
    """正文 pre 是深底，highlight.js 必须是深色主题，否则字与底同色。"""
    vue = _read("vue-frontend/src/views/PostView.vue")
    assert 'highlight.js/styles/github-dark.css' in vue
    css = _read("vue-frontend/src/styles/global.css")
    assert re.search(r"\.post-body pre\s*\{[^}]*background:\s*#0d1117", css), \
        "pre 背景与 github-dark 的 #0d1117 不一致"


def test_accent_default_is_unified():
    """默认品牌色只允许一个值：改一处必须改全部，否则首屏会闪旧色。"""
    files = [
        "vue-frontend/src/store.js",
        "myblog/api/site.py",
        "myblog/app.py",
        "myblog/templates/base.html",
        "myblog/templates/admin/base.html",
        "myblog/templates/_error_base.html",
    ]
    for rel in files:
        assert "#1a73e8" not in _read(rel), "%s 仍在使用旧默认色 #1a73e8" % rel


def test_meta_and_tag_text_meet_wcag():
    """元信息与标签 text 的真实组合必须 >= 4.5:1。"""
    # 元信息：--text-muted 压 surface / surface-2 / 白
    assert _ratio("#6a717f", "#ffffff") >= 4.5
    assert _ratio("#6a717f", "#f4f6f8") >= 4.5
    # 标签：--text 压 rgba(120,120,128,.10) 叠白后的实际底色
    assert _ratio("#2c2c2c", "#f2f2f2") >= 4.5

    css = _read("vue-frontend/src/styles/look.css")
    m = re.search(r"\.post-meta\s*\{([^}]*)\}", css)
    assert m and "var(--text-muted" in m.group(1) and "var(--type-meta" in m.group(1), \
        ".post-meta 又回到 13px/faint 的低对比组合"
    m = re.search(r"\.tag-cloud \.tag\s*\{([^}]*)\}", css)
    assert m and "color: var(--text," in m.group(1), \
        ".tag-cloud .tag 又回到 --text-muted（chip 底上只有 4.38:1）"


def test_square_and_stats_have_no_known_dark_literals():
    """这两个页面此前有深色字面量且零暗色覆盖，用户实测「深色看不清」。"""
    sq = _read("vue-frontend/src/views/SquareView.vue")
    for bad in ("color: #1f1f1f", "color: #666", "color: #999", "color: #888"):
        assert bad not in sq, "SquareView 又出现写死深色：%s" % bad

    st = _read("vue-frontend/src/views/StatsView.vue")
    assert "color: #777" not in st, "StatsView 趋势图例又写死 #777"
    assert ".trend-legend" in st
    m = re.search(r"\.trend-legend\s*\{([^}]*)\}", st)
    assert m and "var(--text-muted" in m.group(1), \
        "StatsView 图例没有跟随主题 token"


def test_cover_subtitle_stays_white_on_image():
    """封面副标题压在渐变/照片上，不能用正文灰阶。"""
    css = _read("vue-frontend/src/styles/look.css")
    m = re.search(r"\.home-cover-sub\s*\{([^}]*)\}", css)
    assert m and "rgba(255, 255, 255" in m.group(1), \
        ".home-cover-sub 又变成灰字（压在图片/渐变上会糊掉）"
