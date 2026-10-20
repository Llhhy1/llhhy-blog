"""在线人数索引 + 「谁在用 llhhy-blog」自愿登记标记

v4.8.0 两件事一起：
- `ix_visit_log_created`：`/api/stats/online` 按 `created_at >= 最近 N 分钟` 扫
  `visit_log`，此前只有 `date` / `ip` / `is_bot` 三个索引，窗口查询走全表。
- `friend_link.uses_llhhy` / `link_application.uses_llhhy`：使用者**自愿登记**
  「我这个站是用 llhhy-blog 搭的」。走既有友链申请 + 审核链路，不新建表、
  不引入遥测 —— 拿不到真实部署数，就不假装拿得到（口径见 api/site.py 的
  `/adopters`）。

保持幂等：全新库由 `db.create_all()` 已按模型建好索引与列，迁移不得重复创建；
生产库可能是老结构，缺什么补什么。

Revision ID: c9f2a6d18e40
Revises: b8e4f1a72c93
Create Date: 2026-10-20 23:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "c9f2a6d18e40"
down_revision = "b8e4f1a72c93"
branch_labels = None
depends_on = None


def _index_exists(name):
    """跨方言判断索引是否存在（SQLite / Postgres）。"""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :n"
    else:
        sql = "SELECT 1 FROM pg_indexes WHERE indexname = :n"
    return bind.execute(sa.text(sql), {"n": name}).fetchone() is not None


def _column_exists(table, name):
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # 名字必须与 SQLAlchemy `index=True` 生成的 `ix_visit_log_created_at` **完全一致**：
    # 否则全新库（create_all 已建）与老库（走本迁移）会各留一个同列索引，
    # 而幂等检查按名字判断，根本发现不了重复。
    if not _index_exists("ix_visit_log_created_at"):
        op.create_index("ix_visit_log_created_at", "visit_log", ["created_at"], unique=False)
    for table in ("friend_link", "link_application"):
        if not _column_exists(table, "uses_llhhy"):
            op.add_column(table, sa.Column("uses_llhhy", sa.Boolean(), nullable=False,
                                           server_default=sa.false()))


def downgrade():
    for table in ("link_application", "friend_link"):
        if _column_exists(table, "uses_llhhy"):
            # SQLite 3.35+ 才支持 DROP COLUMN；本项目服务器为更新的 Python 自带 SQLite。
            op.drop_column(table, "uses_llhhy")
    if _index_exists("ix_visit_log_created_at"):
        op.drop_index("ix_visit_log_created_at")
