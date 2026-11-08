# -*- coding: utf-8 -*-
"""v5.7.0 排版尺度全量收敛守卫。

## 背景

v5.6.0 只做了「字号棘轮」(18 种 distinct px 值只许减不许增)，
实际 CSS 里仍散着 21 种 px 字号 / 19 种行高字面量。本轮把它们
统一到 13 级字号 + 7 级行高，且**每个消费点必须带兜底值**
``var(--type-*, 13px)`` —— token 未加载（旧缓存 / 旧模板）时
表现与收敛前逐字一致。

## 为什么不用「distinct 数量 <= N」这种棘轮

棘轮只防新增，不能证明「已收敛」。改动完成后直接断言字面量归零，
并反查每个兜底值确实落在尺度表内 —— 防止有人写一个
``var(--type-sm, 19px)`` 把新尺度悄悄架空。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# (token, 值)：两份 tokens.css 必须逐字一致，且与消费点的兜底口径对齐
TYPE_SCALE = {
    "--type-3xs": "10px", "--type-2xs": "11px", "--type-xs": "12px",
    "--type-sm": "13px", "--type-meta": "14px", "--type-base": "15px",
    "--type-md": "16px", "--type-lg": "18px", "--type-xlg": "20px",
    "--type-xl": "22px", "--type-2xl": "28px", "--type-3xl": "32px",
    "--type-display": "44px",
}
LEADING_SCALE = {
    "--leading-flat": "1", "--leading-tight": "1.3", "--leading-snug": "1.4",
    "--leading-normal": "1.5", "--leading-base": "1.6",
    "--leading-loose": "1.75", "--leading-relaxed": "1.85",
    # 布局专用档（不是排版尺度）：消基线间隙 / 单行垂直居中
    "--leading-none": "0", "--leading-double": "2",
}

# 全库扫描范围：SPA 样式 + Vue SFC 的 scoped style + 后台 / SSR 样式
CSS_DIRS = [ROOT / "vue-frontend" / "src" / "styles", ROOT / "myblog" / "static"]
VUE_DIR = ROOT / "vue-frontend" / "src"

BLOCK_RE = re.compile(r"/\*.*?\*/", re.S)
STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
FS_LITERAL = re.compile(r"(?<![-\w])font-size\s*:\s*([0-9.]+)px")
LH_LITERAL = re.compile(r"(?<![-\w])line-height\s*:\s*([0-9.]+)\s*;")
FS_VAR = re.compile(r"var\(\s*(--type-[a-z0-9-]+)\s*,\s*([0-9.]+)px\s*\)")
LH_VAR = re.compile(r"var\(\s*(--leading-[a-z0-9-]+)\s*,\s*([0-9.]+)\s*\)")

# 允许出现的兜底值（原字面量 -> 目标 token），即 CONVERGENCE 映射表
FS_FALLBACKS = {
    "9": "--type-3xs", "10": "--type-3xs", "11": "--type-2xs", "11.5": "--type-xs",
    "12": "--type-xs", "12.5": "--type-sm", "12.8": "--type-sm", "13": "--type-sm",
    "13.5": "--type-meta", "14": "--type-meta", "14.5": "--type-meta",
    "15": "--type-base", "15.5": "--type-md", "16": "--type-md", "17": "--type-md",
    "18": "--type-lg", "19": "--type-lg", "20": "--type-xlg", "21": "--type-xlg",
    "22": "--type-xl", "23": "--type-xl", "24": "--type-xl",
    "26": "--type-2xl", "28": "--type-2xl",
    "30": "--type-3xl", "34": "--type-3xl", "44": "--type-display",
}
LH_FALLBACKS = {
    "0": "--leading-none", "2": "--leading-double",
    "1": "--leading-flat", "1.1": "--leading-tight", "1.2": "--leading-tight",
    "1.22": "--leading-tight", "1.24": "--leading-tight", "1.25": "--leading-tight",
    "1.3": "--leading-tight",
    "1.34": "--leading-snug", "1.35": "--leading-snug", "1.4": "--leading-snug",
    "1.5": "--leading-normal", "1.55": "--leading-normal",
    "1.6": "--leading-base", "1.65": "--leading-base", "1.68": "--leading-base",
    # theme_center.html 的 .tc-hint 用 1.65
    "1.7": "--leading-loose", "1.75": "--leading-loose", "1.78": "--leading-loose",
    "1.8": "--leading-relaxed", "1.85": "--leading-relaxed",
    "1.86": "--leading-relaxed", "1.9": "--leading-relaxed",
}


def _code_only(src: str) -> str:
    """剥块注释，避免注释里的示例被当成真实声明。"""
    return BLOCK_RE.sub("", src)


def _css_sources():
    """返回 (相对显示名, 去注释后的 CSS/模板文本) 列表。

    覆盖范围必须等于「实际会渲染出字号的来源」：
    SPA / 后台 CSS 样式表、Vue SFC 全文（含 template 里的内联 style）、
    后台 Jinja2 模板的 <style> 段。少一处就等于给那处开了后门。
    """
    out = []
    for d in CSS_DIRS:
        for p in sorted(d.glob("*.css")):
            out.append((p.relative_to(ROOT).as_posix(), _code_only(p.read_text(encoding="utf-8"))))
    for p in sorted(VUE_DIR.rglob("*.vue")):
        out.append((p.relative_to(ROOT).as_posix(), _code_only(p.read_text(encoding="utf-8"))))
    for p in sorted((ROOT / "myblog" / "templates" / "admin").glob("*.html")):
        # 全文：元素内联 style="..." 里的字号同样会渲染，不能只扫 <style> 段。
        out.append((p.relative_to(ROOT).as_posix(), _code_only(p.read_text(encoding="utf-8"))))
    return out


@pytest.mark.parametrize("rel", [
    "myblog/static/tokens.css",
    "vue-frontend/src/styles/tokens.css",
])
def test_两份tokens定义了完整尺度(rel):
    t = (ROOT / rel).read_text(encoding="utf-8")
    defs = dict(re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);", t))
    for token, val in {**TYPE_SCALE, **LEADING_SCALE}.items():
        assert defs.get(token) == val, "%s 缺 %s: %s（或取值漂移）" % (rel, token, val)


def test_尺度表两份tokens逐字一致():
    def parse(rel):
        t = (ROOT / rel).read_text(encoding="utf-8")
        d = {}
        for m in re.finditer(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);", t):
            d.setdefault(m.group(1), []).append(m.group(2).strip())
        return d
    a = parse("myblog/static/tokens.css")
    b = parse("vue-frontend/src/styles/tokens.css")
    assert set(a) == set(b), "两份 tokens.css 变量集合漂移"
    assert not [k for k in a if a[k] != b[k]], "两份 tokens.css 取值不一致"


def test_全库无裸字号字面量():
    bad = []
    for name, css in _css_sources():
        hits = FS_LITERAL.findall(css)
        if hits:
            bad.append("%s: %s" % (name, sorted(set(hits))))
    assert not bad, "仍有 font-size 字面量，请走 --type-* 尺度：\n" + "\n".join(bad)


def test_全库无裸行高字面量():
    bad = []
    for name, css in _css_sources():
        hits = LH_LITERAL.findall(css)
        if hits:
            bad.append("%s: %s" % (name, sorted(set(hits))))
    assert not bad, "仍有 line-height 字面量，请走 --leading-* 尺度：\n" + "\n".join(bad)


def test_所有字号兜底值落在收敛映射表内():
    bad = []
    total = 0
    for name, css in _css_sources():
        for tok, val in FS_VAR.findall(css):
            total += 1
            if FS_FALLBACKS.get(val) != tok or tok not in TYPE_SCALE:
                bad.append("%s: var(%s, %spx)" % (name, tok, val))
    assert total >= 100, "只找到 %d 处带兜底的字号消费点，收敛疑似没落地" % total
    assert not bad, "兜底值与尺度表不匹配：\n" + "\n".join(bad[:20])


def test_所有行高兜底值落在收敛映射表内():
    bad = []
    total = 0
    for name, css in _css_sources():
        for tok, val in LH_VAR.findall(css):
            total += 1
            if LH_FALLBACKS.get(val) != tok or tok not in LEADING_SCALE:
                bad.append("%s: var(%s, %s)" % (name, tok, val))
    assert total >= 30, "只找到 %d 处带兜底的行高消费点，收敛疑似没落地" % total
    assert not bad, "兜底值与尺度表不匹配：\n" + "\n".join(bad[:20])


def test_行高兜底后不得粘连下一条声明():
    """批量替换踩过的坑：``line-height: 1.6;`` 若被写成
    ``line-height: var(--leading-base, 1.6) color: ...``，浏览器会把整条
    声明连同后面的属性一起丢弃，CSS 不报错、页面只是悄悄掉样式，肉眼极难发现。

    判据只抓「) 后紧跟另一个属性名:」这一种粘连；末声明省略分号
    （``... 1.6) }``）是合法 CSS，不在此列。
    """
    glued = re.compile(
        r"var\(--leading-[a-z0-9-]+,\s*[0-9.]+\)\s+[a-zA-Z-]+\s*:")
    bad = []
    for name, css in _css_sources():
        for m in glued.finditer(css):
            bad.append("%s: ...%s..." % (name, css[max(0, m.start()-30):m.end()+20].replace("\n", " ")))
    assert not bad, "line-height 兜底后缺分号、粘连下一条声明：\n" + "\n".join(bad[:10])
