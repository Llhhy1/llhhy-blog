# -*- coding: utf-8 -*-
"""限流、可信代理与客户端 IP / 客户端标识。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import time
import ipaddress

# ---------- 限流（Redis 全局 / 内存回退）----------
# 单进程内有效；多 worker 部署下作为纵深防御，不替代专业限流组件。
# v3.1.6（高优）：配置 REDIS_URL 后改用 Redis 滑动窗口计数（多 worker 全局一致），
# 未配置自动回退内存计数（单进程）。Redis 连接异常时静默回退内存，不影响主流程。
_RATE = {}
_REDIS_KEY_PREFIX = "blog:rl:"


def _redis():
    """按需创建 Redis 客户端（懒加载，失败返回 None）。"""
    try:
        from flask import current_app
        import redis as _redis_mod
        url = current_app.config.get("REDIS_URL", "")
        if not url:
            return None
        return _redis_mod.from_url(url, socket_connect_timeout=2, socket_timeout=2,
                                   decode_responses=True)
    except Exception:
        return None


def rate_limit(key, limit=20, window=60):
    """返回 True 表示允许；超出则 False。key 通常含 IP。

    Redis 模式：用 INCR + EXPIRE 做固定窗口计数（首请求建键，超限返回 False）。
    内存模式：滑动窗口时间戳列表（旧逻辑）。
    """
    now = time.time()
    r = _redis()
    if r is not None:
        try:
            rk = _REDIS_KEY_PREFIX + str(key)
            # 固定窗口：计数 + 过期（窗口长度秒）。首请求 INCR=1 后设一次过期。
            c = r.incr(rk)
            if c == 1:
                r.expire(rk, window)
            return int(c) <= limit
        except Exception:  # noqa: S110  Redis 不可用则回退内存实现
            pass  # Redis 异常回退内存
    hits = _RATE.get(key, [])
    hits = [t for t in hits if now - t < window]
    if len(hits) >= limit:
        _RATE[key] = hits
        return False
    hits.append(now)
    _RATE[key] = hits
    return True


def _parse_trusted_proxies(cfg):
    """解析 TRUSTED_PROXIES 配置（逗号分隔的 IP 或 CIDR），返回 (ip集合, 网段列表)。"""
    ips = set()
    nets = []
    for raw in (cfg or "").split(","):
        s = raw.strip()
        if not s:
            continue
        try:
            if "/" in s:
                nets.append(ipaddress.ip_network(s, strict=False))
            else:
                ips.add(str(ipaddress.ip_address(s)))
        except Exception:
            continue
    return ips, nets


def _is_trusted_proxy(ip, trusted):
    """判断 TCP 直连对端 ip 是否为可信代理。

    - 若显式配置了 TRUSTED_PROXIES，命中 IP/CIDR 即视为可信；
    - 否则采用安全默认：仅「内部地址」（私网/回环/链路本地/保留等不可公网直达）
      视为可信代理；公网直连地址不可信——攻击者可在公网任意伪造 XFF。
    """
    try:
        a = ipaddress.ip_address(ip)
    except Exception:
        return False
    ips, nets = trusted
    if ip in ips:
        return True
    for n in nets:
        if a in n:
            return True
    return not a.is_global


# ===== EdgeOne 真实客户端 IP 还原（v4.8.5）=====
# 站点套了腾讯 EdgeOne 后，源站 TCP 对端 = EO 回源节点；Nginx 的
# $proxy_add_x_forwarded_for 又会把节点 IP 追加到 XFF 末尾，于是「取 XFF 最右端」
# 拿到的仍是节点 IP（实测线上 visit_log TOP IP 全是 223.74.x.x，单 IP 426 次）。
#
# 解法（两路，按优先级）：
#   ① **EdgeOne 内置头** `EO-Client-IP` —— 控制台「站点加速 → 回源配置 →
#      客户端 IP 头部」打开后，EO 自动带上，**不需要规则引擎、不需要猜变量名**。
#   ② 共享密钥头 `X-EO-Auth`（需 EdgeOne 规则引擎支持自定义回源头）——
#      公网攻击者能伪造 ① 的头，但猜不到这个密钥；密钥不匹配就整个分支不生效。
#
# ⚠️ 安全含义（重要）：只开 ① 而没配 ② 时，`EO-Client-IP` 是可被直连源站者伪造的
#   （谁都能给自己的请求加这个头）。此时本函数仍会采纳它 —— 换取统计准确性，
#   代价是限流可被轮换假 IP 绕过。若在意，见 app.py 的 EO_BLOCK_DIRECT
#   （拒绝直连源站）或让 Nginx 只对 EO 回源段透传该头。
EO_CLIENT_IP_HEADERS = ("EO-Client-IP", "X-EO-Client-IP")
EO_AUTH_HEADER = "X-EO-Auth"


def _eo_auth_key():
    """取 EdgeOne 共享密钥（部署侧机密）。空 = 未启用 EO 还原。"""
    from flask import current_app
    try:
        return (current_app.config.get("EO_AUTH_KEY") or "").strip()
    except Exception:  # noqa: BLE001  无 app 上下文（如后台脚本）按未启用处理
        return ""


def _clean_ip(raw):
    """把头里取到的值归一成合法 IP；不合法返回 ""（严防脏值进库/进日志）。

    兼容 "1.2.3.4" / "1.2.3.4:5678" / "[2001:db8::1]:443" / "2001:db8::1"。
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if s.startswith("["):                       # [IPv6] 或 [IPv6]:port
        s = s[1:].split("]", 1)[0]
    elif s.count(":") == 1 and "." in s:        # IPv4:port（IPv6 冒号数 >1，不误伤）
        s = s.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(s))
    except Exception:
        return ""


def get_client_ip():
    """取客户端真实 IP（服务端统一收口，杜绝伪造 XFF 绕过限流/埋点/属地）。

    安全模型（v4.8.5 起分三级，优先级从高到低）：
    0. **EdgeOne 真实 IP 头**（`EO-Client-IP`，EdgeOne 内置，控制台开关打开即有）：
       - 配了 `EO_AUTH_KEY` 时，还要求 `X-EO-Auth` 完全匹配才采纳 —— 公网攻击者
         能伪造前者但猜不到后者，**这一级不可伪造**；
       - 没配密钥时也采纳内置头（换取统计准确性），但此时直连源站者可伪造该头，
         限流可被轮换假 IP 绕过 —— 风险与取舍见模块顶部注释。
    1. X-Forwarded-For 仅在「TCP 直连对端 remote_addr 是可信代理」时才可被采纳；
       公网直连的请求一律忽略 XFF，直接使用不可伪造的 remote_addr——
       攻击者即便伪造任意公网 XFF 也会被丢弃，无法轮换 IP 绕过限流。
    2. 采纳 XFF 时取**最右端**一段（最近一跳代理追加的真实客户端 IP），
       丢弃客户端在 XFF 左侧自行伪造的任意前缀，避免首段被篡改。
    """
    from flask import request, current_app
    remote = request.remote_addr or ""
    if not remote:
        return ""
    # 0) EdgeOne 真实 IP 头（EO-Client-IP 为 EdgeOne 内置；X-EO-Client-IP 为备选自定义名）
    #    安全门禁只由密钥提供：配了 EO_AUTH_KEY 就要求 X-EO-Auth 完全匹配（不可伪造）；
    #    没配密钥时无条件采纳 —— 两个头在无密钥时**同样可被直连源站者伪造**，
    #    区别只在「哪个是 EdgeOne 真会发的」。此处选择保统计准确性，风险见顶部注释。
    eo_key = _eo_auth_key()
    if (not eo_key) or request.headers.get(EO_AUTH_HEADER, "") == eo_key:
        for _h in EO_CLIENT_IP_HEADERS:
            eo_ip = _clean_ip(request.headers.get(_h, ""))
            if eo_ip:
                return eo_ip
    cfg = ""
    try:
        cfg = current_app.config.get("TRUSTED_PROXIES", "")
    except Exception:
        cfg = ""
    trusted = _parse_trusted_proxies(cfg)
    if not _is_trusted_proxy(remote, trusted):
        # 直连对端不是可信代理：XFF 完全由客户端控制，忽略，用不可伪造的 remote_addr
        return remote
    # 经可信代理转发：取 XFF 最右端、且为合法 IP 的一段作为真实客户端 IP
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for cand in reversed([p.strip() for p in xff.split(",") if p.strip()]):
            try:
                ipaddress.ip_address(cand)
            except Exception:
                continue
            return cand
    return remote


def client_key(prefix):
    """基于客户端真实 IP 生成限流 key（服务端统一收口，防伪造 XFF 绕过限流）。"""
    ip = get_client_ip() or "unknown"
    return f"{prefix}:{ip}"
