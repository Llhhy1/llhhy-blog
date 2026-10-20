"""v4.7.4 壁纸直接引用媒体库已有文件（不再强制重新上传）。

背景：壁纸配置**本来就存路径引用**（`/static/uploads/<name>`），媒体库文件也在
同一个命名空间里 —— 所以「从媒体库选一张当壁纸」在数据模型上零障碍，缺的只是入口。
但引入「引用」就引入了**引用生命周期**问题：媒体库的文件是可以被删的，
删掉正在当壁纸用的那张，首屏 `background-image` 会直接 404。

这里钉住三件事：
1. **契约**：媒体库产出的 URL 必须能被壁纸白名单接受（否则「从媒体库选」是死的）。
2. **引用判定**：`wallpaper_uses()` 认得出亮色/暗色两个槽位。
3. **删除保护**：正在被壁纸引用的文件删不掉。
"""
import json
import os

import pytest

from models import db, Setting
from api.theme import _safe_wp_url, wallpaper_uses

_FNAME = "1750000000-wall.webp"
_FURL = "/static/uploads/" + _FNAME


def _set_wallpaper(**kw):
    """直接写 Setting KV（绕过 API，聚焦「引用关系」这一层）。"""
    payload = {"enabled": True, "light": _FURL, "dark": "", "overlay": 0.35}
    payload.update(kw)
    row = Setting.query.filter_by(key="home_wallpaper").first()
    if row:
        row.value = json.dumps(payload, ensure_ascii=False)
    else:
        db.session.add(Setting(key="home_wallpaper",
                                value=json.dumps(payload, ensure_ascii=False)))
    db.session.commit()


@pytest.fixture(autouse=True)
def _clean_wp(app):
    """每个用例后清掉壁纸配置，避免相互污染。

    ⚠️ teardown 里必须自己开 app context —— fixture 主体执行完 Flask 上下文
    已经退出，直接 `db.session` 会抛 "Working outside of application context"。
    """
    yield
    with app.app_context():
        db.session.remove()
        Setting.query.filter_by(key="home_wallpaper").delete()
        db.session.commit()


# ---------- 契约：媒体库的 URL 必须是壁纸能接受的形态 ----------


def test_媒体库_url_能被壁纸白名单接受():
    """这一条不成立的话，「从媒体库选」整个功能就是死的。"""
    assert _safe_wp_url(_FURL) == _FURL, \
        "媒体库产出的 /static/uploads/<name> 必须能被壁纸白名单接受"


def test_媒体库产出的_url_形态与壁纸一致():
    """媒体库 `collect_media()` 产出的 url 形态必须落在壁纸白名单里。

    这里用源码级断言锁住两处的口径：媒体的 url 前缀与壁纸的前缀必须相同 ——
    万一哪天媒体库改成别的目录（比如 /static/media/），这个功能会静默失效。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    with open(os.path.join(root, "myblog", "admin", "media.py"), encoding="utf-8") as f:
        media_src = f.read()
    with open(os.path.join(root, "myblog", "api", "theme.py"), encoding="utf-8") as f:
        theme_src = f.read()
    assert '"uploads/"' in media_src, "媒体库 URL 形态变了，需同步壁纸白名单"
    assert '"/static/uploads/"' in theme_src, "壁纸白名单前缀变了，需同步媒体库"


# ---------- 引用判定 ----------


def test_未配置壁纸时不算引用(app):
    with app.app_context():
        Setting.query.filter_by(key="home_wallpaper").delete()
        db.session.commit()
        assert wallpaper_uses(_FNAME) is False


def test_亮色槽位引用可被认出(app):
    with app.app_context():
        _set_wallpaper(light=_FURL)
        assert wallpaper_uses(_FNAME) is True


def test_暗色槽位引用可被认出(app):
    with app.app_context():
        _set_wallpaper(light="", dark=_FURL)
        assert wallpaper_uses(_FNAME) is True


def test_引用别的文件不算(app):
    with app.app_context():
        _set_wallpaper(light="/static/uploads/other.webp")
        assert wallpaper_uses(_FNAME) is False


def test_站外壁纸不算媒体库引用(app):
    """站外壁纸不是媒体库的文件，删媒体库删不到它 —— 不该被拦。"""
    with app.app_context():
        _set_wallpaper(light="https://cdn.example.com/a.jpg")
        assert wallpaper_uses(_FNAME) is False


def test_空文件名不报错(app):
    with app.app_context():
        assert wallpaper_uses("") is False
        assert wallpaper_uses(None) is False


# ---------- 删除保护 ----------


def _make_upload(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"x")
    return p


def test_删除被壁纸引用的文件被拒绝(app, tmp_path):
    from admin.media import delete_media_core
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        _set_wallpaper(light=_FURL)
        _make_upload(tmp_path, _FNAME)
        ok, msg = delete_media_core(_FNAME)
        assert ok is False, "正在当壁纸用的图不能被删掉"
        assert "壁纸" in msg
        assert (tmp_path / _FNAME).exists(), "文件应当还在"


def test_删除未被引用的文件照常成功(app, tmp_path):
    from admin.media import delete_media_core
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        _set_wallpaper(light="/static/uploads/some-other.webp")
        _make_upload(tmp_path, _FNAME)
        ok, msg = delete_media_core(_FNAME)
        assert ok is True, msg
        assert not (tmp_path / _FNAME).exists()


def test_没有壁纸时删除照常成功(app, tmp_path):
    from admin.media import delete_media_core
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        Setting.query.filter_by(key="home_wallpaper").delete()
        db.session.commit()
        _make_upload(tmp_path, _FNAME)
        ok, msg = delete_media_core(_FNAME)
        assert ok is True, msg


# ---------- 入口：两个方向都要有 ----------
# ⚠️ 用**源码级**断言而不是「登录后访问页面」：这两个页面要超管会话，
#   走登录流程会把测试变成一整套认证测试；而这里要守的其实是
#   「模板里有没有这个入口」——静态扫模板更直接、跑得也快
#   （与 tests/test_admin_table_data_label.py 同一手法）。


def _read(rel):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def test_主题中心提供从媒体库选的入口():
    src = _read("myblog/templates/admin/theme_center.html")
    assert "data-wplib" in src, "主题中心缺少「从媒体库选」按钮"
    assert "wp-lib-grid" in src, "主题中心缺少媒体库选择面板"
    assert "{% for it in media %}" in src, "媒体库清单没有渲染进模板"
    # 两个槽位都要有入口（亮色 + 暗色）
    assert src.count("data-wplib=") >= 2, "亮色/暗色两个壁纸槽位都要能选"


def test_主题中心的媒体库选择会写进壁纸状态():
    src = _read("myblog/templates/admin/theme_center.html")
    assert "wp[wpLibTarget] = it.getAttribute('data-url')" in src, \
        "选中媒体库图片后必须写进壁纸状态，否则「从媒体库选」是死的"
    assert "renderWp()" in src, "选择后必须重渲染预览"


def test_媒体库页提供设为壁纸入口():
    src = _read("myblog/templates/admin/media_lib.html")
    assert "set-wallpaper" in src, "媒体库页缺少「设为壁纸」按钮"
    assert "/api/theme" in src, "「设为壁纸」必须走 /api/theme"
    assert "X-CSRF-Token" in src, "写壁纸的请求必须带 CSRF 头"


def test_设为壁纸按钮只对超管渲染():
    """媒体库页是管理员可进，而写壁纸要求超管 —— 权限不同，按钮必须条件渲染。"""
    src = _read("myblog/templates/admin/media_lib.html")
    assert "{% if is_super %}" in src, "「设为壁纸」按钮必须只对超管显示"
    route = _read("myblog/admin/media.py")
    assert "is_super=" in route, "media_lib 路由必须把 is_super 传给模板"


def test_媒体库清单复用同一个实现(app):
    """主题中心与媒体库页必须用**同一个** collect_media()，不能各写一份。"""
    src = _read("myblog/admin/theme_center.py")
    assert "collect_media()" in src, "主题中心应复用 collect_media()，避免两套口径"
    assert "from .media import collect_media" in src
