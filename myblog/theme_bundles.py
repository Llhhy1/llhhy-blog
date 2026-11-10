# -*- coding: utf-8 -*-
"""主题包（Theme Bundle）v5.5.0：把主题从「30 个颜色 token」升级为可分发单元。

一个主题包是 **一份纯 JSON**，同时声明 tokens / 章节配色 / 布局原语 / 动效档 /
文案标签 / 受限 CSS。目录 ``myblog/theme_packs/`` 随部署包分发 —— 部署者想加自己的
主题，扔一个 JSON 进去即可，**不用改 Python 源码**（这是「主题市场」的地基）。

架构约束（ADR-001）
------------------
- **不建表**：当前激活的包 id 存 ``Setting.theme_bundle_id``（KV），沿用既有 Setting。
- **纯声明式**：布局靠 ``data-*`` 属性 + CSS 变量驱动，24 个视图零改动；
  主题包不是代码，因此可被第三方分发而不必审核 JS。
- **前台 SPA 限定**：后台 Jinja2 不读这些字段，v5.4.5 的访客换肤缺席守卫不动。
- **信任边界**：内置包随代码分发，第三方包走同一套 :func:`validate_bundle`。
  其中 ``css`` 是唯一能注入样式的地方，除黑名单外还强制**选择器命名空间**
  （只允许 ``.zh-*`` / ``[data-layout…]`` / ``@media`` 等），避免一份主题包
  把 ``body``、``.btn`` 这类全局选择器改掉、污染整站。
"""
import json
import logging
import os
import re

from flask import has_app_context
from sqlalchemy.exc import SQLAlchemyError

from themes import normalize_custom_theme, validate_accent

logger = logging.getLogger(__name__)

BUNDLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme_packs")
ACTIVE_KEY = "theme_bundle_id"

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

# 布局原语：全部是有限枚举或受夹取的数字。刻意不放任意 CSS / DOM 结构，
# 因为「主题包 = 可分发 JSON」的前提就是表达力可被白名单穷举。
LAYOUT_MODES = ("classic", "chapter", "reading", "bento", "wiki")
CARD_MODES = ("col", "row")
FRAME_MODES = ("normal", "wide", "frameless")
SIDEBAR_MODES = ("auto", "show", "hide")
HERO_MODES = ("required", "optional", "none")
BACKGROUND_MODES = ("flat", "chapter")
MOTION_LEVELS = ("off", "subtle", "full")

# v5.11.0 设计北极星：主题包除了「长什么样」，还要能声明「要让人记住什么」。
# 这组字段不参与渲染，只作为可校验的设计契约 —— 让「平淡」从主观感受变成
# 可断言的红线（见 DESIGN.md 与 tests/test_design_north_star_v5110.py）。
DESIGN_TONES = ("minimal", "maximalist", "retro_futuristic", "organic", "luxury",
                "editorial", "brutalist", "art_deco", "pastel", "industrial")
_MAX_SIGNATURE = 60

# 章节配色：明暗分章需要在**同一页面**同时出现两套底色，现有亮/暗 token
# 是随 data-theme 二选一的，装不下这个语义，所以单独开一组受校验的变量。
PALETTE_KEYS = ("ink", "ink_card", "ink_line", "ink_fg", "ink_muted",
                "paper", "paper_card", "paper_line", "paper_fg", "paper_muted",
                "seal", "watermark", "thumb")

# 文案标签：主题自带的栏目文字。键白名单，值纯文本（禁尖括号，防模板注入）。
LABEL_KEYS = ("eyebrow", "volume", "volume_en", "categories_en",
              "categories_title", "watermark", "hero_badge", "seal")

_MAX_TEXT = 120
_MAX_LABEL = 40
_MAX_CSS = 8000
_CSS_FORBIDDEN = ("url(", "@import", "expression(", "javascript:", "</",
                  "<script", "@font-face", "behavior:", "-moz-binding",
                  "\\", "@namespace", "data:", "vbscript:")
_CSS_SELECTOR_OK = re.compile(
    r"^\s*(?:\.zh-[\w-]+|\[data-layout[^\]]*\]|:root\[data-layout[^\]]*\]"
    r"|@media|@supports|@keyframes|from|to|\d+%|:root)", re.I)


def _as_text(v, limit=_MAX_TEXT, allow_empty=False):
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s and not allow_empty:
        return None
    if len(s) > limit or "<" in s or ">" in s:
        return None
    return s


def _enum(v, choices, default=None):
    """枚举取值：非法一律回落 default（而不是抛异常让页面 500）。"""
    return v if isinstance(v, str) and v in choices else default


def _int_clamp(v, lo, hi, default):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _f_clamp(v, lo, hi, default):
    """浮点夹取：字号跳跃这类比例值允许小数，但仍要有上下界防离谱声明。"""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _css_clean(raw):
    """校验受限 CSS：返回 ``(css, errors)``。

    两道闸：① 危险子串（``url(`` 会让每个访客的浏览器替站主请求第三方地址，
    是实打实的信标，不是洁癖）；② 每个顶层选择器必须落在允许的命名空间内。
    """
    if not isinstance(raw, str) or not raw.strip():
        return "", []
    css = raw.strip()
    errors = []
    if len(css) > _MAX_CSS:
        errors.append("css 超出 %d 字符上限" % _MAX_CSS)
    low = css.lower()
    for sub in _CSS_FORBIDDEN:
        if sub in low:
            errors.append("css 含禁用片段：%s" % sub)
    # 提取每个 `{` 之前的选择器段；@media 内部的选择器同样会被下一轮捕获。
    for m in re.finditer(r"([^{}]+)\{", css):
        seg = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
        for sel in seg.split(","):
            sel = sel.strip()
            if not sel:
                continue
            if not _CSS_SELECTOR_OK.match(sel):
                errors.append("css 选择器越界（只允许 .zh-* / [data-layout…]）：%s" % sel[:40])
    return (css if not errors else ""), errors


def validate_bundle(raw):
    """校验一份主题包，返回 ``(clean, errors)``。

    刻意**不抛异常**：市场里可能躺着别人写的包，坏包最多不出现在列表里，
    不该让整个主题中心 500。缺字段一律补默认值，保证前台永远拿到完整结构。
    """
    errors = []
    if not isinstance(raw, dict):
        return None, ["主题包必须是 JSON 对象"]
    if raw.get("schema") != SCHEMA_VERSION:
        errors.append("schema 版本不支持（需要 %d）" % SCHEMA_VERSION)

    bid = raw.get("id")
    if not isinstance(bid, str) or not _ID_RE.match(bid):
        errors.append("id 非法（只允许小写字母/数字/连字符，2~32 位）")

    name = _as_text(raw.get("name"))
    if not name:
        errors.append("name 缺失或非法")
    desc = _as_text(raw.get("desc"), 300, allow_empty=True) or ""
    en = _as_text(raw.get("en"), 80, allow_empty=True) or ""
    version = _as_text(raw.get("version"), 32, allow_empty=True) or "1.0.0"
    source = _as_text(raw.get("source"), 400, allow_empty=True) or ""
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    tags = [t for t in (_as_text(x, 24) for x in tags) if t][:6]

    # tokens：复用现有 30 键白名单 + OKLCH 暗色推导，不另起一套色彩口径。
    tok_in = raw.get("tokens")
    tok_in = tok_in if isinstance(tok_in, dict) else {}
    light, dark, tok_errors = normalize_custom_theme(tok_in)
    if tok_errors:
        errors.extend("tokens: " + e for e in tok_errors[:10])
        light = dark = None

    # palette：章节专用色，逐个过十六进制校验（与 accent_color 同一口径）。
    pal_in = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
    palette = {}
    for k in PALETTE_KEYS:
        v = pal_in.get(k)
        val, err = validate_accent(v if isinstance(v, str) else "")
        if err or not val:
            errors.append("palette.%s 非法（需 #rgb / #rrggbb）" % k)
        else:
            palette[k] = val

    # labels：缺项给空串，前台自行回退中文默认，不因此判整个包非法。
    lab_in = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
    labels = {}
    for k in LABEL_KEYS:
        v = lab_in.get(k, "")
        s = v if isinstance(v, str) else ""
        if "<" in s or ">" in s or len(s) > _MAX_LABEL:
            errors.append("labels.%s 非法" % k)
        else:
            labels[k] = s[:_MAX_LABEL]

    lay = raw.get("layout") if isinstance(raw.get("layout"), dict) else {}
    bg = raw.get("background") if isinstance(raw.get("background"), dict) else {}
    mot = raw.get("motion") if isinstance(raw.get("motion"), dict) else {}
    # 显式写了个不在枚举里的值 ⇒ **拒绝整包**，不能静默回落。
    # 「站主点了深色主题却悄悄变回经典」比报错难查得多；缺字段才走默认值。
    for sec, key, choices, src in (
            ("layout", "mode", LAYOUT_MODES, lay),
            ("layout", "card", CARD_MODES, lay),
            ("layout", "frame", FRAME_MODES, lay),
            ("layout", "sidebar", SIDEBAR_MODES, lay),
            ("layout", "hero", HERO_MODES, lay),
            ("background", "mode", BACKGROUND_MODES, bg),
            ("background", "texture", ("none", "dots", "grid"), bg),
            ("motion", "level", MOTION_LEVELS, mot)):
        if key in src and src[key] not in choices:
            errors.append("%s.%s 取值不支持：%r" % (sec, key, src[key]))
    layout = {
        "mode": _enum(lay.get("mode"), LAYOUT_MODES, "classic"),
        "card": _enum(lay.get("card"), CARD_MODES, "col"),
        "frame": _enum(lay.get("frame"), FRAME_MODES, "normal"),
        "sidebar": _enum(lay.get("sidebar"), SIDEBAR_MODES, "auto"),
        "hero": _enum(lay.get("hero"), HERO_MODES, "optional"),
        "columns": _int_clamp(lay.get("columns"), 1, 4, 2),
        "content_max": _int_clamp(lay.get("content_max"), 640, 1600, 1100),
        "gap": _int_clamp(lay.get("gap"), 4, 48, 16),
    }
    background = {
        "mode": _enum(bg.get("mode"), BACKGROUND_MODES, "flat"),
        "texture": _enum(bg.get("texture"), ("none", "dots", "grid"), "none"),
    }
    motion = {"level": _enum(mot.get("level"), MOTION_LEVELS, "subtle")}

    # design：设计契约（不参与渲染）。显式写了不支持的 tone ⇒ 拒绝整包，
    # 与 layout/background/motion 的既有策略一致；缺字段才走默认值。
    des = raw.get("design") if isinstance(raw.get("design"), dict) else {}
    if "tone" in des and des["tone"] not in DESIGN_TONES:
        errors.append("design.tone 取值不支持：%r" % des["tone"])
    sig_raw = des.get("signature", "")
    signature = sig_raw if isinstance(sig_raw, str) else ""
    if "<" in signature or ">" in signature:
        errors.append("design.signature 非法（禁尖括号）")
    elif len(signature) > _MAX_SIGNATURE:
        errors.append("design.signature 超出 %d 字" % _MAX_SIGNATURE)
    asym = des.get("asymmetry", True)
    design = {
        "tone": _enum(des.get("tone"), DESIGN_TONES, "editorial"),
        "signature": signature.strip(),
        "type_jump_min": _f_clamp(des.get("type_jump_min"), 2.0, 6.0, 3.0),
        "accent_share": _int_clamp(des.get("accent_share"), 5, 20, 10),
        "asymmetry": asym if isinstance(asym, bool) else True,
    }

    css, css_errors = _css_clean(raw.get("css", ""))
    errors.extend(css_errors)

    if errors:
        return None, errors
    clean = {
        "schema": SCHEMA_VERSION,
        "id": bid, "name": name, "en": en, "desc": desc,
        "version": version, "source": source, "tags": tags,
        "tokens": {"light": light, "dark": dark},
        "palette": palette, "labels": labels,
        "layout": layout, "background": background,
        "motion": motion, "design": design, "css": css,
    }
    return clean, []


def list_bundles():
    """列出全部合法内置主题包（按文件名排序）。坏包跳过并记日志。"""
    out = []
    try:
        names = sorted(n for n in os.listdir(BUNDLES_DIR)
                       if n.endswith(".json") and not n.startswith("_"))
    except OSError:
        return out
    for fn in names:
        path = os.path.join(BUNDLES_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning("主题包 %s 读取失败：%s", fn, e)
            continue
        clean, errors = validate_bundle(raw)
        if errors:
            logger.warning("主题包 %s 校验失败：%s", fn, "; ".join(errors[:5]))
            continue
        out.append(clean)
    return out


def get_bundle(bundle_id):
    """只读内置目录（随部署包分发的只读资产）。"""
    for b in list_bundles():
        if b["id"] == bundle_id:
            return b
    return None


def resolve_bundle(bundle_id):
    """统一解析激活 id：``zhanghui`` ⇒ 内置包；``lib:my-dark`` ⇒ 站主主题库条目。

    v5.5.0 ②③：应用、``/api/site`` 下发、后台编辑都走这一处，避免「应用成功但
    前台读不到」的两套口径。库内条目同样经过 :func:`validate_bundle`（读时再验一次），
    所以手改 KV 塞进来的坏包只会静默回落经典布局，不会把坏 token 下发到前台。
    """
    bid = (bundle_id or "").strip()
    if not bid:
        return None
    if bid.startswith("lib:"):
        if not has_app_context():
            return None
        import theme_library
        try:
            it = theme_library.get_item(bid[4:])
        except SQLAlchemyError as exc:
            logger.warning("主题库读取失败：%s", exc)
            return None
        return it["bundle"] if it else None
    return get_bundle(bid)


def active_bundle():
    """读当前激活的主题包；未激活 / 包已删除 / 包损坏 → ``None``（前台回落经典布局）。"""
    from utils import get_setting
    bid = (get_setting(ACTIVE_KEY) or "").strip()
    return resolve_bundle(bid) if bid else None


def summary(bundle):
    """后台列表用的精简摘要（不把整套 token / CSS 塞进列表响应）。"""
    return {
        "id": bundle["id"], "name": bundle["name"], "en": bundle["en"],
        "desc": bundle["desc"], "version": bundle["version"],
        "tags": bundle["tags"], "source": bundle["source"],
        "layout": bundle["layout"]["mode"], "card": bundle["layout"]["card"],
        "swatch": bundle["palette"].get("ink", bundle["tokens"]["light"]["accent"]),
        "accent": bundle["tokens"]["light"]["accent"],
    }


def public_bundle(bundle):
    """下发给前台 SPA 的展示层结构（不含作者/版本等后台元数据）。"""
    if not bundle:
        return None
    return {
        "id": bundle["id"],
        "layout": bundle["layout"],
        "background": bundle["background"],
        "motion": bundle["motion"],
        "design": bundle.get("design") or {},
        "palette": bundle["palette"],
        "labels": bundle["labels"],
        "css": bundle["css"],
    }
