"""v3.7.1 发布脚本：创建 GitHub Release 并上传资产。

PAT 从环境变量 GH_TOKEN 读取（绝不硬编码）。资产走 uploads.github.com 域名。
运行：GH_TOKEN=xxx ./venv/Scripts/python _make_release_v3.7.1.py
"""
import os
import sys
import json
import urllib.request

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("ERROR: 环境变量 GH_TOKEN 未设置")
REPO = "Llhhy1/llhhy-blog"
TAG = "v3.7.1"
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


body = """## v3.7.1 · 访问统计新增 Bot/爬虫识别（R38 审计通过）

### 新增能力
- 后台「📊 访问统计」新增**爬虫识别**维度：访问记录时从 User-Agent 自动识别是否为 Bot/爬虫，并细分**搜索引擎(search)/AI(ai)/工具脚本(tool)/未知(unknown)** 四类。
- `VisitLog` 新增 `is_bot`/`bot_name`/`bot_category` 三字段（含 SQLite 迁移脚本 `myblog/migrate_visit_log_bot.py`，幂等可重跑）。
- 统计看板新增「🤖 爬虫访问」占比卡片 + 「🤖 爬虫/Bot 来源排行」（列出 Googlebot/Bingbot/Baiduspider/GPTBot/CCBot/ClaudeBot 等具体爬虫名与类型标签、次数、占比）。

### 部署注意：本次有 SQLite DB 迁移
覆盖后端代码后，**必须先在服务器跑迁移脚本**（否则旧库无新列会 500）：
`python myblog/migrate_visit_log_bot.py`（blog.db 不在默认路径时用 `BLOG_DB=绝对路径 python myblog/migrate_visit_log_bot.py`），再宝塔「停止 -> 启动」gunicorn。

### 验证
- 新增 `smoke_v371.py`（19 项断言全通过）；`py_compile` 通过。
- R38 七维审计 **0 Blocker，0 高危**（详见 `myblog/SECURITY_AUDIT.md` 第四十八轮）。"""

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
