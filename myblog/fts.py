"""全文搜索（SQLite FTS5）维护与查询。

设计要点：
- 用 FTS5 虚拟表 post_fts 对文章标题/摘要/正文建全文索引，按相关度（rank）排序。
- 若运行环境不支持 FTS5（极少数精简版 SQLite），available() 返回 False，
  所有调用方自动回退到 LIKE 搜索，绝不报错中断。
- 维护接口（ensure / sync_post / delete_post）在应用启动时和文章增删改时调用。
"""
from models import db, Post


def _probe():
    try:
        db.session.execute(db.text("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(content)"))
        db.session.execute(db.text("DROP TABLE _fts_probe"))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


_AVAIL = None


def available():
    """FTS5 是否可用（带缓存，只探测一次）。"""
    global _AVAIL
    if _AVAIL is None:
        _AVAIL = _probe()
    return _AVAIL


def ensure():
    """建 post_fts 虚拟表并全量填充（仅首次，幂等）。"""
    if not available():
        return
    db.session.execute(db.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS post_fts "
        "USING fts5(title, summary, content, slug UNINDEXED)"
    ))
    db.session.commit()
    try:
        cnt = db.session.execute(db.text("SELECT count(*) FROM post_fts")).scalar() or 0
    except Exception:
        cnt = 0
    if cnt == 0:
        for p in Post.query.filter_by(published=True).all():
            db.session.execute(db.text(
                "INSERT INTO post_fts (rowid, title, summary, content, slug) "
                "VALUES (:rid,:t,:s,:c,:sl)"
            ), {"rid": p.id, "t": p.title, "s": p.summary or "", "c": p.content or "", "sl": p.slug})
        db.session.commit()


def sync_post(post):
    """新增 / 更新文章后同步 FTS 索引（未发布不进索引）。"""
    if not available():
        return
    try:
        db.session.execute(db.text("DELETE FROM post_fts WHERE rowid=:rid"), {"rid": post.id})
        if post.published:
            db.session.execute(db.text(
                "INSERT INTO post_fts (rowid, title, summary, content, slug) "
                "VALUES (:rid,:t,:s,:c,:sl)"
            ), {"rid": post.id, "t": post.title, "s": post.summary or "", "c": post.content or "", "sl": post.slug})
        db.session.commit()
    except Exception:
        db.session.rollback()


def delete_post(post_id):
    """删除文章后清理 FTS 索引。"""
    if not available():
        return
    try:
        db.session.execute(db.text("DELETE FROM post_fts WHERE rowid=:rid"), {"rid": post_id})
        db.session.commit()
    except Exception:
        db.session.rollback()


def search(q, limit=30):
    """全文搜索：FTS5 命中返回 post id 列表（按相关度），失败返回 None（调用方回退）。"""
    if not available() or not q:
        return None
    try:
        rows = db.session.execute(db.text(
            "SELECT rowid FROM post_fts WHERE post_fts MATCH :q ORDER BY rank LIMIT :lim"
        ), {"q": q, "lim": limit}).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return None
