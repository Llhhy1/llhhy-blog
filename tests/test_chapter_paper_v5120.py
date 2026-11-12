# -*- coding: utf-8 -*-
"""v5.12.0 章回卷首精修（按主题分流）静态守卫。

钉住的是**分流语义**而不是像素值：
- 章回 = 纸墨（宋体 400 / 墨字 / 细线），其余 14 套主题保留满屏壁纸 + 白字 + 粗线；
- 保留 .has-wall class，只覆盖视觉层，JS 壁纸变量链路不许改；
- 纸底上顶栏必须可读，手机端印章不许压住眉标；
- 动效两档兜底齐全。

断言一律写「每一条都」，避免 v5.11.1 M4 那种「至少一条」漏抓。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "vue-frontend" / "src" / "styles" / "global.css"
HOME = ROOT / "vue-frontend" / "src" / "views" / "HomeView.vue"
MAIN = ROOT / "vue-frontend" / "src" / "main.js"
SEG_MARK = "v5.12.0 · 章回卷首精修"
SEG_END = "v5.12.0 CHAPTER PAPER LAYER END"
CH = ':root[data-layout="chapter"]'


def _css():
    return CSS.read_text(encoding="utf-8")


def _seg():
    t = _css()
    assert SEG_MARK in t, "找不到 v5.12.0 纸墨层起始标记"
    assert SEG_END in t, "找不到 v5.12.0 纸墨层结束标记"
    return t.split(SEG_MARK, 1)[-1].split(SEG_END, 1)[0]


def _code(seg=None):
    return re.sub(r"/\*.*?\*/", "", seg if seg is not None else _seg(), flags=re.S)


def _rule(seg, selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", seg, re.S)
    assert m, f"找不到规则：{selector}"
    return m.group(1)


def test_分流段边界完整且不与旧段混算():
    seg = _seg()
    assert "@keyframes seal-drop" in seg
    assert "v5.10.0" not in seg, "新段误把 v5.10.0 旧段包进来"
    assert len(seg) > 1000, "纸墨层被删得只剩骨架"


def test_每一条卷首覆盖规则都带章回前缀():
    """无前缀规则会连带改掉另外 14 套主题 —— 这是分流最容易破的地方。"""
    code = _code()
    # 🔴 必须按逗号拆成**单条**选择器：多选择器规则里只删第一条的前缀时，
    # 按整块判定会因同块第二条仍带前缀而漏抓（v5.12.0 变异验证实测踩过）。
    sels = []
    for block in re.findall(r"([^{}]+)\{", code):
        sels.extend(p.strip() for p in block.split(",") if p.strip())
    targets = [s for s in sels if ".home-cover.has-wall" in s or ":has(" in s]
    assert targets, "新段一条卷首覆盖规则都没有"
    offenders = [s for s in targets if CH not in s]
    assert not offenders, f"以下选择器缺章回前缀，会污染其他主题：{offenders}"


def test_卷首宋体不再触发合成粗体():
    body = _rule(_seg(), f"{CH} .home-cover.has-wall .home-cover-title")
    assert re.search(r"font-weight:\s*400\b", body), "章回卷首仍是 800 合成假粗体"
    assert "800" not in body
    assert "letter-spacing: -.012em" in body, "负字距仍是挤在一起的 -.035em"
    assert "text-shadow: none" in body, "图上白字的双层阴影没去掉"
    assert "var(--zh-paper-fg" in body, "没回到纸墨色"


def test_全局基础规则保留给其他十四套主题():
    css = _css()
    base = re.search(r"(?m)^\s*\.home-cover-title\s*\{([^}]*)\}", css, re.S)
    assert base and "font-weight: 800" in base.group(1), (
        "全局 800 被删：其他 14 套用无衬线栈，那是真实字重，不该被章回连坐"
    )
    after = re.search(r"\.home-cover\.has-wall \.home-cover-title::after\s*\{([^}]*)\}", css, re.S)
    assert after and "height: 8px" in after.group(1), (
        "全局 8px 粗横线被删：其余主题的卷首视觉必须原样保留"
    )
    veil = re.search(r"(?m)^\s*\.home-cover\.has-wall\s*\{([^}]*)\}", css, re.S)
    assert veil and "--wall-veil" in veil.group(1), "壁纸遮罩链路被拆"


def test_章回细线降为一像素():
    body = _rule(_seg(), f"{CH} .home-cover.has-wall .home-cover-title::after")
    assert "height: 1px" in body and "width: 88px" in body, "朱砂粗横线仍是色块，没降回排印细线"


def test_纸底成立且顶栏不再用图上白字():
    seg, code = _seg(), _code()
    cover = _rule(seg, f"{CH} .home-cover.has-wall")
    assert "background-color: var(--zh-paper" in cover, "章回卷首没切到纸底"
    assert "background-attachment: scroll" in cover
    before = _rule(seg, f'{CH}:has(.home-cover.has-wall) .site-header::before')
    assert "background: transparent" in before, "黑色顶栏遮罩还压在纸底上"
    assert "color: #fff" not in code, "纸底上仍有白字规则"
    assert "text-shadow: 0 1px" not in code, "图上白字的文字阴影残留"
    nav_rules = [s.strip() for s in re.findall(r"([^{}]+)\{", code) if ":has(" in s]
    nav_targets = [s for s in nav_rules if ".logo" in s or "nav > a" in s or "toggle" in s]
    base = [s for s in nav_targets if ":hover" not in s]
    hover = [s for s in nav_targets if ":hover" in s]
    assert base and all("var(--zh-paper-fg" in _rule(seg, s) for s in base), (
        "并非每一条顶栏基础色都换成了墨色"
    )
    assert hover and all("var(--zh-seal" in _rule(seg, s) for s in hover), (
        "并非每一条顶栏 hover 都换成了朱砂"
    )


def test_手机端印章横排且底部避开安全区():
    seg = _seg()
    m = re.search(r"@media \(max-width: 640px\)\s*\{(.*?)\n\}", seg, re.S)
    assert m, "找不到手机端 640 断点块"
    mobile = m.group(1)
    badge = _rule(mobile, f"{CH} .home-cover.has-wall .zh-hero-badge")
    assert "position: static" in badge and "writing-mode: horizontal-tb" in badge, (
        "窄屏印章仍是 absolute 竖排，会压住眉标小字"
    )
    assert "animation: none" in badge, "窄屏横印不该再播落印"
    assert "env(safe-area-inset-bottom" in mobile, "底部信息没避开 iPhone 安全区"
    line = _rule(mobile, f"{CH} .home-cover.has-wall .home-cover-title::after")
    assert "width: 64px" in line, "窄屏细线没收短"


def test_动效两档兜底每一条都在():
    code = _code()
    assert "@keyframes seal-drop" in code, "落印动效被删"
    assert f'{CH}[data-motion="off"]' in code, "缺 off 档兜底"
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", code, re.S)
    assert m, "缺系统减弱动效兜底"
    off = re.search(re.escape(f'{CH}[data-motion="off"] .home-cover.has-wall .zh-hero-badge')
                    + r"\s*\{([^}]*)\}", code, re.S)
    assert off and "animation: none" in off.group(1), "off 档没关掉落印"
    for block in (m.group(1), off.group(1)):
        assert "animation: none" in block, "减弱动效下仍会播落印"


def test_壁纸变量注入链路未被拆():
    home = HOME.read_text(encoding="utf-8")
    for needle in ('"--wall-veil": veil', '"--wall-light": light', '"--wall-dark": dark',
                   "wallpaperUrl", "veilOpacity.value"):
        assert needle in home, f"HomeView.vue 少了 {needle}：其余主题壁纸/后台滑块会失效"


def test_三行CSS导入未被改动():
    imports = re.findall(r'import\s+["\']\./styles/([^"\']+\.css)["\']',
                         MAIN.read_text(encoding="utf-8"))
    assert imports == ["global.css", "responsive.css", "look.css"], "新建了 CSS 文件"
