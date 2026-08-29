"""插件系统冒烟测试（框架层 · v3.10.0 起不再依赖内置插件）。

v3.10.0 起仓库**不再内置任何插件**（contact_card / article_toc 已下线），
但插件框架本身保留，随时可装自写插件。因此本文件的定位是：

- 验证「框架可用」：加载、槽位聚合、事件总线、失败隔离、运行时启停、后台鉴权；
- **不依赖任何内置插件**：需要具体插件时，用 `tmp_plugin` fixture 在临时目录
  现场生成一个最小插件（通过改写 plugins 包的 __path__ 让它可被 import），
  测完自动恢复，不污染仓库。

运行：在仓库根目录 `python -m pytest tests/ -q`
"""
import os

import pytest

# 最小插件源码：覆盖 slots / footer / nav / html / remote_components 五类声明
PROBE_SRC = '''
def register(app, cfg):
    return {
        "name": "探测插件",
        "version": "0.1.0",
        "author": "tests",
        "description": "仅用于测试插件框架的最小插件",
        "slots": ["footer", "html"],
        "footer_provider": lambda: [{"title": "探测", "text": "ok"}],
        "nav_provider": lambda: [{"label": "探测", "url": "/probe"}],
        "html_provider": lambda: "<b>probe</b>",
        "remote_components": [
            {"name": "probe_widget", "url": "/static/plugins/probe/widget.js"},
            {"name": "bad_widget", "url": "https://evil.example.com/x.js"},
        ],
    }
'''


@pytest.fixture
def tmp_plugin(app, tmp_path, monkeypatch):
    """在临时目录造一个最小插件并加载，返回 slug。

    原理：`_load_one` 用 `importlib.import_module("plugins.<slug>")` 加载，
    只能从 plugins 包内导入。这里把包的 __path__ 临时指向 tmp 目录，
    就能在不污染仓库的前提下测试真实加载链路（monkeypatch 结束后自动恢复）。
    """
    import plugins as plugins_pkg
    from plugins import PLUGIN_REGISTRY, RUNTIME_DISABLED

    slug = "probe_demo"
    pkg = tmp_path / slug
    pkg.mkdir()
    (pkg / "__init__.py").write_text(PROBE_SRC, encoding="utf-8")

    app.config["PLUGINS_DIR"] = str(tmp_path)
    app.config["ENABLED_PLUGINS"] = slug
    app.config["DISABLED_PLUGINS"] = ""
    monkeypatch.setattr(plugins_pkg, "__path__",
                        [str(tmp_path)] + list(plugins_pkg.__path__))
    RUNTIME_DISABLED.clear()
    PLUGIN_REGISTRY.clear()

    # 用 reload 而非 load：它会先卸载 plugins_sys 蓝图再重新注册，
    # 避免在同一个 app 上重复 register_blueprint 报「名字已注册」。
    from plugins import reload_plugins
    reload_plugins(app, app.config)
    yield slug

    # 收尾：清干净全局状态，避免影响其它测试
    PLUGIN_REGISTRY.clear()
    RUNTIME_DISABLED.clear()


def test_app_boots_and_plugins_endpoint(client):
    """框架端点可用且结构完整（五个槽位键齐全）。"""
    r = client.get("/api/plugins")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("plugins", "footer", "nav", "sidebar", "html", "remote_components"):
        assert key in data, f"缺少槽位键：{key}"


def test_no_builtin_plugins_by_default():
    """v3.10.0：默认不内置任何插件（ENABLED_PLUGINS 为空）。"""
    import config as _cfg
    assert (_cfg.Config.ENABLED_PLUGINS or "").strip() == ""


def test_plugins_list_empty_when_nothing_enabled(client):
    """未启用插件时列表为空，且前端槽位数据也为空（不应报错）。"""
    data = client.get("/api/plugins").get_json()
    assert data["plugins"] == []
    assert data["footer"] == [] and data["nav"] == [] and data["html"] == []


def test_failure_isolation_bad_plugin(monkeypatch):
    """启用不存在的 slug：create_app 不崩溃，坏插件被隔离。"""
    import config as _cfg
    monkeypatch.setattr(_cfg.Config, "ENABLED_PLUGINS", "nonexistent_slug")
    monkeypatch.setattr(_cfg.Config, "DISABLED_PLUGINS", "")
    from app import create_app

    app = create_app()
    r = app.test_client().get("/api/plugins")
    assert r.status_code == 200
    assert r.get_json()["plugins"] == []


def test_disabled_plugin_skipped(monkeypatch, tmp_path):
    """DISABLED_PLUGINS 优先级高于 ENABLED_PLUGINS，命中的插件不加载。"""
    import config as _cfg
    import plugins as plugins_pkg
    slug = "probe_demo"
    pkg = tmp_path / slug
    pkg.mkdir()
    (pkg / "__init__.py").write_text(PROBE_SRC, encoding="utf-8")
    monkeypatch.setattr(plugins_pkg, "__path__",
                        [str(tmp_path)] + list(plugins_pkg.__path__))
    monkeypatch.setattr(_cfg.Config, "ENABLED_PLUGINS", slug)
    monkeypatch.setattr(_cfg.Config, "DISABLED_PLUGINS", slug)
    monkeypatch.setattr(_cfg.Config, "PLUGINS_DIR", str(tmp_path))

    from app import create_app
    app = create_app()
    assert app.test_client().get("/api/plugins").get_json()["plugins"] == []


def test_plugin_dir_missing_is_safe(app):
    """PLUGINS_DIR 不存在时应安全跳过，不影响启动。"""
    from plugins import load_plugins, PLUGIN_REGISTRY
    app.config["PLUGINS_DIR"] = "/definitely/not/a/real/path"
    PLUGIN_REGISTRY.clear()
    load_plugins(app, app.config)          # 不应抛异常
    assert PLUGIN_REGISTRY == {}


# ---------- M1：事件总线 ----------
def test_signal_bus_fires():
    """连接订阅者后调用 emit 助手，订阅者应被触发（验证总线 + 助手可用）。"""
    from plugins.signals import (post_published, comment_created,
                                 emit_post_published, emit_comment_created)

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


# ---------- M2/M3：槽位聚合与远程组件（用临时插件验证） ----------
def test_tmp_plugin_exposes_slots(client, tmp_plugin):
    r = client.get("/api/plugins")
    data = r.get_json()
    assert [p["id"] for p in data["plugins"]] == [tmp_plugin]
    assert data["plugins"][0]["slots"] == ["footer", "html"]

    # nav / html / footer 聚合生效
    assert "探测" in [n.get("label") for n in data["nav"]]
    assert tmp_plugin in [h.get("slug") for h in data["html"]]
    assert any(f.get("title") == "探测" for f in data["footer"])


def test_remote_components_must_be_same_origin(client, tmp_plugin):
    """远程组件只允许同源 /static/plugins/ 前缀，外链一律过滤（防任意脚本注入）。"""
    data = client.get("/api/plugins").get_json()
    remotes = data.get("remote_components", [])
    urls = [rc["url"] for rc in remotes]
    assert "/static/plugins/probe/widget.js" in urls
    assert "https://evil.example.com/x.js" not in urls
    assert all(u.startswith("/static/plugins/") for u in urls)


# ---------- M3：后台鉴权 + 运行时启停 ----------
def test_plugins_status_requires_admin(client):
    r = client.get("/api/plugins/status")
    assert r.status_code in (401, 403)


def test_runtime_enable_disable(app, tmp_plugin):
    """禁用 → 移出注册表 + 写 disabled 标记；启用 → 重新加载回注册表。"""
    import tempfile
    from plugins import (set_plugin_enabled, PLUGIN_REGISTRY, RUNTIME_DISABLED,
                         _marker_path)

    cfg = app.config
    slug = tmp_plugin
    mp = _marker_path(cfg, slug)
    try:
        res = set_plugin_enabled(app, cfg, slug, False)
        assert res["ok"] is True and res["enabled"] is False
        assert slug not in PLUGIN_REGISTRY
        assert slug in RUNTIME_DISABLED
        assert mp and os.path.exists(mp)

        res2 = set_plugin_enabled(app, cfg, slug, True)
        assert res2["ok"] is True and res2["enabled"] is True
        assert slug in PLUGIN_REGISTRY
        assert slug not in RUNTIME_DISABLED
        # 注：本沙箱对 os.remove 做 fail-closed 拦截，故不断言标记文件已物理删除。
    finally:
        RUNTIME_DISABLED.discard(slug)
        assert isinstance(tempfile.tempdir, str) or tempfile.tempdir is None


def test_reload_plugins(app, tmp_plugin):
    """整体重载不报错，临时插件仍在注册表。"""
    import tempfile
    from plugins import reload_plugins, PLUGIN_REGISTRY

    res = reload_plugins(app, app.config)
    assert res["ok"] is True
    assert tmp_plugin in PLUGIN_REGISTRY
    assert isinstance(tempfile.tempdir, str) or tempfile.tempdir is None
