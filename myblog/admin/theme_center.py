# -*- coding: utf-8 -*-
# 主题中心后台页（v3.16.0）：仅超管可进入；实际「应用」走 /api/theme（AJAX + CSRF）。
from . import admin_bp
from ._helpers import super_required
from flask import render_template
from themes import THEME_PRESETS, current_theme


@admin_bp.route("/theme-center")
@super_required
def theme_center():
    return render_template("admin/theme_center.html",
                           presets=THEME_PRESETS, current=current_theme())
