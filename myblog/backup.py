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

BACKUP_ROOT = os.environ.get("BACKUP_DIR") or _DEF_BACKUP_DIR
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS") or _DEF_RETENTION)


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
        with zipfile.ZipFile(arc_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1) 数据库
            db = os.path.join(DATA_DIR, "blog.db")
            if os.path.exists(db):
                rel = "data/blog.db"
                zf.write(db, rel)
                manifest["files"].append(
                    {"path": rel, "sha256": _sha256_file(db), "size": os.path.getsize(db)})
            # 2) 上传目录（图片等）
            if os.path.isdir(UPLOAD_DIR):
                for dirpath, dirnames, filenames in os.walk(UPLOAD_DIR):
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
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run(cmd, timeout=300):
    """执行外部命令；失败抛异常由调用方捕获。"""
    if isinstance(cmd, str):
        return subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout,
                              check=True)
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


def sync_scp(arc, man):
    """scp 到备用机。依赖系统 scp + SSH 互信或 BACKUP_SCP_KEY。"""
    try:
        host = os.environ["BACKUP_SCP_HOST"]          # user@host
        dest = os.environ.get("BACKUP_SCP_DIR", "~/blog_backups")
        port = os.environ.get("BACKUP_SCP_PORT", "22")
        key = os.environ.get("BACKUP_SCP_KEY", "")
        opts = ["-P", str(port)]
        if key:
            opts += ["-i", key]
        for f in (arc, man):
            _run(["scp"] + opts + [f, "%s:%s/" % (host, dest)], timeout=300)
        return ("scp", True, "ok")
    except Exception as e:
        return ("scp", False, str(e)[:200])


def sync_webdav(arc, man):
    """网盘/云盘（WebDAV 通用：坚果云 / Nextcloud / 群晖 Drive 等）。依赖系统 curl。"""
    try:
        url = os.environ["BACKUP_WEBDAV_URL"].rstrip("/")
        user = os.environ.get("BACKUP_WEBDAV_USER", "")
        pwd = os.environ.get("BACKUP_WEBDAV_PASS", "")
        auth = ["-u", "%s:%s" % (user, pwd)] if user else []
        for f in (arc, man):
            _run(["curl", "-sS", "-f"] + auth + ["-T", f,
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
                data = zf.read(rel)
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    return False, "哈希不一致: %s" % rel
        return True, man
    except Exception as e:
        return False, str(e)


def _snapshot_before_restore(tag=""):
    """恢复前自动打一份当前数据快照，命名含标签，便于回退。"""
    ts = _now().strftime("%Y%m%d_%H%M%S")
    name = "blog_prerestore_%s%s.zip" % (ts, ("_" + tag) if tag else "")
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    arc = os.path.join(BACKUP_ROOT, name)
    with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as zf:
        db = os.path.join(DATA_DIR, "blog.db")
        if os.path.exists(db):
            zf.write(db, "data/blog.db")
        if os.path.isdir(UPLOAD_DIR):
            for dirpath, dirnames, filenames in os.walk(UPLOAD_DIR):
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, BASE_DIR).replace("\\", "/")
                    if _safe_rel(rel):
                        zf.write(full, rel)
    return arc


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
    with zipfile.ZipFile(arc_path) as zf:
        for item in man_or_msg["files"]:
            rel = item["path"]
            if not _safe_rel(rel):
                continue
            target = os.path.join(BASE_DIR, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(zf.read(rel))
    return {"restored_from": arc_path, "snapshot": snap, "file_count": man_or_msg["file_count"]}


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
