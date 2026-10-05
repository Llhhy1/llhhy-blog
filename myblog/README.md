# myblog · Flask 后端

llhhy-blog 的后端：Flask + SQLite，服务端渲染前台 + `/api/*` JSON 接口 + Jinja2 管理后台。

- 当前版本：**v3.25.7**
- **v3.25.7：第三方登录终于能用了** —— 大帅反馈「太难用」，查完发现是**从来就没能用过**。生产实测 `GET /api/auth/oauth/providers` → `{"providers":[]}`、`curl /login | grep -c -i oauth` → **0**；`LoginView.vue:35` 的条件是 `v-if="state.oauthProviders.length"`，空数组**整个区块不渲染**，访客登录页上**一个按钮都没有**。根因：v3.21.0 写完后端与前端，**唯独没留配置入口**（只能改环境变量 + 重启），绑定页也只写「改环境变量并重启」却没说去哪儿注册、回调地址填什么。本次补上**后台「🔑 第三方登录」配置页**（超管）：分步注册引导 + **回调地址照抄/一键复制** + **三档状态**（已启用 / **只填了一半·不生效** / 未启用）+ Secret **Fernet 加密**、留空保持原值、清除走显式动作；取值 **Setting 表 → 环境变量**（DB 优先是既定语义，env 保留兜底，老部署不失效）；回调地址推导收口到 `oauth.callback_url()` 纯函数供配置页与登录流程共用。**前端零改动**（按钮本就动态渲染）。**微信登录暂不做**：开放平台网站应用要企业主体 + 300 元 + 备案主体一致，个人主体申请不下来，已记 ROADMAP。**607 passed**（+16）/ ruff 全绿 / 四项变异全红。无表结构变更、无迁移、无新增依赖、前端产物无变化。⚠️ 附带发现 **lint 棘轮欠债**（BLE001 +9 / S110 +4 / SIM +21，非本次引入，是 v3.25.2~v3.25.6 发版时没跑棘轮攒下的），**未抬基线**。
- **v3.25.6：v3.25.5 上线核验抓到的三处收尾** —— 来源不是设计评审，是**上线后只读核验在生产实测**抓出来的。① **`sitemap.xml` 的 `<image:loc>` 一直是错的**：两层叠在一起 —— `cover` 语义是站内相对路径（`og_image._local_cover_path()` 只认 `static/`/`uploads/`），而 sitemap 规范要求 `image:loc` **必须是绝对 URL**；且生产有一篇 `cover` 存成了字符串 `'None'` → 实测输出 `<image:loc>None</image:loc>`。新增 `routes._sitemap_image_loc()`：判据**不是猜脏值长什么样**，而是与 `og_image` 同口径只放行站内路径并拼成绝对 URL，`site_url` 未配置时**不输出**。**另需一次生产数据修正**（把 `cover='None'` 改回 `''`）。② **证书状态文件三个时间字段口径不一致**（裸 UTC / 带 " UTC" / 北京时间混用）→ 诊断页「上次检查」看着早 8 小时，容易被读成「监控没跑」；统一北京时间。③ **填完 `site_url` 后证书检查要等第二天才跑**，「填完去看还是旧状态」正是本功能要消除的误导 → 保存时值变化即后台线程立刻重跑。**591 passed**（+17）/ ruff 全绿 / 四项变异全红。无表结构变更、无迁移（head 仍 `c7a2f19b4d30`）、前端产物无变化。
- **v3.25.5：补上 `site_url` 的配置入口** —— v3.25.4 说「顺手在站点设置填上 `site_url`」，**而那个输入框根本不存在**：`site_url` 一直被 `site_base()` 读取（canonical / og:url / sitemap / 分享卡片 / 邮件链接 / 证书监控全靠它），但后台**只有读取方没有写入方**（只能改环境变量或直接改库），SEO 页却一直红字警告并**链接到站点设置页** —— 把人指进死胡同。本次：站点设置页新增输入框（带 `<label for>`、说明影响范围、显示**实际生效**地址），保存前**清洗 + 校验**（只接受 `scheme://host[:port]`，拒非 http(s)、拒带路径/参数、剥 userinfo、去尾斜杠；**理由**：写坏不报错，只会静默让全站对外声明漂移）；校验不过只跳过该字段、其它照存并提示；同时进配置快照可回滚；SEO 页告警链接加 `#site_url` 锚点。**574 passed**（+22）/ ruff 全绿 / 三项变异全红（取消校验→11、不进可保存字段→5、输入框改名→1）。无表结构变更、无迁移（head 仍 `c7a2f19b4d30`）、前端产物无变化。
- **v3.25.4：证书监控修正** —— **v3.25.3 上线实证时抓到的自身缺陷**：生产 `site_url` 未配置 → `site_base()` 返回空 → 原实现**回落到 `socket.gethostname()`**，监控目标变成服务器名 `llhhy1` 而非对外域名。当时「碰巧准确」（nginx 只挂一个域名、两域名同证书），但**多 server 块 + 多证书时会静默失灵** —— 正是设计要防的假监控。已改为明确报 `unknown` + 提示配置 `site_url`，**不悄悄换目标**。**根本解决**：后台「设置 → 站点设置」填上 `site_url`（诊断页也一直在报这项，它还影响 sitemap/feed 绝对链接、分享卡片、canonical —— 证书监控只是这个老问题的又一个受害者）。**552 passed** / ruff 全绿 / 变异 3 条全红。
  改动：`cert_watch._target_host()` 拿不到域名时返回空串（不再回落本机名）+ `check_once()` 检测到空 host 时报 `unknown` 并提示配置 `site_url`；新增 3 条守卫（`test_no_host_falls_back_to_machine_name` / `test_missing_site_url_reports_unknown_not_ok` / `test_target_host_exception_falls_back_to_empty`）。
  **为什么测试没抓到**：写测试时用 monkeypatch 绕过了 `site_base()`，只覆盖「有域名」，**没测「域名取不到」** —— 由生产实测补上。**教训：mock 掉关键依赖时，要单独想一遍「它返回空/异常时会怎样」。**




- **v3.24.0：表结构改走 Alembic + 积分去重/保留策略 + Setting KV 治理** —— ⚠️ **含部署流程变更**：升级时必须在「覆盖后端后、重启前」执行一次 `BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app <venv>/bin/python -m flask db upgrade`（一键更新脚本已自动包含；手动升级务必手做）。**迁移含删除动作，升级前先备份 `blog.db`**。① **Alembic 首次真正在生产跑起来**：此前线上升级从不执行迁移，所有表结构变更靠 9 个启动自愈函数（`create_all()` + `_migrate_*`）完成，**只写在迁移脚本里的变更不会生效**——这是本版要修的根因。`update.sh` 新增迁移步骤（失败即中止且不重启，以站点用户执行避免 db 变 root 属主）。② **`BLOG_MIGRATE_ONLY=1` 迁移模式**：构造 app 但跳过建表/播种/FTS/超管兜底/插件加载等全部启动副作用，部署脚本**不必持有管理员凭据**。③ **9 个 `_migrate_*` 退役**，历史加列固化为幂等迁移 `d4a7f08c2e91` —— 消灭「Alembic + 手写自愈」两份 schema 真相源；数据播种拆出 `_seed_default_badges()` 并**无条件调用**。④ **积分 DB 级去重 + 保留策略**：`point_log` 唯一索引（迁移会删重复行，不去重索引建不出来）、`reader.points` 索引；`gamify.prune_retention()` 每日执行：reader 永久 / point_log 2 年 / reader_badge 随 reader。⑤ **定时发布原子认领**（`app.claim_scheduled_post()`）：多 worker 不再重复发布、重复推送、重复发订阅邮件。⑥ **`Setting` KV 治理**：评论表情 → `comment.reactions`、AI 摘要/标签 → `post.ai_summary`/`post.ai_tags`（**不新增表**，迁移 `e5b8c3f17a24` 搬迁并清理原 setting 行），设置表不再随内容无限增长，6 处全表加载随之瘦身，**对外接口与页面行为不变**。⑦ `create_app()` **510 行 → 35 行**（拆成 8 个私有函数，纯机械搬运零逻辑改动）。安全审计 **R96**。验证 **362 passed** + ruff 全绿 + 棘轮 601≤648 + i18n 通过 + 干净库迁移链串行通过 + 打包双源互证 20 项全通过。
- **v3.23.0：可观测性 + 后台任务 + OAuth 自助解绑 + CI 门禁** —— **无表结构变更、无新增必填环境变量**。① **后台「第三方绑定」页**（`admin/oauth_bindings.py`，R94 §94.8-7 收口）：查看/解绑自己的 OAuth 绑定；解绑需输登录密码（= 证明仍有可用登录方式，OAuth 建号者输不出随机密码即被挡住），超管可代查代解但不得解掉他人最后一个绑定；② **结构化日志**（`logging_setup.py`）：每请求 `X-Request-ID`（形态校验防日志注入、回写响应头），日志带 `rid=` 可按请求串联，新增可选 `LOG_LEVEL`（默认 INFO）；运行时 `print(` 清零（47 处转 logger，CLI stdout 刻意保留）；③ **后台长任务**（`tasks.py`）：状态落盘 `data/tasks/`（跨 worker 可见、原子写）、同名任务跨进程锁文件互斥 + 过期清理、异常落盘不外抛；**立即备份**（最长 300s）与**游戏上传 LLM 审计**（120s）改后台执行 + 页面轮询；④ **`/api/weather` 缓存**：10 分钟进程内缓存（限容 200），上游全故障回吐过期值；⑤ **CI**：前端 `npm audit` 门禁（基线 0 漏洞，须显式官方 registry）+ CodeQL（SAST 非阻断）；lint 棘轮修复转绿（T20 66→21）。安全审计 **R95**。验证 **342 passed** + ruff 全仓全绿 + 棘轮 602≤648 + i18n 通过。
- **v3.21.0：内容多语言 M1 + PWA + 读者积分勋章 + OAuth + 2FA** —— 四项新功能**默认全部休眠**（OAuth 需 provider 凭据、2FA 需 `BLOG_TWOFA_ENABLED=true`），**无新增必填环境变量、无新增依赖、无需改 Nginx、无需 Alembic**。① **多语言 M1**：`Post` 加 `lang` + `translation_group`，列表/详情支持 `?lang=` 且无译文自动回退原文，OG/sitemap/feed 输出 `hreflang` 互链；② **PWA**：`manifest.webmanifest` + `sw.js` + `offline.html` + 4 图标，导航 network-first、文章只读 API stale-while-revalidate，**后台与其余 `/api/*` 不缓存**；③ **积分勋章**（`gamify.py`）：匿名读者用 httpOnly cookie 标识，「同 reader + 同 reason + 同文章 + 同天」去重防刷，5 枚勋章按阈值自动授予，新增 `/api/reader/me` 与 `/api/reader/leaderboard`；④ **OAuth**（`oauth.py`）：GitHub / Google，出站固定白名单 URL + **禁跟随重定向**，未配凭据则 `start` 返 503；⑤ **2FA**（`twofa.py`）：**零新增依赖**（标准库实现 RFC 6238，官方 6 条测试向量自证），密钥 **Fernet 加密落库**、`last_counter` 防同窗重放、8 个一次性恢复码，关闭需「密码 + 动态码」双确认，走**新表** `UserTwoFactor`（SQLite `create_all()` 只建新表、不 ALTER 旧表）。新增 6 张表由 `_migrate_new_tables_v3()` **启动自愈**。🔴 **安全修复**：原实现用 GitHub `/user` 的**未验证公开邮箱**匹配本地账号 → 可被用来**接管他人账号**；已改为只信任 provider 断言「已验证」的邮箱。验证 **269 passed** + ruff 全绿 + 棘轮 648=648 + `vite build` 通过。安全审计 **R93**。
- **v3.20.0：待办清单批次（工程化门禁 + 异步化 + 可观测性 + 前端 a11y + 统计深度 + SEO 自动推送）** —— 把 `ROADMAP` §5.8/§5.9 的延后批次先实测再动手：① 工程化门禁 —— `pyproject.toml`（ruff 高信号阻断集）+ `tools/lint_debt.py` lint 债务棘轮（只减不增）+ CI `lint` job（i18n / 发布公钥一致性 / pip-audit CVE 扫描）+ `dependabot.yml` + `npm ci`；② `gunicorn_conf.py` 入库；③ `GET /api/health` 存活探针；④ `notify.py` 通知异步化（后台线程，原最坏阻塞 12s）；⑤ 前端 a11y —— skip-link、toast 常驻 live region、修 `DocsView` IntersectionObserver 真泄漏、灯箱 `role=dialog` + 完整焦点陷阱、每页 2 个 `<main>` 修复；⑥ `/api/qr` 不再用 `request.host_url`（闭环 R90 待办②）；⑦ Atom 1.0 `/feed.atom`（nginx 需补 `location = /feed.atom`）；⑧ 统计深度（零表变更）—— 来源渠道 TOP / 实时在线 / 趋势环比 / CSV 导出（BOM + 公式注入防护）；⑨ SEO 自动推送 —— 废弃实测不可用的 ping 端点（Bing 410 / Google 超时），改为发布即自动 `enqueue`（`maybe_auto_push`，默认关闭、只推可见文章、复用限流去重）。验证 **221 passed** + ruff 全绿 + 棘轮 648=648 + i18n 通过 + 覆盖率 49% + pip-audit 无漏洞。安全审计 **R92**。
- **v3.19.2：修正百度配额字段名** —— v3.19.1 上线后核对**生产真实数据**发现：百度主动推送的剩余配额字段是 **`remain`**，不是 `remaining`（实测响应 `{"remain":8,"success":1}`）。代码读错名字 → 剩余配额恒为 `None` → 「剩余配额」写不进 `seo_baidu_quota`（生产实测该键为空），收录页配额栏**一直空白**。`quota` 档仍被 `data["error"]` 的 `"over quota"` 分支兜住，所以**不是状态误判、只是信息缺失**（生产 7 篇推送全部 `ok`，真实 `success` 1~5，说明推送链路本身正常）。修复三处：① `data.get("remain", data.get("remaining"))` 两个名字都认；② `_RESP_KEYS` 加入 `remain`（否则白名单会把它连配额一起丢掉）；③ **更正 docstring 里那句错误示例** `{"success":2,"remaining":998}` —— 它正是这个 bug 的来源。**该缺陷第三轮复审报告未覆盖，由生产数据抓出。** 验证 **185 passed** + 变异测试（回退字段名 → 新断言变红）。
- **v3.19.1：第三轮复审修复（302 环 / 出站 SSRF / 自检放大面）** —— 修掉一个**已上线的可用性 + 收录事故**：v3.19.0 把「真人否决」无差别套在**两类桶**上，而 nginx 的 `map` 只按 UA 粗筛（**看不见请求头**），于是「带 `Accept: text/html` 的搜索引擎」与「QQ/微信内置浏览器真人」陷入**无限 302 环**（线上实测 Googlebot / Baiduspider / QQ 真人 **12 次重定向后仍是 302** → 搜索引擎抓不到正文、真人看到 `ERR_TOO_MANY_REDIRECTS`）。修法两处：① **否决作用域按桶拆分**（`utils/seo_shell.py`：`Sec-Fetch-*` 是浏览器专有头 → 两类桶都否决；**`Accept: text/html` 只否决社交桶**——真实 Googlebot 就会送它，拿它否决搜索引擎正是环的根因）；② **经通道的请求绝不 3xx**（`api/og.py` 出口 3 拆 3a/3b：直敲 API 无 `?seo=1` → 302 回公开地址；经通道但被否决 → 真人 **200 + `noindex` 可读页**、工具蜘蛛 **404 不给正文**）。同时修：出站**禁跟随重定向**（`_NoRedirect`，堵住「白名单 host 返回 302 → 任意 host 发 GET」的半盲 SSRF，已用两个本地服务实证并写成回归测试）、成功判定要求可解析 JSON + `Content-Type`、响应**只存白名单字段**（消内容回显）、**脱敏先于截断**（原顺序会漏抹截断点之后的 token）、`/api/seo/shell-check` **改为零出网（`test_request_context` 直调 `og_post`）+ 超管限定 + 限流**并改送**真实请求头**（原探针只送 UA —— 那正是线上环在自检里**假绿一整轮**的原因）、`/admin/seo/selfcheck` 改为**真调 `seo_shell_ua()`**（原先本地重写公式，缺两道否决）、后台线程异常不再静默（原先整批**永久停在「排队中」**）、审计改用统一 `log_audit()` **带 IP**、推送限流 3 次/5 分钟 + pending 去重、`keyLocation` 校验、彻底删除文章清 `SeoSubmission` 孤儿行、`og:description` 剥 Markdown、后台模板去 `innerHTML`、nginx map 补齐 13 个 token。验证 **185 passed**（+9 条新增，另有 6 条按新契约改写）+ `ruff` F821/E9 全绿 + **变异测试**（回退修复 → 13 条变红，证明非空转）+ 随机顺序同样全绿。安全审计 **R91**。
- **v3.19.0：后台「🔍 收录」控制台（阶段 2）** —— v3.18.9 把爬虫通道接通了（爬虫能拿到带正文的壳页），但「接通」不等于「被收录」，另一半是**主动告诉搜索引擎「我更新了」**。本版新增：① 新表 `SeoSubmission`（每篇 × 每引擎一行，**明确不用 Setting KV**——`Setting` 全表 `query.all()` 在 6 处被调用含每次模板渲染，长 KV 会把它变成 O(n) 负担；**迁移策略已记录为「暂由 `create_all` 自愈创建」**）；② `myblog/seo_push.py` 推送引擎（**百度主动推送** + **Bing/IndexNow**；百度官方地址是唯一的 http 出站目标，故白名单**精确比对 host**，四种绕过手法都有测试；批量**一次请求**而非逐篇发；`quota` 独立成档，修掉「`success:0,remaining:0` 被误判为 ok」的顺序坑）；③ 新增 `myblog/admin/seo.py` + `templates/admin/seo.html`：通道自检（含两个**真人**用例）/凭据表单（`encrypt_secret` 密文存储、掩码回显、显式清除、IndexNow key 规范校验）/批量与单篇推送/**按批一次**/文章状态列表/sitemap·robots 只读预览（**复用既有视图**）+ GSC·Bing·百度站长入口。**推送一律异步**（daemon 线程，接口立即返回，页面轮询），URL 恒由 `site_base()+"/post/"+slug` 生成。**Google 不做自动推送**（无通用 API，不造假的「提交成功」按钮）。顺带把 `og_image.py` 的 `.ttc` 字重匹配缺陷修掉，并把文泉驿微米黑补入 `static/fonts/`（关闭 v3.18.9 的待决策项）。验证 **171 passed**（+29 条） + ruff F821/E9 全绿，开发库 sha256/mtime 零变化。
- **v3.18.9：SEO 爬虫通道修复（阶段 1）** —— 阶段 0 真机自查发现线上 nginx **早有一条手工爬虫规则**（`location ~ ^/post/` 的 `if ($http_user_agent ~* "(bot|spider|crawl|…")` → `rewrite /api/og/post/$1`），但**从未入库 deploy_guide.md**；且后端那个页面**恒发 `X-Robots-Tag: noindex,nofollow` 且 canonical 指向 `/api/og/post/<slug>`** → 百度能被引导进来、进来后立刻被告知「勿收录」，等于**接通通道反而杀死收录**；微信则根本进不来（`detect_bot()` 认不出 `MicroMessenger`）。本版重做为三个互斥出口（不可见→404+noindex；经通道+抓取方→200 壳页+**index,follow**+公开 canonical；其余→302 回 `/post/<slug>`），新增独立闸门 `utils/seo_shell.py`（两层：搜索引擎/社交预览 UA 白名单 + **真人信号否决** `Sec-Fetch-Mode: navigate`/`Accept: text/html`/站内 Referer），修复 meta 页与 `.png` 分享卡**两处都漏 `scheduled_at`** 的可见性缺陷，壳页带正文（复用 `content_html` 缓存列）+ `BlogPosting`/`BreadcrumbList` JSON-LD，站点地址收敛为 `utils.site_base()` 唯一真相源（**删除 `request.url_root`/`request.host` 回退**），Nginx 配置**原文入库**并线上更新（`nginx -t` 通过）。新增 `/api/seo/shell-check` 后台通道自检（4 种身份实测）。另查出并修复**分享卡 `.png` 自 v3.16.0 起一直返回兜底图**的三层叠加故障（字体缺失 → 宝塔图片正则压过 `^~ /api/` → 全局 `proxy_cache` 缓存了兜底图）。验证 **142 passed** + ruff F821/E9 全绿，含变异测试验证断言有效性。
- **v3.18.8：修复 v3.18.7 上线实测发现的验签顺序缺陷**——`$WORK`（`/tmp/llhhy_update`）跨轮复用且原先只清解压目录，导致上一轮遗留的 `sha256.txt` 被拿来与本轮新的 `sha256.txt.sig` 配对比对 → 必然验签失败（v3.18.7 首次上线即 BAD；站点未受影响，fail-closed 在覆盖代码前就拒绝了安装）。修复：验签函数内部**先清旧清单再自行下载两者**（自包含），`$WORK` 准备阶段显式清清单与 zip，并新增契约测试钉死。验证 **126 passed** + 服务器端到端实跑全绿。
- **v3.18.7：更新链 fail-closed + Ed25519 发布物签名**——`package.py` 打包后对 `sha256.txt` 做 Ed25519 分离签名（新资产 `sha256.txt.sig`，首次运行自动生成密钥对到 `~/.workbuddy/llhhy_release_key`）；`update.sh`/`deploy.sh` **内置验签公钥**（`BUILTIN_RELEASE_PUBKEY`，可被 `RELEASE_PUBKEY` 覆盖）→ 任何人 clone 部署开箱即可获得签名保护。7 处 fail-open 全转 fail-closed（签名缺失/验签失败/清单查不到文件/注释双源互证失败/无 python3 一律终止），**不再自动兜底第三方镜像**（只认显式 `GH_MIRROR`）；新增版本单调性（默认拒降级，`ALLOW_DOWNGRADE=1` 放行）与 `ALLOW_UNSIGNED=1` 显式逃生舱。`deploy.sh` 收敛为 `update.sh` 的薄封装（历史上是副本且校验更弱）。`verify_package_checksums.py` 增加**双源互证 ③**（用 update.sh 里读出的同一公钥验签）。验证 **125 passed** + 反向实测 20/20。
- **v3.18.6：退役公共 SSR（单前端）**——生产 Nginx 只反代 `/api/` `/admin` `/static/` `/mcp*` 与 `feed.xml`/`sitemap.xml`/`robots.txt`/`feed/comments`，其余由 Vue SPA 兜底，故 `routes.py` 中 8 个页面级 SSR 路由（`/`、`/post/<slug>`、`/category/<slug>`、`/tag/<slug>`、`/search`、`/about`、`/links`、`/archive`）在生产从未被访问 → **退役为 410 Gone** 并**删除 7 个对应模板**（`myblog/templates/` 顶层仅剩 `base.html`/`login.html`/`register.html`/错误页 5 个）。**endpoint 名一律保留**（`base.html` 的 `url_for` 依赖它们，删路由会让登录页 `BuildError`）；`/login` `/register` `/logout` 仍为 SSR，`/post/<slug>/comment`、`/post/<slug>/like` 两个 POST 入口保留。验证 119 passed。
- **文档口径更正（v3.18.5 · 依据第三方独立审计 §10）**：① 「后台表格手机端可浏览全文」**不成立**——卡片化依赖 `td[data-label]`，22 个表格模板只有 2 个写了（补齐见 ROADMAP §5.8）；② 「硬编码颜色已统一替换为 token」**部分不成立**——`admin.css` 与 `global.css` 各残留约 230~250 处裸 hex，两份 `tokens.css` 为手工复制；③ 「全站时间统一北京时间」在本版**已真正落地**（7 处 Jinja 模板改用 `bj` 过滤器、`/api/games` 改用 `fmt_bj`）；④ ~~「文章页动态 OG」实现于 Vue 客户端，当前 Nginx 下服务端 JSON-LD/OG 抓不到流量，对国内 SEO 近似无效~~ → **v3.18.9 已修复**：爬虫/社交抓取走 nginx UA 分流到 `/api/og/post/<slug>`，服务端输出正文 + canonical + JSON-LD，百度可读（配置原文见 `deploy_guide.md`「第 4b 步」）；⑤ 「14 套 OKLCH 主题保证对比可读」不等价于 WCAG —— `derive_dark` 只钳 L，无亮度校验环。
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
├── app.py          # 应用工厂（35 行；v3.24.0 起表结构由 Alembic 迁移负责，不再启动自愈）
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
│                   #   ai_summary.py = AI 摘要管理（v3.17.7）；seo.py = 收录控制台（v3.19.0）
│                   #   twofa.py = 两步验证绑定页（v3.21.0，与 /api/auth/2fa/* 共用 twofa 服务层）
│                   #   oauth_bindings.py = 第三方账号绑定/解绑（v3.23.0，账号安全项）
├── seo_push.py     # 主动推送引擎（v3.19.0）：百度主动推送 + Bing/IndexNow，异步、host 白名单
├── oauth.py        # v3.21.0 OAuth 第三方登录（GitHub/Google，config-gated，禁跟随重定向）
├── twofa.py        # v3.21.0 双因素认证：TOTP（标准库实现 RFC 6238）+ 业务操作层（API/后台共用）
├── gamify.py       # v3.21.0 读者积分勋章（cookie 标识读者、去重发放、阈值授勋、排行榜）
├── api/            # JSON 接口（/api/*，按功能拆分，见 API.md）
├── mcp_diag.py     # 只读诊断 MCP 端点 /mcp（v3.10.0，见文末说明）
├── mcp_write.py    # 写能力 MCP 端点 /mcp-write（v3.12.2，默认草稿、fail-closed）
├── plugins/        # 插件系统 v3.9.0（<slug>/ 目录 + signals.py 事件总线）
│                   #   v3.10.0 起仓库不再内置插件，放目录 + 填 ENABLED_PLUGINS 即启用
├── fts.py          # SQLite FTS5 全文搜索（不可用时降级 LIKE）
├── tasks.py        # 后台长任务（v3.23.0）：状态落盘 data/tasks/、同名任务锁文件互斥、
│                   #   立即备份 / 游戏 LLM 审计走它，不再占死 gunicorn 并发槽
├── logging_setup.py  # 结构化日志（v3.23.0）：request_id 中间件 + rid= 日志格式 + LOG_LEVEL
├── stats.py        # 访问统计与 IP 属地解析
├── backup.py       # 数据备份与异地容灾（本地/OSS/SCP/WebDAV）
├── bot_guard.py    # 反爬限流（默认关闭）
├── security.py     # 安全响应头 / 图形验证码 / CSRF
├── config.py       # 配置（含 APP_VERSION）
├── migrations/     # Flask-Migrate / Alembic 迁移（v3.11.0 起；基线对齐 v3.10.6）
├── API.md          # 全部 /api/* 端点文档
├── SECURITY_AUDIT.md  # 安全审计报告（R81 起；R1~R80 已归档至 ../docs/archive/）
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
- **v3.24.0 起手动升级必须跑迁移**：v3.24.0 之前表结构变更靠启动自愈，v3.24.0 起改由 Alembic 承担。
  手动覆盖代码后、重启前须执行一次
  `BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app <venv>/bin/python -m flask db upgrade`，
  否则迁移里的索引/列不会落到生产（用一键更新脚本 `update.sh` 的无需手动做）。
  `BLOG_MIGRATE_ONLY=1` 让迁移跳过全部启动副作用，因此**无需提供 `SECRET_KEY`/`ADMIN_PASSWORD`**。
  可用 `flask db heads` 确认当前应为 `e5b8c3f17a24 (head)`。
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
