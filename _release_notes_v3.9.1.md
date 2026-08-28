# llhhy-blog v3.9.1 — 打开文章从「每次重算」到「秒开」

性能与稳定性补丁：**正文渲染缓存** + **SQLite WAL**。纯后端改动，前端构建产物与 v3.9.0 一致（可只覆盖后端包）。

## 修了什么

### ① 文章每次打开都要重算 Markdown（长文最明显）

- **根因**：`render_markdown()`（Markdown 解析 + bleach 白名单清洗）在**每次请求**都跑一遍 —— 文章详情接口 `GET /api/post/<slug>`、SSR 首页 / 文章页 / 分类 / 标签 / 搜索结果（`routes.py::_render()`）无一例外。正文越长越慢，且**与内容是否被修改无关**。
- **修法**：`post` 表新增 `content_html`（渲染结果）+ `content_hash`（指纹）两列，唯一出口改为 `utils.render_post_html(post)`：
  - 命中指纹 → 直接返回缓存，**不再渲染**；
  - 指纹 = `sha256(渲染版本号 | 正文 | HTML)`，正文一改指纹即变 → 自动重新渲染，**保存文章无需手工清缓存**；
  - HTML 本身也进指纹，缓存被意外改坏会**自动自愈**（重新渲染）；
  - 写回用独立连接（不污染当前会话事务）、撞锁 800ms 即放弃，任何失败都静默回退为「本次重算」，**不影响正确性**。
- **实测**（1 万字符长文样本）：`87ms → 2.7ms`（约 30×）；发布包冒烟：首次 78.2ms / 再次 3.5ms，`render_markdown` 只被调用 1 次。

### ② 并发下偶发 `database is locked`

- **根因**：SQLite 默认 rollback journal 且未设 `busy_timeout`，gunicorn 多 worker 下每个访客都在写（阅读量 + 统计埋点），读写互相阻塞即报错。
- **修法**：建连即执行 `PRAGMA journal_mode=WAL` + `busy_timeout=5000` + `synchronous=NORMAL`（PRAGMA 是**连接级**的，故挂 SQLAlchemy `connect` 事件逐连接设置；非 SQLite 与 `:memory:` 自动跳过）。WAL 让**读不阻塞写、写不阻塞读**。

### ③ 备份链路配套（不做的活，启用 WAL 反而有数据风险）

WAL 模式下 `cp blog.db` 会漏掉「已提交但尚未 checkpoint」的数据 —— 备份静默不完整，恢复后可能报 `database disk image is malformed`。故同步改造：

- `backup.py`：备份改用 sqlite3 **在线备份 API**（产出自包含 .db，失败回退直拷）；恢复后删除 `-wal` / `-shm` 残留（否则旧 WAL 会回放新库导致损坏）；
- `update.sh` / `deploy.sh`：升级前备份优先 `sqlite3 .backup`，无该命令时退化为 `cp` 且连 `-wal` 一起拷；
- 后台「🩺 全站体检 → 数据库健康」新增 `journal_mode`、`busy_timeout` 两行，便于部署后核验。

### ④ 核实后**不做**的改动

传言中的「评论 XSS（`_comment()` 返回未消毒原文 + 前端 `v-html`）」经核实为**误判**：`CommentForm.vue` 用 `{{ c.content }}` 文本插值，前台 4 处 `v-html` 的内容均经服务端 `clean_html()` / `escape()` 处理。本次未改动评论链路，不做无谓改动。

## 升级步骤（宝塔）

1. 覆盖后端包 `myblog-backend.zip`（前端产物与 v3.9.0 相同，可不覆盖；覆盖也无害）；
2. 宝塔项目管理器 → gunicorn「**停止 → 启动**」（restart 不重载）；
3. 后台 → 运维诊断 → 🩺 全站体检 → **数据库健康**，确认：
   - `日志模式 journal_mode` = **WAL**
   - `写锁等待 busy_timeout` = **5000 ms**
   - 若显示 `delete`：说明 `myblog/data/` 对运行用户（一般 `www`）不可写，检查属主与权限；
4. 随便打开两篇文章（第一次会落缓存，稍慢属正常），随后刷新应明显变快。

## ⚠️ 运维提醒（请务必知悉）

- 启用 WAL 后 `myblog/data/` 下会出现 `blog.db-wal`、`blog.db-shm` 两个文件，这是**正常产物，千万别手动删除**（删掉 `-wal` 可能丢失尚未 checkpoint 的已提交数据）；
- 手工备份数据库请改用 `sqlite3 blog.db ".backup /path/to/backup.db"` 或后台「💾 数据备份」，**不要**直接 `cp blog.db`；
- 若将来调整 Markdown 扩展或 `clean_html()` 白名单，把 `utils._RENDER_VERSION` +1 即可让全部缓存一次性失效；
- 极端情况下想强制重算某篇文章：把该行 `content_html` / `content_hash` 置空，下次访问即重新渲染。

## 验证

- pytest **23 passed**（新增 8 条：缓存写入 / 命中不重算 / 正文变更失效 / 篡改自愈 / 迁移幂等 / WAL PRAGMA 生效 / 备份快照完整性 / 清理 WAL 残留）；
- 发布包冒烟：解压 `myblog-backend.zip` 用隔离库启动 → 版本 3.9.1 ✅ / WAL+busy_timeout ✅ / 渲染只 1 次（78.2ms → 3.5ms）✅ / 缓存落库 ✅ / 备份快照 `integrity_check=ok` ✅；
- R49 十维安全审计 **0 遗留**（详见 `myblog/SECURITY_AUDIT.md` R49 轮）。

## 改动文件

`myblog/utils.py`（`content_digest` / `render_post_html`）、`myblog/models.py`（Post 两列）、`myblog/app.py`（`_install_sqlite_pragmas` + 迁移补列）、`myblog/api/common.py`、`myblog/api/posts.py`、`myblog/routes.py`、`myblog/backup.py`（在线备份 + 清理 WAL）、`myblog/diagnostics.py`（体检新增两项）、`myblog/config.py`（APP_VERSION→3.9.1）、`update.sh`、`deploy.sh`、`tests/test_render_cache.py`（新增）、四份文档（README / CHANGELOG / ROADMAP / deploy_guide / SECURITY_AUDIT）。
