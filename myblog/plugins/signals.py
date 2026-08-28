"""插件事件总线（v3.9.0 · M1）。

用 blinker 提供核心事件信号，插件可在 register() 内订阅，实现「发布后推送 / 清缓存」等
解耦逻辑。订阅者抛异常不影响主流程（在 emit 处被吞掉并打印告警）。

信号列表（详见仓库 PLUGIN_SYSTEM.md M1）：
- post_published(post)      ：文章发布 / 转为已发布（立即发布、定时到点、后台一键）
- post_deleted(post)        ：文章被删除（回收站清空或硬删）
- comment_created(comment)  ：新评论写入（含待审）
- comment_approved(comment) ：评论通过审核
- plugin_loaded(slug, manifest)：插件加载完成

插件订阅示例（在 register(app, cfg) 内）：
    from plugins.signals import post_published
    def _on_published(post):
        print("新文章：", post.title)
    post_published.connect(_on_published)
"""
from blinker import Namespace

_signals = Namespace()

post_published = _signals.signal("post_published")
post_deleted = _signals.signal("post_deleted")
comment_created = _signals.signal("comment_created")
comment_approved = _signals.signal("comment_approved")
plugin_loaded = _signals.signal("plugin_loaded")


def emit_post_published(post):
    try:
        post_published.send(post)
    except Exception as e:
        print(f"[插件信号] post_published 订阅者异常（已忽略）：{e}")


def emit_post_deleted(post):
    try:
        post_deleted.send(post)
    except Exception as e:
        print(f"[插件信号] post_deleted 订阅者异常（已忽略）：{e}")


def emit_comment_created(comment):
    try:
        comment_created.send(comment)
    except Exception as e:
        print(f"[插件信号] comment_created 订阅者异常（已忽略）：{e}")


def emit_comment_approved(comment):
    try:
        comment_approved.send(comment)
    except Exception as e:
        print(f"[插件信号] comment_approved 订阅者异常（已忽略）：{e}")


def emit_plugin_loaded(slug, manifest):
    try:
        plugin_loaded.send(slug, manifest=manifest)
    except Exception as e:
        print(f"[插件信号] plugin_loaded 订阅者异常（已忽略）：{e}")
