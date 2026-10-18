"""阅读记录加 duration 列（v4.5.0 · 平均阅读时间）

后台「访客数据」要显示平均阅读时间，但**此前根本没有时长数据**：
`ReadLog` 只有 `read_count`（累加次数），前端也没有任何停留时长上报
（全目录搜 `visibilitychange` / `sendBeacon` 均为 0 命中）。所以这不是
"加个显示"，得先有数据可读。

本迁移给 `read_log` 加一列 `duration`（秒，累加）。

**为什么加在 `read_log` 而不是 `visit_log`**：`read_log` 已按
`(post_id, ip)` 唯一，累加语义天然成立（同一访客同一篇反复读，时长也该
累加）。而 `visit_log` 是「每次访问一行」的流水，拿它算时长必须先配对
相邻记录 —— 读者关页面后没有后续记录，最后一段时长会整体丢失，系统性低估。

**为什么 `NOT NULL` + `server_default='0'`**：历史行必须有值，否则
`SUM(duration)` 在 NULL 参与下会漏掉旧数据。default 0 表示"这次阅读没有
上报时长"（升级前的老阅读都落在这一档），统计时用 `duration > 0` 过滤即可。

**幂等**：用 `inspect` 先看列在不在，重复执行不报错（运维有时会手动重跑）。

downgrade：**列保留**（不 DROP）。理由同 c7a2f19b4d30 —— SQLite 的
DROP COLUMN 需要 3.35+，且一个默认 0 的多余列无害；真要清理走
`UPDATE read_log SET duration = 0`。

Revision ID: a7e3c92d5b18
Revises: c7a2f19b4d30
Create Date: 2026-10-18 22:40:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "a7e3c92d5b18"
down_revision = "c7a2f19b4d30"
branch_labels = None
depends_on = None


def _has_column(conn, table, col):
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    conn = op.get_bind()
    if _has_column(conn, "read_log", "duration"):
        log.info("read_log.duration 已存在，跳过")
        return
    op.add_column("read_log", sa.Column("duration", sa.Integer(),
                                        nullable=False, server_default="0"))
    log.info("read_log.duration 已添加（秒，默认 0 = 未上报时长）")


def downgrade():
    """**刻意不删列**：SQLite DROP COLUMN 需 3.35+，且默认 0 的列无害。

    如需清理：`UPDATE read_log SET duration = 0`。
    """
    log.info("downgrade 保留 read_log.duration 列，如需清理请手工 UPDATE 归零")