# 更新日志归档件（v3.20.0 ~ v3.21.2）

> 这是**归档件**，不是当前文档。
> **拆分点**：`CHANGELOG.md` 因体积守卫（上限 200 KB）触发，在 v4.8.5 发布前
> 把 v3.21.2 ~ v3.20.0 这四轮搬到这里，主文件保留 v3.22.0 及以后。
> 查**近期**（v3.22.0 ~ 最新）变更请回 `CHANGELOG.md`；更早的
> v3.19.2 及以前见 `docs/archive/CHANGELOG_v3.18.6-v3.19.2.md`，
> v3.18.5 及以前见 `docs/archive/CHANGELOG_v1-v3.18.5.md`。
> **归档不是删除** —— 本文件内容与搬迁前逐字一致。

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
