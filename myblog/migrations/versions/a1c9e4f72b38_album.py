"""新建相册三张表：album / album_section / album_item（v5.1.0 · 相册归档）

## 背景

v5.0.0 把媒体库升级成了图床（图片 + 视频 + 云存储 + 分栏归档），
但 `/gallery` 仍然是**素材视角**：所有公开媒体平铺一页、靠分类 chips 筛选，
没有「一次旅行 / 一个主题」这种集合概念，也没有给单张照片配说明文字的地方。

参考 `album.victor42.work` 这类相册站后，明确了缺的是**编排层**：
相册是独立内容页（有 slug / 封面 / 标题 / 日期 / 张数），
内部按可选分组组织，每张照片带 `<figcaption>` 说明。

## 为什么是三张表，而不是给 media_asset 加字段

1. **同一张图要能进多个相册**：一张照片既属于「云和自驾」，也可能属于
   「2026 年度精选」。把 album_id 写进 media_asset 就只能归一处。
2. **说明文字是相册语境相关的**：同一张照片在两个相册里配文不同，
   caption 属于「照片 × 相册」这条关系，不属于文件本身。
3. **顺序与分组只在相册内有意义**：写在文件上是错的。

所以相册**只引用** media_asset（存 media_id），不复制文件、不复制 URL。

## 为什么 media_id / cover_media_id 不设外键

媒体行被删后，相册项会变成空引用，接口渲染时**跳过**该项，
相册其余部分照常显示 —— 误删一张图不该让整篇游记崩掉。
（与 media_asset.uploaded_by 不设外键是同一条口径：
「内容不该因为账户/素材的删除而连带消失」。）

## 幂等

先用 `inspect` 看表在不在，重复执行不报错（运维会手动重跑）。

downgrade：DROP TABLE。三张都是全新独立表，删掉不破坏既有数据；
但相册元数据（标题 / 说明 / 编排）无法从文件恢复，日志里明确提示先自行备份。

Revision ID: a1c9e4f72b38
Revises: f3b7d2a91c58
Create Date: 2026-10-28 01:30:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "a1c9e4f72b38"
down_revision = "f3b7d2a91c58"
branch_labels = None
depends_on = None

# (表名, 索引名, 列, 是否唯一)
_INDEXES = (
    ("album", "ix_album_slug", ["slug"], True),
    ("album", "ix_album_is_public", ["is_public"], False),
    ("album", "ix_album_created_at", ["created_at"], False),
    ("album", "ix_album_cover_media_id", ["cover_media_id"], False),
    ("album_section", "ix_album_section_album_id", ["album_id"], False),
    ("album_section", "ix_album_section_sort", ["sort"], False),
    ("album_item", "ix_album_item_album_id", ["album_id"], False),
    ("album_item", "ix_album_item_section_id", ["section_id"], False),
    ("album_item", "ix_album_item_sort", ["sort"], False),
)

_TABLES = ("album", "album_section", "album_item")


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())

    if "album" not in existing:
        op.create_table(
            "album",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("summary", sa.Text(), nullable=True, server_default=""),
            # 游记页三块：相册不只是照片墙，还能写交通/住宿/路线与小提示
            sa.Column("trip_days", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("intro", sa.Text(), nullable=True, server_default=""),
            sa.Column("tips", sa.Text(), nullable=True, server_default=""),
            sa.Column("cover_media_id", sa.Integer(), nullable=True),
            sa.Column("event_date", sa.Date(), nullable=True),
            sa.Column("location", sa.String(length=120), nullable=True, server_default=""),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        log.info("album 新建完成")
    else:
        log.info("album 已存在，跳过建表")

    if "album_section" not in existing:
        op.create_table(
            "album_section",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("album_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=True, server_default=""),
            sa.Column("summary", sa.Text(), nullable=True, server_default=""),
            sa.Column("sort", sa.Integer(), nullable=True, server_default="0"),
        )
        log.info("album_section 新建完成")
    else:
        log.info("album_section 已存在，跳过建表")

    if "album_item" not in existing:
        op.create_table(
            "album_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("album_id", sa.Integer(), nullable=False),
            sa.Column("section_id", sa.Integer(), nullable=True),
            sa.Column("media_id", sa.Integer(), nullable=False),
            sa.Column("caption", sa.Text(), nullable=True, server_default=""),
            sa.Column("sort", sa.Integer(), nullable=True, server_default="0"),
        )
        log.info("album_item 新建完成")
    else:
        log.info("album_item 已存在，跳过建表")

    # 索引一律走 try/except：重跑迁移时索引多半已存在，
    # 直接用开头那份 inspect 快照判断会漏掉「本轮刚建的表」（快照里还没有它）。
    made = 0
    for table, name, cols, uniq in _INDEXES:
        try:
            op.create_index(name, table, cols, unique=uniq)
            made += 1
        except Exception as exc:  # noqa: BLE001  索引已存在不该中断整批
            log.warning("索引 %s 创建跳过：%s", name, str(exc)[:120])
    log.info("相册索引处理完成（新建 %d 个）", made)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing = set(insp.get_table_names())
    log.warning("即将删除相册三张表：其中的标题 / 说明文字 / 编排顺序**无法从文件恢复**；"
                "若仍需保留，请先自行备份 album / album_section / album_item 三表。")
    for table in reversed(_TABLES):
        if table not in existing:
            continue
        for idx in insp.get_indexes(table):
            try:
                op.drop_index(idx["name"], table_name=table)
            except Exception as exc:  # noqa: BLE001
                log.warning("索引 %s 删除跳过：%s", idx["name"], str(exc)[:120])
        op.drop_table(table)
        log.info("已删除 %s", table)
