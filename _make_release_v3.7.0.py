#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3.7.0 发布脚本（PAT 直发，无 gh CLI 兜底）。

Token 通过环境变量 GH_TOKEN 注入（不硬编码、不打印到日志）。
创建 Release 并上传资产——资产上传**必须走 uploads.github.com 域名**
（用 api.github.com 传资产会 404，已踩坑）。
"""
import os
import sys
import json
import urllib.request
import urllib.error

REPO = "Llhhy1/llhhy-blog"
TAG = "v3.7.0"
VERSION = "3.7.0"
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

NOTES = """## llhhy-blog v3.7.0 · 链接后缀（slug）强制全局设置

### 功能变更
- **取消单篇手动覆盖**：编辑/新建文章页移除「链接后缀」输入框，slug 一律由后台「🔗 链接后缀规则」全局设置（`slug_mode`/`slug_template`）强制生成，作者不再能单篇手写覆盖。
- **保留原则**：编辑已有文章时仅标题变化才按全局模板重建 slug；标题未变则保持原 slug 不动，避免悄悄改掉旧 URL 造成外链/SEO 失效。
- 后台全局设置页（预制模板 / 自定义占位符）保持不变，仍是唯一定义 slug 形态的地方。
- 后端删除已无调用方的 `clean_slug()` 死代码；前端草稿自动保存字段移除 `slug`。

### 安全审计（R37）
- 七维审计 **0 Blocker，0 高危**。本轮为行为收敛，攻击面不增反减（移除一处用户输入入口）；无 DB schema 变更（`blog.db` 无需迁移）。详见 `myblog/SECURITY_AUDIT.md` 第四十七轮。

### 部署注意
- **无数据库迁移**、**无前端构建改动**（前端沿用 `_vite_build16`）。
- 覆盖后端后须在宝塔「停止 → 启动」gunicorn 方真正重载（restart 不重载）。
- 升级后后台左下角版本号显示 `v3.7.0`。
- 资产：`myblog-backend.zip` + `vue-frontend-dist.zip` + `sha256.txt`（含双源互证校验：整文件哈希 + zip 注释内嵌内容区哈希）。
"""

ASSETS = ["myblog-backend.zip", "vue-frontend-dist.zip", "sha256.txt"]


def req(method, url, headers, data=None):
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GH_TOKEN 未设置")
    auth = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "llhhy-blog-release",
        "Content-Type": "application/json",
    }
    # 1. 创建 Release
    payload = json.dumps({
        "tag_name": TAG,
        "name": "v%s" % VERSION,
        "body": NOTES,
        "draft": False,
        "prerelease": False,
    }, ensure_ascii=False).encode("utf-8")
    code, body = req("POST", API + "/repos/%s/releases" % REPO, auth, payload)
    if code not in (200, 201):
        sys.exit("创建 Release 失败 %s: %s" % (code, body[:800]))
    rid = json.loads(body)["id"]
    print("Release 已创建 id=%s" % rid)
    # 2. 上传资产（uploads.github.com 域名）
    for name in ASSETS:
        if not os.path.isfile(name):
            print("跳过缺失资产:", name)
            continue
        with open(name, "rb") as f:
            data = f.read()
        hdr = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "llhhy-blog-release",
            "Content-Type": "application/octet-stream",
        }
        u = UPLOADS + "/repos/%s/releases/%s/assets?name=%s" % (REPO, rid, name)
        c, b = req("POST", u, hdr, data)
        if c not in (200, 201):
            sys.exit("上传 %s 失败 %s: %s" % (name, c, b[:800]))
        print("已上传资产:", name)
    print("全部资产上传完成。")


if __name__ == "__main__":
    main()
