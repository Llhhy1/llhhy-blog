"""v3.8.0 发布脚本：创建 GitHub Release 并上传资产。

PAT 从环境变量 GH_TOKEN 读取（绝不硬编码）。资产走 uploads.github.com 域名。
运行：GH_TOKEN=xxx ./venv/Scripts/python _make_release_v3.8.0.py
"""
import os
import sys
import json
import urllib.request

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("ERROR: 环境变量 GH_TOKEN 未设置（需要 repo 权限的 Personal Access Token）")
REPO = "Llhhy1/llhhy-blog"
TAG = "v3.8.0"
API = f"https://api.github.com/repos/{REPO}"
UPLOAD = f"https://uploads.github.com/repos/{REPO}"


def api(method, url, data=None, is_upload=False):
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "llhhy-blog-release",
    }
    if is_upload:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


body = """## v3.8.0 · 反爬限流保护 + SEO 服务增强（R39 审计通过）

### 新增能力
- **反爬限流保护（bot_guard，默认关闭）**：基于 v3.7.1 的 Bot 识别，对高频/可疑请求限流与封禁。搜索引擎（Google/Baidu/Bing 等）默认白名单豁免，不影响 SEO 抓取；坏 Bot（tool/unknown 类，如 AhrefsBot/SemrushBot）走更严格阈值；达到拦截次数阈值才封禁一段时间。新增 `BotBlock` 表，后台「🛡️ 反爬限流保护」看板可查看并解封。
- **SEO 服务增强**：文章页新增 JSON-LD `BlogPosting` 结构化数据 + Open Graph / Twitter Card 元标签；`sitemap.xml` 增强（lastmod/changefreq/priority/封面图）；`robots.txt` 支持后台配置屏蔽指定坏 Bot；RSS/feed 增强（dc:creator 作者 + category 分类）。

### 部署注意：本次无 DB 迁移
`BotBlock` 新表由 `app.py` 的 `db.create_all()` 在重启时自动创建，**无需手工迁移脚本**。服务器直接跑一键更新；覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。后台开关「⚙️ 站点设置 → 反爬限流」**默认关闭**，确认无误后再按需开启。

### 安全审计（R39 · 第四十九轮）
发现并修复 1 处高危——后台解封表单原缺 CSRF Token（全局 `_csrf_protect` 对所有非豁免 POST 生效）导致「解封」按钮必定 403，已补全 `{{ csrf_input() }}`。其余 XSS/注入/越权/SSRF/限流/资源泄漏维度均通过。**1 高危已修，0 遗留**（详见 `myblog/SECURITY_AUDIT.md` 第四十九轮）。

### 验证
- 新增 `smoke_v380.py`（18 项断言全通过）；`py_compile` 通过。
- 打包校验：后端 zip 含 `myblog/bot_guard.py`、不含 `data/`、内嵌 `APP_VERSION = 3.8.0`。"""

print("creating release", TAG)
rel = api("POST", f"{API}/releases", json.dumps({
    "tag_name": TAG, "name": TAG, "body": body, "draft": False, "prerelease": False,
}).encode())
rel_id = rel["id"]
print("release id =", rel_id)

assets = ["myblog-backend.zip", "vue-frontend-dist.zip", "sha256.txt"]
for path in assets:
    with open(path, "rb") as f:
        content = f.read()
    name = os.path.basename(path)
    url = f"{UPLOAD}/releases/{rel_id}/assets?name={name}"
    api("POST", url, data=content, is_upload=True)
    print("uploaded", name)

print("RELEASE_OK id=", rel_id)
