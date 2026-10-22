"""content_migrate 迁移插件回归：WXR / Typecho SQL 解析、落库、图片本地化、后台路由。

测试数据全部现场生成，不依赖网络；图片下载用桩替换出站层。
"""
import pytest

from models import db, Post, User, ROLE_SUPER

PASSWORD = "Passw0rd!23"


WXR = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:wp="http://wordpress.org/export/1.2/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/">
  <channel>
    <item>
      <title>Hello &amp; World</title>
      <wp:post_id>11</wp:post_id>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_name>mig-test-1</wp:post_name>
      <wp:post_date_gmt>2020-01-02 03:04:05</wp:post_date_gmt>
      <wp:post_modified_gmt>2020-01-03 03:04:05</wp:post_modified_gmt>
      <category domain="category"><![CDATA[迁移分类]]></category>
      <category domain="post_tag"><![CDATA[迁移标签]]></category>
      <category domain="post_tag"><![CDATA[Python]]></category>
      <wp:postmeta><wp:meta_key>_thumbnail_id</wp:meta_key><wp:meta_value>99</wp:meta_value></wp:postmeta>
      <content:encoded><![CDATA[<!-- wp:paragraph --><p>正文 <strong>bold</strong></p><!-- /wp:paragraph --><!--more-->]]></content:encoded>
      <excerpt:encoded><![CDATA[摘要 <em>here</em>]]></excerpt:encoded>
    </item>
    <item>
      <title>Draft Post</title>
      <wp:post_id>12</wp:post_id>
      <wp:post_type>post</wp:post_type>
      <wp:status>draft</wp:status>
      <wp:post_name>mig-test-2</wp:post_name>
      <wp:post_date_gmt>2020-02-02 00:00:00</wp:post_date_gmt>
      <content:encoded><![CDATA[<p>draft body</p>]]></content:encoded>
      <excerpt:encoded><![CDATA[]]></excerpt:encoded>
    </item>
    <item>
      <title>About Page</title>
      <wp:post_type>page</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_name>about</wp:post_name>
      <content:encoded><![CDATA[<p>page</p>]]></content:encoded>
    </item>
    <item>
      <title>cover</title>
      <wp:post_type>attachment</wp:post_type>
      <wp:post_id>99</wp:post_id>
      <wp:attachment_url>https://old.example.com/wp-content/uploads/cover.jpg</wp:attachment_url>
    </item>
  </channel>
</rss>
"""


TYPECHO_SQL = r"""
-- Typecho 1.2 dump
CREATE TABLE `typecho_contents` (`cid` int, `title` varchar(200));
INSERT INTO `typecho_contents` VALUES
(1,'第一篇文章','first-post',1600000000,1600000100,'<!--markdown--># 标题\n\n正文 It\'s ok','0',1,NULL,'post','publish',NULL,0,'1','1','1',0),
(2,'草稿文章','draft-post',1600000200,1600000200,'<p>HTML 草稿</p>','0',1,NULL,'post_draft','publish',NULL,0,'1','1','1',0),
(3,'关于页面','about',1600000300,1600000300,'x','0',1,NULL,'page','publish',NULL,0,'1','1','1',0);
INSERT INTO `typecho_metas` VALUES
(1,'技术','tech','category',1,0,0,''),
(2,'Python','python','tag',1,0,0,'');
INSERT INTO `typecho_relationships` VALUES (1,1),(1,2);
"""


IMG_WXR = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:wp="http://wordpress.org/export/1.2/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/">
  <channel>
    <item>
      <title>Image Post</title>
      <wp:post_id>21</wp:post_id>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_name>mig-img-1</wp:post_name>
      <content:encoded><![CDATA[<p><img src="/usr/uploads/a.png" alt="a"></p>]]></content:encoded>
      <excerpt:encoded><![CDATA[img]]></excerpt:encoded>
      <wp:postmeta><wp:meta_key>_thumbnail_id</wp:meta_key><wp:meta_value>98</wp:meta_value></wp:postmeta>
    </item>
    <item>
      <title>cover</title>
      <wp:post_type>attachment</wp:post_type>
      <wp:post_id>98</wp:post_id>
      <wp:attachment_url>/usr/uploads/cover.png</wp:attachment_url>
    </item>
  </channel>
</rss>
"""

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


class _Resp:
    def __init__(self, body):
        self.headers = {"Content-Type": "image/png"}
        self._body = body
        self._i = 0

    def read(self, n=-1):
        if n is None or n < 0:
            chunk, self._i = self._body[self._i:], len(self._body)
            return chunk
        chunk = self._body[self._i:self._i + n]
        self._i += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


@pytest.fixture(autouse=True)
def _clean_posts(app):
    """每个用例前后清掉本文件固定 slug 的文章，避免共享测试库相互影响。"""
    with app.app_context():
        for slug in ("mig-test-1", "mig-test-2", "first-post", "draft-post", "mig-img-1"):
            row = Post.query.filter_by(slug=slug).first()
            if row:
                db.session.delete(row)
        db.session.commit()
    yield


# ---------- 解析 ----------

def test_parse_wxr_fields_and_skips():
    from plugins.content_migrate.parsers import parse_wxr
    r = parse_wxr(WXR.encode("utf-8"))
    assert r.format == "wordpress"
    assert len(r.items) == 2
    assert r.skipped.get("page") == 1
    a, b = r.items
    assert a.title == "Hello & World"
    assert a.slug == "mig-test-1"
    assert a.published is True and b.published is False
    assert a.categories == ["迁移分类"]
    assert a.tags == ["迁移标签", "Python"]
    assert "正文" in a.content and "wp:paragraph" not in a.content and "more" not in a.content
    assert a.summary == "摘要 here"
    assert a.cover == "https://old.example.com/wp-content/uploads/cover.jpg"
    assert a.created_at.isoformat() == "2020-01-02T03:04:05"
    assert b.created_at.isoformat() == "2020-02-02T00:00:00"


def test_parse_wxr_rejects_doctype():
    from plugins.content_migrate.parsers import ParseError, parse_wxr
    bad = b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]><rss><channel/></rss>'
    with pytest.raises(ParseError, match="DOCTYPE"):
        parse_wxr(bad)


def test_parse_typecho_sql_fields():
    from plugins.content_migrate.parsers import parse_typecho_sql
    r = parse_typecho_sql(TYPECHO_SQL.encode("utf-8"))
    assert r.format == "typecho"
    assert len(r.items) == 2
    assert r.skipped.get("page") == 1
    a, b = r.items
    assert a.slug == "first-post"
    assert a.published is True and b.published is False
    assert a.content.startswith("# 标题")
    assert "<!--markdown-->" not in a.content
    assert "It's ok" in a.content and "\n" in a.content
    assert a.categories == ["技术"] and a.tags == ["Python"]
    assert a.created_at.isoformat() == "2020-09-13T12:26:40"
    assert b.slug == "draft-post"


def test_parse_any_sniffs_both_formats():
    from plugins.content_migrate.parsers import parse_any
    assert parse_any(WXR.encode(), "x.xml").format == "wordpress"
    assert parse_any(TYPECHO_SQL.encode(), "x.sql").format == "typecho"


def test_parse_any_rejects_unknown():
    from plugins.content_migrate.parsers import ParseError, parse_any
    with pytest.raises(ParseError):
        parse_any(b"hello world", "x.txt")


# ---------- 落库 ----------

def test_import_preserves_slug_category_tags_and_status(app):
    from plugins.content_migrate.importer import import_items
    from plugins.content_migrate.parsers import parse_wxr
    r = parse_wxr(WXR.encode())
    with app.app_context():
        out = import_items(r, preserve_slug=True)
        assert out["created"] == 2, out
        p1 = Post.query.filter_by(slug="mig-test-1").first()
        p2 = Post.query.filter_by(slug="mig-test-2").first()
        assert p1 and p2
        assert p1.published is True and p2.published is False
        assert p1.created_at.isoformat() == "2020-01-02T03:04:05"
        assert p1.category and p1.category.name == "迁移分类"
        assert {t.name for t in p1.tags} == {"迁移标签", "Python"}
        assert p1.cover.startswith("https://old.example.com/")

        # 重复导入：按 slug 去重，不翻倍
        again = import_items(r, preserve_slug=True)
        assert again["created"] == 0 and again["skipped"] == 2
        assert Post.query.filter_by(slug="mig-test-1").count() == 1


def test_import_publish_override(app):
    from plugins.content_migrate.importer import import_items
    from plugins.content_migrate.parsers import parse_wxr
    with app.app_context():
        out = import_items(parse_wxr(WXR.encode()), publish=True)
        assert out["created"] == 2
        assert Post.query.filter_by(slug="mig-test-2").first().published is True


def test_import_localizes_images(app, monkeypatch, tmp_path):
    from plugins.content_migrate import importer
    from plugins.content_migrate.parsers import parse_wxr
    import outbound

    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(outbound, "open_url", lambda url, **_kw: _Resp(PNG))
    with app.app_context():
        out = importer.import_items(parse_wxr(IMG_WXR.encode()), download_images=True,
                                    source_base="https://old.example.com")
        assert out["created"] == 1, out["warnings"]
        p = Post.query.filter_by(slug="mig-img-1").first()
        assert "/static/uploads/mig-" in p.content, p.content
        assert "old.example.com" not in p.content
        assert "/static/uploads/mig-" in p.cover, p.cover
        files = list(tmp_path.glob("mig-*.png"))
        assert files, "图片没有落盘"


# ---------- 路由 ----------

@pytest.fixture
def mig_client(app):
    from plugins.content_migrate.routes import bp
    if "content_migrate" not in app.blueprints:
        app.register_blueprint(bp)
    return app.test_client()


def _login_super(client, app):
    import secrets
    uname = "mig_su_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    d = client.get("/api/csrf").get_json() or {}
    assert client.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}
                       ).status_code == 200
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def test_preview_requires_admin(mig_client):
    r = mig_client.post("/admin/migrate/preview", data=WXR.encode(),
                        content_type="application/octet-stream")
    assert r.status_code in (302, 403)   # 未登录：CSRF 或登录跳转均算拒绝


def test_preview_returns_summary_for_admin(mig_client, app):
    csrf = _login_super(mig_client, app)
    r = mig_client.post("/admin/migrate/preview", data=WXR.encode(),
                        content_type="application/octet-stream",
                        query_string={"name": "export.xml"}, headers=csrf)
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["format"] == "wordpress" and d["total"] == 2
    assert d["samples"][0]["title"] == "Hello & World"


def test_import_route_runs_task_and_creates_posts(mig_client, app, monkeypatch):
    from plugins.content_migrate import routes as mig_routes

    def fake_submit(name, fn, *a, **kw):
        fn(*a, **kw)          # 测试里同步执行，避免依赖线程调度
        return "tid-test", None

    monkeypatch.setattr(mig_routes.tasks, "submit", fake_submit)
    csrf = _login_super(mig_client, app)
    r = mig_client.post("/admin/migrate/import", data=WXR.encode(),
                        content_type="application/octet-stream",
                        query_string={"name": "export.xml", "publish": "source",
                                      "preserve_slug": "1"}, headers=csrf)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["task_id"] == "tid-test"
    assert body["poll"].endswith("/admin/migrate/task/tid-test")
    with app.app_context():
        assert Post.query.filter_by(slug="mig-test-1").count() == 1


# ---------- 回归：选项从 query string 取（v4.8.0 修） ----------

def test_import_route_reads_publish_option_from_query_string(mig_client, app, monkeypatch):
    """**非默认值**才能钉死这个回归。

    之前路由从 `request.form` 读选项，而前台用原始字节流提交文件 → 选项在
    query string 里 → `publish` / `download_images` / `source_base` 三个选项
    **静默失效**（发布状态永远沿用原站、图片永远不下载、旧站相对路径永远补不出来）。
    原路由测试传的参数恰好等于默认值，所以一直是假绿。
    """
    from plugins.content_migrate import routes as mig_routes

    def fake_submit(name, fn, *a, **kw):
        fn(*a, **kw)
        return "tid-test", None

    monkeypatch.setattr(mig_routes.tasks, "submit", fake_submit)
    csrf = _login_super(mig_client, app)
    r = mig_client.post("/admin/migrate/import", data=WXR.encode(),
                        content_type="application/octet-stream",
                        query_string={"name": "export.xml", "publish": "draft"},
                        headers=csrf)
    assert r.status_code == 200, r.get_data(as_text=True)
    with app.app_context():
        p = Post.query.filter_by(slug="mig-test-1").first()
        assert p is not None, "文章没导入"
        assert p.published is False, "publish=draft 必须生效（原站状态是 publish）"


def test_import_route_reads_download_images_option_from_query_string(
        mig_client, app, monkeypatch, tmp_path):
    """勾选「下载正文图片」必须真的下载 —— 之前这个勾选是死的。"""
    import outbound
    from plugins.content_migrate import routes as mig_routes

    def fake_submit(name, fn, *a, **kw):
        fn(*a, **kw)
        return "tid-test", None

    monkeypatch.setattr(mig_routes.tasks, "submit", fake_submit)
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(outbound, "open_url", lambda url, **_kw: _Resp(PNG))
    csrf = _login_super(mig_client, app)
    r = mig_client.post("/admin/migrate/import", data=IMG_WXR.encode(),
                        content_type="application/octet-stream",
                        query_string={"name": "export.xml", "download_images": "1",
                                      "source_base": "https://old.example.com"},
                        headers=csrf)
    assert r.status_code == 200, r.get_data(as_text=True)
    with app.app_context():
        p = Post.query.filter_by(slug="mig-img-1").first()
        assert p is not None, "文章没导入"
        assert "/static/uploads/mig-" in p.content, \
            "download_images=1 必须真的本地化图片，实际正文：%s" % p.content[:200]
        assert list(tmp_path.glob("mig-*.png")), "图片没有落盘"
