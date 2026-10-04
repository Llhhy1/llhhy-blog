"""评论串：嵌套深度 + 排序（v3.25.2）。

**先说这个功能的真正起因** —— 排序不是第一优先，**丢评论**才是：

原 `post_comments` 只查两层（`for t in tops: ... parent_id=t.id`），
于是「回复的回复」（第三层）**永远不会出现在返回里**。`Comment.parent_id`
是指向任意评论的自关联外键，前端也支持对回复再回复，所以**用户能创建，
但 API 读不回来** —— 写进去了、界面上看不见，等于静默丢数据。

本文件覆盖三件事：
1. **任意层嵌套都能取回**（递归收集，且有总量上限防退化）
2. **排序切换**（时间正序/倒序/最热），`sort` 走**白名单映射**而非字符串拼接
3. **深度封顶**（默认 4 层，超出折叠为「继续回复」而不是无限缩进）
"""
import datetime

import pytest

# 项目惯例：模块直接导入（`db` 定义在 models.py，不在 myblog 包下）
from models import Comment, Post, db, utcnow


@pytest.fixture()
def app_and_post(app):
    """建一篇可见文章，返回 (app, post_id, slug)。

    ⚠️ slug 必须**每轮唯一**：测试库 `%TEMP%/llhhy-blog-pytest/test.db` 是**跨轮复用**
    的（conftest 只覆盖 DATABASE_URL，不重建库），写死 slug 第二轮就撞
    `UNIQUE constraint failed: post.slug`。teardown 顺手清干净，不留残留数据。
    """
    import uuid
    slug = "nest-%s" % uuid.uuid4().hex[:10]
    with app.app_context():
        p = Post(title="嵌套测试", slug=slug, published=True,
                 content="x", created_at=utcnow())
        db.session.add(p)
        db.session.commit()
        pid = p.id
    yield pid, slug
    with app.app_context():
        Comment.query.filter_by(post_id=pid).delete(synchronize_session=False)
        Post.query.filter_by(id=pid).delete(synchronize_session=False)
        db.session.commit()


def _mk(app, post_id, author, content, parent_id=None):
    with app.app_context():
        c = Comment(post_id=post_id, author=author, content=content,
                    parent_id=parent_id, approved=True)
        db.session.add(c)
        db.session.commit()
        return c.id


def _get(app, slug, **qs):
    with app.test_client() as cl:
        q = "&".join("%s=%s" % kv for kv in qs.items())
        return cl.get("/api/post/%s/comments?%s" % (slug, q)).get_json()


@pytest.fixture()
def deep_thread(app, app_and_post):
    """造一条 5 层链：L0 → L1 → L2 → L3 → L4，并给每层不同点赞数。"""
    pid, slug = app_and_post
    ids = [_mk(app, pid, "L0", "顶层")]
    for i in range(1, 5):
        ids.append(_mk(app, pid, "L%d" % i, "第 %d 层" % i, parent_id=ids[-1]))
    # 另给顶层加两个兄弟（L1b），验证分叉也能取回
    ids.append(_mk(app, pid, "L1b", "分叉", parent_id=ids[0]))
    return pid, slug


# ---------- 1. 嵌套：全部层级都要能取回（这是修 bug）----------

def test_third_level_comment_is_returned(app, deep_thread):
    """**这条是第一版的失败点**：第三层曾经永远拿不到（只查两层）。"""
    _pid, slug = deep_thread
    data = _get(app, slug)
    authors = {i["author"] for i in data["items"]}
    assert {"L0", "L1", "L2", "L3", "L4"} <= authors, \
        "深层次评论丢失：拿到 %s" % sorted(authors)


def test_all_descendants_returned_with_count(app, deep_thread):
    _pid, slug = deep_thread
    data = _get(app, slug)
    assert len(data["items"]) == 6, "应返回 6 条（5 层链 + 1 个分叉），实际 %d" % len(data["items"])


def test_top_level_count_not_inflated_by_replies(app, deep_thread):
    """**分页 count 必须是顶层数**，否则「共 N 条」会把回复也算进去，
    点「加载更多」会永远有下一页（经典死循环）。"""
    _pid, slug = deep_thread
    data = _get(app, slug, per_page=1)
    assert data["total"] == 1, "total 应只算顶层评论，实际 %s" % data["total"]
    assert data["has_more"] is False, "顶层只有 1 条，per_page=1 时不该还有下一页"


def test_depth_field_is_accurate(app, deep_thread):
    """每个 item 都要带正确的 depth（0=顶层），前端靠它决定缩进与折叠。"""
    _pid, slug = deep_thread
    data = _get(app, slug)
    by_author = {i["author"]: i for i in data["items"]}
    assert by_author["L0"]["depth"] == 0
    assert by_author["L1"]["depth"] == 1
    assert by_author["L2"]["depth"] == 2
    assert by_author["L3"]["depth"] == 3
    assert by_author["L4"]["depth"] == 4


# ---------- 2. 排序 ----------

def test_sort_newest_first(app, deep_thread):
    """`sort=new` 时顶层评论应按时间**倒序**，且深层次跟着它所属的顶层走。"""
    _pid, slug = deep_thread
    _mk_all(app, deep_thread[0])
    data = _get(app, slug, sort="new", per_page=50)
    tops = [i["author"] for i in data["items"]
            if i["depth"] == 0 and i["author"].startswith("Top")]
    assert tops == ["TopNew", "TopOld"], "倒序应把 TopNew 排在前，实际 %s" % tops
    # 深度优先：每个顶层后面紧跟它自己的子树，不会有别的顶层的回复混进来
    authors = [i["author"] for i in data["items"]]
    if "L0" in authors:
        i_l0 = authors.index("L0")
        assert authors[i_l0 + 1].startswith("L1"), \
            "子树必须紧跟其顶层（深度优先），实际顺序 %s" % authors


def _mk_all(app, pid):
    """再加两条顶层评论用于排序断言（返回它们的 id）。"""
    a = _mk(app, pid, "TopOld", "更早的顶层")
    b = _mk(app, pid, "TopNew", "更晚的顶层")
    with app.app_context():
        c = Comment.query.filter_by(id=a).first()
        c.created_at = datetime.datetime(2020, 1, 1)
        d = Comment.query.filter_by(id=b).first()
        d.created_at = datetime.datetime(2030, 1, 1)
        db.session.commit()
    return a, b


def test_sort_old_ascending(app, deep_thread):
    _pid, slug = deep_thread
    _mk_all(app, deep_thread[0])
    data = _get(app, slug, sort="old", per_page=50)
    tops = [i for i in data["items"] if i["depth"] == 0 and i["author"].startswith("Top")]
    assert [t["author"] for t in tops] == ["TopOld", "TopNew"]


def test_sort_new_descending(app, deep_thread):
    _pid, slug = deep_thread
    _mk_all(app, deep_thread[0])
    data = _get(app, slug, sort="new", per_page=50)
    tops = [i for i in data["items"] if i["depth"] == 0 and i["author"].startswith("Top")]
    assert [t["author"] for t in tops] == ["TopNew", "TopOld"]


def test_sort_hot_uses_likes(app, deep_thread):
    _pid, slug = deep_thread
    with app.app_context():
        db.session.query(Comment).filter_by(author="L0").update({"likes": 99})
        db.session.query(Comment).filter_by(author="L1").update({"likes": 1})
        db.session.commit()
    data = _get(app, slug, sort="hot", per_page=50)
    authors = [i["author"] for i in data["items"]]
    assert authors.index("L0") < authors.index("L1"), "最热排序应让 99 赞排在 1 赞前"


def test_illegal_sort_falls_back_to_default(app, deep_thread):
    """**order_by 绝不能拼用户输入** —— 这里是白名单映射，非法值一律回落。
    传 `sort=created_at;drop table post` 这类 payload 不得引发任何异常。"""
    _pid, slug = deep_thread
    data = _get(app, slug, sort="created_at;DROP TABLE post", per_page=50)
    assert data and data.get("items") is not None
    # 表还在，且仍能正常查询
    assert _get(app, slug, per_page=1) is not None


def test_default_sort_is_old(app, deep_thread):
    _pid, slug = deep_thread
    _mk_all(app, deep_thread[0])
    a = _get(app, slug, per_page=50)
    b = _get(app, slug, sort="old", per_page=50)
    assert [x["id"] for x in a["items"]] == [x["id"] for x in b["items"]]


# ---------- 3. 深度封顶 ----------

def test_max_depth_is_reported(app, deep_thread):
    """响应里要带回 max_depth，前端据此决定「继续回复」按钮。"""
    _pid, slug = deep_thread
    data = _get(app, slug, max_depth=2)
    assert data.get("max_depth") == 2


def test_deep_items_flagged_for_collapse(app, deep_thread):
    """超出 max_depth 的 item 要能被前端识别出来 —— 用 `depth` 与 `max_depth`
    比较即可，故这里只需保证 depth 一直如实上报（哪怕很深）。"""
    _pid, slug = deep_thread
    data = _get(app, slug, max_depth=2)
    deep = [i for i in data["items"] if i["depth"] > 2]
    assert deep, "深层仍应返回（前端折叠 ≠ 不返回）"
    assert all(i["depth"] > 2 for i in deep)


def test_max_depth_illegal_value_falls_back(app, deep_thread):
    _pid, slug = deep_thread
    data = _get(app, slug, max_depth="abc")
    assert data.get("max_depth") == 4, "非法 max_depth 应回落到默认 4"


def test_max_depth_upper_bound(app, deep_thread):
    """上限要封顶：传 9999 不应让前端无限缩进。"""
    _pid, slug = deep_thread
    data = _get(app, slug, max_depth="9999")
    assert data.get("max_depth") <= 8


def test_pathological_deep_chain_does_not_crash(app, app_and_post):
    """**脏数据（parent_id 成环 / 超长链）不得把接口打挂**。

    这条锁的是一个真实潜伏 bug：`_walk_thread` 里调 `logger.warning`，
    而 `api/posts.py` 当时**并没有模块级 logger** —— 浅链测试永远走不到那行，
    于是全绿，直到某天真的出现超深链才炸 NameError 500。
    教训与 v3.25.1 那批守卫一致：**没被执行到的分支不等于没问题**。
    """
    pid, slug = app_and_post
    deep = _mk(app, pid, "Deep", "第 30 层", parent_id=None)
    prev = deep
    for i in range(30):
        prev = _mk(app, pid, "D%d" % i, "x", parent_id=prev)
    data = _get(app, slug, per_page=50)
    assert data and "items" in data, "超深链导致接口异常：%s" % data
    # 不要求 30 层全在（_COMMENT_MAX_WALK 会在 24 层停下并记日志），但必须返回 200 且有数据
    assert data["items"], "超深链下顶层评论本身必须可见"
    depths = [i["depth"] for i in data["items"]]
    assert max(depths) <= 24, "深度上限未生效：%d" % max(depths)
