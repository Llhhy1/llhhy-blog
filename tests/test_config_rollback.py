"""配置快照与回滚（v3.25.2）。

**这个功能要解决什么**：`Setting` 有 65 项配置、各处可改，`log_audit` 记了
「谁改的」但不记「改之前是什么值」—— 改错了只能凭记忆手改回去。

**测试里最重要的两类断言**（都不是功能正确性，而是安全不变量）：

1. **`detail` 里绝不出现配置值**。`detail` 会进审计列表页、CSV 导出、被超管
   在屏幕上看到 —— 把值写进去等于把凭据抄进一份可导出、可截图的日志。
2. **敏感项全程是密文**。快照存 `Setting` 原始值（已是 Fernet 密文），
   回滚是「把密文写回去」，不接触明文。测试用真实的 `encrypt_secret` 验证。
"""
import json

import pytest

import config_rollback as cr
from models import AuditLog, Setting, db


@pytest.fixture(autouse=True)
def _isolate(app):
    """每个用例前后清掉本模块写的行。

    ⚠️ 测试库是**整轮共用**的一个文件（conftest 在 session 开始时建一次），
    跨用例累积。审计表尤其致命：`list_snapshots()` 断言的是「最近 N 条」，
    别的用例留下的快照会混进来 → 单独跑通过、一起跑失败。
    """
    keys = ["site_title", "site_lang", "bot_guard_threshold", "k_none", "k_empty",
            "brand_new_key", "probe_k", "backup_smtp_secret", "backup_webdav_pass",
            "never_set_key_xyz"] + ["k%d" % i for i in range(5)]
    with app.app_context():
        db.session.query(AuditLog).filter(
            AuditLog.target.in_([cr.SNAPSHOT_TARGET, cr.ROLLBACK_TARGET])
        ).delete(synchronize_session=False)
        db.session.query(Setting).filter(Setting.key.in_(keys)).delete(
            synchronize_session=False)
        db.session.commit()
    yield
    with app.app_context():
        db.session.query(AuditLog).filter(
            AuditLog.target.in_([cr.SNAPSHOT_TARGET, cr.ROLLBACK_TARGET])
        ).delete(synchronize_session=False)
        db.session.query(Setting).filter(Setting.key.in_(keys)).delete(
            synchronize_session=False)
        db.session.commit()


def _set(app, key, value):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()


def _get(app, key):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        return row.value if row else None


# ---------- 快照 ----------

def test_snapshot_captures_current_values(app):
    _set(app, "site_title", "旧标题")
    _set(app, "site_lang", "zh")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title", "site_lang"], reason="单测")
        assert sid is not None
        row = db.session.get(AuditLog, sid)
        vals = json.loads(row.payload)
        assert vals == {"site_title": "旧标题", "site_lang": "zh"}


def test_snapshot_records_none_for_missing_key(app):
    """快照里不存在的 key 记 None —— 回滚时才能「删回未设置」而不是「设成空串」。"""
    with app.app_context():
        sid = cr.snapshot_settings(["site_title", "never_set_key_xyz"])
        vals = json.loads(db.session.get(AuditLog, sid).payload)
        assert vals["never_set_key_xyz"] is None


def test_snapshot_rejects_too_many_keys(app):
    with app.app_context():
        with pytest.raises(ValueError):
            cr.snapshot_settings(["k%d" % i for i in range(300)])


# ---------- 安全不变量 ----------

def test_detail_never_contains_values(app):
    """**detail 只写摘要，绝不写值。** detail 会进 CSV 导出与审计列表页。"""
    _set(app, "smtp_password_probe", "SUPER-SECRET-123")
    with app.app_context():
        sid = cr.snapshot_settings(["smtp_password_probe"], reason="单测")
        row = db.session.get(AuditLog, sid)
        assert "SUPER-SECRET-123" not in (row.detail or "")
        assert "smtp_password_probe" not in (row.detail or ""), \
            "detail 也不该列 key 名（会让 65 项配置全貌从日志侧漏出）"


def test_snapshot_stores_ciphertext_not_plaintext(app):
    """敏感项快照里存的是**密文**，回滚全程不碰明文。"""
    import backup_settings as bs
    plain = "MY-SMTP-授权码-abc123"
    with app.app_context():
        enc = bs.encrypt_secret(plain)
    assert enc != plain and enc.startswith("bkenc$"), "前置条件：encrypt_secret 确实是密文"
    _set(app, "backup_smtp_secret", enc)
    with app.app_context():
        sid = cr.snapshot_settings(["backup_smtp_secret"])
        payload_text = db.session.get(AuditLog, sid).payload
    assert plain not in payload_text, "❌ 快照里出现了明文"
    assert enc in payload_text, "快照里应原样存着密文"


def test_rollback_does_not_decrypt(app):
    """回滚密文时不得调用解密（调用即意味着明文曾进入内存/日志）。"""
    import backup_settings as bs
    enc = bs.encrypt_secret("pw-xyz")
    _set(app, "backup_webdav_pass", enc)
    with app.app_context():
        sid = cr.snapshot_settings(["backup_webdav_pass"])
        calls = {"n": 0}
        real = bs.decrypt_secret

        def spy(v):
            calls["n"] += 1
            return real(v)
        bs.decrypt_secret = spy
        try:
            ok, _msg = cr.rollback(sid, confirm=True)
        finally:
            bs.decrypt_secret = real
    assert ok
    assert calls["n"] == 0, "回滚不该解密任何东西"
    assert _get(app, "backup_webdav_pass") == enc


# ---------- 差异预览 ----------

def test_diff_lists_only_changed_keys(app):
    _set(app, "site_title", "A")
    _set(app, "site_lang", "zh")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title", "site_lang"])
    _set(app, "site_title", "B")          # 改了
    # site_lang 不动
    with app.app_context():
        d = cr.diff_snapshot(sid)
    assert d is not None
    assert [x["key"] for x in d] == ["site_title"], "未变的项不该出现在差异里"
    assert d[0]["before"] == "A" and d[0]["now"] == "B"


def test_diff_treats_none_and_empty_as_equal(app):
    """表单没填提交上来是 ""，从未设置读出来是 None —— 语义上都是「没配」，
    不该报成差异（否则每次回滚预览都是一长串假差异，没人看得下去）。"""
    with app.app_context():
        sid = cr.snapshot_settings(["k_none", "k_empty"])
    _set(app, "k_none", "")
    with app.app_context():
        d = cr.diff_snapshot(sid)
    assert d == [], "None 与空串不应算差异，实际 %s" % d


def test_diff_returns_none_for_missing_snapshot(app):
    with app.app_context():
        assert cr.diff_snapshot(999999) is None


def test_diff_returns_none_for_non_snapshot_row(app):
    """普通审计行（没有 payload）不能被当成快照用。"""
    from audit import log_audit
    with app.app_context():
        log_audit("update", "post", 1, "改了篇文章")
        rid = db.session.query(AuditLog).order_by(AuditLog.id.desc()).first().id
        assert cr.diff_snapshot(rid) is None


# ---------- 回滚 ----------

def test_rollback_restores_values(app):
    _set(app, "bot_guard_threshold", "120")
    with app.app_context():
        sid = cr.snapshot_settings(["bot_guard_threshold"])
    _set(app, "bot_guard_threshold", "1")
    with app.app_context():
        ok, msg = cr.rollback(sid, confirm=True)
    assert ok, msg
    assert _get(app, "bot_guard_threshold") == "120"


def test_rollback_deletes_key_that_was_absent_in_snapshot(app):
    """快照里是 None（当时没这项）→ 回滚应**删除该行**，
    而不是写空串 —— 「回到代码默认值」≠「显式设成空」。"""
    with app.app_context():
        sid = cr.snapshot_settings(["brand_new_key"])
    _set(app, "brand_new_key", "后来加的")
    with app.app_context():
        ok, _ = cr.rollback(sid, confirm=True)
        assert ok
        assert Setting.query.filter_by(key="brand_new_key").first() is None


def test_rollback_requires_confirm(app):
    _set(app, "site_title", "A")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title"])
    _set(app, "site_title", "B")
    with app.app_context():
        ok, msg = cr.rollback(sid, confirm=False)
    assert not ok and "确认" in msg
    assert _get(app, "site_title") == "B", "未确认时不得动数据"


def test_rollback_takes_safety_snapshot_first(app):
    """回滚**前**必须给当前值也拍一份 —— 否则「回滚回滚」没有退路。"""
    _set(app, "site_title", "A")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title"])
    _set(app, "site_title", "B")
    with app.app_context():
        cr.rollback(sid, confirm=True)
        snaps = cr.list_snapshots(limit=10)
        # 第一条是回滚前的退路快照，值应为 B（回滚前的状态）
        top = json.loads(snaps[0].payload)
        assert top["site_title"] == "B", "退路快照应记录回滚前的值"


def test_rollback_is_audited(app):
    _set(app, "site_title", "A")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title"])
    _set(app, "site_title", "B")
    with app.app_context():
        cr.rollback(sid, confirm=True)
        r = db.session.query(AuditLog).filter_by(target=cr.ROLLBACK_TARGET).first()
        assert r is not None, "回滚本身必须留审计"
        assert str(sid) in (r.detail or ""), "审计里要指明是从哪个快照回滚的"


def test_rollback_rejects_bad_snapshot_id(app):
    with app.app_context():
        ok, msg = cr.rollback(999999, confirm=True)
    assert not ok and ("不存在" in msg or "过期" in msg)


def test_rollback_ignores_out_of_scope_keys(app):
    """只回滚被勾选的 key —— 不能顺带覆盖别的管理员在这期间的合法修改。"""
    _set(app, "site_title", "A")
    _set(app, "site_lang", "zh")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title", "site_lang"])
    _set(app, "site_title", "B")
    _set(app, "site_lang", "en")
    with app.app_context():
        ok, _ = cr.rollback(sid, keys=["site_title"], confirm=True)
    assert ok
    assert _get(app, "site_title") == "A"
    assert _get(app, "site_lang") == "en", "未勾选的项不应被回滚"


# ---------- 收口 ----------

def test_purge_keeps_recent_and_clears_old(app):
    with app.app_context():
        for i in range(5):
            _set(app, "k%d" % i, str(i))
            cr.snapshot_settings(["k%d" % i])
        n = cr.purge_snapshots(keep=2)
        assert n == 3, "应删除 3 条，实际 %d" % n
        assert cr.snapshot_count() == 2


def test_list_snapshots_newest_first(app):
    _set(app, "site_title", "A")
    with app.app_context():
        cr.snapshot_settings(["site_title"])
    _set(app, "site_title", "B")
    with app.app_context():
        cr.snapshot_settings(["site_title"])
        snaps = cr.list_snapshots(limit=10)
        vals = [json.loads(s.payload)["site_title"] for s in snaps]
        assert vals == ["B", "A"], "新的应在前，实际 %s" % vals


def test_corrupted_payload_does_not_crash_rollback(app):
    """快照内容损坏时必须**明确报错**而不是静默部分执行。"""
    _set(app, "site_title", "A")
    with app.app_context():
        sid = cr.snapshot_settings(["site_title"])
        db.session.get(AuditLog, sid).payload = "{ 这不是 json"
        db.session.commit()
        ok, msg = cr.rollback(sid, confirm=True)
    assert not ok and "损坏" in msg
    assert _get(app, "site_title") == "A", "失败时不得动数据"


def test_audit_writes_without_request_context(app):
    """**锁 v3.25.2 修掉的一个真实根因**（不是本功能的题外话）。

    `log_audit` 原先无条件 `session.get("user_id")` —— 在**无请求上下文**
    （CLI / 定时任务 / 单元测试）下抛 `RuntimeError: Working outside of
    request context`，而它位于最外层 `try` 内，异常被 `except Exception: pass`
    静默吞掉：**整条审计一条都没写，且毫无迹象**。

    表现是「配置快照功能看起来完全失效」——因为它正是从 `log_audit` 落库的。
    根因不在快照逻辑，而在审计函数；所以这条测试放在本文件守。

    **变异说明（如实记录）**：把 `if has_request_context():` 改成 `if True:`
    **这条测试不会变红** —— 那是**等价变异**：无上下文时两者都会走进内层
    `except Exception: user = None`，行为一致（双保险的预期结果）。
    本条锁的是**行为**（无请求上下文不丢审计），不是某一行实现；
    守卫与兜底任去其一，行为都仍然正确。
    """
    from audit import log_audit
    with app.app_context():
        assert not has_request_context_for_test(), "前提：本用例确实没有请求上下文"
        log_audit("update", "probe_no_ctx", 0, "无请求上下文也应写入")
        db.session.commit()
        after = db.session.query(AuditLog).filter_by(target="probe_no_ctx").count()
    assert after == 1, "无请求上下文时审计被静默丢弃了"


def has_request_context_for_test():
    from flask import has_request_context
    return has_request_context()
