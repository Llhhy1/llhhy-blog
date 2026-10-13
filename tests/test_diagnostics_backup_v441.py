# -*- coding: utf-8 -*-
"""v4.4.1 修复：后台体检「数据备份」误报「未找到备份文件」。

**根因（生产实证）**：备份实际有三处写入方，而体检只猜了其中一条**恒不存在**的路径：

| 写入方 | 实际路径（服务器） |
|---|---|
| `update.sh` 部署前直拷 | `/www/wwwroot/myblog/data/backup`（**backup 单数**，141 个文件） |
| `backup.py` + 每天 4 点 cron | `/www/wwwroot/backups`（37 个文件，含 `blog_backup_*.zip`） |
| 后台「数据备份」配置 / `BACKUP_DIR` | 由用户填 |

旧实现的三处错：① 目录名写成 `data/backups`（复数）；② 从不看 `BACKUP_ROOT`
（定时任务真正落盘的地方）；③ 用 `REPO_ROOT/myblog/...` 拼路径，而线上代码直接铺在
站点根、没有 `myblog/` 这层 → 路径恒不存在 → 明明每天都在备份却报「没有数据备份」。

⚠️ 所有调用必须在 `app.app_context()` 内：`read_setting_db()` 脱离上下文会
**直连真实库** `myblog/data/blog.db`（不是"读不到"，是读错库）。
"""
import os
import time

import pytest

from models import db, Setting

_FAKE_ZIP = b"PK\x03\x04fake"


@pytest.fixture(autouse=True)
def _clean_backup_settings(app):
    """测试库是全 session 共享的：清掉 backup_* 设置，避免被前序用例带偏。"""
    def _wipe():
        with app.app_context():
            db.session.query(Setting).filter(
                Setting.key.like("backup%")).delete(synchronize_session=False)
            db.session.commit()
    _wipe()
    yield
    _wipe()


def _mk(path, name, age_days=0.0):
    os.makedirs(path, exist_ok=True)
    p = os.path.join(path, name)
    with open(p, "wb") as f:
        f.write(_FAKE_ZIP)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def _item(res, label):
    labels = [i["label"] for i in res["items"]]
    for it in res["items"]:
        if it["label"] == label:
            return it
    raise AssertionError("体检结果里没有 %r，实际有：%s" % (label, labels))


def _check(app):
    from diagnostics import check_backup
    with app.app_context():
        return check_backup()


def test_定时任务目录的备份能被识别(app, tmp_path, monkeypatch):
    """v4.4.1 核心回归：`BACKUP_ROOT`（定时任务目录）里的备份必须被找到。

    旧实现从不查这个目录 → 本用例在旧代码下必红。
    """
    import backup
    timer_dir = tmp_path / "backups"
    _mk(str(timer_dir), "blog_backup_20260101_040000.zip")
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(timer_dir))
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path / "no-code-here"))

    res = _check(app)
    assert res["status"] != "error", res["notes"]
    recent = _item(res, "最近备份")
    assert "未找到" not in recent["value"], "仍报未找到：%s" % recent["value"]
    assert "blog_backup_20260101_040000.zip" in recent["value"]
    assert "定时任务目录" in recent["value"], "应标注来源：%s" % recent["value"]


def test_部署备份目录是_backup单数(app, tmp_path, monkeypatch):
    """v4.4.1 回归：部署备份目录是 `data/backup`（单数，update.sh 实际用的）。

    旧实现写的是 `data/backups`（复数）→ 本用例在旧代码下必红。
    """
    import backup
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(tmp_path / "absent"))
    deploy = tmp_path / "data" / "backup"
    _mk(str(deploy), "blog_20260102_120000.db")
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path))

    recent = _item(_check(app), "最近备份")
    assert "未找到" not in recent["value"], recent["value"]
    assert "blog_20260102_120000.db" in recent["value"]
    assert "部署备份目录" in recent["value"]


def test_跨目录取最新且两个目录都列出(app, tmp_path, monkeypatch):
    """两个来源都在时：取 mtime 最新的那个，且「本地备份目录」两处都列出来。"""
    import backup
    timer_dir = tmp_path / "backups"
    _mk(str(timer_dir), "old_20260101.zip", age_days=9)     # 旧的（超过 7 天 → warn）
    deploy = tmp_path / "data" / "backup"
    _mk(str(deploy), "new_20260110.db")                     # 新的
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(timer_dir))
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path))

    res = _check(app)
    recent = _item(res, "最近备份")
    assert "new_20260110.db" in recent["value"], recent["value"]
    assert recent["level"] == "ok"
    dirs = _item(res, "本地备份目录")
    assert str(timer_dir) in dirs["value"] and str(deploy) in dirs["value"]


def test_确实一个备份都没有时才报未找到(app, tmp_path, monkeypatch):
    """反向守卫：目录存在但里面没有备份文件 → 仍要报「未找到备份文件」。

    只断言「该报警的报了」不够；不钉住这一条，修宽了会变成永远说 OK 的假体检。
    """
    import backup
    empty = tmp_path / "backups"
    os.makedirs(str(empty), exist_ok=True)
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(empty))
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path / "no-code-here"))

    res = _check(app)
    recent = _item(res, "最近备份")
    assert "未找到备份文件" in recent["value"]
    assert res["status"] == "warn"


def test_配置了但不存在的目录要点出来(app, tmp_path, monkeypatch):
    """后台填了 backup_dir 但目录不存在 → 必须显式报「目录缺失」，不能静默忽略。"""
    import backup
    timer_dir = tmp_path / "backups"
    _mk(str(timer_dir), "ok_20260101.zip")
    missing = tmp_path / "nowhere"
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(timer_dir))
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path / "no-code-here"))
    monkeypatch.setenv("BACKUP_DIR", str(missing))

    res = _check(app)
    labels = [i["label"] for i in res["items"]]
    assert "目录缺失" in labels, "配置了但不存在的目录未被点出：%s" % labels
    miss = _item(res, "目录缺失")
    assert str(missing) in miss["value"]


def test_非备份文件不被误认成备份(app, tmp_path, monkeypatch):
    """目录里的其它文件（如 manifest_*.json、-wal）不算备份。"""
    import backup
    timer_dir = tmp_path / "backups"
    os.makedirs(str(timer_dir), exist_ok=True)
    _mk(str(timer_dir), "manifest_20260101.json")
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(timer_dir))
    monkeypatch.setattr("diagnostics._CODE_DIR", str(tmp_path / "no-code-here"))

    recent = _item(_check(app), "最近备份")
    assert "未找到备份文件" in recent["value"], recent["value"]
