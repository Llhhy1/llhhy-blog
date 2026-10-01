"""表单可访问名守卫（v3.25.1 · placeholder-only 治理）。

**背景**：审计（ROADMAP §B）记「表单 placeholder-only」为长期债，实测 **71 处**
控件只有 placeholder、没有任何可访问名。placeholder 在用户开始输入**后立即消失**，
且部分屏幕阅读器不把它当作可访问名 —— 输入到一半就不知道这一格是什么了。

**本轮实测的三类形态**（修法不同，别一刀切）：
- **A 类 40 处**：前面已有 `<label>` 文本，只是**没有 `for`/`id` 配对**（视觉上看得见，
  程序上无关联）。修法是补 `for` + `id`，顺带获得「点标签聚焦控件」。
- **B 类 29 处**：纯 placeholder 表单（新建系列/友链/用户等），没有任何 label 元素。
  修法是补 `aria-label`，**值取字段语义名而非 placeholder 原文** —— 很多 placeholder
  是示例值（`https://...` / `LTAI...` / `root@192.168.1.10`），复制过去等于没标签。
- **C 类 8 处**：`<span class="qc-label">` 冒充 label。改成 `<label class="qc-label" for=...>`
  （CSS 用类选择器，改成 label 元素**样式零影响**）。

**踩坑（第一版脚本真的做错了，靠本守卫 + 校验脚本抓出来）**：
1. **给已有 id 的控件又加一个 id** —— edit_post/settings 的控件原本就有
   `f-title` / `sel-category` / `slugMode`（JS 与 CSS 依赖），新加第二个会产出
   `id="title" ... id="f-title"` 这种**重复属性**：非法 HTML，且浏览器只认第一个，
   等于把 JS 选择器打断。**11 处中招，全部回滚重做**。正解：控件已有 id 就**复用**它，
   只改 label 的 `for`，控件一个字都不动。
2. **循环内不能加固定 id** —— series/categories 的编辑行在 `{% for %}` 里，
   每项都渲染一次，固定 id 必然重复。正解：用 Jinja 变量拼唯一 id
   （`ser-name-{{ s.id }}` / `cat-move-{{ c.id }}`）。

**为什么判据要认「包裹式 label」**：`<label>文本<br><input></label>` 也是有效关联，
不算缺陷（games_llm_config.html 就是这种）。只认 `for` 会误报。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "myblog" / "templates"

# 不需要可访问名的控件类型
_EXEMPT_TYPES = {"hidden", "submit", "button", "reset", "image"}

_CTRL = r"<(input|select|textarea)\b"


def _strip_comment(sel):
    """剥掉选择器里的 CSS 注释（模板里也有 `<!-- -->` 夹在选择器旁的情况）。"""
    return re.sub(r"/\*.*?\*/", "", sel).strip()


def _iter_controls(src):
    """产出 (match, tag_name, attrs)。"""
    for m in re.finditer(_CTRL + r"([^>]*)>", src, re.I):
        yield m, m.group(1).lower(), m.group(2)


def _has_accessible_name(src, m, attrs):
    """该控件是否已有可访问名（aria-label / for=id / 被 label 包裹 / 被 span.qc-label 前置已改）。"""
    if re.search(r"aria-label(?:ledby)?=", attrs, re.I):
        return True
    cid = re.search(r'\bid=["\']([^"\']+)["\']', attrs)
    if cid and re.search(r'<label[^>]*\bfor=["\']%s["\']' % re.escape(cid.group(1)),
                         src, re.I):
        return True
    # 包裹式：<label ...> ... 本控件 ... </label>
    for lm in re.finditer(r"<label\b[^>]*>(.*?)</label>", src, re.I | re.S):
        if lm.start() <= m.start() < lm.end():
            return True
    return False


def test_every_placeholder_control_has_accessible_name():
    """凡带 placeholder 的可见控件，都必须有可访问名（placeholder 不算）。"""
    if not TEMPLATES.exists():
        pytest.skip("模板目录不存在")

    problems = []
    checked = 0
    for p in sorted(TEMPLATES.rglob("*.html")):
        src = p.read_text(encoding="utf-8")
        for m, tag, attrs in _iter_controls(src):
            tm = re.search(r'\btype=["\']([^"\']+)["\']', attrs, re.I)
            if tm and tm.group(1).lower() in _EXEMPT_TYPES:
                continue
            if "placeholder" not in attrs.lower():
                continue
            checked += 1
            if not _has_accessible_name(src, m, attrs):
                line = src[:m.start()].count("\n") + 1
                ph = re.search(r'placeholder=["\']([^"\']*)["\']', attrs, re.I)
                problems.append("  %s:%d  <%s> placeholder=%r 无 aria-label / label for / 包裹"
                                % (p.relative_to(ROOT).as_posix(), line, tag,
                                   (ph.group(1) if ph else "")[:40]))

    # 口径护栏：模板被整体删掉或正则失效时，这里会先红，不至于静默假绿。
    # 阈值取实测（v3.25.1 治理后为 72）向下留 12 的余量 —— 目的是捕捉
    # 「正则失效导致扫不到」（那会掉到接近 0），不是卡死新增数量。
    assert checked >= 60, (
        "扫到的带 placeholder 控件只有 %d 个（实测基准 72，下限 60）——"
        "正则或模板路径可能失效，守卫形同虚设" % checked)
    assert not problems, (
        "以下控件只有 placeholder、没有可访问名（补 aria-label 或 label for）：\n"
        + "\n".join(problems))


def test_no_duplicate_id_attribute_in_one_tag():
    """同一个标签内不得出现两次 id 属性（v3.25.1 脚本真踩过的坑）。

    重复属性是非法 HTML：浏览器只认**第一个**，后面的被丢弃。给已有 id 的控件
    再加一个 id，等于把依赖第二个 id 的 JS/CSS 选择器静默打断。
    """
    if not TEMPLATES.exists():
        pytest.skip("模板目录不存在")

    problems = []
    for p in sorted(TEMPLATES.rglob("*.html")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"<[a-zA-Z][^>]*>", src):
            ids = re.findall(r'\sid=["\']([^"\']+)["\']', m.group(0))
            if len(ids) > 1:
                line = src[:m.start()].count("\n") + 1
                problems.append("  %s:%d id 重复 %s"
                                % (p.relative_to(ROOT).as_posix(), line, ids))
    assert not problems, (
        "同一标签内有重复 id 属性（非法 HTML，浏览器只认第一个）：\n"
        + "\n".join(problems))


def test_no_span_pretending_to_be_label():
    """不得再用 `<span class="qc-label">` 冒充标签（v3.25.1 已全部改为真 `<label>`）。

    span 只是长得像标签，程序上**没有任何关联** —— 屏幕阅读器读到这里就是一个
    孤立的 input。改成 `<label class="qc-label" for=...>`：CSS 用的是类选择器，
    换成 label 元素对视觉**零影响**，却拿到了真正的关联。
    """
    if not TEMPLATES.exists():
        pytest.skip("模板目录不存在")

    problems = []
    for p in sorted(TEMPLATES.rglob("*.html")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r'<span[^>]*class=["\'][^"\']*\bqc-label\b[^"\']*["\'][^>]*>',
                             src, re.I):
            line = src[:m.start()].count("\n") + 1
            problems.append("  %s:%d %s"
                            % (p.relative_to(ROOT).as_posix(), line, m.group(0)[:80]))
    assert not problems, (
        "仍有用 <span class=\"qc-label\"> 冒充标签的地方（改成 "
        "<label class=\"qc-label\" for=\"...\">）：\n" + "\n".join(problems))
