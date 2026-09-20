# myblog · Flask 后端

llhhy-blog 的后端：Flask + SQLite，服务端渲染前台 + `/api/*` JSON 接口 + Jinja2 管理后台。

- 当前版本：**v3.18.8**
- **v3.18.8：修复 v3.18.7 上线实测发现的验签顺序缺陷**——`$WORK`（`/tmp/llhhy_update`）跨轮复用且原先只清解压目录，导致上一轮遗留的 `sha256.txt` 被拿来与本轮新的 `sha256.txt.sig` 配对比对 → 必然验签失败（v3.18.7 首次上线即 BAD；站点未受影响，fail-closed 在覆盖代码前就拒绝了安装）。修复：验签函数内部**先清旧清单再自行下载两者**（自包含），`$WORK` 准备阶段显式清清单与 zip，并新增契约测试钉死。验证 **126 passed** + 服务器端到端实跑全绿。
- **v3.18.7：更新链 fail-closed + Ed25519 发布物签名**——`package.py` 打包后对 `sha256.txt` 做 Ed25519 分离签名（新资产 `sha256.txt.sig`，首次运行自动生成密钥对到 `~/.workbuddy/llhhy_release_key`）；`update.sh`/`deploy.sh` **内置验签公钥**（`BUILTIN_RELEASE_PUBKEY`，可被 `RELEASE_PUBKEY` 覆盖）→ 任何人 clone 部署开箱即可获得签名保护。7 处 fail-open 全转 fail-closed（签名缺失/验签失败/清单查不到文件/注释双源互证失败/无 python3 一律终止），**不再自动兜底第三方镜像**（只认显式 `GH_MIRROR`）；新增版本单调性（默认拒降级，`ALLOW_DOWNGRADE=1` 放行）与 `ALLOW_UNSIGNED=1` 显式逃生舱。`deploy.sh` 收敛为 `update.sh` 的薄封装（历史上是副本且校验更弱）。`verify_package_checksums.py` 增加**双源互证 ③**（用 update.sh 里读出的同一公钥验签）。验证 **125 passed** + 反向实测 20/20。
- **v3.18.6：退役公共 SSR（单前端）**——生产 Nginx 只反代 `/api/` `/admin` `/static/` `/mcp*` 与 `feed.xml`/`sitemap.xml`/`robots.txt`/`feed/comments`，其余由 Vue SPA 兜底，故 `routes.py` 中 8 个页面级 SSR 路由（`/`、`/post/<slug>`、`/category/<slug>`、`/tag/<slug>`、`/search`、`/about`、`/links`、`/archive`）在生产从未被访问 → **退役为 410 Gone** 并**删除 7 个对应模板**（`myblog/templates/` 顶层仅剩 `base.html`/`login.html`/`register.html`/错误页 5 个）。**endpoint 名一律保留**（`base.html` 的 `url_for` 依赖它们，删路由会让登录页 `BuildError`）；`/login` `/register` `/logout` 仍为 SSR，`/post/<slug>/comment`、`/post/<slug>/like` 两个 POST 入口保留。验证 119 passed。
- **文档口径更正（v3.18.5 · 依据第三方独立审计 §10）**：① 「后台表格手机端可浏览全文」**不成立**——卡片化依赖 `td[data-label]`，22 个表格模板只有 2 个写了（补齐见 ROADMAP §5.8）；② 「硬编码颜色已统一替换为 token」**部分不成立**——`admin.css` 与 `global.css` 各残留约 230~250 处裸 hex，两份 `tokens.css` 为手工复制；③ 「全站时间统一北京时间」在本版**已真正落地**（7 处 Jinja 模板改用 `bj` 过滤器、`/api/games` 改用 `fmt_bj`）；④ 「文章页动态 OG」实现于 Vue 客户端，当前 Nginx 下服务端 JSON-LD/OG 抓不到流量，对国内 SEO 近似无效；⑤ 「14 套 OKLCH 主题保证对比可读」不等价于 WCAG —— `derive_dark` 只钳 L，无亮度校验环。
- **v3.18.5：第三方独立审计 P0 批次（8 项真实缺陷）**——① 补 `redirect` 导入（会话失效时三处 `redirect` 触发 `NameError` → 500），统一 `redirect(safe_redirect(url_for("main.login", next=…)))`；② 前台注册/登录补写 `session_version`（原先缺失 → 改过密码的用户前台登录后下一请求即失效）；③ `flask seed` 移到 `return app` 之前（原先 CLI 注册是死代码）；④ `/api/review/annual` 改走 `visible_posts_query()`（原先自建过滤器漏 `in_trash`/`is_private` → 匿名枚举隐私文章标题/slug）；⑤ `/api/ai/summary/<slug>` 加可见性过滤 + 后台「AI 摘要」页提权 `@super_required`；⑥ bleach 白名单补表格标签并 `_RENDER_VERSION` 2→3（原先 Markdown 表格被静默剥空）；⑦ 新增 `400/403/404/405/422/500` 错误处理器 + `404/403/500/error` 模板（原先 `first_or_404` 对 JSON 客户端返回 HTML）；⑧ `tests/conftest.py` 改用隔离临时库 + `create_app(enable_scheduler=False)`（原先 pytest 直接在 `myblog/data/blog.db` 上增删数据）。附带：审计日志 IP 走 `get_client_ip()`（原取 XFF 最左段可伪造）、`?category_id=abc` 不再 500、`/api/stats/dashboard` 不再回显 `str(e)`、删除无用的 `ADMIN_HASH` 与死赋值。验证 **112 passed**（+13 条回归），开发库 sha256/mtime 零变化。
- **v3.18.1：超长文件拆分（纯重构，公共 API 与路由零变更）**——`utils.py`（784 行）拆成 `utils/` 包（timeutil / render / net / slug / text / security / settings / web；`__init__.py` 全量重导出，**27 个导入点零改动**）；`admin/posts.py`（852 行 / 26 路由）拆成 post_editor / post_manage / post_trash / post_history / taxonomy 五个模块（**同一 `admin_bp`、函数名与 URL 不变**）。验证：逐名 `ast.dump` 等价性（44/44 + 31/31 名、0 结构差异）+ endpoint 守恒（26 条全在、99 处 `url_for` 全可解析）+ `113 passed`。最大文件从 852/784 降到 448/294 行。
- **v3.18.4：补齐核心 i18n**——导航 `回顾` / `社交` / `游戏` 三项接入词典（原先硬编码 → 导航不再中英混排）；抽屉与顶栏（后台 / 写文章 / 退出 / 登录 / 注册 / 主题）、通知面板、回到顶部与各 `aria-label` 全部接入；消除 `admin` / `write` / `search_placeholder` 3 个死键；修正语言按钮 tooltip 错绑（`t('theme')` → `t('switch_lang')`）。词典 **17 → 31 键**（实际使用 = 31，无死键 / 缺失）。范围限导航与公共部件，内容页文案仍中文。验证 `99 passed`。
- **v3.18.3：移除内置插件 `page_translate` + 恢复核心中英切换**——删除 `myblog/plugins/page_translate/` 与远程组件 `myblog/static/plugins/page_translate/widget.js`，`ENABLED_PLUGINS` 默认值恢复为空；插件框架（加载器 / 失败隔离 / 事件总线 / 后台「🧩 插件管理」/ 前端槽位）全部保留。同时 v3.18.0 移除的核心 i18n **全量恢复**（`store.js` 的 `I18N`/`t()`/`setLang`/`initLang`/`state.lang` + `App.vue` 语言按钮 + `global.css` 的 `.lang-toggle`，逐字节还原 v3.17.14）。验证 `99 passed`。
- **v3.18.0：全站翻译（插件形态）+ 移除核心中英切换**（⚠️ 该插件已在 v3.18.3 移除）——新增内置插件 `page_translate`（`myblog/plugins/page_translate/__init__.py` + 远程组件 `myblog/static/plugins/page_translate/widget.js`）：前台左下角浮层「翻译整页 / 显示原文」，整页翻译（导航 + 界面 + **文章正文**）；引擎**浏览器内置 Translator 优先、站点大模型兜底**（复用 `games_llm_*` OpenAI 兼容配置，后端 `POST /api/plugin/page_translate/translate`，CSRF + 双层限流 + 目标语言白名单 + 条数/字符上限）；`GET /api/plugin/page_translate/config` 下发源/目标语言与 LLM 可用性；译文 localStorage 缓存 + WeakMap 原文还原 + MutationObserver 适配 SPA。**核心移除** `store.js` 的 `I18N`/`t()`/`setLang`/`initLang`/`state.lang` 与 `App.vue` 语言按钮（导航文案固定中文）。`ENABLED_PLUGINS` 默认值改为 `page_translate`。
- **v3.15.1：响应式基座重构**（Grid minmax(0,1fr)/流式字阶/防溢出基线，前后台同步）+ 微信分享卡 OG 收尾；内置游戏调整（撤《就是开车》）。
- **v3.15.0：游戏平台 + 标签治理 + 分享卡片**——`myblog/builtin_games/` 官方内置游戏两枚（纯静态），`myblog/tools/seed_games.py` 一键收录；后台「🎮 游戏收录」（上传 zip → `games_safety` 安全解包/白名单/静态扫描 → 审核；可选 OpenAI 兼容 LLM 代码审计，Key Fernet 加密）；公开 `/api/games` 与 `/api/game-files/…`（仅 approved + 沙箱响应头）；标签 `_sync_tags` 归一化去重 + 孤儿清理 + 后台一键整理；OG/分享 meta。**新表 `game` 启动自愈创建；无新环境变量**。
- 移动端适配（v3.10.6）：修复后台「统计」长标题与公开站「文档页」移动端长文本横向溢出穿模（窄屏统一换行而非挤压版心）。v3.11.0：引入 Flask-Migrate 基线迁移、运营驾驶舱二期（趋势区间切换 + 评论/新文量曲线 + CSV 导出）、CI 增前端构建校验与双源互证校验脚本。v3.11.1：修复后台侧边栏版本号未注入回归（裸「v」）+ 运营驾驶舱视觉升级（指标卡重做、趋势图加面积填充/网格/抗拉伸描边/悬浮高亮），纯前端无逻辑变更。v3.12.0：新增「💭 微动态」后台管理（列表检索/编辑/删除级联清评论/批量删除，写审计日志，无迁移）。**v3.12.1：UI 设计系统 token 纯度（铲除散点暗色）**——后台 `admin.css` 与前端 `global.css` 的散点硬编码色（hex/rgb）全替换为 `tokens.css` 语义 token，明暗主题像素级零色差；无逻辑变更、无 DB 迁移。v3.13.0：后台「🔌 MCP 服务」面板（内置 /mcp、/mcp-write 一键启停 + 外部 MCP 服务登记 + AI 脱敏接入指令，token Fernet 加密零明文落库，零新表）。v3.13.1：插件重载在应用已处理请求后崩溃的修复。**v3.14.0：写作后台大升级**——写作面板（Markdown 工具栏 / 分屏实时预览 / 云端自动保存 / 未发布稿免登录预览链接）+ 「📄 文章管理」独立页（管理员全站、筛选/排序/分页/批量）+ 就地新建分类/系列 + 「🖼️ 媒体库」+ 版本逐行对比 + 分类/系列改名 + 分类删除可先转移文章；修复图片上传必 500 的遗留 bug（v3.11.0 切片遗失 `_MAGIC_PATTERNS`）。纯后端改动、无 DB 迁移。
- **v3.16.0：主题中心 + 分享卡重做收尾 + 动态 OG/二维码**——后台「🎨 主题中心」：`myblog/themes.py`（OKLCH 感知色彩，14 套预设包，亮色单源 / 暗色自动推导）+ `myblog/api/theme.py`（`GET /api/theme` 公开 / `POST /api/theme` 仅超管 + 全局 CSRF）+ `admin/theme_center.py` + 模板（实时预览网格 + 自定义 JSON 导入/导出），`base.html` 新增导航；`api/site.py` 下发 `theme_pack/theme_tokens/theme_dark_tokens`，前台 `store.js`/`App.vue` 整体换肤；复用 `Setting` 表，**无 DB 迁移**。后端：`myblog/og_image.py`（Pillow 1200×630 分享卡 + 磁盘缓存 + 降级回退）、`myblog/api/og.py`（动态 OG 图 `/api/og/post/<slug>.png` + 站点二维码 `/api/qr` + 文章级 OG meta SSR）、`requirements.txt` 加 `segno`。前端：`SharePanel.vue` SVG 分享面板（微博/QQ/微信/X/Telegram/Facebook/LinkedIn）+ `PostView.vue` 图片灯箱 + 代码复制 + 阅读时长。安全见 `SECURITY_AUDIT.md` R69（0 遗留，自定义主题值未做颜色白名单为已记录低风险）。
- **v3.17.0：深色修复 + 动效/无障碍 + AVIF + 年度回顾 + AI 摘要**——修复前后台深色白条（`app.py` 拆 `theme_nav_css` 限定 `html:not([data-theme="dark"])`；`store.js` 不再写死 `--nav-bg`；SSR `style.css` 用 `var(--nav-bg)`）、主题包换肤 key 映射（`_`→`-`）、后台表格窄屏卡片化；前端 reduced-motion/骨架屏/Toast/路由过渡/滚动渐入/容器查询/Bento 概览/手势/彩蛋。后端：`maybe_convert_webp` 增 AVIF 旁路 + `utils.render_markdown` 升级 `<picture>`（`_RENDER_VERSION`→2）、新增 `api/review.py`（`/api/review/annual` 年度回顾 + 地域榜）、新增 `api/ai.py`（`/api/ai/summary/<slug>` GET 公开 / POST 仅超管，复用 `games_llm_*` 配置，结果存 Setting）。**无 DB 迁移、无新增依赖。**
- **v3.17.2：后台移动端系统性修复 + 打印优化 + 成就徽章**——`admin.css` 新增 ≤760px 规则组（表单控件窄屏占满并取消 `min-width`、写作面板分屏改单列、工具条/筛选换行、`pre/code` 横滚、容器宽度上限解除、媒体自适应），修掉「仪表盘已修但其他菜单仍溢出」；新增 `@media print` 打印样式（隐藏交互元素、正文全宽黑字白底、外链附 URL）；新增 `GET /api/milestones`（公开只读聚合，**无表结构变更**）提供 8 枚成就徽章 + 连续更新/开博天数，`/annual` 页展示。`admin.css` 为静态文件随后端包分发。
- **v3.17.4~9 修复与增强**：Bento 概览卡布局修复（`bento-tall` → 对角双宽卡）；归档时间线深色可读性（写死浅色改 token）；LLM Base 兼容完整端点（`_llm_chat` 与游戏审计自动剥离尾部 `/chat/completions`，游戏审计与 AI 摘要恢复可用）；**全站 7 处一键复制三层兜底**（新增 `lib/clipboard.js`、后台 `base.html` 注入 `window.__copyText`）；后台移动端补齐（`.stats-grid` 内联多列 `!important` 覆盖 + 通用 `[style*="grid-template-columns"]` 窄屏单列；`.stats-table` 横滚）；**后台「AI 摘要」独立管理页**（`admin/ai_summary.py`，生成/重新生成/编辑/清除/批量补齐 + 覆盖状态，提示词与 API 共用常量）+ 摘要默认完整展示；**社交账号墙独立成页 `/social`**（`lib/social.js` 20 平台图标/主题色/行为自动匹配，QQ/微信填号码点击复制、填图片展示二维码、邮箱补 mailto:）+ 主页「找到我」区块 + 导航入口 + 后台 20 平台预设下拉。
- **v3.17.3：评论表情回应 + 访客来源分析 + 访客地图**——新增 `api/reactions.py`（👍❤️😂🎉🤔👏，计数存 Setting KV `react_<cid>` **零表结构变更**，限流 40/分钟 + CSRF + 仅已审核评论；前端乐观更新 + localStorage 去重）；`visit_log` 新增 `referrer` 列（**仅存 origin**，防外链 query 隐私泄漏；`_migrate_visit_log_table` 启动自愈补列 + 幂等脚本 `migrate_visit_log_referrer.py` 备用）；`GET /api/stats/referrers`（排除 bot/本站）+ 统计页「来源 Top 10」卡；`GET /api/geo/visitors`（省级聚合，简称→全称映射）与 `/api/geo/china.json`（阿里 DataV 合规底图缓存 7 天）+ `/annual`「🗺️ 访客地图」（自绘墨卡托 SVG 省份热力，含港澳台及南海诸岛，失败降级地域榜）。VisitLog 加列经用户确认；表情回应零迁移。
- 时区：展示统一北京时间（UTC+8），存储仍为 UTC；配置见 `config.TIME_ZONE`（默认 `Asia/Shanghai`，固定不可经环境变量改，避免 UI 内部错位）。
- 根目录 README / 历史版本见仓库根 [README.md](../README.md) 与 [CHANGELOG.md](../CHANGELOG.md)

## 目录结构

```
myblog/
├── app.py          # 应用工厂（自动迁移 + FTS 初始化 + CLI + 首建超管）
├── models.py       # 数据模型（文章/评论/用户/系列/公告/留言/订阅者等）
│                   #   Post.content_html/content_hash = 正文渲染缓存（v3.9.1）
├── routes.py       # 前台页面 / 登录注册 / 评论 / 天气 / RSS
├── utils/          # 通用工具包（v3.18.1 由单文件 utils.py 拆出，公共 API 不变）：
│                   #   timeutil 时间 / render Markdown 渲染清洗 / net 限流与客户端 IP /
│                   #   slug / text 文本·UA / security 密码与 CSRF / settings / web
│                   #   兼容层：`from utils import X` 与 `utils.X` 全部照旧可用
├── admin/          # 后台管理包（v3.11.0 由 admin.py 拆出）：_helpers/auth/comments/
│                   #   settings/users/stats/media/friends/misc/moments/mcp_services
│                   #   moments.py = 微动态管理（v3.12.0）；mcp_services.py = MCP 服务面板（v3.13.0）
│                   #   post_*.py = 文章后台（v3.18.1 由 posts.py 拆分）：post_editor 写作面板 /
│                   #     post_manage 列表·批量·发布·置顶 / post_trash 回收站 /
│                   #     post_history 版本历史 / taxonomy 分类·标签·系列；media.py = 媒体库
├── api/            # JSON 接口（/api/*，按功能拆分，见 API.md）
├── mcp_diag.py     # 只读诊断 MCP 端点 /mcp（v3.10.0，见文末说明）
├── mcp_write.py    # 写能力 MCP 端点 /mcp-write（v3.12.2，默认草稿、fail-closed）
├── plugins/        # 插件系统 v3.9.0（<slug>/ 目录 + signals.py 事件总线）
│                   #   v3.10.0 起仓库不再内置插件，放目录 + 填 ENABLED_PLUGINS 即启用
├── fts.py          # SQLite FTS5 全文搜索（不可用时降级 LIKE）
├── stats.py        # 访问统计与 IP 属地解析
├── backup.py       # 数据备份与异地容灾（本地/OSS/SCP/WebDAV）
├── bot_guard.py    # 反爬限流（默认关闭）
├── security.py     # 安全响应头 / 图形验证码 / CSRF
├── config.py       # 配置（含 APP_VERSION）
├── migrations/     # Flask-Migrate / Alembic 迁移（v3.11.0 起；基线对齐 v3.10.6）
├── API.md          # 全部 /api/* 端点文档
├── SECURITY_AUDIT.md  # 安全审计报告
└── deploy_guide.md    # 宝塔部署手册
```

## 本地运行

```bash
python -m venv venv && pip install -r requirements.txt
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export ADMIN_PASSWORD=$(python -c "import secrets;print(secrets.token_hex(16))")
flask --app app init-db
python app.py            # http://127.0.0.1:5000
```

## 用户与权限

| 角色 | 权限 |
|---|---|
| `super` 超管 | 全部权限，含用户管理与站点设置；不可被删除或降级 |
| `admin` 管理员 | 管理内容（文章/分类/标签/评论/友链/统计），不能管用户与站点设置 |
| `user` 普通用户 | 登录、评论、发表文章（仅可编辑自己的） |

首次运行自动用 `ADMIN_USERNAME`（默认 `admin`）+ `ADMIN_PASSWORD` 创建超管。首次登录 `/admin` 会强制进入「设置管理员账号」页，改密后旧密码立即失效。

## 环境变量

**必填（缺失即拒绝启动）**

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | 会话签名密钥 |
| `ADMIN_PASSWORD` | 超管初始密码 |

**常用可选**

| 变量 | 默认 | 说明 |
|---|---|---|
| `SITE_URL` | — | 站点对外地址，RSS/sitemap 生成绝对链接用 |
| `DATABASE_URL` | `sqlite:///data/blog.db` | 可换 SQLite 路径或 Postgres/MySQL |
| `COOKIE_SECURE` | `true` | 本地 HTTP 开发设 `false` |
| `BLOG_OPEN_REGISTER` | `true` | 关闭公开注册设为 `false` |
| `CORS_ORIGIN` | 空 | 跨域白名单，逗号分隔 |
| `REDIS_URL` | — | 多 worker 全局限流 |
| `SESSION_IDLE_MINUTES` | `60` | 会话闲置超时，`0` 关闭 |
| `CAPTCHA_ENABLED` | `true` | 图形验证码 |
| `FEED_FETCH_TIMEOUT` | `8` | 友链 RSS 抓取 socket 超时（秒）；坏源超时只跳过、不卡死 worker |
| `UPDATE_HMAC_KEY` | — | 发布包 HMAC 签名 |

**插件系统（v3.9.0 起；v3.10.0 起不再内置插件）**

| 变量 | 默认 | 说明 |
|---|---|---|
| `ENABLED_PLUGINS` | 空 | 启用插件 slug 列表（v3.10.0 起默认为空 = 不加载任何插件） |
| `DISABLED_PLUGINS` | 空 | 紧急关停，优先级高于启用列表 |
| `PLUGINS_DIR` | `myblog/plugins` | 插件根目录 |

**只读诊断 MCP（v3.10.0）**

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCP_AUTH_TOKEN` | 空 | 认证令牌。**留空 = `/mcp` 整体关闭（401）**，不会裸奔 |
| `MCP_LOG_FILES` | 空 | 允许被读取的日志文件绝对路径，逗号分隔；留空则「最近错误日志」不可用 |
| `MCP_ALLOWED_ORIGINS` | 空 | 额外的合法 Origin 白名单（防 DNS 重绑定），一般留空 |

**MCP 服务管理面板（v3.13.0）**：后台「🔌 MCP 服务」（超管专属）——两个内置端点一键启停（停止 = 对外 404，即时生效无需重启）、外部 MCP 服务登记（token Fernet 加密落库、页面只显掩码）、每个服务一键生成「AI 脱敏接入指令」（脱敏版 / 完整版，完整版查看记审计）。**无新增环境变量**，数据走 Setting 表，开箱即用；手工配置口径见 [deploy_guide.md](deploy_guide.md)。

其他备份（`BACKUP_*`）、推送（`TELEGRAM_*` / `WECOM_WEBHOOK_URL`）、Webhook（`WH_DEPLOY_SECRET`）等变量见 [deploy_guide.md](deploy_guide.md)。密钥一律走环境变量，绝不落库。

## 正文渲染缓存与 WAL（v3.9.1）

**渲染缓存**：文章正文的 Markdown 渲染结果存在 `post.content_html`，指纹存 `content_hash`
（`sha256(渲染版本号 | 正文 | HTML)`）。唯一出口是 `utils.render_post_html(post)`：

- 命中指纹 → 直接返回缓存，**不再渲染**（1 万字符长文实测 `87ms → 2.7ms`）；
- 正文一改指纹即变 → 自动重新渲染，**保存文章无需手工清缓存**；
- HTML 本身也进指纹，缓存被意外改坏会自愈（重新渲染）；
- 写回用独立连接、撞锁 800ms 即放弃，任何失败都静默回退为「本次重算」，不影响正确性。

若将来调整 Markdown 扩展或 `clean_html()` 白名单，把 `utils._RENDER_VERSION` +1 即可让全部缓存一次性失效。

**SQLite WAL**：`app.py` 在每次建连时执行 `PRAGMA journal_mode=WAL` + `busy_timeout=5000` +
`synchronous=NORMAL`（PRAGMA 是连接级的，故挂 connect 事件；非 SQLite / `:memory:` 自动跳过）。
副作用与注意：

- `data/` 下会多出 `blog.db-wal`、`blog.db-shm` 两个文件，属**正常产物，请勿手动删除**；
- 备份**不能**直接 `cp blog.db`（会漏掉 WAL 中已提交的数据）——`backup.py` 已改用 sqlite3
  在线备份 API，`update.sh`/`deploy.sh` 改走 `sqlite3 .backup`，恢复后会自动清理 `-wal`/`-shm`；
- 部署后可在后台「运维诊断 → 🩺 全站体检 → 数据库健康」查看 `journal_mode` 是否为 `wal`。

## 常见问题

- **502**：gunicorn 未起来，看项目管理器状态与日志（端口冲突 / 依赖缺失最常见）。
- **后台无样式（纯文本）**：Nginx 缺 `location /static/` 反代，详见 deploy_guide.md。
- **更新后还是旧界面**：① `ls /www/wwwroot/*/data/blog.db` 确认真实运行目录；② 宝塔「停止 → 启动」（restart 不重载）；③ 看后台左下角版本号。
- **RSS/sitemap 是 localhost**：设 `SITE_URL=https://你的域名` 并重启。
- **写接口 403（CSRF）**：先 GET `/api/csrf` 取 token，再带 `X-CSRF-Token` 头提交。
- **搜索降级 LIKE**：服务器 SQLite 无 FTS5，功能正常但较慢。
- **`database is locked`**：v3.9.1 起已启用 WAL + `busy_timeout=5000`；若仍出现，检查 `data/` 目录
  是否可写（体检页 `journal_mode` 应为 `wal`）以及是否有外部进程长期持锁（如手工 sqlite3 会话）。
- **改了文章前台没变**：缓存按正文指纹自动失效，理论上不会残留；若手工改过数据库，
  可把该行 `content_html`/`content_hash` 置空，下次访问即重新渲染。
- **订阅者收不到邮件**：需在后台「📧 邮件设置」配置 SMTP（用授权码，非登录密码）。

## 部署

宝塔面板点按式教程见 [deploy_guide.md](deploy_guide.md)：后端用 gunicorn（监听 8686），前端 `vue-frontend` 构建产物作静态站根，Nginx 反代 `/api/`、`/admin`、`/static/`。
