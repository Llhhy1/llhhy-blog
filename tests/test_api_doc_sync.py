"""v5.2.5：接口文档与真实路由必须一致（防文档再次滞后）。

背景：`myblog/API.md` 曾经停在 v3.6.0（那时只有约 60 条 `/api/*`），
而代码里已经长到 166 条 —— **没人发现，因为文档不会自己报错**。
本文件把「文档条目 == 真实路由」钉成可执行断言：

  1. 真实路由必须**全部**出现在文档里（防漏写）；
  2. 文档里**不得**出现已不存在的路由（防留残骸误导调用方）；
  3. 文档目录里的每个锚点都必须指向真实存在的章节（防死链）；
  4. 后台 `/admin/*` 的 JSON 接口同样受管（它们被后台页面 fetch 调用）。

判定方式与 `package.py` 打包前的三链校验同源：**以 Flask `url_map` 为真相**，
不靠人工数条目。
"""
import io
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
API_MD = os.path.join(_ROOT, "myblog", "API.md")

# 文档条目的写法：`### `GET /api/xxx` — 标题`
_ENTRY_RE = re.compile(r"^### `([A-Z]+(?:,\s*[A-Z]+)*)\s+(/[^`]+)`", re.M)
# 后台 JSON 接口（被后台页面 fetch 调用）——不在 `/api/*` 里，但同样是「可用接口」
_ADMIN_JSON_FUNCS = {
    "album_media_picker", "slug_preview", "media_to_album", "autosave_post",
    "upload", "upload_chunk_init", "upload_chunk_part", "upload_chunk_complete",
    "upload_chunk_abort", "seo_status", "seo_preview", "seo_selfcheck",
    "task_status", "mcp_services_toggle", "mcp_services_update",
    "mcp_services_delete", "mcp_instruction",
}


def _read_doc():
    with io.open(API_MD, encoding="utf-8") as f:
        return f.read()


def _doc_entries(doc):
    """文档里声明的 (方法, 路径) 集合。"""
    out = set()
    for m in _ENTRY_RE.finditer(doc):
        for meth in [x.strip() for x in m.group(1).split(",")]:
            out.add((meth, m.group(2)))
    return out


def _plugin_entries():
    """插件蓝图（`myblog/plugins/__init__.py`）的 4 条路由。

    注意：这些路由**只在插件目录存在时才会注册** ——
    `load_plugins()` 在 `PLUGINS_DIR` 不存在时直接 return，`plugins_bp` 从未挂上。
    测试环境通常没有插件目录，所以不能只靠 `app.url_map` 枚举它们
    （那会让「文档写了接口、代码里找不到」变成常态性假失败）。
    这里用一个**独立的探针 app**注册同一个蓝图，取它自己的 url_map ——
    与运行环境无关，拿到的永远是真实的 4 条。
    """
    from flask import Flask
    from plugins import plugins_bp
    probe = Flask(__name__)
    probe.register_blueprint(plugins_bp)
    out = set()
    for rule in probe.url_map.iter_rules():
        path = str(rule.rule)
        if not path.startswith("/api/"):
            continue          # 探针 app 自带的 /static/<path:filename> 不算接口
        for meth in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            out.add((meth, path))
    return out


def _real_entries(app):
    """代码里真实存在的 (方法, 路径) 集合：/api/* 全部 + /admin/* 的 JSON 接口。"""
    api = set()
    admin = set()
    for rule in app.url_map.iter_rules():
        path = str(rule.rule)
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        view = app.view_functions.get(rule.endpoint)
        func = getattr(view, "__name__", "") if view else ""
        if path.startswith("/api/"):
            for meth in methods:
                api.add((meth, path))
        elif path.startswith("/admin/") and func in _ADMIN_JSON_FUNCS:
            for meth in methods:
                admin.add((meth, path))
    # 插件蓝图按上面的说明单独取（可能没注册到 app 上）
    api |= _plugin_entries()
    return api, admin


def test_文档文件存在():
    assert os.path.exists(API_MD), "myblog/API.md 不存在"


def test_所有真实接口都在文档里(app):
    """漏写是这次要治的病 —— 新增接口忘了写文档，调用方按文档做集成就会踩空。"""
    doc = _read_doc()
    doc_entries = _doc_entries(doc)
    api, admin = _real_entries(app)

    missing_api = sorted(api - doc_entries)
    assert not missing_api, (
        "以下真实路由未写进 myblog/API.md（新增接口忘了同步文档）：\n  "
        + "\n  ".join("%s %s" % x for x in missing_api)
    )

    missing_admin = sorted(admin - doc_entries)
    assert not missing_admin, (
        "以下后台 JSON 接口未写进 myblog/API.md：\n  "
        + "\n  ".join("%s %s" % x for x in missing_admin)
    )


def test_文档里没有已废弃的接口(app):
    """反向：文档里留着已删除的接口，调用方会照着调一个 404。"""
    doc = _read_doc()
    doc_entries = _doc_entries(doc)
    api, admin = _real_entries(app)
    real = api | admin

    stale = sorted(doc_entries - real)
    assert not stale, (
        "myblog/API.md 里写着已不存在的接口（删接口忘了删文档）：\n  "
        + "\n  ".join("%s %s" % x for x in stale)
    )


def test_文档目录锚点全部有效():
    """目录里指向不存在的章节 → 点进去是空白，读者以为文档没写完。"""
    doc = _read_doc()
    heads = re.findall(r"^## (.+)$", doc, re.M)
    slugs = set()
    for h in heads:
        s = h.strip().lower()
        s = re.sub(r"[^\w一-鿿\- ]", "", s)
        slugs.add(s.replace(" ", "-"))

    toc = re.findall(r"^- \[([^\]]+)\]\(#([^)]+)\)", doc, re.M)
    assert toc, "文档目录是空的"
    bad = [(t, a) for t, a in toc if a not in slugs]
    assert not bad, (
        "文档目录里有失效锚点（点进去是空白）：\n  "
        + "\n  ".join("%s -> #%s" % x for x in bad)
    )


def test_文档版本号与代码一致():
    """文档头写的版本要跟 APP_VERSION 对得上，否则读者不知道文档描述的是哪一版。"""
    import config
    doc = _read_doc()
    assert ("v" + config.APP_VERSION) in doc, (
        "API.md 头部没有当前版本号 v%s" % config.APP_VERSION)
