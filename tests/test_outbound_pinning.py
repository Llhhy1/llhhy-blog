"""v4.7.4 出站统一层与 IP pinning 的实测。

**为什么必须实测**：pinning 的全部价值在于「连接时不再重新解析 DNS」——
这件事从代码上读不出来，只能跑出来看。本文件用两个手段钉住它：

1. `getaddrinfo` 被 mock 成「第二次调用就直接失败」——
   只要出站过程中发生了第二次 DNS 解析，测试立刻红。
   这正是 DNS rebinding 的利用前提（两次解析之间改 DNS）。
2. 起真实的本地 HTTP server，验证请求**真的到达了**被 pin 的那个地址，
   且 HTTP `Host` 头仍是原域名（身份不能丢，否则虚拟主机与证书校验都失效）。
"""
import http.server
import ipaddress
import socket
import threading

import pytest

import outbound
from outbound import (OutboundRejected, build_opener, open_url, read_limited,
                      resolve_public, safe_public_url)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("host=%s path=%s" % (self.headers.get("Host"), self.path)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else b""
        body = ("host=%s got=%s" % (self.headers.get("Host"), data.decode("utf-8", "ignore"))).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    """起一个本地 HTTP server，返回 (base_url, port)。"""
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield ("http://127.0.0.1:%d" % port, port)
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- resolve_public ----------


def test_resolve_public_返回_ip_而不只是布尔():
    """旧版只返回 bool，被校验的 IP 被算完就扔 —— 这正是 rebinding 的成因。"""
    r = resolve_public("http://1.1.1.1/x")
    assert r is not None
    host, port, ips = r
    assert host == "1.1.1.1"
    assert port == 80
    assert ips == ["1.1.1.1"], "必须把解析出的 IP 交给调用方固定使用"


def test_resolve_public_https_默认端口():
    r = resolve_public("https://1.1.1.1/x")
    assert r[1] == 443


def test_resolve_public_显式端口():
    r = resolve_public("http://1.1.1.1:8080/x")
    assert r[1] == 8080


def test_resolve_public_私网返回_none():
    assert resolve_public("http://127.0.0.1/x") is None
    assert resolve_public("http://10.0.0.1/x") is None
    assert resolve_public("http://169.254.169.254/") is None


def test_safe_public_url_行为保持不变():
    """旧调用方（games.py 保存前预检）依赖这个函数的既有语义。"""
    assert safe_public_url("https://1.1.1.1/v1") is True
    assert safe_public_url("http://127.0.0.1/v1") is False
    assert safe_public_url("not a url") is False


# ---------- pinning 的核心证明 ----------


def _is_ip_literal(host):
    """host 是不是 IP 字面量（IP 字面量的解析不查 DNS，**不算**二次解析）。"""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def test_pinning_出站过程中不再解析_dns(server, monkeypatch):
    """**这是整个改动的核心断言**。

    只统计**域名**的解析次数：`socket.create_connection` 内部会对连到的地址
    再调一次 `getaddrinfo`，但那是对 **IP 字面量**的解析 —— 不查 DNS，无害。
    真正要禁止的是「域名被解析第二次」（DNS rebinding 的利用前提）。

    如果出站路径上又用域名解析了一次，测试立刻红。
    """
    base, port = server
    domain_calls = []

    def fake_getaddrinfo(host, p, *a, **kw):
        if not _is_ip_literal(host):
            domain_calls.append(host)
            if len(domain_calls) > 1:
                raise AssertionError(
                    "域名被解析了 %d 次 —— pinning 失效！" % len(domain_calls))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))]

    monkeypatch.setattr(outbound.socket, "getaddrinfo", fake_getaddrinfo)
    # 本地 server 在 127.0.0.1 上，校验会判它是私网 —— 这里只放行这一次测试
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)

    with open_url("http://evil.test:%d/probe" % port, timeout=5) as resp:
        body = resp.read().decode("utf-8", "ignore")

    assert "path=/probe" in body, body
    assert "host=evil.test" in body, \
        "Host 头必须仍是原域名（身份不能丢），实际：" + body
    assert len(domain_calls) == 1, \
        "域名只应解析一次，实际 %d 次：%r" % (len(domain_calls), domain_calls)


def test_pinning_连的是被固定的_ip_而不是重新解析(server, monkeypatch):
    """从结果侧证明连的是**被 pin 的那个 IP**，而不是重新解析出来的。

    mock 语义：IP 字面量的解析永远给 127.0.0.1（`create_connection` 内部对
    连到的地址会再解析一次，那是对 IP 的解析，不查 DNS）；
    **域名**的第二次解析才返回 127.0.0.2（模拟 DNS 被改指）。
    若 pinning 失效 → 连接会用域名 → 拿到 127.0.0.2 → 连不上 → 测试红。
    """
    base, port = server
    seq = []

    def fake_getaddrinfo(host, p, *a, **kw):
        if _is_ip_literal(host):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))]
        seq.append(host)
        if len(seq) == 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))]
        # 域名的第二次解析：DNS 被改指到别处
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.2", p))]

    monkeypatch.setattr(outbound.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)

    with open_url("http://evil.test:%d/again" % port, timeout=5) as resp:
        body = resp.read().decode("utf-8", "ignore")
    assert "path=/again" in body, "请求应到达被 pin 的地址"
    assert len(seq) == 1, "域名只应解析一次，实际 %d 次" % len(seq)


def test_pinning_后仍禁跟随重定向(server, monkeypatch):
    """pinning 不能把「禁跟随 3xx」的能力弄丢。"""
    base, port = server
    monkeypatch.setattr(outbound.socket, "getaddrinfo",
                        lambda host, p, *a, **kw: [
                            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))])
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)

    class _Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
    rport = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(Exception) as ei, open_url(
                "http://evil.test:%d/r" % rport, timeout=5):
            pass
        # 302 必须被拒绝，而不是被跟随到内网地址
        assert "302" in str(ei.value) or "HTTPError" in type(ei.value).__name__, \
            "302 应被拒绝（禁止跟随），实际异常：%r" % (ei.value,)
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- 统一入口的基本行为 ----------


def test_open_url_拒绝不安全_url():
    with pytest.raises(OutboundRejected):
        open_url("http://127.0.0.1/x", timeout=2)
    with pytest.raises(OutboundRejected):
        open_url("file:///etc/passwd", timeout=2)
    with pytest.raises(OutboundRejected):
        open_url("http://user:pass@1.1.1.1/x", timeout=2)


def test_open_url_真实请求可达(server, monkeypatch):
    """不走 mock 的真实路径：起一个把 127.0.0.1 视作公网的假解析。"""
    base, port = server
    monkeypatch.setattr(outbound.socket, "getaddrinfo",
                        lambda host, p, *a, **kw: [
                            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))])
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)
    with open_url("http://good.test:%d/ok" % port, timeout=5) as resp:
        assert resp.status == 200
        assert b"path=/ok" in resp.read()


def test_open_url_带请求体(server, monkeypatch):
    base, port = server
    monkeypatch.setattr(outbound.socket, "getaddrinfo",
                        lambda host, p, *a, **kw: [
                            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))])
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)
    with open_url("http://good.test:%d/post" % port, timeout=5,
                  data=b'{"a":1}',
                  headers={"Content-Type": "application/json"},
                  method="POST") as resp:
        body = resp.read().decode("utf-8", "ignore")
    assert "got=" in body and "a" in body, body


def test_read_limited_截断(server, monkeypatch):
    base, port = server
    monkeypatch.setattr(outbound.socket, "getaddrinfo",
                        lambda host, p, *a, **kw: [
                            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))])
    monkeypatch.setattr(outbound, "is_private_ip", lambda ip: False)
    with open_url("http://good.test:%d/big" % port, timeout=5) as resp:
        data, truncated = read_limited(resp, 4)
    assert truncated is True
    assert len(data) == 4


def test_build_opener_禁跟随重定向():
    """opener 恒定带 NoRedirect —— 这是最常见的 SSRF 绕过路径。"""
    op = build_opener()
    handlers = [type(h).__name__ for h in op.handlers]
    assert "NoRedirect" in handlers
