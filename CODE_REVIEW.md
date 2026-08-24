# 代码审查标准与流程（CODE_REVIEW.md）

> 适用于 llhhy-blog（Flask + Vue3 前后端分离博客）。
> 目标：让每次代码改动在「正确性、安全性、可维护性、性能、文档同步」五个维度都有据可查，杜绝「代码新、文档旧」与「改了没生效」类问题复发。
> 本文件是仓库内的权威审查依据，配套执行入口见 `tools/review/`（脚本）与 `~/.workbuddy/skills/code-review/`（WorkBuddy 审查 Skill）。

---

## 一、审查分层总览

| 层 | 名称 | 频率 | 执行者 | 耗时 | 产出 |
|---|---|---|---|---|---|
| L1 | 发布前自审快检 | 每次发版前 | 开发者（或 WorkBuddy 代跑） | 5–10 分钟 | `smoke_*.py` 全绿 + 安全快检清单勾选 |
| L2 | 季度深度代码审查 | 每季度一次 | WorkBuddy（CodeReview 专家角色） | 1–2 小时 | `docs/review/report-YYYY-Qn.md` 审查报告 |
| L3 | 提交/推送自动门禁 | 每次 commit/push | git pre-commit + pre-push 钩子 | <1 分钟 | 拦截不合规提交，保证 L1 底线自动执行 |

三层关系：L3 是底线（自动、强制、轻量），L1 是发版前的人工快检（补齐 L3 覆盖不到的业务与安全语义），L2 是周期性深挖（发现趋势性/结构性债）。

---

## 二、审查维度（每层都用这 5 个维度）

### D1 正确性
- 改动是否真的实现了需求意图（对照 issue/用户原话，不臆想）
- 边界条件：空输入、超长输入、并发、重复调用、时区（项目用 UTC 存储）
- 兼容性：旧库数据的列迁移（`app.py` 的 `_migrate_*`）是否覆盖本次模型改动
- 回归：跑既有 `smoke_*.py`，新增行为补新冒烟用例

### D2 安全性（对照 SECURITY_AUDIT.md 的轮次记录）
- XSS：模板插值 `|tojson`（防 `'` 逃逸）；前端 `v-html` 是否接触用户输入
- SQL 注入：ORM 参数化；FTS5 拼接是否转义（`fts.py` 有既有实现）
- 越权：`is_super` / `is_admin_role` / `_can_edit_post` 是否正确覆盖新路由
- CSRF：全局强制 POST（`app.py::_csrf_protect()`）；`fetch` POST 带 `X-CSRF-Token`；豁免名单只减不加
- SSRF：外部 URL 请求的 host/协议是否可控；`_is_safe_public_ip` 是否在场
- 密钥：`SECRET_KEY`/`ADMIN_PASSWORD` 默认值不落库、环境变量覆盖
- 限流：新暴露接口是否有 `rate_limit`

### D3 可维护性
- 命名自解释；单一职责；模块边界（`routes.py`/`api.py` 分清 SSR 与 JSON API）
- 不复制粘贴 3 次以上（提取函数/组件）；死代码清理（曾发生 `notify_mentioned` 死代码事故）
- 前端「改源码 ≠ 改 dist」：改 `vue-frontend/src/` 必须重新 `vite build`，否则线上不变

### D4 性能
- N+1 查询（循环内查库）→ 用 join / 预取
- 页面上耗时操作（属地解析、RSS 抓取）是否在后台线程/缓存（`stats.py`、`feed_agg.py` 范式）
- 大表 group_by / 无界缓存（`_RECENT_FAIL` 容量护栏范式）

### D5 文档同步（项目铁律）
- 四份文档随版本同步：`README.md`（根）、`myblog/README.md`、`deploy_guide.md`、`ROADMAP.md`
- 安全改动必须追加 `SECURITY_AUDIT.md` 新轮次章节
- `APP_VERSION`（`myblog/config.py`）与 Git tag 一致；改动部署脚本时挂 deploy 固定包

---

## 三、L1 发布前自审快检（每次发版必过）

顺序执行，任一 FAIL 即中止：

```text
□ 1. 变更清单核对：列出本轮改动的文件，确认无意外文件（如 data/、*.zip、临时 smoke）
□ 2. 语法与编译：后端 py_compile 全过；前端 vite build 通过
□ 3. 冒烟回归：跑对应 smoke_*.py（新建或复用），全绿
□ 4. 安全快检（对照 SECURITY_AUDIT.md 维度：XSS / SQL注入 / 越权 / CSRF / SSRF / 密钥 / 限流）
□ 5. 文档同步：README 根 + myblog、deploy_guide、ROADMAP、SECURITY_AUDIT 是否随版本更新
□ 6. 版本号：APP_VERSION 与 tag 一致；打包后 zip 内 config.py 版本断言通过
□ 7. 打包校验：双源互证（zip 注释 SHA256 == 内容区；sha256.txt == 整文件）
□ 8. 部署提示：改动部署脚本则挂 deploy_scripts_vXXXfix.zip 并要求先覆盖；否则直接一键更新
```

### L1 快检产出示例

```markdown
## v3.4.9 审查记录（L1）
- 变更：myblog/stats.py（GBK 解码修复 + 乱码自愈）
- 冒烟：smoke_gbk_fix.py 15/15 全绿；py_compile OK
- 安全：无新外部输入面（属地解析原有 _is_safe_public_ip 收口），无 XSS/越权/CSRF 变化
- 文档：README / myblog README / deploy_guide / ROADMAP 已补 v3.4.9 段；SECURITY_AUDIT 追加 R31
- 版本：APP_VERSION=3.4.9，zip 内断言通过
```

---

## 四、L2 季度深度代码审查（每季度一次）

### 4.1 流程
1. **范围锁定**：最近一个季度（或自上次审查起）的 git 变更：`git log --oneline --since="3 months ago"`
2. **五维审查**：对每个变更文件按 D1–D5 过一遍；重点模块（安全敏感：`api.py`/`admin.py`/部署脚本）逐行
3. **趋势分析**：统计本季度缺陷类型分布（安全/兼容/死代码/文档漏更），标记高频复发点
4. **产出报告**：`docs/review/report-YYYY-Qn.md`（结构见 4.3）
5. **整改闭环**：🔴 Blocker 立即修；🟡 建议排入下个版本；💭 记入 ROADMAP

### 4.2 L2 深度检查维度（在 L1 基础上追加）

| 维度 | 深挖点 |
|---|---|
| 数据完整性 | `_migrate_*` 是否幂等；回滚路径是否存在；备份/恢复是否覆盖新表 |
| 依赖审计 | `requirements.txt` 是否有未用/过期/已知漏洞依赖；Pillow/cryptography/feedparser 等 |
| 前端状态管理 | `store.js` 状态是否响应式；`apiPost`/`apiGet` 是否都正确 import（曾漏 import 事故） |
| 异步与线程 | 线程是否 daemon；是否独立 app_context；异常是否静默（stats/feed 范式） |
| 编码与国际化 | 外部接口编码兜底（UTF-8 严格 → GBK）；i18n 键是否完整 |
| 部署链路 | update.sh/deploy.sh 是否与当前打包约定一致（双源互证/唯一目录/停止→启动） |

### 4.3 审查报告模板

```markdown
# 代码审查报告 YYYY-Qn（日期）

## 审查范围
- 周期：YYYY-MM-DD ~ YYYY-MM-DD
- 变更：N 个 commit，变更文件清单（M 个）

## 结论
- 总体：🔴 X 个 Blocker / 🟡 Y 个建议 / 💭 Z 个优化
- 一句话评价：

## 问题清单
### 🔴 Blocker
1. （文件/行号/问题/影响/修复建议）
### 🟡 建议
...
### 💭 优化
...

## 趋势与复发点
- 高频问题（近 N 季度出现 ≥2 次）：...

## 整改计划
- 下版本修：...
- ROADMAP 记录：...
```

---

## 五、L3 提交/推送自动门禁

已提供 `tools/review/install-hooks.sh` 一键安装两个 git 钩子：

| 钩子 | 触发时机 | 检查内容 |
|---|---|---|
| `pre-commit` | `git commit` | ① 变更文件黑名单（`data/`、`*.zip`、`*.db` 误入）；② Python 语法（`py_compile`）；③ 前端源码变更未构建警告；④ 文档与代码不同步警告 |
| `pre-push` | `git push` | ⑤ 存在未提交的 `smoke_*.py` 全绿记录检查（提示性）；⑥ `APP_VERSION` 与 tag 提示 |

> 设计原则：钩子**拦截硬错误（黑名单/语法）**、**警告软问题（文档/构建/版本）**——单飞开发者不被过严钩子卡死，但底线不被突破。

安装：`bash tools/review/install-hooks.sh`
卸载：删除 `.git/hooks/pre-commit` 与 `.git/hooks/pre-push`。

---

## 六、审查执行角色与职责（本项目）

| 角色 | 职责 | 触发 |
|---|---|---|
| 开发者（用户） | 提供需求意图、确认审查报告、拍板发布 | 每次改动 |
| WorkBuddy（CodeReview 专家） | 执行 L1 自审快检、L2 季度深度审查；修复 🔴；沉淀 Skill | 用户发起 / 每季度 |
| Git 钩子 | 自动执行 L3 底线门禁 | commit / push |

审查不是「找茬」，是「共同守住质量底线」。🔴 必改、🟡 应当改、💭 可选——优先级清楚，执行不纠结。

---

## 七、配套资源索引

| 资源 | 位置 | 用途 |
|---|---|---|
| 本标准 | `CODE_REVIEW.md`（仓库根） | 审查依据与流程 |
| 审查工具 | `tools/review/`（钩子 + 检查脚本） | L3 自动门禁 |
| WorkBuddy 审查 Skill | `~/.workbuddy/skills/code-review/` | 一键代跑 L1/L2 |
| 安全审计历史 | `myblog/SECURITY_AUDIT.md` | D2 维度依据 |
| 冒烟测试 | 仓库根 `smoke_*.py` | L1 回归 |
| 路线图 | `ROADMAP.md` | 🟡💭 整改去向 |