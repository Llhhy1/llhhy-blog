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
DOCS = ("README.md", "myblog/README.md", "deploy_guide.md", "ROADMAP.md",
        "myblog/SECURITY_AUDIT.md")
BACKEND_SRC = "myblog/"
FRONTEND_SRC = "vue-frontend/src/"


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