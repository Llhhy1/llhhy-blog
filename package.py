#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llhhy-blog 发布打包脚本。

生成两个 zip（与 update.sh 约定一致）：
  - myblog-backend.zip : 顶层为 myblog/ ，排除 data/ 与 __pycache__/*.pyc
  - vue-frontend-dist.zip : 顶层为 index.html + assets/ + favicon.svg （即前端构建产物）

用法：
  python package.py                 # 默认读取 vue-frontend/_vite_buildN（最新），回退 dist/
  python package.py --front-dir vue-frontend/_vite_build9

校验：
  - 后端 zip 必须含 myblog/config.py 且 APP_VERSION 与目标一致
  - 后端 zip 不得含 data/ 目录
  - 前端 zip 顶层必须含 index.html 与 assets/
"""
import os
import re
import sys
import hashlib
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_SRC = os.path.join(ROOT, "myblog")
FRONT_BASE = os.path.join(ROOT, "vue-frontend")

# 后端打包排除项
EXCLUDE_DIRS = {"data", "__pycache__", ".git", "node_modules"}
EXCLUDE_SUFFIXES = (".pyc",)


def expected_version():
    cfg = os.path.join(BACKEND_SRC, "config.py")
    with open(cfg, "r", encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', txt)
    return m.group(1) if m else None


def add_tree(zf, base_dir, arc_root, exclude_dirs, exclude_suffixes):
    """递归把 base_dir 加入 zf，arcname 以 arc_root 开头。"""
    for dirpath, dirnames, filenames in os.walk(base_dir):
        # 过滤目录
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fn in filenames:
            if fn.endswith(exclude_suffixes):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, base_dir)
            arcname = os.path.join(arc_root, rel).replace("\\", "/")
            zf.write(full, arcname)


def find_front_dir(explicit=None):
    if explicit:
        p = os.path.join(ROOT, explicit) if not os.path.isabs(explicit) else explicit
        if os.path.isdir(p):
            return p
        raise SystemExit("指定前端目录不存在: " + explicit)
    # 优先级：最新 dist*（含 dist_vXXX，规避本地删除保护用非 dist 名）> 最新 _vite_buildN > dist
    dist_like = []
    numbered = []
    for name in os.listdir(FRONT_BASE):
        full = os.path.join(FRONT_BASE, name)
        if not os.path.isdir(full):
            continue
        if re.match(r"^dist", name):  # dist / dist_v311 / dist_v312 ...
            dist_like.append((os.path.getmtime(full), name))
        elif re.match(r"^_vite_build\d+$", name):
            numbered.append(name)
    if dist_like:
        # 取修改时间最新的 dist* 目录（正式产物名，优先）
        dist_like.sort(key=lambda t: t[0], reverse=True)
        return os.path.join(FRONT_BASE, dist_like[0][1])
    if numbered:
        numbered.sort(key=lambda s: int(re.search(r"\d+", s).group()))
        return os.path.join(FRONT_BASE, numbered[-1])
    raise SystemExit("未找到前端构建目录（请先 npm run build 或指定 --front-dir）")


def package_backend(version):
    out = os.path.join(ROOT, "myblog-backend.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        add_tree(zf, BACKEND_SRC, "myblog", EXCLUDE_DIRS, EXCLUDE_SUFFIXES)
    # 校验
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert any(n == "myblog/config.py" for n in names), "缺少 myblog/config.py"
        assert not any(n.startswith("myblog/data/") for n in names), "不应包含 myblog/data/"
        cfg = zf.read("myblog/config.py").decode("utf-8")
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', cfg)
        assert m and m.group(1) == version, (
            "zip 内 APP_VERSION=%s 与目标 %s 不一致" % (m.group(1) if m else None, version)
        )
    size = os.path.getsize(out)
    print("  [backend] %s (%d bytes, %d entries)" % (out, size, len(names)))
    return out


def package_frontend(front_dir):
    out = os.path.join(ROOT, "vue-frontend-dist.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(front_dir):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, front_dir)
                arcname = rel.replace("\\", "/")
                zf.write(full, arcname)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "index.html" in names, "前端 zip 缺少 index.html"
        assert any(n.startswith("assets/") for n in names), "前端 zip 缺少 assets/"
    size = os.path.getsize(out)
    print("  [frontend] %s (%d bytes, %d entries, src=%s)"
          % (out, size, len(names), os.path.basename(front_dir)))
    return out


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(files):
    """生成 sha256.txt（每行：哈希 文件名），供 update.sh 校验完整性防篡改。"""
    out = os.path.join(ROOT, "sha256.txt")
    with open(out, "w", encoding="utf-8") as f:
        for p in files:
            f.write("%s  %s\n" % (sha256_of(p), os.path.basename(p)))
    print("  [checksum] %s" % out)
    return out


def main():
    explicit = None
    if "--front-dir" in sys.argv:
        i = sys.argv.index("--front-dir")
        explicit = sys.argv[i + 1]
    version = expected_version()
    if not version:
        raise SystemExit("无法从 config.py 解析 APP_VERSION")
    print("目标版本: v%s" % version)
    print("打包后端 ...")
    backend = package_backend(version)
    print("打包前端 ...")
    frontend = package_frontend(find_front_dir(explicit))
    print("生成校验文件 ...")
    write_checksums([backend, frontend])
    print("完成。两个 zip + sha256.txt 已生成在项目根目录（已被 .gitignore 忽略）。")


if __name__ == "__main__":
    main()
