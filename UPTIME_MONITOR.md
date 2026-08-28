# UptimeRobot 监控配置清单（llhhy-blog）

> 目的：补上「线上异常你不知道」的盲区。今天两次线上问题（RSS 订阅不了、导航栏不切英文）
> 都是本地正常、线上才暴露，且是朋友/你自己发现，不是系统告警。加外部监控后，
> 线上异常会第一时间通知你。UptimeRobot 免费版可监控 50 个 URL，完全够用。

## 一、操作步骤（照着点）

1. 打开 https://uptimerobot.com 注册（免费）。
2. 左侧 **Dashboards → Add New Monitor**（逐个添加下表 6 项）。
3. **Monitor Type** 选 **HTTP(s)**。
4. **URL** 填下表「URL」列（把 `你的域名` 换成真实域名，如 `https://llhhy.com`）。
5. **Interval** 选 **5 minutes**（免费版最短间隔，足够）。
6. **Alert Contacts**：先去右上角 **My Settings → Alert Contacts** 添加你的邮箱；
   若要微信告警，用 **Server 酱（sct.ftqq.com）** 或企业微信群机器人生成一个 Webhook URL，
   在 Alert Contacts 里选 **Webhook** 类型粘贴进去。
7. **Advanced（高级）** 里对 feed/sitemap/robots 三项勾选 **Keyword**，填下表「Keyword」列；其余留空。
8. 点 **Create Monitor** 保存。

## 二、监控项清单（直接抄）

| # | 名称 | URL | 检查方式 | Keyword（高级里填） | 说明 |
|---|------|-----|----------|----------------------|------|
| 1 | 首页 | `https://你的域名/` | 状态码 200 | 不填 | 站点存活 |
| 2 | **RSS 订阅** | `https://你的域名/feed.xml` | 状态码 200 | `<?xml` | **最关键**，今天坑的就是它；返回必须含 XML |
| 3 | 站点地图 | `https://你的域名/sitemap.xml` | 状态码 200 | `urlset` | 搜索引擎抓取 |
| 4 | 爬虫规则 | `https://你的域名/robots.txt` | 状态码 200 | `Sitemap:` | 搜索引擎入口 |
| 5 | 文档页 | `https://你的域名/docs` | 状态码 200 | 不填 | 文档可用性 |
| 6 | 后台登录 | `https://你的域名/admin` | 状态码 200 | 不填 | 后台可达（登录页，勿填 keyword 防误报） |

> 第 2/3/4 项的 Keyword 是双保险：即使状态码 200，但内容被 Nginx 兜底成 `index.html`
> （就像今天 RSS 的坑），Keyword 不匹配也会告警——能直接抓出「拿到网页而非 XML」。

## 三、告警设置建议

- **Alert when down**（宕机才告警），避免正常抖动噪音。
- **Confirmations（确认次数）** 设 **2**：连续 2 个周期（约 10 分钟）都异常才发告警，减少误报。
- 联系人：邮箱必填；微信通过 Server 酱 / 企业微信 Webhook 推送。
- 免费版支持 email、Telegram、Slack、Discord、Webhook；SMS 仅付费。

## 四、HTTPS 证书到期监控（自动，无需额外配置）

UptimeRobot 对 HTTPS 类型的 URL 会自动检测证书有效期，剩余 <30 天会标黄告警，
等于免费送你一份「证书过期提醒」，不用再单独设日历。

## 五、可选的进阶（P1，以后再做）

- 把 `tools/check_i18n.py` 接进 GitHub Actions，每次推代码自动跑 i18n key 校验。
- 加一个「根路径 Flask 路由 ↔ Nginx 反代清单」对账脚本，防今天 RSS 那种「路由没被代理」的坑。
