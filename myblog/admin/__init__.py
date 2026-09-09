# -*- coding: utf-8 -*-
"""admin 蓝图包（v3.11.0 由单文件 admin.py 拆出，按业务域模块化；路由 URL/行为零变更）。"""
from ._helpers import *   # 等价于原 admin.py 顶层命名空间（admin_bp / 辅助函数 / 装饰器）
from . import auth
from . import comments
from . import posts
from . import settings
from . import users
from . import stats
from . import media
from . import friends
from . import misc
from . import moments   # v3.12.0：微动态（广场/个人动态）后台管理
from . import mcp_services  # v3.13.0：MCP 服务管理面板（内置启停/外部登记/AI 接入指令）
from . import games        # v3.15.0：游戏平台（收录/审核/LLM 审计）
from . import theme_center  # v3.16.0：主题中心（预设包 + 实时预览 + 自定义导入/导出）

