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
- **数据备份与异地容灾**（v3.3.0）：后台「💾 数据备份」一键备份/下载/恢复（超管 + 二次确认 + 审计），备份包内嵌 SHA256 manifest 完整性校验 + 路径白名单防穿越；可插拔异地目的地（本地 / OSS·COS·S3 / 备用机 SCP / 云盘 WebDAV），宝塔定时任务 `backup.sh` 每日自动备份
- **备份配置后台化**（v3.4.0）：新增后台「⚙️ 备份配置」页（`/admin/backup-settings`，超管专属）——本地目录/保留天数/OSS/SCP/WebDAV 目的地与密钥全部后台直接填写，保存即生效，无需再配环境变量。**密钥（OSS SecretKey / WebDAV 密码 / SCP 私钥路径）用 SECRET_KEY 派生的 Fernet 密钥（PBKDF2）加密后存库，页面只回显掩码，绝不落明文**。读取优先级：非密钥字段「后台配置优先 → 环境变量兜底」；密钥字段「环境变量优先 → 后台加密值兜底」——老环境变量配置无需迁移。定时任务 `backup.sh`（CLI）自动读后台配置
- **前台视觉升级**（v3.4.1，纯前端）：首页渐变 hero 横幅 + 页面标题主题色装饰条 + 卡片/widget hover 上浮 + 输入框 focus ring + 按钮 ghost/danger 变体 + 分页胶囊 + 热门标签云补齐 + 天气组件暗色适配——前台与后台（inis 风格）统一设计语言；同时修复深色模式下汉堡菜单文字不可读（根因 `applyThemeVars` 内联 style 覆盖暗色变量，已双保险修复：JS 同步导航变量 + CSS 暗色写死浅色）

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

### v3.1.7 修复：CSRF 隐藏域乱码（R14 审计通过）

- **根因**：`csrf_input()` 返回普通字符串的 `<input>` 隐藏域，Jinja2 默认 autoescape 把标签转义成 `&lt;input&gt;` 源码文本，导致登录后台后页面显示乱码。
- **修复**：`csrf_input()` 改用 `markupsafe.Markup` 包装（服务端生成的 HMAC 签名 Token，无用户可控输入），隐藏域以原生 HTML 渲染。所有模板 `{{ csrf_input() }}` 调用一处修复全局生效。
- **验证**：真实渲染验证（隔离临时库 + test_client）——后台 dashboard（`/admin/`）+ 前台登录页（`/login`）均含原生隐藏域、无转义乱码。无新增依赖（markupsafe 为 Flask 自带）。APP_VERSION 升为 v3.1.7（后被 v3.1.8 接续）。


### v3.1.8 修复：后台退出按钮 405（R15 审计通过）

- **根因**：v3.1.6 引入 CSRF 时把后台退出表单改成 POST + 隐藏域，但 `/admin/logout` 路由仍是默认 GET-only → 退出按钮点击报 **405 Method Not Allowed**。
- **修复**：`admin.py` `/admin/logout` 路由改为 `methods=["GET", "POST"]`（POST 带 CSRF Token 退出，GET 兼容旧链接）。全仓库排查为唯一遗漏。
- **验证**：隔离临时库 + test_client 实测退出链路 POST/GET 均 302、退出后后台被重定向。无回归。APP_VERSION 升为 v3.1.8。

### v3.2.0 新增：后台验证码独立设置页 + Pillow 缺失修复（R16 审计通过）

- 后台「🛡️ 验证码设置」（`/admin/captcha-settings`，超管）可单独配置：全局开关、长度（3–8）、干扰强度、排除易混字符、注册/评论/留言各场景独立开关，存 `Setting` 表。
- **根因修复**：`requirements.txt` 补 `Pillow>=10.0.0`（此前遗漏 → 服务器未装时验证码恒降级停用）。升级后需 `pip install Pillow` 并重启。
- 新增 `GET /api/captcha/config`；`/api/captcha` 按场景显隐。APP_VERSION 升为 v3.2.0。

### v3.2.1 修复：前台平板断点（768–1004px）头部竖排（R17 审计通过）

- **背景**：用户反馈前台在视口宽度 `768px ≤ W < 1004px` 时，顶部导航文字变成纵向排布、非常难看。
- **根因**：头部两套响应式断点冲突——`max-width:760px` 收起桌面 nav 走汉堡抽屉，`max-width:768px` 又给头部加 `flex-wrap` 让导航换行堆叠。761–768px 区间桌面 nav 仍显却被强制换行→竖排；769–1004px 区间内联导航 9+ 链接放不下→溢出。
- **修复**：汉堡/抽屉断点 `760px` → `1004px`，平板区间统一走「汉堡 + 抽屉」，桌面内联 nav 仅大屏（>1004px）显示；删除 768px 断点里冲突的头部换行规则。因平板区间桌面 nav 隐藏，原 nav 内语言切换按钮一并消失，已在抽屉底部补等价按钮。
- **验证**：前端 build（dist_v317）通过；纯前端改动无后端变动、无新增安全面（R17 五维 ✅）。APP_VERSION 升为 v3.2.1。

### v3.3.0 新增：数据备份与异地容灾（R18 审计通过）

- **可插拔后端**（`myblog/backup.py`，纯标准库）：local（本地滚动保留）/ oss（对象存储，需 boto3）/ scp（备用机）/ webdav（云盘），各目的地由环境变量独立开关，远程失败只记录不阻断本地。
- **安全**：备份包内嵌 `manifest.json`（每文件 SHA256 + 整包哈希）；`verify()` 路径白名单（`data/`、`static/uploads/`）拒绝 `..`/绝对路径防穿越；密钥只走环境变量，不落库不回显。
- **恢复安全**：CLI 需 `--yes`；后台 `/admin/backup` 需超管 + CSRF + 二次确认 + 恢复前自动快照 + 审计日志，并提示宝塔「停止→启动」。
- **定时**：`myblog/backup.sh` 供宝塔 `0 4 * * *` 定时任务调用。APP_VERSION 升为 v3.3.0。

### v3.3.1 修复：后台「立即更新」CSRF 校验失败（R19 审计通过）

- **背景**：后台「系统设置 → 立即更新」报错「CSRF 校验失败，请刷新页面后重试」。
- **根因**：该按钮用 `fetch()` 发 JSON POST 到 `/api/version/update`，请求头漏带全局 CSRF 要求的 `X-CSRF-Token`（v3.1.6 起所有写接口强制校验会话绑定 token），点击即被拒绝。
- **修复**：`templates/admin/base.html` 的 fetch 请求头补 `'X-CSRF-Token': '{{ csrf_token }}'`（模板上下文本就注入该值）。**单行改动，未把接口加入豁免名单，CSRF 防护完整保留。**
- **验证**：隔离临时库冒烟——带 token 返回 400「未找到更新脚本」（CSRF 放行，本地无 update.sh 属预期）；不带 token 仍 403（防护未失效）。`py_compile` 通过。R19 四维审计全 ✅（详见 `SECURITY_AUDIT.md` 第二十九轮）。APP_VERSION 升为 v3.3.1。

### v3.4.0 新增：备份配置后台化 + 立即备份 500 修复（R20 审计通过）

- **500 修复**：后台「💾 数据备份 → 立即备份一次」此前点击报 500。根因：`admin.py` backup 路由 4 处把审计函数名误写为未定义的 `add_audit`（正确为 `log_audit`），备份文件实际已生成但写审计日志抛 `NameError` → except 再调 `add_audit` → 再次 NameError → 500。已全部修正。
- **备份配置后台化**：新增后台「⚙️ 备份配置」页（`/admin/backup-settings`，超管专属）——本地目录 / 保留天数 / OSS / SCP / WebDAV 目的地与密钥全部后台填写，**保存即生效、无需再配环境变量**。
  - **密钥加密存储**：OSS SecretKey / WebDAV 密码 / SCP 私钥路径用 **SECRET_KEY 派生的 Fernet 密钥（PBKDF2-HMAC-SHA256 固定盐）加密**后存库，页面只回显掩码（`Su****23` 类），**绝不落明文、不回显明文**。
  - **读取优先级**：非密钥字段「后台配置优先 → 环境变量兜底」；密钥字段「环境变量优先 → 后台加密值兜底」——老环境变量配置无需迁移。
  - **定时任务兼容**：`backup.sh`（CLI 无 Flask 上下文）自动读后台配置（sqlite3 直连 Setting 表），保持纯标准库独立运行。
- **需新增依赖**：`cryptography>=41.0.0`（Fernet 必需）。
- **验证**：`py_compile` 全量通过；500 复现修复（POST 200 + 审计写入）；备份配置冒烟 7 项全过（加密落库/掩码回显/合并配置/CLI 独立/密钥环境变量优先）；前端本轮无改动（复用 dist_v317）。R20 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十轮）。APP_VERSION 升为 v3.4.0。

### v3.4.1 前台视觉升级 + 汉堡菜单深色修复（R21 审计通过，纯前端）

- **深色汉堡菜单不可读修复**（用户反馈「深色模式下汉堡菜单文字看不清」）：
  - 根因：`store.js#applyThemeVars()` 用**内联 style** 写死导航变量（--nav-fg 浅色 #555555），内联优先级高于 `[data-theme="dark"]` 的 CSS 变量重定义 → 暗色下抽屉 logo/关闭/导航/操作按钮文字仍是深灰，看不清。
  - 修复① `App.vue#applyTheme()`：切暗色时内联覆盖导航变量为暗色值，切浅色按后台 nav_style 回写；
  - 修复② `global.css`：暗色下抽屉全部文字直接写死浅色（不依赖变量），JS 未执行也兜底可读。
- **前台视觉整体升级**（与后台 inis 风格统一）：
  - 首页渐变 hero 横幅、页面标题主题色装饰条；
  - 文章卡 / 侧边栏 widget（含主题色装饰线）/ 统计大卡 / 系列卡 / 搜索卡 / 留言项：hover 上浮 + 阴影过渡；
  - 输入框全网 focus ring、按钮 ghost/danger/small 变体 + 暗色适配、分页胶囊、登录卡升级；
  - 空态虚线卡片、热门标签云补齐（此前完全无样式）、天气组件暗色适配、评论/留言区明细补齐。
- **验证**：前端构建 `_vite_build15` 成功、`vite preview` HTTP 200；`py_compile` 零后端改动跳过。R21 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十一轮）。APP_VERSION 升为 v3.4.1。

### v3.4.2 修复：一键更新脚本双源互证校验错误（R22 审计通过，脚本修复）

- **故障现象**：后台「立即更新」/ 宝塔终端跑 `bash /www/wwwroot/myblog/update.sh`，在「下载 sha256.txt」后**静默退出(码1)**，日志无 ❌ 行、仅提示「脚本异常退出(码1)，详见 data/update_log.txt」。
- **根因**：`update.sh` / `deploy.sh` 的 `verify_checksum` ②「zip 注释内嵌哈希校验」写成**三向链式比较** `内容区哈希 == 注释内嵌哈希 == 整文件哈希`。而「注释内嵌哈希」是**内容区**（剥离注释）哈希，`sha256.txt` 记录的是**整文件**（含注释）哈希——两者按双源互证设计**故意不等** → 链式比较恒为假 → python3 校验永远失败返回非 0 → 被 `set -e` 静默终止且无 ❌ 日志。
- **修复**：改为「本地剥离 zip 注释重算内容区哈希 == 注释内嵌 SHA256」两源互证（数学正确的双源互证）；命令替换加 `|| true` 兜底，python3 缺失/异常时降级跳过该层，不再炸脚本。
- **验证**：本地双路径闭环——正常发布包 `通过`、篡改包体 `拒绝`；`bash -n` 语法通过；CRLF=0。R22 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十二轮）。
- **⚠️ 升级顺序**：服务器若仍用 v3.4.1（含）之前的 `update.sh` / `deploy.sh`，**必须先覆盖 Release v3.4.2 的 `deploy_scripts_v342fix.zip`** 再跑一键更新，否则新 Release 包会被旧脚本误判「注释不一致」而终止。
- **⚠️ 已知缺陷（v3.4.3 已修复）**：`deploy_scripts_v342fix.zip` 校验段仍用 `sys.exit(0/1)` 传结果，bash 命令替换捕获 stdout 而非退出码 → 正常包必误报。**该包已废弃，改用 v3.4.3 的 `deploy_scripts_v343fix.zip`。**

### v3.4.3 修复：一键更新脚本输出机制（R23 审计通过，脚本修复）

- **故障现象**：v3.4.2 修复版脚本在**正常发布包**上误报「❌ … zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。」
- **根因**：v3.4.2 已把比较改对为两向，但校验段仍用 `sys.exit(0/1)` 传结果。bash 命令替换 `comment_ok=$(python3 -c ...)` 捕获的是 **stdout** 而非退出码，`sys.exit()` 不产生任何 stdout → `comment_ok` 恒为空 → `"" != "0"` → 永远走失败分支 → 正常包也误报。（`gh api` 下载 v3.4.2 真实资产回验：内容区哈希 == 注释内嵌哈希，包本身无问题。）
- **修复**：校验段 Python 改为 `print('OK'/'BAD'/'NO'/'ERR')` + `sys.exit(0)`；bash `case "$comment_ok"` 按内容判断：OK→通过、BAD→终止、NO/ERR/无输出→降级仅靠 sha256.txt 比对。
- **验证**：双路径闭环——正常包 → `OK`、篡改包 → `BAD`；`bash -n` 通过；CRLF=0。R23 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十三轮）。APP_VERSION 升为 v3.4.3。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` 若来自 v3.4.2 及更早 Release，**必须先覆盖 Release v3.4.3 的 `deploy_scripts_v343fix.zip`** 再跑一键更新——**不要用已废弃的 `deploy_scripts_v342fix.zip`**，它对正常包必误报。

### v3.4.4 修复：一键更新解压目录唯一化（R24 审计通过，脚本修复）

- **故障现象**：v3.4.3 更新走到「④ 覆盖后端代码」报 `mkdir: cannot create directory 'backend_extract': File exists` 后退出——`/tmp/llhhy_update/` 残留了历史失败更新的 `backend_extract` 目录。
- **根因**：脚本解压用**固定目录名** `backend_extract` / `frontend_extract`；删除残留失败被 `|| true` 吞掉，`mkdir` 无兜底 + `set -e` → 静默终止。任何一次更新中途失败都会留下半解压目录，下次更新即炸。
- **修复**：解压目录改为**唯一时间戳名** `backend_extract_$TS` / `frontend_extract_$TS`（TS=本次时间戳），彻底免疫残留目录；脚本启动时尽力清理旧残留（`|| true` 不阻断主流程）。
- **验证**：模拟残留目录存在时唯一目录解压后端/前端均成功；`bash -n` 通过；CRLF=0。R24 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十四轮）。APP_VERSION 升为 v3.4.4。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **须覆盖 Release v3.4.4 的 `deploy_scripts_v344fix.zip`**（v3.4.3 及更早脚本在 /tmp 有残留时仍会炸）。已卡住的服务器可先手动 `rm -rf /tmp/llhhy_update /tmp/llhhy_deploy`，或直接换新脚本后重跑（新脚本不依赖清理）。

### v3.4.5 多项后端 bug 修复（R25+R26 审计通过）

- **修复**：① 一键更新覆盖段静默失败修复 + 覆盖后版本号硬校验（R25）；② 评论提交 500——`notify_mentioned` 误贴进 `csrf_input` 死代码导致 `ImportError`，已恢复独立函数（@通知失效 + 评论必 500 自 v3.1.7 潜伏一并修复）；③ 统计埋点 403——`/api/stats/read|visit|search` 加入 CSRF 豁免，恢复访问统计。
- **验证**：`py_compile` 全过；AST + 桩模块实测 `from utils import notify_mentioned` 成功；R25/R26 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十五/三十六轮）。APP_VERSION 升为 v3.4.5。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.5 的 `deploy_scripts_v345fix.zip`**（含覆盖段修复 + 版本校验），并先覆盖脚本再跑一键更新，否则后端不会被真正覆盖。

### v3.4.6 CSRF 多 worker 下 403「抽风」修复 + 一键更新自动重启加固（R27+R28 审计通过）

- **后端修复（R28 · CSRF token 跨 worker 轮换导致 403「抽风」）**：登录用户发评论、后台批量审核/删除评论均间歇性 `403 (Forbidden)`（登录账号评论「总是抽风」）。根因：gunicorn 以 `-w 3`（3 worker）启动，旧 `generate_csrf_token()` 用**进程级 `_CSRF_CACHE`** 判断 token 是否「新鲜」——每个 worker 各持一份缓存，落到不同 worker 会认为「缓存里没有当前 token」从而重新生成并**覆盖 session 里的 token**，前端缓存的 token 随之失效 → 后续 POST 全 403（看哪个 worker 接手，时好时坏）。前端 `ensureCsrfToken()` 仅在 token 为空时拉一次并永久缓存，403 时无自愈。修复：移除 `_CSRF_CACHE`，改为**签名校验复用**——只要 session 中已有「签名有效」（HMAC(SECRET_KEY, `"csrf:"`+raw)）的 token 即直接复用，token 在整段会话内稳定，不再随 worker 切换而轮换；仅当 token 缺失或签名失效时才重新生成。
- **运维脚本加固（R27 · 一键更新自动重启）**：v3.4.5 覆盖已正确，但后端进程不会真正重载，仍需去宝塔「Python项目 → 停止 → 启动」手动重启。根因：旧 `stop_backend` 只 TERM master、没杀干净 worker，残留进程占端口 → 新 gunicorn 因「Address already in use」起不来，自动重启段形同虚设。本轮加固：`stop_backend` 改 `pkill -TERM -f "gunicorn.*$APP_DIR"` 杀光所有 worker + 端口释放检查；`start_backend` 改 `setsid`+`< /dev/null` 彻底脱离脚本会话 + 启动后扫 `gunicorn.log` 致命错误并打印末尾；并修正重启注释（宝塔 `bt` 是交互式菜单，不支持 `bt stop 项目名`）。
- **验证**：`py_compile` 全过；双 worker 共享 session 模拟复用 token 成功、`check_csrf_token` 对合法 / 篡改 / 无格式 / 空 token 判断均正确；`bash -n` 双脚本通过；R27+R28 七维审计全 ✅（详见 `SECURITY_AUDIT.md` 第三十七 / 三十八轮）。APP_VERSION 升为 v3.4.6。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.6 的 `deploy_scripts_v346fix.zip`**（v3.4.5 及更早脚本的自动重启段仍是旧逻辑，覆盖后仍需手动重启）。**务必先手动覆盖脚本再跑一键更新**，即可免除手动重启 + 生效 CSRF 修复。

### v3.4.7 评论者 IP 定位恢复（IP 属地多源兜底 + 防注入 + 自愈）+ 后台筛选表单美化（R29 审计通过）

- **修复①「评论者 IP 定位没了」**：原 `stats.py` 的 IP 属地解析仅依赖 `api.vore.top`（已超时挂掉）与 `ip-api.com`（已 403 被封），二者全挂后 `region` 恒空 → 前台 `📍 属地` 不渲染。改为**国内源优先 + 国际源依次兜底**（pconline → ipwho.is → api.ip.sb → ipinfo.io）；并改「仅缓存成功结果、外部源恢复后自动回填」（修复旧逻辑把失败空值也永久缓存、无法自愈的坑）。
- **加固（严格审计发现并修复）**：新增 `_is_safe_public_ip()` 仅公网 IP 才查外部（排除私网/环回/保留/CGNAT `100.64/10`）杜绝 XFF 伪造与内网外发；`short_region` 补英文/ISO2→中文归一（根治 `UnitedStatesCalifornia` 脏数据、ipinfo 的 `CN` 码误判）；`_RECENT_FAIL` 加 `_FAIL_MAX=5000` 容量护栏防内存无界增长。
- **修复②后台筛选表单美化**：`我的文章`/`仪表盘` 筛选表单卡片化（圆角 + 🔍 图标 + 统一 38px 控件 + accent 焦点环 + 主/ghost 按钮），适配深色模式；样式抽进 `admin.css` 的 `.filter-form` 去内联 style。
- **验证**：`py_compile` 全过；离线桩冒烟 14/14 PASS；R29 七维审计 0 Blocker（详见 `SECURITY_AUDIT.md` 第三十九轮）。APP_VERSION 升为 v3.4.7；前端复用既有 `vue-frontend-dist.zip`。
- **⚠️ 升级顺序（重要）**：服务器 `update.sh` / `deploy.sh` **必须覆盖 Release v3.4.7 的 `deploy_scripts_v347fix.zip`**（沿用 v3.4.6 自动重启加固）再跑一键更新。

### v3.4.8 全量安全审计加固（R30 审计通过 · 3 Blocker + 5 建议全部修复）

- **🔴 后台 4 处模板 JS 上下文存储型 XSS（已修复）**：`users.html`（`{{ u.username }}`）、`subscribers.html`（`{{ s.email }}`）、`backup.html`（`{{ b.file }}`）、`audit_logs.html`（`{{ keep_days }}`）的 `onsubmit="return confirm('...')"` 把用户可控值直接拼进 **JS 单引号字符串**——Jinja 在 HTML 属性上下文 autoescape **不转义单引号 `'`**，任何注册用户可用 `'` 或 `</script>` 构造存储型 XSS，后台一浏览即触发。修复：4 处全部改用 `|tojson` 过滤器（输出 JSON 字符串字面量，天然 JS 上下文安全）；`utils.py` 新增 `js_escape()` 作非模板场景等价备选。
- **🔴 `/api/version/update` 权限收窄（已修复）**：原普通管理员即可触发服务器更新脚本执行 → 收窄为 `is_super`，非超管返回 403。
- **🔴 `/api/version/status` 补鉴权（已修复）**：原完全无鉴权 → 加 `is_super`，未登录/非超管一律 403。
- **🟡 TOCTOU 防重入（已修复）**：新增模块级 `_UPDATE_LOCK` + `_do_version_update()` 锁内原子段，消除「两并发请求各起一个 update.sh」窗口。
- **🟡 XFF 伪造收口（已修复）**：`client_ip()`/`client_key()` 仅采信**合法公网 IP** 的 XFF 首段，否则回退 `remote_addr`——杜绝伪造 IP 绕过限流、刷爆埋点。
- **🟡 限流补齐（已修复）**：stats 三埋点加 `rate_limit`（visit 60/min、read 60/min、search 120/h，超限静默丢弃）；前台 `/login` POST 加 `rate_limit 10次/60s`。
- **🟡 `add_user` 用户名限长（已修复）**：入库前 `username[:40]` 截断（与模型 `String(40)` 一致）。
- **验证**：`py_compile` 全模块通过（`-W error::SyntaxWarning` 无警告）；隔离临时库冒烟 14 项 ALL PASS；R30 全量审计 3 Blocker + 5 建议全部修复（详见 `SECURITY_AUDIT.md` 第四十轮）。APP_VERSION 升为 v3.4.8。
- **🅰️ 升级顺序（本轮调整 · 无需换脚本包）**：R30 **未改动部署脚本**，服务器**可直接跑一键更新**（沿用已在服的 v3.4.7 脚本）；**若更新过程报错再覆盖 Release v3.4.8 的 `deploy_scripts_v348fix.zip`**（正常情况不需要）。

### v3.4.9 修复：评论 IP 属地 GBK 解码乱码（R31 审计通过）

- **解码健壮性修复**：`stats._http_get_json` 原 `decode("utf-8","ignore")` 永不抛错，太平洋 IP 库（GBK）中文被吞成乱码、GBK 兜底分支形同虚设。改为**逐编码严格解码**（utf-8 → gbk，双失败才抛错交多源兜底），根治省份变乱码、城市丢失。
- **历史脏缓存自愈**：新增 `_looks_corrupted()` 启发式检测乱码；缓存命中先判脏，脏则忽略缓存走在线重查并覆盖旧值，新访问即自动自愈（无需手动清库）。
- **验证**：`py_compile` 通过；`smoke_gbk.py` 15/15 ALL GREEN（GBK 全链路 + 脏缓存自愈 + 异步重查）。R31 聚焦审计 0 Blocker。APP_VERSION 升为 v3.4.9；前端无改动。

### v3.5.0 自定义链接后缀 + 5 项功能/修复 + 抽屉毛玻璃美化（R32 审计通过）

- **① 自定义链接后缀（slug）**：编辑/新建文章新增「链接后缀」字段，可手动填中文/英文/数字/下划线/连字符生成短链接（如 `/post/我的笔记`）；留空按标题自动生成。后端 `clean_slug()` 复用 `make_slug()` 清洗并查重，清洗为空回退标题生成，仅影响自己文章 URL，沿用既有鉴权。
- **② 前台模糊搜索修复**：旧守卫 `if ids is not None` 把 FTS5 空结果 `[]` 误判为「有结果」→ 永不走 LIKE 兜底。改为 `if ids:`（`[]`/`None` 均走 LIKE 兜底），无异常路径。
- **③ 分类/标签页前台无文章修复**：后端下发 `{items, name}`，前端 `CategoryView`/`TagView` 原读 `data.posts`（恒 undefined）。改为读 `data.items`，`name` 缺失回退 slug。
- **④ 后台评论单独删除 405 修复**：行内按钮原嵌在批量表单的嵌套 `<form>` 里被浏览器丢弃 → 单删 405。改为行内按钮用 `formaction` 共享外层 `batch-form` 的 CSRF token（单 POST 表单），未新增裸 POST 表单。
- **⑤ 英文窄屏菜单/LOGO 纵向错位修复**：抽屉断点 `1004px` → `1100px`，`.header-inner` 加 `flex-wrap:nowrap; min-width:0`，`.logo` 加 `flex-shrink:0`；`.drawer` 内 `.logo` 加 `flex-shrink:0`。
- **⑥ 前台抽屉毛玻璃圆角美化**：汉堡抽屉改为浮动毛玻璃卡片（`backdrop-filter:blur(20px) saturate(180%)` + 20px 圆角 + 阴影），深色模式同步适配。
- **运维脚本**：新增 `tools/reset_stats.py`（标准库、运维手动）——清空四统计表，执行前 `post` 表预检防误伤他库、自动时间戳备份、默认 `YES` 二次确认。
- **验证**：`py_compile` 全模块通过；前端构建 `_vite_build15` 成功、含毛玻璃 CSS。R32 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十二轮）。APP_VERSION 升为 v3.5.0。
- ⚠️ 升级顺序：R32 未改动部署脚本，服务器**直接跑一键更新**即可（后端 + 前端 `vue-frontend-dist.zip` 一并覆盖）；后端覆盖后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.5.1 英文桌面端菜单换行修复 + 深色抽屉毛玻璃回归修复（R33 审计通过）

- **① 英文桌面端顶部菜单换行修复**：v3.5.0 漏给顶部 inline 导航 `.site-header nav` 加 `nowrap`、且抽屉断点只到 `1100px` → 常见桌面宽（约 1280px）切英文时顶部菜单换行成两行、LOGO 顶乱。本轮给 `.site-header nav` 加 `flex-wrap:nowrap;min-width:0`、`.site-header nav a` 加 `white-space:nowrap`（首子项左间距归零），抽屉断点 `1100px`→`1280px`，顶部 inline 导航全宽度保持单行。
- **② 深色模式抽屉毛玻璃回归修复**：删除遗留的 `[data-theme="dark"] .drawer{background:#1d2025;border-color:#2a2e35}` 不透明覆盖（压死 v3.5.0 毛玻璃）；深色抽屉改由毛玻璃基样式（alpha 背景 + `backdrop-filter` + 浅描边）渲染，仅保留文字色兜底。
- **验证**：`compileall myblog` 无语法错误；前端构建 `_vite_build15` 成功、含 `1280px` 断点 + `nowrap` + `backdrop-filter`。R33 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十三轮）。APP_VERSION 升为 v3.5.1。
- ⚠️ 升级顺序：R33 纯前端改动（外加 `APP_VERSION` 升版本号），服务器**直接跑一键更新**即可；后端覆盖后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.5.2 链接后缀全局模板 + 预制可选/自定义（R34 审计通过）

- **① 链接后缀独立全局设置**：后台「站点设置」新增「🔗 链接后缀规则」区块，统一配置文章 URL 后缀生成规则（存 `Setting` 表 `slug_mode`/`slug_template`）。
- **② 预制 5 模板 + 自定义**：`仅标题`（默认，旧行为一致）/`标题-日期`/`纯 ID`/`日期-标题`/`分类-标题`，另「自定义模板」支持 `{slug}` `{id}` `{date}` `{category}` 占位符混排固定文字。
- **③ 实时预览**：设置页即时预览（只读 GET `/api/slug-preview`）。
- **④ 单篇覆盖 + 全局模板**：编辑页「链接后缀」填了即单篇硬覆盖；留空套用全局模板；老文章标题未变则保持原 slug 不变。默认 `title` 与升级前一致，**零破坏**。
- **验证**：`compileall myblog` 无语法错误；`render_slug_template` 单测 + 临时库 DB 功能测试（6 模式 + 唯一化 `-2/-3`）通过；`settings.html` 渲染通过。R34 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十四轮）。APP_VERSION 升为 v3.5.2。
- ⚠️ 升级顺序：R34 纯后端改动（无 DB 迁移、无前端构建），服务器**直接跑一键更新**即可；后端覆盖后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.6.0 API 解耦重构：api.py 拆分 api/ 包 + 新增 API.md（R35 审计通过）

- **① API 按功能拆包**：`myblog/api.py`（单文件 1312 行 / 53 路由）解耦为 `myblog/api/` 包——`auth` / `site` / `posts` / `stats` / `social` / `series` / `guestbook` / `subscribe` / `notifications` / `system` 十个功能模块 + `common.py`（共享辅助：当前用户/登录/CSRF/序列化）+ `__init__.py`（`api_bp` 聚合导出）。
- **② 零破坏**：`url_prefix="/api"` 不变，全 54 条路由（含 `/api/weather` main 蓝图）与基线快照 **diff 完全一致**；`app.py` 的 `from api import api_bp` 不改照样兼容；CSRF 豁免清单 / 限流 / 鉴权行为全部不变。验证：路由快照对比 + `create_app()` 全应用加载 + GET/POST 行为抽查通过。
- **③ 新增 API.md**：`myblog/API.md` 完整接口文档（通用约定 / 鉴权 / CSRF / 分页 / 限流 / 全端点说明 / 如何新增 API / 错误码速查），方便定制第三方客户端。
- **④ 后续加 API 更简单**：新功能直接往对应模块加路由，或在 `__init__.py` 追加一行新模块导入即可，不再动大文件；共享逻辑一律走 `common.py`，模块间禁止互相 import（防循环依赖）。
- **⑤ 拆包补测修复 6 处跨模块引用缺失**：5 个功能模块对顶层 `stats` 模块的引用（`client_ip` / `cached_region` / `record_*` / `compute_*`）拆包后未导入 → 请求时 `NameError` 500（统计端点 / 评论 / 留言 / 朋友圈 / 友链 / 系列排序）。补 `import stats`（`posts.py` 另补 `User`，`stats.py`/`series.py` 补 `Post`），新增 `smoke_api_pkg.py` 10 项断言全通过。
- **验证**：`compileall` 全模块无语法错误；路由快照 54 条 diff 零差异；`smoke_api_pkg.py` 10/10（含 visit 落库读回、评论/留言/友链写路径）。R35 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十五轮）。APP_VERSION 升为 v3.6.0。
- ⚠️ 升级顺序：R35 纯后端改动（无 DB 迁移、无前端构建），服务器**直接跑一键更新**即可；后端覆盖后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.6.1 修复：编辑文章改链接后缀（slug）保存报 500（R36 审计通过）

- **① 根因**：`admin.py` 的 `edit_post` 第 662 行 `if post.content != content` 引用了**从未赋值的局部变量 `content`**（该缺陷自 v3.0.0 引入版本历史时即存在）→ `NameError` → 500。以前新建文章走 `new_post` 不经过此路径，故长期未触发。
- **② 修复**：627 行先取新内容到局部变量 `content`、保留 `old_content` 旧值后再覆盖；版本历史判断改为 `post.content != old_content`（新 vs 旧，语义才正确）；删除 664/665 死代码。
- **③ 附带修复（前端草稿丢 slug）**：编辑页草稿自动保存 `fields` 数组补 `"slug"`，改链接后缀后刷新页面草稿恢复不再丢 slug。
- **验证**：完整 HTTP 链路复现（改 slug / 改内容 / 无变化保存均 200，修复前改 slug 即 500）；`py_compile` 通过；`smoke_v320.py` 回归通过。R36 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十六轮）。APP_VERSION 升为 v3.6.1。
- ⚠️ 升级顺序：R36 纯后端 + 模板改动（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.7.0 链接后缀（slug）强制全局设置 · 取消单篇手动覆盖（R37 审计通过）

- **① 行为变更**：编辑/新建文章页**移除「链接后缀」输入框**，slug 一律由后台「🔗 链接后缀规则」全局设置（`slug_mode`/`slug_template`）强制生成，作者不再能单篇手写覆盖。
- **② 保留原则**：编辑已有文章时仅标题变化才按全局模板重建 slug；标题未变则保持原 slug 不动（不破坏旧 URL，与 v3.5.2 既有原则一致）。
- **③ 删除死代码**：`clean_slug()`（单篇覆盖专用）已无调用方，随之删除。
- **④ 前端**：`edit_post.html` 删除 slug 输入框，加一行「slug 由后台全局设置自动生成」提示；草稿自动保存 `fields` 数组移除 `slug`。
- **⑤ 验证**：新增 `smoke_v370.py`（10 项断言全通过）；`py_compile` 通过。R37 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十七轮）。APP_VERSION 升为 v3.7.0。
- ⚠️ 升级顺序：R37 纯后端 + 模板改动（无 DB 迁移、无前端构建，前端沿用 `_vite_build15`），服务器**直接跑一键更新**即可；覆盖后端后须宝塔「停止 → 启动」gunicorn 方真正重载。

### v3.7.1 访问统计新增 Bot/爬虫识别（R38 审计通过）

- **① 新增能力**：后台访问统计新增爬虫识别维度，访问记录时从 UA 自动识别 Bot/爬虫并细分搜索引擎/AI/工具/未知四类。
- **② 数据落库**：`VisitLog` 新增 `is_bot`/`bot_name`/`bot_category` 三字段（迁移脚本 `myblog/migrate_visit_log_bot.py`）；`record_visit` 落库、`compute_summary` 新增 `bot_visits`/`human_visits`/`bot_today`/`bot_breakdown`。
- **③ 后台可视化**：统计看板新增「🤖 爬虫访问」占比卡片 + 「🤖 爬虫/Bot 来源排行」。
- **④ 验证**：新增 `smoke_v371.py`（19 项断言全通过）；`py_compile` 通过。R38 七维审计 **0 Blocker，0 高危**（详见 `SECURITY_AUDIT.md` 第四十八轮）。APP_VERSION 升为 v3.7.1。
- ⚠️ 升级顺序：R38 **有 SQLite DB 迁移**（visit_log 加 3 列）。覆盖后端后先跑 `python myblog/migrate_visit_log_bot.py`（或 `BLOG_DB=...`），再宝塔「停止 → 启动」gunicorn；无前端构建改动。升级后后台左下角显示 `v3.7.1`。

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
├── api/            # 前后端分离用的 JSON 接口（/api/*，v3.6.0 起按功能拆分为包）
│   ├── __init__.py # api_bp 聚合导出（from api import api_bp 兼容，url_prefix=/api 不变）
│   ├── common.py   # 共享辅助（当前用户/登录/CSRF/序列化器等）
│   ├── auth.py     # 认证与验证码
│   ├── site.py     # 站点信息/友链/公告
│   ├── posts.py    # 文章/分类/标签/归档/评论/搜索/RSS
│   ├── stats.py    # 访问统计埋点与汇总
│   ├── social.py   # 微动态/圈子/社交账号
│   ├── series.py   # 文章专题
│   ├── guestbook.py # 留言墙
│   ├── subscribe.py # 邮件订阅/退订
│   ├── notifications.py # 站内通知
│   └── system.py   # 版本更新/部署 webhook
├── API.md          # API 接口文档（全部 /api/* 端点，含鉴权与 CSRF 约定）
├── security.py     # 安全响应头 / 图形验证码 / SMTP 密码优先级（v3.1.6 新增）
├── backup.py       # 数据备份与异地容灾（v3.3.0，可插拔：本地/OSS/SCP/WebDAV）
├── backup_settings.py # 备份配置后台化 + 密钥加密（v3.4.0，Fernet/Setting 表）
├── backup.sh       # 宝塔定时任务入口（0 4 * * * 调用 backup.py run）
├── requirements.txt
├── deploy_guide.md # 宝塔部署手册（点按式，含 Nginx 反代配置）
├── SECURITY_AUDIT.md # 安全审计报告（第一~二十九轮，R1-R19）
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

**v3.3.0 数据备份环境变量**（均为可选，不配默认只做本地备份；**密钥只走环境变量，绝不落库、后台不回显**）：
- `BACKUP_DIR`：本地备份目录（默认项目上级 `backups/`）。
- `BACKUP_RETENTION_DAYS`：本地滚动保留天数（默认 `14`）。
- 对象存储（OSS/COS/S3，需服务端 `pip install boto3`）：`BACKUP_OSS_BUCKET` / `BACKUP_OSS_REGION` / `BACKUP_OSS_ENDPOINT` / `BACKUP_OSS_KEY` / `BACKUP_OSS_SECRET` / `BACKUP_OSS_PREFIX`（默认 `backups`）。
- 备用机 SCP（需系统 scp + SSH 互信或私钥）：`BACKUP_SCP_HOST`（`user@host`）/ `BACKUP_SCP_DIR`（默认 `~/blog_backups`）/ `BACKUP_SCP_PORT`（默认 `22`）/ `BACKUP_SCP_KEY`。
- 云盘 WebDAV（坚果云/Nextcloud/群晖，需系统 curl）：`BACKUP_WEBDAV_URL` / `BACKUP_WEBDAV_USER` / `BACKUP_WEBDAV_PASS`。
- 定时任务：宝塔「计划任务 → Shell 脚本」配 `0 4 * * * bash /www/wwwroot/myblog/backup.sh`。

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
- **升级 v3.1.6+ 后所有用户都要重新登录**：`session_version` 会话版本机制启动生效，旧会话全部失效（预期安全行为，登录一次即可）。
- **登录后台后页面显示 `<input type="hidden" name="csrf_token" ...>` 源码乱码**：v3.1.6 的 `csrf_input()` 返回普通字符串被 Jinja2 autoescape 转义导致。**升级 v3.1.7 即可修复**（改用 Markup 原生渲染隐藏域；v3.1.8 又修复了后台退出按钮 405）；不想升级的话，可在服务器手动把 `myblog/utils.py` 的 `csrf_input()` 返回值改成 `Markup(...)` 并重启项目。
- **评论 IP 属地显示乱码（如「㽭ʡ」、省份变乱码 / 城市为空）**：v3.4.9 已修复。根因是 IP 属地解析（`stats.py`）对太平洋 IP 库（GBK 编码）用了 `utf-8` 静默吞字符导致乱码；v3.4.9 改为「utf-8→gbk 严格解码兜底」并新增历史脏缓存自愈（新访问触发重查自动覆盖，**无需手动清库**）。升级后看后台左下角版本号 `v3.4.9` 即可确认生效。
