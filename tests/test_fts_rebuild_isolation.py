"""`fts.rebuild_all()` 不得影响调用方持有的 ORM 实例（v3.25.0）。

**为什么这条要单独守**：`rebuild_all()` 原先每批末尾 `db.session.expunge_all()`
来控制内存。`expunge_all()` 是**整会话级**操作，会把调用方自己 `get()` 出来、
正打算接着用的 Post 一并摘出会话 → 后续访问即 detached。生产调用方
（`tools/rebuild_fts.py`）不持实例，所以这问题在生产一直"看不见"，只在测试里
咬人（`test_setting_governance` 造的 Post 被 `test_visibility_leaks` 的 rebuild
顺手摘走，症状是 teardown 莫名变慢、标量取值时飘 DetachedInstanceError）。

修法不是「换成只 expunge 自己那批」——那仍然要靠 id 去猜哪些是自己的；改成
**Core `select()` 取标量行**，压根不产生 ORM 实体，会话里没有需要摘的东西。
所以守卫同时断言两件事：① 行为上不牵连调用方；② 结构上不再出现 `expunge*`。
"""
import pytest
import sqlalchemy
from sqlalchemy import inspect

from models import db, Post, User, ROLE_ADMIN


def _r():
    import secrets
    return secrets.token_hex(4)


def _seed(app, n=3):
    """建 n 篇文章，返回 (author, [Post...])，全部已 commit。"""
    u = User(username="ftsiso-author-" + _r(), email="ftsiso@test.local", role=ROLE_ADMIN)
    u.set_password("test-pass-123")
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    made = []
    for i in range(n):
        p = Post(title="IsoWidget%s-%d" % (_r(), i), slug="iso-%s-%d" % (_r(), i),
                 summary="sum %d" % i, content="ISO-BODY-%d" % i,
                 author_id=u.id, published=True)
        db.session.add(p)
        made.append(p)
    db.session.commit()
    return u, made


# ---------- 行为：调用方实例不受牵连 ----------

def test_rebuild_all_keeps_caller_instance_attached(app):
    """rebuild 前后，调用方持有的 Post 必须始终 attached。"""
    import fts
    with app.app_context():
        _u, made = _seed(app)
        held = db.session.get(Post, made[0].id)
        assert held in db.session, "前置条件：get 出来的实例本应在会话里"

        res = fts.rebuild_all()
        assert res["ok"] is True

        assert held in db.session, (
            "rebuild_all() 把调用方持有的实例摘出了会话 —— 这会让调用方后续访问 "
            "直接 DetachedInstanceError。expunge_all() 是整会话级操作，不能用来做批量内存回收。"
        )
        # 未加载的列仍可懒加载（detached 的对象这里会直接抛错）
        assert held.views is not None
        # 已加载的列不受影响
        assert held.title == made[0].title


def test_rebuild_all_does_not_grow_identity_map(app):
    """核心不变量：rebuild **不得往会话里塞实体**。

    这条比「不 detach 调用方」更强也更准：只要没有新实体进会话，就不可能摘走别人的。
    上一版（ORM 实体 + expunge_all）虽然也不留垃圾，但每批结束时会把会话清空——
    调用方在 rebuild 之前拿到的一切都被殃及。
    """
    import fts
    with app.app_context():
        _u, made = _seed(app, n=5)
        # 标量先取出：`session.remove()` 后 `made` 里的实例已 detached，
        # 而 commit 之后它们的列处于 expired 状态，再取属性会触发刷新失败。
        ids = [p.id for p in made]
        db.session.remove()          # 清掉播种带来的实体，从干净会话量起
        sentinel = db.session.get(Post, ids[0])
        before = len(db.session().identity_map)

        assert fts.rebuild_all()["ok"] is True

        after = len(db.session().identity_map)
        assert after == before, (
            "rebuild_all() 让 identity_map 从 %d 涨到 %d —— 说明仍在产生 ORM 实体，"
            "那些实体只能靠 expunge 回收，而 expunge 会牵连调用方。改用 Core select 取标量行。"
            % (before, after)
        )
        assert sentinel in db.session
        assert sentinel.id == ids[0]


def test_rebuild_all_still_indexes_and_purges(app):
    """改实现不能改行为：可见文章进索引、隐私文章被清掉，且不残留上一轮脏行。"""
    import datetime
    import fts
    with app.app_context():
        u = User(username="ftspurge-" + _r(), email="ftspurge@test.local", role=ROLE_ADMIN)
        u.set_password("test-pass-123")
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        ok = Post(title="PurgeOk" + _r(), slug="purge-ok-" + _r(), summary="s",
                  content="PURGE-OK-BODY", author_id=u.id, published=True)
        priv = Post(title="PurgePriv" + _r(), slug="purge-priv-" + _r(), summary="s",
                    content="PURGE-PRIV-BODY", author_id=u.id, published=True, is_private=True)
        trash = Post(title="PurgeTrash" + _r(), slug="purge-trash-" + _r(), summary="s",
                     content="PURGE-TRASH-BODY", author_id=u.id, published=True, in_trash=True)
        future = Post(title="PurgeFuture" + _r(), slug="purge-future-" + _r(), summary="s",
                      content="PURGE-FUTURE-BODY", author_id=u.id, published=True,
                      scheduled_at=datetime.datetime.utcnow() + datetime.timedelta(days=2))
        db.session.add_all([ok, priv, trash, future])
        db.session.commit()
        # 塞一条脏行：上一版索引闸门放进来的隐私正文
        db.session.execute(db.text(
            "INSERT INTO post_fts (rowid, title, summary, content, slug) "
            "VALUES (:rid,:t,:s,:c,:sl)"),
            {"rid": priv.id, "t": "stale", "s": "s", "c": "PURGE-PRIV-BODY", "sl": "stale"})
        db.session.commit()

        res = fts.rebuild_all()
        assert res["ok"] is True
        assert res["indexed"] >= 1, "可见文章必须被索引，否则本用例是假绿"

        rows = {r[0] for r in db.session.execute(db.text("SELECT rowid FROM post_fts")).all()}
        assert ok.id in rows, "可见文章应进索引"
        assert rows.isdisjoint({priv.id, trash.id, future.id}), \
            "隐私 / 回收站 / 定时未到的文章不得留在索引里（脏行必须被清掉）"
        body = " ".join(str(r[0]) for r in db.session.execute(
            db.text("SELECT content FROM post_fts")).all())
        assert "PURGE-PRIV-BODY" not in body, "隐私正文仍躺在索引里"


def test_rebuild_all_handles_more_rows_than_one_batch(app):
    """分页循环必须能跨批（batch=50，用 55 篇验证多走一轮 + 收尾批次）。"""
    import fts
    with app.app_context():
        _u, made = _seed(app, n=55)
        res = fts.rebuild_all()
        assert res["ok"] is True
        rows = {r[0] for r in db.session.execute(db.text("SELECT rowid FROM post_fts")).all()}
        missing = [p.id for p in made if p.id not in rows]
        assert not missing, "跨批漏索引 %d 篇（分页 last_id 推进有问题）" % len(missing)


# ---------- 结构：expunge 不得复活 ----------

def test_fts_module_never_expunges_the_session(app):
    """静态防复发：`fts.py` 内不得出现任何 `expunge*` 调用。

    收紧到「整个模块」而非只查 `rebuild_all()`：内存回收是这一层的通用诱惑，
    换个函数名再犯一次同样会牵连调用方。`fts.py` 现在不产生 ORM 实体，本来就不需要它。
    """
    import ast
    import pathlib
    src_path = pathlib.Path(__file__).resolve().parent.parent / "myblog" / "fts.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("expunge"):
            offenders.append("line %d: .%s" % (node.lineno, node.attr))
    assert not offenders, (
        "fts.py 不得摘会话对象 %s —— 它会连带摘走调用方持有的实例。"
        "需要控内存就改用 Core select 取标量行（见 rebuild_all 注释）。" % offenders
    )


def test_rebuild_all_leaves_no_detached_instance_error(app):
    """端到端口径：调用方在 rebuild 前后读写同一实例，全程不得抛 DetachedInstanceError。"""
    import fts
    with app.app_context():
        _u, made = _seed(app, n=2)
        held = db.session.get(Post, made[0].id)
        held.views = 7
        db.session.commit()
        # 未加载的列：commit 后 expired，重建后访问才是真正的懒加载检验
        state = inspect(held)
        fts.rebuild_all()
        try:
            assert state.persistent, "rebuild 后实例应仍是 persistent（attached）"
            assert held.content == made[0].content
            assert held.views == 7
        except sqlalchemy.orm.exc.DetachedInstanceError as e:  # pragma: no cover
            pytest.fail("rebuild_all() 导致调用方实例 detached: %s" % e)
        db.session.rollback()
