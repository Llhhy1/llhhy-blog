# Llhhy Blog · 个人博客系统（Flask + Vue3）

前后端分离的个人博客：**Flask** 后端（SSR + JSON API + 管理后台）+ **Vue3** 前端（SPA）。单仓库托管前后端代码、部署文档与安全报告。

- 当前版本：**v3.17.3**
- **游戏平台（v3.15.0）**：前台「🎮 游戏」卡片厅 + 沙箱内播放（`iframe sandbox` + CSP，拿不到本站 Cookie/登录态/API，禁外联）；后台「游戏收录」上传 zip → 安全解包 + 静态扫描 → 审核上架，可配置 OpenAI 兼容大模型做代码安全审计（Key 加密）；内置官方《就是按一下》《就是开车》两枚荒谬马拉松；开发者接入文档 `/games/dev`。
- **标签治理（v3.15.0）**：保存文章自动去重（中英文逗号/顿号/大小写/空白变体归一复用）、自动清理 0 使用标签；后台一键整理（合并重复 + 清理未使用）。
- **分享卡片（v3.15.0）**：站点级 OG/twitter meta + 文章页动态 OG（绝对图址 / 无封面自动回退），微信/QQ 分享不再只是裸链接。
- **主题中心（v3.16.0）**：后台「🎨 主题中心」——14 套预设主题包（OKLCH 感知色彩空间，亮色单源 / 暗色自动推导），实时预览网格 + 自定义 JSON 导入/导出，一键应用全站整体换肤（前后台共用同一套 token）；写操作仅超管 + 全局 CSRF，无 DB 迁移。
- **分享卡重做（v3.16.0）**：文章页 SVG 图标分享面板（微博 / QQ / 微信 / X / Telegram / Facebook / LinkedIn）、动态 OG 图（Pillow 绘制 1200×630 + 磁盘缓存）、文章二维码（站点二维码 SVG）、图片灯箱 / 代码复制 / 阅读时长等阅读体验增强。
- **体验修复与升级（v3.17.0）**：修复**前后台深色模式顶部白条**（导航配色不再压过深色覆盖）、**主题包换肤未生效**（token key 下划线→短横线）、**后台表格手机端无法浏览全文**（窄屏卡片化堆叠）；新增 `prefers-reduced-motion` 降级、首页骨架屏、Toast 提示、路由过渡、滚动渐入、容器查询、Bento 首页概览、移动端手势导航、键盘彩蛋。
- **AVIF / 年度回顾 / AI 摘要（v3.17.0）**：上传图片自动生成 AVIF 并以 `<picture>` 优先加载（Pillow 支持时启用，**零新增依赖**）；新增 `/annual` 年度回顾页（发文 / 阅读 / 评论 / 访客 / 地域榜 / 最热文章 / 高频标签）；后台文章编辑页「🤖 生成 AI 摘要」+ 前台展示（复用 OpenAI 兼容配置，结果存 Setting，**零表结构变更**）。
- 历史版本记录见 [CHANGELOG.md](CHANGELOG.md)

## 功能一览

- **内容**：Markdown 写作（代码高亮）、定时发布、文章置顶、分类 / 标签 / 归档、每篇独立 SEO 字段、RSS / sitemap / robots
- **时区**：全站时间统一以「北京时间（UTC+8）」展示（数据库仍按 UTC 存储），覆盖文章 / 评论 / 归档 / RSS / sitemap / JSON-LD / 后台模板；定时发布输入框也按北京时间填写。
- **搜索**：SQLite FTS5 全文搜索（环境不支持时自动降级 LIKE）
- **阅读**：文章目录 TOC、阅读进度条、相关文章推荐、系列专栏（上下篇导航）、图片懒加载 + WebP 转码、阅读量防刷、多作者署名
- **互动**：评论（登录/匿名，显示 IP 属地与设备，头像由 cravatar 提供）、嵌套回复、评论与文章点赞、留言墙
- **社交**：广场微动态、友链 RSS 聚合（博客圈）、社交账号墙
- **微动态管理（v3.12.0）**：后台「💭 微动态」——列表检索（关键词 / 作者 / 分页）、编辑正文、删除动态（级联清评论）、逐条删评论、批量删除；编辑与删除均写入后台操作日志。此前动态发布后只能直改数据库
- **UI 设计系统 token 纯度（v3.12.1）**：后台 `admin.css` 与前端 `global.css` 的散点硬编码暗色（hex/rgb）统一替换为 `tokens.css` 语义 token，明暗主题外观像素级零色差；无逻辑变更、无 DB 迁移。详见 [CHANGELOG.md](CHANGELOG.md) v3.12.1 段
- **写作后台（v3.14.0）**：写作面板带 Markdown 工具栏与分屏实时预览（走后端同一渲染管线）、云端自动保存、未发布草稿一键「🔗 复制免登录预览链接」（HMAC 签名 + 24h 有效）；「📄 文章管理」独立成页（管理员看全站，关键词 / 状态 / 分类 / 系列筛选 + 多列排序 + 批量发布·转草稿·移分类·移回收站）；写文章时可就地**新建分类 / 系列**无需退出页面（同名自动复用）；「🖼️ 媒体库」浏览 / 复制 URL / 删除（带引用提示）；版本历史支持逐行对比；分类 / 系列可改名（slug 自动保持唯一）、删除分类可先把文章转移到目标分类；修复后台上传图片必 500 的遗留 bug（v3.11.0 切片遗失魔数表）
- **运营**：邮件订阅与新文推送、Telegram / 企业微信推送、站点公告、Open Graph 分享卡片
- **运维**：访问统计（区域 / 热读 / 热搜 / 时段）、数据备份与异地容灾（本地 / OSS / SCP / WebDAV）、后台一键在线更新、全站健康体检（11 维）、运营驾驶舱（趋势区间切换 / 评论·新文量曲线 / CSV 导出）
- **插件（框架保留，v3.10.0 起无内置插件）**：`myblog/plugins/` 可扩展插件框架 + 后台「🧩 插件管理」+ 事件总线与前端槽位；仓库不再内置插件，装自写插件只需放目录 + 填 `ENABLED_PLUGINS`
- **性能（v3.9.1）**：文章正文渲染结果落库缓存（`Post.content_html`，正文一改自动失效，长文 `87ms → 2.7ms`）+ SQLite WAL（读不阻塞写，解决并发 `database is locked`）
- **数据库迁移（v3.11.0）**：引入 Flask-Migrate / Alembic 基线迁移，与现有 `db.create_all()` 自动迁移并存；新库 `flask db upgrade`、存量库 `flask db stamp head` 即可对齐 v3.10.6 基线，后续模型变更可自动生成迁移（无缝升级）
- **远程诊断（v3.10.0）**：只读 MCP 端点 `/mcp`，AI 助手可远程查全站体检、数据库状态、错误日志、内容统计；未配置 token 时自动关闭，全部工具只读
- **MCP 服务管理（v3.13.0）**：后台「🔌 MCP 服务」面板——内置端点一键启停（停止 = 对外 404，即时生效）、外部 MCP 服务登记（token Fernet 加密落库零明文）、每个服务一键生成「AI 脱敏接入指令」（脱敏版可放心转发 / 完整版 AI 拿到即可直接配好 mcp.json，查看记审计）
- **博客圈稳定性（v3.10.4）**：友链 RSS 聚合加 socket 超时（默认 8s，环境变量 `FEED_FETCH_TIMEOUT` 可覆盖），坏源只跳过不卡死 worker；后台保存 RSS 增加可达性软校验
- **系统**：三级权限（超管 / 管理员 / 用户）、前后台统一明暗主题与自定义主题色、设备自适应
- **主题中心（v3.16.0）**：后台「🎨 主题中心」——14 套预设主题包（OKLCH 感知色彩，纯标准库推导暗色，亮色单源 / 暗色自动；每包含 light.accent 与 dark.bg 等语义 token）；实时预览网格 + 自定义 JSON 导入/导出（`POST /api/theme` 仅超管 + 全局 CSRF，自定义值仅作 CSS 变量无 JS 执行）；`/api/site` 下发 `theme_pack`/`theme_tokens`/`theme_dark_tokens` 供前后台统一换肤；复用既有 `Setting` 表，无 DB 迁移
- **移动端适配（v3.10.6）**：修复后台「统计」长标题与公开站「文档页」长路径 / 长表格 / 长代码在手机端横向溢出穿模，窄屏下统一换行而非挤压版心

## 快速开始

后端（默认 5000 端口）：

```bash
cd myblog
python -m venv venv && pip install -r requirements.txt
# 安全启动前置：两个环境变量缺失时程序拒绝启动
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export ADMIN_PASSWORD=$(python -c "import secrets;print(secrets.token_hex(16))")
flask --app app init-db
python app.py            # http://127.0.0.1:5000
```

前端（开发模式，自动代理 `/api` 到后端）：

```bash
cd vue-frontend
npm install
npm run dev              # http://localhost:5173
```

## 部署

完整宝塔面板点按式教程见 [myblog/deploy_guide.md](myblog/deploy_guide.md)。

- **后端**：gunicorn 运行 `myblog`（监听 8686），Nginx 反代 `/api/`、`/admin`、`/static/`
- **前端**：`npm run build` 后把 `dist/` 作为静态站根目录
- **必配环境变量**：`SECRET_KEY`、`ADMIN_PASSWORD`
- **升级**：覆盖后端与前端后，gunicorn 必须「**停止 → 启动**」（restart 不会重载前端静态资源），再硬刷新浏览器
- **确认版本**：登录后台，左下角显示当前版本号

部署包（后端 `myblog-backend.zip`、前端 `vue-frontend-dist.zip`）随 [Releases](../../releases) 发布。

## 安全

- `SECRET_KEY` / `ADMIN_PASSWORD` 必须经环境变量注入，缺失即拒绝启动，源码无任何弱默认密钥
- 会话 Cookie `Secure` / `HttpOnly` / `SameSite=Lax` + 同源校验 + CSRF Token 双重防护
- Markdown 经白名单清洗（防存储型 XSS）；RSS 聚合防 SSRF（仅 http/https、拦截内网与 DNS 重绑定）
- 登录 / 注册 / 评论 / 点赞按 IP 限流；Webhook 用 HMAC 恒定时间比较 + 时间戳防重放
- 图片上传禁用 SVG + 文件头魔数校验
- 评论头像由第三方 CDN（cn.cravatar.com）提供：仅发送邮箱的 MD5 哈希（Gravatar 协议标准，明文不落库），拉取失败自动回退默认头像（`?d=mp`）；用户邮箱不会对外暴露

完整审计见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)。

## License

[MIT](LICENSE) © 2026 Llhhy
