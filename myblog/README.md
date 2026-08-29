# myblog · Flask 后端

llhhy-blog 的后端：Flask + SQLite，服务端渲染前台 + `/api/*` JSON 接口 + Jinja2 管理后台。

- 当前版本：**v3.10.6**
- 移动端适配（v3.10.6）：修复后台「统计」长标题与公开站「文档页」移动端长文本横向溢出穿模（窄屏统一换行而非挤压版心）。
- 时区：展示统一北京时间（UTC+8），存储仍为 UTC；配置见 `config.TIME_ZONE`（默认 `Asia/Shanghai`，固定不可经环境变量改，避免 UI 内部错位）。
- 根目录 README / 历史版本见仓库根 [README.md](../README.md) 与 [CHANGELOG.md](../CHANGELOG.md)

## 目录结构

```
myblog/
├── app.py          # 应用工厂（自动迁移 + FTS 初始化 + CLI + 首建超管）
├── models.py       # 数据模型（文章/评论/用户/系列/公告/留言/订阅者等）
│                   #   Post.content_html/content_hash = 正文渲染缓存（v3.9.1）
├── routes.py       # 前台页面 / 登录注册 / 评论 / 天气 / RSS
├── admin.py        # 后台管理（内容/评论/统计/用户/设置/系列/公告/留言墙/订阅者）
├── api/            # JSON 接口（/api/*，按功能拆分，见 API.md）
├── mcp_diag.py     # 只读诊断 MCP 端点 /mcp（v3.10.0，见文末说明）
├── plugins/        # 插件系统 v3.9.0（<slug>/ 目录 + signals.py 事件总线）
│                   #   v3.10.0 起仓库不再内置插件，放目录 + 填 ENABLED_PLUGINS 即启用
├── fts.py          # SQLite FTS5 全文搜索（不可用时降级 LIKE）
├── stats.py        # 访问统计与 IP 属地解析
├── backup.py       # 数据备份与异地容灾（本地/OSS/SCP/WebDAV）
├── bot_guard.py    # 反爬限流（默认关闭）
├── security.py     # 安全响应头 / 图形验证码 / CSRF
├── config.py       # 配置（含 APP_VERSION）
├── API.md          # 全部 /api/* 端点文档
├── SECURITY_AUDIT.md  # 安全审计报告
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
