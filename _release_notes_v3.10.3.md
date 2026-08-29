# llhhy-blog v3.10.3 - 新增评论 RSS 订阅源 `/feed/comments`

## 改了什么
- **新增评论 RSS 路由** `routes.py::comments_feed`：
  - 路径：`/feed/comments` + `/feed/comments/`（两个都注册，带不带斜杠都行）
  - 输出 RSS 2.0（`application/rss+xml`），取最近 50 条「`approved=True` 且所属文章已发布」的评论
  - 每项含文章链接锚点 `#comment-<id>`、评论摘要、作者
  - 评论内容 / 作者 / 文章标题**全部 `escape` 转义**，杜绝 XSS（`<script>` → `&lt;script&gt;`）
- **`bot_guard._SKIP_PREFIXES` 加 `/feed/comments`**：开启反爬后 RSS 阅读器（Feedly 等 bot UA）不会被限流/封禁
- **`diagnostics.check_seo` 加 `/feed/comments` 路由检查**：防止未来 Nginx 反代漏配导致该路由又被 SPA 兜底返主界面

## 根因
用户访问 `/feed/comments/` 返回主界面——博客（自研 Flask）只有文章 feed `/feed.xml`，**从未实现评论 feed 路由**，请求落到 Nginx `try_files ... /index.html` SPA 兜底规则返回 `index.html`。本版补全。

## 验证
- `py_compile` 通过
- 本地冒烟测试（临时 sqlite + Flask `test_client`）：`/feed/comments/` 与 `/feed/comments` 均返回 200 + `application/rss+xml`，`<item>` 存在、XSS 转义生效、锚点 `#comment-<id>` 正确
- R53 安全审计 **0 遗留**（XSS / 越权 / 注入 / SSRF / 密钥 / 资源 / 反爬误伤 / 回归 全 ✅）
- 全量 pytest **31 passed** 保持

## 部署注意（必做）
- **纯后端改动，前端产物无变化**
- 覆盖 `myblog-backend.zip` 后「**停止 → 启动**」gunicorn（restart 不重载）即生效
- 评论订阅源：`https://你的域名/feed/comments/` 即可被 RSS 阅读器订阅
- APP_VERSION 升为 v3.10.3（后台左下角可见）
