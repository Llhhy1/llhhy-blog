# -*- coding: utf-8 -*-
"""v5.5.0 ②③ 站主主题库 / 主题市场 / 外观回滚 守卫。

钉住五条容易「改了没生效」或「静默降安全级别」的边界：

1. **权限**：库读取与四个动作只有超管能做。
2. **导入信任边界**：第三方包必须剥掉 CSS、标注来源、id 不撞内置包。
3. **派生 token 重算**：站主只改主色并把完整 token 提交回来时，hover / soft /
   muted 与整套暗色必须跟着重算（否则「主色换了但其余还停在旧主题」）。
4. **回滚时序**：快照里必须是**切换前**的五个 Setting 原值，不能拍到新值；
   回滚后当前外观成为新的回滚目标（可反悔）。
5. **不回归**：主题包 schema、文档同步、访客换肤缺席守卫仍绿。
"""
import copy
import json
import os
import secrets
import uuid

import pytest

from models import db, User, Setting, ROLE_SUPER, ROLE_ADMIN
from utils import _sign_csrf
import theme_bundles as bundles
import theme_library as library

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACK = os.path.join(_ROOT, "myblog", "theme_packs", "zhanghui.json")
_KEYS = (bundles.ACTIVE_KEY, "theme_pack", "theme_tokens", "accent_color",
         "home_wallpaper", library.LIBRARY_KEY, library.PREV_KEY)


@pytest.fixture(autouse=True)
def _ctx(app):
    """DB 操作需要应用上下文；每个用例后清掉本文件写过的 Setting 键。

    测试库是全 session 共享的（见 conftest），不清会互相污染，
    也会让后续用例读到「上一套外观」这种跨用例残留。
    """
    with app.app_context():
        yield
        for k in _KEYS:
            for row in Setting.query.filter_by(key=k).all():
                db.session.delete(row)
        db.session.commit()


def _uid():
    return uuid.uuid4().hex[:10]


def _mkuser(role=ROLE_SUPER):
    u = User(username="tl-" + _uid(), email="tl-%s@test.local" % _uid())
    u.set_password("test-pass")
    u.role = role
    u.must_change_password = False
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, u):
    raw = secrets.token_hex(24)
    with client.application.app_context():
        tok = raw + "." + _sign_csrf(raw)
    with client.session_transaction() as s:
        s["user_id"] = u.id
        s["_fresh"] = True
        s["csrf_token"] = tok


def _post(client, url, body):
    payload = dict(body)
    with client.session_transaction() as s:
        payload.setdefault("csrf_token", s.get("csrf_token", ""))
    return client.post(url, json=payload)


def _base():
    with open(_PACK, encoding="utf-8") as f:
        return json.load(f)


def _as_super(client):
    u = _mkuser(ROLE_SUPER)
    _login(client, u)
    return u


def _kv(key):
    row = Setting.query.filter_by(key=key).first()
    return row.value if row and row.value is not None else ""


# ---------- 1. 权限 ----------

def test_库读取需要超管(app, client):
    assert client.get("/api/theme/library").status_code == 403
    u = _mkuser(ROLE_ADMIN)
    _login(client, u)
    assert client.get("/api/theme/library").status_code == 403
    _as_super(client)
    assert client.get("/api/theme/library").status_code == 200


def test_库操作需要超管(app, client):
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": _base()})
    assert r.status_code == 403
    u = _mkuser(ROLE_ADMIN)
    _login(client, u)
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": _base()})
    assert r.status_code == 403


# ---------- 2. 保存 / 导入 ----------

def test_保存自建主题并出现在库中(app, client):
    _as_super(client)
    raw = _base()
    raw["id"] = "my-dark-" + _uid()
    raw["name"] = "我的墨色"
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": raw})
    assert r.status_code == 200, r.get_json()
    item = r.get_json()["item"]
    assert item["origin"] == "own"
    assert item["name"] == "我的墨色"

    d = client.get("/api/theme/library").get_json()
    ids = [it["id"] for it in d["items"]]
    assert item["id"] in ids
    assert d["builtins"] and d["builtins"][0]["id"] == "zhanghui"
    assert d["limits"]["max_items"] == library.MAX_ITEMS


def test_保存坏包返回400且不落库(app, client):
    _as_super(client)
    raw = _base()
    raw["layout"]["mode"] = "drop-all-tables"
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": raw})
    assert r.status_code == 400
    assert r.get_json()["details"]
    assert client.get("/api/theme/library").get_json()["items"] == []


def test_保存时派生token与暗色按新主色重算(app, client):
    """站主把编辑器返回的**完整** token 原样提交回来，只改了主色。

    若不做归一化，accent_hover / accent_soft / info / text_muted 与整套 dark
    会沿用旧主题的颜色 —— 这正是本项目反复出现过的「半新半旧」加载错误。
    """
    _as_super(client)
    clean, errors = bundles.validate_bundle(_base())
    assert not errors
    old_dark = copy.deepcopy(clean["tokens"]["dark"])
    new_accent = "#2F6B4F"
    edited = copy.deepcopy(clean)
    edited["id"] = "recolor-" + _uid()
    edited["tokens"]["light"]["accent"] = new_accent
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": edited})
    assert r.status_code == 200, r.get_json()
    light = r.get_json()["bundle"]["tokens"]["light"]
    dark = r.get_json()["bundle"]["tokens"]["dark"]
    assert light["accent"] == new_accent
    assert light["info"] == new_accent                    # normalize 按主色重算
    assert light["accent_hover"] != clean["tokens"]["light"]["accent_hover"]
    assert dark != old_dark                               # 暗色按新亮色重推


def test_导入包强制剥离CSS且id不撞内置(app, client):
    _as_super(client)
    raw = _base()
    raw["id"] = "zhanghui"                 # 故意与内置包同名
    raw["css"] = ".zh-card { color: #fff; }"   # 命名空间内、本来合法
    r = _post(client, "/api/theme/library", {"action": "import", "bundle": raw})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["bundle"]["css"] == ""
    assert d["item"]["origin"] == "imported"
    assert d["item"]["css_disabled"] is True
    assert d["item"]["id"].startswith("imp-")
    assert d["item"]["id"] != "zhanghui"
    assert "第三方自定义 CSS 已按安全策略禁用" in d["bundle"]["source"]
    # 内置包没被覆盖
    assert bundles.get_bundle("zhanghui") is not None
    assert bundles.get_bundle("zhanghui")["css"] == ""


def test_导入包带危险CSS直接拒绝(app, client):
    _as_super(client)
    raw = _base()
    raw["css"] = ".zh-card { background: url(https://evil.example/x); }"
    r = _post(client, "/api/theme/library", {"action": "import", "bundle": raw})
    assert r.status_code == 400
    assert any("url(" in x for x in r.get_json()["details"])


def test_导入字符串JSON与未知action(app, client):
    _as_super(client)
    raw = _base()
    raw["id"] = "from-text-" + _uid()
    r = _post(client, "/api/theme/library",
              {"action": "import", "text": json.dumps(raw, ensure_ascii=False)})
    assert r.status_code == 200, r.get_json()
    r = _post(client, "/api/theme/library", {"action": "import", "text": "{oops"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid json"
    r = _post(client, "/api/theme/library", {"action": "fly-to-moon"})
    assert r.status_code == 400 and r.get_json()["error"] == "unknown action"


def test_容量上限会拒绝并给原因(app, client, monkeypatch):
    _as_super(client)
    monkeypatch.setattr(library, "MAX_ITEMS", 2)
    for i in range(2):
        raw = _base()
        raw["id"] = "cap-%d-%s" % (i, _uid())
        assert _post(client, "/api/theme/library",
                     {"action": "save", "bundle": raw}).status_code == 200
    raw = _base()
    raw["id"] = "cap-over-" + _uid()
    r = _post(client, "/api/theme/library", {"action": "save", "bundle": raw})
    assert r.status_code == 400
    assert any("已满" in x for x in r.get_json()["details"])


# ---------- 3. 应用 / 删除 / 回滚 ----------

def test_应用库内包后site下发且可回滚(app, client):
    _as_super(client)
    # 先应用内置包作为「上一套外观」
    r0 = _post(client, "/api/theme", {"bundle_id": "zhanghui"})
    assert r0.status_code == 200, r0.get_json()
    before = {k: _kv(k) for k in library.LOOK_KEYS}

    raw = _base()
    raw["id"] = "lib-apply-" + _uid()
    raw["palette"]["seal"] = "#2F6B4F"
    saved = _post(client, "/api/theme/library", {"action": "save", "bundle": raw})
    iid = saved.get_json()["item"]["id"]
    r = _post(client, "/api/theme", {"bundle_id": "lib:" + iid})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["bundle_id"] == "lib:" + iid
    site = client.get("/api/site").get_json()
    assert site["theme_bundle"]["id"] == iid
    assert site["theme_bundle"]["palette"]["seal"] == "#2F6B4F"

    # 快照必须是切换前那套，绝不能拍到新值
    prev = library.prev_summary()
    assert prev["label"] == "章回"
    pv = json.loads(_kv(library.PREV_KEY))
    assert pv["look"] == before

    rb = _post(client, "/api/theme/library", {"action": "rollback"})
    assert rb.status_code == 200, rb.get_json()
    assert rb.get_json()["label"] == "章回"
    assert {k: _kv(k) for k in library.LOOK_KEYS} == before
    assert client.get("/api/site").get_json()["theme_bundle"]["id"] == "zhanghui"

    # 反悔：再回滚一次应回到自建主题
    rb2 = _post(client, "/api/theme/library", {"action": "rollback"})
    assert rb2.status_code == 200
    assert _kv(bundles.ACTIVE_KEY) == "lib:" + iid


def test_无历史时回滚返回400(app, client):
    _as_super(client)
    r = _post(client, "/api/theme/library", {"action": "rollback"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "nothing to rollback"


def test_正在使用的主题不可删_内置包不可删(app, client):
    _as_super(client)
    raw = _base()
    raw["id"] = "no-del-" + _uid()
    iid = _post(client, "/api/theme/library",
                {"action": "save", "bundle": raw}).get_json()["item"]["id"]
    _post(client, "/api/theme", {"bundle_id": "lib:" + iid})
    r = _post(client, "/api/theme/library", {"action": "delete", "id": iid})
    assert r.status_code == 400
    assert any("正在使用" in x for x in r.get_json()["details"])
    r = _post(client, "/api/theme/library", {"action": "delete", "id": "zhanghui"})
    assert r.status_code == 400
    assert bundles.get_bundle("zhanghui") is not None


def test_解析库内包与损坏KV的降级(app, client):
    _as_super(client)
    raw = _base()
    raw["id"] = "resolve-" + _uid()
    iid = _post(client, "/api/theme/library",
                {"action": "save", "bundle": raw}).get_json()["item"]["id"]
    assert bundles.resolve_bundle("lib:" + iid)["id"] == iid
    assert bundles.resolve_bundle("lib:not-exist") is None
    row = Setting.query.filter_by(key=library.LIBRARY_KEY).first()
    row.value = "{坏掉的 JSON"
    db.session.commit()
    assert library.library_data()["items"] == []
    assert bundles.resolve_bundle("lib:" + iid) is None   # 坏包不会下发到前台


# ---------- 4. 前后台契约与不回归 ----------

def test_后台工坊不提供任意CSS输入框():
    p = os.path.join(_ROOT, "myblog", "templates", "admin", "theme_center.html")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    assert "data-path=\"css\"" not in s
    assert "data-path=\"tokens.dark" not in s
    assert "tc_preview=1" in s
    # 市场卡片的缩略图只能用具体样式属性上色。写 CSS 变量会把前台主题注入
    # 带进后台，破坏「后台配色只来自 tokens.css」的单一真相源。
    assert "setProperty" not in s
    assert "applyThemeTokens" not in s


def test_前台预览标记跳过统计代码注入():
    p = os.path.join(_ROOT, "vue-frontend", "src", "store.js")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    seg = s[s.index("injectCustomCss(s.custom_css);"):]
    assert "tc_preview=1" in seg
    assert seg.index("tc_preview=1") < seg.index("injectFooterCode(s.footer_html);")


def test_外观快照五键与模块常量一致():
    assert library.LOOK_KEYS[0] == bundles.ACTIVE_KEY
    assert len(library.LOOK_KEYS) == 5
    assert "home_wallpaper" in library.LOOK_KEYS
