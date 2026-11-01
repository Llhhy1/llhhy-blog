#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""京华老宋体（KingHwaOldSong）分片下载器 —— 把第三方字体搬到本站自己托管。

**为什么要有这个脚本**（v5.4.x 主题「青野」的一部分）：
官方只提供 `https://fontsapi.zeoseven.com/309/main/result.css` 这种 hotlink 用法，
而 hotlink 有两个真实代价：

1. 本站 CSP 是 `font-src 'self' data:`（`myblog/security.py`）—— **外链字体根本加载不出来**，
   不是「不太推荐」，是直接被浏览器拦掉；
2. 每个访客的浏览器都会替本站去请求第三方 —— 访客的 IP/UA 就此外流，
   而且对方一挂，字体立刻回落到系统宋体，观感突变。
   （与 `api/theme.py:_safe_wp_url` 拒绝外链壁纸是同一条理由。）

所以这里把官方 cn-font-split 的产物**原样**抓下来放到 `myblog/static/fonts/`：
只改 CSS 里的文件路径、只加 `font-display` 加载提示，**不动字体二进制**
（作者授权：可免费商用，不可修改字体本身、不可单独售卖字体文件）。

用法：
    python tools/fetch_kinghua_font.py            # 下载缺失的分片 + 生成 kinghua.css
    python tools/fetch_kinghua_font.py --check    # 只校验：CSS 引用的分片是否都在（部署后跑）
    python tools/fetch_kinghua_font.py --force    # 重下所有分片

产物（都在 .gitignore 的 myblog/static/fonts/ 下，仓库不背这 ~26MB）：
    myblog/static/fonts/kinghua.css
    myblog/static/fonts/kinghua/<hash>.woff2   × 503
缺文件时不会报错打断启动：前台的 font_sans 回落链里有 'Noto Serif SC','Songti SC',
'SimSun',serif，没下载就是系统宋体，功能完好。
"""
import argparse
import concurrent.futures as cf
import io
import re
import sys
import urllib.error
import urllib.request

BASE = "https://fontsapi.zeoseven.com/309/main/"
CSS_URL = BASE + "result.css"
UA = "Mozilla/5.0 (compatible; llhhy-blog font self-host script)"
OUT_DIR = "myblog/static/fonts"
CSS_NAME = "kinghua.css"
SLICE_DIR = "kinghua"
# 官方 CSS 里是 `url("./<16hex>.woff2")`，本地化后是 `url("./kinghua/<16hex>.woff2")`。
# 两条都要能匹配：`--check` 读的是**本地化之后**的 CSS，只认前一种的话它会数出 0 个分片，
# 于是「503 个文件明明都在」也能报就绪（真踩过：写完 --check 第一次跑就 0/0）。
URL_RE = re.compile(r"""url\(\s*["']?[^"')]*?([0-9a-f]{16}\.woff2)["']?\s*\)""")
FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}")


def repo_root():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build_css(text):
    """把官方 CSS 里的相对路径改指到本地分片目录，并补 font-display。

    `font-display: swap` 是**加载策略**不是字体内容：不补的话中文分片在加载期间
    是「不可见占位」，首屏会白一下（体感比系统宋体更差）。
    """
    css = URL_RE.sub(lambda m: 'url("./%s/%s")' % (SLICE_DIR, m.group(1)), text)
    n = 0

    def _face(m):
        nonlocal n
        block = m.group(0)
        if "font-display" in block:
            return block
        n += 1
        return block[:-1].rstrip() + "\n  font-display: swap;\n}"

    css = FACE_RE.sub(_face, css)
    return css, n


def main(argv=None):
    ap = argparse.ArgumentParser(description="京华老宋体分片自托管下载器")
    ap.add_argument("--check", action="store_true", help="只校验已下载的分片是否齐全")
    ap.add_argument("--force", action="store_true", help="忽略已存在文件，全部重下")
    ap.add_argument("--jobs", type=int, default=6, help="并发数（默认 6，别调太高）")
    args = ap.parse_args(argv)

    root = repo_root()
    fonts = root / OUT_DIR
    slices = fonts / SLICE_DIR
    css_path = fonts / CSS_NAME

    if args.check:
        if not css_path.exists():
            print("[未就绪] 缺 %s —— 先跑：python tools/fetch_kinghua_font.py" % css_path)
            return 1
        css = css_path.read_text(encoding="utf-8")
        want = set(URL_RE.findall(css))
        missing = [h for h in sorted(want) if not (slices / h).exists() or (slices / h).stat().st_size == 0]
        print("CSS 引用 %d 个分片，本地缺失 %d 个" % (len(want), len(missing)))
        for h in missing[:10]:
            print("   缺：", h)
        if missing:
            return 1
        print("[就绪] %s -> %s（%.1f MB）" % (
            "/" + OUT_DIR + "/" + CSS_NAME, SLICE_DIR,
            sum((slices / h).stat().st_size for h in want) / 1048576.0))
        return 0

    print("取官方 CSS：", CSS_URL)
    raw = http_get(CSS_URL).decode("utf-8")
    hashes = sorted(set(URL_RE.findall(raw)))
    if not hashes:
        print("[失败] 官方 CSS 里没解析到 woff2 分片，可能上游改了产物格式，先手工看一眼。")
        return 1
    print("分片 %d 个；先写 %s" % (len(hashes), CSS_NAME))
    slices.mkdir(parents=True, exist_ok=True)
    css, patched = build_css(raw)
    io.open(str(css_path), "w", encoding="utf-8", newline="\n").write(css)
    print("CSS 路径已本地化，补 font-display 的 @font-face：%d" % patched)

    def fetch(h):
        dst = slices / h
        if dst.exists() and dst.stat().st_size and not args.force:
            return (h, 0)
        for attempt in (1, 2, 3):
            try:
                data = http_get(BASE + h, timeout=45)
                if data[:4] != b"wOF2":
                    return (h, -1)
                dst.write_bytes(data)
                return (h, len(data))
            except (urllib.error.URLError, OSError, ValueError) as e:
                if attempt == 3:
                    print("  [失败]", h, e)
                    return (h, -2)
        return (h, -2)

    done = bad = skipped = 0
    total = 0
    with cf.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        for _h, size in ex.map(fetch, hashes):
            if size == 0:
                skipped += 1
            elif size < 0:
                bad += 1
            else:
                done += 1
                total += size
            if (done + skipped + bad) % 50 == 0:
                print("  进度 %d/%d" % (done + skipped + bad, len(hashes)))

    print("\n结果：新下 %d 个（%.1f MB），已存在跳过 %d，失败 %d"
          % (done, total / 1048576.0, skipped, bad))
    if bad:
        print("有分片没下全：前台会按 font_sans 的回落链用系统宋体，不影响功能；"
              "重跑本脚本只会补缺的那几个。")
        return 1
    print("下一步：确认前端已引用 /%s/%s（见 myblog/deploy_guide.md 的字体一节）。" % (OUT_DIR, CSS_NAME))
    return 0


if __name__ == "__main__":
    sys.exit(main())
