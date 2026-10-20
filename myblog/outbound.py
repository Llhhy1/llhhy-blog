"""出站 URL 安全校验（SSRF 防护）。

只允许 http/https，且域名必须解析到**公网**地址：私网、回环、链路本地、
保留、组播、未指定地址一律拒绝。URL 内嵌凭据也拒绝。

调用方必须在**真正发起请求前**再校验一次，并配合 `NoRedirect` 禁跟随 3xx：
先查一次再交给会重新解析 DNS / 自动跳转的客户端，等于没查。
"""
import ipaddress
import socket
import urllib.parse
import urllib.request


def is_private_ip(ip):
    """非公网地址（含私网/回环/链路本地/保留/组播/未指定）返回 True。"""
    try:
        obj = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not obj.is_global


def safe_public_url(url):
    """URL 是否可安全出站：http/https + 公网解析结果 + 不含凭据。"""
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower()
        port = p.port
    except (TypeError, ValueError):
        return False
    if p.scheme not in ("http", "https"):
        return False
    if p.username or p.password:
        return False
    if not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        infos = socket.getaddrinfo(host, port or (443 if p.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except OSError:
        return False
    ips = {info[4][0] for info in infos}
    if not ips:
        return False
    return all(not is_private_ip(ip) for ip in ips)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """任何 3xx 都不跟随（返回 None 使 urllib 抛 HTTPError）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None
