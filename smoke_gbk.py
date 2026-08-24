# -*- coding: utf-8 -*-
"""v3.4.9 GBK 乱码修复验证（隔离验证，不碰真实库）。

验证点：
1. _http_get_json 对 GBK 编码 JSON 正确解码（此前 utf-8 ignore 吞字成乱码）
2. UTF-8 中文/纯 ASCII 不回归
3. 双编码都解不了（伪随机字节）→ 抛错（不缓存乱码）
4. _looks_corrupted 启发式：乱码脏值判定 / 干净中文不误判
5. 缓存乱码自愈：缓存里有脏值 → _ensure_region 重查覆盖
6. _lookup_pconline 全链路：GBK mock → 干净中文「广东广州」
"""
import json
import os
import sys
import types

# 让 import 能命中 myblog/ 下的 stats / models
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "myblog"))

# ── 用桩模型模块替换真实 models（避免依赖 Flask-SQLAlchemy 实例） ──
class _FakeDB:
    class session:
        @staticmethod
        def add(obj):
            pass

        @staticmethod
        def commit():
            pass

        @staticmethod
        def rollback():
            pass

stub = types.ModuleType("models")
stub.db = _FakeDB
stub.Post = object
stub.VisitLog = object
stub.ReadLog = object
stub.SearchLog = object
stub.Comment = object


class _IpQuery:
    def __init__(self, cls):
        self._cls = cls

    def filter_by(self, **kw):
        self._kw = kw
        return self

    def first(self):
        ip = self._kw.get("ip")
        region = self._cls._rows.get(ip)
        if region is None:
            return None
        return self._cls(ip=ip, region=region)


class _IpRegion:
    _rows = {}

    def __init__(self, ip=None, region=None):
        self.ip = ip
        self.region = region


# Flask-SQLAlchemy 的 Model.query 是类属性（可直接链式），模拟之
_IpRegion.query = _IpQuery(_IpRegion)


def _seed(ip, region):
    _IpRegion._rows[ip] = region


stub.IpRegion = _IpRegion
sys.modules["models"] = stub

# ── 打桩 urllib.request.urlopen：按 url 返回预设字节 ──
class _FakeResp:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_RESP_BY_URL = {}


class _FakeURLRequest:
    def __init__(self, url, *a, **k):
        self.full_url = url


class _FakeURLopener:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def open(self, req, timeout=4):
        url = req if isinstance(req, str) else req.full_url
        if url not in _RESP_BY_URL:
            raise OSError("mock 未定义该 URL: " + url)
        return _FakeResp(_RESP_BY_URL[url])


def _install_url_stub():
    urllib = sys.modules.get("urllib")
    # 直接 monkey-patch 模块内引用的名字
    import stats
    stats.urllib.request.urlopen = _FakeURLopener().open
    stats.urllib.request.Request = _FakeURLRequest


import stats  # noqa: E402  确保打桩后导入

_install_url_stub()

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  ✓", name)
    else:
        FAIL.append(name)
        print("  ✗", name, "|", detail)


def resp_gbk(payload):
    return payload.encode("gbk")


def resp_utf8(payload):
    return payload.encode("utf-8")


# ── 1. GBK 编码 JSON 正确解码 ──
_RESP_BY_URL["https://gbk.test/1"] = resp_gbk('{"pro":"广东省","city":"广州市"}')
try:
    d = stats._http_get_json("https://gbk.test/1")
    check("GBK 解码成功且内容正确", d == {"pro": "广东省", "city": "广州市"}, repr(d))
except Exception as e:
    check("GBK 解码成功且内容正确", False, repr(e))

# ── 2. UTF-8 / ASCII 不回归 ──
_RESP_BY_URL["https://utf8.test/1"] = resp_utf8('{"pro":"浙江省","city":"杭州市"}')
try:
    d = stats._http_get_json("https://utf8.test/1")
    check("UTF-8 中文正常解码", d == {"pro": "浙江省", "city": "杭州市"}, repr(d))
except Exception as e:
    check("UTF-8 中文正常解码", False, repr(e))

_RESP_BY_URL["https://ascii.test/1"] = b'{"ok":true,"city":"Beijing"}'
try:
    d = stats._http_get_json("https://ascii.test/1")
    check("ASCII/纯英文 JSON 正常", d == {"ok": True, "city": "Beijing"}, repr(d))
except Exception as e:
    check("ASCII/纯英文 JSON 正常", False, repr(e))

# ── 3. 双编码都解不了 → 抛错（走调用方兜底，不缓存乱码） ──
_RESP_BY_URL["https://garbage.test/1"] = bytes(range(1, 20))  # 无效 UTF-8 也无效 GBK 的字节
try:
    stats._http_get_json("https://garbage.test/1")
    check("乱码字节 → 抛错不返回垃圾", False, "未抛错")
except Exception as e:
    # 低字节对两种编码都可解码但 JSON 非法 → 抛 JSONDecodeError 或 UnicodeDecodeError 均可
    check("乱码字节 → 抛错不返回垃圾",
          isinstance(e, (UnicodeDecodeError, json.JSONDecodeError)), repr(e))

# ── 4. _looks_corrupted ──
check("脏值 '㽭ʡ' 判乱码", stats._looks_corrupted("㽭ʡ") is True)
check("脏值 '广东广州' 不判乱码", stats._looks_corrupted("广东广州") is False)
check("脏值 '美国加利福尼亚' 不判乱码", stats._looks_corrupted("美国加利福尼亚") is False)
check("脏值 '中国台湾' 不判乱码", stats._looks_corrupted("中国台湾") is False)
check("脏值 '北京·朝阳' 不判乱码", stats._looks_corrupted("北京·朝阳") is False)
check("空值不判乱码", stats._looks_corrupted("") is False)

# ── 5. _lookup_pconline 全链路（GBK mock → 干净中文） ──
_RESP_BY_URL["https://whois.pconline.com.cn/ipJson.jsp?ip=1.2.3.4&json=true"] = \
    resp_gbk('{"pro":"广东省","city":"广州市"}')
r = stats._lookup_pconline("1.2.3.4")
check("pconline GBK 全链路 → 广东广州", r == "广东广州", repr(r))

_RESP_BY_URL["https://whois.pconline.com.cn/ipJson.jsp?ip=5.6.7.8&json=true"] = \
    resp_gbk('{"pro":"浙江省","city":"杭州市"}')
r = stats._lookup_pconline("5.6.7.8")
check("pconline GBK 全链路 → 浙江杭州", r == "浙江杭州", repr(r))

# ── 6. _ensure_region 缓存乱码自愈 ──
_seed("9.9.9.9", "㽭ʡ")  # 历史脏缓存=乱码
_RESP_BY_URL["https://whois.pconline.com.cn/ipJson.jsp?ip=9.9.9.9&json=true"] = \
    resp_gbk('{"pro":"四川省","city":"成都市"}')
# 直接测 _ensure_region：脏缓存应被忽略、在线重查、覆盖
try:
    region = stats._ensure_region("9.9.9.9")
    check("脏缓存被重查为干净中文", region == "四川成都", repr(region))
except Exception as e:
    check("脏缓存被重查为干净中文", False, repr(e))

# ── 7. cached_region 对脏缓存不直接信任（异步重查） ──
# 打桩 threading.Thread.start 为同步执行，验证 cached_region 也会触发重查
_calls = []
_orig_thread = stats.threading.Thread


class _SyncThread:
    def __init__(self, target, daemon=True):
        self._target = target

    def start(self):
        _calls.append("thread_started")
        self._target()


stats.threading.Thread = _SyncThread
_seed("8.8.8.9", "㽭ʡ")
res = stats.cached_region("8.8.8.9")
check("cached_region 脏缓存不直接返回", res == "", repr(res))
check("cached_region 触发异步重查线程", len(_calls) == 1, str(_calls))
stats.threading.Thread = _orig_thread

print()
print("=" * 40)
print("PASS: %d / FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    sys.exit(1)
print("ALL GREEN")