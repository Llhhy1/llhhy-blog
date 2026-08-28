"""正文渲染缓存 + SQLite WAL 冒烟测试（v3.9.1）。

覆盖：
1. 文章详情接口返回的 html 与直接渲染一致，并把结果写入 post.content_html；
2. 第二次请求命中缓存，不再调用 render_markdown（核心性能诉求）；
3. 正文一改指纹即变，缓存自动失效并重新渲染；
4. 缓存列迁移幂等（旧库升级可重复执行）；
5. SQLite 连接已启用 WAL + busy_timeout；
6. 备份用一致性快照（WAL 安全），恢复后清理 -wal/-shm 残留。

运行：仓库根目录 `python -m pytest tests/ -q`
"""
import os
import sqlite3
import tempfile

import pytest


def _make_post(app, slug, content, title="测试文章"):
    """在应用上下文里建一篇已发布文章，返回其 id。"""
    from models import db, Post
    p = Post(title=title, slug=slug, summary="摘要", content=content,
             published=True)
    db.session.add(p)
    db.session.commit()
    return p.id


def _del_post(app, post_id):
    from models import db, Post
    p = db.session.get(Post, post_id)
    if p:
        db.session.delete(p)
        db.session.commit()


def test_detail_html_matches_and_cached(app):
    """首次访问：返回正确 HTML，并把渲染结果写入 content_html/content_hash。"""
    from models import db, Post
    from utils import render_markdown, content_digest
    with app.app_context():
        pid = _make_post(app, "v391-cache-a", "# 标题\n\n正文 **加粗**")
        try:
            client = app.test_client()
            r = client.get("/api/post/v391-cache-a")
            assert r.status_code == 200
            html = r.get_json()["html"]
            assert "<h1>标题</h1>" in html and "<strong>加粗</strong>" in html

            p = db.session.get(Post, pid)
            expect = render_markdown(p.content)
            assert p.content_html == expect          # 缓存已落库
            assert p.content_hash == content_digest(p.content, p.content_html)
            assert html == expect                    # 接口返回的正是缓存内容
        finally:
            _del_post(app, pid)


def test_tampered_cache_self_heals(app):
    """缓存列被外部改坏（手工改库/回档错乱）→ 指纹不匹配 → 自动重新渲染自愈。"""
    from models import db, Post
    with app.app_context():
        pid = _make_post(app, "v391-cache-d", "# 原文")
        try:
            client = app.test_client()
            good = client.get("/api/post/v391-cache-d").get_json()["html"]

            p = db.session.get(Post, pid)
            p.content_html = "<p>被改坏的缓存</p>"   # 只改 HTML，不动指纹
            db.session.commit()

            healed = client.get("/api/post/v391-cache-d").get_json()["html"]
            assert healed == good                     # 自愈：重新渲染出正确结果
            assert "被改坏" not in healed
        finally:
            _del_post(app, pid)


def test_second_visit_hits_cache(app, monkeypatch):
    """第二次访问同一篇文章不应再触发 render_markdown（缓存命中）。"""
    import utils
    calls = {"n": 0}
    origin = utils.render_markdown

    def spy(content):
        calls["n"] += 1
        return origin(content)

    monkeypatch.setattr(utils, "render_markdown", spy)
    with app.app_context():
        pid = _make_post(app, "v391-cache-b", "## 二\n\n内容")
        try:
            client = app.test_client()
            r1 = client.get("/api/post/v391-cache-b")
            assert r1.status_code == 200
            after_first = calls["n"]
            assert after_first >= 1

            r2 = client.get("/api/post/v391-cache-b")
            assert r2.status_code == 200
            assert calls["n"] == after_first          # 命中缓存：渲染次数不再增加
            assert r1.get_json()["html"] == r2.get_json()["html"]
        finally:
            _del_post(app, pid)


def test_cache_invalidated_when_content_changes(app):
    """改正文后指纹变化 → 缓存自动失效，接口返回新渲染结果（无需手工清缓存）。"""
    from models import db, Post
    with app.app_context():
        pid = _make_post(app, "v391-cache-c", "# 旧内容")
        try:
            client = app.test_client()
            old_html = client.get("/api/post/v391-cache-c").get_json()["html"]
            assert "旧内容" in old_html

            p = db.session.get(Post, pid)
            p.content = "# 新内容"
            db.session.commit()

            new_html = client.get("/api/post/v391-cache-c").get_json()["html"]
            assert "新内容" in new_html and "旧内容" not in new_html
            assert new_html != old_html
        finally:
            _del_post(app, pid)


def test_cache_columns_migration_idempotent(app):
    """_migrate_post_table 可重复执行（旧库升级加列，已有则不重复）。"""
    from sqlalchemy import inspect
    from app import _migrate_post_table
    with app.app_context():
        _migrate_post_table()
        _migrate_post_table()  # 再跑一次不应报错
        cols = [c["name"] for c in inspect(db_engine()).get_columns("post")]
    assert "content_html" in cols and "content_hash" in cols


def db_engine():
    from models import db
    return db.engine


def test_sqlite_wal_pragmas(app):
    """SQLite 连接应处于 WAL 模式且设置了 busy_timeout（内存库自动跳过）。"""
    from sqlalchemy import text
    from models import db
    with app.app_context():
        url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" not in url or ":memory:" in url:
            pytest.skip("非文件型 SQLite，跳过 WAL 断言")
        mode = db.session.execute(text("PRAGMA journal_mode")).scalar()
        timeout = db.session.execute(text("PRAGMA busy_timeout")).scalar()
    assert (mode or "").lower() == "wal"
    assert timeout == 5000


def test_backup_snapshot_is_consistent(app):
    """backup.snapshot_db 产出的副本是自包含且完整可读的（不会丢 WAL 数据）。"""
    import backup as backup_mod
    from models import db
    with app.app_context():
        db_path = db.engine.url.database
        tmp = os.path.join(tempfile.mkdtemp(prefix="snap_"), "blog.db")
        try:
            backup_mod.snapshot_db(db_path, tmp)
            assert os.path.exists(tmp)
            con = sqlite3.connect(tmp)
            try:
                assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                # 快照里应能看到当前文章表结构（说明复制的是完整逻辑库）
                tables = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                assert "post" in tables
            finally:
                con.close()
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                os.rmdir(os.path.dirname(tmp))
            except Exception:
                pass


def test_drop_wal_sidecars():
    """恢复备份时清掉 -wal/-shm，避免旧 WAL 回放新库导致损坏。"""
    import backup as backup_mod
    d = tempfile.mkdtemp(prefix="wal_")
    db_path = os.path.join(d, "blog.db")
    open(db_path, "wb").close()
    for suffix in ("-wal", "-shm"):
        open(db_path + suffix, "wb").close()
    removed = backup_mod.drop_wal_sidecars(db_path)
    assert sorted(removed) == ["-shm", "-wal"]
    assert os.path.exists(db_path)            # 主库本身不受影响
    assert not os.path.exists(db_path + "-wal")
    assert not os.path.exists(db_path + "-shm")
