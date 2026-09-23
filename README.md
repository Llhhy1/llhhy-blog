# Llhhy Blog · 个人博客系统（Flask + Vue3）

前后端分离的个人博客：**Flask** 后端（SSR + JSON API + 管理后台）+ **Vue3** 前端（SPA）。单仓库托管前后端代码、部署文档与安全报告。

- 当前版本：**v3.20.0**
- **SEO 收录闭环（v3.18.9 + v3.19.0 + v3.19.1）**：爬虫通道 + 主动推送两层。
  - **v3.18.9（通道）**：`/post/<slug>` 对爬虫/社交抓取器返回**带正文的服务端壳页**，壳页含 **`BlogPosting`/`BreadcrumbList` JSON-LD**（补上 v3.18.6 SSR 退役后彻底缺失的那块）。闸门独立于 `detect_bot()`（它认不出微信、且把社交抓取与 Ahrefs 混在一类），改为「搜索引擎/社交预览双 UA 表 + **真人信号否决**」两层——**防 QQ 内置浏览器里的真人（UA 带 `QQ/9.7.x`）被误伤**。站点地址收敛为 `utils.site_base()` 唯一真相源（**删除 `request.host` 回退**，关闭 Host 注入遗留项）。**Nginx 配置原文入库** `deploy_guide.md`「第 4b 步」（缺它 = 重装后爬虫变回空壳）。另修复**分享卡 `.png` 自 v3.16.0 起一直返回兜底图**的三层叠加故障（字体缺失 → 宝塔图片正则压过 `^~ /api/` → 全局 `proxy_cache` 把兜底图缓存了）。
  - **v3.19.0（推送）**：后台「🔍 收录」控制台——主动推送给**百度**（主动推送 API）与 **Bing/IndexNow**，凭据 Fernet 加密存储、推送**全异步**（接口立即返回 + 页面轮询）、**不可见文章拒绝推送**、sitemap/robots 只读预览、GSC/Bing/百度站长入口。**Google 不做自动推送**（无通用推送 API，不造假的「提交成功」按钮）。
  - **v3.19.1（第三轮复审修复）**：修掉一个**已上线的 302 环**——v3.19.0 把「真人否决」无差别套在搜索引擎上，而真实 Googlebot/Baiduspider **会送 `Accept: text/html`**，于是「nginx 按 UA rewrite → 后端否决后 302 回 `/post/<slug>` → nginx 再 rewrite」形成**无限环**（线上实测三类身份 12 次重定向后仍是 302：搜索引擎抓不到正文、QQ 真人看到 `ERR_TOO_MANY_REDIRECTS`）。修法：**否决作用域按桶拆分**（`Sec-Fetch-*` 两类桶都否决；`Accept` 只否决社交桶）+ **经通道的请求绝不 3xx**（真人→200+`noindex` 可读页；工具蜘蛛→404 不给正文）。同时修出站**禁跟随重定向**（半盲 SSRF）、推送成功判定要求 JSON、响应只存白名单字段、**脱敏先于截断**、自检端点**改为零出网 + 超管限定**、线程异常不再静默、审计带 IP、推送限流与在飞去重、彻底删除文章清推送记录。行为现状：**三出口**为「不可见→404+`noindex`」/「经通道且判为抓取方→200+`index,follow`+公开 canonical」/「经通道但被否决→200+`noindex` 可读页（真人）或 404（工具蜘蛛）」；**不带 `?seo=1` 的直敲仍 302 回公开地址**。
  - **v3.19.2（配额字段名修正）**：v3.19.1 上线后核对**生产真实数据**发现百度主动推送的剩余配额字段名是 **`remain`** 而非 `remaining`（实测响应 `{"remain":8,"success":1}`）——代码读错名字导致剩余配额读不到、收录页配额栏一直空白（`quota` 档仍被 `error: over quota` 分支兜住，故**不是状态误判、只是信息缺失**）。修复：两个名字都认 + 把 `remain` 加入响应字段白名单 + **更正 docstring 里那句错误示例**（它正是这个 bug 的来源）。该缺陷第三轮复审报告未覆盖，由生产数据抓出。这也顺带验证了 v3.19.1 的推送链路在真实环境工作正常（7 篇全部 `ok`）。
  - **v3.20.0（待办清单批次）**：把 `ROADMAP` §5.8/§5.9 的延后批次逐项过了一遍，但**先实测再动手**，因此有 3 项结论与审计描述不同。**做了什么**：① 工程化门禁 —— `pyproject.toml`（ruff 高信号阻断集）+ `tools/lint_debt.py` **lint 债务棘轮**（历史债只允许减少、不允许增加，从而在不清算 91 处 `except: pass` 的前提下止住新增）+ CI `lint` job（含 i18n、发布公钥一致性）+ `dependabot.yml` + `npm install`→`npm ci`；② `gunicorn_conf.py` **入库**（原先只在线上、删站即丢）；③ **`GET /api/health`** 存活探针（此前零探活端点，只能靠人工体检）；④ `notify.py` **通知异步化**（原最坏阻塞 12s，且 5 个调用点全在请求路径上）；⑤ 前端 a11y —— skip-link、toast 改**常驻 live region**、修掉 `DocsView` 的 **IntersectionObserver 真泄漏**、灯箱补 `role="dialog"`。**做了什么决定不做**：`post`/`comment` 加索引（实测 **7 行 / 1 行**，有量的表早已建好索引 → 改为设触发条件：`post > 500`）；`inject_globals` 加缓存（SSR 退役后只剩 **2 个模板**走 `base.html`，那 8 条查询只在后台页发生 → 收益小于复杂度）。**并更正一处我自己写错的因果**：原以为「ORM 对象进后台线程必抛 `DetachedInstanceError`」，实测**证伪**（detached 后标量属性照常可读；真实边界是**懒加载关系**）→ 相应改动定性为「纵深防御」而非「修 bug」。安全审计 **R92**；验证 **221 passed** + 覆盖率 **49%**（CI 以 `--fail-under=45` 防回退）+ ruff 全绿 + 棘轮通过 + `check_i18n` 通过 + `vite build` 通过 + `pip-audit` 无已知漏洞。同日续做第三轮（功能类）：统计深度 —— 来源渠道 TOP / 实时在线 / 趋势环比 / CSV 导出（UTF-8 BOM + 公式注入防护），**零表变更**；SEO 自动推送 —— 废弃实测不可用的 ping 端点（Bing 410 / Google 超时），改为「发布即自动 `enqueue`」（`maybe_auto_push`，**默认关闭**、只推可见文章、复用限流去重）。
    **同日续做的第二轮**（用户要求「能做的全部实现」）：修掉上一轮**只有实测才能发现的真缺陷** —— **每页 2 个 `<main>`**（11 个视图改 `<div>`）、灯箱**完整焦点陷阱**、**`/api/qr` 不再用 `request.host_url`** 拼对外地址（闭环 R90 待办②，同时保住别名域名可用）；新增 **Atom 1.0 订阅源 `/feed.atom`**（⚠️ **nginx 需加一行 `location = /feed.atom`**）；CI 补 **覆盖率门禁与 pip-audit CVE 扫描**。**并把一条审计结论更正掉**：4 处未走客户端 `sanitizeHtml` 的 `v-html`，其数据**全部在服务端已消毒**（`api/site.py:20/103`、`feed_agg.py:258`）—— 消毒在服务端才是正确的信任边界，客户端再洗对管理员富文本反而有剥离合法标记的风险，**故不加**。
  - 详细缺口与后续方案（`/`、`/category/*` 等仍是 SPA 空壳、性能与 CI 批次）见 `ROADMAP.md` §5.8 / §5.9。
- **架构：单前端（v3.18.6）**。生产只有一套渲染器——**Vue SPA**。Nginx 只把 `/api/` `/admin` `/static/` `/mcp*` 与 `feed.xml` / `sitemap.xml` / `robots.txt` / `feed/comments` 反代给 Flask，其余路径由 SPA 兜底；`routes.py` 里原有的 8 个「页面级」SSR 路由（`/`、`/post/<slug>`、`/category/<slug>`、`/tag/<slug>`、`/search`、`/about`、`/links`、`/archive`）**已退役为 410 Gone**，7 个对应模板已删除（顶层模板只剩认证与错误页）。endpoint 名保留（`base.html` 的 `url_for` 依赖它们）；`/login` `/register` `/logout` 仍是 SSR，`/post/<slug>/comment` 与 `/post/<slug>/like` 两个 POST 入口保留。
- **超长文件拆分（v3.18.1 · 纯重构，公共 API 与路由零变更）**：`myblog/utils.py`（784 行）拆成 `utils/` 包（`timeutil` / `render` / `net` / `slug` / `text` / `security` / `settings` / `web`，`__init__.py` 全量重导出，导入点零改动）；`admin/posts.py`（852 行 / 26 路由）拆成 `post_editor` / `post_manage` / `post_trash` / `post_history` / `taxonomy`（同一蓝图、URL 不变）。验证：逐名 `ast.dump` 等价性 + endpoint 守恒（99 处 `url_for` 全可解析）+ `113 passed`；最大文件 852/784 → 448/294 行。
- **游戏平台（v3.15.0）**：前台「🎮 游戏」卡片厅 + 沙箱内播放（`iframe sandbox` + CSP，拿不到本站 Cookie/登录态/API，禁外联）；后台「游戏收录」上传 zip → 安全解包 + 静态扫描 → 审核上架，可配置 OpenAI 兼容大模型做代码安全审计（Key 加密）；内置官方《就是按一下》《就是开车》两枚荒谬马拉松；开发者接入文档 `/games/dev`。
- **标签治理（v3.15.0）**：保存文章自动去重（中英文逗号/顿号/大小写/空白变体归一复用）、自动清理 0 使用标签；后台一键整理（合并重复 + 清理未使用）。
- **分享卡片（v3.15.0）**：站点级 OG/twitter meta + 文章页动态 OG（绝对图址 / 无封面自动回退），微信/QQ 分享不再只是裸链接。
  > ⚠️ **口径更正（v3.18.5 / 细化于 v3.18.6 / 部分已修复于 v3.18.9）**：文章页的「动态 OG」实现在 **Vue 客户端**（`PostView.vue` 注入 meta）。服务端侧有一条**爬虫专用通道**：Nginx 按 UA 把爬虫/社交抓取器的 `/post/*` 改写为 `/api/og/post/<slug>?seo=1`。**v3.18.9 已修复这条通道并补齐 JSON-LD**——现在服务端壳页带正文 + `BlogPosting`/`BreadcrumbList`，且明确输出 `index,follow`（修复前恒发 `noindex` 且 canonical 指向 `/api/…`，等于接通即拒收）。`/`、`/archive`、`/category/*`、`/tag/*`、`/about`、`/links` 仍是 SPA 空壳，**无任何服务端 meta**。补 meta 的具体方案见 `ROADMAP.md` §5.8。
- **主题中心（v3.16.0）**：后台「🎨 主题中心」——14 套预设主题包（OKLCH 感知色彩空间，亮色单源 / 暗色自动推导），实时预览网格 + 自定义 JSON 导入/导出，一键应用全站整体换肤（前后台共用同一套 token）；写操作仅超管 + 全局 CSRF，无 DB 迁移。
  > ⚠️ **口径更正（v3.18.5）**：`derive_dark` 只做明度（L）钳制，**没有 WCAG 相对亮度校验环**；抽查已发现 4 组 token 组合对比度 < 4.5:1（如浅色 `--text-faint #9aa0a6` on `#fff` ≈ 2.6:1），风险面覆盖 14 套主题。补校验环见 `ROADMAP.md` §5.8。
- **分享卡重做（v3.16.0）**：文章页 SVG 图标分享面板（微博 / QQ / 微信 / X / Telegram / Facebook / LinkedIn）、动态 OG 图（Pillow 绘制 1200×630 + 磁盘缓存）、文章二维码（站点二维码 SVG）、图片灯箱 / 代码复制 / 阅读时长等阅读体验增强。
- **体验修复与升级（v3.17.0）**：修复**前后台深色模式顶部白条**（导航配色不再压过深色覆盖）、**主题包换肤未生效**（token key 下划线→短横线）、后台表格手机端窄屏卡片化堆叠；新增 `prefers-reduced-motion` 降级、首页骨架屏、Toast 提示、路由过渡、滚动渐入、容器查询、Bento 首页概览、移动端手势导航、键盘彩蛋。
  > ⚠️ **口径更正（v3.18.5）**：后台表格卡片化依赖每个单元格的 `td[data-label]` 生成列名，**实际只有 2/22 个表格模板写了 `data-label`**（备份页等），其余（我的文章 / 评论 / 用户 …）窄屏下只是无标签堆叠，**并非「全站可浏览全文」**。补齐见 `ROADMAP.md` §5.8。
- **AVIF / 年度回顾 / AI 摘要（v3.17.0）**：上传图片自动生成 AVIF 并以 `<picture>` 优先加载（Pillow 支持时启用，**零新增依赖**）；新增 `/annual` 年度回顾页（发文 / 阅读 / 评论 / 访客 / 地域榜 / 最热文章 / 高频标签）；后台文章编辑页「🤖 生成 AI 摘要」+ 前台展示（复用 OpenAI 兼容配置，结果存 Setting，**零表结构变更**）。
- **后续增强（v3.17.1~3）**：修复导航 CSS 选择器被 Jinja autoescape 转义致深色修复不生效（改无引号写法 + 回归测试锁死）；后台移动端系统性防溢出（表单/分屏编辑器/工具条）+ `@media print` 打印样式 + 成就徽章（8 枚里程碑）；评论表情回应（👍❤️😂🎉🤔👏，Setting KV 存储**零迁移**）；访客来源分析（`visit_log` 加 `referrer` 列仅存 origin，统计页「来源 Top 10」）；访客地图（阿里 DataV 合规行政区划底图 + 自绘墨卡托 SVG 省份热力，含港澳台及南海诸岛，失败降级地域榜）。
- **修复与增强（v3.17.4~9）**：Bento 概览卡布局修复（对角双宽卡）；归档时间线深色可读性修复；LLM Base 兼容完整端点（游戏审计与 AI 摘要恢复可用）；**全站 7 处一键复制统一三层兜底**（Clipboard → execCommand → 手动提示）；后台移动端补齐（备份配置页内联 4 列网格、诊断助手 `.stats-table` 横滚）；**后台「AI 摘要」独立管理页**（覆盖状态 + 单篇生成/编辑/清除 + 批量补齐）与摘要完整展示；**社交账号墙独立成页 `/social`**（20 平台图标自动匹配，QQ/微信填号码点击复制、填图片展示二维码）+ 主页「找到我」区块 + 导航入口。
- 历史版本记录见 [CHANGELOG.md](CHANGELOG.md)

## 功能一览

- **内容**：Markdown 写作（代码高亮）、定时发布、文章置顶、分类 / 标签 / 归档、每篇独立 SEO 字段、RSS / sitemap / robots
- **时区**：全站时间统一以「北京时间（UTC+8）」展示（数据库仍按 UTC 存储），覆盖文章 / 评论 / 归档 / RSS / sitemap / JSON-LD / 后台模板；定时发布输入框也按北京时间填写。
- **搜索**：SQLite FTS5 全文搜索（环境不支持时自动降级 LIKE）
- **阅读**：文章目录 TOC、阅读进度条、相关文章推荐、系列专栏（上下篇导航）、图片懒加载 + WebP 转码、阅读量防刷、多作者署名
- **互动**：评论（登录/匿名，显示 IP 属地与设备，头像由 cravatar 提供）、嵌套回复、评论与文章点赞、留言墙
- **社交**：广场微动态、友链 RSS 聚合（博客圈）、社交账号墙
- **微动态管理（v3.12.0）**：后台「💭 微动态」——列表检索（关键词 / 作者 / 分页）、编辑正文、删除动态（级联清评论）、逐条删评论、批量删除；编辑与删除均写入后台操作日志。此前动态发布后只能直改数据库
- **UI 设计系统 token 纯度（v3.12.1）**：后台 `admin.css` 与前端 `global.css` 的散点硬编码暗色（hex/rgb）统一替换为 `tokens.css` 语义 token，明暗主题外观像素级零色差；无逻辑变更、无 DB 迁移。详见 [CHANGELOG.md](CHANGELOG.md) v3.12.1 段
  > ⚠️ **口径更正（v3.18.5）**：**组件级 token 化已完成**，但两份样式表仍各残留约 230~250 处裸 hex（`DocsView.vue` 内还有整段局部硬编码色，主题包对其无效）；且 `vue-frontend/src/styles/tokens.css` 与 `myblog/static/tokens.css` 是**手工复制的两份**，非单一来源。
- **写作后台（v3.14.0）**：写作面板带 Markdown 工具栏与分屏实时预览（走后端同一渲染管线）、云端自动保存、未发布草稿一键「🔗 复制免登录预览链接」（HMAC 签名 + 24h 有效）；「📄 文章管理」独立成页（管理员看全站，关键词 / 状态 / 分类 / 系列筛选 + 多列排序 + 批量发布·转草稿·移分类·移回收站）；写文章时可就地**新建分类 / 系列**无需退出页面（同名自动复用）；「🖼️ 媒体库」浏览 / 复制 URL / 删除（带引用提示）；版本历史支持逐行对比；分类 / 系列可改名（slug 自动保持唯一）、删除分类可先把文章转移到目标分类；修复后台上传图片必 500 的遗留 bug（v3.11.0 切片遗失魔数表）
- **运营**：邮件订阅与新文推送、Telegram / 企业微信推送、站点公告、Open Graph 分享卡片
- **运维**：访问统计（区域 / 热读 / 热搜 / 时段）、数据备份与异地容灾（本地 / OSS / SCP / WebDAV）、后台一键在线更新、全站健康体检（11 维）、运营驾驶舱（趋势区间切换 / 评论·新文量曲线 / CSV 导出）
- **一键在线更新的完整性（v3.18.7 · 对所有人开箱可用）**：更新包用 **Ed25519 分离签名**——`sha256.txt` 由发布者私钥签名，**验签公钥内置在 `update.sh` 里**，所以任何人 clone 这份仓库部署都无需任何配置即可获得签名保护；校验**默认 fail-closed**（签名缺失/验签失败/清单查不到文件/注释双源互证失败，一律终止更新，不再「静默跳过」），**不再自动兜底第三方公共镜像**（清单与产物同通道，公共代理可同时改写）。自建发布者（fork 后自己发版）用 `python package.py --gen-key` 生成自己的密钥对，把公钥填进 `update.sh` 的 `BUILTIN_RELEASE_PUBKEY` 或部署侧设 `RELEASE_PUBKEY` 即可；调试期可用 `ALLOW_UNSIGNED=1` 显式放行（会打醒目警告）。另有版本单调性（默认拒绝降级覆盖，`ALLOW_DOWNGRADE=1` 可放行）。本地可用 `python verify_package_checksums.py` 跑**三链互证**（整文件哈希 / zip 注释内容区哈希 / 发布物签名）。
- **插件（框架保留，v3.10.0 起无内置插件）**：`myblog/plugins/` 可扩展插件框架 + 后台「🧩 插件管理」+ 事件总线与前端槽位；仓库不再内置插件，装自写插件只需放目录 + 填 `ENABLED_PLUGINS`
- **性能（v3.9.1）**：文章正文渲染结果落库缓存（`Post.content_html`，正文一改自动失效，长文 `87ms → 2.7ms`）+ SQLite WAL（读不阻塞写，解决并发 `database is locked`）
- **数据库迁移（v3.11.0）**：引入 Flask-Migrate / Alembic 基线迁移，与现有 `db.create_all()` 自动迁移并存；新库 `flask db upgrade`、存量库 `flask db stamp head` 即可对齐 v3.10.6 基线，后续模型变更可自动生成迁移（无缝升级）
- **远程诊断（v3.10.0）**：只读 MCP 端点 `/mcp`，AI 助手可远程查全站体检、数据库状态、错误日志、内容统计；未配置 token 时自动关闭，全部工具只读
- **MCP 服务管理（v3.13.0）**：后台「🔌 MCP 服务」面板——内置端点一键启停（停止 = 对外 404，即时生效）、外部 MCP 服务登记（token Fernet 加密落库零明文）、每个服务一键生成「AI 脱敏接入指令」（脱敏版可放心转发 / 完整版 AI 拿到即可直接配好 mcp.json，查看记审计）
- **博客圈稳定性（v3.10.4）**：友链 RSS 聚合加 socket 超时（默认 8s，环境变量 `FEED_FETCH_TIMEOUT` 可覆盖），坏源只跳过不卡死 worker；后台保存 RSS 增加可达性软校验
- **系统**：三级权限（超管 / 管理员 / 用户）、前后台统一明暗主题与自定义主题色、设备自适应
- **主题中心（v3.16.0）**：后台「🎨 主题中心」——14 套预设主题包（OKLCH 感知色彩，纯标准库推导暗色，亮色单源 / 暗色自动；每包含 light.accent 与 dark.bg 等语义 token）；实时预览网格 + 自定义 JSON 导入/导出（`POST /api/theme` 仅超管 + 全局 CSRF，自定义值仅作 CSS 变量无 JS 执行）；`/api/site` 下发 `theme_pack`/`theme_tokens`/`theme_dark_tokens` 供前后台统一换肤；复用既有 `Setting` 表，无 DB 迁移
- **移动端适配（v3.10.6）**：修复后台「统计」长标题与公开站「文档页」长路径 / 长表格 / 长代码在手机端横向溢出穿模，窄屏下统一换行而非挤压版心

## 快速开始

后端（默认 5000 端口）：

```bash
cd myblog
python -m venv venv && pip install -r requirements.txt
# 安全启动前置：两个环境变量缺失时程序拒绝启动
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export ADMIN_PASSWORD=$(python -c "import secrets;print(secrets.token_hex(16))")
flask --app app init-db
python app.py            # http://127.0.0.1:5000
```

前端（开发模式，自动代理 `/api` 到后端）：

```bash
cd vue-frontend
npm install
npm run dev              # http://localhost:5173
```

## 部署

完整宝塔面板点按式教程见 [myblog/deploy_guide.md](myblog/deploy_guide.md)。

- **后端**：gunicorn 运行 `myblog`（监听 8686），Nginx 反代 `/api/`、`/admin`、`/static/`
- **前端**：`npm run build` 后把 `dist/` 作为静态站根目录
- **必配环境变量**：`SECRET_KEY`、`ADMIN_PASSWORD`
- **升级**：覆盖后端与前端后，gunicorn 必须「**停止 → 启动**」（restart 不会重载前端静态资源），再硬刷新浏览器
- **确认版本**：登录后台，左下角显示当前版本号

部署包（后端 `myblog-backend.zip`、前端 `vue-frontend-dist.zip`）随 [Releases](../../releases) 发布。

## 安全

- `SECRET_KEY` / `ADMIN_PASSWORD` 必须经环境变量注入，缺失即拒绝启动，源码无任何弱默认密钥
- 会话 Cookie `Secure` / `HttpOnly` / `SameSite=Lax` + 同源校验 + CSRF Token 双重防护
- Markdown 经白名单清洗（防存储型 XSS）；RSS 聚合防 SSRF（仅 http/https、拦截内网与 DNS 重绑定）
- 登录 / 注册 / 评论 / 点赞按 IP 限流；Webhook 用 HMAC 恒定时间比较 + 时间戳防重放
- 图片上传禁用 SVG + 文件头魔数校验
- 评论头像由第三方 CDN（cn.cravatar.com）提供：仅发送邮箱的 MD5 哈希（Gravatar 协议标准，明文不落库），拉取失败自动回退默认头像（`?d=mp`）；用户邮箱不会对外暴露

完整审计见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)。

## License

[MIT](LICENSE) © 2026 Llhhy
