# 可选功能：邮件通知 / 友链 RSS / 自动部署 / 访问统计

> 本文摘自 `myblog/deploy_guide.md` 的「可选配置」部分，独立成文以降低主文档体量。
> **主线部署请回到 [部署手册](../../myblog/deploy_guide.md)。**
>
> 以下功能全部可选，按需开启即可，不配不影响博客上线运行。

## 邮件设置（新文章通知订阅者 · 后台配置）

> 邮件群发配置**不需要填环境变量**，直接在后台操作（更便捷）。

1. 登录后台 → 左侧「**📧 邮件设置**」（超管可见）。
2. 填写 SMTP 信息：
   | 字段 | 示例（QQ 邮箱） | 说明 |
   |---|---|---|
   | SMTP 服务器 | `smtp.qq.com` | 163 用 `smtp.163.com`，Gmail 用 `smtp.gmail.com` |
   | 端口 | `465` | QQ/163 用 465（SSL）；部分服务用 587（TLS，需取消勾选 SSL） |
   | 邮箱账号 | `你的QQ号@qq.com` | 发件登录账号 |
   | 授权码/密码 | `xxxxxxxxxxxxxxxx` | **QQ/163 邮箱必须用「授权码」**（邮箱设置 → 账户 → 开启 SMTP 后生成），不是登录密码 |
   | 发件人地址 | 同邮箱账号 | 一般等于账号 |
   | 使用 SSL | 勾选（465） | 587 端口取消勾选 |
3. 点「保存」→ 再填一个测试收件人邮箱 → 点「**发送测试邮件**」，收到邮件即配置成功。
4. 之后每次发布新文章，会自动给「✉️ 订阅者」里所有 active 邮箱发通知（含一键退订链接）。
   - 未配置 SMTP 时群发自动跳过，不影响发文章。

> **排错（异常栈直接打印到站点日志）**：若点「发送测试邮件」仍提示「错误详情见后端日志」，重部署后真实异常会打印到站点日志。定位站点目录：`ls /www/wwwroot/*/data/blog.db`（父目录即 `APP_DIR`）；查看：`tail -n 60 /www/wwwroot/<站点>/gunicorn.log | grep "SMTP ERROR"`。常见真实报错与对策：
> - `535 Authentication failed` → 授权码错（QQ/163 必须用邮箱后台生成的**授权码**，不是登录密码）。
> - `timeout` / `Connection refused` → 主机名拼错、端口错，或服务器出站 465/587 被防火墙/安全组拦截（国内机器常见）。
> - `SSL: wrong version number` → 端口与 SSL 开关不匹配：465 **必须勾选** SSL，587 **必须取消**勾选。
> - 另注意 `SMTP_PASSWORD_ENV_FIRST`（默认 `true`）：宝塔环境变量里的 `SMTP_PASSWORD` 优先于后台填的密码，若两者不一致以环境变量为准——核对宝塔「Python 项目 → 设置 → 环境变量」是否覆盖。

## 友链 RSS 聚合到广场（博客圈）· 排错（失败原因日志可见）

> 广场（博客圈）页面的「友链 RSS 聚合」依赖后台「友链管理」里给友链填的 RSS 地址。若广场上始终看不到友链文章，按以下顺序排查。

1. **确认友链填了 RSS 地址**：后台 → 「🔗 友链管理」→ 给每个要聚合的友链填 `RSS 地址`（如 `https://example.com/feed.xml` 或 `atom.xml`）。未填的友链不会聚合。
2. **确认服务器装了 feedparser**：SSH 进服务器 `pip show feedparser`；若未安装，在站点 Python 环境执行 `pip install feedparser==6.0.11`，然后宝塔「停止 → 启动」gunicorn。若未装，日志会明确提示 `pip install feedparser==6.0.11`。
3. **确认服务器能出站抓 RSS**：服务器安全组/防火墙放行出站 443（HTTPS RSS 多为 443）。可用 `curl -I https://友链RSS地址` 在服务器上自测连通性。
4. **看日志定位具体失败**：
   - 定位日志：`tail -n 60 /www/wwwroot/<站点>/gunicorn.log | grep "FEED AGG"`
   - 四类提示：
     - `[FEED AGG] 共 N 条友链，其中 0 条填写了 RSS 地址` → 后台补填 RSS 地址即可。
     - `[FEED AGG] 跳过友链「X」：RSS 地址未通过安全校验` → RSS 地址指向私有 IP（SSRF 防护拦截），换公网可访问地址。
     - `[FEED AGG] feedparser 未安装！` → 按提示 `pip install feedparser==6.0.11` 后重启服务。
     - `[FEED AGG] 抓取友链「X」RSS 失败: <错误类型>: <消息>` → 具体错误（超时/证书/格式），按消息修复（多为出站网络或 RSS 格式问题）。
5. **缓存**：聚合结果内存缓存 15 分钟。确认配置正确后，等 15 分钟或重启服务即时生效。

## 自动部署（GitHub push → 服务器自动更新）

> 想让「GitHub 推送代码 = 服务器自动更新」，只需三步。**可选功能，不配不影响使用。**

### 第一步：准备部署脚本

仓库根目录已提供 `deploy.sh` 模板（从 GitHub Release 下载最新 zip → 备份 data/ 和 uploads → 覆盖代码 → 重启）。上传到服务器：

```bash
# 宝塔「文件」上传 deploy.sh 到 /www/wwwroot/myblog/，然后终端执行：
chmod +x /www/wwwroot/myblog/deploy.sh
```

按你的环境修改脚本顶部的三个变量：`REPO`（默认已对）、`APP_DIR`、`FRONT_DIR`，以及 `RESTART_CMD`（重启方式，见脚本内注释）。

> **一键更新重启权限（重要）**：若一键更新卡在第⑥步 `Operation not permitted`，根因是 gunicorn 由宝塔以 **`mw` 用户**（非 `www`）启动，且宝塔 Python 项目**不是** supervisor 管理。请用**最新 Release 附带的部署脚本**覆盖 `update.sh`/`deploy.sh` 到 `/www/wwwroot/myblog/`（最新版重启逻辑：宝塔 CLI 优先 → 以实际运行用户 `runuser` 真杀 + 宝塔真实 gunicorn 路径重新拉起，彻底绕开跨用户 kill）。若项目名不是 `myblog`，改两个脚本里的 `PROJECT_NAME`；若 gunicorn 属主不是 `mw`，改 `APP_USER`。

> **一键更新完整性校验（三重防线）**：
> - **① sha256.txt 列表比对**：`update.sh` 下载后端/前端部署包后比对 Release 附带的 `sha256.txt`，不一致**直接终止更新**（防止下载损坏/被篡改）。
> - **② zip 注释内嵌哈希**：`package.py` 打包时把每个 zip 的 **「内容区」SHA256**（= 剥离 EOCD 尾注释后的 zip 字节，写入/修改注释不影响内容区）写进该 zip 自身的 EOCD 注释；`update.sh` 用内置 python 同样剥离注释重算内容区哈希二次比对。即使 `sha256.txt` 被整体替换，注释哈希依然能发现不一致（双源互证，解决「sha256.txt 自身被篡改」的死角）。注意：注释哈希按内容区计算，不能对含注释的整文件算（注释参与文件字节后必然对不上）。
> - **③ HMAC 签名**（可选）：若发布时设置了 `UPDATE_HMAC_KEY`，`package.py` 会为 `sha256.txt` 内容生成 HMAC 首行，`update.sh` 配置同一密钥后强制校验签名（不签名直接拒绝更新）。设置方法：本地打包机与服务器都配置同一个 `UPDATE_HMAC_KEY` 环境变量。
>
> 发布时请确保 `package.py` 生成的 `sha256.txt` 一并上传到 Release；若某次 Release 漏传，脚本会告警但不阻断（降级为仅告警）。

### 第二步：告诉后端脚本路径

宝塔「网站 → Python项目」→ 项目「设置」→「环境变量」新增：

```
DEPLOY_SCRIPT=/www/wwwroot/myblog/deploy.sh
```

> 同时建议配 `WH_DEPLOY_SECRET`（一段随机字符串），它是 Webhook 的鉴权密钥。**两个都配好后重启项目。**

### 第三步：GitHub 仓库挂 Webhook

1. 打开你的 GitHub 仓库 `Llhhy1/llhhy-blog` → **Settings → Webhooks → Add webhook**；
2. 填写：
   | 字段 | 值 |
   |---|---|
   | Payload URL | `https://你的域名/api/webhook/deploy?token=你在WH_DEPLOY_SECRET里填的字符串` |
   | Content type | `application/json` |
   | Secret | 留空（已用 URL token 鉴权） |
   | Which events | **Just the push event**（默认即可） |
3. 点 **Add webhook** 保存。

之后每次 `git push origin main`，GitHub 会 POST 到你的站点 → 后端校验 token → 自动执行 `deploy.sh` → 服务器自动更新。后台左下角版本号会变成最新版。

> **安全说明**：token 放在 URL 里会出现在 GitHub 后台，介意可改用 Header：把 Payload URL 设为 `https://你的域名/api/webhook/deploy`，并在 GitHub Webhook 的 **Secret** 字段填同一字符串（后端同时支持 Header `X-Deploy-Token` 校验，二者任一匹配即通过）。
> **防重放**：Webhook 请求必须在 Header 带 `X-Deploy-Time`（Unix 秒级时间戳），后端会校验与服务器当前时间差是否在 `WH_REPLAY_WINDOW`（默认 300 秒）内，超窗或缺失一律拒绝（HTTP 400）。GitHub 原生 Webhook 不带此头时，可改用**自建小脚本**（如 GitHub Actions 里 `curl -H "X-Deploy-Time: $(date +%s)" ...`）触发；或跳过该头后仍可用 URL token 校验（防重放会降级为仅鉴权——若需严格防重放请带该头）。
> **不会误伤数据**：`deploy.sh` 覆盖代码前会先备份 `data/blog.db` 和 `static/uploads/` 到 `data/backup/`，且解压时排除 `data/`，数据库永远不会被覆盖。

## 访问统计功能说明

- **统计入口**：前台导航「**统计**」→ `https://你的域名/stats`；后台仪表盘 →「📊 访问统计」。
- **统计内容**：累计/今日访问次数、访客区域排行（今日 + 累计 TOP10）、最受关注的文章（含回读人数）、常搜词汇 TOP10、24 小时访问时段分布。
- **统计口径**：前端每次打开/切换页面上报一次访问；打开文章记一次「阅读」（同一访客重复读会累加）；搜索关键词会被记录。
- **IP 属地识别**：服务器后台线程异步解析，国内源优先多源兜底（太平洋 pconline → ipwho.is → api.ip.sb → ipinfo.io，任一成功即返回），仅公网 IP 才查询、仅缓存成功结果（外部源恢复后历史空属地自动回填）；解析失败显示「未知」，不影响页面响应速度。
- **博客名称 / 浏览器便签**：后台 → 站点设置 → 可修改「博客名称」（前台顶部 Logo + 浏览器标签页标题）与「浏览器便签」（前台顶部一条可关闭的公告条，留空不显示）。
