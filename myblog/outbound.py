"""出站 URL 安全校验（SSRF 防护）与固定 IP 的出站入口。

只允许 http/https，且域名必须解析到**公网**地址：私网、回环、链路本地、
保留、组播、未指定地址一律拒绝。URL 内嵌凭据也拒绝。

**为什么必须有 `open_public()`**：只做「先校验、再交给客户端去请求」是拦不住
DNS 重绑定的 —— 校验方解析一次 DNS，客户端建连时**又解析一次**，攻击者只要
在两次解析之间把 A 记录从公网 IP 换成 `127.0.0.1` / `169.254.169.254`，
预检查就完全白做。`open_public()` 把「解析一次 → 用那个 IP 建连」收成一条路，
并禁用 3xx 跟随与环境代理（代理会让"连到哪个 IP"重新失控）。
"""
import contextlib
import functools
import http.client
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


class UnsafeURLError(ValueError):
    """URL 不允许出站。`str(e)` 是可直接给管理员看的拒绝原因。"""


def resolve_public(url):
    """校验 URL 并**只解析一次** DNS，返回 `(host, port, ip)`。

    返回的 `ip` 就是真正要连的地址：调用方必须把它交给 `open_public()`，
    而不是让客户端再解析一遍。不合格一律抛 `UnsafeURLError`。
    """
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower()
        port = p.port
    except (TypeError, ValueError) as e:
        raise UnsafeURLError("URL 无法解析") from e
    if p.scheme not in ("http", "https"):
        raise UnsafeURLError(f"协议 {p.scheme!r} 非 http/https")
    if p.username or p.password:
        raise UnsafeURLError("URL 内嵌了凭据")
    if not host:
        raise UnsafeURLError("缺少主机名")
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeURLError("主机为回环域名")
    port = port or (443 if p.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise UnsafeURLError(f"DNS 解析失败（{e}）") from e
    ips = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise UnsafeURLError("域名解析结果为空")
    for ip in ips:
        if is_private_ip(ip):
            raise UnsafeURLError(f"域名解析到内网/保留 IP（{ip}）")
    return host, port, ips[0]


def safe_public_url(url):
    """URL 是否可安全出站（布尔版；需要拒绝原因时用 `resolve_public()`）。"""
    try:
        resolve_public(url)
    except UnsafeURLError:
        return False
    return True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """任何 3xx 都不跟随（返回 None 使 urllib 抛 HTTPError）。

    出站层刻意**不**提供「跟随后复检」：跳转目标同样是攻击者可控的字符串，
    复检逻辑一旦漏一处就等于全漏。要跳转就交给调用方自己决定。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """按 `pin_ip` 建 TCP，但 `Host` 头仍用原域名（虚拟主机语义不变）。"""

    def __init__(self, host, port=None, *, pin_ip=None, **kwargs):
        super().__init__(host, port, **kwargs)
        self.pin_ip = pin_ip or host

    def connect(self):
        if self._tunnel_host:
            raise UnsafeURLError("出站请求不支持 HTTP 代理")
        self.sock = self._create_connection(
            (self.pin_ip, self.port), self.timeout, self.source_address)
        # NODELAY 失败只是退化成默认缓冲，不该让整个请求失败
        with contextlib.suppress(OSError):
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


class _PinnedHTTPSConnection(_PinnedHTTPConnection, http.client.HTTPSConnection):
    """连固定 IP、按原域名做 SNI 与证书校验。

    MRO 是 `_PinnedHTTPSConnection → _PinnedHTTPConnection → HTTPSConnection`：
    `super().connect()` 只会用 `pin_ip` 建 TCP，`self.host` 保持原域名，
    因此 `wrap_socket(server_hostname=self.host)` 校验的仍是真实主机名。
    """

    def connect(self):
        if self._tunnel_host:
            raise UnsafeURLError("出站请求不支持 HTTPS 代理")
        super().connect()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pin_ip):
        super().__init__()
        self._pin_ip = pin_ip

    def http_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPConnection, pin_ip=self._pin_ip), req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pin_ip):
        super().__init__()
        self._pin_ip = pin_ip

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPSConnection, pin_ip=self._pin_ip), req,
                            context=self._context)


def open_public(url, timeout=10, headers=None, data=None):
    """安全出站**唯一入口**：校验 + 固定 IP + 禁跟随 3xx + 禁环境代理。

    `url` 可以是字符串（配 `headers`/`data`）或已构造好的 `Request`。
    返回 urllib 响应对象，调用方负责 `with`/`close` 并自行限制读取字节数。
    3xx/4xx/5xx 抛 `HTTPError`，地址不合格抛 `UnsafeURLError`。
    """
    if isinstance(url, urllib.request.Request):
        req = url
    else:
        # 这里被 `py/full-ssrf` 认成汇聚点，但 CodeQL 认不出**紧接其后**的
        # `resolve_public()` 才是净化器：那里已做完「http/https + 无凭据 +
        # 解析结果全部公网」判定，且下面建连用的就是这次解析得到的 IP，
        # 不存在第二次解析、不跟随 3xx、环境代理禁用。
        # codeql[py/full-ssrf] 下一行构造的 Request 在发出前必定经过 resolve_public() 校验
        req = urllib.request.Request(url, data=data, headers=dict(headers or {}))
    _host, _port, pin_ip = resolve_public(req.full_url)
    opener = urllib.request.build_opener(
        NoRedirect,
        urllib.request.ProxyHandler({}),
        _PinnedHTTPHandler(pin_ip),
        _PinnedHTTPSHandler(pin_ip),
    )
    return opener.open(req, timeout=timeout)
