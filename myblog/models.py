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


class Subscriber(db.Model):
    """邮件订阅者（Newsletter）。"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
