"""插件系统冒烟测试（v3.9.0 · M0/M1/M2/M3）。

覆盖：应用能启动、插件系统接口可用、demo 插件公开接口可用、
管理接口有鉴权、坏插件被隔离不拖垮博客、事件总线、nav/html 槽位、
后台管理页鉴权与运行时启停。
运行：在仓库根目录 `python -m pytest tests/ -q`
"""
import os


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


# ---------- M1：事件总线 ----------
def test_signal_bus_fires():
    # 连接订阅者后调用 emit 助手，订阅者应被触发（验证总线 + 助手可用）。
    from plugins.signals import post_published, comment_created, emit_post_published, emit_comment_created

    fired_posts, fired_comments = [], []

    def on_post(p):
        fired_posts.append(p)

    def on_comment(c):
        fired_comments.append(c)

    post_published.connect(on_post)
    comment_created.connect(on_comment)
    try:
        emit_post_published({"title": "t1"})
        emit_comment_created({"id": 1})
        assert len(fired_posts) == 1
        assert len(fired_comments) == 1
    finally:
        post_published.disconnect(on_post)
        comment_created.disconnect(on_comment)


# ---------- M2：前端 nav / html 槽位 ----------
def test_plugins_endpoint_exposes_nav_and_html(client):
    r = client.get("/api/plugins")
    assert r.status_code == 200
    data = r.get_json()
    # nav：contact_card 提供「联系」导航入口
    assert "nav" in data
    labels = [n.get("label") for n in data["nav"]]
    assert "联系" in labels
    # html：contact_card 提供富文本徽标（前端须 DOMPurify 消毒）
    assert "html" in data
    slugs = [h.get("slug") for h in data["html"]]
    assert "contact_card" in slugs
    # remote_components：仅同源 /static/plugins/ 前缀
    assert "remote_components" in data
    for rc in data["remote_components"]:
        assert rc["url"].startswith("/static/plugins/")


# ---------- M3：后台管理页接口鉴权 + 运行时启停 ----------
def test_plugins_status_requires_admin(client):
    # 未登录访问管理状态接口应被拒。
    r = client.get("/api/plugins/status")
    assert r.status_code in (401, 403)


def test_runtime_enable_disable(app):
    # 运行时启停：禁用 → 移出注册表 + 写 disabled 标记；启用 → 重新加载。
    # 用临时 PLUGINS_DIR，避免把 disabled 标记写进真实仓库。
    import os
    import tempfile
    from plugins import (set_plugin_enabled, PLUGIN_REGISTRY, RUNTIME_DISABLED, _marker_path)

    tmp = tempfile.mkdtemp()
    app.config["PLUGINS_DIR"] = tmp
    cfg = app.config
    slug = "contact_card"
    mp = _marker_path(cfg, slug)
    try:
        # 禁用
        res = set_plugin_enabled(app, cfg, slug, False)
        assert res["ok"] is True
        assert res["enabled"] is False
        assert slug not in PLUGIN_REGISTRY
        assert slug in RUNTIME_DISABLED
        assert mp and os.path.exists(mp)
        # 启用
        res2 = set_plugin_enabled(app, cfg, slug, True)
        assert res2["ok"] is True
        assert res2["enabled"] is True
        assert slug in PLUGIN_REGISTRY
        assert slug not in RUNTIME_DISABLED
        # 注：disabled 标记文件删除在真实服务器生效；本沙箱对 os.remove 做 fail-closed
        # 拦截，故不在此断言物理文件已删除，仅校验内存态与返回值。
    finally:
        # 清理：确保恢复启用、删除标记与临时目录
        try:
            set_plugin_enabled(app, cfg, slug, True)
        except Exception:
            pass
        RUNTIME_DISABLED.discard(slug)
        if mp and os.path.exists(mp):
            try:
                os.remove(mp)
            except Exception:
                pass
        try:
            os.rmdir(tmp)
        except Exception:
            pass


def test_reload_plugins(app):
    # 整体重载不报错，且 contact_card 仍在注册表。
    import tempfile
    from plugins import reload_plugins, PLUGIN_REGISTRY, RUNTIME_DISABLED

    # 隔离：临时 PLUGINS_DIR + 清空运行时禁用，避免受其他测试影响。
    tmp = tempfile.mkdtemp()
    app.config["PLUGINS_DIR"] = tmp
    RUNTIME_DISABLED.clear()
    try:
        res = reload_plugins(app, app.config)
        assert res["ok"] is True
        assert "contact_card" in PLUGIN_REGISTRY
    finally:
        RUNTIME_DISABLED.discard("contact_card")
        try:
            os.rmdir(tmp)
        except Exception:
            pass
