# -*- coding: utf-8 -*-
"""v3.17.7：AI 摘要管理页（后台独立页面）。

- 列出全部已发布文章的摘要状态；单篇生成 / 重新生成 / 手动编辑 / 清除；批量补齐（限 3 篇/次，防请求超时）。
- LLM 复用「游戏收录」的 OpenAI 兼容配置（games_llm_*），本页只读展示状态；提示词与 API 共用同一常量。
- 摘要仍存 Setting KV（ai_summary_<id> / ai_tags_<id>），前台展示逻辑不变、零表结构变更。
- 全部写操作 admin_required + log_audit。
"""
from flask import request, render_template, redirect, url_for, flash

from models import db, Post, Setting
from utils import get_setting
from ._helpers import admin_bp, admin_required, log_audit, _current_user_or_none
from api.ai import _llm_chat, _setting_get, _setting_set, AI_SUMMARY_SYSTEM, AI_SUMMARY_USER_TMPL


def _summary_of(pid):
    return _setting_get("ai_summary_%d" % pid, "")


def _tags_of(pid):
    return _setting_get("ai_tags_%d" % pid, "")


def _generate_for(post):
    """为单篇文章生成摘要（含标签建议）；返回 (ok, msg)。"""
    content = (post.content or "").strip()
    if not content:
        return False, "正文为空，无法生成"
    text, err = _llm_chat(AI_SUMMARY_SYSTEM,
                          AI_SUMMARY_USER_TMPL.format(title=(post.title or ""), content=content[:6000]))
    if text is None:
        return False, err or "生成失败"
    summary, tag_sug = text, ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("标签建议"):
            tag_sug = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
            summary = "\n".join(lines[:i]).strip()
            break
    if not summary:
        return False, "模型返回为空"
    _setting_set("ai_summary_%d" % post.id, summary)
    if tag_sug:
        _setting_set("ai_tags_%d" % post.id, tag_sug)
    return True, summary


@admin_bp.route("/ai-summary")
@admin_required
def ai_summary():
    posts = Post.query.filter_by(published=True).order_by(Post.id.desc()).all()
    rows = [{"p": p, "summary": _summary_of(p.id), "tags": _tags_of(p.id)} for p in posts]
    llm = {
        "on": get_setting("games_llm_on", "0") == "1",
        "base": (get_setting("games_llm_base", "") or "").rstrip("/"),
        "model": get_setting("games_llm_model", "") or "",
        "has_key": bool(get_setting("games_llm_key_enc", "")),
    }
    covered = sum(1 for r in rows if r["summary"])
    return render_template("admin/ai_summary.html", rows=rows, llm=llm,
                           total=len(rows), covered=covered)


@admin_bp.route("/ai-summary/generate/<int:post_id>", methods=["POST"])
@admin_required
def ai_summary_generate(post_id):
    p = db.session.get(Post, post_id)
    if not p:
        flash("文章不存在")
        return redirect(url_for("admin.ai_summary"))
    ok, msg = _generate_for(p)
    log_audit("generate" if ok else "generate_fail", "post", post_id,
              ("AI 摘要生成成功：%s" % msg[:80]) if ok else ("AI 摘要生成失败：%s" % msg[:120]),
              user=_current_user_or_none(), success=ok)
    flash("✅ 已生成摘要" if ok else ("⚠️ 生成失败：" + msg))
    return redirect(url_for("admin.ai_summary"))


@admin_bp.route("/ai-summary/batch", methods=["POST"])
@admin_required
def ai_summary_batch():
    """批量补齐：每次最多 3 篇（LLM 同步调用，防请求超时）；多次点击直至全覆盖。"""
    posts = Post.query.filter_by(published=True).order_by(Post.id.desc()).all()
    done, fail = 0, 0
    for p in posts:
        if done >= 3:
            break
        if _summary_of(p.id):
            continue
        ok, msg = _generate_for(p)
        log_audit("batch_generate" if ok else "batch_generate_fail", "post", p.id,
                  ("批量生成成功" if ok else "批量生成失败：%s" % msg[:100]),
                  user=_current_user_or_none(), success=ok)
        if ok:
            done += 1
        else:
            fail += 1
    remain = sum(1 for p in posts if not _summary_of(p.id))
    flash("批量完成：本次生成 %d 篇%s；%s" % (
        done, ("，失败 %d 篇" % fail) if fail else "",
        ("仍有 %d 篇未覆盖，可继续点击" % remain) if remain else "已全部覆盖"))
    return redirect(url_for("admin.ai_summary"))


@admin_bp.route("/ai-summary/save/<int:post_id>", methods=["POST"])
@admin_required
def ai_summary_save(post_id):
    text = (request.form.get("summary") or "").strip()
    tags = (request.form.get("tags") or "").strip()
    if text:
        _setting_set("ai_summary_%d" % post_id, text)
    if tags:
        _setting_set("ai_tags_%d" % post_id, tags)
    log_audit("save", "post", post_id, "手动保存 AI 摘要", user=_current_user_or_none())
    flash("已保存")
    return redirect(url_for("admin.ai_summary"))


@admin_bp.route("/ai-summary/clear/<int:post_id>", methods=["POST"])
@admin_required
def ai_summary_clear(post_id):
    n = 0
    for k in ("ai_summary_%d" % post_id, "ai_tags_%d" % post_id):
        row = Setting.query.filter_by(key=k).first()
        if row:
            db.session.delete(row)
            n += 1
    db.session.commit()
    log_audit("clear", "post", post_id, "清除 AI 摘要", user=_current_user_or_none())
    flash("已清除")
    return redirect(url_for("admin.ai_summary"))
