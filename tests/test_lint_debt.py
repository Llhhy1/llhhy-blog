# -*- coding: utf-8 -*-
"""tools/lint_debt.py 的单元测试（v3.20.0）。

为什么要为一个「小工具」写测试：它的核心匹配逻辑**连错两次，而且两次都是静默失效**——
界面照常打印、退出码照常为 0，只是把整族规则漏掉，棘轮门禁形同虚设。
这种「不报错的错」只能靠断言钉住。

背景（两次踩坑）：
  1. 第 1 版把选择器（`T20`/`SIM`/`ARG`）当**完整码**去查字典 →
     恒为 0，T201/SIM117/ARG002 全部漏计。
  2. 第 2 版用「结尾是不是数字」区分「完整码 vs 族前缀」→
     `T20` 结尾是 0，被误判成完整码，`T201` 又漏了。

正确判据：ruff 规则码是「字母 + 恰好 3 位数字」，故 `startswith` 即准确语义。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tools"))

import lint_debt  # noqa: E402


def test_full_code_matches_only_itself():
    """完整码选择器只能命中它自己（不存在 F4011 这类码）。"""
    assert lint_debt._family_matches("F401", "F401") is True
    assert lint_debt._family_matches("F402", "F401") is False
    assert lint_debt._family_matches("S110", "S110") is True
    assert lint_debt._family_matches("S101", "S110") is False
    assert lint_debt._family_matches("BLE001", "BLE001") is True


def test_group_prefix_ending_with_digit():
    """**回归**：以数字结尾的族前缀（`T20`）必须匹配整族 —— 这是踩过的坑。"""
    assert lint_debt._family_matches("T201", "T20") is True, \
        "T20 是族前缀（T201/T203），不能因结尾是数字就被当成完整码"
    assert lint_debt._family_matches("T203", "T20") is True
    assert lint_debt._family_matches("T201", "T2") is True
    assert lint_debt._family_matches("T201", "T3") is False


def test_letter_only_prefix_matches_family():
    """纯字母族前缀匹配整族。"""
    assert lint_debt._family_matches("SIM117", "SIM") is True
    assert lint_debt._family_matches("ARG002", "ARG") is True
    assert lint_debt._family_matches("SIM117", "ARG") is False


def test_ratchet_rules_all_resolve_against_real_codes():
    """棘轮规则集里每个选择器都必须能命中代码库中真实存在的码。

    这条是**防漏计的上限断言**：若哪天有人把选择器写错（例如 `T02`），
    它永远匹配不到任何码、计数恒为 0 —— 本测试会在核心里立刻发现：
    只要该选择器对应的族确实有违规，`_family_matches` 就必须为真。
    """
    # (选择器, 该族真实存在的样例码) —— 样例取自本仓库实测命中码
    samples = {
        "F401": "F401",
        "SIM": "SIM117",
        "ARG": "ARG002",
        "T20": "T201",
        "S110": "S110",
        "BLE001": "BLE001",
    }
    assert set(samples) == set(lint_debt.RATCHET_RULES), \
        "新增/改名棘轮规则时，请同步本测试的观测样例"
    for sel, code in samples.items():
        assert lint_debt._family_matches(code, sel) is True, \
            "选择器 %s 匹配不到真实码 %s（会静默漏计）" % (sel, code)


def test_baseline_file_is_wellformed():
    """基线文件必须存在且格式正确（否则棘轮会静默地永远放行）。"""
    import json
    path = lint_debt.BASELINE
    assert os.path.exists(path), "缺少基线文件：%s" % path
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    counts = data.get("counts", {})
    assert counts, "基线 counts 不能为空"
    for sel in lint_debt.RATCHET_RULES:
        assert sel in counts, "基线缺少选择器 %s（新增规则后请跑 --update）" % sel
        assert isinstance(counts[sel], int) and counts[sel] >= 0


def test_internal_codes_key_not_persisted():
    """`_codes` 只是排查用的原始码清单，不得进入基线（否则会被当成债务计数）。"""
    import json
    with open(lint_debt.BASELINE, "r", encoding="utf-8") as f:
        counts = json.load(f).get("counts", {})
    assert "_codes" not in counts, "`_codes` 不应写入基线"
