#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llhhy-blog v3.8.5 Release 创建脚本
无网络依赖本地创建 Release 并上传资产（适用于 PAT 权限不全或 API 临时不可用场景）
"""

import os
import re
import zipfile
import json
from datetime import datetime

def make_release():
    print(f"[INFO] 构建 llhhy-blog v3.8.5 Release 本地脚本")
    print(f"[INFO] 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查资产文件
    assets = ["myblog-backend.zip", "vue-frontend-dist.zip", "sha256.txt"]
    for asset in assets:
        if not os.path.exists(asset):
            print(f"[ERROR] 缺少资产文件: {asset}")
            return False
        print(f"[OK] 找到资产: {asset} ({os.path.getsize(asset)} bytes)")

    # 提取 commit hash
    with open(".git/HEAD", "r", encoding="utf-8") as f:
        head = f.read().strip()
    if head.startswith("ref: refs/heads/"):
        commit_file = os.path.join(".git", head[5:])
        with open(commit_file, "r", encoding="utf-8") as f:
            commit_hash = f.read().strip()
    else:
        commit_hash = head

    print(f"[INFO] 最新 commit: {commit_hash}")

    # 构建 Release 信息
    release_info = {
        "tag_name": "v3.8.5",
        "name": "llhhy-blog v3.8.5 - 新增 API 文档页面",
        "body": """## v3.8.5 新增 API 文档页面（懒方案）

### 🎯 主要改动
- **API 文档页面**：新增 `/docs` 路径，左侧导航 + 右侧内容 + 代码高亮（CDN highlight.js）
- **路由新增**：`router.js` 添加 `/docs` 路由，无需额外框架
- **版本升级**：APP_VERSION 升为 3.8.5，配套文档同步更新

### 📁 文件改动
- vue-frontend/src/router.js：新增 /docs 路由
- vue-frontend/src/views/DocsView.vue：API 文档页面
- myblog/config.py：APP_VERSION = "3.8.5"
- README.md/myblog/README.md/ROADMAP.md：文档同步更新

### 🔍 技术实现
- **懒方案**：复用现有 Vue 前端，新增 DocsView.vue 页面
- **无额外框架**：不使用 VitePress/Docusaurus，仅用 Vue + CDN highlight.js
- **响应式设计**：移动端侧边栏自动折叠
- **代码高亮**：CDN 加载 highlight.js，支持多语言语法高亮

### 🧪 部署测试
1. 宝塔「停止 → 启动」gunicorn（**必须停止再启动**）
2. 访问 http://your-domain.com/docs 查看文档页
3. Ctrl+F 可搜索接口文档内容

### 🔗 链接
- 在线预览：https://github.com/Llhhy1/llhhy-blog/releases/tag/v3.8.5
- 项目主页：https://github.com/Llhhy1/llhhy-blog

---

> 🚀 发布时间：2026-08-26  
> 📦 commit：{commit_hash}  
> ⚖️ 开源协议：MIT License  
> 👤 作者：Llhhy1  
""".format(commit_hash=commit_hash[:7]),

        "draft": False,
        "prerelease": False,
        "target_commitish": "main"
    }

    # 保存 release 信息文件（用于人工创建）
    release_file = "v3.8.5_release_info.json"
    with open(release_file, "w", encoding="utf-8") as f:
        json.dump(release_info, f, ensure_ascii=False, indent=2)
    print(f"[OK] Release 信息已保存到: {release_file}")

    # 显示资产清单
    print("\n[资产清单]")
    for asset in assets:
        size = os.path.getsize(asset)
        print(f"  • {asset} ({size} bytes)")

    print(f"\n[完成] Release 信息已准备就绪")
    print(f"[提示] 请手动访问 https://github.com/Llhhy1/llhhy-blog/releases/new")
    print(f"[提示] 上传三个资产文件并粘贴 Release 信息")

if __name__ == "__main__":
    make_release()