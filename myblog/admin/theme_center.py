# -*- coding: utf-8 -*-
# 主题中心后台页（v3.16.0）：仅超管可进入；实际「应用」走 /api/theme（AJAX + CSRF）。
from ._helpers import super_required, admin_bp     # admin_bp = 同一蓝图对象
from flask import render_template
from themes import THEME_PRESETS, current_theme


@admin_bp.route("/theme-center")
@super_required
def theme_center():
    # v4.7.4：把媒体库清单一并传进模板 —— 壁纸可以直接「从媒体库选」，
    # 不用每次重新上传同一张图。清单由 `collect_media()` 统一产出
    # （与媒体库页、移动端媒体 API 同一实现，不会出现两套口径）。
    from .media import collect_media
    return render_template("admin/theme_center.html",
                           presets=THEME_PRESETS, current=current_theme(),
                           media=collect_media())
