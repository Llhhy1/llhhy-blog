# -*- coding: utf-8 -*-
# 自动切片自 admin.py（v3.11.0）：原样搬运，路由/行为不变。
from ._helpers import *   # 复用导入、辅助函数与装饰器
from . import admin_bp     # 同一蓝图对象

@admin_bp.route("/settings", methods=["GET", "POST"])
@super_required
def settings():
    if request.method == "POST":
        fields = ["site_title", "site_name", "site_note", "site_description", "about_content", "footer_text",
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
        for f in fields:
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
        # v3.8.0：反爬限流两个开关（checkbox：勾选=true，不勾选=空）
        for cb in ("bot_guard_enabled", "bot_guard_search_whitelist"):
            row = Setting.query.filter_by(key=cb).first()
            val = "true" if request.form.get(cb) else "false"
            if row:
                row.value = val
            else:
                db.session.add(Setting(key=cb, value=val))
        db.session.commit()
        flash("站点设置已保存")
        return redirect(url_for("admin.settings"))
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=settings)

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
    date_str = fmt_bj(datetime.datetime.utcnow(), "%Y%m%d")
    slug = render_slug_template(
        template,
        slug=make_slug(title) if title else "示例文章",
        post_id=123,
        date=date_str,
        category="技术",
    )
    return jsonify({"slug": slug or "post"})

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
            try:
                arc, man, sync = backup_mod.create_backup()
                msg = "备份成功：%s（%d 个文件）" % (os.path.basename(arc), man["file_count"])
                for name, ok, s in sync:
                    msg += "；远程[%s]%s" % (name, "✅" if ok else "⚠️" + s)
                log_audit("backup", target="创建备份", detail=msg)
                flash(msg)
            except Exception as e:
                log_audit("backup", target="创建备份", detail=str(e)[:200], success=False)
                flash("备份失败：" + str(e)[:200])
            return redirect(url_for("admin.backup"))
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
    return render_template("admin/backup.html", backups=backups, remote_status=remote_status,
                           retention=backup_mod.RETENTION_DAYS)

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
        for skey, (env, default) in bs.ALL_FIELDS.items():
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
    mail_keys = ["mail_host", "mail_port", "mail_username", "mail_password", "mail_from", "mail_use_ssl"]
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
