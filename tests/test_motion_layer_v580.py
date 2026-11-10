"""v5.8.0 动效层守卫。

钉住三件以前「声明过但没真正落地」的事，防止改 CSS 时悄悄退化：

1. 主题包 motion 三档（off / subtle / full）**都要有实际规则**，
   且 full 明显强于 subtle、off 彻底关掉 —— 后台主题中心的下拉不是摆设。
2. v-reveal 的错峰、单例观察器、卸载解绑与列表扩面。
3. 阅读进度条走合成层（transform/rAF），不再每次滚动写 width 触发 layout。

同时守两条边界：动效规则不许写进 look.css 的 P2 章回语言层（那里禁
@media / 禁 !important / 每条选择器必须带 :root[data-layout="chapter"] 前缀），
也不许新建 CSS 文件（main.js 的三行 import 被冻结）。
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


GLOBAL_CSS = "vue-frontend/src/styles/global.css"
LOOK_CSS = "vue-frontend/src/styles/look.css"
MAIN_JS = "vue-frontend/src/main.js"
APP_VUE = "vue-frontend/src/App.vue"
HOME_VUE = "vue-frontend/src/views/HomeView.vue"
CATEGORY_VUE = "vue-frontend/src/views/CategoryView.vue"


def _motion_block(level, css):
    m = re.search(
        r':root\[data-motion="' + level + r'"\]\s*\{([^}]*)\}', css, re.S
    )
    assert m, "缺少 :root[data-motion=\"%s\"] 参数块" % level
    return m.group(1)


def test_动效三档都有参数且强度递增():
    css = _read(GLOBAL_CSS)
    blocks = {lv: _motion_block(lv, css) for lv in ("off", "subtle", "full")}
    keys = (
        "--motion-reveal-dur", "--motion-enter-dur", "--motion-stagger",
        "--motion-reveal-y", "--motion-enter-y", "--motion-wm-shift",
    )
    for lv, body in blocks.items():
        for k in keys:
            assert k + ":" in body, "%s 档缺少 %s" % (lv, k)

    def ms(lv, key):
        m = re.search(re.escape(key) + r":\s*([0-9.]+)ms", blocks[lv])
        assert m, "%s 档 %s 不是 ms 值" % (lv, key)
        return float(m.group(1))

    def px(lv, key):
        m = re.search(re.escape(key) + r":\s*([0-9.]+)px", blocks[lv])
        assert m, "%s 档 %s 不是 px 值" % (lv, key)
        return float(m.group(1))

    for key in ("--motion-reveal-dur", "--motion-enter-dur", "--motion-stagger"):
        assert ms("subtle", key) < ms("full", key), "%s 在 full 档没有变强" % key
        assert ms("off", key) <= 1, "%s 在 off 档没有关掉" % key
    for key in ("--motion-reveal-y", "--motion-enter-y", "--motion-wm-shift"):
        assert px("subtle", key) < px("full", key), "%s 在 full 档位移没变大" % key
        assert px("off", key) == 0, "%s 在 off 档位移没归零" % key


def test_reveal_消费错峰延迟与档位时长():
    css = _read(GLOBAL_CSS)
    # global.css 里有 v3.17.0 旧 .reveal 与本轮新 .reveal 两条，靠后者覆盖。
    blocks = re.findall(r"\.reveal\s*\{([^}]*)\}", css, re.S)
    assert blocks
    body = [b for b in blocks if "--reveal-delay" in b]
    assert body, "渐入没有消费指令写入的错峰延迟"
    assert "--motion-reveal-dur" in body[-1], "渐入时长没有跟随档位"
    assert "opacity" in body[-1] and "transform" in body[-1]
    assert re.search(r"\.reveal\.revealed\s*\{[^}]*opacity:\s*1", css, re.S)


def test_reveal_指令是单例观察器且卸载解绑():
    js = _read(MAIN_JS)
    assert "let _revealIO = null" in js, "观察器不是模块级单例"
    assert "--reveal-delay" in js, "指令没有写入错峰延迟"
    assert "Math.min(idx, 7) * 55" in js, "错峰封顶规则被改掉"
    assert "unobserve" in js and "unmounted(" in js, "卸载没有解绑观察器"
    assert "prefers-reduced-motion" in js, "指令不再尊重系统减弱动效"
    assert "IntersectionObserver" in js


def test_reveal_已扩面并传序号():
    home = _read(HOME_VUE)
    cat = _read(CATEGORY_VUE)
    assert 'v-reveal="i"' in home, "首页列表卡没有传序号"
    assert 'v-for="(p, i) in items"' in home
    assert 'v-for="(c, i) in chapterCategories"' in home, "分卷卡没有错峰"
    assert 'v-reveal="i"' in cat, "分类页列表卡没有扩面"
    assert 'v-for="(p, i) in items"' in cat


def test_阅读进度条走合成层且不再写width():
    js = _read(APP_VUE)
    # 只匹配赋值语句：改动说明的注释里也会提到旧写法，不应算回归。
    assert not re.search(r"bar\.style\.width\s*=", js), \
        "进度条又退回写 width（触发 layout）"
    assert re.search(r"bar\.style\.transform\s*=", js), \
        "进度条没有改用 transform: scaleX"
    assert "scaleX(" in js
    assert "requestAnimationFrame" in js, "滚动回调没有合帧"
    assert 'classList.toggle("is-visible"' in js, "回顶按钮没有改成 class 过渡"
    css = _read(GLOBAL_CSS)
    assert re.search(r"\.reading-progress\s*\{[^}]*transform:\s*scaleX\(0\)", css, re.S)
    assert "#back-to-top.is-visible" in css


def test_off档与减弱动效都彻底静态且强制可见():
    css = _read(GLOBAL_CSS)
    # 注意：global.css 里 off 与 prefers-reduced-motion 各有多处规则（参数块、
    # v3.17.0 的全局兜底、本轮新增的兜底），re.search 只取第一处会假红。
    off_blocks = re.findall(
        r':root\[data-motion="off"\][^{]*\{([^}]*)\}', css, re.S
    )
    assert off_blocks
    assert any("animation: none" in b and "opacity: 1" in b for b in off_blocks), \
        "off 档没有把入场动画整体关掉并强制可见"
    rm_blocks = re.findall(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}", css, re.S
    )
    assert rm_blocks
    target = [b for b in rm_blocks
              if "animation: none" in b and ".home-cover [data-enter]" in b]
    assert target, "缺少本轮 reduced-motion 兜底（全局兜底只压 duration，不压 delay）"
    assert all("opacity: 1" in b for b in target)


def test_卷首阶梯入场用backwards且五个序号齐全():
    css = _read(GLOBAL_CSS)
    assert "animation: cover-enter" in css
    assert "backwards" in css, "fill-mode 必须 backwards，避免末态锁死与 LCP 回退"
    for i in range(1, 6):
        assert '[data-enter="%d"] { --enter-i: %d; }' % (i, i - 1) in css
    assert "calc(var(--motion-stagger" in css


def test_分章揭幕默认可见且只在命中后播放():
    css = _read(GLOBAL_CSS)
    assert ".zh-chapter-light.is-revealed" in css
    assert "@keyframes chapter-uncover" in css
    # 默认 .zh-chapter-light 不能被设成透明：JS 挂了也不能白屏。
    base = re.search(r"\.zh-chapter-light\s*\{([^}]*)\}", css, re.S)
    assert base and "opacity: 0" not in base.group(1)
    home = _read(HOME_VUE)
    assert "watch(lightRef" in home, "异步主题包下必须 watch template ref，不能只在 onMounted 取"
    assert 'flush: "post"' in home


def test_水印视差只在full档且被supports包裹():
    css = _read(GLOBAL_CSS)
    assert "@supports (animation-timeline: view())" in css
    m = re.search(
        r"@supports\s*\(animation-timeline:\s*view\(\)\)\s*\{(.*?)\n\}", css, re.S
    )
    assert m and 'data-motion="full"' in m.group(1)
    assert "animation-timeline: view()" in m.group(1)
    assert "@keyframes wm-drift" in css


def test_动效不污染章回语言层也不新建样式文件():
    look = _read(LOOK_CSS)
    begin = "P2 CHAPTER LANGUAGE LAYER BEGIN"
    end = "P2 CHAPTER LANGUAGE LAYER END"
    assert begin in look and end in look
    block = look.split(begin, 1)[1].split(end, 1)[0]
    assert "data-motion" not in block, "动效参数写进了章回语言层"
    assert "animation-timeline" not in block
    assert "prefers-reduced-motion" not in block, "章回层内禁 @media"
    js = _read(MAIN_JS)
    imports = re.findall(r'import\s+["\'](?:\./)?styles/([^"\']+\.css)["\']', js)
    assert imports == ["global.css", "responsive.css", "look.css"], \
        "动效不得新增 CSS 文件，main.js 三行 import 被冻结"


def test_主题包motion档位契约未变():
    py = _read("myblog/theme_bundles.py")
    assert re.search(r'MOTION_LEVELS\s*=\s*\("off",\s*"subtle",\s*"full"\)', py)
    store = _read("vue-frontend/src/store.js")
    assert 'setAttribute("data-motion"' in store
