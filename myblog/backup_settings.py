"""备份配置后台化管理（v3.4.0）。

把 v3.3.0 以来「只走环境变量」的 BACKUP_* 配置，改为「后台可配置」：
非密钥字段（目录/桶名/域名/路径/保留天数等）存 Setting 表，后台表单直改；
密钥字段（OSS SecretKey / WebDAV 密码 / SCP 私钥路径等）以「SECRET_KEY 派生的
Fernet 密钥」加密后存 Setting 表——**绝不落明文**，页面只回显掩码。

读取优先级（与邮件设置一致的双层回退）：
  非密钥字段：Setting 表（后台配置）优先 → 环境变量兜底；
  密钥字段  ：环境变量优先（老用户无需迁移）→ Setting 表加密值兜底。

本模块兼容两种运行环境：
  - Flask 应用内：直接用 SQLAlchemy（models.Setting）；
  - backup.py 独立 CLI（backup.sh 触发）：无 Flask 上下文，退化为 sqlite3 标准库
    直连 data/blog.db 读 Setting 表——保持 backup.py 纯标准库可独立运行。
"""
import os
import json
import base64
import secrets
import hashlib

# 加密前缀标记，解密时用于识别「已加密值」vs 明文（抵御历史明文）
ENC_PREFIX = "bkenc$"

# 各后端密钥字段（环境变量名 → Setting 键名）
SECRET_FIELDS = {
    "BACKUP_OSS_SECRET": "backup_oss_secret",
    "BACKUP_WEBDAV_PASS": "backup_webdav_pass",
}
# SCP 私钥是「路径」而非密钥本身，属非密钥字段但可能指向敏感位置，
# 保持与密钥相同处理（加密存储路径、不回显）。
SCP_KEY_FIELD = ("BACKUP_SCP_KEY", "backup_scp_key")

# 全部可后台配置字段：Setting 键名 → (环境变量名, 默认值)
ALL_FIELDS = {
    # 本地
    "backup_dir": ("BACKUP_DIR", ""),
    "backup_retention_days": ("BACKUP_RETENTION_DAYS", "14"),
    # OSS / 对象存储
    "backup_oss_bucket": ("BACKUP_OSS_BUCKET", ""),
    "backup_oss_region": ("BACKUP_OSS_REGION", ""),
    "backup_oss_endpoint": ("BACKUP_OSS_ENDPOINT", ""),
    "backup_oss_key": ("BACKUP_OSS_KEY", ""),
    "backup_oss_prefix": ("BACKUP_OSS_PREFIX", "backups"),
    # SCP
    "backup_scp_host": ("BACKUP_SCP_HOST", ""),
    "backup_scp_dir": ("BACKUP_SCP_DIR", "~/blog_backups"),
    "backup_scp_port": ("BACKUP_SCP_PORT", "22"),
    # WebDAV
    "backup_webdav_url": ("BACKUP_WEBDAV_URL", ""),
    "backup_webdav_user": ("BACKUP_WEBDAV_USER", ""),
    # 密钥/敏感字段（加密存储；环境变量优先；也纳入 ALL_FIELDS 以便表单保存）
    "backup_oss_secret": ("BACKUP_OSS_SECRET", ""),
    "backup_scp_key": ("BACKUP_SCP_KEY", ""),
    "backup_webdav_pass": ("BACKUP_WEBDAV_PASS", ""),
}
# 密钥/敏感字段（加密存储；环境变量优先）
SENSITIVE_KEYS = {SECRET_FIELDS["BACKUP_OSS_SECRET"], SECRET_FIELDS["BACKUP_WEBDAV_PASS"],
                  SCP_KEY_FIELD[1]}


def _db_path():
    """定位 SQLite 数据库文件：Flask 配置优先，CLI 用备份模块自身路径。"""
    try:
        from flask import current_app
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if uri and uri.startswith("sqlite:///"):
            return uri[len("sqlite:///"):]
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "blog.db")


_KDF_SALT = b"llhhy-blog-backup-secrets-v1"  # 固定盐保持确定性（重启后仍可解密）

def _fernet_key():
    """从 SECRET_KEY（环境变量或 Flask 配置）派生 Fernet 密钥（base64 urlsafe 32B）。
    用 PBKDF2-HMAC-SHA256（固定盐、高迭代）派生——SECRET_KEY 高熵 + KDF 双重
    加固，且固定盐保证「重启后密文仍可解密」。SECRET_KEY 缺失时拒绝（同应用启动约束）。
    """
    key = os.environ.get("SECRET_KEY") or ""
    try:
        from flask import current_app
        if not key:
            key = current_app.config.get("SECRET_KEY", "")
    except Exception:
        pass
    if not key:
        raise RuntimeError("SECRET_KEY 未配置，无法加密备份密钥（应用启动要求必须配置）")
    raw = hashlib.pbkdf2_hmac(
        "sha256", key.encode("utf-8"), _KDF_SALT, iterations=200_000, dklen=32)
    return base64.urlsafe_b64encode(raw)


def encrypt_secret(plain):
    """用 Fernet 加密明文。返回带前缀的密文串；空值原样返回。"""
    if not plain:
        return ""
    from cryptography.fernet import Fernet
    return ENC_PREFIX + Fernet(_fernet_key()).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored):
    """解密带前缀的密文；不是本模块加密（无前缀）或解密失败则原样返回。"""
    if not stored:
        return ""
    if not stored.startswith(ENC_PREFIX):
        return stored
    from cryptography.fernet import Fernet
    try:
        return Fernet(_fernet_key()).decrypt(stored[len(ENC_PREFIX):]).decode("utf-8")
    except Exception:
        # 密钥轮换/篡改：返回空并让调用方回退，绝不抛异常泄露
        return ""


def read_setting_db(key):
    """读取 Setting 表某键值：Flask 环境走 models.Setting；CLI 走 sqlite3。"""
    try:
        from models import Setting
        s = Setting.query.filter_by(key=key).first()
        return s.value if s and s.value is not None else None
    except Exception:
        pass
    import sqlite3
    try:
        conn = sqlite3.connect(_db_path())
        try:
            row = conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None


def write_setting_db(key, value):
    """写 Setting 表：Flask 环境走 SQLAlchemy；CLI 走 sqlite3（UPSERT，兼容应用内自建表）。"""
    try:
        from models import Setting, db
        s = Setting.query.filter_by(key=key).first()
        if s:
            s.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()
        return True
    except Exception:
        pass
    import sqlite3
    try:
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS setting (id INTEGER PRIMARY KEY, "
                         "key TEXT UNIQUE NOT NULL, value TEXT)")
            conn.execute("INSERT INTO setting(key, value) VALUES(?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def get_config():
    """合并后台配置 + 环境变量，返回可直接给 backup.py 使用的环境变量字典。
    非密钥字段：库值优先；密钥字段：环境变量优先 → 库值（加密解密）兜底。
    """
    cfg = {}
    for skey, (env, default) in ALL_FIELDS.items():
        db_val = read_setting_db(skey)
        if skey in SENSITIVE_KEYS:
            # 密钥：环境变量优先
            env_val = os.environ.get(env, "")
            val = env_val if env_val else decrypt_secret(db_val or "")
            cfg[env] = val
        else:
            # 非密钥：库值优先（空则回退环境变量，再回退默认）
            val = db_val if db_val not in (None, "") else os.environ.get(env, "")
            cfg[env] = val if val not in (None, "") else default
    return cfg


def apply_env():
    """把合并后的配置写回 os.environ，供 backup.py 读取（同步函数仍读环境变量）。"""
    for env, val in get_config().items():
        os.environ[env] = val


def mask_value(v):
    """掩码：非空且长度 > 4 显示前2后2，其余 **。用于页面不回显明文。"""
    if not v:
        return ""
    if len(v) <= 4:
        return "****"
    return v[:2] + "****" + v[-2:]


def setting_value_for_admin(skey):
    """后台回显用：非敏感键返回明文，敏感键返回掩码。"""
    db_val = read_setting_db(skey)
    if skey in SENSITIVE_KEYS:
        return mask_value(decrypt_secret(db_val or ""))
    return db_val or ""