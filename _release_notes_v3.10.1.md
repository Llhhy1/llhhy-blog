# llhhy-blog v3.10.1 · 修复全站体检「前端构建产物」部署态误报

## 改动
- 修复全站体检「前端构建产物」维度在**部署态**必现的 warn 误报：旧逻辑只查 `vue-frontend/_vite_build*`，但部署布局是 `vue-frontend-dist.zip` 平铺到站点根目录（直接 `index.html + assets/`），无 `_vite_build*` 子目录，导致永远误报「未构建」。改为查 **SPA 入口 `index.html` 是否存在**——部署态优先查 `fe_dir/index.html`，回退本地 `_vite_buildN` / `dist` 构建目录，两种布局都能正确识别。
- 友链 RSS 某源解析 0 条属对方源为空（非本博客 bug），不在本轮修复范围。

## 安全审计
- **R51 九维审计 0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R51 轮）。纯诊断误报修复，不引入任何新的安全边界（XSS / SQL / 越权 / SSRF / CSRF / 密钥 / 资源泄漏 / 限流 均为既有权限与渲染模型下的安全改造）。

## 验证
- 全量 pytest **31 passed**（无回归）；`py_compile` 通过；用模拟服务器布局（部署态 `vue-frontend/index.html`）验证体检该维度返回 `ok`、本地无构建返回 `warn`（符合预期）。

## 部署注意
- **纯后端改动，前端产物无变化**：覆盖 `myblog-backend.zip` 后「停止 → 启动」gunicorn（restart 不重载）即生效。
- 后台「🩺 全站体检 → 前端构建产物」维度在部署态应直接显示 `ok`（不再误报 warn）。
- 发布资产：`myblog-backend.zip` / `vue-frontend-dist.zip` / `sha256.txt`（含双源互证校验，可防篡改）。
