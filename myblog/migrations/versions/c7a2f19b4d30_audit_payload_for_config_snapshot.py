"""审计日志加 payload 列（v3.25.2 · 配置快照与回滚）

`log_audit` 一直记「谁在什么时候改了设置」，但不记「改之前是什么值」—— 于是改错了
（SMTP 端口填错 / 限流阈值调成 1）只能凭记忆手改回去。

本迁移给 `audit_log` 加一列 `payload`（Text，存 JSON 快照）。

**为什么不用 `detail`**：`detail` 是 `String(300)`，配置快照动辄几 KB。
硬塞会被截断，而**被截断的快照回滚回去就是错值** —— 比没有快照更危险。

**为什么加可空列而不是新建快照表**：项目纪律「能走 log_audit 优先走审计表」。
快照与「谁改的」同处一行，天然对齐；新建表则两者可能各写各的、不同步。
已有行的 `payload` 为 NULL，`config_rollback` 一律跳过它们（`if not row.payload`）。

**幂等**：用 `inspect` 先看列在不在，重复执行不报错（运维有时会手动重跑）。

⚠️ **安全**：快照里存的是 `Setting` 的**原始值**，敏感项（OSS SecretKey /
WebDAV 密码 / SCP 私钥）落库时已是 Fernet 密文（`bkenc$` 前缀）—— 回滚全程
不接触明文。审计的 `detail` 只写「改了哪几个 key」，**绝不写值**。

downgrade：**列保留**（不 DROP）。理由同 e5b8c3f17a24 —— SQLite 的 DROP COLUMN
需要 3.35+，而一个存着历史快照的多余列无害；真要清理走
`DELETE FROM audit_log WHERE payload IS NOT NULL`。

Revision ID: c7a2f19b4d30
Revises: e5b8c3f17a24
Create Date: 2026-10-05 00:10:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "c7a2f19b4d30"
down_revision = "e5b8c3f17a24"
branch_labels = None
depends_on = None


def _has_column(conn, table, col):
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    conn = op.get_bind()
    if _has_column(conn, "audit_log", "payload"):
        log.info("audit_log.payload 已存在，跳过")
        return
    op.add_column("audit_log", sa.Column("payload", sa.Text(), nullable=True))
    log.info("audit_log.payload 已添加（可空；历史行为 NULL）")


def downgrade():
    """**刻意不删列**：SQLite DROP COLUMN 需 3.35+，且列里有配置快照历史。

    如需清理：`DELETE FROM audit_log WHERE payload IS NOT NULL`。
    """
    log.info("downgrade 保留 audit_log.payload 列（含配置快照历史），如需清理请手工 DELETE")
