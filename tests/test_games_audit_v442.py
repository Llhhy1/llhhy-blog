# -*- coding: utf-8 -*-
"""游戏审计修复的回归测试（v4.4.2 · R124）。

修的四个缺陷（均为「审计结论与实际安全状态脱钩」）：
1. `_sample_code` 每文件硬砍 3000 字符 → dino-run 只送审 25%，
   LLM 自己报「源码被截断」但结论仍记为 safe；
2. LLM 的 verdict 从未被解析 → 判 risk 也能无声上架；
3. 审计失败不落库 → 页面继续显示上一次的 safe（失败伪装成已审）；
4. approve 不看审计结论 → 无声上架无留痕。

每条守卫都写成**反向可证伪**形式：把修复摘掉必须变红。
"""
import contextlib
import json
import os
import sys
import urllib.error

import pytest

_MY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "myblog")
if _MY not in sys.path:
    sys.path.insert(0, _MY)

from models import db, Game, User, Setting, ROLE_SUPER, ROLE_ADMIN  # noqa: E402
import games_safety  # noqa: E402
from admin import games as ag  # noqa: E402


def _tok():
    import secrets
    return secrets.token_hex(6)


@pytest.fixture
def app_ctx(app):
    """每个用例独占干净数据（测试库全 session 共享的教训：别跨用例假设基线）。

    🔑 清库必须在 app_context 内 —— ORM 查询脱离上下文直接抛
    RuntimeError（不是"读不到"，是根本没绑上下文）。
    """
    def _wipe():
        with app.app_context():
            for m in (Game, Setting, User):
                m.query.delete()
            db.session.commit()
    _wipe()
    yield app
    _wipe()


def _mkuser(app, role):
    """真实建用户并返回 (id, 用户名, 密码)。

    🔑 必须走真登录（POST /api/auth/login）而不是往 session 里塞 uid：
    session 键名/登录态字段一旦与实现漂移，测试会静默变成"未登录"
    （表现为断言落在 login 重定向页上，很难看出是登录失败）。
    样板照抄 tests/test_system_settings.py。
    """
    import secrets as _s
    uname = "gu" + _s.token_hex(5)
    pwd = "Passw0rd!23"
    with app.app_context():
        u = User(username=uname, email=uname + "@example.com",
                 role=role, must_change_password=False)
        u.set_password(pwd)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    return uid, uname, pwd


def _do_login(client, uname, pwd):
    d = client.get("/api/csrf").get_json() or {}
    r = client.post("/api/auth/login", json={"username": uname, "password": pwd},
                    headers={"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""})
    assert r.status_code == 200, "登录失败（后台页会跳 login 而非 403，容易误判成路由问题）"


def _super_client(app, client):
    _uid, uname, pwd = _mkuser(app, ROLE_SUPER)
    _do_login(client, uname, pwd)
    return client


def _csrf(client):
    d = client.get("/api/csrf").get_json() or {}
    return {"X-CSRF-Token": d.get("csrf_token") or d.get("token") or ""}


def _mk_game(app, slug, summary="", score=100, status="pending"):
    """建一个真实落盘的游戏目录 + DB 行（_sample_code 只认磁盘上的文件）。"""
    gdir = os.path.join(ag._root(), slug)
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>t</title><script>ok()</script>")
    with app.app_context():
        g = Game(slug=slug, title="G-" + slug, entry="index.html", status=status,
                 version="1.0", audit_score=score, audit_summary=summary)
        db.session.add(g)
        db.session.commit()
        return g.id


def _cleanup_dirs(*slugs):
    import shutil
    for s in slugs:
        with contextlib.suppress(OSError):
            shutil.rmtree(os.path.join(ag._root(), s), ignore_errors=True)


# ---------- 缺陷 1：送审代码被截断 ----------

def test_sample_code_sends_full_small_file_not_3000(app, app_ctx):
    """回归：dino-run 的 game.js 是 12153 字符，旧实现只送 3000（丢 75%）。"""
    slug = "audit-full-" + _tok()
    try:
        gdir = os.path.join(ag._root(), slug)
        os.makedirs(gdir, exist_ok=True)
        body = "\n".join("var line%d = %d;" % (i, i) for i in range(800))  # ~1.4 万字符
        with open(os.path.join(gdir, "game.js"), "w", encoding="utf-8") as fh:
            fh.write(body)
        assert len(body) > 5000
        with app.app_context():
            code, trunc = ag._sample_code(slug)
        # 全文必须在（尾部同样要审 —— 恶意代码常藏在文件尾）
        assert "var line799" in code, "文件尾部未被送审，截断漏洞仍在"
        assert "var line0" in code
        assert not trunc, "1.4 万字符不应触发截断标记"
    finally:
        _cleanup_dirs(slug)


def test_sample_code_marks_truncation_when_over_budget(app, app_ctx):
    """超过总预算时必须显式标注覆盖率 —— 否则「没看到问题」会被误读成「没问题」。"""
    slug = "audit-trunc-" + _tok()
    try:
        gdir = os.path.join(ag._root(), slug)
        os.makedirs(gdir, exist_ok=True)
        big = "A" * (ag.LLM_AUDIT_BUDGET + 20000)
        with open(os.path.join(gdir, "huge.js"), "w", encoding="utf-8") as fh:
            fh.write(big)
        with app.app_context():
            code, trunc = ag._sample_code(slug)
        assert trunc, "超预算未产生截断标记"
        assert "覆盖率声明" in code, "缺少覆盖率声明（LLM 无从知道看的是残片）"
        assert "不能视为安全" in code
        assert len(code) <= ag.LLM_AUDIT_BUDGET + 2000
        # 尾部仍须保留：截断按比例削减而非只取开头
        assert "A" * 200 in code.split("===== huge.js =====")[-1]
    finally:
        _cleanup_dirs(slug)


def test_sample_code_keeps_tail_of_huge_single_file(app, app_ctx):
    """单文件超上限时头尾都保留 —— 只保留开头等于换个地方漏。"""
    slug = "audit-tail-" + _tok()
    try:
        gdir = os.path.join(ag._root(), slug)
        os.makedirs(gdir, exist_ok=True)
        with open(os.path.join(gdir, "x.js"), "w", encoding="utf-8") as fh:
            fh.write("HEAD_MARK" + "B" * (ag.LLM_AUDIT_PER_FILE + 5000) + "TAIL_MARK")
        with app.app_context():
            code, trunc = ag._sample_code(slug)
        assert trunc
        assert "HEAD_MARK" in code and "TAIL_MARK" in code, "头尾必须都保留"
        assert "单文件上限被截断" in code
    finally:
        _cleanup_dirs(slug)


def test_sample_code_missing_dir_returns_empty():
    """目录不存在时返回空 + 空标记（旧实现 os.listdir 会抛 FileNotFoundError）。"""
    code, trunc = ag._sample_code("no-such-slug-" + _tok())
    assert code == "" and trunc == {}


# ---------- 缺陷 2：verdict 从未解析 ----------

@pytest.mark.parametrize("raw,expect", [
    ('{"verdict":"safe","issues":[],"summary":"ok"}', "safe"),
    ('```json\n{"verdict":"risk","issues":[],"summary":"bad"}\n```', "risk"),
    ('好的，审计结果如下：\n{"verdict":"unknown","issues":[],"summary":"x"}\n以上。', "unknown"),
    ('```\n{"verdict":"risk"}\n```', "risk"),
])
def test_extract_json_levels(raw, expect):
    """LLM 回复围栏/散文包裹都要能抠出 JSON —— 线上 openrouter 就返回过围栏格式。"""
    assert ag._extract_json(raw)["verdict"] == expect


def test_extract_json_failure_returns_none():
    assert ag._extract_json("") is None
    assert ag._extract_json("完全没有 JSON") is None
    assert ag._extract_json("{坏掉的 json") is None


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self._b if n is None or n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_llm(app, gid, content=None, raise_exc=None):
    """把出站 opener 换掉 + 配好 LLM 设置，跑一次审计并返回 (ok, note)。

    gid 而非 Game 对象：ORM 实例跨 app_context 会 detached，必须按 id 重取
    （这正是 admin/games.py 后台任务里那段注释讲的情形）。
    """
    def _on():
        # 🔑 Key 必须真的加密落库：配置不完整是一条**独立的**早退出口
        # （首版修复漏了它，被本文件的两条用例抓出来）。只设 base/model
        # 会让所有用例都走到"未配置完整"，测不到真正的 verdict 解析路径。
        from backup_settings import encrypt_secret
        for k in ("games_llm_on", "games_llm_base", "games_llm_model", "games_llm_key_enc"):
            Setting.query.filter_by(key=k).delete()
        db.session.add(Setting(key="games_llm_on", value="1"))
        db.session.add(Setting(key="games_llm_base", value="https://x.example/v1"))
        db.session.add(Setting(key="games_llm_model", value="m"))
        db.session.add(Setting(key="games_llm_key_enc", value=encrypt_secret("sk-test")))
        db.session.commit()

    def _fake_urlopen(req, timeout=None):
        if raise_exc:
            raise raise_exc
        return _Resp({"choices": [{"message": {"content": content}}]})

    with app.app_context():
        _on()
        g = db.session.get(Game, gid)
        orig_open = ag._open_llm
        orig_check = ag.safe_public_url
        ag._open_llm = _fake_urlopen
        # 测试不依赖真实 DNS（x.example 可能解析失败）；生产路径由
        # tests/test_outbound.py 与 test_llm_base_ssrf_is_rejected 覆盖。
        ag.safe_public_url = lambda u: True
        try:
            return ag._run_llm_audit(g)
        finally:
            ag._open_llm = orig_open
            ag.safe_public_url = orig_check


def test_risk_verdict_parsed_and_lowers_score(app, app_ctx):
    """判 risk 必须：解析出来 + 压低静态分 + 结论写进库里。"""
    slug = "audit-risk-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="", score=100)
        _fake_llm(app, gid, content='```json\n{"verdict":"risk","issues":[{"level":"warn","desc":"外传 cookie"}],"summary":"存在外传行为"}\n```')
        with app.app_context():
            g = db.session.get(Game, gid)
            assert g.audit_score == 0, "risk 未压低静态分（会与静态分混淆误导）"
            s = g.audit_summary
            assert "有风险" in s
            assert "外传 cookie" in s
            assert "存在外传行为" in s
            assert ag._latest_verdict(g) == ("risk", True)
    finally:
        _cleanup_dirs(slug)


def test_unparsable_reply_is_unknown_not_safe(app, app_ctx):
    """回复无法解析时必须判 unknown —— 旧实现把原文当结论，实际是「没审但显示已审」。"""
    slug = "audit-unknown-" + _tok()
    try:
        gid = _mk_game(app, slug, score=100)
        _fake_llm(app, gid, content="我觉得这个游戏看起来还好吧，没什么问题。")
        with app.app_context():
            g = db.session.get(Game, gid)
            v, has = ag._latest_verdict(g)
            assert v == "unknown" and has is True
            assert "无法判定" in g.audit_summary
            assert g.audit_score == 100  # 不是 risk，不该压分
    finally:
        _cleanup_dirs(slug)


# ---------- 缺陷 3：审计失败仍显示旧结论 ----------

def test_audit_failure_writes_unknown_over_old_safe(app, app_ctx):
    """核心回归：重审失败后，页面绝不能还显示上一次的 safe。"""
    slug = "audit-fail-" + _tok()
    try:
        old = "LLM 审计（安全）：2026-01-01 00:00\n结论：看起来没问题"
        gid = _mk_game(app, slug, summary=old, score=100)
        _fake_llm(app, gid, raise_exc=urllib.error.URLError("connection reset"))
        with app.app_context():
            g = db.session.get(Game, gid)
            v, has = ag._latest_verdict(g)
            assert v == "unknown" and has is True, "失败未覆盖旧结论，页面仍显示 safe"
            assert "审计失败" in g.audit_summary
            # 历史结论必须留痕（不能直接抹掉）
            assert "历史结论" in g.audit_summary
    finally:
        _cleanup_dirs(slug)


def test_audit_off_is_reported_not_silent(app, app_ctx):
    """LLM 关闭时审计不发请求，但也不应写任何结论（旧结论保持不变即可）。"""
    slug = "audit-off-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="LLM 审计（安全）：x\n结论：ok")
        with app.app_context():
            Setting.query.filter_by(key="games_llm_on").delete()
            db.session.add(Setting(key="games_llm_on", value="0"))
            db.session.commit()
            g = db.session.get(Game, gid)
            ok, note = ag._run_llm_audit(g)
            assert ok is False and "未开启" in note
            assert g.audit_summary == "LLM 审计（安全）：x\n结论：ok", "未开启不应改写结论"
    finally:
        _cleanup_dirs(slug)


def test_missing_llm_config_also_overwrites_old_safe(app, app_ctx):
    """🔑 这条是首版修复自己漏掉的出口（实测抓出来的）：配置不完整时直接 return，
    页面仍显示上一次的 safe。凡是"拿不到结论"的路径都必须落 unknown。"""
    slug = "audit-noconf-" + _tok()
    try:
        gid = _mk_game(app, slug,
                       summary="LLM 审计（安全）：2026-01-01 00:00\n结论：看起来没问题")
        with app.app_context():
            Setting.query.delete()
            db.session.add(Setting(key="games_llm_on", value="1"))
            db.session.add(Setting(key="games_llm_base", value=""))   # base 缺
            db.session.commit()
            g = db.session.get(Game, gid)
            ok, note = ag._run_llm_audit(g)
            assert ok is False and "未配置完整" in note
            v, has = ag._latest_verdict(g)
            assert (v, has) == ("unknown", True), "配置不完整未覆盖旧结论"
            assert "未配置完整" in g.audit_summary
    finally:
        _cleanup_dirs(slug)


def test_llm_base_ssrf_is_rejected_without_request(app, app_ctx):
    """Base 指向回环/内网时必须拒绝，且**不得发出请求**（管理员级 SSRF）。"""
    slug = "audit-ssrf-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="")
        with app.app_context():
            from backup_settings import encrypt_secret
            Setting.query.delete()
            db.session.add_all([
                Setting(key="games_llm_on", value="1"),
                Setting(key="games_llm_base", value="http://127.0.0.1:9/v1"),
                Setting(key="games_llm_model", value="m"),
                Setting(key="games_llm_key_enc", value=encrypt_secret("sk-test")),
            ])
            db.session.commit()
            called = []
            orig = ag._open_llm
            ag._open_llm = lambda *a, **k: called.append(True)
            try:
                ok, note = ag._run_llm_audit(db.session.get(Game, gid))
            finally:
                ag._open_llm = orig
            assert ok is False and "不安全" in note
            assert called == [], "指向内网的 Base 不得发出任何请求"
            assert "非公网" in db.session.get(Game, gid).audit_summary
    finally:
        _cleanup_dirs(slug)


def test_no_sendable_code_also_writes_unknown(app, app_ctx):
    """包内无可送审文本（只有二进制素材）也必须落 unknown，不能静默 return。"""
    slug = "audit-nocode-" + _tok()
    try:
        gdir = os.path.join(ag._root(), slug)
        os.makedirs(gdir, exist_ok=True)
        with open(os.path.join(gdir, "sprite.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
        with app.app_context():
            row = Game(slug=slug, title="N", entry="index.html",
                       status="pending", audit_score=100)
            db.session.add(row)
            db.session.commit()
            gid = row.id
        _fake_llm(app, gid, content='{"verdict":"safe"}')
        with app.app_context():
            g = db.session.get(Game, gid)
            v, has = ag._latest_verdict(g)
            assert (v, has) == ("unknown", True)
            assert "没有可送审" in g.audit_summary
    finally:
        _cleanup_dirs(slug)


# ---------- 缺陷 4：放行与审计结论脱钩 ----------

def test_approve_risk_requires_confirm_then_goes_through(app, app_ctx, client):
    """判 risk 时：第一次点击不落库（返回确认页），带 confirm_risk 才真正上架。"""
    slug = "audit-gate-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="LLM 审计（有风险）：2026-01-01 00:00\n结论：有风险")
        _super_client(app, client)
        # 未确认 → 不应上架
        r = client.post(f"/admin/game/{gid}/action",
                        data={"action": "approve"},
                        headers=_csrf(client), follow_redirects=False)
        assert r.status_code == 200 and "上架前确认" in r.get_data(as_text=True), \
            "risk 未触发二次确认页"
        with app.app_context():
            assert db.session.get(Game, gid).status == "pending", "确认前不得上架"
        # 确认 → 上架且留痕
        r2 = client.post(f"/admin/game/{gid}/action",
                         data={"action": "approve", "confirm_risk": "1"},
                         headers=_csrf(client), follow_redirects=False)
        assert r2.status_code in (302, 303)
        with app.app_context():
            g = db.session.get(Game, gid)
            assert g.status == "approved"
            assert "站长确认放行" in (g.admin_note or ""), "风险放行必须留痕"
    finally:
        _cleanup_dirs(slug)


def test_approve_never_audited_requires_confirm(app, app_ctx, client):
    """从未审计的游戏也要二次确认（未审 ≠ 安全）。"""
    slug = "audit-gate2-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="")
        _super_client(app, client)
        r = client.post(f"/admin/game/{gid}/action", data={"action": "approve"},
                        headers=_csrf(client), follow_redirects=False)
        assert "上架前确认" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Game, gid).status == "pending"
    finally:
        _cleanup_dirs(slug)


def test_approve_safe_goes_through_directly(app, app_ctx, client):
    """反向守卫：审计通过时**不该**弹确认页（否则确认页成了永远清不掉的噪音）。"""
    slug = "audit-gate3-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="LLM 审计（安全）：2026-01-01 00:00\n结论：ok")
        _super_client(app, client)
        r = client.post(f"/admin/game/{gid}/action", data={"action": "approve"},
                        headers=_csrf(client), follow_redirects=False)
        assert r.status_code in (302, 303), "安全游戏被确认页拦住了"
        with app.app_context():
            g = db.session.get(Game, gid)
            assert g.status == "approved"
            assert "站长确认放行" not in (g.admin_note or "")
    finally:
        _cleanup_dirs(slug)


def test_legacy_summary_counts_as_unaudited(app, app_ctx):
    """老数据（v4.4.2 之前的「LLM 审计：」原文格式）一律判 unknown，不是 safe。"""
    slug = "audit-legacy-" + _tok()
    try:
        gid = _mk_game(app, slug, summary='LLM 审计：\n{"verdict":"safe","issues":[]}')
        with app.app_context():
            g = db.session.get(Game, gid)
            assert ag._latest_verdict(g) == ("unknown", True)
            assert ag._approve_gate(g), "老格式不得被当作已审安全"
    finally:
        _cleanup_dirs(slug)


def test_games_page_shows_verdict_badge(app, app_ctx, client):
    """列表页必须把 verdict 显示出来（否则站长看到的只有静态分）。"""
    slug = "audit-badge-" + _tok()
    try:
        _mk_game(app, slug, summary="LLM 审计（有风险）：2026-01-01 00:00\n结论：坏")
        _super_client(app, client)
        body = client.get("/admin/games").get_data(as_text=True)
        assert "LLM 有风险" in body
        assert "LLM 审计配置" in body or "LLM 代码审计配置" in body
    finally:
        _cleanup_dirs(slug)


def test_admin_cannot_delete_game(app, app_ctx, client):
    """反向守卫：非超管不能删游戏（确认页不能成为越权通道）。"""
    slug = "audit-perm-" + _tok()
    try:
        gid = _mk_game(app, slug, summary="LLM 审计（有风险）：x\n结论：坏")
        _uid, uname, pwd = _mkuser(app, ROLE_ADMIN)
        _do_login(client, uname, pwd)
        r = client.post(f"/admin/game/{gid}/action",
                        data={"action": "approve", "confirm_risk": "1"},
                        headers=_csrf(client), follow_redirects=False)
        assert r.status_code in (302, 403, 404), "普通管理员竟能操作游戏审核"
        with app.app_context():
            assert db.session.get(Game, gid) is not None
    finally:
        _cleanup_dirs(slug)


# ---------- 静态扫描本身没被改坏 ----------

def test_scan_still_works():
    files = [
        {"name": "a.js", "data": b"eval('x')"},
        {"name": "b.html", "data": b"<html>hi</html>"},
    ]
    findings, score = games_safety.scan_game_files(files)
    assert any(x["rule"] == "eval_ctor" for x in findings)
    assert score == 94