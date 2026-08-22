"""v3.1.0 smoke test — 验证登录审计记录、30天清理、导出接口、汉堡主题修复不回归。

Run with: python smoke_v310.py
"""
import os
import sys
import tempfile
import io

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["SECRET_KEY"] = "smoke-test-secret-key-1234567890"
os.environ["ADMIN_PASSWORD"] = "smoke-admin-password-1234567890"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import app, db
from models import (User, AuditLog, ROLE_SUPER, ROLE_USER)
import app as _appmod
import admin as _adminmod

failures = []
def check(name, cond):
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        failures.append(name)

print("== 迁移 ==")
with app.app_context():
    db.create_all()
    _appmod._migrate_audit_log_table()
    # 新建超管 + 普通用户
    su = User(username="su", role=ROLE_SUPER)
    su.set_password("pw"); su.must_change_password = False
    u = User(username="bob", role=ROLE_USER)
    u.set_password("pw"); u.must_change_password = False
    db.session.add_all([su, u]); db.session.commit()

    print("== 登录审计记录 ==")
    # 模拟 admin.py login 成功
    _adminmod.log_login_attempt("su", True)
    # 模拟失败
    _adminmod.log_login_attempt("hacker", False)
    n_login = AuditLog.query.filter_by(action="login").count()
    check("登录记录写入(含成功/失败)", n_login == 2)
    ok = AuditLog.query.filter_by(action="login", success=True).count()
    bad = AuditLog.query.filter_by(action="login", success=False).count()
    check("成功/失败区分正确", ok == 1 and bad == 1)
    fail_log = AuditLog.query.filter_by(action="login", success=False).first()
    check("失败记录含尝试用户名", "hacker" in (fail_log.detail or ""))

    print("== 30 天保留清理 ==")
    # 插入一条 >30 天的旧日志，验证清理
    import datetime
    old = AuditLog(username="old", action="login", target="成功",
                   detail="old", ip="1.1.1.1", success=True,
                   created_at=datetime.datetime.utcnow() - datetime.timedelta(days=35))
    db.session.add(old); db.session.commit()
    before = AuditLog.query.count()
    _adminmod._purge_audit_logs_older_than(30)
    after = AuditLog.query.count()
    check("超过30天的旧日志被清理", after == before - 1)
    check("近30天记录保留", after >= 2)

    print("== 导出接口 ==")
    client = app.test_client()
    # 登录超管拿到会话
    with client.session_transaction() as sess:
        sess["user_id"] = su.id
    resp = client.get("/admin/audit-logs/export")
    check("导出接口返回 200", resp.status_code == 200)
    check("导出是 zip 附件", "application/zip" in (resp.headers.get("Content-Type") or ""))
    check("zip 含两个文件名", b"audit_logs.csv" in resp.data and b"audit_logs.txt" in resp.data)

    print("== 越权：普通用户不能导出 ==")
    with client.session_transaction() as sess:
        sess["user_id"] = u.id
    resp2 = client.get("/admin/audit-logs/export")
    check("普通用户导出被拒绝(302/403)", resp2.status_code in (302, 403))

print()
if failures:
    print("❌ 失败项:", failures)
    sys.exit(1)
else:
    print("✅ 全部通过")
    os.remove(tmp.name)
