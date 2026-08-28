# Llhhy Blog · 个人博客系统（Flask + Vue3）

前后端分离的个人博客：**Flask** 后端（SSR + JSON API + 管理后台）+ **Vue3** 前端（SPA）。单仓库托管前后端代码、部署文档与安全报告。

- 当前版本：**v3.9.1**
- 历史版本记录见 [CHANGELOG.md](CHANGELOG.md)

## 功能一览

- **内容**：Markdown 写作（代码高亮）、定时发布、文章置顶、分类 / 标签 / 归档、每篇独立 SEO 字段、RSS / sitemap / robots
- **搜索**：SQLite FTS5 全文搜索（环境不支持时自动降级 LIKE）
- **阅读**：文章目录 TOC、阅读进度条、相关文章推荐、系列专栏（上下篇导航）、图片懒加载 + WebP 转码、阅读量防刷、多作者署名
- **互动**：评论（登录/匿名，显示 IP 属地与设备）、嵌套回复、评论与文章点赞、留言墙
- **社交**：广场微动态、友链 RSS 聚合（博客圈）、社交账号墙
- **运营**：邮件订阅与新文推送、Telegram / 企业微信推送、站点公告、Open Graph 分享卡片
- **运维**：访问统计（区域 / 热读 / 热搜 / 时段）、数据备份与异地容灾（本地 / OSS / SCP / WebDAV）、后台一键在线更新、全站健康体检（9 维）
- **插件（v3.9.0）**：`myblog/plugins/` 可扩展插件框架 + 后台「🧩 插件管理」+ 内置文章目录侧栏插件
- **性能（v3.9.1）**：文章正文渲染结果落库缓存（`Post.content_html`，正文一改自动失效，长文 `87ms → 2.7ms`）+ SQLite WAL（读不阻塞写，解决并发 `database is locked`）
- **系统**：三级权限（超管 / 管理员 / 用户）、前后台统一明暗主题与自定义主题色、设备自适应

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

完整审计见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)。

## License

[MIT](LICENSE) © 2026 Llhhy
