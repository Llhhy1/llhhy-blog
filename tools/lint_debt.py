# -*- coding: utf-8 -*-
"""lint 债务棘轮（v3.20.0）：**只允许减少，不允许增加**。

## 为什么需要它

`pyproject.toml` 里的 `select` 只覆盖「高信号、当天全绿」的一小部分规则。
真正的大头不能一次修完：

| 规则 | 命中 | 为什么不当场修 |
| --- | --- | --- |
| `BLE001` | 268 | 捕获过宽，需逐个判断该记日志还是该静默 |
| `PTH` | 258 | 换 pathlib，改动面大且与运行行为无关 |
| `F401` | 168 | 未使用导入，但要区分「真没用」与「故意再导出」 |
| `UP` | 161 | pyupgrade，纯风格 |
| `I` | 107 | 导入排序，纯风格 |
| `S110` | 91 | `except ...: pass` —— 与 BLE001 同一批，需语义决策 |
| `T20` | 68 | `print(` 残留，需换成 logger（部分是真调试输出） |
| `SIM` | 36 | 化简建议，部分不适用 |
| `ARG` | 12 | 未使用参数，部分是接口占位 |

但「放着不管」就会继续长。本脚本把当前数量记成**基线**，之后任何一次提交
只要让某个计数**上升**就失败 —— 从而在不清算历史债的前提下**止住新增**。
债务下降时用 `--update` 刷新基线，等于把棘轮往前拧一格。

## 用法

    python tools/lint_debt.py            # 检查（CI 用；有新债则退出码 1）
    python tools/lint_debt.py --update   # 债务下降后刷新基线
    python tools/lint_debt.py --report   # 只打印当前计数，不做判断

## 注意

基线是**按仓库快照**固定的，所以新增规则时需先 `--update` 一次。
本脚本只依赖 `ruff`（CI 里已单独安装）。
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tools", "lint_debt_baseline.json")
TARGETS = ["myblog", "tests"]

# 只做棘轮的规则集（不含 pyproject.toml 里已阻断的那些）。
# 选原则：**只收「真债务」**——正确性 / 可观测性气味，或修改成本极低。
# 刻意**不收** `I`（导入排序）/`UP`（pyupgrade）/`PTH`（强制 pathlib）：
# 它们属个人风格偏好，`os.path.join` 本身没有错，收进棘轮只会制造无意义的历史债务。
# 注：`S110`（try-except-pass）与 `BLE001`（blind except）在**同一处会同时命中**，
# 故「合计」含重复计数 —— 它只用于趋势比较，不代表独立缺陷数。
RATCHET_RULES = ["F401", "SIM", "ARG", "T20", "S110", "BLE001"]

_LINE = re.compile(r"^(?P<file>[^:]+):\d+:\d+:\s+(?P<code>[A-Z]+\d+)\b")


def _family_matches(code, selector):
    """selector 命中 code 吗？

    ⚠️ 这里容易写错，而且**错了会静默失效**（本脚本连踩两次，故配了单元测试
    `tests/test_lint_debt.py`）：
      * 第 1 版把 `RATCHET_RULES` 当完整码去查字典 → `T20`/`SIM`/`ARG` 恒为 0，
        界面显示「零债务」而整族被漏掉，棘轮形同虚设。
      * 第 2 版用「选择器结尾是不是数字」来区分「完整码 vs 族前缀」→
        `T20` 结尾是 0，被误判成完整码，结果 T201 又漏了。

    正确判据很简单：ruff 规则码一律是「字母 + 恰好 3 位数字」
    （`F401` / `SIM117` / `T201` / `BLE001`），
    所以 `startswith` 就是准确语义 —— 完整码只会匹配到自身
    （不存在 `F4011` 这种码），族前缀则匹配整族。
    """
    return code.startswith(selector)


def _run_ruff():
    """返回 {选择器: 命中数}（另含 `_codes` 便于排查）。ruff 缺失时抛 RuntimeError。"""
    select = ",".join(RATCHET_RULES)
    cmd = [sys.executable, "-m", "ruff", "check",
           "--select", select, "--output-format", "concise"] + TARGETS
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise RuntimeError("找不到 ruff：请先 `pip install ruff`") from None
    if proc.returncode not in (0, 1):
        raise RuntimeError("ruff 执行失败（退出码 %s）：%s"
                           % (proc.returncode, (proc.stderr or "")[:400])) from None

    codes = []
    for line in proc.stdout.splitlines():
        m = _LINE.match(line.strip())
        if m:
            codes.append(m.group("code"))

    counts = {sel: sum(1 for c in codes if _family_matches(c, sel))
              for sel in RATCHET_RULES}
    counts["_codes"] = sorted(set(codes))
    return counts


def _load_baseline():
    if not os.path.exists(BASELINE):
        return None
    with open(BASELINE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_baseline(counts):
    payload = {
        "_comment": "lint 债务基线（由 tools/lint_debt.py --update 生成）。"
                    "计数只允许下降；新增规则请先 --update。"
                    "S110 与 BLE001 在同一处会同时命中，合计含重复计数。",
        "rules": RATCHET_RULES,
        "targets": TARGETS,
        "counts": {k: v for k, v in sorted(counts.items()) if not k.startswith("_")},
    }
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    print("已写入基线：%s" % os.path.relpath(BASELINE, ROOT))


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    try:
        counts = _run_ruff()
    except RuntimeError as e:
        print("跳过：%s" % e)
        return 0

    # `_codes` 是排查用的原始码清单，不参与计数与基线
    actual = {k: v for k, v in counts.items() if not k.startswith("_")}
    total = sum(actual.values())
    print("=== lint 债务现状（棘轮规则集）===")
    for code in RATCHET_RULES:
        print("  %-8s %6d" % (code, actual.get(code, 0)))
    print("  %-8s %6d" % ("合计", total))
    if "--report" in argv:
        print("  实际命中码: %s" % ", ".join(counts.get("_codes") or []))
    print()

    if "--update" in argv:
        _write_baseline(actual)
        return 0

    if "--report" in argv:
        return 0

    base = _load_baseline()
    if base is None:
        print("没有基线文件 → 以当前状态建立基线（首次运行）")
        _write_baseline(actual)
        return 0

    base_counts = {k: v for k, v in base.get("counts", {}).items()
                   if not k.startswith("_")}
    grew, shrank = [], []
    for code in sorted(set(list(actual) + list(base_counts))):
        now, was = actual.get(code, 0), base_counts.get(code, 0)
        if now > was:
            grew.append((code, was, now))
        elif now < was:
            shrank.append((code, was, now))

    if shrank:
        print("债务下降（可考虑 `--update` 把棘轮往前拧一格）：")
        for code, was, now in shrank:
            print("  %-8s %6d → %6d  (-%d)" % (code, was, now, was - now))
        print()

    if grew:
        print("❌ 出现**新增** lint 债务（棘轮门禁不允许）：")
        for code, was, now in grew:
            print("  %-8s %6d → %6d  (+%d)" % (code, was, now, now - was))
        print()
        print("处置：要么把这几处改掉，要么按实际情况调整 pyproject.toml 的规则集。")
        print("（**不要**为了过门禁而直接 --update 把基线抬上去 —— 那就失去了棘轮的意义。）")
        return 1

    print("✅ 无新增 lint 债务（合计 %d，基线 %d）。"
          % (total, sum(base_counts.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
