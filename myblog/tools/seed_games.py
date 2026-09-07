"""内置游戏收录脚本（v3.15.0）。

用途：把 myblog/builtin_games/<slug>/ 下的官方内置游戏，按与后台收录相同的安全链路
（games_safety.unpack/校验/扫描）解包进 <myblog>/data/games/<slug> 并登记为已上架，
使前台 /games 立即可见。亦可用于部署服务器时安装内置游戏。

用法：python tools/seed_games.py [--force]
运行环境：需在仓库根目录、且 myblog 依赖已装；SECRET_KEY/ADMIN_PASSWORD 自动取
myblog 环境变量，缺省用占位值（仅本地种子场景，勿用于生产配置）。
"""
import os
import sys
import hashlib

_MYBLOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _MYBLOG)

os.environ.setdefault("SECRET_KEY", "seed-games-local-secret")
os.environ.setdefault("ADMIN_PASSWORD", "seed-games-local-admin")

SRC = os.path.join(_MYBLOG, "builtin_games")
DST = os.path.join(_MYBLOG, "data", "games")

import games_safety  # noqa: E402
from app import create_app  # noqa: E402


def _dir_files(slug):
    base = os.path.join(SRC, slug)
    files = []
    total = 0
    for root, _dirs, names in os.walk(base):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, base).replace(os.sep, "/")
            with open(p, "rb") as fh:
                data = fh.read()
            total += len(data)
            files.append({"name": rel, "data": data})
    if total > games_safety.MAX_TOTAL_BYTES:
        raise ValueError(f"{slug} 超过解压大小上限")
    return files


def main(force=False):
    with create_app().app_context():
        from models import db, Game
        made = 0
        for slug in sorted(os.listdir(SRC)):
            if not os.path.isdir(os.path.join(SRC, slug)):
                continue
            files = _dir_files(slug)
            man = games_safety.find_manifest(files)
            ok, errs = games_safety.validate_manifest(man) if man else (False, ["缺 manifest"])
            if not ok:
                print(f"[skip] {slug}: {errs}")
                continue
            entry = man["entry"].strip()
            if entry not in {f["name"] for f in files}:
                print(f"[skip] {slug}: 入口 {entry} 缺失")
                continue
            findings, score = games_safety.scan_game_files(files)
            g = Game.query.filter_by(slug=slug).first()
            if g and not force:
                print(f"[skip] {slug}: 已存在（--force 覆盖更新）")
                continue
            gdir = os.path.join(DST, slug)
            os.makedirs(gdir, exist_ok=True)
            for f in files:
                full = os.path.join(gdir, f["name"].replace("/", os.sep))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "wb") as fh:
                    fh.write(f["data"])
            blob = "".join(str(f["data"][:64]) for f in files).encode("utf-8", "ignore")
            digest = hashlib.sha256(blob).hexdigest()
            if not g:
                g = Game(slug=slug)
                db.session.add(g)
            g.title = (man.get("name") or slug)[:120]
            g.description = (man.get("description") or "")[:4000]
            g.cover = (man.get("cover") or "")[:500]
            g.entry = entry
            g.author = (man.get("author") or "llhhy")[:80]
            g.version = (man.get("version") or "1.0")[:30]
            g.status = "approved"
            g.package_hash = digest
            g.size = sum(len(f["data"]) for f in files)
            g.file_count = len(files)
            g.audit_score = score
            g.audit_summary = "内置游戏（官方）。静态扫描："
            g.audit_summary += f"{len(findings)} 项" if findings else "未见明显可疑"
            made += 1
            print(f"[ok] {slug} 已上架（静态分 {score}，{len(files)} 文件）")
        db.session.commit()
        print(f"完成：内置游戏处理 {made} 个（目录 {DST}）")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
