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
