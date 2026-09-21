# -*- coding: utf-8 -*-
"""主动推送收录（v3.19.0）——百度主动推送 + Bing/IndexNow。

设计纪律（对应实施清单 2.3，两条都不能破）：

1. **URL 一律由 `site_base() + "/post/" + slug` 生成**，绝不来自用户输入或
   `request.host`。`site_base()` 是 v3.18.9 收敛出来的唯一真相源（见
   `utils/settings.py`），这里不引入第二个取值路径。

2. **推送是阻塞网络调用，绝不能同步跑在请求里。** 首轮报告的 4.6 就是
   `notify.py` 同步连 Telegram 卡 6 秒、游戏 LLM 审计卡 120 秒。本模块的
   对外入口一律「写 pending 行 → 起后台线程 → 立即返回」，页面轮询状态。
   异步模式照抄 `mail_notify.notify_subscribers_async()`（threading.Thread +
   app context + 全异常静默）。

出网 host 白名单：
    这是本项目**唯一**允许 http 的出站目标——百度主动推送的官方地址就是
    `http://data.zz.baidu.com/urls`（无 https）。因此这里显式放行 http，但
    **仅当 host 精确等于 `data.zz.baidu.com`**（`_is_allowed_url()` 精确比对，
    不做后缀匹配，防 `data.zz.baidu.com.evil.com` 之类）。

配额与退避：
    - 百度单次最多 2000 条 URL（本站取 500 作上限，够了）；
    - IndexNow 单次最多 10000 条，本站同样取 500；
    - 单次请求 timeout 10s；失败记录 `status=fail` + 截断的 response，
      不做自动重试（避免配额被无效请求吃掉），由后台页手动重推。
    百度返回的 `remaining`（当日剩余配额）会回写进 `Setting`，供页面展示。
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

# --- 出站目标（唯一真相源；不得从别处拼接）---
BAIDU_ENDPOINT = "http://data.zz.baidu.com/urls"
BAIDU_HOST = "data.zz.baidu.com"
INDEXNOW_ENDPOINT = "https://api.bing.com/indexnow"
INDEXNOW_HOST = "api.bing.com"

TIMEOUT = 10          # 单次外发超时（秒）
MAX_URLS = 500        # 单次推送条数上限（百度 2000 / IndexNow 10000，取保守值）
RESP_KEEP = 500       # response 截断保留长度
LOG_KEEP = 200        # 审计日志 detail 截断长度

ENGINES = ("baidu", "indexnow")

# 百度当日剩余配额的 Setting 键（页面展示用，非密钥）
QUOTA_KEY = "seo_baidu_quota"


def _is_allowed_url(url):
    """出网站点白名单校验：**精确比对 host**（不做后缀包含）。

    这是本项目唯一允许 http 的地方，但只有 host 精确等于 `data.zz.baidu.com`
    才放行 http——避免「白名单写成 startswith 后被人用
    `http://data.zz.baidu.com.evil.com/` 绕过」这类经典错误。
    """
    try:
        u = urllib.parse.urlsplit(url)
    except Exception:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "https":
        return host in (BAIDU_HOST, INDEXNOW_HOST)
    if u.scheme == "http":
        return host == BAIDU_HOST
    return False


def _http_post(url, body, headers=None, timeout=TIMEOUT):
    """发一个 POST，返回 (status_code, text)。**绝不抛异常**。

    仅允许白名单 host；其余一律返回 (0, "blocked-host")，让调用方落 fail。
    """
    if not _is_allowed_url(url):
        return 0, "blocked-host: 出站目标不在白名单内"
    hdrs = {"User-Agent": "llhhy-blog-seo-push/1.0 (+site-owner)"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            txt = e.read(2000).decode("utf-8", "replace")
        except Exception:
            txt = ""
        return e.code, txt
    except Exception as e:
        # 断网 / DNS 失败 / 超时：返回 0，由调用方落 fail。**不重试**。
        return 0, "%s: %s" % (type(e).__name__, str(e)[:200])


def _clean(text, n=RESP_KEEP):
    """把外发响应清洗成可入库的单行文本。

    两道处理缺一不可：
    1. **剔除 token**——百度把 token 拼在 query 里，若响应回显了请求 URL，
       直接落库/上屏就等于泄露密钥（清单 2.4 明确要求页面与日志无明文）。
    2. 压平换行 + 截断——避免脏字符撑爆页面与日志。
    """
    s = str(text or "").replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    return s[:n]


def _get_secret(key):
    """读取并解密一个密钥型 Setting；未配置/解密失败返回空串。"""
    try:
        from utils import get_setting
        import backup_settings as bs
        enc = get_setting(key, "") or ""
        return bs.decrypt_secret(enc) if enc else ""
    except Exception:
        return ""


def _set_setting(key, value):
    """写一个 Setting（不存在则建）。异常静默。"""
    try:
        from models import db, Setting
        row = Setting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(Setting(key=key, value=value))
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 单引擎推送
# --------------------------------------------------------------------------

def push_baidu(urls, token, site_domain=""):
    """百度主动推送。返回 (status, response_text, remaining)。

    status ∈ ok / fail / quota。
    - 返回体形如 `{"success":2,"remaining":998}` 或 `{"error":401,"message":"token is not valid"}`。
    - `error=over quota` / `remaining=0` 记 quota（清单要求把配额单独成一档，
      便于页面区分「被限流」和「配置错」——一上来就 `status=fail` 会让用户
      以为 token 填错了）。
    """
    if not urls:
        return "fail", "无 URL 可推送", None
    if not token:
        return "fail", "未配置百度 token", None
    token = token.strip()
    if not site_domain:
        return "fail", "site_base() 未配置，无法确定 site 参数", None
    # URL 一律来自 site_base()，不来自用户输入（清单纪律 1）
    domain = site_domain.split("://", 1)[-1].strip("/")
    qs = urllib.parse.urlencode({"site": domain, "token": token})
    body = "\n".join(urls[:MAX_URLS]).encode("utf-8")
    status, text = _http_post(
        BAIDU_ENDPOINT + "?" + qs, body,
        headers={"Content-Type": "text/plain"},
    )
    # 清洗时把 token 从任何回显里抹掉
    safe = _clean(text).replace(token, "***")
    if status == 0:
        return "fail", safe or "网络不可达", None
    remaining = None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("remaining") is not None:
                try:
                    remaining = int(data["remaining"])
                except Exception:
                    remaining = None
            # ⚠️ 顺序要紧：先判 error，再判「配额已耗尽」，最后才认 success。
            # 百度在配额耗尽时返回 `{"success":0,"remaining":0}`——既没有 error
            # 字段，success 也是 0。若把 success 判定放在前面，这种情况会被记成
            # ok（页面显示绿色对勾，实际一条也没推成功），是最误导人的一种错。
            if data.get("error"):
                msg = str(data.get("message") or "")
                low = (msg + " " + str(data.get("error"))).lower()
                if "over quota" in low or "quota" in low or (remaining == 0):
                    return "quota", safe, remaining
                return "fail", safe, remaining
            if remaining == 0:
                return "quota", safe, remaining
            if data.get("success") is not None:
                try:
                    n_success = int(data["success"])
                except Exception:
                    n_success = -1
                if n_success == 0:
                    return "fail", safe or "上游返回 success=0", remaining
                return "ok", safe, remaining
    except Exception:
        pass
    # 非 JSON（百度偶发返回纯文本/HTML 错误页）
    return ("ok" if status == 200 else "fail"), safe, remaining


def push_indexnow(urls, key, host=""):
    """Bing / IndexNow 推送。返回 (status, response_text, None)。

    需要站点根可访问的 key 文件（`https://<域名>/<key>.txt`，内容就是 key 本身）。
    未配置 key 时返回 fail 并给出可读提示——不要静默成功。
    """
    if not urls:
        return "fail", "无 URL 可推送", None
    if not key:
        return "fail", "未配置 IndexNow key", None
    key = key.strip()
    if not host:
        return "fail", "site_base() 未配置，无法确定 host", None
    h = host.split("://", 1)[-1].strip("/")
    payload = json.dumps({
        "host": h,
        "key": key,
        "keyLocation": "https://%s/%s.txt" % (h, key),
        "urlList": urls[:MAX_URLS],
    }).encode("utf-8")
    status, text = _http_post(
        INDEXNOW_ENDPOINT, payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    safe = _clean(text).replace(key, "***")
    if status == 0:
        return "fail", safe or "网络不可达", None
    # IndexNow 成功返回 200/202 且通常无 body；4xx 视为失败
    if status in (200, 202):
        return "ok", safe or ("HTTP %d" % status), None
    return "fail", safe or ("HTTP %d" % status), None


# --------------------------------------------------------------------------
# 记录与异步调度
# --------------------------------------------------------------------------

def _record(post_id, engine, status, response):
    """写/更新一条 SeoSubmission（唯一键 post_id+engine）。异常静默。"""
    try:
        from models import db, SeoSubmission
        from _time import utcnow
        row = SeoSubmission.query.filter_by(post_id=post_id, engine=engine).first()
        if row is None:
            row = SeoSubmission(post_id=post_id, engine=engine)
            db.session.add(row)
        row.status = status
        row.response = _clean(response)
        row.submitted_at = utcnow()
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def submit_posts(post_ids, engine, actor=None):
    """**同步**执行一批推送（仅供后台线程调用，勿在请求里直接调）。

    返回 (ok_count, fail_count, summary)。summary 是给审计日志用的一句话。

    实现要点：**按批一次请求**，不是每篇一发。百度与 IndexNow 都接受
    换行 / urlList 批量提交，逐篇发等于把配额和超时都浪费掉。
    批失败时整批落 fail——无法区分单篇责任，但页面会显示截断后的响应，
    用户据此判断是 token 错还是网络问题。
    """
    from models import Post
    from utils import site_base

    if engine not in ENGINES:
        return 0, len(post_ids), "未知引擎"
    ids = [int(i) for i in post_ids][:MAX_URLS]
    base = site_base()
    if not base:
        # 站点地址未配置 → 全批 fail，但**不抛异常**（页面显示红字提示）
        for pid in ids:
            _record(pid, engine, "fail", "site_base() 未配置")
        return 0, len(ids), "site_base() 未配置：请先在后台设置站点 URL"

    token = _get_secret("seo_baidu_token_enc" if engine == "baidu" else "seo_indexnow_key_enc")

    # URL 一律由 site_base() + /post/ + slug 生成（清单纪律 1），逐条都能溯源到 post
    pairs = []
    for pid in ids:
        p = Post.query.filter_by(id=pid).first()
        if p and p.slug:
            pairs.append((pid, "%s/post/%s" % (base, p.slug)))
        else:
            _record(pid, engine, "fail", "文章不存在或无 slug")
    if not pairs:
        return 0, len(ids), "无可推送的有效文章"

    urls = [u for _pid, u in pairs]
    if engine == "baidu":
        st, resp, remaining = push_baidu(urls, token, base)
    else:
        st, resp, remaining = push_indexnow(urls, token, base)

    if remaining is not None:
        _set_setting(QUOTA_KEY, str(remaining))

    # 成功时整批标 ok；失败/配额时整批落同一状态（页面提示可重推）
    for pid, _u in pairs:
        _record(pid, engine, st, resp)
    if st == "ok":
        return len(pairs), 0, "成功 %d 篇" % len(pairs)
    tag = "配额耗尽" if st == "quota" else "失败"
    return 0, len(pairs), "%s（%d 篇）：%s" % (tag, len(pairs), resp[:120])


def _spawn(post_ids, engine, actor_name=""):
    """起后台线程执行推送。调用方据此立即返回「已入队」。"""
    ids = list(post_ids)

    def _runner(app):
        with app.app_context():
            try:
                ok, fail, summary = submit_posts(ids, engine)
                # 审计日志：在后台线程内写（请求上下文的 session 已结束）
                try:
                    from models import db, User, AuditLog
                    from utils import get_client_ip
                    u = User.query.filter_by(username=actor_name).first() if actor_name else None
                    db.session.add(AuditLog(
                        user_id=u.id if u else None,
                        username=actor_name or "",
                        action="seo_push", target=engine, target_id=ids[0] if ids else None,
                        detail=("推送 %d 篇：" % len(ids)) + summary,
                        ip="", success=(fail == 0),
                    ))
                    db.session.commit()
                except Exception:
                    pass
            except Exception:
                pass

    try:
        from flask import current_app
        app = current_app._get_current_object()
        threading.Thread(target=_runner, args=(app,), daemon=True).start()
        return True
    except Exception:
        return False


def enqueue(post_ids, engine, actor=None):
    """把推送丢给后台线程，立即返回。**这是路由唯一应调用的入口。**

    v3：先把涉及的记录置为 pending（页面立刻能显示「排队中」），再起线程。
    """
    ids = [int(i) for i in post_ids if i]
    if not ids:
        return 0
    try:
        from models import db, SeoSubmission
        from _time import utcnow
        now = utcnow()
        for pid in ids[:MAX_URLS]:
            row = SeoSubmission.query.filter_by(post_id=pid, engine=engine).first()
            if row is None:
                row = SeoSubmission(post_id=pid, engine=engine)
                db.session.add(row)
            row.status = "pending"
            row.submitted_at = now
            row.response = ""
        db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
    actor_name = ""
    try:
        actor_name = getattr(actor, "username", "") or ""
    except Exception:
        pass
    _spawn(ids, engine, actor_name)
    return len(ids)
