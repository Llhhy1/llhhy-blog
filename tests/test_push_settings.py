"""v4.10.0 推送配置后台化 + 出站 SSRF 加固（ROADMAP §3.1 + SECURITY R128 §128.3）。

背景：把 `TELEGRAM_BOT_TOKEN` / `WECOM_WEBHOOK_URL` 做成后台可填的那一刻，
「推送地址」就从「管理员自己写进 .env 的东西」变成了「后台表单里的一个值」——
**不校验就是给每个后台账号开一个直连内网的 SSRF 出口**。所以本文件分两块：

A. 出站加固（`notify._post_json`）：非 https / 内网 / 带凭据的地址一律拒绝，
   且**拒绝时不重试**（配置错重试一万次也不会好，只会白耗 7 秒）。
B. 后台配置（`push_settings`）：凭据加密落库、掩码不被写成真值、留空保持不变、
   页面只有超管能进。

判据可证伪：每条拒绝用例都断言**没有真的出网**（用探针替换 `open_url`），
而不是只看「抛了错」——抛错也可能是「请求发出去了、对面拒了」。
"""

import secrets

import pytest

import notify as notify_mod
import push_settings as ps
from models import db, User, ROLE_SUPER, ROLE_ADMIN
from outbound import OutboundRejected
from backup_settings import ENC_PREFIX, decrypt_secret

PASSWORD = "Passw0rd!23"
_WEBHOOK_OK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc"


# ---------------------------------------------------------------- A. 出站加固


def test_非https地址被拒且不出网(monkeypatch):
    """http:// 明文：推送内容里带文章标题与链接，绝不能走明文出网。

    判据为什么还要断言 reason 里含 "https"：只断言「抛了 OutboundRejected」
    是**可假绿**的 —— 若把 scheme 检查摘掉，这里会掉进 `open_url`，在没网的
    机器上以「DNS 解析失败」抛同一个异常类型，测试照样绿。带上原因串才能分辨
    「被 https 策略拒绝」和「碰巧解析失败」。
    """
    connects = []

    def fake_conn(addr, *a, **k):
        connects.append(addr)
        raise AssertionError("不合法地址竟然发起了出网请求 %s" % (addr,))

    monkeypatch.setattr("outbound.socket.create_connection", fake_conn)
    with pytest.raises(OutboundRejected) as ei:
        notify_mod._post_json("http://example.com/hook", {"a": 1})
    assert "https" in str(ei.value), "拒绝原因不是 https 策略：%s" % ei.value
    assert connects == []


def test_内网地址被拒(monkeypatch):
    """后台化之后最现实的攻击：把 webhook 填成内网地址探测内部服务。

    ⚠️ 这里**不 mock `open_url`** —— 私网过滤就是它做的，mock 掉等于把被测
    的东西换掉了（那样就算没过滤也会红，但红的原因是 TypeError 而非拒绝）。
    改为 mock 更底层的 `socket.create_connection`：校验若失效，就会真的去连，
    探针立刻留下记录；IP 字面量不会触发 DNS 查询，测试本身不出网。
    """
    connects = []

    def fake_conn(addr, *a, **k):
        connects.append(addr)
        raise AssertionError("竟然真的去连内网地址 %s" % (addr,))

    monkeypatch.setattr("outbound.socket.create_connection", fake_conn)
    for bad in ("https://127.0.0.1:8686/admin", "https://localhost/x",
                "https://169.254.169.254/latest/meta-data", "https://10.0.0.5/x"):
        with pytest.raises(OutboundRejected):
            notify_mod._post_json(bad, {"a": 1})
    assert connects == [], "竟然尝试与内网地址建立连接"


def test_带凭据的地址被拒(monkeypatch):
    connects = []

    def fake_conn(addr, *a, **k):
        connects.append(addr)
        raise AssertionError("竟然出网")

    monkeypatch.setattr("outbound.socket.create_connection", fake_conn)
    with pytest.raises(OutboundRejected):
        notify_mod._post_json("https://user:pw@example.com/x", {"a": 1})
    assert connects == []


def test_合法地址确实走统一出站层(monkeypatch):
    """正向：正常地址必须**经过** `open_url`（而不是绕过它自己 urlopen）。

    这条是防「加固写反了」：若 `_post_json` 里误写成先 urlopen 再校验，
    前面三条拒绝用例可能依然红，但真正的出网已经在校验前发生了。
    """
    seen = {}

    class _FakeResp:
        def read(self):
            return b'{"ok":true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open_url(url, **kw):
        seen["url"] = url
        seen["kw"] = kw
        return _FakeResp()

    monkeypatch.setattr(notify_mod, "open_url", fake_open_url)
    out = notify_mod._post_json(_WEBHOOK_OK, {"msgtype": "text"})
    assert out == '{"ok":true}'
    assert seen["url"] == _WEBHOOK_OK
    assert seen["kw"]["method"] == "POST", "必须显式带 method=POST"


def test_配置类错误不重试():
    """OutboundRejected 是「地址写错了」，不是「对面抖了一下」—— 不该退避重试。

    若这里重试，一次填错的地址会让每次发文都多耗 7 秒，并在日志里堆 3 条
    一模一样的堆栈，把真正的错误埋掉。
    """
    sleeps = []
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise OutboundRejected("内网地址")

    ok = notify_mod._send_with_retry(boom, "企业微信", sleep=sleeps.append)
    assert ok is False
    assert calls["n"] == 1, "配置错误重试了 %d 次（应只试一次就放弃）" % calls["n"]
    assert sleeps == [], "配置错误不该退避等待"


def test_网络抖动仍然重试():
    """反证用：确认上一条不是因为「整个重试机制失效」才没重试。"""
    sleeps = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("connection reset")

    assert notify_mod._send_with_retry(flaky, "Telegram", sleep=sleeps.append) is True
    assert calls["n"] == 3 and sleeps == [1.0, 2.0]


# ------------------------------------------------------------ B. 后台配置读写


@pytest.fixture
def push_db(app):
    """推送设置读写**必须在 app 上下文里**做。

    ⚠️ 这不是风格问题：`push_settings` 经 `backup_settings.write_setting_db`
    在无 Flask 上下文时**退化为 sqlite3 直连 `myblog/data/blog.db`**（默认路径）——
    也就是**真实开发库**。在上下文外调用会让测试写到开发库上，既污染本地
    又让断言读到错误库的值（本文件初版就踩了：库值读回来是空，页面没有掩码）。

    用完一定清库：测试库**全 session 共享**，`notify.deliver` 读的就是这张表，
    残留值会让别的测试里「未配置渠道不发」假红。
    """
    class _Ctx:
        def save(self, key, val):
            with app.app_context():
                return ps.save(key, val)

        def get(self, key, **kw):
            with app.app_context():
                return ps.get(key, **kw)

        def clear(self, key):
            with app.app_context():
                return ps.clear(key)

        def read_raw(self, key):
            with app.app_context():
                return ps.read_setting_db(key)

        def for_admin(self, key):
            with app.app_context():
                return ps.for_admin(key)

    h = _Ctx()
    for k in ps.FIELDS:
        h.clear(k)
    yield h
    for k in ps.FIELDS:
        h.clear(k)


def test_敏感字段加密落库_绝不明文(app, push_db):
    push_db.save("push_telegram_token", "123456:AAbbCC-token-plain")
    stored = push_db.read_raw("push_telegram_token")
    assert stored.startswith(ENC_PREFIX), "敏感字段没加密就落库了（CWE-312）"
    assert "AAbbCC-token-plain" not in stored
    assert decrypt_secret(stored) == "123456:AAbbCC-token-plain"


def test_回显掩码被原样提交时不会被写成真值(app, push_db):
    """页面回显 `12****en`，管理员不改就原样提交 —— 存进去就全完了。"""
    push_db.save("push_telegram_token", "123456:AAbbCC-real-token")
    masked = push_db.for_admin("push_telegram_token")
    assert masked and masked != "123456:AAbbCC-real-token", "回显的不是掩码？"
    push_db.save("push_telegram_token", masked)     # 模拟「原样提交回来」
    assert push_db.get("push_telegram_token", env_first=False) == "123456:AAbbCC-real-token", \
        "掩码被当成真值写进库了"


def test_留空保持不变(app, push_db):
    """与 backup_settings 同一语义：留空 = 不改。否则「只改 chat id」会顺手清掉 token。"""
    push_db.save("push_telegram_token", "tok-keep-me")
    push_db.save("push_telegram_token", "")
    assert push_db.get("push_telegram_token", env_first=False) == "tok-keep-me"


def test_显式清除才清空(app, push_db):
    push_db.save("push_telegram_token", "tok")
    push_db.clear("push_telegram_token")
    assert push_db.get("push_telegram_token", env_first=False) == ""


def test_环境变量优先于库值(app, push_db, monkeypatch):
    """老部署零迁移：env 配了就用 env，不会因为升级改用库里的空值而静默停推。"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-env")
    push_db.save("push_telegram_token", "from-db")
    with app.app_context():
        assert ps.get("push_telegram_token") == "from-env"


def test_非敏感字段库值优先(app, push_db, monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    push_db.save("push_telegram_chat", "-100123")
    with app.app_context():
        assert ps.get("push_telegram_chat") == "-100123"


@pytest.mark.parametrize("bad,why", [
    ("http://qyapi.weixin.qq.com/hook", "明文 http"),
    ("https://127.0.0.1/hook", "回环"),
    ("https://10.0.0.5/hook", "内网"),
    ("https://169.254.169.254/latest", "链路本地"),
    ("https://user:pw@qyapi.weixin.qq.com/h", "内嵌凭据"),
])
def test_保存前预检挡住明显不合格的地址(bad, why):
    ok, _reason = ps.precheck_url("push_wecom_webhook", bad)
    assert ok is False, "「%s」竟然通过预检" % why


def test_预检放行正常地址():
    assert ps.precheck_url("push_wecom_webhook", _WEBHOOK_OK)[0] is True


# ------------------------------------------------------------------ C. 权限


def _mk(app, role):
    uname = "u_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=role, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    return uname


def _login(client, uname):
    d = client.get("/api/csrf").get_json() or {}
    tok = d.get("csrf_token") or d.get("token") or ""
    r = client.post("/api/auth/login",
                    json={"username": uname, "password": PASSWORD},
                    headers={"X-CSRF-Token": tok})
    assert r.status_code == 200
    return client


def test_只有超管能进推送设置页(app, client, push_db):
    """凭据类配置（bot token / webhook key）—— 管理员也不该看。"""
    super_c = _login(client, _mk(app, ROLE_SUPER))
    r = super_c.get("/admin/push-settings")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]

    admin_c = _login(client, _mk(app, ROLE_ADMIN))
    r2 = admin_c.get("/admin/push-settings")
    assert r2.status_code != 200, "管理员竟能打开推送设置页（凭据泄露面）"


def test_未登录不能进推送设置页(client):
    assert client.get("/admin/push-settings").status_code != 200


def test_页面不回显明文凭据(app, client, push_db):
    """页面里**绝对不能**出现明文 token —— 截图 / 录屏 / 浏览器历史都会泄。"""
    push_db.save("push_telegram_token", "123456:AAbbCC-secret-token")
    c = _login(client, _mk(app, ROLE_SUPER))
    html = c.get("/admin/push-settings").get_data(as_text=True)
    assert "AAbbCC-secret-token" not in html, "明文 token 出现在页面里"
    assert "12****en" in html, "掩码没渲染出来"


def test_保存并测试_未配置时不外发(app, client, push_db, monkeypatch):
    """没配就点「测试」：应明确提示「未配置」，且**不发起任何外发**。"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)

    def boom(*a, **k):
        raise AssertionError("未配置却发起了外发")

    monkeypatch.setattr(notify_mod, "_tg_send", boom)
    monkeypatch.setattr(notify_mod, "_wecom_send", boom)

    c = _login(client, _mk(app, ROLE_SUPER))
    d = c.get("/api/csrf").get_json() or {}
    tok = d.get("csrf_token") or d.get("token") or ""
    r = c.post("/admin/push-settings",
               data={"action": "test", "push_telegram_token": "",
                     "push_telegram_chat": "", "push_wecom_webhook": ""},
               headers={"X-CSRF-Token": tok})
    assert r.status_code == 302
