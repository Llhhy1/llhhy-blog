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
- ✅ Python 3.13.5 系统级环境已就绪（但**不能直接作为项目环境**，需先基于它创建虚拟环境，见第 2 步）；**注意 v3.17.14 起 `requirements.txt` 要求 Python ≥3.10**（bleach 6.4.0 / cryptography 50.0.1 的 `requires_python` 下限），低于 3.10 会 `pip install` 失败。本机 3.13.5 满足。
- ✅ 宝塔 v13 的 Python 项目入口在：左侧「网站」→ 顶部「Python项目」

> ⚠️ **v3.17.14 部署前置**：运行环境最低 **Python 3.10+**。若服务器 Python < 3.10，`pip install -r requirements.txt` 会因 bleach / cryptography / Flask / markdown 的 `requires_python` 下限报错、升级失败。上线前先 `python --version` 确认。

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
   > - **v3.21.0 新增（全部可选，不配则对应功能整体休眠、行为与旧版一致）**：
   >   - `OAUTH_GITHUB_CLIENT_ID` + `OAUTH_GITHUB_CLIENT_SECRET`：配置后登录页出现「用 GitHub 登录」。回调地址需在 GitHub OAuth App 里登记为 `https://<本站>/api/auth/oauth/github/callback`。
   >   - `OAUTH_GOOGLE_CLIENT_ID` + `OAUTH_GOOGLE_CLIENT_SECRET`：配置后登录页出现「用 Google 登录」。回调地址登记为 `https://<本站>/api/auth/oauth/google/callback`。
   >   - `BLOG_TWOFA_ENABLED`：默认 `false`。设为 `true` 后后台侧边栏出现「🔐 两步验证」，登录用户可自行绑定验证器 App。
   >   - ⚠️ 2FA 密钥用 **`SECRET_KEY` 派生的 Fernet 密钥加密后落库**：**启用 2FA 后不要更换 `SECRET_KEY`**，否则已绑定用户的密钥无法解密（表现为动态码始终错误），只能重新绑定。

4. 点 **「提交」**。等待依赖安装完成（首次约 1-3 分钟，面板会显示进度）。
5. 项目状态变为 **运行中（绿色）** 即成功。若报错，点项目右侧 **「日志」** 查看原因。

### 第 2b 步：gunicorn 并发配置（v3.20.0 起仓库内有权威副本）

仓库根目录有 **`gunicorn_conf.py`**（v3.20.0 起入库）。它**不在部署包里**——
`package.py` 只收 `myblog/`，所以 `update.sh` 不会覆盖它，日常升级无需关心它；
它的作用是**重建站点时有据可依**（此前这份配置由宝塔生成、从未入库，
删站/换机器就会丢，而且丢了以后并发能力静默退化、没人会发现）。

**必须知道的三个事实**（都写在那份文件的注释里，这里再强调一遍）：

1. **写的 `sync`，跑的是 `gthread`**：配置里是 `workers = 4, threads = 2,
   worker_class = 'sync'`，但 **gunicorn 22 只要看到 `threads > 1` 就会自动把
   worker 升级为 `gthread`**（官方文档原话：*"If you try to use the sync worker
   type and set the threads setting to more than 1, the gthread worker type will
   be used instead."*）。启动日志可见 `[INFO] Using worker: gthread`。
2. **实际并发槽 = `workers × threads` = 4 × 2 = 8**，不是 4。
   排查「慢请求占满 worker」类问题时**请按 gthread 判断**——
   曾有一份第三方审计报告据「2~3 个 sync worker」误判为「两个并发点击即可打挂全站」。
3. **4 个 worker 是刻意的**：机器是 2 核（`nproc` = 2），官方建议 `(2 × nproc) + 1`，
   但本项目用 SQLite，worker 越多写锁竞争越重，故取 4。

**验证线上实际并发模型**：

```bash
# ① 看启动日志里的 worker 类型（应出现 gthread）
grep -m1 'Using worker' /www/wwwlogs/python/myblog/gunicorn_error.log

# ② 看每个 worker 进程内的线程数（gthread 下应 > 1）
for p in $(pgrep -f 'gunicorn.*myblog'); do echo "pid=$p threads=$(ls /proc/$p/task | wc -l)"; done
```

**改并发数怎么改**：编辑服务器上的 `gunicorn_conf.py` → 在宝塔「Python 项目」
点「停止」再「启动」（**不是**「重启」）→ 用上面两条命令确认生效。

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
    # v3.20.0 新增：Atom 1.0 订阅源。**这条必须加** —— 它是精确匹配，
    # 漏了就会落到 SPA 的 try_files 拿到 index.html（RSS 阅读器解析失败）。
    location = /feed.atom {
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

### 第 4b 步：SEO 爬虫通道（v3.18.9 新增，**不加则文章对搜索引擎是空壳**）

本站前台是 Vue SPA（`<div id="app"></div>`），**不执行 JS 的爬虫拿不到任何文章内容**——
百度、微信、QQ 链接预览看到的都是一张空白壳页。这一段就是给它们开的服务端通道：
把爬虫/社交抓取 UA 的 `/post/<slug>` 请求改写给后端的 `/api/og/post/<slug>`，
由后端渲染带正文、canonical 与 JSON-LD 的服务端 HTML；真人照旧走 SPA。

**① 在 `http { }` 块内、所有 `server { }` 之前**加这段 `map`（已有同名 `map` 就合并，不要声明两次）：

```nginx
# SEO 爬虫通道：判定哪些 UA 走服务端壳页（粗筛，后端有第二层真人否决）
map $http_user_agent $seo_shell {
    default                                0;
    # 搜索引擎 —— 与 utils/seo_shell.py::SEARCH_BOT_UA 对齐
    ~*(Googlebot|Bingbot|Baiduspider|Sogou|360Spider|Bytespider|YisouSpider|Yandex|DuckDuckBot|Applebot|PetalBot|Naver|QwantBot|SeznamBot|Google-InspectionTool|ShenmaSpider|ToutiaoSpider) 1;
    # 社交/IM 链接预览抓取器：UA 里不含 bot 字样，后端 detect_bot() 也识别不出，必须列全
    # —— 与 utils/seo_shell.py::_SOCIAL_PREVIEW_UA 对齐
    ~*(MicroMessenger|weixin|QQ\/|qqtool|Weibo|Twitterbot|facebookexternalhit|Facebot|TelegramBot|LinkedInBot|SlackBot|WhatsApp|SkypeURIPreview|Discordbot|Embedly|Pinterest|Vkshare|W3C_Validator|Outbrain|Nuzzel|BitlyBot|Line-Poker) 1;
}
```

> ⚠️ **这份 map 是「粗筛」，不是唯一真相源**：权威判定在
> `myblog/utils/seo_shell.py`（它有请求头可看，nginx 没有）。两处的 token 列表
> **应保持「nginx ⊆ 后端」**——即 nginx 放行的每个 UA，后端都认得。
> 若 nginx 放行了后端不认识的 UA，后端会判 `not-crawler` 并返回 404
> （v3.19.1 起**不再 302**，所以不会成环，但那个抓取方也拿不到内容）。
> 反过来（后端有、nginx 漏）方向更安全：那个抓取方拿到 SPA 空壳，不致命。
> v3.19.1 补齐了原先漏掉的 `ShenmaSpider`/`ToutiaoSpider`/`QwantBot`/`SeznamBot`/
> `Embedly`/`Pinterest`/`Vkshare`/`W3C_Validator`/`Outbrain`/`Nuzzel`/`BitlyBot`/
> `Line-Poker`/`Facebot` 等（此前这些抓取方只能拿到 SPA 空壳）。

> ⚠️ **绝对不要把 `QQBrowser` / `MQQBrowser` 写进上面的列表** —— 那是 QQ 内置浏览器里的
> **真人**（会执行 JS）。注意即便不写，真人的 UA 里也可能带 `QQ/9.7.x` 命中规则，
> 所以**后端必须有第二层否决**（`Sec-Fetch-Mode: navigate` / `Accept: text/html`），
> nginx 这层只是粗筛。见 `myblog/utils/seo_shell.py`。
> ⚠️ 也**不要**偷懒写成 `bot|spider|crawl` 这类宽泛词——那会把 Ahrefs/Semrush 等第三方
> SEO 蜘蛛一并放进服务端通道，等于给出一个批量抓取全文的入口。

**② 在 `server { }` 块内、`location / { }` 之前**加这段（`$seo_shell` 命中才 rewrite，
`last` 会重新匹配 location 从而命中已有的 `location /api/` 反代；避开在 `if` 里写 `proxy_pass`）：

```nginx
    # 爬虫/社交抓取访问文章页 → 走服务端壳页（真人本 UA 不命中 → 落到下面的 try_files 走 SPA）
    # ?seo=1 是「我是经 Nginx 正式通道进来的」标记，后端据此决定是否允许索引；
    # 同时它让「真人被误判」时后端能 302 回 /post/<slug> 而不会成环。
    location /post/ {
        if ($seo_shell) { rewrite ^/post/([^/?#]+)/?$ /api/og/post/$1?seo=1 last; }
        try_files $uri $uri/ /index.html;
    }
```

**③ 在 `server { }` 块内、图片正则 `location ~ .*\.(gif|jpg|jpeg|png|bmp|swf)$` 之前**加这段
（**v3.18.9 补充，漏了它分享卡永远是兜底图**）：

```nginx
    # 【必须】/api/og/ 必须比图片正则优先，否则分享卡 .png 永远拿不到后端渲染结果。
    # nginx 优先级：`=` 精确 → `^~` 前缀（命中即停止正则）→ 正则 ~ / ~*（先于普通前缀）。
    # 宝塔默认的 `location ~ .*\.(png|jpg|...)$` 是正则，会压过 `location ^~ /api/`，
    # 把 /api/og/post/<slug>.png 从反代上抢走 → 落到 SPA 静态根里的 og-default.png。
    # 用更长的 ^~ 前缀（^~ 之间按最长前缀取胜）抢回给 Flask。
    location ^~ /api/og/ {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

> ⚠️ 常见误区：`location ^~ /api/` **挡不住** 图片正则——`^~` 只在**最长前缀**命中时才跳过正则，
> 而 `/api/og/x.png` 的最长前缀就是 `^~ /api/`（也带 `^~`）……但**宝塔站点配置里图片正则在
> `^~ /api/` 之前出现时**，一旦图片正则先被匹配就轮不到它。显式加一条更长的 `^~ /api/og/`
> 是唯一稳妥的写法。判据：`curl -D- .../post/x.png` 若出现
> `Content-Disposition: inline; filename=og-default.png`，或与站点根目录 `og-default.png`
> **sha256 完全相同**，就是被这层截了。

**④【重要】宝塔 `proxy.conf` 全局开了 `proxy_cache`** —— `nginx.conf` 顶层 `include proxy.conf`，
其中 `proxy_cache cache_one;` 会**缓存所有反代响应**。若某次后端降级（字体缺失、文章当时不可见）
吐出了兜底图，这张图会被**长期缓存**，之后即使代码修好，客户端也一直拿到旧图——
**并且客户端发 `Cache-Control: no-cache` 无法绕过**（需 `proxy_cache_bypass`）。
修完分享卡相关代码后，必须清一次：

```bash
find /www/server/nginx/proxy_cache_dir -type f -delete && nginx -s reload
```

**⑤ 保存 → `nginx -t` 通过 → 重载配置**（不要跳过语法检查，改错会导致全站 502）。

**验证**（把 `<slug>` 换成你站上真实文章的 slug）：

```bash
# 爬虫视角：应有 <title>、og:title、canonical 指向 /post/<slug>、且不含 noindex
curl -sS -A "Mozilla/5.0 (compatible; Baiduspider/2.0)" "https://你的域名/post/<slug>" \
  | grep -oE "<title>[^<]*|og:title' content='[^']*|canonical' href='[^']*"

# 真人视角：应仍是 SPA（首行含 id="app"）
curl -sS -A "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/120" "https://你的域名/post/<slug>" | head -c 200

# 【最容易做错的一条】QQ 内置浏览器里的真人：必须是 302 回 /post/<slug>，不能被留在壳页
curl -sSI -A "Mozilla/5.0 (Linux; U; Android 12) MQQBrowser/13.0 QQ/9.7.10.43400" \
  -H "Accept: text/html" "https://你的域名/api/og/post/<slug>?seo=1" | grep -iE "^HTTP|^location"

# 分享卡（v3.18.9 补充）：必须是 1200×630 真实卡片，不是 966B 兜底图
curl -sS -o /tmp/og.png "https://你的域名/api/og/post/<slug>.png"
ls -l /tmp/og.png            # 正常应 >100KB（约 120KB）；966B = 仍被截胡
# 与站点根目录静态兜底图对比，sha256 必须不同：
sha256sum /tmp/og.png /www/wwwroot/你的站点根/og-default.png
```

> 后台「系统诊断」的 **搜索引擎 SEO** 一节会检查爬虫通道路由是否存在；
> 站内若配了 `site_url` 且通道正常，收录页的「通道自检」会同时给出 4 种身份的实测结果。


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

> **v3.21.2（修复勋章播种的多 worker 竞态假警报）升级要点**：**纯后端改动，只需覆盖后端包**。
> - **现象**：v3.21.1 重启日志出现 `默认勋章播种失败: UNIQUE constraint failed: badge.key`，但勋章表数据完好 —— 是 4 个 worker 并发启动的**竞态**（都看到空表、都去插入，后提交的撞键），功能无害但属**假警报**，会掩盖真正的播种失败。
> - **修复**：`seed_badges()` 改为按 key 逐枚幂等；撞键回滚放弃。顺带修掉「表里有任意一行就整体跳过 → 缺的勋章补不齐」的坑。
> - **升级后验证**：重启后 `grep 播种失败 gunicorn.log` 应无新增；`badge` 表仍为 5 行。
> - **回滚**：无破坏性变更。

> **v3.21.1（修复默认勋章未播种）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 未动）。
> - **修的是什么**：v3.21.0 的 `seed_badges()` 写在了 `_migrate_new_tables_v3()` 的 `if need:` 分支内，而 `create_app()` 里的 `db.create_all()` **已经先把新表建好了** → `need` 恒为空 → **勋章从未播种**。线上实测 `badge` 表 0 行：读者能攒积分但**永远拿不到勋章**，且全程不报错。
> - **怎么修**：播种移出条件分支，改为无条件调用（幂等，表内有数据则不插入）。
> - **升级后**：重启时自动补齐 5 枚默认勋章，**无需手工 SQL**。可在服务器上验证：`python -c "import sqlite3;print(sqlite3.connect('data/blog.db').execute('select count(*) from badge').fetchone())"` 应 ≥ 5。
> - **回滚**：无破坏性变更；回退到 v3.21.0 仅失去勋章播种修复。

> **v3.21.0（内容多语言 M1 + PWA + 读者积分勋章 + OAuth + 2FA）升级要点**：**后端与前端都改了 → 两个包都要覆盖**（`myblog-backend.zip` + `vue-frontend-dist.zip`）。
> - **新增 6 张表，全部启动自愈**：`Reader` / `PointLog` / `Badge` / `ReaderBadge` / `OAuthAccount` / `UserTwoFactor`。由 `_migrate_new_tables_v3()` + `db.create_all()` 在应用启动时建表并播种 5 枚默认勋章，**无需手工 SQL、无需 `flask db`、无需 `flask db stamp`**。首次启动日志会打印「已迁移：新建数据表（…）」。
> - **无新增依赖**：2FA 的 TOTP 是标准库实现（RFC 6238），**不需要 `pip install pyotp`**。
> - **无新增必填环境变量**：新增 5 个**可选**变量，不配置则对应功能整体休眠、行为与 v3.20.0 完全一致：
>   - `OAUTH_GITHUB_CLIENT_ID` + `OAUTH_GITHUB_CLIENT_SECRET` → 配置后登录页出现「用 GitHub 登录」；回调地址需在 GitHub OAuth App 登记为 `https://<本站>/api/auth/oauth/github/callback`。
>   - `OAUTH_GOOGLE_CLIENT_ID` + `OAUTH_GOOGLE_CLIENT_SECRET` → 同上，回调 `https://<本站>/api/auth/oauth/google/callback`。
>   - `BLOG_TWOFA_ENABLED=true` → 开放后台「🔐 两步验证」绑定入口（默认 `false` 关闭）。
> - **无需改 Nginx**：PWA 的 `/sw.js` 与 `/manifest.webmanifest` 落在站点根目录，nginx 现有 `location /` 的 `try_files` 已能正确返回，scope 自动为 `/`。
> - **2FA 密钥依赖 `SECRET_KEY`**：密钥用 `SECRET_KEY` 派生的 Fernet 加密后落库。**若更换 `SECRET_KEY`，已绑定的 2FA 密钥将无法解密**（表现为动态码始终错误），需用户重新绑定 —— 请勿在启用 2FA 后随意更换该变量。
> - ⚠️ **公开积分排行榜会显示登录读者的用户名**（匿名读者显示「读者N」）。如不希望对外展示，可先不启用该入口或改 `myblog/gamify.py::leaderboard()`。
> - **回滚**：无破坏性变更；回退到 v3.20.0 仅失去本版新功能（已建的新表会保留，不影响旧版本运行）。

> **v3.20.0（待办清单批次：工程化门禁 + 异步化 + 可观测性 + 前端 a11y）升级要点**：**本版同时改了后端与前端 → 两个包都要覆盖**（`myblog-backend.zip` + `vue-frontend-dist.zip`）。
> - **新增 `GET /api/health`**：无需登录的存活探针，回 `{ok, version, db}`；依赖不可用返回 **503**。此前项目**没有**任何探活端点，`UPTIME_MONITOR.md` 的监控可以直接打这个地址做机器判定（不再依赖人工体检）。
> - **通知改为异步**：保存/发布文章不再同步等待 Telegram / 企业微信推送（原先每渠道 6s、两渠道齐配最坏阻塞 **12s**）。**行为变化**：调用即返回，外发在后台线程；无应用上下文时（脚本调用）自动退化为同步。线上目前两个渠道**都未配置**，所以体感无变化。
> - **`gunicorn_conf.py` 已入库**（仓库根）：**不在部署包里**，`update.sh` 不会覆盖服务器上那份，日常升级无需关心。详见上文新增的「第 2b 步」。
> - **CI 新增 lint 门禁**（ruff + 债务棘轮 + i18n + 发布公钥一致性）与 **dependabot**：仅影响 GitHub 侧，不影响部署。`npm install` → `npm ci`。**Dependabot 会定期开依赖升级 PR，但不会自动合并** —— `requirements.txt` 的上限是带理由刻意选的，合前需人工复核。
> - **无新表、无新依赖、无新增必填环境变量、无表结构变更、无需 `flask db`。** 新增一个**可选**环境变量 `SEO_AUTO_PUSH`（默认 `0` = 关闭）：设为 `1` 后，文章发布即自动入队推送给已配置凭据的搜索引擎（复用收录控制台的 `enqueue` 限流去重）。默认关闭是为了不烧百度当日推送配额；不设则完全无行为变化。
> - **🔴 Nginx 需要加一行**：本版新增 `GET /feed.atom`（Atom 1.0 订阅源）。nginx 对 `/feed.xml` 用的是 `location =`（精确匹配），所以**必须同步加 `location = /feed.atom`**（原文见上文「第 4 步」的 feed 段落）。**漏了不会报错，只会悄悄返回 SPA 的 index.html**，表现为「订阅器说这个 Atom 源无效」。改完 `nginx -t && nginx -s reload`。
> - **新增 `GET /api/health`**：见上一条。
> - **前端 a11y 变化**（可见的很轻微）：键盘「跳到正文」链接（Tab 首个焦点，平时不可见）；toast 改为**常驻 live region**（读屏可播报 —— 原先给每条 toast 现挂 `role="status"`，而 live region 必须先在 DOM 中存在才会被朗读）；`/docs` 目录高亮的 observer 现在离开页面会释放（修掉一处真实泄漏）；图片灯箱补 `role="dialog"` + **完整焦点陷阱**（Tab 循环、关闭后焦点归还）；**修掉「每页 2 个 `<main>`」**（11 个视图的 `<main>` 改 `<div>`，landmark 语义恢复正确）。
> - **回滚**：本版无破坏性变更，回退到 v3.19.2 会失去 `/health` 与 a11y 修复，其余功能不受影响。

> **v3.19.2（修正百度配额字段名 `remain`）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 未动）。**无新表、无新依赖、无新环境变量、无需改 Nginx、无需 `flask db`**——只需覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」。
> - **改了什么**：百度主动推送的剩余配额字段名是 **`remain`**（生产实测 `{"remain":8,"success":1}`），v3.19.0/v3.19.1 读的是 `remaining` → 剩余配额读不到、写不进 `seo_baidu_quota`，后台「🔍 收录」页的配额栏一直空白。修法：两个字段名都认 + 把 `remain` 加入响应字段白名单。
> - **影响范围（说清楚以免误判严重度）**：只是**配额显示缺失**——`quota` 档（配额耗尽）**一直都能被正确识别**，走的是 `data["error"]` 里 `"over quota"` 那条分支。**不是状态误判，推送功能本身正常**（生产 7 篇全部推送成功）。
> - **升级后自检**：后台「🔍 收录」→ 点一次推送；成功后配额栏应显示「剩余 N」。（在此之前该栏为空属预期，因为要靠一次成功推送才会写入。）
> - 回滚：本版只改字段名读取，回滚到 v3.19.1 仅会失去配额显示，无其它影响。

> **v3.19.1（第三轮复审修复：302 环 + 出站 SSRF + 自检放大面）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 未动，前端包无变化、可不必覆盖）。**本版不强制改 Nginx**（见下第 3 条）。
> - **⚠️ 本版修的是一个正在发生的线上事故，上线后必须复验**：v3.19.0 让**带 `Accept: text/html` 的搜索引擎**与**QQ/微信内置浏览器真人**在 `/post/<slug>` 陷入**无限 302 环**（实测 Googlebot / Baiduspider / QQ 真人 12 次重定向后仍是 302）→ 搜索引擎抓不到正文、真人看到 `ERR_TOO_MANY_REDIRECTS`。复验命令（三者都应 `200` 且 `num_redirects=0`）：
>   ```bash
>   curl -s -o /dev/null -L --max-redirs 12 -w '%{http_code} %{num_redirects}\n' \
>     -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
>     -H "Accept: text/html,application/xhtml+xml,*/*;q=0.8" https://<你的域名>/post/<真实slug>
>   curl -s -o /dev/null -L --max-redirs 12 -w '%{http_code} %{num_redirects}\n' \
>     -A "Mozilla/5.0 (Linux; U; Android 12) AppleWebKit/537.36 Chrome/100.0 Mobile Safari/537.36 MQQBrowser/13.0 QQ/9.7.10.43400" \
>     -H "Accept: text/html" -H "Sec-Fetch-Mode: navigate" https://<你的域名>/post/<真实slug>
>   ```
>   预期：Googlebot 得 `200`（可索引壳页）；QQ 真人得 `200`（noindex 可读页，能看到正文）。
> - **行为变化（预期内）**：真人经通道时**不再是 302**，而是拿到 **200 + `noindex,nofollow` 的可读页**（微信/QQ 内置浏览器里的正文照常可读，只是没有 SPA 交互）。这是断掉 302 环的唯一办法；**不影响正常浏览器**（Chrome/Safari 的 UA 不命中 nginx 的 `map`，根本不进通道）。
> - **3. Nginx 可选更新**：核心修复在后端，**不改 nginx 也已生效**。若要顺带补齐抓取方覆盖，把 `map` 更新为上文「第 4b 步」的最新版本（新增 `ShenmaSpider`/`ToutiaoSpider`/`QwantBot`/`SeznamBot`/`Embedly`/`Pinterest`/`Vkshare`/`W3C_Validator`/`Outbrain`/`Nuzzel`/`BitlyBot`/`Line-Poker`/`Facebot`），然后 `nginx -t && nginx -s reload`。**必须保持「nginx 的 UA 集合 ⊆ 后端」**：nginx 放行了后端不认识的 UA 时后端判 `not-crawler` 返回 404（不会成环，但那个抓取方拿不到内容）。
> - **新增限流**：后台「🔍 收录」的**推送**最多 3 次 / 5 分钟，且同引擎有排队批次时拒绝新推送（**百度当日配额用完不可逆**）。批量/单篇连点会被拒，属预期。
> - **自检页变化**：`/admin/seo` 的「通道自检」现在需要**超管登录**（原先匿名可调），判定显示**三档**（可索引壳页 / 可读但不索引 / 不给内容），并在出现 3xx 时明确报警。
> - **⚠️ 服务器 worker 类型的既有事实（记录备查，避免后人误判）**：宝塔面板生成的 `gunicorn_conf.py` 里是 `workers = 4` + `threads = 2` + `worker_class = 'sync'`；**gunicorn 22.0.0 会在 `threads > 1` 时自动把 worker 升级为 `gthread`**（启动日志可见 `Using worker: gthread`，每个 worker 4 个线程）→ 实际并发槽为 **4 × 2 = 8**。排查「自请求/慢请求占满 worker」类问题时，请按 gthread 而非 sync 判断。
> - 无需 `flask db`（无新表）；无新增依赖、无新增环境变量。

> **v3.19.0（后台「🔍 收录」控制台：主动推送 + 通道自检）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 未动，前端包无变化、可不必覆盖）。**无需补 Nginx 配置**——本版不含任何 Nginx 变更，通道配置仍以 v3.18.9 的「第 4b 步」为准。
> - **覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」**；**无新依赖、无新增必填环境变量**。
> - **⚠️ 新表 `seo_submission` 启动时由 `create_all` 自愈创建，无需 `flask db`**（与 `game` 表同一机制，见 `models.SeoSubmission` docstring 记录的迁移策略）。首次启动日志可见「已迁移：新建数据表（seo_submission）」。
> - **新增一个出网站点**：本版起后台可主动向**百度**（`http://data.zz.baidu.com`）与 **IndexNow / Bing**（`https://api.bing.com`）推送文章 URL。这是本项目**唯一允许 http 的出站目标**，且**仅当 host 精确等于 `data.zz.baidu.com`** 才放行（精确比对，非后缀匹配）。**若服务器有出站防火墙/安全组白名单，需放行 `data.zz.baidu.com:80` 与 `api.bing.com:443`**；未放行时推送会记为 `fail`（响应 `blocked-host` 或超时），**不影响站点本身运行**。
> - **⚠️ 字体已随包入库**：`myblog/static/fonts/wqy-microhei.ttc`（5.2 MB，文泉驿微米黑，GPL v2 + 字体嵌入例外）。这修复了 v3.16.0 以来「服务器无中文字体 → 分享卡静默降级成兜底图」的隐患。**升级后必须清两处缓存**，否则仍看到旧兜底图：① 后端 `myblog/data/og_cache/` 全删；② Nginx 代理缓存 `find /www/server/nginx/proxy_cache_dir -type f -delete && nginx -s reload`（宝塔全局 `proxy_cache` 会长期缓存兜底结果，客户端 `Cache-Control: no-cache` 绕不过）。
> - **推送凭据需在后台自行配置**（不随包分发）：进「🔍 收录」页 → 填百度推送 token（百度搜索资源平台获取）与/或 IndexNow key。凭据以 Fernet 密文存 `Setting` 表，**不入包、不入库明文、不回显**。
> - **升级后自检**：后台左下角 `v3.19.0`；侧栏出现「🔍 收录」；进页面点「通道自检」应见 4 个身份判定（其中 **QQ 内置浏览器真人** 与 **Chrome** 两盏灯必须是「拿到 SPA」）；`.png` 分享卡应返回真实卡片而非兜底图。

> **v3.18.9（SEO 爬虫通道修复）升级要点**：**纯后端改动 + 一段 Nginx 配置**（`vue-frontend/` 未动，前端包无变化）。
> - **覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」**；**无表结构变更、无新依赖、无新增必填环境变量**。
> - **⚠️ 必须补 Nginx 配置，否则本轮改动等于没做**：见上文 **「第 4b 步：SEO 爬虫通道」**。若你的服务器此前**已**手工配过一条爬虫规则（`if ($http_user_agent ~* "(bot|spider|crawl|…")` → `rewrite … /api/og/post/$1`），**请用「第 4b 步」的版本替换它**——旧规则有两个问题：① 含宽泛的 `bot`/`spider`/`crawl`，会把 Ahrefs/Semrush 等第三方 SEO 蜘蛛一并放进服务端通道；② 不带 `?seo=1`，后端无法区分「经通道」与「直敲」，会对所有访问者（含百度）下发 `noindex` 并输出指向 API 地址的 canonical → **接通通道反而杀死收录**。替换后记得 `nginx -t` 再 reload，原配置先备份。
> - **行为变化（预期内，且是本轮修复的重点）**：爬虫/社交抓取访问 `/post/<slug>` 从「拿到 `noindex` 的 meta 页」变为「拿到 `index,follow` 的完整壳页（含正文 + canonical + JSON-LD）」；微信 UA 首次能拿到服务端 HTML（此前是 SPA 空壳）；第三人 SEO 蜘蛛不再获得壳页；真人（含 QQ/微信内置浏览器）行为完全不变，仍走 SPA。
> - **升级后自检**：后台「系统诊断」→「搜索引擎 SEO」应显示爬虫通道路由存在；或直接按「第 4b 步」末尾的 4 条 `curl` 命令验证。

> **v3.18.8（修复 v3.18.7 的验签顺序缺陷）升级要点**：**仍需先覆盖部署脚本再做更新**（本轮改的依然是 `update.sh`）。
> - **必须用本 Release 的 `deploy_scripts_v3188fix.zip`**，不要用 v3.18.7 的那个——v3.18.7 的脚本有个顺序缺陷：工作目录 `/tmp/llhhy_update` 跨轮复用且不清校验清单，会把上一轮遗留的 `sha256.txt` 跟本轮的 `sha256.txt.sig` 配对比对，**必然验签失败**（实测首次跑就 BAD；站点不会受影响，脚本在覆盖代码前就被拦住）。
> - 若你从未覆盖过 v3.18.7 的脚本（即服务器上一直是旧版 update.sh），直接用本 Release 的 `deploy_scripts_v3188fix.zip` 覆盖即可，一步到位。
> - **本次更新前后的行为差异**：脚本会自动清理工作目录里的旧清单与旧包，无需你手动 `rm -rf /tmp/llhhy_update`（想手动清也无害）。
> - 其余（签名机制、`RELEASE_PUBKEY` / `ALLOW_UNSIGNED` / `ALLOW_DOWNGRADE` / `GH_MIRROR`、自建发布者流程）同 v3.18.7，见上一节。

> **v3.18.7（更新链 fail-closed + Ed25519 发布物签名）升级要点**：**本轮改的是部署脚本自身**，而 `update.sh` / `deploy.sh` **不在** `myblog-backend.zip` 里 —— 必须**先单独覆盖脚本**。
> - **升级顺序**：① 从本 Release 下载 `deploy_scripts_v3187fix.zip`，解压覆盖 `/www/wwwroot/myblog/update.sh` 与 `deploy.sh`（保持 **LF 行尾**，`chmod +x`）；② 再跑 `bash /www/wwwroot/myblog/update.sh`。顺序反了**不会坏**——旧脚本仍能装上 v3.18.7 的后端代码，只是那一刻生效的仍是旧（fail-open）校验；覆盖脚本后下次更新才走新逻辑。
> - **行为变化（预期内）**：更新**默认要求 Release 带 `sha256.txt.sig` 且验签通过**，否则**终止更新**；不再自动兜底第三方公共镜像（ghfast / gh-proxy / ghproxy）——若你的服务器访问不了 GitHub，请**显式**设 `GH_MIRROR="https://你自己的代理/"`；远端版本不高于本地时不再重复覆盖（同版本收工，更低版本需 `ALLOW_DOWNGRADE=1`）。
> - **可用的环境变量（全部可选）**：`RELEASE_PUBKEY`（换成自建发布者的公钥）、`ALLOW_UNSIGNED=1`（仅调试/过渡期，跳过验签并打警告）、`ALLOW_DOWNGRADE=1`（允许降级覆盖）、`GH_MIRROR`（显式镜像前缀）。
> - **验签依赖**：需要 `cryptography`（本就在 `requirements.txt` 里，无需额外安装）。脚本会优先用项目虚拟环境的 python 验签，找不到带 `cryptography` 的解释器时**终止更新**并提示。
> - **无迁移、无新增必填环境变量、前端产物零变化**（前端未动）。验证：后台左下角 = **v3.18.7**；`bash -n update.sh` 无输出（语法 OK）。

### 自己发版（fork / 自建发布链）怎么用签名
```bash
# 1) 生成（或查看）你自己的发布密钥对；公钥会打印出来
python package.py --gen-key
# 2) 把公钥填进 update.sh 的 BUILTIN_RELEASE_PUBKEY（或部署侧设环境变量 RELEASE_PUBKEY）
# 3) 正常打包（会自动签名，产出 sha256.txt.sig）
python package.py
# 4) 本地三链自检（整文件哈希 / zip 注释内容区哈希 / 发布物签名）
python verify_package_checksums.py
```
> 私钥默认在 `~/.workbuddy/llhhy_release_key`（0600）。**请备份**：私钥丢失后无法再为同一公钥补签名，只能换公钥并同步更新部署侧。
> 换密钥路径：设环境变量 `RELEASE_SIGNING_KEY=<私钥文件路径>`；只想本地调试不签名：`python package.py --no-sign`（这样打出的包会被新版 `update.sh` 拒绝，属预期）。

> **v3.18.6（退役公共 SSR：8 个页面路由改 410 + 删 7 个死模板）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 未动，前端包无变化）。覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」；**无表结构变更、无新依赖、无新增环境变量、无新 Nginx 规则**。
> - **⚠️ 必须整体覆盖后端包**（本轮**删除了 7 个文件**）：`myblog/templates/` 下的 `index.html` / `post.html` / `archive.html` / `archive_timeline.html` / `about.html` / `links.html` / `search.html` 已删除。覆盖式部署**不会删服务器上的旧文件** → 升级后建议手动清理这 7 个残留模板（不清理也无功能影响：已无任何路由渲染它们）。
> - **行为变化（预期内）**：直接访问 Flask 端口（`:8686`）上的 `/`、`/post/xxx`、`/archive`、`/category/xxx`、`/tag/xxx`、`/search`、`/about`、`/links` 现在返回 **410 Gone**（此前返回 SSR HTML）。**公网无感**——这些路径在 Nginx 下本来就由 Vue SPA 兜底，升级前后用户看到的都是 SPA 页面。
> - **不受影响**：`/login` `/register` `/logout`（SSR 认证页）、`/post/<slug>/comment` 与 `/post/<slug>/like`（POST 入口）、`/api/*`、`/admin/*`、`/mcp`、`/feed.xml`、`/feed/comments`、`/sitemap.xml`、`/robots.txt`。
> - **验证清单**：后台左下角 = **v3.18.6**；公网首页/文章页/归档页正常（SPA 渲染）；`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8686/` = **410**（预期）；`/login` 直接访问 Flask 仍 200；`/api/site`、`/feed.xml`、`/sitemap.xml`、`/robots.txt` 均 200。

> **v3.18.5（第三方独立审计 P0 批次：8 项真实缺陷修复）升级要点**：**纯后端改动，只需覆盖后端包**（`vue-frontend/` 一字未动，前端包无变化、可不必覆盖）。覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」即生效；**无表结构变更、无新依赖、无新增环境变量、无新 Nginx 规则**。
> - **新增文件**（务必整体覆盖，勿只增量拷单文件）：`myblog/templates/_error_base.html`、`404.html`、`403.html`、`500.html`、`error.html`（统一错误页）。
> - **⚠️ 正文渲染缓存会整体失效**：`_RENDER_VERSION` 由 `2` 提升到 `3`（Markdown 表格白名单修复的必然结果）——升级后**首次访问每篇文章会重新渲染一次**（属正常，稍后恢复缓存速度；渲染结果会通过独立连接写回 `post.content_html`）。
> - **行为变化（预期内）**：① 会话失效（改密 / 被踢下线 / 闲置超时）访问非 `/api/` 页面现在**跳登录页**，此前是 500；② 前台表单登录现在正确记录会话版本，**改过密码的用户首次需重新登录一次**（属正常）；③ `/api/review/annual`、`/api/ai/summary/<slug>` 不再返回隐私空间与回收站文章的数据；④ 后台「🤖 AI 摘要」页**仅超级管理员可见**（普通管理员访问 403，侧栏入口对普通管理员隐藏）；⑤ 接口 404 等错误现在返回 JSON（`{"error": "…"}`）而不是 HTML 错误页；⑥ 浏览器路径的 404/500 走新的品牌错误页。
> - **验证清单**：后台左下角 = **v3.18.5**；访问一个不存在的 `/api/xxx` 应返回 JSON 且 `Content-Type: application/json`；浏览器访问一个不存在的路径应看到「页面不存在」错误页（非 Werkzeug 默认页）；任一含 Markdown 表格的文章**表格结构正常显示**；后台「访问统计」页正常；`/api/review/annual` 与 `/api/games` 正常 200。
> - **无需操作**：`myblog/data/blog.db` 不受影响（测试库隔离只作用于本地 pytest，生产无影响）。

> **v3.18.1（超长文件拆分，纯重构）升级要点**：后端内部结构重组 —— `utils.py` → `myblog/utils/` 包（timeutil / render / net / slug / text / security / settings / web）、`admin/posts.py` → `post_editor` / `post_manage` / `post_trash` / `post_history` / `taxonomy`。**公共 API、路由 URL、endpoint、环境变量、依赖、表结构全部不变**（已用逐名 AST 等价性 + 26 条路由守恒 + 99 处 `url_for` 全解析 + 113 passed 验证）。**只需覆盖后端包** + gunicorn「停止 → 启动」；前端包无变化（可不必覆盖）。⚠️ 因内部模块被删除（`utils.py` / `admin/posts.py`），升级务必**整体覆盖** `myblog-backend.zip`（勿只增量拷单个文件）。验证：后台左下角 v3.18.1，各后台页与文章页正常。

> **v3.18.4（补齐核心 i18n）升级要点**：**只需覆盖前端包**（`vue-frontend-dist.zip` —— 改的是 `App.vue` / `store.js` / `components/Sidebar.vue`）；后端仅版本号变化（覆盖亦可）。覆盖后**硬刷新（Ctrl+F5）**。**无迁移、无新依赖、无新增环境变量。**验证：点顶栏「EN」后**导航栏 13 项全英文**（含 回顾→Review / 社交→Social / 游戏→Games）；抽屉里 后台 / 写文章 / 退出 / 登录 / 注册 / 主题 均随语言切换；通知面板（通知 / 全部已读 / 暂无通知）与「回到顶部」亦切换；悬停语言按钮 tooltip 显示「切换语言」。

> **v3.18.3（移除内置插件 page_translate + 恢复核心中英切换）升级要点**：**前后端包都要覆盖**——前端 `App.vue` / `store.js` / `global.css` 恢复了语言切换按钮与 i18n 字典（若只覆盖后端包，前台**看不到**语言按钮）；后端删除插件目录（`myblog/plugins/page_translate/`）与前端远程组件（`myblog/static/plugins/page_translate/`），`ENABLED_PLUGINS` 默认值恢复为空。⚠️ 覆盖式部署**不会删服务器上的旧插件文件**，升级后建议手动删除 `myblog/plugins/page_translate/` 与 `myblog/static/plugins/page_translate/`（含 `__pycache__`）保持整洁——因 `ENABLED_PLUGINS` 已为空，残留文件**不会被加载**、无功能影响。**无迁移、无新依赖、无新增环境变量。**验证：前台顶栏恢复「中 / EN」语言按钮（点击切英文，抽屉底部亦有）；前台**不再**出现「翻译整页」浮层；后台「🧩 插件管理」不再列出 `page_translate`；后台左下角 v3.18.3。

> **v3.17.13（后台备份页移动端重构 + 前台导航图标统一）升级要点**：后端包 + **前端包都需覆盖**（`vue-frontend-dist.zip` 更新了 `App.vue` 导航与 `global.css` 的 `.nav-emoji`）；无迁移、无新增依赖。`backup.py` 新增 4 个统计工具（`fmt_size`/`file_size`/`dir_stat`/`backup_stamp`），`admin/settings.py` 装配 `summary` 给备份页模板。

> **v3.17.12（RSS 聚合超时 + gitignore 兜底）升级要点**：`feed_agg.py` 聚合抓取加 12s socket 超时（防友链源挂起拖死 worker）；`.gitignore` 补纪律零黑名单。**只需覆盖后端包**；无迁移、无前端改动。
> **v3.17.11（全项目审查修复）升级要点**：SSR 文章页 highlight.js 由 bootcdn 改为**本地静态资源**（`myblog/static/vendor/hljs/`，新增 3 个文件：`highlight.min.js` + 两个主题 CSS）；`custom_css` 注入前转义；MCP 写端点限流改 fail-closed；`requirements.txt` 可选依赖补上限。**后端包必须覆盖**（含 `static/vendor/`），前端包无变化。**无迁移、无新依赖要求**（依赖上限仅约束版本区间，已装环境无需重装）。验证：访问任一篇文章（SSR 页）查看代码块是否已高亮（亮/暗主题各一次）。
> **v3.17.10（update.sh 清理旧 assets + 文档页代码高亮修复）升级要点**：`update.sh` 前端覆盖步骤新增「先清 `assets/` 再解压」（防止历史 hash chunk 堆积）；文档页 `/docs` 的 highlight.js 由 cdnjs 动态注入改为**本地打包**（原被 CSP 拦截、高亮从未生效）。**只需覆盖前端包**（后端仅版本号）；无迁移、无新依赖。
> **v3.17.9（复制修复 + 后台移动端 + AI 摘要 + 社交墙独立页）升级要点**：**前后端包都要覆盖**（前端新增 `lib/clipboard.js`、`lib/social.js`、`SocialView.vue` 与路由 `/social`；后台模板改造复制调用、`admin.css` 补移动端规则、`social.html` 加平台预设）。**无迁移、无新依赖**。验证：手机端打开后台「备份配置」与「诊断助手」不再挤压/溢出；任一「复制」按钮（后台媒体库/预览链接、前台代码块/分享链接）可复制并给出提示；后台「AI 摘要」页摘要完整可读；前台导航出现「🔗 社交」，主页出现「找到我」区块，`/social` 卡片墙正常。
> **v3.17.3（评论表情回应 + 访客来源分析）升级要点**：**前后端包都要覆盖**（后端新增 `api/reactions.py`、VisitLog 新列 `referrer` 与 `/api/stats/referrers`；前端新增评论表情条与统计页「访客来源 Top 10」）。**VisitLog 的 `referrer` 列由启动自愈自动添加**（`_migrate_visit_log_table` 幂等补列，重启即生效）——**无需手动迁移**；备用脚本 `myblog/migrate_visit_log_referrer.py`（幂等）仅当自愈失效时手动跑。表情回应计数存 Setting KV（`react_<评论id>`），零表结构变更。验证：评论区出现 👍❤️😂🎉🤔👏 表情条（点击 +1，再点取消）；统计页出现「🧭 访客来源 Top 10」卡（需积累几天外部访问数据）；后台左下角 v3.17.3。**v3.17.3 同版补全「🗺️ 访客地图」**（`/annual` 页，阿里 DataV 合规底图由后端缓存 7 天，无需任何 key；仅省级聚合、不含个人位置；底图不可用时前端自动降级为地域榜）。
> **v3.17.2（后台移动端修复 + 打印优化 + 成就徽章）升级要点**：**前后端包都要覆盖**（后端新增 `GET /api/milestones` 与 `admin.css` 移动端规则；前端含打印样式与 `/annual` 徽章区）。覆盖两包 → gunicorn「停止 → 启动」；**无迁移、无新依赖**。验证：手机端打开后台各菜单（设置 / 写文章 / 媒体库 / 统计 / MCP 服务等）无横向溢出、写文章面板变单列；浏览器打印预览正文干净（无导航/评论/分享）；`/annual` 页出现「🏅 成就徽章」区。
> **v3.17.1（导航 CSS 选择器转义修复）升级要点**：**纯后端修复**（`app.py` 选择器去引号 + 新增回归测试；`vue-frontend/` 未动，前端包无变化、可不必覆盖）。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn 即生效；**无迁移、无新依赖**。验证：后台 SSR 页（如 `/admin/login`）源码中应含 **`html:not([data-theme=dark])`（无引号）**——若仍是 `html:not([data-theme=&#34;dark&#34;])` 说明未生效（该写法 CSS 非法、深色下顶部会白条）。
> **v3.17.0（深色修复 + 动效/无障碍 + AVIF + 年度回顾 + AI 摘要）升级要点**：**前后端包都要覆盖**（前端含大量新样式/指令/新页面，务必覆盖 `vue-frontend-dist.zip` 并硬刷新；后端新增 `api/review.py`、`api/ai.py`，`utils.py` 渲染升级）。**无新表、无迁移、无新增依赖**。⚠️ `_RENDER_VERSION` 1→2 会让正文缓存整体失效——升级后**首次访问每篇文章会重新渲染一次**（属正常，随后恢复缓存速度）。AVIF：仅当服务器 Pillow 编译了 AVIF 支持时自动生成旁路文件（本机 Pillow 12.3.0 `features.check('avif')=True`），不支持则自动跳过、行为与旧版一致。AI 摘要：复用「游戏收录 → ⚙️ LLM 审计配置」的 Base/Key/Model，无需新配置；结果存 Setting（`ai_summary_<id>`），零表结构变更。验证：后台左下角 v3.17.0、**深色模式顶部不再整条白**、后台表格手机端成卡片可读全文、首页 Bento 概览卡、`/annual` 年度回顾页、文章编辑页「🤖 生成 AI 摘要」按钮、上传图片后同目录出现 `.avif`。
> **v3.16.0（主题中心 + 分享卡重做 + 动态 OG/二维码）升级要点**：**前后端包都要覆盖**。后端：覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」；**无新表、无新列、无 Alembic 迁移**（`theme_center`/`og_image`/`api/og` 全部复用既有 `Setting` 表与 `db.create_all` 自愈），无需 `flask db`；`requirements.txt` 新增 `segno`（二维码），升级后务必重进虚拟环境 `pip install -r requirements.txt` 否则 `/api/qr` 500。前端：覆盖 `vue-frontend-dist.zip` 并硬刷新（主题中心依赖新 `index.html` + 分享面板组件）。新增依赖与目录：`myblog/themes.py`、`myblog/api/theme.py`、`myblog/admin/theme_center.py` + 模板、`myblog/og_image.py`、`myblog/api/og.py`、`myblog/static/og-default.png`，后台 `base.html` 新增「🎨 主题中心」导航。验证：后台左下角 v3.16.0、侧栏出现「🎨 主题中心」（实时预览网格 + 自定义 JSON 导入/导出）、文章页「📤 分享到…」SVG 面板、`/api/og/post/<slug>.png` 返回 1200×630 分享卡、`/api/qr` 返回站点二维码 SVG。无新增环境变量、无新 Nginx 规则。
> **v3.15.0（标签治理 / 分享卡片 / 游戏平台）升级要点**：**前后端包都要覆盖**。后端：覆盖 `myblog-backend.zip` → gunicorn「停止 → 启动」；**新表 `game` 启动时 `create_all` 自愈创建，无需 `flask db`**；无新增环境变量、无新 Nginx 规则。内置游戏：在站点目录执行 `python tools/seed_games.py` 一键收录《就是按一下》《就是开车》（等同后台上传的安全链路），也可在后台「🎮 游戏收录」手动上传 zip。前端：覆盖 `vue-frontend-dist.zip` 并硬刷新（/games 系列路由依赖新 index.html）。后台 LLM 审计为可选：需在「游戏收录 → ⚙️ LLM 审计配置」填 OpenAI 兼容 Base/Model/Key。验证：后台左下角 v3.15.0、侧栏「🎮 游戏收录」、前台「🎮 游戏」两枚内置游戏卡、`/games/dev` 文档页。
> **v3.14.0（写作后台大升级）升级要点**：**纯后端改动**——本轮全部代码在 `myblog/` 包内（admin 视图 / 后台模板 / `admin.css` / `script.js`），**前端产物无变化**（`vue-frontend/` 未动，无需覆盖 `vue-frontend-dist.zip`）。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn 即生效；**无 DB 迁移**，无需 `flask db`；无新增环境变量、无新 Nginx 配置。验证：后台左下角版本号 = v3.14.0；左侧出现「📄 文章管理」（原「我的文章」升级为全站管理）与「🖼️ 媒体库」；进「写新文章」可见工具栏 / 分屏预览；编辑未发布草稿可「🔗 复制未发布预览链接」（免登录，24h 有效）。后台静态资源已带版本参数自动破缓存，必要时硬刷新一次。

---

## MCP 配置指南（两个端点一次配好：只读 `/mcp` ＋ 写能力 `/mcp-write`）

> 本节是**统一操作手册**；两端各自的来龙去脉（引入背景与安全设计）见仓库根目录 `CHANGELOG.md` 的 v3.10.0 / v3.12.2 条目。
> 两个端点**完全独立**（各自 token / 各自开关 / 互不影响），但环境变量、Nginx、AI 助手接入可以**一次配完**。
>
> **v3.13.0 起：以下大部分操作可在后台点按钮完成**——登录后台 → 左侧「系统设置」→「🔌 MCP 服务」：
> - 两个内置端点**一键启停**（「停止」= 端点对外 404 不暴露存在，即时生效无需重启），token 只显示掩码（本体仍在宝塔环境变量）；
> - 可**登记外部 MCP 服务**（名称 / URL / Header / Token，token Fernet 加密落库，库里无明文），统一查看、启停、编辑、删除；
> - 每个服务都能生成 **「AI 脱敏接入指令」一键复制**：**脱敏版**含完整连接步骤但 token 用占位符（可放心转发给 AI，由它引导你填 token）；**完整版**（页面点「显示完整指令」）含真实 token，AI 拿到即可直接写好 mcp.json / 完成安装——完整版每次查看都记「🧾 操作日志」。
>
> 本节保留手工操作口径，作为无后台 / 脚本化部署时的对照。

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

