# -*- coding: utf-8 -*-
"""后台「外部入口」管理（v4.1.0）。

为什么从「站点设置」里独立成一页
--------------------------------
v4.0.0 时入口只有一个，塞在站点设置的一节里是合适的。
变成多个之后就不成立了：列表、排序、启停、删除都需要独立的页面结构，
而站点设置是一张**整体提交**的大表单 —— 在一张大表单里放「删除第 3 条」这种
局部写操作，语义是拧的（提交表单 ≠ 只删一条）。

安全
----
每条 URL 都必须过 ``utils.is_http_url``：这是前台 ``:href`` 的直接来源，
``javascript:`` 之类 scheme = 存储型 XSS。
**一条填错只丢弃这一条**，同批次的其它编辑照常生效 —— 与 ``site_url`` 同一取舍：
一个字段填错不该让人丢掉整张表单的输入（v4.0.0 已确立的口径）。
"""

import config_rollback as cr
import nav_entries as ne
from flask import flash, redirect, render_template, request, url_for
from utils import is_http_url

from ._helpers import admin_bp, admin_required, log_audit

_LABEL_MAX = 20
_ICON_MAX = 8


def _snapshot(reason):
    """改之前拍快照（失败不影响主流程，同 settings.py 的取舍）。"""
    try:
        return cr.snapshot_settings([ne.KEY], reason=reason)
    except Exception:      # noqa: BLE001  快照失败不该阻断管理操作
        return None


@admin_bp.route("/nav-entries")
@admin_required
def nav_entries():
    items = ne.load()
    return render_template("admin/nav_entries.html",
                           items=items, max_items=ne.MAX_ITEMS)


@admin_bp.route("/nav-entries/add", methods=["POST"])
@admin_required
def nav_entry_add():
    label = (request.form.get("label") or "").strip()[:_LABEL_MAX]
    url = (request.form.get("url") or "").strip()
    icon = (request.form.get("icon") or "").strip()[:_ICON_MAX]

    # 标签缺失就补默认：地址合法而名称为空的条目，前台会渲染成一个空按钮，
    # 看起来像坏了。宁可给个兜底名字。
    if not label:
        label = "工具"

    if not is_http_url(url):
        flash("入口地址必须以 http:// 或 https:// 开头（不接受 javascript: 等其它协议），"
              "该条未添加。", "warning")
        return redirect(url_for("admin.nav_entries"))

    items = ne.load()
    if len(items) >= ne.MAX_ITEMS:
        flash("入口数量已达上限 %d 条（再多导航栏会横向溢出），请先删掉不用的。" % ne.MAX_ITEMS,
              "warning")
        return redirect(url_for("admin.nav_entries"))

    _snapshot("新增外部入口")
    items.append({"id": ne.new_id(), "label": label, "url": url,
                  "icon": icon, "enabled": True})
    ne.save(items)
    log_audit("add", "nav_entry", None, "新增外部入口：%s → %s" % (label, url))
    flash("已添加入口：%s" % label)
    return redirect(url_for("admin.nav_entries"))


@admin_bp.route("/nav-entries/<item_id>/edit", methods=["POST"])
@admin_required
def nav_entry_edit(item_id):
    items = ne.load()
    hit = next((x for x in items if x["id"] == item_id), None)
    if not hit:
        flash("该入口不存在（可能已被删除）。", "warning")
        return redirect(url_for("admin.nav_entries"))

    label = (request.form.get("label") or "").strip()[:_LABEL_MAX]
    icon = (request.form.get("icon") or "").strip()[:_ICON_MAX]
    raw_url = (request.form.get("url") or "").strip()

    if not label:
        label = hit["label"] or "工具"

    # 地址非法 → **保留旧地址**并提示，名称/图标照常保存。
    # 「一个字段填错不该丢掉整张表单」—— 否则管理员辛辛苦苦改好的名字也会一起没。
    url_bad = bool(raw_url) and not is_http_url(raw_url)

    _snapshot("编辑外部入口")
    hit["label"] = label
    hit["icon"] = icon
    if not url_bad:
        hit["url"] = raw_url
    ne.save(items)

    if url_bad:
        flash("地址未保存（必须是 http/https 开头），名称与图标已更新。", "warning")
    else:
        flash("已保存：%s" % label)
    log_audit("edit", "nav_entry", item_id, "编辑外部入口：%s" % label)
    return redirect(url_for("admin.nav_entries"))


@admin_bp.route("/nav-entries/<item_id>/delete", methods=["POST"])
@admin_required
def nav_entry_delete(item_id):
    items = ne.load()
    left = [x for x in items if x["id"] != item_id]
    if len(left) == len(items):
        flash("该入口不存在（可能已被删除）。", "warning")
        return redirect(url_for("admin.nav_entries"))
    _snapshot("删除外部入口")
    ne.save(left)
    log_audit("delete", "nav_entry", item_id, "删除外部入口")
    flash("已删除该入口")
    return redirect(url_for("admin.nav_entries"))


@admin_bp.route("/nav-entries/<item_id>/toggle", methods=["POST"])
@admin_required
def nav_entry_toggle(item_id):
    items = ne.load()
    hit = next((x for x in items if x["id"] == item_id), None)
    if not hit:
        flash("该入口不存在（可能已被删除）。", "warning")
        return redirect(url_for("admin.nav_entries"))
    _snapshot("切换外部入口启停")
    hit["enabled"] = not hit["enabled"]
    ne.save(items)
    log_audit("toggle", "nav_entry", item_id,
              "入口已%s：%s" % ("启用" if hit["enabled"] else "停用", hit.get("label", "")))
    flash("已%s：%s" % ("启用" if hit["enabled"] else "停用", hit.get("label", "")))
    return redirect(url_for("admin.nav_entries"))


@admin_bp.route("/nav-entries/<item_id>/move", methods=["POST"])
@admin_required
def nav_entry_move(item_id):
    """上/下移动一条（决定导航栏里的先后顺序）。"""
    direction = (request.args.get("dir") or request.form.get("dir") or "").strip()
    if direction not in ("up", "down"):
        flash("移动方向不正确。", "warning")
        return redirect(url_for("admin.nav_entries"))

    items = ne.load()
    idx = next((i for i, x in enumerate(items) if x["id"] == item_id), None)
    if idx is None:
        flash("该入口不存在（可能已被删除）。", "warning")
        return redirect(url_for("admin.nav_entries"))

    target = idx - 1 if direction == "up" else idx + 1
    if target < 0 or target >= len(items):
        return redirect(url_for("admin.nav_entries"))   # 已在端点，静默不动

    _snapshot("调整外部入口顺序")
    items[idx], items[target] = items[target], items[idx]
    ne.save(items)
    return redirect(url_for("admin.nav_entries"))
