"""UGC 搬出 Setting KV（v3.24.0 · Setting 治理）

三类「每条内容一个键」的 UGC 原先存在 setting 表里：

| 键 | 内容 | 挂载点 |
| --- | --- | --- |
| `react_<comment_id>` | 评论表情回应计数（JSON `{"👍":3}`） | comment 行 |
| `ai_summary_<post_id>` | AI 生成摘要 | post 行 |
| `ai_tags_<post_id>` | AI 标签建议 | post 行 |

问题有两层：
1. **语义错**：setting 是「站点设置」表，却存着随评论/文章数**无限增长**的 UGC；
2. **被放大**：setting 有 **6 处** `Setting.query.all()` 全表加载（后台每次渲染的
   `inject_globals`、天气默认坐标、后台设置页 ×3、`api/common._settings_map`），
   每次都把几千条 UGC 一起捞出来构建字典。

本迁移三步：
1. 幂等加三列 `comment.reactions` / `post.ai_summary` / `post.ai_tags`；
2. 数据搬迁：把上述键的值写进**所属行**的对应列（UGC 各归其主，不需要新表）；
3. 清理：搬迁完成后删除这些 setting 行（含目标行已不存在的孤儿行）。

⚠️ 第 3 步是**删除操作**：内容已先复制到新列、不丢数据，但**升级前务必备份 blog.db**。

downgrade：把列里的值写回 setting 键（尽力还原）；**列保留**——SQLite 的 DROP COLUMN
需要 3.35+，且多一列无害。

Revision ID: e5b8c3f17a24
Revises: d4a7f08c2e91
Create Date: 2026-09-30 01:10:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5b8c3f17a24"
down_revision = "d4a7f08c2e91"
branch_labels = None
depends_on = None

_LOG = logging.getLogger("alembic.runtime.migration")

# (键前缀, 目标表, 目标列)
UGC_PREFIXES = (
    ("react_", "comment", "reactions"),
    ("ai_summary_", "post", "ai_summary"),
    ("ai_tags_", "post", "ai_tags"),
)


def _has_table(bind, table):
    sql = ("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '%s'" % table
           if bind.dialect.name == "sqlite"
           else "SELECT 1 FROM information_schema.tables WHERE table_name = '%s'" % table)
    return bind.execute(sa.text(sql)).fetchone() is not None


def _has_column(bind, table, col):
    if bind.dialect.name == "sqlite":
        rows = bind.execute(sa.text("PRAGMA table_info(%s)" % table)).fetchall()
        return any(r[1] == col for r in rows)
    rows = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = '%s'" % table
    )).fetchall()
    return any(r[0] == col for r in rows)


def _upsert_setting(bind, key, value):
    bind.execute(sa.text("DELETE FROM setting WHERE key = :k"), {"k": key})
    bind.execute(sa.text("INSERT INTO setting (key, value) VALUES (:k, :v)"),
                 {"k": key, "v": value})


def upgrade():
    bind = op.get_bind()

    # 1) 幂等加列
    if _has_table(bind, "comment") and not _has_column(bind, "comment", "reactions"):
        op.execute("ALTER TABLE comment ADD COLUMN reactions TEXT")
    for _p, table, col in UGC_PREFIXES:
        if table != "post":
            continue
        if _has_table(bind, "post") and not _has_column(bind, "post", col):
            op.execute("ALTER TABLE post ADD COLUMN %s TEXT" % col)

    # 2) 搬迁  3) 清理
    if not _has_table(bind, "setting"):
        return
    rows = bind.execute(sa.text("SELECT key, value FROM setting")).fetchall()
    moved = {}
    to_delete = []
    stale = 0
    for key, value in rows:
        for prefix, table, col in UGC_PREFIXES:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix):]
            if not suffix.isdigit():
                continue          # 非 UGC 键（例如真有个设置恰好以 react_ 开头）→ 不动
            oid = int(suffix)
            hit = bind.execute(sa.text("SELECT 1 FROM %s WHERE id = :i" % table),
                               {"i": oid}).fetchone()
            if hit:
                bind.execute(sa.text("UPDATE %s SET %s = :v WHERE id = :i" % (table, col)),
                             {"v": value, "i": oid})
                moved[col] = moved.get(col, 0) + 1
            else:
                stale += 1        # 目标行已删除 → 孤儿 UGC，一并清掉
            to_delete.append(key)
            break
    for k in to_delete:
        bind.execute(sa.text("DELETE FROM setting WHERE key = :k"), {"k": k})
    _LOG.info("[Setting 治理] 搬迁 %s；清理 setting 行 %d 条（其中孤儿 %d 条）",
              moved or "0 条", len(to_delete), stale)


def downgrade():
    bind = op.get_bind()
    if not _has_table(bind, "setting"):
        return
    # 写回 setting 键（尽力还原）；列保留 —— SQLite DROP COLUMN 需 3.35+，且多列无害。
    if _has_table(bind, "comment") and _has_column(bind, "comment", "reactions"):
        for cid, val in bind.execute(sa.text(
                "SELECT id, reactions FROM comment "
                "WHERE reactions IS NOT NULL AND reactions != ''")).fetchall():
            _upsert_setting(bind, "react_%d" % cid, val)
    for _p, table, col in UGC_PREFIXES:
        if table != "post" or not _has_column(bind, "post", col):
            continue
        prefix = _p
        for pid, val in bind.execute(sa.text(
                "SELECT id, %s FROM post WHERE %s IS NOT NULL AND %s != ''" % (col, col, col))
        ).fetchall():
            _upsert_setting(bind, "%s%d" % (prefix, pid), val)
