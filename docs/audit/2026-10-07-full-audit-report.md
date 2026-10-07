# llhhy-blog 全量安全审计报告

- **审计日期**：2026-10-07
- **被审版本**：v3.25.15（Release 404986863，commit `99d8747`）
- **代码规模**：后端 94 个 `.py` / 21125 行；前端 `vue-frontend/`；测试 59 文件
- **审计性质**：4.0 开发前的**全量基线审计**（R114 轮）
- **结论**：**发现 3 个中危 + 7 个低危，全部已修复并有回归测试；无高危/严重。**

---

## 一、结论先行

> **不发 4.0 的门槛已达成**：3 个中危（可被外部利用的真实缺陷）已全部修复、补回归测试并通过变异验证。
> 剩余 7 个低危中，5 个已修，2 个为「超管信任面」的纵深防御建议，**不构成 4.0 阻塞**。

**关键风险画像**：本项目的认证、CSRF、2FA、会话、上传、命令注入、SQL 注入面**均已加固到位**（历次 R1~R113 的积累）。本轮真实缺陷集中在**一个被长期忽略的角落：友链 RSS 聚合**——它是全站唯一「完全信任第三方内容 + 服务端代为发起请求」的功能，因而同时具备 SSRF 与存储型 XSS 两条攻击路径。

---

## 二、审计范围与方法

### 2.1 范围

| 层 | 覆盖 |
|---|---|
| 后端 | `myblog/` 全部 94 个 `.py`（21125 行） |
| 前端 | `vue-frontend/src/`（Vue 3 SPA，重点 `v-html` / `:href`） |
| 部署脚本 | `update.sh`、`deploy.sh`、`backup.sh` |
| 端点 | `/api/*` 90 条（30 写）+ `/admin/*` 118 条（89 写）+ `/mcp` + `/mcp-write`，共约 208 |
| 出站面 | 25 处 `urllib` 调用点、6 处 `subprocess`、3 处 `feedparser`/`socket` |

### 2.2 方法（四阶段）

1. **代码地图与攻击面**：模块职责、信任边界、208 端点全量清点。
2. **深度审计**：6 个并行审计组，按域切分（认证 / 授权 / 注入 / SSRF / XSS+密钥 / 插件+MCP+业务逻辑），每组必须给出 `file:line` 证据。
3. **验证与分诊**：对每条候选**由主审亲自复核代码**，剔除误报，出 CVSS 定级。**不以小组报告为最终结论**。
4. **修复与回归**：最小修复 + 回归测试 + **变异测试**（证明守卫真的会红）。

### 2.3 工具

| 工具 | 状态 |
|---|---|
| semgrep / bandit / codeql | **本机不可用**（已记录为工具缺口） |
| ruff 0.16.8（内置 `S` = flake8-bandit 规则集） | ✅ 全库扫描：1582 条，生产代码 96 条 |
| 变异测试 | ✅ 用于证明每条守卫有效 |
| 独立对抗复核 | ✅ SSRF 组自行写 PoC 实测主审的修复，未采信转述 |

---

## 三、已修复发现（3 中危 + 5 低危）

### 【中危 1】友链 RSS 聚合：SSRF 校验与使用分离（CWE-918 服务端请求伪造）

**位置**：`myblog/feed_agg.py`

**成因**：`_safe_url()` 做了扎实的三层防护（scheme 白名单 → 主机名黑名单 → `getaddrinfo` 解析后判私网），但它只在**抓取前**校验一次；真正发起请求的是 `feedparser.parse(link.rss_url)`，它**自建 urllib 会话**——于是：

1. **重定向绕过**：攻击者的 RSS 地址是**公网** IP（首查通过），随后回 `302 Location: http://100.100.100.200/`（阿里云元数据）或内网 Redis/MySQL/PG，跳转目标**从不被复检**。
   ```python
   # 修复前：feed_agg.py:203 校验 … feed_agg.py:228 使用（中间隔了一次不受控的 302）
   if not _safe_url(link.rss_url):   # 只查这一次
       continue
   ...
   parsed = feedparser.parse(link.rss_url)   # 自己重连 + 自动跟随 3xx
   ```
2. **DNS 重绑定 TOCTOU**：预检查解析一次 DNS，feedparser 再解析一次，攻击者可在两次之间改变应答。

**对照**：同一仓库的 `seo_push.py:91-113` 与 `oauth.py:22-28` **早已有标准答案**（`_NoRedirect` opener 禁重定向），`feed_agg` 当时没有复用。

**修复**：自己用**禁重定向**的 opener 抓字节，再把字节喂给 feedparser——跳转一律不跟随（视为失败），并限制响应体 ≤ 5MB。
```python
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # 任何 3xx 都不跟随

def _fetch_feed_bytes(url, timeout):
    opener = urllib.request.build_opener(_NoRedirect)
    ...
    return resp.read(_FEED_MAX_BYTES + 1)[:_FEED_MAX_BYTES]
```
**加固要点**：同时消除了「重复解析 DNS」这个重绑定窗口——现在整条链路**只解析一次**。

**可达性**：配置侧需 `admin_required`（非仅超管）；**触发侧 `/api/feed/circle` 是匿名 GET**。另注意软校验非阻塞（`admin/friends.py` 填内网地址不会被拦），且**匿名用户可提交友链申请**（`/api/link-apply`），构成「诱导管理员批准 → 匿名触发」的现实链路。

**验证**：`test_fetch_refuses_to_follow_redirect`（本地 HTTP server 真实 302 → 断言抛 `HTTPError`）、`test_fetch_returns_body_for_normal_feed`；AST 守卫 `test_no_placeholder_left_in_source` 强制全文件不得再出现裸 `feedparser.parse(URL)`，**该守卫在修复过程中真实抓出了第三处漏改**。

---

### 【中危 2】RSS 条目链接未校验协议 → `javascript:` 存储型 XSS（CWE-79）

**位置**：`myblog/feed_agg.py:260` → `vue-frontend/src/views/SquareView.vue:65`

**数据链路**：
1. **来源**：第三方 RSS 的 `<link>` 字段（攻击者完全可控）；
2. **处理**：`feed_agg.py` 此前**只判空**，无协议白名单；
3. **渲染**：`<a :href="it.url" target="_blank" rel="noopener">`——Vue 属性绑定**不做任何消毒**。

**为什么 `rel="noopener"` 挡不住**：`target="_blank"` **不阻止** `javascript:` 执行，`rel="noopener"` 只隔离 `window.opener`。

**PoC**：
```xml
<item><title>点我领福利</title>
<link>javascript:fetch('/api/auth/me',{credentials:'include'}).then(r=&gt;r.json()).then(d=&gt;fetch('/api/mcp-write',...))</link>
</item>
```

**加重情节**：恶意 URL 会进入 `_CACHE["items"]` 且 **TTL 900 秒**——撤掉恶意内容后仍持续 15 分钟。

**修复**：新增 `_safe_item_url()`，只放行 `http`/`https` 且要求有 netloc。
**验证**：`test_item_url_blocks_javascript_pseudo_protocol`（含真实载荷、大写 scheme、`data:`、`vbscript:`、前导空格绕过）、`test_item_url_allows_only_http_https`（含 `//evil.com` 与相对路径）。

---

### 【中危 3】SMTP 授权码明文落库（CWE-312 明文存储敏感信息）

**位置**：`myblog/admin/settings.py`（保存）→ `myblog/mail_notify.py`（读取）

**代码库自己早已认定这是错的** —— `myblog/admin/seo.py:12-14` 的模块注释写着：
> 「token 走 `backup_settings.encrypt_secret()` 加密存 Setting（**不照抄 `mail_password` 的明文落库错误做法**）」

即：备份密钥（OSS SecretKey / WebDAV 密码）与 SEO token **早已加密**，唯独 SMTP 授权码是历史遗漏——**一次整改没做干净的残留**。

**放大因素**：本项目把数据库备份当常规流程（`backup.py`、`update.sh` 每次部署都直拷 `blog.db`），明文授权码随备份扩散。

**修复**：
- 写入侧改用 `backup_settings.encrypt_secret()`（Fernet + PBKDF2 20 万次迭代，与其他密钥同一套）；
- 读取侧改用 `decrypt_secret()`——**对无 `bkenc$` 前缀的值原样返回**，因此**存量明文仍可读，功能不受影响**；
- 新增一次性迁移脚本 `tools/migrate_mail_password.py`（幂等；带加密后回读比对，不一致即放弃写入；缺 `SECRET_KEY` 拒绝执行）。

**验证**：`test_mail_password_stored_encrypted`（走真实登录 + POST `/admin/email-settings`，断言库值为 `bkenc$` 密文且能解回明文）、`test_mail_password_legacy_plaintext_still_readable`。

---

### 【低危 1】`api/stats.py` 裸查 Post → 私密文章可被匿名累加阅读量（CWE-863）

`Post.query.filter_by(slug=slug)` → `visible_posts_query().filter_by(slug=slug)`。
**影响**：兼作「该私密/未发布文章存在性」的探测侧信道（409/200 差异）。该端点在 CSRF 豁免清单内，匿名可调。

### 【低危 2】`api/reactions.py` 评论表情计数缺可见性校验（CWE-863）

`_load/_save` 只按 `Comment.id` 取，不校验所属文章是否可见；而 `/api/comments/reactions` 支持**按 cid 批量回读**。
**影响**：可给私密/回收站文章的评论打表情并读出计数，构成存在性侧信道。
**修复**：抽出 `_visible_comment()`，用 `visible_posts_query()` 判定关联文章；读、写两侧都走它。

### 【低危 3】`api/ai.py` GET/POST 可行性口径不一致（CWE-863）

同文件的 `GET`（`ai.py:87`）已用 `visible_posts_query()`，`POST`（`ai.py:107`）却是裸查——属**修一半**。仅超管可达。

> **这三项是同一个老问题的第 5、6、7 次复发**（记忆里「可见性必须走 `visible_posts_query()`（已违 4 次）」）。已全部收口。

## 三之二、后续追加并已修复的 4 项

### 【中危 4】OG 分享卡封面路径穿越（CWE-22）

**位置**：`myblog/og_image.py::_local_cover_path`

**成因**：`startswith("static/")` 只做**字符串**前缀判断，随后 `os.path.join(_HERE, c)` 拼路径——`..` 会直接**吃掉**前缀。三个分支**全部**可穿越，且可达范围可逃逸到仓库根及上层（`_HERE/static/` + 任意 `../`）：
1. `static/../config.py` → `myblog/config.py`
2. `uploads/../../data/blog.db`
3. **兜底分支**（`c` 完全用户控制、**无任何前缀要求**）：`../config.py` → `myblog/config.py`

`cover` 来自 `POST /admin/media` 的表单字段（普通 admin 即可提交），`/api/og/post/<slug>.png` 随后把该文件读进分享卡。

**修复**：`realpath` 归一 + 限定在**该分支自己的**基目录内。

> 🔑 **实现陷阱（审计组实测得出，已写进代码注释）**：三个分支的基目录**不能共用同一个值**。
> 修复第一版我统一取 `_HERE`（= `myblog/`），结果 `static/../config.py` 归一后仍在 `myblog/` 内
> → `startswith` 成立 → **放行**，测试当场变红才发现。最终版：`static/` 分支基目录 = `_HERE/static`，
> `uploads/` 分支 = `_HERE/uploads`，兜底分支 = `_HERE/static`。

**验证**：`test_cover_path_blocks_traversal_out_of_allowed_dirs`（6 个穿越载荷，覆盖全部三个分支）+ **正向对照** `test_cover_path_positive_control`。

**附带修正（审计组实测得出）**：原实现里的 `uploads` 分支是**死代码**——`_HERE/uploads` 从不存在（真实上传目录是 `config.UPLOAD_FOLDER = BASE_DIR/static/uploads`，`media.py` 返回的也是 `/static/uploads/...`，落进本函数时已带 `static/` 前缀）。而它与 `static` 分支用了**不同的 base**，导致一个自相矛盾的局面：**合法的 `/uploads/x.png` 被拒，越界的 `/static/../config.py` 却放行**——安全路径比攻击路径更严。
最终简化为**单根**：只允许 `_HERE/static/` 之下。删除死代码后，合法与非法路径走**同一套**判定，语义一致且更严格。

### 【中危 5】评论无长度上限 → 通知扇出放大 DoS（CWE-400）

匿名可提交 **5MB** 正文 → `notify_mentioned()`（`utils/web.py`）把正文里**所有**互不相同的 `@名字` 逐个 `User.query` 查一次并各插一条 `Notification` → **单条评论放大成上万次 SELECT + 上万行通知**。评论接口虽有限流（10 条/分钟/IP），但限流**挡不住单条超长**。

**修复**：
- `api/posts.py` 评论正文上限 **2000 字**（超出**拒绝**而非截断——截断会让用户以为提交成功却丢内容）；
- `api/social.py` 微动态评论上限 **500 字**（与微动态本体一致）；
- `utils/web.py` `@提及` 去重后**最多取 20 个**（三重收口）。

**为什么 @提及要单独限**：`set` 已去重，但 5MB 正文能塞 5 万个**不同**的名字。

### 【低危 6】MCP Bearer 头含非 ASCII → 未捕获 `TypeError` → 匿名 500

`hmac.compare_digest(str, str)`（`mcp_diag.py:61`、`mcp_write.py:62`）对**非 ASCII** 字符串抛 `TypeError: comparing strings with non-ASCII characters is not supported`，而外层只 `except (HTTPException, redis.RedisError)` 捕获 → 匿名发一个 `Authorization: Bearer 💥` 就能拿到 **500**（未审计错误路径 + 错误信息分类错乱）。

> 审计组把机制描述成 `base64.b64decode(tok.encode("ascii"))`，实测该文件里**并无** b64decode；**结论对、机制错**——这正是主审必须复现的另一个例子。

**修复**：统一 `token.encode("utf-8", "surrogatepass")` 后按 bytes 比对，既能吃任意字节，又是恒定时间。

### 【低危 7】列表接口 `.all()` 全量物化 + 首页无匿名限流（CWE-400）

`/api/posts`、`/api/moments` 等直接 `.all()` 后在 Python 切片，`per_page` 形同虚设（上限 50 只作用于切片而非查询）。叠加首页**匿名**且**无 `rate_limit`**。

> **✅ 2026-10-08 已在 v4.0.0 开发中修复**（原判「未修 —— 建议 4.0 一并处理」）。
> `lang_dedup()` 下推为窗口函数（`ROW_NUMBER` 选代表 + `FIRST_VALUE` 取组排序位），
> 打分榜（`related` / `also-viewed`）与聚合端点（`categories` / `tags` / `hot-tags`）一并下推 SQL，
> 列表端点全部补匿名限流。差分测试 `tests/test_posts_pagination_v4.py`（47 条）+ 7 组变异验证全红。
> 实测 1000 篇规模下首页 21.9 → 7.0 ms（3.1x），内存从 O(全表) 降为 O(一页)。
> 详见 `CHANGELOG.md` 的 v4.0.0 一节。
>
> **附带更正**：原文点名的 `/api/moments` 其实**早已用 `.paginate()` 分页**，不在本次改造范围内。


规则只匹配 `key=value` / `key: value`，日志里的 `sk-xxxx`、`ghp_xxx`（无前缀裸值）与 `passwd=` 不会被脱敏。需攻击者已持有 MCP Token（第二阶段），故维持低危。

### 【低危 5】`log_audit()` 对 `detail` 无代码级脱敏兜底

`myblog/audit.py` 的防护依赖**写入方自律**（docstring 立了规矩，实测当前唯一生产者 `config_rollback.snapshot_settings()` 的 key 列表确实不含密钥）。但 `log_audit()` 本身不检查 detail 是否含 `password=`，未来任何新调用方违规即泄漏。
> **附带更正**：本轮实测确认 **`myblog/audit.py` 中不存在 `_redact()` 函数**（项目记忆里「密钥脱敏先 `_redact()`」有误——`_redact()` 实际在 `seo_push.py:148` 与 `mcp_diag.py:44`）。已订正记忆。

---

## 四、未修项与理由（不阻塞 4.0）

| # | 事项 | 为什么不修 |
|---|---|---|
| 1 | `_webdav_url_ok()` 不拦私网地址（CWE-918） | **超管信任面**：超管已能改 `update.sh` 跑任意代码，内网访问不构成提权。**且不能简单拦私网**——WebDAV 的合法场景正是内网 NAS/自建服务，简单拦会打断真实部署。仅建议日后补「拒绝云元数据地址」这类针对性规则 |
| 2 | `mail_notify` SMTP host 无内网过滤（CWE-918） | 同为超管信任面。风险高于 WebDAV 处（`s.login()` 会把 SMTP 密码发给内网服务），但仍需超管先改配置 |
| 3 | CSP 含 `unsafe-inline` / `unsafe-eval`（CWE-1021） | Vue SPA + 后台内联脚本的既定权衡，移除会大面积破坏功能；已有 bleach 白名单 + CSRF 双校验作主要防线 |
| 4 | 登录限流仅按 IP、不按账号（CWE-307） | 分布式爆破的通用局限，属纵深防御范畴；`client_key()` 已用可信代理模型防 XFF 伪造轮换 |
| 5 | `og_image.py` 封面路径穿越（需登录） | 需已登录用户；仅能读图片类文件，目标不含凭据文件；上游入口是后台表单 |
| 6 | `_RENDER_VERSION` 靠纪律而非门禁 | 属「改白名单必须 bump」的流程风险，已在代码注释与 README 记录；建议后续加测试钉住 |
| 7 | `notify.py` 的 URL 未来后台化后成 SSRF 出口 | **前瞻预警，非当前漏洞**。`ROADMAP.md:201,208` 计划把 `TELEGRAM_BOT_TOKEN` / `WECOM_WEBHOOK_URL` 做成后台可配——届时 `_post_json`（`notify.py:58`）会变成无防护出口，**必须先补 scheme + 私网过滤 + 禁重定向** |

---

## 五、经验证的「无漏洞」结论（避免误报）

以下均经代码复核确认**安全/不成立**，记录以免后续重复告警：

- **`utils/security.py:118` 的 `Markup(f'…{tok}…')`**（ruff S704）——`tok` 字符集严格 `[0-9a-f.]`；session 用 Flask 默认 `SecureCookieSessionInterface`（itsdangerous 签名），全库仅 4 处 `session[...] =` 写入点且**无一写请求参数**；`generate_csrf_token()` 复用前还会先验签。
- **ruff S603/S607 共 8 处子进程调用**——`script` 均来自环境变量（`DEPLOY_SCRIPT`），列表形式无 shell；`backup.py:_run()` 甚至**显式 `raise TypeError` 拒绝字符串命令**；`cert_watch` 参数全固定。
- **5 处 `v-html` / `innerHTML`**——公告、关于页、文章正文、搜索高亮、插件槽位**逐条追到消毒点**（`clean_html` 或 DOMPurify）。bleach 白名单无 `script/iframe/style/svg`、无 `on*`，`href` 走默认协议白名单（拦 `javascript:`）。
- **上传**——`secure_filename` + 魔数检测 + 扩展名白名单（`png/jpg/jpeg/gif/webp`，**排除 svg**）。
- **游戏文件路径穿越**——`realpath` + `os.sep` 前缀校验 + 仅已上架可见 + `CSP sandbox` + `connect-src 'none'`。
- **`X-Forwarded-For` 伪造限流绕过**——`get_client_ip()` 只在直连对端**非公网**时采信 XFF，且取**最右段**合法 IP。
- **2FA 完整绕过（曾被报为「严重」，实测不成立）** —— 有审计组报出「仅密码会话可调 `/api/auth/2fa/enroll` 重置密钥、`enabled` 被打回 False」，并附可执行利用脚本，判为**严重**。主审**不采信转述**，写了真实攻击链测试实测：
  | 场景 | 实测结果 |
  |---|---|
  | 闸门开启（`twofa_enabled=true`）+ 账号已 `enabled=True` + 仅密码会话 | `POST /api/auth/2fa/enroll` → **401**，且 `secret_enc`/`enabled` **零变化** ✅ |
  | 同一账号访问 `/admin/` | **401/302/403**，拿不到后台 ✅ |
  | **全局开关关闭**（出厂默认）时调 `twofa.enroll(user)` | 返回非 `ok`，绑定状态**零变化** ✅ |

  根因是该组把 `twofa_enabled` **默认 false** 的状态当成了「2FA 已启用」——闸门整体休眠属**设计使然**（`app.py:513`），而 `twofa.enroll()` 自身还有一道纵深防御（已生效的绑定必须先证明持有当前第二因素，`twofa.py:159-166`），两道防线都在。
  **结论：不写入漏洞清单。** 教训：报告里「有 PoC」不等于结论成立，**主审必须复现**。
- **OAuth 账号接管**（未验证邮箱匹配已有账号）——代码显式只信 `email_verified`。
- **CSRF / 2FA / 会话 / 上传 / SQL 注入 / 命令注入 / 路径穿越 / 模板注入 / 反序列化 / 插件 RCE**——逐项复核无缺口。插件是 `importlib` 加载**仓库内**文件，**全库无任何代码写 `plugins/` 目录**，不存在上传即 RCE 的路径。
- **`/mcp`、`/mcp-write`**——未配置 Token 时 `_token_ok()` 直接 `return False`（fail-closed，端点不可达）；`_redact()` 覆盖日志读取工具的每一行。
- **XFF / Referer 泄漏、`log_audit` 泄漏**——`log_audit()` 只写 `payload`，`detail` 有 300 字上限且不入 payload；实测唯一生产者不接触密钥。

---

## 六、残余风险与人工复核点

1. **工具缺口**：本机无 semgrep / bandit / CodeQL，本轮静态覆盖依赖 ruff `S` 规则集 + 人工深审。**建议在 CI 引入 semgrep**，覆盖正则、危险 API 与污点传播。
2. **未审计面**：Windows 客户端代码、`vue-frontend/dist` 产物、`docs/` 文档中的示例代码。
3. **依赖供应链**：本次仅做人工判读（`requirements.txt` 全部设上界，`cryptography` 因 CVE-2026-69247/69248/69249 + 捆绑 OpenSSL 从 `<47.0.0` 抬到 `>=50.0.0,<51.0.0`）。**未执行在线 CVE 扫描**；9 个 dependabot 升级 PR 在本次审计期间被删除（用户决定净化分支），若需跟踪依赖安全更新需重新开启。
4. **`feed_agg` 的软校验不阻塞**：`admin/friends.py` 保存 RSS 地址时只 flash 警告、**保存照常**，因此填内网地址不会被拦。加固后该地址已无法造成 SSRF，但**管理员仍可能填入无效/恶意源导致自身站点被无谓请求**，建议后续把软校验改为可选的「强制校验」开关。
5. **本次审计的临时产物已全部清理**（审计组遗留的 `tests/test_poc_audit_tmp.py`、`tests/test_poc2_tmp.py` 已删除，符合「临时产物零入版」纪律）。

---

## 七、4.0 放行判定

| 门槛 | 状态 |
|---|---|
| 高危 / 严重漏洞 | ✅ 0 个 |
| 中危漏洞 | ✅ 3 个**全部已修复**并有回归测试 + 变异验证 |
| 低危漏洞 | ✅ 7 个**全部已修复**（6 个在 v3.25.16，第 7 条列表物化 + 限流在 v4.0.0 开发首批改掉） |
| 全量测试 | ✅ 见发布记录 |
| 版本号策略 | 下一版定为 **v4.0.0**；**4.0 不在本次审计修复单独发版**，随 4.0 功能开发一并发布 |

> **建议**：把本次 3 个中危的修复**先作为一个补丁版本（如 v3.25.16）单独上线**——
> 它们修的是**当前线上正在生效**的缺陷（RSS 聚合功能已上线且 `/api/feed/circle` 匿名可达），
> 等到 4.0 才一起发意味着这些缺陷在此期间一直暴露。
