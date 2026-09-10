"""v3.17.3 数据库迁移：为 visit_log 表新增 referrer 字段（来源分析）。

背景：
- 项目用 SQLite（blog.db）。create_all 只建「不存在的表」，不会给已存在的表加列，
  所以升级到 v3.17.3 必须手动迁移（与 v3.7.1 的 bot 字段迁移同模式）。
- 本脚本幂等：先用 PRAGMA table_info 检查列是否存在，已存在则跳过，可重复运行。
- 新增列：referrer(VARCHAR300 DEFAULT '')——只存 origin（协议+域名），
  完整 referrer 里的 query 可能含 token/隐私参数，不入库。

运行方式（二选一）：
  1) 环境变量指定 db 路径（推荐，宝塔部署时用真实路径）：
       BLOG_DB=/www/wwwroot/你的站点/data/blog.db python myblog/migrate_visit_log_referrer.py
  2) 自动查找（../data/blog.db、./data/blog.db、当前目录/data/blog.db）：
       cd <项目根>
       python myblog/migrate_visit_log_referrer.py
"""
import os
import sqlite3
import sys
from os.path import abspath, dirname, exists, join, getcwd

sys.path.insert(0, dirname(dirname(abspath(__file__))))


def find_db():
    env = os.environ.get("BLOG_DB")
    if env and exists(env):
        return abspath(env)
    here = dirname(abspath(__file__))
    for cand in (
        join(here, "..", "data", "blog.db"),
        join(here, "data", "blog.db"),
        join(getcwd(), "data", "blog.db"),
    ):
        if exists(cand):
            return abspath(cand)
    return None


def migrate(db_path):
    cols = {
        "referrer": "VARCHAR(300) DEFAULT ''",
    }
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(visit_log)").fetchall()}
    for col, ddl in cols.items():
        if col in existing:
            print(f"  skip {col} (already exists)")
            continue
        cur.execute(f"ALTER TABLE visit_log ADD COLUMN {col} {ddl}")
        print(f"  added {col}")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    db_path = find_db()
    if not db_path:
        print("未找到 blog.db：请用环境变量 BLOG_DB 指定，或在该库所在目录运行。脚本结束。")
        sys.exit(1)
    print(f"migrating: {db_path}")
    migrate(db_path)
    print("done.")
