# v3.10.4 博客圈 RSS 卡死修复

> 纯后端改动，**无需 vite build**。仅修复博客圈（友链 RSS 聚合）的可用性加固问题。

## 概述

本次修复博客圈在抓取**不可达 / 超慢** RSS 源时被永久卡死、拖垮 gunicorn worker 的可用性隐患（此前后台点「强制刷新聚合」即触发 502 / 站点罢工）。同时消除诊断读内存快照导致的多 worker 滞后，以及友链 RSS 填错路径无提示的体验问题。

## 变更内容

| 模块 | 改动 |
|---|---|
| `myblog/feed_agg.py` | 抓取前设置 socket 超时（`FEED_FETCH_TIMEOUT` 默认 8s），`try/finally` 确保还原；坏源超时被 `skip` 而非挂死。新增 `validate_feed_url()` 轻量校验。 |
| `myblog/diagnostics.py` | `check_feed_agg` 改**实时读库**计数，消除多 worker 内存快照滞后（之前填了 RSS 仍长时间显示「没有任何友链填写 RSS」）。 |
| `myblog/admin.py` | `set_link_rss` 保存后**软校验** RSS 可达性（非阻塞 flash 告警），填错 `/feed/` 这类路径立即提示。 |
| `myblog/config.py` | `APP_VERSION="3.10.4"` + 新增 `FEED_FETCH_TIMEOUT`（环境变量 `FEED_FETCH_TIMEOUT` 可覆盖，默认 8）。 |

## 安全审计（R54，0 遗留）

| 维度 | 结论 |
|---|---|
| XSS | 无新增用户可控 HTML 注入点；`validate_feed_url` 仅返回 reason 字符串，不入库不渲染 |
| SQL 注入 | 无新增查询；`links_with_rss` 计数用 ORM 参数化 |
| 越权 | `set_link_rss` 维持 `@admin_required`；`validate_feed_url` 为只读辅助 |
| SSRF | `_safe_url` 既有防护保留并仍生效；超时不影响其判定 |
| CSRF | RSS 保存为既有 POST 路由，全局 CSRF 保护不变 |
| 密钥泄露 | `FEED_FETCH_TIMEOUT` 为非敏感配置，可走环境变量 |
| 资源泄漏 | **核心修复**：socket 超时确保 worker 不被外部抓取挂死；`finally` 还原默认超时 |
| 限流 | 仅诊断/读取类，无新增写接口 |
| 回归 | `py_compile` 通过（四文件）；缓存命中路径不碰超时；软校验非阻塞；`check_feed_agg` 实时读库无回归 |

## 部署注意（按顺序）

1. **先恢复站点**（若此前罢工）：宝塔 → 网站/Python 项目 → `llhhy.cn` → **停止 → 启动**（不要点重启）。
2. 站点恢复后，后台「友链管理」→ 编辑 `hedelei` 那条 → **清空其 RSS 栏** → 保存。
   - 这步只改库、不会去抓外链，安全。目的：避免重启后博客圈再抓 hedelei 卡住。
3. 保留你自己的 `https://www.llhhy.cn/feed.xml`（同服务器，秒回）。
4. 后台「诊断助手」点「强制刷新聚合」→ 博客圈出你 3 篇文章；诊断 `feed_agg` 转 `ok`。
5. （可选）若 hedelei 实际可达，再把其正确 RSS 填回；v3.10.4 起即便不可达也只 `skip` 不卡死。
6. 服务器基线脚本 **v3.4.7**，**本版未改部署脚本** → 直接跑一键更新即可，无需先覆盖 deploy 脚本。

## 发布资产（双源互证）

- `myblog-backend.zip` — 后端 4 个 py 改动（feed_agg / diagnostics / admin / config）
- `vue-frontend-dist.zip` — 前端无变更，复用上次 build 产物
- `sha256.txt` — 整文件哈希，与 zip 注释内嵌的「内容区」SHA256 互为独立校验
