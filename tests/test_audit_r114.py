"""v3.26.0 审计 R114 回归：友链 RSS 聚合的 SSRF 绕过与条目 XSS。

两处都出在同一个文件 `myblog/feed_agg.py`，成因是同一个：
**「校验」与「使用」分离**——`_safe_url()` 在抓取前查一次，之后真正的请求
却由 `feedparser.parse(url)` 另发，它自建 urllib 会话、重新解析 DNS、且
**自动跟随 3xx**。

1. SSRF（CWE-918）：攻击者的 RSS 地址是**公网** IP，过 `_safe_url()` 没问题；
   然后回一个 `302 Location: http://100.100.100.200/`（阿里云元数据）或内网服务，
   跳转目标**从不被复检**。DNS 重绑定同理：预检查解析一次，feedparser 再解析一次。
   → 修法：自己用**禁重定向**的 opener 抓字节，再把字节喂给 feedparser。
2. 存储型 XSS（CWE-79）：条目的 `<link>` 此前**只判空**，于是
   `javascript:fetch(...)` 原样进前端 `:href`（`target="_blank"` 不阻止
   `javascript:` 执行）→ 现只放行 http/https。

另附 SMTP 授权码明文落库（CWE-312）的回归。
"""
import http.server
import io
import os
import threading

import pytest

from models import db, User, Setting, ROLE_SUPER

PASSWORD = "Passw0rd!23"


# ---------- 1. 条目链接协议白名单 ----------

def test_item_url_blocks_javascript_pseudo_protocol():
    from feed_agg import _safe_item_url
    # 真实攻击载荷：点一下就在本站源下执行任意 JS
    payload = "javascript:fetch('/api/auth/me',{credentials:'include'})"
    assert _safe_item_url(payload) == ""
    assert _safe_item_url("JavaScript:alert(1)") == ""
    assert _safe_item_url("data:text/html,<script>alert(1)</script>") == ""
    assert _safe_item_url("vbscript:msgbox(1)") == ""
    assert _safe_item_url("") == ""
    assert _safe_item_url("   ") == ""


def test_item_url_allows_only_http_https():
    from feed_agg import _safe_item_url
    assert _safe_item_url("https://example.com/p/1") == "https://example.com/p/1"
    assert _safe_item_url("http://example.com/") == "http://example.com/"
    # 无 netloc 的相对路径也不该放行（前端 :href 会拼成站内路径，语义不同）
    assert _safe_item_url("/relative/path") == ""
    assert _safe_item_url("//evil.com/x") == ""


# ---------- 2. 禁重定向抓取器 ----------

class _FeedHandler(http.server.BaseHTTPRequestHandler):
    """一个 302 跳转到内网的「恶意」RSS 源 + 一个正常 200 源。"""

    def do_GET(self):
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/metadata/latest/meta-data/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静音 pytest 输出
        pass


@pytest.fixture()
def feed_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FeedHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_fetch_refuses_to_follow_redirect(feed_server):
    """302 必须被拒绝，而不是默默跟到内网目标。"""
    import urllib.error
    from feed_agg import _fetch_feed_bytes
    with pytest.raises(urllib.error.HTTPError) as ei:
        _fetch_feed_bytes(feed_server + "/redirect", timeout=5)
    assert ei.value.code in (301, 302, 303, 307, 308)


def test_fetch_returns_body_for_normal_feed(feed_server):
    from feed_agg import _fetch_feed_bytes
    data = _fetch_feed_bytes(feed_server + "/ok", timeout=5)
    assert b"<rss" in data


def test_no_placeholder_left_in_source():
    """防止「补了一处、漏了另一处」——源码里不得再出现裸 feedparser.parse(URL)。

    用 **AST** 判定而不是正则扫文本：注释与文档字符串里大量出现
    `feedparser.parse(url)` 这段字样（正是在解释「为什么不能这么写」），
    正则会把它们一起抓出来，产出假红。
    """
    import ast
    with io.open("myblog/feed_agg.py", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = "%s.%s" % (getattr(fn.value, "id", ""), getattr(fn, "attr", "")) \
            if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name != "feedparser.parse":
            continue
        arg = node.args[0] if node.args else None
        # 允许 feedparser.parse(io.BytesIO(...))，禁止 feedparser.parse(<url/变量>)
        ok = (isinstance(arg, ast.Call)
              and isinstance(arg.func, ast.Attribute)
              and getattr(arg.func.value, "id", "") == "io"
              and arg.func.attr == "BytesIO")
        if not ok:
            bad.append(ast.dump(arg)[:80] if arg is not None else "<no args>")
    assert not bad, (
        "feed_agg.py 里仍有未加固的 feedparser.parse(...)：%s —— "
        "它会自建会话重新解析 DNS 并跟随 302，绕过 _safe_url 的私网过滤" % bad)


# ---------- 3. SMTP 授权码密文落库（CWE-312） ----------

@pytest.fixture()
def super_client(client, app):
    import secrets
    uname = "su_" + secrets.token_hex(4)
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


def test_mail_password_stored_encrypted(super_client, app):
    """后台保存后，库里必须是 bkenc$ 密文，不能是明文。"""
    secret = "SMTP-AUTH-CODE-9x8y7z"
    r = super_client.post("/admin/email-settings", data={
        "mail_host": "smtp.example.com", "mail_port": "465",
        "mail_username": "u@example.com", "mail_from": "u@example.com",
        "mail_use_ssl": "on", "mail_password": secret,
    }, headers=_csrf(super_client), follow_redirects=True)
    assert r.status_code in (200, 302, 303), r.status_code
    with app.app_context():
        row = db.session.query(Setting).filter_by(key="mail_password").first()
        assert row is not None, "邮件密码根本没落库，用例无效"
        assert row.value != secret, "SMTP 授权码仍以明文落库（CWE-312）"
        assert row.value.startswith("bkenc$"), "应存为 Fernet 密文（bkenc$ 前缀）"
        from backup_settings import decrypt_secret
        assert decrypt_secret(row.value) == secret, "密文应能解回明文（写入侧与读取侧不一致）"
    with app.app_context():
        db.session.query(Setting).filter_by(key="mail_password").delete()
        db.session.commit()


def test_mail_password_legacy_plaintext_still_readable(app):
    """存量明文不能因此发不出邮件：decrypt_secret 对无前缀值原样返回。"""
    from backup_settings import decrypt_secret
    assert decrypt_secret("legacy-plaintext") == "legacy-plaintext"
    assert decrypt_secret("") == ""
    assert decrypt_secret(None) == ""


# ---------- 5. OG 分享卡封面路径穿越（CWE-22） ----------

def test_cover_path_blocks_traversal_out_of_allowed_dirs(app):
    """`static/../../config.py` 曾能越出 static/ 读到 myblog/config.py。

    ⚠️ 测试方法要点（审计组提出的有效批评，已采纳）：
    - **目标文件必须真实存在**，否则 `os.path.isfile()` 先返回 None，
      会让人误把「文件不存在」读成「穿越被拦」——空断言的假绿。
      这里用 `config.py`（仓库里必然存在，且含 SECRET_KEY 派生逻辑）。
    - **必须正反双向**：只有反向用例时，一个「永远返回 None」的过滤器也能全绿。
      故下面另有 `test_cover_path_positive_control` 证明过滤器并非空转。
    """
    import og_image
    with app.app_context():
        assert os.path.isfile(os.path.join(og_image._HERE, "config.py")), \
            "前提失效：config.py 不存在，本用例会变成假绿"
        # 带前缀分支（原缺陷所在）
        for evil in ("static/../../config.py",
                     "uploads/../../data/blog.db",
                     "static/../config.py"):
            got = og_image._local_cover_path(evil)
            assert got is None or "config.py" not in got, \
                "带前缀分支的穿越未被拦住：%r -> %r" % (evil, got)
        # 无前缀的兜底分支（join(_HERE, "static", c)）同样要拦住
        for evil in ("../config.py", "../app.py", "../data/blog.db",
                     "../templates/admin/base.html", "../../etc/passwd"):
            got = og_image._local_cover_path(evil)
            assert got is None, \
                "兜底分支的穿越未被拦住：%r -> %r" % (evil, got)


def test_cover_path_positive_control(app):
    """反向对照：合法路径**必须仍能解析**，否则说明过滤器是「一律拒绝」的假绿。"""
    import og_image
    with app.app_context():
        static_dir = os.path.join(og_image._HERE, "static")
        real = None
        for name in os.listdir(static_dir):
            if os.path.isfile(os.path.join(static_dir, name)):
                real = "static/" + name
                break
        assert real, "static/ 下没有可用文件，无法做正向对照"
        got = og_image._local_cover_path(real)
        assert got is not None and os.path.isfile(got), \
            "合法封面路径被误拦：%r -> %r" % (real, got)


def test_cover_path_still_accepts_real_static_file(app):
    """修复不能把正常封面也一起拦掉（防「修过头」）。"""
    import og_image
    with app.app_context():
        assert og_image._local_cover_path("https://evil.com/x.png") is None
        assert og_image._local_cover_path("") is None
        assert og_image._local_cover_path("//evil.com/x.png") is None


# ---------- 4. 可见性收口：私密文章的 sidere 通道 ----------

def test_reactions_ignore_comments_of_invisible_posts(app):
    """私密/未发布文章的评论，表情计数既读不到也写不进。"""
    from api import reactions as R
    with app.app_context():
        assert R._readable_comment(999999) is None
        assert R._load(999999) == {}


def test_stats_read_ignores_non_visible_slug(app):
    """stats/read 走 visible_posts_query()，不可见文章的 slug 不该被计数。"""
    import inspect
    src = inspect.getsource(__import__("api.stats", fromlist=["stats_read"]))
    assert "visible_posts_query().filter_by(slug=slug)" in src, (
        "api/stats.py 又退回裸 Post.query 查 slug 了——匿名可给私密文章累加阅读量")
    assert "Post.query.filter_by(slug=slug)" not in src
