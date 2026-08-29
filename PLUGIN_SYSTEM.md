# 插件系统设计方案（PLUGIN_SYSTEM）

> 状态：设计稿（v1，2026-08-28）· 目标版本：v3.9.0 起逐步落地
> **v3.10.0 变更（2026-08-29）**：内置插件 `contact_card`、`article_toc` 已**全部移除**，仅保留插件框架（加载器 / 事件总线 / 后台管理页 / 前端槽位）。`ENABLED_PLUGINS` 默认值改为空。详见第 16 节。
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
| **M0** | 后端骨架：`plugins/__init__.py` + `load_plugins` + `config` 三项 + `create_app` 接入 + `GET /api/plugins` + 失败隔离 + 1 个 demo 插件 `contact_card`（联系卡片：独立模型 + 前端页脚渲染） | 可启用插件的后端、demo 插件、冒烟测试 | 低 ✅ 已落地 |
| **M1** | 事件总线 `signals.py`（`post_published` / `post_deleted` / `comment_created` / `comment_approved` / `plugin_loaded`）+ 在发布/评论流程 emit | 插件可订阅核心事件 | 低 ✅ 已落地 |
| **M2** | 前端槽位：nav / sidebar / footer 注入（config 驱动，无 v-html）+ `App.vue` 改造 | 前端展示插件入口 | 中 ✅ 已落地（已 vite 构建验证） |
| **M3（可选）** | 后台插件管理页（列出已装/启停）+ DOMPurify 富文本槽位 + 远程预构建组件（`/static/plugins/<slug>/*.js` 预构建，运行时 `defineAsyncComponent`） | 可运营化、可富文本 | 高 ✅ 已落地（按安全约束收窄实现） |

**建议首版范围**：M0 + M1 + M2 + M3 全部落地（本会话一次性完成），均随下次发版（目标 v3.9.0）走 8 步流程。

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

1. **首个真实插件做什么？** ✅ 曾选定并落地 `article_toc`（文章目录侧栏），详见第 15 节。
   ⚠️ **v3.10.0 起该插件已随 `contact_card` 一并移除**（内置插件全部下线，框架保留）。
   其余候选（访客统计增强、友链 RSS 聚合面板、第三方评论接入）仍可按同一骨架继续加——新建目录 + 填 `ENABLED_PLUGINS` 即可，无需改核心代码。
2. **M2 是否随 M0 一起做？** ✅ 已随 M0 一起做（见第 14 节）。
3. **插件数据持久化方式**：共用主库 SQLite 表（简单，随备份走）vs 插件独立文件（隔离，但备份需单独处理）。默认共用主库（`article_toc` 无持久化需求，纯前端插件）。

---

## 13. M0 实施进展（已落地 · 2026-08-28）

M0 已在 `main` 落地（未单独打 Release，随下次版本带）：

- **插件系统核心** `myblog/plugins/__init__.py`
  - `load_plugins(app, cfg)` 在 `create_app()` 的 `with app.app_context():` 末尾
    （`_ensure_super_admin` 之后）调用，扫描 `ENABLED_PLUGINS` → importlib 动态加载
    `myblog/plugins/<slug>/__init__.py` 的 `register(app, cfg)`，返回 manifest dict。
  - **失败隔离**：单插件 import/register 抛异常只 `print` 告警、不阻断博客启动。
  - **紧急关停**：`DISABLED_PLUGINS` 优先级高于 `ENABLED_PLUGINS`（重启生效）；
    插件目录放置 `disabled` 标记文件也跳过（免改配置）。
  - `GET /api/plugins`（`strict_slashes` 兼容有无尾斜杠）：返回已启用插件的 `slots` 声明
    + `footer` 渲染数据，供前端**结构化**渲染（不用 `v-html`，防 XSS）。
- **配置** `config.Config` 新增 `ENABLED_PLUGINS`（默认 `contact_card`）/
  `DISABLED_PLUGINS`/`PLUGINS_DIR`。
- **demo 插件** `myblog/plugins/contact_card/`（联系卡片）
  - 自带独立模型 `PluginContactCard`（表 `plugin_contact_card`，与核心零耦合）；
    选 contact_card 而非原设想「友链」，是因为 `FriendLink` 已是核心模型，避免插件与核心重复。
  - 独立 Blueprint：`GET /api/plugin/contact_card/list`（公开）、
    `POST /upsert`、`POST /delete`（管理员鉴权，复用前端 `apiPost` 自带 CSRF）。
  - `manifest.json` 声明 `slots: ["footer"]`。
- **前端** `App.vue` 页脚新增插件槽位，启动拉 `GET /api/plugins` 后结构化渲染
  `<a>` 联系卡片（`.plugin-footer-card`）。
- **测试** `tests/`（pytest，5 passed）：覆盖启动、`/api/plugins`、公开 list、admin 鉴权、
  坏插件隔离、禁用清单跳过。
- **打包** `package.py` 递归 `os.walk(myblog/)`，插件目录随 `myblog-backend.zip` 自动带出，无需改脚本。

**下一步**：M1/M2/M3 已全部落地（见第 14 节）。后续可做：把插件系统纳入 GitHub Actions 门禁（P1）、接真实第二个业务插件、把 `disabled` 标记加入 `.gitignore` 防止误提交。

---

## 14. M1 / M2 / M3 实施进展（已落地 · 2026-08-28）

### M1 · 事件总线（blinker）
- 新增 `myblog/plugins/signals.py`：blinker `Namespace` 定义 5 个信号，并提供 `emit_*` 助手
  （订阅者异常被吞掉并打印告警，不拖垮主流程）。
- 发射点（懒导入，避免循环依赖）：
  - `api/posts.py` 评论写入、`api/posts.py` 立即发布、`admin.py` 后台一键发布、
    `app.py` 定时发布守护线程、`routes.py` 旧 SSR 评论写入。
- 插件订阅示例（在 `register(app, cfg)` 内）：
  ```python
  from plugins.signals import post_published
  def _on_published(post):
      print("新文章：", post.title)
  post_published.connect(_on_published)
  ```

### M2 · 前端槽位（nav / sidebar / footer）
- `GET /api/plugins` 聚合返回 `nav` / `sidebar` / `footer` / `html` / `remote_components`。
- 前端 `App.vue`：
  - 抽屉导航 + 桌面导航均注入插件 `nav` 入口（结构化 `<a>`，不用 v-html）；
  - `site-frame-body` 包裹主内容 + `plugin-sidebar` 侧栏（窄屏自动堆叠，docs 页隐藏侧栏）；
  - 页脚新增 `html` 富文本区（经 DOMPurify 消毒后渲染）+ `plugin-remote` 远程组件区。
- `contact_card` demo 提供 `nav_provider`（「联系」入口）→ 指向插件自有页面 `/plugin/contact_card`。

### M3 · 后台管理页 + DOMPurify + 远程组件
- **后台管理页**（`admin.py` `/admin/plugins` + `templates/admin/plugins.html` + `base.html` 导航项）：
  列出已配置插件（含运行状态），支持「启用/停用」（写/删 `disabled` 标记文件 + 内存覆盖
  `RUNTIME_DISABLED`，前端槽位即时生效；路由级启停需重启 gunicorn）+ 「立即重载」。
- **DOMPurify 富文本**：`lib/sanitize.js` 封装 DOMPurify（禁用 script/iframe/on*），插件 `html`
  槽位一律消毒后 `v-html`；`package.json` 新增 `dompurify` 依赖。
- **远程预构建组件**：`manifest.remote_components` 声明 `{name, url}`（仅允许同源
  `/static/plugins/<slug>/` 前缀）；前端注入 `<script>` 后由 `window.__pluginRegister` 注册组件，
  经 `<component :is>` 渲染。`contact_card` 提供 `static/plugins/contact_card/widget.js`
  示例（用 `h()` 渲染函数，不依赖运行时模板编译器）。
- **运行时启停 API**：`POST /api/plugins/<slug>/set-enabled`、`POST /api/plugins/reload`
  （均管理员鉴权）；`set_plugin_enabled` 含幂等蓝图卸载/重注册（避免重载重复注册报错）。

### 测试
- `tests/test_plugin_system.py`（pytest，10 passed）：在 M0 原有基础上新增
  M1 信号总线、M2 nav/html 槽位、M3 管理接口鉴权 + 运行时启停 + 整体重载。
  M3 测试用临时 `PLUGINS_DIR`，不污染真实仓库；`disabled` 标记已加入 `.gitignore` 候选。

### 安全红线（重申）
- 单插件崩溃不拖垮整站（失败隔离 + 信号订阅者异常吞掉）。
- 装卸 = 发版 + 重启 gunicorn（不热加载）；运行时开关仅即时影响前端槽位。
- 只装自写/审计过的插件；`html` 槽位强制 DOMPurify；远程组件仅限同源 `/static/plugins/`。

---

## 15. 首个真实插件：`article_toc`（文章目录侧栏 · 已落地 · 2026-08-28 · ⚠️ v3.10.0 已移除）

> **⚠️ 状态变更**：`article_toc` 与 `contact_card` 两个内置插件在 **v3.10.0** 已全部从仓库移除，
> 仅插件框架保留。本节作为**设计参考**保留——若日后要重建文章目录侧栏插件，直接照此实现即可，
> 核心代码（PostView.vue / App.vue / Sidebar.vue）无需改动。移除后文章目录回退到核心
> `PostView.vue` 的内联 TOC（文首显示、不随滚动高亮，可用但体验降级）。

### 需求与选型
- **痛点**：核心 `PostView.vue` 已有内联 TOC（`<nav class="toc">`），但它是**静态列表**，
  固定在文首、滚动后即消失，长文无法随时跳转、也不显示当前所在章节。
- **方案**：做成**常驻右侧栏 + 滚动高亮（scroll-spy）**的目录侧栏，与核心内联 TOC 互补而非冲突。

### 为什么不用 M2 的 `sidebar` 槽位
M2 的全局 `sidebar` 槽位对**所有非 `/docs` 路由**都渲染（见 `App.vue` 的 `has-sidebar` 判断），
而 TOC 只应在文章页出现 → 无法表达"按路由条件显示"。

因此改用 **M3 远程组件（`remote_components`）**：

| 维度 | M2 `sidebar` 槽位 | M3 远程组件（选用） |
|------|------------------|-------------------|
| 显示范围 | 全站（除 /docs），不能按路由过滤 | 自行判断 DOM/路由，只在文章页出现 |
| 内容形态 | 结构化 `<a>` 链接 | 任意 DOM（sticky 容器 + 滚动高亮） |
| 核心改动 | 需改 `App.vue` 加条件 | **零改动**（脚本自包含，注入 `.sidebar` 顶部） |
| 信任级别 | 服务端数据 | 等同插件代码（仅自写/审计过，同源白名单） |

### 布局决策
文章页是「正文 + 右侧 280px `Sidebar`」两栏（`global.css`：`.layout` flex，`.sidebar{width:280px}`），
**右侧已被博客侧栏占用**。若做固定悬浮 TOC 会与之重叠 → 改为把目录以 `position: sticky`
注入 `.sidebar` **顶部**（`insertBefore(nav, sidebar.firstChild)`），随滚动跟随，不遮挡任何已有内容。

### 实现要点（`myblog/static/plugins/article_toc/widget.js`，自包含原生 JS）
- **扫描**：`document.querySelector(".post-body").querySelectorAll("h2, h3, h4")`；
  无 `id` 的标题自动补 `atoc-<i>`（不覆盖核心既有 id）。
- **注入**：`sticky; top: 96px` 卡片插到 `.sidebar` 首位；正文标题加
  `scroll-margin-top: 90px`，防止点击跳转后被固定头部遮挡。
- **滚动高亮**：`requestAnimationFrame` 节流的 scroll-spy，取距视口顶部 ≤110px 的最后一个标题为当前章节。
- **SPA 适配**：`MutationObserver` 监听 `main.site-frame-inner`（文章异步渲染/路由切换）+ 300/900ms 双延迟重试；
  非文章页（无 `.post-body`）自动移出 DOM。
- **响应式**：`@media (max-width: 820px)` 隐藏（此时侧栏堆叠到正文下方），由核心内联 TOC 兜底。
- **主题**：全部用 `var(--card-bg/--border-color/--link/--accent/--muted)` CSS 变量，自动适配深色模式。
- **零耦合**：不修改 `PostView.vue` / `App.vue` / `Sidebar.vue`，不建表、不注册 API 路由。

### 文件清单
| 文件 | 说明 |
|------|------|
| `myblog/plugins/article_toc/__init__.py` | 后端插件模块，`register()` 返回 manifest + 声明 remote_components；`slots: []`（纯前端） |
| `myblog/static/plugins/article_toc/widget.js` | 远程组件（自包含原生 JS，sticky 侧栏 + scroll-spy） |
| `myblog/config.py` | `ENABLED_PLUGINS` 默认值 → 原 `"contact_card,article_toc"`；**v3.10.0 起改为空** |
| `tests/test_plugin_system.py` | 原新增 4 个 article_toc 测试；**v3.10.0 起改为「临时插件驱动」，不再依赖任何内置插件**（共 31 passed 全量） |

### 测试（14 passed）
- `test_article_toc_loaded`：默认启用，出现在 `/api/plugins`。
- `test_article_toc_declares_remote_component`：名为 `article_toc_widget`，URL 为 `/static/plugins/article_toc/widget.js`（同源白名单）。
- `test_article_toc_no_unexpected_slots`：`slots == []`，不污染 nav/sidebar/html 槽位。
- `test_article_toc_widget_file_exists`：静态资源存在且非空（打包前守卫）。

### 部署注意
- 远程组件走 `/static/plugins/` 静态目录，**前端无需重新构建**（本轮 `vite build` 仅为回归验证）。
- 后端需重启 gunicorn（宝塔「停止 → 启动」）才会加载新插件并出现在 `/api/plugins`。
- 若不想启用：后台「🧩 插件管理」停用，或设 `DISABLED_PLUGINS=article_toc`。

---

## 16. v3.10.0 内置插件下线 + 如何自建第一个插件（2026-08-29）

### 16.1 为什么下线
- 两个内置插件（`contact_card` 联系卡片、`article_toc` 文章目录侧栏）属于「演示性质」，长期维护成本高、与核心功能重叠（联系卡片可用后台「站点公告」替代；目录侧栏核心 `PostView.vue` 已有内联 TOC）。
- 用户决策：**保留插件框架、移除内置插件**——框架是「能力」，一旦需要新插件随时可加；内置插件是「内容」，下线不影响框架可用性。
- 框架保留项：`myblog/plugins/__init__.py`（加载器 + 失败隔离）、`myblog/plugins/signals.py`（事件总线）、`templates/admin/plugins.html`（后台管理页）、前端 `App.vue` 的 nav/sidebar/footer/html/remote_components 槽位、`/api/plugins` 与运行时启停接口。
- `ENABLED_PLUGINS` 默认值改为空 → `create_app` 不加载任何插件，`/api/plugins` 返回空清单；前端槽位无数据渲染为空，不报错。
- `article_toc` 下线后文章目录回退到核心内联 TOC（文首显示、不随滚动高亮）。

### 16.2 自建一个插件（三步）
以「友链 RSS 聚合面板」为例，照第 2/4/15 节的契约即可：

1. **建目录 + register**：在 `myblog/plugins/<slug>/__init__.py` 写 `register(app, cfg)`，返回 manifest（含 `slots` / `remote_components` / `nav` 等声明），用 `app.register_blueprint(bp)` 挂路由。
2. **（纯前端插件）** 在 `myblog/static/plugins/<slug>/widget.js` 写自包含原生 JS（参考第 15 节），manifest 里声明 `remote_components: [{name, url:"/static/plugins/<slug>/widget.js"}]`。
3. **启用**：宝塔环境变量 `ENABLED_PLUGINS` 填 `<slug>`（多插件逗号分隔），「停止 → 启动」gunicorn 生效。后台「🧩 插件管理」可查看状态与运行时启停。

> 红线（重申）：只装自写 / 审计过的插件（第三方插件 = 任意代码执行）；`html` 槽位强制 DOMPurify；远程组件仅限同源 `/static/plugins/`；装卸 = 发版 + 重启，不做运行时热加载。

### 16.3 测试解耦
`tests/test_plugin_system.py` 改为 **「临时插件驱动」**：用 `pluggy`-free 的 `tmp_path` 现场生成一个临时插件目录，并把 `plugins` 包的 `__path__` 指向它，从而验证「加载 / 槽位 / 事件 / 启停 / 失败隔离」完整链路，**不再依赖任何内置插件**（内置插件一删，测试不红）。

