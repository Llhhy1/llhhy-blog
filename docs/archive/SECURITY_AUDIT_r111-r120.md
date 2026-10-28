# 安全审计归档件 · R111 ~ R120

> **本文件是归档件**，自 `myblog/SECURITY_AUDIT.md` 拆分而来
> （v5.2.3 因体积守卫触发：主文件涨到 162 KB，上限 160 KB）。
> 覆盖 **R111（v3.25.13）~ R120（v4.3.0）**，正序排列，与主文件同一体例。
> 归档不是删除 —— 查这一段看本文件；主文件从 R121 起。
> 指针与契约见主文件头部与 `tests/test_doc_archival.py::PAIRS`。

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
