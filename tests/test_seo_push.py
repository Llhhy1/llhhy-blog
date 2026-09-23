"""v3.19.0 阶段 2 回归测试 —— 后台「🔍 收录」页：主动推送 + 凭据安全。

清单 2 的验收口径逐条落地：token 密文存储 / 非超管 403 / 缺 CSRF 403 /
推送不阻塞请求 / URL 不来自 `request.host` / 不可见文章不予推送。

另有两条**不在清单字面但真会出事**的断言，一并锁住：
- 出站 host 白名单必须精确（`data.zz.baidu.com.evil.com` 不能过）；
- 响应回显里的 token 必须被抹掉（否则「页面不回显明文」当场失效）。
"""
import os
import secrets
from datetime import timedelta

import pytest

from models import (db, Post, Setting, User, SeoSubmission,
                    ROLE_SUPER, ROLE_ADMIN)
from _time import utcnow
from utils import _sign_csrf

import seo_push


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """每个用例前后清空限流计数。

    推送接口自 v3.19.1 起有「3 次 / 5 分钟」限流（按客户端 key，测试里恒为
    127.0.0.1）。不隔离的话多个用例共用同一份额度，套件会变成**顺序相关**
    （单独跑绿、连跑红——本文件就踩到过）。故统一在用例前后清空。
    """
    from utils import _RATE
    _RATE.clear()
    yield
    _RATE.clear()


def _uid():
    return secrets.token_hex(4)


def _mkuser(role=ROLE_SUPER):
    u = User(username="seo-" + _uid(), email="seo-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False   # 否则 login_required 会把超管跳去 /admin/setup
    db.session.add(u)
    db.session.commit()
    return u


def _mkpost(**kw):
    slug = kw.pop("slug", "seopush-" + _uid())
    p = Post(title=kw.pop("title", "推送测试文章"), slug=slug,
             content="正文", summary="摘要",
             published=kw.pop("published", True),
             in_trash=kw.pop("in_trash", False),
             is_private=kw.pop("is_private", False),
             scheduled_at=kw.pop("scheduled_at", None),
             **kw)
    db.session.add(p)
    db.session.commit()
    return p


def _mkbase(base="https://www.llhhy.cn"):
    """把 site_url 设成给定值（site_base() 的唯一真相源）。"""
    Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
    db.session.add(Setting(key="site_url", value=base))
    db.session.commit()


def _clearbase():
    Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
    db.session.commit()


def _auth(app, client, user_id, with_csrf=True):
    """写会话 user_id 并生成绑定的 CSRF token。

    注意：`_sign_csrf()` 需要**应用上下文**（读 `current_app.config["SECRET_KEY"]`），
    测试里自造 token 必须包在 `with app.app_context():` 内，否则会
    `RuntimeError: Working outside of application context`。
    """
    raw = secrets.token_hex(24)
    with app.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        if with_csrf:
            sess["csrf_token"] = tok
    return tok


def _cleanup(post_ids=(), user_ids=(), drop_base=False, drop_keys=False):
    if post_ids:
        SeoSubmission.query.filter(SeoSubmission.post_id.in_(list(post_ids))).delete(
            synchronize_session=False)
        Post.query.filter(Post.id.in_(list(post_ids))).delete(synchronize_session=False)
    if user_ids:
        User.query.filter(User.id.in_(list(user_ids))).delete(synchronize_session=False)
    if drop_base:
        Setting.query.filter_by(key="site_url").delete(synchronize_session=False)
    if drop_keys:
        Setting.query.filter(Setting.key.like("seo_baidu_token%")).delete(
            synchronize_session=False)
        Setting.query.filter(Setting.key.like("seo_indexnow_key%")).delete(
            synchronize_session=False)
        Setting.query.filter_by(key=seo_push.QUOTA_KEY).delete(synchronize_session=False)
    db.session.commit()


# ===========================================================================
# 一、权限：非超管一律 403
# ===========================================================================
def test_seo_console_requires_super(app, client):
    """普通管理员（admin 角色）访问收录页与全部子接口 → 403。"""
    with app.app_context():
        u = _mkuser(ROLE_ADMIN)
        uid = u.id
    try:
        _auth(app, client, uid)
        assert client.get("/admin/seo").status_code == 403
        assert client.get("/admin/seo/status").status_code == 403
        assert client.get("/admin/seo/selfcheck").status_code == 403
        assert client.post("/admin/seo/token", data={}).status_code == 403
        assert client.post("/admin/seo/push", data={"engine": "baidu"}).status_code == 403
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid])


def test_seo_console_anonymous_not_200(app, client):
    """未登录：不能拿到页面内容（302 去登录 或 403 均可，绝不能 200）。"""
    r = client.get("/admin/seo")
    assert r.status_code in (302, 403), "匿名访问不得返回 200，实得 %s" % r.status_code


# ===========================================================================
# 二、凭据：必须密文存储、不回显明文
# ===========================================================================
def test_baidu_token_stored_encrypted(app, client):
    """保存 token 后库里必须是密文（bkenc$ 前缀），且与明文不同。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    plain = "tok-" + secrets.token_hex(12)
    try:
        tok = _auth(app, client, uid)
        r = client.post("/admin/seo/token", data={"baidu_token": plain, "csrf_token": tok})
        assert r.status_code in (302, 200)
        with app.app_context():
            row = Setting.query.filter_by(key="seo_baidu_token_enc").first()
            assert row is not None, "token 应写入 Setting"
            assert row.value != plain, "明文落库 = mail_password 的错误做法，绝不能照抄"
            assert row.value.startswith("bkenc$"), "必须是备份模块的 Fernet 密文格式"
            import backup_settings as bs
            assert bs.decrypt_secret(row.value) == plain, "密文应能解回原文"
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_keys=True)


def test_token_never_echoed_in_page(app, client):
    """保存后页面不得出现明文 token（清单 2.4）。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    plain = "secret-" + secrets.token_hex(10)
    try:
        tok = _auth(app, client, uid)
        client.post("/admin/seo/token", data={"baidu_token": plain, "csrf_token": tok})
        body = client.get("/admin/seo").get_data(as_text=True)
        assert plain not in body, "页面回显了明文 token"
        assert "••••••" in body, "已配置时应显示掩码"
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_keys=True)


def test_indexnow_key_validated(app, client):
    """IndexNow key 非法（含 `/`、`.`、空格、超长）必须被拒且不落库。

    不校验的后果：key 会被拼进 `keyLocation` URL，可被用来指向站内任意路径。
    """
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        tok = _auth(app, client, uid)
        for bad in ("../../etc/passwd", "has space", "short", "a" * 200, "key.txt"):
            client.post("/admin/seo/token", data={"indexnow_key": bad, "csrf_token": tok})
            with app.app_context():
                assert Setting.query.filter_by(key="seo_indexnow_key_enc").first() is None, \
                    "非法 key %r 不应落库" % bad
        client.post("/admin/seo/token",
                    data={"indexnow_key": "abc12345-6789", "csrf_token": tok})
        with app.app_context():
            assert Setting.query.filter_by(key="seo_indexnow_key_enc").first() is not None
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_keys=True)


def test_secret_leave_blank_keeps_value(app, client):
    """留空提交不得清除已存凭据（留空语义 = 保持不变，清除需显式勾选）。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        tok = _auth(app, client, uid)
        client.post("/admin/seo/token", data={"baidu_token": "keepme-123456", "csrf_token": tok})
        with app.app_context():
            first = Setting.query.filter_by(key="seo_baidu_token_enc").first().value
        client.post("/admin/seo/token", data={"baidu_token": "", "csrf_token": tok})
        with app.app_context():
            assert Setting.query.filter_by(key="seo_baidu_token_enc").first().value == first
        # 显式清除才允许抹掉
        client.post("/admin/seo/token",
                    data={"clear_baidu_token": "1", "csrf_token": tok})
        with app.app_context():
            row = Setting.query.filter_by(key="seo_baidu_token_enc").first()
            assert row is None or row.value == ""
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_keys=True)


# ===========================================================================
# 三、CSRF：缺 token 必须 403
# ===========================================================================
def test_push_without_csrf_forbidden(app, client):
    """缺 CSRF token 的推送请求 → 403（全局 _csrf_protect 兜底）。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pid = _mkpost().id
    try:
        _auth(app, client, uid, with_csrf=False)     # 有会话、无 token
        r = client.post("/admin/seo/push", data={"engine": "baidu", "post_id": str(pid)})
        assert r.status_code == 403, "缺 CSRF token 必须 403，实得 %s" % r.status_code
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid], drop_keys=True)


def test_token_save_without_csrf_forbidden(app, client):
    """凭据保存缺 CSRF → 403（且不得落库）。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        _auth(app, client, uid, with_csrf=False)
        r = client.post("/admin/seo/token", data={"baidu_token": "nope-123456"})
        assert r.status_code == 403
        with app.app_context():
            assert Setting.query.filter_by(key="seo_baidu_token_enc").first() is None
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_keys=True)


# ===========================================================================
# 四、推送：不阻塞请求 + 异步落状态
# ===========================================================================
def test_push_returns_immediately_without_network(app, client, monkeypatch):
    """推送接口必须**立即返回**，且请求期间不发生任何外发。

    手法：把最底层出网口替换成「记录调用 + 抛错」。若接口同步跑外发，
    这个替身会在请求线程内被命中（并让测试失败）；正确实现下它只会在
    请求返回之后、后台线程里被调用。
    """
    called = []

    def _boom(*a, **kw):
        called.append(a)
        raise AssertionError("请求线程内发生了外发调用——推送必须异步")

    monkeypatch.setattr(seo_push, "_http_post", _boom)

    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pid = _mkpost().id
    try:
        tok = _auth(app, client, uid)
        r = client.post("/admin/seo/push",
                        data={"engine": "baidu", "post_id": str(pid), "csrf_token": tok})
        assert r.status_code in (302, 200), "接口应当立即返回"
        assert not called, "请求线程内不得发生外发（_http_post 被同步调用）"
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid], drop_base=True, drop_keys=True)


def test_enqueue_marks_pending(app, monkeypatch):
    """入队后记录应立刻是 pending（页面据此显示「排队中」）。

    做法：把后台线程启动替成 no-op，让记录停在 pending 状态可观测——
    否则后台线程会立刻把它改成最终状态，测试就成了竞态。
    """
    monkeypatch.setattr(seo_push, "_spawn", lambda *a, **kw: True)
    with app.app_context():
        p = _mkpost()
        pid = p.id
    try:
        with app.app_context():
            n = seo_push.enqueue([pid], "baidu")
            assert n == 1
            row = SeoSubmission.query.filter_by(post_id=pid, engine="baidu").first()
            assert row is not None and row.status == "pending"
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid])


def test_enqueue_starts_background_thread(app, monkeypatch):
    """enqueue 必须真的起线程（而不是同步跑完）——否则「立即返回」是假的。"""
    started = []
    real_thread = seo_push.threading.Thread

    class _FakeThread:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            started.append({"target": target, "args": args, "daemon": daemon})

        def start(self):
            started[-1]["started"] = True

    monkeypatch.setattr(seo_push.threading, "Thread", _FakeThread)
    with app.app_context():
        _mkbase()
        pid = _mkpost().id
    try:
        with app.app_context():
            seo_push.enqueue([pid], "baidu")
        assert started and started[0]["started"] is True, "必须启动后台线程"
        assert started[0]["daemon"] is True, "守护线程——否则进程退出会被卡住"
    finally:
        monkeypatch.setattr(seo_push.threading, "Thread", real_thread)
        with app.app_context():
            _cleanup(post_ids=[pid], drop_base=True)


# ===========================================================================
# 五、出站白名单与 URL 来源（安全红线）
# ===========================================================================
def test_outbound_host_whitelist_is_exact():
    """白名单必须精确比对 host——防 `data.zz.baidu.com.evil.com` 绕过。"""
    assert seo_push._is_allowed_url("http://data.zz.baidu.com/urls") is True
    assert seo_push._is_allowed_url("https://data.zz.baidu.com/urls") is True
    assert seo_push._is_allowed_url("https://api.bing.com/indexnow") is True
    # 经典绕过手法，必须全部拒绝
    assert seo_push._is_allowed_url("http://data.zz.baidu.com.evil.com/urls") is False
    assert seo_push._is_allowed_url("http://evil.com/http://data.zz.baidu.com") is False
    assert seo_push._is_allowed_url("http://data.zz.baidu.com@evil.com/") is False
    # 除百度外的 http 一律拒（本项目只此一个 http 例外）
    assert seo_push._is_allowed_url("http://api.bing.com/indexnow") is False
    assert seo_push._is_allowed_url("http://example.com/") is False
    assert seo_push._is_allowed_url("ftp://data.zz.baidu.com/") is False


def test_blocked_host_never_sends(monkeypatch):
    """白名单外的目标必须返回 blocked-host，且**不发起真实网络请求**。"""
    import urllib.request
    opened = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: opened.append(a) or (_ for _ in ()).throw(
                            AssertionError("不该发起请求")))
    st, txt, _ct = seo_push._http_post("http://evil.example.com/steal", b"x")
    assert st == 0 and "blocked-host" in txt
    assert not opened


def test_push_urls_use_site_base_not_request_host(app):
    """推送 URL 必须由 site_base() 生成，**不受请求 Host 影响**。

    首轮审计 2.9 的同一类问题：不能让请求方提供的 Host 决定我们对外声明的地址。
    这里直接以「命中 site_base()」为准，并断言绝不等于伪造 Host。
    """
    seen = {}

    def _capture(urls, token, site_domain=""):
        seen["urls"] = list(urls)
        seen["domain"] = site_domain
        return "ok", "ok", None

    with app.app_context():
        _mkbase("https://www.llhhy.cn")
        p = _mkpost()
        pid, slug = p.id, p.slug
        real = seo_push.push_baidu
        seo_push.push_baidu = _capture
        try:
            seo_push.submit_posts([pid], "baidu")
        finally:
            seo_push.push_baidu = real
        assert seen["urls"] == ["https://www.llhhy.cn/post/" + slug], \
            "URL 必须来自 site_base()，实得 %r" % (seen.get("urls"),)
        assert "evil.example.com" not in (seen.get("domain") or "")
        assert seen["domain"] == "https://www.llhhy.cn"
    with app.app_context():
        _cleanup(post_ids=[pid], drop_base=True)


def test_push_aborts_when_site_base_missing(app, monkeypatch):
    """site_base() 为空时必须全批落 fail、给出可读原因，**不发请求、不抛异常**。"""
    hit = []

    def _should_not_run(*a, **k):
        hit.append(1)
        return "ok", "", None

    monkeypatch.setattr(seo_push, "push_baidu", _should_not_run)
    monkeypatch.setattr(seo_push, "push_indexnow", _should_not_run)
    with app.app_context():
        _clearbase()
        pid = _mkpost().id
    try:
        with app.app_context():
            ok, fail, summary = seo_push.submit_posts([pid], "baidu")
            assert ok == 0 and fail == 1
            assert ("site_base" in summary) or ("站点" in summary), \
                "必须给出可读原因，实得 %r" % summary
            assert not hit, "站点地址未配置时不得发起外发请求"
            row = SeoSubmission.query.filter_by(post_id=pid, engine="baidu").first()
            assert row is not None and row.status == "fail"
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], drop_base=True)


# ===========================================================================
# 六、不可见文章不予推送
# ===========================================================================
def test_invisible_post_push_rejected(app, client):
    """草稿/隐私/回收站/未到点定时的文章 → 单篇推送被拒，且不建推送记录。"""
    from datetime import timedelta
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pids = [
            _mkpost(published=False).id,
            _mkpost(is_private=True).id,
            _mkpost(in_trash=True).id,
            _mkpost(published=True, scheduled_at=utcnow() + timedelta(days=2)).id,
        ]
    try:
        tok = _auth(app, client, uid)
        for pid in pids:
            r = client.post("/admin/seo/push",
                            data={"engine": "baidu", "post_id": str(pid), "csrf_token": tok})
            assert r.status_code in (302, 200)
        with app.app_context():
            rows = SeoSubmission.query.filter(SeoSubmission.post_id.in_(pids)).all()
            assert rows == [], "不可见文章不得产生推送记录（应被直接拒绝）"
    finally:
        with app.app_context():
            _cleanup(post_ids=pids, user_ids=[uid])


def test_push_rejected_posts_get_audit_log(app, client):
    """拒绝不可见文章时必须留审计痕迹（事后可追溯谁尝试推了隐私文）。"""
    from models import AuditLog
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pid = _mkpost(is_private=True).id
    try:
        tok = _auth(app, client, uid)
        client.post("/admin/seo/push",
                    data={"engine": "baidu", "post_id": str(pid), "csrf_token": tok})
        with app.app_context():
            log = AuditLog.query.filter_by(action="seo_push_reject").order_by(
                AuditLog.id.desc()).first()
            assert log is not None, "拒绝推送应写审计日志"
            AuditLog.query.filter_by(action="seo_push_reject").delete(
                synchronize_session=False)
            db.session.commit()
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid])


# ===========================================================================
# 七、响应清洗：token 不得出现在入库文本中
# ===========================================================================
def test_response_text_strips_token(monkeypatch):
    """即使上游把请求 URL（含 token）回显在错误里，入库文本也必须已抹掉。"""
    token = "tok-" + secrets.token_hex(8)
    monkeypatch.setattr(
        seo_push, "_http_post",
        lambda *a, **k: (401, '{"error":401,"message":"bad",'
                              '"url":"http://data.zz.baidu.com/urls?token=%s"}' % token,
                         "application/json"))
    st, resp, _ = seo_push.push_baidu(["https://x.cn/post/a"], token, "https://x.cn")
    assert st == "fail"
    assert token not in resp, "响应回显里的 token 必须被抹掉，否则页面/日志泄露密钥"


def test_redact_happens_before_truncation(monkeypatch):
    """**脱敏必须在截断之前**（v3.19.1 修的缺陷）。

    v3.19.0 是 `_clean(text).replace(token, "***")`——先截断到 500 字符再替换。
    若 token 出现在第 500 字符之后，替换不再命中，密钥会入库并上屏。
    这里把 token 放在 600 字符之后，断言仍然被抹掉。
    """
    token = "TOKEN" + secrets.token_hex(12)
    # 构造：前 600 字符是噪音，token 落在截断点之后
    padded = "x" * 600
    monkeypatch.setattr(
        seo_push, "_http_post",
        lambda *a, **k: (401, padded + " token=" + token, "application/json"))
    st, resp, _ = seo_push.push_baidu(["https://x.cn/post/a"], token, "https://x.cn")
    assert st == "fail"
    assert token not in resp, \
        "token 落在截断点之后仍必须被抹掉（先脱敏、后截断）"
    assert token[:24] not in resp, "整串之外还要抹前缀片段"

    # 直接测 _clean 的顺序契约
    out = seo_push._clean("y" * 600 + " tok=" + token, secrets=(token,))
    assert token not in out


def test_indexnow_response_strips_key(monkeypatch):
    """IndexNow 的 key 同样不得出现在入库文本里。"""
    key = "abcdef1234567890"
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (400, '{"error":"invalid key %s"}' % key,
                                         "application/json"))
    st, resp, _ = seo_push.push_indexnow(["https://x.cn/post/a"], key, "https://x.cn")
    assert st == "fail" and key not in resp


def test_clean_truncates_and_flattens():
    """入库文本必须压平换行并截断。"""
    out = seo_push._clean("a\nb\r\nc" + "x" * 1000)
    assert "\n" not in out and "\r" not in out
    assert len(out) <= seo_push.RESP_KEEP


def test_baidu_quota_status(monkeypatch):
    """配额耗尽必须单独成 quota 档（否则用户会误以为是 token 填错）。"""
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"error":400,"message":"over quota"}',
                                         "application/json"))
    st, _resp, remaining = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "quota"
    # remaining 为 0 也应归 quota
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"success":0,"remaining":0}',
                                         "application/json"))
    st2, _r2, rem2 = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st2 == "quota" and rem2 == 0


def test_baidu_ok_parses_remaining(monkeypatch):
    """成功必须解析出剩余配额供页面展示。

    **字段名是 `remain`**（v3.19.2 由生产数据实证：`{"remain":8,"success":1}`），
    不是 `remaining`。v3.19.0/v3.19.1 读错名字 → 剩余配额永远读不到，
    收录页配额栏一直空白。两个名字都断言，避免以后再改错。
    """
    # 真实字段名
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"remain":998,"success":2}',
                                         "application/json"))
    st, resp, remaining = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "ok" and remaining == 998, "必须解析 Baidu 真实的 `remain` 字段"
    assert "remain" in resp, "`remain` 必须在响应白名单里，否则配额被一起丢掉"

    # 兼容旧写法
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"success":1,"remaining":77}',
                                         "application/json"))
    st2, _r2, rem2 = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st2 == "ok" and rem2 == 77

    # `remain:0` 且 success:0 → 配额耗尽（有了正确字段名这条判定才真正生效）
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"remain":0,"success":0}',
                                         "application/json"))
    st3, _r3, rem3 = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st3 == "quota" and rem3 == 0, "remain=0 必须归 quota 档"


def test_baidu_non_json_200_is_not_success(monkeypatch):
    """**HTTP 200 但响应不是 JSON → 必须判 fail，不得记成功**（v3.19.1）。

    v3.19.0 的实现是 `return ("ok" if status == 200 else "fail")`——于是一个
    伪造的 200（或被劫持链路上的 HTML 错误页）就能让控制台显示「成功」，
    还会写入虚假配额。这是「半盲 SSRF」的放大器之一。
    """
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, "<html>captive portal</html>", "text/html"))
    st, resp, _rem = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "fail", "非 JSON 的 200 不得记成功，实得 %r" % st

    # Content-Type 明确非 JSON 时，即使 body 能解析出 JSON 也判 fail
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"success":5,"remaining":10}', "text/html"))
    st2, _r2, _rem2 = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st2 == "fail", "Content-Type 非 JSON 时不认成功"


def test_response_only_keeps_whitelisted_fields(monkeypatch):
    """入库/上屏的响应只保留白名单字段（v3.19.1：防内容回显）。"""
    monkeypatch.setattr(
        seo_push, "_http_post",
        lambda *a, **k: (200, '{"success":2,"remaining":7,'
                              '"injected":"<script>alert(1)</script>",'
                              '"arbitrary":"whatever"}', "application/json"))
    st, resp, _rem = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "ok"
    assert "script" not in resp, "非白名单字段不得入库/上屏"
    assert "arbitrary" not in resp
    assert "remaining" in resp and "success" in resp


# ===========================================================================
# 八、预览与自检
# ===========================================================================
def test_preview_reuses_existing_views(app, client):
    """sitemap/robots 预览必须直接复用既有视图（不重写生成逻辑）。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        _auth(app, client, uid)
        for kind, needle in (("sitemap", "<urlset"), ("robots", "User-agent")):
            r = client.get("/admin/seo/preview?kind=%s" % kind)
            assert r.status_code == 200
            body = r.get_json()["body"]
            assert needle in body, "%s 预览内容不对" % kind
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid])


def test_selfcheck_calls_the_real_gate(app, client):
    """自检必须**真调闸门函数**，且真人项不得被判成「可索引壳页」。

    **v3.19.1 修正（原 test_selfcheck_flags_human_misjudgement）**：
    v3.19.0 的 `/admin/seo/selfcheck` 用本地重写的公式复刻闸门
    （缺 `is_internal_referer()` 与 `Sec-Fetch-Dest: document` 两道否决），
    而 `seo_shell_ua` 导入后从未调用——闸门改了、自检页仍显示全绿。
    现在它直接调 `seo_shell_ua()`，这条测试同时锁住判定口径与真人安全。
    """
    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        _auth(app, client, uid)
        d = client.get("/admin/seo/selfcheck").get_json()
        assert d["configured"] is True
        by_expect = {}
        for c in d["checks"]:
            by_expect.setdefault(c["expect"], []).append(c)
        assert len(by_expect.get("shell", [])) == 3, \
            "应有 3 个抓取方用例（百度 / Google / 微信）"
        assert len(by_expect.get("noindex", [])) == 1, "应有 1 个真人用例（QQ）"
        assert len(by_expect.get("404", [])) == 1, "应有 1 个普通浏览器用例（Chrome）"
        assert all(c["ok"] for c in d["checks"]), \
            "闸门判定与预期不符：%r" % d["checks"]
        # 真人两条**绝不能**是可索引壳页
        for label in ("QQ", "Chrome"):
            c = [x for x in d["checks"] if label in x["label"]][0]
            assert c["allow"] is False, "%s 不该被放行" % label
            assert c["got"] in ("noindex", "404"), \
                "%s 被判成「可索引壳页」= 生产事故" % label
        qq = [c for c in d["checks"] if "QQ" in c["label"]][0]
        assert qq["got"] == "noindex" and qq["reason"].startswith("human"), \
            "QQ 内置浏览器真人必须被判为真人（否则打不开页面）"
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_base=True)


def test_selfcheck_not_configured(app, client):
    """site_url 未配置时 configured=False（页面据此红字提示）。"""
    with app.app_context():
        _clearbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        _auth(app, client, uid)
        d = client.get("/admin/seo/selfcheck").get_json()
        assert d["configured"] is False
        assert d["all_ok"] is False
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_base=True)


def test_console_and_status_never_expose_token(app, client):
    """收录页与状态接口都不得出现 token 的**明文或密文**。

    **v3.19.1 修正**：原断言是
    `assert "token" not in str(d).lower() or "baidu_token" not in str(d)`
    —— 两个子句都只查**键名**，且用 `or` 连接，任一成立即通过；把 token 的
    **值**原样吐给页面时第一个子句为真 → 断言恒成立（等于空转，报告 2.7-1）。
    现在真的存一个凭据，断言明文与密文都不出现在两个响应里。
    """
    plain = "SECRET" + secrets.token_hex(8)
    with app.app_context():
        import backup_settings as bs
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        enc = bs.encrypt_secret(plain)
        Setting.query.filter_by(key="seo_baidu_token_enc").delete()
        db.session.add(Setting(key="seo_baidu_token_enc", value=enc))
        pid = _mkpost().id
        db.session.add(SeoSubmission(post_id=pid, engine="baidu", status="ok", response="x"))
        db.session.commit()
    try:
        _auth(app, client, uid)

        page = client.get("/admin/seo").get_data(as_text=True)
        assert plain not in page, "收录页泄露了 token 明文"
        assert enc not in page, "收录页泄露了 token 密文"
        assert "••••" in page, "有值时应收敛成掩码回显"

        d = client.get("/admin/seo/status")
        assert d.status_code == 200
        body = d.get_data(as_text=True)
        assert plain not in body, "状态接口泄露了 token 明文"
        assert enc not in body, "状态接口泄露了 token 密文"

        js = d.get_json()
        assert "counts" in js and "rows" in js and "quota" in js
        assert js["counts"]["ok"] >= 1
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid], drop_keys=True)


def test_console_page_renders(app, client):
    """收录页本身必须能 200 渲染（模板语法/url_for 全部可用）。"""
    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pid = _mkpost().id
    try:
        _auth(app, client, uid)
        r = client.get("/admin/seo")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        for needle in ("收录控制台", "爬虫通道自检", "IndexNow", "只读预览", "gsc",
                       "search.google.com"):
            assert needle.lower() in body.lower(), "页面缺少 %r" % needle
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid], drop_base=True)


def test_console_page_renders_without_site_url(app, client):
    """site_url 未配置时页面也必须能渲染（并给出红字提示），不得 500。"""
    with app.app_context():
        _clearbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        _auth(app, client, uid)
        r = client.get("/admin/seo")
        assert r.status_code == 200, "site_url 未配置也必须能打开页面"
        assert "site_url" in r.get_data(as_text=True)
    finally:
        with app.app_context():
            _cleanup(user_ids=[uid], drop_base=True)


def test_shell_check_requires_super_and_never_goes_out(app, client, monkeypatch):
    """`/api/seo/shell-check` 现在：① 需超管 ② **零出网** ③ 经通道不出 3xx。

    **v3.19.1 修正（原 test_shell_check_endpoint_untouched）**：
    v3.19.0 该端点**匿名可调**且内部用 `urllib` 回打公网地址 4 次（自请求放大面，
    占住 worker 等自己返回）；而旧测试只断言 `200 or 400` 且**不 stub urlopen**——
    是全库唯一可能真出网的测试（报告 2.7-3）。现在把 urlopen 打成「命中即抛错」，
    既验证零出网，也保证这条测试永远不再触网。
    """
    import urllib.request

    def _boom(*a, **k):
        raise AssertionError("自检端点不得发起任何网络请求（应走 test_request_context）")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with app.app_context():
        pid = _mkpost().id
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
    try:
        # 匿名 → 403（v3.19.0 是 200，任何访客都能触发 4 次自请求）
        r0 = client.get("/api/seo/shell-check?slug=x")
        assert r0.status_code == 403, "自检端点必须只给超管，实得 %s" % r0.status_code

        # 超管 → 200，且全部在本地请求上下文里完成（零出网）
        _auth(app, client, uid)
        r = client.get("/api/seo/shell-check")
        assert r.status_code == 200, r.get_data(as_text=True)[:200]
        d = r.get_json()
        assert d["all_ok"] is True, d.get("checks")
        for c in d["checks"]:
            assert c["would_loop"] is False, \
                "经通道出现 3xx = 302 环：%r" % c
            assert c["status"] in (200, 404), \
                "经通道只允许 200/404：%r" % c
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid], drop_base=True)


# ===========================================================================
# 九、v3.19.1 复审修复项（报告 2.2 / 2.4 / 2.5 / 2.8 / 2.9）
# ===========================================================================
def test_redirect_is_not_followed(monkeypatch):
    """**出站禁跟随重定向**（报告 2.2，半盲 SSRF）。

    用两个本地 HTTP 服务复现：白名单里的第一个返回 `302 → 第二个`，
    断言「第二个从未收到请求」。v3.19.0 用默认 opener，urllib 会把 POST 降级成
    GET 跟过去——本地实测确实发生（这正是报告认定的 SSRF 面）。

    做法：把白名单临时改成只放行第一个服务，既复现真实路径，
    又不必真的连到 `data.zz.baidu.com`。
    """
    import http.server
    import socketserver
    import threading as _th

    hits = []
    evil_port = [0]

    class _Redirector(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append("redirector:POST")
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/steal" % evil_port[0])
            self.end_headers()

        def log_message(self, *a):
            pass

    class _Evil(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append("EVIL:GET")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"leaked":"internal"}')

        def do_POST(self):
            hits.append("EVIL:POST")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"evil")

        def log_message(self, *a):
            pass

    evil = socketserver.TCPServer(("127.0.0.1", 0), _Evil)
    evil_port[0] = evil.server_address[1]
    red = socketserver.TCPServer(("127.0.0.1", 0), _Redirector)
    rp = red.server_address[1]
    for s in (red, evil):
        _th.Thread(target=s.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(seo_push, "_is_allowed_url",
                            lambda u: ("127.0.0.1:%d" % rp) in u)
        st, _txt, _ct = seo_push._http_post("http://127.0.0.1:%d/urls" % rp, b"urls=a",
                                            timeout=5)
        assert "redirector:POST" in hits, "请求本身应发出"
        assert not any(h.startswith("EVIL") for h in hits), \
            "**不得跟随 302 到白名单外主机**（半盲 SSRF）——实得 %r" % hits
        assert st in (301, 302, 303, 307, 308), \
            "3xx 应原样返回给调用方落 fail，实得 %r" % st
    finally:
        red.shutdown()
        evil.shutdown()


def test_thread_exception_marks_fail_instead_of_stuck_pending(app, monkeypatch):
    """**后台线程异常必须落 fail，不能永久停在「排队中」**（报告 2.4）。

    v3.19.0 有两层 `except Exception: pass`：一旦 `submit_posts` 抛出，
    这批记录永远显示 ⏳ 排队中，页面轮询永远等不到结果，日志里也没有痕迹。

    做法：把 `submit_posts` 换成「一调就抛」，并把 Thread 换成**同步执行**的替身
    （否则断言会与真线程竞态）。
    """
    def _boom(*a, **k):
        raise ValueError("模拟后台线程崩溃")

    class _SyncThread:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self._t, self._a = target, args

        def start(self):
            self._t(*self._a)          # 同步跑完，便于断言

    monkeypatch.setattr(seo_push, "submit_posts", _boom)
    monkeypatch.setattr(seo_push.threading, "Thread", _SyncThread)
    with app.app_context():
        _mkbase()
        pid = _mkpost().id
    try:
        with app.app_context():
            seo_push.enqueue([pid], "baidu")
            row = SeoSubmission.query.filter_by(post_id=pid, engine="baidu").first()
            assert row is not None
            assert row.status == "fail", \
                "线程异常必须落 fail，不能停在 pending（实得 %s）" % row.status
            assert "异常" in (row.response or ""), "应写明是线程异常：%r" % row.response
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], drop_base=True)


def test_spawn_failure_marks_fail_and_reports_zero(app, monkeypatch):
    """`_spawn` 起不来线程时：落 fail + `enqueue` 返回 0（页面不再假报「已入队」）。"""
    monkeypatch.setattr(seo_push, "_spawn", lambda *a, **kw: False)
    with app.app_context():
        _mkbase()
        pid = _mkpost().id
    try:
        with app.app_context():
            n = seo_push.enqueue([pid], "baidu")
            assert n == 0, "起线程失败必须返回 0"
            row = SeoSubmission.query.filter_by(post_id=pid, engine="baidu").first()
            assert row is not None and row.status == "fail"
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], drop_base=True)


def test_push_audit_records_ip(app, client, monkeypatch):
    """推送审计必须带来源 IP（报告 2.4）。

    v3.19.0 手搓 `AuditLog(..., ip="")`，`get_client_ip` 导入了却没用——
    「谁、从哪个 IP 烧了配额」事后查不到。

    测法要点：后台线程体在**请求上下文之外**执行（真实情形如此），
    所以断言 IP 非空才能真正证明「IP 是在请求线程里捕获后传进来的」。
    做法：把 Thread 换成**只记录不执行**的替身，之后在 app_context 里手动跑线程体。
    """
    from models import AuditLog

    captured = {}

    class _CapturingThread:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(seo_push.threading, "Thread", _CapturingThread)
    monkeypatch.setattr(seo_push, "push_baidu", lambda *a, **k: ("ok", "success 1", 998))
    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        uname = u.username
        pid = _mkpost().id
    try:
        tok = _auth(app, client, uid)
        r = client.post("/admin/seo/push",
                        data={"engine": "baidu", "post_id": str(pid), "csrf_token": tok},
                        follow_redirects=False)
        assert r.status_code == 302
        assert captured.get("started"), "应启动后台线程"
        assert captured.get("daemon") is True

        # 在**请求上下文之外**执行线程体（= 真实的后台线程情形）
        with app.app_context():
            captured["target"](*captured["args"])
            row = (AuditLog.query.filter_by(action="seo_push")
                   .order_by(AuditLog.id.desc()).first())
            assert row is not None, "必须写 seo_push 审计"
            assert row.username == uname
            assert (row.ip or "") != "", \
                "审计 IP 为空——说明 IP 没有在请求线程里捕获（v3.19.0 的缺陷）"
    finally:
        with app.app_context():
            AuditLog.query.filter_by(action="seo_push").delete(synchronize_session=False)
            db.session.commit()
            _cleanup(post_ids=[pid], user_ids=[uid], drop_base=True)


def test_push_endpoint_is_rate_limited(app, client, monkeypatch):
    """推送接口必须限流（报告 2.5）：百度配额用完不可逆，连点会打光配额。

    注意：这里必须把 `_spawn` 替成 no-op。否则会起**真实后台线程**，而线程
    可能在用例清理**之后**才写回记录 → 留下残留行 + post id 被复用 → 后续用例
    撞 `(post_id, engine)` 唯一约束（本文件踩到过）。
    """
    monkeypatch.setattr(seo_push, "_spawn", lambda *a, **kw: True)
    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pids = [_mkpost().id for _ in range(3)]
    try:
        tok = _auth(app, client, uid)
        for pid in pids + [pids[0], pids[1]]:
            client.post("/admin/seo/push",
                        data={"engine": "baidu", "post_id": str(pid), "csrf_token": tok},
                        follow_redirects=False)
        with app.app_context():
            rows = SeoSubmission.query.filter_by(engine="baidu").count()
            assert rows <= 3, \
                "5 分钟内超过 3 次仍入队 = 限流没生效（实得 %d 行）" % rows
    finally:
        with app.app_context():
            _cleanup(post_ids=pids, user_ids=[uid], drop_base=True)


def test_push_refused_while_another_batch_pending(app, client):
    """已有 pending 批次时必须拒绝新推送（在飞去重，报告 2.5）。"""
    with app.app_context():
        _mkbase()
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        p1 = _mkpost()
        p2 = _mkpost()
        p1id, p2id = p1.id, p2.id
        # 防御：本用例假设「该 post 还没有推送记录」，但 SQLite 会复用被删行的
        # rowid（前面用例删过文章后，新文章可能拿到同一个 id）——先清干净。
        SeoSubmission.query.filter(
            SeoSubmission.post_id.in_([p1id, p2id])).delete(synchronize_session=False)
        db.session.add(SeoSubmission(post_id=p1id, engine="baidu", status="pending"))
        db.session.commit()
    try:
        tok = _auth(app, client, uid)
        r = client.post("/admin/seo/push",
                        data={"engine": "baidu", "post_id": str(p2id), "csrf_token": tok},
                        follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            rows = SeoSubmission.query.filter_by(post_id=p2id, engine="baidu").all()
            assert rows == [], "有 pending 批次时不得再入队新推送"
    finally:
        with app.app_context():
            _cleanup(post_ids=[p1id, p2id], user_ids=[uid], drop_base=True)


def test_keylocation_is_validated():
    """`keyLocation` 必须由合法 site_url 构造（报告 2.9）。

    `host` 来自后台可填的 `site_url`：填成别的域名等于把 key 的 URL 路径
    告知那个域名的持有者；带 query/fragment/userinfo 会拼出非法或钓鱼式 URL。
    """
    assert seo_push._keylocation("https://www.llhhy.cn", "abc12345") == \
        "https://www.llhhy.cn/abc12345.txt"
    # 带子路径：保留 path（站点可能部署在子目录）
    assert seo_push._keylocation("https://x.cn/blog", "abc12345") == \
        "https://x.cn/blog/abc12345.txt"
    for bad in ("", "ftp://x.cn", "https://", "https://x.cn?a=1",
                "https://x.cn#f", "https://user:pw@x.cn", "not a url"):
        assert seo_push._keylocation(bad, "abc12345") == "", \
            "非法 site_url 必须被拒：%r" % bad


def test_indexnow_bad_key_or_host_fails_without_network(monkeypatch):
    """key 格式非法 / site_url 非法时，IndexNow 必须**不出网**直接 fail。"""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("不该发起请求")))
    st, resp, _ = seo_push.push_indexnow(["https://x.cn/post/a"], "bad key!!", "https://x.cn")
    assert st == "fail" and "key" in resp
    st2, resp2, _ = seo_push.push_indexnow(["https://x.cn/post/a"],
                                           "abcdef1234567890", "ftp://x.cn")
    assert st2 == "fail" and "site_url" in resp2


def test_purge_removes_seo_submission_rows(app, client):
    """彻底删除文章时必须清掉它的推送记录（报告 2.8）。

    SQLite 默认不启用外键（`app.py` 未设 `PRAGMA foreign_keys=ON`），
    所以 `seo_submission` 的 FK 不会级联——不显式删就留下 `post_id` 悬空行。
    """
    from models import RecycleBin

    with app.app_context():
        u = _mkuser(ROLE_ADMIN)
        uid = u.id
        p = _mkpost()
        pid = p.id
        db.session.add(SeoSubmission(post_id=pid, engine="baidu", status="ok", response="x"))
        rb = RecycleBin(post_id=pid, title=p.title)
        db.session.add(rb)
        db.session.commit()
        rid = rb.id
    try:
        tok = _auth(app, client, uid)
        r = client.post("/admin/recycle-bin/%d/purge" % rid,
                        data={"csrf_token": tok},
                        follow_redirects=False)
        assert r.status_code in (200, 302), r.status_code
        with app.app_context():
            assert Post.query.get(pid) is None, "文章应已被彻底删除"
            left = SeoSubmission.query.filter_by(post_id=pid).all()
            assert left == [], "彻底删除后不得留下孤儿推送记录：%r" % left
    finally:
        with app.app_context():
            SeoSubmission.query.filter_by(post_id=pid).delete(synchronize_session=False)
            RecycleBin.query.filter_by(id=rid).delete(synchronize_session=False)
            Post.query.filter_by(id=pid).delete(synchronize_session=False)
            _cleanup(post_ids=[pid], user_ids=[uid])


# ===========================================================================
# 九、v3.20.0：发布即自动推送（seo_push.maybe_auto_push）
#     —— 默认关闭 + 防配额烧掉 + 不推不可见 URL
# ===========================================================================
def test_maybe_auto_push_disabled_by_default_is_noop(app):
    """默认关闭（不读 env / 不读 setting）→ 返回 0，且**不创建任何** SeoSubmission。"""
    os.environ.pop("SEO_AUTO_PUSH", None)
    with app.app_context():
        Setting.query.filter_by(key=seo_push.AUTO_PUSH_KEY).delete(synchronize_session=False)
        db.session.commit()
        p = _mkpost(published=True)
        pid = p.id
        before = SeoSubmission.query.count()
        n = seo_push.maybe_auto_push(p)
        after = SeoSubmission.query.count()
        _cleanup(post_ids=[pid])
    assert n == 0, "默认关闭时应返回 0"
    assert after == before, "默认关闭时不得产生推送记录（百度配额只剩 2，不能自动烧）"


def test_maybe_auto_push_enabled_enqueues_visible(app):
    """开启（SEO_AUTO_PUSH=1）+ 已发布可见文章 → 为每个引擎入队（建 pending 行）。"""
    os.environ["SEO_AUTO_PUSH"] = "1"
    pids = []
    try:
        with app.app_context():
            p = _mkpost(published=True)
            pid = p.id
            pids.append(pid)
            n = seo_push.maybe_auto_push(p)
            rows = SeoSubmission.query.filter_by(post_id=pid).all()
        assert n == len(seo_push.ENGINES), "返回数应等于引擎数"
        assert {r.engine for r in rows} == set(seo_push.ENGINES)
        # ⚠️ 不卡 status=="pending"：enqueue 建的是 pending 行，但后台线程会异步
        # 把它改成 ok/fail（无凭据时通常 fail）。行已创建 + 引擎集合正确即达标。
        assert all(r.status in ("pending", "ok", "fail") for r in rows)
    finally:
        os.environ.pop("SEO_AUTO_PUSH", None)
        with app.app_context():
            _cleanup(post_ids=pids)


def test_maybe_auto_push_refuses_invisible(app):
    """开启但文章在回收站 / 私密 / 定时未到 → 一律拒绝（不推不可见 URL 给搜索引擎）。"""
    os.environ["SEO_AUTO_PUSH"] = "1"
    pids = []
    try:
        with app.app_context():
            for kw in ({"in_trash": True},
                       {"is_private": True},
                       {"scheduled_at": utcnow() + timedelta(days=1)}):
                p = _mkpost(published=True, **kw)
                pid = p.id
                pids.append(pid)
                n = seo_push.maybe_auto_push(p)
                cnt = SeoSubmission.query.filter_by(post_id=pid).count()
                assert n == 0 and cnt == 0, "不可见文章不得推送：%r" % kw
    finally:
        os.environ.pop("SEO_AUTO_PUSH", None)
        with app.app_context():
            _cleanup(post_ids=pids)


def test_maybe_auto_push_none_is_safe(app):
    """调用参数为 None / 无 id → 不抛异常，返回 0（发布主流程不因此崩）。"""
    os.environ["SEO_AUTO_PUSH"] = "1"
    try:
        with app.app_context():
            assert seo_push.maybe_auto_push(None) == 0
    finally:
        os.environ.pop("SEO_AUTO_PUSH", None)
