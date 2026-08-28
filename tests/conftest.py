import os
import sys

# 把 myblog/ 加入 sys.path（项目无 __init__.py，靠目录直接 import 模块）。
_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS)
_MYBLOG = os.path.join(_ROOT, "myblog")
if _MYBLOG not in sys.path:
    sys.path.insert(0, _MYBLOG)

# create_app 强制要求这两个环境变量，测试用固定值（不写死到源码）。
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-plugin-system")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

import pytest
from app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()
