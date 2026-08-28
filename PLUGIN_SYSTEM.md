# 插件系统设计方案（PLUGIN_SYSTEM）

> 状态：设计稿（v1，2026-08-28）· 目标版本：v3.9.0 起逐步落地
> 适用仓库：`llhhy-blog`（Flask 后端 `myblog/` + Vue3 前端 `vue-frontend/`）
> 关联纪律：发版仍走 8 步流程（审计→文档→版本→构建→打包→commit/tag→Release→记忆）；
> 插件代码随博客一起走 Release，**不做运行时热加载**。

---

## 1. 结论与原则

**可行性：✅ 完全可行。** Flask 是做插件化最友好的框架之一——`Blueprint` 动态注册 + `blinker` 信号原生支持，后端扩展几乎是零成本。前端是 Vue3 SPA（Nginx 直服），动态组件有安全与构建风险，因此前端采用「配置驱动槽位」而非「运行时远程组件」。

**三条红线（必须守住）：**

1. **一个坏插件绝不能拖垮整站。** 每个插件 `try/except` 包裹，加载失败只告警、不阻断博客启动；并提供紧急关停开关。
2. **装/卸 = 重新发版 + 重启 gunicorn。** 不做运行时热加载（对个人博客风险远大于收益）。插件随 `myblog-backend.zip` 一起分发。
3. **只装自己写/审计过的插件。** 第三方插件 = 任意代码执行。

**设计原则（ponytail 风格，最简单能跑）：**

- 架构支持全栈，但落地分两截：**后端骨架先立（M0），前端槽位后接（M2）**，第一版风险仍和纯后端一样低。
- 前端插件**不做运行时 SFC 热编译**；后端在 `manifest` 声明要占的槽位 + 内容，前端读配置渲染。
- 配置全部来自环境变量 / `manifest.json`，不硬编码。
- 每个插件至少带 1 条冒烟测试（当前仓库零自动化测试，这是插件系统能安全的底线）。

---

## 2. 目录结构与插件契约

每个插件 = `myblog/plugins/<slug>/` 一个包。`<slug>` 为插件唯一短标识（英文小写+下划线）。

```
myblog/plugins/
├── __init__.py          # 导出 load_plugins(app)，宿主在 create_app 内调用
├── events.py            # 事件总线（blinker Namespace，M1）
└── <slug>/              # 单个插件
    ├── __init__.py      # 导出 register(app, cfg) -> dict（插件清单）
    ├── manifest.json    # 元数据 + 前端槽位声明
    ├── models.py        # 可选：插件数据模型（从 models import db）
    ├── routes.py        # 可选：Flask Blueprint（API/页面）
    ├── tasks.py         # 可选：定时任务（挂到宿主调度线程）
    └── static/          # 可选：前端静态资源，由 /static/plugins/<slug>/ 提供
```

### `manifest.json` 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `slug` | ✅ | 与目录名一致，唯一 |
| `name` | ✅ | 展示名 |
| `version` | ✅ | 语义化版本 |
| `author` | | 作者 |
| `description` | | 简介 |
| `frontend` | | `bool`，是否含前端槽位 |
| `slots.nav` | | `[{ "to": "/plugin/<slug>", "title": {"zh":"", "en":""}, "icon": "" }]` 注入导航栏 |
| `slots.footer` | | `[{ "label": {"zh":"", "en":""}, "url": "" }]` 页脚链接（安全 `<a>`，非 v-html） |
| `slots.sidebar` | | M2 预留，右侧栏块（结构化数据，非原始 HTML） |
| `permissions` | | `["db", "network", "schedule"]` 声明插件用到的敏感能力，供审阅清单核对 |

### `register(app, cfg)` 约定

```python
# myblog/plugins/<slug>/__init__.py
from .routes import bp          # 插件 Blueprint（url_prefix=/api/plugin/<slug>）

def register(app, cfg):
    app.register_blueprint(bp)   # 注册路由（create_app 已在 app context 内调用）
    # 可选：db.create_all() 已在宿主 load_plugins 内统一调用，此处无需重复
    # 可选：订阅事件（M1）：from ..events import post_published; post_published.connect(_on_publish)
    return {
        "slug": "demo",
        "name": "示例插件",
        "frontend": True,
        "slots": {
            "nav": [{"to": "/plugin/demo", "title": {"zh": "示例", "en": "Demo"},
                     "icon": "🧩"}],
            "footer": [{"label": {"zh": "关于示例", "en": "About Demo"}, "url": "/plugin/demo"}],
        },
    }
```

---

## 3. 后端挂载机制（M0 核心）

### 3.1 配置项（`myblog/config.py` 的 `Config` 内新增）

```python
# ===== 插件系统 =====
# 启用的插件（逗号分隔 slug），留空 = 全部禁用。仅装自己审计过的插件。
ENABLED_PLUGINS = os.environ.get("ENABLED_PLUGINS", "")
# 强制停用的插件（逗号分隔），优先于 ENABLED_PLUGINS，用于线上紧急救火（不重发版）。
DISABLED_PLUGINS = os.environ.get("DISABLED_PLUGINS", "")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")
```

### 3.2 `load_plugins`（`myblog/plugins/__init__.py`）

```python
import importlib
import traceback
from flask import Blueprint

def load_plugins(app):
    """在 create_app 的 app context 内调用。返回已启用插件清单列表（供 /api/plugins）。"""
    enabled = {s.strip() for s in (app.config.get("ENABLED_PLUGINS") or "").split(",") if s.strip()}
    disabled = {s.strip() for s in (app.config.get("DISABLED_PLUGINS") or "").split(",") if s.strip()}
    manifests = []
    import os
    plugins_dir = app.config.get("PLUGINS_DIR")
    if not os.path.isdir(plugins_dir):
        return manifests
    for slug in sorted(os.listdir(plugins_dir)):
        if not enabled or slug not in enabled:
            continue
        if slug in disabled:
            print(f"[插件] 已跳过（DISABLED_PLUGINS）：{slug}")
            continue
        try:
            mod = importlib.import_module(f"plugins.{slug}")
            manifest = mod.register(app, app.config)
            manifests.append(manifest)
        except Exception as e:
            # 失败隔离：单插件崩溃不影响博客启动
            print(f"[插件] 加载失败（已跳过，不影响博客）：{slug}\n{traceback.format_exc()}")
    # 统一建表：仅创建缺失的表，幂等；插件 models 已在 import 时定义到共享 db
    try:
        from models import db
        db.create_all()
    except Exception as e:
        print(f"[插件] 插件建表跳过：{e}")
    app.config["_PLUGIN_MANIFESTS"] = manifests
    return manifests
```

### 3.3 接入 `create_app`（`myblog/app.py`）

在 `create_app()` 的 `with app.app_context():` 块内、`_ensure_settings(app)`（约 498 行）**之后**插入一行：

```python
        _ensure_settings(app)
        _ensure_super_admin(app)

        # ===== 插件系统（M0）=====
        from plugins import load_plugins
        load_plugins(app)        # 注册蓝图 + 建插件表 + 收集清单
```

> 说明：放在 `_ensure_super_admin` 之后，确保 `db` 已 init、各迁移已完成；`load_plugins` 内部再 `db.create_all()` 补齐插件表。蓝图注册在 app context 内同样安全。

### 3.4 暴露 `GET /api/plugins`

在 `api` 包新增 `myblog/api/plugins.py`，由 `api_bp` 挂载（参考 `myblog/api/__init__.py` 的注册顺序）。返回启用插件的槽位声明，供前端渲染：

```python
from .common import api_bp
from flask import jsonify, current_app

@api_bp.route("/plugins")
def list_plugins():
    manifests = current_app.config.get("_PLUGIN_MANIFESTS", [])
    return jsonify([
        {"slug": m["slug"], "name": m.get("name"),
         "slots": m.get("slots", {})}
        for m in manifests
    ])
```

---

## 4. 路由 / 静态 / 事件 约定（贴合现有安全机制）

| 关注点 | 现有机制 | 插件应遵循 |
|---|---|---|
| 反爬限流 | `bot_guard._SKIP_PREFIXES` = `(/static/, /robots.txt, /sitemap.xml, /feed.xml, /admin/, /api/)` | 插件 API 挂 `/api/plugin/<slug>/`、静态挂 `/static/plugins/<slug>/` → **自动豁免 bot_guard**，RSS/SEO 不受影响 |
| CSRF | `_csrf_protect` 对所有 `/api/` 变更请求校验（仅 webhook/captcha/stats 信标豁免） | 插件变更接口**自动受 CSRF 保护**；前端必须用 `apiPost`（见 `vue-frontend/src/lib/api.js`，已自动带 `X-CSRF-Token`） |
| 同源 | `enforce_same_origin` 校验 Origin | 插件接口同源部署，无需特殊处理 |
| 静态资源 | Flask 默认 `/static` 来自 `myblog/static` | 插件用 Blueprint `static_folder` + `static_url_path="/static/plugins/<slug>"` 隔离，互不污染 |

插件 Blueprint 推荐写法（路由与静态同前缀、互不冲突）：

```python
from flask import Blueprint
bp = Blueprint("plugin_demo", __name__,
               url_prefix="/api/plugin/demo",
               static_folder="static",
               static_url_path="/static/plugins/demo")
```

---

## 5. 前端槽位（M2）

前端采用「配置驱动槽位」：**不引入运行时远程组件**，只读取 `/api/plugins` 的声明并渲染安全结构。

### 5.1 数据获取（`vue-frontend/src/App.vue` 的 `onMounted` 内）

```js
import { apiGet } from "./lib/api.js";
const plugins = ref([]);
onMounted(async () => {
  await initSite();
  // ... 现有主题/公告/通知加载 ...
  try { plugins.value = await apiGet("/api/plugins"); } catch (e) {}
});
function pluginTitle(p) {
  const t = (p.title && (p.title[state.lang] || p.title.zh)) || p.slug;
  return t;
}
```

### 5.2 导航栏注入（两处：移动抽屉 + 桌面，见 `App.vue` 10–21 行与 42–52 行）

在两处 `<nav>` 的现有 `<router-link>` 列表**之后**追加：

```html
<router-link v-for="p in plugins" :key="p.slug"
             v-if="p.slots.nav" v-for="n in p.slots.nav"
             :to="n.to" @click="drawerOpen=false">{{ n.icon || '🧩' }} {{ pluginTitle(n) }}</router-link>
```

> 注：Vue3 单元素上不能并列两个 `v-for`；实际实现用嵌套 `<template v-for>` 包裹，文档只示意意图。
> 导航文案来自 `manifest` 的 `title.{zh,en}`，**不污染**全局 `I18N` 词典（保持 `tools/check_i18n.py` 校验有效）。

### 5.3 页脚链接注入（`App.vue` 110–115 行 `site-footer` 内）

```html
<p v-for="p in plugins" :key="'f'+p.slug">
  <template v-for="l in (p.slots.footer||[])" :key="l.url">
    <a :href="l.url" target="_blank" rel="noopener">{{ pluginTitle(l) }}</a>
  </template>
</p>
```

### 5.4 XSS 红线

- **MVP 只用结构化数据渲染**（`<router-link>` / `<a>` + 文案），**不用 `v-html`**。
- 确实需要富文本（如公告块）的插件，留到 **M3**，且渲染前**必须 DOMPurify 消毒**（`npm i dompurify`），即使是自己写的也防手滑。
- 现有 `lib/api.js` 的 `esc()` 可作后端文本的兜底转义。

---

## 6. 事件总线（M1）

Flask 已依赖 `blinker`，无需新增依赖。新增 `myblog/plugins/events.py`：

```python
from blinker import Namespace
_events = Namespace()
post_published = _events.signal("post-published")
comment_created = _events.signal("comment-created")

# 宿主在发布/评论流程 emit：
#   from plugins.events import post_published
#   post_published.send(current_app._get_current_object(), post=post)
```

插件订阅：

```python
from ..events import post_published
def _on_publish(app, post, **kw):
    # 例如：发布后清缓存 / 推送到外部服务
    pass
post_published.connect(_on_publish)
```

> 接入点：在 `myblog/routes.py`（发布文章）与 `myblog/api/posts.py`（评论创建）对应成功分支 `send`。保持「异常静默」——插件处理失败不影响主流程（与现有 `notify` / `mail_notify` 风格一致）。

---

## 7. 失败隔离与紧急关停（三档）

| 档位 | 方式 | 是否需重发版 | 适用场景 |
|---|---|---|---|
| ① 配置关 | `ENABLED_PLUGINS` 去掉该 slug | 是（改环境变量后重启） | 计划内停用 |
| ② 紧急关 | `DISABLED_PLUGINS=slug` 环境变量 | 否（改 env 后重启 gunicorn） | 线上出问题但服务还能起 |
| ③ 运行时关 | `GET /api/plugin/<slug>/disable`（仅 admin） | 否 | 临时熔断，下次重启恢复 |

> **启动期崩溃的恢复**：若插件在 `import`/`register` 阶段就让 `create_app()` 抛错（博客起不来），①②③都来不及生效。此时只能：SSH 上服务器 → 改名/移走 `myblog/plugins/<slug>/` 或设 `DISABLED_PLUGINS` 环境变量 → 宝塔 gunicorn **停止→启动**。因此插件代码必须经冒烟测试 + 发版前审计。

---

## 8. 打包与部署（几乎零改动）

- **后端**：`package.py` 以 `arc_root="myblog"` 递归打包，排除 `{data, __pycache__, .git, node_modules}`（`package.py:30`）。`myblog/plugins/` **自动被包含**，无需改 `package.py`。
- **前端**：MVP 用配置驱动槽位，`App.vue` 仅多读 `/api/plugins` 并渲染，**前端构建产物不变**，前端 zip 不受影响。
- **部署**：插件随 `myblog-backend.zip` 经 `update.sh` 解压 → 宝塔 gunicorn **停止→启动**生效（沿用现有「停止→启动才真正重载」规则）。
- **校验**：沿用 `sha256.txt` 双源互证，插件文件一并纳入哈希。

---

## 9. 安全红线（再次强调）

- 插件 = 在博客进程内执行任意 Python，**只装自己写/审计过的**，绝不装来路不明插件。
- `v-html` 一律 DOMPurify；页脚/导航只用结构化 `<a>`。
- 插件若需网络/定时任务，在 `manifest.permissions` 显式声明，发版前人工核对。
- 每个插件至少 1 条冒烟测试（参考仓库根 `smoke_*.py` 风格），纳入发版前验证。

---

## 10. 分阶段落地计划

| 阶段 | 内容 | 交付物 | 风险 |
|---|---|---|---|
| **M0** | 后端骨架：`plugins/__init__.py` + `load_plugins` + `config` 三项 + `create_app` 接入 + `GET /api/plugins` + 失败隔离 + 1 个 demo 插件（如「访客统计」：后端记数据 + 前端页脚渲染） | 可启用插件的后端、demo 插件、冒烟测试 | 低 |
| **M1** | 事件总线 `events.py`（`post_published` / `comment_created`）+ 在发布/评论流程 emit | 插件可订阅核心事件 | 低 |
| **M2** | 前端槽位：nav / footer 注入（config 驱动，无 v-html）+ `App.vue` 改造 | 前端展示插件入口 | 中（需前端构建回归） |
| **M3（可选）** | 后台插件管理页（列出已装/启停）+ DOMPurify 富文本槽位 + 远程预构建组件（`defineAsyncComponent`） | 可运营化、可富文本 | 高（仅必要时做） |

**建议首版范围**：M0 + M1（纯后端，零前端构建风险），M2 视需求再上。

---

## 11. 验收 / 冒烟（M0 示例）

```bash
# 1) 启用 demo 插件后启动，确认不崩溃且 /api/plugins 返回清单
ENABLED_PLUGINS=demo python -c "from myblog.app import create_app; app=create_app(); \
  c=app.test_client(); print(c.get('/api/plugins').get_json())"

# 2) 制造一个会抛错的插件，确认启动仍成功（失败隔离）
# 3) 设 DISABLED_PLUGINS=demo，确认 /api/plugins 不含该插件
```

---

## 12. 开放决策点（待你拍板）

1. **首个真实插件做什么？** 候选：访客统计增强、友链 RSS 聚合面板、文章目录(TOC)侧栏、第三方评论接入。决定后我按 M0 直接脚手架。
2. **M2 是否随 M0 一起做？** 建议分开（降风险），除非你马上要在前台看到插件入口。
3. **插件数据持久化方式**：共用主库 SQLite 表（简单，随备份走）vs 插件独立文件（隔离，但备份需单独处理）。默认共用主库。
