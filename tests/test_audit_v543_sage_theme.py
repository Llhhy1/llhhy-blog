# -*- coding: utf-8 -*-
"""v5.4.x 主题「青野」的落地守卫。

这一档的坑不在算法，在**接线**：token 定义了但没人消费、字体写了 `<link>` 但产物
不在库里、白字规则没限定作用域 —— 三种都会「测试全绿而线上没效果」。
所以本文件钉的是接线，而不是色值本身（色值由 test_wcag_contrast /
test_all_presets_pass_own_whitelist 覆盖）。
"""
import pathlib
import re

import pytest
from themes import PRESET_MAP, _BASE_LIGHT

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAGE = "sage-sand"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _css(rel):
    """去掉注释后的 CSS —— 解释性注释里提到坏值（#6aa9ff）不算回归，别跟自己打。"""
    return re.sub(r"/\*.*?\*/", "", _read(rel), flags=re.S)


def _lum(hx):
    hx = hx.lstrip("#")
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)

    def ch(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    vals = [ch(int(hx[i:i + 2], 16) / 255) for i in (0, 2, 4)]
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def _ratio(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


# ---------- 1. 预设本身 ----------

def test_sage_preset_exists_and_is_readable():
    assert SAGE in PRESET_MAP, "「青野」预设没了"
    lt = PRESET_MAP[SAGE]["light"]
    # 主色不能用最浅那档鼠尾草 #7ea774：白字压它只有 2.74:1，过不了自家 WCAG 门禁。
    assert lt["accent"] != "#7ea774"
    assert _ratio("#ffffff", lt["accent"]) >= 4.5, "按钮白字压不住主色"
    assert _ratio(lt["accent"], lt["bg"]) >= 4.5, "主色当链接文字压不住页面底"
    assert _ratio(lt["accent"], lt["surface_2"]) >= 4.5, "主色当链接文字压不住卡片底"
    # 浅鼠尾草原色必须还在，但只作为 wash —— 这套配色的观感来源就在这一条上
    assert "126,167,116" in lt["accent_soft"], "鼠尾草绿原色没留在 wash 里"


def test_sage_preset_switches_the_font_family():
    lt = PRESET_MAP[SAGE]["light"]
    assert lt["font_sans"] != _BASE_LIGHT["font_sans"], "衬线包没换字体栈"
    assert "KingHwaOldSong" in lt["font_sans"]
    # 回落链要真能回落：缺字体时不能掉成无衬线（那样整站观感突变）
    tail = lt["font_sans"].rsplit(",", 1)[-1].strip()
    assert tail == "serif", "字体栈末尾不是 serif，回落会变成无衬线"
    assert lt["line_height_base"] != _BASE_LIGHT["line_height_base"]


# ---------- 2. token 真的被 CSS 消费（曾经的死键） ----------

@pytest.mark.parametrize("tok,css_var", [
    ("font_sans", "--font-sans"),
    ("line_height_base", "--line-height-base"),
    ("accent_soft", "--accent-soft"),
])
def test_theme_tokens_are_consumed_by_css(tok, css_var):
    """token 定义了但没人读 = 改了个寂寞。v5.4.x 之前 `font_sans`/`line_height_base`
    就是这样的死键：body 里写死了系统字体栈和 1.7。"""
    css = _css("vue-frontend/src/styles/global.css")
    body = re.search(r"\nbody\s*\{(.*?)\}", css, re.S)
    assert body, "global.css 里找不到 body 规则"
    assert ("var(%s" % css_var) in body.group(1), \
        "body 没有消费 %s（%s 又变回写死值）" % (css_var, tok)


def test_font_link_and_csp_agree():
    """前台挂了自托管字体的 `<link>`，而 CSP 必须允许 `'self'` —— 两边任缺其一，
    字体都不会生效（而且不报错，只是悄悄回落）。"""
    html = _read("vue-frontend/index.html")
    assert "/static/fonts/kinghua.css" in html, "index.html 没挂自托管字体 CSS"
    sec = _read("myblog/security.py")
    m = re.search(r"font-src([^;\"]*)", sec)
    assert m and "'self'" in m.group(1), "CSP font-src 不放 'self'，本地字体加载不了"


def test_generated_font_assets_stay_out_of_git():
    """503 个分片 ≈ 24.8 MB：必须被 .gitignore 挡住，否则仓库永久背二进制。"""
    gi = _read(".gitignore")
    assert "myblog/static/fonts/kinghua/" in gi
    assert "myblog/static/fonts/kinghua.css" in gi
    # 但只忽略这两条路径 —— 整个 fonts/ 目录里还有入库的 og:image 字体与说明
    assert "myblog/static/fonts/\n" not in gi, "不能忽略整个 fonts/ 目录"
    script = _read("tools/fetch_kinghua_font.py")
    assert "--check" in script, "脚本要能校验分片是否齐全（部署后唯一的自检入口）"


def test_fetch_css_rewrite_is_idempotent():
    """重跑脚本必须得到同一个 CSS；`--check` 读的是**改写后**的文件，
    正则只认官方原始路径的话会数出 0 个分片并「报就绪」（本轮实际踩过）。"""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from fetch_kinghua_font import URL_RE, build_css
    official = ('@font-face{font-family:"KingHwaOldSong";'
                'src:url("./0179f5045a40e044.woff2") format("woff2")}')
    once, patched = build_css(official)
    twice, _ = build_css(once)
    assert patched == 1 and "font-display: swap" in once
    assert URL_RE.findall(once) == URL_RE.findall(twice) == ["0179f5045a40e044.woff2"]
    assert twice == once, "改写不稳定"
    assert "kinghua/kinghua" not in once


# ---------- 3. 首屏配色的作用域 ----------

def test_post_links_follow_the_theme():
    """正文链接必须吃主题色。v5.4.x 走查实测 `.post-body a` 只有断行规则、**没有颜色**，
    于是任何主题下链接都是浏览器默认的 rgb(0,0,238) —— 绿底上一排蓝字。"""
    css = _css("vue-frontend/src/styles/global.css")
    m = re.search(r"\.post-body a\s*\{([^}]*)\}", css)
    assert m, "global.css 里没有 .post-body a 的颜色规则"
    assert "var(--accent" in m.group(1), "正文链接又回到默认蓝色"
    # 打印态仍然要是黑字（!important 在后，允许共存）
    assert re.search(r"\.post-body a\s*\{\s*color: #000 !important", css)


def test_no_live_blue_literals_in_spa_styles():
    """写死的蓝色（`#6aa9ff` / `rgba(25,109,221,…)`）在非蓝预设上会露出「另一套配色」。

    v5.4.x 换「青野」时才暴露：焦点环、抽屉 hover、热门标签 hover、首页横幅渐变
    等 8 处一直硬编码蓝色 —— 换成绿主色后它们是**绿底上的蓝边**。
    唯一允许出现的形式是 `var(--x, <兜底值>)` 的兜底位（只在 token 缺失时生效）。
    """
    blue = re.compile(r"#6aa9ff|rgba\(25,\s*109,\s*221", re.I)
    one_level = re.compile(r"var\((?:[^()]|\([^()]*\))*\)")
    bad = []
    for rel in ("vue-frontend/src/styles/global.css",
                "vue-frontend/src/styles/look.css",
                "vue-frontend/src/styles/responsive.css"):
        for line in _css(rel).splitlines():
            if not blue.search(line):
                continue
            if blue.search(one_level.sub("", line)):
                bad.append("%s: %s" % (rel, line.strip()[:100]))
    assert not bad, "出现写死蓝色：\n" + "\n".join(bad)


def test_cover_white_text_is_scoped_to_wallpaper():
    """无壁纸首屏是「浅 wash + 深字」，白字规则必须全部限定在 `.has-wall` 下。"""
    css = _css("vue-frontend/src/styles/global.css")
    assert "#6aa9ff" not in css, "首屏渐变又写回蓝色专属的 #6aa9ff"
    blocks = re.findall(r"([^{}]*)\{(.*?)\}", css, re.S)
    for sel, body in blocks:
        sel = sel.strip().splitlines()[-1].strip()
        if re.search(r"\.home-cover-title\s*$", sel) and ".has-wall" not in sel:
            assert "var(--text)" in body, "无壁纸首屏标题又变回白字（白压浅底＝没字）"
