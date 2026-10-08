# MCP 配置指南（只读 `/mcp` ＋ 写能力 `/mcp-write`）

> 本文摘自 `myblog/deploy_guide.md` 的「可选配置」部分，独立成文以降低主文档体量。
> **主线部署请回到 [部署手册](../../myblog/deploy_guide.md)。**
>
> MCP 不是上线必需功能：不配则两端点对外不可见，不影响博客运行。

## MCP 配置指南（两个端点一次配好：只读 `/mcp` ＋ 写能力 `/mcp-write`）

> 本节是**统一操作手册**；两端各自的来龙去脉（引入背景与安全设计）见仓库根目录 `CHANGELOG.md` 的 v3.10.0 / v3.12.2 条目
> （这两版早于 v3.18.6，已随v3.25.0 归档至 `docs/archive/CHANGELOG_v1-v3.18.5.md`）。
> 两个端点**完全独立**（各自 token / 各自开关 / 互不影响），但环境变量、Nginx、AI 助手接入可以**一次配完**。
>
> **v3.13.0 起：以下大部分操作可在后台点按钮完成**——登录后台 → 左侧「系统设置」→「🔌 MCP 服务」：
> - 两个内置端点**一键启停**（「停止」= 端点对外 404 不暴露存在，即时生效无需重启），token 只显示掩码（本体仍在宝塔环境变量）；
> - 可**登记外部 MCP 服务**（名称 / URL / Header / Token，token Fernet 加密落库，库里无明文），统一查看、启停、编辑、删除；
> - 每个服务都能生成 **「AI 脱敏接入指令」一键复制**：**脱敏版**含完整连接步骤但 token 用占位符（可放心转发给 AI，由它引导你填 token）；**完整版**（页面点「显示完整指令」）含真实 token，AI 拿到即可直接写好 mcp.json / 完成安装——完整版每次查看都记「🧾 操作日志」。
>
> 本节保留手工操作口径，作为无后台 / 脚本化部署时的对照。

### 两个端点速览

| | 只读诊断 `/mcp` | 写能力 `/mcp-write` |
|---|---|---|
| 用途 | AI 远程读健康状态（全站体检、DB 状态、版本一致性、错误日志、内容统计） | AI 远程建文（`create_post` 默认草稿；`list_recent_posts` 查重） |
| token 变量 | `MCP_AUTH_TOKEN` | `MCP_WRITE_TOKEN`（**必须与前者取不同值**） |
| 未配 token 时 | 整体关闭（401） | 整体关闭（**404**，连端点存在都不暴露） |
| 限流 | 60 次/分钟/IP | 10 次/分钟/IP（更严） |
| 审计 | — | 每次调用写「🧾 操作日志」（后台可查，username=`mcp`，记 token 前 8 位与来源 IP） |

### 第 1 步：生成两个不同的 token

```bash
python3 -c "import secrets;print(secrets.token_hex(32))"   # 跑两次，分别得到两个不同值
```
第 1 次输出 → `MCP_AUTH_TOKEN`；第 2 次输出 → `MCP_WRITE_TOKEN`。**不要填进代码、不要提交 git**。

### 第 2 步：宝塔填环境变量（Python 项目 → 设置 → 环境变量）

| 变量 | 必填？ | 说明 |
|---|---|---|
| `MCP_AUTH_TOKEN` | 用 `/mcp` 就必填 | 留空 = `/mcp` 关闭（401），不会裸奔 |
| `MCP_LOG_FILES` | 可选 | `/mcp`「最近错误日志」工具可读的日志绝对路径，逗号分隔；留空该工具不可用 |
| `MCP_ALLOWED_ORIGINS` | 可选 | 额外合法 Origin 白名单（防 DNS 重绑定），两端共用，一般留空 |
| `MCP_WRITE_TOKEN` | 用 `/mcp-write` 就必填 | 留空 = `/mcp-write` 关闭（404）；**须与 `MCP_AUTH_TOKEN` 不同值** |
| `MCP_WRITE_DEFAULT_PUBLISH` | 可选 | 默认 `0` = 无论请求传什么都**强制转草稿**；改 `1` 才允许 MCP 直接发布 |
| `MCP_WRITE_ALLOW_NOTIFY` | 可选 | 默认 `0` = 不群发；改 `1` 且请求显式 `notify_subscribers=true` 才通知订阅者 |
| `MCP_WRITE_ALLOW_SUPER_FIELDS` | 可选 | 默认 `0` = 忽略提权字段（`is_pinned`/`is_private`/`reward_*`/`author_id`） |

填完「保存」，然后宝塔对 Python 项目「**停止 → 启动**」（restart 不重载环境变量）。

### 第 3 步：Nginx 补两段反代（一次复制两段）

> 放在 `server { }` 里 `location / { ... }` 之前（精确匹配优先于前缀匹配，不加会被 Vue SPA 兜底成 index.html）。
> `8686` 改成你 Python 项目的实际监听端口。加完点「重载配置」。**站点必须 HTTPS**（token 走请求头）。

```nginx
location = /mcp {
    proxy_pass http://127.0.0.1:8686;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /mcp-write {
    proxy_pass http://127.0.0.1:8686;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

（可选，推荐）两段各加 IP 白名单，只放行你常用的出口 IP：
```nginx
    allow 你的公网IP;
    deny all;
```

### 第 4 步：上线核验（curl 四连，服务器或本机执行）

```bash
# ① /mcp 不带 token → 必须 401（若返回 HTML 说明反代没生效）
curl -i -X POST https://你的域名/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ② /mcp 带对 token → 返回工具列表 JSON
curl -s -X POST https://你的域名/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H "Authorization: Bearer 只读TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ③ /mcp-write 不带 token → 必须 404（已配 token 而没带对则是 401）
curl -i -X POST https://你的域名/mcp-write -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# ④ /mcp-write 带对 token → initialize 握手 JSON（server 名 llhhy-blog-write）
curl -s -X POST https://你的域名/mcp-write -H 'Content-Type: application/json' \
  -H "Authorization: Bearer 写TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

### 第 5 步：AI 助手接入（本机 `~/.workbuddy/mcp.json`，两个 server 一起配）

```json
{
  "mcpServers": {
    "llhhy-blog-diag": {
      "type": "http",
      "url": "https://你的域名/mcp",
      "headers": { "Authorization": "Bearer 只读TOKEN" }
    },
    "llhhy-blog-write": {
      "type": "http",
      "url": "https://你的域名/mcp-write",
      "headers": { "Authorization": "Bearer 写TOKEN" }
    }
  }
}
```

保存后到 WorkBuddy 连接器管理页，对 `llhhy-blog-diag`、`llhhy-blog-write` 各点一次「**信任**」才生效。之后可直接说「博客现在健康吗」（走只读）或「帮我建一篇草稿，标题是…正文是…」（走写端点，默认落草稿，后台审核后发布）。

### 安全红线（两端通用）

站点强制 HTTPS；token 定期轮换（两端分开轮换）；`/mcp` 尽量加 IP 白名单；写端点建议**保持 `MCP_WRITE_DEFAULT_PUBLISH=0`**（AI 只落草稿、人工后台把关发布），发布动作全部可在「🧾 操作日志」回溯。
