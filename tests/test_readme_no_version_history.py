"""README 极简守卫：版本史的唯一真相源是 CHANGELOG.md（v3.25.13）。

**为什么要有这个测试**：`tools/review/check-staged.py` 只在提交时跑（不提交就没人管），
而 pytest 是 CI 与本地都会跑的。README 曾被逐版追加版本说明堆到 137 行 —— 与 CHANGELOG
**重复且必然漂移**，用户直接指出要「极致的简化」。

三条断言：
  1. 两份 README 里不得出现版本史条目（`## vX.Y.Z` / `- **vX.Y.Z：…**` 形态）；
  2. 两份 README 必须写出**当前版本号**（否则门面与代码不一致）；
  3. 「当前版本」那行的版本号必须与 `config.APP_VERSION` 一致（防改了代码忘了改门面）。
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_FILES = ("README.md", "myblog/README.md")

# `- **v3.25.12：…**` / `## v3.25.12（…）` / `### v3.24.0` 都算版本史条目
VERSION_HISTORY_RE = re.compile(r"^\s*(?:[-*]\s*\*\*|#{1,6}\s*)v\d+\.\d+\.\d+")
CURRENT_VERSION_RE = re.compile(r"当前版本[^\d]*(\d+\.\d+\.\d+)")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("rel", README_FILES)
def test_readme_has_no_version_history(rel):
    """版本史一律归 CHANGELOG.md —— README 只留「当前版本」一行。"""
    bad = [(i, ln.strip()[:60]) for i, ln in enumerate(_read(rel).splitlines(), 1)
           if VERSION_HISTORY_RE.match(ln)]
    assert not bad, "%s 出现版本史条目（应移入 CHANGELOG.md）：%s" % (rel, bad)


@pytest.mark.parametrize("rel", README_FILES)
def test_readme_version_matches_config(rel):
    """README 写的当前版本必须与 config.APP_VERSION 一致。"""
    sys_path = os.path.join(ROOT, "myblog")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from config import APP_VERSION
    m = CURRENT_VERSION_RE.search(_read(rel))
    assert m, "%s 找不到「当前版本」行" % rel
    assert m.group(1) == APP_VERSION, (
        "%s 写的版本 %s 与 config.APP_VERSION %s 不一致" % (rel, m.group(1), APP_VERSION))


def test_changelog_has_current_version():
    """反过来也要成立：CHANGELOG 里有当前版本那一节。"""
    sys_path = os.path.join(ROOT, "myblog")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from config import APP_VERSION
    top = _read("CHANGELOG.md")[:4000]
    assert "## v%s" % APP_VERSION in top, (
        "CHANGELOG.md 顶部缺少 v%s 的条目" % APP_VERSION)
