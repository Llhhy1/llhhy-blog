# -*- coding: utf-8 -*-
"""前台「自定义外部入口」的多条目存储（v4.1.0）。

为什么是「单个 Setting 存 JSON」而不是新建一张表
-----------------------------------------------
1. **这里永远不需要 SQL 查询**——入口数量天然是「几个」，既不过滤、也不分页、
   更不和其它表联合。为一个 List[Tuple] 加一张表，换来的只是「能用 SQL 查」。
2. **它需要跟着 ``config_rollback`` 快照与回滚**（误删了要能一键回去）。
   放在 Setting 表里，``snapshot_settings`` 按 key 取值就自动具备这个能力；
   新建表则要把回滚 Gui Lung 再写一遍。
3. 省掉一次 Alembic 迁移。本项目纪律是「能不改表结构就不改」。

安全边界不在这一层
------------------
本模块**只负责读写 JSON，不校验 URL 合法性**。判据统一用 ``utils.is_http_url``
一处实现，在两处生效：后台保存时拒绝、``/api/site`` 输出前再过滤一次。
两侧互不依赖 —— 任何一侧失效，危险 href 都不会流到前台。
"""

import json
import uuid

KEY = "nav_entries"

# 上限不是为了省地方：导航栏塞太多项会横向溢出（见 global.css 的 nowrap），
# 与其让页面撑破再事后收拾，不如在写入侧设一个明确的量。
MAX_ITEMS = 12

_LABEL_MAX = 20
_ICON_MAX = 8
_URL_MAX = 300


def new_id():
    """条目 id：短随机串，够用且不可枚举（后台删除/排序靠它定位）。"""
    return uuid.uuid4().hex[:8]


def load():
    """读取原始条目列表（**不做 URL 过滤** —— 过滤是出口的责任）。

    容忍任何脏数据：JSON 坏了、类型不对、缺字段，都退化成「该项跳过」而不是抛异常。
    后台一旦因为一行脏数据打不开，管理员就失去了修它的手段 —— 那才是最坏的结果。
    """
    from utils import get_setting
    raw = get_setting(KEY, "") or ""
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append({
            "id": str(item.get("id") or new_id()),
            "label": str(item.get("label") or "")[:_LABEL_MAX],
            "url": str(item.get("url") or "")[:_URL_MAX],
            "icon": str(item.get("icon") or "")[:_ICON_MAX],
            "enabled": bool(item.get("enabled", True)),
        })
    return out


def save(items):
    """整体覆写（列表小，没必要做增量 diff）。"""
    from models import Setting, db
    payload = json.dumps(items, ensure_ascii=False)
    row = Setting.query.filter_by(key=KEY).first()
    if row:
        row.value = payload
    else:
        db.session.add(Setting(key=KEY, value=payload))
    db.session.commit()


def find(item_id):
    for it in load():
        if it["id"] == item_id:
            return it
    return None


def migrate_legacy():
    """把 v4.0.0 的四件套（``entry_label/url/icon/enabled``）迁成第一条。

    **只迁一次**：``nav_entries`` 这个 key 一旦存在（哪怕是空数组）就不再动——
    否则用户在新管理页里删掉全部入口后，重启又把老配置变回来，等于删不掉。
    """
    from utils import get_setting
    if get_setting(KEY, None) is not None:
        return False
    url = (get_setting("entry_url", "") or "").strip()
    if not url:
        save([])          # 明确落成「空」，封住下一次迁移
        return False
    save([{
        "id": new_id(),
        "label": (get_setting("entry_label", "") or "百宝箱")[:_LABEL_MAX],
        "url": url,
        "icon": (get_setting("entry_icon", "") or "")[:_ICON_MAX],
        "enabled": str(get_setting("entry_enabled", "true")).strip().lower() == "true",
    }])
    return True
