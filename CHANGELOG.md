# 更新日志（CHANGELOG）

> 本文件承载 **历史版本** 记录。README 只保留最新版本与上手信息。
> 各版本的安全审计结论见 `myblog/SECURITY_AUDIT.md`；功能规划见 `ROADMAP.md`。

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

### v3.7.0 链接后缀（slug）强制全局设置 · 取消单篇手动覆盖（R37 审计通过）

- **① 行为变更（用户可见）**：编辑/新建文章页**移除「链接后缀」输入框**，slug 一律由后台「🔗 链接后缀规则」全局设置（`slug_mode`/`slug_template`）强制生成，作者不再能单篇手写覆盖。后台全局设置页（预制模板 / 自定义占位符）保持不变，仍是唯一定义 slug 形态的地方。
- **② 保留原则**：编辑已有文章时**仅当标题变化才按全局模板重建 slug**；标题未变则保持原 slug 不动——避免悄悄改掉旧 URL 造成外链/SEO 失效（与 v3.5.2 既有原则一致）。
- **③ 删除死代码**：后端 `clean_slug()`（单篇覆盖专用）已无调用方，随之删除，避免误导「仍可单篇覆盖」。
- **④ 前端**：`edit_post.html` 删除 slug 输入框 DOM，并加一行提示「slug 由后台全局设置自动生成」；草稿自动保存 `fields` 数组移除 `slug`（输入框没了，快照不再引用空元素）。
- **⑤ 验证**：新增 `smoke_v370.py`（10 项断言全通过）覆盖 new_post 强制全局、edit_post 标题变/不变、title/id/category-slug 三种模式、前端无 slug 输入框；`py_compile` 通过。R37 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十七轮）。APP_VERSION 升为 v3.7.0。
- ⚠️ 升级顺序：R37 **纯后端 + 模板改动**（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.7.0`。

### v3.7.1 访问统计新增 Bot/爬虫识别（R38 审计通过）

- **① 新增能力**：后台「📊 访问统计」新增**爬虫识别**维度——访问记录时从 User-Agent 自动识别是否为 Bot/爬虫，并细分**搜索引擎(search)/AI(ai)/工具脚本(tool)/未知(unknown)** 四类。
- **② 数据落库**：`VisitLog` 新增 `is_bot`/`bot_name`/`bot_category` 三字段（SQLite 迁移脚本 `myblog/migrate_visit_log_bot.py`，幂等可重跑）；`stats.record_visit` 在记录访问时调用 `detect_bot()` 落库，`compute_summary` 新增 `bot_visits`/`human_visits`/`bot_today`/`bot_breakdown`。
- **③ 后台可视化**：统计看板新增「🤖 爬虫访问」占比卡片 + 「🤖 爬虫/Bot 来源排行」（列出 Googlebot/Bingbot/Baiduspider/GPTBot/CCBot/ClaudeBot 等具体爬虫名与类型标签、次数、占比）。
- **④ 验证**：新增 `smoke_v371.py`（19 项断言全通过）覆盖 detect_bot 五类 UA、record_visit 落库、compute_summary 维度；`py_compile` 通过。R38 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十八轮）。APP_VERSION 升为 v3.7.1。
- ⚠️ 升级顺序：R38 **有 SQLite DB 迁移**（visit_log 加 3 列）。覆盖后端后**先跑迁移** `python myblog/migrate_visit_log_bot.py`（或 `BLOG_DB=/www/wwwroot/你的站点/data/blog.db python myblog/migrate_visit_log_bot.py`），再宝塔「停止 → 启动」gunicorn 方真正重载。无前端构建改动，前端沿用 `_vite_build16`。升级后后台左下角显示 `v3.7.1`。

### v3.8.0 反爬限流保护 + SEO 服务增强（R39 审计通过）

- **① 反爬限流保护（bot_guard，默认关闭）**：基于 v3.7.1 的 Bot 识别，对高频/可疑请求做限流与封禁。搜索引擎（Google/Baidu/Bing 等）默认白名单豁免，不影响 SEO 抓取；坏 Bot（tool/unknown 类，如 AhrefsBot/SemrushBot）走更严格阈值；达到拦截次数阈值才封禁一段时间。新增 `BotBlock` 表记录触发/封禁，后台「🛡️ 反爬限流保护」看板可查看并解封。
- **② SEO 服务增强**：文章页新增 JSON-LD `BlogPosting` 结构化数据 + Open Graph / Twitter Card 元标签；`sitemap.xml` 增强（lastmod/changefreq/priority/封面图）；`robots.txt` 支持后台配置屏蔽指定坏 Bot；RSS/feed 增强（dc:creator 作者 + category 分类）。
- **③ 安全加固**：R39 审计发现并修复 1 处高危——后台解封表单原本缺失 CSRF Token（全局 `_csrf_protect` 对所有非豁免 POST 生效），会导致「解封」按钮必定 403；已补全 `{{ csrf_input() }}`。其余 XSS / 注入 / 越权 / SSRF / 限流 / 资源泄漏维度均通过。
- **④ 验证**：新增 `smoke_v380.py`（18 项断言全通过）覆盖 BotBlock 自动建表、默认关闭放行、搜索引擎豁免、真人/坏 Bot 限流与封禁、解封、已封禁拦截、sitemap/robots/feed/JSON-LD、关闭后放行；`py_compile` 通过。R39 七维审计 **1 高危已修，0 遗留**（详见 `myblog/SECURITY_AUDIT.md` 第四十九轮）。APP_VERSION 升为 v3.8.0。
- ⚠️ 升级顺序：R39 **纯后端 + 模板改动（无 DB 迁移、无前端构建）**。`BotBlock` 新表由 `app.py` 的 `db.create_all()` 在重启时自动创建，无需手工迁移脚本。服务器**直接跑一键更新**即可；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。后台开关位于「⚙️ 站点设置 → 反爬限流」，**默认关闭**，按需开启。升级后后台左下角显示 `v3.8.0`。

### v3.8.1 补丁：修复后台统计页 500（R40）

- **① 根因**：`/admin/stats` 依赖 `visit_log` 表的 bot 三列（`is_bot` / `bot_name` / `bot_category`，v3.7.1 引入）。`db.create_all()` 只建「不存在的表」、不给已存在的表加列；若部署库未跑过 v3.7.1 迁移脚本，`visit_log` 缺这三列，`compute_summary()` 执行 `VisitLog.query.count()`（SQLAlchemy 会包一层全字段子查询）即报 `no such column: visit_log.is_bot` → 后台统计页 500。
- **② 修复**：`app.py` 启动序列新增 `_migrate_visit_log_table()`，每次启动幂等补列（先 PRAGMA 检查、缺才 `ALTER TABLE ... ADD COLUMN`），**彻底取消对 v3.7.1 手动迁移脚本的依赖**——旧库升级自动自愈，无需任何手工步骤。
- **③ 验证**：`_debug_admin500.py` 复现夹具确认「修复前 500 / 修复后 `compute_summary` + `guard_stats` + 三个后台模板（含 bot_guard.html 与 settings 新区块）全部正常」；`smoke_v380.py` 18/18 无回归。APP_VERSION 升为 v3.8.1。
- ⚠️ 升级：纯后端一行迁移逻辑（无新表、无前端构建）。覆盖后端 → 宝塔「停止 → 启动」gunicorn。重启即自动补列，后台不再 500。

### v3.8.2 安全补丁：合并独立复审 PR#1（M1-M4 + L6）

- **背景**：第三方独立安全复审（基于 v3.8.1，完整报告见 `myblog/INDEPENDENT_SECURITY_REVIEW_v3.8.1.md`）发现若干纵深防御缺口，已评审确认属实并合并修复。
- **① M1 SSR 验证码绕过**：`/register`、`/post/<slug>/comment` 两个 SSR 表单路由原本未接入图形验证码（仅 API 路由有），可直连绕过批量注册/刷评论。现与 API 口径统一（`_captcha_fail` fail-closed），模板按需渲染验证码输入框。
- **② M2 XFF 限流伪造绕过**：`client_ip` / `client_key` 原无条件信任 `X-Forwarded-For` 首段（只要公网 IP 即采纳），攻击者可轮换公网 IP 绕过注册/登录/评论/点赞限流。现收口为 `utils.get_client_ip()`：仅当 TCP 直连对端为可信代理（新增 `TRUSTED_PROXIES` 环境变量，留空时安全默认=仅内部地址可信）才采纳 XFF，且取**最右端**真实客户端 IP，丢弃左侧伪造前缀。
- **③ M3 Webhook 部署密钥泄露/重放可关**：`/api/webhook/deploy` 原接受 `?token=` URL 参数（会写入 Nginx/GitHub 投递日志），且 `WH_REPLAY_WINDOW=0` 可完全关闭重放保护。现只接受 `X-Deploy-Token` 请求头，重放窗口强制 ≥30s 且始终启用时间戳校验。
- **④ M4 `/api/weather` 坐标未校验**：`lat`/`lon` 原未经校验直接拼进出站 URL（SSRF/CRLF 面）。现强校验浮点与范围（lat∈[-90,90]、lon∈[-180,180]），非法拒绝或回落默认；出站参数统一 `quote` 转义；新增限流。
- **⑤ L6 `backup.py` 命令注入陷阱**：`_run()` 原保留 `shell=True` 分支（str 命令即走 shell），现强制 list 参数、str 一律 `TypeError` 拒绝。
- **验证**：`smoke_audit_r30.py`（含 XFF 收口 4 项新断言）、`smoke_api_pkg.py`(10)、`smoke_backup_settings.py`(7) 全部通过；`smoke_v380.py` 18/18 无回归（测试夹具补充注册 `api_bp` 以解析验证码图片路由）。APP_VERSION 升为 v3.8.2。
- ⚠️ 部署前置：若站点跑在「remote_addr 为公网 IP」的前置代理/CDN（Cloudflare、云 LB）之后，必须配置 `TRUSTED_PROXIES`（见 `config.py` 注释），否则真实访客 IP 会显示为代理 IP；Nginx 仍建议 `proxy_set_header X-Forwarded-For $remote_addr;`（替换非追加）。

### v3.8.3：SMTP 发送异常可观测性修复（R42）

- **背景**：后台「📧 邮件设置」点「发送测试邮件」报错「错误详情见后端日志」，但日志里查不到 SMTP 详情——原 `_send_smtp()` 静默吞掉异常（`except Exception: return False`）。
- **修复**：异常分支现把完整栈打到 `sys.stderr`，由 gunicorn 写入 `gunicorn.log`（搜 `[SMTP ERROR]` 即可定位）。纯可观测性增强，无新路由/表/模板/前端改动；R42 七维审计 0 遗留。
- **排错**：重部署后填对 SMTP（授权码≠登录密码、465 勾 SSL / 587 取消勾选、出站端口放行），点测试邮件；`tail -n 60 /www/wwwroot/<站点>/gunicorn.log | grep "SMTP ERROR"` 看真实报错（535 认证失败 / 超时 / SSL 握手 / 连接拒绝）。详见 `myblog/deploy_guide.md`「邮件设置」排错块。
- ⚠️ 升级：纯后端一行改动（无 DB 迁移、无前端构建）。覆盖后端 → 宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。升级后后台左下角显示 `v3.8.3`。

### v3.8.4：修复点赞不累加 + 友链 RSS 聚合可观测性（R43）

- **① 点赞不累加（BUG）**：v3.1.6 起后端严格校验所有 POST 的 CSRF Token；前端 `LikeButton.vue`（Vue 文章页）与 `script.js`（SSR 文章页）用裸 `fetch` POST 不带 token，被 403 拦截，服务端 `likes` 从未 +1。更槽的是前端 `catch` 分支还「本地假加一 + 假置已赞」误导用户以为成功。
  - 修复：`LikeButton.vue` 改用项目已有的 `apiPost`（自动带 `X-CSRF-Token`），`script.js` 从 `csrf_input` 隐藏域取 token 带上；移除 catch 假加一逻辑，失败如实报错。
- **② 友链 RSS 不聚合到广场（可观测性）**：`feed_agg.py` / `api/social.py` 原静默吞掉友链抓取异常，现场无迹可查（与 SMTP 同类病）。现把失败原因打到日志，区分四类：
  1. 友链未填 RSS 地址（后台友链管理里补填即可）
  2. RSS 地址未过 SSRF 安全校验（私有地址拦截）
  3. 服务器未装 `feedparser`（日志提示 `pip install feedparser==6.0.11`）
  4. 抓取/解析异常（含具体错误类型与消息，便于定位超时/证书/格式问题）
- **验证**：R43 七维审计 0 遗留（无 XSS/注入/越权/SSRF/CSRF/密钥泄露/资源泄漏）；前端用 `node --check` 校验语法。APP_VERSION 升为 v3.8.4。
- ⚠️ 升级：**含前端构建产物**——必须重新 `vite build` 并打包（见下方构建说明），仅覆盖后端不会生效。宝塔「停止 → 启动」gunicorn 重载前端静态资源。

### v3.8.5：新增 API 文档页面（懒方案）

- **需求**：用户想把 API 文档做成智谱风格（左侧导航 + 右侧内容 + 代码高亮）。
- **懒方案**：复用现有 Vue 前端，新增 `/docs` 路由 → `DocsView.vue`（纯 HTML）+ 左侧导航（硬编码）+ 代码高亮（CDN highlight.js）。
- **优势**：3 个文件改完即可，无需额外框架（VitePress / Docusaurus / VuePress）、无需独立文档站点、无需学习新工具链。
- **访问**：http://your-domain.com/docs
- **内容**：认证 + 通用说明 + 文章 API（列表/详情/点赞）+ 评论 API（列表/创建）+ RSS 订阅 + 博客圈聚合。
- **跳过的**：搜索功能（初期 Ctrl+F 够用）、多语言（初期只中文）、版本管理（初期 git 标签即可）、接口自动生成（初期手写）。
- APP_VERSION 升为 v3.8.5。

### v3.8.6：博客圈自诊断 + 系列热门标签 + 文档页导航（R41–R44 审计通过）

- 博客圈自诊断（`feed_agg._LAST_DIAG` + `/api/feed/circle` 附 `debug` 块，前端直显原因）、系列详情页热门标签云、文档页导航入口（App.vue 桌面 + 抽屉）、文档页内容充实（完整 API 参考 + 二次开发指南）、endpoint 卡片主题色。**含前端构建产物**，须重新 `vite build` + `package.py`。APP_VERSION 升为 v3.8.6。

### v3.8.7：前台移除诊断面板 + 后台全站体检中心 + 文档页 BigModel 风格（R45 审计通过）

- **① 前台移除诊断面板**：`SquareView.vue` 博客圈仅留「↻ 刷新聚合」。**② 后台全站健康体检中心**（`diagnostics.py` · 仅超管）：`feed_diag` 路由（`@super_required` + CSRF）调用 `run_all()` 汇总 9 维 checker（数据库/依赖/配置/备份/SEO/待办/前端构建/存储/RSS 聚合），单点异常降级为 error 不拖垮整页。**③ 文档页 BigModel 风格**：三栏（左导航 + 中内容 + 右「本页目录」TOC 滚动高亮）+ 代码块复制按钮 + 深色模式适配。含前端构建产物。APP_VERSION 升为 v3.8.7。

### v3.8.8：补丁——修复「全站体检」500 与文档页显示不全（R46 审计通过）

- **① 修复后台「🩺 全站体检」打开 500**：根因为 `feed_diag.html` 的 `sec.items` 被 Jinja 解析为 Python `dict.items` 方法（而非数据键），`{% for it in sec.items %}` 报 `TypeError: 'builtin_function_or_method' object is not iterable`。将 `diagnostics.py` 结果数据键 `items` 重命名为 `rows`（彻底规避该陷阱），模板同步改为 `sec.rows`。已本地冒烟验证：超管访问 `/admin/feed-diag` 返回 200 并渲染 9 维仪表盘。
- **② 修复文档页 `/docs` 显示不全**：`.site-frame` 限宽 `max-width:1100px` + `overflow:hidden` 把文档页设计的三栏（1400px）压窄，且 `@media(max-width:1100px){.docs-toc{display:none}}` 直接隐藏右侧「本页目录」、overflow 还破坏了 sticky 侧栏。`App.vue` 给 `/docs` 路由加 `site-frame--wide` 类，`global.css` 对该类放开 `max-width:1500px` 与 `overflow:visible`，文档页恢复完整三栏 + TOC + sticky。`DocsView.vue` 把 highlight.js 的 `<link>/<script>` 从模板移入 `onMounted` 动态幂等加载（避免重复注入与告警）。
- **③ 验证**：后端 `py_compile` 全过；前端 `vite build`（`_vite_build16`）70 模块全部转换成功；隔离临时库 + test_client 冒烟确认 500→200。R46 七维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R46 轮）。
- **④ 部署注意**：**含前端构建产物**，须重新 `vite build` + `package.py` 打包；宝塔「停止 → 启动」gunicorn 重载前端静态资源（restart 不重载）；前端 SPA 由 Nginx 服务，上线后请硬刷新 / 清浏览器与 Nginx 缓存。APP_VERSION 升为 v3.8.8。

### v3.8.9：修复 RSS 订阅失败 + 导航栏「文档」不切英文（R47 审计通过）

- **① 修复 RSS 订阅失败（Nginx 未反代 feed.xml）**：朋友用 RSS 阅读器订阅 `域名/feed.xml` 失败。代码本身健康（本地 `GET /feed.xml` → `200 + application/rss+xml` 合法 RSS），但线上 Nginx 只反代 `/api/`、`/admin`、`/static/` 给 Flask，其余走 Vue SPA 兜底，`/feed.xml`（及 `/sitemap.xml`、`/robots.txt`）被兜底成 `index.html` → 阅读器拿到网页而非 XML。修复：`deploy_guide.md` 补 Nginx 精确反代段（`location = /feed.xml` 等三块反代到 `127.0.0.1:8686`）；`bot_guard.py` 的 `_SKIP_PREFIXES` 增加 `/feed.xml`，防止将来开启反爬限流时误封 RSS 阅读器（与 `/robots.txt`、`/sitemap.xml` 同级）。
- **② 修复前台导航栏「文档」不切英文**：导航栏其他项用 `t('...')` 接自研 i18n（`store.js`），唯独「文档」两项（桌面 + 移动抽屉）硬编码中文，且 `I18N` 词典缺 `docs` key，故切 EN 不变。修复：`store.js` 词典加 `docs`（zh「文档」/ en「Docs」），`App.vue` 两处导航项改用 `{{ t('docs') }}`（已 `vite build _vite_build17`）。
- **③ 验证**：`py_compile` 通过；本地冒烟 `/feed.xml`/`/sitemap.xml`/`/robots.txt` 均正常；前端重建 70 模块通过；R47 审计 0 遗留（含 i18n 维度）。
- **④ 部署注意（强提醒）**：**含前端构建产物**，须覆盖 `vue-frontend-dist.zip` 到 Nginx 根 + 后端覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn + 硬刷新清缓存；**且宝塔 Nginx 必须补三段 feed/sitemap/robots 反代并「重载配置」**，朋友才能订阅、「文档」英文才生效。APP_VERSION 升为 v3.8.9。

### v3.9.0：全栈插件系统（M0/M1/M2/M3）+ 文章目录侧栏插件（R48 审计通过）

- **① 插件系统（全栈，分阶段落地）**：新增 `myblog/plugins/` 动态加载框架——扫描 `ENABLED_PLUGINS`、importlib 加载 `myblog/plugins/<slug>/__init__.py` 的 `register(app, cfg)`，失败隔离（单插件崩溃不拖垮博客）；设计文档 `PLUGIN_SYSTEM.md` 同仓。
- **② 事件总线（M1）**：`myblog/plugins/signals.py` 基于 blinker 定义发布/评论/插件加载等 5 个信号，`emit_*` 助手吞掉订阅者异常。
- **③ 前端槽位 + 路由级启停（M2）**：`App.vue` 新增 nav/sidebar/footer 结构化 `<a>` 槽位（不用 v-html）；后端 `/api/plugins` 暴露槽位声明；新增 `/api/plugins/<slug>/set-enabled`、`/api/plugins/reload` 运行时启停 API（写/删 `disabled` 标记 + 内存覆盖，前端槽位即时生效；路由级启停需重启 gunicorn）。
- **④ 后台插件管理页 + 远程组件（M3）**：后台「运维诊断 → 🧩 插件管理」列出插件状态与启停；html 富文本经 `vue-frontend/src/lib/sanitize.js`（DOMPurify）消毒后渲染；远程组件走同源 `/static/plugins/` 前缀 + `<component :is>`（runtime-only Vue 渲染函数，零改动核心代码）。
- **⑤ 首个真实插件 `article_toc`（文章目录侧栏）**：自包含原生 JS 扫描 `.post-body` 的 h2/h3/h4，以 sticky 形态注入文章页右侧栏顶部、随滚动高亮当前章节、点击平滑滚动、窄屏（≤820px）隐藏（由核心内联 TOC 兜底）。默认启用 `contact_card,article_toc`。
- **验证**：pytest 15 passed；前端 `vite build`（`_vite_build17`）通过；R48 七维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R48 轮）。
- **⚠️ 部署注意（强提醒）**：**含前端构建产物**——须重新 `vite build` + `package.py` 打包；覆盖后端 `myblog-backend.zip` + 前端 `vue-frontend-dist.zip` 后「停止 → 启动」gunicorn（restart 不重载）+ 硬刷新清缓存。新环境变量 `ENABLED_PLUGINS`/`DISABLED_PLUGINS`（紧急关停某插件）见 `myblog/README.md` 与 `deploy_guide.md`。APP_VERSION 升为 v3.9.0。

### v3.9.1：正文渲染缓存 + SQLite WAL（打开文章从「每次重算」到「秒开」· R49 审计通过）

- **① 修复：文章页每次打开都要重算 Markdown（长文 ~87ms）**。根因：`render_markdown()`（Markdown 解析 + bleach 白名单清洗）在**每次请求**都跑一遍——文章详情接口 `/api/post/<slug>`、SSR 首页/文章页/分类/标签/搜索结果（`routes.py::_render()`）无一例外，正文越长越慢，且与内容是否被修改无关。修法：`Post` 新增 `content_html`（渲染结果）+ `content_hash`（指纹）两列，新增 `utils.render_post_html()` 作为唯一渲染出口——命中缓存直接返回，未命中才渲染并写回。指纹 = `sha256(渲染版本号 | 正文 | HTML)`，正文一改指纹即变、缓存自动失效（**无需在保存文章的各处手工清缓存**）；把 HTML 也算进指纹，缓存被意外改坏时会自动重新渲染自愈。实测（1 万字符长文样本）：`87ms → 2.7ms`（约 30×）。
- **② 修复：并发下偶发 `database is locked`**。根因：SQLite 默认 rollback journal，且未设 `busy_timeout`，gunicorn 多 worker 下每个访客都在写（阅读量 + 统计埋点），读写互相阻塞即报错。修法：`app.py::_install_sqlite_pragmas()` 挂 SQLAlchemy `connect` 事件，逐连接执行 `PRAGMA journal_mode=WAL` + `busy_timeout=5000` + `synchronous=NORMAL`（PRAGMA 是连接级的，只设一次不够；非 SQLite 与 `:memory:` 自动跳过）。WAL 让**读不阻塞写、写不阻塞读**。
- **③ 配套（不做则启用 WAL 有数据风险）**：WAL 模式下 `cp blog.db` 会漏掉「已提交但未 checkpoint」的数据，备份静默不完整、恢复可能报 `database disk image is malformed`。故同步改造：① `backup.py` 备份改用 sqlite3 **在线备份 API**（`snapshot_db()`，产出自包含 .db；失败回退直拷），恢复后删除 `-wal`/`-shm` 残留（`drop_wal_sidecars()`，否则旧 WAL 会回放新库）；② `update.sh` / `deploy.sh` 升级前备份优先用 `sqlite3 .backup`，无该命令时退化为 `cp` 且连 `-wal` 一起拷；③ 后台「🩺 全站体检 → 数据库健康」新增 `journal_mode` 与 `busy_timeout` 两行，便于部署后核验。
- **④ 核实（不做无谓改动）**：传言中的「评论 XSS（`_comment()` 返回未消毒原文 + 前端 `v-html`）」经核实为**误判**——`CommentForm.vue` 用 `{{ c.content }}` 文本插值，前台 4 处 `v-html` 的内容均经服务端 `clean_html()` / `escape()` 处理。本次未改动评论链路。
- **验证**：pytest **23 passed**（新增 8 条：缓存写入/命中不重算/正文变更失效/篡改自愈/迁移幂等/WAL PRAGMA 生效/备份快照完整性/清理 WAL 残留）；R49 十维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R49 轮）。
- **⚠️ 部署注意**：**纯后端改动，不含前端构建产物**（前端 dist 无需重建，但发布包仍会整体重打）。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn；升级后请到后台「运维诊断 → 🩺 全站体检 → 数据库健康」确认 `日志模式 journal_mode` 显示 **WAL**、`写锁等待 busy_timeout` 显示 **5000 ms**（若显示 `delete` 说明 `data/` 目录不可写，检查属主与权限）。首次访问文章会触发一次渲染并落缓存，属正常现象。`data/` 目录下新增的 `blog.db-wal`、`blog.db-shm` 是 WAL 正常产物，**请勿手动删除**。APP_VERSION 升为 v3.9.1。

### v3.10.0：只读诊断 MCP + 内置插件全部下线（R50 审计通过）

- **① 新增只读诊断 MCP 端点 `/mcp`**（`myblog/mcp_diag.py`）：把「应用层健康状态」暴露给 AI 助手远程诊断，补的是云主机监控看不到的那一层。实现 MCP Streamable HTTP 传输的**最小子集**（仅 POST、响应单 JSON，不流式），因此无需 ASGI / 新依赖 / 新进程，Flask 直接承载。提供 5 个只读工具：`health_overview`（全站体检 9 维）、`db_status`（journal_mode + 渲染缓存命中率）、`version_info`（版本与迁移一致性）、`recent_errors`（日志尾部，自动打码）、`content_stats`（内容与待办统计）。
- **② 安全是设计出来的，不是靠自觉**（四条都是代码级约束 + 测试兜底）：
  - **认证 fail-closed**：未配置 `MCP_AUTH_TOKEN` 时端点整体返回 401，绝不存在「忘了配就裸奔」；校验用 `hmac.compare_digest` 恒定时间比较防时序爆破。
  - **强制只读**：源码层不含任何写操作，由 `test_mcp_source_is_readonly` 静态审查（禁 commit/add/delete/os.remove/subprocess/eval）守住红线。
  - **日志必脱敏**：`SECRET_KEY`、`password`、`token`、`api_key`、`Bearer xxx` 统一打码。
  - **路径不可遍历**：日志文件只能由环境变量 `MCP_LOG_FILES` 显式指定，不接受客户端传路径。
  - 另：按 IP 限流 60 次/分钟、MCP 规范要求的 Origin 校验（防 DNS 重绑定）、`/mcp` 加入 CSRF 豁免与 bot_guard 白名单（避免反爬误封）。
- **③ 内置插件全部下线**：移除 `contact_card`、`article_toc` 两个插件及 `static/plugins/` 下两个远程组件；**插件框架保留**（加载器、事件总线、后台管理页、前端槽位），`ENABLED_PLUGINS` 默认值改为空。文章目录回退到核心 `PostView.vue` 的内联 TOC（文首显示、不随滚动高亮）。测试改为「临时插件驱动」（改写 plugins 包 `__path__` 指向 tmp 目录），不再依赖任何内置插件。
- **验证**：pytest **31 passed**（新增 11 条 MCP 测试 + 重写 10 条插件框架测试）；发布包冒烟验证 MCP 握手/鉴权/Origin/5 工具/脱敏/错误码全通过；R50 十二维审计 **0 遗留**。
- **⚠️ 部署注意（必做）**：**纯后端改动，前端产物无变化**。① 生成 token 填进宝塔环境变量 `MCP_AUTH_TOKEN`；② **Nginx 必须补 `location = /mcp` 反代**（否则被 Vue SPA 兜底成 index.html），站点强制 HTTPS；③ 建议对 `/mcp` 再加 IP 白名单；④ 上线后按 deploy_guide 的 curl 三步核验（无 token 必须 401）。本机接入：在 `~/.workbuddy/mcp.json` 加一条 `type: "http"` + `headers.Authorization`，再到连接器管理页点「信任」。APP_VERSION 升为 v3.10.0。

### v3.10.1：修复全站体检「前端构建产物」部署态误报（R51 审计通过）

- **改的什么（纯后端，仅 `myblog/diagnostics.py` 一处）**：全站体检的「前端构建产物」维度在**部署态**永远误报 warn（「未找到 `_vite_build*`」）。根因：旧逻辑只查 `vue-frontend/_vite_build*`，但部署布局是 `vue-frontend-dist.zip` 平铺到站点根目录 `/www/wwwroot/vue-frontend/`，直接是 `index.html + assets/`，无 `_vite_build*` 子目录。改为查 **SPA 入口 `index.html` 是否存在**——部署态优先查 `fe_dir/index.html`，回退本地 `_vite_buildN` / `dist` 构建目录，两种布局都能正确识别。友链 RSS 某源解析 0 条属对方源为空（非本博客 bug），不在本轮修复范围。
- **验证**：`py_compile` 通过；用模拟服务器布局（部署态 `vue-frontend/index.html`）验证返回 `ok`、本地无构建返回 `warn`（符合预期）；全量 pytest 预期保持 **31 passed**（本轮未动测试文件）。R51 九维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R51 轮）。
- **⚠️ 部署注意**：**纯后端改动，前端产物无变化**。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效；体检「前端构建产物」维度在部署态应直接显示 `ok`。APP_VERSION 升为 v3.10.1。

### v3.10.2：诊断助手增强——SMTP 误报修复 + 新增 2 维度（R52 审计通过）

- **① 修复「邮件 SMTP」误报（根因）**：`diagnostics.py::check_config()` 原查 `get_setting("smtp_host")`，但后台「邮件设置」存库的 key 实为 `mail_host`（`mail_notify.load_mail_config()` 读取 `mail_host`/`mail_username`/…），且用户是在后台面板配、没用 `SMTP_HOST` 环境变量 → 诊断永远判「未配置」误报 warn。改为 `get_setting("mail_host") or os.environ.get("SMTP_HOST")`，与实际发信配置一致（仅显示 SMTP 服务器域名，不回显账号/密码）。
- **② 新增 2 个诊断维度（9 维 → 11 维）**：
  - **安全配置概览**（`check_security`）：汇总图形验证码 / 评论开关 / 强密码策略(`STRONG_PASSWORD`) / 安全响应头(`SECURITY_HEADERS`) / 接口限流 状态；开着评论却关验证码、或未开安全头/强密码时告警，暴露安全短板。
  - **渲染缓存命中率**（`check_render_cache`）：统计 `Post.content_html` 已缓存占比；全部未缓存则预警（性能退化 + 可能缓存写回失败）。
  - 两个新维度自动纳入 `run_all()`，后台「🩺 全站体检」与 MCP `health_overview` 同步可见，无需改 MCP 代码。
- **验证**：`py_compile` 通过；全量 pytest **31 passed**（无回归）；R52 九维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R52 轮）。
- **⚠️ 部署注意**：**纯后端改动，前端产物无变化**。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效；体检维度由 9 增至 11。APP_VERSION 升为 v3.10.2。

### v3.10.3：新增评论 RSS 订阅源 `/feed/comments`（R53 审计通过）

- **改的什么**：用户访问 `/feed/comments/` 被 Nginx SPA 兜底返主界面——根因是该路由博客从未实现（只有文章 feed `/feed.xml`）。本次在 `routes.py` 新增 `comments_feed` 路由（`/feed/comments` + `/feed/comments/`），输出 RSS 2.0：取最近 50 条「`approved=True` 且所属文章已发布」的评论，每项含文章链接锚点 `#comment-<id>`、评论摘要、作者；评论内容/作者/文章标题全部 `escape` 转义防 XSS。同步：① `bot_guard._SKIP_PREFIXES` 加 `/feed/comments`，避免开启反爬后 RSS 阅读器被限流/封禁；② `diagnostics.check_seo` 路由存在性检查加 `/feed/comments`，防止未来 Nginx 反代漏配导致再次返主界面。
- **验证**：`py_compile` 通过 + 本地冒烟测试（临时 sqlite + `test_client` 验证 `/feed/comments/` 与 `/feed/comments` 均返回 200 + `application/rss+xml`，`<item>` 存在、`<script>` 转义为 `&lt;script&gt;`、锚点正确）；R53 审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R53 轮）；pytest **31 passed** 保持。
- **⚠️ 部署注意**：**纯后端改动，前端产物无变化**。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效；评论订阅源 `https://你的域名/feed/comments/` 即可被 RSS 阅读器订阅。APP_VERSION 升为 v3.10.3。

### v3.10.4 修复：博客圈 RSS 卡死（R54 审计通过）

- **修复**：后台点「强制刷新聚合」即触发 502/罢工。根因：`feed_agg.get_circle_feed` 抓友链 RSS 时 `feedparser.parse` 默认**无 socket 超时**，单个不可达源（如被墙的外站 hedelei）会让 worker 永久挂起、拖垮整站。改为抓取前 `socket.setdefaulttimeout(8)`（取 `current_app.config["FEED_FETCH_TIMEOUT"]`，环境变量 `FEED_FETCH_TIMEOUT` 可覆盖，`try/finally` 还原），坏源超时被 `except` 捕获标记 `skipped/error`、**不再无限挂起**。同时：① `diagnostics.check_feed_agg` 改**实时读库**计数，消除多 gunicorn worker 下内存快照滞后（填了 RSS 仍长时间误报「没有任何友链填写 RSS」）；② `admin.set_link_rss` 保存后**软校验** RSS 可达性（填错 `/feed/` 这类路径立即 warning，保存照常）。纯后端改动，**无需 vite build**。
- **验证**：`py_compile` 通过（feed_agg/diagnostics/admin/config 四文件）；R54 九维审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R54 轮）；pytest **31 passed** 保持。
- **⚠️ 部署注意**：**纯后端改动，前端产物无变化**。覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效。若此前因强制刷新罢工，先「停止 → 启动」恢复；后台「友链管理」建议先清空 `hedelei` 的 RSS（避开被墙源），保留自身 `https://www.llhhy.cn/feed.xml`（同服务器秒回）；恢复后「诊断助手」点「强制刷新聚合」验证博客圈出文章、`feed_agg` 转 ok。APP_VERSION 升为 v3.10.4。
