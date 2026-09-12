"""时区安全的 UTC 当前时间（消除 datetime.utcnow() 弃用告警，语义保持不变：返回 naive UTC）。

旧代码广泛用 datetime.utcnow()，Python 3.12+ 产生 DeprecationWarning。
本函数集中提供等价实现：datetime.now(timezone.utc).replace(tzinfo=None) 返回 naive UTC，
与旧行为逐字节一致（数据库 DateTime 列均为 naive 存储），不含时区信息、不触发告警。
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
