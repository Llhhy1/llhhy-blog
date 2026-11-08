# -*- coding: utf-8 -*-
"""v5.6.0 P3 · 设计系统收口守卫（三源合一 / 排版尺度 / 真实组合对比度）。

v5.3.3 审计点名的四条硬伤里，accent 自引用、代码块配色、元信息 3.81:1 已在
v5.3.4 修掉；本轮收剩下的：SSR 登录/错误页不引 tokens、字号尺度无棘轮、
「只校验 token 对、不校验真实页面组合」的对比度盲区、组件圆角打架。

本文件全部是静态文件断言 + 纯函数计算，不 import app、不连数据库。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "myblog" / "static"
SPA_CSS = ROOT / "vue-frontend" / "src" / "styles"

# v5.6.0 实施前实测：SPA 四份 CSS 里共 18 种 px 字号，当时只做「只许减不许增」的棘轮。
# v5.7.0 已把 CSS 里全部 px 字号迁到 13 级 --type-* 尺度（每处带兜底），
# 所以这里收紧为 0：任何新的 font-size: Npx 字面量都会立刻变红。
# 更完整的全库断言（含 Vue scoped / 后台 / SSR 与兜底值反查）见
# tests/test_typography_scale_v570.py。
FONT_SIZE_BASELINE = 0


def _lum(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    assert len(h) == 6, f"不是可计算的颜色: {hex_color}"

    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(fg, bg):
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_三套渲染面共享同一份tokens():
    admin = (STATIC / "admin.css").read_text(encoding="utf-8")
    assert '@import url("tokens.css")' in admin, "后台丢了 tokens 真相源"
    base = (ROOT / "myblog" / "templates" / "base.html").read_text(encoding="utf-8")
    i_tok = base.find("filename='tokens.css'")
    i_css = base.find("filename='style.css'")
    assert i_tok != -1, "SSR 登录/错误页没有引入 tokens.css"
    assert i_css != -1 and i_tok < i_css, "tokens.css 必须在 style.css 之前加载"
    spa = (SPA_CSS / "global.css").read_text(encoding="utf-8")
    assert '@import "./tokens.css"' in spa, "SPA 丢了 tokens 真相源"


def test_两份tokens变量集合与取值一致():
    def parse(p):
        t = p.read_text(encoding="utf-8")
        d = {}
        for m in re.finditer(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);", t):
            d.setdefault(m.group(1), []).append(m.group(2).strip())
        return d

    a = parse(STATIC / "tokens.css")
    b = parse(SPA_CSS / "tokens.css")
    assert set(a) == set(b), "两份 tokens.css 变量集合漂移"
    diff = [k for k in a if a[k] != b[k]]
    assert not diff, "两份 tokens.css 取值不一致：" + ", ".join(diff)


def test_真实页面组合的对比度达标():
    """不是校验 token 对，而是校验「.post-meta 灰字压 .post-card 白卡」这个真实组合。"""
    tok = (STATIC / "tokens.css").read_text(encoding="utf-8")
    m = re.search(r"--text-muted:\s*(#[0-9a-fA-F]{6})", tok)
    assert m, "tokens.css 里找不到 --text-muted"
    muted = m.group(1)
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    meta = re.search(r"\.post-meta\s*\{([^}]*)\}", css)
    assert meta, "style.css 里找不到 .post-meta 规则"
    assert "var(--text-muted" in meta.group(1), "元信息没走对比度达标的 token"
    assert "#999" not in meta.group(1), "元信息退回 2.85:1 的旧灰了"
    card = re.search(r"\.post-card\s*\{([^}]*)\}", css)
    assert card and "#fff" in card.group(1), "取不到文章卡真实底色"
    ratio = _ratio(muted, "#ffffff")
    assert ratio >= 4.5, f"元信息真实组合只有 {ratio:.2f}:1（需 4.5:1）"
    # 旧值留作反证：守卫若被误改成允许 #999，下面这条会立刻变红。
    assert _ratio("#999999", "#ffffff") < 4.5, "旧灰值本应不达标，别把门槛算反了"


def test_字号尺度棘轮只减不增():
    sizes = set()
    for p in SPA_CSS.glob("*.css"):
        # (?<![-\w])：排除 --theme-font-size: 15px 这类**变量定义**里的子串，
        # 它不是 font-size 声明（v5.7.0 实测不加会假报 1 种字号）。
        sizes |= set(re.findall(r"(?<![-\w])font-size\s*:\s*([0-9.]+)px",
                                p.read_text(encoding="utf-8")))
    assert len(sizes) <= FONT_SIZE_BASELINE, (
        f"字号从 {FONT_SIZE_BASELINE} 种涨到 {len(sizes)} 种：{sorted(sizes)}。"
        "新增字号请走 --type-* 尺度。"
    )


def test_章回新代码走typetoken():
    look = (SPA_CSS / "look.css").read_text(encoding="utf-8")
    m = re.search(r"P2 CHAPTER LANGUAGE LAYER BEGIN(.*?)P2 CHAPTER LANGUAGE LAYER END",
                  look, re.S)
    assert m
    block = m.group(1)
    assert len(re.findall(r"font-size:\s*var\(--type-", block)) >= 2, (
        "新增语言层没用 --type-* 尺度"
    )


def test_天气按钮与全局胶囊按钮不再打架():
    g = (SPA_CSS / "global.css").read_text(encoding="utf-8")
    m = re.search(r"\.weather-widget \.w-btn\s*\{([^}]*)\}", g)
    assert m, "找不到天气按钮规则"
    body = m.group(1)
    assert "6px" not in body, "天气按钮又退回方角了"
    assert "!important" not in body, "天气按钮不许靠 !important 盖过观感层"
    assert "var(--radius-pill)" in body, "天气按钮应复用统一胶囊圆角"
