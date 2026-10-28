"""v4.14.0 媒体库：视频上传 / 分块合并 / 图床归档 / 正文视频渲染。

测试重点不是「能不能传」，而是**边界**：

1. **伪装文件必须被拒**：`.mp4` 里塞 PNG 字节 —— 这是上传口最经典的攻击面
   （白名单看后缀，服务器/浏览器却按内容嗅探执行）。
2. **上限按类型分流**：图片 50MB、视频 500MB；不能因为放开视频把图片也放大。
3. **磁盘闸门**：剩余空间不够时**在写盘前**拒绝 —— 写满盘会让 SQLite 全线失败。
4. **分块必须完整**：缺块/大小不符一律拒绝合并，绝不入库一个残缺文件。
5. **公开接口只吐 is_public**：私密附件靠 SQL 层过滤，而不是取回来再筛。
"""
import os

import pytest

import media_service
import media_storage
from models import db, MediaAsset

MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8       # ISO BMFF: 第 4~8 字节 'ftyp'
PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.fixture(autouse=True)
def _clean_assets(app):
    """测试库全 session 共享 —— 不清表的话，别的用例留下的资源会让计数类断言假红/假绿。"""
    with app.app_context():
        MediaAsset.query.delete()
        db.session.commit()
    yield
    with app.app_context():
        MediaAsset.query.delete()
        db.session.commit()


@pytest.fixture
def media_dirs(app, tmp_path):
    """把上传目录/临时目录指到 pytest 的 tmp_path —— 绝不写进仓库。"""
    up = tmp_path / "uploads"
    tmp = tmp_path / "upload_tmp"
    up.mkdir()
    tmp.mkdir()
    app.config["UPLOAD_FOLDER"] = str(up)
    app.config["UPLOAD_TMP_DIR"] = str(tmp)
    # 测试库是全 session 共享的：清掉别的用例可能留下的存储后端设置，
    # 否则这里会真的去连 OSS/WebDAV（慢且不确定）。
    from models import Setting
    with app.app_context():
        Setting.query.filter(Setting.key.like("media_%")).delete()
        db.session.commit()
    return up, tmp


# ---------------------------------------------------------------- 类型与魔数

def test_视频与图片后缀分流():
    assert media_service.kind_of("a.mp4") == "video"
    assert media_service.kind_of("a.MOV") == "video"
    assert media_service.kind_of("a.webm") == "video"
    assert media_service.kind_of("a.png") == "image"
    # 刻意不支持：浏览器放不了，收进来只会变成下载链接
    assert media_service.kind_of("a.avi") is None
    assert media_service.kind_of("a.svg") is None


def test_伪装的视频被拒绝():
    ok, msg = media_service.validate_magic(PNG_HEAD, "fake.mp4")
    assert ok is False, "PNG 字节却声明 .mp4，必须拒绝"
    assert "不符" in msg


def test_真实视频通过校验():
    assert media_service.validate_magic(MP4_HEAD, "real.mp4")[0] is True
    assert media_service.validate_magic(b"\x1a\x45\xdf\xa3" + b"\x00" * 12, "real.webm")[0] is True


def test_图片与视频上限分流(app):
    with app.app_context():
        assert media_service.max_bytes_for("image") == 50 * 1024 * 1024
        assert media_service.max_bytes_for("video") == 500 * 1024 * 1024


# ---------------------------------------------------------------- 磁盘闸门

def test_磁盘余量不足时拒绝(app, media_dirs, monkeypatch):
    class _Usage:
        free = 100 * 1024 * 1024        # 只剩 100MB

    monkeypatch.setattr(media_service.shutil, "disk_usage", lambda p: _Usage())
    with app.app_context():
        app.config["MEDIA_DISK_RESERVE_BYTES"] = 2 * 1024 * 1024 * 1024
        ok, msg = media_service.check_disk_room(50 * 1024 * 1024)
        assert ok is False
        assert "空间不足" in msg


def test_磁盘充足时放行(app, media_dirs, monkeypatch):
    class _Usage:
        free = 10 * 1024 * 1024 * 1024

    monkeypatch.setattr(media_service.shutil, "disk_usage", lambda p: _Usage())
    with app.app_context():
        app.config["MEDIA_DISK_RESERVE_BYTES"] = 2 * 1024 * 1024 * 1024
        assert media_service.check_disk_room(50 * 1024 * 1024)[0] is True


# ---------------------------------------------------------------- 分块上传

def _init(app, name, size):
    return media_service.chunk_init(name, size)


def test_分块上传合并成功(app, media_dirs):
    payload = MP4_HEAD + b"hello-world-video" * 3
    with app.app_context():
        app.config["UPLOAD_CHUNK_SIZE"] = 8          # 故意切很小，确保多块
        info = _init(app, "clip.mp4", len(payload))
        uid = info["upload_id"]
        for i in range(0, len(payload), 8):
            media_service.chunk_save(uid, i // 8, payload[i:i + 8])
        asset = media_service.chunk_complete(uid)

        assert asset.kind == "video"
        assert asset.size == len(payload)
        assert asset.url.startswith("/static/uploads/")
        up, tmp = media_dirs
        assert (up / asset.filename).exists(), "合并后的文件必须真的落盘"
        assert not (tmp / uid).exists(), "合并成功后临时目录必须清理"


def test_分块缺块时拒绝合并(app, media_dirs):
    payload = MP4_HEAD + b"x" * 20
    with app.app_context():
        app.config["UPLOAD_CHUNK_SIZE"] = 8
        uid = _init(app, "clip.mp4", len(payload))["upload_id"]
        media_service.chunk_save(uid, 0, payload[:8])      # 只传第一块
        with pytest.raises(media_service.MediaError) as ei:
            media_service.chunk_complete(uid)
        assert "不完整" in ei.value.message
        assert not MediaAsset.query.filter_by(kind="video").first()


def test_分块大小不符时拒绝合并(app, media_dirs):
    """声明 100 字节、实际传 10 字节 —— 不能因为「块数够了」就放行。"""
    with app.app_context():
        app.config["UPLOAD_CHUNK_SIZE"] = 8
        uid = _init(app, "clip.mp4", 100)["upload_id"]
        media_service.chunk_save(uid, 0, MP4_HEAD[:8])
        media_service.chunk_save(uid, 1, MP4_HEAD[8:16])
        with pytest.raises(media_service.MediaError):
            media_service.chunk_complete(uid)


def test_上传会话_id_必须合法(app, media_dirs):
    with app.app_context():
        for bad in ("../../etc", "abc", "", "x" * 32):
            with pytest.raises(media_service.MediaError):
                media_service.chunk_dir(bad)


# ---------------------------------------------------------------- 公开接口

def test_公开接口只返回_is_public(app, client, media_dirs):
    with app.app_context():
        a1 = MediaAsset(filename="1-a.png", kind="image", source="local", storage="local",
                        url="/static/uploads/1-a.png", title="公开图", is_public=True)
        a2 = MediaAsset(filename="2-b.png", kind="image", source="local", storage="local",
                        url="/static/uploads/2-b.png", title="私密图", is_public=False)
        db.session.add_all([a1, a2])
        db.session.commit()

    data = client.get("/api/media/list").get_json()
    titles = [i["title"] for i in data["items"]]
    assert "公开图" in titles
    assert "私密图" not in titles, "is_public=False 的资源绝不能出现在公开接口里"
    assert data["total"] == 1


def test_公开接口按类型筛选(app, client, media_dirs):
    with app.app_context():
        db.session.add(MediaAsset(filename="3-c.mp4", kind="video", source="local",
                                  url="/static/uploads/3-c.mp4", title="视频", is_public=True))
        db.session.add(MediaAsset(filename="4-d.png", kind="image", source="local",
                                  url="/static/uploads/4-d.png", title="图片", is_public=True))
        db.session.commit()

    data = client.get("/api/media/list?kind=video").get_json()
    assert [i["kind"] for i in data["items"]] == ["video"]


# ---------------------------------------------------------------- 外链

def test_外链只允许白名单播放器(app):
    with app.app_context():
        with pytest.raises(media_service.MediaError):
            media_service.normalize_embed("https://evil.example.com/player")
        with pytest.raises(media_service.MediaError):
            media_service.normalize_embed("javascript:alert(1)")
        assert media_service.normalize_embed(
            "https://player.bilibili.com/player.html?bvid=BV1xx")[1] == "video"


# ---------------------------------------------------------------- 正文渲染

def test_正文图片语法指向视频会变成_video():
    from utils.render import render_markdown

    html = render_markdown("![](/static/uploads/1-a.mp4)")
    assert "<video" in html and "controls" in html
    assert "<img" not in html, "视频不该继续输出成 img（那会是一张裂图）"


def test_正文普通图片仍然是_img():
    from utils.render import render_markdown

    html = render_markdown("![](/static/uploads/1-a.png)")
    assert "<img" in html and "<video" not in html


def test_正文视频标签不会被白名单剥掉():
    from utils.render import render_markdown

    html = render_markdown('<video src="/static/uploads/1-a.mp4" controls></video>')
    assert "<video" in html and "controls" in html


def test_正文仍剥离脚本与_iframe():
    from utils.render import render_markdown

    html = render_markdown('<script>alert(1)</script><iframe src="http://evil"></iframe>')
    assert "<script" not in html and "<iframe" not in html


# ---------------------------------------------------------------- 后台页面渲染

def test_后台媒体库页面能渲染(app, client, media_dirs):
    """模板最容易悄悄改坏 —— 至少确认 `media_lib.html` 不 500。

    这个用例抓的是「路由传了变量但模板读了另一个名字」这类错误：
    Jinja 的 Undefined 默认不报错，页面会「看起来正常但某块空白」，
    只有真正渲染一次才发现（`single_max_bytes` 就属于这类）。
    """
    import secrets
    from models import User, ROLE_SUPER
    from utils import _sign_csrf

    with app.app_context():
        u = User(username="m-" + secrets.token_hex(4), email="m-%s@test.local" % secrets.token_hex(4))
        u.set_password("test-pass")
        u.role = ROLE_SUPER
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        uid = u.id

    raw = secrets.token_hex(24)
    with app.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["csrf_token"] = tok

    r = client.get("/admin/media")
    assert r.status_code == 200, r.data[:400]
    body = r.data.decode("utf-8")
    assert "媒体库" in body
    assert "云存储后端" in body, "存储设置面板没渲染出来"


def test_分块初始化写不进临时目录时给可读错误(app, media_dirs, monkeypatch):
    """回归 v5.2.1：`data/upload_tmp` 属主是 root、worker 是 www 时，
    `os.makedirs` 抛 PermissionError。

    若这个异常漏出去，Flask 会返回 **500 HTML**，而前端用 `r.json()` 解析，
    用户看到的是「Unexpected token '<', "<!DOCTYPE "... is not valid JSON」——
    完全不知道发生了什么，也不知道该找谁。

    所以这里断言的是「必须翻成带 507 状态码的 MediaError」，
    而不是断言某个具体文案。
    """
    def _deny(*a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(media_service.os, "makedirs", _deny)
    with app.app_context():
        with pytest.raises(media_service.MediaError) as ei:
            _init(app, "clip.mp4", 20 * 1024 * 1024)
        assert ei.value.status == 507, "写不进临时目录应当返回 507 而不是 500"
        assert "无法写入上传临时目录" in ei.value.message
