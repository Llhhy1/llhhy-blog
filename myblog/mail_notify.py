"""邮件群发：新文章发布时给所有 active 订阅者发通知邮件。
使用标准库 smtplib，无需新依赖。环境变量驱动（SMTP_HOST 等），未配置自动跳过，异常静默处理。
每封邮件密送（收件人互不可见），并带退订链接（凭 email + unsub_token）。
"""
import threading


def _send_smtp(to_addrs, subject, html_body, plain_body=""):
    """同步发送一封邮件（密送所有收件人）。返回 True/False。"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from flask import current_app

    host = current_app.config.get("SMTP_HOST", "")
    if not host:
        return False
    port = int(current_app.config.get("SMTP_PORT", 465))
    user = current_app.config.get("SMTP_USERNAME", "")
    pwd = current_app.config.get("SMTP_PASSWORD", "")
    sender = current_app.config.get("SMTP_FROM", "") or user
    use_ssl = current_app.config.get("SMTP_USE_SSL", True)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = sender  # To 设为发件人，真实收件人放 Bcc（密送），保护隐私
    msg["Bcc"] = ", ".join(to_addrs)
    if plain_body:
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                s.login(user, pwd)
                s.sendmail(sender, to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls()
                s.login(user, pwd)
                s.sendmail(sender, to_addrs, msg.as_string())
        return True
    except Exception:
        return False


def _build_mail(post, site_url):
    """构造新文章通知邮件的 HTML/纯文本正文。"""
    from utils import clean_html, render_markdown
    title = post.title
    link = f"{site_url.rstrip('/')}/post/{post.slug}"
    summary = post.summary or (post.content or "")[:120]
    body_html = f"""\
<div style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;max-width:560px;margin:0 auto;padding:24px;">
  <h2 style="color:#1a73e8;margin:0 0 12px;">{title}</h2>
  <p style="color:#555;line-height:1.7;">{summary}</p>
  <p style="margin:18px 0;">
    <a href="{link}" style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:10px 22px;border-radius:6px;">阅读全文 →</a>
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="font-size:12px;color:#999;">你收到这封邮件是因为订阅了本站的新文章通知。</p>
  <p style="font-size:12px;color:#999;">不想再收到？<a href="{site_url.rstrip('/')}/unsubscribe?email=__EMAIL__&token=__TOKEN__">点此退订</a>。</p>
</div>"""
    plain = f"{title}\n\n{summary}\n\n阅读全文：{link}\n\n不想再收到？访问：{site_url.rstrip('/')}/unsubscribe?email=__EMAIL__&token=__TOKEN__"
    return body_html, plain


def notify_subscribers_async(post):
    """后台线程异步群发新文章通知给所有 active 订阅者。
    在新文章发布时调用（不阻塞发布主流程）。所有异常静默处理。
    """
    def _worker():
        try:
            from models import Subscriber
            from flask import current_app
            app = current_app._get_current_object()
            site_url = app.config.get("MAIL_SITE_URL") or app.config.get("SITE_URL", "")
            if not app.config.get("SMTP_HOST"):
                return  # 未配置 SMTP，跳过
            subs = Subscriber.query.filter_by(active=True).all()
            if not subs:
                return
            body_html, plain = _build_mail(post, site_url)
            # 逐个填充退订链接后批量密送（分批每 50 个，避免单封过大）
            batch = []
            for sub in subs:
                bh = body_html.replace("__EMAIL__", sub.email).replace("__TOKEN__", sub.unsub_token or "")
                bp = plain.replace("__EMAIL__", sub.email).replace("__TOKEN__", sub.unsub_token or "")
                batch.append((sub.email, bh, bp))
            # 为简化，每封单独发送（保证各自退订链接正确）；量大时可分批密送相同正文
            for email, bh, bp in batch:
                _send_smtp([email], f"【新文章】{post.title}", bh, bp)
        except Exception:
            pass  # 群发失败不影响发文章

    try:
        from flask import current_app
        app = current_app._get_current_object()
        t = threading.Thread(target=_worker, daemon=True)
        # 需要在 app context 内执行 worker，用 make_app_context 包一层
        def _runner():
            with app.app_context():
                _worker()
        t2 = threading.Thread(target=_runner, daemon=True)
        t2.start()
    except Exception:
        pass
