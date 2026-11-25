# CHANGELOG 历史归档件（v4.7.0 ~ v4.8.3）

> **归档件**：本文件是 `CHANGELOG.md` 的历史段落拆分快照，不是当前文档。
> **拆分点**：v5.14.0 发版时 CHANGELOG 主文件涨到 202 KB（上限 200 KB），按「新增版本写进主文件、最老一批历史段落才归档」搬出 v4.7.0 ~ v4.8.3（13 个版本段）。
> 近期版本请回主文件 `CHANGELOG.md` 顶部查看；本文件只保留历史，不再随版本更新。

---

## v4.8.3（2026-10-23）

把**部署前三查固化进 `update.sh`**：自动清理残留更新进程、自动对账并自更新脚本本身。
**应用代码无变更**（仅部署脚本 + 版本号）。

### 一、为什么改这个

v4.8.2 部署前撞上一个**跑了 6 小时的僵尸 `update.sh`**（ppid=1 孤儿，上次部署留下的），
人工核对了 `wchan` / fd 才敢杀。同时 `update.sh` **不在发布 zip 里**，线上脚本容易滞后，
过去每次部署都要人工比对「本地 update.sh sha256 == 线上」。这两件事现在脚本自己做。

### 二、新增 `⓪ 部署前三查`

| 检查 | 行为 |
|---|---|
| **残留 update.sh 进程** | 自动识别并清理。判据（安全优先，宁可拦住也不误杀）：<br>① 有**活着的父进程**且不是本进程祖先 → 判定为**真并发更新** → 终止本次；<br>② `ppid=1` 孤儿 + `wchan=do_wait`（在等 gunicorn、不持有下载文件、不写 `$APP_DIR`）→ **自动清理**（杀父不杀子，gunicorn 被 init 接管）；<br>③ 孤儿但 `wchan` 非 `do_wait`（可能停在下载/覆盖中段）→ **不猜**，报清 pid 与 wchan 后终止；确需清理设 `FORCE_CLEAN_STALE=1`；<br>④ `state=Z`（已退出等回收）→ 跳过，无害。 |
| **当前线上版本** | 启动即打印 `$APP_DIR/config.py` 里的版本，不必等查完 GitHub 才知道。 |
| **脚本自身哈希** | 与**同 tag 的 GitHub raw** 对账；不一致则备份旧版 → `bash -n` 校验 → 替换 → `exec` 重跑（带 `SELF_UPDATE_DONE` 防重入环）。 |

**精确判据（重要）**：只用 `pgrep -f "update[.]sh"` 粗筛会**误伤**——任何命令行里
*提到* "update.sh" 的进程都会中招（实测：MCP 的 `sh -c` 包装层、含该字样的脚本都会
导致合法更新被无谓拦截）。因此第二步必须读到 `/proc/<pid>/cmdline`，
**只有 argv 里存在 basename 恰为 `update.sh` 的参数**才算「在执行更新脚本」。

### 三、真机测试（4 个用例）

- ✅ 真孤儿 + `do_wait` → **被自动清理**，gunicorn 无恙
- ✅ 命令行只「提到」update.sh 的包装进程 → **不误拦**
- ✅ 无残留 → 直接放行
- ✅ 过程中 gunicorn master + workers 全程存活

> 测试还反向证明了一件事：把被测逻辑漏掉「祖先排除」时，测试脚本自己会被杀 ——
> 正是这个风险让 `update.sh` 里必须同时做**祖先链排除 + argv 精确判据**。

### 四、已知限制（如实记录）

自更新依赖能访问 `raw.githubusercontent.com`。**实测该域名在此服务器环境直连被重置**
（`Connection reset by peer`），需设 `GH_MIRROR`（走 gh-proxy 实测 200）才能自更新；
取不到时脚本只打日志提示并继续，**不影响本次更新本身**。可用 `SELF_UPDATE=0` 关闭自更新。

### 五、其他

- `SELF_UPDATE`（默认 1）：是否启用脚本自更新。
- `FORCE_CLEAN_STALE`（默认 0）：强制清理 `wchan` 非 `do_wait` 的孤儿残留进程。
- **无迁移、无表结构变更**（Alembic head 仍为 `c3d9e2f71a04`）。

## v4.8.2（2026-10-23）

修掉**文章管理页「批量管理」完全失效**（勾选、全选、执行全线失灵），并补齐
**中英文适配**：切到英文界面时「工具箱 / 百宝箱」不再停留在中文（审计轮次 R138）。

### 一、文章管理批量操作修复（两个叠加 bug）

**根因 1（功能全废）**：批量条 `<form id="bulk-form">` 在表格**之前就闭合**，
而行复选框在 `<table>` 里 → 复选框**全部落在表单外**。于是：

- JS 的 `form.querySelectorAll('.row-check')` **永远是空集合** → 全选失效、
  「已选 N 篇」永远为空；
- 提交时勾选数恒为 0 → **每次点「执行」都弹「请先勾选要操作的文章」并阻止提交**；
- 即便提交成功，`ids` 也一个都不在请求里。

⚠️ **不能**简单把表格包进表单：表格里每篇还嵌着「发布 / 申请置顶 / 删除」的 `<form>`，
包进来会造成**表单嵌套**（HTML 非法，浏览器会丢弃内层）。修法是给复选框加 HTML5 的
`form="bulk-form"` 属性做关联（与 `moments.html` 的 `form="moment-batch"` 同一约定），
并把 JS 查询改到 `document`。

**根因 2（连带）**：「分类」和「分区」两个下拉**都叫 `name="value"`**，后端
`request.form.get("value")` 只取第一个 → 即使勾选修好，**「移入分区」也永远拿到
「分类」的空值**而报「请选择目标」。修法：分别命名 `category_value` / `series_value`，
后端按 action 取（保留 `value` 兜底），同时把未启用的下拉 `disabled`。

### 二、中英文适配：切英文不再露中文

1. **「工具箱」按钮是硬编码中文**（`App.vue`，桌面 + 移动端两处），周围每一项都走
   `{{ t('...') }}` → 新增 `toolbox` 键并改用 `t('toolbox')`。
2. **工具箱条目名只有单语言 `label`**（存在 Setting 的 JSON 里）→ 新增可选
   `label_en`：只在既有 JSON 里加一个键，**不动表结构**（符合「能不改表就不改」）；
   英文界面优先取、没配则回退中文。后台「导航入口」页新增「英文名」输入框，
   `/api/site` 输出该字段。
3. **全局组件 i18n**（每页可见，优先级最高）：`Sidebar.vue` 侧栏 22 处、
   `WeatherWidget.vue` 天气卡 18 处（含天气代码 → 文案映射改为 `t("w_"+code)`）、
   `App.vue` 4 处（关闭按钮 aria-label、插件侧栏标题、在线人数）。
4. `t()` 扩展为支持占位变量（`t('stats_line', {p, c})`）—— 原来会把 `{p}` 原样吐到页面上。

### 三、验证

- `tests/test_admin_bulk_posts.py` 新增 8 项（5 个批量动作各测一遍 + 边界情况）；
  `tests/test_nav_entries_v4_1.py` 新增 8 项 i18n 守卫。
- **两处变异验证均实测变红**：摘掉 `form="bulk-form"` → 结构性测试红；
  后端改回 `get("value")` → 分类/分区两条红。i18n 守卫同样做了变异验证
  （把 `t('site_search')` 改回中文、从英文字典摘掉一个键，各自变红）。
- 全量 **1028 passed**，零回归；前端 `vite build` 通过，构建产物已含全部新键的中英文值。

### 四、刻意没做的

- **全站 i18n 是工程不是本版范围**：扫描前台共 **751 处**硬编码中文、涉及 34 个文件
  （其中 `DocsView.vue` 独占 227 处，属长篇文档内容而非 UI 文案）。本版只做了
  全局壳（Sidebar / WeatherWidget / App，约 44 处），剩余按页排优先级分批推进。
- 文章内嵌「目录」被挤成一大段链接：是**正文 markdown 写法**（连续单行 = 同一段落），
  非渲染 bug；改渲染器会影响全站所有文章并需 bump `_RENDER_VERSION`，未动。
- **无迁移、无表结构变更**（Alembic head 仍为 `c3d9e2f71a04`）。

## v4.8.1（2026-10-22）

内容迁移插件新增 **Typecho SQLite 数据库（`.db`）** 支持；发布前审计发现并修掉一个
SQL 标识符注入（审计轮次 R137）。

### 一、content_migrate 支持 Typecho SQLite 库文件

真实场景：Typecho 用 SQLite 存储引擎时，导出的是 `.db` 库文件本身，而 v4.8.0 只认
`.sql` 文本备份 —— 上传会直接报「无法识别格式」。

- 新增 `parse_typecho_sqlite()`：把上传字节落到临时文件，`file:...?mode=ro` **只读**打开，
  用完即删，**绝不写回原文件**；表前缀自动识别 `*_contents`。
- `parse_any()` 增加 SQLite 魔数嗅探（`SQLite format 3\0`），并按 `.db/.sqlite/.sqlite3`
  文件名给出兜底报错（非 SQLite 的 `.db` 会得到明确提示，而不是笼统的「无法识别」）。
- 抽出 `_typecho_build_post()`：`.sql` 与 `.db` 两条路径**共用同一套**正文 / 状态 / 密码
  判定（`<!--markdown-->` 前缀剥离、`<!--more-->` 清理、密码保护文章转草稿），
  避免两种 Typecho 导出行为漂移。
- 前台上传控件 `accept` 增加 `.db/.sqlite/.sqlite3`，预览标题改为
  「Typecho（SQL 备份 / SQLite）」；插件描述与 README 同步。

### 二、安全审计 R137：修掉 SQL 标识符注入（CWE-89）

⚠️ 初版把**从上传文件里读出的表名**直接 `"%s" % tbl` 拼进 SQL。表名完全不可信，
一个形如 `x" ; DROP TABLE post; --_contents` 的表名就能让引号突破出去 ——
变异验证显示：摘掉校验后 SQLite 把表名解析成了 `x`，抛出未捕获的
`sqlite3.OperationalError`（请求会变 500）。

- 新增 `_safe_ident()`：标识符只放行 `[A-Za-z0-9_]`，其余给出清晰报错（400 而非 500）。
- 配一条**变异验证过**的回归测试（摘掉校验必须变红，已实测）。

### 三、验证

- `test_content_migrate_plugin.py` **19 passed**（新增 7 项，含标识符注入守卫的变异验证）。
- lint 棘轮无新增债务。
- 对一份真实 Typecho + SQLite `.db`（139KB）做**只读 dry-run**：解析出 3 篇已发布文章、
  正确跳过 `关于` 页面、分类「默认分类」识别、`<!--markdown-->` 前缀剥离、时间戳正确。
  该 `.db` 全程只读、零改动。
- **无迁移、无表结构变更**（Alembic head 仍为 `c3d9e2f71a04`）。

### 四、刻意没做的

- **评论仍不迁移**（与 v4.8.0 一致）：本站 `Comment` 没有「原站用户 / 邮箱验证 / 层级」
  字段，硬导会变成无法追责的匿名文本。库里的 3 条评论不会进站。

## v4.8.0（2026-10-22）

新增**内容迁移插件**（PR #27）：把 WordPress / Typecho 旧站的文章搬进本系统。
同时带上两个依赖安全修复。

### 一、内容迁移插件 `content_migrate`

**默认不启用**（符合「装卸 = 发版 + 重启」的红线）。启用方式：

```bash
ENABLED_PLUGINS=content_migrate   # 重启 gunicorn 生效
```

后台入口：插件管理 → 内容迁移 → 打开（`/admin/migrate/`）。

| 能力 | 说明 |
|---|---|
| 输入 | WordPress **WXR**（`.xml`）、Typecho **SQL 备份**（`.sql`，表前缀自动识别，GBK/GB18030 兜底） |
| 导入 | 标题、正文、摘要、发布时间、分类（一篇只留第一个）、标签、特色图 |
| 图片 | 可选把正文 `<img src>` 与特色图下载到本站并重写地址 |
| 重复导入 | 保留 slug 时按 slug 去重；否则按「标题 + 创建时间」去重 |
| 不导入 | 页面、评论、用户/密码、附件库、主题与插件设置（预览里会计数） |

**不触发发布副作用**：迁移先以草稿落库，最后直接改 `published` 并补一次 FTS 同步 ——
否则迁 200 篇 = 给订阅者发 200 封信。

### 二、合并前审查发现并修掉的问题

1. 🔴 **导入选项全部失效**（真 bug，会让「下载正文图片」这个核心功能形同虚设）：
   前台用**原始字节流**提交文件（multipart 会被全局 5MB `MAX_CONTENT_LENGTH` 先截住），
   选项只能放在 **query string**；但路由从 `request.form` 读 →
   `publish` / `download_images` / `source_base` 三个选项**静默取默认值**。
   - 修法：新增 `_opt()`，query string 优先、`request.form` 兜底。
   - ⚠️ 原路由测试传的参数**恰好等于默认值**（`publish=source`、`preserve_slug=1`），
     所以一直是**假绿**。新测试一律用**非默认值**（`publish=draft`、`download_images=1`）。
   - 变异验证：把 `_opt` 改回只读 `request.form` → 两条新测试**都变红**（老测试仍绿）。
2. **插件 `admin_url` 未校验**：`admin_url` 会被渲染成 `href`，
   放任 `javascript:` / 协议相对 `//host/` 就等于给第三方插件包一个
   「点一下就在管理员上下文里跑脚本」的口子。加 `_safe_admin_url()`：
   只放行以 `/` 开头的站内相对路径。

### 三、安全边界（审计 R136）

| 面 | 处理 |
|---|---|
| 鉴权 | 所有路由 `@admin_required`；未登录 302/403 |
| CSRF | 全局中间件校验；非表单请求回落到 `X-CSRF-Token` 头 |
| 上传 | 64MB 上限（路由内 `request.max_content_length`）；解析前先嗅探格式 |
| XML | **拒绝带 `DOCTYPE` / `ENTITY` 的文档**（防 billion laughs 实体膨胀）；`ElementTree` 不解析外部实体 |
| SQL | **纯文本扫描，不执行任何语句**；只读 `contents` / `metas` / `relationships` 三张表 |
| 外站图片 | 一律走 `outbound.open_url()`（公网校验 + 固定 IP + 禁 3xx）；`Content-Type` 必须是 `image/*`；扩展名白名单（**SVG 一律不收**，XSS 面）；文件名用内容哈希（**无路径穿越**） |
| 资源 | 每次导入最多 200 张图、单张 5MB；单篇文章失败不中断整批 |

### 四、依赖

- `Pillow` >=10.0.0,<13.0.0 → **>=13.0.0,<14.0.0**（今日新披露的高危修复）
  —— 本地已装 13.0.0 实测：`Image.LANCZOS` 仍在，resize + WebP 编码 + 绘图均正常
- `vite` ^6.0.7 → **^6.4.5**（同批高危修复，仍在 v6 内，未跨大版本）

### 五、验证

**1004 passed**（新增插件 13 条 + 插件系统 1 条）；`ruff check .` 全绿；
lint 债务 471（基线 475）；**无迁移、无表结构变更**。

## v4.7.8（2026-10-21）

依赖升级（dependabot #20 #21 #22 #23）+ 由此引出的**渲染缓存版本号 bump**。

### 一、合并了什么

| PR | 内容 | CI |
|---|---|---|
| #20 | `@vitejs/plugin-vue` 5.2.4 → 6.0.10 | 全绿（含 build） |
| #21 | `markdown` 3.8.1 → 3.11.1、`feedparser` 6.0.11 → 6.0.14、`Flask-Migrate` 4.0.7 → 4.1.0 | 全绿 |
| #22 | `segno` >=1.6.6 | 全绿 |
| #23 | `redis` 4.5.0 → 8.1.0 | 全绿 |

未合并 **#19**（`vite` 6.4.3 → 8.3.4）：CI 的 `build` 任务**失败**，跨两个大版本构建不过，
已关闭并删除分支，等前端能过再处理。

### 二、为什么升级 markdown 必须 bump `_RENDER_VERSION`

`utils/render.py` 把正文渲染结果缓存进 `post.content_html`，失效判据是
`content_digest()` —— 指纹 = `sha256(渲染版本号 | 正文 | HTML)`，**只认这三项**。

markdown 库从 3.8.1 升到 3.11.1，渲染器实际变了，但指纹里没有任何「库版本」成分：
老文章缓存的 HTML 依然指纹匹配 → **继续吐旧库渲染的结果**，新文章用新库渲染。
两套结果静默混着，**不报错、不红测**，只有读者看到排版差异时才会被发现。

所以 `_RENDER_VERSION` 3 → 4，让全部历史缓存一次性失效重渲染。
棘轮测试 `test_render_allowlist_ratchet.py` 里的 `EXPECTED_RENDER_VERSION` 同步改。

> 这条纪律原本只写的是「改白名单要 bump」。**升级 markdown 库同样算「渲染器变了」** ——
> 已补进 `render.py` 的注释里。

### 三、上线注意

1. **无迁移**，head 仍为 `c3d9e2f71a04`。
2. ⚠️ 升级后**首次访问各文章会重新渲染**（缓存全部失效），长文有一次性开销；
   可通过 `tools/rebuild_fts.py` 之外的批量预热缓解，或直接接受首次慢一点。
3. 前端 `@vitejs/plugin-vue` 升到 6 需要**重新 `npm install` + `vite build`** 才生效；
   本机没有 npm，下次构建时自然会用新版本。
4. `redis` 升到 8.x：`utils/net.py` 只用到 `from_url` / `incr` / `expire`，
   且 `REDIS_URL` 是可选配置、全程 `try/except` 兜底 → 未启用 redis 的站点不受影响。

### 四、验证

990 passed；`ruff check .` 全绿；lint 债务 471（基线 475）。

## v4.7.7（2026-10-21）

**修 v4.7.6 引入的回归：测试与 CI 会往生产发真实心跳。**

### 一、发生了什么

v4.7.6 上线后 `GET /api/ecosystem/stats` 的 `total` 从 1 涨到 **6**。查 nginx 访问日志，
心跳来源有三个 IP：

| 来源 | 身份 | 次数 |
|---|---|---|
| `8.138.98.164` | 生产服务器自己（正常） | 若干 |
| `223.74.146.47` | **本机跑 pytest** | 7 |
| `20.98.135.189` | **GitHub Actions CI 跑 pytest**（Azure 出口段） | 3 |

上报的 url 里出现 `https://c-1e568c3f.example.com` 这种明显是测试数据的域名 ——
站点注册表被注入了 5 条假站点。

### 二、根因

三个条件叠在一起才出事，缺一个都不会发生：

1. v4.7.6 把默认值翻成「开」；
2. 新增了**真实**的 `DEFAULT_CENTER`（否则默认开启也发不出去）；
3. `tests/test_mcp_write.py:47` 用 `create_app()` **没关调度器** —— 它起的后台线程
   会调用 `report_heartbeat()`，于是真的打到生产。

conftest 的 `app` fixture 早就传了 `enable_scheduler=False`，但那个清理辅助函数是
另一条路径，漏了。

### 三、修法（两层）

1. **`ecosystem._is_test_runtime()` 护栏**：`report_heartbeat()` 在非 `force` 情况下，
   若处于 pytest（`PYTEST_CURRENT_TEST`）或 Flask `TESTING` 配置下，直接返回 False。
2. **`test_mcp_write.py` 改为 `create_app(enable_scheduler=False)`** —— 从源头不起线程。

护栏保留 `force=True` 通道给人工排障。

### 四、为什么这条必须钉死而不只是「以后注意」

「站点数」是这个功能唯一的产出数字。测试/CI 每跑一次就往里灌几条，
数字就再也不能信了 —— 而且**灌进去的是无法分辨真假的自报数据**。
所以加了两条测试：一条断言 pytest 里零出站，另一条**摘掉护栏后必须真的会发**
（证明护栏是唯一拦路者，不是假绿）。

### 五、线上处置

已清理生产注册表里的 5 条假站点，只保留官方站点那一行（`total=1`）。

### 六、验证

- 生态统计测试 **25 passed**（新增 2 条护栏测试）
- 修复后重跑 `tests/test_ecosystem.py`，生产行数**不再变化**（实测确认）

## v4.7.6（2026-10-20）

生态统计从 **opt-in（默认关）改为 opt-out（默认开，可关闭）**，并把「匿名」做成一条
真能走通的路径。

### 一、为什么改默认

v4.7.5 上线后的实际情况是：**默认关闭 = 永远统计不到**。新部署的实例要自己找到
「设置 → 🌐 生态统计」、理解这是干什么、手动打开并填中心地址，三步一步都不会发生。
而不上报这个功能就没有任何数据 —— 等于没做。

所以默认值从「关」改为「开」，**关闭入口原样保留**：取消勾选即真的一个请求都不发
（有测试钉死这一点）。告知是必要的，但不能替代选择权；这里把两者都留下了。

### 二、「默认开」必须内置默认中心，否则等于没开

`center_url()` 原来是「留空 = 不上报」。opt-in 默认开之后，留空就等于开关开着却不发。
新增 `ecosystem.DEFAULT_CENTER`（`https://www.llhhy.cn`），设置里留空即回退到它；
自部署者仍可填自己的中心（必须过 SSRF 公网白名单）。

⚠️ 代价是明确的：本项目的官方站点成了所有部署实例的遥测接收端，是**单点**。
`report_heartbeat()` 是 fail-silent 的，中心挂了只影响统计，不影响别人的站点运行。

### 三、匿名路径（原来是不成立的）

v4.7.5 里心跳无条件带 `url`。对个人博客来说 **URL 就是站主身份**，那不叫匿名。
现在拆成两层：

- **L1 计数**：随机 `site_key` + `version` + 时间戳 —— 始终发，无法反推是谁
- **L2 列出**：额外带 `url`，由「公开展示本站」控制

取消「公开展示本站」后，心跳**不带 url**，且**中心端会把已存的 url 清空** ——
只做「不展示」而不清库是假匿名（旧地址还躺在表里）。这条有测试钉死。

### 四、改动清单

- `ecosystem.py`：`opt_in()` 默认 `1`；`center_url()` 留空回退 `DEFAULT_CENTER`；
  `report_heartbeat()` 在 `listed=0` 时不带 url；`receive_heartbeat()` 在
  `listed=0` 时清空已存 url
- `admin/settings.py` + 设置页：开关文案改为「默认开启，可随时关闭」，
  并把两条关闭路径（停止上报 / 改为匿名）写清楚；中心地址输入框显示默认中心
- 新增 3 条测试（默认开启、取消后零出站、匿名心跳不带 url + 中心端遗忘），共 23 条

### 五、上线注意

1. 已部署的站点**不受影响**：Setting 里已有的值不会被默认值覆盖。
2. 生态统计现在**默认就会上报** —— 不想参与的站点需要去设置页取消勾选。
3. 无迁移（本版不碰表结构）。

## v4.7.5（2026-10-20）

把「**有多少人在用本系统部署上线**」和「**当前有多少人在浏览**」这两件事
做出来 —— 前者是跨站点的（需要部署实例自愿上报），后者是站内的（数据早已存在）。

### 一、生态统计：使用本系统的站点注册表

**为什么必须有它**：GitHub 侧只能看到 **fork 派生关系**（实测本仓库 fork=1、star=2），
而绝大多数使用者是 `git clone` 完自己改的 —— GitHub 完全看不见他们。
想知道真实使用量，只有���条路：**由部署实例主动上报**。

**设计上的硬约束**（这个功能能不能被接受，全看这几条）：

- **默认关闭**。设置项 `ecosystem_opt_in` 默认关，不开就一个请求都不发 ——
  未经告知的遥测会直接毁掉开源项目的信任。
- **上报内容严格受限**：只有 `site_key`（随机安装 ID）、`url`、`version`、时间戳四项。
  **绝不包含任何访客数据、文章内容、账号信息。**
- **站点可以拒绝被列出**（`ecosystem_listed`）：只计数、不公开 URL。
- **中心地址必须是公网**（过 SSRF 白名单）—— 否则这个设置会变成
  「让服务器去请求任意地址」的内网探测后门。
- **心跳数据是自报的**，任何人都能伪造 → 前台展示时如实标注，不宣称权威。
- **不做 URL 可达性验证** —— 那是 SSRF。

**机制**：

| 端点 | 作用 | 防护 |
|---|---|---|
| `POST /api/ecosystem/heartbeat` | 部署实例向中心发心跳 | 限流 30/min；`site_key` 必须 16~64 位十六进制；payload 只认 4 个白名单字段 |
| `GET /api/ecosystem/stats` | 站点注册表统计 | 限流 60/min |

- 新增表 `ecosystem_site`（7 列，幂等迁移 `c3d9e2f71a04`）
- 调度器**每小时**发一次心跳（挂在既有定时发布线程里，失败静默）
- 后台「设置」页新增：参与开关 / 中心地址 / 是否公开展示

**为什么心跳端点要豁免 CSRF**：上报方是**后台定时任务**，它没有用户会话、
也就没有 CSRF token —— 不豁免就永远发不出去。这里的防滥用改由
「限流 + 随机 site_key + 字段白名单」三件事承担。

### 二、前台展示

- **页脚**：「👥 N 人正在浏览」（近 10 分钟独立 IP 数，每 60 秒刷新，
  页面隐藏时跳过）。放在页脚而不是首页 —— 首页首屏是壁纸层，文字颜色要单独适配；
  页脚明暗主题都自适应。
- **「关于」页**新增「🌐 生态」区块：当前在线访客数、已知站点总数、
  过去 24 小时活跃站点数，以及愿意公开的站点列表（带版本号）。
  站点地址是**自报**的 → 前端再过一遍 http/https 白名单才渲染成链接。

### 三、公开的在线数接口

新增 `GET /api/stats/online`。数据本来就存在（`stats.compute_online()`），
只是前台一直没露出来。

⚠️ 单独开这个端点，而不是塞进 `/api/stats/dashboard`：后者成本高
（referrers / trend / 聚合），不该被高频轮询，且**需要登录**，
而「当前在线」是要公开给访客看的。

⚠️ **它是近似值**：本项目没有会话表，只能按 VisitLog 的独立 IP 推算
（NAT / 换网络会重复计数，短时无请求会漏掉）。接口返回 `approx: true`，
前端文案也如实写「近 10 分钟独立访客数」。

### 四、验证

- 全量 **985 passed**（新增生态统计 20 条）
- 迁移**双场景**验证：空库 `upgrade` 到 `c3d9e2f71a04`；已 `create_all` 的库
  先 `stamp b8e4f1a72c93` 再 `upgrade` —— 表与两个索引均存在且未重复创建
- `ruff check .` 全绿；`lint_debt.py` 无新增

### 五、上线注意

1. ⚠️ **新迁移 head = `c3d9e2f71a04`**（原 `b8e4f1a72c93`）→ 部署走
   `flask db upgrade`，**不要 `stamp head`**。
2. 本版**新增一张表**（`ecosystem_site`）—— 这是本项目少有的「加表」决定：
   需要「每站点一行 + 最后心跳时间 + 按时间范围查活跃数」，
   `log_audit` 是追加写的日志表，**承担不了去重与聚合**。
3. 生态统计**默认关闭**，上线后需在「设置 → 生态统计」里手动开启并填中心地址。

## v4.7.4（2026-10-20）

两件事：出站请求层**根治 DNS rebinding** + 壁纸**直接引用媒体库已有文件**。

### 一、出站统一层 + IP pinning（根治 DNS rebinding）

v4.7.3 建立的 `myblog/outbound.py` 统一了 SSRF 判据，但**只统一了一半**：
`feed_agg` 仍自带一份 `_NoRedirect` 和一份私网判断，`seo_push` / `oauth` 各有各的
`NoRedirect` —— 口径漂移，改一处漏三处。更关键的是**判据通过了不等于请求安全**：

```python
# outbound.py（v4.7.3）
ips = {info[4][0] for info in infos}
return all(not is_private_ip(ip) for ip in ips)   # ← 算完就扔，只留一个 bool
```

被校验过的那组 IP **没有传给后续的请求**。调用方随后 `opener.open(url)` 时
HTTP 客户端会**再解析一次 DNS** —— 两次独立解析之间，攻击者可以把 DNS 改指
回环/内网（DNS rebinding）。这是典型的「检查-使用时」竞态，
**重复校验无法消除**，只有把已校验的 IP **固定下来**才行。

本版的做法：

- `outbound.resolve_public_ex()`：**一次解析**同时给出「能不能放行」和「用哪个 IP」——
  校验与固定必须用**同一次解析**，否则「校验的是 A、固定的是 B」更糟。
- `outbound.open_url()`：校验 → **把 IP 固定在连接上** → 禁跟随 3xx。
  TCP 连的是已验证的 IP，但 HTTP `Host` 头与 TLS SNI **仍用原域名**
  （否则虚拟主机与证书校验都失效）。
- `outbound.read_limited()`：限响应体大小，避免 `resp.read()` 把内存吃光。
- `outbound.check_public_url()`：给人看的「为什么被拒」，判据与放行**同一份**
  （`_check()` 是唯一实现）。

**出口收敛**：

| 出口 | URL 来源 | 改动 |
|---|---|---|
| `feed_agg`（友链 RSS） | 管理员可配 | 删自带 `_NoRedirect` + 私网判断；改走 `open_url`，**一次解析**同时拿原因与 IP |
| `games`（LLM 审计） | 管理员可配（本就要求公网） | `_open_llm` 改走 `open_url`，获得 pinning |
| `seo_push` | 固定 API + 自己的业务白名单 | 删自带 `_NoRedirect`，改用统一的 opener（业务白名单保留在本模块） |
| `api/ai`（LLM 摘要） | 管理员可配，**可能是内网自建** | 改用统一 opener（禁 3xx），**刻意不套私网过滤** |

> ⚠️ `api/ai` 的例外是有理由的：LLM base 由管理员自己配，很多人指向本机自建
> （Ollama / vLLM 在 `127.0.0.1`）。私网过滤是给「URL 不可信」的场景用的，
> 套上去会把「本地自建 LLM」这种正当用法打死。**禁 3xx 仍然必要**。

> ⚠️ **pinning 在走代理时无效**（目标 IP 由代理解析），故统一 opener 显式装
> 空的 `ProxyHandler({})` 禁掉环境代理。

### 二、壁纸直接引用媒体库已有文件

壁纸配置**本来就存路径引用**（`/static/uploads/<name>`），媒体库文件也在同一个
命名空间里 —— 所以「从媒体库选一张当壁纸」在数据模型上**零障碍**，缺的只是入口。

- **主题中心**新增「📁 从媒体库选」：列出媒体库，点图即填入对应槽位
- **媒体库页**新增「设为壁纸」：在素材旁边直接用（**仅超管**可见 ——
  写壁纸走 `/api/theme`，那边要求 `is_super`，而媒体库页是管理员可进）
- 两个入口都**不需要重新上传**

**引入引用就必须处理引用生命周期**：媒体库的文件是可以被删的，删掉正在当壁纸
用的那张，首屏 `background-image` 会直接 404。

- `api/theme.wallpaper_uses()`：判定某文件是否正被壁纸引用（放在壁纸的 owner
  模块里，单一真相源）
- `admin/media.delete_media_core()`：正在被壁纸引用的文件**拒绝删除**，
  提示先去主题中心换壁纸
  （⚠️ 这里**故意 fail-open** —— 检查挂了不该让管理员完全删不了文件；
  误放行的后果只是壁纸裂图，不是安全问题）

### 三、验证

- 全量 **965 passed**（新增 pinning 实测 12 条 + 壁纸引用 16 条）
- `ruff check .` 全绿；`lint_debt.py` 无新增
- **pinning 是实测出来的，不是读代码读出来的**：`getaddrinfo` 被 mock 成
  「域名被解析第二次就失败」，只要出站路径上又用域名解析了一次，测试立刻红。
  另有一个用「重新解析会得到别的 IP」的 mock 从结果侧证明连的是被 pin 的那个。

## v4.7.3（2026-10-20）

全量审计的**代码批次**：发布阻塞、安全/健壮性、文档/测试一致性三批一次落地
（PR #24，分支 `fix/v4.7.3-audit-batch`）。

> **批次 1（生产升级操作）单独执行**：本版只交付代码与运维自动化文档。
> 历史库的隐私/回收站正文不会因写入闸门收紧而自动消失，需要时显式跑
> `BLOG_REBUILD_FTS=1 bash update.sh` 或 `tools/rebuild_fts.py`。

### 发布阻塞

- `gamify.award()`：`PointLog` 的 `add()` 移入 `try`。原实现中随后的 `UPDATE` 会
  autoflush 待插入行，`IntegrityError` 在 `try` 之外抛出 —— 积分事件失败会冒泡成 500。
- `api/site.py`：去掉 RET504 的中间变量，`ruff check .` 恢复 0。
- 前端依赖：`vue` 3.5.13 → 3.5.44、`dompurify` 3.2.4 → 3.4.17，`package-lock.json` 同步。
- 测试可移植性：`test_cert_watch` 改用 `cryptography` 生成证书（Ubuntu OpenSSL 3.0
  不支持 `-not_before/-not_after`）；`test_seo_push` 的重定向桩补齐请求体读取与
  `Content-Length`，消除 Windows `WinError 10053`。

### 安全

- **SSRF（管理员级）**：新增 `myblog/outbound.py`，统一「http/https + 公网解析 +
  禁 URL 凭据 + 禁跟随 3xx」。游戏 LLM 审计在保存与出站前各校验一次，响应体限 1MB。
  此前公网 Base 可 302 到内网，或直接配置回环地址。
- **SSRF（匿名面）**：`feed_agg` 删除重复实现，复用 `outbound` 的同一判据。
- **zip 炸弹**：`games_safety.unpack_zip_safely()` 在 `zf.read()` **之前**按中央目录的
  `file_size` / `compress_size` 拒绝单文件超限与压缩比 > 200 的条目；游戏上传按请求
  覆盖 `max_content_length`，使 20MB 上限真正生效。
- **手动黑名单**：`check_bot_guard()` 把黑名单检查提到 `_SKIP_PREFIXES` 之前，并在
  `api_bp` 注册钩子；被拉黑 IP 现在访问 `/api/stats/visit` 等接口也会 429。
  `/admin/`、`/mcp` 保留豁免，避免管理员把自己锁死。

### 性能与一致性

- 新增幂等迁移 `b8e4f1a72c93`：`ix_post_visibility_created`
  （published/in_trash/is_private/created_at）与 `ix_comment_post_approved`
  （post_id/approved）。空库升级与「`create_all()` 已建索引」两种场景均验证不重复创建。
- 移动端文章列表的 `comment_count` 改为当前页一次 `GROUP BY`，去掉逐行
  `p.comments.count()` 的 N+1；详情接口保持原回退路径。
- 移动端撤回权限由「仅管理员」改为 `_can_edit_post()`，普通作者可撤回自己的文章，
  与桌面端批量操作一致。
- 移动端置顶改为必须显式传 `pinned`；缺字段返回 400，不再静默取消置顶。
- 移动端上传文件名改用 `time.time_ns()`，同秒多文件不再互相覆盖。

### 运维与文档

- `update.sh` 新增 `BLOG_REBUILD_FTS=1` 可选步骤：迁移成功、服务重启后重建 FTS；
  失败只告警，不回滚已启动站点。**默认行为与旧版完全一致。**
- `deploy_guide.md` 移除 `flask db stamp head` 建议（会跳过实际列/索引变更，形成
  「版本号已升级、表结构没变」的假升级），改为 `flask db current` + `flask db upgrade`。
- `tests/conftest.py` 的测试库改为每轮 `mkdtemp`，两个 pytest 并行不再互相清库。

### 验证

- 全量 **936 passed**（含新增 SSRF / zip / 黑名单 / 移动端权限用例）
- `ruff check .` 全绿；`lint_debt.py` 473（基线 475，无新增）
- `pip-audit` 无已知漏洞；`npm audit --audit-level=high` 0 vulnerabilities
- Alembic 临时库双场景验证：空库 `upgrade` 到 `b8e4f1a72c93`；已 `create_all` 的库先
  `stamp a7e3c92d5b18` 再 `upgrade`，两个索引均存在且未重复创建

### 上线注意

1. 新迁移 head 为 **`b8e4f1a72c93`**（原 `a7e3c92d5b18`）。部署执行 `flask db upgrade`，
   **不要 `stamp head`**。
2. `update.sh` 本版有改动（`BLOG_REBUILD_FTS`），**不在 `myblog-backend.zip` 内**，
   需在服务器上单独覆盖。
3. 前端依赖已变更，须先 `npm ci` 再重新 build 出包。

## v4.7.2（2026-10-19）

修 v4.7.1 遗留的一处漏改：满屏壁纸下，顶栏「⋯ 更多」「🧰 工具箱」**深色按钮压在
亮色壁纸上几乎看不清**（用户报障）。

### 根因：v4.7.1 把选择器收窄时，只想到了一种元素

v4.7.1 修「下拉菜单白字压浅底」时，把壁纸模式的白字规则从 `nav a`（后代选择器，
会误染下拉浮层）收窄成 `nav > a`：

```css
:root:has(.home-cover.has-wall) .site-header > .container > nav > a { color: #fff; }
```

**但顶栏不全是 `<a>`** —— 「⋯ 更多」和「🧰 工具箱」是
`<button class="site-toolbox-toggle">`。它们不匹配 `> a`，于是被收窄的规则一并漏掉，
保持 `color: var(--nav-fg)`（深色）压在壁纸上。

也就是说 v4.7.1 那次「收窄」是**按元素类型逐个排查漏掉的**——改了 `<a>` 却没数一遍
顶栏里到底还有哪几种元素。

### 修法

把按钮用 `.site-toolbox-toggle` 精确补进同一条规则（而不是退回宽泛的后代选择器）：

```css
:root:has(.home-cover.has-wall) .site-header > .container > nav > a,
:root:has(.home-cover.has-wall) .site-header .site-toolbox-toggle { color: #fff; }
```

下拉浮层里的条目是 `.toolbox-menu a`，与 `.site-toolbox-toggle` 互不重叠，
所以**既能染白顶栏按钮，又不会重新引入 v4.7.1 那个「白字压浅底」**。
`.is-solid`（滚过首屏变实心条）的恢复规则同步补上。

### 验证

playwright 实测（computed color，非肉眼估计）：

```
moreColor(壁纸模式)=rgb(255,255,255)  moreShadow=rgba(0,0,0,0.38)  logoColor=rgb(255,255,255)
headerSolid=1  moreColor(实心条)=rgb(85,85,85)
```

即：壁纸模式下按钮与 logo、其余导航项同为白色并带暗投影；滚过首屏后恢复主题本色。

### 范围

纯 CSS，改动文件仅 `vue-frontend/src/styles/global.css`（+ 文档与版本号）。
**无表结构变更、无后端代码改动、无新依赖。**

## v4.7.1（2026-10-19）

修 v4.7.0 新增的「⋯ 更多」下拉**完全无法使用**。两个叠加的问题，都在真实浏览器里
模拟指针路径才暴露出来 —— 静态截图看不出「鼠标移过去」这一步。

### 一、菜单一碰就关（用户报障）

菜单用 `margin: 6px 0 0` 撑出视觉间隙，但**这段间隙不属于容器**
（`.nav-toolbox` 的高度只到按钮，菜单是 `position:absolute`）。鼠标从按钮往下
穿过间隙时，容器触发 `mouseleave` → 菜单关闭。而 **`mouseleave` 是不可逆的**
（不像 `mouseenter` 能再次触发回来），所以菜单一关，用户再也回不去 ——
「点开之后鼠标一离开就没了，我怎么选择菜单」。

- CSS：`margin: 6px 0 0` → `margin: 0`，视觉间隙改由菜单自身的 `padding: 6px 0` 提供，
  容器与菜单恢复连续，指针路径全程在容器内
- JS：补 `@mouseenter` 作为第二条打开路径

### 二、开关语义打架（我自己引入的）

加上 `mouseenter` 后立刻出现新问题：鼠标移上去已经打开，**再点击时 `@click`
的 toggle 把它关掉** —— 用户看到「点一下开了、又点一下没了」，比原 bug 更迷惑。
（这个问题是写完 `@mouseenter` 后用 playwright 跑指针路径才暴露的。）

把开关从「取反」改成**幂等的「确保打开」**：

```js
const openMore = () => { moreOpen.value = true; };   // 不再 !value
```

配合 `@keydown.esc="closeMore"` 保留键盘可达性（打开后仍可关闭）。

### 三、下拉菜单白字压浅底（截图才发现）

壁纸模式下顶栏链接被染白的那条规则写的是 `nav a`（后代选择器），**连下拉浮层里的
链接一起染了** —— 而浮层是 `background: var(--surface-2)` 的浅色卡片，
白字压浅底几乎看不见。

改成 `> .container > nav > a`，**只命中顶栏直接子项**；`.is-solid` 变实心条后的
恢复规则同步限定，否则滚过首屏又会退回白字。

### 验证（playwright 真实指针路径，非静态截图）

```
hover=1 | afterClick=1 | movedIntoMenu=1 | atItem=1 | url=/series
opened=1 | afterMouseLeaveFar=0 | reopenByHover=1
linkColor=rgb(85,85,85) | menuBg=rgb(251,238,243) | headerSolid=1
```

即：悬停开 → 点击不关 → 移入菜单不关 → 移到菜单项不关 → 点击跳转成功；
移远正常关闭 → 移回能重新打开（这正是原 bug 不可逆的那一环）；下拉文字为深灰，
与浅底对比度约 7:1。

### 范围

纯前端，**无表结构变更、无后端代码改动**。改动文件仅
`vue-frontend/src/App.vue`、`vue-frontend/src/styles/global.css`。

## v4.7.0（2026-10-19）

### 一、首页瘦身：概览卡与社交墙移入「运营驾驶舱」

满屏壁纸首屏之后立刻堆六张数据卡 + 一排社交入口，视觉噪声大于信息量；
且首屏壁纸里已有联系方式图标，与「找到我」一栏**内容重复**。

- 移除首页 `.bento`（文章 / 累计阅读 / 分类 / 标签 / 友链 / 评论六卡）
- 移除首页 `.home-social`（「找到我」社交墙）
- 两者内容移入 `/stats` 新增的「🏷️ 站点概览」区块
- 首屏的 `.home-cover-social` 联系方式图标**保留**（那是 v4.5.0 的需求）

⚠️ `.bento` / `.home-social` 的样式已随之删除 —— 内容去了新地方，留着就是死代码。
社交账号的加载逻辑（`loadSocials` / `socials`）**必须保留**，首屏图标依赖它。

### 二、开站时间（新增）

后端此前**完全没有**这个数据（全仓搜 `site_since` / `开站` / `建站` 零命中）。

- `/api/site` 新增 `site_since`（`YYYY-MM-DD`）
- **优先取后台配置的 `site_since`**；未配置时回退到**最早一篇可见文章的发布时间**
- 后台「设置」页新增日期输入框（存 Setting KV，**零表结构变更**）
- 只取**可见**文章 —— 不可见的草稿时间更早，用它会把开站日期算早

> 回退值只是**近似值**：第一篇文章未必等于建站日（可能先写草稿、换过域名、迁移过旧站）。
> 所以后台留了手工覆盖入口。前台据此显示「已运行 3 年 2 个月」。

### 三、前台顶栏瘦身（修英文模式溢出）

顶栏原有 **13 项**，每项 `margin-left:18px` + emoji + gap ≈ 91px，英文下约需 **1550px**
—— 1440 屏装不下，切换英文必然溢出。

- 保留 **7 项**高频入口：首页 / 归档 / 统计 / 热门标签 / 友链 / 广场 / 留言墙
- 站内次要页（系列 / 文档 / 关于 / 社交 / 游戏）收进「⋯ 更多」下拉
- **「回顾」不再单列** —— `/annual` 的核心内容（月度发文 / 最热文章 / 高频标签）
  已并入 `/stats` 的「📅 年度回顾」区块，带**年份切换器**
  （`/api/review/annual` 本就支持 `?year=`，响应里带 `years[]`）
- `/annual` 路由**保留可直达**（含访客地图，本区块未搬），年度回顾区块底部给入口
- 移动端抽屉**仍平铺全部入口**（竖向空间充足，不受英文长度影响）

⚠️ **外站「🧰 工具箱」是另一回事，未合并**：它的条目是外部域名，必须带
`target=_blank` + `rel="noopener`，`tests/test_nav_entries_v4_1.py` 守着这条契约。
「更多」里的站内链接刻意用 `.more-link` 而非 `.site-entry-link`，
避免被外链守卫判为不合规。

### 四、修后台表格「文字超出单元格」

**根因不在某一列，而在一条全局规则**：

```css
.admin-table td { white-space: nowrap; }   /* admin.css:152 */
```

为了让短列不换行、保持行高一致设的 `nowrap`，对**长文本列是致命的** ——
URL / 路径 / 文章标题这类无空格长串在 `nowrap` 下永不换行，直接撑破单元格。

而此前 `.vl-path { max-width: 280px }` 在 `display: table-cell` 上
**根本不生效**（CSS 规范如此）—— 这正是「设了上限却还是溢出」的原因：
上限从来没起作用过；同行的 `word-break` 又被 `nowrap` 压制。三重冲突。

修法：

- `.admin-table td.vl-path / .cell-wrap` → `white-space: normal` + `overflow-wrap: anywhere`
- 新增 `.cell-break` 供整串无空格的内容（纯 URL）用 `word-break: break-all`
- `.stats-table td / .rank-table td` 补 `overflow-wrap: anywhere; min-width: 0`
- 删除无效的 `max-width` 以免误导后人

⚠️ 刻意**不用** `table-layout: fixed`：它会把「路径 / 次数」两列强行均分成 50/50，
数值列被撑得和长 URL 一样宽，比溢出更难看。

移动端不受影响 —— `@media` 内的卡片化已把 td 变成 `display:block` + `white-space: normal`。

### 五、验证

- 全量 **902 passed**
- `vite build` 通过，产物逐项 grep（bento/home-social 已归零、`site_since`、
  `review/annual`、`nav-more`、`/annual` 在顶栏消失但抽屉保留）
- **测试门禁抓到一个我自己造的破坏**：曾把 `site-entry-link`（语义＝外域链接）
  给了站内 `router-link`，被 `test_nav_entries_v4_1` 与 `test_site_entry_v4` 拦下 —— 已拆成两类

