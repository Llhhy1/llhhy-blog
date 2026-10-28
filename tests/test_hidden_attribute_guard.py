# -*- coding: utf-8 -*-
"""`hidden` 属性的兜底守卫（v5.1.3）。

## 为什么需要这个测试

HTML 的 `hidden` 属性只是浏览器默认样式表里的一条 `[hidden] { display: none }`，
而 **UA 样式表的优先级低于任何作者样式** —— 只要 CSS 给同一元素写了任何
`display`，`hidden` 属性就彻底失效（与特异性无关，是来源顺序问题）。

v5.1.0 就踩了这个坑：`album_edit.html` 的媒体选择器写成

    <div class="album-picker-mask" id="picker-mask" hidden>

而 `admin.css` 里 `.album-picker-mask { display: flex }`。结果：

* 弹层从页面加载起就一直显示；
* 点「关闭」执行 `el.hidden = true`，属性设上了但视觉毫无变化 → 用户看到
  「点关闭没响应」；
* 刷新后仍然带着 `hidden` 属性渲染，还是被 `display: flex` 盖掉 → 用户看到
  「刷新后还是这个弹窗」。

排查时极易误判成「JS 报错事件没绑上」（实际 JS 完全正常），所以在 CSS 层
加一条 `[hidden] { display: none !important }` 兜底，并用本测试锁住。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_CSS = os.path.join(ROOT, "myblog", "static", "admin.css")
ALBUM_EDIT = os.path.join(ROOT, "myblog", "templates", "admin", "album_edit.html")


def _read(path):
    return io.open(path, encoding="utf-8").read()


def test_admin_css_has_hidden_fallback():
    """admin.css 必须有 `[hidden]` 兜底规则，且带 !important。

    去掉 !important 的话，同特异性下后写的 `display` 仍会赢，
    事故会原样复发。
    """
    css = re.sub(r"/\*.*?\*/", "", _read(ADMIN_CSS), flags=re.S)  # 去掉注释，避免注释里的示例代码骗过断言
    m = re.search(r"\[hidden\]\s*\{([^}]*)\}", css)
    assert m, "admin.css 缺少 [hidden] 兜底规则"
    body = m.group(1).replace(" ", "").lower()
    assert "display:none" in body, "兜底规则必须是 display: none，实际：%r" % m.group(1)
    assert "!important" in body, "兜底规则必须带 !important，否则同特异性下会被 display 覆盖"


def test_album_picker_uses_hidden_attribute():
    """相册媒体选择器必须靠 `hidden` 属性隐藏（配合上面的兜底规则）。

    若改成别的隐藏方式也需同步调整本测试 —— 目的只是不让它「默认可见」。
    """
    html = _read(ALBUM_EDIT)
    m = re.search(r"<div[^>]*id=\"picker-mask\"[^>]*>", html)
    assert m, "album_edit.html 里找不到 #picker-mask"
    assert re.search(r"\bhidden\b", m.group(0)), \
        "#picker-mask 必须带 hidden 属性，否则弹层会一直显示：%r" % m.group(0)


def test_picker_mask_really_has_display_conflict():
    """确认冲突场景真实存在：`.album-picker-mask` 确实写了 display。

    这条不是「证明代码对」，而是防止有人把 display 删掉后，兜底规则变成
    一条无用的规则、而测试仍然绿 —— 那样就失去了守卫意义。
    """
    css = re.sub(r"/\*.*?\*/", "", _read(ADMIN_CSS), flags=re.S)
    m = re.search(r"\.album-picker-mask\s*\{([^}]*)\}", css)
    assert m, "admin.css 缺少 .album-picker-mask 规则"
    assert re.search(r"display\s*:", m.group(1)), \
        ".album-picker-mask 没有 display 声明 —— 若真改了实现，请同步更新本测试"


def test_no_template_relies_on_hidden_with_inline_display():
    """后台模板里带 hidden 属性的元素，不得同时写内联 display。

    内联样式优先级高于本文件的 `[hidden]`（除非兜底规则带 !important ——
    它确实带了，但内联 style 依然比外部样式表强，只能靠 !important 打赢，
    这条断言是为了让「内联 display + hidden」这种组合在评审时被看见）。
    """
    import glob
    bad = []
    for p in glob.glob(os.path.join(ROOT, "myblog", "templates", "admin", "*.html")):
        html = _read(p)
        for m in re.finditer(r"<[^>]*\bhidden\b[^>]*>", html):
            tag = m.group(0)
            if "aria-hidden" in tag:
                continue
            if re.search(r"style\s*=\s*\"[^\"]*display", tag, re.I):
                bad.append((os.path.basename(p), tag[:90]))
    assert not bad, "这些元素同时用了 hidden 属性与内联 display，行为不可预期：%r" % bad
