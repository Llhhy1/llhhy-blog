"""FTS5 能力探测必须**只读**、且失败不得按进程永久缓存（v4.13.0）。

这条守卫挡的是两处线上实测过的后果：

① **worker 永久降级**：4 个 gunicorn worker 启动时都经 `ensure()` 探测 FTS5，
   旧实现用 `CREATE VIRTUAL TABLE _fts_probe / DROP / commit`（**写库**）当能力测试，
   抢不到写锁的 worker 拿到异常 → 结果被按进程永久缓存 → 该 worker 整个生命周期
   走 LIKE 全表扫描，而体检把它报成「SQLite 未编译 FTS5」（错判）。
   实测 `/api/search` 连打 10 次，`engine` 在 fts5(3) / like(7) 之间翻转。

② **体检误报数据库损坏**：同一份探测被 `diagnostics.check_search_index()` 惰性调用，
   等于在「只读」体检里写库；多连接同时搅动 `sqlite_master` 时，另一个连接跑
   `PRAGMA integrity_check` 会吐
   `malformed inverted index for FTS5 table main.post_fts`，notes 还建议「从备份恢复」。
   库副本隔离复现：1 个写者 60 次检查 0 假报，4 个写者 60 次里 2 次假报。

所以断言分三层：**不写库**（无 DDL/DML、sqlite_master 不变）、
**失败可重试**（窗口外必须重新探测）、**口径不混**（探测失败 ≠ 未编译）。
"""
import time

import pytest
from sqlalchemy import event

from models import db

_WRITE_VERBS = ("create", "drop", "insert", "update", "delete", "alter",
                "replace", "vacuum", "reindex", "attach", "detach")


def _clear_state():
    import fts
    fts._AVAIL = None
    fts._FAILED_AT = 0.0
    fts._FAIL_CODE = ""
    fts._FAIL_DETAIL = ""


def _table_names():
    rows = db.session.execute(db.text(
        "SELECT name FROM sqlite_master WHERE type='table'")).all()
    return {r[0] for r in rows}


def _blob(sec):
    """把 sections 的 items.value 与 notes 拼成一段可 grep 的文本。"""
    parts = [str(i.get("value")) for i in (sec.get("items") or [])]
    parts += [str(n) for n in (sec.get("notes") or [])]
    return " | ".join(parts)


@pytest.fixture(autouse=True)
def _reset_probe_state(app):  # noqa: ARG001  app 仅为确定夹具顺序：create_app 会跑 ensure() 改状态
    """每个用例前后复位 fts 的进程级缓存，避免用例互相污染。"""
    _clear_state()
    yield
    _clear_state()


# ---------- 第一层：探测不得写库 ----------

def test_probe_executes_no_write_statement(app):
    """`_probe()` 只能发 SELECT —— 一条 DDL/DML 就足以让并发的体检误报损坏。"""
    import fts
    with app.app_context():
        stmts = []

        def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001  事件签名固定
            stmts.append(statement.strip().lower())

        event.listen(db.engine, "before_cursor_execute", _capture)
        try:
            ok, code, detail = fts._probe()
        finally:
            event.remove(db.engine, "before_cursor_execute", _capture)

        assert ok is True, "测试环境应支持 FTS5，否则本用例前提不成立：%s" % detail
        writers = [s for s in stmts if s.split() and s.split()[0] in _WRITE_VERBS]
        assert not writers, (
            "fts._probe() 执行了写库语句 %r —— 能力探测必须只读："
            "写锁竞争会让输的 worker 永久降级成 LIKE 全表扫描，"
            "还会让并发跑的 PRAGMA integrity_check 误报「FTS5 索引损坏」。" % writers
        )


def test_probe_leaves_no_probe_table_behind(app):
    """旧实现会现建现删 `_fts_probe`；探测后 sqlite_master 必须一字不动。"""
    import fts
    with app.app_context():
        before = _table_names()
        assert fts.available() is True
        after = _table_names()
        assert after == before, "探测改动了 sqlite_master：新增 %s" % (after - before)
        assert "_fts_probe" not in after, "旧实现的临时探测表又出现了"


# ---------- 第二层：失败必须可重试，不能锁死进程 ----------

def test_probe_failure_is_retried_not_cached_forever(app, monkeypatch):
    """一次锁冲突不得把整个 worker 判成「永久没有 FTS5」。

    这是本版最关键的一条：旧实现 `_AVAIL = _probe()` 无条件缓存，失败一次即终身降级。
    """
    import fts
    with app.app_context():
        monkeypatch.setattr(fts, "_probe",
                            lambda: (False, fts.CODE_PROBE_FAILED, "模拟 database is locked"))
        assert fts.available() is False
        assert fts.probe_code() == fts.CODE_PROBE_FAILED
        assert "database is locked" in fts.probe_reason()

        # 窗口内不得重复探测（否则每次搜索都多一次查询）
        calls = {"n": 0}

        def _ok():
            calls["n"] += 1
            return True, "", ""

        monkeypatch.setattr(fts, "_probe", _ok)
        assert fts.available() is False, "重试窗口内应继续沿用上次的失败结果"
        assert calls["n"] == 0, "重试窗口内不应再次探测"

        # 把上次失败时刻挪到窗口之外 → 必须重新探测并恢复
        fts._FAILED_AT = time.monotonic() - fts._PROBE_RETRY_SECONDS - 1
        assert fts.available() is True, (
            "探测失败被按进程永久缓存了 —— 线上 4 个 worker 里 3 个就是这么永久降级成 "
            "LIKE 全表扫描的（且没有任何日志）。失败必须只按窗口缓存。"
        )
        assert calls["n"] == 1
        assert fts.probe_code() == "", "恢复后不应残留失败原因"
        assert fts.probe_reason() == ""


def test_success_is_cached_and_never_reprobed(app, monkeypatch):
    """成功要缓存：不能每次搜索都多打一次探测查询。"""
    import fts
    with app.app_context():
        calls = {"n": 0}

        def _ok():
            calls["n"] += 1
            return True, "", ""

        monkeypatch.setattr(fts, "_probe", _ok)
        assert fts.available() is True
        assert fts.available() is True
        assert fts.available() is True
        assert calls["n"] == 1, "成功后应缓存，实际探测了 %d 次" % calls["n"]


# ---------- 第三层：两种失败口径不得混 ----------

def test_check_search_index_blames_probe_not_missing_fts5(app, monkeypatch):
    """探测失败必须报成「探测失败 + 会自动重试」，不能报「未编译 FTS5」。"""
    import diagnostics
    import fts
    with app.app_context():
        monkeypatch.setattr(fts, "available", lambda: False)
        monkeypatch.setattr(fts, "probe_code", lambda: fts.CODE_PROBE_FAILED)
        monkeypatch.setattr(fts, "probe_reason",
                            lambda: "FTS5 探测失败（OperationalError: database is locked）")

        sec = diagnostics.check_search_index()
        blob = _blob(sec)
        assert sec["status"] == "warn"
        assert "探测失败" in blob
        assert "database is locked" in blob, "必须把真实原因原样带出来，否则无从排查"
        assert "重试" in blob
        assert "未编译" not in blob, (
            "探测失败被报成「SQLite 未编译 FTS5」—— 这会把站长指向换 SQLite 构建"
            "这种完全无关的处置动作。"
        )


def test_check_search_index_reports_missing_fts5_when_truly_missing(app, monkeypatch):
    """环境真的没有 FTS5 时，仍然要明确说「未编译」，别把两种情况一起抹平。"""
    import diagnostics
    import fts
    with app.app_context():
        monkeypatch.setattr(fts, "available", lambda: False)
        monkeypatch.setattr(fts, "probe_code", lambda: fts.CODE_NOT_COMPILED)
        monkeypatch.setattr(fts, "probe_reason",
                            lambda: "SQLite 未编译 FTS5（sqlite_compileoption_used 返回 0）")

        blob = _blob(diagnostics.check_search_index())
        assert "未编译" in blob
        assert "探测失败" not in blob
        assert "重试" not in blob, "未编译是环境事实，给「等重试」的指引是误导"


# ---------- health_score 必须能看见「为什么坏」 ----------

def test_dim_brief_carries_reason_for_bad_dimension():
    """status != ok 的维度要带上 notes 与出问题的 items；正常维度不回传（避免响应膨胀）。"""
    from mcp_diag import _dim_brief

    bad = {"key": "database", "title": "数据库健康", "status": "error",
           "items": [{"label": "完整性 PRAGMA integrity_check",
                      "value": "发现问题：malformed inverted index for FTS5 table main.post_fts",
                      "level": "error"},
                     {"label": "文件大小", "value": "4.91 MB", "level": "info"}],
           "notes": ["数据库可能存在损坏，建议从备份恢复或执行 PRAGMA repair。"]}
    brief = _dim_brief(bad)
    assert brief["status"] == "error"
    assert brief["issues"] == 1, "只数 error/warn 项，info 不计入"
    assert "malformed inverted index" in " ".join(i["value"] for i in brief["items"]), (
        "真实原因写在 items.value 里，不回传就等于让人查不到根因"
    )
    assert brief["notes"], "notes 里的处置建议也要带出来"
    assert all(i["level"] != "info" for i in brief["items"]), "只回传出问题的条目"

    ok = {"key": "disk", "title": "磁盘与 WAL", "status": "ok",
          "items": [{"label": "磁盘剩余", "value": "28.1 GB", "level": "ok"}], "notes": []}
    brief_ok = _dim_brief(ok)
    assert brief_ok["issues"] == 0
    assert "notes" not in brief_ok and "items" not in brief_ok, (
        "正常维度不应回传明细，否则 19 个维度会把响应撑大"
    )


def test_health_score_surfaces_checker_crash_reason(app, monkeypatch):
    """端到端：checker 走 except 降级时，health_score 必须把原因带出来。"""
    import diagnostics
    import mcp_diag

    fake = {
        "generated_at": "2026-10-26 00:00:00",
        "score": 95,
        "summary": {"ok": 1, "warn": 0, "error": 1},
        "issue_total": 1,
        "sections": [
            {"key": "database", "title": "数据库健康", "status": "error", "items": [],
             "notes": ["数据库检查异常：OperationalError: database is locked"]},
            {"key": "disk", "title": "磁盘与 WAL", "status": "ok", "items": [], "notes": []},
        ],
    }
    monkeypatch.setattr(diagnostics, "run_all", lambda: fake)

    out = mcp_diag.tool_health_score({})
    dims = {d["key"]: d for d in out["dimensions"]}
    assert dims["database"]["status"] == "error"
    assert dims["database"]["notes"] == [
        "数据库检查异常：OperationalError: database is locked"
    ], "瞬时错误的根因必须随评分一起返回，否则错误一消失就永久查不到"
    assert "notes" not in dims["disk"]
