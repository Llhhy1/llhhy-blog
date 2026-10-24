"""v4.9.0 推送指数退避重试（ROADMAP §3.1「推送编排」）。

改之前：渠道失败**完全静默** —— 只记一条 warning，运营侧没人知道新文章
根本没推到群里。改之后：失败按 1s / 2s / 4s 退避重试 3 次，全失败才记日志。

测试要点：

1. **成功路径不重试**：一次就成，不该多打一次对方接口（少一次无效外发）。
2. **中间失败能自愈**：前 2 次失败、第 3 次成功 → 返回成功且只调了 3 次。
3. **全失败要出声**：返回 False 且**确实写了 warning 日志**（含「已重试 3 次」）。
   只验返回值不算数 —— 日志才是运营侧唯一能看见的信号。
4. **退避间隔用非默认值验证**：`base_delay=0.5, retries=4` → 期望
   `[0.5, 1.0, 2.0]`。若把公式写死成 1/2/4，这条会红（判据可证伪）。

安全：`_tg_send` / `_wecom_send` 一律 monkeypatch 掉，**绝不真发外网**；
`sleep` 也换成探针，否则一个单测要干等 7 秒。
"""

import logging

import notify as notify_mod


class _Flaky:
    """前 fail_times 次调用抛错，之后成功；记录调用次数与每次 sleep 时长。"""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0
        self.sleeps = []

    def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("boom #%d" % self.calls)
        return "sent"

    def sleep(self, sec):
        self.sleeps.append(sec)


def test_首次成功则不重试():
    f = _Flaky(0)
    assert notify_mod._send_with_retry(f, "测试", sleep=f.sleep) is True
    assert f.calls == 1, "一次就成功不该再打第二次"
    assert f.sleeps == []


def test_前两次失败第三次成功():
    f = _Flaky(2)
    assert notify_mod._send_with_retry(f, "测试", sleep=f.sleep) is True
    assert f.calls == 3
    assert f.sleeps == [1.0, 2.0], "默认退避应为 1s / 2s"


def test_全失败返回False且确实记日志(caplog):
    f = _Flaky(99)
    with caplog.at_level(logging.WARNING):
        ok = notify_mod._send_with_retry(f, "测试", sleep=f.sleep)
    assert ok is False
    assert f.calls == notify_mod.RETRY_TIMES
    assert "已重试 3 次" in caplog.text, "全失败必须留痕，否则运营侧无感知"


def test_退避间隔按公式递增_非默认值():
    """用 base_delay=0.5 / retries=4 验证公式，避免「恰好等于默认值」的假绿。"""
    f = _Flaky(99)
    notify_mod._send_with_retry(f, "测试", retries=4, base_delay=0.5, sleep=f.sleep)
    assert f.calls == 4
    assert f.sleeps == [0.5, 1.0, 2.0], f.sleeps


def test_deliver_渠道失败会走重试(monkeypatch):
    """deliver 层面：Telegram 前 2 次失败第 3 次成功 → 计入 ok 而非 failed。"""
    calls = {"n": 0}

    def fake_tg(token, chat, text):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("网络抖动")

    monkeypatch.setattr(notify_mod, "_tg_send", fake_tg)
    monkeypatch.setattr(notify_mod.time, "sleep", lambda s: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)

    ok, failed = notify_mod.deliver({"title": "标题", "summary": "摘要", "link": "/post/x"})
    assert (ok, failed) == (1, 0), "重试后成功应计为成功"
    assert calls["n"] == 3


def test_deliver_未配置渠道不发也不计失败(monkeypatch):
    """未配 env 时两个渠道都跳过：既不外发，也不该计进 failed。"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)

    def boom(*a, **k):
        raise AssertionError("未配置却发起了外发")

    monkeypatch.setattr(notify_mod, "_tg_send", boom)
    monkeypatch.setattr(notify_mod, "_wecom_send", boom)
    assert notify_mod.deliver({"title": "t", "summary": "s", "link": "/l"}) == (0, 0)
