"""访客日志加设备 / 浏览器列（v4.9.0 · 设备分布统计）

ROADMAP「设备 / 浏览器分布」此前挂了很久，卡在「需新表」这个判断上。
实测不需要新表：`utils.parse_device()` 早就存在（`utils/text.py:46`），
它把 UA 解析成「手机 · Android · Chrome」这样的组合串；只要把解析结果
落进 `visit_log` 就能直接 GROUP BY，无需另建维度表。

**为什么拆成 device / browser 两列，而不是存一个组合串**：
组合串（"手机 · Android · Chrome"）在 SQLite 里做「浏览器分布」聚合时
必须字符串切分，写不进 GROUP BY。拆成两列后设备分布与浏览器分布是两个
干净的分组，互不干扰。系统（OS）不单独成列 —— 它与 device 高度相关
（Android→手机、Windows/macOS→电脑），单列即可表达。

**为什么 `NOT NULL` + `server_default=''`**：历史行必须有值，否则
聚合时 NULL 会自成一档。空串表示「升级前的老访问没采集」，统计时过滤掉。
这两个列由 `stats.record_visit()` 在写日志时填入，**不落原始 UA**。

**隐私**：原始 User-Agent 含设备型号、系统小版本、插件指纹等，属于可
指纹化信息，个人博客没有留存必要。此处只存粗粒度分类（"手机"/"Chrome"），
不可逆推个体，与 `referrer` 只存 origin 是同一条隐私收口原则。

**幂等**：用 `inspect` 先看列在不在，重复执行不报错。

downgrade：**列保留**（不 DROP）。理由同 a7e3c92d5b18 —— SQLite 的
DROP COLUMN 需要 3.35+，且两个默认空串的冗余列无害；真要清理走
`UPDATE visit_log SET device = '', browser = ''`。

Revision ID: d9f1a4c7b2e8
Revises: c3d9e2f71a04
Create Date: 2026-10-24 23:20:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "d9f1a4c7b2e8"
down_revision = "c3d9e2f71a04"
branch_labels = None
depends_on = None


def _has_column(conn, table, col):
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    conn = op.get_bind()
    for col in ("device", "browser"):
        if _has_column(conn, "visit_log", col):
            log.info("visit_log.%s 已存在，跳过", col)
            continue
        op.add_column("visit_log", sa.Column(col, sa.String(40),
                                             nullable=False, server_default=""))
        log.info("visit_log.%s 已添加（空串 = 升级前未采集）", col)


def downgrade():
    """**刻意不删列**：SQLite DROP COLUMN 需 3.35+，且默认空串的列无害。

    如需清理：`UPDATE visit_log SET device = '', browser = ''`。
    """
    log.info("downgrade 保留 visit_log.device/browser 列，如需清理请手工 UPDATE 置空")
