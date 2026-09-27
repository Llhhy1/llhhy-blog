"""v3.21.2 审计批次 2 回归测试：权限面 / 文件系统面 / 停用而非删除。

覆盖：
  B1 备份远程后端的 argv 注入（后台 Setting 可写的值直接进 scp/curl 参数位）
  B2 恢复前快照：有上传文件时不再崩掉，且自带 manifest 因而真的可回退
  B3 插件 slug 目录穿越
  B4 `super_required` 的首登闸门（29 条裸 @super_required 路由）
  B5 删除用户 → 停用用户：不回收 rowid，不继承旧人文章，第三方绑定一并断开
  B6 读者积分：未鉴权接口限流 + 勋章并发不炸评论
"""
import io
import json
import os
import secrets
import zipfile

import pytest

from models import db, User, Post, OAuthAccount, ROLE_ADMIN, ROLE_USER


def _r():
    return secrets.token_hex(4)


# ---------- B1 备份 argv 注入 ----------

def test_scp_host_rejects_option_injection():
    import backup
    # `-oProxyCommand=<命令>` 会被 scp 当成选项，即以 gunicorn 进程身份执行任意命令
    assert backup._scp_target_ok("-oProxyCommand=touch /tmp/pwned") is False
    assert backup._scp_target_ok("root@evil-") is True          # 形态合法即可，不做 DNS
    assert backup._scp_target_ok("root@example.com") is True
    assert backup._scp_target_ok("10.0.0.5") is True            # 裸 IP 不得被误杀
    assert backup._scp_target_ok("") is False
    assert backup._scp_target_ok("a b@host.com") is False       # 空白/换行
    assert backup._scp_target_ok("root@evil.com;rm -rf /") is False


def test_webdav_url_rejects_non_http_scheme():
    import backup
    # curl -T 配 file:// = 把备份包写到任意本地路径（cron / web 目录）
    assert backup._webdav_url_ok("file:///var/spool/cron/admin") is False
    assert backup._webdav_url_ok("gopher://127.0.0.1:11211/") is False
    assert backup._webdav_url_ok("-o/etc/passwd") is False
    assert backup._webdav_url_ok("https://dav.jianguoyun.com/dav/b") is True
    assert backup._webdav_url_ok("http://127.0.0.1:8080/d") is True


def test_sync_scp_fails_without_touching_subprocess(monkeypatch):
    """非法 HOST 必须在**调用子进程之前**被拒，而不是靠 argv 里的 `--` 兜底。"""
    import backup
    calls = []
    monkeypatch.setattr(backup, "_run", lambda cmd, **kw: calls.append(cmd))
    os.environ["BACKUP_SCP_HOST"] = "-oProxyCommand=calc.exe"
    kind, ok, msg = backup.sync_scp("a.zip", "a.json")
    assert ok is False and calls == [], "非法 host 不应发出任何子进程调用"
    assert kind == "scp"
    os.environ.pop("BACKUP_SCP_HOST", None)


# ---------- B2 恢复前快照 ----------

def test_snapshot_before_restore_works_with_uploads(tmp_path, monkeypatch):
    """回归：uploads 打包循环写在 `with ZipFile(...)` **块外**，对已关闭的归档调
    `write()` 实测抛 `ValueError: Attempt to write to ZIP archive that was already
    closed`，而 `restore()` 在覆盖主库之前调用它 → 有图片的站点恢复必然崩。"""
    import backup
    up = tmp_path / "static" / "uploads"
    up.mkdir(parents=True)
    (up / "a.png").write_bytes(b"\x89PNG fake")
    root = tmp_path / "backups"
    root.mkdir()
    monkeypatch.setattr(backup, "UPLOAD_DIR", str(up))
    monkeypatch.setattr(backup, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(backup, "BACKUP_ROOT", str(root))
    monkeypatch.setattr(backup, "DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()

    arc = backup._snapshot_before_restore(tag="t1")
    assert arc and os.path.isfile(arc), "有上传文件时快照必须成功（原实现抛 ValueError）"
    assert os.path.basename(arc).startswith("blog_backup_"), "命名须被 prune_local 匹配，否则永不回收"
    with zipfile.ZipFile(arc) as zf:
        assert "manifest.json" in zf.namelist(), "缺 manifest 则 verify() 拒收，这份快照永远回不去"
        assert "static/uploads/a.png" in zf.namelist()
    ok, man = backup.verify(arc)
    assert ok is True, "自动快照必须是可恢复的：%r" % man
    assert isinstance(man, dict) and man.get("kind") == "prerestore"


def test_verify_rejects_size_mismatch(tmp_path, monkeypatch):
    """manifest 里本来就写了 size，却从未被校验；同时成员解压后不得无上限进内存。"""
    import backup
    p = tmp_path / "b.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/blog.db", b"hello")
        man = {"files": [{"path": "data/blog.db",
                          "sha256": __import__("hashlib").sha256(b"hello").hexdigest(),
                          "size": 999}], "file_count": 1}
        zf.writestr("manifest.json", json.dumps(man))
    ok, msg = backup.verify(str(p))
    assert ok is False and "尺寸" in str(msg)


# ---------- B3 插件 slug ----------

@pytest.mark.parametrize("slug", [
    "../../etc", "..", "a/../../b", "C:..", "", "a\\b", "x" * 65, "正常中文",
])
def test_plugin_dir_rejects_traversal(tmp_path, slug):
    from plugins import _plugin_dir
    cfg = {"PLUGINS_DIR": str(tmp_path)}
    assert _plugin_dir(cfg, slug) == "", "%r 必须被拒绝" % slug


def test_plugin_dir_accepts_normal_slug_and_blocks_escape(tmp_path):
    from plugins import _plugin_dir, set_plugin_enabled
    cfg = {"PLUGINS_DIR": str(tmp_path)}
    assert _plugin_dir(cfg, "my_plugin-1") == str(tmp_path / "my_plugin-1")
    # 拒绝的 slug 走的是调用方已有的「目录未配置」分支：不落盘、不建目录
    res = set_plugin_enabled(None, cfg, "../outside", False)
    assert res.get("ok") is False
    assert not (tmp_path.parent / "outside").exists()


# ---------- B4 super_required 首登闸门 ----------

def _mkadmin(app, role=ROLE_ADMIN, must_change=False):
    name = "aud-" + _r()
    u = User(username=name, email=name + "@test.local", role=role)
    u.set_password("test-pass-123")
    u.must_change_password = must_change
    with app.app_context():
        db.session.add(u)
        db.session.commit()
        return u.id, name


def _signin(client, user_id, version=0):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["session_version"] = version


def test_super_required_sends_unconfigured_super_to_setup(app, client):
    """超管还没改默认密码时，裸 @super_required 的路由也必须先被赶去 setup。

    此前只有 `login_required` / `admin_required` 有这一关，而 29 条路由是裸
    @super_required（/admin/settings、/admin/backup、/admin/theme、MCP 服务、
    AI 摘要、收录控制台）—— 默认密码窗口期内这些全部可用。
    """
    uid, _ = _mkadmin(app, role="super", must_change=True)
    _signin(client, uid)
    for path in ("/admin/settings", "/admin/backup", "/admin/theme-center", "/admin/seo"):
        r = client.get(path)
        assert r.status_code == 302, "%s 应被拦下" % path
        assert "/admin/setup" in r.headers["Location"], \
            "%s 实得 %r" % (path, r.headers.get("Location"))


def test_super_required_still_forbids_non_super(app, client):
    uid, _ = _mkadmin(app, role=ROLE_ADMIN, must_change=False)
    _signin(client, uid)
    assert client.get("/admin/settings").status_code == 403


# ---------- B5 停用而非删除 ----------

def test_deactivating_user_does_not_hand_their_posts_to_the_next(app, client):
    """删行会让 SQLite 复用 rowid：下一个注册者拿到同一个 id，而 `Post.author_id`
    不是外键，`_can_edit_post()` 只比 id 相等 → 新人获得旧人全部文章的编辑权。"""
    from admin._helpers import _can_edit_post
    with app.app_context():
        old = User(username="old-" + _r(), email="o@test.local", role=ROLE_USER)
        old.set_password("pw-old-12345")
        db.session.add(old)
        db.session.commit()
        p = Post(title="旧人文章" + _r(), slug="oldpost" + _r(), summary="s",
                 content="c", author_id=old.id, published=True)
        db.session.add(p)
        db.session.commit()
        old_id, pid = old.id, p.id      # 出上下文即 detached，先取成标量

        superu = User(username="sup-" + _r(), email="s@test.local", role="super")
        superu.set_password("pw-sup-12345")
        superu.must_change_password = False
        db.session.add(superu)
        db.session.commit()
        sup_id = superu.id
        # 旧账号先绑一个第三方身份，验证停用时会被断开（否则留下孤儿绑定）
        db.session.add(OAuthAccount(user_id=old_id, provider="github", sub="orphan-" + _r(),
                                    email="o@x.local"))
        db.session.commit()

    _signin(client, sup_id)
    tok = client.get("/api/csrf").get_json()["csrf_token"]
    r = client.post("/admin/user/%d/delete" % old_id, data={"csrf_token": tok})
    assert r.status_code == 302

    with app.app_context():
        gone = db.session.get(User, old_id)
        assert gone is not None, "行必须保留，否则其 id 会被复用"
        assert gone.role == ROLE_USER
        assert gone.username.startswith("disabled_")
        assert not gone.check_password("pw-old-12345"), "旧密码必须失效"
        assert (gone.session_version or 0) >= 1, "现有会话应被 bump 掉"
        assert OAuthAccount.query.filter_by(user_id=old_id).count() == 0, "第三方绑定要断开"
        # 关键：新注册者不可能再拿到 old_id
        fresh = User(username="fresh-" + _r(), email="f@test.local", role=ROLE_USER)
        fresh.set_password("pw-fresh-12345")
        db.session.add(fresh)
        db.session.commit()
        assert fresh.id != old_id
        assert _can_edit_post(fresh, db.session.get(Post, pid)) is False, \
            "新人不得因此获得旧人文章的编辑权"


# ---------- B6 读者积分 ----------

def test_reader_endpoints_are_rate_limited(app, client, monkeypatch):
    """`/api/reader/me` 对无 cookie 的请求会**新建并 commit 一行 Reader**；
    未鉴权 + 无限流 = 任何人可用「每次都不带 cookie」的 GET 洪水无上限灌行。"""
    seen = []
    import utils.net as net

    real = net.rate_limit

    def spy(*a, **k):
        r = real(*a, **k)
        seen.append(r)
        return r
    monkeypatch.setattr("api.reader.rate_limit", spy)
    for _ in range(3):
        client.get("/api/reader/me")
    assert seen, "必须调用 rate_limit"
    assert client.get("/api/reader/leaderboard").status_code == 200


def test_badge_integrity_error_does_not_poison_session(app, monkeypatch):
    """并发授予同一枚勋章时唯一约束会拒后来者；**不 rollback 会把会话留在失败状态**，
    同一请求里紧接着的取库操作（评论流程随后还要写 ReadLog）连带炸成 500。"""
    import gamify
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        r = gamify.Reader(token=secrets.token_hex(24))
        db.session.add(r)
        db.session.commit()
        rid = r.id

        def boom(*a, **k):
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
        monkeypatch.setattr(db.session, "commit", boom)
        db.session.rollback()
        db.session.add(gamify.ReaderBadge(reader_id=rid, badge_id=1))
        try:
            gamify._check_badges(db.session.get(gamify.Reader, rid))
        except IntegrityError:
            pytest.fail("_check_badges 不得把 IntegrityError 抛给调用方")
        # 回滚后会话必须仍可用：再查一次不应炸
        db.session.query(User).count()
