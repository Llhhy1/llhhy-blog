# -*- coding: utf-8 -*-
"""媒体存储后端（v4.14.0）：本地 / 对象存储 / WebDAV 网盘。

## 为什么复刻 backup.py 的通道而不是引新依赖

`backup.py` 已经趟过两条路，坑都在注释里写清了：

- **OSS**：boto3（S3 兼容协议，阿里云 OSS / 腾讯云 COS / MinIO 都能用）。
  未安装 boto3 时**明确报错**，不是静默降级 —— 用户选了云存储却存到本地，
  比直接失败更糟（他以为文件在云上，本地盘被悄悄写满）。
- **WebDAV**：系统 `curl`（坚果云 / Nextcloud / 群晖 都支持）。
  用 curl 而不是 Python 库，是为了不再多一个 `requests`/`webdavclient3` 依赖 ——
  服务器上 curl 本来就有（备份功能一直在用）。

## 与备份配置的关系：**完全独立**

不复用 `BACKUP_OSS_*`。理由很实在：备份桶通常**私有**（放数据库快照），
而图床桶必须**公开可读**（浏览器要直接加载图片）。混用会把私有桶变成公开桶，
或者让图片 403。所以这里是独立的一套 `media_*` 键。

## 密钥存储

SecretKey / 密码用 `backup_settings.encrypt_secret()`（Fernet，`bkenc$` 前缀）加密后
存 `Setting` 表 —— 与备份配置同一套做法。页面上只回显掩码，留空表示「不修改」。
"""
import logging
import os
import subprocess

from flask import current_app

log = logging.getLogger(__name__)

_BACKENDS = ("local", "oss", "webdav")


def _s(key, default=""):
    from utils.settings import get_setting
    v = get_setting(key)
    return (str(v).strip() if v is not None else "") or default


def _secret(key):
    """读取加密存储的密钥；解密失败按空处理（不让整个上传链路 500）。"""
    raw = _s(key)
    if not raw:
        return ""
    try:
        from backup_settings import decrypt_secret
        return decrypt_secret(raw) or ""
    except Exception as e:  # noqa: BLE001
        log.warning("[MEDIA] 读取 %s 失败：%s", key, str(e)[:120])
        return ""


def backend():
    """当前启用的后端：local / oss / webdav。

    未知值一律回落 local —— 配置写错不该让整个媒体库不可用。
    """
    b = (_s("media_backend") or "local").lower()
    return b if b in _BACKENDS else "local"


def conf(b=None):
    """一次性读出后端所需配置（供上传与状态展示共用）。

    `b` 可显式指定后端：删除资源时要按**当初存它的那个后端**去删，
    不能按「当前激活的后端」—— 中途换过后端的话，两者不是一回事。
    """
    b = (b or backend()).lower()
    if b == "oss":
        return {
            "backend": b,
            "bucket": _s("media_oss_bucket"),
            "region": _s("media_oss_region"),
            "endpoint": _s("media_oss_endpoint"),
            "key": _s("media_oss_key"),
            "secret": _secret("media_oss_secret"),
            "public_base": _s("media_oss_public_base").rstrip("/"),
            "prefix": _s("media_oss_prefix", "media").strip("/"),
        }
    if b == "webdav":
        return {
            "backend": b,
            "url": _s("media_webdav_url").rstrip("/"),
            "user": _s("media_webdav_user"),
            "password": _secret("media_webdav_password"),
            "public_base": _s("media_webdav_public_base").rstrip("/"),
            "prefix": _s("media_webdav_prefix", "media").strip("/"),
        }
    return {"backend": "local"}


def is_configured(c=None):
    """当前后端是否配置完整。未配置时上传**回落本地**（并留痕），不阻断写文章。"""
    c = c or conf()
    if c["backend"] == "oss":
        return bool(c["bucket"] and c["key"] and c["secret"] and c["public_base"])
    if c["backend"] == "webdav":
        return bool(c["url"] and c["public_base"])
    return True


def status():
    """给后台页面用的状态摘要（不含任何密钥明文）。"""
    c = conf()
    ok = is_configured(c)
    out = {"backend": c["backend"], "configured": ok, "message": ""}
    if c["backend"] == "oss":
        out["public_base"] = c["public_base"]
        if not ok:
            out["message"] = "OSS 配置不完整（Bucket / Key / Secret / 公开访问前缀缺一不可）"
        else:
            try:
                import boto3  # noqa: F401
            except Exception:
                out["configured"] = False
                out["message"] = "已填 OSS 配置，但服务器未安装 boto3（pip install boto3）"
    elif c["backend"] == "webdav":
        out["public_base"] = c["public_base"]
        if not ok:
            out["message"] = "WebDAV 配置不完整（地址与公开访问前缀必填）"
        elif not _has_curl():
            out["configured"] = False
            out["message"] = "服务器上没有 curl，无法使用 WebDAV 后端"
    return out


def _has_curl():
    from shutil import which
    return bool(which("curl"))


def object_key(filename):
    """对象键：`<prefix>/<文件名>`。prefix 为空时退化为文件名。"""
    c = conf()
    prefix = c.get("prefix") or ""
    return ("%s/%s" % (prefix, filename)) if prefix else filename


def put_file(local_path, filename, mime=""):
    """把本地文件送上当前后端，返回 `(ok, url_or_message)`。

    **本地后端直接返回站内 URL**（调用方不需要区别对待）。
    云后端成功后会删除本地副本吗？**不会** —— 见 `publish()`，那里统一处理。
    """
    c = conf()
    if c["backend"] == "local":
        return True, "/static/uploads/" + filename

    key = object_key(filename)
    if c["backend"] == "oss":
        ok, msg = _put_oss(local_path, key, c, mime)
    else:
        ok, msg = _put_webdav(local_path, key, c, mime)
    if not ok:
        return False, msg
    return True, "%s/%s" % (c["public_base"], key)


def _put_oss(local_path, key, c, mime):
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except Exception:
        return False, "服务器未安装 boto3，无法上传到对象存储（pip install boto3）"
    try:
        kw = {"aws_access_key_id": c["key"], "aws_secret_access_key": c["secret"],
              "config": BotoConfig(signature_version="s3v4", retries={"max_attempts": 2})}
        if c["region"]:
            kw["region_name"] = c["region"]
        if c["endpoint"]:
            kw["endpoint_url"] = c["endpoint"]
        client = boto3.client("s3", **kw)
        extra = {"ACL": "public-read"}
        if mime:
            extra["ContentType"] = mime
        with open(local_path, "rb") as f:
            client.put_object(Bucket=c["bucket"], Key=key, Body=f, **extra)
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("[MEDIA] OSS 上传失败：%s", str(e)[:200])
        return False, "对象存储上传失败：%s" % str(e)[:160]


def _put_webdav(local_path, key, c, mime):
    """用系统 curl 走 WebDAV PUT。

    `--fail` 让 4xx/5xx 变成非零退出码（否则 curl 默认对 404 也返回 0）；
    `--max-time 120` 防止网盘端卡死把 gunicorn worker 拖到超时。
    """
    if not _has_curl():
        return False, "服务器上没有 curl，无法使用 WebDAV"
    url = "%s/%s" % (c["url"], key)
    cmd = ["curl", "-sS", "--fail", "--max-time", "120", "-T", local_path, url]
    if c["user"]:
        cmd[3:3] = ["-u", "%s:%s" % (c["user"], c["password"])]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=150)
        if p.returncode != 0:
            return False, "WebDAV 上传失败：%s" % (p.stderr or b"").decode("utf-8", "ignore")[:160]
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        log.warning("[MEDIA] WebDAV 上传异常：%s", str(e)[:200])
        return False, "WebDAV 上传异常：%s" % str(e)[:160]


def publish(local_path, filename, mime=""):
    """上传落盘的统一出口：送后端 → 云后端成功则删除本地副本。

    返回 `(ok, url_or_message)`。**失败时不删本地文件**，调用方可以把它作为
    本地资源登记（UI 会提示「云端失败，已存本地」），文件不会凭空消失。
    """
    ok, msg = put_file(local_path, filename, mime)
    if not ok:
        return False, msg
    if backend() != "local":
        try:
            os.remove(local_path)
        except OSError:
            log.warning("[MEDIA] 云端已上传但本地副本删除失败：%s", local_path)
    return True, msg


def delete_remote(filename, storage=None):
    """尽力删除云端对象；失败只记日志、不抛。

    删除本地文件是「管理员明确要求的动作」，不该因为云端 API 抖动而失败 ——
    否则会留下一条「点了删除但还在」的僵尸记录。远端残留最多占点空间。
    """
    storage = storage or backend()
    if storage == "local" or not filename:
        return True
    c = conf(storage)
    key = object_key(filename)
    try:
        if storage == "oss":
            import boto3
            from botocore.config import Config as BotoConfig
            kw = {"aws_access_key_id": c["key"], "aws_secret_access_key": c["secret"],
                  "config": BotoConfig(signature_version="s3v4", retries={"max_attempts": 2})}
            if c["region"]:
                kw["region_name"] = c["region"]
            if c["endpoint"]:
                kw["endpoint_url"] = c["endpoint"]
            boto3.client("s3", **kw).delete_object(Bucket=c["bucket"], Key=key)
        elif storage == "webdav" and _has_curl():
            cmd = ["curl", "-sS", "--fail", "--max-time", "60", "-X", "DELETE",
                   "%s/%s" % (c["url"], key)]
            if c["user"]:
                cmd[3:3] = ["-u", "%s:%s" % (c["user"], c["password"])]
            subprocess.run(cmd, capture_output=True, timeout=90)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[MEDIA] 远端删除失败 %s：%s", key, str(e)[:160])
        return False


def test_connection():
    """后台「测试连接」：写一个 1 字节对象，确认凭据真的可用。"""
    c = conf()
    if c["backend"] == "local":
        return True, "当前是本地存储，无需测试"
    probe = os.path.join(current_app.config.get("UPLOAD_TMP_DIR", "/tmp"), ".probe")
    try:
        with open(probe, "wb") as f:
            f.write(b"0")
        ok, msg = put_file(probe, ".probe-%d" % os.getpid(), "application/octet-stream")
        return ok, (msg if ok else msg)
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
