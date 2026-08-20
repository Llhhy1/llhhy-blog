# 安全审计报告（SECURITY_AUDIT.md）

> 审计时间：2026-08-20 · 审计对象：myblog（Flask 后端）+ vue-frontend（Vue3 前端）
> 审计目标：以**开源前最严格标准**核查代码并修复安全问题；本文件随代码同步交付。
> 修复验证：本地自动化验证脚本覆盖 7 项关键行为（XSS 清理 / CORS 关闭 / 跨站拦截 / 开放重定向 / 登录限流 / 评论存储 / 缺失密钥拒绝启动），**全部通过**。

---

## 一、审计结论

发现并修复 **1 个严重、6 个高危、4 个中危** 问题。修复后无遗留严重/高危问题。

## 二、发现的问题与修复

### 🔴 严重

| # | 问题 | 修复 |
|---|---|---|
| S1 | `app.py` 直接运行入口 `debug=True` 且监听 `0.0.0.0`：若误用 `python app.py` 启动生产，Werkzeug 调试器可被远程利用执行代码（RCE） | 改为 `debug=False` 且仅监听 `127.0.0.1`（生产走 Nginx → gunicorn 反代，不暴露 5000 端口） |

### 🟠 高危

| # | 问题 | 修复 |
|---|---|---|
| H1 | `SECRET_KEY` 内置弱默认值 `please-change-this-secret-key`：未配置时可用已知密钥伪造任意用户（含超管）会话 | 改为**必须**从环境变量读取，缺失直接拒绝启动 |
| H2 | `ADMIN_PASSWORD` 内置默认值 `admin123`：首次部署若未配置会创建弱密码超管 | 同上，必须从环境变量读取，缺失拒绝启动；首次登录仍强制修改账号密码 |
| H3 | CORS 默认 `*`：任意网站可跨域读取接口响应，并对登录/注册接口无限制调用 | 默认**关闭** CORS；仅显式配置允许的前端来源时才开启并精确匹配 |
| H4 | 文章/关于页 Markdown 渲染不过滤 HTML，且前端用 `innerHTML`/`v-html` 渲染 → 存储型 XSS | 新增 `bleach` 白名单清理，统一 `render_markdown()` / `clean_html()` 出口，剥离 script、事件属性、危险协议 |
| H5 | 登录/注册/评论/点赞等写接口无防护：可暴力破解、刷量、灌垃圾 | 会话 Cookie `SameSite=Lax` + 全局同源校验（跨站 POST 返回 403）+ 每 IP 限流（登录/注册 10 次/60s、评论 10 次/60s、点赞 20 次/60s/篇） |
| H6 | 登录回跳 `next` 参数未校验 → 开放重定向（钓鱼） | 新增 `safe_redirect()`：仅允许站内相对路径，拒绝 `//` 开头的协议相对地址 |
| H7 | 会话 Cookie 未显式设置 `Secure`/`HttpOnly`/`SameSite` | 配置 `SESSION_COOKIE_SECURE`（默认 true，可 `COOKIE_SECURE=false` 覆盖本地）、`HttpOnly=True`、`SameSite=Lax` |

### 🟡 中危

| # | 问题 | 修复 |
|---|---|---|
| M1 | 上传允许 `svg`：SVG 可内嵌脚本，直接访问 URL 时可能执行 JS | 从允许扩展名移除 `svg`（仅 png/jpg/jpeg/gif/webp） |
| M2 | 前端通过外部 CDN（bootcdn）动态加载 highlight.js：CDN 被劫持可注入任意脚本（供应链风险） | 改为**本地打包** highlight.js，按需注册常用语言；顺带把文章页 JS 从 985KB 压到 73KB |
| M3 | 公开注册无开关，任何人可无限注册 | 新增 `BLOG_OPEN_REGISTER` 环境变量（默认开，可设 `false` 关闭） |
| M4 | IP 属地接口 `http://ip-api.com` 明文传输 | 改为 HTTPS |

## 三、改动文件清单

- **后端 `myblog/`**：`config.py`、`app.py`、`utils.py`、`routes.py`、`api.py`、`admin.py`、`stats.py`、`requirements.txt`（新增 `bleach`）、`README.md`、`deploy_guide.md`
- **前端 `vue-frontend/`**：`src/views/PostView.vue`（highlight.js 本地化）

## 四、上线前必做（宝塔面板 · 环境变量配置）

程序启动**必须**存在两个环境变量（缺失即拒绝启动）：

1. 宝塔面板 → 「Python 项目」→ 你的项目 → **「设置」→「环境变量」**；
2. 新增两项**必填**：
   - `SECRET_KEY` ← 在服务器终端执行以下命令生成一串随机值填入：
     ```bash
     python3 -c "import secrets;print(secrets.token_hex(32))"
     ```
   - `ADMIN_PASSWORD` ← 一个随机强密码（首次登录后台还会被强制修改，这里只是初始值）
3. （推荐）`COOKIE_SECURE=true`；`SITE_URL=https://你的域名`
4. 保存并**重启项目**。若日志报"缺少环境变量 SECRET_KEY / ADMIN_PASSWORD"，说明没配置成功。

## 五、残余风险与建议（非阻塞）

- 内存限流在 gunicorn 多 worker 下各自计数，仅作纵深防御；高流量可引入 Redis + Flask-Limiter。
- 生产建议启用 HTTPS（Let's Encrypt 免费证书），并定期备份 `data/blog.db`。
- 评论/注册等写接口后续可加验证码（如极验）进一步防滥用。
- 请确认 Nginx 反代已配置 `proxy_set_header X-Forwarded-For $remote_addr;`（由 Nginx 写入真实 IP，而不是透传客户端伪造值）。
