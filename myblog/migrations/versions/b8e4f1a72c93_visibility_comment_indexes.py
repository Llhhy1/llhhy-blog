"""列表热路径索引：post 可见性/时间、comment(post_id, approved)

v4.7.3 审计：`visible_posts_query()` 每次列表/搜索都按 published/in_trash/
is_private 过滤并按 created_at 排序，但这三列和 created_at 都没有索引；
评论列表与计数同样按 post_id 扫全表。数据量上万后 SQLite 单写者下会明显放大
锁等待。

保持幂等：全新库由 `db.create_all()` 已按模型建好同名索引，迁移不能重复创建。

Revision ID: b8e4f1a72c93
Revises: a7e3c92d5b18
Create Date: 2026-10-20 11:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "b8e4f1a72c93"
down_revision = "a7e3c92d5b18"
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


def _create(name, table, cols):
    if _index_exists(name):
        return
    op.create_index(name, table, cols, unique=False)


def upgrade():
    _create("ix_post_visibility_created", "post",
            ["published", "in_trash", "is_private", "created_at"])
    _create("ix_comment_post_approved", "comment", ["post_id", "approved"])


def downgrade():
    for name in ("ix_comment_post_approved", "ix_post_visibility_created"):
        if _index_exists(name):
            op.drop_index(name)
