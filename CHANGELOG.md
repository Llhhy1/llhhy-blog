# 更新日志（CHANGELOG）

> **📦 历史归档**：v3.18.5 及以前 → `docs/archive/CHANGELOG_v1-v3.18.5.md`；
> v3.18.6 ~ v3.19.2 → `docs/archive/CHANGELOG_v3.18.6-v3.19.2.md`（v4.7.0 因体积守卫触发，按「新增轮次写进主文件、历史段落才归档」搬出）。
> v3.20.0 ~ v3.21.2 → `docs/archive/CHANGELOG_v3.20.0-v3.21.2.md`（v4.8.5 因体积守卫再次触发，按「新增轮次写进主文件、历史段落才归档」搬出）。
> v3.22.0 ~ v3.25.16 → `docs/archive/CHANGELOG_v3.22.0-v3.25.16.md`（v4.11.0 因体积守卫触发，主文件涨到 201 KB / 上限 200 KB）。
> v4.0.0 ~ v4.3.0 → `docs/archive/CHANGELOG_v4.0.0-v4.3.0.md`（v5.3.4 因体积守卫触发，主文件涨到 200 KB / 上限 200 KB）。
> v4.3.1 ~ v4.6.1 → `docs/archive/CHANGELOG_v4.3.1-v4.6.1.md`（v5.5.0 因体积守卫触发，搬走最老六个版本段）。
> 本文件从 **v4.7.0** 起。**归档不是删除** —— 查旧版本变更细节时去上述文件。

## v5.11.1（2026-11-12 · 列表页调性统一：页首覆盖面补齐 + 卷内序号）

把 v5.11.0 立下的章回调性扩到全部索引页。**接口向后兼容（`labels` 多 5 键）、无迁移、无新依赖、无表结构变更、`update.sh` 未动。**

- **覆盖面**：线上实测标签/热门标签/搜索/系列列表/系列详情/年度/统计 **7 页只有裸 `.page-title`**，与分类/归档页的「眉标 + 衬线大标题 + 朱砂计数」是两套语言。按 `CategoryView` 模式补 `v-if="chapterOn()"` 三件套 + `v-else` 经典分支，计数用真实数据。
- **调性**：`.zh-page-head` 原居中，与首页卷首 `left:9vw` 破格相反 → 改左对齐（文章页标题刻意保留居中）；`.zh-page-seal` 原灰描边灰字 → 改**实底朱砂 + 纸白字**（6.4:1，明暗都达标）。
- **卷内序号**：纸白区 `.post-card::before` 用 CSS counter 出 01/02/03，零模板改动零数据依赖，以 `:not(.zh-chapter-dark)` 锁死（实测首页暗色横卡为 `none`）。
- **眉标可声明**：`LABEL_KEYS` 加 `tags_en`/`search_en`/`series_en`/`annual_en`/`stats_en`，章回包同步声明，模板带 `|| 'TAGS'` 回退。
- **守卫**：新增 `tests/test_list_pages_v5111.py`（8 条）。第一版「至少一条规则带 `:not()`」被变异验证抓出漏判，改成「**每一条**含 `cardno` 的规则都必须隔离」后 3 种变异全捕获。
- **验证**：全量 **1534 passed**、ruff 0；真实浏览器 light/dark × 1280/390 覆盖 10 页，console 0 error、无横向溢出。

## v5.11.0（2026-11-11 · 设计北极星：调性可声明 / 可校验 + 文章页层级修复）

把「设计意图散在 5703 行 CSS 里」收成一份**可断言的规格**，并修掉 v5.10.0 诊断里最后一处「主角缺失」。
**接口向后兼容（展示层新增 `design` 键）、无迁移、无新依赖、无表结构变更、`update.sh` 未动。**

- **`DESIGN.md`（新）**：调性承诺 / 唯一难忘元素 / 6 条可判定硬指标 / 实测表 / 架构判定 / 新增主题包 checklist，成为视觉决策的单一真相源。
- **主题包 `design` 契约**：`theme_bundles.py` 新增 10 种调性枚举与 `_f_clamp`，`design` 块（`tone` / `signature` / `type_jump_min` / `accent_share` / `asymmetry`）经校验并入 `clean` 与 `public_bundle`；显式写错 `tone` 拒绝整包（与 layout 同策略）。章回包 1.0.2 → 1.1.0。
- **推翻旧判断**：内置主题包 `css: ""` **不是缺陷** —— `#site-bundle-css` 在 `myblog/templates/`、`vue-frontend/index.html` 与构建产物中均不存在，是 `/api/site` 之后由 `applyThemeBundle()` `createElement` 的运行时注入点；首屏视觉写进 `css` 必然 FOUC。取证与结论写进 `DESIGN.md §5` 并由守卫钉住。
- **文章页层级修复**：`.zh-page-title` 由 `var(--type-xl, 22px)` 改为 `clamp(30px, 3vw + 8px, 44px)` + `text-wrap: balance`。桌面 **44/16 = 2.75×**（原 1.38×），390 为 30px（1.88×，为可读性主动让步）。`font-weight` 保持 500：OFL 子集只有 400 字重，≥600 会触发合成粗体。
- **守卫**：新增 `tests/test_design_north_star_v5110.py`（8 条，5 种变异验证）；`test_theme_bundles.py` 的前台契约键集显式扩一项 `design` 并钉死 5 个子键。
- **验证**：全量 **1526 passed**、ruff 0；真实浏览器 1280/390 文章页 console 0 error、无横向溢出。

## v5.10.0（2026-11-10 · 章回视觉推到极致：一个主角 / 不对称 / 朱砂强调）

资深评审取证后由站主选定方向 **A**，P1 卷首 + P2 分卷 + P3 对比度一次交付。
**接口契约不变、无迁移、无新依赖、无表结构变更、主题包 schema 与 `update.sh` 未动。**

- **诊断**：线上实测卷首主标题 44px / 副标题 16px（仅 2.75×）、文章 H1 22px / 正文 16px（**1.38×**）；主题包 `css` 字段 0 字节、章回语言硬编码在 `look.css` 的 47 条选择器；全仓 114 个守卫。结论是「每处都安全地好看，但没有一处推到极致」。
- **P1 卷首**：主标题 `clamp(24px,5.4vw,44px)` → **`clamp(52px,9.2vw,118px)`**（跳跃约 7.4×）；`.home-cover-inner` 从居中改**左对齐 9vw**；`coverStyle` 遮罩改**左深右浅三段渐变**，但仍消费 `veilOpacity`，后台遮罩浓度滑块继续有效；`.zh-hero-badge` 从 12px 胶囊改**朱砂竖排印章**（复用 `data-enter="1"`，模板零改动）；新增 `.home-cover-title::after` 8px 朱砂粗横线；`.zh-update-bar` 从居中墨色胶囊改**右下角大字排版**。
- **P2 分卷**：`/api/site` 的 categories 只有 `{count,name,slug}`、**无 cover 字段** → 用 CSS counter + 纸纹做**程序化卷号封面**（零数据依赖、不改表）；`FEN JUAN` 水印放大到 `clamp(72px,12vw,164px)` 并改朱砂淡印，刻意用 `color` 的 alpha 而非 `opacity`（避开 reduced-motion 块里 `opacity:1 !important` 的突变）。
- **P3 对比度**：根因是 `global.css:1582` 的 `:root[data-card="row"] .post-card .read-more` 浅字规则权重高于 `look.css:885` 章回层朱砂规则，而 `data-card="row"` 是**全站**属性 → 暗色横卡区的浅字**泄漏到纸白分类页**（实测 1.25:1，AA 需 4.5:1）。已把作用域收窄到 `.layout.zh-chapter-dark`，亮色页回落朱砂（≥4.5:1）。
- **守卫**：新增 `tests/test_visual_max_v5100.py`（11 条，已变异验证：把主标题改回 44px 立刻变红）。全程不新建 CSS 文件、不新增 `@media` 块（断点棘轮只许减不许增）、不动 `[data-enter]` 五串与动效参数名、不改两份 `tokens.css`；`look.css` 的 P2 章回块一行未动。
- **工程约束**：字号沿用既有 `clamp()` 惯例（不命中 `FS_LITERAL` 正则），新增 `var(--type-*, Npx)` 兜底值全部落在 `FS_FALLBACKS` 收敛表内；朱砂一律走 `var(--accent, #a8442a)` 兜底形式。

## v5.9.0（2026-11-10 · 前台字体换为 OFL 子集：后端包 27.96 MB → 约 4 MB）

**背景（只读实测）**：`myblog-backend.zip` 压缩后 27.96 MB / 728 条目，其中京华老宋体
503 个 woff2 分片占 **24.63 MB（88%）**、文泉驿微米黑 2.24 MB、代码/静态仅 1.01 MB。
每次发版都要重传 29 MB，服务器直连 GitHub 仅 21~28 KB/s，`GH_MIRROR` 从可选变必需。
浏览器侧其实不重（分片按 `unicode-range` 按需加载，v5.8.0 实测首屏仅 27 请求 / 76 KB）
—— 真正的问题在**发布包**，不是访客加载。线上 13 篇文章 + 前端文案实测只用
**2089 个汉字**，命中 77/503 分片（4.88 MB）；京华老宋体授权「不可修改字体本身」，
无法子集化。

**决策**：改用 **Noto Serif SC / 思源宋体（SIL OFL 1.1）**，允许修改与再分发，
按站点真实用字生成单个 woff2。站主已确认接受观感变化（老铅印宋 → 现代规整宋）。
- 新增 `myblog/static/fonts/llhhy-serif-sc.woff2`（**0.61 MB / 2563 字形**，
  较 24.80 MB 缩小 **40.8 倍**）、`llhhy-serif-sc.css`、`OFL-NotoSerifSC.txt`
  （许可全文 + 版权声明）、`tools/build_subset_font.py`（可重复构建 +
  `--refresh` 从公开 API 刷新用字 + `--check` 自检）、`tools/font_charset.txt`
  （离线基线清单）。内部 family 改名 `LLHhy Serif SC`，避免与访客本机完整版混淆。
- **供应链**：源 OTF / OFL 全文从 GitHub raw 下载后逐一校验 sha256，不匹配即拒绝生成；
  `fonttools[woff]` + brotli **仅构建机依赖**，不进生产 requirements。
- 切换：`vue-frontend/index.html` 改挂新 CSS、`themes.py` 的 `font_sans` 首选改
  `LLHhy Serif SC`（回落链仍以 `serif` 收尾）；CSP `font-src 'self' data:` 一字未改，
  仍是自托管、无外链。🔴 **关键接线**：站主激活的是内置「章回」主题包
  `theme_packs/zhanghui.json`，它的 `tokens.light.font_sans` **也写死了旧字体**，
  而 `/api/site` 的 `theme_tokens.font_sans` 来自该包而非 `themes.py` 预设 ——
  **只改 `themes.py` 对线上零效果**（本地预览反代线上 API 时抓到 `bodyFont`
  仍是 `KingHwaOldSong` 才发现）。已同步改包内字体栈、desc，version `1.0.1 → 1.0.2`。
  🔴 **还有第三个真相源**：`themes.current_theme()` 优先读 `Setting.theme_tokens`
  持久化快照（站主切主题时落库），`/api/site` 的 `theme_tokens` 来自它 ——
  部署后实测公网仍返回旧字体名，导致「新字体上线了却没被使用」。
  已以 www 身份一次性修正 `light`/`dark` 的 `font_sans`（先备份到服务器
  `/tmp/theme_tokens_backup_v590.json`，`get_setting` 无缓存即时生效），
  并在 `FONTS.md` 写清三处同步纪律与回滚快照 `theme_look_prev_v1` 的残留。**CSS 不写 `unicode-range`**：子集外的字按字体栈优雅回落
  系统宋体，不 404、不白屏；emoji / 韩文由系统字形渲染。
- `package.py` 的 `EXCLUDE_DIRS` / `EXCLUDE_FILES` 显式排除旧 `kinghua/` 与
  `kinghua.css`（打包机残留也不会再进包）；`.gitignore` 保留旧两条 +
  新增 `tools/.font-source/`（11.6 MB 源 OTF 不入库）。
- 旧资产：`tools/fetch_kinghua_font.py` 保留作历史工具（守卫仍引用其幂等性），
  不再被部署流程调用；线上历史分片因 `rsync -a`（无 `--delete`）**不会自动删除**，
  已无人引用，仅占约 25 MB 磁盘，回收需站主手动确认。
- 守卫：同步 `test_audit_v543_sage_theme.py` 两处钉死 kinghua 的断言，
  新增 `tests/test_font_subset_v590.py`（字体三件套 / woff2 magic / 体积上限 /
  CSS 与字体栈一致 / 打包排除 / 许可全文 / 清单下限 / 旧 CSS 不再被引用）。

**验证**：vite build + 全量 pytest（基线 1493 只增不减）+ ruff 0；本地预览
真实构建产物 + 反代线上 API，按亮/暗 × 1280/390 真实浏览器验字体生效
（`document.fonts.check` / computed family / 无 404），console 0 error；上线后
三层核验 + 线上浏览器复核。**接口契约不变**、无迁移、无表结构变更、
无新增生产依赖、`update.sh` 未动。后端包预计降至约 4 MB；部署仍建议带
`GH_MIRROR`（沿用既有纪律）。

## v5.8.0（2026-11-10 · 动效层补齐与章回质感：三档 motion 落地 / 错峰渐入 / 卷首入场与分章揭幕）

按「资深开发评审」的取证结论动手：主题包 schema 早有 `MOTION_LEVELS = (off, subtle, full)`、后台主题中心有对应下拉、`store.js` 也确实注入 `data-motion`，但 `global.css` 只实现了 `off` 一档（3 条 `transition:none`），`subtle`（当前激活档）与 `full` **零规则** —— 站主在后台选「明显」不会有任何变化。本轮先补欠账，再做质感，未引入任何动效库。

- **P0 · 三档真正生效**：`global.css` 末尾新增独立动效层，用 6 个 `--motion-*` 参数把时长 / 阶梯延迟 / 位移幅度做成档位变量；`full` 明显强于 `subtle`，`off` 归零并彻底关掉动画。`look.css` 的 P2 章回语言层**一行未动**（该块禁 `@media` / 禁 `!important` / 每条选择器必须带 `:root[data-layout="chapter"]` 前缀），`tokens.css` 与 `main.js` 的三行 CSS import 也未动（守卫冻结，不能新建样式文件）。
- **P0 · 渐入错峰与扩面**：`v-reveal` 从「每个元素各 new 一个 IntersectionObserver、无卸载解绑」改成**模块级单例 + `unmounted` 解绑**；`binding.value` 传列表序号，写入 `--reveal-delay`（55ms 递增、封顶 7 档，防长列表末卡久等）。覆盖从首页 8 张卡扩到**首页卡 + 分卷卡 + 分类页卡**。经典主题与无主题包时 `var()` 兜底值等于旧行为，观感不变。
- **P0 · 滚动性能**：`App.vue` 的 `onScroll` 旧实现每次滚动写 `bar.style.width`（触发 layout）且不合帧；改成 **rAF 合帧 + `transform: scaleX()`（合成层）**，回顶按钮从 `display:none/block` 硬切改为 `.is-visible` 的 opacity/pointer-events 过渡。
- **P1 · 卷首阶梯入场**：`HomeView.vue` 给徽章 / 标题 / 副标题 / 社交图标 / 最近更新胶囊加 `data-enter="1..5"` 序号钩子（不新增 class、不碰被白字守卫静态扫描的 `.home-cover-title` 选择器），CSS 按 `--motion-stagger` 递延。`fill-mode` 用 `backwards` 而非 `both` —— 动画结束回到原有可见样式，不锁末态、不影响 LCP 与主题切换。
- **P1 · 明暗分章揭幕**：分卷区默认**完全可见**（不依赖 JS），IO 命中后才追加一次性 `.is-revealed` 播一段 `clip-path` 自上而下展开 —— 即使 IO 不可用或 JS 出错也不会白屏。只加过渡，**不改「突然切到纸白」的硬切语义**。🔴 这里踩了一个真坑：`theme_bundle` 由 `/api/site` 异步回填，子组件 `onMounted` 时 `isChapter` 多半还是 false、`v-if` 的 section 尚未渲染，直接取 `lightRef` 会拿到 null 且再不重试 —— 改成 `watch(lightRef, ..., {flush:"post"})` 等真实 DOM 出现再观察。
- **P1 · 其余质感**：顶栏「浮在壁纸上 → 滚过首屏变实心」**复用** `HomeView.vue` 已有的 `_coverIO` / `.is-solid`，只给这个切换补颜色与毛玻璃过渡，不重造逻辑；`FEN JUAN` 水印视差只在 `full` 档 + `@supports (animation-timeline: view())` 成立时启用，Safari / 老浏览器完全静态，无需 JS 兜底。全部动效只用 `opacity` / `transform` / `clip-path`，不碰 `width` / `top` / `left`。
- **无障碍**：`off` 档与 `prefers-reduced-motion` 都彻底静态并强制可见。既有全局兜底只压 `animation-duration`、**不压 `animation-delay`**，阶梯入场的延迟若不显式清掉，开了「减少动态效果」的用户仍会看到元素先隐藏一小会儿 —— 本轮补上。
- **守卫**：新增 `tests/test_motion_layer_v580.py`（11 条），钉住三档参数强度递增、错峰延迟被消费、单例 IO 与卸载解绑、进度条不再写 width、五个入场序号齐全、`backwards`、揭幕默认可见且用 `watch`、水印视差仅 full 档、动效不污染章回层、不新建 CSS 文件、主题包档位契约未变。
- **验证口径**：vite build、全量 pytest、ruff、compileall；真实浏览器按 1280 / 390 两档 × 亮 / 暗 × 开启 reduced-motion 复核，比对首页三段式、文章页、分类页与控制台 0 error。

**接口契约不变**（`API.md` 只 bump 头部版本）、无迁移、无新依赖、主题包 schema 未改、`update.sh` 未动、无表结构变化。**前端 CSS/JS 与模板都改了 → 必须重新 `vite build` 再打包**；后端包仍约 29 MB，一键更新必须带 `GH_MIRROR=https://gh-proxy.com/`。

## v5.7.0（2026-11-08 · 设计系统收口二期：后台去内联 / 暗色 token 化 / 排版尺度统一）

承接 v5.6.0 明确延后的四项，本轮全部落地。

- **后台模板去内联**：新增 `myblog/static/admin-pages.css`，把各页静态内联 `<style>` 抽取到共享文件，由 `admin/base.html` 在 `admin.css` 之后引入（tokens 变量先加载）。**刻意保留**：`base.html` 的两个动态注入块（`:root` 主题注入、`custom_css`）、响应式卡片化基座（`td[data-label]::before`）、`backup.html` 的 `bk-table` 卡片化规则、`theme_center.html` 的市场样式 —— 前两者含 Jinja 变量，后三者被 `test_admin_table_data_label.py` / `test_base_css_规则与守卫同口径` 按「规则在模板内」钉死，搬走会让守卫假红。内联块数量 **14 → 11**（守卫按字符串计数，含 content_calendar.html 里 JS 字符串中的 `<style>` 字样；真实块 10 个），`test_admin_componentization.py` 棘轮同步下调。
- **宏全量迁移**：`admin/_components.html` 的 `btn` / `empty_state` / `section_title` 等宏从 3 个高频页扩到全部能找到逐字等价静态片段的模板；每处都是「1 行 from-import + 1~2 行替换」，可逐行回退。表单 action/name、CSRF 隐藏字段、`data-label`、`aria-label`、`hidden` 一个没动，`theme_center.html` 只有 `<style>` 段与元素内联样式的字号/行高走尺度，市场卡片的上色逻辑与页面 JS 一行未动（该页禁用 CSS 变量上色）。
- **暗色硬编码 + 裸 hex 收敛**：`admin.css` 与 `static/style.css` 里与亮/暗语义 token 精确相等的裸色统一改成 `var(--token, #原值)` 兜底写法；暗色段写死的灰阶（`#e6e8eb` / `#9aa0a8` / `#333842` 一类）改走 `[data-theme="dark"]` 的对应 token，消除「暗色另有一套 hardcoded 灰阶」的双真相源。渐变端点色、状态徽章专用底色、阴影 rgba 保留并登记理由。`static/style.css` 非兜底裸 hex **156 → 21**；`admin.css` 的降幅由 `test_css_token_ratchet.py` 的新基线记录。所有替换都带兜底值，token 未加载（旧缓存 / 旧模板）时表现不变。
- **排版尺度统一**：两份 `tokens.css` 同步扩到 **13 级字号**（`--type-3xs` … `--type-display`）+ **7 级排版行高**（`--leading-flat` … `--leading-relaxed`）与 2 个布局专用档（`--leading-none: 0` / `--leading-double: 2`）；SPA CSS、Vue SFC 全文（含 `<template>` 内联 `style`）、`admin.css`、`static/style.css`、`admin-pages.css`，以及后台模板全文（含元素内联 `style`）里，原先 **21 种 px 字号 / 19 种行高字面量全部归零**，每处带 `var(--token, 原值)` 兜底。模板内联 CSS 的**颜色**按动态注入 / 守卫依赖 / 市场卡片配色的边界保留原样，不在本轮收敛范围。新增 `tests/test_typography_scale_v570.py`：断言全库零字面量、两份 tokens 的尺度定义逐字一致，**反查每个兜底值确实落在收敛映射表内**（防 `var(--type-sm, 19px)` 把新尺度架空），并钉住「`var(--leading-*)` 后必须有分号或规则闭合」—— 批量替换曾把 `line-height: 1.6;` 的分号吃掉，写成 `... 1.6) color: ...`，浏览器静默丢弃整条声明，全库共修回 36 处。`test_design_system_v560.py` 的字号棘轮由 18 收紧到 **0**。
- **验证口径**：全量 pytest、ruff、compileall、`vite build`；真实浏览器用「本地构建产物 + 反代线上真实 API」的预览服务，逐页对比首页 / 文章 / 分类 / 归档 / 登录页的亮暗两套表现，不用手写等价 DOM。

**接口契约不变**（`API.md` 只 bump 头部版本）、无迁移、无新依赖、主题包 schema 未改、`update.sh` 未动。**前端 CSS 与后台 CSS 都改了 → 必须重新 `vite build` 再打包**；后端包仍约 29 MB，一键更新必须带 `GH_MIRROR=https://gh-proxy.com/`。

## v5.6.1（2026-11-08 · 章回内页网格回归修复）

> **来源**：v5.6.0 上线后的「真实浏览器逐项核验」抓到的真问题，不是本地推测。
> 按回归修复闭环补一个补丁版并重新发版上线；v5.6.0 的四个阶段内容不变。

- **现象**：章回主题（`sidebar=hide`）下，文章页与分类页内容整体偏左、右侧约 300px 空白。
- **根因**：`global.css` 把侧栏设为 `display:none`，但 `.layout` 的网格仍是
  `698px 300px` 两条轨道 —— **隐藏元素不会让 grid 轨道消失**。线上实测
  `gridTemplateColumns = "698px 300px"`、`content x=204 w=698`、`frame x=170 w=1100`。
  这是 v5.5.0 主题包引入布局原语时就存在的实现缺口，站主激活章回后一直可见。
- **修法**：`look.css` 章回语言层补两条规则 —— `data-sidebar=hide` 时收成单轨、
  正文限宽 760px 居中；**选择器必须带 `:not(.zh-chapter-dark)`**，否则首页
  `display:block` 的两列横卡会被挤窄。修复前先在真实浏览器注入等价样式模拟，
  截图确认分类页与文章页两侧留白均衡、无重叠，再落到源码。
- **守卫**：`test_chapter_coverage_v560.py` 新增一条，钉死「收单轨 + 居中 +
  排除首页暗色分卷」三件事；变体（去掉 `:not(...)`）会立刻变红。
- **口径**：纯 CSS 补丁，接口契约不变（`API.md` 只 bump 头部）、无迁移、无新依赖、
  不改 `update.sh`；主题包 schema 与后台模板均未动。前端改了 `src/styles/look.css`
  → **必须重新 `vite build` 再打包**。后端包仍 29 MB，部署必须带 `GH_MIRROR`。

## v5.6.0（2026-11-08 · UI 深度优化四阶段：章回贯通 / 四态 / 设计系统 / 后台组件化）

> 依据 `docs/audit/2026-10-31-v5.3.3-audit-and-theme.md` 的 7 类观感问题与
> 「三套主题管线仍未合并，是下一轮视觉升级的主要工作」结论，按 **P1 → P2 → P3 → P4**
> 依赖顺序一次发版。**四个阶段各自可独立验证，未跨阶段混改。**

### P1 · 状态与刻度

- 新增 `vue-frontend/src/components/AsyncState.vue`：骨架 / 空 / 错误+重试 / 正常四态统一，
  容器常驻 `role="status" aria-live="polite"`，颜色全走设计系统变量、零裸 hex。
- `CategoryView.vue` / `ArchiveView.vue` 接入四态：原来请求失败会把分类名或「暂无文章」
  当成空列表，现在能区分 loading / empty / error 并可重试。首页保留其专用三卡骨架，不强迁。
- `App.vue` / `store.js` 的静默 `catch` 补用户可见提示，降级行为不变。
- 新增断点棘轮守卫 `tests/test_ui_state_layer.py`：扫描 `@media` 硬编码像素值，
  只允许减少、不许新增；同时钉死 `main.js` 的三文件 CSS 导入顺序。
  ⚠️ 原生 CSS 变量不能用于 `@media` 条件，所以「统一刻度」是**约定 + 扫描守卫**，不是变量替换。

### P2 · 章回贯通（消除「首页章回、点进去变经典」）

- 新增 `vue-frontend/src/styles/look.css` 末尾的「章回全站语言层」：纸白 / 墨色 / 朱砂 /
  衬线标题贯通到首页以外的视图；**每条选择器都以 `:root[data-layout="chapter"]` 开头**，
  并用 `:not(.zh-chapter-dark)` 排除首页暗色分卷，避免最后加载的 look.css 盖掉横卡暗底。
- 新增 `vue-frontend/src/lib/chapter.js` 作为章回判定单一入口；
  `PostView.vue` / `CategoryView.vue` / `ArchiveView.vue` 补结构钩子（眉标 + 衬线大标题 + 朱砂计数），
  经典分支 DOM 一行不变。**不做 DOM 重构**（ADR-001 已放弃需重构 DOM 的结构性版面）。
- 分卷区不再硬砍前 4 类（`HomeView.vue` 去掉 `slice(0, 4)`），列数改 `repeat(auto-fit, …)`；
  恰好 4 个分类时观感与原 `repeat(4)` 一致。
- 新增 `tests/test_chapter_coverage_v560.py`：逐条扫描语言层选择器前缀、暗色分卷排除、
  壁纸联动 18 处不减少、cover 标题白字守卫、`data-columns` 契约不变。
- ⚠️ 列数仍是 `store.js` 注释里记录的四条 `repeat(N, …)` 规则：`repeat(var(--n), 1fr)`
  的计数位在 Chrome 判为计算值期无效，会静默塌成单列，**这是刻意保留的兼容性写法**。

### P3 · 设计系统收口

- SSR 登录 / 错误页（`myblog/templates/base.html`）补引 `tokens.css`，与 SPA `global.css`
  的 `@import`、后台 `admin.css` 的 `@import` 形成**三面共享同一份真相源**；
  `tests/test_design_system_v560.py` 钉死加载顺序与两份 tokens 变量集合 / 取值一致。
- `myblog/static/style.css` 8 处次级灰字（`#999` 压白卡 **2.85:1**）统一到
  `var(--text-muted, …)` + `--type-meta`：实测 **4.9:1**，13px 小字过 4.5:1 门槛；
  非兜底裸 hex 从 177 降到 **156**（棘轮只减不增）。
- 新增「真实页面组合」对比度守卫：不再只校验 token 对，而是计算 `.post-meta` 前景压
  `.post-card` 白底的实际比值，并用旧灰值作反证。
- 字号尺度棘轮：SPA 四份 CSS 共 **18 种** px 字号，守卫只允许减少；新增语言层一律用 `--type-*`。
  27 种字号 / 24 种行高的**全量收敛不做**（会牵动 `themes.py:_BASE_LIGHT` 双向绑定与视觉回归），
  改为先用棘轮止住新增。
- 确认 `look.css:43` 与天气组件按钮的圆角冲突已在既有版本收口，补守卫防回退。

### P4 · 后台组件化（一期）

- 新增 `myblog/templates/admin/_components.html`：`btn` / `card` / `empty_state` /
  `field_hint` / `section_title` 五个宏，只复用 `admin.css` 已有类、参数自动转义、不输出脚本。
- 在 3 个高频后台页小范围落地（不改表单 action / name / CSRF / `data-label`），
  新增内联 `<style>` 棘轮守卫 `tests/test_admin_componentization.py`。
- 明确**未做**：其余 52 个模板的批量迁移、后台暗色硬编码全量 token 化、
  `test_css_token_ratchet.py` 里 admin.css 234 处裸 hex 的收敛 —— 这些都需要单独的设计决策，
  本版用棘轮止住新增，不假装已经做完。

### 发布与部署口径

- **接口契约不变**：`API.md` 仅 bump 头部版本；无新增 / 修改接口、无环境变量变化、
  主题包 schema（`theme_bundles.py`）一行未改、导入包仍禁 CSS。
- **无数据库迁移、无新依赖、不改 `update.sh`**；`alembic_version` 仍 `b7c2e91a4d63`。
- **前后端都改了**：`vue-frontend/src/**` 必须先 `vite build` 再打包（`package.py` 打 `_vite_build30/`）；
  后端包仍约 29 MB（503 个字体分片），一键更新**必须带 `GH_MIRROR`**。

## v5.5.1（2026-11-07 · 主题说明整理与发布检查修复）

- 精简「章回」主题元数据、更新日志与路线图；主题包版本为 1.0.1，配色、布局、字体和功能不变。
- 删除主题设置读取的重复异常兜底；主题库解析显式区分无应用上下文与数据库异常，不再吞掉程序错误。
- 修复 v5.5.0 新增的 6 条 BLE001，沿用原 lint 债务基线，不放宽门禁。
- 同步版本文档，重新构建两个部署包并生成哈希与 Ed25519 签名。无数据库迁移、无新依赖。

## v5.5.0（2026-11-07 · 主题包「章回」+ 主题工坊 + 主题市场 + 外观回滚）

> 站主要求「升级主题定制、上架主题市场，并先做一套自己觉得好看的主题」。方向澄清后定为
> **站主主题库**：主题只有超管能换，部署本系统的人可以换自己想要的；**访客换肤不回归**
> （v5.4.5 下架的档 1 缺席守卫原样保留）。三步（地基 / 工坊 / 市场）一次发版。

### A. 架构决策（ADR-001 定案，记录取舍而非只记做法）

| 决策 | 换来了什么 / 放弃了什么 |
|---|---|
| 主题包 = 纯声明式 JSON（`theme_packs/*.json`），布局靠 `data-*` + CSS 变量驱动 | 换来换主题可逆、24 个视图零改动、第三方包无需代码审核；放弃三栏 wiki 这类需要重构 DOM 的结构性版面 |
| 主题库存 `Setting` KV，不建表 | 换来不动生产 schema、零迁移；放弃索引与无限容量，改为 24 套 / 单套 16 KB / 总 192 KB 三道上限（后台低频写入可接受） |
| 布局用「原语 + 有限结构钩子」，不做视图级布局组件 | 换来主题包与前端组件版本解耦；放弃 CSS 表达不了的自由度 |
| 回滚存五个 Setting 原值整组回写，不存主题 id 再重放 | 换来可逆性最强、不会漏键造成「颜色回来了但布局没回来」；代价是快照体积略大 |
| 三层信任边界：内置只读 / 站主自建 / 第三方导入（**禁 CSS**） | 换来导入包仍能用颜色、字体、版面，且信任级别清晰；放弃第三方 CSS 兜底片段，市场卡明确标注 |

**19 处** `:root:has(.home-cover.has-wall)` 壁纸联动未改动，主题包契约显式声明
`layout.hero = required | optional | none`；「章回」取 `required`，将来切到无首屏版面时须提示壁纸停用。

### B. 落地内容

- **① 地基**：`myblog/theme_bundles.py`（schema 白名单 + OKLCH 暗色推导 + 受限 CSS 命名空间）、
  `myblog/theme_packs/zhanghui.json`、布局原语 CSS、`HomeView.vue` 的 `isChapter` 结构钩子。
- **② 工坊**：`myblog/theme_library.py`（库 CRUD + 五键快照/回滚）、后台可视化编辑器
  （38 字段：拾色器 / 版面枚举 / 栏目文案）、**真实前台 iframe 预览**、一键回滚（可反悔）。
- **③ 市场**：内置 / 自建 / 导入三类卡片，应用 / 编辑 / 导出 JSON / 复制副本 / 删除；JSON 导入走严格模式。
- **接口契约**：`GET /api/theme` 增主题包摘要、`POST /api/theme` 支持 `bundle_id`（含 `lib:` 前缀）
  并返回 `prev`；新增 `GET/POST /api/theme/library`；`GET /api/site` 下发 `theme_bundle` 展示层。
  `myblog/API.md` 全量同步（头部版本与 `APP_VERSION` 一致）。

### C. 本版修掉的真问题

- **半新半旧**：编辑器提交的是校验补齐后的完整 token，若原样落库，`normalize_custom_theme`
  见 `accent_hover` / `accent_soft` / `info` / `text_muted` 已存在就**不重算** —— 改了主色但 hover
  与整套暗色还停在旧主题。保存前剥掉派生键与 `dark`，让服务端按新亮色重推。
- **回滚快照时序**：`capture_look()` 必须在任何 `set_kv` 之前，否则 SQLAlchemy identity map
  会读到同一 session 里尚未提交的新值。
- **PV 翻倍**：后台预览 iframe 会重新加载前台、重跑统计脚本；前台 `initSite()` 见
  `tc_preview=1` 跳过 `injectFooterCode`，自定义 CSS 照常注入。
- **两条既有守卫正确拦下新代码**：带 placeholder 的 textarea 缺 `aria-label`；市场卡片用 CSS
  变量上色违反「后台配色只来自 tokens.css」，改为 inline 具体属性（连注释里的 `setProperty`
  字面量都会被逐行文本扫描命中）。
- **视觉**：无壁纸时 `.home-cover` 仅 300px，「最近更新」胶囊压住副标题；胶囊半透明底在米色
  浅底上糊成浅灰、链接落回默认蓝。已改 `min-height:460px + padding-bottom:118px`（仅
  `:not(.has-wall)`）与深墨实底 + `--zh-ink-fg` 接管链接色。

### D. 验证与部署注意

- 全量 pytest **1439 passed**；ruff 0；`npm run build` ✓。变异验证两条关键守卫（派生 token
  归一化 / 导入 CSS 剥离）改坏均变红。
- 真实浏览器（本地 Flask + Vite dev + 隔离库 6 篇文章）：改主色 → 应用 → 快照 → 导入 → 回滚
  全链路；「章回」首屏 / 暗色卷一两列横卡 / 纸白分卷区三屏截图核验。
- **后端与前端都改了 → 两个包都要覆盖**；前端动了 `store.js` / `global.css` / `HomeView.vue`，
  **必须先 `npm run build` 再打包**。无迁移、无新依赖、无改 `update.sh`。
- 后端包仍含 503 个京华老宋体分片（v5.4.4 起 ~29 MB），一键更新**必须带 `GH_MIRROR`**
  （直连实测 21~28 KB/s 会顶爆 `--max-time 180`）。
- 文档瘦身：CHANGELOG 逼近 200 KB 上限，按「归档不删除」把 v4.3.1~v4.6.1 搬进
  `docs/archive/CHANGELOG_v4.3.1-v4.6.1.md`，主文件留指针并登记 `test_doc_archival.py` 的 PAIRS。

## v5.4.5（2026-11-03 · 自定义页脚代码 + 访客自选主题下架）

> 来源：分支 `feat/footer-code-and-tier1-removal`（待合并）。站主反馈：档 1「访客自选主题」是多余功能，拆掉；要一个能自己写页脚代码的入口。

### A. 自定义页脚代码（`footer_html`）

- 后台「站点设置 → ① 站点信息」新增 textarea（挨着页脚文字/备案号），内容**原样输出**到页脚：统计代码、自定义链接、版权行都行。
- **不做任何清洗**（转义 `<` 或剥 `<script>` 会让头号用途失效）。信任边界改由三处守住：
  ① 只有 `@super_required` 的 `/admin/settings` 能写（普通管理员 403，移动端 `_SETTING_KEYS` 只读、MCP 无写入口）；
  ② 长度上限 `FOOTER_HTML_MAX = 20000`（它进的是**每个前台页面**，防误粘贴整份 HTML）；
  ③ 改动写一条审计日志（`target=自定义页脚代码`），值没变不刷日志；同时进配置快照 → 可回滚。
- **前端脚本会真的执行**：`v-html` / `innerHTML` 插进去的 `<script>` 按规范不运行，所以 `store.js:injectFooterCode()` 插入后把每个 script 换成新建元素（内联与外链同路）；`data-src` 比对保证幂等，SPA 换路由不会把统计脚本重跑一遍（否则 PV 翻倍）。
- SSR 侧（`templates/base.html`，登录/注册页）`| safe` 直出。注意 CSP：Flask 渲染的页面 `script-src 'self' 'unsafe-inline' 'unsafe-eval'` → **内联脚本可跑，外链 `<script src="https://…">` 会被拦**；SPA 首页由 nginx 直出、不带 CSP 头，所以站外统计代码在前台正常加载。
- 接口契约：`GET /api/site` 新增 `footer_html`（恒有键，未配置为 `""`）。

### B. 档 1「访客自选主题」下架

- 删除范围：`themes.ALLOW_VISITOR_KEY` / `visitor_theme_allowed()`、`POST /api/theme` 的 `visitor_theme` 分支、`GET /api/theme` 与 `GET /api/site` 的 `allow_visitor_theme`、主题中心开关卡片、`ThemePicker.vue`、`store.js` 的 `themePacks`/`visitorPack`/`loadThemePacks`/`setVisitorTheme`/`VISITOR_THEME_KEY`、3 个 i18n 键、`tests/test_audit_v542_visitor_theme.py`（23 条）。
- **保留**：批次 D 的主题校验加固（`tests/test_audit_v543_sage_theme.py`、`test_audit_v542_theme_input.py` 不动）与第 15 套预设「青野」。
- 新增缺席守卫 `test_visitor_theme_switch_is_gone_from_code`：扫 `myblog/`、`vue-frontend/src/`、`tests/`、`tools/`，任何残影（含 `localStorage` 键名）即变红 —— 本项目由 AI 协助维护，留残影等于邀请下一次改动把它接回去。
- 线上库里那行 `allow_visitor_theme` Setting **不用清**：已无人读取，留着无害；`localStorage` 里访客存过的 `visitorTheme` 同理。

### C. 验证

- 新增 `tests/test_footer_html_v545.py`（19 条）：原样存/原样输出（含「登录页 302 导致断言假绿」的坑已用匿名 client 规避）、超限拒绝且其他字段照常保存、边界值恰好可存、普通管理员 403、无 API 写入口、审计一条且不重复、进快照、前端契约（mount + 重建 script + 幂等）、档 1 缺席扫描。
- 全量 pytest / ruff / `lint_debt`（基线不放宽）/ `check_i18n` / `vite build` 见 PR。

### D. 部署

- **前端有改动 → 必须 `npm run build` 再打包**（`App.vue`、`store.js`，并删了 `components/ThemePicker.vue`）。
- **无数据库迁移**：`footer_html` 是 Setting KV（`_ensure_settings` 会补默认空值行）。旧前端配新后端 → 少一个页脚 div，不报错；新前端配旧后端 → `footer_html` 缺失即不注入。

## v5.4.4（2026-11-02 · 主题「青野」+ 京华老宋体自托管 + 主题 token 真正被消费）

> 来源：PR #36 `feat/sage-theme`（2 提交 / 12 文件 / +482−28，`mergeable_state=clean`），本地快进合并为 `3288b15`；同批并入 PR #37（Dependabot：`github/codeql-action` 3→4，只改 `.github/workflows/codeql.yml`，不进部署包）。

### A. 第 15 套预设「青野」（`sage-sand`）

- 浅鼠尾草 + 沙橙的纸感方向：bg `#f5f5f5` / surface `#fff` / surface_2 `#efefe8` / text `#333` / 圆角 10-15-20 / 单层柔影 / 行高 1.62。
- **accent 没有直接拿浅绿用**：`#7ea774` 白字只有 2.74:1、当链接压 `#f5f5f5` 只有 2.51:1，过不了 `test_wcag_contrast.py` 的 4.5:1；accent 取同色相加深的 `#4e7544`（白字 5.31:1），`#7ea774` 原封留在 `accent_soft` 当 wash / 标签底 —— 观感来源保住，不靠放宽断言换可读性。

### B. 京华老宋体自托管（`tools/fetch_kinghua_font.py`）

- 官方 cn-font-split 产物**原样**落地：503 个 woff2 / 24.8 MB + 生成的 `kinghua.css`（只把路径改成本地、只补 `font-display: swap`，不动字体二进制）。
- **不入 git**（`.gitignore` 只加 `kinghua/` 与 `kinghua.css` 两条，`fonts/` 其余照旧入库），但**会进后端 zip**：`package.py` 的 `add_tree()` 递归收 `myblog/`，后端包体积由 ~5 MB 涨到 ~30 MB。不想带就删掉这两条路径再打包，前台回落 `Noto Serif SC / Songti SC / SimSun / serif`。
- 为什么必须自托管：CSP 是 `font-src 'self' data:`（`security.py`），hotlink 会被浏览器直接拦掉；即便放开，也是让每个访客替本站去请求第三方（IP/UA 外流）。
- `--check` 是部署后唯一的自检入口；它读**改写后**的 CSS —— 正则只认官方原始路径时会数出 0/0 并「报就绪」（本轮实际踩过）。
- `vite.config.js` 给 dev 补 `/static` 代理：本地不再出现「字体不生效、壁纸 404」的假象。

### C. 主题 token 终于被消费（换色才露出来的硬编码蓝）

- `body` 之前写死系统无衬线栈 + `line-height: 1.7`，主题包的 `font_sans` / `line_height_base` **从来没生效**（实测全站只有后台预览卡用了 `var(--font-sans)`）。改接 `var(--font-sans)` / `var(--line-height-base)`；`tokens.css` 的 `--font-sans` 与原栈逐字相同 → 其余 14 套外观不变。
- `.home-cover` 无壁纸首屏：旧渐变终点写死 `#6aa9ff`（蓝色专属），14 套里 13 套是「主色→蓝」的脏渐变。改为主色淡 wash + 深字；配壁纸走 `.has-wall` 分支，仍是图上白字 + 双层阴影。
- `.home-hero` 渐变终点 → `var(--accent-hover)`、投影 → `var(--shadow-lg)`；抽屉 hover / 热门标签 / 统计卡光斑 / 手机汉堡投影等 6 处 `rgba(25,109,221,…)` → `--accent-soft` / `--ui-fill` / 中性黑。
- `.post-body a` 补 `color: var(--accent)`：此前只有断行规则、没有颜色，链接一直是浏览器默认蓝。

### D. 兼容与代价

- 无接口契约变化、**无数据库迁移**；`API.md` 仅版本号同步。新增 `tests/test_audit_v543_sage_theme.py`（9 条：预设可读性、token 真被 CSS 消费、字体 link 与 CSP 一致、分片不入库、`build_css` 幂等、正文链接跟随主题、无硬编码蓝、白字只作用于壁纸态）。
- 首次部署多一步：分片不在仓库里，打包机上必须跑过 `python tools/fetch_kinghua_font.py`，否则包里没有字体（不报错，只是回落系统宋体）。

### E. 验证

- 合并后本机：`npm run build` ✓（`_vite_build30` / 5.87s）、全量 pytest 1405 passed；两条失败均为版本号守卫（`myblog/README.md` 未同步、CHANGELOG 缺本节），补齐后定向复跑转绿；字体 `--check` = 503/503 齐全。

## v5.4.3（2026-11-02 · 批次 D 主题校验加固 + 档 1 访客自选主题（默认关））

> 来源：PR #35 `feat/theme-validation-and-picker`（5 提交 / 23 文件 / +1146−40，CI 6/6 通过），本地快进合并为 `a4e4599`。完整说明见 `docs/audit/2026-11-01-v5.4.x-batch-D-and-tier1.md`。

### A. 批次 D：4 个 P2 收口（共同点是「值被原样搬进 CSS/XML 上下文」）

| 面 | 之前 | 现在 |
|---|---|---|
| `custom_css` | 只转义小写 `</style`，`</StYlE><script>` 可逃逸出样式上下文 | `utils.css_context_escape()` 大小写不敏感；写入侧再拒一次 `</` |
| `accent_color` | 原样拼进 SSR `--accent: {{…}}`，可注入任意 CSS 规则 | `themes.validate_accent()` 写入校验 + 渲染前再洗（`accent_hex`） |
| 自定义主题 token | 只判 `light.accent` 存不存在，任意键值落库 | 键走白名单、值按类别校验；非法 400 + 逐条 `details`；读侧 `current_theme()` 再洗一遍 |
| `post.lang` | 只 `strip()`，`x'><script>…` 能落库 | `normalize_lang()` 写入收敛 + 4 处输出转义 |

### B. 档 1：访客自选主题（默认关）

- 主题中心新增站主总开关（Setting KV `allow_visitor_theme`，**默认关**；首次保存才建行 → **无迁移**）。
- 开放后前台顶栏与手机抽屉各出现一个选择器，访客可在 14 套预设里挑；选择**只写自己的 `localStorage`**，不改 Setting、不影响其他访客。
- 站主关掉开关 → 选择器不再渲染，访客残留选择立即失效。
- 接口变化：`GET /api/theme`、`GET /api/site`、`POST /api/theme` 的返回多 `allow_visitor_theme`；`POST /api/theme` 新增 `visitor_theme`（只收 `true`/`false` 或 `"true"`/`"false"`，其他一律 400）。**`API.md` 已同步这三处契约。**

### C. 行为变化（会咬到存量脚本，先看一眼）

- `POST /api/theme` 的 `custom` **变严**：未知 token 键、`url(...)`、颜色名 `red`、`12px; body{…}` 一律 400（`details` 逐条说明）。以前是静默收下并落库 —— 历史主题 JSON 导入前要先按文案清理。
- 自定义主题现在**补齐基准**：只传 `accent` 也得到完整一套 token，且 `accent_hover / accent_soft / info / text_muted / text_faint` 按新主色重算（不再留旧蓝）。
- 库里已有脏 token（备份还原 / 直接改库）在**读取时**被剔除并回落基准，不必手工清库；`post.lang` 白名单只作用于写入，存量脏值靠输出转义兜住。

### D. 验证

- PR 侧：新增 `test_audit_v542_theme_input.py`（32 条）+ `test_audit_v542_visitor_theme.py`（23 条）；全量 1390 passed、`ruff` 0 错、`lint_debt` 无新增债务、`check_i18n` 通过、`vite build` 通过、CI 6/6 success。
- 合并后本机：`compileall` exit 0、`ruff check .` 全绿、**定向回归 198 passed**（主题 / SEO / site / 文档守卫共 12 个文件）、`npm run build` ✓、**全量 pytest 1396 passed**（发布前实测）。
- **未验**：像素级观感（PR 作者本机拿不到可见视口）。上线后需真机看一眼顶栏胶囊、抽屉整行按钮、14 套时面板滚动。

**前端源码有改动 → 本版必须重新构建前端**（`_vite_build30/` 已按合并后源码重建）；无数据库迁移，head 仍 `b7c2e91a4d63`。

## v5.4.2（2026-11-01 · 修 `/docs`「如何新增一个 API」步骤编号错乱）

> 起因：`/docs` 上这一节的步骤编号显示成 **6/7/8/9/10/11**。不是编号写错，是 **Markdown 缩进**：步骤 4「鉴权按需选」下的 4 个子项只缩进 **3 空格**，而 Python-Markdown 的嵌套列表要 **4 空格** —— 少一个空格，这 4 项就被并进同一个 `<ol>` 成了第 5~8 步，后面的 5/6/7 步顺延成 9/10/11。

### A. 修法

- 那 4 行（公开 / 登录 / 管理员 / 超管）改为 **4 空格**缩进，正文一字未改。
- 渲染实测：该小节 `<ol>` 恰好 **7 个** `<li>`，步骤 4 内嵌 `<ul>`（4 项）；全文 `<pre>` 仍为 **2**，语言仍 `text` + `python`。

### B. 守卫

`tests/test_docs_codeblock_design.py::test_apimd_列表子项缩进不会被并进有序列表`，两条互补判据：

- **静态**：围栏外不允许出现「恰好 3 空格 + `- `」—— 这是「被并进父级 `<ol>`」的唯一指纹；
- **渲染**：真实走 `render_markdown()`，断言该小节 `<ol>` 里确实嵌着 `<ul>`、且紧跟「鉴权按需选」这一步。

已做变异验证：把 4 空格改回 3，守卫立刻变红并报出 `(1974, '   - 公开 → 不判断')`。

纯文档内容变更，无代码改动、无迁移，head 仍 `b7c2e91a4d63`。

## v5.4.1（2026-11-01 · 部署脚本热修：venv 属 root 时装不上新依赖）

> 起因：v5.4.0 首次真的新增 Python 依赖（`pypinyin`），部署时暴露 `update.sh` 的一个潜伏缺陷 —— ④b 用运行身份（www）跑 `pip install`，而宝塔「Python 项目」的 venv 属 **root**：

```text
ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied:
'/www/server/pyporject_evn/blog_env/lib/python3.13/site-packages/pypinyin'
```

**为什么潜伏这么久**：此前每一版都是「依赖已满足」，pip 从不写盘，这条路径从未真正执行过；而且报错发生在 `Downloading pypinyin-0.55.0 … 840 kB` **之后**，看起来极像镜像/网络失败（本次一度按网络查，实测三个镜像索引都返回 200）。

### A. 修复 `update.sh::install_deps`

- **可写性预判**：先用 `sysconfig.get_paths()['purelib']` 取 site-packages，再以运行身份 `test -w`；不可写就跳过该身份，不再「下载完才报权限错」。
- **root 兜底**：仅当 `id -u == 0` 且运行身份不是 root 时，先镜像、再官方 PyPI 各装一次。
- **`( umask 022; … )`**：root 默认 umask 可能是 077，否则会装出运行身份读不到的包 —— 表现为「部署日志全绿、运行期 `ModuleNotFoundError`」，比装不上更难查。
- **失败原因判定**：pip 日志命中 `Errno 13|Permission denied` 时明写「与网络无关」，避免下次又被下载日志误导。

**没有改 venv 属主**：该 venv 由宝塔面板创建与管理，改属主可能影响面板自身；由 root 安装更安全，且产物按 umask 022 生成、运行身份可读。

### B. 生效方式与验证

- `update.sh` **不在发布 zip 里**，靠同 tag 的 raw 自更新：`self_update_check()` 末尾 `exec bash "$canon"` —— 本次部署会先自更新再重跑，**本次部署即用上新逻辑**，不需要手工覆盖生产文件。
- 验证：`bash -n` 通过；把 `install_deps()` 真实抽出配 stub 跑 4 个分支（www 全失败 → 4 次调用且落到 root／www 第 2 次成功 → 不触发 root／预判不可写 → 只 2 次 root 调用／root 首次成功）；新增守卫 `test_依赖安装_venv属root时要能自动兜底` 并做**变异验证**（`umask 022`→`077` 立刻变红）；全量 pytest 全绿、`ruff check .` 通过。
- 服务器只读确认：`purelib` 属 `root:root`、以 www `test -w` 为假 → 修复后的脚本会走 root 分支（与预判一致）。

无数据库迁移，head 仍 `b7c2e91a4d63`。

## v5.4.0（2026-11-01 · 分类/标签/系列 slug 可读化：中文名转 ASCII，旧地址自动跳转）

> 起因：中文标签的访问日志与分享链接是 `%e6%99%ba%e8%83%bd%e4%bd%93%e5%ae%89%e5%85%a8`。查明是 RFC 3986 的标准百分号编码 —— `make_slug()` 保留汉字，46 个标签的 slug 就是中文，本身不是故障，但可读性差、也不利于英文关键词匹配。

### A. 纯 ASCII slug
- 新增 `utils.slug.ascii_slug()`：ASCII 小写保留、符号转 `-`、汉字走 `pypinyin.lazy_pinyin`（**惰性导入**，缺库时降级剔汉字而非崩站）、超长截断。
- `unique_model_slug()` 统一改走它，并新增 `explicit=` 显式 slug 参数。
- `requirements.txt` 增 `pypinyin>=0.53,<1.0`（纯 Python，无二进制依赖）。

### B. 后台可读可改
- 建标签/分类/系列可选填「地址 slug」，留空按名字自动转拼音（`智能体安全` → `zhi-neng-ti-an-quan`）。
- 标签管理页每行可直接改地址（`set_tag_slug_core`）；分类/系列编辑表单新增「地址」栏。
- **行为变更**：改名不再自动重算 slug。slug 是对外地址，改名顺带换地址会让已发链接 404；现在只有显式填「地址」才改，并提示「旧 → 新」。

### C. 旧地址兼容
- `utils.taxonomy_slug.resolve_taxonomy()` 四路兜底：精确 → 忽略大小写 → `name`（历史中文 slug）→ `ascii_slug(name)`（旧自动拼音）。
- `/api/tag|category|series/<旧slug>`：200 + `"moved": true` + 新 `slug`，前端 `router.replace` 换地址栏（数据不重取）。
- `/api/rss/tag|category/<旧slug>` 与爬虫壳页 `/api/og/page/*` 对旧地址发 **301**（nginx 的爬虫通道已存在，无需改配置）。
- 壳页 canonical 一律用解析后的新 slug，避免同一内容出现两个可索引地址。

### D. 数据迁移（上线后执行）
- 一次性脚本把 **56 个标签 / 4 个分类 / 1 个系列**的中文 slug 改成 ASCII（品牌用官方名如 `qwen`/`hunyuan`，通用词用英文如 `cybersecurity`/`fields-medal`）。
- **顺序不可颠倒**：先发代码（旧地址靠 `name` 反查仍可用）→ 再跑迁移；反序会让旧代码 404。

**实证**：新增 `tests/test_slug_ascii.py` **16 条**；全量 pytest **1333 passed**；`ruff check .` 全绿；`vite build` 通过。无 schema 变更，head 仍 `b7c2e91a4d63`。

## v5.3.4（2026-10-31 · v5.3.3 审计修复 + 设计系统收口 + lint 门禁归零）

> 基于 v5.3.3（`669f749`）的审计结果，按 **E → A → B → C → F** 五批执行修复。完整审计与主题系统评估见 `docs/audit/2026-10-31-v5.3.3-audit-and-theme.md`。

### E. lint 门禁归零

- 修复 10 条 ruff 错误：`media_service.py` 4×B904、`media_storage.py` 2×C408、tests 3×F841、1×RET504。
- v5.3.3 的 CI `lint` 是红的（run 41066023513），本版后 `ruff check .` = **0**。
- 修复第二个门禁问题：`tools/lint_debt.py` 基线由旧版 ruff 生成（F401/SIM 等基线为 0），在 0.16.8 下同一快照实际命中 3/7/1/1/244 → 主分支自己会卡在棘轮上。本版将 CI ruff 固定为 `0.16.8` 并重设基线；今后升级 ruff 需同步 `--update`。

### A. 会话与 2FA

- `/logout`、`/admin/logout`、`/api/auth/logout` 统一 `session.clear()`（此前只 pop `user_id`，`twofa_ok=True` 残留）。
- `/login`、`/admin/login`、注册、首次设置密码显式写 `twofa_ok=False`。
- `/admin/logout` 加入 2FA 放行清单（仅密码会话也能退出）。
- `/admin/login` 补 10 次/60 秒限流与失败延迟；2FA 生效时不再提前记「登录成功」。

### B. 可见性收口

- `Post.in_group()` 默认走 `visible_posts_query()`；`hreflang_alternates()` 同口径。
- `/api/post/<slug>` 的 `translations[]` 不再泄露私密/草稿/回收站译文。
- `GET /api/comments/reactions` 校验评论所属文章可见，且不回显不存在的 id。
- `/api/tags`、`/api/site` 的文章数/阅读量/评论数只统计可见文章。

### C. 限流与出站

- `client_key()` 改用 `get_client_ip(strict=True)`：未配 `EO_AUTH_KEY` 时**不再采信** `EO-Client-IP`（防轮换假头绕过限流）；统计/属地仍走宽松档，行为不变。
- `/api/feed/circle?refresh=1`：管理员不限；匿名 1 次/5 分钟，超出静默回落缓存并在 `debug.refresh_throttled` 标记。

### F. 设计系统收口

- 删除 `--accent: var(--accent)` 自引用；默认品牌色统一 `#196ddd`。
- 正文代码块改用 `highlight.js/styles/github-dark.css`，`pre` 背景对齐 `#0d1117`。
- 封面副标题恢复白色 + 文字阴影。
- 元信息 13px faint（3.81:1）→ 14px muted（4.9:1）；标签 chip 改 `--text`（≥5.1:1）。
- 通知面板、SquareView、StatsView 的写死颜色改 token，暗色自动翻转；按钮圆角统一。
- 两份 `tokens.css` 增加字号尺度 `--type-*`。

### 需要重点注意的行为变化

1. **登出清整份 session**：CSRF token 也会清空；前端 `logout()` 已调用 `clearCsrfToken()`，下一次请求会重新获取。
2. **`/admin/login` 限流 10/60s**：自动化脚本/压测可能受影响。
3. **限流键 strict IP**：EdgeOne 未配 `EO_AUTH_KEY` 时，限流按 `remote_addr` 聚合；统计不变。若线上依赖「无密钥也按真实客户端 IP 限流」，需要先配密钥。
4. **博客圈匿名强制刷新 1/5min**：超出不报错，静默回缓存。
5. **视觉变化**：默认蓝色 `#1a73e8 → #196ddd`、代码块深色高亮、元信息字号 13→14px，属预期变化。
6. **测试断言变更**：`tests/test_posts_pagination_v4.py::test_tags_endpoint_matches_naive` 原先断言「标签计数包含回收站/隐私文章」——那正是本次修复的泄露行为，已改为 `visible_posts_query()` 口径。**不是为让测试变绿而放宽断言，而是契约本身被修正。**
7. **安全提示**：审计报告含漏洞细节（2FA 绕过条件、可见性泄露路径）。仓库是公开的，**已随合并进入 main，请尽快部署**，使公开细节对应的线上已是修复态。

### 实证

- `python -m ruff check .` → **0**。
- 全量 `pytest` → **1311 passed, 0 failed**（合并后本地复跑，5:52）。
- `vite build`（vue-frontend）→ **通过**。
- 新增 25 条回归测试：`test_audit_v533_session.py`(7) / `test_audit_v533_visibility.py`(6) / `test_audit_v533_ratelimit.py`(5) / `test_audit_v533_design.py`(7)。
- 无迁移，head 仍 `b7c2e91a4d63`。

## v5.3.3（2026-10-30 · 热修 /docs 代码块整体失效：API.md 闭合围栏写错）

> **这是 v5.3.2 的热修**。v5.3.2 上线后 `/docs` 的代码块设计仍未生效 —— 根因**不在前端**（`decorateCodeBlocks` 逻辑正确），而在 `myblog/API.md`：给目录树补 `text` 语言时，**误把第一棵目录树的闭合围栏也改成了 ` ```text `**。markdown 的闭合围栏不允许带 info string，于是该代码块永不闭合，**整篇文档从第 138 行起所有围栏都退化成行内 `<code>`**（渲染结果 `<pre>`=0、`<code>`=1870），前端 `decorateCodeBlocks()` 自然找不到任何 `<pre>`。
> 另有第二个坑：`python` 示例原本缩进在有序列表第 3 步内，Python-Markdown 3.8 的 `fenced_code` **不支持列表项内的缩进围栏**，同样不产出 `<pre>`。

### 改动内容

- **`myblog/API.md`**：
  - 第 165 行闭合围栏 ` ```text ` → ` ``` `（核心修复）；
  - 「如何新增一个 API」的 `python` 示例从有序列表第 3 步内**提到列表之后顶格**（保持 1-7 步编号连续），确保被渲染为 `<pre><code class="language-python">`。
- **`tests/test_docs_codeblock_design.py`**：守卫从「只查源码文本」升级为双判据 ——
  - 静态：闭合围栏必须是纯 ` ``` `、围栏必须顶格、必须严格成对；
  - 渲染：真实调用 `render_markdown(API.md)`，断言 `<pre>` 数量 == 围栏块数、语言标注含 `text`+`python`；
  - 已做**变异验证**：把闭合围栏改回 ` ```text `，两条守卫立刻变红。
- `APP_VERSION` 与 `API.md` 版本头同步到 `v5.3.3`。

### 实证

- 真实 `API.md` 渲染：`<pre>` = **2**，语言标注 `text` + `python`，围栏 4 行严格配对（138 开 / 165 闭、1979 开 / 1990 闭）。
- 前端 `DocsView.vue` 与后端 `render_markdown` 均未改动（v5.3.2 已部署且正确），本次纯文档内容修复。
- 无迁移，head 仍 `b7c2e91a4d63`。

## v5.3.2（2026-10-30 已发布 · /docs 代码块重做：语言标签栏 + 复制按钮 + 真高亮）

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

