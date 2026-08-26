# 独立安全复审报告 · llhhy-blog v3.8.1

> 复审类型：独立第三方安全复审（不依赖 `SECURITY_AUDIT.md` 既有结论，逐文件读码核实）
> 复审对象：`myblog/`（Flask 后端）+ `vue-frontend/`（Vue3 前端）+ 部署脚本
> 复审范围：认证/会话、CSRF、XSS、SQL 注入、越权、SSRF、限流、密钥管理、命令/路径安全
> 结论总览：**未发现严重（🔴）或可独立利用的高危（🟠）远程漏洞**；发现若干**纵深防御缺口 / 配置依赖型 / 一致性**问题（中 4 / 低 7）。代码整体安全水位明显高于一般个人项目，既有审计文档中抽查的关键修复**确实落地在代码里**。

---

## 〇、先说结论：既有审计的可信度

我逐文件核对了审计文档（R1~R39）声称的若干关键修复，**代码侧确认已真实落地**，并非纸面修复：

| 文档声称 | 代码核实结果 |
|---|---|
| R30-B1 后台 4 处 `confirm()` 存储型 XSS 改 `\|tojson` | ✅ `users.html`/`subscribers.html`/`backup.html`/`audit_logs.html` 均已用 `\|tojson`，无 `tojson` 字面残留 |
| CSRF 双重防护（Origin 同源 + 会话绑定 HMAC Token） | ✅ `app.py::_csrf_protect` + `utils.check_csrf_token` 真实存在；且**实际比文档更严格**——文档提到的「纯 API 客户端无 token 自动放行」分支**在代码中并未实现**，而是统一 403，更安全 |
| 上传魔数校验（R13-6） | ✅ `admin.py::_detect_image_magic` + `secure_filename` + WebP 转码 |
| 越权收窄（R30-B2/B3） | ✅ `system.py` 的 `/api/version/update` 与 `/api/version/status` 均已 `is_super` |
| 全 `v-html` 出口经 `clean_html` | ✅ 仅 4 处 `v-html`（公告/关于/RSS摘要/搜索高亮），均经 bleach 清洗或 escape+`<mark>` |
| IP 属地 XFF 收口 | ✅ `stats.client_ip` 与 `utils.client_key` 均要求 XFF[0] 为 `is_global` 才采纳 |
| Webhook HMAC 恒定时间比较 | ✅ `system.py` 用 `hmac.compare_digest` |

因此下方的问题属于「在已加固地基上的残留缺口」，而非「文档没修的洞」。

---

## 一、中危（建议尽快修）

### M1 · 验证码在 SSR 遗留路由上未生效（一致性缺口）
- **位置**：`routes.py:36` `register()` POST 分支、`routes.py:179` `add_comment()` POST 分支。
- **问题**：图形验证码只在 API 路由强制（`api/auth.py:22`、`api/posts.py:220` 的 `captcha_required()`）。但 SSR 表单路由 `/register` 和 `/post/<slug>/comment` **完全没有调用 `captcha_required()`**，仅做 `rate_limit` + 弱密码校验。
- **影响**：若攻击者直接 POST 这两个 Flask 路由（绕过 Vue SPA 走 `/api/auth/register`、`/api/post/<slug>/comment`），即可**完全无视验证码**进行批量注册 / 刷评论。验证码作为「防机器人」控制被实质性绕过。
- **说明（重要）**：若生产 Nginx 把 `/register`、`/post/...` 交给 Vue SPA（catch-all `try_files $uri /index.html`），这两个 Flask 路由在线上可能不可达，此时仅为「遗留死路由」。但作为纵深防御，依赖「恰好路由不到」是脆弱的；一旦 Nginx 配置变动即暴露。
- **建议**：二选一——① 在 `routes.py` 的 `register`/`add_comment` 也接入 `captcha_required()`（与 API 一致）；② 或确认并显式阻断这两个遗留 POST 路由（返回 404/405）。

### M2 · 基于 XFF 的限流可被伪造公网 IP 绕过（部署依赖型）
- **位置**：`utils.client_key`（utils.py:128）、`stats.client_ip`（stats.py:27）。
- **问题**：限流 key 优先采用 `X-Forwarded-For` 首段，仅当该段 `is_global` 时才采纳，否则回退 `remote_addr`。**攻击者可在 XFF 首段填入任意「公网 IP」（如 `9.9.9.9`），代码会接受并据此计数**。
- **影响**：若反代 Nginx 使用 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`（常见默认），客户端自填的 XFF 会被保留为首段，攻击者可不断轮换公网 IP 使每 IP 计数不超阈，从而**绕过注册/登录/评论/点赞的限流**（注册 10/60s、登录 10/60s、评论 10/60s、点赞 20/60s 等）。
- **依赖条件**：Nginx 必须用 `proxy_set_header X-Forwarded-For $remote_addr;`（替换而非追加）才能根治。审计文档第 403 行已要求，但代码侧对此**无任何兜底**。
- **建议**：① 部署文档/脚本里把 `X-Forwarded-For $remote_addr;` 作为**强制前置条件**并加注释告警；② 代码侧可加「仅信任由本机反代写入的固定请求头（如 `X-Real-IP`）」的开关，避免把客户端可控的 XFF 直接当真。

### M3 · Webhook 部署密钥可通过 URL 传递且为静态共享密钥
- **位置**：`api/system.py:155` `webhook_deploy`。
- **问题**：
  1. 密钥既接受 `X-Deploy-Token` 头，也接受 `?token=...` URL 参数。**URL 中的密钥会出现在 Nginx/反代/GitHub webhook 投递/访问日志里**，造成凭据泄露。
  2. 校验为「客户端 token == 服务端 secret」的**明文直比**，而非对请求体做 HMAC-SHA256（GitHub 官方范式）。即 secret 本身作为每请求 bearer 明文传输。
  3. 防重放依赖可选 `WH_REPLAY_WINDOW`（默认 300s）；若运维误设为 `0` 则**完全无重放保护**，截获一次即可无限重放触发部署。
- **建议**：① 仅接受 `X-Deploy-Token` 头，删除 `?token=` 支持；② 改为 HMAC-SHA256(request_body, secret) 校验；③ 强制 `WH_REPLAY_WINDOW>0` 且给出下限（如 ≥30s）。

### M4 · `/api/weather` 将未校验的 lat/lon 直接拼入出站 URL
- **位置**：`routes.py:305` `api_weather`（`_wttr`、`api.open-meteo.com`、`api.bigdatacloud.net` 拼接处）。
- **问题**：`lat`/`lon` 来自 `request.args`，**未经类型/范围校验，也未 `quote` 转义**，直接 f-string 拼进外网 URL：
  ```python
  f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
  ```
  `city` 参数有 `quote`，但 `lat`/`lon` 没有。
- **影响（低-中）**：① 至少可被用来向固定外部主机发出攻击者构造的查询串（反射/放大，且本接口为**公开 GET、无限流**）；② 视 Python/`urllib` 版本，未转义的用户输入进入 URL 可能触发 HTTP 请求行/头注入（CRLF）——取决于运行环境对 `\r\n` 的防护，**存在版本相关不确定性**，应主动消除。
- **建议**：`lat`/`lon` 用正则/浮点强校验（`^-?\d+(\.\d+)?$` 且范围合理），否则拒绝；或统一 `urllib.parse.quote`；并给该接口加基础限流。

---

## 二、低危（加固项）

### L1 · 统计/版本接口未鉴权，泄露内部运营数据
- **位置**：`api/stats.py:54` `/stats/summary`、`api/stats.py:60` `/stats/trend`、`api/system.py:19` `/api/version/check`。
- **问题**：均为公开 GET，返回累计访问、热门搜索词、访客 IP 属地排行、爬虫分布、趋势等。对个人博客属「半公开分析数据」，但搜索词与地域排行具备一定敏感性，且 `/version/check` 暴露当前版本（便于攻击者定向）。
- **建议**：对非登录用户限制为聚合粒度更粗的数据，或至少对 `/stats/summary`、`/stats/trend` 加限流；`/version/check` 保持现状（无害）或仅登录可见。

### L2 · `custom_css` 以 `|safe` 渲染（管理员 CSS 注入）
- **位置**：`templates/base.html:14`、`templates/admin/base.html:11`。
- **问题**：`custom_css` 由 `Setting` 表提供，仅超管可写，但用 `|safe` 直接进 `<style>`。超管可注入任意 CSS（叠加已存在的 `style-src 'unsafe-inline'`）。属「管理员自 XSS」，风险低；但一旦超管账号被盗，攻击者可借 CSS（属性选择器读取 input 值等技巧）做进一步利用。
- **建议**：对 `custom_css` 做 CSS 语法/属性白名单清洗（如剥离 `@import`、`url()` 外链、`expression` 等），或至少禁止 `url()` 与 `@`。

### L3 · 密码复杂度「大小写混合」默认与文档不符
- **位置**：`config.py:119` `STRONG_PASSWORD_MIXED_CASE = os.environ.get(..., "false")`。
- **问题**：审计 R13 声称该开关默认 `true`，但代码默认 `false`。即默认密码策略仅要求「字母+数字」，**不要求同时含大小写**。属策略偏弱、文档与实现不一致。
- **建议**：若确要「大小写混合」，把默认值改为 `"true"`；并同步修订审计文档。

### L4 · 备份包 manifest 无密码学签名（仅完整性、非防篡改）
- **位置**：`backup.py:288` `verify()`、`create_backup()`。
- **问题**：`manifest.json` 内嵌于 zip 内，校验仅重算每文件 SHA256 与 manifest 内记录比对。**manifest 本身无签名/MAC**：能改写文件者也能同步改写 manifest，故该机制只防「意外损坏」，不防「恶意篡改」。审计文档 R18 称「防坏档/被篡改恢复」略夸大。
- **影响**：威胁模型下，能触达备份文件的攻击者通常已具备超管能力，故实际风险低。
- **建议**：用 `SECRET_KEY` 对 manifest 做 HMAC 并以独立密钥存于服务器（非备份包内），恢复前校验 HMAC，实现真正的防篡改。

### L5 · `feed_agg` 的 DNS 重绑定为「检查时」而非「使用时」（TOCTOU）
- **位置**：`feed_agg.py:33` `_safe_url`（解析校验）vs `:91` `feedparser.parse(link.rss_url)`（实际抓取）。
- **问题**：`_safe_url` 解析域名确认为公网 IP 后放行，但抓取时 `feedparser`/urllib 会**再次解析**，存在「检查期间公网、抓取瞬间回绑内网」的窗口。审计 R13 已自述此残留风险（低）。
- **建议**：解析后直接用解析到的 IP + `Host` 头发起请求（或复用校验得到的 IP），或用 `requests` + 自定义 `socket` 绑定，消除重绑窗口。

### L6 · `backup.py::_run` 保留 `shell=True` 分支（潜在能力）
- **位置**：`backup.py:165`。
- **问题**：`_run` 在 `cmd` 为 `str` 时走 `shell=True`。当前所有调用方（`sync_scp`/`sync_webdav`）均传 list，故实际走 `shell=False`，无注入。但保留 `shell=True` 分支是潜在陷阱：未来若有人传入字符串命令即可能命令注入。
- **建议**：删除 `shell=True` 分支，统一强制 list 参数（或加断言）。

### L7 · `restore()` 在应用运行时直接覆盖活动数据库（运维风险）
- **位置**：`backup.py:332` `restore()`。
- **问题**：恢复会直接覆盖 `data/blog.db`，而 SQLite 在 gunicorn 多 worker 运行时被占用，可能造成库损坏。审计文档已提示需「停止→启动」，但代码未做任何保护（如检测占用/强制下线）。
- **建议**：恢复前检测是否有活跃连接/进程，或要求通过「停止站点」钩子后再执行；在后台恢复按钮文案与文档中强调。

---

## 三、明确核实「无问题」的项（避免重复劳动）

- **SQL 注入**：全库 ORM 参数化；原生 SQL 仅出现在 `_migrate_*` 用 f-string 拼**硬编码列名**（来自写死 dict），无用户输入；FTS 查询经参数绑定 + `escape_fts_query`。
- **CSRF**：全局 `_csrf_protect` 覆盖所有 POST/PUT/DELETE/PATCH，豁免清单（webhook/captcha/stats 信标）均合理；SPA 走 `X-CSRF-Token`、后台表单走 `{{ csrf_input() }}`（Markup 包装，已修复乱码）。
- **命令执行**：`subprocess.Popen(["bash", script], ...)` 均为 list 参数、脚本路径来自环境变量/常量，无 shell 拼接。
- **路径穿越**：备份 `_safe_rel` 拒绝 `..`/绝对路径且强制白名单前缀 `data/`、`static/uploads/`；恢复前 `verify()` 二次校验。
- **密钥管理**：`SECRET_KEY`/`ADMIN_PASSWORD` 缺失即拒绝启动；备份密钥 Fernet 加密落库、环境变量优先、页面掩码回显；仓库无 `.env`、无硬编码密钥。
- **会话安全**：`session_version` 改密/踢下线失效旧会话；`SESSION_IDLE_MINUTES` 闲置超时；`SameSite=Lax` + HttpOnly + 安全头。
- **XSS（存储型）**：评论/留言/动态/公告内容，前端均 `{{ }}` 文本插值或经 `clean_html`；搜索高亮先 `escape` 再包 `<mark>`。

---

## 四、给部署方的硬性前置清单（来自代码事实）

1. **Nginx 必须** `proxy_set_header X-Forwarded-For $remote_addr;`（替换，非追加），否则 M2 限流可被绕过、且属地/埋点归属被伪造。
2. **SPA 必须与 API 同源部署**（同站/同父域），因 `SESSION_COOKIE_SAMESITE=Lax`：跨站 fetch 不带会话 Cookie，会导致 CSRF token 无法携带、所有需登录 API 失效。
3. `WH_DEPLOY_SECRET` 只走请求头、不落 URL（见 M3）；`WH_REPLAY_WINDOW` 勿设 0。
4. 升级后务必 `pip install Pillow cryptography redis`（否则验证码/备份加密/Redis 全局限流分别降级）。
5. 一键更新前须先用对应 Release 的 `deploy_scripts_*.zip` 覆盖 `update.sh`/`deploy.sh`（历史多轮脚本 bug，见审计 R22~R27）。

---

## 五、复审方法说明

- 全程**读源码**核实，未轻信审计文档结论；对关键修复（tojson/CSRF/魔数/is_super/v-html 清洗/XFF 收口/HMAC）均在代码与模板中确认落地。
- 未执行动态渗透（无运行环境）；结论基于静态读码 + 威胁建模。
- 总体评价：项目安全工程成熟度较高，本轮独立复审**未推翻既有审计的核心结论**，补充发现的均为纵深防御/一致性/配置依赖层面的改进点，无需要立即回滚的阻断级问题。
