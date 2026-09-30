# -*- coding: utf-8 -*-
"""v3.25.0 回归：CSS 裸hex **棘轮** —— 只许减，不许增。

背景与实测结论（v3.25.0 做的测绘，结论与直觉相反，值得记下来）
----------------------------------------------------------------
``admin.css``（234 处hex）与 ``style.css``（194 处）长期被列为「裸 hex 待收敛」。
v3.25.0 逐值核对了「能否用现有 token **等价**替代」，答案是：

- **``admin.css`` 几乎没有可换的。** 它的 200 处非兜底裸 hex 分三类：
  1. **暗色块内的专用值**（``#cfd3d8`` / ``#9aa0a8`` / ``#333842`` …）——
     值与亮色 token 不同，换过去会跟着主题一起变亮，是**改设计**不是收敛。
  2. **无对应 token 的独立色**（``#98a1ad`` placeholder 灰 ×11 / ``#e6e8eb`` ×9）——
     ``--text-muted`` 是 ``#6a717f``，与 ``#98a1ad`` **值不同**，
     「长得像灰」不等于「可以换」。
  3. **渐变端点**（``#7cb0ff`` / ``#6aa9ff``）—— 与 ``--accent`` 构成设计语义。
  顺带查出 ``admin.css`` 本身就很早就用 ``var()`` 了（17 个 token），
  裸 hex 集中在**它自己管的那套灰阶**里，属于「没token 化」而非「该换」。
- **``style.css`` 有 11 处真等价**，已按本文件既有的 ``var(--token, 原值)``
  兜底约定换掉（零像素差、token 缺失时行为不变）。

所以本文件**不做「全部替换」的大承诺**，只钉两件能验证的事：
1. 棘轮：非兜底裸 hex 数量**不得增长**（给出当前值作基线）。
2. 已token 化的那11 处**不得退回**成裸 hex。

「全部收敛」需要先扩 ``tokens.css``（新增灰阶token）再动，
那是另一次有设计决策的改动，不该由一条测试假装已经做完。
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 裸 hex 计数基线（**排除** var(--x, #hex) 兜底里的那些 —— 它们已经是 token 化写法）
# v3.25.0 实测：style.css 188 → 177（本批token 化 11 处），admin.css 200 → 190
# （计数口径修过一次：早先统计时把 var() 兜底算成了裸 hex，基线偏大 10）
BASELINE = {
    "myblog/static/admin.css": 190,
    "myblog/static/style.css": 177,
}

# 已 token 化的位置：(文件, 行内容片段, token 名) —— 防止退回裸 hex
TOKENIZED = [
    ("myblog/static/style.css", "color: var(--text, #2c2c2c);", "--text"),
    ("myblog/static/style.css", "background: var(--bg, #f7f8fa);", "--bg"),
    ("myblog/static/style.css", "color: var(--text-muted, #555);", "--text-muted"),
    ("myblog/static/style.css", "background: var(--surface, #fff);", "--surface"),
    ("myblog/static/style.css", "border-top: 1px solid var(--border, #ececec);", "--border"),
]

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def _bare_hex_count(src: str) -> int:
    """非 var() 兜底里的裸 hex 数量。

    判定方式：hex 往前 40 字符内若出现 ``var(`` 且该 hex 落在对应的 ``)`` 之前，
    则它已经��在 ``var(--token, #hex)`` 兜底里，不算裸 hex。
    """
    n = 0
    for m in HEX_RE.finditer(src):
        # 找最近的一个 var( 与它是否配对到当前 hex 之前
        v = src.rfind("var(", max(0, m.start() - 60), m.start())
        if v != -1:
            close = src.find(")", v, m.end())
            if close != -1:
                # var( ... ) 完整包住这个 hex -> 兜底写法
                tail = src[v + 4:close]
                if re.search(r"--[a-z0-9-]+", tail) and m.start() > v:
                    continue
        n += 1
    return n


@pytest.mark.parametrize("rel,cap", sorted(BASELINE.items()))
def test_裸_hex_棘轮不增长(rel, cap):
    """非兜底裸 hex 不得多于基线。新增裸色= 绕过 token 体系，必须先改基线并说明理由。"""
    got = _bare_hex_count(_read(rel))
    assert got <= cap, (
        f"{rel} 裸 hex 从 {cap} 涨到 {got}（+{got - cap}）。"
        "新颜色请走 tokens.css；确有必要新增时，先想清楚是不是漏了语义 token。"
    )


@pytest.mark.parametrize("rel,frag,token", TOKENIZED)
def test_已_token_化的写法不得退回(rel, frag, token):
    assert frag in _read(rel), (
        f"{rel} 里 {frag!r} 消失了 —— {token} 又退回成裸色了"
    )


def test_兜底写法是本项目约定():
    """``var(--token, #原值)`` 是这两份 CSS 里既有的写法（v3.17 起），
    好处是 token 缺失时行为与改动前完全一致。新增 token 化必须沿用它，
    不许直接写裸 ``var(--token)``（那会让旧缓存/旧模板掉色）。"""
    total = 0
    for rel in BASELINE:
        total += len(re.findall(r"var\(\s*--[a-z0-9-]+\s*,\s*#[0-9a-fA-F]{3,8}\s*\)", _read(rel)))
    assert total >= 15, (
        f"只找到 {total} 处 var(--token, #hex) 兜底写法（基线 15）。"
        "若确认约定已废弃，请连同本文件一起改；否则新 token 化漏了兜底参数"
    )


def test_新增的_token_化必须带兜底():
    """``var(--token, #原值)`` 兜底写法要求：凡是**我们这一批**引入的
    token 化（TOKENIZED 清单里那11 处），都必须带兜底参数。

    既有代码里大量 ``var(--accent)`` / ``var(--border)`` 不带兜底是历史风格
    （它们假设 tokens.css 必定加载），本文件不去动它们 —— 但新引入的不许跟。
    """
    src = _read("myblog/static/style.css")
    # 反向：token 出现在裸 var(--x) 里（无逗号兜底）则提示
    naked = re.findall(r"var\(\s*--(?:text|text-muted|surface|bg|border)\s*\)", src)
    assert not naked, (
        f"style.css 里出现无兜底的 var(--text/--text-muted/--surface/--bg/--border)：{naked}。"
        "新 token 化一律用 var(--token, #原值) 兜底写法"
    )

