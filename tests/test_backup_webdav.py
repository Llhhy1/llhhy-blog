"""备份 WebDAV 可写性探测 + 配置刷新守卫（v3.25.13）。

**起因是线上一起真实故障**：后台「WebDAV 云盘」填好了地址/用户名/应用密码，
配置页显示「✅ 已配置」，但备份**每天失败**。两个原因叠加：

1. 填的是坚果云 WebDAV **根目录** `https://dav.jianguoyun.com/dav/`。PROPFIND 返回
   207（认证其实是好的），但 `current-user-privilege-set` 里**只有 `<d:read/>`**
   —— 根目录只读，PUT 一律 404。
2. 页面把失败显示成 `命令退出码 22` —— 既看不出 404 还是 401，也看不出是地址错、
   凭据错还是目录只读，**等于没法自助排障**（curl 早就把原因写在 stderr 里）。

另一个同批发现：`apply_env()` 只在 `backup.py` **被导入时**跑一次，而后台保存只作用于
「处理保存请求的那个 worker」。gunicorn 多 worker 下，落到别的 worker 的备份任务仍用
**导入那一刻**的旧值，页面却写着「保存后立即生效（无需重启）」。

本文件把这三件事都钉死：
  - 错误信息**带 stderr** 且翻译成人话（根目录只读要指出来）；
  - `probe_webdav()` 能区分 ok / auth_failed / **not_writable** / missing / unreachable；
  - `create_backup()` 与 `probe_webdav()` 都会**重新**读一次后台配置（不靠导入时机）。
"""
import contextlib
import os
import secrets
import subprocess

import pytest

from models import db, User, Setting, ROLE_SUPER

PASSWORD = "Passw0rd!23"

BACKUP_KEYS = (
    "backup_dir", "backup_retention_days",
    "backup_oss_bucket", "backup_oss_region", "backup_oss_endpoint",
    "backup_oss_key", "backup_oss_secret", "backup_oss_prefix",
    "backup_scp_host", "backup_scp_dir", "backup_scp_port", "backup_scp_key",
    "backup_webdav_url", "backup_webdav_user", "backup_webdav_pass",
)

# 坚果云根目录 PROPFIND 的真实形态（2026-10-06 线上抓的）：207 + 只有 <d:read/>
_READ_ONLY_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:multistatus xmlns:d="DAV:"><d:response><d:href>/dav/</d:href>'
    "<d:propstat><d:prop><d:current-user-privilege-set>"
    "<d:privilege><d:read/></d:privilege>"
    "</d:current-user-privilege-set></d:prop>"
    "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>"
)
_WRITABLE_BODY = _READ_ONLY_BODY.replace("<d:read/>", "<d:read/><d:write/>")


def _r():
    return secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _clean_backup_settings(app):
    """pytest 库是全 session 共享的，备份键同样要前后清干净。

    不清会出**假红**：上一条用例把 `backup_webdav_url` 留在库里，下一条「未配置」
    的断言就挂了 —— 而那种红看起来像是我改坏了 backup.py。
    """
    def _wipe():
        with app.app_context():
            db.session.query(Setting).filter(Setting.key.in_(BACKUP_KEYS)).delete(
                synchronize_session=False)
            db.session.commit()
    _wipe()
    yield
    _wipe()


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.get(k) for k in (
        "BACKUP_DIR", "BACKUP_RETENTION_DAYS", "BACKUP_WEBDAV_URL",
        "BACKUP_WEBDAV_USER", "BACKUP_WEBDAV_PASS")}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


def _set_db(app, **kv):
    with app.app_context():
        for k, v in kv.items():
            row = Setting.query.filter_by(key=k).first()
            if row:
                row.value = v
            else:
                db.session.add(Setting(key=k, value=v))
        db.session.commit()


class _FakeProc:
    def __init__(self, body, code):
        # curl -w "\n%{http_code}" 的输出形态：正文 + "\n" + 状态码
        self.stdout = ("%s\n%s" % (body, code)).encode("utf-8")
        self.returncode = 0
        self.stderr = b""


@pytest.fixture()
def fake_curl(monkeypatch):
    """拦掉真正的 curl：把 (命令, 返回体, 状态码) 交给用例控制。"""
    import backup
    seen = {}

    def _run(cmd, **kw):
        seen["cmd"] = cmd
        return _FakeProc(seen.get("body", ""), seen.get("code", "207"))

    monkeypatch.setattr(backup.subprocess, "run", _run)
    return seen


# ---------- 1. 错误信息要能自助排障 ----------

def test_cmd_err_includes_curl_stderr():
    """退出码 22 只是「curl 失败了」，原因在 stderr —— 必须带出来。"""
    import backup
    e = subprocess.CalledProcessError(
        22, ["curl", "-T", "a.zip"],
        stderr=b"curl: (22) The requested URL returned error: 404")
    msg = backup._cmd_err(e)
    assert "22" in msg
    assert "404" in msg


def test_webdav_hint_points_at_read_only_root():
    """「根目录只读」是坚果云的高频坑，错误文案必须直接指出来。"""
    import backup
    msg = backup._webdav_hint("命令退出码 22：curl: (22) The requested URL returned error: 404")
    assert "只读" in msg and "子目录" in msg


def test_webdav_hint_leaves_unrelated_errors_alone():
    """不是 4xx/22 的错误别硬套提示（否则真因被噪音盖住）。"""
    import backup
    assert backup._webdav_hint("连接超时") == "连接超时"


# ---------- 2. probe_webdav 分得清「能读不能写」 ----------

def test_probe_detects_read_only_root(app, fake_curl):
    """线上真实故障：207 + 只有 <d:read/> —— 认证没问题，但备份必失败。"""
    import backup
    # ⚠️ 必须在 app_context 里调：`read_setting_db()` 脱离上下文会退回 sqlite3
    # 直连 `myblog/data/blog.db`（真实库），读不到测试库的值 —— 不包一层会得到假红。
    with app.app_context():
        _set_db(app, backup_webdav_url="https://dav.jianguoyun.com/dav/",
                backup_webdav_user="me@example.com")
        fake_curl["body"] = _READ_ONLY_BODY
        fake_curl["code"] = "207"
        level, msg = backup.probe_webdav()
    assert level == "not_writable"
    assert "只读" in msg


def test_probe_ok_when_write_privilege_present(app, fake_curl):
    import backup
    with app.app_context():
        _set_db(app, backup_webdav_url="https://dav.jianguoyun.com/dav/blogbackup",
                backup_webdav_user="me@example.com")
        fake_curl["body"] = _WRITABLE_BODY
        fake_curl["code"] = "207"
        level, _msg = backup.probe_webdav()
    assert level == "ok"


def test_probe_auth_failed(app, fake_curl):
    import backup
    with app.app_context():
        _set_db(app, backup_webdav_url="https://dav.jianguoyun.com/dav/blogbackup",
                backup_webdav_user="me@example.com")
        fake_curl["code"] = "401"
        level = backup.probe_webdav()[0]
    assert level == "auth_failed"


def test_probe_missing_directory(app, fake_curl):
    import backup
    with app.app_context():
        _set_db(app, backup_webdav_url="https://dav.jianguoyun.com/dav/nope",
                backup_webdav_user="me@example.com")
        fake_curl["code"] = "404"
        level = backup.probe_webdav()[0]
    assert level == "missing"


def test_probe_unconfigured(app, fake_curl):
    import backup
    with app.app_context():
        assert backup.probe_webdav()[0] == "unconfigured"


def test_probe_rejects_non_http_scheme(app, fake_curl):
    """`curl -T file://...` 是任意本地路径写入 —— 地址必须是 http(s)。"""
    import backup
    with app.app_context():
        _set_db(app, backup_webdav_url="file:///etc/cron.d")
        level = backup.probe_webdav()[0]
    assert level == "unreachable"
    assert "cmd" not in fake_curl       # 根本没发起请求


# ---------- 3. 后台配置刷新：不靠「导入那一刻」 ----------

def test_refresh_env_picks_up_new_db_value(app, monkeypatch):
    """多 worker 下救命的一条：模块早就导入过了，仍要读到最新后台配置。"""
    import backup
    with app.app_context():
        _set_db(app, backup_dir="/tmp/llhhy_backup_probe", backup_retention_days="7")
        backup._refresh_env()
        root, days = backup.BACKUP_ROOT, backup.RETENTION_DAYS
    assert root == "/tmp/llhhy_backup_probe"
    assert days == 7


def test_probe_webdav_reads_fresh_config(app, fake_curl):
    """探测也要先刷新：否则刚保存的地址测不到（页面刚填完点测试 = 最常见路径）。"""
    import backup
    fake_curl["body"] = _WRITABLE_BODY
    fake_curl["code"] = "207"
    with app.app_context():
        assert backup.probe_webdav()[0] == "unconfigured"          # 未配置
        _set_db(app, backup_webdav_url="https://dav.jianguoyun.com/dav/blogbackup")
        level = backup.probe_webdav()[0]                           # 保存后立刻可用
    assert level == "ok"


# ---------- 4. 后台「保存并测试 WebDAV」按钮 ----------

@pytest.fixture()
def super_client(client, app):
    uname = "su_" + _r()
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    d = client.get("/api/csrf").get_json() or {}
    assert client.post("/api/auth/login",
                       json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}
                       ).status_code == 200
    return client


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def test_backup_settings_has_test_webdav_button(super_client):
    html = super_client.get("/admin/backup-settings").get_data(as_text=True)
    assert 'value="test_webdav"' in html


def test_test_webdav_reports_read_only(super_client, app, monkeypatch, fake_curl):
    """填完根目录当场知道「只读」，而不是第二天备份失败才发现。"""
    import backup
    fake_curl["body"] = _READ_ONLY_BODY
    fake_curl["code"] = "207"
    r = super_client.post("/admin/backup-settings", data={
        "action": "test_webdav",
        "backup_webdav_url": "https://dav.jianguoyun.com/dav/",
        "backup_webdav_user": "me@example.com",
        "backup_webdav_pass": "app-password",
        "backup_retention_days": "14",
    }, headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code == 200
    assert "只读" in r.get_data(as_text=True)
    # 顺带证明：配置确实落库了（测试前先保存）
    with app.app_context():
        row = Setting.query.filter_by(key="backup_webdav_url").first()
        assert row and row.value == "https://dav.jianguoyun.com/dav/"
    assert backup is not None


def test_retention_days_invalid_reports_error(super_client, app):
    """运营手填错不该 500，也不该把错误悄悄吞掉。"""
    r = super_client.post("/admin/backup-settings", data={
        "action": "save", "backup_retention_days": "两周",
    }, headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code == 200
    assert "保留天数必须是数字" in r.get_data(as_text=True)


def test_save_persists_and_masks_secret(super_client, app):
    """密码字段必须加密落库，绝不出现明文。"""
    r = super_client.post("/admin/backup-settings", data={
        "action": "save",
        "backup_webdav_url": "https://dav.jianguoyun.com/dav/blogbackup",
        "backup_webdav_user": "me@example.com",
        "backup_webdav_pass": "super-secret-pw",
        "backup_retention_days": "14",
    }, headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        row = Setting.query.filter_by(key="backup_webdav_pass").first()
        assert row and row.value.startswith("bkenc$")
        assert "super-secret-pw" not in (row.value or "")
