# -*- coding: utf-8 -*-
"""v5.6.0 后台组件化一期的静态守卫（纯文件断言，不 import app、不连数据库）。

只扫描模板源码文本，钉住「组件化只许收敛、不许回退」四件事：
1. ``_components.html`` 存在、宏数量达标，且不夹带脚本 / 转义短路 / 写死颜色；
2. 后台模板内联 ``<style`` 标签总数只许减不许增（棘轮）；
3. 组件化确实落地：被改的高频模板真的 import 了宏文件；
4. 与主题市场卡片守卫同口径：所有 admin 模板 ``setProperty`` 总数为 0。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN_DIR = ROOT / "myblog" / "templates" / "admin"
COMPONENTS = ADMIN_DIR / "_components.html"

# 本次实际替换过的高频模板
CHANGED_TEMPLATES = ("dashboard.html", "stats.html", "my_posts.html")

# 内联 <style 标签基线：v5.6.0 实测 54 个 admin 模板共 14 个 <style 开标签。
# 棘轮语义「只允许减少」：新样式请进 admin.css / tokens.css，不许再加内联块。
# 主动收敛了内联样式时同步调低本常量，绝不要调高。
INLINE_STYLE_BASELINE = 14

_MACRO_RE = re.compile(r"\{%\s*macro\s+(\w+)")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_IMPORT_FRAG = '{% from "admin/_components.html" import'


def _admin_html_files():
    return sorted(ADMIN_DIR.glob("*.html"))


def test_components_file_exists_and_defines_macros():
    """宏组件文件必须存在，且提供至少 4 个可复用 macro。"""
    assert COMPONENTS.is_file(), "_components.html 不存在"
    macros = _MACRO_RE.findall(COMPONENTS.read_text(encoding="utf-8"))
    assert len(macros) >= 4, "宏数量不足 4 个，实际 %d：%s" % (len(macros), macros)


def test_components_file_has_no_forbidden_tokens():
    """宏只输出已有 CSS 类与语义标签，不得夹带脚本 / |safe / 写死颜色 / setProperty。"""
    src = COMPONENTS.read_text(encoding="utf-8")
    low = src.lower()
    assert "setproperty" not in low, "宏文件不得出现 setProperty（主题上色守卫逐行扫描口径）"
    assert "<script" not in low, "宏文件不得输出脚本标签"
    assert "|safe" not in src, "宏参数一律自动转义，不得用 |safe 绕过"
    assert not _HEX_RE.search(src), "宏文件不得写死 hex 颜色"


def test_inline_style_ratchet_not_growing():
    """后台模板内联 <style 总数不得高于基线（只允许减少）。"""
    total = sum(p.read_text(encoding="utf-8").count("<style") for p in _admin_html_files())
    assert total <= INLINE_STYLE_BASELINE, (
        "内联 <style 从基线 %d 涨到 %d —— 新样式请进 admin.css，不要再加内联块"
        % (INLINE_STYLE_BASELINE, total)
    )


def test_changed_templates_import_components():
    """被组件化的高频模板必须真的 import 了宏文件。"""
    for name in CHANGED_TEMPLATES:
        src = (ADMIN_DIR / name).read_text(encoding="utf-8")
        assert _IMPORT_FRAG in src, "%s 没有 import _components.html —— 组件化未落地" % name


def test_no_setproperty_in_any_admin_template():
    """所有 admin 模板 setProperty 总次数为 0（与主题市场卡片守卫同口径）。"""
    total = sum(p.read_text(encoding="utf-8").count("setProperty") for p in _admin_html_files())
    assert total == 0, "admin 模板出现 %d 处 setProperty —— 主题卡片上色不许改成 CSS 变量注入" % total
