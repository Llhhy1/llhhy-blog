"""empty baseline

现有库已通过 db.create_all() + _migrate_* 建表。本基线为「空迁移」：
- upgrade/downgrade 均不做任何 schema 变更；
- 在已有库上执行一次 `flask db stamp head` 即可把当前 schema 登记为基线，
  之后改 model 用 `flask db migrate` 生成差异迁移，无需对已有表做任何改动。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
