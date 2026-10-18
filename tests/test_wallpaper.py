"""v4.5.0 首页壁纸配置（存 Setting KV，零表结构变更）。

三条边界，逐条都有对应的失败方式：

1. **URL 必须自限**。壁纸 URL 会进 inline style 的 `background-image`；
   放开外部 URL 等于让每个访客替站主向第三方发请求（IP/UA 泄漏），
   `data:` 还能塞任意内容。
2. **必须挡路径穿越**。只判 `startswith("/static/uploads/")` 会被
   `/static/uploads/../../config.py` 绕过 —— 前缀仍然成立，浏览器再把
   `..` 规范化掉。
3. **纯壁纸请求不得顺手改主题**。后台保存壁纸时会只带 wallpaper 字段；
   反过来，主题应用也不该清掉已配好的壁纸。
"""
import secrets

import pytest

from models import db, Setting, User, ROLE_SUPER
from api.theme import _wallpaper, _safe_wp_url, _clamp

_OK = "/static/uploads/1750000000-wall.webp"


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _post(client, body):
    return client.post("/api/theme", json=body,
                       headers={"X-CSRF-Token": _csrf(client)})


@pytest.fixture
def super_user(app):
    with app.app_context():
        u = User(username="wp-" + secrets.token_hex(4),
                 email="wp-%s@test.local" % secrets.token_hex(4))
        u.set_password("x")
        u.role = ROLE_SUPER
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        return u.id


def _wipe():
    Setting.query.filter_by(key="home_wallpaper").delete()
    db.session.commit()


# ---------- URL 净化 ----------


def test_safe_url_accepts_only_local_upload():
    assert _safe_wp_url(_OK) == _OK
    assert _safe_wp_url("https://evil.example.com/a.jpg") == "", \
        "外部 URL 会让访客浏览器代持第三方请求"
    assert _safe_wp_url("javascript:alert(1)") == ""
    assert _safe_wp_url("data:image/svg+xml;base64,PHN2Zz4=") == ""


def test_safe_url_blocks_path_traversal():
    """`..` 必须被拒 —— 它同样以 /static/uploads/ 开头，靠 startswith 拦不住。"""
    assert _safe_wp_url("/static/uploads/../../config.py") == ""
    assert _safe_wp_url("/static/uploads/../secret") == ""
    assert _safe_wp_url("/static/uploads\\..\\x.png") == ""


def test_safe_url_blocks_query_and_fragment():
    assert _safe_wp_url("/static/uploads/a.png?x=1") == ""
    assert _safe_wp_url("/static/uploads/a.png#frag") == ""


def test_clamp_overlay():
    assert _clamp("abc", 0.0, 0.8, 0.35) == 0.35
    assert _clamp(-5, 0.0, 0.8, 0.35) == 0.0
    assert _clamp(99, 0.0, 0.8, 0.35) == 0.8
    assert _clamp(0.5, 0.0, 0.8, 0.35) == 0.5


# ---------- 默认值与损坏数据 ----------


def test_wallpaper_defaults_when_unset(app):
    with app.app_context():
        _wipe()
        wp = _wallpaper()
        assert wp == {"enabled": False, "light": "", "dark": "", "overlay": 0.35}


def test_wallpaper_survives_corrupt_json(app):
    """损坏/非法的存量值必须回落默认，不能把 /api/site 整个打挂。"""
    with app.app_context():
        _wipe()
        row = Setting(key="home_wallpaper", value="{not json")
        db.session.add(row)
        db.session.commit()
        assert _wallpaper()["enabled"] is False
        row.value = '"just a string"'
        db.session.commit()
        assert _wallpaper()["overlay"] == 0.35
        _wipe()


def test_enabled_requires_an_image(app):
    """`enabled` 为真但一张图都没有时必须回落为关闭 ——
    否则前台会渲染出一片纯色空区。"""
    with app.app_context():
        _wipe()
        db.session.add(Setting(key="home_wallpaper",
                               value='{"enabled":true,"light":"","dark":""}'))
        db.session.commit()
        assert _wallpaper()["enabled"] is False
        _wipe()


# ---------- API ----------


def test_theme_api_exposes_wallpaper(app, client):
    r = client.get("/api/theme")
    assert r.status_code == 200
    assert "wallpaper" in r.get_json()
    assert "wallpaper" in client.get("/api/site").get_json()


def test_post_wallpaper_only_does_not_touch_theme(app, client, super_user):
    """守卫 3：只带 wallpaper 的请求不得改动主题包。"""
    with app.app_context():
        _wipe()
        before = client.get("/api/theme").get_json()["current"]["pack_id"]
        with client.session_transaction() as sess:
            sess["user_id"] = super_user
        r = _post(client, {"wallpaper": {
            "enabled": True, "light": _OK, "dark": "", "overlay": 0.5}})
        assert r.status_code == 200, r.get_data(as_text=True)
        d = r.get_json()
        assert d["wallpaper"]["enabled"] is True
        assert d["wallpaper"]["overlay"] == 0.5
        assert d["pack_id"] == before, "纯壁纸请求顺手改了主题包"
        _wipe()


def test_post_wallpaper_rejects_enable_without_image(app, client, super_user):
    with app.app_context():
        _wipe()
        with client.session_transaction() as sess:
            sess["user_id"] = super_user
        r = _post(client, {"wallpaper": {
            "enabled": True, "light": "", "dark": ""}})
        assert r.status_code == 400
        assert "至少一张" in r.get_json()["error"]
        _wipe()


def test_post_wallpaper_sanitizes_urls(app, client, super_user):
    """外部 URL 在写入侧就该被清掉，而不是只靠读取侧过滤。"""
    with app.app_context():
        _wipe()
        with client.session_transaction() as sess:
            sess["user_id"] = super_user
        r = _post(client, {"wallpaper": {
            "enabled": True,
            "light": "https://evil.example.com/x.jpg",
            "dark": "/static/uploads/../../config.py"}})
        assert r.status_code == 400, "两条 URL 都被拒后等于没图，应报 400"
        _wipe()


def test_wallpaper_requires_super(app, client, super_user):
    """壁纸是站点级外观配置，沿用 /api/theme 的超管口径，不得放宽。"""
    with app.app_context():
        _wipe()
        r = client.post("/api/theme", json={"wallpaper": {
            "enabled": True, "light": _OK}})
        assert r.status_code in (401, 403), r.status_code
        _wipe()


def test_theme_pack_still_works(app, client, super_user):
    """回归：纯主题应用不能因为新增 wallpaper 分支而失效。"""
    with app.app_context():
        _wipe()
        with client.session_transaction() as sess:
            sess["user_id"] = super_user
        r = _post(client, {"pack_id": "classic-blue"})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["pack_id"] == "classic-blue"
        # 拼错的 pack_id 必须仍然报错（不能被壁纸分支静默吞掉）
        bad = _post(client, {"pack_id": "no-such-pack"})
        assert bad.status_code == 400