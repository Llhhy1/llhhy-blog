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
import hashlib
import json
import os
import shutil
import urllib.request

from flask import (request, render_template, redirect, url_for, flash)
from sqlalchemy.exc import SQLAlchemyError

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


# LLM 送审的总字符预算。此前每文件硬砍 3000 字符，导致 dino-run 的 game.js
# （12153 字符）只送审 25% —— LLM 自己在结论里报「源码在末尾处被截断，无法完全
# 确认后续代码」，但结论仍被记成 safe（v4.4.2 R124）。现改为总预算制。
LLM_AUDIT_BUDGET = 120000

# 单个文件即便总预算充裕也不无限送审（防止单文件把预算吃光，
# 导致后面的入口 html 反而没审到 —— 入口文件才是攻击面最大的地方）。
LLM_AUDIT_PER_FILE = 40000


def _sample_code(slug, limit=LLM_AUDIT_BUDGET):
    """拼接包内 HTML/JS 用于 LLM 审计。

    v4.4.2 修复：原实现对**每个文件**硬砍 3000 字符，且累计计数加的也是
    砍后长度 → `limit` 参数永远碰不到，等于「每文件 3000」的天花板。
    恶意代码只要落在第 3001 行之后即完全逃过 LLM 审计。

    现为两级上限：单文件 ≤ LLM_AUDIT_PER_FILE，总量 ≤ limit。
    🔑 截断时**必须在送审文本里显式标注**「该文件只审了 X%」——否则
    收审方（LLM）无从知道自己看的是残片，就会把「没看到问题」误报成
    「没有问题」（这正是线上 dino-run 审计结论的原文）。

    返回 (code_text, truncated_files) —— truncated_files 用于写进结论元信息。
    """
    base = os.path.join(_root(), slug)
    if not os.path.isdir(base):
        return "", {}
    # 先收集（按文件名排序保证同一游戏每次送审内容稳定，便于对比）
    picked = []
    for f in sorted(os.listdir(base)):
        p = os.path.join(base, f)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(f)[1].lower() not in (".html", ".htm", ".js", ".mjs", ".css", ".json"):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        picked.append((f, text))
    if not picked:
        return "", {}

    # 单文件上限（带明确截断标记，头尾都保留：恶意代码常藏在文件尾）
    capped = []
    truncated = {}
    for name, text in picked:
        if len(text) > LLM_AUDIT_PER_FILE:
            cut = len(text) - LLM_AUDIT_PER_FILE
            half = LLM_AUDIT_PER_FILE // 2
            marker = f"\n\n/* …【本文件中段约 {cut} 字符因单文件上限被截断】… */\n\n"
            text = text[:half] + marker + text[-half:]
            truncated[name] = round(LLM_AUDIT_PER_FILE * 100.0 / len(text))
        capped.append((name, text))

    # 总预算：超了就按比例削减每个文件，并在文首给出覆盖率声明
    def _joined(pairs):
        return "\n".join(f"===== {n} =====\n{t}" for n, t in pairs)

    total = sum(len(t) for _n, t in capped) + len(capped) * 20
    if total > limit:
        ratio = limit / float(total)
        shrunk = []
        for name, text in capped:
            keep = max(500, int(len(text) * ratio))
            if len(text) > keep:
                half = keep // 2
                text = (text[:half] + "\n/* …【本文件中段被总量预算截断】… */\n" + text[-half:])
                truncated[name] = round(keep * 100.0 / len(text))
            shrunk.append((name, text))
        capped = shrunk
        out = _joined(capped)[:limit]
    else:
        out = _joined(capped)

    if truncated:
        lines = "".join("  - %s：约 %d%% 已送审\n" % (n, pct) for n, pct in truncated.items())
        out = ("【覆盖率声明】以下文件因长度限制只审了部分内容，"
               "未读到的部分不能视为安全：\n" + lines + "\n") + out
    return out, truncated


def _extract_json(text):
    """从 LLM 回复里抠出 JSON 对象。

    实测 openrouter 等网关会返回 ```json 围栏或前后带散文，纯 json.loads
    会整条失败 → 旧实现把整段原文当结论存库，verdict 永远解析不出来。
    这里做三级降级：直接 loads → 剥围栏 → 首个 {...} 到末个 {...}。
    失败返回 None（绝不抛，调用方据此判定 unknown）。
    """
    if not text:
        return None
    t = text.strip()
    for cand in (t, _strip_fence(t)):
        if not cand:
            continue
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            pass
    # 最后兜底：截取最外层花括号区间（注意从后往前找，避免贪婪匹配尾部噪声）
    start = t.find("{")
    if start < 0:
        return None
    end = t.rfind("}")
    if end <= start:
        return None
    try:
        obj = json.loads(t[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None


def _strip_fence(text):
    """剥掉 ```json … ``` 围栏。"""
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if len(lines) < 2:
        return ""
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


VERDICT_LABEL = {"safe": "安全", "risk": "有风险", "unknown": "无法判定"}


def _latest_verdict(g):
    """从最近一次审计结论里取 verdict。返回 (verdict, ok)。

    🔑 不新增表字段（项目纪律：能不改表就不改表），verdict 落在一行文本里，
    用固定前缀解析。老数据（v4.4.2 之前的「LLM 审计：…」原文）一律判为
    unknown —— 那批结论本来就未被解析过，当 safe 是错的。
    """
    head = (g.audit_summary or "").lstrip().split("\n", 1)[0]
    for v, label in VERDICT_LABEL.items():
        if head.startswith("LLM 审计（%s）" % label):
            return v, True
    if head.startswith("LLM 审计"):
        return "unknown", True     # 老格式：有审计但结论不可解析
    return "unknown", False        # 从未审计


def _approve_gate(g):
    """返回需要二次确认的风险说明；不需要确认时返回空串。"""
    v, has = _latest_verdict(g)
    if not has:
        return "该游戏尚未经过 LLM 代码审计（未审不等于安全，静态扫描只是辅助防线）"
    if v == "risk":
        return "LLM 审计判定为「有风险」，详见下方审计结论"
    if v == "unknown":
        return "LLM 审计无法判定（含审计失败 / 结论不可解析 / 覆盖率不足）"
    return ""


def _run_llm_audit(g):
    """OpenAI 兼容接口做代码安全审计。返回 (ok, note)。

    v4.4.2 修复三处：
    1) **失败也必须落库** —— 原实现失败时只 return，游戏行里留着上一次的
       "safe" 旧结论，失败伪装成「已审」（同一游戏重审失败即触发）。
    2) **解析 verdict** —— 原实现从不解析 JSON，risk 判定与放行完全脱钩。
    3) **记覆盖率** —— 送审若发生截断，结论里写明「只审了 X%」，
       否则「没看到问题」会被误读成「没有问题」。
    """
    verdict = "unknown"
    issues_txt = ""
    summary = ""
    try:
        if get_setting("games_llm_on", "0") != "1":
            # 未开启：不写库（保持结论不变），也不该算"审过"——
            # _latest_verdict 会把"没动过的旧结论"原样保留，这里刻意不覆盖。
            return False, "未开启"
        base = (get_setting("games_llm_base", "") or "").rstrip("/")
        # v3.17.8：兼容把完整端点填进 Base 的情况（如 .../v4/chat/completions），归一化为前缀
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        enc = get_setting("games_llm_key_enc", "") or ""
        key = decrypt_secret(enc) if enc else ""
        model = get_setting("games_llm_model", "gpt-4o-mini")
        if not (base and key and model):
            # 🔑 这里**必须**落库。v4.4.2 首版修复漏了这个出口：配置不完整时
            # 直接 return，页面继续显示上一次的 safe —— 正是本轮要修的缺陷本身
            # （首次修复被自己的测试抓回来，见 tests 里的对应用例）。
            _write_audit_result(g, "unknown", "LLM 未配置完整"
                                "（base / Key / model 三者缺一即无法审计）",
                                "", {}, raw="")
            return False, "LLM 未配置完整"
        code, truncated = _sample_code(g.slug)
        if not code:
            _write_audit_result(g, "unknown", "游戏包内没有可送审的 HTML/JS 文本文件",
                                "", {}, raw="")
            return False, "无代码可审计"
        prompt = ("请对下面的 HTML5 小游戏源码做安全审计，判断是否存在：外传用户数据、"
                  "读取 cookie/localStorage、跳转钓鱼、远程脚本/混淆、访问父窗口等恶意行为。"
                  "输出 JSON：{\"verdict\":\"safe|risk|unknown\", \"issues\":[{\"level\":\"warn|info\","
                  "\"desc\":\"…\"}], \"summary\":\"一段 100 字内中文结论\"}。"
                  "注意：源码开头若有【覆盖率声明】，说明部分文件未完整审阅，"
                  "此时若无法排除风险，verdict 必须给 unknown 而非 safe。\n\n" + code)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的浏览器游戏代码安全审计员，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        obj = _extract_json(text)
        if obj is None:
            # 解析不出来 = 无法判定，**不能**默认当 safe（旧实现正是在这里
            # 把无法解析的原文当结论，实际等于「没审但显示已审」）
            verdict = "unknown"
            summary = "LLM 回复无法解析为 JSON（原文摘录）：" + text[:800]
            ok = False
        else:
            v = str(obj.get("verdict") or "").strip().lower()
            verdict = v if v in ("safe", "risk", "unknown") else "unknown"
            summary = str(obj.get("summary") or "")[:800]
            iss = obj.get("issues")
            if isinstance(iss, list):
                parts = []
                for it in iss[:15]:
                    if isinstance(it, dict):
                        lv = str(it.get("level") or "info")
                        ds = str(it.get("desc") or "")[:200]
                        if ds:
                            parts.append("[%s] %s" % (lv, ds))
                    elif isinstance(it, str):
                        parts.append(it[:200])
                issues_txt = "\n".join(parts)
            ok = True
        _write_audit_result(g, verdict, summary, issues_txt, truncated,
                            raw=text[:1500] if obj is None else "")
        return ok, "审计完成（判定：%s）" % VERDICT_LABEL.get(verdict, "无法判定")
    except Exception as e:  # noqa: BLE001  外部服务失败形态不可枚举，统一降级为「无法判定」并落库
        # 关键：**失败也要写库**，否则页面仍显示上一次的 safe 结论
        try:
            _write_audit_result(g, "unknown", "审计失败：%s: %s" % (type(e).__name__, str(e)[:200]),
                                "", [], raw="")
        except SQLAlchemyError:
            db.session.rollback()
        return False, "审计失败：%s: %s" % (type(e).__name__, str(e)[:120])


def _write_audit_result(g, verdict, summary, issues_txt, truncated, raw=""):
    """把审计结论写入 Game 行（含 verdict / 时间 / 覆盖率）。失败回滚不抛。"""
    head = "LLM 审计（%s）：" % VERDICT_LABEL.get(verdict, "无法判定")
    # 🔑 用项目的 utcnow()，**不要 import datetime** —— 本项目有 myblog/_time.py，
    # 与标准库 datetime 同名；`import datetime` 在 myblog 包的导入序里拿到的是
    # 那个封装模块（只有 utcnow，没有 .now），首版修复就因此让写库静默失败，
    # 被 except Exception 吞掉伪装成"审计失败"。
    body = [head + " " + utcnow().strftime("%Y-%m-%d %H:%M")]
    if truncated:
        pct = "、".join("%s 约 %d%%" % (n, p) for n, p in truncated.items())
        body.append("⚠️ 覆盖率不足：" + pct + " 已送审 —— 未审到的部分不能视为安全")
    if summary:
        body.append("结论：" + summary)
    if issues_txt:
        body.append("问题清单：\n" + issues_txt)
    if raw:
        body.append("原始回复（未能解析）：\n" + raw)
    # 保留旧的历史结论，最长 8000 字（DB 是 Text，无上限但不让它无限膨胀）
    prev = g.audit_summary or ""
    g.audit_summary = ("\n\n".join(body) + ("\n\n——— 历史结论 ———\n" + prev))[:8000]
    # 🔑 verdict 落库：approve 时据此要求二次确认（见 game_action）。
    # 风险判定直接把静态分压到 0，避免「静态分 94 + verdict=risk」并列误导。
    if verdict == "risk":
        g.audit_score = 0
    db.session.commit()


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
            # v3.23.0 #48：LLM 审计单次要 120s（urlopen timeout=120），而上传路径
            # **不使用其结果**（flash 是静态文案、无论如何都跳转）——本来就是
            # fire-and-forget 语义，同步跑只会白占一个 gunicorn 并发槽。
            # 故改为后台任务；结果写回 Game 行（audit_summary / audit_score），
            # 刷新列表即可见。线程里必须**按 id 重取**：ORM 对象跨线程会 detached。
            import tasks as tasks_mod
            _gid = g.id

            def _audit_bg():
                gobj = db.session.get(Game, _gid)
                if gobj is None:
                    return "游戏已被删除，跳过审计"
                _ok, note = _run_llm_audit(gobj)
                return note

            _tid, _err = tasks_mod.submit("llm_audit", _audit_bg)
            if _err:
                flash("LLM 审计任务未能启动：" + _err)
        flash(f"已收录《{title}》待审核（静态分 {score}）")
        return redirect(url_for("admin.games"))

    games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("admin/games.html", games=games, latest_verdict=_latest_verdict,
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
        # v4.4.2：审计结论与放行耦合 —— risk / 未审计 / 审计失败时，
        # 第一次点击只渲染确认页（不落库），站长确认后才真正上架。
        # 🔑 保留站长最终裁量（不做服务端硬拦），但「无声上架」的缝补上了：
        #    风险摘要写进 admin_note + log_audit，事后可追溯是谁放行的。
        gate = _approve_gate(g)
        if gate and request.form.get("confirm_risk") != "1":
            return render_template("admin/game_confirm.html", g=g, gate=gate)
        if gate:
            g.admin_note = (gate + " ｜ 站长确认放行：" +
                            ((g.admin_note or "")[:200])).strip()[:300]
        g.status = "approved"
        g.approved_at = utcnow()
        db.session.commit()
        log_audit("approve", "game", g.id,
                  f"上架《{g.title}》" + ("（风险确认后放行）" if gate else ""), user=user)
        flash("《%s》已上架" % g.title)
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
