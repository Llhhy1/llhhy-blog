#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键发布 GitHub Release（v3.9.1）。

用法：
    set GH_TOKEN=ghp_xxx          (Windows)  /  export GH_TOKEN=ghp_xxx   (bash)
    python create_github_release.py

说明：
    - token 只从环境变量 GH_TOKEN 读取，绝不写入聊天 / 不落盘 / 不进 git。
    - Release 创建走 api.github.com，资产上传走 uploads.github.com（两个域名必须分开）。
    - 资产：myblog-backend.zip / vue-frontend-dist.zip / sha256.txt
"""
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse

REPO = "Llhhy1/llhhy-blog"
TAG = "v3.9.1"
TITLE = "llhhy-blog v3.9.1 - 正文渲染缓存 + SQLite WAL"
NOTES_FILE = "_release_notes_v3.9.1.md"
ASSETS = ["myblog-backend.zip", "vue-frontend-dist.zip", "sha256.txt"]

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"

UA = {"User-Agent": "llhhy-blog-release-script"}


def req(method, url, token, data=None, headers=None, raw=False):
    h = dict(UA)
    h["Accept"] = "application/vnd.github+json"
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        else:
            body = data
    r = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        return e.code, err


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.stderr.write("错误：未找到环境变量 GH_TOKEN。\n请先设置：set GH_TOKEN=ghp_xxx  （或 export GH_TOKEN=ghp_xxx）\n")
        sys.exit(1)

    # 1) 读发布说明
    try:
        notes = open(NOTES_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        sys.stderr.write("错误：找不到 %s\n" % NOTES_FILE)
        sys.exit(1)

    # 2) 校验资产存在
    missing = [a for a in ASSETS if not os.path.isfile(a)]
    if missing:
        sys.stderr.write("错误：以下资产不存在：%s\n" % ", ".join(missing))
        sys.exit(1)

    # 3) 创建 Release
    print("→ 创建 Release %s ..." % TAG)
    status, resp = req("POST", API + "/repos/%s/releases" % REPO, token, {
        "tag_name": TAG,
        "name": TITLE,
        "body": notes,
        "draft": False,
        "prerelease": False,
    })
    if status < 200 or status >= 300:
        sys.stderr.write("创建 Release 失败（HTTP %d）：\n%s\n" % (status, resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)))
        sys.exit(1)

    rel_id = resp.get("id")
    if not rel_id:
        sys.stderr.write("创建 Release 成功但未返回 id：%s\n" % json.dumps(resp, ensure_ascii=False))
        sys.exit(1)
    print("  ✓ Release 已创建 (id=%s)" % rel_id)

    # 4) 上传资产（走 uploads.github.com）
    for a in ASSETS:
        print("→ 上传资产 %s ..." % a)
        with open(a, "rb") as f:
            data = f.read()
        url = UPLOAD + "/repos/%s/releases/%s/assets?name=%s" % (
            REPO, rel_id, urllib.parse.quote(a)
        )
        st, body = req("POST", url, token, data=data,
                       headers={"Content-Type": "application/octet-stream"}, raw=True)
        if st < 200 or st >= 300:
            sys.stderr.write("  上传 %s 失败（HTTP %d）：%s\n" % (a, st, body.decode("utf-8", "replace")[:500]))
            sys.exit(1)
        print("  ✓ %s 上传成功" % a)

    print("\n✅ 完成：https://github.com/%s/releases/tag/%s" % (REPO, TAG))


if __name__ == "__main__":
    main()
