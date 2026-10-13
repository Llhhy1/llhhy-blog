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

运行：仓库根目录 `python -m pytest tests/test_api_mobile.py -q`
测试库是 conftest 建的独立临时库；每个用例 finally 清自建数据。
"""
import contextlib
import io
import os
import secrets
import uuid
from datetime import timedelta

from models import (AuditLog, BotBlock, Comment, FriendLink, LinkApplication, Moment,
                    Notification, Post, RecycleBin, User, VisitLog, db,
                    ROLE_ADMIN, ROLE_SUPER, ROLE_USER)
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
