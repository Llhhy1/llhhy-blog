#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v5.9.0：从 Noto Serif SC（SIL OFL 1.1）生成站点专用子集 woff2。

**为什么不再用京华老宋体**（v5.4.4 ~ v5.8.0）：
官方 cn-font-split 产物是 503 个 woff2 / 24.8 MB 的全 CJK 分片，且授权
「免费商用但不可修改字体本身」—— 不能重新子集化。它占后端发布包的 88%，
让每次发版都必须挂 GH_MIRROR；而本站 13 篇文章 + 前端文案实际只用约 2100 字。

**本方案**：改用 SIL OFL 1.1 的思源宋体（Noto Serif SC）。OFL 允许修改、
子集化与再分发，于是把站点真实用字压成单个 woff2（约 0.5~1 MB）。
OFL 要求随字体附带许可全文与版权声明 → 见 static/fonts/OFL-NotoSerifSC.txt。

用法：
    python tools/build_subset_font.py --refresh          # 从线上公开 API 刷新用字清单
    python tools/build_subset_font.py                    # 用清单 + 本地源码生成子集
    python tools/build_subset_font.py --source X.otf     # 指定源字体（默认 %TEMP%）
    python tools/build_subset_font.py --check            # 校验产物覆盖率/体积，不写文件

依赖（**仅构建机**，不进生产 requirements）：fonttools[woff]、brotli。
源字体（不入库，11.6 MB）：
    https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf
许可全文：
    https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/OFL.txt

⚠️ 写新文章后若出现「某几个字变成系统宋体」，跑一次 --refresh 再重新生成即可。
   缺字是**优雅回落**（字体栈末尾仍是 serif），不会 404、不会白屏、不影响功能。
"""
import argparse
import hashlib
import html as html_mod
import json
import os
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "myblog" / "static" / "fonts"
TOOLS = ROOT / "tools"
CHARSET_FILE = TOOLS / "font_charset.txt"
WOFF2 = FONTS / "llhhy-serif-sc.woff2"
CSS = FONTS / "llhhy-serif-sc.css"
LICENSE = FONTS / "OFL-NotoSerifSC.txt"
CSS_HREF = "/static/fonts/llhhy-serif-sc.css"
FAMILY = "LLHhy Serif SC"
SITE = "https://www.llhhy.cn"
SOURCE_URL = ("https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
              "Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf")
LICENSE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/OFL.txt"
MAX_WOFF2 = 1_500_000  # 守卫生效上限：1.5 MB

# 供应链钉子：源字体与许可全文来自 GitHub raw，下载后必须逐一校验 sha256，
# 不匹配就拒绝生成（避免上游被替换/中间人篡改时把来路不明的二进制打进字体）。
SOURCE_SHA256 = "e8f396decc1f0963a016a989c3d8852e863d1350996f573860a80767c83a1cd3"
LICENSE_SHA256 = "5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(p, expected, label, strict=True):
    got = sha256_file(p)
    if got == expected:
        return True
    msg = "%s 哈希不符：期望 %s，实得 %s" % (label, expected, got)
    if strict:
        raise SystemExit("[拒绝] " + msg)
    print("[警告] " + msg, file=sys.stderr)
    return False

# 基础字符：ASCII 可打印 + CJK 标点 + 全角 + 常用排版符号。
# 文章/源码里出现过的字符会被自动收进来，这里只兜住「还没写但一定会用」的那批。
BASE_RANGES = [(0x20, 0x7E), (0x3000, 0x303F), (0xFF00, 0xFFEF)]
BASE_EXTRA = (
    " ©®™°±×÷‰–—…·•†‡§¶"
    "「」『』〈〉《》【】（）［］｛｝"
    "①②③④⑤⑥⑦⑧⑨⑩→←↑↓↔⇒⇐⇑⇓√∞≠≤≥≈≡∂∑∏∫"
    "、。，．：；！？‥﹐﹒﹔﹖﹗"
)
TAG_RE = re.compile(r"<[^>]+>")
SCAN_DIRS = ("vue-frontend/src", "myblog/templates", "myblog/static")
SCAN_SUFFIXES = {".vue", ".js", ".ts", ".css", ".html", ".json", ".md"}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (llhhy-blog font subset)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def collect_api(site=SITE):
    """从公开 API 抓所有文章正文（列表分页 + 单数详情端点 /api/post/<slug>）。"""
    slugs, page = [], 1
    while page <= 20:
        raw = http_get("%s/api/posts?per_page=100&page=%d" % (site, page)).decode("utf-8")
        d = json.loads(raw)
        items = d.get("items") or []
        if not items:
            break
        slugs.extend(x["slug"] for x in items if x.get("slug"))
        total = d.get("total") or 0
        if len(slugs) >= total:
            break
        page += 1
    text = []
    for slug in slugs:
        try:
            d = json.loads(http_get("%s/api/post/%s" % (site, slug)).decode("utf-8"))
        except Exception as e:
            print("  [跳过] %s: %s" % (slug, e), file=sys.stderr)
            continue
        for k in ("title", "summary", "seo_description", "seo_keywords", "html"):
            v = d.get(k)
            if isinstance(v, str):
                text.append(TAG_RE.sub("", html_mod.unescape(v)))
    try:
        text.append(json.dumps(json.loads(http_get(site + "/api/site").decode("utf-8")),
                               ensure_ascii=False))
    except Exception:
        pass
    return slugs, "".join(text)


def collect_repo():
    """扫本地源码里的中文字（前台文案 / 后台模板 / 样式注释）。"""
    out = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES:
                continue
            if "kinghua" in p.name or p.name == "llhhy-serif-sc.css":
                continue
            try:
                out.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "".join(out)


def charset_from_text(*chunks):
    chars = {chr(c) for a, b in BASE_RANGES for c in range(a, b + 1)}
    chars |= set(BASE_EXTRA)
    for t in chunks:
        chars |= {ch for ch in t if ord(ch) >= 0x20}
    # 控制字符 / 代理区 / 未分配区不进字体
    return "".join(sorted(c for c in chars if 0x20 <= ord(c) <= 0x10FFFF))


def refresh_charset(site=SITE):
    slugs, api_text = collect_api(site)
    s = charset_from_text(api_text, collect_repo())
    CHARSET_FILE.write_text(s, encoding="utf-8", newline="\n")
    print("[refresh] 文章 %d 篇，字集 %d 字 -> %s" % (len(slugs), len(s), CHARSET_FILE))
    return s


def read_charset():
    if not CHARSET_FILE.exists():
        raise SystemExit("缺 %s —— 先跑：python tools/build_subset_font.py --refresh" % CHARSET_FILE)
    s = CHARSET_FILE.read_text(encoding="utf-8")
    return charset_from_text(s, collect_repo())


def default_source(strict=True):
    names = [
        pathlib.Path(os.environ.get("TEMP", "/tmp")) / "NotoSerifSC-Regular.otf",
        TOOLS / ".font-source" / "NotoSerifSC-Regular.otf",
    ]
    for p in names:
        if p.is_file():
            verify(p, SOURCE_SHA256, "源字体", strict)
            return p
    cache = names[1]
    cache.parent.mkdir(parents=True, exist_ok=True)
    print("下载源字体（一次性，11.6 MB）...")
    cache.write_bytes(http_get(SOURCE_URL, timeout=120))
    verify(cache, SOURCE_SHA256, "源字体", strict)
    return cache


def build(source, chars, strict=True):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]          # 保留版权/许可等 name 记录
    opts.name_legacy = True
    opts.notdef_glyph = True
    opts.recommended_glyphs = True
    font = subset.load_font(str(source), opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=chars)
    sub.subset(font)
    # OFL 允许修改再分发；把内部 family 名改成站点专名，避免与访客本机
    # 安装的完整版 Noto Serif SC 在调试/字体面板里混淆。
    for rec in font["name"].names:
        if rec.nameID in (1, 3, 4, 6, 16):
            try:
                rec.string = FAMILY.encode("utf-16-be") if rec.isUnicode() else FAMILY.encode("ascii")
            except UnicodeEncodeError:
                pass
    WOFF2.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(WOFF2), opts)
    font.close()
    if not LICENSE.exists():
        LICENSE.write_bytes(http_get(LICENSE_URL))
    verify(LICENSE, LICENSE_SHA256, "OFL 许可全文", strict)
    CSS.write_text(
        "/* v5.9.0：站点专用宋体子集，基于 Noto Serif SC (SIL OFL 1.1)。\n"
        "   生成：python tools/build_subset_font.py --refresh && python tools/build_subset_font.py\n"
        "   许可全文见同目录 OFL-NotoSerifSC.txt；缺字由字体栈优雅回落到系统宋体。 */\n"
        '@font-face {\n'
        '  font-family: "%s";\n' % FAMILY +
        '  src: url("./llhhy-serif-sc.woff2") format("woff2");\n'
        '  font-style: normal;\n'
        '  font-weight: 400;\n'
        '  font-display: swap;\n'
        '}\n', encoding="utf-8", newline="\n")
    return WOFF2.stat().st_size


def check():
    from fontTools.ttLib import TTFont
    if not WOFF2.exists() or not CSS.exists() or not LICENSE.exists():
        print("[FAIL] 产物不全"); return 1
    size = WOFF2.stat().st_size
    f = TTFont(str(WOFF2))
    cmap = set(f.getBestCmap())
    fam = f["name"].getDebugName(1)
    f.close()
    # 只钉汉字覆盖：CJK 基本区 + 扩展 A 是源字体（Noto Serif SC）明确覆盖的范围，
    # 这里的缺字才是「子集漏了」。emoji / 韩文 / 变体选择符 / 未分配码位源字体
    # 本来就没有字形，浏览器按字体栈用系统字形渲染，属预期回落，不算缺陷。
    need_all = {ord(c) for c in read_charset()}
    han = {c for c in need_all if 0x4E00 <= c <= 0x9FFF or 0x3400 <= c <= 0x4DBF}
    missing = sorted(c for c in han if c not in cmap)
    fallback = sum(1 for c in need_all if c >= 0x4E00 and c not in cmap and c not in han)
    print("woff2 %.2f MB / %d 字形 / 汉字需覆盖 %d / 缺 %d / 系统字形回落 %d"
          % (size / 1048576, len(cmap), len(han), len(missing), fallback))
    if missing:
        print("  缺字示例:", "".join(chr(c) for c in missing[:20]))
    print("内部 family:", fam)
    ok = size <= MAX_WOFF2 and not missing and fam == FAMILY
    print("[就绪]" if ok else "[未就绪]", "CSS:", CSS.name, "LICENSE:", LICENSE.name)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成站点专用宋体子集")
    ap.add_argument("--refresh", action="store_true", help="从线上公开 API 刷新用字清单")
    ap.add_argument("--source", help="源 OTF 路径（默认自动下载到 tools/.font-source/）")
    ap.add_argument("--site", default=SITE, help="收集用字的站点，默认 %s" % SITE)
    ap.add_argument("--check", action="store_true", help="只校验产物，不写文件")
    ap.add_argument("--no-verify", action="store_true",
                    help="跳过源字体/许可 sha256 校验（仅用于自定义源字体）")
    args = ap.parse_args(argv)
    strict = not args.no_verify
    if args.check:
        return check()
    if args.refresh:
        refresh_charset(args.site)
    chars = read_charset()
    src = pathlib.Path(args.source) if args.source else default_source(strict)
    verify(src, SOURCE_SHA256, "源字体", strict)
    print("源字体:", src, "字集:", len(chars), "字")
    size = build(src, chars, strict)
    print("生成 %s（%.2f MB）+ %s + %s" % (WOFF2, size / 1048576, CSS.name, LICENSE.name))
    return 0 if size <= MAX_WOFF2 else 1


if __name__ == "__main__":
    sys.exit(main())
