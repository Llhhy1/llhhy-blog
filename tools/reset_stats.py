#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reset_stats.py — 清空 llhhy-blog 网站统计数据并重新统计（维护脚本）

仅清除统计相关表，不动文章/评论/用户等业务数据：
  - visit_log   访问流水（看板：趋势/区域排行/时段分布）
  - read_log    文章阅读记录（反复阅读统计）
  - search_log  搜索词（常搜词排行）
  - ip_region   IP 属地缓存（顺带清掉历史 GBK 乱码缓存）
  - post.views  文章阅读量归零

特点：
  - 纯标准库（sqlite3），丢服务器上用系统 Python 即可运行，无需 Flask/venv
  - 执行前自动备份 blog.db 到带时间戳的 .stats_bak_xxx 文件
  - 默认交互二次确认；--yes 可跳过（自动化用）
  - 自动探测常见生产路径 /www/wwwroot/*/data/blog.db，也可用 --db 指定

用法：
  python tools/reset_stats.py                 # 自动探测 + 交互确认
  python tools/reset_stats.py --yes            # 跳过确认（脚本化用）
  python tools/reset_stats.py --db /path/blog.db
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# 仅统计表（硬编码常量，非用户输入，无注入风险）
STATS_TABLES = ("visit_log", "read_log", "search_log", "ip_region")


def find_db():
    """按常见生产路径 + 相对路径探测 blog.db"""
    candidates = []
    base = "/www/wwwroot"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name, "data", "blog.db")
            if os.path.isfile(p):
                candidates.append(p)
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("../data/blog.db", "data/blog.db", "blog.db"):
        p = os.path.normpath(os.path.join(here, rel))
        if os.path.isfile(p):
            candidates.append(p)
    # 去重保序
    seen, uniq = set(), []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def main():
    ap = argparse.ArgumentParser(description="清空 llhhy-blog 统计数据并重新统计")
    ap.add_argument("--db", help="blog.db 路径（不指定则自动探测）")
    ap.add_argument("--yes", action="store_true", help="跳过交互确认")
    args = ap.parse_args()

    if args.db:
        db_path = args.db
    else:
        found = find_db()
        if not found:
            print("未自动找到 blog.db，请用 --db 指定路径（如 --db /www/wwwroot/xxx/data/blog.db）")
            sys.exit(1)
        if len(found) > 1:
            print("发现多个 blog.db，请用 --db 指定其一：")
            for p in found:
                print("   ", p)
            sys.exit(1)
        db_path = found[0]

    if not os.path.isfile(db_path):
        print("数据库文件不存在:", db_path)
        sys.exit(1)

    # 预检表结构，避免误伤非本项目的库
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    con.close()
    if "post" not in tables:
        print("未找到 post 表，可能不是 llhhy-blog 数据库，已中止以防误删")
        sys.exit(1)
    missing = [t for t in STATS_TABLES if t not in tables]

    print("目标数据库:", db_path)
    print("将清除:", ", ".join(t for t in STATS_TABLES if t in tables), "+ post.views 归零")
    if missing:
        print("（以下表不存在，自动跳过: %s）" % ", ".join(missing))

    if not args.yes:
        ans = input("确认清空以上统计数据？(输入 YES 继续): ").strip()
        if ans != "YES":
            print("已取消，未做任何修改")
            sys.exit(0)

    # 备份（带时间戳，避免覆盖上一次备份）
    bak = db_path + ".stats_bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(db_path, bak)
    print("已备份至:", bak)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    for t in STATS_TABLES:
        if t in tables:
            cur.execute("DELETE FROM %s" % t)
            print("  DELETE %s: %d 行" % (t, cur.rowcount))
    cur.execute("UPDATE post SET views = 0")
    print("  UPDATE post.views -> 0（%d 篇）" % cur.rowcount)
    con.commit()
    con.close()

    print("完成。统计已重置：新访客进来会重新累计；文章页阅读量从 0 起算。")


if __name__ == "__main__":
    main()
