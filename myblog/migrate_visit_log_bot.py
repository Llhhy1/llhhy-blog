"""v3.7.1 数据库迁移：为 visit_log 表新增 bot 识别字段。

背景：
- 项目用 SQLite（blog.db）。Flask-SQLAlchemy 的 create_all 只建「不存在的表」，
  不会给已存在的表加列，所以升级到 v3.7.1 必须手动迁移。
- 本脚本幂等：先用 PRAGMA table_info 检查列是否已存在，已存在则跳过，可重复运行。
- 新增列：is_bot(BOOLEAN) / bot_name(VARCHAR60) / bot_category(VARCHAR20)

运行方式（二选一）：
  1) 环境变量指定 db 路径（推荐，宝塔部署时用真实路径）：
       BLOG_DB=/www/wwwroot/你的站点/data/blog.db python myblog/migrate_visit_log_bot.py
  2) 自动查找（脚本会尝试 ../data/blog.db、./data/blog.db、当前目录/data/blog.db）：
       cd <项目根>
       python myblog/migrate_visit_log_bot.py
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
        "is_bot": "BOOLEAN DEFAULT 0",
        "bot_name": "VARCHAR(60) DEFAULT ''",
        "bot_category": "VARCHAR(20) DEFAULT ''",
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
