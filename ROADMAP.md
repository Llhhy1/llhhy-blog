# 博客功能路线图（Roadmap）

> 本文档 = **功能地图（已做）+ 待办（不做放一块）**，简单描述。
> 历史版本迭代明细、v3.25.x 详细决策 / 取证日志见 `docs/archive/ROADMAP_archive.md`；权威版本史见 `CHANGELOG.md`。
> 当前线上：**v4.13.1（Flask 线，v4.0→v4.13.1 连续版本）**。
> 代码 / 文档里出现的旧章节编号（`ROADMAP §5.2`、`§5.9` 等）→ 见文末「旧章节索引」。

## 一、当前状态

- 线上 **v4.13.1**：Flask 后端 + Vue SPA 前台 + Flask/Jinja2 后台，SQLite（WAL）。
- 已启用：`content_migrate` 插件（WordPress WXR / Typecho SQL / **Typecho SQLite .db** 只读迁移）。
- 架构决策：**维持 Flask 栈**（SQLite 上 async 负收益，仅 Postgres + asyncpg 才有收益）；**v4 FastAPI 异步栈实验分支已废弃**，不接管线上。

## 二、已做（功能地图，按模块）

- **A 社交聚合（广场）**：微动态发布 / 点赞 / 评论、友链 RSS 聚合（博客圈，防 SSRF + bleach）、社交账号墙、动态互动。
- **B 内容与阅读**：相关文章推荐、热门排行、TOC + 阅读进度条、文章系列 / 专栏、FTS5 全文搜索（自动降级 LIKE）、定时发布、文章置顶。
- **C 互动与社区**：留言墙、评论嵌套回复（深度遍历 + 排序白名单）、邮件订阅 / Newsletter（SMTP + 退订链接 + 新文群发）。
- **D 运营与分发**：OG 分享卡片、微信 / Telegram 新文推送、Webhook 自动部署（HMAC + 防重放）、站点公告、自定义外部入口（单 / 多条化）、访客数据精细化 + 访客日志 + IP 拉黑、移动端管理接口（66 端点 + 权限收口 + 内容全套）。
- **E 插件系统（v3.9.0）**：加载框架（失败隔离）、blinker 事件总线、前端结构化槽位、后台插件管理页。
- **F 性能与稳定（v3.9.1）**：正文渲染缓存（指纹失效）、SQLite WAL、备份链路 WAL 适配、体检项可观测。
- **安全 / 质量**：三级角色、CSRF 全量、SSRF 防护、限流、两轮独立安全审计、CI（ruff 棘轮 + pip-audit + 覆盖率门禁）。
- **来源渠道（referer）统计（v3.17.3）**：`VisitLog.referrer` 列 + `_top_referrers()` + `/api/stats/referrers`；**只存 origin**，天然不泄隐私。（曾长期被误记为「需新列、隐私待定」）
- **v4.9.0 升级地图落地**：设备 / 浏览器分布（`visit_log` 加 `device`/`browser` 两列，**不落原始 UA**）、推送指数退避重试、留言墙敏感词过滤（与评论共用 `find_spam_hit`）、搜索历史（前端 localStorage）、内容日历（`/admin/content-calendar`）、分享卡片模板库（含**微信方图 800×800** 防裁切）。
- **v4.10.0 升级地图第二轮**：推送配置后台化（含 `notify._post_json` **出站 SSRF 加固**：
  https 白名单 + 公网解析 + IP pinning + 禁 3xx）、列表页服务端 SEO 壳页
  （`/api/og/page/<path>`，归档/分类/标签/系列/关于/友链）、移动端第二批 7 组「数据与设置」端点
  （统计报表/审计/备份/设置/收录/证书/用户角色，**逐条对齐后台页面权限**）、
  `update.sh` 版本号解析加固、lint 债务 472 → **241**。
- **v4.11.0 后台统一 + 诊断扩展**：`admin.css` 后台统一组件层（补齐 `.hint-block` /
  `.entry-edit-form` / `.tag` 等**从未被定义**的类 —— 这才是「几页看着不像一套」的真实原因）
  + `:where()` 零特异性全局表单控件基座 + 新建表单统一到 `.field` 范式；
  访问统计页样式越权修复（`.tag` / `.card-head` 无作用域前缀覆盖全站、`var(--muted)` 变量不存在）；
  全站体检 **12 → 19 维**（新增插件 / 搜索索引 / 定时任务 / 出站安全 / 内容质量 / 磁盘 / MCP 自检）
  并修掉「明细表恒不渲染」的静默 bug；MCP 只读工具 **5 → 8**（health_score / issues / run_check）。
- **v4.12.0 前台 /docs 修正与重做**：版本号改为运行时取 `GET /api/health`（原先写死 v3.8.7，
  落后三个大版本）；补「其他接口」一章（分享卡 / 列表页壳页 / 二维码 / 通道自检 / 管理类 74 条分组）；
  修 `scroll-margin-top` 20px 致锚点被 58px 吸顶头遮挡；修**复制按钮从来没有样式**
  （JS 动态创建拿不到 scoped 的 `data-v`，`pre :deep(.copy-btn)` 才对）；样式全部改走设计令牌
  （原先硬编码色导致换主题色不跟、深色要逐条覆盖）；左右两个目录改为互补（左=章节，右=当前章小节）；
  新增文档内搜索、回顶按钮、移动端横向 chip 导航；修纵向 flex 下 `align-items: flex-start`
  造成整页横向溢出 1245px。
- **v4.12.1 访问统计表格对齐修复**：中间数值列（「来源 | 次数 | 占比」的次数）表头继承
  `text-align:left` 而数据是 `.rank-count` 的右对齐，`table-layout:auto` 下拉宽后两者分居
  两端 → 新增 `th.num` / `td.num` 统一右对齐并用 `width:1%+nowrap` 收窄；同源另一半：
  `≤900px` 给 `.stats-table` 的 `display:block`（为横滚）会把 `thead`/`tbody` 拆成两个
  匿名表格、列宽各自计算，改为恢复 `display:table` + 卡片级横滚。
- **v5.3.1（2026-10-30 已发布）修复 /docs 搜索与目录失效 + API.md 版本头补 bump**：v5.3.0 把 `/docs` 改成渲染 `API.md` 后，搜索框与左侧目录同时失效（左栏链接数组恒空、搜索 `visibleSections` 永远 0 命中、右栏「本节内容」也空）。根因是 `DocsView.vue` 的建树逻辑写错：`buildToc` 在 h2 分支只 `subs.push` 漏了 `links.push`、`sectionText` 的 key 错挂成 h2 id（而搜索查 h3 的 link id）、`syncActive` 把 `activeId` 设成 `.doc-section` 容器 id 而非 h2 模块 id。修法：h2 分支 `subs`/`links` 都 push 同一组 h3；`sectionText` 改为 key=h3 link id、value=该模块整段正文；`syncActive` 改为跟踪 h2；左栏当前模块加高亮。另补 bump：`myblog/API.md` 头部版本号 v5.2.6→v5.3.0（v5.3.0 漏了，被弱断言假通过）；`test_api_doc_sync.py` 版本断言收紧为头部整段严格匹配。**实证**：`npm run build` + `test_api_doc_sync.py` 5 passed；用真实 `render_markdown(API.md)` 复刻建树得 30 模块 / 198 端点条目、links/subs 非空、搜索 `mobile`→81/`slug`→140 等命中。**新增发版纪律**：凡新增/改接口，`API.md` 与前端 `/docs`（消费 API.md）必须同步、头部版本须 bump，已由 `test_api_doc_sync.py` 在发版全量 pytest 强制把关。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.3.2（2026-10-30 已发布）/docs 代码块重做**：`DocsView.vue` 新增 `decorateCodeBlocks()`，把 `/api/docs` 注入的每个 `<pre>` 包成「语言标签栏（`.code-block__lang`，取自后端 `language-*` class）+ 复制按钮（`.code-block__copy`）+ 深底 `pre`」的 `.code-block`，并修好高亮时机（原 `tryHl` 在 `onMounted` 装饰空容器、异步内容到达后 `v-html` 重建的 `<pre>` 永不被高亮）。无语言围栏（目录树）显式标 `plaintext` 防自动探测误上色。`API.md` 两处目录树补 `text` 语言；`APP_VERSION`→`v5.3.2`（与文档头一致）。无迁移，head 不变。
- **v5.3.3（2026-10-30 已发布）热修 /docs 代码块整体失效**：v5.3.2 上线后 `/docs` 代码块设计仍未生效，根因**不在前端**而在 `myblog/API.md` —— 给目录树补 `text` 语言时**误把第一棵目录树的闭合围栏也写成 ` ```text `**；markdown 闭合围栏不允许带 info string，该块永不闭合，**整篇从第 138 行起所有围栏退化为行内 `<code>`**（渲染 `<pre>`=0 / `<code>`=1870），前端 `decorateCodeBlocks()` 找不到任何 `<pre>`。第二坑：`python` 示例缩进在有序列表第 3 步内，Python-Markdown 3.8 的 `fenced_code` 不支持列表内缩进围栏。修法：闭合围栏改回纯 ` ``` `；`python` 示例提到列表之后顶格（保持 1-7 步编号连续）。**守卫升级**：`test_docs_codeblock_design.py` 从「只查源码文本」改为「静态（闭合围栏纯反引号 / 必须顶格 / 必须成对）+ 真实 `render_markdown(API.md)` 断言 `<pre>` 数 == 围栏块数、语言含 text+python」，并做变异验证（改回 ` ```text ` 立刻变红）。**实证**：真实渲染 `<pre>`=2、语言 `text`+`python`、围栏 4 行严格配对。前端与后端代码均未改动。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.4.0（2026-11-01 已发布）分类/标签/系列 slug 可读化**：起因是中文标签的访问日志与分享链接是 `%e6%99%ba...`——`make_slug()` 保留汉字，46 个标签 slug 就是中文（标准百分号编码，不是故障，但不可读）。改法：新增 `utils.slug.ascii_slug()`（ASCII 小写保留、符号转 `-`、汉字走 `pypinyin.lazy_pinyin` 惰性导入、缺库降级剔汉字）、`unique_model_slug()` 统一走它并支持 `explicit=`；后台建标签/分类/系列可选填地址、标签页每行可改；**行为变更：改名不再自动重算 slug**（只有显式填地址才改，避免外链 404）。旧地址由 `utils.taxonomy_slug.resolve_taxonomy()` 四路兜底（精确 → 忽略大小写 → `name` → `ascii_slug(name)`）：列表接口返回 `moved:true`+新 slug 供前端 `router.replace`，`/api/rss/*` 与爬虫壳页 `/api/og/page/*` 发 **301**（nginx 不用改）。数据侧一次性迁移 56 标签/4 分类/1 系列；**顺序：先发代码再迁移**。**实证**：新增 `test_slug_ascii.py` 16 条、全量 pytest 1333 passed、ruff 0、vite build 通过。无 schema 变更，head 仍 `b7c2e91a4d63`。
- **v5.4.1（2026-11-01 已发布）部署脚本热修：venv 属 root 时装不上新依赖**：v5.4.0 首次真的新增依赖（`pypinyin`）才暴露 —— `update.sh` ④b 用运行身份（www）`pip install`，而宝塔 venv 属 root，报 `[Errno 13] Permission denied: .../site-packages/pypinyin`；且错误出现在 `Downloading … 840 kB` 之后，极像网络问题（实测三个镜像索引都 200，此前每版都是「依赖已满足」故从未写盘）。修法三条：① `sysconfig` 取 `purelib` + 运行身份 `test -w` 预判可写性；② `id -u == 0` 且非 root 身份时 root 兜底（先镜像后官方）；③ root 安装包在 `( umask 022; … )` 内，避免 root 默认 umask 077 装出运行身份读不到的包（那会变成「日志全绿、运行期 ModuleNotFoundError」）。不改 venv 属主（面板自管，改了破坏面更大）。**实证**：`bash -n` + 抽出函数配 stub 跑 4 个分支 + 新增守卫 `test_依赖安装_venv属root时要能自动兜底`（变异验证 `umask 022`→`077` 立刻变红）+ 全量 pytest 全绿 + ruff 0。`update.sh` 不在 zip 内，靠同 tag raw 自更新后 `exec bash` 重跑，故**本次部署即生效**。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.4.2（2026-11-01 已发布）修 `/docs`「如何新增一个 API」步骤编号错乱**：页面显示 6/7/8/9/10/11，根因不是编号而是 **Markdown 缩进** —— 步骤 4「鉴权按需选」下 4 个子项用 3 空格，而 Python-Markdown 嵌套列表要 **4 空格**，少一个空格就被并进同一个 `<ol>`。改法：4 行改 4 空格（正文不动）。**实证**：渲染后该小节 `<ol>` 恰好 7 个 `<li>`、步骤 4 内嵌 `<ul>`(4 项)、全文 `<pre>` 仍 2、语言仍 `text`+`python`；新增守卫 `test_apimd_列表子项缩进不会被并进有序列表`（静态「围栏外禁 3 空格无序项」+ 真实渲染断言），变异验证改回 3 空格立刻变红。纯文档变更，无迁移，head 仍 `b7c2e91a4d63`。
- **v5.4.3（2026-11-02 已发布）批次 D 主题校验加固 + 档 1 访客自选主题（默认关）**：来源 PR #35（5 提交 / 23 文件 / +1146−40，CI 6/6），快进合并 `a4e4599`。**批次 D** 收 4 个 P2：①`custom_css` 的 `</style` 转义改大小写不敏感（`</StYlE><script>` 曾可逃逸）+ 写入侧再拒 `</`；②`accent_color` 走 `validate_accent()` 并在 SSR 前再洗；③自定义主题 token 加键白名单 + 逐类取值校验，非法 400 带 `details`，读侧 `current_theme()` 再洗（脏库值自动回落）；④`post.lang` 用 `normalize_lang()` 收敛写入 + 4 处输出转义。**档 1**：站主开关 `allow_visitor_theme`（Setting KV，默认关、无迁移）开放后，访客可在 14 套预设里选，选择只写自己的 `localStorage`；关掉开关残留选择立即失效。（**该档已于 v5.4.5 整体下架**，见下一条）**接口契约变化**：`GET /api/theme`、`GET /api/site`、`POST /api/theme` 多 `allow_visitor_theme`，`POST` 新增 `visitor_theme`（只收布尔/`"true"`/`"false"`）。**实证**：PR 侧全量 1390 passed + CI 6/6；合并后本机 compileall/ruff/定向回归 198 passed/`npm run build`/全量 **1396 passed** 全通过。**前端有改动 → 必须重建**。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.11.0（2026-11-11）设计北极星（方向 B）：调性可声明 / 可校验 + 文章页层级修复**：把「设计意图散在 5703 行 CSS」收成单一真相源。新增 `DESIGN.md`（调性承诺 / 唯一难忘元素 / 6 条硬指标 / 实测表 / 架构判定 / 主题包 checklist）；主题包新增受限 `design` 契约（`tone` 十枚举 / `signature` ≤60 字 / `type_jump_min` / `accent_share` / `asymmetry`），经 `validate_bundle` 校验后并入 `clean` 与 `public_bundle`，章回包升 1.1.0。**推翻旧判断**：内置包 `css: ""` 不是缺陷 —— `#site-bundle-css` 无 SSR 注入点，是 `/api/site` 之后 `createElement` 的，首屏视觉写进 `css` 必然 FOUC（取证见 `DESIGN.md §5`）。文章页 `.zh-page-title` `22px` → `clamp(30px,3vw+8px,44px)` + `text-wrap: balance`，桌面 **44/16 = 2.75×**（原 1.38×）。新增守卫 `test_design_north_star_v5110.py`（8 条，5 种变异验证）；两次指标校准（朱砂口径 6→4 且改「去重选择器」；正文基准 16.5→16px 因 look.css 最后导入）。接口向后兼容、无迁移/新依赖/表结构变更。
- **v5.10.0（2026-11-10）章回视觉推到极致（资深评审 → 方向 A，P1+P2+P3 一次交付）**：站主从三张真实渲染样张中选定「章回推到极致」。只读诊断：卷首 44/16px 仅 2.75×、文章 H1/正文 22/16px 仅 **1.38×**，主题包 `css=0`、章回语言硬编码 47 条选择器、114 个守卫把大胆试错成本抬得极高；根因是「一直用工程语言提需求、系统一直用工程指标回答」+「先读文字方案凭想象选」。本轮不夹带架构改动，只把视觉推到极致：主标题 `clamp(52px,9.2vw,118px)`、左对齐 9vw、左深右浅遮罩（保留滑块联动）、朱砂竖排印章 + 8px 粗横线、最近更新改大字排版；分卷卡用 CSS counter 卷号封面（category 无 cover 字段、零数据依赖），水印放大成朱砂淡印；顺手修 `read-more` 浅字规则泄漏到纸白页的 **1.25:1** 缺陷（收窄到 `.layout.zh-chapter-dark`）。新增 `tests/test_visual_max_v5100.py`（11 条，已变异验证）。接口契约不变、无迁移/新依赖/表结构变更，`look.css` P2 块与两份 tokens.css 未动。
- **v5.9.0（2026-11-10）前台字体换为 OFL 子集，发布包瘦身**：只读实测后端 zip 27.96 MB 里京华老宋体 503 分片占 24.63 MB（88%），但线上 13 篇文章 + 前端文案只用 2089 个汉字（命中 77/503 分片）；京华老宋体授权「不可修改字体本身」无法子集化 → 改用 **Noto Serif SC / 思源宋体（SIL OFL 1.1）** 按真实用字生成单个 woff2：**24.80 MB → 0.61 MB（40.8 倍）**，汉字覆盖 2089/2089 零缺字。新增 `static/fonts/llhhy-serif-sc.woff2` + `.css` + `OFL-NotoSerifSC.txt`、`tools/build_subset_font.py`（`--refresh` 从公开 API 刷新用字 / `--check` 自检 / 源字体与许可 **sha256 钉死**）、`tools/font_charset.txt`（离线基线）；`index.html` 与 `themes.py` 的 `font_sans` 切到 `LLHhy Serif SC`；🔴 **站主激活的内置章回包 `theme_packs/zhanghui.json` 的 `tokens.light.font_sans` 也写死了旧字体**（`/api/site` 的 `theme_tokens` 来源），已同步切并 bump `1.0.1→1.0.2`，只改 `themes.py` 会线上零效果；CSP 不变、仍自托管；`package.py` 显式排除旧 `kinghua/`。**CSS 不写 `unicode-range`** → 子集外的字优雅回落系统宋体，不 404。新增 `tests/test_font_subset_v590.py`，同步 `test_audit_v543_sage_theme.py` 两处断言。🔴 观感变化（老铅印宋 → 现代规整宋）已由站主确认。线上旧 503 分片因 `rsync -a` 无 `--delete` **不自动删除**，无引用、待站主手动回收。接口契约不变、无迁移、无新增生产依赖、`update.sh` 未动。
- **v5.8.0（2026-11-10）动效层补齐与章回质感（资深评审取证后的 P0+P1 一次交付）**：① **补功能欠账**：主题包 `off/subtle/full` 三档早有 schema + 后台下拉 + `store.js` 注入，但 `global.css` 只实现了 `off`，`subtle`（线上激活档）与 `full` 零规则 → 新增独立动效层用 6 个 `--motion-*` 参数让三档真正生效；`look.css` P2 块与 `tokens.css`、三行 CSS import 全部不动。② **渐入**：`v-reveal` 改模块级单例 IO + 卸载解绑 + 序号错峰（55ms 递增封顶 7），覆盖扩到首页卡 / 分卷卡 / 分类页卡。③ **性能**：`onScroll` 从每次写 `bar.style.width` 改 rAF + `transform:scaleX`，回顶按钮改 opacity 过渡。④ **质感**：卷首 5 个元素阶梯入场（`backwards` 不锁末态）、分章交界 IO 揭幕（默认可见不依赖 JS、不改硬切语义）、复用既有 `_coverIO`/`.is-solid` 补顶栏过渡、`full` 档 + `@supports (animation-timeline: view())` 水印视差。⑤ **无障碍**：`off` 与 reduced-motion 彻底静态并显式清 `animation-delay`（全局兜底只压 duration 不压 delay）。🔴 异步主题包下分卷区 `v-if` 晚渲染，必须用 `watch(lightRef, ..., {flush:"post"})` 而非 `onMounted` 取 ref。新增 `tests/test_motion_layer_v580.py` 11 条守卫。**接口契约不变**、无迁移、无新依赖、主题包 schema 与 `update.sh` 未改；前端需重建，部署仍带 `GH_MIRROR`。
- **v5.7.0（2026-11-08）设计系统收口二期（v5.6.0 明确延后的四项全部落地）**：① **后台去内联**：新增 `static/admin-pages.css`，把各页静态 `<style>` 抽到共享文件；两个动态注入块与 `td[data-label]::before` / `bk-table` 卡片化规则按守卫依赖刻意留在模板内，内联 style 棘轮基线按实测下调；`_components.html` 五个宏从 3 个高频页扩到全部可逐字等价替换的模板。② **暗色硬编码 + 裸 hex**：`admin.css` / `static/style.css` 的语义色统一 `var(--token, #原值)` 兜底写法，暗色段写死灰阶改走 `[data-theme="dark"]` 对应 token；`static/style.css` 非兜底裸 hex **156→21**，渐变端点 / 状态徽章专用底色保留并登记理由。③ **排版尺度**：两份 `tokens.css` 扩到 **13 级字号 + 7 级排版行高（另加 2 个布局专用档）**，全库 21 种 px 字号 / 19 种行高字面量归零，`test_design_system_v560.py` 棘轮 18→0，新增 `test_typography_scale_v570.py` 反查每个兜底值防「架空尺度」。**口径更正**：上一版写的「27 种字号 / 24 种行高 / admin.css 234 处裸 hex」是含重复与含兜底的旧口径，实测为 **21 / 19 / 188**。④ 全量 pytest / ruff / compileall / vite build + 本地构建产物反代线上真实 API 的真实浏览器逐页核验。**接口契约不变**、无迁移、无新依赖、主题包 schema 未改、`update.sh` 未动；前端需重建，部署仍带 `GH_MIRROR`。
- **v5.6.1（2026-11-08）章回内页网格回归修复**：v5.6.0 上线后真实浏览器核验抓到「文章页 / 分类页内容偏左、右侧约 300px 空白」——根因是 `sidebar=hide` 只做 `display:none`，`.layout` 的 `698px 300px` 网格轨道不会随之消失（v5.5.0 起的存量缺口）。`look.css` 补单轨 + 正文 760px 居中，选择器带 `:not(.zh-chapter-dark)` 保护首页横卡，新增守卫钉死三要件。纯 CSS，无迁移 / 无新依赖 / 接口不变；前端需重建，部署仍带 `GH_MIRROR`。
- **v5.6.0（2026-11-08）UI 深度优化四阶段（P1 状态与刻度 → P2 章回贯通 → P3 设计系统收口 → P4 后台组件化一期）**：依据 `docs/audit/2026-10-31-v5.3.3-audit-and-theme.md` 的 7 类观感问题。① 新增 `AsyncState.vue` 四态组件与断点棘轮守卫，CategoryView / ArchiveView 接入；静默 `catch` 补提示。② `look.css` 追加章回全站语言层（全部选择器带 `:root[data-layout="chapter"]` 前缀、`:not(.zh-chapter-dark)` 排除首页暗底）、`lib/chapter.js` 共享判定、PostView / CategoryView / ArchiveView 三个结构钩子；分卷去 `slice(0,4)` 改 auto-fit。③ SSR 补引 `tokens.css` 实现三面共享真相源；`static/style.css` 8 处 `#999`（2.85:1）统一到 `--text-muted`（4.9:1），裸 hex 177→156；新增真实页面组合对比度守卫与 18 种字号棘轮。④ 新增 `admin/_components.html` 五个宏 + 3 个高频页小范围落地 + 内联 `<style>` 棘轮。**接口契约不变**（`API.md` 只 bump 头）、无迁移、无新依赖、主题包 schema 未改。**前端有改动 → 必须重建**；后端包 29 MB → 部署必须带 `GH_MIRROR`。**明确延后**：其余 52 个后台模板的宏迁移、后台暗色硬编码全量 token 化、admin.css 234 处裸 hex 收敛、27 种字号 / 24 种行高的全量尺度统一（牵动 `themes.py:_BASE_LIGHT` 双向绑定，需单独设计决策）。
- **v5.5.1（2026-11-07）主题说明整理与发布检查修复**：精简主题元数据与说明，保留全部外观和功能；修复主题模块新增的 6 条宽泛异常捕获，lint 债务基线不变。无迁移、无新依赖，仅发布不部署。
- **v5.5.0（2026-11-07）主题包「章回」+ 主题工坊 + 主题市场 + 外观回滚**：三步一次发版，方向是「站主主题库」——只有超管能换主题，部署本系统的人可以换自己想要的，**访客换肤缺席守卫保留**。① 主题包 = 纯声明式 JSON（`theme_packs/*.json`），布局靠 `data-*` + CSS 变量驱动，24 个视图零改动；首套内置「章回」用明暗分章 + 两列横卡流 + 纸白分卷区，搭配朱砂色与衬线字体。② `theme_library.py` 用 Setting KV 存自建 / 导入主题与五键外观快照（**不建表**），后台可视化编辑器 38 字段 + 真实前台 iframe 预览 + 一键回滚。③ 主题市场统一管内置 / 自建 / 导入三类，导入走严格模式**强制剥离 CSS**；信任边界三层。**接口契约**：新增 `GET/POST /api/theme/library`；`POST /api/theme` 支持 `bundle_id`（含 `lib:` 前缀）并返回 `prev`；`GET /api/site` 下发 `theme_bundle`。**实证**：全量 1439 passed、ruff 0、`npm run build`、变异验证 2 条守卫变红、真实浏览器全链路（应用 / 导入 / 回滚）。**前端有改动 → 必须重建**；后端包 29 MB → 部署必须带 `GH_MIRROR`。无迁移、无新依赖。CHANGELOG 因体积守卫归档 v4.3.1~v4.6.1（PAIRS 已登记）。**本轮只发版未上线**，部署需另给口令。
- **v5.4.5（2026-11-03）自定义页脚代码 + 档 1「访客自选主题」下架**：站主反馈「访客能自己换主题」是多余功能，要求拆掉并补一个能自己写页脚代码的入口。① 新增 Setting `footer_html` —— 后台「站点设置」textarea **原样输出**到页脚（SSR `base.html` `| safe`；SPA 由 `store.js:injectFooterCode()` 注入），**不清洗内容**，改由三处守边界：只有 `@super_required` 的 `/admin/settings` 能写（移动端设置白名单只读、无 API 写入口）、长度上限 `FOOTER_HTML_MAX=20000`（它进每一个前台页面）、改动记一条审计并进配置快照（可回滚）；② 关键实现坑：`innerHTML` 插入的 `<script>` 按规范**不执行**，所以插入后逐个换成新建元素（内联/外链同路），并用 `data-src` 比对保幂等 —— 否则 SPA 换路由会把统计脚本重跑、PV 翻倍；③ 下架范围：`themes.ALLOW_VISITOR_KEY`/`visitor_theme_allowed()`、`POST /api/theme` 的 `visitor_theme`、两处返回的 `allow_visitor_theme`、主题中心开关卡片、`ThemePicker.vue`、`store.js` 四件套 + `VISITOR_THEME_KEY`、3 个 i18n 键、`test_audit_v542_visitor_theme.py`（23 条）；**批次 D 校验与「青野」预设保留**。新增缺席守卫 `test_visitor_theme_switch_is_gone_from_code`（扫代码目录，残影即红）——本项目由 AI 协助维护，留残影等于邀请下次改动接回去。**接口契约变化**：`GET /api/site` 增 `footer_html`；`GET /api/theme` / `POST /api/theme` 去掉 v5.4.3 那两个字段（老客户端提交 `visitor_theme` 静默忽略）。**前端有改动 → 必须重建**。无迁移（`footer_html` 由 `_ensure_settings` 补默认空行），head 仍 `b7c2e91a4d63`。
- **v5.4.4（2026-11-02 已发布）主题「青野」+ 京华老宋体自托管 + 主题 token 真正被消费**：来源 PR #36 `feat/sage-theme`（2 提交 / 12 文件 / +482−28，`mergeable_state=clean`），快进合并 `3288b15`；同批并入 PR #37（Dependabot `github/codeql-action` 3→4，只改 `.github/workflows/codeql.yml`，不进部署包）。①第 15 套预设 `sage-sand`：accent 取 `#4e7544`（白字 5.31:1）而不是浅绿 `#7ea774`（2.74:1 过不了 `test_wcag_contrast` 的 4.5:1），浅绿原封留 `accent_soft` 当 wash；②京华老宋体 **503 分片 / 24.8 MB** 自托管（`tools/fetch_kinghua_font.py` 下载 + `--check` 校验；不入 git 但**随包分发**，后端 zip ~5 MB → ~29 MB；不带的降级路径是回落系统宋体）；③`body` 接上 `var(--font-sans)` / `var(--line-height-base)` —— 这两个 token 一直存在却从未被消费，主题包里的 `font_sans` 改了个寂寞；④换色才露出来的 8 处硬编码蓝（`#6aa9ff` / `rgba(25,109,221,…)`）收口到主题 token，无壁纸首屏改「淡 wash + 深字」、配壁纸仍白字（`.has-wall` 分叉），`.post-body a` 补主题色。**实证**：定向回归 48 passed、全量 **1405 passed**（2 条版本号守卫补齐后定向转绿）、`ruff` 0、`vite build` ✓（5.87s）、字体 `--check` 503/503、zip 内 723 条与磁盘逐字节一致（含 503 分片）。无迁移、无新依赖。**前端有改动 → 必须重建**。
- **v5.3.4（2026-10-31 已发布）v5.3.3 审计修复 + 设计系统收口 + lint 门禁归零**：按 **E → A → B → C → F** 五批执行。E 修复 10 条 ruff 错误（`media_service.py` 4×B904 / `media_storage.py` 2×C408 / tests 3×F841 + 1×RET504），CI ruff 固定 `0.16.8` 并重设 lint 债务基线 —— 因旧基线由老版 ruff 生成（F401/SIM 基线为 0），在 0.16.8 下同一快照实际命中 3/7/1/1/244，主分支自己会卡死棘轮。A 会话与 2FA：三处 logout 统一 `session.clear()`（此前只 pop `user_id`，`twofa_ok` 残留）、登录/注册/首次设密显式复位 `twofa_ok`、`/admin/logout` 进 2FA 放行清单、`/admin/login` 补 10/60s 限流与失败延迟。B 可见性收口：`Post.in_group()`/`hreflang_alternates()` 统一走 `visible_posts_query()`、`translations[]` 不再泄露私密/草稿、`/api/comments/reactions` 校验文章可见、`/api/tags` 与 `/api/site` 计数只算可见文章。C 限流：`client_key()` 改 `get_client_ip(strict=True)`，未配 `EO_AUTH_KEY` 时**不采信** `EO-Client-IP`（防假头绕过），博客圈匿名强制刷新 1/5min 静默回落缓存。F 设计系统：删 `--accent: var(--accent)` 自引用、默认品牌色统一 `#196ddd`、代码块换 `github-dark.css` 并对齐 `#0d1117`、元信息 13→14px（3.81:1 → 4.9:1）、标签 chip 改 `--text`、三处写死颜色改 token、两份 `tokens.css` 加 `--type-*` 尺度。**行为变化**：登出会清空 CSRF（前端已适配）、`/admin/login` 限流、限流键 strict IP。**实证**：ruff 0、全量 pytest 1311 passed、vite build 通过、新增 25 条回归测试。无迁移，head 仍 `b7c2e91a4d63`。

- **v5.3.0（2026-10-29 已发布）RSS 订阅入口 + 写文章相册素材/卡片 + /docs 单源**：① 访客侧 —— `/feed.xml` / `/feed.atom` 早已存在但**没有入口**，新增 `/feed` 订阅页（RSS 2.0 与 Atom 双源并列 + 一键复制 + 最近 5 篇佐证源是活的）与页脚 / 侧栏入口；地址用 `window.location.origin` 拼接、**不读后台 `SITE_URL`**，换域名 / 多域名时不会静默失效。② 写作侧 —— 编辑页新增「🖼 从相册选图」（`media-picker` 加 `album_id`，按**相册内 sort** 而非素材创建时间返回）与「🔗 插入相册卡片」（`picker-list` 含私密相册，卡片是否可见由渲染侧按 `is_public` 决定）；正文独占一段写 `@album[slug]` → `inject_album_cards()` 在**正文缓存之外**注入卡片，标题 / 摘要 / 地点 / 封面 URL 全 `_esc()`、**不扩 bleach 白名单**；私密相册与不存在的 slug **整段移除**（不泄露「存在一个叫 X 的私密相册」）。卡片样式三处各存一份（`admin.css` 后台实时预览 / `style.css` 预览页 / `look.css` 前台），守卫 `test_album_card_style.py`。③ 文档 —— `/docs` 改消费 `GET /api/docs`（读 `myblog/API.md` → `render_markdown`，mtime+size 缓存，失败返 `available:false` 而非 500），删除约 520 行手写摘要；`docs/adr/ADR-001` 记录决策。新增守卫 43 条（`test_post_album_card.py` 13 / `test_album_card_style.py` 23 / `test_feed_entry.py` 7），含「预算缓存不得吞掉卡片」「私密 slug 不得出现在公开 HTML」等变异已验证条目。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.6（2026-10-28 已发布）v5.2.5 视频播放按钮点不动 → 元素查找写错**：`videoElOf()` 原写「`querySelector('[data-video-id]')` 再在**其内部** `querySelector('video')`」，但 `data-video-id` 挂在 **`<video>` 自己**身上 → 内部无 video 子节点 → 恒为 `null` → `playVideo()` 首行 `if (!v) return` → **点播放按钮毫无反应**（视频能加载、时长正常，只有这一下失效，属静默失败）。修法：改用 Vue **函数式 ref** 直接持有元素（`videoEls` Map + `:ref="(el) => bindVideo(it.id, el)"`，两处卡片都绑），不再依赖 DOM 层级假设。新增 `tests/test_album_video_ref.py` 6 条守卫（含「`videoElOf` 函数体内不得出现任何 DOM 查询」），变异验证两次均变红。🔴 **教训**：修完用**手写探针页**验证是这次漏过的根因 —— 探针把 id 挂在容器上、真实组件挂在 video 自己身上，结构差异让验证结果失真 → **前端交互验证必须用真实组件**，不能用「手写等价物」。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.5（2026-10-28 已发布）API 文档全量重写 + 同步守卫 + 视频一直转圈/点击悬浮挡页面**：① 视频：宝塔全局 `proxy.conf` 的 `proxy_cache cache_one;` 让 nginx **剥掉 Range 头**（实测经 nginx 带 Range 返回 200+整个 17MB，直连 Flask 返回 206），而 mp4 的 moov 在文件尾部 → 浏览器必须下完整个文件才能读时长 → 视频一直转圈（实测 `readyState=0`）、三个视频一进页面就是 57MB；修法：nginx 新增 `location ^~ /static/uploads/` 用 root 直出（Range 原生支持 + 不再占 gunicorn worker）+ `/static/` 加 `proxy_cache off`（已授权、已备份、已 reload，经 nginx 带 Range → 206，三视频 `readyState=3`、时长 7.8/8.6/8.7 秒）；② 点视频触发移动端**原生全屏浮层**挡住整页 → 前台去掉原生 `controls` 改自绘播放按钮（JS `play()` + `playsinline` → 内联播放不接管，播放中才挂 controls），后台两处缩略图 `pointer-events:none`；竖屏视频两侧从纯黑改为卡片同色中性底。③ 文档：API.md 停在 v3.6.0 而代码已有 176 条 `/api/*` + 17 条后台 JSON 接口 → 清单从 `url_map` 枚举、逐条回源码核对（纠正 10 处与源码不符的描述）、新增 `tests/test_api_doc_sync.py` 5 条守卫（漏写/留残骸/死链/版本号），插件路由用独立探针 app 取 url_map（`load_plugins()` 在无插件目录时不注册蓝图）。无迁移，head 仍 `b7c2e91a4d63`。`myblog/API.md` 停在 v3.6.0，而代码已有 166 条 `/api/*`（含插件 4 条共 176 条）+ 17 条后台 JSON 接口，新增的十几个模块（相册/媒体/AI 摘要/生态/分享卡/表情/读者/回顾/主题/插件）**一条都没进文档**。改法不止是补写：清单从 `url_map` 枚举、逐条回源码核对（顺手纠错旧文档 10 处与源码不符的描述），并新增 `tests/test_api_doc_sync.py` 5 条守卫 —— 以后新增接口忘写文档、删接口忘删文档，测试立刻变红。插件路由因 `load_plugins()` 在无插件目录时提前 return 而未注册，测试用**独立探针 app** 取其 url_map。前台 `DocsView.vue` 同步 3 处约定文案（CSRF 白名单 / 分页口径 / 限流阈值）。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.4（2026-10-28 已发布）属主探测把 4 个 worker 的用户名拼成一个**：`ps -o user= --ppid` 返回**每个子进程一行**（4 行 `www`），而 `tr -d '[:space:]'` 把**换行也删了** → 拼成 `wwwwwwwwwww`（不存在的用户）→ `run_as` 全部静默降级为 root、`chown` 全部失败，但部署日志仍显示「✅ 全部完成」。修法：先 `head -1` 再去空白 + 校验探测结果是真实用户（`id` 校验）+ 其余 `ps` 读取统一补 `head -1`。线上已手工把 root 属主文件全部 chown 回 www 并清理 root 生成的 pyc（`data/backup/` 按设计不校正）。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.3（2026-10-28 已发布）部署脚本自更新认不出自己**：v5.2.2 部署日志暴露 —— `update.sh` 在 `cd "$WORK"` 之后才用 `readlink -f "$0"` 算自身路径，相对路径调用时解析成 `/tmp/llhhy_update/update.sh` ≠ 规范路径 → 自更新误判「不是同一个文件」而拒绝替换 → **线上 update.sh 永远停在旧版，所有脚本类改动都送不到服务器**（v5.2.2 承诺的「属主探测改看 worker」「⑤c 校正 data 属主」就是这么没上线的）。改为在任何 `cd` 之前捕获 `SELF_PATH_ABS`，判据一律用它；顺带把 `fix_data_owner` 的 `chown -R` 收窄到业务目录（不再改写 `data/backup/` 里的历史备份）。新增契约测试锁死捕获顺序。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.2（2026-10-28 已发布）编辑器被圆角裁掉 / 选图格子被压扁 / 大文件上传 500**：① 观感层把状态类 `view-split` 混进按钮规则，整个编辑器被设 999px 圆角、工具栏两端按钮被裁（只留 `.md-vw`）；② 选图网格 `grid-auto-rows: auto` 按 min-content 算高度，`aspect-ratio` 在 min-content 里算不出 → 每行只剩 85px、图片被裁成一条条（改 `minmax(96px, auto)` + 每格加名字）；③ `data/upload_tmp` 属主成了 root（`update.sh` 看 master 而非 worker），>16MB 分块上传必 500 返回 HTML → 前端报 `Unexpected token '<'`（线上 chown 恢复 + 后端翻 MediaError 507 + 前端 readJson + 部署脚本探测 worker 属主并 ⑤c 校正）。无迁移，head 仍 `b7c2e91a4d63`。
- **v5.2.1（2026-10-28 已发布）相册封面与名字同步修复**：① 相册列表永远显示「无封面」—— 取封面时写成 `[a.id for a in rows]`，拿**相册 id** 去查媒体表（两套自增序列，除偶然相等外必然查不到），改为 `cover_media_id`；② 名字只有一份 —— 编排页改名直接写 `media_asset.title`，v5.2.0 的 `album_item.caption` 冻结不再写入，迁移 `b7c2e91a4d63` 把历史图注合并进素材标题后清空。无表结构变更。
- **v5.2.0（2026-10-28 已发布）媒体库与相册双向打通**：相册编排页可直接上传并入册；媒体库每张素材可「加入相册」并显示所属相册标签（一次聚合查询，无 N+1）；图注留空自动回退显示素材标题（不复制、不写库，改标题会跟着变）。无迁移，head 仍 `a1c9e4f72b38`。
- **v5.1.4（2026-10-28 已发布）保存相册信息后页面变成 JSON**：表单提交 vs JSON 返回的契约不一致。改为按 `request.is_json` 分支（表单走 flash + 302，fetch 仍收 JSON），并全量排查后台 107 处 POST 表单确认无同类问题。
- **v5.1.3（2026-10-28 已发布）媒体选择器弹层关不掉**：`hidden` 属性被 `.album-picker-mask { display: flex }` 盖掉（UA 样式表优先级最低），弹层常显且「点关闭没响应」。加 `[hidden] { display: none !important }` 兜底 + 4 条守卫测试。
- **v5.1.2（2026-10-28 已发布）移动端抽屉滚动修复**：`overflow: hidden` 是简写，把抽屉与通知面板原有的 `overflow-y: auto` 一起重置，导致移动端菜单溢出 244px 却划不动。改为外层裁切 + 头尾固定 + 菜单区滚动（`min-height: 0`）。
- **v5.1.1（2026-10-28 已发布）相册正文渲染修复**：`**粗体**` 不再露出星号、段内换行保留 `<br>`（token 化 + 插值，仍不走 `v-html`）；后台 placeholder 改为明确列出支持的语法。
- **v5.1.0（2026-10-28 已发布）相册（媒体编排层）**：`media_asset` 回答「我有什么素材」，相册回答「这些素材怎么讲一个故事」—— 只引用 media_id，不复制文件。三张新表 `album` / `album_section`（可选章节）/ `album_item`；后台 `/admin/albums` 列表 + 编排页（章节增删改、媒体选择器搜索多选、图注、排序、设封面）；前台 `/gallery` 改为相册卡片墙，新增 `/album/<slug>` 游记页（封面大图、行程概览、章节图文、小提示、灯箱左右键翻页）。行程概览/小提示用「空行分段 + `- ` 转列表」纯文本解析，不引 markdown 库、不用 `v-html`。
- **v5.0.0（2026-10-28 已发布）媒体库升级为图床**：新增视频（mp4/m4v/mov/webm，图片 50MB /
  视频 500MB 分级上限）+ **8MB 分块上传**（绕开 gunicorn 30s timeout，500MB 单请求
  在国内上行要 80~250 秒，必被 kill）+ 新建 `media_asset` 表承载归档元数据
  （标题/分类/时长/封面/公开标记，不改既有表）+ 云存储外挂（OSS/COS/S3 与 WebDAV，
  独立于备份配置，密钥 Fernet 加密）+ 后台分栏归档页与前台 `/gallery` +
  正文 `![](x.mp4)` 自动渲染 `<video>`（`_RENDER_VERSION` 4→5）+ 上传前磁盘余量闸门。
- **v5.0.0（2026-10-28 已发布）游戏板块下线**：删 `api/games.py` / `admin/games.py` /
  `games_safety.py` / `tools/seed_games.py` / `Game` 模型 / 3 个模板 / 3 个前端页面
  与全部导航入口。**保留** `games_llm_*` 设置键（AI 摘要复用），配置入口迁到
  `/admin/ai-summary/llm-config`；`game` 表与 `data/games/` 数据不删。
- **v5.0.0（2026-10-28 已发布）前后台统一观感（圆润风格）**：**不换配色**（语义色被 WCAG 与 `themes.py._BASE_LIGHT` 双向绑定），靠形状/动效/层级出味道 —— 卡片 22px、按钮全胶囊、系统缓动 `cubic-bezier(.32,.72,0,1)` + 按压 `scale(.96)`、1px 发丝线 + 半透明填充、顶栏毛玻璃、导航大标题。后台侧栏激活项改为填充胶囊、表格改分组圆角。新增 21 条 `--ui-*` 令牌（两份 tokens.css 取值一致，暗色反相叠白）。
  ⚠️ **层叠顺序坑**：覆盖层必须单独 `styles/look.css` 并在 `responsive.css` **之后**导入 —— 放在 global.css 末尾会被 responsive.css:75 的 `.page-title` 压回旧值（构建通过但页面不变）。由 `tests/test_frontend_css_order.py` 锁住。
- **v5.0.0（2026-10-28 已发布）逐页精修三轮**：① 文章卡 / 分页 / 文章页阅读排版 / 侧栏
  ② 登录注册 / 留言墙 / 归档时间线 / 搜索结果（这些页面无 `<style scoped>`，改 `look.css` 即全站生效）
  ③ 后台 48 个模板的**跨模板结构类**（`.card` 系 / `.field` 系 / `.stat-card` / 编辑器 `.md-*`），
  一轮覆盖几十个模板。**命名用 `--ui-*` 与 `look.css`，不借用任何厂商产品名。**
- **v5.0.0（2026-10-28 已发布）生态统计优化**：离线站点超过 **24 小时无心跳自动从注册表硬删**
  （原仅 30 天「不展示」、行仍留库，导致 `total` 被早已离线的实例虚高）；
  生态统计从「关于」页独立成 `/ecosystem` 单独页面（抽屉 + 顶栏「更多」均加入口），
  关于页只保留本站「当前在线访客」；`stats()` 展示窗口同步收敛到 24h 并补
  `first_seen` / 带时分时间戳。`prune_stale_sites()` 用 `exclude_self` 排除本机
  key，保证中心站不会把自己误删。

## 三、待办

### 3.1 可选 / 小（真·待办，未做）

- **移动端第二批 ①「前台浏览」**：文章列表 / 正文 / 搜索 / 归档 / 分类标签系列页 / 微动态流 /
  博客圈 / 游戏与工具页 —— 基本无需新端点，是**原生 App 侧界面**，不在本仓库范围（②「数据与设置」
  已于 v4.10.0 落地）。
- **骨架屏 / 首屏预加载**：实测无 `UiSkeleton.vue`、前端零 `skeleton` 引用；当前响应 5~52ms，
  骨架屏是给慢网络用的，这里没有慢网络。
- **lint 棘轮欠债：BLE001 241 处 `except Exception`**：v4.10.0 已清零另外 5 类（F401 / S110 /
  SIM / T20 / ARG，合计 231 条），基线从 472 收到 **241**。剩下的盲捕获需要**逐条判断异常边界**
  ——改错会让本该兜底的路径真的炸掉，风险高于收益，留作专项。
- **站点设置移动端可写**：v4.10.0 只做了只读（白名单键）。写入要覆盖 30+ 键各自的校验规则，
  漏一条即配置损坏；网页端已有完整表单。
- **`admin.css` 重复定义合并**：`.admin-table` / `.hero-card` / `.card-body` 等存在 20+ 处
  同名类多定义（最多 21 处）。v4.11.0 只统一了「类名欠账 + 控件外观」，**没动重复定义** ——
  合并需要逐条判定覆盖关系（含媒体查询内外的叠加），改错会让某页突然变形，风险大于收益。
- **`run_check` 的 inputSchema 维度枚举**：19 个 key 目前是硬编码字符串。执行侧由
  `CHECKS_BY_KEY` 驱动（新增 checker 自动可用），但**描述**会过时。属文档漂移，非功能缺陷。

### 3.2 判定不做（有意识放弃，非遗漏）

- **实时在线**：单人博客无运营动作可依，无决策 / 告警价值。
- **A4 被 @ 后邮件提醒 / 周报月报 Digest / 送达退订追踪**：站内 @ 已落地；AI 周报系列本身就是 digest；订阅者 635 行、日活低，叠加邮件噪声 > 收益（退订追踪需新表，>2000 订阅再评估）。
- **评论精选 / 置顶**：comment 仅 2 行，无值得置顶者（>50 条且现长讨论再评估）。
- **内容多语言**：中文技术长文主体，翻译收益低且持续产生两版不同步的维护债。
- **图片 CDN**：图片量小，加速无感；配置化 CDN = 引入新回源真相源，与 `site_base()` 收口方向相反。
- **微信登录**：需企业 / 个体户主体 + 300 元 + ICP 备案主体一致，个人主体通过率极低；国内访客亦访问不到 GitHub/Google，第三方登录本质走不通。
- **APM / Sentry / 前端组件库 / PWA 离线**：维护成本 > 收益（单人博客），且组件化重写对功能零增益。
- **性能索引 / eager loading / N+1 / static gzip**：实测 post 8 行、最大表 635 行，全表扫描比索引快，加索引收益为零（`post>500` 或 p95>200ms 再评估）。

## 四、运维须知（极简）

- **库迁移**：`models.py` 定义即生效，重启由 `_migrate_*` 自动补列 / 建表；**生产禁用 `create_all`，走 Alembic**。
- **备份**：SQLite 启用 WAL，备份必须走在线备份 API，**不可直接 `cp blog.db`**（会丢 `-wal`）。
- 详细决策与取证日志、历史版本迭代：见 `docs/archive/ROADMAP_archive.md`。

## 五、旧章节索引（兼容映射）

瘦身时旧章节号整体搬到了归档件。代码 / 文档里已有的 `ROADMAP §x` 引用**继续有效**，按此表跳转：

| 旧编号 | 原内容 | 现在去哪 |
| --- | --- | --- |
| §1 现状基线 | 能力表 | 本文件 §一 |
| §2 功能地图 | 模块 A–F 明细 | 本文件 §二 |
| §3 分期计划 | 六期已完成 | `docs/archive/ROADMAP_archive.md` |
| §4 技术注意与风险 | 迁移 / 安全 / 性能 / 开源 | 归档件；要点摘要在本文件 §四 |
| §5.1 运营与分发 | 邮件模板、推送编排 | 归档件；待办见 §3.1「推送编排」 |
| §5.2 统计深度 | 环比 / CSV / 来源渠道 / 设备分布 | 归档件；**来源渠道 v3.17.3、设备分布 v4.9.0 已完成** |
| §5.3 互动与留存 | 积分勋章 / 评论排序 / 搜索历史 | 归档件；**搜索历史 v4.9.0 已完成** |
| §5.4 SEO / 拉新 | JSON-LD / canonical / 分享卡 | 归档件；**分享卡模板 v4.9.0、列表页 meta v4.10.0 已完成** |
| §5.5 内容运营 | 内容日历 / 多语言 / 图片 CDN | 归档件；**内容日历 v4.9.0 已完成**；不做项见 §3.2 |
| §5.6 工程 / 运维 / 安全 | v3.25.x 决策与教训全文 | 归档件 |
| §5.7 落地原则 | 各条目前置约束 | 归档件 |
| §5.8 第一轮审计延后批次 | 处置记录 | 归档件 |
| §5.9 / §5.9.1 第三轮复审 | 处置状态表、热表索引、lint 欠债 | 归档件；lint 欠债待办见 §3.1 |
| §B 前端质量 | a11y / 对比度 / token | 归档件 |
| 第 26~27 节 | 一键更新双源互证设计 | 归档件 |
| §六 ~ §73 | v2.6 → v3.17 逐版本迭代记录 | 归档件（另见 `CHANGELOG.md`） |
