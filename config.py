"""博客基础配置。
部署到服务器后，请通过环境变量修改管理员密码等敏感信息，不要写死在代码里。
"""
import os

# 项目根目录（本文件所在目录）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# 数据库存放目录
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


class Config:
    # 会话签名密钥：必须来自环境变量，缺失则拒绝启动（禁止使用任何弱默认值）。
    # 生成：python -c "import secrets;print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # SQLite 数据库文件路径
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(DATA_DIR, "blog.db")
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


# 确保上传目录存在（图片保存在 static/uploads，随项目一起）
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
