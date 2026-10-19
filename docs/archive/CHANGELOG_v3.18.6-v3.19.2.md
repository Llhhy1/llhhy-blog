# 更新日志归档件（v3.18.6 ~ v3.19.2）

> 这是**归档件**，不是当前文档。
> **拆分点**：`CHANGELOG.md` 因体积守卫（上限 200 KB）触发，在 v4.7.0 发布前
> 把 v3.19.2 ~ v3.18.6 这七轮搬到这里，主文件保留 v3.20.0 及以后。
> 查**近期**（v3.20.0 ~ 最新）变更请回 `CHANGELOG.md`；更早的 v3.18.5 及以前
> 见 `docs/archive/CHANGELOG_v1-v3.18.5.md`。
> **归档不是删除** —— 本文件内容与搬迁前逐字一致。

## v3.19.2（2026-09-23 · 修正百度配额字段名：`remain` 而非 `remaining`）

> **来源**：v3.19.1 上线后核对**生产真实数据**时发现——`seo_submission` 里 baidu 引擎的原始响应是：
> ```
> {"remain":8,"success":1}
> {"remain":2,"success":5}
> ```
> 即**百度主动推送的剩余配额字段名是 `remain`**，而不是 `remaining`。**这一条第三轮复审报告也没抓到，是生产数据抓出来的。**

### 1. 缺陷与影响

| 项 | 说明 |
| --- | --- |
| **代码事实** | `push_baidu()` 读的是 `data.get("remaining")` → 对真实响应恒为 `None` |
| **影响①（主）** | 「剩余配额」永远写不进 `Setting.seo_baidu_quota`（**生产实测该键为空**）→ 后台「🔍 收录」页的配额栏**一直空白**，用户看不到配额还剩多少 |
| **影响②** | `remaining == 0 → quota` 这条判定永不触发 |
| **未受影响（重要）** | `quota` 档**仍能被正确识别**——走的是 `data["error"]` 里 `"over quota"` 那条分支兜住了。所以**不是状态误判，只是信息缺失**。生产数据也印证：7 篇推送全部 `ok`，真实 `success` 为 1~5 |
| **顺带** | `_RESP_KEYS` 白名单里只有 `remaining`，会把真实的 `remain` 一起丢掉 → 必须同时加进去 |

### 2. 修复

- `push_baidu()`：改为 `data.get("remain", data.get("remaining"))` —— **两个名字都认**（防止文档与实际不符时再踩一次），并注明生产实测来源。
- `_RESP_KEYS`：加入 `remain`。
- `push_baidu()` docstring 里那句**错误示例** `{"success":2,"remaining":998}` 更正为 `{"remain":998,"success":2}` —— 这句错误的文档正是这个 bug 的来源，必须一并改掉，否则后人会照它再写一遍。

### 3. 验证
- **新增/加强回归**：`test_baidu_ok_parses_remaining` 现在同时断言三件事：① 真实字段名 `remain` 能解析；② `remain` 在响应白名单里（不被丢弃）；③ `{"remain":0,"success":0}` 归 `quota` 档。另保留 `remaining` 的兼容断言。
- **变异测试**：把 `data.get("remain", ...)` 回退成 `data.get("remaining")` → 该测试**变红** → 证明断言真能抓住字段名错误。
- 全量 **185 passed**（改的是既有测试 `test_baidu_ok_parses_remaining`，未新增用例）；`ruff --select F821,E9` 全绿；开发库 sha256 + mtime 双查零变化。

### 4. 部署注意
- **纯后端改动**，只需覆盖 `myblog-backend.zip`（前端包无变化）。无新表、无新依赖、无新环境变量、**无需改 Nginx**。
- 修复后**首次推送成功时**才会写入 `seo_baidu_quota`；在此之前配额栏仍为空属预期（也可在后台手动再推一次让它立即生效）。

---

## v3.19.1（2026-09-22 · 第三轮复审修复：**线上 302 环** + 出站 SSRF + 自检放大面）

> **背景**：v3.19.0 上线后收到第三轮第三方复审报告（3 High / 5 Medium / 4 Low）。**逐条回代码与线上复验**后发现 11 条里 10 条成立、1 条部分不成立（见下 §5），并确认其中**一条已是正在发生的线上事故**。
>
> 🔴 **线上事故（本版修的就是它）**：`/post/<slug>` 对**带 `Accept: text/html` 的搜索引擎**与**QQ/微信内置浏览器真人**陷入**无限 302 环**。线上实测：Googlebot / Baiduspider / QQ 真人**三者都在 12 次重定向后仍是 302** → 搜索引擎彻底抓不到正文（收录归零），真人看到 `ERR_TOO_MANY_REDIRECTS`。

### 1. 🔴 302 环（根因与修法）

**根因**：v3.19.0 把「真人否决」无差别套在**两类桶**上（`utils/seo_shell.py`）。而 nginx 的 `map` 只按 UA 粗筛、**看不见请求头**，于是：

```
/post/x ──nginx(UA 命中 → rewrite ?seo=1)──▶ /api/og/post/x?seo=1
        ◀──闸门因 Accept: text/html 否决而 302 回 /post/x──┘   ← 无限
```

**修法分两处**（都用测试钉死）：

1. **否决作用域按桶拆分**（`utils/seo_shell.py`）：
   - `Sec-Fetch-Mode` / `Sec-Fetch-Dest`：浏览器专有头，搜索引擎不送 → **两类桶都否决**；
   - `Accept: text/html`：**搜索引擎正常也会送**（Googlebot 就送）→ **只对社交桶否决**。
   - 新增 `has_fetch_metadata_signal()` / `has_html_accept()` / `HUMAN_VETO_REASONS` 三个纯函数/常量；`is_human_navigation()` 保留为「两者并集」，并在 docstring 明确警告**不要拿它当单一闸门**（这正是原缺陷）。
2. **经通道的请求绝不 3xx**（`api/og.py` 出口 3 拆成 3a/3b）：
   - **3a** 直敲 API（无 `?seo=1`）→ 302 回公开地址（安全，只有一跳）；
   - **3b** 经通道但被否决 → 按原因分流，**都不 3xx**：
     * 真人（`human-*` / `internal-referer`）→ **200 + `noindex,nofollow` 的可读页**（人能读到正文，索引不受污染）；
     * `tool-bot` / `not-crawler` → **404 + noindex，不给正文**（保持「不给批量抓取入口」的原意图）。

**顺带修**：302 响应过去**没带 `Vary`**（CDN 可能把给爬虫的 302 缓存给真人）——由测试 `test_shell_and_redirect_carry_vary` 抓出。

### 2. 出站面加固（`seo_push.py`）

| 项 | v3.19.0 | v3.19.1 |
| --- | --- | --- |
| 重定向 | 默认 opener **自动跟随**，urllib 把 POST 降级为 GET → 白名单 host 返回 302 即可**任意 host 发 GET**（半盲 SSRF） | 自定义 `_NoRedirect` 抛 `HTTPError`，3xx 原样返回落 fail |
| 成功判定 | `HTTP 200` 即判 ok（伪造 200 就能显示「推送成功」并写虚假配额） | 要求**可解析为 JSON** + `Content-Type` 含 `json` |
| 响应入库 | 上游 body 前 500 字符**原样**入库并上屏（内容回显） | `_extract_response()` **只保留白名单字段**（`success`/`remaining`/`error`/`message`…） |
| 脱敏顺序 | `_clean(text).replace(token,"***")` —— **先截断后替换**，token 落在 500 字符之后即漏抹 | `_redact()` 先抹（含 24/16/8 字符前缀片段），再截断 |

**本地实证 SSRF**（写进测试）：起两个本地服务，第一个返回 `302 → 第二个`，v3.19.0 的行为是「第二个收到了 GET」，修复后「第二个从未收到请求」。

### 3. 后台自检：从「重写一份公式」改为「真调闸门」

- `/api/seo/shell-check`：**移除自请求**（v3.19.0 用 `urllib` 回打公网地址 4 次，匿名可调 → 自请求放大面），改为 `test_request_context()` 注入请求头后**直接调 `og_post()`**，**零出网**；补 `@super_required`（匿名由 200 变 403）与 `rate_limit`。
- 探针**改送真实请求头**：搜索引擎带上 `Accept: text/html` —— v3.19.0 漏测这个头，正是**线上 302 环在自检里全绿**的原因（假绿一整轮）。
- `/admin/seo/selfcheck`：原先用本地重写的 `allow = ... and not human` 复刻闸门（**缺 `is_internal_referer` 与 `Sec-Fetch-Dest` 两道否决**，且 `seo_shell_ua` 导入后从未调用）→ 改为 `test_request_context` + 真调 `seo_shell_ua()`，**结构上不可能再漂移**。判定分 `shell` / `noindex` / `404` 三档，**三档都不允许 3xx**。

### 4. 其余修复

- **后台线程不再静默**（`seo_push._spawn`）：v3.19.0 双层 `except Exception: pass` 会让整批记录**永久停在「排队中」**且日志无痕；现在异常记 `logger.exception` 并把这批落 `fail`。
- **审计带 IP**：改用项目统一的 `admin._helpers.log_audit()`（v3.19.0 手搓 `AuditLog(..., ip="")`，`get_client_ip` 导入了却没用）。IP 在**请求线程**捕获后传入后台线程。
- **`_spawn` 失败不再被吞**：起线程失败 → 落 `fail` + `enqueue` 返回 0 + 页面不再假报「已入队」。
- **推送限流 + 在飞去重**：`rate_limit(client_key("seo_push"), limit=3, window=300)`；同引擎有 `pending` 时直接拒绝（百度当日配额用完不可逆）。
- **`keyLocation` 校验**：新增 `_keylocation()` 校验 `site_url` 的 scheme/hostname、拒绝 query/fragment/userinfo；`_valid_indexnow_key()` 出站前再校验一次 key 格式。
- **彻底删除文章清推送记录**：`admin/post_trash.py::purge_post` 显式删 `seo_submission` 同 `post_id` 行（SQLite 未开 `PRAGMA foreign_keys`，FK 不级联 → 原先留悬空行）。
- **`og:description` 剥 Markdown**：新增 `_plain_preview()`，兜底不再把 `## ` / `![图](…)` 原样写进分享卡文案。
- **模板去掉 `innerHTML`**：`templates/admin/seo.html` 改用 DOM + `textContent` 构造（服务端字段一律当纯文本）。
- **nginx map 补齐**：补入后端已接受但 map 漏掉的 `ShenmaSpider`/`ToutiaoSpider`/`QwantBot`/`SeznamBot`/`Embedly`/`Pinterest`/`Vkshare`/`W3C_Validator`/`Outbrain`/`Nuzzel`/`BitlyBot`/`Line-Poker`/`Facebot` 等，并在 `deploy_guide.md` 写明**「nginx ⊆ 后端」是必须保持的不变量**。
- 删死代码：`LOG_KEEP`、`submit_posts(actor=)` 未被使用的参数。

### 5. 复验结论（**不采信报告自述**）

11 条里 **10 条成立**。**1 条部分不成立**，须更正：

> 报告 2.1 称「生产是 **sync worker、无 `gunicorn_conf.py`**，两个并发点击即可让全站无 worker 可用」。
> **实测：`gunicorn_conf.py` 存在**（`workers=4, threads=2, worker_class='sync'`），且 gunicorn 22.0.0 会把 `threads>1` **自动升级为 gthread**（启动日志 `Using worker: gthread`，每 worker 4 线程）→ 实际是 **4×2 = 8 个并发槽**，不是「2–3 个 sync worker」，也**没有**报告描述的硬死锁（同一 worker 的空闲线程可以服务自请求）。
> 严重度应下调为「放大型可用性风险」。**但端点匿名可调、无 `rate_limit`、每次 4 个自请求这三条代码事实成立**，故仍按报告建议修掉（改为零出网）。

另：报告称「首审 4.10 gthread 至今未修」——**部署文档里确实没写 gthread**（命中 0），但线上已因 `threads=2` 自动成为 gthread，故该项的实际影响与报告描述不同。

### 6. 验证

- **185 passed**（176 基线 + **9 条新增**；另有 6 条按新契约改写并注明原因）。
- `ruff check --select F821,E9 myblog/ tests/` **All checks passed**。
- **变异测试**：把修复回退（闸门恢复全域否决 + 出口恢复 302）→ **13 条测试变红**，含两条新回归（`test_search_engine_with_accept_html_still_gets_indexable_shell`、`test_channel_never_returns_3xx`）→ 证明新测试不是空转。
- **顺序无关**：随机顺序全量跑同样 185 passed（限流状态已用 autouse fixture 隔离）。
- 新增回归：环不变量（8 种 UA 矩阵、经通道禁 3xx）｜搜索 UA 带 Accept 仍可索引｜重定向不跟随｜非 JSON 200 不算成功｜响应字段白名单｜脱敏先于截断｜线程异常落 fail｜`_spawn` 失败落 fail｜审计带 IP｜推送限流｜pending 去重｜`keyLocation` 校验｜purge 清孤儿行。

### 7. 部署注意

- **纯后端改动**，只需覆盖 `myblog-backend.zip`（前端包无变化）。
- **本版不强制改 nginx**：核心修复（不再 302）在后端生效；map 补齐只是让更多抓取方拿到壳页。若要补齐，按 `deploy_guide.md` 更新 `map` 后 `nginx -t && nginx -s reload`。
- **⚠️ 上线后必须复验环是否消失**（这是本版的核心验收）：
  ```bash
  # 三者都应返回 200，且 num_redirects=0
  curl -s -o /dev/null -L --max-redirs 12 -w '%{http_code} %{num_redirects}\n' \
    -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
    -H "Accept: text/html,application/xhtml+xml,*/*;q=0.8" https://<域名>/post/<真实slug>
  ```
- 后台「🔍 收录」页的「通道自检」现在会显示**三档**（可索引壳页 / 可读但不索引 / 不给内容），并在出现 3xx 时明确报警。

---

## v3.19.0（2026-09-21 · 后台「🔍 收录」控制台：主动推送 + 通道自检）

> **背景**：v3.18.9 把爬虫通道接通了（爬虫能拿到带正文的壳页、微信卡片能用），但**「接通」不等于「被收录」**——SEO 的另一半是**主动告诉搜索引擎「我更新了」**。此前站点只能被动等爬虫、以及在 robots.txt 里屏蔽坏 Bot，缺「主动推送」这一环。
>
> 本版按实施清单阶段 2 建后台收录页。**边界很明确**：UA 分类、搜索引擎限流豁免、坏 Bot 屏蔽、sitemap/robots 生成**全都已经存在**，本页只做两件真正缺的事——**主动推送 + 通道自检**，其余一律给跳转链接，不复制控件。

### 1. 数据模型：`SeoSubmission`（新表，**不用 Setting KV**）
推送状态是「每篇 × 每引擎」的行，必须建表。写成 `Setting(key="baidu_push_<post_id>")` 是**明确的错误**：`Setting` 全表 `query.all()` 在 6 处被调用（含 `app.py::inject_globals` 的**每次模板渲染**），按文章写长 KV 会把它变成 O(n) 负担。

```python
class SeoSubmission(db.Model):
    post_id    # FK post.id，index
    engine     # "baidu" | "indexnow"
    status     # pending|ok|fail|quota
    submitted_at
    response   # 截断存（含返回码）
    __table_args__ = (db.Index("ix_seo_sub_post_engine", "post_id", "engine", unique=True),)
```

**迁移策略已明确记录（清单要求「别两边各写一半」）**：本表**暂由 `app.py::_migrate_new_tables_v3()` + `db.create_all()` 自愈创建，不走 Alembic**。理由：`migrations/versions/*` 的基线本身就是假迁移（stamp 出来的 `db.create_all()`），此时单为一张新表引入真实迁移脚本会造成两套体系并行。模型 docstring 里写明了这一点与日后补 baseline 迁移的条件。

### 2. 推送引擎（`myblog/seo_push.py` 新增）
- **百度主动推送**：`POST http://data.zz.baidu.com/urls?site=<域名>&token=<token>`，body 是换行分隔的绝对 URL，返回 `success`/`remaining`/`error,message`。
  - ⚠️ **这是本项目唯一必须显式允许 http 的出站目标**（官方地址就是 http，没有 https）。因此白名单**精确比对 host**：`http` 仅当 host **等于** `data.zz.baidu.com` 才放行。刻意不做后缀匹配——`http://data.zz.baidu.com.evil.com/` 与 `http://data.zz.baidu.com@evil.com/` 都必须被拒（已写成测试）。
- **Bing / IndexNow**：`POST https://api.bing.com/indexnow`，`{host, key, keyLocation, urlList}`；需站点根放 key 文件。
  - **IndexNow key 做规范校验**（8–128 位、仅 `[A-Za-z0-9-]`）。这不是洁癖：key 会被拼进 `keyLocation` URL，不校验就能塞 `/`、`..`、空格，把 `keyLocation` 指向站内任意路径。非法值**拒绝保存**并提示。
- **Google 不做自动推送**：Google 没有通用推送 API（Indexing API 仅对 `JobPosting`/`Recipe` 生效且要服务账号）。页面只给 sitemap 地址 + GSC 入口链接，**不造一个假的「提交成功」按钮**。

**两条纪律**：
1. **URL 一律 `site_base() + "/post/" + slug`**，绝不来自用户输入或 `request.host`（延续 v3.18.9 的 Host 注入修复）。
2. **推送必须异步**：入口只「写 pending 行 → 起 daemon 线程 → 立即返回」，外发全在后台（照抄 `mail_notify.notify_subscribers_async()` 的模式）。附 `timeout=10s`、单次 500 条上限、失败**不自动重试**（避免无效请求吃掉配额），由页面手动重推。

### 3. 批量语义：**按批一次请求**，不是每篇一发
百度与 IndexNow 都接受换行 / `urlList` 批量提交。逐篇发等于把配额和带宽都浪费掉。批失败时整批落同一状态，页面显示截断后的响应供判断（token 错 vs 网络问题）。

### 4. `quota` 单独成一档（**一个会误导人的顺序坑**）
百度在配额耗尽时返回 `{"success":0,"remaining":0}`——**既没有 `error` 字段，`success` 也是 0**。若按「有 `success` 就 ok」的朴素顺序判断，这种情况会被记成绿色的「已推送」，实际一条也没推成功。因此判定顺序固定为：**先 `error` → 再 `remaining == 0` → 最后 `success`**，且 `success == 0` 归 `fail`。已写成测试钉死。

### 5. 凭据存储（**不照抄 `mail_password` 的错误做法**）
token / key 走 `backup_settings.encrypt_secret()`（PBKDF2-HMAC-SHA256 200k + Fernet，`bkenc$` 前缀）。`admin/settings.py` 里 `mail_password` 是**明文落库**的反例，本页刻意不照抄。另外：
- **留空 = 保持不变**，清除需显式勾选（否则「编辑页面时浏览器自动清空密码框」会静默抹掉凭据）；
- 页面只回显掩码（`••••••`），**明文绝不上屏**；
- **响应清洗会抹掉 token**——百度可能把带 token 的请求 URL 回显在错误里，直接落库/上屏就等于泄露密钥（`_clean` 里 `.replace(token, "***")`，有测试）；
- 审计日志**只记「改了哪个键」，不记值**。

### 6. 安全与权限
- 全部 6 条路由（`/admin/seo` 及 5 个子接口）`@super_required`；普通管理员一律 403（有测试）。
- 全部写操作带 CSRF（模板 `csrf_input()` + 全局 `_csrf_protect` 兜底，缺 token 403 有测试）。
- **不可见文章拒绝推送**：草稿/隐私/回收站/未到点定时的文章**单篇推送直接拒绝**并写审计（`seo_push_reject`）。理由：给搜索引擎送 404 会浪费配额并拉低站点质量评分。批量推送的候选也走 `visible_posts_query()`。

### 7. 后台页面（`/admin/seo`，侧栏「🔍 收录」）
① **通道自检**：服务端跑 4 身份闸门判定（Baiduspider / MicroMessenger / **QQ 内置浏览器真人** / Chrome），另给「真机验证」按钮直达阶段 1 的 `/api/seo/shell-check`（走完整 nginx 链路）。**两个真人用例必须显示「拿到 SPA」**——只测爬虫照不出真人误伤。
② **推送凭据**表单（掩码回显 + 显式清除 + IndexNow key 校验 + key 文件放置说明）。
③ **批量/单篇推送**（选引擎 + 选「最近 N 篇未推送」；已 ok 的不重发以省配额；接口立即返回，页面 3 秒轮询）。
④ **文章列表**（每篇显示百度/Bing 状态 + 失败响应摘要 + 单篇推送按钮）。
⑤ **sitemap/robots 只读预览**（**直接复用既有视图**，不重写生成逻辑，防预览与实际输出漂移）+ GSC / Bing / 百度站长入口链接。

- **验证**：**171 passed**（142 基线 + **29 条新增** `tests/test_seo_push.py`）；`ruff --select F821,E9` 全绿。
- 新增测试覆盖：token 密文存储（断言 `bkenc$` 前缀且能解回原文）/ 页面无明文 / IndexNow key 校验（5 种非法值）/ 留空不改写 / 非超管 403（5 条路由）/ 匿名非 200 / 缺 CSRF 403（推送与凭据各一条）/ **推送不阻塞请求**（把 `_http_post` 打成「命中即抛错」的替身，请求线程内不得被调用）/ enqueue 起 daemon 线程 / **出站白名单精确性**（4 种绕过手法）/ 白名单外不发请求 / URL 来自 `site_base()` 而非 Host / `site_base()` 缺失时全批 fail 且不发请求 / 不可见四态拒绝 / **响应回显抹 token** / `quota` 独立成档（含 `success:0,remaining:0` 那个坑）/ remaining 解析 / 页面渲染（有无 site_url 两种情况）/ 状态接口 / 预览复用既有视图。
- **本轮未 commit / push / tag / 未建 Release**（等显式发版口令）。改动了 `deploy_guide.md` 但**未动** `update.sh`/`deploy.sh` → 不需要 `deploy_scripts_*.zip`。

### 8. 顺带：字体入库（关闭 v3.18.9 遗留的待决策项）
`myblog/static/fonts/` 补入 **文泉驿微米黑**（`wqy-microhei.ttc`，5,177,387 B，sha256 `e4bca8df…c88212`）。选它是因为在候选里体积最小（Noto Sans SC VF 17.77 MB / Source Han Sans CN 8.04 MB / LXGW WenKai Lite 13.23 MB）。

- **许可**：GPL v2 + **字体嵌入例外条款**（**不是 OFL**，`FONTS.md` 里明确写明，不可声称 OFL）。换 OFL 字体需同步改说明，且 Noto CJK 单字约 20 MB 是其 4 倍。
- **顺带修掉一个真缺陷**：`og_image.py::_cjk_candidates()` 原先只对 `.ttf`/`.otf` 做字重命名匹配，**`.ttc` 不参与** → 放进仓库的 `*-Bold.ttc` / `*-Regular.ttc` **永远不会被优先选中**（静默用回任意字体）。已补 `.ttc`。
- **降级路径不再静默（可观测性）**：`og_image.py` 此前三处降级全无日志——Pillow 不可用、**找不到中文字体**、渲染异常——这正是「`.png` 分享卡恒返回兜底图」能潜伏整整一个版本周期而无人察觉的原因。现三处均加 `logger.warning`（含字体目录与 `_PIL_OK` 状态），运维可直接从日志定位。**不改任何行为，只补痕迹**，无测试破坏（171 passed 保持不变）。
- `package.py` **无需改动**（`add_tree()` 递归 `myblog/`，`static/fonts/` 自动入包，已模拟验证）。
- `FONTS.md` 记录了「为什么必须打包」（静默降级潜伏了一个版本周期的教训）与**改完必须清两处缓存**（后端 `data/og_cache/` + nginx `proxy_cache_dir`）。



## v3.18.9（2026-09-21 · SEO 爬虫通道修复：从「接通即拒收」到真正可收录）

> **背景（阶段 0 真机自查结论）**：线上 nginx **早有一条手工配置的爬虫规则**（`location ~ ^/post/` 里的 `if ($http_user_agent ~* "(bot|spider|crawl|…")` → `rewrite … /api/og/post/$1`），但它**从未入库到 `deploy_guide.md`**——`routes.py` 的注释声称「Nginx 有 bot 规则」，而部署文档里 0 命中。更糟的是后端那个页面的行为：
>
> ```bash
> # 实测（修复前）
> curl -sSI -A "Baiduspider" https://域名/post/post-8   # → 200 + x-robots-tag: noindex,nofollow
> #                                                    #   + canonical: https://域名/api/og/post/post-8
> curl -sS  -A "MicroMessenger/8.0.40" https://域名/post/post-8  # → SPA 空壳（og:image 命中 1 次，
> #                                                    #    来自 index.html 里写死的默认值）
> ```
>
> 即：**百度能被引导进来，进来后立刻被告知「请勿收录」，且 canonical 指向 API 地址**——等于主动放弃收录。微信根本进不来（`detect_bot()` 认不出 `MicroMessenger`）。本版把通道做成真正可用的东西。

### 1. 出口语义（`myblog/api/og.py` 重做，三种互斥出口）
| 条件 | 响应 | 理由 |
| --- | --- | --- |
| 文章不可见 | **404** + `noindex,nofollow` + 站点级兜底文案 | 不透露该 slug 任何信息 |
| 经通道（`?seo=1`）且判定为抓取方 | **200** 壳页 + **`index,follow`** + canonical=公开地址 | 正式出口，**允许收录** |
| 其余（真人 / 直敲 API） | **302** → `/post/<slug>` | 真人回到能跑 JS 的 SPA；不留下「可索引但 canonical 指向自己」的页面 |

- **`X-Robots-Tag` 不再恒发 `noindex`**（修复前那行接通通道即杀死收录）。仅「不可见」与「非通道直敲的兜底」给 noindex。
- **canonical / og:url / twitter:url 全部改为 `site_base() + /post/<slug>`**，不再用 `request.url`（修复前会生成 `…/api/og/post/<slug>`）。
- 三种出口都带 **`Vary: User-Agent, Sec-Fetch-Mode, Accept, Referer`**（同一 URL 三种结果，不声明会被 CDN/共享缓存串味）。

### 2. 通道闸门（`myblog/utils/seo_shell.py` 新增，**独立于 `detect_bot()`**）
两条实测结论决定了它不能复用 `detect_bot()`：
- `detect_bot("…MicroMessenger/8.0.40")` → `(False, "", "")`：**微信 UA 里没有 bot 字样**，任何 `== "search"` 闸门都必然让微信卡片失效。
- `detect_bot()` 把社交抓取器与 Ahrefs/curl **混在同一个 `tool` 类**里 → 只放行 `search` 微信失效、整体放行 `tool` 等于给第三方 SEO 蜘蛛送全文入口。

因此闸门做成**两层**：① 放行候选（搜索引擎 ∨ 社交/IM 预览抓取器，各自独立 UA 表）；② **真人否决**——命中 `Sec-Fetch-Mode: navigate` 或 `Accept: text/html` 或站内 Referer 即一律否决，即使第一层命中。

> ⚠️ **这一层是防生产事故的关键**：QQ 内置浏览器里的真人 UA 常带 `QQ/9.7.x`（如 `…MQQBrowser/13.0 QQ/9.7.10.43400`），会被第一层命中；没有第二层否决，真人就会看到一张几乎空白的壳页。**爬虫侧测试全绿也照不出这一类。**

限流 `rate_limit(client_key("og_shell"), limit=120, window=60)` **豁免正规搜索引擎**（把 Google/Baidu 正常抓取 429 掉等于自废收录）。

### 3. 可见性漏判修复（`[安全红线]`，两个入口都漏）
`og.py` 的 meta 页与 `.png` 分享卡**各自手写** `filter_by(slug, published=True, in_trash=False)` 再补 `if post.is_private`——**两处都漏 `scheduled_at`**。未到发布时间的文章标题既能被 meta 页读到，也会被**画进那张对外可取的 PNG 图**。现统一改走 `visible_posts_query().filter_by(slug=slug).first()`，删掉手工 `is_private` 判断，并修正模块 docstring（原文声称「只读 visible_posts_query」与实现相反）。

### 4. 壳页带正文 + 结构化数据（百度对 JS 最不友好，只有 meta 时 rankings 弱）
- 正文**复用 `Post.content_html` 缓存列**（`render_post_html`，命中时几乎零成本），不新写渲染逻辑 → 不引入与正文页不一致的白名单/XSS 差异。
- 加 **`BlogPosting` + `BreadcrumbList` JSON-LD**（`</` 显式转义防 `</script>` 提前闭合）。
- 壳页无 CSS、无脚本；`<article>` 包正文。

### 5. 站点地址收敛为唯一真相源（`utils/settings.py::site_base()`）
此前 canonical / og:url / sitemap / feed / 邮件链接 / MCP 指令各自取值（有的只读 DB、有的回退 `request.url_root`）。现统一为 **DB `site_url` → env `SITE_URL` → 空串**，并**删除 `request.url_root` / `request.host` 回退**——那等于让请求方提供的 Host 决定我们对外声明的 URL（`Host: evil.example.com` 可诱导 canonical 指向外部域名，首轮审计 2.9 遗留项）。未配置时输出相对路径，诊断页红字提示。

改动点：`api/og.py`、`routes.py`（`_site_base` / feed / sitemap / comments_feed）、`diagnostics.py`（站点配置 + SEO 两节，并新增**爬虫通道路由存在性检查**）、`mail_notify.py`、`api/posts.py`（分类/标签 RSS）、`admin/mcp_services.py`。

### 6. Nginx 配置**入库**（`deploy_guide.md` 新增「第 4b 步：SEO 爬虫通道」）
- 用 `map $http_user_agent $seo_shell` + `location /post/` 内 `rewrite …?seo=1 last`（`last` 会重新匹配 location 从而命中既有的 `location /api/` 反代；避开在 `if` 里写 `proxy_pass`）。
- **明确写入两条禁令**：绝不加 `QQBrowser` / `MQQBrowser`（那是真人）；绝不写成宽泛的 `bot|spider|crawl`（会把 Ahrefs/Semrush 放进通道）。
- 附完整的验证命令（爬虫/真人/QQ 内真人三种视角）。
- **线上已按此更新并 reload**（`nginx -t` 通过；原配置备份在 `/root/html_www.llhhy.cn.conf.bak-v3189`）。
- `routes.py` 里那条「Nginx 的 bot 规则会把 /post/* 改写」的注释**改为指向 `deploy_guide.md` 的实际章节**（原文声称有规则而文档里没有 = 重装即丢）。

### 6b. 顺带查出并修复：分享卡 `.png` 自 v3.16.0 起**一直**返回兜底图（三层叠加故障）

真机验收时发现 `https://域名/api/og/post/<slug>.png` 恒返回 966 B 兜底图，且与站点根目录的 `og-default.png` **sha256 逐字节相同**。逐层剥开是**三个独立故障叠在一起**，缺任何一层都不会是这个症状：

| 层 | 故障 | 处置 |
| --- | --- | --- |
| ① 字体 | `og_image.py` 文档声称「仓库内打包开源字体」，但 `myblog/static/fonts/` **在仓库与服务器都不存在**，服务器也无任何 CJK 字体 → `_find_font()` 返回 `None` → `render_og_image()` 返回 `None` → **静默**降级成兜底图（全程不报错，所以潜伏了一个版本周期） | 服务器 `apt-get install -y fonts-noto-cjk`；`render_og_image` 立即恢复输出 1200×630 真实卡片 |
| ② nginx | 宝塔默认 `location ~ .*\.(gif\|jpg\|jpeg\|png\|bmp\|swf)$` 是**正则 location**，优先级高于 `location ^~ /api/`，把 `/api/og/**/*.png` 从反代上抢走 | 新增 `location ^~ /api/og/ { proxy_pass …; }`（`^~` 之间按最长前缀取胜，命中即跳过正则） |
| ③ 缓存 | 宝塔 `proxy.conf` **全局** `proxy_cache cache_one;`，把①时期吐出的那张兜底图**长期缓存**了；客户端发 `Cache-Control: no-cache` **无法**绕过 | `find /www/server/nginx/proxy_cache_dir -type f -delete` |

- **定位手法（可复用）**：① 分层——`curl` 直打 `127.0.0.1:8686` 确认后端正确、再经域名复现外部症状，**问题必在中间层**；② `Content-Disposition: inline; filename=og-default.png` 与 `etag` 格式指认响应来源；③ **加唯一 query 参数**（`?v=2`）能绕开静态/缓存命中，是「快速判断是否被缓存层截胡」的可靠手段；④ 在 nginx 各候选 location 里临时 `add_header X-Which …` / `return 418` 直接问出**实际命中的是哪个 location**（本次据此证明 nginx 层修复已生效、病灶在缓存层）。
- **文档同步**：`deploy_guide.md`「第 4b 步」新增 ③（`^~ /api/og/` 原文 + 判据）与 ④（`proxy_cache` 清缓存），验证命令补上分享卡一条。
- ⚠️ **仓库侧仍待决策**：`myblog/static/fonts/` 是否补入 OFL 可分发 CJK 字体（避免换服务器后重新降级），涉及包体积与 `package.py` 收录范围，**本轮未擅自改动**。

### 7. 后台「通道自检」接口（`/api/seo/shell-check`）
按需自测本端点在 **4 种身份**下的真实响应（Baiduspider / MicroMessenger / **QQ 内置浏览器真人** / Chrome），返回三盏灯：是否拿到服务端 HTML、canonical 是否等于 `/post/<slug>`、是否 `index,follow`；并检查 `site_base()` 是否已配置。**两个真人身份必须显示「拿到 SPA」**——这一项才是防事故的关键，只测爬虫是不够的。

- **验证**：**142 passed**（126 + 16 条新增，`tests/test_seo_shell.py`）；`ruff --select F821,E9` 全绿。
- 新增测试覆盖清单的 **7 条判定表**（百度→壳 / 微信抓取器→壳 / 微信真人→302 / QQ 真人→302 / Chrome→302 / Ahrefs&curl→不给 / 站内 Referer→不给）+ **隐私·回收站·定时未到 三态 × meta页·png 两入口** + Host 头不得进 canonical + `Vary` + JSON-LD/转义。
- 做了**变异测试**验证这些断言真的能抓回归：① 把 `index,follow` 回退成恒 `noindex` → 2 条红；② 删掉第二层真人否决 → 2 条红（微信/QQ 真人变 200）。



## v3.18.8（2026-09-21 · 修复 v3.18.7 上线实测发现的验签顺序缺陷：工作目录旧清单未清）

> **v3.18.7 上线首次实测即失败**，但**站点未受任何影响**——新的 fail-closed 逻辑在「覆盖代码之前」就拒绝了安装（这正是它该有的行为）。根因是 v3.18.7 自身的一个顺序缺陷，本版修复。

- **根因**：`$WORK`（`/tmp/llhhy_update`）在多轮更新之间是**复用的**，而脚本原先只清解压目录、**不清校验清单**。v3.18.7 的 `verify_release_signature` 又排在「下载清单」之前，于是：上一轮（v3.18.6）遗留的 `sha256.txt`（00:28）被拿去和本轮新的 `sha256.txt.sig`（00:43）配对比对 → 必然 `BAD`。
- **修复**：① `verify_release_signature` 内部**先 `rm -f sha256.txt sha256.txt.sig`，再自己下载两者**（不再依赖调用方先下载，函数自包含）；② `$WORK` 准备阶段显式清掉 `sha256.txt` / `sha256.txt.sig` / 两个 zip；③ 新增契约测试 `test_stale_workdir_files_are_cleaned` 把「先清旧清单再下载」钉死。
- **教训（值得记）**：**跨轮复用的工作目录 + 校验文件 = 隐性状态泄漏**。任何「读一个可能已存在的文件」的校验逻辑，都要先明确它是**这一轮**产生的。
- **验证**：**126 passed**（125 + 1 条新增契约测试）；在服务器上以「新脚本 + 旧版本站点」端到端实跑：**签名校验通过 → 哈希校验通过 → zip 注释双源互证通过 → 备份 → 覆盖 → 重启全绿**（这是 v3.18.7 想做但没做完的那次真实演练）。



## v3.18.7（2026-09-21 · 更新链 fail-closed + Ed25519 发布物签名：一键在线更新对所有人开箱可用）

> 起因：v3.18.5 的独立审计把「在线更新链完整性校验全链 fail-open」判为**全仓最高风险**——`sha256.txt` 与它描述的产物走**同一条下载通道**，脚本里还有 4 处「取不到校验文件 / 清单里查不到该文件」时**静默 `return 0` 继续安装**的分支，外加自动兜底第三方公共镜像（ghfast / gh-proxy / ghproxy）→ 能拿到包就能同时改写校验清单，等价一条远程代码执行通道。
> 处置原则（用户要求「这个功能大家都能用」）：**默认安全、人人可用、想绕开必须显式声明**。公钥内置在脚本里 → 任何人 clone 部署即用，无需任何配置；自建发布者换掉公钥即可。

### 新增：Ed25519 发布物签名（唯一能打破自指的信任锚）
- **发布侧**：`package.py` 打包后对 `sha256.txt` 做 **Ed25519 分离签名** → 新资产 `sha256.txt.sig`。**首次运行自动生成密钥对**到 `~/.workbuddy/llhhy_release_key`（0600）并打印公钥——这样「clone 下来就能出可被接受的签名包」，不会因为「没配密钥」卡住。支持 `--gen-key`（只看/生成密钥）、`--no-sign`（调试）、`RELEASE_SIGNING_KEY`（指定私钥路径）。
- **消费侧**：`update.sh` / `deploy.sh` **内置公钥** `BUILTIN_RELEASE_PUBKEY`，可被环境变量 `RELEASE_PUBKEY` 覆盖。校验用 `cryptography`（**本就是硬依赖**，零新增），验签失败/签名缺失一律 `fail_exit`。
- **本地三链校验**：`verify_package_checksums.py` 增加 **双源互证 ③**——用 `update.sh` 里**读出来的同一个公钥**验证 `sha256.txt.sig`（从脚本里读，不另存一份，避免漂移）。

### 修复：fail-open 全链转 fail-closed（7 处）
| 位置 | 原行为 | 现行为 |
|---|---|---|
| `sha256.txt` 未附带 | 跳过校验，继续安装 | **终止更新** |
| `sha256.txt` 下载失败 | 跳过校验，继续安装 | **终止更新** |
| 清单里查不到该文件 | 跳过校验，继续安装 | **终止更新** |
| zip 注释双源互证失败（NO/ERR/无输出） | 「降级为仅靠哈希列表比对」 | **终止更新** |
| 无 python3 | 跳过 zip 注释校验、跳过 HMAC | **终止更新** |
| HMAC 首行格式 | 只在首行以 `HMAC ` 开头时才校验（**删掉首行即关闭签名**） | 带签名但无密钥时明确标注「已被 Ed25519 取代」；带签名且无 python3 → 终止 |
| 下载通道 | **自动**兜底 `ghfast.top` / `gh-proxy.com` / `ghproxy.net` | **不再自动兜底**；只认显式配置的 `GH_MIRROR`（该代理可信度由运维承担） |

### 新增：版本单调性 + 两个显式逃生舱
- 远端 tag == 本地 `APP_VERSION` → 提示「已是最新」并收工；远端 **低于**本地 → 默认**拒绝降级覆盖**（`ALLOW_DOWNGRADE=1` 才放行，用于刻意回退）。
- `ALLOW_UNSIGNED=1`：仅调试 / 自建发布链过渡期使用，**必须显式设置**，且会打醒目警告。

### 架构收敛：`deploy.sh` 改为 `update.sh` 的薄封装
历史上 `deploy.sh` 是 `update.sh` 的一份**独立副本**且长期停在更弱的一版（同一份校验逻辑两份实现、安全面不一致；Webhook 路径就是走它）。现改为 `exec bash update.sh` —— **单一实现、单一审计面**，Webhook 路径自动获得同等的签名校验。文件从 529 行降到 ~45 行。

- **验证**：**125 passed**（119 基线 + 6 条新增 `tests/test_update_chain_contract.py`，静态钉死「不得出现 fail-open 措辞 / 不得自动兜底第三方镜像 / 公钥非空且验签强制 / 逃生舱默认关闭 / `deploy.sh` 必须是薄封装 / 脚本必须 LF 行尾」）。
- **反向实测 20/20 通过**（用 `update.sh` 里**真实的那段内联验签代码**跑，不是另写一份等价逻辑）：官方签名通过；篡改 `sha256.txt` 被拒；冒名密钥签名被拒；签名损坏被拒；空公钥被拒；篡改 zip 内容区被 ②拦截；7 类旧 fail-open 措辞已清除；镜像兜底已除；两个逃生舱与版本单调性在位。
- `bash -n update.sh` / `bash -n deploy.sh` 通过；两脚本 CRLF=0、孤立 CR=0（服务器上 CRLF 的 bash 会直接语法报错）。
- **无表结构变更、无新增依赖（`cryptography` 原已是硬依赖）、无新增环境变量（新增的都是可选环境变量）、前端产物零变化。**

### ⚠️ 部署顺序（本轮特殊：更新链自身被改）
服务器上的 `update.sh` / `deploy.sh` **不在** `myblog-backend.zip` 里，必须单独覆盖：
1. 从本 Release 下载 `deploy_scripts_v3187fix.zip`，解压覆盖 `/www/wwwroot/myblog/update.sh` 与 `deploy.sh`（保持 LF 行尾，`chmod +x`）；
2. 再跑 `bash /www/wwwroot/myblog/update.sh`。
> 顺序反了会怎样：**不会坏**——旧脚本仍能装上 v3.18.7 的后端代码，只是那一刻生效的仍是旧（fail-open）校验逻辑；覆盖脚本后下次更新才走新逻辑。



## v3.18.6（2026-09-20 · 退役公共 SSR：8 个页面路由改 410 + 删 7 个死模板）

> 起因：v3.18.5 的独立审计确认「双前端并存」——生产 Nginx 只把 `/api/` `/admin` `/static/` `/mcp*` 与 `feed.xml` / `sitemap.xml` / `robots.txt` / `feed/comments` 反代给 Flask，**其余路径全部由 Vue SPA 兜底**，于是 `routes.py` 里 8 个「页面级」SSR 路由在生产从未被访问。它们不只是死代码：还会和 SPA 的同名页面各自漂移（v3.18.5 修的「模板时间打 UTC」bug 就只存在于这些死模板里，改了两遍才发现生产根本用不到）。

- **8 个公共 SSR 页面退役为 410 Gone**：`/`（首页）、`/post/<slug>`（文章页）、`/category/<slug>`、`/tag/<slug>`、`/search`、`/about`、`/links`、`/archive`。这些页面的渲染逻辑（含 `_render()` 辅助、每页的 DB 查询、文章页的 JSON-LD/OG 拼装）一并移除。
- **保留了 endpoint 名，没有直接删路由**——这是硬约束：`base.html`（仍被 `/login` 与 `/register` 使用）里有 `url_for('main.post')` / `url_for('main.archive')` 等 8 处引用，删除路由会让**登录页渲染直接 `BuildError`**。故改为「路由仍在、只返回 410」，`url_for` 照常生成链接（浏览器访问这些链接时由 Nginx 交给 SPA，用户无感）。
- **不做 302 → SPA**：Flask 路由路径与 SPA 路径同名（如 `/post/x`），302 会让直接访问 `:8686` 的客户端自环。410 语义也更准确：「该资源在此不再提供」。
- **删除 7 个死模板**：`index.html` / `post.html` / `archive.html` / `archive_timeline.html` / `about.html` / `links.html` / `search.html`。`myblog/templates/` 顶层现在只剩认证与错误页 8 个文件（`base.html` / `login.html` / `register.html` / `403` / `404` / `500` / `error` / `_error_base`）。→ **从根上消灭「SSR 模板与 SPA 各自漂移」这类问题**。
- **明确保留不动**：`/login` `/register` `/logout`（认证页 SSR——`app.py` 的会话失效跳转依赖 `url_for("main.login")`）、`/post/<slug>/comment` 与 `/post/<slug>/like`（两个 POST 入口，是 `DocsView` 公开文档里的 API，且不渲染模板）、`/api/weather`（在 `/api/` 前缀下，Nginx 反代）、`feed.xml` / `sitemap.xml` / `robots.txt` / `feed/comments`。
- **SEO 现状（更正 v3.18.5 的表述）**：`/post/*` **有**聚合通道——Nginx 的 bot 规则会把匹配爬虫 UA 的请求改写为 `/api/og/post/<slug>`（服务端渲染 OG meta 的文章页），该通道不依赖已退役的 SSR 路由；但**只有 OG、没有 JSON-LD**，而 JSON-LD 原本只存在于已退役的 SSR 文章页 → **现在彻底没有了**。`/`、`/archive`、`/category/*`、`/tag/*`、`/about`、`/links` 仍是 SPA 空壳，**无任何服务端 meta**。
- **验证**：**119 passed**（112 基线 + 7 条新增 `tests/test_ssr_retirement.py`：8 个路径 410、endpoint 名守恒、认证页仍 200、机器接口仍 200、退役模板确已删除且认证/错误页未被误删）；`compileall` 通过。**无表结构变更、无新依赖、无新增环境变量、前端产物零变化**（前端未动）。
