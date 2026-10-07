# myblog · Flask 后端

llhhy-blog 的后端：Flask + SQLite，服务端渲染前台 + `/api/*` JSON 接口 + Jinja2 管理后台。

- 当前版本：**v3.25.16**
- **版本历史一律记在 [CHANGELOG.md](../CHANGELOG.md)，本文件不重复记录。**
- 根目录总览见 [README.md](../README.md)
- 时区：展示统一北京时间（UTC+8），存储仍为 UTC；配置见 `config.TIME_ZONE`
  （默认 `Asia/Shanghai`，固定不可经环境变量改，避免 UI 内部错位）。

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
- **手动升级必须跑迁移**：表结构变更已由 Alembic 承担（不再靠启动自愈）。
  手动覆盖代码后、重启前须执行一次
  `BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app <venv>/bin/python -m flask db upgrade`，
  否则迁移里的索引/列不会落到生产（用一键更新脚本 `update.sh` 的无需手动做）。
  `BLOG_MIGRATE_ONLY=1` 让迁移跳过全部启动副作用，因此**无需提供 `SECRET_KEY`/`ADMIN_PASSWORD`**。
  可用 `flask db heads` 确认当前应为 `c7a2f19b4d30 (head)`。
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
