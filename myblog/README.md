# 我的博客（Flask + SQLite + Vue3 前端）

一个适合新手自己搭建、维护和部署的博客系统，采用 **方案 B：前后端分离**（默认且唯一推荐方案）：

- **后端 `myblog/`**：Flask + SQLite，提供 `/api/*` JSON 接口与 `/admin` 后台管理（服务端渲染，含用户系统与权限）。
- **前端 `vue-frontend/`**：Vue3 + Vite，构建成静态站，由 Nginx 直接托管，页面通过 `/api/*` 拉取数据。
- 部署最省心：Nginx 托管静态文件 + 反代 `/api` 与 `/admin` 到 Flask，**服务器不需要 Node**（前端在本地构建好再上传）。

## 功能
- 写文章（后台在线编辑，支持 Markdown 语法，代码高亮）
- **定时发布**（写文章时可选未来时间，保存后先存为「待发布」，后台线程每 60s 扫描到点自动公开并推送通知；列表/详情/搜索/归档/RSS 等所有出口对未到时间文章均不可见）
- **文章置顶**（写文章时勾选「📌 置顶」，首页/分类/标签/归档/搜索/RSS 等列表优先展示，前台卡片显示 📌 标识；与定时/立即发布独立并存）
- 分类与标签 / **FTS5 全文搜索**（不支持时自动降级 LIKE）/ 评论区（**嵌套回复 + @显示 + 点赞**）/ 阅读量统计
- **系列 / 专栏**（多篇成系列，文章页带上一篇/下一篇导航）+ **相关文章推荐**（标签重合度算法）+ **热门文章排行**
- **留言墙**（前台独立留言页，登录可留言、点赞，后台管理）
- **邮件订阅**（前台侧边栏订阅框，后台「✉️ 订阅者」可查看/删除/启用停用）
- **邮件群发**（后台「📧 邮件设置」直接配置 SMTP + 一键测试发送；新文章发布自动通知订阅者，带退订链接）
- **站点公告**（全局可关闭横幅，Markdown 内容，info/success/warning 级别）
- **广场页**：微动态发布/点赞/评论 + 友链 RSS 聚合（博客圈）+ 社交账号墙
- **访问统计**（前台「统计」页 + 后台「📊 访问统计」）：
  - 累计 / 今日访问次数
  - 访客区域排行榜（今日 + 累计 TOP10，IP 属地异步识别）
  - 最受关注（反复阅读）的文章、常搜词汇 TOP10、24 小时访问时段分布
- **天气小组件**：wttr.in 主源 + Open-Meteo 兜底（免费无需 Key；支持浏览器定位 + 城市名查询；失败自动回退默认城市）
- **博客名称 / 浏览器便签**：后台可编辑，前台 Logo、浏览器标签标题、顶部公告条跟随
- **前后台统一登录**：一个 `/login` 入口（访问 `/admin` 自动跳转），登录后按角色鉴权分流
- **精美管理后台**（inis 风格）：分组侧边栏 + 用户卡片 + 渐变欢迎卡 + 双栏仪表盘 + 统计图表，明暗双主题
- **后台新消息提醒**：未读评论/留言角标（导航 + 仪表盘卡片），一键标记已读
- **版本自检**：后台左下角显示当前安装版本（vX.Y.Z），点击直达 GitHub Releases 比对最新版
- **后台一键在线更新**（v2.5.0+）：登录后台自动检测新版本 → 超管点「立即更新」→ 后台静默完成下载/备份/覆盖/自动重启 → 完成提示刷新
- 关于本站 / 友情链接 / 底部备案号（ICP 备案码后台可编辑）
- 前后台统一明暗主题切换（自动记忆；后台侧边栏新增切换按钮，与前台共用同一主题偏好）
- 图片上传（后台插图 + 文章封面图）
- RSS 订阅（`/feed.xml`）、SEO 优化（`sitemap.xml` / `robots.txt`）
- 文章目录 TOC + 阅读进度条 + 首页数字分页 + 回到顶部
- **自定义主题色**（后台取色器，全站跟随）
- **归档时间线**（导航「归档」按年/月汇总）
- **文章点赞**（同一浏览器去重计一次）
- **新文章推送通知**：发布时推送到 Telegram / 企业微信（可选，未配置自动跳过）
- **Webhook 自动部署接口**：`/api/webhook/deploy`（HMAC 校验密钥，校验通过后自动执行 `DEPLOY_SCRIPT` 部署脚本，实现「GitHub push → 服务器自动更新」；脚本模板见仓库根 `deploy.sh`）
- **用户系统与权限**：访客注册/登录（评论自动用用户名）；三级权限——超级管理员（管理用户，不可被删/降级）/ 管理员（管理内容）/ 普通用户
- **后台修改密码** + **用户管理**（超级管理员专属：新增用户、调整角色、重置密码、删除用户）
- **上线安全**：首次进入后台强制设置管理员用户名与密码，未设置前默认密码无法看到后台内容

### v3.0.0 新增功能
- **系列目录页增强**：系列详情页新增带编号的章节目录（系列 TOC）。
- **字数统计 + 阅读时长**：每篇文章自动统计字数并估算阅读分钟数，前台详情页展示。
- **评论批量管理 + 垃圾过滤**：后台评论可批量勾选通过/删除；评论提交命中「垃圾评论关键词」即被拒收（站点设置可配）。
- **后台操作日志（审计 trail）**：超管可见所有关键后台操作流水，支持清空（只读、隐私）。
- **文章版本历史 / 回收站**：每次保存自动留存历史版本（每篇上限 20）；删除进回收站，可一键还原或彻底清除。
- **友情链接申请 + 自助审核**：前台访客可自助提交友链申请（限流 + URL 校验 + 去重），后台超管审核通过/拒绝。
- **热门标签云**：新增「热门标签」云（按文章数 ×2 + 阅读量加权），前台独立页面。
- **「看了又看」协同过滤**：文章详情页底部推荐基于共同阅读人群 + 标签/分类相似度（取代原简单相关推荐）。
- **访客趋势图**：后台统计页新增近 30 天 PV/UV 折线趋势图（纯 SVG）。
- **RSS 按分类 / 标签订阅**：新增 `/api/rss/category/<slug>` 与 `/api/rss/tag/<slug>`。
- **多语言 / i18n**：前台内置中/英双语切换，后台可设默认语言 `site_lang`。
- **超级管理员隐私空间**：超管可将文章标记为「隐私」，仅本人登录后可见，前台及 API 对其余人一律 404。
- **文章打赏**：仅超管可在每篇文章结尾开关「打赏」并填收款码；前台展示站点默认或文章自定义收款码。
- 简约清爽的响应式界面（手机也能看）

### v3.1.0 新增功能
- **后台登录审计日志**：每次后台登录（成功/失败、尝试用户名、来源 IP）写入审计日志（`action='login'`），「操作日志」页可查看并区分成功/失败。
- **审计日志 30 天保留**：登录日志与操作日志超过 30 天自动清理（原 7 天）。
- **审计日志打包下载**：「操作日志」页新增「📦 打包下载」按钮，超管一键导出 CSV + TXT 压缩包（内存打包，不落盘）。
- **前台统一大框**：前台内容（公告/便签/正文/页脚）外包一层大框架，视觉与后台一致，明暗主题跟随。
- **修复**：手机端汉堡菜单不随深色模式切换（主题初始化误重置为 light）。

### v3.1.1 修复
- **修复**：手机端抽屉菜单（`.drawer`）深色模式下仍为白底——`[data-theme="dark"]` 未重定义 `--nav-bg/--nav-fg/--nav-border` 变量，抽屉依赖变量导致不跟随；已在暗色段重定义并补充抽屉暗色适配（R9）。

### v3.1.2 部署脚本修复（不含代码变更）
- **修复**：一键更新第⑥步跨用户 `kill` 权限失败（`Operation not permitted`）。`update.sh`/`deploy.sh` 默认 `PROJECT_NAME="myblog"`，重启优先走 `supervisorctl restart myblog`（supervisor 以 www 身份停+起，绕开跨用户 kill）；root 身份运行时自动加 `sudo -u www` 保护。仅更新部署脚本，APP_VERSION 仍为 v3.1.1。

### v3.1.3 抽屉深色补充修复
- **修复**：在 `[data-theme="dark"]` 区块末尾追加 4 条直接写死暗色值的菜单抽屉规则（`.drawer` / `.drawer-nav a` / `.drawer-nav a:hover` / `.drawer-foot`），彻底覆盖旧变量规则，确保深色模式下抽屉视觉稳定（R10，纯前端 CSS，无后端改动）。APP_VERSION 升为 3.1.3。

### v3.1.4 部署脚本根因修复（不含代码变更）
- **修复**：纠正 v3.1.2 的错误假设——宝塔 Python 项目**不是** supervisor 管理，gunicorn 属主是 **`mw`（非 `www`）**。重启逻辑改为宝塔 CLI（`bt stop/start`）优先 → `runuser -u mw` 真杀 + 宝塔真实 gunicorn 路径重新拉起。彻底消除跨用户 kill 权限失败。仅更新部署脚本，APP_VERSION 仍为 v3.1.3。

### v3.1.5 安全加固四项
- **FTS 搜索转义**：全文搜索（搜索建议接口）对用户输入做 FTS5 特殊字符转义，防止语法错误 / 查询异常。
- **密码最小长度 6 → 8**：注册、改密、创建用户、重置密码、首次设置统一为 8 位下限（前后端一致）。
- **审计日志 CSV 公式注入防护**：导出审计日志时，对以 `= + - @` 开头的单元格加前缀，防止 Excel 打开执行恶意公式。
- **一键更新哈希校验**：`update.sh` 下载部署包后比对 Release 附带的 `sha256.txt`，不一致直接终止更新，防中间人篡改 / 下载损坏（由 `package.py` 自动生成校验文件）。APP_VERSION 升为 v3.1.5。

### v3.1.6 安全加固 12 项（全量落地）
- **更新包完整性双重互证**：`package.py` 将各 zip 的「内容区」SHA256（剥离 EOCD 尾注释后的字节）写入 zip 注释，`sha256.txt` 记录含注释的整文件哈希；`update.sh` 同时比对 `sha256.txt` + zip 注释 + 可选 `UPDATE_HMAC_KEY` HMAC 签名——解决「sha256.txt 本身被替换」的漏洞（R13 审计通过）。注释哈希按内容区计算，不能对含注释的整文件算（注释参与字节后必然对不上）。
- **上传文件魔数校验**：后缀白名单 + PNG / JPG / GIF / WebP 文件头 magic bytes 双重校验，伪造扩展名文件被拒。
- **SMTP 密码不存库**：`SMTP_PASSWORD_ENV_FIRST`（默认 true）——SMTP 密码优先读环境变量，库值仅兜底。
- **多 worker 全局限流**：`REDIS_URL` 配置后走 Redis INCR+EXPIRE 全局计数（多 worker 共享）；未配置自动回退内存滑动窗口（单 worker 等价）。
- **CSRF Token 双重防护**：同源校验 + 会话绑定 HMAC Token，全局 POST / PUT / DELETE / PATCH 均校验；前端 apiPost 自动携带 `X-CSRF-Token`，服务端表单自动注入隐藏域。
- **RSS DNS 重绑定缓解**：`feed_agg` 先解析域名再校验解析结果不含内网 / 回环 / 保留地址。
- **弱密码黑名单 + 复杂度开关**：`STRONG_PASSWORD`（黑名单 + 字母/数字）与 `STRONG_PASSWORD_MIXED_CASE`（大小写混合）可独立开关，前后端统一提示。
- **登录防枚举 + 会话踢下线**：失败统一文案 + `LOGIN_DELAY_SECONDS`（默认 1s）统一延迟，消除用户名枚举与时序侧信道；`session_version` 机制 + 超管「踢下线」路由实现「改密码销毁全部旧会话」。
- **审计日志时间筛选与保留**：后台支持 `?from=&to=` 日期筛选；`AUDIT_LOG_DAYS`（默认 90）自动清理超期日志；导出支持筛选。
- **可开关验证码**：`CAPTCHA_ENABLED`（默认 true）——注册 / 评论 / 留言图形验证码，一次性票据防重放，未装 Pillow 自动降级关闭。
- **安全响应头**：`SECURITY_HEADERS`（默认 true）——全局追加 X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy。
- **会话超时 + Webhook 防重放**：`SESSION_IDLE_MINUTES`（默认 60）闲置超时强制重登；Webhook 必须带 `X-Deploy-Time` 时间戳（`WH_REPLAY_WINDOW` 默认 300s 窗口校验）。APP_VERSION 升为 v3.1.6。

## 目录结构
```
myblog/             # 后端（Flask + SQLite）
├── app.py          # 应用入口（工厂函数 + 自动迁移 + FTS 初始化 + CLI 命令）
├── config.py       # 配置（密钥、数据库路径、管理员初始账号、APP_VERSION）
├── models.py       # 数据库表结构（文章/评论/用户/设置/系列/公告/留言/订阅者等）
├── fts.py          # SQLite FTS5 全文搜索（探测可用性，不可用时自动降级 LIKE）
├── notify.py       # 新文章推送通知（Telegram / 企业微信，环境变量驱动，静默失败）
├── feed_agg.py     # 友链 RSS 聚合（15 分钟内存缓存 + SSRF 防护 + bleach 清洗）
├── stats.py        # 访问统计：IP 属地解析（缓存+在线接口）、埋点记录、汇总
├── utils.py        # 小工具（生成网址 slug、clean_html 白名单清洗、限流、安全跳转、弱密码校验、CSRF Token）
├── routes.py       # 前台页面 + 注册/登录 + 评论提交 + 天气接口
├── admin.py        # 后台管理（登录/写文章/分类/标签/评论/设置/统计/用户/系列/公告/留言墙/订阅者）
├── api.py          # 前后端分离用的 JSON 接口（/api/*，含 /api/stats/* 埋点与汇总）
├── security.py     # 安全响应头 / 图形验证码 / SMTP 密码优先级（v3.1.6 新增）
├── requirements.txt
├── deploy_guide.md # 宝塔部署手册（点按式，含 Nginx 反代配置）
├── SECURITY_AUDIT.md # 安全审计报告（两轮）
├── templates/      # 页面模板（含后台：admin/base.html 管理外壳、admin/stats.html 统计页等）
├── static/         # 样式与脚本（admin.css 后台样式、script.js、上传图片在 static/uploads/）
└── data/           # 运行时自动生成的 SQLite 数据库 blog.db

vue-frontend/       # 前端（Vue3 + Vite，构建成静态站）
├── vite.config.js  # Vite 配置（/api 开发代理到 8080）
├── package.json
├── index.html
└── src/
    ├── main.js / App.vue / router.js / store.js
    ├── lib/api.js          # fetch 封装
    ├── components/         # PostCard / Sidebar / WeatherWidget / LikeButton / CommentForm
    ├── views/              # 首页/文章/分类/标签/归档/统计/关于/友链/搜索/登录/注册/广场/系列/留言墙
    └── styles/global.css   # 整套样式（含暗色模式）
```

## 本地运行
1. 先启动后端（含 API）：
   ```bash
   cd myblog
   python -m venv venv
   # Windows：venv\Scripts\activate   |   macOS/Linux：source venv/bin/activate
   pip install -r requirements.txt
   # 安全启动前置：设置随机会话密钥与初始管理员密码（缺失则程序拒绝启动）
   export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
   export ADMIN_PASSWORD=$(python -c "import secrets;print(secrets.token_hex(16))")
   flask --app app init-db
   flask --app app seed          # 可选：填充示例文章
   python app.py                 # 或 python -m flask --app app run -p 8080
   ```
   确认 http://127.0.0.1:8080/api/site 返回 JSON。
2. 再启动 Vue3 开发服务器（自动把 `/api` 代理到 8080）：
   ```bash
   cd vue-frontend
   npm install
   npm run dev                  # 打开 http://localhost:5173
   ```
3. 前台在 http://localhost:5173/ ；后台在 http://localhost:8080/admin（初始账号：`ADMIN_USERNAME` 默认 `admin` + 上一步设置的 `ADMIN_PASSWORD`；首次登录强制设置新账号密码）。

## 用户与权限
- **注册**：前台导航「注册」（或 `/register`），注册即登录，评论自动显示用户名。
- **统一登录**：前台 `/login` 与后台共用同一套账号体系、同一个登录入口。访问 `/admin` 未登录会自动跳到 `/login?next=/admin`，登录成功后按权限自动回到后台。
- **登录/登出**：导航「登录」/「退出」（退出走接口清会话，前端任意页面可退）。
- **角色**：
  - `super` 超级管理员：全部权限；后台可见「用户管理」「站点设置」；**不可被删除、不可被降级**。
  - `admin` 管理员：可管理内容（文章/分类/标签/评论/友链/统计），**不能管理用户、不能改站点设置**。
  - `user` 普通用户：可登录、评论；**可发表文章**（导航「✏️ 写文章」进入，只能编辑/删除自己发表的文章）；访问后台管理页会被引导到写文章。
- **改密码**：后台 →「修改密码」（需原密码）；超级管理员可在用户管理里重置他人密码。
- 首次运行自动用环境变量 `ADMIN_USERNAME`（默认 admin）/ `ADMIN_PASSWORD`（必填）创建唯一超级管理员；启动时若缺少 `SECRET_KEY` 或 `ADMIN_PASSWORD` 环境变量，程序直接拒绝启动（源码不内置任何弱默认密钥）。

## 上线安全：环境变量与管理员账号
程序启动时必须存在两个环境变量（缺失即拒绝启动）：
- `SECRET_KEY`：随机长字符串（会话签名密钥）。生成：`python -c "import secrets;print(secrets.token_hex(32))"`
- `ADMIN_PASSWORD`：首次创建超级管理员的初始密码。生成：`python -c "import secrets;print(secrets.token_hex(16))"`

上线后第一次访问 `/admin`，用 `ADMIN_USERNAME`（默认 `admin`）+ `ADMIN_PASSWORD` 登录，系统会**强制进入「设置管理员账号」页面**：
1. 填你自己的用户名（可沿用 admin）；
2. 设置新密码（至少 8 位）；
3. 保存后进入后台，旧密码立即失效，之后不再出现本页。

其他可选环境变量：
- `COOKIE_SECURE`：默认 `true`（生产 HTTPS 推荐）；本地纯 HTTP 开发可设 `false`。
- `BLOG_OPEN_REGISTER`：默认 `true`；设为 `false` 可关闭公开注册。
- `CORS_ORIGIN`：默认空（不开启跨域）；前后端分离时才填允许的前端域名列表（逗号分隔）。
- `SITE_URL`：站点对外地址，如 `https://blog.example.com`（RSS/sitemap 生成绝对链接用）。
- `DATABASE_URL`：默认 `sqlite:///data/blog.db`；可覆盖为其他 SQLite 路径或 Postgres/MySQL 连接串（此时 FTS5 自动降级 LIKE）。
- `WH_DEPLOY_SECRET`：设置后 `/api/webhook/deploy` 才可用（Header `X-Deploy-Token` 或 `?token=` 携带，HMAC 恒定时间比对）。**v3.1.6 起另需 `X-Deploy-Time` 时间戳头**（可选，缺省仅鉴权）。
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `WECOM_WEBHOOK_URL`：新文章推送渠道（均可选，不配置自动跳过）。

**v3.1.6 安全加固新增环境变量**（均为可选，不配用默认值）：
- `REDIS_URL`：多 worker 部署时启用 Redis 全局限流（如 `redis://127.0.0.1:6379/0`）；不配自动回退内存滑动窗口（单 worker 等价）。
- `SMTP_PASSWORD_ENV_FIRST`：默认 `true`——SMTP 密码优先环境变量 `SMTP_PASSWORD`，库值仅兜底。
- `STRONG_PASSWORD`：默认 `true`——弱密码黑名单 + 字母/数字复杂度校验；`false` 关闭。
- `STRONG_PASSWORD_MIXED_CASE`：默认 `false`——`true` 时额外要求大小写混合。
- `LOGIN_DELAY_SECONDS`：默认 `1`——登录失败统一延迟（防用户名枚举时序侧信道）。
- `SESSION_IDLE_MINUTES`：默认 `60`——会话闲置超时；`0` 关闭。
- `AUDIT_LOG_DAYS`：默认 `90`——审计日志保留天数。
- `CAPTCHA_ENABLED`：默认 `true`——注册/评论/留言图形验证码（未装 Pillow 自动降级关闭）。
- `SECURITY_HEADERS`：默认 `true`——安全响应头（X-Frame-Options/CSP/X-Content-Type-Options/Referrer-Policy）。
- `UPDATE_HMAC_KEY`：可选——为发布包生成 HMAC 签名并在 `update.sh` 校验（增强更新包完整性）。

> 安全设计：源码开源后，以上密钥不会以任何弱默认值出现在代码里，请在部署环境通过环境变量注入。

## 部署到宝塔面板（Debian 13）
**完整、逐步的点击式部署教程见同目录 `deploy_guide.md`**（全程用宝塔界面操作，不需要 SSH，不需要在服务器装 Node）。需要两个文件：
- `myblog-backend.zip` —— 后端（上传后由宝塔 Python 项目管理器启动）；
- `vue-frontend-dist.zip` —— 前端构建产物（上传解压即网站根目录）。

> 如需重新构建前端（修改过 `vue-frontend/` 源码后）：本地执行 `npm install && npm run build`，把生成的 `dist/` 内容打成 zip 再上传覆盖。

## 常见问题
- **502**：gunicorn 没起来，去项目管理器看「运行中」与日志（端口冲突/依赖缺失最常见）。
- **后台能打开但完全没有样式（全文本）**：Nginx 少了 `location /static/ { proxy_pass ... }` 反代，`/static/admin.css` 返回 404。详见 `deploy_guide.md` 第 4 步（宝塔不会自动加这段）。
- **改了后台样式不生效**：admin.css 引用带自动版本戳（按文件 mtime），重启 Python 项目 + 浏览器强刷（Ctrl+F5）即可。
- **天气组件不显示 / 定位报错**：wttr.in 主源 + Open-Meteo 兜底。定位被拒或接口失败会自动回退默认城市；访客也可手动输入城市名查询，无需 Key。
- **点赞数不增加**：同一浏览器已点过会显示已赞（localStorage 去重）。
- **RSS/sitemap 里链接是 localhost 或 IP**：在宝塔项目「环境变量」里加 `SITE_URL=https://你的域名` 并重启项目。
- **部署包与数据库**：`myblog-backend.zip` 不包含 `data/` 目录，解压覆盖不会动服务器上已有的 `blog.db`；新增表/列（评论嵌套字段、系列、公告、留言、订阅者、is_read 等）在重启时自动迁移创建。
- **更新后后台还是旧界面**：① 先 `ls -la /www/wwwroot/*/data/blog.db` 确认真实运行目录，确认 zip 解压覆盖到了该目录（zip 自带一层 `myblog/`，避免解压成嵌套）；② 宝塔 Python 项目「停止」再「启动」（仅点重启可能只是重载配置，gunicorn 旧进程未退出）；③ 登录后台看左下角版本号是否为最新（如 v3.1.1，与 GitHub Releases 对比）。
- **搜索变弱 / 接口返回 engine=like**：服务器 SQLite 不带 FTS5 模块，程序已自动降级为 LIKE 模糊搜索（功能正常，大数据量下较慢）。Debian 13 自带 SQLite 一般支持 FTS5。
- **订阅者列表是空的**：订阅入口在**前台侧边栏「📬 邮件订阅」**（访客填邮箱提交）。要让订阅者真正收到新文章邮件，需在后台「📧 邮件设置」配置 SMTP（QQ/163 邮箱用授权码）并保存。
- **后台左下角没有版本号**：说明后端代码未更新到 v2.2.0+，请按「更新后后台还是旧界面」排查。
- **测试邮件发送失败**：检查后台「📧 邮件设置」——端口/SSL 开关是否匹配（465=勾选 SSL，587=取消）、授权码是否正确（不是登录密码）、发件邮箱是否已在邮箱后台开启 SMTP 服务。
- **第三方脚本直接 POST 接口被 403（CSRF）**：v3.1.6 起所有写接口要求会话绑定的 CSRF Token。前端页面/后台表单已自动处理；第三方脚本需先 GET `/api/csrf` 拿 token 再带 `X-CSRF-Token` 头提交（或改用 webhook 等豁免接口）。
- **评论/留言/注册要填验证码**：v3.1.6 起默认开启图形验证码（`CAPTCHA_ENABLED=true`）；如果服务器没装 Pillow 会自动降级关闭。若不想用，在环境变量设 `CAPTCHA_ENABLED=false` 并重启项目。
- **升级 v3.1.6 后所有用户都要重新登录**：`session_version` 会话版本机制启动生效，旧会话全部失效（预期安全行为，登录一次即可）。
