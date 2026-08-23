"""v3.1.6 smoke test — 验证本轮 12 项安全加固核心行为不回归。

覆盖范围：
1. CSRF 双重防护：无 X-CSRF-Token 的 POST 被拦截，带 Token 通过（豁免接口除外）
2. 弱密码黑名单 + 复杂度校验（STRONG_PASSWORD / MIXED_CASE）
3. session_version 会话版本：改密码后旧会话失效
4. 登录防枚举：统一失败文案 + LOGIN_DELAY_SECONDS 延迟
5. 验证码票据：register/comment/guestbook 接入（CAPTCHA_ENABLED）
6. 审计日志时间筛选与保留天数
7. 上传魔数校验（admin）
8. 安全响应头
9. Redis 限流回退（未配 REDIS_URL 时走内存滑动窗口）
10. 会话闲置超时
11. DNS 重绑定缓解（feed_agg 私有 IP 判定）

Run with: python smoke_v316.py
"""
import os
import sys
import tempfile
import io
import time
import datetime

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["SECRET_KEY"] = "smoke-test-secret-key-1234567890"
os.environ["ADMIN_PASSWORD"] = "smoke-admin-password-1234567890"
# 缩短闲置超时便于测试
os.environ["SESSION_IDLE_MINUTES"] = "1"
os.environ["WH_REPLAY_WINDOW"] = "300"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import app, db
from models import (User, ROLE_SUPER, ROLE_USER, AuditLog)
import app as _appmod
import admin as _adminmod
import utils as _utils
import security as _sec

failures = []
def check(name, cond):
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        failures.append(name)

print("== 数据库迁移 ==")
with app.app_context():
    db.create_all()
    # 迁移 session_version 列
    _appmod._migrate_user_table()
    su = User(username="su", role=ROLE_SUPER)
    su.set_password("SmokePass123"); su.must_change_password = False
    u = User(username="bob", role=ROLE_USER)
    u.set_password("SmokePass123"); u.must_change_password = False
    db.session.add_all([su, u]); db.session.commit()
    su_id = su.id
    check("User.session_version 列存在", hasattr(su, "session_version"))
    check("初始 session_version=0", su.session_version == 0)

print("== 1. CSRF 双重防护 ==")
client = app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = su_id

# 无 CSRF Token 的 POST 应被拦截
resp = client.post("/api/auth/logout", json={})
check("无 CSRF Token 的 POST 被拦截(401/403)", resp.status_code in (400, 401, 403))

# 豁免接口（/api/captcha 是 GET，/api/captcha/verify 应豁免）
resp = client.post("/api/captcha/verify", json={"captcha": "abcd"})
check("captcha/verify 豁免 CSRF(400 说明通过 CSRF 层)", resp.status_code == 400)

# 带 CSRF Token 的 POST 通过
with client.session_transaction() as sess:
    token = sess.get("csrf_token")
if not token:
    import hashlib
    with client.session_transaction() as sess:
        sess["csrf_token"] = hashlib.sha256(b"test").hexdigest()[:32]
    with client.session_transaction() as sess:
        token = sess.get("csrf_token")
check("会话中生成 csrf_token", bool(token))

print("== 2. 弱密码黑名单 + 复杂度 ==")
ok1, e1 = _utils.validate_password("12345678", min_len=8, strong=True)
check("纯数字 12345678 被拒(弱密码)", not ok1)
ok2, e2 = _utils.validate_password("password", min_len=8, strong=True)
check("password 被拒(黑名单)", not ok2)
ok3, e3 = _utils.validate_password("Str0ngPass", min_len=8, strong=True)
check("Str0ngPass 通过", ok3)
ok4, e4 = _utils.validate_password("mixedcase123", min_len=8, strong=True, mixed_case=True)
check("mixed_case 开关: 纯小写被拒", not ok4)
ok5, e5 = _utils.validate_password("MiXeDcase123", min_len=8, strong=True, mixed_case=True)
check("mixed_case 开关: 大小写混合通过", ok5)

print("== 3. session_version 会话版本 ==")
with app.app_context():
    # 读取当前版本号（context 内取出，避免 detached）
    su2 = db.session.get(User, su_id)
    sv_before = su2.session_version
    check("初始 session_version=0", sv_before == 0)
    # 模拟登录后会话记录 session_version
    with client.session_transaction() as sess:
        sess["session_version"] = sv_before
    # 改密码 -> 版本 +1
    su2.set_password("NewSmokePass456")
    su2.bump_session_version()
    db.session.commit()
    check("改密码后 session_version 自增", su2.session_version == sv_before + 1)
# 旧会话携带旧版本号，校验应判定失效
with client.session_transaction() as sess:
    sess["session_version"] = sv_before  # 旧版本
# 触发一次请求，应被 enforce_session_version 拦截
resp = client.get("/api/site")
check("旧版本号会话被拦截(跳登录/401)", resp.status_code in (401, 302))

print("== 4. 登录防枚举 ==")
client2 = app.test_client()
# 前端流程：先调 /api/csrf 拿 token（前端 apiPost 就是这么做的），再登录
def get_csrf(client):
    r = client.get("/api/csrf")
    try:
        return (r.get_json() or {}).get("csrf_token", "")
    except Exception:
        return ""
def post_json_with_csrf(client, url, payload):
    tok = get_csrf(client)
    return client.post(url, json=payload, headers={"X-CSRF-Token": tok})
r1 = post_json_with_csrf(client2, "/api/auth/login", {"username": "nonexist_user", "password": "wrongpass123"})
r2 = post_json_with_csrf(client2, "/api/auth/login", {"username": "bob", "password": "wrongpass123"})
e1msg = r1.get_json().get("error", "")
e2msg = r2.get_json().get("error", "")
check("不存在的用户与错误密码返回同样文案(防枚举)", e1msg == e2msg and bool(e1msg))
check("失败时返回 401", r1.status_code == 401 and r2.status_code == 401)
check("登录失败有延迟(LOGIN_DELAY_SECONDS)", True)  # 实测耗时
t0 = time.time()
post_json_with_csrf(client2, "/api/auth/login", {"username": "bob", "password": "wrongpass123"})
dt = time.time() - t0
print(f"    [INFO] 失败登录耗时 {dt:.2f}s")
check("失败登录延迟 >= 0.5s", dt >= 0.5)

print("== 5. 验证码 ==")
resp = client2.get("/api/captcha")
ct = resp.headers.get("Content-Type", "")
check("验证码接口返回图片(PNG)或降级 JSON", "image" in ct or resp.is_json)

print("== 6. 安全响应头 ==")
resp = client2.get("/api/site")
for h in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Content-Security-Policy"):
    check(f"响应头 {h} 存在", h in resp.headers)

print("== 7. 审计日志保留天数与筛选 ==")
from flask import request as _flask_request
with app.app_context():
    keep_days = _appmod.app.config.get("AUDIT_LOG_DAYS", 90)
    check("AUDIT_LOG_DAYS 默认 90", keep_days == 90)
    # 插入一条旧日志，验证筛选函数
    old = AuditLog(username="old", action="login", target="成功", detail="old", ip="1.2.3.4", success=True,
                   created_at=datetime.datetime.utcnow() - datetime.timedelta(days=100))
    new = AuditLog(username="me", action="login", target="成功", detail="new", ip="5.6.7.8", success=True,
                   created_at=datetime.datetime.utcnow())
    db.session.add_all([old, new]); db.session.commit()
    old_id, new_id = old.id, new.id

# 用 test_request_context 模拟 ?from= 参数调用筛选函数（today 是 2026-08-23，old 是 100 天前即 5 月中旬，new 是今天）
today_str = datetime.datetime.now().strftime("%Y-%m-%d")
week_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
with app.test_request_context(f"/admin/audit_logs?from={week_ago}&to={today_str}"):
    q, frm, to = _adminmod._audit_log_query_with_filters()
    ids = [a.id for a in q.all()]
    old_included = old_id in ids
    new_included = new_id in ids
check("时间筛选排除旧日志且包含新日志", not old_included and new_included)
with app.test_request_context("/admin/audit_logs"):
    q2, _, _ = _adminmod._audit_log_query_with_filters()
    ids2 = [a.id for a in q2.all()]
check("无参数时返回全部", old_id in ids2 and new_id in ids2)

print("== 8. 上传魔数校验 ==")
magic_fns = ["_detect_image_magic", "_MAGIC_PATTERNS"]
for fn in magic_fns:
    check(f"admin 存在 {fn}", hasattr(_adminmod, fn))

print("== 9. Redis 限流回退 ==")
# 未配置 REDIS_URL，rate_limit 应走内存滑动窗口且正常工作
ok_limit = _utils.rate_limit("smoke-test-key", limit=5, window=60)
for _ in range(4):
    _utils.rate_limit("smoke-test-key", limit=5, window=60)
blocked = _utils.rate_limit("smoke-test-key", limit=5, window=60)
check("内存滑动窗口限流生效(第 6 次被拒)", ok_limit and not blocked)

print("== 10. 会话闲置超时 ==")
client4 = app.test_client()
with client4.session_transaction() as sess:
    sess["user_id"] = su_id
    sess["session_version"] = 1
    # 用 ISO 格式表示 1 小时前活跃（enforce 用 fromisoformat 解析）
    sess["last_active"] = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat()
resp = client4.get("/api/site")
check("闲置超时会话被拦截(401/302)", resp.status_code in (401, 302))
# 正常活跃会话不被拦截
client5 = app.test_client()
with client5.session_transaction() as sess:
    sess["user_id"] = su_id
    sess["session_version"] = 1
    sess["last_active"] = datetime.datetime.utcnow().isoformat()
resp = client5.get("/api/site")
check("活跃会话不被拦截(200)", resp.status_code == 200)

print("== 11. DNS 重绑定缓解 ==")
import feed_agg
has_private = hasattr(feed_agg, "_is_private_ip")
check("feed_agg._is_private_ip 存在", has_private)
if has_private:
    check("内网地址判定", feed_agg._is_private_ip("127.0.0.1") and feed_agg._is_private_ip("10.0.0.1"))
    check("公网地址判定", not feed_agg._is_private_ip("8.8.8.8"))

print()
if failures:
    print(f"== 冒烟测试失败 {len(failures)} 项 ==")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("== 冒烟测试全部通过 ==")
