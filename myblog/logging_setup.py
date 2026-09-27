# -*- coding: utf-8 -*-
"""结构化日志基建（v3.23.0）。

为什么要有它：全仓 85 处 `print(` 直接打 stdout——没有级别、没有模块名，
**更没法按请求串联**。线上排查「这次 502 是哪条请求引起的」只能靠时间戳猜。
本模块先把「带 request_id 的日志管道」建起来，print 再分批改到 logger 上。

提供两件事：

1. `init_request_id(app)`：每个请求生成/沿用 `X-Request-ID`，放进 `g`，并回写响应头。
2. `setup_logging(app)`：让日志格式带上 `rid=<request_id>`。

设计取舍（都写下来，避免后人改回去）：

- **不劫持 root logger 的 handler**：gunicorn 自己配了 handler，硬改 root 会造成
  双重输出。这里只给**已有** handler 挂 filter（让 `%(request_id)s` 可用），
  仅当 root **完全没有** handler 时（本地开发 / pytest）才补一个 StreamHandler。
- **`request_id` 取不到时写 `-`**：后台线程、定时任务、启动阶段没有请求上下文，
  不能因为拿不到就抛异常，否则「加个日志把启动搞崩」。
- **沿用上游 `X-Request-ID` 但校验形态**：只接受 ≤64 字符的字母数字/`-`/`_`，
  防止上游塞进超长串或换行符污染日志（日志注入）。
- print → logger **分批**替换：85 处一次改完无法评审，本模块先立基建。
"""
import logging
import uuid

from flask import g, has_request_context, request

DEFAULT_LEVEL = "INFO"
_G_KEY = "request_id"
_MAX_INCOMING = 64


def _safe_id(value):
    """上游传来的 X-Request-ID 是否是可信形态（防日志注入）。"""
    if not value or len(value) > _MAX_INCOMING:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in value)


def current_request_id():
    """当前请求 ID；无请求上下文时返回 '-'。"""
    if has_request_context():
        return getattr(g, _G_KEY, None) or "-"
    return "-"


class RequestIdFilter(logging.Filter):
    """把当前 request_id 塞进每条 LogRecord（供 `%(request_id)s` 使用）。"""

    def filter(self, record):
        if not getattr(record, "request_id", None):
            record.request_id = current_request_id()
        return True


def init_request_id(app):
    """注册 request_id 中间件。"""

    @app.before_request
    def _assign_request_id():
        incoming = request.headers.get("X-Request-ID", "").strip()
        g.__setattr__(_G_KEY, incoming if _safe_id(incoming) else uuid.uuid4().hex[:16])

    @app.after_request
    def _echo_request_id(resp):
        rid = getattr(g, _G_KEY, None)
        if rid:
            resp.headers["X-Request-ID"] = rid
        return resp


def setup_logging(app, level=None):
    """配置日志：级别 + request_id 过滤器。生产沿用 gunicorn 的 handler。"""
    level_name = str(level or app.config.get("LOG_LEVEL") or DEFAULT_LEVEL).upper()
    level_value = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] [rid=%(request_id)s] %(message)s")
    req_filter = RequestIdFilter()

    root = logging.getLogger()
    # 已有 handler（gunicorn 的）：只挂 filter，**不改它的格式**，避免动生产日志样式。
    for handler in root.handlers:
        if req_filter not in handler.filters:
            handler.addFilter(req_filter)

    # 完全没有 handler（本地开发 / pytest）：补一个带 rid 的 StreamHandler。
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(req_filter)
        root.addHandler(handler)

    root.setLevel(level_value)
    app.logger.setLevel(level_value)
    # werkzeug 的每请求 INFO 与 gunicorn access log 重复，降到 WARNING。
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return app.logger
