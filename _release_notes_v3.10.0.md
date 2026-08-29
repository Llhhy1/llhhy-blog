# llhhy-blog v3.10.0 · 只读诊断 MCP + 内置插件全部下线

> 安全审计：R50 十二维 **0 遗留**。验证：pytest **31 passed**（新增 11 条 MCP 测试 + 重写 10 条插件框架测试）。

## 一、只读诊断 MCP 端点 `/mcp`（新增）

把「应用层健康状态」暴露给 AI 助手远程诊断——补的是云主机监控（Lighthouse MCP）看不到的那一层。

- 实现 MCP **Streamable HTTP 传输最小子集**（仅 POST、响应单 JSON，不流式），因此 **Flask 直接承载、零新依赖、零新进程**，博客崩了 MCP 不会拖垮它、MCP 崩了也不影响博客。
- 提供 5 个**只读**工具：`health_overview`（全站体检 9 维）、`db_status`（journal_mode + 渲染缓存命中率）、`version_info`（版本与迁移一致性）、`recent_errors`（日志尾部，自动打码）、`content_stats`（内容与待办统计）。

### 安全是设计出来的，不是靠自觉（四条代码级约束 + 测试兜底）

1. **认证 fail-closed**：未配置 `MCP_AUTH_TOKEN` 时端点整体返回 401，绝不存在「忘了配 token 就裸奔」；校验用 `hmac.compare_digest` 恒定时间比较，杜绝时序爆破。
2. **强制只读**：源码层不含任何写操作，由 `test_mcp_source_is_readonly` 静态审查（禁 `commit`/`add`/`delete`/`os.remove`/`subprocess`/`eval`）守住红线。
3. **日志必脱敏**：`SECRET_KEY`、`password`、`token`、`api_key`、`Bearer xxx` 统一打码；绝不返回任何凭据。
4. **路径不可遍历**：日志文件只能由环境变量 `MCP_LOG_FILES` 显式指定，不接受客户端传路径。
5. 另：按 IP 限流 60 次/分钟 + MCP 规范要求的 Origin 校验（防 DNS 重绑定）+ `/mcp` 加入 CSRF 豁免与 bot_guard 白名单（避免反爬误封）。

## 二、内置插件全部下线（变更）

- 移除 `contact_card`、`article_toc` 两个插件及 `static/plugins/` 下两个远程组件；**插件框架保留**（`plugins/__init__.py`、`signals.py`、后台「🧩 插件管理」页、前端 nav/sidebar/footer/html/remote_components 槽位）。
- `ENABLED_PLUGINS` 默认值改为空 → `create_app` 不加载任何插件，`/api/plugins` 返回空清单；前端槽位无数据渲染为空，不报错。
- `article_toc` 下线后文章目录回退到核心 `PostView.vue` 的内联 TOC（文首显示、不随滚动高亮）。
- 测试改为「临时插件驱动」（改写 `plugins` 包 `__path__` 指向 tmp 目录），不再依赖任何内置插件。

## ⚠️ 部署注意（必做）

**纯后端改动，前端产物无变化（可只覆盖 `myblog-backend.zip`）。**

1. 生成 token 填宝塔环境变量 `MCP_AUTH_TOKEN`：`python3 -c "import secrets;print(secrets.token_urlsafe(32))"`（不要填进代码、不要提交 git）。留空则 `/mcp` 关闭。
2. **Nginx 必须补 `location = /mcp` 反代**（否则被 Vue SPA 兜底成 index.html，返回 HTML 而非 JSON）：
   ```nginx
   location = /mcp {
       proxy_pass http://127.0.0.1:8686;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
   加完「重载配置」。**站点必须走 HTTPS**（token 在请求头里，HTTP 明文 = 裸奔）。
3. 建议对 `/mcp` 再加 `allow 你的出口IP; deny all;` 的 IP 白名单。
4. 覆盖 `myblog-backend.zip` → 宝塔 gunicorn **停止 → 启动**。
5. **上线核验**（逐条 curl）：
   ```bash
   # ① 无 token → 必须 401（若返回 200 或 HTML，说明反代没生效）
   curl -i -X POST https://你的域名/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   # ② 正确 token → 返回 JSON 工具列表
   curl -s -X POST https://你的域名/mcp -H 'Content-Type: application/json' \
     -H "Authorization: Bearer 你的TOKEN" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   # ③ 错误 token → 仍须 401
   ```

## 本机接入（让 AI 助手能调用）

编辑 `~/.workbuddy/mcp.json`：

```json
{
  "mcpServers": {
    "llhhy-blog-diag": {
      "type": "http",
      "url": "https://你的域名/mcp",
      "headers": { "Authorization": "Bearer 你的TOKEN" }
    }
  }
}
```

保存后到 WorkBuddy 连接器管理页面对新出现的 `llhhy-blog-diag` 点「信任」才生效。之后直接问「博客现在健康吗」即可远程诊断。

## 关于 Typecho 协议（已查实，本次未引入）

Typecho 主体 **GPL-2.0（强 copyleft，传染）**；其 Markdown 解析器是 **HyperDown**（PHP，上游 clean 副本 `segmentfault/hyperdown` 为 **BSD 3-Clause**）。结论：**不引入**——从 Typecho 直接抄会 GPL 传染、且 PHP 与 Python 不通需重写约 1500 行；v3.9.1 已把渲染降到 `2.7ms`，换解析器零收益且会丢 bleach 白名单的 XSS 防护。仅借鉴其架构/交互思路（不受版权保护），不复制代码。

---

APP_VERSION 升为 **v3.10.0**。详见 `myblog/SECURITY_AUDIT.md`（R50）、`myblog/deploy_guide.md`、`PLUGIN_SYSTEM.md`、`CHANGELOG.md`、`ROADMAP.md`。
