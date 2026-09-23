"""新文章推送通知（D2 · 运营分发）。

配置（环境变量，不入库、不开源）：
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ：Telegram Bot 推送
- WECOM_WEBHOOK_URL                   ：企业微信 / 微信「群机器人」Webhook 推送（最简单，推荐）

未配置对应变量时对应渠道自动跳过（默认不打扰）。所有异常**记日志但不抛出** ——
绝不影响发文章的主流程。

## v3.20.0 改动一：同步外网调用 → 后台线程

原实现是**同步**的：`_post_json` 每渠道 `timeout=6`，两个渠道都配齐即**最坏阻塞 12s**。
而调用点全在请求路径上（`admin/post_editor.py`、`admin/post_manage.py`、
`admin/_helpers.py`、`api/posts.py`、`app.py` 共 5 处）—— 保存 / 发布文章会干等。

⚠️ 这个缺陷此前一直是「**睡着的**」：线上环境变量只配了
`SECRET_KEY / ADMIN_PASSWORD / SITE_URL / MCP_AUTH_TOKEN / MCP_WRITE_TOKEN`，
`TELEGRAM_*` 与 `WECOM_WEBHOOK_URL` **都没配** → 两个渠道分支全部跳过 → 零成本。
但一旦哪天配上推送，保存文章立刻慢 6~12s。所以趁没配先拆掉。
（异步范式照抄 `mail_notify.notify_subscribers_async()`：
Thread + app context + 全异常兜底。）

## v3.20.0 改动二：为什么在请求线程里先取快照

**先澄清一个我原本以为、但实测证伪的说法**（记在这里免得后人再想当然）：

我最初以为「把 ORM 对象传进后台线程会炸」是因为 `db.session.commit()` 会让属性过期
（`expire_on_commit` 默认 `True`），而后台线程用的是新 session，访问属性会
`DetachedInstanceError`。**实测并非如此**（Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.52）：

| detached 之后访问 | 实测结果 |
| --- | --- |
| 标量 `post.title` / `post.summary` | **成功** —— 属性值仍在实例 `__dict__` 里，没有被过期 |
| 关系 `post.tags`（session 内已碰过） | 成功 |
| **关系 `post.author`（从未加载）** | **抛 `DetachedInstanceError`** |

也就是说：**只读标量的旧写法本来就能跑**，不存在「通知静默不发」的历史缺陷
（`mail_notify.notify_subscribers_async()` 当年那样传对象，对它的用法而言是能工作的）。

**但风险边界确实存在**，而且很窄、很容易被后来人踩到：
后台线程里一旦访问**未加载的懒加载关系**（或任何需要回库的属性），就会抛
`DetachedInstanceError`，再被 `except Exception` 吞掉 → 表现为「通知静默不发」，
且**只有配了推送渠道的环境才会遇到**。所以本模块选择**主动划一条安全边界**：
在调用线程里把需要的内容读成纯数据，线程内只碰字符串。

**这个改动是「纵深防御」，不是「修 bug」** —— 区别很重要：
前者我会照做，后者才需要急着上线。判断依据就是上面那张实测表。
"""
import json
import logging
import os
import threading
import urllib.request

logger = logging.getLogger(__name__)


def _post_json(url, payload, timeout=6):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _tg_send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_json(url, {"chat_id": chat_id, "text": text,
                     "parse_mode": "HTML", "disable_web_page_preview": False})


def _wecom_send(webhook, text):
    # 企业微信群机器人：content 为纯文本（支持 \n）
    _post_json(webhook, {"msgtype": "text", "text": {"content": text}})


def _snapshot(post, site_url=""):
    """把文章读成**纯数据**（必须在 session 尚可用的线程里调用）。

    这一步是安全边界：跨过它之后就不再持有任何 ORM 对象，
    后台线程也就不可能踩到 detached / expired 实例。
    """
    title = getattr(post, "title", None) or "新文章"
    slug = getattr(post, "slug", None) or ""
    summary = (getattr(post, "summary", None)
               or (getattr(post, "content", None) or "")[:120]).strip()
    link = (f"{site_url.rstrip('/')}/post/{slug}" if site_url
            else f"/post/{slug}")
    return {"title": title, "summary": summary, "link": link}


def _build_text(snap):
    return "📝 新文章：%s\n%s\n%s" % (snap["title"], snap["summary"], snap["link"])


def deliver(payload):
    """真正执行外发（纯数据入参，可安全地在任意线程调用）。返回 (ok, failed) 计数。"""
    text = _build_text(payload)
    ok = failed = 0

    # Telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            _tg_send(token, chat, text)
            ok += 1
        except Exception:
            failed += 1
            # 不再用 print：升级为结构化日志（含堆栈），便于排障
            logger.warning("Telegram 新文章推送失败", exc_info=True)

    # 企业微信 / 微信「群机器人」
    wecom = os.environ.get("WECOM_WEBHOOK_URL")
    if wecom:
        try:
            _wecom_send(wecom, text)
            ok += 1
        except Exception:
            failed += 1
            logger.warning("企业微信新文章推送失败", exc_info=True)

    return ok, failed


def notify_new_post(post, site_url=""):
    """新文章发布后调用。**立即返回**，真正的外发在后台线程。

    调用方无需改动（签名不变）；但语义已从「同步发完才返回」变为「入队即返回」
    —— 这是 v3.20.0 刻意的行为变更，目的是把 6~12s 的外网等待移出请求路径。

    无应用上下文时（例如在脚本里直接调用）自动退化为**同步**执行，
    保持原来的「调完就已经发过」语义，避免静默不发送。
    """
    # ⚠️ 快照必须在此刻（调用方所在线程、且 session 尚可用）完成
    payload = _snapshot(post, site_url)

    try:
        from flask import current_app
        app = current_app._get_current_object()
    except Exception:
        # 无 app → 无法在新线程里建上下文，直接同步发
        deliver(payload)
        return

    def _runner():
        with app.app_context():
            deliver(payload)

    try:
        threading.Thread(target=_runner, daemon=True).start()
    except Exception:
        logger.warning("起后台线程失败，改为同步发送新文章通知", exc_info=True)
        deliver(payload)
