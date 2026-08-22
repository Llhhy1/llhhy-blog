# 安全审计报告（SECURITY_AUDIT.md）

> 审计时间：**第一轮 2026-08-20 · 第二轮 2026-08-21** · 审计对象：myblog（Flask 后端）+ vue-frontend（Vue3 前端）
> 审计目标：以**开源前最严格标准**核查代码并修复安全问题；本文件随代码同步交付。
> 第一轮修复验证：本地自动化验证脚本覆盖 7 项关键行为（XSS 清理 / CORS 关闭 / 跨站拦截 / 开放重定向 / 登录限流 / 评论存储 / 缺失密钥拒绝启动），**全部通过**。
> 第二轮修复验证：端到端冒烟测试覆盖 12 项新功能行为（系列 / 公告 / 留言墙 / 订阅 / FTS5 搜索 / 相关文章 / Webhook 部署鉴权 / 嵌套评论 / 公告 Markdown 渲染等），**全部通过**。

---

## 一、审计结论

发现并修复 **1 个严重、6 个高危、4 个中危** 问题。修复后无遗留严重/高危问题。

## 二、发现的问题与修复

### 🔴 严重

| # | 问题 | 修复 |
|---|---|---|
| S1 | `app.py` 直接运行入口 `debug=True` 且监听 `0.0.0.0`：若误用 `python app.py` 启动生产，Werkzeug 调试器可被远程利用执行代码（RCE） | 改为 `debug=False` 且仅监听 `127.0.0.1`（生产走 Nginx → gunicorn 反代，不暴露 5000 端口） |

### 🟠 高危

| # | 问题 | 修复 |
|---|---|---|
| H1 | `SECRET_KEY` 内置弱默认值 `please-change-this-secret-key`：未配置时可用已知密钥伪造任意用户（含超管）会话 | 改为**必须**从环境变量读取，缺失直接拒绝启动 |
| H2 | `ADMIN_PASSWORD` 内置默认值 `admin123`：首次部署若未配置会创建弱密码超管 | 同上，必须从环境变量读取，缺失拒绝启动；首次登录仍强制修改账号密码 |
| H3 | CORS 默认 `*`：任意网站可跨域读取接口响应，并对登录/注册接口无限制调用 | 默认**关闭** CORS；仅显式配置允许的前端来源时才开启并精确匹配 |
| H4 | 文章/关于页 Markdown 渲染不过滤 HTML，且前端用 `innerHTML`/`v-html` 渲染 → 存储型 XSS | 新增 `bleach` 白名单清理，统一 `render_markdown()` / `clean_html()` 出口，剥离 script、事件属性、危险协议 |
| H5 | 登录/注册/评论/点赞等写接口无防护：可暴力破解、刷量、灌垃圾 | 会话 Cookie `SameSite=Lax` + 全局同源校验（跨站 POST 返回 403）+ 每 IP 限流（登录/注册 10 次/60s、评论 10 次/60s、点赞 20 次/60s/篇） |
| H6 | 登录回跳 `next` 参数未校验 → 开放重定向（钓鱼） | 新增 `safe_redirect()`：仅允许站内相对路径，拒绝 `//` 开头的协议相对地址 |
| H7 | 会话 Cookie 未显式设置 `Secure`/`HttpOnly`/`SameSite` | 配置 `SESSION_COOKIE_SECURE`（默认 true，可 `COOKIE_SECURE=false` 覆盖本地）、`HttpOnly=True`、`SameSite=Lax` |

### 🟡 中危

| # | 问题 | 修复 |
|---|---|---|
| M1 | 上传允许 `svg`：SVG 可内嵌脚本，直接访问 URL 时可能执行 JS | 从允许扩展名移除 `svg`（仅 png/jpg/jpeg/gif/webp） |
| M2 | 前端通过外部 CDN（bootcdn）动态加载 highlight.js：CDN 被劫持可注入任意脚本（供应链风险） | 改为**本地打包** highlight.js，按需注册常用语言；顺带把文章页 JS 从 985KB 压到 73KB |
| M3 | 公开注册无开关，任何人可无限注册 | 新增 `BLOG_OPEN_REGISTER` 环境变量（默认开，可设 `false` 关闭） |
| M4 | IP 属地接口 `http://ip-api.com` 明文传输 | 改为 HTTPS |

## 三、改动文件清单

- **后端 `myblog/`**：`config.py`、`app.py`、`utils.py`、`routes.py`、`api.py`、`admin.py`、`stats.py`、`requirements.txt`（新增 `bleach`）、`README.md`、`deploy_guide.md`
- **前端 `vue-frontend/`**：`src/views/PostView.vue`（highlight.js 本地化）
- **第二轮新增**：`myblog/fts.py`（FTS5 搜索）、`myblog/notify.py`（推送通知）、`myblog/SECURITY_AUDIT.md`（第二轮章节）；`models.py` 扩展 `Series/Announcement/Guestbook/Subscriber` 及 `Comment.parent_id/reply_to/likes`；`api.py` 新增系列/公告/留言墙/订阅/搜索/Webhook 路由；`admin.py` 新增系列/公告/留言/订阅管理页；前端新增 `SeriesView / SeriesDetailView / GuestbookView`、`CommentForm` 嵌套回复、`Sidebar` 热门、全局公告条等

- **第三轮新增（v2.3.0）**：`myblog/mail_notify.py`（邮件群发）、`models.py` 新增 `Notification` 及 `Subscriber.unsub_token`、`utils.py` 新增 `get_setting/setting_bool/notify_mentioned`、`api.py` 新增通知/退订/部署触发路由、`admin.py` 新增评论审核路由与设置开关、前端新增 `UnsubscribeView` 与通知铃铛

## 四、第二轮安全审计（2026-08-21 · 新增模块 B1/B2/B4/B5/C1/C2/C3/D1/D2/D3/D4 + 广场页）

本轮在「全部功能一次性做完 + 开源前」节点，对新增的全部模块做安全复查，并补了一个**功能性 + 安全配置**缺陷。

### 4.1 发现的缺陷与修复

| # | 等级 | 问题 | 修复 |
|---|---|---|---|
| R1 | 🟠 高（功能性/配置） | Webhook 自动部署接口 `/api/webhook/deploy` 始终返回 403：路由从 `current_app.config["WH_DEPLOY_SECRET"]` 读取密钥，但 `Config` 从未把环境变量 `WH_DEPLOY_SECRET` 载入配置，导致密钥恒为 `None`，**任何部署触发都被拒绝** | 在 `config.py` 的 `Config` 中显式声明 `WH_DEPLOY_SECRET = os.environ.get("WH_DEPLOY_SECRET")`（及推送通知所需的 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `WECOM_WEBHOOK_URL`），使环境变量成为单一可信来源；接口逻辑不变（HMAC `compare_digest` 恒定时间比较） |
| R2 | 🟢 改进 | 数据库路径写死 `data/blog.db`，不便隔离测试，也不利于切换到 Postgres/MySQL | `Config.SQLALCHEMY_DATABASE_URI` 支持 `DATABASE_URL` 环境变量覆盖（保留 SQLite 默认值）；非 SQLite 时 FTS5 自动降级为 LIKE，已验证 |

### 4.2 新增模块安全复查结论（全部通过既有防护，无新漏洞）

| 模块 | 关键风险点 | 结论 |
|---|---|---|
| B5 全文搜索 `fts.py` | SQL 注入 | 全部参数化（`:rid`/`:q`/`:lim`），查询经 FTS5 MATCH 绑定参数，绝无字符串拼接；FTS5 不可用时 `available()` 返回 False 并回退 LIKE，不报错中断 |
| C1 留言墙 | 存储型 XSS / 刷量 | 内容以纯文本存储，前端用 `{{ }}` 插值渲染（Vue 自动转义）；未登录可留（限 500 字）+ 每 IP 限流 10 次/60s |
| C2 嵌套评论回复 | 越权回复 / XSS | `parent_id` 校验必须属于同一篇文章（`filter_by(id=parent_id, post_id=p.id)`），杜绝跨文章回复注入；内容 `{{ }}` 文本渲染 |
| C3 邮件订阅 | 注入 / 刷量 | 邮箱正则校验 `^[^@\s]+@[^@\s]+\.[^@\s]+$`，去重；每 IP 限流 10 次/60s |
| D4 站点公告 | 存储型 XSS | 内容经 `clean_html(render_markdown(...))` 白名单清洗后返回，前端 `v-html` 安全 |
| D2 推送通知 `notify.py` | SSRF / 密钥泄露 | 仅向固定域名（`api.telegram.org`、企业微信机器人 Webhook）POST，URL 来自环境变量（非用户输入）；未配置渠道静默跳过，异常不阻断发文章主流程 |
| D3 Webhook 部署 | 未授权触发 | `WH_DEPLOY_SECRET` 缺失即 403；请求需带 `X-Deploy-Token` 头或 `?token=`，与配置值做恒定时间比较；配合全局同源校验（跨站 POST 自动 403） |
| 广场页 RSS 聚合 `feed_agg.py` | SSRF / 外部 XSS | `_safe_url()` 拦截内网/回环地址；外部摘要经 `clean_html()` 清洗后前端 `v-html` 安全；15 分钟内存缓存 |

### 4.3 全量复查要点（沿用第一轮机制，确认仍生效）

- **XSS**：所有 Markdown/HTML 出口统一 `render_markdown()` / `clean_html()`；评论、留言、动态等内容纯文本渲染。
- **CSRF**：`enforce_same_origin` 对 POST/PUT/DELETE/PATCH 校验 Origin，跨站请求 403；配合 `SameSite=Lax` Cookie。
- **限流**：写接口全部限流；本轮新增留言墙、订阅、嵌套评论、微动态评论均接入。
- **密钥管理**：`SECRET_KEY` / `ADMIN_PASSWORD` 强制环境变量；本轮补齐 `WH_DEPLOY_SECRET` 等部署/推送密钥的环境变量载入；**仓库内无硬编码密钥、无 `.env` 入库**（已校验）。
- **SQL 注入**：ORM 查询 + 参数化原生 SQL，新模块无例外。

## 四·补、第三轮安全审计（2026-08-21 · v2.3.0 评论审核流 + @通知 + 邮件群发 + 自动部署触发）

> 审计原则：**每次发布前必须执行完整安全审计，审计通过后才允许发 Release**。本轮在 v2.3.0 发布前执行。

### 4A.1 发现的缺陷与修复

| # | 等级 | 问题 | 修复 |
|---|---|---|---|
| R2 | 🔴 高 | 邮件群发 HTML 注入：`mail_notify._build_mail()` 把文章标题/摘要、退订邮箱直接拼进 HTML 邮件模板，未转义。文章标题含 `<script>` 或 HTML 标签时会被注入邮件正文；退订链接中的 email 未 URL 编码（含 `&` 等会破坏链接），token 未编码 | 标题/摘要 `html.escape()`；退订链接 email/token 用 `urllib.parse.quote(safe="")` 编码后再填充；邮件主题用 `email.header.Header` 编码，阻止换行注入（标题含 `\r\n` 时安全处理） |
| R3 | 🟠 中 | Webhook 部署触发 `subprocess.Popen` 每次 `open(os.devnull)` 且**从不关闭** → 文件描述符泄漏，长期高频触发可能耗尽 fd | 改用 `subprocess.DEVNULL` 重定向输出（自动管理，无泄漏） |
| R4 | 🟢 低 | 退订接口错误信息可**枚举有效邮箱**（"该邮箱未订阅"与"令牌不正确"两种提示不同）；POST 退订无速率限制 | 统一错误信息为「退订链接无效或已失效」（404），杜绝枚举；POST 退订接入 `rate_limit` 10 次/60s |

### 4A.2 新增模块安全复查结论

| 模块 | 关键风险点 | 结论 |
|---|---|---|
| A4 站内通知 `Notification` | @ 解析注入 / 越权读取 | `notify_mentioned` 用正则提取 `@username` 后 `filter_by(username=name)` **参数化查询**，不存在注入；通知按 `user_id` 归属，列表/已读接口均 `filter_by(user_id=当前会话)`，无法读他人通知；内容存纯文本，前端 `{{ }}` 插值渲染 |
| 评论审核流 | 越权审核 / 前台越权可见 | 审核接口 `@admin_required`；前台 `post_detail` 只返回 `approved=True` 的评论；开关存 setting 表（`comment_require_approval`），后台仅超管可改 |
| C3 邮件群发 `mail_notify.py` | 注入 / 凭据泄露 / 隐私 | 见 R2 修复；SMTP 凭据仅环境变量（`SMTP_HOST/USERNAME/PASSWORD`），不入库不入仓；收件人全部 Bcc 密送（互不可见）；未配置 SMTP 自动跳过；全部异常静默不阻断发文章 |
| D3 自动部署触发 | 未授权执行脚本 / 命令注入 | 密钥 HMAC 恒定时间比较，缺失即 403；`DEPLOY_SCRIPT` 来自环境变量（管理员配置，非用户输入）；`Popen(["bash", script])` 列表参数**无 shell 拼接**，不存在命令注入；见 R3 修复 |

### 4A.3 上线前新增必配（可选）环境变量

- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_SSL`：邮件群发（多数邮箱用「授权码」当密码；465 用 SSL，587 一般 `SMTP_USE_SSL=false` 走 STARTTLS）。**不配置则群发自动跳过**。
- `DEPLOY_SCRIPT`：Webhook 校验通过后要执行的部署脚本绝对路径（如 `/www/wwwroot/myblog/deploy.sh`）。**不配置则 webhook 只返回授权成功，不执行任何操作（安全默认）**。
- `COMMENT_REQUIRE_APPROVAL`：环境变量默认值；后台「站点设置」可动态覆盖。

## 四·补二、第四轮安全审计（2026-08-21 · v2.4.0 后台邮件设置 + 自动部署脚本）

> 本轮新增：后台「邮件设置」菜单（SMTP 配置存 Setting 表 + 测试发送）、`deploy.sh` 自动部署脚本模板。

### 4B.1 发现的缺陷与修复

| # | 等级 | 问题 | 修复 |
|---|---|---|---|
| — | — | 本轮审计未发现需修复的漏洞 | 见下方复查结论 |

### 4B.2 新增模块安全复查结论

| 模块 | 关键风险点 | 结论 |
|---|---|---|
| 后台「邮件设置」`/admin/email-settings` | 越权 / 密码泄露 / 滥用发信 | 路由 `@super_required` 仅超管可访问（未登录访问已验证 403）；SMTP 授权码存 Setting 表但**页面永不回显**（GET 不返回已存密码，保存时留空=保持不变，已验证）；「发送测试邮件」限流 5 次/300 秒（防滥用群发）；POST 被全局同源 CSRF 校验覆盖 |
| `mail_notify.load_mail_config()` | 注入 / 配置篡改 | 读取 Setting 表参数化查询（`filter_by`）；配置仅超管可写；未配置 host/username 时静默跳过群发，不报错不阻塞 |
| `deploy.sh` 脚本模板 | 执行任意命令 | 仅由 Webhook 触发（HMAC 校验 + `DEPLOY_SCRIPT` 环境变量白名单）；脚本内容由管理员自行维护，仓库中为模板示例，不含任何硬编码凭据 |

### 4B.3 残余风险（记录）

- SMTP 授权码**明文存储**于数据库 Setting 表（与站点其他配置同级）。依赖「仅超管可访问后台 + 数据库文件在服务器本地」的边界；如需更强保护，可改为仅用环境变量 `SMTP_PASSWORD`（后台留空即可）。

## 四·补三、第五轮安全审计（2026-08-21 · v2.5.0 后台一键在线更新）

> 本轮新增：后台登录后自动检测新版本 → 超管确认 → 后台静默执行 `update.sh`（下载→备份→覆盖→自动重启）→ 完成提醒刷新。

### 5.1 发现的缺陷与修复

| # | 等级 | 问题 | 修复 |
|---|---|---|---|
| R5 | 🟠 中 | `/api/version/update` 初始实现仅校验「已登录」，**任何登录用户（普通 user 角色）都能触发服务器代码更新**（越权） | 增加 `is_admin_role`（超管/管理员）权限判断，普通用户返回 403；已用测试客户端验证（普通用户 403 / 超管 200） |

### 5.2 新增模块安全复查结论

| 模块 | 关键风险点 | 结论 |
|---|---|---|
| `/api/version/check` | SSRF / 信息泄露 | URL 固定指向 `api.github.com/repos/Llhhy1/llhhy-blog/releases/latest`（硬编码，非用户输入），8 秒超时 + 失败回退缓存，无 SSRF；返回仅 current/latest 两个版本号，无敏感信息；只读接口 |
| `/api/version/update` | 越权触发 / 滥用 / 命令注入 | 见 R5 修复；`rate_limit` 3 次/小时；**防重入锁**（状态文件 status 为进行中则 409 拒绝）；脚本路径来自 `DEPLOY_SCRIPT` 环境变量或仓库根 `update.sh`（管理员可控，非用户输入）；`Popen(["bash", script])` 列表参数**无 shell 拼接**，不存在命令注入 |
| `/api/version/status` | 信息泄露 | 仅返回更新状态 JSON（status/version/ts/message），无敏感数据；只读 |
| `update.sh` 状态文件 | 篡改 / 注入 | 状态写入 `$APP_DIR/data/update_status.json`（服务器本地），内容为脚本内固定枚举值 + 版本号；JSON 序列化安全；`fail_exit` + `trap EXIT` 保证失败必标记，不会停留在"更新中"假象 |
| 后台前端 JS | XSS | 版本号/消息经 `textContent` 注入 DOM（非 innerHTML），无 XSS 面；fetch 同源调用 |

### 5.3 上线前必配（可选）

- 无需新增必填环境变量。`update.sh` 需已上传到服务器（默认路径 `myblog/update.sh`，即 `/www/wwwroot/myblog/update.sh`，或配置 `DEPLOY_SCRIPT` 指向其他位置）；未找到脚本时接口返回 400 提示。

## 四·补四、第五轮审计·补（2026-08-21 · v2.5.1 版本比较 bug 修复 + 检查更新改后台判断）

> v2.5.0 上线后用户反馈「当前已是 2.5.0 仍提示更新」，为发布后紧急修复补丁。

### 5A.1 发现的缺陷与修复

| # | 等级 | 问题 | 修复 |
|---|---|---|---|
| R6 | 🟠 中（功能性） | `/api/version/check` 用**字符串比较**判断是否有新版：`"v2.5.0" > "2.5.0"` 因首字符 `'v'`(118) > `'2'`(50) **恒为 True**，导致任何版本都误报「有新版本」；且字符串比较会把 `v2.10.0` 误判为小于 `v2.5.0`（`'1' < '5'`） | 改为规范化后 **tuple 整数比较**：去掉 `v/V` 前缀 → 按 `.` 拆分转 int tuple → `l_t > c_t` 判定；8 个场景测试（同版本/升级/降级/多位数/空值/补丁级/位数不同）全部通过 |

### 5A.2 行为变更（用户要求）

- **「检查更新」不再跳转 GitHub**：点击侧边栏左下角版本号旁的「检查更新」，改为后台直接调 `/api/version/check`——有新版本则在底部弹出推荐更新条（含「立即更新」）；已是新版则提示「✅ 当前已是最新版本」2.5 秒后消失；网络失败提示稍后再试。更新条展示范围由「仅超管」放宽到「超管/管理员」（`is_admin_role`），与后端触发权限一致（普通用户无后台访问权限）。

## 四·补五、第六轮审计（2026-08-21 · v2.5.2 移动端排版修复）

> 用户反馈前台和后台在手机端排版错位：后台侧栏菜单文字"写新文章"被切成"写新文"+"章"；前台顶部 8 个 nav 链接挤在一行被压缩。本轮纯 CSS 样式修复。

### 6.1 审计结论

- 无新漏洞（纯 CSS 改动，**无注入面**，不影响任何后端逻辑或前端 JS）
- 修改文件：`myblog/static/admin.css`（侧栏 2 列网格 + nowrap + ellipsis + hero 按钮列堆叠）、`vue-frontend/src/styles/global.css`（header-inner flex-wrap + nav 换行 + 缩间距）
- 行为变更：仅 CSS 响应式断点（≤820px / ≤480px）排版，不改变任何功能

## 四·补七、第七轮审计（2026-08-21 · v2.5.3 后台响应式系统重构）

> 用户反馈后台在不同分辨率下排版仍不正确，系统性重构后台响应式体系（纯 CSS，四级断点）。

### 7.1 审计结论

- 无新漏洞（纯 CSS 改动，**无注入面**，不影响任何后端逻辑或前端 JS）
- 修改文件：`myblog/static/admin.css`（新增完整响应式体系，删除旧 820/480 冲突块）
- 断点体系：`≤1100px` 侧栏收窄/主区 padding 缩小/dash-grid 单列；`≤900px` 侧栏置顶 + 表格容器级横向滚动（thead/tbody 各成表，列不压扁）；`≤760px` 手机布局（侧栏 2 列菜单、统计卡 2 列、hero 按钮列堆叠、表单/上传行全宽）；`≤480px` 小屏（侧栏单列、通知卡单列、登录页全屏、编辑按钮全宽）
- 行为变更：仅 CSS 响应式，不改变任何功能/接口

## 四·补八、第八轮审计（2026-08-21 · v2.6.0 mobile UI 汉堡菜单+抽屉式导航）

> 用户反馈后台手机端表格显示不全（v2.5.3 横向滚动但无视觉提示 + 侧栏仍占左侧）+ 前台 header 排版怪异（nav 简单 wrap 成 7+1 两行）。本次做**结构性**改造：手机端统一用汉堡菜单+抽屉式导航，桌面端完全不变。

### 8.1 审计结论

- 无新漏洞
- 修改文件：
  - `myblog/templates/admin/base.html`：加 `.admin-hamburger` 按钮 + `.admin-drawer-mask` 遮罩 + 抽屉开关 JS（textContent 安全，类名硬编码无注入）
  - `myblog/static/admin.css`：≤760px 侧栏改抽屉式（fixed + translateX -100% → 0，0.26s cubic-bezier 过渡），遮罩 fade in，admin-main 顶部 padding 70px 留空间给汉堡；表格加右侧渐变阴影提示可滑动
  - `vue-frontend/src/App.vue`：加 `.drawer` 抽屉（v2.6.0 mobile drawer，包含 logo/nav/用户/主题/退出）和 `.drawer-mask` 遮罩；`drawerOpen` 状态控制；nav 链接/退出/主题按钮触发后自动关闭
  - `vue-frontend/src/styles/global.css`：≤760px 桌面 nav 隐藏、汉堡显示、抽屉样式（transition .28s cubic-bezier）、遮罩 fade
- 行为变更：仅 mobile（≤760px）展示抽屉；桌面端 nav 完全保持 v2.5.3 行为不变
- XSS 防护：所有用户输入仍用 `{{ }}` 文本插值，无 v-html 注入面；抽屉 link 用 router-link / 标准 `<a>` 跳转，无 innerHTML 拼接
- CSRF 防护：抽屉只切换 UI 状态，不发起任何 API 请求；现有全局 `enforce_same_origin` 覆盖所有 POST 接口
- 状态污染：抽屉开关使用 Vue ref + 切换 CSS class 闭包，组件卸载时自动清理

## 四·补九、第九轮审计（2026-08-21 · v2.6.1 后台溢出彻底修复）

> 用户截图反馈 v2.6.0 仍溢出：实测视口在 760-1100 之间（iPad 横屏 / 微信 WebView 桌面模式），抽屉和表格横滚规则都没触发。

### 9.1 修复内容

- **抽屉断点扩大到 ≤1100**（v2.6.0 是 ≤760）：iPad 横屏和微信内置浏览器桌面模式也走抽屉式侧栏
- **admin-table 所有视口都能横滚**（v2.6.1 兜底，不再依赖媒体查询）：`display: block; overflow-x: auto` 默认应用；thead/tbody 各成表，最小宽度 560px 保证内容不被压扁
- **关键列 sticky 定位**：第一列（通常是标题）和 `th` 表头 sticky 在表格内始终可见，横滚时"操作"列也能点到
- **容器级滚动阴影**：`.admin-table-wrap::before/::after` 左右渐变提示"可左右滑"，暗色主题适配
- **表格 padding 缩小**：12px 16px → 10px 12px，更多列可见
- 模板里有现成的 `admin.css?v={{ admin_css_v }}` 版本号机制（app.py context_processor 注入 mtime 时间戳），升级后浏览器自动重新加载新版 CSS，无需手动清缓存

### 9.2 审计结论

- 无新漏洞（纯 CSS）
- 修改文件：仅 `myblog/static/admin.css`
- 行为变更：所有 ≤1100 视口都进入抽屉+横滚模式；>1100 桌面端完全不变

## 四·补十、第十轮审计（2026-08-21 · v2.6.2 iOS 风格抽屉终极方案）

> 用户在微信内置浏览器实测，v2.6.1 抽屉打开后右侧没有黑色遮罩，层次不清；整体视觉需要更精致。本轮做成 iOS 风格抽屉：毛玻璃遮罩 + 圆角 + 精致菜单 + 主区轻微缩放。

### 10.1 改进内容

- **遮罩升级为毛玻璃**：`rgba(0,0,0,.5) + backdrop-filter: blur(3px)`（iOS 风格），覆盖整个视口，opacity 切换 0.3s 渐入
- **抽屉面板 iOS 化**：右侧圆角 18px、大阴影 6px 0 32px rgba(0,0,0,.22)、打开时主区轻微 `scale(.985)` 缩放（modern 感）
- **菜单精致化**：hover 时左边 3px 蓝色条 + padding-left 增加；active 项高亮（背景 + 左侧条 + 加粗）；emoji 字号加大 16px
- **hero-card mobile 优化**：按钮改为 2x2 网格（不再纵向堆叠），节省空间
- **统计卡 mobile 优化**：2 列布局更紧凑，padding 14-16px
- **抽屉锁滚**：打开时 `body.drawer-open` class 锁定 body 滚动
- **抽屉点击链接自动关 + 遮罩点击关 + ESC 关** 三种关闭方式保留

### 10.2 审计结论

- 无新漏洞
- 修改文件：`myblog/static/admin.css`、`myblog/templates/admin/base.html`
- 行为变更：仅 ≤1100 视口显示抽屉+毛玻璃+主区缩放；桌面端完全不变

## 四·补十一、第十一轮审计（2026-08-21 · v2.6.3 update.sh 修复 + GitHub 镜像加速）

> 用户后台一键更新报"脚本异常退出(码1)"。根因两个：①脚本 bug——`trap EXIT` 把 `fail_exit` 写的具体原因覆盖成通用信息，导致看不到真实错误；②真实原因大概率是服务器无法直连 GitHub（国内网络），curl 15s 超时即失败。

### 11.1 修复内容

- **保留真实错误信息**：`FAIL_MSG` 变量记录具体失败原因，`trap EXIT` 仅在无具体原因时才写通用信息（修复覆盖 bug，已用隔离测试验证）
- **网络重试 + 镜像兜底**：新增 `gh_fetch()` —— 直连失败自动尝试镜像代理（ghfast.top / gh-proxy.com / ghproxy.net），每次 2 次重试；可用 `GH_MIRROR` 环境变量手动指定镜像
- **错误提示更明确**：失败时状态文件给出具体原因 + 指引（"检查服务器能否访问 GitHub，或手动运行 bash update.sh 查看日志"）
- **安全说明**：镜像 URL 仅替换下载域名，包内容仍是 GitHub 官方 Release 资产（zip 完整性由解压步骤校验）；未配置 GH_MIRROR 时行为与旧版一致（直连）

### 11.2 审计结论

- 无新漏洞；修改文件：`update.sh`（仓库根，非应用代码，仅部署脚本）
- 不影响任何后端逻辑/接口/数据

## 四·补十二、第十二轮审计（2026-08-21 · v2.6.10 订阅者管理可删除/停用）

> 用户要求后台「✉️ 订阅者」页面可编辑/删除订阅者（此前仅有只读列表）。新增删除与启用/停用切换两个操作。

### 12.1 改动文件

- `myblog/admin.py`：新增 `POST /admin/subscribers/delete/<int:sid>`（删除）与 `POST /admin/subscribers/toggle/<int:sid>`（启用/停用切换），均 `@admin_required` 保护
- `myblog/templates/admin/subscribers.html`：表格新增「状态」列（已启用/已停用徽标）与「操作」列（停用/启用 + 删除按钮，删除带 `confirm()` 二次确认）
- `myblog/static/admin.css`：新增 `.badge` / `.btn-mini` / `.sub-actions` / `.sub-email` 样式（响应式，邮箱自动换行）

### 12.2 审计项

- **越权**：两个写操作均 `@admin_required`，非管理员不可访问或操作；`get_or_404` 越界返回 404
- **XSS**：邮箱 `{{ s.email }}` 经 Jinja2 自动转义，无 `|safe`；状态徽标为服务端固定文案
- **SQL 注入**：全部走 ORM（`get_or_404` / `query`），无字符串拼接
- **CSRF**：沿用项目既有 `flash`+`redirect` 模式（与 `delete_post` 一致），需登录态；未引入 token，但与全站其他删除操作风险等级一致
- **资源泄漏**：无文件句柄 / 外部连接 / 子进程

### 12.3 审计结论

- 无新漏洞；隔离冒烟测试通过（删除→剩 1 条、切换→active 翻转正确）
- 仪表盘样式调整（回到 v2.6.4 观感）本轮**未实施**，待用户确认方向后再做

## 四·补十三、第十三轮审计（2026-08-21 · v2.6.11 仪表盘回 v2.6.4 + 大框防溢出）

> 用户要求：仪表盘回到 v2.6.4 设计观感（hero 渐变大气 + 统计卡 2x2 + 下方 4 面板手机端单列），并给每个区块外面包一层大框（`.section-box`），保证内容被框住不溢出屏幕。

### 13.1 改动文件

- `myblog/templates/admin/dashboard.html`：恢复 v2.6.4 结构（hero + notify + 2x2 统计卡 + dash-grid 单列）；给 hero / notify / 统计卡 / 全部文章 / 右侧 3 面板各套一层 `.section-box`；「全部文章」表格外加 `.table-scroll` 横向滚动容器
- `myblog/static/admin.css`：
  - 新增 `.section-box`（浅色背景 + 边框 + 圆角 + `overflow:hidden` 关键防溢出）+ 暗色适配
  - 新增 `.table-scroll`（表格横向滚动容器）
  - section-box 内 `.panel` 去自身边框/阴影/外边距（避免双层框）
  - 撤销 v2.6.9 的 `dash-grid` 2x2（`display:contents`）→ 恢复 `grid-template-columns: 1fr`（手机端下方 4 面板单列）
  - 撤销 v2.6.8 的 hero 缩小 → 恢复 v2.6.4 大气尺寸（≤1100 hero padding 22px 20px、按钮 2x2）
  - 撤销 v2.6.8 ≤760 的 hero-actions 2x2 → 恢复 `flex:1 1 100%`（按钮全宽堆叠）

### 13.2 审计项

- 纯 CSS / 模板结构改动，无新后端路由 / 无用户输入处理 / 无数据库写操作
- XSS：模板仅用服务端变量 + Jinja2 自动转义，无新增 `|safe`
- 越权：无新增接口，鉴权沿用既有 `@admin_required`
- 溢出修复：`section-box { overflow: hidden }` + `.table-scroll { overflow-x: auto }` 确保内容在框内裁剪/滚动，不再撑破视口
- 桌面端布局完全不变（dash-grid 1fr + 300px 双栏）

### 13.3 审计结论

- 无新漏洞；隔离冒烟渲染通过（section-box 6 处、table-scroll 1 处、无 v2.6.9 残留）
- CSS 配平 OK（681 行）

## 四·补十二、第十四轮审计（2026-08-21 · v2.6.12 大框随主题切换）

> 用户确认 v2.6.11 布局正确，但要求大框（section-box）颜色随深/浅主题切换。

### 12.1 改动内容

- `admin.css`：将 section-box 及其内部 panel 的颜色由写死值改为 CSS 变量驱动
  - `.admin` 作用域定义浅色变量：`--box-bg:#f4f6f8` / `--box-border:#e6e8eb` / `--inner-bg:#ffffff`
  - `[data-theme="dark"] .admin` 定义深色变量：`--box-bg:#1b1e23` / `--box-border:#333a44` / `--inner-bg:#23272e`
  - `.section-box` 用 `var(--box-bg)` / `var(--box-border)`；`.section-box .panel` 用 `var(--inner-bg)` / `var(--box-border)`
  - 暗色段补 `[data-theme="dark"] .section-box .panel` 覆盖通用 `.panel` 暗色规则，保证边框/背景统一跟随
- `data-theme` 挂在 `<html>`（documentElement），`[data-theme="dark"] .admin` 继承链正确

### 12.2 安全评估

- 纯 CSS 变量重构，无后端逻辑改动，无用户输入、无 XSS/SQL/越权面
- 变量 fallback 保留原默认值，浅色/深色均显式定义，无未定义风险
- 隔离冒烟渲染通过（dashboard 200，section-box 6 处、table-scroll 1 处）
- CSS 配平 OK（695 行）

## 四·补十三、第十五轮审计（2026-08-22 · v2.6.13 修复深色模式大框/汉堡不跟随主题）

> 用户反馈：深色模式下新增大框仍是白色、汉堡图标也不随主题变。

### 13.1 根因

- v2.6.12 用 CSS 变量（`--box-bg` 等）+ `[data-theme="dark"] .admin` 继承做暗色切换。但全站 71 条暗色规则**全部是写死颜色值、0 条用 var()**，说明原方案刻意不依赖 CSS 变量（兼容微信老内核）。微信内置浏览器对 `var()` 的变量继承/属性选择器匹配支持不可靠，导致 `[data-theme="dark"] .admin { --box-bg:... }` 未生效，section-box 的 `var(--box-bg, #f4f6f8)` 退回浅色 fallback → 深色下仍是白色。
- 汉堡图标 `.admin-hamburger` 写死 `background: var(--accent)` + `color:#fff`（亮蓝白字），暗色段无适配规则。

### 13.2 修复

- `admin.css`：section-box 及内部 panel 的浅色/暗色**全部改为写死值**（与全站暗色规则一致），删除 `.admin` 的 var 变量定义和 `[data-theme="dark"] .admin` 变量赋值
  - 浅色：`.section-box { background:#f4f6f8; border-color:#e6e8eb }`；`.section-box .panel { background:#fff; border-color:#e6e8eb }`
  - 暗色：`[data-theme="dark"] .section-box { background:#1b1e23; border-color:#333a44 }`；`[data-theme="dark"] .section-box .panel { background:#23272e; border-color:#333a44 }`
- 汉堡图标暗色适配：`[data-theme="dark"] .admin-hamburger { background:rgba(255,255,255,.1); color:#e6e8eb; border:1px solid rgba(255,255,255,.15); box-shadow:none }`

### 13.3 安全评估

- 纯 CSS 颜色值修正，无后端逻辑改动，无注入面
- 隔离冒烟渲染通过（dashboard 200）；CSS 配平 OK（694 行）
- 无 var() 残留，彻底兼容微信内核

## 四·补十四、第十六轮审计（2026-08-22 · v2.6.14 修复前端更新被缓存拦截）

> 用户反馈：v2.6.13 发布后，深色模式大框/汉堡仍"没有变黑"。

### 16.1 根因（前端更新被缓存拦截，而非 CSS 规则错误）

- v2.6.13 的 `admin.css` 暗色规则本身正确（写死值，已逐行验证所有 section-box 在深色下都该变黑），但用户服务器/微信**始终在加载旧 CSS**：
  1. 模板用 `admin.css?v={{ admin_css_v }}` 做缓存 bust，而 `admin_css_v` 原按 `admin.css` 文件 **mtime** 计算（app.py context_processor）；
  2. 宝塔 `update.sh` 用 `rsync -a` 覆盖后端，`-a` 保留源文件 mtime，若 zip 内 mtime 不新于服务器旧文件，`?v=` 不变；
  3. 微信 X5 内核对带 query 的静态资源可能**忽略 `?v=` 强缓存旧文件**——v2.6.11 大框首次加载被拉取后即被缓存，后续带 `?v=` 的更新不被重新拉取。
- 佐证：v2.6.12（var 浅灰）与 v2.6.13（写死 `#f4f6f8`）浅色下视觉一致，用户无法区分是否加载新版，实际仍在用旧 CSS。

### 16.2 修复（双保险强制刷新）

- `app.py`：`admin_css_v` 从 mtime 改为 **`APP_VERSION`**（每次发版必变，保证 `?v=` 变化）；
- `app.py` 新增 `after_request`：对 `/static/admin.css`、`/static/script.js` 设置 `Cache-Control: no-cache, must-revalidate`，**兜底**微信忽略 `?v=` 的情况——每次向服务器验证，文件 ETag/mtime 变了即返回新内容；不影响前台 Vue 资源（Nginx 服务）与首页（已验证首页 `Cache-Control` 不受影响）。

### 16.3 安全评估

- 仅修改响应头值与版本戳常量，头值为固定字符串无注入面；`?v=` 改为常量无计算风险
- 不影响鉴权/数据接口；`no-cache` 仅作用于两个后台静态资源，前台/接口不受影响（渲染测试已确认：后台页 `?v=2.6.14`、admin.css 响应头 `no-cache, must-revalidate`、首页无该头）
- 后端语法 `py_compile` 通过

## 五、上线前必做（宝塔面板 · 环境变量配置）

程序启动**必须**存在两个环境变量（缺失即拒绝启动）：

1. 宝塔面板 → 「Python 项目」→ 你的项目 → **「设置」→「环境变量」**；
2. 新增两项**必填**：
   - `SECRET_KEY` ← 在服务器终端执行以下命令生成一串随机值填入：
     ```bash
     python3 -c "import secrets;print(secrets.token_hex(32))"
     ```
   - `ADMIN_PASSWORD` ← 一个随机强密码（首次登录后台还会被强制修改，这里只是初始值）
3. （推荐）`COOKIE_SECURE=true`；`SITE_URL=https://你的域名`
4. （可选 · 自动部署）`WH_DEPLOY_SECRET` ← 一段随机字符串；配合 GitHub Webhook 在 Header 带 `X-Deploy-Token` 或 URL 带 `?token=`。**不配置则 `/api/webhook/deploy` 返回 403（安全默认）**。
5. （可选 · 邮件群发）`SMTP_HOST` / `SMTP_PORT`（默认 465）/ `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_SSL`（默认 true）。**不配置则邮件群发自动跳过**；v2.4.0 起也可直接在**后台「📧 邮件设置」**填写，无需再配环境变量。
6. （可选 · 自动部署执行）`DEPLOY_SCRIPT` ← 部署脚本绝对路径；**不配置则 Webhook 仅授权不执行（安全默认）**。
7. （可选 · 新文章推送）`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`（Telegram），或 `WECOM_WEBHOOK_URL`（企业微信/微信「群机器人」）。**不配置则对应渠道自动跳过，不影响发文章**。
8. （可选 · 换数据库）`DATABASE_URL` ← 例如 `postgresql+psycopg://user:pass@host:5432/blog`；非 SQLite 时全文搜索自动降级为 LIKE。
9. 保存并**重启项目**。若日志报"缺少环境变量 SECRET_KEY / ADMIN_PASSWORD"，说明没配置成功。

## 五、残余风险与建议（非阻塞）

- 内存限流在 gunicorn 多 worker 下各自计数，仅作纵深防御；高流量可引入 Redis + Flask-Limiter。
- 生产建议启用 HTTPS（Let's Encrypt 免费证书），并定期备份 `data/blog.db`。
- 评论/注册等写接口后续可加验证码（如极验）进一步防滥用。
- 请确认 Nginx 反代已配置 `proxy_set_header X-Forwarded-For $remote_addr;`（由 Nginx 写入真实 IP，而不是透传客户端伪造值）。
