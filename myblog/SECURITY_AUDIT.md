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
