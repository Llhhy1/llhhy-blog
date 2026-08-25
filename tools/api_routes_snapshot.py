#!/usr/bin/env python
"""API 路由快照：dump 当前应用全部 /api/* 路由（rule + methods + endpoint）。

用法：
    python tools/api_routes_snapshot.py [outfile]
不传 outfile 则打印到 stdout；传则写入文件（路由行排序后输出）供 diff 对比。

用途：API 解耦重构（api.py -> api/ 包）前后各跑一次，对比快照保证零破坏。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "myblog"))

# 需要最小配置：SECRET_KEY / ADMIN_PASSWORD 缺一不可（app.py 启动校验）
os.environ.setdefault("SECRET_KEY", "snapshot-secret-key-for-route-dump-only")
os.environ.setdefault("ADMIN_PASSWORD", "snapshot-admin-password-for-route-dump-only")
# 关掉可选增强，避免依赖（PIL / 邮件等一律不需要，只做路由枚举）
os.environ.setdefault("CAPTCHA_ENABLED", "false")
os.environ.setdefault("BLOG_OPEN_REGISTER", "true")

from app import create_app

app = create_app()

rows = []
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if not rule.rule.startswith("/api/"):
        continue
    methods = ",".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS")))
    rows.append(f"{rule.rule} [{methods}] -> {rule.endpoint}")

out = "\n".join(rows) + "\n"
if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(out)
    print(f"已写入 {sys.argv[1]}（{len(rows)} 条路由）")
else:
    sys.stdout.write(out)