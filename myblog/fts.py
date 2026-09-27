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


def _indexable(post):
    """索引闸门：这篇文章是否允许出现在 `post_fts` 里。

    与 `models.visible_posts_query()` 的**访客**语义对齐（不含超管豁免）。
    为什么在写入侧收口而不只在查询侧：查询分支会随功能增加而漂移（`_is_visible()`
    就是第 4 次漂移出来的），而索引里一旦躺着隐私文章的**正文**，任何一次漏判都是
    直接外泄；写入门闸后，漏判最多是「搜不到」，不会是「泄露」。
    """
    from _time import utcnow
    if not post or not post.published:
        return False
    if post.in_trash or post.is_private:
        return False
    return post.scheduled_at is None or post.scheduled_at <= utcnow()


def _insert(post):
    db.session.execute(db.text(
        "INSERT INTO post_fts (rowid, title, summary, content, slug) "
        "VALUES (:rid,:t,:s,:c,:sl)"
    ), {"rid": post.id, "t": post.title, "s": post.summary or "", "c": post.content or "",
        "sl": post.slug})


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
            if _indexable(p):
                _insert(p)
        db.session.commit()


def rebuild_all():
    """全量重建 `post_fts`：清空后只写入通过 `_indexable()` 的文章。

    必须提供且**执行一次**：`ensure()` 只在表为空时回填（见上方 cnt == 0 判断），
    所以历史库中已存在的隐私文章正文行不会因为改了闸门而消失——它们仍在盘上，
    且仍会被 `/api/search` 的 FTS 分支命中。
    """
    if not available():
        return {"ok": False, "reason": "fts5-unavailable"}
    try:
        db.session.execute(db.text("DELETE FROM post_fts"))
        db.session.commit()
    except Exception:  # noqa: BLE001  清空失败必须吞掉并降级返回，绝不外抛：rebuild 是维护动作，抛异常只会让调用方（启动/管理接口）整条崩掉
        db.session.rollback()
        return {"ok": False, "reason": "clear-failed"}
    kept = 0
    # 按 id 分页取，不 `yield_per`：流式游标尚未读完就在同一连接上写 post_fts，
    # SQLite/DBAPI 下会重置游标；也不 `Post.query.all()`：正文全文进内存会吃掉数百 MB。
    batch = 50
    last_id = 0
    while True:
        rows = (Post.query.filter(Post.id > last_id)
                .order_by(Post.id).limit(batch).all())
        if not rows:
            break
        last_id = rows[-1].id
        for p in rows:
            if not _indexable(p):
                continue
            _insert(p)
            kept += 1
        db.session.expunge_all()
    db.session.commit()
    return {"ok": True, "indexed": kept}


def sync_post(post):
    """新增 / 更新文章后同步 FTS 索引（不可对外露出的内容不进索引）。"""
    if not available():
        return
    try:
        db.session.execute(db.text("DELETE FROM post_fts WHERE rowid=:rid"), {"rid": post.id})
        if _indexable(post):
            _insert(post)
        db.session.commit()
    except Exception:
        db.session.rollback()


def sync_post_quiet(post):
    """`sync_post()` 的免抛别名，供「改变可见性」的写路径收尾统一调用。

    这些站点散布在请求处理器、后台定时线程与 SSR 表单里，任何一处漏调，文章就会
    **永久**搜不到（`ensure()` 只在索引表为空时回填，不会自愈）。

    `sync_post()` 自身已 `except Exception: db.session.rollback()` 不会外抛，
    故此处无需再包一层 `try/except/pass`（那既冗余又会触发 SIM105）。
    """
    sync_post(post)


def delete_post(post_id):
    """删除文章后清理 FTS 索引。"""
    if not available():
        return
    try:
        db.session.execute(db.text("DELETE FROM post_fts WHERE rowid=:rid"), {"rid": post_id})
        db.session.commit()
    except Exception:
        db.session.rollback()


def escape_fts_query(q):
    """转义 FTS5 MATCH 查询中的特殊字符，防止用户输入语法错误 / 查询注入。

    FTS5 把 " * : - ( ) + ^ / < > ~ 等视为语法符号；用户直接输入会导致
    sqlite3 抛出语法错误（OperationalError），进而 search() 返回 None 回退到 LIKE。
    处理方式：按空白切分为词组，每个词组用双引号包裹成对短语，词组内双引号转义为 ""。
    这样所有特殊字符都被当作字面量，且中文 / 多词搜索语义基本不变（空格=AND）。
    """
    if not q:
        return ""
    terms = []
    for raw in q.split():
        if not raw:
            continue
        # 双引号内部转义：连续两个双引号
        safe = raw.replace('"', '""')
        terms.append('"%s"' % safe)
    return " ".join(terms)


def search(q, limit=30):
    """全文搜索：FTS5 命中返回 post id 列表（按相关度），失败返回 None（调用方回退）。"""
    if not available() or not q:
        return None
    q_escaped = escape_fts_query(q)
    if not q_escaped:
        return None
    try:
        rows = db.session.execute(db.text(
            "SELECT rowid FROM post_fts WHERE post_fts MATCH :q ORDER BY rank LIMIT :lim"
        ), {"q": q_escaped, "lim": limit}).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return None
