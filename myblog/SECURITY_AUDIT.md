# 安全审计报告（SECURITY_AUDIT.md）

> **📦 历史归档**：第一轮 ~ 第八十轮（R1~R80）已归档至 `docs/archive/SECURITY_AUDIT_r01-r80.md`；本文件从 R81 起。

## R81 · page_translate 全站翻译插件（v3.18.0）

**范围**：新增插件 `myblog/plugins/page_translate/`（后端端点）+ `myblog/static/plugins/page_translate/widget.js`（远程组件）；核心侧为**纯减法**（移除 `store.js` 的 i18n 与 `App.vue` 语言按钮），不新增暴露面。

### 81.1 七维复核
- **XSS**：插件译文**一律以 `textContent` / `nodeValue` 写入文本节点**，绝不经 `innerHTML` / `v-html`（本插件未使用富文本槽位）；后端只返回纯字符串数组，不拼接 HTML。→ 无新增 XSS 面。
- **SQL 注入**：插件**不建表、不落库、无 SQL**。
- **越权**：`/translate` 定位为**面向访客的公开只读型转发**（不读写任何用户数据、不返回他人信息）；`/config` 仅回站点主语言与 LLM 是否配置，无敏感信息。故无需鉴权，但已用限流 + 白名单约束。
- **SSRF**：出站仅由后端 `_llm_chat` 访问**管理员在后台配置的 LLM Base**（非用户可控 URL），沿用 AI 摘要同一链路；前端外链仅浏览器内置 Translator（本地能力，无网络 URL）。
- **CSRF**：`POST /api/plugin/page_translate/translate` 落在 `/api/` 前缀 → 受全局 `_csrf_protect` 覆盖，要求 `X-CSRF-Token`（`test_translate_requires_csrf` 锁死 403）。
- **密钥泄露**：不新增任何密钥；LLM Key 仍走既有 Fernet 加密 Setting（`games_llm_key_enc`）。
- **资源泄漏 / 成本**：**双层限流**（IP 40/分 + 全局 240/分）防刷爆 LLM 账单；单次 ≤40 段 / ≤4000 字符防超长 payload；上游 `timeout=60`；前端译文缓存避免重复请求。
- **限流**：同上（`rate_limit` 双 key）；`/config` 为只读 GET、无成本，不额外限流。
- **文本注入 / 幻觉**：模型输出按 JSON 数组解析，**条数必须与输入一致**否则 502（不把半截/错位译文写页面）；解析失败即报错，不写 DOM。

### 81.2 低风险（已记录）
- 目标语言白名单为静态 10 种；如需扩展改 `_LANG_NAMES` 即可（无动态注入面）。
- 前端译文缓存写 `localStorage`（用户本机），不含服务端隐私；>4000 条自动裁剪。
- 浏览器内置 Translator 属**实验性 API**，仅在受支持浏览器启用，失败自动回退，不影响主流程。

### 81.3 验证
- `tests/test_plugin_page_translate.py` 14 例全过；`tests/test_plugin_system.py` 全过；全量 **113 passed**。
- `node --check widget.js` 通过；前端 `vite build` 通过；后端 `py_compile` 通过。

**R81 结论**：**0 遗留**。插件为「公开只读转发 + 纯文本写 DOM」形态，无 XSS / SQLi / SSRF / 越权新面；成本面已用双层限流 + 长度上限约束。

---

## R82 · utils.py / admin/posts.py 拆分重构（v3.18.1）

**范围**：纯代码移动（`utils.py` → `myblog/utils/` 包；`admin/posts.py` → 5 个领域模块）。**无逻辑变更、无表结构变更、无新增/删除依赖、无新增环境变量、无路由增删**。

### 82.1 安全面复核（七维）
- **XSS**：`clean_html` / Markdown 渲染 / `_upgrade_img_avif` 原样移动；白名单常量 `_ALLOWED_TAGS` / `_ALLOWED_ATTRS` 随 `utils/render.py` 迁移，**取值未变**。
- **SQL 注入**：无 SQL 文本变化，ORM 调用原样。
- **越权**：26 个后台路由的装饰器（`@login_required` / 超管校验等）随函数一同迁移（`ast.dump` 含装饰器，已证等价）；`admin_bp` 与函数名不变 → 权限口径零变化。
- **SSRF**：无变化（`utils/net.py` 的可信代理 / 客户端 IP 逻辑原样）。
- **CSRF**：`generate_csrf_token` / `check_csrf_token` / `_sign_csrf` 原样移至 `utils/security.py`；`app.py` 的豁免清单与校验入口未动。
- **密钥泄露**：无变化。
- **资源 / 成本**：`utils/net.py` 的限流（含 Redis 回退）原样；无新增外部调用。

### 82.2 结构性保障（本次采用的可证性手段）
- **逐名 `ast.dump` 等价性证明**：utils **44/44** 名、posts **31/31** 名，**0 处结构差异**（含装饰器）→ 证明是「纯移动」而非「改写」。
- **endpoint 守恒**：原 26 条路由函数全部仍在 `app.view_functions`；模板与代码中 **99 处 `url_for('admin.*')` 全部可解析** → 无断链 404/500。
- **导入面零改动**：`utils/__init__.py` 显式重导出全部 44 个名字（含 `_redis` / `_sign_csrf` 等私有名，5 个测试文件依赖），故 27 个导入点无需改动 → 无遗漏改写面。

### 82.3 低风险（已记录）
- 拆分后「模块属性补丁」语义有变：`monkeypatch.setattr(utils, "X", ...)` 不再影响 `utils/<mod>.py` 内部的同名自调用（如 `render_post_html` 调用同模块 `render_markdown`）。**仅影响测试打桩**，已同步 `tests/test_render_cache.py` 的补丁目标至 `utils.render.render_markdown`；生产代码无此类动态查找（`grep getattr(utils` **0 命中**）。

### 82.4 验证
- `113 passed`；`compileall` 通过；`ast.dump` 等价性 + endpoint 守恒 + `url_for` 全解析三项通过。

**R82 结论**：**0 遗留**。纯重构，安全面零变化；以「等价性证明 + endpoint / 导入面守恒」替代常规人工复核，风险压到最低。

---

## R83 · 移除内置插件 page_translate + 恢复核心 i18n（v3.18.3）

**范围**：删除 v3.18.0 引入的插件（`myblog/plugins/page_translate/`、`myblog/static/plugins/page_translate/widget.js`、`tests/test_plugin_page_translate.py`），`ENABLED_PLUGINS` 默认值恢复为空。插件框架保留。

### 83.1 安全面影响（净减少）
- 删除的对外面：`GET /api/plugin/page_translate/config`、`POST /api/plugin/page_translate/translate`、静态资源 `/static/plugins/page_translate/widget.js`。
- 上述端点原本即「公开只读 / CSRF + 双层限流 + 白名单 + 长度上限 + 零落库」，**移除后攻击面净减少**（少一个对外 JSON 端点与一个静态 JS）。
- **无新增**端点、依赖、环境变量、表结构；`ENABLED_PLUGINS` 恢复为空 = 不加载任何插件（插件框架的失败隔离与紧急关停能力不变）。
- 前端：仅少一个浮层按钮，无其他变化（v3.18.0 移除的中英切换不在本次范围）。

### 83.2 验证
- `99 passed`（113 − 14 条插件测试）；`compileall` 通过；`/api/plugins` 返回空清单。


### 83.3 附：核心中英切换恢复（同版）
- v3.18.0 移除的核心 i18n 已**逐字节还原**（`store.js` 的 `I18N`/`t()`/`setLang`/`initLang`/`state.lang`、`App.vue` 24 处 `t()` 与两个语言按钮、`global.css` 的 `.lang-toggle`）。
- 安全面：`t()` 的返回值只经 Vue `{{ }}` 文本插值输出（**自动 HTML 转义**），词典为**静态常量**，**无用户输入注入面**；`localStorage` 仅存语言偏好（`lang`），无敏感数据。→ 安全面不变。

**R83 结论**：**0 遗留（对外面净减少）**。
---

## R84 · i18n 补齐（v3.18.4）

**范围**：纯前端文案接线（`App.vue` 24 处、`store.js` 词典 17→31 键、`components/Sidebar.vue` 2 处）。无后端/端点/依赖/表结构变化。

### 84.1 安全面复核
- **XSS**：新增的 31 个词典值均为**静态常量字符串**，经 Vue `{{ }}` 文本插值输出（**自动 HTML 转义**）；未引入任何 `v-html`。→ 无新增面。
- **其余六维**（SQLi / 越权 / SSRF / CSRF / 密钥 / 限流）：未触碰任何请求、鉴权、网络或存储逻辑。→ 无变化。

### 84.2 验证
- 词典键 zh/en 完全一致（31 = 31）；实际使用 = 31（**0 死键 / 0 缺失**）；前端 `vite build` 通过；`99 passed`。

**R84 结论**：**0 遗留**。纯文案接线，安全面零变化。

---

## R85 · 第三方独立审计 P0 批次（v3.18.5）

**背景**：2026-09-20 收到一份针对 tag `v3.18.4` 的第三方独立静态审计报告（8 章 / 240 文件 / 17,490 行 Python）。报告列出 8 项「现在就是坏的」缺陷，并指出 3 处既有审计轮次的**结论失真**。本轮**逐条打开对应文件核对复现**后全部修复，另附带修 3 项同源缺陷。**本轮未改任何表结构、未新增依赖、未改前端产物。**

### 85.1 修复清单（含对既有轮次结论的更正）

| 编号 | 级别 | 问题 | 位置 | 状态 |
|---|---|---|---|---|
| R85-1 | Critical | `redirect` 未导入 → 会话失效命中非 `/api/` 路径时 `NameError` 500 | `app.py` 三处 | ✅ 已修（补导入 + `redirect(safe_redirect(url_for(...)))`） |
| R85-2 | Critical | 前台注册/登录不写 `session_version` → 改密用户登录后即失效 | `routes.py` 2 处 | ✅ 已修（`admin/auth.py` 原为正确实现） |
| R85-3 | Critical | `return app` 之后定义 CLI → `flask seed` 从未注册 | `app.py` | ✅ 已修（注册上移，删死函数与不可达 `return`） |
| R85-4 | Critical | `/api/review/annual` 泄露隐私空间 + 回收站文章的标题/slug | `api/review.py` | ✅ 已修（改走 `visible_posts_query()`） |
| R85-5 | Critical | `/api/ai/summary/<slug>` 无可见性过滤 → 可读任意文章摘要 | `api/ai.py` | ✅ 已修（`visible_posts_query(user=…)`） |
| R85-6 | Critical | Markdown 表格被 bleach 白名单静默剥空 | `utils/render.py` | ✅ 已修（补表格标签 + `_RENDER_VERSION` 2→3） |
| R85-7 | High | 零 `errorhandler` → `first_or_404()` 对 JSON 客户端返回 HTML | `app.py` | ✅ 已修（400/403/404/405/422/500 + 4 个模板） |
| R85-8 | High | 测试直接在真实开发库 `myblog/data/blog.db` 上增删数据 | `tests/conftest.py` | ✅ 已修（隔离临时库 + `enable_scheduler=False`） |
| R85-9 | High | 审计日志来源 IP 取 XFF **最左段** → 可任意伪造 | `admin/_helpers.py` 2 处 | ✅ 已修（改走 `get_client_ip()`） |
| R85-10 | Medium | 后台「AI 摘要」页仅 `@admin_required`，却会外发正文到自设 LLM Base | `admin/ai_summary.py` | ✅ 已提权 `@super_required`（导航同步移入超管区） |
| R85-11 | Low | `/admin/?category_id=abc` → `ValueError` 500 | `admin/stats.py` | ✅ 已修（非法值按不筛选处理） |
| R85-12 | Low | 未鉴权的 `/api/stats/dashboard` 回显 `str(e)` | `api/stats.py` | ✅ 已修（详情只写日志） |
| R85-13 | Low | 残留 `app.config["ADMIN_HASH"]`（无读取方）+ `_orig_after` 死赋值 + 未用导入 | `app.py` | ✅ 已删 |
| R85-14 | High | 文档称「全站时间统一北京时间」，但 7 处 Jinja 模板 + `/api/games` 仍打 naive UTC | 模板 ×7、`api/games.py` | ✅ 已修（统一 `bj` 过滤器 / `fmt_bj`） |

**对既有轮次结论的更正（原结论为假）**：
- **R70-1**：`/api/review` 标注「公开只读，无敏感数据」→ 实际泄露隐私空间 + 回收站文章的标题与 slug（R85-4）。
- **R41-2**：审计 IP 标注「✅ 修复（纵深防御正确）」→ 对 `log_audit` / `log_login_attempt` 两条路径为假，仍取 XFF 最左段（R85-9）。
- **跨轮次**：README 声称「后台表格手机端可浏览全文」「硬编码颜色已统一替换为 token」「全站时间统一北京时间」——前两条经本轮复核**仍不成立**（详见下节未修项），第三条已在本轮代码层修复。

### 85.2 七维复核（本轮改动）

- **XSS**：错误页模板（`404/403/500/error` + `_error_base`）只输出 `error_code`（int）与 `error_text`（**服务端常量字典**，非用户输入）；`_render_error_page` 的兜底分支用 `%d`/`%s` 拼的是同一组常量。表格标签白名单**新增的是结构标签**，未放行 `style` / `on*` / `href`；`colspan/rowspan/align/scope` 均为非脚本属性；`srcset` 未放行（`<picture>` 由 `_upgrade_img_avif` 在清洗**之后**注入，路径仍受 `/static/` 前缀与磁盘存在性双重限制）。→ **无新增 XSS 面**。
- **越权**：本轮**净收紧**两处——`/api/ai/summary/<slug>` 加可见性过滤；后台 AI 摘要页由「管理员」提权为「超管」。`visible_posts_query(user=user)` 的隐私放行条件为 `user.is_super`，与 `models.py` 既有约定一致。
- **敏感信息外泄**：`/api/stats/dashboard` 不再回显 `str(e)`；审计日志 IP 改走 `get_client_ip()`（不再信任可伪造的 XFF 左段）；`session_version` 写入使「改密销毁旧会话」在前台登录路径真正生效（原先该路径下失效判定错误地作用于**所有**改密用户，属可用性缺陷，修复后行为与文档一致）。
- **CSRF / SSRF / SQLi / 限流 / 密钥**：本轮未新增任何写端点、未新增出站请求、未新增 SQL 拼接（`visible_posts_query` 为既有 ORM 查询）、未新增/变更密钥来源。→ 五维无变化。
- **资源与降级**：`get_client_ip()` 包在独立 `try/except` 内，取 IP 失败仍写审计（不因取 IP 失败丢日志）；错误页渲染失败有纯 HTML 兜底（防止「500 处理器自身再抛错」造成二次故障）。

### 85.3 验证

- **`112 passed`**（99 基线 + **13 条新增回归** `tests/test_p0_regressions.py`：每条断言在修复前逐一失败、修复后全绿）。
  - 其中 ① `test_session_version_mismatch_redirects_instead_of_500` 在开发过程中**真的抓到了一次自引入缺陷**：最初把 `redirect(...)` 误写成直接 `return safe_redirect(...)`（字符串），Flask 会将其转为 **200 文本响应**而非 302——测试立刻暴露，已改回 `redirect(safe_redirect(...))`。
- `compileall -q myblog` 通过。
- **`myblog/data/blog.db` 的 sha256 与 mtime 在全量测试前后完全一致**（修复前 pytest 会写该库）。
- 无表结构变更、无新增依赖、无新增环境变量、**前端产物零变化**。

### 85.4 未纳入本轮（已记入 ROADMAP，按报告建议分批）

报告第 2~8 章中**改动面大或需要外部决策**的部分**故意不在本补丁版内混做**：
- **2.1 在线更新链 fail-open**（报告判为全仓最高风险，等价 RCE 通道）：需要引入分离物签名与**签名私钥托管**决策、公钥内置、发布工作流改造；属基础设施级变更。
- **3 双前端结构**：Nginx 使 `/post/*` 等 9 个 SSR 路由收不到流量，README 的 SEO 能力对国内引擎实际失效——涉及产品决策（退役 SSR vs 预渲染）。
- **4 索引 / 查询 / 缓存**、**4.6 请求内同步外网调用**、**6.3 可观测性（零 errorhandler 之外的日志/指标）**、**5 前端 a11y / SEO 细节**、**6.1 CI 工程化**、**文档瘦身（SECURITY_AUDIT 342KB / CHANGELOG 134KB / ROADMAP 116KB）**。

**R85 结论**：**0 遗留（本批次范围内）**。8 项 P0 全部核对复现并修复，3 处文档失真已更正，报告第 2~8 章明确延后并登记。

---

## R86 · 退役公共 SSR（v3.18.6）

**范围**：`myblog/routes.py` 的 8 个页面级 SSR 路由改为 410 Gone（保留 endpoint 名）；删除 7 个死模板；`app.py` 的 `_HTTP_ERROR_TEXT` 增加 410 并注册 `errorhandler(410)`；清理 `routes.py` 6 个随之失效的导入。**无表结构变更、无新增依赖、无新增环境变量、前端未动。**

### 86.1 七维复核

- **攻击面（净减少）**：退役的 8 个路由原本承载大量 DB 查询与模板渲染（首页分页、文章页 + 评论全量加载 + JSON-LD/OG 拼装、分类/标签筛选、搜索 LIKE 查询、归档分组）。它们在生产从未被外部访问到（Nginx 不反代），因此退役**不改变线上暴露面**，但**移除了 8 个「一旦将来有人给这些路径加反代就会立刻生效」的未加固入口**——尤其 `/search` 的 `LIKE %q%` 全表扫描（无 FTS、无限流、无最小长度约束），以及文章页 `p.comments.filter_by(approved=True).all()` 的无分页全量加载（v3.18.5 修的是 API 侧分页，SSR 侧从未修）。
- **信息泄露（净减少）**：文章页 SSR 会向匿名访客输出作者名、发布时间、评论者昵称与地域；退役后这些出口消失。JSON-LD/OG 的拼装代码一并移除，不再有 `seo_description`/`summary` 被写入结构化数据的路径。
- **XSS**：退役后的 `/` 等路径走 `error.html`（只输出 `error_code`（int）与 `error_text`（服务端常量字典），无用户输入）；`base.html` / `login.html` / `register.html` 未改动；`DocsView.vue` 未改动。**无新增 XSS 面。**
- **CSRF / 越权 / SQLi / SSRF / 密钥 / 限流**：未新增任何写端点、未新增出站请求、未新增 SQL 拼接、未新增密钥。保留的两个 POST 入口（`/post/<slug>/comment`、`/post/<slug>/like`）原本就有限流 + 验证码（comment）/ 限流（like），**未做任何放宽**。
- **可用性风险（已核并规避）**：不能直接删路由——`base.html`（仍被 `/login`、`/register` 使用）里有 8 处 `url_for('main.post'|'main.archive'|…)`，删路由会让**登录页渲染 `BuildError`**，等于把用户锁在站外。故采用「路由保留、只换响应」。不做 302 → SPA 也是刻意的：Flask 路径与 SPA 路径同名，302 会让直接访问 `:8686` 的客户端自环。

### 86.2 验证
- **119 passed**（112 基线 + 7 条新增 `tests/test_ssr_retirement.py`）：8 个路径均 410；8 个 endpoint 名 `url_for` 恒等；`/login` `/register` 仍 200 且含中文文案；`/feed.xml` `/sitemap.xml` `/robots.txt` `/feed/comments` 仍 200；`/api/` 404 仍为 JSON；退役模板确已删除、认证与错误页未被误删。
- `compileall -q myblog` 通过；`git status` 确认无 `data/`、`*.zip`、临时脚本混入。

**R86 结论**：**0 遗留**。纯路由退役 + 死代码删除，安全面净减少，可用性风险（登录页 BuildError）已在设计阶段识别并规避。

---

## R87 · 更新链 fail-closed + Ed25519 发布物签名（v3.18.7）

**背景**：R85 摘录的第三方独立审计把「在线更新链完整性校验全链 fail-open」判为**全仓最高风险**，原话是「实际强度远低于文档描述，等价于一条 RCE 通道」。本轮按用户要求「**这个功能大家都能用**」落地：默认安全、开箱可用、想绕开必须显式声明。

### 87.1 原设计的根本缺陷（为什么哈希比对挡不住）

`sha256.txt` 与它描述的两个 zip **走同一条下载通道**（同一个 Release，同一个 `curl`）。因此「zip 哈希 == 清单里的哈希」只证明**两个文件彼此自洽**，不证明「清单是发布者写的」——能拿到包的人也能同时改写清单，比对必然通过。原脚本还叠了三重放大：
1. **4 处静默跳过**：清单未附带 / 下载失败 / 清单里查不到该文件 / zip 注释校验失败 → `return 0` 继续安装；
2. **HMAC 可被绕过**：只在**首行**以 `HMAC ` 开头时才校验 → 删掉首行即「无签名」，脚本当作「旧格式包」放行；且服务器**从未配置** `UPDATE_HMAC_KEY`（本轮实测确认，`.env` 与宝塔项目 env 均为 0 命中）；
3. **自动兜底第三方公共镜像**：`ghfast.top` / `gh-proxy.com` / `ghproxy.net` —— 公共代理可同时改写清单与产物。

→ 综合效果：攻击者只要能让服务器走一次第三方镜像（或伪造一个不带 HMAC 首行的包），即可在服务器上执行任意代码。

### 87.2 修复（7 处 fail-closed + 引入真正的信任锚）

| 编号 | 级别 | 问题 | 状态 |
|---|---|---|---|
| R87-1 | Critical | 引入 **Ed25519 分离签名**（`sha256.txt.sig`），公钥内置脚本、私钥仅发布者持有 | ✅ 已修 |
| R87-2 | Critical | 签名缺失 / 验签失败 → 终止更新（原：无此校验） | ✅ 已修 |
| R87-3 | High | 清单未附带 / 下载失败 / 查不到该文件 → 终止更新（原：静默跳过） | ✅ 已修 |
| R87-4 | High | zip 注释双源互证失败（NO/ERR/无输出）→ 终止更新（原：降级为仅比对哈希列表） | ✅ 已修 |
| R87-5 | High | 去掉自动第三方镜像兜底，改为**必须显式**配置 `GH_MIRROR` | ✅ 已修 |
| R87-6 | Medium | HMAC 首行可绕过 → 保留为「有密钥才校验」的**次层**校验，并明确标注完整性已由 Ed25519 保证；无 python3 时硬失败 | ✅ 已修 |
| R87-7 | Medium | 无版本单调性 → 同版本收工；更低版本默认拒绝覆盖（`ALLOW_DOWNGRADE=1` 放行） | ✅ 已修 |
| R87-8 | Medium | `deploy.sh` 是 `update.sh` 的**独立副本**且停在更弱一版（Webhook 路径走的就是它） | ✅ 收敛为薄封装 |

**设计取舍（为什么不做成「必须配密钥才能用」）**：若把公钥做成「部署者自己填」的必填项，等于把一键更新变成「不配就不能用」——用户明确要求「**大家都能用**」。故采用「**内置官方公钥 + 可覆盖**」：clone 即用、默认安全；自建发布者换公钥即可。同时保留两个**显式**逃生舱（`ALLOW_UNSIGNED` / `ALLOW_DOWNGRADE`），默认关闭且会打醒目警告——**默认安全，但不锁死任何人**。

### 87.3 七维复核

- **命令执行**：本轮**关闭**了唯一一条被判定为等价 RCE 的通道（见 87.1）。验签只读文件、不执行内容；内联 python 通过 `argv` 传参，无 shell 拼接。
- **密钥管理**：私钥存发布者本机 `~/.workbuddy/llhhy_release_key`（0600），**不入库、不入包、不上传**；公钥是公开信息，可安全内置。用户可用 `RELEASE_SIGNING_KEY` 换路径。**未新增任何服务端密钥**（`RELEASE_PUBKEY` 有内置默认值，无需配置）。
- **可用性风险（本轮自评）**：① 若发布时忘记签名 → 所有部署者都无法更新（缓解：`package.py` 默认签名、缺少密钥会自动生成，绝不静默不签；`--no-sign` 需显式传入）；② 若服务器访问不了 GitHub 且未配 `GH_MIRROR` → 无法更新（缓解：保留 `GH_MIRROR` 入口并在文档写明；实测本项目服务器可直连）；③ 验签需要 `cryptography`（缓解：它本就在 `requirements.txt`，且找不到时给出明确提示而非静默跳过）。
- **其余五维**（XSS / SQLi / 越权 / CSRF / SSRF）：本轮未触碰后端请求路径（仅 `config.py` 版本号），无变化。
- **供应链**：`deploy.sh` 由独立副本收敛为委派，**审计面减半**——历史上两份校验逻辑各自演化正是本次风险长期未被发现的成因之一。

### 87.4 验证
- **反向实测 20/20 通过**（`.workbuddy/_test_update_chain.py`，用完即删）：**直接从 `update.sh` 里抽出真实的内联验签 python 代码**运行（不是另写一份等价逻辑）；覆盖：官方签名通过、篡改 `sha256.txt` 被拒、冒名密钥签名被拒、签名损坏被拒、空公钥被拒、篡改 zip 内容区被 ②拦截；7 类旧 fail-open 措辞已清除、第三方镜像兜底已除、两个逃生舱与版本单调性在位。
- **125 passed**（119 基线 + 6 条新增 `tests/test_update_chain_contract.py`，静态钉死上述不变量，防 fail-open 回潮）。
- `bash -n update.sh` / `bash -n deploy.sh` 通过；两脚本 `CRLF=0`、孤立 `CR=0`。
- `verify_package_checksums.py` 增加**双源互证 ③**（用 `update.sh` 里读出的**同一个公钥**验签——不另存一份，避免漂移）：本地实测 4 条全 OK。
- **无表结构变更、无新增依赖、无新增必填环境变量、前端产物零变化。**

**R87 结论**：**0 遗留**。审计判定的最高风险项已闭环；残余风险是「发布侧忘记签名会导致全员无法更新」，已通过「默认签名 + 缺密钥自动生成 + `--no-sign` 需显式传入」三重设计压到最低。

---

## R88 · v3.18.7 上线实测发现的验签顺序缺陷（v3.18.8 修复）

**这是一次「上线实测抓到自家 bug」的记录，站点全程未受影响。**

### 88.1 事件

v3.18.7 发布后按「先覆盖脚本、再跑一键更新」的顺序在服务器实跑，**首次即失败**：

```
[00:43:53] 尝试下载: .../v3.18.7/sha256.txt.sig (第 1/2 次)
[00:43:55] ❌ 发布物签名校验失败（拒绝安装）：BAD
```

**关键点：失败发生在「覆盖代码」之前**——R87 新增的 fail-closed 逻辑按设计拦住了安装，站点与数据库零改动（本次实测也顺带证明了 fail-closed 真的会在坏情况下保护站点）。

### 88.2 根因

`$WORK`（`/tmp/llhhy_update`）**在多轮更新之间复用**，而脚本原先只清理解压目录，**不清校验清单**。同时 R87 的 `verify_release_signature` 排在「下载清单」这一步之前，又只做 `[ -f sha256.txt ]` 的存在性检查。于是：

| 文件 | 时间 | 来源 |
|---|---|---|
| `sha256.txt` | **00:28** | 上一轮（v3.18.6）遗留 |
| `sha256.txt.sig` | 00:43 | 本轮（v3.18.7）刚下载 |

用**旧清单**去验**新签名** → 必然 `BAD`。属我方的实现缺陷，不是签名机制本身的问题。

### 88.3 修复与固化

1. `verify_release_signature` 改为**自包含**：先 `rm -f sha256.txt sha256.txt.sig`，再自己下载清单与签名（不再依赖调用方先下载）；同时补 `CHECKSUM_URL` 非空校验。
2. `$WORK` 准备阶段显式清理 `sha256.txt` / `sha256.txt.sig` / 两个 zip。
3. 新增契约测试 `tests/test_update_chain_contract.py::test_stale_workdir_files_are_cleaned`，把「先清旧清单再下载」钉死，防回归。

### 88.4 教训（已写入技能经验）

**跨轮复用的工作目录 + 校验文件 = 隐性状态泄漏。** 任何「读一个可能已存在的文件」的校验逻辑，都必须先明确该文件是**本轮**产生的；否则会得到「用 A 轮的期望值去校验 B 轮的产物」这类必然失败（或更糟——必然通过）的结果。

### 88.5 验证
- **126 passed**（125 + 1 条新增契约测试）。
- 服务器端到端实跑（新脚本 + 站点仍处 v3.18.6）：**签名校验通过 → 哈希校验通过 → zip 注释双源互证通过 → 备份 → 覆盖 → 依赖检查 → 重启，全绿**。这是 v3.18.7 想做但没做完的那次真实演练，现已补上。
- `bash -n update.sh` / `deploy.sh` 通过；CRLF=0。

**R88 结论**：**0 遗留**。缺陷为我方实现顺序问题，已修复并加测试固化；fail-closed 保护在真实坏情况下得到验证。

---

## R89 · SEO 爬虫通道（v3.18.9 · 阶段 1）

**范围**：`myblog/utils/seo_shell.py`（新增）、`myblog/utils/settings.py`（新增 `site_base`/`abs_url`）、`myblog/api/og.py`（重写为三出口）、`myblog/routes.py`、`myblog/diagnostics.py`、`myblog/mail_notify.py`、`myblog/api/posts.py`、`myblog/admin/mcp_services.py`、`myblog/deploy_guide.md`、`myblog/config.py`；新增 `tests/test_seo_shell.py`（16 条）。**线上 nginx 配置同步更新并 reload。**

### 89.1 阶段 0 真机自查（先证伪再动手）

清单指出代码注释与部署文档**互相矛盾**（`routes.py` 声称有 Nginx bot 规则，`deploy_guide.md` 里 0 命中）。实测结论：

| 检查 | 实测 |
| --- | --- |
| `nginx -T \| grep og/post` | **命中**：`location ~ ^/post/` 内 `if ($http_user_agent ~* "(bot\|spider\|crawl\|…)") { rewrite … /api/og/post/$1 last; }` |
| 百度爬虫访问真实文章 | `200` + **`x-robots-tag: noindex,nofollow`** + canonical 指向 `/api/og/post/<slug>` |
| 微信 UA | `200` 但**是 SPA 空壳**（`og:image` 命中 1 次来自 `index.html` 里写死的默认值） |
| 直接敲 API（带/不带 `?seo=1`） | 两者都 `200` + `noindex` |
| QQ 内置浏览器真人 | 侥幸拿到 SPA（UA 里 `QQ/` 未命中该宽泛正则） |
| AhrefsBot | **拿到壳页**（`bot` 宽泛词命中） |

**结论**：通道**早已存在但行为是坏的**——百度能被引导进来后被明确拒绝收录，微信完全进不来，第三方 SEO 蜘蛛反而被放进来。这正是清单 1.1 描述的「接通通道反而杀死收录」。

### 89.2 安全维度

| 维度 | 结论 |
| --- | --- |
| **越权/信息泄露（本轮最重要）** | `og.py` 的 meta 页与 `.png` 分享卡**各自手写** `filter_by(slug, published=True, in_trash=False)` + `if post.is_private`，**两处都漏 `scheduled_at`** → 未到发布时间的文章标题可被 meta 页读到、并被**画进对外可取的 PNG**。现统一 `visible_posts_query().filter_by(slug=slug).first()`，删除手工判断。**与首轮 `api/review.py` / `api/ai.py` 同一出错模式（自建过滤器漏项）——这是本项目第三次栽在「不走真相源」上**，已在测试中锁死三态 × 两入口。 |
| **真人误伤（可用性/生产事故）** | UA 分流天然会误伤：**QQ 内置浏览器里的真人 UA 带 `QQ/9.7.x`**，会被社交预览 UA 表命中。若只看 UA，真人会看到近乎空白的壳页。已加**第二层否决**（`Sec-Fetch-Mode: navigate` / `Sec-Fetch-Date: document` / `Accept: text/html` / 站内 Referer），并选择**宁可错杀爬虫也不误伤真人**的不对称策略（爬虫少收一篇 vs 真人看到空白页）。8 条判定 + 4 种身份自检接口覆盖。 |
| **Host 注入（首轮 2.9 遗留）** | 修复前 `_site_base()` 回退 `request.url_root`、`og.py` 直接用 `request.url` → `Host: evil.example.com` 可诱导 canonical/og:url 指向外部域名。现已全部收敛到 `site_base()`（DB → env → 空串），**删除 `request.url_root`/`request.host` 回退**，并加测试断言 `evil.example.com` 不出现在响应体。 |
| **限流绕过** | 通道**豁免正规搜索引擎**（否则把 Google/Baidu 正常抓取 429 掉 = 自废收录），其余走 `rate_limit(client_key("og_shell"), 120/60s)`。UA 可伪造，故豁免仅影响限流、**不影响可见性**（可见性恒走真相源）。 |
| **XSS** | 壳页所有字段经 `html.escape`；正文复用既有 `render_post_html`（bleach 白名单管线，**不新写渲染逻辑**从而不引入白名单差异）；JSON-LD 显式转义 `</` 防 `</script>` 提前闭合。测试覆盖 `<script>alert(1)</script>` 标题被转义。 |
| **SSRF** | 通道本身不出网；`_og_default_response` 只读本地文件。新增的 `/api/seo/shell-check` **只请求 `site_base()` 推导出的本站地址**（不接收任意 URL 参数），且需登录后台。 |
| **缓存串味** | 同 URL 三种结果，已加 `Vary: User-Agent, Sec-Fetch-Mode, Accept, Referer`（缺失会被 CDN 把爬虫/真人结果互相串通）。 |
| **CSRF / 鉴权** | 本轮新增接口均为只读 GET；无新增写面。 |
| **表结构 / 依赖 / 环境变量** | **零变更**。 |

### 89.3 验证
- **142 passed**（126 + 16 条新增 `tests/test_seo_shell.py`）；`ruff --select F821,E9 myblog/ tests/` **All checks passed**。
- **变异测试**（证明断言真的能抓回归，不是"看起来对"）：
  - ① 把抓取方出口的 `index,follow` 回退成恒 `noindex` → **2 条红**（`test_baidu_gets_indexable_shell`、`test_wechat_crawler_gets_shell`）；
  - ② 删掉第二层真人否决 → **2 条红**（微信真人、QQ 真人变 `200`）。
- 线上 nginx：`nginx -t` 通过后 reload；原配置备份 `/root/html_www.llhhy.cn.conf.bak-v3189`。
- 文档同步：`CHANGELOG.md`、`README.md`、`myblog/README.md`、`myblog/deploy_guide.md`（新增「第 4b 步：SEO 爬虫通道」，含配置原文与验证命令）、`routes.py` 失真注释修正。

**R89 结论**：**0 遗留**。本轮修复的是「通道存在但行为相反」的隐性故障，且顺带关闭了首轮审计 2.9 的 Host 注入遗留项。**注意**：`scheduled_at` 漏判暴露了「可见性必须走 `visible_posts_query()`」这条纪律在本项目已被违反三次，建议后续新增任何公开只读接口时把「是否调用真相源」列为评审必查项。

---

## R90 · 后台「🔍 收录」控制台（v3.19.0 · 阶段 2）

**范围**：`myblog/seo_push.py`（新增，推送引擎）、`myblog/admin/seo.py`（新增，收录页蓝图）、`myblog/templates/admin/seo.html`（新增）、`myblog/models.py`（新增 `SeoSubmission`）、`myblog/app.py`（`_migrate_new_tables_v3` 纳入新表）、`myblog/admin/__init__.py`、`myblog/templates/admin/base.html`（侧栏入口）、`myblog/og_image.py`（`.ttc` 字重匹配修复 + 三处降级日志）、`myblog/static/fonts/`（新字体 + `FONTS.md`）、`myblog/config.py`；新增 `tests/test_seo_push.py`（29 条）。

### 90.1 本轮唯一的「新增出网面」及其处置

本版是**近几版里唯一新增对外网络调用的版本**（此前项目没有统一出网守卫，各调用点各自 `urlopen` + 固定 host）。因此把出网约束做成了模块级硬约束，而不是散在各处的约定：

| 维度 | 结论 |
| --- | --- |
| **出站目标白名单** | `_is_allowed_url()` **精确比对 host**（不做后缀匹配）。`http` 仅放行 host **等于** `data.zz.baidu.com`（百度官方地址就是 http，无 https——这是本项目唯一必须允许 http 的出站目标）。 |
| **绕过手法已覆盖** | `http://data.zz.baidu.com.evil.com/`（后缀拼接）、`http://data.zz.baidu.com@evil.com/`（userinfo 混淆）、`http://evil.com/http://data.zz.baidu.com`（路径伪装）、`http://api.bing.com/`（非百度走 http）、`ftp://` —— **全部拒绝，且拒绝时返回 `blocked-host` 而非放行**。测试逐条钉死；另有测试断言「白名单外目标不得调用 `urlopen`」。 |
| **SSRF** | 推送目标**恒为常量**（`BAIDU_ENDPOINT` / `INDEXNOW_ENDPOINT`），**不接受任何用户输入作为 URL**；被推送的正文 URL 恒由 `site_base() + /post/<slug>` 拼出。 |
| **Host 注入（延续 2.9）** | 推送 URL 不读 `request.host`。测试 `test_push_urls_use_site_base_not_request_host` 直接断言生成结果等于 `site_base()` 拼出的值、且不含伪造型 Host。 |
| **凭据泄露（最重要）** | ① 存储走 `encrypt_secret()`（**不照抄 `mail_password` 的明文落库反例**），测试断言 `bkenc$` 前缀且能解回原文；② 页面只回显掩码，测试断言明文不出现在 HTML；③ **响应清洗会抹掉 token**——百度可能把带 token 的请求 URL 回显在错误里，`_clean()` 做 `.replace(token, "***")`，测试注入含 token 的回显并断言已抹除；④ 审计日志只记「改了哪个键」，不记值。 |
| **URL 注入（IndexNow key）** | key 会被拼进 `keyLocation`（`https://<host>/<key>.txt`）。若不做校验，可塞 `/`、`..`、空格把 `keyLocation` 指向站内任意路径。已加规范校验（8–128 位、仅 `[A-Za-z0-9-]`），非法值**拒绝保存**并提示。测试覆盖 5 种非法值。 |
| **鉴权 / CSRF** | 6 条路由（`/admin/seo` + 5 子接口）**全部 `@super_required`**（普通管理员 403，有测试）；全部写操作带 CSRF token（模板 `csrf_input()` + 全局 `_csrf_protect` 兜底），推送与凭据保存缺 token 均 403（各有测试）。 |
| **阻塞请求（首轮 4.6 同类）** | 推送是阻塞网络调用，**绝不跑在请求线程里**。入口只「写 pending → 起 daemon 线程 → 立即返回」。测试把最底层出网口 `_http_post` 替换成「命中即 `AssertionError`」，验证请求线程内不被命中；另有测试断言确实启动了 **daemon** 线程。 |
| **配额滥用** | 单次上限 500 条（百度 2000 / IndexNow 10000，取保守值）；`timeout=10s`；失败**不自动重试**（避免无效请求吃掉配额），由页面手动重推；已成功的不重复推送。 |
| **不可见文章** | 单篇推送先过 `visible_posts_query()`，草稿/隐私/回收站/未到点定时**一律拒绝**并写 `seo_push_reject` 审计；批量候选同样走真相源。理由：给搜索引擎送 404 浪费配额且拉低站点质量评分。测试覆盖四态 + 审计留痕。 |
| **XSS** | 页面渲染的 `response` 一律经 Jinja 自动转义；JS 侧只写入 `textContent` / 拼接固定标签，不 `innerHTML` 注入后端文本。 |
| **表结构 / 依赖 / 环境变量** | 新增 1 张表 `seo_submission`（**明确记录由 `create_all` 自愈创建、不走 Alembic**，理由见模型 docstring）；**零新增依赖**（标准库 `urllib`）、**零新增环境变量**。 |

### 90.2 顺带修复：`og_image.py` 的 `.ttc` 字重匹配缺陷 + 降级不再静默

**（a）`.ttc` 不参与字重匹配**：`_cjk_candidates()` 原先只对 `.ttf`/`.otf` 做 `*Bold*`/`*Regular*` 命名匹配，**`.ttc` 不参与** → 放进 `static/fonts/` 的 `*-Bold.ttc` / `*-Regular.ttc` **永远不会被优先选中**，会静默回落到「任意一个字体文件」。已补 `.ttc`。

**（b）降级路径不再静默（本轮关闭 90.4 待办①）**：`og_image.py` 原有三处降级**全无日志**——① Pillow 不可用（模块导入期）、② `render_og_image()` 找不到中文字体、③ `og_png_bytes()` 渲染抛异常。这正是「`.png` 分享卡恒返回兜底图」能潜伏**整整一个版本周期**而无人察觉的直接原因：调用方只看到「返回 None」，日志里查不到任何线索。

现三处均加 `logger.warning`：① 记 Pillow 不可用；② 记**字体目录路径 + `_PIL_OK` 状态**（运维据此可直接判断是「包里没字体」还是「字体路径不对」）；③ 带 `exc_info=True` 并记 slug。

**安全属性**：改动**只加日志、不改任何行为**（无新依赖、无新出网、无新输入路径），全量测试 **171 passed 保持不变**。日志内容**不含 token**（该路径根本不接触凭据），不引入日志注入面（`slug` 经 `%s` 参数化，非字符串拼插）。

这一条与 R89 的字体静默降级是同一类问题：**降级不报错，所以没人发现**。

### 90.3 验证
- **171 passed**（142 基线 + 29 条新增 `tests/test_seo_push.py`）；`ruff --select F821,E9 myblog/` **All checks passed**。
- 全量测试前后 `myblog/data/blog.db` 的 **sha256 与 mtime 双查零变化**（`9e1f92a4…cf6b9` / `1789310851.2362475`）。
- 文档同步：`CHANGELOG.md`（v3.19.0）、`myblog/README.md`、`myblog/static/fonts/FONTS.md`（新增）、`myblog/config.py`（版本号）。
- **未 commit / push / tag / 未建 Release**（等显式发版口令）。本轮改了 `deploy_guide.md`（v3.18.9 期间）但**未动** `update.sh`/`deploy.sh` → 不需要 `deploy_scripts_*.zip`。

**R90 结论**：**0 遗留**。本轮新增的出网面按「常量目标 + 精确 host 白名单 + 用户输入不参与 URL + 凭据加密 + 响应抹密钥」五条收口，并有 29 条测试覆盖。`og_image` 静默降级已在 90.2(b) 关闭。

> **待办建议（非本版缺陷）**：
> 1. `migrations/versions/*` 的 Alembic 基线仍是假的 `db.create_all()`，若日后要真正启用迁移体系，需为 `seo_submission`（及 `game`）补 baseline 迁移。
> 2. **发版安全快检时发现的既有项（非本轮引入，如实记录）**：`myblog/api/og.py::qr_image`（`GET /api/qr`，v3.16.0 引入）在 `site_url` **未配置**时，会用 `request.host_url`（第 145 行）与 `request.host`（第 140 行）拼装对外二维码内容，即「让请求方提供 Host 决定我们对外声明什么」。**当前生产已配置 `site_url`（`site_base()` 有值）→ 该分支不生效，实测无风险**；但它与首轮审计 2.9 / R89 确立的「对外地址只走 `site_base()`」原则不一致。该接口另有 host 白名单（`allowed` 集合，仅站内 host 或 `site_url` host 可通过）与 30 次/60s 限流，影响面限于「未配置 `site_url` 的部署」。**处置建议**：下版本把该分支改为「`site_url` 为空时返回 400 并提示先配置站点地址」，与 v3.18.9 对 `_abs()` 的处理保持一致。**本版不改**（属既有行为，改它需回归二维码功能，不适合夹在收录控制台版本里）。
> 3. `myblog/utils/seo_shell.py::_is_same_site_referer`（第 111-118 行）在 `site_base()` 为空时用 `request.host` 作比对基准 — 这是**判据用途而非对外声明用途**（只用于回答「这个 Referer 是不是自己家」），代码注释已说明，**不构成 Host 注入**，无需修改。

---

## R91 · 第三轮复审修复（v3.19.1 · 302 环 / 出站 SSRF / 自检放大面）

**范围**：`myblog/utils/seo_shell.py`、`myblog/api/og.py`、`myblog/seo_push.py`、`myblog/admin/seo.py`、`myblog/admin/post_trash.py`、`myblog/templates/admin/seo.html`、`myblog/deploy_guide.md`、`myblog/config.py`；测试 `tests/test_seo_shell.py`、`tests/test_seo_push.py`。

**来源**：第三轮第三方复审报告（3 High / 5 Medium / 4 Low）。**复验纪律：逐条回代码与线上实测，不采信报告自述**——11 条中 10 条成立，1 条部分不成立（见 91.5）。

### 91.1 `[High]` 线上 302 环 —— 连接通通道反而杀死收录（**已上线事故**）

| 维度 | 结论 |
| --- | --- |
| **症状** | `/post/<slug>` 对「带 `Accept: text/html` 的搜索引擎」与「QQ/微信内置浏览器真人」**无限 302**。线上实测：Googlebot / Baiduspider / QQ 真人**三者 12 次重定向后仍是 302**（`curl --max-redirs 12` 退出码 47）。后果：**搜索引擎抓不到任何正文（收录归零）**；真人在内置浏览器里看到 `ERR_TOO_MANY_REDIRECTS`。 |
| **根因** | 否决层作用域过宽 + 出口动作与 nginx 粗筛互相激励。nginx 的 `map` **只按 UA** 粗筛（看不见请求头），后端却因 `Accept: text/html` 否决并 **302** 回 `/post/<slug>` → nginx 按同一个 UA 再次 rewrite → 环。 |
| **为什么自检没照出来** | v3.19.0 的探针给搜索引擎**只送 UA、不送 `Accept`** → 线上环在自检里**全绿**（假绿一整轮）。 |
| **修复①：作用域按桶拆分** | `Sec-Fetch-Mode`/`Sec-Fetch-Dest`（浏览器专有，搜索引擎不送）→ 两类桶都否决；`Accept: text/html`（**搜索引擎正常也会送**）→ **只对社交桶否决**。新增 `has_fetch_metadata_signal()` / `has_html_accept()` / `HUMAN_VETO_REASONS`；`is_human_navigation()` 保留为并集并**在 docstring 明确禁止当单一闸门用**。 |
| **修复②：经通道绝不 3xx** | `og_post()` 出口 3 拆为 3a（无 `?seo=1` → 302，安全：只有一跳）与 3b（有 `?seo=1` → **按原因分流且绝不 3xx**）：真人类 → **200 + `noindex,nofollow` 可读页**（人能读正文、索引不受污染）；`tool-bot`/`not-crawler` → **404 + noindex 不给正文**（保住「不给批量抓取入口」的原意图）。 |
| **顺带修** | 302 响应过去**未带 `Vary`** → CDN 可能把「给爬虫的 302」缓存给真人。测试 `test_shell_and_redirect_carry_vary` 抓出后已补。 |
| **回归钉死** | `test_channel_never_returns_3xx`（8 种 UA 矩阵断言「经通道禁 3xx，只允许 200/404」）＋ `test_search_engine_with_accept_html_still_gets_indexable_shell`（Googlebot/Baiduspider 带 `Accept` 必须拿 `index,follow`）。**变异测试**：回退修复 → 13 条变红（含这两条）→ 证明非空转。 |

### 91.2 `[High]` 出站跟随重定向 → 半盲 SSRF + 可伪造「推送成功」

**代码事实**：`_http_post()` 的 `_is_allowed_url()` 只在**发起前**校验一次，随后用**默认 opener**（自动跟随 3xx），且 urllib 会把 POST **降级为 GET**。于是「白名单 host 返回 302」= **任意 host 的一次 GET**，响应体还会被当作推送结果入库并上屏（内容回显）。

**本地实证**（已写成回归测试 `test_redirect_is_not_followed`）：起两个本地 HTTP 服务，第一个返回 `302 → 第二个`；v3.19.0 行为 = 第二个**收到 GET**，修复后 = **从未收到请求**。

| 修法 | 说明 |
| --- | --- |
| 禁跟随重定向 | 自定义 `_NoRedirect(HTTPRedirectHandler)` 抛 `HTTPError`，3xx 原样返回给调用方落 `fail`（也便于排查链路劫持/端点迁移）。 |
| 成功判定加严 | 百度要求「可解析为 JSON」**且** `Content-Type` 含 `json`。原先 `HTTP 200` 即判 ok —— 一个伪造 200（或被劫持链路上的 HTML 错误页）就能让控制台显示「成功」并写入虚假配额。 |
| 响应字段白名单 | 新增 `_extract_response()`，只保留 `success`/`remaining`/`error`/`message` 等协议已知字段，**不再把上游 body 原文入库/上屏**（消除内容回显面）。 |
| 脱敏先于截断 | 新增 `_redact()`（含 24/16/8 字符前缀片段），`_clean()` 内部顺序固定为「先脱敏 → 再压平 → 最后截断」。原 `_clean(text).replace(token,"***")` 是**先截断后替换**：token 落在 500 字符之后即漏抹（IndexNow key 最长 128 位，泄露面更大）。 |

### 91.3 `[High→Medium]` 自检端点：自请求放大面 + 假绿

| 项 | v3.19.0 | v3.19.1 |
| --- | --- | --- |
| 出网 | `urllib` 回打 `site_base()` 公网地址，**串行 4 次**（从 Flask worker 内部请求自己） | `test_request_context()` 注入头后**直调 `og_post()`**，**零出网** |
| 鉴权 | **匿名可调** | `@super_required`（匿名 403） |
| 限流 | 无 | `rate_limit(client_key("seo_shell_check"), 30/60s)` |
| 探针头 | 搜索引擎**只送 UA** → 环在自检里假绿 | 送**真实头**（`Accept: text/html`）→ 环会立刻显红 |
| 预期分档 | 2 档（shell / spa） | **3 档**（`shell` / `noindex` / `404`），且**三档都不允许 3xx**，`would_loop` 字段供页面报警 |

> **关于报告 2.1 的严重度描述**：报告称「生产是 sync worker、**无 `gunicorn_conf.py`**，两个并发点击即可让全站无 worker 可用」。**实测不成立**：`gunicorn_conf.py` 存在（`workers=4, threads=2, worker_class='sync'`），gunicorn 22.0.0 会把 `threads>1` **自动升级为 gthread**（启动日志 `Using worker: gthread`，每 worker 4 线程）→ 实际 **8 个并发槽**，且同一 worker 的空闲线程可服务自请求，**无报告描述的硬死锁**。严重度下调为「放大型可用性风险」。**但「匿名可调 / 无 rate_limit / 每次 4 个自请求」三条代码事实成立**，故仍按零出网改造。

### 91.4 `[Medium]` 后台线程静默失败 / 审计缺 IP / 配额滥用 / 孤儿行

| 项 | 修法 |
| --- | --- |
| **双层 `except Exception: pass`** | `_runner` 外层改为 `logger.exception(...)` **并把这批落 `fail`**。原先 `submit_posts` 一旦抛出，整批记录**永久停在「排队中」**（页面轮询永远等不到结果，日志无痕）。 |
| **审计无 IP** | 改用统一的 `admin._helpers.log_audit()`（v3.19.0 手搓 `AuditLog(..., ip="")`，`get_client_ip` 导入后从未调用 → 与 v3.18.5 收口的口径矛盾）。IP 在**请求线程**捕获后传入后台线程（后台线程无请求上下文，取不到 IP）。 |
| **`_spawn` 返回值被丢弃** | 起线程失败 → 落 `fail` + `enqueue` 返回 0 + 页面不再假报「已入队」。 |
| **无限流 / 无在飞去重** | `rate_limit(client_key("seo_push"), limit=3, window=300)`；同引擎存在 `pending` 时直接拒绝（**百度当日配额用完不可逆**）。 |
| **`keyLocation` 未校验** | 新增 `_keylocation()`：校验 `site_url` 的 scheme/hostname，拒绝 query/fragment/userinfo；`_valid_indexnow_key()` 出站前再校验 key 格式（纵深防御，管理页保存时已校验一次）。 |
| **硬删除留孤儿行** | `admin/post_trash.py::purge_post` 显式删 `seo_submission` 同 `post_id` 行 —— SQLite 未开 `PRAGMA foreign_keys=ON`（`app.py` 只设 WAL/busy_timeout/synchronous），FK **不级联**。 |
| **`og:description` 漏 Markdown** | 新增 `_plain_preview()`（图片整段丢、链接留文字、去反引号/行首标记/标签）。 |
| **模板 `innerHTML`** | `templates/admin/seo.html` 改为 DOM + `textContent` 构造（当前来源全为常量、不可利用，属**纵深防御**；同时修正了与「只写 textContent」的陈述不符）。 |
| **nginx map 漏 token** | 补入 `ShenmaSpider`/`ToutiaoSpider`/`QwantBot`/`SeznamBot`/`Embedly`/`Pinterest`/`Vkshare`/`W3C_Validator`/`Outbrain`/`Nuzzel`/`BitlyBot`/`Line-Poker`/`Facebot`；`deploy_guide.md` 写明**必须保持「nginx ⊆ 后端」**这一环安全不变量（nginx 放行了后端不认识的 UA → 后端判 `not-crawler` 返回 404，**不会成环**，但该抓取方拿不到内容）。 |
| **死代码** | 删 `LOG_KEEP`、`submit_posts(actor=)` 未使用参数。 |

### 91.5 复验结论表（**逐条回代码/线上核对**）

| 报告条目 | 复验 |
| --- | --- |
| 2.1 自检端点 DoS | **部分成立**——「匿名/无限流/4 自请求」成立；「sync worker、无 `gunicorn_conf.py`、两个点击打挂」**不成立**（实为 gthread 4×2=8 槽） |
| 2.2 重定向 SSRF + 伪造成功 | **成立**（本地双服务实证） |
| 2.3(a) 302 环 | **成立且已是线上事故**（线上实测 3 类身份 12 次重定向仍 302） |
| 2.3(b) 自检公式漂移 | **成立**（缺 `is_internal_referer` / `Sec-Fetch-Dest`，`seo_shell_ua` 从未调用） |
| 2.4 静默失败 / 审计无 IP / 丢弃返回值 | **成立** |
| 2.5 无限流 / 无去重 | **成立** |
| 2.6 先截断后脱敏 | **成立** |
| 2.7 三处测试问题 | **成立**（`:594` 的 `or` 断言近乎空转；`test_shell_check_endpoint_untouched` 断言 `200 or 400` 且不 stub `urlopen`；线程内真路径零覆盖） |
| 2.8 孤儿行 | **成立** |
| 2.9 五个 Low | 逐条成立（`og:description` / `keyLocation` / 死代码 ×2 / `innerHTML` / nginx map 不一致） |
| §3 首审 4.x（性能 / 前端 / 可观测性 / CI） | **确认零改动**，转入 `ROADMAP.md` 登记，不夹进本补丁版 |

### 91.6 验证

- **185 passed**（176 基线 + 9 条新增）；`ruff --select F821,E9 myblog/ tests/` **All checks passed**。
- **变异测试通过**：回退修复 → 13 条红（含两条新回归）→ 新测试非空转。
- **顺序无关**：随机顺序同样 185 passed；新增 autouse fixture 清空 `utils._RATE`（限流状态原先会跨用例串味，导致「单独跑绿、连跑红」）。
- **开发库**：`PRAGMA integrity_check` = **ok**；0 篇文章 / 1 用户（与修复前一致）。
- ⚠️ **如实记录一处自家操作瑕疵**：开发库 `blog.db` 的 sha256 有变化 —— 原因是**我上一轮为渲染样例图，把 `DATABASE_URL` 显式指向了开发库并调用 `create_app()`**，触发 `_migrate_new_tables_v3()` 在该库上建了 `seo_submission` 表。**数据无损**（行数与完整性均正常），但违反了「测试/诊断不得写开发库」的精神。**教训**：任何调 `create_app()` 的诊断脚本，必须先把 `DATABASE_URL` 指向**副本或临时目录**。

**R91 结论**：**0 遗留**（本版范围内）。核心是两条：**经通道绝不 3xx**（断环）+ **出站禁跟随重定向**（断 SSRF）；两条都由回归测试 + 变异测试双重钉死。

> **待办（非本版）**：
> 1. R90 待办②（`/api/qr` 未配 `site_url` 时用 `request.host`）仍开放 —— **本版未动**（同前述理由：需回归二维码功能，不宜夹进补丁版）。
> 2. 首审报告第 3–7 章（`post`/`comment` 索引、`inject_globals` 每渲染 8 查询、列表 3N+1、`notify.py` 同步外网、前端 a11y/对比度/`tokens.css` 双份、CI 加 lint/覆盖率/CVE/CodeQL）—— 已登记 `ROADMAP.md`。
> 3. ✅ **已关闭**：报告 2.9 提到的「**部署文档未记录 gthread**」。实测线上已因 `threads=2` 自动成为 gthread；本版在 `deploy_guide.md` 的 v3.19.1 升级要点里**明确记录了该事实**（避免后人再照报告误判为「未修」）。

### 91.7 附注：上线后由**生产数据**发现的字段名缺陷（→ v3.19.2）

**本项非安全缺陷**，但方法论值得记一笔，且报告未覆盖。

- **发现方式**：v3.19.1 上线后核对 `seo_submission` 的真实数据（而非自造 mock）→ baidu 引擎的原始响应是 `{"remain":8,"success":1}`。
- **缺陷**：`push_baidu()` 读的是 `data.get("remaining")` → 对真实响应**恒为 None** → 「剩余配额」写不进 `Setting.seo_baidu_quota`（实测该键为空）→ 收录页配额栏一直空白；`remaining == 0 → quota` 判定永不触发。
- **未受影响（重要）**：`quota` 档仍被 `data["error"]` 里 `"over quota"` 分支兜住 → **不是状态误判，只是信息缺失**。生产数据同时印证推送链路正常（7 篇全 `ok`，真实 `success` 1~5）。
- **根因**：`push_baidu` docstring 里那句**凭想象编的示例** `{"success":2,"remaining":998}` —— 实现照着它写了字段名。→ **一般规律：上游协议字段名必须用真实响应校准；发现写错要连 docstring 的错误示例一起改掉**，否则后人照它再写一遍。
- **修复（v3.19.2）**：`data.get("remain", data.get("remaining"))` 两个名字都认；`_RESP_KEYS` 加入 `remain`（否则白名单会把配额一起丢掉）；docstring 示例更正为 `{"remain":998,"success":2}`；加强回归测试并做变异验证（回退字段名 → 断言变红）。
- **与 R91 的关系**：R91 修的 `_RESP_KEYS` 白名单**本身是正确的**（它成功挡住了原始 body 回显）——正因为它生效，`remain` 才需要显式加入白名单。两条修复互补，不冲突。




---

## R92 · 待办清单批次（v3.20.0 · 工程化门禁 / 异步化 / 可观测性 / 前端 a11y）

**范围**：`pyproject.toml`、`tools/lint_debt.py`、`tools/lint_debt_baseline.json`、`.github/workflows/ci.yml`、`.github/dependabot.yml`、`gunicorn_conf.py`、`myblog/notify.py`、`myblog/mail_notify.py`、`myblog/api/system.py`（`/health`）、`myblog/app.py`、`vue-frontend/src/{App.vue,lib/toast.js,views/DocsView.vue,views/PostView.vue,store.js}`、`tests/test_lint_debt.py`、`tests/test_notify_health.py`。

**来源**：`ROADMAP.md` §5.8 / §5.9（第一、三轮第三方审计的延后批次）。**本轮的特点是先实测再动手**，因此有 3 项结论与审计描述不同（§92.4），另有 1 项**我自己的假设被实验推翻**（§92.3），已从代码注释里清掉，不留错误结论。

### 92.1 供应链与门禁（原审计：无 lint / 无 ruff 配置 / 无 dependabot）

- **`pyproject.toml`（新增）**：只承载 ruff 配置，**刻意不写 `[project]`** —— 避免引入第二处版本号（该仓库已有「版本号多处复制」的已知问题）。`select` 的选型原则是「**高信号且加入当天全绿**」，因为一上线就红的门禁很快会被绕过或关掉。
- **阻断集与处置**：`E9/F63/F7/F82`（0 条）｜`B`（8 条，全修：4×B904 异常链 + 4×B007）｜`F841`（3 条，**抓到的全是真死代码**）｜`S105`（3 条**全为误报** —— 是 Setting/session **键名**，已就地 `# noqa` 并写明理由）｜`C4`/`RET`/`A`（9 条，已修；`RET503` 2 处与 `C408` 1 处为误报/可读性取舍，已 noqa 说明）。
- **`DTZ`（13 条）明确不修** —— 项目约定是 **naive UTC 存储**（`myblog/_time.py` docstring 明写「数据库 DateTime 列均为 naive 存储，与旧行为逐字节一致」）。改成 tz-aware = 改存储语义 + 数据迁移。**这是设计决定，不是缺陷**；把它当阻断项修属于「修 lint 把系统修坏」。
- **`tools/lint_debt.py`（新增）—— 债务棘轮**：历史债（`BLE001` 272 / `F401` 171 / `S110` 94 / `ARG` 73 / `T20` 68 / `SIM` 40）一次性修完风险高（91 处 `except: pass` 涉及「记日志还是静默」的语义决策），但放着会继续长。棘轮把当前数量固化为基线，**只允许减少、不允许增加**，从而在不清算历史债的前提下止住新增。
  刻意**不收** `I`/`UP`/`PTH`：属个人风格偏好，收进去只会制造无意义的历史债务。
- **CI `lint` job**：`ruff check .`（阻断）+ 债务棘轮 + `check_i18n.py` + **发布公钥一致性**（钉住 `update.sh` 的 `BUILTIN_RELEASE_PUBKEY` —— 它是更新链 fail-closed 的根锚点，误改会让所有老版本拒装新包或让验签形同虚设）。
- **`npm install` → `npm ci`**：前者按 range 重解依赖且可能改写 lockfile，会让「CI 绿」与「本机装出的那份」脱钩。
- **`dependabot.yml`（新增）**：三类生态，小版本/补丁**分组**成单 PR，**明确不自动合并** —— `requirements.txt` 的上限是带理由刻意选的（`cryptography>=50,<51` 消化过 CVE），且该文件承载「最低 Python 版本由 bleach 决定为 >=3.10」这条需人工复核的约束。

> ⚠️ **诚实边界**：完整的 `verify_package_checksums.py` **无法在 CI 运行** —— 它需要已签名的发布物，而签名私钥只存在于发布者本机且绝不入库。CI 只能守住「公钥值」这个不变量；包级三链校验仍留在本机发版流程。

### 92.2 配置入库与探活

- **`gunicorn_conf.py` 入库**（原先只存在于线上、由宝塔生成，删站即丢）。**不在部署包里**（`package.py` 只收 `myblog/`），`update.sh` 不覆盖它。
  把三个此前只在线上、且**被第三方报告误判过**的事实写进 `deploy_guide.md`：① 写 `sync` 但 gunicorn 22 在 `threads>1` 时自动升级 `gthread`；② 实际并发槽 = 4×2 = **8** 而非 4（报告据此误判为「2~3 个 sync worker」，见 R91）；③ 4 个 worker 是刻意的（2 核 + SQLite 写锁竞争）。
- **`GET /api/health`（新增）**：无需登录、单次 `SELECT 1`、**不出网**、依赖不可用返回 **503**。响应字段严格 `{ok, version, db}` 三项，**不回显配置/路径/密钥/异常细节**（测试逐条断言 `SECRET`/`password`/`token`/`/www/`/`sqlite` 不出现）。
  此前项目**零探活端点**，`diagnostics.py` 是人工触发的拉取式体检 → 「站点挂了」只能靠人先发现。

### 92.3 通知异步化（含一处**我方假设被实测推翻**）

`notify.py` 改为后台线程（原为同步，每渠道 `timeout=6`，两渠道齐配最坏阻塞 **12s**，而 5 个调用点全在请求路径上）。

**必须更正的判断**（我原本写在注释里的因果是错的，已全部改掉）：

| 我的原假设 | 实测结果 | 结论 |
| --- | --- | --- |
| 传 ORM 对象进后台线程会抛 `DetachedInstanceError`，因为 `commit()` 让属性过期、线程里是新 session | **证伪**。实测（Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.52）：detached 的 `Post` 上**标量属性照常可读**（值仍在实例 `__dict__`） | `mail_notify` 当年那样传对象，**对它自己的用法是能工作的** —— 不存在「订阅者静默收不到信」的历史缺陷 |
| —— | detached 实例上访问**从未加载的懒加载关系**（如 `post.author`）**确实抛** `DetachedInstanceError` | **这才是真实风险边界**，且窄：只有「后台线程里访问懒加载关系」才会踩到 |

**处置**：`notify.py` 用「调用线程内先取快照」（线程内只碰字符串）；`mail_notify` 改为「传 id、线程内重查」（拿到属于新 session 的活对象）。
**并明确记录：这两处是「纵深防御」，不是「修 bug」** —— 区别重要，因为它决定了是否值得为一个已上线版本紧急发补丁。判断依据就是上表两条实测。
同时把两模块的 `print(...)` 与静默 `except: pass` 换成 `logger.warning(..., exc_info=True)`。

### 92.4 前端 a11y（含 3 处与审计描述不同的结论）

先实测发现**改动面比审计小得多**（`vue-frontend/src` 仅 38 个文件）。逐项：

| 项 | 复验结论 |
| --- | --- |
| 零 `aria-live` | **真缺陷，但根因不是「忘了写」**：`lib/toast.js` 给**每条** toast 现建现挂 `role="status"`，而 **live region 必须先在 DOM 中存在**之后插入的内容才会被朗读 → 实际不会被播报。已改为**宿主常驻** `role="status" aria-live="polite" aria-atomic="false"`。 |
| 无 skip-link | **真缺陷**，已加（含 `<main tabindex="-1">`）+ 同步 zh/en i18n key。 |
| 灯箱无 `role="dialog"` | **真缺陷**（容器对读屏是「哑」的），已补 `role="dialog" aria-modal="true" aria-label`。**未做完整焦点陷阱**，已在注释里记为已知缺口 —— 不假装达到 modal 的 WCAG 要求。 |
| `IntersectionObserver` 泄漏 | **只有 `DocsView.vue` 是真泄漏**：它是**路由组件**，每次进入 `/docs` 新建 observer 且从不 `disconnect` → 持续累积。已加 `onBeforeUnmount` + `disconnect`。`main.js` 的 `v-reveal` 是**一次性** observer（命中即 `disconnect`），**无需改**（审计把它一并列出属扩大描述）。 |
| scroll/resize 未清理 | `App.vue` 是**根组件、SPA 内不卸载** → **理论问题、无实际影响**。既然该处已有 `onBeforeUnmount`，顺手收口并在注释说明它并非真实泄漏。 |
| `v-html` 未统一 `sanitizeHtml` | **未复现**：仓库存在 `lib/sanitize.js`，抽查 `App.vue` 的 `v-html` 均已经过 `sanitizeHtml()`。本轮**未做全量核对**，列为下次复核项（见待办）。 |

### 92.5 评估后**明确不做**的两项（附实测依据）

| 审计项 | 实测 | 结论 |
| --- | --- | --- |
| `post`/`comment` 主表零索引 | 生产真实行数 `post` = **7**、`comment` = **1**；**有量**的表其实都已建索引（`visit_log` 2593 / `ip_region` 854 / `read_log` 85 / `setting` 77）；`post.slug` 也已有 unique 自动索引 | **不按原样做**。7 行加索引只有写入成本且要改表结构 → **改为设触发条件**（`post > 500` 或 `comment > 5000` 再加）。唯一「有量且无索引」者是 `audit_log`（218 行），亦未到需要索引的量级。 |
| `inject_globals` 每次渲染 8 条查询 | SSR 退役后全项目只剩 **2 个模板**（`login`/`register`）extend `base.html`，其余 **45 处渲染全是 `admin/*`** → 这 8 条**只发生在后台页与登录页**；公开文章页由 nginx 直出 SPA + JSON API，不经过它 | **不加缓存**。项目有 **20 处**直接写 `Setting`（无单一收口点），做缓存须引入 TTL + 失效钩子，代价是「改完主题后一段时间显示旧值」，换来的只是省掉后台点击时的 8 条小表查询 —— **收益小于复杂度**。理由已写进 `inject_globals` docstring。 |

顺带删掉一处真死代码：`inject_globals` 注入的 `now_year` 未被任何模板使用（同时消掉一处 `DTZ005`）。

### 92.6 验证

- 全量 **221 passed**（185 基线 + 36 新增：`test_stats_depth.py` 5 条 + `test_seo_push.py` 4 条 + `test_lint_debt.py` 6 条 + `test_notify_health.py` 10 条 + `test_qr.py` 7 条 + `test_atom_feed.py` 4 条）；`ruff check .` 全绿；棘轮通过（**648 = 648，无新增**）；`check_i18n.py` 通过；`vite build` 通过。
- 新增测试均做**变异验证**：① 棘轮前缀匹配（`T20` 这类「以数字结尾的族前缀」—— 该函数**连错两次且两次都是静默失效**，界面照常打印、退出码照常 0，只是整族漏计）；② `mail_notify` 回退成「传对象」→ 断言变红；③ `maybe_auto_push` 回退「默认关闭 / 拒绝不可见」→ 断言变红。
- 开发库 `blog.db` sha256 + mtime 双查零变化（本轮零表结构变更）。

### 92.7 待办（本轮新增）

1. **`v-html` + `sanitizeHtml` 全量核对**（92.4 只抽查了 `App.vue`）—— 需逐个确认 6 个文件的 10 处 `v-html` 都过了清洗。
2. **灯箱焦点陷阱**：`role="dialog"` 已补，但 Tab 仍可能走到背后元素；要做完整的 focus trap + 关闭后焦点归还。
3. **`audit_log` 索引**：218 行仍不需要；若日后审计日志查询变慢再评估。
4. 棘轮基线需在**每次债务下降后** `--update` 刷新（否则「下降」不会反映到门禁上，不影响正确性）。


### 92.8 第二轮（同日续做：真缺陷闭包 / 订阅源 / CI 深度）

用户随后要求「能做的全部实现」，故把上一轮**只有实测才能发现的真缺陷**补齐。

| # | 项 | 复验结论 | 处置 |
| --- | --- | --- | --- |
| 1 | **每页 2 个 `<main>`** | **真缺陷**（上一轮遗漏）：`App.vue` 1 个 + **11 个视图各 1 个** → 每页 2 个。`main` 是 landmark，一个文档只应有一个 | 保留 `App.vue`（兼 skip-link 落点），11 个视图改 `<div>`；**改前先验证视图 CSS 不依赖 `main` 标签选择器**（实测无依赖） |
| 2 | **灯箱焦点陷阱** | 上一轮只补 `role="dialog"`，Tab 仍会跑到背后 → 键盘/读屏用户「掉出对话框」 | 补完整焦点管理：记录来源焦点、聚焦关闭按钮、**Tab 循环**、关闭后**归还焦点** |
| 3 | **`/api/qr` 用 `request.host_url`**（R90 待办②） | **真缺陷**：与「对外地址只走 `site_base()`」原则冲突（`/api/og/*`、`_abs()` 在 v3.18.9 已收口，此接口是**唯一漏网**） | 相对路径分支**不再回退请求 Host**，未配置即 400。**同时保住别名域名可用性**（前端 `postUrl` 派生自 `location.origin`）→ 绝对 URL 分支继续放行本次请求 host。两条方向相反，写 7 条测试钉住 |
| 4 | **Atom 1.0**（§5.4） | 此前只有 RSS 2.0 | 新增 `GET /feed.atom`，**复用 `/feed.xml` 的同一条查询**（不新增查询逻辑，避免两套订阅源口径漂移）。测试用 `xml.etree` **真解析**，并断言「未发布状态不泄露」「特殊字符被转义」 |
| 5 | **CI 覆盖率** | 基线 **49%**（9216 语句） | 加 `coverage` + `--fail-under=45`，定位是**防回退下限**，不是「证明覆盖充分」 |
| 6 | **CI CVE 扫描** | 实跑 `pip-audit` → **无已知漏洞** | 因基线干净，设为**阻断项** |

#### ⚠️ 92.8.1 更正一条审计结论：「`v-html` 未统一 `sanitizeHtml`」**不成立为风险**

上一轮我只抽查了 `App.vue` 就把它留作待办。本轮**逐个查完 4 处**未走客户端 `sanitizeHtml` 的 `v-html`：

| 位置 | 数据来源 | 服务端消毒 |
| --- | --- | --- |
| `App.vue` 公告 `a.content` | `/api/site` | ✅ `api/site.py:103`：`clean_html(render_markdown(a.content))` |
| `AboutView` `about_content` | `/api/site` | ✅ `api/site.py:20`：`clean_html(...)` |
| `SquareView` 博客圈 `it.summary` | `/api/feed/circle`（**第三方 RSS**） | ✅ `feed_agg.py:258`：`clean_html(e["summary"])[:300]` |
| `SearchView` `p.highlight` | 服务端生成 | ✅ 先 `escape()` 全文再插 `<mark>` |
| `PostView` 正文 `innerHTML` | `content_html` 缓存列 | ✅ 经 `clean_html` 白名单 |

**结论：消毒发生在服务端 —— 也就是正确的信任边界上。** 客户端再洗一遍属纵深防御，而对「管理员富文本」槽位反而**有风险**：DOMPurify 的默认白名单与服务端 `clean_html` 白名单**不一致**，会剥掉服务端认为是合法的标记，造成可见的内容缺失。
→ **收益不为正，故不加**；同时把「消毒在服务端」这件事记在这里，避免后人再按审计原文重开此条。

#### 92.8.2 本轮仍未做（清单已收敛，见 `ROADMAP.md` §5.9.1）

- **前端**：token 对比度（4 组 < 4.5:1）与 `derive_dark` 无 WCAG 校验｜表单 placeholder-only 无 `label`｜后台模板 `data-label`（**2/50**）｜`tokens.css` 两份且**已漂移**（2004 vs 2291 字符，需人工判断哪份为准）
- **性能**：`eager loading` 仍 **0 处**、`.all()` 107 处、列表 N+1（**须先量耗时再改**）、`/static/` 的 gzip/expires（nginx 层）
- **结构**：`create_app` **432 行**（比审计基线 373 还长）、函数级 import **258 处**（基线 226）→ **两者都在持续增长**，故必须先有门禁再动刀
- **schema**：Alembic 基线仍是假的 + 9 个手写 `_migrate_*` = 两份 schema 真相源
- **功能类**（ROADMAP §5.1–5.6，需产品决策或新表/外部凭据）：内容多语言、读者积分勋章、OAuth、2FA、PWA（已标注暂无计划）等

### 92.9 第三轮（统计深度 + SEO 自动推送）

用户要求把功能类清单也做掉，选**零表变更、无外部凭据、可验证**的项。安全维度逐项核对：

| 项 | 安全核对 |
| --- | --- |
| **来源渠道 TOP** | 数据只来自 `VisitLog.referrer`（v3.17.3 起只存 origin，**不含 query/path**），不回显完整 URL → 无 SSRF 反射面；未知来源退回域名本身（无害）。聚合走 `group_by`，参数化查询 |
| **实时在线 / 趋势环比** | 只读聚合，三个 helper 各自独立 `try/except`（`# noqa: BLE001`，理由写明），单点失败不影响统计页其余部分、更不抛到请求路径 |
| **CSV 导出** | `super_required` + 全局 CSRF 已覆盖；**公式注入防护**：单元格以 `= + - @ \t \r \n` 开头时加前缀单引号（防 `=cmd\|'/c calc'!A1` 类 CSV 宏执行）；**UTF-8 BOM** 让 Excel 正确识别中文；`days` 上限 `min(days, 365)` 防 `?days=999999` 拉全表做 DoS |
| **SEO 自动推送** | `maybe_auto_push` **复用 `enqueue`**（自带「3 次/5 分钟」限流 + pending 去重，连点发布不会重复烧配额）；**只推可见文章**（复用 `visible_posts_query`，含 `scheduled_at` 检查 → 未到点定时文章不会被推给搜索引擎）；无凭据引擎被 `submit_posts` 跳过（不会凭空造失败记录）；**全程异常不抛出**（绝不影响发布主流程、不破坏 `visible_posts_query` 真相源）；**默认关闭**（`SEO_AUTO_PUSH` / setting `seo_auto_push`），不烧百度当日配额。**无新增 SSRF 面**：`enqueue` → `push_baidu` / `push_indexnow` 走固定端点 + 既有超时/白名单 |

> 第三轮的 9 处 `# noqa: BLE001/S110` 全部来自「发布主流程不能被 SEO 推送拖垮」的防御性 `except`（每处写明理由），与「CSV 路由用具体异常替代裸 `except` 消除 1 处」相抵，故棘轮维持 **648 = 648**。详见 `CHANGELOG.md` §8 / §9。

## R93 · 内容多语言 M1 + PWA + 读者积分勋章 + OAuth + 2FA（v3.21.0）

**范围**：`myblog/oauth.py`（新）、`myblog/twofa.py`（新）、`myblog/gamify.py`（新）、`myblog/api/reader.py`（新）、`myblog/admin/twofa.py`（新）、`myblog/templates/admin/twofa.html`（新）、`myblog/models.py`（新增 `Reader`/`PointLog`/`Badge`/`ReaderBadge`/`OAuthAccount`/`UserTwoFactor` 六表）、`myblog/api/auth.py`（OAuth 三路由 + 2FA 五路由 + 登录二步）、`myblog/api/{posts,stats}.py`（积分埋点）、`myblog/config.py`（8 个**可选**环境变量）、`myblog/app.py`（自愈迁移表列）、`vue-frontend/public/{manifest.webmanifest,sw.js,offline.html,icon-*.png}`、`vue-frontend/src/{main.js,store.js,App.vue,views/LoginView.vue,views/PostView.vue}`、`tests/test_{oauth,twofa,gamify}.py`。

**来源**：v3.21.0 功能批次（用户勾选「四个功能全做」）。**本轮发现并修复 1 个高危账号接管缺陷（§93.1）**，另有 4 项设计取舍如实记录（§93.5）。纪律：安全项修复后一律补回归测试 + **变异验证**（回退修复必须变红），否则等于没修。

### 93.1 🔴 [High] OAuth 账号接管：未验证邮箱参与账号绑定（**已修**）

**缺陷**：`exchange_code()` 直接取 GitHub `/user` 的 `email` 字段，再用它去 `User.query.filter_by(email=...)` 匹配既有账号。而 GitHub `/user` 的 `email` 是**用户可自填的公开邮箱、不带验证断言** —— 攻击者注册一个 GitHub 账号、把公开邮箱改成受害者的邮箱地址，即可通过 OAuth 登录**接管受害者本地账号**（典型 OAuth 账号接管，且不需要碰受害者任何凭据）。

**修复**：把「provider 是否断言邮箱已验证」提升为**安全边界**，而非可选元数据：
- `exchange_code()` 返回值新增 `email_verified`。GitHub 侧改为**只信任 `/user/emails` 里 `verified && primary` 的条目**（`/user` 的 email 仅作展示名来源，明确标为未验证）；Google 侧用其显式字段 `email_verified`。
- `find_or_create_user(..., email_verified=False)`：**未验证邮箱绝不参与既有账号匹配**，只按 provider 侧不可伪造的 `sub` 命中，否则新建独立账号；新建时未验证邮箱**不落 `email` 列**（避免占位后被别处当作已验证使用）。

**回归测试 + 变异验证**（`tests/test_oauth.py`）：mock 的是**网络层 `_http_json`** 而非 `exchange_code` —— 只 mock 上层会把被修的判定逻辑一起替掉，等于没测。新增 3 条：GitHub 未验证不绑定 / GitHub 已验证才绑定 / Google `email_verified=false` 不绑定。变异验证 4 处，其中 3 条可达路径**全部变红**（`if email and email_verified` → `if email` 红 2 条；GitHub 循环条件去掉 `verified` 红 1 条；Google 忽略断言红 1 条；`email=email if email_verified else ""` → `email=email` 红 1 条）。

> 教训（可复用）：**任何「用第三方返回的邮箱去匹配本地账号」的绑定逻辑，都必须先确认 provider 是否断言了该邮箱已验证**；不同 provider 的字段名和语义不同（GitHub 无 `email_verified`，只有 `/user/emails` 的逐条 `verified`），不能靠猜——本轮最初的实现正是照「字段存在即可用」写的。

### 93.2 2FA / TOTP

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 算法正确性 | ✅ 用 RFC 6238 官方 6 条测试向量自证（SHA-1、8 位码） | `test_rfc6238_vectors` 逐条比对 `94287082/07081804/14050471/89005924/69279037/65353130` |
| 依赖面 | ✅ **零新增依赖**（未引入 pyotp） | 标准库 `hmac/hashlib/base64/struct/secrets` 实现；部署无需 `pip install` |
| 密钥存储 | ✅ 加密落库，绝不存明文 | 复用 `backup_settings.encrypt_secret`（Fernet，SECRET_KEY 派生，`bkenc$` 前缀）；测试断言 `row.secret_enc != secret` 且 `get_secret(row) == secret` |
| 防重放 | ✅ 同时间窗的码用过即失效 | `last_counter` 落库；`test_verify_replay_protection` + 登录二步同窗复用被拒 |
| 爆破防护 | ✅ 二步码 10/60s 限流；**本轮补** enroll/confirm/disable 各 10/60s | 审计前 `confirm` 无限流（6 位码空间仅 10⁶，持会话即可爆破）→ 已补，且三处用**独立 key** 互不挤占 |
| 越权 | ✅ 所有入口只作用于 `session["user_id"]` 本人 | `_cur_user()`；关闭还需**密码 + 动态码双确认**（防会话劫持后直接关掉 2FA） |
| 挂起态 | ✅ 5 分钟 TTL，超时必须重走密码 | `_TWOFA_PENDING_TTL=300`；`test_pending_state_expires` |
| 锁死风险 | ✅ 重新 enroll 会把 `enabled` 打回 False | 避免「换了密钥但没验证」把用户永久锁在门外；另有 8 个一次性恢复码 |
| 表结构 | ✅ 走**新表** `UserTwoFactor`，不给 `user` 加列 | SQLite `create_all()` 只建新表、**不 ALTER 已有表**，旧库升级时加列不会生效 |

### 93.3 读者积分勋章（gamification）

- `reader_token` cookie：`httponly=True` + `samesite=Lax` + `path=/` ✅（JS 读不到，缓解 XSS 后的身份冒用）。
- 积分发放走 `award_interaction()` 兜底：任何异常都吞掉并记日志，**绝不影响阅读/评论/访问主流程**（`# noqa: BLE001` 写明理由）。
- 去重键「同 reader + 同 reason + 同 post + 同天」，防刷量 ✅；`leaderboard` 的 `limit` 上限 50、非法值回落 10 ✅（防 `?limit=999999` 拉全表）。
- **公开排行榜会展示登录读者的用户名**（`Reader.name` 回落到 `user.username`）：这是**有意的产品行为**（排行榜需可辨识），但属于对外可见信息面，已在 CHANGELOG 明确告知站点所有者。

### 93.4 PWA Service Worker

- 只处理 **GET** 且**同源**请求 ✅；`/admin*` 直接放行、`/api/*` 中**除文章只读接口**（`/api/post/`、`/api/posts`）外全部不缓存 —— 因此 `/api/auth/*`、`/api/reader/*`、`/api/auth/2fa/*` **不会被离线缓存**，不存在「共享设备上离线读到他人会话数据」的路径 ✅。
- 导航 network-first + `/offline.html` 兜底；静态资源 stale-while-revalidate ✅。
- `manifest.webmanifest` 与图标为纯静态，**无密钥/无敏感字段**（已 grep 确认）✅。

### 93.5 设计取舍（明确接受，非遗漏）

| 项 | 决定 | 理由 |
| --- | --- | --- |
| OAuth state 用 `!=` 比较而非 `compare_digest` | 接受 | state 为一次性、单次会话内消费；时序攻击需大量样本且先要拿到同一会话，收益不抵复杂度 |
| 2FA 恢复码用 SHA-256 而非慢哈希 | 接受 | 恢复码是 `secrets.token_urlsafe(12)`（约 96 bit 高熵），**不存在暴力破解空间**，慢哈希只增加无谓开销；口令才需要 scrypt |
| TOTP 容忍 ±1 个时间窗（±30s） | 接受 | 补偿手机与服务器时钟漂移；同时用 `last_counter` 防同窗重放，二者不冲突 |
| OAuth / 2FA 默认**整体休眠** | 接受（刻意） | 未配凭据/未开开关时代码路径存在但不激活（start 返 503、2FA 入口 404、登录流程完全不变）——新增攻击面在无配置时为 **0** |

### 93.6 门禁与回归

- 全量 **269 passed**（本轮新增 32 条：OAuth 13 + 2FA 19）；`ruff check myblog tests` 全绿。
- **lint 棘轮维持 648 = 648**：本轮新增约 1500 行，一度涨到 673（+25），逐项真修后归零 —— 删无用导入/未用参数、`contextlib.suppress` 取代 `try/except: pass`（同时消 S110+BLE001）、清理测试未用变量；仅对 6 处「刻意兜底」的宽异常加 `# noqa: BLE001` 并写明理由。**未用 `--update` 抬基线**。

**R93 结论**：**0 遗留**。核心是 §93.1 那条 —— 「第三方返回的邮箱能否用于绑定」是本轮唯一真正的高危面，已修且由 3 条回归测试 + 4 处变异验证钉死。

### 93.7 上线后实证发现的静默降级（→ v3.21.1 修复，非安全类）

v3.21.0 **上线后在服务器上实测**才发现：`badge` 表建好了但 **0 行** —— 读者能攒积分却**永远拿不到勋章**，全程不报错。

**根因**：`create_app()` 在 `_migrate_new_tables_v3()` **之前**已执行 `db.create_all()`（app.py 第 619 行），新表在进函数前就已建好 → 函数内 `need` **恒为空** → 写在 `if need:` 分支里的 `seed_badges()` **从未执行**。

**处置**：播种移出条件分支，改为无条件幂等调用。回归测试 `test_badges_seeded_even_when_tables_already_exist`（先清空勋章再跑迁移，精确复现 `need` 为空的路径），**变异验证通过**（移回分支内 → 变红）。

> 与 §93.6 的关联：本轮**本地 269 全绿、服务器首跑即中**。原因正是本地测试库每轮重建（所有表都是「新表」→ `need` 非空 → 播种正常执行），而**生产库是既有库**，走的是 `need` 为空那条路径。**一般规律：涉及「首次初始化 vs 既有库升级」两条路径的逻辑，测试必须显式覆盖「既有库」那条。**

### 93.8 播种竞态假警报（→ v3.21.2 修复，非安全类）

v3.21.1 上线后日志出现 `默认勋章播种失败: UNIQUE constraint failed: badge.key`，勋章表数据完好（5 行）。**根因**：gunicorn 4 worker 并发启动，都通过 `Badge.query.count()==0` 检查、都去插入，后提交的撞键 —— 功能无害，但每次重启都留一条**假警报**，会掩盖真正的播种失败。顺带发现旧写法还有「表里有任意一行就整体跳过 → 缺的勋章补不齐」的问题。

**处置**：`seed_badges()` 改为按 key 逐枚幂等，撞键回滚放弃（另一 worker 已完成，非失败）。回归测试 `test_seed_badges_partial_and_race_safe`，**变异验证**（回退旧实现 → 2 条变红）。

> 与 §93.7 同一条经验链：**多 worker 并发是本项目部署常态（workers=4）**，任何「初始化一次」的写入逻辑都必须假设自己会与其他 worker 同时执行；判断「失败」前先想清楚「是不是别人已经做完了」。

---

## R94 · 第四轮复审：v3.19.3~v3.21.2 新增鉴权面 + 批次 1/2 遗留项

> 审计对象：v3.21.2（`80fa71d`）。第三方复审同时核对了上一轮清单（可见性泄露 / 权限面）的落地情况：**批次 1、批次 2 当时均未实施**，本轮随新发现一并修复。
> 结论：**2 条 Critical、4 条 High、若干 Medium**。§93.1 那条修复本身是**真的**（代码与测试都对），但同一段逻辑还有反方向的一半没修（见 §94.2）。

### 94.1 2FA 只是装饰：三条登录路径里只有一条判了第二因素（Critical）

全仓库唯一的第二因素检查在 `/api/auth/login`。而 `POST /login`（`routes.py`）、`POST /admin/login`（`admin/auth.py`）都是验完密码直接写 `session["user_id"]`，`login_required` / `admin_required` / `super_required` 又只看 `user_id`。攻击者从后台登录框输对密码即可拿到完整后台（含设置、删用户、备份），第二因素形同装饰。

**处置**：不在各路径补 `if`（第 5 条登录路径出现时还会漏），而是与 `enforce_session_version` 同层加 `enforce_twofa` 会话级闸门 + `/twofa` 挑战页；`_login_user()` 每次显式写回 `twofa_ok=False`。回归测试 `test_ssr_password_login_cannot_bypass_second_factor` 从**新的 SSR 会话**复现原绕过路径，**变异验证**：移除闸门 → 变红。

### 94.2 OAuth 账号接管：不可信的不仅是第三方给的邮箱，本地存的邮箱同样没验证过（High）

R93 §93.1 排除了「provider 返回未验证邮箱」，但保留了「按邮箱匹配既有账号」。问题是本站注册路径（`auth_register` / `routes.register`）对 email 只做 `strip()`——**无格式校验、无唯一约束、无所有权验证**。于是：攻击者先用受害者邮箱注册一个自己知道密码的账号 → 受害者首次 OAuth 登录 → 按邮箱匹配命中**攻击者**的账号并永久绑上其 provider `sub`（`OAuthAccount` 命中在邮箱匹配之前，之后每次登录都落进攻击者账号，且无解绑入口）。`.first()` 还无 `order_by`，命中哪行不确定。

**处置**：认领既有账号只保留「该账号当前已登录」一个入口（`bind_user_id` 取自服务端 session）。回归测试 `test_oauth_email_preclaim_cannot_takeover` 精确复现上述 4 步。

### 94.3 隐私文章经搜索/推荐/统计外泄（Critical）+ 索引里躺着正文全文

`_is_visible()` 只判 `published` / `scheduled_at`，不判 `is_private` / `in_trash`，却被 `/api/search` 的 FTS 分支和 `also-viewed` 使用；`stats._hot_posts()` 则裸用 `db.session.get(Post, id)`。FTS 索引自 v3.x 起就收录着隐私文章的**全文正文**。

**这是同一模式第 5 次出现**（v3.18.5 修过 `/api/review`、`/api/ai/summary`）。因此除接口层收口外，另加两道：索引侧闸门 `fts._indexable()`、静态防复发用例 `test_no_second_visibility_helper`（发现第二个 `*visible*` helper 即变红）。`ensure()` 只在表为空时回填 → 脏行必须显式重建，故新增 `fts.rebuild_all()` + `tools/rebuild_fts.py`。

### 94.4 发布路径漏同步索引：文章永久搜不到（High，功能类静默缺陷）

5 处改变可见性的写路径不调 `sync_post`：定时发布线程、两个 publish-now、批量发布/转草稿、回收站就地还原。**定时发布是最主要的那条**——它由机器触发，没有人会再人肉点一次「发布」，而 `ensure()` 不会自愈。之所以长期无人发现：中文查询因 FTS 未配 CJK 分词本就回退 LIKE，掩盖了缺行。

**处置**：`fts.sync_post_quiet()` 在 5 处统一收尾。测试 `test_publish_paths_sync_index`。

### 94.5 备份远程后端的 argv 注入（High）

`BACKUP_SCP_HOST` / `BACKUP_WEBDAV_URL` 来自后台可编辑的 Setting 表（`apply_to_environ()` 写回 `os.environ`），却直接拼进 argv：`-oProxyCommand=<命令>` 被 scp 当选项 → 以 gunicorn 进程身份执行任意命令；`file://` 配 `curl -T` → 把备份包写到任意本地路径。`_run` 早已禁 `shell=True`，缺的是 argv 层。已加取值形态校验 + `--` 结束选项解析。

### 94.6 「恢复」在有上传文件时必然崩掉（High，可用性）

`_snapshot_before_restore()` 的 uploads 打包循环写在 `with ZipFile(...)` **块外**，对已关闭归档调 `write()` 实测抛 `ValueError: Attempt to write to ZIP archive that was already closed`；`restore()` 在覆盖主库**之前**调用它 → 快照一崩整个恢复中止。即：**最需要恢复的时候恢复不可用**。且该快照不写 manifest（`verify()` 会拒收，「回退保险」是纸面的），其 `blog_prerestore_` 前缀也不被 `prune_local()` 匹配（无限堆积）。三条一起修。

### 94.7 其它已修（Medium）

`super_required` 缺首登闸门（29 条裸用它的路由在默认密码窗口期内全部可用）；插件 `slug` 目录穿越（`makedirs`/`open(w)`/`os.remove` 原语）；`feed_agg` 内层复用外层变量名 `_old_to` → 出口还原的是错的值，**进程级 socket 默认超时被永久改写**；删用户导致 rowid 复用与 `OAuthAccount` 孤儿绑定；勋章并发提交不 rollback → 评论请求连带 500；`/api/reader/me` 未鉴权无限流却会写库；`_hot_posts` 所在的 `/api/stats/summary` 无 `rate_limit`。

### 94.8 本轮记录但**未**修改（需产品决策或需改表结构）

1. **积分身份 = 客户端 cookie，去重键含 `reader_id`** → 丢掉 cookie 即刷新每日额度，排行榜可被无限刷。但积分/勋章经核对**不参与任何权限或可见性判定**（纯展示），故属公平性而非安全问题。
2. `PointLog` 去重缺复合 UNIQUE 约束（`award` 仍是 check-then-insert）；`Reader.points` 无索引 → 排行榜全表排序。都需要迁移。
3. 未过审评论即发 +5 积分，驳回不回收。
4. 无 `reader` / `point_log` / `reader_badge` 保留策略（仅 `AuditLog` 有）。
5. OAuth **未接入 2FA**：已绑 2FA 的账号仍可从 OAuth 直接进（把 IdP 视为等效第二因素是常见设计，但若 provider 账号被盗则 2FA 失效）——需决策，且改动会影响前端流程。
6. 订阅邮件群发仍**每个收件人一次 SMTP 连接 + 一次登录**（`_send_smtp`），上千订阅者时会被 QQ/163 限流。
7. 后台无 OAuth 绑定列表/解绑入口（§94.2 的可发现性缺口）。

### 94.9 v3.22.0 发版说明（合并 PR #14 落地）

- **合并方式**：PR #14（`fix/audit-v3212-security`，作者 `Llhhy1`）rebase 到 v3.21.2 之上，无冲突，本地 `--no-ff` 合并（merge 节点 `304772c`）。
- **发版口令**：用户选 B 方案「全收」——即接受 PR 原设计与其全部取舍，作为 **v3.22.0**（非补丁）整体发版，合后跑 `tools/rebuild_fts.py` 并重发版验证。
- **取舍确认（沿用 PR 设计）**：① OAuth+2FA 用户由全局 `enforce_twofa` 闸门重定向到挑战页（安全行为）；② 删用户改停用；③ 积分公平性 / `PointLog` 复合 UNIQUE / 保留策略——本版刻意不做；④ 老邮箱绑定用户需重新绑定（§94.2 必要取舍）。
- **审计纪律备注（事实澄清）**：PR 正文把 §94.3 写成「上一轮（R93）可见性修复一条都没落地」——**经逐条回代码核对，该表述不实**。`visible_posts_query()` 在 v3.21.2 中于 `api/posts.py` / `routes.py` / `api/og.py` / `admin/seo.py` / `api/review.py` 等约 40 处均已使用，真实漏口只有 `api/posts.py` 的 2 处（相关推荐、搜索）与 `fts.py` 写入侧。其余 §94.1 / §94.2 / §94.4 / §94.5 / §94.6 的底层事实均属实（仅 §94.5 严重度偏高，属管理后提权而非未授权远程 RCE）。
- **本地核实**：300 passed；ruff 全绿；lint 棘轮 648 = 648（PR 带入 1 处 `fts.py:133` SIM105，已真修）；compileall + 打包三链互证与验签通过；`enforce_twofa` / FTS `_indexable()` / OAuth 本地邮箱闸门 / 备份注入校验 均按 diff 复核，逻辑正确。
- **部署必做**：升 v3.22.0 后跑一次 `python tools/rebuild_fts.py`，否则历史库隐私/回收站正文脏行不会被清。

## R95 · v3.23.0 发版安全审查（后台任务 + 结构化日志 + OAuth 解绑 + 天气缓存 + CI 门禁）

> 审计对象：本轮 18 改 + 9 新增（基线 6618ca8）。结论：**未发现新增暴露面**，限流 / CSRF / 越权 / 密钥 / 资源释放逐项核对通过。

### 95.1 新增攻击面逐项核对

| 改动 | 维度核对 | 结论 |
| --- | --- | --- |
| `admin/oauth_bindings.py`（OAuth 绑定列表 + 解绑） | 越权：仅本人；超管可 `?user_id=` 查他人但**不得解绑他人最后一个绑定**（超管密码只证明超管身份）；CSRF：POST 走全局 `_csrf_protect`；SQL：ORM `filter_by`/`get` 参数化；XSS：模板 autoescape；审计：`log_audit` 成败皆记 | ✅ 通过 |
| `tasks.py`（后台长任务） | 路径穿越：`status()` 仅接受**字母数字** task id，`../` 直拒；状态文件为**原子写**（tmp+replace），防轮询读到半截 JSON；跨进程互斥用锁文件（`O_EXCL`）+ 过期清理，锁名全部为内部常量；异常落盘不外抛；线程内 app context 仿 `notify.py` 既有范式 | ✅ 通过 |
| `/admin/task/<id>`（任务状态轮询） | `admin_required`；只回 `id/name/state/message/error` 五字段。⚠️ `error` 为 `str(e)[:500]`，可能含内部路径——**仅管理员可见，接受**（与管理页既有口径一致） | ✅ 通过（注记） |
| `logging_setup.py`（结构化日志） | **日志注入**：沿用上游 `X-Request-ID` 前做形态校验（≤64、字母数字/`-`/`_`），否则丢弃重生成；格式化仅含 `request_id/levelname/name/message`，**不含** query/body/cookie，无密钥泄露面 | ✅ 通过 |
| `/api/weather` 缓存 | `city` 用户可控 → cache key 无界增长风险，**限容 200 + 到顶全清**；出站 URL 全部固定白名单域名 + `quote` 编码（SSRF 既有口径不变）；只缓存成功结果；失败回吐**同 key** 过期数据（不串味）；限流 60/min 保留 | ✅ 通过 |
| 备份改后台任务 | `super_required` 不变；CSRF 不变；审计日志改为「任务已提交」+ 任务状态落盘；`create_backup` 本身无改动 | ✅ 通过 |
| 游戏上传 LLM 审计后台化 | 线程内按 id 重取 Game（防 detached 对象写脏数据）；审计结果仍写回 `Game` 行，权限口径不变 | ✅ 通过 |
| CI（npm audit + CodeQL） | 无密钥入仓；CodeQL 刻意**非阻断**（SAST 告警需人工判定） | ✅ 通过 |
| `api/common.py` `import stats` noqa / 删 `import io` / fts.py、backup.py 加 noqa | 纯注释/死代码清理，**零行为变更**（棘轮债修复，非功能） | ✅ 通过 |

### 95.2 本轮记录但未修改

1. `/admin/task/<id>` 的 `error` 字段可能含内部路径（如 traceback 片段）——仅管理员可见，与全站「管理页可看异常摘要」口径一致；若未来开放给普通用户需先脱敏。
2. 天气缓存的「到顶全清」策略在极端并发下可能互相挤掉对方缓存（DoS 放大有限，rate_limit 60/min 已兜底）；若日后上量再换 LRU。
3. CodeQL 首轮可能报出一批历史 SAST 告警（非阻断，进 Security 选项卡），处置见 ROADMAP。

### 95.3 部署注意

- 新增运行期目录 `data/tasks/`（任务状态 + 锁文件，自动创建；`update.sh` 不触碰 data/，无需迁移）。
- 新增可选环境变量 `LOG_LEVEL`（默认 INFO，不改任何默认行为）。
- `/api/weather` 行为变化：同参数 10 分钟内返回缓存（含失败时回吐过期值），属预期。
- 本版**无表结构变更、无 `_RENDER_VERSION` 变化**；`rebuild_fts.py` 无需重跑。

---

## R96 · v3.24.0 发版安全审查（表结构改走 Alembic + 积分去重/保留策略 + 定时发布防重 + Setting 治理 + create_app 拆分）

> 审计对象：本轮 13 改 + 6 新增（基线 4d5ab38）。结论：**未发现新增对外暴露面**；新增一个运维态环境变量（`BLOG_MIGRATE_ONLY`），其风险已评估并收敛（见 96.2 第 1 条）。SQL 注入 / 越权 / CSRF / SSRF / 密钥 / 资源释放 / 限流七维逐项核对通过。

### 96.1 新增/改动攻击面逐项核对

| 改动 | 维度核对 | 结论 |
| --- | --- | --- |
| `app.py::claim_scheduled_post()`（定时发布原子认领） | SQL：一条 `UPDATE post ... WHERE id = :id AND COALESCE(published,0) != 1`，**全参数绑定**；无用户可控输入；越权：仅在调度线程内调用，非路由 | ✅ 通过 |
| `app.py` `create_app()` 拆分（510→35 行） | 纯搬运、零逻辑改动；**`before_request` 注册顺序已用探针实证**保持一致（同源→预检→会话版本→闲置→2FA）；无新增路由/无新增暴露面 | ✅ 通过 |
| `BLOG_MIGRATE_ONLY=1`（新增环境变量） | 见 96.2 第 1 条：仅在进程内注入一次性随机 `SECRET_KEY`，**不落盘、不生效于会话**；跳过全部启动副作用；属运维显式开关 | ✅ 通过（注记） |
| `gamify.award()` 捕获 `IntegrityError` 并回滚 | 正确性+可用性：并发撞唯一键时不再 500；回滚同时撤销同事务里已执行的积分 `UPDATE`，防重复加分；异常不外抛到公开读路径 | ✅ 通过（修复） |
| `gamify.prune_retention()`（保留策略清理） | SQL：`DELETE ... WHERE created_at < :cut` 与孤儿清理，**全参数绑定**；仅在调度线程内、包 `try/except` 记日志；无用户可控输入；不涉及删 `reader`（永久保留） | ✅ 通过 |
| `models.py` 新增索引 | 表达式索引 `COALESCE(post_id, -1)` 为**代码内常量**，不接受任何输入；`ix_reader_points` 普通索引 | ✅ 通过 |
| `models.py` 新增列 `comment.reactions` / `post.ai_summary` / `post.ai_tags` | 均为 TEXT，承载的是**原本就存在**的 UGC（原先在 `setting` 表），信任边界**不变**；无新增渲染出口 | ✅ 通过 |
| `api/reactions.py` 存储改造 | SQL：`Comment.query.filter(Comment.id.in_(cids))`，`cids` 经 `isdigit()` 过滤转 int，ORM 参数化；XSS：仅返回 JSON；CSRF：POST 走全局 `_csrf_protect`（用例已实证需 `X-CSRF-Token`）；限流：保留 40 次/60s；越权：保留「仅已审核评论可回应」判定；JSON 解析坏数据一律当空（不让前端炸） | ✅ 通过 |
| `api/ai.py` 摘要改读 `Post` 列 | 越权：**仍走 `visible_posts_query()`**（隐私/回收站/未到点仍 404）；XSS：仅返回 JSON；限流：超管生成保留 10 次/小时；删掉随之失效的 `_setting_get/_setting_set` 死代码 | ✅ 通过 |
| `admin/ai_summary.py` 读写改走 Post 列 | 越权：全部路由仍 `@super_required` + `log_audit`；**保存/清除现改为先取 Post、不存在即 404**（比原先「不管文章在不在都写 Setting」更严）；无新增路由 | ✅ 通过（收紧） |
| `migrations/env.py` `include_object` | 排除 `post_fts*` 与表达式索引 `uq_pointlog_dedup`。**安全意义**：防止 autogenerate 生成 `DROP TABLE post_fts*` 把全文索引删掉（属破坏性误操作防护） | ✅ 通过（加固） |
| 3 个迁移脚本 | SQL：值一律参数绑定；表名/列名来自**代码内常量字典**（非用户输入）已注明；`PRAGMA table_info(%s)` 同理；无密钥操作 | ✅ 通过 |
| `update.sh::apply_db_migrations()` | 以**站点运行用户**执行（`run_as`，防 `blog.db` 变 root 属主）；带 `BLOG_MIGRATE_ONLY=1`（部署机无需持有管理员凭据）；**迁移失败即中止且不重启**（fail-closed：不让新代码访问旧表结构）；`timeout 300` 防挂起 | ✅ 通过 |
| 4 个测试文件（新增/改动） | 无密钥、无真实外部调用；新测试自带清理 fixtures（本轮踩坑见 96.2 第 3 条） | ✅ 通过 |

### 96.2 本轮记录但未修改

1. **`BLOG_MIGRATE_ONLY=1` 若被误配到生产常驻环境，会跳过 `SECRET_KEY`/`ADMIN_PASSWORD` 校验与超管兜底**（进程内随机 `SECRET_KEY` 会让既有会话失效）。评估为**低危且可接受**：它是显式 opt-in、仅由部署脚本的迁移步骤临时注入（`env` 前缀，不写入任何配置文件），且随机密钥只存在于进程内存。**缓解**：deploy_guide 已写明「仅迁移使用，无需手工配置」。若日后要更严，可在 `create_app` 里对该模式下发一次醒目的 `logger.warning`。
2. **两条迁移含删除动作**：`b3f6c1d84a72` 删 `point_log` 重复行、`e5b8c3f17a24` 搬走后删 `setting` 中的 UGC 行（含孤儿）。均为「先复制、后删除」，内容不丢；**升级前必须备份 `blog.db`**（`update.sh` 会自动备份，手动升级者需自行备份）。已在 deploy_guide 显著标注。
3. **`fts.rebuild_all()` 每批结束会 `db.session.expunge_all()`**，会把调用方持有的 ORM 实例摘出会话（本轮因测试污染才暴露）。生产调用方（`ensure()`/后台重建）不持有跨调用实例，属**低危**；已记入 ROADMAP 待办，不在本版改动（避免在发版窗口引入额外行为变化）。
4. `Setting` 表仍保留 6 处 `Setting.query.all()` 全表加载：UGC 搬走后它只剩几十条真设置，**不再为它引入缓存**（与 §5.9 对 `inject_globals` 的同类判断一致：20 处写入无收口点，收益 < 复杂度）。

### 96.3 部署注意

- ⚠️ **部署流程变更**：本版退役 9 个 `_migrate_*`，表结构改由 `flask db upgrade` 承担。`update.sh` 已在「覆盖代码 → 应用迁移 → 重启」中内置该步骤；**手动升级者必须手工补跑**（不跑不报错，但新索引不生效）。
- 新增环境变量 `BLOG_MIGRATE_ONLY`（运维内部使用，无需手工配置）。
- **无 `_RENDER_VERSION` 变化**（未改正文渲染/Markdown/白名单），`rebuild_fts.py` **无需**重跑。
- 无新增必填环境变量；无 Nginx 变更；前端 `vue-frontend/src` 未改动（无需重新 build）。
- 上线后建议核对：库中应存在 `uq_pointlog_dedup` 与 `ix_reader_points` 两个索引；`setting` 表不再有 `react_*` / `ai_summary_*` / `ai_tags_*`。


## R97（v3.24.1 · 2026-09-30）—— admin 包星号导入治理（纯结构，零行为变更）

**范围**：`myblog/admin/` 23 个文件 + `tests/test_admin_explicit_imports.py`（新增）。v3.24.0 上线后的内部治理：`_helpers.__all__` 由 `globals()` 运行时快照改为显式清单，16 个业务子模块的 `from ._helpers import *` 全部改为显式导入，`__init__.py` 星号转发收敛为 `admin_bp` + `log_audit`/`log_login_attempt` 两个 re-export（grep 全仓核定外部消费面）。

**七维核对**：
| 维度 | 结论 |
|---|---|
| XSS | 不涉及（未改任何渲染/模板/输入路径） |
| SQL 注入 | 不涉及（未改任何查询） |
| 越权 | 不涉及（装饰器 `admin_required`/`super_required`/`login_required` 本体未动，仅导入方式变化；`@admin_required` 装饰的视图集经守卫测试证实全部可解析） |
| SSRF | 不涉及（未改任何出站请求） |
| CSRF | 不涉及（全局 `_csrf_protect` 钩子注册顺序未动，`_register_request_hooks` 未改） |
| 密钥泄露 | 不涉及（无凭据相关改动；扫描无硬编码密钥） |
| 资源泄漏/限流 | 不涉及 |

**结构性安全收益**：星号 + 运行时 `__all__` 快照会把 `os`/`time`/`json` 等模块级名字与全部模型静默灌入每个后台模块——既是可维护性债，也让「某个后台模块意外拿到不该有的能力」无法被静态审查。治理后每个模块的依赖面显式、可 grep、被 ruff F821/F401 双向看住（本轮 F821 一度暴露 1076 处星号时代不可见的幽灵依赖，全部以显式导入收敛）；新增 4 条守卫测试（AST 禁星号、`__all__` 禁运行时快照、全模块 LOAD_GLOBAL 可解析的零 NameError 证明、re-export 面与外部消费面一致），并经变异验证（改回星号必红）。

**验证**：366 passed / ruff 全仓全绿 / 棘轮 601→543（F401 171→113、T20 66→21）/ 变异验证通过 / admin 蓝图 113 条路由注册数与治理前一致。

**升级要点**：无表结构变更、无迁移、无新增环境变量、无前端改动（无需 vite build）、无部署脚本变更（无需 deploy_scripts 包）；`rebuild_fts.py` 无需重跑。升级即「覆盖后端 → 重启」（update.sh 用户一键完成，其内置迁移步骤在 head 处为无操作）。

---

## R98 · v3.25.0 发版安全审查（WCAG 对比度治理 + 包级循环依赖清零 + FTS 会话隔离 + data-label 补全 + 文档归档 + 裸 hex 收敛）

**背景**：本轮是 v3.25.0 **发版前审查**，覆盖自 v3.24.1 上线以来的全部累积改动。其中「包级循环依赖清零 + FTS 会话隔离」两项属于 v3.24.1 之后、本版本之前的治理批次，**此前未单独录入审计台账**，与其余四项一并在本轮过审。

**范围**：27 个 Python/前端文件 + 23 个后台模板 + 6 个测试文件。其中含 3 类结构性改动（新增顶层模块 `myblog/audit.py`、`fts.rebuild_all()` 改用 Core 查询、`seo.html` 循环列拆解为显式宏调用）与 3 类纯样式/文档改动（token 对比度、`data-label` 补全、裸 hex→`var()`）。

### 98.1 八维核对

| 维度 | 结论 |
|---|---|
| XSS | **未引入**。23 个模板的改动经 diff 逐行核实，新增侧**只有** `data-label="字面量"` 属性与 2 处结构性调整（`oauth_bindings.html` 类名切换、`seo.html` 的 `{% macro %}`）；`data-label` 值全部是模板内硬编码中文/英文字面量，**不含任何用户可控数据**（守卫 `test_data_label_值已转义` + `test_data_label_不是空串`）。`seo.html` 里原有的 `{{ cell.response }}`（含在 `title="…"` 属性内）**未改动**，Jinja2 autoescape 已覆盖。 |
| SQL 注入 | **未引入**。`fts.rebuild_all()` 由 ORM 查询改为 Core `db.select(*_REBUILD_COLS)`，`_REBUILD_COLS` 是模块级常量的**写死列对象**（非字符串拼接），`where(Post.id > last_id)` 走 SQLAlchemy 参数化。全 diff 无可执行的用户输入拼接。 |
| 越权 | **未引入**。所有 `@admin_required` / `@super_required` 装饰器本体与注册顺序未动；`api/theme.py` 的 `theme_post` 超管校验（`user.is_super` → 403）保持原样。`myblog/audit.py` 新增顶层模块只导出纯写入函数，不含任何视图或权限判断。 |
| SSRF | **未引入**。本轮零出站网络请求改动（`seo_push.py` 只把 `log_audit` 的导入位置从函数内移到模块顶层，出站逻辑与 `_NoRedirect` 禁跟随重定向策略均未触碰）。 |
| CSRF | **未引入**。全局 `_csrf_protect` 钩子注册顺序未变；`seo.html` 里两个 `{{ csrf_input() }}` 表单保持原样。**注意**：`seo_push_cell` 宏**不产生**任何表单，只是渲染状态文本，故不构成新的 POST 面。 |
| 密钥泄露 | **未引入**。无凭据新增/移动；`audit.py` 不触碰 `SECRET_KEY` 或任何加密 Setting。 |
| 资源泄漏 | **修复 1 项**（详见 98.2）。 |
| 限流 | **未引入**。无限流相关改动。 |

### 98.2 `fts.rebuild_all()` 的会话污染修复（本轮唯一的功能性安全修复）

**问题**：原实现为避免几十万 ORM 实体堆在会话里，在**每批末尾**调用 `db.session.expunge_all()`。但 `expunge_all()` 是**整个会话级**操作 —— 它会把**调用方自己持有的实例**一并摘出会话，调用方随后再访问这些对象就是 detached instance（`DetachedInstanceError`）。

**为什么此前没爆**：唯一的生产调用方是 `tools/rebuild_fts.py`（离线脚本，执行期间不持有任何 ORM 实例），所以一直是「低危未爆」。第一个真实受害者是测试里 `test_setting_governance` 构造的 `Post` 对象。

**修复**：改用 Core `select()` 取**标量行**（`db.select(*_REBUILD_COLS)`），不产生 ORM 实体 → 会话里压根没有需要 expunge 的东西，`expunge_all()` 自然删除。三重收益：① 调用方实例不再被牵连；② 内存占用与原来同量级且不随批数累积；③ 不再有「rebuild 顺手 detach 了别人对象」的隐式副作用。`_indexable()` / `_insert()` 只碰 `_REBUILD_COLS` 列出的 9 列，鸭子类型用法无需改动即可吃 `Row`。守卫：`tests/test_fts_rebuild_isolation.py`。

### 98.3 主题色的 CSS 注入面复核（结论：无新增风险，但发现一处代码缺陷）

实测路径：`POST /api/theme` 的 `custom` 分支只校验 `light.accent` **存在**、不校验格式（`api/theme.py:47-50`），故 Setting `theme_tokens` 里可以存进 `"red"` / `"rgb(1,2,3)"` / `"#fff; background:url(//evil)"` / `"#fff</style><script>…"` 等任意值。实测处置结果：

- `derive_dark()` 对上述畸形值 **全部存活**（`hex_to_oklch` 有 `or (0.6, 0.12, 0.0)` 兜底），且**原样透传** accent；
- 消费终端是 `store.js: applyThemeTokens()` 的 `el.style.setProperty(name, value)` —— **CSSOM API 不解析值**、不把它当样式表文本，故 `;` / `</style>` 无法逃逸出属性上下文注入新规则或新标签 → **无 XSS**；
- 后台 admin 的主题来源是静态文件 `myblog/static/tokens.css`，`theme_tokens` 完全不进后台 CSS → 二者互不污染；
- 结论：**此面存在但不可利用**，且属 v3.16.0 既有行为，本轮未改。不升级为必改项，仅在 R98 留档。

**同时发现的真实代码缺陷（已修）**：本轮新增的颜色求解器 `_at_lum()` 内存在**两段完全重复的二分**（v3.25.0 编辑事故），第一段缺 `else: hi = mid` 且结果被第二段整体覆盖 —— 纯死代码，但是真陷阱：后来人只会改到第一段、改完看不到任何效果。已删除，并新增守卫 `test_at_lum_has_no_duplicated_block`（用「关键标记不得出现两次」+「必须存在 `else: hi = mid`」双向钉住）。

**加固（零成本）**：`_at_lum()` 对畸形 `hex_color` 原本直接抛 `ValueError` / `AttributeError`（底层 `_hex_rgb` 无防护）。当前唯一调用方 `_tier_for` 已先用 try/except 探测过 `base_hex`，故**生产路径不可达**；但模块 docstring 明写「任意色彩解析失败都回退默认值，绝不抛异常导致页面 500」，「靠调用方守」太脆 —— 已在函数内加 try/except，畸形返回 `None`（与既有「目标不可达」语义一致，`_tier_for` 的 `if cand is None: continue` 已覆盖）。新增守卫 `test_solvers_never_raise_on_malformed_colors`（9 种畸形值 × 5 个求解器 = 45 组合）。

### 98.4 变异验证（新增 2 条守卫，3 项变异全部精确变红）

| 变异 | 注入方式 | 结果 |
|---|---|---|
| [1] 删掉 `_at_lum` 的 try/except 兜底 | 还原为直接取值 | **8 failed**（畸形值 owed 8 个参数化用例全红） |
| [2] 重新注入重复的二分块 | 在现有一段前插入缺 `else` 的版本 | `test_at_lum_has_no_duplicated_block` 精确红 |
| [3] 删掉二分里的 `else: hi = mid` | 保留单块但去掉 else | 同上精确红（正反双向都守住了） |

**踩坑补记**：第一轮手感探针把畸形值传在 `_at_lum` 的**第 2 个参数**（`fn("#196ddd", bad, …)`），得出「全部存活」的**假阴性**；写成真正的守卫时畸形值传在第 1 个参数（被调色的原色）才暴露出真真空。**教训：探针的调用姿势必须与生产调用姿势逐参数对齐，否则等于没测。**

### 98.5 其余四项的八维结论

- **后台表格 `data-label` 补全**（121 处 / 23 模板）：纯属无障碍改进，八维全部「不涉及」。附带修掉 3 个真问题 —— `oauth_bindings.html` 的 5 处**死标注**（`.stats-table` 全站无 `::before` 规则，标注永不渲染，改类名 `admin-table` 后当场生效）、`ai_summary.html` / `seo.html` 的**套娃表**卡片化后字段名全丢、`seo.html` 的**循环生成列**（静态标注会把「百度」「Bing」两列都写成「百度」）。
- **包级循环依赖清零**（新增 `myblog/audit.py`）：拆除的是 `api → admin` 与 `admin → api` 两条顶层边（此前把两个包拉进同一个 **21 模块强连通分量**）。`api/theme.py` 与 `seo_push.py` 原先只能在**函数内延迟导入** `log_audit`（因为顶层导入会 ImportError），现在可以正常顶层导入 —— 收益是「导入失败会 loud fail」而不是被 `except Exception: pass` 静默吞掉导致**审计日志丢失**。这是审计可追溯性的实质增强。
  - **变异验证的强证据档次高于寻常**：两个反向变异都不是「测试变红」，而是**真实 ImportError**，且发生在 **pytest 收集期** —— 守卫测试根本没跑到就崩了：`api/common.py` 退回 `from admin import` 报 `cannot import name 'log_login_attempt' from partially initialized module 'admin'`；`audit.py` 反向 `from admin import` 报同类错。**这证明那个 21 模块环从来不是理论风险**，而是「只要有一条边写回去，整个后台就起不来」的硬故障。
- **文档归档**（主文件 1,088 → 531 KB）：归档件仍在版本控制内（`docs/archive/`），且 `tools/review/check-staged.py` 的 `DOCS` 门禁已同步加入两条归档路径，**否则发版门禁会失效**。
- **裸 hex 收敛**（`style.css` 11 处）：沿用 v3.17 起的 `var(--token, #原值)` 兜底约定，三重判据（值逐字相等 / 只在亮色作用域成立 / 语义一致），零像素差。

### 98.6 验证与升级要点

**验证**：全量 pytest（见发版记录）/ ruff 全仓 `All checks passed!` / 新增 3 类守卫共 74 条断言（`test_admin_table_data_label.py` 52、`test_doc_archival.py` 13、`test_css_token_ratchet.py` 9）/ 本轮新增 2 条对比度健壮性守卫 + 3 项变异全部变红。

**升级要点**：无表结构变更、无 Alembic 迁移（head 仍为 `e5b8c3f17a24`）、无新增环境变量、无部署脚本变更；**需要 vite build**（改了 `vue-frontend/src/styles/tokens.css`）；`rebuild_fts.py` **不需要**重跑（本轮未改 `_indexable()` 判定条件，只是遍历方式变了，且 batches 结果与原先一致）。升级即「覆盖代码 → `flask db upgrade`（head 处无操作）→ 重启」。

**上线后 checklist**：抽查某篇含 SEO 推送记录的文章，确认「百度 / Bing」两列状态各自正确（不再都显示「百度」）；手机 UA 下任取一张后台表格，确认卡片化后每格都带字段名抬头。

---

## R99 · v3.25.1 发版安全审查（深色模式可读性修复 + 表单可访问名补全）

**范围**：`vue-frontend/src/styles/global.css`（+45 行，纯 CSS 深色覆盖）、
26 个后台模板（+可访问名）、2 个测试文件（+5 条守卫）、4 份文档。

### 99.1 八维核对

| 维度 | 结论 |
|---|---|
| XSS | **未引入**。全部改动是 CSS 属性值与 HTML 属性（`for` / `id` / `aria-label`）。`aria-label` 的值**全部是模板内硬编码的中英文字面量**，无一处来自用户可控数据；`for`/`id` 同理（循环内用 `ser-name-{{ s.id }}` 这类**数据库主键**拼接，非自由文本）。Jinja2 autoescape 亦已覆盖。 |
| SQL 注入 | **不涉及**。本轮零查询改动。 |
| 越权 | **不涉及**。未触碰任何视图、装饰器或权限判断。 |
| SSRF | **不涉及**。零出站请求改动。 |
| CSRF | **未引入**。表单只是补了可访问名，`{{ csrf_input() }}` 与提交目标均未动。 |
| 密钥泄露 | **未引入**。无凭据相关改动。 |
| 资源泄漏 | **不涉及**。 |
| 限流 | **不涉及**。 |

### 99.2 本轮真正的安全相关收益：可访问名 ≠ 只是无障碍

补 `for`/`id` 与 `aria-label` 通常被归为 a11y，但本轮有两处**安全/可用性交叉**的实质收益：

1. **`.comment-content` 深色下 1.84:1** —— 整段评论正文在深色模式等于不可见。
   这不只是「不好看」：用户**看不到自己要回复的内容**，可能误判上下文而泄露信息
   （例如在看不见原文的情况下回复敏感内容）。属于低危但真实的信息处理风险。
2. **「点标签聚焦控件」** —— A 类 40 处补 `for`/`id` 后，标签文字变为可点击的
   命中区。对运动功能障碍用户是实质可用性提升，也降低了误触相邻控件的概率。

### 99.3 本轮脚本差点引入的缺陷（已拦下，留档）

- **重复 id 属性**：第一版脚本给**已有 id** 的控件又加一个（`f-title` / `slugMode` 等，
  JS 与 CSS 依赖），产出 `id="title" ... id="f-title"` —— 非法 HTML，浏览器只认第一个，
  等于**静默打断 JS 选择器**。11 处中招，全部回滚重做（改为复用原有 id，只改 label 的 `for`）。
  已加守卫 `test_no_duplicate_id_attribute_in_one_tag`。
- **循环内固定 id**：`series` / `categories` 的编辑行在 `{% for %}` 内，固定 id 必然重复。
  已改用 Jinja 主键拼唯一 id（`ser-name-{{ s.id }}` / `cat-move-{{ c.id }}`）。

### 99.4 长期债盘点（先量数据再判断，三项判定不做）

- ❌ **`LICENSE` ×3**：三份同内容（1083 B / 同 sha），但 **`myblog/LICENSE` 实证进发布包**
  （`package.py` 打包整个 `myblog/`，LICENSE 不在 `EXCLUDE_DIRS`；
  实测 `myblog-backend.zip` 内含 `myblog/LICENSE`）→ 删了发布物就没许可证。零维护成本。
- ❌ **`v3.x.y` 注释版本戳 524 处**：形如 `# v3.23.0：结构化日志`，是有价值的历史标注
  （说明该段代码为何存在、哪版引入），删掉会让后来人失去变更溯源；纯注释不参与构建。
- ❌ **性能项**（`eager loading` / N+1 / 索引）：线上实测 `/api/site` 52ms / `/api/posts` 15ms /
  `/api/review/annual` 22ms / `/api/games` 5ms；生产库 `post` **8 行** / `comment` 2 /
  `point_log` 391 / `reader` 635 —— **最大表仅 635 行**。此量级下全表扫描比索引快、
  8 行的 N+1 只产生 8 次亚毫秒查询 → 收益为零，只增复杂度。
  **已写明重新评估触发条件**：`post > 500 行` 或 `comment > 2000 行` 或任一 API p95 > 200ms。

**方法论**：ROADMAP 里的「未做（N 项）」有时是**伪债**（记下时未量过数据）。
动手前先实证；判定不做时**必须写明理由与触发条件**，否则下一个人还会再来一轮。

### 99.5 验证与升级要点

**验证**：482 passed / ruff 全仓 `All checks passed!` / 新增 5 条守卫 /
本轮 9 项变异（深色 6 + 表单 3）**全部精确变红** / 构建产物实证含新色值。

**升级要点**：无表结构变更、无 Alembic 迁移（head 仍 `e5b8c3f17a24`）、无新增环境变量、
无部署脚本变更；**需要 vite build**（改了 `vue-frontend/src/styles/global.css`）。
升级即「覆盖代码 → `flask db upgrade`（head 处无操作）→ 重启」。

**上线后 checklist**：切换深色模式，确认 ① 天气文字 ② 文章目录 ③ 系列目录
④ 评论正文 ⑤ 侧边栏标题 ⑥ 排行榜/相关文章链接 —— 六处均应清晰可读。

---

## R100 · v3.25.2 发版安全审查（备份自动巡检 + 评论嵌套修复 + 配置回滚）

**范围**：`backup.py` / `app.py`（调度循环）/ `api/posts.py` / `api/common.py` /
`audit.py` / `models.py` / `admin/settings.py` / 新增 `config_rollback.py` +
迁移 `c7a2f19b4d30` + 前端 `CommentForm.vue` + 3 个测试文件 + 4 份文档。

### 100.1 八维核对

| 维度 | 结论 |
|---|---|
| SQL 注入 | **未引入**。`sort` 走**白名单映射**（`_COMMENT_SORTS` 三键），用户输入只用于**字典查表**，不进 `order_by`、不进 SQL 字符串。守卫 `test_illegal_sort_falls_back_to_default` 用 `sort=created_at;DROP TABLE post` 实测。 |
| XSS | **未引入**。回滚差异页用 `<code>{{ c.key }}</code>` 等，Jinja2 autoescape 覆盖；配置值本身**不是脚本上下文**，且页面仅超管可见。 |
| 越权 | **两处新增特权操作**（`/admin/config-history`、`/admin/config-rollback/<id>`），均 `@super_required`——与「改设置」同级，不放给普通管理员。快照含配置全貌，泄露即等于泄露凭据。 |
| CSRF | **未绕过**。回滚走 POST + 全局 `{{ csrf_input() }}`；另加 `confirm=yes` 二次确认（覆盖当前配置属高破坏性）。 |
| 敏感数据 | **本版重点**。见 100.2。 |
| 资源耗尽 | **已设防**。①评论遍历用**显式栈 + `_COMMENT_MAX_WALK=24` 硬上限**，脏数据（`parent_id` 成环/超长链）不会打爆栈或响应；②快照 key 数上限 200；③巡检 `keep=3` 且后台异步（不占 gunicorn 并发槽，同 v3.23.0 #48）；④`per_page` 沿用原有 ≤50 收口。 |
| 限流 | **沿用**。评论接口原有 60/60s 未动；回滚走后台任务。 |
| 日志注入 | **未引入**。回滚审计的 `detail` 只含 key 名与数量，**不含值**。 |

### 100.2 敏感数据：本版的核心风险面

配置快照天然会碰到密码类配置，三条设计把风险压到最低：

1. **快照存 `Setting` 原始值，不解密**。`SENSITIVE_KEYS`（OSS SecretKey / WebDAV 密码 /
   SCP 私钥）落库时已是 Fernet 密文（`bkenc$` 前缀）。回滚是「把密文原样写回去」，
   **全程不接触明文**。守卫用 spy 替换 `decrypt_secret` 断言**调用 0 次**。
2. **`detail` 只写摘要、绝不写值**。`detail` 会进审计列表页、CSV 导出（`admin/stats.py`
   已有导出实现）、并显示在超管屏幕上 —— 把值写进去等于把凭据抄进一份
   **可导出、可截图**的日志。守卫 `test_detail_never_contains_values` 断言
   `detail` 里既无值也**无 key 名**（key 名清单同样会泄露配置全貌）。
3. **CSV 导出需注意**：`payload` 列是新增的，若日后把审计导出扩展到该列，
   快照（即使密文）也不该外泄。**当前导出未包含 `payload`，本版不需要改**，
   但已在代码注释里留档提醒。

### 100.3 本轮修掉的两个真问题（都是「静默失败」类）

- **`log_audit` 整条审计静默丢失**（既有缺陷，本轮暴露）：原先无条件
  `session.get("user_id")`，在**无请求上下文**（CLI / 定时任务 / 单元测试）时抛
  `RuntimeError: Working outside of request context`，而该调用位于**最外层 `try`** 内
  → 异常被 `except Exception: pass` 吞掉，**一条审计都没写且毫无迹象**。
  表现是「配置快照功能看起来完全失效」，根因却在审计函数。
  已加 `has_request_context()` 守卫 + 内层兜底（双保险），并加守卫锁行为。
- **门禁自身的错误断言**：`test_doc_archival.py::test_发版门禁仍认得归档件`
  断言「归档件必须在 `check-staged.py` 的 `DOCS` 必改清单里」—— 而那正是 v3.25.1
  判定为**错**的行为（归档件是历史快照，不该被迫每次发版都改）。
  已改为断言新行为（归档件**不**在必改清单 + 活的主文档仍在），守住「门禁别被改废」。

### 100.4 备份巡检的「假安全感」

巡检最容易做成一个**自我安慰**的功能。故三处刻意设计：

1. **「没有备份包」报 `empty` 而非 `ok`** —— 空目录不是「一切正常」，
   报 ok 会让运维以为「有备份且已验证」。守卫 + 变异验证。
2. **失败必须响**：`logger.error` + 状态文件标红 + 后台页红字，不静默。
3. **后台手动巡检也走异步任务** —— 同步读 3MB/包算 SHA256 会占住 gunicorn 并发槽。

另：巡检**只查最近 3 个包**。全量巡检会随包数增长线性占住定时线程，
而「最近 3 个能否恢复」已足够回答「备份机制是否还活着」。

### 100.5 表结构变更

`audit_log` 新增**可空列** `payload`（Text）。迁移 `c7a2f19b4d30` 幂等
（先 `inspect` 看列在不在，重复执行不报错）；`downgrade` **刻意不删列**
（SQLite DROP COLUMN 需 3.35+，且列里存着配置快照历史）。

**已用旧 schema 库真实演练**：手工造一个无 `payload` 列的 `audit_log` → 跑
`flask db upgrade` → 验证 ALTER 生效 + 历史审计行完好 + 历史行 `payload` 为 NULL。
⚠️ **只在新建库上验证等于没验证** —— 新建库走 `create_all()`，根本不经过 ADD COLUMN，
而生产升级走的恰恰是 ALTER 这条路。

### 100.6 验证与升级要点

**534 passed**（+23 条新守卫）/ ruff 全仓全绿 / `vite build` 成功 /
迁移演练通过 / **8 项变异全部精确变红**（备份 2 + 评论 2 + 配置 2；
另 1 项**等价变异**如实记录 —— 把 `if has_request_context():` 改成 `if True:`
测试不会红，因为两者在无上下文时都走内层 `except`，行为一致；未硬凑）。

**升级**：备份 → `flask db upgrade` → 重启。`update.sh` 一键完成。
迁移后 head = `c7a2f19b4d30`。上线后 checklist 见 `deploy_guide.md` 三项。

---

## R101 · v3.25.3 发版安全审查（SSL 证书到期监控）

**范围**：新增 `cert_watch.py`、`diagnostics.py`（+`check_certificate`）、
`app.py`（调度循环）、`tests/test_cert_watch.py`、4 份文档。**前端零改动**。

### 101.1 八维核对

| 维度 | 结论 |
|---|---|
| 信息泄露 | **关键设计**。全程只读 `notAfter` / subject / issuer，**不读取证书私钥**、不发送任何凭据。`verify_mode=CERT_NONE` 仅用于取回对端证书（只读 notAfter），**不构成 MITM 风险** —— 校验与否都不影响读取结果的真实性，因为我们要判断的正是「校验会不会失败」。 |
| 权限 | **踩过的坑**：宝塔 `fullchain.pem` 实测权限 `drw-------` / `-rw-------`（**root only**），gunicorn 以 `www` 运行 → **读文件必然 PermissionError**。故走 TLS 握手（`socket.create_connection` 到 443），**不需要任何文件权限**。 |
| SSRF | **无**。目标 host 来自 `site_base()`（管理员自己的配置），**不是用户输入**；固定连 443，6s 超时。 |
| 外部依赖 | 解析优先 `cryptography`（**可选依赖**），不可用时回退 `openssl` 命令行。两条路径都实测可用，**无硬依赖**。 |
| 资源耗尽 | TCP 6s 超时；每日最多一次；`openssl` 子进程 10s 超时。诊断页**读状态文件**而非现连（不能因握手卡住页面）。 |
| 注入 | 不涉及。解析库（`cryptography` / `openssl`）处理的是二进制 DER，非文本注入面。 |
| 越权 | 诊断页沿用既有 `admin_required`。状态文件落 `data/`（与其他状态文件同级），非敏感。 |
| 逻辑正确性 | 分级 `ok`/`warn`(≤30d)/`critical`(≤7d)/`expired`；**「没检查过」报 `never` → 诊断页 warn**（不报 ok）；连不上报 `unknown` **绝不报 ok**。 |

### 101.2 本功能最该防的失败模式：假安全感

一个「证书监控」最讽刺的失败方式是：**它显示一切正常，而证书已经过期**。
三处刻意设计专防此：

1. **「没检查过」≠「没问题」** —— 状态 `never` 在诊断页给 **warn**，
   与「没有备份报 `empty` 而非 `ok`」同源。
2. **连不上 ≠ 正常** —— 握手失败报 `unknown`（info 级但**不隐藏**），
   不伪装成 ok。
3. **域名不硬编码** —— 硬编码 `www.llhhy.cn` 在换域名后会连到旧域名，
   **一直报「正常」**。故取自 `site_base()`（全站唯一真相源），
   并有守卫 `test_target_host_from_site_base` 锁住。

### 101.3 测试方法与两次自我修正

**不 mock 解析函数** —— 本机**真起 TLS 服务**（openssl 自签证书 +
werkzeug `ssl_context`），跑完整握手 → 解析 → 分级路径，四种证书状态
（未过期 / 20 天 / 3 天 / 已过期）各一条。只测「读文件解析」等于没测生产路径。

修正一：**第一版 6 条随机失败** —— TLS 服务线程未进入 accept 循环就开始握手，
连接被拒 → `check_once` 吞成 `unknown` → 随机红。**flaky 测试比没有测试更糟**
（它会让人习惯性忽略红灯）。已在 fixture 加就绪轮询（探测握手成功才返回），
连跑 3 轮稳定。

修正二：**一条测试恒绿** —— `test_never_status_is_warn_in_diagnostics` 直接读
**真实**状态文件，而它已被同文件其它用例写成 `ok`，于是变异「never→ok」删了也不红。
已改为 monkeypatch `read_state`，并补 `test_expired_shows_error_in_diagnostics`
（锁 expired 必须是 error 级且给出续签指引）。

**变异验证 2 项全部精确变红**：①「已过期」误报 ok ②「never」在诊断页显示 ok。

### 101.4 验证与升级要点

**549 passed**（534 → 549，+16）/ ruff 全仓全绿 / **2 项变异精确变红**。
**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**（只改后端）。

**升级**：备份 → `flask db upgrade`（head 处无操作）→ 重启。
上线后 checklist：诊断页确认「SSL 证书」分组显示剩余天数
（首次需等每日定时任务跑一轮，`grep 证书监控 <log>` 可确认已跑）。

⚠️ **本功能只提醒，不续签** —— 证书签发涉及域名验证 / CA 授权，
**不是应用层该做的事**。续签入口：宝塔面板 → 网站 → SSL。

---

## R102 · v3.25.4（证书监控修正）· v3.25.3 自身缺陷的复盘

**性质**：这不是新功能，是**发版后立即修自己的 bug**。记录的重点不在改动本身，
而在**这个缺陷是怎么漏到生产的**。

### 102.1 缺陷

v3.25.3 上线后实测发现状态文件 `"host": "llhhy1"` —— 服务器名，不是对外域名。
根因：生产 `site_url` 未配置 → `site_base()` 返回空 → 原实现**回落到
`socket.gethostname()`**。

**为何当时「看起来正常」**：nginx 对 `llhhy1` 与 `www.llhhy.cn` 返回同一张证书
（实测均 `CN=llhhy.cn` / 12-01 到期）。但**多 server 块 + 多证书时，连本机名拿到的是
另一张证书，而监控会一直报「正常」** —— 这正是 v3.25.3 设计决定 ②（域名取自
`site_base()`、不硬编码）要防的「静默失效的假监控」，结果**从后门又开了一个**。

### 102.2 为什么会漏到生产（这才是重点）

写测试时**用 monkeypatch 绕过了 `site_base()`**，只构造了「有域名」的场景，
**没构造「域名取不到」的场景**。于是：

- 本地：18 条全绿
- 生产：`site_url` 是空的 → 走了没测过的分支 → 静默降级

**教训（可复用）**：**mock 掉一个关键依赖时，必须单独想一遍「它返回空值 / 抛异常 / 返回 None
时会怎样」**。这与 v3.25.1 修的 `title` 字段、`v3.25.2` 修的 `Post.body` 属同一类 ——
**接口的「空/异常」路径比「正常」路径更容易被漏测**，因为测试总是拿真实感的值去构造。

新增 3 条守卫锁住「空」路径：`_target_host()` 返回空串、`check_once()` 报 `unknown`
且不给出天数、`site_base` 抛异常时同样返回空。

### 102.3 为什么不升级为「阻塞」

修法本身很小（两个函数），但**真正的修复在代码之外**：`site_url` 本来就该配 ——
诊断页 `check_config` 一直在报「未设置 site_url」，它影响 sitemap/feed 绝对链接、
分享卡片、canonical。**证书监控只是这个老问题的又一个受害者**，不是独立的 bug。
故本条以「明确报错 + 引导配置」收口，而**不是**再加一层自动探测（比如猜 nginx 配置）。

### 102.4 验证

**552 passed**（549 + 3）/ ruff 全绿 / 变异「把本机名回落加回去」**3 条精确变红**。
**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

---

## R103 · v3.25.5（补上 `site_url` 配置入口）

**范围**：后台「站点设置」新增一个 `site_url` 输入框 + 保存前的清洗/校验
（`admin/settings.py::_normalize_site_url`）+ 两个模板改动。**不新增路由、
不新增表、不新增依赖、不新增环境变量**。

### 103.1 为什么这算安全项，而不只是「补个输入框」

`site_url` 是全站**对外声明的地址**的唯一真相源：

| 消费方 | 填错后的表现 |
|---|---|
| `og.py` canonical / og:url | 规范页指向别的域名 → 搜索引擎选错规范页 |
| `og.py` `/api/qr` 二维码内容 | 二维码把访客带到攻击者可控的 URL（R90 §2.9 遗留项的同一条链） |
| sitemap / feed 绝对链接 | 提交的 URL 集合整体漂移 |
| `seo_push` IndexNow `keyLocation` | 把 key 的存放路径告知别的域名持有者 |
| `mail_notify` 订阅邮件链接 | 邮件里的「阅读全文」指向外部 |

**共同点：全部静默** —— 没有一行会报错。所以它必须**在写入侧**拦住，
而不是指望每个消费方各自再校验一遍（事实上 `og.py` / `seo_push.py` 各有各的
局部校验，那是纵深防御，不能拿来替代入口校验）。

### 103.2 校验口径

只接受 `scheme://host[:port]`：

- **scheme 白名单** `http` / `https` —— 挡掉 `javascript:` / `data:` / `file://`。
  `file://` 尤其要挡：`seo_push` 的出站白名单是按 host 比对的，脏值会进 HTTP 层。
- **拒 path / query / fragment** —— 站点地址不是文章地址。带路径会让
  `abs_url()` 拼出 `https://a.com/blog/post/x` 这类错链。
- **剥 `userinfo`**（`https://u:p@host` → `https://host`）—— 站点地址不该含凭据，
  且凭据会被写进 sitemap / 邮件等对外可见的文本里。
- **尾部斜杠 / 前后空白**自动归一化，避免 `https://a.com/` 与 `https://a.com`
  在字符串比对时被判成两个站点（`og.py` 的允许源比对、`stats.py` 的自引用判定都靠它）。
- **端口非数字** → 拒绝（`urlparse().port` 会抛 `ValueError`，已捕获）。

### 103.3 失败语义（刻意设计）

- 校验不过 → **只跳过 `site_url` 这一个字段**，其余字段照常保存并 commit，
  然后 flash 明确提示「……（本次填写未保存）」。
  **不能因为一个字段填错就整张表单回滚** —— 那比不校验更糟（用户会以为全保存了，
  或以为全没保存，两种误解都会导致错误操作）。
- 清空 → 写 `""` = 显式「未配置」，`site_base()` 回落到环境变量再回落空串，
  **绝不回落到 `request.host`**（R102 已论证）。
- `site_url` 已随 `fields` 进入配置快照（`_snap_keys = list(fields) + [...]`），
  填错可从「配置变更历史」回滚 —— 补入口而不给回滚，等于只补一半。

### 103.4 越权 / CSRF / XSS 复核

- 路由仍是 `POST /admin/settings`，`@super_required` + 全局 CSRF，**权限口径零变化**。
- 模板里 `value="{{ settings.site_url or '' }}"` 走 Jinja 自动转义；
  提示段落里的 `{{ site_base_now }}` 同理 —— **没有 `|safe`、没有 `innerHTML`**。
- 不新增任何出站请求。

### 103.5 验证

**574 passed**（552 → 574，+22）/ ruff 全仓全绿 / **三项变异全红**：

| 变异 | 变红条数 |
|---|---|
| ① `_normalize_site_url` 取消全部校验 | 11（含端到端「非法值不得写库」） |
| ② `site_url` 不进 `fields`（保存被忽略） | 5 |
| ③ 输入框 `name` 改名（等同没有入口） | 1 |

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

### 103.6 遗留（不修，附理由）

- **`/api/qr` 在 `site_url` 未配置时仍用本次请求 host** —— R90 待办②，
  本次不动：入口补上之后它就有了正确的 `site_url`，回归二维码功能不宜夹进补丁版。
  若以后要收口，应改成「未配置则拒绝出图」而不是「回退请求 host」。
- **不自动探测 nginx 里的 `server_name` 来猜 `site_url`** —— 与 R102 §102.3 同一判断：
  猜错会让全站对外声明静默漂移，比明确报「未配置」危险得多。

---

## R104 · v3.25.6（上线核验收尾：sitemap 图片地址 / 时间口径 / site_url 即时重跑）

**范围**：`routes._sitemap_image_loc()`（新增纯函数）+ `sitemap()` 一处调用；
`cert_watch.check_once()` 两个时间字段；`admin/settings.py` 新增 `_trigger_cert_recheck()`。
**不新增路由、不新增表、不新增依赖、不新增环境变量。**

来源说明：这三条**不是设计评审发现的**，是 v3.25.5 上线后做**只读生产核验**时实测抓出来的。
功能写完不等于功能生效 —— 前两版都是发完即收工。

### 104.1 P1 · sitemap 的 `<image:loc>`

原实现 `if p.cover: extra += f'<image:image><image:loc>{escape(p.cover)}...'`，两个错叠在一起：

1. **规范错**：`cover` 的语义是**站内相对路径**（`og_image._local_cover_path()` 只接受
   `static/` / `uploads/` 前缀，外链一律返回 None），而 sitemap 的 `image:loc`
   **必须是绝对 URL** → 输出相对路径，搜索引擎拿不到图（静默失效，无人报错）。
2. **脏值**：生产有一篇 `cover` 存成字符串 `'None'` → 输出 `<image:loc>None</image:loc>`，
   是**无效的 sitemap 条目**。

**判据设计**（关键）：不是「猜脏值长什么样」（`'None'` / `'null'` 黑名单永远列不全），
而是**只放行站内相对路径** —— 与 `og_image._local_cover_path()` 同一口径。
这样任何非站内形态的历史脏值都被自然挡掉，无需枚举。

- **XSS**：仍走 `escape()`，无新增拼接面。
- **SSRF**：本函数**不发起任何网络请求**，只拼字符串。
- **信息泄露**：`site_url` 未配置时**返回空串不输出**，而不是拼半个地址 ——
  同 `site_base()` 的纪律（绝不猜域名）。
- **生产数据修正**：`post.cover = 'None'` → `''`（一条，单独执行）。
  写入侧现已是 `(x or "").strip()`，**未发现会再产生该值的现存入口**，
  故不加写侧防御（不为未发生的问题写代码）。

### 104.2 P2 · 时间口径

纯展示层，`checked_at` / `not_after` 改北京时间；`days_left` 计算仍用 UTC。
**无安全面**。风险点是**误读**：裸 UTC 的「上次检查」比现在早 8 小时，
容易被读成「监控没跑」—— 对监控类功能，误读成「没跑」和真没跑一样危险。

### 104.3 P3 · 保存 site_url 后立刻重跑证书检查（**本轮唯一新增动作面**）

**新增了一条由「保存设置」触发的出站连接**：`cert_watch.check_once()` 会连
`site_url` 的 443 做 TLS 握手。

- **为什么接受**：目标是**超管刚填的、且已通过 `_normalize_site_url()` 校验**
  （`scheme://host[:port]`，无路径无参数）的站点对外地址；动作只需 `@super_required`
  + CSRF。且握手只发 ClientHello、只取证书，**不发送任何数据、不读取响应内容**。
- **不做的边界**：端口**固定 443**（不是管理员可控的任意端口），
  所以不能当通用端口探测器用；不做重定向、不复用 HTTP 客户端。
- **失败语义**：`check_once()` 内部已有 try/except 并落 `unknown` 状态；
  外层再包一层 `logger.exception` —— 线程里的异常不记就等于静默消失（v3.19.1 的教训）。
  **绝不影响「保存设置」的结果**（旁路原则，同 `config_rollback.snapshot_settings`）。
- **只在值变化时触发**：每次保存都跑一遍没意义也白出网。

### 104.4 验证

**591 passed**（574 → 591，+17）/ ruff 全仓全绿 / **四项变异全红**：

| 变异 | 变红条数 |
|---|---|
| ① `_sitemap_image_loc` 退回「原样输出 cover」 | 9 |
| ② `checked_at` 退回裸 UTC | 1 |
| ③ `not_after` 退回 `" UTC"` 后缀 | 2 |
| ④ 去掉「保存后立刻重跑」 | 1 |

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

---

## R105 · v3.25.7（第三方登录配置页）

**范围**：新增 `admin/oauth_settings.py` + 模板 + 侧边栏入口；`oauth.py` 取值逻辑改造
（`Setting` 表优先、环境变量兜底）+ 新增 `callback_url()` 纯函数；
`api/auth.py::_oauth_redirect_uri` 改为复用它。**不新增表、不新增依赖、不新增环境变量、
不新增出站请求、不改前端产物。**

背景：这个功能**从 v3.21.0 上线起一次都没启用过**（生产实测 providers 空、
登录页 0 个 oauth 元素）—— 只有环境变量一个配置入口。本次补后台入口。

### 105.1 权限面

- 路由 `@super_required`（`abort(403)`）+ 全局 CSRF 钩子。
  **判据：改这里等于改「谁能登进这个站点」** —— 拿到 GitHub 凭据的人可以给自己的
  GitHub 账号授权后登录本站（虽然只能拿到自己的身份，但入口本身是身份入口）。
  守卫 `test_settings_page_requires_super` / `test_save_requires_csrf`。
- 侧边栏入口放在**超管区**而非「第三方绑定」旁 —— 后者对普通用户可见，前者不行。

### 105.2 密钥面

- **ClientSecret 用 Fernet 加密落库**（复用 `backup_settings.encrypt_secret`），
  与 IndexNow token / 备份密码同一套；页面只回显掩码，**留空 = 保持原值**。
  守卫 `test_secret_is_encrypted_at_rest`（断言落库值不出现明文、且带 `bkenc$` 前缀）。
- **审计只写 provider 名，绝不写值** —— `detail` 会进 CSV 导出。
  守卫 `test_audit_never_records_credential_values`（用 canary 串扫审计表）。
- **解密失败 fail-safe**：`decrypt_secret` 遇密钥轮换/篡改返回空串 →
  provider 被判「未配置」→ 按钮消失，**不会**拿垃圾值去请求 provider。

### 105.3 为什么 DB 优先于环境变量（取舍写下来）

老实现只有 env。新实现让后台可写，所以必须选一个优先级：

- **env 优先**：老部署零影响，但**后台改了不生效** —— 这正是「太难用」的根因之一，
  等于换了个更隐蔽的坑。
- **DB 优先**（选定）：与 `site_base()` / SMTP 设置同一语义，「后台能改」是本项目既定约定；
  且 DB 里是**密文**，即使 DB 泄露（SQL 注入）拿到的也不是可用凭据，
  而 env 是明文躺在进程环境里（同用户可读 `/proc/<pid>/environ`）。
  两者比较，**DB 优先 + 加密是更安全的那个**，不只是更方便的那个。
  老部署不失效：DB 没值时自动回退 env（守卫 `test_env_credentials_still_work`）。

### 105.4 XSS / SSRF

- **XSS**：模板里 `{{ r.client_id }}`、`{{ r.callback }}`、`{{ r.console_url }}`
  全部走 Jinja 自动转义，无 `|safe`、无 `innerHTML`。
  ⚠️ 特别注意 `{{ r.console_url }}` 进了 `href` —— 它来自 `PROVIDERS` 常量表
  （**代码里的固定值，不是用户输入**），常量表的 URL 不接受任何外部拼接。
- **SSRF**：本模块**不发起任何网络请求**。凭据只在下次有人点登录按钮时，
  由既有 `oauth.exchange_code()` 发往 `PROVIDERS` 里的**常量白名单**地址
  （且禁跟随重定向，R91 已闭环）。

### 105.5 已记录的不足（不阻塞，下次修）

- **ClientId / ClientSecret 长度无上限**。它们会进 authorize URL 的 query 与
  token 请求的 body。超长值不会造成注入（都经 `urlencode`），但会撑大请求行。
  建议下次加长度上限（ClientId ≤ 128、Secret ≤ 256）。
- **「三档状态」是展示层的诚实化，不是校验**：只填一半时后台显示
  「只填了一半 · 不生效」，但**不会阻止**保存 —— 阻止反而会打断
  「先填 ID、拿到 Secret 后再回来填」这种正常流程。

### 105.6 验证

**607 passed**（591 → 607，+16）/ ruff 全仓全绿 / i18n 通过 / **四项变异全红**：
`_cred` 不读库 → 4 条；Secret 明文落库 → 1 条；审计写凭据明文 → 1 条；
Secret 留空即清空 → 1 条。

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

### 105.7 微信登录：不做的理由（写下来免得反复讨论）

微信开放平台「网站应用」（PC 扫码登录）要求：**企业/组织/个体工商户主体** +
**300 元**资质认证 + 域名 **ICP 备案且备案主体与开放平台主体一致或有关联**，
回调域不能带协议头与端口。个人主体通过率极低 —— **这是平台规则，代码解决不了**。
公众号网页授权需**认证服务号**，个人订阅号无此权限。
`oauth.PROVIDERS` 是数据驱动的字典，将来拿到资质再加 provider 是几十行的事。

---

## R106 · v3.25.8（运营开关进后台 · 2FA 启用路径）

**范围**：新增 `utils.flag_bool()` / `flag_num()`；改 13 处开关读点（跨 8 个文件）；
新增 `admin/system_settings.py` + 模板 + 侧边栏；`twofa.html` 提示改文案。
**不新增表、不新增依赖、不新增环境变量、不改前端产物。**

背景：v3.25.7 修完第三方登录后，**同类投诉立刻出现在 2FA 上**。实测生产 env 只有
5 个变量、没有 `BLOG_TWOFA_ENABLED` → **2FA 从 v3.21.0 上线起一直是关着的**。

### 106.1 最核心的安全问题：**可配置 ≠ 该可配置**

一个「把所有 env 搬进后台」的补丁看起来很彻底，但**会引入真实的安全回退**。
本版明确划出三类**永不进数据库**的：

| 类别 | 变量 | 不进 DB 的理由 |
|---|---|---|
| **根信任** | `SECRET_KEY` `ADMIN_PASSWORD` `DATABASE_URL` `MCP_AUTH_TOKEN` `MCP_WRITE_TOKEN` | 存进 DB = 拿到 SQL 注入结果或一份备份文件的人，**顺带获得伪造任意会话 / 改管理员密码**的能力。这些变量躺在 env 文件里，而 env 文件**不在应用的数据面**上 |
| **每请求判断** | `COOKIE_SECURE` `CORS_ORIGIN` `TRUSTED_PROXIES` `SESSION_IDLE_MINUTES` | 每请求一次 DB 查询换一行配置，且这批参数本来就极少改 |
| **启动时读** | `ENABLED_PLUGINS` | 进 DB 照样要重启才生效；放后台只会给人「改了没用」的错觉 —— 那是比没有更坏的结果 |

判据写成可复用的两问：**运营会不会频繁改？× 读取频率多高？** 两个都高才进 Setting。

### 106.2 优先级方向的选择（不是随手定的）

`Setting 表 → 环境变量 → 默认`，DB **优先**：

- **env 优先**的话，后台改了不生效 —— 正是「太难用」的根因之一，等于换了个更隐蔽的坑。
- **DB 优先**且 DB 里**明文**（这些开关都不是密钥），与 `site_base()` / SMTP 设置同语义。
- 风险是「配了 DB 但某个读点还在读 config」→ 所以**每个读点都改**，
  且用**变异测试逐个确认**（见 106.4）。

### 106.3 一个容易写错的细节

`flag_num` 遇到 **DB 里的非法值**（如手填「不是数字」）时**继续往下走**（env → default），
而不是直接回落 `default`。理由：页面上显示「来源」标签走的是**同一个函数** ——
若非法值直接回落 default，页面会显示「来源：数据库」而实际生效的是默认值，
**标签与行为不一致**（v3.25.5 的 `site_url` 死胡同就是这类不一致的变体）。
继续下走则两者天然一致。

同理，页面**必须显示来源**（数据库 / 环境变量 / 默认）。只显示生效值的话，
运营改完发现没生效根本无从查起。

### 106.4 变异测试抓出的真实守卫漏洞（本轮最重要的一条）

第一次做变异时把 `app.py` 的 `enforce_twofa` 闸门退回成 `app.config.get("TWOFA_ENABLED")`
（即 v3.21.0 原行为），**测试全绿**。

- 原因：闸门在 `app.py`，开关判定在 `api/auth.py::_twofa_on()` —— **两处独立读点**，
  我最初的守卫只测了后者。
- **攻击者走的正是闸门**。`enforce_twofa` 是 `@app.before_request`，
  它一放行，后面所有 `login_required` 装饰器都形同虚设 —— 2FA 等于没有。
- 已补 `test_before_request_gate_actually_honors_the_switch`：造一个
  `UserTwoFactor(enabled=True)` 的用户，开关关 → 200；后台打开 → 页面 302 到 twofa、
  API 401 带 `twofa_required`；复位 → 200。重跑变异**精确变红**。
- ⚠️ 附带一条自我教训：第一次变异我写成 `if False: pass` 放在
  `v = get_setting(key)` **之后**，根本没断掉读库 —— 「没变红」是**变异无效**
  而不是守卫无效。**假阴性要当场识破**，否则会误判守卫有价值。

### 106.5 其余安全面

- **权限**：`@super_required` + 全局 CSRF。开 2FA / 强密码 / 关闭注册都属于
  「谁能进这个站点」的决定，**不能给普通管理员**。
- **审计**：记录**改动前后值**（`两步验证 False → True`）。这些开关都不是密钥，
  明文记值才能回溯「谁在什么时候把 2FA 关了」—— 反过来，**记了没有**才是隐患。
  守卫用 canary 串验证审计里不出现未预期的值。
- **越界值拒绝**：`audit_log_days=99999` 之类的输入被拒并提示，不会落库。
- **页面转义**：全部走 Jinja 自动转义，无 `|safe`（唯一例外是 `hint` 字段，
  它是**代码里的常量文案**，非用户输入）。
- **无新增出站请求、无新增依赖。**

### 106.6 验证

**625 passed**（607 → 625，+18）/ ruff 全仓全绿 / i18n 通过 / **三项变异全红**：
`flag_bool` 不查库 → 4 条；`before_request` 闸门退回读 config → 1 条；
保存不落库 → 4 条。

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**。

---

## R107 · v3.25.9（还清 lint 棘轮 + 把棘轮接进发版路径）

**性质**：**还债 + 机制修复**，不是新功能。**行为零变化** —— 34 处改动全是
`try/except Exception: pass` → `with contextlib.suppress(Exception):` 的等价转换。

### 107.1 先说清楚这不是「掩盖」

棘轮基线从 648 降到 490，是**真修完**之后锁定的。判断依据：

- 34 处 SIM105 的形态**逐条看过**（`ruff --diff`），确认是机械等价转换；
- 2 处 ruff 保守未改的（try 体带行内注释、在 `finally` 内）**手工改并注明原因**；
- **625 passed 与改动前完全一致** —— 这是等价性的主要证据。

与之相对的是「新增规则就先 `--update` 抬基线」，那才失去棘轮意义。

### 107.2 更重要的：门禁接进发版路径

`tools/review/check-staged.py` 新增第 5 步：**后端源码变更时自动跑
`tools/lint_debt.py`，新增债务列为 error（退出码 1 硬拦截），不是 warning。**

**为什么这是本轮真正的修复**：棘轮原本只是 CI 的一个 job，而 **CI 在发版之外**。
于是 v3.25.0~v3.25.6 期间的欠债（SIM +21 / BLE001 +9 / S110 +4）连续六个版本
被门禁放行，无人看见。**门禁不在发版路径上 = 等于没有门禁。**

已实测拦截：把基线人为压到 `SIM: 1` → 门禁**退出码 1**；还原 → **退出码 0**。

**这是「没验证」的第五次复发**（前四次：sitemap 脏值 / 证书时间口径 /
填完 site_url 不重跑 / 第三方登录从未启用 / 2FA 从未启用），五次同源于
「代码写了 ≠ 生效了 / 门禁写了 ≠ 跑到了」。

### 107.3 诊断过程（可复用的三步法）

1. **比 ruff 版本** —— 基线生成于 2026-09-23，当时 PyPI 最新版就是 **0.16.8**，
   与本地 venv 同版本；另在隔离 venv 装 **0.16.10**（CI 实际会装的）实测，
   SIM/S110/BLE001 数字**完全相同**（61 / 374）→ 否掉「版本扩容」。
2. **`git worktree add /tmp/x <基线commit>` 跑当时代码** —— v3.20.0 时点实测
   SIM=40 / ARG=10 / T20=66，与 `lint_debt_baseline.json` **完全一致**
   → 否掉「基线虚低」。
3. **逐文件 diff 定位增量来源** —— 最大头是 `tests/test_admin_table_data_label.py`
   独占 +11（v3.25.0 那次加的 121 处 `data-label` 测试），其余零散来自
   v3.25.2 / v3.25.3。

### 107.4 安全面复核

- **无行为变化**：等价转换，**不改变任何异常处理语义**
  （`contextlib.suppress` 与 `try/except: pass` 对控制流的处理一致）。
- **未引入新依赖**：`contextlib` 是标准库，`contextlib.suppress` 自 Python 3.4 起存在
  （项目要求 ≥3.10）。
- **性能**：无实质影响（渲染路径上多一个上下文管理器，对比 bleach 渲染可忽略）。
- **CI 仍不钉 ruff 版本**（`pip install ruff`）—— 本轮实测 0.16.8 与 0.16.10 数字相同，
  但**未来**版本可能变；已记入 ROADMAP 作为待办，不在本版改（改 CI 依赖会引入
  「本地过、CI 挂」的新不一致，需单独处理）。

### 107.5 验证

**625 passed**（与改动前一致）/ ruff 全仓全绿 / i18n 通过 /
门禁**拦截（退出码 1）与放行（退出码 0）均实测通过。

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**、
**对部署零影响**。

---

## R108 · v3.25.10（第三方账号绑定入口 · 顺手修掉静默身份切换）

**范围**：新增 `POST /admin/oauth/bind/<provider>`；`oauth_start` 加 `?redirect=1` 降级；
`oauth_callback` 按「是否为绑定流程」分流落点并 flash；**`oauth.find_or_create_user`
新增绑定冲突检测**；`oauth_bindings.html` 加绑定区块。
**不新增表、不新增依赖、不改数据层、不改前端产物。**

### 108.1 🔴 本轮修的存量缺陷：静默身份切换

原实现：

```python
link = OAuthAccount.query.filter_by(provider=provider, sub=sub).first()
if link:
    return db.session.get(User, link.user_id)      # ← 无条件返回那个人
```

**复现路径**：X 已登录 → 走 OAuth → 授权的第三方账号 G **已绑给 Y** →
`return Y` → callback 无条件 `session["user_id"] = u.id` → **X 的浏览器变成 Y**。

**为什么现在就修**：这条路径**在加绑定入口之前就能触发**（`oauth_start` 是 GET、
无 CSRF、任何人都能发起），但那时它属于边缘情况。加了「绑定」按钮后它会变成
**常见路径** —— 且从用户视角是「我明明绑自己的账号，怎么登录成了别人」，
完全不可接受。

**修法**：`(provider, sub)` 命中已有绑定、且**不是当前会话用户**时 → 抛 `ValueError`，
由 callback 转成明确提示（`该第三方账号已绑定到另一个用户`）而不是静默继续。

**危害评估（如实记录）**：攻击者**不获利**（他只是把受害者踢到一个账号上），
受害者损失的是自己的会话状态。所以定为「可用性 + 身份正确性缺陷」而非
「账号接管」。但**静默**是这里最糟的部分 —— 用户无法察觉发生了什么。

守卫：`test_binding_a_provider_owned_by_another_user_is_refused`，同时断言
①X 的 session 仍是 X ②原绑定未被改写 ③X 反而没被绑上。

### 108.2 绑定入口为什么必须是 POST + CSRF

真正的授权动作发生在 provider 那边（用户要点「授权」），所以单靠 GET 链接
**不足以被静默利用**。但绑定目标取自服务端 session 的 `user_id`——
做成 `<a href>` 就意味着：**任何人构造一个链接发给已登录用户，用户点一下就发起了一次绑定**。
即便 provider 侧还需要一次人工确认，也不该由站内给出这个入口。

故沿用项目既有口径（解绑、改设置同理）：**POST + 全局 CSRF 钩子**，
守卫 `test_bind_start_requires_post` / `test_bind_start_requires_csrf`。
**超管代他人绑定不提供入口** —— 没有正当场景，且它正是静默身份切换最容易发生的地方。

### 108.3 `oauth_start` 的无 JS 降级

第一版实现把绑定端点写成 `redirect(url_for("api.oauth_start", ...))`，
而 `oauth_start` **返回 JSON**（前端 `store.js` 消费 `authorize_url`）——
于是管理员点「绑定」会看到一片 JSON。改为加 `?redirect=1` 时直接 302，
**默认返回 JSON 的行为完全不变**（守卫 `test_start_without_redirect_param_still_returns_json`
专门钉住这一点，防止有人顺手把默认行为改了）。

### 108.4 其余安全面

- **权限分层**：未配置凭据时，超管看到「未配置 + 去配置 →」，
  普通用户只看到「站点尚未启用」—— 不把超管专属入口透给普通用户（守卫覆盖）。
- **解绑仍需密码**：本版**没有**放松解绑。它仍是「解绑后仍有可用登录方式」的证明。
- **`twofa_ok` 复位**：绑定成功时 `session["twofa_ok"] = False` 是**刻意**的 ——
  身份凭据刚变更须重新过第二因素。UI 明确告知「这不是 bug」。
- **信息泄漏**：绑定冲突的提示只说「已绑定到另一个用户」，**不透露**那个用户是谁。
- **异常收敛**：`ValueError`（用户可理解的失败）与其它异常分开处理，
  后者仍走 `logger.exception` + 通用 error，**绝不外泄 provider 原文/库结构**。

### 108.5 验证

**639 passed**（625 → 639，+14）/ ruff 全仓全绿 / 棘轮无新增 / **三项变异全红**：
绑定冲突检测被短路 → 1 条；绑定端点放开 GET → 1 条；绑定后不重定向回绑定页 → 1 条。

🔑 **门禁第一次真正咬人**：v3.25.9 才把棘轮接进 `check-staged.py`，
本版就被它拦了一次（新写的测试文件里一个没用的 `import time` → F401 → error）。
此前这种欠债要攒到下个版本才看得见 —— 这正是它攒了六个版本的原因。

**无表结构变更、无迁移**（head 仍 `c7a2f19b4d30`）、**前端产物无变化**、
**对部署零风险**。
