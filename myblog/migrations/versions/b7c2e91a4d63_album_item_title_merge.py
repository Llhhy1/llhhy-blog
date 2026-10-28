"""把相册图注并进素材标题，名字只留一份（v5.2.1）

## 为什么

v5.2.0 把「图注」设计成相册语境的说明，与素材标题**并存**，并靠展示层回退
（`caption || media.title`）避免重复填写。上线后实测反馈是不认这个区分：

> 「相册里改了文件名称之后呢，媒体库的名称不会跟着改」

用户的理解是对的 —— 同一张照片被起了两个名，在相册里叫「意溪渡口」，
回媒体库还是一串 `1000142174_1_1_7212616`。既然目标本来就是「不要重复填」，
就不该把「两个名字」做成默认路径。

v5.2.1 起：**名字只有一份，存在 `media_asset.title`**。
编排页的输入框直接写它，媒体库改名也读它（不是副本），两边天然同步。

## 本迁移做什么

把已存在的 `album_item.caption` 当作「用户给这张图起的名字」写进
`media_asset.title`，然后清空 caption。这样：
- 用户在相册里写过的名字不会丢；
- 不会出现「caption 留着旧值、title 改了但前台还显示旧 caption」的漂移。

## 覆盖规则（明确承认的取舍）

**caption 覆盖 title**，不做「只填空值」的保守判断。

理由：用户抱怨的正是「相册里改的名字媒体库不认」。若保留 title、
把 caption 丢掉，等于把用户最近一次输入丢弃，而且他回到媒体库看到的
还是旧名 —— 现象与修复前一模一样。

代价：媒体库里**手打过**的标题若与 caption 不同，会被 caption 顶掉
（生产实测一例：`潮州1` → `意溪渡口`）。值只换不删，且用户在前台看到的就是
他最后写下的那个名字，符合预期。

## 幂等

判据是「caption 非空」——跑完 caption 全空，重复执行是空操作。
对新装环境（无相册条目）同样空操作。

downgrade 刻意留空：名字已并进 `media_asset.title`，
**无法区分「原本就是标题」和「从 caption 合过来的」**，
拆回去只会制造猜测出来的错误数据（同 d4a7f08c2e91 的口径：不写不可逆的假回滚）。

Revision ID: b7c2e91a4d63
Revises: a1c9e4f72b38
Create Date: 2026-10-28 16:10:00.000000

"""
import logging

import sqlalchemy as sa
from alembic import op

log = logging.getLogger("alembic.env")

revision = "b7c2e91a4d63"
down_revision = "a1c9e4f72b38"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "album_item" not in tables or "media_asset" not in tables:
        log.info("album_item / media_asset 不存在，跳过图注合并")
        return

    rows = conn.execute(sa.text(
        "SELECT id, media_id, caption FROM album_item "
        "WHERE caption IS NOT NULL AND TRIM(caption) <> ''"
    )).fetchall()
    if not rows:
        log.info("没有需要合并的相册图注")
        return

    moved = 0
    for iid, mid, caption in rows:
        name = (caption or "").strip()[:200]
        if not name:
            continue
        if mid:
            conn.execute(
                sa.text("UPDATE media_asset SET title = :t WHERE id = :m"),
                {"t": name, "m": int(mid)})
        conn.execute(
            sa.text("UPDATE album_item SET caption = '' WHERE id = :i"),
            {"i": int(iid)})
        moved += 1
    log.info("相册图注合并进素材标题：%d 条（caption 已清空，名字只剩一份）", moved)


def downgrade():
    # 单向迁移，见模块 docstring「downgrade 刻意留空」。
    pass
