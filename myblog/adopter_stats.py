"""「谁在用 llhhy-blog」的 GitHub 客观指标：只在后台点「刷新」时取一次。

为什么不给前台接口顺手去拉 GitHub：那是**匿名接口触发出网**，一次调用两次外呼
（仓库信息 + Release 列表），在小 VPS（4 worker × 2 线程 = 8 槽）上就是一个放大
入口 —— v3.19.0 的 `/api/seo/shell-check` 已经把这类坑写过一次了。
所以取数只发生在后台的显式动作里，结果缓存进 `Setting`，`/api/adopters` 只读缓存。

出站统一走 `outbound.open_public()`（公网校验 + 固定 IP + 禁跟随 3xx）。
"""
import json
import urllib.request

from outbound import open_public

# 与 api/system.py 的版本自检同一仓库口径（本项目即 llhhy-blog 本体）
REPO = "Llhhy1/llhhy-blog"
REPO_STATS_KEY = "llhhy_repo_stats"
_UA = "llhhy-blog-adopter-stats/1.0"
_MAX_BYTES = 256 * 1024          # GitHub 这两个接口单次响应都远小于此；超限即视为异常
_TIMEOUT = 8


def _get_json(url):
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": _UA})
    with open_public(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("GitHub 响应超过 %d 字节上限" % _MAX_BYTES)
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict) and data.get("message"):
        raise ValueError("GitHub 返回错误：%s" % str(data["message"])[:120])
    return data


def fetch_repo_stats():
    """取 stars / forks / Release 下载数。任一请求失败即整体抛错（不写脏缓存）。"""
    repo = _get_json("https://api.github.com/repos/" + REPO)
    releases = _get_json("https://api.github.com/repos/%s/releases?per_page=100" % REPO)
    downloads = 0
    for r in (releases if isinstance(releases, list) else []):
        for a in (r.get("assets") or []):
            downloads += int(a.get("download_count") or 0)
    return {
        "repo": REPO,
        "stars": int(repo.get("stargazers_count") or 0),
        "forks": int(repo.get("forks_count") or 0),
        "watchers": int(repo.get("subscribers_count") or 0),
        "open_issues": int(repo.get("open_issues_count") or 0),
        "releases": len(releases) if isinstance(releases, list) else 0,
        "release_downloads": downloads,
    }


def cached_stats():
    """读缓存（供后台页面展示）。无缓存或脏数据返回 None。"""
    from models import Setting
    row = Setting.query.filter_by(key=REPO_STATS_KEY).first()
    if not row or not row.value:
        return None
    try:
        return json.loads(row.value)
    except ValueError:
        return None


def refresh():
    """取一次并落缓存 → `(是否成功, 给管理员看的一句话)`。

    失败**不覆盖**旧缓存：把「GitHub 暂时不可达」显示成「指标全 0」，
    比显示上一次的真实数字更糟。
    """
    from datetime import datetime, timezone
    from models import Setting, db

    try:
        stats = fetch_repo_stats()
    except Exception as e:  # noqa: BLE001 —— 出网失败的原因要原样给管理员看，但不冒泡成 500
        return False, "刷新失败：%s: %s（保留上次结果）" % (type(e).__name__, str(e)[:160])
    stats["refreshed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    row = Setting.query.filter_by(key=REPO_STATS_KEY).first()
    if row is None:
        row = Setting(key=REPO_STATS_KEY)
        db.session.add(row)
    row.value = json.dumps(stats, ensure_ascii=False)
    db.session.commit()
    return True, "已刷新：star %s / fork %s / Release 下载 %s" % (
        stats["stars"], stats["forks"], stats["release_downloads"])
