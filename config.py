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
    # 会话签名密钥，生产环境务必改成随机长字符串（可用环境变量传入）
    SECRET_KEY = os.environ.get("SECRET_KEY", "please-change-this-secret-key")

    # SQLite 数据库文件路径
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(DATA_DIR, "blog.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 后台管理员账号（可用环境变量覆盖）
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # 站点默认标题
    SITE_TITLE = "我的博客"

    # 首页每页显示的文章数量
    POSTS_PER_PAGE = 8

    # ===== 上传文件配置（写文章插图用）=====
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 单文件最大 5MB
    # 站点对外地址（RSS/sitemap 生成绝对链接用，留空则自动用请求域名）
    SITE_URL = os.environ.get("SITE_URL", "")

    # 允许跨域访问的前端来源（前后端分离时，Astro 站点从这里调接口）。
    # 开发/测试用 "*" 即可；生产建议改成你的前端域名，如 "https://blog.example.com"
    CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")


# 确保上传目录存在（图片保存在 static/uploads，随项目一起）
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
