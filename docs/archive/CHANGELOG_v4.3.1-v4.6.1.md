# CHANGELOG 历史归档件（v4.3.1 ~ v4.6.1）

> **归档件**：本文件是 `CHANGELOG.md` 的历史段落拆分快照，不是当前文档。
> **拆分点**：v5.5.0 发版时 CHANGELOG 主文件逼近 200 KB 上限，按「新增版本写进主文件、最老一批历史段落才归档」搬出 v4.3.1 ~ v4.6.1。
> 近期版本请回主文件 `CHANGELOG.md` 顶部查看；本文件只保留历史，不再随版本更新。

---

## v4.6.1（2026-10-19）

### 修：壁纸被整站外框「套住」，首屏其实没铺满

v4.6.0 把 `.home-cover` 改成 `100svh`，但**漏掉了它外面还有一层框**。
`.site-frame`（v3.1.0 的整站大框）是：

```css
max-width: 1100px;  margin: 22px auto 28px;
padding: 0 16px;    border: 1px solid #e6e8eb;
border-radius: var(--theme-radius, 12px);  overflow: hidden;
```

首页内容在这个框里，于是壁纸：左右被 padding 挤窄、顶部被 margin 压出一条白边、
四角被圆角裁掉 —— 就是用户看到的「被一个框套住」。参考站 Butterfly **没有这层框**
（body 直接到 header），所以它的 `height:100vh` 才是真的。

线上实测截图确认：1440×900 下壁纸只占中间约 1100px，顶部有 22px 白条，
移动端左右各露一条白边。

**修法**：在「首页 + 已配壁纸」时把外框整体放开。

```css
:root:has(.home-cover.has-wall) .site-frame {
  max-width: none; margin: 0; padding: 0;
  background: transparent; border: 0; border-radius: 0;
  overflow: visible; box-shadow: none;
}
```

破框后下方内容会失去限宽（`.bento` / `.content` / `.home-social` 本身都没有
`max-width`），所以给首页根节点挂 `.home-page`，用
`.home-page > *:not(.home-cover) { max-width: 1066px; margin-inline: auto }`
把非首屏区块重新限宽居中（1066 = 1100 − 16×2 − 1×2，即原框内的可用宽度）。

未配置壁纸时 `:has()` 不命中，外框照旧，**零影响**。

### 修：文字阴影只有一层大扩散，亮色壁纸上照样发糊

原 `text-shadow: 0 2px 18px rgba(0,0,0,.32)` —— 18px 的扩散看着像光晕，
实际不提供锐利暗边。改成「近锐 + 远柔」双层：

- `0 1px 2px rgba(0,0,0,.55)`：把字边缘切出来
- `0 6px 28px rgba(0,0,0,.45)`：与背景分离

### 修：顶栏渐变不该跟着遮罩滑块一路降到 0

v4.6.0 让 `--wall-veil-top = overlay × 0.7`，本意是「遮罩淡则顶栏也淡」。
实测问题相反：顶栏是**白字**，遮罩调淡后导航项先糊。加下限：

```js
Math.max(0.28, overlay * 0.7)
```

### 验证方式（本版的关键）

前几版都是「构建通过 + 产物 grep」就算过，**这次用户实际看到的是错的**。
本版改用 `playwright-cli` 对**线上真实页面**取证：

1. 先截「修复前」线上图 —— 复现了框、白边、遮罩过重三个现象
2. 用 `page.evaluate` 把修复 CSS **注入线上页面**（不动线上文件），截图验证
3. 分别验桌面 1440×900 / 移动 390×844 / 滚动后（`.is-solid`）/ 遮罩 0.15 四种状态
4. 确认无误后才发版

> 教训：**「代码写了」「构建过了」都不等于「用户看到的是对的」**。
> 有浏览器可用时，视觉改动必须以真实截图为准。

### 范围

纯前端，**无表结构变更、无后端代码改动、无新依赖**。
改动文件仅 `vue-frontend/src/styles/global.css`、`vue-frontend/src/views/HomeView.vue`。

## v4.6.0（2026-10-19）

### 一、首页首屏：壁纸真正铺满整个屏幕

v4.5.0 把壁纸做出来了，但它**并没有真的占满屏幕** —— 首屏高度写的是
`calc(100vh - 58px)`，那个 `58px` 是当初为了给顶栏留位减掉的，视觉上就是
「壁纸从导航栏下面开始」。本版参照 [DeepChirp](https://blog.deepchirp.com/)
（Hexo + Butterfly 5.7.0）的做法重做，实测其 CSS 为：

```css
#page-header.full_page            { height: 100vh; background-attachment: fixed; }
#page-header.full_page #site-info { position: absolute; top: 43%; width: 100%; }
```

改动五处：

| 项 | 原 | 现 | 理由 |
|---|---|---|---|
| 首屏高度 | `calc(100vh - 58px)` | **`100svh`** | 原来扣掉顶栏不满屏。用 `svh` 而非照抄 `vh` —— 移动端地址栏收放会让 `vh` 跳动 |
| 背景 | 无 | **`background-attachment: fixed`**（仅 ≥641px） | 滚动时壁纸停在视口、内容掠过，产生纵深。移动端每帧重绘大图代价高；iOS Safari 对 fixed 另有支持缺陷，用 `@supports (-webkit-touch-callout: none)` 回退 |
| 文字位置 | flex 居中 50% | **`top: 43%` + `translateY(-50%)`** | 几何正中偏上是封面构图的稳态位置 |
| 滚动提示 | 跟在标题下面（`margin-top: 32px`） | **移出文字流，贴视口底部 `bottom: 18px`** | 不再随标题位置漂 |
| 顶栏 | `sticky`、不透明、占 58px 文档流 | **浮在壁上，滚过首屏变实心固定条** | 壁纸要能顶到屏幕最上沿，顶栏就不能占位 |

### 二、顶栏为什么能浮起来

顶栏独立于首屏（DeepChirp 是把 nav 塞进大图 header 里，天然浮在图上），
所以要靠两条机制接上：

- **位置与透明度交给纯 CSS**：`:root:has(.home-cover.has-wall) .site-header { position: fixed; … }`。
  选 `:has()` 而不是 JS 切 body 类 —— 路由切走后条件**自动失效**，
  不存在「切走了忘清理」的中间态，也不引入生命周期管理。
- **「滚过去了没」交给 `IntersectionObserver`**（threshold 0），不用 `scroll` 事件：
  这个 `100svh` 元素整页生命周期里进出视口最多两次，`scroll` 是每帧回调。
  命中后给顶栏加 `.is-solid` 恢复主题本色 + 毛玻璃；`onBeforeUnmount` 里
  `disconnect()` 并清掉 `.is-solid`。

不配壁纸时 `:has()` 不命中，顶栏保持原样，**未启用壁纸的站点零影响**。

### 三、一处自查出的真 bug（已修）

顶栏浮到壁上之后，它**不在 `.home-cover` 的 `background-image` 里**，拿不到那层遮罩，
白字会直接压在亮色壁纸上。补了一条顶部渐变，强度与后台遮罩滑块联动 ——
但第一次实现把 `--wall-veil-top` 放进了 `coverStyle`（inline style 打在 `.home-cover` 上），
而 **CSS 自定义属性只向下继承**，`.site-header` 是它的兄弟节点，永远拿不到，
只会命中 fallback 常量 → **滑块联动是假的**。

改为挂在 `:root` 并在 `onBeforeUnmount` 里 `removeProperty`，避免把首页专用的渐变
留在全局污染其他页面。

### 四、刻意不照搬的两处

- **不删遮罩层**。DeepChirp 没有遮罩，纯靠 `text-shadow` 撑可读性，因为他的
  `banner.avif` 是自己做的暗色设计图；我们的壁纸是后台上传的任意图，
  白底壁纸上白字会瞎 —— 后台那个遮罩强度滑块保留。
- **不隐藏社交图标**。DeepChirp 桌面端 `#site_social_icons` 是 `display:none`
  （靠侧边栏显示联系方式），本站首屏图标是明确需求，保留。

### 五、本版范围

纯前端，**无表结构变更、无后端代码改动、无新依赖**。改动文件仅两个：
`vue-frontend/src/styles/global.css`、`vue-frontend/src/views/HomeView.vue`。

## v4.5.0（2026-10-18）

### 一、访客数据：平均阅读时间（全链路，此前零数据）

后台「访问统计」新增**平均单次阅读时长**卡片。之所以是「全链路」而非加个显示：
**此前根本没有任何时长数据** —— `ReadLog`/`VisitLog` 都无时长字段，前端
`visibilitychange` / `sendBeacon` 全目录 0 命中。

- `ReadLog` 新增 `duration`（秒，累计）+ Alembic 迁移 `a7e3c92d5b18`
- 前端在 `visibilitychange`(hidden) / `pagehide` / 组件卸载 / 切换文章时补报停留秒数
- 后台统计页展示「X 分 Y 秒」

四处必须处理的边界，每一个都有对应的失败方式：

| 陷阱 | 不处理的后果 | 本版做法 |
|---|---|---|
| `duration` 由客户端上报 | 一个 `{"duration":999999}` 就能把平均值抬到任意值 | 钳制到 `[0, 7200]` 秒 |
| 时长复用 `/api/stats/read` 入口 | 停留时长会**多次补报**，读一次被记成两三次，热门文章榜与「反复阅读」榜双双虚高 | 用 `only_duration` 开关分流到独立的 `add_read_duration()`（不动 `read_count`） |
| 分母用 `COUNT(*)` | `ReadLog` 一行 = 「一个访客对一篇的累计」，行数是访客数，均值被压到 1/N | 分母用 `SUM(read_count)` |
| `duration = 0` 的历史行进分母 | 升级前全是 0，「人均阅读时长」刚上线就是 0.3 秒 | 只统计 `duration > 0` 的行 |

**时长为什么挂在 `read_log` 而不是 `visit_log`**：前者按 `(post_id, ip)` 唯一，
累加语义天然成立；后者是「每次访问一行」的流水，算时长必须先配对相邻记录 ——
**读者关页面后没有后续记录，最后一段会整体丢失，系统性低估**。

⚠️ **区间维度做不了**：`read_log` 没有日期列（只有 `updated_at`），按区间过滤
必须另建按日汇总表。故本版只做**全站**口径，模板标签已写明，避免被误读成区间数据。
升级前历史阅读 `duration` 全为 0（不计入均值），短期内该数字偏低甚至显示「—」，
需积累新数据才准。

### 二、修复：访客属地排行榜长期混入爬虫

后台「访客区域排行榜」（全部时间 / 今日）与 v4.2.0 区间统计的「区间访客属地 TOP」
都**没有排除爬虫** —— `stats.py::_top_region()` 与 `_range_top()` 仅过滤空属地。
爬虫多为境外机房 IP，属地异步回填后会挤占真人省份的名次（榜单里混进
「美国· fremont」这类机房）。

**这是遗漏而非设计**：前台公开接口 `/api/geo/visitors`（`api/review.py`）一直都有
`VisitLog.is_bot.is_(False)`。

修法：`_range_top()` 新增 `human_only` 参数，**只在属地维度开启**。
没有一刀切，是因为「热门路径」里的爬虫抓取本身是真实的 SEO 热度，
跟着过滤会低估热门文章；「来源渠道」则是爬虫自身来源、本就没有读者信息。

### 三、主题中心大升级：可自定义壁纸 + 首屏大图

后台「主题中心」新增**首页壁纸**区块，前台首页顶部随之改为整屏大图。

- 亮色 / 暗色各配一张（暗色留空则沿用亮色），遮罩强度 0–0.8 可调
- 上传复用既有 `/admin/upload`（后缀白名单 + 文件头 16 字节魔数校验），**零新建数据表**
- 配置存 Setting KV `home_wallpaper`，符合项目「能不改表就不改表」纪律
- 首屏高 `100vh − 58px`（扣 sticky 导航），叠加站点标题 + 描述 + **联系方式小图标** +
  「向下滚动」提示；向下滚动即进入原有概览 / 文章列表 / 分页
- 联系方式图标复用 `lib/social.js` 的 `toSocialItem`（21 条平台规则，含 GitHub / 邮箱 /
  QQ / 微信的点击复制与二维码），**零新增数据、零后台改动**
- 未配置壁纸时退回 v3.4.1 的渐变横幅，原有观感不变

#### 安全：壁纸 URL 的三道限制

壁纸 URL 最终会进 inline style 的 `background-image`，因此限定得比一般配置更严：

1. **拒绝外部 URL** —— 否则等于让每个访客的浏览器替站主向第三方发起请求，
   读者的 IP 与 UA 就此泄漏；`data:` 前缀还能把任意内容塞进样式。
2. **拒绝 `..`（路径穿越）** —— 只判 `startswith("/static/uploads/")` 是不够的：
   `/static/uploads/../../config.py` 同样以该前缀开头，浏览器再把 `..` 规范化掉
   就打到别的路径。同时拒绝 `?` / `#` / `\`。
3. **「启用但一张图都没有」直接 400** —— 否则前台会渲染出一片没有任何内容的纯色空区。

`POST /api/theme` 现支持纯壁纸请求（只带 `wallpaper` 不碰主题包）；
拼错的 `pack_id` **仍返回 400**，不会被壁纸分支静默吞掉。

#### 前台：亮暗切换交给 CSS 而非 JS

两张壁纸写成 CSS 变量 `--wall-light` / `--wall-dark`，由 `[data-theme="dark"]`
选择器取。主题切换发生在 `App.vue`，若这件事留在 JS 里就得双向同步，
漏一处就是「切了主题、壁纸还是亮色」。

### 四、验证

全量 **902 passed**（新增 28 条），ruff 全仓通过，lint 棘轮 F401 回落基线 116。
新增测试覆盖三组功能，含**反向守卫**（否则「永远返回空列表」也能全绿），
并对四处关键分支做了变异验证，全部正确变红：

| 变异 | 结果 |
|---|---|
| `_top_region` 的 `is_bot` 取反 | 2 红 |
| `_range_top` 的 `human_only` 分支取反 | 2 红 |
| 均值分母改用 `COUNT(*)` | 精确命中该条 |
| 补报时长误加 `read_count` | 单元级 + 端到端级 2 红 |

统计页的改动配了**直接渲染页面**的断言 —— v4.2.0 曾把卡片写在 `{% block %}` 外，
Jinja 子模板中 block 外的内容不渲染，静默丢失且无报错，只测接口永远发现不了。

## v4.4.2（2026-10-13）

### 一、修复：后台游戏审计的四处「结论与安全状态脱钩」

用户报障：后台「游戏平台 · 收录与审核」的审计不可信。逐项查证后确认四个缺陷，
**其中第一项有生产数据库里的自证材料**（见下）。

#### 1. 🔴 送审代码被砍掉 75%，审计是「假审计」

`_sample_code()` 对**每个文件硬砍前 3000 字符**，而 `limit=60000` 形同虚设——
累计计数加的也是砍后长度，永远碰不到 60000，等于「每文件 3000」的天花板。
实测线上两个内置游戏：

| 游戏 | game.js 实际 | 旧版送审 | 丢失 |
|---|---|---|---|
| 恐龙快跑 | 12153 字符 | **3000** | **75%** |
| 就是按一下 | 7883 字符 | **3000** | **62%** |

**证据就在自己的审计结论里**——线上 `dino-run` 的 LLM 结论原文写着：

> "game.js 源码在末尾处被截断，**无法完全确认后续代码**"

LLM 明确说了「我只看到了 25%」，系统照样把 `verdict` 记成 `safe` 并入库。
即：**恶意代码只要落在第 3001 行之后，就 100% 逃过 LLM 审计。**

修法：取消每文件硬砍，改为**两级上限**（单文件 ≤ 40000、总预算 120000），
超限时**按比例削减并头尾都保留**（恶意代码常藏在文件尾），且**在送审文本文首
显式注入覆盖率声明**——否则收审方无从知道自己看的是残片，就会把
「没看到问题」误报成「没有问题」（这正是线上那条结论的成因）。

修复后实测：`dino-run` 送审量 4162 → **13409 字符（100% 全量）**。

#### 2. 🔴 `verdict` 从未被解析，审计结论与放行完全脱钩

LLM 返回 `{"verdict":"safe|risk|unknown"}`，但旧代码只把原文 `text[:3000]` 塞进
`audit_summary` 就结束了。后果：**判 `risk` 也能直接点「通过上架」**（`approve`
分支不读结论），且列表页只有一个「静态分」列（那是静态扫描的分，与 LLM 结论是
两件独立的事，并排显示纯属误导）。

修法：新增 `_extract_json()`（三级降级：直接解析 → 剥 ```` ```json ```` 围栏 →
截取最外层花括号；**失败返回 `None` 而非抛**），解析 verdict 并写进结论首行；
列表页新增审计徽标（LLM 安全 / 有风险 / 无法判定 / 未审计），与静态分分行显示。
`risk` 时把静态分压到 0，避免「静态分 94 + verdict=risk」并列误导。

#### 3. 🔴 审计失败后仍显示旧结论 —— 失败伪装成「已审」

旧实现失败时只 `return False`，**不写库**。于是对同一游戏重新审计如果失败
（Key 失效 / 超时 / 限流 / 配置不完整），后台仍显示**上一次那个 safe**。

修法：所有「拿不到结论」的出口统一落 `unknown` 并附失败原因，历史结论拼接在
「——— 历史结论 ———」之后留痕。**唯一例外是 LLM 总开关关闭**（那是「没审」
而非「审了没结论」，刻意不覆盖旧记录）。

> 🔑 首版修复**自己漏了一个出口**（配置不完整时直接 return），被本轮测试抓出来，
> 补了 `test_missing_llm_config_also_overwrites_old_safe`。
> 教训：**「失败必须落库」要枚举每条早退路径，不能只包 except 那一处。**

#### 4. 放行与审计结论耦合：风险二次确认（保留站长最终裁量）

按站点定位选择「二次确认」而非服务端硬拦：判 `risk` / 未审计 / `unknown` 时，
第一次点「通过上架」只渲染确认页（**不落库**），确认后才真正上架，并把风险摘要
与「站长确认放行」字样写进 `admin_note` + `log_audit`，事后可追溯是谁放行的。
判 `safe` 时直接放行（否则确认页会变成永远清不掉的噪音——**这条也写了反向守卫**）。

verdict 不新增表字段（项目纪律：能不改表就不改表），以固定前缀
`LLM 审计（安全|有风险|无法判定）：` 落在结论文本首行解析；
老数据（v4.4.2 之前的「LLM 审计：」原文格式）一律判 `unknown`——那批结论
本来就未被解析过，当 safe 是错的。

#### 5. 🐞 顺带修掉一个把自己坑了的 bug

写结论时间戳时用了 `datetime.now()`，但本项目有 `myblog/_time.py` 与标准库
`datetime` **同名**，`import datetime` 拿到的是那个封装模块（只有 `utcnow`，
没有 `.now`）→ 抛 `AttributeError` → 被外层 `except Exception` 吞掉，
**伪装成「审计失败」**。第一版修复因此整个写库路径静默失效，是靠测试抓出来的。
已改用项目唯一时间真相源 `utcnow()`。

### 二、新增内置游戏《贪吃星》（v4.4.2）

- `myblog/builtin_games/star-eater/`：单文件 Canvas 贪吃蛇变体，15×15 格，
  吃星星变长、随长度提速（132ms → 62ms 封顶）、碰壁/咬自己结束、
  空格填满即通关；最高分落 `localStorage`（读写均 try 兜底——沙箱禁存储时
  宁可没最高分也不能开不了局）。
- 移动端优先：滑动 + 方向键/WASD 双通道、180° 反向拦截、长按方向键连发；
  触屏才显示方向按钮（桌面显示只会碍事）；页面隐藏时重置计时，回来看不
  会一次性补上大量步数；高 DPI 下画布按 2 倍渲染避免糊。
- 走完整收录链路验证：manifest 校验通过、入口存在、**静态扫描 99 分**
  （唯一发现是 `localstorage` info 级，已 try/catch 兜底）。
- ⚠️ `update.sh` **不会**自动收录内置游戏（有意如此，避免部署覆盖已收录内容）；
  升级后需手动跑一次 `python myblog/tools/seed_games.py`（`builtin_games/`
  会被 `add_tree` 自动打进后端 zip，无需改打包白名单）。

### 三、验证

- 新增 `tests/test_games_audit_v442.py` **22 条**，覆盖四个缺陷 + 静态扫描未回归。
- **变异 4 组全红**：① 恢复每文件硬砍 3000 ② 去掉 verdict 解析
  ③ 去掉「配置不完整」出口的落库 ④ 去掉放行二次确认闸门；恢复后全绿。
- 修复后送审覆盖率实测：`dino-run` 4162 → 13409 字符（全量）、
  `star-eater` 11880 字符（全量）。

---

## v4.4.1（2026-10-13）

### 一、修复：后台「全站体检」误报「未找到备份文件」（用户报障）

**现象**：本地与云端（坚果云 WebDAV）备份**都配了、也都在跑**，体检的「数据备份」卡片
却显示**未找到备份文件**。

**生产实证**（部署前先去看真实文件长什么样，不信代码里的路径假设）：

| 写入方 | 服务器实际路径 | 文件数 |
|---|---|---|
| `update.sh` 每次部署前直拷 | `/www/wwwroot/myblog/data/backup` | **141** |
| `backup.py` + 每天 04:00 cron | `/www/wwwroot/backups` | **37**（含当天 `blog_backup_20260103_040001.zip`） |
| DB `backup_dir` | 空（走默认） | — |
| DB `backup_webdav_url` | `https://dav.jianguoyun.com/dav/blogbackup` | 已配 ✓ |

**根因**：体检只猜了一条**恒不存在**的路径，且三处都错：

1. 目录名写成 `data/backups`（**复数**），实际是 `data/backup`（**单数**，update.sh 用的）；
2. **从不去看 `BACKUP_ROOT`** —— 定时任务真正落盘的地方（37 个文件就在那儿）；
3. 用 `REPO_ROOT/myblog/data/…` 拼路径，而线上代码（v3.18.6 起）**直接铺在站点根**、
   没有 `myblog/` 这一层 → 服务器上这个路径永远不存在。

**修法**：新增 `_backup_search_dirs()`，按「**真实写入方**」枚举候选目录 —
后台配置 / `BACKUP_DIR` / **`backup.BACKUP_ROOT`（唯一真相源）** / `<代码同级>/data/backup`，
跨全部目录取 mtime 最新的一个，并**标注它来自哪个来源**。
🔑 定时任务那条**直接取 `backup.BACKUP_ROOT` 而不自己重算路径规则** —— 重算等于把写入方的
规则抄一份，抄错就是本 bug 本身（与 v4.2.0 发版时「复刻双源互证算法连错三处」同一个教训）。

顺带两个改进：
- **配置了却不存在的目录会显式列为「目录缺失」并置 warn** —— 那是「配了没生效」，
  静默忽略等于把坏配置藏起来；
- 「本地备份目录」现在列出**全部有效目录**而非单个。

### 二、验证
- 新增 `tests/test_diagnostics_backup_v441.py` **6 条**，含一条**反向守卫**
  （目录存在但无备份文件时必须仍报「未找到」，防止修宽成永远说 OK 的假体检）。
- **变异验证**：把「查 `BACKUP_ROOT`」与「查部署目录」两处摘掉（= 旧逻辑）→
  **3 条立刻变红**；还原后 6 条全过 —— 守卫承重，非空话。
- ⚠️ 用例全部包在 `app.app_context()` 内：`read_setting_db()` 脱离上下文会**直连真实库**
  `myblog/data/blog.db`（不是"读不到"，是**读错库**）。

## v4.4.0（2026-10-13）

### 一、移动端「内容全套」：公告 / 留言 / 订阅 / 分类·标签·系列 / 友链本体 / 版本历史 / 媒体库

v4.3.0~v4.3.1 把「文章 + 评论 + 访客」搬上了手机，但后台还有一整排只能回电脑才能做的事。
本次补齐**内容管理这一批**（30 → 66 个 `/api/mobile/*` 端点），并且照旧一条原则不放松：
**JSON 侧不写第二套业务逻辑**，全部复用后台核心函数。

**新端点（按界面分组）**

| 组 | 端点 | 权限 |
|----|------|------|
| 公告 | `GET /mobile/announcements`、`GET/POST /mobile/announcement[/<id>]`、`POST …/active`、`POST …/delete` | 管理员 |
| 留言 | `GET /mobile/guestbook`、`POST /mobile/guestbook/<id>/read`、`POST /mobile/guestbook/read-all`、`POST /mobile/guestbook/<id>/delete` | 管理员（`ip` 字段仅超管） |
| 订阅 | `GET /mobile/subscribers`、`POST /mobile/subscriber/<id>/active`、`POST /mobile/subscriber/<id>/delete` | 管理员（邮箱全量仅超管） |
| 分类 | `GET /mobile/categories`、`POST /mobile/category`、`POST/PUT /mobile/category/<id>`、`POST …/delete?move_to` | 管理员 |
| 标签 | `GET /mobile/tags`、`POST /mobile/tag`、`POST /mobile/tag/<id>/delete`、`POST /mobile/tags/merge` | 管理员 |
| 系列 | `GET /mobile/series`、`POST /mobile/series`、`POST/PUT /mobile/series/<id>`、`POST …/delete?move_to` | 管理员 |
| 友链本体 | `GET /mobile/links`、`POST /mobile/link`、`POST/PUT /mobile/link/<id>`、`POST …/delete`、`POST /mobile/links/reorder` | 管理员 |
| 版本历史 | `GET /mobile/post/<id>/history[/<hid>]`、`GET …/history/diff?a=`、`POST …/history/<hid>/rollback` | 可编辑者（`_can_edit_post`） |
| 媒体库 | `GET /mobile/media`、`POST /mobile/media/delete` | 管理员 |

**顺带补上的首屏指标**：`/mobile/overview` 的 `counts` 新增 `unread_guestbook`。
后台导航角标早就有这个数（`inject_notification_counts` 的 `pending_guestbook`），
App 之前却只能自己拉一页留言去数 —— 现在两端同源。

### 二、这次一并补的**后台缺失能力**（不是只为移动端加的）

盘点时发现三件事在网页端也做不到，本次一起补，移动端与网页端共用同一份实现：

- **公告没有编辑入口**：原先只有「新建 / 启停 / 删除」。公告一删不进回收站、无法还原，
  重建还会掉到列表末尾 —— 改一个错别字的代价是丢掉整条公告的位置。新增
  `POST /admin/announcement/<id>/update` + `templates/admin/announcements.html` 的编辑行。
- **友链没有编辑入口**：`name/url/description/sort` 全都不能改，只能删了重建（丢排序位置）。
  新增 `POST /admin/link/<id>/update`（与新增共用 `save_friend_link_core`）。
- **友链没有排序界面**：`sort` 只能靠新增时手填。新增 `POST /admin/links/reorder`
  （整单顺序提交，`sort=(i+1)*10` 留出插位空档；**未列出的 id 一律不动**），
  页面用 ↑↓ 直接调，改动立刻保存。

`set_link_rss` 这条旧路由也一并接到 `save_friend_link_core` 上：原先它自己写了一遍
「存 rss + 软校验可达性」，与编辑路径各有一套判据 —— 正是本仓库反对的两套逻辑。

### 三、抽出来的核心（`*_core`，SSR 与 JSON 共用）

`admin/_helpers.py`：`ANNOUNCEMENT_LEVELS` / `_announcement_fields` / `create_announcement_core`
/ `update_announcement_core` / `normalize_link_url` / `save_friend_link_core`
/ `reorder_friend_links_core` / `rollback_post_core`。
`admin/taxonomy.py`：`create_category_core` / `rename_category_core` / `delete_category_core`
/ `create_tag_core` / `delete_tag_core` / `tag_usage_counts` / `create_series_core`
/ `rename_series_core` / `delete_series_core`。
`admin/media.py`：`collect_media` / `media_refs_for` / `delete_media_core`。

两条判据因此从「两套」变「一套」：

- **友链新增原先不查重**（同 URL 能连加两次），而审核友链申请那条路早就查了；
- **公告 `level` 原先不校验**（任意字符串都能进库，前台按 level 上色会出现未知档），
  且内容为空时能建出一条挂在前顶部的空横幅。

### 四、三条产品口径（本次确认过的决定）

- **订阅邮箱**：对管理员**遮敏**（`su***@exemple.com`）、对超管全量。理由是「可直接群发的
  PII + App 会本地缓存列表」。`Subscriber.unsub_token` **任何角色都不返回** —— 拿到它就
  等于能替别人免登录退订。
- **分类 / 系列改名**：**沿用后台既有行为**（无条件重算 slug），不改判据、不建别名表、
  不加 301；改为把「旧 → 新」如实回传（`note` 字段），由界面在提交前显示提醒。
  静默改名让外发链接 404 这件事，本来就该被看见。
- **删除类操作全部如实标注可逆性**：留言 / 订阅者 / 友链 / 媒体文件都是**硬删除**，
  不进回收站；媒体文件被文章引用时先返回 `409 + 引用清单`，必须再发一次
  `{"force": true}` 才真删（本模块唯一用 409 表达「请先确认」的接口）。

### 五、幂等性：状态类接口不收「翻转」

后台网页的启停按钮是**翻转**语义（点了就是相反状态，符合页面直觉），移动端一律改成
**显式目标值**：`POST …/active {"active": true|false}`。
弱网下客户端重发同一个请求，翻转会来回横跳（用户以为停用了，实际又启用），显式值重发
多少次结果都一样。同理，`_need_flag()` 对**缺字段**返回 400 而不是静默按 False 落库 ——
整单表单「没勾就是 False」是对的，改单个状态时就是静默改数据。

### 影响面

零表结构变更、零迁移（Alembic head 仍为 `c7a2f19b4d30`）、前端未改（不需要重新构建
`vue-frontend-dist.zip`）、无需 nginx 改动。后台行为变化只有两处：友链新增开始查重、
公告 `level` 开始归一（非法值落 `info`）。

### 测试

`tests/test_api_mobile.py` 从 25 条增至 **36 条**（新增 11 条），逐条覆盖上面的口径；`tests/test_doc_archival.py` 的归档守卫随 `PAIRS` 多一条而多 3 个参数化用例。CI 对照（同为 python 3.13 ubuntu）：main `fe117c7` 是 **7 failed / 824 passed**，本 PR 是 **7 failed / 838 passed** —— 824+11+3=838 正好对上新增，红的还是那 7 条（6 条 `test_cert_watch.py` 的 runner OpenSSL 问题 + 1 条 `test_point_log_dedup_and_retention`），一条不是本次引入。
权限分层（普通用户 / 管理员 / 超管三级）、level 白名单归一、显式启停幂等与缺字段 400、
邮箱遮敏 vs 超管全量 + `unsub_token` 不出现在**原始响应文本**里、留言 IP 分层与
「PII 不进审计」、分类改名的 slug 提醒与 `move_to` 两条去路（含非法落点必须报错）、
标签在用拒删与一键整理合并、系列 `name` 不唯一与删除脱离、友链 URL 归一/查重/排序只动
列出的 id、回滚只改三字段且回滚前自动备份、媒体库 `force` 与 `../` 路径穿越、
以及「网页端新补的编辑/排序入口真的能提交」（SSR 写、JSON 读回同一行）。

顺带修掉两处**本仓库既有**的实现问题：

- `media.collect_media` 原先把引用列表截断到 6 条后再取 `len()` 当 `ref_total`，
  那个数**永远不超过 6**，是个看起来像总数的假数；现在 `media_refs_for` 完整返回、
  调用方自己截断显示。
- 标签用量原先逐行 `len(t.posts)` 把每个标签的全部文章对象读进内存；改成
  `tag_usage_counts()` 一条 GROUP BY（后台标签页与 `/mobile/tags` 共用）。

另：本文件的测试模块加了 autouse 的 `_isolate_rate_limit` fixture。`/api/mobile/*` 的写接口
全按客户端 IP 限流，而测试客户端永远是同一个 IP，`utils.net._RATE` 又是模块级字典、
整个会话累积 —— 累积到 20 次发文就会出现「第 21 次返回 429、用例拿到 None 去下标」这种
与业务无关的红。限流本身仍由 `test_posts_pagination_v4.py` 专门测（同 `test_oauth.py` 的做法）。

### 文档归档（同 v3.25.13 的循环）

`SECURITY_AUDIT.md` 写完 R122 后到 163 KB，触发体积守卫（上限 160 KB）。按「新增轮次写进
主文件、历史段落才归档」把 **R91~R100** 逐字搬到 `docs/archive/SECURITY_AUDIT_r91-r100.md`
（80 KB），主文件从 R101 起、顶部指针已更新，`tests/test_doc_archival.py` 的 `PAIRS`
同步加了一条（归档件存在 / 主文件留指针 / 锚点齐全 三件事一起钉住）。查 R95、R98 这些
老轮次请去归档件，内容没做任何删改。

## v4.3.1（2026-10-13）

### 一条权限收口：访客日志与封禁清单从「管理员」升到「超管」

v4.3.0 的 `/api/mobile/visit-logs` 与 `/api/mobile/blocked` 按后台页面同级放行给了
**管理员（super + admin）**。权限判定本身没有放宽 —— 后台 `/admin/visit-logs` 本来就是
`admin_required` —— 但**出口的性质变了**：

- 页面是「一个人、一页 50 条、逐页翻」；
- JSON 接口是「可被脚本 `?page=1..N` 顺序抓完的整表」。

这两个端点输出的正是**访客 IP 原文**（`VisitLog.ip` 逐条 + 当前生效的封禁 IP 清单）。
把「能不能看」的等价性，直接当成了「能多快全部拿走」的等价性，是个判断漏洞。

**改动**：两个端点升为 `_role(super_only=True)`。

**为什么连同 `/blocked` 一起升**：拉黑与解封在 v4.2.0 就是超管专属，「谁被封了」这份清单
若管理员可见而不可操作，反而更容易造成「看到了却没法核对处理」的错觉 ——
**能决定封谁的人，才应该拿到那份 IP 清单**，清单与操作权限同级更好核对。

**没跟着一起升的，以及为什么**：`/mobile/comments` 也带 `ip` 字段，但后台评论页
（`admin/comments.html` 的「IP」列）本就把它展示给管理员，评论是人产生的、量级比访问日志小两个数量，
且审核是管理员的日常动作 —— 升上去只会把管理员的活挡在门外。这条界线刻意划在
**「逐次访问的原始日志表」** 与 **「人为产生的内容」** 之间，判据与残留风险写进
SECURITY_AUDIT **R121**（`R120.5` 段已随 R111~R120 归档至 `docs/archive/SECURITY_AUDIT_r111-r120.md`）。

**影响面**：只影响 `admin` 角色（非超管）调用这两个新端点；`/admin/visit-logs` 页面行为不变。
你本人是超管，App 侧一切照旧。零表结构变更、零迁移。

**测试**：新增 `test_访客日志与封禁清单仅超管可读` —— 同时断言两件事：非超管管理员拿
`403`，而该管理员仍能读评论 / 统计 / 首屏 / 回收站（防止收得过宽把日常工作挡掉）。
`tests/test_api_mobile.py` 从 23 条增至 24 条。
