"""v5.11.2 · PWA 整套移除 + 交互可达性守卫

为什么需要这一组：
1. `public/sw.js` 自 v3.21.0 引入后从未改动，缓存名写死 `llhhy-pwa-v1`，
   activate 的 `k !== CACHE` 因此永远清不掉旧缓存；`isArticleApi` 又把
   `GET /api/posts` 纳入 `return cached || network` —— 发新文章后第一次刷新
   仍是旧列表。这正是「改了没生效 / 发版看不到新版」的一类真实来源。
   ROADMAP 早已判定「PWA 离线：维护成本 > 收益」，故整套移除而不是修。
2. 只删按钮会留雷：`main.js` 的 `preventDefault()` 会吞掉浏览器原生安装提示，
   且老访客已注册的 SW 不会因仓库删文件而消失。必须留一次性注销逻辑。
3. 同批修掉 4 类用户可感知缺陷：键盘不可达、焦点环不可见、静默吞错、
   硬编码浅灰小字低于 DESIGN.md §3 指标 6 的 4.5:1。

⚠️ 断言口径：凡「多处都要满足」的检查一律收集**全部**违规再断言为空，
绝不写「至少有一条 X 带 Y」—— v5.11.1 就是这样漏抓过 M4 序号隔离。
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "vue-frontend" / "src"
PUB = ROOT / "vue-frontend" / "public"
INDEX = ROOT / "vue-frontend" / "index.html"
README = ROOT / "README.md"

MAIN = SRC / "main.js"
STORE = SRC / "store.js"
APP = SRC / "App.vue"
ALBUM = SRC / "views" / "AlbumView.vue"
SEARCH = SRC / "views" / "SearchView.vue"
GLOBAL_CSS = SRC / "styles" / "global.css"
LOOK_CSS = SRC / "styles" / "look.css"

# 删掉后一个都不许再出现的 PWA 静态文件
PWA_FILES = (
    "sw.js",
    "manifest.webmanifest",
    "offline.html",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-192.png",
    "icon-maskable-512.png",
)

# 安装链路的标识符（不含泛词 PWA / Service Worker —— 迁移注释里会用到）
DEAD_TOKENS = (
    "beforeinstallprompt",
    "appinstalled",
    "setInstallPrompt",
    "installApp",
    "install-app",
    "install_app",
    "state.installPrompt",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def _block(text, selector):
    """取某条规则的大括号内容；找不到返回 None。"""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text, re.S)
    return m.group(1) if m else None


def _block_from(text, marker):
    """从 marker 起取到第一个 }（用于多条选择器并列、不好写正则的 CSS 块）。"""
    i = text.find(marker)
    if i < 0:
        return None
    j = text.find("}", i)
    return text[i:j] if j > i else None


def _fn_block(text, marker):
    """按花括号配平取整段 JS 函数（函数里有 try/catch，不能取第一个 }）。"""
    i = text.find(marker)
    if i < 0:
        return None
    start = text.find("{", i)
    if start < 0:
        return None
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def _source_files():
    files = sorted(SRC.rglob("*.js")) + sorted(SRC.rglob("*.vue"))
    files.append(INDEX)
    return files


# ---------------------------------------------------------------- 1. PWA 移除
def test_every_pwa_static_file_is_removed():
    left = [name for name in PWA_FILES if (PUB / name).exists()]
    assert left == [], f"仍有 PWA 静态文件会被打进前端包: {left}"


def test_no_install_pipeline_token_left_anywhere_in_source():
    violations = []
    for p in _source_files():
        text = _read(p)
        for token in DEAD_TOKENS:
            if token in text:
                violations.append(f"{p.relative_to(ROOT)}: {token}")
    assert violations == [], f"PWA 安装链路有残留（含注释）: {violations}"


def test_index_html_no_longer_links_pwa_assets():
    text = _read(INDEX)
    for needle in ('rel="manifest"', "apple-touch-icon", "icon-192.png"):
        assert needle not in text, f"index.html 仍引用 PWA 资源: {needle}"
    # 浏览器 UI 染色不是 PWA 能力，保留
    assert 'name="theme-color"' in text


def test_legacy_service_worker_cleanup_is_present():
    """存量访客的 SW 不会自己消失，注销逻辑至少保留两个线上版本。"""
    text = _read(MAIN)
    for needle in (
        "import.meta.env.PROD",
        "getRegistrations()",
        ".unregister()",
        "caches.keys()",
        'startsWith("llhhy-pwa")',
        "caches.delete(k)",
    ):
        assert needle in text, f"main.js 缺存量 SW 注销逻辑: {needle}"
    # 不允许再注册新的 SW
    assert 'serviceWorker.register' not in text


def test_readme_no_longer_advertises_pwa():
    line = next((l for l in _read(README).splitlines() if l.startswith("- **系统**")), "")
    assert line, "README 的「系统」功能行找不到了"
    assert "PWA" not in line, "README 仍在宣传已移除的 PWA"


# ---------------------------------------------------------------- 2. 键盘可达
def test_bell_trigger_is_a_real_button_with_aria():
    text = _read(APP)
    m = re.search(r'<button\b[^>]*class="nav-bell-trigger"[^>]*>', text, re.S)
    assert m, "通知铃铛不是真 button（键盘仍不可达）"
    tag = m.group(0)
    for needle in ('type="button"', "aria-label", "aria-expanded", "@click"):
        assert needle in tag, f"铃铛按钮缺 {needle}"
    assert '<div class="nav-bell" @click' not in text, "裸 div 点击入口又回来了"


def test_every_album_image_is_keyboard_reachable():
    text = _read(ALBUM)
    tags = re.findall(r'<div\b[^>]*class="album-media-box is-image"[^>]*>', text, re.S)
    assert len(tags) == 2, f"相册大图容器数量变了（应为分组 + 未分组两处），实际 {len(tags)}"
    bad = []
    for i, tag in enumerate(tags):
        for needle in ('role="button"', 'tabindex="0"', "@keydown.enter", "@keydown.space"):
            if needle not in tag:
                bad.append(f"第 {i + 1} 处缺 {needle}")
    assert bad == [], f"相册大图键盘属性不齐: {bad}"
    focus = _block(text, ".album-media-box.is-image:focus-visible")
    assert focus and "outline: 2px solid var(--accent" in focus, "role=button 的 div 缺实色焦点环"


def test_search_history_delete_is_not_nested_in_another_button():
    text = _read(SEARCH)
    assert not re.findall(r'<button\b[^>]*class="sh-chip"[^>]*>', text, re.S), \
        "sh-chip 又是 button，删除键会被嵌在 button 内"
    assert re.findall(r'<div\b[^>]*class="sh-chip"[^>]*>', text, re.S), "sh-chip 容器不见了"
    m = re.search(r'<button\b[^>]*class="sh-del"[^>]*>', text, re.S)
    assert m, "删除历史没有独立的 button"
    assert 'aria-label' in m.group(0), "删除按钮缺 aria-label"
    assert '<span class="sh-del" role="button"' not in text, "嵌套 span 写法又回来了"


# ---------------------------------------------------------------- 3. 焦点环
def test_every_focus_rule_uses_solid_outline():
    """4 条 focus 规则逐条检查；写「至少一条」会漏抓单条回退。"""
    targets = (
        (LOOK_CSS, "button:focus-visible, .btn:focus-visible {"),
        (LOOK_CSS, "input[type=tel]:focus, select:focus, textarea:focus {"),
        (LOOK_CSS, ".search-box input:focus {"),
        (GLOBAL_CSS, ".search-box input:focus, .sub-box input[type=email]:focus"),
    )
    bad = []
    for path, marker in targets:
        block = _block_from(_read(path), marker)
        if block is None:
            bad.append(f"{path.name}: 找不到 {marker}")
            continue
        if "outline: 2px solid var(--accent" not in block:
            bad.append(f"{path.name}: {marker} 没有实色 outline")
        if "outline: none" in block:
            bad.append(f"{path.name}: {marker} 又把 outline 去掉了")
    assert bad == [], f"焦点环规则不达标: {bad}"


# ---------------------------------------------------------------- 4. 静默吞错
def test_mark_all_read_and_logout_no_longer_swallow_errors():
    app = _read(APP)
    mark = _fn_block(app, "async function markAllNotifRead()")
    assert mark and "catch (e) { toast(" in mark, "「全部已读」失败仍无反馈"
    assert 'catch (e) {}' not in mark, "「全部已读」又变回空 catch"

    logout = _fn_block(_read(STORE), "export async function logout()")
    assert logout, "store.js 找不到 logout()"
    for needle in ("toast(", "return false", "return true", "state.user = null"):
        assert needle in logout, f"logout() 缺 {needle}"
    assert "catch (e) {}" not in logout, "logout 又变回空 catch"

    dologout = _fn_block(app, "async function doLogout()")
    assert dologout and "if (!(await logout())) return;" in dologout, \
        "退出失败时仍会跳首页，界面会假装已退出"


# ---------------------------------------------------------------- 5. 小字对比度
MUTED_SELECTORS = (
    ".comment-meta",
    ".comment-empty",
    ".friend-links .desc",
    ".guestbook-item .gb-meta",
    ".gb-like-btn",
    ".series-count",
    ".series-toc .chapter-meta",
)


def test_every_muted_small_text_rule_uses_token():
    """7 条逐条判：改坏其中任意一条都必须变红。"""
    css = _read(GLOBAL_CSS)
    bad = []
    for sel in MUTED_SELECTORS:
        block = _block(css, sel)
        if block is None:
            bad.append(f"{sel}: 规则找不到")
            continue
        if "var(--text-muted)" not in block:
            bad.append(f"{sel}: 没用 --text-muted")
        for hexcolor in ("#999", "#aaa", "#888"):
            if hexcolor in block.lower():
                bad.append(f"{sel}: 仍含硬编码浅灰 {hexcolor}")
    assert bad == [], f"辅助小字对比度不达标（DESIGN.md §3 指标 6）: {bad}"
