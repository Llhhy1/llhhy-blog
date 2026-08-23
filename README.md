# Llhhy Blog · 个人博客系统（Flask + Vue3）

一个前后端分离的个人博客系统：**Flask** 后端（服务端渲染 + JSON API + 管理后台）+ **Vue3** 前端（SPA，构建为静态站）。采用 monorepo 单仓库托管，前后端代码、部署文档、安全报告都在这里。

## 目录结构

```
llhhy-blog/
├── myblog/                    # Flask 后端
│   ├── app.py                 # 应用工厂（启动入口 + 自动迁移 + FTS 初始化）
│   ├── routes.py              # 前台页面 / 登录注册 / 评论 / 天气 / RSS
│   ├── admin.py               # 后台管理（文章/分类/标签/评论/统计/用户/设置/系列/公告/留言墙/订阅者）
│   ├── api.py                 # 前后端分离 JSON 接口（/api/*）
│   ├── models.py              # 数据模型（文章/评论/用户/统计/系列/公告/留言/订阅者等）
│   ├── fts.py                 # SQLite FTS5 全文搜索（不支持时自动降级 LIKE）
│   ├── notify.py              # 新文章推送（Telegram / 企业微信）
│   ├── feed_agg.py            # 友链 RSS 聚合（广场「博客圈」，防 SSRF + DNS 重绑定缓解）
│   ├── stats.py               # 访问统计与 IP 属地解析
│   ├── security.py            # 安全响应头 / 图形验证码 / SMTP 密码优先级（v3.1.6）
│   ├── config.py              # 配置（含 APP_VERSION 版本号自检）
│   ├── templates/             # Jinja2 模板（含后台管理界面）
│   ├── static/                # 样式脚本与上传目录
│   ├── SECURITY_AUDIT.md      # 安全审计报告
│   └── deploy_guide.md        # 宝塔面板部署手册
├── vue-frontend/              # Vue3 前端（Vite 构建）
│   ├── src/                   # 组件与页面
│   └── vite.config.js         # /api 开发代理
└── ROADMAP.md                 # 功能路线图（已全部落地）
```

## 功能特性

- **内容**：文章发布（Markdown + 代码高亮）、**定时发布**（设未来时间，后台线程到点自动公开并推送通知）、**文章置顶**（首页/列表优先展示，📌 标识）、**SEO 独立字段**（每篇可设独立描述/关键词，注入 Open Graph meta）、分类、标签、归档时间线、RSS / sitemap / robots
- **搜索**：SQLite FTS5 全文搜索（构建环境不支持时自动降级 LIKE 模糊匹配）
- **阅读体验**：文章目录 TOC + 阅读进度条、相关文章推荐（标签重合度算法）、热门文章排行、系列/专栏（含上下篇导航）、**图片懒加载 + WebP 自动转码**（大图省流量）、**阅读量防刷**（同 IP 24h 去重，真实阅读数更可信）、**多作者署名**（列表/详情均展示作者）
- **互动**：评论（登录或匿名，IP 属地 + 设备展示）、**嵌套回复**、评论点赞、文章点赞、留言墙（前台独立留言页）
- **社交**：「广场」页——微动态发布/点赞/评论、友链 RSS 聚合流（博客圈）、社交账号墙
- **运营**：邮件订阅（侧边栏订阅框）、站点公告（可关闭横幅）、一键分享 + Open Graph 标签
- **邮件群发**：新文章发布自动通知订阅者，**后台「📧 邮件设置」直接配置 SMTP + 一键测试发送**（v2.4.0+）
- **推送**：新文章发布推送 Telegram / 企业微信（可选，未配置自动跳过）
- **写作辅助**：**草稿自动保存**（写长文时每 5 秒本地缓存，关页不丢、下次自动恢复）、**定时文章一键提前公开**（后台点一下立即发布）
- **后台**：文章列表支持**关键词 + 状态 + 分类筛选与分页**（v2.8.0+）
- **运维**：Webhook 自动部署接口（HMAC 校验，可触发服务器部署脚本自动更新）、**后台一键在线更新**（登录自动检测新版 → 确认 → 静默更新 → 完成提醒刷新，v2.5.0+）、访问统计（区域 TOP10/热读/热搜/时段分布）
- **系统**：三级权限（超管/管理员/普通用户）、前后台统一登录、后台新消息提醒（未读评论/留言角标）、前后台统一明暗主题切换（自动记忆）+ 自定义主题色、版本号自检（后台左下角显示当前版本）
- 设备自适应：手机 / 平板 / 桌面

### v3.0.0 新增（14 项功能）

- **系列目录页 + 阅读进度增强**：系列详情页新增带编号的章节目录（系列 TOC）；前台全局阅读进度条（App.vue）持续可用。
- **字数统计 + 阅读时长**：每篇文章自动统计中文字数 / 词数并估算阅读分钟数，前台详情页展示。
- **评论管理升级**：后台评论列表支持**批量勾选通过 / 删除**；新增**垃圾评论关键词过滤**（站点设置 `comment_spam_keywords`，命中即拒收）。
- **后台操作日志（审计 trail）**：超管可见所有关键后台操作流水（新建/编辑/删除/审批/还原等），支持清空；隐私且只读。
- **文章版本历史 / 回收站**：每次保存文章自动留存历史版本（每篇上限 20）；删除改为**软删除**进入回收站，可一键还原或彻底清除。
- **友情链接申请 + 自助审核**：前台访客自助提交友链申请（限流 + URL 格式校验 + 去重），后台超管审核通过 / 拒绝。
- **标签 / 分类云 + 热门标签页**：新增「热门标签」云（按文章数 ×2 + 阅读量加权排序），前台独立页面。
- **「看了又看」协同过滤**：文章详情页底部推荐从「共同阅读人群」共现 + 标签/分类相似度加权，取代原简单相关推荐。
- **访客趋势图**：后台统计页新增近 30 天 PV / UV 折线趋势图（纯 SVG，无外部依赖）。
- **RSS 按分类 / 标签订阅**：新增 `/api/rss/category/<slug>` 与 `/api/rss/tag/<slug>` 两个订阅源。
- **多语言 / i18n**：前台内置中 / 英双语切换（导航 + 抽屉 + 部分界面文案），后台可设默认语言 `site_lang`。
- **超级管理员隐私空间**：超管可将文章标记为「隐私」，仅本人登录后可见，前台及 API 对其余人一律 404。
- **文章打赏**：仅超管可在每篇文章结尾开关「打赏」并填收款码；前台展示站点默认收款码或文章自定义收款码。

### v3.1.0 新增（审计日志 + 前台大框）

- **后台登录审计日志**：每次后台登录（含成功 / 失败、尝试用户名、来源 IP）均写入审计日志（`action='login'`），可在「操作日志」页查看，支持按成功 / 失败区分。
- **审计日志 30 天保留**：登录日志与操作日志超过 30 天自动清理（原 7 天），避免表无限膨胀；后台清理按钮文案同步更新。
- **审计日志打包下载**：后台「操作日志」页新增「📦 打包下载」按钮，超管可一键导出 **CSV + TXT 压缩包**（内存打包，不落盘）。
- **前台统一大框（视觉对齐后台）**：前台所有内容（公告 / 便签 / 正文 / 页脚）外面包一层大框架（`.site-frame`），视觉风格与后台 `.section-box` 一致，明暗主题跟随。
- **修复**：手机端汉堡菜单不随深色模式切换（根因为 `App.vue` 初始化时强制把主题重置为 light，已改为站点设置加载后据 localStorage 修正 + 系统主题跟随）。

### v3.1.1 修复（抽屉深色模式）

- **修复**：手机端抽屉菜单（`.drawer`）在深色模式下仍为白底的问题。根因为 `[data-theme="dark"]` 段未重定义 `--nav-bg / --nav-fg / --nav-border` 导航变量，抽屉依赖这些变量导致不跟随。已在暗色段重定义三个变量为暗色值，并补充抽屉 hover / 链接背景的暗色适配（R9 审计通过，纯前端 CSS，无安全风险）。

### v3.1.2 部署脚本修复（不含代码变更）

- **修复**：一键更新第⑥步跨用户 `kill` 权限失败（`Operation not permitted`）。`update.sh`/`deploy.sh` 默认 `PROJECT_NAME="myblog"`，重启优先走 `supervisorctl restart myblog`（supervisor 以 www 身份停+起，绕开跨用户 kill）；root 身份运行时自动加 `sudo -u www` 保护。仅更新部署脚本，APP_VERSION 仍为 v3.1.1。

### v3.1.3 抽屉深色补充修复

- **修复**：在 `[data-theme="dark"]` 区块末尾追加 4 条直接写死暗色值的菜单抽屉规则（`.drawer` / `.drawer-nav a` / `.drawer-nav a:hover` / `.drawer-foot`），彻底覆盖旧变量规则，确保深色模式下抽屉视觉稳定（R10，纯前端 CSS，无后端改动）。APP_VERSION 升为 3.1.3。

### v3.1.4 部署脚本根因修复（不含代码变更）

- **修复**：纠正 v3.1.2 的错误假设——宝塔 Python 项目**不是** supervisor 管理，且 gunicorn 属主是 **`mw`（非 `www`）**。重启逻辑改为：宝塔 CLI（`bt stop/start`）优先 → 以 `mw` 身份 `runuser -u mw` 真杀 + 宝塔真实 gunicorn 路径（`/ww/server/pyporject_evn/blog_env/bin/gunicorn -c gunicorn_conf.py`）重新拉起 → 提示手动。彻底消除跨用户 `kill` 权限失败（Operation not permitted）。仅更新部署脚本，APP_VERSION 仍为 v3.1.3。

### v3.1.5 安全加固四项

- **FTS 搜索转义**：全文搜索（搜索建议接口）对用户输入做 FTS5 特殊字符转义，防止语法错误 / 查询异常。
- **密码最小长度 6 → 8**：注册、改密、创建用户、重置密码、首次设置统一为 8 位下限（前后端一致）。
- **审计日志 CSV 公式注入防护**：导出审计日志时，对以 `= + - @` 开头的单元格加前缀，防止 Excel 打开执行恶意公式。
- **一键更新哈希校验**：`update.sh` 下载部署包后比对 Release 附带的 `sha256.txt`，不一致直接终止更新，防中间人篡改 / 下载损坏（由 `package.py` 自动生成校验文件）。APP_VERSION 升为 v3.1.5。

### v3.1.6 安全加固 12 项（全量落地）

- **更新包完整性双重互证**：`package.py` 将各 zip 的「内容区」SHA256（剥离 EOCD 尾注释后的字节）写入 zip 注释，`sha256.txt` 记录含注释的整文件哈希；`update.sh` 同时比对 `sha256.txt` + zip 注释 + 可选 `UPDATE_HMAC_KEY` HMAC 签名——解决「sha256.txt 本身被替换」的漏洞（R13）。注释哈希按内容区计算，不能对含注释的整文件算（注释参与字节后必然对不上）。
- **上传文件魔数校验**：后缀白名单 + PNG / JPG / GIF / WebP 文件头 magic bytes 双重校验，伪造扩展名文件被拒。
- **SMTP 密码不存库**：`SMTP_PASSWORD_ENV_FIRST`（默认 true）——SMTP 密码优先读环境变量，库值仅兜底（数据库泄露时密码不直接暴露）。
- **多 worker 全局限流**：`REDIS_URL` 配置后走 Redis INCR+EXPIRE 全局计数（多 worker 共享）；未配置自动回退内存滑动窗口（单 worker 等价）。
- **CSRF Token 双重防护**：同源校验 + 会话绑定 HMAC Token，全局 POST / PUT / DELETE / PATCH 均校验；前端 apiPost 自动携带 `X-CSRF-Token`，服务端表单自动注入隐藏域。
- **RSS DNS 重绑定缓解**：`feed_agg` 先解析域名再校验解析结果不含内网 / 回环 / 保留地址。
- **弱密码黑名单 + 复杂度开关**：`STRONG_PASSWORD`（黑名单 + 字母/数字）与 `STRONG_PASSWORD_MIXED_CASE`（大小写混合）可独立开关，前后端统一提示。
- **登录防枚举 + 会话踢下线**：失败统一文案 + `LOGIN_DELAY_SECONDS`（默认 1s）统一延迟，消除用户名枚举与时序侧信道；`session_version` 机制 + 超管「踢下线」路由实现「改密码销毁全部旧会话」。
- **审计日志时间筛选与保留**：后台支持 `?from=&to=` 日期筛选；`AUDIT_LOG_DAYS`（默认 90）自动清理超期日志；导出支持筛选。
- **可开关验证码**：`CAPTCHA_ENABLED`（默认 true）——注册 / 评论 / 留言图形验证码，一次性票据防重放，未装 Pillow 自动降级关闭。
- **安全响应头**：`SECURITY_HEADERS`（默认 true）——全局追加 X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy。
- **会话超时 + Webhook 防重放**：`SESSION_IDLE_MINUTES`（默认 60）闲置超时强制重登；Webhook 必须带 `X-Deploy-Time` 时间戳（`WH_REPLAY_WINDOW` 默认 300s 窗口校验）。APP_VERSION 升为 v3.1.6。

### v3.1.7 修复：CSRF 隐藏域乱码（R14 审计通过）

- **根因**：`csrf_input()` 返回普通字符串的 `<input>` 隐藏域，Jinja2 默认 autoescape 把标签转义成 `&lt;input&gt;` 源码文本，导致登录后台后页面显示乱码。
- **修复**：`csrf_input()` 改用 `markupsafe.Markup` 包装（服务端生成的 HMAC 签名 Token，无用户可控输入），隐藏域以原生 HTML 渲染。所有模板 `{{ csrf_input() }}` 调用一处修复全局生效。
- **验证**：真实渲染验证（隔离临时库 + test_client）——后台 dashboard（`/admin/`）+ 前台登录页（`/login`）均含原生隐藏域、无转义乱码。无新增依赖（markupsafe 为 Flask 自带）。APP_VERSION 升为 v3.1.7。

## 快速开始（本地开发）

后端（默认端口 5000）：

```bash
cd myblog
python -m venv venv
pip install -r requirements.txt
# 安全启动前置：必须设置环境变量（缺失则程序拒绝启动）
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export ADMIN_PASSWORD=$(python -c "import secrets;print(secrets.token_hex(16))")
flask --app app init-db
python app.py            # 访问 http://127.0.0.1:5000
```

前端（开发模式，自动代理 `/api` 到后端）：

```bash
cd vue-frontend
npm install
npm run dev              # 访问 http://localhost:5173
```

## 部署上线

完整的宝塔面板点按式部署教程见 [myblog/deploy_guide.md](myblog/deploy_guide.md)：

- **后端**：gunicorn 运行 `myblog`，监听 8686；Nginx 反代 `/api/`、`/admin`、`/static/`；
- **前端**：`vue-frontend` 执行 `npm run build`，把 `dist/` 作为静态站根目录；
- **必配环境变量**：`SECRET_KEY`、`ADMIN_PASSWORD`（宝塔「Python 项目 → 设置 → 环境变量」）；可选安全项见 [deploy_guide.md](myblog/deploy_guide.md)（`REDIS_URL` / `CAPTCHA_ENABLED` / `SESSION_IDLE_MINUTES` / `AUDIT_LOG_DAYS` / `UPDATE_HMAC_KEY` 等，v3.1.6+）。
- **版本确认**：登录后台，左下角显示当前版本（如 v3.1.7），与 [Releases](../../releases) 最新标签比对即可确认部署是否成功。
- **升级（简单方式）**：用仓库根目录 `update.sh` 懒人版脚本（上传后 `bash update.sh`，自动下载最新包 + 备份数据 + 覆盖代码 + **自动重启**），详见部署文档「一键更新脚本」章节。
- **升级（最懒方式，v2.5.0+）**：登录后台自动检测新版本 → 点「立即更新」→ 后台静默完成 → 刷新即用，详见部署文档「后台一键在线更新」章节。
- **升级（手动方式）**：备份 `data/` 与 `static/uploads/` → 覆盖后端/前端 → 「停止」再「启动」项目 → 验证版本号。详见部署文档「版本升级」章节。

## 安全说明

本项目已做开源前安全加固（两轮审计），完整审计报告见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)：

- `SECRET_KEY` / `ADMIN_PASSWORD` 必须通过环境变量注入，**缺失即拒绝启动**，源码不含任何弱默认密钥；
- 会话 Cookie `Secure` / `HttpOnly` / `SameSite=Lax` + 跨站请求同源校验（CSRF 防御）；
- **v3.1.6 起叠加 CSRF Token 双重防护**：会话绑定 HMAC Token 全局校验 POST/PUT/DELETE/PATCH（前端自动携带、服务端表单自动注入）；
- Markdown 渲染经白名单清理（防存储型 XSS）；RSS 聚合抓取同样清洗 + 防 SSRF（只允许 http/https、拦截内网地址 + DNS 重绑定缓解）；
- CORS 默认关闭；登录 / 注册 / 评论 / 留言 / 订阅 / 点赞按 IP 限流（**v3.1.6 起支持 Redis 全局计数**，多 worker 共享）；
- Webhook 部署接口使用 HMAC 恒定时间比较校验密钥，未配置密钥时接口不可用；**v3.1.6 起叠加 `X-Deploy-Time` 时间戳防重放**；
- 推送通知（Telegram / 企业微信）密钥仅走环境变量，异常静默处理，不入库不入仓；
- 图片上传禁用 SVG（防内嵌脚本 XSS）+ **v3.1.6 起文件头魔数校验**；
- **v3.1.6 起**：弱密码黑名单 + 复杂度校验、登录失败统一延迟（防枚举）、`SESSION_IDLE_MINUTES` 会话闲置超时、改密码/踢下线后旧会话全部失效、审计日志自动清理（`AUDIT_LOG_DAYS`）、安全响应头（X-Frame-Options / CSP / X-Content-Type-Options / Referrer-Policy）。
- **修复记录**：第二轮审计修复 Webhook 密钥未从环境变量载入导致恒 403 的缺陷（R1）；第三轮（v2.3.0）修复邮件注入 / 文件句柄泄漏 / 邮箱枚举；v3.1.1（R9）修复手机端抽屉菜单在深色模式下仍为白底的问题，v3.1.3（R10）补充写死暗色值彻底稳定抽屉深色样式（汉堡菜单深色切换已在 v3.1.0 R8 修复）。

## 下载部署包

部署用压缩包（后端 `myblog-backend.zip`、前端 `vue-frontend-dist.zip`）随本仓库 **Releases** 发布：请到 [Releases](../../releases) 下载，解压后按部署文档上传服务器。

## License

[MIT](LICENSE) © 2026 Llhhy
