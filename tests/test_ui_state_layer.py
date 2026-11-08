# -*- coding: utf-8 -*-
"""P1「状态与刻度」静态守卫：纯文件读取断言。

约束（与主会话约定）：
- 不 import app、不连数据库、不依赖任何 fixture；
- 所有路径用 ``pathlib.Path(__file__).resolve().parents[1]`` 相对定位，Windows 兼容；
- 只做静态文本断言，因此可与全量 pytest 一起安全运行。
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vue-frontend" / "src"

# 约定刻度集合：@media 硬编码像素断点只允许使用这些值。
# 原生 CSS 变量不能用于 @media 条件（媒体查询在变量解析之前求值），
# 所以这里是「约定 + 扫描守卫」，不要用变量去替换断点。
ALLOWED_BREAKPOINTS = {480, 520, 560, 640, 720, 760, 768, 820, 860, 900, 980, 1180, 1280}

# 断点棘轮基线（2026-11-08 实测）：@media 条件里的像素断点总数。
# 【只允许减少，不允许新增】—— 新增断点必须先扩上面的约定集合并说明理由、
# 同步更新本基线，不许悄悄加一个 @media (max-width: 999px)。
BREAKPOINT_BASELINE = 27

# 既有越界断点（历史遗留：641/981 是 640/980 的配对值、1100 是旧布局断点）。
# 棘轮白名单：只允许保持/减少，不允许出现**新的**越界数值。
EXISTING_OUTLIERS = {641, 981, 1100}

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}")


def _read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def _collect_media_breakpoints():
    """扫描 vue-frontend/src/**/*.vue 与 src/styles/*.css 里 @media 条件中的像素断点。"""
    files = list(SRC.rglob("*.vue")) + list((SRC / "styles").glob("*.css"))
    vals = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        # 只取 @media 条件段（到第一个 { 之前），避免把规则体里的 px 算进来
        for seg in re.findall(r"@media[\s\S]*?\{", text):
            vals.extend(int(px) for px in re.findall(r"(\d+)px", seg))
    return vals


# ---- 1. main.js 的 CSS import 顺序（防有人插新 CSS 文件）----
def test_css_import_order_is_frozen():
    src = _read("vue-frontend", "src", "main.js")
    css = re.findall(r'import\s+["\'](?:\./)?styles/([^"\']+\.css)["\']', src)
    assert css == ["global.css", "responsive.css", "look.css"], (
        "main.js 的 CSS import 必须恰好是 global.css → responsive.css → look.css 三行且顺序不变；"
        "禁止新建/插入 CSS 文件（层叠顺序被 test_frontend_css_order.py 钉死）。"
        f"实测：{css}"
    )


# ---- 2. AsyncState.vue 组件契约 ----
def test_async_state_component_contract():
    text = _read("vue-frontend", "src", "components", "AsyncState.vue")
    # 四种 state 分支都要显式出现
    for st in ("loading", "empty", "error", "ready"):
        assert f"state === '{st}'" in text, f"AsyncState.vue 缺少 {st} 状态分支"
    # 可访问性：常驻 polite live region
    assert 'role="status"' in text, "容器必须是 live region"
    assert 'aria-live="polite"' in text, "容器必须 polite 播报"
    # 重试按钮：明确文本 + 只在传了 retry 时显示 + @click 调 retry
    assert "重试" in text, "重试按钮缺少明确文本"
    assert '@click="retry"' in text, "重试按钮必须把 @click 绑定到 retry prop"
    assert 'v-if="retry"' in text, "重试按钮必须只在传了 retry 时显示"
    # 骨架复用 global.css 现成动画，不自己实现
    assert ".skel-shimmer" in text, "必须复用 global.css 的 skel-shimmer 骨架动画"
    assert ".skel-line" in text, "骨架条应复用 .skel-line 现成类"
    # 禁止项
    assert "v-html" not in text, "AsyncState.vue 禁止 v-html"
    assert not HEX_RE.search(text), "AsyncState.vue 禁止裸 hex 颜色，一律走 CSS 变量"


# ---- 3. 断点棘轮 ----
def test_media_breakpoint_ratchet():
    vals = _collect_media_breakpoints()
    assert len(vals) <= BREAKPOINT_BASELINE, (
        f"@media 硬编码像素断点总数只允许减少、不允许新增；"
        f"基线 {BREAKPOINT_BASELINE}，实测 {len(vals)}"
    )
    outliers = set(vals) - ALLOWED_BREAKPOINTS
    assert outliers <= EXISTING_OUTLIERS, (
        "出现了约定刻度集合之外的**新**断点数值；原生 CSS 变量不能用于 @media 条件，"
        f"这是约定+扫描守卫。新增越界值：{sorted(outliers - EXISTING_OUTLIERS)}"
    )


# ---- 4. StatsView / SquareView 深色不可读裸色已清除 ----
def test_stats_unreadable_colors_replaced():
    text = _read("vue-frontend", "src", "views", "StatsView.vue")
    # 本次替换掉的、深色下不可读的具体写法/值：
    gone = [
        "var(--card, #fff)",   # --card 在 tokens.css 未定义 → 回退白底 + 浅字不可读
        "var(--text, #333)",   # 同上（按钮文字）
        "#8a5a00",             # 「新」徽章深棕字
        "#f0c060",             # 给上面那条打的暗色补丁裸色
        '[data-theme="dark"] .dash-delta.new',  # 补丁覆盖已删除，改由 token 自适应
    ]
    for frag in gone:
        assert frag not in text, f"StatsView.vue 仍残留已替换的深色不可读裸色：{frag}"


def test_square_no_hardcoded_dark_color():
    text = _read("vue-frontend", "src", "views", "SquareView.vue")
    # 任务点名的深色底不可读值（实测该文件早已全量使用 CSS 变量，本就不存在）
    assert "#1f1f1f" not in text, "SquareView.vue 仍出现 #1f1f1f"
    assert not HEX_RE.search(text), "SquareView.vue 不应出现任何裸 hex 颜色"


# ---- 5. 静默 catch 不再「完全吞掉错误」+ 循环依赖说明 ----
def test_app_silent_catches_now_report():
    text = _read("vue-frontend", "src", "App.vue")
    for msg in ("通知加载失败", "标记已读失败", "公告加载失败", "插件加载失败"):
        assert msg in text, f"App.vue 的静默 catch 缺少中文提示：{msg}"
    assert 'toast("' in text, "App.vue 必须通过已导入的 toast 给出提示"


def test_store_init_failure_no_longer_silent():
    """store.js 的初始化失败不再「完全吞掉」。

    循环依赖核查：toast.js 与 api.js 均**零 import**（只依赖 DOM / fetch），
    store.js → lib/toast.js 不会形成环，故站点设置加载失败直接用 toast 给中文提示；
    /api/auth/me 的失败多为「未登录」常态，只记中文日志、不弹 toast 骚扰匿名访客。
    两处都保持原有降级值（site 用默认 state、user 置 null）不变。
    """
    text = _read("vue-frontend", "src", "store.js")
    assert "站点设置加载失败" in text and 'toast("' in text, "站点设置加载失败需给出 toast 提示"
    assert "登录状态加载失败" in text, "auth/me 失败需至少留中文日志，不再完全静默"
    assert "站点设置加载失败，请稍后重试" in text, "toast 文案需为中文"
