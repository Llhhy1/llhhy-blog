"""page_translate 插件测试（v3.18.0 · 全站翻译）。

覆盖三块：
1. 加载与声明：插件加载进 /api/plugins、声明同源远程组件、widget.js 存在非空、不占核心槽位；
2. /config：返回源/目标语言与 LLM 可用性；
3. /translate：CSRF 前置（403）、目标语言白名单（400）、空/超长（400）、未配置 LLM（503）、
   monkeypatch LLM 后的成功路径（含 ```json 围栏鲁棒解析、条数不匹配 502）。
"""
import json
import os


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return d.get("csrf_token") or d.get("token") or ""


def _post(client, payload, with_csrf=True):
    headers = {"X-CSRF-Token": _csrf(client)} if with_csrf else {}
    return client.post("/api/plugin/page_translate/translate", json=payload, headers=headers)


# ---------------- 加载与声明 ----------------

def test_plugin_loaded_and_declares_remote_component(client):
    data = client.get("/api/plugins").get_json()
    assert "page_translate" in [p["id"] for p in data["plugins"]]
    urls = [rc["url"] for rc in data.get("remote_components", [])]
    assert "/static/plugins/page_translate/widget.js" in urls


def test_remote_component_is_same_origin_only(client):
    data = client.get("/api/plugins").get_json()
    for rc in data.get("remote_components", []):
        assert rc["url"].startswith("/static/plugins/"), "远程组件只允许同源 /static/plugins/ 前缀"


def test_plugin_declares_no_core_slots(client):
    data = client.get("/api/plugins").get_json()
    me = [p for p in data["plugins"] if p["id"] == "page_translate"][0]
    assert me["slots"] == [], "翻译插件为纯前端远程组件，不应占用核心槽位"


def test_widget_file_exists_and_nonempty():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "myblog", "static", "plugins", "page_translate", "widget.js")
    assert os.path.isfile(p), "widget.js 缺失（打包前守卫）"
    assert os.path.getsize(p) > 1000
    with open(p, encoding="utf-8") as f:
        src = f.read()
    # 注册名与宿主契约必须存在
    assert "__pluginRegister" in src and "page_translate_widget" in src


# ---------------- /config ----------------

def test_config_returns_langs_and_engine(client):
    d = client.get("/api/plugin/page_translate/config").get_json()
    assert isinstance(d.get("source"), str) and d["source"]
    assert d.get("target") in ("zh", "en")
    assert isinstance(d.get("llm_on"), bool)


# ---------------- /translate：安全与参数校验 ----------------

def test_translate_requires_csrf(client):
    r = client.post("/api/plugin/page_translate/translate",
                    json={"target": "en", "texts": ["你好"]})
    assert r.status_code == 403


def test_translate_rejects_bad_target(client):
    assert _post(client, {"target": "xx", "texts": ["你好"]}).status_code == 400


def test_translate_rejects_empty_texts(client):
    assert _post(client, {"target": "en", "texts": []}).status_code == 400


def test_translate_rejects_non_list(client):
    assert _post(client, {"target": "en", "texts": "not-a-list"}).status_code == 400


def test_translate_rejects_oversized(client):
    r = _post(client, {"target": "en", "texts": ["y" * 3000, "z" * 3000]})
    assert r.status_code == 400


def test_translate_without_llm_returns_503(monkeypatch, client):
    """LLM 未配置 → 503（可读错误，绝不 500）。"""
    import plugins.page_translate as pt
    monkeypatch.setattr(pt, "_llm_ready", lambda: False)
    assert _post(client, {"target": "en", "texts": ["你好世界"]}).status_code == 503


# ---------------- /translate：成功路径（monkeypatch LLM） ----------------

def test_translate_success(monkeypatch, client):
    import api.ai as ai
    import plugins.page_translate as pt

    def fake_chat(system, user, timeout=90):
        return json.dumps(["EN:" + t for t in json.loads(user)], ensure_ascii=False), ""

    monkeypatch.setattr(ai, "_llm_chat", fake_chat)
    monkeypatch.setattr(pt, "_llm_ready", lambda: True)
    r = _post(client, {"target": "en", "texts": ["你好", "世界"]})
    assert r.status_code == 200
    assert r.get_json()["translations"] == ["EN:你好", "EN:世界"]


def test_translate_parses_fenced_json(monkeypatch, client):
    import api.ai as ai
    import plugins.page_translate as pt
    monkeypatch.setattr(ai, "_llm_chat", lambda s, u, timeout=90: ('```json\n["Hello"]\n```', ""))
    monkeypatch.setattr(pt, "_llm_ready", lambda: True)
    r = _post(client, {"target": "en", "texts": ["你好"]})
    assert r.status_code == 200
    assert r.get_json()["translations"] == ["Hello"]


def test_translate_length_mismatch_502(monkeypatch, client):
    import api.ai as ai
    import plugins.page_translate as pt
    monkeypatch.setattr(ai, "_llm_chat", lambda s, u, timeout=90: ('["only-one"]', ""))
    monkeypatch.setattr(pt, "_llm_ready", lambda: True)
    assert _post(client, {"target": "en", "texts": ["甲", "乙"]}).status_code == 502
