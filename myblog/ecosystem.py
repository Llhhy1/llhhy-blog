# -*- coding: utf-8 -*-
"""v4.7.5 生态统计：统计「有多少人在用本系统部署上线」。

**为什么需要它**
GitHub 侧只能看到 **fork 派生关系**（实测：本仓库 fork=1、star=2），而绝大多数
使用者是 `git clone` 完自己改的 —— GitHub 完全看不见他们。想知道真实使用量，
只有一条路：**由部署实例主动上报**。

**上报什么（严格受限）**
只有四样：`site_key`（随机安装 ID）、`url`、`version`、时间戳。
**绝不包含任何访客数据、文章内容、账号信息** —— 这是这个功能能成立的前提。

**谁上报给谁**
每个部署实例在设置里填「生态中心地址」，每小时发一次心跳。
**只有中心端会收到心跳、才有数据** —— 别的部署实例的注册表是空的。
这意味着「中心端」不需要特殊开关：你的站点开着接收 API，自然就是中心。

**信任边界（v4.7.6 起改为 opt-out）**
- **默认开启、可随时关闭** —— 后台「设置 → 🌐 生态统计」取消勾选即停止上报。
  默认值从「关」改为「开」的理由：不上报就**永远统计不到**（GitHub 只看得到 fork），
  而关闭入口始终存在，使用者仍然握有选择权。
- **关掉「公开展示」即匿名**：`listed=0` 时心跳**不带 url**，且中心端会把
  已存的 url 清空 —— 只计数、不留身份。
- 中心端注册表里的数据是**自报**的，任何人都能伪造 → 展示时必须如实标注。
"""
import datetime
import json
import logging
import re
import secrets

from _time import utcnow

logger = logging.getLogger(__name__)

# ---------- 设置项（全部走 Setting KV，不建表） ----------
KEY_OPT_IN = "ecosystem_opt_in"       # "1" = 参与（上报心跳）
KEY_CENTER = "ecosystem_center"       # 生态中心地址（空 = 不上报）
KEY_LISTED = "ecosystem_listed"       # "0" = 不公开列出我的站点
KEY_SITE_KEY = "ecosystem_site_key"   # 随机安装 ID（自动生成）

_SITE_KEY_RE = re.compile(r"^[0-9a-f]{16,64}$")
_MAX_URL = 300

# 内置默认中心。**「默认开启」要真的生效，就必须有一个默认中心** ——
# 否则新部署的实例 `ecosystem_center` 为空，opt-in 开了也一个请求都发不出去。
# 自部署者可在设置里改成自己的中心；留空即回退到这里。
DEFAULT_CENTER = "https://www.llhhy.cn"

# 离线站点清理阈值（小时）。心跳每小时一次，24h ≈ 24 次连续错过，足以判定
# 「这个部署已经不在了」（关站 / 换了 center / 取消上报）。见 prune_stale_sites。
PRUNE_STALE_HOURS = 24


# ---------- 客户端侧 ----------


def site_key():
    """本机的随机安装 ID（首次调用时生成并落库）。

    ⚠️ **不绑 IP、不绑账号、不绑域名** —— 纯随机。
    它的唯一用途是让中心端把「同一个站点的多次心跳」认成一行（去重）。
    """
    from models import Setting
    from utils.settings import get_setting
    v = get_setting(KEY_SITE_KEY)
    if v and _SITE_KEY_RE.match(str(v).strip()):
        return str(v).strip()
    new = secrets.token_hex(16)
    try:
        row = Setting.query.filter_by(key=KEY_SITE_KEY).first()
        if row:
            row.value = new
        else:
            db_add_setting(KEY_SITE_KEY, new)
    except Exception as e:  # noqa: BLE001 （拿不到就临时用内存值，不影响主流程）
        logger.warning("[ECOSYSTEM] 生成 site_key 失败：%s", str(e)[:120])
    return new


def db_add_setting(key, value):
    """写一条 Setting（延迟到需要时 import，避免模块级循环依赖）。"""
    from models import db, Setting
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def opt_in():
    """是否参与生态统计（**默认开启**，可在后台随时关闭）。"""
    from utils.settings import get_setting
    return str(get_setting(KEY_OPT_IN, "1")).strip() not in ("0", "false", "no", "off")


def listed():
    """是否愿意公开展示本站点（默认展示；作者可拒绝）。"""
    from utils.settings import get_setting
    return str(get_setting(KEY_LISTED, "1")).strip() not in ("0", "false", "no", "off")


def center_url():
    """生态中心地址（留空 = 回退内置默认中心 `DEFAULT_CENTER`）。"""
    from utils.settings import get_setting
    v = str(get_setting(KEY_CENTER, "") or "").strip()
    return v or DEFAULT_CENTER


def own_site_url():
    """本机的公开地址（上报用）。优先用设置里的站点 URL。"""
    from utils.settings import get_setting
    for key in ("site_url", "SITE_URL"):
        v = get_setting(key)
        if v and str(v).strip().lower().startswith(("http://", "https://")):
            return str(v).strip()[:_MAX_URL]
    # 退而求其次：用当前请求的 Host（由调用方传入更准，这里返回空）
    return ""


def _is_test_runtime():
    """当前是否处于测试 / CI 运行时。**是则绝不发真实心跳**。

    ⚠️ v4.7.6 把默认值翻成「开」之后暴露的回归：默认开启 + 真实 `DEFAULT_CENTER`
    意味着**任何在本地或 CI 里 `create_app()` 的进程**（pytest fixture、
    清数据用的辅助函数、GitHub Actions）都会往生产发真实心跳 —— 既污染站点注册表
    （实测一次 CI + 两次本地全量测试注入 5 条假站点），也让「站点数」虚高。

    写两道判据而不只靠一处：
      · `PYTEST_CURRENT_TEST` —— pytest 运行时一定存在，覆盖测试进程本身；
      · Flask 的 `TESTING` 配置 —— 覆盖「用测试配置起的应用」这类场景。
    """
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    try:
        from flask import current_app, has_app_context
        if has_app_context() and current_app.config.get("TESTING"):
            return True
    except Exception:  # noqa: BLE001, S110 （拿不到上下文就按「不是测试」处理）
        pass
    return False


def report_heartbeat(force=False):
    """向生态中心发一次心跳。**永不抛异常**（失败静默）。

    走 `outbound.open_url()` —— 统一出站层：禁跟随 3xx + 固定已校验的 IP。
    """
    if not opt_in():
        return False
    if not force and _is_test_runtime():
        # force=True 只给人工排障用（显式要求发一次），正常路径一律挡住
        return False
    center = center_url()
    if not center:
        return False
    # ⚠️ 中心地址必须是**公网** http/https —— 否则这个功能会被用来探测内网。
    from outbound import OutboundRejected, open_url, safe_public_url
    if not safe_public_url(center):
        logger.warning("[ECOSYSTEM] 生态中心地址未通过安全校验，已跳过上报")
        return False
    url = center.rstrip("/") + "/api/ecosystem/heartbeat"
    is_listed = listed()
    payload = {
        "site_key": site_key(),
        # ⚠️ **不公开列出 = 匿名**：这时连 url 都不发（URL 对个人博客就是身份）。
        "url": own_site_url() if is_listed else "",
        "version": _app_version(),
        "listed": is_listed,
    }
    try:
        with open_url(url, timeout=10, method="POST",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}) as resp:
            return 200 <= resp.status < 300
    except OutboundRejected:
        return False
    except Exception as e:  # noqa: BLE001 （心跳失败绝不影响站点运行）
        logger.info("[ECOSYSTEM] 心跳上报失败：%s", str(e)[:120])
        return False


def _app_version():
    try:
        from config import APP_VERSION
        return APP_VERSION
    except Exception:  # noqa: BLE001
        return ""


# ---------- 中心端侧 ----------


def receive_heartbeat(data):
    """中心端接收一次心跳 → `(是否接受, 说明)`。

    去重靠 `site_key`（唯一索引）。**不验证站点 URL 是否可达** ——
    那会让中心端变成一个「任意外部 URL 探测器」（SSRF），绝不做。
    """
    if not isinstance(data, dict):
        return False, "bad payload"
    key = str(data.get("site_key") or "").strip().lower()
    if not _SITE_KEY_RE.match(key):
        return False, "bad site_key"
    url = str(data.get("url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        return False, "bad url"
    if len(url) > _MAX_URL:
        return False, "url too long"
    version = str(data.get("version") or "").strip()[:32]
    is_listed = bool(data.get("listed", True))

    from models import db, EcosystemSite
    now = utcnow()
    try:
        row = EcosystemSite.query.filter_by(site_key=key).first()
        if row:
            # 「不愿公开列出」= 匿名：连之前存过的 url 也一并清掉。
            # 只留 `url or row.url` 会让人以为关掉了，旧地址其实还躺在表里。
            row.url = url if is_listed else ""
            row.version = version or row.version
            row.listed = is_listed
            row.last_seen = now
        else:
            db.session.add(EcosystemSite(
                site_key=key, url=url, version=version, listed=is_listed,
                first_seen=now, last_seen=now))
        db.session.commit()
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning("[ECOSYSTEM] 写入站点注册表失败：%s", str(e)[:120])
        return False, "write failed"


def stats(active_hours=24, list_limit=60):
    """中心端统计：总站点数 / 近 N 小时活跃数 / 可公开展示的站点列表。

    ⚠️ 展示窗口与 prune 阈值一致（默认 24h）：超过 24h 无心跳的站点会被
    prune_stale_sites 硬删，这里再多一层防御，保证列表里不会出现僵尸站点。
    """
    from models import EcosystemSite
    out = {"total": 0, "active": 0, "sites": [], "active_hours": active_hours}
    try:
        all_rows = EcosystemSite.query.all()
        out["total"] = len(all_rows)
        cutoff = utcnow() - datetime.timedelta(hours=active_hours)
        recent = [r for r in all_rows if r.last_seen and r.last_seen >= cutoff]
        out["active"] = len(recent)
        # 公开展示：作者愿意列出（listed=1）且近 active_hours 小时内有心跳
        # （prune 已清掉更旧的，这里再兜底一次）
        shown = [r for r in all_rows if r.listed and r.last_seen and r.last_seen >= cutoff]
        shown.sort(key=lambda r: r.last_seen or utcnow(), reverse=True)
        for r in shown[:list_limit]:
            out["sites"].append({
                "url": r.url,
                "version": r.version,
                "first_seen": (r.first_seen.strftime("%Y-%m-%d %H:%M") if r.first_seen else ""),
                "last_seen": (r.last_seen.strftime("%Y-%m-%d %H:%M") if r.last_seen else ""),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("[ECOSYSTEM] 统计失败：%s", str(e)[:120])
    return out


def _stored_site_key():
    """非生成式读取本机 site_key（仅用于 prune 时排除自身，避免误删自己）。

    与 site_key() 的区别：不落库生成，没设置就返回 None —— prune 是维护动作，
    不该因为它而凭空造出一个安装 ID。
    """
    from utils.settings import get_setting
    v = get_setting(KEY_SITE_KEY)
    if v and _SITE_KEY_RE.match(str(v).strip()):
        return str(v).strip()
    return None


def prune_stale_sites(stale_hours=PRUNE_STALE_HOURS, exclude_self=True):
    """中心端：删除超过 stale_hours 小时没有心跳的站点。

    心跳是每小时一次。24 小时 = 24 次错过的心跳，足以判定「这个部署已经不在了」
    （关站 / 改了 center / 取消上报）。硬删而不是「只不展示」，理由：
    - 注册表是自报数据，留一堆永远不跳的僵尸行只会虚高「站点数」；
    - 中心站自己每小时给自己心跳，永远保鲜；`exclude_self` 再上一道闸，
      即使某次心跳偶发失败也不会把自己误删。

    返回被删除的条数。
    """
    from models import db, EcosystemSite
    cutoff = utcnow() - datetime.timedelta(hours=stale_hours)
    try:
        q = EcosystemSite.query.filter(EcosystemSite.last_seen < cutoff)
        if exclude_self:
            sk = _stored_site_key()
            if sk:
                q = q.filter(EcosystemSite.site_key != sk)
        n = q.delete(synchronize_session=False)
        if n:
            db.session.commit()
        return n or 0
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning("[ECOSYSTEM] 清理离线站点失败：%s", str(e)[:120])
        return 0
