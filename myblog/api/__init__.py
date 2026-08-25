"""llhhy-blog API 包（v3.6.0 起：按功能解耦的单文件 → 包结构）。

原 myblog/api.py 拆分为本包：
- common.py     共享辅助（序列化、登录会话、CSRF、可见性判断、限流）与蓝图定义
- auth.py       认证 / 注册 / 登录 / 验证码
- site.py       站点信息 / 友链 / 公告
- posts.py      文章 / 分类 / 标签 / RSS / 归档 / 点赞 / 评论 / 搜索
- stats.py      访问统计
- social.py     朋友圈 / 社交账号
- series.py     系列
- guestbook.py  留言板
- subscribe.py  订阅
- notifications.py 通知
- system.py     版本自检 / 在线更新 / webhook 部署

设计约束：功能模块只从 .common 取共享符号，模块间不互相 import；
本文件的导入顺序即蓝图的注册顺序（不影响路由匹配，Flask 按 rule 匹配）。
"""
from . import auth          # 认证 / 验证码（注册 登录 登出 当前用户 CSRF 验证码）
from . import site          # 站点信息 友链申请 公告
from . import posts         # 文章 分类 标签 RSS 归档 点赞 评论 相关 搜索 定时发布
from . import stats         # 访问统计(visit/search/read/summary/trend)
from . import social        # 朋友圈 动态 点赞 评论 社交账号
from . import series        # 系列列表 系列详情
from . import guestbook     # 留言板 留言点赞
from . import subscribe     # 订阅 退订
from . import notifications # 通知列表 已读 全部已读
from . import system        # 版本检查 在线更新 webhook 部署

# 蓝图唯一出处（功能模块从 .common 取，app.py 从本包取，二者同一对象）
from .common import api_bp