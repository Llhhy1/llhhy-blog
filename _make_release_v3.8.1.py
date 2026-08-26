"""v3.8.1 发布脚本：创建 GitHub Release 并上传资产。

PAT 从环境变量 GH_TOKEN 读取（绝不硬编码）。资产走 uploads.github.com 域名。
运行：GH_TOKEN=xxx ./venv/Scripts/python _make_release_v3.8.1.py
"""
import os
import sys
import json
import urllib.request

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("ERROR: 环境变量 GH_TOKEN 未设置（需要 repo 权限的 Personal Access Token）")
REPO = "Llhhy1/llhhy-blog"
TAG = "v3.8.1"
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


body = """## v3.8.1 · 修复「更新后后台 500」部署阻断补丁

### 修复内容
- **根因**：后台统计页依赖 `visit_log` 表的 bot 识别三列（`is_bot`/`bot_name`/`bot_category`，v3.7.1 新增）。`db.create_all()` 只对「不存在的表」建表、**不会给已存在的表补列**，因此任何没跑过 v3.7.1 迁移脚本的旧库升级到 v3.8.0 后，`compute_summary()` 触发 `no such column: visit_log.is_bot` → 后台 500。
- **修复**：在 `app.py` 启动序列新增 `_migrate_visit_log_table()` **自愈迁移**（幂等 ADD COLUMN，每次启动自动补列，无需手动脚本）。覆盖后端并重启后即在首次启动自愈，彻底消除该 500。
- 配套：APP_VERSION 升为 3.8.1；新增 `_debug_admin500.py` 复现/验证夹具（已移除，不随发版）。

### 升级注意
- **无需手工迁移**：v3.8.1 启动会自愈补列，覆盖后端 → 宝塔「停止 → 启动」gunicorn 真正重载即可。
- 前端无变动，可沿用既有 `vue-frontend-dist.zip`（本轮资产中的前端 zip 与 v3.8.0 一致）。
- 若此前已手动跑过 `myblog/migrate_visit_log_bot.py`，自愈为空操作，安全无副作用。

### 验证
- `smoke_v380.py` 18/18 全过（无回归）；`py_compile` 通过。
- 本地 `visit_log` 经自愈补齐三列，后台统计页（`/admin/stats`）、反爬看板（`/admin/bot-guard`）、设置页均渲染正常。
- 打包校验：后端 zip 含 `myblog/bot_guard.py`、`_migrate_visit_log_table` 已在 `app.py` 内、不含 `data/`、内嵌 `APP_VERSION = 3.8.1`。"""

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
