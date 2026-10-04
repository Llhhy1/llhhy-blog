# -*- coding: utf-8 -*-
"""SSL 证书到期监控（v3.25.3）。

**为什么必须有**：证书过期会让**全站直接不可访问**（HTTP 80 → 301 跳 HTTPS →
证书过期 → 浏览器拒绝）。2026-10-02 22:59 到期，10-05 才发现 —— 靠「记得看」
这种机制对**有硬期限的基础设施**是失效的。

**三个关键设计决定**：

1. **走 TLS 握手，不读证书文件。**
   宝塔的 `fullchain.pem` 权限是 `drw-------`/`-rw-------`（**root only**），
   而 gunicorn 以 `www` 用户运行 —— **读文件必然 PermissionError**。
   ���且证书路径会随宝塔续签/迁移而变，硬编码路径等于埋一颗定时炸弹。
   握手拿到的是**访客真正看到的那张证书**，权威且零依赖。

2. **域名取自 `site_base()`，不硬编码。**
   硬编码 `www.llhhy.cn` 会在换域名时变成**静默失效的假监控** ——
   它会一直报「正常」，因为你连的是旧域名或根本没连。

3. **只提醒，不续签。**
   证书签发涉及域名验证/CA 授权，**不是应用层该做的事**。
   本模块只回答一个问题：**还剩多少天**。
"""
import datetime
import json
import logging
import os
import socket
import ssl

logger = logging.getLogger(__name__)

STATE_FILE = "cert_check.json"

# 分级阈值。30 天不是拍脑袋：本项目证书是 90 天有效期（TrustAsia DV），
# 留 30 天 = 到期前有 **1/3 的余量**，足够处理「续签失败要重来一次」的情况。
WARN_DAYS = 30
CRIT_DAYS = 7


def _state_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", STATE_FILE)


def read_state():
    """读上次巡检结果；文件不存在/损坏返回「未检查」而非抛异常。

    与 `backup.read_verify_state` 同范式：诊断页要的是「有没有问题」，
    不是「有没有数据」。
    """
    defaults = {"status": "never", "checked_at": "", "days_left": None,
                "not_after": "", "subject": "", "issuer": "", "message": "尚未检查证书有效期"}
    try:
        with open(_state_path(), encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict):
            merged = dict(defaults)
            merged.update(st)
            return merged
    except (OSError, ValueError):
        pass
    return defaults


def _write_state(st):
    try:
        os.makedirs(os.path.dirname(_state_path()), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("[证书监控] 状态落盘失败: %s", e)


def _target_host():
    """要检查的 host：优先 `site_base()`（全站唯一真相源），回退本机名。

    ⚠️ 刻意**不硬编码域名** —— 见模块 docstring 第 2 条。
    """
    try:
        from utils import site_base
        base = (site_base() or "").strip()
        if base:
            host = base.split("://", 1)[-1].split("/", 1)[0]
            return host.split(":", 1)[0]      # 去端口
    except Exception:
        pass
    return socket.gethostname()


def _fetch_cert_der(host, port=443, timeout=6):
    """TLS 握手取回对端证书 DER。

    `verify_mode = CERT_NONE` 是**刻意**的：证书已过期时默认校验会直接抛
    `SSLCertVerificationError`，而我们恰恰要读的就是「过期的那张」。
    安全性上这不构成问题 —— 只读 notAfter，不传输任何凭据。
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.getpeercert(binary_form=True)


def _parse_der(der):
    """解析 DER → {not_after, subject, issuer}。

    优先用 `cryptography`（纯 Python、无子进程）；它在 requirements 里是
    **可选依赖**（2026-10-05 实测生产环境 50.0.1 可用），故必须有回退。
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        c = x509.load_der_x509_certificate(der)

        def _name(n):
            try:
                return n.rfc4514_string()
            except Exception:
                return str(n)
        return {
            "not_after": c.not_valid_after_utc,      # cryptography ≥42 给的 *_utc
            "subject": _name(c.subject),
            "issuer": _name(c.issuer),
            "parser": "cryptography",
        }
    except Exception:
        pass
    # 回退：openssl 命令行（实测生产有 /usr/bin/openssl 3.5.6）
    import subprocess
    import tempfile
    out = {"not_after": None, "subject": "", "issuer": "", "parser": "openssl"}
    with tempfile.NamedTemporaryFile(suffix=".der", delete=False) as tf:
        tf.write(der)
        tmp = tf.name
    try:
        txt = subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-in", tmp, "-noout",
             "-enddate", "-subject", "-issuer"],
            capture_output=True, text=True, timeout=10).stdout
        for line in txt.splitlines():
            if line.startswith("notAfter="):
                out["not_after"] = datetime.datetime.strptime(
                    line.split("=", 1)[1].strip(), "%b %d %H:%M:%S %Y %Z").replace(
                    tzinfo=datetime.timezone.utc)
            elif line.startswith("subject="):
                out["subject"] = line.split("=", 1)[1].strip()
            elif line.startswith("issuer="):
                out["issuer"] = line.split("=", 1)[1].strip()
    except Exception:
        pass
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out


def _naive_to_utc(dt):
    """把 naive datetime 当作 UTC（openssl 回退路径给的是不带时区的值）。

    X.509 的 notBefore/notAfter **按定义就是 UTC**，所以这个假设是安全的；
    加这层只是因为 cryptography 的 `not_valid_after`（旧版）返回 naive。
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def check_once(warn_days=WARN_DAYS):
    """检查一次并落盘。返回状态 dict。

    状态取值：
    - `expired` 已过期（**站点很可能已不可访问**，最高优先级）
    - `critical` ≤ 7 天
    - `warn` ≤ warn_days（默认 30）
    - `ok` > warn_days
    - `unknown` 拿不到证书（未启用 HTTPS / 端口不通 / 解析失败）
    """
    host = _target_host()
    now = datetime.datetime.now(datetime.timezone.utc)
    st = {"status": "unknown", "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
          "host": host, "days_left": None, "not_after": "", "subject": "",
          "issuer": "", "message": ""}
    try:
        der = _fetch_cert_der(host)
    except Exception as e:
        st["message"] = "无法连接 %s:443 取证书（%s）——请确认 HTTPS 是否启用" % (
            host, type(e).__name__)
        _write_state(st)
        return st

    info = _parse_der(der)
    not_after = _naive_to_utc(info.get("not_after"))
    if not_after is None:
        st["message"] = "已取到证书但解析失败（缺 cryptography 与 openssl？）"
        _write_state(st)
        return st

    delta = not_after - now
    days = int(delta.total_seconds() // 86400)
    st.update(days_left=days, not_after=not_after.strftime("%Y-%m-%d %H:%M:%S UTC"),
              subject=info.get("subject") or "", issuer=info.get("issuer") or "")
    if days < 0:
        st["status"] = "expired"
        st["message"] = "证书已过期 %d 天，HTTPS 很可能已不可访问，请立即续签" % (-days)
    elif days <= CRIT_DAYS:
        st["status"] = "critical"
        st["message"] = "证书只剩 %d 天，��本周内必须续签" % days
    elif days <= warn_days:
        st["status"] = "warn"
        st["message"] = "证书剩 %d 天，建议尽快续签（有效期通常 90 天）" % days
    else:
        st["status"] = "ok"
        st["message"] = "证书有效，剩 %d 天" % days
    _write_state(st)
    return st


def status_level(status):
    """状态 → 诊断页的 level（诊断页只认 ok/warn/error）。"""
    if status == "ok":
        return "ok"
    if status in ("warn", "critical"):
        return "warn"
    if status == "expired":
        return "error"
    return "info"
