"""全站健康体检（v3.8.7）：把「诊断助手」从单一 RSS 聚合扩展为统一诊断中心。

设计：
- 每个 checker 返回统一结构：{key, title, status, items:[{label,value,level}], notes:[], per_link?}
  status ∈ ok / warn / error；level ∈ ok / warn / error / info。
- run_all() 汇总所有 checker，给出 ok/warn/error 计数与生成时间。
- 任一 checker 异常都被捕获并降级为 error，不影响其它 checker（避免一处故障拖垮整页）。
- 运行环境：admin 路由处于请求上下文内，current_app / db 均可用。

覆盖维度（任何小问题都能在此看到）：
1. 数据库健康（路径/大小/完整性 PRAGMA integrity_check/核心表行数）
2. 运行环境依赖（feedparser / Pillow / bleach / markdown / FTS5 编译选项）
3. 站点配置（站点名 / 注册 / 验证码 / 评论 / 邮件 SMTP / site_url）
4. 博客圈 RSS 聚合（复用 feed_agg 逐条诊断）
5. 数据备份（本地目录 / 保留天数 / 远端目标 / 最近备份文件）
6. 搜索引擎 SEO（site_url / robots / sitemap / feed 路由存在性）
7. 待处理事项（待审评论 / 待审友链申请 / 未读留言）
8. 前端构建产物（_vite_build* 是否存在）
9. 存储权限（数据目录可写）
"""
import importlib
import os
import glob
import time

from flask import current_app
from sqlalchemy import text

from models import (db, Post, Comment, User, FriendLink, Guestbook,
                    LinkApplication, Subscriber, Notification)
from utils import get_setting, setting_bool


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _severity(status):
    return {"error": 2, "warn": 1, "ok": 0, "info": 0}.get(status, 0)


def _mod(name):
    """返回 (是否可用, 版本或缺失原因)。"""
    try:
        m = importlib.import_module(name)
        return True, getattr(m, "__version__", "已安装")
    except Exception as e:
        return False, f"缺失（{type(e).__name__}）"


def _db_path():
    try:
        url = db.engine.url
        if getattr(url, "get_backend_name", lambda: "")() != "sqlite":
            return None
        p = url.database
        if not p:
            return None
        if os.path.isabs(p) and os.path.exists(p):
            return p
        for base in (os.getcwd(), current_app.instance_path, current_app.root_path):
            cand = p if os.path.isabs(p) else os.path.join(base, p)
            if os.path.exists(cand):
                return cand
        return p
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. 数据库健康
# ---------------------------------------------------------------------------
def check_database():
    items, notes, status = [], [], "ok"
    try:
        p = _db_path()
        if p:
            items.append({"label": "数据库文件", "value": p, "level": "info"})
            if os.path.exists(p):
                size = os.path.getsize(p)
                items.append({"label": "文件大小", "value": f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.2f} MB", "level": "info"})
            else:
                items.append({"label": "文件大小", "value": "文件不存在", "level": "error"})
                status = "error"
        else:
            items.append({"label": "数据库类型", "value": "非 SQLite（跳过文件检查）", "level": "info"})

        # 完整性校验
        rows = db.session.execute(text("PRAGMA integrity_check")).fetchall()
        ok_all = all((r[0] == "ok") for r in rows)
        if ok_all:
            items.append({"label": "完整性 PRAGMA integrity_check", "value": "ok（无损坏）", "level": "ok"})
        else:
            bad = [r[0] for r in rows if r[0] != "ok"][:5]
            items.append({"label": "完整性 PRAGMA integrity_check", "value": "发现问题：" + "；".join(bad), "level": "error"})
            notes.append("数据库可能存在损坏，建议从备份恢复或执行 PRAGMA repair。")
            status = "error"

        # 核心表行数
        counts = {
            "文章 Post": Post.query.count(),
            "评论 Comment": Comment.query.count(),
            "用户 User": User.query.count(),
            "友链 FriendLink": FriendLink.query.count(),
            "留言 Guestbook": Guestbook.query.count(),
            "订阅 Subscriber": Subscriber.query.count(),
            "通知 Notification": Notification.query.count(),
        }
        for k, v in counts.items():
            items.append({"label": k, "value": str(v), "level": "info"})
    except Exception as e:
        status = "error"
        notes.append(f"数据库检查异常：{type(e).__name__}: {e}")
    return {"key": "database", "title": "数据库健康", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 2. 运行环境依赖
# ---------------------------------------------------------------------------
def check_dependencies():
    items, notes, status = [], [], "ok"
    deps = {
        "feedparser": "博客圈 RSS 聚合必需",
        "PIL": "图形验证码（Pillow）必需",
        "bleach": "RSS 摘要 HTML 清洗必需",
        "markdown": "文章 Markdown 渲染必需",
        "sqlalchemy": "ORM 基础",
        "flask": "Web 框架基础",
    }
    for name, why in deps.items():
        ok, ver = _mod(name)
        level = "ok" if ok else "error"
        items.append({"label": name, "value": (ver if ok else f"{ver}（{why}）"), "level": level})
        if not ok:
            status = "error"
            notes.append(f"缺少依赖 {name}：{why}")

    # FTS5 编译选项（全文搜索；缺失时自动降级 LIKE，不致命）
    try:
        opts = db.session.execute(text("PRAGMA compile_options")).fetchall()
        has_fts5 = any("FTS5" in (o[0] or "") for o in opts)
        items.append({
            "label": "SQLite FTS5",
            "value": "已编译（全文搜索可用）" if has_fts5 else "未编译（搜索自动降级 LIKE，不影响功能）",
            "level": "ok" if has_fts5 else "warn",
        })
        if not has_fts5:
            notes.append("当前 SQLite 未启用 FTS5，全文搜索走 LIKE 兜底，长文搜索性能略低。")
            status = "warn" if status == "ok" else status
    except Exception as e:
        items.append({"label": "SQLite FTS5", "value": f"检测失败：{e}", "level": "warn"})
        status = "warn" if status == "ok" else status
    return {"key": "dependencies", "title": "运行环境依赖", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 3. 站点配置
# ---------------------------------------------------------------------------
def check_config():
    items, notes, status = [], [], "ok"

    site_name = get_setting("site_name") or get_setting("site_title")
    items.append({"label": "站点名称", "value": (site_name or "未设置"), "level": "ok" if site_name else "warn"})
    if not site_name:
        notes.append("未设置站点名称，前台标题会显示默认占位。后台「站点设置」补全。")
        status = "warn" if status == "ok" else status

    allow_register = setting_bool("allow_register", False)
    items.append({"label": "开放注册", "value": "开启" if allow_register else "关闭", "level": "info"})

    captcha_enabled = setting_bool("captcha_enabled", True)
    pil_ok, _ = _mod("PIL")
    if captcha_enabled and not pil_ok:
        items.append({"label": "验证码", "value": "已开启但 Pillow 缺失 → 验证码不可用", "level": "error"})
        notes.append("验证码已开启却缺少 Pillow，注册/评论/留言的验证码会失败。请 pip install Pillow。")
        status = "error"
    else:
        items.append({"label": "验证码", "value": ("开启" if captcha_enabled else "关闭") + ("" if pil_ok else "（Pillow 缺失）"), "level": "ok"})

    comments_enabled = setting_bool("comments_enabled", True)
    items.append({"label": "评论功能", "value": "开启" if comments_enabled else "关闭", "level": "info"})

    smtp = get_setting("smtp_host") or os.environ.get("SMTP_HOST")
    items.append({"label": "邮件 SMTP", "value": (smtp or "未配置"), "level": "ok" if smtp else "warn"})
    if not smtp:
        notes.append("未配置 SMTP，订阅确认邮件、通知邮件等不会发送（不影响站内功能）。")
        status = "warn" if status == "ok" else status

    site_url = get_setting("site_url") or current_app.config.get("SITE_URL")
    items.append({"label": "站点 URL (site_url)", "value": (site_url or "未设置"), "level": "ok" if site_url else "warn"})
    if not site_url:
        notes.append("未设置 site_url，sitemap/feed 中的绝对链接、分享卡片可能不完整。")
        status = "warn" if status == "ok" else status
    return {"key": "config", "title": "站点配置", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 4. 博客圈 RSS 聚合（复用 feed_agg 逐条诊断）
# ---------------------------------------------------------------------------
def check_feed_agg():
    import feed_agg
    d = feed_agg.get_last_diag()
    items, notes = [], []
    items.append({"label": "友链总数", "value": str(d.get("total_links", 0)), "level": "info"})
    items.append({"label": "已填 RSS", "value": str(d.get("links_with_rss", 0)), "level": "info"})
    items.append({"label": "feedparser", "value": "已安装" if d.get("feedparser_ok") else "未安装", "level": "ok" if d.get("feedparser_ok") else "error"})
    items.append({"label": "成功抓取", "value": str(d.get("fetched", 0)), "level": "info"})
    items.append({"label": "跳过", "value": str(d.get("skipped", 0)), "level": "ok" if not d.get("skipped") else "warn"})
    items.append({"label": "最近运行", "value": d.get("last_run") or "—", "level": "info"})

    status = "ok"
    if not d.get("feedparser_ok"):
        status = "error"
        notes.append("feedparser 未安装：pip install feedparser==6.0.11 后重启服务。")
    if not d.get("links_with_rss"):
        status = "warn"
        notes.append("没有任何友链填写 RSS 地址，博客圈永远为空。后台「友链管理」补 RSS。")
    if d.get("skipped"):
        status = "warn" if status == "ok" else status
    for rec in d.get("per_link", []) or []:
        if rec.get("status") == "empty":
            status = "warn" if status == "ok" else status
            notes.append(f"友链「{rec.get('name')}」RSS 解析到 0 条（地址：{rec.get('rss_url')}）——检查该 RSS 是否指向真实 feed。")
        elif rec.get("status") in ("error", "skipped"):
            status = "warn" if status == "ok" else status
    notes.extend(d.get("notes", []) or [])
    return {"key": "feed_agg", "title": "博客圈 RSS 聚合", "status": status,
            "rows": items, "notes": notes, "per_link": d.get("per_link", []) or []}


# ---------------------------------------------------------------------------
# 5. 数据备份
# ---------------------------------------------------------------------------
def check_backup():
    items, notes, status = [], [], "ok"
    try:
        from backup_settings import read_setting_db
        backup_dir = read_setting_db("backup_dir") or os.environ.get("BACKUP_DIR")
        retention = read_setting_db("backup_retention_days") or os.environ.get("BACKUP_RETENTION_DAYS", "14")
        items.append({"label": "本地备份目录", "value": (backup_dir or "未设置（使用默认）"), "level": "info"})
        items.append({"label": "保留天数", "value": str(retention), "level": "info"})

        # 远端目标
        remote = []
        if read_setting_db("backup_oss_bucket"):
            remote.append("OSS")
        if read_setting_db("backup_scp_host"):
            remote.append("SCP")
        if read_setting_db("backup_webdav_url"):
            remote.append("WebDAV")
        items.append({"label": "远端目标", "value": ("、".join(remote) if remote else "未配置（仅本地）"), "level": "info"})
        if not remote:
            notes.append("未配置任何远端备份目标，数据仅留本地，建议至少配一个异地/对象存储。")
            status = "warn" if status == "ok" else status

        # 最近备份文件
        search_dirs = []
        if backup_dir and os.path.isdir(backup_dir):
            search_dirs.append(backup_dir)
        else:
            cand = os.path.join(REPO_ROOT, "myblog", "data", "backups")
            if os.path.isdir(cand):
                search_dirs.append(cand)
        latest = None
        for d in search_dirs:
            for f in glob.glob(os.path.join(d, "*")):
                if os.path.isfile(f) and f.lower().endswith((".db", ".sql", ".zip", ".sqlite")):
                    m = os.path.getmtime(f)
                    if latest is None or m > latest[1]:
                        latest = (f, m)
        if latest:
            age = time.time() - latest[1]
            items.append({"label": "最近备份", "value": f"{os.path.basename(latest[0])}（{_human_age(age)}前）", "level": "ok" if age < 7*86400 else "warn"})
            if age >= 7*86400:
                notes.append("最近一次备份已超过 7 天，建议检查定时备份是否正常运行。")
                status = "warn" if status == "ok" else status
        else:
            items.append({"label": "最近备份", "value": "未找到备份文件", "level": "warn"})
            notes.append("未发现任何备份文件，请确认备份任务已执行。")
            status = "warn" if status == "ok" else status
    except Exception as e:
        status = "error"
        notes.append(f"备份检查异常：{type(e).__name__}: {e}")
    return {"key": "backup", "title": "数据备份", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 6. 搜索引擎 SEO
# ---------------------------------------------------------------------------
def check_seo():
    items, notes, status = [], [], "ok"
    site_url = get_setting("site_url") or current_app.config.get("SITE_URL")
    items.append({"label": "站点 URL", "value": (site_url or "未设置"), "level": "ok" if site_url else "warn"})
    # 路由存在性（代码内已知；这里只确认关键端点已注册）
    from flask import current_app as app
    routes = {str(r) for r in app.url_map.iter_rules()}
    for path in ("/robots.txt", "/sitemap.xml", "/feed.xml"):
        has = any(path in r for r in routes)
        items.append({"label": f"路由 {path}", "value": "存在" if has else "缺失", "level": "ok" if has else "error"})
        if not has:
            status = "error"
            notes.append(f"缺少 {path} 路由，SEO/订阅源不完整。")
    if not site_url:
        notes.append("site_url 未设置会影响 sitemap/feed 绝对链接与分享卡片。")
        status = "warn" if status == "ok" else status
    return {"key": "seo", "title": "搜索引擎 SEO", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 7. 待处理事项
# ---------------------------------------------------------------------------
def check_pending():
    items, notes, status = [], [], "ok"
    pc = Comment.query.filter_by(approved=False).count()
    pl = LinkApplication.query.filter_by(status="pending").count()
    pg = Guestbook.query.filter_by(is_read=False).count()
    items.append({"label": "待审核评论", "value": str(pc), "level": "ok" if pc == 0 else "warn"})
    items.append({"label": "待审友链申请", "value": str(pl), "level": "ok" if pl == 0 else "warn"})
    items.append({"label": "未读留言", "value": str(pg), "level": "ok" if pg == 0 else "info"})
    if pc:
        notes.append(f"有 {pc} 条评论待审核，去后台「评论管理」处理。")
        status = "warn"
    if pl:
        notes.append(f"有 {pl} 条友链申请待处理，去后台「友链申请」处理。")
        status = "warn"
    return {"key": "pending", "title": "待处理事项", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 8. 前端构建产物
# ---------------------------------------------------------------------------
def check_frontend_build():
    items, notes, status = [], [], "ok"
    fe_dir = os.path.join(REPO_ROOT, "vue-frontend")
    builds = sorted(glob.glob(os.path.join(fe_dir, "_vite_build*")))
    if builds:
        idx = os.path.join(builds[-1], "index.html")
        ok = os.path.exists(idx)
        items.append({"label": "构建目录", "value": os.path.basename(builds[-1]) + ("（含 index.html）" if ok else "（缺失 index.html）"), "level": "ok" if ok else "warn"})
        if not ok:
            status = "warn"
            notes.append("构建目录存在但缺少 index.html，重新 vite build。")
    else:
        items.append({"label": "构建目录", "value": "未找到 _vite_build*", "level": "warn"})
        notes.append("前端未构建（vue-frontend 下没有 _vite_build*）。部署前需 npm run build / vite build。")
        status = "warn"
    return {"key": "frontend", "title": "前端构建产物", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 9. 存储权限
# ---------------------------------------------------------------------------
def check_storage():
    items, notes, status = [], [], "ok"
    p = _db_path()
    data_dir = os.path.dirname(p) if p else os.path.join(REPO_ROOT, "myblog", "data")
    writable = os.access(data_dir, os.W_OK)
    items.append({"label": "数据目录", "value": data_dir, "level": "info"})
    items.append({"label": "可写权限", "value": "可写" if writable else "不可写", "level": "ok" if writable else "error"})
    if not writable:
        notes.append("数据目录不可写：服务可能无法写入数据库/上传文件。检查目录权限与挂载。")
        status = "error"
    return {"key": "storage", "title": "存储权限", "status": status, "items": items, "notes": notes}


def _human_age(sec):
    if sec < 3600:
        return f"{int(sec/60)} 分钟"
    if sec < 86400:
        return f"{int(sec/3600)} 小时"
    return f"{int(sec/86400)} 天"


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
CHECKS = [
    check_database,
    check_dependencies,
    check_config,
    check_feed_agg,
    check_backup,
    check_seo,
    check_pending,
    check_frontend_build,
    check_storage,
]


def run_all():
    """运行全部 checker，返回 {generated_at, summary:{ok,warn,error}, sections:[...]}。"""
    sections = []
    summary = {"ok": 0, "warn": 0, "error": 0}
    for fn in CHECKS:
        try:
            sec = fn()
        except Exception as e:
            sec = {"key": fn.__name__, "title": fn.__name__, "status": "error",
                   "rows": [], "notes": [f"checker 异常：{type(e).__name__}: {e}"]}
        sections.append(sec)
        summary[sec.get("status", "ok")] = summary.get(sec.get("status", "ok"), 0) + 1
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "summary": summary,
        "sections": sections,
    }
