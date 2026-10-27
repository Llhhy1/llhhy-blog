"""v5.0.0 前台样式**层叠顺序**守卫。

## 背景（这是实测踩出来的，不是理论推演）

改 统一观感层时，第一版把规则追加在 `global.css` 末尾，构建也通过了 ——
但页面上的大标题**根本没变**。原因：

```
main.js:  import global.css → import responsive.css
responsive.css:75:  .page-title { font-size: clamp(19px, 4.6vw, 25px); }
```

`responsive.css` 在 `global.css` **之后**导入，同特异性下后者胜 —— 所以
「写在 global.css 末尾」并不等于「最终生效」。判据很实在：构建产物
`index-*.css` 里 `.page-title` 的**最后一条**仍是旧值。

正解是把观感层单独成 `styles/look.css`，排在 responsive.css 之后导入。
本文件把这个顺序钉死 —— 否则下次有人改导入顺序，视觉会静默退化，
而测试全绿、构建全绿，没人会发现。

## 为什么只断言顺序不断言具体样式

具体样式值会随设计迭代变化，锁死了反而是负担。这里锁的是**机制**：
「覆盖层必须最后加载」这条不变量一旦破了，全站的视觉改动都会失效。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_JS = os.path.join(ROOT, "vue-frontend", "src", "main.js")


def _main_src():
    with io.open(MAIN_JS, encoding="utf-8") as f:
        return f.read()


def _import_line(src, name):
    for line in src.splitlines():
        if name in line and ("import" in line or "@import" in line):
            return line
    return None


def test_look_css_在_responsive_css_之后导入():
    """覆盖层必须在响应式基座之后 —— 顺序反了大标题/胶囊按钮会被压回旧值。"""
    src = _main_src()
    look = _import_line(src, "look.css")
    resp = _import_line(src, "responsive.css")
    assert resp is not None, "main.js 里找不到 responsive.css 的导入"
    assert look is not None, "main.js 里找不到 look.css 的导入"
    lines = src.splitlines()
    assert lines.index(resp) < lines.index(look), (
        "look.css 必须排在 responsive.css 之后，否则 responsive.css:75 的 "
        ".page-title 会覆盖观感层的大标题（实测表现为「改了但页面没变」）。")


def test_look_css_文件存在且非空():
    p = os.path.join(ROOT, "vue-frontend", "src", "styles", "look.css")
    assert os.path.isfile(p), "统一观感层文件丢失"
    with io.open(p, encoding="utf-8") as f:
        body = f.read()
    assert "--ui-radius-card" in body, "观感层没有引用设计令牌，说明规则被清空了"

    # ⚠️ 变异验证：把 look.css 的内容挪回 global.css 末尾，本用例通过但页面失效 ——
    # 所以顺序那条断言才是真正起作用的一道，本条只是兜底防误删。
    assert "page-title" in body and "backdrop-filter" in body
