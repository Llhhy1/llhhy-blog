"""新文章推送通知（D2 · 运营分发）。

配置（环境变量，不入库、不开源）：
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ：Telegram Bot 推送
- WECOM_WEBHOOK_URL                   ：企业微信 / 微信「群机器人」Webhook 推送（最简单，推荐）

未配置对应变量时对应渠道自动跳过（默认不打扰）。所有异常静默处理，
绝不影响发文章的主流程。
"""
import os
import json
import urllib.request


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


def notify_new_post(post, site_url=""):
    """新文章发布后调用。所有渠道未配置或异常都静默跳过。"""
    title = post.title or "新文章"
    link = f"{site_url.rstrip('/')}/post/{post.slug}" if site_url else f"/post/{post.slug}"
    summary = (post.summary or (post.content or "")[:120]).strip()
    text = f"📝 新文章：{title}\n{summary}\n{link}"

    # Telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            _tg_send(token, chat, text)
        except Exception as e:
            print("Telegram 推送失败:", e)

    # 企业微信 / 微信「群机器人」
    wecom = os.environ.get("WECOM_WEBHOOK_URL")
    if wecom:
        try:
            _wecom_send(wecom, text)
        except Exception as e:
            print("企业微信推送失败:", e)
