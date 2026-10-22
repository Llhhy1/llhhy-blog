# content_migrate · 内容迁移插件

把 **WordPress** 或 **Typecho** 的文章迁移到 llhhy-blog：标题、正文、摘要、发布时间、
分类、标签、特色图；可选把正文图片下载到本站。

## 启用

插件随代码发版，不热加载。在服务器环境变量（或 `.env`）里加：

```bash
ENABLED_PLUGINS=content_migrate
```

重启 gunicorn / 宝塔进程后生效。然后进后台 **插件管理 → 内容迁移 → 打开**，
或直接访问 `/admin/migrate/`。

> 如果同时还启用了别的插件，用逗号分隔：`ENABLED_PLUGINS=foo,content_migrate`。

## 输入格式

### WordPress：WXR

后台「工具 → 导出 → 所有内容」得到 `.xml`。插件读取：

- `post`（文章）；`page` / `attachment` 会跳过并在预览里计数；
- 状态：`publish` 视为已发布，其余（draft / pending / private / future）一律存草稿；
- `category` / `post_tag`；一篇文章只保留**第一个**分类（本站文章是单分类模型）；
- 特色图（`_thumbnail_id` 对应的附件地址）；
- `post_date_gmt` / `post_modified_gmt`（按 naive UTC 存储，与全站一致）。

### Typecho：SQL 备份

Typecho 没有官方 XML 导出，使用 phpMyAdmin / 面板导出整库 `.sql` 即可
（表前缀任意，插件自动识别 `*_contents`）。会读取：

- `*_contents`：`post` / `post_draft`（`page` / `attachment` / `revision` 跳过）；
- `*_metas` + `*_relationships`：分类与标签；
- `text` 开头的 `<!--markdown-->` 标记会自动去掉，其余按原样保存；
- 密码保护文章会导入为草稿（导入器不支持密码），并在结果里提示。

> 「Typecho → WordPress → 本站」也可以：先转到 WordPress 再导出 WXR，效果等价。

## 选项

| 选项 | 默认 | 说明 |
|---|---|---|
| 导入后状态 | 沿用原站 | 也可以「全部发布 / 全部草稿」 |
| 保留原站 slug | 开 | 保留旧链接、并让重复导入可去重；冲突时追加 `-2` |
| 下载图片 | 关 | 正文 `<img>` 与特色图下载到 `static/uploads/`；单张 ≤ 5MB、每次 ≤ 200 张 |
| 原站地址 | 空 | 补全 `/usr/uploads/...` 这类相对图片地址，如 `https://old.example.com` |

## 不会导入的内容

- **页面（Page）**、评论、用户/密码、附件库、主题与插件设置；
- 原站的多分类（只留第一个）；
- 站外图片若开启下载且失败，会**保留原地址**并在结果里提示（不会静默丢弃）。

## 安全与限制

- 仅管理员可访问；POST 走全局 CSRF 校验；上传上限 **64MB**（建议按年份拆分导出）。
- XML 拒绝 `DOCTYPE` / `ENTITY`（防实体膨胀）；SQL 只做文本解析，不执行。
- 图片下载走 `outbound.open_url()`：公网校验 + 固定 IP + 禁 3xx + 禁环境代理，
  不接受 `data:` 与 SVG；单张/数量双上限。
- **导入不会触发**「新文章」通知、SEO 推送、订阅邮件 —— 迁移 200 篇不该给订阅者发 200 封信。
  发布状态在落库后直接设置，再补一次 FTS 同步。
- 重复导入安全：保留 slug 时按 slug 去重；关闭保留时按「标题 + 创建时间」去重。
- 单篇失败不会中断整体；结果里会列出失败原因（最多 50 条）。

## 推荐迁移流程

1. 在原站完整导出（WordPress WXR / Typecho SQL），并**留档原站备份**；
2. 本站先做一次数据库备份（后台「数据备份」）；
3. 上传 → **先预览**（只看统计，不写库）；
4. 确认分类/数量无误 → 开始导入（走后台任务，可离开页面稍后回来看）；
5. 抽查 2~3 篇：图片、代码块、分类、标签、发布时间；
6. 如果开了「下载图片」，确认 `static/uploads/` 有新增文件、正文图片能打开；
7. 迁移完成后再决定是否让旧站 301 到新站（不在本插件范围）。

> 图片本地化只处理正文里的 `<img src="...">` 与特色图；`srcset`、`<a href>` 指向的
> 图片仍保留原站地址（通常不影响阅读，需要时可在导入后手动替换）。
