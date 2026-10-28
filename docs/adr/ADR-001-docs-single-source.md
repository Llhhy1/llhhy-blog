# ADR-001：/docs 页面改为消费单一数据源（API.md）

## Status

Accepted（v5.3.0 实施）

## Context

`/docs` 页面原本是 `vue-frontend/src/views/DocsView.vue` 里 **1274 行手写 HTML**，
与 `myblog/API.md` 是**两份独立维护**的接口文档：

- `API.md` 是权威清单（v5.2.5 重写后覆盖 176 条 `/api/*` + 17 条后台 JSON 接口）；
- `DocsView.vue` 只手写了其中一部分，并在文案里写「完整清单以仓库 `myblog/API.md` 为准」。

两份独立维护的后果在 v5.2.5 后**实际发生了**：API.md 已全量重写并上线，
而 `/docs` 页面纹丝不动，读者在线上完全看不到新增的那十几个模块的接口。

更隐蔽的一点是：手写那份**已经过时**——它写的是 `utils.py`、`_current_user_or_none`
等拆包前的旧符号，而代码早已演进。也就是说，即使没有"没更新"的问题，
它也是一份**会持续误导读者**的文档。

## Decision

`myblog/API.md` 作为**唯一权威数据源**，`/docs` 页面不再手写任何接口清单：

1. 新增 `GET /api/docs`（`myblog/api/system.py`）：读取并渲染 `API.md` 返回 HTML，
   按文件 `mtime + size` 做进程内缓存；
2. DocsView 删除全部手写章节（520 行），整页 `v-html` 渲染该接口返回的内容；
3. 页面保留的**能力**（不是数据）：侧栏导航（由 `buildToc()` 从渲染后的 DOM 生成）、
   全文搜索（按 h2 小节建索引）、滚动高亮、回顶；
4. DocsView 里 API.md 原本没有的内容，迁移进 API.md：
   - SSR 页面与订阅源（表格）
   - `GET /api/docs` 自身的接口条目
   - 二次开发指南**不迁移**：API.md 的「如何新增一个 API」更准确且未过时

## Consequences

**变容易的：**

- 改 `API.md` → `/docs` 自动跟着变（mtime 变化即缓存失效），不再有"文档没更新"；
- 新增接口只需写一处；`tests/test_api_doc_sync.py` 的守卫（漏写/留残骸）足以覆盖；
- 渲染复用 `utils.render_markdown`（走 bleach 白名单），不引入与正文不同的 XSS 口径。

**变难的 / 代价：**

- 每次进 `/docs` 多一次 `GET /api/docs` 请求（已缓存，首次渲染约 3ms，后续命中缓存）；
- 页面样式要兼顾「API.md 里任意 markdown」的可读性（表格/代码块/引用），
  用 `:deep()` 限定在 `.doc-full-body` 内，不污染全局；
- `buildToc()` 原本按「一个 `.doc-section` = 一个章节」建树，整页只有一块时目录会退化成一条。
  已改为按 **h2（模块章节）+ h3（接口条目）** 建树；搜索索引同样改为按 h2 切片。

**被放弃的（记录在案）：**

- 手写文档里那些「为什么这么设计」的说明（如 CSRF 豁免理由、分页口径差异）
  在 API.md 中已有对应内容，但**叙述详尽程度不同**。若将来觉得 /docs 缺导读，
  正确做法是**补充 API.md**，而不是在前端再写一份。
