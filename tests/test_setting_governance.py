"""Setting KV 治理（v3.24.0）：UGC 不再塞进设置表。

钉死的不变量：
- 评论表情回应存**评论自己的行**（`Comment.reactions`），setting 表**不再出现** `react_*`；
- AI 摘要/标签存**文章自己的列**（`Post.ai_summary` / `Post.ai_tags`），setting 表不再
  出现 `ai_summary_*` / `ai_tags_*`；
- 前台 API 读到的数据来自新列（行为不变：批量 reactions、摘要 GET）；
- 删到 0 的表情要从 JSON 里去掉（前端据此决定是否高亮）。

背景：setting 表有 6 处 `Setting.query.all()` 全表加载（后台每次渲染的
`inject_globals`、天气默认坐标、后台设置页 ×3、`api/common._settings_map`），
UGC 混在里面会随评论/文章数无限增长并被每次全表捞出。
"""
import json

import pytest

from models import db, Comment, Post, Setting


@pytest.fixture(autouse=True)
def _cleanup(app):
    """每个用例后清掉本文件造的文章与评论。

    conftest 让整场测试共用**同一个**临时库且不清数据；不清的话这些残留的已发布文章
    会被后面的用例（如 test_visibility_leaks 的 `fts.rebuild_all()`）扫到 ——
    `rebuild_all()` 每批结束会 `db.session.expunge_all()`，实例被摘出会话后，
    别的用例再取 `post.id` 就会 DetachedInstanceError。**污染必须清干净。**
    """
    yield
    with app.app_context():
        db.session.execute(db.text(
            "DELETE FROM comment WHERE post_id IN (SELECT id FROM post WHERE slug LIKE 'gov-%')"))
        db.session.execute(db.text("DELETE FROM post WHERE slug LIKE 'gov-%'"))
        db.session.commit()


def _csrf(client):
    return (client.get("/api/csrf").get_json() or {}).get("csrf_token") or ""


def _mk_comment(app, tag):
    """建一篇已发布文章 + 一条已审核评论，返回 comment id。"""
    with app.app_context():
        p = Post(title="gov-" + tag, slug="gov-" + tag, content="正文", published=True)
        db.session.add(p)
        db.session.commit()
        c = Comment(post_id=p.id, author="读者", content="说得对", approved=True)
        db.session.add(c)
        db.session.commit()
        return c.id


def test_reaction_goes_to_comment_row_not_setting(app, client):
    cid = _mk_comment(app, "react")
    tok = _csrf(client)
    r = client.post("/api/comments/%d/reactions" % cid,
                    json={"emoji": "\U0001F44D"},     # 👍
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["counts"] == {"\U0001F44D": 1}

    with app.app_context():
        c = db.session.get(Comment, cid)
        assert json.loads(c.reactions) == {"\U0001F44D": 1}
        # setting 表不应再出现 react_<id>
        assert Setting.query.filter_by(key="react_%d" % cid).first() is None


def test_reaction_remove_drops_zero_entry(app, client):
    cid = _mk_comment(app, "rm")
    tok = _csrf(client)
    client.post("/api/comments/%d/reactions" % cid, json={"emoji": "\U0001F44D"},
                headers={"X-CSRF-Token": tok})
    r = client.post("/api/comments/%d/reactions" % cid,
                    json={"emoji": "\U0001F44D", "action": "remove"},
                    headers={"X-CSRF-Token": tok})
    assert r.get_json()["counts"] == {}
    with app.app_context():
        c = db.session.get(Comment, cid)
        assert json.loads(c.reactions) == {}


def test_reactions_batch_get(app, client):
    c1 = _mk_comment(app, "b1")
    c2 = _mk_comment(app, "b2")
    tok = _csrf(client)
    client.post("/api/comments/%d/reactions" % c1, json={"emoji": "\U0001F602"},
                headers={"X-CSRF-Token": tok})
    d = client.get("/api/comments/reactions?ids=%d,%d" % (c1, c2)).get_json()
    assert d["items"][str(c1)] == {"\U0001F602": 1}
    assert d["items"][str(c2)] == {}          # 无回应 → 空对象，不能漏 key


def test_ai_summary_reads_post_column(app, client):
    """前台摘要接口读的是 Post.ai_summary，且不再往 setting 写。"""
    with app.app_context():
        p = Post(title="AI摘要", slug="gov-ai", content="正文", published=True)
        p.ai_summary = "这是一段摘要"
        p.ai_tags = "AI,摘要"
        db.session.add(p)
        db.session.commit()
        pid = p.id          # ⚠️ 标量必须在 app_context 内取出（退出后 ORM 会 detached）
    try:
        d = client.get("/api/ai/summary/gov-ai").get_json()
        assert d["summary"] == "这是一段摘要"
        assert d["tags"] == "AI,摘要"
        with app.app_context():
            assert Setting.query.filter_by(key="ai_summary_%d" % pid).first() is None
    finally:
        with app.app_context():
            Post.query.filter_by(slug="gov-ai").delete()
            db.session.commit()


def test_setting_table_has_no_ugc_keys_after_operations(app, client):
    """兜底断言：跑完上述写操作后，setting 表里不存在任何 UGC 键。"""
    cid = _mk_comment(app, "noguc")
    tok = _csrf(client)
    client.post("/api/comments/%d/reactions" % cid, json={"emoji": "\U0001F389"},
                headers={"X-CSRF-Token": tok})
    with app.app_context():
        bad = Setting.query.filter(
            Setting.key.like("react\\_%", escape="\\")
            | Setting.key.like("ai\\_summary\\_%", escape="\\")
            | Setting.key.like("ai\\_tags\\_%", escape="\\")
        ).all()
        assert not bad, "setting 表仍残留 UGC 键：%s" % [s.key for s in bad]
