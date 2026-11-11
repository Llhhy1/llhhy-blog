"""v5.11.1 · 列表页章回页首覆盖守卫

为什么需要这一组：
v5.10.0 把首页卷首推到 118px、v5.11.0 把文章页 H1 放大到 2.75×，两轮都在解决
「没有主角」。但**列表页被漏掉了**——分类页和归档页有 zh-page-head，标签页、
热门标签、搜索、系列列表、系列详情、年度、统计共 7 个页面只有裸 .page-title，
切主题后像两个不同的网站。而且已覆盖的两页是**居中 + 灰色计数胶囊**，
跟首页刚立的「左对齐破格 + 朱砂」是相反的调性。

这一组守卫把「页首覆盖面」和「调性方向」都钉死，防的是：
- 新增页面时忘了加 zh-page-head（退回裸 page-title）
- 有人图省事把 .zh-page-head 改回居中（首页破格的努力当场作废）
- 计数胶囊退回灰色（「朱砂计数」名不副实）
- 卷内序号泄漏到首页暗色横卡区
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEWS = ROOT / "vue-frontend" / "src" / "views"
LOOK = ROOT / "vue-frontend" / "src" / "styles" / "look.css"
BUNDLES = ROOT / "myblog" / "theme_bundles.py"
PACK = ROOT / "myblog" / "theme_packs" / "zhanghui.json"

# 列表 / 索引类页面：都必须有章回页首结构（文章页 PostView 走自己的 eyebrow + 标题，
# 不在本表里）。
LIST_VIEWS = (
    "CategoryView.vue",
    "ArchiveView.vue",
    "TagView.vue",
    "HotTagsView.vue",
    "SearchView.vue",
    "SeriesView.vue",
    "SeriesDetailView.vue",
    "AnnualView.vue",
    "StatsView.vue",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def _block(text, selector):
    """取某条规则的大括号内容；找不到返回 None。"""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text, re.S)
    return m.group(1) if m else None


def test_所有列表页都有章回页首结构():
    missing = []
    for name in LIST_VIEWS:
        p = VIEWS / name
        assert p.exists(), f"{name} 不存在，守卫名单该更新了"
        if "zh-page-head" not in _read(p):
            missing.append(name)
    assert not missing, "以下页面缺 zh-page-head（只有裸 page-title）：%s" % ", ".join(missing)


def test_列表页同时保留经典分支():
    """章回结构必须挂在 chapterOn() 上，v-else 保留原 page-title。
    否则未启用章回主题的站点会被强行套章回样式。"""
    bad = []
    for name in LIST_VIEWS:
        text = _read(VIEWS / name)
        if "chapterOn()" not in text:
            bad.append("%s: 无 chapterOn() 判断" % name)
        elif "page-title" not in text and "zh-page-title" not in text:
            bad.append("%s: 无任何标题" % name)
    assert not bad, "\n".join(bad)


def test_页首块必须左对齐不得居中():
    """首页卷首是 left:9vw 的破格左对齐。列表页若居中，
    同一个站在两屏之间会换一次对齐方式 —— 这是调性断裂，不是风格选择。"""
    block = _block(_read(LOOK), ':root[data-layout="chapter"] .zh-page-head')
    assert block, "找不到 .zh-page-head 规则"
    assert "text-align: center" not in block, (
        ".zh-page-head 又居中：首页已立左对齐破格，列表页居中会让调性断裂"
    )
    assert re.search(r"text-align:\s*left", block), ".zh-page-head 没有显式左对齐"
    assert "margin: 0 auto" not in block, ".zh-page-head 用 auto 外边距会重新居中"


def test_计数胶囊必须是实底朱砂():
    """原实现是 --zh-paper-muted 的灰描边胶囊，与「朱砂计数」的声明不符。
    实底而非描边：不依赖底色，明暗两套对比度都 ≥6:1。"""
    block = _block(_read(LOOK), ':root[data-layout="chapter"] .zh-page-seal')
    assert block, "找不到 .zh-page-seal 规则"
    assert "var(--zh-seal" in block, "计数胶囊没用朱砂 token"
    assert re.search(r"background:\s*var\(--zh-seal", block), (
        "计数胶囊不是实底朱砂（描边+灰字会退回「名不副实」）"
    )
    assert "--zh-paper-muted" not in block, "计数胶囊又用回灰色 muted"


def test_卷内序号被锁在纸白区():
    """首页暗色横卡区也用 PostCard，序号若泄漏过去，
    会在深色横卡右上角叠一个淡朱砂数字，像脏点。

    判据必须是「**每一条**带 counter 的规则都隔离了暗色区」——
    第一版只查「至少有一条带 :not()」，把 counter-increment 那条的
    :not() 删掉后 ::before 那条还在，断言照样绿（M4 变异漏抓）。
    """
    css = _read(LOOK)
    assert re.search(r"counter\(cardno, decimal-leading-zero\)", css), (
        "序号没用 decimal-leading-zero，1 会显示成 1 而不是 01"
    )

    # 按规则块切：每条含 cardno 的规则，其选择器都必须带 :not(.zh-chapter-dark)
    bad = []
    for chunk in css.split("}"):
        if "cardno" not in chunk:
            continue
        selector = chunk.rsplit("{", 1)[0]
        # 只保留最后一条选择器（可能有逗号分组或前置注释）
        tail = [s.strip() for s in selector.split("\n") if s.strip()]
        sel = tail[-1] if tail else ""
        if ":not(.zh-chapter-dark)" not in sel:
            bad.append(sel[:90])
    assert not bad, "以下含 cardno 的规则没隔离首页暗色区，序号会漏到深色横卡上：\n" + "\n".join(bad)
    assert css.count("cardno") >= 3, "序号三件套（reset / increment / content）缺项"

    before = re.search(
        r':root\[data-layout="chapter"\][^{]*\.post-card::before\s*\{([^}]*)\}', css, re.S)
    assert before, "找不到 .post-card::before 序号规则"
    body = before.group(1)
    assert "var(--zh-seal-wash" in body, "序号不是淡朱砂，会与标题抢注意力"
    assert "pointer-events: none" in body, "序号会挡住卡片点击"


def test_文章页保持居中():
    """列表页左对齐 ≠ 全站左对齐。阅读页标题居中更稳，
    PostView 没有 zh-page-head 容器，靠这条独立规则。"""
    block = _block(_read(LOOK), ':root[data-layout="chapter"] .post-detail h1.zh-page-title')
    assert block, "找不到文章页标题规则"
    assert "text-align: center" in block, "文章页标题被改成左对齐了（阅读页应保持居中）"


def test_眉标键可由主题包声明():
    """7 个新页面的眉标不能死写在模板里，否则换主题时改不了。
    与 design 契约同思路：可声明 + 有回退。"""
    keys = re.search(r"LABEL_KEYS\s*=\s*\(([^)]*)\)", _read(BUNDLES), re.S)
    assert keys, "找不到 LABEL_KEYS"
    declared = re.findall(r'"([a-z_]+)"', keys.group(1))
    for k in ("tags_en", "search_en", "series_en", "annual_en", "stats_en"):
        assert k in declared, f"LABEL_KEYS 缺 {k}，主题包写了也会被静默丢弃"

    import json
    labels = json.loads(_read(PACK)).get("labels", {})
    for k in ("tags_en", "search_en", "series_en", "annual_en", "stats_en"):
        assert labels.get(k), f"章回包 labels 未声明 {k}"


def test_新页面的眉标都有回退值():
    """主题包未激活 / 旧包无该键时，模板必须有 || 'XXX' 兜底，
    不能显示 undefined。"""
    bad = []
    for name in ("TagView.vue", "HotTagsView.vue", "SearchView.vue",
                 "SeriesView.vue", "SeriesDetailView.vue",
                 "AnnualView.vue", "StatsView.vue"):
        text = _read(VIEWS / name)
        m = re.search(r"chapterLabels\(\)\.(\w+)\s*\|\|", text)
        if not m:
            bad.append(f"{name}: 眉标无 || 回退")
    assert not bad, "\n".join(bad)
