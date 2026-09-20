import os
import shutil
import sys
import tempfile

# 把 myblog/ 加入 sys.path（项目无 __init__.py，靠目录直接 import 模块）。
_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS)
_MYBLOG = os.path.join(_ROOT, "myblog")
if _MYBLOG not in sys.path:
    sys.path.insert(0, _MYBLOG)

# create_app 强制要求这两个环境变量，测试用固定值（不写死到源码）。
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-plugin-system")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

# v3.18.5：测试必须跑在**独立临时库**上（本轮审计发现 P0）。
# 原先 app fixture 直接 create_app()，config.Config 的 SQLALCHEMY_DATABASE_URI
# 落到 myblog/data/blog.db → 本地 pytest 在真实开发库上建表/删数据
# （如 test_mcp_write.py 的 `Post.title.like("MCPW%").delete()`）。CI 上是新库，
# 所以长期"碰巧干净"掩盖了问题。
# 注意：Config.SQLALCHEMY_DATABASE_URI 是**类属性，模块导入时即求值**，
# 因此必须在 `import config`（即 import app）之前把 DATABASE_URL 设好。
# 用固定目录（而非每次 mkdtemp）：Windows 下 sqlite 文件句柄未释放时删不掉目录，
# 固定目录 + **下一轮开始时先清空**可保证不累积残留（最多存在一份）。
_TEST_DB_DIR = os.path.join(tempfile.gettempdir(), "llhhy-blog-pytest")
shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)   # 清掉上一轮残留（此刻尚无连接，必成功）
os.makedirs(_TEST_DB_DIR, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TEST_DB_DIR, "test.db")

import pytest  # noqa: E402
from app import create_app  # noqa: E402


_APP = None


def pytest_sessionfinish(session, exitstatus):
    """跑完删掉临时库目录，不在仓库/临时目录留任何测试残留。

    Windows 下 sqlite 文件被进程占用时会被拒绝删除，所以先显式释放连接再删。
    """
    try:
        if _APP is not None:
            from models import db
            with _APP.app_context():
                db.session.remove()
                for engine in list(db.engines.values()):
                    engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture
def app():
    # enable_scheduler=False：关掉定时发布守护线程。
    # 原实现每次 create_app() 都起一个线程，99 个测试最多 99 个后台线程。
    global _APP
    _APP = create_app(enable_scheduler=False)
    return _APP


@pytest.fixture
def client(app):
    return app.test_client()
