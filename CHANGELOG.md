# 更新日志（CHANGELOG）

> **📦 历史归档**：v3.18.5 及以前 → `docs/archive/CHANGELOG_v1-v3.18.5.md`；
> v3.18.6 ~ v3.19.2 → `docs/archive/CHANGELOG_v3.18.6-v3.19.2.md`（v4.7.0 因体积守卫触发，按「新增轮次写进主文件、历史段落才归档」搬出）。
> 本文件从 v3.20.0 起。**归档不是删除** —— 查旧版本变更细节时去上述文件。

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

## v4.6.1（2026-10-19）

### 修：壁纸被整站外框「套住」，首屏其实没铺满

v4.6.0 把 `.home-cover` 改成 `100svh`，但**漏掉了它外面还有一层框**。
`.site-frame`（v3.1.0 的整站大框）是：

```css
max-width: 1100px;  margin: 22px auto 28px;
padding: 0 16px;    border: 1px solid #e6e8eb;
border-radius: var(--theme-radius, 12px);  overflow: hidden;
```

首页内容在这个框里，于是壁纸：左右被 padding 挤窄、顶部被 margin 压出一条白边、
四角被圆角裁掉 —— 就是用户看到的「被一个框套住」。参考站 Butterfly **没有这层框**
（body 直接到 header），所以它的 `height:100vh` 才是真的。

线上实测截图确认：1440×900 下壁纸只占中间约 1100px，顶部有 22px 白条，
移动端左右各露一条白边。

**修法**：在「首页 + 已配壁纸」时把外框整体放开。

```css
:root:has(.home-cover.has-wall) .site-frame {
  max-width: none; margin: 0; padding: 0;
  background: transparent; border: 0; border-radius: 0;
  overflow: visible; box-shadow: none;
}
```

破框后下方内容会失去限宽（`.bento` / `.content` / `.home-social` 本身都没有
`max-width`），所以给首页根节点挂 `.home-page`，用
`.home-page > *:not(.home-cover) { max-width: 1066px; margin-inline: auto }`
把非首屏区块重新限宽居中（1066 = 1100 − 16×2 − 1×2，即原框内的可用宽度）。

未配置壁纸时 `:has()` 不命中，外框照旧，**零影响**。

### 修：文字阴影只有一层大扩散，亮色壁纸上照样发糊

原 `text-shadow: 0 2px 18px rgba(0,0,0,.32)` —— 18px 的扩散看着像光晕，
实际不提供锐利暗边。改成「近锐 + 远柔」双层：

- `0 1px 2px rgba(0,0,0,.55)`：把字边缘切出来
- `0 6px 28px rgba(0,0,0,.45)`：与背景分离

### 修：顶栏渐变不该跟着遮罩滑块一路降到 0

v4.6.0 让 `--wall-veil-top = overlay × 0.7`，本意是「遮罩淡则顶栏也淡」。
实测问题相反：顶栏是**白字**，遮罩调淡后导航项先糊。加下限：

```js
Math.max(0.28, overlay * 0.7)
```

### 验证方式（本版的关键）

前几版都是「构建通过 + 产物 grep」就算过，**这次用户实际看到的是错的**。
本版改用 `playwright-cli` 对**线上真实页面**取证：

1. 先截「修复前」线上图 —— 复现了框、白边、遮罩过重三个现象
2. 用 `page.evaluate` 把修复 CSS **注入线上页面**（不动线上文件），截图验证
3. 分别验桌面 1440×900 / 移动 390×844 / 滚动后（`.is-solid`）/ 遮罩 0.15 四种状态
4. 确认无误后才发版

> 教训：**「代码写了」「构建过了」都不等于「用户看到的是对的」**。
> 有浏览器可用时，视觉改动必须以真实截图为准。

### 范围

纯前端，**无表结构变更、无后端代码改动、无新依赖**。
改动文件仅 `vue-frontend/src/styles/global.css`、`vue-frontend/src/views/HomeView.vue`。

## v4.6.0（2026-10-19）

### 一、首页首屏：壁纸真正铺满整个屏幕

v4.5.0 把壁纸做出来了，但它**并没有真的占满屏幕** —— 首屏高度写的是
`calc(100vh - 58px)`，那个 `58px` 是当初为了给顶栏留位减掉的，视觉上就是
「壁纸从导航栏下面开始」。本版参照 [DeepChirp](https://blog.deepchirp.com/)
（Hexo + Butterfly 5.7.0）的做法重做，实测其 CSS 为：

```css
#page-header.full_page            { height: 100vh; background-attachment: fixed; }
#page-header.full_page #site-info { position: absolute; top: 43%; width: 100%; }
```

改动五处：

| 项 | 原 | 现 | 理由 |
|---|---|---|---|
| 首屏高度 | `calc(100vh - 58px)` | **`100svh`** | 原来扣掉顶栏不满屏。用 `svh` 而非照抄 `vh` —— 移动端地址栏收放会让 `vh` 跳动 |
| 背景 | 无 | **`background-attachment: fixed`**（仅 ≥641px） | 滚动时壁纸停在视口、内容掠过，产生纵深。移动端每帧重绘大图代价高；iOS Safari 对 fixed 另有支持缺陷，用 `@supports (-webkit-touch-callout: none)` 回退 |
| 文字位置 | flex 居中 50% | **`top: 43%` + `translateY(-50%)`** | 几何正中偏上是封面构图的稳态位置 |
| 滚动提示 | 跟在标题下面（`margin-top: 32px`） | **移出文字流，贴视口底部 `bottom: 18px`** | 不再随标题位置漂 |
| 顶栏 | `sticky`、不透明、占 58px 文档流 | **浮在壁上，滚过首屏变实心固定条** | 壁纸要能顶到屏幕最上沿，顶栏就不能占位 |

### 二、顶栏为什么能浮起来

顶栏独立于首屏（DeepChirp 是把 nav 塞进大图 header 里，天然浮在图上），
所以要靠两条机制接上：

- **位置与透明度交给纯 CSS**：`:root:has(.home-cover.has-wall) .site-header { position: fixed; … }`。
  选 `:has()` 而不是 JS 切 body 类 —— 路由切走后条件**自动失效**，
  不存在「切走了忘清理」的中间态，也不引入生命周期管理。
- **「滚过去了没」交给 `IntersectionObserver`**（threshold 0），不用 `scroll` 事件：
  这个 `100svh` 元素整页生命周期里进出视口最多两次，`scroll` 是每帧回调。
  命中后给顶栏加 `.is-solid` 恢复主题本色 + 毛玻璃；`onBeforeUnmount` 里
  `disconnect()` 并清掉 `.is-solid`。

不配壁纸时 `:has()` 不命中，顶栏保持原样，**未启用壁纸的站点零影响**。

### 三、一处自查出的真 bug（已修）

顶栏浮到壁上之后，它**不在 `.home-cover` 的 `background-image` 里**，拿不到那层遮罩，
白字会直接压在亮色壁纸上。补了一条顶部渐变，强度与后台遮罩滑块联动 ——
但第一次实现把 `--wall-veil-top` 放进了 `coverStyle`（inline style 打在 `.home-cover` 上），
而 **CSS 自定义属性只向下继承**，`.site-header` 是它的兄弟节点，永远拿不到，
只会命中 fallback 常量 → **滑块联动是假的**。

改为挂在 `:root` 并在 `onBeforeUnmount` 里 `removeProperty`，避免把首页专用的渐变
留在全局污染其他页面。

### 四、刻意不照搬的两处

- **不删遮罩层**。DeepChirp 没有遮罩，纯靠 `text-shadow` 撑可读性，因为他的
  `banner.avif` 是自己做的暗色设计图；我们的壁纸是后台上传的任意图，
  白底壁纸上白字会瞎 —— 后台那个遮罩强度滑块保留。
- **不隐藏社交图标**。DeepChirp 桌面端 `#site_social_icons` 是 `display:none`
  （靠侧边栏显示联系方式），本站首屏图标是明确需求，保留。

### 五、本版范围

纯前端，**无表结构变更、无后端代码改动、无新依赖**。改动文件仅两个：
`vue-frontend/src/styles/global.css`、`vue-frontend/src/views/HomeView.vue`。

## v4.5.0（2026-10-18）

### 一、访客数据：平均阅读时间（全链路，此前零数据）

后台「访问统计」新增**平均单次阅读时长**卡片。之所以是「全链路」而非加个显示：
**此前根本没有任何时长数据** —— `ReadLog`/`VisitLog` 都无时长字段，前端
`visibilitychange` / `sendBeacon` 全目录 0 命中。

- `ReadLog` 新增 `duration`（秒，累计）+ Alembic 迁移 `a7e3c92d5b18`
- 前端在 `visibilitychange`(hidden) / `pagehide` / 组件卸载 / 切换文章时补报停留秒数
- 后台统计页展示「X 分 Y 秒」

四处必须处理的边界，每一个都有对应的失败方式：

| 陷阱 | 不处理的后果 | 本版做法 |
|---|---|---|
| `duration` 由客户端上报 | 一个 `{"duration":999999}` 就能把平均值抬到任意值 | 钳制到 `[0, 7200]` 秒 |
| 时长复用 `/api/stats/read` 入口 | 停留时长会**多次补报**，读一次被记成两三次，热门文章榜与「反复阅读」榜双双虚高 | 用 `only_duration` 开关分流到独立的 `add_read_duration()`（不动 `read_count`） |
| 分母用 `COUNT(*)` | `ReadLog` 一行 = 「一个访客对一篇的累计」，行数是访客数，均值被压到 1/N | 分母用 `SUM(read_count)` |
| `duration = 0` 的历史行进分母 | 升级前全是 0，「人均阅读时长」刚上线就是 0.3 秒 | 只统计 `duration > 0` 的行 |

**时长为什么挂在 `read_log` 而不是 `visit_log`**：前者按 `(post_id, ip)` 唯一，
累加语义天然成立；后者是「每次访问一行」的流水，算时长必须先配对相邻记录 ——
**读者关页面后没有后续记录，最后一段会整体丢失，系统性低估**。

⚠️ **区间维度做不了**：`read_log` 没有日期列（只有 `updated_at`），按区间过滤
必须另建按日汇总表。故本版只做**全站**口径，模板标签已写明，避免被误读成区间数据。
升级前历史阅读 `duration` 全为 0（不计入均值），短期内该数字偏低甚至显示「—」，
需积累新数据才准。

### 二、修复：访客属地排行榜长期混入爬虫

后台「访客区域排行榜」（全部时间 / 今日）与 v4.2.0 区间统计的「区间访客属地 TOP」
都**没有排除爬虫** —— `stats.py::_top_region()` 与 `_range_top()` 仅过滤空属地。
爬虫多为境外机房 IP，属地异步回填后会挤占真人省份的名次（榜单里混进
「美国· fremont」这类机房）。

**这是遗漏而非设计**：前台公开接口 `/api/geo/visitors`（`api/review.py`）一直都有
`VisitLog.is_bot.is_(False)`。

修法：`_range_top()` 新增 `human_only` 参数，**只在属地维度开启**。
没有一刀切，是因为「热门路径」里的爬虫抓取本身是真实的 SEO 热度，
跟着过滤会低估热门文章；「来源渠道」则是爬虫自身来源、本就没有读者信息。

### 三、主题中心大升级：可自定义壁纸 + 首屏大图

后台「主题中心」新增**首页壁纸**区块，前台首页顶部随之改为整屏大图。

- 亮色 / 暗色各配一张（暗色留空则沿用亮色），遮罩强度 0–0.8 可调
- 上传复用既有 `/admin/upload`（后缀白名单 + 文件头 16 字节魔数校验），**零新建数据表**
- 配置存 Setting KV `home_wallpaper`，符合项目「能不改表就不改表」纪律
- 首屏高 `100vh − 58px`（扣 sticky 导航），叠加站点标题 + 描述 + **联系方式小图标** +
  「向下滚动」提示；向下滚动即进入原有概览 / 文章列表 / 分页
- 联系方式图标复用 `lib/social.js` 的 `toSocialItem`（21 条平台规则，含 GitHub / 邮箱 /
  QQ / 微信的点击复制与二维码），**零新增数据、零后台改动**
- 未配置壁纸时退回 v3.4.1 的渐变横幅，原有观感不变

#### 安全：壁纸 URL 的三道限制

壁纸 URL 最终会进 inline style 的 `background-image`，因此限定得比一般配置更严：

1. **拒绝外部 URL** —— 否则等于让每个访客的浏览器替站主向第三方发起请求，
   读者的 IP 与 UA 就此泄漏；`data:` 前缀还能把任意内容塞进样式。
2. **拒绝 `..`（路径穿越）** —— 只判 `startswith("/static/uploads/")` 是不够的：
   `/static/uploads/../../config.py` 同样以该前缀开头，浏览器再把 `..` 规范化掉
   就打到别的路径。同时拒绝 `?` / `#` / `\`。
3. **「启用但一张图都没有」直接 400** —— 否则前台会渲染出一片没有任何内容的纯色空区。

`POST /api/theme` 现支持纯壁纸请求（只带 `wallpaper` 不碰主题包）；
拼错的 `pack_id` **仍返回 400**，不会被壁纸分支静默吞掉。

#### 前台：亮暗切换交给 CSS 而非 JS

两张壁纸写成 CSS 变量 `--wall-light` / `--wall-dark`，由 `[data-theme="dark"]`
选择器取。主题切换发生在 `App.vue`，若这件事留在 JS 里就得双向同步，
漏一处就是「切了主题、壁纸还是亮色」。

### 四、验证

全量 **902 passed**（新增 28 条），ruff 全仓通过，lint 棘轮 F401 回落基线 116。
新增测试覆盖三组功能，含**反向守卫**（否则「永远返回空列表」也能全绿），
并对四处关键分支做了变异验证，全部正确变红：

| 变异 | 结果 |
|---|---|
| `_top_region` 的 `is_bot` 取反 | 2 红 |
| `_range_top` 的 `human_only` 分支取反 | 2 红 |
| 均值分母改用 `COUNT(*)` | 精确命中该条 |
| 补报时长误加 `read_count` | 单元级 + 端到端级 2 红 |

统计页的改动配了**直接渲染页面**的断言 —— v4.2.0 曾把卡片写在 `{% block %}` 外，
Jinja 子模板中 block 外的内容不渲染，静默丢失且无报错，只测接口永远发现不了。

## v4.4.2（2026-10-13）

### 一、修复：后台游戏审计的四处「结论与安全状态脱钩」

用户报障：后台「游戏平台 · 收录与审核」的审计不可信。逐项查证后确认四个缺陷，
**其中第一项有生产数据库里的自证材料**（见下）。

#### 1. 🔴 送审代码被砍掉 75%，审计是「假审计」

`_sample_code()` 对**每个文件硬砍前 3000 字符**，而 `limit=60000` 形同虚设——
累计计数加的也是砍后长度，永远碰不到 60000，等于「每文件 3000」的天花板。
实测线上两个内置游戏：

| 游戏 | game.js 实际 | 旧版送审 | 丢失 |
|---|---|---|---|
| 恐龙快跑 | 12153 字符 | **3000** | **75%** |
| 就是按一下 | 7883 字符 | **3000** | **62%** |

**证据就在自己的审计结论里**——线上 `dino-run` 的 LLM 结论原文写着：

> "game.js 源码在末尾处被截断，**无法完全确认后续代码**"

LLM 明确说了「我只看到了 25%」，系统照样把 `verdict` 记成 `safe` 并入库。
即：**恶意代码只要落在第 3001 行之后，就 100% 逃过 LLM 审计。**

修法：取消每文件硬砍，改为**两级上限**（单文件 ≤ 40000、总预算 120000），
超限时**按比例削减并头尾都保留**（恶意代码常藏在文件尾），且**在送审文本文首
显式注入覆盖率声明**——否则收审方无从知道自己看的是残片，就会把
「没看到问题」误报成「没有问题」（这正是线上那条结论的成因）。

修复后实测：`dino-run` 送审量 4162 → **13409 字符（100% 全量）**。

#### 2. 🔴 `verdict` 从未被解析，审计结论与放行完全脱钩

LLM 返回 `{"verdict":"safe|risk|unknown"}`，但旧代码只把原文 `text[:3000]` 塞进
`audit_summary` 就结束了。后果：**判 `risk` 也能直接点「通过上架」**（`approve`
分支不读结论），且列表页只有一个「静态分」列（那是静态扫描的分，与 LLM 结论是
两件独立的事，并排显示纯属误导）。

修法：新增 `_extract_json()`（三级降级：直接解析 → 剥 ```` ```json ```` 围栏 →
截取最外层花括号；**失败返回 `None` 而非抛**），解析 verdict 并写进结论首行；
列表页新增审计徽标（LLM 安全 / 有风险 / 无法判定 / 未审计），与静态分分行显示。
`risk` 时把静态分压到 0，避免「静态分 94 + verdict=risk」并列误导。

#### 3. 🔴 审计失败后仍显示旧结论 —— 失败伪装成「已审」

旧实现失败时只 `return False`，**不写库**。于是对同一游戏重新审计如果失败
（Key 失效 / 超时 / 限流 / 配置不完整），后台仍显示**上一次那个 safe**。

修法：所有「拿不到结论」的出口统一落 `unknown` 并附失败原因，历史结论拼接在
「——— 历史结论 ———」之后留痕。**唯一例外是 LLM 总开关关闭**（那是「没审」
而非「审了没结论」，刻意不覆盖旧记录）。

> 🔑 首版修复**自己漏了一个出口**（配置不完整时直接 return），被本轮测试抓出来，
> 补了 `test_missing_llm_config_also_overwrites_old_safe`。
> 教训：**「失败必须落库」要枚举每条早退路径，不能只包 except 那一处。**

#### 4. 放行与审计结论耦合：风险二次确认（保留站长最终裁量）

按站点定位选择「二次确认」而非服务端硬拦：判 `risk` / 未审计 / `unknown` 时，
第一次点「通过上架」只渲染确认页（**不落库**），确认后才真正上架，并把风险摘要
与「站长确认放行」字样写进 `admin_note` + `log_audit`，事后可追溯是谁放行的。
判 `safe` 时直接放行（否则确认页会变成永远清不掉的噪音——**这条也写了反向守卫**）。

verdict 不新增表字段（项目纪律：能不改表就不改表），以固定前缀
`LLM 审计（安全|有风险|无法判定）：` 落在结论文本首行解析；
老数据（v4.4.2 之前的「LLM 审计：」原文格式）一律判 `unknown`——那批结论
本来就未被解析过，当 safe 是错的。

#### 5. 🐞 顺带修掉一个把自己坑了的 bug

写结论时间戳时用了 `datetime.now()`，但本项目有 `myblog/_time.py` 与标准库
`datetime` **同名**，`import datetime` 拿到的是那个封装模块（只有 `utcnow`，
没有 `.now`）→ 抛 `AttributeError` → 被外层 `except Exception` 吞掉，
**伪装成「审计失败」**。第一版修复因此整个写库路径静默失效，是靠测试抓出来的。
已改用项目唯一时间真相源 `utcnow()`。

### 二、新增内置游戏《贪吃星》（v4.4.2）

- `myblog/builtin_games/star-eater/`：单文件 Canvas 贪吃蛇变体，15×15 格，
  吃星星变长、随长度提速（132ms → 62ms 封顶）、碰壁/咬自己结束、
  空格填满即通关；最高分落 `localStorage`（读写均 try 兜底——沙箱禁存储时
  宁可没最高分也不能开不了局）。
- 移动端优先：滑动 + 方向键/WASD 双通道、180° 反向拦截、长按方向键连发；
  触屏才显示方向按钮（桌面显示只会碍事）；页面隐藏时重置计时，回来看不
  会一次性补上大量步数；高 DPI 下画布按 2 倍渲染避免糊。
- 走完整收录链路验证：manifest 校验通过、入口存在、**静态扫描 99 分**
  （唯一发现是 `localstorage` info 级，已 try/catch 兜底）。
- ⚠️ `update.sh` **不会**自动收录内置游戏（有意如此，避免部署覆盖已收录内容）；
  升级后需手动跑一次 `python myblog/tools/seed_games.py`（`builtin_games/`
  会被 `add_tree` 自动打进后端 zip，无需改打包白名单）。

### 三、验证

- 新增 `tests/test_games_audit_v442.py` **22 条**，覆盖四个缺陷 + 静态扫描未回归。
- **变异 4 组全红**：① 恢复每文件硬砍 3000 ② 去掉 verdict 解析
  ③ 去掉「配置不完整」出口的落库 ④ 去掉放行二次确认闸门；恢复后全绿。
- 修复后送审覆盖率实测：`dino-run` 4162 → 13409 字符（全量）、
  `star-eater` 11880 字符（全量）。

---

## v4.4.1（2026-10-13）

### 一、修复：后台「全站体检」误报「未找到备份文件」（用户报障）

**现象**：本地与云端（坚果云 WebDAV）备份**都配了、也都在跑**，体检的「数据备份」卡片
却显示**未找到备份文件**。

**生产实证**（部署前先去看真实文件长什么样，不信代码里的路径假设）：

| 写入方 | 服务器实际路径 | 文件数 |
|---|---|---|
| `update.sh` 每次部署前直拷 | `/www/wwwroot/myblog/data/backup` | **141** |
| `backup.py` + 每天 04:00 cron | `/www/wwwroot/backups` | **37**（含当天 `blog_backup_20260103_040001.zip`） |
| DB `backup_dir` | 空（走默认） | — |
| DB `backup_webdav_url` | `https://dav.jianguoyun.com/dav/blogbackup` | 已配 ✓ |

**根因**：体检只猜了一条**恒不存在**的路径，且三处都错：

1. 目录名写成 `data/backups`（**复数**），实际是 `data/backup`（**单数**，update.sh 用的）；
2. **从不去看 `BACKUP_ROOT`** —— 定时任务真正落盘的地方（37 个文件就在那儿）；
3. 用 `REPO_ROOT/myblog/data/…` 拼路径，而线上代码（v3.18.6 起）**直接铺在站点根**、
   没有 `myblog/` 这一层 → 服务器上这个路径永远不存在。

**修法**：新增 `_backup_search_dirs()`，按「**真实写入方**」枚举候选目录 —
后台配置 / `BACKUP_DIR` / **`backup.BACKUP_ROOT`（唯一真相源）** / `<代码同级>/data/backup`，
跨全部目录取 mtime 最新的一个，并**标注它来自哪个来源**。
🔑 定时任务那条**直接取 `backup.BACKUP_ROOT` 而不自己重算路径规则** —— 重算等于把写入方的
规则抄一份，抄错就是本 bug 本身（与 v4.2.0 发版时「复刻双源互证算法连错三处」同一个教训）。

顺带两个改进：
- **配置了却不存在的目录会显式列为「目录缺失」并置 warn** —— 那是「配了没生效」，
  静默忽略等于把坏配置藏起来；
- 「本地备份目录」现在列出**全部有效目录**而非单个。

### 二、验证
- 新增 `tests/test_diagnostics_backup_v441.py` **6 条**，含一条**反向守卫**
  （目录存在但无备份文件时必须仍报「未找到」，防止修宽成永远说 OK 的假体检）。
- **变异验证**：把「查 `BACKUP_ROOT`」与「查部署目录」两处摘掉（= 旧逻辑）→
  **3 条立刻变红**；还原后 6 条全过 —— 守卫承重，非空话。
- ⚠️ 用例全部包在 `app.app_context()` 内：`read_setting_db()` 脱离上下文会**直连真实库**
  `myblog/data/blog.db`（不是"读不到"，是**读错库**）。

## v4.4.0（2026-10-13）

### 一、移动端「内容全套」：公告 / 留言 / 订阅 / 分类·标签·系列 / 友链本体 / 版本历史 / 媒体库

v4.3.0~v4.3.1 把「文章 + 评论 + 访客」搬上了手机，但后台还有一整排只能回电脑才能做的事。
本次补齐**内容管理这一批**（30 → 66 个 `/api/mobile/*` 端点），并且照旧一条原则不放松：
**JSON 侧不写第二套业务逻辑**，全部复用后台核心函数。

**新端点（按界面分组）**

| 组 | 端点 | 权限 |
|----|------|------|
| 公告 | `GET /mobile/announcements`、`GET/POST /mobile/announcement[/<id>]`、`POST …/active`、`POST …/delete` | 管理员 |
| 留言 | `GET /mobile/guestbook`、`POST /mobile/guestbook/<id>/read`、`POST /mobile/guestbook/read-all`、`POST /mobile/guestbook/<id>/delete` | 管理员（`ip` 字段仅超管） |
| 订阅 | `GET /mobile/subscribers`、`POST /mobile/subscriber/<id>/active`、`POST /mobile/subscriber/<id>/delete` | 管理员（邮箱全量仅超管） |
| 分类 | `GET /mobile/categories`、`POST /mobile/category`、`POST/PUT /mobile/category/<id>`、`POST …/delete?move_to` | 管理员 |
| 标签 | `GET /mobile/tags`、`POST /mobile/tag`、`POST /mobile/tag/<id>/delete`、`POST /mobile/tags/merge` | 管理员 |
| 系列 | `GET /mobile/series`、`POST /mobile/series`、`POST/PUT /mobile/series/<id>`、`POST …/delete?move_to` | 管理员 |
| 友链本体 | `GET /mobile/links`、`POST /mobile/link`、`POST/PUT /mobile/link/<id>`、`POST …/delete`、`POST /mobile/links/reorder` | 管理员 |
| 版本历史 | `GET /mobile/post/<id>/history[/<hid>]`、`GET …/history/diff?a=`、`POST …/history/<hid>/rollback` | 可编辑者（`_can_edit_post`） |
| 媒体库 | `GET /mobile/media`、`POST /mobile/media/delete` | 管理员 |

**顺带补上的首屏指标**：`/mobile/overview` 的 `counts` 新增 `unread_guestbook`。
后台导航角标早就有这个数（`inject_notification_counts` 的 `pending_guestbook`），
App 之前却只能自己拉一页留言去数 —— 现在两端同源。

### 二、这次一并补的**后台缺失能力**（不是只为移动端加的）

盘点时发现三件事在网页端也做不到，本次一起补，移动端与网页端共用同一份实现：

- **公告没有编辑入口**：原先只有「新建 / 启停 / 删除」。公告一删不进回收站、无法还原，
  重建还会掉到列表末尾 —— 改一个错别字的代价是丢掉整条公告的位置。新增
  `POST /admin/announcement/<id>/update` + `templates/admin/announcements.html` 的编辑行。
- **友链没有编辑入口**：`name/url/description/sort` 全都不能改，只能删了重建（丢排序位置）。
  新增 `POST /admin/link/<id>/update`（与新增共用 `save_friend_link_core`）。
- **友链没有排序界面**：`sort` 只能靠新增时手填。新增 `POST /admin/links/reorder`
  （整单顺序提交，`sort=(i+1)*10` 留出插位空档；**未列出的 id 一律不动**），
  页面用 ↑↓ 直接调，改动立刻保存。

`set_link_rss` 这条旧路由也一并接到 `save_friend_link_core` 上：原先它自己写了一遍
「存 rss + 软校验可达性」，与编辑路径各有一套判据 —— 正是本仓库反对的两套逻辑。

### 三、抽出来的核心（`*_core`，SSR 与 JSON 共用）

`admin/_helpers.py`：`ANNOUNCEMENT_LEVELS` / `_announcement_fields` / `create_announcement_core`
/ `update_announcement_core` / `normalize_link_url` / `save_friend_link_core`
/ `reorder_friend_links_core` / `rollback_post_core`。
`admin/taxonomy.py`：`create_category_core` / `rename_category_core` / `delete_category_core`
/ `create_tag_core` / `delete_tag_core` / `tag_usage_counts` / `create_series_core`
/ `rename_series_core` / `delete_series_core`。
`admin/media.py`：`collect_media` / `media_refs_for` / `delete_media_core`。

两条判据因此从「两套」变「一套」：

- **友链新增原先不查重**（同 URL 能连加两次），而审核友链申请那条路早就查了；
- **公告 `level` 原先不校验**（任意字符串都能进库，前台按 level 上色会出现未知档），
  且内容为空时能建出一条挂在前顶部的空横幅。

### 四、三条产品口径（本次确认过的决定）

- **订阅邮箱**：对管理员**遮敏**（`su***@exemple.com`）、对超管全量。理由是「可直接群发的
  PII + App 会本地缓存列表」。`Subscriber.unsub_token` **任何角色都不返回** —— 拿到它就
  等于能替别人免登录退订。
- **分类 / 系列改名**：**沿用后台既有行为**（无条件重算 slug），不改判据、不建别名表、
  不加 301；改为把「旧 → 新」如实回传（`note` 字段），由界面在提交前显示提醒。
  静默改名让外发链接 404 这件事，本来就该被看见。
- **删除类操作全部如实标注可逆性**：留言 / 订阅者 / 友链 / 媒体文件都是**硬删除**，
  不进回收站；媒体文件被文章引用时先返回 `409 + 引用清单`，必须再发一次
  `{"force": true}` 才真删（本模块唯一用 409 表达「请先确认」的接口）。

### 五、幂等性：状态类接口不收「翻转」

后台网页的启停按钮是**翻转**语义（点了就是相反状态，符合页面直觉），移动端一律改成
**显式目标值**：`POST …/active {"active": true|false}`。
弱网下客户端重发同一个请求，翻转会来回横跳（用户以为停用了，实际又启用），显式值重发
多少次结果都一样。同理，`_need_flag()` 对**缺字段**返回 400 而不是静默按 False 落库 ——
整单表单「没勾就是 False」是对的，改单个状态时就是静默改数据。

### 影响面

零表结构变更、零迁移（Alembic head 仍为 `c7a2f19b4d30`）、前端未改（不需要重新构建
`vue-frontend-dist.zip`）、无需 nginx 改动。后台行为变化只有两处：友链新增开始查重、
公告 `level` 开始归一（非法值落 `info`）。

### 测试

`tests/test_api_mobile.py` 从 25 条增至 **36 条**（新增 11 条），逐条覆盖上面的口径；`tests/test_doc_archival.py` 的归档守卫随 `PAIRS` 多一条而多 3 个参数化用例。CI 对照（同为 python 3.13 ubuntu）：main `fe117c7` 是 **7 failed / 824 passed**，本 PR 是 **7 failed / 838 passed** —— 824+11+3=838 正好对上新增，红的还是那 7 条（6 条 `test_cert_watch.py` 的 runner OpenSSL 问题 + 1 条 `test_point_log_dedup_and_retention`），一条不是本次引入。
权限分层（普通用户 / 管理员 / 超管三级）、level 白名单归一、显式启停幂等与缺字段 400、
邮箱遮敏 vs 超管全量 + `unsub_token` 不出现在**原始响应文本**里、留言 IP 分层与
「PII 不进审计」、分类改名的 slug 提醒与 `move_to` 两条去路（含非法落点必须报错）、
标签在用拒删与一键整理合并、系列 `name` 不唯一与删除脱离、友链 URL 归一/查重/排序只动
列出的 id、回滚只改三字段且回滚前自动备份、媒体库 `force` 与 `../` 路径穿越、
以及「网页端新补的编辑/排序入口真的能提交」（SSR 写、JSON 读回同一行）。

顺带修掉两处**本仓库既有**的实现问题：

- `media.collect_media` 原先把引用列表截断到 6 条后再取 `len()` 当 `ref_total`，
  那个数**永远不超过 6**，是个看起来像总数的假数；现在 `media_refs_for` 完整返回、
  调用方自己截断显示。
- 标签用量原先逐行 `len(t.posts)` 把每个标签的全部文章对象读进内存；改成
  `tag_usage_counts()` 一条 GROUP BY（后台标签页与 `/mobile/tags` 共用）。

另：本文件的测试模块加了 autouse 的 `_isolate_rate_limit` fixture。`/api/mobile/*` 的写接口
全按客户端 IP 限流，而测试客户端永远是同一个 IP，`utils.net._RATE` 又是模块级字典、
整个会话累积 —— 累积到 20 次发文就会出现「第 21 次返回 429、用例拿到 None 去下标」这种
与业务无关的红。限流本身仍由 `test_posts_pagination_v4.py` 专门测（同 `test_oauth.py` 的做法）。

### 文档归档（同 v3.25.13 的循环）

`SECURITY_AUDIT.md` 写完 R122 后到 163 KB，触发体积守卫（上限 160 KB）。按「新增轮次写进
主文件、历史段落才归档」把 **R91~R100** 逐字搬到 `docs/archive/SECURITY_AUDIT_r91-r100.md`
（80 KB），主文件从 R101 起、顶部指针已更新，`tests/test_doc_archival.py` 的 `PAIRS`
同步加了一条（归档件存在 / 主文件留指针 / 锚点齐全 三件事一起钉住）。查 R95、R98 这些
老轮次请去归档件，内容没做任何删改。

## v4.3.1（2026-10-13）

### 一条权限收口：访客日志与封禁清单从「管理员」升到「超管」

v4.3.0 的 `/api/mobile/visit-logs` 与 `/api/mobile/blocked` 按后台页面同级放行给了
**管理员（super + admin）**。权限判定本身没有放宽 —— 后台 `/admin/visit-logs` 本来就是
`admin_required` —— 但**出口的性质变了**：

- 页面是「一个人、一页 50 条、逐页翻」；
- JSON 接口是「可被脚本 `?page=1..N` 顺序抓完的整表」。

这两个端点输出的正是**访客 IP 原文**（`VisitLog.ip` 逐条 + 当前生效的封禁 IP 清单）。
把「能不能看」的等价性，直接当成了「能多快全部拿走」的等价性，是个判断漏洞。

**改动**：两个端点升为 `_role(super_only=True)`。

**为什么连同 `/blocked` 一起升**：拉黑与解封在 v4.2.0 就是超管专属，「谁被封了」这份清单
若管理员可见而不可操作，反而更容易造成「看到了却没法核对处理」的错觉 ——
**能决定封谁的人，才应该拿到那份 IP 清单**，清单与操作权限同级更好核对。

**没跟着一起升的，以及为什么**：`/mobile/comments` 也带 `ip` 字段，但后台评论页
（`admin/comments.html` 的「IP」列）本就把它展示给管理员，评论是人产生的、量级比访问日志小两个数量，
且审核是管理员的日常动作 —— 升上去只会把管理员的活挡在门外。这条界线刻意划在
**「逐次访问的原始日志表」** 与 **「人为产生的内容」** 之间，判据与残留风险写进
SECURITY_AUDIT **R120.5 / R121**。

**影响面**：只影响 `admin` 角色（非超管）调用这两个新端点；`/admin/visit-logs` 页面行为不变。
你本人是超管，App 侧一切照旧。零表结构变更、零迁移。

**测试**：新增 `test_访客日志与封禁清单仅超管可读` —— 同时断言两件事：非超管管理员拿
`403`，而该管理员仍能读评论 / 统计 / 首屏 / 回收站（防止收得过宽把日常工作挡掉）。
`tests/test_api_mobile.py` 从 23 条增至 24 条。

## v4.3.0（2026-10-13）

### 一、移动端管理接口：后台能力开成 JSON（`/api/mobile/*`，30 个端点）

手机上管博客此前只有两条路：浏览器开 `/admin/*`（桌面排版，靠缩放），或 WebView 套壳。
套壳除了「保登录 + 快捷导航」给不了任何原生东西，而 v4.2.0 的访客日志页在手机上还会
因为 7 列表格超出可视宽度而点不到「拉黑」按钮。本版把后台管理能力正经开成 JSON：

| 分组 | 端点 |
|------|------|
| 首屏 | `GET /api/mobile/overview`（待审/未读评论、未读通知、草稿、定时、待审友链、置顶申请、回收站计数 + 今日数据 + 最近 5 条评论） |
| 文章 | `GET /posts`（后台同筛选/排序口径）、`GET/PUT/POST /post[/<id>]`、`/publish`、`/unpublish`、`/pin`、`/trash`、`GET /taxonomy` |
| 评论 | `GET /comments`、`/comment/<id>/{approve,reject,read}`、`/comments/read-all`、`/comments/batch` |
| 访客 | `GET /visit-logs`（九档区间随响应回传）、`GET /blocked`、`POST /ip/{block,unblock}` |
| 其他 | `GET /stats`、`GET /trash` + `restore`/`purge`、`GET /moments` + 发布/删除、`GET /link-applications` + 通过/拒绝、`POST /upload`、`GET /notifications` |

完整契约（鉴权级别、请求体字段、curl 联调样例）见 **`myblog/API.md` 的「移动端管理 /mobile」**。

### 二、零业务复制：写入全部复用后台既有核心，并顺手消灭了三处历史重复

新增接口一律「取参 → 鉴权 → 调既有核心 → 序列化」，**没有**复制任何字段级业务规则。
为此把后台的编辑/发布/软删/还原逻辑抽成可复用核心（这一步是本版唯一的存量代码改动）：

- 新增 `admin/_helpers.py::update_post_core` / `publish_post_core` / `trash_post_core` /
  `form_flag` / `_announce_post_published`；`admin/post_trash.py::restore_recycle_core` /
  `purge_recycle_core`。
- `admin/post_editor.py::edit_post` 的 80 行 POST 分支改为调用 `update_post_core`（行为逐行等价）。
- `admin/post_manage.py::publish_now` 与 `api/posts.py::publish_now` 原本**各抄一遍**发布副作用链
  （翻状态 → 清定时 → FTS → 插件事件 → IM 推送 → SEO 自动收录 → 邮件群发），现统一走
  `publish_post_core`；后台 `delete_post` 同理走 `trash_post_core`。
- `form_flag` 让「SSR 表单的 `"on"`」与「JSON 的 `true`」共用一个判据，避免同一字段两套语义。

### 三、权限与闸门（`/admin/*` 的语义原样搬到 JSON）

- 后台的 `admin_required` / `super_required` 未登录时是 **302 跳登录页**，客户端拿到一页 HTML
  分不清「没登录」还是「被重定向」—— 故本模块自带 `_role()`，一律 `401/403 + {"error": …}`。
  判定条件与后台**逐条一致**（未登录 / 超管未改默认密码 / 角色不足），没有放宽任何一条。
- 提权字段在服务端按角色丢弃：`is_pinned` 仅管理员、`is_private`/`reward_*` 仅超管，
  客户端传了也不生效（`tests/test_api_mobile.py` 有专门一条钉住 —— API 没有「表单里没这个勾」
  这层天然保护，必须代码里收紧）。
- CSRF 与 2FA 自动生效：`/api/mobile/*` 不在 `app.py` 的 CSRF 豁免白名单里，写方法必须带
  `X-CSRF-Token`；2FA 是会话级闸门，对 `/api/` 前缀返回 `401 {twofa_required:true}`。
- 写接口按客户端 IP 限流；所有写操作落 `AuditLog`（`mobile_*` 动作名），后台操作日志可查。
- ⚠️ 闸门顺序（测试已钉）：CSRF 检查在业务视图之前，**既未登录又缺 token** 时返回 403（CSRF）
  而不是 401。真实客户端登录后立刻就有 token，不受影响。

### 四、顺带修掉：访客日志页手机端「拉黑」按钮点不到

`templates/admin/visit_logs.html` 用的是 `.stats-table`（≤900 横向滚动兜底）。7 列里
IP / 路径 / 来源都是长文本，而 `base.html` 有 `body{overflow-x:clip}` —— 横滑会被裁掉，
结果「操作」列在手机上根本够不着。现改为走全站既有的 `.admin-table` + 逐格 `data-label`
卡片化机制（≤760 隐藏表头、单元格纵排、字段名由 `td[data-label]::before` 渲染）。
这条约定由 `tests/test_admin_table_data_label.py` 强制，漏一格即红。

### 五、零表结构变更、零迁移

没有新增表、没有新列，Alembic head 仍是 `c7a2f19b4d30`，**升级不需要跑迁移**（照常重启即可）。
前端（`vue-frontend/`）未改，也不需要重新构建。

### 六、必须知道的一条部署约束

`myblog/api/__init__.py` 现在会 `from . import mobile`。**部署必须整套覆盖后端**：
只拷了部分文件（比如漏了 `api/mobile.py`）会让整个应用启动即 `ImportError`，
表现是「升级后站点完全打不开」而不是「新功能没有」。`update.sh` / `package.py` 走的是整目录
`os.walk` 打包，正常流程不会踩到；手工 scp 单个文件才需要当心。

### 七、测试

新增 `tests/test_api_mobile.py`（23 条）：未登录 401 / 越权 403 / 普通用户提权字段被丢弃 /
CSRF 缺失被拦 / 发文-编辑-发布-撤回-软删-还原 全链路 / 定时时间的北京↔UTC 换算 /
访客日志九档筛选与「已拉黑」标记 / 拉黑需超管且幂等解封 / 评论通过与驳回与批量 /
友链通过要落 `FriendLink`、拒绝不落 / 上传拒绝伪装成 png 的 HTML / 首屏计数与表内一致。
既有的 `test_admin_posts_characterization.py`、`test_edit_post_history.py`、
`test_admin_explicit_imports.py`、`test_no_module_import_cycles.py` 全部保持通过
—— 它们就是「抽取核心没有改变行为」的证据。

## v4.2.0（2026-10-12）

### 一、访客运营精细化：九档区间 + 独立访客日志 + 按 IP 拉黑

**1. 区间访客数据（`/admin/stats`）**：新增 **今天 / 昨天 / 近 7 天 / 近半月 / 近 1 月 /
近 3 月 / 近 6 月 / 近 1 年 / 近 2 年** 九档切换。每档给出 PV、UV（去重 IP）、真人 PV/UV、
爬虫 PV、区间新增评论，以及区间内 **热门路径 / 访客属地 / 来源渠道 TOP 10**。
区间边界按 `VisitLog.date`（本地日期字符串，字典序即日期序，有索引）比较。

**2. 访客日志（`/admin/visit-logs`）**：独立页面分页展示每一次访问的 IP / 属地 / 路径 /
来源 / 类型（真人或具体爬虫名），支持区间、类型、IP、属地、路径组合筛选（LIKE 通配符已转义）。
查看权限与「访问统计」同级（admin），**拉黑/解封为超管专属**并写操作日志。

**3. 按 IP 拉黑**：日志页一键拉黑（默认**永久**），被拉黑 IP 访问前台页面返回 429；
可在本页或「🛡️ 反爬限流保护」页解封。

### 二、零表结构变更、零迁移

`VisitLog` 自 v3.0 起就记录 IP / 日期 / 时段 / 属地 / 路径 / 来源 / 是否爬虫，
`BotBlock` 自 v3.8.0 起就是封禁原语 —— 本版**没有新增表、没有 Alembic 迁移**，
只是把已有的数据与能力接到后台界面上。

### 三、必须记住的一条：黑名单不能挂在「反爬限流」开关后面

旧实现把 `check_bot_guard()` 整个放在 `if not guard_enabled(): return None` **之后**，
而 `bot_guard_enabled` **默认 false** —— 开关关着时封禁检查整条不执行，
后台「拉黑」拉了也白拉。本版把手动黑名单的检查**提到开关判断之前**：
管理员显式拉黑的 IP 无条件拦截（安全语义优先），自动限流仍受开关控制。

连带修掉一个关联缺陷：自动限流 `_record_block()` 原来会无差别覆盖既有记录，
把一条**永久手动封禁**改写成 `now + 30min`（永久封禁悄悄降级成半小时，reason 还被改写）。
现在 `reason == "manual"` 的记录只累计命中次数，不动封禁期与原因。

### 三点五、顺带修掉的隐藏 bug：统计页三张卡从未渲染

`admin/stats.html` 把「📈 环比 / 🔗 来源渠道 TOP / ⬇️ 导出访问明细」三张卡写在了
`{% block content %}` **外面** —— Jinja 子模板中 block 外的内容不会输出，
这三张卡自 v3.20.0 上线起就一直没显示过（不报错、不写日志，纯静默）。
本版已移入 content 块，并补上「统计页本身必须被渲染」的测试
（此前只有 `/admin/stats/export` 接口有测试，页面模板从未被渲染过）。

### 四、验证

- 新增 `tests/test_visitor_analytics_v42.py` 11 条用例，其中两条即上述缺陷的回归：
  **开关关闭时拉黑仍 429**、**自动限流不改短永久封禁**。
- 三项变异全部转红：黑名单检查后移到开关之后 / 去掉手动记录保护 / 区间边界 off-by-one。
- 全量 pytest 806 passed；ruff 全仓 0 错。
- 覆盖范围：黑名单经前台蓝图 `main_bp.before_request` 生效；`/api/` 与 `/admin/` 有各自
  鉴权与限流，不在此列（后台不会被误锁，误拉黑可随时解封）。

## v4.1.0（2026-10-09）

### 一、外部入口：从一个变成多个（后台独立管理页）

v4.0.0 的入口只能有一个，且四个配置项挂在「站点设置」这张大表单里。本版拆成独立页面：

- **后台「🧰 外部入口」**：新增 / 编辑 / 删除 / **上下排序** / **逐条启停**，上限 12 条。
- **前台统一收进「🧰 工具箱 ▾」下拉**（桌面导航 + 移动端抽屉两处）。

**为什么是下拉而不是平铺**：导航栏是 `flex-wrap: nowrap`（`global.css:29-33`），
条目放不下时是**横向挤出**而不是换行 —— 而导航栏在此之前已塞了 13 个路由项，
横向预算基本用光。收进下拉后，**加 10 条入口也只占导航栏 1 个位置**，
溢出问题从结构上消失，不需要再写 JS 测量宽度去折叠。

### 二、存哪儿：单个 Setting 存 JSON，不建表

`Setting.nav_entries` = JSON 数组。**没有新增表、没有 Alembic 迁移**。

理由：入口数量天然是几个，此处永远不需要 SQL 过滤/分页/联表；
而它需要跟着 `config_rollback` 一起快照回滚（误删要能回去），
放进 Setting 表就自动具备这个能力 —— 新建表则要把回滚逻辑再写一遍。

### 三、两条必须记住的

**1. 迁移必须幂等。** 旧四件套（`entry_*`）在启动时自动转成第一条 `nav_entries`，
但**只迁一次**：判据是「`nav_entries` 这个 key 存不存在」，而不是「有没有内容」。
否则用户在管理页把入口删光后，重启又会被迁移逻辑变回来 ——
表现为「删不掉」，而没人会想到是迁移在作祟。

**2. 站点设置页不再能改入口。** 已移除那四个输入框，改成一条指路链接。
留着两处都能改，就必须回答「以哪边为准」，这是自找的困惑。

### 四、安全边界保持不变（仍是两层）

| 层 | 位置 | 行为 |
|---|---|---|
| 写入侧 | `admin/nav_entries.py` | 非 http/https 拒绝入库并提示；编辑时地址填错则**保留旧地址**，名称/图标照改 |
| 出口侧 | `api/site.py:_nav_entry_items` | 输出前再判一次，非法一律当作不存在 |

顺带保持：拒绝协议相对地址 `//evil.com`；前台一律 `target="_blank" rel="noopener"`。
`entry` 单条字段**保留**（= `entries[0]`）以兼容既有外部依赖。

### 五、验证

- 新增 `tests/test_nav_entries_v4_1.py`（20 条）：多条顺序、启停、上下移动（含越界不成环）、
  删除、**脏数据容错**（坏 JSON / 非数组 / 非 dict 项一律退化不崩溃）、
  **迁移幂等**、上限、**前台必须 `v-for` 且收进下拉容器**。
- 改造 `tests/test_site_entry_v4.py`（29 条）：安全断言改为**绕过后台表单直接写脏数据**，
  验证出口防线能独立兜住；后台相关用例迁到新管理页。
- **变异验证 4 组全红**：① 出口过滤失效 ② 迁移不幂等 ③ 数量上限失效 ④ 写侧白名单失效
  —— 每条都有对应守卫视红，不是「写了测试就以为安全」。
- 全量 **794 passed**（771 → 794，净增 23：新页名 20 条 + 入口测试 29 条改造后净 +2）；
  `ruff check .` 全仓 0 error。

> 顺带踩到：**测试库是全 session 共享的**（`%TEMP%/llhhy-blog-pytest/test.db`），
> 上一条测试新增的入口会留到下一条，`items[0]` 就指到别的对象上了 ——
> 表现为「期望值和实际值都是合法数据、但不是同一条」的假失败。已加 fixture 每次清空。

### 六、顺带修掉的小瑕疵

`README.md` 里 `(../../releases)` 是 GitHub 站点相对链接、本地不可解析，
改为绝对地址 `https://github.com/Llhhy1/llhhy-blog/releases`。

## v4.0.0（2026-10-08 · 已发布）

> **4.0 的第一个改动是还债，不是新功能。** 全量安全审计（`docs/audit/2026-10-07-full-audit-report.md`）
> 留了一条【低危 7】没修：列表接口 `.all()` 全量物化 + 首页匿名无限流。当时判断「彻底修要动
> `lang_dedup()` 的语义，建议在 4.0 开发里一并做」——现在就做。**未发版**，等 4.0 的功能一起上。

### 一、改了什么

| 端点 | 改造前 | 改造后 |
|---|---|---|
| `/api/posts` | `lang_dedup(query.all(), lang)` 全表物化成 ORM 对象，再 Python 切片 | 去重下推为窗口函数，`LIMIT/OFFSET` 由数据库执行 |
| `/api/search` | FTS 命中 N 篇就 `session.get()` 物化 N 篇；LIKE 分支同样 `.all()` | FTS 只取 id（每行两个整数）后按页取对象；LIKE 走 SQL 分页 |
| `/api/post/<slug>/related` | 取出**全站**可见文章逐篇求标签交集 | 标签重合走聚合子查询、同分类走 `CASE`，库里只回 5 行 |
| `/api/post/<slug>/also-viewed` | 把本篇**全部**访客 IP 取进内存 + 全站文章求交集 | 共现用 `GROUP BY` 计数，访客集合用子查询表达，IP 一行都不进 Python |
| `/api/categories` | 每个分类一次 `count()` —— N+1 | 一条 `GROUP BY` |
| `/api/tags` `/api/hot-tags` | 逐标签惰性加载 `t.posts`（N+1）并在 Python 里求和 | 一条聚合查询 |
| 上述端点 | **匿名无限流** | 全部补上按 IP 的限流（列表 120/60s、搜索 60/60s、归档 30/60s） |

### 二、两条最值得记的

**1. 组的排序位必须用 `FIRST_VALUE`，不能用 `MAX()`。** `lang_dedup()` 里同译文组的先后顺序
取的是「组内**首成员**在展示顺序中的位置」，即 `(is_pinned, created_at, id)` 的**字典序 argmax**。
对两列分别取 `MAX` 会拼出 `(1, t_late)` 这种**不属于任何一行**的组合（首成员其实是 `(1, t_early)`），
顺序就错了。差分测试里专门造了一组「首成员置顶但最旧、另一成员不置顶但最新」的数据来钉死这一点。

**2. 「不慢」不是默认的，是量出来的。** 第一版把去重下推后，`?lang=` 分支在 1000 篇规模下
**反而慢了 1.4x**（35.2ms vs 24.5ms）—— 窗口函数多一遍排序，还要再按 id 取一次对象。
而 `?lang=` 恰恰是首页的**默认路径**（`store.js` 的 `contentLang` 初值是 `"zh"`，
`HomeView.vue` 每次都带）。于是补了两刀：

- `total` 不再用 `SELECT count(*) FROM (窗口子查询) WHERE rn=1`（那等于把窗口计算跑两遍），
  改成一条 `COUNT(DISTINCT 组)` 聚合；
- 同一条聚合里多取一个 `COUNT(*)`，用「**组数 == 文章数**」判定「每组恰好一篇 → 去重是恒等操作」，
  命中就完全跳过窗口、退化成普通分页（顺带省掉「先探一次有没有译文组」的额外查询）。

实测（预热后取中位数，`per_page=8`）：

| 规模 | 首页（无 lang） | 末页 | 首页（lang，无译文组） | 首页（lang，有译文组） |
|---|---|---|---|---|
| 200 篇 | 8.1 → 6.5 ms（1.2x） | 7.9 → 6.6 ms（1.2x） | 8.1 → 6.5 ms（1.3x） | 8.1 → 10.9 ms（0.7x） |
| 1000 篇 | 21.9 → 7.0 ms（3.1x） | 22.5 → 8.7 ms（2.6x） | 23.5 → 7.7 ms（3.0x） | 23.4 → 21.7 ms（1.1x） |

**唯一还变慢的组合**是「文章少 + 有译文组」（200 篇时 +2.8ms 绝对值）：此时窗口计算省不下来，
而旧实现那一次 `.all()` 本来就便宜。文章越多收益越大，且**内存从 O(全表) 变成 O(一页)**。

**按生产库实际规模（10 篇文章 / 43 个标签 / 3 个分类 / 0 个译文组）实测**：

| 端点 | 改造前 | 改造后 |
|---|---|---|
| `/api/hot-tags` | 21.3 ms / **45 条 SQL** | 2.9 ms / **3 条 SQL**（7.3x） |
| `/api/posts?lang=zh`（首页默认） | 命中快路径，与普通分页同速 | 内存物化从「全表」降为「8 篇」 |

生产 SQLite 为 **3.46.1**（窗口函数需 ≥ 3.25），已确认支持。
（`/api/posts` 在 10 篇规模下两种实现都在 1ms 级，此处差异不具参考性，故只列标签聚合这条。）

### 三、顺带修掉的一个行为缺陷

`also-viewed` 原先先按分取 top10、**再**按可见性过滤、最后取 top5，于是 top10 里若混着
隐私/回收站文章，最终可能只返回 3 篇。现在可见性是 SQL 的 `WHERE` 条件，取的就是「可见文章里的
top10」，最后 5 篇一定是满的 —— 与该函数 docstring 里「多取名额以补足被过滤掉的项」的意图一致。

### 四、新增：后台可配的「自定义外部入口」（默认指向百宝箱子站）

前台导航栏（含移动端抽屉）多一个指向外部站点的入口，**名称 / 地址 / 图标 / 开关全部后台可改**
（站点设置 →「🧰 v4.0.0 自定义外部入口」）。默认值即 `百宝箱 → https://box.llhhy.cn`，
升级后自动生效，不需要手工填。想换成别的子站或工具站，改三个输入框即可；不想要就取消勾选。

**唯一值得写下来的是它的安全边界。** 这个入口的地址由后台填写、前台用 `:href` **直接绑定** ——
它是一个「存储型 XSS 的候选入口」：只要 `entry_url` 变成 `javascript:...`（手滑、注入、迁移脏数据），
页面一加载就在访客浏览器里执行，而且**不报错**，导航栏看起来一切正常。所以做了两层：

1. **保存时拒绝**：非 http/https 的地址不写库，并提示用户「本次填写未保存」，
   但**照常保存同表单的其它字段**（一个字段填错不该丢掉整张表单的编辑，同 `site_url` 的取舍）；
2. **出口过滤**：`/api/site` 输出前再判一次，非法地址一律当作未配置
   （`enabled=false` + `url` 为空），前台根本拿不到危险 href。

顺带拒绝协议相对地址 `//evil.com`（继承本站协议却指向外域，既不合意图也不好审计）。
新增 `utils.is_http_url()` 作为这一判据的单一实现，后台与 API 共用。
`entry_enabled` 已进配置快照，误关可回滚。

### 五、验证

- **差分测试** `tests/test_posts_pagination_v4.py`（47 条）：把改造前的 Python 实现原样抄一份
  当参照物，在造好的数据集上逐条比对新旧输出（5 种 lang × 4 种 per_page × 每一页）。
  另含「SQL 必须带 LIMIT / 按 id 取且占位符不超一页」的机器判据、N+1 条数判据、限流阈值判据。
- **变异验证 7 组全红**：把分页退回 `.all()`、`first_value` 换成 `max`、去掉限流、退回 N+1、
  退回 Python 打分、FTS 逐条 `get`、快路径无条件生效 —— 每一条都有对应守卫视红。
- 入口守卫测试 `tests/test_site_entry_v4.py`（27 条）：URL 白名单正反用例、
  **非法地址绝不出现在前台 JSON**（4 种危险 scheme 参数化）、开关真能关、后台四个控件齐全且
  开关被 `label` 包裹、非法值不落库但其它字段照常保存、开关进配置快照、
  前台外链必须带 `rel="noopener"`。变异验证：拆掉出口过滤 → 5 条立刻变红。
- 全量 **771 passed**（744 + 27 新增）；`ruff check .` 全仓 **0 error**；
  lint 棘轮 **486**（基线 490，无新增债务）。

## v3.25.16（2026-10-07 · 4.0 开发前的全量安全审计修复：R114 + R115）

> 发版动因：大帅要求「全量审计一下，准备开发 4.0，**有漏洞未修好之前不发 4.0**」。
> 本次把审计发现的**线上正在生效**的缺陷先修掉发补丁版，不等 4.0。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、无新增**必填**环境变量。
> 完整报告见 `docs/audit/2026-10-07-full-audit-report.md`。

### 一、修了什么（5 个中危 + 4 个低危）

| # | 漏洞 | 位置 | CWE |
|---|---|---|---|
| 1 | **友链 RSS 聚合 SSRF** | `myblog/feed_agg.py` | CWE-918 |
| 2 | **RSS 条目 `javascript:` 存储型 XSS** | `myblog/feed_agg.py` → `SquareView.vue` | CWE-79 |
| 3 | **SMTP 授权码明文落库** | `myblog/admin/settings.py` | CWE-312 |
| 4 | **OG 封面路径穿越（可逃逸到文件系统根）** | `myblog/og_image.py` | CWE-22 |
| 5 | **评论无长度上限 → 通知扇出放大 DoS** | `myblog/api/posts.py` / `api/social.py` / `utils/web.py` | CWE-400 |
| 6 | 可见性收口 3 处（裸查 `Post`） | `api/stats.py` / `api/reactions.py` / `api/ai.py` | CWE-863 |
| 7 | MCP 非 ASCII Bearer → 未捕获异常 → 匿名 500 | `mcp_diag.py` / `mcp_write.py` | CWE-248 |
| 8 | `/mcp-write` 未列入 CSRF 豁免 → **端点实际不可用** | `myblog/app.py` | 功能缺陷 |

### 二、三条最值得记的

**1. SSRF 的根因是「校验与使用分离」。** `_safe_url()` 做了三层防护（scheme 白名单 → 主机名黑名单
→ `getaddrinfo` 判私网），但它只在**抓取前**查一次；真正发请求的 `feedparser.parse(url)`
**自建 urllib 会话** —— 重新解析 DNS（重绑定）+ **自动跟随 3xx**。于是攻击者用一个**公网** RSS
地址通过校验，再回 `302 Location: http://100.100.100.200/`（阿里云元数据）或内网
Redis/MySQL/PG，跳转目标**从不被复检**。触发入口 `/api/feed/circle` 是**匿名 GET**。

修法：自己用**禁重定向**的 opener 抓字节，再把字节喂给 feedparser——这一步同时消除了
「重复解析 DNS」的重绑定窗口。同仓库的 `seo_push.py` / `oauth.py` **早就有这个标准答案**。

**2. 「配了」不等于「用上」。** 三条修复都栽在同一个形状上：
`_safe_url` 配了却没被 fetch 用；`GH_MIRROR` 传了却排在直连之后；白名单写了却没 bump 版本号。
**配置/防护的存在 ≠ 它在关键路径上生效。**

**3. 代码库自己早就知道答案。** SMTP 授权码明文落库，而 `admin/seo.py:12-14` 的注释写着
「**不照抄 `mail_password` 的明文落库错误做法**」——备份密钥与 SEO token 早已 Fernet 加密，
唯独它是历史遗漏。**注释里的自我要求比代码更能暴露「哪里还没改」。**

### 三、一条**误报**（记录以免重复告警）

有审计组报出「**严重：2FA 完整绕过**」并附可执行 PoC（仅密码会话调 `/api/auth/2fa/enroll`
重置密钥、`enabled` 被打回 False）。主审**未采信转述**，写真实攻击链实测：

| 场景 | 实测 |
|---|---|
| 闸门开启 + 账号已 `enabled=True` + 仅密码会话 | `enroll` → **401**，`secret_enc`/`enabled` **零变化** |
| 同一会话访问 `/admin/` | **401/302/403** |
| **全局开关关闭**（出厂默认）时 `twofa.enroll(user)` | 返回非 `ok`，绑定**零变化** |

根因是把 `twofa_enabled` **默认 false** 的状态当成了「2FA 已启用」。**不写入漏洞清单。**

### 四、验证

- **697 passed**（新增 `tests/test_audit_r114.py` / `tests/test_twofa_gate_r115.py` /
  `tests/test_render_allowlist_ratchet.py`）、`ruff check myblog/ tests/` 全绿
- **5 项变异测试精确变红**：AST 门禁（漏改的 `feedparser.parse`）、白名单棘轮、
  2FA 闸门、`_readable_comment` 可见性守卫、RSS 302 拒绝
- 完整报告：`docs/audit/2026-10-07-full-audit-report.md`

### 五、⚠️ 升级后必做一步

新写入的 SMTP 密码已是密文，但**存量明文仍在库里**。用新增的幂等迁移脚本转一次：

```bash
cd /www/wwwroot/myblog
set -a; . /www/server/python_project/vhost/env/myblog.env; set +a
FLASK_APP=app:create_app /www/server/pyporject_evn/blog_env/bin/python tools/migrate_mail_password.py
```

脚本会：已是 `bkenc$` 密文则跳过（可重复跑）→ 加密后**立刻回读比对**，不一致就放弃写入。
**另请注意**：明文曾存在于历史备份文件里，按需清理过期本地备份或**轮换 SMTP 授权码**。

## v3.25.15（2026-10-07 · 让 `GH_MIRROR` 真的用上：镜像优先）

> 承接 v3.25.14 上线时实测到的怪事：**明明传了镜像参数，部署却仍走直连苦等**。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖；**纯脚本变更，
> 前端产物无变化**。

### 一、问题：传了 `GH_MIRROR` 却一次都没轮上

v3.25.14 部署时同一时刻、同一台服务器实测：

| 通道 | 速度 | 3 MB 后端包耗时 |
|---|---|---|
| `gh-proxy.com` | **873 KB/s** | ~4 秒 |
| `ghfast.top` | 452 KB/s | ~7 秒 |
| 直连 GitHub | 21 KB/s | **133 秒** |
| `ghproxy.net` | 15 KB/s | >200 秒 |

部署命令带了 `GH_MIRROR='https://gh-proxy.com/'`，但 `update.sh` 的 `gh_fetch()` 是
`try_urls=("$url")` —— **直连排第一，镜像只是第二顺位兜底**，且每条 URL 各重试 2 次、
`--max-time 180`。直连第一次就成功了（只是慢），镜像于是**一次都没用上**，白等 133 秒。

🔑 **「配了镜像」≠「用上镜像」** —— 兜底位的东西，只有在前面全失败时才会被想起。

### 二、修法

1. 新增 **`GH_MIRROR_FIRST`（默认 `1`）**：显式配了 `GH_MIRROR` 时**镜像优先、直连兜底**；
   设 `GH_MIRROR_FIRST=0` 可取回旧的「直连优先」顺序。
2. 前置条件两个缺一不可（`GH_MIRROR` 非空 **且** 开关为 1），避免未配置时拼出空前缀 URL。
3. **安全性不变**：无论走哪条通道，产物都要过 Ed25519 验签 + zip 注释内嵌哈希双源互证。
   镜像最坏只能给出**旧版本的合法签名**（版本单调性由 `ALLOW_DOWNGRADE` 兜着），
   无法伪造内容——这与它原本作为兜底位时的风险面一致。

### 三、验证

- 新增契约断言 `test_gh_mirror_is_tried_first_when_configured`
  （`tests/test_update_chain_contract.py`）：钉住默认开关值、镜像优先的数组顺序，
  以及「`GH_MIRROR` 非空 **且** `GH_MIRROR_FIRST=1`」这个双重前置条件。
- 变异测试：把镜像优先分支删掉 → 该断言精确变红。

## v3.25.14（2026-10-07 · 修「定时任务跑的备份永远失败」：缺 `SECRET_KEY`）

> v3.25.13 上线后做了端到端实测：**直接跑 `backup.py run` → `远程[webdav]: ✅ ok`，
> 但跑 `backup.sh`（计划任务走的那条）→ `401`**。顺着这条差异查，挖出比「根目录只读」
> **更靠前**的真因。无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、
> 无新增环境变量；纯后端 + 脚本变更，**前端产物无变化**。

### 一、真因：计划任务不带 `SECRET_KEY`，密文解不开 → 空密码 → 401

后台「⚙️ 备份配置」里填的 OSS Secret / WebDAV 密码是 **Fernet 密文**，解密要用
`SECRET_KEY` 派生的密钥（`backup_settings.decrypt_secret`）。

- gunicorn 由宝塔带 env 启动 → 有 `SECRET_KEY` → 能解 → 后台点「测试」一切正常；
- **计划任务不带任何项目环境变量** → `_fernet_key()` 抛 `RuntimeError`，
  而 `decrypt_secret()` 的设计是**失败返回空串、绝不抛异常** → curl 拿着**空密码**
  去认证 → 只得到一句 `401`。

线上实证（同一台机器、同一份配置，只差一个环境变量）：

| 跑法 | 结果 |
|---|---|
| `env -u SECRET_KEY python3 backup.py run` | `error: 401`（模拟计划任务） |
| 带 `SECRET_KEY` 跑 | `远程[webdav]: ✅ ok` |

也就是说：**在 v3.25.14 之前，每天凌晨的异地容灾备份从来就不可能成功** ——
「根目录只读」只是压在它上面的第二个问题。

### 二、修法（三处）

1. **`backup.sh` 先加载站点环境变量文件**（含 `SECRET_KEY`；路径可用 `BACKUP_ENV_FILE` 覆盖，
   文件不存在则跳过并告警，非宝塔部署不受影响）。
2. **`_secret_unreadable()`**（新增）：库里存着密文但当前解不开时**明确报错**，
   不再拿空密码去撞 401 —— `sync_webdav()` 与 `probe_webdav()` 都会在发起请求前拦下。
3. **`_webdav_hint()` 把 401/403 与 404/405 分开提示**。
   🔴 **这是 v3.25.13 自己引入的文案缺陷**：当时把 `40[1345]` 一并翻成「目录只读」，
   于是定时任务因缺 `SECRET_KEY` 报出的 401 被提示成「请改填子目录」——**指错了方向**。
   现在 401/403 → 认证失败（并点出「后台测试正常、定时任务失败 = 没加载 `SECRET_KEY`」）；
   404/405 → 目录不可写/不存在；stderr 为空无法分辨时两条都给，不瞎猜。

**22 passed**（`tests/test_backup_webdav.py`，+7）/ ruff 全绿 / 棘轮 490=490 /
**三项变异精确变红**（退回旧的单分支提示→1 条红、撤「解不开的密钥」拦截→1 条红、
`backup.sh` 不加载 env→1 条红）。

> 第一次跑变异时 MUT-A 判成「没变红」—— 是**测试不够强**（变异后落到含糊的兜底分支，
> 仍含「认证失败」字样），已把断言收紧为「已知是 401 就不该再提 404/405」。

### 三、生产侧的连带处置（已做，非代码）

`MKCOL` 在坚果云建了 `blogbackup` 目录（**201 Created**，PROPFIND 确认含 `<d:write/>`），
并把库里 `backup_webdav_url` 从只读的 `/dav/` 改到 `/dav/blogbackup`。
随后一次真实备份端到端成功：云盘里出现 `blog_backup_20261006_235907.zip` +
`manifest_20261006_235907.json`。

## v3.25.13（2026-10-06 · 修「WebDAV 云盘备份配置好了却异常」+ 文档瘦身）

> 大帅反馈三件事：① README 被版本史堆满，要「极致的简化」；② 版本更新信息必须统一并入
> 更新文档、部署文档同步更新，且**流程要固定在开发技能里**；③ **后台 WebDAV 备份配置好之后备份异常**。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、无新增环境变量；
> 仅后端 + 模板变更，**前端产物无变化**。

### 一、WebDAV 备份：从「不知道为什么失败」到「填完当场就知道」

线上取证：后台「WebDAV 云盘」地址/用户名/应用密码**都填好了**，配置页显示「✅ 已配置」，
但**备份每天失败**；而页面只报 `命令退出码 22` —— 既看不出 404 还是 401，也看不出是地址错、
凭据错还是目录只读，**等于没法自助排障**。生产审计日志自 2026-09-12 起只有「后台任务已提交」，
**一次「备份成功」都没有**。

用真实密钥解密后直连坚果云实测：

| 动作 | 结果 | 含义 |
|---|---|---|
| PROPFIND `https://dav.jianguoyun.com/dav/` | **HTTP 207** | 认证其实是**好的** |
| `current-user-privilege-set` | 只有 `<d:read/>` | **根目录只读** |
| PUT 一个测试文件 | **HTTP 404** | 写入被拒 → 备份必然失败 |

两个真因叠加：

1. **填的是根目录，而不少云盘的根目录只读**（坚果云 `/dav/` 实测只有 read 权限）。
2. `apply_env()` 只在 `backup.py` **被导入时**跑一次，后台保存只作用于**处理保存请求的那个 worker**；
   gunicorn 多 worker 下，落到别的 worker 的备份任务仍用**导入那一刻**的旧值 ——
   而页面明确写着「保存后立即生效（无需重启）」。

三处修改：

- **错误文案能自助排障**：`_cmd_err()` 带上 curl 的 **stderr**（原因早写在里面，原来被丢掉了）；
  `_webdav_hint()` 把 4xx / 退出码 22 翻译成「目录只读，请改填可写的子目录」。
- **新增 `probe_webdav()`**：用 `PROPFIND` 读 `current-user-privilege-set` 里有没有 `<d:write/>`
  判可写性（**不写任何文件**），返回 `ok` / `auth_failed` / **`not_writable`** / `missing` /
  `unreachable` / `unconfigured`；后台加「🔌 保存并测试 WebDAV」按钮（先落盘再探测，5 次/分钟限流），
  WebDAV 区块加「根目录只读」的醒目提示。
- **新增 `_refresh_env()`**：`create_backup()` 与 `probe_webdav()` 开头各调一次，
  **不靠导入时机**，任何 worker、任何时刻都用最新后台配置。
  顺带把模块级 `apply_env()` 失败从静默 `pass` 改成 `logger.warning`
  （原先一静默，表现就是「配置页显示已配置、备份却不上传」）。

**670 passed**（647 → 670，新增 `tests/test_backup_webdav.py` 15 条 +
`tests/test_readme_no_version_history.py` 5 条 + 归档守卫 3 条）/ ruff 全绿 / 棘轮 490=490 /
**变异四条精确变红**（撤 `<d:write/>` 判定→1 条红、撤 `_refresh_env()`→6 条红、
撤 stderr→1 条红、撤提示翻译→1 条红）。

> 写这个探针时踩的两个坑已写进技能：① `raw.rpartition("\n")` 返回 `(head, sep, tail)`，
> 写成 `code, _, body = ...` 会静默把正文当状态码 → 全部判成 `unreachable`（被测试当场抓出）；
> ② `read_setting_db()` **脱离 Flask app_context 会退回 sqlite3 直连 `myblog/data/blog.db`**（真实库）
> → 测试里调备份函数必须包 `with app.app_context():`，否则是假红。

### 二、README 极简化 + 版本史单一真相源

README 一度被逐版追加的版本说明堆到 **137 行（正文近半是版本史）**，与 CHANGELOG 重复且必然漂移。
按「极致简化」重做：

- `README.md` **137 → 69 行**、`myblog/README.md` **201 → 163 行**；
  版本史整段删除，只留「当前版本：**v3.25.13**」一行 + 指向 CHANGELOG 的链接。
- 功能一览改为**当前能力清单**：不再标版本号、不再写「⚠️ 口径更正」、不再复述某版的取舍与根因
  （那些属于 CHANGELOG / ROADMAP / SECURITY_AUDIT）。
- 顺手修一处**写了两年的错口径**：`myblog/README.md` 里「`flask db heads` 应为 `e5b8c3f17a24`」，
  实际 head 是 **`c7a2f19b4d30`**。

**并把它固化成门禁，而不只是写进技能**（「门禁不在发版路径上 = 等于没有门禁」，
同一条已在 lint 棘轮上验证过一次）：`tools/review/check-staged.py` 新增两条**硬拦截** ——

- README（根 + `myblog/`）里出现 `## vX.Y.Z` / `- **vX.Y.Z：…**` 形态的版本史条目 → **退出码 1**；
- `myblog/config.py` 版本号变了但 `CHANGELOG.md` 未同批提交 → **退出码 1**；
  且两份 README 必须含新版本号。

同时写进 `blog-release` 技能（纪律二新增「README 极简 + 版本史单一真相源」硬规则 +
机械自检命令，经验 64/65）。

### 三、顺带：安全审计报告再归档一轮

本轮新增 R111 后 `SECURITY_AUDIT.md` 涨到 **162.6 KB**，触发
`tests/test_doc_archival.py` 的体积守卫（上限 160 KB）。按项目自身「新增轮次写进主文件、
历史段落才归档」的原则，把 **R81~R90**（v3.18.0 ~ v3.19.0）搬到
`docs/archive/SECURITY_AUDIT_r81-r90.md`（40.1 KB），主文件回到 **123.3 KB**
（而不是抬阈值 —— 抬阈值等于把守卫关掉）。守卫 `PAIRS` 同步加一条，16 条全绿。

## v3.25.12（2026-10-05 · 修「用绑定的第三方账号登录报 401」）

> 大帅实测：**2FA 用账号密码登录能跳到验证页，用已绑定的 GitHub 账号登录却报 401**。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、无新增环境变量；
> **前端产物有变化**（登录页 + `api.js` 兜底）。

### 诊断：先取证

`?oauth=ok` 之后 SPA 的每个请求都是 401（49 字节，即 `{"error":"twofa_required",...}`）：

```
GET  /?oauth=ok                      → 304   ← 回调**成功了**，登录态已建立
GET  /api/posts?page=1&page_size=8   → 401
GET  /api/site                       → 401
GET  /api/stats/summary              → 401
…… 共 17 个 /api/* 全 401
GET  /api/auth/me                    → 200   ← 例外：它在闸门白名单里
GET  /api/csrf                       → 200   ← 同上
```

### 根因：两条登录路径契约不一致

| | 账号密码登录 | 第三方登录（修复前） |
|---|---|---|
| 需要二步时 | **只挂起** `twofa_pending_*`，会话里**没有** `user_id` | 照样写下 `session["user_id"]`，置 `twofa_ok=False` |
| 返回给前端 | `200 + twofa_required` → 前端弹动态码框 | `302 → /?oauth=ok`（前端不知道要验二步） |
| 结果 | ✅ 跳验证 | ❌ 会话落在「已登录但没过二因素」，SSR 被赶去 `/twofa`，SPA 的每个 `/api/*` 都是 401 |

即：`enforce_twofa` 闸门**工作正常**（SSR 重定向 / API 401 都是设计行为），
缺的是「OAuth 这条路**没有接上第二步**」——前端只认 `/api/auth/login` 的
`twofa_required`，对 401 没有任何处理，于是整页接口全红、登录像是失败了。

### 修法（四处，全部对准同一条契约）

1. **`oauth_callback`**：目标账号开了两步验证时**只挂起**、不写 `user_id`，
   落点改 `/login?twofa=1` —— 与 `auth_login` 完全一致。
2. **登录页**：`?twofa=1` 时**问服务端** `/api/auth/2fa/status` 的 `pending`，
   为真才切到「输动态码」步骤（同一张表单、同一句话）。
3. **`api.js` 兜底**：任何 `401 + twofa_required` 一律跳 `/login?twofa=1`。
   收口在请求层而不是逐个调用点补 —— 再有别的路径漏接二步，也不会死在一片 401 里。
4. **`twofa_verify` 补登录审计**：第二因素通过才算登录成功。

### 🔴 改到一半才发现的：线上 `/twofa` 根本到不了

落点一开始写的是 `/twofa`（`enforce_twofa` 对 SSR 路径就是这么跳的），查生产
nginx 才发现**那条路在线上是死的**：

- `location / { try_files $uri $uri/ /index.html; }` + `root /www/wwwroot/vue-frontend`
  → `/login`、`/register`、`/twofa` **全被当成 SPA 静态页**（只有 `/api/`、`/admin`、
  `/static/`、`/mcp` 等显式 `location` 才反代到 gunicorn）；
- 而 SPA 路由表（`vue-frontend/src/router.js`）里**没有 `/twofa`**，
  命中兜底 `/:pathMatch(.*)*` → redirect `/` → 首页 → 又是一堆 401 → 再跳……**死循环**；
- 访问日志佐证：`/twofa` 在本次排查期间出现 **0 次**（连被闸门重定向的记录都没有）。

所以落点必须是 SPA 真实路由 `/login`。**同一份代码在本机（Flask 直连）与线上
（nginx 静态优先）的行为不同** —— 这也解释了为什么 `/?oauth=ok` 是 304 而不是
闸门期待的 302：那条请求压根没进 Flask。

> 📌 **本条已在 2026-10-06 线上应用**（经你确认后改的生产 nginx，已回滚备份
> `html_www.llhhy.cn.conf.bak-20261006`）：加了
> `location = /twofa { proxy_pass http://127.0.0.1:8686; }`，
> 配置原文已同步进 `myblog/deploy_guide.md` 的 nginx 片段（避免「只存在于线上、重装即丢」）。

### 顺带修掉的：开了 2FA 的账号**一条成功登录审计都没有**

v3.21.2 定了「密码对但未过第二因素不得记成功」，但**通过之后**没人记 ——
于是开了 2FA 的账号，无论账号密码还是第三方登录，登录审计里都是空的，
恰恰是最该看的一类。现补在 `twofa_verify` 里（一处修好两条路径）。

### 验证

**647 passed**（641 → 647，+6，新增 `tests/test_oauth_twofa.py` 6 条）/ ruff 全仓全绿 /
棘轮 490 = 490 / **变异三条精确变红**（撤挂起分支 → 3 条红；撤审计 → 1 条红；
撤 `status.pending` → 1 条红）。构建产物已实测含新逻辑：`LoginView-*.js` 有
`twofa=1` 分支与 `2fa/status` 调用、`index-*.js` 有 `/login?twofa=1` 兜底。

### 边界不变

仍是 **v3.25.11 那条能力边界**：第三方登录只对「能访问 GitHub 的人」有用，
国内访客访问不到 GitHub —— 这是网络现实，代码解决不了。

## v3.25.11（2026-10-05 · 修「点击绑定不跳转」—— 浏览器拦截跨站自动重定向）

> v3.25.10 上线当天大帅即报「第三方账号绑定点击绑定不会跳转」。**不是网络问题，也不是代码错误**。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、
> 无新增环境变量、**前端产物无变化**。

### 诊断：先看证据，再猜原因

访问日志给出决定性证据 —— 用户（Edge 浏览器）在 22:50:02~22:50:11 **连点 7 次**：

```
POST /admin/oauth/bind/github                    → 302  ✓（每次都对）
GET  /api/auth/oauth/github/start?redirect=1     → 302  ✓（Location 指向 github.com 授权页）
                                                     …… 而 callback 一次都没出现
```

链路分段实测：

| 环节 | 结果 |
|---|---|
| 服务端两次重定向 | **全部正确** ✓ |
| 服务器 → github.com | 302，0.5 秒 ✓ |
| **用户手动输入**同一 URL | **能看到授权页** ✓（用户实测） |
| 服务端 `callback` | **零次** —— 浏览器从未到达 GitHub 授权页 |

**结论**：拦截的是「**页面发起的跨站自动重定向**」（Edge 跟踪防护 / Strict Blocking），
不是网络不可达、不是 GitHub 侧问题、也不是凭据填错。

### 修法：不要自动跳，改成让用户主动点

`oauth_bind` 不再 `302` 到 provider，改为渲染**中间确认页**：

- 页面上给一个 `target="_blank" rel="noreferrer noopener"` 的「前往 GitHub 授权 →」按钮；
- 浏览器对**用户发起**的导航基本不拦，对**页面自动发起**的重定向才会拦；
- 顺带好处：新标签打开不会把本站页面留在身后，授权完切回来还能看到绑定页状态。

### 验证

**641 passed**（639 → 641，+2）/ ruff 全仓全绿 / 棘轮无新增 / **变异「改回自动跳转」3 条变红**
（含专门的回归守卫 `test_bind_renders_interstitial_not_auto_redirect`）。

### ⚠️ 这条路的能力边界（必须说清）

**本版只解决「你自己能绑自己的 GitHub」。** 对**国内访客依然无效** ——
他们访问不到 GitHub，这是网络现实，代码解决不了。
而且当时的渠道选型（v3.25.7）我只验了**配置门槛**（免费/易得），
**没验网络可达性** —— 那是与「微信要企业资质」同等级的前置条件，漏判了。

## v3.25.10（2026-10-05 · 第三方账号「绑定」入口 + 修掉一个静默身份切换）

> 大帅问「我要绑定第三方账号，应该在哪里绑定」—— 答案是** nowhere**：此前根本没有入口。
> 顺手还挖出一个**存量安全缺陷**（静默身份切换），一并修掉。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、
> 无新增环境变量、**前端产物无变化**。

### 缺口：机制是通的，但没有入口

v3.21.0 的 OAuth 实现里，`api/auth.py::oauth_callback` 早就写明
「已登录时回调 = 用户主动把第三方身份**绑到自己这个账号**」——
但 `/admin/oauth` 页**只有查看 + 解绑**，没有任何"开始绑定"的按钮。
用户看得见「第三方绑定」这个菜单，点进去发现只能解绑、不能绑。

而且绑定完成**连一句提示都没有**：`callback` 跳 `?oauth=ok` 回首页，
而全项目**没人读这个参数**（`store.js` 的注释写着「callback 用 ?oauth=ok|error 回首页」，
但没有实现）。

### 🔴 顺手修掉的存量缺陷：静默身份切换

`oauth.find_or_create_user` 原先是这样：

```python
link = OAuthAccount.query.filter_by(provider=provider, sub=sub).first()
if link:
    return db.session.get(User, link.user_id)   # ← 无条件返回那个人
```

**场景**：X 已登录 → 走 OAuth → 授权的第三方账号 G 其实**已经绑给 Y** →
这里 `return Y` → callback 把 `session["user_id"]` 写成 Y →
**X 的浏览器被静默切成 Y 的身份**。

这条路径**在加绑定入口之前就能触发**（`oauth_start` 是 GET、无 CSRF），
但那时它属于边缘情况。加了绑定入口后它会变成**常见路径**，所以必须先堵：
`(provider, sub)` 命中已有绑定、且**不是当前会话用户**时 → 明确拒绝。

危害本身有限（攻击者不获利，受害者只是丢了会话），但「我明明绑自己的账号，
怎么登录成了别人」对用户是完全不可接受的行为。

### 做了什么

- **`POST /admin/oauth/bind/<provider>`**（`@login_required`）：校验渠道存在 + 已启用 +
  未重复绑定 → 在会话里标记「本次是绑定流程」→ 转发到既有 `oauth_start`。
  - ⚠️ **必须是 POST + CSRF，不能做成 GET 链接**：真正的授权发生在 provider 那边
    （用户要点确认），所以单靠 GET 不足以被静默利用；但绑定目标取自服务端 session
    的 `user_id`，做成 `<a href>` 就会变成「任何人发个链接诱导他人发起绑定」。
- **`oauth_start` 新增 `?redirect=1` 无 JS 降级**：默认仍返回 JSON 给前端
  `store.js` 消费（**行为完全不变**）；带 `redirect=1` 时直接 302 到 provider。
  起因是第一版实现把管理员重定向到了一个**返回 JSON 的 API 端点**——
  点了只会看到一片 JSON。
- **绑定结果 flash 回绑定页**（成功 / 冲突 / 失败三种），并说明
  「若已开启两步验证，接下来需重新输一次动态码」（`twofa_ok` 被刻意复位，
  这是安全设计，不是 bug）。
- **超管代他人绑定不提供入口**：没有任何正当场景，且它正是静默身份切换最容易发生的地方。
- 未配置凭据时**按权限分层**：超管看到「未配置 + 去配置 →」，普通用户只看到「站点尚未启用」。
- 页面明说「绑定不影响你原有的用户名密码登录，它是多一条登录方式」。

### 验证

**639 passed**（625 → 639，+14）/ ruff 全仓全绿 / 棘轮无新增 / **三项变异全红**：
绑定冲突检测被短路 → 1 条；绑定端点放开 GET → 1 条；绑定后不重定向回绑定页 → 1 条。

🔑 **v3.25.9 刚把棘轮接进发版路径，v3.25.10 当场就被它拦了一次** ——
我新写的测试文件里有个没用的 `import time`（F401），门禁直接判 error。
上一版之前，这种欠债要攒到下一个版本才看得见（这正是它攒了六个版本的原因）。

### 📌 变异测试：同一天内第三次「变异无效」

这个缺陷的变异我**连写错三次**，前三次都「没变红」：

1. 在判断**之前**加 `if False: pass` —— 根本不影响它后面的语句；
2. 加了**两个** `raise`，短路了第一个但第二个照常执行；
3. 把条件改成 `... and bound.id != int(bind_user_id) and False` —— 这次才**真正**
   短路，守卫立刻精确变红。

**「没变红」有两种可能：守卫无效，或变异无效。** 前者要改测试，后者要改变异 ——
**必须当场分辨清楚**，否则会误删有价值的守卫，或误以为某段代码没有守卫。
判据：动手前先确认「我改的那几行，是不是唯一决定该分支行为的代码」。

## v3.25.9（2026-10-05 · 还清 lint 棘轮欠债 + 把棘轮接进发版路径）

> 这一版是**还债**，不是加功能。起因：v3.25.7 手动跑 `tools/lint_debt.py` 时
> 发现 v3.25.0~v3.25.6 期间攒下的 `SIM +21 / BLE001 +9 / S110 +4` 一直没人看见。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、
> 无新增环境变量、**行为零变化**（全是等价重构）、前端产物无变化。

### 诊断：三个假设，两个被否

1. ❌ **不是 ruff 版本扩容** —— 基线生成于 2026-09-23，当时最新版就是 **0.16.8**，
   与本地 venv 同版本；另装 **0.16.10**（CI 实际会装的）实测，SIM/S110/BLE001
   数字**完全相同**（61 / 374）。
2. ❌ **不是基线虚低** —— 用 `git worktree` 检出 v3.20.0 时点跑 ruff 0.16.8：
   SIM=**40**、ARG=**10**、T20=**66**，与基线记录**完全一致**。
3. ✅ **确证是真实新增**，逐文件增量：`tests/test_admin_table_data_label.py` **+11**
   （v3.25.0）、`cert_watch.py` +2、`test_cert_watch.py` +2、`test_doc_archival.py` +2、
   `test_config_rollback.py` +1、`backup.py` +1、`app.py` +1、
   `test_no_module_import_cycles.py` +1、`api/theme.py` +1、`api/common.py` −1。

### 还债：SIM105 改 `contextlib.suppress`

34 处 SIM105 的形态全是 `try: ... except Exception: pass` ——
改 `with contextlib.suppress(Exception):` **行为完全等价**。

- 31 处用 `ruff check --select SIM105 --fix --unsafe-fixes`（官方 fix，diff 逐条看过）；
  2 处 ruff 保守没改（一条 try 体带行内注释、一条在 `finally` 内）**手工改**并注明原因。
- **一项改动连带降三样**：`try/except/pass` 同时命中 S110，所以 S110 也降了：
  BLE001 **269 → 248（−21）**、S110 **92 → 66（−26）**、SIM **40 → 28（−12）**、
  F401 171 → 117、T20 66 → 21。**合计 648 → 490。**

### 🔑 更重要的：把棘轮接进发版路径

`check-staged.py` 新增第 5 步——**后端源码变更时自动跑 `tools/lint_debt.py`，
新增债务直接**拦截**（不是警告）**。

**为什么必须接**：棘轮原本只是 CI 的一个 job，而 CI 在发版之外 ——
于是六个版本的欠债一直攒着，每次发版门禁都放行。**门禁不在发版路径上 = 等于没有门禁。**
这是 v3.25.6 那三条（sitemap 脏值 / 时间口径 / 填完 site_url 不重跑）
和 v3.25.7、v3.25.8 两次「功能从未启用」**同源的第五次复发**，根因都是「没验证」。

已实测拦截：把基线人为压到 `SIM: 1` → 门禁**退出码 1** 硬拦截；还原 → **退出码 0** 放行。

### 基线收紧

`--update` 把基线从 648 锁到 **490**（分类：BLE001 248 / F401 117 / S110 66 / SIM 28 /
T20 21 / ARG 10）。**这次是「真修完后的新基线」，不是掩盖** —— 与「新增规则就先抬基线」
是两回事：后者才失去棘轮意义。

### 验证

**625 passed**（与改动前一致，证明 33 处转换行为等价）/ ruff 全仓全绿 / i18n 通过 /
门禁拦截与放行均实测通过。

## v3.25.8（2026-10-05 · 运营开关进后台，2FA 终于能开）

> 第三方登录（v3.25.7）之后紧接着被投诉「2FA 也不好用，还要我去配置服务器」——
> **同款缺陷的第二次出现**。这次做了根因级的处理，不只是补一个开关。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增依赖、
> 无新增环境变量、**前端产物无变化**。

### 先说清楚：2FA 从 v3.21.0 上线起就一直关着

生产实测 `/www/server/python_project/vhost/env/myblog.env` 里**只有 5 个变量**
（`SECRET_KEY` `ADMIN_PASSWORD` `SITE_URL` `MCP_AUTH_TOKEN` `MCP_WRITE_TOKEN`），
**没有 `BLOG_TWOFA_ENABLED`** → 全局开关为 false → 2FA 整条链路休眠。

而 `admin/twofa.html` 上写着一句「需先在服务器环境变量设置 `BLOG_TWOFA_ENABLED=true`
并重启应用」——**告诉人怎么改服务器，却不给入口**。要开它得：SSH（或宝塔面板）
→ 编辑 env 文件 → 加一行 → **重启 gunicorn**（4 个 worker 全断）。

### 根因处理：先分类，再决定搬不搬

扫了全部 61 个环境变量，**不是所有 env-only 都是缺陷**。判据是
「运营会不会频繁改」×「读取频率」：

| 类别 | 例子 | 搬进后台？ | 理由 |
|---|---|---|---|
| **低频读、要常改的运营开关** | 2FA / 开放注册 / 验证码 / 强密码 / 登录延迟 / 审计保留 | ✅ **搬** | 就是这批在被投诉 |
| **根信任** | `SECRET_KEY` `ADMIN_PASSWORD` `DATABASE_URL` `MCP_*_TOKEN` | ❌ **永不** | 存进 DB = 拿到 SQL 注入或备份文件的人顺带获得伪造会话 / 改管理员密码的能力 |
| **每请求都判断** | `COOKIE_SECURE` `CORS_ORIGIN` `TRUSTED_PROXIES` `SESSION_IDLE_MINUTES` | ❌ 不搬 | 每次会话校验查一次库，是用数据库换一行配置 |
| **启动时读** | `ENABLED_PLUGINS` | ❌ 不搬 | 进 DB 照样要重启才生效，放后台只会给人「改了没用」的错觉 |

这三条判据写进了页面本身（`系统设置`页底部「刻意不放进本页的配置」），
免得下次又有人来问「为什么 `SECRET_KEY` 没有开关」。

### 做了什么

- **`utils.flag_bool()` / `flag_num()`**：统一取值 **Setting 表 → 环境变量 → 默认**。
  - DB 优先 = 后台能改、**改完不用重启**（本项目既定语义，同 `site_base()`）
  - env 兜底 = 老部署行为**完全不变**
  - 非法值**当作未设继续往下走**而不是直接回落默认 —— 因为页面显示的「来源」标签
    走的是同一个函数，直接回落默认会让页面显示「来源：数据库」而实际生效的是默认值，
    **标签与行为不一致**
- **改 13 处读点**：`app.py`（`before_request` 闸门）、`api/auth.py`（2 处）、
  `routes.py`（2 处）、`admin/twofa.py`、`admin/_helpers.py`、`api/common.py`、
  `admin/stats.py`（3 处）、`audit.py`、`diagnostics.py`。
  `captcha_enabled` 早有 DB 优先先例（`security.py` 的 `_cfg_bool`），本页只是把它暴露出来。
- **新增「⚙️ 系统设置」页**（超管区，紧邻第三方登录）：7 个开关分「安全 / 注册 / 运维」三组，
  每项显示**当前生效值 + 来源**（数据库 / 环境变量 / 默认）+ 默认值 + 环境变量名；
  支持「恢复默认」（删除本页覆盖、交还环境变量）；越界值拒绝并提示；
  审计记录**改动前后值**（这些开关都不是密钥，明文记值才能回溯「谁把 2FA 关了」）。
- `twofa.html` 的提示改成指向新入口，不再让人改服务器。

### 🔑 变异测试抓出的一个真实守卫漏洞

第一次做变异时，我把 `app.py` 的 `before_request` 闸门退回成读 `app.config`
（即 v3.21.0 原行为），**测试全绿**。

原因：闸门在 `app.py`，而登录流程的开关判定在 `api/auth.py::_twofa_on()` ——
**两处独立读点**，我最初的守卫只测了后者。**攻击者走的正是闸门**，
绕过它等于 2FA 形同虚设。已补 `test_before_request_gate_actually_honors_the_switch`
（造一个已绑定的用户 + 真开关，验证页面 302 到 twofa、API 401 带 `twofa_required`），
重跑变异精确变红。

> 附：第一次变异我写成了 `if False: pass` 放在 `v = get_setting(key)` 之后 ——
> **根本没断掉读库**，所以「没变红」是变异无效而不是守卫无效。这类假阴性要当场识破。

### 验证

**625 passed**（607 → 625，+18）/ ruff 全仓全绿 / i18n 通过 / **三项变异全红**：
`flag_bool` 不查库 → 4 条；`before_request` 闸门退回读 config → 1 条；
保存不落库 → 4 条。

安全审计 **R106**。无表结构变更、无迁移、无新增依赖、前端产物无变化。

## v3.25.7（2026-10-05 · 第三方登录终于能用了）

> 大帅反馈「第三方登录太难用」。查完发现不是难用，是**从来就没能用过**。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增环境变量、
> 无新增依赖、**前端产物无变化**（按钮本来就是动态渲染的）。

### 先说清楚：功能此前是死的

生产实测（本次改动前）：

```
GET /api/auth/oauth/providers  →  {"providers":[]}
curl /login | grep -c -i oauth  →  0
```

`LoginView.vue:35` 的渲染条件是 `v-if="state.oauthProviders.length"` —— 空数组
**整个区块不渲染**，所以访客看到的登录页上**一个第三方按钮都没有**。

根因：v3.21.0 把后端（`oauth.py` 205 行）与前端（按钮 + `store.js`）都写完了，
**唯独没留配置入口** —— 凭据只能改环境变量再重启 gunicorn。
而绑定页只写了一句「需设置 `OAUTH_GITHUB_CLIENT_ID/SECRET` 并重启」，
**没说去哪儿注册、回调地址填什么**。

> 教训：我上一轮说「前端已有 GitHub 按钮」是**只看了代码、没验证线上效果**。
> 补测线上才发现按钮从未出现过。**「代码写了」≠「功能生效了」。**

### 补上什么

- **后台「🔑 第三方登录」配置页**（`admin/oauth_settings.py` + 模板，超管可见）：
  - 每个渠道一张卡：**三档状态**（已启用 / **只填了一半·不生效** / 未启用）——
    两档模型会把「只填了 ClientId」显示成「未启用」，让人反复检查自己漏了哪一步。
  - **分步注册引导**（GitHub：Settings → Developer settings → OAuth Apps → New OAuth App），
    带注册入口与官方文档直链。
  - **回调地址直接摆出来 + 一键复制** —— 回调地址填错是 OAuth 最常见的失败原因，
    而它可由纯函数推导，不该让人去猜。
  - ClientSecret **Fernet 加密落库**（复用 `backup_settings.encrypt_secret`），
    只回显掩码；**留空 = 保持原值**；清除要走**显式动作**。
  - ClientId 明文回显（不是秘密，便于核对）。
  - 凭据来自环境变量时明确提示「在库里改会优先于它」——免得改了没反应白折腾。
- **取值优先级：Setting 表 → 环境变量**。DB 优先是本项目既定语义（同 `site_base()` /
  SMTP 设置）；环境变量**保留兜底**，老部署的登录不会因为改了优先级而突然失效。
- **回调地址推导收口到 `oauth.callback_url()` 纯函数**，配置页与 `api/auth.py`
  共用同一份逻辑 —— 两处各写一遍必然漂移，而回调地址写错是 OAuth 最常见的失败原因。
- 绑定页的提示从「改环境变量并重启」改成**指向配置页**；provider 名单由后端渲染，
  不在模板里写死。
- **前端零改动**：按钮本来就是动态读后端接口的，配好即出现。

### 微信登录：暂不做，把硬门槛写进 ROADMAP

微信开放平台「网站应用」（PC 扫码登录）要求 **企业/组织/个体工商户主体** +
**300 元**资质认证 + 域名 **ICP 备案且备案主体与开放平台主体一致**，且回调域
不能带协议头与端口。**个人主体基本申请不下来**（这是平台规则，不是代码问题）。
公众号网页授权那条替代路同样要认证服务号。已记入 ROADMAP §5.6，
`oauth.PROVIDERS` 是数据驱动的表，将来有资质再加 provider 是几十行的事。

### 验证

**607 passed**（591 → 607，+16）/ ruff 全仓全绿 / i18n 通过 /
**四项变异全红**：`_cred` 不读库 → 4 条；Secret 明文落库 → 1 条；
审计写凭据明文 → 1 条；Secret 留空即清空 → 1 条。

### ⚠️ 附带发现：lint 棘轮欠债（**非本次引入**，未抬基线）

跑 `tools/lint_debt.py` 才发现：`BLE001 269→278 (+9)`、`S110 92→96 (+4)`、
`SIM 40→61 (+21)`。**本次新增/修改的文件对这三条规则零命中**（已用
`ruff check . --select SIM,S110,BLE001` 逐文件核对），全部落在
v3.25.2~v3.25.6 期间新增的兜底捕获上（`cert_watch` / `_trigger_cert_recheck` 等）——
**那几次发版没跑棘轮**（`check-staged.py` 不含它，它是 CI job），欠债就一直攒着。

按纪律**没有** `--update` 抬基线。处置方案待定，见 ROADMAP §5.6。

## v3.25.6（2026-10-05 · v3.25.5 上线核验抓到的三处收尾）

> 来源不是设计评审，是**上线后只读核验在生产实测抓出来的**三条。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、无新增环境变量、
> **前端产物无变化**。

### P1 · `sitemap.xml` 的 `<image:loc>` 是错的（两层叠在一起）

1. `post.cover` 的语义是**站内相对路径**（`og_image._local_cover_path()` 只认
   `static/` / `uploads/` 前缀，外链一律返回 None），而 sitemap 规范里
   `image:loc` **必须是绝对 URL** → 原实现直接输出相对路径，搜索引擎根本拿不到图。
2. 生产有一篇文章的 `cover` 存成了字符串 `'None'`（历史写入路径把 Python 的
   `None` 拼成了 `"None"`）→ 实测输出 `<image:loc>None</image:loc>`，
   是**无效的 sitemap 条目**。

**修法**：新增 `routes._sitemap_image_loc()` —— 判据**不是「猜脏值长什么样」**，
而是与 `og_image._local_cover_path()` 同口径**只放行站内相对路径**并拼成绝对 URL；
站点对外地址未配置时**不输出**（拼不出绝对 URL 就别拼，绝不猜域名，同 `site_base()` 纪律）。

⚠️ **另需一次生产数据修正**：把 `post.cover = 'None'` 改回 `''`（本次核验后已执行）。
写入侧（`admin/post_editor.py` 等）现已是 `(x or "").strip()`，**未发现会再产生该值的
现存入口**，故不额外加写侧防御（不为未发生的问题写代码）。

### P2 · 证书状态文件三个时间字段口径不一致

`checked_at` 存**裸 UTC 不标时区**、`not_after` 反而带 `" UTC"` 后缀、
`backup_verify.json` 又是北京时间 → 诊断页「上次检查」看起来比现在早 8 小时，
很容易被读成「监控没跑」。现统一为北京时间（`fmt_bj`）；`days_left` 的计算仍用 UTC
（两端之差，时区无所谓）。

### P3 · 填完 `site_url` 后证书检查不会立刻重跑

每日定时那一次要等到第二天，而「照提示填完 `site_url`、回头看诊断页还是旧的
『未配置 site_url』」—— 这正是这个功能本身要消除的误导，不补这一下等于让人以为白填了
（v3.25.5 上线核验时实测就是这个体验）。

现：设置页保存 `site_url` 且**值发生变化**时，后台线程立刻重跑一次 `cert_watch.check_once()`。
放线程是因为要走 TLS 握手，不该拖慢「保存设置」；异常只记日志 —— 证书检查是旁路，
绝不能把保存变成失败。

### 验证

**591 passed**（574 → 591，+17）/ ruff 全仓全绿 / **四项变异全红**：
P1 退回原样输出 → 9 条；P2 `checked_at` 退回裸 UTC → 1 条；
P2 `not_after` 退回 `" UTC"` 后缀 → 2 条；P3 去掉重跑 → 1 条。

## v3.25.5（2026-10-05 · 补上 `site_url` 的配置入口）

> v3.25.4 那句「强烈建议顺手在站点设置填上 `site_url`」——**那个输入框根本不存在**。
> 本次就是补上它。无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、
> 无新增环境变量、**前端产物无变化**。

### 缺陷：一个配置项只有读取方，没有写入方

`site_url` 从项目建立就一直被 `site_base()` 读取 —— canonical / og:url / sitemap /
分享卡片 / 邮件里的文章链接 / 证书到期监控全靠它。但后台**从来没有输入框**：
唯一写入方式是改环境变量 `SITE_URL`，或直接改库。

更糟的是 SEO 页一直在红字警告「站点对外地址（site_url）未配置」并**链接到
「站点设置」页** —— 等于把人指进死胡同。本次是在大帅回「找不到可填写的地方」
之后才确认的：**我没有先验证入口存在，就给了「去设置页填」的建议。**

### 做法

- 站点设置页新增 `site_url` 输入框（`<label for>` 配对、说明文案写明它影响哪些位置），
  并显示**当前实际生效**的地址（DB → 环境变量 → 未配置），不是只回显输入框里的值。
- **保存前清洗 + 校验**：只接受 `scheme://host[:port]`。拒绝非 http(s)（`javascript:`
  / `file://`）、拒绝带路径/参数/锚点、剥掉 `userinfo`、去掉尾部斜杠与前后空白。
  理由：`site_url` 写坏**不报错**，只会静默让全站对外声明漂移（canonical 指向错页、
  二维码内容错、sitemap 域名错），等发现时外链已经散出去。
- 校验不过时**只跳过这一个字段**，其它字段照常保存，并 flash 明确提示 ——
  一个字段填错不该丢掉整张表单的编辑。
- 它同时进配置快照（`config_rollback`），填错能回滚。
- SEO 页告警链接加锚点 `#site_url`，直接落到字段上。

### 验证

**574 passed**（552 → 574，+22）/ ruff 全仓全绿 / **三项变异全红**：
① 取消全部校验 → 11 条变红；② `site_url` 不进可保存字段 → 5 条变红；
③ 输入框改名（等同没有入口）→ 1 条变红。

## v3.25.4（2026-10-05 · 证书监控：不再回落到本机名）

> v3.25.3 上线实证时抓到的**自身缺陷**，立即修补。
> 无表结构变更、**无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

### 修掉：静默降级到可能错误的检查目标

v3.25.3 上线后实测发现状态文件里 `"host": "llhhy1"` —— **服务器名，不是 `www.llhhy.cn`**。
查证：生产 **`site_url` 未配置** → `site_base()` 返回空 → 原实现**回落到 `socket.gethostname()`**。

**当时结果是「碰巧准确」的** —— nginx 对 `llhhy1` 与 `www.llhhy.cn` 返回同一张证书
（实测均 `CN=llhhy.cn` / 12-01 到期）。但**多 server 块 + 多证书时，连本机名拿到的是
另一张证书，而监控会一直报「正常」** —— 这正是设计第 2 条要防的「假监控」，
却从后门又开了一个。

**为什么测试没抓到**：写测试时用 monkeypatch 绕过了 `site_base()`，只覆盖了
「有域名」的情况，**没测「域名取不到」** —— 测试设计的漏洞，由生产实测补上。

**修法**：拿不到域名就返回空串 → 明确报 `unknown` + 提示配置 `site_url`，
**绝不悄悄换一个目标**。把「没配」变成看得见的状态。

### 根本解决（不在代码里）

在后台「设置 → 站点设置」填上 `site_url`。这本来就该填 —— 诊断页 `check_config`
一直在报「未设置 site_url」，而它会影响 sitemap/feed 绝对链接、分享卡片、canonical。
**证书监控只是这个老问题的又一个受害者。**

### 验证

**552 passed**（+3 守卫）/ ruff 全绿 / 变异「把本机名回落加回去」**3 条精确变红**。

## v3.25.3（2026-10-05 · SSL 证书到期监控）

> 起因：**2026-10-02 22:59 证书到期，10-05 才发现**，期间全站 HTTPS 不可访问
> （HTTP 80 → 301 跳 HTTPS → 浏览器拒绝）。后端与 nginx 始终正常，**只有证书过期**。
> 无表结构变更、**无 Alembic 迁移**（head 仍 `c7a2f19b4d30`）、无新增环境变量、
> **后端改动即可生效**（前端产物无变化）。安全审计 **R101**。

### 新增 `cert_watch.py`：证书到期检查

**为什么必须有**：「记得看」这种机制对**有硬期限的基础设施**是失效的 ——
本站证书是 90 天周期（TrustAsia DV），到期那天不会有任何报错，只会有用户打不开。

- **每日自动检查**，挂在 `_start_scheduler` 已有的循环里（第三个复用同一循环的任务，
  **不新增线程**）
- 状态落 `data/cert_check.json`（**零新表**，与 `backup_verify.json` 同范式）
- 诊断页新增「SSL 证书」分组（`check_certificate`），显示到期时间 / 剩余天数 / 签发机构
- 分级：`ok`（>30 天）/ `warn`（≤30 天）/ `critical`（≤7 天）/ `expired`（已过期，error 级）
- 过期或临期时 `logger.error` / `warning` 进日志

### 三个关键设计决定（都是踩过才知道的）

1. **走 TLS 握手，不读证书文件。**
   宝塔的 `fullchain.pem` 权限是 `drw-------` / `-rw-------`（**root only**），
   而 gunicorn 以 `www` 用户运行 —— **读文件必然 PermissionError**（实测）。
   且证书路径会随宝塔续签/迁移而变，硬编码路径等于埋雷。
   握手拿到的是**访客真正看到的那张证书**，权威且零依赖。
2. **域名取自 `site_base()`，不硬编码。**
   硬编码 `www.llhhy.cn` 会在换域名后变成**静默失效的假监控** ——
   它会一直报「正常」，因为你连的是旧域名。
3. **「没检查过」报 `never`/warn 而非 `ok`。**
   与「没有备份报 `empty` 而非 `ok`」同源：**没查过 ≠ 没问题**。

### 技术细节

- `verify_mode = CERT_NONE` 是**刻意**的：证书已过期时默认校验会直接抛
  `SSLCertVerificationError`，而我们要读的就是那张过期证书。
  安全性上不构成问题 —— 只读 notAfter，不传输任何凭据。
- 解析优先 `cryptography`（纯 Python、无子进程），回退 `openssl` 命令行。
  ⚠️ 记忆档案里「服务器缺 cryptography」**已失效** —— 2026-10-05 实测生产环境
  50.0.1 可用。两条路径都留着。
- **只提醒，不续签**：证书签发涉及域名验证 / CA 授权，不是应用层该做的事。
- 诊断页**读状态文件**而非现连（TCP 6s 超时摆在那，诊断页不能因此变慢）。

### 测试

`tests/test_cert_watch.py` 16 条。**不 mock 解析函数** —— 本机**真起 TLS 服务**
（自签证书）跑完整的握手路径，分别构造「未过期 / 20 天 / 3 天 / 已过期」四种情况。
只测「读文件解析」等于没测生产路径。

⚠️ 第一版有 6 条**随机失败**（TLS 服务线程未就绪就发起握手）——
flaky 测试比没有测试更糟，已在 fixture 里加就绪轮询，连跑 3 轮稳定。

**变异验证 2 项全部精确变红**：①「已过期」误报为 ok ②「never」在诊断页显示为 ok。

## v3.25.2（2026-10-05 · 备份自动巡检 + 评论嵌套修复与排序 + 配置回滚）

> ⚠️ **本版含一条表结构变更**：`audit_log` 新增可空列 `payload`（存配置快照 JSON）。
> 迁移 `c7a2f19b4d30`，`update.sh` 会自动执行；已用**旧 schema 库真实演练** ALTER + 历史数据完好。
> 无新增环境变量、无部署脚本变更。安全审计 **R100**。

### ① 备份自动巡检（优先级最高 —— 不做会出事的那项）

**问题**：`backup verify` 一直只能手动跑，于是「备份能不能恢复」这个属性
**在真出事之前永远是未知的** —— 而磁盘故障那天正是最需要备份的一天。

- `backup.py` 新增 `verify_latest(keep=3)` / `read_verify_state()` / `list_archives()`
- 挂进 `_start_scheduler` **已有的每日一轮**循环（与保留策略并列，`_last_verify_day`
  闭包，**不新增线程**）
- 结果落 `data/backup_verify.json`（**零新表**；与 `tasks.py` 状态文件同思路 ——
  4 个 gunicorn worker 是独立进程，内存态彼此不可见）
- 后台备份页三态显示（可恢复 / 校验不通过 / 无备份包 / 尚未巡检）+ 手动「立即巡检」
  按钮（走 `tasks.submit` 异步 —— 同步读 3MB/包算 SHA256 会占住并发槽，
  同 v3.23.0 #48 修过的坑）
- **失败必须响**：`logger.error` + 状态文件标红 + 后台显示。
  **「没有备份」刻意报 `empty` 而非 `ok`** —— 那是假安全感。

### ② 评论嵌套修复 + 排序切换（**修掉一个数据丢失缺陷**）

**比排序严重得多**：`post_comments` 原先只查两层
（`for t in tops: … filter_by(parent_id=t.id)`），而 `Comment.parent_id` 是
**指向任意评论的自关联外键**、前端也支持对回复再回复 ——
于是「回复的回复」（第三层起）**永远不会被返回**。
实测造 5 层链 + 1 分叉共 6 条，旧实现只返回 3 条，**L2/L3/L4 永久丢失**：
用户能创建、API 读不回来，等于写进去了界面上却看不见。

- 改为「一次取全量 → 内存建 `parent_id→children` 索引 → 深度优先遍历（**显式栈**，
  不用递归：脏数据的深链会撞 Python 递归上限）」，每条带 `depth`
- `sort` 走**白名单映射**（`old` / `new` / `hot`，附 id 兜底保证同秒评论顺序稳定），
  非法值回落默认；顶层与**每个子树内部**都按同一规则排
- `max_depth`（默认 4、上限 8）**只作折叠阈值回传前端，后端绝不裁剪** ——
  裁剪等于把「丢评论」从三层挪到四层，治标不治本
- `total` 只统计**顶层**（否则 per_page > 顶层数时 `has_more` 永远为真 → 死循环）
- 前端 `CommentForm.vue`：两层硬编码 → 扁平 + `depth` 缩进（超过 3 层不再加 padding，
  否则窄屏被挤成一条线）+ 「展开剩余 N 条」+ 排序切换条（样式全走 token，
  不再重演深色对比度那类缺陷）

### ③ 配置版本控制 / 回滚

`Setting` 有 65 项配置、各处可改，`log_audit` 记了「谁改的」却不记「改之前是什么值」——
改错了（SMTP 端口填错、限流阈值调成 1）只能凭记忆手改回去。

- 给 `audit_log` 加 `payload`（Text，存 JSON 快照）。
  **不塞 `detail`** 是因为它 `String(300)`，配置快照动辄几 KB ——
  **被截断的快照回滚回去就是错值，比没有快照更危险**。
  加列而非建表：项目纪律「能走 log_audit 优先走审计表」。
- 新模块 `config_rollback.py`：快照 / 差异预览 / 回滚 / 裁剪
- 设置页保存**前**自动拍快照；回滚走 `@super_required` + CSRF + `confirm=yes` +
  差异预览页 + 可勾选部分项（**只回滚勾选的 key**，不覆盖他人同期修改）

**三条安全不变量**（均有守卫）：

1. **快照存 `Setting` 原始值 → 敏感项落库时已是 Fernet 密文（`bkenc$`）**，
   回滚是「把密文写回去」，**全程不碰明文**（测试 spy `decrypt_secret` 断言 0 次调用）
2. **`detail` 只写摘要、绝不写值** —— 它会出现在审计列表页、CSV 导出、超管屏幕上
3. **回滚前先给当前值也拍一份退路快照** —— 否则「回滚回滚」没有退路

### ④ 顺带修掉的两个真问题

- **`log_audit` 静默丢审计**：原先无条件 `session.get("user_id")`，在**无请求上下文**
  （CLI / 定时任务 / 单元测试）时抛 `RuntimeError: Working outside of request context`，
  而它在最外层 `try` 内 → 异常被 `except Exception: pass` 吞掉，
  **整条审计一条都没写且毫无迹象**。表现是「配置快照看起来完全失效」，
  根因不在快照逻辑而在审计函数。已加 `has_request_context()` 守卫 + 内层兜底（双保险）。
- **门禁自身的一处缺陷**：`test_doc_archival.py` 里那条测试断言的是
  「归档件必须在发版门禁的必改清单里」—— 而那正是 v3.25.1 判定为**错**的行为。
  已改成断言新行为（归档件**不**在必改清单 + 活的主文档仍在），守住「门禁别被改废」。

### ⑤ ROADMAP §5 逐条复核（长期债盘点）

§5 清单写于 v3.10.6 期（2026-08-31）。逐条 grep 后发现 **8 项早已落地却仍记着「未做」**
（canonical / Atom feed / JSON-LD / HTML 邮件 / 趋势环比+CSV / 积分勋章 / 2FA / OAuth /
自动元描述），**10 项经实测判定不做**（每条附理由与重新评估的触发条件），
剩余 7 项标「可选」。

**方法论**：清单里的「未做（N 项）」是**计数式断言**，不做逐条实证就会变成假账
（本轮已是第三次因此发现假账：v3.25.0 的 B 项、v3.25.1 的 E 项、本轮 §5）。
今后新增条目必须写**实测依据**（文件 / 函数 / 字段名），不写「已做」二字。

### 验证与升级要点

**534 passed**（+23 条新守卫）/ ruff 全仓全绿 / `vite build` 成功 /
迁移演练通过（ALTER 生效 + 历史审计行完好）/ **8 项变异全部精确变红**
（备份 2 + 评论 2 + 配置 2；另 1 项**等价变异**如实记录，未硬凑）。

**升级**：备份 → `flask db upgrade`（自动执行 `c7a2f19b4d30`）→ 重启。
`update.sh` 一键完成。**上线后 checklist**：① 后台备份页看「可恢复性巡检」卡片是否
显示（首次需等每日定时任务跑一轮，或点「立即巡检」）② 打开带多层回复的评论文章确认
深层评论可见、可排序 ③ 设置页改一次配置后，进「配置变更历史」应能看到快照。

## v3.25.1（2026-10-02 · 深色模式可读性修复 + 表单可访问名补全）

> ⚠️ **本版是 v3.25.0 上线后的两个修复批次**，均不含表结构变更、无 Alembic 迁移
> （head 仍 `e5b8c3f17a24`）、无新增环境变量。安全审计 **R99**。

### ① 深色模式「看不清」（用户报告 + 守卫扫出共 6 处）

用户报告：天气文字（`阵雨 25°C · 潮州`）看不清、文章目录颜色太白。

**定性：不是 v3.25.0 的回归** —— 本轮只改了 `tokens.css`，`global.css` 一字未动
（已用 `git diff v3.24.1 HEAD --stat` 实证）。是历史遗留的**深色模式适配缺口**。

根因是**两个方向相反的遗漏碰在一起**，必须同时看容器与文字才现形：

| 元素 | 形态 | 实测 |
|---|---|---|
| `.weather-widget .w-text` | 写死 `#333`、深色**无覆盖** → 深字压深底 | **1.42:1** |
| `.toc` 容器 | 背景写死 `#fafbfc`、深色**无覆盖**，文字却翻浅了 → 浅字压白底 | **1.56 / 1.79:1** |
| `.series-toc` 容器 | 同上（`.toc` 的姐妹组件，用户还没翻到） | **1.21:1** |
| `.widget h3` | 写死 `#333` 无覆盖 | 1.42:1 |
| `.comment-content` | 写死 `#444` 无覆盖（整段评论看不见） | 1.84:1 |
| `.rank-name a` / `.related-list a` | 写死 `#333` / `#444` 无覆盖 | 1.42 / 1.84:1 |

**次生修复**：`.toc-sub a`(#777) 与 `.series-toc .chapter-meta`(#aaa) 原本在白底上勉强
合格（4.32 / 3.79），容器一改深底就掉到 3.35 / 3.79 —— **改容器背景必须连带查子元素的
写死色**，否则修一个坏一个。

新增 2 条守卫（`tests/test_wcag_contrast.py`）：`test_dark_mode_no_light_text_on_light_background`
（浅字压浅底）、`test_dark_mode_no_dark_text_left_behind`（深字压深底，门槛刻意取 2.5）。

### ② 表单可访问名补全（placeholder-only 71 处）

实测 71 处控件只有 placeholder、没有可访问名，分三类分别处理：

- **A 类 40 处**：前面有 `<label>` 文字但**无 `for`/`id` 配对**（人看得见、程序上无关联）
  → 补配对，顺带获得「点标签聚焦控件」。
- **B 类 29 处**：纯 placeholder 表单（新建系列/友链/用户等）→ 补 `aria-label`，
  **值取字段语义名而非 placeholder 原文**（很多 placeholder 是示例值
  `https://...` / `LTAI...`，照抄等于没标签）。
- **C 类 8 处**：`<span class="qc-label">` 冒充标签 → 改真 `<label class="qc-label" for=...>`
  （CSS 用类选择器，换元素对视觉零影响）。

新增 `tests/test_form_accessible_name.py` 3 条守卫（含「同一标签不得有重复 id 属性」），
**3 项变异全部精确变红**。

### ③ 长期债盘点（先量数据再判断，三项判定不做）

- ❌ **`LICENSE` ×3**：三份同内容，但 `myblog/LICENSE` **实证进发布包**，删了发布物就没许可证。
- ❌ **`v3.x.y` 注释版本戳 524 处**：是有价值的历史标注（说明代码为何存在、哪版引入）。
- ❌ **性能项**（eager loading / N+1 / 索引）：线上响应 **5~52ms**、生产库 `post` 仅 **8 行**、
  最大表 635 行 → 收益为零。已写明**重新评估触发条件**：`post > 500 行` 或 `comment > 2000 行`
  或任一 API p95 > 200ms。
- ✅ 另更正过时记录：~~`/api/qr` 用 `request.host`~~ → v3.20.0 已闭环（未配置即 400）。

### 升级要点

**需要 vite build**（改了 `vue-frontend/src/styles/global.css`）→ 两个包都要覆盖。
`update.sh` 一键完成。**上线后**：切换到深色模式，确认天气文字、文章目录、系列目录、
评论正文、侧边栏标题、排行榜/相关文章链接**都能看清**。

## v3.25.0（2026-10-01 · WCAG 对比度治理 + 手机端表格字段名 + 包级循环依赖清零 + FTS 会话隔离 + 文档归档 + 裸 hex 收敛）

> **本版本含可见视觉变更**（主题色被压深、后台表格手机端显示字段名），
> 与前几个「纯内部重构」的版本不同，升级后请在**手机端**与**深色模式**下各过一遍。
> 无表结构变更、无 Alembic 迁移（head 仍为 `e5b8c3f17a24`）、无新增环境变量。
> 安全审计见 `myblog/SECURITY_AUDIT.md` **R98**。

### WCAG SC 1.4.3 对比度治理

**先纠正一个错误结论**：上一轮认定「`{{ theme_css }}` 会用 `themes.py` 的值整体覆盖
CSS 变量」——**这是错的**。`app.py:621` 的 `theme_css` 只含 `--theme-radius` /
`--theme-font-size`，**不含任何颜色**。真实链路是**两条互不覆盖**的：

| 渲染面 | 主题色来源 | 机制 |
|---|---|---|
| 前台 SPA | `myblog/themes.py` | `vue-frontend/src/store.js: applyThemeTokens()` 逐个 `setProperty("--surface-2", …)` 写 `:root` |
| 后台 admin | `myblog/static/tokens.css` | **纯 CSS 兜底，后台零 JS 注入** |
| SSR/SEO 页 | `tokens.css` + 内联 `--accent` | Jinja，无 JS |

**两份真相源都得改，只改一份等于只改一半。** 已新增两条守卫钉住
（`test_admin_has_no_theme_token_injection` / `test_theme_css_carries_no_colors`），
防止再次有人按错误结论去改。

修掉的 4 类缺陷（实测远多于原记录的「4 组 token」）：

1. **暗色 `text_faint` 层级坍缩（14/14 preset 全中）** —— 根因不是二分精度，而是
   `themes.py:_scan` 里方向标志算错：`cand = _at_lum(base_hex, want_l, lighter if sign > 0 else (not lighter))`。
   暗色（`lighter=False`）下 `sign=-1` 会传 `True` 进「向白插值」分支，而该分支
   `t=0` 就返回基准色本身 → 兜底轮直接返回 muted，表现为 faint == muted（间隔 0.000）。
   改为 `sign > 0`（第三参只该看 `want_l` 相对 `base_l` 的方向，与主题的 `lighter` 无关）。
2. **`_at_lum` 系统性「差一口气」** —— 二分取 `hi` 侧（`lum >= want_l`）使返回值总比
   目标略亮，调用方拿它卡「对比度 >= 4.5」就系统性不达标（实测目标 L=0.1696 时
   实际只有 4.11~4.15）。改取 `lo` 侧（保守方向），并新增 `test_at_lum_never_overshoots`。
3. **暗色主按钮白字崩（14/14 preset，最低 2.43:1）** —— `--accent` 在暗色下同时是
   「主按钮底色」和「链接/标签前景」双重身份。白字需 `L ≤ 0.60`，作文字需 `L ≥ 0.65`，
   在深底上**真互斥**。新增 `_on_accent_for(*block_hexes, page_bg_hex)` 自适应求解
   `--on-accent`（深字），实测 4.55~6.52。该函数按**变参全量校验**所有色块 ——
   因为同一个 `on_accent` 同时压在 `accent` 与 `danger` 两个色块上。
4. **暗色 `--danger` 前景身份漏判** —— 注释断言「暗色 danger 零 `color:` 用法」是错的，
   `admin.css:315` `.link-danger`（13px 危险操作链接）与 `:604` `.side-logout:hover`
   都是前景身份。提到 L=0.67 档后实测 4.75~4.81。

**14 套 preset 品牌色压深**（用户确认口径「压深品牌色」而非「新增 `--accent-text` token」）：

| preset | 原值 | 新值 | preset | 原值 | 新值 |
|---|---|---|---|---|---|
| classic-blue | `#1a73e8` | `#1a6ddf` | sakura-pink | `#e64980` | `#bd3c6a` |
| aurora-green | `#12b886` | `#0d7f5d` | teal | `#0d9488` | `#0c7d75` |
| twilight-purple | `#7c5cff` | `#7354ec` | amber-gold | `#ca8a04` | `#966703` |
| maple-orange | `#ff6b35` | `#b94f27` | cyan-electric | `#06b6d4` | `#047a90` |
| rose-red | `#e5484d` | `#c73e43` | terracotta / graphite / indigo | 不变 | 原本已达标 |
| lime-citrus | `#65a30d` | `#4e7c0b` | | | |
| deep-ocean | `#0ea5e9` | `#0b76a9` | | | |

**已知取舍（用户拍板「保层级，faint 走大字门槛」）**：亮色 `--text-faint` 从
2.44:1 提到 **3.51:1** —— 达不到正文 4.5:1，但过了 WCAG **大字档 3:1**。之所以不硬推
4.5:1，是因为那会吃掉 `text` / `text_muted` / `text_faint` 三档的亮度层级
（`min_gap` 守不住），浅灰变深灰后「弱化文本」的语义就没了。

新增 `tests/test_wcag_contrast.py`：**16 条守卫 + 14 项变异验证全红**。

### 后台表格 `data-label` 补全（手机端可读性）

`base.html:42` 的 `.admin-table td[data-label]::before` 只在 ≤760px 生效，
而此前 44 个后台模板里**只有 3 个**写了标注 —— 手机端表格卡片化后表头隐藏，
单元格只剩裸值（「2026-09-30 10:00」这种时间完全失去上下文）。

补标 **115** 处（21 张 `.admin-table`）。过程中发现并修掉 3 个真问题：

1. **`oauth_bindings.html` 的 5 个 `data-label` 是死标注** —— 它用 `.stats-table`
   类，而 `.stats-table` 在 `admin.css:928` 走的是**横向滚动**兜底，全站没有它的
   `::before` 规则，属性在、字段名永不渲染。改为 `admin-table` 后当场生效。
2. **`ai_summary.html` / `seo.html` 是「套娃表」** —— 写法为
   `<div class="admin-table"><table>`，而 `.admin-table` 的规则全是**后代选择器**
   （`.admin-table td`），外层 div 照样把内层裸 table 卡片化了。等于
   「卡片化了一半、字段名全丢」，比纯横滚更糟。
3. **`seo.html` 用 `{% for cell in (r.baidu, r.indexnow) %}` 在一个 `<tr>` 里生成
   两列** —— 两列共用同一段 `<td>` 源码，只能标同一个 `data-label`，实测 Bing 列被
   写成「百度」。已改为 `{% macro seo_push_cell(cell) %}` 显式两次调用。

新增 `tests/test_admin_table_data_label.py`：**52 条断言 + 12 项变异验证全红**。
其中 `test_每个表格都纳管` 是被变异逼出来的：原先漏标检查与「class 是否含
`admin-table`」耦合，把类名改掉整张表就从视野消失而守卫仍绿。

### 包级循环依赖清零 + FTS 重建会话隔离

见 `ROADMAP.md §结构` 与 `myblog/SECURITY_AUDIT.md` R98。

一句话摘要：新增顶层模块 `myblog/audit.py`，把横切关注点（审计写入）从 `admin/_helpers.py` 搬出来，
拆掉 `api → admin` 与 `admin → api` 两条顶层边 —— 原先这两个包处在**同一个 21 模块强连通分量**里。
反向变异验证给出的不是「测试变红」而是 **pytest 收集期真实 ImportError**，
证明那个环从来不是理论风险，而是「一条边写回去整个后台就起不来」的硬故障。

### 文档归档（主文件 1,088 KB → 531 KB，-51%）

两份长期文档已分段归档到 `docs/archive/`，**内容零丢失**（脚本末尾做逐字包含校验）：

| 主文件 | 归档前 | 归档后 | 归档件 |
|---|---|---|---|
| `myblog/SECURITY_AUDIT.md` | 436 KB | **98 KB** | `SECURITY_AUDIT_r01-r80.md`（327 KB，R1~R80） |
| `CHANGELOG.md` | 218 KB | **82 KB** | `CHANGELOG_v1-v3.18.5.md`（137 KB，v3.18.5 及更早） |

另整份归档两份一次性快照：`INDEPENDENT_SECURITY_REVIEW_v3.8.1.md` / `REVIEW_v3.18.0.md`。
目的是让文档体积不再随轮次线性吃掉 LLM 上下文；归档仍在版本控制内、可检索，
主文件头部各留一行指针。守卫 `tests/test_doc_archival.py`（13 条）。

**踩坑记录**：`git checkout <file>` 会连带 revert 该文件**未提交**的改动 ——
本轮回滚时用它，把刚写好的 v3.25.0 段落一起冲掉了，只能凭上下文重写。
**长文档回滚务必先 `git stash` 或按 hunk 回退。**（已写入 `tools/review/check-staged.py` 注释）

### CSS 裸 hex 收敛（`style.css` 11 处）

沿用 v3.17 起本项目的 `var(--token, #原值)` 兜底约定，**零像素差**：token 缺失时行为不变、
旧缓存不掉色。三重判据（任一条不满足就不换）：① 值必须**逐字相等**（「长得像灰」不等于可换）；
② 只在**亮色作用域**成立（暗色块里的值换过去会跟着变亮 = 改设计）；③ **语义一致**
（`#ffffff` 作背景是 `--surface`、作文字是 `--on-accent`，不能同一个值到处换）。

同时测绘了 `admin.css`：**190 处几乎无可换的**，分三类 —— 暗色块专用值 /
无对应 token 的独立灰阶 / 渐变端点；且该文件早在 v3.17 就已用 17 个 `var()`。
结论是「230 处裸 hex」这个数字本身不构成技术债，已写入棘轮基线
`tests/test_css_token_ratchet.py`（admin.css 190 / style.css 177）。

### 主题求解器畸形输入加固（发版审计 newly found）

`myblog/themes.py` 的 `_at_lum()` 有两处问题，安全审计 R98 实测发现并已修：

1. **重复死代码块** —— 同一份二分逻辑写了两遍，第一段缺 `else: hi = mid` 且结果被
   第二段整体覆盖。纯死代码，但是真陷阱：后来人只会改到第一段，改完看不到任何效果。
2. **畸形色值直接抛异常** —— 当前生产路径已由 `_tier_for` 的 try/except 挡住（不可达），
   但模块 docstring 明写「绝不抛异常导致页面 500」，「靠调用方守」太脆。已改为
   畸形返回 `None`（与既有「目标不可达」语义一致）。

新增守卫 2 条 / 参数化组合 11 条，3 项变异全部精确变红。
**教训**：第一轮手感探针把畸形值传在**第 2 个参数**得出「全部存活」的假阴性，
写成真守卫时传在第 1 个参数（被调色的原色）才暴露真真空 ——
**探针的调用姿势必须与生产调用姿势逐参数对齐。**

### 升级要点

- **需要 vite build**（改了 `vue-frontend/src/styles/tokens.css`），发布物含 `vue-frontend-dist.zip`。
- 无表结构变更 → `flask db upgrade` 在 head 处为空操作（`update.sh` 会自动跑）。
- `tools/rebuild_fts.py` **不需要**重跑（本轮未改 `_indexable()` 判定条件，只改了遍历方式）。
- **上线后 checklist**：① 抽查含 SEO 推送记录的文章，确认「百度 / Bing」两列状态各自正确
  （不再都显示「百度」）；② 手机 UA 下任取一张后台表格，确认卡片化后每格都带字段名抬头；
  ③ 深色模式下过一遍全部 14 套 preset。


> 本文件承载 **历史版本** 记录。README 只保留最新版本与上手信息。
> 各版本的安全审计结论见 `myblog/SECURITY_AUDIT.md`；功能规划见 `ROADMAP.md`。

## v3.24.1（2026-09-30 · admin 包显式导入治理——纯内部重构，零行为变更）

> **无表结构变更、无迁移、无新增环境变量、无前端改动、无部署脚本变更**；升级即「覆盖后端 → 重启」。
> 安全审查见 `myblog/SECURITY_AUDIT.md` §R97。

### 架构：admin 包依赖面显式化（消灭「静态检查看不见」的债）

- **原状**：`_helpers.py` 用 `globals()` 运行时快照拼 `__all__`，把 `os`/`time`/`functools`/
  `Blueprint`/`db`/`Post`… 等全部顶层名字经 `from ._helpers import *` 灌进 16 个业务子模块
  （基线实测：22 个模块共 1571 个名字，每模块背 15~20 个污染名）。16 个模块存在同名符号
  （`time`/`utcnow`/`feed_agg`/`current_app`…），**谁生效只取决于「星号行与自身 import 行」
  的先后**——行序一变即 NameError，且 F403 默认放行、F821 因名字恰好存在而不报，
  任何静态检查都看不见。
- **改造**：`__all__` 改显式清单（21 个本模块定义的公共 API，含下划线 helper——star-import
  默认跳过下划线，这正是当初被迫用快照的原因，显式清单两头兼顾）；16 个子模块全部改显式导入
  （真实跨模块依赖仅 21 个 helper + 各自所需第三方）；`__init__.py` 星号转发收敛为
  `admin_bp` + 外部真实消费的 `log_audit`/`log_login_attempt`；22 个模块注册行标注为
  副作用导入（`# ruff: noqa: F401` + 理由注释——**删一行 = 后台路由整块消失**）。
- **净效果**：清除 **505 个**跨模块污染名；治理首轮 ruff F821 一度暴露 **1076 处**星号时代
  不可见的幽灵依赖，全部以显式导入收敛；顺带 F401 棘轮 171→113、T20 66→21，lint 总债
  601→**543**。

### 守卫（新增 `tests/test_admin_explicit_imports.py` 4 条）

1. AST 判定禁星号导入（注释字样不误报）；
2. `_helpers.__all__` 禁退回运行时快照；
3. **全模块 LOAD_GLOBAL 可解析的结构性零 NameError 证明**——覆盖没有任何测试打到的路由；
   解析域用 `fn.__globals__` 而非 `vars(导入方)`（`functools.wraps` 会复制 `__module__`，
   判错域产出 287 个假阳性——这个坑本身写进了测试 docstring）；
4. 包命名空间 re-export 面与外部真实消费面一致。

4 条均经**变异验证**（把子模块改回星号必红）。

---

## v3.24.0（2026-09-30 · 表结构改走 Alembic + 积分去重/保留策略 + Setting KV 治理）

> ⚠️ **本版含部署流程变更**：升级时**必须**在「覆盖后端之后、重启之前」执行一次
> `BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app <venv>/bin/python -m flask db upgrade`，
> 否则迁移里的索引/列不会落到生产。详见 `myblog/deploy_guide.md` 升级流程第 4 步。
>
> ⚠️ **本版迁移含删除动作，升级前务必备份 `blog.db`**。
> 安全审查见 `myblog/SECURITY_AUDIT.md` §R96。

### 架构：单一 schema 真相源（部署侧 + 退役 9 个 `_migrate_*`）

- **根因修复**：v3.24.0 之前，`update.sh` 与部署手册**从不执行 `flask db upgrade`**——线上升级
  就是「覆盖代码 → 重启」，所有表结构变更靠启动自愈（`db.create_all()` + 9 个 `_migrate_*`）
  完成，Alembic 只被 `stamp`、从未真正 upgrade。**只写在迁移脚本里的结构变更不会生效**。
- `update.sh` 新增 `apply_db_migrations()`（step 5b，覆盖代码后、重启前）；迁移失败则**中止且
  不重启**（宁可继续跑旧代码，也不让新代码访问旧表结构）。以站点用户执行，避免 `blog.db`
  及其 `-wal` 变成 root 属主。
- `BLOG_MIGRATE_ONLY=1` 新增迁移专用模式：正常构造 app 但**跳过** `create_all()`、
  勋章播种、FTS、设置/超管兜底、插件加载等全部启动副作用。部署脚本因此**不必持有管理员凭据**，
  也杜绝了「用占位 `ADMIN_PASSWORD` 而库里恰好无超管时造出已知密码超管」的风险。
- 9 个 `_migrate_*` 全部退役，历史加列固化为迁移 `d4a7f08c2e91`（**冻结快照**、逐列查存在性：
  生产空操作，老库补齐）。数据播种 `seed_badges()` 不是表结构，拆出为 `_seed_default_badges()`
  并**无条件调用**（曾因写在 `if need:` 分支内导致勋章永远播不进去）。

### 数据完整性：积分去重 + 保留策略 + 定时发布防重

- `point_log` 加 DB 级去重唯一索引 `uq_pointlog_dedup`、`reader.points` 加索引 `ix_reader_points`；
  配套迁移 `b3f6c1d84a72` 会**删除 `point_log` 里的重复行**（同读者 + 同原因 + 同文章 + 同天
  只留 id 最小的一条），这是建索引的必要前提，不去重索引建不出来。
- 新增保留策略（`gamify.prune_retention()`，调度线程每日一次）：**reader 永久 / point_log 2 年 /
  reader_badge 随 reader**。
- 定时发布改为**原子认领**（`app.claim_scheduled_post()`）：多 worker 的调度线程不再把同一篇
  文章重复发布，也不会重复推送/重复发订阅邮件。

### `Setting` KV 治理：UGC 各归其主

- 两类 UGC 曾被当设置存进 `setting` 表——`react_<comment_id>`（评论表情）与
  `ai_summary_<id>`/`ai_tags_<id>`（每篇文章的 AI 摘要）。后果：设置表随评论/文章数无限增长，
  且因有 **6 处 `Setting.query.all()` 全表加载**（后台 `inject_globals`、天气默认坐标、后台设置页 ×3、
  `api/common._settings_map`），每次渲染都把这些 UGC 一起捞出来建字典。
- 改为挂到各自已有的主行上（**不新增表**）：`comment.reactions`（JSON `{"👍":3}`）、
  `post.ai_summary` / `post.ai_tags`。保留了「每条评论独立、并发互不干扰」的设计优点
  （无需整表 JSON 读改写）。迁移 `e5b8c3f17a24` 幂等搬迁并清理原 setting 行（含孤儿键）。
- `api/reactions.py`、`api/ai.py`、`admin/ai_summary.py` 随之改造；后台摘要列表页顺带消除 N+1。
  对外接口与页面行为**完全不变**。

### 代码结构

- `create_app()` 由 **510 行拆成 35 行**（拆成同文件 8 个私有函数：环境校验 / 核心装配 /
  请求钩子 / 数据库引导 / 模板上下文 / CLI / 错误处理 / 调度线程）。纯机械按行块搬运，无一行代码
  重写。守住两条顺序约束：`db.init_app` 须早于数据库引导；**Flask 的 `before_request` 执行顺序
  = 注册顺序**，故 5 个钩子集中在同一函数内按原序注册。
- 测试 357 → **362**（新增 `tests/test_setting_governance.py` 5 条）。

---

## v3.23.0（2026-09-28 · 可观测性 + 后台任务 + OAuth 自助解绑 + CI 门禁）

> 本版本**无表结构变更**；安全审查见 `myblog/SECURITY_AUDIT.md` §R95。

**功能**

1. **后台「第三方账号绑定」管理**（R94 §94.8-7 可发现性缺口收口）：查看当前账号已绑定的
   OAuth 渠道并解绑。解绑要求输入登录密码——它同时是「该账号仍有可用登录方式」的证明
   （OAuth 建号者的密码是随机串，输不出来即被挡住，不会把自己锁在门外）；超管可代查/代解，
   但**不得解绑他人最后一个绑定**（超管密码只证明超管身份，证明不了对方还有别的登录方式）。
2. **结构化日志 + request_id**：新增 `logging_setup.py`，每个请求生成/沿用 `X-Request-ID`
   （形态校验防日志注入，回写响应头），日志格式带 `rid=`，可按请求串联排障；新增可选环境
   变量 `LOG_LEVEL`（默认 INFO，行为不变）。全仓**运行时 `print(` 清零**（47 处转 logger；
   CLI 脚本的 stdout 刻意保留——那是给运维管道用的）。
3. **后台长任务基建 `tasks.py`**：状态落盘 `data/tasks/<id>.json`（跨 worker 可见，原子写）、
   同名任务跨进程互斥（锁文件 + 过期清理）、异常落盘不外抛。接入两个试点：
   **立即备份**（含 scp/curl 远程同步，最长 300s）与**游戏上传的 LLM 审计**（120s）改为
   后台执行 + 页面轮询进度，不再长期占住 gunicorn 并发槽。手动 LLM 审计 / AI 摘要生成
   保持同步（操作者在等结果）。
4. **`/api/weather` 出站结果缓存**：公开端点原先每次请求都真打外部 API（坐标模式串行最坏
   约 17s），现进程内缓存 10 分钟（限容 200，`city` 用户可控必须防无界增长）；上游全失败时
   回吐过期数据（宁可旧，不要 502）。
5. **后台操作日志轮询端点**：`GET /admin/task/<task_id>`。

**平台 / 工程**

6. **CI 补齐**：build 作业新增前端依赖 CVE 扫描（`npm audit`，基线 0 漏洞，显式指定官方
   registry——镜像源不实现 audit 端点）；新增 CodeQL（SAST，刻意非阻断）。
7. **lint 棘轮修复**：清理 v3.21~v3.22 带入的 4 处新增债（删死导入 ×1；刻意兜底 / 刻意再导出
   补 `# noqa` + 理由 ×3），棘轮自 v3.20.0 后首次转绿，且 T20 66→21（print → logger）。

**部署注意**：新增运行期目录 `data/tasks/`（自动创建，无需迁移）；`LOG_LEVEL` 可选；
本版无表结构变更、无渲染版本变化，`rebuild_fts.py` 无需重跑。

## v3.22.0（2026-09-27 · 安全复审 R94：2FA 闸门 / OAuth 接管 / 隐私外泄修复）

> **来源**：合并 PR #14（GitHub 用户 `Llhhy1` 提的第四轮安全复审），作者即站点所有者。
> 本版本**无新功能**，是 R94 审计结论的工程化落地：2 Critical + 4 High + 若干 Medium。
> 审计详情见 `myblog/SECURITY_AUDIT.md` §R94（由 PR 写入）。

**六项修复（逐条回代码核对，非采信报告自述）**：

1. **R94.1 Critical｜2FA 只是装饰**：此前 2FA 只在 `/api/auth/login`（JSON 登录）判了，
   `POST /login`（前台 SPA）、`POST /admin/login`（后台）直接写 `session["user_id"]` 放行。
   改为**会话级 before_request 闸门 `enforce_twofa`**（`TWOFA_ENABLED` 关则整体休眠；只对
   已启用 2FA 的账号拦截非白名单路径；白名单不含 enroll/confirm/disable 以防单因素会话改
   第二因素）；`twofa.enroll` 对**已生效**的 2FA 要求先验证当前码（防静默解除）。
2. **R94.2 High｜OAuth 接管（本地邮箱）**：原 `oauth.py` 按**本地库未验证邮箱**匹配既有账号
   （注册仅 `strip()`，无校验/唯一约束）。改为未登录回调不再按邮箱认领，认领入口限缩为
   「当前已登录会话本人」。⚠️ **语义变更**：曾按邮箱绑定的老用户下次 OAuth 会进新账号，
   需在其账号内重新点一次绑定。
3. **R94.3 Critical｜隐私/回收站外泄 + FTS 正文**：`api/posts.py` 两处（相关推荐、搜索）用
   不判 `is_private/in_trash` 的 `_is_visible()`；`fts.py` 索引只判 `published`，隐私/回收站
   正文进全文索引。改为 FTS 写入侧闸门 `_indexable()` + 删除平行 `_is_visible()`（配静态防复发
   测试）+ 两处改回 `visible_posts_query()`。📌 **部署必须跑一次 `python tools/rebuild_fts.py`**
   清洗历史脏行。
4. **R94.4 High｜FTS 不同步**：5 处改变可见性的写路径（定时发布线程、publish_now、后台发布/
   进回收站等）补 `sync_post_quiet()`，避免文章永久搜不到。
5. **R94.5 High｜备份 scp/curl 参数注入**：`BACKUP_SCP_HOST`/`WEBDAV_URL` 来自后台可编辑
   Setting，写入 `-oProxyCommand=` 或 `file://` 可 RCE/任意写。改为严格正则校验 + 仅限
   http/https + scp/curl 加 `--` 终止符 + size 上限 + 流式哈希。
6. **R94.6 High｜恢复在有上传文件时必崩**：`_snapshot_before_restore` 上传打包循环写在
   `with ZipFile` 块外，对已关闭归档调 `write()` → `ValueError`，而 `restore()` 在覆盖主库前先
   调它 → 真实站点恢复直接废。修复 indentation + 快照自带 manifest + 改名纳入清理 + 失败不阻断。

**取舍（按 B 方案「全收」接受，沿用 PR 设计）**：① OAuth+2FA 用户由全局闸门重定向到 2FA 挑战
页（安全行为，非锁死）；② 删用户改为**停用**（防 rowid 复用 / OAuth 孤儿）；③ 积分身份公平性、
`PointLog` 复合 UNIQUE 迁移、`reader/point_log` 保留策略——PR 刻意未做；④ 老邮箱绑定用户需重新
绑定（R94.2 必要取舍）。

**审计纪律备注**：R94 报告把 94.3 写成「上一轮（R93）可见性修复一条都没落地」，经核对**不实**——
`visible_posts_query()` 在 v3.21.2 中约 40 处均已使用，真正漏的只有 2 处 + FTS 写入侧；但 94.1 /
94.2 / 94.4 / 94.5 / 94.6 的底层事实均属实（仅 94.5 严重度偏高，属管理后提权而非未授权远程 RCE）。

**验证**：300 passed；ruff 全绿；lint 棘轮 648 = 648（PR 带入 1 处 SIM105，已真修）；
compileall + 打包三链互证与验签通过。

## v3.21.2（2026-09-24 · 修复勋章播种的多 worker 竞态假警报）

> **来源**：v3.21.1 上线后看 gunicorn 日志发现一条 `默认勋章播种失败: UNIQUE constraint failed: badge.key`。勋章表实际完好（5 行）—— 这是 **4 个 gunicorn worker 并发启动的竞态**：都看到空表、都去插入，后提交的撞键。

**修复**：`seed_badges()` 从「`Badge.query.count()==0` 才整批插入」改为**按 key 逐枚跳过已有项**；并发撞键时回滚放弃（另一 worker 已完成播种，**不算失败、不必报警**）。顺带修掉旧实现的另一个坑：表里有任意一行就整体跳过 → 缺的勋章永远补不齐。

**回归测试**：`test_seed_badges_partial_and_race_safe`（部分播种 → 补齐到默认枚数且不覆盖已有项；重复调用幂等）。**变异验证**：回退旧实现 → 2 条用例变红。

**部署**：纯后端改动，只需覆盖后端包。重启后日志不应再出现「默认勋章播种失败」。

## v3.21.1（2026-09-24 · 修复默认勋章未播种）

> **来源**：v3.21.0 **上线后实证**发现（不是本地测试发现的 —— 本地全绿、服务器首跑即中）。

**缺陷**：`create_app()` 在调用 `_migrate_new_tables_v3()` **之前**就已经执行了 `db.create_all()`，因此新表在函数入口处**早已建好**，函数内算出的 `need` **恒为空** → 写在 `if need:` 分支里的 `seed_badges()` **永远不会执行**。

**后果（静默降级）**：`badge` 表建好了但**一条数据都没有**（线上实测 `select count(*) from badge` = 0）。读者能正常累积积分，但**永远拿不到任何勋章**，且全程不报错 —— 正是「找不到资源就安静降级」那类会在生产里长期潜伏的缺陷。

**修复**：把 `seed_badges()` 移出 `if need:` 分支，改为**无条件调用**（它本身幂等：`Badge.query.count()==0` 才插入），并单独包 `try/except`，播种失败也不影响启动。

**回归测试**：`tests/test_gamify.py::test_badges_seeded_even_when_tables_already_exist` —— 先清空勋章再跑迁移，精确复现「表已存在 → `need` 为空」这条路径。**变异验证**：把播种移回 `if need:` 内 → 该用例立刻变红。

> 教训（可复用）：**把「建表」与「播种初始数据」写进同一个条件分支是隐蔽陷阱** —— 只要建表动作可能在别处先发生（本项目就是 `create_app` 里的 `db.create_all()`），播种就会被静默跳过。播种应当是**幂等的独立步骤**。

**部署**：只需覆盖后端包（`vue-frontend/` 未动）。升级后重启时会自动补齐 5 枚默认勋章，**无需手工 SQL**。

## v3.21.0（2026-09-24 · 内容多语言 M1 + PWA + 读者积分勋章 + OAuth + 2FA）

> **来源**：用户勾选「四个功能全做」（PWA / 读者积分勋章 / OAuth / 2FA），并连同上一轮已完成待发的**内容多语言 M1** 一并发版。
> **安全**：本轮**发现并修复 1 个高危账号接管缺陷**（见 §6 与 `SECURITY_AUDIT.md` R93 §93.1）。
> **部署友好**：新增能力**默认全部休眠**（OAuth 需配 provider 凭据、2FA 需 `BLOG_TWOFA_ENABLED=true`），**无新增必填环境变量**，不配置则行为与 v3.20.0 完全一致。

### 1. 内容多语言 M1（译文配对）

- `Post` 新增 `lang` 与 `translation_group` 两列；列表/详情支持 `?lang=`，指定语言无译文时**自动回退原文**（不会出现空白页）。
- OG / sitemap / feed 输出 `hreflang` 互链；后台文章表单可直接填写语言与译文组；SPA 支持 `?lang=` 解析并同步 `<html lang>`。
- 前端构建产物须**重新构建**（改了 `vue-frontend/src/**`）。

### 2. PWA 可安装 / 离线

- `vue-frontend/public/` 新增 `manifest.webmanifest`、`sw.js`、`offline.html` 与 4 个图标（192/512 + maskable）。
- 缓存策略：**导航 network-first**（离线回退 `/offline.html`）、文章只读 API stale-while-revalidate（离线可读）、**后台与其余 `/api/*` 一律不缓存**。
- 右下角出现「安装应用」按钮（仅浏览器触发 `beforeinstallprompt` 时）。
- **无需改 Nginx**：nginx `location /` 已 `try_files`，`/sw.js` 与 `/manifest.webmanifest` 落在站点根、scope 自动为 `/`。

### 3. 读者积分勋章（gamification）

- 匿名读者用 httpOnly cookie `reader_token` 标识，登录读者绑定 `user_id`；积分规则集中可调（阅读 +2 / 评论 +5 / 每日访问 +1 / 分享 +3）。
- **同 reader + 同 reason + 同文章 + 同天**去重防刷；按累计积分自动授予勋章（初来乍到 10 / 阅读达人 50 / 热心评论 120 / 忠实读者 300 / 博客传奇 800）。
- 新增 `GET /api/reader/me`、`GET /api/reader/leaderboard`；文章页展示积分与勋章。
- ⚠️ **公开排行榜会显示登录读者的用户名**（匿名读者显示「读者N」）。这是排行榜可辨识所必需的，如不希望对外展示用户名，可在后台停用该入口或改 `gamify.leaderboard()`。

### 4. OAuth 第三方登录（可选，config-gated）

- 支持 GitHub 与 Google；回调地址需在各 provider 后台登记为 `https://<本站>/api/auth/oauth/{github,google}/callback`。
- **未配置凭据则完全休眠**：`/api/auth/oauth/<p>/start` 返回 503，登录页**不显示**对应按钮。
- 出站请求走**固定白名单 URL + 禁止跟随重定向**（防半盲 SSRF）。

### 5. 双因素认证 2FA / TOTP（可选，默认关闭）

- **零新增依赖**：TOTP 由标准库实现（RFC 6238），用官方 6 条测试向量自证正确；**不需要 `pip install pyotp`**。
- 绑定入口：后台侧边栏「🔐 两步验证」（管理员与普通用户均可见），扫码或手抄密钥 → 输入 6 位码确认 → **一次性下发 8 个恢复码**（设备丢失时的唯一救命通道，请务必保存）。
- 登录流程：已启用账号在密码校验通过后**暂不建立登录态**，需再输入动态码（挂起态 5 分钟有效）；动态码与恢复码均可，且**同一时间窗的码用过即失效**（防重放）。
- 密钥**加密落库**（Fernet，由 `SECRET_KEY` 派生），绝不存明文；关闭需「密码 + 动态码」双确认。
- 启用开关：`BLOG_TWOFA_ENABLED=true`（默认 false）。未启用时所有 2FA 入口短路，**登录流程完全不变**。

### 6. 🔴 安全修复：OAuth 未验证邮箱可导致账号接管

**缺陷**：原实现直接用 GitHub `/user` 返回的 `email` 匹配本地账号。该字段是**用户可自填的公开邮箱、不带验证断言** —— 攻击者把 GitHub 公开邮箱改成受害者邮箱，即可通过 OAuth 登录**接管受害者本地账号**。

**修复**：把「provider 是否断言邮箱已验证」提升为安全边界 —— GitHub 只信任 `/user/emails` 中 `verified && primary` 的条目，Google 用其 `email_verified` 字段；**未验证邮箱绝不参与既有账号匹配**（改为新建独立账号，且不落 `email` 列）。

**验证**：新增 3 条回归测试，**4 处变异验证全部变红**（证明测试真能抓住回退）。

### 7. 数据库与部署

- 新增 6 张表：`Reader` / `PointLog` / `Badge` / `ReaderBadge` / `OAuthAccount` / `UserTwoFactor`。均由 `_migrate_new_tables_v3()` + `db.create_all()` **启动自愈**，**无需手工 SQL、不走 Alembic**。
- 2FA 走**新表**而非给 `user` 加列：SQLite 的 `create_all()` 只建新表、**不 ALTER 已有表**，旧库升级时加列不会生效。

### 8. 新增环境变量（全部可选）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OAUTH_GITHUB_CLIENT_ID` / `OAUTH_GITHUB_CLIENT_SECRET` | 空 | 配置后启用 GitHub 登录 |
| `OAUTH_GOOGLE_CLIENT_ID` / `OAUTH_GOOGLE_CLIENT_SECRET` | 空 | 配置后启用 Google 登录 |
| `BLOG_TWOFA_ENABLED` | `false` | 设为 `true` 开放 2FA 绑定 |

### 9. 验证

- 全量 **269 passed**（新增 32 条：OAuth 13 + 2FA 19）；`ruff check myblog tests` 全绿；**lint 债务棘轮维持 648 = 648**（未抬基线）。
- 前端 `vite build` 通过。

---

## v3.20.0（2026-09-23 · 待办清单批次：工程化门禁 + 异步化 + 可观测性 + 前端 a11y）

> **来源**：用户要求「查看待升级清单」后指示「全部做」。清单来自 `ROADMAP.md` §5.8/§5.9（第一、三轮第三方审计的延后批次）。
> **做法**：先**实测当前真实状态**再动手 —— 结果发现若干审计项「按现状做等于白做」，另有一项我原本的判断被实验推翻（见 §3）。**未能成立的假设我已从代码注释里清掉**，不留错误结论。

### 1. 工程化门禁（原审计：CI 只有 test+build，无 lint / 无 ruff 配置）

**`pyproject.toml`（新增）** —— 只承载 ruff 配置，刻意不写 `[project]`（不引入第二处版本号）。`select` 选型原则是「**高信号、且加入当天全绿**」，因为一上线就红的门禁很快会被绕过：

| 规则 | 命中 | 处置 |
| --- | --- | --- |
| `E9` / `F63` / `F7` / `F82` | 0 | 直接纳入（语法错、未定义名等「一定会炸」的） |
| `B`（bugbear） | 8 | 已修：4×`B904` 异常链（`raise ... from`，影响排障）+ 4×`B007` 未用循环变量 |
| `F841` | 3 | **抓到的全是真死代码**（`admin/settings.py::mail_keys`、`admin/stats.py::total_hour`、`mail_notify.py::app`）+ tests 里 3 处未用变量 |
| `S105` | 3 | **全是误报**（`BAIDU_TOKEN_KEY`/`KEY_TOKEN_FMT`/`_CAPTCHA_PASS_KEY` 是 Setting/session **键名**）→ 就地 `# noqa: S105` 并写明理由 |
| `C4` / `RET` / `A` | 5 / 4 / 0 | 已修（`C401` 集合推导 4 处、`RET504` 2 处；`RET503` 2 处是 Flask `before_request` 的**隐式 None = 放行**语义，属误报，已 noqa；`C408` 1 处保留 `dict()` 可读写法并 noqa） |
| **`DTZ`** | 13 | **明确不修**：项目约定是 **naive UTC 存储**（`myblog/_time.py` docstring 写明「数据库 DateTime 列均为 naive 存储」）。改成 tz-aware = 改存储语义 + 数据迁移 → **这是设计决定，不是缺陷** |

**`tools/lint_debt.py` + `tools/lint_debt_baseline.json`（新增）—— lint 债务棘轮**：历史债（`BLE001` 272 / `F401` 171 / `S110` 94 / `ARG` 73 / `T20` 68 / `SIM` 40）不能一次修完（尤其 91 处 `except: pass` 涉及「该记日志还是该静默」的语义决策），但放着就会继续长。棘轮把当前数量记成基线，**只允许减少、不允许增加**。
刻意**不**把 `I`（导入排序）/ `UP`（pyupgrade）/ `PTH`（强制 pathlib）收进棘轮 —— 它们属个人风格偏好，收进来只会制造无意义的历史债务。

**CI（`.github/workflows/ci.yml`）**：新增 `lint` job = `ruff check .`（阻断）+ 债务棘轮 + `check_i18n.py` + **发布公钥一致性**（钉住 `update.sh` 内置公钥值 —— 它是更新链 fail-closed 的根锚点）。`build` job 的 `npm install` → **`npm ci`**（严格按 lockfile 装，避免「CI 绿」与「本机装出的那份」脱钩）。
> 诚实记录：完整的 `verify_package_checksums.py` **无法在 CI 跑** —— 它需要已签名的发布物，而签名私钥只在本机且绝不入库。CI 只能守住「公钥值」这个不变量。

**`.github/dependabot.yml`（新增）**：pip / npm / github-actions 三类，小版本与补丁**分组**成一个 PR（避免单人维护者被 PR 淹没），**明确不开启自动合并** —— 因为 `requirements.txt` 的上限是**带理由刻意选的**（`cryptography>=50,<51` 是消化 CVE 后抬的），且该文件记录了「运行环境最低 Python 版本由 bleach 决定为 >=3.10」这条约束需要人工复核。

### 2. `gunicorn_conf.py` 入库（原审计：未入库，重建站点会丢）

仓库根新增该文件（**不在部署包里** —— `package.py` 只收 `myblog/`，故 `update.sh` 不会覆盖它）。`deploy_guide.md` 新增「第 2b 步」。
把三个此前只存在于线上、且被第三方报告**误判过**的事实写进文档：
1. 配置写的是 `worker_class = 'sync'`，但 **gunicorn 22 在 `threads > 1` 时会自动升级为 `gthread`**（启动日志 `Using worker: gthread`）；
2. **实际并发槽 = 4 × 2 = 8**，不是 4（第三轮报告据此误判为「2~3 个 sync worker、两个点击即可打挂全站」，见 R91）；
3. 4 个 worker 是刻意的（2 核机器 + SQLite 写锁竞争）。

### 3. 通知异步化（原审计：请求路径内的同步外网调用）

`myblog/notify.py` 重写为**后台线程**（原来每渠道 `timeout=6`，两渠道齐配即最坏**阻塞 12s**，而 5 个调用点全在请求路径上）。
**此前的两个判断需要更正，一并记录**：

- ❌ **我原以为「传 ORM 对象进线程会抛 DetachedInstanceError」—— 实测证伪。**
  实测（Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.52）：detached 的 `Post` 上**标量属性照常可读**（值仍在实例 `__dict__`），所以 `mail_notify` 当年那样传对象**对它自己的用法是能工作的**，不存在「订阅者静默收不到信」的历史缺陷。
- ✅ **真实的风险边界是懒加载关系**：detached 实例上访问**从未加载**的关系（如 `post.author`）**会抛** `DetachedInstanceError`。
  → 因此 `notify.py` 采取「**调用线程内先取快照**」（线程内只碰字符串），`mail_notify` 改为「**传 id、线程内重查**」（线程内拿到属于新 session 的活对象）。
  **这两处改动是纵深防御，不是修 bug** —— 区别很重要，判断依据就是上面两条实测。
- 同时把两个模块的 `print(...)` 与静默 `except: pass` 改为 `logger.warning(..., exc_info=True)`（可观测性）。

### 4. `/health` 存活探针（新增）

`GET /api/health` → `{ok, version, db}`，**无需登录**、只做一次 `SELECT 1`、**不出网**、依赖不可用时返回 **503**（便于通用 HTTP 探活直接判定）。
安全约束：响应字段严格只有三项，**不回显配置/路径/密钥/异常细节**（有测试逐条断言 `SECRET`/`password`/`token`/`/www/`/`sqlite` 等字样不出现）。
此前项目**没有任何探活端点**，`diagnostics.py` 是人工触发的拉取式体检 —— 即「站点挂了」只能靠人先发现。

### 5. 前端 a11y（原审计：零 `aria-live`、无 skip-link、灯箱无 `role="dialog"`、Observer 泄漏）

先实测发现**改动面比审计描述小得多**（`vue-frontend/src` 仅 38 个文件）。逐项处置：

| 项 | 结论 | 处置 |
| --- | --- | --- |
| 零 `aria-live` | **真缺陷，但根因不是「忘了写」**：`lib/toast.js` 给每条 toast 现建现挂 `role="status"`，而 **live region 必须先在 DOM 中存在**才会被朗读 → 实际不会被播报 | 改为**宿主常驻** `role="status" aria-live="polite" aria-atomic="false"`，toast 只往里塞文本 |
| 无 skip-link | 真缺陷 | `App.vue` 新增跳转链接 + `<main id="main-content" tabindex="-1">`，并补 i18n key（zh/en 同步，`check_i18n.py` 通过） |
| 灯箱无 `role="dialog"` | 真缺陷 | `PostView.vue` 补 `role="dialog" aria-modal="true" aria-label`。**未做完整焦点陷阱**，已在注释里记为已知缺口，不假装达到 modal 的 WCAG 要求 |
| IntersectionObserver 泄漏 | **只有一处是真泄漏**：`DocsView.vue` 是**路由组件**，每次进入 `/docs` 都新建 observer 且从不 `disconnect` → 持续累积 | 新增 `onBeforeUnmount` + `disconnect`。`main.js` 的 `v-reveal` 是**一次性** observer（命中即 `disconnect`），无需改 |
| scroll/resize 监听未清理 | `App.vue` 是**根组件、SPA 内不卸载** → **理论问题、无实际影响** | 既然该处已有 `onBeforeUnmount`，顺手收口（并在注释里说明它并非真实泄漏） |

### 6. 评估后**不做**的两项（附实测依据，避免后来人重复讨论）

| 审计项 | 实测 | 结论 |
| --- | --- | --- |
| **`post`/`comment` 主表零索引** | 生产真实行数：`post` = **7**、`comment` = **1**；而**有量**的表其实都已建索引（`visit_log` 2593、`ip_region` 854、`read_log` 85、`setting` 77）；`post.slug` 也已有 unique 自动索引 | **不加**。7 行加索引只有写入成本，还要改表结构。**改为设触发条件**（如 `post > 500` / `comment > 5000` 再加）。唯一「有量且无索引」的是 `audit_log`（218 行），也没到需要索引的量级 |
| **`inject_globals` 每次渲染 8 条查询** | v3.18.6 SSR 退役后，全项目只剩 **2 个模板** extend `base.html`（`login`/`register`），其余 **45 处渲染全是 `admin/*`** → 这 8 条查询**只发生在后台页与登录页**；公开文章页由 nginx 直出 SPA + JSON API，根本不经过它 | **不加缓存**。项目有 **20 处**直接写 `Setting`（无单一收口点），做缓存就得引入 TTL + 失效钩子，代价是「改完主题后一段时间显示旧值」，换来的只是省掉后台点击时的 8 条小表查询 —— 收益小于复杂度。理由已写进 `inject_globals` 的 docstring |

顺带删掉一处**真死代码**：`inject_globals` 注入的 `now_year` 未被任何模板使用（同时消掉一处 `DTZ005`）。

### 7. 第二轮（同日续做：真缺陷闭包 + 订阅源 + CI 深度）

用户随后要求「能做的全部实现」。这一轮先把上一轮**只能靠实测才发现的真缺陷**补齐，并记录**一条要更正审计的结论**：

| 项 | 复验 | 处置 |
| --- | --- | --- |
| **每页 2 个 `<main>`** | **真缺陷**（上一轮我漏了它）：`App.vue` 有 1 个 `<main>`，**11 个视图各自又有 1 个** → 每页 2 个。`main` 是 landmark，一个文档只应有一个，多了会让读屏的「跳到主内容」产生歧义 | 保留 `App.vue` 那个（同时是 skip-link 落点），把 11 个视图的 `<main>` 改 `<div>`（先验证视图 CSS **不依赖** `main` 标签选择器，再改） |
| **灯箱焦点陷阱** | 上一轮只补了 `role="dialog"`；Tab 仍会跑到背后页面 → 键盘/读屏用户「掉出对话框」 | 补完整焦点管理：打开时记住来源焦点并聚焦关闭按钮、**Tab 在对话框内循环**、关闭时把焦点**归还**给来源元素 |
| **`/api/qr` 未配 `site_url` 时用 `request.host_url`**（R90 待办②） | **真缺陷**（与项目「对外地址只走 `site_base()`」原则冲突；`/api/og/*` 与 `_abs()` 在 v3.18.9 已收口，此接口是唯一漏网） | 相对路径分支**不再回退请求 Host**，未配置即 400（带可操作提示）。**同时必须保住别名域名可用性** —— 前端 `postUrl` 是 `location.origin` 派生的，所以绝对 URL 分支**继续放行本次请求的 host**（那是访客地址栏里的域名，且 URL 由客户端显式传入）。两条要求方向相反，故写了 7 条测试钉住 |
| **Atom 1.0 订阅源**（ROADMAP §5.4 最后一项） | 此前只有 RSS 2.0 | 新增 `GET /feed.atom`，**复用 `/feed.xml` 的同一条查询**（不新增查询逻辑，避免两套订阅源口径漂移）。⚠️ nginx 对 `/feed.xml` 是 `location =`（精确匹配）→ `deploy_guide.md` 已同步补 `location = /feed.atom`，**漏了会落到 SPA 拿到 index.html** |
| **CI 覆盖率** | 实测基线 **49%**（9216 语句） | 测试改为带 `coverage` 运行，`--fail-under=45` 作**防回退下限**（不是「证明覆盖充分」）。覆盖率上去后请一起抬阈值 |
| **CI 依赖 CVE 扫描** | 实跑 `pip-audit -r myblog/requirements.txt` → **No known vulnerabilities found** | 因为基线干净，故设为**阻断项**（若报漏洞应抬依赖版本，而不是把这一步改成非阻断） |

**⚠️ 需要更正审计的一条（「`v-html` 未统一 `sanitizeHtml`」）**：我逐个查了 4 处未走客户端 `sanitizeHtml` 的 `v-html`，**其数据全部在服务端已消毒** ——
`api/site.py:20`（关于页）、`api/site.py:103`（公告，还先过 `render_markdown`）、`feed_agg.py:258`（博客圈第三方 RSS 摘要）、搜索高亮的 `<mark>`（服务端先 `escape` 全文再插标记）。
**消毒在服务端 = 正确的信任边界**。客户端再洗一遍属纵深防御，但对「管理员富文本」槽位有**剥离合法标记**的风险（DOMPurify 默认白名单 ≠ 服务端 `clean_html` 白名单），**收益不为正，故不加**。

### 8. 第三轮（同日续做：统计深度 + SEO 自动推送）

用户要求继续把功能类清单做掉。这轮选**零表变更、无外部凭据、可验证**的项：

| 项 | 来源 | 处置 |
| --- | --- | --- |
| **来源渠道 TOP** | §5.2 | 新增 `_label_referrer` / `_top_referrers`：把 `VisitLog.referrer`（v3.17.3 起只存 origin，天然不泄隐私）映射成可读名（搜索引擎 / 社媒），30 天窗口取 TOP 10 |
| **实时在线** | §5.2 | `compute_online`：最近 10 分钟独立 IP 近似（字段刻意叫 `online` 而非 `online_users`，避免被当成精确在线人数） |
| **趋势环比** | §5.2 | `compute_period_compare`：本期 vs 上期 PV / UV / 评论 / 订阅；**分母为 0 时 `pct=None`**（而非 0 / ∞），前端显示「—」 |
| **CSV 导出** | §5.2 | 新增 `GET /admin/stats/export`（超管 + 全局 CSRF）：访问日志导出，**UTF-8 BOM**（Excel 中文不乱码）+ **公式注入防护**（含 `= + - @` 前缀单元格加前缀单引号）；`days` 上限 365 防 `?days=999999` 拉全表 |
| **SEO 自动推送** | §5.4 | 原「新文 ping 百度 / Google / Bing」端点**实测不可用**（Bing `https://www.bing.com/ping` 返 **HTTP 410 Gone**、Google 超时）→ 改为复用 `enqueue` 的「**发布即自动推送**」（`maybe_auto_push`）。**默认关闭**（`SEO_AUTO_PUSH=1` 或后台设置 `seo_auto_push=1`）；只推**可见**文章（复用 `visible_posts_query`，含未到点定时拒绝）；复用 `enqueue` 自带「3 次 / 5 分钟」限流与 pending 去重；无凭据引擎被 `submit_posts` 跳过；全程异常不抛出、绝不拖垮发布主流程 |

> ⚠️ **统计深度刻意不做设备 / 浏览器分布**：`VisitLog` 没有 UA 字段，要做必须新增列 —— 与项目「能不改表结构就不改」的原则冲突，故列在 `ROADMAP.md` §5.9.1 待办而非强做。

后台统计页（`admin/stats.html`）新增三块：环比卡片、来源渠道 TOP、CSV 导出按钮（7 / 30 / 365 天）。5 处发布路径（后台保存 / 发布 / 恢复 + 前台 API 发布 + 评论触发）均接 `maybe_auto_push`，统一 `try/except` 包裹（防拖垮发布）。

### 9. 验证

- 全量 **221 passed**（185 基线 + 36 新增：统计深度 `test_stats_depth.py` 5 条 + SEO 自动推送 `test_seo_push.py` 4 条 + 第二轮的 `test_lint_debt.py` 6 条 / `test_notify_health.py` 10 条 / `test_qr.py` 7 条 / `test_atom_feed.py` 4 条）。
- **覆盖率 49%**（9216 语句），CI 以 `--fail-under=45` 作防回退下限。
- 新增测试都做了**变异验证**：棘轮前缀匹配（连错两次的坑）与 `mail_notify` 的「传 id vs 传对象」回退后都会变红；`maybe_auto_push` 的「默认关闭 = noop」「拒绝不可见 / 回收站 / 私密 / 未到点定时」回退后变红。
- `ruff check .` 全绿（阻断集）；`tools/lint_debt.py` 棘轮通过（**648 = 648，无新增**：第三轮新增的 9 处 `# noqa: BLE001/S110` 来自「发布主流程不能被 SEO 推送拖垮」的防御性 `except` —— 每处已写明理由，与「CSV 路由用具体异常替代裸 `except` 消除 1 处」相抵）；`check_i18n.py` 通过。
- 前端 `vite build` 通过（93 模块）。`pip-audit` 对 `requirements.txt` 扫描：**无已知漏洞**。
- 开发库 `blog.db` sha256 + mtime 双查零变化（本轮零表结构变更）。

---

