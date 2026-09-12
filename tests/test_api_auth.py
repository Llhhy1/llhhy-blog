"""认证 API 冒烟测试（v3.17.11 · 审计 R76-R4 补测）。

背景：与 articles 面同理，`/api/auth/*`（注册/登录/会话）此前无专测，而它是最容易被
暴力破解与枚举攻击的面。本文件覆盖最小必要集（不测限流阈值本身，避免套件不稳定）：

1. `/api/csrf` 可获取会话 Token（SPA 写请求的前置条件）；
2. 未登录 `/api/auth/me` 返回 `user: null`，不泄露任何用户实体；
3. 错误密码登录 → 401，且**统一文案**（不区分用户是否存在，防枚举）；
4. 失败响应不泄露 traceback / 口令散列等内部信息。
"""


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def test_csrf_token_available(client):
    tok = _csrf(client)
    assert isinstance(tok, str) and len(tok) >= 16


def test_me_anonymous_returns_null_user(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    d = r.get_json() or {}
    assert d.get("user") is None
    assert "password_hash" not in r.get_data(as_text=True).lower()


def test_login_wrong_password_401_uniform_message(client):
    tok = _csrf(client)
    r = client.post(
        "/api/auth/login",
        json={"username": "zztest-nobody-9f8e", "password": "definitely-wrong-xyz"},
        headers={"X-CSRF-Token": tok},
    )
    assert r.status_code == 401
    # 统一文案（不区分「用户不存在」与「密码错误」），防止用户名枚举
    # 注意：Flask jsonify 会把中文转成 \uXXXX，需解析 JSON 后再比对
    assert (r.get_json() or {}).get("error") == "用户名或密码错误"
    low = r.get_data(as_text=True).lower()
    assert "traceback" not in low
    assert "password_hash" not in low


def test_login_response_never_echoes_password(client):
    tok = _csrf(client)
    secret = "should-never-be-echoed-123456"
    r = client.post(
        "/api/auth/login",
        json={"username": "zztest-nobody-9f8e", "password": secret},
        headers={"X-CSRF-Token": tok},
    )
    assert secret not in r.get_data(as_text=True)
