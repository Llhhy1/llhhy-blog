# -*- coding: utf-8 -*-
"""主题中心（v3.16.0）：预设主题包 + OKLCH 色彩推导。

设计要点
--------
- ``THEME_PRESETS``：14 套精心调配的主题包，仅定义「亮色」token；
  暗色变体由 :func:`derive_dark` 基于 OKLCH 自动推导（替换历史硬编码暗色块）。
- OKLCH 为现代感知均匀色彩空间（Björn Ottosson 规范），纯标准库实现、零依赖；
  推导保证「同色相、暗色协调、对比可读」，每个亮色主题都得到一套配套暗色。
- 单一真相源：暗色只在后端算一次（存 Setting），前后台共用，避免两套色彩不一致。
- 降级：任意色彩解析失败都回退默认值，绝不抛异常导致页面 500。
"""
import math


# ---------- OKLCH 色彩工具（纯标准库，sRGB <-> OKLab <-> OKLCH）----------
def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c):
    c = 1.055 * (c ** (1 / 2.4)) - 0.055 if c > 0.0031308 else 12.92 * c
    return max(0.0, min(255.0, c * 255.0))


def hex_to_rgb(h):
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_to_hex(rgb):
    return "#" + "".join("%02x" % max(0, min(255, int(round(x)))) for x in rgb)


def hex_to_oklch(h):
    rgb = hex_to_rgb(h)
    if not rgb:
        return None
    r, g, b = (_srgb_to_linear(x) for x in rgb)
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l_ ** (1.0 / 3), m_ ** (1.0 / 3), s_ ** (1.0 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.sqrt(a * a + bb * bb)
    H = math.atan2(bb, a)
    return (L, C, H)


def oklch_to_hex(L, C, H):
    L = max(0.0, min(1.0, L))
    C = max(0.0, C)
    a = C * math.cos(H)
    bb = C * math.sin(H)
    l_ = L + 0.3963377774 * a + 0.2158037573 * bb
    m_ = L - 0.1055613458 * a - 0.0638541728 * bb
    s_ = L - 0.0894841775 * a - 1.2914855480 * bb
    l_, m_, s_ = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    b = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return rgb_to_hex((_linear_to_srgb(r), _linear_to_srgb(g), _linear_to_srgb(b)))


def _oklch_clamp_l(h, lo, hi):
    """把颜色亮度 L 钳制到 [lo, hi]，保持色相/彩度（用于暗色下提亮保证对比）。"""
    t = hex_to_oklch(h)
    if not t:
        return h
    L, C, H = t
    return oklch_to_hex(max(lo, min(hi, L)), C, H)


def _rgba(h, alpha):
    rgb = hex_to_rgb(h)
    if not rgb:
        return "rgba(0,0,0,%s)" % alpha
    return "rgba(%d,%d,%d,%s)" % (rgb[0], rgb[1], rgb[2], alpha)


# ---------- 默认亮色 token（与 tokens.css 一致）----------
# v3.25.0：WCAG 对比度修正。**本字典是前台 SPA 的运行时主题源** ——
# vue-frontend/src/store.js 的 applyThemeTokens() 会把 theme_tokens 逐个
# `setProperty("--surface-2", …)` 写到 :root，覆盖 tokens.css。
# ⚠️ 更正：早先注释称 `{{ theme_css }}` 会「整体覆盖 CSS 变量」是**错的**——
# theme_css 只含 --theme-radius / --theme-font-size，不含任何颜色。且后台
# admin 完全没有 JS 注入，myblog/static/tokens.css 是后台**唯一**主题来源。
# 所以两份真相源都得改，由 test_base_light_matches_token_files 钉住同值。
_BASE_LIGHT = {
    "accent": "#196ddd", "accent_hover": "#1765cc",
    "accent_soft": "rgba(25,109,221,.10)", "on_accent": "#ffffff",
    "bg": "#f7f8fa", "surface": "#ffffff", "surface_2": "#f4f6f8", "surface_3": "#e9ecef",
    # text_faint 走**大字档 3:1**（2.44 -> 3.51）：强拉到 4.5 会与 text_muted
    # 亮度差仅 0.003，三档层级视觉塌成两档。取舍理由见 test_wcag_contrast.py。
    # ⚠️ 这三个值会被 _make_pack / _default_theme 用 _muted_for / _faint_for 按
    # **本主题真实表面**重新求解（sakura-pink / teal 的 surface_2 更浅，写死值在
    # 它们身上连 muted 都跌到 4.35 / 4.43 < 4.5）。此处存的是**基准表面 #f4f6f8
    # 上的求解结果**，改这里必须同步两份 tokens.css。
    "text": "#2c2c2c", "text_muted": "#6a717f", "text_faint": "#7d838f",
    "border": "#ececec", "border_strong": "#d9dde3",
    # danger 亦作 .btn.danger 底色配白字（14px），需 4.5:1（3.91 -> 4.53）
    "success": "#188038", "warning": "#e8a33d", "danger": "#d34247", "info": "#196ddd",
    "nav_bg": "#ffffff", "nav_fg": "#555555", "nav_border": "#ececec",
    "radius_sm": "8px", "radius_md": "12px", "radius_lg": "20px", "radius_pill": "999px",
    "shadow_sm": "0 1px 3px rgba(0,0,0,.03)", "shadow_md": "0 6px 18px rgba(20,30,50,.08)",
    "shadow_lg": "0 16px 48px rgba(0,0,0,.20)",
    "font_sans": "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif",
    "font_size_base": "15px", "line_height_base": "1.7",
}


def derive_dark(light):
    """从亮色 token 推导协调的暗色 token（OKLCH）。

    策略：暗色表面以近黑为底、极轻 accent 色调（C≈0.012）保持品牌协调；
    文本/边框用统一中性暗值；accent 与状态色在暗色下提亮到可读对比。
    """
    light = light or {}
    accent = light.get("accent", "#1a73e8")
    at = hex_to_oklch(accent) or (0.6, 0.12, 0.0)
    H = at[2]

    def surf(L):
        return oklch_to_hex(L, 0.012, H)

    bg = surf(0.165)
    surface = surf(0.205)
    surface_2 = surf(0.245)
    surface_3 = surf(0.29)
    border = surf(0.30)
    border_strong = surf(0.37)
    # v3.25.0：accent_d 的 L 下界从 0.62 提到 0.66。暗色下 accent 同时是
    # 「链接文字色」（126 处 color: var(--accent)）和「主按钮底色」，下界 0.62
    # 时 7/14 preset 作前景只有 3.96~4.45:1（classic-blue 4.36、indigo 4.02、
    # twilight-purple 4.00）。提到 0.66 后 14/14 全部 >= 4.5，且与上界 0.72 一样
    # 不会让白字/深字压其上崩（on_accent 自适应，见 _on_accent_for）。
    accent_d = _oklch_clamp_l(accent, 0.66, 0.72)
    accent_hover = _oklch_clamp_l(accent, 0.54, 0.64)
    success = _oklch_clamp_l(light.get("success", "#188038"), 0.66, 0.74)
    warning = _oklch_clamp_l(light.get("warning", "#e8a33d"), 0.66, 0.74)
    # v3.25.0：danger 的 L 从「上界 0.58」改为「下界 0.66」。它有**两个身份**：
    # - 底色：`.btn.danger` 配 `color: var(--on-accent)`（全站确认继承基类，
    #   非写死白字）+ global.css:53 通知角标 `color: var(--on-accent)`；
    # - 前景：admin.css:315 `.link-danger`（13px 危险操作链接，无背景覆盖）
    #   与 admin.css:604 `.side-logout:hover`，暗色下均无覆盖。
    # ⚠️ **两个身份在暗色深底上互斥，无交集**（实测 L 扫 0.30~0.78 全域）：
    # 白字压它 >= 4.5 需 L <= 0.60，而它作前景 >= 4.5 需 L >= 0.65。
    # 解法不是折中，而是**让 on_accent 自适应**（见 _on_accent_for）：把 danger
    # 提到 L=0.66（作前景 4.76:1），按钮字改由深色 on_accent 压（4.76~5.66:1）。
    # 取下界 0.66 而非上界，是为了让 admin 的 13px 危险链接可读 —— 它无背景
    # 色块帮忙，只能靠自身够亮。
    # ⚠️ 下界 0.67 而非 0.66：0.66 档（#ec5a5c）在 themes.py 自己的暗色表面上
    # 是 4.76:1，但 tokens.css 的暗色表面略亮（#23272e vs #1d2126），同一色
    # 在那里只有 4.41:1 —— **两份真相源的表面不同，同一个值不可能都达标**。
    # 取 0.67（#f05d5f）后两套表面分别 4.59 / 4.96，on_accent 压它 5.89。
    # 改这个下界时必须同时验算 themes.py 与 tokens.css 两套表面。
    danger = _oklch_clamp_l(light.get("danger", "#d34247"), 0.67, 0.72)
    # v3.25.0：暗色整条文本链同样按真实表面联动求解。
    # ⚠️ 基准必须是**设计基准灰**而不是最亮的 text —— 从 text 往下走时
    # `min_gap` 一满足就停，muted 会停在 L=0.62（对比 10.47:1，几乎和 text 同亮，
    # 视觉上「副文本」消失）。语义上 muted 是一档**固定的弱化灰**，不是
    # 「text 减一点点」。
    text_muted_dark = _muted_for(surface_2, "#9aa0a6", light=False)
    text_faint_dark = _faint_for(surface_2, text_muted_dark, light=False)
    # v3.25.0：on_accent 不再写死白字。暗色 accent / danger 都被提到 L>=0.66
    # （否则深底上当文字不够亮），**白字压它们必然崩** —— 实测 14/14 preset 的
    # 白字压 accent_d 只有 2.43~4.06:1。改为按底色亮度自适应取白字或深字。
    # ⚠️ 它同时压在 accent 与 danger 两个色块上（.btn 基类 + .btn.danger 都用
    # var(--on-accent)），所以必须对**两者都**达标 —— 亮色下 danger 更亮，
    # 是更严的那一侧。详见 _on_accent_for 的 docstring。
    on_accent = _on_accent_for(accent_d, danger, page_bg_hex=bg)
    dark = {
        "accent": accent_d, "accent_hover": accent_hover,
        "accent_soft": _rgba(accent_d, 0.16), "on_accent": on_accent,
        "bg": bg, "surface": surface, "surface_2": surface_2, "surface_3": surface_3,
        "text": "#d7d9dc", "text_muted": text_muted_dark, "text_faint": text_faint_dark,
        "border": border, "border_strong": border_strong,
        "success": success, "warning": warning, "danger": danger, "info": accent_d,
        "nav_bg": surface, "nav_fg": "#d7d9dc", "nav_border": border,
        "shadow_sm": "0 1px 3px rgba(0,0,0,.40)",
        "shadow_md": "0 6px 18px rgba(0,0,0,.35)",
        "shadow_lg": "0 16px 48px rgba(0,0,0,.50)",
    }
    # 非色彩 token（圆角/字体）从亮色继承
    for k in light:
        if k.startswith(("radius_", "font_", "line_")):
            dark.setdefault(k, light[k])
    return dark


def _tier_for(surface_hex, base_hex, target, lighter, min_gap=0.06,
              always_move=False):
    """让 base_hex（设计基准灰）在**本主题真实表面**上达标，必要时微调。

    ⚠️ **约束顺序不能反**（实测踩过）：先用 `min_gap` 卡住「与上一档拉开足够
    距离」，再在满足层级的候选里找第一个达标的。写成「先扫到达标即返回、层级
    用 floor 兜底」会产出 #454545/#505050 这种三档挤成一团的值 —— 对比度数字
    全绿，但 muted 紧贴 text、faint 紧贴 muted，肉眼分不出三档。

    `min_gap` 0.06 是实测下界：WCAG 亮度差 0.06 大致对应「灰阶上肉眼可辨的一档」，
    低于此值（实测 0.026 / 0.024）三档视觉上塌成两档。

    ⚠️ `always_move` 不能省：早退「基准已达标就原样返回」会让 faint 直接等于
    muted（实测 14/14 preset 的 text_muted 与 text_faint 全部相同，间隔 0.000）。
    faint 的语义就是「比 muted 再弱一档」，即使 muted 已达标也**必须**拉开距离 ——
    它要守的是层级约束，不是把 muted 复制一份。

    ⚠️ `min_gap` 不能反过来阻塞达标修复（sakura-pink / teal）：这两套的
    surface_2 更浅，muted 只差 0.07:1 就达标，压暗幅度不足 min_gap 就返回 None
    → 退回基准 → 仍不达标。所以扫完全程若**无一满足层级+达标**，再退一档做
    「只要达标就行」的二次扫描（对比度是硬底线，层级是可辨性偏好）。

    方向：`lighter` 由主题决定 —— 亮色 True（往白走，离浅底更近 = 更弱），
    暗色 False（往黑走）。
    """
    try:
        base_l = _wcag_lum(base_hex)
    except Exception:                                    # noqa: BLE001
        return None
    if not always_move and _wcag_ratio(base_hex, surface_hex) >= target:
        return base_hex                                  # 基准在本表面达标，不动

    # 「朝更弱方向走」的亮度增量：亮色往白走（L↑，+），暗色往黑走（L↓，-）。
    # ⚠️ 符号别写反：暗色下 span 是 base_l，若用 `+span*t` 会**变亮**，
    # 实测把暗色 faint 推到 L=0.408（比 muted 的 0.348 还亮，语义反了）。
    weak_sign = 1 if lighter else -1
    span = (1.0 - base_l) if lighter else base_l

    def _scan(sign, require_gap):
        """sign=weak_sign 朝更弱方向；反向 -weak_sign 为兜底。"""
        # always_move 时**不能从 i=0 起** —— i=0 的 want_l == base_l，
        # _at_lum 会返回基准色本身，于是 faint 直接等于 muted（实测暗色 14/14
        # preset 间隔 0.000）。从满足 min_gap 的最小 t 起扫。
        start = 0.0
        if always_move:
            # 二分找出使亮度差首次 >= min_gap 的 t
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = (lo + hi) / 2
                if abs(span * mid) >= min_gap:
                    hi = mid
                else:
                    lo = mid
            start = hi
        for i in range(int(start * 200), 201):
            t = i / 200
            want_l = base_l + sign * span * t
            want_l = min(max(want_l, 0.0), 0.999)
            # ⚠️ `_at_lum` 的第三参只该看 `want_l` 相对 base_l 的**方向**，
            # 与主题的 `lighter` 无关：sign>0 -> 要调亮（往白插值分支），
            # sign<0 -> 要调暗（缩放分支）。曾经写成 `lighter if sign>0 else
            # not lighter`，暗色（lighter=False）下 sign=-1 会传 True 进变亮分支，
            # 而变亮分支 `t=0` 就返回基准色本身 —— 兜底轮直接返回 muted，
            # 表现为 14/14 preset 的 text_faint == text_muted（间隔 0.000）。
            cand = _at_lum(base_hex, want_l, sign > 0)
            if cand is None:
                continue
            if require_gap and abs(_wcag_lum(cand) - base_l) < min_gap:
                continue                                 # 层级优先，不许贴脸达标
            if _wcag_ratio(cand, surface_hex) < target:
                continue
            return cand
        return None

    # 三轮：先守层级再达标（弱化方向）→ 只要达标（弱化方向）→ 兜底反向。
    # 兜底存在的理由（实测）：sakura-pink / teal 的 surface_2 比基准浅，
    # muted 要达标只能**变强**（偏离「弱于 text」语义）。这两套主题的浅底本身
    # 就压缩了层级空间 —— 此时「可读性」优先级高于「弱化语义」，否则永远不达标。
    return (_scan(weak_sign, True) or _scan(weak_sign, False)
            or _scan(-weak_sign, True) or _scan(-weak_sign, False))


def _on_accent_for(*block_hexes, page_bg_hex, target=4.5):
    """解出压在若干 `--accent` 类色块**上面**的文字色（`--on-accent`）。

    为什么需要它（v3.25.0 实测）：这些色块在暗色下都被提到 L>=0.66（否则深底上
    当文字不够亮），**白字压它们必然崩** —— 实测 14/14 preset 的白字压 accent_d
    只有 2.43~4.06:1。`button, .btn { background: var(--accent); color: var(--on-accent) }`
    是全站主按钮，这就是实打实看不清。

    取值策略：在「白」和「页面自身的深色」两端各试一次，取**对所有色块都达标**者：
    - 白字能达标就用白字（保持浅色主题的既有观感）；
    - 否则用页面深色 —— 它天然与色块同族（都由 accent 色相派生），观感协调。
    - 仍不达标就把文字往黑压到刚好达标。

    ⚠️ `*block_hexes` 是**所有**会被它压住的色块（当前是 accent 与 danger）。
    只按其中一个取值会让另一个崩 —— danger 在亮色下比 accent 亮，是更严的一侧。
    少传一个就是漏守卫，实测正是这么漏掉 `.btn.danger` 的。

    ⚠️ `page_bg_hex` 是**页面背景**，不是色块。别把两者搞混：早先一版误把
    accent_d 当页面背景去压，产出 on_accent = accent 的暗化同色，压其上只有
    1.70:1（等于同色），14/14 全崩。
    """
    try:
        _wcag_lum(page_bg_hex)
        for b in block_hexes:
            _wcag_lum(b)
    except Exception:                                    # noqa: BLE001
        return "#ffffff"
    for b in block_hexes:
        if _wcag_ratio("#ffffff", b) >= target:
            continue                                    # 白字在这个色块上够用
        # 有色块白字不够 -> 整体走深字路线
        for cand in (page_bg_hex,):
            if all(_wcag_ratio(cand, b) >= target for b in block_hexes):
                return cand
        cur = _wcag_lum(page_bg_hex)                     # 逐级往黑压
        for step in range(1, 101):
            c = _at_lum(page_bg_hex, max(0.0, cur - step * 0.01), False)
            if c is None:
                break
            if all(_wcag_ratio(c, b) >= target for b in block_hexes):
                return c
        return "#000000"
    return "#ffffff"


def _muted_for(surface_hex, text_hex, light=True):
    """解出达标的 muted（副文本，正文档 4.5:1），语义是「比 text 更弱」。

    必须联动的原因：sakura-pink / teal 的 surface_2 更浅（#fbeef3 / #e9f6f4），
    设计基准灰 #6a717f 在它们身上只有 4.35 / 4.43:1，跌破正文门槛；而在
    classic-blue（#f4f6f8）上是 4.53:1 达标。**同一基准在不同表面上结论相反**，
    所以每套主题都必须按自己的表面重算，不能早退。

    方向与 _faint_for 一致（亮色往白走、暗色往黑走）。
    """
    try:
        _wcag_lum(surface_hex)
        _wcag_lum(text_hex)
    except Exception:                                    # noqa: BLE001
        return "#6a717f" if light else "#9aa0a6"
    fallback = "#6a717f" if light else "#9aa0a6"
    # ⚠️ always_move=False：muted 以**设计基准灰**为准，只在本表面不达标时微调
    # （早退在这里是正确的 —— muted 是「固定的一档弱化灰」，不需要额外拉开距离；
    # 需要拉开的是 faint）。
    return _tier_for(surface_hex, fallback, 4.5, light) or fallback


def _faint_for(surface_hex, muted_hex, light=True):
    """解出「达标且层级可辨」的 faint 值（v3.25.0）。

    ⚠️ **方向随主题翻转**（判反过两次，务必记牢）：
    - **亮色**：背景浅，文字越亮 -> 对比越低。语义「faint 最弱」= 亮度**更高**，
      从 muted **向上**找。
    - **暗色**：背景深，文字越暗 -> 对比越低。语义「faint 最弱」= 亮度**更低**，
      从 muted **向下**找。

    判据唯一：在 sRGB 上按 WCAG 亮度求解。⛔ 不要借 OKLCH 的 L ——
    它与 WCAG 相对亮度非线性，拿它当达标判据等于没判（实测据此产出过
    反向 + 亮度冲到 5.09/6.72 的荒诞结果）。

    为什么不能写死全局常量：sakura-pink / teal 自定义了**更浅**的 surface_2
    （#fbeef3 / #e9f6f4），写死的 #8a8f95 在这两套上只有 2.89 / 2.94:1，
    连 text_muted 也跌到 4.35 / 4.43（都 < 4.5）—— 所以整条文本链都必须联动。

    门槛分档：亮色 3.0（弱化文本 + 保层级），暗色 4.5（修到位后间隔仍够）。
    """
    target = 3.0 if light else 4.5
    fallback = "#8a8f95" if light else "#888d99"
    try:
        _wcag_lum(surface_hex)
        _wcag_lum(muted_hex)
    except Exception:                                    # noqa: BLE001
        return fallback
    return _tier_for(surface_hex, muted_hex, target, light,
                      always_move=True) or fallback


def _hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "ff"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _wcag_lum(h):
    """WCAG 相对亮度（sRGB 线性化）。"""
    out = []
    for c in _hex_rgb(h)[:3]:
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def _at_lum(hex_color, want_l, lighter):
    """把 hex_color 调到 WCAG 亮度≈ want_l，尽量保色相。

    ⚠️ **变暗必须用二分，不能用比例缩放**（实测踩过）：比例缩放 k = want/cur
    得到的是「sRGB 通道缩放」，但 WCAG 亮度是 sRGB **线性化后**的加权和不认，
    实测 want_l=0.2876 实际只到 0.2282（偏低一大截）。后果是调用方按
    `want_l` 递进扫描时，每一步实际都比预期更暗，ratio 一路下滑到不达标，
    整轮扫空后落到兜底分支 —— 最终返回基准色本身（faint == muted，间隔 0.000）。

    变亮方向用「向白插值 + 取第一个 >= want 的点」是安全的（插值在 sRGB 上，
    单调且不过冲）。

    ⚠️ 畸形 `hex_color` 一律返回 None（v3.25.0 发版审计加固）。`_hex_rgb` 对
    `"red"` / `""` / `None` 会抛 ValueError / AttributeError，而本函数是模块级
    求解器、不该把异常抛给调用方。当前唯一调用方 `_tier_for` 已先用 try/except
    探测过 `base_hex`，故生产路径上畸形值不可达 —— 但「靠调用方守」太脆：
    将来谁在新的调用点直接传 Setting 里的值就炸，且本模块 docstring 明写
    「任意色彩解析失败都回退默认值，绝不抛异常导致页面 500」。返回 None 与
    既有的「目标不可达」语义一致，`_tier_for` 的 `if cand is None: continue`
    已能处理。
    """
    try:
        rgb = _hex_rgb(hex_color)[:3]
        cur = _wcag_lum(hex_color)
    except Exception:                                    # noqa: BLE001
        return None
    if lighter:
        for i in range(201):
            t = i / 200
            cand = tuple(c + (1 - c) * t for c in rgb)
            hx = "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in cand)
            if _wcag_lum(hx) >= want_l:
                return hx
        return None
    # 变暗：二分找最接近 want_l 的缩放系数（保色相）
    # ⚠️ v3.25.0 审计发现此处曾有**两段完全重复的二分**，第一段缺 `else: hi = mid`
    # 且结果被第二段整体覆盖 —— 纯死代码，但它是真陷阱：后来人只会改到第一段，
    # 改完看不到任何效果。现已删除，只保留下方这一段（带 else 的正确版本）。
    # `cur` 已在函数开头的 try 块里取好，这里不再重算。
    if cur <= 0:
        return None
    lo, hi = 0.0, 1.0                     # k=0 -> 全黑，k=1 -> 原色
    for _ in range(40):
        mid = (lo + hi) / 2
        cand = "#%02x%02x%02x" % tuple(int(round(c * mid * 255)) for c in rgb)
        if _wcag_lum(cand) < want_l:
            lo = mid                     # 还太暗，往上走
        else:
            hi = mid
    # ⚠️ **必须取 lo 侧（更暗的那个），不能取 hi**（实测踩过）：hi 满足
    # lum >= want_l，所以返回色总比目标**略亮**。调用方拿它去卡「对比度 >= 门槛」
    # 时就会系统性差一口气 —— 实测目标 L=0.1696 时返回值的实际 ratio 只有
    # 4.11~4.15（前景）/ 4.45~4.50（白字），**全部卡在 4.5 下方**，
    # 而调用方以为已经达标就直接放行。
    # lo 侧是「刚好达到或略低于 want_l」的最亮点，量化误差方向确定为**偏保守**
    # （绝不会高估对比度），这正是求解器该有的失败方向。
    return "#%02x%02x%02x" % tuple(int(round(c * lo * 255)) for c in rgb)


def _wcag_ratio(fg, bg):
    """WCAG SC 1.4.3 对比度：(L1+0.05)/(L2+0.05)。局部实现，避免为一个
    纯算术函数新增模块级依赖（utils 是刻意的纯工具层，不该被塞进东西）。"""
    def rel_lum(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    a, b = rel_lum(fg), rel_lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _make_pack(pid, name, en, desc, accent, tags=None, **tweaks):
    light = dict(_BASE_LIGHT)
    light["accent"] = accent
    at = hex_to_oklch(accent) or (0.6, 0.12, 0.0)
    light["accent_hover"] = oklch_to_hex(max(0.0, at[0] - 0.06), at[1], at[2])
    light["accent_soft"] = _rgba(accent, 0.10)
    light["info"] = accent
    light.update(tweaks)
    # v3.25.0：整条文本链按该主题**真实表面**联动求解。sakura-pink / teal 自定义了
    # 更浅的 surface_2，写死值在它们身上连 muted 都跌到 4.35 / 4.43（< 4.5）。
    #
    # 基准是**设计基准灰**（muted/faint 各自的全局常量），不是 text ——
    # muted 的语义是「一档固定的弱化灰」，不是「text 减一点点」。
    # 若从 text 下移，`min_gap` 一满足就停，muted 会贴在 text 旁边（实测
    # #545454 对比 6.99:1），副文本在视觉上消失。
    # 顺序有依赖：muted 先定（以基准灰为起点向达标推），faint 再以 muted 为起点。必须在 tweaks 之后调。
    _surf = light.get("surface_2") or light["surface"]
    light["text_muted"] = _muted_for(_surf, "#6a717f", light=True)
    light["text_faint"] = _faint_for(_surf, light["text_muted"], light=True)
    dark = derive_dark(light)
    return {"id": pid, "name": name, "en": en, "desc": desc,
            "tags": tags or [], "light": light, "dark": dark}


THEME_PRESETS = [
    _make_pack("classic-blue", "经典蓝", "Classic Blue", "沉稳专业的默认蓝，百搭不过时", "#1a6ddf",
               tags=["经典", "商务"]),
    _make_pack("aurora-green", "极光绿", "Aurora Green", "清新自然的翠绿，阅读友好", "#0d7f5d",
               tags=["自然", "清新"]),
    _make_pack("twilight-purple", "暮山紫", "Twilight Purple", "神秘优雅的紫调，科技感十足", "#7354ec",
               tags=["科技", "优雅"]),
    _make_pack("maple-orange", "枫叶橙", "Maple Orange", "温暖活力的橙红，热情醒目", "#b94f27",
               tags=["活力", "暖色"]),
    _make_pack("rose-red", "玫瑰红", "Rose Red", "浪漫明快的红，强调与号召力强", "#c73e43",
               tags=["热情", "强调"]),
    _make_pack("lime-citrus", "青柠", "Lime Citrus", "轻盈酸爽的草绿，年轻有生气", "#4e7c0b",
               tags=["年轻", "自然"]),
    _make_pack("deep-ocean", "深海蓝", "Deep Ocean", "通透的湖蓝，冷静而专注", "#0b76a9",
               tags=["冷静", "专注"]),
    _make_pack("terracotta", "赤陶", "Terracotta", "大地色赤陶，复古文艺范", "#c2410c",
               tags=["复古", "文艺"]),
    _make_pack("sakura-pink", "樱粉", "Sakura Pink", "柔和的樱粉，温柔治愈", "#bd3c6a",
               tags=["温柔", "治愈"], bg="#fdf6f9", surface="#ffffff", surface_2="#fbeef3",
               surface_3="#f6dde7", border="#f3dfe7", border_strong="#e9c9d6"),
    _make_pack("graphite", "石墨", "Graphite", "中性灰黑，极简高级无彩色", "#495057",
               tags=["极简", "中性"]),
    _make_pack("indigo", "靛蓝", "Indigo", "深邃的靛蓝，知性而沉静", "#4f46e5",
               tags=["知性", "沉静"]),
    _make_pack("teal", "松石", "Teal", "清新的松石绿，平衡而现代", "#0c7d75",
               tags=["现代", "平衡"], bg="#f3faf9", surface="#ffffff", surface_2="#e9f6f4",
               surface_3="#d7efeb", border="#e0efec", border_strong="#c4e2dd"),
    _make_pack("amber-gold", "琥珀金", "Amber Gold", "贵气的琥珀金，明亮有质感", "#966703",
               tags=["贵气", "明亮"]),
    _make_pack("cyan-electric", "电光青", "Cyan Electric", "高饱和的电光青，未来感拉满", "#047a90",
               tags=["未来", "高饱和"]),
]
PRESET_MAP = {p["id"]: p for p in THEME_PRESETS}


def _default_theme(accent):
    light = dict(_BASE_LIGHT)
    light["accent"] = accent
    at = hex_to_oklch(accent) or (0.6, 0.12, 0.0)
    light["accent_hover"] = oklch_to_hex(max(0.0, at[0] - 0.06), at[1], at[2])
    light["accent_soft"] = _rgba(accent, 0.10)
    light["info"] = accent
    # v3.25.0：同 _make_pack，整条文本链按真实表面联动求解
    _surf = light.get("surface_2") or light["surface"]
    light["text_muted"] = _muted_for(_surf, light["text"], light=True)
    light["text_faint"] = _faint_for(_surf, light["text_muted"], light=True)
    dark = derive_dark(light)
    return {"light": light, "dark": dark}


def current_theme():
    """读取当前激活主题，返回 {pack_id, light, dark}。

    优先用 Setting 中持久化的 theme_tokens（含亮/暗完整映射）；
    否则用 accent_color 即时推导默认主题（保证任何情况下都有完整 token）。
    """
    from utils import get_setting
    pack_id = (get_setting("theme_pack") or "").strip()
    raw = get_setting("theme_tokens")
    if raw:
        try:
            data = __import__("json").loads(raw)
            light = data.get("light") or {}
            dark = data.get("dark") or derive_dark(light)
            if light:
                return {"pack_id": pack_id or "custom", "light": light, "dark": dark}
        except Exception:
            pass
    accent = get_setting("accent_color", "#1a73e8") or "#1a73e8"
    t = _default_theme(accent)
    return {"pack_id": pack_id or "default", "light": t["light"], "dark": t["dark"]}
