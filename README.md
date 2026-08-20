# Llhhy Blog · 个人博客系统（Flask + Vue3）

一个前后端分离的个人博客系统：**Flask** 后端（服务端渲染 + JSON API + 管理后台）+ **Vue3** 前端（SPA，构建为静态站）。采用 monorepo 单仓库托管，前后端代码、部署文档、安全报告都在这里。

## 目录结构

```
llhhy-blog/
├── myblog/                    # Flask 后端
│   ├── app.py                 # 应用工厂（启动入口）
│   ├── routes.py              # 前台页面 / 登录注册 / 评论 / 天气 / RSS
│   ├── admin.py               # 后台管理（文章/分类/标签/评论/统计/用户/设置）
│   ├── api.py                 # 前后端分离 JSON 接口（/api/*）
│   ├── models.py              # 数据模型（文章/评论/用户/统计等）
│   ├── stats.py               # 访问统计与 IP 属地解析
│   ├── templates/             # Jinja2 模板（含后台管理界面）
│   ├── static/                # 样式脚本与上传目录
│   ├── SECURITY_AUDIT.md      # 安全审计报告
│   └── deploy_guide.md        # 宝塔面板部署手册
└── vue-frontend/              # Vue3 前端（Vite 构建）
    ├── src/                   # 组件与页面
    └── vite.config.js         # /api 开发代理
```

## 功能特性

- 文章发布（Markdown）、分类、标签、搜索、归档、RSS / 站点地图
- 评论（登录或匿名，展示属地与设备）、点赞、阅读量统计
- 天气小组件、友情链接、关于页
- 三级权限：超级管理员 / 管理员 / 普通用户（普通用户也可发表文章）
- 主题美化：明暗模式、圆角、字号、导航样式、自定义 CSS
- 访问统计：区域 TOP10、热读文章、常搜词、时段分布
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

## 安全说明

本项目已做开源前安全加固，完整审计报告见 [myblog/SECURITY_AUDIT.md](myblog/SECURITY_AUDIT.md)：

- `SECRET_KEY` / `ADMIN_PASSWORD` 必须通过环境变量注入，**缺失即拒绝启动**，源码不含任何弱默认密钥；
- 会话 Cookie `Secure` / `HttpOnly` / `SameSite=Lax` + 跨站请求同源校验（CSRF 防御）；
- Markdown 渲染经白名单清理（防存储型 XSS）；CORS 默认关闭；
- 登录 / 注册 / 评论 / 点赞按 IP 限流；图片上传禁用 SVG。

## 下载部署包

部署用压缩包（后端 `myblog-backend.zip`、前端 `vue-frontend-dist.zip`）随本仓库 **Releases** 发布：请到 [Releases](../../releases) 下载，解压后按部署文档上传服务器。

## License

[MIT](LICENSE) © 2026 Llhhy
