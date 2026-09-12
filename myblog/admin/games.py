# -*- coding: utf-8 -*-
"""游戏平台后台收录（v3.15.0）。

流程：上传 zip → 安全解包（防穿越/大小/扩展名白名单）→ manifest 校验 →
静态可疑扫描（记分）→ 落盘为 pending → （可选）大模型 LLM 代码审计 →
站长审核通过后前台沙箱内可播放。

安全红线：
- zip 内容解包严格白名单（见 games_safety）；所有文本文件先静态扫描；
- LLM 审计接口为 OpenAI 兼容 /chat/completions，Key 用 encrypt_secret 加密落库，
  页面只回显掩码；一切写操作 log_audit；
- 收录目录 <myblog>/data/games/<slug>，删除即整目录移除。
"""
import datetime
import hashlib
import json
import os
import shutil
import urllib.request

from flask import (request, render_template, redirect, url_for, flash, current_app)

from models import db, Game
import games_safety
from utils import get_setting
from backup_settings import encrypt_secret, decrypt_secret
from ._helpers import (admin_bp, admin_required, log_audit, _current_user_or_none,
                       unique_model_slug)
from _time import utcnow


def _root():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "games")


def _sample_code(slug, limit=60000):
    """拼接包内 HTML/JS 用于 LLM 审计（控制体量）。"""
    base = os.path.join(_root(), slug)
    chunks = []
    total = 0
    for f in sorted(os.listdir(base)):
        p = os.path.join(base, f)
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in (".html", ".htm", ".js", ".mjs", ".css", ".json"):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except Exception:
            continue
        chunks.append(f"===== {f} =====\n" + text[:3000])
        total += min(len(text), 3000)
        if total > limit:
            break
    return "\n".join(chunks)[:limit]


def _run_llm_audit(g):
    """OpenAI 兼容接口做代码安全审计。返回 (ok, note)。未配置/失败返回 (False, 原因)。"""
    if get_setting("games_llm_on", "0") != "1":
        return False, "未开启"
    base = (get_setting("games_llm_base", "") or "").rstrip("/")
    # v3.17.8：兼容把完整端点填进 Base 的情况（如 .../v4/chat/completions），归一化为前缀
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    enc = get_setting("games_llm_key_enc", "") or ""
    key = decrypt_secret(enc) if enc else ""
    model = get_setting("games_llm_model", "gpt-4o-mini")
    if not (base and key and model):
        return False, "LLM 未配置完整"
    code = _sample_code(g.slug)
    if not code:
        return False, "无代码可审计"
    prompt = ("请对下面的 HTML5 小游戏源码做安全审计，判断是否存在：外传用户数据、"
              "读取 cookie/localStorage、跳转钓鱼、远程脚本/混淆、访问父窗口等恶意行为。"
              "输出 JSON：{\"verdict\":\"safe|risk|unknown\", \"issues\":[{\"level\":\"warn|info\","
              "\"desc\":\"…\"}], \"summary\":\"一段 100 字内中文结论\"}。\n\n" + code)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的浏览器游戏代码安全审计员，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    try:
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        g.audit_summary = "LLM 审计：\n" + text[:3000]
        db.session.commit()
        return True, "审计完成"
    except Exception as e:
        return False, f"审计失败：{type(e).__name__}: {str(e)[:120]}"


@admin_bp.route("/games", methods=["GET", "POST"])
@admin_required
def games():
    if request.method == "POST":
        zf = request.files.get("game_zip")
        if not zf or not zf.filename:
            flash("请选择游戏 zip 文件")
            return redirect(url_for("admin.games"))
        raw = zf.read()
        try:
            files = games_safety.unpack_zip_safely(raw)
            man = games_safety.find_manifest(files)
            if man is None:
                raise ValueError("包内缺少 manifest.json")
            ok, errs = games_safety.validate_manifest(man)
            if not ok:
                raise ValueError("manifest 校验失败：" + "；".join(errs))
            entry = man["entry"].strip()
            if entry not in {f["name"] for f in files}:
                raise ValueError(f"入口 {entry} 不在包内")
            findings, score = games_safety.scan_game_files(files)
        except ValueError as e:
            flash("上传失败：" + str(e))
            return redirect(url_for("admin.games"))

        title = (man.get("name") or "").strip()[:120] or "未命名游戏"
        slug = unique_model_slug(Game, man.get("slug") or title or "game", max_len=90)
        d = os.path.join(_root(), slug)
        os.makedirs(d, exist_ok=True)
        for f in files:
            full = os.path.join(d, f["name"].replace("/", os.sep))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(f["data"])
        summary_lines = [f"{x['level']}|{x['rule']}|{x['file']}|{x['note']}" for x in findings]
        g = Game(
            slug=slug, title=title,
            description=(man.get("description") or "")[:4000],
            cover=(man.get("cover") or "")[:500],
            entry=entry, author=(man.get("author") or "")[:80],
            version=(man.get("version") or "1.0")[:30],
            status="pending",
            package_hash=hashlib.sha256(raw).hexdigest(),
            size=sum(len(x["data"]) for x in files),
            file_count=len(files),
            audit_score=score,
            audit_summary="静态扫描发现 "
                          + (f"{len(findings)} 项：\n" + "\n".join(summary_lines[:60])
                             if findings else "未见明显可疑特征"),
        )
        db.session.add(g)
        db.session.commit()
        log_audit("create", "game", g.id, f"上传收录《{title}》", user=_current_user_or_none())
        if get_setting("games_llm_on", "0") == "1":
            _run_llm_audit(g)
        flash(f"已收录《{title}》待审核（静态分 {score}）")
        return redirect(url_for("admin.games"))

    games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("admin/games.html", games=games,
                           llm_on=get_setting("games_llm_on", "0") == "1")


@admin_bp.route("/game/<int:gid>/action", methods=["POST"])
@admin_required
def game_action(gid):
    g = db.session.get(Game, gid)
    if not g:
        flash("游戏不存在")
        return redirect(url_for("admin.games"))
    action = request.form.get("action") or ""
    user = _current_user_or_none()
    if action == "approve":
        g.status = "approved"
        g.approved_at = utcnow()
        db.session.commit()
        log_audit("approve", "game", g.id, f"上架《{g.title}》", user=user)
        flash(f"《{g.title}》已上架")
    elif action == "reject":
        g.status = "rejected"
        g.admin_note = (request.form.get("note") or "")[:300]
        db.session.commit()
        log_audit("reject", "game", g.id, "驳回", user=user)
        flash("已驳回")
    elif action == "remove":
        g.status = "removed"
        db.session.commit()
        log_audit("remove", "game", g.id, "下架", user=user)
        flash("已下架")
    elif action == "audit":
        ok, note = _run_llm_audit(g)
        flash(f"LLM 审计：{note}")
        log_audit("audit", "game", g.id, note, user=user)
    elif action == "delete":
        d = os.path.join(_root(), g.slug)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        db.session.delete(g)
        db.session.commit()
        log_audit("delete", "game", g.id, f"删除《{g.title}》", user=user)
        flash("已删除")
    return redirect(url_for("admin.games"))


@admin_bp.route("/games/llm-config", methods=["GET", "POST"])
@admin_required
def games_llm_config():
    def _set(k, v):
        from models import Setting
        s = Setting.query.filter_by(key=k).first()
        if s:
            s.value = v
        else:
            db.session.add(Setting(key=k, value=v))

    if request.method == "POST":
        _set("games_llm_on", "1" if request.form.get("on") == "1" else "0")
        _set("games_llm_base", (request.form.get("base") or "").strip())
        _set("games_llm_model", (request.form.get("model") or "").strip())
        new_key = (request.form.get("key") or "").strip()
        if new_key:
            _set("games_llm_key_enc", encrypt_secret(new_key))
        db.session.commit()
        log_audit("update", "setting", 0, "游戏 LLM 审计配置", user=_current_user_or_none())
        flash("已保存（Key 已加密存储）")
        return redirect(url_for("admin.games_llm_config"))
    return render_template(
        "admin/games_llm_config.html",
        on=get_setting("games_llm_on", "0"),
        base=get_setting("games_llm_base", ""),
        model=get_setting("games_llm_model", "gpt-4o-mini"),
        key_masked="••••••" if get_setting("games_llm_key_enc", "") else "",
    )
