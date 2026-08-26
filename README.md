# Llhhy Blog · 个人博客系统（Flask + Vue3）

一个前后端分离的个人博客系统：**Flask** 后端（服务端渲染 + JSON API + 管理后台）+ **Vue3** 前端（SPA，构建为静态站）。采用 monorepo 单仓库托管，前后端代码、部署文档、安全报告都在这里。

## 目录结构

```
llhhy-blog/
├── myblog/                    # Flask 后端
│   ├── app.py                 # 应用工厂（启动入口 + 自动迁移 + FTS 初始化）
│   ├── routes.py              # 前台页面 / 登录注册 / 评论 / 天气 / RSS
│   ├── admin.py               # 后台管理（文章/分类/标签/评论/统计/用户/设置/系列/公告/留言墙/订阅者）
│   ├── api/                   # 前后端分离 JSON 接口（/api/*，v3.6.0 起按功能拆分）
│   │   ├── __init__.py        # api_bp 聚合导出
│   │   ├── common.py          # 共享辅助（鉴权/CSRF/序列化）
│   │   ├── auth.py / site.py / posts.py / stats.py / social.py
│   │   ├── series.py / guestbook.py / subscribe.py / notifications.py / system.py
│   │   └── API.md 见 myblog/API.md（全部 /api/* 端点文档）
│   ├── models.py              # 数据模型（文章/评论/用户/统计/系列/公告/留言/订阅者等）
│   ├── fts.py                 # SQLite FTS5 全文搜索（不支持时自动降级 LIKE）
│   ├── notify.py              # 新文章推送（Telegram / 企业微信）
│   ├── feed_agg.py            # 友链 RSS 聚合（广场「博客圈」，防 SSRF + DNS 重绑定缓解）
│   ├── stats.py               # 访问统计与 IP 属地解析
│   ├── backup.py              # 数据备份与异地容灾（v3.3.0，本地/OSS/SCP/WebDAV 可插拔）
│   ├── backup.sh              # 宝塔定时任务入口（每日自动备份）
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
- **运维**：Webhook 自动部署接口（HMAC 校验，可触发服务器部署脚本自动更新）、**后台一键在线更新**（登录自动检测新版 → 确认 → 静默更新 → 完成提醒刷新，v2.5.0+）、访问统计（区域 TOP10/热读/热搜/时段分布）、**数据备份与异地容灾**（v3.3.0：后台「💾 数据备份」一键备份/下载/恢复 · 超管 + 二次确认 + 审计 · 本地/OSS·COS·S3/SCP/WebDAV 可插拔 · 宝塔定时任务自动备份）
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
- **验证**：真实渲染验证（隔离临时库 + test_client）——后台 dashboard（`/admin/`）+ 前台登录页（`/login`）均含原生隐藏域、无转义乱码。无新增依赖（markupsafe 为 Flask 自带）。APP_VERSION 升为 v3.1.7（后被 v3.1.8 接续）。


### v3.1.8 修复：后台退出按钮 405（R15 审计通过）

- **根因**：v3.1.6 引入 CSRF 时把后台退出表单改成 POST + 隐藏域（base.html `method="post"`），但 `/admin/logout` 路由仍是默认 GET-only，POST 请求命中 GET-only 路由 → **405 Method Not Allowed**（点退出按钮失效）。
- **修复**：`admin.py` 的 `/admin/logout` 路由改为 `methods=["GET", "POST"]`——POST 服务退出表单（带 CSRF 隐藏域），GET 保留兼容旧链接。全仓库排查确认这是唯一「表单 POST 但路由未声明 POST」的遗漏。
- **验证**：隔离临时库 + test_client 实测——登录后 POST `/admin/logout` 返回 302 不再 405；GET 兼容 302；退出后访问后台被重定向回登录页。无回归（py_compile + 冒烟 11 组全过）。APP_VERSION 升为 v3.1.8。

### v3.2.0 新增：后台验证码独立设置页 + Pillow 依赖修复（R16 审计通过）

- **后台验证码设置页**：`/admin/captcha-settings`（超管专属）可单独配置——全局开关、验证码长度（3–8）、干扰强度（低/标准/高）、排除易混字符，以及**注册 / 评论 / 留言三个场景各自独立开关**。配置存 `Setting` 表，前端按场景自动显隐验证码框。
- **修复「验证码用不了」根因**：`requirements.txt` 此前漏写 Pillow，导致服务器未装图像库时验证码整块降级停用。现补 `Pillow>=10.0.0`；**服务器升级后务必 `pip install Pillow` 并停止再启动**，验证码图片才会正常出图（设置页也会实时提示 Pillow 是否可用）。
- `api.py` 新增 `GET /api/captcha/config`（返回全局/场景开关 + Pillow 可用性）；`/api/captcha` 图片接口按场景（`from` 参数）判断是否出图。
- **验证**：py_compile + 前端 build（dist_v316）+ `smoke_v320.py` 专项冒烟（默认配置 / 单场景关闭 / 全局关闭 / 长度配置 / 后台页面登录 GET·POST 保存）全部通过。APP_VERSION 升为 v3.2.0。

### v3.2.1 修复：前台平板断点（768–1004px）头部竖排（R17 审计通过）

- **背景**：用户反馈前台在视口宽度 `768px ≤ W < 1004px` 时，顶部导航文字变成纵向排布、非常难看。
- **根因**：头部存在两套互相打架的响应式断点——`max-width:760px` 隐藏桌面 nav 走汉堡抽屉，`max-width:768px` 又给头部加 `flex-wrap` 让导航换行堆叠。在 761–768px 区间桌面 nav 仍显示却被强制换行→竖排；769–1004px 区间内联导航 9+ 链接放不下→溢出/拥挤。
- **修复**：把汉堡/抽屉断点从 `760px` 提到 `1004px`，整个平板区间统一走「汉堡 + 抽屉」干净布局，桌面内联 nav 仅在大屏（>1004px）显示；并删除 768px 断点里与抽屉冲突的头部换行规则，根除竖排。因平板区间桌面 nav 被隐藏，原 nav 内的语言切换按钮一并消失，遂在抽屉底部补一个等价语言切换按钮，保持功能一致。
- **验证**：前端 build（dist_v317）编译通过；纯前端改动，无后端代码变动、无新增安全面（R17 五维全 ✅）。APP_VERSION 升为 v3.2.1。

### v3.3.0 新增：数据备份与异地容灾（R18 审计通过）

- **痛点**：此前只有手动打包，缺自动备份与多目的地容灾；服务器误删 / 被黑 / 磁盘坏道会导致文章与上传图片永久丢失。
- **可插拔后端**（`myblog/backup.py`，纯标准库，零新增依赖）：
  - **local**：本地滚动保留（默认开，`BACKUP_DIR` / `BACKUP_RETENTION_DAYS`，默认 14 天）。
  - **oss**：对象存储（阿里云 OSS / 腾讯云 COS / S3 兼容，需 `boto3`，未装则跳过）。
  - **scp**：`scp` 到备用机（需 SSH 互信或 `BACKUP_SCP_KEY`）。
  - **webdav**：网盘/云盘（坚果云 / Nextcloud / 群晖 Drive，需系统 `curl`）。
  - 各目的地由环境变量**独立开关**；未配置自动跳过；任何远程异常**只记录不阻断**本地落盘（避免备份脚本拖垮发文章主流程）。
- **完整性与安全**：备份包内嵌 `manifest.json`（每文件 SHA256 + 整包哈希）；`verify()` 强制校验且路径白名单（`data/`、`static/uploads/`）拒绝 `..`/绝对路径防穿越；密钥只走环境变量，不落库、不在任何接口回显。
- **恢复安全**：高危操作——CLI 需 `--yes`；后台端点需**超管 + 全局 CSRF + 二次确认(confirm=yes) + 恢复前自动快照 + 写审计日志**，并提示宝塔「停止→启动」使数据库生效。
- **后台页** `/admin/backup`（超管）：远程状态卡、立即备份、列表/下载/恢复（带二次确认）。
- **定时任务**：`myblog/backup.sh` 供宝塔定时任务 `0 4 * * *` 调用（已随包分发）。
- **验证**：`py_compile` 全量通过；隔离临时库 roundtrip 实测（创建 → verify → restore → 快照）全部通过。APP_VERSION 升为 v3.3.0。

### v3.3.1 修复：后台「立即更新」CSRF 校验失败（R19 审计通过）

- **背景**：后台「系统设置 → 立即更新」报错「CSRF 校验失败，请刷新页面后重试」。
- **根因**：该按钮用 `fetch()` 发 JSON POST 到 `/api/version/update`，但请求头漏带全局 CSRF 要求的 `X-CSRF-Token`（v3.1.6 起所有 POST 都必须带会话绑定 token），点击即被 `_csrf_protect()` 拒绝。
- **修复**：`myblog/templates/admin/base.html` 的 fetch 请求头补上 `'X-CSRF-Token': '{{ csrf_token }}'`（模板上下文本就注入该值）。**单行改动，未把该接口加入豁免名单，CSRF 防护完整保留。**
- **验证**：隔离临时库冒烟——带 token 调用返回 400「未找到更新脚本」（CSRF 放行，本地无 update.sh 属预期）；不带 token 仍 403（防护未失效）。`py_compile` 通过。R19 四维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第二十九轮）。APP_VERSION 升为 v3.3.1。

### v3.4.0 新增：备份配置后台化 + 立即备份 500 修复（R20 审计通过）

- **500 修复**：后台「💾 数据备份 → 立即备份一次」此前点击报 500。根因：`admin.py` backup 路由 4 处把审计函数名误写为未定义的 `add_audit`（正确为 `log_audit`），备份文件实际已生成，但写审计日志抛 `NameError` → 再次抛 500。已全部修正，立即备份正常返回 200 并成功写审计。
- **备份配置后台化**（不再依赖环境变量）：新增后台「⚙️ 备份配置」页（`/admin/backup-settings`，超管专属）——本地目录/保留天数/OSS/SCP/WebDAV 目的地与密钥全部在后台直接填写保存。
  - **密钥加密存储**：OSS SecretKey / WebDAV 密码 / SCP 私钥路径用 **SECRET_KEY 派生的 Fernet 密钥加密**（PBKDF2-HMAC-SHA256、固定盐）后存库，页面只回显掩码（`Su****23`），**绝不落明文、绝不回显明文**。
  - **读取优先级**：非密钥「后台配置优先 → 环境变量兜底」；密钥「环境变量优先 → 后台加密值兜底」——老环境变量配置无需迁移。
  - **保存即可生效**：后台保存后当前进程立即生效；`backup.sh` CLI 定时任务（无 Flask 上下文）自动读后台配置（sqlite3 直连 Setting 表，保持纯标准库可独立运行）。
- **需新增依赖**：`cryptography>=41.0.0`（Fernet 加密必需）。**升级后必须 `pip install cryptography` 并「停止→启动」站点**，后台备份配置页的加密保存/解密才可用；不装则旧备份/恢复功能不降级，仅配置页加密保存报错。
- **验证**：`py_compile` 全量通过；500 复现修复（POST 200 + 审计写入）；备份配置冒烟 7 项全过（加密落库无明文/掩码回显/合并配置/CLI 独立/环境变量优先）；前端本轮无改动（复用 dist_v317）。R20 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十轮）。APP_VERSION 升为 v3.4.0。

### v3.4.1 前台视觉升级 + 汉堡菜单深色修复（R21 审计通过，纯前端）

- **深色汉堡菜单不可读修复**（用户反馈「深色模式下汉堡菜单文字看不清」）：
  - 根因：`vue-frontend/src/store.js#applyThemeVars()` 用内联 style 写死导航变量（--nav-fg 浅色 #555555），内联优先级高于 `[data-theme="dark"]` 的 CSS 变量重定义 → 暗色下抽屉 logo/关闭/导航/操作按钮文字仍是深灰，看不清。
  - 修复① `App.vue#applyTheme()`：切暗色时内联覆盖导航变量为暗色值，切浅色按后台 nav_style 回写；修复② `global.css`：暗色下抽屉文字直接写死浅色，JS 未执行也兜底可读（双保险）。
- **前台视觉整体升级**（与后台 inis 风格统一）：首页渐变 hero 横幅、页面标题主题色装饰条、卡片/widget hover 上浮、输入框 focus ring、按钮 ghost/danger 变体、分页胶囊、空态虚线卡片、热门标签云补齐、天气组件暗色适配、评论/留言/登录区明细补齐。
- **部署**：纯前端升级——用新构建产物 `vue-frontend-dist.zip` 覆盖 `/www/wwwroot/vue-frontend`，无需动后端与数据库；CDN/浏览器缓存建议先清再验证。
- **验证**：前端构建 `_vite_build15` 成功、`vite preview` HTTP 200；后端零改动。R21 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十一轮）。APP_VERSION 升为 v3.4.1。

### v3.4.2 一键更新脚本双源互证校验修复（R22 审计通过，脚本修复）

- **故障现象**：用户反馈「一键更新走到下载 sha256.txt 后静默退出(码1)，未执行更新」——日志无 ❌ 行、仅见「脚本异常退出(码1)」+「详见 data/update_log.txt」。
- **根因**：`update.sh` / `deploy.sh` 的 `verify_checksum` ②「zip 注释内嵌哈希校验」写成链式比较 `内容区哈希 == 注释内嵌哈希 == 整文件哈希`，其中「注释内嵌哈希」是**内容区**（剥离注释）哈希、「sha256.txt」记录的是**整文件**（含注释）哈希，二者恒不等 → python3 校验恒失败返回非 0 → 被 `set -e` 静默终止、且无 ❌ 日志。
- **修复**：改为「本地剥离 zip 注释重算内容区哈希 == 注释内嵌 SHA256」两源互证（数学上正确的双源互证）；命令替换加 `|| true` 兜底，python3 缺失/异常时降级为跳过该层，不再因 `set -e` 炸脚本。
- **验证**：本地双路径闭环——正常发布包 `PASS`、中间人篡改包体`REJECT`；`bash -n` 语法通过；CRLF=0。
- **⚠️ 升级顺序**：若服务器仍用 v3.4.1（含）之前的 `update.sh`，必须先覆盖 **Release v3.4.2 的 `deploy_scripts_v342fix.zip`** 再跑一键更新，否则新包会被旧脚本误判终止。
- **验证**：`py_compile` 全量通过（后端本轮零改动）；R22 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十二轮）。
- **⚠️ 已知缺陷（v3.4.3 已修复）**：`deploy_scripts_v342fix.zip` 的校验段仍用 `sys.exit(0/1)` 传结果，而 bash 命令替换 `$(...)` 捕获的是 stdout 而非退出码 → 正常包也误报「zip 注释内嵌 SHA256 与包内容不一致」。**该包已废弃，请使用 v3.4.3 的 `deploy_scripts_v343fix.zip`。**

### v3.4.3 一键更新脚本输出机制修复（R23 审计通过，脚本修复）

- **故障现象**：v3.4.2 修复版脚本在**正常发布包**上误报「❌ myblog-backend.zip 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。」
- **根因**：v3.4.2 虽把比较改对为两向，但仍用 `sys.exit(0/1)` 传校验结果——`sys.exit()` **不产生任何 stdout**，而 bash 命令替换 `comment_ok=$(python3 -c ...)` 捕获的是 stdout → `comment_ok` 恒为空串 → `"" != "0"` → 永远走失败分支 → 正常包也误报。（已用 `gh api` 下载 v3.4.2 真实资产验证：内容区哈希 == 注释内嵌哈希，包本身无问题。）
- **修复**：校验段 Python 改为 `print('OK'/'BAD'/'NO'/'ERR')` + `sys.exit(0)`；bash 用 `case "$comment_ok"` 按内容判断——OK→通过、BAD→终止、NO/ERR/无输出→降级为仅靠 sha256.txt 比对。
- **验证**：双路径闭环——正常包 → `OK`、篡改包 → `BAD`；`bash -n` 通过；CRLF=0。R23 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十三轮）。APP_VERSION 升为 v3.4.3。
- **⚠️ 升级顺序（重要）**：服务器上的 `update.sh` / `deploy.sh` 若来自 v3.4.2 及更早 Release，**必须先覆盖 Release v3.4.3 的 `deploy_scripts_v343fix.zip`**（内含 print 修复）再跑一键更新——**绝对不要用已废弃的 `deploy_scripts_v342fix.zip`**，它对正常包必误报。

### v3.4.4 一键更新解压目录唯一化（R24 审计通过，脚本修复）

- **故障现象**：v3.4.3 更新走到「④ 覆盖后端代码」报 `mkdir: cannot create directory 'backend_extract': File exists` 后退出——`/tmp/llhhy_update/` 残留了历史失败更新的 `backend_extract` 目录。
- **根因**：脚本解压用**固定目录名** `backend_extract` / `frontend_extract`；删除残留失败被 `|| true` 吞掉，`mkdir` 无兜底 + `set -e` → 静默终止。任何一次更新中途失败都会留下半解压目录，下次更新即炸。
- **修复**：解压目录改为**唯一时间戳名** `backend_extract_$TS` / `frontend_extract_$TS`，彻底免疫残留目录；脚本启动时尽力清理旧残留（`|| true` 不阻断）。
- **验证**：模拟残留目录存在时解压仍成功；`bash -n` 通过；CRLF=0。R24 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十四轮）。APP_VERSION 升为 v3.4.4。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **须覆盖 Release v3.4.4 的 `deploy_scripts_v344fix.zip`**（v3.4.3 及更早脚本在 /tmp 有残留时仍会炸）。已卡住的服务器可先手动 `rm -rf /tmp/llhhy_update /tmp/llhhy_deploy`，或直接换新脚本后重跑（新脚本不依赖清理）。

### v3.4.5 多项后端 bug 修复（R25+R26 审计通过）

- **修复内容**：① 一键更新覆盖段「假成功」修复 + 覆盖后版本号硬校验（R25，杜绝后端长期未被真正覆盖）；② **评论提交 500**——`utils.py` 的 `notify_mentioned` 函数体曾被误贴进 `csrf_input` 的 `return` 之后成为死代码，请求时 `ImportError`；已恢复为独立函数（v3.1.7 起潜伏的 @通知失效 + 评论必 500 一并修复）；③ **统计埋点 403**——`/api/stats/read|visit|search` 匿名信标加入 CSRF 豁免，恢复访问统计记录并消除控制台报错。
- **验证**：`py_compile` 全模块通过；AST 校验 `notify_mentioned` 为顶层函数且签名匹配调用点；桩模块实测 `from utils import notify_mentioned` 成功；app.py 豁免三埋点路径已确认。R25/R26 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十五/三十六轮）。APP_VERSION 升为 v3.4.5。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.5 的 `deploy_scripts_v345fix.zip`**（含覆盖段修复 + 版本校验 + 后端 bug 修复）。**务必先手动覆盖脚本再跑一键更新**——否则旧脚本仍会「假成功」不覆盖后端，评论 500 / stats 403 依旧。

### v3.4.6 CSRF 多 worker 下 403「抽风」修复 + 一键更新自动重启加固（R27+R28 审计通过）

- **后端修复（R28 · CSRF token 跨 worker 轮换导致 403「抽风」）**：登录用户发评论、后台批量审核/删除评论均间歇性 `403 (Forbidden)`（登录账号评论「总是抽风」）。根因：gunicorn 以 `-w 3`（3 worker）启动，旧 `generate_csrf_token()` 用**进程级 `_CSRF_CACHE`** 判断 token 是否「新鲜」——每个 worker 各持一份缓存，落到不同 worker 的请求会认为「缓存里没有当前 token」从而重新生成并**覆盖 session 里的 token**，前端缓存的 token 随之失效 → 后续 POST 全 403（看哪个 worker 接手，时好时坏，故称「抽风」）。前端 `ensureCsrfToken()` 仅在 token 为空时拉一次并永久缓存，403 时无自愈，token 一旦失效即永久 403 直到刷新页面。修复：移除 `_CSRF_CACHE`，改为**签名校验复用**——只要 session 中已有「签名有效」（HMAC(SECRET_KEY, `"csrf:"`+raw)，天然防伪造/防跨服务复用）的 token 即直接复用，token 在整段会话内保持稳定，不再随 worker 切换而轮换；仅当 token 缺失或签名失效（被篡改 / SECRET_KEY 已轮换）时才重新生成。
- **运维脚本加固（R27 · 一键更新自动重启）**：v3.4.5 覆盖已正确，但后端进程不会真正重载，仍需去宝塔「Python项目 → 停止 → 启动」手动重启。根因：旧 `stop_backend` 只 TERM master、没杀干净 worker，残留进程占端口 → 新 gunicorn 因「Address already in use」起不来，自动重启段形同虚设。本轮加固：`stop_backend` 改 `pkill -TERM -f "gunicorn.*$APP_DIR"` 杀光所有 worker + 端口释放检查；`start_backend` 改 `setsid`+`< /dev/null` 彻底脱离脚本会话 + 启动后扫 `gunicorn.log` 致命错误并打印末尾；并修正重启注释（宝塔 `bt` 是交互式菜单，不支持 `bt stop 项目名`）。
- **验证**：`py_compile` 全模块通过；双 worker 共享 session 模拟：worker1 生成 T1(new=True)、worker2 直接复用 T1(new=False)，`check_csrf_token` 对合法 / 篡改 / 无格式 / 空 token 判断均正确（ALL PASS）；`bash -n` 双脚本通过；R27+R28 七维审计全 ✅（详见 `myblog/SECURITY_AUDIT.md` 第三十七 / 三十八轮）。APP_VERSION 升为 v3.4.6。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.6 的 `deploy_scripts_v346fix.zip`**（v3.4.5 及更早脚本的自动重启段仍是旧逻辑，覆盖后仍需手动重启）。**务必先手动覆盖脚本再跑一键更新**，即可免除手动重启 + 生效 CSRF 修复。

### v3.4.7 评论者 IP 定位恢复（IP 属地多源兜底 + 防注入 + 自愈）+ 后台筛选表单美化（R29 审计通过）

- **修复①「评论者 IP 定位没了」**：原 `stats.py` 的 IP 属地解析只依赖 `api.vore.top`（已超时挂掉）与 `ip-api.com`（已 403 被封）两个源，二者全挂后所有评论/访问的 `region` 恒为空 → 前台 `📍 {{ c.region }}` 不渲染，像「定位组件没了」。改为**国内源优先 + 国际源依次兜底**（太平洋 pconline → ipwho.is → api.ip.sb → ipinfo.io）；并修复旧逻辑「解析失败(空)也被缓存、永久不重试」的坑——改为**仅缓存成功结果、外部源恢复后自动回填**（含历史空属地评论）。
- **加固（严格审计发现并修复）**：
  - 新增 `_is_safe_public_ip()`：仅合法**公网** IP 才查外部（排除私网/环回/链路本地/保留/CGNAT `100.64/10`），杜绝 XFF 伪造污染与内网 IP 无意义外发；
  - `short_region` 补英文/ISO2→中文归一（如 `CN Guangdong`→`中国广东`、`United States California`→`美国加利福尼亚`），根治海外属地脏数据 `UnitedStatesCalifornia` 与 ipinfo 的 `CN` 码误判；
  - `_RECENT_FAIL` 加 `_FAIL_MAX=5000` 容量护栏，防公网被扫描时内存无界增长。
- **修复②后台筛选表单美化**：`我的文章`/`仪表盘` 的文章筛选表单改为卡片化（圆角容器 + 🔍 搜索图标 + 统一 38px 控件 + accent 焦点环 + 主/ghost 按钮层级），并适配深色模式；样式抽进 `admin.css` 的 `.filter-form`，去掉内联 style。
- **验证**：`py_compile` 全模块通过；离线桩冒烟 14/14 PASS（四解析器 + 中文归一 + 公网/私网/保留/CGNAT 拦截）；R29 七维审计 0 Blocker（详见 `myblog/SECURITY_AUDIT.md` 第三十九轮）。APP_VERSION 升为 v3.4.7；前端复用既有 `vue-frontend-dist.zip`（无前台改动）。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.7 的 `deploy_scripts_v347fix.zip`**（沿用 v3.4.6 自动重启加固）再跑一键更新，方可覆盖后端新代码 + 免除手动重启。

### v3.4.8 全量安全审计加固（R30 审计通过 · 3 Blocker + 5 建议全部修复）

- **🔴 后台 4 处模板 JS 上下文存储型 XSS（已修复）**：`users.html`（用户名）、`subscribers.html`（邮箱）、`backup.html`（备份文件名）、`audit_logs.html`（保留天数）的 `onsubmit="return confirm('...')"` 把用户可控值直接拼进 **JS 单引号字符串**——Jinja 在 HTML 属性上下文 autoescape **不转义单引号 `'`**，任何注册用户可用 `'` 或 `</script>` 构造存储型 XSS，后台一浏览即触发。修复：4 处全改 `|tojson` 过滤器（JSON 字符串字面量天然 JS 上下文安全）；`utils.py` 新增 `js_escape()` 作非模板场景等价备选。
- **🔴 `/api/version/update` 权限收窄（已修复）**：原普通管理员（`is_admin_role`）即可触发服务器 `update.sh` 脚本执行（运维级脚本执行暴露给非超管）→ 收窄为 `is_super`，非超管 403。
- **🔴 `/api/version/status` 补鉴权（已修复）**：原完全无鉴权，任何人可读更新进度并可配合防重入锁制造 409 DoS → 加 `is_super` 鉴权，未登录/非超管一律 403。
- **🟡 TOCTOU 防重入（已修复）**：`version_update` 原是「读 status 文件判断 idle → Popen」非原子，两并发请求可同时读到 idle 各起一个 `update.sh` → 新增模块级 `_UPDATE_LOCK`（threading.Lock）+ 抽出 `_do_version_update()` 在锁内完成「检查+启动」原子段（status 文件保留作跨 worker 双保险），并发触发立即 409。
- **🟡 XFF 伪造收口（已修复）**：`stats.client_ip()` 与 `utils.client_key()` 原无条件取 `X-Forwarded-For` 首段（可伪造任意 IP 绕过注册/登录/评论/点赞限流并刷爆埋点）→ 仅当 XFF 首段为**合法公网 IP**（`ipaddress` + `is_global`，排除私网/环回/保留/CGNAT）才采纳，否则回退 `request.remote_addr`（Nginx 直连 TCP 地址不可伪造）。
- **🟡 限流补齐（已修复）**：三个 stats 埋点（`/api/stats/visit|read|search`）加 `rate_limit`（visit 60次/分钟、read 60次/分钟、search 120次/小时），**超限静默丢弃**不打扰正常访客；前台 `/login` POST 加 `rate_limit 10次/60s` 防暴力破解。
- **🟡 `add_user` 用户名限长（已修复）**：入库前 `username[:40]` 截断 + 超长提示（与模型 `String(40)` 一致）。
- **验证**：`py_compile` 全模块通过（`-W error::SyntaxWarning` 无无效转义警告）；隔离临时库冒烟 `smoke_audit_r30.py` 14 项 ALL PASS（鉴权收窄/埋点限流/登录限流/XFF 收口/模板 tojson 渲染）；R30 全量审计 3 Blocker + 5 建议全部修复（详见 `myblog/SECURITY_AUDIT.md` 第四十轮）。APP_VERSION 升为 v3.4.8。
- **🅰️ 升级顺序（本轮调整 · 无需换脚本包）**：R30 **未改动部署脚本**（`update.sh`/`deploy.sh`），服务器**可直接跑一键更新**（沿用 v3.4.7 已在服脚本）；**若更新过程报错再覆盖 Release v3.4.8 的 `deploy_scripts_v348fix.zip`**（正常情况不需要）。

### v3.4.9 评论 IP 属地 GBK 解码乱码修复（R31 审计通过）
- **根因**：`stats._http_get_json` 用 `decode("utf-8","ignore")`（永不抛错），太平洋 IP 库（GBK）中文被静默吞成乱码，GBK 兜底分支形同虚设 → 前台评论 IP 定位显示 `㽭ʡ` 类乱码。
- **修复**：逐编码严格解码（utf-8→gbk 兜底）+ 新增 `_looks_corrupted()` 历史脏缓存自愈（脏则在线重查覆盖）。
- **验证**：`py_compile` 通过；`smoke_gbk.py` 15/15 ALL GREEN。R31 聚焦审计 0 Blocker。APP_VERSION 升为 v3.4.9；前端无改动，直接跑一键更新即可。

### v3.5.0 自定义链接后缀 + 5 项功能/修复 + 抽屉毛玻璃美化（R32 审计通过）

- **① 自定义链接后缀（slug）**：编辑/新建文章新增「链接后缀」字段，可手动填中文/英文/数字/下划线/连字符生成短链接（如 `/post/我的笔记`）；留空则按标题自动生成。后端 `clean_slug()` 复用 `make_slug()` 清洗并查重（冲突自动 `-2/-3`），清洗为空回退标题生成，绝不写出空 slug 触发路由冲突；仅影响自己文章的 URL，沿用既有 `new_post`/`edit_post` 鉴权。
- **② 前台模糊搜索修复**：根因 FTS5 无匹配返回空列表 `[]` 时，旧守卫 `if ids is not None` 把「空结果」误判为「有结果」，永不走 LIKE 兜底 → 前台搜索恒报「无结果」。改为 `if ids:`（`[]`/`None` 均走 LIKE 兜底），FTS5 不可用（`None`）也已覆盖；无异常路径。
- **③ 分类/标签页前台无文章修复**：根因后端 `posts_by_category`/`posts_by_tag` 下发 `{items, name}`，前端 `CategoryView`/`TagView` 却读 `data.posts`（恒 undefined）→ 永远渲染空。改为读 `data.items`，`name` 缺失时回退 slug。
- **④ 后台评论单独删除 405 修复**：根因行内「删除/通过」按钮嵌在批量表单的嵌套 `<form>` 里，浏览器丢弃内层表单与 CSRF → 单删 405。改为行内按钮用 `formaction` 共享外层 `batch-form` 的 CSRF token（单 POST 表单），未新增任何裸 POST 表单；顺手删掉重复「通过」按钮。
- **⑤ 英文窄屏菜单/LOGO 纵向错位修复**：抽屉断点 `1004px` → `1100px`，`.header-inner` 加 `flex-wrap:nowrap; min-width:0`，`.logo` 加 `flex-shrink:0`，较长英文导航不再换行顶乱布局。
- **⑥ 前台抽屉毛玻璃圆角美化**：汉堡抽屉改为浮动毛玻璃卡片（背景 `rgba(255,255,255,.72)` + `backdrop-filter:blur(20px) saturate(180%)` + 20px 圆角 + 阴影），深色模式同步适配（`rgba(29,32,37,.62)` + 浅色描边）。
- **运维脚本**：新增 `tools/reset_stats.py`（标准库，运维手动用）——清空 `visit_log/read_log/search_log/ip_region` 四表，执行前 `post` 表预检防误伤他库、自动时间戳备份、默认 `YES` 二次确认（`--yes` 跳过），不入库不取密钥。
- **验证**：`py_compile` 全模块通过；前端构建 `_vite_build15` 成功、`vite preview` HTTP 200（含 `backdrop-filter` + `border-radius:20px`）。R32 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十二轮）。APP_VERSION 升为 v3.5.0。
- ⚠️ 升级顺序：R32 **未改动部署脚本**（沿用 v3.4.9 已在服脚本），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

### v3.5.1 英文桌面端菜单换行修复 + 深色抽屉毛玻璃回归修复（R33 审计通过）

- **① 英文桌面端顶部菜单换行修复**：v3.5.0 只给 `.logo`/`.header-inner` 加了 `nowrap`，**漏给顶部 inline 导航 `.site-header nav` 约束**，且抽屉断点只到 `1100px`；导致常见桌面宽度（约 1280px）下切英文时顶部菜单栏因英文文案更宽而换行成两行、LOGO 文字顶乱。本轮给 `.site-header nav` 加 `flex-wrap:nowrap; min-width:0`、`.site-header nav a` 加 `white-space:nowrap` 并把左间距归零首子项，抽屉断点 `1100px` → `1280px`，顶部 inline 导航所有宽度下保持单行。
- **② 深色模式抽屉毛玻璃回归修复**：删除一条遗留的 `[data-theme="dark"] .drawer { background:#1d2025; border-color:#2a2e35 }` 不透明覆盖规则——它压死了 v3.5.0 的毛玻璃（深色抽屉退回不透明深底、丢失 `backdrop-filter`）。现在深色抽屉改由毛玻璃基样式（带 alpha 背景 + `backdrop-filter` + 浅描边）渲染，仅保留文字色兜底保证可读性。
- **验证**：`py_compile` 全模块通过（`compileall` 无语法错误）；前端构建 `_vite_build15` 成功、产物 CSS 含 `max-width:1280px` 断点 + `.logo`/`nav a` 的 `white-space:nowrap` + 抽屉 `backdrop-filter`。R33 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十三轮）。APP_VERSION 升为 v3.5.1。
- ⚠️ 升级顺序：R33 **纯前端改动**（外加 `APP_VERSION` 升版本号），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

### v3.5.2 链接后缀全局模板 + 预制可选/自定义（R34 审计通过）

- **① 链接后缀提升为独立全局设置**：后台「站点设置」新增「🔗 链接后缀规则」区块，把文章 URL 后缀的生成变成可统一配置的全局规则（存 `Setting` 表 `slug_mode`/`slug_template`）。
- **② 预制 5 个模板 + 自定义**：下拉可选 `仅标题`（默认，与旧行为一致）/`标题-日期`/`纯 ID`/`日期-标题`/`分类-标题`，另提供「自定义模板」可填任意串，支持占位符 `{slug}`（标题短名）`{id}`（文章 ID）`{date}`（YYYYMMDD）`{category}`（分类短名），可混排固定文字。
- **③ 实时预览**：设置页带即时预览（新增只读 GET 端点 `/api/slug-preview`，基于示例标题/ID/分类返回生成的 slug）。
- **④ 语义「单篇覆盖 + 全局模板」**：文章编辑页「链接后缀」框仍是**单篇硬覆盖**（填了优先）；留空则套用后台全局模板生成。老文章编辑时若标题未变则保持原 slug 不变（绝不悄悄改旧 URL）。默认 `title` 模式与升级前行为完全一致，**零破坏**。
- **验证**：`py_compile` + `render_slug_template` 单测 + 临时库 DB 功能测试（6 模式 + 唯一化 `-2/-3`）全通过；`settings.html` 渲染验证通过。R34 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十四轮）。APP_VERSION 升为 v3.5.2。
- ⚠️ 升级顺序：R34 **纯后端改动**（无 DB 迁移、无前端构建），服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。

### v3.6.0 API 解耦重构（api.py → api/ 包）+ 新增 API.md（R35 审计通过）

- **① API 按功能拆包**：`myblog/api.py`（单文件 1312 行 / 53 路由）解耦为 `myblog/api/` 包——`auth`/`site`/`posts`/`stats`/`social`/`series`/`guestbook`/`subscribe`/`notifications`/`system` 十个功能模块 + `common.py`（共享辅助）+ `__init__.py`（`api_bp` 聚合导出，`from api import api_bp` 兼容）。
- **② 零破坏**：全 54 条路由与基线快照 `diff` 零差异；CSRF 豁免清单 / 限流 / 鉴权级别全部不变；函数体逐行保真搬移。
- **③ 新增 API.md**：`myblog/API.md` 完整接口文档（通用约定 + 全部端点 + 如何新增 API + 错误码速查）。
- **④ 拆包补测修复 6 处跨模块引用缺失（NameError）**：5 个功能模块对顶层 `stats` 的引用未导入（`stats.client_ip` / `stats.cached_region` / `stats.record_*` / `stats.compute_*`）→ 请求时 500；补 `import stats`（`posts.py` 补 `User`，`stats.py`/`series.py` 补 `Post`），新增 `smoke_api_pkg.py` 10 项断言全通过（含 visit 落库读回、评论/留言/友链写路径）。
- **验证**：`compileall myblog` 无语法错误；路由快照 54 条 diff 零差异；`smoke_api_pkg.py` 10/10。R35 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十五轮）。APP_VERSION 升为 v3.6.0。
- ⚠️ 升级顺序：R35 **纯后端改动**（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.6.0`。

### v3.6.1 修复：编辑文章改链接后缀（slug）保存报 500（R36 审计通过）

- **① 根因**：`admin.py` 的 `edit_post` 第 662 行 `if post.content != content` 引用了**从未赋值的局部变量 `content`**（该缺陷自 v3.0.0 引入版本历史时即存在）→ `NameError` → 500。以前新建文章走 `new_post` 不经过此路径，故长期未触发。
- **② 修复**：627 行先取新内容到局部变量 `content`、保留 `old_content` 旧值后再覆盖；版本历史判断改为 `post.content != old_content`（新 vs 旧，语义才正确）；删除 664/665 死代码。
- **③ 附带修复（前端草稿丢 slug）**：后台编辑页草稿自动保存 `fields` 数组补 `"slug"`，改链接后缀后若不点保存（如刷新页面）草稿恢复不再丢 slug。
- **验证**：完整 HTTP 链路复现（改 slug / 改内容 / 无变化保存均 200，修复前改 slug 即 500）；`py_compile` 通过；`smoke_v320.py` 回归通过。R36 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十六轮）。APP_VERSION 升为 v3.6.1。
- ⚠️ 升级顺序：R36 **纯后端 + 模板改动**（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.6.1`。

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
- **版本确认**：登录后台，左下角显示当前版本（如 v3.1.8），与 [Releases](../../releases) 最新标签比对即可确认部署是否成功。
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
