# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import (_current_user_or_none, admin_required, create_announcement_core,
                       log_audit, super_required, unique_model_slug, update_announcement_core,
                       admin_bp)     # 同一蓝图对象
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from models import Announcement, Category, Guestbook, SocialAccount, Subscriber, db
from _time import utcnow
from config import APP_VERSION
import bot_guard
import diagnostics
import feed_agg
import os

@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        # v4.4.0：建分类的判据搬到 `admin.taxonomy.create_category_core`，
        # 与移动端 `/api/mobile/category` 走同一份代码（同名判据不能有两套）。
        from .taxonomy import create_category_core
        name = (request.form.get("name") or "").strip()
        new_id, err = create_category_core(name)
        if err:
            flash(err)
        else:
            flash("分类已添加")
            log_audit("create", "category", new_id, f"新建分类：{name}",
                      user=_current_user_or_none())
        return redirect(url_for("admin.categories"))
    cats = Category.query.order_by(Category.id).all()
    return render_template("admin/categories.html", cats=cats)

@admin_bp.route("/category/<int:cid>/rename", methods=["POST"])
@admin_required
def rename_category(cid):
    """分类编辑（v3.14.0）：改名（slug 自动重算并保持唯一）。

    v4.4.0：判据搬到 `admin.taxonomy.rename_category_core`，移动端改名共用同一份；
    改名会换 slug 且站点没有 301，所以把「旧 → 新」显示出来（原实现静默改，
    用户不知道外发链接已经失效）。
    """
    from .taxonomy import rename_category_core
    cat = Category.query.get_or_404(cid)
    name = (request.form.get("name") or "").strip()
    old_slug = cat.slug
    err, note = rename_category_core(cat, name)
    if err:
        flash(err)
    else:
        log_audit("rename", "category", cid,
                  f"分类改名：{name}（{old_slug} → {cat.slug}）", user=_current_user_or_none())
        flash(f"分类已更新：{name}" + (f"（{note}）" if note else ""))
    return redirect(url_for("admin.categories"))

@admin_bp.route("/social", methods=["GET", "POST"])
@admin_required
def social():
    """社交账号管理（广场页「我的社交账号」墙）。"""
    if request.method == "POST":
        platform = (request.form.get("platform") or "").strip()
        url = (request.form.get("url") or "").strip()
        if platform and url:
            db.session.add(SocialAccount(
                platform=platform,
                handle=(request.form.get("handle") or "").strip(),
                url=url,
                sort=request.form.get("sort", 0, type=int),
            ))
            db.session.commit()
            flash("社交账号已添加")
        return redirect(url_for("admin.social"))
    accounts = SocialAccount.query.order_by(SocialAccount.sort).all()
    return render_template("admin/social.html", accounts=accounts)

@admin_bp.route("/social/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_social(aid):
    acc = SocialAccount.query.get_or_404(aid)
    db.session.delete(acc)
    db.session.commit()
    flash("社交账号已删除")
    return redirect(url_for("admin.social"))

@admin_bp.route("/bot-guard", methods=["GET", "POST"])
@super_required
def bot_guard_view():
    """反爬限流保护看板 + 封禁管理（v3.8.0）。"""
    if request.method == "POST":
        action = request.form.get("action")
        ip = (request.form.get("ip") or "").strip()
        if action == "unblock" and ip:
            ok = bot_guard.unblock_ip(ip)
            flash("已解封 " + ip if ok else "未找到该 IP 的封禁记录")
        return redirect(url_for("admin.bot_guard_view"))
    data = bot_guard.guard_stats()
    return render_template("admin/bot_guard.html", stats=data, now=utcnow())

@admin_bp.route("/announcements", methods=["GET", "POST"])
@admin_required
def manage_announcements():
    if request.method == "POST":
        ann, err = create_announcement_core(request.form)
        if err:
            flash(err)
        else:
            flash("公告已添加")
            log_audit("create", "announcement", ann.id,
                      f"新建公告：{(ann.content or '')[:40]}", user=_current_user_or_none())
        return redirect(url_for("admin.manage_announcements"))
    items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", items=items)


@admin_bp.route("/announcement/<int:aid>/update", methods=["POST"])
@admin_required
def update_announcement(aid):
    """公告编辑（v4.4.0 新增）。

    之前后台**只有「新建 + 启停 + 删除」**，改一个字都得删了重建 —— 而公告一删就没法还原
    （不进回收站），重建还会把它掉到列表末尾。App 侧同样需要编辑，所以补在这里，
    落库逻辑与新建共用 `_announcement_fields`（内容非空 + level 白名单）。
    """
    a = Announcement.query.get_or_404(aid)
    err = update_announcement_core(a, request.form)
    flash(err or "公告已更新")
    if not err:
        log_audit("update", "announcement", a.id,
                  f"编辑公告：{(a.content or '')[:40]}", user=_current_user_or_none())
    return redirect(url_for("admin.manage_announcements"))


@admin_bp.route("/announcement/<int:aid>/toggle", methods=["POST"])
@admin_required
def toggle_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    # v4.4.0：网页按钮仍是「翻转」（点了就是相反状态，符合页面直觉）；
    # 移动端 JSON 传的是显式目标值，见 `/api/mobile/announcement/<id>/active`。
    a.active = not a.active
    db.session.commit()
    log_audit("toggle", "announcement", a.id,
              f"公告{'启用' if a.active else '停用'}", user=_current_user_or_none())
    return redirect(url_for("admin.manage_announcements"))


@admin_bp.route("/announcement/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_announcement(aid):
    a = Announcement.query.get_or_404(aid)
    preview = (a.content or "")[:40]
    db.session.delete(a)
    db.session.commit()
    log_audit("delete", "announcement", aid, f"删除公告：{preview}", user=_current_user_or_none())
    flash("公告已删除")
    return redirect(url_for("admin.manage_announcements"))

@admin_bp.route("/guestbook", methods=["GET"])
@admin_required
def manage_guestbook():
    rows = Guestbook.query.order_by(Guestbook.created_at.desc()).all()
    return render_template("admin/guestbook.html", rows=rows)

@admin_bp.route("/guestbook/<int:gid>/read", methods=["POST"])
@admin_required
def mark_guestbook_read(gid):
    """单条留言标记为已读。"""
    g = Guestbook.query.get_or_404(gid)
    g.is_read = True
    db.session.commit()
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/guestbook/read-all", methods=["POST"])
@admin_required
def mark_all_guestbook_read():
    """全部留言标记为已读。"""
    Guestbook.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("全部留言已标记为已读")
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/guestbook/<int:gid>/delete", methods=["POST"])
@admin_required
def delete_guestbook(gid):
    g = Guestbook.query.get_or_404(gid)
    preview = (g.content or "")[:40]
    db.session.delete(g)
    db.session.commit()
    # v4.4.0：这三类操作原先在 misc.py 里**一条审计都没有**（对照 moments.py 有 4 条）。
    # 留言删除是硬删、不进回收站，出事只能靠审计回推是谁删的，所以补上。
    # detail 只放正文预览，**不放 ip**（`audit.log_audit` 的纪律：敏感值不进 detail）。
    log_audit("delete", "guestbook", gid, f"删除留言：{preview}", user=_current_user_or_none())
    flash("留言已删除")
    return redirect(url_for("admin.manage_guestbook"))

@admin_bp.route("/subscribers", methods=["GET"])
@admin_required
def manage_subscribers():
    rows = Subscriber.query.order_by(Subscriber.created_at.desc()).all()
    return render_template("admin/subscribers.html", rows=rows)

@admin_bp.route("/subscribers/delete/<int:sid>", methods=["POST"])
@admin_required
def delete_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    email = sub.email
    db.session.delete(sub)
    db.session.commit()
    flash(f"已删除订阅者：{email}")
    return redirect(url_for("admin.manage_subscribers"))

@admin_bp.route("/subscribers/toggle/<int:sid>", methods=["POST"])
@admin_required
def toggle_subscriber(sid):
    sub = Subscriber.query.get_or_404(sid)
    sub.active = not sub.active
    db.session.commit()
    flash(f"已{'启用' if sub.active else '停用'}订阅者：{sub.email}")
    return redirect(url_for("admin.manage_subscribers"))

@admin_bp.route("/feed-diag", methods=["GET", "POST"])
@super_required
def feed_diag():
    """全站健康体检中心（仅超管）：汇总数据库/依赖/配置/备份/SEO/待办/前端构建/存储/RSS 聚合。

    POST 触发强制重新聚合（force=True），刷新 RSS 诊断；其余维度每次加载实时计算。
    诊断逻辑见 myblog/diagnostics.py（run_all）。
    """
    if request.method == "POST":
        try:
            feed_agg.get_circle_feed(force=True)
            flash("已强制刷新博客圈聚合与诊断")
        except Exception as e:
            flash("刷新失败：" + str(e)[:200])
        return redirect(url_for("admin.feed_diag"))
    result = diagnostics.run_all()
    return render_template("admin/feed_diag.html", result=result)

def _safe_admin_url(value):
    """插件声明的后台入口地址：**只允许站内相对路径**。

    非 "/" 开头的（`javascript:…`、协议相对 `//host/…`、外链）一律丢掉 ——
    这个值会被渲染成 `href`，放任它就等于允许第三方插件包在管理员上下文里
    挂一个「点一下就跑脚本」的链接。
    """
    u = str(value or "").strip()
    if not u.startswith("/") or u.startswith("//"):
        return ""
    return u


@admin_bp.route("/plugins")
@admin_required
def plugins():
    """插件管理页：列出已配置插件及其运行状态，支持运行时启停与整体重载。

    启停写 disabled 标记文件 + 内存覆盖，前端槽位即时生效；路由级启停需重启 gunicorn。
    """
    from plugins import (PLUGIN_REGISTRY, RUNTIME_DISABLED, _marker_path, _parse_list)
    cfg = current_app.config
    enabled = _parse_list(cfg.get("ENABLED_PLUGINS", ""))
    items = []
    for slug in enabled:
        m = PLUGIN_REGISTRY.get(slug, {})
        mp = _marker_path(cfg, slug)
        disabled = (slug in RUNTIME_DISABLED) or (mp and os.path.exists(mp))
        items.append({
            "slug": slug,
            "name": m.get("name", slug),
            "version": m.get("version", ""),
            "author": m.get("author", ""),
            "description": m.get("description", ""),
            "slots": m.get("slots", []) or [],
            "loaded": slug in PLUGIN_REGISTRY,
            "disabled": bool(disabled),
            # v4.8.x：带后台页面的插件可声明 admin_url，插件管理页据此给一个「打开」入口
            # ⚠️ 只允许**站内相对路径**（以 "/" 开头）：admin_url 会被渲染成 href，
            # 放任 javascript: / 协议相对 URL（//evil.com）就等于给插件一个
            # 「点一下就在管理员上下文里执行脚本」的口子。插件本身已有代码执行权，
            # 但 manifest 常常是用户没读过的第三方包 —— 这里多挡一道是一道。
            "admin_url": _safe_admin_url(m.get("admin_url", "")),
        })
    return render_template("admin/plugins.html", plugins=items, app_version=APP_VERSION)


@admin_bp.route("/task/<task_id>")
@admin_required
def task_status(task_id):
    """后台长任务状态轮询（v3.23.0 #48）。

    前端提交「立即备份 / LLM 审计 / AI 摘要」后拿到 task_id，用本端点轮询，
    避免这三个 90~300s 的操作长期占住 gunicorn 的并发槽。
    状态来自**文件**（data/tasks/<id>.json）——不能放内存，因为 4 个 worker
    是独立进程，提交在 A、轮询可能打到 B。
    """
    import tasks as tasks_mod
    st = tasks_mod.status(task_id)
    if st is None:
        return jsonify({"state": "unknown", "message": "任务不存在或已过期"}), 404
    # 只回前端需要的字段，不把内部字段（started_at 等浮点）全部外泄
    return jsonify({
        "id": st.get("id", ""),
        "name": st.get("name", ""),
        "state": st.get("state", "unknown"),
        "message": st.get("message", ""),
        "error": st.get("error", ""),
    })
