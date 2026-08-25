# llhhy-blog API 文档

> 版本：v3.6.0（API 解耦重构后）
>
> 本文档描述 llhhy-blog 的全部 JSON 接口（`/api/*`）。前端（`vue-frontend/src/lib/api.js`）与本站页面共用这些接口；你也可以用它们定制自己的客户端、App 或第三方应用。

## 目录

- [通用约定](#通用约定)
- [模块结构](#模块结构)
- [认证 /auth](#认证-auth)
- [站点 /site](#站点-site)
- [文章 /posts](#文章-posts)
- [统计 /stats](#统计-stats)
- [社交广场 /social](#社交广场-social)
- [专题 /series](#专题-series)
- [留言墙 /guestbook](#留言墙-guestbook)
- [订阅 /subscribe](#订阅-subscribe)
- [通知 /notifications](#通知-notifications)
- [系统 /system](#系统-system)

---

## 通用约定

### 1. 基地址与返回格式

- 所有接口前缀为 `/api`，例如 `POST /api/auth/login`。
- 成功返回 `200`（创建类有时为 `201`），带 `JSON` 响应体。
- 错误统一返回 JSON：`{"error": "<原因>"}`，状态码见各端点。
- 所有响应均带统一安全头（CSP、X-Frame-Options 等，见 `security.py`）。

### 2. 鉴权方式

| 级别 | 说明 | 判定 |
|------|------|------|
| 公开 | 无需登录即可访问 | — |
| 登录 | 需登录（会话 Cookie 或 `X-User-Id` 头） | 未登录返回 `401 {"error": "请先登录"}`；无权限返回 `403` |
| 超管 | 仅超级管理员 | 未登录/无权返回 `403` |

登录后，Flask session 与前端 `X-User-Id` 头共用同一会话（见 `_login_user`）。

### 3. CSRF 保护

- **仅对写操作（POST / PUT / DELETE / PATCH）生效**，GET 豁免。
- 写法：先 `GET /api/csrf` 取 token，再在写请求头带 `X-CSRF-Token: <token>`。
- 豁免白名单（写操作无需 token）：`/api/webhook/deploy`、`/api/captcha`、`/api/stats/read`、`/api/stats/visit`、`/api/stats/search`。
- 缺失/错误 token 时返回 `403 {"error": "CSRF token 缺失或无效"}`。

### 4. 分页

列表类接口统一支持 `?page=<页码>`（从 1 开始）与 `?per_page=<每页条数>`（默认 8，最大 100）。

### 5. 限流

部分写接口有限流（`utils.rate_limit`），超限返回 `429`。常见阈值：登录 5 次/分钟、动态发布 5 次/分钟、搜索记录 120 次/小时、阅读记录 60 次/分钟。

---

## 模块结构

v3.6.0 起，API 从单文件 `api.py` 解耦为按功能组织的包：

```
myblog/
├── api/
│   ├── __init__.py      # api_bp 聚合导出（from api import api_bp 兼容）
│   ├── common.py        # 共享辅助（当前用户/登录/CSRF/序列化器等）
│   ├── auth.py          # 认证与验证码
│   ├── site.py          # 站点信息/友链/公告
│   ├── posts.py         # 文章/分类/标签/归档/评论/搜索/RSS
│   ├── stats.py         # 访问统计埋点与汇总
│   ├── social.py        # 微动态/圈子/社交账号
│   ├── series.py        # 文章专题
│   ├── guestbook.py     # 留言墙
│   ├── subscribe.py     # 邮件订阅/退订
│   ├── notifications.py # 站内通知
│   └── system.py        # 版本更新/部署 webhook
```

- 新增一个功能时：新建 `myblog/api/xxx.py`，从 `common.py` 按需导入，
  在 `__init__.py` 的导入清单中加一行即可，无需改动其他任何文件。
- **不要**在模块间互相 `import`（避免循环依赖）；共享逻辑一律放 `common.py`。
- **`stats` 是独立的项目级模块**（`myblog/stats.py`），不通过 `common.py` 转发。
  若新模块需要 `stats.client_ip()` / `stats.cached_region()` / `stats.record_*()` 等，
  必须在本模块顶部显式 `import stats`（与 `common.py` 一致），
  否则运行时抛 `NameError: name 'stats' is not defined`（拆包时曾因此漏修 5 个模块）。

---

## 认证 /auth

### `POST /api/auth/register` — 注册

- 鉴权：公开（站点未开启注册时返回 `403`）
- 请求体：`{"username": "...", "password": "..."}`
- 成功：`201 {"ok": true, "message": "注册成功，请登录"}`
- 失败：`400`（用户名已被占用/弱密码等，`{"error": "..."}`）

### `POST /api/auth/login` — 登录

- 鉴权：公开（失败统一延迟 1s 防枚举）
- 请求体：`{"username": "...", "password": "..."}`
- 成功：`200 {"ok": true, "user": {...}, "csrf_token": "..."}`
  - `user` 含 `id / username / role / is_admin / is_super / created_at`
  - `csrf_token` 供前端登录后立即更新缓存（v3.1.6）
- 失败：`401 {"error": "用户名或密码错误"}`

### `POST /api/auth/logout` — 登出

- 鉴权：公开（已登录则清除会话）
- 成功：`200 {"ok": true}`

### `GET /api/auth/me` — 当前用户

- 鉴权：登录
- 成功：`200 {"user": {...}}`；未登录：`200 {"user": null}`

### `GET /api/csrf` — 取 CSRF Token

- 鉴权：公开
- 成功：`200 {"csrf_token": "<token>"}`

### `GET /api/captcha/config` — 验证码配置快照

- 鉴权：公开
- 成功：`200 {"global_enabled": true/false, "pil_available": true/false, "scenes": {"register": true, "comment": true, "guestbook": true}}`

### `GET /api/captcha` — 图形验证码

- 鉴权：公开（CSRF 豁免）
- 已启用：返回 PNG 图片；未启用/不可用：`404`

### `POST /api/captcha/verify` — 提交验证码

- 鉴权：公开
- 请求体：`{"captcha": "<文本>"}`
- 成功：`200 {"ok": true}`（会话标记 `captcha_passed`，一次性票据，后续注册/评论/留言免再验证）；失败：`400 {"error": "验证码错误"}`

---

## 站点 /site

### `GET /api/site` — 站点全局配置

- 鉴权：公开
- 成功：`200 {"site_name": "...", "about_content": "...", "allow_register": true, "announcements": [...]}` 等

### `GET /api/links` — 友情链接列表

- 鉴权：公开
- 成功：`200 [{"name": "...", "url": "...", "description": "..."}, ...]`

### `POST /api/link-apply` — 友链自助申请（v3.0.0 功能6）

- 鉴权：公开
- 请求体：`{"name": "...", "url": "...", "description": "..."}`
- 成功：`200 {"ok": true}`；失败：`400 {"error": "..."}`

### `GET /api/announcements` — 公告列表

- 鉴权：公开
- 成功：`200 [{"id": 1, "content": "...", "created_at": "YYYY-MM-DD HH:MM"}, ...]`

---

## 文章 /posts

### `GET /api/posts` — 文章列表（分页、可筛选）

- 鉴权：公开
- 查询参数：`page`、`per_page`、`category=<slug>`、`tag=<slug>`、`q=<关键词>`
- 成功：`200 {"items": [PostCard...], "page": 1, "pages": 3, "per_page": 8, "total": 20}`
- `items` 内每项为文章卡片摘要（含 `id / slug / title / excerpt / cover / category / tags / created_at / likes / views / word_count / reading_minutes`）

### `GET /api/post/<slug>` — 文章详情

- 鉴权：公开（未发布/定时未到/私密文章：未登录 `404`，登录且超管可见）
- 成功：`200 {"post": {...}, "comments": [...], "related": [...]}`
- `post` 含正文（`content_html`）、`word_count`、`reading_minutes`、`reward_enabled`、`is_private`、前后篇等

### `GET /api/categories` — 分类列表

- 鉴权：公开
- 成功：`200 [{"id": 1, "name": "...", "slug": "...", "count": 5}, ...]`

### `GET /api/tags` — 标签列表

- 鉴权：公开
- 成功：`200 [{"id": 1, "name": "...", "slug": "...", "count": 3}, ...]`

### `GET /api/hot-tags` — 热门标签（v3.0.0 功能7）

- 鉴权：公开
- 成功：`200 [{"name": "...", "slug": "...", "count": N, "views": N}, ...]`（按文章数排序取前 N，附总阅读量便于热度加权）

### `GET /api/category/<slug>` — 分类下文章

- 鉴权：公开
- 查询参数：`page`、`per_page`
- 成功：`200 {"items": [...], "category": {...}, "page": 1, "pages": N}`

### `GET /api/tag/<slug>` — 标签下文章

- 鉴权：公开
- 查询参数：`page`、`per_page`
- 成功：`200 {"items": [...], "tag": {...}, "page": 1, "pages": N}`

### `GET /api/rss/category/<slug>` — 分类 RSS

- 鉴权：公开
- 成功：`200`，`Content-Type: application/rss+xml`（该分类下已发布文章的订阅源）

### `GET /api/rss/tag/<slug>` — 标签 RSS

- 鉴权：公开
- 成功：`200`，`Content-Type: application/rss+xml`

### `GET /api/archive` — 文章归档

- 鉴权：公开
- 成功：`200 [{"year": 2026, "months": [{"month": 1, "count": 3}, ...]}, ...]`

### `POST /api/post/<slug>/like` — 点赞/取消点赞

- 鉴权：公开（限流防刷）
- 请求体：可选 `{"unlike": true}`（取消点赞）
- 成功：`200 {"ok": true, "likes": N}`；文章不存在：`404`

### `POST /api/post/<slug>/comment` — 发表评论

- 鉴权：公开（若站点开启评论登录则需登录；开启验证码则需先 `/captcha/verify`）
- 请求体：`{"content": "...", "parent_id": <可选>}`
- 成功：`201 {"ok": true, "comment": {...}}`；未登录被拒：`401`；验证码未过：`400`

### `GET /api/post/<slug>/related` — 相关文章

- 鉴权：公开
- 成功：`200 [PostCard...]`（同分类/同标签的推荐文章）

### `GET /api/post/<slug>/also-viewed` — 「看了又看」

- 鉴权：公开
- 成功：`200 [PostCard...]`（v3.0.0 功能8：协同过滤推荐）

### `GET /api/search` — 全文搜索

- 鉴权：公开
- 查询参数：`q=<关键词>`、`page`、`per_page`
- 成功：`200 {"items": [...], "page": 1, "pages": N, "total": N}`（FTS5，不可用时自动降级 LIKE）

### `POST /api/post/<int:post_id>/publish-now` — 立即发布定时文章

- 鉴权：超管
- 成功：`200 {"ok": true}`（清空 `scheduled_at` 并翻为已发布）；无权限：`403`

---

## 统计 /stats

### `POST /api/stats/visit` — 上报访问

- 鉴权：公开（**CSRF 豁免**）
- 请求体：`{"path": "/..."}`（前端每次路由变化 fire-and-forget）
- 成功：`200 {"ok": true}`

### `POST /api/stats/search` — 记录搜索词

- 鉴权：公开（**CSRF 豁免**；120 次/小时限流）
- 请求体：`{"keyword": "..."}`
- 成功：`200 {"ok": true}`；超限：`429`

### `POST /api/stats/read` — 记录文章阅读

- 鉴权：公开（**CSRF 豁免**；60 次/分钟限流）
- 请求体：`{"slug": "..."}`
- 成功：`200 {"ok": true}`；超限：`429`

### `GET /api/stats/summary` — 统计汇总

- 鉴权：公开
- 成功：`200 {"views": N, "visitors": N, "region_top": [...], "hot_posts": [...], "hot_queries": [...], "hourly_dist": [...], "trend": [...]}`

### `GET /api/stats/trend` — 访客趋势（v3.0.0 功能9）

- 鉴权：公开
- 查询参数：`days=<N>`（默认 7）
- 成功：`200 [{"date": "YYYY-MM-DD", "pv": N, "uv": N}, ...]`

---

## 社交广场 /social

### `GET /api/moments` — 微动态列表

- 鉴权：公开
- 查询参数：`page`、`per_page`
- 成功：`200 {"items": [{"id", "author", "content", "likes", "comments": [...], "created_at"}], "page": 1, "pages": N}`

### `POST /api/moment` — 发布微动态

- 鉴权：登录（5 次/分钟限流；纯文本存储，前端渲染转义防 XSS）
- 请求体：`{"content": "..."}`
- 成功：`201 {"ok": true, "moment": {...}}`；未登录：`401`

### `POST /api/moment/<int:mid>/like` — 微动态点赞

- 鉴权：登录（限流防刷）
- 成功：`200 {"ok": true}`；未登录：`401`

### `POST /api/moment/<int:mid>/comment` — 微动态评论

- 鉴权：公开（需昵称；已登录自动用用户名）
- 请求体：`{"content": "...", "nickname": "<可选>"}`
- 成功：`201 {"ok": true, "comment": {...}}`

### `GET /api/feed/circle` — 博客圈

- 鉴权：公开
- 成功：`200 {"items": [{"title", "link", "source", "published"}], "updated_at": "..."}`（抓取友链 RSS 混排，15 分钟缓存 + SSRF 防护）

### `GET /api/social-accounts` — 作者社交账号墙

- 鉴权：公开
- 成功：`200 [{\"platform\": \"github\", \"text\": \"...\", \"url\": \"...\"}, ...]`

---

## 专题 /series

### `GET /api/series` — 专题列表

- 鉴权：公开
- 成功：`200 {\"items\": [{\"id\", \"name\", \"slug\", \"description\", \"post_count\", \"updated_at\"}], \"page\": 1, \"pages\": N}`

### `GET /api/series/<slug>` — 专题详情

- 鉴权：公开
- 成功：`200 {\"series\": {...}, \"posts\": [PostCard...]}`；不存在：`404`

---

## 留言墙 /guestbook

### `GET /api/guestbook` — 留言列表

- 鉴权：公开
- 查询参数：`page`、`per_page`
- 成功：`200 {\"items\": [{\"id\", \"author\", \"content\", \"likes\", \"region\", \"device\", \"created_at\"}], \"page\": 1, \"pages\": N, \"total\": N}`

### `POST /api/guestbook` — 发表留言

- 鉴权：公开（开启验证码则需先 `/captcha/verify`）
- 请求体：`{\"content\": \"...\", \"author\": \"昵称（可选）\"}`
- 成功：`201 {\"ok\": true}`；验证码未过：`400`

### `POST /api/guestbook/<int:gid>/like` — 留言点赞

- 鉴权：公开（限流防刷）
- 成功：`200 {\"ok\": true, \"likes\": N}`；不存在：`404`

---

## 订阅 /subscribe

### `POST /api/subscribe` — 邮件订阅

- 鉴权：公开（需验证码校验）
- 请求体：`{\"email\": \"user@example.com\"}`
- 成功：`200 {\"ok\": true, \"message\": \"订阅成功，请查收确认邮件\"}`；重复订阅：`200 {\"ok\": true, \"message\": \"你已经订阅啦\"}`

### `GET/POST /api/unsubscribe` — 退订

- 鉴权：公开（无需登录）
- 请求体/参数：`{\"email\": \"...\", \"token\": \"<退订令牌>\"}`
- 成功：`200 {\"ok\": true, \"message\": \"已退订\"}`；令牌无效：`400`

---

## 通知 /notifications

### `GET /api/notifications` — 通知列表

- 鉴权：登录
- 成功：`200 {\"items\": [{\"id\", \"content\", \"link\", \"read\", \"created_at\"}], \"unread\": N}`；未登录：`401`

### `POST /api/notification/<int:nid>/read` — 标记单条已读

- 鉴权：登录
- 成功：`200 {\"ok\": true}`；非本人通知：`404`

### `POST /api/notifications/read-all` — 全部标记已读

- 鉴权：登录
- 成功：`200 {\"ok\": true}`

---

## 系统 /system

### `GET /api/version/check` — 检测新版本

- 鉴权：登录
- 成功：`200 {\"latest\": \"v3.6.0\", \"current\": \"v3.6.0\", \"has_update\": false}`（对比 GitHub latest tag 与本地 `APP_VERSION`）

### `POST /api/version/update` — 触发在线更新

- 鉴权：超管
- 成功：`200 {\"ok\": true, \"message\": \"更新已触发，服务器将自动重启\"}`（异步执行 `update.sh`：下载→备份→覆盖→自动重启）

### `GET /api/version/status` — 更新状态

- 鉴权：超管（后台轮询用）
- 成功：`200 {\"status\": \"idle|running|done\", \"message\": \"...\"}`；无权限：`403`

### `POST /api/webhook/deploy` — 部署 Webhook

- 鉴权：公开（**CSRF 豁免**，但需密钥鉴权）
- 请求头：`X-Deploy-Secret: <与配置相同的密钥>`
- 成功：`200 {\"ok\": true, \"message\": \"部署已触发\"}`；密钥错误：`401`

---

## 如何新增一个 API

1. 按功能归属，选择对应模块（或新建 `myblog/api/xxx.py`）；
2. 在模块内：
   ```python
   from .common import api_bp, db, _current_user_or_none, ...

   @api_bp.route(\"/your-route\", methods=[\"POST\"])
   def your_handler():
       ...   # 返回 jsonify(...)
   ```
3. 若是新模块，在 `myblog/api/__init__.py` 的导入清单追加 `from . import xxx`；
4. 涉及共享逻辑（当前用户、序列化、CSRF）一律复用 `common.py`，不要跨模块 import；
5. 更新本文档对应章节，并在 README 的 API 小节登记。

## 常见错误码速查

| 状态码 | 含义 |
|--------|------|
| `200` | 成功 |
| `201` | 创建成功 |
| `400` | 参数错误/业务校验失败/验证码未过 |
| `401` | 未登录或凭据错误 |
| `403` | 无权限 / CSRF 缺失 / 站点禁用某功能 |
| `404` | 资源不存在 |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |