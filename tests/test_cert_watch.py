"""SSL 证书到期监控（v3.25.3）。

**为什么要有**：证书过期 = 全站不可访问（HTTP 80 → 301 跳 HTTPS → 浏览器拒绝）。
2026-10-02 22:59 到期、10-05 才发现 —— 「记得看」对 90 天周期的基础设施是失效的。

**测试策略**：本机**真起一个 TLS 服务**（自签证书），分别构造「未过期 /
7 天内 / 已过期」三种情况，验 `cert_watch` 的分级逻辑。
不这么做就只能测「读文件解析」这条路径，**而生产走的是 TLS 握手那条**。

**同时锁住三个设计决定**（都是踩过才知道的）：
1. 走握手不读文件 —— 宝塔 `fullchain.pem` 是 `drw-------`（root only），
   gunicorn 以 `www` 运行，**读文件必然 PermissionError**。
2. 域名取自 `site_base()` —— 硬编码域名会变成**静默失效的假监控**。
3. `never`（没检查过）必须给 warn 而非 ok —— 「没查过」≠「没问题」。
"""
import datetime
import os
import ssl
import subprocess
import threading

import pytest

import cert_watch as cw


# ---------- 真实 TLS 服务：三种证书状态 ----------

def _make_cert(tmp_path, days_left):
    """用 openssl 造一张自签证书，`days_left` 为负即已过期。"""
    os.makedirs(str(tmp_path), exist_ok=True)      # 子目录可能还没建
    key = tmp_path / "k.pem"
    crt = tmp_path / "c.pem"
    # -days 为负在 openssl 里不合法，用 -not_after 明确指定
    if days_left < 0:
        # 已过期：结束时间设为 1 天前
        end = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    else:
        end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_left)
    fmt = "%y%m%d%H%M%SZ"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(crt), "-days", "3650",
         "-subj", "/CN=cert-test.local",
         "-not_before", (end - datetime.timedelta(days=2)).strftime(fmt),
         "-not_after", end.strftime(fmt)],
        capture_output=True, check=True, timeout=60)
    return str(crt), str(key)


def _serve_tls(tmp_path, days_left):
    """起一个后台 TLS 服务，返回 (host, port)。"""
    crt, key = _make_cert(tmp_path, days_left)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    return socket_server(ctx)


def socket_server(ctx):
    """起一个后台 TLS 服务并**等它真正就绪**再返回。

    ⚠️ 必须轮询握手确认 ready：只 `Thread(...).start()` 就返回的话，
    客户端可能在 `serve_forever` 还没进入 accept 循环时就发起握手 →
    连接被拒 → `check_once` 吞成 `unknown` → **随机红**。
    这是实测踩过的：第一版 15 条里有 6 条随机失败，加了下面这段才稳定。
    """
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", 0, lambda e, s: None, ssl_context=ctx)
    port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    probe.check_hostname = False
    probe.verify_mode = ssl.CERT_NONE
    import socket as _socket
    import time as _time
    deadline = _time.time() + 5
    while _time.time() < deadline:
        try:
            with _socket.create_connection(("127.0.0.1", port), timeout=1) as s:
                with probe.wrap_socket(s, server_hostname="127.0.0.1"):
                    return ("127.0.0.1", port)
        except OSError:
            _time.sleep(0.05)
    raise RuntimeError("TLS 测试服务在 5s 内未就绪")


@pytest.fixture()
def tls_server(tmp_path):
    """返回工厂：make(60) 起一个 60 天后过期的 TLS 服务。"""
    made = []

    def _make(days_left):
        host, port = _serve_tls(tmp_path / ("d%s" % days_left), days_left)
        made.append((host, port))
        return host, port
    yield _make


# ---------- 分级逻辑（真实握手）----------

def test_valid_certificate_is_ok(tls_server, monkeypatch, tmp_path):
    host, port = tls_server(60)
    monkeypatch.setattr(cw, "_target_host", lambda: host)
    real = cw._fetch_cert_der          # ⚠️ 先存原函数，否则替换后 lambda 调自己 → 无限递归
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: real(h, port))
    st = cw.check_once()
    assert st["status"] == "ok", st
    assert st["days_left"] >= 55
    assert "剩" in st["message"]


def test_expiring_certificate_is_warn(tls_server, monkeypatch):
    host, port = tls_server(20)
    monkeypatch.setattr(cw, "_target_host", lambda: host)
    real = cw._fetch_cert_der          # ⚠️ 先存原函数，否则替换后 lambda 调自己 → 无限递归
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: real(h, port))
    st = cw.check_once()
    assert st["status"] == "warn", st
    assert 15 <= st["days_left"] <= 20
    assert "尽快续签" in st["message"]


def test_certificate_within_7_days_is_critical(tls_server, monkeypatch):
    host, port = tls_server(3)
    monkeypatch.setattr(cw, "_target_host", lambda: host)
    real = cw._fetch_cert_der          # ⚠️ 先存原函数，否则替换后 lambda 调自己 → 无限递归
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: real(h, port))
    st = cw.check_once()
    assert st["status"] == "critical", st
    assert "本周内" in st["message"]


def test_expired_certificate_is_error(tls_server, monkeypatch):
    """**这条是整个功能的核心** —— 2026-10-02 那次就该被它抓住。"""
    host, port = tls_server(-1)
    monkeypatch.setattr(cw, "_target_host", lambda: host)
    real = cw._fetch_cert_der          # ⚠️ 先存原函数，否则替换后 lambda 调自己 → 无限递归
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: real(h, port))
    st = cw.check_once()
    assert st["status"] == "expired", st
    assert st["days_left"] < 0
    assert "已过期" in st["message"] and "立即续签" in st["message"]


def test_handshake_works_even_when_cert_expired(tls_server, monkeypatch):
    """**过期时握手仍必须能拿到证书** —— 这正是 `verify_mode=CERT_NONE` 的理由。

    默认校验会直接抛 SSLCertVerificationError，而我们要读的就是那张过期证书。
    """
    host, port = tls_server(-1)
    der = cw._fetch_cert_der(host, port)
    assert der and len(der) > 100


# ---------- 状态落盘与读取 ----------

def test_state_persisted_and_readable(tls_server, monkeypatch, tmp_path):
    host, port = tls_server(40)
    monkeypatch.setattr(cw, "_target_host", lambda: host)
    real = cw._fetch_cert_der          # ⚠️ 先存原函数，否则替换后 lambda 调自己 → 无限递归
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: real(h, port))
    monkeypatch.setattr(cw, "_state_path",
                        lambda: str(tmp_path / "cert_check.json"))
    cw.check_once()
    st = cw.read_state()
    assert st["status"] == "ok"
    assert st["checked_at"] and st["not_after"]


def test_read_state_never_raises(tmp_path):
    """文件不存在 / 损坏都返回「未检查」，诊断页不能因此崩。"""
    monkey_path = os.path.join(str(tmp_path), "nope.json")
    orig = cw._state_path
    cw._state_path = lambda: monkey_path
    try:
        assert cw.read_state()["status"] == "never"
        with open(monkey_path, "w", encoding="utf-8") as f:
            f.write("{ 坏 json")
        assert cw.read_state()["status"] == "never"
    finally:
        cw._state_path = orig


# ---------- 设计决定 1：不读文件 ----------

def test_never_reads_cert_file():
    """**锁设计决定 1**：宝塔 `fullchain.pem` 是 `-rw-------` root only，
    gunicorn 以 `www` 运行 —— 读文件必然 PermissionError。所以只能走 TLS 握手。

    ⚠️ 只断言**绝对路径**不被硬编码：docstring 里提到 `fullchain.pem` 这个
    **文件名**（解释为什么要走握手）是必要说明，不该被这条断言误伤。
    真正要防的是「代码里写死了 `/www/server/panel/vhost/cert/...` 这类路径」——
    宝塔续签/迁移会改路径，写死就等于埋雷。
    """
    src = open(cw.__file__, encoding="utf-8").read()
    for bad in ("/www/server/panel", "/www/server/nginx", "/etc/nginx",
                "ssl_certificate", "CERT_PATH", "cert_path"):
        assert bad not in src, "cert_watch 不应硬编码证书路径（%s）" % bad


# ---------- 设计决定 2：域名不硬编码 ----------

def test_target_host_from_site_base(monkeypatch):
    """域名必须来自 `site_base()` —— 硬编码会在换域名后变成**假监控**。"""
    import utils
    monkeypatch.setattr(utils, "site_base", lambda: "https://blog.example.com/")
    assert cw._target_host() == "blog.example.com"
    monkeypatch.setattr(utils, "site_base", lambda: "http://127.0.0.1:8686")
    assert cw._target_host() == "127.0.0.1"
    monkeypatch.setattr(utils, "site_base", lambda: "")
    assert cw._target_host()  # 回落本机名，不抛


def test_site_base_exception_falls_back(monkeypatch):
    import utils
    def boom():
        raise RuntimeError("db 挂了")
    monkeypatch.setattr(utils, "site_base", boom)
    assert cw._target_host()


# ---------- 设计决定 3：never ≠ ok ----------

def test_never_status_is_warn_in_diagnostics(app, monkeypatch):
    """「没检查过」必须给 warn 而非 ok —— 与「没有备份报 empty 而非 ok」同源。

    ⚠️ 必须 monkeypatch `read_state`：直接调会读到**真实**状态文件，而它可能已被
    同文件的其它用例写成 `ok` —— 那样这条测试就恒绿、什么也没验。
    （第一版就这么写的，变异「never→ok」删了它也不红，被抓出来。）
    """
    import diagnostics
    monkeypatch.setattr(cw, "read_state", lambda: {
        "status": "never", "checked_at": "", "days_left": None,
        "not_after": "", "subject": "", "issuer": "",
        "message": "尚未检查证书有效期",
    })
    r = diagnostics.check_certificate()
    assert r["status"] in ("warn", "error"), \
        "未检查过证书时诊断页不得显示为正常：%s" % r["status"]


def test_expired_shows_error_in_diagnostics(app, monkeypatch):
    """已过期必须是 error 级（诊断页最高级），且 note 里给出续签入口。"""
    import diagnostics
    monkeypatch.setattr(cw, "read_state", lambda: {
        "status": "expired", "checked_at": "2026-10-05 00:00:00", "days_left": -2,
        "not_after": "2026-10-02 22:59:59 UTC", "subject": "CN=llhhy.cn",
        "issuer": "TrustAsia", "message": "证书已过期 2 天",
    })
    r = diagnostics.check_certificate()
    assert r["status"] == "error", r["status"]
    assert any("续签" in n for n in r["notes"]), "必须给出续签指引：%s" % r["notes"]


def test_expired_maps_to_error_level():
    assert cw.status_level("expired") == "error"
    assert cw.status_level("critical") == "warn"
    assert cw.status_level("warn") == "warn"
    assert cw.status_level("ok") == "ok"


# ---------- 挂载点 ----------

def test_scheduler_calls_check_once():
    import inspect
    src = inspect.getsource(_app_mod()._start_scheduler)
    assert "check_once" in src, "每日循环里没有调用证书检查"
    assert "_last_cert_day" in src, "未按天去重（会每 60s 跑一次握手）"


def _app_mod():
    import importlib
    return importlib.import_module("app")


def test_diagnostics_registers_checker():
    import diagnostics
    assert diagnostics.check_certificate in diagnostics.CHECKS, "未注册进 CHECKS 清单"


def test_unreachable_port_is_unknown_not_ok(monkeypatch, tmp_path):
    """连不上必须报 unknown —— **绝不能报 ok**（那是假安全感）。"""
    monkeypatch.setattr(cw, "_target_host", lambda: "127.0.0.1")
    monkeypatch.setattr(cw, "_fetch_cert_der",
                        lambda h, p=443, timeout=6: (_ for _ in ()).throw(
                            ConnectionRefusedError("连不上")))
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "c.json"))
    st = cw.check_once()
    assert st["status"] == "unknown"
    assert "无法连接" in st["message"]
