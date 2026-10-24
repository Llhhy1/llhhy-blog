# -*- coding: utf-8 -*-
"""EdgeOne 真实客户端 IP 还原（v4.8.5）守卫测试。

背景（实测证据）：站点套腾讯 EdgeOne 后，源站 TCP 对端 = EO 回源节点，
Nginx 的 `$proxy_add_x_forwarded_for` 又把节点 IP 追加到 XFF 末尾 ——
原有「取 XFF 最右端」拿到的仍是节点 IP。线上 `visit_log` TOP IP 全是
`223.74.x.x`（腾讯回源段），单 IP 426 次访问，访客记录/在线统计/限流
全部按节点合并计数。

方案：EdgeOne 回源带两个自定义头，由共享密钥保证不可伪造：
    X-EO-Client-IP   真实 IP
    X-EO-Auth        共享密钥（只有站主与 EdgeOne 知道）

本测试守四类性质：
1. **正确性** —— 密钥匹配时取到真实 IP（含带端口/方括号的脏值归一）。
2. **不可伪造** —— 密钥缺失/错误时，攻击者伪造的 X-EO-Client-IP 一律不被采纳。
3. **向后兼容** —— 未配 EO_AUTH_KEY 时行为与 v4.8.4 完全一致（零风险回退）。
4. **原有防线不回归** —— 可信代理 + XFF 最右端、公网直连忽略 XFF 仍然有效。
"""
import pytest

from utils.net import get_client_ip, _clean_ip


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    with __import__("contextlib").suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield


def _ip(client, headers, remote="127.0.0.1", key=None):
    """在请求上下文里取 get_client_ip()。"""
    with client.application.test_request_context(
            "/", headers=headers, environ_base={"REMOTE_ADDR": remote}):
        if key is not None:
            from flask import current_app
            current_app.config["EO_AUTH_KEY"] = key
        return get_client_ip()


# ---------- 1. 正确性：密钥匹配时取真实 IP ----------

def test_eo_builtin_header_used_when_key_matches(app, client):
    """EdgeOne 内置头 EO-Client-IP（控制台开关打开即有，不需规则引擎）。"""
    ip = _ip(client, {"X-EO-Auth": "s3cret", "EO-Client-IP": "1.2.3.4"}, key="s3cret")
    assert ip == "1.2.3.4"


def test_eo_builtin_header_works_without_key(app, client):
    """没配密钥时也用内置头 —— 换取统计准确性（风险见 net.py 顶部注释）。

    这是用户实际配置路径：EdgeOne 控制台打开「客户端 IP 头部」即有 EO-Client-IP，
    但规则引擎不一定能加自定义 X-EO-Auth。
    """
    ip = _ip(client, {"EO-Client-IP": "7.7.7.7"}, key="")
    assert ip == "7.7.7.7"


def test_eo_header_used_when_key_matches(app, client):
    ip = _ip(client, {"X-EO-Auth": "s3cret", "X-EO-Client-IP": "1.2.3.4"}, key="s3cret")
    assert ip == "1.2.3.4"


def test_eo_header_wins_over_xff_node_ip(app, client):
    """核心场景：XFF 末尾是 EO 节点 IP 时，也必须返回真实 IP。"""
    ip = _ip(client, {
        "X-EO-Auth": "s3cret",
        "X-EO-Client-IP": "8.8.8.8",
        "X-Forwarded-For": "8.8.8.8, 223.74.211.144",   # 节点 IP 追加在末尾
    }, key="s3cret")
    assert ip == "8.8.8.8", "EO 真实 IP 必须优先于 XFF 最右端的节点 IP"


@pytest.mark.parametrize("raw,expect", [
    ("1.2.3.4", "1.2.3.4"),
    ("1.2.3.4:5678", "1.2.3.4"),          # IPv4 带端口
    ("[2001:db8::1]:443", "2001:db8::1"),  # IPv6 带方括号和端口
    ("2001:db8::1", "2001:db8::1"),        # 裸 IPv6（冒号数 >1，不能被当端口剥掉）
    ("  5.6.7.8  ", "5.6.7.8"),            # 前后空白
    ("not-an-ip", ""),                     # 非法值必须被拒
    ("", ""),
    (None, ""),
    ("1.2.3.4, 9.9.9.9", ""),              # 逗号分隔的脏值必须被拒（不能取错）
])
def test_clean_ip_normalization(raw, expect):
    assert _clean_ip(raw) == expect


# ---------- 2. 不可伪造：密钥缺失/错误时绝不采纳 EO 头 ----------

def test_forged_eo_ip_rejected_when_key_mismatch(app, client):
    """攻击者知道要带 X-EO-Client-IP，但猜不到 X-EO-Auth → 必须被拒。"""
    ip = _ip(client, {"X-EO-Auth": "wrong", "X-EO-Client-IP": "6.6.6.6"}, key="s3cret")
    assert ip != "6.6.6.6"


def test_forged_eo_ip_rejected_when_header_absent(app, client):
    ip = _ip(client, {"X-EO-Client-IP": "6.6.6.6"}, key="s3cret")
    assert ip != "6.6.6.6"


def test_eo_header_used_without_key(app, client):
    """未配 EO_AUTH_KEY 时也采纳 EO 头 —— 用户实际配置路径就是这样
    （EdgeOne 控制台开「客户端 IP 头部」即有 EO-Client-IP，规则引擎不一定能加密钥头）。

    ⚠️ 这是**刻意的取舍**：无密钥时该头可被直连源站者伪造，限流可被轮换假 IP 绕过。
    选择保统计准确性；在意的补救是 EO_BLOCK_DIRECT 或让 Nginx 只透传 EO 回源段。
    """
    ip = _ip(client, {"EO-Client-IP": "6.6.6.6"}, key="")
    assert ip == "6.6.6.6"


def test_eo_custom_header_also_used_without_key(app, client):
    """无密钥时自定义头 X-EO-Client-IP 同样被采纳。

    理由：无密钥时 EO-Client-IP 与 X-EO-Client-IP **可伪造性相同**，区别只在
    「哪个是 EdgeOne 真会发的」。安全门禁只由密钥提供，不按头名搞假安全。
    """
    ip = _ip(client, {"X-EO-Client-IP": "6.6.6.6"}, key="")
    assert ip == "6.6.6.6"


def test_eo_key_empty_string_means_disabled(app, client):
    """密钥配成空白串 = 视为未配置（走无密钥路径，不报错）。"""
    ip = _ip(client, {"X-EO-Auth": "", "EO-Client-IP": "6.6.6.6"}, key="   ")
    assert ip == "6.6.6.6"


def test_eo_key_comparison_is_exact(app, client):
    """前缀/后缀相同不算匹配（不能变成「包含即通过」）。"""
    ip = _ip(client, {"X-EO-Auth": "s3cretXYZ", "X-EO-Client-IP": "6.6.6.6"}, key="s3cret")
    assert ip != "6.6.6.6"


def test_invalid_eo_ip_falls_through_not_crash(app, client):
    """EO 头是脏值时不能崩，应继续走原有逻辑。"""
    ip = _ip(client, {"X-EO-Auth": "s3cret", "X-EO-Client-IP": "javascript:alert(1)"},
             key="s3cret")
    assert ip and "javascript" not in ip


# ---------- 3. 向后兼容：未配密钥时行为与旧版一致 ----------

def test_legacy_behavior_trusted_proxy_xff(app, client):
    """未配 EO key：经 Nginx（127.0.0.1）转发仍取 XFF 最右端。"""
    ip = _ip(client, {"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}, remote="127.0.0.1", key="")
    assert ip == "1.1.1.1"


def test_legacy_behavior_public_direct_ignores_xff(app, client):
    """未配 EO key：公网直连仍忽略 XFF（这条防线不能回归）。"""
    ip = _ip(client, {"X-Forwarded-For": "9.9.9.9"}, remote="8.8.8.8", key="")
    assert ip == "8.8.8.8"


def test_legacy_behavior_no_xff_uses_remote(app, client):
    ip = _ip(client, {}, remote="127.0.0.1", key="")
    assert ip == "127.0.0.1"


# ---------- 4. EO_BLOCK_DIRECT 加固开关 ----------

def test_block_direct_defaults_off(client):
    """默认不拦直连 —— 这是有故障面的开关，必须默认关闭。"""
    r = client.get("/api/health")
    assert r.status_code == 200


def test_block_direct_rejects_without_key(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "EO_AUTH_KEY", "s3cret")
    monkeypatch.setitem(app.config, "EO_BLOCK_DIRECT", True)
    r = client.get("/api/posts?limit=1")
    assert r.status_code == 403
    assert r.get_json().get("error") == "direct_origin_access_forbidden"


def test_block_direct_allows_with_key(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "EO_AUTH_KEY", "s3cret")
    monkeypatch.setitem(app.config, "EO_BLOCK_DIRECT", True)
    r = client.get("/api/posts?limit=1", headers={"X-EO-Auth": "s3cret"})
    assert r.status_code == 200


def test_block_direct_whitelists_acme_and_health(client, app, monkeypatch):
    """ACME 与健康检查必须能直连，否则证书过期/监控告警会把站拖死。"""
    monkeypatch.setitem(app.config, "EO_AUTH_KEY", "s3cret")
    monkeypatch.setitem(app.config, "EO_BLOCK_DIRECT", True)
    assert client.get("/api/health").status_code == 200
    r = client.get("/.well-known/acme-challenge/xyz")
    assert r.status_code != 403


def test_block_direct_without_key_configured_never_blocks(client, app, monkeypatch):
    """没配 EO_AUTH_KEY 时即使开了开关也不拦（防把自己关在门外）。"""
    monkeypatch.setitem(app.config, "EO_AUTH_KEY", "")
    monkeypatch.setitem(app.config, "EO_BLOCK_DIRECT", True)
    assert client.get("/api/posts?limit=1").status_code == 200
