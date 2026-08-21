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
│   ├── feed_agg.py            # 友链 RSS 聚合（广场「博客圈」，防 SSRF + 清洗）
│   ├── stats.py               # 访问统计与 IP 属地解析
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

- **内容**：文章发布（Markdown + 代码高亮）、分类、标签、归档时间线、RSS / sitemap / robots
- **搜索**：SQLite FTS5 全文搜索（构建环境不支持时自动降级 LIKE 模糊匹配）
- **阅读体验**：文章目录 TOC + 阅读进度条、相关文章推荐（标签重合度算法）、热门文章排行、系列/专栏（含上下篇导航）
- **互动**：评论（登录或匿名，IP 属地 + 设备展示）、**嵌套回复**、评论点赞、文章点赞、留言墙（前台独立留言页）
- **社交**：「广场」页——微动态发布/点赞/评论、友链 RSS 聚合流（博客圈）、社交账号墙
- **运营**：邮件订阅（侧边栏订阅框）、站点公告（可关闭横幅）、一键分享 + Open Graph 标签
- **邮件群发**：新文章发布自动通知订阅者，**后台「📧 邮件设置」直接配置 SMTP + 一键测试发送**（v2.4.0+）
- **推送**：新文章发布推送 Telegram / 企业微信（可选，未配置自动跳过）
- **运维**：Webhook 自动部署接口（HMAC 校验，可触发服务器部署脚本自动更新）、访问统计（区域 TOP10/热读/热搜/时段分布）
- **系统**：三级权限（超管/管理员/普通用户）、前后台统一登录、后台新消息提醒（未读评论/留言角标）、明暗主题 + 自定义主题色、版本号自检（后台左下角显示当前版本）
- 设备自适应：手机 / 平板 / 桌面

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
- **必配环境变量**：`SECRET_KEY`、`ADMIN_PASSWORD`（宝塔「Python 项目 → 设置 → 环境变量」）。
- **版本确认**：登录后台，左下角显示当前版本（如 v2.4.0），与 [Releases](../../releases) 最新标签比对即可确认部署是否成功。
- **升级（简单方式）**：用仓库根目录 `update.sh` 一键脚本（上传后 `bash update.sh`，自动下载最新包 + 备份数据 + 覆盖代码），详见部署文档「一键更新脚本」章节。
- **升级（手动方式）**：备份 `data/` 与 `static/uploads/` → 覆盖后端/前端 → 「停止」再「启动」项目 → 验证版本号。详见部署文档「版本升级」章节。

## 安全说明

本项目已做开源前安全加固（两轮审计），完整审计报告见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)：

- `SECRET_KEY` / `ADMIN_PASSWORD` 必须通过环境变量注入，**缺失即拒绝启动**，源码不含任何弱默认密钥；
- 会话 Cookie `Secure` / `HttpOnly` / `SameSite=Lax` + 跨站请求同源校验（CSRF 防御）；
- Markdown 渲染经白名单清理（防存储型 XSS）；RSS 聚合抓取同样清洗 + 防 SSRF（只允许 http/https、拦截内网地址）；
- CORS 默认关闭；登录 / 注册 / 评论 / 留言 / 订阅 / 点赞按 IP 限流；
- Webhook 部署接口使用 HMAC 恒定时间比较校验密钥，未配置密钥时接口不可用；
- 推送通知（Telegram / 企业微信）密钥仅走环境变量，异常静默处理，不入库不入仓；
- 图片上传禁用 SVG（防内嵌脚本 XSS）。
- **修复记录**：第二轮审计修复 Webhook 密钥未从环境变量载入导致恒 403 的缺陷（R1）。

## 下载部署包

部署用压缩包（后端 `myblog-backend.zip`、前端 `vue-frontend-dist.zip`）随本仓库 **Releases** 发布：请到 [Releases](../../releases) 下载，解压后按部署文档上传服务器。

## License

[MIT](LICENSE) © 2026 Llhhy
