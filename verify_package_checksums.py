#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地校验脚本：验证 package.py 生成的「双源互证」SHA256 口径正确。

双源互证设计（见 package.py / ROADMAP 第 26~27 节）：
  - ① sha256.txt 记「完整文件哈希」（含 zip 注释），update.sh 用标准 sha256sum 比对；
  - ② zip 注释内嵌「内容区哈希」：内容区 = 剥离尾注释后的字节，update.sh ② 重算比对。

内容区精确口径（关键，极易写错）：
  EOCD 签名 PK\x05\x06 在 idx；EOCD 固定 22 字节，comment_length 字段在 idx+20，
  注释在 idx+22 起。内容区 = data[:idx + 20] —— **连 comment_length 的 2 字节也要排除**，
  绝不能写成 data[:len(文件) - comment_len]（那样会多算这 2 字节，哈希恒失配，
  把"包被篡改"误判成"包正常"）。本脚本的 content_region() 严格对齐
  package.py::_strip_zip_comment()。

三件事：
  1. 对每个 zip 用精确口径重算内容区 SHA256，与注释内嵌 SHA256= 比对（双源互证 ②）；
  2. 对 sha256.txt 的整文件哈希用标准 sha256sum 重算比对（双源互证 ①）；
  3. --self-test 构造带注释的 zip，演示「精确口径 != 错误口径」，固化踩坑教训。

全部通过输出 OK；任一失败输出 FAIL 并以退出码 1 结束。脚本只读、不发布、不篡改任何文件。
"""
import hashlib
import io
import os
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def content_region(data):
    """内容区字节：严格对齐 package.py::_strip_zip_comment。"""
    idx = data.rfind(b"\x50\x4b\x05\x06")
    if idx < 0:
        raise ValueError("不是合法 zip（找不到 EOCD 签名）")
    return data[:idx + 20]            # 截到 idx+20：EOCD 签名(4)+固定字段(16)，
                                      # 注释长度字段(2B)与注释(comment)整体排除


def content_sha256(data):
    return hashlib.sha256(content_region(data)).hexdigest()


def full_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def comment_sha256(path):
    """读取注释内嵌 SHA256= 值（小写）；无注释/无 SHA256= 返回 None。"""
    with open(path, "rb") as f:
        data = f.read()
    idx = data.rfind(b"\x50\x4b\x05\x06")
    if idx < 0:
        return None
    clen = int.from_bytes(data[idx + 20:idx + 22], "little")
    if clen <= 0:
        return None
    comment = data[idx + 22:idx + 22 + clen].decode("utf-8", "replace")
    for ln in comment.splitlines():
        ln = ln.strip()
        if ln.startswith("SHA256="):
            return ln[7:].strip().lower()
    return None


def _wrong_content_sha256(data):
    """错误口径演示：data[:文件长度 - comment_len]，会多算 comment_length 的 2 字节。"""
    idx = data.rfind(b"\x50\x4b\x05\x06")
    clen = int.from_bytes(data[idx + 20:idx + 22], "little")
    return hashlib.sha256(data[:len(data) - clen]).hexdigest()


def verify_zip(path):
    with open(path, "rb") as f:
        data = f.read()
    content = content_sha256(data)
    embedded = comment_sha256(path)
    if embedded is None:
        return False, "zip 无内嵌 SHA256 注释（未跑 package.py 或注释写入失败）"
    if content != embedded:
        return False, "内容区哈希(%s) != 注释内嵌(%s)" % (content[:12], embedded[:12])
    # 口径自检：若精确口径竟等于错误口径，说明没真正排除那 2 字节
    if _wrong_content_sha256(data) == content:
        return False, "内容区口径 == 错误口径（未排除 comment_length 的 2 字节）"
    return True, "内容区 %s == 注释内嵌 %s（双源互证 ② 成立）" % (content[:12], embedded[:12])


def verify_checksums_txt():
    txt = os.path.join(ROOT, "sha256.txt")
    if not os.path.isfile(txt):
        return False, "sha256.txt 不存在（先跑 package.py）"
    lines = [l for l in open(txt, encoding="utf-8").read().splitlines()
             if l.strip() and not l.startswith("HMAC")]
    if not lines:
        return False, "sha256.txt 无校验行"
    for ln in lines:
        parts = ln.split(None, 1)
        if len(parts) != 2:
            continue
        expect, name = parts
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            return False, "sha256.txt 引用 %s 但文件不存在" % name
        if full_sha256(p).lower() != expect.lower():
            return False, "%s 整文件哈希失配（双源互证 ① 失败）" % name
    return True, "sha256.txt 全部整文件哈希一致（双源互证 ① 成立）"


def self_test():
    """构造带注释的 zip，证明「精确口径 != 错误口径」，固化踩坑教训。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.txt", "hello world")
    data = bytearray(buf.getvalue())
    comment = b"SHA256=deadbeef"
    idx = data.rfind(b"\x50\x4b\x05\x06")
    # 对齐 _embed_zip_comment：data[:idx+20] + 新 comment_length + 新注释
    data = data[:idx + 20] + len(comment).to_bytes(2, "little") + comment

    fd, p = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with open(p, "wb") as f:
            f.write(data)
        content = content_sha256(bytes(data))
        wrong = _wrong_content_sha256(bytes(data))
        embedded = comment_sha256(p)
        assert embedded == "deadbeef", "注释读取应为 deadbeef，实际 %r" % embedded
        assert content != wrong, "精确口径不应等于错误口径（说明口径写错）"
        # 证明：用错误口径重算的哈希 ≠ 注释内嵌值（否则会误判篡改）
        assert wrong != embedded, "错误口径竟等于注释内嵌，双源互证将失效"
        print("self-test OK：")
        print("  精确口径内容区哈希 = %s" % content)
        print("  错误口径内容区哈希 = %s  (≠ 精确口径，证明未排除 comment_length 的 2 字节会恒失配)" % wrong)
        print("  注释内嵌值读取     = %s (与写入一致，读取逻辑正确；此处是占位符非真实哈希)" % embedded)
        print("  结论：update.sh ② 必须用「精确口径 data[:EOCD+20]」重算，否则双源互证失效")
    finally:
        os.remove(p)


def main():
    if "--self-test" in sys.argv:
        self_test()
        return
    targets = [os.path.join(ROOT, "myblog-backend.zip"),
               os.path.join(ROOT, "vue-frontend-dist.zip")]
    all_ok = True
    for p in targets:
        if not os.path.isfile(p):
            print("SKIP %s（未生成，先跑 package.py）" % os.path.basename(p))
            continue
        ok, msg = verify_zip(p)
        print(("OK   " if ok else "FAIL ") + os.path.basename(p) + "：" + msg)
        all_ok = all_ok and ok
    ok, msg = verify_checksums_txt()
    print(("OK   " if ok else "FAIL ") + "sha256.txt" + "：" + msg)
    all_ok = all_ok and ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
