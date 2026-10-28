"""v5.2.6：相册页视频卡片的**元素查找方式**守卫。

## 背景（这是线上实测踩出来的真 bug，不是理论推演）

v5.2.5 把 `<video controls>` 换成「自绘播放按钮 + JS `play()`」，
上线后浏览器实测发现：**点播放按钮毫无反应** —— 视频不播、按钮不消失、
原生控件也不出现。

根因是元素查找写错了：

```js
// ❌ v5.2.5 首版（错的）
function videoElOf(it) {
  const box = document.querySelector('[data-video-id="' + it.id + '"]');
  return box ? box.querySelector("video") : null;   // ← 恒为 null
}
```

模板里 `data-video-id` 是挂在 **`<video>` 自己**身上的：

```html
<video :data-video-id="it.id" ...></video>
```

于是 `querySelector('[data-video-id="7"]')` 命中的**就是那个 video 元素本身**，
它内部没有 video 子节点 → `box.querySelector("video")` 恒为 `null` →
`playVideo()` 第一行 `if (!v) return;` 直接返回 → **点了没反应**。

## 为什么值得单独立一条守卫

这类 bug 的特征是「**静默失败**」：构建通过、测试全绿、页面能渲染、
视频甚至能加载（`readyState=4`、时长正常），**只有「点击播放」这一下没反应**。
没有断言盯着的话，几乎不可能在下次改动里被发现。

本文件把「查找 video 元素的机制」钉死：**必须用 Vue 的函数式 ref 直接持有元素**，
不允许再写「先找容器、再在容器里 find 嵌套元素」这种依赖 DOM 层级假设的写法。

## 为什么只断言机制不断言具体实现

实现可以换（Map 换成 WeakMap、ref 换成 provide/inject…），
但「不能靠 DOM 层级假设去找元素」这条不变量必须成立。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALBUM_VIEW = os.path.join(ROOT, "vue-frontend", "src", "views", "AlbumView.vue")


def _src():
    with io.open(ALBUM_VIEW, encoding="utf-8") as f:
        return f.read()


def _code_only(src):
    """剥掉注释，只留真正的代码。

    🔴 判据必须跳过注释 —— 本文件自己的注释里就写了
    `document.querySelector('[data-video-id="X"]')` 这个**反面示例**，
    不剥注释的话守卫会拿自己的注释把自己判成违规。
    （与部署链审查里同一个坑：匹配 `cd "$WORK"` 时命中了注释里的同名字样。）
    """
    out = []
    for line in src.splitlines():
        s = line.lstrip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*") or s.startswith("<!--"):
            continue
        out.append(line)
    return "\n".join(out)


def test_不用容器嵌套查找来定位video元素():
    """禁止「先找带标记的容器、再在它内部找 video」这种写法。

    判据：`querySelector(...)` 的结果**不得**再接 `.querySelector("video")`。
    这种写法在标记挂在 video 自身时会静默返回 null（v5.2.5 的真 bug）。
    """
    src = _code_only(_src())
    bad = re.findall(
        r"""querySelector\(\s*['\"]\[data-video-id[^)]*\)\s*\)?\s*[\r\n]*\s*\??\.?\s*querySelector\(\s*['\"]video['\"]""",
        src,
    )
    assert not bad, (
        "禁止「先按 data-video-id 找元素、再在它内部 querySelector('video')」—— "
        "data-video-id 挂在 <video> 自身时，内部没有 video 子节点，"
        "结果是 null，表现为「点播放按钮毫无反应」（v5.2.5 线上实测）"
    )


def test_查找video元素用函数式ref登记():
    """必须用 Vue 的函数式 ref 直接持有 video 元素。"""
    src = _code_only(_src())
    assert ":ref=" in src and "bindVideo" in src, (
        "video 元素必须用函数式 ref 登记（:ref=\"(el) => bindVideo(it.id, el)\"），"
        "这样不依赖 DOM 层级假设"
    )
    assert re.search(r":ref=\"\(el\)\s*=>\s*bindVideo\(", src), (
        "函数式 ref 必须把元素登记进 videoEls 登记表"
    )


def test_函数式ref在两处video卡片上都绑定了():
    """章节内与未分组两处 video 都要绑定 —— 漏一处那处就点不动。"""
    src = _code_only(_src())
    n = len(re.findall(r":ref=\"\(el\)\s*=>\s*bindVideo\(", src))
    assert n == 2, (
        "期望 2 处 video 绑定函数式 ref（章节内 + 未分组），实际 %d 处" % n
    )


def test_视频不靠data_video_id做元素定位():
    """`data-video-id` 只用于 @ended 事件里回查条目 id，不能再用于定位元素。"""
    src = _code_only(_src())
    # 允许出现：模板里的 :data-video-id 绑定、@ended 里读 dataset.videoId
    # 禁止出现：querySelector 里拿 data-video-id 做选择器
    sel = re.findall(r"querySelector\(\s*['\"]\[data-video-id", src)
    assert not sel, (
        "不允许用 querySelector('[data-video-id=...]') 定位 video 元素"
    )


def test_播放按钮与video元素绑定同一个条目id():
    """按钮与 video 必须用同一个 id 键，否则登记的 element 对不上按钮点的那个。"""
    src = _code_only(_src())
    vid_bind = re.findall(r":ref=\"\(el\)\s*=>\s*bindVideo\(\s*it\.id\s*,", src)
    btn_click = re.findall(r"@click\.stop=\"playVideo\(it\)\"", src)
    assert len(vid_bind) == 2, "两处 video 都应绑定 it.id"
    assert len(btn_click) == 2, "两处播放按钮都应调用 playVideo(it)"


def test_videoElOf只从登记表取元素():
    """`videoElOf` 必须只认登记表 —— 它是所有播放逻辑的唯一入口。

    这条判据比「模式匹配」更直接：只要这个函数的实现里出现 DOM 查询
    （无论写成 `querySelector` 还是 `getElementById` 还是 `closest`），
    就说明又退回了「依赖 DOM 层级假设」的写法。
    """
    src = _code_only(_src())
    m = re.search(r"function\s+videoElOf\s*\([^)]*\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "找不到 videoElOf 函数"
    body = m.group(1)
    for bad in ("querySelector", "getElementById", "closest", "document."):
        assert bad not in body, (
            "videoElOf 里出现了 %r —— 它必须只从 videoEls 登记表取元素，"
            "不能靠 DOM 查询（v5.2.5 的真 bug 就是靠 DOM 查询取到了 null）" % bad
        )
    assert "videoEls.get" in body, "videoElOf 应从 videoEls 登记表取元素"
