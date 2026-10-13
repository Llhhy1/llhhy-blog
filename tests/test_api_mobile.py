# -*- coding: utf-8 -*-
"""移动端管理接口（`/api/mobile/*`，v4.3.0）回归测试。

守的是什么
----------
本模块把后台管理能力开成 JSON，**风险面从「有表单的浏览器」变成「任意客户端」**，
所以断言优先级是权限，不是字段好看：

1. **未登录 401、越权 403，且必须是 JSON** —— 不能是 302 登录页（那正是复用
   `admin_required` 会得到的结果，也是本模块自带 `_role()` 的原因）。
2. **提权字段不因走 API 而绕过**：普通用户提交 `is_pinned` / `is_private` /
   `reward_enabled` 一律被服务端忽略（与后台编辑页同规则；后台靠「表单里没有这个勾」
   防绕过，API 没有这层，必须在代码里收紧）。
3. **写接口照样吃 CSRF**（由 `app.py` 全局闸门管，新前缀自动纳入）。
4. **复用后台核心 = 行为一致**：发文/改文/发布/软删/还原/拉黑在 API 与后台两条路上
   落到同一张表、同一套副作用（FTS、审计、定时换算），这里用断言把「同一实现」钉住。
5. **v4.2.0 的访客日志与按 IP 拉黑**在 JSON 侧同样只对管理员/超管开放。
6. **v4.4.0 内容全套（公告/留言/订阅/分类·标签·系列/友链/版本历史/媒体库）**：断言重心是
   三条已确认口径 + 两类静默改数据风险 ——
   PII 分层（邮箱遮敏 vs 超管全量、`unsub_token` 在任何响应文本里都不出现、留言 IP 只给超管、
   审计 detail 不留 PII）、状态类写接口收**显式目标值**（缺字段 400 而不是静默 False、
   重发幂等）、改名回传「旧 slug → 新 slug」的失效提醒、删除的可逆性（媒体被引用先 409、
   必须 `force` 才真删；`../` 穿越打不到 uploads 外的文件）、回滚**只改三个字段**。
   另有两条「网页端新入口真的能提交」（SSR 表单写、JSON 读回同一行）—— 只补 API 不补页面
   在本仓库算缺陷。

7. **本模块自带 autouse 的限流隔离 fixture**：`/api/mobile/*` 写接口按客户端 IP 限流，
   而测试客户端永远是同一个 IP、`utils.net._RATE` 是模块级字典会跨用例累积。限流本身
   由 `test_posts_pagination_v4.py` 专门测。

运行：仓库根目录 `python -m pytest tests/test_api_mobile.py -q`
测试库是 conftest 建的独立临时库；每个用例 finally 清自建数据。
"""
import contextlib
import io
import os
import pytest
import secrets
import uuid
from datetime import timedelta

from models import (AuditLog, Announcement, BotBlock, Category, Comment, FriendLink, Guestbook,
                    LinkApplication, Moment, Notification, Post, PostHistory, RecycleBin, Series,
                    Subscriber, Tag, User, VisitLog, db, ROLE_ADMIN, ROLE_SUPER, ROLE_USER)
from utils import _sign_csrf
from _time import utcnow


def _uid():
    return uuid.uuid4().hex[:10]


def _mkuser(role=ROLE_SUPER):
    u = User(username="mob-" + _uid(), email="mob-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user_id):
    """写会话 user_id 并生成与会话绑定的有效 CSRF token（同 tests 内既有写法）。"""
    raw = secrets.token_hex(24)
    tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = tok
    return tok


def _req(client, method, path, tok=None, payload=None):
    """发一个 JSON 请求：CSRF 走 `X-CSRF-Token` 头（与 SPA 同写法）。"""
    headers = {"X-CSRF-Token": tok} if tok else {}
    return getattr(client, method)(path, json=payload, headers=headers)


def _audit_count(action, target_id=None):
    """审计条数（移动端每个写操作都该留下一条，与后台同级）。"""
    q = AuditLog.query.filter_by(action=action)
    if target_id is not None:
        q = q.filter_by(target_id=target_id)
    return q.count()


def _drop(pids=(), uids=(), cids=(), mids=(), rids=(), ips=(), links=(), note_users=()):
    """按 id 精确清理，绝不整表删除（同一测试库会被多个用例共用）。"""
    RecycleBin.query.filter(RecycleBin.id.in_(list(rids))).delete(synchronize_session=False)
    Post.query.filter(Post.id.in_(list(pids))).delete(synchronize_session=False)
    Comment.query.filter(Comment.id.in_(list(cids))).delete(synchronize_session=False)
    Moment.query.filter(Moment.id.in_(list(mids))).delete(synchronize_session=False)
    LinkApplication.query.filter(LinkApplication.id.in_(list(links))).delete(
        synchronize_session=False)
    if note_users:
        Notification.query.filter(Notification.user_id.in_(list(note_users))).delete(
            synchronize_session=False)
    if ips:
        VisitLog.query.filter(VisitLog.ip.in_(list(ips))).delete(synchronize_session=False)
        BotBlock.query.filter(BotBlock.ip.in_(list(ips))).delete(synchronize_session=False)
    for uid in uids:
        usr = db.session.get(User, uid)
        if usr:
            db.session.delete(usr)
    db.session.commit()


@pytest.fixture(autouse=True)
def _isolate_rate_limit():
    """每个用例前后清空内存限流计数（同 `test_oauth.py` / `test_twofa.py` 的做法）。

    `/api/mobile/*` 的写接口全按客户端 IP 限流，而测试客户端永远是同一个 IP，`_RATE`
    又是 `utils.net` 的**模块级**字典、整个会话累积 —— 累积到 20 次发文就会出现
    「第 21 次返回 429、用例拿到 None 去下标」这种与业务无关的红。限流本身由
    `test_posts_pagination_v4.py` 专门测，这里按用例隔离，不互相踩计数。
    """
    from utils.net import _RATE
    _RATE.clear()
    yield
    _RATE.clear()


# ---------------------------------------------------------------- 权限闸门


def test_未登录一律_401_且返回_json_而非登录页(app, client):
    """这条直接验证「不能复用 admin_required」：后台装饰器是 302 跳 /login，
    客户端拿到一页 HTML 就无法区分「没登录」与「被重定向」。"""
    for path in ("/api/mobile/overview", "/api/mobile/posts", "/api/mobile/comments",
                 "/api/mobile/visit-logs", "/api/mobile/stats", "/api/mobile/blocked",
                 "/api/mobile/trash", "/api/mobile/notifications"):
        r = client.get(path)
        assert r.status_code == 401, (path, r.status_code)
        assert "error" in (r.get_json() or {}), path
        assert (r.content_type or "").startswith("application/json"), path


def test_普通用户进不了管理只读接口(app, client):
    """普通注册用户（role=user）：能发文，但看不到全站评论 / 访客日志 / 统计 / 回收站。"""
    with app.app_context():
        u = _mkuser(ROLE_USER)
        try:
            _auth(client, u.id)
            for path in ("/api/mobile/overview", "/api/mobile/comments",
                         "/api/mobile/visit-logs", "/api/mobile/stats",
                         "/api/mobile/blocked", "/api/mobile/trash",
                         "/api/mobile/moments", "/api/mobile/link-applications"):
                assert client.get(path).status_code == 403, path
            assert client.get("/api/mobile/posts").status_code == 200
            # 通知是自己的数据，普通用户可读
            assert client.get("/api/mobile/notifications").status_code == 200
        finally:
            _drop(uids=[u.id])


def test_写接口缺_csrf_被全局闸门拦下(app, client):
    """`/api/mobile/*` 不在 CSRF 豁免白名单里，缺 token 一律 403。

    ⚠️ 闸门顺序（`app.py` 里 `csrf_protect` 先于业务视图）：未登录又缺 token 时拿到的是
    **403（CSRF）** 而不是 401。已登录客户端永远先有 token（登录响应里就带），
    所以这条不影响真实流程，只是把顺序钉死，避免将来「顺手豁免 /api/mobile」把
    后台写操作变成无 CSRF 保护的公开面。
    """
    with app.app_context():
        u = _mkuser()
        try:
            _auth(client, u.id)
            r = _req(client, "post", "/api/mobile/moment", tok=None,
                     payload={"content": "没有 token 的动态"})
            assert r.status_code == 403, r.get_json()
            assert "error" in (r.get_json() or {})

            tok = _auth(client, u.id)
            r2 = _req(client, "post", "/api/mobile/moment", tok=tok,
                      payload={"content": "带 token 的动态"})
            assert r2.status_code == 201, r2.get_json()
            mid = r2.get_json()["id"]
            assert db.session.get(Moment, mid).content == "带 token 的动态"
        finally:
            _drop(mids=[mid] if r2.status_code == 201 else [], uids=[u.id])


def test_新前缀不抢既有路由(app, client):
    """注册后规则不冲突：这些路径必须存在（不是 404），未登录才回 401。"""
    for path in ("/api/mobile/overview", "/api/mobile/posts", "/api/mobile/comments",
                 "/api/mobile/visit-logs", "/api/mobile/stats"):
        assert client.get(path).status_code != 404, path


def test_访客日志与封禁清单仅超管可读(app, client):
    """v4.3.1：`/visit-logs` 与 `/blocked` 从「管理员」升到「超管」。

    断言的是**这一条界线**：同为管理员，仍能审评论、看统计、看回收站，但拿不到
    逐条访问日志与封禁 IP 清单。反过来说，如果哪天有人把这两个端点改回 `admin=True`，
    这条会红 —— 那是有意的决定还是手滑，就该被看见。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        super_u = _mkuser(ROLE_SUPER)
        try:
            _auth(client, admin.id)
            assert client.get("/api/mobile/visit-logs").status_code == 403, \
                "访客日志输出 IP 原文，管理员不该能整表翻页抓走"
            assert client.get("/api/mobile/blocked").status_code == 403, "封禁清单同上"
            # 同级管理员的日常工作不受影响
            assert client.get("/api/mobile/comments").status_code == 200
            assert client.get("/api/mobile/stats").status_code == 200
            assert client.get("/api/mobile/overview").status_code == 200
            assert client.get("/api/mobile/trash").status_code == 200

            _auth(client, super_u.id)
            assert client.get("/api/mobile/visit-logs").status_code == 200
            assert client.get("/api/mobile/blocked").status_code == 200
        finally:
            _drop(uids=[admin.id, super_u.id])


# ---------------------------------------------------------------- 发文 / 改文


def test_移动端发文落库并带后台同字段(app, client):
    with app.app_context():
        u = _mkuser()
        pid = None
        try:
            tok = _auth(client, u.id)
            r = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "移动端发的文章", "content": "正文一二三",
                "summary": "摘要", "tags": "生活, 技术", "published": True})
            assert r.status_code == 201, r.get_json()
            pid = r.get_json()["id"]
            p = db.session.get(Post, pid)
            assert p.author_id == u.id and p.published is True
            assert p.slug and p.word_count > 0, "字数统计必须与后台一致（走同一 create_post_core）"
            assert {t.name for t in p.tags} == {"生活", "技术"}
            assert _audit_count("mobile_create", pid) == 1, "移动端写操作必须落审计日志"
        finally:
            _drop(pids=[pid] if pid else [], uids=[u.id])


def test_空标题被拒(app, client):
    with app.app_context():
        u = _mkuser()
        try:
            tok = _auth(client, u.id)
            r = _req(client, "post", "/api/mobile/post", tok=tok,
                     payload={"title": "   ", "content": "x"})
            assert r.status_code == 400
            assert "标题" in (r.get_json() or {}).get("error", "")
        finally:
            _drop(uids=[u.id])


def test_普通用户经_api_提权字段被忽略(app, client):
    """⚠️ 本模块最关键的一条安全断言：越权字段静默失效，而不是「客户端没显示」而已。"""
    with app.app_context():
        u = _mkuser(ROLE_USER)
        pid = None
        try:
            tok = _auth(client, u.id)
            r = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "越权尝试" + _uid(), "content": "x", "published": True,
                "is_pinned": True, "is_private": True, "reward_enabled": True})
            assert r.status_code == 201, r.get_json()
            pid = r.get_json()["id"]
            p = db.session.get(Post, pid)
            assert p.is_pinned is False, "普通用户不得直接置顶"
            assert p.is_private is False, "普通用户不得把文章塞进隐私空间"
            assert p.reward_enabled is False, "普通用户不得自开打赏"
        finally:
            _drop(pids=[pid] if pid else [], uids=[u.id])


def test_编辑别人的文章_403_自己的生效(app, client):
    with app.app_context():
        owner = _mkuser(ROLE_USER)
        other = _mkuser(ROLE_USER)
        title = "我的草稿" + _uid()
        pid = None
        try:
            tok_owner = _auth(client, owner.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok_owner,
                       payload={"title": title, "content": "初稿"}).get_json()["id"]

            tok_other = _auth(client, other.id)
            assert client.get("/api/mobile/post/%d" % pid).status_code == 403
            r2 = _req(client, "put", "/api/mobile/post/%d" % pid, tok=tok_other,
                      payload={"title": "改掉别人的文章", "content": "x"})
            assert r2.status_code == 403
            assert db.session.get(Post, pid).title == title, "越权编辑不得改动任何字段"

            # 作者自己改：必须重新登录取 token —— CSRF token **绑会话**，
            # 上一步 `_auth(client, other.id)` 已把会话里的 token 换掉，拿旧 token 会撞
            # CSRF 403。这一行同时把「换人登录即失效旧 token」钉住（v3.1.6 会话设计）。
            tok_owner2 = _auth(client, owner.id)
            r3 = _req(client, "put", "/api/mobile/post/%d" % pid, tok=tok_owner2,
                      payload={"title": title + "（改）", "content": "改后的正文",
                               "published": True})
            assert r3.status_code == 200, r3.get_json()
            p = db.session.get(Post, pid)
            assert p.title == title + "（改）" and p.published is True
        finally:
            _drop(pids=[pid] if pid else [], uids=[owner.id, other.id])


def test_详情回传未回退的_seo_原值(app, client):
    """移动端编辑要求「取全量再整单回传」，所以详情必须给出库里**未回退**的 SEO 原值。

    `_post_summary` 的 `seo_description` 是「独立描述 **或** 回退到摘要」的展示值；
    而 `update_post_core` 的表单语义是「缺省即清空」。客户端若把展示值原样回传，
    就等于把「本来没填 SEO 描述」悄悄改写成「描述 = 当期摘要」——此后改摘要再也带不动
    描述，且后台编辑页看起来一切正常。这类「接口不难用，但回传一次就静默改数据」的坑，
    只能用一条往返测试钉住。
    """
    with app.app_context():
        u = _mkuser()
        title = "SEO 原值" + _uid()
        summary = "这是摘要" + _uid()
        pid = None
        try:
            tok = _auth(client, u.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": title, "content": "正文", "summary": summary}).get_json()["id"]

            d = client.get("/api/mobile/post/%d" % pid).get_json()
            assert d["seo_description"] == summary, "展示值仍按既有口径回退到摘要"
            assert d["seo_description_raw"] == "", "库里没填就必须是空串"

            r = _req(client, "put", "/api/mobile/post/%d" % pid, tok=tok, payload={
                "title": title, "content": "正文", "summary": summary,
                "seo_description": d["seo_description_raw"]})
            assert r.status_code == 200, r.get_json()
            assert (db.session.get(Post, pid).seo_description or "") == "", \
                "整单回传空原值不得把摘要写成独立描述"

            r2 = _req(client, "put", "/api/mobile/post/%d" % pid, tok=tok, payload={
                "title": title, "content": "正文", "summary": summary,
                "seo_description": "独立描述" + _uid()})
            assert r2.status_code == 200, r2.get_json()
            d2 = client.get("/api/mobile/post/%d" % pid).get_json()
            assert d2["seo_description_raw"].startswith("独立描述")
            assert d2["seo_description"] == d2["seo_description_raw"], "填了之后两个字段应当一致"
        finally:
            _drop(pids=[pid] if pid else [], uids=[u.id])


def test_发布与撤回沿用后台副作用链(app, client):
    """草稿 → 发布 → 撤回。

    断言 `scheduled_at` 被清空：定时文章手动提前发布后若不清空，后台线程到点会再翻一次，
    对已撤回的文章还可能把它重新公开回去。
    """
    with app.app_context():
        u = _mkuser()
        pid = None
        try:
            tok = _auth(client, u.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok,
                       payload={"title": "定时与撤回" + _uid(), "content": "正文"}
                       ).get_json()["id"]
            assert db.session.get(Post, pid).published is False, "不勾 published 应为草稿"

            assert _req(client, "post", "/api/mobile/post/%d/publish" % pid,
                        tok=tok).status_code == 200
            p = db.session.get(Post, pid)
            assert p.published is True and p.scheduled_at is None

            r = _req(client, "post", "/api/mobile/post/%d/unpublish" % pid, tok=tok)
            assert r.status_code == 200, r.get_json()
            assert db.session.get(Post, pid).published is False, "撤回后必须回到草稿"
        finally:
            _drop(pids=[pid] if pid else [], uids=[u.id])


def test_置顶只许超管(app, client):
    with app.app_context():
        normal = _mkuser(ROLE_USER)
        super_u = _mkuser(ROLE_SUPER)
        pid = None
        try:
            tok_normal = _auth(client, normal.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok_normal,
                       payload={"title": "置顶权限" + _uid(), "content": "x",
                                "published": True}).get_json()["id"]
            r = _req(client, "post", "/api/mobile/post/%d/pin" % pid, tok=tok_normal,
                     payload={"pinned": True})
            assert r.status_code == 403, "普通用户不能置顶"

            tok_super = _auth(client, super_u.id)
            r2 = _req(client, "post", "/api/mobile/post/%d/pin" % pid, tok=tok_super,
                      payload={"pinned": True})
            assert r2.status_code == 200, r2.get_json()
            assert db.session.get(Post, pid).is_pinned is True

            r3 = _req(client, "post", "/api/mobile/post/%d/pin" % pid, tok=tok_super,
                      payload={"pinned": False})
            assert r3.status_code == 200
            assert db.session.get(Post, pid).is_pinned is False
        finally:
            _drop(pids=[pid] if pid else [], uids=[normal.id, super_u.id])


def test_软删进回收站并可还原(app, client):
    """trash → `/mobile/trash` 列出 → restore → 文章回到列表（走后台同一实现）。"""
    with app.app_context():
        u = _mkuser()
        pid = None
        rid = None
        try:
            tok = _auth(client, u.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok,
                       payload={"title": "待删除的文章" + _uid(), "content": "x",
                                "published": True}).get_json()["id"]
            assert _req(client, "post", "/api/mobile/post/%d/trash" % pid,
                        tok=tok).status_code == 200
            assert db.session.get(Post, pid).in_trash is True, "必须是软删除，不真删表行"

            row = next((i for i in client.get("/api/mobile/trash").get_json()["items"]
                        if i["post_id"] == pid), None)
            assert row is not None, "回收站列表没出现刚删除的文章"
            rid = row["id"]

            r = _req(client, "post", "/api/mobile/trash/%d/restore" % rid, tok=tok)
            assert r.status_code == 200, r.get_json()
            assert db.session.get(Post, pid).in_trash is False
            assert db.session.get(RecycleBin, rid).restored is True
        finally:
            _drop(pids=[pid] if pid else [], rids=[rid] if rid else [], uids=[u.id])


def test_列表分页信封与状态筛选(app, client):
    with app.app_context():
        u = _mkuser()
        pids = []
        tag = _uid()
        try:
            tok = _auth(client, u.id)
            for i in range(3):
                r = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                    "title": "分页样本%d-%s" % (i, tag), "content": "正文",
                    "published": i != 0})
                pids.append(r.get_json()["id"])

            body = client.get("/api/mobile/posts?per_page=2&page=1").get_json()
            assert {"items", "total", "page", "pages"} <= set(body)
            assert body["page"] == 1 and len(body["items"]) <= 2

            drafts = client.get("/api/mobile/posts?status=draft&q=%s" % tag).get_json()
            assert drafts["items"], "草稿筛选应命中刚建的那篇"
            assert all(i["published"] is False for i in drafts["items"])

            detail = client.get("/api/mobile/post/%d" % pids[0]).get_json()
            assert detail["content"] == "正文", "详情必须带 Markdown 原文"
            assert "content" not in drafts["items"][0], "列表不该拖正文"
        finally:
            _drop(pids=pids, uids=[u.id])


def test_分类候选接口(app, client):
    with app.app_context():
        u = _mkuser()
        try:
            _auth(client, u.id)
            body = client.get("/api/mobile/taxonomy").get_json()
            assert {"categories", "series", "tags"} <= set(body)
        finally:
            _drop(uids=[u.id])


# ---------------------------------------------------------------- 评论审核


def test_评论通过_驳回_未知动作(app, client):
    with app.app_context():
        u = _mkuser()
        pid = None
        cid = None
        try:
            tok = _auth(client, u.id)
            title = "评论样本文章" + _uid()
            pid = _req(client, "post", "/api/mobile/post", tok=tok,
                       payload={"title": title, "content": "x",
                                "published": True}).get_json()["id"]
            c = Comment(post_id=pid, author="路人甲", content="待审评论内容",
                        approved=False, is_read=False)
            db.session.add(c)
            db.session.commit()
            cid = c.id

            pend = client.get("/api/mobile/comments?status=pending").get_json()
            hit = next((i for i in pend["items"] if i["id"] == cid), None)
            assert hit is not None, "待审列表应含这条"
            assert hit["post_title"] == title, "列表要带文章上下文，App 才知道在审哪篇"

            assert _req(client, "post", "/api/mobile/comment/%d/approve" % cid,
                        tok=tok).status_code == 200
            c = db.session.get(Comment, cid)
            assert (c.approved, c.is_read) == (True, True), "通过应同时标已读"

            r = _req(client, "post", "/api/mobile/comment/%d/reject" % cid, tok=tok)
            assert r.status_code == 200
            assert db.session.get(Comment, cid) is None, "驳回=删除，与后台同口径"
            cid = None

            assert _req(client, "post", "/api/mobile/comment/1/noop",
                        tok=tok).status_code == 400, "未知动作要拒绝"
        finally:
            _drop(pids=[pid] if pid else [], cids=[cid] if cid else [], uids=[u.id])


def test_批量审核与全部已读(app, client):
    with app.app_context():
        u = _mkuser()
        pid = None
        cids = []
        try:
            tok = _auth(client, u.id)
            pid = _req(client, "post", "/api/mobile/post", tok=tok,
                       payload={"title": "批量审核文章" + _uid(), "content": "x",
                                "published": True}).get_json()["id"]
            for i in range(2):
                c = Comment(post_id=pid, author="批%d" % i, content="批量内容%d" % i,
                            approved=False, is_read=False)
                db.session.add(c)
                db.session.commit()
                cids.append(c.id)

            r = _req(client, "post", "/api/mobile/comments/batch", tok=tok,
                     payload={"action": "approve", "ids": cids})
            assert r.status_code == 200 and r.get_json()["changed"] == 2
            assert Comment.query.filter(Comment.id.in_(cids),
                                        Comment.approved.is_(False)).count() == 0

            assert _req(client, "post", "/api/mobile/comments/read-all",
                        tok=tok).status_code == 200
            assert Comment.query.filter_by(is_read=False).count() == 0

            assert _req(client, "post", "/api/mobile/comments/batch", tok=tok,
                        payload={"action": "approve", "ids": []}).status_code == 400
            assert _req(client, "post", "/api/mobile/comments/batch", tok=tok,
                        payload={"action": "nope", "ids": cids}).status_code == 400
        finally:
            _drop(pids=[pid] if pid else [], cids=cids, uids=[u.id])


# ---------------------------------------------------------------- 访客日志 / 封禁


def _test_ip(prefix):
    return "%s.%d" % (prefix, int(_uid(), 16) % 250 + 1)


def test_访客日志区间筛选与字段(app, client):
    with app.app_context():
        u = _mkuser()
        ip = _test_ip("203.0.113")
        try:
            _auth(client, u.id)
            today = utcnow().date().isoformat()
            db.session.add(VisitLog(date=today, hour=9, ip=ip, region="浙江·杭州",
                                    path="/post/abc", referrer="baidu.com",
                                    is_bot=False, created_at=utcnow()))
            db.session.add(VisitLog(date=today, hour=10, ip=ip, region="浙江·杭州",
                                    path="/", is_bot=True, bot_name="Googlebot",
                                    bot_category="search", created_at=utcnow()))
            db.session.commit()

            body = client.get("/api/mobile/visit-logs?range=today").get_json()
            assert body["range"]["key"] == "today"
            assert len(body["ranges"]) == 9, "九档区间原样回传，App 不必自己算日期"
            mine = [i for i in body["items"] if i["ip"] == ip]
            assert len(mine) == 2
            assert {i["is_bot"] for i in mine} == {True, False}
            bot = next(i for i in mine if i["is_bot"])
            assert bot["bot_name"] == "Googlebot" and bot["bot_category"] == "search"

            bots = client.get("/api/mobile/visit-logs?range=today&type=bot").get_json()
            assert all(i["is_bot"] for i in bots["items"])

            bypath = client.get("/api/mobile/visit-logs?range=today&path=/post").get_json()
            assert all("/post" in i["path"] for i in bypath["items"]), "LIKE 筛选要生效"
        finally:
            _drop(uids=[u.id], ips=[ip])


def test_拉黑需超管_且日志页标记已拉黑(app, client):
    with app.app_context():
        normal = _mkuser(ROLE_USER)
        super_u = _mkuser(ROLE_SUPER)
        ip = _test_ip("198.51.100")
        try:
            tok_normal = _auth(client, normal.id)
            r = _req(client, "post", "/api/mobile/ip/block", tok=tok_normal,
                     payload={"ip": ip})
            assert r.status_code == 403, "拉黑是超管专属（与后台 visit_logs_block 同级）"

            tok_super = _auth(client, super_u.id)
            ok = _req(client, "post", "/api/mobile/ip/block", tok=tok_super,
                      payload={"ip": ip})
            assert ok.status_code == 200, ok.get_json()

            listed = client.get("/api/mobile/blocked").get_json()
            row = next((i for i in listed["items"] if i["ip"] == ip), None)
            assert row is not None and row["permanent"] is True, "默认永久封禁"

            db.session.add(VisitLog(date=utcnow().date().isoformat(), hour=1, ip=ip,
                                    path="/post/x", is_bot=False, created_at=utcnow()))
            db.session.commit()
            logs = client.get("/api/mobile/visit-logs?range=today").get_json()
            hit = next((i for i in logs["items"] if i["ip"] == ip), None)
            assert hit is not None and hit["blocked"] is True, "日志要显示「已拉黑」态"

            bad = _req(client, "post", "/api/mobile/ip/block", tok=tok_super,
                       payload={"ip": "不是IP"})
            assert bad.status_code == 400, "非法 IP 要拒绝，不能写脏数据"

            assert _req(client, "post", "/api/mobile/ip/unblock", tok=tok_super,
                        payload={"ip": ip}).status_code == 200
            # 解封是幂等的：BotBlock 行仍在（只是 active=False），再解一次仍返回成功，
            # 与后台「未找到记录才报失败」的口径一致 —— 这里刻意**不**要求第二次 404。
            assert _req(client, "post", "/api/mobile/ip/unblock", tok=tok_super,
                        payload={"ip": ip}).status_code == 200
            gone = _req(client, "post", "/api/mobile/ip/unblock", tok=tok_super,
                        payload={"ip": "240.0.0.1"})
            assert gone.status_code == 404, "从未封禁过的 IP 才该报未找到"
        finally:
            _drop(uids=[normal.id, super_u.id], ips=[ip])


# ---------------------------------------------------------------- 友链 / 微动态 / 统计 / 上传


def test_友链申请通过与拒绝(app, client):
    with app.app_context():
        u = _mkuser()
        ids = []
        url = "https://%s.example.com" % _uid()
        url2 = url + "/also"
        try:
            tok = _auth(client, u.id)
            a = LinkApplication(name="样本站" + _uid(), url=url, description="d",
                                status="pending")
            b = LinkApplication(name="被拒站" + _uid(), url=url2, description="d2",
                                status="pending")
            db.session.add_all([a, b])
            db.session.commit()
            ids = [a.id, b.id]

            lst = client.get("/api/mobile/link-applications").get_json()
            assert {i["id"] for i in lst["items"]} >= set(ids)

            assert _req(client, "post", "/api/mobile/link-application/%d/approve" % a.id,
                        tok=tok).status_code == 200
            assert db.session.get(LinkApplication, a.id).status == "approved"
            assert FriendLink.query.filter_by(url=url).first() is not None, "通过要落友链表"

            r = _req(client, "post", "/api/mobile/link-application/%d/reject" % b.id,
                     tok=tok, payload={"note": "内容不符"})
            assert r.status_code == 200
            got = db.session.get(LinkApplication, b.id)
            assert got.status == "rejected" and got.review_note == "内容不符"
            assert got.reviewer == u.username
            assert FriendLink.query.filter_by(url=url2).first() is None, "拒绝不该落友链表"
        finally:
            FriendLink.query.filter(FriendLink.url.in_([url, url2])).delete(
                synchronize_session=False)
            db.session.commit()
            _drop(uids=[u.id], links=ids)


def test_微动态发布与删除(app, client):
    with app.app_context():
        u = _mkuser()
        mid = None
        try:
            tok = _auth(client, u.id)
            r = _req(client, "post", "/api/mobile/moment", tok=tok,
                     payload={"content": "移动端发的微动态" + _uid()})
            assert r.status_code == 201
            mid = r.get_json()["id"]
            assert db.session.get(Moment, mid).author_id == u.id

            assert _req(client, "post", "/api/mobile/moment", tok=tok,
                        payload={"content": "  "}).status_code == 400

            listed = client.get("/api/mobile/moments?q=移动端发的微动态").get_json()
            assert any(i["id"] == mid for i in listed["items"])

            assert _req(client, "post", "/api/mobile/moment/%d/delete" % mid,
                        tok=tok).status_code == 200
            assert db.session.get(Moment, mid) is None
            mid = None
        finally:
            _drop(mids=[mid] if mid else [], uids=[u.id])


def test_统计接口给汇总与趋势(app, client):
    with app.app_context():
        u = _mkuser()
        try:
            _auth(client, u.id)
            body = client.get("/api/mobile/stats").get_json()
            assert body["ok"] is True and "summary" in body
            assert "trend" not in body, "默认不拖趋势序列"
            detail = client.get("/api/mobile/stats?detail=1").get_json()
            assert "trend" in detail
        finally:
            _drop(uids=[u.id])


def test_上传拒绝伪装图片并接受真图片(app, client):
    """文件头不是图片就拒 —— 手机相册/文件管理器里同样能塞进伪装成 .png 的 HTML。"""
    with app.app_context():
        u = _mkuser()
        saved = []
        try:
            tok = _auth(client, u.id)
            r = client.post("/api/mobile/upload",
                            data={"file": (io.BytesIO(b"<html>fake</html>"), "fake.png")},
                            content_type="multipart/form-data",
                            headers={"X-CSRF-Token": tok})
            assert r.status_code == 400, r.get_json()

            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
            r2 = client.post("/api/mobile/upload",
                             data={"file": (io.BytesIO(png), "real.png")},
                             content_type="multipart/form-data",
                             headers={"X-CSRF-Token": tok})
            assert r2.status_code in (200, 201), r2.get_json()
            body = r2.get_json() or {}
            assert body.get("url", "").startswith("/static/uploads/")
            name = body.get("name") or ""
            if name:
                from flask import current_app
                fp = os.path.join(current_app.config["UPLOAD_FOLDER"], name)
                if os.path.isfile(fp):
                    saved.append(fp)
        finally:
            for fp in saved:
                with contextlib.suppress(OSError):
                    os.remove(fp)
            _drop(uids=[u.id])


# ---------------------------------------------------------------- 首屏与定时


def test_overview_一次给回首屏需要的数(app, client):
    """断言「计数键齐全」且「与表内实际一致」—— App 不必再打五个请求。"""
    with app.app_context():
        u = _mkuser()
        pid = None
        cid = None
        nid = None
        try:
            tok = _auth(client, u.id)
            title = "首屏样本" + _uid()
            pid = _req(client, "post", "/api/mobile/post", tok=tok,
                       payload={"title": title, "content": "x"}).get_json()["id"]
            c = Comment(post_id=pid, author="甲", content="首屏评论", approved=False,
                        is_read=False)
            db.session.add(c)
            db.session.commit()
            cid = c.id
            n = Notification(user_id=u.id, content="有人评论了你" + _uid(), is_read=False)
            db.session.add(n)
            db.session.commit()
            nid = n.id

            body = client.get("/api/mobile/overview").get_json()
            counts = body["counts"]
            for key in ("pending_comments", "unread_comments", "unread_notifications",
                        "drafts", "scheduled", "pending_links", "pin_requests", "trash"):
                assert key in counts, key
            assert counts["pending_comments"] >= 1
            assert counts["unread_notifications"] >= 1
            assert counts["drafts"] >= 1, "刚建的未发布文章应计入草稿"
            assert body["user"]["is_super"] is True
            assert body["user"]["id"] == u.id
            assert "today_visits" in body["today"]
            assert any(i["id"] == cid for i in body["recent_comments"])
        finally:
            if nid:
                db.session.delete(db.session.get(Notification, nid))
                db.session.commit()
            _drop(pids=[pid] if pid else [], cids=[cid] if cid else [], uids=[u.id])


def test_定时发布时间格式与后台一致(app, client):
    """`scheduled_at` 收北京时间 `YYYY-MM-DDTHH:MM`，落库必须是 UTC naive。

    锁的是「入口从表单变成 JSON，换算不能变」——v3.x 就因两套换算错过 8 小时。
    """
    with app.app_context():
        u = _mkuser()
        pid = None
        try:
            tok = _auth(client, u.id)
            # `scheduled_at` 按北京时间传入，`_parse_scheduled` 会减 8 小时存成 UTC naive。
            # 所以想让「落库的 UTC 时间 = 现在 + 32h」，送出去的北京时间得是 现在 + 40h。
            want_utc_delta = timedelta(hours=32)
            future_bj = (utcnow() + timedelta(hours=8) + want_utc_delta).strftime(
                "%Y-%m-%dT%H:%M")
            r = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "定时样本" + _uid(), "content": "x", "published": True,
                "scheduled_at": future_bj})
            assert r.status_code == 201, r.get_json()
            pid = r.get_json()["id"]
            p = db.session.get(Post, pid)
            assert p.published is False, "未来定时必须存为未发布，到点由后台线程翻牌"
            assert p.scheduled_at is not None
            delta = p.scheduled_at - utcnow()
            # ±1h 容差：传入只到分钟，且 strftime 截断了秒
            assert want_utc_delta - timedelta(hours=1) < delta < \
                want_utc_delta + timedelta(hours=1), delta
            assert r.get_json()["scheduled_at"], "响应要回显生效的定时时间，App 才能显示「将于…」"
        finally:
            _drop(pids=[pid] if pid else [], uids=[u.id])


# ---------------------------------------------------------------- v4.4.0：内容管理全套


def _drop_rows(anns=(), subs=(), guests=(), cats=(), tags=(), ser=(), links=(), hist=()):
    """按 id 精确清理 v4.4.0 新增接口涉及的表（与 `_drop` 同一原则：绝不整表删）。"""
    for model, ids in ((Announcement, anns), (Subscriber, subs), (Guestbook, guests),
                       (Category, cats), (Tag, tags), (Series, ser),
                       (FriendLink, links), (PostHistory, hist)):
        if ids:
            model.query.filter(model.id.in_(list(ids))).delete(synchronize_session=False)
    db.session.commit()


def _mkann(client, tok, content=None, level="info", active=True, dismiss=True):
    """建一条公告并返回 id（用例正文里少重复五字段）。"""
    r = _req(client, "post", "/api/mobile/announcement", tok=tok, payload={
        "content": content or ("样本公告" + _uid()), "level": level,
        "active": active, "dismissible": dismiss})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_公告权限分层与档位归一(app, client):
    """公告是**全站顶部横幅**：普通用户连列表都不该拿到；未知 level 归一 info；空内容必须拒。

    `level` 白名单和空内容判据都在 `admin._helpers._announcement_fields`，后台网页与
    移动端共用 —— 这里断言的是 API 侧确实吃到了同一套，而不是自己另写一套宽松校验。
    """
    with app.app_context():
        normal, admin = _mkuser(ROLE_USER), _mkuser(ROLE_ADMIN)
        ids = []
        try:
            _auth(client, normal.id)
            assert client.get("/api/mobile/announcements").status_code == 403
            tok = _auth(client, admin.id)
            assert client.get("/api/mobile/announcements").status_code == 200

            empty = _req(client, "post", "/api/mobile/announcement", tok=tok,
                         payload={"content": "   ", "active": True})
            assert empty.status_code == 400, empty.get_json()

            aid = _mkann(client, tok, level="critical", dismiss=False)
            ids.append(aid)
            a = db.session.get(Announcement, aid)
            assert a.level == "info", "非白名单档位必须归一，否则前台按 level 上色会出现未知档"
            assert a.active is True and a.dismissible is False
            assert _audit_count("mobile_ann_create", aid) == 1
            # 列表里的 content 是 Markdown 原文（编辑器要能改），不是前台渲染后的 HTML
            listed = client.get("/api/mobile/announcements").get_json()["items"]
            mine = next(i for i in listed if i["id"] == aid)
            assert mine["content"] == a.content and "<p>" not in mine["content"]
        finally:
            _drop_rows(anns=ids)
            _drop(uids=[normal.id, admin.id])


def test_公告启停传显式目标值_整单语义与后台一致(app, client):
    """`/active` 收 **显式值**而不是翻转：漏传字段报 400，重发多少次结果都一样。

    两条都是手机上踩出来的：弱网重发让 toggle 来回横跳；客户端只发 `{"active": …}`
    以外的部分表单时，`form_flag` 缺键会得到 False —— 对整单表单是对的，
    对「改一个状态」的接口就是静默改数据。同时钉住整单 PUT 的「缺省即没勾选」语义。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        ids = []
        try:
            tok = _auth(client, admin.id)
            aid = _mkann(client, tok, level="warning", active=True, dismiss=True)
            ids.append(aid)

            missing = _req(client, "post", f"/api/mobile/announcement/{aid}/active",
                           tok=tok, payload={})
            assert missing.status_code == 400, "漏传 active 不能当成「停用」静默写库"

            for _ in range(2):     # 幂等：连发两次停用，第二次不该把状态翻回去
                off = _req(client, "post", f"/api/mobile/announcement/{aid}/active",
                           tok=tok, payload={"active": False})
                assert off.status_code == 200, off.get_json()
            assert db.session.get(Announcement, aid).active is False

            on = _req(client, "post", f"/api/mobile/announcement/{aid}/active",
                      tok=tok, payload={"active": "true"})
            assert on.get_json()["item"]["active"] is True, '"true" 字符串与 true 同一判据'

            partial = _req(client, "put", f"/api/mobile/announcement/{aid}", tok=tok,
                           payload={"content": "改过的公告", "level": "info"})
            assert partial.status_code == 200, partial.get_json()
            a = db.session.get(Announcement, aid)
            assert a.content == "改过的公告" and a.active is False and a.dismissible is False, \
                "整单语义＝没带就是没勾；客户端必须先 GET 详情再回传全量"
        finally:
            _drop_rows(anns=ids)
            _drop(uids=[admin.id])


def test_订阅邮箱遮敏给管理员_超管全量_令牌绝不出现在响应里(app, client):
    """三个必须同时成立：管理员看到遮敏、超管看到全量、任何人都拿不到 `unsub_token`。

    `unsub_token` 是免登录退订凭证（`/unsubscribe/<token>`），泄露等于任何人都能替
    订阅者退订；把它从响应里去掉是本接口唯一的硬性红线，所以断言写在**原始文本**上
    （`r.get_data(as_text=True)`），而不是解析后的 dict —— 解析后漏检一个嵌套键就白测了。
    """
    with app.app_context():
        admin, super_u = _mkuser(ROLE_ADMIN), _mkuser(ROLE_SUPER)
        uid = _uid()
        email = "sub-%s@exemple-mail.test" % uid
        token = secrets.token_hex(16)
        sub = Subscriber(email=email, unsub_token=token, active=True)
        db.session.add(sub)
        db.session.commit()
        try:
            _auth(client, admin.id)
            body = client.get("/api/mobile/subscribers?q=exemple-mail").get_json()
            mine = next(i for i in body["items"] if i["id"] == sub.id)
            assert mine["email"] == "su***@exemple-mail.test", mine
            assert mine["email_masked"] is True
            raw_admin = client.get("/api/mobile/subscribers").get_data(as_text=True)
            assert email not in raw_admin, "管理员整页翻页不该把可群发的邮箱清单带走"
            assert token not in raw_admin and "unsub_token" not in raw_admin
            assert body["total"] >= 1, "遮敏不影响计数"

            _auth(client, super_u.id)
            raw_super = client.get("/api/mobile/subscribers?q=exemple-mail").get_data(as_text=True)
            assert email in raw_super, "超管要全量才能联系/导出"
            assert token not in raw_super, "全量指的是邮箱，退订令牌对谁都不给"

            off = _req(client, "post", f"/api/mobile/subscriber/{sub.id}/active",
                       tok=_auth(client, super_u.id), payload={"active": False})
            assert off.status_code == 200, off.get_json()
            assert db.session.get(Subscriber, sub.id).active is False
        finally:
            _drop_rows(subs=[sub.id])
            _drop(uids=[admin.id, super_u.id])


def test_留言_ip_只给超管_删除是硬删且不留档(app, client):
    """沿用 v4.3.1 对访客日志的分层：IP 原文超管可见，管理员拿归属地/设备。

    另外两条红线：删除是**硬删**（`RecycleBin` 只登记文章，留言没有回收站），
    以及审计 `detail` 里不出现 IP —— 审计表长期留存，没必要为一条被删的留言
    再留一份可定位到人的信息。
    """
    with app.app_context():
        admin, super_u = _mkuser(ROLE_ADMIN), _mkuser(ROLE_SUPER)
        uid = _uid()
        ip = "203.0.113.%s" % uid[:3].replace("-", "0")[:3]
        g = Guestbook(author="留言客" + uid, content="需要处理的留言" + uid,
                      ip=ip, region="海外", device="iPhone", is_read=False)
        db.session.add(g)
        db.session.commit()
        try:
            _auth(client, admin.id)
            listed = client.get("/api/mobile/guestbook?q=" + uid).get_json()["items"]
            mine = next(i for i in listed if i["id"] == g.id)
            assert mine["region"] == "海外" and mine["device"] == "iPhone"
            assert "ip" not in mine, "管理员不该从 JSON 里拿到访客 IP 原文"
            assert client.get("/api/mobile/guestbook").get_data(as_text=True).count(ip) == 0

            # 未读数走 overview（与后台导航角标同一指标），列表接口只给数据不给计数
            tok_admin = _auth(client, admin.id)
            assert client.get("/api/mobile/overview").get_json()["counts"]["unread_guestbook"] >= 1

            read = _req(client, "post", f"/api/mobile/guestbook/{g.id}/read",
                        tok=tok_admin, payload={})
            assert read.status_code == 200, read.get_json()
            assert db.session.get(Guestbook, g.id).is_read is True
            again = _req(client, "post", f"/api/mobile/guestbook/{g.id}/read",
                         tok=tok_admin, payload={})
            assert again.status_code == 200, "标已读幂等，重发不会报错"

            _auth(client, super_u.id)
            tok_super = _auth(client, super_u.id)
            s_item = next(i for i in client.get("/api/mobile/guestbook?q=" + uid)
                          .get_json()["items"] if i["id"] == g.id)
            assert s_item["ip"] == ip, "超管可见 IP（处理骚扰留言不必回电脑）"

            dele = _req(client, "post", f"/api/mobile/guestbook/%d/delete" % g.id,
                        tok=tok_super, payload={})
            assert dele.status_code == 200, dele.get_json()
            assert db.session.get(Guestbook, g.id) is None, "留言删除是硬删，没有可还原记录"
            assert RecycleBin.query.filter_by(title=g.content).count() == 0
            row = AuditLog.query.filter_by(action="mobile_guest_delete", target_id=g.id).first()
            assert row and ip not in (row.detail or ""), "PII 不进审计"
        finally:
            _drop_rows(guests=[g.id])
            _drop(uids=[admin.id, super_u.id])


def test_分类改名回传_slug_变化_删除分转移与留空两种(app, client):
    """改名**沿用后台行为**（无条件重算 slug），但必须把「旧 → 新」如实回传。

    站点没有 slug 别名表也没有 301，改名等于让外发链接 404 —— UI 要能在动手前显示这条
    提醒，而提醒的内容只能由服务端给（客户端自己算不出 unique_model_slug 的结果）。
    删除分两条路：给 `move_to` 是转移，不给是文章变「无分类」，两者都必须可区分（
    `affected` / `moved`），并且非法 `move_to` 要报错而不是静默退化成无分类。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        cats, pids = [], []
        try:
            src = _req(client, "post", "/api/mobile/category", tok=tok,
                       payload={"name": "改名源" + uid}).get_json()
            dst = _req(client, "post", "/api/mobile/category", tok=tok,
                       payload={"name": "落点" + uid}).get_json()
            cats += [src["item"]["id"], dst["item"]["id"]]
            dup = _req(client, "post", "/api/mobile/category", tok=tok,
                       payload={"name": "改名源" + uid})
            assert dup.status_code == 400, "同名精确判重与编辑器「就地新建」同一口径"

            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "分类样本" + uid, "content": "x",
                "category_id": src["item"]["id"]}).get_json()["id"]
            pids.append(pid)

            rename = _req(client, "put", f"/api/mobile/category/{src['item']['id']}", tok=tok,
                          payload={"name": "改名后" + uid})
            assert rename.status_code == 200, rename.get_json()
            note = rename.get_json()["note"]
            assert "失效" in note and src["item"]["slug"] in note, note
            assert db.session.get(Category, src["item"]["id"]).slug == rename.get_json()["item"]["slug"]

            bad = _req(client, "post", "/api/mobile/category/%d/delete" % dst["item"]["id"],
                       tok=tok, payload={"move_to": 999999})
            assert bad.status_code == 400, "非法 move_to 必须报错，不能静默把文章甩成无分类"

            moved = _req(client, "post", "/api/mobile/category/%d/delete" % src["item"]["id"],
                         tok=tok, payload={"move_to": dst["item"]["id"]})
            assert moved.status_code == 200, moved.get_json()
            mb = moved.get_json()
            assert (mb["affected"], mb["moved"]) == (1, 1), mb
            assert db.session.get(Post, pid).category_id == dst["item"]["id"]

            # 再建一个带文章的分类，不给 move_to：文章留着，但变成无分类
            other = _req(client, "post", "/api/mobile/category", tok=tok,
                         payload={"name": "无落点" + uid}).get_json()
            cats.append(other["item"]["id"])
            p2 = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "无落点样本" + uid, "content": "x",
                "category_id": other["item"]["id"]}).get_json()["id"]
            pids.append(p2)
            bare = _req(client, "post", "/api/mobile/category/%d/delete" % other["item"]["id"],
                        tok=tok, payload={})
            bb = bare.get_json()
            assert (bb["affected"], bb["moved"]) == (1, 0), bb
            assert db.session.get(Post, p2).category_id is None
            assert db.session.get(Post, p2) is not None, "删分类不该连文章一起删"
        finally:
            _drop(pids=pids)
            _drop_rows(cats=cats)
            _drop(uids=[admin.id])


def test_标签在用拒删_变体经一键整理合并(app, client):
    """标签是文章的属性：级联清理等于悄悄改文章，所以「在用」一律 400。

    合并走后台同一对函数（`merge_duplicate_tags` / `cleanup_orphan_tags`）。重复行**只能
    直接入库**造出来：`create_tag_core` 自己就按 `normalize_tag_key` 拒绝变体，用它建不出
    待合并的脏数据 —— 而线上遗留的 `'AI' + 'ai'` 两行正是这种历史产物。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        tag_ids, pids = [], []
        try:
            # 顺序很重要：`create_post_core` 提交后会调 `cleanup_orphan_tags()` 清全站 0 使用
            # 标签，所以**先建文章**再建标签 —— 反过来建好的变体行会在建文章时被顺手清掉，
            # 于是后面的关联拿到的是「已被删除的实例」。
            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "标签样本" + uid, "content": "x"}).get_json()["id"]
            pids.append(pid)

            dup = _req(client, "post", "/api/mobile/tag", tok=tok,
                       payload={"name": "TagCase" + uid}).get_json()["item"]
            tag_ids.append(dup["id"])
            used_row = Tag(name="tagcase" + uid, slug="tagcase-" + uid)   # 大小写变体，直接入库
            db.session.add(used_row)
            db.session.commit()
            tag_ids.append(used_row.id)

            refused_by_api = _req(client, "post", "/api/mobile/tag", tok=tok,
                                  payload={"name": "  TagCase%s  " % uid})
            assert refused_by_api.status_code == 400, "大小写/空白变体按 normalize_tag_key 判重"

            post = db.session.get(Post, pid)
            post.tags.append(used_row)          # 挂到「用得更多」的那行，合并后它才是保留行
            db.session.commit()

            refused = _req(client, "post", "/api/mobile/tag/%d/delete" % used_row.id,
                           tok=tok, payload={})
            assert refused.status_code == 400, "被文章用着的标签必须拒删"
            assert "篇文章" in refused.get_json()["error"]

            spare = _req(client, "post", "/api/mobile/tag", tok=tok,
                         payload={"name": "Spare" + uid}).get_json()["item"]
            ok_del = _req(client, "post", "/api/mobile/tag/%d/delete" % spare["id"],
                          tok=tok, payload={})
            assert ok_del.status_code == 200, ok_del.get_json()
            assert db.session.get(Tag, spare["id"]) is None, "没人用的标签可以直接删"

            orphan = Tag(name="Orphan" + uid, slug="orphan-" + uid)   # 0 使用，等一键整理清
            db.session.add(orphan)
            db.session.commit()
            tag_ids.append(orphan.id)

            merged = _req(client, "post", "/api/mobile/tags/merge", tok=tok, payload={})
            assert merged.status_code == 200, merged.get_json()
            mb = merged.get_json()
            assert mb["merged"] >= 1 and mb["cleaned"] >= 1, mb
            assert db.session.get(Tag, dup["id"]) is None, "重复行里没被保留的那行要消失"
            assert db.session.get(Tag, orphan.id) is None, "0 使用的标签被清理"
            after = db.session.get(Post, pid)
            assert [t.id for t in after.tags] == [used_row.id], \
                "合并后文章关联要跟着保留行走（保留行按使用篇数选）"
        finally:
            _drop(pids=pids)
            _drop_rows(tags=tag_ids)
            _drop(uids=[admin.id])


def test_系列改名换_slug_删除可选转移到另一系列(app, client):
    """系列与分类的两点差异都要覆盖：`name` 不唯一（重名不拒）、删除新增 `move_to`。"""
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        sids, pids = [], []
        try:
            src = _req(client, "post", "/api/mobile/series", tok=tok, payload={
                "name": "系列源" + uid, "description": "简介", "sort": 3}).get_json()
            dst = _req(client, "post", "/api/mobile/series", tok=tok,
                       payload={"name": "系列落点" + uid}).get_json()
            sids += [src["item"]["id"], dst["item"]["id"]]
            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "系列样本" + uid, "content": "x",
                "series_id": src["item"]["id"]}).get_json()["id"]
            pids.append(pid)

            edit = _req(client, "put", f"/api/mobile/series/{src['item']['id']}", tok=tok,
                        payload={"name": "系列改名" + uid, "description": "新简介"})
            assert edit.status_code == 200, edit.get_json()
            eb = edit.get_json()
            assert "失效" in eb["note"] and eb["item"]["description"] == "新简介"
            assert eb["item"]["cover"] == "", "整单回传时没带的字段按后台语义覆盖为空"

            # move_to 指向自身 / 指向不存在的行：`_resolve_target` 本来会静默返回 None
            # （等于「不转移」），但客户端以为自己转移了 —— 这种静默退化必须在 API 层挡住。
            self_move = _req(client, "post", "/api/mobile/series/%d/delete" % src["item"]["id"],
                             tok=tok, payload={"move_to": src["item"]["id"]})
            assert self_move.status_code == 400, self_move.get_json()
            ghost = _req(client, "post", "/api/mobile/series/%d/delete" % src["item"]["id"],
                         tok=tok, payload={"move_to": 999999})
            assert ghost.status_code == 400, "不存在的落点要报错，不能静默把文章甩成无系列"
            assert db.session.get(Series, src["item"]["id"]) is not None

            # 不给 move_to：dst 也有文章，删掉后文章**留着但脱离系列**（后台原行为）
            p2 = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "脱离系列样本" + uid, "content": "x",
                "series_id": dst["item"]["id"]}).get_json()["id"]
            pids.append(p2)
            plain = _req(client, "post", "/api/mobile/series/%d/delete" % dst["item"]["id"],
                         tok=tok, payload={})
            pb = plain.get_json()
            assert plain.status_code == 200 and (pb["affected"], pb["moved"]) == (1, 0), pb
            assert db.session.get(Post, p2).series_id is None
            assert db.session.get(Post, p2) is not None, "删系列不许把文章一起删掉"

            # `Series.name` 没有唯一约束（与 `Category.name` 不同）：重名照建，只能按 id 定位
            same_name = "系列改名" + uid
            last = _req(client, "post", "/api/mobile/series", tok=tok,
                        payload={"name": same_name}).get_json()["item"]
            sids.append(last["id"])
            assert Series.query.filter_by(name=same_name).count() == 2, \
                "同名系列不会被拒 —— App 里想避免重复系列，得先拉清单自己比对"

            moved = _req(client, "post", f"/api/mobile/series/{src['item']['id']}/delete",
                         tok=tok, payload={"move_to": last["id"]}).get_json()
            assert (moved["affected"], moved["moved"]) == (1, 1), moved
            assert db.session.get(Post, pid).series_id == last["id"]
            assert db.session.get(Post, pid) is not None, "删系列不该连文章一起删"
        finally:
            _drop(pids=pids)
            _drop_rows(ser=sids)
            _drop(uids=[admin.id])


def test_友链_url_归一查重与排序只动列出的(app, client):
    """友链本体的四个写动作全部复用 `save_friend_link_core` / `reorder_friend_links_core`。

    三件这次才成立的事：URL 归一（光秃秃域名补 `https://`、伪协议与相对路径一律拒）、
    同 URL 查重（后台新增原先不查）、以及「编辑不再等于删了重建」（原先没有编辑入口，
    改一个字就丢 `sort` 位置）。排序只认列出的 id，未列出的保持原位。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        ids = []
        try:
            bad = _req(client, "post", "/api/mobile/link", tok=tok,
                       payload={"name": "伪协议" + uid, "url": "javascript:alert(1)"})
            assert bad.status_code == 400, "前台把 url 直接当 href，这里放行就是送一个可点执行的链接"

            r = _req(client, "post", "/api/mobile/link", tok=tok,
                     payload={"name": "补协议" + uid, "url": "Example.COM/path"})
            assert r.status_code == 201, r.get_json()
            first = r.get_json()["item"]
            ids.append(first["id"])
            assert first["url"] == "https://Example.COM/path", first

            dup = _req(client, "post", "/api/mobile/link", tok=tok,
                       payload={"name": "同址" + uid, "url": "https://Example.COM/path"})
            assert dup.status_code == 400 and "已存在" in dup.get_json()["error"]

            second = _req(client, "post", "/api/mobile/link", tok=tok,
                          payload={"name": "第二家" + uid, "url": "https://b-%s.test" % uid,
                                   "sort": 5}).get_json()["item"]
            ids.append(second["id"])
            third = _req(client, "post", "/api/mobile/link", tok=tok,
                         payload={"name": "第三家" + uid, "url": "https://c-%s.test" % uid,
                                  "sort": 9}).get_json()["item"]
            ids.append(third["id"])

            upd = _req(client, "put", f"/api/mobile/link/{second['id']}", tok=tok,
                       payload={"name": "改过名" + uid, "url": second["url"],
                                "description": "d", "sort": 5})
            assert upd.status_code == 200, upd.get_json()
            assert db.session.get(FriendLink, second["id"]).name == "改过名" + uid, \
                "编辑走同一 core，不再需要删了重建"

            order = _req(client, "post", "/api/mobile/links/reorder", tok=tok,
                         payload={"ids": [third["id"], first["id"]]}).get_json()
            assert order["moved"] >= 1
            assert db.session.get(FriendLink, second["id"]).sort == 5, "未列出的不许动"
            listed = [i["id"] for i in client.get("/api/mobile/links").get_json()["items"]]
            assert listed.index(third["id"]) < listed.index(first["id"])
            assert client.get("/api/mobile/links").status_code == 200

            assert _req(client, "post", "/api/mobile/link/%d/delete" % third["id"],
                        tok=tok, payload={}).status_code == 200
        finally:
            _drop_rows(links=ids)
            _drop(uids=[admin.id])


def test_版本历史列表不给正文_回滚只改三个字段(app, client):
    """历史的三条口径都要钉住：列表**不含正文**、diff 与后台同源、回滚**只写回三字段**。

    回滚不动 slug / 封面 / 分类 / 标签 / 系列 / 发布态 / SEO —— 所以它不会破坏已分发的
    URL，也不会把已发布文章悄悄变草稿。回滚前先备份当前版本，因此这一步本身还能撤销。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        cat_id = None
        pid = None
        try:
            cat = _req(client, "post", "/api/mobile/category", tok=tok,
                       payload={"name": "历史分类" + uid}).get_json()["item"]
            cat_id = cat["id"]
            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "历史标题一" + uid, "content": "第一版正文\n公共行",
                "summary": "摘要一", "cover": "/static/uploads/a.png",
                "category_id": cat_id, "tags": "历史标签" + uid,
                "published": True}).get_json()["id"]
            from admin._helpers import _save_post_history
            post = db.session.get(Post, pid)
            _save_post_history(post, admin.username)     # 存下「第一版」快照
            h1 = PostHistory.query.filter_by(post_id=pid).order_by(
                PostHistory.id.desc()).first()
            assert h1 is not None

            # 当前版改头改尾，但分类/封面/标签/发布态保持
            post.title = "历史标题二" + uid
            post.content = "第二版正文\n公共行\n多了的一行"
            post.summary = "摘要二"
            db.session.commit()

            lst = client.get(f"/api/mobile/post/{pid}/history").get_json()
            assert lst["items"], lst
            assert all("content" not in i for i in lst["items"]), "列表不拖正文"
            assert lst["items"][0]["size"] == len(h1.content or "")

            diff = client.get(f"/api/mobile/post/{pid}/history/diff").get_json()
            kinds = {row["kind"] for row in diff["rows"]}
            assert {"del", "add", "equal"} <= kinds, diff["rows"]

            rb = _req(client, "post", f"/api/mobile/post/{pid}/history/{h1.id}/rollback",
                      tok=tok, payload={})
            assert rb.status_code == 200, rb.get_json()
            after = db.session.get(Post, pid)
            assert (after.title, after.summary) == (h1.title, h1.summary)
            assert after.content == h1.content
            assert after.published is True and after.cover == "/static/uploads/a.png", \
                "回滚不许把已发布文章变成草稿，也不许清掉封面"
            assert after.category_id == cat_id and len(after.tags) == 1, \
                "回滚只写三字段：分类与标签关联不许被碰（`Post.tags` 是列表，用 len 不用 count）"
            assert PostHistory.query.filter_by(post_id=pid).count() >= 2, \
                "回滚前要备份当前版，否则这一步不可撤销"

            other = _mkuser(ROLE_USER)
            try:
                _auth(client, other.id)
                assert client.get(f"/api/mobile/post/{pid}/history").status_code == 403
            finally:
                _drop(uids=[other.id])
        finally:
            if pid:
                # 历史是 `_save_post_history` 自动写的，`_drop` 不管它，按 post 精确清一次
                PostHistory.query.filter_by(post_id=pid).delete(synchronize_session=False)
                db.session.commit()
            _drop(pids=[pid] if pid else [])
            _drop_rows(cats=[cat_id] if cat_id else [])
            _drop(uids=[admin.id])


# ---------------------------------------------------------------- 媒体库 / 网页端入口


def test_媒体库删除需_force_且路径穿越无效(app, client):
    """媒体库是**目录列举**，删除是硬删：被引用时先 409，再发一次 `force` 才真删。

    断言三件事：
      1. 引用判定（封面 URL 含文件名 / 正文含去时间戳片段）在 JSON 侧同样给得出 `refs`；
      2. `only_free=1` 能把没被引用的挑出来 —— 手机上清理孤儿图不可能翻全目录；
      3. 名字里带 `../` 只会因为 basename 变成 uploads 里不存在的普通文件名 → 404，
         **上级目录的真文件一个字节都不会少**（这条是五道路径防护的实证）。
    """
    import time as _time
    from flask import current_app
    with app.app_context():
        admin, normal = _mkuser(ROLE_ADMIN), _mkuser(ROLE_USER)
        uid = _uid()
        folder = current_app.config["UPLOAD_FOLDER"]
        used_name = "%d-media-used-%s.png" % (int(_time.time()), uid)
        free_name = "%d-media-free-%s.png" % (int(_time.time()), uid)
        made = []
        pid = None
        try:
            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
            for n in (used_name, free_name):
                with open(os.path.join(folder, n), "wb") as fh:
                    fh.write(png)
                made.append(os.path.join(folder, n))
            tok = _auth(client, admin.id)
            _auth(client, normal.id)
            assert client.get("/api/mobile/media").status_code == 403, "媒体库只有管理员能看"
            # 换过会话就得重取 token：`_auth` 每次都会重写会话里的 csrf_token，
            # 拿旧 token 发写请求会被全局闸门判 403（这是 CSRF 与会话绑定的正确行为）。
            tok = _auth(client, admin.id)

            # 正文引用（用去掉时间戳前缀后的裸文件名，正是 `media_refs_for` 的判据）
            pid = _req(client, "post", "/api/mobile/post", tok=tok, payload={
                "title": "插图样本" + uid,
                "content": "看图 ![](/static/uploads/%s)" % used_name}).get_json()["id"]

            listed = client.get("/api/mobile/media?q=media-used-" + uid).get_json()
            mine = next(i for i in listed["items"] if i["name"] == used_name)
            assert mine["ref_total"] >= 1 and mine["refs"][0]["id"] == pid, mine

            blocked = _req(client, "post", "/api/mobile/media/delete", tok=tok,
                           payload={"name": used_name})
            assert blocked.status_code == 409, blocked.get_json()
            assert blocked.get_json()["need_force"] is True
            assert os.path.isfile(os.path.join(folder, used_name)), "409 之后文件必须还在"

            forced = _req(client, "post", "/api/mobile/media/delete", tok=tok,
                          payload={"name": used_name, "force": True})
            assert forced.status_code == 200, forced.get_json()
            assert not os.path.isfile(os.path.join(folder, used_name))

            only = client.get("/api/mobile/media?only_free=1&q=media-free-" + uid).get_json()
            assert any(i["name"] == free_name for i in only["items"]), "孤儿图要能被筛出来"
            assert all(not i["ref_total"] for i in only["items"])

            # uploads 的上上级才是 myblog/（BASE_DIR/static/uploads）—— 穿越目标要真在那儿
            cfg = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(folder)),
                                               "config.py"))
            assert os.path.isfile(cfg), "前置条件：myblog/config.py 确实存在（穿越靶子）"
            traversal = _req(client, "post", "/api/mobile/media/delete", tok=tok,
                             payload={"name": "../config.py", "force": True})
            assert traversal.status_code == 404, traversal.get_json()
            assert os.path.isfile(cfg), "带 force 的穿越请求也不该碰到 uploads 之外的文件"
        finally:
            for fp in made:
                with contextlib.suppress(OSError):
                    os.remove(fp)
            _drop(pids=[pid] if pid else [])
            _drop(uids=[admin.id, normal.id])


def test_后台新补的编辑入口真的能提交(app, client):
    """网页端这轮补了三处 UI：公告编辑、友链编辑、友链 ↑↓ 排序 —— 页面必须真能提交。

    「只补 API 不补页面」在本仓库算缺陷：他平时手机和电脑浏览器两端都用，
    任何一端做不到的事都是能力缺口。这里用 SSR 表单写、再用 JSON 读回来，
    顺带证明两端落的是同一张表、同一套 core。
    """
    with app.app_context():
        admin = _mkuser(ROLE_ADMIN)
        tok = _auth(client, admin.id)
        uid = _uid()
        aids, lids = [], []
        try:
            aid = _mkann(client, tok, content="待网页编辑" + uid)
            aids.append(aid)
            page = client.get("/admin/announcements").get_data(as_text=True)
            assert 'data-edit-row="edit-%d"' % aid in page, "公告编辑行没渲染出来"
            assert "/admin/announcement/%d/update" % aid in page
            r = client.post("/admin/announcement/%d/update" % aid,
                            data={"content": "网页改过" + uid, "level": "success",
                                  "active": "on", "dismissible": "on", "csrf_token": tok})
            assert r.status_code in (200, 302), r.status_code
            body = client.get("/api/mobile/announcement/%d" % aid).get_json()
            assert body["content"] == "网页改过" + uid and body["level"] == "success"
            assert body["active"] is True and body["dismissible"] is True, \
                '网页表单的 "on" 与移动端的 true 走同一个 form_flag 判据'

            link = _req(client, "post", "/api/mobile/link", tok=tok,
                        payload={"name": "网页改友链" + uid,
                                 "url": "https://l-%s.test" % uid, "sort": 7}).get_json()["item"]
            lids.append(link["id"])
            lpage = client.get("/admin/links").get_data(as_text=True)
            assert 'data-edit-row="edit-%d"' % link["id"] in lpage, "友链编辑行没渲染出来"
            assert "/admin/link/%d/update" % link["id"] in lpage
            assert 'action="/admin/links/reorder"' in lpage, "排序表单没渲染出来"
            r2 = client.post("/admin/link/%d/update" % link["id"],
                             data={"name": "改好的友链" + uid, "url": link["url"],
                                   "description": "网页写的简介", "sort": 2,
                                   "rss_url": "", "csrf_token": tok})
            assert r2.status_code in (200, 302), r2.status_code
            back = next(i for i in client.get("/api/mobile/links").get_json()["items"]
                        if i["id"] == link["id"])
            assert back["name"] == "改好的友链" + uid and back["sort"] == 2
            assert back["description"] == "网页写的简介"

            # 网页端 ↑↓ 提交的是一整串按当前 DOM 顺序的 ids，与 App 拖拽后一次提交同形
            second = _req(client, "post", "/api/mobile/link", tok=tok,
                          payload={"name": "排序第二家" + uid,
                                   "url": "https://k-%s.test" % uid, "sort": 1}).get_json()["item"]
            lids.append(second["id"])
            r3 = client.post("/admin/links/reorder",
                             data={"ids": "%d,%d" % (second["id"], link["id"]),
                                   "csrf_token": tok})
            assert r3.status_code in (200, 302), r3.status_code
            order = [i["id"] for i in client.get("/api/mobile/links").get_json()["items"]
                     if i["id"] in lids]
            assert order == [second["id"], link["id"]], order
        finally:
            _drop_rows(anns=aids, links=lids)
            _drop(uids=[admin.id])
