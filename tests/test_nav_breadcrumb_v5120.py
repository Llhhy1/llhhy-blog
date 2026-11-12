# -*- coding: utf-8 -*-
"""v5.12.0「导航不迷路」守卫。

取证：线上真实 DOM 实测 aria-current=page 已有 4 个、抽屉 14 个入口
（Vue Router 4 自动注入），所以**不重复造**；这里钉住真正新增的三件事：
面包屑层级、可见当前态、抽屉焦点闭环。断言一律「每一条都」。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "vue-frontend" / "src" / "App.vue"
MAIN = ROOT / "vue-frontend" / "src" / "main.js"


def _app():
    return APP.read_text(encoding="utf-8")


def _style():
    return _app().split("<style", 1)[-1]


def test_面包屑渲染层级且最后一级不可点():
    t = _app()
    assert 'class="breadcrumb"' in t and 'aria-label="面包屑"' in t
    assert '<router-link to="/">{{ t(\'home\') }}</router-link>' in t, "缺首页回退"
    assert '<span v-else class="bc-current" aria-current="page">' in t, "最后一级不是不可点文本"
    assert '<router-link v-if="c.to" :to="c.to">' in t, "中间级不可回退"
    for needle in ('v-if="crumbItems.length"', 'class="bc-sep" aria-hidden="true"'):
        assert needle in t, f"面包屑缺 {needle}"


def test_面包屑按栏目级生成且不依赖文章数据():
    t = _app()
    assert "const route = useRoute();" in t, "没接路由，面包屑不会随页面更新"
    for needle in ('const crumbItems = computed(', 'route.path.split("/").filter(Boolean)',
                   'segs.slice(0, 1)', 'segs.slice(0, 2)', 'CRUMB_LABELS[raw]',
                   'decodeURIComponent(raw)'):
        assert needle in t, f"面包屑生成逻辑缺 {needle}"
    assert "apiGet" not in t.split("const crumbItems", 1)[-1].split("function onDrawerKey", 1)[0], (
        "面包屑不该发额外请求"
    )


def test_可见当前态不能只靠颜色():
    css = _style()
    top = re.search(r"\.site-header > \.container > nav > a\.router-link-exact-active\s*\{([^}]*)\}", css, re.S)
    assert top and "border-bottom:" in top.group(1), "顶栏当前态缺可见下划线"
    assert "var(--accent" in top.group(1)
    drawer = re.search(r"\.drawer-nav > a\.router-link-exact-active\s*\{([^}]*)\}", css, re.S)
    assert drawer and "border-left:" in drawer.group(1), "抽屉当前态缺可见竖条"
    for sel in (".breadcrumb .bc-sep", ".breadcrumb .bc-current", ".breadcrumb a:hover"):
        assert sel in css, f"缺 {sel} 样式"


def test_抽屉焦点闭环每一环都在():
    t = _app()
    for needle in ('ref="drawerRef"', 'ref="hamburgerRef"',
                   'watch(drawerOpen, async (open)', 'await nextTick()',
                   'document.addEventListener("keydown", onDrawerKey)',
                   'document.removeEventListener("keydown", onDrawerKey)',
                   'onBeforeUnmount(() => document.removeEventListener("keydown", onDrawerKey))',
                   'e.key === "Escape"', 'e.key !== "Tab"',
                   'e.shiftKey && document.activeElement === first',
                   'document.activeElement === last',
                   'hamburgerRef.value.focus()'):
        assert needle in t, f"抽屉焦点闭环缺 {needle}"


def test_抽屉打开时具备对话框语义():
    t = _app()
    for needle in (':aria-modal="drawerOpen ? \'true\' : undefined"',
                   ':role="drawerOpen ? \'dialog\' : undefined"'):
        assert needle in t, f"抽屉缺 {needle}"


def test_导航改动未新增断点与CSS文件():
    t = _app()
    # App.vue 原本只有一个 900px 媒体块；新增样式一律用 clamp()。
    # 必须先剥注释 —— 说明文字里出现「媒体块」字样不该被当成真实规则。
    code = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    assert len(re.findall(r"@media", code)) == 1, "导航改动引入了新断点（棘轮 27 已用满）"
    imports = re.findall(r'import\s+["\']\./styles/([^"\']+\.css)["\']',
                         MAIN.read_text(encoding="utf-8"))
    assert imports == ["global.css", "responsive.css", "look.css"]
    assert "clamp(" in _style(), "窄屏间距没走 clamp()"
