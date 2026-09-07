"""游戏包安全处理（v3.15.0，纯逻辑、无 Flask 依赖，便于单测）。

职责：
1) zip 安全解包：拒绝目录穿越 / 绝对路径 / 超限大小 / 超限文件数 / 非法扩展名。
2) manifest.json 解析与校验：name/title/entry 等字段白名单。
3) 静态可疑扫描：对每个文本文件做启发式特征匹配，产出「规则级」发现列表 + 0-100 评分。

安全边界说明（配合沙箱托管 /game-files/… 的响应头 CSP sandbox 一起生效）：
- 这里的扫描是「辅助防线」不是「绝对保证」：纯客户端 JS 无法 100% 静态判定恶意。
- 真正的隔离在浏览器侧：iframe sandbox（无 allow-same-origin）+ CSP + nosniff + 独立资源路径。
"""
import io
import os
import re
import zipfile

MAX_ZIP_BYTES = 20 * 1024 * 1024      # 上传 zip 上限 20MB
MAX_TOTAL_BYTES = 60 * 1024 * 1024    # 解压后总字节上限 60MB
MAX_FILES = 200                       # 文件数上限

# 允许的素材/代码扩展名（一律白名单；可执行文件/服务器脚本一律拒绝）
ALLOWED_EXT = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".ico", ".mp3", ".ogg", ".wav", ".mp4", ".webm",
    ".ttf", ".woff", ".woff2", ".txt", ".md",
}
# 文本类扩展名（需要做可疑扫描）
TEXT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".md"}

# ---- zip 安全解包 ----

def _norm_member(path):
    """规范化 zip 内路径，检测穿越。返回 (ok, safe_relpath)。"""
    p = path.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return False, ""
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            return False, ""
        parts.append(seg)
    if not parts:
        return False, ""
    return True, "/".join(parts)


def unpack_zip_safely(zip_bytes, max_zip=MAX_ZIP_BYTES, max_total=MAX_TOTAL_BYTES,
                      max_files=MAX_FILES):
    """校验并解包 zip → [{name, data}]。任一越界抛 ValueError。

    通过检查才会进入磁盘/入库；调用方不直接 trust zip。
    """
    if not zip_bytes or len(zip_bytes) > max_zip:
        raise ValueError("游戏包为空或超过大小上限")
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError("不是合法的 zip 文件") from e
    out, total = [], 0
    infos = zf.infolist()
    if len(infos) > max_files:
        raise ValueError(f"游戏包文件数超过上限 {max_files}")
    for info in infos:
        ok, rel = _norm_member(info.filename)
        if not ok:
            raise ValueError(f"包含非法路径：{info.filename!r}")
        if info.is_dir():
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext not in ALLOWED_EXT:
            raise ValueError(f"含不允许的文件类型：{rel}")
        data = zf.read(info)
        total += len(data)
        if total > max_total:
            raise ValueError("解压后总大小超过上限")
        out.append({"name": rel, "data": data})
    return out


# ---- manifest 解析 ----

def find_manifest(files):
    """从解包结果里找 manifest.json 并解析。找不到/非法返回 None。"""
    blob = None
    for f in files:
        if f["name"].lower() == "manifest.json":
            blob = f["data"]
            break
    if blob is None:
        return None
    import json
    try:
        m = json.loads(blob.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(m, dict):
        return None
    return m


def validate_manifest(m):
    """校验 manifest 必备字段与入口合法性，返回 (ok, errors)。"""
    if not isinstance(m, dict):
        return False, ["manifest 不是 JSON 对象"]
    errs = []
    if not (m.get("name") or "").strip():
        errs.append("缺少 name")
    if not (m.get("entry") or "").strip():
        errs.append("缺少 entry")
    else:
        entry = m["entry"].strip()
        if not re.match(r"^[A-Za-z0-9_./-]+\.(html?)$", entry):
            errs.append("entry 必须是指向 html 的相对路径")
        if ".." in entry.split("/"):
            errs.append("entry 路径不允许 ..")
    if len(errs):
        return False, errs
    return True, []


# ---- 静态可疑扫描 ----

# (规则名, 匹配正则, 级别, 说明)
SCAN_RULES = [
    ("remote_script", re.compile(r"<script[^>]+src\s*=\s*['\"]https?://", re.I),
     "warn", "外链远程脚本（供应链风险）"),
    ("http_links", re.compile(r"(?:src|href)\s*=\s*['\"]http://", re.I),
     "warn", "明文 http 资源会被 CSP/混合内容拦截"),
    ("eval_ctor", re.compile(r"\beval\s*\(|new\s+Function\s*\("),
     "warn", "eval/new Function 动态执行"),
    ("obfuscated", re.compile(r"document\.write\s*\(|atob\s*\(|(?:^|\n)\s*\w+=\s*String\.fromCharCode"),
     "warn", "疑似混淆/动态解码"),
    ("cookie_read", re.compile(r"document\.cookie"),
     "warn", "读取 cookie（沙箱内无效，仍提示）"),
    ("exfil_fetch", re.compile(r"fetch\s*\(\s*['\"`](?:https?:)?//"),
     "warn", "向绝对地址发请求（外传数据风险）"),
    ("websocket", re.compile(r"new\s+WebSocket\s*\("),
     "warn", "WebSocket 外连"),
    ("base64_large", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"),
     "warn", "超长疑似 base64 载荷"),
    ("localstorage", re.compile(r"localStorage|sessionStorage"),
     "info", "使用本地存储（沙箱内可能受限）"),
    ("parent_access", re.compile(r"parent\.|window\.parent|top\."),
     "warn", "尝试访问父窗口（沙箱会阻止）"),
    ("topnav", re.compile(r"window\.open\s*\(|location\.(?:href|replace)\s*="),
     "info", "尝试跳转/开窗（将被沙箱 CSP 限制）"),
]


def scan_game_files(files):
    """扫描解包结果，返回 (findings, score)。

    findings: [{rule, file, level, note}]；score 0-100，100=未见可疑。
    """
    findings = []
    for f in files:
        if os.path.splitext(f["name"])[1].lower() not in TEXT_EXT:
            continue
        try:
            text = f["data"].decode("utf-8", errors="ignore")
        except Exception:
            continue
        for rule, rx, level, note in SCAN_RULES:
            if rx.search(text):
                findings.append({
                    "rule": rule, "file": f["name"][:120], "level": level, "note": note,
                })
    # 评分：warn 每条约 -6，info 每条约 -1，下限 0
    warn_n = sum(1 for x in findings if x["level"] == "warn")
    info_n = sum(1 for x in findings if x["level"] == "info")
    score = max(0, 100 - warn_n * 6 - info_n)
    return findings, score
