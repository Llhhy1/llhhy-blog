# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import admin_required, log_audit, super_required, admin_bp     # 同一蓝图对象
from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from models import Setting, db
from utils import fmt_bj, site_base
from _time import utcnow
import os
from urllib.parse import urlparse


def _normalize_site_url(raw):
    """清洗「站点对外地址（site_url）」输入（v3.25.5）。

    返回 `(value, error)`：
    - `error` 非空 → 这个值**不能写库**，调用方应提示用户（但其它字段照常保存，
      不能因为一个字段填错就丢掉整张表单的编辑）；
    - `value` 为 `""` → 用户主动清空，写库即「未配置」。

    为什么必须校验：`site_url` 是全站绝对地址的**唯一真相源**，填成
    `www.llhhy.cn/post/1`、`javascript:alert(1)` 或 `https://a.com/?x=1`
    会让 canonical / og:url / sitemap / 二维码内容整体漂移，而且**不报错**——
    只会静默产生错误的对外声明，等发现时外链已经散出去了。
    """
    v = (raw or "").strip().rstrip("/")
    if not v:
        return "", None
    p = urlparse(v)
    if p.scheme not in ("http", "https"):
        return None, "必须以 http:// 或 https:// 开头（本次填写未保存）"
    if not (p.hostname or "").strip():
        return None, "缺少域名（本次填写未保存）"
    if p.path or p.query or p.fragment:
        return None, "只填「协议 + 域名」，不要带路径或参数（本次填写未保存）"
    try:
        port = f":{p.port}" if p.port else ""
    except ValueError:
        return None, "端口不是数字（本次填写未保存）"
    # 只保留 scheme://host[:port] —— netloc 里若带 userinfo（`https://u:p@host`）
    # 会被 hostname/port 重组时自然丢掉，站点地址不该含凭据。
    return f"{p.scheme}://{p.hostname}{port}", None


@admin_bp.route("/settings", methods=["GET", "POST"])
@super_required
def settings():
    if request.method == "POST":
        # v3.25.5：`site_url` 补进可保存字段——它是全站绝对地址的唯一真相源，
        # 但后台此前**根本没有输入框**，SEO 页却一直警告"未配置"并指向本页，
        # 等于把人指进死胡同（只能改环境变量或直接改库）。
        fields = ["site_url", "site_title", "site_name", "site_note", "site_description", "about_content", "footer_text",
                  "beian_code", "weather_lat", "weather_lon", "weather_city",
                  "accent_color",
                  "theme_mode", "theme_radius", "theme_font", "nav_style", "custom_css",
                  # v3.0.0 功能2：垃圾评论关键词（逗号分隔）；功能11：前台默认语言
                  "comment_spam_keywords", "site_lang", "reward_qr_default",
                  # v3.5.2 链接后缀全局模板
                  "slug_mode", "slug_template",
                  # v3.8.0 反爬限流保护配置
                  "bot_guard_threshold", "bot_guard_window", "bot_guard_tool_limit",
                  "bot_guard_block_hits", "bot_guard_block_minutes", "seo_block_bots"]
        # v3.25.2：**改动之前**拍快照（必须在这里，否则快照记的是新值，
        # 回滚会「成功」但毫无作用）。含下面两个 checkbox。
        _cfg_snapshot = None
        try:
            import config_rollback as _cr
            _snap_keys = list(fields) + ["comment_require_approval", "comment_email_required"]
            _cfg_snapshot = _cr.snapshot_settings(_snap_keys, reason="设置页保存")
        except Exception:
            _cfg_snapshot = None
        # site_url 单独清洗：其它字段原样取表单值，只有它必须先过校验。
        _site_url_value, _site_url_error = _normalize_site_url(request.form.get("site_url", ""))
        for f in fields:
            if f == "site_url":
                if _site_url_value is None:
                    continue        # 校验没过：一个字段填错不该丢掉整张表单的其它编辑
                val = _site_url_value
            else:
                val = request.form.get(f, "")
            row = Setting.query.filter_by(key=f).first()
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=f, value=val))
        # 评论审核开关（checkbox：勾选=true，不勾选=空）
        cap = Setting.query.filter_by(key="comment_require_approval").first()
        cap_val = "true" if request.form.get("comment_require_approval") else "false"
        if cap:
            cap.value = cap_val
        else:
            db.session.add(Setting(key="comment_require_approval", value=cap_val))
        # v3.15.3 功能1：评论邮箱必填开关（checkbox：勾选=true，不勾选=空）
        cer = Setting.query.filter_by(key="comment_email_required").first()
        cer_val = "true" if request.form.get("comment_email_required") else "false"
        if cer:
            cer.value = cer_val
        else:
            db.session.add(Setting(key="comment_email_required", value=cer_val))
        # v3.8.0：反爬限流两个开关（checkbox：勾选=true，不勾选=空）
        for cb in ("bot_guard_enabled", "bot_guard_search_whitelist"):
            row = Setting.query.filter_by(key=cb).first()
            val = "true" if request.form.get(cb) else "false"
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=cb, value=val))
        db.session.commit()
        if _site_url_error:
            flash("站点对外地址（site_url）" + _site_url_error)
        flash("站点设置已保存")
        return redirect(url_for("admin.settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    # site_base_now：**实际生效**的对外地址（DB site_url → 环境变量 SITE_URL → 空），
    # 让页面能直接显示"当前是什么"，而不是只回显输入框里那个值。
    return render_template("admin/settings.html", settings=settings, site_base_now=site_base())

@admin_bp.route("/api/slug-preview", methods=["GET"])
@admin_required
def slug_preview():
    """v3.5.2：链接后缀模板实时预览（只读 GET，不受 CSRF 限制）。

    参数：title（文章标题）、mode（slug_mode）、tpl（自定义模板串）。
    返回 JSON {slug}，slug 经 render_slug_template 清洗（仅合法 slug 字符），
    前端用 textContent 输出，天然转义，无 XSS。
    """
    from utils import render_slug_template, make_slug, SLUG_PRESETS

    title = (request.args.get("title") or "").strip()
    mode = (request.args.get("mode") or "title").strip()
    tpl = (request.args.get("tpl") or "").strip()
    if mode == "custom":
        template = tpl or ""
    else:
        template = SLUG_PRESETS.get(mode, SLUG_PRESETS["title"])
    # 预览用占位数据：ID=123、日期=今天、分类=技术
    date_str = fmt_bj(utcnow(), "%Y%m%d")
    slug = render_slug_template(
        template,
        slug=make_slug(title) if title else "示例文章",
        post_id=123,
        date=date_str,
        category="技术",
    )
    return jsonify({"slug": slug or "post"})


# ===== v3.25.2：配置快照与回滚 =====
@admin_bp.route("/config-history")
@super_required
def config_history():
    """配置变更历史（快照列表 + 与当前值的差异预览）。

    **为什么是 @super_required**：回滚是特权操作（能把限流阈值、SMTP 主机改回去），
    权限必须与「改设置」本身同级。列表页同样不放给普通管理员 ——
    快照里有值，等于泄露了配置全貌。
    """
    import config_rollback as cr
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    per = 20
    total_n = cr.snapshot_count()
    snaps = cr.list_snapshots(limit=per, offset=(page - 1) * per)
    # 预览：只算第一页的差异（每条快照的 diff 都要查库，翻页时全算太重）
    previews = {}
    for s in snaps:
        d = cr.diff_snapshot(s.id)
        previews[s.id] = d if d is not None else None
    return render_template("admin/config_history.html",
                           snapshots=snaps, previews=previews,
                           total_n=total_n, page=page, per=per,
                           last_at=cr.last_snapshot_at())


@admin_bp.route("/config-rollback/<int:snapshot_id>", methods=["GET", "POST"])
@super_required
def config_rollback(snapshot_id):
    """配置回滚。**GET = 差异预览，POST = 执行**（同一个端点两用）。

    ⚠️ 这里刻意用「一个函数 + methods=[GET, POST]」而不是拆成两个同名路由：
    拆成两个 `def config_rollback` 时后一个会**覆盖**前一个，
    Flask 只注册到最后那个 → POST 端点直接 405（第一版真写错了）。

    **两个刻意设计**：
    1. POST 必须带 `confirm=yes` —— 覆盖当前配置是高破坏性操作，
       不能一个误点就生效；不带 confirm 就退回预览页让人再看一遍。
    2. 预览必须先看清「会改哪些项、当前值是什么」—— 特权操作标配。

    snapshot_id 用 `<int:>` 约束，非整数直接 404（不把任意字符串喂进 db.session.get）。
    """
    import config_rollback as cr
    d = cr.diff_snapshot(snapshot_id)
    if d is None:
        flash("快照不存在、已过期或内容损坏", "error")
        return redirect(url_for("admin.config_history"))
    if not d:
        flash("该快照与当前配置完全一致，无需回滚", "info")
        return redirect(url_for("admin.config_history"))

    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            flash("回滚是高风险操作，请勾选确认后再提交", "error")
            return redirect(url_for("admin.config_rollback", snapshot_id=snapshot_id))
        keys = request.form.getlist("keys") or None
        ok, msg = cr.rollback(snapshot_id, keys=keys, confirm=True)
        flash(msg, "success" if ok else "error")
        return redirect(url_for("admin.config_history"))

    return render_template("admin/config_rollback.html",
                           snapshot_id=snapshot_id, changes=d)


@admin_bp.route("/captcha-settings", methods=["GET", "POST"])
@super_required
def captcha_settings():
    """验证码独立设置页（v3.2.0）：全局开关 + 长度 + 难度 + 排除易混字符 + 各场景开关，存 Setting 表。"""
    keys = ["captcha_enabled", "captcha_length", "captcha_difficulty", "captcha_exclude_ambiguous",
            "captcha_on_register", "captcha_on_comment", "captcha_on_guestbook"]
    bool_keys = {"captcha_enabled", "captcha_exclude_ambiguous",
                 "captcha_on_register", "captcha_on_comment", "captcha_on_guestbook"}
    if request.method == "POST":
        for k in keys:
            val = "true" if (k in bool_keys and request.form.get(k)) else (
                request.form.get(k, "").strip() if k not in bool_keys else "false")
            row = Setting.query.filter_by(key=k).first()
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=k, value=val))
        db.session.commit()
        flash("验证码设置已保存")
        return redirect(url_for("admin.captcha_settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    defaults = {
        "captcha_enabled": "true", "captcha_length": "4", "captcha_difficulty": "normal",
        "captcha_exclude_ambiguous": "true", "captcha_on_register": "true",
        "captcha_on_comment": "true", "captcha_on_guestbook": "true",
    }
    for k, v in defaults.items():
        settings.setdefault(k, v)
    from security import get_captcha_config
    return render_template("admin/captcha_settings.html", settings=settings,
                           captcha_cfg=get_captcha_config())

@admin_bp.route("/backup", methods=["GET", "POST"])
@super_required
def backup():
    """数据备份管理（v3.3.0）：列表 / 立即备份 / 下载 / 恢复。

    恢复是高危操作：仅超管（@super_required）+ 全局 CSRF 校验 + 表单二次确认
    （confirm=yes）+ 恢复前自动快照 + 写审计日志。密钥只走环境变量，页面不回显。
    """
    import backup as backup_mod
    remote_status = backup_mod.remote_status()
    backups = backup_mod.list_backups()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "backup_now":
            # v3.23.0 #48：`create_backup` 内含 scp/curl 远程同步（`_run(timeout=300)`），
            # 同步跑会**长期占住一个 gunicorn 并发槽**（gthread 只有 8 个），
            # 几个这样的请求就能把整站拖成 502。改为后台任务 + 页面轮询。
            import tasks as tasks_mod
            tid, err = tasks_mod.submit("backup", backup_mod.create_backup)
            if err:
                log_audit("backup", target="创建备份", detail=err, success=False)
                flash(err)
                return redirect(url_for("admin.backup"))
            log_audit("backup", target="创建备份", detail="后台任务已提交：%s" % tid)
            return redirect(url_for("admin.backup", task=tid))
        if action == "verify_now":
            # v3.25.2：手动触发一次巡检。**刻意复用后台任务模型**而不是同步跑 ——
            # verify 要把每个包完整读一遍算 SHA256（3MB/包起），同步跑同样会占并发槽。
            import tasks as tasks_mod
            tid, err = tasks_mod.submit("backup-verify", backup_mod.verify_latest)
            if err:
                log_audit("backup", target="备份巡检", detail=err, success=False)
                flash(err)
                return redirect(url_for("admin.backup"))
            log_audit("backup", target="备份巡检", detail="后台任务已提交：%s" % tid)
            return redirect(url_for("admin.backup", task=tid))
        fn = request.form.get("file", "")
        fp = os.path.join(backup_mod.BACKUP_ROOT, fn) if fn else ""
        safe = bool(fn and os.path.basename(fn) == fn and fn.startswith("blog_backup_")
                    and os.path.exists(fp))
        if action == "download":
            if safe:
                return send_file(fp, as_attachment=True, download_name=fn)
            flash("备份文件不存在")
            return redirect(url_for("admin.backup"))
        if action == "restore":
            if request.form.get("confirm") != "yes":
                flash("恢复是高危操作，需勾选二次确认")
                return redirect(url_for("admin.backup"))
            if not safe:
                flash("备份文件不存在")
                return redirect(url_for("admin.backup"))
            try:
                r = backup_mod.restore(fp, yes=True, tag="admin")
                flash("已从 %s 恢复（恢复前快照 %s）。请到宝塔「停止」再「启动」站点使数据库生效。"
                      % (fn, os.path.basename(r["snapshot"])))
                log_audit("backup_restore", target="恢复备份", target_id=fn,
                          detail="快照 %s" % os.path.basename(r["snapshot"]))
            except Exception as e:
                log_audit("backup_restore", target="恢复备份", target_id=fn,
                          detail=str(e)[:200], success=False)
                flash("恢复失败：" + str(e)[:200])
            return redirect(url_for("admin.backup"))
    # v3.17.13：把「更全面」的运维数据一次性算好传给模板（零新增表/字段）
    import config as _cfg
    total_size = sum((b.get("size") or 0) for b in backups)
    for _b in backups:
        _b["size_h"] = backup_mod.fmt_size(_b.get("size") or 0)
        _b["stamp"] = backup_mod.backup_stamp(_b.get("file"))
    _up_dir = os.path.join(_cfg.BASE_DIR, "static", "uploads")
    _up_size, _up_count = backup_mod.dir_stat(_up_dir)
    summary = {
        "count": len(backups),
        "total_size_h": backup_mod.fmt_size(total_size),
        "db_size_h": backup_mod.fmt_size(backup_mod.file_size(os.path.join(_cfg.DATA_DIR, "blog.db"))),
        "uploads_size_h": backup_mod.fmt_size(_up_size),
        "uploads_count": _up_count,
        "latest_at": (backups[-1].get("stamp") or backups[-1].get("created_at") or "") if backups else "",
        "remote_count": sum(1 for _k in ("oss", "scp", "webdav") if remote_status.get(_k)),
    }
    # v3.23.0 #48：提交后台任务后带 ?task=<id> 回来，页面据此轮询进度
    task_id = (request.args.get("task") or "").strip()
    # v3.25.2：把最近一次自动巡检结果带进页面（读文件，不查库 —— 与 tasks 状态同思路）
    return render_template("admin/backup.html", backups=backups, remote_status=remote_status,
                           retention=backup_mod.RETENTION_DAYS, summary=summary,
                           task_id=task_id, verify_state=backup_mod.read_verify_state())

@admin_bp.route("/backup-settings", methods=["GET", "POST"])
@super_required
def backup_settings():
    """备份配置后台化（v3.4.0）：目的地/保留天数/密钥等全部在后台配置。
    非密钥字段存 Setting 表；密钥字段（OSS Secret / WebDAV 密码 / SCP 私钥路径）
    用 SECRET_KEY 派生的 Fernet 密钥加密后存储，页面只回显掩码、绝不回显明文。
    读取优先级：非密钥「库优先」；密钥「环境变量优先、库值兜底」。
    """
    import backup_settings as bs
    from utils import get_setting
    # 回显用：非敏感键回显库值（或占位空），敏感键回显掩码（或空=未设置）
    values = {}
    for skey in bs.ALL_FIELDS:
        if skey in bs.SENSITIVE_KEYS:
            values[skey] = bs.setting_value_for_admin(skey)  # 掩码
        else:
            values[skey] = get_setting(skey, "") or ""
    # 各后端是否已配置（合并视角），用于提示当前生效来源
    cfg = bs.get_config()
    enabled = {
        "local": True,
        "oss": bool(cfg.get("BACKUP_OSS_BUCKET")),
        "scp": bool(cfg.get("BACKUP_SCP_HOST")),
        "webdav": bool(cfg.get("BACKUP_WEBDAV_URL")),
    }
    if request.method == "POST":
        for skey in bs.ALL_FIELDS:
            if skey in bs.SENSITIVE_KEYS:
                # 敏感键：留空 = 保持不变；非空则加密覆盖
                new_val = (request.form.get(skey) or "").strip()
                cur_db = bs.read_setting_db(skey) or ""
                if new_val and new_val != bs.mask_value(bs.decrypt_secret(cur_db or "")):
                    bs.write_setting_db(skey, bs.encrypt_secret(new_val))
                # 密码留空：保持原库值（不回显、不覆盖）
            else:
                val = (request.form.get(skey) or "").strip() if skey != "backup_retention_days" \
                    else (request.form.get(skey) or "14").strip()
                if skey == "backup_retention_days":
                    try:
                        int(val)
                    except ValueError:
                        flash("保留天数必须是数字")
                        return redirect(url_for("admin.backup_settings"))
                bs.write_setting_db(skey, val)
        # 重新合并进环境变量，本次进程立即生效
        bs.apply_env()
        try:
            import backup as backup_mod
            backup_mod.BACKUP_ROOT = backup_mod._DEF_BACKUP_DIR if bs.get_config().get("BACKUP_DIR") == backup_mod._DEF_BACKUP_DIR \
                else bs.get_config().get("BACKUP_DIR") or backup_mod._DEF_BACKUP_DIR
            backup_mod.RETENTION_DAYS = int(bs.get_config().get("BACKUP_RETENTION_DAYS") or 14)
        except Exception:
            pass
        flash("备份配置已保存")
        return redirect(url_for("admin.backup_settings"))
    return render_template("admin/backup_settings.html", values=values, enabled=enabled,
                           settings_cfg=cfg)

@admin_bp.route("/email-settings", methods=["GET", "POST"])
@super_required
def email_settings():
    """邮件群发设置（C3）：SMTP 配置存 Setting 表，mail_notify.py 读取时优先库值、回退环境变量。
    密码不回显：保存时密码留空 = 保持不变。提供「发送测试邮件」验证配置。
    """
    from utils import rate_limit, client_key
    if request.method == "POST":
        action = request.form.get("action", "save")
        # 保存配置
        if action == "save":
            host = (request.form.get("mail_host") or "").strip()
            vals = {
                "mail_host": host,
                "mail_port": (request.form.get("mail_port") or "465").strip() or "465",
                "mail_username": (request.form.get("mail_username") or "").strip(),
                "mail_from": (request.form.get("mail_from") or "").strip(),
                "mail_use_ssl": "true" if request.form.get("mail_use_ssl") else "false",
            }
            # 密码：仅当输入了非空值才更新（不回显、留空保持原值）
            pwd = request.form.get("mail_password") or ""
            if pwd.strip():
                vals["mail_password"] = pwd.strip()
            for k, v in vals.items():
                row = Setting.query.filter_by(key=k).first()
                if row:
                    row.value = v
                else:
                    db.session.add(Setting(key=k, value=v))
            db.session.commit()
            flash("邮件设置已保存")
            return redirect(url_for("admin.email_settings"))
        # 发送测试邮件（限流防滥用）
        if action == "test":
            if not rate_limit(client_key("admin_mail_test"), limit=5, window=300):
                flash("测试邮件发送过于频繁，请 5 分钟后再试", "error")
                return redirect(url_for("admin.email_settings"))
            to = (request.form.get("test_to") or "").strip()
            if not to:
                flash("请填写测试收件人邮箱", "error")
                return redirect(url_for("admin.email_settings"))
            # 用表单当前值（含新填密码）+ 库中已存值组装测试配置，不落库
            import mail_notify
            cfg = mail_notify.load_mail_config()
            cfg["host"] = (request.form.get("mail_host") or cfg["host"]).strip()
            cfg["port"] = int((request.form.get("mail_port") or str(cfg["port"])).strip() or 465)
            cfg["username"] = (request.form.get("mail_username") or cfg["username"]).strip()
            cfg["from"] = (request.form.get("mail_from") or cfg["from"]).strip()
            if request.form.get("mail_use_ssl") is not None:
                cfg["use_ssl"] = True
            pwd = request.form.get("mail_password") or ""
            if pwd.strip():
                cfg["password"] = pwd.strip()
            ok = mail_notify.send_test_mail(cfg, to)
            if ok:
                flash(f"测试邮件已发送到 {to}，请查收（含垃圾箱）")
            else:
                flash("发送失败：请检查 SMTP 配置（主机/端口/授权码/SSL 开关），错误详情见后端日志", "error")
            return redirect(url_for("admin.email_settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/email_settings.html", settings=settings)
