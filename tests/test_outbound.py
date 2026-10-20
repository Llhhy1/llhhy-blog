"""出站 URL 安全校验（SSRF）单测。

用 IP 字面量，不做真实 DNS 查询：测试不依赖网络。
"""
import pytest

from outbound import is_private_ip, safe_public_url


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
