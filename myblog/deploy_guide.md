# 博客上线部署手册（宝塔面板 · Debian 13 示例）

> 本手册以 **宝塔面板 + Debian 13** 为例编写，各版本菜单名称、按钮位置大同小异，照着点即可，全程**不需要 SSH、不需要装 Node**。

## 0. 部署前准备

| 需要文件 | 在你自己电脑上 | 说明 |
|---|---|---|
| `myblog-backend.zip` | ✅ 已有 | 后端 + 管理后台，约 69KB |
| `vue-frontend-dist.zip` | ✅ 已有 | 前端构建产物，上传解压即网站根目录（由 `package.py` 自动识别最新构建目录打包） |

**另外确认**：域名已在域名商后台做好 A 记录解析（主机记录 `@` 和 `www`，记录值填服务器公网 IP）。解析通常几分钟生效。

**部署前置条件**（以宝塔面板为例，若已具备可跳过）：
- ✅ Nginx 1.30.4 已安装
- ✅ Python 3.13.5 系统级环境已就绪（但**不能直接作为项目环境**，需先基于它创建虚拟环境，见第 2 步）
- ✅ 宝塔 v13 的 Python 项目入口在：左侧「网站」→ 顶部「Python项目」

---

## 第 1 步：上传后端代码

1. 宝塔左侧菜单点 **「文件」**。
2. 地址栏/面包屑导航到 `/www/wwwroot/`（左侧目录树点 `www` → `wwwroot`）。
3. 点右上角 **「上传」** → 选择本地电脑的 `myblog-backend.zip` → 上传完成后点 **「上传完成」** 关闭。
4. 在文件列表里**右键 `myblog-backend.zip`** → 点 **「解压」**。
5. 解压后确认出现文件夹 `/www/wwwroot/myblog/`（里面有 `app.py`、`config.py`、`templates/` 等）。
6. 进入 `myblog/`，确认有 `data/` 文件夹（**没有就点「新建文件夹」创建**），数据库会自动生成在这里。

## 第 2 步：创建 Python 项目（启动后端）

1. 左侧菜单点 **「网站」** → 顶部切到 **「Python项目」** 标签。
2. **先创建虚拟环境**（宝塔 v13 不允许直接用系统 Python 跑项目，必须基于它建虚拟环境）：
   - 在「Python项目」页面顶部找到 **「Python 版本管理」**（或「Python 环境管理」）按钮，点进去。
   - 找到 **Python 3.13.5** 那一行，点它右侧的 **「创建虚拟环境」**（有的版本是个「+」或「虚拟环境」图标）。
   - 填一个名称，如 `blog_env` → 确定，等它创建完成（约几秒到 1 分钟）。
   - 如果面板里实在找不到「创建虚拟环境」入口，就用宝塔「终端」执行：
     ```bash
     cd /www/wwwroot/myblog
     python3 -m venv venv
     ```
     然后在「添加项目」的 Python 版本处，通过「自定义/手动指定」选 `/www/wwwroot/myblog/venv/bin/python`。
3. 点 **「添加项目」**，按下表填写：

   | 表单项 | 填写内容 |
   |---|---|
   | 项目名称 | `myblog` |
   | 项目路径 | `/www/wwwroot/myblog` |
   | Python 版本 | 选刚创建的 **`blog_env`**（虚拟环境，不要选"系统Python"） |
   | 启动方式 | 选 **gunicorn**（Flask） |
   | 启动文件 | `app.py` |
   | 启动对象/入口 | `app` |
   | 监听端口 | `8686`（示例值；面板填多少，第 4 步 Nginx 反代就写多少，保持一致即可） |
   | 依赖安装 | ✅ 勾选（自动 pip install） |
   | 开机启动 | ✅ 勾选 |

   > **必须在「环境变量」栏填写的两项（缺失程序会拒绝启动）**：
   > - `SECRET_KEY`：随机会话密钥。可在服务器终端执行 `python3 -c "import secrets;print(secrets.token_hex(32))"` 生成一串粘贴进来。
   > - `ADMIN_PASSWORD`：初始管理员密码（首次登录后台会强制你修改），例如 `Kx9mP2vL8qW7c4`。
   >
   > 建议同时填：
   > - `SITE_URL`：你的域名，如 `https://blog.example.com`（RSS/sitemap 生成绝对链接用）。
   >
   > 可选：
   > - `COOKIE_SECURE=true`（HTTPS 部署推荐）、`BLOG_OPEN_REGISTER=false`（关闭公开注册）、`CORS_ORIGIN`（前后端分离时的前端域名列表，一般留空即可）。
   > - `WH_DEPLOY_SECRET`（开启 Webhook 自动部署接口）、`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` / `WECOM_WEBHOOK_URL`（新文章推送）、`DATABASE_URL`（默认 SQLite，一般不用填）。
   > - **邮件群发不需要在环境变量配**：登录后台 → 「📧 邮件设置」直接填 SMTP 即可（见下方「邮件设置」章节）。若你更想用环境变量，也可配 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_SSL`（后台设置优先于环境变量）。
   >
   > **安全加固可选配置**（不配用默认值即可）：
   > - `REDIS_URL`：多 worker 部署时启用 Redis 全局限流计数（如 `redis://127.0.0.1:6379/0`）。**不配则自动回退进程内内存滑动窗口**，单 worker 无影响，多 worker 限流各自独立（略弱但可用）。
   > - `SMTP_PASSWORD_ENV_FIRST`：默认 `true`——SMTP 密码优先读环境变量 `SMTP_PASSWORD`，库值仅兜底（避免数据库泄露时密码直接暴露）。
   > - `STRONG_PASSWORD`：默认 `true`——启用弱密码黑名单 + 字母/数字复杂度校验；`false` 关闭。
   > - `STRONG_PASSWORD_MIXED_CASE`：默认 `false`——`true` 时额外要求大小写混合。
   > - `LOGIN_DELAY_SECONDS`：默认 `1`——登录失败统一延迟秒数（消除用户名枚举时序侧信道）。
   > - `SESSION_IDLE_MINUTES`：默认 `60`——登录会话闲置多少分钟后强制重新登录；`0` 关闭。
   > - `AUDIT_LOG_DAYS`：默认 `90`——审计日志保留天数，超期自动清理。
   > - `CAPTCHA_ENABLED`：默认 `true`——注册/评论/留言启用图形验证码（服务器未装 Pillow 时自动降级关闭）。
   > - `SECURITY_HEADERS`：默认 `true`——追加 X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy 安全响应头。
   > - `UPDATE_HMAC_KEY`：可选——为发布包生成 HMAC 签名并在 `update.sh` 校验（增强更新包完整性，见「一键更新」章节）。
   > - `FEED_FETCH_TIMEOUT`：默认 `8`——友链 RSS 聚合抓取 socket 超时（秒）；不可达/超慢源超时只跳过、不卡死 worker。
   > - `TIME_ZONE`：固定 `Asia/Shanghai`（北京时间，UTC+8）；全站时间按此展示，**暂不可经环境变量改**（避免 UI 内部错位）。展示层统一转北京时间，数据库存储仍为 UTC。
   > - `ENABLED_PLUGINS` / `DISABLED_PLUGINS`：插件启用 / 紧急关停列表（内置插件当前默认全部下线，默认留空；`DISABLED_PLUGINS` 优先级更高，紧急关停单个插件用，重启生效）。

4. 点 **「提交」**。等待依赖安装完成（首次约 1-3 分钟，面板会显示进度）。
5. 项目状态变为 **运行中（绿色）** 即成功。若报错，点项目右侧 **「日志」** 查看原因。

## 第 3 步：上传前端静态文件

1. 仍在 **「文件」** 管理，进入 `/www/wwwroot/`。
2. 点 **「新建文件夹」** → 命名 `vue-frontend` → 回车创建，然后进入该文件夹。
3. 点 **「上传」** → 选择本地电脑的 `vue-frontend-dist.zip` → 上传完成后**右键解压**。
4. **重要**：解压后 `vue-frontend/` 里应**直接**有 `index.html` 和 `assets/` 文件夹。
   - 如果出现的是 `dist/index.html`（多套了一层），把 `dist` 里的内容全部**剪切**到 `vue-frontend/` 根目录。

## 第 4 步：添加网站并配置反代

1. 左侧菜单点 **「网站」** → 顶部切到 **「HTML项目」** 标签（前端是纯静态站）。
2. 点 **「添加站点」**：
   - 域名：填你的域名（如 `blog.example.com`；可同时添加 `www.blog.example.com`）
   - 根目录：选 `/www/wwwroot/vue-frontend`
   - 纯静态/HTML 类型，其他默认 → 提交。
3. 添加完成后，在站点列表点该站点的 **「设置」**（或直接点进网站）。
4. 左侧点 **「配置文件」**，在 `server { }` 块里**找到并替换** `location / { ... }` 这段为（整段复制粘贴覆盖）：

```nginx
    # Vue 单页应用：找不到文件就回退到 index.html（刷新/直达文章页不 404）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ⚠️ 根路径下的 Flask 路由（RSS / sitemap / robots / 评论RSS）必须反代给后端，
    # 绝不能落入上面的 location / 被 SPA 兜底成 index.html，否则 RSS 阅读器
    # 拿到的是 HTML 而非 XML → 表现为「朋友订阅不了 RSS」。这几段必须放在
    # location / 之前（精确匹配优先于前缀匹配）。
    location = /feed.xml {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location = /sitemap.xml {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location = /robots.txt {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ⚠️ 评论 RSS 订阅源 /feed/comments：必须反代给后端，
    # 否则会被 location / 兜底成 index.html（拿到 HTML 而非 RSS XML）。
    # 用前缀匹配，同时覆盖「/feed/comments」与「/feed/comments/」两种写法。
    location /feed/comments {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端接口反代
    location /api/ {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后台管理反代（宝塔「Python项目」可能已自动加一条，有就不用重复）
    location /admin {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ⚠️ Flask 静态资源（admin.css / style.css / script.js / 上传的图片）
    # 宝塔不会自动加这条！不加的话 /static/* 会到 vue-frontend 目录里找，返回 404，
    # 表现为「后台能打开但完全没有样式（全文本）」
    location /static/ {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

> 端口 `8686` 要与第 2 步 Python 项目里填的「监听端口」一致。`/api/`、`/admin`、`/static/` 三段都要有；`/feed.xml`、`/sitemap.xml`、`/robots.txt`、`/feed/comments` 四段是 RSS/SEO 的根路径路由，**同样必须反代给后端**，否则会落到 `location /` 被 SPA 兜底成 `index.html`（RSS 阅读器收不到 XML、搜索引擎抓不到 sitemap）。缺一不可。

5. 点 **「保存」** → 再点 **「重载配置」**（或重启 Nginx）。
6. 浏览器访问 `http://你的域名`，应能看到博客首页（文章列表 + 右侧边栏 + 天气）。

## 第 5 步：开启 HTTPS（强烈推荐）

1. 站点 **「设置」** → 左侧 **「SSL」** → 选 **Let's Encrypt** → 勾选你的域名 → 点 **「申请」**（约 30 秒-1 分钟）。
2. 申请成功后打开 **「强制 HTTPS」**。之后都用 `https://你的域名` 访问。

> 若申请失败提示"域名验证不通过"，说明域名还没解析成功，等几分钟再试。

## 第 6 步：首次登录设置管理员（上线安全第一步）

> **登录已统一**：前台 `/login` 和后台是**同一套账号体系、同一个登录入口**。访问 `/admin` 未登录时会自动跳到 `/login?next=/admin`，登录成功后按权限自动回到后台。

1. 浏览器打开 `https://你的域名/login`（或直接访问 `/admin` 也会跳到这里）。
2. 用初始账号登录：用户名 `admin`（或环境变量 `ADMIN_USERNAME` 指定的名字），密码为环境变量 `ADMIN_PASSWORD` 里设置的值（不是 admin123）。
3. 超级管理员首次登录会**强制跳转到「设置管理员账号」页面**：
   - 用户名：填你想要的（可沿用 admin 或改成别的）；
   - 新密码：至少 8 位的强密码；
   - 确认新密码。
4. 点 **「保存并进入后台」** → 进入后台仪表盘，旧密码立即失效。
5. 权限分级（登录即鉴权）：
   - **超级管理员**：全部后台功能 + 用户管理；
   - **管理员**：除用户管理外全部后台功能；
   - **普通注册用户**：只能前台浏览/评论，访问 `/admin` 会被拦截。
6. 建议马上做三件事：
   - 后台 **站点设置**：博客名称、站点标题、浏览器便签、主题色、默认天气城市；
   - **分类管理 / 标签管理**：建分类；
   - **写新文章**：发第一篇正式文章。

## 第 7 步：上线验证清单

| 检查项 | 地址 | 期望结果 |
|---|---|---|
| 首页 | `https://你的域名/` | 文章列表、侧边栏（含「📬 邮件订阅」框）、天气组件 |
| 文章页 | `https://你的域名/post/xxx` | 打开文章，**直接刷新不 404** |
| 登录/注册 | `https://你的域名/login`、`/register` | 页面正常，可注册 |
| 后台 | `https://你的域名/admin` | 用新账号登录进仪表盘；**左下角显示版本号**（如 vX.Y.Z，点它直达 GitHub Releases 比对最新版） |
| 广场 | `https://你的域名/square` | 微动态 + 博客圈 + 社交账号墙可打开 |
| 系列 | `https://你的域名/series` | 系列列表页可打开（空列表正常） |
| 留言墙 | `https://你的域名/guestbook` | 留言页可打开，登录后可留言 |
| 公告 | 后台新建一条公告 | 前台每个页面顶部出现横幅 |
| 订阅 | 前台侧边栏填邮箱提交 | 提示订阅成功；后台「✉️ 订阅者」能看到该邮箱，并支持删除 / 启用停用 |
| 搜索 | 前台搜索关键词 | 返回结果（接口 `engine` 字段为 `fts5` 或 `like`） |
| RSS | `https://你的域名/feed.xml` | 显示 XML |
| API | `https://你的域名/api/site` | 返回 JSON |

---

## 日常维护

- **写文章**：`/admin` → 写新文章（Markdown，可插图、设封面、标签、分类）。
- **后台开关类功能**：验证码「🛡️ 验证码设置」（注册/评论/留言独立开关，服务器未装 Pillow 自动降级）；反爬限流「🛡️ 反爬限流保护」（默认关闭，开启后搜索引擎自动豁免）；插件「🧩 插件管理」（运行时启停/重载）。
- **改后端代码**：改 `myblog/` 下文件后，到「网站 → Python项目」对该项目点 **「重启」**。
- **改后台样式（admin.css / script.js）**：后台静态资源已绑定 `APP_VERSION` 版本戳，并对这两个文件加 `no-cache` 响应头——**发版后浏览器/微信自动拉新**，无需手动清缓存；若手动替换文件，重启项目 + 强刷（Ctrl+F5）即可。
- **改前端**：以后修改 `vue-frontend` 源码后**本地重新 `npm run build`**（不构建就上传等于没改），把新的 `index.html` + `assets/` 覆盖上传即可（**无需重启**，记得强刷浏览器）。
- **看后端日志**：「网站 → Python项目」→ 项目右侧 **「日志」**。
- **备份（重要）**：**推荐后台「💾 数据备份」页一键备份 + 宝塔定时任务跑 `backup.sh`**（每天凌晨执行 `bash /www/wwwroot/myblog/backup.sh`），自动打包 `blog.db` + 上传目录；异地容灾在后台「⚙️ 备份配置」页填目的地（OSS / SCP / WebDAV，密钥加密存库、页面只回显掩码；老 `BACKUP_*` 环境变量仍兼容，密钥环境变量优先）。手动兜底（⚠️ 数据库已启用 WAL 模式，**不能直接拷 `blog.db`**，会漏未 checkpoint 数据）：
  - 数据库：`sqlite3 /www/wwwroot/myblog/data/blog.db ".backup /www/backup/myblog/blog_$(date +%F).db"`
  - 上传目录：`/www/wwwroot/myblog/static/uploads/`（全部图片）
  - 恢复：把备份的 `blog.db` 传回 `myblog/data/` 后**务必「停止 → 启动」站点**（后台恢复页恢复前会自动打快照并写审计日志，异常可回退）
  - ⚠️ **WAL 产物别手删**：`data/` 下 `blog.db-wal`、`blog.db-shm` 是正常产物，删 `-wal` 可能丢已提交数据；到「🩺 全站体检 → 数据库健康」确认 `journal_mode=WAL`、`busy_timeout=5000`（显示 `delete` 则检查 `data/` 对运行用户的写权限）

> **备份自动化（建议）**：建议在宝塔「计划任务」（或 crontab）加一条**每日凌晨**备份，一条命令搞定：
> ```bash
> # 宝塔「计划任务」→「Shell 脚本」，每天 03:00 执行（数据库走 sqlite3 在线备份，WAL 安全）：
> mkdir -p /www/backup/myblog && sqlite3 /www/wwwroot/myblog/data/blog.db ".backup /www/backup/myblog/blog_$(date +%F).db" && cp -r /www/wwwroot/myblog/static/uploads /www/backup/myblog/uploads_$(date +%F)
> ```
> 保留最近 N 份自动清理（可选，如只留 14 天）：
> ```bash
> find /www/backup/myblog -name '*.db' -mtime +14 -delete
> ```

- **恢复**：把 `blog.db` 传回 `myblog/data/`，重启 Python 项目即可。

> **Nginx 真实 IP 转发（运维要点）**：第 4 步反代配置已含 `X-Real-IP` / `X-Forwarded-For`，后端据此识别访客真实 IP（限流 / 访问统计 / 评论记录都依赖它）。**请确认** `location /api/`、`location /admin`、`location /static/` 三段都带全这两个头（上面配置模板已含，保持原样即可）。若站点再套了 CDN（如腾讯云 CDN / 又拍云），还要在 Nginx 里把 CDN 回源 IP 加入 `real_ip` 信任列表，否则统计/限流看到的是 CDN 节点 IP：
> ```nginx
> # 在 server{} 内（CDN 场景才需要）：
> set_real_ip_from 你的CDN节点IP段;
> real_ip_header X-Forwarded-For;
> ```
> **TRUSTED_PROXIES（限流/统计取真实 IP 的收口）**：默认留空即可——仅私网/回环等内部地址视为可信代理，本机 Nginx 反代（`remote_addr=127.0.0.1`）天然可信。**若站点套在「remote_addr 为公网 IP」的前置代理 / CDN（Cloudflare、云 LB、CDN）之后**，必须在环境变量显式填 `TRUSTED_PROXIES`（逗号分隔 IP/CIDR），否则拿不到真实访客 IP；同时 Nginx 建议改 `proxy_set_header X-Forwarded-For $remote_addr;`（替换而非追加，杜绝客户端自填）。
> **强制 HTTPS（强烈推荐）**：站点「设置 → SSL → 强制 HTTPS」打开后，所有 http 请求自动 301 到 https。配合 `COOKIE_SECURE=true` 环境变量，会话 Cookie 仅走 HTTPS，杜绝中间人窃取登录态。

> ⚠️ **数据库保护说明**：部署包 `myblog-backend.zip` **不包含 `data/` 目录**，解压覆盖不会动你服务器上已有的 `blog.db`（文章/评论/设置都安全保留）。
> 新增的表与列（统计表、评论嵌套字段、系列/公告/留言/订阅者表、is_read 列等）在项目**重启时自动迁移创建**，无需手动建表。

---

## 一键更新脚本（懒人版 · 推荐，连重启都自动）

> 仓库根目录的 **`update.sh`**：一条命令自动完成「下载最新 Release → 备份数据 → 覆盖代码 → **自动重启后端**」，全程无需手动操作。
> ⚠️ 服务器上的 `update.sh` 务必与最新 Release 同版：脚本经历过「假成功不覆盖 / 校验误报 / 无法自动重启」多轮加固，老脚本先覆盖再跑。

**首次配置（只需一次，约 3 分钟）：**

1. 在仓库下载 `update.sh`（[GitHub 仓库根目录](https://github.com/Llhhy1/llhhy-blog) → 点 `update.sh` → 右上角「Download raw file」）。
2. 宝塔「文件」→ 上传到 `/www/wwwroot/myblog/update.sh`。
3. （推荐）确认宝塔环境支持自动重启，见下方「宝塔环境配置（自动重启的前提）」。
4. 宝塔「终端」执行一行：
   ```bash
   bash /www/wwwroot/myblog/update.sh
   ```
5. 脚本跑完即更新完成。以后每次更新**只需要再跑这一条命令**；也可以配置宝塔「计划任务」每周自动跑一次（shell 脚本任务，命令同上），连跑都不用跑。

> **脚本做了什么**：查最新版本号 → 下载后端/前端 zip → 备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/` → 覆盖代码（跳过 `data/`，数据库永远保留）→ **自动重启后端**（见下）。
>
> **自动重启原理（懒人的关键）**：脚本依次尝试——
> ① 若脚本顶部填了 `RESTART_CMD`，直接执行它（supervisor `restart` 本身是停+起，安全）；
> ② 探测 `supervisorctl`（宝塔 Python 项目底层就是 supervisor 管理），自动找到指向你项目目录的 supervisor 项目名并 `restart`；
> ③ 若没装 supervisor，则**真杀 gunicorn master（`kill -TERM`）→ 等待退出 → 用记录的启动命令重新拉起**（见下方 `start_cmd.txt`）；
> ④ 以上都失败才提示手动去宝塔点「停止→启动」。
>
> ⚠️ **严禁 HUP 热重载**：早期脚本用 `pkill -HUP` 优雅重载，但 HUP 只让 gunicorn master fork 新 worker、**master 不退出**。当版本改动涉及 import / 表结构（如新增多张表 + 模型 import）时，老 worker 仍在服务旧代码，表现为「更新完不重启 / 还是旧版」。已改为「真杀 + 真启动」。
>
> 脚本顶部可填：`PROJECT_NAME="myblog"`（宝塔 Python 项目名，填了重启最稳）、或 `RESTART_CMD="supervisorctl restart myblog"`（手动指定重启命令，优先级最高）。

### 宝塔环境配置（自动重启的前提）

要让脚本能"一键重启"，服务器需要满足以下任一条件（**都不需要也行**，脚本会退化为提示你手动点）：

| 方式 | 需要做什么 | 效果 |
|---|---|---|
| **A. supervisor（推荐，最稳）** | 宝塔「软件商店」搜索安装 **Supervisor 管理器**（宝塔自带插件）；装好后**重启一次 Python 项目**让 supervisor 接管 | 脚本自动 `supervisorctl restart`，完全自动 |
| **B. 记录启动命令（无 supervisor 时推荐）** | 把宝塔 Python 项目的「启动命令」写入 `data/start_cmd.txt`（见下） | 脚本真杀 gunicorn 后用该命令重新拉起，全自动 |
| C. 手动 | 无 | 脚本最后提示你去宝塔点「停止→启动」 |

**方式 B 配置（只需一次）**：在宝塔「Python 项目 → 设置 → 启动命令」复制那行命令，在服务器终端执行（把 gunicorn 启动那行原样写进文件，注意用 `nohup ... &` 后台化）：

```bash
# 示例（按你宝塔实际启动命令改）：
echo 'nohup /www/wwwroot/myblog/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app >/www/wwwroot/myblog/gunicorn.log 2>&1 &' > /www/wwwroot/myblog/data/start_cmd.txt
```

> 此后 `update.sh` 在第 ③ 步会自动 `kill -TERM` 旧进程并用 `start_cmd.txt` 重新拉起，实现真正的「停止→启动」。

**确认 supervisor 是否接管了你的项目**（宝塔终端执行）：

```bash
supervisorctl status
# 若输出里有你的项目名（如 myblog RUNNING）→ 方式 A 生效，脚本可全自动重启
# 若提示 command not found → 未装 supervisor，走方式 B/C
```

> 装好 supervisor 后记得：宝塔「网站 → Python项目」→ 你的项目 → 重新「停止→启动」一次（让 supervisor 注册接管），再跑 `supervisorctl status` 确认。

## 后台一键在线更新（最懒人）

> 连终端都不用进：**登录后台 → 自动检测到新版本 → 点「立即更新」→ 后台静默完成 → 提示刷新**。全程无需 SSH、无需传文件。

**「检查更新」入口**：点击后台左下角版本号旁的「检查更新」，**在后台直接判断**是否有新版本（不再跳转 GitHub）——有新版本弹出推荐更新条（含「立即更新」按钮）；已是新版提示「✅ 当前已是最新版本」；网络不通提示稍后再试。

**前置条件（只需一次）**：按上一节把 `update.sh` 上传到 `/www/wwwroot/myblog/update.sh`（并建议装好 supervisor 让重启自动）。之后一切在后台操作。

**使用流程：**

1. 超管登录后台，页面底部自动弹出提示条：
   > 「发现新版本 vX.Y.Z（当前 vA.B.C），是否立即在线更新？（将自动备份数据库并重启）」
2. 点 **「立即更新」** → 提示条变为「🔄 后台正在更新…（自动备份→覆盖→重启，请勿关闭本页）」
3. 后台自动完成：下载最新包 → **备份数据库和图片**（`data/backup/`）→ 覆盖代码 → 自动重启
4. 完成 → 提示条显示「✅ 更新完成，请刷新页面」→ 约 2.5 秒后自动刷新，后台左下角即为新版本号

**要点与安全：**

- 只有**超管/管理员**能看到和触发（普通用户触发返回 403）；
- 更新是**异步后台进程**，不阻塞后台其他操作；正在更新时再次触发会被拒绝（防重入）；
- 每次更新前自动备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/`，数据库永远不会被覆盖；
- 若更新中途失败（网络/包损坏），提示条会显示失败原因，数据保持原样（备份仍在）；
- 页面刷新或重新登录时，如果更新还在进行中，会自动进入轮询继续显示进度。


## 版本升级（通用流程 · 任意旧版 → 最新版）

> 适用：服务器已部署过旧版本，要升级到最新 Release。**只需覆盖代码 + 重启，不要删目录。**
> 各版本的逐版升级说明已归档至仓库根目录 [`CHANGELOG.md`](../CHANGELOG.md)，本手册只保留当前最新版的全量部署与运维口径。

1. **备份（最重要）**：到「文件」下载留底：
   - `/www/wwwroot/myblog/data/blog.db`（全部数据）
   - `/www/wwwroot/myblog/static/uploads/`（上传的图片）
2. **先确认真实运行目录**（避免解压到错误路径）：
   - 宝塔「网站 → Python项目」→ 点该项目 → 看「项目路径」；
   - 或终端执行 `ls -la /www/wwwroot/*/data/blog.db`，数据库在哪，项目就在哪。
3. **覆盖后端**：上传新版 `myblog-backend.zip` → 解压到上述真实目录。
   - ⚠️ zip 内自带一层 `myblog/`，解压后应合并进运行目录，**避免出现 `myblog/myblog/` 嵌套**；
   - 确认 `data/` 目录和 `blog.db` 还在（没删目录就一定在）。
4. **重启后端（关键）**：宝塔「网站 → Python项目」→ 该项目 → **先点「停止」，再点「启动」**。
   - ⚠️ 只点「重启」可能只是重载配置，gunicorn 旧进程没退出，页面还是旧版；
   - 可用 `ps -ef | grep gunicorn` 看进程启动时间，确认是新进程；
   - 若需对齐迁移基线，可在站点目录执行一次 `flask db stamp head`（幂等无害、不改变任何表结构；`flask db heads` 应显示基线 `f8f1f29b6ddf`）。
5. **覆盖前端**：上传新版 `vue-frontend-dist.zip` 到 `/www/wwwroot/vue-frontend/` → 解压覆盖 `index.html` + `assets/`（**无需重启后端**）。
6. **验证**：浏览器**无痕窗口**打开（避免缓存）：
   - 后台左下角显示 `vX.Y.Z`，与 [GitHub Releases](https://github.com/Llhhy1/llhhy-blog/releases) 最新标签一致 → 后端升级成功；
   - 前台侧边栏出现「📬 邮件订阅」→ 前端升级成功。
7. **环境变量**：只覆盖文件 + 重启，环境变量原样保留，无需重填；**若误删 Python 项目重建，必须重填 `SECRET_KEY` / `ADMIN_PASSWORD`**（缺失拒绝启动）。改 `SECRET_KEY` 会让已登录用户需要重新登录，属正常现象。

> ⚠️ **服务器上的 `update.sh` / `deploy.sh` 也务必与最新 Release 同版**：脚本经历过「假成功不覆盖 / 校验误报 / 无法自动重启」多轮加固，升级前先从最新 Release 覆盖一次脚本，再跑一键更新。

---

## MCP 配置指南（两个端点一次配好：只读 `/mcp` ＋ 写能力 `/mcp-write`）

> 本节是**统一操作手册**；两端各自的来龙去脉（引入背景与安全设计）见仓库根目录 `CHANGELOG.md` 的 v3.10.0 / v3.12.2 条目。
> 两个端点**完全独立**（各自 token / 各自开关 / 互不影响），但环境变量、Nginx、AI 助手接入可以**一次配完**。

### 两个端点速览

| | 只读诊断 `/mcp` | 写能力 `/mcp-write` |
|---|---|---|
| 用途 | AI 远程读健康状态（全站体检、DB 状态、版本一致性、错误日志、内容统计） | AI 远程建文（`create_post` 默认草稿；`list_recent_posts` 查重） |
| token 变量 | `MCP_AUTH_TOKEN` | `MCP_WRITE_TOKEN`（**必须与前者取不同值**） |
| 未配 token 时 | 整体关闭（401） | 整体关闭（**404**，连端点存在都不暴露） |
| 限流 | 60 次/分钟/IP | 10 次/分钟/IP（更严） |
| 审计 | — | 每次调用写「🧾 操作日志」（后台可查，username=`mcp`，记 token 前 8 位与来源 IP） |

### 第 1 步：生成两个不同的 token

```bash
python3 -c "import secrets;print(secrets.token_hex(32))"   # 跑两次，分别得到两个不同值
```
第 1 次输出 → `MCP_AUTH_TOKEN`；第 2 次输出 → `MCP_WRITE_TOKEN`。**不要填进代码、不要提交 git**。

### 第 2 步：宝塔填环境变量（Python 项目 → 设置 → 环境变量）

| 变量 | 必填？ | 说明 |
|---|---|---|
| `MCP_AUTH_TOKEN` | 用 `/mcp` 就必填 | 留空 = `/mcp` 关闭（401），不会裸奔 |
| `MCP_LOG_FILES` | 可选 | `/mcp`「最近错误日志」工具可读的日志绝对路径，逗号分隔；留空该工具不可用 |
| `MCP_ALLOWED_ORIGINS` | 可选 | 额外合法 Origin 白名单（防 DNS 重绑定），两端共用，一般留空 |
| `MCP_WRITE_TOKEN` | 用 `/mcp-write` 就必填 | 留空 = `/mcp-write` 关闭（404）；**须与 `MCP_AUTH_TOKEN` 不同值** |
| `MCP_WRITE_DEFAULT_PUBLISH` | 可选 | 默认 `0` = 无论请求传什么都**强制转草稿**；改 `1` 才允许 MCP 直接发布 |
| `MCP_WRITE_ALLOW_NOTIFY` | 可选 | 默认 `0` = 不群发；改 `1` 且请求显式 `notify_subscribers=true` 才通知订阅者 |
| `MCP_WRITE_ALLOW_SUPER_FIELDS` | 可选 | 默认 `0` = 忽略提权字段（`is_pinned`/`is_private`/`reward_*`/`author_id`） |

填完「保存」，然后宝塔对 Python 项目「**停止 → 启动**」（restart 不重载环境变量）。

### 第 3 步：Nginx 补两段反代（一次复制两段）

> 放在 `server { }` 里 `location / { ... }` 之前（精确匹配优先于前缀匹配，不加会被 Vue SPA 兜底成 index.html）。
> `8686` 改成你 Python 项目的实际监听端口。加完点「重载配置」。**站点必须 HTTPS**（token 走请求头）。

```nginx
location = /mcp {
    proxy_pass http://127.0.0.1:8686;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /mcp-write {
    proxy_pass http://127.0.0.1:8686;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

（可选，推荐）两段各加 IP 白名单，只放行你常用的出口 IP：
```nginx
    allow 你的公网IP;
    deny all;
```

### 第 4 步：上线核验（curl 四连，服务器或本机执行）

```bash
# ① /mcp 不带 token → 必须 401（若返回 HTML 说明反代没生效）
curl -i -X POST https://你的域名/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ② /mcp 带对 token → 返回工具列表 JSON
curl -s -X POST https://你的域名/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H "Authorization: Bearer 只读TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ③ /mcp-write 不带 token → 必须 404（已配 token 而没带对则是 401）
curl -i -X POST https://你的域名/mcp-write -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ④ /mcp-write 带对 token → initialize 握手 JSON（server 名 llhhy-blog-write）
curl -s -X POST https://你的域名/mcp-write -H 'Content-Type: application/json' \
  -H "Authorization: Bearer 写TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

### 第 5 步：AI 助手接入（本机 `~/.workbuddy/mcp.json`，两个 server 一起配）

```json
{
  "mcpServers": {
    "llhhy-blog-diag": {
      "type": "http",
      "url": "https://你的域名/mcp",
      "headers": { "Authorization": "Bearer 只读TOKEN" }
    },
    "llhhy-blog-write": {
      "type": "http",
      "url": "https://你的域名/mcp-write",
      "headers": { "Authorization": "Bearer 写TOKEN" }
    }
  }
}
```

保存后到 WorkBuddy 连接器管理页，对 `llhhy-blog-diag`、`llhhy-blog-write` 各点一次「**信任**」才生效。之后可直接说「博客现在健康吗」（走只读）或「帮我建一篇草稿，标题是…正文是…」（走写端点，默认落草稿，后台审核后发布）。

### 安全红线（两端通用）

站点强制 HTTPS；token 定期轮换（两端分开轮换）；`/mcp` 尽量加 IP 白名单；写端点建议**保持 `MCP_WRITE_DEFAULT_PUBLISH=0`**（AI 只落草稿、人工后台把关发布），发布动作全部可在「🧾 操作日志」回溯。

## 邮件设置（新文章通知订阅者 · 后台配置）

> 邮件群发配置**不需要填环境变量**，直接在后台操作（更便捷）。

1. 登录后台 → 左侧「**📧 邮件设置**」（超管可见）。
2. 填写 SMTP 信息：
   | 字段 | 示例（QQ 邮箱） | 说明 |
   |---|---|---|
   | SMTP 服务器 | `smtp.qq.com` | 163 用 `smtp.163.com`，Gmail 用 `smtp.gmail.com` |
   | 端口 | `465` | QQ/163 用 465（SSL）；部分服务用 587（TLS，需取消勾选 SSL） |
   | 邮箱账号 | `你的QQ号@qq.com` | 发件登录账号 |
   | 授权码/密码 | `xxxxxxxxxxxxxxxx` | **QQ/163 邮箱必须用「授权码」**（邮箱设置 → 账户 → 开启 SMTP 后生成），不是登录密码 |
   | 发件人地址 | 同邮箱账号 | 一般等于账号 |
   | 使用 SSL | 勾选（465） | 587 端口取消勾选 |
3. 点「保存」→ 再填一个测试收件人邮箱 → 点「**发送测试邮件**」，收到邮件即配置成功。
4. 之后每次发布新文章，会自动给「✉️ 订阅者」里所有 active 邮箱发通知（含一键退订链接）。
   - 未配置 SMTP 时群发自动跳过，不影响发文章。

> **排错（异常栈直接打印到站点日志）**：若点「发送测试邮件」仍提示「错误详情见后端日志」，重部署后真实异常会打印到站点日志。定位站点目录：`ls /www/wwwroot/*/data/blog.db`（父目录即 `APP_DIR`）；查看：`tail -n 60 /www/wwwroot/<站点>/gunicorn.log | grep "SMTP ERROR"`。常见真实报错与对策：
> - `535 Authentication failed` → 授权码错（QQ/163 必须用邮箱后台生成的**授权码**，不是登录密码）。
> - `timeout` / `Connection refused` → 主机名拼错、端口错，或服务器出站 465/587 被防火墙/安全组拦截（国内机器常见）。
> - `SSL: wrong version number` → 端口与 SSL 开关不匹配：465 **必须勾选** SSL，587 **必须取消**勾选。
> - 另注意 `SMTP_PASSWORD_ENV_FIRST`（默认 `true`）：宝塔环境变量里的 `SMTP_PASSWORD` 优先于后台填的密码，若两者不一致以环境变量为准——核对宝塔「Python 项目 → 设置 → 环境变量」是否覆盖。

## 友链 RSS 聚合到广场（博客圈）· 排错（失败原因日志可见）

> 广场（博客圈）页面的「友链 RSS 聚合」依赖后台「友链管理」里给友链填的 RSS 地址。若广场上始终看不到友链文章，按以下顺序排查。

1. **确认友链填了 RSS 地址**：后台 → 「🔗 友链管理」→ 给每个要聚合的友链填 `RSS 地址`（如 `https://example.com/feed.xml` 或 `atom.xml`）。未填的友链不会聚合。
2. **确认服务器装了 feedparser**：SSH 进服务器 `pip show feedparser`；若未安装，在站点 Python 环境执行 `pip install feedparser==6.0.11`，然后宝塔「停止 → 启动」gunicorn。若未装，日志会明确提示 `pip install feedparser==6.0.11`。
3. **确认服务器能出站抓 RSS**：服务器安全组/防火墙放行出站 443（HTTPS RSS 多为 443）。可用 `curl -I https://友链RSS地址` 在服务器上自测连通性。
4. **看日志定位具体失败**：
   - 定位日志：`tail -n 60 /www/wwwroot/<站点>/gunicorn.log | grep "FEED AGG"`
   - 四类提示：
     - `[FEED AGG] 共 N 条友链，其中 0 条填写了 RSS 地址` → 后台补填 RSS 地址即可。
     - `[FEED AGG] 跳过友链「X」：RSS 地址未通过安全校验` → RSS 地址指向私有 IP（SSRF 防护拦截），换公网可访问地址。
     - `[FEED AGG] feedparser 未安装！` → 按提示 `pip install feedparser==6.0.11` 后重启服务。
     - `[FEED AGG] 抓取友链「X」RSS 失败: <错误类型>: <消息>` → 具体错误（超时/证书/格式），按消息修复（多为出站网络或 RSS 格式问题）。
5. **缓存**：聚合结果内存缓存 15 分钟。确认配置正确后，等 15 分钟或重启服务即时生效。

## 自动部署（GitHub push → 服务器自动更新）

> 想让「GitHub 推送代码 = 服务器自动更新」，只需三步。**可选功能，不配不影响使用。**

### 第一步：准备部署脚本

仓库根目录已提供 `deploy.sh` 模板（从 GitHub Release 下载最新 zip → 备份 data/ 和 uploads → 覆盖代码 → 重启）。上传到服务器：

```bash
# 宝塔「文件」上传 deploy.sh 到 /www/wwwroot/myblog/，然后终端执行：
chmod +x /www/wwwroot/myblog/deploy.sh
```

按你的环境修改脚本顶部的三个变量：`REPO`（默认已对）、`APP_DIR`、`FRONT_DIR`，以及 `RESTART_CMD`（重启方式，见脚本内注释）。

> **一键更新重启权限（重要）**：若一键更新卡在第⑥步 `Operation not permitted`，根因是 gunicorn 由宝塔以 **`mw` 用户**（非 `www`）启动，且宝塔 Python 项目**不是** supervisor 管理。请用**最新 Release 附带的部署脚本**覆盖 `update.sh`/`deploy.sh` 到 `/www/wwwroot/myblog/`（最新版重启逻辑：宝塔 CLI 优先 → 以实际运行用户 `runuser` 真杀 + 宝塔真实 gunicorn 路径重新拉起，彻底绕开跨用户 kill）。若项目名不是 `myblog`，改两个脚本里的 `PROJECT_NAME`；若 gunicorn 属主不是 `mw`，改 `APP_USER`。

> **一键更新完整性校验（三重防线）**：
> - **① sha256.txt 列表比对**：`update.sh` 下载后端/前端部署包后比对 Release 附带的 `sha256.txt`，不一致**直接终止更新**（防止下载损坏/被篡改）。
> - **② zip 注释内嵌哈希**：`package.py` 打包时把每个 zip 的 **「内容区」SHA256**（= 剥离 EOCD 尾注释后的 zip 字节，写入/修改注释不影响内容区）写进该 zip 自身的 EOCD 注释；`update.sh` 用内置 python 同样剥离注释重算内容区哈希二次比对。即使 `sha256.txt` 被整体替换，注释哈希依然能发现不一致（双源互证，解决「sha256.txt 自身被篡改」的死角）。注意：注释哈希按内容区计算，不能对含注释的整文件算（注释参与文件字节后必然对不上）。
> - **③ HMAC 签名**（可选）：若发布时设置了 `UPDATE_HMAC_KEY`，`package.py` 会为 `sha256.txt` 内容生成 HMAC 首行，`update.sh` 配置同一密钥后强制校验签名（不签名直接拒绝更新）。设置方法：本地打包机与服务器都配置同一个 `UPDATE_HMAC_KEY` 环境变量。
>
> 发布时请确保 `package.py` 生成的 `sha256.txt` 一并上传到 Release；若某次 Release 漏传，脚本会告警但不阻断（降级为仅告警）。

### 第二步：告诉后端脚本路径

宝塔「网站 → Python项目」→ 项目「设置」→「环境变量」新增：

```
DEPLOY_SCRIPT=/www/wwwroot/myblog/deploy.sh
```

> 同时建议配 `WH_DEPLOY_SECRET`（一段随机字符串），它是 Webhook 的鉴权密钥。**两个都配好后重启项目。**

### 第三步：GitHub 仓库挂 Webhook

1. 打开你的 GitHub 仓库 `Llhhy1/llhhy-blog` → **Settings → Webhooks → Add webhook**；
2. 填写：
   | 字段 | 值 |
   |---|---|
   | Payload URL | `https://你的域名/api/webhook/deploy?token=你在WH_DEPLOY_SECRET里填的字符串` |
   | Content type | `application/json` |
   | Secret | 留空（已用 URL token 鉴权） |
   | Which events | **Just the push event**（默认即可） |
3. 点 **Add webhook** 保存。

之后每次 `git push origin main`，GitHub 会 POST 到你的站点 → 后端校验 token → 自动执行 `deploy.sh` → 服务器自动更新。后台左下角版本号会变成最新版。

> **安全说明**：token 放在 URL 里会出现在 GitHub 后台，介意可改用 Header：把 Payload URL 设为 `https://你的域名/api/webhook/deploy`，并在 GitHub Webhook 的 **Secret** 字段填同一字符串（后端同时支持 Header `X-Deploy-Token` 校验，二者任一匹配即通过）。
> **防重放**：Webhook 请求必须在 Header 带 `X-Deploy-Time`（Unix 秒级时间戳），后端会校验与服务器当前时间差是否在 `WH_REPLAY_WINDOW`（默认 300 秒）内，超窗或缺失一律拒绝（HTTP 400）。GitHub 原生 Webhook 不带此头时，可改用**自建小脚本**（如 GitHub Actions 里 `curl -H "X-Deploy-Time: $(date +%s)" ...`）触发；或跳过该头后仍可用 URL token 校验（防重放会降级为仅鉴权——若需严格防重放请带该头）。
> **不会误伤数据**：`deploy.sh` 覆盖代码前会先备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/`，且解压时排除 `data/`，数据库永远不会被覆盖。

## 访问统计功能说明

- **统计入口**：前台导航「**统计**」→ `https://你的域名/stats`；后台仪表盘 →「📊 访问统计」。
- **统计内容**：累计/今日访问次数、访客区域排行（今日 + 累计 TOP10）、最受关注的文章（含回读人数）、常搜词汇 TOP10、24 小时访问时段分布。
- **统计口径**：前端每次打开/切换页面上报一次访问；打开文章记一次「阅读」（同一访客重复读会累加）；搜索关键词会被记录。
- **IP 属地识别**：服务器后台线程异步解析，国内源优先多源兜底（太平洋 pconline → ipwho.is → api.ip.sb → ipinfo.io，任一成功即返回），仅公网 IP 才查询、仅缓存成功结果（外部源恢复后历史空属地自动回填）；解析失败显示「未知」，不影响页面响应速度。
- **博客名称 / 浏览器便签**：后台 → 站点设置 → 可修改「博客名称」（前台顶部 Logo + 浏览器标签页标题）与「浏览器便签」（前台顶部一条可关闭的公告条，留空不显示）。

## 常见问题排查

| 现象 | 原因与解决 |
|---|---|
| 打开网站 502 | Python 项目没起来：到「网站 → Python项目」看是否「运行中」，点日志看报错（端口被占/依赖没装全最常见） |
| 页面刷新 404 | Nginx 少了 `try_files $uri $uri/ /index.html;`，检查第 4 步 |
| **后台能打开但完全没样式（全文本）** | **Nginx 少了 `location /static/` 反代**！`/static/admin.css` 返回 404。检查第 4 步，把 `/static/` 那段加上并重载配置 |
| 改了后台样式没变化 | admin.css 有缓存：重启 Python 项目（刷新版本戳）+ 浏览器强刷 Ctrl+F5 |
| 页面白屏 | 按 F12 → Network：`/api/site` 若 404/502，说明 `/api/` 反代没生效或 Python 项目没启动 |
| 登录后点「退出」没反应 | 旧版前端的 bug：前台退出已改为调用接口（不再用 /logout 链接），重新上传 `vue-frontend-dist.zip` 并强刷 |
| 后台登录提示密码错误 | 已设置过新密码；忘了就用下面的「重置密码」命令 |
| 上传图片 500 | `static/uploads/` 无写权限：文件管理右键该目录 → 权限 → 755 |
| 天气不显示 / 定位报错 | 已改双源（wttr.in 优先 + Open-Meteo 兜底）：定位被拒会自动回退默认城市；也可手动输城市名，无需 Key |
| 备案号怎么填 | 后台 → 站点设置 → 页脚备案号，填 `京ICP备xxxxxx号` 格式 |

## 忘记后台密码怎么办

宝塔左侧 **「终端」** → 粘贴执行（把 `新密码123` 换成你的）：

```bash
cd /www/wwwroot/myblog
# 找到项目的虚拟环境 python（宝塔 Python 项目详情里可看到，一般是 /www/wwwroot/myblog/venv/bin/python 或类似）
python -c "
from app import app
from models import db, User
from werkzeug.security import generate_password_hash
with app.app_context():
    u = User.query.filter_by(role='super').first()
    u.password_hash = generate_password_hash('新密码123')
    u.must_change_password = True
    db.session.commit()
    print('超级管理员密码已重置')
"
```

若 `python` 找不到，先用 `ls /www/wwwroot/myblog/venv/bin/python` 确认路径，把命令开头的 `python` 换成完整路径。执行后用 `新密码123` 登录（会再次要求设置新密码）。

---

## 云服务器安全组（如果端口访问不通）

本博客对外只需 **80（HTTP）/ 443（HTTPS）** 两个端口。若部署后域名打不开，请到你的云厂商控制台 → 云服务器 → 安全组 → 确认入方向放行了 `80` 和 `443`（能正常打开面板一般说明安全组是通的，通常无需改动）。

