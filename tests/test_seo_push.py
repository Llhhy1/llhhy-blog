"""v3.19.0 阶段 2 回归测试 —— 后台「🔍 收录」页：主动推送 + 凭据安全。

清单 2 的验收口径逐条落地：token 密文存储 / 非超管 403 / 缺 CSRF 403 /
推送不阻塞请求 / URL 不来自 `request.host` / 不可见文章不予推送。

另有两条**不在清单字面但真会出事**的断言，一并锁住：
- 出站 host 白名单必须精确（`data.zz.baidu.com.evil.com` 不能过）；
- 响应回显里的 token 必须被抹掉（否则「页面不回显明文」当场失效）。
"""
import secrets

from models import (db, Post, Setting, User, SeoSubmission,
                    ROLE_SUPER, ROLE_ADMIN)
from _time import utcnow
from utils import _sign_csrf

import seo_push


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
    st, txt = seo_push._http_post("http://evil.example.com/steal", b"x")
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
                              '"url":"http://data.zz.baidu.com/urls?token=%s"}' % token))
    st, resp, _ = seo_push.push_baidu(["https://x.cn/post/a"], token, "https://x.cn")
    assert st == "fail"
    assert token not in resp, "响应回显里的 token 必须被抹掉，否则页面/日志泄露密钥"


def test_indexnow_response_strips_key(monkeypatch):
    """IndexNow 的 key 同样不得出现在入库文本里。"""
    key = "abcdef1234567890"
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (400, '{"error":"invalid key %s"}' % key))
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
                        lambda *a, **k: (200, '{"error":400,"message":"over quota"}'))
    st, _resp, remaining = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "quota"
    # remaining 为 0 也应归 quota
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"success":0,"remaining":0}'))
    st2, _r2, rem2 = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st2 == "quota" and rem2 == 0


def test_baidu_ok_parses_remaining(monkeypatch):
    """成功必须解析出 remaining 供页面展示配额。"""
    monkeypatch.setattr(seo_push, "_http_post",
                        lambda *a, **k: (200, '{"success":1,"remaining":998}'))
    st, _resp, remaining = seo_push.push_baidu(["https://x.cn/post/a"], "t", "https://x.cn")
    assert st == "ok" and remaining == 998


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


def test_selfcheck_flags_human_misjudgement(app, client):
    """自检必须同时验证抓取方与**真人**——后者才是防生产事故的关键项。"""
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
        assert len(by_expect.get("shell", [])) == 2, "应有 2 个抓取方用例"
        assert len(by_expect.get("spa", [])) == 2, "应有 2 个真人用例"
        assert all(c["ok"] for c in d["checks"]), \
            "闸门判定与预期不符：%r" % d["checks"]
        qq = [c for c in d["checks"] if "QQ" in c["label"]][0]
        assert qq["got"] == "spa" and qq["human_signal"] is True, \
            "QQ 内置浏览器真人必须被判为真人（否则真人会看到空白壳页）"
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


def test_status_endpoint_shape(app, client):
    """状态接口返回 counts 与 quota，供页面轮询渲染。"""
    with app.app_context():
        u = _mkuser(ROLE_SUPER)
        uid = u.id
        pid = _mkpost().id
        db.session.add(SeoSubmission(post_id=pid, engine="baidu", status="ok", response="x"))
        db.session.commit()
    try:
        _auth(app, client, uid)
        d = client.get("/admin/seo/status").get_json()
        assert "counts" in d and "rows" in d and "quota" in d
        assert d["counts"]["ok"] >= 1
        # 状态接口绝不能泄露 token
        assert "token" not in str(d).lower() or "baidu_token" not in str(d)
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid], user_ids=[uid])


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


def test_shell_check_endpoint_untouched(app, client):
    """阶段 1 的 /api/seo/shell-check 必须仍可用（本轮不改它的语义）。"""
    with app.app_context():
        pid = _mkpost().id
    try:
        r = client.get("/api/seo/shell-check?slug=whatever")
        assert r.status_code in (200, 400), "既有端点行为不应被本轮改动影响"
    finally:
        with app.app_context():
            _cleanup(post_ids=[pid])
