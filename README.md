# Llhhy Blog · 个人博客系统（Flask + Vue3）

前后端分离的个人博客：**Flask** 后端（JSON API + 管理后台）+ **Vue3** 前台（SPA）。单仓库托管前后端代码、部署文档与安全报告。

- 当前版本：**v3.25.16**
- **版本历史一律记在 [CHANGELOG.md](CHANGELOG.md)，README 不重复记录。**

## 功能一览

- **内容**：Markdown 写作（代码高亮）、定时发布、置顶、分类 / 标签 / 归档 / 系列专栏、每篇独立 SEO 字段、RSS / Atom / sitemap / robots、多语言与译文回退
- **搜索**：SQLite FTS5 全文搜索（环境不支持时自动降级 LIKE）
- **阅读**：目录 TOC、阅读进度条、相关文章推荐、图片懒加载 + AVIF / WebP、阅读量防刷、多作者署名
- **互动**：评论（登录 / 匿名，嵌套回复）、文章与评论点赞、表情回应、留言墙
- **社交**：广场微动态、友链 RSS 聚合（博客圈）、社交账号墙
- **写作后台**：分屏实时预览、云端自动保存、免登录预览链接、文章管理（筛选 / 排序 / 批量操作）、媒体库、版本历史逐行对比、AI 摘要
- **运营**：邮件订阅与新文推送、Telegram / 企业微信推送、站点公告、OG 分享卡片、收录主动推送（百度 / IndexNow）
- **运维**：访问统计与来源分析、运营驾驶舱、数据备份与异地容灾（本地 / OSS / SCP / WebDAV）、一键在线更新（Ed25519 签名、验签失败即终止）、全站健康体检、只读 MCP 远程诊断
- **系统**：三级权限（超管 / 管理员 / 用户）、前后台统一明暗主题 + 主题中心、设备自适应、PWA、可选 OAuth 登录与 2FA
- **插件**：`myblog/plugins/` 可扩展框架 + 后台「🧩 插件管理」；仓库不内置插件，装自写插件只需放目录 + 填 `ENABLED_PLUGINS`
- **时区**：全站按北京时间（UTC+8）展示，数据库仍存 UTC

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
- 评论头像由第三方 CDN（cn.cravatar.com）提供：仅发送邮箱的 MD5 哈希（Gravatar 协议标准，明文不落库），拉取失败自动回退默认头像；用户邮箱不会对外暴露

完整审计见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)。

## License

[MIT](LICENSE) © 2026 Llhhy
