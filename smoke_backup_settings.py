"""v3.4.0 备份配置后台化冒烟测试。
覆盖：加密落库 / 掩码回显 / 合并配置 / 后台保存路由 / backup.py 应用配置。
"""
import os
import sys
import tempfile
import shutil
import re

TMP = tempfile.mkdtemp(prefix="bkcfg_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(TMP, "blog.db")
os.environ["SECRET_KEY"] = "test-secret-for-backup-settings"
os.environ["ADMIN_PASSWORD"] = "Admin123!"
os.environ["BACKUP_DIR"] = os.path.join(TMP, "backups")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))

from app import create_app

app = create_app()
app.config["TESTING"] = True

def get_csrf(c):
    r = c.get("/api/csrf")
    return r.get_json().get("csrf_token") if r.is_json else None

passed = []

with app.test_client() as c:
    # 登录 + 首次设置
    tok = get_csrf(c)
    c.post("/login", data={"username": "admin", "password": "Admin123!", "csrf_token": tok or ""})
    c.get("/admin/setup")
    tok = get_csrf(c)
    c.post("/admin/setup", data={"username": "admin", "password": "Admin123!",
                                 "confirm_password": "Admin123!", "csrf_token": tok or ""})

    # GET 备份配置页
    r = c.get("/admin/backup-settings")
    body = r.get_data(as_text=True)
    assert r.status_code == 200, "backup-settings GET = %s" % r.status_code
    assert 'name="backup_oss_bucket"' in body, "模板缺 OSS 字段"
    assert 'name="backup_webdav_pass"' in body, "模板缺 WebDAV 密码字段"
    passed.append("GET /admin/backup-settings 渲染正常")

    # POST 保存配置（含密钥字段）
    tok = get_csrf(c)
    r = c.post("/admin/backup-settings", data={
        "backup_dir": os.path.join(TMP, "backups"),
        "backup_retention_days": "7",
        "backup_oss_bucket": "my-blog-backups",
        "backup_oss_region": "oss-cn-hangzhou",
        "backup_oss_endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "backup_oss_key": "LTAI-testkey",
        "backup_oss_secret": "SuperSecretKey123",
        "backup_oss_prefix": "backups",
        "backup_scp_host": "root@192.168.1.10",
        "backup_scp_dir": "~/blog_backups",
        "backup_scp_port": "22",
        "backup_scp_key": "/root/.ssh/id_ed25519",
        "backup_webdav_url": "https://dav.jianguoyun.com/dav/blog",
        "backup_webdav_user": "user@mail.com",
        "backup_webdav_pass": "WebDAVPass456",
        "csrf_token": tok or "",
    }, follow_redirects=True)
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "备份配置已保存" in body, \
        "POST 保存失败 status=%s body=%s" % (r.status_code, body[:200])
    passed.append("POST 保存备份配置成功")

    # 验证密文落库（不应出现明文）
    import sqlite3
    conn = sqlite3.connect(os.path.join(TMP, "blog.db"))
    rows = dict(conn.execute("SELECT key, value FROM setting WHERE key LIKE 'backup_%'").fetchall())
    conn.close()
    assert "SuperSecretKey123" not in str(rows), "OSS 密钥明文落库！"
    assert "WebDAVPass456" not in str(rows), "WebDAV 密码明文落库！"
    assert rows.get("backup_oss_secret", "").startswith("bkenc$"), "OSS 密钥未加密"
    assert rows.get("backup_webdav_pass", "").startswith("bkenc$"), "WebDAV 密码未加密"
    assert rows.get("backup_scp_key", "").startswith("bkenc$"), "SCP 私钥路径未加密"
    passed.append("敏感字段加密落库（无明文）")

    # GET 页面回显：敏感键应显示掩码而非明文
    r = c.get("/admin/backup-settings")
    body = r.get_data(as_text=True)
    assert "SuperSecretKey123" not in body, "页面回显 OSS 明文"
    assert "WebDAVPass456" not in body, "页面回显 WebDAV 明文"
    assert "Su****23" in body or "Se****" in body or "已设置" in body, "敏感键未掩码回显"
    passed.append("页面敏感键掩码回显（无明文泄漏）")

    # 合并配置生效：backup_settings.get_config 应返回解密后的真实密钥
    import backup_settings as bs
    cfg = bs.get_config()
    assert cfg.get("BACKUP_OSS_BUCKET") == "my-blog-backups", "OSS bucket 未读库值"
    assert cfg.get("BACKUP_RETENTION_DAYS") == "7", "保留天数未读库值"
    assert cfg.get("BACKUP_OSS_SECRET") == "SuperSecretKey123", "OSS 密钥解密失败"
    assert cfg.get("BACKUP_WEBDAV_PASS") == "WebDAVPass456", "WebDAV 密码解密失败"
    passed.append("合并配置解密正确")

    # backup.py 应用配置：BACKUP_ROOT / RETENTION_DAYS 应取后台值
    import backup
    assert backup.BACKUP_ROOT == os.path.join(TMP, "backups"), "BACKUP_ROOT 未取后台配置"
    assert backup.RETENTION_DAYS == 7, "RETENTION_DAYS 未取后台配置: %s" % backup.RETENTION_DAYS
    os.environ["BACKUP_OSS_SECRET"] = "EnvSecretOverride999"  # 密钥环境变量优先测试
    backup._BS.apply_env()
    assert os.environ.get("BACKUP_OSS_SECRET") == "EnvSecretOverride999", "密钥环境变量未优先生效"
    passed.append("backup.py 应用后台配置 + 密钥环境变量优先")

    # CLI 独立运行模式（无 Flask 上下文）：直接调 backup 模块函数
    import backup as bk2
    arc, man, sync = bk2.create_backup()
    assert os.path.exists(arc), "CLI 模式备份失败"
    passed.append("CLI 独立模式 create_backup 成功（使用后台配置）")

print("=== SMOKE 结果 ===")
for p in passed:
    print("✅", p)
print("共 %d 项全部通过" % len(passed))
shutil.rmtree(TMP, ignore_errors=True)
print("DONE")