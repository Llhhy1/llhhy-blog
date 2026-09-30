# -*- coding: utf-8 -*-
"""v3.25.0回归：后台 ``.admin-table`` 的每个数据单元格必须带 ``data-label``。

背景
----
``myblog/templates/admin/base.html`` 的 ≤760px 媒体查询把 ``.admin-table``
卡片化（``thead``隐藏、``tr``/``td`` 转``display:block`` 纵向堆叠）。堆叠后
表头不见了，单元格只剩裸值 —— 「2026-09-30 10:00」这种时间、「未读」这种状态
在手机上完全失去上下文。

唯一的补救机制就是同一条规则里的::

    .admin-table td[data-label]::before { content: attr(data-label) "："; }

即**只有带 ``data-label`` 的 td 才会显示字段名**。漏标 = 该字段在手机端
彻底不可读。这条测试就是把「漏标」变成红灯，而不是靠人肉记性。

实测数据（v3.25.0）
--------------------
- 44 个 admin 模板 / 34 个 ``<table>`` / 21 个走卡片化的 ``.admin-table``
- 补标 **115** 个 td（此前只有 backup.html 10 处+ oauth_bindings.html 5 处）
- 有意**不标**的三类（见下方豁免），它们在手机端不需要/不该有字段名

作用域（别把守卫开过宽）
----------------------
只有 ``class`` 里含 ``admin-table`` 的表走卡片化。``.stats-table`` /
``.rank-table`` 在 ``admin.css:928`` 明确走 ≤900 的**横向滚动**兜底，
``.data-table`` 与裸 ``<table>``（seo.html）压根没有卡片化规则 —— 给它们加
``data-label`` 是纯噪声，会让本测试失去意义。
"""

import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "myblog/templates/admin")

# 只解析这些结构标签，够用且不会被 Jinja 表达式里的 '>' 带偏
_TAG_RE = re.compile(r"<(/?)(table|thead|tbody|tr|th|td)\b([^>]*)>", re.I)
_TH_RE = re.compile(r"<th\b([^>]*)>(.*?)</th>", re.I | re.S)
_TD_OPEN_RE = re.compile(r"<td\b([^>]*)>", re.I)
_TR_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.I | re.S)
_COLSPAN_RE = re.compile(r'colspan\s*=\s*["\']?\s*(\d+)', re.I)
_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# 至少要有这么多个 .admin-table，低于此数说明本守卫本身失效（口径腐化）
_MIN_TABLES = 15
# 至少要有这么多个 data-label，低于此数同上
_MIN_LABELS = 100

# 走「横向滚动」兜底的表类名（admin.css:928起）。它们**不需要** data-label，
# 但必须在本文件里有名字，否则 test_每个表格都纳管 会把「没人管的表」放过去。
_HORIZONTAL_SCROLL_CLASSES = {"stats-table", "rank-table", "data-table"}

# 模板内自带卡片化规则的表类名 —— backup.html 的 .bk-table 在**模板自己的**
# ≤760 媒体查询里做了卡片化（``.bk-table td::before{content:attr(data-label)}``），
# 是独立于 base.html 的第二套机制，同样算「已纳管」，但它的标注由那份模板自守。
_SELF_HOSTED_CLASSES = {"bk-table"}


def _templates():
    return sorted(glob.glob(os.path.join(TPL_DIR, "*.html")))


def _table_ranges(src):
    """(内部起点, 内部终点, 开标签属性串, 归类标记)，嵌套 table 也能配对正确。

    ``归类标记`` ∈ {"admin", "scroll", "wrapped_admin", "unmanaged"}：
    - ``admin``          ``<table class="admin-table">``，正常形态
    - ``wrapped_admin``  ``<div class="admin-table"><table>`` 套娃 —— ``.admin-table``
      的规则全是后代选择器，外层 div 照样把内层 table 卡片化了，所以它**归本文件管**
    - ``scroll``         ``.stats-table`` / ``.rank-table`` / ``.data-table``，
      走 admin.css:928 的横滚兜底，不需要 data-label
    - ``unmanaged``      谁都不归 —— test_每个表格都纳管 会拦它
    """
    out = []
    wrapped_starts = set()
    # 先扫套娃形态：<div class="admin-table"><table>…</table></div>
    # 必须在常规扫描**之前**记下这些 table 的起点，否则它们会被再登记一次
    # （一次 cat=unmanaged因为 table 自身无 class，一次 cat=admin），
    # test_每个表格都纳管 就会把 1 张表算成 2 张。
    for dm in re.finditer(r'<div\b([^>]*class="[^"]*admin-table[^"]*"[^>]*)>', src, re.I):
        d_depth = 1
        seg_end = len(src)
        for e in re.finditer(r"<(/?)div\b[^>]*>", src[dm.end():], re.I):
            d_depth += -1 if e.group(1) else 1
            if d_depth == 0:
                seg_end = dm.end() + e.start()
                break
        for t in _TAG_RE.finditer(src, dm.end(), seg_end):
            if t.group(2).lower() == "table" and not t.group(1):
                wrapped_starts.add(t.end())
                out.append((
                    t.end(), src.find("</table>", t.end()),
                    t.group(3) or "", "WRAPPED",
                ))
                break
    for m in _TAG_RE.finditer(src):
        if m.group(2).lower() != "table" or m.group(1):
            continue
        if m.end() in wrapped_starts:
            continue                      # 已按套娃形态登记过
        depth = 1
        for e in _TAG_RE.finditer(src, m.end()):
            if e.group(2).lower() != "table":
                continue
            depth += -1 if e.group(1) else 1
            if depth == 0:
                out.append((m.end(), e.start(), m.group(3) or "", "TABLE"))
                break
    # 定类
    final = []
    for cs, ce, attrs, kind in out:
        cm = re.search(r'class="([^"]*)"', attrs, re.I)
        classes = set((cm.group(1) if cm else "").split())
        if "admin-table" in classes or kind == "WRAPPED":
            cat = "admin"
        elif classes & _HORIZONTAL_SCROLL_CLASSES:
            cat = "scroll"
        elif classes & _SELF_HOSTED_CLASSES:
            cat = "self_hosted"
        else:
            cat = "unmanaged"
        final.append((cs, ce, attrs, cat))
    return final


def _th_labels(src, c_start, c_end):
    th = re.search(r"<thead\b[^>]*>", src[c_start:c_end], re.I)
    s = c_start + (th.end() if th else 0)
    e = src.find("</thead>", s)
    e = e if e != -1 else c_end
    labels = []
    for t in _TH_RE.finditer(src, s, e):
        txt = _STRIP_RE.sub(" ", t.group(2))
        txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
        labels.append(_WS_RE.sub(" ", txt).strip().rstrip(":：").strip())
    return labels


def _admin_tables(path):
    """产出 (模板名, 表序号, 表头标签列表, [未标data-label 的 td 描述])。"""
    src = open(path, encoding="utf-8").read()
    idx = 0
    for c_start, c_end, _attrs, cat in _table_ranges(src):
        if cat != "admin":
            continue
        labels = _th_labels(src, c_start, c_end)
        if not labels:
            continue
        # 护栏：嵌套 table 会让行/列切分失真，宁可不查也不能给假绿灯
        nested = sum(
            1 for e in _TAG_RE.finditer(src, c_start, c_end)
            if e.group(2).lower() == "table" and not e.group(1)
        )
        if nested:
            continue
        tb = re.search(r"<tbody\b[^>]*>", src[c_start:c_end], re.I)
        b_start = tb.end() if tb else c_start
        b_end = c_end
        if tb:
            te = src.find("</tbody>", b_start)
            b_end = te if te != -1 else c_end
        missing = []
        for tr in _TR_RE.finditer(src, b_start, b_end):
            tds = list(_TD_OPEN_RE.finditer(src, tr.start(), tr.end()))
            if not tds:
                continue
            # 豁免 1：空状态占位行（整行唯一 td + colspan>1）—— 一张卡片里
            # 放「暂无标签」，加字段名只会变成「操作：暂无标签」这种废话
            if len(tds) == 1:
                csm = _COLSPAN_RE.search(tds[0].group(1) or "")
                if csm and int(csm.group(1)) > 1:
                    continue
            for col, td in enumerate(tds):
                if col >= len(labels):
                    break
                if "data-label" in (td.group(1) or ""):
                    continue
                # 豁免 2：全选 checkbox 列（表头 th 里只有 <input>，无文字）
                if not labels[col]:
                    continue
                # 豁免 3：单元格本身就是操作/按钮容器时标注仍然有意义，
                # 但表格里「td 里只放一个 form+button」是操作列的固定写法，
                # 保留标注（手机端显示「操作：」更清楚），故不豁免。
                missing.append(
                    f"第{col + 1}列(应标 {labels[col]!r}) @{td.start()}"
                )
        yield os.path.basename(path), idx, labels, missing
        idx += 1


def test_admin_table_每格都有_data_label():
    """核心守卫：任何 .admin-table 的数据 td 漏标即红。"""
    problems = []
    total_tables = 0
    total_labels = 0
    for path in _templates():
        for name, idx, labels, missing in _admin_tables(path):
            total_tables += 1
            total_labels += sum(1 for _ in labels)
            if missing:
                problems.append(
                    f"{name} 第{idx}张 admin-table漏标 {len(missing)} 处：{'; '.join(missing[:6])}"
                )
    assert not problems, (
        "以下 .admin-table 存在未标 data-label 的数据单元格（手机端会失去字段上下文）：\n"
        + "\n".join(problems)
    )
    assert total_tables >= _MIN_TABLES, (
        f"只扫到 {total_tables} 张 .admin-table（阈值 {_MIN_TABLES}），"
        "口径可能已腐化——确认 base.html 的卡片化规则是否改了选择器"
    )
    assert total_labels >= _MIN_LABELS, (
        f"只认出{total_labels} 个表头（阈值 {_MIN_LABELS}），"
        "th 解析可能失效（表头写法变了？）"
    )


def test_data_label_不是空串():
    """data-label="" 会让::before渲染成裸的「：」，比不标还糟。"""
    bad = []
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r'data-label="([^"]*)"', src):
            if not m.group(1).strip():
                line = src[:m.start()].count("\n") + 1
                bad.append(f"{os.path.basename(path)}:{line}")
    assert not bad, f"空 data-label：{bad}"


def test_data_label_值已转义():
    """属性值里不能有裸双引号（会提前闭合属性并污染后续 HTML）。"""
    bad = []
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r'data-label="([^"]*)"', src):
            v = m.group(1)
            if "<" in v or ">" in v or "&" in v.replace("&amp;", "").replace("&quot;", ""):
                line = src[:m.start()].count("\n") + 1
                bad.append(f"{os.path.basename(path)}:{line} -> {v!r}")
    assert not bad, f"data-label 值含未转义字符：{bad}"


def test_数据行内不得有循环生成列():
    """⚠️ 这条是**真 bug 的墓碑**。

    ``seo.html`` 原本用 ``{% for cell in (r.baidu, r.indexnow) %}`` 在一个 ``<tr>`` 里
    生成百度/Bing 两列。表头是写死的两列，所以按列号静态标注**看不出问题** ——
    但两列共用同一个 ``<td>`` 源码，只能标同一个 ``data-label``，实测两列都被写成
    「百度」，Bing 列在手机端会显示成「百度：✗ 失败」。

    结论：**同一行内若用 Jinja 循环生成 td，data-label 就不可能逐列正确** ——
    只能把列显式写开（已改成两次宏调用）。

    判定口径（收紧过三次，踩了三类假阳性/假阴性）：
    - 先剥掉 ``{# ... #}`` 注释 —— 否则 seo.html 那条**已经修好**的循环会
      因为注释里还留着原代码而一直被报出来。
    - 抓「``{% for %}`` 与 ``<td>``/``</td>`` 在同一层交错」——
      ``categories.html`` 的 ``{% for other in cats %}`` 在 ``<select>`` 里生成
      ``<option>``，是**列内**循环，与列数无关，不能误伤。
    - ⚠️ 不能只判「循环在 ``<td>`` **内部**」：原 bug 形态是循环包住 td
      （``{% for %}…<td>…</td>{% endfor %}``），判「循环在 td 内」永远抓不到它，
      变异验证第11 项就是这么变绿的。真正的判据是**循环与 td 标签交错**。
    """
    offenders = []
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for c_start, c_end, _attrs, cat in _table_ranges(src):
            if cat != "admin":
                continue
            for tr in _TR_RE.finditer(src, c_start, c_end):
                row = re.sub(r"\{#.*?#\}", "", tr.group(0), flags=re.S)
                # 逐 token 扫：<td>/<th> 与 {% for %} 谁在谁前面
                tokens = re.findall(
                    r"<t[dh]\b|</t[dh]>|\{%-?\s*(?:for|endfor)\b",
                    row, re.I,
                )
                depth = 0
                loop_depth_at_cell = []      # 每个 cell 开标签所处的循环深度
                for tok in tokens:
                    low = tok.lower()
                    if low.startswith("{%") and "endfor" not in low:
                        depth += 1
                    elif "endfor" in low:
                        depth = max(0, depth - 1)
                    elif low.startswith("<t"):
                        loop_depth_at_cell.append(depth)
                # 同一行里 cell 所处深度不一致 = 有 cell 是循环生成的
                if loop_depth_at_cell and len(set(loop_depth_at_cell)) > 1:
                    offenders.append(
                        f"{os.path.basename(path)}: 同一 <tr> 内 td 处于不同循环深度 "
                        f"{sorted(set(loop_depth_at_cell))} -> 有列由 Jinja 循环生成"
                    )
    assert not offenders, (
        "数据行里用 Jinja 循环生成 td 会让 data-label 无法逐列正确（"
        "同一段源码只能标一个标签）。请把列显式写开：\n" + "\n".join(offenders)
    )


def test_每个表格都纳管():
    """口径护栏：模板里的每张表都必须被某个机制管起来 ——
    要么走卡片化（``.admin-table``，含套娃形态，本文件负责），
    要么走横滚兜底（``.stats-table`` / ``.rank-table`` / ``.data-table``）。

    这条是 **变异 [7] 逼出来的**：原先漏标检查与「class 是否含 admin-table」
    耦合，把 ``admin-table`` 改个名，整张表就从检查视野里消失 ——
    守卫当时仍绿，属于真真空。现在独立断言分类计数。
    """
    counts = {"admin": 0, "scroll": 0, "self_hosted": 0, "unmanaged": 0}
    unmanaged = []
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for _c_start, _c_end, attrs, cat in _table_ranges(src):
            counts[cat] += 1
            if cat == "unmanaged":
                cm = re.search(r'class="([^"]*)"', attrs, re.I)
                unmanaged.append(
                    f"{os.path.basename(path)} class={(cm.group(1) if cm else None)!r}"
                )
    assert not unmanaged, (
        f"共 {sum(counts.values())} 张表，{counts['unmanaged']} 张无人管：{unmanaged}。"
        "新增表格请给它加 admin-table（卡片化，需补 data-label）或纳入横滚兜底类名，"
        "否则它在手机端既没字段名也没纳管"
    )
    assert counts["admin"] >= _MIN_TABLES, (
        f"只认出 {counts['admin']} 张卡片化表（阈值 {_MIN_TABLES}），"
        "口径可能已腐化——确认 base.html 的卡片化规则是否改了选择器"
    )


def test_非卡片化的表不带_data_label():
    """反向守卫：``.stats-table`` / ``.rank-table`` / ``.data-table`` 走
    ``admin.css:928`` 的横滚兜底，**全站没有它们的 ``::before`` 规则** ——
    给它们标 data-label 是死标注（属性在，字段名永不渲染），纯噪声。

    合法例外：``backup.html`` 的 ``.bk-table`` 在**模板内**自带卡片化规则
    （``backup.html`` 的 ≤760 媒体查询里有 ``.bk-table td::before{content:attr(data-label)}``），
    它是独立于 base.html 的第二套机制，必须放行。
    """
    # 模板内自带 ::before{content:attr(data-label)} 规则的表类名 -> 允许 data-label
    # 两种写法都要认：base.html 是 `.admin-table td[data-label]::before`，
    # backup.html 是 `.bk-table td::before`（不限属性选择器）。
    self_hosted = set()
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(
            r"\.([a-zA-Z][\w-]*)\s+td(?:\[data-label\])?::before\s*\{[^}]*attr\(\s*data-label",
            src,
        ):
            self_hosted.add(m.group(1))

    noise = []
    for path in _templates():
        src = open(path, encoding="utf-8").read()
        for c_start, c_end, attrs, cat in _table_ranges(src):
            if cat != "scroll":
                continue
            classes = set(
                re.search(r'class="([^"]*)"', attrs, re.I).group(1).split()
            )
            if classes & self_hosted:
                continue
            if re.search(r"data-label=", src[c_start:c_end]):
                noise.append(f"{os.path.basename(path)} class={' '.join(classes)!r}")
    assert not noise, (
        "这些表既不走 base.html 的卡片化、模板内也没有自己的 ::before 规则，"
        f"data-label 是永不渲染的死标注：{noise}"
    )
    # 护栏：bk-table 这条例外必须真的存在，否则本测试会把合法标注误杀而没人知道
    assert "bk-table" in self_hosted, (
        "没在任何模板里找到自带 td[data-label]::before 的表格类——"
        "若 backup.html 的规则被挪进 admin.css，请把它加进 self_hosted 口径"
    )


def test_base_css_规则与守卫同口径():
    """守卫的前提是 base.html 那条 ::before 规则还在。规则若被删/改选择器，
    本文件全部断言就成了「测一个不存在的行为」的空转。"""
    base = open(os.path.join(TPL_DIR, "base.html"), encoding="utf-8").read()
    assert "td[data-label]::before" in base, (
        "base.html 的 .admin-table td[data-label]::before 规则不见了，"
        "data-label 不会渲染成字段名——请同步修本守卫或修CSS"
    )
    assert re.search(r"@media\s*\(max-width:\s*760px\)", base), (
        "base.html 里找不到 ≤760px 媒体查询，卡片化规则可能被挪走或改了断点"
    )
    assert ".admin-table thead { display: none; }" in base.replace("  ", " ") or \
           re.search(r"\.admin-table\s+thead\s*\{[^}]*display:\s*none", base), (
        "卡片化规则里的 thead 隐藏没了——那样横向滚动就还在，本守卫的前提改变"
    )


@pytest.mark.parametrize("tpl", [os.path.basename(p) for p in _templates()])
def test_模板_jinja_可解析(tpl):
    """批量插入 data-label 最大的风险是把标签插到标签外；
    Jinja 解析不过 = 模板报废。"""
    from jinja2 import Environment

    src = open(os.path.join(TPL_DIR, tpl), encoding="utf-8").read()
    Environment().parse(src, filename=tpl)


def test_已知的三个豁免确实还在():
    """把豁免规则也钉住：一旦空状态行改成不写 colspan（或checkbox 列加了文字），
    对应豁免就该失效、必须补标——这条测试提醒人来复核。"""
    # tags.html 的空状态行
    tags = open(os.path.join(TPL_DIR, "tags.html"), encoding="utf-8").read()
    assert '<td colspan="4">暂无标签</td>' in tags, (
        "tags.html 空状态行写法变了（不再用 colspan 合并），"
        "现在它会被当数据行要求标 data-label——请复核"
    )
    # comments.html 的全选列
    cm = open(os.path.join(TPL_DIR, "comments.html"), encoding="utf-8").read()
    head = cm[cm.find("<thead"): cm.find("</thead>")]
    first_th = _TH_RE.search(head)
    assert first_th is not None
    body = _STRIP_RE.sub("", first_th.group(2)).replace("&nbsp;", "").strip()
    assert body == "", (
        f"comments.html 首个 th 现在有文字 {body!r}——它不再是无标签豁免的"
        "checkbox 列，守卫会开始要求标注，请复核是否该标"
    )
