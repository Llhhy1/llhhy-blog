"""WCAG 对比度守卫（v3.25.0）。

背景：审计实测 6 处 token 组合低于 WCAG 2.1 SC 1.4.3 门槛（正文 4.5:1 /
大字 3:1）。其中 `--text-faint` 亮色 2.44:1、`--danger` 暗色白字 2.39:1
属真实可读性缺陷（前者 14 处 11-13px 小字说明，后者红底白字按钮与通知角标）。

**建表口径**（这三条是本文件最容易写错的地方，改前务必照抄）：

1. **token 有角色，不能一律当文字色判**。`--danger` / `--accent` / `--success`
   既做 `background:`（配 `--on-accent` 白字）也做 `color:`。两种身份各自有
   搭配关系，混在一起判会同时产生假阳性和假阴性：
   - 亮色 `--success` 白字 5.02:1 ✅，但**零** background 消费点 → 不该判它当底色；
   - 暗色 `--success` 当文字 6.52:1 ✅，若误判「白字压色块」会报 2.09:1 FAIL ——
     而改成 #518154 会直接毁掉暗色配色。**这是本文件最贵的一个教训。**
   故下面按 `(主题, token, 身份)` 三元组逐条枚举，只校验真实存在的搭配。

2. **背景只取真实承载文本的表面**。`--surface-3` **不参与**：实测它只用于
   `global.css:1182` 的骨架屏 shimmer 渐变，从不压文字。把它当文本背景会让
   `--text-muted` 亮色误报 4.08:1 FAIL（真实值 4.46:1，只差 0.04）。

3. **同一 token 的最难表面随主题而变**，所以每条都逐表面算 min，不假定
   「最难的一定是 surface-3」。

4. **两个渲染面各有一份真相源，缺一不可**（v3.25.0 实测更正 —— 原注释写
   「`themes.py` 靠 `{{ theme_css }}` 覆盖 CSS 变量」是**错的**，`theme_css`
   只含 `--theme-radius` / `--theme-font-size`，不含任何颜色）。真实链路：
   - **前台 SPA**：`store.js: applyThemeTokens()` 把 `theme_tokens` 逐个
     `setProperty("--surface-2", …)` 写到 `:root`，**覆盖** tokens.css。
     实测「tokens 全绿、14/14 preset 仍不达标」—— 只改 tokens.css 对 SPA 无效。
   - **后台 admin**：`myblog/static/tokens.css` 是**唯一**来源（admin 无任何
     JS 注入，实测 `admin/` 模板 + `admin.css` 里零 `setProperty`）。
     只改 themes.py 对后台无效。
   所以下面一半守卫跑 tokens.css（覆盖 admin + SSR），一半跑运行时主题
   （覆盖 SPA）。**两边都要绿才算修完。**

**门槛为何分档**：`--text-faint` 亮色取 **3.0**（大字/次要文本档）而非 4.5。
实测强取 4.5 会让它落到与 `--text-muted` 亮度差仅 0.003 的位置，三档文本层级
视觉塌成两档，等于用「可辨性」换「数字达标」。这是刻意取舍，已写入 tokens.css
与 `themes._faint_for` 的注释。暗色下修到位后间隔仍够，故按正文 4.5 守。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 单一真相源有两份（前端 SPA + 后台 admin），必须同时校验并保持同值
TOKEN_FILES = [
    ROOT / "vue-frontend" / "src" / "styles" / "tokens.css",
    ROOT / "myblog" / "static" / "tokens.css",
]

BODY_MIN = 4.5   # WCAG 2.1 SC 1.4.3 正文
LARGE_MIN = 3.0  # WCAG 2.1 SC 1.4.3 大字（>=18px，或 >=14px 粗体）

# 承载文本的真实表面（不含 --surface-3：仅骨架屏渐变用）
SURFACES = ("--bg", "--surface", "--surface-2", "--nav-bg")

# 契约：(主题, 前景 token, 背景 token, 门槛, 为什么存在这个搭配)
# 背景写 None 表示「压在纯白/纯黑上」（底色身份，配 --on-accent）
FOREGROUND_PAIRS = [
    # ---- 正文与副文本：全站主力 ----
    ("root", "--text", SURFACES, BODY_MIN, "正文"),
    ("root", "--text-muted", SURFACES, BODY_MIN, "副文本 11-14px"),
    ("root", "--text-faint", SURFACES, LARGE_MIN,
     "次要说明 11-13px —— 走大字档，见模块 docstring 门槛分档说明"),
    ("dark", "--text", SURFACES, BODY_MIN, "正文"),
    ("dark", "--text-muted", SURFACES, BODY_MIN, "副文本"),
    ("dark", "--text-faint", SURFACES, BODY_MIN,
     "暗色下有余量（修到位后与 muted 间隔仍 0.082），故按正文 4.5 守"),
    ("root", "--nav-fg", ("--nav-bg",), BODY_MIN, "导航文字"),
    ("dark", "--nav-fg", ("--nav-bg",), BODY_MIN, "导航文字"),

    # ---- 状态色 / 主题色：作前景 ----
    ("root", "--accent", SURFACES, BODY_MIN,
     "链接 / 标签 / ghost 按钮文字（默认值；运行时可被 accent_color 覆盖）"),
    ("dark", "--accent", SURFACES, BODY_MIN,
     "同上的暗色版（暗色 accent 提到 L 0.66~0.72，下界 0.62 时仅 3.96~4.45）"),
    ("root", "--success", SURFACES, BODY_MIN,
     ".unsub-tip.ok / .sub-msg.ok / .comment-status.success 等提示文字"),
    ("dark", "--success", SURFACES, BODY_MIN, "同上的暗色版"),

    # ---- 底色身份：文字压色块 ----
    # ⚠️ 亮色用「__white__」，暗色用 `--on-accent` —— 暗色下 on_accent **不是**
    # 白字（accent 被提亮后白字必然崩，实测 14/14 全不达标）。这条是本次最
    # 容易被写错的身份：用 __white__ 判暗色会报出一堆假 FAIL，而真去调暗色
    # accent 又会毁掉「深底上 accent 作文字」的观感。
    ("root", "--danger", ("__white__",), BODY_MIN,
     ".btn.danger 按钮文字（基类 color: var(--on-accent)，亮色 on_accent 即白字）+ 通知角标"),
    # ⚠️ 暗色**不登记** `__white__` × `--danger`：暗色 danger 被提到 L>=0.67
    # 才能当文字（admin.css:315 .link-danger 13px 链接），而那个亮度下白字
    # 数学上不可能到 4.5（L 扫 0.30~0.78 无交集）。这条契约是**自相矛盾**的，
    # 写进去只会永远红。真正要守的是下面两条 on_accent 契约。
    ("dark", "--danger", SURFACES, BODY_MIN,
     "⚠️ 暗色 danger 也有**前景身份**：admin.css:315 .link-danger（13px 危险操作"
     "链接，无背景覆盖）+ :604 .side-logout:hover，暗色均无覆盖"),
    ("root", "--accent", ("__white__",), BODY_MIN,
     "button/.btn 基类背景 + 白字，全站按钮默认态"),
    ("dark", "--accent", ("--on-accent",), BODY_MIN,
     "暗色主按钮：on_accent 深字压 accent_d（实测白字只有 2.43~4.06）"),
    ("dark", "--danger", ("--on-accent",), BODY_MIN,
     "暗色 .btn.danger：同一个 on_accent 也要压得住 danger（danger 更亮，更严）"),
    ("root", "--success", ("__white__",), BODY_MIN,
     "语义位：保留底色身份以防将来新增 background 消费点"),
]


def _parse(path):
    """返回 {'root': {token: hex}, 'dark': {...}}；只取十六进制实值。"""
    out = {"root": {}, "dark": {}}
    theme = "root"
    for line in path.read_text(encoding="utf-8").splitlines():
        if "[data-theme" in line and "dark" in line:
            theme = "dark"
        m = re.match(r"\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", line)
        if m:
            out[theme][m.group(1)] = m.group(2)
    return out


def _lum(hex_color):
    def chan(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "ff"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _ratio(fg, bg):
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@pytest.mark.parametrize("path", TOKEN_FILES, ids=lambda p: p.as_posix())
def test_token_contrast_meets_wcag(path):
    """每条已登记的「前景 × 背景」搭配都不得低于其门槛。"""
    themes = _parse(path)
    failures = []
    for theme, fg_tok, bg_toks, minimum, why in FOREGROUND_PAIRS:
        tk = themes[theme]
        assert fg_tok in tk, "%s: token %s 未定义（契约与实现漂移）" % (theme, fg_tok)
        for bg_tok in bg_toks:
            bg_hex = "#ffffff" if bg_tok == "__white__" else tk[bg_tok]
            ratio = _ratio(tk[fg_tok], bg_hex)
            if ratio < minimum:
                failures.append(
                    "  [%s] %s(%s) on %s(%s) = %.2f:1  < %.1f:1  — %s"
                    % (theme, fg_tok, tk[fg_tok], bg_tok, bg_hex, ratio, minimum, why))
    assert not failures, (
        "WCAG SC 1.4.3 未达标（正文 4.5:1 / 大字 3:0）:\n" + "\n".join(failures))


def test_on_accent_covers_every_block_it_sits_on():
    """`--on-accent` 必须压得住**它实际会坐上去的每一个色块**。

    这条是补一个真实的守卫真空（变异验证实测：把 `_on_accent_for(accent_d,
    danger, ...)` 改回只传 accent，**其余 13 条守卫全绿**）。

    为什么会漏：`_on_accent_for` 的深字分支取「页面背景色」，而暗色页面背景
    恰好对 accent 与 danger 都够深（4.7~5.7），所以少传一个参数时结果一模一样
    —— 但语义上危险是**更亮**的一侧，一旦页面背景调亮或 danger 再提亮就会崩。
    token 的**声明**必须覆盖真实搭配集合，不能靠「碰巧也过」。

    ⚠️ 这条也防止把 on_accent 从深字改回白字：白字在暗色下压不住任何色块
    （实测 2.43~4.06），而 13 条契约里的 `__white__` 哨兵抓不到它 ——
    哨兵只判「若有人用白字」，不判「on_accent 本身是否够用」。
    """
    import themes as T

    problems = []
    for pack in T.THEME_PRESETS:
        for label, tk in (("light", pack["light"]), ("dark", pack["dark"])):
            on = tk["on_accent"]
            # on_accent 会坐上去的色块 = 配了 color: var(--on-accent) 的背景
            for block in ("accent", "danger"):
                r = _ratio(on, tk[block])
                if r < BODY_MIN:
                    problems.append("  [%s/%s] on_accent %s 压 --%s(%s) = %.2f:1 < 4.5"
                                    % (pack["id"], label, on, block, tk[block], r))
    # 默认主题路径（accent 由后台 accent_color 给，不是 preset）
    d = T._default_theme("#196ddd")
    for label, tk in (("light", d["light"]), ("dark", d["dark"])):
        for block in ("accent", "danger"):
            r = _ratio(tk["on_accent"], tk[block])
            if r < BODY_MIN:
                problems.append("  [default/%s] on_accent %s 压 --%s(%s) = %.2f:1 < 4.5"
                                % (label, tk["on_accent"], block, tk[block], r))
    assert not problems, ("--on-accent 压不住它会坐上去的色块:\n" + "\n".join(problems))


def test_on_accent_solver_receives_every_block():
    """`derive_dark` 必须把**每一个**会被 on_accent 压住的色块都传进求解器。

    这条守的是一个**数值上不可见**的漏洞（变异验证实测：把
    `_on_accent_for(accent_d, danger, page_bg_hex=bg)` 改成不传 danger，
    上面那条 `test_on_accent_covers_every_block_it_sits_on` **仍然全绿**）。

    为什么会漏：`_on_accent_for` 的深字分支取「页面背景色」，而暗色页面背景
    恰好对 accent 与 danger 都够深，所以少传一个参数时**返回值一模一样**。
    数值守不住这种「碰巧也对」，只能守住调用点本身的声明完整性。

    做法：静态检查 `derive_dark` 源码里的调用点，确认 `on_accent` 求解传入的
    变量集合覆盖了全部「配了 color: var(--on-accent)」的背景 token。
    将来新增第三个这样的色块（例如 --warning 转正），这条会提醒同步。
    """
    import inspect
    import themes as T

    src = inspect.getsource(T.derive_dark)
    call = re.search(r"on_accent\s*=\s*_on_accent_for\(([^)]*)\)", src, re.S)
    assert call, "derive_dark 里找不到 _on_accent_for 调用点（写法变了？本守卫需同步）"
    args = call.group(1)
    # 当前必须压住的色块：.btn 基类(accent) + .btn.danger + 通知角标(danger)
    for block in ("accent_d", "danger"):
        assert re.search(r"\b%s\b" % block, args), (
            "_on_accent_for 调用点未传入 %r —— 少传时返回值可能**碰巧**相同，"
            "数值守卫抓不到（实测：去掉 danger 后 14/14 preset 全部仍绿）。\n"
            "实际调用：_on_accent_for(%s)" % (block, args.strip()))
    assert "page_bg_hex" in args, (
        "_on_accent_for 调用点丢了 page_bg_hex（页面背景，不是色块）")


def test_at_lum_never_overshoots():
    """`_at_lum` 变暗必须返回**不超过** want_l 的值（保守方向）。

    为什么要有这条（实测踩过）：二分返回 `hi` 侧时，结果总比目标**略亮**。
    后果不是「不达标」而是**系统性差一口气** —— 目标 L=0.1696 时实测 ratio
    只有 4.11~4.15（前景）/ 4.45~4.50（白字），全都卡在 4.5 下方，而调用方
    以为已达标就直接放行。这类偏差不会触发任何 4.5 门槛的守卫（值仍「差不多」
    达标），只能靠「方向确定性」来守。

    判据：对同一输入，变暗分支的实测亮度必须 <= want_l（+1e-9 容差）。
    """
    import themes as T

    problems = []
    samples = ("#9aa0a6", "#6a717f", "#12b886", "#ff6b35", "#ca8a04", "#ffffff")
    for src in samples:
        cur = T._wcag_lum(src)
        for want in (0.02, 0.05, 0.10, 0.1696, 0.2876, cur * 0.5):
            if want <= 0 or want >= cur:
                continue
            got_hex = T._at_lum(src, want, False)
            if got_hex is None:
                continue                      # 纯黑等不可达目标，跳过
            got = T._wcag_lum(got_hex)
            if got > want + 1e-9:
                problems.append("  _at_lum(%s, %.4f) -> %s 实测 %.6f **超过**目标 %.6f"
                                % (src, want, got_hex, got, want))
    assert not problems, (
        "_at_lum 变暗方向过冲（应为保守方向：宁略暗勿略亮）:\n" + "\n".join(problems))


# v3.25.0 发版审计新增：畸形值安全降级。
#
# **为什么需要这条**：`theme_post` 的 custom 路径只校验 `light.accent` **存在**、
# 不校验格式（实测 `from api/theme.py:47-50`），所以 `theme_tokens` 里可以存进
# `"red"` / `"#12345"` / `"rgb(1,2,3)"` 甚至 `"#fff</style><script>…"`。实测：
# `derive_dark()` 对这些值**全部存活**（accent 原样透传），下游 `setProperty`
# 是 CSSOM API、不解析值，故无 XSS。但求解器一旦吃到畸形值**抛异常**，
# 就会把「换主题」这个后台操作变成 500，且 `themes.py` 的模块 docstring 明写
# 「任意色彩解析失败都回退默认值，绝不抛异常导致页面 500」—— 实测底层
# `_hex_rgb` / `_wcag_lum` / `_wcag_ratio` 对 `red` / `''` / `None` **确实抛**
# （ValueError / AttributeError），只是被上层的 try/except 挡住了。
#
# 这条守卫钉的是**契约本身**：底层求解器（`_muted_for` / `_faint_for` /
# `_on_accent_for` / `_at_lum`）是所有外部入口的唯一通道，它们必须自己对
# 畸形输入免疫 —— 一旦有人删掉某处的 try/except 兜底，这里立刻红。
_MALFORMED = [
    None, "", "red", "#12345", "#1234567", "rgb(1,2,3)",
    "#fff; background: url(//evil)", "#fff</style><script>alert(1)</script>",
    "红色", "#ff\U0001F389",
]


@pytest.mark.parametrize("bad", _MALFORMED, ids=lambda v: repr(v)[:24])
def test_solvers_never_raise_on_malformed_colors(bad):
    """求解器对畸形色值必须安全降级，绝不抛异常（模块 docstring 的硬承诺）。"""
    import themes as T

    for label, call in (
        ("_muted_for", lambda: T._muted_for(bad, "#6a717f", light=True)),
        ("_faint_for", lambda: T._faint_for(bad, "#6a717f", light=True)),
        ("_on_accent_for", lambda: T._on_accent_for(bad, target=4.5, page_bg_hex=bad)),
        ("_at_lum", lambda: T._at_lum(bad, 0.3, True)),
        ("derive_dark", lambda: T.derive_dark({"accent": bad})),
    ):
        try:
            call()
        except Exception as e:  # noqa: BLE001
            pytest.fail("%s(畸形值 %r) 抛异常 %s: %s —— 会把「换主题」变成 500"
                        % (label, bad, type(e).__name__, e))


def test_at_lum_has_no_duplicated_block():
    """`_at_lum` 不得出现重复的二分块（v3.25.0 审计实测存在的死代码）。

    为什么这不是洁癖：重复的第一段**缺 `else: hi = mid`**，且其结果被第二段
    整体覆盖。它是纯死代码，但也是真陷阱 —— 后来人只会改到第一段，改完
    看不到任何效果，还会以为求解器没生效。故用「关键行不得出现两次」钉死。
    """
    import inspect

    import themes as T

    src = inspect.getsource(T._at_lum)
    for marker, why in (
        ("lo, hi = 0.0, 1.0", "二分初始化"),
        ("cur = _wcag_lum(hex_color)", "变暗前的亮度探测"),
    ):
        n = src.count(marker)
        assert n <= 1, (
            "_at_lum 里 %r 出现 %d 次（%s）—— 存在重复死代码块。"
            "只保留下方带 `else: hi = mid` 的正确版本。"
            % (marker, n, why))
    # 反向：正确的二分必须带 else 分支（缺它就等于永远取 lo，退化成单侧爬）
    assert "else:\n            hi = mid" in src, (
        "_at_lum 的二分缺 `else: hi = mid` —— 返回值会系统性偏暗，"
        "而调用方拿它去卡对比度门槛会差一口气")


@pytest.mark.parametrize("path", TOKEN_FILES, ids=lambda p: p.as_posix())
def test_two_token_files_stay_identical(path):
    """两份 tokens.css 必须同值 —— 它们声称自己是「单一真相源」。

    值一旦漂移，前台与后台会渲染出不同颜色，而所有静态检查都看不出来。
    """
    themes = _parse(path)
    other = _parse(TOKEN_FILES[1] if path == TOKEN_FILES[0] else TOKEN_FILES[0])
    diffs = []
    for theme in ("root", "dark"):
        for tok in sorted(set(themes[theme]) | set(other[theme])):
            a, b = themes[theme].get(tok), other[theme].get(tok)
            if a != b:
                diffs.append("  [%s] %-16s %s vs %s" % (theme, tok, a, b))
    assert not diffs, "两份 tokens.css 取值不一致：\n" + "\n".join(diffs)


@pytest.mark.parametrize("path", TOKEN_FILES, ids=lambda p: p.as_posix())
def test_text_tier_hierarchy_remains_distinguishable(path):
    """三档文本层级必须仍然肉眼可辨（相邻档 WCAG 亮度差 > 0.02）。

    这条守的是**取舍本身**：把 `--text-faint` 强拉到 4.5:1 会让它与
    `--text-muted` 亮度差只剩 0.003，三档塌成两档。数字达标了、设计语义没了 ——
    那不是修复。本守卫让这个取舍无法被静默推翻。

    ⚠️ **层级方向随主题翻转**（判错过一次，见下）：
    - 亮色：背景浅，文字越亮 -> 对比越低。语义「faint 最弱」= 亮度**最高**，
      故顺序是 text(L最低) < muted < faint(L最高)。
    - 暗色：背景深，文字越暗 -> 对比越低。语义「faint 最弱」= 亮度**最低**，
      故顺序是 text(L最高) > muted > faint(L最低)。
    两边都是「离表面越近 = 越弱」，判据统一成「与 surface 的亮度距离」。
    """
    themes = _parse(path)
    problems = []
    for theme in ("root", "dark"):
        tk = themes[theme]
        # 亮度离表面越远 = 越强；离表面越近 = 越弱
        dists = [abs(_lum(tk[t]) - _lum(tk["--surface"])) for t in
                 ("--text", "--text-muted", "--text-faint")]
        gaps = [abs(dists[0] - dists[1]), abs(dists[1] - dists[2])]
        if min(gaps) <= 0.02:
            problems.append("  [%s] 距表面亮度 %s 间隔 %.4f / %.4f"
                            % (theme, ["%.4f" % x for x in dists], *gaps))
    assert not problems, (
        "文本层级已坍缩（相邻档亮度差需 > 0.02，肉眼才分得出）:\n"
        + "\n".join(problems))


# ---------- 运行时主题（真正生效的那份）----------

def test_runtime_themes_meet_wcag():
    """**14 套运行时主题**的 faint / muted / danger 全部达标。

    为什么 tokens.css 的守卫不够：`themes.py` 的 `_BASE_LIGHT` + `derive_dark()`
    经 `store.js: applyThemeTokens()` 逐个 `setProperty` 写到 `:root`，在**前台
    SPA 上覆盖** tokens.css。只改 tokens.css 等于没改前端：实测「tokens 全绿、
    14/14 preset 仍不达标」。这条守卫才是真正拦住 SPA 回归的那道。
    （后台 admin 反过来只吃 tokens.css，见模块 docstring 第 4 条。）
    """
    import themes as T

    problems = []
    for pack in T.THEME_PRESETS:
        lt, dk = pack["light"], pack["dark"]
        bg_keys = ("bg", "surface", "surface_2", "nav_bg")
        # 亮色 faint 走大字档，暗色走正文档（见模块 docstring 取舍说明）
        for label, tk, minimum in (("light", lt, LARGE_MIN), ("dark", dk, BODY_MIN)):
            faint = tk["text_faint"]
            worst = min(_ratio(faint, tk[k]) for k in bg_keys)
            if worst < minimum:
                problems.append("  [%s/%s] text_faint %s 最差 %.2f:1 < %.1f"
                                % (pack["id"], label, faint, worst, minimum))
            muted_worst = min(_ratio(tk["text_muted"], tk[k]) for k in bg_keys)
            if muted_worst < BODY_MIN:
                problems.append("  [%s/%s] text_muted %s 最差 %.2f:1 < 4.5"
                                % (pack["id"], label, tk["text_muted"], muted_worst))
        # accent 身兼两职：作前景（126 处 color:）+ 作底色（配 on_accent）
        for label, tk in (("light", lt), ("dark", dk)):
            accent_fg = min(_ratio(tk["accent"], tk[k]) for k in bg_keys)
            if accent_fg < BODY_MIN:
                problems.append("  [%s/%s] accent %s 作文字最差 %.2f:1 < 4.5"
                                % (pack["id"], label, tk["accent"], accent_fg))
        # 底色身份：**亮色压白字、暗色压 on_accent**。统一写「白字」会报出
        # 一堆假 FAIL（暗色 accent/danger 被提亮到 L>=0.66，白字必然崩），
        # 而真去压暗 accent 又会毁掉「深底上 accent 作文字」的观感。
        light_on = min(_ratio("#ffffff", lt["danger"]), _ratio("#ffffff", lt["accent"]))
        if light_on < BODY_MIN:
            problems.append("  [%s/light] 白字压 accent/danger 最差 %.2f:1 < 4.5"
                            % (pack["id"], light_on))
        for label, tk in (("light", lt), ("dark", dk)):
            on_a, on_d = _ratio(tk["on_accent"], tk["accent"]), _ratio(tk["on_accent"], tk["danger"])
            if min(on_a, on_d) < BODY_MIN:
                problems.append("  [%s/%s] on_accent %s 压 accent %.2f:1 / danger %.2f:1 < 4.5"
                                % (pack["id"], label, tk["on_accent"], on_a, on_d))
        # danger 也有前景身份（admin.css:315 .link-danger 13px、暗色无覆盖）
        dark_danger_fg = min(_ratio(dk["danger"], dk[k]) for k in bg_keys)
        if dark_danger_fg < BODY_MIN:
            problems.append("  [%s/dark] danger %s 作文字最差 %.2f:1 < 4.5"
                            % (pack["id"], dk["danger"], dark_danger_fg))
    assert not problems, (
        "运行时主题未达 WCAG SC 1.4.3（tokens.css 全绿也不够——SPA 上它被覆盖）:\n"
        + "\n".join(problems))


def test_runtime_theme_tier_hierarchy_holds():
    """运行时主题的三档文本层级也必须可辨（与 tokens.css 同一取舍）。"""
    import themes as T

    problems = []
    for pack in T.THEME_PRESETS:
        for label, tk in (("light", pack["light"]), ("dark", pack["dark"])):
            dists = [abs(_lum(tk[t]) - _lum(tk["surface"]))
                     for t in ("text", "text_muted", "text_faint")]
            gaps = [abs(dists[0] - dists[1]), abs(dists[1] - dists[2])]
            if min(gaps) <= 0.02:
                problems.append("  [%s/%s] 距表面亮度 %s 间隔 %.4f / %.4f"
                                % (pack["id"], label,
                                   ["%.4f" % x for x in dists], *gaps))
    assert not problems, "运行时主题文本层级坍缩:\n" + "\n".join(problems)


def test_base_light_matches_token_files():
    """`_BASE_LIGHT` 必须与两份 tokens.css 同值 —— 它自称「与 tokens.css 一致」。

    三个真相源（themes.py + 两份 tokens.css）任一漂移，前台与后台就会渲染出
    不同颜色，而所有静态检查都看不出来。
    """
    import themes as T

    token_themes = _parse(TOKEN_FILES[0])
    diffs = []
    # tokens 用连字符，_BASE_LIGHT 用下划线
    for theme, tk in (("root", token_themes["root"]), ("dark", token_themes["dark"])):
        for css_tok, css_val in tk.items():
            if not css_tok.startswith("--"):
                continue
            py_key = css_tok[2:].replace("-", "_")
            if py_key not in ("accent", "accent_hover", "accent_soft", "on_accent",
                              "bg", "surface", "surface_2", "surface_3", "text",
                              "text_muted", "text_faint", "border", "border_strong",
                              "success", "warning", "danger", "info",
                              "nav_bg", "nav_fg", "nav_border"):
                continue
            py_val = (T._BASE_LIGHT if theme == "root" else {}).get(py_key)
            if py_val is None:
                continue
            # 颜色类必须逐字相等；rgba/格式差异在 token 里也逐字比
            if css_val.lower() != str(py_val).lower():
                diffs.append("  [%s] %-14s tokens=%s  _BASE_LIGHT=%s"
                             % (theme, py_key, css_val, py_val))
    assert not diffs, (
        "themes.py 与 tokens.css 漂移：\n" + "\n".join(diffs)
        + "\n提示：两份真相源各管一个渲染面（见模块 docstring 第 4 条），必须同步。")


def test_admin_has_no_theme_token_injection():
    """后台 admin 的主题**只能**来自 tokens.css —— 它没有任何 JS 注入。

    这条是钉住「两份真相源都得改」这个事实，防止以后有人看到「SPA 已经被
    applyThemeTokens 覆盖」就只改 themes.py，把后台留成旧配色。

    真实链路（v3.25.0 实测）：
    - 前台 SPA：`vue-frontend/src/store.js: applyThemeTokens()` 逐个 setProperty
      写 :root，会**覆盖** tokens.css；
    - 后台 admin：`myblog/templates/admin/*.html` + `admin.css` 里**零**
      setProperty / applyThemeTokens，颜色只可能来自 myblog/static/tokens.css；
    - `{{ theme_css }}`（app.py:621）只含 --theme-radius / --theme-font-size，
      **不含任何颜色** —— 早先版本注释称它「整体覆盖 CSS 变量」是错的。
    """
    admin_dir = ROOT / "myblog" / "templates" / "admin"
    offenders = []
    for path in list(admin_dir.rglob("*.html")) + [ROOT / "myblog" / "static" / "admin.css"]:
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "setProperty" in line or "applyThemeTokens" in line:
                offenders.append("  %s:%d %s" % (path.relative_to(ROOT), i, line.strip()))
    assert not offenders, (
        "后台出现主题注入代码 —— myblog/static/tokens.css 不再是后台唯一来源，\n"
        "test_base_light_matches_token_files 与本文件的对比度守卫都需重新评估：\n"
        + "\n".join(offenders))


def test_theme_css_carries_no_colors():
    """`theme_css` 不得开始注入颜色 token（否则又多了第三份真相源）。

    它现在只承载 radius / font-size。若将来有人往里塞颜色，SPA 的
    `applyThemeTokens()` 与内联 style 会互相覆盖，且顺序依赖浏览器特异性 ——
    那时三份真相源的守卫全部失效。
    """
    app = (ROOT / "myblog" / "app.py").read_text(encoding="utf-8")
    start = app.find("theme_css = (")
    assert start != -1, "app.py 里找不到 theme_css 定义，位置已变，请重新评估本守卫"
    snippet = app[start:app.find("\n", app.find(")", start))]
    assert "--accent" not in snippet and "--surface" not in snippet and \
        "--text" not in snippet, (
        "theme_css 开始注入颜色 token（片段：%s）—— 这会形成第三份真相源，\n"
        "且与 applyThemeTokens 的内联 style 互相覆盖（顺序依赖特异性）。" % snippet.strip())


def test_surface_3_is_not_used_as_text_background():
    """`--surface-3` 只用于骨架屏渐变，从不承载文本 —— 不得被当成对比度背景。

    这条不是审美偏好，是**防止假阳性复发**：把 surface-3 算进背景会让
    `--text-muted` 亮色误报 4.08:1 FAIL（真实值 4.46:1，只差 0.04 就达标）。
    """
    css = (ROOT / "vue-frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")
    hits = [ln.strip() for ln in css.splitlines()
            if "var(--surface-3)" in ln and "linear-gradient" not in ln]
    assert not hits, (
        "--surface-3 出现了渐变以外的用法，需重新评估它能否作为文本背景：\n"
        + "\n".join(hits))


def test_contrast_rules_cover_every_foreground_token():
    """契约表不得漏掉任何实际承载文字的 token（防新增 token 忘记校验）。"""
    themes = _parse(TOKEN_FILES[0])
    # 已登记的身份覆盖（前景向）
    covered = {(t, tok) for t, tok, _b, _m, _w in FOREGROUND_PAIRS}
    # 全站零消费的 token：定义了但没人用，不该逼着改配色
    # （grep 全仓，除 tokens.css 自身定义外无任何引用）
    unused = {"--warning", "--accent-hover"}
    # --info 只有 1 处 color: 用法且背景是写死的 #2a3140（不属 token 表面层级），
    # 故不纳入契约表 —— 但它必须仍在 tokens 里定义（theme_center fallback 用）
    out_of_contract = []
    for theme in ("root", "dark"):
        for tok in themes[theme]:
            if not tok.startswith(("--text", "--accent", "--success", "--danger",
                                  "--nav-fg", "--on-accent", "--warning", "--info")):
                continue
            if tok in unused or tok in ("--on-accent", "--info", "--warning"):
                continue
            if (theme, tok) not in covered:
                out_of_contract.append("  [%s] %s" % (theme, tok))
    assert not out_of_contract, (
        "这些 token 承载文字但不在契约表里，新增/改名后会静默失去校验：\n"
        + "\n".join(out_of_contract))

# ---------- v3.25.1：深色「浅底压浅字」缺口守卫 ----------
_GLOBAL_CSS = ROOT / "vue-frontend" / "src" / "styles" / "global.css"


def test_dark_mode_no_light_text_on_light_background():
    """深色模式下不得出现「浅色文字压在浅色背景上」（v3.25.1 线上实测缺陷）。

    **背景**：用户报告深色模式下「天气文字看不清」「文章目录颜色太白」。实测：
    - `.weather-widget .w-text` 写死 `#333`、**深色无覆盖** → 深字压深底 1.42:1；
    - `.toc` 容器背景写死 `#fafbfc`、**深色无覆盖**，而 `.toc a` / `.toc-title`
      早已被深色覆盖成浅灰（`#c7ccd1` / `#b9bfc6`）→ **浅字压白底 1.56 / 1.79:1**。

    **为什么这类缺陷守得住**：它不是「忘了加某个 token」，而是**两个方向相反的
    遗漏碰在一起** —— 容器停在亮色、文字却跟着深色翻了。单独看任一半都合理，
    只有把它们放到同一上下文算对比度才暴露。故这条守卫做**交叉比对**：
    找出「写了深色文字覆盖」的选择器，再找它所在容器的背景是否被深色覆盖。

    **为什么不用「背景必须 token 化」当判据**：那样会误杀 8 处**合法**的浅底
    （`.post-body pre` 代码块 / `.reward-box` / `.trend-chart` …）—— 它们文字
    没被深色覆盖，保持「深字压浅底」，可读且是设计选择。真正致命的只有
    「两边方向相反」的组合。
    """
    if not _GLOBAL_CSS.exists():
        pytest.skip("前端样式不存在")
    css = _GLOBAL_CSS.read_text(encoding="utf-8")

    def _lum(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    def _ratio(f, b):
        a, c = _lum(f), _lum(b)
        return (max(a, c) + 0.05) / (min(a, c) + 0.05)

    def _strip_comment(sel):
        """剥掉选择器里的 CSS 注释。

        ⚠️ **这是本守卫最容易写错的地方**（变异验证抓出来的假绿灯）：
        `global.css` 里大量写成 `/* TOC（v3.4.1：…） */.toc {`，
        注释与选择器**同行**。不剥掉的话 `light_bg` 的 key 会变成
        `/* TOC（…） */.toc`，而 `dark_text` 的 key 是干净的 `.toc a` ——
        两边永远匹配不上，守卫恒绿、形同虚设。
        """
        return re.sub(r"/\*.*?\*/", "", sel).strip()

    # 收集「深色块里被显式改成浅色的文字」：选择器 -> 颜色
    dark_text = {}
    for m in re.finditer(r'\[data-theme="dark"\]\s+([^{]+)\{([^}]*)\}', css):
        sel, body = _strip_comment(m.group(1)), m.group(2)
        # ⚠️ 这里必须是 \s 不是 /s —— 用 bash heredoc 写本文件时 Git Bash 会把
        #    `\s` 转成 `/s`（MSYS 路径转换），正则当场失效、守卫恒绿形同虚设。
        #    **含正则的 Python 一律用 Write/Edit 工具写，不要走 shell heredoc。**
        cm = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})", body)
        if cm and _lum(cm.group(1)) > 0.5:          # 只关心浅色字
            dark_text[sel] = cm.group(1)

    # 收集「深色块里写了背景的容器」：选择器 -> 颜色
    # ⚠️ **var() 必须算已覆盖**（变异验证抓出来的假阳性）：`.search-tag` /
    #   `.replying-tip` 用的是 `background: var(--surface-2)` 而不是裸 hex，
    #   只收 hex 会把它们误报成缺陷。判据是「有没有写深色背景」，不是「用什么写法」。
    dark_bg = {}
    for m in re.finditer(r'\[data-theme="dark"\]\s+([^{]+)\{([^}]*)\}', css):
        sel, body = _strip_comment(m.group(1)), m.group(2)
        bm = re.search(r"background(?:-color)?:\s*([^;}]+)", body)
        if bm:
            dark_bg[sel] = bm.group(1).strip()

    # 收集亮色（无深色覆盖）的写死背景
    light_bg = {}
    for m in re.finditer(r'([^{}]+)\{([^}]*)\}', css):
        sel, body = _strip_comment(m.group(1)), m.group(2)
        if '[data-theme="dark"]' in sel:
            continue
        for bm in re.finditer(r'background(?:-color)?:\s*(#[0-9a-fA-F]{6})', body):
            for part in sel.split(","):
                light_bg[part.strip()] = bm.group(1)

    # ⚠️ **判据必须落在「容器」身上，不能落在文字选择器身上**（变异验证抓出来的
    #   第二个假绿灯）：第一版写的是 `if sel in dark_bg: continue`，但 sel 是
    #   `.toc-title`（文字），而深色背景写在 `.toc`（容器）上 —— 精确匹配永远
    #   不中，于是修好了也照样报。必须先定位所属容器，再看**容器**有没有深色覆盖。
    problems = []
    for sel, fg in dark_text.items():
        # 找它落在哪个亮底容器里
        for container, bg in light_bg.items():
            if container == "html" or not container:
                continue
            if not (sel.startswith(container) or container in sel):
                continue
            if container in dark_bg:
                continue                              # 容器自己已深色化 → 安全
            ratio = _ratio(fg, bg)
            if ratio < 4.5:
                problems.append(
                    "  [%s] 深色字 %s 压在写死浅底 %s（%s）上 = %.2f:1 < 4.5"
                    % (sel, fg, bg, container, ratio))
    assert not problems, (
        "深色模式下出现「浅字压浅底」（给容器补深色背景覆盖，或别把文字改浅）：\n"
        + "\n".join(problems))


def test_dark_mode_no_dark_text_left_behind():
    """深色模式下不得有「写死的深色文字没跟着翻浅」（v3.25.1 天气组件实测缺陷）。

    与上一条守卫是**相反方向**的两个缺陷：
    - 上一条：容器停在亮色、文字却翻浅 → 浅字压浅底；
    - 这一条：文字写死深色且**深色无覆盖** → 深字压深底。

    实测样本：`.weather-widget .w-text` 写死 `color: #333`，深色块里只覆盖了
    `.w-btn` / `.w-input`，**漏了 `.w-text`** → 深色模式下 #333 压在
    `--bg`(#15171a) 上只有 1.42:1，用户报告「看不清」。

    **为什么判据要排除「落在浅底容器里」的选择器**：`.post-body pre` /
    `.post-body code` 这类代码块在深色下**刻意保持浅底**（设计选择），里面的
    深色字压浅底是**正确的**，不能报。故先排除落在已知浅底容器内的选择器，
    剩下的才按「压在最深表面 --bg」估算。
    """
    if not _GLOBAL_CSS.exists():
        pytest.skip("前端样式不存在")
    css = _GLOBAL_CSS.read_text(encoding="utf-8")

    def _lum(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    def _strip(sel):
        return re.sub(r"/\*.*?\*/", "", sel).strip()

    # 深色块里被覆盖到的选择器（无论改了什么属性，都算「照顾到了」）
    dark_covered = set()
    for m in re.finditer(r'\[data-theme="dark"\]\s+([^{]+)\{', css):
        for part in _strip(m.group(1)).split(","):
            dark_covered.add(part.strip())

    # 有深色背景覆盖的容器（其内部的写死深色字是安全的）
    dark_bg_containers = set()
    for m in re.finditer(r'\[data-theme="dark"\]\s+([^{]+)\{([^}]*)\}', css):
        if re.search(r"background(?:-color)?:\s*[^;}]+", m.group(2)):
            for part in _strip(m.group(1)).split(","):
                dark_bg_containers.add(part.strip())

    # 亮色侧写死背景的容器（浅底，其内部的深色字是安全的）
    light_bg_containers = {}
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        sel = _strip(m.group(1))
        if '[data-theme="dark"]' in sel:
            continue
        for bm in re.finditer(r"background(?:-color)?:\s*(#[0-9a-fA-F]{3,6})", m.group(2)):
            for part in sel.split(","):
                light_bg_containers[part.strip()] = bm.group(1)

    # 深色模式下的页面底色 --bg
    dblk = css.split('[data-theme="dark"]')[1] if '[data-theme="dark"]' in css else ""
    m_bg = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", dblk)
    page_bg = m_bg.group(1) if m_bg else "#15171a"

    problems = []
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        sel = _strip(m.group(1))
        if '[data-theme="dark"]' in sel:
            continue
        # ⚠️ 必须是 {3,6} 不是 {6}（变异验证抓出来的第三个失效点）：
        #   出事的 `.w-text` 用的正是 **3 位** 简写 `#333`，只认 6 位会让
        #   整条守卫对它视而不见 —— 变异删掉修复后仍全绿。
        cm = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{3,6})\b", m.group(2))
        if not cm:
            continue
        fg = cm.group(1)
        if _lum(fg) >= 0.2:                     # 只关心「深色字」
            continue
        for part in sel.split(","):
            p = part.strip()
            if not p or p == "html":
                continue
            if p in dark_covered:               # 已有深色覆盖 → 安全
                continue
            in_light_box = any(
                p.startswith(c) or c in p for c in light_bg_containers if c)
            in_dark_box = any(
                p.startswith(c) or c in p for c in dark_bg_containers if c)
            if in_light_box or in_dark_box:     # 落在某个有背景的容器里 → 交给上一条守
                continue
            ratio = (_lum(page_bg) + 0.05) / (_lum(fg) + 0.05)
            if _lum(fg) > _lum(page_bg):
                ratio = (_lum(fg) + 0.05) / (_lum(page_bg) + 0.05)
            # ⚠️ 门槛刻意取 2.5 而非 4.5（实测校准）：4.5 会带出 5 处**状态色**提示
            #   （.apply-msg.err #c0392b 3.30 / .comment-status.error #d93025 3.76 …）。
            #   它们是「偏低但可读」，与天气那种「1.42 等于看不见」不是一个性质，
            #   一并报进来会淹没真信号、还会逼着改品牌色。2.5 只收真正不可读的。
            #   那 5 处已另立待办，不在此守卫射程内。
            if ratio < 2.5:
                problems.append(
                    "  [%s] 写死深字 %s 且深色无覆盖 → 压在 --bg %s 上 = %.2f:1 < 4.5"
                    % (p, fg, page_bg, ratio))
    assert not problems, (
        "深色模式下有写死的深色文字没跟着翻浅（补 [data-theme=\"dark\"] 的 color 覆盖）：\n"
        + "\n".join(sorted(set(problems))))
