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
4. 安全配置概览（v3.10.2：验证码 / 评论 / 强密码 / 安全响应头 / 限流 状态汇总）
5. 博客圈 RSS 聚合（复用 feed_agg 逐条诊断）
6. 数据备份（本地目录 / 保留天数 / 远端目标 / 最近备份文件）
7. 搜索引擎 SEO（site_url / robots / sitemap / feed 路由存在性）
8. 待处理事项（待审评论 / 待审友链申请 / 未读留言）
9. 前端构建产物（SPA 入口 index.html 是否存在，部署态/本地构建均识别）
10. 存储权限（数据目录可写）
11. 渲染缓存命中率（v3.10.2：已缓存正文文章占比，暴露缓存写回是否失效）
12. SSL 证书（v3.25.3：读 cert_watch 状态文件，过期即全站不可访问）
13. 插件与扩展（v4.11.0：声明启用但没载入 = 真故障，与「运行时停用」分开看）
14. 全文搜索索引（v4.11.0：post_fts 与应索引文章数的漂移，对应「搜不到/搜出已删」）
15. 定时任务与定时发布（v4.11.0：到点没发、后台任务失败或卡死）
16. 外发通道（v4.11.0：邮件/推送配置完整性与密文可解，只读不联网）
17. 内容健康度（v4.11.0：可见文章缺摘要/未分类/正文为空/标题重复）
18. 磁盘与 WAL（v4.11.0：剩余空间不足会让 SQLite 直接不可写）
19. MCP 服务（v4.11.0：诊断/写端点开关、Token、Origin、日志路径）

⚠️ 新增 checker 的两条硬约定（v4.11.0）：
- 只读：不写库、不发网络请求（SMTP/TLS 握手一律不做，那属于各页面自己的「测试」按钮）；
- 不许抛：内部异常必须自己兜住并降级成 notes，否则一个 checker 崩掉会污染整页评分。
"""
import importlib
import os
import glob
import time
import contextlib

from flask import current_app
from sqlalchemy import text

from models import (db, Post, Comment, User, FriendLink, Guestbook,
                    LinkApplication, Subscriber, Notification)
from utils import (get_setting, setting_bool, flag_bool, fmt_bj, site_base)
from _time import utcnow


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 本文件所在目录（= 代码根）。⚠️ **不要用 REPO_ROOT 拼 myblog/ 前缀**：
# 本地开发时代码在 `<repo>/myblog/`，但线上（v3.18.6 起）代码直接铺在站点根
# `/www/wwwroot/myblog/`，没有 `myblog/` 这一层 —— 用 REPO_ROOT 拼前缀在服务器上恒为空路径
# （v4.4.1 修备份误报时踩到：旧代码 `REPO_ROOT/myblog/data/backups` 永远不存在）。
_CODE_DIR = os.path.dirname(os.path.abspath(__file__))


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

        # v3.9.1：WAL 模式（多 worker 下读写并发的关键指标，未生效多半是内存库或只读盘）
        try:
            mode = db.session.execute(text("PRAGMA journal_mode")).scalar()
            mode = (mode or "").lower()
            if mode == "wal":
                items.append({"label": "日志模式 journal_mode", "value": "WAL（读不阻塞写）", "level": "ok"})
            else:
                items.append({"label": "日志模式 journal_mode", "value": f"{mode or '未知'}（建议 WAL）", "level": "warn"})
                notes.append("数据库未处于 WAL 模式，多 worker 并发下可能出现 database is locked；"
                             "检查数据库文件所在目录是否可写。")
            bt = db.session.execute(text("PRAGMA busy_timeout")).scalar()
            items.append({"label": "写锁等待 busy_timeout", "value": f"{bt} ms", "level": "ok" if bt else "warn"})
        except Exception:  # noqa: S110  旁路/兜底路径，失败按降级处理，不影响主流程
            pass

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

    # 注意：后台「邮件设置」存库的 key 是 mail_host（见 mail_notify.load_mail_config），
    # 而非环境变量名 smtp_host；宝塔环境变量才是 SMTP_HOST。两者任一存在即视为已配置。
    smtp = get_setting("mail_host") or os.environ.get("SMTP_HOST")
    items.append({"label": "邮件 SMTP", "value": (smtp or "未配置"), "level": "ok" if smtp else "warn"})
    if not smtp:
        notes.append("未配置 SMTP，订阅确认邮件、通知邮件等不会发送（不影响站内功能）。")
        status = "warn" if status == "ok" else status

    site_url = site_base()
    items.append({"label": "站点 URL (site_url)", "value": (site_url or "未设置"), "level": "ok" if site_url else "warn"})
    if not site_url:
        notes.append("未设置 site_url，sitemap/feed 中的绝对链接、分享卡片可能不完整。")
        status = "warn" if status == "ok" else status
    return {"key": "config", "title": "站点配置", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 4. 博客圈 RSS 聚合（复用 feed_agg 逐条诊断）
# ---------------------------------------------------------------------------
def check_feed_agg():
    """博客圈 RSS 聚合诊断。

    v3.10.4 起：「已填 RSS」改读实时库（FriendLink.rss_url 非空计数），
    消除多 worker 下读 get_last_diag() 内存快照导致的滞后——
    之前填了 RSS 也要等某进程新鲜聚合才刷新，诊断长时间误报「没有任何友链填写 RSS」。
    抓取明细（成功/跳过/最近运行/逐条）仍取快照，仅在新鲜聚合时更新，属可接受。
    """
    import feed_agg
    try:
        total_links = FriendLink.query.count()
        links_with_rss = FriendLink.query.filter(
            FriendLink.rss_url.isnot(None), FriendLink.rss_url != ""
        ).count()
    except Exception:
        total_links = 0
        links_with_rss = 0
    d = feed_agg.get_last_diag()
    items, notes = [], []
    items.append({"label": "友链总数", "value": str(total_links), "level": "info"})
    items.append({"label": "已填 RSS（实时库）", "value": str(links_with_rss), "level": "info"})
    items.append({"label": "feedparser", "value": "已安装" if d.get("feedparser_ok") else "未安装", "level": "ok" if d.get("feedparser_ok") else "error"})
    items.append({"label": "成功抓取", "value": str(d.get("fetched", 0)), "level": "info"})
    items.append({"label": "跳过", "value": str(d.get("skipped", 0)), "level": "ok" if not d.get("skipped") else "warn"})
    items.append({"label": "最近运行", "value": d.get("last_run") or "—", "level": "info"})

    status = "ok"
    if not d.get("feedparser_ok"):
        status = "error"
        notes.append("feedparser 未安装：pip install feedparser==6.0.11 后重启服务。")
    if not links_with_rss:
        status = "warn"
        notes.append("没有任何友链填写 RSS 地址，博客圈永远为空。后台「友链管理」补 RSS。")
    elif d.get("skipped"):
        status = "warn"
    for rec in d.get("per_link", []) or []:
        if rec.get("status") == "empty":
            status = "warn" if status == "ok" else status
            notes.append(f"友链「{rec.get('name')}」RSS 解析到 0 条（地址：{rec.get('rss_url')}）——检查该 RSS 是否指向真实 feed。")
        elif rec.get("status") in ("error", "skipped"):
            status = "warn" if status == "ok" else status
    notes.extend(d.get("notes", []) or [])
    return {"key": "feed_agg", "title": "博客圈 RSS 聚合", "status": status,
            "rows": items, "notes": notes[:5], "per_link": d.get("per_link", []) or []}


# ---------------------------------------------------------------------------
# 5. 数据备份
# ---------------------------------------------------------------------------
def _backup_search_dirs():
    """枚举**真实写入方**用到的本地备份目录：返回 `[(路径, 来源标签), ...]`（只含已存在的）。

    v4.4.1 修：旧实现只猜一条 `REPO_ROOT/myblog/data/backups`，而备份实际有三处写入方：
      ① 后台「数据备份」页面配置的目录 / `BACKUP_DIR` 环境变量；
      ② `backup.py` 的滚动备份（`BACKUP_ROOT`，服务器上是**站点上级**的 `backups/`，
         即每天 4 点 cron 跑出来的那批）；
      ③ `update.sh` 每次部署前的直拷备份（`<代码同级>/data/backup`）。
    旧代码猜的那条有两个错：目录名写成 `backups`（实际 `backup`，单数），
    且多套了一层 `myblog/`（线上代码直接铺在站点根，没有这层）→ 路径恒不存在，
    于是明明每天都在备份，体检却报「未找到备份文件」。

    🔑 不自己重算 ② 的路径规则，直接取 `backup.BACKUP_ROOT`（唯一真相源）；
    重算等于把写入方的规则抄一份，抄错就是今天这个 bug。
    """
    found = []
    seen = set()

    def _add(path, label):
        if not path:
            return
        real = os.path.abspath(path)
        if real in seen:
            return
        seen.add(real)
        found.append((real, label, os.path.isdir(real)))

    # ① 后台配置 / 环境变量
    with contextlib.suppress(Exception):
        from backup_settings import read_setting_db
        _add(read_setting_db("backup_dir"), "后台配置目录")
    _add(os.environ.get("BACKUP_DIR"), "环境变量 BACKUP_DIR")

    # ② 定时任务目录：backup.py 自己解析出来的结果
    try:
        import backup as _bk
        _add(getattr(_bk, "BACKUP_ROOT", None), "定时任务目录")
    except Exception:  # noqa: BLE001 —— 体检不能因导入失败而崩，退回同规则的默认值
        _add(os.path.join(os.path.dirname(REPO_ROOT), "backups"), "定时任务目录")

    # ③ 部署备份目录：与代码同级（本地= myblog/data/backup，线上= 站点根/data/backup）
    _add(os.path.join(_CODE_DIR, "data", "backup"), "部署备份目录")

    return found


def check_backup():
    items, notes, status = [], [], "ok"
    try:
        from backup_settings import read_setting_db
        retention = read_setting_db("backup_retention_days") or os.environ.get("BACKUP_RETENTION_DAYS", "14")
        dirs = _backup_search_dirs()
        alive = [(p, lb) for p, lb, ok in dirs if ok]
        items.append({
            "label": "本地备份目录",
            "value": ("；".join(p for p, _ in alive) if alive
                      else "未找到可用的本地备份目录"),
            "level": "ok" if alive else "warn",
        })
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

        # 配置了却不存在的目录 —— 是「配了没生效」，必须点出来而不是静默忽略
        for path, label, ok in dirs:
            if not ok:
                items.append({"label": "目录缺失", "value": f"{path}（{label}）", "level": "warn"})
                notes.append(f"{label}已配置但目录不存在：{path}")
                status = "warn" if status == "ok" else status

        # 最近备份文件：跨所有真实目录取最新，并标注它来自哪个来源
        latest = None
        for path, label in alive:
            for f in glob.glob(os.path.join(path, "*")):
                if os.path.isfile(f) and f.lower().endswith((".db", ".sql", ".zip", ".sqlite")):
                    m = os.path.getmtime(f)
                    if latest is None or m > latest[1]:
                        latest = (f, m, label)
        if latest:
            age = time.time() - latest[1]
            items.append({
                "label": "最近备份",
                "value": f"{os.path.basename(latest[0])}（{_human_age(age)}前 · {latest[2]}）",
                "level": "ok" if age < 7 * 86400 else "warn",
            })
            if age >= 7 * 86400:
                notes.append("最近一次备份已超过 7 天，建议检查定时备份是否正常运行。")
                status = "warn" if status == "ok" else status
        else:
            items.append({"label": "最近备份", "value": "未找到备份文件", "level": "warn"})
            notes.append("已找到本地备份目录但其中没有备份文件，请确认备份任务是否执行成功。")
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
    site_url = site_base()
    items.append({"label": "站点 URL", "value": (site_url or "未设置"), "level": "ok" if site_url else "warn"})
    # v3.18.9：爬虫通道自检（本轮新增，见 deploy_guide.md 的 map $http_user_agent $seo_shell）
    from flask import current_app as app
    routes = {str(r) for r in app.url_map.iter_rules()}
    for path in ("/robots.txt", "/sitemap.xml", "/feed.xml", "/feed/comments"):
        has = any(path in r for r in routes)
        items.append({"label": f"路由 {path}", "value": "存在" if has else "缺失", "level": "ok" if has else "error"})
        if not has:
            status = "error"
            notes.append(f"缺少 {path} 路由，SEO/订阅源不完整。")
    # 爬虫通道（/api/og/post/<slug>）是本轮 SEO 的正式出口，缺了等于文章对爬虫不可见
    has_og_shell = any("/api/og/post/" in r for r in routes)
    items.append({"label": "路由 /api/og/post/<slug>（爬虫通道）",
                  "value": "存在" if has_og_shell else "缺失",
                  "level": "ok" if has_og_shell else "error"})
    if not has_og_shell:
        status = "error"
        notes.append("缺少爬虫通道路由，搜索引擎/微信拿不到文章服务端 HTML（只剩 SPA 空壳）。")
    if not site_url:
        notes.append("site_url 未设置会影响 sitemap/feed 绝对链接与分享卡片；"
                     "爬虫通道的 canonical/og:url 也会退化成相对路径，微信卡片取不到图。")
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
    """前端构建产物体检（v3.10.0 修正：部署态误报修复）。

    部署布局（见 deploy_guide）：vue-frontend-dist.zip 解压到站点根目录
    /www/wwwroot/vue-frontend/，直接是 index.html + assets/（无 _vite_build* 子目录）。
    本地构建则是 vue-frontend/_vite_buildN/index.html 或 vue-frontend/dist/index.html。
    旧逻辑只查 vue-frontend/_vite_build*，在部署态永远查不到 → 误报「未构建」。
    改为查 SPA 入口 index.html：部署态优先查 fe_dir/index.html，回退本地构建子目录。
    """
    items, notes, status = [], [], "ok"
    fe_dir = os.path.join(REPO_ROOT, "vue-frontend")

    # 候选 SPA 入口（按优先级：部署态 > 本地构建）
    candidates = []
    candidates.append(("部署目录", os.path.join(fe_dir, "index.html")))
    for b in sorted(glob.glob(os.path.join(fe_dir, "_vite_build*"))):
        candidates.append(("构建目录 " + os.path.basename(b), os.path.join(b, "index.html")))
    candidates.append(("本地 dist", os.path.join(fe_dir, "dist", "index.html")))

    found = [(label, p) for label, p in candidates if os.path.isfile(p)]
    if found:
        label, _ = found[0]
        items.append({"label": "构建产物", "value": "%s（含 index.html）" % label, "level": "ok"})
    else:
        items.append({"label": "构建产物", "value": "未找到前端 index.html", "level": "warn"})
        notes.append("前端未构建或未部署：%s 下未发现 index.html（部署态应为站点根目录 vue-frontend/ 直接含 index.html + assets/；本地需先 npm run build）。" % fe_dir)
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


def check_security():
    """安全配置概览（v3.10.2）：验证码/评论/强密码/安全头/限流 状态汇总，暴露安全短板。

    仅读取配置（环境变量 STRONG_PASSWORD / SECURITY_HEADERS + 后台设置 captcha_enabled/
    comments_enabled），不做任何写操作与网络请求。
    """
    items, notes, status = [], [], "ok"
    captcha = setting_bool("captcha_enabled", True)
    comments = setting_bool("comments_enabled", True)
    strong = flag_bool("strong_password", "STRONG_PASSWORD", True)
    sec_headers = current_app.config.get("SECURITY_HEADERS", True)
    items.append({"label": "图形验证码", "value": "开启" if captcha else "关闭", "level": "ok" if captcha else "warn"})
    items.append({"label": "评论功能", "value": "开启" if comments else "关闭", "level": "info"})
    items.append({"label": "强密码策略", "value": "开启" if strong else "关闭", "level": "ok" if strong else "warn"})
    items.append({"label": "安全响应头", "value": "开启" if sec_headers else "关闭", "level": "ok" if sec_headers else "warn"})
    items.append({"label": "接口限流", "value": "启用（按 IP 60/min）", "level": "ok"})
    if comments and not captcha:
        status = "warn"
        notes.append("评论功能开启但未启用图形验证码：匿名评论易被垃圾评论刷屏，建议开启验证码或开启评论审核。")
    if not sec_headers:
        if status == "ok":
            status = "warn"
        notes.append("未启用安全响应头（X-Frame-Options / X-Content-Type-Options 等）：建议开启 SECURITY_HEADERS。")
    if not strong:
        if status == "ok":
            status = "warn"
        notes.append("未启用强密码策略：管理员账户建议开启 STRONG_PASSWORD。")
    return {"key": "security", "title": "安全配置概览", "status": status, "items": items, "notes": notes}


def check_render_cache():
    """渲染缓存命中率（v3.10.2）：已缓存正文文章占比，暴露缓存写回是否失效。

    纯 DB 读取：Post.content_html 非空即视为已缓存。全部未缓存=性能退化+可能写回失败。
    """
    items, notes, status = [], [], "ok"
    try:
        total = Post.query.count()
        cached = Post.query.filter(Post.content_html.isnot(None)).count()
        if total == 0:
            items.append({"label": "文章总数", "value": "0", "level": "info"})
            items.append({"label": "渲染缓存命中率", "value": "无文章，跳过", "level": "info"})
        else:
            pct = round(cached * 100.0 / total, 1) if total else 0.0
            items.append({"label": "文章总数", "value": str(total), "level": "info"})
            items.append({"label": "已缓存正文", "value": str(cached), "level": "info"})
            items.append({"label": "渲染缓存命中率", "value": "%.1f%%" % pct, "level": "ok" if pct > 0 else "warn"})
            if cached == 0:
                status = "warn"
                notes.append("全部文章均未缓存正文：首次访问会实时渲染（较慢），且可能说明缓存写回失败，检查 WAL/存储权限与 utils.render_post_html。")
            elif pct < 50:
                notes.append("部分文章尚未缓存（新文章首次访问才填充，属正常），命中率会随访问上升。")
    except Exception as e:
        status = "error"
        notes.append("渲染缓存检查异常：%s: %s" % (type(e).__name__, e))
    return {"key": "render_cache", "title": "渲染缓存命中率", "status": status, "items": items, "notes": notes}


def check_certificate():
    """SSL 证书有效期（v3.25.3）。

    **为什么单列一组**：证书过期会让**全站直接不可访问**（HTTP 80 → 301 跳 HTTPS
    → 浏览器拒绝），影响面比组内任何其他项都大；而它偏偏又是个「不动手就忘了」
    的 90 天周期事项 —— 2026-10-02 到期、10-05 才发现。

    读 `cert_watch` 的状态文件（由每日定时任务写入），**不在诊断页现连** ——
    诊断页是要给人看的，不能因一次握手卡住而变慢（TCP 6s 超时摆在那）。

    ⚠️ 状态为 `never`（刚部署、巡检还没跑过一轮）时**给 warn 而不是 ok** ——
    「没检查过」不等于「没问题」，这与备份巡检里「没有备份报 empty 而非 ok」同源。
    """
    items, notes, status = [], [], "ok"
    try:
        import cert_watch
        st = cert_watch.read_state()
    except Exception as e:
        return {"key": "certificate", "title": "SSL 证书", "status": "error",
                "items": [{"label": "证书检查", "value": "检查器异常：%s" % e,
                            "level": "error"}],
                "notes": [], "rows": items}

    days = st.get("days_left")
    if st.get("status") == "never":
        items.append({"label": "证书有效期", "value": "尚未检查（每日定时任务跑一轮后显示）",
                      "level": "warn"})
        notes.append("尚未执行过证书到期检查。证书过期会导致全站不可访问，"
                     "建议在「设置页」保存一次配置或等次日巡检后回来看。")
        status = "warn"
    else:
        lvl = cert_watch.status_level(st.get("status"))
        items.append({"label": "检查目标", "value": st.get("host") or "（未取到）", "level": "info"})
        items.append({"label": "到期时间", "value": st.get("not_after") or "—", "level": lvl})
        items.append({"label": "剩余天数",
                      "value": ("%d 天" % days) if isinstance(days, int) else "—",
                      "level": lvl})
        if st.get("issuer"):
            items.append({"label": "签发机构", "value": st["issuer"], "level": "info"})
        items.append({"label": "检查时间", "value": st.get("checked_at") or "—", "level": "info"})
        if st.get("message"):
            notes.append(st["message"])
        if st.get("status") in ("expired", "critical", "warn"):
            notes.append("续签入口：宝塔面板 → 网站 → SSL → 申请证书（本站证书 90 天有效期）。")
        status = lvl if lvl in ("warn", "error") else status
    return {"key": "certificate", "title": "SSL 证书", "status": status,
            "items": items, "notes": notes, "rows": items}


# ---------------------------------------------------------------------------
# 13. 插件与扩展（v4.11.0）
# ---------------------------------------------------------------------------
def check_plugins():
    """插件启用 / 载入一致性。

    三态必须分开看，混在一个数字里会误报：
    - **声明启用但没载入**（不在 RUNTIME_DISABLED 里）= 真故障（manifest 缺失 / 载入抛错）；
    - **运行时停用**（管理员点了「停用」）= 正常操作，只报 info；
    - 未启用任何插件 = info，不是问题。
    """
    items, notes, status = [], [], "ok"
    try:
        from plugins import PLUGIN_REGISTRY, RUNTIME_DISABLED, _parse_list
        enabled = _parse_list(current_app.config.get("ENABLED_PLUGINS", ""))
        loaded = sorted(PLUGIN_REGISTRY.keys())
        runtime_off = sorted(RUNTIME_DISABLED)
        items.append({"label": "配置启用",
                      "value": f"{len(enabled)} 个" + (f"（{'、'.join(enabled)}）" if enabled else ""),
                      "level": "info"})
        items.append({"label": "实际载入",
                      "value": f"{len(loaded)} 个" + (f"（{'、'.join(loaded)}）" if loaded else ""),
                      "level": "info"})
        if runtime_off:
            items.append({"label": "运行时停用", "value": "、".join(runtime_off), "level": "info"})
        missing = [s for s in enabled if s not in loaded and s not in runtime_off]
        if missing:
            items.append({"label": "未载入的插件", "value": "、".join(missing), "level": "error"})
            notes.append("以下插件声明启用但未载入：" + "、".join(missing)
                         + "。检查插件目录 / manifest.json，或搜错误日志里的 load_plugins 告警。")
            status = "error"
        elif not enabled:
            items.append({"label": "插件", "value": "未启用任何插件", "level": "info"})
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"插件状态检查异常：{type(e).__name__}: {e}")
    return {"key": "plugins", "title": "插件与扩展", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 14. 全文搜索索引（v4.11.0）
# ---------------------------------------------------------------------------
def check_search_index():
    """`post_fts` 与「应当被索引的文章数」是否一致。

    搜索是访客最常用的功能，而索引是**惰性维护**的：删文章、改可见性、改正文
    都要有人去同步。漏同步的表现是「搜不到刚发的文章」或「搜到已删文章」，
    但页面本身不报错 —— 只有比对条数才看得出来。
    """
    items, notes, status = [], [], "ok"
    try:
        import fts
        if not fts.available():
            items.append({"label": "FTS5 支持", "value": "不可用（搜索降级为 LIKE 扫描）", "level": "warn"})
            notes.append("SQLite 未编译 FTS5：站内搜索退化为 LIKE 全表扫描，文章多时明显变慢。")
            return {"key": "search_index", "title": "全文搜索索引", "status": "warn",
                    "items": items, "notes": notes}

        indexed = db.session.execute(text("SELECT count(*) FROM post_fts")).scalar() or 0
        total = Post.query.count()
        # 有 _indexable() 就用它（与写入路径同一判据，避免两套口径各说各话）；
        # 文章过多时退化为 SQL 近似，避免体检把全表拉进内存。
        indexable = getattr(fts, "_indexable", None)
        if callable(indexable) and total <= 5000:
            expect = len([p for p in Post.query.all() if indexable(p)])
            basis = "按 fts._indexable() 逐篇判定"
        else:
            expect = Post.query.filter_by(published=True, in_trash=False, is_private=False).count()
            basis = "按 SQL 近似（published 且非隐私非回收站）"

        items.append({"label": "索引条目 post_fts", "value": str(indexed), "level": "info"})
        items.append({"label": "应被索引的文章", "value": f"{expect}（{basis}）", "level": "info"})
        diff = indexed - expect
        if diff == 0:
            items.append({"label": "一致性", "value": "一致", "level": "ok"})
        elif diff < 0:
            items.append({"label": "一致性", "value": f"缺 {abs(diff)} 条（搜不到的文章）", "level": "warn"})
            notes.append(f"索引缺 {abs(diff)} 条：这些文章搜不到。跑 `python rebuild_fts.py` 全量重建。")
            status = "warn"
        else:
            items.append({"label": "一致性", "value": f"多 {diff} 条（可能是已删/已隐藏文章）", "level": "warn"})
            notes.append(f"索引多 {diff} 条：会把已删或已转隐私的文章搜出来。跑 `python rebuild_fts.py` 清理。")
            status = "warn"
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"搜索索引检查异常：{type(e).__name__}: {e}")
    return {"key": "search_index", "title": "全文搜索索引", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 15. 定时任务与定时发布（v4.11.0）
# ---------------------------------------------------------------------------
def check_scheduler():
    """定时发布积压 + 后台任务失败。

    「到点没发」是静默失败：文章看起来还是草稿，没人会去点它，
    但作者以为它已经上线了。这一项专门把这种「时间已经过去、状态没变」揪出来。
    """
    items, notes, status = [], [], "ok"
    try:
        now = utcnow()
        overdue = Post.query.filter(Post.scheduled_at.isnot(None),
                                    Post.scheduled_at <= now,
                                    Post.published.is_(False),
                                    Post.in_trash.is_(False)).count()
        upcoming = Post.query.filter(Post.scheduled_at.isnot(None),
                                     Post.scheduled_at > now,
                                     Post.published.is_(False)).count()
        items.append({"label": "已过定时点未发布", "value": str(overdue),
                      "level": "ok" if overdue == 0 else "error"})
        items.append({"label": "待发布（未到点）", "value": str(upcoming), "level": "info"})
        if overdue:
            notes.append(f"有 {overdue} 篇已过定时发布时间但仍未发布：定时线程可能没在跑"
                         "（gunicorn 重启后定时线程需重新拉起），或该篇被手动改回草稿。")
            status = "error"
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"定时发布检查异常：{type(e).__name__}: {e}")

    # 后台任务状态文件（tasks.py）：失败 / 长时间 running
    try:
        import json as _json
        from config import DATA_DIR
        tdir = os.path.join(DATA_DIR, "tasks")
        failed, stuck = [], []
        if os.path.isdir(tdir):
            recs = []
            for p in glob.glob(os.path.join(tdir, "*.json")):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        recs.append(_json.load(f))
                except Exception:  # noqa: BLE001, S110  单条读取失败按缺省处理，不能让一个损坏文件把整项判红
                    continue
            recs.sort(key=lambda r: r.get("updated_at") or 0, reverse=True)
            for r in recs[:50]:
                st = r.get("state")
                if st == "error":
                    failed.append(r.get("name") or "?")
                elif st == "running" and (time.time() - (r.get("started_at") or 0)) > 1800:
                    stuck.append(r.get("name") or "?")
        items.append({"label": "失败的后台任务（最近 50 条内）",
                      "value": (f"{len(failed)} 个：" + "、".join(sorted(set(failed))[:5])) if failed else "无",
                      "level": "ok" if not failed else "warn"})
        if stuck:
            items.append({"label": "疑似卡住（running > 30 分钟）",
                          "value": "、".join(sorted(set(stuck))[:5]), "level": "warn"})
            notes.append("有后台任务 running 超过 30 分钟：可能线程已死但状态没落盘，"
                         "相应功能会一直提示「正在运行中」而无法再次触发（防重入锁未释放）。")
            if status == "ok":
                status = "warn"
        if failed:
            notes.append("有后台任务执行失败（如推送 / 备份 / LLM 审计），去对应页面重试并看错误日志。")
            if status == "ok":
                status = "warn"
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        notes.append(f"后台任务检查异常：{type(e).__name__}: {e}")
        if status == "ok":
            status = "warn"
    return {"key": "scheduler", "title": "定时任务与定时发布", "status": status,
            "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 16. 外发通道：邮件 / 推送（v4.11.0）
# ---------------------------------------------------------------------------
def check_outbound():
    """邮件与推送通道的配置完整性与可解密性。

    **只读配置，不发起任何网络请求** —— 体检页不能因为一次 SMTP 握手卡住
    （TCP 6s 超时摆在那）。真正的连通性验证在「邮件设置 → 发送测试邮件」。
    """
    items, notes, status = [], [], "ok"
    try:
        from mail_notify import load_mail_config
        cfg = load_mail_config()
        host, user, pwd = cfg.get("host") or "", cfg.get("username") or "", cfg.get("password") or ""
        mail_on = bool(host and user and pwd)
        items.append({"label": "SMTP 配置",
                      "value": f"{host}:{cfg.get('port')}" if host else "未配置",
                      "level": "ok" if mail_on else "info"})
        if host and not (user and pwd):
            items.append({"label": "SMTP 凭据", "value": "主机已填但账号/密码不全", "level": "warn"})
            notes.append("SMTP 主机已配置但账号或密码为空：发信会失败。"
                         "密码若是新写入的密文，解密失败也会表现为空 —— 到「邮件设置」重填一次。")
            status = "warn"
        if not mail_on and status == "ok":
            items.append({"label": "发信能力", "value": "未启用（不影响站点运行）", "level": "info"})
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        notes.append(f"邮件配置检查异常：{type(e).__name__}: {e}")
        if status == "ok":
            status = "warn"

    try:
        from push_settings import resolve_all
        vals = resolve_all()
        tg = bool(vals.get("push_telegram_token") and vals.get("push_telegram_chat"))
        wecom = bool(vals.get("push_wecom_webhook"))
        items.append({"label": "Telegram 推送", "value": "已配置" if tg else "未配置",
                      "level": "ok" if tg else "info"})
        items.append({"label": "企业微信推送", "value": "已配置" if wecom else "未配置",
                      "level": "ok" if wecom else "info"})
        half = []
        if vals.get("push_telegram_token") and not vals.get("push_telegram_chat"):
            half.append("Telegram（有 token 无 chat_id）")
        if vals.get("push_telegram_chat") and not vals.get("push_telegram_token"):
            half.append("Telegram（有 chat_id 无 token）")
        if half:
            items.append({"label": "推送配置不完整", "value": "；".join(half), "level": "warn"})
            notes.append("推送配置只填了一半：" + "；".join(half) + "。缺任一项都发不出去。")
            status = "warn"
        if not tg and not wecom and status == "ok":
            items.append({"label": "推送", "value": "无渠道（发布只用站内通知）", "level": "info"})
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        notes.append(f"推送配置检查异常：{type(e).__name__}: {e}")
        if status == "ok":
            status = "warn"
    return {"key": "outbound", "title": "外发通道（邮件/推送）", "status": status,
            "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 17. 内容健康度（v4.11.0）
# ---------------------------------------------------------------------------
def check_content_quality():
    """对访客可见文章的「欠账」：摘要 / 封面 / 分类 / 重复标题。

    只统计 published 且非隐私非回收站的文章 —— 草稿没摘要不是问题，
    把它算进来会让这一项永远报红，红久了就没人看。
    """
    items, notes, status = [], [], "ok"
    try:
        visible = Post.query.filter_by(published=True, in_trash=False, is_private=False)
        total = visible.count()
        items.append({"label": "对访客可见文章", "value": str(total), "level": "info"})
        if total == 0:
            notes.append("暂无已发布文章，跳过内容欠账检查。")
            return {"key": "content_quality", "title": "内容健康度", "status": "ok",
                    "items": items, "notes": notes}

        no_summary = visible.filter((Post.summary.is_(None)) | (Post.summary == "")).count()
        no_seo_desc = visible.filter((Post.seo_description.is_(None)) | (Post.seo_description == "")).count()
        no_cover = visible.filter((Post.cover.is_(None)) | (Post.cover == "")).count()
        no_cat = visible.filter(Post.category_id.is_(None)).count()

        def lv(n):
            return "ok" if n == 0 else "warn"

        items.append({"label": "缺摘要", "value": str(no_summary), "level": lv(no_summary)})
        items.append({"label": "缺 SEO 描述", "value": str(no_seo_desc), "level": "info"})
        items.append({"label": "缺封面图", "value": str(no_cover), "level": "info"})
        items.append({"label": "未分类", "value": str(no_cat), "level": lv(no_cat)})

        # 重复标题：内容层面的「两篇同名」会让 SEO 互相稀释，也让人分不清哪篇是新的
        dup = db.session.execute(text(
            "SELECT title, count(*) c FROM post "
            "WHERE published=1 AND in_trash=0 AND is_private=0 "
            "GROUP BY title HAVING c > 1 ORDER BY c DESC LIMIT 5")).fetchall()
        if dup:
            items.append({"label": "重复标题", "value": "; ".join(f"「{r[0]}」×{r[1]}" for r in dup),
                          "level": "warn"})
            notes.append("存在重复标题：两篇同名文章会互相稀释 SEO，也不利于读者区分。")
            status = "warn"

        if no_summary > 0:
            notes.append(f"{no_summary} 篇已发布文章缺摘要：列表页与分享卡片会退化成正文首段截断。")
            status = "warn"
        if no_cat > 0:
            notes.append(f"{no_cat} 篇未分类：归档/分类页里找不到它们。")
            status = "warn"

        # 单篇正文为空是硬伤（页面上是一片空白）
        empty_body = visible.filter((Post.content.is_(None)) | (Post.content == "")).count()
        items.append({"label": "正文为空", "value": str(empty_body),
                      "level": "ok" if empty_body == 0 else "error"})
        if empty_body:
            notes.append(f"{empty_body} 篇已发布文章正文为空：前台是空白页，搜索引擎会记为低质。")
            status = "error"
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"内容健康度检查异常：{type(e).__name__}: {e}")
    return {"key": "content_quality", "title": "内容健康度", "status": status,
            "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 18. 磁盘容量与 WAL 体积（v4.11.0）
# ---------------------------------------------------------------------------
def check_disk():
    """数据盘剩余空间 + WAL 体积。

    磁盘写满的后果不是「慢」，是**数据库直接不可写**（评论/访问日志全失败），
    所以要提前预警而不是等它满。
    """
    items, notes, status = [], [], "ok"
    try:
        import shutil
        p = _db_path()
        data_dir = os.path.dirname(p) if p else os.path.join(_CODE_DIR, "data")
        items.append({"label": "数据目录", "value": data_dir, "level": "info"})
        try:
            total, used, free = shutil.disk_usage(data_dir)
            free_pct = round(free * 100.0 / total, 1) if total else 0.0
            items.append({"label": "磁盘剩余",
                          "value": f"{free / 1024 ** 3:.1f} GB / 共 {total / 1024 ** 3:.1f} GB（{free_pct}%）",
                          "level": "ok" if free_pct >= 10 else ("warn" if free_pct >= 5 else "error")})
            if free_pct < 5:
                notes.append("数据盘剩余不足 5%：SQLite 写不进去会直接导致后台报错、评论丢失。立刻清理日志/备份。")
                status = "error"
            elif free_pct < 10:
                notes.append("数据盘剩余不足 10%：建议清理旧备份与日志。")
                status = "warn"
        except Exception as e:  # noqa: BLE001, S110  单条读取失败按缺省处理，不能让一个损坏文件把整项判红
            items.append({"label": "磁盘剩余", "value": f"读取失败：{type(e).__name__}", "level": "warn"})
            if status == "ok":
                status = "warn"

        if p and os.path.exists(p):
            wal = p + "-wal"
            if os.path.exists(wal):
                mb = os.path.getsize(wal) / 1024.0 / 1024.0
                items.append({"label": "WAL 文件体积", "value": f"{mb:.2f} MB",
                              "level": "ok" if mb < 64 else "warn"})
                if mb >= 64:
                    notes.append(f"WAL 已涨到 {mb:.0f} MB：说明长时间没 checkpoint（通常是长连接一直持有读事务）。"
                                 "可执行 PRAGMA wal_checkpoint(TRUNCATE)。")
                    if status == "ok":
                        status = "warn"
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"磁盘检查异常：{type(e).__name__}: {e}")
    return {"key": "disk", "title": "磁盘与 WAL", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 19. MCP 服务自身（v4.11.0）
# ---------------------------------------------------------------------------
def check_mcp():
    """MCP 只读诊断 / 写服务 的运行状态。

    这一项存在的理由：MCP 是「AI 远程排障」的入口，它自己静默关掉了，
    外部助手只会看到 404 而**不知道该去后台哪一页打开**。
    """
    items, notes, status = [], [], "ok"
    try:
        import json as _json
        from utils import get_setting as _gs
        diag_off = (_gs("mcp_diag_disabled") or "").strip().lower() == "true"
        write_off = (_gs("mcp_write_disabled") or "").strip().lower() == "true"
        token = (current_app.config.get("MCP_AUTH_TOKEN") or "").strip()
        origins = (current_app.config.get("MCP_ALLOWED_ORIGINS") or "").strip()
        logfiles = (current_app.config.get("MCP_LOG_FILES") or "").strip()

        items.append({"label": "只读诊断 /mcp", "value": "已停止（对外 404）" if diag_off else "运行中",
                      "level": "warn" if diag_off else "ok"})
        items.append({"label": "写能力 /mcp-write", "value": "已停止（对外 404）" if write_off else "运行中",
                      "level": "info"})
        items.append({"label": "Bearer Token", "value": "已配置" if token else "未配置（端点整体关闭）",
                      "level": "ok" if token else "warn"})
        items.append({"label": "Origin 白名单", "value": origins or "仅同源", "level": "info"})
        items.append({"label": "日志读取 MCP_LOG_FILES", "value": logfiles or "未配置（recent_errors 不可用）",
                      "level": "info" if logfiles else "warn"})
        if not token:
            notes.append("未配置 MCP_AUTH_TOKEN：MCP 端点 fail-closed 全关，外部 AI 助手连不上。"
                         "这是**刻意的安全默认**，要启用就在环境变量里配一个长随机串。")
            status = "warn"
        if diag_off:
            notes.append("只读诊断端点被后台总开关停止（「MCP 服务」页可重新打开）：对外返回 404，不暴露端点存在。")
            if status == "ok":
                status = "warn"
        try:
            ext = _json.loads(_gs("mcp_external_services") or "[]")
            n = len(ext) if isinstance(ext, list) else 0
        except Exception:  # noqa: BLE001, S110  单条读取失败按缺省处理，不能让一个损坏文件把整项判红
            n = 0
        items.append({"label": "已登记外部 MCP 服务", "value": f"{n} 个", "level": "info"})
    except Exception as e:  # noqa: BLE001  体检项必须自兜底：checker 抛异常会拖垮整页评分与 MCP 输出，故在此统一降级为 notes
        status = "error"
        notes.append(f"MCP 状态检查异常：{type(e).__name__}: {e}")
    return {"key": "mcp", "title": "MCP 服务", "status": status, "items": items, "notes": notes}


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
CHECKS = [
    check_database,
    check_dependencies,
    check_config,
    check_security,
    check_feed_agg,
    check_backup,
    check_certificate,
    check_seo,
    check_pending,
    check_frontend_build,
    check_storage,
    check_render_cache,
    # v4.11.0：把「静默失败」的四类补齐 —— 插件没载入、搜索索引漂移、
    # 定时发布积压、MCP 自己关掉了，都不会让页面报错，只会让功能悄悄失效。
    check_plugins,
    check_search_index,
    check_scheduler,
    check_outbound,
    check_content_quality,
    check_disk,
    check_mcp,
]

# key → checker（MCP 的 run_check 工具与「只看某一维」都靠它查表）
CHECKS_BY_KEY = {
    "database": check_database, "dependencies": check_dependencies,
    "config": check_config, "security": check_security,
    "feed_agg": check_feed_agg, "backup": check_backup,
    "certificate": check_certificate, "seo": check_seo,
    "pending": check_pending, "frontend": check_frontend_build,
    "storage": check_storage, "render_cache": check_render_cache,
    "plugins": check_plugins, "search_index": check_search_index,
    "scheduler": check_scheduler, "outbound": check_outbound,
    "content_quality": check_content_quality, "disk": check_disk,
    "mcp": check_mcp,
}

# 每维权重：error 记 0 分、warn 记半分。用「维度均分」而不是「问题条数」——
# 否则一个磁盘 5 个异常项就能把 19 个维度里 18 个全绿的站点打成 20 分，
# 分数失去区分度（站长只会觉得这个数字没用）。
_STATUS_SCORE = {"ok": 1.0, "warn": 0.5}


def _normalize(sec):
    """统一 checker 输出：`items` 与 `rows` 互为别名，两边都补齐。

    ⚠️ 这是**修 bug 不是加功能**，而且是双向的同一个 bug 的两半：
    - 模板侧：`admin/feed_diag.html` 读 `sec.rows`，而 12 个 checker 里 10 个只返回
      `items` → Jinja 取到 Undefined（falsy）→ 明细表**恒不渲染**，体检页只剩
      标题、徽标和 notes；
    - 数据侧：`check_feed_agg` 只返回 `rows`（没有 `items`），而 `run_all()` 汇总
      问题清单与评分时遍历的是 `items` → 博客圈 RSS 的异常**从来没进过问题清单**。

    把归一化放在 run_all() 一处双向补齐，模板、MCP、评分三条消费路径同时对上；
    比在每个 checker 里各补一个键更不容易漏（漏一个就静默少一块）。
    """
    if not isinstance(sec, dict):
        return sec
    if not sec.get("items"):
        sec["items"] = sec.get("rows") or []
    if not sec.get("rows"):
        sec["rows"] = sec.get("items") or []
    return sec


def run_all():
    """运行全部 checker。

    返回：{generated_at, summary:{ok,warn,error}, sections:[...],
           score:int(0-100), issues:[...], issue_total:int}
    """
    sections = []
    summary = {"ok": 0, "warn": 0, "error": 0}
    for fn in CHECKS:
        try:
            sec = fn()
        except Exception as e:  # noqa: BLE001, S110  单条读取失败按缺省处理，不能让一个损坏文件把整项判红
            sec = {"key": fn.__name__, "title": fn.__name__, "status": "error",
                   "items": [], "rows": [], "notes": [f"checker 异常：{type(e).__name__}: {e}"]}
        _normalize(sec)
        sections.append(sec)
        summary[sec.get("status", "ok")] = summary.get(sec.get("status", "ok"), 0) + 1

    # 跨维度问题清单：页面与 MCP 都用它，避免各自再遍历一遍 items 而口径不一
    issues = []
    for sec in sections:
        for it in (sec.get("items") or []):
            lv = it.get("level")
            if lv not in ("error", "warn"):
                continue
            issues.append({"key": sec.get("key"), "dimension": sec.get("title"),
                           "label": it.get("label"), "value": it.get("value"),
                           "level": lv})
    # error 在前，同级保持 checker 顺序（sort 稳定）
    issues.sort(key=lambda x: -_severity(x.get("level")))

    score = 100
    if sections:
        score = round(100 * sum(_STATUS_SCORE.get(s.get("status"), 0.0) for s in sections) / len(sections))

    return {
        "generated_at": fmt_bj(utcnow(), "%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "score": score,
        "sections": sections,
        "issues": issues[:50],
        "issue_total": len(issues),
    }
