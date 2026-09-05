"""插件系统核心（v3.9.0 · M0/M1/M2/M3）。

设计原则（详见仓库 PLUGIN_SYSTEM.md）：
- 动态加载：扫描 ENABLED_PLUGINS，importlib 加载 myblog/plugins/<slug>/__init__.py 的
  register(app, cfg)，返回 manifest dict（含 name/version/slots/footer_provider/
  nav_provider/sidebar_provider/html_provider/remote_components 等）。
- 失败隔离：单个插件 import / register 抛异常只告警、不阻断博客启动。
- 紧急关停：DISABLED_PLUGINS 优先级高于 ENABLED_PLUGINS（重启生效）；
  插件目录放 disabled 标记文件也跳过（免改配置）。
- 运行时启停（M3）：set_plugin_enabled() 写/删 disabled 标记文件 + 维护内存覆盖
  RUNTIME_DISABLED，前端槽位立即生效；路由级启停需重启 gunicorn（架构红线：不热加载）。
- 不热加载：插件随代码发版，装卸 = 重新发版 + 重启 gunicorn。
- /api/plugins：返回已启用插件的槽位声明 + footer/nav/sidebar/html 渲染数据，供前端渲染。
- 事件总线（M1）：插件可在 register() 内订阅 plugins.signals 的信号。
"""
import os
import importlib
import traceback

from flask import Blueprint, jsonify, request, session

# 插件运行时注册表：slug -> manifest dict（含 slots、各 provider 等）。
# 单进程内有效；多 worker 各自加载，互不影响。
PLUGIN_REGISTRY = {}

# 运行时禁用覆盖（内存）：优先级同 disabled 标记文件，用于「即时影响前端槽位」，
# 无需重启。持久化靠 disabled 标记文件（重启后仍生效）。
RUNTIME_DISABLED = set()

# 记录每个插件注册的蓝图名（slug -> {bp_name}），用于运行时卸载/重载避免重复注册。
SLUG_BLUEPRINTS = {}

# 系统蓝图名（每次 load 都重新注册，重载时需先卸载）。
SYS_BP_NAME = "plugins_sys"

plugins_bp = Blueprint(SYS_BP_NAME, __name__, url_prefix="/api/plugins")


def _parse_list(raw):
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def _plugin_dir(cfg, slug):
    plugins_dir = cfg.get("PLUGINS_DIR", "")
    return os.path.join(plugins_dir, slug) if plugins_dir else ""


def _marker_path(cfg, slug):
    d = _plugin_dir(cfg, slug)
    return os.path.join(d, "disabled") if d else ""


def _should_load(slug, cfg):
    """根据启用/禁用清单 + 标记文件 + 运行时覆盖判断是否加载该插件。"""
    enabled = set(_parse_list(cfg.get("ENABLED_PLUGINS", "")))
    disabled = set(_parse_list(cfg.get("DISABLED_PLUGINS", "")))
    if slug in disabled:
        return False
    if slug in RUNTIME_DISABLED:
        return False
    # disabled 标记文件：plugins/<slug>/disabled 存在则跳过（紧急关停，免改配置）。
    mp = _marker_path(cfg, slug)
    if mp and os.path.exists(mp):
        return False
    return slug in enabled


def _unregister_blueprints(app, slug=None):
    """卸载插件（或全部）注册的蓝图，避免重载时重复注册报错。"""
    names = []
    if slug is None:
        for s, bs in list(SLUG_BLUEPRINTS.items()):
            if s == "__sys__":
                continue  # v3.13.1：系统蓝图常驻，整体重载不卸载（否则运行时无法安全补回）
            names.extend(bs)
        # v3.13.1：整体重载不再卸载系统蓝图（plugins_bp 常驻，承载 /api/plugins 自身）。
        # 运行时（应用已处理请求）Flask 禁止重新 register_blueprint，卸掉后无法安全补回，
        # 会导致插件 API 在重启前 404。系统蓝图本就无路由级热更需求，留着即可。
    elif slug in SLUG_BLUEPRINTS:
        names.extend(SLUG_BLUEPRINTS[slug])
    for name in set(names):
        try:
            app.blueprints.pop(name, None)
            # 重建 URL 规则表，剔除该蓝图前缀的规则（Werkzeug 无公开 _remap，手动过滤；
            # _rules 是只读 property，用原地切片赋值避免触发 setter）。
            keep = []
            for r in list(app.url_map._rules):
                if r.endpoint.startswith(name + "."):
                    app.url_map._rules_by_endpoint.pop(r.endpoint, None)
                else:
                    keep.append(r)
            app.url_map._rules[:] = keep
        except Exception as e:
            print(f"[插件] 卸载蓝图失败（忽略）：{name} -> {e}")
    if slug is None:
        SLUG_BLUEPRINTS.clear()
    else:
        SLUG_BLUEPRINTS.pop(slug, None)


def _load_one(app, cfg, slug):
    """加载单个插件；任何异常都被捕获，返回 manifest 或 None（失败隔离）。"""
    try:
        module = importlib.import_module(f"plugins.{slug}")
        register = getattr(module, "register", None)
        if register is None:
            print(f"[插件] {slug} 缺少 register(app, cfg)，已跳过")
            return None
        before = set(app.blueprints.keys())
        manifest = register(app, cfg) or {}
        after = set(app.blueprints.keys())
        for name in (after - before):
            SLUG_BLUEPRINTS.setdefault(slug, set()).add(name)
        manifest["id"] = slug
        PLUGIN_REGISTRY[slug] = manifest
        try:
            from plugins.signals import emit_plugin_loaded
            emit_plugin_loaded(slug, manifest)
        except Exception:
            pass
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
            print(f"[插件] 已跳过（禁用清单/标记文件/运行时禁用）：{slug}")
    # v3.13.1：幂等 + 崩溃安全注册。create_app 启动时已注册过一次；
    # 后台「插件重载」按钮（reload_plugins → load_plugins）会在运行时再次走到这里，
    # 若应用已处理过请求，Flask 禁止 register_blueprint（抛 AssertionError → 该接口直接 500）。
    # 故仅在缺失时补注册；即便缺失且处于运行时，也吞掉断言跳过（路由级变更本就需重启 gunicorn，
    # 符合「不热加载」架构红线），避免一次重载把整个接口打挂。
    if SYS_BP_NAME not in app.blueprints:
        try:
            app.register_blueprint(plugins_bp)
        except AssertionError:
            app.logger.warning(
                "跳过 plugins 系统蓝图运行时注册（应用已处理请求，路由级变更需重启 gunicorn 生效）"
            )
    SLUG_BLUEPRINTS.setdefault("__sys__", set()).add(SYS_BP_NAME)
    print(f"[插件] 加载完成，共 {loaded} 个启用")


def set_plugin_enabled(app, cfg, slug, enabled):
    """运行时启停（M3）。写/删 disabled 标记文件 + 维护 RUNTIME_DISABLED。

    返回 {"ok": True, "slug": slug, "enabled": bool}。
    说明：前端槽位（nav/sidebar/footer/html）立即生效；路由级启停需重启 gunicorn。
    """
    mp = _marker_path(cfg, slug)
    if not mp:
        return {"ok": False, "error": "插件目录未配置"}
    if not enabled:
        # 禁用：写标记 + 内存覆盖 + 移出注册表 + 卸载蓝图（即时去掉前端槽位与路由）
        try:
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            open(mp, "w").close()
        except Exception as e:
            return {"ok": False, "error": f"写禁用标记失败：{e}"}
        RUNTIME_DISABLED.add(slug)
        PLUGIN_REGISTRY.pop(slug, None)
        try:
            _unregister_blueprints(app, slug)
        except Exception:
            pass
        return {"ok": True, "slug": slug, "enabled": False}
    # 启用：删标记 + 清内存覆盖 + 重新加载该插件
    try:
        if os.path.exists(mp):
            os.remove(mp)
    except Exception:
        pass
    RUNTIME_DISABLED.discard(slug)
    try:
        _unregister_blueprints(app, slug)
    except Exception:
        pass
    PLUGIN_REGISTRY.pop(slug, None)
    _load_one(app, cfg, slug)
    return {"ok": True, "slug": slug, "enabled": slug in PLUGIN_REGISTRY}


def reload_plugins(app, cfg):
    """整体重载（M3「立即重载」按钮）。卸载全部插件蓝图后重新扫描加载。"""
    try:
        _unregister_blueprints(app, None)
    except Exception as e:
        print(f"[插件] 卸载全部蓝图失败（忽略）：{e}")
    load_plugins(app, cfg)
    return {"ok": True, "loaded": len(PLUGIN_REGISTRY)}


def _require_admin():
    """仅管理员/超管可写。未登录 401，权限不足 403。"""
    from models import User
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    u = User.query.get(uid) if hasattr(User, "query") else None
    # 上面 query 在 app_context 外不可用，改为 db 会话取
    try:
        from models import db
        u = db.session.get(User, uid)
    except Exception:
        u = None
    if not u or not (getattr(u, "is_super", False) or getattr(u, "is_admin_role", False)):
        return jsonify({"error": "需要管理员权限"}), 403
    return None


def _collect_providers():
    """聚合所有启用插件的 nav/sidebar/html/footer 渲染数据。"""
    footer_items, nav_items, sidebar_items, html_items, remote = [], [], [], [], []
    for slug, m in PLUGIN_REGISTRY.items():
        slots = m.get("slots", []) or []
        # footer
        if "footer" in slots and m.get("footer_provider"):
            try:
                footer_items.extend(m["footer_provider"]() or [])
            except Exception as e:
                print(f"[插件] footer_provider 失败：{slug} -> {e}")
        # nav
        if m.get("nav_provider"):
            try:
                nav_items.extend(m["nav_provider"]() or [])
            except Exception as e:
                print(f"[插件] nav_provider 失败：{slug} -> {e}")
        # sidebar
        if m.get("sidebar_provider"):
            try:
                sidebar_items.extend(m["sidebar_provider"]() or [])
            except Exception as e:
                print(f"[插件] sidebar_provider 失败：{slug} -> {e}")
        # html（富文本，前端须 DOMPurify 消毒后 v-html）
        if "html" in slots and m.get("html_provider"):
            try:
                html_items.append({"slug": slug, "html": m["html_provider"]() or ""})
            except Exception as e:
                print(f"[插件] html_provider 失败：{slug} -> {e}")
        # remote_components（预构建 JS，仅允许同源 /static/plugins/ 前缀）
        for rc in (m.get("remote_components") or []):
            url = rc.get("url", "")
            if url.startswith("/static/plugins/"):
                remote.append({"name": rc.get("name", slug), "url": url})
    return footer_items, nav_items, sidebar_items, html_items, remote


@plugins_bp.get("/", strict_slashes=False)
def list_plugins():
    """公开：返回已启用插件的槽位声明 + footer/nav/sidebar/html/remote 渲染数据。"""
    footer_items, nav_items, sidebar_items, html_items, remote = _collect_providers()
    out = []
    for slug, m in PLUGIN_REGISTRY.items():
        out.append({
            "id": slug,
            "name": m.get("name", slug),
            "version": m.get("version", ""),
            "author": m.get("author", ""),
            "description": m.get("description", ""),
            "slots": m.get("slots", []) or [],
        })
    return jsonify({
        "plugins": out,
        "footer": footer_items,
        "nav": nav_items,
        "sidebar": sidebar_items,
        "html": html_items,
        "remote_components": remote,
    })


@plugins_bp.get("/status")
def plugins_status():
    """管理员：返回全部已配置插件（含被禁用）的状态，供后台管理页使用。"""
    r = _require_admin()
    if r:
        return r
    cfg = {}
    try:
        from app import app as _app
        cfg = _app.config
    except Exception:
        cfg = {}
    enabled = _parse_list(cfg.get("ENABLED_PLUGINS", "")) if cfg else []
    out = []
    for slug in enabled:
        m = PLUGIN_REGISTRY.get(slug, {})
        mp = _marker_path(cfg, slug)
        disabled = (slug in RUNTIME_DISABLED) or (mp and os.path.exists(mp))
        out.append({
            "slug": slug,
            "name": m.get("name", slug),
            "version": m.get("version", ""),
            "author": m.get("author", ""),
            "description": m.get("description", ""),
            "slots": m.get("slots", []) or [],
            "loaded": slug in PLUGIN_REGISTRY,
            "disabled": bool(disabled),
        })
    return jsonify({"plugins": out})


@plugins_bp.post("/<slug>/set-enabled")
def set_enabled(slug):
    """管理员：运行时启停插件（写/删 disabled 标记文件 + 内存覆盖）。"""
    r = _require_admin()
    if r:
        return r
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    from app import app as _app
    res = set_plugin_enabled(_app, _app.config, slug, enabled)
    return jsonify(res)


@plugins_bp.post("/reload")
def reload():
    """管理员：整体重载插件（卸载全部蓝图后重新扫描加载）。"""
    r = _require_admin()
    if r:
        return r
    from app import app as _app
    return jsonify(reload_plugins(_app, _app.config))
