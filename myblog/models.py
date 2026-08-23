"""数据库模型定义。
使用 SQLAlchemy ORM，所有表结构都在这里描述，运行时会自动建表。
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Post(db.Model):
    """文章表"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)  # 网址用的短名
    summary = db.Column(db.String(400))                            # 摘要
    content = db.Column(db.Text)                                   # 正文（Markdown）
    cover = db.Column(db.String(500))                             # 封面图 URL（可选）
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    author_id = db.Column(db.Integer, default=None)  # 作者 id（普通用户发表的文章记录；管理员/旧文章为 None）
    # 作者关系：author_id 并非真正的外键（旧数据/管理员的文章为 None），用 primaryjoin 显式关联
    author = db.relationship("User", primaryjoin="Post.author_id == User.id",
                             foreign_keys=[author_id], viewonly=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published = db.Column(db.Boolean, default=True)                # 是否发布
    # 定时发布时间：为空=立即发布/已发布；不为空且未来时间=定时待发布（到点后由后台线程翻 published）
    scheduled_at = db.Column(db.DateTime, nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)               # 是否置顶（首页/列表优先展示）
    # 置顶申请（v2.8.1）：普通用户无直接置顶权，需向超管申请；超管批准后才 is_pinned=True
    pin_requested = db.Column(db.Boolean, default=False)           # 是否已提交置顶申请（待审批）
    # SEO 单独字段（v2.8.0）：独立的页面描述与关键词，缺省回退到 summary/标签
    seo_description = db.Column(db.Text)                            # 页面 meta description（搜索引擎摘要）
    seo_keywords = db.Column(db.String(300))                        # 页面 meta keywords（逗号分隔）
    # ===== v3.0.0 新增字段 =====
    # 字数统计 + 预计阅读时长（由正文自动计算，存储以便排序/展示）
    word_count = db.Column(db.Integer, default=0)                   # 正文中文字数（粗略：中文字+英文词）
    reading_minutes = db.Column(db.Integer, default=0)             # 预计阅读时长（分钟，按 300 字/分估算）
    # 文章打赏（仅超级管理员可在每篇结尾开关，v3.0.0 功能14）
    reward_enabled = db.Column(db.Boolean, default=False)         # 该篇是否开启打赏
    reward_qr = db.Column(db.String(500), default="")               # 打赏二维码图片 URL（留空用全局默认）
    # 超级管理员隐私空间（v3.0.0 功能13）：is_private=True 的文章仅超管可见
    is_private = db.Column(db.Boolean, default=False)              # 是否隐私文章（仅超管可见）
    # 回收站（v3.0.0 功能5）：deleted=True 表示进入回收站（软删除），不出现在前台/列表
    in_trash = db.Column(db.Boolean, default=False)                 # 是否已在回收站（软删除）
    deleted_at = db.Column(db.DateTime, nullable=True)             # 进入回收站时间（用于排序/保留期）
    views = db.Column(db.Integer, default=0)                       # 阅读量
    likes = db.Column(db.Integer, default=0)                       # 点赞数
    comments = db.relationship("Comment", backref="post", cascade="all, delete-orphan", lazy="dynamic")
    tags = db.relationship("Tag", secondary="post_tag", backref="posts")
    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=True)  # 所属专栏/系列
    series = db.relationship("Series", backref=db.backref("posts", lazy="dynamic"),
                             foreign_keys=[series_id],
                             primaryjoin="Series.id == Post.series_id")


class Category(db.Model):
    """分类表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False)
    posts = db.relationship("Post", backref="category", lazy="dynamic")


class Tag(db.Model):
    """标签表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False)


class PostTag(db.Model):
    """文章与标签的关联表（多对多）"""
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag.id"), primary_key=True)


class Comment(db.Model):
    """评论表"""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    author = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved = db.Column(db.Boolean, default=True)  # True=显示，False=待审核
    ip = db.Column(db.String(64), default="")       # 评论者 IP（用于回填归属地）
    region = db.Column(db.String(64), default="")   # 归属地（如 广东·广州），异步解析回填
    device = db.Column(db.String(120), default="")  # 设备信息（如 手机 · Android · Chrome）
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)  # 回复的父评论 id（嵌套回复）
    reply_to = db.Column(db.String(80), default="")  # 被回复者昵称（前端 @ 显示用）
    likes = db.Column(db.Integer, default=0)         # 评论点赞数
    is_read = db.Column(db.Boolean, default=False)   # 管理员是否已读（新消息提醒）


class FriendLink(db.Model):
    """友情链接表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(300), nullable=False)
    description = db.Column(db.String(200))
    sort = db.Column(db.Integer, default=0)  # 排序，越小越靠前
    rss_url = db.Column(db.String(300), default="")  # 该友链站点的 RSS 地址（留空则不参与「博客圈」聚合）


class Setting(db.Model):
    """站点设置（键值对存储，如站点标题、关于内容、天气坐标等）"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text)


class VisitLog(db.Model):
    """访客访问日志（统计累计访问、区域排行榜、时段分布用）"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), index=True)    # 本地日期 YYYY-MM-DD
    hour = db.Column(db.Integer, default=0)        # 访问时段 0-23
    ip = db.Column(db.String(64), index=True)
    region = db.Column(db.String(64), default="")  # 属地（如 浙江·杭州），后台线程异步解析回填
    path = db.Column(db.String(255), default="")
    post_id = db.Column(db.Integer, default=None)  # 若访问的是文章页，记录文章 id
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ReadLog(db.Model):
    """文章阅读记录（同一访客同一篇累加 read_count，用于"反复阅读"统计）"""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    ip = db.Column(db.String(64), index=True)
    read_count = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("post_id", "ip", name="uq_read_post_ip"),)


class SearchLog(db.Model):
    """搜索词记录（统计常搜词汇）"""
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(120), index=True)
    date = db.Column(db.String(10), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IpRegion(db.Model):
    """IP 属地缓存（避免每个访客都请求在线查询接口）"""
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), unique=True, index=True)
    region = db.Column(db.String(64), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 用户角色（权限等级从高到低）
ROLE_SUPER = "super"   # 超级管理员：拥有全部权限，可管理其他用户，不可被删除/降级
ROLE_ADMIN = "admin"   # 管理员：可进入后台管理内容（文章/分类/标签/评论/设置）
ROLE_USER = "user"     # 普通用户：可注册、登录、发表评论


class User(db.Model):
    """用户表：注册用户 + 后台管理员。
    角色说明见 ROLE_* 常量。
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    email = db.Column(db.String(120))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), default=ROLE_USER, nullable=False)
    must_change_password = db.Column(db.Boolean, default=True)  # True=首次进入后台需先设置账号密码
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3.1.6 中优：会话版本号（改密码 / 超管踢下线时 +1，旧会话全部失效）
    session_version = db.Column(db.Integer, default=0)

    def set_password(self, raw):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, raw)

    @property
    def is_super(self):
        return self.role == ROLE_SUPER

    @property
    def is_admin_role(self):
        """能否进入后台（超级管理员 + 管理员）。"""
        return self.role in (ROLE_SUPER, ROLE_ADMIN)

    def bump_session_version(self):
        """v3.1.6：会话版本号 +1（改密码 / 超管踢下线时调用），使该用户所有旧会话立即失效。"""
        self.session_version = (self.session_version or 0) + 1
        db.session.commit()
        return self.session_version

    @property
    def role_label(self):
        return {"super": "超级管理员", "admin": "管理员", "user": "普通用户"}.get(self.role, self.role)


class Moment(db.Model):
    """微动态（微博客）：作者发的短内容，可点赞、可评论。"""
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    author = db.relationship("User", foreign_keys=[author_id], viewonly=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    comments = db.relationship("MomentComment", backref="moment",
                               cascade="all, delete-orphan", lazy="dynamic")


class MomentComment(db.Model):
    """微动态评论。"""
    id = db.Column(db.Integer, primary_key=True)
    moment_id = db.Column(db.Integer, db.ForeignKey("moment.id"), nullable=False)
    author = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip = db.Column(db.String(64), default="")       # 评论者 IP（异步回填归属地）
    region = db.Column(db.String(64), default="")   # 归属地
    device = db.Column(db.String(120), default="")  # 设备信息


class SocialAccount(db.Model):
    """作者的社交账号（广场页「我的社交账号」墙）。"""
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(40), nullable=False)   # 如 GitHub / Bilibili / 知乎 / 微博
    handle = db.Column(db.String(120), default="")         # 展示名 / @账号
    url = db.Column(db.String(300), nullable=False)
    sort = db.Column(db.Integer, default=0)                # 排序，越小越靠前


class Series(db.Model):
    """文章系列 / 专栏：多篇成系列，带上下篇导航。"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(110), unique=True, nullable=False)
    description = db.Column(db.String(400))
    cover = db.Column(db.String(500))
    sort = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Announcement(db.Model):
    """站点公告 / 置顶动态（首页顶部公告条）。"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)          # 公告内容（Markdown，渲染时清洗）
    level = db.Column(db.String(20), default="info")      # info / warning / success
    active = db.Column(db.Boolean, default=True)          # 是否启用
    dismissible = db.Column(db.Boolean, default=True)     # 访客能否关闭
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Guestbook(db.Model):
    """留言墙：独立于文章评论的短留言。"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    author = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    ip = db.Column(db.String(64), default="")
    region = db.Column(db.String(64), default="")
    device = db.Column(db.String(120), default="")
    is_read = db.Column(db.Boolean, default=False)   # 管理员是否已读（新消息提醒）


class Subscriber(db.Model):
    """邮件订阅者（Newsletter）。"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    unsub_token = db.Column(db.String(64), default="")  # 退订令牌（邮件退订链接用，一次性校验）


class Notification(db.Model):
    """站内通知：评论/动态 @ 某人时给对方生成的提醒。"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)  # 接收者
    content = db.Column(db.String(300), nullable=False)   # 通知文案（纯文本）
    link = db.Column(db.String(300), default="")          # 点击跳转地址（如 /post/xxx）
    is_read = db.Column(db.Boolean, default=False)        # 是否已读
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    """后台操作日志（审计 trail，v3.0.0 功能4）。

    记录后台关键写操作（增删改文章/评论/用户/设置等），含操作人、动作、对象、
    来源 IP，便于事后追溯与责任定位。仅超管可见、可导出、可清空（保留 90 天以上）。
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    username = db.Column(db.String(40), default="")     # 冗余存用户名，账号删除后仍可读
    action = db.Column(db.String(40), nullable=False)   # 动作类别：create/post/login/delete/...
    target = db.Column(db.String(60), default="")        # 操作对象类型：post/comment/user/setting/...
    target_id = db.Column(db.Integer, nullable=True)     # 操作对象 id
    detail = db.Column(db.String(300), default="")       # 简述，如文章标题/动作结果
    ip = db.Column(db.String(64), default="")
    success = db.Column(db.Boolean, default=True)        # 是否成功（登录失败/操作失败时为 False）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RecycleBin(db.Model):
    """回收站：被删除文章的软删除存档（v3.0.0 功能5）。

    删除文章时不真正从 post 表移除，而是把快照存入回收站，并标记原 post.in_trash=True。
    支持从回收站还原（恢复 in_trash=False）或彻底删除（真正从 post 表移除 + 删 FTS）。
    """
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, nullable=True)      # 原 post.id（彻底删除后失效）
    title = db.Column(db.String(200), default="")
    slug = db.Column(db.String(220), default="")
    summary = db.Column(db.String(400))
    content = db.Column(db.Text)
    cover = db.Column(db.String(500))
    category_id = db.Column(db.Integer, nullable=True)
    author_id = db.Column(db.Integer, nullable=True)
    series_id = db.Column(db.Integer, nullable=True)
    deleted_by = db.Column(db.String(40), default="")   # 删除操作执行者用户名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 入站时间
    restored = db.Column(db.Boolean, default=False)     # 是否已还原（避免重复还原）


class LinkApplication(db.Model):
    """友情链接自助申请（v3.0.0 功能6）。

    访客在前台提交友链申请，后台审核通过后才正式加入 FriendLink 列表；
    审核中/被拒均可查看状态。避免开放前台直接写 FriendLink 表带来的 spam 风险。
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(300), nullable=False)
    description = db.Column(db.String(200), default="")
    email = db.Column(db.String(160), default="")       # 申请人联系邮箱（可选）
    status = db.Column(db.String(16), default="pending") # pending（待审）/ approved（通过）/ rejected（拒绝）
    applicant_ip = db.Column(db.String(64), default="")
    reviewer = db.Column(db.String(40), default="")      # 审核人用户名
    review_note = db.Column(db.String(200), default="") # 审核备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)


class PostHistory(db.Model):
    """文章版本历史（v3.0.0 功能5）。

    每次保存/发布文章时，若正文或标题有变化，自动存一份快照（标题/正文/摘要/作者）。
    保留最近若干版本，支持对比与回滚（把某历史版本写回当前 post）。
    """
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    title = db.Column(db.String(200), default="")
    summary = db.Column(db.String(400))
    content = db.Column(db.Text)
    author = db.Column(db.String(40), default="")        # 编辑者用户名（冗余存，便于追溯）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.Index("ix_post_history_post", "post_id"),)


def visible_posts_query(user=None):
    """返回「对访客可见」的文章查询（已发布 且 未到定时发布时间 且 未入回收站 且 非隐私）。

    定时发布：scheduled_at 为空或 <= 当前 UTC 时间，才对外可见；未来的定时文章
    暂不对外露出（列表/详情/搜索/归档/分类/标签/系列/热门/相关都走此条件）。
    回收站：in_trash=True 的文章（v3.0.0 软删除）前台永不出现。
    隐私空间：is_private=True 的文章仅超级管理员可见（v3.0.0 功能13）。
    后台管理（dashboard/my_posts）仍用裸 Post.query，方便查看/编辑定时草稿与隐私/回收站。

    参数 user：传入当前登录用户对象时，超级管理员可见隐私文章；普通访客/未登录一律过滤隐私。
    注意：本函数只负责「可见性过滤」，排序由各调用方自行 order_by。
    置顶优先：调用方应在 order_by 最前面加 Post.is_pinned.desc()。
    """
    now = datetime.utcnow()
    q = Post.query.filter(
        Post.published == True,
        Post.in_trash == False,
        db.or_(Post.scheduled_at.is_(None), Post.scheduled_at <= now),
    )
    # 隐私文章：非超管不可见（传入 user 且为 super 才放行）
    if not (user and getattr(user, "is_super", False)):
        q = q.filter(Post.is_private == False)
    return q
