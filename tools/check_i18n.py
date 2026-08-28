#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
i18n key 完整性检查（防「导航栏文档不切英文」类回归）。

问题背景：今天 v3.8.9 修复的 bug —— 导航栏「文档」两项硬编码中文，且 store.js 的
I18N 词典缺 docs key，导致切英文不变。本质是「模板用了 t('x')，但词典没这个 key」。

本脚本在发布前 / CI 跑一遍：
  - 扫描 vue-frontend/src 下所有 .vue / .js，提取所有 t('key') / t("key") 调用
  - 解析 store.js 的 I18N.zh / I18N.en 词典 key 集合
  - 发现「用了但词典没有」或「zh/en 不一致」→ 打印并报错（退出码 1，CI 失败）
  - 「词典有但没用到」仅警告（可能是动态使用，不致命）

用法（仓库根目录执行）：
  python tools/check_i18n.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "vue-frontend", "src")
STORE = os.path.join(SRC, "store.js")


def parse_dict(block):
    """从某个语言块文本里提取所有 "key": 形式的 key。"""
    return set(re.findall(r'["\']([^"\']+)["\']\s*:', block))


def main():
    if not os.path.isfile(STORE):
        print("❌ 找不到", STORE)
        sys.exit(1)

    with open(STORE, encoding="utf-8") as f:
        txt = f.read()

    # 提取 zh / en 语言块（到第一个 `},` 结束）
    zh_block = re.search(r'zh:\s*\{(.*?)\n\s*\},', txt, re.S)
    en_block = re.search(r'en:\s*\{(.*?)\n\s*\},', txt, re.S)
    zh_keys = parse_dict(zh_block.group(1)) if zh_block else set()
    en_keys = parse_dict(en_block.group(1)) if en_block else set()

    # 扫描所有源文件里的 t('key') / t("key")
    used = set()
    hit_files = {}
    for dirpath, _, files in os.walk(SRC):
        for fn in files:
            if not fn.endswith((".vue", ".js")):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            # (?<![\w$]) 排除 setTimeout/apiGet/import(/createElement/$t/mount 等以 t( 结尾的调用，
            # 只匹配从 store.js 导入的独立 t('key') 调用
            for m in re.findall(r"""(?<![\w$])t\(\s*['"]([^'"]+)['"]\s*\)""", content):
                used.add(m)
                hit_files.setdefault(m, set()).add(os.path.relpath(p, ROOT))

    errors = []
    missing_zh = sorted(used - zh_keys)
    missing_en = sorted(used - en_keys)
    if missing_zh:
        errors.append("缺失 zh 翻译（模板用了但 I18N.zh 没有）: " + ", ".join(missing_zh))
    if missing_en:
        errors.append("缺失 en 翻译（模板用了但 I18N.en 没有）: " + ", ".join(missing_en))
    if zh_keys != en_keys:
        only_zh = sorted(zh_keys - en_keys)
        only_en = sorted(en_keys - zh_keys)
        if only_zh:
            errors.append("仅 zh 有而 en 缺: " + ", ".join(only_zh))
        if only_en:
            errors.append("仅 en 有而 zh 缺: " + ", ".join(only_en))

    # 词典有但没被 t() 使用 → 仅警告
    unused = sorted((zh_keys | en_keys) - used)
    if unused:
        print("⚠️ 词典定义了但未在任何 t() 中使用的 key（可能为动态使用，仅供参考）: "
              + ", ".join(unused))

    if errors:
        print("❌ i18n 检查失败：")
        for e in errors:
            print("  - " + e)
        print("\n修复方法：在 store.js 的 I18N.zh / I18N.en 中补上对应 key，"
              "模板用 {{ t('key') }} 引用。")
        sys.exit(1)

    print("✅ i18n 检查通过：模板实际使用 %d 个 key，zh/en 词典齐全，无缺失。"
          % len(used))
    print("   涉及文件: " + ", ".join(sorted(set().union(*hit_files.values()))))


if __name__ == "__main__":
    main()
