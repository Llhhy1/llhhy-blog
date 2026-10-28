# llhhy-blog API 文档

> 版本：**v5.2.6**（2026-10-28 全量重写：按 Flask `url_map` 枚举真实路由，逐条回源码核对）
>
> 本文档描述 llhhy-blog 的全部 JSON 接口（`/api/*`，共 **176 条**）与后台页面调用的
> JSON 接口（`/admin/*`，共 **17 条**）。前端（`vue-frontend/src/lib/api.js`）与本站页面
> 共用这些接口；你也可以用它们定制自己的客户端、App 或第三方应用。
>
> **本文档怎么来的**：路由清单由 `app.url_map` 枚举得出（不靠人工回忆），
> 每条接口的鉴权级别、请求参数、返回字段、错误码都**逐条回源码核对**过。
> 如果你改了接口，记得同步这里 —— 前台 `/docs` 页把本文件当作「完整清单」引用。

## 目录

- [通用约定](#通用约定)
- [模块结构](#模块结构)
- [认证与验证码 /auth](#认证与验证码-auth)（17 条）
- [站点信息 /site](#站点信息-site)（4 条）
- [文章 /posts](#文章-posts)（17 条）
- [统计 /stats](#统计-stats)（8 条）
- [社交广场 /social](#社交广场-social)（6 条）
- [专题 /series](#专题-series)（2 条）
- [留言墙 /guestbook](#留言墙-guestbook)（3 条）
- [邮件订阅 /subscribe](#邮件订阅-subscribe)（2 条）
- [站内通知 /notifications](#站内通知-notifications)（3 条）
- [移动端管理 /mobile](#移动端管理-mobile)（74 条）
- [相册 /album](#相册-album)（2 条）
- [公开媒体 /media](#公开媒体-media)（3 条）
- [AI 摘要 /ai](#ai-摘要-ai)（2 条）
- [生态统计 /ecosystem](#生态统计-ecosystem)（2 条）
- [分享卡与爬虫通道 /og](#分享卡与爬虫通道-og)（4 条）
- [列表页壳页 /og/page](#列表页壳页-ogpage)（1 条）
- [天气 /weather](#天气-weather)（1 条）
- [评论表情 /reactions](#评论表情-reactions)（2 条）
- [读者积分 /reader](#读者积分-reader)（2 条）
- [回顾与地域 /review](#回顾与地域-review)（4 条）
- [主题中心 /theme](#主题中心-theme)（2 条）
- [插件 /plugins](#插件-plugins)（4 条）
- [系统与版本 /system](#系统与版本-system)（5 条）
- [后台 JSON 接口 /admin](#后台-json-接口-admin)（17 条）
- [如何新增一个 API](#如何新增一个-api)
- [常见错误码速查](#常见错误码速查)

---

## 通用约定

### 1. 基地址与返回格式

- 所有接口前缀为 `/api`，例如 `POST /api/auth/login`。
- 成功返回 `200`（创建类有时为 `201`），带 `JSON` 响应体。
- 错误统一返回 JSON：`{"error": "<原因>"}`，状态码见各端点。
- **少数接口不返回 JSON**：`/api/og/*`、`/api/qr`、`/api/geo/china.json`、
  `/api/rss/*`（XML）、`/api/seo/shell-check` 之外的壳页，以及后台 `/admin/mcp-services/*`
  （成功时 `302` 跳回列表页）。各条目已单独标注。
- 所有响应均带统一安全头（CSP、X-Frame-Options 等，见 `security.py`）。

### 2. 鉴权方式

| 级别 | 说明 | 未登录 / 无权时 |
|------|------|----------------|
| 公开 | 无需登录即可访问 | — |
| 公开（降级） | 未登录时不报错，返回空结果 | `200` + 空数据 |
| 登录 | 需登录（会话 Cookie 或 `X-User-Id` 头） | `401 {"error": "请先登录"}` |
| 管理员 | 需管理员或超管 | `401` / `403 {"error": "需要管理员权限"}` |
| 超管 | 仅超级管理员 | `401` / `403 {"error": "仅超级管理员可执行该操作"}` |

登录后，Flask session 与前端 `X-User-Id` 头共用同一会话（见 `_login_user`）。

**「按对象归属分权」**：部分登录级接口不是「登录就能用」，而是**按资源归属**再判一次
——管理员可操作全部，普通用户仅能操作 `author_id` 为自己的文章。
这类接口在各条目里写明（如 `POST /api/mobile/post/<id>`）。

### 3. CSRF 保护

- **仅对写操作（POST / PUT / DELETE / PATCH）生效**，GET 豁免。
- 写法：先 `GET /api/csrf`（或 `GET /api/auth/me`）取 token，再在写请求头带
  `X-CSRF-Token: <token>`；token 也可放在 JSON body 的 `csrf_token` 字段或表单 `csrf_token` 字段。
- 失败：`403 {"error": "CSRF 校验失败，请刷新页面后重试"}`。
- **豁免白名单**（写操作无需 token）：
  `/api/webhook/deploy`、`/api/captcha`（前缀匹配，其下路径全部豁免）、`/api/captcha/verify`、
  `/api/stats/read`、`/api/stats/visit`、`/api/stats/search`、`/api/ecosystem/heartbeat`、
  `/mcp`、`/mcp-write`。
- 另有同源校验：`403 {"error": "跨站请求被拒绝"}`。

### 4. 两道全局闸门

| 闸门 | 触发条件 | 响应 |
|------|----------|------|
| 两步验证 | 账号已绑定 2FA 但本会话未过第二因素 | `401 {"error": "twofa_required", "twofa_required": true}` |
| 反爬黑名单 | 访客 IP 在封禁名单里 | `429 {"error": "Too Many Requests"}`（带 `Retry-After: 60`） |

2FA 闸门放行：`/api/auth/2fa/verify`、`/api/auth/2fa/status`、`/api/auth/logout`、
`/api/auth/me`、`/api/csrf`。

### 5. 分页

**各接口的分页参数不统一**，请以每条说明为准 —— 常见的几种：

| 形式 | 接口举例 |
|------|----------|
| `?page=N&per_page=M` | `/api/mobile/*` 绝大多数列表接口（`per_page` 默认 15~20，上限 100） |
| `?page=N&size=M` | `/api/albums`、`/api/media/list`、`/admin/albums/media-picker`（`size` 上限 24~60） |
| `?page=N`（每页固定 20） | `/api/moments`、`/api/guestbook` |
| 服务端配置决定 | `/api/posts`（`POSTS_PER_PAGE`，默认 8，**不接受 `per_page` 参数**） |
| 不分页 | `/api/categories`、`/api/tags`、`/api/series`、`/api/archive` 等 |

### 6. 限流

部分接口有限流（`utils.rate_limit`），超限返回 `429`。常见阈值：登录/注册 10 次/分钟、
微动态发布 5 次/分钟、留言与评论 10 次/分钟、点赞 20 次/分钟、搜索记录 120 次/小时、
阅读记录 60 次/分钟、访客上报 30 次/分钟。部分接口超限**不报错**，只返回 `200`
并附 `"skipped": true`（如 `/api/stats/visit`、`/api/stats/read`）。

各接口的具体阈值写在对应条目的「失败」行里。

### 7. 错误响应格式

`/api/*` 下的 404 / 405 / 403 / 422 / 410 等未捕获异常，由 `app.py:_handle_client_error`
统一转成 JSON 信封：

| 状态码 | 响应体 |
|--------|--------|
| 404 | `{"error": "页面或资源不存在"}` |
| 405 | `{"error": "请求方法不被允许"}` |
| 403 | `{"error": "没有访问权限"}` |
| 422 | `{"error": "请求内容无法处理"}` |
| 410 | `{"error": "该页面已由前端 SPA 渲染，服务端不再输出 HTML"}` |

但**各接口自己返回的错误不受此管辖**，仍用各自的文案（见各条目「失败」行）。

---

## 模块结构

API 从单文件 `api.py` 解耦为按功能组织的包：

```
myblog/
├── api/
│   ├── __init__.py      # api_bp 聚合导出（from api import api_bp 兼容）
│   ├── common.py        # 共享辅助（当前用户/登录/CSRF/序列化器等）
│   ├── auth.py          # 认证、验证码、OAuth、两步验证
│   ├── site.py          # 站点信息/友链/公告
│   ├── posts.py         # 文章/分类/标签/归档/评论/搜索/RSS
│   ├── stats.py         # 访问统计埋点与汇总
│   ├── social.py        # 微动态/圈子/社交账号
│   ├── series.py        # 文章专题
│   ├── guestbook.py     # 留言墙
│   ├── subscribe.py     # 邮件订阅/退订
│   ├── notifications.py # 站内通知
│   ├── mobile.py        # 移动端管理接口（后台管理能力的 JSON 版，66 条）
│   ├── mobile_ops.py    # 移动端管理接口的超管/只读部分（8 条）
│   ├── album.py         # 公开相册（列表/详情）
│   ├── media.py         # 公开媒体（列表/单条/分类）
│   ├── ai.py            # 文章 AI 摘要
│   ├── ecosystem.py     # 站点注册表心跳与统计
│   ├── og.py            # 分享卡 PNG / SEO 爬虫通道 / 站点二维码 / 通道自检
│   ├── seo_page.py      # 列表页 SEO 壳页
│   ├── reactions.py     # 评论表情回应
│   ├── reader.py        # 读者积分与勋章
│   ├── review.py        # 年度回顾 / 里程碑 / 访客地域
│   ├── theme.py         # 主题预设与应用
│   └── system.py        # 健康探针/版本更新/部署 webhook
```

- 新增一个功能时：新建 `myblog/api/xxx.py`，从 `common.py` 按需导入，
  在 `__init__.py` 的导入清单中加一行即可，无需改动其他任何文件。
- **不要**在模块间互相 `import`（避免循环依赖）；共享逻辑一律放 `common.py`。
- **`stats` 是独立的项目级模块**（`myblog/stats.py`），不通过 `common.py` 转发。
  若新模块需要 `stats.client_ip()` / `stats.cached_region()` / `stats.record_*()` 等，
  必须在本模块顶部显式 `import stats`（与 `common.py` 一致），
  否则运行时抛 `NameError: name 'stats' is not defined`（拆包时曾因此漏修 5 个模块）。

---

## 认证与验证码 /auth

本模块共 17 条接口（`/api/auth/*` 12 条、`/api/captcha*` 3 条、`/api/csrf` 1 条、`/api/comment/config` 1 条）。

### `GET /api/auth/me` — 当前登录用户

- 鉴权：公开（未登录时返回 `user: null`，不报 401）
- 说明：返回当前会话的用户信息与 CSRF Token；用户不存在时清会话并按未登录返回
- 请求：无
- 成功：`200 {"user": null, "csrf_token": "..."}`（未登录）/ `200 {"user": {...}, "csrf_token": "..."}`（已登录）
- 失败：无（未登录为 200 + `user: null`）

### `GET /api/csrf` — 获取 CSRF Token

- 鉴权：公开
- 说明：返回当前会话的 CSRF Token（不存在则生成并写入会话），写操作需放入 `X-CSRF-Token` 头
- 请求：无
- 成功：`200 {"csrf_token": "..."}`
- 失败：无

### `GET /api/captcha/config` — 验证码配置快照

- 鉴权：公开
- 说明：返回验证码全局开关、PIL 是否可用、以及 register/comment/guestbook 各场景开关，供前端分场景显隐
- 请求：无
- 成功：`200 {"enabled": true, "available": true, "scenes": {"register": true, "comment": true, "guestbook": true}}`
- 失败：无

### `GET /api/comment/config` — 评论配置

- 鉴权：公开
- 说明：返回评论是否要求填写邮箱，供前端动态切换邮箱输入框的 required 属性
- 请求：无
- 成功：`200 {"email_required": false}`
- 失败：无

### `GET /api/captcha` — 图形验证码图片

- 鉴权：公开
- 说明：生成并返回注册/评论/留言场景的验证码 PNG（答案存会话）；PIL 不可用时降级为纯文本模式
- 请求：`?from=<场景>`（`register` / `comment` / `guestbook`，决定是否按场景开关返回图片）
- 成功：`200`（`Content-Type: image/png`，`Cache-Control: no-store`）；PIL 不可用时 `200 {"captcha": "off", "message": "服务器未安装图像库，验证码已降级停用"}`
- 失败：`404 {"error": "验证码未启用"}`（全局关闭或该场景未启用）

### `GET /api/auth/oauth/providers` — 已配置的第三方登录

- 鉴权：公开
- 说明：返回已配置凭据的 OAuth provider 列表（仅 `github` / `google`），前端据此显隐登录按钮
- 请求：无
- 成功：`200 {"providers": ["github"]}`（未配置时为空数组）
- 失败：无

### `GET /api/auth/oauth/<provider>/start` — 发起第三方授权

- 鉴权：公开（20 次/分钟限流）
- 说明：生成 state 并落入会话，返回第三方授权地址；带 `redirect=1` 时直接 302 跳转（无 JS 降级）
- 请求：`?redirect=1`（可选，值为 `1` 时 302 跳转而非返回 JSON）
- 成功：`200 {"authorize_url": "https://..."}`；`?redirect=1` 时 `302` 跳转至 provider
- 失败：`429 {"error": "操作过于频繁，请稍后再试"}`、`503 {"error": "provider_not_configured"}`（provider 非 github/google 或凭据未配置）

### `GET /api/auth/oauth/<provider>/callback` — 第三方授权回调

- 鉴权：公开（成功后建立/绑定登录态；本接口不返回 JSON，只做跳转）
- 说明：校验 state（恒定时间比较 + 600 秒 TTL）后换取 code，登录或绑定第三方账号到当前会话
- 请求：`?state=<值>&code=<授权码>`
- 成功：`302` 跳转首页 `/?oauth=ok`；绑定流程成功时 `302` 跳转 `/admin/oauth-bindings`
- 失败：`302` 跳转 `/?oauth=error`（state 不匹配/过期、缺 code、provider 未配置、绑定冲突等）、`302` 跳转 `/?oauth=rate_limited`（20 次/分钟限流）

### `GET /api/auth/2fa/status` — 两步验证状态

- 鉴权：公开（未登录时 `enrolled` 恒为 false）
- 说明：返回 2FA 全局开关、当前账号绑定状态、剩余恢复码数量，以及本会话是否处于「已过密码、等动态码」的挂起态
- 请求：无
- 成功：`200 {"enabled": true, "enrolled": false, "recovery_codes_left": 0, "pending": false}`
- 失败：无

### `POST /api/auth/register` — 注册

- 鉴权：公开（需 CSRF Token；同 IP 60 秒内最多 10 次）
- 说明：创建普通用户（`role=ROLE_USER`）并直接建立登录态；站点可关闭公开注册
- 请求：body JSON 或 form — `username`、`password`、`email`（可选）、`captcha`（启用验证码时必填或携带一次性票据）
- 成功：`201 {"ok": true, "user": {...}, "csrf_token": "..."}`（`user` 含 `id / username / role / role_label / is_super / is_admin / created_at`）
- 失败：`400 {"error": "用户名和密码不能为空"}` / `400 {"error": "用户名长度需在 2-20 个字符"}` / `400 {"error": "<密码强度提示>"}` / `400 {"error": "请先完成验证码校验"}` / `403 {"error": "本站已关闭公开注册"}` / `409 {"error": "该用户名已被注册"}` / `429 {"error": "操作过于频繁，请稍后再试"}`

### `POST /api/auth/login` — 登录

- 鉴权：公开（需 CSRF Token；同 IP 60 秒内最多 10 次）
- 说明：用户名密码登录；失败统一文案 + 统一延迟防用户名枚举；账号已启用 2FA 时不直接建立登录态
- 请求：body JSON 或 form — `username`、`password`
- 成功：`200 {"ok": true, "user": {...}, "csrf_token": "..."}`；需第二因素时 `200 {"twofa_required": true, "username": "..."}`
- 失败：`401 {"error": "用户名或密码错误"}`、`429 {"error": "尝试过于频繁，请稍后再试"}`

### `POST /api/auth/logout` — 登出

- 鉴权：公开（需 CSRF Token）
- 说明：清除会话中的 `user_id`
- 请求：无
- 成功：`200 {"ok": true}`
- 失败：无

### `POST /api/auth/2fa/verify` — 两步验证（登录第二步）

- 鉴权：公开（需 CSRF Token；需先有「密码已过」的挂起态；10 次/分钟限流）
- 说明：校验挂起态用户的动态码或恢复码，通过后才真正建立登录态并写登录审计
- 请求：body JSON 或 form — `code`（6 位动态码或恢复码）
- 成功：`200 {"ok": true, "user": {...}, "csrf_token": "..."}`
- 失败：`400 {"error": "验证已超时，请重新登录"}`（挂起态不存在或超过 300 秒）、`400 {"error": "验证码或恢复码错误"}`、`404 {"error": "2FA 未启用"}`、`429 {"error": "操作过于频繁，请稍后再试"}`

### `POST /api/auth/2fa/enroll` — 绑定两步验证

- 鉴权：登录（需 CSRF Token；10 次/分钟限流）
- 说明：生成/重置 TOTP 密钥并返回 otpauth URI 与明文密钥（仅此一次展示）
- 请求：body JSON 或 form — `code`（可选，仅当重置一个**已生效**的 2FA 时需要当前动态码或恢复码）
- 成功：`200 {"secret": "...", "provisioning_uri": "otpauth://..."}`（`Cache-Control: no-store`）
- 失败：`401 {"error": "请先登录"}`、`403 {"error": "重置已生效的两步验证需要当前动态码或恢复码"}`、`404 {"error": "2FA 未启用"}`、`429 {"error": "操作过于频繁，请稍后再试"}`、`500 {"error": "密钥加密失败，请联系管理员检查 cryptography 依赖"}`

### `POST /api/auth/2fa/confirm` — 确认绑定两步验证

- 鉴权：登录（需 CSRF Token；10 次/分钟限流）
- 说明：用验证器 App 的 6 位码确认绑定，成功后启用并一次性返回恢复码
- 请求：body JSON 或 form — `code`
- 成功：`200 {"ok": true, "recovery_codes": ["..."]}`
- 失败：`400 {"error": "请先获取绑定密钥"}`、`400 {"error": "验证码错误或已过期"}`、`401 {"error": "请先登录"}`、`404 {"error": "2FA 未启用"}`、`429 {"error": "操作过于频繁，请稍后再试"}`、`500 {"error": "密钥读取失败"}`

### `POST /api/auth/2fa/disable` — 关闭两步验证

- 鉴权：登录（需 CSRF Token；10 次/分钟限流）
- 说明：关闭 2FA 需「密码 + 动态码（或恢复码）」双重确认，防会话被劫持后直接关掉
- 请求：body JSON 或 form — `password`、`code`
- 成功：`200 {"ok": true}`
- 失败：`400 {"error": "未启用两步验证"}`、`400 {"error": "密码错误"}`、`400 {"error": "验证码或恢复码错误"}`、`401 {"error": "请先登录"}`、`404 {"error": "2FA 未启用"}`、`429 {"error": "操作过于频繁，请稍后再试"}`

### `POST /api/captcha/verify` — 校验验证码文本

- 鉴权：公开（**CSRF 豁免**）
- 说明：校验验证码文本，通过后写入会话一次性票据，供注册/评论/留言免再验证
- 请求：body JSON 或 form — `captcha`
- 成功：`200 {"ok": true, "captcha_passed": true}`
- 失败：`400 {"error": "请输入验证码"}`、`400 {"error": "验证码错误，请重新输入"}`

该模块源码位置：`myblog/api/auth.py`

---

## 站点信息 /site

本模块共 4 条接口（站点全局配置、友情链接、友链自助申请、站点公告）。

### `GET /api/site` — 站点全局配置

- 鉴权：公开
- 说明：一次性返回前台所需的站点信息、主题 token、壁纸、分类/标签/友链与统计汇总
- 请求：无
- 成功：`200 {"site_name": "...", "site_title": "...", "site_note": "...", "site_description": "...", "about_content": "...", "footer_text": "...", "beian_code": "...", "accent_color": "...", "weather_city": "...", "weather_lat": "...", "weather_lon": "...", "theme_mode": "...", "theme_radius": "...", "theme_font": "...", "nav_style": "...", "custom_css": "...", "reward_qr_default": "...", "site_lang": "...", "entry": {...}, "entries": [{"label", "label_en", "url", "icon"}], "theme_pack": "...", "theme_tokens": {...}, "theme_dark_tokens": {...}, "wallpaper": {"enabled", "light", "dark", "overlay"}, "site_since": "YYYY-MM-DD", "categories": [{"name", "slug", "count"}], "tags": [{"name", "slug", "count"}], "links": [{"name", "url", "description"}], "stats": {"posts", "views", "comments"}}`
- 失败：无

### `GET /api/links` — 友情链接列表

- 鉴权：公开
- 说明：按 `sort` 排序返回全部友情链接
- 请求：无
- 成功：`200 [{"name": "...", "url": "...", "description": "..."}]`
- 失败：无

### `GET /api/announcements` — 站点公告列表

- 鉴权：公开
- 说明：返回启用中的站点公告（Markdown 渲染并清洗 HTML），按创建时间倒序
- 请求：无
- 成功：`200 {"items": [{"id": 1, "content": "...", "level": "info", "dismissible": true}]}`
- 失败：无

### `POST /api/link-apply` — 友情链接自助申请

- 鉴权：公开（需 CSRF Token；同 IP 24 小时内最多 10 次）
- 说明：访客提交友链申请进入待审核队列（不直接写友链表）；同一 URL 未处理的申请不重复接收
- 请求：body JSON 或 form — `name`、`url`、`description`（可选）、`email`（可选）
- 成功：`201 {"ok": true, "message": "申请已提交，管理员审核通过后会展示在友情链接"}`；重复申请 `201 {"ok": true, "message": "该链接已在审核队列中，请耐心等待"}`
- 失败：`400 {"error": "站点名称和链接不能为空"}`、`400 {"error": "链接格式不正确（需以 http:// 或 https:// 开头）"}`、`429 {"error": "申请过于频繁，请 24 小时后再试"}`

该模块源码位置：`myblog/api/site.py`

---

## 社交广场 /social

本模块共 6 条接口（微动态列表/发布/点赞/评论、博客圈 RSS 聚合、作者社交账号墙）。

### `GET /api/moments` — 微动态列表

- 鉴权：公开
- 说明：微动态按时间倒序分页返回（每页固定 20 条）
- 请求：`?page=<页码>`（默认 1）
- 成功：`200 {"items": [{"id", "author", "content", "created_at", "likes", "comments": [...]}], "page": 1, "pages": 3, "total": 42}`
- 失败：无

### `GET /api/feed/circle` — 博客圈 RSS 聚合

- 鉴权：公开
- 说明：抓取友链站点 RSS 按时间混排（带缓存与 SSRF 防护），并附诊断块
- 请求：`?refresh=1`（可选，忽略缓存强制重新抓取）
- 成功：`200 {"items": [{"title", "link", "source"}], "debug": {"total_links", "links_with_rss", "feedparser_ok", "fetched", "skipped", "last_run", "notes": [...]}}`
- 失败：无（聚合异常时仍返回 `200`，`items` 为空且 `debug.error` 给出异常 repr）

### `GET /api/social-accounts` — 作者社交账号墙

- 鉴权：公开
- 说明：返回按 `sort` 排序的社交账号列表（广场页「关注」标签用）
- 请求：无
- 成功：`200 [{"id": 1, "platform": "github", "handle": "...", "url": "..."}]`
- 失败：无

### `POST /api/moment` — 发布微动态

- 鉴权：登录（需 CSRF Token；20 次/分钟限流）
- 说明：发布一条纯文本微动态（前端渲染时转义防 XSS）
- 请求：body JSON 或 form — `content`（非空且不超过 500 字）
- 成功：`201 {"ok": true, "moment": {"id", "author", "content", "created_at", "likes", "comments"}}`
- 失败：`400 {"error": "动态内容不能为空"}`、`400 {"error": "动态最多 500 字"}`、`401 {"error": "请先登录"}`、`429 {"error": "操作过于频繁，请稍后再试"}`

### `POST /api/moment/<int:mid>/like` — 微动态点赞

- 鉴权：公开（需 CSRF Token；同动态 20 次/分钟限流）
- 说明：给微动态点赞计数 +1
- 请求：路径参数 `mid`（动态 id）
- 成功：`200 {"likes": 12}`
- 失败：`404 {"error": "页面或资源不存在"}`（动态不存在）；超限时不报错，直接返回当前点赞数 `200 {"likes": 12}`

### `POST /api/moment/<int:mid>/comment` — 微动态评论

- 鉴权：公开（需 CSRF Token；10 次/分钟限流）
- 说明：给微动态发表评论；已登录自动用用户名作昵称，否则需在请求体带 `author`
- 请求：路径参数 `mid`（动态 id）；body JSON 或 form — `content`（不超过 500 字）、`author`（未登录时必填）
- 成功：`201 {"ok": true, "comment": {"id", "author", "content", "created_at", "region"}}`
- 失败：`400 {"error": "昵称和评论内容不能为空"}`、`400 {"error": "评论最多 500 字"}`、`404 {"error": "页面或资源不存在"}`、`429 {"error": "评论过于频繁，请稍后再试"}`

该模块源码位置：`myblog/api/social.py`

---

## 留言墙 /guestbook

本模块共 3 条接口（留言列表、发表留言、留言点赞）。

### `GET /api/guestbook` — 留言列表

- 鉴权：公开
- 说明：留言按时间倒序分页返回（每页固定 20 条）
- 请求：`?page=<页码>`（默认 1）
- 成功：`200 {"items": [{"id", "author", "content", "created_at", "likes", "region", "device"}], "page": 1, "pages": 2, "total": 30}`
- 失败：无

### `POST /api/guestbook` — 发表留言

- 鉴权：公开（需 CSRF Token；10 次/分钟限流；启用验证码时需先过验证码）
- 说明：匿名或登录用户均可留言；内容走敏感词过滤（与评论共用词表），昵称截断 80 字
- 请求：body JSON 或 form — `content`（非空且不超过 500 字）、`author`（未登录时必填）、`captcha`（启用验证码时必填或携带一次性票据）
- 成功：`201 {"ok": true, "guestbook": {"id", "author", "content", "created_at", "likes", "region", "device"}}`
- 失败：`400 {"error": "请先完成验证码校验"}`、`400 {"error": "昵称和留言内容不能为空"}`、`400 {"error": "留言最多 500 字"}`、`400 {"error": "留言包含不被允许的词汇，已被过滤"}`、`429 {"error": "留言过于频繁，请稍后再试"}`

### `POST /api/guestbook/<int:gid>/like` — 留言点赞

- 鉴权：公开（需 CSRF Token；同留言 20 次/分钟限流）
- 说明：给留言点赞计数 +1
- 请求：路径参数 `gid`（留言 id）
- 成功：`200 {"likes": 5}`
- 失败：`404 {"error": "页面或资源不存在"}`（留言不存在）；超限时返回当前点赞数 `200 {"likes": 5}`

该模块源码位置：`myblog/api/guestbook.py`

---

## 邮件订阅 /subscribe

本模块共 2 条接口（订阅、退订）。

### `POST /api/subscribe` — 邮件订阅

- 鉴权：公开（需 CSRF Token；10 次/分钟限流）
- 说明：登记邮箱订阅新文章通知；重复订阅时补写退订令牌
- 请求：body JSON 或 form — `email`（合法邮箱，会转小写存储）
- 成功：`201 {"ok": true, "message": "订阅成功，新文章发布时会邮件通知你"}`；已订阅 `200 {"ok": true, "message": "你已经订阅过啦"}`
- 失败：`400 {"error": "邮箱格式不正确"}`、`429 {"error": "操作过于频繁，请稍后再试"}`

### `GET /api/unsubscribe` — 查询退订状态

- 鉴权：公开（GET 不校验 CSRF）
- 说明：凭邮箱 + 退订令牌查询订阅状态，提示改用 POST 确认退订；令牌错误与邮箱不存在返回同一文案，避免枚举邮箱
- 请求：`?email=<邮箱>&token=<退订令牌>`（GET 与 POST 均从 query 读取）
- 成功：`200 {"ok": true, "email": "...", "active": true, "message": "确认退订？请用 POST 请求确认"}`
- 失败：`400 {"error": "退订链接不完整"}`（缺 email 或 token）、`404 {"error": "退订链接无效或已失效"}`

### `POST /api/unsubscribe` — 执行退订

- 鉴权：公开（需 CSRF Token；10 次/分钟限流）
- 说明：凭邮箱 + 退订令牌取消订阅，将 `active` 置为 false
- 请求：query — `email=<邮箱>&token=<退订令牌>`（该接口只读 query，不读 body）
- 成功：`200 {"ok": true, "message": "已退订，不再发送新文章邮件"}`
- 失败：`400 {"error": "退订链接不完整"}`、`404 {"error": "退订链接无效或已失效"}`、`429 {"error": "操作过于频繁，请稍后再试"}`

该模块源码位置：`myblog/api/subscribe.py`

---

## 站内通知 /notifications

本模块共 3 条接口（通知列表、单条已读、全部已读）。

### `GET /api/notifications` — 通知列表

- 鉴权：公开（未登录时返回空列表，不报 401）
- 说明：返回当前用户的未读通知数与最近 20 条通知（评论 @ 提醒等）
- 请求：无
- 成功：`200 {"unread": 3, "items": [{"id", "content", "link", "is_read", "created_at"}]}`
- 失败：无

### `POST /api/notification/<int:nid>/read` — 标记单条通知已读

- 鉴权：登录（需 CSRF Token）
- 说明：把当前用户的一条通知标记为已读（非本人通知按不存在处理）
- 请求：路径参数 `nid`（通知 id）
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}`、`404 {"error": "页面或资源不存在"}`

### `POST /api/notifications/read-all` — 全部通知标记已读

- 鉴权：登录（需 CSRF Token）
- 说明：把当前用户所有未读通知批量标记为已读
- 请求：无
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}`

该模块源码位置：`myblog/api/notifications.py`

---

## 主题中心 /theme

本模块共 2 条接口（主题预设读取、应用主题/壁纸）。

### `GET /api/theme` — 主题预设与当前主题

- 鉴权：公开
- 说明：返回全部预设主题包（亮/暗 token）+ 当前激活的 pack_id + 当前壁纸配置
- 请求：无
- 成功：`200 {"presets": [{"id", "name", "en", "desc", "tags", "light", "dark"}], "current": {"pack_id": "classic-blue"}, "wallpaper": {"enabled", "light", "dark", "overlay"}}`
- 失败：无

### `POST /api/theme` — 应用主题 / 设置壁纸

- 鉴权：超管（需 CSRF Token）
- 说明：应用预设主题包或自定义主题 token，并可单独设置首页壁纸；写 Setting 并记审计日志
- 请求：body JSON — `pack_id`（预设 id，如 `classic-blue`）、`custom`（`{light:{...}, dark?:{...}}` 或单层 token 对象，须含 `accent`）、`wallpaper`（`{enabled, light, dark, overlay}`，图片路径仅接受 `/static/uploads/` 下的单层文件名）；三者可组合，只带 `wallpaper` 即为纯壁纸请求
- 成功：`200 {"ok": true, "pack_id": "classic-blue", "theme_tokens": {...}, "theme_dark_tokens": {...}, "wallpaper": {"enabled", "light", "dark", "overlay"}}`
- 失败：`403 {"error": "forbidden"}`（非超管）、`400 {"error": "invalid custom theme"}`、`400 {"error": "custom theme requires light.accent"}`、`400 {"error": "unknown pack_id"}`、`400 {"error": "invalid wallpaper"}`、`400 {"error": "启用壁纸前请先上传至少一张图片"}`

该模块源码位置：`myblog/api/theme.py`

---

## 文章 /posts

本模块共 17 条接口（文章、分类、标签、归档、评论、搜索与 RSS）。

> 文章卡片字段（来自 `api/common.py:_post_summary`）：
> `slug / title / author / summary / cover / created_at / views / likes / is_pinned /
> seo_description / seo_keywords / category{name,slug} / tags[{name,slug}] /
> word_count / reading_minutes / reward_enabled / is_private / lang / translation_group`
> （**不含** `id` 与 `excerpt`）。
>
> 评论字段（来自 `api/common.py:_comment`）：
> `id / author / content / created_at / region / device / parent_id / depth / reply_to / likes / avatar`

### `GET /api/posts` — 文章列表（分页、搜索、多语言去重）

- 鉴权：公开
- 说明：分页返回前台可见文章；`q` 在标题/摘要/正文中做模糊匹配；`lang` 触发同组多语言去重。**每页条数取服务端配置 `POSTS_PER_PAGE`（默认 8），不接受 `per_page` 查询参数**
- 请求：`?page=1`、`?q=关键词`、`?lang=zh`（均可选）
- 成功：`200 {"items": [<文章卡片>...], "page": 1, "pages": 3, "total": 20, "per_page": 8}`
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/post/<slug>` — 文章详情（正文 + 已通过审核的评论）

- 鉴权：公开（私密文章仅超级管理员可见，其余一律 404）
- 说明：返回文章卡片字段 + 渲染后的正文 HTML + 已审核评论 + 系列上下篇 + 多语言入口。**本接口会写库**：同 IP 24 小时内对同一篇只计一次阅读量（`views += 1`），并给读者加阅读积分（首次访问会下发 `reader_token` Cookie）
- 请求：`?lang=en`（可选，请求同组译文；不可见则回退本篇）
- 成功：`200 {<文章卡片字段>, "html": "<正文 HTML>", "comments": [<评论>...], "series": {"slug": "...", "name": "...", "prev": {"slug", "title"} | null, "next": {...} | null} | null, "lang": "zh", "translation_group": "...", "translations": [{"lang", "slug", "title"}]}`
- 失败：`404 {"error": "页面或资源不存在"}`

### `GET /api/categories` — 分类列表

- 鉴权：公开
- 说明：列出全部分类并附前台可见文章数（无可见文章的分类也列出，`count=0`）；限流 120 次/分钟
- 请求：无
- 成功：`200 [{"name": "...", "slug": "...", "count": 5}]`（**不含 `id`**）
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/tags` — 标签列表

- 鉴权：公开
- 说明：列出全部标签并附文章数；**统计口径含全部文章（含回收站/私密）**，与 `/api/hot-tags` 的可见文章口径不同。限流 120 次/分钟
- 请求：无
- 成功：`200 [{"name": "...", "slug": "...", "count": 3}]`（**不含 `id`**）
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/hot-tags` — 热门标签

- 鉴权：公开
- 说明：按「文章数 × 2 + 总阅读量/1000」权重排序取前 N，只统计前台可见文章
- 请求：`?limit=20`（可选，默认 20，`<=0` 或 `>50` 回落为 20）
- 成功：`200 {"items": [{"name": "...", "slug": "...", "count": 3, "views": 1200, "weight": 7}]}`（**是对象包裹，不是裸数组**；无数据时 `{"items": []}`）
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/category/<slug>` — 分类下的文章

- 鉴权：公开
- 说明：列出该分类下全部前台可见文章（不分页），可按语言去重；限流 120 次/分钟
- 请求：`?lang=zh`（可选，用于同组多语言去重）
- 成功：`200 {"name": "...", "slug": "...", "items": [<文章卡片>...]}`
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/tag/<slug>` — 标签下的文章

- 鉴权：公开
- 说明：列出带该标签的全部前台可见文章（不分页），可按语言去重；限流 120 次/分钟
- 请求：`?lang=zh`（可选）
- 成功：`200 {"name": "...", "slug": "...", "items": [<文章卡片>...]}`
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/rss/category/<slug>` — 分类 RSS

- 鉴权：公开
- 说明：该分类下前台可见文章的 RSS 2.0 订阅源，最多 20 篇（置顶优先）；含作者/分类元数据与译文组 hreflang 互链
- 请求：无
- 成功：`200`，`Content-Type: application/rss+xml`
- 失败：`404 {"error": "页面或资源不存在"}`

### `GET /api/rss/tag/<slug>` — 标签 RSS

- 鉴权：公开
- 说明：带该标签的前台可见文章的 RSS 2.0 订阅源，最多 20 篇（置顶优先）
- 请求：无
- 成功：`200`，`Content-Type: application/rss+xml`
- 失败：`404 {"error": "页面或资源不存在"}`

### `GET /api/archive` — 归档时间线（按年月分组）

- 鉴权：公开
- 说明：把全部前台可见文章按「年 → 月」分组输出，用于归档页；不分页，限流 30 次/分钟
- 请求：无
- 成功：`200 [{"year": "2026", "months": [{"month": "01", "posts": [<文章卡片>...]}]}]`（`year` / `month` 均为字符串）
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`

### `POST /api/post/<slug>/like` — 点赞

- 鉴权：公开（需 CSRF Token）
- 说明：对文章 `likes` 计数 +1 并落库；**只支持加，没有取关参数**。同一 IP 对同一篇 60 秒内最多 20 次
- 请求：无
- 成功：`200 {"likes": 13}`（超限时同样返回 `200` 与当前 `likes`，只是不累加）
- 失败：`404 {"error": "页面或资源不存在"}`

### `POST /api/post/<slug>/comment` — 发表评论

- 鉴权：公开（已登录自动取会话用户名；未登录须传 `author`）
- 说明：写入评论并按设置决定是否进入待审核；记录 IP 属地与设备；触发插件事件与站内 @ 通知；给读者加评论积分
- 请求：JSON 或表单，字段 `content`（必填，≤2000 字）、`author`（未登录必填）、`email`（可选，仅存 MD5 哈希）、`parent_id`（可选，必须属于同一篇文章）、`reply_to`（可选）、`captcha`（站点开启评论验证码时必填）
- 成功：`201 {"ok": true, "comment": {<评论字段>}, "pending": false}`（`pending` 为是否需审核）
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "评论过于频繁，请稍后再试"}`；`400 {"error": "请先完成验证码校验"}`；`400 {"error": "评论最多 2000 字"}`；`400 {"error": "昵称和评论内容不能为空"}`；`400 {"error": "请填写有效的电子邮箱"}`；`400 {"error": "评论包含不被允许的词汇，已被过滤"}`；`400 {"error": "回复的评论不存在"}`

### `GET /api/post/<slug>/comments` — 评论分页与完整嵌套

- 鉴权：公开
- 说明：只返回已审核评论；一次性取全量后按 `parent_id` 建索引做深度优先展开，回复的回复（第三层及更深）也能读回；`total` 只计顶层评论
- 请求：`?per_page=20`（可选，默认 20，`<=0` 或 `>50` 回落 20）、`?page=1`、`?sort=old`（可选，`old`（默认，正序）/ `new` / `hot`，未知键回落 `old`）、`?max_depth=4`（可选，默认 4，`<=0` 或 `>8` 回落 4；仅作为折叠阈值回传，后端不裁剪数据）
- 成功：`200 {"items": [{<评论字段>, "depth": N}], "page": 1, "per_page": 20, "total": 12, "pages": 1, "has_more": false, "sort": "old", "max_depth": 4}`
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/post/<slug>/related` — 相关文章推荐

- 鉴权：公开
- 说明：按「标签重合数 + 同分类 1 分」打分，只返回前台可见文章，取前 5 篇
- 请求：无
- 成功：`200 {"items": [<文章卡片>...]}`（最多 5 篇）
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/post/<slug>/also-viewed` — 「看了又看」协同过滤推荐

- 鉴权：公开
- 说明：按「共同阅读人数 + 0.5×（标签重合数 + 同分类）」打分，只返回前台可见文章，取前 5 篇
- 请求：无
- 成功：`200 {"items": [<文章卡片>...]}`（最多 5 篇）
- 失败：`404 {"error": "页面或资源不存在"}`；`429 {"error": "请求过于频繁，请稍后再试"}`

### `GET /api/search` — 全文搜索

- 鉴权：公开
- 说明：优先走 SQLite FTS5（`engine: "fts5"`），无命中或不可用时回退 LIKE 模糊匹配（`engine: "like"`）；命中项附 `<mark>` 高亮片段
- 请求：`?q=关键词`（必填，为空直接返回空结果且 `engine: "none"`）、`?page=1`、`?per_page=10`（可选，默认 10，`<=0` 或 `>50` 回落 10）
- 成功：`200 {"items": [{<文章卡片>, "highlight": "<mark>命中</mark>..."}], "total": 5, "pages": 1, "page": 1, "engine": "fts5", "query": "关键词"}`
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`（60 次/分钟）

### `POST /api/post/<int:post_id>/publish-now` — 定时文章立即发布

- 鉴权：登录（且需对该文章有编辑权：管理员可操作全部，普通用户仅能操作 `author_id` 为自己的文章）
- 说明：清空 `scheduled_at` 并翻为已发布，触发新文章推送与订阅者邮件群发（均静默失败）
- 请求：无（路径参数 `post_id`）
- 成功：`200 {"ok": true, "message": "已立即发布", "published": true}`；文章已是发布态：`200 {"ok": true, "message": "文章已处于发布状态", "published": true}`
- 失败：`401 {"error": "请先登录"}`；`404 {"error": "文章不存在"}`；`403 {"error": "没有权限操作这篇文章"}`

该模块源码位置：`myblog/api/posts.py`

---

## 统计 /stats

本模块共 8 条接口（访问埋点与统计汇总）。

> ⚠️ `/api/stats/visit`、`/api/stats/search`、`/api/stats/read` 虽为公开接口，但**都会写库**
> （分别写 `VisitLog`、`SearchLog`、`ReadLog`），是匿名埋点信标。

### `POST /api/stats/visit` — 上报访问

- 鉴权：公开（**会写库**：写 `VisitLog`，并给读者加每日访问积分，首次访问会下发 `reader_token` Cookie）
- 说明：前端每次路由变化上报一次；`path` 以 `/admin` 开头直接跳过；referrer 只保留 origin 入库
- 请求：JSON 字段 `path`（访问路径，截断 255 字符）、`referrer`（可选，截断 500 字符）、`post_id`（可选，非数字则忽略）
- 成功：`200 {"ok": true}`
- 失败：无（超限或 `/admin` 路径返回 `200 {"ok": true, "skipped": true}`）
- CSRF：**豁免**

### `POST /api/stats/search` — 记录搜索词

- 鉴权：公开（**会写库**：写 `SearchLog`）
- 说明：记录一次搜索关键词（截断到 120 字，空词不记录）；限流 120 次/小时
- 请求：JSON 字段 `keyword`
- 成功：`200 {"ok": true}`
- 失败：无（超限返回 `200 {"ok": true, "skipped": true}`）
- CSRF：**豁免**

### `POST /api/stats/read` — 记录文章阅读

- 鉴权：公开（**会写库**：写 `ReadLog`）
- 说明：按 slug 累加阅读次数与停留时长；slug 不可见（私密/未发布/回收站）时静默不计数。限流 60 次/分钟
- 请求：JSON 字段 `slug`（必填）、`duration`（可选，秒，服务端钳制到 0~7200）、`only_duration`（可选，`true` 时只补停留时长不累加阅读次数）
- 成功：`200 {"ok": true}`
- 失败：无（超限返回 `200 {"ok": true, "skipped": true}`）
- CSRF：**豁免**

### `GET /api/stats/summary` — 统计汇总

- 鉴权：公开
- 说明：累计访问、区域排行、热读文章、常搜词、时段分布、访客趋势、爬虫分布与环比等只读聚合；限流 30 次/分钟（成本较高）
- 请求：无
- 成功：`200 {"total_visits", "today_visits", "today_date", "regions_today", "regions_all", "hot_posts", "hot_searches", "avg_read_seconds", "hourly", "trend", "bot_visits", "human_visits", "bot_today", "bot_breakdown", "referrers", "devices", "browsers", "online", "compare", "updated_at"}`（`hot_posts` 项为 `{"slug", "title", "reads", "readers"}`，`hot_searches` 项为 `{"keyword", "count"}`，`hourly` 为 24 个 `{"hour", "count"}`，`trend` 为 `{"date", "pv", "uv"}` 序列）
- 失败：`429 {"error": "too_many_requests"}`；`500 {"error": "internal_error"}`

### `GET /api/stats/trend` — 访客趋势（PV / UV）

- 鉴权：公开
- 说明：最近 N 天按天聚合的总访问次数（PV）与独立访客数（UV），缺失日期补 0
- 请求：`?days=30`（可选，默认 30，`<=0` 或 `>90` 回落 30）
- 成功：`200 {"trend": [{"date": "2026-01-01", "pv": 12, "uv": 8}]}`
- 失败：无

### `GET /api/stats/dashboard` — 运营驾驶舱聚合

- 鉴权：公开
- 说明：核心指标 + 环比 + 区间趋势（只读聚合，单指标失败静默降级为 0）；限流 30 次/分钟
- 请求：`?range=30`（可选，仅接受 7 / 30 / 90，非法值回落 30；只影响趋势序列区间，卡片恒为「今日」快照 + 环比）
- 成功：`200 {"generated_at": "...", "metrics": {"pv_today", "uv_today", "subs_total", "comments_total", "comments_unread", "posts_total", "new_subs_today", "new_subs_week", "new_comments_today", "new_comments_week", "new_posts_today", "new_posts_week"}, "deltas": {"pv_dod", "pv_wow", "uv_dod", "uv_wow", "subs_dod", "subs_wow", "comments_dod", "comments_wow", "posts_dod", "posts_wow"}, "hot_reads": [...], "hot_searches": [...], "active_regions": [...], "trend": [{"date", "pv", "uv", "comments", "posts"}], "hourly": [...], "regions_today": [...], "regions_all": [...], "total_visits": N, "today_visits": N, "today_date": "YYYY-MM-DD"}`
- 失败：`429 {"error": "too_many_requests"}`；`500 {"error": "dashboard_failed"}`

### `GET /api/stats/online` — 当前在线访客数（近似值）

- 鉴权：公开
- 说明：近 10 分钟内的独立 IP 数（排除 bot），**是近似值不是精确在线人数**；限流 30 次/分钟
- 请求：无
- 成功：`200 {"online": 12, "approx": true}`
- 失败：无（超限不报错，返回 `200 {"online": 0, "approx": true}`）

### `GET /api/stats/referrers` — 访客来源 TOP

- 鉴权：公开
- 说明：按 referrer origin 聚合，排除 bot 与本站自引用（`site_url` 设置 + 当前 host）；直接访问数单列为 `direct`
- 请求：`?days=30`（可选，默认 30，钳制到 1~365）
- 成功：`200 {"days": 30, "direct": 42, "items": [{"source": "https://example.com", "count": 8}]}`（`items` 最多 10 条）
- 失败：无

该模块源码位置：`myblog/api/stats.py`

---

## 专题 /series

本模块共 2 条接口（文章系列）。

### `GET /api/series` — 系列列表

- 鉴权：公开
- 说明：列出全部系列，附前台可见文章数
- 请求：无
- 成功：`200 [{"slug": "...", "name": "...", "description": "...", "cover": "...", "count": 4}]`
- 失败：无

### `GET /api/series/<slug>` — 系列详情与文章列表

- 鉴权：公开
- 说明：返回系列元信息与该系列下全部前台可见文章（按创建时间正序，不分页）
- 请求：无
- 成功：`200 {"slug": "...", "name": "...", "description": "...", "cover": "...", "posts": [<文章卡片>...]}`
- 失败：`404 {"error": "页面或资源不存在"}`

该模块源码位置：`myblog/api/series.py`

---

## 评论表情 /reactions

本模块共 2 条接口（评论表情回应）。

### `GET /api/comments/reactions` — 批量回读表情计数

- 鉴权：公开
- 说明：按评论 id 批量回读表情计数，避免前端 N+1 请求；同时返回允许使用的表情白名单
- 请求：`?ids=1,2,3`（可选，逗号分隔，最多取前 300 个）
- 成功：`200 {"allowed": ["👍", "❤️", "😂", "🎉", "🤔", "👏"], "items": {"1": {"👍": 2}}}`
- 失败：无

### `POST /api/comments/<int:cid>/reactions` — 对评论加/减表情

- 鉴权：公开（匿名可用，与发表评论一致；需 CSRF Token）
- 说明：计数存于该评论自身的 `Comment.reactions` 字段（JSON），每条评论独立、互不干扰；仅允许对「已审核」的评论回应；同一 IP 60 秒内最多 40 次。注：所属文章当前不可见时计数不落库
- 请求：JSON 字段 `emoji`（必填，须在白名单内）、`action`（可选，`add` 默认 / `remove`）
- 成功：`200 {"ok": true, "counts": {"👍": 3}}`
- 失败：`429 {"error": "操作过于频繁，请稍后再试"}`；`404 {"error": "评论不存在"}`（评论不存在或未审核通过）；`400 {"error": "不支持的表情"}`

该模块源码位置：`myblog/api/reactions.py`

---

## 读者积分 /reader

本模块共 2 条接口（读者积分与勋章）。

### `GET /api/reader/leaderboard` — 公开积分排行榜

- 鉴权：公开
- 说明：按积分倒序列出有积分的读者；限流 30 次/分钟
- 请求：`?limit=10`（可选，默认 10，`<=0` 或 `>50` 回落 10）
- 成功：`200 {"items": [{"name": "...", "points": 120, "badges": ["🌱", "📚"]}]}`
- 失败：`429 {"error": "too_many_requests"}`

### `GET /api/reader/me` — 当前读者积分与勋章

- 鉴权：公开（匿名靠 `reader_token` Cookie 识别，登录后绑定 `user_id` 并同步用户名）
- 说明：**会写库** —— 无 Cookie 的请求会新建一行读者档案（故必须限流 60 次/分钟）；首次访问会下发 `reader_token` Cookie
- 请求：无
- 成功：`200 {"reader": {"points": 42, "badges": [{"key": "novice", "name": "初来乍到", "icon": "🌱", "description": "累计 10 积分"}], "name": "读者"}}`
- 失败：`429 {"error": "too_many_requests"}`

该模块源码位置：`myblog/api/reader.py`

---

## 回顾与地域 /review

本模块共 4 条接口（年度回顾、里程碑与访客地域）。

### `GET /api/review/annual` — 年度回顾

- 鉴权：公开
- 说明：按年聚合文章数、阅读量、字数、评论数、访客数、月度分布、热文、分类/标签榜、地域榜与可选年份列表；聚合异常一律降级为空列表，不返回 500
- 请求：`?year=2026`（可选，默认当前年，非法值回落当前年）
- 成功：`200 {"year": 2026, "posts": 12, "views": 3400, "comments": 20, "words": 52000, "visitors": 180, "months": [0,1,...], "hot_posts": [{"title", "slug", "views"}], "categories": [{"name", "slug", "count"}], "tags": [{"name", "slug", "count"}], "regions": [{"region", "count"}], "years": [2026, 2025]}`
- 失败：无

### `GET /api/milestones` — 站点里程碑与成就徽章

- 鉴权：公开
- 说明：纯聚合，无表结构变更；含连续更新天数与开博天数等徽章进度
- 请求：无
- 成功：`200 {"posts": 52, "views": 12000, "comments": 60, "streak": 7, "running_days": 400, "unlocked": 5, "total": 8, "items": [{"id": "sprout", "icon": "🌱", "name": "起步", "desc": "发布第一篇文章", "unlocked": true, "current": 52, "target": 1}]}`
- 失败：无

### `GET /api/geo/visitors` — 访客省份分布

- 鉴权：公开
- 说明：按 `VisitLog.region` 的省级部分聚合，排除 bot；**只返回省级聚合计数，不含 IP 与任何个人位置数据**
- 请求：`?days=30`（可选，默认 30，钳制到 1~365）
- 成功：`200 {"days": 30, "provinces": [{"name": "广东省", "count": 12}]}`
- 失败：无

### `GET /api/geo/china.json` — 中国省级行政区划 GeoJSON 底图

- 鉴权：公开
- 说明：阿里云 DataV 省级行政区划 GeoJSON（含港澳台与南海诸岛，审图号合规数据）；后端磁盘缓存 7 天
- 请求：无
- 成功：`200`，`Content-Type: application/json`，`Cache-Control: public, max-age=86400`（响应体为 GeoJSON 原文）
- 失败：`503 {"error": "底图数据暂不可用"}`

该模块源码位置：`myblog/api/review.py`

---

## 天气 /weather

本模块共 1 条接口（双源容灾天气）。

### `GET /api/weather` — 天气查询（wttr.in 主源 + Open-Meteo 兜底）

- 鉴权：公开
- 说明：免费无需 Key 的双源天气接口。主源 wttr.in（支持中文城市名与坐标），失败时用 Open-Meteo 兜底（WMO code）；坐标模式先反查地名。结果进程内缓存 10 分钟（只缓存成功结果，上游全失败时回吐过期数据）
- 请求：`?city=北京`（可选，≤80 字符）、`?lat=39.9`（可选，-90~90）、`?lon=116.4`（可选，-180~180；`lat`/`lon` 需同时提供且合法才进入坐标模式，否则用后台设置的默认坐标与城市名）
- 成功：`200 {"name": "北京", "city": "北京", "temp": 21.5, "code": 113, "description": "晴", "lat": null, "lon": null}`
- 失败：`429 {"error": "请求过于频繁，请稍后再试"}`（60 次/分钟）；`400 {"error": "城市名过长"}`；`502 {"error": "天气获取失败"}`（上游全失败且无过期缓存）

该模块源码位置：`myblog/routes.py`

---

## 移动端管理 /mobile

本模块共 **74 条**接口（`myblog/api/mobile.py` 66 条 + `myblog/api/mobile_ops.py` 8 条），
是后台管理能力的 JSON 版，供 App / 脚本调用。

> **本组通用约定**
>
> - **鉴权闸门**（`myblog/api/mobile.py:80` 的 `_role(admin=False, super_only=False)`）：
>   未登录 → `401 {"error": "请先登录"}`；
>   超管未改默认密码 → `403 {"error": "请先完成账号安全设置（修改默认密码）"}`；
>   `super_only=True` 且非超管 → `403 {"error": "仅超级管理员可执行该操作"}`；
>   `admin=True` 且非 admin/super → `403 {"error": "需要管理员权限"}`。
> - **CSRF**：所有 POST / PUT / DELETE / PATCH 走全局闸门，失败 → `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`。
> - **2FA**：账号启用第二因素而会话未通过时，`/api/*` 全局闸门 → `401 {"error": "twofa_required"}`。
> - **404 / 405 / 400 等未捕获异常**由 `app.py:_handle_client_error` 转成 JSON `{"error": "<中文短句>"}`。
> - **PII 分层**：访客 IP 原文只在超管响应里出现；订阅者邮箱对管理员遮敏；`unsub_token` 任何角色都不返回。

**概览**

### `GET /api/mobile/overview` — App 首屏概览

- 鉴权：管理员（超管亦可）
- 说明：一次请求拿齐今天的访客数据、待办计数与最近 5 条评论
- 请求：无
- 成功：`200 {"ok": true, "user": {...}, "counts": {...}, "today": {...}, "recent_comments": [...]}`；`counts` 含 `pending_comments` / `unread_comments` / `unread_notifications` / `drafts` / `scheduled` / `pending_links` / `pin_requests` / `trash` / `unread_guestbook`，`today` 含 `today_visits` / `bot_today` / `online` / `total_visits` / `today_date`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `403 {"error": "请先完成账号安全设置（修改默认密码）"}`

**文章**

### `POST /api/mobile/post` — 新建文章

- 鉴权：登录（普通用户只为自己发文；`is_pinned` 仅管理员生效、`is_private` / `reward_*` 仅超管生效、`notify_subscribers` 仅管理员生效）
- 说明：新建文章（草稿 / 直接发布 / 定时），走后台唯一入口 `create_post_core`
- 请求：body `{"title": "..."（必填）, "content", "summary", "cover", "category_id", "new_category_name", "tags", "series_id", "new_series_name", "seo_description", "seo_keywords", "published", "scheduled_at", "is_pinned", "is_private", "reward_enabled", "reward_qr", "notify_subscribers", "lang", "translation_group"}`；`scheduled_at` 为北京时间 `YYYY-MM-DDTHH:MM`
- 成功：`201 {"ok": true, "id": N, "slug": "...", "published": false, "scheduled_at": "..."}`
- 失败：`401 {"error": "请先登录"}` / `400 {"error": "标题不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `GET /api/mobile/posts` — 文章管理列表

- 鉴权：登录（管理员可见全部；普通用户仅自己 `author_id` 的文章）
- 说明：文章管理列表，与后台「文章管理」同筛选口径；不含正文
- 请求：query `?q=`（标题 / 正文关键词）、`?status=published|draft|scheduled|pinned`、`?category_id=N`、`?series_id=N`、`?sort=updated|views|words|title|created`、`?order=asc|desc`、`?page=N`、`?per_page=N`（默认 15，上限 100）
- 成功：`200 {"items": [...], "total": N, "page": P, "pages": P}`；每项含 `id` / `slug` / `title` / `author` / `summary` / `cover` / `created_at` / `views` / `likes` / `is_pinned` / `published` / `in_trash` / `pin_requested` / `scheduled_at` / `updated_at` / `comment_count` / `category_id` / `series_id` / `category` / `tags` / `word_count` / `reading_minutes` / `reward_enabled` / `is_private` / `lang` / `translation_group`
- 失败：`401 {"error": "请先登录"}`

### `GET /api/mobile/post/<int:post_id>` — 文章详情

- 鉴权：登录 + 按对象归属（管理员可看全部；普通用户仅自己 `author_id` 的文章）
- 说明：取文章详情，含 Markdown 原文，供编辑器载入
- 请求：路径参数 `post_id`；无 query / body
- 成功：`200` 返回文章摘要字段 + `id` / `published` / `in_trash` / `pin_requested` / `scheduled_at` / `updated_at` / `comment_count` / `category_id` / `series_id` / `content` / `reward_qr` / `seo_description_raw` / `tag_names` / `url` / `previewable`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能查看自己发表的文章"}` / `404 {"error": "文章不存在"}`

### `POST,PUT /api/mobile/post/<int:post_id>` — 修改文章

- 鉴权：登录 + 按对象归属（管理员可改全部；普通用户仅自己 `author_id` 的文章）
- 说明：整单修改文章（含发布 / 定时状态），走 `update_post_core`；**缺省即清空**，应回传完整表单
- 请求：body `{"title", "summary", "content", "cover", "category_id", "new_category_name", "series_id", "new_series_name", "scheduled_at", "published", "is_pinned", "seo_description", "seo_keywords", "lang", "translation_group", "is_private", "reward_enabled", "reward_qr", "tags"}`；`is_pinned` 仅管理员生效、`is_private` / `reward_*` 仅超管生效
- 成功：`200 {"ok": true, "id": N, "slug": "...", "published": false, "scheduled_at": "..."}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能编辑自己发表的文章"}` / `404 {"error": "文章不存在"}` / `400 {"error": "<update_post_core 校验文案>"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（30 次/分钟）

### `POST /api/mobile/post/<int:post_id>/publish` — 发布文章

- 鉴权：登录 + 按对象归属（管理员可发布全部；普通用户仅自己 `author_id` 的文章）
- 说明：把草稿 / 定时文章翻为已发布，副作用同后台「立即发布」（索引、推送、群发）
- 请求：路径参数 `post_id`；无 query / body
- 成功：`200 {"ok": true, "published": true, "id": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能操作自己发表的文章"}` / `404 {"error": "文章不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/post/<int:post_id>/unpublish` — 撤回为草稿

- 鉴权：登录 + 按对象归属（管理员可操作全部；普通用户仅自己 `author_id` 的文章）
- 说明：撤回为草稿并清空定时时间，同步移除全文检索索引
- 请求：路径参数 `post_id`；无 query / body
- 成功：`200 {"ok": true, "published": false, "id": N}`；已是草稿时 `200 {"ok": true, "published": false, "message": "已是草稿"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能操作自己发表的文章"}` / `404 {"error": "文章不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/post/<int:post_id>/trash` — 移入回收站

- 鉴权：登录 + 按对象归属（管理员可删全部；普通用户仅自己 `author_id` 的文章）
- 说明：软删除文章，快照进回收站，可还原
- 请求：路径参数 `post_id`；无 query / body
- 成功：`200 {"ok": true, "in_trash": true, "id": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能删除自己发表的文章"}` / `404 {"error": "文章不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/post/<int:post_id>/pin` — 置顶 / 取消置顶

- 鉴权：仅超管
- 说明：显式设置置顶目标值（`pinned: true/false`），置顶时清掉置顶申请态
- 请求：body `{"pinned": true}`（必填）
- 成功：`200 {"ok": true, "pinned": true, "id": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}` / `404 {"error": "文章不存在"}` / `400 {"error": "请带上 pinned（true/false）"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**文章版本历史**

### `GET /api/mobile/post/<int:post_id>/history` — 版本历史列表

- 鉴权：登录 + 按对象归属（管理员可见全部；普通用户仅自己 `author_id` 的文章）
- 说明：版本历史列表，时间倒序，不含正文（`size` 是正文字符数）
- 请求：路径参数 `post_id`；无 query / body
- 成功：`200 {"items": [{"id", "post_id", "title", "summary", "author", "created_at", "size"}], "total": N, "post_id": N, "post_title": "...", "current": {"title", "summary", "size"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能查看自己文章的版本历史"}` / `404 {"error": "文章不存在"}`

### `GET /api/mobile/post/<int:post_id>/history/<int:hid>` — 历史版本正文

- 鉴权：登录 + 按对象归属（管理员可见全部；普通用户仅自己 `author_id` 的文章）
- 说明：取某个历史版本的完整正文，供预览 / 逐字比对
- 请求：路径参数 `post_id`、`hid`；无 query / body
- 成功：`200 {"id", "post_id", "title", "summary", "author", "created_at", "size", "content"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能查看自己文章的版本历史"}` / `404 {"error": "文章不存在"}` / `404 {"error": "历史版本不存在"}`

### `GET /api/mobile/post/<int:post_id>/history/diff` — 版本对比

- 鉴权：登录 + 按对象归属（管理员可见全部；普通用户仅自己 `author_id` 的文章）
- 说明：把指定历史版本与**当前正文**做逐行 diff；不指定 `a` 时与最近一版比
- 请求：query `?a=<历史版本 id>`；路径参数 `post_id`
- 成功：`200 {"post_id": N, "base": {...}, "rows": [{"kind", "old", "new"}]}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能查看自己文章的版本对比"}` / `404 {"error": "文章不存在"}` / `404 {"error": "暂无历史版本可对比"}`

### `POST /api/mobile/post/<int:post_id>/history/<int:hid>/rollback` — 回滚到历史版本

- 鉴权：登录 + 按对象归属（管理员可操作全部；普通用户仅自己 `author_id` 的文章）
- 说明：回滚到指定历史版本，只写回 `title` / `summary` / `content`；回滚前先把当前版存入历史，可再撤销
- 请求：路径参数 `post_id`、`hid`；无 query / body
- 成功：`200 {"ok": true, "title": "...", "size": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "只能回滚自己文章的版本"}` / `404 {"error": "文章不存在"}` / `404 {"error": "历史版本不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**分类 / 标签 / 系列**

### `GET /api/mobile/taxonomy` — 编辑器分类 / 系列 / 标签候选

- 鉴权：登录
- 说明：编辑器下拉数据源（与后台编辑页同数据源）
- 请求：无
- 成功：`200 {"categories": [{"id", "name", "slug"}], "series": [{"id", "name", "slug"}], "tags": [{"id", "name", "slug"}]}`；标签最多取 300 条
- 失败：`401 {"error": "请先登录"}`

### `GET /api/mobile/categories` — 分类清单

- 鉴权：管理员（超管亦可）
- 说明：分类列表，每行带文章数，删除前可预知影响面
- 请求：无
- 成功：`200 {"items": [{"id", "name", "slug", "post_count", "url"}], "total": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/category` — 新建分类

- 鉴权：管理员（超管亦可）
- 说明：新建分类，走 `create_category_core`；同名精确判重
- 请求：body `{"name": "..."}`
- 成功：`201 {"ok": true, "item": {"id", "name", "slug", "post_count", "url"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "分类名称不能为空"}` / `400 {"error": "已存在同名分类「x」，请勿重复添加"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST,PUT /api/mobile/category/<int:cid>` — 分类改名

- 鉴权：管理员（超管亦可）
- 说明：分类改名（走 `rename_category_core`）；改名无条件重算 slug，无 301、旧链接会失效，`note` 里给出「旧 → 新」说明
- 请求：body `{"name": "..."}`
- 成功：`200 {"ok": true, "note": "地址已由 /category/旧 改为 /category/新 ...", "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "分类不存在"}` / `400 {"error": "分类名称不能为空"}` / `400 {"error": "已存在同名分类「x」，未修改 ..."}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/category/<int:cid>/delete` — 删除分类

- 鉴权：管理员（超管亦可）
- 说明：删除分类；可带 `move_to` 先转移文章，不带则文章变无分类
- 请求：body `{"move_to": <目标分类 id>}`（可选）
- 成功：`200 {"ok": true, "name": "...", "affected": N, "moved": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "分类不存在"}` / `400 {"error": "move_to 必须是另一个存在的分类 id"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `GET /api/mobile/tags` — 标签清单

- 鉴权：管理员（超管亦可）
- 说明：标签列表，带每个标签的使用篇数与 0 使用标签数
- 请求：无
- 成功：`200 {"items": [{"id", "name", "slug", "post_count", "url"}], "total": N, "orphan_count": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/tag` — 新建标签

- 鉴权：管理员（超管亦可）
- 说明：新建标签，走 `create_tag_core`；按「小写 + 去空白」归一键查重
- 请求：body `{"name": "..."}`
- 成功：`201 {"ok": true, "item": {"id", "name", "slug", "post_count", "url"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "标签名称不能为空"}` / `400 {"error": "标签「x」已存在（含大小写/空白变体），未重复添加"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/tag/<int:tid>/delete` — 删除标签

- 鉴权：管理员（超管亦可）
- 说明：删除标签；正被文章引用时拒绝（不级联清理）
- 请求：路径参数 `tid`；无 query / body
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "标签不存在"}` / `400 {"error": "标签「x」正被 N 篇文章使用：请先移除文章里的该标签，或用「一键整理」合并"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/tags/merge` — 一键整理标签

- 鉴权：管理员（超管亦可）
- 说明：合并大小写 / 空白变体标签并清理 0 使用标签，会改动多篇文章的标签关联
- 请求：无
- 成功：`200 {"ok": true, "merged": N, "cleaned": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（5 次/分钟）

### `GET /api/mobile/series` — 系列清单

- 鉴权：管理员（超管亦可）
- 说明：系列列表，按 `sort` 升序、再按创建时间倒序，带文章数
- 请求：无
- 成功：`200 {"items": [{"id", "name", "slug", "description", "cover", "sort", "post_count", "created_at", "url"}], "total": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/series` — 新建系列

- 鉴权：管理员（超管亦可）
- 说明：新建系列，走 `create_series_core`；`Series.name` 无唯一约束，重名不会被拒
- 请求：body `{"name": "..."（必填）, "description", "cover", "sort"}`
- 成功：`201 {"ok": true, "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "系列名称不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST,PUT /api/mobile/series/<int:sid>` — 编辑系列

- 鉴权：管理员（超管亦可）
- 说明：编辑系列（走 `rename_series_core`）；`name` 必填，`description` / `cover` / `sort` **给了才改**（与文章接口「缺省即清空」相反）
- 请求：body `{"name": "..."（必填）, "description", "cover", "sort"}`
- 成功：`200 {"ok": true, "note": "地址已由 /series/旧 改为 /series/新 ...", "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "系列不存在"}` / `400 {"error": "系列名称不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/series/<int:sid>/delete` — 删除系列

- 鉴权：管理员（超管亦可）
- 说明：删除系列；不带 `move_to` 时文章留着、只是脱离系列
- 请求：body `{"move_to": <目标系列 id>}`（可选）
- 成功：`200 {"ok": true, "name": "...", "affected": N, "moved": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "系列不存在"}` / `400 {"error": "move_to 必须是另一个存在的系列 id"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**评论**

### `GET /api/mobile/comments` — 评论列表

- 鉴权：管理员（超管亦可）
- 说明：评论列表，时间倒序；`?unread=1` 只看未读
- 请求：query `?status=pending|approved`、`?unread=1`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [...], "total": N, "page": P, "pages": P}`；每项含 `id` / `author` / `content` / `created_at` / `region` / `device` / `parent_id` / `depth` / `reply_to` / `likes` / `avatar` / `approved` / `is_read` / `post_id` / `post_title` / `ip`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/comment/<int:cid>/<action>` — 单条评论动作

- 鉴权：管理员（超管亦可）
- 说明：`approve`（通过并标已读）/ `reject`（驳回即删除）/ `read`（标已读）
- 请求：路径参数 `cid`、`<action>` ∈ `approve|reject|read`；无 query / body
- 成功：`200 {"ok": true, "id": N, "approved": true}`（approve）/ `200 {"ok": true, "id": N, "is_read": true}`（read）/ `200 {"ok": true, "deleted": true}`（reject）
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "未知操作"}` / `404 {"error": "评论不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（60 次/分钟）

### `POST /api/mobile/comments/batch` — 批量审核评论

- 鉴权：管理员（超管亦可）
- 说明：批量通过或删除评论，与后台批量同口径，上限 500 条
- 请求：body `{"ids": [1, 2], "action": "approve|delete"}`
- 成功：`200 {"ok": true, "changed": N, "action": "approve"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "未知操作"}` / `400 {"error": "请选择要操作的评论"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（30 次/分钟）

### `POST /api/mobile/comments/read-all` — 全部评论标记已读

- 鉴权：管理员（超管亦可）
- 说明：把所有未读评论批量标记为已读，返回实际改动条数
- 请求：无
- 成功：`200 {"ok": true, "updated": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

**留言**

### `GET /api/mobile/guestbook` — 留言墙

- 鉴权：管理员（超管亦可）；**PII 分层：`ip` 原文只出现在超管响应里，管理员拿到 `region` / `device`**
- 说明：留言列表，`q` 搜昵称与内容、`unread=1` 只看未读，时间倒序分页
- 请求：query `?q=`、`?unread=1`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "author", "content", "created_at", "likes", "is_read", "region", "device", "ip"?}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/guestbook/<int:gid>/read` — 留言标记已读

- 鉴权：管理员（超管亦可）
- 说明：把一条留言标记为已读，幂等（弱网重试安全）
- 请求：路径参数 `gid`；无 query / body
- 成功：`200 {"ok": true, "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "留言不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/guestbook/read-all` — 全部留言标记已读

- 鉴权：管理员（超管亦可）
- 说明：批量标记所有未读留言为已读，返回实际改动条数
- 请求：无
- 成功：`200 {"ok": true, "updated": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（10 次/分钟）

### `POST /api/mobile/guestbook/<int:gid>/delete` — 删除留言

- 鉴权：管理员（超管亦可）
- 说明：硬删除留言，**不进回收站、不可恢复**；审计只记内容前 60 字，不记 IP / 设备
- 请求：路径参数 `gid`；无 query / body
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "留言不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（30 次/分钟）

**友链**

### `GET /api/mobile/links` — 友链清单

- 鉴权：管理员（超管亦可）
- 说明：友链清单，按 `sort` 升序，与前台展示顺序一致
- 请求：无
- 成功：`200 {"items": [{"id", "name", "url", "description", "sort", "rss_url"}], "total": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/link` — 新增友链

- 鉴权：管理员（超管亦可）
- 说明：新增友链，走 `save_friend_link_core`；URL 归一（补 `https://`、只放行 http/https、拒伪协议与站内相对路径）且同 URL 查重
- 请求：body `{"name": "..."（必填）, "url": "..."（必填）, "description", "sort", "rss_url"}`
- 成功：`201 {"ok": true, "note": "<RSS 软校验提示，可为空>", "item": {"id", "name", "url", "description", "sort", "rss_url"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "友链名称不能为空"}` / `400 {"error": "网址不合法（只支持 http/https，且不能是站内相对路径）"}` / `400 {"error": "已存在指向同一网址的友链「x」，请勿重复添加"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST,PUT /api/mobile/link/<int:lid>` — 编辑友链

- 鉴权：管理员（超管亦可）
- 说明：编辑友链，走同一个 `save_friend_link_core`；`note` 非空表示 RSS 软校验未通过（保存已成功）
- 请求：body `{"name": "...", "url": "...", "description", "sort", "rss_url"}`
- 成功：`200 {"ok": true, "note": "...", "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "友链不存在"}` / `400 {"error": "友链名称不能为空"}` / `400 {"error": "网址不合法（只支持 http/https，且不能是站内相对路径）"}` / `400 {"error": "已存在指向同一网址的友链「x」，请勿重复添加"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/link/<int:lid>/delete` — 删除友链

- 鉴权：管理员（超管亦可）
- 说明：硬删除友链，`sort` 位置不保留
- 请求：路径参数 `lid`；无 query / body
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "友链不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/links/reorder` — 友链排序

- 鉴权：管理员（超管亦可）
- 说明：按数组顺序重排 `sort`（步长 10），只动列出的 id，上限 500 条
- 请求：body `{"ids": [3, 1, 2]}`
- 成功：`200 {"ok": true, "moved": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "ids 必须是非空数组"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（10 次/分钟）

### `GET /api/mobile/link-applications` — 友链申请列表

- 鉴权：管理员（超管亦可）
- 说明：友链申请列表，默认只看待审，最多返回 200 条
- 请求：query `?status=pending|approved|rejected`（默认 `pending`）
- 成功：`200 {"items": [{"id", "name", "url", "description", "email", "status", "reviewer", "review_note", "created_at", "reviewed_at"}], "status": "pending", "pending_count": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/link-application/<int:aid>/approve` — 通过友链申请

- 鉴权：管理员（超管亦可）
- 说明：写入 FriendLink（同 URL 已存在则跳过），标记申请为 approved
- 请求：路径参数 `aid`；无 query / body
- 成功：`200 {"ok": true, "status": "approved"}`；重复通过时 `200 {"ok": true, "message": "该申请已通过"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "申请不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/link-application/<int:aid>/reject` — 拒绝友链申请

- 鉴权：管理员（超管亦可）
- 说明：拒绝友链申请（仅标记状态，不写入友链表），可附备注
- 请求：body `{"note": "..."}`（可选）；路径参数 `aid`
- 成功：`200 {"ok": true, "status": "rejected"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "申请不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

**公告**

### `GET /api/mobile/announcements` — 公告列表

- 鉴权：管理员（超管亦可）
- 说明：公告列表，按创建时间倒序分页；`active=1/0` 只看启用 / 停用
- 请求：query `?active=1|0`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "content", "level", "levels", "active", "dismissible", "created_at", "preview"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/announcement` — 新建公告

- 鉴权：管理员（超管亦可）
- 说明：新建全站顶部横幅公告，走 `create_announcement_core`；`level` 白名单 `info|warning|success`（其它值归一为 `info`）
- 请求：body `{"content": "..."（必填）, "level": "info", "active": true, "dismissible": true}`
- 成功：`201 {"ok": true, "id": N, "item": {"id", "content", "level", "levels", "active", "dismissible", "created_at", "preview"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "公告内容不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `GET /api/mobile/announcement/<int:aid>` — 公告详情

- 鉴权：管理员（超管亦可）
- 说明：取一条公告的完整信息（`content` 是库里的 Markdown 原文，非渲染 HTML），供编辑器载入
- 请求：路径参数 `aid`；无 query / body
- 成功：`200 {"id", "content", "level", "levels", "active", "dismissible", "created_at", "preview"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "公告不存在"}`

### `POST,PUT /api/mobile/announcement/<int:aid>` — 修改公告

- 鉴权：管理员（超管亦可）
- 说明：整单修改公告，走 `update_announcement_core`；**必须回传完整表单**（没带的布尔字段等同「没勾选」，会被写成 false）
- 请求：body `{"content": "..."（必填）, "level": "info", "active": true, "dismissible": true}`
- 成功：`200 {"ok": true, "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "公告不存在"}` / `400 {"error": "公告内容不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/announcement/<int:aid>/active` — 设置公告启用状态

- 鉴权：管理员（超管亦可）
- 说明：设置公告启用状态，收**显式目标值**（不是翻转），幂等
- 请求：body `{"active": true}`（必填）
- 成功：`200 {"ok": true, "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "公告不存在"}` / `400 {"error": "请带上 active（true/false）"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/announcement/<int:aid>/delete` — 删除公告

- 鉴权：管理员（超管亦可）
- 说明：删除公告，⚠️ 硬删除，公告没有回收站
- 请求：路径参数 `aid`；无 query / body
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "公告不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**微动态**

### `GET /api/mobile/moments` — 微动态列表

- 鉴权：管理员（超管亦可）
- 说明：微动态列表，含评论数
- 请求：query `?q=`（正文关键词）、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "author", "content", "created_at", "likes", "comment_count"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/moment` — 发微动态

- 鉴权：登录
- 说明：发表一条微动态，与前台 `/api/moment` 同一权限位、同一限流强度
- 请求：body `{"content": "..."}`
- 成功：`201 {"ok": true, "id": N}`
- 失败：`401 {"error": "请先登录"}` / `400 {"error": "内容不能为空"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（5 次/分钟）

### `POST /api/mobile/moment/<int:mid>/delete` — 删除微动态

- 鉴权：管理员（超管亦可）
- 说明：删除微动态，级联删除其下评论
- 请求：路径参数 `mid`；无 query / body
- 成功：`200 {"ok": true, "deleted": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "动态不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

**订阅者**

### `GET /api/mobile/subscribers` — 订阅者列表

- 鉴权：管理员（超管亦可）；**PII 分层：邮箱对管理员遮敏（`ab***@domain`），对超管全量；`unsub_token` 任何角色都不返回**
- 说明：订阅者列表，`q` 搜邮箱、`active=1/0` 筛生效 / 退订，时间倒序分页
- 请求：query `?q=`、`?active=1|0`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "email", "email_masked", "active", "created_at"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/subscriber/<int:sid>/active` — 设置订阅状态

- 鉴权：管理员（超管亦可）
- 说明：显式设置订阅生效状态（`active: true/false`），幂等；置 false 即不再收发文邮件但保留记录
- 请求：body `{"active": true}`（必填）
- 成功：`200 {"ok": true, "item": {...}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "订阅者不存在"}` / `400 {"error": "请带上 active（true/false）"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/subscriber/<int:sid>/delete` — 删除订阅者

- 鉴权：管理员（超管亦可）
- 说明：硬删除订阅者；下次同一邮箱再订阅会拿到新的 `unsub_token`。审计只记 id，不写邮箱
- 请求：路径参数 `sid`；无 query / body
- 成功：`200 {"ok": true}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "订阅者不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**通知**

### `GET /api/mobile/notifications` — 站内通知

- 鉴权：登录
- 说明：取当前用户的站内通知（与 `/api/notifications` 同一数据源）；`unread_comments` 仅管理员非零
- 请求：query `?limit=N`（默认 20，钳制 1~50）
- 成功：`200 {"unread": N, "unread_comments": N, "items": [{"id", "content", "link", "is_read", "created_at"}]}`
- 失败：`401 {"error": "请先登录"}`

**媒体库**

### `GET /api/mobile/media` — 媒体库清单

- 鉴权：管理员（超管亦可）
- 说明：媒体库清单（`media_asset` 查表），`q` 搜文件名、`only_free=1` 只看疑似无引用；分页在内存里切，`per_page` 建议 20~30
- 请求：query `?q=`、`?only_free=1`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"name", "url", "size", "ts", "time_str", "refs", "ref_total", "id", "kind", "title", "folder", "storage", "is_public", "width", "height", "duration", "poster", "mime", "size_str"}], "total": N, "page": P, "pages": P}`；`refs` 最多 6 条，`ref_total` 是完整篇数
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/media/delete` — 删除上传文件

- 鉴权：管理员（超管亦可）
- 说明：删除 `uploads` 内的文件（五道路径穿越防护）；被引用时先要 `force` 确认——本模块唯一用 409 表达「请先确认」的接口
- 请求：body `{"name": "文件名", "force": true}`
- 成功：`200 {"ok": true, "name": "...", "ref_total": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `400 {"error": "参数不合法"}` / `409 {"error": "该文件疑似被 N 篇文章引用，删除后文章图片会失效", "refs": [...], "ref_total": N, "need_force": true}` / `404 {"error": "文件不存在"}` / `400 {"error": "<delete_media_core 返回文案>"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

**上传**

### `POST /api/mobile/upload` — 上传图片

- 鉴权：登录
- 说明：上传图片（封面 / 正文插图），multipart 字段名固定 `file`；后缀白名单 + 文件头 16 字节魔数双重校验，大图自动转 WebP
- 请求：multipart 表单 `file`（文件）
- 成功：`201 {"ok": true, "name": "1750...-a.png", "url": "/static/uploads/1750...-a.png"}`
- 失败：`401 {"error": "请先登录"}` / `400 {"error": "没有选择文件"}` / `400 {"error": "只支持 png/jpg/jpeg/gif/webp 图片"}` / `400 {"error": "文件内容与图片格式不符，已拒绝（仅允许真实图片）"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（10 次/分钟）

**统计**

### `GET /api/mobile/stats` — 统计汇总

- 鉴权：管理员（超管亦可）
- 说明：统计汇总（与 `/api/stats/summary` 同口径）；`?detail=1` 额外带趋势序列
- 请求：query `?detail=1`、`?days=N`（1~90，仅 `detail=1` 时生效）
- 成功：`200 {"ok": true, "summary": {...}}`；`detail=1` 时追加 `"trend": [{"date", "pv", "uv"}]`。`summary` 含 `total_visits` / `today_visits` / `today_date` / `regions_today` / `regions_all` / `hot_posts` / `hot_searches` / `avg_read_seconds` / `hourly` / `trend` / `bot_visits` / `human_visits` / `bot_today` / `bot_breakdown` / `referrers` / `devices` / `browsers` / `online` / `compare` / `updated_at`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `500 {"error": "internal_error"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（30 次/分钟）

### `GET /api/mobile/stats/report` — 访问统计多维报表

- 鉴权：管理员（超管亦可）
- 说明：区间汇总 + 日趋势 + 设备 / 浏览器 / 来源分布（复用 `stats.compute_range_stats`）
- 请求：query `?range=today|yesterday|7d|15d|30d|90d|180d|365d|730d`（非法 key 回落 `7d`）
- 成功：`200 {"range": {"key", "label", "start", "end", "days"}, "summary": {"pv", "uv", "human_pv", "human_uv", "bot_pv", "bot_uv", "new_comments"}, "trend": [{"date", "pv", "human_pv"}], "top_paths": [...], "top_regions": [...], "top_referrers": [...], "devices_30d": [...], "browsers_30d": [...]}`；设备 / 浏览器固定 30 天窗口
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

**访客日志与 IP 封禁**

### `GET /api/mobile/visit-logs` — 访客日志

- 鉴权：仅超管（v4.3.1 起收为超管专属，因为输出访客 IP 原文且可被脚本批量抓取）
- 说明：访客日志（后台访客日志页的 JSON 版），区间 / 类型 / IP / 属地 / 路径组合筛选
- 请求：query `?range=today|yesterday|7d|15d|30d|90d|180d|365d|730d`（默认 `7d`）、`?type=human|bot`、`?ip=`、`?region=`、`?path=`、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "time", "ip", "region", "path", "referrer", "is_bot", "bot_name", "bot_category", "blocked"}], "total": N, "page": P, "pages": P, "range": {"key", "label", "start", "end"}, "ranges": [{"key", "label"}]}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

### `GET /api/mobile/blocked` — 生效中的 IP 封禁列表

- 鉴权：仅超管
- 说明：列出正在生效期的 IP 封禁（最多 300 条），供 App 侧解封入口使用
- 请求：无
- 成功：`200 {"items": [{"ip", "reason", "bot_name", "hit_count", "blocked_until", "permanent"}], "total": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

### `POST /api/mobile/ip/block` — 拉黑 IP

- 鉴权：仅超管
- 说明：手动拉黑 IP（默认永久），与后台访客日志页同一个 `bot_guard.block_ip`，写审计
- 请求：body `{"ip": "1.2.3.4"}`
- 成功：`200 {"ok": true, "ip": "1.2.3.4", "message": "..."}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}` / `400 {"error": "IP 格式不合法：..."}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}` / `429 {"error": "操作过于频繁，请稍后再试"}`（20 次/分钟）

### `POST /api/mobile/ip/unblock` — 解封 IP

- 鉴权：仅超管
- 说明：解除一个 IP 的封禁（清封禁期并标记 inactive）
- 请求：body `{"ip": "1.2.3.4"}`
- 成功：`200 {"ok": true, "ip": "1.2.3.4"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}` / `404 {"error": "未找到该 IP 的封禁记录"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

**回收站**

### `GET /api/mobile/trash` — 回收站列表

- 鉴权：管理员（超管亦可）
- 说明：未还原的软删除文章列表，按删除时间倒序
- 请求：query `?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "post_id", "title", "slug", "summary", "deleted_by", "restored", "created_at"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}`

### `POST /api/mobile/trash/<int:rid>/restore` — 从回收站还原

- 鉴权：管理员（超管亦可）
- 说明：还原文章——原文章还在就清 `in_trash` 标记，否则按快照重建为**草稿**
- 请求：路径参数 `rid`；无 query / body
- 成功：`200 {"ok": true, "restored": true, "message": "已还原文章：...", "post_id": N}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "回收站记录不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

### `POST /api/mobile/trash/<int:rid>/purge` — 彻底删除

- 鉴权：管理员（超管亦可）
- 说明：彻底删除文章（删 post 行 + 回收站记录 + 移出索引 + 清收录记录），不可恢复
- 请求：路径参数 `rid`；无 query / body
- 成功：`200 {"ok": true, "message": "已彻底删除：..."}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "需要管理员权限"}` / `404 {"error": "回收站记录不存在"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

**审计**

### `GET /api/mobile/audit-logs` — 后台操作审计日志

- 鉴权：仅超管（`ip` 是原文；`payload` 快照不返回，可能含密钥类键历史值）
- 说明：后台操作审计日志，分页，可按 action / 成败过滤
- 请求：query `?action=`、`?success=1|true|yes`（只看成功）/ `?success=0|false|no`（只看失败）、`?page=N`、`?per_page=N`（默认 50，上限 100）
- 成功：`200 {"items": [{"id", "username", "action", "target", "target_id", "detail", "ip", "success", "created_at"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

**备份**

### `GET /api/mobile/backups` — 备份文件列表

- 鉴权：仅超管
- 说明：备份文件列表 + 远端同步状态（**只读**，不提供触发 / 恢复）
- 请求：无
- 成功：`200 {"backups": [{"file", "size", "size_h", "stamp"}], "total": N, "remote": {...}}`；备份目录不可读时 `200 {"backups": [], "remote": {}, "error": "备份目录不可读"}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

**证书**

### `GET /api/mobile/cert` — 证书看护状态

- 鉴权：仅超管
- 说明：读 `cert_watch` 的持久化状态（**不触发新的探测**，巡检由后台定时任务做）
- 请求：无
- 成功：`200 {"state": {...}, "level": "ok|warn|error|info", "warn_days": 30}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

**SEO**

### `GET /api/mobile/seo/summary` — 收录概览

- 鉴权：仅超管
- 说明：按引擎统计各状态条数 + 最近 20 条提交记录（只读，不提供推送）
- 请求：无
- 成功：`200 {"by_engine": {"<engine>": {"<status>": N}}, "recent": [{"id", "post_id", "engine", "status", "updated_at"}]}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

**设置**

### `GET /api/mobile/settings` — 站点设置只读

- 鉴权：仅超管
- 说明：站点设置**只读**（白名单键 + 是否已配置），凭据类键完全不出现
- 请求：无
- 成功：`200 {"settings": [{"key", "label", "value", "configured"}], "push_channels": {"telegram": false, "wecom": false}}`；白名单键为 `site_name` / `site_title` / `site_description` / `site_url` / `about_content` / `comment_require_approval` / `comment_email_required` / `captcha_enabled` / `og_template` / `accent_color` / `beian_code`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

**用户**

### `GET /api/mobile/users` — 用户列表

- 鉴权：仅超管
- 说明：用户列表，分页，可按角色过滤；**不含 `password_hash` / 邮箱全文**（邮箱对超管也遮敏）
- 请求：query `?role=user|admin|super`、`?q=`（用户名模糊匹配）、`?page=N`、`?per_page=N`（默认 20，上限 100）
- 成功：`200 {"items": [{"id", "username", "email_masked", "role", "role_label", "must_change_password", "created_at"}], "total": N, "page": P, "pages": P}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}`

### `POST /api/mobile/user/<int:uid>/role` — 修改用户角色

- 鉴权：仅超管
- 说明：改用户角色；不能改自己的角色、角色须在白名单内、变更后目标用户 `session_version + 1`（旧会话失效）
- 请求：body `{"role": "user|admin|super"}`；路径参数 `uid`
- 成功：`200 {"ok": true, "user": {"id": N, "role": "admin"}}`
- 失败：`401 {"error": "请先登录"}` / `403 {"error": "仅超级管理员可执行该操作"}` / `404 {"error": "用户不存在"}` / `400 {"error": "不能修改自己的角色（避免把自己锁在后台外）"}` / `400 {"error": "角色只能是 user / admin / super 之一"}` / `403 {"error": "CSRF 校验失败，请刷新页面后重试"}`

该模块源码位置：`myblog/api/mobile.py`、`myblog/api/mobile_ops.py`

---

## 相册 /album

本模块共 2 条接口（公开相册列表与详情）。相册用于「游记 + 照片墙」形态的展示，
**私密相册与不存在统一返回 404**，不区分两者。

### `GET /api/albums` — 公开相册列表

- 鉴权：公开
- 说明：分页列出 `is_public` 的相册，按事件日期倒序（无日期的排最后）；每个相册附封面与前 6 张预览图。仅 2 次查询（相册一次 + 条目 join 媒体一次）
- 请求：`?page=1`（默认 1）、`?size=12`（默认 12，上限 24）
- 成功：`200 {"items": [{"id","slug","title","summary","trip_days","event_date","location","count","cover","preview","created_at"}], "page": 1, "size": 12, "total": 0}`
  - `cover` / `preview` 元素字段：`id, kind, source, url, title, width, height, duration, poster`（不含 `filename` / `uploaded_by` / `storage`）
- 失败：无（列表接口不返回错误码；非法参数被夹到合法区间）

### `GET /api/albums/<slug>` — 公开相册详情

- 鉴权：公开
- 说明：相册元信息 + 可选分组（`sections`）+ 未归入任何分组的扁平条目（`items`）；私密相册与不存在统一 404
- 请求：路径参数 `slug`；无 query 参数
- 成功：`200 {"id","slug","title","summary","trip_days","intro","tips","event_date","location","count","cover","sections": [...], "items": [...], "created_at"}`
  - `sections[]`：`id, title, summary, count, items`
  - `items[]` / `sections[].items[]`：`id, caption, sort, media`
- 失败：`404 {"error": "not found"}`

该模块源码位置：`myblog/api/album.py`

---

## 公开媒体 /media

本模块共 3 条接口（公开媒体列表、单条、归档分类）。
公开面过滤在 SQL 层完成 —— `is_public=False` 的素材**永不出现**，哪怕知道 id。

### `GET /api/media/list` — 公开媒体分页列表

- 鉴权：公开
- 说明：分页列出 `is_public` 的媒体，过滤在 SQL 层完成
- 请求：`?kind=image`（可选，仅 `image` / `video` 生效）、`?folder=xxx`（可选，归档分类）、`?page=1`（默认 1）、`?size=24`（默认 24，上限 60）
- 成功：`200 {"total": 0, "page": 1, "size": 24, "items": [{"id","kind","source","url","title","folder","mime","size","width","height","duration","poster","created_at"}]}`
- 失败：无（`source=embed` 时 `url` 是播放器地址，前台须用 iframe 而非 `<video>`）

### `GET /api/media/folders` — 公开媒体归档分类

- 鉴权：公开
- 说明：列出公开资源用到的归档分类及计数，按计数倒序，供前台分类筛选
- 请求：无
- 成功：`200 [{"folder": "旅行", "count": 12}]`（顶层是数组，非对象）
- 失败：无

### `GET /api/media/<int:aid>` — 单条公开媒体

- 鉴权：公开
- 说明：按 id 取单条公开资源（视频播放页用）；非公开与不存在统一 404
- 请求：路径参数 `aid`（整数）；无 query 参数
- 成功：`200 {"id","kind","source","url","title","folder","mime","size","width","height","duration","poster","created_at"}`
- 失败：`404 {"error": "资源不存在"}`

该模块源码位置：`myblog/api/media.py`

---

## AI 摘要 /ai

本模块共 2 条接口（文章 AI 摘要的读取与生成）。

### `GET /api/ai/summary/<slug>` — 读取文章 AI 摘要与标签

- 鉴权：公开（按文章可见性过滤：匿名只能读到已发布文章；超管可见隐私文章）
- 说明：读文章自己的 `Post.ai_summary` / `Post.ai_tags` 两列，供前台展示；不可见文章与不存在统一返回 404
- 请求：路径参数 `slug`；无 query 参数
- 成功：`200 {"summary": "...", "tags": "..."}`
- 失败：`404 {"error": "文章不存在"}`

### `POST /api/ai/summary/<slug>` — 生成并写入 AI 摘要

- 鉴权：超管（`is_super`）
- 说明：调 OpenAI 兼容 `/chat/completions` 生成 120 字以内摘要 + 标签建议，写回文章自己的列；每超管每小时最多 10 次
- 请求：路径参数 `slug`；无 body 参数
- 成功：`200 {"ok": true, "summary": "...", "tags": "..."}`
- 失败：`403 {"error": "没有权限（仅超级管理员）"}`、`404 {"error": "文章不存在"}`、`400 {"error": "正文为空，无法生成"}`、`429 {"error": "生成过于频繁，请稍后再试"}`、`502 {"error": "<LLM 异常信息>"}` / `502 {"error": "模型返回为空"}`
- 备注：属状态变更请求，受全局 CSRF 保护（非豁免）

该模块源码位置：`myblog/api/ai.py`

---

## 生态统计 /ecosystem

本模块共 2 条接口（站点注册表心跳与统计）。

### `POST /api/ecosystem/heartbeat` — 站点注册表心跳接收

- 鉴权：公开（无会话；内容严格白名单，不代收任何访客数据）
- 说明：部署实例向中心端上报一次心跳；按 `site_key` 去重写入 `EcosystemSite` 表。**不做 URL 可达性验证**（那会是 SSRF）
- 请求：JSON body —— `site_key`（必填，16~64 位小写十六进制）、`url`（可选，http/https，≤300 字符；`listed=false` 时会被清空）、`version`（可选，≤32 字符）、`listed`（可选，默认 true）
- 成功：`200 {"ok": true}`
- 失败：`400 {"error": "bad payload"}` / `400 {"error": "bad site_key"}` / `400 {"error": "bad url"}` / `400 {"error": "url too long"}` / `400 {"error": "write failed"}`、`429 {"error": "rate limited"}`（每 IP 每分钟 30 次）
- 备注：CSRF 豁免端点（上报方是后台定时任务，无会话无 token）

### `GET /api/ecosystem/stats` — 站点注册表统计

- 鉴权：公开
- 说明：返回总站点数 / 近 24 小时活跃数 / 愿意公开列出的站点列表（最多 60 条，按 `last_seen` 倒序）
- 请求：无
- 成功：`200 {"total": 0, "active": 0, "sites": [{"url","version","first_seen","last_seen"}], "active_hours": 24}`
- 失败：无限流时仍返回 `200`，但内容为空壳 `{"total": 0, "active": 0, "sites": []}`（每 IP 每分钟 60 次）

该模块源码位置：`myblog/api/ecosystem.py`、`myblog/ecosystem.py`

---

## 分享卡与爬虫通道 /og

本模块共 4 条接口（分享卡 PNG、爬虫通道、站点二维码、通道自检）。

### `GET /api/og/post/<slug>.png` — 文章分享卡 PNG

- 鉴权：公开
- 说明：服务端动态渲染文章分享卡（标题/摘要/封面/日期/阅读时长/分类），按 slug+updated_at+主题色 hash 落盘缓存；封面只合成站内路径（外链不下载，防 SSRF）
- 请求：路径参数 `slug`；无 query 参数
- 成功：`200 image/png`（`Cache-Control: public, max-age=86400`）
- 失败：无 4xx —— 文章不可见或 Pillow/中文字体缺失时**降级**返回兜底图 `og-default.png`（本地有文件则 `200 image/png`，否则 `302 → /og-default.png`）

### `GET /api/qr` — 站点 URL 二维码

- 鉴权：公开
- 说明：生成 SVG 二维码（矢量小体积，微信扫码分享用）；**仅允许本站 URL**（`site_url` 的 host 或本次请求 host），否则本接口会变成公共二维码生成服务
- 请求：`?url=/post/xxx`（必填；站内相对路径以 `/` 开头，或 `http(s)://` 绝对地址且 host 须在白名单内）
- 成功：`200 image/svg+xml`（`Cache-Control: public, max-age=86400`）
- 失败：`400`（纯文本 `bad request`）、`400`（纯文本 `site_url 未配置：…`）、`403`（纯文本 `forbidden`）、`429`（纯文本 `too many requests`，每 IP 每分钟 30 次）、`404`（空响应体，二维码生成异常）

### `GET /api/og/post/<slug>` — SEO 爬虫通道正式出口

- 鉴权：公开
- 说明：文章级 SSR 壳页，按 slug 服务端渲染标题/描述/canonical/OG/JSON-LD 与正文。**三种互斥出口**：① 文章不可见 → 404 + noindex；② 经通道（`?seo=1`）且抓取方 → 200 壳页 + `index,follow`；③ 其余 → 302 回 `/post/<slug>`。真人（微信/QQ 内置浏览器）经通道时给 200 可读页但 noindex；tool-bot 给 404
- 请求：路径参数 `slug`；query `?seo=1`（通道标记，决定走 ② 还是 ③）、`?lang=zh`（多语言：解析到同组译文，不可见时回退）
- 成功：`200 text/html`（含 `og:title` / `og:image` / `canonical` / `BlogPosting` JSON-LD / hreflang 互链；正文走 `content_html` 缓存列）
- 失败：`404 text/html`（`noindex,nofollow`，不透露 slug 任何信息）、`302`（→ `/post/<slug>`）、`429`（纯文本 `too many requests`，非搜索引擎每分钟 120 次，正规搜索引擎 UA 豁免）

### `GET /api/seo/shell-check` — 爬虫通道自检

- 鉴权：超管（`is_super`）
- 说明：在本地请求上下文直调 `og_post()`（零出网、无自请求放大），用 5 组 UA/请求头（搜索引擎×2、微信抓取、QQ 真人、Chrome 真人）验证闸门三档判定，**三档都不允许 3xx**（3xx = nginx 302 环）
- 请求：`?slug=xxx`（可选；不传则取最新一篇可见文章）
- 成功：`200 {"slug": "...", "site_base": "...", "checks": [{"label","expect","status","location","robots","server_html","canonical","canonical_ok","indexable","ok","would_loop"}], "all_ok": true, "canonical_ok": true, "index_ok": true}`
- 失败：`403`（纯文本 `forbidden`）、`429`（纯文本 `too many requests`，每 IP 每分钟 30 次）、`404 {"error": "站点还没有已发布文章，无法自检"}`、`400 {"error": "site_url 未配置：og:url/canonical 会退化成相对路径，微信卡片将取不到图。请先在后台设置站点 URL。"}`

该模块源码位置：`myblog/api/og.py`

---

## 列表页壳页 /og/page

本模块共 1 条接口。

### `GET /api/og/page/<path:page_path>` — 列表页壳页

- 鉴权：公开
- 说明：SPA 列表路径（`archive` / `about` / `links` / `category/<slug>` / `tag/<slug>` / `series/<slug>`）的服务端 SEO 壳页，输出 title/description/canonical/OG + `CollectionPage` JSON-LD + 文章链接列表（每页最多 50 条）。**只服务认识的路径**，不认识 → 404 + noindex，绝不给通用兜底页
- 请求：路径参数 `page_path`（如 `category/tech`，`path` 转换器可含 `/`）；无 query 参数
- 成功：`200 text/html`（`Cache-Control: no-store` + `Vary: User-Agent, Sec-Fetch-Mode, Accept, Referer`；友链页外链带 `nofollow noopener`）
- 失败：`404 text/html`（`noindex,nofollow`，标题「页面不存在」）、`429`（纯文本 `too many requests`，非搜索引擎每分钟 120 次，搜索引擎 UA 豁免）

该模块源码位置：`myblog/api/seo_page.py`

---

## 系统与版本 /system

本模块共 5 条接口（健康探针、版本检查、触发更新、读取更新状态、部署 Webhook）。

### `GET /api/health` — 存活探针

- 鉴权：公开（无需登录；因此只回 `ok` / `version` / `db` 三项，不回显配置、路径、密钥、异常细节）
- 说明：给外部监控 / 负载均衡做机器判定；只做一次 `SELECT 1`，不查业务表、不出网、**刻意不限流**
- 请求：无
- 成功：`200 {"ok": true, "version": "...", "db": "up"}`
- 失败：`503 {"ok": false, "version": "...", "db": "down"}`（数据库探活失败）

### `GET /api/version/check` — 版本自检

- 鉴权：公开（源码内无任何会话判定）
- 说明：对比 GitHub `latest` tag 与本地 `APP_VERSION`；10 分钟进程内缓存，网络失败回退缓存值；纯只读，不做任何写操作
- 请求：无
- 成功：`200 {"current": "v5.2.4", "latest": "v5.3.0", "update_available": true, "check_ok": true}`
- 失败：无（GitHub 请求失败时 `latest` 可能为空、`update_available` 为 false，仍返回 200）

### `GET /api/version/status` — 在线更新状态

- 鉴权：超管（`is_super`）
- 说明：读取 `data/update_status.json`，供后台轮询更新进度
- 请求：无
- 成功：`200 {"status": "idle", "version": "", "ts": "", "message": ""}`（状态文件不存在时返回该默认值；有则原样返回文件内容）
- 失败：`403 {"error": "没有权限"}`

### `POST /api/version/update` — 触发在线更新

- 鉴权：超管（`is_super`）
- 说明：异步执行 `update.sh`（下载 → 备份 → 覆盖 → 自动重启），立即返回；进程内锁 + 状态文件双保险防重入（状态文件超 10 分钟视为陈旧残留，允许重新触发）
- 请求：无 body 参数
- 成功：`200 {"ok": true, "message": "已开始后台更新，完成后会提示刷新"}`
- 失败：`401 {"error": "请先登录"}`、`403 {"error": "没有权限执行更新（仅超级管理员）"}`、`429 {"error": "更新触发过于频繁，请稍后再试"}`（每 IP 每小时 3 次）、`409 {"error": "更新正在进行中，请稍候"}`、`400 {"error": "未找到更新脚本 <path>，请先上传 update.sh 到服务器"}`、`500 {"error": "更新脚本启动失败: ..."}`
- 备注：受全局 CSRF 保护

### `POST /api/webhook/deploy` — Webhook 触发部署

- 鉴权：密钥鉴权（请求头 `X-Deploy-Token` 与环境变量 `WH_DEPLOY_SECRET` 恒定时间比对；**禁止 URL `?token=`**）+ 时间戳防重放
- 说明：GitHub Webhook → 服务器自动更新；校验通过后异步执行 `DEPLOY_SCRIPT`（如 `git pull` / 解压 / 重启），不等待不阻塞
- 请求：请求头 `X-Deploy-Token`（必填）、`X-Deploy-Time`（必填，Unix 秒；与服务器时间偏差须 ≤ `WH_REPLAY_WINDOW`，默认 300 秒且下限强制 ≥30 秒）
- 成功：`200 {"ok": true, "triggered": true, "message": "部署已触发"}`；未配置 `DEPLOY_SCRIPT` 时 `200 {"ok": true, "triggered": false, "message": "授权通过但未配置 DEPLOY_SCRIPT，请手动部署"}`
- 失败：`403 {"error": "服务器未配置部署密钥 WH_DEPLOY_SECRET"}`、`403 {"error": "密钥错误"}`、`403 {"error": "部署请求时间戳过期或缺失，已拒绝（防重放）"}`、`403 {"error": "缺少有效的 X-Deploy-Time 时间戳，已拒绝（防重放）"}`、`500 {"ok": true, "triggered": false, "error": "部署脚本启动失败: ..."}`
- 备注：CSRF 豁免端点

该模块源码位置：`myblog/api/system.py`

---

## 后台 JSON 接口 /admin

本模块共 **17 条**接口（`/admin/*`，在后台页面里被前端 `fetch` 调用）。

> **CSRF 说明**：所有 POST 类接口均受全局 CSRF 保护（`/admin/*` 不在豁免清单内），
> 需带 `X-CSRF-Token` 请求头或表单 `csrf_token` 字段；GET 类接口不受 CSRF 限制。
>
> **鉴权说明**：后台装饰器 `admin_required` / `super_required`（`myblog/admin/_helpers.py`）
> 认 `session["user_id"]` + 角色 —— 未登录时**重定向到登录页（302）**，
> 非管理员重定向到 `/admin/post/new`，不是返回 JSON。

### `GET /admin/albums/media-picker` — 相册编辑页媒体选择器数据源

- 鉴权：管理员及以上（`@admin_required`）
- 说明：给相册编辑页「添加照片」弹层用，分页返回媒体库素材（与 `/admin/media` 页面同源，只输出 JSON）
- 请求：`?kind=image`（可选，按类型筛）、`?q=xxx`（可选，标题/文件名模糊匹配）、`?page=1`（默认 1）、`?size=24`（默认 24，上限 60）
- 成功：`200 {"items": [{"id","url","thumb","kind","title","created_at"}], "page": 1, "size": 24, "total": 0}`
  - `thumb`：图片取 `url`，视频取 `poster`
- 失败：鉴权不通过时**不是 JSON** —— 未登录 → `302` 跳前台登录页；已登录但非管理员 → `302` 跳 `/admin/post/new`

### `GET /admin/api/slug-preview` — 链接后缀模板实时预览

- 鉴权：管理员及以上（`@admin_required`）
- 说明：按 slug 模板实时预览最终 URL，只读 GET（不受 CSRF 限制）；用占位数据渲染（ID=123、日期=今天、分类=技术），slug 经 `render_slug_template` 清洗
- 请求：`?title=xxx`（文章标题）、`?mode=title`（`slug_mode`，`custom` 时才用 `tpl`）、`?tpl=xxx`（自定义模板串）
- 成功：`200 {"slug": "my-post-20260101"}`
- 失败：鉴权不通过 → `302`（未登录跳登录页 / 非管理员跳 `/admin/post/new`）

### `POST /admin/media/<int:mid>/to-album` — 把素材加入相册

- 鉴权：管理员及以上（`@admin_required`）
- 说明：媒体库侧的横向入口，只建引用（写一条 `album_item`），不复制任何字段；图注留空，前台自动回退显示素材在媒体库的标题。同一张图允许重复加入，不做去重
- 请求：路径参数 `mid`（媒体 id）；JSON body —— `album_id`（必填，目标相册 id）、`section_id`（可选，目标相册内的分组 id）
- 成功：`200 {"ok": true, "album_id": 1, "album_title": "云和梯田"}`
- 失败：`404 {"ok": false, "msg": "素材不存在"}`、`400 {"ok": false, "msg": "请选择相册"}`、`404 {"ok": false, "msg": "相册不存在"}`、`400 {"ok": false, "msg": "该章节不属于这个相册"}`

### `POST /admin/post/<int:post_id>/autosave` — 云端草稿自动保存

- 鉴权：登录（`@login_required`）+ 文章可编辑权（管理员可编辑全部；普通用户仅能编辑自己的）
- 说明：编辑页防抖调用，**仅更新内容类字段**；不记版本历史、不触发发布/订阅/通知、不改发布状态与定时时间
- 请求：路径参数 `post_id`；JSON body —— `title`（必填）、`content`、`summary`、`cover`、`new_category_name` / `category_id`、`new_series_name` / `series_id`、`tags`、`seo_description`、`seo_keywords`、`lang`、`translation_group`
- 成功：`200 {"ok": true, "saved_at": "14:30:05"}`
- 失败：`403 {"ok": false, "error": "无权编辑"}`、`400 {"ok": false, "error": "标题不能为空"}`、`404`（文章不存在；非 JSON 客户端渲染错误页）

### `POST /admin/upload` — 单请求上传

- 鉴权：登录（`@login_required`）
- 说明：单请求上传一个文件；校验链（后缀白名单 → 魔数 → 大小 → 磁盘余量）全在 `media_service.save_single()` 内。更大文件走 `/admin/upload/chunk/*`
- 请求：multipart form —— `file`（必填，文件）、`folder`（可选，归档分类）
- 成功：`200 {"url": "/static/uploads/xxx.png", "id": 1, "kind": "image", "title": "xxx", "size": 12345, "cloud_error": ""}`
- 失败：`400 {"error": "没有选择文件"}` / `400 {"error": "只支持图片（png/jpg/jpeg/gif/webp）或视频（mp4/m4v/mov/webm）"}` / `400 {"error": "<魔数校验信息>"}` / `413 {"error": "文件过大：… 超过 … 上限（…）"}`（图片 50MB、视频 500MB 上限） / `507 {"error": "<磁盘余量不足信息>"}`、`500 {"error": "上传失败：..."}`
- 备注：`kind` 由后缀判定（`png/jpg/jpeg/gif/webp` → image；`mp4/m4v/mov/webm` → video）；图片保留 WebP 优化，云存储失败时保留本地副本并在 `cloud_error` 里回传提示

### 分块上传四件套 `/admin/upload/chunk/*`

超过单请求上限（图片 50MB / 视频 500MB）时走分块。四条接口均为 `@login_required`，
受 CSRF 保护。**临时目录是 `data/upload_tmp`，属主必须是 gunicorn worker 的运行用户**
（否则 www 写不进去 → 500 HTML，前端只能看到 `Unexpected token '<'`）。

### `POST /admin/upload/chunk/init` — 初始化分块会话

- 鉴权：登录
- 请求：JSON body `filename`（必填）、`size`（必填，客户端声明的总字节数）、`folder`（可选）
- 成功：`200 {"upload_id": "<32 位 hex>", "chunk_size": 8388608, "received": 0}`
- 失败：`400`（类型/大小非法）、`413`（声明即超限）、`507`（磁盘不足 / 临时目录不可写）

### `POST /admin/upload/chunk` — 上传一个分块

- 鉴权：登录
- 请求：表单 `chunk`（必填，分块原始字节，**文件字段**）、`upload_id`（必填）、`index`（必填，0~9999）
- 成功：`200 {"received": 1, "expected": 3}`
- 失败：`400`（会话 ID / 序号 / 空块非法）、`410`（会话不存在或已过期）、`413`（单块超过 2×chunk_size）

### `POST /admin/upload/chunk/complete` — 合并完成

- 鉴权：登录
- 请求：JSON 或表单 `upload_id`
- 成功：`200 {"url","id","kind","title","size","cloud_error"}`
- 失败：`409`（分块不完整 / 合并后大小与声明不符）、`410`（会话过期）、`400`（类型 / 魔数不符）、`507`、`500 {"error": "合并失败：..."}`

### `POST /admin/upload/chunk/abort` — 放弃分块会话

- 鉴权：登录
- 请求：JSON 或表单 `upload_id`
- 成功：`200 {"ok": true}`

### `GET /admin/task/<task_id>` — 后台长任务状态轮询

- 鉴权：管理员及以上（`@admin_required`）
- 说明：前端提交「立即备份 / LLM 审计 / AI 摘要」拿到 `task_id` 后轮询，避免长任务占住并发槽；状态存文件（`data/tasks/<id>.json`），跨 worker 可读
- 请求：路径参数 `task_id`（只接受字母数字，非字母数字直接判为不存在）
- 成功：`200 {"id": "...", "name": "备份", "state": "running", "message": "...", "error": ""}`
- 失败：`404 {"state": "unknown", "message": "任务不存在或已过期"}`；鉴权不通过 → `302`

### `GET /admin/seo/status` — 推送状态轮询

- 鉴权：超管（`@super_required`）
- 说明：返回最近 300 条推送记录与状态计数，供页面 JS 定时拉取（不阻塞体验）
- 请求：无
- 成功：`200 {"rows": [{"post_id","engine","status","submitted_at","response"}], "counts": {"pending": 0, "ok": 0, "fail": 0, "quota": 0}, "quota": "剩余配额"}`
- 失败：鉴权不通过 → `403`（JSON 客户端得 `{"error": "没有访问权限"}`，否则渲染 403 错误页）

### `GET /admin/seo/preview` — sitemap / robots 只读预览

- 鉴权：超管（`@super_required`）
- 说明：直接复用 `routes.sitemap()` / `routes.robots()` 的响应体（不重写生成逻辑，避免预览与实际输出漂移），正文截断到 20000 字符
- 请求：`?kind=sitemap`（默认 `sitemap`；传 `robots` 取 robots.txt）
- 成功：`200 {"kind": "sitemap", "body": "<?xml ...", "base": "https://www.example.com"}`
- 失败：`500 {"error": "生成失败：<异常类名>"}`

### `GET /admin/seo/selfcheck` — 通道自检（服务器侧）

- 鉴权：超管（`@super_required`）
- 说明：在 `test_request_context()` 内**直接调 `seo_shell_ua()`**（与线上出口同一函数，结构上不可能漂移），用同一组 5 个 UA/请求头判定三档：搜索擎/微信抓取 = `shell`、真人 = `noindex`、非通道候选 = `404`
- 请求：无
- 成功：`200 {"site_base": "https://www.example.com", "configured": true, "checks": [{"label","expect","got","ok","reason","allow"}], "all_ok": true}`
- 失败：鉴权不通过 → `403`（JSON 客户端得 `{"error": "没有访问权限"}`，否则渲染 403 错误页）

### `POST /admin/mcp-services/toggle/<which>` — 内置 MCP 端点启停

- 鉴权：超管（`@super_required`）
- 说明：启停内置 MCP 端点；停止后该端点对外直接 404（不暴露存在），即时生效无需重启
- 请求：路径参数 `which` —— `diag` 或 `write`；表单字段 `enable`（`"1"` 表示开启，缺省=停止）
- 成功：`302` 重定向回 `/admin/mcp-services`（flash 提示）—— **成功路径不返回 JSON**
- 失败：`404 {"error": "not found"}`（which 非 `diag` / `write`）

### `POST /admin/mcp-services/update/<sid>` — 更新 MCP 外部服务

- 鉴权：超管（`@super_required`）
- 说明：两种用法：**表单带 `name` 字段** → 走完整校验并更新名称/URL/Header/Token/说明（留空 token = 不改）；**表单不带 `name`** → 只做启停切换（读 `enable`）
- 请求：路径参数 `sid`；表单字段 `name`（≤40 字、无空白与引号）、`url`（http/https 完整地址，≤300 字符）、`header`（≤60 字符，无空白与冒号）、`token`（≤200 字符，留空不改）、`desc`（≤120 字）、`enable`（仅不带 `name` 时生效）
- 成功：`302` 重定向回 `/admin/mcp-services`（flash 提示）—— **成功路径不返回 JSON**
- 失败：`404 {"error": "not found"}`（sid 不存在）；表单校验失败 → `302` 回列表页 + flash 错误文案

### `POST /admin/mcp-services/delete/<sid>` — 删除 MCP 外部服务

- 鉴权：超管（`@super_required`）
- 说明：删除一条外部 MCP 服务登记，并连带删除其加密 token（`Setting` 中 `mcp_token_<sid>`）；记审计日志
- 请求：路径参数 `sid`（服务 id，8 位 hex）；无 body 参数
- 成功：`302` 重定向回 `/admin/mcp-services`（flash 提示「已删除」）—— **成功路径不返回 JSON**
- 失败：`404 {"error": "not found"}`（sid 不存在）

### `GET /admin/mcp-services/instruction/<kind>` — 生成 MCP 接入指令

- 鉴权：超管（`@super_required`）
- 说明：生成某服务的 AI 接入指令（脱敏版 token 用占位符；`?full=1` 出含真实 token 的完整版，并记审计日志）
- 请求：路径参数 `kind` —— `diag`（只读诊断 `/mcp`）、`write`（写能力 `/mcp-write`）、或某个外部服务 id；query `?full=1`
- 成功：`200 text/html`（渲染 `admin/mcp_instruction.html`，含 `mcp.json` 片段与接入步骤）—— **成功路径不是 JSON**
- 失败：`404 {"error": "not found"}`（kind 既非内置端点也非已登记的外部服务 id）

该模块源码位置：`myblog/admin/album.py`、`myblog/admin/settings.py`、`myblog/admin/media.py`、
`myblog/admin/post_editor.py`、`myblog/admin/seo.py`、`myblog/admin/misc.py`、`myblog/admin/mcp_services.py`

---

## 如何新增一个 API

1. **新建模块文件**（或加到已有模块）：`myblog/api/xxx.py`
2. **在 `myblog/api/__init__.py` 的导入清单加一行**（`from .xxx import xxx_bp` 之类）
3. **写路由**，用 `api_bp` 装饰器：

   ```python
   from api.common import _current_user
   from flask import jsonify, request

   @api_bp.route("/xxx", methods=["GET"])
   def xxx_list():
       user = _current_user()
       if not user:
           return jsonify({"error": "请先登录"}), 401
       ...
       return jsonify({"items": [...]})
   ```

4. **鉴权按需选**：
   - 公开 → 不判断
   - 登录 → `if not _current_user(): return jsonify({"error": "请先登录"}), 401`
   - 管理员 → `user, err = _role(admin=True); if err: return err`
   - 超管 → `user, err = _role(super_only=True); if err: return err`
5. **写操作自动受 CSRF 保护**，无需额外处理；若要豁免，在 `myblog/app.py:_csrf_protect` 的
   豁免清单里加路径（**谨慎**：豁免意味着该接口可被跨站触发）。
6. **限流**用 `utils.rate_limit` + `client_key`，见 `myblog/api/posts.py` 的写法。
7. **同步本文档**：在对应模块章节加一条，写明方法、路径、鉴权、请求参数、返回字段、错误码。

### 模块间约定的硬规则

- **不要**在模块间互相 `import`（避免循环依赖）；共享逻辑一律放 `common.py`。
- **`stats` 是独立的项目级模块**（`myblog/stats.py`），不通过 `common.py` 转发。
  若新模块需要 `stats.client_ip()` / `stats.cached_region()` / `stats.record_*()` 等，
  必须在本模块顶部显式 `import stats`，否则运行时抛
  `NameError: name 'stats' is not defined`（拆包时曾因此漏修 5 个模块）。

---

## 常见错误码速查

| 状态码 | 含义 | 典型场景 |
|--------|------|----------|
| `200` | 成功 | 正常返回；部分写接口超限时也返 200（附 `"skipped": true`） |
| `201` | 已创建 | 注册、发评论、发留言、订阅、上传 |
| `302` | 重定向 | 后台页面路由鉴权失败跳登录页；`/api/og/post/<slug>` 的默认出口；`/admin/mcp-services/*` 成功后的回跳 |
| `400` | 请求不合法 | 参数缺失、格式错误、魔数校验失败、状态值未带 |
| `401` | 未登录 | 需登录接口；2FA 未过时返回 `{"error": "twofa_required"}` |
| `403` | 无权限 | 角色不足、被 IP 封禁、CSRF 校验失败、跨站请求 |
| `404` | 不存在 | 资源不存在（**私密资源与不存在不区分**，避免泄露存在性） |
| `405` | 方法不允许 | 对只接受 POST 的路由发 GET |
| `409` | 冲突 | 分块不完整；删除被引用的媒体需先 `force` |
| `410` | 已失效 | 分块会话不存在或已过期 |
| `413` | 体积超限 | 单文件超过上限；单块超过 2×chunk_size |
| `429` | 限流 | 触发频率阈值，或 IP 在反爬黑名单里 |
| `500` | 服务器错误 | 聚合异常；上传失败 |
| `503` | 不可用 | 数据库探活失败；GeoJSON 底图取不到 |
| `507` | 存储不足 | 磁盘余量不足；上传临时目录不可写 |

---

> **维护提示**：本文档的路由清单由 `app.url_map` 枚举得出。改了接口后，
> 可用一段脚本重新枚举并与本文档比对，避免遗漏。文档版本号跟随 `APP_VERSION`。

## 插件 /plugins

本模块共 4 条接口（插件槽位声明与运行时管理）。

> 插件系统说明见仓库根目录 `PLUGIN_SYSTEM.md`。插件接口由 `myblog/plugins/__init__.py`
> 的 `plugins_bp` 提供，**不随 `myblog/api/` 一起拆包**，故单列本章。

### `GET /api/plugins/` — 已启用插件清单与渲染数据

- 鉴权：公开
- 说明：返回已启用插件的槽位声明 + footer/nav/sidebar/html/remote 渲染数据，供前台渲染
- 请求：无
- 成功：`200 {"plugins": [{"id","name","version","author","description","slots"}], "footer": [...], "nav": [...], "sidebar": [...], "html": [...], "remote_components": [...]}`
- 失败：无

### `GET /api/plugins/status` — 全部已配置插件状态

- 鉴权：管理员（`_require_admin()`，超管亦可）
- 说明：返回全部已配置插件（含被禁用）的状态，供后台管理页使用
- 请求：无
- 成功：`200 {"plugins": [{"slug","name","version","author","description","slots","loaded","disabled"}]}`
- 失败：`401 {"error": "请先登录"}`、`403 {"error": "需要管理员权限"}`

### `POST /api/plugins/<slug>/set-enabled` — 运行时启停插件

- 鉴权：管理员（`_require_admin()`，超管亦可）
- 说明：运行时启停插件（写/删 disabled 标记文件 + 内存覆盖）
- 请求：路径参数 `slug`（插件标识）；JSON body `{"enabled": true|false}`（缺省为 true）
- 成功：`200`（返回 `set_plugin_enabled()` 的结果对象）
- 失败：`401 {"error": "请先登录"}`、`403 {"error": "需要管理员权限"}`

### `POST /api/plugins/reload` — 整体重载插件

- 鉴权：管理员（`_require_admin()`，超管亦可）
- 说明：整体重载插件（卸载全部蓝图后重新扫描加载）
- 请求：无
- 成功：`200`（返回 `reload_plugins()` 的结果对象）
- 失败：`401 {"error": "请先登录"}`、`403 {"error": "需要管理员权限"}`

该模块源码位置：`myblog/plugins/__init__.py`

---
