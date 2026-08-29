"""v3.10.7 Redis 缓存层集成测试（零依赖：内置假 Redis）。

验证：
- get_setting / compute_summary / get_circle_feed 在配置 Redis 时真正写入 blog:cache:* 且二次命中；
- 未配置 Redis（REDIS_URL 为空）时降级为直查 DB，函数行为不受影响（不抛异常、返回正确）。

不引入 fakeredis 依赖：用一个最小内存假 Redis 模拟 cache.py 实际调用的
get / set(ex=) / delete / scan_iter 子集，避免给仓库增加测试依赖。
"""
import fnmatch

import pytest

import cache
from models import db, Setting


class _FakeRedis:
    """cache.py 用到的 Redis 方法子集的内存实现。"""

    def __init__(self):
        self._d = {}

    def get(self, k):
        return self._d.get(k)

    def set(self, k, v, ex=None):
        self._d[k] = v
        return True

    def delete(self, k):
        self._d.pop(k, None)
        return 1

    def scan_iter(self, match="*"):
        for k in list(self._d.keys()):
            if fnmatch.fnmatch(k, match):
                yield k


@pytest.fixture
def redis_app(app):
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    # 注入假 Redis，模拟「已配置 REDIS_URL」的命中路径
    cache._local.redis = _FakeRedis()
    yield app
    cache._local.redis = None
    ctx.pop()


def test_get_setting_caches(redis_app):
    from utils import get_setting
    if not Setting.query.filter_by(key="ck_test").first():
        db.session.add(Setting(key="ck_test", value="hello"))
        db.session.commit()
    assert get_setting("ck_test") == "hello"
    # 命中路径：Redis 中应有对应 key
    assert cache._local.redis.get("blog:cache:setting:ck_test") is not None
    # 二次调用仍返回正确值（命中缓存）
    assert get_setting("ck_test") == "hello"


def test_compute_summary_caches(redis_app):
    from stats import compute_summary
    s1 = compute_summary()
    assert isinstance(s1, dict) and "total_visits" in s1
    assert cache._local.redis.get("blog:cache:stats:summary") is not None
    s2 = compute_summary()
    assert s2 == s1  # 命中缓存，结果一致


def test_feed_circle_caches(redis_app):
    from feed_agg import get_circle_feed
    items = get_circle_feed()
    assert isinstance(items, list)
    assert cache._local.redis.get("blog:cache:feed:circle") is not None
    assert get_circle_feed() == items  # 命中缓存


def test_fallback_without_redis(app):
    # 默认 app fixture：REDIS_URL 通常为空 -> 缓存禁用，函数仍正常工作
    ctx = app.app_context()
    ctx.push()
    cache._local.redis = None
    from utils import get_setting
    from stats import compute_summary
    from feed_agg import get_circle_feed
    # 不抛异常、返回合理结构
    assert get_setting("site_title") is not None
    assert isinstance(compute_summary(), dict)
    assert isinstance(get_circle_feed(), list)
    ctx.pop()
