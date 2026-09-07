"""标签治理回归测试（v3.15.0）。

守护四件事：
1) 输入拆分兼容中英文逗号/顿号/分号，单篇去重；
2) 大小写/空白变体不再新建重复标签（复用同一行）；
3) 文章保存后自动清理 0 使用标签（不越积越多）；
4) 历史遗留的重复标签可被 merge_duplicate_tags 一键收敛。

运行：仓库根目录 `python -m pytest tests/test_tags.py -q`
注意：测试库为仓库内持久化的 myblog/data/blog.db（gitignored），可能与真实数据共存，
故标签名一律用随机 token 隔离，用例 finally 按 token 清理自建数据。
"""
import uuid

from models import db, Post, Tag, PostTag
from utils import normalize_tag_key, split_tag_input
from admin._helpers import _sync_tags, cleanup_orphan_tags, merge_duplicate_tags, create_post_core


def _tok():
    return uuid.uuid4().hex[:10]


def _cleanup_token(token):
    """删除名字里含 token 的标签 + slug 含 token 的自建文章（幂等、健壮）。"""
    db.session.rollback()  # 清掉可能的残留失败事务
    for p in Post.query.filter(Post.slug.like(f"%{token}%")).all():
        PostTag.query.filter_by(post_id=p.id).delete()
        db.session.delete(p)
    for t in Tag.query.all():
        if token in (t.name or ""):
            for p in list(t.posts):
                p.tags.remove(t)
            db.session.delete(t)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def test_normalize_and_split():
    assert normalize_tag_key("AI") == normalize_tag_key("ai") == normalize_tag_key(" AI ")
    assert normalize_tag_key("AI 大模型") == normalize_tag_key("AI大模型")
    parts = split_tag_input("生活, 技术，AI、AI，游戏；音乐\n技术")
    keys = [normalize_tag_key(p) for p in parts]
    assert len(keys) == len(set(keys))
    assert "生活" in parts and "技术" in parts and "AI" in parts


def test_sync_tags_dedups_case_and_dups(app):
    tk = _tok()
    tag_a = "Zz" + tk          # 随机名，保证不与真实数据撞
    with app.app_context():
        pid = None
        try:
            p = Post(title="t-" + tk, slug="p-" + tk, content="正文", published=False)
            db.session.add(p)
            db.session.flush()
            pid = p.id
            # 大小写变体 + 中文分隔 + 同义重复
            _sync_tags(p, f"{tag_a}， {tag_a.lower()}、{tag_a.upper()}, 生活")
            db.session.commit()
            assert len(p.tags) == 2, [t.name for t in p.tags]
            # token 族只允许存在一行标签
            n = Tag.query.filter(Tag.name.contains(tk)).count()
            assert n == 1
        finally:
            _cleanup_token(tk)


def test_create_post_core_reuses_tag_and_cleans_orphan(app):
    tk = _tok()
    tag_a = "Aa" + tk
    orphan_tag = "orphan" + tk
    with app.app_context():
        try:
            p1 = create_post_core(title="tg1-" + tk, content="a",
                                  tags=f"{tag_a}, {orphan_tag}", published=False)
            # 第二次用不同大小写，应复用而不是新建
            p2 = create_post_core(title="tg2-" + tk, content="b", tags=tag_a.lower(),
                                  published=False)
            rows = Tag.query.filter(Tag.name.contains(tk)).all()
            names = [r.name for r in rows]
            # token 族只出现两个标签：tag_a 族 1 个 + orphan 1 个
            assert sum(1 for x in names if tag_a.casefold() == x.casefold()) == 1
            assert len(p2.tags) == 1
            # 删掉 p1 后清理：orphan_tag 变为 0 使用，应被清掉
            PostTag.query.filter_by(post_id=p1.id).delete()
            db.session.delete(p1)
            db.session.commit()
            cleanup_orphan_tags()
            left = [t.name for t in Tag.query.all() if orphan_tag in (t.name or "")]
            assert left == []
        finally:
            _cleanup_token(tk)


def test_merge_duplicate_tags_legacy_mess(app):
    """模拟历史遗留：同名大小写变体两行各挂一篇文章，merge 后收敛为一行且文章不丢。"""
    tk = _tok()
    na = "Lg" + tk
    nb = "lg" + tk
    with app.app_context():
        try:
            p1 = Post(title="m1-" + tk, slug="m1-" + tk, content="x", published=False)
            p2 = Post(title="m2-" + tk, slug="m2-" + tk, content="y", published=False)
            db.session.add_all([p1, p2])
            db.session.flush()
            ta = Tag(name=na, slug="s" + na)
            tb = Tag(name=nb, slug="s" + nb)
            db.session.add_all([ta, tb])
            db.session.flush()
            p1.tags = [ta]
            p2.tags = [tb]
            db.session.commit()
            merged = merge_duplicate_tags()
            assert merged >= 1
            rows = Tag.query.filter(Tag.name.contains(tk)).all()
            assert len(rows) == 1
            keep = rows[0]
            assert set(x.id for x in keep.posts) == {p1.id, p2.id}
        finally:
            _cleanup_token(tk)
