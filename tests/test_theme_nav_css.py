# -*- coding: utf-8 -*-
"""v3.17.1 回归：导航 CSS 注入的选择器必须保持"可用"，不得被 Jinja autoescape 转义。

背景（线上实测）：
v3.17.0 用 ``html:not([data-theme="dark"])`` 注入导航配色，Jinja autoescape 会把
双引号转成 ``&#34;``，渲染结果为 ``html:not([data-theme=&#34;dark&#34;])``——CSS 里
这不是合法选择器，整条规则失效，导致「后台/SSR 深色模式顶部白条」的修复实际不生效。
本测试把该行为锁死，防止再次踩坑。
"""


def test_nav_css_selector_is_not_escaped(client):
    """后台 SSR 页必须输出可用的无引号属性选择器，且不含转义痕迹。"""
    r = client.get("/admin/login", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "html:not([data-theme=dark])" in html, "导航 CSS 选择器缺失（修复未注入）"
    assert "data-theme=&#34;dark&#34;" not in html, "选择器被转义，CSS 将失效"


def test_theme_css_still_injected(client):
    """顺带确认同一次注入里的圆角/字号变量仍在（theme_css 未被误删）。"""
    r = client.get("/admin/login", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "--theme-radius:" in html
    assert "--theme-font-size:" in html
