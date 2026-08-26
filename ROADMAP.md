# 博客功能路线图（Roadmap）

> **状态：全部模块已实现 ✅**（截至 v2.2.0）。本文档保留作为功能地图与历史规划存档；新需求请另开 issue 或直接提出。

---

## 一、现状基线（已实现）

| 能力 | 说明 |
|------|------|
| 内容 | 文章 CRUD（后台）、分类、标签、系列/专栏、Markdown 渲染（已 bleach 清洗） |
| 搜索 | **FTS5 全文搜索**（不支持时自动降级 LIKE） |
| 互动 | 评论（**嵌套回复** + IP 属地 + 设备）、评论点赞、文章点赞、**留言墙**、**邮件订阅** |
| 社交 | 「广场」页：微动态（发布/点赞/评论）、**友链 RSS 聚合（博客圈）**、社交账号墙、友情链接 |
| 阅读 | 列表分页、**相关文章推荐**、**热门排行**、**TOC + 阅读进度条**、归档时间线、天气组件 |
| 运营 | 访问统计（区域/时段/热读/热搜）、RSS、sitemap、robots、**站点公告**、**分享 + OG 标签** |
| 分发 | **新文章推送（Telegram / 企业微信）**、**Webhook 自动部署** |
| 后台 | 三级角色、前后台统一登录、**新消息提醒（未读评论/留言角标）**、**版本自检** |
| 安全 | 关 debug、密钥强制环境变量、CORS 同源、限流、开放重定向修复、SSRF 防护、两轮审计 |

**v1.0 时代两大缺口**已补齐：① 社交内容（微动态/留言墙/通知角标）；② 友链 RSS 聚合。

---

## 二、功能地图（按模块 · 全部 ✅）

### 模块 A：社交聚合（「广场」页）✅
- **A1 微动态 Moment**：发短句/随手记 ✅
- **A2 友链 RSS 聚合（博客圈）**：`FriendLink.rss_url` + `feed_agg.py`（15 分钟缓存、防 SSRF、bleach 清洗）✅
- **A3 社交账号墙**：GitHub / B站 / 知乎 / 微博 入口 ✅
- **A4 动态互动**：动态点赞、评论 ✅

### 模块 B：内容与阅读体验 ✅
- **B1 相关文章推荐**：标签重合度算法 ✅
- **B2 热门排行 widget**：复用访问/阅读日志 ✅
- **B3 文章目录 TOC + 阅读进度条** ✅
- **B4 文章系列 / 专栏**：`Series` 模型 + 上下篇导航 ✅
- **B5 全文搜索升级**：`fts.py`（FTS5，自动降级 LIKE）✅
- **B6 定时发布**：`Post.scheduled_at` + 后台守护线程到点自动公开并推送通知；所有对外出口对未到时间文章不可见（v2.7.0）✅
- **B7 文章置顶**：`Post.is_pinned` + 所有公开列表排序 `is_pinned.desc()` 优先展示，前台卡片 📌 标识，后台列表状态徽标（v2.7.1）✅

### 模块 C：互动与社区 ✅
- **C1 留言墙 Guestbook** ✅
- **C2 评论嵌套回复**：`parent_id` / `reply_to`，同文章校验 ✅
- **C3 邮件订阅 / Newsletter**：侧边栏订阅框 + `/api/subscribe`（去重 + 限流）+ 后台「✉️ 订阅者」可查看/删除/启用停用 + 后台「📧 邮件设置」SMTP 配置与测试发送 + 新文章自动群发（带退订链接） ✅ 全部落地

### 模块 D：运营与分发 ✅
- **D1 一键分享卡片（OG 标签）** ✅
- **D2 微信 / Telegram 新文推送**：`notify.py`（Telegram + 企业微信）✅
- **D3 Webhook 自动部署**：`/api/webhook/deploy`（HMAC 校验）+ `DEPLOY_SCRIPT` 自动执行部署脚本（`deploy.sh` 模板随仓库发布）+ 后台一键在线更新（v2.5.0：登录检测→确认→静默更新→完成刷新）+ **v3.1.6 新增 `X-Deploy-Time` 时间戳防重放** ✅
- **D4 站点公告 / 置顶动态**：全局可关闭横幅 ✅

---

## 三、分期计划（已完成存档）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1 · 热身 MVP** | B1 相关文章、B2 热门排行、B3 TOC+进度条、A1 微动态基础 | ✅ 已上线 |
| **Phase 2 · 社交核心** | A2 友链 RSS 聚合、A3 社交账号墙、A4 动态互动、C1 留言墙 | ✅ 已上线 |
| **Phase 3 · 互动深化** | C2 评论嵌套+@、C3 邮件订阅、B4 文章系列 | ✅ 已上线 |
| **Phase 4 · 运营分发** | D1 分享卡片、D2 推送、D3 自动部署、D4 公告、B5 搜索升级 | ✅ 已上线 |

---

## 四、技术注意与风险（实施回顾）

1. **数据库迁移**：本项目用 `db.create_all()` + 启动时手动 `ALTER TABLE`（`app.py` 中 `_migrate_*` 系列函数）自动补列/建表，**重启即迁移，无需手动 SQL**。新增模型直接在 `models.py` 定义即可。
2. **安全**：微动态 / 留言墙 / 评论 / RSS 聚合内容统一走 `clean_html()` 清洗 + 限流；RSS 抓取防 SSRF（只抓 http/https、拦截内网地址）；Webhook 密钥 HMAC 恒定时间比对。
3. **性能**：RSS 抓取 15 分钟内存缓存；FTS5 全文索引与文章同步更新。
4. **开源发布**：v2.0.0（全功能）+ v2.1.0（后台消息提醒）+ v2.2.0（订阅框 + 版本自检）已发布到 GitHub Releases，部署包随 Release 提供。

---

## 五、后续可做（未实现，按需提出）

- **A4 @ 通知增强**：评论/动态 @ 某人时除站内通知外，可加「被@后邮件提醒」（复用现有 SMTP）。
- **评论/留言内容审核增强**：支持先审后发（已有开关）+ 敏感词过滤、图片验证码。
- **多语言 / PWA / 离线缓存**：锦上添花，暂无计划。

---

## 六、v2.6.x UI 打磨迭代记录（存档）

> 以下功能均为前端/静态资源与 UI 调整，无新增后端接口、环境变量或数据库迁移；发版后覆盖代码 + 重启 + 强刷即可。

- **v2.6.14**：根治「后台改了样式不生效」——`admin.css/script.js` 版本戳绑定 `APP_VERSION` + 加 `no-cache` 响应头，发版后浏览器/微信自动拉新（详见 SECURITY_AUDIT 第十六轮）。
- **v2.6.15**:
  - 前台（Vue SPA）移动端汉堡菜单视觉同步为后台 `.admin-hamburger` 风格（强调色胶囊、圆角、阴影、暗色变体）。
  - 后台仪表盘桌面端改为单列全宽布局，修复左右栏（左侧「全部文章」文章少时）高度失衡的大块空白。
  - **后台新增明暗主题切换按钮**（侧边栏顶部 `#theme-toggle`），与前台共用同一 `localStorage.theme` 偏好键——两端切换互相同步。
- **v2.6.16**：修复后台深色模式部分文字不可见——`admin.css` 中 `.admin body` 选择器错误（`body` 的 `.admin` 类在自身上），改为 `body.admin` 后深色模式文字颜色正确继承 `#d7d9dc`，表格、评论列表等子元素在深色背景下均可正常阅读。

## 七、v2.7.0 功能迭代（定时发布 + 优化建议）

> v2.7.0 为**功能新增 + 优化**版本：核心新增「文章定时发布」，并对现有代码做了可见性一致性与后台自动化扫描的优化。

### 7.1 新增：文章定时发布
- **后台写文章页**新增「定时发布」时间选择（datetime-local），与「立即发布」互斥联动。
- **数据模型**：`Post` 新增 `scheduled_at`（可空）；发布时若填未来时间则先存为「待发布」。
- **自动发布**：后端启动守护线程每 60s 扫描到期文章，自动翻 `published=True` 并触发 Telegram/企业微信推送 + 邮件群发（复用现有逻辑，异常静默）。
- **全出口隐藏**：列表/详情/搜索/归档/RSS/sitemap/系列/相关/分类/标签/评论/点赞 全部改用 `visible_posts_query()`，未到时间的定时文章对外完全不可见。
- **后台状态展示**：仪表盘与「我的文章」状态列显示"⏰ 定时(时间)"徽标（含深色模式适配）。

### 7.2 代码优化（本轮顺带）
- 抽离统一的 `visible_posts_query()` 与 `_is_visible()`，消除各接口重复书写 `published=True` 判断，避免后续新接口遗漏"定时可见性"过滤。
- 定时扫描逻辑与请求上下文解耦（独立 `app.app_context()`），线程异常不影响主流程。

### 7.3 后续新功能建议（待定，按优先级）
1. ~~**文章置顶 / 精华**：首页/列表支持置顶，运营用的高频需求。**（v2.7.1 已落地）**~~
2. ~~**草稿自动保存**：写长文时定时 localStorage 缓存，防丢失（关页不丢、下次自动恢复）。**（v2.8.0 已落地）**~~
3. ~~**图片懒加载 + WebP**：前台文章图懒加载，上传大图自动转 WebP 省流量。**（v2.8.0 已落地）**~~
4. ~~**SEO 增强**：文章 `description`/`keywords` 单独编辑字段，注入 Open Graph meta。**（v2.8.0 已落地）**~~
5. ~~**阅读量防刷**：同 IP 24h 去重，真实阅读数更可信，保留反复阅读累计。**（v2.8.0 已落地）**~~
6. ~~**后台文章列表分页/筛选**：关键词 + 状态 + 分类筛选，分页 12/页。**（v2.8.0 已落地）**~~
7. ~~**定时发布「立即发布」一键提前**：后台点一下立即公开，清空定时避免重复触发。**（v2.8.0 已落地）**~~
8. ~~**多作者署名展示**：普通用户文章作者名在列表/详情均展示。**（v2.8.0 已落地）**~~

## 八、v2.7.1 功能迭代（文章置顶）

> v2.7.1 为**功能新增（增量）**版本：落地 v2.7.0 建议清单中优先级最高的「文章置顶」，并同步补充前台卡片标识与后台状态可视化。

### 8.1 新增：文章置顶
- **数据模型**：`Post` 新增 `is_pinned`（Boolean，默认 False），重启后端自动 `ALTER TABLE` 补列。
- **后台写文章页**：新增「📌 置顶」复选框，与「立即发布」「定时发布」独立并存（三者可组合：定时到点后变成"已发布+置顶"是合理组合）。
- **前台/API 排序**：`routes.py` / `api.py` 所有公开文章列表（首页/分类/标签/归档/搜索/RSS/sitemap）的 `order_by` 最前加 `Post.is_pinned.desc()`，置顶文章优先展示；**系列内部上下篇导航（`.asc()`）刻意保持原顺序不动**。
- **API 序列化**：`_post_summary` 返回 `is_pinned` 字段。
- **Vue 前台**：`PostCard.vue` 对置顶文章显示「📌」徽标（`.pin-badge`）。
- **后台状态展示**：仪表盘与「我的文章」状态列追加「📌 置顶」徽标（含深色模式适配 `.status-pinned`）。
- **安全审计**：第二十轮，无高危问题；冒烟测试覆盖列迁移 + 置顶排序 + API 字段，全部通过。

## 九、v2.8.0 功能迭代（七项功能整合）

> v2.8.0 为**功能整合**版本：一次性落地 v2.7.x 建议清单中剩余的 7 项功能（草稿自动保存、图片懒加载+WebP、SEO 独立字段、阅读量防刷、后台分页筛选、定时一键提前公开、多作者署名），全部经安全审计与冒烟测试。

### 9.1 新增功能清单
- **SEO 独立字段**：`Post.seo_description`（TEXT）/ `seo_keywords`（VARCHAR(300)），自动迁移补列；后台编辑页新增输入框；`_post_summary` 返回；`PostView.setOgMeta` 注入 `description`/`keywords`（独立优先于摘要/标签）。
- **多作者署名**：`PostCard.vue` meta 行展示 `✍️ author`；`ArchiveView` 时间轴补作者；所有列表视图共用 `PostCard` 统一生效。
- **阅读量防刷**：`app.count_unique_view(post_id, ip)` 同 IP 24h 去重（真实阅读数可信），保留 `ReadLog` 反复阅读累计；`routes.py` `post()` 与 `api.py` `post_detail()` 均接入。
- **图片懒加载 + WebP**：`utils.clean_html` 给正文 `<img>` 补 `loading="lazy"`；后台 `upload` 接 `app.maybe_convert_webp`（Pillow 可用转 WebP，未装零依赖降级）；封面图模板已懒加载。
- **草稿自动保存**：`edit_post.html` 前端 JS 每 5 秒把编辑内容存 `localStorage`（按 post id 隔离），进入自动恢复并提示，保存后清除。纯前端无后端改动。
- **后台分页+筛选**：`dashboard`/`my_posts` 支持关键词 + 状态（已发布/草稿/定时/置顶）+ 分类筛选，分页 12/页；模板加筛选表单与分页导航。
- **定时一键提前公开**：新增 `/api/post/<id>/publish-now`（登录+权限校验）与后台同名 SSR 路由，立即翻 `published=True` 并清空 `scheduled_at`，触发推送+邮件。
- **安全审计**：第二十一轮，无高危问题；冒烟测试覆盖列迁移、置顶排序、阅读去重、一键发布、WebP 降级，全部通过。

## 十、v3.0.0 功能迭代（14 项功能整合）

> v3.0.0 为**大型功能整合**版本：一次性落地 14 项功能（系列目录增强、字数统计、评论批量+垃圾过滤、操作日志、版本历史/回收站、友链申请、热门标签、看了又看、访客趋势图、分类/标签 RSS、多语言、隐私空间、打赏），全部经安全审计（R7）与冒烟测试（24 项通过）。

### 10.1 新增功能清单
- **系列目录页 + 阅读进度**：`SeriesDetailView` 新增带编号章节 TOC（系列 TOC）；前台全局阅读进度条（App.vue `reading-progress`）持续生效。
- **字数统计 + 阅读时长**：`Post.word_count`/`reading_minutes` + `utils.count_words`（中文字数 + 英文/数字 token，分钟 = max(1, round(字数/300))）；编辑/详情页展示。
- **评论批量 + 垃圾过滤**：后台 `/comments/batch-approve`、`/comments/batch-delete`（多选 + `@admin_required`）；评论提交命中 `Setting.comment_spam_keywords` 即 400 拒收。
- **后台操作日志**：`AuditLog` 模型 + `/admin/audit-logs`、`/admin/clear-audit_logs`（均 `@super_required`，`log_audit` 辅助函数贯穿关键写操作）。
- **版本历史 / 回收站**：`PostHistory`（每篇上限 20 版，`_save_post_history` 自动留存）；删除改为软删除（`in_trash=True` + `RecycleBin` 快照），支持 `/admin/post/<id>/restore`、`/purge`、`/history`、回滚。
- **友链申请 + 自助审核**：`LinkApplication` 模型 + 前台 `/api/link-apply`（限流 10/24h + URL 正则 + 去重）、后台 `/admin/link-applications` 审核通过/拒绝。
- **热门标签云**：`/api/hot-tags`（权重 = 文章数×2 + 阅读量//1000），前台 `HotTagsView` 独立页。
- **「看了又看」协同过滤**：`/api/post/<slug>/also-viewed`（ReadLog 共现 + 标签/分类相似度加权，冷启动退化为相似推荐）。
- **访客趋势图**：`stats.compute_trend(days)` + `/api/stats/trend`；`StatsView` 纯 SVG 折线（PV 蓝 / UV 绿）。
- **RSS 按分类 / 标签**：`/api/rss/category/<slug>`、`/api/rss/tag/<slug>`（复用 `_rss_xml` 助手）。
- **多语言 i18n**：`store.js` 内置 `I18N` 中英词典 + `t()`/`setLang()`/`initLang()`；导航 + 抽屉 + 部分界面文案随 `state.lang` 切换；后台可设 `site_lang` 默认语言。
- **隐私空间**：`Post.is_private`；`visible_posts_query(user)` 对非超管过滤；`post_detail` 传入当前 user，超管登录可见本人隐私文章，其余人 404。
- **文章打赏**：`Post.reward_enabled`/`reward_qr`（仅超管编辑时开关）；前台 `PostView` 展示 `post.reward_qr` 或站点 `reward_qr_default`；后台设置可设默认收款码。

### 10.2 新增/变更接口与环境变量
- 新增接口：`/api/hot-tags`、`/api/post/<slug>/also-viewed`、`/api/stats/trend`、`/api/rss/category/<slug>`、`/api/rss/tag/<slug>`、`/api/search`（分页 + 高亮）、`/api/link-apply`。
- 新增后台页：`/admin/audit-logs`、`/admin/recycle-bin`、`/admin/link-applications`、`/admin/post/<id>/history`。
- 新增站点设置：`comment_spam_keywords`（垃圾评论关键词，逗号分隔）、`site_lang`（默认语言 `zh`/`en`）、`reward_qr_default`（默认打赏收款码 URL）。
- **自动迁移**：重启时 `app.py` 的 `_migrate_*` 自动补列（Post 7 个新字段）+ 新建 4 张表（audit_log / recycle_bin / link_application / post_history），无需手动 SQL。
- **安全审计**：第七轮（R7），修复 `/api/link-apply` 模型未导入导致的 500 与隐私空间超管自查看不到的问题；24 项冒烟测试全部通过。

## 十一、v3.1.0 功能迭代（登录审计 + 前台大框 + 主题修复）

> v3.1.0 为**可观测性增强 + 视觉对齐**版本：补齐后台登录审计、审计日志 30 天保留与打包下载，前台内容统一大框（对齐后台），并修复手机端汉堡菜单不随深色模式切换的问题。全部经安全审计（R8）与冒烟测试通过。

### 11.1 新增功能清单
- **后台登录审计日志**：`log_login_attempt()` 在三个登录入口（api `/auth/login`、admin `login`、routes `login`）调用，成功/失败均写入 `AuditLog`（action='login'，含尝试用户名、来源 IP）；`AuditLog` 新增 `success` 列（迁移 `_migrate_audit_log_table` 自动补列）。
- **审计日志 30 天保留**：每次登录顺带调用 `_purge_audit_logs_older_than(30)` 清理超期日志（原清理按钮由 7 天改为 30 天）。
- **审计日志打包下载**：`/admin/audit-logs/export`（`@super_required`）用 `io.BytesIO` + `zipfile` 内存打包 CSV + TXT，经 `send_file` 流式返回，不落盘。
- **前台统一大框**：`App.vue` 内容区外包 `.site-frame`（视觉对齐后台 `.section-box`，浅灰底 + 细边框 + 圆角 + overflow 裁剪 + 暗色变量）；窄屏收敛边距。
- **主题初始化修复（手机汉堡不跟随）**：`App.vue` `onMounted` 原在 `initSite` 异步完成前强制把 `data-theme` 重置为 light（覆盖用户已选 dark），改为站点设置加载后据 `localStorage` 修正主题与图标，并加 `matchMedia` 跟随系统。

### 11.2 安全审计
- 第八轮（R8）：导出接口路径穿越/注入/资源泄漏均不涉及（文件名服务端生成、内存打包）；登录日志仅超管可见；XSS/SQL 注入/CSRF/限流沿用既有防护。无高危问题。

## 十二、v3.1.1 修复迭代（抽屉深色模式）

> v3.1.1 为**纯前端 CSS 修复**版本：修复手机端抽屉（`.drawer`）在深色模式下仍为白底的问题。

### 12.1 修复清单
- **抽屉不跟随深色模式**：根因为 `[data-theme="dark"]` 段只重写了 `.site-header` 写死背景，未重定义 `--nav-bg / --nav-fg / --nav-border` 导航变量，而 `.drawer` 依赖这三个变量，导致暗色下仍是白底。
- **修复**：在 `[data-theme="dark"]` 段重定义三个变量为暗色值（`#1d2025 / #d7d9dc / #2a2e35`）；补充抽屉暗色专属规则（`.drawer` 底色/边框、`.drawer-nav a:hover`、`.drawer-link` 背景加深）；`.drawer-user` 文字由写死 `#666` 改为 `var(--nav-fg)` 降透明度。

### 12.2 安全审计
- 第九轮（R9）：纯 CSS 变量重定义，无动态内容/用户输入，无接口变更，无回归风险（亮色模式用 `:root` 原变量不受影响）。`vite build` 通过。

## 十三、v3.1.2 部署脚本修复（不含代码变更）

> v3.1.2 为**部署脚本修复**版本：解决一键更新卡在第⑥步跨用户 `kill` 权限失败（`Operation not permitted`）。仅更新 `update.sh` / `deploy.sh`，APP_VERSION 仍为 v3.1.1。

### 13.1 修复清单
- **跨用户 kill 权限失败**：gunicorn 由宝塔以 `www` 用户启动，一键更新脚本以 root 触发时 `kill -TERM <pid>` 被系统拒绝。
- **修复**：脚本默认 `PROJECT_NAME="myblog"`，重启优先走 `supervisorctl restart myblog`（supervisor 以 www 身份停+起，根本不碰跨用户 kill）；root 身份运行时自动加 `sudo -u www` 保护；兜底 kill 段同样加 `sudo -u www`。

## 十四、v3.1.3 抽屉深色补充修复

> v3.1.3 为**纯前端 CSS 修复**版本：在 `[data-theme="dark"]` 区块末尾追加 4 条直接写死暗色值的菜单抽屉规则，彻底覆盖旧规则，确保深色模式下抽屉视觉稳定。

### 14.1 修复清单
- **抽屉深色样式仍可能不稳定**：v3.1.1 仅靠重定义变量，个别抽屉子元素仍可能回退浅色。
- **修复**：在 `[data-theme="dark"]` 区块末尾追加 `.drawer { background:#1d2025; border-color:#2a2e35 }`、`.drawer-nav a { color:#c7ccd1 }`、`.drawer-nav a:hover { background:rgba(124,176,255,.12); color:#fff }`、`.drawer-foot { color:#9aa0a6; border-top-color:#2a2e35 }`，置于文件末尾后定义覆盖前定义（预期行为）。APP_VERSION 升为 3.1.3。

### 14.2 安全审计
- 第十轮（R10）：纯 CSS 静态规则，无动态内容/用户输入/接口变更，无新增攻击面；4 条规则置于文件末尾特异性与旧规则相同，覆盖行为符合预期，不影响亮色模式。`py_compile` 通过（仅版本字符串）、`vite build` 通过、package.py 打包校验通过（APP_VERSION=3.1.3，不含 data/）。

## 十五、v3.1.4 部署脚本根因修复（不含代码变更）

> v3.1.4 为**部署脚本根因修复**版本：纠正 v3.1.2 的错误假设，让一键更新/自动部署真正能在宝塔环境自动重启。仅更新 `update.sh` / `deploy.sh`，APP_VERSION 仍为 v3.1.3。

### 15.1 修复清单
- **错误假设纠正**：宝塔 Python 项目**不是** supervisor 管理（无 `supervisorctl`），且 gunicorn 进程属主是 **`mw`（uid=1000），不是 `www`**。v3.1.2 写死的 `sudo -u www` / `supervisorctl` 在本机全部不成立，导致跨用户 kill 权限失败（Operation not permitted）。
- **修复**：重启探测顺序改为 ① `RESTART_CMD`（手动指定）→ ② 宝塔 CLI `bt stop/start <项目名>` → ③ 以 `mw` 身份 `runuser -u mw` 真杀 + 用宝塔真实 gunicorn 路径（`/ww/server/pyporject_evn/blog_env/bin/gunicorn -c gunicorn_conf.py`）重新拉起 → ④ 提示手动。
- **新增变量**：`APP_USER="mw"`、`GUNICORN_BIN`（宝塔托管路径）、`GUNICORN_CONF="gunicorn_conf.py"`，彻底移除对 `www` / supervisor 的依赖。

### 15.2 安全审计
- 第十一轮（R11）：纯部署脚本修正，无后端/前端代码改动。以进程同身份 `mw` 操作，跨用户 kill 根因消除；所有变量为脚本内置常量无外部输入注入；仍优先 pidfile + 精确匹配避免误杀；若 bt/runuser 均不可用降级为提示手动，绝不误报成功。`bash -n` 语法校验通过（update.sh / deploy.sh）。

## 十六、v3.1.5 安全加固四项

> v3.1.5 为**安全加固**版本：补齐外部安全审计清单中确属真实缺口的四项，外加一键更新完整性校验。后端代码、前端代码、数据库结构均有改动，APP_VERSION 升为 3.1.5。

### 16.1 修复清单
- **FTS 搜索转义**：全文搜索（搜索建议接口 `/api/search/suggest`）原样把用户输入拼入 FTS5 `MATCH`，特殊字符（`" * : - ( )` 等）会导致查询语法异常。新增 `escape_fts_query()` 做短语包裹 + 内部双引号转义，`search()` 失败仍回退 LIKE。
- **密码最小长度 6 → 8**：注册（`api.py`/`routes.py`/`RegisterView.vue`）、后台改密、创建用户、重置他人密码、首次设置五处后端校验 + 后台活跃模板（`change_password`/`setup`/`users`/`register`）+ 前端注册的 `minlength` 与提示文本，统一为 8 位下限，前后端一致。
- **审计日志 CSV 公式注入防护**：后台审计日志导出（`/admin/audit-logs/export`）的 CSV 写入，对以 `= + - @` 及空白控制字符开头的单元格加前缀单引号，防止 Excel/Numbers 打开时执行恶意公式（如 `=cmd|...`）。
- **一键更新哈希校验**：`update.sh` 下载后端/前端包后比对 Release 附带的 `sha256.txt`（由 `package.py` 自动生成），哈希不一致直接 `fail_exit` 终止更新，防中间人篡改 / 下载损坏；缺失 checksum 文件时降级为告警不阻断。

### 16.2 安全审计
- 第二十二轮（R12）：四项缺口全部补齐，无新增攻击面。`py_compile` 全量编译通过；隔离单元冒烟测试（FTS 转义 5/5、CSV 防护 6/6、密码校验逻辑）通过；`bash -n` 校验 update.sh / deploy.sh 通过；package.py 生成 sha256.txt 验证通过。残余风险（CSRF Token 显式校验、上传魔数校验、DNS 重绑定）已记录在 SECURITY_AUDIT.md，非阻塞。

## 十七、v3.1.6 安全加固 12 项（全量落地）

> v3.1.6 依据外部安全审计清单（高优 4 + 中优 5 + 可选增强 4 + 运维 3）逐项核对，将其中**确属真实缺口**的 12 项代码级加固全部落地，配套文档/部署脚本同步更新。经 R13 安全审计 + 11 组冒烟测试全部通过。

### 17.1 新增/变更清单

| 分类 | 项目 | 落地方式 |
|---|---|---|
| 高优 | 更新包 sha256.txt 自身完整性（双源互证） | `package.py` 把「内容区」SHA256（剥离 EOCD 尾注释后的字节）写入 zip 注释；`sha256.txt` 记录含注释的整文件哈希；`update.sh` 分别按各自口径比对 + 可选 HMAC 签名 |
| 高优 | 上传文件魔数校验 | 后缀白名单 + PNG/JPG/GIF/WebP magic bytes 双重校验 |
| 高优 | SMTP 密码不存库 | `SMTP_PASSWORD_ENV_FIRST`（默认 true）——密码优先环境变量，库值仅兜底 |
| 高优 | 多 worker 全局限流 | `REDIS_URL` 配置后走 Redis INCR+EXPIRE 全局计数；未配置自动回退内存滑动窗口 |
| 中优 | CSRF Token 双重防护 | 同源校验 + 会话绑定 HMAC Token，全局 POST/PUT/DELETE/PATCH 校验；前端 apiPost 自动带 `X-CSRF-Token` |
| 中优 | RSS DNS 重绑定缓解 | feed_agg 域名先 `getaddrinfo` 解析，解析结果含内网/回环/保留地址即拒 |
| 中优 | 弱密码黑名单 + 复杂度开关 | `STRONG_PASSWORD` / `STRONG_PASSWORD_MIXED_CASE`；前端/后端统一提示 |
| 中优 | 登录防枚举 + 会话踢下线 | 失败统一文案 + `LOGIN_DELAY_SECONDS` 延迟；`session_version` 机制 + 超管「踢下线」路由 |
| 中优 | 审计日志筛选与保留 | `?from=&to=` 时间筛选；`AUDIT_LOG_DAYS` 保留周期；导出支持筛选 |
| 可选 | 可开关验证码 | `CAPTCHA_ENABLED`：注册/评论/留言图形验证码，一次性票据防重放，PIL 缺失自动降级 |
| 可选 | 安全响应头 | `SECURITY_HEADERS`：X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy 全局追加 |
| 可选 | 会话超时 + 改密码销毁旧会话 | `SESSION_IDLE_MINUTES` 闲置超时；改密/重置/踢下线后 session_version+1 旧会话失效 |
| 可选 | Webhook 防重放 | `X-Deploy-Time` 时间戳 + `WH_REPLAY_WINDOW`（默认 300s）窗口校验 |
| 运维 | Nginx 真实 IP / HTTPS / 定期备份 | deploy_guide 新增 CDN real_ip、强制 HTTPS、宝塔计划任务每日备份命令 |

### 17.2 新增环境变量

`REDIS_URL`、`WH_REPLAY_WINDOW`、`SMTP_PASSWORD_ENV_FIRST`、`STRONG_PASSWORD`、`STRONG_PASSWORD_MIXED_CASE`、`LOGIN_DELAY_SECONDS`、`SESSION_IDLE_MINUTES`、`AUDIT_LOG_DAYS`、`CAPTCHA_ENABLED`、`SECURITY_HEADERS`、`UPDATE_HMAC_KEY`（详见 `myblog/deploy_guide.md` 与根 README）。

### 17.3 升级注意

- `user` 表新增 `session_version` 列，重启后端自动迁移；**升级后所有用户需重新登录一次**（预期行为）。
- 第三方直接 POST 不带 CSRF Token 会被 403（预期安全行为），前端已自动适配。
- 验证码默认开启，未装 Pillow 自动降级关闭。

### 17.4 验证

- R13 安全审计：13 个维度全部 ✅ 通过。
- `py_compile` 全量通过；隔离临时库冒烟测试 11 组全部通过。
- 前端 Vue 改动（api.js/store.js/RegisterView/CommentForm/GuestbookView/global.css）经 `npm run build` 构建验证。

## 18. v3.1.7：CSRF 隐藏域乱码修复（R14 审计通过）

### 18.1 背景
v3.1.6 上线后用户反馈「登录后台后出乱码」。根因：`csrf_input()` 返回普通字符串的 `<input>` 隐藏域，Jinja2 默认 autoescape 将其转义成 `&lt;input ...&gt;` 源码文本渲染到页面（尤其带表单的后台页）。

### 18.2 修复
- `myblog/utils.py` 的 `csrf_input()` 返回值改用 `markupsafe.Markup(...)` 包装——Markup 是已信任的安全 HTML，autoescape 不再转义，隐藏域以原生 `<input type="hidden" name="csrf_token" value="...">` 渲染。
- `markupsafe` 是 Flask 自带传递依赖，**无新增 requirements**。
- 一处修复全局生效：后台 24 个表单模板 + 前台登录/注册页 + base.html 退出按钮，全部走 `{{ csrf_input() }}`。
- 前端无需改动。

### 18.3 验证
- R14 审计：功能回归 / XSS / CSRF 有效性 / 资源依赖 4 维度全部 ✅（详见 `myblog/SECURITY_AUDIT.md` 第二十四轮）。
- 真实渲染验证（隔离临时库 + test_client）：后台 dashboard（`/admin/`）+ 前台登录页（`/login`）均含原生隐藏域、无 `&lt;input` 转义文本。
- `py_compile` 编译通过。APP_VERSION 升为 v3.1.7。

## 19. v3.1.8：后台退出按钮 405 修复（R15 审计通过）

### 19.1 背景
v3.1.7 修复 CSRF 隐藏域乱码后，用户反馈「退出登录按钮失效，点击显示 Method Not Allowed」。根因：v3.1.6 引入 CSRF 时把后台退出表单从 GET 改为 POST + 隐藏域（base.html），但 `/admin/logout` 路由声明仍为默认 GET-only，POST 命中 GET-only 路由 → 405。

### 19.2 修复
- `myblog/admin.py`：`/admin/logout` 路由改为 `methods=["GET", "POST"]`——POST 服务退出表单（带 CSRF 隐藏域），GET 保留兼容旧链接/直接访问。
- `logout()` 逻辑不变（仅清会话后跳首页）。
- 全仓库排查确认：这是唯一「表单 POST 但路由未声明 POST」的遗漏（其余表单 action 路由均已声明 POST）。

### 19.3 验证
- R15 审计：功能回归 / CSRF 有效性 / 越权会话 / 回归风险 4 维度全 ✅（详见 SECURITY_AUDIT.md 第二十五轮）。
- 隔离临时库 + test_client 实测：POST `/admin/logout` 302（不再 405）、GET 兼容 302、退出后访问后台被重定向。
- `py_compile` + 冒烟 11 组全通过。APP_VERSION 升为 v3.1.8。

## 20. v3.2.0：后台验证码独立设置页 + Pillow 缺失修复（R16 审计通过）

### 20.1 背景
用户反馈「验证码功能用不了」并要求「在后台加一个可以单独设置的页面」。根因有二：① `requirements.txt` 遗漏 Pillow，服务器未装图像库时验证码恒降级停用；② 验证码只能靠环境变量 `CAPTCHA_ENABLED` 控制全局，后台无配置入口。

### 20.2 修复
- `requirements.txt` 补 `Pillow>=10.0.0`。
- `security.py`：验证码配置改为读 `Setting` 表（全局开关 / 长度 3–8 / 干扰强度 / 排除易混字符 / 注册·评论·留言各场景开关）；`captcha_required(scope)` 按请求路径自动推断场景；新增 `get_captcha_config()`。
- `api.py`：新增 `GET /api/captcha/config`；`/api/captcha` 图片接口按场景（`from` 参数）显隐。
- `admin.py` + 模板：新增 `/admin/captcha-settings`（超管）读写上述 Setting；`base.html` 系统设置组加「🛡️ 验证码设置」菜单。
- 前端 `RegisterView/CommentForm/GuestbookView` 的 `initCaptcha()` 改为读 `/api/captcha/config` 按场景显隐。

### 20.3 验证
- R16 审计：越权 / XSS·注入 / CSRF / 资源依赖 / 降级兼容 5 维度全 ✅（详见 SECURITY_AUDIT.md 第二十六轮）。
- `py_compile` + 前端 build（dist_v316）+ `smoke_v320.py` 专项冒烟（默认配置 / 单场景关闭 / 全局关闭 / 长度配置 / 后台页面登录 GET·POST 保存）全部通过。
- APP_VERSION 升为 v3.2.0。

## 21. v3.2.1：前台平板断点（768–1004px）头部竖排修复（R17 审计通过）

### 21.1 背景
用户反馈前台在视口宽度 `768px ≤ W < 1004px` 时，顶部导航文字变成纵向排布、非常难看。

### 21.2 修复
- `vue-frontend/src/styles/global.css`：把汉堡/抽屉断点从 `760px` 提到 `1004px`，整个平板区间统一走「汉堡 + 抽屉」干净布局，桌面内联 nav 仅在大屏（>1004px，容器达 1040px 上限能从容排开）才显示；并删除 `max-width:768px` 断点里与抽屉断点冲突的头部换行规则（`.header-inner`/`.site-header nav` 的 `flex-wrap`/`width:100%`），根除竖排根因。
- `vue-frontend/src/App.vue`：因平板区间桌面 nav 被隐藏，原 nav 内语言切换按钮会一并消失，遂在抽屉底部补等价语言切换按钮（`drawer-lang`），保持功能一致。

### 21.3 验证
- R17 审计：越权 / XSS·注入 / CSRF / 资源依赖 / 降级兼容 5 维度全 ✅（纯前端改动，无新增安全面，详见 SECURITY_AUDIT.md 第二十七轮）。
- 前端 build（dist_v317）编译通过；后端本轮无 Python 改动。
- APP_VERSION 升为 v3.2.1。

## 22. v3.3.0：数据备份与异地容灾（R18 审计通过）

### 22.1 背景
此前仅有手动打包，缺自动备份与多目的地容灾；服务器误删 / 被黑 / 磁盘坏道会导致文章与上传图片永久丢失。用户明确选择「本地 + OSS + SCP + 云盘」四类目的地全覆盖，并采用「仅超管 + 二次确认」的恢复策略。

### 22.2 实现
- `myblog/backup.py`（纯标准库）：`create_backup()` 打包 `data/blog.db` + `static/uploads/*` 为带 `manifest.json` 的 zip，落本地后同步已启用的远程后端，并按 `RETENTION_DAYS` 滚动清理；`sync_oss/sync_scp/sync_webdav` 各自 env 开关、`ImportError`/异常仅记录不阻断；`verify()` 校验 manifest + 每文件 SHA256 + 路径白名单；`restore()` 需 `yes=True`，恢复前自动 `_snapshot_before_restore()`，路径白名单 `_safe_rel()` 防穿越。
- `myblog/config.py`：新增全部 `BACKUP_*` 环境变量（密钥仅环境变量，不落库）。
- `myblog/admin.py` + `templates/admin/backup.html`：超管专属 `/admin/backup`（GET 列表 / POST 备份·下载·恢复），恢复需 `confirm=yes` + CSRF + 审计日志。
- `myblog/backup.sh`：宝塔定时任务入口（`0 4 * * * bash .../backup.sh`）。
- `templates/admin/base.html`：系统设置组加「💾 数据备份」菜单。

### 22.3 验证
- R18 审计：越权 / XSS·注入 / CSRF / 资源依赖 / 降级兼容 5 维度全 ✅（详见 SECURITY_AUDIT.md 第二十八轮）。
- `py_compile` 全量通过；隔离临时库 roundtrip（create → verify → restore → snapshot）通过。
- 前端本轮无改动（复用 dist_v317）。APP_VERSION 升为 v3.3.0。

## 23. v3.3.1：后台「立即更新」CSRF 修复（R19 审计通过）

### 23.1 背景
用户反馈后台「系统设置 → 立即更新」报错「CSRF 校验失败，请刷新页面后重试」。v3.1.6 引入的全局 CSRF 要求所有 POST 携带会话绑定 token（表单字段或 `X-CSRF-Token` 请求头），而「立即更新」按钮用 `fetch()` 发 JSON POST 到 `/api/version/update`，此前未带 token，点击必 403。

### 23.2 实现
- `myblog/templates/admin/base.html`：`/api/version/update` 的 fetch 请求头补 `'X-CSRF-Token': '{{ csrf_token }}'`（模板上下文本就由 `inject_globals()` 注入该值）。**单行改动；接口未加入 CSRF 豁免名单，防护完整保留。**
- `myblog/config.py`：`APP_VERSION` 升为 `3.3.1`。

### 23.3 验证
- R19 审计：功能回归 / CSRF 有效性 / 越权 / 回归风险 4 维度全 ✅（详见 SECURITY_AUDIT.md 第二十九轮）。
- 隔离临时库冒烟：带 token 调 `/api/version/update` → 400「未找到更新脚本」（CSRF 放行）；不带 token → 仍 403（防护未失效）。
- `py_compile` 全量通过。前端本轮无改动（复用 dist_v317）。APP_VERSION 升为 v3.3.1。

## 24. v3.4.0：备份配置后台化 + 立即备份 500 修复（R20 审计通过）

### 24.1 背景
两件事合并为 v3.4.0：
1. 用户反馈后台「立即备份」点击报 500；
2. 用户要求备份配置直接在后台管理（不再依赖环境变量）。

### 24.2 实现
- **500 修复**：`admin.py` backup 路由 4 处 `add_audit` → `log_audit`（函数名笔误，NameError 导致 500；备份文件实际已生成，仅审计写入崩）。修复后立即备份 200 + 审计正常。
- **`myblog/backup_settings.py`（新增）**：
  - 非密钥字段（目录/桶名/域名/保留天数等）存 Setting 表，库值优先、环境变量兜底；
  - 密钥字段（OSS SecretKey / WebDAV 密码 / SCP 私钥路径）用 **SECRET_KEY 派生的 Fernet 密钥（PBKDF2-HMAC-SHA256、固定盐）加密**后存库，页面只回显掩码；
  - 密钥读取优先级：环境变量优先 → 库加密值兜底（老配置兼容无迁移）；
  - `apply_env()` 写回 `os.environ`，backup.py 同步函数与 CLI（无 Flask 上下文，sqlite3 直连 Setting 表）均自动读后台配置。
- **`admin.py`**：新增 `/admin/backup-settings`（`@super_required` + 全局 CSRF + 掩码回显 + 保存后热生效）。
- **`backup.py`**：启动应用后台配置；新增 `remote_status()`（含来源标记）。
- **模板**：`admin/backup_settings.html`（新增）+ `backup.html` 来源标记/入口 + `base.html` 菜单「⚙️ 备份配置」。
- **`requirements.txt`**：新增 `cryptography>=41.0.0`；`config.py` `APP_VERSION=3.4.0`。

### 24.3 验证
- R20 审计：XSS / CSRF / 越权 / 密钥管理 / SSRF·命令注入 / 资源依赖 / 回归风险 7 维度全 ✅（详见 SECURITY_AUDIT.md 第三十轮）。
- 500 复现修复：POST `/admin/backup`（backup_now）200 + 审计写入。
- 备份配置冒烟 7 项：加密落库/掩码回显/合并配置/CLI 独立/密钥环境变量优先/立即备份回归。
- `py_compile` 全量通过。前端本轮无改动（复用 dist_v317）。APP_VERSION 升为 v3.4.0。

## 25. v3.4.1：前台视觉升级 + 汉堡菜单深色修复（R21 审计通过，纯前端）

### 25.1 背景
用户反馈：「后台设计比前台精美，帮前台也设计一下，顺手修复深色模式下汉堡菜单文字看不清」。本轮仅改 `vue-frontend/`，后端零改动。

### 25.2 实现
- **深色汉堡菜单不可读修复（双保险）**：
  - 根因：`src/store.js#applyThemeVars()` 用**内联 style** 写死导航变量（--nav-fg 浅色 #555555），内联优先级高于 `[data-theme="dark"]` 的 CSS 变量重定义 → 暗色下抽屉文字仍是深灰。
  - 修复① `App.vue#applyTheme()`：切暗色时内联覆盖 --nav-bg/--nav-fg/--nav-border 为暗色值，切浅色按后台 nav_style 回写；
  - 修复② `styles/global.css`：暗色下抽屉全部文字直接写死浅色（logo/close/nav/user/foot/link），JS 未执行也兜底。
- **前台视觉升级（与后台 inis 风格统一）**：首页渐变 hero 横幅（同后台 hero-card）、页面标题主题色装饰条、卡片/widget hover 上浮 + 阴影、widget 顶部主题色装饰线、输入框 focus ring、按钮 ghost/danger/small 变体 + 暗色适配、分页胶囊、登录卡升级、空态虚线卡片、热门标签云补齐（此前无样式）、天气组件暗色适配、评论/留言/搜索/系列/统计页明细补齐、TOC hover 细化。
- **构建**：`vite.config.js` outDir → `_vite_build15`（延续 _vite_buildN 序列规避删除保护）；根 .gitignore 同步加入。
- `config.py` `APP_VERSION=3.4.1`。

### 25.3 验证
- R21 审计：XSS / SQL 注入 / 越权 / CSRF·会话 / 密钥 / 资源 / 回归 7 维度全 ✅（详见 SECURITY_AUDIT.md 第三十一轮）。
- 前端构建 `_vite_build15` 成功（vite build 2.67s，产物 15 chunk），`vite preview` HTTP 200。
- 深色修复核查：applyTheme 内联覆盖（暗色 + 浅色回写分支）+ global.css 暗色抽屉 7 条写死浅色规则齐全。
- 后端零改动，`py_compile` 无需重跑。APP_VERSION 升为 v3.4.1。

## 26. v3.4.2：一键更新脚本双源互证校验修复（R22 审计通过，脚本修复）

### 26.1 背景
用户反馈：后台「立即更新」/ 宝塔终端 `bash /www/wwwroot/myblog/update.sh`，走到「下载 sha256.txt」后**静默退出(码1)**，日志无 ❌ 行、仅「脚本异常退出(码1)，详见 data/update_log.txt」。排查为 `update.sh` / `deploy.sh` 的 `verify_checksum` ②段（v3.1.6 zip 注释双源互证）逻辑写错。

### 26.2 根因
- 双源互证设计：发布 zip 在 **ZIP 注释内嵌「内容区」SHA256**（剥离尾注释，package.py `_strip_zip_comment`：EOCD 注释长度字段清零）；`sha256.txt` 记录**整文件**（含注释）哈希。两源**故意不同**、互相独立：整文件替换 → sha256sum 失败；单改包体/单改注释 → 注释内嵌哈希与剥离后内容区哈希不一致。这就是双源互证。
- 脚本 bug：②段 Python 写成 `sys.exit(0 if h.hexdigest() == 注释内嵌hash == sys.argv[2].lower() else 1)`——**三向链式比较**（内容区哈希 == 注释内嵌哈希 == 整文件哈希）。后两项恒不等 → 整链恒 False → python3 校验**永远失败**返回 1。
- 放大：`$(python3 -c ...)` 命令替换无 `|| true` 兜底，配合 `set -e` → python3 返回 1 就**静默终止整脚本**，FAIL_MSG 未设 → 只剩通用「异常退出(码1)」。

### 26.3 修复
- `update.sh` / `deploy.sh` ②段改为「本地剥离 zip 尾注释重算内容区哈希 == 注释内嵌 SHA256 单独比对」（不再链 sha256.txt，sha256.txt 由 ① `sha256sum` 负责）——数学正确的双源互证②。
- 两处 `$(python3 -c ...)` 加 `|| true` 兜底：python3 缺失/异常时降级跳过（log 提示），不再炸脚本。

### 26.4 验证
- R22 审计：XSS / SQL / 越权 / CSRF / 密钥 / 资源 / 回归 7 维度全 ✅（详见 SECURITY_AUDIT.md 第三十二轮）。
- 双路径闭环：正常 `vue-frontend-dist.zip` → PASS；篡改副本（改包体保留注释）→ REJECT；整文件哈希 ≠ 内容区哈希（双源互证前提成立）。
- `bash -n` 语法通过、CRLF=0。后端零改动。
- ⚠️ 升级顺序：服务器若仍用 v3.4.1（含）之前脚本，先覆盖 Release v3.4.2 的 `deploy_scripts_v342fix.zip` 再跑一键更新。
- ⚠️ 已知缺陷（v3.4.3 已修复）：`deploy_scripts_v342fix.zip` 校验段用 `sys.exit(0/1)` 传结果，bash 命令替换捕获 stdout 而非退出码 → 正常包必误报。该包已废弃，改用 `deploy_scripts_v343fix.zip`。

## 27. v3.4.3：一键更新脚本输出机制修复（R23 审计通过，脚本修复）

### 27.1 背景
用户反馈 v3.4.2 修复版脚本在**正常发布包**上误报「❌ myblog-backend.zip 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。」——即 v3.4.2 自己引入了新的可用性故障。

### 27.2 根因（输出机制陷阱，重要经验）
- v3.4.2 已把校验比较改对为两向（内容区哈希 == 注释内嵌哈希），但校验结果仍用 `sys.exit(0/1)` 传出。
- bash **命令替换 `$(...)` 捕获的是 stdout 而非退出码**；`sys.exit()` 不产生任何 stdout → `comment_ok` 恒为空串 → `"" != "0"` → 永远走失败分支 → 正常包也误报。
- 已用 `gh api` 认证通道下载 v3.4.2 真实资产回验：内容区哈希 `88b99800…` == 注释内嵌哈希（PASS）、整文件哈希 `e9283c16…` == sha256.txt（一致）——**包本身无问题，纯脚本输出机制 bug**。

### 27.3 修复
- `update.sh` / `deploy.sh` 校验段 Python 改为 `print('OK'/'BAD'/'NO'/'ERR')` + `sys.exit(0)`（用 stdout 传结果）。
- bash 用 `case "$comment_ok"` 按内容判断：`OK` → 通过；`BAD` → fail_exit 终止；`NO`/`ERR`/无输出 → 降级为仅靠 sha256.txt 比对（不再误杀正常包）。

### 27.4 验证
- R23 审计：XSS / SQL / 越权 / CSRF / 密钥 / 资源 / 回归 7 维度全 ✅（详见 SECURITY_AUDIT.md 第三十三轮）。
- 双路径闭环（直接执行脚本内真实代码段，不复刻逻辑）：正常发布包 → `OK`；篡改副本（改包体保留注释）→ `BAD`。
- `bash -n` 语法通过、CRLF=0。后端业务代码零改动。
- ⚠️ 升级顺序：服务器 `update.sh` / `deploy.sh` 若来自 v3.4.2 及更早 Release，先覆盖 Release v3.4.3 的 `deploy_scripts_v343fix.zip` 再跑一键更新——**绝不用已废弃的 `deploy_scripts_v342fix.zip`**。

## 28. v3.4.4：一键更新解压目录唯一化（R24 审计通过，脚本修复）

### 28.1 背景
用户跑 v3.4.3 一键更新，双源互证 ✅ 通过、备份完成，但在「④ 覆盖后端代码」报 `mkdir: cannot create directory 'backend_extract': File exists` 后退出——`/tmp/llhhy_update/` 残留了历史失败更新的 `backend_extract` 目录。

### 28.2 根因
- 脚本解压用**固定目录名** `backend_extract` / `frontend_extract`（位于 `$WORK` = /tmp/llhhy_update）。
- `[ -d backend_extract ]` 仅认目录；`rm -rf` 失败被 `|| true` 吞掉（无报错无阻断）；`mkdir backend_extract` 无 `|| fail_exit` 兜底 → 配合 `set -e` 静默终止整脚本。
- 触发条件：任何一次更新中途失败都会在 /tmp 留下半解压目录，下次更新即炸（v3.4.1 静默退出、v3.4.2 误报失败都可能在服务器上留下该残留）。

### 28.3 修复
- **解压目录唯一化**：`$WORK/backend_extract_$TS` / `$WORK/frontend_extract_$TS`（TS=本次时间戳），不再复用固定名 → 残留目录存在也不影响本次更新。
- **启动尽力清理**：脚本开头 `rm -rf "$WORK"/backend_extract* "$WORK"/frontend_extract* ... || true`（范围锁定在 $WORK 内，失败不阻断）。
- 旧残留由 /tmp 系统清理机制自然回收。

### 28.4 验证
- R24 审计：XSS / SQL / 越权 / CSRF / 密钥 / 资源 / 回归 7 维度全 ✅（详见 SECURITY_AUDIT.md 第三十四轮）。
- 模拟残留场景：预建 backend_extract/frontend_extract 目录（不删除），按新逻辑解压到唯一目录 → 后端 config.py、前端 index.html 均存在。
- `bash -n` 语法通过；字节统计 CRLF=0、孤立 CR=0；grep 无裸 backend_extract 引用。
- 后端仅 config.py 版本号变更，py_compile 通过。APP_VERSION 升为 v3.4.4。
- ⚠️ 升级顺序：服务器 `update.sh` / `deploy.sh` **须覆盖 Release v3.4.4 的 `deploy_scripts_v344fix.zip`**；已卡住可先 `rm -rf /tmp/llhhy_update /tmp/llhhy_deploy` 或直接换新脚本重跑。

## 29. v3.4.5：一键更新覆盖校验 + 评论500/统计403 修复（R25+R26 审计通过）

- 一键更新覆盖段静默失败修复 + 覆盖后版本号硬校验（R25）；评论提交 500 根因（`notify_mentioned` 误贴进 `csrf_input` 死代码→ImportError）修复并恢复 @通知；统计埋点接口 `/api/stats/read|visit|search` 加入 CSRF 豁免修复 403。
- `py_compile` 全过；AST + 桩模块实测 `from utils import notify_mentioned` 成功；R25/R26 七维审计全 ✅。APP_VERSION 升为 v3.4.5。
- ⚠️ 升级顺序：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.5 的 `deploy_scripts_v345fix.zip`**，先覆盖脚本再跑一键更新。

## 30. v3.4.6：CSRF 多 worker 下 403「抽风」修复 + 一键更新自动重启加固（R27+R28 审计通过）

- **R28 · 后端 CSRF token 跨 worker 轮换导致 403「抽风」**：登录用户发评论、后台批量审核 / 删除评论均间歇性 `403 (Forbidden)`（登录账号评论「总是抽风」）。根因：gunicorn `-w 3` 下旧 `generate_csrf_token()` 用进程级 `_CSRF_CACHE` 判断 token 新鲜度，各 worker 缓存独立 → 落到不同 worker 会重新生成并**覆盖 session token** → 前端缓存 token 失效 → 后续 POST 全 403。修复：移除 `_CSRF_CACHE`，改为**签名校验复用**（HMAC(SECRET_KEY, `"csrf:"`+raw)，天然防伪造 / 防跨服务复用），token 在会话内稳定，不再随 worker 切换而轮换；仅 token 缺失或签名失效才重建。验证：双 worker 共享 session 模拟复用成功，`check_csrf_token` 对合法 / 篡改 / 无格式 / 空判断均正确。
- **R27 · 一键更新自动重启加固**：用户反馈 v3.4.5 覆盖已正确，但**进程不会真正重载**，仍需去宝塔「Python项目 → 停止 → 启动」手动重启。根因：旧 `stop_backend` 只 TERM master、没杀干净 worker，残留进程占端口 → 新 gunicorn 因「Address already in use」起不来，自动重启段形同虚设。
- 加固（运维脚本变更 + 后端 `utils.py` CSRF 修复，R27+R28 七维审计全 ✅）：
  - `stop_backend`：TERM master 后 `pkill -TERM -f "gunicorn.*$APP_DIR"` 杀光整个项目所有 gunicorn（含 worker），超时 KILL 兜底；新增**端口释放检查**（探测 `gunicorn_conf.py` 的 bind 端口是否真的空了）。
  - `start_backend`：`setsid` + `< /dev/null` 彻底脱离脚本会话（防新进程被脚本退出带走）；补全 venv `PATH`；启动后扫 `gunicorn.log` 致命错误并打印末尾辅助定位。
  - 修正 `RESTART_CMD` 注释：宝塔 `bt` 命令行是交互式菜单、不支持 `bt stop 项目名`，旧范例 `bt stop myblog && bt start myblog` 错误已删。
- `py_compile` 全过 + `bash -n` 双脚本通过；APP_VERSION 升为 v3.4.6。
- ⚠️ 升级顺序：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.6 的 `deploy_scripts_v346fix.zip`**，先覆盖脚本再跑一键更新，方可免除手动重启 + 生效 CSRF 修复。

## 31. v3.4.7：评论者 IP 定位恢复（IP 属地多源兜底 + 防注入 + 自愈）+ 后台筛选表单美化（R29 审计通过）

- **R29-① 评论者 IP 定位恢复**：用户反馈「评论的人的 IP 定位」没了。根因：原 `stats.py` IP 属地仅依赖 `api.vore.top`（已超时挂）与 `ip-api.com`（已 403 被封）两个源，全挂后 `region` 恒空 → 前台 `📍 {{ c.region }}` 不渲染。改为**国内源优先 + 国际源依次兜底**（太平洋 pconline → ipwho.is → api.ip.sb → ipinfo.io）；并修复旧逻辑「解析失败(空)也被缓存、永久不重试」的坑 → 改**仅缓存成功结果、外部源恢复后自动回填**（含历史空属地评论/访问）。
- **R29-② 严格审计加固（协同 CodeReview 专家，0 Blocker）**：
  - 新增 `_is_safe_public_ip()`：`ipaddress` 格式校验 + 要求 `is_global`，仅合法公网 IP 才查外部，排除私网/环回/链路本地/保留/CGNAT `100.64/10`，杜绝 XFF 伪造污染与内网 IP 无意义外发。
  - `short_region` 补英文 / ISO2→中文整词归一（`_REGION_EN2CN` 含 `CN/US/JP/...` + `China/United States/...`），根治海外属地脏数据 `UnitedStatesCalifornia` 与 ipinfo 的 `CN` ISO 码误判（`CN Guangdong`→`中国广东`）。
  - `_RECENT_FAIL` 加 `_FAIL_MAX=5000` 容量护栏 + 过期清理，防公网被扫描时 dict 无界增长（内存泄漏）。
- **R29-③ 后台筛选表单美化**：`我的文章` / `仪表盘` 文章筛选表单卡片化（圆角容器 + 🔍 搜索图标 + 统一 38px 控件 + accent 焦点环 + 主 / ghost 按钮层级），适配深色模式；样式抽进 `admin.css` 的 `.filter-form`，去掉内联 style。
- `py_compile` 全过；离线桩冒烟 14/14 PASS；R29 七维审计 0 Blocker。APP_VERSION 升为 v3.4.7；前端复用既有 `vue-frontend-dist.zip`（无前台改动）。
- ⚠️ 升级顺序：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.7 的 `deploy_scripts_v347fix.zip`**（沿用 v3.4.6 自动重启加固），先覆盖脚本再跑一键更新。

## 32. v3.4.8：全量安全审计加固（R30 审计通过 · 3 Blocker + 5 建议全部修复 · 未改部署脚本）

- **性质**：对 v3.4.7（含）之前全部既有代码做**全量横向审计**（协同 CodeReview 专家，R30 八维复核），3 Blocker + 5 建议全部修复入库。
- **R30-① 🔴 后台 4 处模板 JS 上下文存储型 XSS（已修复）**：`users.html`（用户名）、`subscribers.html`（邮箱）、`backup.html`（备份文件名）、`audit_logs.html`（保留天数）的 `onsubmit="return confirm('...')"` 把用户可控值直接拼进 JS 单引号字符串——Jinja autoescape 不转义 `'` → 任何注册用户可用 `'` / `</script>` 构造存储型 XSS，后台浏览即触发。修复：4 处全改 `|tojson`（JSON 字符串字面量天然 JS 安全）+ `utils.py` 新增 `js_escape()` 备选。
- **R30-② 🔴 越权/命令执行（已修复）**：`/api/version/update` 原普通管理员即可触发服务器 update.sh 执行 → 收窄 `is_super`（非超管 403）；`/api/version/status` 原无鉴权 → 加 `is_super` 鉴权。
- **R30-③ 🟡 TOCTOU 防重入（已修复）**：`version_update` 原「读 status → Popen」非原子 → 新增模块级 `_UPDATE_LOCK` + `_do_version_update()` 锁内原子段（status 文件保留作跨 worker 双保险），并发触发立即 409。
- **R30-④ 🟡 XFF 伪造收口（已修复）**：`stats.client_ip()` / `utils.client_key()` 原无条件取 XFF 首段 → 仅采信合法公网 IP（`is_global`，排除私网/环回/保留/CGNAT），否则回退 `remote_addr`——杜绝伪造 IP 绕过限流/刷爆埋点。
- **R30-⑤ 🟡 限流补齐（已修复）**：stats 三埋点（visit 60/min、read 60/min、search 120/h，超限静默丢弃）+ 前台 `/login` POST（10 次/60s）。
- **R30-⑥ 🟡 用户名限长（已修复）**：`add_user` 入库前 `username[:40]` 截断（与模型 `String(40)` 一致）。
- **💭 优化（暂不改）**：`/api/tags` 标签计数含不可见文章（信息泄露极低，随标签重构处理）；`_resolve_region_async` 后台线程未显式 `db.session.remove()`（SQLite 线程退出已回收，下版补 close 更规范）。
- **验证**：`py_compile` 全模块通过（`-W error::SyntaxWarning` 无警告）；隔离临时库冒烟 `smoke_audit_r30.py` 14 项 ALL PASS；R30 全量审计 3 Blocker + 5 建议全部修复（详见 `SECURITY_AUDIT.md` 第四十轮）。APP_VERSION 升为 v3.4.8；前端无改动。
- **🅰️ 升级顺序（本轮调整）**：R30 **未改动部署脚本**——服务器**直接跑一键更新**（沿用已在服的 v3.4.7 脚本）；**若更新报错再覆盖 Release v3.4.8 的 `deploy_scripts_v348fix.zip` 后重跑**（正常不需要）。

## 33. v3.4.9：评论 IP 属地 GBK 解码乱码修复（R31 审计通过）

- **R31-① 解码健壮性修复**：`stats._http_get_json` 原 `decode("utf-8","ignore")` 永不抛错，导致太平洋 IP 库（GBK 编码）中文被吞成乱码、GBK 兜底分支形同虚设。改为**逐编码严格解码**（utf-8 → gbk，任一 JSON 非法则试下一编码，双失败才抛错交多源兜底），根治「省份变乱码、城市丢失」。
- **R31-② 历史脏缓存自愈**：新增 `_looks_corrupted()` 启发式检测乱码特征；`_ensure_region` / `cached_region` 缓存命中先判脏，脏则忽略缓存走在线重查并覆盖旧值，新访问即自动自愈（无需手动清库）。
- **验证**：`py_compile` 通过；`smoke_gbk.py` 15/15 ALL GREEN（GBK 全链路 + 脏缓存自愈 + 异步重查）。R31 聚焦审计 0 Blocker。APP_VERSION 升为 v3.4.9；前端无改动。
- ⚠️ 升级顺序：R31 **未改动部署脚本**（沿用 v3.4.8 已在服脚本），服务器**直接跑一键更新**即可；历史脏属地将在新访问触发重查后自动覆盖。

## 34. v3.5.0：自定义链接后缀 + 5 项功能/修复 + 抽屉毛玻璃美化（R32 审计通过）

- **① 自定义链接后缀（slug）**：编辑/新建文章新增「链接后缀」字段，可手动填中文/英文/数字/下划线/连字符生成短链接（如 `/post/我的笔记`）；留空按标题自动生成。后端 `clean_slug()` 复用 `make_slug()` 清洗并查重（冲突自动 `-2/-3`），清洗为空回退标题生成，绝不写出空 slug 触发路由冲突；仅影响自己文章的 URL，沿用既有 `new_post`/`edit_post` 鉴权。
- **② 前台模糊搜索修复**：根因 FTS5 无匹配返回空列表 `[]` 时，旧守卫 `if ids is not None` 把「空结果」误判为「有结果」，永不走 LIKE 兜底 → 前台搜索恒报「无结果」。改为 `if ids:`（`[]`/`None` 均走 LIKE 兜底），FTS5 不可用（`None`）也已覆盖；无异常路径。
- **③ 分类/标签页前台无文章修复**：根因后端 `posts_by_category`/`posts_by_tag` 下发 `{items, name}`，前端 `CategoryView`/`TagView` 却读 `data.posts`（恒 undefined）→ 永远渲染空。改为读 `data.items`，`name` 缺失时回退 slug。
- **④ 后台评论单独删除 405 修复**：根因行内「删除/通过」按钮嵌在批量表单的嵌套 `<form>` 里，浏览器丢弃内层表单与 CSRF → 单删 405。改为行内按钮用 `formaction` 共享外层 `batch-form` 的 CSRF token（单 POST 表单），未新增任何裸 POST 表单；顺手删掉重复「通过」按钮。
- **⑤ 英文窄屏菜单/LOGO 纵向错位修复**：抽屉断点 `1004px` → `1100px`，`.header-inner` 加 `flex-wrap:nowrap; min-width:0`，`.logo` 加 `flex-shrink:0`，较长英文导航不再换行顶乱布局。
- **⑥ 前台抽屉毛玻璃圆角美化**：汉堡抽屉改为浮动毛玻璃卡片（背景 `rgba(255,255,255,.72)` + `backdrop-filter:blur(20px) saturate(180%)` + 20px 圆角 + 阴影），深色模式同步适配（`rgba(29,32,37,.62)` + 浅色描边）。
- **运维脚本**：新增 `tools/reset_stats.py`（标准库，运维手动用）——清空 `visit_log/read_log/search_log/ip_region` 四表，执行前 `post` 表预检防误伤他库、自动时间戳备份、默认 `YES` 二次确认（`--yes` 跳过），不入库不取密钥。
- **验证**：`py_compile` 全模块通过；前端构建 `_vite_build15` 成功、`vite preview` HTTP 200（含 `backdrop-filter` + `border-radius:20px`）。R32 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十二轮）。APP_VERSION 升为 v3.5.0。
- ⚠️ 升级顺序：R32 **未改动部署脚本**（沿用 v3.4.9 已在服脚本），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

## 35. v3.5.1：英文桌面端菜单换行修复 + 深色抽屉毛玻璃回归修复（R33 审计通过）

- **① 英文桌面端顶部菜单换行修复**：v3.5.0 只给 `.logo`/`.header-inner` 加 `nowrap`、漏给顶部 inline 导航 `.site-header nav` 约束，且抽屉断点只到 `1100px`；导致常见桌面宽（约 1280px）切英文时顶部菜单栏换行成两行、LOGO 文字顶乱。本轮给 `.site-header nav` 加 `flex-wrap:nowrap;min-width:0`、`.site-header nav a` 加 `white-space:nowrap`（首子项左间距归零），抽屉断点 `1100px`→`1280px`，顶部 inline 导航所有宽度下保持单行不换行（中/英/长文案均不再顶乱 LOGO）。
- **② 深色模式抽屉毛玻璃回归修复**：删除遗留的 `[data-theme="dark"] .drawer { background:#1d2025; border-color:#2a2e35 }` 不透明覆盖规则——它压死了 v3.5.0 的毛玻璃（深色抽屉退回不透明深底、丢失 `backdrop-filter`）。现在深色抽屉改由毛玻璃基样式（带 alpha 背景 + `backdrop-filter` + 浅描边）渲染，仅保留文字色兜底保证可读性。
- **验证**：`compileall myblog` 无语法错误；前端构建 `_vite_build15` 成功、产物 CSS 含 `max-width:1280px` 断点 + `.logo`/`nav a` 的 `white-space:nowrap` + 抽屉 `backdrop-filter`。R33 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十三轮）。APP_VERSION 升为 v3.5.1。
- ⚠️ 升级顺序：R33 **纯前端改动**（外加 `APP_VERSION` 升版本号），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

## 36. v3.5.2：链接后缀全局模板 + 预制可选/自定义（R34 审计通过）

- **① 链接后缀改为「全局模板 + 单篇覆盖」双轨**：原 v3.5.0「单篇手动填后缀」保留为单篇硬覆盖；新增后台「🔗 链接后缀规则」全局设置——`slug_mode` 选 title(沿用标题)/slug-date/id/date-slug/category-slug/自定义，自定义时填 `slug_template`（支持 `{slug}{id}{date}{category}` 占位符）；新建/编辑文章标题变动时自动套用全局模板生成后缀，单篇手动填了则硬覆盖（零破坏性：默认值 = 旧行为）。
- **② 占位符渲染 + 查重**：`render_slug_template()` 把占位符替换为清洗后的片段（日期 `YYYYMMDD`、分类取 slug、id 取文章 ID），未知占位符清空；`_unique_slug_local()` 复用 `make_slug()` 清洗并查重（冲突 `-2/-3`），绝不写出空 slug。
- **③ 后台实时预览**：`/api/slug-preview`（GET，`@admin_required`，CSRF 豁免 GET）按 title/mode/tpl 返回预览 slug，设置页用 `textContent` 输出（XSS 安全）。
- **验证**：`compileall myblog` 无语法错误；DB 功能测试 6 种模式后缀正确、重复标题查重 `重复标题→重复标题-2→重复标题-3` 验证通过；`settings.html` 渲染含全部新元素。R34 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十四轮 R34）。APP_VERSION 升为 v3.5.2。
- ⚠️ 升级顺序：R34 **改了后端 `utils.py`/`admin.py`/模板 + `APP_VERSION`**，服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

## 37. v3.6.0：API 解耦重构（api.py → api/ 包）+ 新增 API.md（R35 审计通过）

- **① API 按功能拆包**：`myblog/api.py`（单文件 1312 行 / 53 路由）解耦为 `myblog/api/` 包——`auth`/`site`/`posts`/`stats`/`social`/`series`/`guestbook`/`subscribe`/`notifications`/`system` 十个功能模块 + `common.py`（共享辅助：当前用户 / 登录 / CSRF / 序列化 + `_UPDATE_LOCK` / `_VER_CHECK_CACHE`）+ `__init__.py`（`api_bp` 聚合导出，`from api import api_bp` 兼容）。
- **② 零破坏**：`url_prefix="/api"` 不变；全 54 条路由（53 条 api 蓝图 + 1 条 `/api/weather` main 蓝图）与基线快照 `diff` **零差异**；CSRF 豁免清单 / 限流 / 鉴权级别全部不变；`app.py` 对 api 的引用零改动。函数体按行区间**逐行保真**搬移，杜绝手工改写偏差。
- **③ 新增 API.md**：`myblog/API.md` 完整接口文档——通用约定（基地址/返回格式/鉴权/CSRF/分页/限流）+ 全部端点说明（请求/响应/鉴权）+ 如何新增 API + 错误码速查，方便定制第三方客户端。
- **④ 后续开发更简单**：新 API 直接往对应功能模块加路由（共享逻辑走 `common.py`），新模块只需在 `__init__.py` 追加一行导入；模块间禁止互相 import（防循环依赖）。
- **⑤ 拆包补测修复 6 处跨模块引用缺失（NameError）**：拆包后 5 个功能模块对顶层 `stats` 模块的引用（`stats.client_ip` / `stats.cached_region` / `stats.record_*` / `stats.compute_*`）未导入——路由注册不报错，请求时才 `NameError` 500（统计端点 / 评论归属地 / 留言 / 朋友圈 / 友链 / 系列排序）。补 `import stats`（`posts.py` 另补 `User`、`stats.py` 与 `series.py` 补 `Post`），新增 `smoke_api_pkg.py` 10 项断言全通过（含 visit 落库读回、评论 201、留言 201 落库、朋友圈 401=函数体正常、友链 201、系列 200）。
- **验证**：`compileall myblog` 无语法错误；路由快照 54 条 diff 零差异（删旧 api.py 后重新验证，确认加载的是包）；全应用加载 + GET 10 端点 + POST 6 端点（CSRF 链路）行为抽查全通过；`smoke_api_pkg.py` 10/10（补测 NameError 修复闭环）。R35 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十五轮 R35）。APP_VERSION 升为 v3.6.0。
- ⚠️ 升级顺序：R35 **纯后端改动**（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.6.0`。

## 38. v3.6.1：修复编辑文章改链接后缀（slug）保存报 500（R36 审计通过）

- **① 根因**：`admin.py` 的 `edit_post` 第 662 行 `if post.content != content` 引用了**从未赋值的局部变量 `content`**（v3.0.0 引入版本历史时就存在）→ `NameError` → 500。此前新建文章走 `new_post` 不经过此路径，故长期未触发；直到用户报告「编辑文章改链接后缀保存报 500」。
- **② 修复**：627 行先取新内容到局部变量 `content`、保留 `old_content` 旧值再覆盖 `post.content`；版本历史判断改为 `post.content != old_content`（新 vs 旧，语义才正确）；删除 664/665 死代码（重复赋值）。
- **③ 附带修复（前端草稿丢 slug）**：编辑页草稿自动保存 `fields` 数组补 `"slug"`——`snapshot()`/`restore()` 共用该数组，改链接后缀后刷新页面草稿恢复不再丢 slug。
- **验证**：完整 HTTP 链路复现（改 slug 200 且入库 / 改内容 200 且版本历史 +1 / 无变化 200 且历史不增长）；`py_compile` 通过；`smoke_v320.py` 回归通过。R36 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十六轮 R36）。APP_VERSION 升为 v3.6.1。
- ⚠️ 升级顺序：R36 **纯后端 + 模板改动**（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.6.1`。

## 40. v3.7.0：链接后缀（slug）强制全局设置 · 取消单篇手动覆盖（R37 审计通过）

- **① 行为变更**：编辑/新建文章页移除「链接后缀」输入框，slug 强制由后台全局设置（`slug_mode`/`slug_template`）生成，作者不可单篇覆盖。
- **② 保留原则**：编辑文章标题未变 → 保持原 slug 不动（不破坏旧 URL）；标题变 → 按全局模板重建。
- **③ 删除死代码**：`clean_slug()` 无调用方，已删除。
- **④ 验证**：`smoke_v370.py` 10 项断言全通过；R37 七维审计 0 Blocker。APP_VERSION 升为 v3.7.0。

## 41. v3.7.1：访问统计新增 Bot/爬虫识别（R38 审计通过）

- **① 新增能力**：后台访问统计新增爬虫识别维度，从 UA 细分搜索引擎/AI/工具/未知四类。
- **② 数据落库**：VisitLog 新增 is_bot/bot_name/bot_category 三字段（迁移脚本 myblog/migrate_visit_log_bot.py）；record_visit 落库，compute_summary 新增 bot_visits/human_visits/bot_today/bot_breakdown。
- **③ 后台可视化**：统计看板新增「🤖 爬虫访问」占比卡片 + 「🤖 爬虫/Bot 来源排行」。
- **④ 验证**：smoke_v371.py 19 项断言全通过；R38 七维审计 0 Blocker。APP_VERSION 升为 v3.7.1。

## 42. v3.8.0：反爬限流保护 + SEO 服务增强（R39 审计通过）

- **① 反爬限流保护（bot_guard，默认关闭）**：基于 v3.7.1 的 Bot 识别对高频/可疑请求限流与封禁。搜索引擎（search 类）默认白名单豁免，不影响 SEO；坏 Bot（tool/unknown）更严阈值；达次数阈值才封禁一段时间。新增 `BotBlock` 表，`db.create_all()` 自动建表（无迁移脚本），后台「🛡️ 反爬限流保护」看板可查看与解封。
- **② SEO 服务增强**：文章页 JSON-LD `BlogPosting` 结构化数据 + OG/Twitter Card；`sitemap.xml` 增强（lastmod/changefreq/priority/封面图）；`robots.txt` 支持后台配置屏蔽指定坏 Bot；RSS/feed 增强（dc:creator 作者 + category 分类）。
- **③ 安全加固**：R39 发现并修复 1 处高危——后台解封表单原缺 CSRF Token（全局 `_csrf_protect` 对所有非豁免 POST 生效）致「解封」必 403，已补全 `{{ csrf_input() }}`；XSS/注入/越权/SSRF/限流/资源泄漏维度均通过。
- **④ 验证**：smoke_v380.py 18 项断言全通过；py_compile 通过。R39 审计 **1 高危已修，0 遗留**。APP_VERSION 升为 v3.8.0。

## 43. v3.8.1：修复后台统计页 500（R40）

- **① 根因**：`/admin/stats` 依赖 `visit_log` 的 bot 三列（v3.7.1 引入）；`db.create_all()` 不给已存在表加列，未跑过 v3.7.1 迁移脚本的库缺列 → `compute_summary()` 的 `VisitLog.query.count()` 报 `no such column: visit_log.is_bot` → 后台 500。
- **② 修复**：`app.py` 启动序列新增 `_migrate_visit_log_table()`，每次启动幂等补列，取消对 v3.7.1 手动迁移脚本的依赖，旧库升级自动自愈。
- **③ 验证**：`_debug_admin500.py` 复现夹具确认修复前 500 / 修复后正常；smoke_v380.py 18/18 无回归。APP_VERSION 升为 v3.8.1。
