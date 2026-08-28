"""插件系统核心（v3.9.0 · M0）。

设计原则（详见仓库 PLUGIN_SYSTEM.md）：
- 动态加载：扫描 ENABLED_PLUGINS，importlib 加载 myblog/plugins/<slug>/__init__.py 的
  register(app, cfg)，返回 manifest dict（含 name/version/slots/footer_provider 等）。
- 失败隔离：单个插件 import / register 抛异常只告警、不阻断博客启动。
- 紧急关停：DISABLED_PLUGINS 优先级高于 ENABLED_PLUGINS（重启生效）；
  插件目录放 disabled 标记文件也跳过（免改配置）。
- 不热加载：插件随代码发版，装卸 = 重新发版 + 重启 gunicorn。
- /api/plugins：返回已启用插件的槽位声明 + footer 渲染数据，供前端渲染（结构化 <a>，不用 v-html）。
"""
import os
import importlib
import traceback

from flask import Blueprint, jsonify

# 插件运行时注册表：slug -> manifest dict（含 slots、footer_provider 等）。
# 单进程内有效；多 worker 各自加载，互不影响。
PLUGIN_REGISTRY = {}

plugins_bp = Blueprint("plugins_sys", __name__, url_prefix="/api/plugins")


def _parse_list(raw):
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def _should_load(slug, cfg):
    """根据启用/禁用清单 + 标记文件判断是否加载该插件。"""
    enabled = set(_parse_list(cfg.get("ENABLED_PLUGINS", "")))
    disabled = set(_parse_list(cfg.get("DISABLED_PLUGINS", "")))
    if slug in disabled:
        return False
    # disabled 标记文件：plugins/<slug>/disabled 存在则跳过（紧急关停，免改配置）。
    plugins_dir = cfg.get("PLUGINS_DIR", "")
    if plugins_dir and os.path.exists(os.path.join(plugins_dir, slug, "disabled")):
        return False
    return slug in enabled


def _load_one(app, cfg, slug):
    """加载单个插件；任何异常都被捕获，返回 manifest 或 None（失败隔离）。"""
    try:
        module = importlib.import_module(f"plugins.{slug}")
        register = getattr(module, "register", None)
        if register is None:
            print(f"[插件] {slug} 缺少 register(app, cfg)，已跳过")
            return None
        manifest = register(app, cfg) or {}
        manifest["id"] = slug
        PLUGIN_REGISTRY[slug] = manifest
        print(f"[插件] 已加载：{slug} v{manifest.get('version', '?')}")
        return manifest
    except Exception as e:
        print(f"[插件] 加载失败（已隔离，不影响博客）：{slug} -> {e}")
        traceback.print_exc()
        return None


def load_plugins(app, cfg):
    """在 create_app 的 app_context 内调用：扫描并加载全部启用插件。"""
    PLUGIN_REGISTRY.clear()
    plugins_dir = cfg.get("PLUGINS_DIR", "")
    if plugins_dir and not os.path.isdir(plugins_dir):
        print(f"[插件] 插件目录不存在：{plugins_dir}，跳过")
        return
    enabled = _parse_list(cfg.get("ENABLED_PLUGINS", ""))
    loaded = 0
    for slug in enabled:
        if _should_load(slug, cfg):
            if _load_one(app, cfg, slug):
                loaded += 1
        else:
            print(f"[插件] 已跳过（禁用清单/标记文件）：{slug}")
    app.register_blueprint(plugins_bp)
    print(f"[插件] 加载完成，共 {loaded} 个启用")


@plugins_bp.get("/", strict_slashes=False)
def list_plugins():
    """返回已启用插件的槽位声明 + footer 渲染数据（公开）。"""
    out = []
    footer_items = []
    for slug, m in PLUGIN_REGISTRY.items():
        slots = m.get("slots", []) or []
        out.append({
            "id": slug,
            "name": m.get("name", slug),
            "version": m.get("version", ""),
            "author": m.get("author", ""),
            "slots": slots,
        })
        provider = m.get("footer_provider")
        if provider and "footer" in slots:
            try:
                footer_items.extend(provider() or [])
            except Exception as e:
                print(f"[插件] footer_provider 失败：{slug} -> {e}")
    return jsonify({"plugins": out, "footer": footer_items})
