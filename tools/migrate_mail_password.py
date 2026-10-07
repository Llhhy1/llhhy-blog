"""一次性迁移：把 `mail_password` 的**存量明文**转成 Fernet 密文。

背景（v3.26.0 审计 R114 · CWE-312 明文存储敏感信息）：
后台「邮件设置」此前把 SMTP 授权码**明文**写进 `setting` 表，而同一项目的
备份密钥（OSS SecretKey / WebDAV 密码）与 SEO token 早已改用
`backup_settings.encrypt_secret()` 加密——`admin/seo.py` 的注释甚至写着
「不照抄 `mail_password` 的明文落库错误做法」。这次把写入侧补齐后，
库里**已存的明文**不会自动变密文（读侧 `decrypt_secret()` 对无前缀值原样返回，
所以功能不受影响，但明文依然躺在库里），需要跑一次本脚本。

用法（**必须先备份数据库**，脚本本身不备份）：
    # 本地/测试
    python tools/migrate_mail_password.py
    # 生产（服务器上）
    FLASK_APP=app:create_app <venv>/bin/python tools/migrate_mail_password.py

行为：
- 逐行扫描 `setting` 表里 key='mail_password' 的值；
- **已是 `bkenc$` 密文 → 跳过**（幂等，可重复跑）；
- 空值 → 跳过；
- 明文 → 加密写回，并**立刻回读解密比对**，不一致就报错并回滚该行。

⚠️ 依赖 `SECRET_KEY`：脚本用与线上应用**同一把**密钥派生 Fernet key。
若在没加载站点环境变量的shell 里跑，会因解不开密文而把密文当明文二次加密
（幂等判断会拦住已加密的值，但明文行会被错误处理）——所以务必先 source 环境文件。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, Setting  # noqa: E402


def main():
    if not os.environ.get("SECRET_KEY"):
        print("✗ 未检测到 SECRET_KEY 环境变量。")
        print("  请先加载站点环境变量文件，例如：")
        print("    set -a; . /www/server/python_project/vhost/env/myblog.env; set +a")
        return 2

    from app import create_app
    from backup_settings import encrypt_secret, decrypt_secret, ENC_PREFIX

    app = create_app(enable_scheduler=False)
    with app.app_context():
        row = db.session.query(Setting).filter_by(key="mail_password").first()
        if not row or not (row.value or "").strip():
            print("✓ 无 mail_password 明文，无需迁移。")
            return 0

        raw = row.value
        if raw.startswith(ENC_PREFIX):
            # 幂等：解密成功即视为已迁移；解不开说明 SECRET_KEY 不对，必须报错。
            if decrypt_secret(raw):
                print("✓ 已是密文（bkenc$ 前缀）且可正常解密，无需迁移。")
                return 0
            print("✗ 库中值是密文但当前 SECRET_KEY 解不开——请在正确的环境里跑本脚本。")
            return 2

        print("· 发现明文，长度 %d，正在加密…" % len(raw))
        enc = encrypt_secret(raw)
        back = decrypt_secret(enc)
        if back != raw:
            print("✗ 加密后回读比对不一致，已放弃写入（库中仍是原值）。")
            return 2
        row.value = enc
        db.session.commit()
        print("✓ 已转为密文（bkenc$ 前缀，长度 %d）。" % len(enc))
        print("  提醒：明文曾存在于历史备份文件里，旧备份 zip/db 仍含明文，")
        print("        请按需清理过期本地备份或轮换 SMTP 授权码。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
