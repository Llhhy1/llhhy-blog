"""新建 media_asset 媒体资源表（v4.14.0 · 图床 / 视频归档）

## 背景

v3.14.0 的媒体库是**纯文件系统扫描**：`os.listdir(static/uploads)` → 从文件名
前缀解析时间 → 对每个文件扫全部文章正文做字符串包含，判断「这张图有没有被引用」。
只有图片、没有归档需求时够用。要支持「图床 + 视频 + 分类归档」后它有三处硬伤：

1. 标题 / 归档分类 / 视频时长 / 封面 / 是否公开 —— 文件名表达不了；
2. 引用判定 `O(文件数 × 文章数)`，几百个视频进来首屏就是秒级卡顿；
3. 目录扫描只能全量读内存再排序，配合上一条就是雪崩。

因此新增**一张表**承载元数据。**不改任何既有表** —— 符合项目「能不改表就不改表」
的纪律：这里变的是「新增一个实体」，不是「给老实体加字段」。

## 为什么 `uploaded_by` 不设外键

用户被删除时，他上传的图片/视频**不应该跟着消失**（那会让历史文章集体裂图）。
存裸 id，展示时再 join，取不到就显示「已注销用户」。

## 为什么 `folder` 是字符串而不是分类表

归档分类是给人看的标签，不是需要引用完整性的实体。做成表要多一套增删改查界面，
而收益只有「改名时自动同步」—— 字符串改名用一条 UPDATE 也能做到，且不会产生
孤儿分类。真要分类树，届时再加不迟。

## 幂等

先用 `inspect` 看表在不在，重复执行不报错（运维会手动重跑）。

downgrade：**DROP TABLE**。与「加列」类迁移不同，这里是一张全新的独立表，
删掉不会破坏既有数据；但表里有归档元数据，日志里明确提示先自行备份。

Revision ID: f3b7d2a91c58
Revises: d9f1a4c7b2e8
Create Date: 2026-10-27 22:45:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "f3b7d2a91c58"
down_revision = "d9f1a4c7b2e8"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_media_asset_filename", "filename"),
    ("ix_media_asset_kind", "kind"),
    ("ix_media_asset_folder", "folder"),
    ("ix_media_asset_is_public", "is_public"),
    ("ix_media_asset_created_at", "created_at"),
)


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "media_asset" in insp.get_table_names():
        log.info("media_asset 已存在，跳过建表")
        return

    op.create_table(
        "media_asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="image"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="local"),
        sa.Column("storage", sa.String(length=16), nullable=False, server_default="local"),
        sa.Column("url", sa.String(length=800), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=200), nullable=True, server_default=""),
        sa.Column("folder", sa.String(length=60), nullable=True, server_default=""),
        sa.Column("mime", sa.String(length=80), nullable=True, server_default=""),
        sa.Column("size", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("poster", sa.String(length=800), nullable=True, server_default=""),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    for name, col in _INDEXES:
        op.create_index(name, "media_asset", [col])
    log.info("media_asset 新建完成（%d 个索引）", len(_INDEXES))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "media_asset" not in insp.get_table_names():
        log.info("media_asset 不存在，跳过")
        return
    log.warning("即将删除 media_asset —— 表内的归档元数据（标题/分类/封面/公开标记）不可恢复，"
                "磁盘上的文件不受影响。如需保留请先导出本表。")
    op.drop_table("media_asset")
    log.info("media_asset 已删除")
