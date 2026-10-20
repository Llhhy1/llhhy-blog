"""出站 URL 安全校验（SSRF）单测。

用 IP 字面量，不做真实 DNS 查询：测试不依赖网络。
`open_public()` 的固定 IP 用桩替换 DNS 与建连，同样不触网。
"""
import socket

import pytest

from outbound import UnsafeURLError, is_private_ip, open_public, resolve_public, safe_public_url


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1",
    "fe80::1", "fc00::1", "203.0.113.9",   # TEST-NET-3 也非公网
])
def test_private_ip_detected(ip):
    assert is_private_ip(ip) is True


def test_public_ip_not_private():
    assert is_private_ip("1.1.1.1") is False
    assert is_private_ip("8.8.8.8") is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/v1",
    "https://127.0.0.1/v1",
    "http://localhost/v1",
    "http://foo.localhost/v1",
    "http://10.0.0.5/v1",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/v1",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://user:pass@1.1.1.1/v1",
    "not a url",
])
def test_unsafe_urls_rejected(url):
    assert safe_public_url(url) is False


def test_public_url_accepted_without_dns():
    assert safe_public_url("https://1.1.1.1/v1") is True
    assert safe_public_url("http://8.8.8.8:8080/chat/completions") is True


# ---------- resolve_public：拒绝原因可直接展示 ----------

def test_resolve_public_returns_the_ip_to_connect():
    host, port, ip = resolve_public("https://8.8.8.8:8443/x")
    assert (host, port, ip) == ("8.8.8.8", 8443, "8.8.8.8")


@pytest.mark.parametrize("url,keyword", [
    ("http://127.0.0.1/x", "内网"),
    ("http://169.254.169.254/latest/meta-data/", "内网"),
    ("file:///etc/passwd", "非 http/https"),
    ("http://user:pass@8.8.8.8/x", "凭据"),
    ("http://localhost/x", "回环"),
])
def test_resolve_public_reason_is_showable(url, keyword):
    with pytest.raises(UnsafeURLError) as ei:
        resolve_public(url)
    assert keyword in str(ei.value)


# ---------- open_public：解析一次 + 连那个被校验过的 IP ----------

class _ConnectAttempted(Exception):
    """桩：记录建连目标后中断，避免真的联网。"""


def _stub_dns_and_connect(monkeypatch, answers):
    """把 DNS 与建连都换成桩。返回 `(dns_calls, connect_targets)`。

    `answers` 是每次 DNS 要返回的 IP，按调用顺序取；不够用则重复最后一个。
    """
    dns_calls, targets = [], []
    state = {"n": 0}

    def _getaddrinfo(host, port, **_kw):
        ip = answers[min(state["n"], len(answers) - 1)]
        state["n"] += 1
        dns_calls.append((host, ip))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    def _create_connection(address, *_a, **_kw):
        targets.append(address)
        raise _ConnectAttempted()

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    # `HTTPConnection.__init__` 里是 `self._create_connection = socket.create_connection`
    # （建连函数在**实例化时**从 socket 模块取），所以必须 patch socket 上的原名，
    # 且要在连接对象构造之前生效 —— open_public 内部才构造，这里已经 patch 完。
    monkeypatch.setattr(socket, "create_connection", _create_connection)
    return dns_calls, targets


def test_open_public_resolves_once_and_pins_that_ip(monkeypatch):
    dns, targets = _stub_dns_and_connect(monkeypatch, ["93.184.216.34"])
    with pytest.raises(_ConnectAttempted):
        open_public("https://example.com/v1", timeout=1)
    assert dns == [("example.com", "93.184.216.34")]      # 只解析一次
    assert targets == [("93.184.216.34", 443)]            # 连的就是被校验过的那个 IP


def test_open_public_blocks_dns_rebinding(monkeypatch):
    """「预检查公网 → 建连时二次解析已变内网」这条路必须不存在。

    让桩按调用顺序先后给出公网、回环两个答案：只解析一次的话，
    第二个答案根本不会被读到，建连目标也就仍是那个公网 IP。
    """
    dns, targets = _stub_dns_and_connect(monkeypatch, ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(_ConnectAttempted):
        open_public("http://rebind.example/feed", timeout=1)
    assert len(dns) == 1, f"DNS 被解析了 {len(dns)} 次，重绑定窗口又开了"
    assert targets and targets[0][0] == "93.184.216.34"


def test_open_public_refuses_before_any_connect(monkeypatch):
    dns, targets = _stub_dns_and_connect(monkeypatch, ["169.254.169.254"])
    with pytest.raises(UnsafeURLError):
        open_public("http://metadata.example/latest", timeout=1)
    assert targets == [], "内网地址不该发生任何建连"
    assert len(dns) == 1
