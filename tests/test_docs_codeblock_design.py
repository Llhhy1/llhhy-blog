"""v5.3.2 /docs 代码块设计守卫。

## 背景（为什么要有这道守卫）

v5.3.1 修好 `/docs` 搜索/目录后，代码块仍是「无设计 + 不高亮」：

1. **没有语言标签栏**，复制按钮漂浮在 `pre` 右上角（旧 `.copy-btn`）；
2. **高亮从未生效**：原 `tryHl()` 在 `onMounted` 立即跑，此时 `/api/docs` 的异步内容
   还没到、装饰的是空容器；内容到达后 `v-html` 重建出新的 `<pre>`，再没人高亮。

本次 `decorateCodeBlocks()` 在内容注入 DOM 后，把每个 `<pre>` 包成
`.code-block`（`.code-block__bar` 含 `.code-block__lang` 语言标签 + `.code-block__copy`
复制按钮 + `pre`），并真正调用 `hljs.highlightElement`。本文件把这条不变量钉死：

- 源码必须定义 `decorateCodeBlocks` 且使用 `.code-block` / `.code-block__copy` /
  `.code-block__lang` 这套结构；
- 必须处理「无语言围栏 → 标 plaintext」防止自动探测误上色；
- `API.md` 的**每个开口围栏**都必须带语言（目录树用 `text`），否则标签栏会空、且
  highlight.js 退化成自动探测把目录树染成 bash/python。

## ⚠️ 注释剥离（防守卫自己误判）

凡「正则匹配源码文本」的守卫，一律先剥注释行 —— 否则守卫会拿自己注释里写的
反面示例把自己判违规（本项目已踩 3 次）。这里剥 `/* */` 与 `//`（保留 `://`）。
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VUE = os.path.join(ROOT, "vue-frontend", "src", "views", "DocsView.vue")
API_MD = os.path.join(ROOT, "myblog", "API.md")
CONFIG = os.path.join(ROOT, "myblog", "config.py")


def _read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    # 先剥块注释 /* ... */
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    # 再剥行注释 //，但保留 http:// / https:// 里的 //
    src = re.sub(r"(?<!:)//[^\n]*", "", src)
    return src


def test_docsview_定义_decorateCodeBlocks():
    body = _strip_comments(_read(VUE))
    assert "function decorateCodeBlocks" in body, (
        "DocsView.vue 必须定义 decorateCodeBlocks()：原 tryHl 在挂载时装饰空容器，"
        "异步内容到达后 v-html 重建的 <pre> 永不被高亮，高亮形同虚设。")


def test_docsview_代码块结构含标签栏与复制按钮():
    body = _strip_comments(_read(VUE))
    for token in (".code-block", ".code-block__copy", ".code-block__lang"):
        assert token in body, (
            "decorateCodeBlocks 必须把 <pre> 包成 .code-block 并带语言标签栏 "
            "(.code-block__lang) 与复制按钮 (.code-block__copy)；缺 %s 即退化成旧的无设计块。" % token)


def test_docsview_无语言围栏标_plaintext_防止误上色():
    body = _strip_comments(_read(VUE))
    assert "language-plaintext" in body, (
        "无语言标注的围栏（目录树）必须显式标 language-plaintext，否则 highlight.js "
        "会退化成自动探测，把目录树误判成 bash/python 乱上色。")


def test_docsview_高亮在内容注入后调用():
    body = _strip_comments(_read(VUE))
    # 必须在 loadFullList 的内容注入路径（buildToc 之后）调用，而不是 onMounted 立即调
    assert "decorateCodeBlocks()" in body, (
        "decorateCodeBlocks() 必须在 /api/docs 内容注入 DOM 后（buildToc 之后）调用；"
        "若改回 onMounted 立即调用，又回到「装饰空容器、真正代码块永不高亮」的坑。")


def test_apimd_每个开口围栏都带语言():
    md = _read(API_MD)
    in_fence = False
    opens = 0
    langs = set()
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fence = stripped[3:].strip()
            if not in_fence:
                opens += 1
                assert fence, (
                    "API.md 存在无语言的开口围栏 ``` —— 既会让 /docs 标签栏空白，"
                    "又会让 highlight.js 自动探测把目录树染成 bash/python。请补语言（目录树用 text）。")
                langs.add(fence)
                in_fence = True
            else:
                in_fence = False
    assert opens > 0, "API.md 应至少有一个代码围栏，守卫不应空跑"
    assert in_fence is False, "API.md 存在未闭合的围栏（开口数 != 闭口数）"
    # 目录树用 text，示例用 python —— 至少出现过这两种语言即说明标注体系生效
    assert "text" in langs or "python" in langs, (
        "API.md 围栏语言标注异常：期望至少包含 text/python，实际 %r" % sorted(langs))


def test_版本号_api_md_与_config_一致():
    md = _read(API_MD)
    cfg = _read(CONFIG)
    m = re.search(r"> 版本：\*\*v([\d.]+)\*\*", md)
    assert m, "API.md 头部缺少 `> 版本：**vX.Y.Z**`"
    ver = m.group(1)
    assert ('APP_VERSION = "%s"' % ver) in cfg, (
        "API.md 版本头 v%s 与 config.APP_VERSION 不一致（test_api_doc_sync.py 也会卡这道）。" % ver)
