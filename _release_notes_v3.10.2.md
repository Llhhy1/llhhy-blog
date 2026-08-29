# llhhy-blog v3.10.2 · 诊断助手增强：SMTP 误报修复 + 新增 2 维度

## 改动
- **① 修复「邮件 SMTP」误报（根因）**：`diagnostics.py::check_config()` 原查 `get_setting("smtp_host")`，但后台「邮件设置」存库的 key 实为 `mail_host`（`mail_notify.load_mail_config()` 读取 `mail_host`/`mail_username`/…），且用户是在后台面板配、没用 `SMTP_HOST` 环境变量，导致诊断永远判「未配置」误报 warn。改为 `get_setting("mail_host") or os.environ.get("SMTP_HOST")`，与实际发信配置一致（仅显示 SMTP 服务器域名，不回显账号/密码）。
- **② 新增 2 个诊断维度（9 维 → 11 维）**：
  - **安全配置概览**（`check_security`）：汇总图形验证码 / 评论开关 / 强密码策略(`STRONG_PASSWORD`) / 安全响应头(`SECURITY_HEADERS`) / 接口限流 状态；开着评论却关验证码、或未开安全头/强密码时告警，暴露安全短板。
  - **渲染缓存命中率**（`check_render_cache`）：统计 `Post.content_html` 已缓存占比；全部未缓存则预警（性能退化 + 可能缓存写回失败）。
  - 两个新维度自动纳入 `run_all()`，后台「🩺 全站体检」与 MCP `health_overview` 同步可见，无需改 MCP 代码。

## 安全审计
- **R52 九维审计 0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R52 轮）。两个新 checker 与 SMTP 修正均为只读配置/DB 读取，无用户可控输入、无 HTML 输出、无 SQL 拼接/越权/SSRF/CSRF 缺口/密钥泄露/资源泄漏；仅显示 SMTP 服务器域名与布尔开关，绝不回显账号/密码/令牌。

## 验证
- `py_compile` 通过；全量 pytest **31 passed**（无回归）；R52 九维审计 **0 遗留**。

## 部署注意
- **纯后端改动，前端产物无变化**：覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效。
- 体检维度由 9 增至 11：「邮件 SMTP」维度后台配的也能显示 `ok`、新增「安全配置概览」「渲染缓存命中率」。
- 发布资产：`myblog-backend.zip` / `vue-frontend-dist.zip` / `sha256.txt`（含双源互证校验）。
