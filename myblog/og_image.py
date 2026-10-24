# -*- coding: utf-8 -*-
"""文章 OG 分享图生成（v3.16.0 · 分享卡重做）。

把文章信息用 Pillow 画成 1200×630 的分享卡 PNG，供 og:image / twitter:image 使用，
解决「分享到微信/微博时卡片图不是为这篇文章生成」的问题。

设计原则（沿用项目一贯的降级范式）：
  * **零新增依赖**：Pillow 已是验证码必需依赖（requirements 已声明）。
  * **字体自动探测**：仓库内 static/fonts/ 的开源字体 → 系统中文字体常见路径（glob 扫描）。
  * **找不到中文字体即降级**：返回 None，调用方回退 cover / og-default.png，
    绝不因缺字体导致接口 500 或页面异常（Linux 服务器常见无中文字体）。
  * **磁盘缓存**：按 slug + updated_at + 主题色 hash 缓存到 myblog/data/og_cache/，
    避免爬虫每次抓取都重绘。
  * **封面只读站内**：仅处理 /static/、/uploads/ 等本地路径；外链不下载（防 SSRF + 防延迟）。
"""
import glob
import hashlib
import logging
import os
import contextlib

# v3.19.0：降级不再静默。
# 历史教训——v3.18.9 真机验收时才发现 `.png` 分享卡长期恒返回兜底图，
# 根因是「找不到中文字体 → 静默 return None」，整条降级链一个日志都不打，
# 于是缺陷潜伏了整整一个版本周期而无人察觉。可观测性成本极低、收益极大。
logger = logging.getLogger(__name__)

# Pillow 缺失（理论上不会，requirements 已声明）时整体降级
try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False
    logger.warning("og_image: Pillow 不可用，分享卡将全程降级为兜底图")

W, H = 1200, 630
PAD = 72
COVER_W = 380          # 右侧封面宽度（无封面时为 0）
MAX_TITLE_LINES = 3
MAX_DESC_LINES = 2

# ---------------- 分享卡片模板库（v4.9.0 · ROADMAP §3.1）----------------
#
# 为什么需要多套而不是一套：各平台对 og:image 的**裁剪规则不同**，一张横图
# 通吃的结果是「在某个平台显示不全」。
#
#   · 微信：分享卡缩略图会被裁成**正方形**。1200×630 的横图两侧会被切掉，
#     标题若贴边就只剩半截 —— 所以单独给一套方图模板，内容落在中央安全区。
#     （ROADMAP 原文点名：「微信缩略图规则不同，最值得单做」。）
#   · Twitter/X、Telegram、多数博客聚合器：按 1200×630 横图原样展示。
#
# 模板只管**尺寸 + 默认主色**；渲染时仍可由调用方传 accent 覆盖
# （站点主题色优先于模板默认色），所以加模板不会让站长丢掉品牌色。
# 配色优先级：**站点自定义主色 > 模板默认色**（见 render_og_image）。
# classic 的默认色刻意沿用站点历史默认 #1a73e8，保证升级前后默认表现一致。
TEMPLATES = {
    "classic": {"name": "经典渐变（1200×630）", "accent": "#1a73e8", "w": 1200, "h": 630},
    "wechat_square": {"name": "微信方图（800×800，防裁切）", "accent": "#1a73e8", "w": 800, "h": 800},
    "dark_minimal": {"name": "深色极简（1200×630）", "accent": "#1f2937", "w": 1200, "h": 630},
    "warm_paper": {"name": "暖色纸感（1200×630）", "accent": "#c2410c", "w": 1200, "h": 630},
}
DEFAULT_TEMPLATE = "classic"


def resolve_template(key):
    """按 key 取模板；未命中 / 空值一律退回默认模板（不抛错）。

    之所以不抛错：模板名来自站点设置，可能被手改成无效值。分享卡是锦上
    添花的东西，不该因为设置写错就让文章页 500。
    """
    return TEMPLATES.get(key or "") or TEMPLATES[DEFAULT_TEMPLATE]


def list_templates():
    """后台下拉框用：[(key, 显示名), ...]，默认模板排在最前。"""
    keys = [DEFAULT_TEMPLATE] + [k for k in TEMPLATES if k != DEFAULT_TEMPLATE]
    return [(k, TEMPLATES[k]["name"]) for k in keys]

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_HERE, "static", "fonts")
_CACHE_DIR = os.path.join(_HERE, "data", "og_cache")
_CACHE_MAX = 300       # 缓存上限，超出清理最旧的一批


# ---------------- 字体探测 ----------------
def _cjk_candidates(bold=False):
    """按优先级返回中文字体候选路径（打包字体优先，其次系统字体）。"""
    cands = []
    # 1) 仓库内打包的开源字体（保证跨服务器一致。
    #    当前入库的是文泉驿微米黑：GPL v2 + 字体嵌入例外条款，
    #    可随站点分发；详见 static/fonts/FONTS.md —— 不要写成 OFL。）
    if os.path.isdir(_FONT_DIR):
        # 三轮：① 指定字重命名（*Bold* / *Regular*）② 仓库内任意字体 ③ 兜底
        # 注意 .ttc 也要参与字重命名匹配——v3.18.9 前只匹配 .ttf/.otf，
        # 导致放进去的 *-Bold.ttc 永远不会被优先选中（静默用回任意字体）。
        pats = ["*Bold*", "*bold*"] if bold else ["*Regular*", "*regular*"]
        for ext in (".ttf", ".otf", ".ttc"):
            for p in pats:
                cands += sorted(glob.glob(os.path.join(_FONT_DIR, p + ext)))
        # 没有 Regular/Bold 命名时，退而求其次用目录里任意一个字体文件
        cands += sorted(glob.glob(os.path.join(_FONT_DIR, "*.ttf")))
        cands += sorted(glob.glob(os.path.join(_FONT_DIR, "*.otf")))
        cands += sorted(glob.glob(os.path.join(_FONT_DIR, "*.ttc")))

    # 2) 系统字体（glob 扫描，覆盖不同发行版/系统）
    sys_globs = [
        "/usr/share/fonts/**/NotoSansCJK*",
        "/usr/share/fonts/**/NotoSansSC*",
        "/usr/share/fonts/**/SourceHanSans*",
        "/usr/share/fonts/**/wqy-*",
        "/usr/share/fonts/**/DroidSansFallback*",
        "/usr/share/fonts/**/msyh*",
        "/usr/share/fonts/**/simhei*",
        "/Library/Fonts/**/PingFang*",
        "/System/Library/Fonts/**/PingFang*",
        "/System/Library/Fonts/**/STHeiti*",
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for g in sys_globs:
        with contextlib.suppress(Exception):
            cands += sorted(glob.glob(g, recursive=True))
    return cands


def _find_font(size, bold=False):
    """找可用中文字体；找不到返回 None（调用方据此降级）。"""
    if not _PIL_OK:
        return None
    for path in _cjk_candidates(bold=bold):
        if not os.path.isfile(path):
            continue
        try:
            # .ttc 多 face，取第一个
            return ImageFont.truetype(path, size, index=0)
        except Exception:
            continue
    return None


# ---------------- 绘图工具 ----------------
def _hex_to_rgb(s, default=(79, 124, 255)):
    s = (s or "").strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        if len(s) != 6:
            raise ValueError
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _darken(rgb, k=0.28):
    """按比例压暗，做渐变终点色。"""
    return tuple(max(0, int(c * k)) for c in rgb)


def _gradient_bg(c1, c2, w=None, h=None):
    """垂直渐变背景（逐行绘制，几百行开销可忽略）。

    `w` / `h` 缺省时退回模块级 W/H —— v4.9.0 模板库引入方图后才需要传，
    老调用方不受影响。
    """
    w = w or W
    h = h or H
    img = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(img)
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=(
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        ))
    return img


def _tokenize(text):
    """中英混排切词：中文按字，英文/数字按单词，便于换行不切断单词。"""
    toks, buf = [], ""
    for ch in text:
        if ch.isspace():
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(" ")
            continue
        if "一" <= ch <= "鿿" or ch in "，。！？；：、（）《》“”‘’—…":
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(ch)
        else:
            buf += ch
    if buf:
        toks.append(buf)
    return toks


_KINSOKU = "，。、；：？！）】》〉」』\"'…—％‰"


def _fix_kinsoku(lines):
    """中文避头尾：禁则字符不得出现在行首，挪到上一行行尾（允许轻微超宽）。"""
    for i in range(1, len(lines)):
        moved = 0
        while lines[i] and lines[i][0] in _KINSOKU and moved < 2:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
            moved += 1
    return [l for l in lines if l]


def _wrap(draw, text, font, max_w, max_lines):
    """按像素宽度换行；行首禁则修正；超出 max_lines 截断加省略号；末行孤字合并。"""
    if not text:
        return [], False
    lines, cur = [], ""
    for tok in _tokenize(text):
        trial = cur + tok
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur.rstrip())
            cur = tok.lstrip() if tok.strip() else ""
    if cur.strip():
        lines.append(cur.rstrip())
    lines = _fix_kinsoku(lines)
    if len(lines) <= max_lines:
        return lines, False
    lines = lines[:max_lines]
    last = lines[-1]
    while last and draw.textlength(last + "…", font=font) > max_w:
        last = last[:-1]
    lines[-1] = last + "…"
    return lines, True


def _round_cover(src_path, size=COVER_W):
    """读取站内封面并裁成正方形（居中裁剪），失败返回 None。"""
    try:
        im = Image.open(src_path)
        im = im.convert("RGB")
        w, h = im.size
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
        return im.resize((size, size), Image.LANCZOS)
    except Exception:
        return None


def _resolve_within(root, candidate):
    """把 candidate 归一化后限制在 root 之内；越界或不是文件一律 None。

    root 必须是 **realpath 过的目录**。用 `startswith(root + os.sep)` 而非
    `startswith(root)`——否则 `/myblog/static-evil/x` 这类同前缀兄弟目录会通过。
    """
    rp = os.path.realpath(candidate)
    if not (rp == os.path.realpath(root) or rp.startswith(os.path.realpath(root) + os.sep)):
        return None
    return rp if os.path.isfile(rp) else None


def _local_cover_path(cover):
    """仅接受站内相对路径；外链/异常一律返回 None（不下载，防 SSRF）。

    R114 审计：**三个**分支都曾可路径穿越（CWE-22），且可达范围可逃逸到
    仓库根及上层（`_HERE/static/` + 任意 `../`）：

    1. `static/../config.py`  → 归一后是 `myblog/config.py`（越出 static/）
    2. `uploads/../../data/blog.db`
    3. **兜底分支** `c` 完全用户控制、**无任何前缀要求**：
       `../config.py` → `_HERE/static/../config.py` = `myblog/config.py`

    实测确认**逃逸范围可到文件系统根**：`../` × 8 能读到 `E:/Windows/win.ini`，
    不只是仓库内。

    修法：`realpath` 归一 + 限定在 `_HERE/static` 之内。

    🔑 **实现陷阱（务必保留，两条都是实测踩出来的）**：
    1. 基目录**不能取 `_HERE`**（= `myblog/`）——那样 `static/../config.py` 归一后
       仍是 `myblog/config.py`，`startswith(_HERE + sep)` 成立 → **放行**。
       第一版就是这么写的，测试当场变红才发现。
    2. 前缀判断必须用 `startswith(root + os.sep)` 而非 `startswith(root)`，
       否则 `/myblog/static-evil/x` 这类同前缀兄弟目录能通过。
    """
    if not cover:
        return None
    c = cover.strip()
    if c.startswith("http://") or c.startswith("https://") or c.startswith("//"):
        return None
    c = c.split("?")[0]
    if c.startswith("/"):
        c = c[1:]
    # **单一 root** = `_HERE/static`：三条路径全部归一到这一个根下判定。
    #
    # 关于 `uploads/` 前缀：审计组核实 `_HERE/uploads` 从不存在（真实上传目录是
    # `config.UPLOAD_FOLDER = BASE_DIR/static/uploads`，`admin/media.py` 返回的
    # `/static/uploads/...` 也落进本函数时已带 `static/` 前缀），故该分支在
    # **当前数据下不可达**。但 `cover` 是**自由文本表单字段**（`post_editor.py`
    # / `taxonomy.py` / `mcp_write.py` 均直接取 `request.form["cover"]`），
    # 管理员手工填 `uploads/evil.png` 就会命中它——**结构上可达**。
    # 因此**保留该前缀**（不把 bug 修复做成「一种输入格式不再被识别」的行为收窄），
    # 只是把它归一到同一个 root：`uploads/x.png` → `static/uploads/x.png`，
    # 恰好也正是它本来的语义。
    static_root = os.path.join(os.path.realpath(_HERE), "static")
    # 只剥 `static/`（它等价于 root 本身）；`uploads/` **必须保留**——它是
    # root 下的子目录，剥掉就会把 `uploads/x.png` 错映射成 `static/x.png`。
    # `uploads/x.png` → `static/uploads/x.png`（正是它的本来语义）。
    if c.startswith("static/"):
        c = c[len("static/"):]
    return _resolve_within(static_root, os.path.join(static_root, c))


# ---------------- 缓存 ----------------
def _cache_key(slug, stamp, accent, template=""):
    """v4.9.0：**template 必须进 key**。

    模板会同时改变尺寸与默认主色。若 key 只含 accent，那么「换模板但主色
    相同」（例如 classic → wechat_square 都用 #4f7cff）会命中旧缓存，
    吐回一张 1200×630 的横图 —— 表现是「明明选了微信方图，分享出去还是
    被裁」。这类 bug 很难发现，因为缓存命中时没有任何日志。
    """
    raw = f"{slug}|{stamp}|{accent}|{template}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _cache_get(key):
    p = os.path.join(_CACHE_DIR, key + ".png")
    return p if os.path.isfile(p) else None


def _cache_put(key, img):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        p = os.path.join(_CACHE_DIR, key + ".png")
        img.save(p, "PNG", optimize=True)
        _cache_trim()
        return p
    except Exception:
        return None


def _cache_trim():
    """缓存文件超过上限时，删除最旧的一批（防止无限增长）。"""
    try:
        fs = [os.path.join(_CACHE_DIR, f) for f in os.listdir(_CACHE_DIR) if f.endswith(".png")]
        if len(fs) <= _CACHE_MAX:
            return
        fs.sort(key=lambda p: os.path.getmtime(p))
        for p in fs[:len(fs) - _CACHE_MAX + 50]:
            with contextlib.suppress(Exception):
                os.remove(p)
    except Exception:  # noqa: S110  清理动作，失败无副作用（文件本就可能已不存在）
        pass


# ---------------- 主入口 ----------------
def render_og_image(*, title, desc="", site_name="", accent="",
                    date_str="", read_min=0, category="", cover=None,
                    template=None):
    """绘制分享卡，返回 PIL.Image；字体缺失或异常时返回 None（降级信号）。

    v4.9.0 模板库：`template` 决定**尺寸**与**默认主色**；若调用方显式传了
    `accent`（站点品牌色），则覆盖模板默认色 —— 保证加模板不会丢品牌色。
    """
    if not _PIL_OK:
        return None
    tpl = resolve_template(template)
    w, h = tpl["w"], tpl["h"]
    accent = accent or tpl["accent"]
    f_title = _find_font(64, bold=True) or _find_font(64)
    if f_title is None:
        # 降级信号。这条日志是 v3.18.9 之后补的——之前这里静默 return None，
        # 导致「服务器缺中文字体」表现为「分享卡悄悄变成兜底图」，排查成本极高。
        logger.warning(
            "og_image: 未找到任何可用中文字体，分享卡降级为兜底图"
            "（字体目录=%s，PIL=%s）。请确认 myblog/static/fonts/ 已随包部署。",
            _FONT_DIR, _PIL_OK,
        )
        return None
    f_desc = _find_font(30) or f_title
    f_meta = _find_font(26) or f_title

    c1 = _hex_to_rgb(accent)
    img = _gradient_bg(c1, _darken(c1), w=w, h=h)
    d = ImageDraw.Draw(img)

    # 右上角装饰圆（半透明感：用同色系亮色低透明叠加）
    try:
        deco = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(deco)
        dd.ellipse([w - 320, -160, w + 120, 280], fill=tuple(list(c1) + [40]))
        dd.ellipse([w - 520, h - 260, w - 60, h + 200], fill=(255, 255, 255, 16))
        img = Image.alpha_composite(img.convert("RGBA"), deco).convert("RGB")
        d = ImageDraw.Draw(img)
    except Exception:  # noqa: S110  旁路/兜底路径，失败按降级处理，不影响主流程
        pass

    cover_im = None
    cp = _local_cover_path(cover)
    if cp:
        cover_im = _round_cover(cp, COVER_W)

    text_w = w - PAD * 2 - (COVER_W + 56 if cover_im else 0)
    x = PAD
    y = PAD + 8

    # 站点名
    if site_name:
        d.text((x, y), site_name[:24], font=f_meta, fill=(255, 255, 255, 200))
        y += 54

    # 标题（自适应字号：长标题用小号）
    fsize = 64
    for s in (64, 56, 48, 40):
        f_title = _find_font(s, bold=True) or _find_font(s) or f_title
        lines, _ = _wrap(d, title, f_title, text_w, MAX_TITLE_LINES)
        if len(lines) <= MAX_TITLE_LINES and (not lines or d.textlength(lines[0], font=f_title) <= text_w):
            fsize = s
            break
    y += 12
    for ln in lines:
        d.text((x, y), ln, font=f_title, fill=(255, 255, 255, 255))
        y += int(fsize * 1.42)

    # 摘要
    y += 18
    if desc:
        for ln in _wrap(d, desc, f_desc, text_w, MAX_DESC_LINES)[0]:
            d.text((x, y), ln, font=f_desc, fill=(255, 255, 255, 205))
            y += 44

    # 底部元信息
    bits = [b for b in (category, date_str, (f"约 {read_min} 分钟" if read_min else "")) if b]
    if bits:
        d.text((x, h - PAD - 34), "  ·  ".join(bits), font=f_meta, fill=(255, 255, 255, 190))

    # 封面（右侧居中的圆角方块）
    if cover_im:
        cx = w - PAD - COVER_W
        cy = (h - COVER_W) // 2
        mask = Image.new("L", (COVER_W * 4, COVER_W * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, COVER_W * 4 - 1, COVER_W * 4 - 1], radius=120, fill=255)
        mask = mask.resize((COVER_W, COVER_W), Image.LANCZOS)
        try:
            img.paste(cover_im, (cx, cy), mask)
        except Exception:
            img.paste(cover_im, (cx, cy))
    return img


def og_png_bytes(*, slug, stamp="", **kw):
    """带缓存的对外入口：返回 (png_bytes, 是否命中缓存)；降级时返回 (None, False)。"""
    if not _PIL_OK:
        return None, False
    key = _cache_key(slug, stamp, kw.get("accent", ""), kw.get("template", ""))
    hit = _cache_get(key)
    if hit:
        try:
            with open(hit, "rb") as f:
                return f.read(), True
        except Exception:  # noqa: S110  读缓存/状态文件失败则当没有缓存
            pass
    try:
        img = render_og_image(**kw)
    except Exception:
        # 同样不再静默：渲染期异常（坏封面、Pillow 版本差异等）也要留痕。
        logger.warning("og_image: 渲染分享卡失败，降级为兜底图 (slug=%s)", slug, exc_info=True)
        return None, False
    if img is None:
        return None, False
    _cache_put(key, img)
    try:
        import io
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue(), False
    except Exception:
        return None, False
