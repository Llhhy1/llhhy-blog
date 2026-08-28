"""文章目录（TOC）侧栏插件（v3.9.0 · 首个真实插件）。

定位：弥补核心 PostView 内联 TOC（仅在文首、滚动后即消失）的不足，提供
「常驻右侧栏 + 滚动高亮当前章节」的目录侧栏，提升长文阅读体验。

实现方式（M3 远程组件，纯前端）：
- 本模块只声明一个 remote_components（widget.js），不建表、不注册蓝图、不写 API。
- widget.js 由前端经 /api/plugins 的 remote_components 白名单加载（仅同源
  /static/plugins/ 前缀），属「自写/审计过的插件」信任级别。
- widget.js 扫描文章正文 .post-body 的 h2/h3/h4，生成 sticky 目录注入文章页
  右侧 Sidebar 顶部；随滚动高亮当前章节、点击平滑滚动；SPA 路由切换自动重建。

与核心零耦合：不修改 PostView / App.vue / Sidebar；核心内联 TOC 仍保留（窄屏
无侧栏 TOC 时兜底）。
"""
from flask import Blueprint


# 插件自有蓝图（如需后续加「目录深度 / 是否显示」等设置可在此扩展；当前无需）。
bp = Blueprint("plugin_article_toc", __name__, url_prefix="/api/plugin/article_toc")


def register(app, cfg):
    # 幂等注册：运行时重载（set_plugin_enabled/reload）可能再次调用 register，
    # 蓝图已存在则跳过，避免 Flask 抛出「重复注册」异常。当前无路由，仅为保留扩展点。
    if bp.name not in app.blueprints:
        try:
            app.register_blueprint(bp)
        except Exception as e:
            print(f"[article_toc] 蓝图注册跳过：{e}")
    return {
        "name": "文章目录侧栏",
        "version": "1.0.0",
        "author": "Llhhy",
        "description": "文章页右侧常驻目录侧栏（sticky + 滚动高亮当前章节），扫描正文 h2/h3/h4 自动生成，窄屏自动隐藏。",
        "slots": [],
        "remote_components": [
            {"name": "article_toc_widget", "url": "/static/plugins/article_toc/widget.js"}
        ],
    }
