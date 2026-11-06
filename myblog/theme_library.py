# -*- coding: utf-8 -*-
"""站主主题库与「上一套外观」快照（v5.5.0 第 ②③ 步）。

定位
----
主题包（``myblog/theme_packs/*.json``）是**随部署包分发的只读资产**；这里存的是
**站主自己在本站后台做的主题**（新建 / 编辑 / 导入），以及换主题前的回滚快照。
两者共用 :func:`theme_bundles.validate_bundle` 的同一套白名单，只是信任级别不同。

为什么不建表
-------------
主题库是「一个站点的几十份 JSON」，读写频率极低，且天然是键值结构。沿用 ``Setting``
KV 与项目既有纪律（能不改表就不改表），不引入迁移、不动生产库结构。

信任边界（本模块最要紧的一条）
-----------------------------
- ``own``：站主在可视化编辑器里逐项调出来的，**编辑器不提供 CSS 输入框**，
  其信任级别与站点设置里的 ``custom_css`` 相同（站主本人写的代码）。
- ``imported``：第三方 JSON。**导入时强制把 ``css`` 置空**并改写 ``source`` 标注。
  原因不是「CSS 一定恶意」，而是内置包随代码分发、站主自己写的自己负责，
  唯有导入包是别人写的代码 —— 三者不能混用同一个信任级别。
  颜色 / 字体 / 布局仍全部可用（它们本来就是被白名单穷举的声明式数据）。
- ``css`` 之外的危险面由 ``themes.sanitize_theme_tokens`` 兜住：token 值禁
  ``url(`` / ``@`` / ``;`` / ``:`` / 尖括号 / 花括号，第三方包塞不进外联信标。

快照为什么存「五个 Setting 原值」而不是存主题 id 再重放
------------------------------------------------------
主题状态散在 ``theme_bundle_id`` / ``theme_pack`` / ``accent_color`` /
``theme_tokens`` / ``home_wallpaper`` 五个键里，还有「预设 / 自定义 / 内置包 /
库内包」四种来源。存 id 再重放等于要复刻整套应用逻辑，任何一处漏了就是回滚后
「颜色回来了但布局没回来」。直接整组恢复原值是**可逆性最强**的做法。

⚠️ 时序：``capture_look()`` 必须在任何 ``set_kv`` 之前调用。SQLAlchemy 的
identity map 会让之后的查询读到同一 session 里尚未提交的新值，晚一步就拍到
「新外观」而不是「上一套」。
"""
import datetime
import json
import re

from models import Setting, db
from themes import PRESET_MAP
from theme_bundles import ACTIVE_KEY, validate_bundle, list_bundles, get_bundle

LIBRARY_KEY = "theme_library_v1"
PREV_KEY = "theme_look_prev_v1"

# 「一套外观」的全部状态。改这里必须同步 capture_look / rollback 与测试。
LOOK_KEYS = (ACTIVE_KEY, "theme_pack", "accent_color", "theme_tokens", "home_wallpaper")

MAX_ITEMS = 24
MAX_ITEM_BYTES = 16 * 1024
MAX_TOTAL_BYTES = 192 * 1024

ORIGINS = ("own", "imported")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _read_kv(key):
    row = Setting.query.filter_by(key=key).first()
    return row.value if row and row.value is not None else ""


def _write_kv(key, val):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = val
    else:
        db.session.add(Setting(key=key, value=val))


def _read_json(key, fallback):
    try:
        d = json.loads(_read_kv(key) or "")
    except (TypeError, ValueError):
        return fallback
    return d if isinstance(d, type(fallback)) else fallback


def _bytes(obj):
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


# ---------------------------------------------------------------------------
# 主题库
# ---------------------------------------------------------------------------

def library_data():
    """返回规范化后的库结构；KV 损坏时回落空库，不让后台 500。"""
    d = _read_json(LIBRARY_KEY, {})
    items = d.get("items") if isinstance(d, dict) else None
    if not isinstance(items, list):
        items = []
    clean = []
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = it.get("id")
        bundle = it.get("bundle")
        if not isinstance(iid, str) or not _ID_RE.match(iid) or not isinstance(bundle, dict):
            continue
        b, errors = validate_bundle(bundle)
        if errors:
            continue
        clean.append({
            "id": iid,
            "name": it.get("name") if isinstance(it.get("name"), str) else b["name"],
            "origin": it.get("origin") if it.get("origin") in ORIGINS else "own",
            "saved_at": it.get("saved_at") if isinstance(it.get("saved_at"), str) else "",
            "bundle": b,
        })
    return {"schema": 1, "items": clean}


def get_item(item_id):
    for it in library_data()["items"]:
        if it["id"] == item_id:
            return it
    return None


def _slug(s):
    return re.sub(r"[^a-z0-9-]+", "-", str(s).lower()).strip("-")[:24] or "theme"


def _unique_id(base, taken):
    b = _slug(base)
    if len(b) < 2:
        b = "theme"
    if b not in taken:
        return b
    for i in range(2, 100):
        cand = "%s-%d" % (b[:22], i)
        if cand not in taken:
            return cand
    return None


_DERIVED_TOKENS = ("accent_hover", "accent_soft", "info", "on_accent",
                   "text_muted", "text_faint")


def _strip_derived_tokens(raw):
    """编辑器保存前剥掉「由主色推导」的键，让服务端按新 accent 重算。

    后台拿到的是 `validate_bundle` 补齐后的**完整** token（含 accent_hover、
    text_muted 与整套 dark）。站主只改了主色却把这一整份原样提交回来时，
    `normalize_custom_theme` 看到这些键已经存在就**不会重算** —— 结果是
    「主色变了、hover/soft/muted 与整套暗色还停在旧主题」，正是本项目反复
    出现过的一类加载错误。它们本来就是派生量，不该被当成站主输入持久化。

    注意这是**原地修改传入 dict**，调用方拿到的就是我们准备落库的同一份。
    """
    if not isinstance(raw, dict):
        return
    tok = raw.get("tokens")
    if not isinstance(tok, dict):
        return
    light = tok.get("light")
    if isinstance(light, dict):
        for k in _DERIVED_TOKENS:
            light.pop(k, None)
    tok.pop("dark", None)   # 暗色一律按新亮色由 OKLCH 重新推导


def save_item(raw, overwrite_id=None, origin="own"):
    """保存一份主题包到库，返回 ``(item, errors)``。

    ``overwrite_id`` 为空 ⇒ 新建（自动分配不撞内置包的 id）；非空 ⇒ 覆盖指定
    条目并保留其 ``origin``（站主编辑导入包**不会**把它的信任级别洗白）。
    """
    if origin not in ORIGINS:
        return None, ["origin 非法"]
    _strip_derived_tokens(raw)
    clean, errors = validate_bundle(raw)
    if errors:
        return None, errors

    data = library_data()
    items = data["items"]
    taken = {it["id"] for it in items} | {b["id"] for b in list_bundles()}
    hit = None
    if overwrite_id:
        hit = next((it for it in items if it["id"] == overwrite_id), None)
        if not hit:
            return None, ["要覆盖的主题不存在"]
        iid = overwrite_id
        kept_origin = hit["origin"]
    else:
        iid = _unique_id(clean["id"], taken)
        if not iid:
            return None, ["主题 id 无法分配（重名过多）"]
        kept_origin = origin

    clean["id"] = iid
    item = {
        "id": iid,
        "name": clean["name"],
        "origin": kept_origin,
        "saved_at": _now(),
        "bundle": clean,
    }
    if _bytes(item) > MAX_ITEM_BYTES:
        return None, ["单套主题超出 %d KB 上限" % (MAX_ITEM_BYTES // 1024)]
    rest = [it for it in items if it["id"] != iid]
    if not hit and len(rest) >= MAX_ITEMS:
        return None, ["主题库已满（最多 %d 套），请先删除一套" % MAX_ITEMS]
    total = sum(_bytes(it) for it in rest) + _bytes(item)
    if total > MAX_TOTAL_BYTES:
        return None, ["主题库总体积超出 %d KB 上限" % (MAX_TOTAL_BYTES // 1024)]

    _write_kv(LIBRARY_KEY, json.dumps({"schema": 1, "items": rest + [item]},
                                     ensure_ascii=False))
    db.session.commit()
    return item, []


def import_item(raw):
    """导入第三方主题包（**严格模式**）：校验后剥掉 CSS、标注来源、防撞改名。"""
    clean, errors = validate_bundle(raw)
    if errors:
        return None, errors
    # 第三方包里唯一「像代码」的字段。颜色/字体/布局都是可被穷举的数据，
    # 不需要为它们牺牲功能；CSS 则直接禁用，并在来源里写清楚，避免日后误判。
    clean["css"] = ""
    note = "由主题市场导入；第三方自定义 CSS 已按安全策略禁用"
    src = clean.get("source") or ""
    clean["source"] = ((src + " ｜ ") if src else "") + note
    clean["id"] = "imp-" + _slug(clean["id"])
    return save_item(clean, origin="imported")


def delete_item(item_id):
    """删除库内条目；内置只读包不可删（它们根本不在库里）。"""
    data = library_data()
    kept = [it for it in data["items"] if it["id"] != item_id]
    if len(kept) == len(data["items"]):
        return False, ["主题不存在"]
    # 正在使用的自建主题不允许删：删掉后 active_bundle() 会解析失败，
    # 前台静默回落经典布局，属于「改了没生效」那类难查问题。
    active = (_read_kv(ACTIVE_KEY) or "").strip()
    if active == "lib:" + item_id:
        return False, ["该主题正在使用中，请先切换到别的主题"]
    _write_kv(LIBRARY_KEY, json.dumps({"schema": 1, "items": kept}, ensure_ascii=False))
    db.session.commit()
    return True, []


def item_summary(it):
    b = it["bundle"]
    return {
        "id": it["id"], "name": it["name"], "origin": it["origin"],
        "saved_at": it["saved_at"], "desc": b["desc"], "tags": b["tags"],
        "layout": b["layout"]["mode"], "card": b["layout"]["card"],
        "accent": b["tokens"]["light"]["accent"],
        "swatch": b["palette"].get("ink", b["tokens"]["light"]["accent"]),
        "css_disabled": not b["css"],
        "source": b["source"],
    }


# ---------------------------------------------------------------------------
# 外观快照 / 回滚
# ---------------------------------------------------------------------------

def capture_look():
    """拍下当前五个 Setting 的原值。**必须在任何写操作之前调用**。"""
    return {k: _read_kv(k) for k in LOOK_KEYS}


def _label_of(look):
    pack = (look.get("theme_pack") or "").strip()
    if pack.startswith("bundle:lib:"):
        it = get_item(pack[len("bundle:lib:"):])
        return it["name"] if it else "自建主题"
    if pack.startswith("bundle:"):
        b = get_bundle(pack[len("bundle:"):])
        return b["name"] if b else pack
    if pack == "custom":
        return "自定义主题"
    p = PRESET_MAP.get(pack)
    return p["name"] if p else (pack or "默认主题")


def set_prev(old_look, label=None):
    """把「切换前」的外观记为可回滚目标（与本次变更一起提交）。"""
    payload = {
        "look": {k: old_look.get(k, "") for k in LOOK_KEYS},
        "label": label or _label_of(old_look),
        "at": _now(),
    }
    _write_kv(PREV_KEY, json.dumps(payload, ensure_ascii=False))


def prev_summary():
    d = _read_json(PREV_KEY, {})
    if not isinstance(d, dict) or not isinstance(d.get("look"), dict):
        return None
    return {"label": str(d.get("label") or "上一套外观")[:80],
            "at": str(d.get("at") or "")[:40]}


def rollback():
    """恢复上一套外观，并把「当前」存成新的回滚目标（支持反悔）。返回标签或 None。"""
    d = _read_json(PREV_KEY, {})
    if not isinstance(d, dict) or not isinstance(d.get("look"), dict):
        return None
    prev_look = {k: d["look"].get(k, "") for k in LOOK_KEYS}
    cur = capture_look()
    for k in LOOK_KEYS:
        _write_kv(k, prev_look[k] if prev_look[k] is not None else "")
    _write_kv(PREV_KEY, json.dumps({
        "look": cur, "label": _label_of(cur), "at": _now(),
    }, ensure_ascii=False))
    db.session.commit()
    return str(d.get("label") or "上一套外观")[:80]
