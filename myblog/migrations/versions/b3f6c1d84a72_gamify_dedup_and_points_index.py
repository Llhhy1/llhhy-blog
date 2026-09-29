"""gamify 去重索引 + 排行榜索引（#47 改表批次）

保留策略（2026-09-29 产品决策）：reader 永久 / point_log 2 年 / reader_badge 随 reader。
其中**保留策略是应用逻辑**（`gamify.prune_retention()` + 每日调度），不涉及表结构，
所以本迁移只做索引。

1. `point_log` 加**数据库级去重唯一索引** `uq_pointlog_dedup`
   (reader_id, reason, COALESCE(post_id, -1), day)。
   - 用 COALESCE 而非裸 post_id：`post_id` 可空，而 SQLite 与 Postgres 的 UNIQUE
     都把 NULL 视作「互不相同」，朴素四列唯一键对 visit/share 这类无文章的积分
     **根本不生效**（已实测：同样两条 NULL 行能插进去）。
   - 哨兵取 -1：`post_id` 实际取值 ≥ 1，不可能与之冲突。
2. `reader.points` 加索引 `ix_reader_points`（排行榜按积分排序）。

两个必须注意的点：
- **必须先去重再建索引**。`gamify.award()` 是「先查后插」，存在 TOCTOU 竞态，
  既有库里很可能已积累重复行；直接 `CREATE UNIQUE INDEX` 会失败并中断升级。
- **必须幂等**。全新库由 `db.create_all()` 建表时，这两个索引已随模型建好；
  若之后再跑 `upgrade`，不加判断就会撞「index already exists」。故先查后建。
  表达式索引另有一个坑：SQLAlchemy 反射不了它（会警告 Skipped unsupported
  reflection），已在 `env.py` 的 `include_object` 中排除，避免 autogenerate
  每次生成多余的 `op.create_index()`。

Revision ID: b3f6c1d84a72
Revises: f8f1f29b6ddf
Create Date: 2026-09-29 23:52:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3f6c1d84a72"
down_revision = "f8f1f29b6ddf"
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


def upgrade():
    # 1) 先清掉历史重复行：同一去重键只保留 id 最小的一条。
    op.execute(
        """
        DELETE FROM point_log
        WHERE id NOT IN (
            SELECT MIN(id) FROM point_log
            GROUP BY reader_id, reason, COALESCE(post_id, -1), day
        )
        """
    )
    # 2) 建索引（幂等）
    if not _index_exists("uq_pointlog_dedup"):
        op.execute(
            "CREATE UNIQUE INDEX uq_pointlog_dedup "
            "ON point_log (reader_id, reason, COALESCE(post_id, -1), day)"
        )
    if not _index_exists("ix_reader_points"):
        op.create_index("ix_reader_points", "reader", ["points"], unique=False)


def downgrade():
    # 幂等：索引可能已被手删（或被 create_all 重建过），先查再删。
    if _index_exists("ix_reader_points"):
        op.drop_index("ix_reader_points", table_name="reader")
    if _index_exists("uq_pointlog_dedup"):
        op.execute("DROP INDEX uq_pointlog_dedup")
