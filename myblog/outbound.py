"""出站 URL 安全校验（SSRF 防护）+ 统一出站入口（v4.7.4）。

只允许 http/https，且域名必须解析到**公网**地址：私网、回环、链路本地、
保留、组播、未指定地址一律拒绝。URL 内嵌凭据也拒绝。

**为什么要有统一入口（v4.7.4）**
此前每个出口各自实现一套 —— `feed_agg.py` 自己写了一份 `_NoRedirect`、
自己写了一份私网判断，`games.py` 走 `safe_public_url` + 自己的 opener，
`seo_push.py` / `oauth.py` 各有各的。口径必然漂移，改一处漏三处。
现在统一到这里：

    from outbound import open_url
    with open_url(url, timeout=10) as resp:
        data = resp.read(1 << 20)

**IP pinning —— 根治 DNS rebinding**
`safe_public_url()` 解析 DNS 一次、校验完**只返回布尔值**；调用方随后
`opener.open(url)` 时 HTTP 客户端会**再解析一次 DNS** —— 两次独立解析之间，
攻击者可以把 DNS 改指回环/内网（DNS rebinding）。这是典型的「检查-使用时」
竞态（TOCTOU），**重复校验无法消除**，只有把**已校验过的 IP 固定下来**才行。

`open_url()` 做的正是这件事：解析 → 校验 → **把 IP 固定在连接上**，之后不再解析。
TCP 连的是已验证的 IP，但 HTTP `Host` 头与 TLS SNI 仍用原域名
（否则证书校验与虚拟主机都会失效）。

> ⚠️ **pinning 在走代理时无效** —— 目标 IP 由代理解析。故 `build_opener()`
> 显式装一个空的 `ProxyHandler({})` 禁掉环境代理。
"""
import http.client
import ipaddress
import socket
import urllib.parse
import urllib.request


class OutboundRejected(Exception):
    """出站请求被安全策略拒绝（URL 不合法 / 指向非公网 / 协议不支持）。"""


def is_private_ip(ip):
    """非公网地址（含私网/回环/链路本地/保留/组播/未指定）返回 True。"""
    try:
        obj = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not obj.is_global


def _check(url):
    """判据的**唯一实现**。返回 ``(ok, reason, host, port, ips)``。

    `resolve_public()` 与 `check_public_url()` 都从这里派生 ——
    判据只写一遍，避免「放行用一套、给人看的提示又用另一套」那种漂移。
    """
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower()
        port = p.port
    except (TypeError, ValueError):
        return False, "URL 格式不合法", None, None, []
    if p.scheme not in ("http", "https"):
        return False, "只允许 http/https 协议", None, None, []
    if p.username or p.password:
        return False, "URL 里不允许内嵌凭据", None, None, []
    if not host:
        return False, "缺少主机名", None, None, []
    if host == "localhost" or host.endswith(".localhost"):
        return False, "主机是回环地址", None, None, []
    if port is not None and not (0 < port < 65536):
        return False, "端口不合法", None, None, []
    default_port = 443 if p.scheme == "https" else 80
    try:
        infos = socket.getaddrinfo(host, port or default_port,
                                   type=socket.SOCK_STREAM)
    except OSError as e:
        return False, "DNS 解析失败（%s）" % (str(e)[:60]), host, None, []
    ips = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    if not ips:
        return False, "域名解析结果为空", host, None, []
    bad = [ip for ip in ips if is_private_ip(ip)]
    if bad:
        return False, "域名解析到内网/保留 IP（%s）" % bad[0], host, None, ips
    return True, "", host, (port or default_port), ips


def resolve_public_ex(url):
    """一次解析，给出**全部**信息：``(ok, reason, host, port, ips)``。

    为什么要有这个「ex」版本：调用方常常需要**同一个解析结果**既做放行决策、
    又拿 IP 去固定连接 —— 如果先调 `resolve_public()` 校验、再调别的函数解析一次，
    两次解析之间 DNS 可被改指内网，**固定下来的那个 IP 根本没经过校验**。

    所以：**一次解析 → 同时拿到「能不能放行」和「用哪个 IP」**。
    """
    return _check(url)


def resolve_public(url):
    """解析并校验 URL，返回 ``(host, port, ips)``；不合格返回 ``None``。

    与旧版 `safe_public_url` 的差别只有一个，但很关键：**把解析出来的 IP 一起返回**。
    旧版算完就扔，只留一个布尔值，调用方随后让 HTTP 客户端**重新解析**一次 DNS ——
    两次解析之间 DNS 可被改指内网（DNS rebinding）。
    调用方应当把这组 IP **固定下来**使用（见 `open_url` / `build_opener`）。

    `ips` 保留全部解析结果：真实环境里一个域名可能解析出多个 IP，
    逐个尝试比只取第一个更不容易「第一个连不上就直接失败」。
    """
    ok, _reason, host, port, ips = _check(url)
    if not ok:
        return None
    return host, port, ips


def check_public_url(url):
    """返回 ``(是否通过, 原因)`` —— 给「为什么被拒」这类提示用。

    判据与 `resolve_public` **完全一致**（同一个 `_check`），
    不会出现「放行是一套标准、提示语是另一套标准」。
    """
    ok, reason, _host, _port, _ips = _check(url)
    return ok, reason


def safe_public_url(url):
    """URL 是否可安全出站：http/https + 公网解析结果 + 不含凭据。

    保留这个函数是因为既有调用方（`games.py` 等）用它做**保存前**的预检查 ——
    那一步的语义正是「这个地址能不能填」，不需要固定 IP。
    """
    return resolve_public(url) is not None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """任何 3xx 都不跟随（返回 None 使 urllib 抛 HTTPError）。

    堵的是「公网 302 → 内网元数据服务」这条最常见的 SSRF 绕过：
    预检查看到的是公网地址，跳转变量却**从不复检**。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


# ---------- IP pinning：把已校验的 IP 固定在连接上 ----------


class _PinnedMixin:
    """连接目标固定为**已校验过**的 IP，而不是让系统再解析一次 DNS。"""

    _pinned_ips = ()

    def _connect_socket(self, timeout):
        """依次尝试已固定的 IP；全部失败才报错。"""
        last = None
        for ip in self._pinned_ips:
            try:
                return socket.create_connection((ip, self.port), timeout,
                                                self.source_address)
            except OSError as e:
                last = e
        if last is None:
            raise OSError("没有可用的已校验 IP")
        raise last


class _PinnedHTTPConnection(_PinnedMixin, http.client.HTTPConnection):
    def __init__(self, host, port=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                 pinned_ips=(), **kw):
        # `host` 可能带端口（urllib 的 do_open 传的是 req.host，形如 "h:8080"），
        # http.client 自己会拆 —— 这里原样传下去即可。
        super().__init__(host, port, timeout=timeout, **kw)
        self._pinned_ips = tuple(pinned_ips)

    def connect(self):
        self.sock = self._connect_socket(self.timeout)
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(_PinnedMixin, http.client.HTTPSConnection):
    def __init__(self, host, port=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                 pinned_ips=(), context=None, **kw):
        super().__init__(host, port, timeout=timeout, context=context, **kw)
        self._pinned_ips = tuple(pinned_ips)

    def connect(self):
        sock = self._connect_socket(self.timeout)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        else:
            # ⚠️ `server_hostname=self.host` 必须保留 —— SNI 与证书校验都靠它。
            #    固定的只是 TCP 目标，**身份**仍然是原域名。
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        ips = getattr(req, "_pinned_ips", None)
        if not ips:
            return self.do_open(http.client.HTTPConnection, req)
        return self.do_open(_PinnedHTTPConnection, req, pinned_ips=ips)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        ips = getattr(req, "_pinned_ips", None)
        ctx = self._context
        if not ips:
            return self.do_open(http.client.HTTPSConnection, req, context=ctx)
        return self.do_open(_PinnedHTTPSConnection, req, context=ctx, pinned_ips=ips)


def build_opener(pinned=True, context=None):
    """构造出站 opener。

    - 恒定装 `NoRedirect`：**任何 3xx 都不跟随**。
    - 恒定装空的 `ProxyHandler({})`：禁掉环境代理。走代理时目标 IP 由代理解析，
      pinning 就没有意义了（等于没 pin）。
    - `pinned=True` 时用固定 IP 的连接类。
    """
    handlers = [
        urllib.request.ProxyHandler({}),
        NoRedirect(),
    ]
    if pinned:
        handlers.append(_PinnedHTTPHandler())
        handlers.append(_PinnedHTTPSHandler(context=context))
    else:
        handlers.append(urllib.request.HTTPHandler())
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def open_url(url, *, timeout=10, data=None, headers=None, method=None,
             context=None, pinned_ips=None):
    """统一出站入口：校验 → 固定 IP → 禁跟随 3xx。

    返回 `http.client.HTTPResponse`（调用方负责 `with` / `close`）。
    校验不通过抛 `OutboundRejected`。

    `pinned_ips`：**已经校验过的那组 IP**。调用方若已经做过
    `resolve_public_ex()`（它一次解析就同时给出「能不能放行」和「用哪个 IP」），
    就把 `ips` 传进来 —— 这样**校验与固定用的是同一次解析**，
    不会出现「校验的是 A、固定的是 B」这种致命的不一致。
    不传则本函数自己解析一次并校验。

    ⚠️ **不限制响应体大小** —— 上限由调用方按业务决定（RSS 5MB、LLM 1MB…），
    统一层强设一个值会误伤合法的大响应。需要限流时用 `read_limited()`。
    """
    if pinned_ips:
        ips = list(pinned_ips)
    else:
        resolved = resolve_public(url)
        if resolved is None:
            raise OutboundRejected("URL 未通过出站安全校验：%s" % (url or "")[:120])
        _host, _port, ips = resolved
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method=method)
    # 把已校验的 IP 挂到 Request 上，连接类据此固定目标。
    req._pinned_ips = ips
    opener = build_opener(pinned=True, context=context)
    return opener.open(req, timeout=timeout)


def read_limited(resp, max_bytes):
    """读响应体，超过上限就截断（不会像 `resp.read()` 那样把内存吃光）。

    返回 ``(data, truncated)``。
    """
    chunks = []
    got = 0
    while True:
        chunk = resp.read(min(65536, max_bytes - got + 1))
        if not chunk:
            break
        got += len(chunk)
        if got > max_bytes:
            chunks.append(chunk[:max_bytes - (got - len(chunk))])
            return b"".join(chunks), True
        chunks.append(chunk)
    return b"".join(chunks), False
