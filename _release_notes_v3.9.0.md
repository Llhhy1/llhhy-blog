# llhhy-blog v3.9.0 · 全栈插件系统

## ✨ 核心新增：插件系统（分阶段 M0→M3 全落地）

- **M0 插件骨架**：`myblog/plugins/` 动态加载框架，`importlib` 加载 `myblog/plugins/<slug>/__init__.py` 的 `register(app, cfg)`；失败隔离——单个插件崩溃只告警，不拖垮博客。
- **M1 事件总线**：`myblog/plugins/signals.py` 基于 blinker 定义 5 个信号（发布 / 评论 / 插件加载等），`emit_*` 助手吞掉订阅者异常，插件可解耦订阅系统事件。
- **M2 前端槽位 + 路由级启停**：`App.vue` 新增 nav / sidebar / footer 结构化 `<a>` 槽位（不用 v-html，杜绝注入）；后端 `/api/plugins` 暴露槽位声明；新增 `POST /api/plugins/<slug>/set-enabled`、`POST /api/plugins/reload` 运行时启停 API（写/删 `disabled` 标记 + 内存覆盖，前端槽位即时生效；路由级启停需重启 gunicorn）。
- **M3 后台插件管理页 + 远程组件**：后台「运维诊断 → 🧩 插件管理」列出插件状态并可运行时启用/停用/整体重载；html 富文本经 `vue-frontend/src/lib/sanitize.js`（DOMPurify）消毒后渲染；远程组件走同源 `/static/plugins/` 前缀 + `<component :is>`（runtime-only Vue 渲染函数，零改动核心代码）。

## 🧩 首个真实插件：`article_toc`（文章目录侧栏）

自包含原生 JS，扫描文章正文 `.post-body` 的 h2/h3/h4：
- 以 `position: sticky` 注入文章页右侧栏**顶部**，随滚动跟随（避开已占用的右栏，不重叠）
- 滚动高亮当前章节（requestAnimationFrame 节流）
- 点击平滑滚动 + `scroll-margin-top` 防被固定头部遮挡
- 窄屏（≤820px）自动隐藏，由核心内联 TOC 兜底；CSS 变量自动适配深色模式

> 选型说明：M2 全局 `sidebar` 槽位无法按路由过滤（全站除 `/docs` 都渲染），故 article_toc 改用 M3 远程组件——能自行判断只在文章页出现，且零改动核心 `App.vue`/`PostView`/`Sidebar`。

## 🔒 安全审计（R48 · 七维 · 0 遗留）

| 维度 | 结论 |
|---|---|
| XSS | SSR 模板 `{{ }}` 自动转义；前端 `v-html` 仅经 DOMPurify 消毒；widget.js 全 `textContent`，无用户数据拼接 |
| 越权 | 后台页 `@admin_required`；写路由 `_require_admin()`（401/403） |
| CSRF | 全局 `before_request` 覆盖所有 POST，插件写路由不在豁免清单，须带 `X-CSRF-Token` |
| SSRF | 远程组件 URL 仅收同源 `/static/plugins/` 前缀（前后端双重校验） |
| 密钥/注入/资源 | 无硬编码密钥、无字符串拼接 SQL、失败隔离 + 异常吞掉 |

详见 `myblog/SECURITY_AUDIT.md` R48 轮。

## 📦 部署

- **含前端构建产物**：须覆盖 `myblog-backend.zip` + `vue-frontend-dist.zip`，宝塔「停止 → 启动」gunicorn（restart 不重载）+ 硬刷新清缓存。
- 新环境变量（可选）：`ENABLED_PLUGINS`（默认 `contact_card,article_toc`）、`DISABLED_PLUGINS`（紧急关停，优先级高于启用列表）、`PLUGINS_DIR`（默认 `myblog/plugins`）。
- 登录后台看左下角版本号应为 `v3.9.0`；后台侧栏「🧩 插件管理」可看 `contact_card`/`article_toc` 状态；打开长文右侧栏顶部出现「目录」卡片。
- 无数据库迁移（插件系统不建表），旧库无缝升级。

## 📎 资产

- `myblog-backend.zip`（后端）
- `vue-frontend-dist.zip`（前端构建产物）
- `sha256.txt`（完整性校验）

---

> 开源协议：MIT · 作者：Llhhy1
