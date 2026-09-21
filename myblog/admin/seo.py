# -*- coding: utf-8 -*-
"""v3.19.0：后台「🔍 收录」页 —— 主动推送收录控制台。

清单 2.0 的边界（**本模块严格不越界**）：
    UA 分类（`utils/text.py:detect_bot`）、搜索引擎豁免开关
    （`bot_guard.bot_guard_search_whitelist`）、坏 Bot 屏蔽
    （`Setting.seo_block_bots`，UI 在「站点设置」）、sitemap/robots 生成
    （`routes.py` /sitemap.xml /robots.txt）**全都已经存在**。
    本页只做两件真正缺的事：**主动推送 + 通道自检**，其余一律给跳转链接，
    不复制控件、不新开顶级菜单的分组。

安全要点（清单 2.2）：
    - token 走 `backup_settings.encrypt_secret()` 加密存 `Setting`
      （**不照抄 `mail_password` 的明文落库错误做法**）；
    - 全部路由 `@super_required`；
    - 写操作一律 `log_audit(...)`；
    - 表单带 CSRF（`csrf_input()`，全局 `_csrf_protect` 兜底）；
    - 推送丢后台线程，接口立即返回（清单 2.3 纪律 2）。
"""
from flask import request, render_template, redirect, url_for, flash

from models import db, Post, Setting, SeoSubmission
from models import visible_posts_query
from utils import get_setting, site_base, seo_shell_ua
from ._helpers import admin_bp, super_required, log_audit, _current_user_or_none
import seo_push

# 单次批量推送的默认篇数（页面可选）
BATCH_CHOICES = (10, 20, 50)
# 密钥键名（Setting）
BAIDU_TOKEN_KEY = "seo_baidu_token_enc"
INDEXNOW_KEY_KEY = "seo_indexnow_key_enc"


def _mask(has_value):
    """有值回显掩码，绝不回显明文（清单 2.4：页面不出现 token）。"""
    return "••••••••" if has_value else ""


def _engine_status_map(post_ids):
    """返回 {post_id: {"baidu": row, "indexnow": row}}，供列表渲染。"""
    if not post_ids:
        return {}
    out = {}
    # 用 in 一次查完，避免 N+1（列表页最多 100 篇）
    rows = SeoSubmission.query.filter(SeoSubmission.post_id.in_(post_ids)).all()
    for r in rows:
        out.setdefault(r.post_id, {})[r.engine] = r
    return out


@admin_bp.route("/seo")
@super_required
def seo_console():
    """收录控制台首页：通道自检 + 文章推送状态 + sitemap/robots 预览。"""
    # --- 通道自检的样本文章：最近一篇可见文章（自检在浏览器端异步拉 /api/seo/shell-check）
    sample = visible_posts_query().order_by(Post.created_at.desc()).first()

    # --- 文章列表（只列可见文章：草稿/隐私/回收站/未到点定时不该被推送收录）
    q = (request.args.get("q") or "").strip()
    queryset = visible_posts_query()
    if q:
        queryset = queryset.filter(Post.title.like("%" + q + "%"))
    posts = queryset.order_by(Post.created_at.desc()).limit(100).all()

    st = _engine_status_map([p.id for p in posts])
    rows = []
    for p in posts:
        m = st.get(p.id, {})
        rows.append({"p": p, "baidu": m.get("baidu"), "indexnow": m.get("indexnow")})

    # --- 统计
    total_visible = visible_posts_query().count()
    pushed_baidu = (SeoSubmission.query.filter_by(engine="baidu", status="ok").count())
    pushed_bing = (SeoSubmission.query.filter_by(engine="indexnow", status="ok").count())

    # --- 各类不可见文章的篇数（让超管一眼看到「有多少篇不会被收录」）
    hidden = {
        "草稿": Post.query.filter_by(published=False, in_trash=False).count(),
        "隐私": Post.query.filter_by(is_private=True, in_trash=False).count(),
        "回收站": Post.query.filter_by(in_trash=True).count(),
    }

    base = site_base()
    return render_template(
        "admin/seo.html", rows=rows, q=q,
        sample_slug=(sample.slug if sample else ""),
        total_visible=total_visible, pushed_baidu=pushed_baidu,
        pushed_bing=pushed_bing, hidden=hidden,
        site_base=base,
        has_baidu_token=bool(get_setting(BAIDU_TOKEN_KEY, "")),
        has_indexnow_key=bool(get_setting(INDEXNOW_KEY_KEY, "")),
        baidu_token_mask=_mask(bool(get_setting(BAIDU_TOKEN_KEY, ""))),
        indexnow_key_mask=_mask(bool(get_setting(INDEXNOW_KEY_KEY, ""))),
        baidu_quota=get_setting(seo_push.QUOTA_KEY, "") or "",
        batch_choices=BATCH_CHOICES,
        # 只读展示既有开关的当前值（**不复制控件**，给跳转链接）
        search_whitelist=get_setting("bot_guard_search_whitelist", "1"),
        block_bots=get_setting("seo_block_bots", "") or "",
    )


@admin_bp.route("/seo/token", methods=["POST"])
@super_required
def seo_save_token():
    """保存百度 token / IndexNow key（加密存储）。留空 = 保持不变。"""
    import backup_settings as bs
    changed = []

    new_token = (request.form.get("baidu_token") or "").strip()
    if new_token:
        _write_secret(BAIDU_TOKEN_KEY, bs.encrypt_secret(new_token))
        changed.append("百度 token")
    # 显式清除（勾选「清除」而非留空——留空语义已给「保持不变」）
    if request.form.get("clear_baidu_token"):
        _write_secret(BAIDU_TOKEN_KEY, "")
        changed.append("百度 token（已清除）")

    new_key = (request.form.get("indexnow_key") or "").strip()
    if new_key:
        if not _valid_indexnow_key(new_key):
            flash("⚠️ IndexNow key 必须是 8–128 位，且只含字母、数字与短横线——"
                  "否则 Bing 会拒绝，且 keyLocation 文件无法命名。")
            return redirect(url_for("admin.seo_console"))
        _write_secret(INDEXNOW_KEY_KEY, bs.encrypt_secret(new_key))
        changed.append("IndexNow key")
    if request.form.get("clear_indexnow_key"):
        _write_secret(INDEXNOW_KEY_KEY, "")
        changed.append("IndexNow key（已清除）")

    if changed:
        # 审计日志只记「改了哪个键」，**绝不记值**
        log_audit("update", "setting", 0, "SEO 推送凭据更新：" + "、".join(changed),
                  user=_current_user_or_none())
        flash("已保存：" + "、".join(changed) + "（密文存储，页面不回显）")
    else:
        flash("没有改动")
    return redirect(url_for("admin.seo_console"))


def _valid_indexnow_key(key):
    """IndexNow key 规范：8–128 字符，仅 [A-Za-z0-9-]。

    校验它的理由是**实打实的**：key 会被拼进 `keyLocation` URL
    （`https://<host>/<key>.txt`），不校验的话可以塞进 `/`、`..`、
    空格甚至 `#`，把 keyLocation 指向站内任意路径，甚至让 Bing 去
    请求一个我们没打算公开的文件。这不是洁癖，是 URL 注入面。
    """
    if not (8 <= len(key) <= 128):
        return False
    return all(c.isalnum() or c == "-" for c in key)


def _write_secret(key, value):
    """写 Setting（供密钥存储），异常静默。"""
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


@admin_bp.route("/seo/push", methods=["POST"])
@super_required
def seo_push_now():
    """单篇 / 批量推送。**立即返回**，真正的外发在后台线程。

    post_id 为空 + batch=N → 推送最近 N 篇「未成功推送」的可见文章。
    """
    engine = (request.form.get("engine") or "baidu").strip()
    if engine not in seo_push.ENGINES:
        flash("未知推送引擎")
        return redirect(url_for("admin.seo_console"))

    post_id = (request.form.get("post_id") or "").strip()
    if post_id:
        p = db.session.get(Post, int(post_id)) if post_id.isdigit() else None
        if not p:
            flash("文章不存在")
            return redirect(url_for("admin.seo_console"))
        # 只推可见文章：草稿/隐私/回收站/未到点定时不该被提交给搜索引擎
        visible = visible_posts_query().filter(Post.id == p.id).first()
        if not visible:
            log_audit("seo_push_reject", "post", p.id,
                      "拒绝了不可见文章的推送（%s）" % engine,
                      user=_current_user_or_none(), success=False)
            flash("⚠️ 该文章对访客不可见（草稿/隐私/回收站/未到点定时），不予推送——"
                  "给搜索引擎送去 404 会浪费配额并降低站点质量评分。")
            return redirect(url_for("admin.seo_console"))
        ids = [p.id]
    else:
        try:
            n = int(request.form.get("batch") or 20)
        except ValueError:
            n = 20
        n = max(1, min(n, max(BATCH_CHOICES)))
        # 已成功推送过的不再重发（省配额）；失败/pending 的重推
        done_ids = {r.post_id for r in SeoSubmission.query.filter_by(engine=engine, status="ok").all()}
        cand = visible_posts_query().order_by(Post.created_at.desc()).limit(n * 3).all()
        ids = [p.id for p in cand if p.id not in done_ids][:n]
        if not ids:
            flash("最近 %d 篇都已成功推送到该引擎，无需重推。" % n)
            return redirect(url_for("admin.seo_console"))

    n_enq = seo_push.enqueue(ids, engine, actor=_current_user_or_none())
    flash("已入队 %d 篇（%s），推送在后台进行——稍后刷新本页查看结果。" % (n_enq, engine))
    return redirect(url_for("admin.seo_console"))


@admin_bp.route("/seo/status")
@super_required
def seo_status():
    """轮询接口：返回当前推送状态汇总（页面 JS 定时拉，实现「不阻塞」体验）。"""
    from flask import jsonify
    rows = SeoSubmission.query.order_by(SeoSubmission.submitted_at.desc()).limit(300).all()
    data = [{
        "post_id": r.post_id, "engine": r.engine, "status": r.status,
        "submitted_at": (r.submitted_at or "").strftime("%Y-%m-%d %H:%M:%S") if r.submitted_at else "",
        "response": r.response or "",
    } for r in rows]
    counts = {"pending": 0, "ok": 0, "fail": 0, "quota": 0}
    for r in rows:
        if r.status in counts:
            counts[r.status] += 1
    return jsonify(rows=data, counts=counts,
                   quota=get_setting(seo_push.QUOTA_KEY, "") or "")


@admin_bp.route("/seo/preview")
@super_required
def seo_preview():
    """sitemap / robots 只读预览（清单 2.0：只做预览，不改生成逻辑）。

    直接复用 `routes.sitemap()` / `routes.robots()` 的响应体——**不重写生成逻辑**，
    否则预览与实际输出必然漂移。
    """
    from flask import jsonify
    from routes import sitemap as _sitemap_view, robots as _robots_view
    kind = request.args.get("kind", "sitemap")
    try:
        if kind == "robots":
            resp = _robots_view()
        else:
            resp = _sitemap_view()
        body = resp.get_data(as_text=True)
    except Exception as e:
        return jsonify(error="生成失败：%s" % type(e).__name__), 500
    return jsonify(kind=kind, body=body[:20000], base=site_base())


@admin_bp.route("/seo/selfcheck")
@super_required
def seo_selfcheck():
    """服务器侧通道自检：复用既有的 4 身份探针端点。

    ⚠️ **不能直接调 `api/og.py::seo_shell_check()` 这个视图函数**——它内部用
    `urllib` 请求「本站对外地址」（`site_base()`），而那通常是公网域名：
    从服务器回打自己等于绕一圈公网 + 过 CDN，慢且依赖外网可达。

    所以这里做的是**在服务端把 4 种身份的判定逻辑跑一遍**（纯函数调用，
    零网络），把「闸门判定结果」直接给页面。至于「线上 nginx 有没有把配置
    加进去」这一层，页面另给一个按钮指向真实的 `/api/seo/shell-check`
    （由浏览器发起，走完整链路，这才是真机验证）。
    """
    from flask import jsonify
    import re as _re
    from utils.seo_shell import SEARCH_BOT_UA, _SOCIAL_PREVIEW_UA, _TOOL_BOT_UA

    base = site_base()
    cases = [
        ("Baiduspider（搜索引擎）",
         "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
         {}, "shell"),
        ("MicroMessenger（微信预览抓取）",
         "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) MicroMessenger/8.0.40",
         {}, "shell"),
        ("QQ 内置浏览器（真人）",
         "Mozilla/5.0 (Linux; U; Android 12) AppleWebKit/537.36 Chrome/100.0 Mobile"
         " Safari/537.36 MQQBrowser/13.0 QQ/9.7.10.43400",
         {"Sec-Fetch-Mode": "navigate", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
         "spa"),
        ("Chrome（真人）",
         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
         {"Sec-Fetch-Mode": "navigate", "Accept": "text/html"}, "spa"),
    ]
    out = []
    for label, ua, hdr, expect in cases:
        ual = ua.lower()
        is_tool = bool(_TOOL_BOT_UA.search(ua))
        is_search = bool(SEARCH_BOT_UA.search(ua))
        is_social = bool(_SOCIAL_PREVIEW_UA.search(ua))
        human = (hdr.get("Sec-Fetch-Mode", "").lower() == "navigate"
                 or "text/html" in hdr.get("Accept", "").lower())
        allow = (not is_tool) and (is_search or is_social) and not human
        got = "shell" if allow else "spa"
        out.append({
            "label": label, "expect": expect, "got": got,
            "ok": got == expect, "human_signal": human,
            "matched": ("search" if is_search else ("social" if is_social else
                        ("tool-bot" if is_tool else "none"))),
        })
    return jsonify(site_base=base, configured=bool(base), checks=out,
                   all_ok=all(c["ok"] for c in out) and bool(base))
