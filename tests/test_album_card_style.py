# -*- coding: utf-8 -*-
"""v5.3.0 相册卡片样式的「三处同步」守卫。

## 为什么需要这条守卫

同一段 `.post-album-*` 样式在**三个互不加載**的样式表里各存一份：

| 文件                                | 用在哪                                   |
|-------------------------------------|------------------------------------------|
| `myblog/static/admin.css`           | 写文章页的实时预览面板                   |
| `myblog/static/style.css`           | 未发布稿预览页 `/admin/preview/<token>`  |
| `vue-frontend/src/styles/look.css`  | 前台 SPA（正文 v-html 注入）             |

它们互不 `@import`，也不是同一套构建产物 —— 所以「改了一处」不会自动同步
到另外两处，表现是**某个入口的卡片长得不对**（预览里正常、前台难看，或反之）。

这类「三份拷贝」靠人记必然漏。这里把「选择器集合必须一致」钉死：
新增一个卡片子元素而只改了一个文件 → 变红。

## 判据为什么先剥注释

注释里会写到类名（「这段样式在三处各存一份」之类），直接 grep 会把**注释里
提到的类名**当成已定义 —— 守卫就拿自己的注释把自己判成通过。
（同一类坑在本项目已踩 3 次，见 MEMORY.md「代码陷阱」。）
"""
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    "myblog/static/admin.css",
    "myblog/static/style.css",
    "vue-frontend/src/styles/look.css",
]

# 卡片的结构性选择器（少一个，某个入口的卡片就会缺一块）
REQUIRED = [
    ".post-album-card",
    ".post-album-cover",
    ".post-album-body",
    ".post-album-title",
    ".post-album-summary",
    ".post-album-meta",
    ".post-album-link",
]

# 只在后台用的两个弹层的独有部件
ADMIN_ONLY = [".acp-row", ".acp-cover", ".acp-body", ".amp-field"]

_BLOCK_RE = re.compile(r"/\*.*?\*/", re.S)


def _code_only(src: str) -> str:
    """剥掉注释（块注释 + 行注释 + HTML 注释）再匹配，避免注释里的类名命中。"""
    src = _BLOCK_RE.sub("", src)
    lines = []
    for ln in src.splitlines():
        s = ln.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("<!--"):
            continue
        lines.append(ln)
    return "\n".join(lines)


def _read(rel):
    with io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("rel", FILES)
@pytest.mark.parametrize("sel", REQUIRED)
def test_卡片样式三处都有(rel, sel):
    assert sel in _code_only(_read(rel)), (
        "%s 缺 %s —— 卡片样式在三份样式表里各存一份（admin.css / style.css / look.css），"
        "改一处必须改三处，否则某个入口的卡片会缺一块" % (rel, sel)
    )


def test_后台弹层的独有部件只在_admin_css():
    for sel in ADMIN_ONLY:
        assert sel in _code_only(_read("myblog/static/admin.css")), (
            "admin.css 缺 %s（写文章页的两个弹层）" % sel
        )


def test_守卫自身的判据会剥注释():
    """反证：把类名**只**写在注释里应当判为缺失 —— 否则本守卫形同虚设。"""
    fake = "/* 说明：这里引用 .post-album-card 只是为了举例子 */\n.x { color: red; }"
    assert ".post-album-card" in fake
    assert ".post-album-card" not in _code_only(fake)
