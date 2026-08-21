"""邮件群发：新文章发布时给所有 active 订阅者发通知邮件。
使用标准库 smtplib，无需新依赖。配置来源：后台「邮件设置」（Setting 表 mail_* 键）优先，环境变量 SMTP_* 兜底；
均未配置则自动跳过，异常静默处理。
每封邮件密送（收件人互不可见），并带退订链接（凭 email + unsub_token）。
安全：标题/摘要/邮箱插入 HTML 前均转义；退订链接 email/token 均 URL 编码；主题经 Header 编码防换行注入。
"""
import threading


def load_mail_config():
    """读取邮件配置：优先 Setting 表（后台可配置），回退环境变量。
    返回 dict：{host, port, username, password, from, use_ssl, site_url}
    """
    from flask import current_app
    from utils import get_setting
    # 环境变量为兜底默认
    host = current_app.config.get("SMTP_HOST", "") or ""
    port = current_app.config.get("SMTP_PORT", 465)
    user = current_app.config.get("SMTP_USERNAME", "") or ""
    pwd = current_app.config.get("SMTP_PASSWORD", "") or ""
    sender = current_app.config.get("SMTP_FROM", "") or user
    use_ssl = current_app.config.get("SMTP_USE_SSL", True)
    site_url = current_app.config.get("MAIL_SITE_URL") or current_app.config.get("SITE_URL", "") or ""
    # Setting 表覆盖（后台配置优先）
    host = get_setting("mail_host", host) or host
    port = int(get_setting("mail_port", str(port)) or str(port))
    user = get_setting("mail_username", user) or user
    pwd = get_setting("mail_password", pwd) or pwd
    sender = get_setting("mail_from", sender) or sender or user
    use_ssl = (get_setting("mail_use_ssl", "true" if use_ssl else "false") or "true").lower() != "false"
    return {"host": host, "port": port, "username": user, "password": pwd,
            "from": sender, "use_ssl": use_ssl, "site_url": site_url}


def send_test_mail(cfg, to_addr):
    """发送测试邮件（后台「邮件设置」页验证用）。cfg 为 load_mail_config() 返回的 dict。"""
    subject = "【测试】博客邮件配置验证"
    body_html = "<p>这是一封测试邮件，说明你的博客 SMTP 邮件配置可用。✅</p>"
    return _send_smtp(cfg, [to_addr], subject, body_html, "这是一封测试邮件，说明你的博客 SMTP 邮件配置可用。")


def _send_smtp(cfg, to_addrs, subject, html_body, plain_body=""):
    """同步发送一封邮件（密送所有收件人）。返回 True/False。
    cfg 为 load_mail_config() 返回的 dict（含 host/port/username/password/from/use_ssl）。
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.header import Header

    host = cfg.get("host", "")
    port = int(cfg.get("port", 465))
    user = cfg.get("username", "")
    pwd = cfg.get("password", "")
    sender = cfg.get("from", "") or user
    use_ssl = cfg.get("use_ssl", True)
    if not host or not user:
        return False

    msg = MIMEMultipart("alternative")
    # Header() 编码主题，阻止换行注入（标题里含 \r\n 时安全处理）
    msg["Subject"] = Header(subject, "utf-8")
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
    """构造新文章通知邮件的 HTML/纯文本正文（所有用户可控内容均转义）。"""
    import html
    title = html.escape(post.title or "")
    summary = html.escape((post.summary or (post.content or ""))[:200])
    link = f"{site_url.rstrip('/')}/post/{post.slug}"
    # email / token 用于退订链接，必须 URL 编码（邮箱可能含 @、.、+ 等；token 是十六进制）
    # 注意：这里保留占位符，实际发送前按每个订阅者填充并编码
    unsub_href = f"{site_url.rstrip('/')}/unsubscribe?email=__EMAIL_ENC__&token=__TOKEN_ENC__"
    body_html = f"""\
<div style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;max-width:560px;margin:0 auto;padding:24px;">
  <h2 style="color:#1a73e8;margin:0 0 12px;">{title}</h2>
  <p style="color:#555;line-height:1.7;">{summary}</p>
  <p style="margin:18px 0;">
    <a href="{link}" style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:10px 22px;border-radius:6px;">阅读全文 →</a>
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="font-size:12px;color:#999;">你收到这封邮件是因为订阅了本站的新文章通知。</p>
  <p style="font-size:12px;color:#999;">不想再收到？<a href="{unsub_href}">点此退订</a>。</p>
</div>"""
    plain = f"{post.title}\n\n{(post.summary or (post.content or ''))[:200]}\n\n阅读全文：{link}\n\n不想再收到？访问：{site_url.rstrip('/')}/unsubscribe?email=__EMAIL_ENC__&token=__TOKEN_ENC__"
    return body_html, plain


def _fill_unsub(body, email, token):
    """按订阅者填充退订链接（email/token URL 编码后再填入，纯文本版不编码但转义）。"""
    import urllib.parse
    enc_email = urllib.parse.quote(email, safe="")
    enc_token = urllib.parse.quote(token, safe="")
    return body.replace("__EMAIL_ENC__", enc_email).replace("__TOKEN_ENC__", enc_token)


def notify_subscribers_async(post):
    """后台线程异步群发新文章通知给所有 active 订阅者。
    在新文章发布时调用（不阻塞发布主流程）。所有异常静默处理。
    """
    def _worker():
        try:
            from models import Subscriber
            from flask import current_app
            app = current_app._get_current_object()
            cfg = load_mail_config()
            if not cfg.get("host") or not cfg.get("username"):
                return  # 未配置 SMTP，跳过
            subs = Subscriber.query.filter_by(active=True).all()
            if not subs:
                return
            body_html, plain = _build_mail(post, cfg.get("site_url", ""))
            for sub in subs:
                token = sub.unsub_token or ""
                bh = _fill_unsub(body_html, sub.email, token)
                bp = _fill_unsub(plain, sub.email, token)
                _send_smtp(cfg, [sub.email], f"【新文章】{post.title}", bh, bp)
        except Exception:
            pass  # 群发失败不影响发文章

    try:
        from flask import current_app
        app = current_app._get_current_object()
        # 需要在 app context 内执行 worker
        def _runner():
            with app.app_context():
                _worker()
        t2 = threading.Thread(target=_runner, daemon=True)
        t2.start()
    except Exception:
        pass
