# 更新日志（CHANGELOG）

> **📦 历史归档**：v3.18.5 及以前 → `docs/archive/CHANGELOG_v1-v3.18.5.md`；
> v3.18.6 ~ v3.19.2 → `docs/archive/CHANGELOG_v3.18.6-v3.19.2.md`（v4.7.0 因体积守卫触发，按「新增轮次写进主文件、历史段落才归档」搬出）。
> v3.20.0 ~ v3.21.2 → `docs/archive/CHANGELOG_v3.20.0-v3.21.2.md`（v4.8.5 因体积守卫再次触发，按「新增轮次写进主文件、历史段落才归档」搬出）。
> v3.22.0 ~ v3.25.16 → `docs/archive/CHANGELOG_v3.22.0-v3.25.16.md`（v4.11.0 因体积守卫触发，主文件涨到 201 KB / 上限 200 KB）。
> 本文件从 **v4.0.0** 起。**归档不是删除** —— 查旧版本变更细节时去上述文件。

## v5.3.2（待发布 · /docs 代码块重做：语言标签栏 + 复制按钮 + 真高亮）

> v5.3.1 修好搜索/目录后，/docs 的代码块仍是「无设计 + 不高亮」：围栏没有语言标签、复制按钮漂浮在右上角、且因异步时序 bug，highlight.js 装饰的是空容器，真正的代码块从未被高亮。本次把代码块做成统一的「语言标签栏 + 复制按钮」深色块，并修好高亮时机。

### 改动内容

- **`vue-frontend/src/views/DocsView.vue`**：
  - 新增 `decorateCodeBlocks()`：在 `/api/docs` 内容注入 DOM 后，把每个 `<pre>` 包装成 `.code-block`（圆角深色容器 → `.code-block__bar` 语言标签 + 复制按钮 + `pre`），并真正调用 `hljs.highlightElement` 高亮。
  - **修时序 bug**：原 `tryHl()` 在 `onMounted` 立即跑，此时异步内容未到、装饰的是空容器；内容到达后 `v-html` 重建出新的 `<pre>`，再没人高亮 → 高亮形同虚设。现改由 `loadFullList()` 在 `buildToc()` 之后统一调用。
  - **修误上色**：无语言标注的围栏（目录树）显式标 `language-plaintext`，避免 highlight.js 退化成自动探测把目录树误判成 bash/python。新增 `plaintext`/`text` 语言注册。
  - 复制按钮从 `onMounted` 漂浮式改为落在标签栏内，样式走 `:deep()` 命中动态创建节点（同旧 `.copy-btn` 的坑）。
  - `API.md` 两处目录树围栏补 `text` 语言标注（原裸 ``` 无语言）。
- **`myblog/config.py` / `myblog/API.md`**：`APP_VERSION` 与文档头部版本号同步到 `v5.3.2`（守卫 `test_api_doc_sync.py` 强制一致）。

### 设计要点（为何如此）

- 代码块**刻意保持深底**不随明暗模式翻转：highlight.js 的 github-dark 主题要求深底，落在浅底上几乎不可读；统一深底是「文档代码块」最稳的观感。
- 标签栏显示的语言名取自后端 markdown 渲染出的 `class="language-xxx"`（fenced_code 扩展产物），与文档同源、无需前端硬编码。

### 实证（发版前本地验证）

- `npm run build` 通过；`tests/test_docs_codeblock_design.py` 守卫通过（含「源码含 `decorateCodeBlocks` + `.code-block` 结构」「`API.md` 无裸 ``` 围栏」变异验证）。
- 用真实 `render_markdown(API.md)` 产出 HTML，确认 `python`/`text` 围栏均带 `language-*` class；`decorateCodeBlocks` 命中后每个 `pre` 被包进 `.code-block`、标签栏显示正确语言名、复制按钮可用。

---

## v5.3.1（2026-10-30 · 修复 /docs 搜索与目录失效 + API.md 版本头补 bump）

> v5.3.0 把 `/docs` 改成渲染 `API.md` 后，搜索框和左侧目录同时失效：输入任何关键词都「没找到」、左栏空空、右侧「本节内容」也空。根因是建树逻辑写错，不是布局方向问题（BigModel 那种三栏范式本来就对）。

### 修复内容

- **`DocsView.vue` 建树逻辑（`buildToc`/`syncActive`）**：
  - 原实现在 h2 分支只 `subs.push`、**漏了 `links.push`** → 左栏接口链接数组恒空、搜索 `visibleSections` 永远 0 命中（即「没找到」）；
  - `sectionText` 的 key 错挂成 h2 id，而搜索查的是 h3 的 link id → 正文匹配也永远不中；
  - `syncActive()` 把 `activeId` 设成 `.doc-section` 容器 id（`full-list`）而非 h2 模块 id → 右栏「本节内容」恒空、左栏无高亮。
  - 修法：h2 分支 `subs`/`links` 都 push 同一组 h3；`sectionText` 改为 key=h3 link id、value=该模块整段正文；`syncActive` 改为跟踪 h2；左栏当前模块加 `.nav-section-active` 高亮。
- **`myblog/API.md` 头部版本号**：v5.3.0 发版时漏 bump，仍写 `v5.2.6`（被弱断言假通过）。本次补为 `v5.3.1`，并把版本断言收紧。
- **`tests/test_api_doc_sync.py`**：版本断言由「子串 `vX.Y.Z` in doc」升级为严格匹配头部 `> 版本：**vX.Y.Z**` 整段，杜绝假通过（v5.3.0 的坑）。

### 实证（发版前本地验证）

- `npm run build` 通过；`test_api_doc_sync.py` 5 passed；
- 用真实 `render_markdown(API.md)` 产出 HTML 忠实复刻建树：**30 模块 / 198 端点条目**，links/subs 非空；搜索 `mobile`→81、`/api/auth/me`→24、`rollback`→74、`slug`→140、`订阅`→112 命中。

### 新增发版纪律（已自动把关）

> 每次发版凡新增/修改接口，`API.md` 与前端 `/docs`（消费 API.md）必须同步；`API.md` 头部版本号须 bump。此纪律已由 `tests/test_api_doc_sync.py` 在发版全量 pytest 阶段强制（路由表 ↔ 文档条目 + 版本头双重断言），漏写会在测试阶段直接红。

无表结构变更、无迁移（alembic head 仍为 `b7c2e91a4d63`）。


## v5.3.0（2026-10-29 · RSS 订阅入口 + 写文章相册素材 + /docs 单源）

> 三个彼此独立的能力，统一进本次发版：① 给访客一个**明确的 RSS 订阅入口**；
> ② 写文章时能从**已发布相册**拉素材、把相册渲染成正文里的「打开相册」卡片；
> ③ 把 `/docs` 页从「第二份手写清单」改成**唯一数据源**（API.md）的消费者。

### 1. RSS 订阅入口（访客侧）

后端 `/feed.xml`（RSS 2.0）与 `/feed.atom`（Atom）两条路由**早已存在**（各取最新 20 篇公开文），
缺的只是「访客从哪点进去」。本次补的是**前端入口**，不动任何生成逻辑：

- 新增 `/feed` 订阅页（`SubscribeView.vue`）：并列列出两个源、一键复制地址、订阅步骤、
  以及「源里最近 5 篇」佐证源是活的；
- 全站入口两处：页脚「📡 RSS 订阅」+ 侧栏 RSS 小挂件（与邮件订阅并列，
  让访客知道「不想留邮箱也能订阅」）；
- **同源取址**：地址用 `window.location.origin + 路径`，不读后台手填的 `SITE_URL`——
  换域名 / 多域名时复制到的地址点开一定还是本站，避免硬编码域名在换域时静默失效；
- 语言键 `rss_*` 中英文齐全，i18n 无混排。

判据：两者都是 SPA 的 `/feed` 路由与后端的精确匹配 `/feed.xml` `/feed.atom` 并存，
**nginx 无需改动**（SPA 的 `/` fallback 只匹配不到精确路由时才生效）。

### 2. 写文章相册素材入口（编辑侧）

写长文配图时，作者常有「这张图在我某个相册里、又得去媒体库翻一遍」的摩擦。本次在
`edit_post.html` 编辑器加两个只读弹层：

- **🖼 从相册选图**：复用 `/admin/albums/media-picker`，新增 `album_id` 参数——
  传了就只返回该相册内素材，且**按相册内编排顺序**（而非素材创建时间）返回；
- **🔗 插入相册卡片**：复用新增的 `/admin/albums/picker-list`（含私密相册，
  作者自己看得到全部），往正文插一段 `@album[slug]`。

渲染侧（`utils/render.py` 的 `inject_album_cards`，在**正文缓存之外**注入）：

- 正文**独占一段**写 `@album[slug]`，渲染成一张「打开相册 →」链接卡片；
- 卡片 HTML **完全服务端生成**，标题/摘要/地点/封面 URL 一律 `_esc()` 转义，
  **不经过 bleach、也不扩大白名单**（作者不该拥有写 `<div>` 的能力）；
- **私密相册（is_public=0）不渲染**，整段移除 —— 公开文章引用私密相册时若吐出卡片，
  等于泄露「存在一个叫 X 的私密相册」；
- 放缓存之外而非 `render_markdown()` 内：改相册标题/封面时，引用它的文章缓存不必失效，
  卡片永远反映相册当前状态，真正的 CPU 大头（Markdown 渲染）仍命中缓存。

### 3. /docs 单源（消除两份清单漂移）

`myblog/API.md` 是**唯一权威**的接口清单（覆盖 176 条 `/api/*` + 17 条后台 JSON 接口）。
原先前台 `/docs` 是另一份**手写摘要**，改了 API.md 页面不跟着变（v5.2.5 之后实测「文档怎么没更新」）。

- 后端新增 `GET /api/docs`：读 `myblog/API.md` → 复用 `render_markdown`（markdown → bleach 清洗），
  按**文件 mtime + 大小**缓存，失败返回 `available:false` 而不让文档缺失变 500；
- 前台 `/docs` 页直接消费 `/api/docs`，删除约 520 行手写摘要段落；
- 配套 `docs/adr/ADR-001-docs-single-source.md` 记录这个决策与回退理由。

### 安全审计要点（本次改动）

- 全部查询走 SQLAlchemy 参数化（`like` 模式以绑定参数传递，无拼接 SQL）；
- `album_id` 经 `type=int` 强转；`picker-list` 与 `media-picker` 均 `@admin_required`；
- `/api/docs` 源路径写死为仓库内 `API.md`，无路径遍历、错误不回显路径；
- 编辑页弹层所有 innerHTML 拼接都对服务端数据走 `esc()`，且数据落点是 textarea `.value`
  （纯文本上下文，非 HTML）；`inject_album_cards` 全动态内容转义；
- 订阅页无用户输入、Vue 插值自动转义、取公开 `/api/posts`（服务端固定 per_page）。

## v5.2.6（2026-10-28 · v5.2.5 的视频播放按钮点不动 —— 元素查找写错）

> v5.2.5 上线后浏览器实测发现的**真 bug**：视频能正常加载（`readyState=4`、时长 7.8/8.6/8.7 秒
> 全部秒出），但**点播放按钮毫无反应** —— 不播、按钮不消失、原生控件也不出现。

### 根因：元素查找依赖了错误的 DOM 层级假设

```js
// ❌ v5.2.5 首版
function videoElOf(it) {
  const box = document.querySelector('[data-video-id="' + it.id + '"]');
  return box ? box.querySelector("video") : null;   // ← 恒为 null
}
```

模板里 `data-video-id` 挂在 **`<video>` 自己**身上：

```html
<video :data-video-id="it.id" ...></video>
```

所以 `querySelector('[data-video-id="7"]')` 命中的**就是那个 video 元素本身**，
它内部没有 video 子节点 → `box.querySelector("video")` **恒为 `null`** →
`playVideo()` 第一行 `if (!v) return;` 直接返回 → **点了没反应**。

### 修法：用 Vue 的函数式 ref 直接持有元素

```js
const videoEls = new Map();
function bindVideo(id, el) {
  if (el) videoEls.set(id, el);
  else videoEls.delete(id);
}
function videoElOf(it) {
  return videoEls.get(it.id) || null;
}
```

模板里 `:ref="(el) => bindVideo(it.id, el)"`（章节内 + 未分组两处都加）。
不再依赖 DOM 层级假设，也不受同名元素干扰。

### 为什么这个 bug 能溜过去（教训）

它的特征是**静默失败**：构建通过、测试全绿、页面能渲染、**视频甚至能正常加载**
（`readyState=4`、时长正确），**只有「点击播放」这一下没反应**。

🔴 **根因是我自己的验证方法有缺陷**：修复后我用一个**手写的探针页**验证，
把 `data-video-id` 挂在了**容器**上（`<div data-video-id><video></video></div>`）——
而真实组件挂在 `<video>` 自己身上。**探针页结构与真实组件不一致，掩盖了这个 bug。**

→ **通用教训**：验证前端交互必须用**真实组件**（或从真实组件产物派生的探针），
不能用「手写等价物」—— 后者的结构差异会让验证结果失真。
（同源教训：`tests/test_update_chain_contract.py` 里匹配 `cd "$WORK"` 时命中了
注释里的同名字样 → 判据必须**跳过注释行**。）

### 守卫（`tests/test_album_video_ref.py`，6 条）

1. 禁止「先按 `data-video-id` 找元素、再在它内部 `querySelector('video')`」的嵌套写法
2. 必须用函数式 ref 登记 video 元素
3. 两处 video 卡片（章节内 + 未分组）**都要**绑定 —— 漏一处那处就点不动
4. 不允许用 `querySelector('[data-video-id...]')` 定位元素
5. 播放按钮与 video 元素绑定**同一个** id 键
6. `videoElOf` 函数体内**不得出现任何 DOM 查询**（`querySelector` / `getElementById` /
   `closest` / `document.`）—— 它是所有播放逻辑的唯一入口

**变异验证**：把 `videoElOf` 改回旧写法 → 第 6 条变红；
改成 `document.getElementById` → 第 6 条变红；恢复后全绿。

### 兼容性

**无迁移**（head 仍 `b7c2e91a4d63`）、无新依赖、无新环境变量、无数据回填、
无后端业务代码改动（仅版本号）。**后端包与前端包都要覆盖**（本版改的是前端）。
安全审查见 `myblog/SECURITY_AUDIT.md` R157。

## v5.2.5（2026-10-28 · API 文档全量重写 + 视频一直转圈/悬浮挡页面）

> 用户反馈两条：「最近新增了很多接口，文档也要同步更新才行，现有的所有可用接口全部更新上文档」、
> 「视频展示有问题，前台也一样，点击加载视频就一直悬浮在最上层，还会挡住我看图片」。

### ① 视频一直转圈 + 点击后悬浮在最上层挡住页面

**根因分两层，都实测确认：**

**(a) nginx 把 `Range` 头剥掉了 → 视频没法流式播放**

宝塔全局 `/www/server/nginx/conf/proxy.conf` 里有 `proxy_cache cache_one;`（**http 级，全局生效**）。
nginx 启用代理缓存后，会**剥掉客户端的 `Range` 头**去拉完整对象。实测：

| 层次 | 带 `Range: bytes=0-1023` 的结果 |
|---|---|
| 直连 Flask（`127.0.0.1:8686`） | **206 PARTIAL CONTENT**，`Content-Range: bytes 0-1023/17628112` ✓ |
| 经 nginx | **200** + 整个 17MB ✗ |

而这三个 mp4 的 **moov 在文件尾部**（实测 `head moov = -1`），浏览器要读到时长/首帧
就必须拿到尾部 —— 没有 Range 就只能**把整个 17MB 下载完**。三个视频 = 一进页面 57MB。
所以视频一直转圈、`duration` 读不出来（实测 `readyState=0`）。

**修法（改生产 nginx 配置，已授权、已备份、已 reload）**：
1. 新增 `location ^~ /static/uploads/`，用 `root` 让 **nginx 直接 serve** ——
   Range 原生支持 + sendfile 直读，视频**不再占 gunicorn worker**（生产只有 2 核 4 worker）；
2. 现有 `location ^~ /static/` 加 `proxy_cache off`，让 Range 正常透传给 Flask。

**修复后实测**：经 nginx 带 Range → **206**；三个视频 `readyState=3`、
时长 7.8 / 8.6 / 8.7 秒、分辨率 1080×1920 全部正常读出。

**(b) 点视频触发移动端原生全屏接管 → 浮层挡住整页**

`<video controls>` 在 iOS Safari / 微信内置浏览器里，用户点一下就被系统接管成
**原生全屏播放器**（一层盖在整页上的系统浮层），退出后部分浏览器还会把 video
元素留在视口顶层继续挡着内容 —— 这正是「悬浮在最上层、挡住看图片」。

**修法（前端）**：
- 前台相册页：**去掉原生 `controls`**，改成**自绘播放按钮**。用户点的是普通按钮，
  JS 再调 `video.play()`；因为有 `playsinline`，这次调用走**内联播放**，不触发系统全屏接管。
  真要全屏时，播放中才把 `controls` 挂上，用户可在控件里自己选。
- 后台两处（媒体库缩略图、相册编排页缩略图）：`pointer-events: none` ——
  缩略图不该可点，点了就是误触全屏。

**竖屏视频的观感**：1080×1920 的竖屏片放进 4:3 横格，左右必然留边。
原来留的是纯黑 `#000`，看着像破图；改成卡片同色的中性底 + 居中的圆形播放按钮。

### ② API 文档全量重写 + 同步守卫

`myblog/API.md` 停在 v3.6.0，而代码已有 166 条 `/api/*`（含插件 4 条共 176 条）
+ 17 条后台 JSON 接口，新增的十几个模块（相册/媒体/AI 摘要/生态/分享卡/表情/读者/
回顾/主题/插件）**一条都没进文档**。改法不止是补写：

1. **清单从代码枚举**，不靠人工回忆；
2. **逐条回源码核对**鉴权级别、请求参数、返回字段、错误码，顺带纠正旧文档里
   **10 处与源码不符**的描述（详见下方「顺手纠错」）；
3. **写进守卫测试**（`tests/test_api_doc_sync.py`，5 条）：以后新增接口忘了写文档、
   或者删接口忘了删文档，**测试立刻变红**。

### 文档结构

| 章节 | 条数 | 说明 |
|---|---|---|
| 通用约定 | — | 重写：补上 2FA 闸门、反爬闸门、错误信封表、分页口径差异表 |
| 认证与验证码 /auth | 17 | 含 OAuth、两步验证、验证码 |
| 站点信息 /site | 4 | |
| 文章 /posts | 17 | |
| 统计 /stats | 8 | 标注了哪几条**会写库** |
| 社交广场 /social | 6 | |
| 专题 /series | 2 | |
| 留言墙 /guestbook | 3 | |
| 邮件订阅 /subscribe | 2 | |
| 站内通知 /notifications | 3 | |
| 移动端管理 /mobile | 74 | 按功能分组，标出「按对象归属分权」的接口 |
| 相册 /album | 2 | 新增 |
| 公开媒体 /media | 3 | 新增 |
| AI 摘要 /ai | 2 | 新增 |
| 生态统计 /ecosystem | 2 | 新增 |
| 分享卡与爬虫通道 /og | 4 | 新增 |
| 列表页壳页 /og/page | 1 | 新增 |
| 天气 /weather | 1 | 新增 |
| 评论表情 /reactions | 2 | 新增 |
| 读者积分 /reader | 2 | 新增 |
| 回顾与地域 /review | 4 | 新增 |
| 主题中心 /theme | 2 | 新增 |
| 插件 /plugins | 4 | 新增 |
| 系统与版本 /system | 5 | |
| 后台 JSON 接口 /admin | 17 | 新增（含分块上传四件套） |

### 顺手纠错（旧文档与源码不符的 10 处）

| 接口 | 旧文档 | 源码实际 |
|---|---|---|
| `GET /api/posts` | 支持 `per_page` 参数 | 每页取服务端配置 `POSTS_PER_PAGE`（默认 8），**不接受该参数** |
| `GET /api/categories` / `GET /api/tags` | 返回项含 `id` | 只有 `name / slug / count` |
| `GET /api/hot-tags` | 裸数组 | `{"items": [...]}` |
| `GET /api/archive` | `{"year": 2026, "months": [{"month": 1, "count": 3}]}` | `{"year": "2026", "months": [{"month": "01", "posts": [<文章卡片>...]}]}` |
| `GET /api/post/<slug>` | `{"post": {...}, ...}` | 文章字段**平铺在顶层**，另加 `html / comments / series / translations` |
| `GET /api/post/<slug>/related`、`/also-viewed` | 裸数组 | `{"items": [...]}` |
| `POST /api/post/<slug>/like` | 支持 `{"unlike": true}` | **只支持加**，无取关参数 |
| `POST /api/post/<int:post_id>/publish-now` | 鉴权「超管」 | 登录 + 对该文有编辑权（普通用户仅能操作自己的文章） |
| `GET /api/announcements` | 裸数组 | `{"items": [...]}`（含 `level` / `dismissible`） |
| `GET /api/captcha/config` | `global_enabled` / `pil_available` | `enabled` / `available` / `scenes` |

另修：CSRF 失败文案、CSRF 豁免白名单（漏了 `/api/ecosystem/heartbeat`）、
`/api/mobile/*` 5 条接口实际同时支持 `POST` 与 `PUT`（旧文档只写 POST）、
分块上传的内容字段名是 `chunk`（不是裸字节）。

### 守卫测试（`tests/test_api_doc_sync.py`，5 条）

1. `test_所有真实接口都在文档里` —— 真实路由 ⊆ 文档条目（防**漏写**）
2. `test_文档里没有已废弃的接口` —— 文档条目 ⊆ 真实路由（防**留残骸**）
3. `test_文档目录锚点全部有效` —— 目录里 28 个锚点必须都指向真实章节（防死链）
4. `test_文档版本号与代码一致` —— 文档头版本 == `APP_VERSION`
5. `test_文档文件存在`

**插件路由的特殊处理**：`load_plugins()` 在 `PLUGINS_DIR` 不存在时直接 return，
`plugins_bp` 从未注册 —— 测试环境通常没有插件目录，光靠 `app.url_map` 会漏掉这 4 条，
导致「文档写了接口、代码里找不到」的常态性假失败。故用**独立探针 app** 注册同一个蓝图
取它自己的 url_map，与运行环境无关。

### 前台文档页同步（`vue-frontend/src/views/DocsView.vue`）

修了 3 处与源码不符的约定文案：CSRF 豁免白名单、分页口径（并非所有列表都支持 `per_page`）、
限流阈值（登录/注册是 10 次/分不是 5；前台微动态 20 次/分，5 次/分的是 App 端）。

### 打包前漏洞审查（R156）

定稿后做了一次**独立复核**（不是增量续写），并且**首次把「生产 nginx 配置」
纳入审查范围**（前几版只审代码，没审过生产配置）。

**静态分析工具报的 7 条 Critical，逐条回源码验证后全部为误报**：
「硬编码密钥」判据无法区分**键名映射表**与真密钥（`BACKUP_OSS_SECRET` /
`oauth.*.client_secret` 都是键名，真值走环境变量 / Setting 表）；
「SQL 拼接」判据无法区分**拼接常量**与拼接用户输入（两个 migrate 脚本拼的是
模块内写死的 dict）。

**真正审的是 nginx 直出的攻击面**（逐项实测，非推断）：

| 攻击面 | 实测 | 结论 |
|---|---|---|
| 路径穿越读源码 | `/static/uploads/../../config.py` → 200，但返回的是 **SPA 首页 HTML**（`grep APP_VERSION` 命中 0）；越界读 `.env` / `requirements.txt` → 404，`/etc/passwd` → 400 | 无源码泄露 |
| 上传 SVG → 存储型 XSS | 实测**若能落盘就会执行**（直出返回 `image/svg+xml`），但上传链三道闸门在**落盘前**拦住：① `kind_of()` 扩展名白名单（不含 svg/html）② `validate_magic()` 复核文件头 ③ `nosniff` | 走不进来 |
| 目录列举 / 子目录 | `autoindex` 未开 → 403；uploads 内无子目录 | 安全 |
| 误改全局配置 | 未改（全局 `proxy_cache cache_one;` 原样，只在站点 conf 加了 `proxy_cache off`） | 其它站点不受影响 |
| 可回滚 | 备份 `html_www.llhhy.cn.conf.bak_v5255_20261028_215636` 在位 | 有 |

**遗留观察项（非漏洞）**：直出资源没有 CSP（Flask 侧有）。判定可接受 ——
CSP 约束的是文档上下文，而图片/视频响应本身不是文档；**但若将来放开 SVG/HTML
上传，必须同步在 nginx 侧加 `Content-Disposition: attachment`**。

### 兼容性

**无迁移**（head 仍 `b7c2e91a4d63`）、无新依赖、无新环境变量、无数据回填。
除视频卡片（`AlbumView.vue` / 两个后台模板）与前台文档页文案外**无业务代码改动**。
安全审查见 `myblog/SECURITY_AUDIT.md` R154、R155、**R156**。

### 远端分支清理（同批处理）

关闭了 5 个 dependabot 自动开的依赖升级 PR（#29~#33）及其分支 —— 远端现在只剩
`main`。逐项核实后确认关闭无实际损失：
`cryptography` 50.0.2 **只改了 wheel 的 OpenSSL 版本、无安全修复**（CVE-2026-69247
已被服务器上的 50.0.1 消化）；`markdown` 3.11.2 是 patch（下次扫描会重新提出）；
`gunicorn` 22→26 / `vite` 6→8 / `vue-router` 4→5 是**未经生产验证的大版本跳跃**
（其中 vue-router 的 CI build 还是失败的），按仓库既定策略「机器提议、人工裁决」关闭。

## v5.2.4（2026-10-28 · 属主探测把 4 个 worker 的用户名拼成一个 → 全部静默降级为 root）

> v5.2.3 上线后从部署日志里发现的**第二个真缺陷**：v5.2.3 修好的「探测 worker 属主」
> 拿到的却是一个**不存在的用户** `wwwwwwwwwww`。

### 根因：`tr -d '[:space:]'` 把换行也删了

```bash
APP_USER_FINAL=$(ps -o user= --ppid "$pid" | tr -d '[:space:]' | head -1)
```

`ps -o user= --ppid $pid` 返回的是**每个子进程一行**（4 个 worker → 4 行 `www`），
而 `tr -d '[:space:]'` 会把**换行符也一并删掉** → 4 行拼成 `wwwwwwwwwww`（13 个字符）。

### 后果：静默降级（比直接失败危险得多）

- `run_as` 每次都报「用户 wwwwwwwwwwww 不存在，以当前身份执行」→ **全部以 root 跑**；
- `chown` 全部失败（用户不存在）→ 属主校正形同虚设；
- 但部署日志**仍然显示「✅ 全部完成」** —— 表面成功，实际文件属主成了 root。

本次实测：5 个业务文件 + 3 个模板 + 29 个 `__pycache__/*.pyc` 变成 root:root。
站点当时仍正常（读权限够），但这正是 v5.2.2 那次 `data/upload_tmp` 事故的同一个病根
——「属主错位」会**在下一次需要写文件的操作上才爆出来**。

### 修法（三层）

1. **先 `head -1` 再去空白**（顺序反了才是 bug 本身）；
2. **校验探测结果是真实存在的用户**（`id "$APP_USER_FINAL"`），无效则作废并继续兜底链；
3. 其余 `ps` 读取一律统一补 `head -1`，防同类问题复发。

### 线上已修正

本次部署后已手工把 root 属主的文件全部 chown 回 `www`（含清理 root 生成的 `.pyc`，
移到 `/tmp/pycache_root_20261028/` 保留回滚），`data/backup/` 按设计**不校正**。

### 验证

- `tests/test_update_chain_contract.py` **11 passed**，新增 1 条：
  `test_属主探测不会被多行输出拼坏` —— 断言 ① 多行 `ps --ppid` 必须先 `head -1`
  （只查代码行，跳过注释）；② 探测结果必须校验是真实用户；
  ③ 其余 `ps -o … -p` 读取也统一 `head -1`。
- `bash -n update.sh` 通过。

### 兼容性

**无迁移**（head 仍 `b7c2e91a4d63`）、无新依赖、无新环境变量、无数据回填。
安全审查见 `myblog/SECURITY_AUDIT.md` R153。

## v5.2.3（2026-10-28 · 部署脚本自更新认不出自己 → 脚本类改动送不到服务器）

> v5.2.2 上线时从部署日志里发现的**真缺陷**：本版承诺的「属主探测改看 worker」
> 与「部署后校正 data/ 属主」两项 `update.sh` 改动**根本没送到服务器**。

### 根因：`cd "$WORK"` 之后才算自己的路径

`update.sh` 第 80 行会 `cd "$WORK"`（切到 `/tmp/llhhy_update`），
而自更新函数 `self_update_check()` 用 `readlink -f "$0"` 判断「当前运行的是不是
规范路径 `$APP_DIR/update.sh`」。

用**相对路径**调用时（`cd /www/wwwroot/myblog && bash update.sh`），
`$0 = "update.sh"`，`readlink -f` 在**已经被 cd 改掉的 cwd** 下解析 →
得到 `/tmp/llhhy_update/update.sh` ≠ 规范路径 → 脚本判定
「当前运行的不是 update.sh，不自动替换」，**拒绝自更新**。

后果：线上 `update.sh` 永远停在旧版，**所有脚本类改动都不会生效**。
本次日志里只有一句「请手动更新该文件」——不盯着看会以为已经更新了。
（后台「立即更新」按钮传的是绝对路径，所以平时不触发；手动 `cd` 后执行就中招。）

### 修法

在任何 `cd` 之前先把 `$0` 解析成绝对路径存进 `SELF_PATH_ABS`，自更新判据一律用它；
`readlink -f "$0"` 保留为兜底分支。

### 顺带

本次部署还发现并修掉了 v5.2.2 引入的另一个自伤：`fix_data_owner()` 会对
`data/` 整棵 `chown -R`，而 `data/backup/` 下是**历次部署的备份**（属主可能是 root），
会被一起改写。现改为只校正 `data/` 下的**业务目录**，不动 `backup/`。

### 验证

- `tests/test_update_chain_contract.py` 新增 1 条守卫：
  `SELF_PATH_ABS` 必须在行首 `cd "$WORK"` **之前**捕获（用行首正则匹配，
  避免误匹配注释里的同名字样），且自更新判据必须优先用它。
- 线上实测：改完后自更新日志出现「✅ 脚本已是最新（与 v5.2.3 一致）」，
  说明脚本能正确认出自己并完成替换。

### 兼容性

**无迁移**（head 仍 `b7c2e91a4d63`）、无新依赖、无新环境变量、无数据回填。
安全审查见 `myblog/SECURITY_AUDIT.md` R152。

## v5.2.2（2026-10-28 · 编辑器被圆角裁掉 / 选图格子被压扁 / 大文件上传 500）

> 用户反馈三条：「倒圆角之后写文章页编辑功能显示不全」、
> 「手机端上传和选图时已上传的图片堆叠在一起，很容易选错」、
> 「视频和图片一起上传会报 `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`」。

### ① 编辑器工具栏被裁掉：状态类被当成按钮类

观感层里有一条给视图切换按钮加药丸圆角的规则：

```css
.view-split, .md-vw { border-radius: 999px; overflow: hidden; }
```

而编辑器的容器 class 是 **`md-stage view-split`** —— `view-split` 是**视图状态**，
不是按钮。于是整个 62vh 高的编辑器被设成 999px 圆角，浏览器把半径压到高度的一半，
工具栏左右各几百 px 落进圆角裁切区，「B」「粗体」和右侧的「分栏/仅编辑/仅预览」
全部看不见。

修法：这条规则只留给 `.md-vw`；`view-*` 只做后代选择器（`.view-edit .md-body`）。

### ② 选图格子被压扁：grid 行高按 min-content 算

手机端选图弹层一屏 8 张，每张只露出上半截、下半截被裁掉，看起来「叠在一起」。

根因不在 `aspect-ratio` 本身，而在 **行高**：
`.album-picker-grid` 用 `grid-auto-rows: auto`，而格子高度来自 `aspect-ratio`——
它在 min-content 计算里算不出值，四行于是均分容器、每行只剩 **85px**（实测），
`overflow: hidden` 把图裁成一条条。改 `aspect-ratio`、把 button 换成 div，全都没用。

修法三道：`grid-auto-rows: minmax(96px, auto)` 给不依赖比例的确定下限；
`gap` 8→10px 拉开间距；**每格压一条名字**（`media.title`），
因为一屏七八张风景照只靠画面根本分不清哪张是哪张 —— 这才是「容易选错」的正解。

### ③ 大文件上传 500：`data/upload_tmp` 属主是 root

`>16MB` 的文件走分块上传，要写 `data/upload_tmp`。这个目录由 `config.py` 在
**import 时** `os.makedirs()` 创建；而 `update.sh` 探测运行属主时看的是 gunicorn
**master**（root），可实际接请求、写文件的是**worker**（www）。
于是目录建成 `root:root 755`，www 写不进去 → `PermissionError` → Flask 返回 **500 HTML**
→ 前端 `r.json()` 抛 `Unexpected token '<'`。图片（≤16MB 走单请求）一切正常，
唯独视频必炸 —— 这就是「视频和图片一起上传才触发」的原因。

四处一起改：

1. **线上立即恢复**：`chown -R www:www data/upload_tmp`（已执行并实测分块初始化通过）；
2. `media_service.chunk_init` 把 `OSError` 翻成 `MediaError(507)`，前端拿到的是
   「服务器无法写入上传临时目录…」而不是 500 HTML；
3. `album_edit.html` 的上传链路统一走 `readJson()`，非 JSON 响应翻成人话
   （413 / 会话失效 / 502 分别提示），不再把 `Unexpected token '<'` 甩给用户；
4. `update.sh`：属主探测改为**取 master 的子进程（worker）**，取不到再退回
   blog.db 属主；并在迁移后新增 `⑤c 校正 data/ 属主`，每次部署顺手纠一次 —— 只改属主，
   不动内容与权限位。

### 影响面

- **无表结构变更**：Alembic head 仍 `b7c2e91a4d63`。
- 无新依赖、无新环境变量。
- `update.sh` 有改动 → 本次部署需设 `GH_MIRROR`（服务器直连 `raw.githubusercontent.com` 被重置，脚本自更新会跳过）。

## v5.2.1（2026-10-28 · 相册封面与名字同步修复）

> 用户反馈两条：「相册里改了文件名称之后呢，媒体库的名称不会跟着改」、
> 「设置好封面之后返回相册管理页面，然后还是显示无封面」。

### ① 封面永远显示「无封面」（确定性 bug）

`album_list()` 取封面时写的是：

```
ids = [a.id for a in rows if a.cover_media_id]      # 相册 id
MediaAsset.query.filter(MediaAsset.id.in_(ids))     # 当媒体 id 用
```

相册 id 与媒体 id 是**两套自增序列**，除偶然相等外一定查不到 →
`covers.get(a.cover_media_id)` 恒为空，列表页永远「无封面」。
改成 `a.cover_media_id` 即可。

判据不是「页面上有没有图」，而是**两者错开**时还取不取得到：
测试刻意让相册 id=1、封面媒体 id=2，旧写法必红（已做变异验证）。
顺带把编辑页 `cover_url` 的「条件里查一次、取值再查一次」合成一次查询。

### ② 名字只能有一份（设计修正）

v5.2.0 把图注（`album_item.caption`）设计成「相册语境的说明」，与素材标题并存，
靠展示层回退避免重复填。**但用户不认这个区分** —— 在相册里起了名，
回媒体库还是一串 `1000142174_1_1_7212616`，「改一处、另一处不动」又变成两份要维护的数据。

v5.2.1 起：

- 名字只存在 `media_asset.title`。编排页输入框直接写它，**改这里 = 改媒体库标题**；
- 媒体库改标题，编排页与前台立刻跟着变（读同一份，不是副本）；
- `album_item.caption` **冻结不再写入**（列保留，不改表结构）；旧页面（浏览器缓存未过期）若仍发 `caption` 字段，也落到素材标题上，避免从缓存页面长回两份；
- 迁移 `b7c2e91a4d63` 把历史 caption 合并进素材标题并清空。
  **覆盖规则是 caption 覆盖 title** —— 用户抱怨的正是「相册里改的名字媒体库不认」，
  若反过来保留 title、丢掉 caption，现象与修复前一模一样。
  生产实测一例：`潮州1` → `意溪渡口`（只换不删，且那正是他最后写下的名字）。

代价（明确承认）：同一张图不能在不同相册有不同说明。真要做那个场景，
应该另加一个可选字段，而不是让主名字分叉。

### 影响面

- **无表结构变更**：Alembic head 变为 `b7c2e91a4d63`（仅数据迁移）。
- 无新依赖、无新环境变量。
- 部署时 `flask db upgrade` 自动跑合并，无需手工回填。

## v5.2.0（2026-10-28 · 媒体库与相册双向打通）

> 用户反馈：「媒体库和相册可以融合一下，太难用了，总是在不同页面切来切去」。
> 补充约束：「有一些多余的信息就不要总是重复填，直接引用就行」。

### 问题在哪：上传与编排被拆在两个页面

加照片的实际路径是：

```
相册页 → 媒体库 → 上传 → 回相册页 → 打开选择器 → 找到刚传的那张 → 勾选 → 加入
```

两侧能力是互补而非重叠的：**上传只在媒体库**（相册的选择器里没有任何上传入口），
**编排只在相册页**（媒体库不知道这张图进了哪个相册，所以会重复挑同一张）。

### 改了四处

**① 相册编排页可直接上传并入册**
选择器顶部加「📤 上传并加入」：选文件（支持多选）→ 上传 → 自动落到「加入章节」
下拉选中的位置 → 刷新。沿用媒体库同一套接口（单请求 + 分块三件套），
阈值也取同一个配置项 `UPLOAD_SINGLE_SHOT_MAX`，避免两处各写一套、日后改一边忘另一边。

**② 媒体库每张素材可「加入相册」**
卡片操作区加「➕ 相册」→ 选相册（章节可选，随相册切换）→ 确定。**不填任何字段**。
成功后**就地补一个标签、不刷新页面**，方便连续给多张图加同一个相册。

**③ 媒体库显示素材归属**
每张素材下面显示「📚 相册名」标签（点击跳转编排页），没有归属的显示「未加入任何相册」。
后端用**一次聚合查询**（`AlbumItem join Album`，按 media_id 归组）算出归属，避免逐行查（N+1）。

**④ 图注留空即引用素材标题（核心：不重复填）**
`AlbumView.vue` 新增 `capOf(it)`：`caption || media.title`。
也就是说同一张图在媒体库叫「梯田晨雾」，编进相册时**不必再抄一遍**；
只有这个相册需要不同说法时才填 caption。纯展示层回退 —— 不写库、不复制，
**媒体库改了标题，前台相册会跟着变**。
后台编排页的图注输入框 placeholder 会直接显示「留空即显示「梯田晨雾」」，
把「不填也有内容」这件事变得可见。

### 刻意没做的事

- **没有把两个页面合并成一个**。用户原话是「融合」，但媒体库承担的是「素材总览 +
  存储设置 + 磁盘同步」这些**维护性**职责，塞进编排页会让日常写相册的路径变重。
  真正要消灭的是「为了加照片而跳页」，不是页面数量。
- **没有在加入相册时弹表单**。标题、日期、地点、图注全都可以后填，加进去就是加进去。
- **没有给 `caption` 做「回填」到素材标题的双向同步**。那会让「同一张图在两个相册
  不同说明」失效，也会产生两处都能改、谁覆盖谁的歧义。

### 影响面

- **无迁移**：Alembic head 仍 `a1c9e4f72b38`。**无新依赖、无新环境变量、无数据回填。**
- 新增路由 `POST /admin/media/<id>/to-album`（管理员）。
- 改动文件：`admin/media.py`、`admin/album.py`、`templates/admin/media_lib.html`、
  `templates/admin/album_edit.html`、`static/admin.css`、`views/AlbumView.vue`。

### 验证

- `tests/test_album.py` **19 passed**（新增 5 条）：
  媒体库页面显示归属、加入相册成功且 `caption` 必须留空、跨相册章节必须拒绝、
  相册不存在返回 404、详情接口带出 `media.title` 供前端回退。
- **变异验证**：把 `caption=""` 改成 `caption=(m.title or "")`（典型的「重复填」实现）
  → 立即变红：`AssertionError: caption 必须留空（前台回退显示素材标题，不复制）`。
- 全量回归见下。

### 顺手修的一处测试互扰

新增的「媒体库页面」测试会让 `collect_media()` 的 60 秒磁盘同步节流被消耗掉，
导致随后 60 秒内手工写进 uploads 的文件不登记，打挂
`test_api_mobile.py::test_媒体库删除需_force_且路径穿越无效`（实测 `StopIteration`）。
在 `test_album.py` 加了 autouse fixture，每条测试后清零 `_SYNC_AT` —— 谁污染谁清理。
**这不是线上缺陷**：正常上传走 `save_single()` 直接登记，不依赖节流同步。

## v5.1.4（2026-10-28 · 保存相册信息后页面变成一串 JSON）

> 用户报：编好相册点「保存相册信息」，页面直接显示 `{"ok":true,"slug":"album-1793152410"}`，
> 既回不去也不知道到底存没存。

### 根因：同一个端点，两种提交方式，只有一种返回值

编排页的「保存相册信息」是**传统表单提交**：

```html
<form method="post" action="{{ url_for('admin.album_update', aid=album.id) }}">
```

而 `album_update` 是按 JSON API 写的，末尾无条件 `return _ok(slug=a.slug)`。
浏览器提交表单后会**导航到 POST 的响应体**——于是把 JSON 当页面渲染了。
既没有 `Location` 可跳转，页面上也没有任何链接，用户就「卡」在那串 JSON 上。

同页其余操作（章节增删、条目增删、排序、设封面）都是 `fetch` + JSON，
所以只有这一处踩到——**契约不一致，不是逻辑写错**。

### 修复：按请求类型分支，一个端点服务两种调用

```python
form_mode = not request.is_json

def fail(msg, code=400):
    if form_mode:
        flash(msg)
        return redirect(url_for("admin.album_edit", aid=aid))
    return _fail(msg, code)
```

- **表单提交** → `flash` + 302 回编排页（成功提示「相册信息已保存」）；
  校验失败（标题空 / slug 冲突 / 日期格式错）同样 flash + 回跳，不会把
  `{"ok":false,...}` 甩在页面上。
- **fetch 调用** → 仍返回 JSON，现有 JS 一行不用改。
- 判据用 `request.is_json` 而不是「谁调的」：**顺带让无 JS 环境也能保存**。

### 顺带做的一次全量排查

把后台 **107 处 POST 表单**全部对了一遍「对应的路由函数返回什么」：
只有 `album_update` 一处属于「只返回 JSON」。另有 5 处（`mcp_services_*`）
的 `jsonify` 只出现在「id 不存在」的错误分支，成功路径是 flash + redirect，
属既有正常写法，不在本次范围。

### 影响面

只改 `myblog/admin/album.py`（一个函数）+ `tests/test_album.py`（新增 3 条）。
**无迁移、无前端包改动、无新路由、无新依赖。**

### 验证

- 新增 3 条回归测试（**共 14 passed**）：表单提交必须 302 且响应体不是 JSON、
  跟随重定向后页面出现「相册信息已保存」、JSON 提交仍返回 `{"ok":true,...}`、
  校验失败也走重定向。
- **变异验证**：把 `form_mode` 恒定为 `False`（退回旧行为）→ 测试立即变红，
  且报错信息正是 `AssertionError: 表单提交应重定向，实际 200（b'{"ok":true,"slug":"form-mode"}'）`
  —— 与用户看到的现象逐字一致。
- 端到端核对六个字段（title / summary / trip_days / intro / location / is_public）
  全部正确落库：**用户的修改在修复前其实已经存进去了**，只是页面显示错了。

## v5.1.3（2026-10-28 · 媒体选择器弹层关不掉）

> 用户报：相册编排页点「从媒体库添加图片」，没选图就点关闭，**点了没反应**，
> **刷新后弹窗还在**。

### 根因：`hidden` 属性被 `display` 覆盖

模板靠 HTML 的 `hidden` 属性隐藏弹层：

```html
<div class="album-picker-mask" id="picker-mask" hidden>
```

而 `admin.css` 里 `.album-picker-mask { display: flex }`。

`hidden` 属性只是浏览器默认样式表里的一条 `[hidden] { display: none }`，
而 **UA 样式表的优先级低于任何作者样式** —— 只要 CSS 给同一元素写了 `display`，
`hidden` 就彻底失效（这与特异性无关，是**来源顺序**问题）。

于是：

- 弹层从页面加载起就一直显示；
- 点「关闭」执行 `el.hidden = true`，属性确实设上了，但视觉毫无变化
  → 用户看到的是「点关闭没响应」；
- 刷新后仍然带着 `hidden` 属性重新渲染，还是被 `display: flex` 盖掉
  → 用户看到的是「刷新后还是这个弹窗」。

**排查陷阱**：这个症状极易被误判成「JS 报错、事件没绑上」。本次先抽出模板脚本
跑 `node --check` 确认语法 OK（`picker-close` 的绑定在顶层、会执行到），
才把矛头转向 CSS。

### 修复

`admin.css` 末尾加基础兜底：

```css
[hidden] { display: none !important; }
```

`!important` 是必要的：同特异性下 `[hidden]` 与 `.某类` 打平，后写的 `display` 仍会赢。
加上之后语义变成「带 `hidden` 就一定隐藏」，这正是该属性的本意。
同时防住未来所有同类写法（后台模板里还有 6 处用 `hidden` 属性隐藏 `input[type=file]`
与 `.wp-lib`，此前只是碰巧没有 `display` 冲突）。

### 验证

隔离验证（最小 HTML + 真实 `admin.css`，本地 HTTP）：

| 操作 | computed `display` |
|---|---|
| 带 `hidden` 属性 | `none` |
| `el.hidden = false` | `flex` |
| `el.hidden = true` | `none` |
| **删掉兜底规则后**（反证） | **`flex`** ← 证明是这条规则在起作用 |

新增 `tests/test_hidden_attribute_guard.py` **4 条**并做变异验证：
把 `!important` 去掉 → 立即变红；恢复 → 4 passed。

### 影响面

只改 `myblog/static/admin.css`（后端包）+ 新增测试。
**无迁移、无路由变更、无依赖变更、前端包无改动。**
## v5.1.2（2026-10-28 · 移动端抽屉菜单滚不动）

> 用户报「菜单栏在移动端上下划不动」。

### 根因

`styles/look.css` 里有一条为圆角裁切写的共享规则：

```css
.drawer, .notif-panel, .toolbox-menu { ... overflow: hidden; }
```

**`overflow` 是简写**，它把 `.drawer` 与 `.notif-panel` 在 `global.css` 里原有的
`overflow-y: auto` **一并重置成 hidden**。线上实测（390×844 视口）：

```
overflowY: "hidden"  scrollHeight: 1062  clientHeight: 818  → 溢出 244px
```

内容比屏幕高 244px（约 5 个菜单项），却完全划不动。

**为什么之前没被发现**：`overflow: hidden` 下**程序设 `el.scrollTop` 仍然生效**
（实测设 400 后读回 244），只看 DOM、或跑一行 `scrollTop = N` 会得出「能滚」的
错误结论。判据必须是 **computed `overflowY`**，而且要看**用户手势路径**。

### 修复

- `.notif-panel` 显式恢复 `overflow-y: auto`（站内通知面板此前同样被锁死）。
- `.drawer` 改为：**外层 `overflow: hidden` 裁圆角，`.drawer-head` / `.drawer-foot`
  固定，只让 `.drawer-nav` 滚动**。
  顺带修掉一个隐藏的可用性坑 —— 原来整个抽屉滚，滚到底部时关闭按钮会一起滚走，
  手机上只能点遮罩才能关。`.drawer-nav` 必须带 `min-height: 0`
  （flex 子项默认 `min-height: auto`，不置 0 就不会收缩，`overflow` 也不生效）。
- `.toolbox-menu` 保留 `overflow: hidden`：它是下拉菜单，没有 `max-height`、
  内容不溢出，需要裁掉 hover 底色顶破圆角的部分。

### 影响面

只改 `styles/look.css`：**无迁移、无新路由、无新依赖、无新环境变量、无后端改动**。

### 验证

- 修复前（线上）：`overflowY: hidden`，溢出 244px，滚不动。
- 修复后（本地 390×844）：`.drawer` `hidden` / `.drawer-nav` `auto`，
  `scrollHeight 737 > clientHeight 540`，可滚到底 197px。
- 截图对照：滚到底部时标题与关闭按钮仍固定在顶部、登录/注册/主题/EN 固定在底部、
  圆角完整无溢出。
- 构建产物层叠顺序核对：`.drawer` 相关规则的最后一条为修复后的值
  （`body.drawer-open-lock { overflow: hidden }` 只锁 body，不影响抽屉内部）。

## v5.1.1（2026-10-28 · 相册正文渲染修复）

> v5.1.0 上线后实测发现：行程概览与小提示的纯文本渲染器只认「空行分段 + `- ` 列表」，
> 管理员一旦写 `**粗体**`（写「路线 / 里程 / 住宿」这类键值时几乎必然），星号会原样露出来。
> 根因是**对输入语法的假设太窄** —— 不是解析写错，是只实现了最容易想到的那一种。

### 修复

- **`**粗体**` 支持**：按 `**` 把每行切成片段（`{text, bold}`），渲染时用 `<strong>`/`<span>`
  插值。**仍然不用 `v-html`、不引 markdown 库** —— HTML 永远不会被当作标签执行。
  未成对的 `**` 会作为普通文本保留，不吞字符。
- **段内换行保留**：原来同一段落的多行被 `join(" ")` 合成一行，
  导致「路线 / 里程 / 住宿」三行挤成一段。改为逐行渲染、行间 `<br>`。
- 后台两个输入框的 placeholder 由「支持 Markdown 换行」改为**明确列出支持的语法**
  （空行分段 / 行首 `- ` 成列表 / `**文字**` 加粗）—— 原文案会让人以为支持完整 Markdown。

### 影响面

- 只改前端渲染层与后台文案：**无迁移、无新路由、无新依赖、无新环境变量**。
- 安全面不变：渲染仍走 Vue 插值，未引入 `v-html`。

### 验证

- 实测截图对照：修复前 `**路线**：… **里程**：…` 露出星号且三行并成一段；
  修复后三行分开、加粗生效。
- 全量回归通过。

## v5.1.0（2026-10-28 · 相册：把素材编排成游记页）

> 相册：把图床里的素材编排成**可发布的图文集合**——一次旅行/一个主题一个页面，
> 章节分组、逐张图注、可写行程概览与小提示。

### 新：相册（媒体编排层）

**为什么不是继续扩展媒体库**：`media_asset` 回答「我有什么素材」，相册回答
「这些素材怎么讲一个故事」。同一张梯田照片既属于「云和自驾」也可能属于
「年度精选」，说明文字在两个相册里还不一样——所以相册**只引用** media_id，
不复制文件、不复制 URL。删掉一张图不会让整篇游记崩掉（空引用在该层被过滤）。

**三张表（只加新表，不改任何既有表）**：
- `album`：slug / 标题 / 摘要 / 封面 / 事件日期 / 地点 / 节奏(trip_days) /
  行程概览(intro) / 小提示(tips) / 是否公开。
- `album_section`：相册内**可选**的分组（「D1 畲乡之窗」「梯田晨雾」…），
  自带标题与说明，可排序。不建分组就是一面扁平照片墙。
- `album_item`：一条「素材 + 图注 + 归属分组 + 顺序」。

**后台**：新增 `/admin/albums`（列表）与编排页——基本信息、行程概览、小提示、
章节增删改、从媒体库挑素材（支持搜索/类型筛选/多选）、写图注、上下移排序、
设封面、移除条目。移除条目**不删文件**，素材仍在媒体库。

**前台**：`/gallery` 从「全站素材平铺」改造为**相册卡片墙**（封面、摘要、
日期/地点/节奏、项数、预览带）；新增 `/album/<slug>` 游记页——封面大图、
行程概览、按章节分组的图文、未分组区、小提示、灯箱（点击放大、左右键翻页、
Esc 关闭、显示图注与序号）。

**渲染安全**：行程概览与小提示按「空行分段、整段 `- ` 转列表」在前端解析，
**不引 markdown 库、不用 `v-html`** —— 少一个 XSS 面。

### 影响面

- **新增路由**：`/album/<slug>`（前台）、`/api/albums`、`/api/albums/<slug>`、
  `/admin/albums`、`/admin/albums/<id>/edit`、`/admin/albums/create`、
  `/admin/albums/<id>/update|delete`、`/admin/albums/<id>/sections[/<sid>[/delete]]`、
  `/admin/albums/<id>/items[/<iid>[/delete]]`、`/admin/albums/<id>/items/sort`、
  `/admin/albums/media-picker`。
- **表结构**：新增 `album` / `album_section` / `album_item` 三张表
  （Alembic `a1c9e4f72b38`，down_revision `f3b7d2a91c58`）；不改任何既有表。
- **权限**：`/admin/albums*` 全部要求管理员；`/api/albums*` 公开只读。
- **前端**：`/gallery` 语义由「素材列表」变为「相册列表」；新增 `AlbumView` chunk。

### 验证

- `tests/test_album.py` **11 passed**：公开过滤（私密相册不进列表、详情 404）、
  非公开媒体不进相册、已删媒体的条目被 join 过滤（不渲染破图）、
  删章节后条目回到未分组、删相册不删媒体、批量添加与指定章节、slug 不冲突、
  后台列表页与编排页能渲染（含游记三块与图注）。
- **全量回归：1199 passed / 0 failed**（v5.0.0 为 1186，本版新增 13）。
- `vite build` 通过，`AlbumView` chunk（6.69 kB）正常产出。
- 无障碍守卫：章节说明 textarea 补 `aria-label`（placeholder 不算可访问名）。

## v5.0.0（2026-10-28 · 媒体库升级为图床 + 游戏下线 + 前后台统一观感）

> 大版本：**媒体库升级为图床**（视频播放 / 分类归档 / 云存储外挂）+ **游戏板块整体下线**
> + 生态统计优化 + 部署门槛文档 + 前后台统一观感改版。
>
> 原计划的 v4.13.2 未单独发版，内容已并入本版。

### 新：媒体库升级为图床（视频 / 归档 / 云存储）

**支持视频**：新增 `mp4 / m4v / mov / webm`（浏览器能原生播放的容器；刻意不收
avi/wmv/flv —— 收了也播不了，除非上 ffmpeg 转码）。上限分级：**图片 50MB、视频 500MB**
（`MEDIA_IMAGE_MAX_MB` / `MEDIA_VIDEO_MAX_MB` 可调）。

**分块上传**：>16MB 的文件自动切 8MB 块逐块上传（`/admin/upload/chunk/init|part|complete`）。
这不是花活：500MB 单请求在国内家宽上行要 80~250 秒，而 gunicorn 默认 `timeout=30s`
会把 worker 直接杀掉，表现为「传到一半 502」。分块后每块最慢也在 30s 内完成，且天然可续传。

**新建 `media_asset` 表**（唯一表结构变更，只加新表）：承载标题 / 归档分类 / 时长 /
封面 / 是否公开等元数据。此前媒体库是纯目录扫描 + `O(文件数 × 文章数)` 的引用判定，
几百个视频进来首屏就会秒级卡顿。旧图片由 `sync_from_disk()` 自动补登记（幂等），
**不会出现「升级后媒体库全空」**。

**云存储外挂**：媒体库可切到**对象存储（OSS/COS/S3 兼容）** 或 **WebDAV 网盘**
（坚果云 / Nextcloud / 群晖）。通道复用 `backup.py` 已趟过的 boto3 / curl 两条路，
但与备份配置**完全独立**（备份桶通常私有，图床桶必须公开可读，混用会 403）。
密钥 Fernet 加密落库、页面只回显掩码。云端失败时**保留本地副本**并提示，
不把「云挂了」变成「文章写不了」。

**归档页面**：后台 `/admin/media` 重做（图片/视频分栏、分类筛选、关键词搜索、
编辑标题/分类/公开状态/视频封面、复制 URL 与 Markdown）；前台新增 `/gallery`
（分类 chips + 图片墙 + 视频内嵌播放 + 分页）。

**正文视频播放**：`![](/static/uploads/x.mp4)` 会渲染成 `<video controls preload="metadata">`
（`_img_to_video()`），白名单新增 `video/source`（**没有 style、没有 on\*、没有 iframe**）。
`_RENDER_VERSION` 4 → 5，强制历史缓存重渲染。

**磁盘闸门**：上传前检查剩余空间 ≥ 文件大小 + `MEDIA_DISK_RESERVE_GB`（默认 2GB），
不足直接拒传。磁盘写满会让 SQLite 全线失败，那比「传不上去」严重得多。

### 删：游戏板块整体下线

按你的判断「实际不会打开、白占资源」，整体移除：
`api/games.py`、`admin/games.py`、`games_safety.py`、`tools/seed_games.py`、
`Game` 模型、3 个后台模板、3 个前端页面（`/games`、`/games/dev`、`/games/:slug`）、
后台导航与抽屉/顶栏入口、相关测试与 i18n 键。

**没有跟着一起删的东西**（刻意保留）：
- `games_llm_*` 设置键：AI 摘要一直在用同一套 OpenAI 兼容配置。键名不改（改键名会让
  存量部署加密存的 Key 静默失效）。配置入口从「游戏收录 → LLM 审计」搬到
  **`/admin/ai-summary/llm-config`**，`ai_summary.html` 里的链接同步改掉 ——
  否则 `url_for('admin.games')` 会 BuildError，AI 摘要页直接 500。
- 数据库 `game` 表与 `data/games/` 目录：**不删数据**。代码不再引用它们，需要清空可自行操作。
- `gamify.py`（读者积分勋章）：名字含 game 但与本功能无关，**没动**。

### 新：生态统计独立页面 `/ecosystem`

原「关于」页里的「🌐 生态」板块（跨站点注册表统计）迁出，单独成
`/ecosystem` 页面（抽屉导航 + 顶栏「更多」均加入口）。关于页仅保留本站
「当前在线访客」指标（与生态注册表无关）。新页面拉取既有公开接口
`GET /api/ecosystem/stats`，无新增后端接口、无权限变更。

### 改：离线站点超过 24 小时无心跳自动删除

原逻辑：注册表里超过 30 天无心跳的站点只是「不展示」，行仍在，导致
「站点总数」被早已离线的实例虚高（实测曾出现 2 条 10-25 发版当天的本地
实例一直计入 `total`）。

新逻辑：中心端每小时心跳后顺手调用 `ecosystem.prune_stale_sites()`，
**硬删** `last_seen` 早于 `now - 24h` 的行（心跳每小时一次，24h≈24 次
连续错过，足以判定部署已不在）。`stats()` 的展示窗口同步从 30 天收敛到
24h，并给站点输出补 `first_seen` 与带时分的 `last_seen` 时间戳。

`prune_stale_sites()` 的 `exclude_self=True` 会排除本机 `site_key`
对应的那一行 —— 即使某次心跳偶发失败，中心站也不会把自己误删；心跳先跑
（刷新自身 `last_seen`）、prune 后跑，进一步保证不会误删自己。

### 文档：README 补「服务器最低配置」

README 的 `## 部署` 下新增 `### 服务器最低配置` 小节，给出 **CPU / 内存 / 磁盘 /
系统 / Python** 五项「最低 vs 推荐」对照，并显式列出**不需要**的东西（MySQL /
Redis / Node.js / 独立数据库服务器），省掉新用户的选型纠结；原本的部署要点
收进 `### 部署要点` 小标题。`myblog/deploy_guide.md` 的「部署前置条件」加入
对应指引与锚点链接，`myblog/README.md` 的「部署」段也加一行指向根 README
（**只放链接不复制表格**，避免两份文档的数字漂移）。

内存口径为实测而非估算：Python 解释器空载 22 MB，导入 Flask / SQLAlchemy /
Pillow / cryptography / markdown / bleach / feedparser 全套后 **81 MB**；据此推算
4 worker + Nginx + 宝塔面板合计约 1.2~1.5 GB。故 1 GB 只在「worker 降到 2 +
开 2 GB swap」时可用，2 GB 是省心起点。此前 README 只有零散的「Python ≥3.10」
和 `gunicorn_conf.py` 注释里的「2 核机器」，读者无法据此选机型。

### 改：前后台统一观感（v5.0.0 主线）

**刻意没做的事：换配色。** `--text` / `--bg` / `--text-muted` 这些语义色既被
WCAG 守卫视死（`test_wcag_contrast.py`），又与 `myblog/themes.py` 的 `_BASE_LIGHT`
逐字绑定（`test_base_light_matches_token_files`）—— 改一个值就是「前后台灰阶不一致」
或「对比度不达标」。所以这套观感全部由**形状 + 动效 + 层级**来出：

| 维度 | 做法 |
|---|---|
| 形状 | 卡片 22px、分组 14px、控件 12px、**按钮全胶囊** |
| 动效 | 系统缓动 `cubic-bezier(.32,.72,0,1)`；按压 `scale(.96)` 回弹；卡片 hover 上浮 |
| 层级 | 1px 发丝分隔线 + 半透明填充（tertiary fill）+ 顶栏**毛玻璃**（backdrop-filter） |
| 排版 | 导航大标题：`clamp(24px,3.4vw,32px)`、字距 `-0.02em`；去掉标题左侧竖条 |
| 后台 | 侧栏激活项从「左侧渐变竖杠」改为**填充胶囊**；表格改分组圆角 |

新增 21 条 `--ui-*` 令牌，两份 `tokens.css`（前台 / 后台）**取值逐字一致**。
暗色下发丝线与填充**反相叠白**（亮色的 12% 黑在深底上几乎看不见，会整片糊掉）。
`prefers-reduced-motion` 打开时位移全部关闭，只保留颜色过渡。

**踩到的真坑（已修 + 已加守卫）**：第一版把规则追加在 `global.css` 末尾，
构建通过但页面没变 —— `main.js` 里 `responsive.css` 在 `global.css` **之后**导入，
它的 `.page-title { clamp(19px…) }` 同特异性下赢过了新规则。改为单独
`styles/look.css` 排在 responsive.css 之后，并新增 `test_frontend_css_order.py` 锁住顺序。
判据是构建产物里 `.page-title` 的最后一条是否为新值 —— **构建通过证明不了样式生效**。

顺带修了 `test_css_token_ratchet.py` 的计数 bug：`find(")", v, m.end())` 区间右开，
导致 `var(--accent, #196ddd)` 这种**标准兜底写法**会被误判成裸 hex
（闭合 var( 的 `)` 恰好在 hex 之后）。已补回归用例锁住。

**逐页精修（第二轮）**：在全局组件层之上，对读者停留最久的几处做针对性打磨。

- **文章卡片**（`PostCard.vue` 无 scoped 样式，改 `look.css` 即首页 / 归档 / 分类 /
  标签 / 搜索结果**全部跟着变**）：22px 分组卡、标题 20px/600、封面比卡片小一档
  圆角形成层次、「阅读全文」从裸链接改为灰填充胶囊按钮。
- **分页**：改为分段控件（38px 胶囊，当前页填充品牌色）。
- **文章页阅读排版**：正文 17px / 行距 1.86（阅读器式）、标题字阶与段前距重排、
  图片与视频 14px 圆角、代码块 12px 圆角、引用块改「左侧品牌色竖条 + 填充底」、
  目录 / 语言切换 / 标签 / AI 摘要统一为分组卡与胶囊。
- **侧栏**：标签云改胶囊 chips、列表行改用发丝线分隔、搜索框改胶囊字段。
- ⚠️ **刻意没动 `.post-body table`** —— v4.12.1 修过「表头与数据分居两端」的对齐 bug，
  表格的圆角/边框改动容易把那套对齐口径弄坏，收益不抵风险。


**逐页精修（第三轮）**：前台交互页 + 后台 48 个模板的结构类。

- **登录 / 注册**：卡片 22px；表单标签从「粗体黑字」弱化为 13px/500 灰阶
  （原来标签比输入内容还抢眼）；验证码图 12px 圆角可点。
- **留言墙**：条目改分组卡 + hover 上浮；点赞按钮从「1px 描边方角」改灰填充胶囊
  + 按压 `scale(.94)`；元信息与提示改用令牌色。
- **归档时间线**：轴线从 2px 实线改 1px 发丝线，节点圆点带底色环，年月字阶重排。
- **搜索结果**：22px 分组卡 + hover 上浮；搜索历史 chips 与「清空」按钮统一胶囊、
  去掉下划线（`SearchView.vue` 的 `<style scoped>` 内改 —— 它的属性选择器特异性
  高于全局类，只能在组件内改）。
- **后台**：只覆盖跨模板复用的结构类（`.card` 系 / `.field` 系 / `.stat-card` /
  编辑器 `.md-*`），一轮覆盖几十个模板；复选框行补 hover 反馈；统计卡统一圆角与上浮。
- ⚠️ **踩到的坑（自查修掉）**：给 `.md-toolbar` / `.md-pane` 加全边框时，忘了它们
  在 `.md-stage`（自带边框 + `overflow:hidden`）**内部**，会画成嵌套双框；`.md-stage`
  不是 flex/grid，给它写 `gap` 是无效规则；`.field-grid` 原 `gap: 4px 16px` 的紧凑
  行距被我压成 16px、`.stats-grid` 原 18px 被我改小 —— 三处均已回退到原意图。
  教训：**给子元素加边框前，先确认祖先有没有边框**（与 v4.12.1「改铺满视口前查
  祖先限宽」是同一类错误）。

**命名合规**：本轮把所有风格相关命名从厂商产品名改为中性名 ——
`--ios-*` → `--ui-*`（21 条令牌）、`styles/ios.css` → `styles/look.css`、
文档措辞改为「统一观感层 / 圆润风格」，`Large Title`、`tertiary fill`、
`inset grouped` 等专有叫法一并换成通用说法。
**保留**的 4 处是技术事实指代，不属于风格自述：`utils/text.py` 里 UA 设备识别
（Windows / Android / macOS 并列）、以及「某浏览器对 `background-attachment: fixed`
存在支持缺陷」这类兼容性说明。判据是：**说别人家的浏览器/系统 → 保留；说自己
产品的风格 → 改掉。**

### 影响面

- **新增路由**：`/gallery`（前台）；`/api/media/list|folders/<id>`；
  `/admin/media/update|embed|sync|storage`；
  `/admin/upload/chunk/init|part|complete|abort`；`/admin/ai-summary/llm-config`。
- **删除路由**：`/api/games*`、`/admin/games*`、前台 `/games`、`/games/dev`、`/games/:slug`。
- **表结构**：新增 `media_asset` 表（Alembic `f3b7d2a91c58`，down_revision `d9f1a4c7b2e8`）；
  **不改任何既有表**。`game` 表保留但代码不再读写。
- **权限**：媒体库页面/上传/删除要求管理员；**存储后端设置要求超管** ——
  能改「文件往哪写」等于接管存储，不能下放给普通管理员。
- **部署**：Nginx 必须加 `client_max_body_size 40m`（默认 1MB，否则大图直接 413，
  且后端日志里什么都没有）；`data/upload_tmp/` 需可写（分块临时目录，超 24h 自动清）。
- **环境变量（可选）**：`MEDIA_IMAGE_MAX_MB`（默认 50）、`MEDIA_VIDEO_MAX_MB`（默认 500）、
  `MEDIA_DISK_RESERVE_GB`（默认 2）。小盘服务器建议调低视频上限。
- **依赖**：仅在选择 OSS 后端时需要 `boto3`；未安装会在媒体库页面**明确报错**，
  不静默降级成本地存储（否则用户以为文件在云上，本地盘被悄悄写满）。

### 验证

- `tests/test_media_asset.py` 新增 **17 条**：伪装视频拒绝、图片/视频上限分流、
  磁盘闸门、分块合并 / 缺块 / 大小不符、会话 ID 路径穿越、公开接口只吐 `is_public`、
  外链播放器白名单、正文 `img→video` 转换与 script/iframe 剥离。
- `tests/test_ecosystem.py` 28 passed（含 3 个 prune 用例）。
- 渲染白名单棘轮：`EXPECTED_ALLOWLIST_SHA256` 与 `_RENDER_VERSION=5` 已同步更新
  （白名单新增 `video/source`，属性仍无 style、无 on\*、无 iframe）。
- `vite build` 通过，`GalleryView` chunk 正常产出。
- 删除游戏后回归：`/admin/games` 相关诊断用例与游戏测试一并移除，无残留 500。
- **全量回归：1186 passed / 0 failed**（较 v4.13.1 的 1195：媒体 +18、前台样式顺序 +2、棘轮计数回归 +1，删除 2 个游戏测试文件 −15）。三轮精修后复跑仍为 1186 / 0 failed。
- `vite build` 通过；构建产物里 `.page-title` / `.post-card` / `.pagination` / `.toc` /
  `.post-body` / `.tag-cloud .tag` / `.read-more` / `button,.btn` / `@supports backdrop-filter`
  的**最后生效规则均为观感层新值**（不是只看构建成功）。


## v4.13.1（2026-10-26）

> 纯文档补丁：清理 `SECURITY_AUDIT.md` 里重复出现的 R127 标题。**无代码变更、无前端变化、无迁移**。

### 修：审计文件里 `## R127` 出现两次

v4.13.0 的排查过程中发现本文件有两个 `## R127 · v4.8.7 …` 标题，但**两处内容并不相同**：

| 位置 | 内容 | 位置是否正确 |
|---|---|---|
| 原第 328 行（在 R128 与 R126 之间） | 只有 3 行结论的**简版** | ✅ 正确 |
| 原第 373 行（落在 R126 之后） | 带 `127.1` / `127.2` 小节的**完整版** | ❌ 破坏了降序 |

所以不能「直接删第二个」——那样会把信息量更大的完整版丢掉。修法是**保留完整版、删简版，
并把完整版放回原先正确的位置**（R128 → R127 → R126）。顺带删掉 R132.5 里那条
「本轮未修的既有文档缺陷」记录，它已不成立。

结果：总标题 23 → 22，R127 出现次数 2 → 1，文件 129067 → 128391 字节。

### 本版未新增审计轮次

按 `blog-release` 的口径，「新增轮次」是**发现安全问题并修复**时才做（v4.12.1 的
「表格对齐 + 审计归档 R101~R110」同样未新增轮次）。本版只有文档去重，无代码、无攻击面变化，
因此不新增 R133，在此说明以免被误当成漏项。

### 验证

- 全文件标题扫描：重复标题 **0**；R127 落在 R128 与 R126 之间，降序正确。
- `tests/test_doc_archival.py` **34 passed**（PAIRS 守卫未受影响）。
- 全量 **1195 passed**。
- 部署包内 `SECURITY_AUDIT.md` 已含清理后的版本（`myblog/` 整目录进包）。

---

## v4.13.0（2026-10-26）

> 由一次「帮我诊断一下博客」引出的两个自身缺陷：站点本身健康（19 维全绿），
> 坏的是**诊断链路自己**——它在拿写操作做能力探测，既让 3/4 的 worker 静默降级，
> 又会在并发时误报「数据库索引损坏、建议从备份恢复」。

### 修：FTS5 能力探测从「写库」改为「只读」

`fts._probe()` 原先用 `CREATE VIRTUAL TABLE _fts_probe USING fts5(...)` + `DROP` + `commit()`
来测 FTS5 是否可用，即**拿一次 DDL 当能力测试**，并把结果按进程永久缓存。两条实测后果：

1. **worker 永久降级。** `app.py` 里每个 gunicorn worker 启动都会走
   `fts.ensure()` → `available()` → `_probe()`，4 个进程同时抢写锁，抢输的拿到异常 →
   结果被写进模块级变量、终身不再重试 → 该 worker 此后所有 `fts.search()` 直接返回
   `None`，搜索永久退化为 LIKE 全表扫描，**且没有任何日志**。
   实测：同一查询连打 10 次 `/api/search?q=Flask`，`engine` 在 `fts5`(3 次) / `like`(7 次)
   之间翻转 —— 4 个 worker 里 3 个已降级。结果条数相同，用户看不出异常，只有性能与
   语义（词元匹配 vs 子串匹配）的差异。

2. **体检误报数据库损坏。** `diagnostics.check_search_index()` 会惰性调到这里，等于在
   「只读」体检里写库。多个连接同时 CREATE/DROP 搅动 `sqlite_master` 时，另一个连接跑
   `PRAGMA integrity_check` 会吐
   `malformed inverted index for FTS5 table main.post_fts`，notes 还写着「建议从备份恢复」——
   照做就是拿一次误报毁掉一个健康的库。
   隔离复现（在 `/tmp` 的库副本上，不碰生产）：1 个写者 60 次检查 **0** 假报，
   4 个写者 60 次里 **2** 次假报（`vtable constructor failed: post_fts`）。

修法：`SELECT sqlite_compileoption_used('ENABLE_FTS5')` 只读编译期选项，不开事务、不建表；
返回 0 时再查一次 `sqlite_master` 里 `post_fts` 是否已存在（老库可能早就建好表），
避免把能用的库判死。已核实生产 SQLite 3.46.1、本机 3.53.1、测试 venv 3.50.4 均返回 1。

### 修：探测失败不再永久缓存

`available()` 改为**只缓存成功**；失败只保留一个有界窗口（`_PROBE_RETRY_SECONDS = 60`），
窗口内不重复探测（避免每次搜索多一次查询），窗口外自动重试。单次瞬时故障不再扩散成
进程级状态。

### 修：把「未编译 FTS5」与「探测失败」分开报

`check_search_index()` 原先一律报「SQLite 未编译 FTS5：站内搜索退化为 LIKE 全表扫描」。
但实测里真正发生的是**探测本身失败**（抢不到写锁），FTS5 明明是好的 —— 这句话会把运维
指向「换一个编译了 FTS5 的 SQLite/Python 运行环境」这种完全无关的动作。

现在按 `probe_code()` 分流：`not-compiled` → 提示换运行环境；`probe-failed` →
明说「这是探测本身失败，多为数据库忙/连接回收，60 秒后自动重试」，并原样带出真实异常文案
（截断到 200 字符：SQLite 异常偶尔会带数据库绝对路径，超管可见但没必要整段外露）。

### 改：`health_score` 对异常维度回传原因

`MCP health_score` 原先只回各维度的 `key/title/status/问题数`，而 checker 走 `except`
降级时「为什么坏」只写进 `notes`（有时真实原因只在 `items[].value` 里，`notes` 只是一句
通用建议）。于是**瞬时错误一消失，根因就永久查不到了** —— 本次就是只看到
`database=error`，得再单独跑一次 `health_overview` 才捞到那句 `malformed inverted index`，
而那时错误往往已经消失。

现在 `status != ok` 的维度会一并带上 `notes` 与出问题的 `items`（正常维度仍不回传明细，
避免 19 个维度把响应撑大）。同一次会话里三次并发 `health_score` 给出 92/95/100 三个分数、
`generated_at` 却是同一秒 —— 这种「评分不可重复」的表现也因此可解释了。

### 验证

- 新增 `tests/test_fts_probe_readonly.py`（8 条）：在 `before_cursor_execute` 上挂事件
  收集实际执行的 SQL，断言 `_probe()` 期间**不含任何 DDL/DML**；断言探测后
  `sqlite_master` 一字不动、无 `_fts_probe` 残表；断言失败在窗口外会重试、成功会缓存；
  断言两种失败口径不互相污染；断言 `health_score` 会带出原因。
- **变异验证 4/4**（把修复逐个回退，对应测试必须变红，复原回绿）：
  ① 失败永久缓存 → 红；② 探测改回 DDL → 红；③ 体检口径退回「一律未编译」→ 红；
  ④ `health_score` 不回传 notes/items → 2 条红。
- 全量 **1195 passed**（352 秒）。后端改动，前端包无变化。
- 生产侧复核：独立只读连接连跑 3 次 `integrity_check` + `quick_check` 全 `ok`，
  `post_fts` 13 条与 13 篇文章一致，无 `_fts_probe` 残表 —— 确认真实数据一直健康，
  那句「索引损坏」纯属并发误报。

---

## v4.12.1（2026-10-25）

> v4.12.0 的部署因服务器直连 GitHub 下载超时（3.3 MB 的包两次都在 2.2~2.9 MB 处断开）未上线，
> 本轮把用户报的表格对齐问题一并带进来，重走镜像部署。

### 修：访问统计页「数值列表头与数据对不上」

现象：最后三张卡（来源渠道 / 设备分布 / 浏览器分布）的表头「次数」贴在列左边，
而数字贴在列右边，中间空出一大片。

根因：`.rank-count` 让**数据**右对齐，但 `<th>次数</th>` 继承的是 `.stats-table th` 的
`text-align: left`；表格是 `table-layout: auto`，当第一列内容（域名 / 浏览器名）较长时，
中间这列会被拉宽，于是同一列里的表头与数字分居左右两端。另外 `.stats-table` 的
`th:last-child` / `td:last-child` 都右对齐，所以「占比」列一直是对的 —— 只有
**夹在中间的数值列**中招，这也解释了为什么只有这三张卡明显。

修法：给中间数值列引入 `th.num` / `td.num`，表头与数据统一右对齐，
并用 `width: 1% + white-space: nowrap` 把它收窄到内容宽度（剩余宽度让给第一列）。
环比表的「本期 / 上期」同属数值列，一并统一，避免同一页一半右一半左。

### 修：≤900px 时整页表格表头错位（同一根源的另一半）

`admin.css` 在 `≤900px` 给 `.stats-table` 设了 `display: block` 来实现横滚，
但 `display: block` 会让 `thead` / `tbody` 各自成为「匿名表格」—— 列宽分别计算，
**表头与数据必然对不齐**。改为在移动端恢复 `display: table`，把横滚交给
`.stats-card` 容器（`.stats-page` 作用域内，不影响诊断页等其他使用方）。

### 验证

- 用真实 CSS 搭静态验证页（与模板同一份内联样式 + `admin.css` + `tokens.css`），
  逐列比较「文本边缘」而非元素左边界：三张表全部 `表头[L83 R792 R1197] == 数据[L83 R792 R1197]`。
- 390px 视口：`display` 回到 `table`，`scrollWidth == innerWidth == 390`（无横向溢出）。
- 全量 1184 passed。

---

## v4.12.0（2026-10-25）

### /docs 页修正与重做（前台 API 文档）

**修**
- **版本号写死在模板里**：正文写「当前版本基于 v3.8.7」，而线上已到 v4.11.0 —— 落后三个大版本。
  改为运行时取 `GET /api/health` 的 `version`（公开接口，只回 ok/version/db），
  取不到就渲染「—」，**不再回退到任何写死的字符串**。顶栏也加了版本徽标。
- **「覆盖全部 JSON 接口」是不成立的承诺**：实际文档详列的只是前台接口，而
  `/api/mobile/*` 74 条、`/api/og/*` 5 条、`/api/qr` 等均未提及。
  改为如实分层说明，并新增「其他接口 More」一节：分享卡 / 列表页壳页 / 二维码 / 通道自检
  逐个给边界条件，管理类 74 条按 12 个分组列表（不逐条抄，指向 `API.md`）。
- **锚点落点被顶栏遮住**：`scroll-margin-top` 原为 20px，而站点头是 sticky 58px，
  点目录后标题正好藏在顶栏下面。改为 74px（移动端 68px），h3 另给 82px。
- **复制按钮从来没有样式**：它是 `onMounted` 里 `document.createElement` 出来的，
  拿不到 scoped 的 `data-v` 属性，因此 `.copy-btn { … }` 编译成 `.copy-btn[data-v-x]`
  永不匹配 —— 线上一直是代码块左下角一段无样式裸文字（靠截图才发现）。
  改用 `pre :deep(.copy-btn)`；同时给 `pre code` 加右内边距，长代码首行不再被按钮压住。

**改（UI）**
- **颜色全部改为设计令牌**：原样式是整套硬编码色（`#3b82f6` / `#e5e7eb` / `#f8fafc`…），
  与全站 tokens.css 两套体系 —— 后台改主题色后这页仍是蓝的，深色模式要靠 20 多条
  `[data-theme="dark"]` 逐条覆盖。现统一走 `--accent / --border / --surface-* / --text-*`，
  换主题色跟着变，深色模式基本无需单独写。
- **两个目录不再互相抄**：左栏列章节、右栏原来把每节 h1 又列一遍（前几条完全重复），
  现在右栏只显示**当前章节的小节**并随滚动替换，与左栏形成互补关系；
  目录高亮由 IntersectionObserver 改为按位置判定（顺带让 v3.20.0 那个
  「observer 从不 disconnect」的泄漏从结构上消失，只剩一个 scroll 监听且卸载时摘除）。
- 侧栏新增**文档内搜索**：既匹配章节名，也匹配该节正文（可搜端点片段如 `mobile`、`slug`），
  命中数与空结果都有提示。
- 端点行、表格、代码块改用同一套间距节奏；方法徽标补齐 PUT/PATCH/DELETE；
  纵深色用 `--on-accent` 双向适配（暗色下亮底配深字，亮色下深底配白字）。
- 表格桌面改回 `table-layout: auto`（原来固定布局把「路径 / 说明」两列拉成 50/50，
  长度差一倍的两列被强行等宽）；窄屏仍用 fixed + 强制换行防撑破。
- 移动端侧栏由「200px 高的纵向滚动块」改为**横向滑动 chip**（`display: contents` 让
  链接直接进入 flex 行，不改模板）；新增回顶按钮（长文档实用）。
- 移动端横向溢出修复：纵向 flex 下必须把桌面为三栏短栏写的 `align-items: flex-start`
  复位成 `stretch`，否则正文按内容宽度撑开，整页被拉宽到 1245px、文字被切掉（实测）。

---

## v4.11.0（2026-10-25）

后台 UI 统一 + 诊断能力扩展。一句话概括：把「后台每个页面各写一套样式」收成一套组件层，
同时把体检从 **12 个维度扩到 19 个**、给 MCP 补上能直接用的三个工具。

### 一、后台统一组件层（`admin.css` +486 行）

此前「统一美化」只停留在各模板自己内联 `<style>`，同一件事（页面说明、空状态、徽标、
按钮尺寸）在每个页面写法都不同；更严重的是有**一批类名从未被定义**
（`.hint-block` / `.section-sub` / `.empty-tip` / `.row-off` / `.inline-details` /
`.entry-edit-form` / `.btn-danger` / `.btn-sm` / `.tag` / `.stats-sub` / `.ann-form-row`）——
模板写了等于没写，浏览器按裸标签渲染。**这才是「几个后台页面看着不像一套」的真实原因。**

本版把它收成后台**唯一**的组件真相源：

- 结构类：`.page-head`（标题 + 右侧操作）/ `.card` / `.toolbar` / `.field` / `.kv-list` / `.empty`
- 补齐上述历史欠账（同名保留，不改模板的 data 契约）
- 徽标体系统一为 `.tag` + 语义变体（`.tag-up/-down/-flat/-warn/-info`）
- 全部走 `tokens.css` 变量，暗色只补「品牌彩色底」这一层

### 二、表单控件统一基座

组件层解决的是「类名欠账 + 容器内宽度」，但它是**按容器类**生效的，没有一条全局控件
外观规则——没落进 `.field` / `.edit-form` / `.inline-form` 的控件（筛选栏、工具栏、
卡片里直接放的输入框）拿到的是浏览器默认样式。

新增一节 `:where()` **零特异性**全局控件基座：`input`/`select`/`textarea` 的
border / padding / radius / focus-visible 光晕 / disabled / readonly / placeholder，
外加 `checkbox`/`radio` 的 `accent-color`、`file` 的 `::file-selector-button`、`color` 的
尺寸。特异性为 0，所以既有的 `.edit-form input` 等规则**仍然优先**，不改任何现有视觉。

同时把「新建表单」统一到 `.field` + `.field-label` + `.field-hint` 范式（有可见标签，
不再用 placeholder 兼作标签）：`用户管理` 新增用户卡、`外部入口` 添加卡片。
⚠️ **刻意不统一**的地方：筛选栏（`.toolbar`）、表格行内操作（`.row-ops`）、
行内编辑浮层（`.inline-details > .entry-edit-form`）保持紧凑布局——套 `.field` 会撑破表格。

### 三、修复：访问统计页的样式越权（两个真 bug）

`stats.html` 的页面级 `<style>` 里有 13 个选择器**没有作用域前缀**，其中两个是全局类：

- `.tag` —— `announcements` / `bot_guard` / `email_settings` / `feed_diag` / `games`
  五处都在用，被这一页的定义覆盖，徽标样式全站走样；
- `.card-head` —— `admin.css` 有全局版本（带 `surface-2` 背景与 `14px 20px` 内边距），
  被这页的定义覆盖，所有卡片的头部一起变形。

已全部补上 `.stats-page` 前缀（13 处），页面样式不再外溢。

另修 `var(--muted)` —— 这个变量在 `tokens.css` 与 `admin.css` 里**都不存在**，
两处共用的结果是深色模式回退到硬编码 `#888`，文字糊在深色背景上。改为 `var(--text-muted)`。

### 四、全站体检：12 → 19 个维度

新增 7 个 checker：`plugins`（插件加载/启停状态）、`search_index`（FTS 索引一致性）、
`scheduler`（定时任务）、`outbound`（出站安全层）、`content_quality`（内容质量）、
`disk`（磁盘）、`mcp`（MCP 端点自检）。

**顺带修掉一个静默 bug**：体检页模板读 `sec.rows`，而 12 个 checker 里 10 个只返回
`items` → Jinja 取到 Undefined（falsy）→ **明细表恒不渲染**，页面只剩标题、徽标和 notes。
现在 `_normalize()` 双向补齐 `items` / `rows` 两个别名（这是「修 bug」不是「加功能」，
两半是同一个 bug）。

### 五、MCP 同步：新增 3 个工具

| 工具 | 用途 |
|---|---|
| `health_score` | 0-100 分 + 19 维状态一览，不含明细（先判断「整体多糟」） |
| `issues` | 跨维度问题清单，按严重度排序，每项含 key/dimension/value/level |
| `run_check` | 只跑单个维度，返回**全部明细**（不裁剪，含正常项实际值——排障时正需要看这些） |

`run_check` 的 `check` 取值由 `diagnostics.CHECKS_BY_KEY` 驱动，新增 checker 会自动可用。
权限面无变化：仍只读、仍需 `MCP_AUTH_TOKEN`、仍按客户端 IP 限流 60/分钟。

### 六、其他

- 10 个后台模板改造：`announcements` / `base` / `email_settings` / `feed_diag` / `games` /
  `mcp_services` / `moments` / `nav_entries` / `seo` / `settings`
- 新增 `tests/test_diagnostics_v4110.py`（184 行），`test_mcp_diag.py` 补 83 行
- 全量 **1181 passed**（v4.10.1 时 1154）
- **无迁移、无表结构变更**

## v4.10.1（2026-10-25）

**热修**：v4.10.0 上线后实测发现列表页壳页被 CDN 缓存，导致**真人看到无样式壳页**。

### 缺陷与根因

- 现象：`https://www.llhhy.cn/archive` 真人访问返回 11038 字节的壳页（无 `<div id="app">`、无导航样式），
  而 `/archive/`（带尾斜杠）、`/category/x`、`/tag/x` 正常返回 SPA；直连源站（`127.0.0.1` + `Host` 头）
  也完全正常 —— 说明**源站 nginx 逻辑正确，问题出在回源之后的缓存**。
- 证据：响应头 `eo-cache-status: HIT`、`age: 151`、`cache-control: public, max-age=300`。
- 根因：壳页与真人 SPA 是**同一个 URL 的两种表示**，只靠 `Vary: User-Agent` 区分。而 `Vary` 只是建议，
  **EdgeOne 实测不按它分桶** —— 爬虫先抓一次 `/archive`，接下来 5 分钟所有真人都拿到那张壳页。
- 这是 v4.10.0 引入的新问题（此前只有文章页壳页，且真人流量一直在刷它，掩盖了窗口期）。

### 修复

`api/og.py::_shell_headers` 的 `Cache-Control` 由 `public, max-age=300` 改为 **`no-store`**
（文章页与列表页壳页统一）。理由：**同一个 URL 有两种内容，就不能允许中间层缓存** ——
`Vary` 挡不住不守规范的 CDN / 反向代理 / 公司网关。

代价是爬虫每次回源：列表页本地 5~52ms，文章正文有 `content_html` 缓存，可忽略；
而真人看到壳页是不可接受的事故。

### 测试

新增 2 条断言（文章页 / 列表页各一条）：`Cache-Control` 必须含 `no-store`，且**不得**出现
`public` / `max-age`（只查前者的话，`public, max-age=300, no-store` 这种自相矛盾写法会假绿）。
变异验证：把 `no-store` 改回原值 → 两条同时变红。

## v4.10.0（2026-10-25）

按 `ROADMAP.md` §3.1 剩余待办做的第二轮升级（4 项功能 + lint 债务减半）。安全审查见 `SECURITY_AUDIT.md` R129。

### 一、推送配置进后台（含出站 SSRF 加固）· 安全前置先做

`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `WECOM_WEBHOOK_URL` 此前只能写 `.env` 再重启，
现在后台「推送设置」页可配（`/admin/push-settings`，**仅超管**）：凭据 Fernet 加密落库、
页面只回显掩码、留空=保持不变、要清空须显式勾选，另有「保存并发送测试推送」做真实连通性校验。

⚠️ **落地前先补了 `notify._post_json` 的出站防护**（R128 §128.3 开列的前置条件）：
改走统一出站层 `outbound.open_url()` —— https 白名单 + 公网解析 + **IP pinning**（防 DNS
rebinding）+ **禁跟随 3xx**（防「公网 302 → 内网」）。若不做这一步，后台化就等于给每个后台
账号开一个直连内网的 SSRF 出口。另：`OutboundRejected`（配置错误）**不再重试**，避免白耗 7 秒
并把真错误埋进 3 条重复日志。

### 二、SPA 列表路径的服务端 SEO meta

`/archive`、`/category/*`、`/tag/*`、`/series/*`、`/about`、`/links` 此前对爬虫是一张
**共用站点级默认 meta 的空壳**（所有列表页同一个标题、同一段描述、无实质内容）。
新增 `/api/og/page/<path>` 出口，渲染带真实文章列表的壳页（title / description / canonical /
OG / CollectionPage JSON-LD），爬虫经 nginx rewrite 进入，真人照旧走 SPA。

- 可见性口径与前台列表**完全一致**（草稿/定时/回收站/隐私一律不出现）。
- **不认识的路径一律 404 + noindex**，绝不给通用兜底页（否则等于开放无限重复 URL）。
- 闸门与文章页共用 `_shell_gate()`，判定只写一份（这类逻辑漂移的表现是「收录静默归零」，最难排查）。
- 部署需在 nginx 加一段 `location ~ ^/(archive|about|links|(category|tag|series)/[^/]+)/?$`，
  见 `deploy_guide.md` 第 4b 步 ②。

### 三、移动端第二批「数据与设置」（D8.3 ②）

新增 7 组 JSON 端点（`api/mobile_ops.py`）：统计多维报表（含日趋势 / 设备 / 浏览器 / 来源）、
审计日志、备份列表、站点设置（白名单只读）、收录概览、证书状态、用户列表 + 改角色。

**权限逐条对齐后台页面**（D8.3 明确要求重新判，不沿用「管理员可读」）：除统计报表对齐
`admin.stats` 的 `@admin_required` 外，其余六组全部**超管专属**。PII 收口照旧：邮箱遮敏、
审计 `payload` 不返回、设置走白名单。**刻意不做**备份触发（含 300s 远程同步）与设置写入。

> D8.3 ①「前台浏览」是原生 App 侧界面，不在本仓库范围。

### 四、`update.sh` 版本号解析加固

两处 `grep -oE 'APP_VERSION *= *"[0-9.]+"'` 强绑字面格式，改单引号 / 带 `-rc1` / 加行尾注释
都会静默失配；而它用在「覆盖后校验」，失配时 `fail_exit`「版本号校验失败」会把人引向
「zip 没覆盖成功」的错误方向。改为 `read_app_version()`（python 解析优先、正则回退），
并把**「解析不到」与「版本不符」分开报错**。

### 五、lint 债务 472 → 241（-49%）

| 规则 | 前 | 后 | 处置 |
| --- | --- | --- | --- |
| F401 未使用导入 | 118 | 0 | **真删**死代码；`api/__init__.py`（注册式导入）与 `api/common.py`（再导出契约）逐条核实后加 `noqa` + 理由 |
| S110 try-except-pass | 60 | 0 | 逐条确认**全是刻意忽略**（可选依赖 / 清理动作 / 旁路信号），按语义分类登记理由 |
| SIM | 27 | 0 | 改用 with / 三元 / 合并条件（`open(...).read()` 全部改上下文管理器） |
| T20 print | 21 | 0 | 全在 CLI 脚本（`backup.py` __main__ / `migrate_*.py` / `tools/seed_games.py`），print 就是其输出接口 |
| ARG 未用参数 | 8 | 0 | 全是路由/回调签名参数，不能改名或删除 |
| BLE001 盲捕获 | 241 | 241 | **本轮不动**：逐条具体化需要业务判断，改错会让应有的兜底失效。留作后续专项 |

基线已 `--update` 收紧到 241。

### 六、其他

- `deploy_guide.md`：第 4b 步补列表页 rewrite 片段；升级要点加 v4.10.0。
- 全量测试 **1200+ 项通过**；四处变异验证实测变红（详见 R129 §129.6）。

## v4.9.0（2026-10-24）

按 `ROADMAP.md` §3.1「真·待办」做的一次**功能升级**（6 项落地 + 3 处文档过时描述修正 + 棘轮收紧）。
一句话概括：把升级地图里**还没有真正做完**的小项一次补齐，其中两项此前被误判为「没做 / 成本很高」。

### 一、设备 / 浏览器分布（新）

后台「访客统计」新增**设备分布 TOP** 与**浏览器分布 TOP** 两张表（最近 30 天，含占比）。

- 落地方式：给 `visit_log` 加 `device` / `browser` 两列（Alembic 迁移 `d9f1a4c7b2e8`），**没有新建表** ——
  升级地图原写「需新表」是过时判断，`utils.parse_device()` 早就存在，补两列即可直接 GROUP BY。
- **隐私收口**：只存解析后的粗分类（`手机` / `Chrome`），**不落原始 UA**。
  原始 UA 含设备型号与系统小版本，可指纹化；这与 `referrer` 只存 origin 是同一条原则。
  测试里有反向断言守着（型号串 `SM-S918B` 不得出现在任何一列）。
- 空串（v4.9.0 之前的老访问）**不参与聚合**，否则会聚成一大坨「未知」把真实分布压扁。

### 二、推送指数退避重试

`notify_new_post` 各渠道此前失败**完全静默**（只记一条 warning，运营侧无人知晓新文章没推到群里）。
改为 **1s / 2s / 4s 退避重试 3 次**，只在**全失败**时才记日志（中间失败的堆栈是噪声）。
重试跑在既有后台线程里（v3.20.0 起就不在请求路径上），单渠道最坏多耗 7s 不影响前台。
`sleep` 做成可注入参数，单测不必真等 7 秒。

### 三、留言墙敏感词过滤（补缺口）

评论侧自 v3.0.0 就有 `comment_spam_keywords` 过滤，**留言墙一直没有** —— 同样匿名可提交、
且直接公开展示，暴露面其实更大。属「改了一处忘了另一处」的规则漂移。

修法是抽公共函数 `api/common.py::find_spam_hit()`，评论与留言**共用同一份词表与匹配语义**，
从此不可能再漂移。已做变异验证：摘掉留言侧过滤后测试必须变红。

### 四、搜索历史（纯前端）

搜索页新增「最近搜索」胶囊：localStorage 记最近 10 条，可点击重搜、单条删除、一键清空。
零后端、零表结构变更 —— 搜索词属本机浏览痕迹，没有理由上报服务器。
全函数 try/catch（Safari 无痕模式下 `setItem` 会抛错，不能因此让搜索页挂掉）。

### 五、内容日历（后台）

后台新增 `/admin/content-calendar`：月历视图聚合**草稿 / 定时发布 / 已发布**，
按归属日期铺到日历格子上，点标题进编辑页。归属日期 = 有定时时间用定时，否则用创建时间（均显示北京时间）。
带渲染测试守着（Jinja 子模板 block 外内容不渲染，项目已踩过一次）。

### 六、分享卡片模板库

后台「站点设置」新增**分享卡片模板**下拉，4 套：经典渐变 / 微信方图 / 深色极简 / 暖色纸感。

- **微信方图（800×800）是这次最值得做的一项**：微信会把 og:image **裁成正方形**，
  1200×630 横图两侧会被切掉、贴边标题只剩半截 —— 所以单独给一套方图模板。
- 主色优先级：**站点自定义主题色 > 模板默认色**；classic 默认色沿用 `#1a73e8`，升级前后默认表现一致。
- ⚠️ **缓存 key 必须含模板名**：classic 与 wechat_square 默认主色**故意相同**、只有尺寸不同，
  若 key 只按 accent 算，换模板会命中旧缓存吐回横图，且缓存命中时**没有任何日志** —— 已配专项测试。

### 七、升级地图 3 处过时描述修正

瘦身后的 `ROADMAP.md` 里有 3 条与代码实际不符，一并改正（避免后人照着错误描述重复劳动）：

| 条目 | 原描述 | 实际 |
| --- | --- | --- |
| 来源渠道 referer | 需新列、隐私待定 | **v3.17.3 已做**（`referrer` 列 + `_top_referrers()` + `/api/stats/referrers`） |
| 评论审核增强 | 敏感词 + 验证码都缺 | **验证码 v3.2.0 已做**（含独立设置页），仅敏感词缺 |
| 版本号多处复制 | 5+ 处副本 | 只有 `config.py` 一处权威源，其余 8 处是 `import` **引用**；真风险仅 `update.sh` 正则强绑字面写法 |

### 八、lint 棘轮收紧

本轮改动一度引入 +3 债务（SIM102 嵌套 if、F401 未用 `pytest`、`Setting` 导入因改用
`find_spam_hit` 后失去唯一使用点），已逐条**真修**（不是抬基线）。
债务 475 → **472**，基线同步 `--update` 压到 472 锁住改善。

### 兼容性

- 新增 1 个 Alembic 迁移（`d9f1a4c7b2e8`），`device` / `browser` 均为 `NOT NULL DEFAULT ''`，历史行不受影响。
- 新增后台页 `/admin/content-calendar`（`@login_required`）与设置项 `og_template`（留空 = 经典渐变）。

## v4.8.7（2026-10-24）

纯前端呈现打磨（后台访客统计页「表单数据」展示）：**无逻辑 / 无安全面变化，仅 CSS**。

### 一、数据表（`.stats-table`）统一美化

上一轮只美化了卡片 / KPI / 进度条 / 标签，但多张**数据表**仍是浏览器默认表格渲染
（`.stats-table` 在 `admin.css` 里仅有一行 `overflow-wrap`，无表头 / 边框 / 数值强调样式）。本轮补齐：

- 表头：小号弱化字、底部分隔线、禁止换行；数值列表头右对齐。
- 单元格：内边距、细分隔线、行 hover 高亮（accent 极浅底色）。
- **数值列**：右对齐 + `tabular-nums` 等宽数字 + accent 强调色，长数字不再左对齐发飘。
- 「区间访客数据」指标表加 `metrics` 类：PV/UV/真人/爬虫等数值放大到 18px 渐变描边，成视觉重点。
- 环比表的 `.tag-up / .tag-down / .tag-flat` 涨跌徽章**此前全局未定义**（裸文字），
  本轮在 `.stats-page` 作用域内补上绿涨 / 红跌 / 灰平三色胶囊。

全部限定在 `.stats-page` 作用域（`admin.css` 里诊断页用的 `.stats-table` 不受影响），
暗色主题同步适配。模板新增 `tests` 已含渲染用例（5 passed）。

## v4.8.6（2026-10-24）

三件事：**历史脏数据清理（数据操作，已在线上完成）+ 后台「常搜词汇」重置按钮 + 访客统计页 UI 美化**。

### 一、历史 `visit_log` 脏数据清理（线上数据操作，本次发版前已完成）

**背景**：站点套 EdgeOne 之前（v4.8.5 才接真实访客 IP 还原），`visit_log` 长期被 CDN 回源节点 IP 污染。发版前已整体备份并清空：

- 备份：`/www/wwwroot/myblog/data/blog.db.bak_before_visitlog_clear_20261024_172109`（5.1MB，已 `chown www:www`）。
- 清空前 **4722 行**（created_at 2026-08-25 ~ 2026-10-24）→ 清空后 0 行。
- **`search_log` 未动**（仅清访问日志，热搜词保留）。
- 清空走 `PRAGMA busy_timeout=60000` + `BEGIN IMMEDIATE` + 重试，规避 gunicorn 持 WAL 写锁导致的 `database table is locked`。

> 为什么不按「IP 段」删：用户的真实设备 IP（`116.16.142.74`）也落在 `116.16.x.x` 段内，
> 按段删会误杀真实记录。故采用「整体备份 + 整体清空」而非前缀过滤。

### 二、后台「常搜词汇」重置按钮（超管专属）

`myblog/admin/stats.py` 新增路由 `POST /admin/stats/reset-searches`：

- 权限：`@login_required` + `@super_required`（与既有 `/admin/audit-logs/clear` 同网关）。
- 防护：CSRF 由 `app.py` 全局 `before_request` 钩子统一校验（表单携带 `csrf_token`）；无 token 直接 403，且**不清数据**（`tests/test_stats_reset_searches.py` 正反双向覆盖）。
- 行为：`SearchLog.query.delete()` 全清空 → `log_audit("clear","search_log",...)` 落审计 → flash 提示 → 跳回 stats 页。
- 模板：`templates/admin/stats.html` 的「常搜词汇」卡片加 `card-head` 布局 + 重置按钮（带 `onsubmit` 二次确认）。

### 三、访客统计页 UI 美化

`templates/admin/stats.html` 大幅扩展 `<style>`，全部限定在 `.stats-page` 作用域（不影响其它后台页），并兼容明暗主题：

- 卡片柔和阴影 + hover 上浮 + 顶部渐变描边。
- KPI 大号渐变数字、横向条形图圆角发光平滑动画、24h 柱状图 hover 高亮。
- 常搜标签胶囊化 hover 上浮、区间切换圆角高亮 active、表格行 hover 高亮。
- 修复 `.card-head h3` 双下边框（提升选择器特异性到 `.stats-page .card-head h3`）。

### 安全审计

本轮新增 5 条测试（`tests/test_stats_reset_searches.py`），覆盖匿名拦截 / 普通管理员 403 / 超管清空 + 审计落库 / 缺 CSRF 拒删 / 页面渲染出按钮。完整套件 **1064 passed**。

## v4.8.5（2026-10-24）

两件事：**EdgeOne 真实访客 IP 还原**（统计失真的根治）+ **`update.sh` 不再绕开宝塔面板**。

### 一、EdgeOne 真实访客 IP 还原

**实测证据**：站点套腾讯 EdgeOne 后，线上 `visit_log` TOP IP 全是 `223.74.x.x` /
`116.16.x.x`（腾讯回源段），**单个 IP 426 次访问**——成千访客被合并成几个节点，
访客记录、实时在线、基于 IP 的限流全部失真。

**根因（关键，决定了方案）**：Nginx 配了
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`，它把 **EO 节点 IP
追加到 XFF 末尾**；而 `get_client_ip()` 取「XFF 最右端」→ 拿到的必然是节点 IP。
所以**只开 EdgeOne 的「客户端 IP 头部」标准开关也不够**（XFF 变成 `真实IP, 节点IP`，
取最右端仍是节点 IP）。

**方案**：读 EdgeOne 内置回源头 `EO-Client-IP`（控制台「站点加速 → 回源配置 →
客户端 IP 头部」打开即有，**不需规则引擎、不需猜变量**），并用共享密钥 `X-EO-Auth`
防伪造（需 EdgeOne 规则引擎「修改 HTTP 回源请求头」加一条）。

| 配置状态 | 行为 | 风险 |
|---|---|---|
| 只开 EO 开关，**没配** `EO_AUTH_KEY` | 采纳 `EO-Client-IP` | ⚠️ 该头可被直连源站者伪造 → 限流可被轮换假 IP 绕过。**换统计准确性** |
| 配了 `EO_AUTH_KEY` + 规则引擎加了 `X-EO-Auth` | 要求密钥匹配才采纳 | ✅ 不可伪造 |

未配密钥时**不退回旧行为**（旧行为=节点 IP，统计全废），否则功能在最常见配置下
根本不生效。密钥只走环境变量，绝不进仓库。

改动：`config.py` 新增 `EO_AUTH_KEY` / `EO_BLOCK_DIRECT`；
`utils/net.py` 的 `get_client_ip()` 新增第 0 级 EO 分支 + `_clean_ip()`（IP 合法性归一，
兼容 `1.2.3.4:5678` / `[v6]:443` / 裸 v6，拒脏值）；
`app.py` 新增 `enforce_edgeone_only()` 钩子（`EO_BLOCK_DIRECT` 开时才拦，默认放行，
放行 `/.well-known/`、`/api/health`、OPTIONS）。

### 二、`update.sh` 修复：不再绕开宝塔面板（v4.8.5 实测踩坑）

**现象**：在宝塔面板加环境变量后保存成功，但点「重启」报失败；站点其实正常。

**根因**：宝塔 Python 项目的启停**只认一个文件**
`/www/server/python_project/vhost/pids/<项目名>.pid`。而 `update.sh` 用 `setsid`
自己拉起 gunicorn，那个文件从没被更新 → 面板「重启」时：
① 停：读到的 pid 已是死进程，杀不到真实 gunicorn；
② 起：新 gunicorn 看到 `gunicorn_conf.py` 的 pidfile 里老 master 还活着 →
**拒绝启动**（`Error: Already running on PID xxx`）→ 面板报「重启失败」，
站长无法用面板启停项目。

> 面板有一个「按命令行兜底」的自愈逻辑，但它要求**唯一匹配**；gunicorn 的 master
> 与 N 个 worker 命令行完全相同，会匹配到 N+1 个 → **兜底失效**（读面板源码
> `pythonModel.py::get_project_run_state` 确认）。

**修复（两处）**：

1. **新增 `sync_panel_pid()`**：启动成功后把真实 master pid 写进面板的 pid 文件
   （优先读 gunicorn 自写的 `gunicorn.pid`，缺失时 `pgrep` 兜底）。启动日志会打印
   `✅ 已同步宝塔面板 PID（... = <pid>）—— 现在可在面板停止/启动本项目`。
2. **`setsid` 改为 `setsid -f/--fork`**：不带 `-f` 时，若调用方不是进程组组长，
   setsid 直接 `setsid()+exec`，**子进程的父进程仍是调用方** → 留下一个停在
   `do_wait` 等 gunicorn 的壳（实测：`update.sh` 自己就因此变成 ppid=1 的僵尸，
   每次部署都产生一个）。实测对比：

   | 方式 | 子进程 ppid | 父进程 |
   |---|---|---|
   | `setsid -f` | **1** | `/sbin/init` → 不留残壳 |
   | `setsid`（旧） | shell pid | `/bin/sh -c ...` → 留壳 |

   老版本 util-linux 没有 `-f` 时自动退化为裸 `setsid`（行为同旧版，不更差）。

### 三、验证

- `tests/test_edgeone_client_ip.py` **28 项**（含伪造攻击、无密钥取舍、向后兼容、脏值归一）；
  三处变异验证均实测变红（不校验密钥 / 不校验 IP 合法性 / EO 分支优先级降到 XFF 之后）。
- 真机验证：`setsid -f` vs 裸 `setsid` 的父进程对比见上表；
  面板 PID 同步后，模拟面板读取逻辑确认能识别到 master + 4 children。
- **无迁移、无表结构变更**（Alembic head 仍为 `c3d9e2f71a04`）。

### 四、需要站主手工配置（否则功能不生效）

详见 `docs/deploy/edgeone-real-ip.md`：
① EdgeOne 开「客户端 IP 头部」② （可选，防伪造）规则引擎加 `X-EO-Auth`
③ 宝塔加环境变量 `EO_AUTH_KEY` 并重启。

## v4.8.4（2026-10-23）

`update.sh` 部署前三查的两处**打磨修正**（v4.8.3 首次实战暴露）。应用代码零变更。

### 一、修掉 stderr 噪音（重定向顺序）

v4.8.3 的 argv 判据写成 `done < "/proc/$p/cmdline" 2>/dev/null` —— bash 会**先尝试打开文件**，
打开失败的错误先于 `2>/dev/null` 生效。于是瞬时进程消失时，日志里刷一行
`update.sh: line 374: /proc/1800279/cmdline: No such file or directory`，
**吓人但无害**。改为 `done 2>/dev/null < "/proc/$p/cmdline"`（重定向放在输入之前）。

### 二、日志明确化（不再「什么都不说」）

v4.8.3 只有 `pgrep` **完全没命中**时才打「✅ 无残留 update.sh 进程」；而实战中
`pgrep -f "update[.]sh"` 几乎总会命中一些**包装层**（MCP 的 bwrap / `sh -c`，
其命令行里含脚本文本），这些被 argv 精确判据排除后，日志**既不说「无残留」也不说排除了什么**，
看起来像功能没跑。现在区分三种情况：

- 有命中且全部是包装层 → `✅ 无残留 update.sh 进程（pgrep 命中 N 个，均为祖先链 / 包装层等非执行者，已按 argv 精确判据排除）`
- 有命中且清理了僵尸 → 原有的 `🧹 清理残留更新进程 …`
- 完全没命中 → `✅ 无残留 update.sh 进程`

### 三、v4.8.3 首次实战的验证结果（补记）

- `⓪ 部署前三查` 正常执行并打印当前线上版本；
- **脚本自检端到端跑通**：`脚本自检：本地 update.sh sha256=cb7ad49f…` →
  `✅ 脚本已是最新（与 v4.8.3 一致）`（经 gh-proxy 取 raw 成功）；
- 部署**照例留下一个僵尸**（`ppid=1` + `do_wait` + 0 个下载文件，正是三查设计要处理的形态）；
- 随后真机测试中，三查**自动清掉了那个真僵尸**，且 gunicorn master 被 init 接管、
  4 worker 完整、端口与公网 health 全程正常 —— **服务零影响**。

### 四、其他

- **无迁移、无表结构变更**（Alembic head 仍为 `c3d9e2f71a04`）。

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
SECURITY_AUDIT **R121**（`R120.5` 段已随 R111~R120 归档至 `docs/archive/SECURITY_AUDIT_r111-r120.md`）。

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
