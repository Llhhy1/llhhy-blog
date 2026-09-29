"""历史列补齐（退役 `_migrate_*` 的前置条件）

背景：本项目历史上**所有**列的新增都靠启动自愈（app.py 里 9 个 `_migrate_*`）完成，
Alembic 只在生产被 `stamp` 过、从未真正 upgrade —— 形成「模型 + `_migrate_*` 两份
schema 真相源」。v3.24.0 起部署流程会显式跑 `flask db upgrade`（见 update.sh 的
`apply_db_migrations`），于是可以把 `_migrate_*` 删掉，改由本迁移兜底。

本迁移是 `_migrate_*` 的**冻结快照**（不是从模型派生——迁移必须是稳定的历史记录）：
逐表检查列是否存在，缺了才 ADD COLUMN。因此对生产库（列早已齐全）是**完全空操作**，
对任何更老的库则补齐到当前结构。

刻意**不含**建表：`db.create_all()` 仍在启动时负责建缺失的表，且基线迁移本身也会
create_all；本迁移只补「已有表缺列」这一件 create_all 做不到的事。

downgrade 刻意留空：SQLite 的 DROP COLUMN 需要 3.35+，且这些列删掉没有意义
（多一列无害，删反而可能丢数据）。

Revision ID: d4a7f08c2e91
Revises: b3f6c1d84a72
Create Date: 2026-09-30 00:33:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4a7f08c2e91"
down_revision = "b3f6c1d84a72"
branch_labels = None
depends_on = None

# 冻结快照：与退役前 app.py 里 `_migrate_*` 的 specs 逐项一致。
# 顺序按表分组，组内顺序即历史添加顺序。
LEGACY_COLUMNS = {
    "user": [
        ("session_version", "INTEGER DEFAULT 0"),
        ("must_change_password", "BOOLEAN DEFAULT 1"),
    ],
    "post": [
        ("author_id", "INTEGER"),
        ("series_id", "INTEGER"),
        ("scheduled_at", "DATETIME"),
        ("is_pinned", "BOOLEAN"),
        ("seo_description", "TEXT"),
        ("seo_keywords", "VARCHAR(300)"),
        ("pin_requested", "BOOLEAN"),
        ("word_count", "INTEGER DEFAULT 0"),
        ("reading_minutes", "INTEGER DEFAULT 0"),
        ("reward_enabled", "BOOLEAN DEFAULT 0"),
        ("reward_qr", "VARCHAR(500) DEFAULT ''"),
        ("is_private", "BOOLEAN DEFAULT 0"),
        ("in_trash", "BOOLEAN DEFAULT 0"),
        ("deleted_at", "DATETIME"),
        ("content_html", "TEXT"),
        ("content_hash", "VARCHAR(64)"),
        ("lang", "VARCHAR(10) DEFAULT 'zh'"),
        ("translation_group", "VARCHAR(64) DEFAULT ''"),
    ],
    "comment": [
        ("ip", "VARCHAR(64) DEFAULT ''"),
        ("region", "VARCHAR(64) DEFAULT ''"),
        ("device", "VARCHAR(120) DEFAULT ''"),
        ("parent_id", "INTEGER"),
        ("reply_to", "VARCHAR(80) DEFAULT ''"),
        ("likes", "INTEGER DEFAULT 0"),
        ("is_read", "BOOLEAN DEFAULT 0"),
        ("approved", "BOOLEAN DEFAULT 1"),
        ("email_hash", "VARCHAR(32) DEFAULT ''"),
    ],
    "friend_link": [
        ("rss_url", "VARCHAR(300) DEFAULT ''"),
    ],
    "guestbook": [
        ("is_read", "BOOLEAN DEFAULT 0"),
    ],
    "subscriber": [
        ("unsub_token", "VARCHAR(64) DEFAULT ''"),
    ],
    "audit_log": [
        ("success", "BOOLEAN DEFAULT 1"),
    ],
    "visit_log": [
        ("is_bot", "BOOLEAN DEFAULT 0"),
        ("bot_name", "VARCHAR(60) DEFAULT ''"),
        ("bot_category", "VARCHAR(20) DEFAULT ''"),
        ("referrer", "VARCHAR(300) DEFAULT ''"),
    ],
}


def _table_exists(bind, table):
    sql = ("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '%s'"
           if bind.dialect.name == "sqlite"
           else "SELECT 1 FROM information_schema.tables WHERE table_name = '%s'")
    # 表名来自上面的常量字典，非用户输入，拼接安全。
    return bind.execute(sa.text(sql % table)).fetchone() is not None


def _existing_columns(bind, table):
    if bind.dialect.name == "sqlite":
        # PRAGMA 的表名不能参数化，用常量拼接（非用户输入）。
        rows = bind.execute(sa.text("PRAGMA table_info(%s)" % table)).fetchall()
        return {r[1] for r in rows}
    rows = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = '%s'" % table
    )).fetchall()
    return {r[0] for r in rows}


def upgrade():
    bind = op.get_bind()
    for table, cols in LEGACY_COLUMNS.items():
        if not _table_exists(bind, table):
            continue          # 表都没有 → 交给 create_all / 基线迁移，不在这里建
        have = _existing_columns(bind, table)
        for name, ddl in cols:
            if name not in have:
                op.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))


def downgrade():
    # 刻意不删列：SQLite DROP COLUMN 需 3.35+，且这些列留着无害、删掉可能丢数据。
    pass
