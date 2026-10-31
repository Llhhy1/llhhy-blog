# 安全审计报告（SECURITY_AUDIT.md）

> **📦 历史归档**：第一轮 ~ 第一百轮（R1~R100）已归档至 `docs/archive/SECURITY_AUDIT_r01-r80.md`（R1~R80）、`docs/archive/SECURITY_AUDIT_r81-r90.md`（R81~R90）与 `docs/archive/SECURITY_AUDIT_r91-r100.md`（R91~R100）；R101~R110 → `docs/archive/SECURITY_AUDIT_r101-r110.md`（v4.12.1 因体积守卫触发，主文件涨到 166 KB / 上限 160 KB）；R111~R120 → `docs/archive/SECURITY_AUDIT_r111-r120.md`（v5.2.3 因体积守卫触发，主文件涨到 162 KB / 上限 160 KB）；R121~R132 → `docs/archive/SECURITY_AUDIT_r121-r132.md`（v5.3.4 因体积守卫触发，主文件涨到 162 KB / 上限 160 KB）；**本文件从 R142 起**。

---

## R142 · v4.13.2（待发版）生态统计优化安全审查（24h 离线清理 + 独立页 · 无新攻击面）

**范围**：`myblog/ecosystem.py`（`stats()` 展示窗口 30 天→24h 收敛 + 新增 `prune_stale_sites` /
`_stored_site_key`）、`myblog/app.py`（`_start_scheduler` 每小时生态块新增 prune 调用）、
前端 `EcosystemView.vue` + `router.js` 路由 + `App.vue` 导航 + `AboutView.vue` 剥离生态板块。
无新路由、无权限变更、无表结构变更、无迁移。

### 142.1 删除操作的注入面与误删面

`prune_stale_sites()` 的删除条件：

```python
cutoff = utcnow() - datetime.timedelta(hours=stale_hours)
q = EcosystemSite.query.filter(EcosystemSite.last_seen < cutoff)
if exclude_self:
    sk = _stored_site_key()
    if sk:
        q = q.filter(EcosystemSite.site_key != sk)
```

- `cutoff` 完全由服务端时间算出，**没有任何用户输入参与** → 无注入面（SQLAlchemy ORM 参数化）。
- `exclude_self=True`（默认）排除本机 `site_key` 对应的那一行：
  即使中心站某次心跳偶发失败、自身 `last_seen` 变陈旧，也不会把自己删掉；
  且调度里**心跳先跑**（刷新自身 `last_seen`）、prune 后跑，双保险不会误删自身。
- `_stored_site_key()` 是**非生成式**读取（不落库造 ID），避免 prune 这种维护动作凭空产生安装 ID。
- 只动 `ecosystem_site` 表，**不触碰** `visit_log` / 评论 / 文章等任何访客或内容数据。

### 142.2 新页面权限与数据暴露（CWE-200 复核）

- 新页面 `/ecosystem` 仅 `GET /api/ecosystem/stats`，该接口自 v4.7.5 起就是**公开只读**、已有限流，
  本次未改其鉴权与返回字段结构（仅给 `sites[]` 明细补了 `first_seen` 与带时分时间戳）。
- 注册表内容仍是**自报**的（`site_key` / `url` / `version` / 时间戳），**不含任何访客数据**；
  沿用既有设计：**中心端不验证 URL 可达性**（那会成 SSRF 探测器），页面已如实标注「数据自报」。
- 离线清理把保留期从「30 天不展示」收成「24 小时硬删」—— 留存更少陈旧的「自报」数据，
  属**隐私正向**变化，无新增泄露通道。

### 142.3 已知残留风险（如实记录）

1. 生态注册表的「真伪」本质上不可验证（心跳可伪造、不验 URL）—— 这是该统计的设计前提，
   本次未改变；页面免责声明已写明「只反映当前仍在运行的实例」。
2. `exclude_self` 依赖 `Setting` 里存有本机 `site_key`；若极端情况下该设置缺失，
   `_stored_site_key()` 返回 None、exclude 失效，但心跳先跑会即时补植 key，下一轮即恢复，
   且中心站自身行即便被删也会在下一次成功心跳后重新注册，无持久影响。

### 142.4 测试与变异验证

- `tests/test_ecosystem.py` 新增 3 个 prune 用例：超阈值删除 / 无过期返回 0 / exclude_self 保护自身，
  全文件 **28 passed**。
- 该轮完成时全量 **1198 passed**（较 v4.13.1 的 1195 + 3）；并入 v5.0.0 后的最终全量见 R143.7。`vite build` 通过（产出 `EcosystemView` chunk）。
- 变异验证：临时把阈值改到 0h → 「超阈值删除」用例变红（证明删除确实按时间窗生效）；
  把 `exclude_self` 强制 False → 「保护自身」用例变红（证明 exclude 逻辑真实生效）。

## R143 · v5.0.0（待发版）媒体上传面扩容安全审查

本轮把上传口从「只收 5 种图片」扩到「图片 + 视频 + 分块 + 云存储」，攻击面显著变大。
按「新增入口逐个过」的口径记录。

### 143.1 上传校验链（顺序即边界）

```
后缀白名单 → 单文件大小（按 kind 分流）→ 磁盘余量 → 文件头魔数（后缀与内容必须一致）→ 落盘
```

1. **后缀白名单**：图片 `png/jpg/jpeg/gif/webp`（**仍不含 svg**，svg 可内嵌脚本），
   视频 `mp4/m4v/mov/webm`。不在白名单直接拒，不读文件内容。
2. **魔数比旧实现更严**：旧 `_detect_image_magic(header, ext)` **忽略 ext**，只判断
   「是不是某种图片」，于是 PNG 改名成 .jpg 也能过。新 `validate_magic()` 要求
   「声明后缀对应的规范类型」== 「文件头真实类型」，不一致即拒
   （如 `.mp4` 里塞 PNG 字节 → 拒绝）。
3. **大小分流**：图片 50MB、视频 500MB。**不共用同一个上限** —— 放开视频不能顺带
   把图片也放到 500MB。
4. **磁盘闸门**：剩余空间 < 文件大小 + 2GB 直接拒（HTTP 507）。这道闸的意义不在
   「省空间」，而在**保护 SQLite**：磁盘写满时 WAL 与回滚日志写不进去，整站写入会雪崩。

### 143.2 分块上传的路径与状态安全

- `upload_id` 必须匹配 `^[0-9a-f]{32}$`，且拼出的绝对路径必须落在 `UPLOAD_TMP_DIR`
  **内**（双重校验）—— 这是本功能唯一的路径穿越入口，测试里对 `../../etc` 有专门用例。
- `index` 限制在 `[0, 9999]` 整数；单块上限 `2 × chunk_size`（16MB），防止用超大
  「一块」绕过总大小检查。
- **合并前三道复核**：块数齐全 → 合并后字节数 == 初始化声明值 → 文件头魔数。
  任一失败**删除半成品**，绝不入库一个「存在但内容不对」的文件。
- 临时目录按 mtime 超 24h 清理（在每次 `chunk_init` 时顺手做，不额外加定时任务）。
- 分块大小 8MB 是**安全与可用性的平衡点**：既保证单请求远低于 gunicorn 30s timeout
  （否则大文件必然「传到一半 502」），又不给单请求留太大缓冲。

### 143.3 公开展示面（CWE-200）

- `/api/media/*` 的过滤写在 **SQL 层**（`filter(is_public == True)`），不是取回再筛 ——
  后者一旦加分页就会算错 `total`，也容易在重构中漏掉。
- 公开接口**不返回** `filename`（磁盘名含秒级上传时间）、`uploaded_by`（上传者 id）、
  `storage`（部署细节）。私密资源的详情接口返回 404，与「不存在」不区分，避免枚举。
- 后台 `/admin/media` 与上传/删除要求管理员；**存储后端设置要求超管** ——
  能改「文件往哪写」等于接管存储，不能下放。

### 143.4 云存储凭据

- OSS SecretKey / WebDAV 密码经 `backup_settings.encrypt_secret()`（Fernet）加密后存
  `Setting` 表，页面只回显 `••••••`，表单留空 = 不修改（避免「打开设置页一保存就把
  密钥清空」这类经典事故）。
- 与 `BACKUP_OSS_*` **完全独立**：备份桶通常私有、图床桶必须公开可读，混用会造成
  私有桶被公开或图片全 403。
- 云端上传失败时**保留本地副本并明确提示**，不静默降级 —— 静默降级会让用户以为
  文件在云上，本地盘被悄悄写满。

### 143.5 正文与 iframe 的边界

- 正文白名单新增 `video` / `source`，属性仅播放控制类（`controls/preload/poster/
  playsinline/loop/muted/width/height/src/type`）。**仍然没有 `style`、没有任何 `on*`、
  没有 `iframe`** —— `test_allowlist_has_no_dangerous_tags_or_attrs` 与棘轮哈希双重把关。
- `_img_to_video()` 生成的 `src` 做了引号转义；`javascript:` 之类即便写进 Markdown，
  也会在 bleach 阶段被清掉（有专门用例）。
- 外链播放器**只允许 B 站 / YouTube / Vimeo 的播放器域名**（`normalize_embed()`），
  且只接受 http/https。**正文里不放 iframe**：外链播放器只在前台图库页由 Vue 以
  `<iframe :src>` 渲染，域名在登记时已按白名单校验，并带 `sandbox` 属性。

### 143.6 残留风险（明确承认）

1. **没有病毒/恶意内容扫描**：视频只校验容器魔数，不解析内容。自建博客的上传者是
   管理员本人，风险可接受；若将来开放给普通用户上传，必须补这一层。
2. **盗链与流量**：文件由 Nginx 直接服务，未加 Referer 防盗链。500MB 视频被外站
   盗链会消耗真实流量，需要时在 Nginx 侧加 `valid_referers`。
3. **单块请求仍占 worker 最多 30s**：多人大文件并发上传会挤占并发槽（默认 4 worker）。
   个人博客量级可接受；要彻底解决需改成后台任务队列。
4. **云端删除是尽力而为**：远端 API 失败只记日志，可能留下孤儿对象（不会导致 404，
   因为记录已删）。

### 143.7 测试与变异验证

- **v5.0.0 全量回归：1186 passed**（0 failed）。较并入前的 1198 少 15 条，差额来自删除的 2 个游戏测试文件（`test_games.py` / `test_games_audit_v442.py`）与诊断页参数化用例里移除的 `/admin/games` 一项；新增媒体相关 18 条。

- `tests/test_media_asset.py` **17 passed**：伪装视频拒绝 / 上限分流 / 磁盘闸门 /
  分块成功 / 缺块拒绝 / 大小不符拒绝 / 会话 ID 穿越 / 公开接口只吐 is_public /
  类型筛选 / 外链白名单 / img→video / 普通图仍是 img / `<video>` 不被剥 /
  script+iframe 仍被剥离。
- 渲染白名单棘轮同步：`EXPECTED_ALLOWLIST_SHA256` 更新、`EXPECTED_RENDER_VERSION="5"`。
- 变异验证：把 `validate_magic()` 改回「只看是不是图片」→「伪装视频」用例变红；
  把公开接口的 `is_public` 过滤去掉 →「只返回 is_public」用例变红。

## R144 · v5.0.0（2026-10-28）观感层与整体变更安全审查

R143 已覆盖媒体上传面（分块/魔数/云存储凭据/公开展示）。本轮补审**观感层改版**与
**本版整体变更面**，按「新增入口逐个过」的口径记录。

### 144.1 观感层（纯样式，攻击面为零但有两条真实风险）

本轮风格改动**只新增 CSS 令牌与覆盖规则，不含任何可执行代码、不含新路由、不含新
后端逻辑**：新增 21 条 `--ui-*` 令牌（两份 `tokens.css` 取值一致）、新增
`styles/look.css`（748 行，纯声明式规则）、`admin.css` 末尾追加一段。

按七维逐项过：

| 维度 | 结论 |
|---|---|
| XSS | 无。CSS 不承载用户可控内容；`content` 属性未新增 |
| SQL 注入 | 无。不涉及查询 |
| 越权 | 无。不涉及路由与权限 |
| SSRF | 无。观感层未引入 `url()` 外链资源（背景图仍走既有 `--wallpaper`） |
| CSRF | 无。不涉及写接口 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无 |

**两条需要记录的真实风险**（都不是漏洞，是「会静默退化」的坑）：

1. **层叠顺序**：覆盖层若放回 `global.css` 末尾会被 `responsive.css:75` 的
   `.page-title` 压回旧值 —— 表现为「代码写了、构建通过、页面没变」。
   已由 `tests/test_frontend_css_order.py` 锁死导入顺序，并把判据定为
   「构建产物里该选择器的**最后一条**是否为新值」。
2. **scoped 特异性**：带 `<style scoped>` 的组件，其属性选择器特异性高于全局类，
   观感层覆盖不到（`LoginView` 的 `.oauth-*`、`SearchView` 的 `.sh-*` 已就地改）。
   这条不设守卫是因为它属于「改的时候要知道」，不是「会自己变坏」。

### 144.2 命名合规（非安全项，按用户要求执行并留档）

风格层命名去掉厂商产品名：`--ios-*` → `--ui-*`、`styles/ios.css` → `styles/look.css`，
文档措辞改「统一观感层 / 圆润风格」，`Large Title`、`tertiary fill`、`inset grouped`
等专有叫法换成通用说法。

**保留**的 4 处为技术事实指代，不属于风格自述：`utils/text.py` 的 UA 设备识别
（Windows / Android / macOS 并列），以及两处「某浏览器对 `background-attachment: fixed`
存在支持缺陷」的兼容性说明。判据：**说别人家的浏览器/系统 → 保留；说自己产品的风格 → 改掉。**

### 144.3 本版整体变更面复核

- **新增路由**：`/gallery`、`/api/media/list`、`/api/media/folders/<id>`、
  `/admin/media/update|embed|sync|storage`、`/admin/upload/chunk/init|part|complete|abort`、
  `/admin/ai-summary/llm-config`。均已核验装饰器：`/admin/*` 全数带管理员或超管装饰器，
  **存储后端设置要求超管**（能改「文件往哪写」等于接管存储，不能下放）；
  `/api/media/*` 为公开只读，过滤写在 **SQL 层**（`filter(is_public == True)`）而非取回再筛。
- **删除路由**：`/api/games*`、`/admin/games*`、前台 `/games` 三条。删除前已
  `grep` 全部 `url_for('admin.games')` 引用面并改指新入口 —— 否则 AI 摘要页会
  `BuildError` 500（经验 24 的同类坑，本次在动手前就查了）。
- **表结构**：新增 `media_asset`（head `d9f1a4c7b2e8` → `f3b7d2a91c58`），**不改任何既有表**；
  `game` 表保留但代码不再读写，`data/games/` 数据不删。
- **部署面**：Nginx 需加 `client_max_body_size 40m`（默认 1 MB，漏了表现为「上传转圈后
  失败且后端日志空白」）；`data/upload_tmp/` 需可写。已写入 `deploy_guide.md` 的 v5.0.0 升级要点。

### 144.4 审计结论表

| 编号 | 级别 | 问题 | 状态 |
|---|---|---|---|
| 144-A | 🟡 | 覆盖层放错文件会被 `responsive.css` 压回旧值（静默失效） | 已修 + 已加守卫 `test_frontend_css_order.py` |
| 144-B | 🟡 | scoped 组件特异性高于全局类，观感层覆盖不到 | 已就地改（LoginView / SearchView），注释记录 |
| 144-C | 🟡 | 命名借用厂商产品名，存在商标风险 | 已全量改为中性名（`--ui-*` / `look.css`） |
| 144-D | 🟢 | 观感层七维安全面 | 通过（无可执行代码、无新路由、无外链资源） |
| 144-E | 🟢 | 新增路由权限 | 通过（管理员 / 超管分级正确） |
| 144-F | 🟢 | 公开接口过滤 | 通过（SQL 层过滤，不返回 filename / uploaded_by / storage） |
| 144-G | 🟡 | Nginx 上传上限未配置会导致 413 且后端无日志 | 已写入 deploy_guide 升级要点 ② |

### 144.5 测试与变异验证

- **全量回归 1186 passed / 0 failed**。
- `test_frontend_css_order.py`（2 条）：锁住 `look.css` 必须在 `responsive.css` 之后导入，
  且文件非空并引用 `--ui-radius-card`。变异验证：把导入顺序调换 → 立即变红。
- `test_css_token_ratchet.py`：裸 hex 棘轮守住（颜色一律 `var(--token, 原值)` 兜底）；
  本版顺带修了该守卫自身的计数 bug 并补了回归用例。
- `test_wcag_contrast.py` + `test_base_light_matches_token_files`：语义色未被改动，
  对比度与前后台一致性均在预算内。

## R145 · v5.1.0（相册）安全审查

相册是**编排层**：只引用 `media_asset`，不存文件、不新增上传入口。因此本轮不重复
R143 的上传面审查，重点在「编排关系」带来的三个新问题：**谁能看见、谁能改、删了会怎样**。

### 145.1 公开面（CWE-200）

- `/api/albums` 的过滤写在 **SQL 层**（`filter(Album.is_public == True)`），
  不是取回再筛 —— 后者在分页时必然把 `total` 算错，也容易在重构中漏掉。
- 相册内的媒体**二次过滤**：即使相册公开，其中 `is_public=False` 的素材也不返回。
  这条容易漏（相册本身公开不等于里面每张图都该公开），有专门用例守住。
- `AlbumItem.media_id` 不设外键，媒体被删会留下空引用 → 查询用 **inner join**
  `media_asset`，空引用在 SQL 层就被滤掉，不会渲染出一个 `src=""` 的破图。
- 私密相册详情返回 **404**，与「不存在」不区分，避免通过状态码枚举 slug。
- 公开字段口径与 `/api/media` 一致：不返回 `filename` / `uploaded_by` / `storage`。

### 145.2 权限（越权）

- `/admin/albums*` 全部带 `@admin_required`（列表、编排页、创建、更新、删除、
  章节增删改、条目增删改与排序、媒体选择器）——逐个核对了装饰器，没有遗漏。
- 章节与条目的接口都做**归属校验**：`AlbumSection.query.filter_by(id=sid, album_id=aid)`
  与 `AlbumItem.query.filter_by(id=iid, album_id=aid)`。只校验 id 存在是不够的 ——
  否则 A 相册的章节 id 可以被贴到 B 相册的请求里改掉别人的数据。
- 媒体选择器只能读（`GET`），不能借它改媒体归属。

### 145.3 输入校验

- `slug` 走正则 `^[A-Za-z0-9\u4e00-\u9fa5_-]{1,120}$`（允许中文，便于分享时可读），
  且更新时检查是否被**其他**相册占用；创建时由 `_unique_slug()` 生成，重名自动加后缀。
- `media_ids` 支持字符串与数组两种形态，统一 `int()` 转换后逐个查存在性；
  不存在的 id 跳过而不是整批失败。
- `section_id` 允许空（未分组），非空时必须属于当前相册。
- `sort` 只在同一 `(album_id, section_id)` 内有意义，批量重排接口按传入顺序重编号。

### 145.4 渲染安全（XSS）

- 行程概览（`intro`）与小提示（`tips`）在前端按「空行分段、整段 `- ` 转列表」
  解析后**用 Vue 插值渲染**，**不引 markdown 库、不用 `v-html`**。
  这两块是管理员自己写的，但少一个 `v-html` 就少一个「将来某天正文改成用户可写」
  时的 XSS 面。
- 灯箱与网格里的图片走 `<img :src>`，`src` 来自后端的 `media.url`（本地资源为
  `/static/uploads/...`，外链为登记时已校验的 http/https）。
- 图注（`caption`）同样走插值，不拼 HTML。

### 145.5 残留风险（明确承认）

1. **相册不校验素材是否属于自己**：管理员可以把任意公开素材编进任意相册 ——
   自建博客单作者场景下这是特性不是缺陷；若将来开放多作者，需要按 `uploaded_by` 收窄。
2. **无相册访问计数**：不做统计，避免每次浏览产生一次写库。
3. **slug 允许中文**：URL 会被百分号编码，部分 IM 客户端预览时显示不美观；
   想要纯 ASCII 可在编排页手动改。
4. **删除相册不可恢复**：条目随相册删除（媒体文件保留）。后台有二次确认。

### 145.6 测试与变异验证

- `tests/test_album.py` **11 passed**。
- 变异验证：把 `/api/albums` 的 `is_public` 过滤去掉 → 「公开列表只返回公开相册」变红；
  把媒体 join 的 `MediaAsset.is_public == True` 去掉 → 「非公开媒体不出现在相册」变红；
  把 inner join 改成 outer join → 「已删媒体的条目被跳过」变红。

### 145.7 v5.1.1 渲染器升级后的 XSS 面复核（追加）

v5.1.1 把 `intro` / `tips` 的渲染从「整段纯文本」升级为「按行 token 化」：
`**粗体**` → `<strong>`、段内换行 → `<br>`。渲染逻辑变了，145.4 的结论不能直接沿用，
逐条复核：

| 检查点 | 结论 |
|---|---|
| 是否引入 `v-html` | **否**，仍然全部走 `{{ }}` 插值 |
| 是否引入 markdown 解析库 | **否**，自写约 20 行 tokenizer |
| 用户可控内容能否变成 HTML | **不能**。`**` 只决定「是否包一层 `<strong>`」，标签由模板写死；文本永远是文本节点 |
| 能否造成标签注入 | **不能**。正文里写 `<script>` 会原样显示为字面文字 |
| 未成对 `**` 的处理 | 按 `split("**")` 的下标奇偶判定，多余片段仍作文本渲染，不吞字符、不抛错 |

**刻意取舍（明确承认）**：tokenizer 只认 `**`。写 `*斜体*`、`[链接](url)`、`# 标题`
仍会露出原始符号。这是主动选择 —— 每多支持一种语法就多一层解析，也多一分
「某天正则写错导致内容错乱」的风险，而这两块的实际需求只到「分段 / 列表 / 加粗」。
支持的写法已写进后台 placeholder，让输入时就知道边界，而不是写完在页面上发现星号。

接口面未变：`intro` / `tips` 仍只由 `@admin_required` 的 `album_update` 写入，
前端只读渲染；不存在「用户可控内容进入这条渲染链」的路径。

## R146 · v5.1.2（移动端抽屉滚动修复）安全审查

本轮只改一个 CSS 文件（`vue-frontend/src/styles/look.css`）里的三条规则，用于修复
移动端抽屉被 `overflow: hidden` 锁死滚动的问题。按七维过一遍：

| 维度 | 结论 |
|---|---|
| XSS | 无。CSS 不承载任何用户内容，不新增 `content` 属性 |
| SQL 注入 | 无。不涉及查询 |
| 越权 | 无。不涉及路由与权限判断 |
| SSRF | 无。未新增 `url()` 外链资源 |
| CSRF | 无。不涉及写接口 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无 |

**一条与安全无关但值得留档的边界说明**：`.drawer` 从「整体滚动」改成
「外层裁切 + 头尾固定 + 菜单区滚动」，**不改变任何权限边界** —— 抽屉里的
「管理后台」「写文章」等入口是否出现，仍由模板层的 `state.user.is_admin`
决定；CSS 只改滚动容器，不会让未授权的人看到本不该出现的入口。

**残留风险**：无新增。`overflow: hidden` 的简写陷阱属于**可用性缺陷**而非安全问题，
已记录在 CHANGELOG 与代码注释中（判据是 computed `overflowY`，不是 `scrollTop`）。

## R147 · v5.1.3（`hidden` 属性兜底）安全审查

本轮只改 `myblog/static/admin.css` 追加一条 `[hidden] { display: none !important; }`，
并新增 `tests/test_hidden_attribute_guard.py` 4 条守卫测试。

| 维度 | 结论 |
|---|---|
| XSS | 无。CSS 不承载内容，未新增 `content` 属性 |
| SQL 注入 / 越权 / SSRF / CSRF | 无。不涉及请求、路由、权限 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无 |

**一条必须点明的边界**：这条兜底是**全局 `!important`**，会覆盖任何带 `hidden`
属性的元素的 `display`。这不会造成越权 —— `hidden` 的语义就是「不显示」，
强制它生效只会让元素更隐蔽，不会让本不该出现的东西暴露出来。

反方向的副作用（某元素本该显示却被 `hidden` 属性误藏）属于**功能缺陷**而非安全问题，
且会在页面上直接看出来；本轮也顺带核对了后台模板里另外 6 处用 `hidden` 的元素
（`input[type=file]` 与 `.wp-lib`），它们本来就该隐藏，行为不变。

**残留风险**：无新增。

## R148 · v5.1.4（`album_update` 双模式返回）安全审查

本轮在一个已鉴权的写接口里加「按请求类型分支返回」，涉及两个需要确认的点：
**鉴权有没有被绕过**、**flash 里会不会带出未转义内容**。

### 148.1 鉴权未被绕过

`form_mode` 只在函数体内决定**返回值形态**，位置在 `@admin_required` 之后：

```python
@admin_bp.route("/albums/<int:aid>/update", methods=["POST"])
@admin_required
def album_update(aid):
    form_mode = not request.is_json   # ← 装饰器已先行拦截未登录/非管理员
```

`request.is_json` 判断的是 `Content-Type`，客户端可以自由伪造 —— 但伪造的结果
只是「拿到 JSON 而不是重定向」，**不改变权限判定，也不改变写入行为**。
即：有权限的人两种方式都能写；没权限的人两种方式都被 `@admin_required` 拦在门外。

### 148.2 归属校验仍然存在

`_album_or_404(aid)` 只按 id 查，理论上是「知道 id 就能改任何相册」——
但本站在此之前就是这样，且 `album` 没有作者概念（单作者博客）。
多作者场景才需按 `uploaded_by` 收窄，与 R145.5 记录的口径一致，本轮无变化。

### 148.3 flash 内容不含用户输入

所有 `flash()` 的文案都是**常量**（「相册信息已保存」「标题不能为空」
「slug 已被其他相册占用」「日期格式应为 YYYY-MM-DD」），没有拼接 `request` 里的值。
即便将来拼接，`base.html:153` 用的是 `{{ m }}` 插值（Jinja 自动转义），
不会形成 XSS 面。

### 148.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无。flash 全常量，模板走自动转义 |
| SQL 注入 | 无。不新增查询，SQLAlchemy 参数化 |
| 越权 | 无。`@admin_required` 前置，分支只改返回格式 |
| SSRF | 无 |
| CSRF | 无变化。表单带 `csrf_input()` 隐藏域，fetch 带 `X-CSRF-Token` 头 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无 |

### 148.5 测试

- `tests/test_album.py` **14 passed**（新增 3 条覆盖双模式契约）。
- 变异验证：`form_mode = False` 恒定 → 2 条变红，报错内容与线上现象逐字一致。

## R149 · v5.2.0（媒体库 ↔ 相册打通）安全审查

本版新增**一个写接口**（`POST /admin/media/<id>/to-album`）并在媒体库页面
**多展示了相册标题**。按「新增写入口 + 新增展示面」两类分别审。

### 149.1 新写入口：`media_to_album`

| 检查点 | 结论 |
|---|---|
| 鉴权 | `@admin_required`（管理员，不是仅登录）。普通用户与访客不可达 |
| CSRF | 走全局闸门；前端带 `X-CSRF-Token`，与页面其余 fetch 一致 |
| 参数校验 | `album_id` 强制 `int()` 转换，失败即 400；`section_id` 同 |
| 归属校验 | **章节必须属于该相册**（`AlbumSection.filter_by(id=sec, album_id=aid)`）。只校验「章节存在」不够 —— 否则可以把 A 相册的章节 id 贴到 B 相册的请求里 |
| 越权改他人数据 | 不适用：`album` 无作者概念（单作者博客），口径同 R145.5 |
| 写入范围 | 只写 `album_item` 一行（`album_id / section_id / media_id / sort`），**不触碰 media_asset 与 album 任何字段** |

**一个必须点明的组合**：这个接口允许把 `is_public=False` 的素材加入 `is_public=True`
的相册。前台会不会因此泄露？**不会** —— `/api/albums/<slug>` 的查询在 join 时带了
`MediaAsset.is_public == True`（R145.1 记录并有用例守护），非公开素材在 SQL 层被滤掉。
即：**相册公开 ≠ 里面每张图都公开**，这条二次过滤在本版仍然生效。

### 149.2 新展示面：媒体库显示「素材属于哪些相册」

- 页面本身是 `@admin_required`，所以相册标题（**含私密相册**）只对管理员可见 ——
  管理员本来就能在 `/admin/albums` 看到全部相册，这里不构成新增泄露面。
- 展示的是相册 **title**，不含 slug、不含 `is_public`、不含任何素材-相册的权限信息。
- 查询用一次聚合（`AlbumItem join Album` by `media_id`），无 N+1，也不会因页码变化
  而泄露「未被引用」以外的信息。

### 149.3 「不复制字段」这条设计的安全含义

图注留空、由前端回退显示素材标题（`capOf()`），除了避免重复输入，还带来两个副作用：

1. **不会出现数据漂移导致的信息残留**。若把素材标题在加入时抄进 `caption`，
   之后在媒体库把标题改掉（比如改成不含敏感信息的名字），相册里那份副本仍留着旧文字
   —— 而前台是公开的。现在永远读同一份数据，改一处即全站生效。
2. **前端回退只在展示层**，`caption` 空就空着，接口不返回伪造内容；
   `caption` 的写入路径仍只有 `album_item_update`（管理员）。

反向风险（明确承认）：**素材标题一旦是敏感内容，会同时出现在它所属的每个公开相册里**。
这是「同一份数据」的必然结果，管控点在媒体库的标题本身，不在相册侧。

### 149.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无。相册标题与素材标题走 Jinja / Vue 插值；标签是 `textContent` 赋值 |
| SQL 注入 | 无。`in_()` 与 `filter_by` 均为参数化 |
| 越权 | 通过（见 149.1 归属校验） |
| SSRF | 无 |
| CSRF | 无变化 |
| 密钥泄露 | 无。不涉及存储凭据 |
| 资源泄漏 / 限流 | 无。单行写入，无新增后台任务 |

### 149.5 测试

- `tests/test_album.py` **19 passed**（新增 5 条）。
- 变异验证：`caption=""` → `caption=(m.title or "")` 后，「caption 必须留空」立即变红。
- 跨相册章节被拒绝（400）有专门用例。

## R150 · v5.2.1（相册封面 / 名字同步修复）安全审查

本版改了**一个写入口的落点**（`album_item_update` 从写 `album_item.caption`
改为写 `media_asset.title`）、修了一个查询缺陷、加了一条数据迁移。
按「写目标变化 = 按新写入口重审」处理。

### 150.1 写目标变了：`album_item_update` 现在改的是 `media_asset.title`

| 检查点 | 结论 |
|---|---|
| 鉴权 | 不变，仍 `@admin_required` |
| 越权改他人数据 | 不适用：blog 单作者，`media_asset` 无「归属者」语义（口径同 R145.5 / R149.1） |
| 影响面扩大了吗 | **是，需说明**：原来只能改「本相册这一条的说明」，现在改的是**全站共享的素材标题** —— 同一张图若在多个相册，改一次全都变。这是本次设计的**目的**（名字只有一份），不是副作用 |
| 输入校验 | 长度截断 `[:200]`（与 `media_asset.title` 列宽一致）；空值即清空标题，展示层回退文件名 |
| 目标存在性 | 先 `MediaAsset.query.filter_by(id=it.media_id)`，媒体已删则**跳过写**，不抛错（与「删图不让相册崩」同口径） |
| 旧字段兼容 | 旧页面发 `caption` 也落到 `title`，**不写 caption** —— 避免缓存页面把两份名字又长回来 |

### 150.2 查询修复（封面）

`album_list()` 由 `[a.id for a in rows]` 改为 `[a.cover_media_id for a in rows]`。

- 这是**取数正确性**修复，不改变可见范围：媒体 id 来自管理员可编辑的 `cover_media_id`，
  查询仍是 `MediaAsset.id.in_(ids)` 参数化，无注入面。
- **没有**因此新增「私密素材泄露到公开面」的路径：这里只决定后台列表页缩略图，
  公开接口 `/api/albums` 的封面过滤逻辑未变（R145.1 的 `is_public` 二次过滤仍在）。

### 150.3 数据迁移 `b7c2e91a4d63`

| 检查点 | 结论 |
|---|---|
| SQL 注入 | 无。全部 `sa.text(...)` + 绑定参数（`{"t": name, "m": int(mid)}`） |
| 覆盖范围 | 只处理 `caption` 非空的 `album_item`；`mid` 为空时只清 caption 不写 title |
| 幂等 | 判据是「caption 非空」，跑完即空 → 重复执行是空操作 |
| 不可逆性 | `downgrade` 留空（与 `d4a7f08c2e91` 同口径）：名字已并进 `media_asset.title`，无法区分「原本就是标题」与「从 caption 合来的」，拆回去只会造出猜测数据 |
| 数据丢失风险 | **有，已明确告知用户**：caption 会覆盖 title（生产一例 `潮州1` → `意溪渡口`）。只换不删，且换上去的是用户最后写下的名字 |

### 150.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无。标题走 Jinja 属性值转义 / Vue 插值；`is-synced` 只是 CSS 类名 |
| SQL 注入 | 无（见 150.3） |
| 越权 | 见 150.1：写目标扩大但仍在 `@admin_required` 内，且单作者口径 |
| SSRF | 无 |
| CSRF | 无变化，仍走全局闸门 + `X-CSRF-Token` |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无。单行 UPDATE；封面查询由 per-album 改为一次 `in_()`（反而更少） |

### 150.5 测试

- `tests/test_album.py` **25 passed**（新增 6 条：3 条封面、3 条名字）。
- 封面用例刻意让**相册 id ≠ 封面媒体 id**，并做变异验证：
  改回 `a.id` 后 `test_相册列表的封面按封面媒体id取` 立即变红。
- 迁移在独立临时库上真跑过 `flask db upgrade`：4 条 caption 正确合并、caption 清空、
  `alembic_version` = `b7c2e91a4d63`。

## R151 · v5.2.2（编辑器样式 / 选图布局 / 分块上传错误处理）安全审查

本版**没有新增路由、没有新增写入口**，改的全是样式、错误语义与部署脚本。
按「改动是否扩大信任边界」逐项过。

### 151.1 错误信息外泄面（本版唯一有安全含义的改动）

`media_service.chunk_init` 新增 `except OSError`，把底层异常文本截断 80 字符后
拼进 `MediaError` 返回给前端。

| 检查点 | 结论 |
|---|---|
| 泄露内容 | 只含 `Permission denied` / `No space left` 这类 errno 描述 + 目录名（服务器绝对路径） |
| 是否可被未登录用户触发 | 否，`@login_required` |
| 路径泄露的评估 | **接受**。后台本来就是管理员专属；且报错不含文件名、不含数据库路径、不含密钥。若完全吞掉细节，管理员无法判断是权限还是磁盘满 —— 与 v5.2.1「500 HTML 让人完全看不懂」是同一种失败 |
| 其他异常 | 仍然由 `upload` / `chunk_complete` 的 `except Exception` 兜底（`str(e)[:120]`，口径一致） |

同时 `album_edit.html` 新增 `readJson()`：非 JSON 响应时把 HTML **剥标签后截 90 字符**
作为提示。同样只对已登录管理员可见，且剥标签后不再具备可执行结构。

### 151.2 前端选择器 / DOM 结构变更

- 选图格子由 `<button>` 改为 `<div role="button" tabindex="0">`：
  **键盘可达性保留**（Enter/Space 触发），点击行为不变。
- 新增的图片名字用 `textContent` 赋值，**不拼 innerHTML** —— 素材标题里的
  `<script>` 之类不会被解析执行。这是本版唯一涉及「用户可控文本进 DOM」的地方，
  按最保守写法处理。
- 未新增任何 `v-html` / `innerHTML` 拼接标题的路径。

### 151.3 部署脚本 `update.sh` 的属主探测

改为优先取 gunicorn **master 的子进程（worker）** 属主，并新增 `⑤c` 在迁移后
`chown -R` `data/` 到该用户。

| 检查点 | 结论 |
|---|---|
| 权限提升风险 | 无。`chown` 的目标用户来自**本机进程/文件属主**，不接受外部输入 |
| 会不会把 data/ 交给错误用户 | 探测链有三重回退（worker → master → blog.db 属主），任一成功即用；全部失败则**不做 chown**（`fix_data_owner` 首行 `[ -n "$APP_USER_FINAL" ] || return 0`） |
| 是否动内容 | 只 `chown`，不改权限位、不删文件；`find` 仅用于判断是否存在异常项 |
| 回滚 | 属主随时可改回，无数据影响 |

### 151.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无新增面（见 151.2，标题走 textContent） |
| SQL 注入 | 无 SQL 改动 |
| 越权 | 无路由/权限改动 |
| SSRF | 无 |
| CSRF | 无变化 |
| 密钥泄露 | 无。新错误文案不含 secret / token / 数据库路径 |
| 资源泄漏 / 限流 | 无。`chunk_init` 失败时会 `shutil.rmtree(d, ignore_errors=True)` 清掉半成品目录，不留垃圾 |

### 151.5 测试

- `tests/test_media_asset.py` **19 passed**，新增 1 条：
  `test_分块初始化写不进临时目录时给可读错误` —— 断言 `MediaError` 且 `status == 507`
  （防回归到 500 HTML）。
- `tests/test_album.py` **27 passed**，新增 2 条样式守卫：
  ① `.view-split` 不得出现在自绘圆角的选择器里；
  ② 选图网格必须有 `grid-auto-rows: minmax(...)`、名字层与 `readJson`。
- 线上实测：`chown` 后 `chunk_init("probe-20mb.mp4", 20MB)` 成功建目录、abort 后清理干净。

## R152 · v5.2.3（部署脚本自更新修复）安全审查

本版**只改 `update.sh`**（后端业务代码零改动）。但改的是**部署链自身的执行逻辑**，
按「改动是否影响信任链」逐项过。

### 152.1 改了什么

| 位置 | 改动 |
|---|---|
| 脚本顶部（`cd "$WORK"` 之前） | 新增 `SELF_PATH_ABS="$(readlink -f "$0" ...)"`，记住启动时的绝对路径 |
| `self_update_check()` | 判据从 `readlink -f "$0"` 改为 `${SELF_PATH_ABS:-...}`（保留兜底） |
| `fix_data_owner()` | `chown -R` 目标从整个 `data/` 收窄为**逐个业务目录**（`data/backup/` 排除在外） |

### 152.2 信任边界复核

| 检查点 | 结论 |
|---|---|
| 自更新的远端源是否变了 | **没变**。仍然只从 `https://raw.githubusercontent.com/$REPO/$TAG/update.sh` 取，且 `bash -n` 语法检查、`sha256` 比对、备份旧版、失败回滚（`cp -p` 备份 → 写失败即还原）全部保留 |
| 放宽了「允许替换自己」的条件吗 | **没有放宽判定，只是把「自己是谁」算对了**。原先相对调用时 `self_path` 被解析成 `/tmp/llhhy_update/update.sh` → 与 `$APP_DIR/update.sh` 不等 → 拒绝；现在相对调用时 `SELF_PATH_ABS` 就是 `$APP_DIR/update.sh` → 相等 → 允许。**非规范路径运行（真的在跑别处的副本）仍然会被拒绝**（`self_path != canon` 分支未动） |
| 远端脚本来源是否可信 | 同 tag 的 raw 文件，与已验签的 Release 资产**同源同 tag**；且替换后的脚本仍要过 `bash -n` |
| `chown` 收窄是否有副作用 | **更安全**：原先 `chown -R "$u" "$APP_DIR/data"` 会连 `data/backup/` 下历次部署的备份副本一起改写属主（实测线上 `data/backup/` 里有 root 属主的旧文件）。收窄后只改业务目录，备份保持原状（回滚时按原属主还原） |
| `chown` 目标用户来源 | 仍是**本机进程/文件属主**推导（worker → master → `blog.db` 属主），不接受外部输入；探测全失败则 `fix_data_owner` 首行 `[ -n "$APP_USER_FINAL" ] \|\| return 0` 直接不做 |
| 是否动数据内容 | 不动。只改属主，不改权限位、不删文件 |
| 引入新命令/新依赖吗 | 无。仍是 `readlink` / `chown` / `find` / `bash` |

### 152.3 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无（无 Web 代码改动） |
| SQL 注入 | 无 |
| 越权 | 无（脚本以 root 跑，行为与旧版一致，未新增任何外部可控输入） |
| SSRF | 无（下载源未变，仍限 `raw.githubusercontent.com/$REPO/$TAG/...`） |
| CSRF | 无 |
| 密钥泄露 | 无（`SELF_PATH_ABS` 只含本地路径） |
| 资源泄漏 / 限流 | 无 |

### 152.4 测试

- `tests/test_update_chain_contract.py` **10 passed**，新增 1 条：
  `test_脚本自更新能认出自己_相对路径调用也要行` ——
  断言 ① 存在 `SELF_PATH_ABS=`；② 它的捕获位置**早于行首的 `cd "$WORK"`**
  （用 `^cd "\$WORK"$` 正则，只认独立命令，不匹配注释里的同名字样）；
  ③ 自更新判据优先用它；④ 反向断言 `self_path=$(readlink -f "$0"` 已消失。
- `bash -n update.sh` 通过。

## R153 · v5.2.4（属主探测拼坏用户名 → 静默降级为 root）安全审查

本版**只改 `update.sh`**。但改的是**部署链里「以谁的属主执行写操作」这一环**，
按「写操作的属主是否会错位」逐项过。

### 153.1 改了什么

| 位置 | 改动 |
|---|---|
| 属主探测（worker） | `ps ... \| tr -d '[:space:]' \| head -1` → `ps ... \| head -1 \| tr -d '[:space:]'` |
| 属主探测（master / blog.db / 目录） | 同样补 `head -1` |
| 探测结果校验 | 新增：`id "$APP_USER_FINAL"` 校验，不是真实用户则**作废**并继续兜底链 |
| 其余 `ps` 读取（残留进程扫描） | 统一补 `head -1` |

### 153.2 根因与影响面

`ps -o user= --ppid $pid` 返回**每个子进程一行**（4 个 worker → 4 行 `www`）。
`tr -d '[:space:]'` 会把**换行符也删掉** → 4 行拼成 `wwwwwwwwwww`（13 字符），
这是一个**不存在的用户**。

| 影响 | 结论 |
|---|---|
| `run_as` 行为 | 每次都失败 → 降级为「以当前身份（root）执行」。**脚本设计成不阻断**，所以部署继续 |
| `chown` 行为 | 用户不存在 → 全部失败（`\|\| true` 吞掉）→ 属主校正**形同虚设** |
| 部署日志 | 仍显示「✅ 全部完成」—— **静默降级比直接失败危险**：没有人会去看那串「用户 xxx 不存在」 |
| 实际后果 | 本次实测 5 个业务文件 + 3 个模板 + 29 个 `.pyc` 变成 root:root。站点当时仍正常（读权限足够），但这是 v5.2.2 `data/upload_tmp` 事故的**同一个病根**（属主错位在「下一次要写文件时」才爆） |
| 信任边界 | **未扩大**。修复后属主探测指向的是**真实存在**的 worker 用户（`www`），比修复前更严格 |

### 153.3 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无（无 Web 代码改动） |
| SQL 注入 | 无 |
| 越权 | 无。属主来源仍是本机进程/文件属主，不接受外部输入；修复后**多了 `id` 校验**，只会更严 |
| SSRF | 无（下载源未变） |
| CSRF | 无 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无 |

### 153.4 与 R152 的关系

R152 修的是「自更新认不出自己」；R153 修的是「自更新成功后，**新脚本**里的属主探测本身是坏的」。
两者是同一条链上**前后相邻**的两个缺陷 —— 第一次部署日志里同时暴露（`用户 wwwwwwwwwwww 不存在`）。

### 153.5 测试

- `tests/test_update_chain_contract.py` **11 passed**，新增 1 条：
  `test_属主探测不会被多行输出拼坏` ——
  ① 遍历**代码行**（跳过注释行），凡含 `ps -o user= --ppid` 而**不含** `head -1` 即失败；
  ② 断言存在 `id "$APP_USER_FINAL" >/dev/null 2>&1` 与「不是有效用户，放弃该结果」分支；
  ③ 断言其余 `ps -o … -p` 读取都带 `head -1`。
- `bash -n update.sh` 通过。
- 线上实测：修复后 `run_as` 以 `www` 执行，文件属主保持 `www:www`。

## R154 · v5.2.5（API 文档全量重写 + 同步守卫）安全审查

本版**无业务代码改动**（除版本号与前台文档页文案），改的是文档 + 新增一个测试文件。
按「文档里有没有写出不该公开的东西」逐项过。

### 154.1 本版产出

| 产出 | 性质 | 审查结论 |
|---|---|---|
| `myblog/API.md` 全量重写 | 接口清单文档 | **不含任何密钥、令牌、真实域名之外的内部信息**；示例一律用占位值（`xxx` / `https://www.example.com`） |
| `tests/test_api_doc_sync.py` | 测试文件 | 只读 `app.url_map` 与文档文本，不写库、不发请求 |
| `vue-frontend/src/views/DocsView.vue` | 文案 3 处 | 无逻辑改动 |

### 154.2 文档是否泄露了敏感信息

| 检查点 | 结论 |
|---|---|
| 密钥 / 令牌 | **无**。文档里提到 `WH_DEPLOY_SECRET`、`X-Deploy-Token` 时只写**字段名与校验方式**，不写取值 |
| 内网地址 / 路径 | 只出现**已在仓库公开的**路径（`/www/wwwroot/myblog` 之类部署路径在 deploy_guide 里已有），未新增敏感路径 |
| 内部错误文案 | 写出各接口的业务错误文案（`"请先登录"`、`"需要管理员权限"` 等）—— 这些本来就是**接口对外返回**的内容，不构成信息泄露 |
| 用户数据样例 | 示例一律占位（`123`、`xxx`、`2026-01-01`），**不含真实用户名 / 邮箱 / IP** |
| PII 字段名 | 文档明确写出「`ip` 原文只出现在超管响应里」「邮箱对管理员遮敏」——这是**描述既有的分层保护**，不是绕过它 |

### 154.3 新增测试的安全面

- `test_api_doc_sync.py` 只做两件事：读 `app.url_map`、读文档文本；
- **不写库、不发 HTTP、不碰真实数据**；
- 插件路由用**独立探针 Flask app** 注册蓝图，不触碰生产 app 的蓝图注册
  （`register_blueprint` 在应用已处理请求后会抛 AssertionError，探针 app 规避了这点）。

### 154.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无。文档是 Markdown，由前端渲染时走既有清洗链；本次未改渲染逻辑 |
| SQL 注入 | 无（无 SQL 改动） |
| 越权 | 无（无路由 / 权限改动） |
| SSRF | 无 |
| CSRF | 无 |
| 密钥泄露 | 无（见 154.2） |
| 资源泄漏 / 限流 | 无。测试不写库 |

### 154.5 附带效果：把「鉴权口径」钉进文档

旧文档里 `POST /api/post/<int:post_id>/publish-now` 写的是「超管」，源码实际是
「登录 + 对该文有编辑权（管理员全部 / 普通用户仅自己的文章）」。这类偏差**文档不会报错**，
但会让第三方客户端按错误的权限模型集成。新文档逐条标注了「按对象归属分权」的接口，
并由守卫测试锁住条目存在性 —— **不能锁住权限语义本身**（那需要人工复核），
所以本次把权限语义写进文档并在 CHANGELOG 里显式列出纠正项，供下次复核时对照。

## R155 · v5.2.5（视频一直转圈 / 点击触发原生全屏浮层）安全审查

本版改了三处：前台视频卡片（`AlbumView.vue`）、两个后台模板的**视频缩略图**，
以及**生产 nginx 配置**（上传媒体改为 nginx 直出）。

### 155.1 nginx 配置改动（生产，需单独审）

| 检查点 | 结论 |
|---|---|
| 可见性是否扩大 | **没有**。`/static/uploads/` 里的文件**本来就通过 Flask 的公开静态路由对外可取**（前台相册、媒体库都直接引用 `/static/uploads/xxx`）。改成 nginx 直出只是换了谁来发文件，没换「谁能看」 |
| 是否绕过了鉴权 | 没有可绕过的 —— uploads 是**无鉴权的公开资源**，Flask 侧本来就没有任何检查 |
| 路径穿越风险 | **无**。`location ^~ /static/uploads/ { root /www/wwwroot/myblog; }` 下 nginx 会把 URI 拼到 root 后做规范化，`..` 会被消解；且 uploads 目录里只有媒体文件（实测 22 个，无异常文件） |
| 目录列举 | nginx 关闭 autoindex 时不会列举目录；本次未开启 |
| 丢失的安全头 | Flask 的统一安全头由 `after_request` 加上，改由 nginx 发文件后就没有了 → **已在 location 里显式补回** `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、`Referrer-Policy`。CSP 对静态资源无实质意义（它约束的是文档上下文），未补 |
| MIME 混淆 | `nosniff` 已补 → 浏览器不会把 mp4 当成 html 执行 |
| 可回滚性 | **有**。改前已 `cp` 备份为 `html_www.llhhy.cn.conf.bak_v5255_<时间戳>`，回滚 = 覆盖回去 + `nginx -t` + `nginx -s reload` |
| 变更方式 | 只改了 location 块，**没有动 `proxy_cache` 全局配置**（那会影响所有站点）；`nginx -t` 通过后才 `nginx -s reload`（不是 restart，不断连接） |

### 155.2 前端视频卡片

| 检查点 | 结论 |
|---|---|
| XSS | 无。`it.media.url` 走 Vue 插值绑定到 `src` 属性，Vue 会做属性转义；标题等文本走 `{{ }}` 插值 |
| 用户输入进 DOM | `it.media.url` 是服务端拼的站内路径（`/static/uploads/...`），前端没有 `v-html` / `innerHTML` 拼接 |
| `playsinline` 保留 | 是。保留它才能让 `video.play()` 走**内联播放**而不触发系统全屏 —— 这正是本次要修的行为 |
| 去掉 `controls` 是否有可用性损失 | **有，但可逆**：播放中才动态挂上 `controls`，用户可暂停 / 调音量 / 自己选全屏；未播放时显示自绘按钮 |
| 点击事件的副作用 | `@click.stop` 阻止冒泡，避免误触相册的灯箱逻辑；`play()` 被拒时降级为静音重试（浏览器自动播放策略） |

### 155.3 后台视频缩略图

`pointer-events: none` —— 只是让缩略图**不响应点击**，不改变可见性、不改数据。
这修的是「点到 video 触发移动端原生全屏浮层，挡住整页」的误触。

### 155.4 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无（见 155.2） |
| SQL 注入 | 无 |
| 越权 | 无。未引入任何新数据出口；uploads 本来就是公开资源 |
| SSRF | 无。后端未新增任何出网请求；视频由浏览器直连同源静态路径 |
| CSRF | 无 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | **改善**：视频不再经 gunicorn 转发（原来每个视频请求占一个 worker，生产只有 2 核 4 worker） |

### 155.5 测试与实测

- 浏览器实测（线上真实 mp4 + 真实构建 CSS 的探针页）：
  点播放按钮 → `paused=false`、`currentTime=2`（**确实在播**）、
  `document.fullscreenElement === null`（**没有进入全屏**）、播放中才出现原生控件条；
  修复前实测 `readyState=0`（连时长都读不出）。
- nginx 修复后线上实测：经 nginx 带 Range → **206**；三个视频
  `readyState=3`、时长 7.8 / 8.6 / 8.7 秒、分辨率 1080×1920。
- 本版业务代码改动集中在视频卡片与文档，**全量测试通过**。

## R156 · v5.2.5 打包前漏洞审查（独立复核，非增量续写）

本轮不是新增改动，而是**在打包前对已定稿的 v5.2.5 做一次独立漏洞复核**，
并**首次把「生产 nginx 配置」纳入审查范围**（前几版只审代码，没审过生产配置）。

### 156.1 静态分析工具的 7 条 Critical —— 逐条回源码验证，**全部为误报**

| 工具报告 | 实际 | 判定 |
|---|---|---|
| C-1 `backup_settings.py:25` 硬编码密钥 `BACKUP_OSS_SECRET` | 该值是**环境变量名**，映射到 Setting 键名 `backup_oss_secret`；真值走 `os.environ` / Setting 表 | 误报 |
| C-4~C-7 `oauth.py:62/64/68/70` 硬编码 `client_secret` | 同样是**键名映射表**（`CRED_KEYS` → Setting 键，`ENV_KEYS` → 环境变量名），不是密钥值 | 误报 |
| C-2 `migrate_visit_log_bot.py:52` SQL 注入 | `f"ALTER TABLE visit_log ADD COLUMN {col} {ddl}"` 中 `col`/`ddl` 来自**模块内写字的常量 dict**，无任何外部输入；脚本是本地一次性迁移，不接 HTTP | 误报（拼接的是常量） |
| C-3 `migrate_visit_log_referrer.py:51` 同上 | 同上 | 误报 |

**判据记录**：AST 工具的「硬编码密钥」判据是「字典值长得像密钥」，
**无法区分「键名映射表」与「真密钥」**；「SQL 拼接」判据是「f-string 进 execute」，
**无法区分「拼接常量」与「拼接用户输入」**。这两类必须回源码人工判读，不能直接采信。

### 156.2 生产 nginx 配置（本次真正的风险面，此前从未审过）

v5.2.5 改了 `/www/server/panel/vhost/nginx/html_www.llhhy.cn.conf`，新增
`location ^~ /static/uploads/ { root /www/wwwroot/myblog; }` 让上传媒体由 nginx 直出。
逐项复核：

| 攻击面 | 实测结果 | 结论 |
|---|---|---|
| **路径穿越读源码** | `/static/uploads/../../config.py` → 200，但**返回的是 SPA 首页 HTML**（`<!DOCTYPE html>`，1969 字节，`grep APP_VERSION` 命中 0）；`/config.py` 本身也返回 200（前端路由 catch-all）→ 说明 nginx 已把 `..` 归一化后落到不存在的路径，最终由 Flask 当普通路由处理 | **无源码泄露** |
| 越界读 `.env` / `requirements.txt` | 404 | 安全 |
| 越界读 `/etc/passwd` | 400（nginx 直接拒） | 安全 |
| **上传 SVG/HTML → 存储型 XSS** | 实测 nginx 直出 SVG 返回 `content-type: image/svg+xml`（说明**若能落盘就会被执行**）——但上传链有三道闸门：① `chunk_init` 里 `kind_of()` 按扩展名白名单拒（`png/jpg/jpeg/gif/webp` + `mp4/m4v/mov/webm`，**不含 svg/html**）② `chunk_complete` 合并后 `validate_magic()` 复核文件头魔数与后缀一致 ③ 直出补了 `X-Content-Type-Options: nosniff` | **SVG 走不进来**（白名单在**落盘前**生效，非事后清理） |
| 目录列举 | `autoindex` 未开启，`/static/uploads/` → 403 | 安全 |
| uploads 内是否有子目录 | 无 | 无穿越可能 |
| 全局 `proxy.conf` 是否被误改 | **未改**（`proxy_cache cache_one;` 仍原样，只在站点 conf 的 `/static/` 里加了 `proxy_cache off`） | 其它站点不受影响 |
| 安全头丢失 | 直出补了 `nosniff` / `SAMEORIGIN` / `Referrer-Policy`；**CSP 缺失**（Flask 侧有） | 见 156.3 |
| 可回滚性 | 备份 `html_www.llhhy.cn.conf.bak_v5255_20261028_215636` 在位 | 有 |

### 156.3 CSP 在直出资源上缺失 —— **判定为可接受，但记录在案**

直出的图片/视频响应没有 `Content-Security-Policy`。**判断依据**：CSP 约束的是
「文档上下文里允许加载什么资源 / 执行什么脚本」，而一个 `image/avif` 或 `video/mp4`
响应**本身不是文档**，浏览器不会给它建立脚本执行上下文；结合 `nosniff` 已阻断
MIME 混淆，缺少 CSP 不产生可利用的差异。

**前提条件（若将来变化则结论失效）**：① uploads 目录里**永远只有**图片/视频；
② 若将来允许上传 SVG/HTML，**必须**同时在 nginx 侧加
`Content-Disposition: attachment` 或对 SVG 单独设 `Content-Type` 白名单，
否则 SVG 内联脚本会成为存储型 XSS。**已在 `media_service.kind_of()` 的白名单处
留下约束**（新增类型必须同时改 nginx）。

### 156.4 本版代码改动的自查

| 改动 | 审查结论 |
|---|---|
| `AlbumView.vue` 视频卡片 | `it.media.url` 走 Vue 插值绑定到 `src`（属性转义）；无 `v-html`/`innerHTML`；`playsinline` 保留（正是内联播放不接管全屏的前提）；`@click.stop` 阻止冒泡误触灯箱 |
| 后台两处 `pointer-events:none` | 只改点击响应，不改可见性、不改数据 |
| `tests/test_api_doc_sync.py` | 只读 `url_map` 与文档文本；不写库、不发请求；插件路由用独立探针 app，不触碰生产 app 的蓝图注册 |
| `API.md` 全量重写 | 扫过 `secret/token/password/api_key/私钥` 与真实邮箱/内网 IP：**无真实取值**，只有字段名与占位符；唯一命中的是项目自身名字 `llhhy-blog` |

### 156.5 结论

**未发现需要阻断打包的漏洞。** 本版的改动（文档 + 前端视频卡片 + nginx 直出）
在攻击面上是**收缩**而非扩张：上传链三道闸门未动、uploads 目录无子目录、
路径穿越被 nginx 归一化、全局配置未被误改、配置可回滚。

**遗留观察项（非漏洞，供后续参考）**：
① 直出资源无 CSP（见 156.3，将来放开上传类型时须同步处理）；
② `safe_disk_name()` 的后缀来自用户文件名，虽有白名单 + 魔数双闸，但**依赖
`kind_of()` 白名单始终与 nginx 直出假设一致** —— 二者必须一起改。

## R157 · v5.2.6（v5.2.5 视频播放按钮点不动）安全审查

本版**只改前端**（`AlbumView.vue` 的元素查找方式）+ 版本号 + 新增一个测试文件。
无后端业务代码改动。

### 157.1 改了什么

| 位置 | 改动 |
|---|---|
| `videoElOf()` | 从「`querySelector('[data-video-id]')` 再 `querySelector('video')`」改为「从 `videoEls` 登记表取」 |
| 新增 `bindVideo(id, el)` | 函数式 ref 的登记/注销 |
| 模板两处 `<video>` | 加 `:ref="(el) => bindVideo(it.id, el)"` |

### 157.2 信任边界复核

| 检查点 | 结论 |
|---|---|
| 是否引入新的 DOM 查询 | **没有**。改动方向是**减少** DOM 查询（从「按属性选择器查全局 DOM」改为「持有 Vue 已渲染的引用」） |
| `bindVideo` 的 id 来源 | 来自 `it.id`，即**服务端下发的相册条目 id**（整数）。它只作为 `Map` 的键使用，**不拼进选择器、不拼进 HTML、不参与任何字符串拼接** → 无注入面 |
| 元素引用是否会泄漏 | `bindVideo(id, null)` 时 `delete` → 组件卸载/条目移除时自动注销，不会持有已销毁的 DOM |
| 是否影响鉴权 | 无。播放的媒体 URL 仍来自 `/api/albums/<slug>` 的服务端响应，未新增任何数据出口 |
| 是否引入 XSS 面 | 无。改动只涉及 JS 侧的元素引用，不涉及任何模板输出；`data-video-id` 仍是 Vue 插值绑定（属性转义） |
| 未审到的部分 | 无。本版无新增网络请求、无新增依赖、无新增配置 |

### 157.3 变更方式的风险（这条更重要）

本版修的是一个**「功能失效」**的 bug（按钮点了没反应），不是安全漏洞。
但它的修复过程暴露了一个**流程问题**，值得记在案：

🔴 **修复后的验证用了「手写探针页」，而不是真实组件** ——
探针页把 `data-video-id` 挂在**容器**上，真实组件挂在 **`<video>` 自己**身上。
结构差异让探针页的验证结果（"点击后 currentTime=2、没有全屏"）**失真**，
于是这个 bug 一直活到线上实测才暴露。

→ **通用教训**：验证前端交互时，探针必须**从真实组件派生**
（用真实组件的构建产物 + 真实 API 数据），不能用「手写等价物」——
等价物的结构差异会系统性掩盖 DOM 层级类的 bug。

### 157.4 守卫测试（`tests/test_album_video_ref.py`，6 条）

只读 `AlbumView.vue` 源码文本，**不执行 JS、不写库、不发请求**。

**判据设计的关键**（也是本轮又踩一次的坑）：所有匹配都先**剥掉注释行**——
本文件自己的注释里就写了 `document.querySelector('[data-video-id="X"]')` 这个
**反面示例**，不剥注释的话守卫会拿自己的注释把自己判成违规。
（与 `test_update_chain_contract.py` 里匹配 `cd "$WORK"` 命中注释是同一个坑。）

**变异验证**（两条都实测过）：
- `videoElOf` 改回旧的嵌套 `querySelector` 写法 → 第 6 条变红；
- `videoElOf` 改成 `document.getElementById(...)` → 第 6 条变红；
- 恢复后 6 条全绿。

### 157.5 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无（见 157.2） |
| SQL 注入 | 无（无后端改动） |
| 越权 | 无（无路由/权限改动） |
| SSRF | 无（无新增出网请求） |
| CSRF | 无 |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | 无。`videoEls` 是 `Map`，条目移除/组件卸载时自动清理，条目数受相册条目数限制 |

---

## R159 · v5.3.1（修复 /docs 搜索与目录失效 + API.md 版本头补 bump）安全审查

**范围**：`vue-frontend/src/views/DocsView.vue` 的建树/搜索逻辑（`buildToc` / `syncActive` / `sectionText`）；`myblog/API.md` 版本头文案；`tests/test_api_doc_sync.py` 版本断言收紧。**无后端代码改动、无新路由、无表结构变更。**

### 159.1 逐维复核

| 维度 | 结论 | 说明 |
|---|---|---|
| XSS | 安全 | `v-html="fullHtml"` 的数据源是 `GET /api/docs`（后端用 `render_markdown` → `clean_html` 过 bleach 白名单，剥 `script/style/on*`），内容为本仓库 `API.md` 而非用户输入；前端 JS 仅 `getElementById` + 读 `textContent` 建树，无 `eval`、无对用户输入的 `innerHTML`。 |
| SQL 注入 | 安全 | 本次未新增任何 DB 查询。 |
| 越权 | 安全 | 无新接口；`/api/docs` 为既有公开 GET，失败返 `available:false`，权限模型未变。 |
| SSRF | 安全 | 无外发请求。 |
| CSRF | 安全 | 纯前端 SPA 渲染，无新增改状态调用。 |
| 密钥 | 安全 | 无密钥/凭证改动。 |
| 资源泄漏 / 限流 | 安全 | `buildToc` 在挂载后对**已加载 DOM** 跑一次（受文档体积上限约束）；`sectionText` 仅切片缓存；`scroll` 监听沿用既有实现并在 `onBeforeUnmount` 摘除，无新泄漏。 |

### 159.2 回归点

- v5.3.0 的 `/docs` 搜索/目录失效属**功能缺陷**而非安全漏洞，本次修复不涉及安全边界收紧或放松。
- `test_api_doc_sync.py` 版本断言由「子串 `vX.Y.Z` in doc」升级为严格头部 `> 版本：**vX.Y.Z**` 匹配，仅提升文档一致性，不影响运行时安全。

## R160 · v5.3.2（/docs 代码块重做：语言标签栏 + 复制按钮 + 真高亮）安全审查

**范围**：`vue-frontend/src/views/DocsView.vue` 新增 `decorateCodeBlocks()`（对 `/api/docs` 注入的 `<pre>` 包成 `.code-block` 并调用 `hljs.highlightElement`）；`highlight.js` 注册表新增 `plaintext`/`text`；`API.md` 两处目录树围栏补 `text` 语言；`APP_VERSION` 与文档头同步到 `v5.3.2`。**无后端代码改动、无新路由、无表结构变更。**

### 160.1 逐维复核

| 维度 | 结论 | 说明 |
|---|---|---|
| XSS | 安全 | `decorateCodeBlocks` 用 `document.createElement` + `textContent` + `appendChild` 构建标签栏，**不拼接任何 `innerHTML`**；语言名来自后端渲染出的 `class="language-*"`（本仓库 `API.md`，非用户输入），仅作 `textContent` 展示，无注入面。`hljs.highlightElement` 处理的也是同一份后端已 bleach 清洗的 HTML，未引入新的 `innerHTML` 写入点。 |
| SQL 注入 | 安全 | 本次未新增任何 DB 查询。 |
| 越权 | 安全 | 无新接口；`/api/docs` 为既有公开 GET，权限模型未变。 |
| SSRF | 安全 | 无外发请求。 |
| CSRF | 安全 | 纯前端 SPA 渲染，无新增改状态调用；复制按钮只读写 `code.innerText`。 |
| 密钥 | 安全 | 无密钥/凭证改动。 |
| 资源泄漏 / 限流 | 安全 | `decorateCodeBlocks` 在 `loadFullList` 内容到达后跑一次（受文档体积上限约束）；复制按钮监听随 `pre` 被 DOM 回收而释放，不与路由组件生命周期耦合，无新泄漏。 |

### 160.2 回归点

- 复制按钮沿用 v3.17.9 的三层兜底 `copyText`（`Clipboard API → execCommand → 手动弹窗`），与现有文章正文复制同一实现，无新增复制面。
- `:deep()` 命中动态节点是既有模式（旧 `.copy-btn`），本次仅将选择器从 `pre :deep(.copy-btn)` 改为 `.doc-full-body :deep(.code-block__*)`，未改变「动态节点须用 `:deep()`」的正确性前提。

## R161 · v5.3.3（热修 /docs 代码块整体失效：API.md 闭合围栏写错）安全审查

**范围**：`myblog/API.md` 围栏修正（闭合围栏 ` ```text ` → ` ``` `；`python` 示例从有序列表内提到列表之后顶格）；`tests/test_docs_codeblock_design.py` 守卫升级（静态校验 + 真实渲染断言）。`APP_VERSION` 与文档头同步到 `v5.3.3`。**无后端代码改动、无前端改动、无新路由、无表结构变更。**

### 161.1 逐维复核

| 维度 | 结论 | 说明 |
|---|---|---|
| XSS | 安全 | 改的是 Markdown 源码的围栏位置与语言标注，渲染仍走 `render_markdown` → `clean_html`（bleach 白名单）；`<pre>` / `<code class="language-*">` 本就在白名单内，未扩大允许标签或属性。代码块内容为仓库 `API.md` 自身，非用户输入。 |
| SQL 注入 | 安全 | 未新增任何 DB 查询。 |
| 越权 | 安全 | 无新接口；`/api/docs` 为既有公开 GET，权限模型未变。 |
| SSRF | 安全 | 无外发请求。 |
| CSRF | 安全 | 纯文档内容修复，无状态变更调用。 |
| 密钥 | 安全 | 无密钥/凭证改动。 |
| 资源泄漏 / 限流 | 安全 | 围栏修正后 `/api/docs` 仍按 mtime+size 缓存；单次渲染体积不变，无新增泄漏面。 |

### 161.2 回归点

- 守卫新增「闭合围栏必须是纯 ` ``` `」「围栏必须顶格」「真实渲染 `<pre>` 数 == 围栏块数」三条判据，并已变异验证 —— 防止「源码看着对、渲染却失败」的同类问题再次静默上线。
- 本次修复不改变 `render_markdown` 的渲染口径，也不改 bleach 白名单，历史文章缓存无需失效。

## R163 · v5.4.0（分类/标签/系列 slug 可读化）安全审查

**范围**：`utils.slug.ascii_slug()`（pypinyin 转写）、`utils.taxonomy_slug.resolve_taxonomy()`（旧 slug 四路解析）、`/api/tag|category|series/<slug>` 的 `moved` 标记、`/api/rss/*` 与 `/api/og/page/*` 的 301、后台建/改 slug 入口、`requirements.txt` 新增 `pypinyin`。**无新表、无 schema 变更**（只改 `slug` 列的值）。

### 163.1 逐维复核

| 维度 | 结论 | 说明 |
|---|---|---|
| XSS | 安全 | slug 只进 URL 与 `<a href>`；前端 `TagView`/`CategoryView` 用插值渲染 `name`（无 `v-html` 新增点）。壳页 `_render()` 对所有字段走 `html.escape`。 |
| SQL 注入 | 安全 | 解析一律走 ORM（`filter_by` / `func.lower(col) == param`），参数由 SQLAlchemy 绑定，无字符串拼接。 |
| 越权 / 信息泄露 | 安全 | `resolve_taxonomy()` 只读分类/标签/系列本身（这些名字本来就由 `/api/tags`、`/api/series` 全量公开）；文章列表仍走 `visible_posts_query()`，旧 slug 不构成可见性旁路。 |
| 开放重定向 | 安全 | 301 目标由服务端拼成固定前缀 `"/<kind>/" + obj.slug`，**不接受任何用户提供的 `next`/`url` 参数**；`obj.slug` 来自库且已被 `ascii_slug` 规范化为 `[a-z0-9-]`，无法构造 `//evil.com`。 |
| CSRF | 安全 | 新增的「改标签地址」走后台 POST 表单 + `csrf_input()`（与既有后台表单同闸）；移动端走既有 `_role(admin=True)` 鉴权 + `taxonomy_write` 限流。 |
| 依赖安全 | 可控 | `pypinyin` 为纯 Python（无二进制/无扩展），版本上限 `<1.0`；仅转写本地字符串，不联网、不执行外部输入。未安装时 `ascii_slug` 降级剔汉字，不阻断启动。 |
| 资源 / 限流 | 可控 | 未命中的旧 slug 会做一次全表拼音比对：标签 56 行、分类 4 行、系列 1 行，成本可忽略；相关端点已有 120 次/分钟限流，壳页对非搜索引擎 120 次/分钟。 |

### 163.2 回归点

- **行为契约变更**：改名不再自动重算 slug（此前会静默换地址、让外链 404）。`tests/test_api_mobile.py` 两条改名用例已按新契约改写：不带 `slug` 时 `note` 为空且地址不变，带 `slug` 才换并提示「旧 → 新」。**这是契约修正，不是放宽断言。**
- **迁移顺序是硬约束**：先部署代码 → 再跑数据迁移。反序时旧代码按 `slug` 精确查中文值会 404。
- 旧地址解析只覆盖「中文名 / 忽略大小写 / 自动拼音」三种历史形态；**手动改过的历史 slug 无别名表，不保证可回跳**（已在后台提示中写明）。

## R162 · v5.3.4（v5.3.3 审计修复：lint / 2FA / 可见性 / 限流 / 设计系统）安全审查

**范围**：E. lint 门禁归零（`ruff` 固定 0.16.8 + 重设 `tools/lint_debt_baseline.json`，修复 10 条错误）；A. 会话与 2FA（三处 logout `session.clear()`、登录/注册/首次设密复位 `twofa_ok`、`/admin/logout` 进放行清单、`/admin/login` 限流）；B. 可见性收口（`visible_posts_query()` 统一口径、`translations[]` 不泄露、`/api/comments/reactions` 校验、`/api/tags`+`/api/site` 计数只算可见）；C. 限流与出站（`client_key` strict IP、`/api/feed/circle` 刷新限流）；F. 设计系统（`--accent` 自引用清理、品牌色 `#196ddd`、代码块主题、对比度与暗色 token 化）。**无新路由、无表结构变更**。

### 162.1 逐维复核

| 维度 | 结论 | 说明 |
|---|---|---|
| XSS | 安全 | 本轮无 `v-html`/`innerHTML` 新增写入点；模板层改动仅为 token 化颜色与字号。 |
| SQL 注入 | 安全 | 可见性收口统一改走 `visible_posts_query()`（ORM 表达式），无字符串拼接。 |
| 越权 | 安全 | `/api/comments/reactions` 显式校验评论所属文章可见；logout 放行清单新增项仅放行「登出」这一非敏感动作。 |
| SSRF | 安全 | 无新增外发请求；`get_client_ip(strict=True)` 仅收紧（不再采信未签名头），不新增出网面。 |
| CSRF | 安全 | 登出清 session 同时清 CSRF token，前端 `clearCsrfToken()` 已适配；既有全局 `_csrf_protect` 未动。 |
| 密钥 | 安全 | `EO_AUTH_KEY` 仍只从环境变量读取，不入库不入仓；本次仅修正其注释口径。 |
| 资源泄漏 / 限流 | 安全 | 修复前「未配 `EO_AUTH_KEY` 即采信 `EO-Client-IP`」可被构造头绕过；现按 `remote_addr` 聚合（strict）。新增 `/api/feed/circle` 匿名刷新限流与 `/admin/login` 限流。 |

### 162.2 回归点

- **测试断言变更（契约修正）**：`tests/test_posts_pagination_v4.py::test_tags_endpoint_matches_naive` 原先断言「标签计数包含回收站/隐私文章」，即本次修复的泄露行为；已改为 `visible_posts_query()` 口径。**这不是放宽断言，而是契约本身被修正。**
- **2FA 双读点**：闸门在 `app.py:before_request` 的 `enforce_twofa`（每请求都跑），登录流程另有一处 `_twofa_on()`；两处需保持同源，回归测试须覆盖**闸门本身**（仅测业务函数会漏）。
- **lint 棘轮已接进 `check-staged.py`**：后端源码变更时自动跑，新增债务列 error / 退出码 1 硬拦截，避免「门禁不在发版路径上」再次发生。
- **披露提示**：审计报告描述漏洞细节，仓库公开；已随合并进入 main，建议尽快上线完成闭环。

## R158 · v5.3.0（RSS 订阅入口 / 写文章相册素材 / /docs 单源）安全审查

**范围**：新增 `GET /api/docs`（`api/system.py`）；`/admin/albums/media-picker` 的 `album_id`
参数与新增 `/admin/albums/picker-list`（`admin/album.py`）；`utils/render.py` 的
`inject_album_cards()`；`admin/post_editor.py` 实时预览注入；`templates/admin/edit_post.html`
两个只读弹层；`vue-frontend/src/views/SubscribeView.vue` 与页脚 / 侧栏入口。
无表结构变更、无迁移（head 仍 `b7c2e91a4d63`）。

### 158.1 XSS

- `inject_album_cards()` 生成的卡片 HTML **完全服务端拼装**，所有动态值
  （slug / 标题 / 摘要 / 日期 / 地点 / 封面 URL）都过 `_esc()`（`& < > " '` 全转义）；
- 卡片**不进 bleach**，也**不扩 `_ALLOWED_TAGS`** —— 作者可写的标签集保持不变，
  不给作者新增写 `<div>` 等能力；
- 编辑页弹层的 `innerHTML` 拼接全部对服务端数据走 `esc()`；`@album[slug]` 的落点是
  textarea 的 `.value`（纯文本上下文，不按 HTML 解析）；
- `/api/docs` 的 HTML 复用 `render_markdown`（markdown → bleach 白名单），与正文同一口径；
- 订阅页无用户输入，Vue 插值自动转义，无 `v-html`。

### 158.2 SQL 注入

- `album_id` 经 `request.args.get(..., type=int)` 强转，查询走 SQLAlchemy 表达式；
- `q` 的 `like` 模式由 Python 拼 `%q%` 后作为**绑定参数**传给 `.like()`，不拼进 SQL 文本；
- `/api/docs` 不查库。

### 158.3 越权 / 信息泄露

| 路径 | 鉴权 | 判定 |
|---|---|---|
| `/admin/albums/media-picker` | `@admin_required` | 后台，可接受 |
| `/admin/albums/picker-list` | `@admin_required` | 返回**含私密相册**的列表；调用者是管理员本人，且渲染侧按 `is_public` 过滤 → 不构成对读者泄露 |
| `/api/docs` | 公开（无鉴权） | 文档本身公开；源文件是仓库内 `API.md`，非用户输入 |

- 私密相册在**渲染侧**整段移除（不留「相册不存在」提示），公开文章引用私密相册不泄露其存在性；
- `/api/docs` 失败文案只有「文档文件不可用 / 读取失败 / 渲染失败」，**不含路径**；
- 编辑页「插入相册卡片」返回私密相册的 slug / title 属**管理员可见范围**，不新增对外暴露面。

### 158.4 SSRF / CSRF / 密钥

- SSRF：无新增出网请求。`/api/docs` 只读本地文件；`render_markdown` 的
  `_upgrade_img_avif` 只处理 `/static/*.webp` 且 `os.path.isfile` 本地判定。
- CSRF：两个弹层的数据接口是 **GET 只读**；写操作仍走既有后台 CSRF 闸，无新增写路由。
- 密钥：无新增密钥 / 凭据；`/api/docs` 不回显配置。

### 158.5 资源 / 限流

- `/api/docs` 按 **mtime + size** 缓存渲染结果（128KB 文档渲染数百毫秒，不能每请求重算）；
- `inject_album_cards` 只对含 `@album[` 的 HTML 触发，一次 `IN` 查询取全部 slug，
  封面 / 首图查询在 try 内失败降级为空封面；卡片数量受正文长度限制；
- 订阅页只调一次公开 `/api/posts`（服务端固定 per_page）。

### 158.6 守卫与变异验证

- `test_post_album_card.py`（13）：卡片渲染 / 行内不渲染 / 私密 slug 不得出现在公开 HTML /
  不存在 slug 整段移除 / 标题 HTML 转义 / **缓存不得吞掉卡片** / 预览页与前台一致；
- `test_album_card_style.py`（23）：三份样式表必须都含 `.post-album-*`；
- `test_feed_entry.py`（7）：`/feed` 路由、页脚 / 侧栏入口、双源并列、**同源拼接（禁写死域名）**、
  中英文案齐全、两个源都活着且条目数一致；
- 变异验证：去掉 `is_public` 过滤、缓存命中路径不注入卡片 → 对应守卫均变红。

### 158.7 七维复核

| 维度 | 结论 |
|---|---|
| XSS | 无（见 158.1） |
| SQL 注入 | 无（见 158.2） |
| 越权 | 无（见 158.3） |
| SSRF | 无（见 158.4） |
| CSRF | 无（只读 GET，写路径不变） |
| 密钥泄露 | 无 |
| 资源泄漏 / 限流 | `/api/docs` 有 mtime+size 缓存；无新增无限流公开写接口 |
