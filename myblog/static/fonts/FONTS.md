# 打包字体说明

本目录存放**随仓库分发**的 CJK 字体，供 `myblog/og_image.py` 生成文章分享卡
（og:image，1200×630 PNG）时使用。

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
