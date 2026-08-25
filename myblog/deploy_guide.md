# 博客上线部署手册（宝塔面板 · Debian 13 示例）

> 本手册以 **宝塔面板 + Debian 13** 为例编写，各版本菜单名称、按钮位置大同小异，照着点即可，全程**不需要 SSH、不需要装 Node**。

## 0. 部署前准备

| 需要文件 | 在你自己电脑上 | 说明 |
|---|---|---|
| `myblog-backend.zip` | ✅ 已有 | 后端 + 管理后台，约 69KB |
| `vue-frontend-dist.zip` | ✅ 已有 | 前端构建产物，上传解压即网站根目录（本地构建目录为 `vue-frontend/dist_v311`，由 `package.py` 自动识别最新 `dist*` 目录打包） |

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
   > - **邮件群发（v2.4.0 起不需要在环境变量配）**：登录后台 → 「📧 邮件设置」直接填 SMTP 即可（见下方「邮件设置」章节）。若你更想用环境变量，也可配 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_SSL`（后台设置优先于环境变量）。
   >
   > **v3.1.6 安全加固新增可选配置**（不配用默认值即可）：
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

> 端口 `8686` 要与第 2 步 Python 项目里填的「监听端口」一致。`/api/`、`/admin`、`/static/` 三段都要有，缺一不可。

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
| 后台 | `https://你的域名/admin` | 用新账号登录进仪表盘；**左下角显示版本号**（如 v3.1.8，点它直达 GitHub Releases 比对最新版） |
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
- **改后端代码**：改 `myblog/` 下文件后，到「网站 → Python项目」对该项目点 **「重启」**。
- **改后台样式（admin.css / script.js）**：后台静态资源已绑定 `APP_VERSION` 版本戳，并对这两个文件加 `no-cache` 响应头——**发版后浏览器/微信自动拉新**，无需手动清缓存；若手动替换文件，重启项目 + 强刷（Ctrl+F5）即可。
- **改前端**：以后修改 `vue-frontend` 源码后**本地重新 `npm run build`**（不构建就上传等于没改），把新的 `index.html` + `assets/` 覆盖上传即可（**无需重启**，记得强刷浏览器）。
- **看后端日志**：「网站 → Python项目」→ 项目右侧 **「日志」**。
- **备份（重要）**：v3.3.0 起**推荐改用后台「💾 数据备份」页一键备份 + 宝塔定时任务 `backup.sh`**（见下方「v3.3.0 升级注意」），自动打包 `blog.db` + 上传目录并可选同步 OSS/SCP/WebDAV，无需手动记命令。以下手动方式仍可用作兜底：
  - `/www/wwwroot/myblog/data/blog.db`（全部数据：文章、评论、用户、设置、点赞、访问统计）
  - `/www/wwwroot/myblog/static/uploads/`（上传的图片）

> **备份自动化（v3.1.6 运维建议）**：建议在宝塔「计划任务」（或 crontab）加一条**每日凌晨**备份，一条命令搞定：
> ```bash
> # 宝塔「计划任务」→「Shell 脚本」，每天 03:00 执行：
> mkdir -p /www/backup/myblog && cp /www/wwwroot/myblog/data/blog.db /www/backup/myblog/blog_$(date +%F).db && cp -r /www/wwwroot/myblog/static/uploads /www/backup/myblog/uploads_$(date +%F)
> ```
> 保留最近 N 份自动清理（可选，如只留 14 天）：
> ```bash
> find /www/backup/myblog -name '*.db' -mtime +14 -delete
> ```

- **恢复**：把 `blog.db` 传回 `myblog/data/`，重启 Python 项目即可。

> **Nginx 真实 IP 转发（v3.1.6 运维建议）**：第 4 步反代配置已含 `X-Real-IP` / `X-Forwarded-For`，后端据此识别访客真实 IP（限流 / 访问统计 / 评论记录都依赖它）。**请确认** `location /api/`、`location /admin`、`location /static/` 三段都带全这两个头（上面配置模板已含，保持原样即可）。若站点再套了 CDN（如腾讯云 CDN / 又拍云），还要在 Nginx 里把 CDN 回源 IP 加入 `real_ip` 信任列表，否则统计/限流看到的是 CDN 节点 IP：
> ```nginx
> # 在 server{} 内（CDN 场景才需要）：
> set_real_ip_from 你的CDN节点IP段;
> real_ip_header X-Forwarded-For;
> ```
> **强制 HTTPS（强烈推荐）**：站点「设置 → SSL → 强制 HTTPS」打开后，所有 http 请求自动 301 到 https。配合 `COOKIE_SECURE=true` 环境变量，会话 Cookie 仅走 HTTPS，杜绝中间人窃取登录态。

> ⚠️ **数据库保护说明**：部署包 `myblog-backend.zip` **不包含 `data/` 目录**，解压覆盖不会动你服务器上已有的 `blog.db`（文章/评论/设置都安全保留）。
> 新增的表与列（统计表、评论嵌套字段、系列/公告/留言/订阅者表、is_read 列等）在项目**重启时自动迁移创建**，无需手动建表。

---

## 一键更新脚本（懒人版 · 推荐，连重启都自动）

> 仓库根目录的 **`update.sh`**：一条命令自动完成「下载最新 Release → 备份数据 → 覆盖代码 → **自动重启后端**」，全程无需手动操作。

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
> ⚠️ **严禁 HUP 热重载**：早期脚本用 `pkill -HUP` 优雅重载，但 HUP 只让 gunicorn master fork 新 worker、**master 不退出**。当版本改动涉及 import / 表结构（如 v3.0.0 新增 4 张表 + 模型 import）时，老 worker 仍在服务旧代码，表现为「更新完不重启 / 还是旧版」。v3.0.0 起已改为「真杀 + 真启动」。
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

## 后台一键在线更新（v2.5.0+ · 最懒人）

> 连终端都不用进：**登录后台 → 自动检测到新版本 → 点「立即更新」→ 后台静默完成 → 提示刷新**。全程无需 SSH、无需传文件。

**「检查更新」入口（v2.5.1+）**：点击后台左下角版本号旁的「检查更新」，**在后台直接判断**是否有新版本（不再跳转 GitHub）——有新版本弹出推荐更新条（含「立即更新」按钮）；已是新版提示「✅ 当前已是最新版本」；网络不通提示稍后再试。

**前置条件（只需一次）**：按上一节把 `update.sh` 上传到 `/www/wwwroot/myblog/update.sh`（并建议装好 supervisor 让重启自动）。之后一切在后台操作。

**使用流程：**

1. 超管登录后台，页面底部自动弹出提示条：
   > 「发现新版本 vX.Y.Z（当前 v2.4.0），是否立即在线更新？（将自动备份数据库并重启）」
2. 点 **「立即更新」** → 提示条变为「🔄 后台正在更新…（自动备份→覆盖→重启，请勿关闭本页）」
3. 后台自动完成：下载最新包 → **备份数据库和图片**（`data/backup/`）→ 覆盖代码 → 自动重启
4. 完成 → 提示条显示「✅ 更新完成，请刷新页面」→ 约 2.5 秒后自动刷新，后台左下角即为新版本号

**要点与安全：**

- 只有**超管/管理员**能看到和触发（普通用户触发返回 403）；
- 更新是**异步后台进程**，不阻塞后台其他操作；正在更新时再次触发会被拒绝（防重入）；
- 每次更新前自动备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/`，数据库永远不会被覆盖；
- 若更新中途失败（网络/包损坏），提示条会显示失败原因，数据保持原样（备份仍在）；
- 页面刷新或重新登录时，如果更新还在进行中，会自动进入轮询继续显示进度。


## 版本升级（老版本 → 新版本）

> 适用：服务器已部署过旧版本（如 v1.0.0），要升级到最新 Release。**只需覆盖代码 + 重启，不要删目录。**

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
   - 可用 `ps -ef | grep gunicorn` 看进程启动时间，确认是新进程。
5. **覆盖前端**：上传新版 `vue-frontend-dist.zip` 到 `/www/wwwroot/vue-frontend/` → 解压覆盖 `index.html` + `assets/`（**无需重启后端**）。
6. **验证**：浏览器**无痕窗口**打开（避免缓存）：
   - 后台左下角显示 `vX.Y.Z`，与 [GitHub Releases](https://github.com/Llhhy1/llhhy-blog/releases) 最新标签一致 → 后端升级成功；
   - 前台侧边栏出现「📬 邮件订阅」→ 前端升级成功。
7. **环境变量**：只覆盖文件 + 重启，环境变量原样保留，无需重填；**若误删 Python 项目重建，必须重填 `SECRET_KEY` / `ADMIN_PASSWORD`**（缺失拒绝启动）。改 `SECRET_KEY` 会让已登录用户需要重新登录，属正常现象。

---

### v2.7.0 升级注意（定时发布）

- **新增数据库字段**：`post` 表新增 `scheduled_at` 列（DATETIME，可空）。**无需手动 SQL**——重启后端时 `app.py` 的 `_migrate_post_table()` 会自动 `ALTER TABLE` 补列（旧库无缝升级）。
- **新增后台行为**：后端启动后会起一个守护线程，每 60 秒扫描"已设未来时间、到点但未发布"的文章，自动翻成已发布并触发推送/邮件群发。纯自动，无需配置。
- **后台写文章新增「定时发布」**：选一个未来时间保存即可；与「立即发布」互斥。仪表盘/我的文章状态列会显示"⏰ 定时(时间)"徽标。
- **升级步骤**：与其他版本一致——备份 `data/blog.db` + 覆盖后端 zip + **停止再启动** + 覆盖前端 zip + 无痕窗口验证左下角版本号 `v3.1.8`。

### v2.7.1 升级注意（文章置顶）

- **新增数据库字段**：`post` 表新增 `is_pinned` 列（BOOLEAN，默认 False）。**无需手动 SQL**——重启后端时 `_migrate_post_table()` 会自动补列（旧库无缝升级）。
- **后台写文章新增「📌 置顶」**：勾选后该文章在首页/分类/标签/归档/搜索/RSS 等列表优先展示，前台卡片显示 📌 标识；与「立即发布」「定时发布」独立并存。
- **升级步骤**：与其他版本一致——备份 `data/blog.db` + 覆盖后端 zip + **停止再启动** + 覆盖前端 zip + 无痕窗口验证左下角版本号 `v2.7.1`。

### v2.8.0 升级注意（七项功能整合）

- **新增数据库字段**：`post` 表新增 `seo_description`（TEXT）/ `seo_keywords`（VARCHAR(300)）两列。**无需手动 SQL**——重启后端时 `_migrate_post_table()` 会自动补列（旧库无缝升级）。
- **后台写文章新增「SEO 描述 / 关键词」**：独立编辑页面 meta，留空则自动回退摘要/标签；前台文章详情会自动注入 `description` 与 `keywords` 标签，利于搜索引擎收录。
- **后台文章列表新增筛选 + 分页**：仪表盘与「我的文章」支持关键词搜索、状态筛选（已发布/草稿/定时/置顶）、分类筛选，列表分页 12/页（文章多时不再全量加载）。
- **定时文章「立即发布」**：仪表盘/我的文章里处于"⏰ 定时"状态的文章，旁边多了「立即发布」按钮，点一下立即公开并清空定时（无需改时间重存）。
- **草稿自动保存**：写文章时浏览器每 5 秒本地缓存当前内容，误关页面后再进同一篇会自动恢复草稿（纯本地，不上传服务器）。
- **图片优化**：正文图片统一懒加载；后台上传的图片若体积较大且服务器装了 Pillow，会自动转 WebP 省流量（未装则保持原格式，零依赖降级）。
- **升级步骤**：与其他版本一致——备份 `data/blog.db` + 覆盖后端 zip + **停止再启动** + 覆盖前端 zip + 无痕窗口验证左下角版本号 `v2.8.0`。

### v3.0.0 升级注意（14 项功能整合）

- **新增数据库字段**：`post` 表新增 7 列——`word_count`、`reading_minutes`、`reward_enabled`、`reward_qr`、`is_private`、`in_trash`、`deleted_at`。**无需手动 SQL**——重启后端时 `_migrate_post_table()` 会自动补列（旧库无缝升级）。
- **新增 4 张表**：`audit_log`（操作日志）、`recycle_bin`（回收站快照）、`link_application`（友链申请）、`post_history`（文章版本历史）。**无需手动 SQL**——重启后端时 `_migrate_new_tables_v3()` 会自动建表（旧库无缝升级）。
- **新增后台菜单（超管）**：后台侧边栏新增「📋 操作日志」「♻️ 回收站」「🔗 友链申请」入口；普通管理员可见回收站与友链申请，操作日志仅超管可见。
- **新增站点设置（后台「⚙️ 系统设置」）**：
  - `comment_spam_keywords`：垃圾评论关键词，逗号分隔，评论提交命中任一即被拒收（防御垃圾评论）。
  - `site_lang`：前台默认语言，`zh`（中文，默认）或 `en`（英文），访客仍可手动切换。
  - `reward_qr_default`：文章打赏默认收款码图片 URL，超管未单独设置某篇打赏码时使用。
- **新增后台行为**：
  - 文章删除改为**软删除**（进回收站，可还原/彻底清除），不再是物理删除；
  - 文章保存自动留存历史版本（每篇上限 20 版），编辑页可查看版本历史并回滚；
  - 评论列表支持批量勾选通过/删除；
  - 统计页新增近 30 天 PV/UV 趋势折线图。
- **前台新增页面/入口**：热门标签云（`/tags/hot`）、语言切换按钮（导航栏「中 / EN」）、文章详情页字数/阅读时长与打赏框（打赏仅超管开启的文章显示）、搜索结果分页 + 命中词高亮、系列详情页编号目录。
- **升级步骤**：与其他版本一致——**务必先备份 `data/blog.db` + `static/uploads/`** → 覆盖后端 zip → **停止再启动**（仅重启可能不生效）→ 覆盖前端 zip → 无痕窗口验证左下角版本号 `v3.0.0`。

> ⚠️ v3.0.0 首次启动会自动建表 + 补列，若数据库较大请预留启动时间；建表/补列失败会在启动日志打印提示但**不阻断启动**（下次启动重试）。

### v3.1.6 升级注意（12 项安全加固）

- **新增数据库字段**：`user` 表新增 `session_version` 列（INTEGER，默认 0）。**无需手动 SQL**——重启后端时 `_migrate_user_table()` 自动补列（旧库无缝升级）。
- **升级后需重新登录**：本轮启用了「改密码/被踢下线后旧会话失效」，老会话在升级前存在的 cookie 会因会话版本机制被清理，**所有人需重新登录一次**（正常现象）。
- **CSRF 双重防护（v3.1.6+）**：所有 POST/PUT/DELETE/PATCH 请求（除 webhook、验证码接口）必须携带会话绑定的 CSRF Token。**前端 Vue 已自动处理**（apiPost 自动先取 /api/csrf）；服务端渲染表单（后台）已自动注入隐藏域——**无需手动改动**。第三方直接用 POST 调 API 且不带 token 的会被 403 拒绝（这是预期安全行为）。
- **验证码（默认开启）**：注册、评论、留言新增图形验证码。服务器未安装 Pillow 时自动降级关闭（不影响使用）。
- **登录防枚举**：登录失败统一文案 + 默认延迟 1 秒（`LOGIN_DELAY_SECONDS` 可调）。暴力破解难度大幅提升。
- **升级步骤**：与其他版本一致——**务必先备份 `data/blog.db` + `static/uploads/`** → 覆盖后端 zip → **停止再启动**（仅重启可能不生效）→ 覆盖前端 zip → 无痕窗口验证左下角版本号 `v3.1.8`。

### v3.1.7 升级注意（CSRF 隐藏域乱码修复）

- **修的什么**：v3.1.6 起 `csrf_input()` 返回普通字符串的 `<input>` 隐藏域，被 Jinja2 autoescape 转义成 `&lt;input ...&gt;` **源码文本**，导致登录后台后页面（尤其带表单的后台页）显示乱码。
- **修复方式**：`csrf_input()` 改用 `markupsafe.Markup` 包装，隐藏域以原生 HTML 渲染。`markupsafe` 是 Flask 自带依赖，**无需安装新包**。
- **影响范围**：全后端模板一处修复全局生效（后台 24 个表单模板 + 前台登录/注册页 + base.html 退出按钮），前端无需改动。
- **升级步骤**：与常规一致——备份 `data/blog.db` → 覆盖后端 zip → 停止再启动 → 验证左下角版本号 `v3.1.7`。若服务器当前是 v3.1.6 且不想全量升级，也可手动改 `utils.py` 的 `csrf_input()` 返回 `Markup(...)` 后重启，效果等价。


### v3.1.8 升级注意（后台退出按钮 405 修复）

- **修的什么**：后台「退出登录」按钮点击后报 **Method Not Allowed（405）**。根因：v3.1.6 起退出表单改为 POST + CSRF 隐藏域，但 `/admin/logout` 路由仍只支持 GET。
- **修复**：路由改为 `methods=["GET", "POST"]`。POST 带 CSRF Token 正常退出，GET 兼容旧链接。
- **升级步骤**：与常规一致——备份 `data/blog.db` → 覆盖后端 zip → 停止再启动 → 验证左下角版本号 `v3.1.8`。

### v3.2.0 升级注意（后台验证码独立设置页 + Pillow 修复）

- **修的什么**：用户反馈「验证码功能用不了」。根因：`requirements.txt` 此前漏写 Pillow → 服务器未装图像库时验证码整块降级停用（不出图也不校验）。同时验证码此前只能靠环境变量开关，后台无单独配置入口。
- **新增**：后台「🛡️ 验证码设置」（`/admin/captcha-settings`，超管）可单独配置全局开关、长度、干扰强度、排除易混字符，以及**注册 / 评论 / 留言各场景独立开关**，存 `Setting` 表。
- **依赖修复**：`requirements.txt` 新增 `Pillow>=10.0.0`。**升级后必须 `pip install Pillow` 并停止再启动**，否则验证码图片仍无法生成（设置页会实时提示 Pillow 是否可用）。
- **升级步骤**：备份 `data/blog.db` → 覆盖后端 zip → **停止再启动**（仅重启可能不生效）→ 覆盖前端 zip（`dist_v316`）→ 无痕窗口验证左下角版本号 `v3.2.0` → 后台「验证码设置」确认开关与 Pillow 状态正常。

### v3.3.0 升级注意（数据备份与异地容灾）

- **新增**：内置自动备份模块 `myblog/backup.py` + 后台「💾 数据备份」页（`/admin/backup`，超管专属）+ 宝塔定时任务脚本 `myblog/backup.sh`（已随包分发）。
- **升级后配置（可选但强烈建议）**：
  - 后台「💾 数据备份」页可一键「立即备份」、查看备份列表、下载、恢复（恢复需二次确认 + 超管 + CSRF + 审计）。
  - 配置宝塔「计划任务 → Shell 脚本」，**每天凌晨 4 点**执行：`bash /www/wwwroot/myblog/backup.sh`。脚本会自动调用 `python backup.py run`（本地 + 已启用的远程目的地）。
  - 如需异地容灾，**v3.4.0 起推荐直接在后台「⚙️ 备份配置」页填写**（超管专属，保存即生效、无需 SSH）：目的地/保留天数/密钥全在后台改。密钥（OSS SecretKey / WebDAV 密码 / SCP 私钥路径）用 **SECRET_KEY 派生的 Fernet 密钥加密存储**，页面只回显掩码，**绝不落明文**。
  - **老环境变量仍兼容**（密钥环境变量优先，非密钥后台优先）：若已在宝塔 Python 项目「环境变量」配过 `BACKUP_*`，无需迁移，自动生效。参数对照：
    - **对象存储 OSS/COS/S3**：`BACKUP_OSS_BUCKET` / `BACKUP_OSS_REGION` / `BACKUP_OSS_ENDPOINT` / `BACKUP_OSS_KEY` / `BACKUP_OSS_SECRET`（服务端需 `pip install boto3`）。
    - **备用机 SCP**：`BACKUP_SCP_HOST`（`user@host`）/ `BACKUP_SCP_DIR`（默认 `~/blog_backups`）/ `BACKUP_SCP_PORT`（默认 22）/ `BACKUP_SCP_KEY`（私钥路径）。
    - **云盘 WebDAV**：`BACKUP_WEBDAV_URL` / `BACKUP_WEBDAV_USER` / `BACKUP_WEBDAV_PASS`（服务器需系统 `curl`）。
    - 本地保留天数：`BACKUP_RETENTION_DAYS`（默认 14）；本地目录：`BACKUP_DIR`（默认项目上级 `backups/`）。
- **恢复注意事项（高危）**：后台「恢复」会把 `blog.db` 与 `static/uploads/` 覆盖回备份时点；SQLite 在站点运行时被覆盖有风险，**恢复后务必到宝塔「停止」再「启动」站点**使数据库生效（页面会给出「恢复前快照」文件名，异常可回退）。恢复前系统自动打一份快照并写审计日志。
- **升级步骤**：备份 `data/blog.db` → 覆盖后端 zip → **停止再启动**（仅重启可能不生效）→ 覆盖前端 zip（本轮前端无变动，可沿用 `dist_v317`）→ 无痕窗口验证左下角版本号 `v3.3.0`。

### v3.3.1 升级注意（后台「立即更新」CSRF 修复）

- **修复**：后台「系统设置 → 立即更新」此前用 `fetch()` POST `/api/version/update` 时漏带 `X-CSRF-Token` 请求头，点击报「CSRF 校验失败，请刷新页面后重试」；本轮在模板 `templates/admin/base.html` 请求头补 token（单行改动，CSRF 防护完整保留）。
- **升级步骤**：仅后端变更——备份 `data/blog.db` → 覆盖后端 zip（`myblog-backend.zip`）→ **停止再启动**（仅重启可能不生效）→ 无痕窗口验证左下角版本号 `v3.3.1`。**前端无需更新**（本轮无前端改动）。
- 若升级前正好卡在该报错上：升级后回到后台「系统设置 → 立即更新」重新点击即可正常触发；如需立即验证，也可先手动在服务器把 `base.html` 该 fetch 请求头补上再重启，效果等价。

### v3.4.0 升级注意（备份配置后台化 + 立即备份 500 修复）

- **500 修复**：后台「💾 数据备份 → 立即备份一次」此前点击报 500 —— 根因是 `admin.py` backup 路由 4 处把审计函数名误写为未定义的 `add_audit`（正确为 `log_audit`），备份文件实际已生成但写审计日志抛 `NameError`。升级后立即备份恢复正常（返回 200 + 成功提示 + 审计日志）。
- **备份配置后台化**：新增后台「⚙️ 备份配置」页（`/admin/backup-settings`，超管专属）——本地目录 / 保留天数 / OSS / SCP / WebDAV 目的地与密钥全部后台填写保存即生效。**密钥（OSS SecretKey / WebDAV 密码 / SCP 私钥路径）用 SECRET_KEY 派生的 Fernet 密钥加密存储，页面只回显掩码，绝不落明文**。
- **⚠️ 必须新增依赖**：`requirements.txt` 新增 `cryptography>=41.0.0`。**升级后必须 `pip install cryptography` 并「停止→启动」站点**，后台备份配置页才可加密保存/解密；不装则旧备份/恢复功能不降级，仅配置页加密保存会报错。
- **老环境变量无需迁移**：密钥字段仍环境变量优先、后台加密值兜底；非密钥字段后台优先、环境变量兜底。已在宝塔配过 `BACKUP_*` 的继续生效。
- **升级步骤**：备份 `data/blog.db` → 覆盖后端 zip → **停止再启动**（仅重启可能不生效）→ `pip install cryptography`（宝塔 Python 项目「依赖安装」勾选自动装，或命令行手动装）→ 再停止启动一次 → 无痕窗口验证左下角版本号 `v3.4.0` → 后台「⚙️ 备份配置」页确认/配置远程目的地。**前端无需更新**（复用 dist_v317）。

### v3.4.1 升级注意（前台视觉升级 + 汉堡菜单深色修复 · 纯前端）

- **改动范围**：仅 `vue-frontend/`（Vue SPA）视觉升级 + 深色汉堡菜单修复；**后端零改动**。
- **修复**：深色模式下前台汉堡抽屉文字看不清（根因 `vue-frontend/src/store.js#applyThemeVars` 内联 style 覆盖暗色导航变量；`App.vue#applyTheme` + `global.css` 双保险修复）。
- **升级步骤（仅前端）**：
  1. 先备份（可选）：`cp -r /www/wwwroot/vue-frontend /www/wwwroot/vue-frontend.bak`；
  2. 下载 v3.4.1 Release 中的 `vue-frontend-dist.zip` 上传服务器（或后台「一键在线更新」自动完成），覆盖解压到 `/www/wwwroot/vue-frontend`（zip 自带一层 `vue-frontend/` 避免嵌套）；
  3. **前后台均无需「停止→启动」**（后端零改动）；若浏览器/CDN 缓存旧静态资源，建议等几分钟或清缓存后无痕窗口验证。
- **验证**：前台首页顶部出现渐变主题色横幅、文章卡 hover 上浮；手机/窄屏（≤1004px）打开汉堡菜单，切深色后菜单文字清晰（浅色文字）。
- **版本显示**：后台左下角版本号仍为 `v3.4.0`（后端未变）；确认前端已更新直接看前台新样式即可；Release 标签为 `v3.4.1` 用于区分。

### v3.4.2 升级注意（一键更新脚本双源互证校验修复）

- **改了啥**：`update.sh` / `deploy.sh` 里的 zip 注释内嵌哈希校验（v3.1.6 引入的「双源互证」②）此前写错——把「内容区哈希 == 注释内嵌哈希」误写成「内容区哈希 == 注释内嵌哈希 == 整文件哈希」三向链式比较（恒为假），导致 python3 校验段**永远失败**。
- **故障现象**：后台「立即更新」/ 宝塔终端跑 `bash /www/wwwroot/myblog/update.sh`，走到「下载 sha256.txt」后 **静默退出(码1)**，日志没有 ❌ 行、只显示「更新未完全成功：脚本异常退出(码1)」。因 python3 命令替换返回值非 0 被 `set -e` 吞掉，**下载已成功但更新未执行**。
- **修复**：改为「本地剥离 zip 注释后重算内容区哈希 == 注释内嵌 SHA256」两源互证（正确的双源互证）；同时命令替换加 `|| true` 兜底，python3 异常时降级为跳过该层、不再炸脚本。
- **⚠️ 必须更新脚本**：若你的服务器用的是 v3.4.1（含）之前的 `update.sh` / `deploy.sh`，**请先下载 Release v3.4.2 的 `deploy_scripts_v342fix.zip`，覆盖 `/www/wwwroot/myblog/update.sh`（及 deploy.sh 若有）**，再跑一键更新；否则新 Release 包同样会被旧脚本误判「注释不一致」而终止。
- **验证**：覆盖后再跑 `bash /www/wwwroot/myblog/update.sh`，应看到 `✅ xxx 的 zip 注释内嵌哈希一致（双源互证通过）`，并继续完成备份/覆盖/重启。
- **⚠️ 已知缺陷（v3.4.3 已修复，见下节）**：`deploy_scripts_v342fix.zip` 里的脚本虽然修好了三向链式比较，但校验段仍用 `sys.exit(0/1)` 传结果——bash 命令替换 `$(...)` 捕获的是 **stdout 不是退出码**，`sys.exit()` 不产生任何输出 → 结果恒为空 → 脚本会**把一切正常包误报为「zip 注释内嵌 SHA256 与包内容不一致」并终止更新**。**该包已废弃，请勿再使用。**

### v3.4.3 升级注意（一键更新脚本输出机制修复 · 必须换新脚本包）

- **改了啥**：`update.sh` / `deploy.sh` 的 zip 注释内嵌哈希校验段（「双源互证」②）此前用 `sys.exit(0/1)` 传递校验结果——但 bash **命令替换只捕获 stdout**，`sys.exit()` 无输出 → 即便比较逻辑已正确，正常包也会得到空结果 → 误报「注释不一致」并终止更新（v3.4.2 的 `deploy_scripts_v342fix.zip` 正是此缺陷，**已废弃**）。
- **修复**：Python 校验段改为 `print('OK'/'BAD'/'NO'/'ERR')` + `sys.exit(0)`，bash 侧用 `case "$comment_ok" in OK|BAD|NO|ERR|*)` 按**输出内容**判断：OK → 双源互证通过；BAD → 篡改终止；NO/ERR/无输出 → 降级为仅靠 sha256.txt 比对（不再误杀正常包）。
- **⚠️ 必须换新脚本包**：**`deploy_scripts_v342fix.zip` 已废弃（对正常包必误报，请不要再用）**。请下载 Release v3.4.3 的 **`deploy_scripts_v343fix.zip`**，覆盖 `/www/wwwroot/myblog/update.sh`（及 deploy.sh 若有）后，再跑一键更新。
- **验证**：覆盖后跑 `bash /www/wwwroot/myblog/update.sh` 应看到 `✅ xxx 的 zip 注释内嵌哈希一致（双源互证通过）`，并继续完成备份/覆盖/重启；后台左下角版本号显示 `v3.4.3`。
- **顺带修正**：后台「立即更新」此前可能因脚本校验误报而失败，本次一并恢复可用；改动仅脚本，后端业务代码无变化。

### v3.4.4 升级注意（解压目录唯一化 · 残留目录免疫 · 必须换新脚本包）

- **故障现象**：v3.4.3 更新走到「④ 覆盖后端代码」报 `mkdir: cannot create directory 'backend_extract': File exists` 后退出——`/tmp/llhhy_update/` 下残留了历史失败更新的 `backend_extract` 目录。
- **根因**：脚本解压使用**固定目录名** `backend_extract` / `frontend_extract`；删除残留失败被 `|| true` 吞掉（不报错），随后 `mkdir` 无兜底 + 脚本 `set -e` → 静默终止。**任何一次更新中途失败都会在 /tmp 留下半解压目录，下次更新即炸**（v3.4.1 静默退出 / v3.4.2 误报失败都可能在服务器上留过该残留）。
- **修复**：解压目录改为**唯一时间戳名** `backend_extract_$TS` / `frontend_extract_$TS`——新目录名每次唯一，残留目录存在也**不影响本次更新**；脚本启动时尽力清理旧残留（`rm -rf ... || true`，范围锁定在 $WORK 内）。
- **⚠️ 必须换新脚本包**：**服务器 `update.sh` / `deploy.sh` 须覆盖 Release v3.4.4 的 `deploy_scripts_v344fix.zip`**（v3.4.3 及更早脚本在 /tmp 有残留时仍会炸）。已卡住的服务器：可先手动 `rm -rf /tmp/llhhy_update /tmp/llhhy_deploy`，或**直接换新脚本后重跑**（新脚本不依赖清理残留）。
- **验证**：覆盖后跑 `bash /www/wwwroot/myblog/update.sh`，应完整走完 ①下载校验 ✅ → ②备份 → ③覆盖 → ④b 依赖 → ⑤前端 → ⑥重启；后台左下角版本号显示 `v3.4.4`。
- **顺带说明**：后端业务代码无变化（仅 config.py 版本号 + 运维脚本 + 文档）。

### v3.4.5 升级注意（覆盖段修复 + 评论500/统计403 修复 · 必须换新脚本包）

- **修了什么**：① 一键更新覆盖段「假成功」修复 + 覆盖后版本号硬校验（R25）——此前多轮更新后端根本没被覆盖（后台长期停在 v3.4.0）；② **评论提交 500**——`utils.py` 的 `notify_mentioned` 函数体被误贴进 `csrf_input` 的 `return` 之后成了死代码，请求时 `ImportError`（v3.1.7 起潜伏，@通知也从未生效），已恢复为独立函数；③ **统计埋点 403**——`/api/stats/read|visit|search` 加入 CSRF 豁免，恢复访问统计记录并消除控制台报错。
- **⚠️ 必须换新脚本包**：**服务器 `update.sh` / `deploy.sh` 必须覆盖 Release v3.4.5 的 `deploy_scripts_v345fix.zip`**（v3.4.4 及更早脚本仍会「假成功」不覆盖后端，评论 500 / stats 403 依旧）。**务必先手动覆盖脚本再跑一键更新。**
- **验证**：覆盖后跑 `bash /www/wwwroot/myblog/update.sh`，应完整走完 ①下载校验 ✅ → ②备份 → ③覆盖（含版本号校验通过）→ ④b 依赖 → ⑤前端 → ⑥重启；后台左下角版本号显示 `v3.4.5`；提交评论不再 500、控制台无 `stats/read` 403。
- **顺带说明**：后端业务代码本轮修复 `utils.py`（恢复 `notify_mentioned`）+ `app.py`（埋点 CSRF 豁免），与运维脚本一并随 Release 发布。

### v3.4.6 升级注意（CSRF 多 worker 下 403「抽风」修复 + 一键更新自动重启加固 · 必须换新脚本包）

- **后端修复（R28 · CSRF token 跨 worker 轮换导致 403「抽风」）**：登录用户发评论、后台批量审核 / 删除评论均间歇性 `403 (Forbidden)`（登录账号评论「总是抽风」）。根因：gunicorn `-w 3` 下旧 `generate_csrf_token()` 用**进程级 `_CSRF_CACHE`** 判断 token 是否「新鲜」，各 worker 缓存独立 → 落到不同 worker 会重新生成并**覆盖 session token** → 前端缓存 token 失效 → 后续 POST 全 403（看哪个 worker 接手，时好时坏）。前端 `ensureCsrfToken()` 仅在 token 为空时拉一次并永久缓存，403 时无自愈。修复：移除 `_CSRF_CACHE`，改为**签名校验复用**（HMAC(SECRET_KEY, `"csrf:"`+raw)，天然防伪造 / 防跨服务复用），token 在会话内稳定，不再随 worker 切换而轮换；仅 token 缺失或签名失效才重建。验证：双 worker 共享 session 模拟复用成功、`check_csrf_token` 对合法 / 篡改 / 无格式 / 空判断均正确（ALL PASS）。
- **运维脚本加固（R27 · 一键更新自动重启）**：v3.4.5 一键更新跑通后，后端代码已被正确覆盖，但**进程不会真正重载**——还得去宝塔「Python项目 → 停止 → 启动」手动重启一次。根因是旧 `stop_backend` 只 TERM 了 master、没杀干净 worker，残留进程占着端口 → 新 gunicorn 因「Address already in use」起不来，自动重启段形同虚设。本轮加固（R27+R28 审计通过，运维脚本变更 + `utils.py` CSRF 修复）：
  - `stop_backend`：TERM master 后 `pkill -TERM -f "gunicorn.*$APP_DIR"` 杀光整个项目所有 gunicorn（含 worker），超时再 KILL；并新增**端口释放检查**（探测 `gunicorn_conf.py` 的 `bind` 端口是否真的空了）。
  - `start_backend`：改用 `setsid` + `< /dev/null` **彻底脱离脚本会话**（避免新进程被脚本退出带走）；补全 venv 的 `PATH`；启动后扫 `gunicorn.log` 是否有端口占用 / 权限 / 导入失败等致命错误，有则打印日志末尾辅助定位。
  - 修正 `RESTART_CMD` 注释：宝塔 `bt` 命令行是交互式菜单、**不支持 `bt stop 项目名`**，旧范例 `bt stop myblog && bt start myblog` 是错误的（已删除）。
- **⚠️ 必须换新脚本包**：**服务器 `update.sh` / `deploy.sh` 必须覆盖 Release v3.4.6 的 `deploy_scripts_v346fix.zip`**（v3.4.5 及更早脚本的自动重启段仍是旧逻辑，覆盖后仍需手动重启）。**务必先手动覆盖脚本再跑一键更新。**
- **验证**：覆盖后跑 `bash /www/wwwroot/myblog/update.sh`，走到 ⑥ 重启时应看到「后端进程已确认停止，端口已释放」→「后端进程已确认启动（gunicorn 运行中，日志无致命错误）」；**不再需要去宝塔手动重启**；登录账号发评论、后台批量审核 / 删除评论**不再 403**；后台左下角版本号显示 `v3.4.6`。若仍失败，脚本会把 `gunicorn.log` 末尾直接打印出来，把那段贴给我即可定位。

### v3.4.7 升级注意（评论者 IP 定位恢复 + 后台筛选表单美化 · 必须换新脚本包）

- **修了什么①「评论者 IP 定位没了」**：用户反馈评论区「评论的人的 IP 定位」不显示了。根因（R29 审计确认）：原 `stats.py` 的 IP 属地解析只依赖 `api.vore.top`（已超时挂掉）与 `ip-api.com`（已 403 被封）两个外部源，二者全挂后所有评论/访问的 `region` 恒为空 → 前台 `📍 {{ c.region }}` 不渲染，看起来像「定位组件没了」（实为数据源死亡，非前端组件缺失）。本轮修复（R29 七维审计 0 Blocker）：
  - IP 属地改为**国内源优先 + 国际源依次兜底**：太平洋 pconline（CN 中文）→ ipwho.is → api.ip.sb → ipinfo.io，任一成功即返回，全部失败才回空。
  - 修复旧逻辑「解析失败(空)也被永久缓存、永不重试」的坑：改为**仅缓存成功结果**，外部源恢复后下次访问即自动回填（含历史空属地评论/访问）。
  - 严格审计加固：新增 `_is_safe_public_ip()` 仅公网 IP 才查外部（排除私网/环回/保留/CGNAT `100.64/10`），杜绝 XFF 伪造污染与内网 IP 外发；`short_region` 补英文/ISO2→中文归一（根治 `UnitedStatesCalifornia` 脏数据、ipinfo 的 `CN` 码误判）；`_RECENT_FAIL` 加 `_FAIL_MAX=5000` 容量护栏防内存无界增长。
- **修了什么②后台筛选表单美化**：`我的文章`/`仪表盘` 的文章筛选表单卡片化（圆角容器 + 🔍 搜索图标 + 统一 38px 控件 + accent 焦点环 + 主/ghost 按钮层级），并适配深色模式；样式抽进 `admin.css` 的 `.filter-form`，去掉内联 style。
- **⚠️ 必须换新脚本包**：**服务器 `update.sh` / `deploy.sh` 必须覆盖 Release v3.4.7 的 `deploy_scripts_v347fix.zip`**（沿用 v3.4.6 自动重启加固；v3.4.6 及更早脚本的自动重启段仍是旧逻辑）。**务必先手动覆盖脚本再跑一键更新。**
- **验证**：覆盖后跑 `bash /www/wwwroot/myblog/update.sh` 走完应无需手动重启；后台左下角版本号显示 `v3.4.7`；**新评论 / 历史评论重新加载列表后**应恢复显示 `📍 省·市`（外部源恢复后陆续回填，可能需访问/刷新触发几次）；筛选表单为卡片化带 🔍 图标。若属地仍未显示，多为外部 IP 库偶发超时，稍后重试即可（已加节流，不会狂打）。

### v3.4.8 升级注意（全量安全审计加固 R30 · 本轮可直接跑一键更新，有问题再换脚本包）

- **本轮改动**：**纯后端安全加固**（3 Blocker + 5 建议全部修复，无部署脚本改动，无前端改动）。详见 `README.md` v3.4.8 条目 + `SECURITY_AUDIT.md` 第四十轮 R30。
- **🅰️ 升级顺序（本轮调整）**：R30 **未改动 `update.sh` / `deploy.sh`**——服务器**直接跑一键更新**即可（沿用已在服的 v3.4.7 脚本，含 v3.4.6 自动重启加固）。**若更新过程报错，再覆盖 Release v3.4.8 的 `deploy_scripts_v348fix.zip` 后重跑**（正常情况不需要换脚本包）。
- **验证清单**：
  1. 更新后后台左下角版本号显示 `v3.4.8`；
  2. 后台「用户管理」删除用户的确认弹窗、订阅者删除弹窗、备份恢复弹窗、审计日志清理弹窗均正常显示（`|tojson` 渲染不破坏文案）；
  3. 未登录访问 `/api/version/status` 返回 403（鉴权收窄生效）；普通管理员访问 `/api/version/update` 返回 403；
  4. 前台正常评论/搜索/访问不受影响（埋点限流只拦脚本刷量）；连续错误登录 10 次后出现「尝试过于频繁」429；
  5. 评论/访问的 IP 属地仍正常显示（v3.4.7 逻辑未变）。

### v3.4.9 升级注意（评论 IP 属地 GBK 解码乱码修复 · R31 审计通过）

- **修的什么**：用户反馈前台评论 IP 定位显示乱码（如「㽭ʡ」、省份变乱码、城市为空）。根因：`stats.py` 的 `_http_get_json` 用 `decode("utf-8","ignore")` 静默吞字符——太平洋 IP 库（GBK 编码）中文被吞成乱码，且因 `ignore` 永不抛错，设计中的「GBK 兜底」分支永远走不到，乱码被写入 `IpRegion` 缓存并展示。
- **修复**：改为**逐编码严格解码**（utf-8 → gbk，任一 JSON 非法则试下一编码，双失败才抛错交多源兜底）；并新增 `_looks_corrupted()` 历史脏缓存自愈——缓存命中先判脏，**脏则忽略缓存走在线重查并覆盖旧值**（新访问即自动自愈，无需手动清库）。
- **验证**：`py_compile` 通过；`smoke_gbk.py` 15/15 ALL GREEN（GBK 全链路 `广东广州`/`浙江杭州`、脏缓存自愈、异步重查）。R31 聚焦审计 0 Blocker。
- **🅰️ 升级顺序**：R31 **未改动部署脚本**（沿用 v3.4.8 已在服脚本），服务器**直接跑一键更新**即可；历史脏属地将在新访问触发重查后自动覆盖（无需手动清库）。详见 `README.md` v3.4.9 条目 + `SECURITY_AUDIT.md` 第四十一轮 R31。

### v3.5.0 升级注意（自定义链接后缀 + 5 项功能/修复 + 抽屉毛玻璃美化 · R32 审计通过）

- **① 自定义链接后缀（slug）**：编辑/新建文章新增「链接后缀」字段，可手动填中文/英文/数字/下划线/连字符生成短链接（如 `/post/我的笔记`）；留空按标题自动生成。后端 `clean_slug()` 清洗并查重（冲突自动 `-2/-3`），绝不写出空 slug。
- **② 前台模糊搜索修复**：旧守卫 `if ids is not None` 把 FTS5 空结果 `[]` 误判为「有结果」→ 永不走 LIKE 兜底、搜索恒「无结果」。改为 `if ids:`（`[]`/`None` 均兜底），无异常路径。
- **③ 分类/标签页前台无文章修复**：后端下发 `{items, name}`，前端 `CategoryView`/`TagView` 原读 `data.posts`（恒 undefined）。改为读 `data.items`，`name` 缺失回退 slug。
- **④ 后台评论单独删除 405 修复**：行内按钮原嵌在批量表单的嵌套 `<form>` 里被浏览器丢弃 → 单删 405。改为行内按钮用 `formaction` 共享外层 `batch-form` 的 CSRF token（单 POST 表单）。
- **⑤ 英文窄屏菜单/LOGO 纵向错位修复**：抽屉断点 `1004px` → `1100px`，`.logo` 加 `flex-shrink:0`，英文导航不再换行顶乱布局。
- **⑥ 前台抽屉毛玻璃圆角美化**：汉堡抽屉改为浮动毛玻璃卡片（`backdrop-filter:blur(20px) saturate(180%)` + 20px 圆角 + 阴影），深色模式同步适配——**纯前端改动，覆盖 `vue-frontend-dist.zip` 即可**。
- **运维脚本**：新增 `tools/reset_stats.py`（标准库、运维手动）——清空四统计表，执行前 `post` 表预检防误伤他库、自动时间戳备份、默认 `YES` 二次确认；**不入库、不取密钥、不进 web 路由**。
- **验证**：`py_compile` 全模块通过；前端构建 `_vite_build15` 成功、含毛玻璃 CSS。R32 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十二轮 R32）。
- **⚠️ 升级顺序**：R32 **未改动部署脚本**（沿用 v3.4.9 已在服脚本），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

### v3.5.1 升级注意（英文桌面端菜单换行修复 + 深色抽屉毛玻璃回归修复 · R33 审计通过）

- **① 英文桌面端顶部菜单换行修复**：v3.5.0 漏给顶部 inline 导航 `.site-header nav` 加 `nowrap`、且抽屉断点只到 `1100px` → 常见桌面宽（约 1280px）切英文时顶部菜单换行成两行、LOGO 顶乱。本轮给 `.site-header nav` 加 `flex-wrap:nowrap;min-width:0`、`.site-header nav a` 加 `white-space:nowrap`（首子项左间距归零），抽屉断点 `1100px`→`1280px`，顶部 inline 导航全宽度保持单行。
- **② 深色模式抽屉毛玻璃回归修复**：删除遗留的 `[data-theme="dark"] .drawer{background:#1d2025;border-color:#2a2e35}` 不透明覆盖（压死 v3.5.0 毛玻璃）；深色抽屉改由毛玻璃基样式（alpha 背景 + `backdrop-filter` + 浅描边）渲染，仅保留文字色兜底——**纯前端改动，覆盖 `vue-frontend-dist.zip` 即可**。
- **验证**：`compileall myblog` 无语法错误；前端构建 `_vite_build15` 成功、含 `1280px` 断点 + `nowrap` + `backdrop-filter`。R33 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十三轮 R33）。
- **⚠️ 升级顺序**：R33 **纯前端改动**（外加 `APP_VERSION` 升版本号），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

### v3.5.2 升级注意（链接后缀全局模板 + 预制可选/自定义 · R34 审计通过）

- **改的什么**：链接后缀从「仅单篇手动填」升级为「后台全局模板 + 单篇可覆盖」双轨。后台新增「🔗 链接后缀规则」：选预制模板（标题 / 标题-日期 / post-ID / 日期-标题 / 分类-标题）或自定义（支持 `{slug}{id}{date}{category}` 占位符），新建/编辑文章自动套用；单篇仍可在编辑页手动填后缀硬覆盖。
- **零破坏性**：`slug_mode` 默认 `title` = 旧行为（按标题生成）；编辑文章若标题未变则保留旧后缀（不破坏已有 URL）；单篇手动填了后缀则硬覆盖模板。
- **占位符**：`{slug}`=标题短名、`{id}`=文章 ID、`{date}`=创建日期 `YYYYMMDD`、`{category}`=分类 slug；未知占位符自动清空；冲突自动 `-2/-3` 查重，绝不写空 slug。
- **后台实时预览**：设置页输入标题/选模板即时显示预览 slug（`textContent` 输出，XSS 安全）。
- **验证**：`compileall myblog` 通过；DB 功能测试 6 模式 + 查重通过。R34 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十四轮 R34）。
- **⚠️ 升级顺序**：R34 **改了后端**，服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

## 邮件设置（新文章通知订阅者 · 后台配置）

> 从 v2.4.0 起，邮件群发配置**不需要再填环境变量**，直接在后台操作（更便捷）。

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

## 自动部署（GitHub push → 服务器自动更新）

> 想让「GitHub 推送代码 = 服务器自动更新」，只需三步。**可选功能，不配不影响使用。**

### 第一步：准备部署脚本

仓库根目录已提供 `deploy.sh` 模板（从 GitHub Release 下载最新 zip → 备份 data/ 和 uploads → 覆盖代码 → 重启）。上传到服务器：

```bash
# 宝塔「文件」上传 deploy.sh 到 /www/wwwroot/myblog/，然后终端执行：
chmod +x /www/wwwroot/myblog/deploy.sh
```

按你的环境修改脚本顶部的三个变量：`REPO`（默认已对）、`APP_DIR`、`FRONT_DIR`，以及 `RESTART_CMD`（重启方式，见脚本内注释）。

> **一键更新重启权限（重要，v3.1.4 已根治）**：若一键更新卡在第⑥步 `Operation not permitted`，根因是 gunicorn 由宝塔以 **`mw` 用户**（非 `www`）启动，且宝塔 Python 项目**不是** supervisor 管理。请下载 **v3.1.4** Release 里的 `deploy_scripts_v314fix.zip`，覆盖 `update.sh`/`deploy.sh` 到 `/www/wwwroot/myblog/`。新版重启逻辑：宝塔 CLI（`bt stop/start <项目名>`）优先 → 以 `mw` 身份 `runuser -u mw` 真杀 + 宝塔真实 gunicorn 路径（`/ww/server/pyporject_evn/blog_env/bin/gunicorn -c gunicorn_conf.py`）重新拉起，彻底绕开跨用户 kill。若项目名不是 `myblog`，改两个脚本里的 `PROJECT_NAME`；若 gunicorn 属主不是 `mw`，改 `APP_USER`。

> **一键更新完整性校验（v3.1.5+ 三重防线）**：
> - **① sha256.txt 列表比对**：`update.sh` 下载后端/前端部署包后比对 Release 附带的 `sha256.txt`，不一致**直接终止更新**（防止下载损坏/被篡改）。
> - **② zip 注释内嵌哈希**（v3.1.6+）：`package.py` 打包时把每个 zip 的 **「内容区」SHA256**（= 剥离 EOCD 尾注释后的 zip 字节，写入/修改注释不影响内容区）写进该 zip 自身的 EOCD 注释；`update.sh` 用内置 python 同样剥离注释重算内容区哈希二次比对。即使 `sha256.txt` 被整体替换，注释哈希依然能发现不一致（双源互证，解决「sha256.txt 自身被篡改」的死角）。注意：注释哈希按内容区计算，不能对含注释的整文件算（注释参与文件字节后必然对不上）。
> - **③ HMAC 签名**（v3.1.6+，可选）：若发布时设置了 `UPDATE_HMAC_KEY`，`package.py` 会为 `sha256.txt` 内容生成 HMAC 首行，`update.sh` 配置同一密钥后强制校验签名（不签名直接拒绝更新）。设置方法：本地打包机与服务器都配置同一个 `UPDATE_HMAC_KEY` 环境变量。
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
> **防重放（v3.1.6+）**：Webhook 请求必须在 Header 带 `X-Deploy-Time`（Unix 秒级时间戳），后端会校验与服务器当前时间差是否在 `WH_REPLAY_WINDOW`（默认 300 秒）内，超窗或缺失一律拒绝（HTTP 400）。GitHub 原生 Webhook 不带此头时，可改用**自建小脚本**（如 GitHub Actions 里 `curl -H "X-Deploy-Time: $(date +%s)" ...`）触发；或跳过该头后仍可用 URL token 校验（防重放会降级为仅鉴权——若需严格防重放请带该头）。
> **不会误伤数据**：`deploy.sh` 覆盖代码前会先备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/`，且解压时排除 `data/`，数据库永远不会被覆盖。

## 访问统计功能说明（新增）

- **统计入口**：前台导航「**统计**」→ `https://你的域名/stats`；后台仪表盘 →「📊 访问统计」。
- **统计内容**：累计/今日访问次数、访客区域排行（今日 + 累计 TOP10）、最受关注的文章（含回读人数）、常搜词汇 TOP10、24 小时访问时段分布。
- **统计口径**：前端每次打开/切换页面上报一次访问；打开文章记一次「阅读」（同一访客重复读会累加）；搜索关键词会被记录。
- **IP 属地识别**：由服务器后台线程异步解析（vore.top / ip-api.com 两个免费接口自动切换），结果缓存 30 天；解析失败显示「未知」，不影响页面响应速度。
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
