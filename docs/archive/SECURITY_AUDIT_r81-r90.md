# 安全审计报告 · 归档件（R81 ~ R90）

> **📦 这是归档件，不是当前文档。**
> 拆分点：从 `myblog/SECURITY_AUDIT.md` 拆出 **R81 ~ R90**（v3.18.0 ~ v3.19.0 期间的安全审计轮次），
> 归档于 v3.25.13 —— 主文件涨到 162 KB 触发了体积守卫（上限 160 KB），
> 按「新增轮次写进主文件、历史段落才归档」的原则搬到这里。
> **近期轮次（R91 起）仍在** [`../../myblog/SECURITY_AUDIT.md`](../../myblog/SECURITY_AUDIT.md)；
> 更早的 R1~R80 在 `SECURITY_AUDIT_r01-r80.md`。
> 内容逐字搬运，未作删改 —— 审计台账的价值在于「能查到当时发现了什么」。

---

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
