# -*- coding: utf-8 -*-
"""Web 辅助：安全重定向与 @ 提及通知。（utils 子模块，v3.18.1 由 utils.py 拆出）。"""
import re

# ---------- 安全重定向（防开放重定向）----------
def safe_redirect(target, default="/"):
    """仅允许站内相对路径跳转；以 // 开头的协议相对路径会被拒绝。"""
    if not target:
        return default
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def is_http_url(url):
    """是否可以**直接放进 href 的外站地址**：仅放行 http/https 绝对 URL（v4.0.0）。

    为什么外链入口要单独判一次：入口地址由后台填写、前台用 ``:href`` 绑定，
    ``javascript:`` / ``data:`` 这类 scheme 会被浏览器当脚本执行 —— 即**存储型 XSS**。
    只有超管能填不等于可以不校验（手滑、被注入、迁移脏数据都会中招），
    且这类错误**不报错**，只会安静地在访客浏览器里跑起来。

    同时拒绝协议相对地址 ``//evil.com``：它会继承本站协议并指向外域，
    既不符合「外站入口」的意图，也不利于审计。
    """
    from urllib.parse import urlparse
    v = (url or "").strip()
    if not v:
        return False
    if any(ch.isspace() for ch in v):
        return False
    p = urlparse(v)
    return p.scheme in ("http", "https") and bool((p.hostname or "").strip())


def notify_mentioned(content, link, from_author, post_id=None):
    """解析评论/动态内容里的 @username，给被提及的注册用户生成站内通知。
    - content: 评论原文；link: 点击通知跳转地址；from_author: 提及者昵称（文案用）
    - 仅给存在的注册用户发通知，不重复，自己@自己不发
    """
    try:
        from models import db, User, Notification
        names = set(re.findall(r"@([A-Za-z0-9_\u4e00-\u9fa5]{2,40})", content or ""))
        # R114 审计：@提及**必须限量**。此前无上限，匿名可提交 5MB 正文
        # 塞满互不相同的 @名字 → 单次请求扇出上万次 User.query + 上万条
        # Notification 行 = 匿名放大的 DoS + 通知表膨胀。
        names = list(names)[:20]
        if not names:
            return
        for name in names:
            u = User.query.filter_by(username=name).first()
            if u and u.username != from_author:
                db.session.add(Notification(
                    user_id=u.id,
                    content=f"{from_author} 在评论中提到了你：{(content or '')[:80]}",
                    link=link or "",
                ))
        db.session.commit()
    except Exception:
        pass  # 通知失败不影响评论主流程
