"""生态统计：使用本系统部署的站点注册表

v4.7.5 新增一张小表 `ecosystem_site`（中心端才��数据）。

⚠️ **为什么允许加表**：项目纪律是「能不改表就不改表，能用 log_audit 就不加字段」。
但这里需要的是「每个站点一行 + 最后心跳时间 + 按时间范围查询活跃数」——
`log_audit` 是**日志表**（追加写、不可去重、无法按站点聚合），承担不了这个职责。
表只有 7 列，且只在「收到别人心跳」的实例上有数据（别的部署实例是空表）。

保持幂等：全新库由 `db.create_all()` 已按模型建好同名表，迁移不能重复创建。

Revision ID: c3d9e2f71a04
Revises: b8e4f1a72c93
Create Date: 2026-10-20 20:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "c3d9e2f71a04"
down_revision = "b8e4f1a72c93"
branch_labels = None
depends_on = None


def _table_exists(name):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n"
    else:
        sql = "SELECT 1 FROM information_schema.tables WHERE table_name = :n"
    return bind.execute(sa.text(sql), {"n": name}).first() is not None


def _index_exists(name):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :n"
    else:
        sql = "SELECT 1 FROM pg_indexes WHERE indexname = :n"
    return bind.execute(sa.text(sql), {"n": name}).first() is not None


def upgrade():
    if not _table_exists("ecosystem_site"):
        op.create_table(
            "ecosystem_site",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("site_key", sa.String(length=64), nullable=False),
            sa.Column("url", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("version", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("listed", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("first_seen", sa.DateTime(), nullable=True),
            sa.Column("last_seen", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    # 唯一约束（去重的根基）：SQLite 上 create_table 里的 unique=True 会自动建索引，
    # 但显式检查一次，保证「已 create_all 的库」和「迁移建的库」结构一致。
    if not _index_exists("ix_ecosystem_site_site_key"):
        op.create_index("ix_ecosystem_site_site_key", "ecosystem_site", ["site_key"],
                        unique=True)
    if not _index_exists("ix_ecosystem_site_last_seen"):
        op.create_index("ix_ecosystem_site_last_seen", "ecosystem_site", ["last_seen"],
                        unique=False)


def downgrade():
    if _index_exists("ix_ecosystem_site_last_seen"):
        op.drop_index("ix_ecosystem_site_last_seen", table_name="ecosystem_site")
    if _index_exists("ix_ecosystem_site_site_key"):
        op.drop_index("ix_ecosystem_site_site_key", table_name="ecosystem_site")
    if _table_exists("ecosystem_site"):
        op.drop_table("ecosystem_site")
