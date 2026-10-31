# -*- coding: utf-8 -*-
"""分类 / 标签 / 系列的「旧 slug」解析（v5.4.0 slug 可读化配套）。

历史包袱：`make_slug()` **保留汉字**，所以 2026-11 之前建的分类/标签/系列
slug 都是中文（如 `智能体安全`），浏览器请求时被百分号编码成
`%e6%99%ba%e8%83%bd%e4%bd%93%e5%ae%89%e5%85%a8` —— 分享链接和访问日志都难读。

v5.4.0 起新数据一律转纯 ASCII（汉字走 pypinyin），旧数据由一次性迁移改掉；
本模块负责**让旧地址仍然能打开**，三条兼容路径依次尝试，命中即视为 legacy。
"""
from .slug import ascii_slug


def resolve_taxonomy(model, slug):
    """按 slug 找行 → `(obj|None, is_legacy)`。

    兼容顺序（也是优先级）：
    1. 精确命中 —— 正常情况，非 legacy；
    2. 忽略大小写命中 —— 旧 ASCII slug 的大小写写法（`AI-Agent` / `DeepSeek`）；
    3. `name == slug` —— 历史上 slug 与中文名同值（56 个标签里 54 个如此）；
    4. `ascii_slug(name) == slug` —— 曾被自动转成拼音、之后又手改成英文的旧地址。

    只读，不改任何行；调用方决定是「带 moved 标记返回」还是「301 跳转」。
    """
    raw = (slug or "").strip()
    if not raw:
        return None, False

    obj = model.query.filter_by(slug=raw).first()
    if obj is not None:
        return obj, False

    from models import db  # 延迟导入：utils 顶层不反向依赖 models，避免循环

    obj = model.query.filter(db.func.lower(model.slug) == raw.lower()).first()
    if obj is not None:
        return obj, True

    obj = model.query.filter_by(name=raw).first()
    if obj is not None:
        return obj, True

    low = raw.lower()
    for cand in model.query.all():   # 表很小（标签几十行），逐行比拼音可接受
        if ascii_slug(cand.name, max_len=200) == low:
            return cand, True
    return None, False
