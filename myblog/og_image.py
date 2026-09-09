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
import os

# Pillow 缺失（理论上不会，requirements 已声明）时整体降级
try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False

W, H = 1200, 630
PAD = 72
COVER_W = 380          # 右侧封面宽度（无封面时为 0）
MAX_TITLE_LINES = 3
MAX_DESC_LINES = 2

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_HERE, "static", "fonts")
_CACHE_DIR = os.path.join(_HERE, "data", "og_cache")
_CACHE_MAX = 300       # 缓存上限，超出清理最旧的一批


# ---------------- 字体探测 ----------------
def _cjk_candidates(bold=False):
    """按优先级返回中文字体候选路径（打包字体优先，其次系统字体）。"""
    cands = []
    # 1) 仓库内打包的开源字体（OFL 可分发，保证跨服务器一致）
    if os.path.isdir(_FONT_DIR):
        pats = ["*Bold*", "*bold*"] if bold else ["*Regular*", "*regular*"]
        for p in pats:
            cands += sorted(glob.glob(os.path.join(_FONT_DIR, p + ".ttf")))
            cands += sorted(glob.glob(os.path.join(_FONT_DIR, p + ".otf")))
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
        try:
            cands += sorted(glob.glob(g, recursive=True))
        except Exception:
            pass
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


def _gradient_bg(c1, c2):
    """垂直渐变背景（逐行绘制，630 行开销可忽略）。"""
    img = Image.new("RGB", (W, H), c1)
    d = ImageDraw.Draw(img)
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=(
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


def _local_cover_path(cover):
    """仅接受站内相对路径；外链/异常一律返回 None（不下载，防 SSRF）。"""
    if not cover:
        return None
    c = cover.strip()
    if c.startswith("http://") or c.startswith("https://") or c.startswith("//"):
        return None
    c = c.split("?")[0]
    if c.startswith("/"):
        c = c[1:]
    # 允许 static/ 与 uploads/（后台上传目录）前缀
    for base in ("static", "uploads"):
        if c.startswith(base + "/"):
            p = os.path.join(_HERE, c)
            return p if os.path.isfile(p) else None
    p = os.path.join(_HERE, "static", c)
    return p if os.path.isfile(p) else None


# ---------------- 缓存 ----------------
def _cache_key(slug, stamp, accent):
    raw = f"{slug}|{stamp}|{accent}"
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
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass


# ---------------- 主入口 ----------------
def render_og_image(*, title, desc="", site_name="", accent="#4f7cff",
                    date_str="", read_min=0, category="", cover=None):
    """绘制分享卡，返回 PIL.Image；字体缺失或异常时返回 None（降级信号）。"""
    if not _PIL_OK:
        return None
    f_title = _find_font(64, bold=True) or _find_font(64)
    if f_title is None:
        return None  # 无中文字体 → 降级
    f_desc = _find_font(30) or f_title
    f_meta = _find_font(26) or f_title

    c1 = _hex_to_rgb(accent)
    img = _gradient_bg(c1, _darken(c1))
    d = ImageDraw.Draw(img)

    # 右上角装饰圆（半透明感：用同色系亮色低透明叠加）
    try:
        deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(deco)
        dd.ellipse([W - 320, -160, W + 120, 280], fill=tuple(list(c1) + [40]))
        dd.ellipse([W - 520, H - 260, W - 60, H + 200], fill=(255, 255, 255, 16))
        img = Image.alpha_composite(img.convert("RGBA"), deco).convert("RGB")
        d = ImageDraw.Draw(img)
    except Exception:
        pass

    cover_im = None
    cp = _local_cover_path(cover)
    if cp:
        cover_im = _round_cover(cp, COVER_W)

    text_w = W - PAD * 2 - (COVER_W + 56 if cover_im else 0)
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
        d.text((x, H - PAD - 34), "  ·  ".join(bits), font=f_meta, fill=(255, 255, 255, 190))

    # 封面（右侧居中的圆角方块）
    if cover_im:
        cx = W - PAD - COVER_W
        cy = (H - COVER_W) // 2
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
    key = _cache_key(slug, stamp, kw.get("accent", ""))
    hit = _cache_get(key)
    if hit:
        try:
            with open(hit, "rb") as f:
                return f.read(), True
        except Exception:
            pass
    try:
        img = render_og_image(**kw)
    except Exception:
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
