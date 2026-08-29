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
EXCLUDE_DIRS = {"data", "__pycache__", ".git", "node_modules", "instance"}
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
    """完整文件哈希（含 zip 注释）。update.sh ① 用标准 sha256sum 对全文件比对。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_zip_comment(data):
    """定位 EOCD 并剥离尾注释，返回「内容区」字节（EOCD 注释长度字段清零）。

    内容区 = zip 除去尾注释后的全部字节。写入/修改注释只改变注释区，
    内容区保持不变，因此「内容区哈希」在写注释前后恒定——这是双源互证
    能成立的关键（若对含注释的整文件算哈希，注释本身参与文件字节，
    「注释里的哈希 == 整文件哈希」就成了必须破解 SHA256 的自指循环）。
    """
    idx = data.rfind(b"\x50\x4b\x05\x06")
    if idx < 0:
        return data
    # EOCD 固定 22 字节：签名(4) ... comment_length(2B, 偏移 20) comment
    # 截到 idx+20 即把注释长度字段与注释整体去掉
    return data[:idx + 20]


def sha256_of_content(path):
    """内容区哈希（剥离 zip 注释）。zip 注释内嵌的 SHA256 与之对应。"""
    with open(path, "rb") as f:
        data = f.read()
    h = hashlib.sha256()
    h.update(_strip_zip_comment(data))
    return h.hexdigest()


def write_checksums(files):
    """生成 sha256.txt（每行：哈希 文件名），供 update.sh 校验完整性防篡改。

    v3.1.6 增强（双源互证，防「sha256.txt 自身被篡改」）：
    1. ZIP 注释内嵌「内容区哈希」：把每个 zip 剥离尾注释后的内容区 SHA256 写进
       该 zip 的 ZIP comment（规范原生字段）。内容区在写注释前后恒定，因此
       「注释里的哈希 == 内容区实际哈希」始终成立。
       update.sh ② 用 python3 剥离注释后重新计算内容区哈希比对——
       单独篡改包内容或单独篡改注释都会导致不一致。
    2. sha256.txt 记录「完整文件哈希」（含注释），update.sh ① 用标准 sha256sum
       比对——整体替换包或 sha256.txt 都会导致不一致。两层互相独立、互证。
    3. sha256.txt 全文 HMAC 签名：用环境变量 UPDATE_HMAC_KEY 对 sha256.txt 内容做
       HMAC-SHA256，签名以 "HMAC <hex>" 首行写入 sha256.txt。配置了该密钥的服务器
       在 update.sh 里强制校验，未配置则跳过（向后兼容）。密钥属于部署侧机密，
       不在 Release 包内。
    """
    hashes = {}
    for p in files:
        # 先取内容区哈希（写注释前），写入注释后内容区不变，注释哈希恒可与内容区对上；
        # 再对含注释的整文件算哈希，写入 sha256.txt（update.sh ① 用 sha256sum 全文件比对）。
        content_hash = sha256_of_content(p)
        _embed_zip_comment(p, content_hash)
        h = sha256_of(p)
        hashes[os.path.basename(p)] = h
    out = os.path.join(ROOT, "sha256.txt")
    lines = []
    hmac_key = os.environ.get("UPDATE_HMAC_KEY", "")
    if hmac_key:
        lines.append("HMAC " + _hmac_hex(hmac_key, _checksum_body(hashes)))
    for name in sorted(hashes):
        lines.append("%s  %s" % (hashes[name], name))
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("  [checksum] %s" % out)
    return out


def _checksum_body(hashes):
    """sha256.txt 除 HMAC 首行外的正文（update.sh 用它重算签名）。"""
    return "\n".join("%s  %s" % (hashes[n], n) for n in sorted(hashes)) + "\n"


def _hmac_hex(key, body):
    import hmac as _hmac
    import hashlib as _hl
    return _hmac.new(key.encode("utf-8"), body.encode("utf-8"), _hl.sha256).hexdigest()


def _embed_zip_comment(path, sha256_hex):
    """把哈希写入 zip 注释（ZIP comment，随 zip 一起分发，非独立文件）。
    注释格式：开头保留原注释（若有），末尾追加 "SHA256=<hex>"。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        # 定位 EOCD（End of Central Directory）：从文件尾往前找 \x50\x4b\x05\x06
        idx = data.rfind(b"\x50\x4b\x05\x06")
        if idx < 0:
            return
        # EOCD 结构：... comment_length(2B) comment ... 其中 comment_length 在 idx+20 处
        clen = int.from_bytes(data[idx + 20:idx + 22], "little")
        old_comment = data[idx + 22:idx + 22 + clen].decode("utf-8", "replace") if clen else ""
        # 保留旧注释（去掉可能已存在的旧 SHA256 行）
        kept = "\n".join(
            ln for ln in old_comment.splitlines() if not ln.startswith("SHA256=")
        ).strip()
        new_comment = (kept + "\nSHA256=" + sha256_hex).strip()
        cb = new_comment.encode("utf-8")
        # 注意：EOCD 固定 22 字节，注释长度字段位于签名后偏移 20 处。
        # 正确做法：截到签名 + 20（不含旧注释长度字段），再写新长度 + 新注释。
        # 之前写 data[:idx+22] 会保留旧的注释长度字段，导致 zip 工具读不到注释（Bug）。
        body = data[:idx + 20] + len(cb).to_bytes(2, "little") + cb
        with open(path, "wb") as f:
            f.write(body)
    except Exception as e:
        print("  [checksum] 警告：zip 注释内嵌失败（不影响主流程）:", e)


def verify_zip_comment(path, expected_hex):
    """读取 zip 注释里的 SHA256 并比对「内容区实际哈希」（剥离注释后重算）。
    返回 True/False；无注释或格式异常返回 False。
    注意：expected_hex 必须是内容区哈希（sha256_of_content），不是整文件哈希。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        idx = data.rfind(b"\x50\x4b\x05\x06")
        if idx < 0:
            return False
        clen = int.from_bytes(data[idx + 20:idx + 22], "little")
        if clen <= 0:
            return False
        comment = data[idx + 22:idx + 22 + clen].decode("utf-8", "replace")
        for ln in comment.splitlines():
            ln = ln.strip()
            if ln.startswith("SHA256="):
                want = ln[7:].strip().lower()
                # 用「内容区」重新计算实际哈希（剥离注释），与注释里的值比对
                h = hashlib.sha256()
                h.update(_strip_zip_comment(data))
                return h.hexdigest() == want == (expected_hex or "").lower()
        return False
    except Exception:
        return False


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
