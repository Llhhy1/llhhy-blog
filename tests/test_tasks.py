"""后台长任务基建测试（v3.23.0 #48）。

钉死的是「把它挪出请求路径」这件事的关键不变量：
- 任务真的在后台跑完，且结果/异常都落进状态文件。
- **同名任务不并发**（备份连跑两次会撞同一批文件）。
- **状态存在文件里**：4 个 worker 是独立进程，内存 dict 会「查无此任务」——
  本测试通过直接读 `status()` 间接覆盖（它读的就是 data/tasks/<id>.json）。
- 任务 id 只接受字母数字（防路径穿越读到别的 json）。
"""
import contextlib
import os
import secrets
import threading
import time

import pytest

import tasks as tasks_mod
from models import db, User, ROLE_SUPER

PASSWORD = "Passw0rd!23"


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """把任务目录指到**临时目录**并清空（含锁文件），同时清限流计数。

    **必须**做两件事：
    1. `DATA_DIR` 是固定的 `myblog/data`（conftest 只覆盖了 DATABASE_URL），
       不重定向的话任务文件/锁会写进**真实开发数据目录**——「测试污染开发库」
       正是本项目 v3.18.5 修过的 P0 类型，不能重犯。
    2. 任务锁是**文件锁**且跨用例残留，不清理会让「同名任务」用例在第二轮
       跑的时候随机翻红。
    """
    task_dir = tmp_path / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tasks_mod, "_task_dir", lambda: str(task_dir))

    def _wipe():
        for fn in os.listdir(str(task_dir)):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(str(task_dir), fn))
        with contextlib.suppress(Exception):
            from utils.net import _RATE
            _RATE.clear()

    _wipe()
    yield
    _wipe()


def _wait(tid, timeout=15.0):
    """轮询等任务终态（done / error）。"""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = tasks_mod.status(tid)
        if last and last.get("state") in ("done", "error"):
            return last
        time.sleep(0.05)
    return last


def _mksuper():
    """/admin/backup 是 @super_required，故这里必须建超管。"""
    u = User(username="utask_" + secrets.token_hex(4),
             email="utask_" + secrets.token_hex(4) + "@example.com",
             role=ROLE_SUPER, must_change_password=False)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    return u.id, u.username


def _login(client, username):
    csrf = (client.get("/api/csrf").get_json() or {}).get("csrf_token") or ""
    return client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                       headers={"X-CSRF-Token": csrf})


def test_submit_runs_and_records_result(app, client):
    with app.app_context():
        tid, err = tasks_mod.submit("t_ok", lambda: 42)
    assert err is None, "首次提交不应被防重入挡下"
    assert tid
    st = _wait(tid)
    assert st is not None and st["state"] == "done", st
    assert st["result"] == 42


def test_exception_is_captured_not_raised(app, client):
    """任务只做尽力而为：异常必须落进状态文件，绝不抛回请求线程。"""
    def boom():
        raise RuntimeError("boom-42")

    with app.app_context():
        tid, err = tasks_mod.submit("t_err", boom)
    assert err is None
    st = _wait(tid)
    assert st["state"] == "error", st
    assert "boom-42" in (st.get("error") or ""), st


def test_same_name_not_concurrent(app, client):
    """同名任务必须串行——备份连跑两次会撞同一批文件。"""
    gate = threading.Event()
    with app.app_context():
        tid1, err1 = tasks_mod.submit("t_lock", lambda: gate.wait(10))
    assert err1 is None and tid1
    with app.app_context():
        tid2, err2 = tasks_mod.submit("t_lock", lambda: None)
    assert tid2 is None and err2, "同名任务进行中时，第二次提交必须被挡下"
    gate.set()
    st = _wait(tid1)
    assert st["state"] == "done"


def test_different_names_can_coexist(app, client):
    with app.app_context():
        tid_a, err_a = tasks_mod.submit("t_x", lambda: 1)
        tid_b, err_b = tasks_mod.submit("t_y", lambda: 2)
    assert err_a is None and err_b is None
    assert tid_a != tid_b


def test_status_rejects_traversal():
    """task id 只接受字母数字，挡住 ../ 之类的路径穿越。"""
    assert tasks_mod.status("../evil") is None
    assert tasks_mod.status("") is None
    assert tasks_mod.status("a/b") is None
    assert tasks_mod.status("nonexistent123") is None


def test_status_endpoint_requires_login(client):
    resp = client.get("/admin/task/abc123")
    assert resp.status_code in (302, 401, 403)


def test_backup_page_renders_task_banner(app, client):
    """我改了 admin/backup.html（加了轮询横幅）——确保模板仍能编译并渲染出横幅。"""
    with app.app_context():
        _uid, uname = _mksuper()
    assert _login(client, uname).status_code == 200
    resp = client.get("/admin/backup?task=abc123")
    assert resp.status_code == 200
    assert "bk-task" in resp.get_data(as_text=True), "带 task 参数时应渲染出轮询横幅"


def test_status_endpoint_404_for_unknown(app, client):
    with app.app_context():
        _uid, uname = _mksuper()
    assert _login(client, uname).status_code == 200
    resp = client.get("/admin/task/doesnotexist1")
    assert resp.status_code == 404
    assert resp.get_json()["state"] == "unknown"
