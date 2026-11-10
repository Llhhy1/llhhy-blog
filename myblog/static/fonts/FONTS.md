# 打包字体说明

本目录存放**随仓库分发**的两套 CJK 字体，用途互不重叠：

| 文件 | 用途 | 许可 |
| --- | --- | --- |
| `wqy-microhei.ttc` | `myblog/og_image.py` 生成分享卡（PIL 画字 → 二进制嵌图） | GPL v2 + 字体嵌入例外 |
| `llhhy-serif-sc.woff2` | 浏览器前台正文衬线（v5.9.0 起） | SIL OFL 1.1 |

下半部分说明前台子集字体；文泉驿那份的历史坑见下节。

## 为什么必须打包

`og_image._cjk_candidates()` 的查找顺序是「**仓库内字体 → 系统字体**」。
只依赖系统字体时，一台**没有装 CJK 字体**的 Linux 服务器会让
`_find_font()` 返回 `None` → `render_og_image()` 返回 `None` → 接口**静默降级**
成 `og-default.png` 兜底图（**不报错**）。

v3.18.9 实测：本项目自 v3.16.0 上线分享卡起，线上一直返回兜底图——
因为 `myblog/static/fonts/` **从未真正落地**（而 `og_image.py` 的模块 docstring
却写着「仓库内打包开源字体」）。这种「找不到资源就安静降级」的设计让缺陷
潜伏了一个版本周期才被发现。**本目录就是那次修复的产物，请勿删除。**

## 字体清单

| 文件 | 字体 | 版本/来源 | 大小 | 许可 |
| --- | --- | --- | --- | --- |
| `wqy-microhei.ttc` | 文泉驿微米黑 (WenQuanYi Micro Hei) | 取自 `github.com/anthonyfok/fonts-wqy-microhei`（上游打包镜像） | 5.17 MB | **GPL v2 + 字体嵌入例外条款**（见下） |

- 该文件为 `.ttc` 合集，`index=0` 为 **WenQuanYi Micro Hei Regular**（已验证
  `PIL.ImageFont.truetype(path, size, index=0).getname() == ('WenQuanYi Micro Hei', 'Regular')`）。
- 覆盖 GB2312 / GBK 常用汉字，满足标题与摘要排版。
- sha256：`e4bca8df123ce01b104780f576ea1a58b9a5ff1662a91124b6d3180cb6c88212`

### 关于许可（重要）

文泉驿微米黑采用 **GPL v2 并附「字体嵌入例外条款」(Font Embedding Exception)**：
将字体**嵌入文档**以及**随分发**不受 GPL 的传染性约束，因此本项目可以在
GPL 之外分发自己的源代码。但请注意：

- **不要**把本字体声称为 OFL 字体（它不是）。
- 若将来替换为思源黑体 / Noto Sans CJK 等 **OFL** 字体，需一并替换本说明，
  并把体积纳入考量（Noto CJK `.ttc` 单字约 20 MB，是本文体的 4 倍）。

## 增删字体的注意事项

1. **命名约定**：`_cjk_candidates()` 会优先挑选文件名含 `Bold` / `Regular`
   的字体（v3.18.9 起 `.ttf`/`.otf`/`.ttc` 三种扩展名**都**参与匹配，修复了
   此前 `.ttc` 不参与、导致放入 `*-Bold.ttc` 也不会被优先选中的问题）。
   因此新增字重时请按 `xxx-Bold.ttc` / `xxx-Regular.ttf` 命名。
2. **打包**：`package.py` 的 `add_tree()` 递归收集 `myblog/`，仅排除
   `data` / `__pycache__` / `.git` / `node_modules` / `instance` / `.pytest_cache`
   与 `*.pyc`——`static/fonts/` 会**自动**进入 `myblog-backend.zip`，无需改打包脚本。
3. **改完必须清缓存**：分享卡有 `data/og_cache/` 磁盘缓存，**宝塔还在
   `proxy.conf` 里全局开了 `proxy_cache`**。换字体后要清两处，否则看到的仍是旧图：
   ```bash
   rm -f myblog/data/og_cache/*.png                              # 后端磁盘缓存
   find /www/server/nginx/proxy_cache_dir -type f -delete        # nginx 反代缓存
   nginx -s reload
   ```

## 前台网页字体：站点专用宋体子集（v5.9.0 起，**入版**）

`themes.py` 各衬线预设的 `font_sans` 首选 **`LLHhy Serif SC`**，由
`llhhy-serif-sc.woff2`（约 0.61 MB）+ `llhhy-serif-sc.css` 提供。它基于
**Noto Serif SC / 思源宋体**（Google + Adobe，**SIL OFL 1.1**）子集化而来，
按 OFL 要求随字体附带许可全文 `OFL-NotoSerifSC.txt` 与版权声明；内部
family 名已改为站点专名，避免与访客本机安装的完整版混淆。

### 为什么换掉京华老宋体（v5.4.4 ~ v5.8.0）

旧方案是官方 `cn-font-split` 的 **503 个 woff2 分片 / 24.8 MB**（全 CJK 覆盖），
随后端 zip 分发，占包体 **88%** —— 每次发版重传 29 MB，服务器直连 GitHub
仅 21~28 KB/s 必超时，`GH_MIRROR` 从可选变成必需。更关键的是其授权
「免费商用但**不可修改字体本身**」，因此不能重新子集化。

2026-11-10 只读实测：线上 13 篇文章 + 前端文案只用了 **2089 个汉字**，
命中 77/503 个分片（4.88 MB），其余 426 片几乎全是 CJK 扩展 B/C 区生僻字。
换用 OFL 字体后可按真实用字生成单个 woff2：**24.8 MB → 0.61 MB（40.8 倍）**。

> **观感变化（预期内，站主已确认）**：京华老宋体是 60 年代老铅印宋，
> 思源宋体更现代规整。章回主题的「一册书」质感仍在，但字面气质会变。

### 生成与更新

```bash
# 构建机一次性依赖（不进生产 requirements）
python -m pip install "fonttools[woff]" brotli

# 从线上公开 API 刷新用字清单 → 生成 woff2 / CSS / LICENSE
python tools/build_subset_font.py --refresh
python tools/build_subset_font.py --check     # 校验汉字覆盖 / 体积 / 内部 family
```

源字体 `NotoSerifSC-Regular.otf`（11.6 MB）由脚本自动下载到
`tools/.font-source/`（已加 `.gitignore`），**不入库**；产物 woff2 入版，
因此正常发版**不需要**跑这个脚本，也不需要联网。
用字清单 `tools/font_charset.txt` 入版，是离线可重复构建的基线。

写了新文章若出现「某几个字变成系统宋体」，跑一次 `--refresh` 再重新生成即可。
**缺字是优雅回落**：CSS 不写 `unicode-range`，浏览器遇到子集里没有的字会
自动走字体栈下一档（`Noto Serif SC` / `Songti SC` / `SimSun` / `serif`），
不会 404、不会白屏。emoji、韩文、变体选择符等源字体本就不含的字形，
由系统字体渲染，属标准行为。

### 🔴 字体栈有两个真相源

`themes.py` 的预设（`sage-sand` 等）与**内置主题包** `theme_packs/zhanghui.json`
各自带一份 `font_sans`。站主当前激活的是「章回」包，`/api/site` 的
`theme_tokens.font_sans` 来自包内 `tokens.light`，**不是** `themes.py` 预设。
换字体时两处必须同步改，否则会出现「代码改了但线上字体没变」—— 本地预览
反代线上 API 时会抓到 `getComputedStyle(document.body).fontFamily` 仍是旧值。
`tests/test_font_subset_v590.py` 已钉住所有内置包不得残留旧字体名。

### 为什么不 hotlink

本站 CSP 是 `font-src 'self' data:`（`myblog/security.py:75`），外链字体
根本加载不出来；即使放开，也是让每个访客的浏览器替本站请求第三方
（访客 IP/UA 外流 + 对方挂了字体就没了），与 `api/theme.py:_safe_wp_url`
拒绝外链壁纸是同一条理由。

### 旧资产的处理（重要）

- `.gitignore` 里 `myblog/static/fonts/kinghua/` 与 `kinghua.css` 两条**保留**：
  打包机上若有历史生成物，仍不该进 git。
- `package.py` 的 `EXCLUDE_DIRS` / `EXCLUDE_FILES` 显式排除这两条路径，
  **即使本地还留着 503 个分片也不会再进后端 zip**。
- `tools/fetch_kinghua_font.py` 保留作历史工具（守卫仍引用它的
  `URL_RE` / `build_css` 做幂等性回归），但**不再被任何部署流程调用**。
- 线上 `/www/wwwroot/myblog/static/fonts/kinghua/` 的历史分片**不自动删除**：
  `update.sh` 用 `rsync -a`（无 `--delete`）或 `cp -rf` 覆盖，包里没有的文件
  不会从线上移除。它们已无人引用，仅占约 25 MB 磁盘；如需回收，由站主
  手动确认后删除即可（删前先确认 `index.html` 已不再引用 `kinghua.css`）。

