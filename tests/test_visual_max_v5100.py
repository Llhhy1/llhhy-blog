"""v5.10.0 · 章回视觉推到极致（方向 A）静态守卫。

钉住的是**设计决策本身**，不是实现细节：一个主角、不对称、朱砂强调、
分卷卷号封面、read-more 对比度修复；并守住「不新建 CSS 文件 / 不新增断点」。
变异验证：把主标题上限改回 44px 或去掉 read-more 的暗色区作用域，守卫必须变红。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "vue-frontend" / "src" / "styles" / "global.css"
HOME = ROOT / "vue-frontend" / "src" / "views" / "HomeView.vue"
MAIN = ROOT / "vue-frontend" / "src" / "main.js"
SEG_MARK = "v5.10.0 · 章回视觉推到极致"
SEG_END = "v5.12.0 · 章回卷首精修"


def _read(p):
    return p.read_text(encoding="utf-8")


def _seg():
    """只取 v5.10.0 新增视觉段；v5.12.0 起的纸墨层是独立层，由
    test_chapter_paper_v5120.py 单独守卫，不并入本段统计（否则新层的
    @media 会被「不新增断点」误判、朱砂选择器会被重复计数）。"""
    return _read(CSS).split(SEG_MARK, 1)[-1].split(SEG_END, 1)[0]


def _lum(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def _ratio(a, b):
    hi, lo = max(_lum(a), _lum(b)), min(_lum(a), _lum(b))
    return (hi + 0.05) / (lo + 0.05)


def test_卷首主标题达到视觉主角量级():
    css = _read(CSS)
    m = re.search(r"(?m)^\s*\.home-cover-title\s*\{([^}]*)\}", css, re.S)
    assert m, "找不到无 .has-wall 限定的主标题基础规则"
    body = m.group(1)
    mm = re.search(r"font-size:\s*clamp\([^,]+,\s*[^,]+,\s*(\d+)px\)", body)
    assert mm, "主标题不再走既有 clamp() 惯例"
    assert int(mm.group(1)) >= 100, "主标题上限不足 100px，视觉主角没立起来"
    assert "color: var(--text)" in body, "白字守卫要求该规则体含 var(--text)"


def test_卷首左对齐破格():
    m = re.search(r"\.home-cover\.has-wall \.home-cover-inner\s*\{([^}]*)\}", _read(CSS), re.S)
    assert m
    body = m.group(1)
    assert "left: 9vw" in body and "text-align: left" in body
    assert "margin: 0 auto" not in body, "卷首又退回居中对称"


def test_遮罩不对称且后台滑块仍联动():
    js = _read(HOME)
    assert "linear-gradient(90deg" in js, "遮罩不是左深右浅"
    assert "o * 2.4" in js and "o * 0.28" in js, "遮罩写死常量会让后台浓度滑块失效"
    assert "veilOpacity.value" in js


def test_朱砂竖排印章与粗横线():
    seg = _seg()
    m = re.search(r"\.home-cover\.has-wall \.zh-hero-badge\s*\{([^}]*)\}", seg, re.S)
    assert m and "writing-mode: vertical-rl" in m.group(1)
    assert "var(--accent" in m.group(1)
    rule = re.search(r"\.home-cover-title::after\s*\{([^}]*)\}", seg, re.S)
    assert rule and "height: 8px" in rule.group(1)
    assert "var(--accent" in rule.group(1)


def test_最近更新并回主角左轴且降为配角():
    """v5.12.0 精修：右下角 22px 大字会与 118px 主角争视线，改为左轴 14px 配角。"""
    seg = _seg()
    m = re.search(r':root\[data-layout="chapter"\] \.zh-update-bar\s*\{([^}]*)\}', seg, re.S)
    assert m
    body = m.group(1)
    assert "border-radius: 0" in body and "background: transparent" in body
    assert "left: 9vw" in body and "right: auto" in body, "最近更新没并回主角左轴"
    assert "right: 5vw" not in body, "右下角大字排版回归"
    link = re.search(r"\.zh-update-bar a\s*\{([^}]*)\}", seg, re.S)
    assert link, "找不到最近更新链接规则"
    linkbody = link.group(1)
    assert "var(--type-meta, 14px)" in linkbody, "链接没降为配角字号"
    assert "var(--type-xl, 22px)" not in linkbody, "大字排版回归，会抢主角"


def test_分卷封面用程序化卷号不依赖数据():
    seg = _seg()
    assert "counter-reset: catvol" in seg
    assert "content: counter(catvol, decimal-leading-zero)" in seg
    assert ".zh-cat-thumb::before" in seg
    assert "var(--type-display, 44px)" in seg, "卷号没放大到 display 档"


def test_水印放大且不用opacity避开减弱动效突变():
    rule = re.search(r"\.zh-watermark\s*\{([^}]*)\}", _seg(), re.S)
    assert rule and "clamp(72px, 12vw, 164px)" in rule.group(1)
    assert "rgba(168, 68, 42" in rule.group(1)
    assert "opacity" not in rule.group(1), "reduced-motion 有 opacity:1 !important，写 opacity 会突变"


def test_read_more浅字规则已收窄到暗色分章区():
    css = _read(CSS)
    assert ".layout.zh-chapter-dark .post-card .read-more" in css
    assert not re.search(
        r':root\[data-card="row"\] \.post-card \.read-more\s*\{[^}]*--zh-ink-fg', css, re.S
    ), "暗色横卡区的浅字又泄漏到纸白页（1.25:1 缺陷回归）"


def test_朱砂对纸白对比度达到AA():
    assert _ratio((168, 68, 42), (243, 240, 232)) >= 4.5


def test_不新建CSS文件也不新增断点():
    imports = re.findall(r'import\s+["\']\./styles/([^"\']+\.css)["\']', _read(MAIN))
    assert imports == ["global.css", "responsive.css", "look.css"]
    # 标记位于说明注释块**内部**，切出来的段没有开头的 /* —— 先丢掉注释尾巴，
    # 再剥剩余注释；否则注释里「不新增 @media 块」这句话会把自己骗红。
    seg = _seg().split("*/", 1)[-1]
    code = re.sub(r"/\*.*?\*/", "", seg, flags=re.S)
    assert "@media" not in code, "新增视觉段不许引入新断点（棘轮只许减不许增）"


def test_动效冻结串未被破坏():
    css = _read(CSS)
    for i in range(1, 6):
        assert '[data-enter="%d"] { --enter-i: %d; }' % (i, i - 1) in css
    assert "animation: cover-enter" in css
    assert ".home-cover [data-enter]" in css


def test_窄屏印章回退为横排且特异性更高():
    """≤820px：印章右边界(3vw+57px)会追上标题左边界(9vw)，必须退回静态横排。

    回退规则写在**文件更靠前**的既有 820 断点块里，同权重会被末尾的基础规则反超，
    因此选择器必须多带 `.home-cover-inner`（特异性 0,6,0 > 0,5,0）。
    实测：改前 390/768 下印章与标题横向重叠；改后 390 印章 211–253 / 标题 269 起。
    """
    css = _read(CSS)
    m = re.search(
        r':root\[data-layout="chapter"\] \.home-cover\.has-wall \.home-cover-inner \.zh-hero-badge\s*\{([^}]*)\}',
        css, re.S,
    )
    assert m, "缺少窄屏印章回退规则，或漏了抬特异性的 .home-cover-inner 前缀"
    body = m.group(1)
    assert "position: static" in body, "窄屏仍是绝对定位，会压住左对齐标题"
    assert "writing-mode: horizontal-tb" in body, "窄屏应退回横排"
    assert "box-shadow: none" in body


def test_分卷封面文字色不继承链接蓝():
    """分类卡整体是 <a>，空 div 会继承默认链接色 rgb(0,0,238) 污染封面文字。"""
    rule = re.search(r"\.zh-cat-thumb\s*\{([^}]*)\}", _seg(), re.S)
    assert rule and "color: var(--zh-paper" in rule.group(1)

