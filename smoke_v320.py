"""v3.2.0 smoke test — 验证码后台独立设置页 + Pillow 依赖修复专项验证。

覆盖范围：
1. GET /api/captcha/config 默认配置（全局启用 + 三场景全开 + PIL 可用）
2. 关闭单场景（register）→ scenes.register=false 且该场景图片接口 404
3. 关闭全局 → enabled=false 且所有图片接口 404
4. captcha_length 配置生效（generate_captcha 输出长度跟随）
5. 后台 /admin/captcha-settings（super 登录）→ GET 200 含标题 + POST 保存生效

Run with: ./venv/Scripts/python smoke_v320.py
"""
import os
import sys
import tempfile

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["SECRET_KEY"] = "smoke-captcha-secret"
os.environ["ADMIN_PASSWORD"] = "SmokeAdmin123"
os.environ["SESSION_IDLE_MINUTES"] = "60"
os.environ.setdefault("CAPTCHA_ENABLED", "true")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))
from app import app, db
from models import User, ROLE_SUPER, Setting
import security

failures = []
def check(name, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)

def set_setting(key, value):
    with app.app_context():
        s = Setting.query.filter_by(key=key).first()
        if s is None:
            s = Setting(key=key, value=value)
            db.session.add(s)
        else:
            s.value = value
        db.session.commit()

with app.app_context():
    db.create_all()
    su = User(username="su", role=ROLE_SUPER)
    su.set_password("SmokeAdmin123")
    su.must_change_password = False
    db.session.add(su)
    db.session.commit()

client = app.test_client()

print("== 1. 默认配置 ==")
r = client.get("/api/captcha/config")
cfg = r.get_json()
check("config 接口 200", r.status_code == 200)
check("默认 enabled=true", cfg.get("enabled") is True)
sc = cfg.get("scenes", {})
check("默认三场景全开", bool(sc.get("register") and sc.get("comment") and sc.get("guestbook")))
check("PIL 可用(本地已装 Pillow)", cfg.get("available") is True)

print("== 2. 关闭注册场景 ==")
set_setting("captcha_on_register", "false")
r = client.get("/api/captcha/config")
cfg = r.get_json()
check("register 场景关闭", cfg["scenes"]["register"] is False)
check("comment 场景仍开", cfg["scenes"]["comment"] is True)
r2 = client.get("/api/captcha?from=register")
check("场景禁用→图片接口 404", r2.status_code == 404)
r3 = client.get("/api/captcha?from=comment")
check("未禁用场景→图片接口 200(出图或降级)", r3.status_code == 200)
set_setting("captcha_on_register", "true")

print("== 3. 关闭全局 ==")
set_setting("captcha_enabled", "false")
r = client.get("/api/captcha/config")
cfg = r.get_json()
check("全局关闭 enabled=false", cfg["enabled"] is False)
r2 = client.get("/api/captcha?from=register")
check("全局关闭→图片接口 404", r2.status_code == 404)
set_setting("captcha_enabled", "true")

print("== 4. 长度配置 ==")
set_setting("captcha_length", "6")
with app.test_request_context():
    img, text = security.generate_captcha()
    check("生成验证码长度=6", len(text) == 6)
set_setting("captcha_length", "4")

print("== 5. 后台设置页(super 登录) ==")
# 先取 CSRF token（GET 建立会话并生成 token），登录 POST 需携带
csrf = client.get("/api/csrf").get_json().get("csrf_token", "")
lr = client.post("/api/auth/login", json={"username": "su", "password": "SmokeAdmin123"},
                 headers={"X-CSRF-Token": csrf})
check("super 登录 200", lr.status_code == 200)
login_csrf = (lr.get_json() or {}).get("csrf_token", "") if lr.status_code == 200 else ""
r = client.get("/admin/captcha-settings")
check("设置页 GET 200", r.status_code == 200)
check("页面含『验证码设置』标题", "验证码设置" in r.get_data(as_text=True))
r = client.post("/admin/captcha-settings", data={
    "captcha_enabled": "true", "captcha_length": "5", "captcha_difficulty": "high",
    "captcha_exclude_ambiguous": "true", "captcha_on_register": "true",
    "captcha_on_comment": "true", "captcha_on_guestbook": "true",
    "csrf_token": login_csrf})
check("POST 保存重定向", r.status_code in (302, 303))
with app.app_context():
    lv = Setting.query.filter_by(key="captcha_length").first().value
    check("captcha_length 保存=5", lv == "5")

print("\n== 结果 ==", "全部通过 ✅" if not failures else f"失败项: {failures}")
sys.exit(1 if failures else 0)
