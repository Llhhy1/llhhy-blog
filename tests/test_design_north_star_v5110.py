# -*- coding: utf-8 -*-
"""v5.11.0 设计北极星守卫：把「平淡」变成可断言的线。

对应 DESIGN.md：
1. 唯一难忘元素 —— 主题包必须声明 `design.signature`，且必须出现在规格里（两处不漂移）。
2. 硬指标 1/2/3 —— 字号跳跃 ≥ 声明值、卷首必须不对称、朱砂至少落到 6 类元素。
3. 架构判定 §5 —— 内置包 `css` 必须为空（客户端注入会 FOUC），且规格里写明理由。

变异验证：把标题上限改小、把 inner 改回居中、把朱砂规则删到 5 条、给 css 塞一条规则，
四种改法都必须变红。
"""
import json
import re
from pathlib import Path

import theme_bundles as bundles

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "vue-frontend" / "src" / "styles" / "global.css"
LOOK = ROOT / "vue-frontend" / "src" / "styles" / "look.css"
TOKENS = ROOT / "vue-frontend" / "src" / "styles" / "tokens.css"
PACK = ROOT / "myblog" / "theme_packs" / "zhanghui.json"
SPEC = ROOT / "DESIGN.md"
SEG_MARK = "v5.10.0 · 章回视觉推到极致"
SEG_END = "v5.12.0 · 章回卷首精修"


def _read(p):
    return p.read_text(encoding="utf-8")


def _seg():
    """只取 v5.10.0 章回视觉段；v5.12.0 纸墨层由专属守卫统计，避免
    把新层的朱砂规则重复计入指标 3（去重选择器数）。"""
    return (_read(CSS).split(SEG_MARK, 1)[-1]
            .split(SEG_END, 1)[0].split("*/", 1)[-1])


def _pack():
    with open(PACK, encoding="utf-8") as f:
        return json.load(f)


def _hero_jump():
    """主标题 clamp 上限 ÷ 副标题字号 fallback —— 设计口径的「字号跳跃」。"""
    body = re.search(r"(?m)^\s*\.home-cover-title\s*\{([^}]*)\}", _read(CSS), re.S).group(1)
    top = int(re.search(r"font-size:\s*clamp\([^,]+,\s*[^,]+,\s*(\d+)px\)", body).group(1))
    sub = _seg()
    m = re.search(r"\.home-cover-sub\s*\{[^}]*font-size:\s*var\(--[\w-]+,\s*(\d+)px\)",
                  sub, re.S)
    assert m, "副标题字号不再走 var(--type-*, Npx) 惯例，跳跃无法度量"
    return top / int(m.group(1))


def test_规格文件存在且关键章节齐备():
    assert SPEC.exists(), "DESIGN.md 缺失——设计意图又散回 5703 行 CSS 里了"
    text = _read(SPEC)
    for section in ("调性承诺", "唯一难忘元素", "硬指标", "实测现状与缺口", "架构判定"):
        assert section in text, f"DESIGN.md 缺少「{section}」章节"
    assert "FOUC" in text, "必须写明主题包 css 会 FOUC 的理由，否则后人会顺手搬进去"


def test_主题包声明了唯一难忘元素且与规格一致():
    c, errors = bundles.validate_bundle(_pack())
    assert not errors, errors
    design = c["design"]
    assert design["tone"] in bundles.DESIGN_TONES
    sig = design["signature"]
    assert sig and len(sig) <= 60
    assert sig in _read(SPEC), "主题包 signature 与 DESIGN.md 不一致（两处漂移）"
    # 「唯一」：signature 是单值字符串，不允许用分隔符塞多个主角
    for sep in ("、", "；", ";", " / "):
        assert sep not in sig, f"signature 里出现分隔符 {sep!r}，说明想塞多个主角"


def test_卷首字号跳跃达到声明下限():
    design = bundles.validate_bundle(_pack())[0]["design"]
    jump = _hero_jump()
    assert jump >= design["type_jump_min"] >= 3.0, (
        f"字号跳跃 {jump:.2f}× < 声明 {design['type_jump_min']}×：主角又塌回配角量级"
    )


def test_卷首必须不对称():
    body = re.search(r"\.home-cover\.has-wall \.home-cover-inner\s*\{([^}]*)\}",
                     _read(CSS), re.S).group(1)
    assert "margin: 0 auto" not in body, "卷首退回居中对称，违反「有目的的不对称」"
    assert "left: 9vw" in body and "text-align: left" in body


def test_强调色落在至少四类结构元素():
    """指标口径是「去重选择器数」而不是出现次数：同一规则里重复引用不能刷指标。

    实测 4 类：印章实底 / 标题横线 / 更新箭头 / 卷号竖条 —— 每处都是结构性的，
    不加装饰性朱砂（那只会让 60-30-10 的 10 变廉价）。
    """
    seg = _seg()
    sels = {re.sub(r"\s+", " ", m.group(1)).strip()
            for m in re.finditer(r"([^{}]+)\{[^}]*var\(--accent", seg, re.S)}
    design = bundles.validate_bundle(_pack())[0]["design"]
    assert len(sels) >= 4, f"朱砂只落在 {len(sels)} 类元素上：{sorted(sels)}"
    assert design["accent_share"] >= 5


def test_卷号封面零数据依赖():
    seg = _seg()
    assert "counter-reset: catvol" in seg
    assert "content: counter(catvol, decimal-leading-zero)" in seg
    assert "cover" not in seg.split(".zh-cat-thumb", 1)[1][:400], "卷号封面不应依赖封面图字段"


def test_文章页标题对正文达到阅读级跳跃():
    """指标 1 的另一半：文章页是阅读发生的地方，标题必须明显大于正文。

    真实生效链（按 main.js 导入顺序 global → responsive → look）：look.css 最后写
    `.post-body { font-size: var(--type-md, 17px) }`，而 tokens.css 里 --type-md = 16px，
    故桌面正文 = 16px、标题 44px ⇒ **2.75×**（线上实测同值）。
    同时钉住 font-weight 不得 ≥600：OFL 子集只有 400 字重，提 weight 会合成粗体。
    """
    look = _read(LOOK)
    rule = re.search(r':root\[data-layout="chapter"\] \.zh-page-title\s*\{([^}]*)\}',
                     look, re.S)
    assert rule, "找不到章回文章页标题规则"
    body = rule.group(1)
    top = re.search(r"font-size:\s*clamp\([^,]+,[^,]+,\s*([\d.]+)px\)", body)
    assert top, "文章页标题不再用 clamp()，跳跃无法度量"

    post_body = re.search(r"(?m)^\.post-body\s*\{([^}]*)\}", look, re.S)
    assert post_body, "look.css 不再给 .post-body 定字号，口径变了要同步改这里"
    var = re.search(r"font-size:\s*var\(--type-md,\s*([\d.]+)px\)", post_body.group(1))
    assert var, ".post-body 字号不再走 var(--type-md)，请重新确认真实基准"
    tok = re.search(r"--type-md:\s*([\d.]+)px", _read(TOKENS))
    assert tok, "tokens.css 缺少 --type-md"
    base = float(tok.group(1))

    ratio = float(top.group(1)) / base
    assert ratio >= 2.2, (
        f"文章页 H1/正文 = {ratio:.2f}× < 2.2×：标题又和正文同级，读者找不到入口"
    )
    w = re.search(r"font-weight:\s*(\d+)", body)
    assert w and int(w.group(1)) < 600, "字体子集只有 400 字重，weight ≥600 会触发合成粗体"


def test_卷首字重同样不得触发合成粗体():
    """v5.12.0 补漏：原 :138 判据只扫文章页 .zh-page-title，
    卷首 .home-cover-title 的 800 长期漏网 —— 宋体子集只有 400 字重。
    章回专属覆盖必须是 400；全局 800 保留给其余 14 套无衬线主题（真实字重）。
    """
    css = _read(CSS)
    paper = css.split(SEG_END, 1)[-1]
    m = re.search(
        re.escape(':root[data-layout="chapter"] .home-cover.has-wall .home-cover-title')
        + r"\s*\{([^}]*)\}", paper, re.S)
    assert m, "找不到章回卷首的纸墨层字重覆盖规则"
    w = re.search(r"font-weight:\s*(\d+)", m.group(1))
    assert w and int(w.group(1)) < 600, (
        "章回卷首回到 800 合成假粗体：宋体笔画会被机械加粗，主角反而发闷"
    )
    base = re.search(r"(?m)^\s*\.home-cover-title\s*\{([^}]*)\}", css, re.S)
    assert base and "font-weight: 800" in base.group(1), (
        "全局 800 被连坐删除：其余主题的无衬线栈需要真实粗体"
    )


def test_内置包css必须为空避免首屏闪烁():
    """§5 取证：`#site-bundle-css` 在模板与构建产物中都不存在，是 /api/site 之后
    createElement 出来的 —— 首屏视觉语言放进 css 必然 FOUC。"""
    assert bundles.validate_bundle(_pack())[0]["css"] == "", (
        "内置章回包的 css 被填了内容：它只会在首屏后注入，造成样式跳变。"
        "首屏视觉请写进 global.css（见 DESIGN.md §5）"
    )
    for rel in ("vue-frontend/index.html", "myblog/templates/base.html"):
        p = ROOT / rel
        if p.exists():
            assert "site-bundle-css" not in _read(p), (
                f"{rel} 出现了 SSR 注入点——若改为服务端渲染，DESIGN.md §5 需要重写"
            )
