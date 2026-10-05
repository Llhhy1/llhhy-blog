# -*- coding: utf-8 -*-
"""admin 蓝图包（v3.11.0 由单文件 admin.py 拆出，按业务域模块化；路由 URL/行为零变更）。

下面的 `from . import <模块>` 是**副作用导入**：各子模块在被导入时向 admin_bp 注册
路由。ruff 会把它们报成 F401（「未使用」），但删掉任何一行 = 该模块的全部后台路由
消失。v3.24.0 起子模块已改为显式导入，不再依赖本文件的星号转发。
"""
# ruff: noqa: F401  —— 副作用注册路由 + 包命名空间 re-export（见上），非死导入
from ._helpers import admin_bp   # app.py 依赖 admin.admin_bp 是同一个蓝图对象
# v3.25.0：**不再** re-export log_audit / log_login_attempt。
# 原先 re-export 是为了 api/common.py、routes.py、api/theme.py 三处外部按名导入；
# 审计写入搬到顶层 `audit.py` 后，这三处都改成 `from audit import ...`，
# 消费面归零 → 按「re-export 面必须等于真实消费面」的纪律一并撤掉。
# 包内 22 个子模块走的是 `from ._helpers import ...`（转发层），不依赖本行。
from . import auth
from . import comments
from . import post_editor   # v3.18.1：posts.py 拆分 → 写作面板（新建/编辑/自动保存/预览）
from . import post_manage   # v3.18.1：文章管理（列表/批量/发布/置顶/软删除）
from . import post_trash    # v3.18.1：回收站（列出/还原/彻底清除）
from . import post_history  # v3.18.1：版本历史（列表/回滚/对比）
from . import taxonomy      # v3.18.1：分类/标签/系列治理
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
from . import ai_summary   # v3.17.7：AI 摘要管理（列表/生成/编辑/清除/批量补齐）
from . import seo          # v3.19.0：收录控制台（主动推送 + 通道自检 + sitemap/robots 预览）
from . import twofa        # v3.21.0：两步验证 2FA（注册路由用，非按名引用）
from . import oauth_bindings  # 第三方账号绑定列表/解绑（R94 §94.8-7 可发现性缺口）
from . import oauth_settings  # v3.25.7：第三方登录凭据配置（此前只有 env 入口，功能从未启用）
from . import system_settings  # v3.25.8：运营开关集中配置（此前 2FA 等只能改服务器 + 重启）

