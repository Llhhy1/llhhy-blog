"""v3.25.6 三项修复的守卫（sitemap 图片地址 / 证书状态时间口径 / site_url 改动即时重跑）。

来源不是设计评审，是 **v3.25.5 上线核验时在生产实测抓出来的**三条：

1. **P1 `sitemap.xml` 的 `<image:loc>` 是错的**（两层叠在一起）：
   - `post.cover` 的语义是**站内相对路径**（`og_image._local_cover_path()` 只认
     `static/` `uploads/` 前缀），而 sitemap 规范里 `image:loc` **必须是绝对 URL**
     → 原实现直接输出相对路径，搜索引擎根本拿不到图。
   - 生产有一篇文章的 `cover` 存成了字符串 `'None'`（历史写入路径把 Python 的
     `None` 拼成了 `"None"`）→ 实测输出 `<image:loc>None</image:loc>`。
2. **P2 证书状态文件的三个时间字段口径不一致**：`checked_at` 存裸 UTC 不标时区、
   `not_after` 反而带 `" UTC"` 后缀、`backup_verify.json` 又是北京时间 →
   诊断页「上次检查」看起来比现在早 8 小时，容易被读成「监控没跑」。
3. **P3 填完 `site_url` 后证书检查不会立刻重跑**（见 `test_site_url_setting.py`）。
"""
import datetime
import secrets

import pytest

from models import db, Post, User, ROLE_ADMIN

BASE = "https://www.example.com"


def _r():
    return secrets.token_hex(4)


def _author():
    u = User(username="v3256-" + _r(), email="v3256@test.local", role=ROLE_ADMIN)
    u.set_password("test-pass-123")
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _post(author, title, **kw):
    p = Post(title=title, slug=title.lower() + "-" + _r(),
             summary="s", content="c", author_id=author.id, published=True)
    for k, v in kw.items():
        setattr(p, k, v)
    db.session.add(p)
    db.session.commit()
    return p


# ---------- P1 · sitemap 的 image:loc ----------

@pytest.mark.parametrize("cover, want", [
    ("uploads/a.png", BASE + "/uploads/a.png"),      # 站内相对 → 拼成绝对
    ("static/a.png", BASE + "/static/a.png"),
    ("/uploads/a.png", BASE + "/uploads/a.png"),
    ("https://cdn.example.com/a.png", "https://cdn.example.com/a.png"),   # 已是绝对
    ("None", ""),                                    # 生产实测的脏值
    ("null", ""),
    ("", ""),
    ("   ", ""),
    ("a.png", ""),                                   # 非站内前缀：不放进 sitemap
])
def test_image_loc_normalizes(cover, want):
    from routes import _sitemap_image_loc
    assert _sitemap_image_loc(cover, BASE) == want


def test_image_loc_omits_when_site_url_unset():
    """站点对外地址没配 → **不输出**，绝不拼半个地址、也绝不猜域名。"""
    from routes import _sitemap_image_loc
    assert _sitemap_image_loc("uploads/a.png", "") == ""


def test_sitemap_never_emits_none_image(client, app):
    """端到端：封面存成字符串 'None' 的文章，sitemap 里**不能**出现 image:loc。"""
    with app.app_context():
        a = _author()
        _post(a, "DirtyCover" + _r(), cover="None")
    import routes
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(routes, "_site_base", lambda: BASE)
    try:
        xml = client.get("/sitemap.xml").get_data(as_text=True)
    finally:
        monkeypatch.undo()
    assert "<image:loc>None</image:loc>" not in xml, "sitemap 仍在输出脏值图片地址"
    assert "image:loc>None" not in xml


def test_sitemap_image_loc_is_absolute(client, app):
    """端到端：正常封面必须输出**绝对 URL**，不是相对路径。"""
    with app.app_context():
        a = _author()
        _post(a, "GoodCover" + _r(), cover="uploads/cover-x.png")
    import routes
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(routes, "_site_base", lambda: BASE)
    try:
        xml = client.get("/sitemap.xml").get_data(as_text=True)
    finally:
        monkeypatch.undo()
    assert "<image:loc>uploads/cover-x.png</image:loc>" not in xml, "相对路径不合规"
    assert "<image:loc>%s/uploads/cover-x.png</image:loc>" % BASE in xml


# ---------- P2 · 证书状态文件的时间口径 ----------

def _bj_now():
    return (datetime.datetime.now(datetime.timezone.utc)
            .astimezone(datetime.timezone(datetime.timedelta(hours=8))))


def test_checked_at_is_beijing_not_raw_utc(monkeypatch, tmp_path):
    """`checked_at` 必须是北京时间 —— 存裸 UTC 会让它看起来比现在早 8 小时。"""
    import cert_watch as cw
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "cert_check.json"))
    monkeypatch.setattr(cw, "_target_host", lambda: "")
    st = cw.check_once()
    got = datetime.datetime.strptime(st["checked_at"], "%Y-%m-%d %H:%M:%S")
    assert "UTC" not in st["checked_at"], "展示字段不该再带时区后缀"
    assert abs((got - _bj_now().replace(tzinfo=None)).total_seconds()) < 120, (
        "checked_at 应是北京时间，实测 %s（北京应为 %s）"
        % (st["checked_at"], _bj_now().strftime("%Y-%m-%d %H:%M:%S")))


def test_not_after_has_no_utc_suffix_and_is_beijing(monkeypatch, tmp_path):
    """`not_after` 与 `checked_at` 同口径：北京时间、不带 " UTC" 后缀。"""
    import cert_watch as cw
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "cert_check.json"))
    monkeypatch.setattr(cw, "_target_host", lambda: "example.com")
    monkeypatch.setattr(cw, "_fetch_cert_der", lambda h: b"\x00")
    na = (datetime.datetime.now(datetime.timezone.utc)
          + datetime.timedelta(days=40, hours=1))
    monkeypatch.setattr(cw, "_parse_der",
                        lambda der: {"not_after": na, "subject": "CN=x", "issuer": "CN=y"})
    st = cw.check_once()
    assert st["status"] == "ok" and st["days_left"] == 40
    assert "UTC" not in st["not_after"], "not_after 与 checked_at 口径必须一致"
    got = datetime.datetime.strptime(st["not_after"], "%Y-%m-%d %H:%M:%S")
    want = na.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    assert abs((got - want.replace(tzinfo=None)).total_seconds()) < 120


def test_state_file_timestamps_share_one_clock(monkeypatch, tmp_path):
    """两个时间字段必须**同一时基** —— 差 8 小时就说明又混了 UTC 与北京时间。"""
    import cert_watch as cw
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "cert_check.json"))
    monkeypatch.setattr(cw, "_target_host", lambda: "example.com")
    monkeypatch.setattr(cw, "_fetch_cert_der", lambda h: b"\x00")
    na = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=40)
    monkeypatch.setattr(cw, "_parse_der",
                        lambda der: {"not_after": na, "subject": "CN=x", "issuer": "CN=y"})
    st = cw.check_once()
    a = datetime.datetime.strptime(st["checked_at"], "%Y-%m-%d %H:%M:%S")
    b = datetime.datetime.strptime(st["not_after"], "%Y-%m-%d %H:%M:%S")
    assert (b - a).days == 40, "两个字段若时基不同，天数差会整整错 8 小时"
