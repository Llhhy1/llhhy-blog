# -*- coding: utf-8 -*-
"""v4.1.0「多条外部入口」的守卫测试。

主题：**入口从一个变成多个，会引入哪些新的失败模式**。
每一条都不是为了凑数，对应一个具体的坑：

- 多条共存 → 顺序必须由后台控制，不能靠字典序或插入时间碰运气；
- 存在 JSON 里 → 脏数据（坏 JSON / 类型不对）必须退化而不是让后台打不开，
  **后台一旦打不开，管理员就失去了修它的手段**；
- 由旧版迁移而来 → 必须幂等，否则用户在管理页删光入口后，重启又变回来；
- 前台渲染 → 必须收进下拉（``toolbox-menu``），因为 ``flex-wrap: nowrap``
  的导航栏平铺多了会横向撑破，而不是换行。
"""
import contextlib
import json
import secrets

import pytest

from models import db, User, ROLE_SUPER, Setting

PASSWORD = "Passw0rd!23"
APP_VUE = "vue-frontend/src/App.vue"


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()
    yield
    with contextlib.suppress(Exception):
        from utils.net import _RATE
        _RATE.clear()


@pytest.fixture(autouse=True)
def _fresh(app):
    """测试库全 session 共享，每条测试前先把入口清空。"""
    import nav_entries
    with app.app_context():
        nav_entries.save([])
    yield


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


@pytest.fixture()
def super_client(client, app):
    uname = "su_" + secrets.token_hex(4)
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=ROLE_SUPER, must_change_password=False)
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    assert client.post("/api/auth/login", json={"username": uname, "password": PASSWORD},
                       headers={"X-CSRF-Token": _csrf(client)}).status_code == 200
    return client


def _set(app, key, value):
    with app.app_context():
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()


def _load(app):
    import nav_entries
    with app.app_context():
        return nav_entries.load()


def _drop_nav_key(app):
    """把 key 本身删掉 —— 模拟「刚升级、还没迁移过」的旧库状态。

    不能只清成 ``[]``：``migrate_legacy`` 的判据是「这个 key 存不存在」，
    留着一个空数组就等于「已经迁移过了」，迁移会被正确跳过。
    """
    with app.app_context():
        row = Setting.query.filter_by(key="nav_entries").first()
        if row:
            db.session.delete(row)
            db.session.commit()


def _add(client, **fields):
    payload = {"label": "工具", "url": "https://x.example.com", "icon": "🔧"}
    payload.update(fields)
    return client.post("/admin/nav-entries/add", data=payload,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


def _post(client, path, **fields):
    return client.post(path, data=fields,
                       headers={"X-CSRF-Token": _csrf(client)}, follow_redirects=True)


# ---------- 1. 多条共存与顺序 ----------

def test_api_site_emits_all_entries_in_order(client, app):
    """顺序 = 存储顺序（后台上下移决定），不能是别的。"""
    import nav_entries
    with app.app_context():
        nav_entries.save([
            {"id": nav_entries.new_id(), "label": "一号", "url": "https://a.example.com",
             "icon": "1️⃣", "enabled": True},
            {"id": nav_entries.new_id(), "label": "二号", "url": "https://b.example.com",
             "icon": "2️⃣", "enabled": True},
        ])
    got = (client.get("/api/site").get_json() or {}).get("entries") or []
    assert [x["label"] for x in got] == ["一号", "二号"], "前台顺序必须与后台一致"
    assert [x["url"] for x in got] == ["https://a.example.com", "https://b.example.com"]


def test_disabled_entry_is_hidden_from_list(client, app):
    import nav_entries
    with app.app_context():
        nav_entries.save([
            {"id": nav_entries.new_id(), "label": "可见", "url": "https://a.example.com",
             "icon": "", "enabled": True},
            {"id": nav_entries.new_id(), "label": "隐藏", "url": "https://b.example.com",
             "icon": "", "enabled": False},
        ])
    got = (client.get("/api/site").get_json() or {}).get("entries") or []
    assert [x["label"] for x in got] == ["可见"]


def test_move_down_swaps_order(super_client, app):
    _add(super_client, label="上", url="https://a.example.com")
    _add(super_client, label="下", url="https://b.example.com")
    first_id = _load(app)[0]["id"]
    assert _post(super_client, "/admin/nav-entries/%s/move?dir=down" % first_id).status_code == 200
    assert [x["label"] for x in _load(app)] == ["下", "上"], "下移必须真的换位置"


def test_move_up_at_top_is_noop(super_client, app):
    """顶端的条目再上移：静默不动，不能报 500 也不能绕到末尾（成环）。"""
    _add(super_client, label="唯一", url="https://a.example.com")
    eid = _load(app)[0]["id"]
    assert _post(super_client, "/admin/nav-entries/%s/move?dir=up" % eid).status_code == 200
    assert [x["label"] for x in _load(app)] == ["唯一"]


def test_move_rejects_bad_direction(super_client, app):
    """方向参数必须白名单 —— 不接受任意值，也不允许注入。"""
    _add(super_client, label="唯一", url="https://a.example.com")
    eid = _load(app)[0]["id"]
    assert _post(super_client, "/admin/nav-entries/%s/move?dir=sideways" % eid).status_code == 200
    assert len(_load(app)) == 1, "非法方向不应改动数据"


def test_delete_removes_only_target(super_client, app):
    _add(super_client, label="留", url="https://a.example.com")
    _add(super_client, label="删", url="https://b.example.com")
    target = [x for x in _load(app) if x["label"] == "删"][0]["id"]
    assert _post(super_client, "/admin/nav-entries/%s/delete" % target).status_code == 200
    assert [x["label"] for x in _load(app)] == ["留"]


# ---------- 2. 上限 ----------

def test_add_respects_max_items(super_client, app):
    import nav_entries
    for i in range(nav_entries.MAX_ITEMS):
        r = _add(super_client, label="T%d" % i, url="https://x%d.example.com" % i)
        assert r.status_code == 200
    assert len(_load(app)) == nav_entries.MAX_ITEMS

    r = _add(super_client, label="超了", url="https://overflow.example.com")
    assert len(_load(app)) == nav_entries.MAX_ITEMS, "超过上限必须拒绝"
    assert "上限" in r.get_data(as_text=True), "必须告诉用户为什么加不进去"


# ---------- 3. 存储层的脏数据容错 ----------

@pytest.mark.parametrize("raw", [
    "{坏掉的 json",
    "null",
    '"一个字符串"',
    '{"不是": "数组"}',
    "",
    "[]",
])
def test_load_tolerates_corrupt_payload(app, raw):
    """任何脏数据都必须退化成「空/跳过」而不是抛异常。

    后台一旦因为一行脏数据打不开，管理员连修改的机会都没有 —— 那才是最坏的结果。
    """
    _set(app, "nav_entries", raw)
    assert _load(app) == [], f"脏数据 {raw!r} 应退化为空列表，而不是崩溃"


def test_load_skips_non_dict_items(app):
    _set(app, "nav_entries", json.dumps([
        1, "字符串", None, {"url": "https://ok.example.com", "label": "好的",
                            "icon": "", "enabled": True},
    ]))
    items = _load(app)
    assert len(items) == 1, "非 dict 项必须跳过而不是让整列失效"
    assert items[0]["url"] == "https://ok.example.com"


def test_load_clamps_overlong_fields(app):
    """超长字段必须在读取侧截断 —— 与前台写入侧的 maxlength 互为兜底。"""
    _set(app, "nav_entries", json.dumps([
        {"id": "x", "url": "https://ok.example.com", "label": "名" * 100,
         "icon": "图" * 50, "enabled": True},
    ]))
    it = _load(app)[0]
    assert len(it["label"]) <= 20
    assert len(it["icon"]) <= 8


# ---------- 4. 旧版迁移（幂等） ----------

def test_migrate_legacy_creates_first_entry(app):
    _drop_nav_key(app)
    _set(app, "entry_enabled", "true")
    _set(app, "entry_label", "百宝箱")
    _set(app, "entry_url", "https://box.llhhy.cn")
    _set(app, "entry_icon", "🧰")
    with app.app_context():
        import nav_entries
        assert nav_entries.migrate_legacy() is True
    items = _load(app)
    assert len(items) == 1
    assert items[0]["url"] == "https://box.llhhy.cn"
    assert items[0]["label"] == "百宝箱"
    assert items[0]["enabled"] is True, "原开关为开 → 迁移后仍为开"


def test_migrate_legacy_respects_disabled_switch(app):
    _drop_nav_key(app)
    _set(app, "entry_enabled", "false")
    _set(app, "entry_url", "https://box.llhhy.cn")
    with app.app_context():
        import nav_entries
        nav_entries.migrate_legacy()
    assert _load(app)[0]["enabled"] is False, "原来是关的，迁移后不能擅自变成开"


def test_migrate_legacy_runs_only_once(app):
    """**幂等是这里的命门**：不幂等 = 用户在管理页删光入口后，重启又变回来，
    表现为「删不掉」，而谁也不会想到是迁移的问题。
    """
    _drop_nav_key(app)
    _set(app, "entry_url", "https://box.llhhy.cn")
    with app.app_context():
        import nav_entries
        assert nav_entries.migrate_legacy() is True
        nav_entries.save([])                    # 用户在管理页把入口删光了
        assert nav_entries.migrate_legacy() is False, "已迁移过就绝不能再迁一次"
        assert nav_entries.load() == [], "删光后重启不应把旧配置变回来"


def test_migrate_legacy_without_old_url_seals_the_key(app):
    """旧配置没有地址时，也要把 key 落成空 —— 否则每次启动都重试迁移。"""
    _drop_nav_key(app)
    _set(app, "entry_url", "")
    with app.app_context():
        import nav_entries
        assert nav_entries.migrate_legacy() is False
        assert nav_entries.load() == []


# ---------- 5. 前台：必须收进下拉，不能平铺 ----------

def test_front_renders_entries_as_toolbox_dropdown():
    """入口由 v-for 渲染并放进下拉容器 —— 这两点合起来才解决「多了撑破导航」。

    静态扫描源码即可：守的是「写法别被后人改回平铺」，跑得快也够用。
    """
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, APP_VUE), "r", encoding="utf-8") as f:
        src = f.read()

    assert "nav-toolbox" in src, "入口应收进 .nav-toolbox 下拉容器"
    assert "toolbox-menu" in src, "下拉菜单容器缺失"

    lines = [ln for ln in src.splitlines() if "site-entry-link" in ln and "<a" in ln]
    assert len(lines) >= 2, "桌面导航与移动端抽屉都要有"
    for ln in lines:
        assert "v-for" in ln, f"入口必须由 v-for 渲染以支持多条：{ln.strip()}"
        assert 'rel="noopener"' in ln, f"外域链接必须带 noopener：{ln.strip()}"
        assert 'target="_blank"' in ln
        assert ":href" in ln


# ---------- 6. 中英文适配（v4.8.1） ----------

def _src(rel):
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, rel), "r", encoding="utf-8") as f:
        return f.read()


def test_load_keeps_and_clamps_label_en(app):
    """英文名要在读取侧保留并截断 —— 与前台 maxlength 互为兜底。"""
    _set(app, "nav_entries", json.dumps([
        {"id": "a", "url": "https://ok.example.com", "label": "百宝箱",
         "label_en": "Toolbox", "enabled": True},
    ]))
    it = _load(app)[0]
    assert it["label_en"] == "Toolbox"
    _set(app, "nav_entries", json.dumps([
        {"id": "b", "url": "https://ok.example.com", "label": "百宝箱",
         "label_en": "E" * 100, "enabled": True},
    ]))
    assert len(_load(app)[0]["label_en"]) <= 40


def test_load_defaults_label_en_to_empty(app):
    """老数据没有 label_en → 补空串（前台据此回退中文名，不会渲染成 undefined）。"""
    _set(app, "nav_entries", json.dumps([
        {"id": "c", "url": "https://ok.example.com", "label": "百宝箱", "enabled": True},
    ]))
    assert _load(app)[0]["label_en"] == ""


def test_api_site_emits_label_en(client, app):
    _set(app, "nav_entries", json.dumps([
        {"id": "d", "url": "https://ok.example.com", "label": "百宝箱",
         "label_en": "Toolbox", "enabled": True},
    ]))
    entries = client.get("/api/site").get_json()["entries"]
    assert entries[0]["label"] == "百宝箱"
    assert entries[0]["label_en"] == "Toolbox"


def test_admin_add_and_edit_save_label_en(super_client, app):
    _add(super_client, label="百宝箱", label_en="Toolbox", url="https://box.example.com")
    items = _load(app)
    assert items and items[0]["label_en"] == "Toolbox"
    _post(super_client, "/admin/nav-entries/%s/edit" % items[0]["id"],
          label="百宝箱", label_en="Tools", url="https://box.example.com")
    assert _load(app)[0]["label_en"] == "Tools"


def test_front_toolbox_button_uses_i18n_not_hardcoded_chinese():
    """「工具箱」按钮必须走 i18n —— 之前是硬编码中文，切英文界面纹丝不动。

    变异验证：把 `{{ t('toolbox') }}` 改回字面量「工具箱」，此题应变红。
    """
    src = _src(APP_VUE)
    toggles = [ln for ln in src.splitlines() if "site-toolbox-toggle" in ln and "🧰" in ln]
    assert len(toggles) >= 2, "桌面导航与抽屉都应该有工具箱按钮：%d" % len(toggles)
    for ln in toggles:
        assert "t('toolbox')" in ln, f"工具箱按钮硬编码了中文（切英文不会变）：{ln.strip()}"
        assert ">工具箱" not in ln


def test_i18n_dict_has_toolbox_in_both_languages():
    """字典缺键时 t() 会退回中文 —— 那英文界面就又露中文了。"""
    src = _src("vue-frontend/src/store.js")
    assert '"toolbox": "工具箱"' in src
    assert '"toolbox": "Toolbox"' in src


def test_i18n_zh_en_keys_are_paired():
    """zh/en 必须键键齐平 —— 缺的那个会让英文界面退回中文（t() 的回退链）。"""
    src = _src("vue-frontend/src/store.js")
    zh = _dict_keys(src, "zh")
    en = _dict_keys(src, "en")
    assert zh, "没解析到 zh 词典"
    missing_en = sorted(zh - en)
    missing_zh = sorted(en - zh)
    assert not missing_en, "en 缺这些键（切英文会退回中文）：%s" % missing_en
    assert not missing_zh, "zh 缺这些键：%s" % missing_zh


def _dict_keys(src, lang):
    """从一个语言块里抠出所有键名。块以 `lang: {` 起、下一个 `\n  },` 止。"""
    import re as _re
    i = src.find(lang + ": {")
    if i == -1:
        return set()
    j = src.find("\n  },", i)
    if j == -1:
        j = len(src)
    return set(_re.findall(r'"([^"]+)"\s*:', src[i:j]))


def test_t_supports_placeholder_vars():
    """`t('stats_line', {p,c})` 这类带参文案必须能替换 —— 否则前台会露出 "{p} 篇"。"""
    src = _src("vue-frontend/src/store.js")
    assert "for (const k in vars)" in src, "t() 没有实现变量替换"
    assert 's.split("{" + k + "}")' in src


def test_global_components_have_no_hardcoded_ui_chinese():
    """侧栏 / 天气 / App 壳这些每页可见的组件，不能再出现硬编码中文 UI 文案。

    变异验证：把 Sidebar 里某个 t('...') 改回字面量中文，此题应变红。
    ⚠️ 要剥掉行内 `//` 注释再判 —— 注释是给开发者看的，不随语言切换，不算缺陷。
    """
    for rel in ("vue-frontend/src/components/Sidebar.vue",
                "vue-frontend/src/components/WeatherWidget.vue"):
        src = _src(rel)
        for i, ln in enumerate(src.splitlines(), 1):
            s = ln.strip()
            code = s.split("//", 1)[0].strip()   # 剥掉行内注释
            if code.startswith("/*") or code.startswith("*") or code.startswith("<!--"):
                continue
            if not code:
                continue
            if _has_cjk(code) and "t(" not in code:
                raise AssertionError("%s:%d 还有硬编码中文（切英文不会变）：%s" % (rel, i, s[:100]))


def _has_cjk(s):
    return any(chr(0x4e00) <= c <= chr(0x9fff) for c in s)


def test_front_entry_label_prefers_english_when_lang_is_en():
    """英文界面优先取 label_en，没配则回退中文名（既有配置不会突然变空）。"""
    src = _src(APP_VUE)
    assert 'state.lang === "en" && e.label_en' in src, \
        "siteEntries 没有按语言挑选条目名"