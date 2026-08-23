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
