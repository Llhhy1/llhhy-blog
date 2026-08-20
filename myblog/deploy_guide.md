# 博客上线部署手册（宝塔面板 · Debian 13 示例）

> 本手册以 **宝塔面板 + Debian 13** 为例编写，各版本菜单名称、按钮位置大同小异，照着点即可，全程**不需要 SSH、不需要装 Node**。

## 0. 部署前准备

| 需要文件 | 在你自己电脑上 | 说明 |
|---|---|---|
| `myblog-backend.zip` | ✅ 已有 | 后端 + 管理后台，约 69KB |
| `vue-frontend-dist.zip` | ✅ 已有 | 前端构建产物，约 56KB，上传解压即网站根目录 |

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
   > 可选：`COOKIE_SECURE=true`（HTTPS 部署推荐）、`BLOG_OPEN_REGISTER=false`（关闭公开注册）、`CORS_ORIGIN`（前后端分离时的前端域名列表，一般留空即可）。

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
   - 新密码：至少 6 位的强密码；
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
| 首页 | `https://你的域名/` | 文章列表、侧边栏、天气组件 |
| 文章页 | `https://你的域名/post/xxx` | 打开文章，**直接刷新不 404** |
| 登录/注册 | `https://你的域名/login`、`/register` | 页面正常，可注册 |
| 后台 | `https://你的域名/admin` | 用新账号登录进仪表盘 |
| RSS | `https://你的域名/feed.xml` | 显示 XML |
| API | `https://你的域名/api/site` | 返回 JSON |

---

## 日常维护

- **写文章**：`/admin` → 写新文章（Markdown，可插图、设封面、标签、分类）。
- **改后端代码**：改 `myblog/` 下文件后，到「网站 → Python项目」对该项目点 **「重启」**。
- **改后台样式（admin.css）**：改完上传后**必须重启项目**（版本戳按 mtime 变化，重启后才刷新），浏览器**强刷**（Ctrl+F5）即可看到新样式，不用手动清缓存。
- **改前端**：以后修改 `vue-frontend` 源码后**本地重新 `npm run build`**（不构建就上传等于没改），把新的 `index.html` + `assets/` 覆盖上传即可（**无需重启**，记得强刷浏览器）。
- **看后端日志**：「网站 → Python项目」→ 项目右侧 **「日志」**。
- **备份（重要）**：定期下载这两个：
  - `/www/wwwroot/myblog/data/blog.db`（全部数据：文章、评论、用户、设置、点赞、访问统计）
  - `/www/wwwroot/myblog/static/uploads/`（上传的图片）
- **恢复**：把 `blog.db` 传回 `myblog/data/`，重启 Python 项目即可。

> ⚠️ **数据库保护说明**：部署包 `myblog-backend.zip` **不包含 `data/` 目录**，解压覆盖不会动你服务器上已有的 `blog.db`（文章/评论/设置都安全保留）。
> 新增的统计表（`visit_log` / `read_log` / `search_log` / `ip_region`）在项目**重启时自动创建**，无需手动建表。

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
