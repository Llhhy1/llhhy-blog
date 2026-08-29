"""Redis 业务缓存层（v3.10.7）。

复用项目既有的 Redis 接入方式（config REDIS_URL + 懒加载客户端 + 失败静默降级），
与 rate_limit 共用同一 REDIS_URL，但使用独立前缀 ``blog:cache:``，便于运维按前缀清缓存。

设计原则（与 bot_guard.rate_limit 一致）：
- 未配置 REDIS_URL → 全部操作静默降级为「无缓存」（passthrough），不影响主流程；
- Redis 连接/读写异常 → 捕获后降级为无缓存，绝不把异常抛到业务层；
- 统一 key 前缀 ``blog:cache:``，支持 ``cache_clear_prefix()`` 批量失效（后台清缓存用）；
- 模块自包含，不反向依赖业务模块，避免循环导入。
"""
import json
import threading

_CACHE_PREFIX = "blog:cache:"
# 每线程复用同一客户端对象（避免每次调用都 from_url 新建连接池）。
_local = threading.local()


def _client():
    """返回共享 Redis 客户端；未配置或异常时返回 None（触发降级）。"""
    try:
        c = getattr(_local, "redis", None)
        if c is not None:
            return c
        from flask import current_app
        import redis as _redis_mod
        url = current_app.config.get("REDIS_URL", "")
        if not url:
            return None
        c = _redis_mod.from_url(
            url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        _local.redis = c
        return c
    except Exception:
        return None


def cache_get(key):
    """返回 (value, hit)。hit=False 表示未命中或降级（调用方自行计算）。"""
    r = _client()
    if r is None:
        return None, False
    try:
        raw = r.get(_CACHE_PREFIX + key)
        if raw is None:
            return None, False
        return json.loads(raw), True
    except Exception:
        return None, False


def cache_set(key, value, ttl=300):
    """写入缓存；失败静默返回 False（降级为无缓存）。value 必须 JSON 可序列化。"""
    r = _client()
    if r is None:
        return False
    try:
        r.set(_CACHE_PREFIX + key, json.dumps(value, ensure_ascii=False), ex=ttl)
        return True
    except Exception:
        return False


def cache_delete(key):
    """删除单个 key；失败静默返回 False。"""
    r = _client()
    if r is None:
        return False
    try:
        r.delete(_CACHE_PREFIX + key)
        return True
    except Exception:
        return False


def cache_clear_prefix(prefix=""):
    """按前缀批量失效（运维清缓存用）。prefix 为空则清空全部 blog:cache:*。

    返回实际删除的 key 数量；未配置 Redis 时返回 0。
    """
    r = _client()
    if r is None:
        return 0
    try:
        pattern = _CACHE_PREFIX + prefix + "*"
        count = 0
        for k in r.scan_iter(match=pattern):
            r.delete(k)
            count += 1
        return count
    except Exception:
        return 0


def cached(ttl=300, keyfn=None):
    """装饰器：缓存函数返回值。

    用法::

        @cached(ttl=120, keyfn=lambda slug: "post:" + slug)
        def get_post_view(slug):
            ...

    降级：client 不可用时直接调用原函数，不缓存。keyfn 缺省用 ``模块.函数名``。
    """
    def deco(fn):
        def wrapper(*args, **kwargs):
            key = keyfn(*args, **kwargs) if keyfn else (fn.__module__ + "." + fn.__name__)
            val, hit = cache_get(key)
            if hit:
                return val
            val = fn(*args, **kwargs)
            cache_set(key, val, ttl)
            return val
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return deco
