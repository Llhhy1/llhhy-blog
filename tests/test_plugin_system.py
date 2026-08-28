"""插件系统冒烟测试（v3.9.0 · M0）。

覆盖：应用能启动、插件系统接口可用、demo 插件公开接口可用、
管理接口有鉴权、坏插件被隔离不拖垮博客。
运行：在仓库根目录 `python -m pytest tests/ -q`
"""


def test_app_boots_and_plugins_endpoint(client):
    r = client.get("/api/plugins")
    assert r.status_code == 200
    data = r.get_json()
    assert "plugins" in data and "footer" in data
    # 默认启用 contact_card（见 config.ENABLED_PLUGINS）
    ids = [p["id"] for p in data["plugins"]]
    assert "contact_card" in ids


def test_contact_card_list_public(client):
    r = client.get("/api/plugin/contact_card/list")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_admin_upsert_requires_login(client):
    # 未登录写操作应被拒（CSRF 或登录校验），验证管理接口有鉴权屏障。
    r = client.post(
        "/api/plugin/contact_card/upsert",
        json={"title": "x", "csrf_token": "bad"},
    )
    assert r.status_code in (401, 403)


def test_failure_isolation_bad_plugin(monkeypatch):
    # 启用一个不存在的插件 slug，create_app 不应崩溃，
    # 且 /api/plugins 仍正常只列出 contact_card。
    # 注意：Config 类在导入时即固化 env 值，需用 setattr 改类属性（setenv 无效）。
    import config as _cfg
    monkeypatch.setattr(_cfg.Config, "ENABLED_PLUGINS", "nonexistent_slug,contact_card")
    monkeypatch.setattr(_cfg.Config, "DISABLED_PLUGINS", "")
    from app import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/plugins")
    assert r.status_code == 200
    ids = [p["id"] for p in r.get_json()["plugins"]]
    assert "contact_card" in ids
    assert "nonexistent_slug" not in ids


def test_disabled_plugin_skipped(monkeypatch):
    # DISABLED_PLUGINS 优先级高于 ENABLED_PLUGINS，contact_card 应被跳过。
    import config as _cfg
    monkeypatch.setattr(_cfg.Config, "ENABLED_PLUGINS", "contact_card")
    monkeypatch.setattr(_cfg.Config, "DISABLED_PLUGINS", "contact_card")
    from app import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/plugins")
    assert r.status_code == 200
    ids = [p["id"] for p in r.get_json()["plugins"]]
    assert "contact_card" not in ids
