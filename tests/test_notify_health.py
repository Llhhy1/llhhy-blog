# -*- coding: utf-8 -*-
"""v3.20.0 新增：通知异步化 + 存活探针 的回归测试。

本文件守着三件**容易做错且错了很隐蔽**的事：

1. **通知必须离开请求线程**（原为同步，每渠道 timeout=6，两渠道齐配最坏阻塞 12s）。
2. **跨线程不能传 ORM 对象** —— 调用点都在 `db.session.commit()` 之后，
   提交会过期全部属性，而后台线程用的是**新 session**，访问属性必抛
   `DetachedInstanceError`，再被 `except Exception` 吞掉 → 「通知静默不发」。
   `notify.py` 靠「请求线程内先取快照」规避；`mail_notify.py` 靠「传 id、线程内重查」。
3. **`/health` 不得泄露信息、不得出网、不得反向放大**。
"""
import secrets

import pytest

from models import db, Post, Subscriber

import mail_notify
import notify


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
class _CapturingThread:
    """记录线程体但不执行 —— 便于把「请求线程阶段」和「后台线程阶段」分开断言。"""

    instances = []

    def __init__(self, target=None, args=(), daemon=None, **kw):
        self.target, self.args, self.daemon = target, args, daemon
        self.started = False
        _CapturingThread.instances.append(self)

    def start(self):
        self.started = True

    def run_now(self):
        """在**当前上下文**里执行线程体（模拟后台线程）。"""
        self.target(*self.args)


@pytest.fixture
def cap_thread(monkeypatch):
    _CapturingThread.instances = []
    monkeypatch.setattr(notify.threading, "Thread", _CapturingThread)
    monkeypatch.setattr(mail_notify.threading, "Thread", _CapturingThread)
    return _CapturingThread


@pytest.fixture
def clean_env(monkeypatch):
    """清掉推送渠道环境变量；需要时由用例自己设。"""
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WECOM_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)


def _tok():
    return secrets.token_hex(4)


def _mkpost(title="通知测试标题", **kw):
    p = Post(title=title, slug="ntf-" + _tok(), content=kw.pop("content", "正文内容"),
             summary=kw.pop("summary", "摘要"), published=True,
             in_trash=False, is_private=False, **kw)
    db.session.add(p)
    db.session.commit()
    return p


def _cleanup_post(pid):
    Subscriber.query.filter(Subscriber.email.like("ntf-%")).delete(
        synchronize_session=False)
    Post.query.filter_by(id=pid).delete(synchronize_session=False)
    db.session.commit()


# ---------------------------------------------------------------------------
# 一、notify.py：异步 + 快照
# ---------------------------------------------------------------------------
def test_notify_does_not_send_in_request_thread(app, cap_thread, clean_env, monkeypatch):
    """请求线程内**不得**发生外发（否则「异步」是假的）。"""
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(notify, "_tg_send", lambda token, chat, text: sent.append(text))

    with app.app_context():
        p = _mkpost()
        pid = p.id
        try:
            notify.notify_new_post(p, "https://x.cn")
            assert sent == [], "请求线程内发生了外发 —— 保存文章会被阻塞 6~12s"
            assert cap_thread.instances and cap_thread.instances[-1].started, \
                "必须启动后台线程"
            assert cap_thread.instances[-1].daemon is True, "应为守护线程"
        finally:
            _cleanup_post(pid)


def test_notify_works_when_post_is_detached(app, cap_thread, clean_env, monkeypatch):
    """**核心用例**：`commit()` 之后再调通知，后台线程仍必须拿到文章内容。

    复现真实调用序（见 `admin/post_editor.py`）：
        1. `db.session.commit()`
        2. `notify.notify_new_post(post, …)`
        3. 请求结束 → app context 弹出 → session 被移除 → 对象 detached

    本用例断言：① 该对象此刻**确实**是 detached（前置条件，否则没模拟到真实场景）；
    ② 快照已把标题带入后台阶段 → 通知照常发出。
    """
    from sqlalchemy import inspect as sa_inspect

    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(notify, "_tg_send", lambda token, chat, text: sent.append(text))

    pid = None
    try:
        with app.app_context():
            p = _mkpost(title="快照标题-" + _tok())
            expected = p.title
            pid = p.id
            db.session.commit()          # ← 与真实调用序一致：先提交
            notify.notify_new_post(p, "https://x.cn")
        # app context 已弹出 → 新 session 才是「后台线程里」的语境

        with app.app_context():
            # 前置条件：证明对象此刻确实 detached（模拟到位）
            assert sa_inspect(p).detached is True, \
                "前置条件不成立：本应 detached，说明测试没模拟到真实场景"

            # 后台线程体：只碰快照里的纯数据，不得触碰 ORM
            cap_thread.instances[-1].run_now()

        assert sent, "后台线程没有发出通知"
        assert expected in sent[0], "通知内容里应含文章标题，实得 %r" % sent[0]
    finally:
        with app.app_context():
            if pid:
                _cleanup_post(pid)


def test_detached_relationship_access_is_the_real_risk(app):
    """给上面那条用例提供**有据的**理由：detached 实例上访问**未加载的懒加载关系**会抛。

    这条不是在测业务代码，而是把「为什么要在调用线程里先取快照」的依据钉住：

    实测（Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.52）表明
    **标量属性在 detached 后照常可读**（值仍在实例 `__dict__` 里），
    所以「传 ORM 对象进线程」并不是一传就炸；真正的边界是**懒加载关系**。

    → 若哪天 SQLAlchemy 行为变了（例如标量也读不到、或关系不再抛），
    这条会失败，提醒我们**重新评估快照是否仍有必要**，而不是留一条
    没人知道还成不成立的「防御性代码 + 无意义测试」。
    """
    from sqlalchemy import inspect as sa_inspect

    pid = None
    try:
        with app.app_context():
            p = _mkpost()
            pid = p.id
            db.session.commit()
            # 关系「已加载」的情形：在 session 内先访问一次
            _ = list(p.tags)

        with app.app_context():
            assert sa_inspect(p).detached is True
            # ① 标量：detached 后**可读**（所以旧写法不是一传就炸）
            assert p.title, "标量属性在 detached 后应仍可读"
            # ② 已加载的关系：也可读
            assert list(p.tags) == []
            # ③ 未加载的懒加载关系：**抛 DetachedInstanceError** ← 真实边界
            with pytest.raises(Exception) as ei:
                _ = p.author
            assert "DetachedInstanceError" in type(ei.value).__name__, \
                "预期 DetachedInstanceError，实得 %s" % type(ei.value).__name__
    finally:
        with app.app_context():
            if pid:
                _cleanup_post(pid)


def test_notify_falls_back_to_sync_without_app_context(app, clean_env, monkeypatch):
    """无应用上下文时退化为同步执行（保持「调完就已发过」语义，不静默丢失）。"""
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(notify, "_tg_send", lambda token, chat, text: sent.append(text))

    class _Plain:
        title, slug, summary, content = "纯对象标题", "s", "摘要", "正文"

    notify.notify_new_post(_Plain(), "https://x.cn")   # 无 app context
    assert sent and "纯对象标题" in sent[0]


def test_notify_skips_when_unconfigured(app, cap_thread, clean_env, monkeypatch):
    """渠道未配置时：依然起线程，但**不出网**（默认不打扰）。"""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("未配置渠道时不得外发")))
    with app.app_context():
        p = _mkpost()
        pid = p.id
        try:
            notify.notify_new_post(p, "https://x.cn")
            cap_thread.instances[-1].run_now()
        finally:
            _cleanup_post(pid)


# ---------------------------------------------------------------------------
# 二、mail_notify.py：传 id 而非 ORM 对象
# ---------------------------------------------------------------------------
def test_mail_notify_requeries_post_by_id(app, cap_thread, monkeypatch):
    """**核心回归**：群发线程必须重新查库，不能沿用请求线程的 ORM 对象。"""
    built = []

    from sqlalchemy.orm import object_session

    def _fake_build(post, site_url):
        # 在**线程内部执行的那一刻**记录「对象是否绑定 session」——
        # 断言不能放在 run_now() 之后：那时 worker 自己的 app_context 已弹出，
        # 对象必然 detached（标量仍可读，所以看起来"没事"，但已不是我们关心的时点）
        built.append((post, object_session(post)))
        return "<html>%s</html>" % post.title, "plain"

    monkeypatch.setattr(mail_notify, "_build_mail", _fake_build)
    monkeypatch.setattr(mail_notify, "load_mail_config",
                        lambda: {"host": "h", "username": "u", "site_url": ""})
    monkeypatch.setattr(mail_notify, "_send_smtp", lambda *a, **k: None)
    monkeypatch.setattr(mail_notify, "_fill_unsub", lambda t, *a: t)

    pid = None
    sub_email = "ntf-%s@test.local" % _tok()
    try:
        with app.app_context():
            p = _mkpost(title="群发标题-" + _tok())
            expected = p.title
            pid = p.id
            db.session.add(Subscriber(email=sub_email, active=True, unsub_token="tok"))
            db.session.commit()                      # ← 先提交（与真实调用序一致）
            cap_thread.instances.clear()
            mail_notify.notify_subscribers_async(p)
            assert cap_thread.instances and cap_thread.instances[-1].started

        with app.app_context():
            cap_thread.instances[-1].run_now()

        assert built, "群发线程没有构建邮件"
        post_obj, sess = built[0]
        assert post_obj.title == expected, \
            "线程内应拿到**重新查库**后的对象，实得 %r" % post_obj.title
        # 关键：线程内构建邮件的那一刻，对象必须**仍绑定着 session**。
        # 否则一旦 _build_mail 将来访问懒加载关系就会 DetachedInstanceError ——
        # 这正是「传 id 重查」而不是「传对象」的理由。
        assert sess is not None, "线程内构建邮件时对象必须仍绑定 session"
    finally:
        with app.app_context():
            if pid:
                _cleanup_post(pid)


def test_mail_notify_skips_deleted_post(app, cap_thread, monkeypatch):
    """文章在通知前被删除 → 静默跳过，不报错。"""
    monkeypatch.setattr(mail_notify, "load_mail_config",
                        lambda: {"host": "h", "username": "u", "site_url": ""})

    class _Ghost:
        id = 10 ** 9          # 不存在的 id

    cap_thread.instances.clear()
    with app.app_context():
        mail_notify.notify_subscribers_async(_Ghost())
        assert cap_thread.instances[-1].started
        cap_thread.instances[-1].run_now()   # 不应抛异常


# ---------------------------------------------------------------------------
# 三、/health
# ---------------------------------------------------------------------------
def test_health_ok_and_leaks_nothing(app, client, monkeypatch):
    """/health：200 + 三项字段，且**不得**出现配置/路径/密钥等敏感信息。"""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("/health 不得出网")))
    r = client.get("/api/health")
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    body = r.get_data(as_text=True)
    js = r.get_json()
    assert js["ok"] is True and js["db"] == "up"
    assert js["version"], "应返回版本号（监控侧便于确认部署到哪一版）"
    assert set(js) == {"ok", "version", "db"}, "响应字段应严格只有这三项：%r" % list(js)
    # 敏感信息一个都不能出现
    for needle in ("SECRET", "SECRET_KEY", "password", "token", "TOKEN",
                   "/www/", "DATABASE_URL", "sqlite"):
        assert needle not in body, "/health 泄露了敏感字样：%s" % needle


def test_health_needs_no_login(app, client):
    """/health 必须**无需登录**（否则监控打不进来）且无 CSRF 门槛（GET）。"""
    assert client.get("/api/health").status_code == 200


def test_health_returns_503_when_db_down(app, client, monkeypatch):
    """数据库探活失败 → **503**（通用 HTTP 探活可直接判定，无需解析 body）。"""
    import models

    class _BadSession:
        """只让探活那一句失败；其余（如 teardown 调用的 remove）保持可用。"""

        def execute(self, *a, **k):
            raise RuntimeError("模拟数据库不可用")

        def remove(self):
            pass

    monkeypatch.setattr(models.db, "session", _BadSession())
    r = client.get("/api/health")
    assert r.status_code == 503, "依赖不可用应返回 503，实得 %s" % r.status_code
    js = r.get_json()
    assert js["ok"] is False and js["db"] == "down"
