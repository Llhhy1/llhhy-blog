"""v4.9.0 分享卡片模板库（ROADMAP §3.1）。

最值得守的一条是**缓存 key 必须含模板名**：classic 与 wechat_square 的
默认主色**故意相同**、只有尺寸不同，若 key 只按 accent 算，换模板会命中
旧缓存吐回横图 —— 表现为「明明选了微信方图，分享出去还是被裁」，而缓存
命中时**没有任何日志**，这类 bug 几乎不可能靠排查发现。

其余几条守的是「配置写错不能把页面搞挂」：模板名来自后台设置，可能被
手工改成无效值，必须静默退回默认而不是抛异常。
"""

import pytest

import og_image as og


def test_未知模板退回默认():
    t = og.resolve_template("nonexistent-template")
    assert t is og.TEMPLATES[og.DEFAULT_TEMPLATE]


@pytest.mark.parametrize("bad", ["", None, "   "])
def test_空值也退回默认(bad):
    assert og.resolve_template(bad) is og.TEMPLATES[og.DEFAULT_TEMPLATE]


def test_list_templates_默认排最前且含微信方图():
    keys = [k for k, _ in og.list_templates()]
    assert keys[0] == og.DEFAULT_TEMPLATE
    assert "wechat_square" in keys


def test_微信模板必须是正方形():
    """微信会把 og:image 裁成正方形，方图模板非正方就白做了。"""
    t = og.resolve_template("wechat_square")
    assert t["w"] == t["h"], (t["w"], t["h"])


def test_换模板缓存key必须不同():
    """主色相同、仅模板不同 → key 必须变。这是本文件最重要的一条。"""
    # 前提确认：两者默认主色确实相同（否则这条测试就失去意义）
    assert og.TEMPLATES["classic"]["accent"] == og.TEMPLATES["wechat_square"]["accent"]
    k1 = og._cache_key("some-post", "stamp", "#1a73e8", "classic")
    k2 = og._cache_key("some-post", "stamp", "#1a73e8", "wechat_square")
    assert k1 != k2, "换模板却命中同一缓存 → 会吐回旧尺寸的图"


def test_默认模板沿用历史主色():
    """classic 的默认色必须是 #1a73e8：升级前后默认表现要一致。"""
    assert og.TEMPLATES[og.DEFAULT_TEMPLATE]["accent"] == "#1a73e8"


@pytest.mark.skipif(not og._PIL_OK, reason="Pillow 不可用")
def test_方图模板确实渲染出正方形():
    img = og.render_og_image(title="模板探针", template="wechat_square", accent="#1a73e8")
    if img is None:
        pytest.skip("无可用中文字体，分享卡降级")
    assert img.size == (800, 800), img.size
