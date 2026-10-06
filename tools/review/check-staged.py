#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 提交门禁检查脚本（pre-commit 钩子核心）。

检查内容：
  1. 黑名单文件误入暂存区（data/、*.zip、*.db、__pycache__、临时 smoke 产物等）
  2. Python 改动文件语法检查（py_compile）
  3. 前端源码改动但未包含构建产物 → 警告（改 src 必须重新 vite build）
  4. 后端代码改动但四份文档未同步 → 警告（项目铁律：代码新文档旧不允许）

行为：
  - 硬错误（黑名单/语法失败）→ 非零退出，拦截提交
  - 软警告（文档/构建）→ 打印警告并继续（不卡死单飞开发者）
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 黑名单：路径片段命中即拦截
BLOCKLIST_SUBSTR = (
    "/data/", "\\data\\", "data/blog.db", "__pycache__/", "__pycache__\\",
    ".pyc", ".zip", ".db", ".sqlite",
    "node_modules/", "node_modules\\",
    "venv/", "venv\\", ".venv/",
    ".env",
    "deploy_scripts_", "sha256.txt",
)
# 临时冒烟/调试文件（可改名后提交，默认拦截）
# 注意：项目惯例是 smoke_*.py 纳入仓库正常提交（已有 smoke_v28/v300/gbk 等），
# 因此这里只拦截「临时调试」形态的文件，勿把正式 smoke 脚本加进来。
BLOCKLIST_EXACT = (
)

# 文档同步检查：后端代码改动时，这些文档必须同时有改动
# ⚠️ **只放「活的」主文档，不放 docs/archive/ 下的归档件**（v3.25.1 更正）：
#    v3.25.0 归档时曾把归档件一并纳入必改清单 —— 结果每次发版都被迫「虚假地」
#    改一下归档件才能过门禁。但归档件是**历史快照**（R1~R80 / v3.18.5 及更早），
#    内容本就不该随新版本变化；真要在归档里补交叉引用时自然会把它们放进提交，
#    不需要门禁逼。实测 v3.25.1 发版时该警告对两份归档件误报。
# ⚠️ 归档时踩过：`git checkout <file>` 会连带revert 掉该文件**未提交**的改动
#    （当时把 v3.25.0 的 CHANGELOG 段一起revert 了，只能重写）。回滚长文档
#    务必先 `git stash` 或按 hunk 回退，不要整文件 checkout。
DOCS = ("README.md", "myblog/README.md", "myblog/deploy_guide.md", "ROADMAP.md",
        "myblog/SECURITY_AUDIT.md")
BACKEND_SRC = "myblog/"
FRONTEND_SRC = "vue-frontend/src/"

# README 版本史门禁（v3.25.13）：版本史的唯一真相源是 CHANGELOG.md。
# README 一度被逐版追加的版本说明堆到 137 行，与 CHANGELOG 重复且必然漂移。
# 判据：README 里只允许「当前版本号」这一行，不允许任何 `## vX.Y.Z` / `- **vX.Y.Z：…**` 形态。
README_FILES = ("README.md", "myblog/README.md")
_VER_HISTORY_RE = re.compile(r"^\s*(?:[-*]\s*\*\*|#{1,6}\s*)v\d+\.\d+\.\d+")


def staged_files():
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT, text=True, errors="replace")
    return [l for l in out.splitlines() if l.strip()]


def py_compile(files):
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return True
    # 逐个 py_compile，失败即返回 False（信息给到具体文件）
    ok = True
    python = sys.executable
    for f in py_files:
        r = subprocess.run([python, "-m", "py_compile", os.path.join(ROOT, f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            ok = False
            print(f"  ✗ 语法错误: {f}\n{r.stderr[-500:]}")
    return ok


def main():
    files = staged_files()
    errors = []
    warnings = []

    # 1. 黑名单
    for f in files:
        nf = f.replace("\\", "/")
        for blk in BLOCKLIST_SUBSTR:
            if blk.lower() in nf.lower():
                errors.append(f"黑名单文件误入暂存区: {f}（命中 {blk}）")
                break
        if nf in BLOCKLIST_EXACT:
            errors.append(f"临时调试文件不应提交: {f}")

    # 2. Python 语法
    if not py_compile(files):
        errors.append("Python 语法检查失败")

    # 3. 前端源码变更 → 构建产物未同步
    front_changed = any(f.startswith(FRONTEND_SRC) for f in files)
    dist_changed = any("dist" in f or "_vite_build" in f for f in files)
    if front_changed and not dist_changed:
        warnings.append(
            "前端源码已改动，但本次提交不含构建产物（dist/_vite_build*）——"
            "若未重新 vite build，线上不会生效。请确认是否已构建。"
        )

    # 4. 后端代码变更 → 文档未同步
    backend_changed = any(f.startswith(BACKEND_SRC) and f.endswith(".py")
                          for f in files)
    if backend_changed:
        missing = [d for d in DOCS if d not in files]
        if missing:
            warnings.append(
                "后端代码已改动，但以下文档未在本提交同步（项目铁律）：\n"
                + "\n".join(f"    - {d}" for d in missing)
            )

    # 5. lint 棘轮（v3.25.9 接进发版路径）
    #
    # **为什么必须接进来**：棘轮原本只是 CI 的一个 job，而 CI 在发版之外 ——
    # 于是 v3.25.0~v3.25.6 期间新增的 SIM +21 / BLE001 +9 / S110 +4 一直攒着，
    # 连续六个版本没人看见，直到 v3.25.7 手动跑 `tools/lint_debt.py` 才发现。
    # **门禁不在发版路径上 = 等于没有门禁。**
    #
    # 只在后端源码变更时跑（改文档/前端不会影响 Python lint 计数）。
    if backend_changed:
        lint = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "lint_debt.py")],
                              cwd=ROOT, capture_output=True, text=True)
        if lint.returncode != 0:
            out = (lint.stdout or "") + (lint.stderr or "")
            errors.append(
                "lint 棘轮未通过（新增 lint 债务）：\n"
                + "\n".join("    " + l for l in out.strip().splitlines()[-12:])
            )

    # 6. README 版本史门禁 + 版本升级必须带 CHANGELOG（v3.25.13）
    #
    # **为什么做成硬拦截**：技能里写了规则、人还是会忘（「门禁不在发版路径上 = 等于
    # 没有门禁」，同一条已在 lint 棘轮上验证过一次）。README 只允许出现「当前版本号」
    # 这一行，其余「vX.Y.Z 做了什么」一律归 CHANGELOG。
    for f in README_FILES:
        if f not in files:
            continue
        blob = subprocess.run(["git", "show", f":{f}"], cwd=ROOT,
                              capture_output=True, text=True)
        for i, line in enumerate((blob.stdout or "").splitlines(), 1):
            if _VER_HISTORY_RE.match(line):
                errors.append(
                    f"{f}:{i} 出现版本史条目「{line.strip()[:48]}」——"
                    "版本史唯一真相源是 CHANGELOG.md，README 只留「当前版本」一行"
                )

    # 版本号变了 → CHANGELOG.md 必须同批提交（否则版本更新信息没进更新文档）
    if "myblog/config.py" in files:
        def _ver(spec):
            """spec = `HEAD`（上一版）或 `""`（暂存区，`:path` 即 stage 0）。

            ⚠️ 别在调用侧再拼一次 `:myblog/config.py` —— 那样会得到
            `:myblog/config.py:myblog/config.py`，git 静默失败、`_ver` 返回 None，
            整条守卫**假绿**（变异测试当场抓出）。
            """
            r = subprocess.run(["git", "show", f"{spec}:myblog/config.py"], cwd=ROOT,
                               capture_output=True, text=True)
            m = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)", r.stdout or "")
            return m.group(1) if m else None
        old_v, new_v = _ver("HEAD"), _ver("")
        if new_v and old_v and new_v != old_v:
            if "CHANGELOG.md" not in files:
                errors.append(
                    f"版本号 {old_v} → {new_v}，但 CHANGELOG.md 未同批提交——"
                    "版本更新信息必须统一并入更新文档"
                )
            for f in README_FILES:
                if f not in files:
                    continue
                blob = subprocess.run(["git", "show", f":{f}"], cwd=ROOT,
                                      capture_output=True, text=True)
                if new_v not in (blob.stdout or ""):
                    errors.append(f"{f} 未更新到当前版本号 {new_v}")

    # 输出
    for e in errors:
        print(f"[ERROR] {e}")
    for w in warnings:
        print(f"[WARN ] {w}")

    if errors:
        print("\n✗ L3 门禁拦截：存在硬错误，请修复后重新提交。")
        return 1
    if warnings:
        print("\n△ 提交已放行，但存在软警告，请确认后处理。")
    else:
        print("\n✓ L3 门禁通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())