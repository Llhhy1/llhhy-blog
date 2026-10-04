"""备份自动巡检守卫（v3.25.2）。

**为什么要有这个功能**：`backup verify` 一直只能手动跑，于是「备份能不能恢复」
这个属性在真出事之前**永远是未知的** —— 而磁盘故障那天正是最需要备份的一天。

**判据设计上的两个刻意选择**（都是被「假安全感」逼出来的）：

1. **三态而非布尔**：`ok` / `bad` / `empty` / `never` 四态。绝不用单个 `ok` 标志 ——
   「从未巡检」和「巡检通过」语义完全相反，合并会让「还没查过」被读成「查过了没问题」。
2. **零新表**：结果落 `data/backup_verify.json`。4 个 gunicorn worker 是独立进程，
   内存态彼此不可见 —— 与 `tasks.py` 的状态文件同思路。
"""
import json
import os
import zipfile

import pytest

from myblog import backup as B


def _make_archive(path, *, files=None, manifest=None, bad_sha=False):
    """造一个测试用备份包。files 为 None 时放一个最小可用集。

    `bad_sha=True` → manifest 里写**错误的 sha256**，模拟「内容被篡改 / 比特腐烂」。
    这才是 verify 真正能检出的那种损坏。**别用「包里多一个 manifest 没声明的
    文件」当损坏期望** —— 那对恢复无害，verify 也不管它（第一版测试就是这么
    写错的：造了个多余文件，断言 bad，结果 verify 正确地返回 ok）。
    """
    if files is None:
        files = {"data/blog.db": b"SQLite format 3\x00" + b"x" * 64}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        items = manifest if manifest is not None else {
            "created_at": "2026-10-02T03:00:00",
            "app_version": "3.25.1",
            "files": [
                {"path": rel, "size": len(data),
                 "sha256": ("0" * 64) if bad_sha
                 else __import__("hashlib").sha256(data).hexdigest()}
                for rel, data in files.items()
            ],
        }
        for rel, data in files.items():
            zf.writestr(rel, data)
        zf.writestr("manifest.json", json.dumps(items, ensure_ascii=False))


@pytest.fixture()
def backup_root(tmp_path, monkeypatch):
    """把 BACKUP_ROOT / DATA_DIR 指到 tmp。

    ⚠️ 必须两个都指走：conftest 只覆盖 DATABASE_URL，`DATA_DIR` 在模块导入时
    就被解析成 `myblog/data` 了 —— 不覆盖就会让测试写进开发库（已踩过一次）。
    """
    root = tmp_path / "backups"
    root.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(B, "BACKUP_ROOT", str(root))
    monkeypatch.setattr(B, "DATA_DIR", str(data))
    return root, data


# ---------- 核心行为 ----------

def test_verify_latest_ok(backup_root):
    root, _ = backup_root
    for ts in ("20261001_030000", "20261002_030000"):
        _make_archive(root / ("blog_backup_%s.zip" % ts))
    r = B.verify_latest()
    assert r["status"] == "ok"
    assert r["checked"] == 2 and r["ok_count"] == 2 and r["bad_count"] == 0
    assert "均可恢复" in r["message"]


def test_verify_latest_detects_corruption(backup_root):
    """**这一条是这个功能存在的全部意义** —— 坏包必须被「响」地报出来。"""
    root, _ = backup_root
    _make_archive(root / "blog_backup_20261001_030000.zip")
    _make_archive(root / "blog_backup_20261002_030000.zip", bad_sha=True)
    r = B.verify_latest()
    assert r["status"] == "bad"
    assert r["bad_count"] == 1
    assert r["bad_items"] and "20261002" in r["bad_items"][0]["name"]


def test_verify_latest_empty_is_not_ok(backup_root):
    """**没有备份 ≠ 一切正常**。空目录必须报 empty，绝不能落到 ok。"""
    r = B.verify_latest()
    assert r["status"] == "empty"
    assert r["checked"] == 0
    assert "没有任何备份包" in r["message"]


def test_verify_latest_respects_keep(backup_root):
    """只巡检最近 keep 个 —— 全量读包算 SHA256 很贵，时间不能白花。"""
    root, _ = backup_root
    for i in range(1, 6):
        _make_archive(root / ("blog_backup_2026100%d_030000.zip" % i))
    r = B.verify_latest(keep=2)
    assert r["checked"] == 2


def test_one_bad_package_does_not_abort_run(backup_root):
    """单包校验抛异常不应中断整轮 —— 否则一个坏包就让人看不到其余包的状态。"""
    root, _ = backup_root
    _make_archive(root / "blog_backup_20261001_030000.zip")

    real_verify = B.verify
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if "20261002" in path:
            raise RuntimeError("模拟校验异常")
        return real_verify(path)

    _make_archive(root / "blog_backup_20261002_030000.zip")
    orig, B.verify = B.verify, flaky
    try:
        r = B.verify_latest(keep=2)
    finally:
        B.verify = orig
    assert calls["n"] == 2                      # 两个都尝试了，没被第一个异常打断
    assert r["bad_count"] == 1
    assert "校验过程异常" in r["bad_items"][0]["reason"]


# ---------- 状态落盘与读取 ----------

def test_state_persisted_and_readable(backup_root):
    root, data = backup_root
    _make_archive(root / "blog_backup_20261002_030000.zip")
    B.verify_latest()
    p = data / "backup_verify.json"
    assert p.exists(), "巡检结果必须落盘（worker 是独立进程，内存态不可见）"
    st = B.read_verify_state()
    assert st["status"] == "ok"
    assert st["checked_at"]


def test_read_verify_state_never_raises(backup_root):
    """文件不存在 / 内容损坏都返回「从未巡检」而不是抛异常 ——
    后台模板要的是「有没有问题」，不是「有没有数据」。"""
    _root, data = backup_root
    assert B.read_verify_state()["status"] == "never"
    (data / "backup_verify.json").write_text("{ 坏掉的 json", encoding="utf-8")
    assert B.read_verify_state()["status"] == "never"


def test_read_verify_state_fills_missing_keys(backup_root):
    """手工塞进来的残缺文件也要能读 —— 缺 key 时补默认值，不让模板 KeyError。"""
    _root, data = backup_root
    (data / "backup_verify.json").write_text('{"status":"ok"}', encoding="utf-8")
    st = B.read_verify_state()
    for k in ("checked_at", "checked", "ok_count", "bad_count", "bad_items", "message"):
        assert k in st, "缺 key: %s" % k


# ---------- 挂载点 ----------

def test_scheduler_calls_verify_latest(backup_root):
    """每日定时循环里必须真的调了巡检 —— 否则「自动」只是文档里的一句话。"""
    import inspect
    src = inspect.getsource(_app_module())
    assert "verify_latest" in src, "_start_scheduler 里没有调用 verify_latest"
    assert "_last_verify_day" in src, "巡检没有按天去重（会每 60s 跑一次）"


def _app_module():
    import importlib
    return importlib.import_module("app")


def test_backup_page_shows_verify_state(backup_root):
    """后台备份页要把巡检状态显示出来 —— 巡检跑完没人看等于没跑。"""
    import pathlib
    tpl = pathlib.Path(__file__).resolve().parent.parent / "myblog" / "templates" / "admin" / "backup.html"
    src = tpl.read_text(encoding="utf-8")
    assert "verify_state" in src
    for st in ("ok", "bad", "empty"):
        assert "'%s'" % st in src, "模板未处理 %s 状态" % st


def test_backup_route_passes_verify_state():
    """路由必须把 verify_state 传进模板，否则模板里的变量是 Undefined。"""
    import inspect
    src = inspect.getsource(
        __import__("admin.settings", fromlist=["backup"]).backup)
    assert "verify_state=" in src
    assert "read_verify_state()" in src


def test_manual_verify_uses_background_task():
    """手动巡检必须走后台任务 —— 同步跑会占住 gunicorn 并发槽
    （v3.23.0 #48 修过「立即备份」同一个坑）。"""
    import inspect
    mod = __import__("admin.settings", fromlist=["backup"])
    src = inspect.getsource(mod.backup)
    assert 'action == "verify_now"' in src
    assert 'submit("backup-verify"' in src


def test_no_zip_slash_in_manifest_check(tmp_path):
    """verify 的路径白名单仍然生效（巡检只是复用它，不放松校验）。"""
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "files": [{"path": "../../etc/passwd", "size": 1, "sha256": "x"}]}))
    ok, msg = B.verify(str(p))
    assert not ok
    assert "非法路径" in msg or "缺少文件" in msg


def test_state_file_not_written_into_repo_data_dir(backup_root):
    """巡检状态文件落在 DATA_DIR —— 测试里 monkeypatch 后不应碰真实 myblog/data。"""
    _root, data = backup_root
    real_data = os.path.join(os.path.dirname(B.__file__), "data")
    assert str(data) != real_data
