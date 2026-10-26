# 安全审计报告（SECURITY_AUDIT.md）

> **📦 历史归档**：第一轮 ~ 第一百轮（R1~R100）已归档至 `docs/archive/SECURITY_AUDIT_r01-r80.md`（R1~R80）、`docs/archive/SECURITY_AUDIT_r81-r90.md`（R81~R90）与 `docs/archive/SECURITY_AUDIT_r91-r100.md`（R91~R100）；R101~R110 → `docs/archive/SECURITY_AUDIT_r101-r110.md`（v4.12.1 因体积守卫触发，主文件涨到 166 KB / 上限 160 KB）；**本文件从 R111 起**。

---

## R132 · v4.13.0 发版安全审查（FTS5 探测改只读 · 诊断口径分离 · CWE-693 / CWE-200）

**范围**：`myblog/fts.py`（`_probe` / `available` 重写 + 新增 `probe_code` `probe_reason`）、
`myblog/diagnostics.py`（`check_search_index` 口径分离）、`myblog/mcp_diag.py`（`health_score`
回传 notes / items）。无新路由、无权限变更、无表结构变更、无迁移。

本轮的性质比较特殊：**修的是一个「本该只读的路径在写库」的缺陷**，所以审计重点有两层 ——
新探测本身是否引入新攻击面，以及它带出的错误文案是否会变成信息泄露通道。

### 132.1 探测语句的注入面

`_probe()` 现在只发两条**常量** SQL：

| 语句 | 参数化 | 用户可控输入 |
|---|---|---|
| `SELECT sqlite_compileoption_used('ENABLE_FTS5')` | 无参数（字面量） | 无 |
| `SELECT 1 FROM sqlite_master WHERE type='table' AND name='post_fts'` | 无参数（字面量） | 无 |

两条都不拼接任何变量，不存在注入面。**旧的 DDL 版本反而更大**：`CREATE VIRTUAL TABLE
IF NOT EXISTS` 失败后走 `rollback()`，而 pysqlite 的隐式事务对 DDL 的处理与 DML 不同，
失败路径上是否 100% 回滚依赖驱动行为 —— 本次顺带把这个不确定性去掉了。

### 132.2 新增错误文案的暴露面（CWE-200 复核）

`probe_reason()` 会把探测失败的异常文案带出（`OperationalError: …`）。逐层确认可见性：

| 消费方 | 鉴权 | 判定 |
|---|---|---|
| `admin/feed_diag` 页（`diagnostics.run_all`） | `@super_required`（`admin/misc.py:221`） | 超管可见，可接受 |
| MCP `/mcp` 的 `health_score` / `run_check` / `health_overview` | Bearer Token + 仅同源 Origin | 已鉴权，可接受 |

**没有公开路径**会输出这段文本（已 `grep` 确认 `run_all()` 只有上述两个消费方）。
仍做了防御性收口：`_probe()` 把整段文案**截断到 200 字符** —— SQLite 的异常偶尔会带上
数据库绝对路径，对超管不必隐藏但也没必要整段外露。与 `admin/misc.py` 既有的
`str(e)[:200]` 同口径。

### 132.3 「诊断工具不得改数据」这条约束的落地

`diagnostics.py` 头部写死了「只读：不写库、不发网络请求」，但 `check_search_index()`
经 `fts.available()` 走到旧 `_probe()` 的 DDL —— **体检在写生产库**。探测改只读后，
这条约束才真正成立。守卫方式是一条结构测试：在 `before_cursor_execute` 上挂事件收集语句，
断言 `_probe()` 期间**不含任何 DDL/DML**（`tests/test_fts_probe_readonly.py`）。
选「收集实际执行的 SQL」而不是「grep 源码」，是因为前者连将来换实现也拦得住。

### 132.4 并发路径的可用性风险（CWE-693 保护机制未生效）

旧实现把探测结果**按进程永久缓存**，失败一次即让该 worker 整个生命周期降级成 LIKE
全表扫描，且**无日志**。这不只是性能问题：`/api/search` 的 FTS 分支与 LIKE 分支语义不同
（词元匹配 vs 子串匹配），同一查询落在不同 worker 上会得到不同结果集，行为不可预期。
改为「成功才永久缓存、失败只在 60 秒窗口内缓存」后，单次瞬时故障不再扩散成进程级状态。
失败文案同时区分「环境未编译」与「探测失败」，避免把运维指向换 SQLite 构建这种无关动作。

### 132.5 遗留

- 无新增。仍沿用 R130.5 的已知项（`admin.css` 重复定义未合并、`run_check` 枚举硬编码）。

---

## R131 · v4.12.0 发版安全审查（前台 /docs 重做 · CWE-200 信息暴露复核）

**范围**：仅 `vue-frontend/src/views/DocsView.vue`（+ 后端 `APP_VERSION`）。无接口、无权限、
无表结构变更。审查重点是「公开页面上新增的取值行为是否会带出敏感信息」。

### 131.1 新增的唯一外部调用：`GET /api/health`

`/docs` 现在用它取版本号（此前写死 v3.8.7）。该端点本身的设计约束已在前一轮固化，
本轮复核三项：

| 检查项 | 结果 |
|---|---|
| 是否公开（无需登录） | 是，按设计；监控探活必须匿名可调 |
| 返回字段 | 仅 `ok` / `version` / `db`，**不含配置、路径、密钥、异常细节** |
| 是否可放大 | 只做一次 `SELECT 1`，不查业务表、**不出网**、不加限流（成本已最低） |
| 失败行为 | DB 不可用返回 `503`，前端 catch 后保持「—」，**不报错、不降级成写死值** |

结论：版本号是**本来就公开**的信息（后台左下角、GitHub tag、`version_info` 均可获取），
由写死改为运行时取值不新增任何暴露面；反过来它消除了「页面上写着一个过期版本号」
这类误导性信息（对评审/受众而言属于准确性问题，非安全问题）。

### 131.2 前端不得新增凭据请求

`/docs` 是**完全公开页面**，任何带凭据的请求都会在未登录访客端触发 401 并在控制台留下噪音。
本轮只加了 `fetch("/api/health")`，**无 Cookie 依赖、无 CSRF token、无 Authorization**。
`credentials: "same-origin"` 沿用全站默认，未放宽。

### 131.3 动态 DOM 与 XSS 复核

复制按钮仍由 `document.createElement` 创建（本轮只修了它的 scoped 样式匹配，
即 `pre :deep(.copy-btn)`）。复核点：该按钮只读写固定的中文字面量「复制 / 已复制」，
**不拼接任何接口返回内容**；`btn.textContent` 赋值而非 `innerHTML`。
版本号走 Vue 模板插值 `{{ appVersion }}`（自动转义），不经 `v-html`。
新增的搜索过滤只对本地静态节点做 `textContent` 匹配，**不注入任何 HTML**。

### 131.4 文档内容本身的合规

新增的「其他接口」章节披露了 `/api/mobile/*`、`/api/og/*` 的存在与分组。
判定：**不构成敏感信息暴露** ——
- 这些都是**已上线的路由**，任何人都能通过 `OPTIONS`/直接请求枚举到；
- 章节只给前缀与用途，**不含鉴权绕过细节、不含任何 token/密钥、不含内部路径**；
- `/api/mobile/*` 全部需要登录会话，文档明写「权限逐条对齐后台对应页面」，
  这类「已知入口 + 明确鉴权」的记录属正常对外文档范畴。

### 131.5 遗留

无新增。仍沿用的已知项见 R130.5（`admin.css` 重复定义未合并、`run_check` 枚举硬编码）。

---

## R130 · v4.11.0 发版安全审查（后台组件层 · 体检 12→19 维 · MCP 新增 3 工具 · CWE-200 / CWE-284）

**范围**：① `admin.css` 后台统一组件层（+486 行，纯样式）；② 全站体检新增 7 个 checker；
③ MCP 诊断新增 3 个工具（`health_score` / `issues` / `run_check`）；④ 访问统计页样式作用域收口。

### 130.1 权限面（CWE-284）：无变化，逐项确认

| 面 | 变化 |
| --- | --- |
| 后台页面 | 无新增页面、无新增路由；`/admin/feed_diag` 仍是 `@super_required` |
| MCP 端点 | 仍走 `MCP_AUTH_TOKEN` fail-closed + Origin 校验 + 60/分钟限流；新增的 3 个工具**全部只读**，不提供任何写能力的替代路径 |
| 前端 | 无任何改动（纯后端 + 后台模板），`vue-frontend/` 未动 |

`run_check` 能返回**正常项的实际值**（设计如此，排障要看 db 体积 / WAL 模式 / 证书到期日），
因此必须确认它不夹带凭据。

### 130.2 信息暴露（CWE-200）：实测扫描 19 个维度

对 `diagnostics.CHECKS_BY_KEY` 全部 19 个 checker 逐一执行 `_normalize()` 并序列化为 JSON，
用 `(password|passwd|secret|token|api[_-]?key|access[_-]?key|webhook|bearer|PRIVATE KEY|bkenc$)`
扫描返回文本：

- **18 个维度零命中**；
- `mcp` 维度命中 `bearer` / `token`，**逐条核对为标签文本**
  （`{"label": "Bearer Token", "value": "未配置（端点整体关闭）"}`），不含任何实际值。

结论：**19 个维度的返回内容均不含凭据**。已有的 `recent_errors` 仍在输出前打码密钥（v3.x 起）。

### 130.3 样式越权（本轮修的真 bug）

`stats.html` 的页面级 `<style>` 里 13 个选择器**无作用域前缀**，其中 `.tag` 与 `.card-head`
是全局类：前者被 `announcements` / `bot_guard` / `email_settings` / `feed_diag` / `games`
五处复用，后者在 `admin.css` 有全局定义 —— 这一页的定义会覆盖全站，属于**样式层面的越权**。
已全部补 `.stats-page` 前缀。同时修 `var(--muted)`（变量不存在 → 深色模式回退硬编码 `#888`）。

> 这类问题的危害不是安全，而是「改 A 页坏 B 页」，且**没有报错**——与 R124 记录的
> 「结论与安全状态脱钩」同属静默失效，故一并记在此处。

### 130.4 测试与验证

- 全量 **1181 passed**（v4.10.1 时 1154，+27）；新增 `tests/test_diagnostics_v4110.py`（184 行）
- Jinja 全部 63 个模板编译通过（改模板后必做）
- Python 语法：改动过的 5 个文件 `py_compile` 全绿
- CSS：`admin.css` 大括号配平 688/688、`stats.html` 65/65

### 130.5 已知遗留（如实记录）

1. `admin.css` 里 `.admin-table` / `.hero-card` / `.card-body` 等存在**多处定义**（21/18/17 处），
   部分在媒体查询外叠加。本轮只统一了「类名欠账 + 控件外观」，**未做重复定义合并** ——
   那需要逐条判定覆盖关系，风险高于收益，留作后续专项。
2. `run_check` 的 `inputSchema` 里 19 个维度 key 是**硬编码字符串**。新增 checker 时
   这段描述会过时（`CHECKS_BY_KEY` 驱动了执行，但没驱动描述）。属于文档漂移，非功能缺陷。

---

## R129 · v4.10.0 发版安全审查（推送配置后台化 · SSRF 出口 · 列表页 SEO 通道 · 移动端第二批 · CWE-918 / CWE-200 / CWE-284）

**范围**：本轮四项 —— ① 推送配置（`TELEGRAM_*` / `WECOM_WEBHOOK_URL`）后台化，含 `notify._post_json`
出站加固；② SPA 列表路径（`/archive`、`/category/*`、`/tag/*`、`/series/*`、`/about`、`/links`）
服务端 SEO 壳页；③ 移动端第二批 7 组「数据与设置」端点；④ `update.sh` 版本号解析加固 + lint 债务清理。

### 129.1 SSRF（CWE-918）—— 本轮最大风险点，已收口

**风险成因（这是「后台化」本身引入的，不是历史漏洞）**：`notify._post_json` 此前直接用
`urllib.request.urlopen`，**无 scheme / 私网 / 重定向限制**。在原设计下不构成漏洞 —— 地址只来自
环境变量，能改 `.env` 的人本来就能改代码（R39 的原判据此作出）。**一旦地址可由后台表单填写**，
「能登后台」就等于「能指定一个出站请求的目标」：`http://127.0.0.1:8686/admin/*`、
`169.254.169.254`（云元数据）、内网网段全部可达。这正是 R128 §128.3 提前开列的前置条件。

**处置**：`_post_json` 改为走统一出站层 `outbound.open_url()`，能力全部复用、不新写判断：

| 防护 | 实现 | 挡住的攻击 |
| --- | --- | --- |
| scheme 白名单 | `_post_json` 内先判 `https://`（比出站层的 http/https 更严一档） | 明文泄露文章标题/链接；`file://` / `gopher://` 等协议探测 |
| 私网/回环/链路本地/保留/组播过滤 | `outbound._check()` → `is_private_ip()` | 打内网服务、云元数据 |
| **IP pinning** | 解析 → 校验 → 把 IP 固定在连接上（`_PinnedHTTPSConnection`） | **DNS rebinding**（检查与使用两次解析之间的 TOCTOU） |
| 禁跟随 3xx | `NoRedirect`（恒装） | 「公网 302 → 内网」绕过 |
| URL 内嵌凭据 | `_check()` 拒绝 `user:pass@` | 借 URL 传递凭据、混淆目标 |

**为什么"重试"也要改**：`OutboundRejected` 是**配置错误**，不是瞬时抖动。原 `_send_with_retry`
会把它重试 3 次（多耗 7 秒、日志里堆 3 条同样堆栈，把真正的错误埋掉）。现改为遇到
`OutboundRejected` **立即停手**并按 error 级别记一条可照做的提示；网络类异常仍按 1/2/4s 退避重试。

**留存风险（如实记录）**：出站层允许 `https` 到**任意公网地址** —— 后台账号仍可把 webhook 指向
自己的公网服务（拿到推送内容）。这是「允许自定义 webhook」的固有代价，与「能改推送配置」
的权限同级；故该页面权限定为**仅超管**，且保存前有 `precheck_url()` 轻量预检。

### 129.2 凭据落库与回显（CWE-312 / CWE-532）

- `TELEGRAM_BOT_TOKEN` / `WECOM_WEBHOOK_URL`（URL 内含 `?key=`）**Fernet 加密落库**
  （`SECRET_KEY` 派生，复用 `backup_settings.encrypt_secret`），页面与接口只回显**掩码**。
- **掩码被原样提交回来时不得当成新值**：`push_settings.save()` 显式识别掩码并跳过。
  若不识别，`ab****cd` 会被存成真 token → 推送全部失败，而页面看起来「明明配着值」。
- **留空 = 保持不变**（与 `backup_settings` 同一语义）；要清空必须显式勾「清除」。
  否则「只改 chat id、不动 token」会把 token 一起清掉，且没有任何提示。
- 读取优先级：**密钥环境变量优先** → 库值兜底（老部署零迁移，不会因升级而静默停推）。

### 129.3 列表页 SEO 通道（CWE-200 信息暴露 / 重复内容）

- 新出口 `/api/og/page/<path>` 走 `visible_posts_query()`，与前台列表**同一可见性口径**：
  草稿 / 定时未到 / 回收站 / 隐私文章一律不出现。已配 4 条内容级测试 + 变异验证
  （把 `visible_posts_query()` 换成 `Post.query` 时 4 条同时变红）。
- **不认识的路径一律 404 + noindex**，绝不给通用兜底页 —— 否则等于向爬虫开放无限个内容雷同的
  URL。`category` / `tag` / `series` 无 slug 时同样 404（前台也是 404）。
- 闸门与文章页**共用 `_shell_gate()`**：直敲 API（无 `?seo=1`）→ 302；经通道但被判为真人 →
  200 但 `noindex`；tool-bot / not-crawler → 404。**任何分支都不 3xx**（否则 nginx 的 UA 粗筛
  会把它再 rewrite 回来，形成无限重定向 —— v3.19.0 线上事故的根因）。
- 友链外链一律 `rel="nofollow noopener"`：友链是站长可编辑内容，不能拿站点权重为其背书。

### 129.4 移动端第二批端点（CWE-284 权限 / CWE-200 信息暴露）

**逐条对齐后台页面装饰器**，不沿用「管理员可读」的省事做法（D8.3 的明确要求）：

| 端点 | 后台对应 | 该页装饰器 | 本端点口径 |
| --- | --- | --- | --- |
| `/mobile/stats/report` | `admin.stats` | `@admin_required` | 管理员 |
| `/mobile/audit-logs` | `admin.audit_logs` | `@login_required @super_required` | 超管 |
| `/mobile/backups` | `admin.backup` | `@super_required` | 超管 |
| `/mobile/settings` | `admin.settings` | `@super_required` | 超管 |
| `/mobile/seo/summary` | `admin.seo_console` | `@super_required` | 超管 |
| `/mobile/cert` | 证书看护 | 超管 | 超管 |
| `/mobile/users` + 改角色 | `admin.users` | `@login_required @super_required` | 超管 |

PII 收口：用户列表邮箱**遮敏**（超管也给 `ab***@ex***.com`）；审计日志**不返回 `payload`**
（配置变更前快照，可能含历史密钥值）；站点设置走**白名单键**（黑名单会在新增密钥键时静默泄漏）。
写操作只保留「改角色」一条，且三条硬约束：不能改自己、角色名白名单、改后 `session_version+1`。
**刻意不做**备份触发/恢复（含 `_run(timeout=300)` 远程同步，移动端没有任务轮询通道）
与设置写入（30+ 键各有校验，漏一条即配置损坏）。

### 129.5 update.sh 版本号解析（可运维性，非安全）

原 `grep -oE 'APP_VERSION[[:space:]]*=[[:space:]]*"[0-9.]+"'` 强绑字面格式：改单引号 / 版本号带
`-rc1` / 加行尾注释都会**静默失配**，而它用在「覆盖后校验」——失配表现为 `fail_exit`
「版本号校验失败」，让人一路排查「zip 是否没覆盖成功」，实际是**量具坏了**。
现改为 `read_app_version()`：优先 python 按赋值语句解析（容忍引号/空格/注释/后缀），
无 python3 时回退正则；**「解析不到」与「版本不符」分开报错**（两者排障方向相反）。

### 129.6 测试与变异验证

新增 `tests/test_push_settings.py`（22 项）、`tests/test_seo_page.py`（20 项）、
`tests/test_mobile_ops.py`（12 项），并给 `test_update_chain_contract.py` 加 1 项静态契约。

**三处变异验证均实测变红**：
① 摘掉 `_post_json` 的 https 判定 → 「非 https 被拒」变红（实测真的去连 `example.com:80`）；
② 摘掉推送设置页的 `@super_required` → 「只有超管能进」变红；
③ 把 `visible_posts_query()` 换成 `Post.query` → 4 条可见性测试同时变红；
④ 把设置端点 `super_only=True` 改成 `admin=True` → 「管理员进不了超管专属端点」变红。

### 129.7 v4.10.1 热修：壳页被 CDN 缓存导致真人看到壳页（可用性事故，非安全面）

**这不是漏洞，但属于「同 URL 两种内容 + 允许缓存」的经典错配**，记在安全文档里是因为
它同样源于「缓存层的信任假设不成立」，与缓存投毒（cache poisoning）是一类问题。

- 现象：v4.10.0 上线后 `/archive` 对真人返回无样式壳页；直连源站一切正常。
- 证据：`eo-cache-status: HIT`、`age: 151`、`cache-control: public, max-age=300`。
- 根因：壳页与 SPA 共用 URL，仅靠 `Vary: User-Agent` 区分，而 **EdgeOne 不按 Vary 分桶**。
- 处置：`_shell_headers` 改 `Cache-Control: no-store`（文章页与列表页统一）。
- 判据：测试同时断言「必须含 no-store」**且**「不得含 public / max-age」——
  只查前者会让 `public, max-age=300, no-store` 这种矛盾写法假绿。
- ⚠️ 遗留：修复只对**新响应**生效；CDN 上已缓存的旧壳页要等 `max-age=300` 自然过期
  （或在 EdgeOne 控制台手动清 `/archive`、`/about`）。部署后需实测确认 `eo-cache-status` 已不为 HIT 携带壳页。

---

## R128 · v4.9.0 发版安全审查（升级地图 6 项落地 · 越权 / 隐私 / 重试幂等）

**范围**：按 `ROADMAP.md` §3.1 落地 6 项 —— 设备/浏览器分布（新增 `visit_log.device` / `browser`
两列 + Alembic 迁移 `d9f1a4c7b2e8`）、推送指数退避重试（`notify.py`）、留言墙敏感词过滤
（`api/common.py::find_spam_hit`）、搜索历史（纯前端 localStorage）、内容日历（新增
`GET /admin/content-calendar`）、分享卡片模板库（`og_image.py` + 设置项 `og_template`）。
另含 3 处 ROADMAP 过时描述修正与 lint 棘轮收紧（475→472）。

### 128.1 八维核对

| 维度 | 结论 |
|---|---|
| **认证** | 内容日历 `@login_required`，匿名访问返回非 200（`test_未登录不能看日历`）✅ |
| **授权（越权）** | ⚠️ **本轮唯一实质性风险，已修**：日历会把**草稿标题**铺在格子上，初版沿用 `@login_required` 而未做归属过滤 → 普通作者可看到他人未发布草稿。已对齐 `admin.my_posts` 口径（`if not user.is_admin_role: 按 author_id 过滤`），并配 `test_普通用户看不到他人文章标题` 专项守卫 ✅ |
| **CSRF** | 本轮无新增写路由；`og_template` 走既有后台设置页（`POST /admin/settings`，`@super_required` + 全局 CSRF 钩子）✅ |
| **注入** | `device` / `browser` 经 ORM 落库；日历 `year` / `month` 用 `request.args.get(..., type=int)` 强转；`find_spam_hit` 只读 Setting 不拼 SQL。SQLi 面为零 ✅ |
| **XSS** | `device` / `browser` 源自 User-Agent（**攻击者可控**），但后台经 Jinja `{{ }}` 自动转义；搜索历史经 Vue `{{ }}` 转义。无 `\|safe`、无 `v-html` ✅ |
| **隐私** | 🔒 只存解析后的粗分类（`手机` / `Chrome`），**不落原始 UA**。原始 UA 含设备型号与系统小版本、可指纹化。配反向断言：型号串 `SM-S918B`、`Android 13`、`Mozilla` 均不得出现在落库字段中（`test_手机UA解析为粗分类且不含可指纹片段`）✅ |
| **SSRF** | 无新增外发出口。模板库不改 URL；推送重试只向**管理员自配的** webhook 重发，不引入新目标 ✅ |
| **越权（水平）** | 见「授权」行；另留言/评论过滤为**拒绝提交**（400），不改写他人内容 ✅ |

### 128.2 已知取舍（ consciously accepted，非缺陷 ）

**推送重试会放大对外请求量，且可能导致重复通知。**

- 现状：Telegram / 企业微信 webhook 均无幂等键，退避重试 3 次最坏把同一条消息推 3 遍。
- 取舍理由：**漏推（运营侧完全无感）比重复（肉眼可见、无副作用）更糟**。
  且重试只在既有后台线程内进行，不影响请求路径。
- 边界：单渠道最坏多耗 7s（`1+2+4`），两渠道共 14s，均在后台线程。

### 128.3 遗留预警（未在本轮扩大，但需记档）

`notify.py::_post_json` 对目标 URL **无 scheme / 私网 / 重定向限制**。当前 webhook 只来自环境变量
（管理员自配），故不构成漏洞；但 ROADMAP §3.1 仍留有「`TELEGRAM_BOT_TOKEN` / `WECOM_WEBHOOK_URL`
进后台」待办 —— **该待办落地时，本函数会变成无防护 SSRF 出口，必须先补
scheme 白名单 + 私网过滤 + 禁跟随 3xx**（与 2026-10-07 全量审计报告第 7 条同源）。

### 128.4 测试证据

新增 5 个测试文件共 **27 用例**：`test_device_stats.py`（4）、`test_notify_retry.py`（6）、
`test_guestbook_spam.py`（5，含变异验证：摘掉留言过滤必须变红）、
`test_content_calendar.py`（4，含越权守卫与 block 渲染守卫）、`test_og_templates.py`（9）。
lint 棘轮：本轮一度引入 +3（SIM102 / F401 未用 `pytest` / `Setting` 失去唯一使用点），
已**逐条真修**而非抬基线，债务 475 → **472**。

---

## R127 · v4.8.7 发版安全审查（访客统计页数据表 CSS 打磨 · 无安全面）

**范围**：`templates/admin/stats.html` 仅 `<style>` 扩展（数据表 `.stats-table` 美化 + 环比涨跌徽章 + 暗色适配）。**无任何 Python / 路由 / JS 逻辑变更**，前端零构建（纯 Jinja/CSS）。

### 127.1 安全结论

- **无新增攻击面**：改动仅为 CSS 选择器与颜色，不引入 HTML 属性、不渲染用户输入、不改 DOM 结构（仅给「区间访客数据」表加 `metrics` 类、数值列右对齐）。
- **作用域隔离**：全部规则限定 `.stats-page`，不影响诊断页等其它后台 `.stats-table`（已确认 `admin.css` 诊断页样式独立）。
- **无注入 / XSS / SSRF / 越权面**：与 v4.8.6 一致，本次零新增。

### 127.2 测试

复用 `tests/test_stats_reset_searches.py` 渲染用例（5 passed），确认模板仍可正常渲染、未引入 Jinja 错误。完整套件 **1064 passed**（v4.8.6）。

---

## R126 · v4.8.6 发版安全审查（后台「常搜词汇」重置按钮 · CWE-284 / CWE-352）

**范围**：新增 `POST /admin/stats/reset-searches` 路由（`myblog/admin/stats.py`）、
`templates/admin/stats.html` 重置按钮与 UI 美化。**前端零构建**（纯 Jinja/CSS，无 vite 产物变更）。

### 126.1 八维核对

| 维度 | 结论 |
|---|---|
| 认证 | `@login_required` 拦截匿名：`tests/test_stats_reset_searches.py::test_anon_cannot_reset_searches` 断言匿名 POST 被拒、库零删除 ✅ |
| 授权 | `@super_required` 仅超管：普通管理员（`ROLE_ADMIN`）POST 返回 **403**，库零删除（`test_normal_admin_forbidden`）✅ |
| CSRF | 全局 `before_request` 钩子对无 token 请求直接 403；**正反双向验证**——超管缺 token 既被拒、库也不删（`test_csrf_required_even_for_super`），证明守卫非空转 ✅ |
| 注入 | `SearchLog.query.delete()` 走 ORM，无用户可控入参；SQLi 面为零 ✅ |
| XSS | 不渲染任何用户输入；flash 文案为服务器生成的整数计数（`已重置…清空 N 条`），无反射/存储 XSS ✅ |
| 审计 | `log_audit("clear","search_log",None,...)` 落审计表（action=clear / target=search_log），`test_super_admin_clears_searches` 断言审计行存在 ✅ |
| 越权 | `target_id=None`、无横向越权路径；按钮仅超管可见（路由层已收口，模板无额外权限分支）✅ |
| 可用性/误用 | 不可逆清空操作有三重闸门：超管 + CSRF + 客户端 `onsubmit` 二次确认；不提供批量/循环入口，无 DoS 面 ✅ |

### 126.2 本功能最该防的失败模式：空守门员

一个「重置」按钮最危险的失败方式是：**CSRF 校验形同虚设，任何人都能清空热搜榜**。
专防设计：

1. **全局钩子不豁免无会话用户** —— `app.py` 的 `before_request` 对缺失/无效 token 一律 403，
   连游客都拦，杜绝「只验登录、不验 token」的常见漏 ✅
2. **正反双向测试** —— 仅有「能拦」的用例会假绿（一个永远返回 None 的过滤器也能全绿），
   故 `test_csrf_required_even_for_super` 用「超管 + 缺 token → 库不删」做反例，守卫失效必红 ✅

### 126.3 测试覆盖

新增 `tests/test_stats_reset_searches.py` 5 条：匿名拦截 / 普通管理员 403 / 超管清空+审计 / 缺 CSRF 拒删 / 页面渲染出按钮。
完整套件 **1064 passed, 0 failed**（v4.8.6）。

---

## R111 · v3.25.13（WebDAV 备份「已配置却异常」· README 版本史门禁）

### 111.1 现象与取证

大帅反馈：**后台「WebDAV 云盘」配置好之后，备份异常。**

不猜，先取证两条：

1. **生产审计日志**：自 2026-09-12 起只有「后台任务已提交：xxx」，**一次「备份成功」都没有**。
2. **用真实 `SECRET_KEY` 解密库里的 WebDAV 密码后直连坚果云**（密钥取自
   `/proc/<gunicorn master pid>/environ`，不是 env 文件 —— 那个文件没有 `KEY=` 行）：

| 动作 | 结果 | 含义 |
|---|---|---|
| PROPFIND `https://dav.jianguoyun.com/dav/` | **HTTP 207** | 认证其实是**好的** |
| `current-user-privilege-set` | 只有 `<d:read/>` | **根目录只读** |
| PUT 一个测试文件 | **HTTP 404** | 写入被拒 → 备份必然失败 |

### 111.2 根因

| # | 问题 | 后果 |
|---|---|---|
| 1 | 填的是云盘**根目录**，而不少云盘的根目录**只读** | 认证通过、写入 404，备份每次失败 |
| 2 | 错误文案只报 `命令退出码 22` | 用户无从判断是地址错、凭据错还是目录只读，**没法自助排障** |
| 3 | `apply_env()` 只在 `backup.py` **被导入时**跑一次 | 后台保存只作用于**处理保存请求的那个 worker**，别的 worker 仍用导入那一刻的旧值 —— 页面却写着「保存后立即生效（无需重启）」 |
| 4 | 模块级 `apply_env()` 失败是静默 `except: pass` | 密钥解密失败等场景下，表现就是「配置页显示已配置、备份却不上传」 |

### 111.3 修法

- **`_cmd_err()` 带上 curl 的 stderr**：原因早写在 stderr 里（`The requested URL returned error: 404`），
  原先被丢掉，只留一个退出码。
- **`_webdav_hint()`**：把 4xx / 退出码 22 翻译成「目录只读，请改填可写的子目录」。
- **`probe_webdav()`**：`PROPFIND` 读 `current-user-privilege-set` 里有没有 `<d:write/>` 判可写性
  （**不写任何文件**），返回 `ok` / `auth_failed` / **`not_writable`** / `missing` /
  `unreachable` / `unconfigured`；后台加「🔌 保存并测试 WebDAV」按钮（先落盘再探测，5 次/分钟限流）。
  ⚠️ 地址仍受 `_webdav_url_ok()` 约束（只允许 http/https、不得以 `-` 开头 ——
  否则 `curl -T file://…` 是任意本地路径写入）。
- **`_refresh_env()`**：`create_backup()` 与 `probe_webdav()` 开头各调一次，**不靠导入时机**。
- 模块级 `apply_env()` 失败由静默改 `logger.warning`。

### 111.4 变异验证

① 撤掉 `<d:write/>` 判定（改 `if True`）→ **1 条变红**
② 撤掉 `probe_webdav()` 里的 `_refresh_env()` → **6 条变红**
③ `_cmd_err()` 丢掉 stderr → **1 条变红**
④ `_webdav_hint()` 不翻译 → **1 条变红**。均精确命中。

> 首次跑变异时 MUT-2 判成「没变红」，原因是驱动脚本用了 `-x`（第一条失败就停，
> 根本没跑到目标用例）→ **判「守卫无效」前先确认用例真的跑到了**。

### 111.5 同批：README 极简 + 版本史单一真相源

README 被逐版追加版本说明堆到 137 行（正文近半是版本史），与 CHANGELOG 重复且必然漂移。
现：`README.md` → 69 行、`myblog/README.md` → 163 行，版本史整段删除；
**并把规则做成门禁**（`check-staged.py` 两条硬拦截 + `tests/test_readme_no_version_history.py` 5 条守卫）。

### 111.6 验证

**670 passed**（647 → 670）/ ruff 全仓全绿 / 棘轮 490 = 490 / i18n 通过 / L3 门禁退出码 0。
**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、无新增环境变量；
仅后端 + 模板变更，**前端产物无变化**。

---

## R112 · v3.25.14（定时任务跑的备份永远失败 · 缺 `SECRET_KEY` + 401 提示指错方向）

### 112.1 现象：两条路径结果不同

v3.25.13 上线后做端到端实测：

| 跑法 | 结果 |
|---|---|
| `python backup.py run`（带 `SECRET_KEY`） | `远程[webdav]: ✅ ok`，云盘里出现 zip + manifest |
| `bash backup.sh`（计划任务走的那条） | `curl: (22) The requested URL returned error: 401` |

同一台机器、同一份配置，只差一个环境变量。

### 112.2 根因

后台配置的备份密钥（OSS Secret / WebDAV 密码）是 **Fernet 密文**，解密要用 `SECRET_KEY`
派生的密钥。gunicorn 由宝塔带 env 启动所以能解；**计划任务不带任何项目环境变量** →
`_fernet_key()` 抛 `RuntimeError`，而 `decrypt_secret()` 的设计是**失败返回空串、不抛异常**
（避免密钥轮换时崩掉备份）→ curl 拿着**空密码**去认证 → 只得到一句 `401`。

即：**v3.25.14 之前，每天凌晨的异地容灾备份从来就不可能成功**。「根目录只读」
（R111）只是压在它上面的第二个问题。

### 112.3 附带发现：v3.25.13 自己引入的文案缺陷

`_webdav_hint()` 把 `40[1345]` 一并翻成「目录只读」→ 定时任务因缺 `SECRET_KEY` 报出的
**401 被提示成「请改填子目录」**，把排查带偏。已按语义拆开：

- `401` / `403` → 认证失败（并点出「后台测试正常、定时任务失败 = 没加载 `SECRET_KEY`」）
- `404` / `405` → 目录不可写/不存在（改填可写子目录）
- stderr 为空、只有退出码 22 → 两条都给，不瞎猜

### 112.4 修法

1. `backup.sh` 先 `set -a; . "$ENV_FILE"; set +a`（路径可 `BACKUP_ENV_FILE` 覆盖，
   文件不存在则跳过并告警）。
2. 新增 `_secret_unreadable()`：密文在库里但解不开时，`sync_webdav()` / `probe_webdav()`
   **在发起请求前就明确报错**，不再拿空密码去撞 401。
3. `_webdav_hint()` 按上面三条拆开。

### 112.5 变异验证

① 退回旧的单分支提示（401 也被说成只读）→ **1 条变红**
② 撤掉 `sync_webdav` 的「解不开的密钥」拦截 → **1 条变红**
③ `backup.sh` 不再 source 环境变量文件 → **1 条变红**。均精确命中。

> MUT-A 第一次判成「没变红」，是**测试不够强**（变异后落到含糊的兜底分支仍含
> 「认证失败」字样），已收紧断言：已知是 401 就不该再提 404/405。

### 112.6 验证

**22 passed**（`tests/test_backup_webdav.py`，+7）/ ruff 全仓全绿 / 棘轮 490 = 490。
**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、无新增环境变量；
纯后端 + 脚本变更，**前端产物无变化**。

---

## R113 · v3.25.15（`GH_MIRROR` 没被真正用上 · 下载通道改为镜像优先）

### 113.1 现象：传了镜像参数，部署却仍在直连苦等

v3.25.14 部署命令带了 `GH_MIRROR='https://gh-proxy.com/'`，但日志显示后端包走的是
`https://github.com/...`、**耗时 133 秒**（00:33:22 → 00:35:35）。同刻实测：

| 通道 | 速度 | 3 MB 后端包耗时 |
|---|---|---|
| `gh-proxy.com` | 873 KB/s | ~4 秒 |
| `ghfast.top` | 452 KB/s | ~7 秒 |
| **直连 GitHub（实际走的）** | 21 KB/s | **133 秒** |
| `ghproxy.net` | 15 KB/s | >200 秒 |

### 113.2 根因：镜像被放在「兜底位」

```bash
try_urls=("$url")                          # 直连排第一
if [ -n "$GH_MIRROR" ]; then
  try_urls+=("${GH_MIRROR}${url}")         # 镜像只是第二顺位
fi
```

`gh_fetch()` 对每条 URL 重试 2 次、`--max-time 180`。直连虽然慢但**第一次就成功了**，
于是镜像一次都没轮上 —— **「配了镜像」≠「用上镜像」**。

### 113.3 修法与安全性评估

新增 `GH_MIRROR_FIRST`（**默认 `1`**）：显式配了 `GH_MIRROR` 时镜像优先、直连兜底；
`GH_MIRROR_FIRST=0` 取回旧顺序。两个前置条件缺一不可（`GH_MIRROR` 非空 **且** 开关为 1），
避免未配置时拼出空前缀 URL。

**安全性不变**，理由与 R103（v3.18.7）一致且仍成立：

- 产物无论走哪条通道，都要过 **Ed25519 分离签名**（公钥内置，私钥在发布者手里）+ zip
  注释内嵌哈希双源互证；
- 镜像**无法伪造内容**（没有私钥），最坏只能给出**旧版本的合法签名** —— 这属于降级，
  由版本单调性比较 + `ALLOW_DOWNGRADE` 默认拒绝兜住；
- 本轮只是把「用户已显式信任的镜像」从兜底位提到首位，风险面与它原本作为兜底位时相同，
  并未引入任何新的第三方通道（脚本内**仍不存在**任何公共镜像字面量）。

### 113.4 验证

新增契约断言 `test_gh_mirror_is_tried_first_when_configured`
（`tests/test_update_chain_contract.py`）：钉住默认开关值、镜像优先的数组顺序与双重前置条件。
变异测试：删掉镜像优先分支 → 该断言精确变红。
**无迁移、无新增依赖、纯脚本变更，前端产物无变化。**

---

## R114 · v3.25.16（友链 RSS 聚合：SSRF + 存储型 XSS + SMTP 明文落库）

> 4.0 开发前的全量审计（6 组并行 → 主审逐条复现）。完整报告：
> `docs/audit/2026-10-07-full-audit-report.md`。

### 114.1 【中危】CWE-918 服务端请求伪造 —— 校验与使用分离

`feed_agg.py::_safe_url()` 有三层防护（scheme 白名单 → 主机名黑名单 → `getaddrinfo`
解析后判私网），但只在**抓取前**查一次；真正发请求的 `feedparser.parse(url)` **自建
urllib 会话**——重新解析 DNS（重绑定）+ **自动跟随 3xx**。攻击链：公网 RSS 地址通过校验
→ 回 `302 Location: http://100.100.100.200/`（阿里云元数据）或内网 Redis/MySQL/PG
→ 跳转目标**从不被复检**。触发入口 `/api/feed/circle` 是**匿名 GET**。

同仓库 `seo_push.py:91-113` / `oauth.py:22-28` **早有标准答案**（`_NoRedirect`），
`feed_agg` 当时没复用。修法：自建禁重定向 opener 抓字节再喂 feedparser（**顺带消除
重复解析 DNS 的重绑定窗口**）。守卫：AST 断言全文件不得再出现裸 `feedparser.parse(URL)`
——**该守卫在修复过程中真实抓出了第三处漏改**。

### 114.2 【中危】CWE-79 存储型 XSS —— 条目链接无协议白名单

RSS 条目的 `<link>` 此前**只判空**，`javascript:fetch(...)` 原样进 `SquareView.vue` 的
`:href`。`target="_blank"` **不阻止** `javascript:` 执行，`rel="noopener"` 只隔离
`window.opener`。加重情节：恶意 URL 进 `_CACHE` 且 **TTL 900 秒**，撤掉内容后仍持续。
修法：`_safe_item_url()` 只放行 http/https 且要求 netloc 非空。

### 114.3 【中危】CWE-312 明文存储敏感信息 —— SMTP 授权码

`admin/settings.py` 把 SMTP 授权码**明文**写进 Setting 表，而 `admin/seo.py:12-14` 的
模块注释**早已写明**「不照抄 `mail_password` 的明文落库错误做法」——备份密钥与 SEO token
均已 Fernet 加密，唯独它是历史遗漏。修法：写入侧 `encrypt_secret()`、读取侧
`decrypt_secret()`（对无 `bkenc$` 前缀值原样返回 → **存量明文不迁移也能读**），
另附幂等迁移脚本 `tools/migrate_mail_password.py`（加密后立刻回读比对）。

**审计副产品**：由此确认**本项目 `audit.py` 中不存在 `_redact()` 函数**（`_redact()` 实际在
`seo_push.py:148` 与 `mcp_diag.py:44`）——此前项目笔记记错了，已订正。

## R115 · v3.25.16（路径穿越 / 放大 DoS / 可见性收口 / 健壮性）

### 115.1 【中危】CWE-22 路径穿越 —— OG 封面

`og_image.py::_local_cover_path` 三条分支全可穿越，**兜底分支 `c` 完全用户控制、连前缀都
不要求**（`../config.py` → `_HERE/static/../config.py`）。实测逃逸范围**可到文件系统根**
（`../`×8 能读到 `E:/Windows/win.ini`）。三道闸门使其维持低危：`cover` 来自后台表单（需
管理员）、`/api/og/post/<slug>.png` 不接受 URL 参数、`Image.open()` 解不出非图片内容。

修法两处教训（均已写进代码注释）：**基目录不能取 `_HERE`**（否则 `static/../config.py`
归一后仍在 `myblog/` 内 → 放行，第一版就是这么错的，测试当场变红才发现）；
前缀判断必须用 `startswith(root + os.sep)` 而非 `startswith(root)`（防同前缀兄弟目录）。
最终收敛为单一 root = `_HERE/static`，并**保留 `uploads/` 前缀**——它是
`routes.py` sitemap 白名单明文承认的输入契约（`:743`「与 `_local_cover_path()` 同一口径」），
删掉属行为收窄而非漏洞修复。

### 115.2 【中危】CWE-400 无界资源消耗 —— 通知扇出

匿名可提交 **5MB** 评论正文 → `notify_mentioned()` 把正文里所有互不相同的 `@名字` 逐个
`User.query` 并各插一条 `Notification` → **单条评论放大成上万次 SELECT + 上万行通知**。
评论接口限流（10/分钟）挡得住条数、**挡不住单条超长**。修法：评论限 2000/500 字（超出**拒绝**
而非截断，截断会让用户以为提交成功却丢内容）+ `@提及` 去重后最多取 20 个。

### 115.3 【低危】CWE-863 可见性收口 3 处

`api/stats.py`、`api/reactions.py`、`api/ai.py` 均为**裸查 `Post`**（`Post.query.filter_by(slug=...)`
或只按 `Comment.id` 取），绕开 `visible_posts_query()`。不泄露正文，但构成「私密/未发布文章
存在性」的侧信道。**这是同一问题的第 5、6、7 次复发**，已全部收口。

### 115.4 【低危】CWE-248 未捕获异常 —— 匿名 500

`hmac.compare_digest(str, str)` 对非 ASCII 抛 `TypeError`，外层只捕获
`(HTTPException, RedisError)` → 匿名发 `Authorization: Bearer 💥` 即得 500。
修法：统一 `encode("utf-8","surrogatepass")` 后按 bytes 比对（恒定时间且不挑字符集）。

### 115.5 【功能缺陷】`/mcp-write` 未列入 CSRF 豁免 → 端点实际不可用

`app.py` 的 CSRF 豁免清单只列了 `/mcp`。而 `/mcp-write` 同样**自带 Bearer 鉴权、非会话**
（不依赖 Cookie），合法 MCP 客户端拿不到 CSRF token → POST 被 403 拦死。
已加入豁免清单（两端各自精确列出，不用 `startswith` 粗放）。

### 115.6 误报记录：2FA「完整绕过」不成立

审计组报出**严重**级 2FA 绕过并附可执行 PoC。主审复现后**驳回**：

| 场景 | 实测 |
|---|---|
| 闸门开启 + 已绑定 + 仅密码会话 | `enroll` → **401**，`secret_enc`/`enabled` **零变化** |
| 同一会话访问 `/admin/` | 401/302/403 |
| **全局开关关闭**时 `twofa.enroll(user)` | 返回非 `ok`，绑定**零变化** |

根因是把 `twofa_enabled`（**默认 false**）的状态当成「2FA 已启用」。**教训：有 PoC ≠ 成立。**

### 115.7 本轮沉淀的三条审计纪律

1. **解析模型须等于执行模型**——正则扫文本 ≠ Python 注释语义；字符串前缀 ≠ 文件系统语义。
2. **判据须用已知存在的目标，且正反双向**——「已知存在确能穿透（没拦漏）+ 已知应拒确被拒
   （没拦错）+ 合法目标确能放行且不随配置漂移失效」。只有反向用例时，「永远返回 None」
   的过滤器也能全绿。
3. **报告须覆盖被测配置空间而非单点**——同一份修正在不同 root 取值下行为不同，
   只测一种取值得出的「已修复」在另一种取值下可能静默失效。

**核心一句**：**修复本身也要测回归，否则「修好了」和「改坏了」在报告里长得一模一样。**

---

## R116 · v4.0.0（列表接口 `.all()` 全量物化 + 首页匿名无限流 · CWE-400）

**来源**：`docs/audit/2026-10-07-full-audit-report.md`【低危 7】。当时判「语义面较大，建议 4.0
一并处理」，现于 4.0 开发首批落地。**范围**：`myblog/api/common.py`（新增 `paged_posts()` /
`_DISPLAY_ORDER`）、`myblog/api/posts.py`（`/posts` `/search` `/categories` `/tags` `/hot-tags`
`/post/<slug>/related` `/also-viewed` `/category/<slug>` `/tag/<slug>` `/archive`）；
测试 `tests/test_posts_pagination_v4.py`（47 条）。

### 116.1 去重下推：为什么必须是 `FIRST_VALUE` 而不是 `MAX()`

`lang_dedup()` 的组顺序 = 「组内**首成员**在展示顺序中的位置」= `(is_pinned, created_at, id)`
的**字典序 argmax**。对两列分别取 `MAX` 会拼出不属于任何一行的组合（首成员 `(1, t_early)`、
另一成员 `(0, t_late)` → `MAX` 得到 `(1, t_late)`），组序就错了。
`FIRST_VALUE(x) OVER (PARTITION BY 组 ORDER BY 展示顺序)` 取的正是首成员**同一行**的值。
差分测试里专门造了「首成员置顶但最旧 / 另一成员不置顶但最新 + 一个夹在中间的独立置顶文章」
这组数据来钉死它；变异验证把 `first_value` 换成 `max` 后该用例立刻变红。

### 116.2 「不慢」是量出来的，不是默认的

第一版下推后 `?lang=` 分支在 1000 篇规模下**反而慢 1.4x**（35.2 → 24.5ms 的反向）。而
`?lang=` 恰是首页默认路径：`store.js` 的 `contentLang` 初值 `"zh"`，`HomeView.vue` 每次都带。
两刀修回：

1. `total` 从 `SELECT count(*) FROM (窗口子查询) WHERE rn=1`（窗口计算跑两遍）
   改为一条 `COUNT(DISTINCT 组)` 聚合；
2. 同一条聚合里多取 `COUNT(*)`，用「**组数 == 文章数**」判定「每组恰好一篇 → 去重恒等」，
   命中即完全跳过窗口、退化成普通分页（顺带省掉「先探一次有没有译文组」的额外查询）。

最终 1000 篇：首页 21.9→7.0ms（3.1x）、末页 2.6x、`?lang=` 无译文组 3.0x、有译文组 1.1x。
**唯一仍变慢的组合**是「文章少 + 有译文组」（200 篇 +2.8ms）—— 已如实写进 CHANGELOG，不粉饰。

### 116.3 守卫踩过的坑：`_ID_ONLY` 前缀匹配放过了无界查询

「SQL 必须带 LIMIT」这条判据里，id-only 投影最初写成 `s.startswith("SELECT post.id ")`。
而全列查询**恰好也是** `SELECT post.id AS post_id, post.title AS ...`（`post.id` 后面同样是空格），
于是无界的 `.all()` 被当成 id-only 放行，M1/M5 两个变异**全绿假过**。改成正则
`^SELECT\s+post\.id\s+AS\s+\w+\s+FROM\s+post\b`（要求 `post.id` 后**紧跟 FROM**）后才变红。

**核心一句**：**判据本身也要能被证伪** —— 先跑变异，变异没红时默认「守卫太松」，
而不是默认「改动没问题」。

---

## R117 · v4.0.0（新增「自定义外部入口」的设计期审计 · CWE-79 预防）

**性质：不是缺陷修复，是「新增功能时把攻击面先关掉」的记录。** 之所以写成一轮：这个入口的
地址由后台填写、前台用 `:href` 直接绑定，结构上就是**存储型 XSS 的候选入口**——
若哪天 `entry_url` 变成 `javascript:...`（手滑 / 注入 / 迁移脏数据），页面一加载就在访客浏览器里执行，
而且**不报错**：导航栏看起来一切正常，链接也点得动。这类缺陷一旦落地，靠人眼是发现不了的。

### 117.1 防护：入口两侧各拦一次

| 位置 | 措施 | 为什么 |
|---|---|---|
| 写入侧（`admin/settings.py`） | 非 http/https 的地址**不写库**，并 flash 提示「本次填写未保存」 | 让错误在**配置时**就可见；同时同表单其它字段照常保存（一个字段填错不该丢掉整张表单，同 `site_url` 的取舍） |
| 读取侧（`api/site.py::_public_entry`） | 输出前**再判一次**，非法即 `enabled=false` + `url` 为空 | 兜住「库里已经是脏数据」的情况（旧备份恢复、直接改库、未来某个写入路径漏校验） |

判据集中在 `utils.is_http_url()` 一处，两侧共用——**不同时有两份实现，就不会漂移**。
同时拒绝协议相对地址 `//evil.com`：它继承本站协议却指向外域，既不合「外站入口」的意图也不好审计。

### 117.2 其余检查

- **越权**：入口配置在 `/admin/settings`，已由 `@super_required` 覆盖，保存需 `X-CSRF-Token`（全局 POST 保护）。
- **外链**：前台一律 `target="_blank" rel="noopener"`，不把 `window.opener` 交给外域；测试里有静态扫描钉住这两项。
- **限流 / 注入**：无新增写接口、无新增 SQL（读的是既有 `Setting` 表，`filter_by` 参数化）。
- **可回滚**：`entry_enabled` 已进配置快照（`config_rollback`），误关可回滚——「后台可配」才算完整。

### 117.3 验证

`tests/test_site_entry_v4.py` 27 条：URL 白名单正反用例、**4 种危险 scheme 参数化断言「绝不出现在前台 JSON」**、
开关真能关、后台四个控件齐全且开关被 `label` 包裹、非法值不落库但其它字段照常保存、
开关进快照、前台外链带 `noopener`。**变异验证：把出口的 `is_http_url` 判断换成 `if False` → 5 条立刻变红。**

---

## R118 · v4.1.0（外部入口「一个 → 多个」的安全边界复审 · CWE-79 预防）

> **性质**：不是发现新漏洞，是把 R117 那条 XSS 边界**在数据结构变化后重新确认一遍**。
> 入口从「单条四件套」变成「多条 JSON 数组」时，最容易发生的事是
> **换了存储却忘了把校验一起搬过去** —— 那会让已经防守住的面重新打开。

### 118.1 复审结论：两层防线仍在，且新增了一处

| 层 | v4.0.0 位置 | v4.1.0 位置 | 行为 |
|---|---|---|---|
| 写入侧 | `admin/settings.py` | `admin/nav_entries.py` | 非 http/https 拒绝入库并提示（add）／保留旧地址（edit） |
| 出口侧 | `api/site.py:_public_entry` | `api/site.py:_nav_entry_items` | 输出前再判一次，非法整条剔除 |
| 新增：迁移路径 | — | `nav_entries.migrate_legacy` | 旧配置走同一批读数再落库，不绕过出口判断 |

`utils.is_http_url` 仍是**唯一判据实现**，三个调用点共用。

### 118.2 本轮特意加严的一处

v4.0.0 的安全测试是「通过后台表单提交脏数据」，这只能证明**写入侧**有效。
本轮改为**绕过后台表单直接写库**（`nav_entries.save()`写危险 URL），
模拟「迁移脚本 / 备份还原 / 后续改动绕过表单」的最坏情况，单独验证**出口侧**这条防线。
判据：`/api/site` 的 `entry.url` 必须为空且 `entries` 必须为空数组。

理由：两条防线如果只有合起来才有效，那等于没有纵深。

### 118.3 非安全性但也值得一提的「删除不掉」陷阱

迁移的幂等判据必须是「`nav_entries` 这个 key **存不存在**」，不能是「有没有内容」。
若用后者，用户在管理页删光入口后，下次启动迁移逻辑会判定「没内容 → 再迁一次」，
旧配置又回来了 —— 表现为**删不掉**，而从表象看谁也想不到是迁移的问题。
`test_migrate_legacy_runs_only_once` 钉死这一点。

### 118.4 验证

- `tests/test_site_entry_v4.py` 29 条（改造）+ `tests/test_nav_entries_v4_1.py` 20 条（新增）。
- **变异验证 4 组全红**：① 出口过滤失效 ② 迁移不幂等 ③ 数量上限失效 ④ 写侧白名单失效。
  其中 ① 和 ④ 直接对应本节的 XSS 边界。
- 全量 794 passed；`ruff check .` 全仓 0 error。

## R119 · v4.2.0（IP 黑名单与「反爬限流」开关解耦 · 安全功能失效缺陷修复）

> **性质**：不是新攻击面，是修一个**安全功能从未生效**的缺陷 ——
> 属于「配了 ≠ 用上」家族在本项目的第四次出现（前三次：`_safe_url()` 未被真正的 fetch 使用、
> 白名单未 bump `_RENDER_VERSION`、cron 不带 `SECRET_KEY`）。

### 119.1 缺陷：黑名单整条挂在默认关闭的开关后面

`bot_guard.check_bot_guard()` 的旧结构是：

```
if not guard_enabled():   # bot_guard_enabled 默认 false
    return None
... is_blocked(ip) 检查 ...
```

后果：只要「反爬限流」开关关着（默认态，且线上从未开启），**封禁检查整条不执行** ——
后台「反爬限流保护」页能操作 `BotBlock` 记录，但那条记录从来不会被读取。
本次给后台加「按 IP 拉黑」时若直接复用 `is_blocked()` 而不动这个结构，
新功能会**一上线就是坏的**，现象是「拉了黑但对方还能访问」——
不从任何报错或日志里能看出来。

### 119.2 修法：手动黑名单检查前移到开关判断之前

```
ip = client_ip()
blocked = is_blocked(ip)             # 手动黑名单：无条件生效
if blocked: return 429
if not guard_enabled(): return None  # 自动限流：仍受开关控制
```

两条链路从此独立：**管理员显式拉黑 = 安全决策，优先于运营开关**；
自动限流保持「默认关、可后台开」的原有语义不变。

### 119.3 连带修掉的第二个缺陷：永久封禁被自动限流改短

`_record_block()`（自动限流路径）原先对既有记录无差别更新 `reason` / `blocked_until`。
若某 IP 已被手动**永久**拉黑，随后它再触发一次限流，`blocked_until` 就会被覆盖成
`now + 30min` —— **永久封禁悄悄降级成半小时**，且 `reason` 被改写后连
「这条是不是手动拉的」都查不出来。现在 `reason == "manual"` 的记录只累计
`hit_count`，不动封禁期与原因。

### 119.4 覆盖范围（明确记录的边界）

- 黑名单经**前台蓝图** `main_bp.before_request` 生效；`/api/`、`/admin/`、`/static/`、
  `/mcp`、`/feed.xml` 等前缀按原有设计跳过（后台与接口有各自鉴权 / 限流）。
  副作用是正面的：**管理员不可能把自己锁在后台外面**，误拉黑随时能解封。
- `is_blocked()` 的判据是 `blocked_until > now`，故「永久」= `blocked_until = 9999-12-31`
  （`None` 在既有语义里表示「仅记录未封禁」，不能复用）。

### 119.5 验证

- `tests/test_visitor_analytics_v42.py` 11 条，其中两条是本节缺陷的回归：
  **开关关闭时拉黑仍 429**（含「未拉黑 IP 正常放行」的对照组）、
  **自动限流不改短永久封禁**（命中次数预推到阈值以上，确保覆盖 `blocked_until` 分支）。
- **变异 3 组全红**：① 黑名单检查后移到开关之后 ② 去掉手动记录保护 ③ 区间边界 off-by-one。
- 全量 pytest 806 passed；`ruff check .` 全仓 0 error。

---

## R120 · v4.3.0（移动端管理接口 `/api/mobile/*` 的设计期审计 · 新增攻击面）

后台能力此前只能通过**浏览器 + HTML 表单**触达；本版把它们开成 JSON，调用方从「会渲染表单的
浏览器」变成「任意持凭据的客户端」。本轮是**新增面**的设计期审计（CWE-862 缺失授权 /
CWE-863 错误授权 预防），不是事后发现缺陷。

### 120.1 新增了什么面

- 30 个端点，全部落在既有 `/api/` 前缀下（不新增 nginx 反代规则、不改 CSRF 豁免白名单）。
- 写面里最敏感的两条：**IP 拉黑/解封**（可让某个访客整站 429）与 **文章发布/软删**（对外可见内容）。
- 读面把 `VisitLog` 的 IP 明细带出去了（此前只在后台页面展示）—— 见 120.5 的残留项。

### 120.2 权限矩阵与后台逐条对齐（这是本轮唯一的「必须不放宽」约束）

| 动作 | 后台 `/admin/*` | 本版 `/api/mobile/*` |
|------|-----------------|----------------------|
| 全站评论 / 访客日志 / 统计 / 回收站 / 微动态 / 友链申请（读） | `admin_required` | `_role(admin=True)` |
| IP 拉黑、解封 | `super_required` | `_role(super_only=True)` |
| 发文、看/改/发/删自己的文章 | `login_required` + `_can_edit_post` | `_role()` + 同一 `_can_edit_post` |
| 超管未改默认密码 | 跳 `/admin/setup` | `403`（不放行任何业务） |

`_role()` **刻意不复用**后台装饰器：那三个装饰器未登录时是 `redirect(url_for("main.login"))`，
客户端拿到的是 200/302 + 一页登录 HTML，会把「没登录」误判成「接口正常」。判定条件本身
（`session.user_id` → `User` → 角色 → `must_change_password`）逐条照抄，**没有放宽任何一条**。

### 120.3 提权字段：这是 API 相对表单的天然缺口，必须在服务端补

后台编辑页对普通用户「看不到置顶勾选框」，等于一层界面保护；JSON 客户端可以直接构造
`{"is_pinned": true}`。因此本模块在服务端按角色丢弃提权字段（与 `update_post_core` 同一规则，
不是两套）：`is_pinned` 仅管理员、`is_private` / `reward_enabled` / `reward_qr` 仅超管、
`author_id` 恒取会话用户（不接受客户端指定作者）。`tests/test_api_mobile.py` 有专门一条
断言「普通用户经 API 提交这三项后，落库仍全为 False」。

### 120.4 继承下来的闸门（新代码一行都不用改就生效）

- **CSRF**：`app.py` 的豁免白名单是**精确路径前缀枚举**，`/api/mobile/*` 不在其中 →
  所有 POST/PUT/DELETE 必须带 `X-CSRF-Token`。若将来有人为了省事把 `/api/mobile` 加进豁免，
  等于把后台写操作变成无 CSRF 保护的公开面 —— 本轮起这条由测试盯住
  （`test_写接口缺_csrf_被全局闸门拦下`）。
- **闸门顺序记录在案**：CSRF 早于业务视图，所以「未登录 + 无 token」得到 **403（CSRF）**
  而非 401。已在 `API.md` 与测试 docstring 双处写明，避免将来被当成 bug「顺手修正」成放宽。
- **2FA**：全局会话闸门对 `/api/` 前缀统一生效，本模块无需自查（也不允许自查 —— 漏一条路径
  就是 v3.21.2 审计 C2 的复现）。
- **限流**：写接口按客户端 IP 限流（发文 20/分、评论动作 60/分、上传 10/分、拉黑 20/分、
  微动态 5/分与前台同强度）；只读接口沿用 `/api/stats/*` 的 30/分口径。
- **审计**：每个写操作落 `AuditLog`，动作名统一 `mobile_*` 前缀，与后台操作日志同表同列，
  事后可按「谁在手机上拉黑了哪个 IP」追查。

### 120.5 残留风险（写明，不假装已解决）

- `/api/mobile/visit-logs` 向**管理员**角色（含非超管的管理员）输出访客 IP 原文，与后台
  访客日志页同级 —— 权限没有放宽，但**出口从「一个页面」变成「一个可批量导出的 JSON 接口」**，
  翻页抓取比人肉点页面容易得多。若日后要收紧，最小改动是把该端点升到 `super_only`。
  本轮**未**擅自收紧，因为这会让非超管管理员在 App 里看不到后台本来看得见的东西。
  → **v4.3.1 已按此结论收紧，见 R121。**
- 批量审核单次上限 500 条（防一次请求把整表扫一遍），但**没有**做「按 id 列表的所有权校验」
  —— 评论本就属于全站数据，管理员有权操作，与后台批量口径一致。
- 本版**不**提供删除文章硬删（`/trash/<rid>/purge` 除外）、改密码、2FA 开关、系统设置、
  备份、MCP 令牌等入口：这些在 App 里没有日常需求，且每一处都是高爆炸半径，
  少开一个面就少一个面。要做手机端仍走浏览器。

### 120.6 验证

- 新增 `tests/test_api_mobile.py` 23 条：未登录 401（含「必须是 JSON 而非 302」断言）、
  普通用户 403 覆盖 8 个只读端点、提权字段被丢弃、缺 CSRF 被拦、
  发文→编辑→发布→撤回→软删→还原全链路、定时时间的北京↔UTC 换算、
  访客日志九档与「已拉黑」标记、拉黑需超管 + 非法 IP 400 + 解封幂等、
  友链通过落 `FriendLink` 而拒绝不落、上传拒绝伪装成 `.png` 的 HTML、首屏计数与表内实数一致。
- 抽出核心这一步由**既有**测试背书：`test_admin_posts_characterization.py`、
  `test_edit_post_history.py`、`test_admin_explicit_imports.py`（LOAD_GLOBAL 解析域守卫）、
  `test_no_module_import_cycles.py`（`api/mobile.py` 对 `admin` 的引用全在函数内，
  模块级 import 图零 SCC 不破）行为不变即通过。
- 模板改动由 `test_admin_table_data_label.py` 背书（访客日志表转 `.admin-table` 后，
  漏标 `data-label` 即红）。
- `ruff check .` 全仓 0 error；`tools/lint_debt.py` 棘轮**只降不升**
  （BLE001 248→243、S110 64→60、SIM 28→27、F401 114→114）。

---

## R121 · v4.3.1（R120.5 残留项落地：访客日志与封禁清单升为超管专属 · CWE-200）

### 121.1 触发点：R120.5 自己留下的那条口子

R120.5 写着「权限与后台页面同级、没有放宽，但出口从『一个页面』变成『一个可批量导出的
JSON 接口』……若日后要收紧，最小改动是把该端点升到 `super_only`」，并把不收紧的理由记成
「非超管管理员会在 App 里看不到后台看得见的东西」。**那句话把「可见性等价」当成了「可达性等价」**：

- 页面形态下，管理员要 IP 得**一页一页翻**（`_PER_PAGE = 50`，人眼逐条读）；
- 接口形态下，同一权限变成 `?page=1..N` **顺序抓完整表**，且 `per_page` 上限 100。

输出的正是 `VisitLog.ip` 逐条与当前生效的封禁 IP 清单，属**个人信息批量导出**面（CWE-200）。
本轮判定为缺陷而非可接受风险，理由不是「管理员不该看」，而是**「管理员需要看的东西」与
「管理员可以整表拖走的东西」不应该是同一个开关**。

### 121.2 改动（两个端点，一个参数各一行）

`api/mobile.py::mobile_visit_logs` 与 `mobile_blocked` 的 `_role(admin=True)` →
`_role(super_only=True)`。`/admin/visit-logs` **页面行为不变**（仍是 `admin_required`）。

### 121.3 为什么 `/blocked` 必须跟着升

拉黑与解封自 v4.2.0 起就是 `super_required`。清单可见而操作不可用，会造成
「看到了却没法核对处理」的半途权限；而**「能决定封谁的人，才应该拿到那份 IP 清单」**
本来就是更干净的不变式。两个端点同表同源（都从 `BotBlock` / `VisitLog` 取 IP），只升一个
等于把界线画在数据中间。

### 121.4 刻意没跟着升的，以及界线画在哪（这条比改动本身重要）

`/api/mobile/comments` 的序列化里也有 `ip` 字段，**没有**升超管。三条理由：

1. 后台评论页（`admin/comments.html` 的「IP」列）本就把它展示给 `admin_required`，
   这条不是我新增的出口，动它等于改后台既有权限语义，超出本版范围；
2. 评论是**人为产生**的数据，量级比访问日志小两个数量级（访问日志是每一次页面命中一行）；
3. 评论审核是管理员的日常动作，升上去会把活挡在门外 —— 与 121.1 的目的相反。

界线因此明确为：**「逐次访问的原始日志表」按超管走，「人为产生的内容」维持后台原有等级**。
将来若给 App 加「搜索日志 / 订阅者邮箱 / 留言墙 IP」这类**机器产生的明细表**端点，
按这条界线默认 `super_only`，除非有管理员日常必需的理由，并把理由写进本节。

### 121.5 验证

- 新增 `tests/test_api_mobile.py::test_访客日志与封禁清单仅超管可读`，**同时**断言两侧：
  非超管管理员对这两个端点 `403`，且仍能读 `/comments`、`/stats`、`/overview`、`/trash`
  （只断言"被挡住"的测试会诱导后人收得过宽，这里把"不该挡的没被挡"一起钉住）。
- 反向保护：若有人把这两个端点改回 `admin=True`，该用例立刻红。
- 全量 pytest / ruff / `tools/lint_debt.py` 棘轮对照见 CHANGELOG v4.3.1。

---

## R122 · v4.4.0（移动端「内容全套」的设计期审计 · 新增 36 个端点 · CWE-200 / CWE-79 / CWE-22）

v4.3.0 的 R120 审的是「后台能力开成 JSON」这一件事本身；v4.4.0 把**公告、留言墙、订阅者、
分类·标签·系列、友链本体、文章版本历史、媒体库**也开成了 JSON。这批端点里第一次出现
**可直接群发的邮箱表**、**访客 IP 与设备串**、**能删掉线上图片的写接口**，所以本轮按
「新增攻击面」重审一遍，并把每条决定写成能被后人推翻的形式。

### 122.1 界线沿用 R121.4，但这次要判的是「人产生的内容」里的 PII

R121.4 画的线是「机器产生的明细表按超管走，人为产生的内容维持后台原有等级」。留言墙属于
「人为产生的内容」，所以列表本身维持 `admin_required`；但它的 `ip` 字段是**机器记录的
访客定位信息**，与评论页那个「管理员日常审核就要看 IP」的列不同用途 —— 留言巡检只需要
「哪来的、什么设备」。故：`region`/`device` 给管理员，`ip` **只在超管响应里出现**
（字段级收口，而不是整个端点升级；管理员仍能完成巡检日常工作）。

同一判据在订阅者表上给出相反形状：`email` 是这份数据**唯一的主键含义**，遮掉它就没法用工，
因此不删字段而是**遮敏**（`su***@dom`），管理员默认遮、超管全量。`total` 不受遮敏影响，
统计口径没被削弱。

### 122.2 一条绝对不下放的字段：`Subscriber.unsub_token`

后台 `/unsubscribe/<token>` 是**免登录**校验的（config.py:104 记着这个设计）。谁拿到 token
谁就能替该订阅者退订，所以它**不以任何形态出现在任何角色的响应里**（连超管也不给：
全量邮箱 + 遮掉的 token 已够联系/导出，token 从来不是运营字段）。

回归把它钉在**原始响应文本**上而不是解析后的 dict：
`assert token not in raw_admin and "unsub_token" not in raw_admin`。解析后逐键检查会漏掉
将来新增的嵌套结构，而整页文本里连字段名都不该出现。

### 122.3 审计日志（`AuditLog.detail`）不写 PII

`detail` 是 `String(300)` 的长期留存字段，删掉一条留言不应该顺带在审计里留下第二条
可定位到人的记录。规则：**公告/留言只记内容前 60 字**（内容本来就是公开或半公开的），
**订阅者只记 `#id`**，**友链/分类/系列只记名称**。IP、设备串、完整邮箱一律不进。
验证：`test_留言_ip_只给超管_删除是硬删且不留档` 直接读 `AuditLog` 行断言 IP 不在 detail 里。

### 122.4 幂等：状态类写接口不收「翻转」，缺字段不收「False」

两条同源的静默改数据风险：

1. 后台网页的 `…/toggle` 是翻转语义，照搬到手机上，弱网重发会让状态**来回横跳**
   （用户以为停用了，实际又启用）。移动端一律改成显式目标值 `{active: true|false}`，
   与 `/mobile/post/<id>/pin` 同形。网页端**保留**翻转 —— 那里按钮写着「停用/启用」，
   翻转才是直觉（`admin/misc.py::toggle_announcement` 的注释记着这个分叉）。
2. `form_flag` 对缺键返回 `False`。这对整单表单是对的（没勾就是没勾），用在
   「改单个状态」上就变成**客户端漏传字段 → 服务端静默停用**。新增 `_need_flag()`：
   键缺失返回 `None`，视图报 400。

顺带把整单语义写进契约并在测试里钉住：`PUT /mobile/announcement/<id>` 不带 `active`
会被落成 `False`（与 `update_post_core` 的「缺省即清空」同规则），客户端必须先 GET 详情
再回传全量。这条不是缺陷，是**必须被看见的表单语义**。

### 122.5 破坏性操作：可逆性必须写进响应，不能只写在文档里

后台原有行为里，这几类删除都是**硬删除**（`RecycleBin` 只登记文章）：留言、订阅者、
公告、友链、上传文件。手机上误触成本比电脑高，所以：

- 端点文档与响应里明确「不进回收站」，App 侧据此做二次确认文案；
- **媒体文件**额外一层：被文章引用时返回 `409 + 引用清单 + need_force`，必须再发一次
  `{"force": true}` 才真删。这是本模块唯一用 409 表达「请先确认」的接口 ——
  删图不会进回收站，而文章里的 `![](/static/uploads/x.png)` 会当场图裂。

`media_refs_for` 的判据是**字符串包含**（封面 URL 含整名 / 正文含去时间戳的裸文件名），
刻意「宁可多报」：多报只多一次确认，漏报就是删完才发现图裂。代价（O(文件数×文章数)）
写在 `collect_media` 的 docstring 里而不是藏在调用方。

### 122.6 友链 `url`：伪协议挡在核心层，不靠 UI（CWE-79 预防）

前台把 `FriendLink.url` 直接当 `href` 用。`javascript:` / `data:` / `file:` / `mailto:`
以及站内相对路径一旦进库，就是一个可点击执行的链接 —— 而写它的入口现在多了一个
（移动端 JSON）。归一与拒绝全在 `normalize_link_url`（SSR 与 JSON 共用），因此
「UI 没做校验」不再是可利用的前提：

- 无协议的光秃域名补 `https://`（用户习惯只写域名）；
- 第一个 `/` 之前出现 `:` 即判为伪协议拒收；以 `/` 或 `\` 开头判为站内路径拒收。

同 URL 查重也在这次统一到 `save_friend_link_core`：后台新增原先**不查重**，而审核友链申请
那条路早就查了 —— 两个入口两套口径，重复行会在前台友链区出现两次。

### 122.7 媒体库删除的路径防护（CWE-22）与实测

`delete_media_core` 的五道：① `basename` 剥掉一切目录成分 ② 拒空串与 `.`/`..`
③ 绝对路径必须落在 uploads **那一层内** ④ 必须是普通文件 ⑤ 才敢 `os.remove`。
新增的 JSON 入口不重做校验，只调它，并在视图里**再 basename 一次**（引用查询也要用
同一个归一后的名字，否则「查的是 A、删的是 B」）。

实测：`{"name": "../config.py", "force": true}` → `404 文件不存在`，
而 `myblog/config.py` 仍在原处（`test_媒体库删除需_force_且路径穿越无效` 断言的是靶子文件
没被删，而不是只断言状态码）。

### 122.8 改名换 slug：不是漏洞，是会被误当成「安全」的数据一致性风险

分类/系列改名**沿用后台既有行为** —— 无条件重算 slug。本站**没有 slug 别名表、没有 301**，
所以改名等于让此前发出去（可能已被搜索引擎收录、被别的博客引用）的链接 404。

本轮决定不是改判据（那会牵动前台与既有数据），而是**把结果如实回传**：
`rename_*_core` 返回 `(错误文案, note)`，`note` 写明「地址已由 X 改为 Y，旧链接会失效」，
由两端界面在提交**之前**显示。审计里同样记下 `旧 slug → 新 slug`，出事时能对回时间线。

### 122.9 本轮修掉的两个既有实现问题

- `collect_media` 原先把引用列表截断到 6 条**之后**才取 `len()` 当 `ref_total`，那个数
  永远不超过 6 —— 是个「看起来像总数」的假数。删除确认如果依赖它，会低估影响面。
- 标签用量原先逐行 `len(t.posts)`：`Tag.posts` 是 secondary 反查、默认 `lazy="select"`，
  等于把每个标签下的全部文章对象读进内存（几十个标签就是几十次全量加载）。
  现在后台标签页与 `/mobile/tags` 共用 `tag_usage_counts()` 一条 GROUP BY。
  ⚠️ 顺带记一个坑：`tag.posts.count()` 会抛 `list.count() takes exactly one argument`
  （500 而不是 400），只有 `Category.posts`（`lazy="dynamic"`）才能 `.count()`。

### 122.10 限流与批量抓取

写接口全部按客户端 IP 限流（`_limit`，键前缀 `api_mobile_`）：公告/友链/分类/订阅 20 次每分钟，
标签一键整理 5 次，友链重排 10 次，留言批量标已读 10 次。只读端点沿用既有分页上限
（`per_page` ≤ 100）。**订阅者列表是这次唯一带「整表可抓」性质的端点**，因此它的缓解手段
放在字段层（遮敏 + 不给 token）而不是把端点锁成超管 —— 管理员需要知道「订阅涨没涨、
有没有退订异常」，这需要计数与状态，不需要完整地址簿。若将来加导出功能，必须另开
超管专属端点并写审计，而不是把 `/mobile/subscribers` 的 `per_page` 上限调高。

### 122.11 残留风险（未在本次处理，按现状接受）

1. **引用判定仍是字符串包含**：改名/复制正文里的图片路径会让 `refs` 误报或漏报，
   它只用于「提醒」，不构成删除的安全保证。真要精确，需要正文图片引用入库（表结构变更）。
2. **转 WebP/AVIF 生成的同名旁路文件不会连带删除**（`delete_media_core` 只删点名的文件），
   孤儿 `.avif` 会留在 uploads 里。需要的是另一条维护接口，不属于本次范围。
3. **公告正文仍是 Markdown 原文回传**：渲染清洗在请求时由前台做，因此 App 里看到的
   与前台可能不同（例如未清洗的原始标记）。这是**编辑器的正确行为**，但意味着
   App 不能把 `content` 直接 `WebView.loadHtml` 当预览。
4. **媒体库全量扫描的耗时**随上传目录与文章数增长（见 122.5）。目前没有缓存，
   真到不可接受的量级时应改为「按文件名反查引用索引」。

---

## R123 · v4.4.1（「全站体检」备份检测假阴性 · 可观测性缺陷修复）

> **性质**：不是漏洞，是**可观测性缺陷** —— 监控项报「未找到备份文件」，
> 而生产实际存在 **178 个备份文件**（`data/backup` 141 + `backups` 37），
> 云端 WebDAV 也已正确配置。本轮由用户报障发现。

### 123.1 为什么「假监控」比「没有监控」更糟

没有监控时，人至少知道「这里我没看着」；**监控误报会训练人忽略它**。
本项的具体危害不是"卡片不好看"，而是**可恢复性判断失真**：
一旦真发生数据丢失，运维看体检会以为"本来就没备份可用"，从而跳过
"先找备份再抢救"这一步 —— 把一个**告警**变成了**误导**。

同类教训在本项目出现过两次：v3.18.9 的 `site_url` 取不到时回落
`socket.gethostname()`（"碰巧准确"→ 多 server 块时静默失灵）、
以及 v3.25.3 证书监控的"假 ok"。**凡是监控项，第一问都是"它凭什么说 ok/不 ok"。**

### 123.2 根因：体检猜了一条恒不存在的路径，且三处都错

备份实际有**三处写入方**，而 `check_backup()` 只猜其中一条，且那条三重错误：

| 错误 | 实际情况 |
|---|---|
| 目录名 `data/backups`（复数） | 实际 `data/backup`（**单数**，`update.sh:714` 用的） |
| 从不查 `BACKUP_ROOT` | 定时任务真正落盘处，服务器上是**站点上级**的 `backups/` |
| `REPO_ROOT/myblog/data/…` | 线上代码（v3.18.6 起）直接铺在站点根，**没有 `myblog/` 这层** |

第三条与 v4.2.0 发版时踩的是同一个坑（核验线上代码路径多套一层 `myblog/`）。

### 123.3 修法与一条设计原则

新增 `_backup_search_dirs()`，按**真实写入方**枚举候选目录（后台配置 /
`BACKUP_DIR` / `backup.BACKUP_ROOT` / `<代码同级>/data/backup`），
跨全部目录取 mtime 最新者，并**标注来源**。

🔑 **定时任务那条直接取 `backup.BACKUP_ROOT`，不自己重算路径规则** ——
重算等于把写入方的规则抄一份，**抄错就是本 bug 本身**。
（同源于 v4.2.0 发版时"自己复刻双源互证算法连错三处"的教训。）

顺带把「配置了却不存在」显式列为 `目录缺失` + warn：那是**配了没生效**，
静默忽略等于把坏配置藏起来。

### 123.4 验证

- `tests/test_diagnostics_backup_v441.py` 6 条，含一条**反向守卫**
  （目录存在但无备份文件时必须**仍报**「未找到」，防止修复把体检修成永远说 ok 的假体检）。
- **变异验证**：摘掉「查 `BACKUP_ROOT`」与「查部署目录」两处（= 旧逻辑）→
  **3 条立刻变红**；还原后 6 条全过。
- ⚠️ 用例全部包在 `app.app_context()` 内：`read_setting_db()` 脱离上下文会
  **直连真实库** `myblog/data/blog.db`（不是"读不到"，是**读错库**）。

---

## R124 · v4.4.2（后台游戏审计「结论与安全状态脱钩」· CWE-693 保护机制失效）

> **性质**：保护机制失效（Protection Mechanism Failure）。游戏审计链路本身
> 一直「在跑」，但**结论不参与任何决策**，且审计输入被截掉 75%——
> 表现为「有审计」，实际是「没审」。用户报障发现。

### 124.1 判据：审计输入覆盖率必须是「看得见」的

本轮的核心不是"漏洞有多严重"，而是**一条通用判据**：

> 🔑 **凡是「监控/审计类」机制，第一问都是「它凭什么说通过」。
> 拿不出依据时，默认按「没通过」处理。**

游戏审计有三条链路：静态扫描（辅助）、LLM 审计（主判据）、沙箱（浏览器侧隔离）。
本轮只有沙箱是真隔离，前两条都失效：

| 环节 | 名义作用 | 实际 |
|---|---|---|
| `_sample_code` | 提供完整源码给 LLM | 每文件硬砍 3000 字符，丢 62~75% |
| 静态扫描 | 启发式发现可疑特征 | 只写 `audit_summary`，与放行无关 |
| LLM 审计 | 给出 safe/risk 判定 | **verdict 从未被解析**，原文入库即丢 |
| 沙箱 | 真隔离 | 唯一真防线（浏览器侧，不在本轮范围） |

### 124.2 最好的证据：审计结论自己举报了截断

线上 `dino-run` 的 LLM 审计结论原文（v4.4.2 之前的生产数据）：

> `game.js 源码在末尾处被截断，无法完全确认后续代码，但已可见部分无网络请求…`
> `"verdict":"safe"`

LLM **明确告知**自己只看到残片，系统却把 `safe` 当作可信结论入库。
这说明**收审方的告警信号存在，但接收端没有对账逻辑**。

🔑 **通用教训**：任何自动化判定的「上游告警」，如果下游不消费，
就等于把告警丢弃。与 v4.4.1「体检报备份不存在」同源——
**都是"有输出但输出没被消费"**，只是方向相反（那次是漏报，这次是吞警）。

### 124.3 截断为什么比不截断更危险

直觉上"截取部分代码总比不审计好"。实际上：

- 恶意代码放在第 3001 行之后 → LLM 报 safe → 上架 → **逃逸**；
- 若显式标注覆盖率 → LLM 只能报 unknown → 触发确认 → **人被拉进来看**。

即截断本身不致命，**「截断了却不让下游知道」才致命**。
修复因此包含一条与算法同等重要的改动：文首注入【覆盖率声明】+ prompt 里
明确要求「无法排除风险时 verdict 必须给 unknown 而非 safe」。

### 124.4 失败必须落库：枚举每条早退路径

首版修复只把外部调用包进 `except`，被自己的测试抓出漏了「配置不完整」这条
早退 `return` —— 该出口同样不写库，于是页面继续显示旧 `safe`。

🔑 **「失败要落库」不等于「在 except 里落库」**：任何 `return False, ...`
形式的早退都是失败出口，必须逐条枚举。本项目已三次同型踩坑
（本次 R124、v4.4.1 体检假阴性、v3.25.3 证书「假 ok」）。

同轮还修掉一个**把自己坑了**的实现 bug：写时间戳用了 `datetime.now()`，
而项目有 `myblog/_time.py` 与标准库 `datetime` 同名，`import datetime`
拿到的是封装模块（只有 `utcnow`），抛的 `AttributeError` 又被外层
`except Exception` 吞掉、**伪装成「审计失败」**——第一版修复整条写库路径
静默失效。已改用 `utcnow()`。

> 🔑 由此得一条**降级路径的纪律**：`except Exception` + 「写入失败也降级」
> 的组合会把**代码自身的 bug** 伪装成**上游服务故障**，极难定位。
> 本项目 BLE001 棘轮把这类裸捕逐步消除，正是为收敛这条风险面。

### 124.5 审计与放行的耦合：确认而非硬拦

判 `risk` / 未审计 / `unknown` 时要求二次确认，风险摘要与「站长确认放行」
写入 `admin_note` + `log_audit`。

选择确认页而非服务端硬拦，依据是本项目定位：**纯个人站点，没有内容审核岗**，
硬拦会把"我就是要上这个包"的正常运营也堵死。但"不硬拦"不等于"放行不留痕"。

🔑 **反向守卫同样重要**：判 `safe` 时必须直接放行（否则确认页退化为噪音，
最终会被整体关掉，安全措施因「总是吵」而被弃用）。

### 124.6 验证

- `tests/test_games_audit_v442.py` **22 条**，含两条反向守卫
  （`safe` 必须直接放行 / 老格式结论必须判 `unknown` 而非 safe）。
- **变异 4 组全红**：恢复每文件硬砍 3000 / 去掉 verdict 解析 /
  去掉「配置不完整」出口落库 / 去掉放行二次确认闸门；恢复后全绿。
- 修复后实测覆盖率：`dino-run` 4162 → **13409 字符（全量）**，
  `star-eater` 11880 字符（全量）。

---

## R125 · v4.5.0（阅读时长与首页壁纸 · CWE-20 输入校验失效）

本轮新增两条数据通路：① 客户端上报的**阅读时长**；② 后台可配置的**壁纸 URL**。
两者都引入了「服务端必须假设客户端不可信 / 配置值可能指向站外」的新攻击面。

### 125.1 🔴 客户端上报的 duration 未钳制 → 可任意篡改统计指标

`/api/stats/read` 新增 `duration`（秒），直接决定后台展示的「平均阅读时长」。
**客户端上报值完全可控**：一个 `{"slug":"x","duration":999999}` 的匿名请求，
就能把全站平均值抬到任意值 —— 且该端点无需登录。

修法：`_clamp_read_seconds()` 统一钳制到 `[0, 7200]` 秒，非法类型一律当 0。
7200 秒（2 小时）作为上限，是因为超过该值基本是客户端时钟异常或页面被挂起整夜。

### 125.2 🔴 停留时长复用计数入口 → read_count 被虚高

停留时长在切后台、跳下一篇文章时会**多次补报**。若复用 `/api/stats/read` 这一
计数入口累加，读者读一次会被记成两三次，**热门文章榜与「反复阅读」榜双双虚高** ——
而这两个榜是站点运营的真实依据。

修法：新增 `add_read_duration()`，**只累加 duration，绝不触碰 read_count**；
API 侧用 `only_duration` 开关分流。同时补上守卫测试（单元级 + 端到端级各一条）。
⚠️ 记录不存在时**不凭空造行** —— 时长必须挂在一次真实阅读上，否则
`SUM(duration)/SUM(read_count)` 的分母会多出没有阅读的时长。

### 125.3 🔴 壁纸 URL 若不限来源 = 让访客浏览器替站主向第三方发请求

壁纸 URL 最终进入 inline style 的 `background-image`。若允许任意外部 URL，
站主（或被盗的超管会话）就能让**每个访客的浏览器**向第三方发起请求 ——
读者的 IP 与 UA 就此泄漏；`data:` 前缀还能把任意内容塞进样式。

修法：`_safe_wp_url()` 只接受本站 `/static/uploads/` 下的相对路径。

### 125.4 🔴 只判 startswith 挡不住路径穿越

`_safe_wp_url()` 第一版仅 `startswith("/static/uploads/")`，**被自写测试当场证伪**：
`/static/uploads/../../config.py` 同样以该前缀开头，浏览器再把 `..` 规范化掉，
请求就打到 `/static/config.py`。

修法：额外拒绝 `..` / `?` / `#` / `\`。
> 一般化：**「前缀白名单」不构成路径校验**，凡是用户可控且会拼进 URL 的值，
> 必须显式拒绝 `..`。

### 125.5 ✅ 其余维度逐条核对

| 维度 | 结论 |
|---|---|
| XSS | 壁纸 URL 经后端白名单 + 前端 `JSON.stringify` 转义后再进 CSS 声明，不裸拼；统计页为纯文本插值 |
| SQL 注入 | 本轮新增查询全部走 ORM 参数化（`func.sum` / `filter`），无字符串拼接 |
| 越权 | `/api/theme` 的 wallpaper 分支沿用 `is_super` 校验，未放宽（测试断言未登录 401/403） |
| CSRF | `POST /api/theme` 走全局校验；壁纸上传复用既有 `/admin/upload`（同样受保护） |
| 密钥 | 本轮无凭据、无环境变量 |
| 资源泄漏 | 未新增文件句柄 / subprocess / 连接 |
| 限流 | `/api/stats/read` 沿用既有 60 次/分钟；补报走同端点同样受限流约束 |
| 可见性 | 未新增公开文章读取面；`/api/site` 新增的 `wallpaper` 字段不含任何用户数据 |

### 125.6 ⚠️ 已知限制（非缺陷，写明口径）

- **阅读时长只有全站口径**：`read_log` 无日期列，区间维度需要另建按日汇总表。
  模板标签已写明「全站」，避免被误读成区间数据。
- **升级前历史数据不计入均值**：`duration` 默认 0，统计时按 `duration > 0` 过滤，
  故刚升级时该指标偏低甚至显示「—」，需积累新数据。

### 125.7 验证

- 新增测试 **28 条**：`test_region_exclude_bot.py`（5）、
  `test_read_duration.py`（10）、`test_wallpaper.py`（13）。
- **反向守卫齐备**：只有正向用例时，「永远返回空列表」也能全绿。故含
  「不传 `human_only` 时爬虫属地**会**出现」「热门页面榜**不**排除爬虫」
  「不传 CSRF 被拒」「拼错 `pack_id` 仍 400」四条。
- **变异 4 组全红**：`_top_region` 的 `is_bot` 取反 / `_range_top` 的 `human_only`
  取反 / 均值分母改 `COUNT(*)` / 补报时长误加 `read_count`。
- 全量 **902 passed**，ruff 全仓通过，lint 棘轮 F401 回落基线 116。
- 表结构变更：`read_log` 加 `duration`（迁移 `a7e3c92d5b18`）；壁纸为 Setting KV，零表变更。

## 126. v4.6.0 首页首屏铺满整屏（纯前端）

### 126.1 范围

改动文件仅 2 个：`vue-frontend/src/styles/global.css`、`vue-frontend/src/views/HomeView.vue`。
**无表结构变更、无后端代码改动、无新依赖、无新路由、无新环境变量。**

### 126.2 逐项审计

| 维度 | 结论 |
|---|---|
| XSS | 无新增 HTML 注入面。唯一的动态 CSS 值是 `--wall-veil-top`，由 `veilOpacity`（`Math.min(0.8, Math.max(0, Number(...)))`）经 `toFixed(3)` 生成，**只可能是纯数字**。壁纸 URL 仍走 v4.5.0 已有的 `JSON.stringify()` 转义 |
| SQL 注入 | 不适用（无后端改动） |
| 越权 | 不适用（无新路由） |
| SSRF | 不适用（壁纸 URL 仍由后端 `_safe_wp_url` 限定本站 `/static/uploads/`，前端未放宽） |
| CSRF | 不适用（无新请求） |
| 密钥 | 本轮无凭据、无环境变量 |
| 资源泄漏 | 新增的 `IntersectionObserver` 在 `onBeforeUnmount` 中 `disconnect()`；写进 `:root` 的 `--wall-veil-top` 同步 `removeProperty()`，不残留全局污染 |
| 限流 | 不适用（无新接口） |

### 126.3 自查发现并修复的缺陷

**CSS 自定义属性只向下继承，兄弟节点拿不到。**

顶栏浮到壁纸上之后，它不在 `.home-cover` 的 `background-image` 里，拿不到那层遮罩，
白字会直接压在亮色壁面上。补顶部渐变的第一次实现把 `--wall-veil-top` 放进 `coverStyle`（inline style
打在 `.home-cover` 上），而 `.site-header` 是它的**兄弟节点**，继承链到不了 —— 
永远只会命中 fallback 常量，**「遮罩滑块联动」是假的**。

改为挂在 `:root`，并在 `onBeforeUnmount` 里 `removeProperty()`。

> 一般规律：**给 CSS 变量找消费者时，先确认它在 DOM 里的位置关系**。
> 写在兄弟节点上的变量不会"流过去"；这类错误不会报错、不会红测，
> 只会让某个 CSS 值静默退回默认值 —— 与「审计报告有 PoC ≠ 结论成立」是同一类陷阱。

### 126.4 已知限制（非缺陷）

- **`background-attachment: fixed` 仅在桌面 ≥641px 开启**：移动端滚动时每帧重绘大图，
  代价高收益低；iOS Safari 对 fixed 背景另有支持缺陷，用 `@supports (-webkit-touch-callout: none)`
  单独回退（Butterfly 主题用 `.apple` 类做的是同一件事）。
- **CSS `:has()` 依赖**：Chrome 105+ / Safari 15.4+ / Firefox 121+。更旧的浏览器
  仅表现为顶栏不浮起来，壁纸仍满屏，无功能损失。

### 126.5 验证

- `vite build` 通过（13s，无报错）；产物逐项 grep 确认：
  `HomeView-*.js` 含 `setProperty` / `removeProperty` / `IntersectionObserver` / `is-solid`；
  `index-*.css` 含 `100svh` / `:has(` / `background-attachment` / `wall-veil-top` / `is-solid`。
- 已知全绿陷阱：`grep -c` 逐项计数**必须全部 > 0** —— 任一项为 0 说明改动没进包，
  而 build 本身不会报错（它只认目录存在，见经验 42）。
- 后端零改动，故未新增 Python 测试；全量测试套件结果见 CHANGELOG。

## 127. v4.6.1 修：壁纸被整站外框套住（纯前端）

### 127.1 触发方式与根因

v4.6.0 上线后**用户实际看到的效果是错的**（「壁纸没占满整、还被一个框套住」）。
根因不是首屏高度算错，而是**漏掉了外层容器**：`.site-frame`（v3.1.0 整站大框）是
`max-width:1100px + margin:22px auto 28px + padding:0 16px + border + radius + overflow:hidden`，
首页内容在它里面。只改内层 `.home-cover` 的高度，不动外层，壁纸必然被挤窄、被裁角、顶部留白。

> **一般规律：改「某元素铺满视口」时，必须先确认它的**所有祖先**是否有限宽 / 外边距 / 圆角 / overflow。
> 漏一层，视觉上就是「没生效」，而代码与构建都全绿。

### 127.2 逐项审计

| 维度 | 结论 |
|---|---|
| XSS | 无新增注入面。改动全为静态 CSS 与既有 CSS 变量的算术（`Math.max`） |
| SQL 注入 / 越权 / CSRF | 不适用（无后端改动、无新路由） |
| SSRF | 不适用（壁纸 URL 仍由 `_safe_wp_url` 限定本站 `/static/uploads/`） |
| 密钥 | 本轮无凭据、无环境变量 |
| 资源泄漏 | 无新增监听器/观察器（本版未动 IntersectionObserver） |
| 回归面 | 破框规则全部由 `:root:has(.home-cover.has-wall)` 把关，**未配壁纸时不命中**。已实测非首页（文章页）不受影响 |

### 127.3 本版的验证方式改进（重要）

前几版的视觉改动只做了「构建通过 + 产物 grep」，**这次证明那不够** —— 用户看到的是错的。
本版改用 `playwright-cli` 对**线上真实页面**取证：

1. 先截修复前线上图，复现了「框 / 顶部白边 / 遮罩过重」三个现象；
2. 用 `page.evaluate` 把修复 CSS **注入线上页面**（不改动线上文件），截图验证；
3. 覆盖桌面 1440×900、移动 390×844、滚动后 `.is-solid`、遮罩 0.15 四种状态；
4. 确认无误后才发版。

> 🔑 **有浏览器可用时，视觉改动必须以真实截图为准**。「代码写了」「构建过了」
> 与「用户看到的是对的」之间隔着祖先容器、对比度、真实数据这三层。

### 127.4 已知限制（非缺陷）

- **遮罩强度与壁纸亮度强相关**：实测一张高亮度草地壁纸在 overlay 0.15 下标题
  仍偏浅。当前默认 0.35 对亮色壁纸是合理值，进一步调低需改用深色壁纸或接受文字变淡。

### 127.5 验证

- 全量 **902 passed**；`vite build` 通过。
- 产物逐项 grep：`HomeView-*.js` 含 `home-page`；`index-*.css` 含 `home-page` / `100svh` / `:has(` / `is-solid`。
- 表结构变更：无。依赖变更：无。

## 128. v4.7.0 首页瘦身 / 开站时间 / 顶栏瘦身 / 后台表格换行

### 128.1 范围

前端 5 个文件 + 后端 3 个文件。**无表结构变更**（`site_since` 存 Setting KV）、无新依赖。

### 128.2 逐项审计

| 维度 | 结论 |
|---|---|
| XSS | 新增的 `site_since` 只经 `_valid_since` 白名单校验（`^\d{4}-\d{2}-\d{2}$` **且** `datetime.date()` 能构造），非法值后台保存时**保留旧值**并 flash 提示，不入库。前台渲染为文本，无 `v-html` |
| 输出编码 | 开站日期只可能是数字与短横，即使混入也只会显示为文本，不构成注入面 |
| SSRF / 越权 / SQL 注入 | 不适用（无新路由、无新查询；`site_since` 回退查询走既有 `visible_posts_query()`） |
| CSRF | `/admin/settings` 是既有表单，新增字段走同一 POST，未新增端点 |
| 密钥 | 无凭据、无环境变量 |
| 资源泄漏 | 无新增监听器（`IntersectionObserver` 本版未动） |
| 可见性 | 回退查询用 `visible_posts_query()` 而非 `Post.query` —— **不可见草稿时间更早**，用它会把开站日期算早 |

### 128.3 测试门禁抓到的两处（本版自查）

1. **我把 `site-entry-link` 用在了站内 `router-link` 上** —— 该类语义是「外域链接」
   （必带 `target=_blank` + `rel="noopener"`），`test_nav_entries_v4_1` 与
   `test_site_entry_v4` 同时拦下。已拆成两类：站内用 `.more-link`，
   外站保持 `.site-entry-link`，并**恢复独立的「🧰 工具箱」下拉**（不做合并）。
2. **CHANGELOG 体积守卫**：追加本轮四条长条目后涨到 201 KB > 上限 200 KB。
   按项目既定规则搬走最老的一批（v3.18.6 ~ v3.19.2 → `docs/archive/`），
   **而不是压缩本轮新写的条目**，并按惯例在 `test_doc_archival.PAIRS` 追加一条。

### 128.4 已知限制（非缺陷）

- **开站时间的回退值是近似值**：第一篇文章未必等于建站日。后台留了手工覆盖入口。
- **`/annual` 未删除**：`/stats` 的年度回顾区块未搬访客地图（需额外加载 `china.json` 与
  `/api/geo/visitors`，单次请求明显更重），故该路由保留可直达，区块底部给了入口。
- **顶栏断点**：≤1280px 走汉堡菜单（英文长度问题只存在于桌面顶栏）。

### 128.5 验证

- 全量 **902 passed**；`vite build` 通过。
- 产物 grep：`HomeView` 中 `bento` / `home-social` 已归零、`hcs-item`（首屏图标）与
  `social-accounts` 仍在；`StatsView` 含 `site_since` / `review/annual` / `ov-grid`；
  入口 chunk 中 `/annual` 由 3 处降到 2 处（**顶栏已移除**，抽屉与路由表保留）。
- **真实浏览器验证**（`vite dev` + proxy 到线上 API + `playwright-cli` 截图）：
  首页无六卡无社交墙、统计页站点概览与年度回顾均正确渲染、
  **英文 1440px 顶栏无溢出且右侧仍有余量**。

## 129. v4.7.1 修「⋯ 更多」下拉无法使用（纯前端）

### 129.1 范围

改动文件仅 `vue-frontend/src/App.vue` + `global.css`。无表结构变更、无后端改动。

### 129.2 逐项审计

| 维度 | 结论 |
|---|---|
| XSS | 无新增 HTML/属性绑定；链接仍走结构化 `:href` + `:to`，未用 `v-html` |
| SQL 注入 / 越权 / CSRF / SSRF | 不适用（无新端点、无新查询） |
| 密钥 | 无 |
| 无障碍 | 补 `@keydown.esc` 关闭：开关改成幂等「确保打开」后，纯 hover 场景下键盘用户无法关掉菜单 |
| 回归面 | 「🧰 工具箱」下拉**同源同病**（共用 `.toolbox-menu` 与同样的 mouseleave 写法），本次一并修复与验证 |

### 129.3 本版的方法论收获（重要）

**静态截图证明不了「鼠标移过去」这一步。** 本版连续三次靠真实指针路径（`playwright run-code`
` 的 `mouse.move` + `boundingBox`）才发现问题：

1. 用户报障的「一碰就关」—— 静态截图里菜单是正常打开的；
2. 我加 `@mouseenter` 后引入的「点击又关掉」—— 同样是鼠标路径才暴露；
3. 下拉白字压浅底—— 这个**静态截图就能看出**，说明截图不能省。

> 🔑 **交互缺陷必须用指针路径验，不能用截图验。** 两类验证各有其位：
> 截图验「长什么样」，指针路径验「动起来对不对」。

### 129.4 关键根因：mouseleave 不可逆

`mouseleave` 与 `mouseenter` 不成对 —— 离开后**不会**因为再次进入容器而重新触发

`mouseenter`。所以只要有一条指针路径误触发了离开（比如穿过容器与绝对定位

子菜单之间的空隙），菜单就永久关闭，用户只能刷新页面。

修复不能只加 `mouseenter`（那是第二条打开路径），还要保证**不存在误触发的路径**：

这里是把 `margin` 归零、让容器与菜单在几何上连续，才是治本。

### 129.5 验证

- 全量测试通过；`vite build` 通过。
- playwright 指针路径实测（见 CHANGELOG 129.5 的三行输出）。

## 130. v4.7.2 修：壁纸模式下顶栏按钮深色难辨（纯 CSS）

### 130.1 范围

改动仅 `vue-frontend/src/styles/global.css`（+ 文档与版本号）。无表结构/后端/依赖变更。

### 130.2 根因

v4.7.1 把壁纸白字规则从 `nav a` 收窄为 `nav > a`（避免误染下拉浮层内的浅色卡片链接），
**但按元素类型漏改了**：顶栏「⋯ 更多」「🧰 工具箱」是 `<button class="site-toolbox-toggle">`，
不匹配 `> a`，于是被收窄动作一并漏掉，保持深色压在亮色壁纸上。

> 一般规律：**收窄 CSS 选择器时，要先枚举被排除的元素类型里有没有「本该被覆盖」的**。
> 收窄解决的是「误伤」，代价可能是「漏盖」——两者必须一起数。

### 130.3 审计

| 维度 | 结论 |
|---|---|
| 变更面 | 纯 CSS 颜色规则，无新增选择器之外的副作用 |
| 回归风险 | 关键是**不能退回宽泛后代选择器**（那会重新引入 v4.7.1 的「白字压浅底」）。本次用 `.site-toolbox-toggle` 精确补，与浮层内的 `.toolbox-menu a` 互不重叠 —— 已由 playwright 实测下拉内链接仍为 `rgb(85,85,85)` 深色 |
| 移动端抽屉 | 抽屉在 `.site-header` 之外，`:has(...).site-header .site-toolbox-toggle` 规则**不会命中**它，抽屉内按钮保持主题本色 —— 无需额外处理 |
| 其他维度 | 无后端改动，不适用 |

### 130.4 验证

- playwright 实测 computed color：壁纸模式 `rgb(255,255,255)` + 暗投影；
  滚过首屏 `.is-solid` 后 `rgb(85,85,85)` 恢复本色；logo 同为白色（视觉一致）。
- 同时确认下拉浮层内链接仍为深色，未回退。
- 全量测试通过。

## 131. v4.7.3 全量审计代码批次（PR #24）

### 131.1 本轮性质

本轮**不新增功能**，是审计清单的代码落地：发布阻塞 + 安全/健壮性 + 文档/测试一致性。
合并 PR #24（`fix/v4.7.3-audit-batch` → `main`），并在其上收口版本号与 CHANGELOG。

### 131.2 逐项审计

| 维度 | 结论 |
|---|---|
| SSRF | **新增统一出站层 `myblog/outbound.py`**：http/https + 域名解析到公网 IP + 禁 URL 凭据 + `NoRedirect` 禁跟随 3xx。管理员级（游戏 LLM Base）与匿名面（`feed_agg`）两处均接入。⚠️ 残余风险见 131.4 |
| zip 炸弹 | `unpack_zip_safely()` 在 `zf.read()` 之前按中央目录 `file_size`/`compress_size` 拒绝超限与压缩比 > 200 —— **先判后读**，避免先解到内存再判 |
| 黑名单 | `check_bot_guard()` 把黑名单提到 `_SKIP_PREFIXES` 之前并注册 `api_bp` 钩子；`/admin/`、`/mcp` 保留豁免（防管理员自锁） |
| 越权 | 移动端撤回改用 `_can_edit_post()`，与桌面端一致（此前仅管理员） |
| 静默失败 | 移动端置顶缺 `pinned` 字段改为返回 400，不再静默取消置顶 |
| 文件覆盖 | 移动端上传文件名改 `time.time_ns()`，消除同秒多文件互相覆盖 |
| N+1 | 移动端列表 `comment_count` 改当前页一次 `GROUP BY` |
| 数据一致性 | 积分事件 `IntegrityError` 冒泡成 500 → `add()` 移入 `try`（autoflush 在 try 外抛出的经典坑） |
| 表结构 | 新增**幂等**迁移 `b8e4f1a72c93`（两个索引），空库与已 `create_all` 库双场景验证不重复创建。部署只走 `flask db upgrade`，**禁 `stamp head`** |
| 依赖 | `vue` 3.5.13→3.5.44、`dompurify` 3.2.4→3.4.17；`npm audit --audit-level=high` 0 vulnerabilities |

### 131.3 一处架构变化（值得记）

**本项目首次有了统一的出站请求安全层**（`myblog/outbound.py`）。此前 `utils/net.py` 只有限流与客户端 IP，
每个出口各自实现（`seo_push.py` / `oauth.py` / `feed_agg.py` 各写一套），口径必然漂移。
本轮把 `feed_agg` 的重复实现删掉（-55 行）并改用 `outbound`，`games.py` 用 `from outbound import ...`。
方向正确 —— 但**统一只做了一半**（见 131.4）。

### 131.4 两处口径未统一 + 一处残余风险（我逐行核对，非照抄 PR 描述）

1. **`feed_agg.py` 仍自己定义 `_NoRedirect`（L65-72）**，未用 `outbound.NoRedirect`。
   `games.py` 已改用统一版，`feed_agg` 未改 —— 两处各留一份，后续改一处就漂移。
2. **`feed_agg._safe_url_fail_reason()`（L128-150）自己又写了一套私网判断**
   （`10.` / `192.168.` / `169.254.` / `172.16-31` 字符串前缀 + `getaddrinfo`），
   与 `outbound` 的「纯 IP global 判据」是两套逻辑（结果近似，但存在漂移空间）。
3. ⚠️ **DNS rebinding 未根治**：`safe_public_url()` 解析 DNS 后只返回 `bool`，调用方 `opener.open(url)`
   时 **urllib 会再解析一次 DNS** —— 两次独立解析之间攻击者可改 DNS 指向内网。
   `feed_agg.py` L58-59 的注释称「不再重复解析 DNS（正是重复解析给了重绑定窗口）」，
   但它消除的是**第三方库那次，urllib 自己那次仍在**。彻底解法是 **IP pinning**
   （预检查解析出 IP，之后直连该 IP，Host 头仍用原域名）。
   威胁模型有限（需先控制 RSS 源域名），本轮不阻塞发版，作为后续收口项。

### 131.5 上线注意事项（本次发版实测）

- `update.sh` 改了 51 行（`BLOG_REBUILD_FTS=1`）→ **不在 `myblog-backend.zip` 内**，
  必须按「脚本类改动必须单独发」在服务器上单独覆盖并对账 sha256。
- 前端 `package.json` / `package-lock.json` 变更 → **必须 `npm ci` 后重新 build**，
  不能沿用旧产物。
- 迁移 head 变更 → 部署后用 `flask db current` 核对为 `b8e4f1a72c93`。

### 131.6 验证

- 全量 **936 passed**；`ruff check .` 全绿；`npm audit --audit-level=high` 0 vulnerabilities。
- 本地合并 PR 后重跑全量测试 + `npm ci` 重新 build + 重新打包（`package.py`），
  并在上传前断言「zip 内 APP_VERSION == tag」与三方哈希互证。

## 132. v4.7.4 出站统一层 + IP pinning / 壁纸引用媒体库

### 132.1 范围

后端 6 个文件（outbound / feed_agg / games / api_ai / seo_push / api_theme / admin_media / admin_theme_center）、
模板 2 个、测试 3 个（含 1 个既有测试适配）。**无表结构变更**、无新依赖、无迁移。

### 132.2 IP pinning —— 根治 DNS rebinding

| 维度 | 结论 |
|---|---|
| 根因 | v4.7.3 的 `safe_public_url()` 解析 DNS 后**只返回 bool**，被校验的 IP 被算完就扔；
调用方 `opener.open(url)` 时 urllib **再解析一次** —— 两次解析之间可被改指内网。
典型 TOCTOU，**重复校验无法消除** |
| 修法 | `resolve_public_ex()` 一次解析同时给出「能否放行」与「用哪个 IP」；`open_url()` 把 IP **固定在连接上**。
TCP 连已验证 IP，HTTP `Host` 与 TLS SNI **仍用原域名**（否则虚拟主机/证书校验失效） |
| 校验与固定的一致性 | ⚠️ 关键：**必须用同一次解析**。若「校验解析一次、连接再解析一次」，
固定的可能是**根本没检查过**的 IP —— 比不修更糟。故 `open_url(pinned_ips=...)` 允许调用方传入已校验的 IP |
| 代理 | ⚠️ **pinning 在走代理时无效**（目标 IP 由代理解析）→ 统一 opener 显式装空 `ProxyHandler({})` 禁掉环境代理 |
| 禁用项 | 统一 opener 恒定装 `NoRedirect`（任何 3xx 不跟随）—— 这是最常见的 SSRF 绕过路径 |
| 判据单一来源 | `_check()` 是唯一实现；`resolve_public` / `check_public_url`（提示语）/ `safe_public_url` 全从它派生，
不会出现「放行一套标准、提示语另一套」 |
| 业务白名单边界 | `seo_push` 的 host 白名单、`games` 的「base 必须公网」是**业务规则**，留在各自模块，不塞进统一层 |

### 132.3 一处刻意的例外（`api/ai.py`）

LLM 摘要的 base 由**管理员自己**配置，很多人指向本机自建（Ollama / vLLM 在 127.0.0.1）。
统一层的私网过滤是给「URL 不可信」的场景用的 —— 套上去会把正当用法打死。
故 `api/ai.py` 只用统一 opener 的**禁 3xx**能力，**不套私网过滤**，并在代码里写明理由。

### 132.4 壁纸引用媒体库 —— 引用生命周期

| 维度 | 结论 |
|---|---|
| 数据模型 | 壁纸本就存**路径引用**，媒体库文件同在 `/static/uploads/` 命名空间 → 零改造即可引用 |
| 入口 | 主题中心「从媒体库选」+ 媒体库页「设为壁纸」（**仅超管** —— `/api/theme` 要求 `is_super`，而媒体库页是管理员可进，权限不同） |
| 引用生命周期 | ⚠️ 媒体库文件**可被删**。新增 `wallpaper_uses()` 判定，`delete_media_core()` 拒绝删除正在当壁纸用的文件 |
| fail-open | 该检查**故意 fail-open**：检查挂了不该让管理员完全删不了文件；误放行的后果只是壁纸裂图（首页退化成纯色底），不是安全问题 |
| 越权 | 「设为壁纸」按钮用 `{% if is_super %}` 条件渲染，权限不一致处不留 403 白板 |

### 132.5 验证

- 全量 **965 passed**（新增 pinning 实测 12 条 + 壁纸引用 16 条）
- **pinning 是实测的**：`getaddrinfo` mock 成「域名被解析第二次就失败」；
  另有 mock 从结果侧证明连的是被 pin 的那个 IP。
- 既有 `test_audit_r114.py` 适配：抓取改走统一层后多了一层私网校验（本地 server 在 127.0.0.1），
  测试里放行本地地址，**断言的意图一字未改**。
- `ruff check .` 全绿；`lint_debt.py` 无新增。

## 133. v4.7.5 生态统计 + 公开在线数

### 133.1 范围

新增 1 张表（`ecosystem_site`，7 列）+ 2 个公开端点 + 1 个设置区 + 2 处前台展示。
**遥测默认关闭**，且上报内容不含任何访客数据。

### 133.2 遥测的信任边界（本功能能否被接受全看这几条）

| 维度 | 结论 |
|---|---|
| 默认状态 | **默认关闭**（`ecosystem_opt_in`）—— 未经告知的遥测会毁掉开源项目信任 |
| 上报内容 | 仅 `site_key`（随机安装 ID）/ `url` / `version` / 时间戳。**绝不含访客数据、文章、账号** |
| 用户可否拒绝 | 可：`ecosystem_listed=0` → 只计数、不公开 URL |
| 中心地址 | 必须过 **SSRF 白名单**（`safe_public_url`）→ 内网/本机地址当场拒绝。否则该设置就是「让服务器请求任意地址」的后门 |
| 数据可信度 | 心跳是**自报**的，任何人都能伪造 → 前台如实标注，不宣称权威 |
| SSRF | 中心端**不验证站点 URL 是否可达**（那是 SSRF）；只做协议白名单 + 长度限制 |
| 站点标识 | `site_key` 是纯随机十六进制，**不绑 IP / 不绑账号 / 不绑域名** |
| CSRF | 心跳端点**豁免**（上报方是后台定时任务，没有会话也就没有 token）。防滥用改由「限流 30/min + 随机 site_key + 字段白名单」承担 |
| 数据留存 | 陈旧站点（30 天无心跳）**仍计数但不展示** —— 避免僵尸站点长期挂在页面上 |

### 133.3 公开端点的滥用面

| 端点 | 风险 | 缓解 |
|---|---|---|
| `POST /api/ecosystem/heartbeat` | 刷注册表 → 数字虚高 | 限流 30/min/IP；`site_key` 必须 16~64 位十六进制；payload 只认 4 个白名单字段；**数据本身标注为自报** |
| `GET /api/ecosystem/stats` | 刷接口 | 限流 60/min/IP |
| `GET /api/stats/online` | 刷接口 + 轻微泄露流量 | 限流 30/min/IP；**只返回计数**，不返回任何访客标识 |

### 133.4 表结构决定（少有的「加表」）

项目纪律是「能不改表就不改表，能用 log_audit 就不加字段」。本版**新增一张表**，`ecosystem_site`（7 列）。
理由：需要「每站点一行 + 最后心跳时间 + 按时间范围查活跃数」，而 `log_audit` 是**追加写的日志表** ——
既无法去重（同一站点每小时一条），也无法按站点聚合。幂等迁移 `c3d9e2f71a04`，
**双场景验证**（空库 upgrade / 已 create_all 的库先 stamp 再 upgrade）均通过。

### 133.5 在线数的诚实性

`compute_online()` 是**近似值**（近 10 分钟独立 IP 数，无会话表）。
接口返回 `approx: true`，前端文案写「近 10 分钟独立访客数」—— **不写成「在线人数」**。
NAT / 换网络会重复计数，短时无请求会漏掉。

### 133.6 验证

- 全量 **985 passed**（新增生态统计 20 条）
- 迁移双场景验证通过；`ruff check .` 全绿；`lint_debt.py` 无新增。
- 前台两处展示均做源码级断言 + 真实渲染验证。

---

## 第一百三十四轮（R134）· v4.7.6 生态统计改为 opt-out + 匿名路径落地

**背景**：v4.7.5 的生态统计是 opt-in（默认关）。上线后的现实是 —— 默认关闭等于
永远统计不到（没人会主动去设置页打开它）。本轮把默认值改为开，并把「匿名」从一句
口号做成一条真能走通的路径。

### 134.1 隐私影响评估（默认开启带来的新风险）

| 项 | 判定 |
|---|---|
| 默认状态 | **开启**（v4.7.5 是关闭）。关闭入口完整保留，取消勾选即零出站 |
| 上报内容 | 不变：随机 `site_key` + `version` + 时间戳 +（可选）`url` |
| 新增风险 | 未看设置页的部署者会在不知情下上报 **url** → 已在设置页与 README 写明 |
| 匿名路径 | **新增且可用**：取消「公开展示」后心跳不带 url，中心端**清空已存 url** |
| 访客数据 | 仍然**完全不采集**（不上传 IP / UA / 文章 / 评论 / 在线人数） |

⚠️ **残留风险（如实记录）**：中心端的 `EcosystemSite` 表不存 IP，应用层是真匿名；
但**中心端 nginx 访问日志仍会记录心跳请求的来源 IP**。对外宣称「匿名」时应理解为
「应用层匿名」，若要彻底匿名需把 `/api/ecosystem/heartbeat` 从访问日志中排除 ——
本轮未做（会削弱排查滥用能力），在此记录，不掩盖。

### 134.2 为什么必须内置默认中心

opt-in 默认开之后，`center_url()` 若仍保持「留空 = 不上报」，开关开着也发不出去。
故新增 `ecosystem.DEFAULT_CENTER`，留空即回退。

⚠️ 代价：官方站点成为所有实例的遥测接收端，**是单点**。缓解：`report_heartbeat()`
fail-silent（失败只记日志，绝不抛、绝不拖垮发布主流程），中心不可用只影响统计。

### 134.3 拒收/遗忘（中心端）

- payload 仍只认 `site_key` / `url` / `version` / `listed` 四项白名单，其余字段丢弃
- 非 http/https 的 url 拒收；`site_key` 必须 16~64 位十六进制
- ⚠️ **遗忘**：`listed=0` 时把已存的 `url` 清空。只做「不展示」是假匿名 ——
  旧地址仍留在表里，等于「关掉了但其实没关」

### 134.4 验证

- 生态统计测试 **23 passed**（新增 3 条：默认开启、取消参与后**零出站**、
  匿名心跳不带 url + 中心端清空 url）
- 「取消参与后零出站」用 monkeypatch 接住 `outbound.open_url` 断言调用次数为 0 ——
  不依赖真实网络，也不靠「返回 False」间接推断

---

## 第一百三十五轮（R135）· v4.7.7 修 v4.7.6 回归：测试 / CI 往生产发真实心跳

### 135.1 现象与取证

v4.7.6 上线后 `GET /api/ecosystem/stats` 的 `total` 由 1 变成 6，且出现
`https://c-1e568c3f.example.com` 这类测试域名。查 nginx 访问日志定位到三个来源：

| 来源 IP | 身份 | 说明 |
|---|---|---|
| `8.138.98.164` | 生产服务器自身 | 正常上报 |
| `223.74.146.47` | 本机 pytest | **异常**，7 次 |
| `20.98.135.189` | GitHub Actions CI（Azure 段） | **异常**，3 次 |

教训：先查**访问日志**再下结论。此前两次猜测（调度线程 race、他人伪造）都不对，
看日志一条命令就定位了。

### 135.2 根因（三个条件叠加）

1. 默认值翻成「开」；
2. 新增真实 `DEFAULT_CENTER`（缺了它「默认开启」也发不出去）；
3. `tests/test_mcp_write.py:47` 用 `create_app()` **未关调度器** —— 后台线程
   调用 `report_heartbeat()` 直连生产。

⚠️ **教训（可复用）**：把一个「默认关闭的外发功能」改成「默认开启」时，
必须同步确认**所有会实例化 app 的非生产路径**（测试夹具、清理脚本、CI、
命令行工具）都被挡住。默认值一翻，攻击面从「只有生产」变成「任何跑代码的地方」。

### 135.3 修复

- `ecosystem._is_test_runtime()`：`PYTEST_CURRENT_TEST` 环境变量 + Flask `TESTING`
  配置双判据；`report_heartbeat()` 非 `force` 时命中即返回 False（保留 `force=True`
  给人工排障）
- `tests/test_mcp_write.py` 改为 `create_app(enable_scheduler=False)`，从源头不起线程

### 135.4 数据处置

生产 `ecosystem_site` 删除 5 条假站点，仅保留官方站点（`site_key=618633f37e…`），
`total` 恢复为 1。WAL checkpoint + 属主已复原。

### 135.5 验证（含反证）

- `test_pytest_里绝不发出真实心跳`：pytest 下断言出站调用数为 0
- `test_护栏本身是唯一拦路者`：**摘掉护栏后必须真的发出** ——
  否则上一条可能是「本来就没发」的假绿
- 修复后重跑测试，生产行数不再变化（实测确认）

---

## 第一百三十六轮（R136）· v4.8.0 内容迁移插件（PR #27）安全评估

**背景**：新增插件 `myblog/plugins/content_migrate/`，把 WordPress / Typecho 的
旧站内容导入本系统。它处理**不可信输入**（用户上传的 XML / SQL）、并会**主动访问
外部站点**（下载旧站图片），因此单独做一轮安全评估。

### 136.1 攻击面与处置

| 面 | 风险 | 处置 | 判定 |
|---|---|---|---|
| 上传 | 64MB 不受限文件 | 路由内 `request.max_content_length = 64MB`；解析前嗅探格式，识别不了直接拒 | ✅ |
| XML 实体膨胀 | billion laughs（`ElementTree` 展开内部实体） | **拒绝含 `DOCTYPE` / `ENTITY` 的文档**（对整份原始字节做小写匹配），报 ParseError | ✅ |
| XML 外部实体 | XXE 读本地文件 | `xml.etree.ElementTree` 不解析外部实体；且 DOCTYPE 已一律拒绝 | ✅ |
| SQL 注入 | 把备份内容当 SQL 执行 | **纯文本扫描器**，一个语句都不执行；只按 `INSERT INTO <表> VALUES` 抽行 | ✅ |
| 路径穿越 | 上传文件名 / 图片名写盘 | 图片名 = `mig-<sha256[:16]><ext>`，与输入无关；无用户可控路径 | ✅ |
| SSRF | 下载旧站图片打到内网 | 一律走 `outbound.open_url()`：公网白名单 + **固定已校验 IP** + 禁跟随 3xx | ✅ |
| XSS（图片） | 存 SVG 造成存储型 XSS | 扩展名白名单（jpg/png/gif/webp/avif），**SVG 一律不收** | ✅ |
| 鉴权 | 未登录即可导入 | 所有路由 `@admin_required` | ✅ |
| CSRF | 跨站触发导入 | 全局中间件校验；非表单请求回落到 `X-CSRF-Token` 头 | ✅ |
| 资源耗尽 | 一次导入拖垮 worker | 每次最多 200 张图、单张 5MB、条目上限 5000；落库放后台任务（有同名任务锁） | ✅ |
| 第三方插件 manifest | `admin_url` 渲染成 `href` | 新增 `_safe_admin_url()`：**只放行 `/` 开头的站内相对路径** | ✅ |

### 136.2 审查中发现并修掉的真 bug

🔴 **导入选项全部失效**：前台用原始字节流提交文件（multipart 会先被全局 5MB
`MAX_CONTENT_LENGTH` 截住），选项只能放 query string；路由却从 `request.form` 读
→ `publish` / `download_images` / `source_base` 三个选项**静默取默认值**
（「下载正文图片」这个核心功能形同虚设）。

⚠️ **原路由测试是假绿**：它传的参数**恰好等于默认值**，所以改动前后都通过。
新测试一律用**非默认值**（`publish=draft`、`download_images=1`），
并做**变异验证**：把读取方式改回 `request.form` → 两条新测试**都变红**。

### 136.3 刻意没做的

- **评论不迁移**：本项目 `Comment` 没有「原站用户 / 邮箱验证 / 层级」字段，
  硬导会变成一堆无法追责的匿名文本，还可能与本站反垃圾策略冲突。
- **页面 / 用户 / 密码 / 附件库 / 主题设置不迁移**：预览里会计数告知。
- **插件默认不启用**（`ENABLED_PLUGINS` 默认为空），符合「装卸 = 发版 + 重启」的红线。

### 136.4 残留风险（如实记录）

⚠️ 解析在**请求内**完成（几十 MB 的 WXR 约 1~3 秒），4 worker × 2 线程 = 8 槽
的场景下，**并发几个大文件上传**会短暂占满并发槽（导入本身已放后台任务，
但解析没有）。上传 64MB + 解析峰值内存约百 MB 级 —— 小内存机器需留意。

## 第一百三十七轮（R137）· v4.8.1 内容迁移插件支持 Typecho SQLite（CWE-89 标识符注入）

### 137.1 审计范围

本轮改动集中在 `myblog/plugins/content_migrate/`：

- `parsers.py`：新增 `parse_typecho_sqlite()`、`_safe_ident()`，抽出 `_typecho_build_post()`，
  `parse_any()` 增加 SQLite 魔数嗅探。
- 其余为模板（`accept`）、插件元信息、README、测试。

**新增暴露面**：接受用户上传的 **SQLite 二进制库文件**并以 `sqlite3` 打开解析 ——
这是一条全新的「解析不可信二进制」路径，重点审它。

### 137.2 发现并修复

| 编号 | 级别 | 问题 | 状态 |
|---|---|---|---|
| 137-A | 🟡 中 | **SQL 标识符注入（CWE-89）**：初版把从 `sqlite_master` 读出的表名直接 `"%s" % tbl` 拼进 `SELECT ... FROM "%s"`。表名来自**上传文件**，完全不可信；形如 `x" ; DROP TABLE post; --_contents` 的表名会让双引号提前闭合、改写查询语义 | **已修** |

**为什么危害被压住了但仍要修**：该连接以 `mode=ro` 打开（不可能写入），且 Python
`sqlite3.execute()` 只允许单条语句（挡住 `; DROP` 这类多语句），所以实际影响是
「语法被改写 → 未捕获 `sqlite3.OperationalError` → 请求 500」。但正确做法是**先校验再拼**，
而不是依赖下游巧合。

**修法**：新增 `_safe_ident()`，标识符只放行 `[A-Za-z0-9_]`，其余抛 `ParseError`
（前台得到 400 + 清晰文案，而不是 500）。

**变异验证**（证明守卫真的有效）：把 `_safe_ident` 的校验改回 `return name` →
SQLite 把表名解析成 `x`，抛 `sqlite3.OperationalError`，该测试**变红**；
恢复校验后测试回绿。测试：
`test_parse_typecho_sqlite_rejects_malicious_table_name`。

### 137.3 逐维结论（均通过）

- **XSS**：从库里读出的 `title` / `name` 沿用既有 `html.unescape` 处理，与 `.sql` 路径一致；
  正文入库后仍经前端渲染清洗链路。无新增暴露面。
- **越权**：解析器无路由；`/admin/migrate/*` 仍带 `@admin_required`，POST 走全局 CSRF。
- **SSRF**：解析器内**零网络请求**；图片下载仍在 `importer` 里走 `outbound.open_url()`
  （公网校验 + 固定 IP + 禁 3xx），未改动。
- **密钥泄露**：无新增环境变量/凭据。
- **资源泄漏**：临时文件在 `finally` 里 `os.remove`，连接 `con.close()` 在 `finally`；
  `mkstemp` 的 fd 用 `with os.fdopen(...)` 关闭。三条路径都收口。
- **限流 / DoS**：`MAX_ITEMS=5000` 与路由的 64MB 上传上限仍生效（沿用 v4.8.0 口径）。

### 137.4 残留风险（如实记录）

- 沿用 R136 的既有项：解析仍在**请求内**完成，并发大文件上传会占并发槽；
  64MB 上传的解析峰值内存约百 MB 级。
- SQLite 解析用 `SELECT ... FROM <表>` 后 `fetchall()` —— 超大 `contents` 表会先把
  全部行读进内存再按 `MAX_ITEMS` 截断。在 64MB 上传上限下可接受，若将来放开上限需改成分页读取。

## 第一百三十八轮（R138）· v4.8.2 文章管理批量操作修复 + 中英文适配

### 138.1 审计范围

本轮改动集中在后台文章管理页与前台全局组件：

- `myblog/admin/post_manage.py`：`bulk_posts()` 的 `value` 取值改为按 action 取
  `category_value` / `series_value`。
- `myblog/templates/admin/my_posts.html`：行复选框加 `form="bulk-form"` 属性；
  两个下拉改名 + 初始 `disabled`；JS 查询根从 `form` 改为 `document`。
- `myblog/nav_entries.py` / `myblog/api/site.py` / `myblog/admin/nav_entries.py` /
  `templates/admin/nav_entries.html`：新增可选 `label_en` 字段。
- `vue-frontend/src/{App.vue, store.js, components/Sidebar.vue, components/WeatherWidget.vue}`：
  界面 i18n 化 + `t()` 支持占位变量。

### 138.2 逐维结论（均通过）

- **XSS（重点审）**：`label_en` 是**管理员可控文本**，全链路核查后无注入面 ——
  ① 写入侧 `.strip()[:40]` 截断；② 后台模板回显全部走 `{{ }}` 插值，
  `nav_entries.html` 内**无 `|safe`**；③ 前台经 `/api/site` 输出后在 `App.vue`
  以 `{{ e.label }}` 渲染（Vue 自动转义），**未使用 `v-html`**。
- **SQL 注入**：`bulk_posts` 仍是 `int()` + `isdigit()` 校验，无字符串拼接；
  改动仅涉及取值键名。
- **越权**：`bulk_posts` 的权限模型（管理员全站 / 普通用户仅自己）未改动；
  `nav-entries` 全部路由仍带 `@admin_required`。
- **SSRF**：无新增外部 URL 请求。
- **CSRF**：后台表单均被全局 `_csrf_protect` 覆盖，`label_en` 是普通表单字段。
- **密钥泄露**：无新增凭据。
- **资源泄漏**：无新增文件句柄 / 连接。

### 138.3 本轮没有新增安全问题，但有两条**质量结论**

1. **「复选框在表单外」是一类结构性缺陷**，本仓库曾在 `my_posts.html` 出现
   （其余页面 `comments.html` / `moments.html` / `config_rollback.html` 经逐一核查均正确）。
   规律已写入 `MEMORY.md`：行复选框常用 HTML5 `form` 属性关联，且 JS 必须从 `document` 查。
2. **「同表单多个同名控件」会导致后端 `get()` 取错值**（CWE-1284 类的输入校验缺陷）。
   本轮即此类。修法是分别命名 + 按 action 取，并把未启用的控件 `disabled`
   （`disabled` 的控件不随表单提交）。

### 138.4 残留风险（如实记录）

- 全站界面 i18n 尚未完成：扫描 `vue-frontend/src` 仍有约 **742 处**硬编码中文
  （含 `DocsView.vue` 227 处文档内容）。本版只覆盖全局壳（Sidebar / WeatherWidget / App）。
  这些是**可用性缺陷而非安全缺陷**，不影响英文访客的账户与数据安全。
- 文章内嵌「目录」在部分旧文章里被渲染成一大段连续链接（作者 markdown 写法所致），
  非渲染器缺陷；改动渲染器会波及全站文章，需单独评估。


## 第一百三十九轮（R139）· v4.8.3 update.sh 部署前三查加固（含脚本自更新）

### 139.1 审计范围

仅 `update.sh`（部署脚本，**不在发布 zip 内**，单独发版）。新增三段逻辑：
`cleanup_stale_updates()`（残留进程清理）、`self_update_check()`（脚本自更新）、
主流程里的「⓪ 部署前三查」。应用代码零变更。

### 139.2 安全影响逐条

- **`kill -9` 误伤风险（新增能力，重点审）**：脚本现在会**主动杀进程**。
  判据设计为「安全优先，宁可拦住也不误杀」：
  ① 有活父进程且非本进程祖先 → 判为并发更新 → 终止本次，**不杀**；
  ② `ppid=1` 孤儿 + `wchan=do_wait` → 自动杀（实测该形态不持有下载文件、不写 `$APP_DIR`，
     且杀的是「等在 gunicorn 前的壳」，gunicorn 已被 `setsid` 托管、被 init 接管，服务无损）；
  ③ 孤儿但 `wchan` 非 `do_wait` → **不猜**，报清 pid/wchan/fd 后终止，留 `FORCE_CLEAN_STALE=1` 人工兜底；
  ④ `state=Z` → 跳过。
  ⚠️ 另加**祖先链排除**：本进程的全部祖先（含 MCP 的 bwrap / `sh -c` 包装层）绝不杀。
- **`pgrep -f` 误判（实测踩到）**：只用 `pgrep -f "update[.]sh"` 粗筛会把
  「命令行里只是*提到* update.sh」的进程算进来（MCP 包装层、含该字样的脚本），
  导致合法更新被无谓拦截。故第二步必须读 `/proc/<pid>/cmdline`，
  **argv 里 basename 恰为 `update.sh`** 才算在执行脚本。
- **自更新的信任边界（未扩大）**：远端源是 **GitHub 同 tag 的 raw 文件**，
  与脚本早已信任的 Release 资产（下载后覆盖 `$APP_DIR`）**同源、同等级**。
  额外防护：替换前必须过 `bash -n`；旧版先 `cp -p` 备份；写入失败即还原；
  `SELF_UPDATE_DONE` 防重入环；`SELF_UPDATE=0` 可整体关闭。
- **可用性降级**：实测该服务器**直连 `raw.githubusercontent.com` 被重置**，
  自更新依赖 `GH_MIRROR`；取不到时仅打日志并继续，**不阻断更新**。

### 139.3 真机测试结论

4 个用例全部通过：真孤儿+`do_wait` 被自动清理且 gunicorn 无恙；
包装进程不误拦；无残留直接放行；全程 gunicorn 存活。
测试过程还**反向证明**了「祖先排除」的必要性——漏掉它时测试脚本自身会被杀。

### 139.4 残留风险

- 自更新在无 `GH_MIRROR` 的环境下不生效（仅提示，不影响更新）。
- `FORCE_CLEAN_STALE=1` 是人工逃生舱，会杀 `wchan` 异常的孤儿进程；
  若该进程恰在覆盖 `$APP_DIR` 中段，可能留下半覆盖状态（下次跑更新会重新覆盖修复）。

## 第一百四十轮（R140）· v4.8.4 update.sh 前三查打磨（无新增安全面）

### 140.1 改动性质

纯**可观测性与日志**修正，不涉及新的进程操作、网络请求或信任边界变化：

1. **重定向顺序**：`done < file 2>/dev/null` → `done 2>/dev/null < file`。
   bash 先应用左侧重定向，原写法在文件打开失败时错误先于 `2>/dev/null` 生效，
   刷无害但吓人的 stderr（R139 首次实战暴露）。
2. **日志三分支**：原逻辑仅在 `pgrep` 完全无命中时才打「无残留」；实战中 `pgrep`
   几乎总会命中包装层（被 argv 判据排除），导致日志「什么都不说」，像功能没跑。
   现区分：全部排除 / 有清理 / 完全无命中。

### 140.2 安全结论

无新增攻击面。R139 已覆盖的能力边界（`kill -9` 判据、`pgrep` 精确判据、
自更新信任边界）**完全未变**，本版只改日志输出与重定向顺序。

### 140.3 顺带记录：R139 功能的真实世界验证

v4.8.3 上线后，三查在真机测试中**自动清掉了 v4.8.3 部署自身留下的僵尸**
（`ppid=1` + `do_wait` + 0 个下载文件），且该僵尸是 gunicorn master 的父进程 ——
杀后 master 被 init 接管（ppid 1→1）、4 worker 完整、端口与公网 health 全程正常。
**这是「杀父不杀子、服务零影响」判据的实证。**

## 第一百四十一轮（R141）· v4.8.5 EdgeOne 真实 IP 还原 + update.sh 面板同步

### 141.1 审计范围

- `myblog/utils/net.py`：`get_client_ip()` 新增第 0 级 EO 分支；新增 `_clean_ip()`。
- `myblog/config.py`：新增 `EO_AUTH_KEY` / `EO_BLOCK_DIRECT`。
- `myblog/app.py`：新增 `enforce_edgeone_only()` 钩子。
- `update.sh`：新增 `sync_panel_pid()`；`setsid` → `setsid -f`。

### 141.2 逐维结论

- **IP 伪造（核心，重点审）**：`EO-Client-IP` 是**客户端可控头**，直连源站者可任意伪造。
  收口规则：
  - 配了 `EO_AUTH_KEY` 时，**必须** `X-EO-Auth` 完全相等才采纳（用 `==` 全等比较，
    非前缀/包含匹配；空密钥视为未配置）；
  - 未配密钥时仍采纳该头 —— 这是**刻意的可用性取舍**（换统计准确性），
    代价是限流可被轮换假 IP 绕过。已在代码注释、CHANGELOG、部署文档三处显式记录。
  - 采纳前必须过 `_clean_ip()`（`ipaddress.ip_address` 校验 + 去端口/去方括号），
    非法值一律拒绝并继续走后续逻辑 —— 严防脏值进 `visit_log.ip` / 审计日志 / 限流 key。
- **越权**：`enforce_edgeone_only()` 只做「有无密钥头」判定，不涉及身份；
  放行清单 `/.well-known/`（ACME）、`/api/health`（健康检查）、OPTIONS（CORS 预检）。
  **默认关闭**（`EO_BLOCK_DIRECT` 默认 false），且未配 `EO_AUTH_KEY` 时该钩子自动失效。
- **SSRF**：无新增外呼。
- **CSRF**：无新增写接口。
- **密钥管理**：`EO_AUTH_KEY` 只从环境变量读，**不在仓库/前端/文档中出现真实值**；
  部署文档用占位符并说明「为何不放真实密钥」。
- **`update.sh` 的 `sync_panel_pid()`**：新增一次**文件写入**（面板 pid 文件）。
  写入内容是本脚本刚启动的 gunicorn master pid（来自 `gunicorn.pid` 或 pgrep），
  非用户输入；失败仅告警不阻断。`setsid -f` 不改变权限模型，只改变进程父子关系。

### 141.3 已知残留风险（如实记录）

1. **未配密钥时 IP 可被伪造**（上述取舍）。缓解：配 `X-EO-Auth`，或开 `EO_BLOCK_DIRECT`，
   或让 Nginx 只对 EO 回源段透传该头（备选方案 C，未实现）。
2. **`EO_BLOCK_DIRECT` 有故障面**：EO 侧漏配规则即全站 403，故默认关闭。
3. **EdgeOne 回源段会变**：若将来改用 IP 段白名单方案需维护（腾讯提供
   `https://api.edgeone.ai/ips` 可程序化获取）。

### 141.4 测试与变异验证

`tests/test_edgeone_client_ip.py` 28 项，覆盖：密钥匹配/不匹配/缺失/空白/前缀近似、
内置头与自定义头、无密钥取舍、向后兼容（可信代理 XFF、公网直连忽略 XFF）、
脏值归一（IPv4 带端口 / IPv6 带方括号 / 裸 IPv6 / 非法值 / 逗号脏值）、
`EO_BLOCK_DIRECT` 五种场景。
三处变异验证均实测变红：① 不校验密钥 → 3 条伪造测试红；
② 不校验 IP 合法性 → 脏值测试红；③ EO 分支降到 XFF 之后 → 优先级测试红。
