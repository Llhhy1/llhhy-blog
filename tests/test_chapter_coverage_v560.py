# -*- coding: utf-8 -*-
"""v5.6.0 P2 · 「章回」全站语言层守卫。

背景：v5.5.0 的章回只在 ``HomeView.vue`` 有结构钩子，``global.css`` 的规则
全挂 ``:root[data-*]``，其余 23 个视图虽然也会收到属性、但自己写死颜色把它
盖掉了 —— 站主切到章回后，首页像章回、点进文章页立刻回到经典主题。

本文件钉死 P2 的四条不变量（都是**静态可验证**的，不依赖浏览器）：
1. 新增语言层的每一条选择器都以 ``:root[data-layout="chapter"]`` 开头 →
   经典主题 data-layout 不存在，整段零影响。
2. 首页暗色分卷必须被 ``:not(.zh-chapter-dark)`` 排除，否则 look.css（最后
   加载）会赢过 global.css 的横卡暗底规则，把卷一刷成纸白。
3. 分卷不再硬砍前 4 类、列数走 auto-fit；三个结构钩子确实落到视图里。
4. v5.5.0 的老契约没被顺手改坏：壁纸联动 18 处、cover 标题不新增规则、
   store.js 仍写 data-columns（自定义属性在 repeat() 计数位无效，见其注释）。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "vue-frontend" / "src"
LOOK = SRC / "styles" / "look.css"
GLOBAL = SRC / "styles" / "global.css"
BEGIN = "P2 CHAPTER LANGUAGE LAYER BEGIN"
END = "P2 CHAPTER LANGUAGE LAYER END"
PREFIX = ':root[data-layout="chapter"]'


def _block():
    text = LOOK.read_text(encoding="utf-8")
    m = re.search(re.escape(BEGIN) + r".*?\*/(.*?)/\*\s*====\s*" + re.escape(END),
                  text, re.S)
    assert m, "look.css 里找不到 P2 章回语言层标记块"
    return m.group(1)


def _selectors(block):
    """把块内每条规则的选择器组拆成单个选择器（去掉注释与规则体）。"""
    clean = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    out = []
    for chunk in clean.split("{")[:-1]:
        head = chunk.split("}")[-1]
        for sel in head.split(","):
            sel = sel.strip()
            if sel:
                out.append(sel)
    return out


def test_语言层存在且规则数足够():
    sels = _selectors(_block())
    assert len(sels) >= 30, f"语言层规则太少（{len(sels)}），疑似被截断"


def test_每条选择器都带章回前缀_经典主题零影响():
    sels = _selectors(_block())
    bad = [s for s in sels if not s.startswith(PREFIX)]
    assert not bad, "以下选择器会泄漏到经典主题：\n" + "\n".join(bad)


def test_语言层不新增断点与important():
    block = _block()
    assert "@media" not in block, "语言层不要自带断点，响应式沿用既有 820/520 规则"
    assert "!important" not in block, "语言层靠层叠顺序生效，不许用 !important 硬压"


def test_首页暗色分卷被排除():
    sels = _selectors(_block())
    # 只查会改卡片底色的 .post-card 规则；.post-detail 的眉标/标题排版
    # 只存在于文章页（首页根本没有 .post-detail），不会波及卷一。
    card_sels = [s for s in sels if ".post-card" in s]
    assert card_sels, "语言层没覆盖文章卡片"
    bad = [s for s in card_sels if ":not(.zh-chapter-dark)" not in s]
    assert not bad, "这些规则会覆盖首页卷一暗底：\n" + "\n".join(bad)


def test_分卷不再写死前四类():
    home = (SRC / "views" / "HomeView.vue").read_text(encoding="utf-8")
    assert "chapterCategories = computed(() => state.site.categories || [])" in home
    assert ".slice(0, 4)" not in home, "分卷又被砍回 4 类了"
    g = GLOBAL.read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))" in g


def test_三个结构钩子落地且共享判定存在():
    helper = SRC / "lib" / "chapter.js"
    assert helper.is_file(), "缺少 lib/chapter.js（章回判定的单一入口）"
    for rel in ("views/PostView.vue", "views/CategoryView.vue", "views/ArchiveView.vue"):
        t = (SRC / rel).read_text(encoding="utf-8")
        assert "chapterOn()" in t, f"{rel} 没用共享判定"
        assert "zh-page" in t, f"{rel} 没有章回结构钩子"
        assert "lib/chapter.js" in t, f"{rel} 没引共享判定"


def test_v550老契约未被改坏():
    g = GLOBAL.read_text(encoding="utf-8")
    # v5.5.0 CHANGELOG 记的是 19 处「:root:has(.home-cover.has-wall) 联动」，
    # 逐字统计当前磁盘是 18 处（另 1 处是注释里提到），按实测值守"不许减少"。
    assert g.count(":root:has(.home-cover.has-wall)") >= 18
    # look.css 自 v5.0.0 起就有一条 .home-cover-title 的排版规则（只改字重/行高，
    # 不碰颜色），它本身合法；要守的是「P2 新增块里不许再写一条」。
    assert ".home-cover-title" not in _block(), (
        "不许在章回语言层新增 cover 标题规则（白字守卫）"
    )
    store = (SRC / "store.js").read_text(encoding="utf-8")
    assert 'setAttribute("data-columns"' in store, "列数契约被改坏了"
