# -*- coding: utf-8 -*-
"""时间与北京时间转换。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
from datetime import timezone as _TZ, timedelta as _TD

# 北京时间（UTC+8）固定偏移：数据库里所有时间按 UTC（naive）存储，
# 展示 / 导出 / RSS / JSON-LD 一律转北京时间，不依赖服务器 OS 时区
# （部署在 UTC 或任意 OS 时区都一致，避免 UI 内部时区错位）。
BEIJING_TZ = _TZ(_TD(hours=8))


def to_beijing(dt):
    """把库里存的 naive UTC 时间解释为 UTC，转换为北京时间（带时区）。

    - None → None
    - 已是 aware 的按原时区换算到北京
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ.utc)
    return dt.astimezone(BEIJING_TZ)


def fmt_bj(dt, fmt="%Y-%m-%d %H:%M:%S"):
    """把 UTC 时间按北京时间格式化（用于显示 / 导出 / RSS / JSON-LD）。

    None 或非法值返回空串，避免模板里 `x.created_at.strftime(...)` 在空值时报错。
    """
    bj = to_beijing(dt)
    return bj.strftime(fmt) if bj else ""
