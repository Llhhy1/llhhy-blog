"""v3.26.0 审计 R115 回归：2FA 闸门是否真的挡得住「仅密码会话」。

**争议点**：有审计报告称「只走 /admin/login 拿到仅密码会话 → 调
`/api/auth/2fa/enroll` 可重新生成密钥并把 `enabled` 打回 False」，
即 2FA 可被完整绕过。本文件**不采信任何转述**，用真实请求链实测。

判据（全部通过才算守卫有效）：
  1. 目标账号已绑定且 `enabled=True`，全局开关 twofa_enabled 打开；
  2. 攻击者只有**密码**（`session['twofa_ok']` 未设置）；
  3. `POST /api/auth/2fa/enroll` 必须被 401 拦住；
  4. 数据库里 `secret_enc` / `enabled` **不得发生任何变化**；
  5. 同一账号在**持有有效 TOTP** 时才能 enroll/reset。
"""
import contextlib
import os
import secrets

import pytest

from models import db, User, UserTwoFactor, Setting, ROLE_SUPER

PASSWORD = "Passw0rd!23"


@pytest.fixture()
def twofa_on(app):
    """打开 2FA 全局闸门（v3.25.8 起该开关可在后台配置，默认 false）。"""
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.add(Setting(key="twofa_enabled", value="true"))
        db.session.commit()
    saved = os.environ.pop("TWOFA_ENABLED", None)
    yield
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.commit()
    if saved is not None:
        os.environ["TWOFA_ENABLED"] = saved


@pytest.fixture()
def victim(client, app, twofa_on):
    """建一个**已绑定 2FA 的超管**，并返回登录后的客户端（仅密码，未过第二因素）。"""
    import twofa
    from backup_settings import encrypt_secret
    uname = "vic_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
        uid = u.id
        # 直接落一条「已确认生效」的绑定（等价于用户走完 enroll+confirm）
        row = UserTwoFactor(user_id=uid,
                            secret_enc=encrypt_secret(twofa.generate_secret()),
                            enabled=True)
        db.session.add(row)
        db.session.commit()
        before = (row.secret_enc, row.enabled)
    d = client.get("/api/csrf").get_json() or {}
    r = client.post("/api/auth/login",
                    json={"username": uname, "password": PASSWORD},
                    headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""})
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    return {"client": client, "app": app, "uid": uid, "uname": uname, "before": before}


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def test_password_only_session_cannot_reset_twofa(victim):
    """核心断言：仅密码会话必须被 401 拦住，且**绑定状态零变化**。"""
    c = victim["client"]
    r = c.post("/api/auth/2fa/enroll", json={}, headers=_csrf(c))
    assert r.status_code == 401, (
        "2FA 闸门失守：仅密码会话竟能重置 2FA（HTTP %s）——第二因素被静默解除"
        % r.status_code)
    with victim["app"].app_context():
        # ⚠️ 只能按 user_id 查：pytest 库是**全 session 共享**的，
        # `db.session.get(UserTwoFactor, 1)` 会命中别的用例留下的 id=1 行，
        # 产出「状态被污染」的假红（本项目已踩过的坑）。
        row = db.session.query(UserTwoFactor).filter_by(
            user_id=victim["uid"]).first()
        assert row is not None, "绑定行不见了，用例前置失效"
        assert (row.secret_enc, row.enabled) == victim["before"], (
            "虽然接口返回了错误码，但数据库里的 2FA 绑定已被改动 —— 状态被污染")


def test_twofa_gate_blocks_admin_surface_for_password_only_session(victim):
    """闸门是**会话级**的：仅密码会话连后台页面也不该拿到。"""
    c = victim["client"]
    r = c.get("/admin/")
    assert r.status_code in (401, 302, 403), (
        "仅密码会话竟能访问后台（HTTP %s）" % r.status_code)
    # 不能是 200 且返回可编辑的设置页
    assert "twofa" not in (r.get_data(as_text=True) or "").lower()[:2000] or r.status_code != 200


def test_enroll_refuses_reset_even_when_global_gate_is_off(victim, app):
    """**纵深防御**场景：全局开关 `twofa_enabled=false`（出厂默认）时闸门整体休眠。

    此时 `before_request` 拦不住任何东西，唯一还能挡住「静默解除第二因素」的
    就是 `twofa.enroll()` 自身的证明要求。`enroll()` 的设计意图是：
    **已生效**的绑定必须先证明持有当前第二因素才能重置。

    这条测试把该意图钉死——否则「闸门关着 + 攻击者只有密码」= 2FA 被静默解除，
    而用户在界面上仍看到「已启用」。
    """
    import twofa
    # 把全局开关关掉（模拟出厂默认 / 运维未开启）
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.commit()
    with app.app_context():
        saved = os.environ.pop("TWOFA_ENABLED", None)
    try:
        with app.app_context():
            u = db.session.get(User, victim["uid"])
            status, secret, uri = twofa.enroll(u)   # 未提供 code
            assert status != "ok", (
                "全局开关关闭时，仅凭密码就能重置已生效的 2FA（返回 %r）—— "
                "第二因素被静默解除，用户界面却仍显示已启用" % status)
            row = db.session.query(UserTwoFactor).filter_by(
                user_id=victim["uid"]).first()
            assert (row.secret_enc, row.enabled) == victim["before"], (
                "重置虽被拒绝返回，但绑定状态已被改动")
    finally:
        if saved is not None:
            os.environ["TWOFA_ENABLED"] = saved


def test_disabled_flag_means_no_false_sense_of_security(app, client, victim):
    """反向风险：全局开关关着时，用户仍能绑定 2FA 并在界面看到「已启用」，
    却**永远不会被要求输入**——这是「以为有 2FA，实际没有」。

    本测试只**记录当前行为**（不强制它必须是什么），把真实语义钉住，
    避免以后改闸门时无声改变安全属性。
    """
    import twofa
    with app.app_context():
        db.session.query(Setting).filter_by(key="twofa_enabled").delete(
            synchronize_session=False)
        db.session.commit()
        row = db.session.query(UserTwoFactor).filter_by(
            user_id=victim["uid"]).first()
        assert twofa.is_active(victim["uid"]) is True, "前置：账号确实已启用 2FA"
        # 开关关闭时 is_active 仍为 True（绑定状态与闸门开关是两个独立概念）
        assert row.enabled is True
    with contextlib.suppress(Exception):
        os.environ.pop("TWOFA_ENABLED", None)
