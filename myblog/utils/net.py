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
        except Exception:
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


def get_client_ip():
    """取客户端真实 IP（服务端统一收口，杜绝伪造 XFF 绕过限流/埋点/属地）。

    安全模型：
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
