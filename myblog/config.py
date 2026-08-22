"""博客基础配置。
部署到服务器后，请通过环境变量修改管理员密码等敏感信息，不要写死在代码里。
"""
import os

# 项目根目录（本文件所在目录）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# 数据库存放目录
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


# 应用版本号：与 GitHub Release 标签保持一致（vX.Y.Z）。
# 后台侧边栏左下角会显示该版本，用于确认服务器安装的代码是否为最新。
APP_VERSION = "2.8.0"


class Config:
    # 会话签名密钥：必须来自环境变量，缺失则拒绝启动（禁止使用任何弱默认值）。
    # 生成：python -c "import secrets;print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # SQLite 数据库文件路径。
    # 可通过环境变量 DATABASE_URL 覆盖（例如切换到 Postgres/MySQL，或本地隔离测试）：
    #   export DATABASE_URL="sqlite:///path/to/other.db"
    #   export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/blog"
    # 注意：使用非 SQLite 数据库时，FTS5 全文搜索会自动降级为 LIKE 模糊匹配。
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(DATA_DIR, "blog.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 后台管理员初始密码：必须来自环境变量，缺失则拒绝启动。
    # 首次启动后会强制在后台修改账号密码（must_change_password）。
    # 注意：不要在这里写死密码，开源后会被任何人看到。
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

    # 站点默认标题
    SITE_TITLE = "我的博客"

    # 首页每页显示的文章数量
    POSTS_PER_PAGE = 8

    # ===== 上传文件配置（写文章插图用）=====
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    # 上传图片允许的类型。注意：不包含 svg —— svg 可内嵌脚本，被直接访问时可能执行，存在 XSS 风险。
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 单文件最大 5MB

    # 站点对外地址（RSS/sitemap 生成绝对链接用，留空则自动用请求域名）
    SITE_URL = os.environ.get("SITE_URL", "")

    # 允许跨域访问的前端来源（前后端分离时，外部站点从这里调接口）。
    # 安全默认值：空字符串 = 不开启任何跨域（同源部署无需 CORS）。
    # 仅当你的前端确实部署在与后端不同的域名时，才显式填逗号分隔的来源列表，
    # 例如 "https://blog.example.com,https://www.example.com"。
    # 严禁使用 "*"（通配会允许任意网站读取接口响应、并对登录/注册做跨站调用）。
    CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "")

    # ===== 会话 Cookie 安全策略 =====
    # 生产经 HTTPS 访问时应置 true；本地纯 HTTP 开发可设 COOKIE_SECURE=false 覆盖。
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
    SESSION_COOKIE_HTTPONLY = True          # JS 不可读取会话 cookie
    SESSION_COOKIE_SAMESITE = "Lax"         # 限制跨站请求携带 cookie，缓解 CSRF

    # 是否开放公开注册（普通用户可自助注册）。设为 false 则关闭注册入口。
    BLOG_OPEN_REGISTER = os.environ.get("BLOG_OPEN_REGISTER", "true").lower() != "false"

    # ===== Webhook 自动部署（D3 · 运维）=====
    # 仅当设置了 WH_DEPLOY_SECRET 时，/api/webhook/deploy 才接受部署触发。
    # 调用方需在 Header 带 X-Deploy-Token 或在 URL 带 ?token=，与本地配置的值做
    # 恒定时间比较（hmac.compare_digest），避免时序侧信道。未配置则接口返回 403。
    WH_DEPLOY_SECRET = os.environ.get("WH_DEPLOY_SECRET")

    # ===== 新文章推送通知（D2 · 运营分发）=====
    # 以下均为可选；不配置则对应渠道自动跳过，且所有异常静默处理，不影响发文章主流程。
    # notify.py 会直接读取同名环境变量，这里在 Config 中集中声明便于部署时一处查看。
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    WECOM_WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_URL")

    # ===== 邮件群发（C3 · 新文章通知订阅者）=====
    # 使用标准库 smtplib，无需新依赖。配置 SMTP 后，新文章发布时异步群发给所有 active 订阅者（密送）。
    # 未配置 SMTP_HOST 则邮件群发自动跳过（订阅者仅收集邮箱，不发信）。
    # 退订链接用 Subscriber.unsub_token 校验，无需登录即可退订。
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # 多数邮箱用「授权码」而非登录密码
    SMTP_FROM = os.environ.get("SMTP_FROM", "")          # 发件人地址（一般等于 SMTP_USERNAME）
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "true").lower() != "false"  # 465 用 SSL，587 一般关 SSL 用 TLS

    # ===== 评论审核流 =====
    # 默认 false：评论提交后直接显示。设为 true 则评论提交后先标记 approved=False，管理员审核通过才显示。
    # 也可在后台「站点设置」里动态覆盖（setting 表 key=comment_require_approval）。
    COMMENT_REQUIRE_APPROVAL = os.environ.get("COMMENT_REQUIRE_APPROVAL", "false").lower() == "true"

    # ===== Webhook 自动部署（D3 · 真正拉取）=====
    # webhook 校验通过后，若设置了 DEPLOY_SCRIPT 路径，会异步执行该脚本（如 git pull / 解压 zip / 重启）。
    # 脚本需有执行权限；未设置则 webhook 仅返回 {"ok":true}（保持旧行为）。
    DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", "")


# 确保上传目录存在（图片保存在 static/uploads，随项目一起）
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
