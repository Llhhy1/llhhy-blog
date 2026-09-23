"""邮件群发：新文章发布时给所有 active 订阅者发通知邮件。
使用标准库 smtplib，无需新依赖。配置来源：后台「邮件设置」（Setting 表 mail_* 键）优先，环境变量 SMTP_* 兜底；
均未配置则自动跳过，异常**记日志但不抛出**。
每封邮件密送（收件人互不可见），并带退订链接（凭 email + unsub_token）。
安全：标题/摘要/邮箱插入 HTML 前均转义；退订链接 email/token 均 URL 编码；主题经 Header 编码防换行注入。
"""
import logging
import threading

logger = logging.getLogger(__name__)


def load_mail_config():
    """读取邮件配置：优先 Setting 表（后台可配置），回退环境变量。
    返回 dict：{host, port, username, password, from, use_ssl, site_url}
    """
    from flask import current_app
    from utils import get_setting, site_base
    # 环境变量为兜底默认
    host = current_app.config.get("SMTP_HOST", "") or ""
    port = current_app.config.get("SMTP_PORT", 465)
    user = current_app.config.get("SMTP_USERNAME", "") or ""
    pwd = current_app.config.get("SMTP_PASSWORD", "") or ""
    sender = current_app.config.get("SMTP_FROM", "") or user
    use_ssl = current_app.config.get("SMTP_USE_SSL", True)
    # v3.18.9：站点对外地址统一收敛到 utils.site_base()（DB site_url → env SITE_URL → 空串），
    # 不再单独读 SITE_URL，避免邮件里的链接与 sitemap/canonical 不一致。
    # MAIL_SITE_URL 保留为邮件专用的显式覆盖（例如邮件要走另一个对外域名）。
    site_url = current_app.config.get("MAIL_SITE_URL") or site_base() or ""
    # Setting 表覆盖（后台配置优先）：主机/端口/用户名/发件人/SSL 仍库值优先（便于后台调整）
    host = get_setting("mail_host", host) or host
    port = int(get_setting("mail_port", str(port)) or str(port))
    user = get_setting("mail_username", user) or user
    sender = get_setting("mail_from", sender) or sender or user
    use_ssl = (get_setting("mail_use_ssl", "true" if use_ssl else "false") or "true").lower() != "false"
    # v3.1.6 高优：SMTP 密码优先读环境变量（默认开启），避免授权码明文落库。
    #   - SMTP_PASSWORD_ENV_FIRST=true（默认）：环境变量 SMTP_PASSWORD 非空即用它，库值仅作兜底；
    #   - 设 false 则回退旧行为（库值优先，兼容已在后台填过密码的用户）。
    env_first = current_app.config.get("SMTP_PASSWORD_ENV_FIRST", True)
    db_pwd = get_setting("mail_password", "") or ""
    if env_first:
        if pwd:  # 环境变量有值，直接用（不落库、更安全）
            pass
        else:
            pwd = db_pwd  # 环境变量未配置才回退库值
    else:
        pwd = db_pwd or pwd  # 库值优先（旧行为）
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
        # v3.8.3 修复：此前静默吞掉异常，导致「错误详情见后端日志」查不到内容。
        # 现在把完整异常栈打到 stderr（gunicorn 会捕获进 gunicorn.log），便于定位。
        import sys, traceback
        sys.stderr.write("[SMTP ERROR] 邮件发送失败，详情：\n" + traceback.format_exc() + "\n")
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
    在新文章发布时调用（不阻塞发布主流程）。异常记日志但不抛出。

    ## v3.20.0：只传 `post.id` 进线程，线程内**重新查库**

    **这是纵深防御，不是修 bug** —— 先把实测事实写清楚，免得后人误判：

    调用点都在 `db.session.commit()` 之后（见 `admin/post_editor.py`），
    而线程里 push 的是**新的 app context（= 新 session）**，原对象已 detach。
    我原以为这会让属性访问抛 `DetachedInstanceError`，但**实测证伪**
    （Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.52）：detached 的 `Post` 上
    **标量属性照常可读**（值仍在实例 `__dict__`），所以原写法对
    `_build_mail`（只读 title/summary/content/slug 四个标量）**本来就能工作**。

    真正的风险边界是**懒加载关系**：detached 实例上访问从未加载的关系
    （如 `post.author`）会抛 `DetachedInstanceError`，再被 `except Exception` 吞掉
    → 「订阅者静默收不到信」，且**只有配了 SMTP 的部署才会遇到**。

    所以这里改为传 id + 线程内 `db.session.get(Post, pid)`：
    线程拿到的是**属于新 session 的活对象**，标量与关系都安全，
    顺便还取到的是**最新状态**（而非提交那一刻的快照）。
    代价是多一次主键查询 —— 相对一次 SMTP 往返可以忽略。
    """
    pid = getattr(post, "id", None)   # ⚠️ 必须在调用线程里取（session 尚可用）
    if not pid:
        return

    def _worker():
        try:
            from models import db, Post, Subscriber
            cfg = load_mail_config()
            if not cfg.get("host") or not cfg.get("username"):
                return  # 未配置 SMTP，跳过
            fresh = db.session.get(Post, pid)
            if fresh is None:
                return  # 文章已被删除，静默跳过（不是错误）
            subs = Subscriber.query.filter_by(active=True).all()
            if not subs:
                return
            body_html, plain = _build_mail(fresh, cfg.get("site_url", ""))
            for sub in subs:
                token = sub.unsub_token or ""
                bh = _fill_unsub(body_html, sub.email, token)
                bp = _fill_unsub(plain, sub.email, token)
                _send_smtp(cfg, [sub.email], f"【新文章】{fresh.title}", bh, bp)
        except Exception:
            # 群发失败不影响发文章，但**必须留痕**（原为静默 pass）
            logger.warning("订阅者群发失败（post_id=%s）", pid, exc_info=True)

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
        logger.warning("起后台线程失败，订阅者群发未执行（post_id=%s）", pid,
                       exc_info=True)
