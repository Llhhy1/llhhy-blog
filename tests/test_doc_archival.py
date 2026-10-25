# -*- coding: utf-8 -*-
"""v3.25.0 回归：文档归档结构（``docs/archive/``）必须保持完整与可达。

背景
----
仓库文档一度达1,088 KB（``SECURITY_AUDIT.md`` 436 KB + ``CHANGELOG.md`` 218 KB+
``ROADMAP.md`` 152 KB + ``deploy_guide.md`` 102 KB），每次让 LLM 读仓库都吃掉大量
上下文。v3.25.0 把**历史段落**移到 ``docs/archive/``，主文件只留近期
（合计降到627 KB，-42%）。

**归档不是删除。** 审计台账的价值在于「能查到 R47 当时发现了什么」，
移动位置不能毁掉这个能力。所以本文件钉住三件事：
1. 归档件**存在**且不是空壳（历史上真的搬过东西过去）
2. 主文件**留了指针**（读到主文件的人知道去哪找历史）
3. 跨文档引用**没被打断**（代码/脚本里提到这些文件名的路径仍然有效）

另有两条是**门禁护栏**：``tools/review/check-staged.py`` 的 ``DOCS`` 元组是真实
逻辑（后端改动时强制文档同步），归档时漏改它会直接让发版门禁失效。
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, "docs/archive")

# (归档文件名, 主文件, 主文件里必须出现的指针片段, 归档件必须含的锚点, 主文件里不得再出现的特征串)
PAIRS = [
    (
        "SECURITY_AUDIT_r01-r80.md",
        "myblog/SECURITY_AUDIT.md",
        "docs/archive/SECURITY_AUDIT_r01-r80.md",
        "## 第八十轮 R80",  # 归档件的最后一条历史（标题含中文轮次名）
        None,
    ),
    (
        "CHANGELOG_v1-v3.18.5.md",
        "CHANGELOG.md",
        "docs/archive/CHANGELOG_v1-v3.18.5.md",
        "## v3.18.5",      # 归档件的最后一条旧版本
        None,
    ),
    # v3.25.13 追加：主文件涨到 162 KB 触发体积守卫（上限 160 KB），
    # 按「新增轮次写进主文件、历史段落才归档」把 R81~R90 搬出来。
    (
        "SECURITY_AUDIT_r81-r90.md",
        "myblog/SECURITY_AUDIT.md",
        "docs/archive/SECURITY_AUDIT_r81-r90.md",
        "## R90 · 后台「🔍 收录」控制台",  # 归档件的最后一条（R90）
        None,
    ),
    # v4.4.0 追加：加完 R122（移动端「内容全套」设计期审计）后主文件涨到 163 KB 再次触发
    # 体积守卫（上限 160 KB）。同一次「先写进主文件、撑满再把最老的十轮搬走」的循环。
    (
        "SECURITY_AUDIT_r91-r100.md",
        "myblog/SECURITY_AUDIT.md",
        "docs/archive/SECURITY_AUDIT_r91-r100.md",
        "## R100 · v3.25.2",  # 归档件的最后一条（R100）
        None,
    ),
    # v4.7.0 追加：加完 v4.7.0（含四块长条目）后 CHANGELOG 主文件涨到 201 KB，
    # 再次触发体积守卫（上限 200 KB）。同一次「先写进主文件、撑满再把最老的一批搬走」的循环，
    # 本轮搬走的是 **CHANGELOG** 而非审计台账（审计主文件当时 102 KB，仍有余量）。
    (
        "CHANGELOG_v3.18.6-v3.19.2.md",
        "CHANGELOG.md",
        "docs/archive/CHANGELOG_v3.18.6-v3.19.2.md",
        "## v3.18.6",  # 归档件的最老一条（也是搬走的最后一条）
        None,
    ),
    # v4.8.5 追加：加完 v4.8.5（EdgeOne 真实 IP 还原 + update.sh 面板同步）后
    # CHANGELOG 主文件涨到 205 KB，再次触发体积守卫（上限 200 KB）。
    # 同一次「先写进主文件、撑满再把最老的一批搬走」的循环，本轮搬走 v3.20.0 ~ v3.21.2。
    (
        "CHANGELOG_v3.20.0-v3.21.2.md",
        "CHANGELOG.md",
        "docs/archive/CHANGELOG_v3.20.0-v3.21.2.md",
        "## v3.20.0",  # 归档件的最老一条（也是搬走的最后一条）
        None,
    ),
    # v4.8.8 追加：**ROADMAP.md 瘦身**（1282 行 → 68 行，-95%）。
    # 原「三、分期计划」～「七十三、v3.17.4~9」整段（逐版本迭代记录 + v3.25.x
    # 决策/取证详志）与 CHANGELOG 高度重复，搬到归档件；主文件只留
    # 「已做 / 不做」两桶 + 旧章节索引（保住代码与文档里已有的 `ROADMAP §x` 引用）。
    # stale 特征串取**版本段标题** —— 主文件里出现它即说明「归档只是复制了一份」。
    (
        "ROADMAP_archive.md",
        "ROADMAP.md",
        "docs/archive/ROADMAP_archive.md",
        "## 73. v3.17.4~9",   # 归档件的最后一段
        "## 六、v2.6.x",      # 主文件不应再含逐版本迭代记录
    ),
    # v4.11.0 追加：加完 v4.11.0（后台统一组件层 + 体检 12→19 维 + MCP 新增 3 工具）后
    # CHANGELOG 主文件涨到 201 KB，再次触发体积守卫（上限 200 KB）。
    # 同一次「先写进主文件、撑满再把最老的一批搬走」的循环，本轮搬走 v3.22.0 ~ v3.25.16
    # （-80 KB，主文件回落到 120 KB，余量够撑好几轮）。
    (
        "CHANGELOG_v3.22.0-v3.25.16.md",
        "CHANGELOG.md",
        "docs/archive/CHANGELOG_v3.22.0-v3.25.16.md",
        "## v3.22.0",   # 归档件的最老一条（也是搬走的最后一条）
        None,
    ),
    # v4.12.1 追加：写进 R131（前台 /docs 重做）后 SECURITY 主文件涨到 166 KB，
    # 触发体积守卫（上限 160 KB）。同一个循环：新增写主文件，撑满再把最老的十轮搬走。
    (
        "SECURITY_AUDIT_r101-r110.md",
        "myblog/SECURITY_AUDIT.md",
        "docs/archive/SECURITY_AUDIT_r101-r110.md",
        "## R110 · v3.25.12",  # 归档件的最后一条（R110）
        # 主文件里若还留着 R101 的标题，说明只是「复制一份」而非真搬走
        "## R101 · v3.25.3",
    ),
]

# 整份搬走的快照（一次性审查报告）
LOOSE = [
    "INDEPENDENT_SECURITY_REVIEW_v3.8.1.md",
    "REVIEW_v3.18.0.md",
]


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("arc,main,pointer,anchor,stale", PAIRS)
def test_归档件存在且有实质内容(arc, main, pointer, anchor, stale):
    p = os.path.join(ARCH, arc)
    assert os.path.exists(p), f"归档件丢失：docs/archive/{arc}"
    text = _read("docs/archive", arc)
    assert len(text.encode()) > 20_000, (
        f"docs/archive/{arc} 只有 {len(text.encode())} B，"
        "远小于历史段落的实际体量 —— 归档很可能被截断"
    )
    assert anchor in text, f"归档件缺末尾锚点 {anchor!r}，切分点可能错位"


@pytest.mark.parametrize("arc,main,pointer,anchor,stale", PAIRS)
def test_主文件留了归档指针(arc, main, pointer, anchor, stale):
    text = _read(*main.split("/"))
    assert pointer in text, (
        f"{main} 里找不到归档指针 {pointer!r} —— "
        "读者打开主文件不知道历史去哪找，等于把历史藏起来了"
    )
    # 指针必须出现在靠前的位置（头部 2000 字内），否则翻到底才看得见
    assert text.index(pointer) < 2000, (
        f"{main} 的归档指针出现在第 {text.index(pointer)} 字符处，太靠后"
    )


@pytest.mark.parametrize("arc,main,pointer,anchor,stale", PAIRS)
def test_主文件不再含已归档内容(arc, main, pointer, anchor, stale):
    """反向守卫：切分必须真的生效。主文件里若还留着 R80 / v3.18.5 / 版本段标题，
    说明归档只是「复制了一份」而不是「搬走了」，上下文一点没省。"""
    text = _read(*main.split("/"))
    if stale:
        # 每个归档对可自带特征串（如 ROADMAP 的「## 六、v2.6.x」版本段标题），
        # 比通用正则更精确 —— ROADMAP 没有「第一轮/R50」那类轮次标题。
        assert stale not in text, (
            f"{main} 仍含已归档的历史段落（{stale!r}）—— 归档没有真正移出内容"
        )
    elif arc.startswith("SECURITY_AUDIT"):
        # R1~R80 的特征：最早的轮次标题
        hit = re.search(r"^## (第一轮|四、|R1\b|R50\b)", text, re.M)
        assert not hit, (
            f"{main} 仍含已归档的历史段落（匹配到 {hit.group(0)!r}）—— "
            "归档没有真正移出内容"
        )
    else:
        assert "## v3.18.5" not in text, (
            f"{main} 仍含已归档的 v3.18.5 段落"
        )


@pytest.mark.parametrize("name", LOOSE)
def test_一次性快照已归档且原位不存在(name):
    assert os.path.exists(os.path.join(ARCH, name)), f"快照未归档：{name}"
    # 原位不应再有同名文件（避免「复制而非搬走」）
    stale = [p for p in ("REVIEW.md", "myblog/INDEPENDENT_SECURITY_REVIEW_v3.8.1.md")
             if os.path.exists(os.path.join(ROOT, *p.split("/")))]
    assert not stale, f"这些一次性文档仍留在原位：{stale}"


def test_归档件带拆分说明():
    """归档件顶部必须写清「这是归档件、从哪拆来、去哪找近期」，
    否则半年后有人打开它会以为是当前文档。"""
    for arc, _main, _pointer, _anchor, _stale in PAIRS:
        head = _read("docs/archive", arc)[:1200]
        assert "归档件" in head, f"{arc} 顶部没说明自己是归档件"
        assert "拆分" in head, f"{arc} 顶部没写拆分点"


def test_发版门禁不强迫改归档件():
    """``tools/review/check-staged.py`` 的 ``DOCS`` 元组是**真实逻辑** ——
    后端代码改动时若这些文档没同步就拦提交。

    **v3.25.2 更正**：这条断言原本要求归档件必须在 ``DOCS`` 里，方向是**错的**。
    归档件是**历史快照**（R1~R80 / v3.18.5 及更早），内容本就不该随新版本变化 ——
    把它列进必改清单，结果是每次发版都被迫「虚假地」动一下归档件才能过门禁。
    v3.25.1 发版时实测到这条误报，已从 ``DOCS`` 移除。

    现在断言的是**两件真正该成立的事**：
    1. 归档件**不在**必改清单里（否则门禁继续误报）；
    2. 但**活的**主文档（``SECURITY_AUDIT.md`` / ``CHANGELOG.md`` 对应的现行文件）
       仍在清单里 —— 门禁不能被改废。
    """
    src = _read("tools/review/check-staged.py")
    m = re.search(r"^DOCS\s*=\s*\((.*?)\)", src, re.M | re.S)
    assert m, "check-staged.py 里找不到 DOCS 元组"
    docs = m.group(1)

    for arc, _main, _pointer, _anchor, _stale in PAIRS:
        assert f"docs/archive/{arc}" not in docs, (
            f"DOCS 元组里仍有 docs/archive/{arc} —— 归档件是历史快照，"
            f"不该被要求每次发版都改（v3.25.1 已移除）"
        )
    for required in ("myblog/SECURITY_AUDIT.md", "myblog/README.md",
                     "myblog/deploy_guide.md", "ROADMAP.md"):
        assert required in docs, f"DOCS 元组缺 {required} —— 门禁被改废了"


def test_跨文档引用路径仍有效():
    """把「谁提到了归档件的旧路径」全仓扫一遍，路径写错就是死链。

    排除两类**故意**提到文件名的地方：
    - 本测试自身（它必须写出文件名才能断言）
    - ``docs/archive/`` 下的归档件（头部就要写「拆自我」）
    """
    targets = {arc for arc, _m, _p, _a, _s in PAIRS} | set(LOOSE)
    self_name = os.path.basename(__file__)
    bad = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", ".workbuddy",
                         ".vite_build30", "dist", "build", "archive"}
        ]
        for fn in filenames:
            if not fn.endswith((".py", ".md", ".sh", ".yml", ".yaml", ".toml", ".cfg")):
                continue
            if fn == self_name:
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT).replace("\\", "/")
            try:
                with open(fp, encoding="utf-8", errors="replace") as _f:
                    text = _f.read()
            except OSError:
                continue
            for t in targets:
                # 提到裸文件名但全文没有 docs/archive/ 目录提示 -> 死链。
                # 「同文件任意位置出现过 docs/archive/ 目录」即算已交代：
                # ROADMAP 里有「已归档到 `docs/archive/` —— `SECURITY_AUDIT_r01-r80.md`（327 KB…）」
                # 这种写法，前缀在同一句已给出，按逐个文件名匹配会误报。
                if t in text and "docs/archive/" not in text:
                    bad.append(f"{rel} 提到 {t} 但全文没有 docs/archive/ 目录提示")
    assert not bad, "归档后路径失配：\n" + "\n".join(sorted(set(bad)))


def test_代码里的归档路径必须完整():
    """比上一条更严：``.py`` / ``.sh`` / ``.yml`` 里的归档路径是**会被工具读到的**
    真实引用（不像文档里「归档到 docs/archive/ 目录下」这种散文式列举），
    必须写全 ``docs/archive/<file>``，否则脚本会去找一个不存在的路径。

    v3.25.0 归档时 ``tools/review/check-staged.py`` 的 ``DOCS`` 元组就是这种引用
    —— 漏改它等于发版门禁对该归档件失效。
    """
    targets = {arc for arc, _m, _p, _a, _s in PAIRS} | set(LOOSE)
    self_name = os.path.basename(__file__)
    bad = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", ".workbuddy",
                         ".vite_build30", "dist", "build", "archive"}
        ]
        for fn in filenames:
            if not fn.endswith((".py", ".sh", ".yml", ".yaml", ".toml", ".cfg")):
                continue
            if fn == self_name:
                continue        # 本测试必须写出文件名才能断言，提到裸名是故意的
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT).replace("\\", "/")
            try:
                with open(fp, encoding="utf-8", errors="replace") as _f:
                    text = _f.read()
            except OSError:
                continue
            for t in targets:
                if t in text and f"docs/archive/{t}" not in text:
                    bad.append(f"{rel} 提到 {t} 但没写完整路径 docs/archive/{t}")
    assert not bad, "代码里的归档路径不完整：\n" + "\n".join(sorted(set(bad)))


def test_主文件体积未回涨():
    """体积是这次归档的目的，得钉住上限，否则几轮追加后又回去了。
    阈值留了余量（当前 SECURITY_AUDIT 99 KB / CHANGELOG 140 KB）。"""
    limits = {
        "myblog/SECURITY_AUDIT.md": 160 * 1024,
        "CHANGELOG.md": 200 * 1024,
    }
    over = []
    for rel, cap in limits.items():
        size = os.path.getsize(os.path.join(ROOT, *rel.split("/")))
        if size > cap:
            over.append(f"{rel} {size // 1024} KB > 上限 {cap // 1024} KB")
    assert not over, (
        "归档后的主文件又涨回去了（新增轮次请写进主文件，历史段落才归档）："
        + "；".join(over)
    )
