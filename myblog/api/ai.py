# -*- coding: utf-8 -*-
"""v3.17.0：A 内容 AI —— 文章摘要 / 标签建议（复用「游戏收录」的 OpenAI 兼容配置）。

设计：
- 配置复用既有 Setting（games_llm_on / games_llm_base / games_llm_key_enc / games_llm_model），
  无需新增密钥与表结构。
- 生成结果存 Setting（键 `ai_summary_<post_id>` / `ai_tags_<post_id>`）——零表结构变更，
  符合项目「能不改表就不改」纪律。
- GET 公开只读（供前台展示）；POST 仅超管（全局 CSRF 保护）。
- 任何 LLM/网络异常都返回可读错误，绝不 500。
"""
import json
import urllib.request

from flask import request, jsonify, session

from .common import api_bp
from models import db, Post, Setting, User
from utils import get_setting, rate_limit
from backup_settings import decrypt_secret


def _setting_get(key, default=""):
    row = Setting.query.filter_by(key=key).first()
    return row.value if row else default


def _setting_set(key, value):
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))


# v3.17.7：摘要生成提示词提取为常量（后台「AI 摘要」管理页与 API 共用，保证口径一致）
AI_SUMMARY_SYSTEM = "你是中文技术博客编辑。输出简洁准确的中文摘要，不要客套话、不要 Markdown 标记。"
AI_SUMMARY_USER_TMPL = ("请为下面这篇文章写一段 120 字以内的中文摘要；然后另起一行，以「标签建议：」开头，"
                        "给出 3-5 个中文标签（用中文逗号分隔）。\n\n标题：{title}\n\n正文：\n{content}")


def _llm_chat(system, user, timeout=90):
    """OpenAI 兼容 /chat/completions。返回 (text, err)。"""
    if get_setting("games_llm_on", "0") != "1":
        return None, "LLM 未开启（后台「游戏收录 → ⚙️ LLM 审计配置」开关）"
    base = (get_setting("games_llm_base", "") or "").rstrip("/")
    enc = get_setting("games_llm_key_enc", "") or ""
    key = decrypt_secret(enc) if enc else ""
    model = get_setting("games_llm_model", "gpt-4o-mini")
    if not (base and key and model):
        return None, "LLM 未配置完整（Base / Key / Model）"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    try:
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        return text.strip(), ""
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:140])


@api_bp.route("/ai/summary/<slug>", methods=["GET"])
def ai_summary_get(slug):
    p = Post.query.filter_by(slug=slug).first()
    if not p:
        return jsonify({"error": "文章不存在"}), 404
    return jsonify({
        "summary": _setting_get("ai_summary_%d" % p.id, ""),
        "tags": _setting_get("ai_tags_%d" % p.id, ""),
    })


@api_bp.route("/ai/summary/<slug>", methods=["POST"])
def ai_summary_make(slug):
    uid = session.get("user_id")
    u = db.session.get(User, uid) if uid else None
    if not u or not u.is_super:
        return jsonify({"error": "没有权限（仅超级管理员）"}), 403
    # 限流：每超管每小时最多 10 次生成（防误连点 / 成本失控）
    if not rate_limit("ai_summary_%s" % uid, limit=10, window=3600):
        return jsonify({"error": "生成过于频繁，请稍后再试"}), 429
    p = Post.query.filter_by(slug=slug).first()
    if not p:
        return jsonify({"error": "文章不存在"}), 404
    content = (p.content or "").strip()
    if not content:
        return jsonify({"error": "正文为空，无法生成"}), 400

    text, err = _llm_chat(AI_SUMMARY_SYSTEM,
                          AI_SUMMARY_USER_TMPL.format(title=(p.title or ""), content=content[:6000]))
    if text is None:
        return jsonify({"error": err or "生成失败"}), 502

    summary, tag_sug = text, ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("标签建议"):
            tag_sug = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
            summary = "\n".join(lines[:i]).strip()
            break
    if not summary:
        return jsonify({"error": "模型返回为空"}), 502

    _setting_set("ai_summary_%d" % p.id, summary)
    if tag_sug:
        _setting_set("ai_tags_%d" % p.id, tag_sug)
    db.session.commit()
    return jsonify({"ok": True, "summary": summary, "tags": tag_sug})
