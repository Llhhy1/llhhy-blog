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
_BASE_LIGHT = {
    "accent": "#1a73e8", "accent_hover": "#1765cc",
    "accent_soft": "rgba(26,115,232,.10)", "on_accent": "#ffffff",
    "bg": "#f7f8fa", "surface": "#ffffff", "surface_2": "#f4f6f8", "surface_3": "#e9ecef",
    "text": "#2c2c2c", "text_muted": "#6b7280", "text_faint": "#9aa0a6",
    "border": "#ececec", "border_strong": "#d9dde3",
    "success": "#188038", "warning": "#e8a33d", "danger": "#e5484d", "info": "#1a73e8",
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
    accent_d = _oklch_clamp_l(accent, 0.62, 0.72)
    accent_hover = _oklch_clamp_l(accent, 0.54, 0.64)
    success = _oklch_clamp_l(light.get("success", "#188038"), 0.66, 0.74)
    warning = _oklch_clamp_l(light.get("warning", "#e8a33d"), 0.66, 0.74)
    danger = _oklch_clamp_l(light.get("danger", "#e5484d"), 0.64, 0.72)
    dark = {
        "accent": accent_d, "accent_hover": accent_hover,
        "accent_soft": _rgba(accent_d, 0.16), "on_accent": "#ffffff",
        "bg": bg, "surface": surface, "surface_2": surface_2, "surface_3": surface_3,
        "text": "#d7d9dc", "text_muted": "#9aa0a6", "text_faint": "#6b7280",
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


def _make_pack(pid, name, en, desc, accent, tags=None, **tweaks):
    light = dict(_BASE_LIGHT)
    light["accent"] = accent
    at = hex_to_oklch(accent) or (0.6, 0.12, 0.0)
    light["accent_hover"] = oklch_to_hex(max(0.0, at[0] - 0.06), at[1], at[2])
    light["accent_soft"] = _rgba(accent, 0.10)
    light["info"] = accent
    light.update(tweaks)
    dark = derive_dark(light)
    return {"id": pid, "name": name, "en": en, "desc": desc,
            "tags": tags or [], "light": light, "dark": dark}


THEME_PRESETS = [
    _make_pack("classic-blue", "经典蓝", "Classic Blue", "沉稳专业的默认蓝，百搭不过时", "#1a73e8",
               tags=["经典", "商务"]),
    _make_pack("aurora-green", "极光绿", "Aurora Green", "清新自然的翠绿，阅读友好", "#12b886",
               tags=["自然", "清新"]),
    _make_pack("twilight-purple", "暮山紫", "Twilight Purple", "神秘优雅的紫调，科技感十足", "#7c5cff",
               tags=["科技", "优雅"]),
    _make_pack("maple-orange", "枫叶橙", "Maple Orange", "温暖活力的橙红，热情醒目", "#ff6b35",
               tags=["活力", "暖色"]),
    _make_pack("rose-red", "玫瑰红", "Rose Red", "浪漫明快的红，强调与号召力强", "#e5484d",
               tags=["热情", "强调"]),
    _make_pack("lime-citrus", "青柠", "Lime Citrus", "轻盈酸爽的草绿，年轻有生气", "#65a30d",
               tags=["年轻", "自然"]),
    _make_pack("deep-ocean", "深海蓝", "Deep Ocean", "通透的湖蓝，冷静而专注", "#0ea5e9",
               tags=["冷静", "专注"]),
    _make_pack("terracotta", "赤陶", "Terracotta", "大地色赤陶，复古文艺范", "#c2410c",
               tags=["复古", "文艺"]),
    _make_pack("sakura-pink", "樱粉", "Sakura Pink", "柔和的樱粉，温柔治愈", "#e64980",
               tags=["温柔", "治愈"], bg="#fdf6f9", surface="#ffffff", surface_2="#fbeef3",
               surface_3="#f6dde7", border="#f3dfe7", border_strong="#e9c9d6"),
    _make_pack("graphite", "石墨", "Graphite", "中性灰黑，极简高级无彩色", "#495057",
               tags=["极简", "中性"]),
    _make_pack("indigo", "靛蓝", "Indigo", "深邃的靛蓝，知性而沉静", "#4f46e5",
               tags=["知性", "沉静"]),
    _make_pack("teal", "松石", "Teal", "清新的松石绿，平衡而现代", "#0d9488",
               tags=["现代", "平衡"], bg="#f3faf9", surface="#ffffff", surface_2="#e9f6f4",
               surface_3="#d7efeb", border="#e0efec", border_strong="#c4e2dd"),
    _make_pack("amber-gold", "琥珀金", "Amber Gold", "贵气的琥珀金，明亮有质感", "#ca8a04",
               tags=["贵气", "明亮"]),
    _make_pack("cyan-electric", "电光青", "Cyan Electric", "高饱和的电光青，未来感拉满", "#06b6d4",
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
