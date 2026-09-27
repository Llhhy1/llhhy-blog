"""结构化日志 / request_id 基建测试（v3.23.0）。

对着的风险：日志没法按请求串联（线上只能靠时间戳猜），以及上游可以塞任意
`X-Request-ID` 污染日志（日志注入）。所以这里钉死三件事：
1. 每个响应都带 X-Request-ID，且**沿用**上游给的合法值（才能跨服务串联）。
2. 上游给的**非法**值（超长 / 含换行或空格）一律丢弃重生成——防日志注入。
3. 无请求上下文时 `current_request_id()` 返回 '-'（后台线程/定时任务不能因此崩）。
"""
import logging

import pytest

import logging_setup
from logging_setup import RequestIdFilter, current_request_id, _safe_id


def test_every_response_carries_request_id(client):
    resp = client.get("/api/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid, "响应必须带 X-Request-ID，否则线上无法按请求串联日志"
    assert 0 < len(rid) <= 64


def test_incoming_request_id_is_echoed(client):
    """上游给了合法 ID 就必须沿用——否则跨服务链路断掉。"""
    resp = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers.get("X-Request-ID") == "abc123"


@pytest.mark.parametrize("bad", [
    "x" * 200,                 # 超长
    "has space",               # 含空格
    "semi;colon",
    "",                        # 空串（等于没给，应重新生成）
])
def test_unsafe_incoming_id_is_replaced(client, bad):
    resp = client.get("/api/health", headers={"X-Request-ID": bad})
    rid = resp.headers.get("X-Request-ID")
    assert rid and rid != bad, f"非法 X-Request-ID 必须丢弃重生成，收到 {bad!r}"
    assert _safe_id(rid), f"生成的 ID 必须是安全形态，实际 {rid!r}"


@pytest.mark.parametrize("bad", ["line\nbreak", "x" * 65, "has space", ";", ""])
def test_safe_id_rejects_injection_shapes(bad):
    """换行等注入形态直接判非法。

    注意：带换行的值 werkzeug 在 header 层就拒了（根本到不了我们代码），
    所以这条走单元测而不是 HTTP——但校验本身必须留着，挡住其他入口。
    """
    assert _safe_id(bad) is False


@pytest.mark.parametrize("good", ["abc123", "req-7f3a", "req_9", "A" * 64])
def test_safe_id_accepts_normal(good):
    assert _safe_id(good) is True


def test_current_request_id_outside_request_is_dash(app):
    with app.app_context():
        assert current_request_id() == "-"


def test_filter_injects_request_id_into_record(app):
    """LogRecord 上必须能取到 request_id，供 %(request_id)s 使用。"""
    filt = RequestIdFilter()
    rec = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
    with app.test_request_context("/", headers={"X-Request-ID": "rid-42"}):
        # before_request 才会赋值，这里手工放进 g 模拟中间件已跑过
        from flask import g
        g.request_id = "rid-42"
        assert filt.filter(rec) is True
    assert rec.request_id == "rid-42"


def test_filter_is_idempotent_when_record_already_has_id():
    """别覆盖已有值（第三方库可能自己带）。"""
    filt = RequestIdFilter()
    rec = logging.LogRecord("test", logging.INFO, __file__, 1, "x", None, None)
    rec.request_id = "preset"
    assert filt.filter(rec) is True
    assert rec.request_id == "preset"


def test_log_level_from_config(app):
    app.config["LOG_LEVEL"] = "DEBUG"
    logging_setup.setup_logging(app, level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    # 还原，避免影响同会话后续用例
    logging_setup.setup_logging(app, level="INFO")
