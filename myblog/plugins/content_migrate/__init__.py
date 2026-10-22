"""WordPress / Typecho → llhhy-blog 内容迁移插件。

启用方式（重启生效）：

    ENABLED_PLUGINS=content_migrate

然后进后台「插件管理 → 内容迁移 → 打开」，或直接访问 `/admin/migrate/`。
"""
from .routes import bp


def register(app, cfg):  # noqa: ARG001 —— 插件契约固定签名，本插件不需要 cfg
    app.register_blueprint(bp)
    return {
        "slug": "content_migrate",
        "name": "内容迁移",
        "version": "1.0.0",
        "author": "llhhy-blog",
        "description": "从 WordPress(WXR) / Typecho(SQL 备份 / SQLite 库) 导入文章、分类与标签，可选下载图片",
        "permissions": ["db", "network"],
        "admin_url": "/admin/migrate/",
        "slots": [],
    }
