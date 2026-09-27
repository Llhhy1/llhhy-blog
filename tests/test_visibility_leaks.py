"""可见性泄露回归测试（v3.21.2 审计批次 1）。

不变量：**文章对访客是否可见，只能由 `models.visible_posts_query()` 判定一次。**
本仓库已第 5 次在同一处踩坑（v3.18.5 修过 /api/review、/api/ai/summary；本轮又
在 /api/search、/post/<slug>/also-viewed、stats._hot_posts 各发现一份平行实现），
所以这里同时断言「索引里不该有它」和「接口不该说出去」两层——只测接口层的话，
脏行会留在盘上等着下一次漂移把内容带出来。
"""
import datetime
import secrets

from models import db, Post, User, ReadLog, ROLE_ADMIN


def _r():
    return secrets.token_hex(4)


def _mkauthor():
    u = User(username="vis-author-" + _r(), email="vis-a@test.local", role=ROLE_ADMIN)
    u.set_password("test-pass-123")
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _post(author, title, **kw):
    p = Post(title=title, slug=title.lower() + "-" + _r(),
             summary="summary of " + title,
             content="SECRET-BODY-" + title,
             author_id=author.id, published=True)
    for k, v in kw.items():
        setattr(p, k, v)
    db.session.add(p)
    db.session.commit()
    return p


def _seed(app):
    """建 4 篇：正常可见 / 隐私 / 回收站 / 定时未到。

    标题带随机后缀：临时库跨用例共享，固定标题会让搜索用例命中别的用例留下的文章。
    """
    import fts
    uniq = _r()
    titles = {"ok": "AlphaWidget%s" % uniq, "priv": "BetaPrivate%s" % uniq,
              "trash": "GammaTrashed%s" % uniq, "future": "DeltaFuture%s" % uniq}
    with app.app_context():
        a = _mkauthor()
        made = {
            "ok": _post(a, titles["ok"]),
            "priv": _post(a, titles["priv"], is_private=True),
            "trash": _post(a, titles["trash"], in_trash=True),
            "future": _post(a, titles["future"], published=False,
                            scheduled_at=datetime.datetime.utcnow()
                            + datetime.timedelta(days=3)),
        }
        fts.rebuild_all()
        return {"ids": {k: p.id for k, p in made.items()},
                "slugs": {k: p.slug for k, p in made.items()},
                "titles": titles}


def _indexed():
    from flask import current_app  # noqa: F401  保持与其它用例一致的取用习惯
    return {r[0] for r in db.session.execute(
        db.text("SELECT rowid FROM post_fts")).fetchall()}


# ---------- 索引层 ----------

def test_fts_index_excludes_invisible_posts(app):
    """隐私 / 回收站 / 定时未到的文章**不得进 FTS 索引**。

    索引里躺着的是正文全文；查询侧漏判一次就是正文直接外泄，所以闸门放在写入侧。
    """
    s = _seed(app)
    with app.app_context():
        rows = _indexed()
        assert s["ids"]["ok"] in rows, "正常文章应被索引，否则本用例是假绿"
        assert rows.isdisjoint({s["ids"]["priv"], s["ids"]["trash"], s["ids"]["future"]}), \
            "不可对外露出的文章不应出现在索引里"


def test_rebuild_all_purges_dirty_rows(app):
    """只改闸门不清历史脏行等于没修：`ensure()` 仅在表为空时回填，不会自愈。"""
    s = _seed(app)
    import fts
    with app.app_context():
        db.session.execute(db.text(
            "INSERT INTO post_fts (rowid, title, summary, content, slug) "
            "VALUES (:rid,:t,:s,:c,:sl)"),
            {"rid": s["ids"]["priv"], "t": s["titles"]["priv"], "s": "x", "c": "y", "sl": "z"})
        db.session.commit()
        assert fts.rebuild_all()["ok"] is True
        rows = _indexed()
        assert s["ids"]["priv"] not in rows
        assert s["ids"]["ok"] in rows


def test_private_post_removed_from_index_on_toggle(app):
    """改成隐私后 `sync_post()` 要把它摘掉；改回来要能重新入索引（不是单向门）。"""
    import fts
    s = _seed(app)
    with app.app_context():
        p = db.session.get(Post, s["ids"]["ok"])
        p.is_private = True
        db.session.commit()
        fts.sync_post(p)
        assert p.id not in _indexed(), "转为隐私后应从索引中移除"
        p.is_private = False
        db.session.commit()
        fts.sync_post(p)
        assert p.id in _indexed(), "取消隐私后应能重新入索引"


def test_publish_paths_sync_index(app):
    """翻 `published` 的每一条路径都必须同步索引，否则文章**永久**搜不到。

    定时发布线程此前就是漏掉的例子：它由机器触发、没有人工会再点一次「发布」，
    所以漏同步会一直留着，`ensure()` 也不会自愈。
    """
    import fts
    s = _seed(app)
    with app.app_context():
        p = db.session.get(Post, s["ids"]["future"])
        assert p.id not in _indexed()
        p.published = True
        p.scheduled_at = None
        db.session.commit()
        fts.sync_post(p)                    # 各发布路径收尾统一调用的那个函数
        assert p.id in _indexed(), "发布后应进入索引"


# ---------- 接口层 ----------

def test_search_api_does_not_leak_invisible(app, client):
    """`/api/search` 的 FTS 分支不得返回隐私 / 回收站 / 未到时的文章。

    查询词特意用 ASCII 前缀：**中文会落到 LIKE 回退分支**（FTS 未配 CJK 分词），
    那样本用例完全没走到被修的分支，会假绿。故先断言 engine == "fts5"。
    """
    s = _seed(app)
    for kind in ("ok", "priv", "trash", "future"):
        q = s["titles"][kind]
        r = client.get("/api/search?q=" + q)
        body = r.get_json()
        text = r.get_data(as_text=True)
        if kind == "ok":
            assert body["engine"] == "fts5", "前置条件破了：没走 FTS 分支，本用例会假绿"
            assert [i["title"] for i in body["items"]] == [q]
        else:
            assert not body["items"], "%s 不应被匿名搜索命中（engine=%r）" % (kind, body["engine"])
            assert s["slugs"][kind] not in text, "%s 的 slug 经搜索外泄" % kind
        assert "SECRET-BODY-" + q not in text


def test_also_viewed_does_not_leak_private(app, client):
    """「看了又看」的候选来自 `ReadLog.post_id`（任意历史 id），读出时必须按可见性过滤。"""
    s = _seed(app)
    with app.app_context():
        # 同一 IP 先读隐私文章、再读可见文章 → 隐私文章进入共读候选
        db.session.add(ReadLog(post_id=s["ids"]["priv"], ip="9.9.9.9", read_count=9))
        db.session.add(ReadLog(post_id=s["ids"]["ok"], ip="9.9.9.9", read_count=9))
        db.session.commit()
        slug = db.session.get(Post, s["ids"]["ok"]).slug
    txt = client.get("/post/%s/also-viewed" % slug).get_data(as_text=True)
    assert s["titles"]["priv"] not in txt, "隐私文章标题经推荐接口外泄"
    assert s["slugs"]["priv"] not in txt, "隐私文章 slug 经推荐接口外泄"
    assert "SECRET-BODY" not in txt


def test_hot_posts_and_summary_do_not_leak(app, client):
    """`stats._hot_posts()` 裸取 Post 时，隐私文章标题与 slug 会经**未鉴权**的
    `/api/stats/summary` 直接外泄。"""
    s = _seed(app)
    with app.app_context():
        db.session.add(ReadLog(post_id=s["ids"]["priv"], ip="8.8.8.8", read_count=99))
        db.session.commit()
    txt = client.get("/api/stats/summary").get_data(as_text=True)
    assert s["titles"]["priv"] not in txt
    assert s["slugs"]["priv"] not in txt


# ---------- 防复发（静态） ----------

def test_no_second_visibility_helper():
    """不许再出现第二套「文章可见性」判定。

    删掉 `_is_visible()` 的理由不是它写错了，而是它与 `visible_posts_query()`
    语义漂移（少了 `in_trash` / `is_private`）。同类 helper 每多一个就多一处泄露面，
    所以把「只有一个真相源」变成机器可检查的约束。
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent / "myblog"
    offenders = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel == "models.py":           # visible_posts_query() 的定义处
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\bdef\s+(\w*visible\w*)\s*\(", src):
            offenders.append("%s::%s" % (rel, m.group(1)))
    assert not offenders, (
        "发现重复的可见性判定实现 %r —— 请改用 models.visible_posts_query()，"
        "单篇判定用 visible_posts_query().filter(Post.id == pid).first()" % offenders)
