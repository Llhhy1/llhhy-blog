# -*- coding: utf-8 -*-
"""v5.9.0 字体子集守卫。

这一档最容易出的问题不是「字体生成错」，而是**接错了线**：CSS 挂了但 HTML 没引、
字体栈还写着旧 family、`package.py` 又把 24 MB 旧分片扫回包里、OFL 全文忘了随附。
四种都会「测试全绿而线上没效果 / 不合规」，所以这里逐条钉死接线与边界。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAMILY = "LLHhy Serif SC"
FONTS = "myblog/static/fonts/"
WOFF2 = FONTS + "llhhy-serif-sc.woff2"
CSS = FONTS + "llhhy-serif-sc.css"
LICENSE = FONTS + "OFL-NotoSerifSC.txt"
CHARSET = "tools/font_charset.txt"
SCRIPT = "tools/build_subset_font.py"
MAX_WOFF2 = 1_500_000


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _bytes(rel):
    return (ROOT / rel).read_bytes()


# ---------- 1. 产物本身 ----------

def test_字体三件套齐全且_woff2_格式有效():
    data = _bytes(WOFF2)
    assert data[:4] == b"wOF2", "不是有效 woff2（magic 应为 wOF2）"
    assert len(data) <= MAX_WOFF2, (
        "子集字体 %.2f MB 超过 %d 字节上限 —— 换了字体就把发布包又撑大了"
        % (len(data) / 1048576, MAX_WOFF2)
    )
    assert (ROOT / CSS).is_file() and (ROOT / LICENSE).is_file()


def test_css_只声明一个自托管字体且不切割_unicode_range():
    css = _read(CSS)
    assert 'font-family: "%s"' % FAMILY in css
    assert 'url("./llhhy-serif-sc.woff2")' in css
    assert "format(\"woff2\")" in css
    assert "font-display: swap" in css
    # 🔴 关键：不写 unicode-range。写了之后子集外的字不会走字体栈回落，
    # 而是被浏览器判定为「本字体负责」→ 显示豆腐块/空白，而不是系统宋体。
    assert "unicode-range" not in css, "子集字体不能声明 unicode-range"
    assert "kinghua" not in css.lower(), "CSS 里还残留旧京华老宋体引用"
    assert len(re.findall(r"@font-face", css)) == 1, "子集应当只有一个 @font-face"


def test_OFL_许可全文与版权声明随字体入版():
    lic = _read(LICENSE)
    assert "SIL OPEN FONT LICENSE" in lic
    assert "Version 1.1" in lic
    assert "Copyright" in lic
    assert "PERMISSION & CONDITIONS" in lic


# ---------- 2. 接线（HTML / 字体栈 / CSP）----------

def test_前台挂载新_css_且不再引用旧_css():
    html = _read("vue-frontend/index.html")
    assert "/static/fonts/llhhy-serif-sc.css" in html
    assert "/static/fonts/kinghua.css" not in html, "旧 503 分片 CSS 还挂在首屏"
    sec = _read("myblog/security.py")
    m = re.search(r"font-src([^;\"]*)", sec)
    assert m and "'self'" in m.group(1), "CSP 不放 'self'，自托管字体加载不了"


def test_主题字体栈首选新字体且以_serif_收尾():
    from themes import PRESET_MAP
    lt = PRESET_MAP["sage-sand"]["light"]
    assert lt["font_sans"].startswith("'%s'" % FAMILY), "字体栈首选没换"
    assert "KingHwaOldSong" not in lt["font_sans"], "旧字体名还留在字体栈"
    assert lt["font_sans"].rsplit(",", 1)[-1].strip() == "serif", (
        "回落链末尾不是 serif，缺字会掉成无衬线"
    )


# ---------- 3. 打包边界与供应链 ----------

def test_package_py_显式排除旧分片与旧_css():
    pkg = _read("package.py")
    assert re.search(r"EXCLUDE_DIRS\s*=\s*\{[^}]*[\"']kinghua[\"']", pkg), (
        "旧 503 分片目录没被排除，本地残留会再进后端 zip"
    )
    assert re.search(r"EXCLUDE_FILES\s*=\s*\{[^}]*[\"']kinghua\.css[\"']", pkg), (
        "旧 kinghua.css 没被排除"
    )
    assert re.search(r"add_tree\([^)]*EXCLUDE_FILES", pkg), (
        "EXCLUDE_FILES 定义了却没传给 add_tree —— 等于没排除"
    )


def test_gitignore_保留旧两条且不忽略整个_fonts_目录():
    gi = _read(".gitignore")
    assert "myblog/static/fonts/kinghua/" in gi
    assert "myblog/static/fonts/kinghua.css" in gi
    assert "myblog/static/fonts/\n" not in gi, "不能忽略整个 fonts/（还有 og:image 字体与说明）"
    assert "tools/.font-source/" in gi, "11.6 MB 源 OTF 必须挡在仓库外"


def test_构建脚本带自检与供应链哈希钉子():
    sc = _read(SCRIPT)
    for needle in ("--check", "--refresh", "MAX_WOFF2", "SOURCE_SHA256",
                   "LICENSE_SHA256", "def verify("):
        assert needle in sc, "构建脚本缺 %s" % needle
    assert "fonttools" in sc.lower() or "fontTools" in sc, "脚本里没写清构建机依赖"


def test_用字清单是离线可重复基线():
    s = _read(CHARSET)
    han = {c for c in s if 0x4E00 <= ord(c) <= 0x9FFF}
    assert len(han) >= 1500, "用字清单只剩 %d 个汉字，基线被误删" % len(han)
    assert "一" in s and "的" in s


def test_内置主题包字体栈同步切换():
    """🔴 站主激活的是内置「章回」包，`/api/site` 的 `theme_tokens.font_sans`
    来自 `theme_packs/*.json` 而不是 `themes.py` 的预设。只改预设 = 线上零效果。"""
    import json
    packs = sorted((ROOT / "myblog" / "theme_packs").glob("*.json"))
    assert packs, "内置主题包目录空了"
    for p in packs:
        raw = p.read_text(encoding="utf-8")
        assert "KingHwaOldSong" not in raw, "%s 仍写死旧字体" % p.name
        assert "京华老宋体" not in raw, "%s 的描述还在说旧字体" % p.name
        d = json.loads(raw)
        for mode, tok in (d.get("tokens") or {}).items():
            if isinstance(tok, dict) and "font_sans" in tok:
                fs = tok["font_sans"]
                assert fs.startswith("'%s'" % FAMILY), "%s/%s 首选没换" % (p.name, mode)
                assert fs.rsplit(",", 1)[-1].strip() == "serif"


def test_FONTS_md_说明新字体许可与旧资产处置():
    doc = _read(FONTS + "FONTS.md")
    assert "SIL OFL 1.1" in doc and FAMILY in doc
    assert "build_subset_font.py" in doc
    assert "不自动删除" in doc or "不会自动删除" in doc


# ---------- 4. 真实字形覆盖（fontTools 为构建机可选依赖）----------

def test_子集覆盖清单内全部汉字且内部_famliy_已改名():
    pytest.importorskip("fontTools", reason="fontTools 只在构建机安装")
    from fontTools.ttLib import TTFont
    f = TTFont(str(ROOT / WOFF2))
    cmap = set(f.getBestCmap())
    fam = f["name"].getDebugName(1)
    f.close()
    han = {ord(c) for c in _read(CHARSET) if 0x4E00 <= ord(c) <= 0x9FFF}
    missing = sorted(han - cmap)
    assert not missing, "子集漏了 %d 个汉字：%s" % (
        len(missing), "".join(chr(c) for c in missing[:20])
    )
    assert fam == FAMILY, "内部 family 没改名，会与访客本机完整版混淆"
