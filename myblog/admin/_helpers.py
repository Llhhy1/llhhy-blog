"""后台管理：登录、写文章、分类/标签/友链/设置/评论管理、修改密码、用户管理。"""
import functools
import datetime

from flask import (Blueprint, request, redirect, url_for,
                   session, current_app, abort)

from models import (db, Post, Tag, Comment, User, Guestbook, AuditLog, PostHistory, RecycleBin,
                    Announcement, FriendLink)
from utils import (make_slug, count_words, validate_password, apply_slug_template,
                   BEIJING_TZ, get_client_ip, safe_redirect)
from config import APP_VERSION
import audit as _audit
import fts
import mail_notify
import notify
from _time import utcnow
import contextlib

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")



def _parse_scheduled(form_val):
    """把编辑页 datetime-local 输入（YYYY-MM-DDTHH:MM，视为北京时间）转成 UTC datetime 存储。

    为空或非法则返回 None（=立即/已发布，不定时）。编辑页输入框与表单默认值均按北京时间
    展示（见 edit_post 视图的 scheduled_local / now_local），此处把用户输入当北京时间，
    换算回 UTC 存储，保证「所见即北京、所存即 UTC」，定时发布不再错位 8 小时。
    """
    if not form_val:
        return None
    try:
        bj = datetime.datetime.fromisoformat(form_val)  # naive 北京时间
        if bj.tzinfo is None:
            bj = bj.replace(tzinfo=BEIJING_TZ)
        return bj.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    except Exception:
        return None

def login_required(view):
    """登录即可访问（普通注册用户也能进来——拥有「发表文章」权限）。

    登录体系前后台已融合：前台 /login 与后台共用同一 Flask 会话；
    未登录统一引导到前台登录页，登录成功后按权限回到对应页面。
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if not user:
            # 未登录：去前台统一登录页，登录后按 next 回到原页面
            return redirect(safe_redirect(url_for("main.login", next=request.path)))
        # 首次进入后台：超级管理员还没设置过账号密码 → 强制去设置页
        if user.is_super and user.must_change_password:
            return redirect(url_for("admin.setup"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    """管理员及以上（super / admin）专属：普通用户（user）只被引导到写文章页。"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if not user:
            return redirect(safe_redirect(url_for("main.login", next=request.path)))
        if not user.is_admin_role:
            # 普通用户没有管理权限：引导到「写文章」（他们能用的功能）
            return redirect(url_for("admin.new_post"))
        if user.is_super and user.must_change_password:
            return redirect(url_for("admin.setup"))
        return view(*args, **kwargs)
    return wrapped

def super_required(view):
    """超级管理员专属装饰器：其他角色（含普通管理员）一律 403。"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        # v3.17.11（审计 R76-R1）：未登录时 session 无 user_id，原写法 db.session.get(User, None)
        # 会触发 SAWarning「fully NULL primary key identity cannot load any object」
        # （SQLAlchemy 未来版本将升级为错误）——先判空再查，行为等价。
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if not user or not user.is_super:
            abort(403)
        # 与 login_required / admin_required 对齐：超管尚未完成首登设置前，除 setup 页
        # 外一律先跳过去。此前只有那两道装饰器有这一关，而 29 条路由是**裸**
        # @super_required（含 /admin/settings、/admin/backup、/admin/theme、MCP 服务、
        # AI 摘要、收录控制台），等于在「默认密码窗口期」内全部可任意使用。
        if user.must_change_password:
            return redirect(url_for("admin.setup"))
        return view(*args, **kwargs)
    return wrapped

def _weak_password(raw):
    """v3.1.6 中优：弱密码统一校验（黑名单 + 复杂度）。返回错误文案；通过返回空字符串。"""
    try:
        from utils import flag_bool, flag_num
        ok, err = validate_password(
            raw or "", min_len=8,
            # v3.25.8：强密码策略改由「系统设置」可配（DB → env → 默认）。
            strong=flag_bool("strong_password", "STRONG_PASSWORD", True),
            mixed_case=flag_bool("strong_password_mixed_case", "STRONG_PASSWORD_MIXED_CASE", False),
        )
        return "" if ok else err
    except Exception:
        return "" if len(raw or "") >= 8 else "密码至少 8 位"

def _can_edit_post(user, post):
    """判断当前用户能否编辑/删除该文章：管理员可编辑全部；普通用户只能编辑自己的。"""
    if user.is_admin_role:
        return True
    return post.author_id is not None and post.author_id == user.id

def log_audit(action, target="", target_id=None, detail="", user=None, ip="", success=True):
    """记录一条后台操作审计日志（v3.0.0 功能4）。

    v3.25.0：实现已迁至顶层 `audit.py`（横切关注点，api / routes / seo_push 都要用）。
    这里保留同名薄转发，**`admin._helpers.log_audit` 这个既有 API 不破** ——
    包内 22 个子模块与外部调用方无需改动。
    """
    return _audit.log_audit(action, target, target_id, detail, user, ip, success)


def log_login_attempt(username, success, ip=""):
    """记录一次后台登录尝试（v3.1.0 新增）。v3.25.0 起实现位于顶层 `audit.py`。"""
    return _audit.log_login_attempt(username, success, ip)


def _purge_audit_logs_older_than(days):
    """清理超过 N 天的审计日志。v3.25.0 起实现位于顶层 `audit.py`。"""
    return _audit._purge_audit_logs_older_than(days)

def _audit_log_query_with_filters():
    """按 query 参数（from / to）构造审计日志查询（v3.1.6 中优·导出时间筛选）。

    支持 ?from=YYYY-MM-DD 与 ?to=YYYY-MM-DD（均为本地日期，按 UTC 存储比较）。
    无参数时返回全部（保留周期内）。
    """
    q = AuditLog.query
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    if frm:
        try:
            d = datetime.datetime.strptime(frm, "%Y-%m-%d")
            q = q.filter(AuditLog.created_at >= d)
        except ValueError:
            pass
    if to:
        try:
            d = datetime.datetime.strptime(to, "%Y-%m-%d") + datetime.timedelta(days=1)
            q = q.filter(AuditLog.created_at < d)
        except ValueError:
            pass
    return q, frm, to

def _current_user_or_none():
    """取当前登录用户对象（用于审计日志等），未登录返回 None。"""
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def unique_slug(base, post_id=None):
    base_slug = make_slug(base)
    slug = base_slug
    i = 2
    while True:
        q = Post.query.filter_by(slug=slug)
        if post_id:
            q = q.filter(Post.id != post_id)
        if not q.first():
            break
        slug = f"{base_slug}-{i}"
        i += 1
    return slug

@admin_bp.context_processor
def inject_notification_counts():
    """向所有后台模板注入未读评论/未读留言数量，用于导航角标和仪表盘提醒。"""
    try:
        pending_comments = Comment.query.filter_by(is_read=False).count()
        pending_guestbook = Guestbook.query.filter_by(is_read=False).count()
    except Exception:
        # 表尚未创建时（首次启动）不报错
        pending_comments = 0
        pending_guestbook = 0
    return {
        "pending_comments": pending_comments,
        "pending_guestbook": pending_guestbook,
        "app_version": APP_VERSION,
    }

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]

# v3.1.6 图片魔数表：文件头前缀 -> (类型名, 期望后缀)。webp 只记 RIFF 前缀，
# 具体 WEBP 标识由 _detect_image_magic 里的 12 字节精验负责。
_MAGIC_PATTERNS = {
    b"\x89PNG\r\n\x1a\n": ("png", "png"),
    b"\xff\xd8\xff": ("jpeg", "jpg"),
    b"GIF87a": ("gif", "gif"),
    b"GIF89a": ("gif", "gif"),
    b"RIFF": ("webp", "webp"),
}

def _detect_image_magic(header, ext):
    """根据文件头魔数 + 期望后缀判断是否匹配。返回 False 拒绝，True 通过。
    对 webp 追加 RIFF 后的 'WEBP' 四个字节精验；其余按魔数前缀匹配。
    """
    for magic, (mtype, _) in _MAGIC_PATTERNS.items():
        if header.startswith(magic):
            if mtype == "webp":
                if len(header) >= 12 and header[8:12] == b"WEBP":
                    return True
                return False
            return True
    return False

def _sync_tags(post, raw):
    """把 '生活, 技术' 这样的标签字符串同步到文章（v3.15.0 标签治理）。

    自动去重 + 防膨胀：
    - 分隔符兼容 ASCII/中文逗号、顿号、分号、换行（此前只认 ASCII 逗号，'，'会整串成一个标签）；
    - 按归一化键（小写 + 去空白）匹配既有标签：'AI'/'ai'/' AI ' 复用同一行，不新建；
    - 单篇内同义重复只保留一次；新建时 slug 走唯一化，避免与既有标签撞 slug。
    0 使用标签由 cleanup_orphan_tags() 在提交后清理。
    """
    from utils import normalize_tag_key, split_tag_input
    index = {}  # norm_key -> Tag（全表按归一化键索引，规模小直接全扫）
    for t in Tag.query.all():
        index.setdefault(normalize_tag_key(t.name), t)
    post.tags = []
    for name in split_tag_input(raw):
        key = normalize_tag_key(name)
        tag = index.get(key)
        if not tag:
            tag = Tag(name=name, slug=unique_model_slug(Tag, name, max_len=90))
            db.session.add(tag)
            db.session.flush()
            index[key] = tag
        if tag not in post.tags:
            post.tags.append(tag)


def cleanup_orphan_tags():
    """删除没有任何文章使用的标签（0 使用清理，v3.15.0）。

    应在文章保存提交后调用（此时新关联已落库），返回清理条数。
    """
    removed = 0
    for t in Tag.query.all():
        if not list(t.posts):
            try:
                db.session.delete(t)
                removed += 1
            except Exception:
                pass
    if removed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return removed


def merge_duplicate_tags():
    """合并归一化键相同的重复标签（v3.15.0 标签治理）。

    按「使用文章最多优先」保留一行，其余行的文章改挂到保留行后删除重复行。
    返回合并删除的行数。历史遗留的 'AI'+'ai' 类重复调用一次即收敛。
    """
    from utils import normalize_tag_key
    by_key = {}
    for t in Tag.query.all():
        by_key.setdefault(normalize_tag_key(t.name), []).append(t)
    merged = 0
    for _key, group in by_key.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda t: len(list(t.posts)), reverse=True)
        keep = group[0]
        for dup in group[1:]:
            for p in list(dup.posts):
                if keep not in p.tags:
                    p.tags.append(keep)
            db.session.delete(dup)
            merged += 1
    if merged:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return merged

def _save_post_history(post, author=""):
    """保存当前文章的版本快照（v3.0.0 功能5）。

    每次有内容/标题变化时调用，存一份 title/summary/content/author 快照。
    仅保留最近 20 个版本（超出删最旧），避免无限增长。
    """
    try:
        db.session.add(PostHistory(
            post_id=post.id, title=post.title or "", summary=post.summary or "",
            content=post.content or "", author=author or "",
        ))
        # 限制每个文章最多 20 个历史版本
        old = PostHistory.query.filter_by(post_id=post.id).order_by(PostHistory.created_at.asc()).all()
        if len(old) > 20:
            for h in old[:len(old) - 20]:
                db.session.delete(h)
    except Exception:
        pass


def create_post_core(*, title, content, summary="", cover="", category_id=None,
                     tags="", series_id=None, seo_description="", seo_keywords="",
                     published=False, scheduled_at=None, author_id=None,
                     is_pinned=False, is_private=False,
                     reward_enabled=False, reward_qr="",
                     notify_subscribers=False,
                     lang="zh", translation_group=""):
    """发文唯一入口：后台表单与写能力 MCP（/mcp-write）共用，返回新建的 Post。

    调用顺序严格沿用 admin/posts.py::new_post()（v3.12.2 抽出，防两套逻辑漂移）：
      count_words → Post(...) → add → flush → apply_slug_template → _sync_tags
      → _save_post_history → commit → fts.sync_post → (发布时) 通知/群发

    注意：本函数对传入的「提权字段」(is_pinned/is_private/reward_*/author_id) 一律按
    调用方已校验后的值使用，自身不做权限分层——权限分层由 new_post（读会话角色）与
    mcp_write（读 MCP_WRITE_ALLOW_SUPER_FIELDS 配置）各自在调用前完成。
    """
    # 定时发布：填了未来时间则先存为未发布（与 new_post 行为一致）
    if scheduled_at is not None and scheduled_at > utcnow():
        published = False

    # 字数统计 + 阅读时长（v3.0.0 功能12）
    wc, rm = count_words(content)
    post = Post(
        title=title, slug=title, summary=summary, content=content,
        cover=cover, category_id=category_id, published=published,
        scheduled_at=scheduled_at, is_pinned=is_pinned,
        seo_description=seo_description, seo_keywords=seo_keywords,
        series_id=int(series_id) if series_id else None,
        author_id=author_id,
        word_count=wc, reading_minutes=rm,
        is_private=is_private, reward_enabled=reward_enabled, reward_qr=reward_qr,
        lang=(lang or "zh"), translation_group=(translation_group or "").strip(),
    )
    db.session.add(post)
    db.session.flush()  # 先把文章放进会话，避免标签关联警告
    # flush 后 post.id / post.category 可用：按全局模板生成最终 slug（用户无法手工干预）
    post.slug = apply_slug_template(post, title)
    _sync_tags(post, tags)
    # v3.0.0 功能5：保存首个版本历史（新建即 v1）；作者名取自 author_id
    author_user = db.session.get(User, author_id) if author_id else None
    _save_post_history(post, author_user.username if author_user else "")
    db.session.commit()
    cleanup_orphan_tags()  # v3.15.0：提交后清 0 使用标签，避免越积越多
    with contextlib.suppress(Exception):
        fts.sync_post(post)
    if published:
        with contextlib.suppress(Exception):
            notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
        # v3.20.0：新文自动推送（默认关闭，见 seo_push.maybe_auto_push 的说明）
        try:
            import seo_push
            seo_push.maybe_auto_push(post)
        except Exception:  # noqa: BLE001, S110  (自动推送失败绝不影响发布主流程)
            pass
        # C3 邮件群发：新文章发布时异步通知所有订阅者（未配置 SMTP 自动跳过）
        if notify_subscribers:
            with contextlib.suppress(Exception):
                mail_notify.notify_subscribers_async(post)
    return post


def form_flag(form, key):
    """勾选框/布尔字段的统一取值（v4.3.0：后台表单与移动端 JSON 共用一个判据）。

    - 后台 SSR 表单：勾选值为 `"on"`，未勾选时键缺失（`.get()` 返回 None）；
    - 移动端 JSON：`true` / `false`（也可能被客户端序列化成 `"true"`）。
    两套写法都归一成 bool，避免同一个字段在不同入口有两套语义。
    """
    v = form.get(key)
    if isinstance(v, str):
        return v.strip().lower() in ("on", "true", "1", "yes")
    return bool(v)


def update_post_core(post, form, user):
    """编辑文章的**唯一**字段落库实现（v4.3.0 从 `post_editor.edit_post` 原样抽出）。

    抽出动机：移动端管理接口（`api/mobile.py`）需要同一个编辑能力。若各处再写一遍
    「哪个字段谁能改」，两份实现就会漂移——`_parse_scheduled` 的注释里记着「定时发布
    曾错位 8 小时」，而「普通用户提交 is_pinned 必须被忽略」这类规则一旦只写在一处，
    另一处迟早漏掉。行为与 v4.2.0 的 `edit_post` POST 分支**逐行等价**，
    改动本函数等于同时改后台编辑页与移动端，务必跑 `tests/test_edit_post_history.py`
    与 `tests/test_admin_posts_characterization.py`。

    `form` 只需支持 `.get(key)`（`request.form` 或普通 dict 均可）。
    返回错误文案；成功返回空字符串（此时 post 已提交并同步 FTS）。

    权限分层与后台一致，刻意**不**信任调用方传入的提权字段：
      · `is_pinned` / `pin_requested`：仅管理员可改（普通用户提交一律忽略）
      · `is_private` / `reward_*`：仅超管可改
    """
    title = (form.get("title") or "").strip()
    if not title:
        return "标题不能为空"
    # 保留旧值用于「是否记版本历史」与「是否刚转发布」判断：
    # post.title / post.content / post.published 在下面就会被覆盖
    old_title = post.title
    old_content = post.content
    was_published = post.published
    from .taxonomy import _ensure_category_by_name, _ensure_series_by_name
    post.title = title
    # v3.7.0：slug 强制由全局模板决定，用户无法手工覆盖。标题 slug 未变则保持原 slug
    # （不破坏已有 URL / SEO），变了（或原为空）才套模板重新生成。
    if make_slug(title) != post.slug:
        post.slug = apply_slug_template(post, title)
    post.summary = (form.get("summary") or "").strip()
    post.content = form.get("content") or ""
    post.cover = (form.get("cover") or "").strip()
    # v3.14.0：就地新建分类/系列（编辑页「＋新建…」随表单提交，同名自动复用）
    new_cat = (form.get("new_category_name") or "").strip()
    cid = _ensure_category_by_name(new_cat) if new_cat else (form.get("category_id") or None)
    post.category_id = int(cid) if cid else None
    new_ser = (form.get("new_series_name") or "").strip()
    sid = _ensure_series_by_name(new_ser) if new_ser else (form.get("series_id") or None)
    post.series_id = int(sid) if sid else None
    scheduled_at = _parse_scheduled(form.get("scheduled_at"))
    published = form_flag(form, "published")
    # 定时发布：填了未来时间先存未发布，后台线程到点自动翻 published；
    # 否则清空 scheduled_at，避免历史脏值把「立即发布」又拖回定时队列。
    if scheduled_at is not None and scheduled_at > utcnow():
        published = False
    else:
        scheduled_at = None
    post.published = published
    post.scheduled_at = scheduled_at
    if user.is_admin_role:
        post.is_pinned = form_flag(form, "is_pinned")
        post.pin_requested = False  # 管理员直接操作置顶，不留申请态
    post.seo_description = (form.get("seo_description") or "").strip()
    post.seo_keywords = (form.get("seo_keywords") or "").strip()
    post.lang = (form.get("lang") or "zh").strip() or "zh"
    post.translation_group = (form.get("translation_group") or "").strip()
    if user.is_super:
        post.is_private = form_flag(form, "is_private")
        post.reward_enabled = form_flag(form, "reward_enabled")
        post.reward_qr = (form.get("reward_qr") or "").strip() if post.reward_enabled else ""
    wc, rm = count_words(post.content)
    post.word_count = wc
    post.reading_minutes = rm
    _sync_tags(post, form.get("tags") or "")
    if post.content != old_content or old_title != title:
        _save_post_history(post, user.username if user else "")
    db.session.commit()
    cleanup_orphan_tags()
    with contextlib.suppress(Exception):
        fts.sync_post(post)
    # 「草稿/定时 → 已发布」这一次翻转才推送与群发（重复保存已发布文章不再骚扰订阅者）
    if post.published and not was_published:
        _announce_post_published(post)
    return ""


def _announce_post_published(post, notify_subscribers=True):
    """文章转为已发布后的对外动作：站内/IM 推送 + SEO 自动收录 + 邮件群发（全部静默失败）。

    v4.3.0 抽出：后台发布、移动端发布、编辑页「草稿转发布」三处原本各抄一遍同样的
    5 行 try/suppress，容易漏掉其中一项（漏 `emit_post_published` 就少一次插件事件）。
    """
    with contextlib.suppress(Exception):
        notify.notify_new_post(post, current_app.config.get("SITE_URL", ""))
    with contextlib.suppress(Exception):
        from plugins.signals import emit_post_published
        emit_post_published(post)
    with contextlib.suppress(Exception):
        import seo_push
        seo_push.maybe_auto_push(post)
    if notify_subscribers:
        with contextlib.suppress(Exception):
            mail_notify.notify_subscribers_async(post)


def publish_post_core(post, user):
    """把文章置为已发布（定时/草稿 → 公开）。返回 True=本次真的翻了状态，False=无权限。

    权限：管理员全部；普通用户仅自己发表的（`author_id` 匹配）。
    后台「立即发布」与 `/api/post/<id>/publish-now`、移动端共用本函数（v4.3.0）。
    """
    if not _can_edit_post(user, post):
        return False
    if post.published:
        return True
    post.published = True
    post.scheduled_at = None  # 清空定时，避免后台线程重复触发
    db.session.commit()
    fts.sync_post_quiet(post)
    _announce_post_published(post)
    return True


def trash_post_core(post, user, snapshot=True):
    """软删除：快照进回收站 + 标记 `in_trash` + 移出 FTS 索引。返回 False=无权限。

    ⚠️ `fts.delete_post()` 必须在：不同步的话已删文章仍会被 `/api/search` 命中。
    """
    if not _can_edit_post(user, post):
        return False
    if snapshot:
        with contextlib.suppress(Exception):
            db.session.add(RecycleBin(
                post_id=post.id, title=post.title or "", slug=post.slug or "",
                summary=post.summary or "", content=post.content or "", cover=post.cover or "",
                category_id=post.category_id, author_id=post.author_id, series_id=post.series_id,
                deleted_by=user.username if user else "",
            ))
    post.in_trash = True
    post.deleted_at = utcnow()
    db.session.commit()
    with contextlib.suppress(Exception):
        fts.delete_post(post.id)
    return True


# ---------------------------------------------------------------- v4.4.0 内容管理核心
# 抽核心的原因与 `create_post_core` 一样：后台 SSR 页面与移动端 JSON 必须共用一套
# 「哪个字段能写、怎么校验、有什么副作用」的实现，否则两边迟早漂移。
# 本节的函数**只做数据与副作用**，`log_audit` / `flash` / `redirect` 留在各自入口
# （与 `publish_post_core` 的分工一致）。

ANNOUNCEMENT_LEVELS = ("info", "warning", "success")


def _announcement_fields(form):
    """归一公告表单字段 → `(字段 dict, 错误文案)`。

    两条收紧（都是后台原来的缺口）：
      · `content` 为空直接拒（原来会建出一条空白公告，前台顶部挂着一条空横幅）；
      · `level` 只认白名单（原来任意字符串都能进库，前台按 level 上色会出现未知档）。
    勾选框走 `form_flag`，后台表单的 `"on"` 与移动端 JSON 的 `true` 同一判据。
    """
    content = (form.get("content") or "").strip()
    if not content:
        return {}, "公告内容不能为空"
    level = (form.get("level") or "info").strip().lower()
    if level not in ANNOUNCEMENT_LEVELS:
        level = "info"
    return {"content": content, "level": level,
            "active": form_flag(form, "active"),
            "dismissible": form_flag(form, "dismissible")}, ""


def create_announcement_core(form):
    """新建公告 → `(Announcement, "")`；校验不过 → `(None, 错误文案)`。"""
    fields, err = _announcement_fields(form)
    if err:
        return None, err
    ann = Announcement(**fields)
    db.session.add(ann)
    db.session.commit()
    return ann, ""


def update_announcement_core(ann, form):
    """整单修改一条公告。返回错误文案；成功返回 ""。"""
    fields, err = _announcement_fields(form)
    if err:
        return err
    ann.content = fields["content"]
    ann.level = fields["level"]
    ann.active = fields["active"]
    ann.dismissible = fields["dismissible"]
    db.session.commit()
    return ""


def normalize_link_url(raw):
    """友链 URL 归一：补协议、去空白。返回 "" 表示不可用。

    前台直接把 url 当 `href` 用，`javascript:` 之类的伪协议就是 XSS 入口，
    所以这里只放行 http/https，且不带协议的自动补 `https://`（用户习惯只写域名）。
    """
    u = (raw or "").strip()
    if not u or len(u) > 300:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if not u.startswith(("http://", "https://")):
        # 第一个 "/" 之前出现 ":" 就说明是别的协议（javascript: / mailto: / data: / file:），
        # 一律拒。前台把 url 直接当 href 用，这里放行一条就等于送一个可点执行的链接。
        # 补 https:// 只对「光秃秃的域名/路径」做，且先排掉以 "/" 或 "\\" 开头的站内/绝对路径。
        if ":" in u.split("/", 1)[0] or u.startswith(("/", "\\")):
            return ""
        u = "https://" + u
    return u if u.startswith(("http://", "https://")) else ""


def save_friend_link_core(link, form):
    """新增（`link=None`）或修改一条友链 → `(错误文案, 附加提示, 落库后的行)`。

    v4.4.0 才有的能力：后台原本只能「新增 / 存 RSS / 删除」，`name/url/description/sort`
    **没有任何编辑入口**，改一个字都得删了重建（会丢排序位置）。新增与修改因此共用本函数。

    三条一起补上的校验/行为：
      · URL 归一（见 `normalize_link_url`）+ **同 URL 查重**（排除自身）。后台新增原先不查重，
        而审核路径 `approve_link_application` 早就查了 —— 两个入口两套口径，这里统一到查重的这套。
      · `sort` 取整数，缺省 0（越小越靠前，见 `models.FriendLink.sort` 注释）。
      · `rss_url` 给了就**软**校验可达性（与既有 `set_link_rss` 一致：不可达只提示、不阻断保存，
        因为对方源可能临时抽风，硬拦会把能用的友链挡在门外）。

    第三个返回值是**落库后的 `FriendLink`**：新增时行对象在本函数内部创建，调用方（审计日志、
    移动端 JSON）要拿到它的 id，否则只能按 URL 回查一次 —— 回查依赖「URL 唯一」这个本函数
    刚刚建立的前提，绕一圈不如直接还回来。校验不过时为 `None`。
    """
    name = (form.get("name") or "").strip()
    if not name:
        return "友链名称不能为空", "", None
    url = normalize_link_url(form.get("url"))
    if not url:
        return "网址不合法（只支持 http/https，且不能是站内相对路径）", "", None
    dup = FriendLink.query.filter(FriendLink.url == url).first()
    if dup and (link is None or dup.id != link.id):
        return f"已存在指向同一网址的友链「{dup.name}」，请勿重复添加", "", None
    try:
        sort = int(form.get("sort") or 0)
    except (TypeError, ValueError):
        sort = 0
    rss = (form.get("rss_url") or "").strip()[:300]
    if link is None:
        link = FriendLink(name=name, url=url)
        db.session.add(link)
    link.name = name[:100]
    link.url = url
    link.description = (form.get("description") or "").strip()[:200]
    link.sort = sort
    link.rss_url = rss
    db.session.commit()
    note = ""
    if rss:
        with contextlib.suppress(Exception):
            import feed_agg
            ok, reason = feed_agg.validate_feed_url(rss)
            if not ok:
                note = "该 RSS 地址可能不可用（%s），博客圈将无法聚合此源" % reason
    return "", note, link


def reorder_friend_links_core(ordered_ids):
    """按给定顺序重排友链 `sort`（步长 10，给以后插位留空档）→ 实际改动的条数。

    只认列表里出现的 id；表里其余条目**不动**（App 侧一次提交完整顺序，
    半提交时未列出的保持原位，比把没列的甩到末尾更安全）。
    """
    moved = 0
    for i, raw in enumerate(ordered_ids[:500]):
        try:
            lid = int(raw)
        except (TypeError, ValueError):
            continue
        link = db.session.get(FriendLink, lid)
        if link is None:
            continue
        want = (i + 1) * 10
        if link.sort != want:
            link.sort = want
            moved += 1
    db.session.commit()
    return moved


def rollback_post_core(post, hist, user):
    """把文章回滚到某个历史版本（v4.4.0 从 `admin/post_history.py` 原样抽出）。

    **只写回 `title` / `summary` / `content`** —— 不动 slug、封面、分类、标签、系列、
    发布态、SEO，所以回滚不会破坏已分发出去的 URL，也不会把已发布文章悄悄变成草稿。
    回滚前先 `_save_post_history` 备份当前版，因此回滚本身可再撤销（原行为保持）。
    """
    if not _can_edit_post(user, post):
        return "只能操作自己发表的文章"
    _save_post_history(post, user.username if user else "")
    post.title = hist.title or post.title
    post.summary = hist.summary or ""
    post.content = hist.content or ""
    db.session.commit()
    with contextlib.suppress(Exception):
        fts.sync_post(post)
    return ""


def unique_model_slug(model, base, exclude_id=None, max_len=80):
    """通用 slug 唯一化（Category / Series / Tag 等 Post 以外的表，v3.14.0）。

    与 post 的 unique_slug 同思路：基础 slug 冲突（可排除自身）时追加 -2/-3。
    额外做长度截断：这些表的 slug 列是 String(90/110)，中文短名一般没问题，
    但超长输入会超出列宽（SQLite 不强制、Postgres 会报错），截断到 max_len 以内最稳。
    """
    b = make_slug(base)
    if len(b) > max_len:
        b = b[:max_len]
    slug = b or "item"
    i = 2
    while True:
        q = model.query.filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if not q.first():
            return slug
        suffix = f"-{i}"
        slug = (b[:max_len - len(suffix)] + suffix) if len(b) > max_len - len(suffix) else f"{b}-{i}"
        i += 1


# 显式导出清单（v3.24.0 治理：原先是 `[n for n in globals() if not n.startswith("__")]`
# 运行时快照，会把 os / time / functools / Blueprint / db / Post… 等全部顶层名字
# 一并导出，各业务子模块的 `from ._helpers import *` 于是把它们全灌进自己的命名空间。
# 后果：① 每个模块带 15~20 个用不上的污染名；② 同名符号（time / utcnow / feed_agg /
# current_app…）谁生效只取决于「星号行与自身 import 行的先后」，行序一变就 NameError，
#    而任何静态检查都看不见这种依赖。
#
# 现在只导出「本模块自己定义的跨模块公共 API」，导入方一律写显式 import。
# 下划线 helper 必须在列：Python 的 star-import 默认跳过下划线命名，若不列入，
# from ._helpers import * 就拿不到 _can_edit_post / _save_post_history 等。
__all__ = [
    # 蓝图对象（各子模块与 app.py 的 admin_bp 必须是这一个）
    "admin_bp",
    # 访问控制装饰器
    "admin_required", "super_required", "login_required",
    # 审计
    "log_audit", "log_login_attempt", "_audit_log_query_with_filters",
    # 当前用户
    "_current_user_or_none",
    # 标签 / slug / 分类
    "unique_slug", "unique_model_slug", "_sync_tags", "cleanup_orphan_tags",
    "merge_duplicate_tags",
    # 文章
    "create_post_core", "_can_edit_post", "_save_post_history", "_parse_scheduled",
    # v4.3.0：编辑/发布/软删的唯一实现（后台 SSR 与移动端 JSON 共用）
    "update_post_core", "publish_post_core", "trash_post_core", "form_flag",
    "_announce_post_published",
    # v4.4.0：公告 / 友链 / 版本回滚的唯一实现（后台 SSR 与移动端 JSON 共用）
    "ANNOUNCEMENT_LEVELS", "_announcement_fields", "create_announcement_core",
    "update_announcement_core", "normalize_link_url", "save_friend_link_core",
    "reorder_friend_links_core", "rollback_post_core",
    # 媒体 / 密码 / 统计
    "allowed_file", "_detect_image_magic", "_weak_password",
]