"""
"""

import os
import json as _json
import time
import threading
from flask import request, jsonify, current_app, session
import hmac
import urllib.request
import subprocess
from config import Config as _Config

from .common import (api_bp, db, User, _UPDATE_LOCK, _VER_CHECK_CACHE, rate_limit, client_key)

# ---------- 版本自检与在线更新（后台一键更新，v2.5.0）----------


@api_bp.route("/version/check")
def version_check():
    """后台登录后检测是否有新版本：对比 GitHub latest tag 与本地 APP_VERSION。
    仅查询 GitHub（10 分钟缓存），不做任何写操作；未配置 WH_DEPLOY_SECRET 也能查。
    """
    import json as _json
    import urllib.request
    import time as _time
    from config import APP_VERSION as _VER

    latest = ""
    now = _time.time()
    # 命中缓存直接返回（避免每次登录都请求 GitHub）
    if _VER_CHECK_CACHE["latest"] and (now - _VER_CHECK_CACHE["ts"]) < 600:
        latest = _VER_CHECK_CACHE["latest"]
    else:
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/Llhhy1/llhhy-blog/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "llhhy-blog"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            latest = (data.get("tag_name") or "").strip()
            _VER_CHECK_CACHE["latest"] = latest
            _VER_CHECK_CACHE["ts"] = now
        except Exception:
            latest = _VER_CHECK_CACHE.get("latest", "")  # 网络失败回退缓存
    current = _VER or ""
    # 规范化版本号：去 v/V 前缀，拆成 tuple 数字比较（修复字符串比较 'v2.5.0' > '2.5.0' 恒 True 的 bug）
    def _v_tuple(s):
        s = (s or "").strip()
        if s and s[0] in "vV":
            s = s[1:]
        try:
            return tuple(int(x) for x in s.split(".") if x.isdigit())
        except (ValueError, TypeError):
            return None
    c_t, l_t = _v_tuple(current), _v_tuple(latest)
    update_available = bool(c_t and l_t and l_t > c_t)
    return jsonify({
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "check_ok": True,
    })


def _do_version_update():
    """在 _UPDATE_LOCK 保护下执行更新触发：校验脚本存在 → 状态文件防重入 → Popen。

    与 version_update 分离以缩小锁内临界区（只包「检查+启动」原子段）。
    """
    import config as _cfg_mod
    script = _cfg_mod.Config.DEPLOY_SCRIPT or os.path.join(_cfg_mod.BASE_DIR, "update.sh")
    script = os.path.normpath(script)
    if not os.path.exists(script):
        return jsonify({"error": f"未找到更新脚本 {script}，请先上传 update.sh 到服务器"}), 400
    try:
        import json as _json
        status_file = os.path.join(_cfg_mod.DATA_DIR, "update_status.json")
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                st = _json.load(f).get("status", "")
            if st in ("started", "downloading", "backing_up", "deploying", "restarting"):
                return jsonify({"error": "更新正在进行中，请稍候"}), 409
    except Exception:
        pass
    # 异步执行（nohup 风格：脱离父进程，输出重定向到日志，不阻塞请求）
    try:
        import subprocess
        log_path = os.path.join(_cfg_mod.DATA_DIR, "update_log.txt")
        with open(log_path, "ab") as logf:
            subprocess.Popen(["bash", script], stdout=logf, stderr=logf,
                             start_new_session=True, close_fds=True)
    except Exception as e:
        return jsonify({"error": f"更新脚本启动失败: {e}"}), 500
    return jsonify({"ok": True, "message": "已开始后台更新，完成后会提示刷新"})


@api_bp.route("/version/update", methods=["POST"])
def version_update():
    """触发在线更新：异步执行 update.sh（下载→备份→覆盖→自动重启）。
    仅超管可触发（全量审计修复：原为 is_admin_role，普通管理员也能触发服务器
    脚本执行——运维级 RCE 被暴露给非超管，收窄为 is_super）；正在更新时拒绝
    重复触发（防重入锁，含进程内锁消除 TOCTOU）。
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "请先登录"}), 401
    u = db.session.get(User, uid) if uid else None
    if not u or not u.is_super:
        return jsonify({"error": "没有权限执行更新（仅超级管理员）"}), 403
    if not rate_limit(client_key("api_version_update"), limit=3, window=3600):
        return jsonify({"error": "更新触发过于频繁，请稍后再试"}), 429
    # 防重入：进程内锁（消除 TOCTOU）+ 状态文件双保险
    if not _UPDATE_LOCK.acquire(blocking=False):
        return jsonify({"error": "更新正在进行中，请稍候"}), 409
    try:
        return _do_version_update()
    finally:
        _UPDATE_LOCK.release()


# ---------- 在线更新状态查询 ----------


@api_bp.route("/version/status")
def version_status():
    """读取在线更新状态（后台轮询用）。仅超管可读（全量审计修复：原无鉴权，任何人可读 \n    更新进度，且可配合 update 的防重入锁制造 409 DoS；收窄为 is_super）。"""
    uid = session.get("user_id")
    u = db.session.get(User, uid) if uid else None
    if not u or not u.is_super:
        return jsonify({"error": "没有权限"}), 403
    import config as _cfg_mod
    status_file = os.path.join(_cfg_mod.DATA_DIR, "update_status.json")
    default = {"status": "idle", "version": "", "ts": "", "message": ""}
    try:
        import json as _json
        if os.path.exists(status_file):
            with open(status_file, "r", encoding="utf-8") as f:
                return jsonify(_json.load(f))
    except Exception:
        pass
    return jsonify(default)

# ---------- Webhook 自动部署（GitHub push → 服务器自动更新，D3）----------
@api_bp.route("/webhook/deploy", methods=["POST"])
def webhook_deploy():
    """密钥鉴权 + 触发服务器部署脚本。
    配置环境变量 WH_DEPLOY_SECRET（鉴权）与 DEPLOY_SCRIPT（部署脚本路径）。
    GitHub Webhook 仅在请求头带 X-Deploy-Token（禁止 URL ?token=，避免部署密钥写入
    Nginx/反代/GitHub webhook 投递/访问日志导致凭据泄露）。校验通过后，若配置了
    DEPLOY_SCRIPT 则异步执行该脚本（如 git pull / 解压 zip / 重启）。"""
    secret = current_app.config.get("WH_DEPLOY_SECRET")
    if not secret:
        return jsonify({"error": "服务器未配置部署密钥 WH_DEPLOY_SECRET"}), 403
    # M3 修复①：仅接受 X-Deploy-Token 请求头，禁止 URL ?token=，避免部署密钥写入
    # Nginx/反代/GitHub webhook 投递/访问日志导致凭据泄露。
    token = request.headers.get("X-Deploy-Token") or ""
    import hmac
    if not hmac.compare_digest(token, secret):
        return jsonify({"error": "密钥错误"}), 403
    # v3.1.6 可选增强：timestamp 防重放（WH_REPLAY_WINDOW，默认 300 秒）。
    # 要求请求头携带 X-Deploy-Time（Unix 秒），与服务器时间偏差超过窗口即拒绝，
    # 防止攻击者截获合法 webhook 请求后在窗口外重放触发部署。
    # M3 修复③：强制防重放下限（≥30s），禁止 WH_REPLAY_WINDOW=0 完全关闭重放保护。
    raw_window = current_app.config.get("WH_REPLAY_WINDOW", 300)
    try:
        window = int(raw_window)
    except (TypeError, ValueError):
        window = 300
    if window < 30:
        window = 30
    # 始终启用时间戳重放校验（window 恒 ≥30s，无法被关闭）
    try:
        import time as _t
        ts = int(request.headers.get("X-Deploy-Time") or "")
        if abs(_t.time() - ts) > window:
            return jsonify({"error": "部署请求时间戳过期或缺失，已拒绝（防重放）"}), 403
    except (TypeError, ValueError):
        return jsonify({"error": "缺少有效的 X-Deploy-Time 时间戳，已拒绝（防重放）"}), 403
    script = current_app.config.get("DEPLOY_SCRIPT", "")
    triggered = False
    if script:
        try:
            import subprocess
            # 异步触发部署脚本（不等待、不阻塞请求）；DEVNULL 重定向输出避免 hang，无 fd 泄漏
            subprocess.Popen(["bash", script], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            triggered = True
        except Exception as e:
            return jsonify({"ok": True, "triggered": False, "error": f"部署脚本启动失败: {e}"}), 500
    return jsonify({"ok": True, "triggered": triggered,
                    "message": "部署已触发" if triggered else "授权通过但未配置 DEPLOY_SCRIPT，请手动部署"})

