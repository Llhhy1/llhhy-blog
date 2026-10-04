"""数据备份与异地容灾（v3.3.0）。

可插拔后端，每个目的地通过环境变量独立开关；未配置则自动跳过，且任何异常
都只记录不影响主流程（避免备份脚本把发文章/站点主干带崩）：

  - local  : 本地滚动保留（默认开，BACKUP_DIR / BACKUP_RETENTION_DAYS）
  - oss    : 对象存储（阿里云 OSS / 腾讯云 COS / S3 兼容），需 boto3，未装则跳过
  - scp    : scp 到备用机（依赖系统 scp + SSH 互信或 BACKUP_SCP_KEY）
  - webdav : 网盘/云盘（坚果云 / Nextcloud / 群晖 Drive 等支持 WebDAV 的服务），依赖系统 curl

安全约定：
  - 密钥只走环境变量，绝不落库、不在任何接口回显。
  - 备份包内嵌 manifest.json（含每个文件的 SHA256），恢复前强制校验完整性。
  - manifest 内的路径仅允许落在 data/ 与 static/uploads/，拒绝任何 ".." 或绝对路径，
    防止被篡改的备份包借恢复做路径穿越写文件。
  - 恢复是高危操作：CLI 需显式 --yes；后台端点还需超管 + CSRF + 二次确认 + 写审计日志，
    且恢复前自动打一份"恢复前快照"。

用法（backup.sh 会调用 run）：
  python backup.py run                 # 执行一次完整备份（本地 + 已启用的远程）
  python backup.py list                # 列出本地备份
  python backup.py verify <path>       # 仅校验某备份包完整性
  python backup.py restore <path> --yes# 从指定备份恢复（--yes 强制确认）
"""
import os
import sys
import io
import json
import shutil
import zipfile
import hashlib
import datetime
import tempfile
import subprocess
import argparse
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

# 允许被备份/恢复落地的相对路径前缀（白名单，防路径穿越）
ALLOWED_PREFIXES = ("data/", "static/uploads/")

sys.path.insert(0, BASE_DIR)
try:
    from config import APP_VERSION, Config  # noqa
    _CFG = Config()
    _DEF_BACKUP_DIR = _CFG.BACKUP_DIR or os.path.join(
        os.path.dirname(BASE_DIR), "backups")
    _DEF_RETENTION = int(_CFG.BACKUP_RETENTION_DAYS or 14)
except Exception:  # pragma: no cover - 独立运行时也能跑
    APP_VERSION = "unknown"
    _DEF_BACKUP_DIR = os.path.join(os.path.dirname(BASE_DIR), "backups")
    _DEF_RETENTION = 14

# v3.4.0：合并「后台配置（Setting 表）+ 环境变量」，把最终值写入 os.environ，
# 使 sync_* 函数与 BACKUP_ROOT/RETENTION_DAYS 均读到后台配置。
_BS = None
try:
    import backup_settings as _BS
    _BS.apply_env()   # 后台配置优先（非密钥），环境变量兜底（密钥）
except Exception:
    pass  # 纯标准库兜底：import 失败不影响旧行为

BACKUP_ROOT = os.environ.get("BACKUP_DIR") or _DEF_BACKUP_DIR
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS") or _DEF_RETENTION)


def remote_status():
    """返回各远程后端是否已配置（供后台页显示状态卡；v3.4.0 起读合并配置）。"""
    def _db_set(k):
        try:
            return _BS.read_setting_db(k) if _BS else None
        except Exception:
            return None
    return {
        "local_dir": BACKUP_ROOT,
        "oss": bool(os.environ.get("BACKUP_OSS_BUCKET")),
        "scp": bool(os.environ.get("BACKUP_SCP_HOST")),
        "webdav": bool(os.environ.get("BACKUP_WEBDAV_URL")),
        # 配置来源标记（后台配置 vs 环境变量），供页面提示
        "oss_from_db": bool(_db_set("backup_oss_bucket")),
        "scp_from_db": bool(_db_set("backup_scp_host")),
        "webdav_from_db": bool(_db_set("backup_webdav_url")),
    }


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _now():
    return datetime.datetime.now()


def _safe_rel(rel):
    """校验相对路径安全：拒绝 '..'、绝对路径、以及白名单之外的前缀。"""
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or ".." in rel.split("/"):
        return False
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in ALLOWED_PREFIXES)


def snapshot_db(src_path, dst_path):
    """生成 SQLite 一致性快照（v3.9.1，WAL 安全）。

    v3.9.1 起数据库启用 WAL：主库 blog.db 里可能还缺一批「已提交但仍留在
    blog.db-wal 中、尚未 checkpoint」的数据。直接 cp 主库会得到一个陈旧且不完整的
    快照（极端情况下打开即报 database disk image is malformed）。

    这里改用 sqlite3 的在线备份 API（Connection.backup），它会读取逻辑数据库内容
    （含 WAL 中已提交部分），产出一个自包含、可直接打开的普通 .db 文件。
    失败（非 SQLite 文件 / 库损坏 / 被独占锁）则回退到直接复制，保证备份不中断。
    """
    import sqlite3
    # 先确认源文件存在：sqlite3.connect 对不存在的路径会「新建一个空库」，
    # 那样会备份出一个空快照，比备份失败更糟。
    if not os.path.exists(src_path):
        return False
    try:
        src = sqlite3.connect(src_path)
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return True
    except Exception:
        try:
            shutil.copyfile(src_path, dst_path)
            return False
        except Exception:
            return False


def drop_wal_sidecars(db_path):
    """删除数据库旁边的 -wal / -shm 残留文件（v3.9.1）。

    恢复备份时若只覆盖 blog.db 而留下旧的 blog.db-wal，SQLite 启动时会拿旧 WAL
    去回放新库，轻则数据错乱、重则报 database disk image is malformed。
    覆盖写库后必须先清掉这两个伴随文件（服务停止状态下删除是安全的）。
    """
    removed = []
    for suffix in ("-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
                removed.append(suffix)
            except Exception:
                pass
    return removed


def make_db_snapshot(db_path):
    """把数据库导出为一致性快照文件，返回快照路径（不存在则返回 None）。

    调用方用完须调 cleanup_db_snapshot(path) 删除临时文件。
    """
    if not os.path.exists(db_path):
        return None
    tmp_dir = tempfile.mkdtemp(prefix="bkdb_")
    tmp_db = os.path.join(tmp_dir, "blog.db")
    try:
        snapshot_db(db_path, tmp_db)
    except Exception:
        pass
    if os.path.exists(tmp_db):
        return tmp_db
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass
    return None


def cleanup_db_snapshot(path):
    """删除 make_db_snapshot 产出的临时快照（含其临时目录）。"""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
        parent = os.path.dirname(path)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except Exception:
        pass


def create_backup():
    """打包 data/blog.db + static/uploads/* 为带 manifest 的 zip，存本地并同步远程。

    返回 (archive_path, manifest_dict)；任何远程同步失败只记录不影响本地落盘。
    """
    ts = _now().strftime("%Y%m%d_%H%M%S")
    arc_name = "blog_backup_%s.zip" % ts
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="bk_")
    try:
        arc_path = os.path.join(tmp_dir, arc_name)
        manifest = {
            "created_at": _now().isoformat(timespec="seconds"),
            "app_version": APP_VERSION,
            "files": [],
        }
        snap = None
        with zipfile.ZipFile(arc_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1) 数据库（v3.9.1：用一致性快照，避免 WAL 模式下 cp 到陈旧主库）
            db = os.path.join(DATA_DIR, "blog.db")
            snap = make_db_snapshot(db)
            if snap:
                rel = "data/blog.db"
                zf.write(snap, rel)
                manifest["files"].append(
                    {"path": rel, "sha256": _sha256_file(snap), "size": os.path.getsize(snap)})
            # 2) 上传目录（图片等）
            if os.path.isdir(UPLOAD_DIR):
                for dirpath, _dirnames, filenames in os.walk(UPLOAD_DIR):
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        rel = os.path.relpath(full, BASE_DIR).replace("\\", "/")
                        if not _safe_rel(rel):
                            continue
                        zf.write(full, rel)
                        manifest["files"].append(
                            {"path": rel, "sha256": _sha256_file(full),
                             "size": os.path.getsize(full)})
            manifest["file_count"] = len(manifest["files"])
            # 内嵌 manifest，使备份包自带完整性描述
            zf.writestr("manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=2))
        # 整包哈希（便于远程端独立校验）
        manifest["archive_sha256"] = _sha256_file(arc_path)
        # 落到备份根目录（archive + 独立 manifest 便于后台免解压读取）
        final_arc = os.path.join(BACKUP_ROOT, arc_name)
        final_man = os.path.join(BACKUP_ROOT, "manifest_%s.json" % ts)
        shutil.move(arc_path, final_arc)
        with open(final_man, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        # 同步已启用的远程后端
        sync_results = sync_remotes(final_arc, final_man)
        # 滚动清理
        prune_local()
        return final_arc, manifest, sync_results
    finally:
        cleanup_db_snapshot(snap)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run(cmd, timeout=300):
    """执行外部命令；失败抛异常由调用方捕获。

    安全约束（L6 修复）：严禁 shell=True，避免命令注入。cmd 必须为 list，
    若为 str 一律拒绝（TypeError），杜绝调用方误用字符串触发 shell 解析的陷阱。
    所有同步调用方（scp/curl/oss）均传 list，无兼容性影响。
    """
    if isinstance(cmd, str):
        raise TypeError(
            "_run 仅接受 list 形式的命令（禁止 shell=True，防命令注入），"
            "收到 str: %r" % cmd
        )
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)


def sync_oss(arc, man):
    """对象存储（S3 兼容：阿里云 OSS / 腾讯云 COS）。需 boto3，未装则跳过。"""
    try:
        import boto3  # noqa
    except ImportError:
        return ("oss", False, "未安装 boto3，已跳过（pip install boto3 后启用）")
    try:
        bucket = os.environ["BACKUP_OSS_BUCKET"]
        region = os.environ.get("BACKUP_OSS_REGION", "")
        endpoint = os.environ.get("BACKUP_OSS_ENDPOINT", "")
        key = os.environ.get("BACKUP_OSS_KEY", "")
        secret = os.environ.get("BACKUP_OSS_SECRET", "")
        client = boto3.client(
            "s3", aws_access_key_id=key or None,
            aws_secret_access_key=secret or None,
            endpoint_url=endpoint or None, region_name=region or None)
        base = os.environ.get("BACKUP_OSS_PREFIX", "backups").strip("/")
        for f in (arc, man):
            obj = "%s/%s" % (base, os.path.basename(f))
            client.upload_file(f, bucket, obj)
        return ("oss", True, "ok")
    except Exception as e:  # 远程失败不阻断本地
        return ("oss", False, str(e)[:200])


_SCP_TARGET_RE = re.compile(r"^(?:[A-Za-z0-9._%+-]{1,64}@)?[A-Za-z0-9.-]{1,253}$")


def _scp_target_ok(host):
    """scp 目标必须是 `[user@]host` 形态（允许 IP 与裸主机名）。

    这些值来自后台可编辑的 Setting 表（`backup_settings.apply_to_environ()` 把它们
    写回 os.environ），属于**跨信任边界输入**：以 `-` 开头会被 scp 当成选项，
    `-oProxyCommand=<命令>` 即以 gunicorn 进程身份执行任意命令。
    """
    if not host or host.startswith("-") or ".." in host:
        return False
    return bool(_SCP_TARGET_RE.match(host))


def _webdav_url_ok(url):
    """WebDAV 地址只允许 http/https，且不得以 `-` 开头（curl 选项注入）。

    `curl -T <文件> <url>` 在 url 为 `file://` 时是**任意本地路径写入**——把备份包
    （内含明文可猜测的 zip 结构）写到 cron / web 目录即可提权。gopher/file 同理。
    """
    if not url or url.startswith("-"):
        return False
    scheme = urlparse(url).scheme.lower()
    return scheme in ("http", "https")


def sync_scp(arc, man):
    """scp 到备用机。依赖系统 scp + SSH 互信或 BACKUP_SCP_KEY。"""
    try:
        host = os.environ["BACKUP_SCP_HOST"]          # user@host
        dest = os.environ.get("BACKUP_SCP_DIR", "~/blog_backups")
        port = os.environ.get("BACKUP_SCP_PORT", "22")
        key = os.environ.get("BACKUP_SCP_KEY", "")
        if not _scp_target_ok(host):
            return ("scp", False, "BACKUP_SCP_HOST 非法（只允许 [user@]host，不得以 - 开头）")
        if not str(port).isdigit() or not (1 <= int(port) <= 65535):
            return ("scp", False, "BACKUP_SCP_PORT 必须是 1-65535 的端口号")
        if key.startswith("-") or any(c in key for c in " \t\r\n"):
            return ("scp", False, "BACKUP_SCP_KEY 路径非法")
        opts = ["-P", str(port)]
        if key:
            opts += ["-i", key]
        for f in (arc, man):
            # `--` 结束选项解析：即便日后新增字段忘了校验，也不会退化成选项注入
            _run(["scp"] + opts + ["--", f, "%s:%s/" % (host, dest)], timeout=300)
        return ("scp", True, "ok")
    except Exception as e:
        return ("scp", False, str(e)[:200])


def sync_webdav(arc, man):
    """网盘/云盘（WebDAV 通用：坚果云 / Nextcloud / 群晖 Drive 等）。依赖系统 curl。"""
    try:
        url = os.environ["BACKUP_WEBDAV_URL"].rstrip("/")
        user = os.environ.get("BACKUP_WEBDAV_USER", "")
        pwd = os.environ.get("BACKUP_WEBDAV_PASS", "")
        if not _webdav_url_ok(url):
            return ("webdav", False, "BACKUP_WEBDAV_URL 非法（只允许 http/https，不得以 - 开头）")
        auth = ["-u", "%s:%s" % (user, pwd)] if user else []
        for f in (arc, man):
            _run(["curl", "-sS", "-f"] + auth + ["-T", f, "--",
                  "%s/%s" % (url, os.path.basename(f))], timeout=300)
        return ("webdav", True, "ok")
    except Exception as e:
        return ("webdav", False, str(e)[:200])


def sync_remotes(arc, man):
    results = []
    if os.environ.get("BACKUP_OSS_BUCKET"):
        results.append(sync_oss(arc, man))
    if os.environ.get("BACKUP_SCP_HOST"):
        results.append(sync_scp(arc, man))
    if os.environ.get("BACKUP_WEBDAV_URL"):
        results.append(sync_webdav(arc, man))
    return results


def prune_local():
    """滚动清理：删除超过 RETENTION_DAYS 天的本地备份（含配套 manifest）。"""
    if RETENTION_DAYS <= 0:
        return
    now = _now()
    for fn in os.listdir(BACKUP_ROOT):
        if not (fn.startswith("blog_backup_") and fn.endswith(".zip")):
            continue
        fp = os.path.join(BACKUP_ROOT, fn)
        try:
            age = (now - datetime.datetime.fromtimestamp(os.path.getmtime(fp))).days
            if age > RETENTION_DAYS:
                os.remove(fp)
                stem = fn[len("blog_backup_"):-len(".zip")]
                man = os.path.join(BACKUP_ROOT, "manifest_%s.json" % stem)
                if os.path.exists(man):
                    os.remove(man)
        except Exception:
            pass


# ---------- v3.17.13：概览统计工具（供后台「数据备份」页展示更全面的运维数据）----------
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")


def fmt_size(n):
    """人性化文件大小（B/KB/MB/GB/TB）——避免出现「51200 KB」这类不直观显示。"""
    try:
        val = float(n or 0)
    except (TypeError, ValueError):
        return "—"
    for unit in _SIZE_UNITS:
        if val < 1024 or unit == _SIZE_UNITS[-1]:
            return ("%.0f %s" % (val, unit)) if unit == "B" else ("%.1f %s" % (val, unit))
        val /= 1024.0
    return "%.1f TB" % val


def file_size(path):
    """单个文件大小（不存在/无权限返回 0）。"""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


_DIR_STAT_CACHE = {"ts": 0.0, "path": "", "size": 0, "count": 0}


def dir_stat(path, ttl=60):
    """目录总大小与文件数（带 TTL 缓存）。

    上传目录可能有上千文件，后台页每次打开都全量遍历会拖慢页面 → 缓存 60 秒。
    """
    import time as _time
    now = _time.time()
    if _DIR_STAT_CACHE["path"] == path and (now - _DIR_STAT_CACHE["ts"]) < ttl:
        return _DIR_STAT_CACHE["size"], _DIR_STAT_CACHE["count"]
    size = 0
    count = 0
    try:
        for root, _dirs, files in os.walk(path):
            for fn in files:
                try:
                    size += os.path.getsize(os.path.join(root, fn))
                    count += 1
                except OSError:
                    pass
    except OSError:
        pass
    _DIR_STAT_CACHE.update({"ts": now, "path": path, "size": size, "count": count})
    return size, count


def backup_stamp(fn):
    """从备份文件名（blog_backup_YYYYMMDD_HHMMSS.zip）解析出可读时间戳。"""
    import re as _re
    m = _re.search(r"blog_backup_(\d{8})_(\d{6})", fn or "")
    if not m:
        return ""
    d, t = m.group(1), m.group(2)
    return "%s-%s-%s %s:%s:%s" % (d[:4], d[4:6], d[6:8], t[:2], t[2:4], t[4:6])


def list_backups():
    out = []
    if not os.path.isdir(BACKUP_ROOT):
        return out
    for fn in sorted(os.listdir(BACKUP_ROOT)):
        if not (fn.startswith("blog_backup_") and fn.endswith(".zip")):
            continue
        fp = os.path.join(BACKUP_ROOT, fn)
        info = {"file": fn, "size": os.path.getsize(fp)}
        stem = fn[len("blog_backup_"):-len(".zip")]
        man = os.path.join(BACKUP_ROOT, "manifest_%s.json" % stem)
        if os.path.exists(man):
            try:
                m = json.load(open(man, encoding="utf-8"))
                info["created_at"] = m.get("created_at")
                info["file_count"] = m.get("file_count")
                info["app_version"] = m.get("app_version")
                info["integrity"] = "ok"
            except Exception:
                info["integrity"] = "manifest 解析失败"
        else:
            info["integrity"] = "缺 manifest"
        out.append(info)
    return out


_MAX_MEMBER_BYTES = 512 * 1024 * 1024   # 单个备份成员解压后允许的上限


def _sha256_stream(fh, limit):
    """分块哈希；累计读出超过 limit 字节立即抛错（不把成员整体读进内存）。"""
    h = hashlib.sha256()
    read = 0
    while True:
        chunk = fh.read(1 << 20)
        if not chunk:
            break
        read += len(chunk)
        if read > limit:
            raise ValueError("成员解压后超过上限 %.0f MiB，拒绝" % (limit / 1048576))
        h.update(chunk)
    return h.hexdigest()


def verify(arc_path):
    """校验备份包完整性：manifest 存在 + 每个文件 SHA256 一致 + 路径白名单。"""
    if not os.path.exists(arc_path):
        return False, "备份文件不存在"
    try:
        with zipfile.ZipFile(arc_path) as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                return False, "备份包缺少 manifest.json"
            man = json.loads(zf.read("manifest.json").decode("utf-8"))
            for item in man.get("files", []):
                rel = item["path"]
                if not _safe_rel(rel):
                    return False, "manifest 含非法路径: %s" % rel
                if rel not in names:
                    return False, "缺少文件: %s" % rel
                info = zf.getinfo(rel)
                declared = int(item.get("size") or 0)
                # manifest 里本来就写了 size（create_backup 记的），却从未被校验：
                # 补上，顺带挡住「解压后巨大」的成员——原实现 zf.read() 整体进内存。
                if declared and info.file_size != declared:
                    return False, "尺寸与 manifest 不符: %s" % rel
                if info.file_size > _MAX_MEMBER_BYTES:
                    return False, "成员过大（%.0f MiB）: %s" % (
                        info.file_size / 1048576, rel)
                with zf.open(rel) as fh:
                    if _sha256_stream(fh, _MAX_MEMBER_BYTES) != item["sha256"]:
                        return False, "哈希不一致: %s" % rel
        return True, man
    except Exception as e:
        return False, str(e)


def _snapshot_before_restore(tag=""):
    """恢复前自动打一份当前数据快照，命名含标签，便于回退。

    三个必须一起满足的性质（v3.21.2 审计时三条全不成立）：
    1. **不能抛异常** —— 调用方 `restore()` 在覆盖主库**之前**打快照，快照一崩
       整个恢复动作就中止，等于「最需要恢复的时候恢复不可用」；
    2. **必须自带 manifest** —— 否则 `verify()` 拒收，这份快照永远无法被恢复回去，
       「回退保险」是纸面的；
    3. **必须被清理** —— 旧名 `blog_prerestore_*` 不被 `prune_local()` 的
       `blog_backup_` 前缀匹配，会在小盘上无限堆积。
    """
    ts = _now().strftime("%Y%m%d_%H%M%S")
    safe_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", tag or "")[:40]
    name = "blog_backup_prerestore_%s%s.zip" % (ts, ("_" + safe_tag) if safe_tag else "")
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    arc = os.path.join(BACKUP_ROOT, name)
    manifest = {
        "created_at": _now().isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "kind": "prerestore",
        "files": [],
    }
    snap = make_db_snapshot(os.path.join(DATA_DIR, "blog.db"))
    try:
        with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as zf:
            if snap:
                zf.write(snap, "data/blog.db")
                manifest["files"].append(
                    {"path": "data/blog.db", "sha256": _sha256_file(snap),
                     "size": os.path.getsize(snap)})
            if os.path.isdir(UPLOAD_DIR):
                for dirpath, _dirnames, filenames in os.walk(UPLOAD_DIR):
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        rel = os.path.relpath(full, BASE_DIR).replace("\\", "/")
                        if not _safe_rel(rel):
                            continue
                        zf.write(full, rel)
                        manifest["files"].append(
                            {"path": rel, "sha256": _sha256_file(full),
                             "size": os.path.getsize(full)})
            manifest["file_count"] = len(manifest["files"])
            zf.writestr("manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001  R94 §94.6：快照失败必须降级、绝不阻断恢复——最需要恢复的时候不能因为保险快照自己崩了而恢复不了；异常已写 stderr 供排查
        # 快照失败绝不阻断恢复：降级为「无保险地继续」，并由调用方把警告打给用户
        sys.stderr.write("[备份] 恢复前快照失败（不影响恢复本身）：%s\n" % e)
        try:
            os.remove(arc)
        except OSError:
            pass
        return None
    finally:
        cleanup_db_snapshot(snap)
    with open(os.path.join(BACKUP_ROOT, "manifest_prerestore_%s%s.json" % (ts, ("_" + safe_tag) if safe_tag else "")),
              "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return arc


# ===== v3.25.2：备份自动巡检 =========================================
# 为什么必须有：**备份的价值 100% 取决于「能不能恢复」，而这个属性一旦不主动
# 验证就永远是未知的**。等到某天磁盘故障时才发现备份包解不开 / 哈希对不上，
# 备份就等于没做 —— 而那正是最需要它的一天。
#
# 设计取舍（与项目既有范式一致）：
#   · **零新表**：结果落 `data/backup_verify.json`，与 `tasks.py` 的状态文件同思路
#     （4 个 gunicorn worker 是独立进程，内存态彼此不可见）。
#   · **不新增线程**：挂在 `_start_scheduler` 已有的每日一轮循环里，与
#     「保留策略清理」并列（`_last_prune_day` 那个闭包）。
#   · **失败必须响**：静默的巡检等于没做 —— 写 logger.error + 状态文件标红 +
#     后台页显示，别让「巡检跑过了」变成一种安心的错觉。

VERIFY_STATE_FILE = "backup_verify.json"


def _verify_state_path():
    return os.path.join(DATA_DIR, VERIFY_STATE_FILE)


def read_verify_state():
    """读上次巡检结果；文件不存在 / 损坏一律返回「从未巡检」，不抛异常。

    刻意不返回 None：调用方（后台模板）要的是「有没有问题」，而不是
    「有没有数据」，None 会让模板分支变多。

    **缺 key 要补齐默认值**：文件可能是旧版本写的、也可能是手工塞进去的残缺 JSON。
    模板里直接 `verify_state.checked_at` 取值，缺 key 就会在**后台页面白屏**（Jinja
    对 undefined 不报错，只渲染空）——「巡检功能把备份页搞崩了」比「巡检没显示」
    严重得多。故此处逐 key 补默认。
    """
    defaults = {"status": "never", "checked_at": "", "checked": 0,
                "ok_count": 0, "bad_count": 0, "bad_items": [], "message": "尚未执行过自动巡检"}
    try:
        with open(_verify_state_path(), encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict):
            merged = dict(defaults)
            merged.update(st)
            # bad_items 必须是 list：手工编辑过的文件里可能是字符串或 null，
            # 模板 `{% for it in verify_state.bad_items %}` 遇到非可迭代对象会抛异常。
            if not isinstance(merged.get("bad_items"), list):
                merged["bad_items"] = []
            return merged
    except (OSError, ValueError):
        pass
    return defaults


def list_archives(limit=None):
    """本地备份包列表（按归档名倒序 = 时间倒序），可选截断。

    归档名 `blog_backup_YYYYMMDD_HHMMSS.zip` 是定长且字典序 == 时间序
    （`create_backup` 用 `_now().strftime("%Y%m%d_%H%M%S")` 生成），故直接按名排序。
    """
    try:
        names = [n for n in os.listdir(BACKUP_ROOT)
                 if n.startswith("blog_backup_") and n.endswith(".zip")]
    except OSError:
        return []
    names.sort(reverse=True)
    if limit:
        names = names[:limit]
    return [os.path.join(BACKUP_ROOT, n) for n in names]


def verify_latest(keep=3):
    """巡检最近 keep 个本地备份包的可恢复性，结果落盘并返回。

    **默认 keep=3 而不是「全部」**：一次全量巡检要把每个包完整读一遍算 SHA256
    （3MB/包起），包多了会占住定时线程很久；而且「最近 3 个能否恢复」已经足够
    回答「备份机制是否还活着」—— 远古包坏掉不影响今天能否恢复。
    """
    arcs = list_archives(limit=keep)
    result = {
        "status": "ok",
        "checked_at": _now().isoformat(timespec="seconds"),
        "checked": len(arcs),
        "ok_count": 0,
        "bad_count": 0,
        "bad_items": [],
        "message": "",
    }
    if not arcs:
        # 没有备份 ≠ 巡检失败，但也绝不能报「一切正常」——那是误导。
        result.update(status="empty", message="本地没有任何备份包，请先手动备份一次")
        _write_verify_state(result)
        return result

    for path in arcs:
        name = os.path.basename(path)
        try:
            ok, msg = verify(path)
        except Exception as e:      # noqa: BLE001  单个包校验异常不应中断整轮巡检
            ok, msg = False, "校验过程异常: %s" % str(e)[:120]
        if ok:
            result["ok_count"] += 1
        else:
            result["bad_count"] += 1
            result["bad_items"].append({"name": name, "reason": str(msg)[:200]})

    if result["bad_count"]:
        result["status"] = "bad"
        result["message"] = "%d/%d 个备份包校验不通过（最近一个是 %s）" % (
            result["bad_count"], result["checked"], os.path.basename(arcs[0]))
    else:
        result["status"] = "ok"
        result["message"] = "最近 %d 个备份包均可恢复" % result["checked"]

    _write_verify_state(result)
    return result


def _write_verify_state(result):
    """落盘巡检结果。写失败只记 warning —— 巡检本身已经跑完，不该因落盘失败而丢结果。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_verify_state_path(), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("[备份巡检] 结果落盘失败（巡检本身已完成）: %s", e)


def restore(arc_path, yes=False, tag=""):
    """从指定备份恢复。需 yes=True（CLI）或后台强确认；恢复前自动快照。

    注意：SQLite 数据库文件在应用运行期间被覆盖存在风险，调用方应在恢复前
    「停止」站点（宝塔），恢复后「启动」。本函数只负责把文件落回原位。
    """
    if not yes:
        raise SystemExit("恢复需显式确认：python backup.py restore <path> --yes")
    ok, man_or_msg = verify(arc_path)
    if not ok:
        raise SystemExit("备份校验未通过，拒绝恢复：" + str(man_or_msg))
    snap = _snapshot_before_restore(tag)
    if not snap:
        sys.stderr.write("[备份] 未能建立恢复前快照，本次恢复**没有回退点**，请确认已另行冷备\n")
    with zipfile.ZipFile(arc_path) as zf:
        for item in man_or_msg["files"]:
            rel = item["path"]
            if not _safe_rel(rel):
                continue
            target = os.path.join(BASE_DIR, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(zf.read(rel))
    # v3.9.1：覆盖主库后必须清掉旧的 -wal/-shm，否则 SQLite 会拿旧 WAL 回放新库导致损坏
    cleared = drop_wal_sidecars(os.path.join(DATA_DIR, "blog.db"))
    return {"restored_from": arc_path, "snapshot": snap,
            "file_count": man_or_msg["file_count"], "wal_cleared": cleared}


def main(argv=None):
    ap = argparse.ArgumentParser(description="llhhy-blog 数据备份")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run", help="执行一次完整备份")
    sub.add_parser("list", help="列出本地备份")
    p_ver = sub.add_parser("verify", help="校验备份完整性")
    p_ver.add_argument("path")
    p_res = sub.add_parser("restore", help="从备份恢复")
    p_res.add_argument("path")
    p_res.add_argument("--yes", action="store_true", help="强制确认")
    p_res.add_argument("--tag", default="", help="快照标签")
    args = ap.parse_args(argv)

    if args.cmd == "run" or args.cmd is None:
        arc, man, sync = create_backup()
        print("备份完成: %s" % arc)
        print("  文件数: %d  整包SHA256: %s" % (
            man["file_count"], man.get("archive_sha256", "")[:16]))
        for name, ok, msg in sync:
            print("  远程[%s]: %s %s" % (name, "✅" if ok else "⚠️", msg))
    elif args.cmd == "list":
        for b in list_backups():
            print(b)
    elif args.cmd == "verify":
        ok, m = verify(args.path)
        print("OK" if ok else "FAIL", m)
    elif args.cmd == "restore":
        r = restore(args.path, yes=args.yes, tag=args.tag)
        print("恢复完成: %s (快照 %s)" % (r["restored_from"], r["snapshot"]))


if __name__ == "__main__":
    main()
