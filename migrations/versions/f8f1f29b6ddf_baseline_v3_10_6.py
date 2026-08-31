"""baseline v3.10.6

Flask-Migrate 基线（v3.10.6 / Python 3.13.5 / Flask 3.0.3）。

设计取舍：本项目生产建表主路径仍是 `db.create_all()` + `_migrate_*` 启动自愈
（见 myblog/app.py:create_app 启动块），Flask-Migrate 仅作为「额外登记的迁移
工具」。因此基线迁移直接复用 `db.create_all()` 产出与现状完全一致的表结构，
而不是手写 op.create_table——避免模型定义与迁移脚本双重描述导致漂移。

既有库（生产 blog.db）只需一次性 `flask db stamp head` 将基线版本号写入
alembic_version，不改动任何表（零风险）。之后新增/修改列时，`flask db migrate`
会基于本基线与当前模型自动 diff 出真实迁移脚本，再用 `flask db upgrade` 应用。

Revision ID: f8f1f29b6ddf
Revises:
Create Date: 2026-08-31 23:33:47.887861

"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

from flask import current_app


# revision identifiers, used by Alembic.
revision = 'f8f1f29b6ddf'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 复用生产主路径 db.create_all()，保证与现状表结构逐字节一致。
    db = current_app.extensions["migrate"].db
    db.create_all()
    # FTS5 虚拟表不在 SQLAlchemy metadata 内，create_all 不会建；这里与生产
    # create_app 启动块（fts.ensure）保持一致，单独建 post_fts 及其影子表。
    # fts.ensure 内部已做「FTS5 是否可用」探测与幂等判断。
    from fts import ensure as fts_ensure
    fts_ensure()


def downgrade():
    db = current_app.extensions["migrate"].db
    from fts import available as fts_available
    if fts_available():
        op.execute("DROP TABLE IF EXISTS post_fts")
    db.drop_all()
