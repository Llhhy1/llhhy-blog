#!/usr/bin/env python
"""全量重建 FTS 索引：清空 post_fts 后只写入「访客可见」的文章。

用法：
    python tools/rebuild_fts.py

为什么需要这个脚本（v3.21.2 审计）：
`fts.ensure()` 只在 `post_fts` 为空时回填，而 v3.21.2 之前的索引闸门是
「published 就进索引」——隐私文章的**正文全文**因此躺在历史库的索引里。
只改写入闸门不会让已存在的脏行消失，必须显式重建一次。

升级后（或怀疑索引不一致时）在服务器上跑一次即可；跑完不影响正在提供的服务。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "myblog"))

os.environ.setdefault("SECRET_KEY", "rebuild-fts-secret-key-only")
os.environ.setdefault("ADMIN_PASSWORD", "rebuild-fts-admin-password-only")
os.environ.setdefault("CAPTCHA_ENABLED", "false")
os.environ.setdefault("BLOG_OPEN_REGISTER", "true")

from app import create_app  # noqa: E402

app = create_app()

with app.app_context():
    import fts

    if not fts.available():
        print("[FTS] 当前 SQLite 不支持 FTS5，跳过（搜索自动走 LIKE 回退，无脏行风险）")
        sys.exit(0)
    res = fts.rebuild_all()
    print("[FTS] 重建结果:", res)
    if not res.get("ok"):
        sys.exit(1)
