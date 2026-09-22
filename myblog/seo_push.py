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
RESP_READ = 2000      # 单次读取上游响应的上限（防大响应）

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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """**拒绝跟随重定向**的出站 opener（v3.19.1）。

    为什么必须有它：`_is_allowed_url()` 只在**发起前**校验一次，而默认 opener
    会自动跟随 3xx，且 urllib 会把 POST **降级成 GET**。于是「白名单 host 返回
    一个 302」就等于把出站目标决策权交给了对端 —— 变成一次**任意 host 的 GET**，
    响应体还会被当作推送结果入库并回显到收录页（半盲 SSRF + 内容回显）。

    触发条件并不苛刻：百度端点本身就是明文 HTTP，链路上任一环（DNS 污染、
    同宿主机、被劫持的路由）能改响应即可。本地实测复现：白名单 host 返回
    `302 → 127.0.0.1:<other>`，`_http_post` 确实对白名单外主机发出了 GET。

    这里选择「抛 HTTPError」而不是「静默忽略」：让调用方看到真实的 3xx 状态码，
    落 fail 并显示原因，便于排查（302 通常意味着链路被劫持或端点已迁移）。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            "重定向被拒绝（出站白名单不允许跟随跳转）", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http_post(url, body, headers=None, timeout=TIMEOUT):
    """发一个 POST，返回 `(status_code, text, content_type)`。**绝不抛异常**。

    两道出站约束（缺一不可）：
    1. 仅允许白名单 host（精确比对，见 `_is_allowed_url`）；
    2. **禁跟随重定向**（见 `_NoRedirect`）。
    """
    if not _is_allowed_url(url):
        return 0, "blocked-host: 出站目标不在白名单内", ""
    hdrs = {"User-Agent": "llhhy-blog-seo-push/1.0 (+site-owner)"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return (r.status,
                    r.read(RESP_READ).decode("utf-8", "replace"),
                    (r.headers.get("Content-Type") or ""))
    except urllib.error.HTTPError as e:
        try:
            txt = e.read(RESP_READ).decode("utf-8", "replace")
        except Exception:
            txt = ""
        try:
            ctype = e.headers.get("Content-Type") or ""
        except Exception:
            ctype = ""
        return e.code, txt, ctype
    except Exception as e:
        # 断网 / DNS 失败 / 超时：返回 0，由调用方落 fail。**不重试**。
        return 0, "%s: %s" % (type(e).__name__, str(e)[:200]), ""


def _redact(text, *secrets):
    """把密钥从文本里抹掉。**必须在截断之前调用**。

    v3.19.1 修：v3.19.0 是 `_clean(text).replace(token, "***")`——**先截断到 500
    字符再替换**。若上游把带 token 的请求 URL 回显在第 500 字符之后，替换就不再
    命中，密钥会入库并上屏。IndexNow key 最长 128 位，泄露面更大。

    除整串外再抹「前缀片段」（24/16/8 字符）：上游只回显 token 的一部分时也救得回。
    """
    s = str(text or "")
    for sec in secrets:
        sec = (sec or "").strip()
        if not sec:
            continue
        s = s.replace(sec, "***")
        for n in (24, 16, 8):
            if len(sec) > n:
                s = s.replace(sec[:n], "***")
    return s


def _clean(text, n=RESP_KEEP, secrets=()):
    """把外发响应清洗成可入库的单行文本。

    顺序**不可倒**：先 `_redact` 脱敏 → 再压平换行 → 最后截断。
    """
    s = _redact(text, *secrets)
    s = s.replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    return s[:n]


# 上游响应里允许入库/上屏的字段白名单（其余一律丢弃）
_RESP_KEYS = ("error", "message", "success", "remaining",
              "not_same_site", "not_valid", "status", "code")


def _extract_response(data):
    """从响应 JSON 里**只取白名单字段**，返回紧凑 JSON 字符串（无可取字段则空串）。

    v3.19.1 修：此前把上游响应的前 500 字符**原样**入库并上屏（收录页与
    `/admin/seo/status` 都会显示）。那是**内容回显**——一旦响应被中间人更换，
    管理页面就成了攻击者的输出面。改为只保留协议里已知的字段。
    """
    if not isinstance(data, dict):
        return ""
    keep = {k: data[k] for k in _RESP_KEYS if k in data}
    if not keep:
        return ""
    try:
        return json.dumps(keep, ensure_ascii=False)
    except Exception:
        return ""


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
    status, text, ctype = _http_post(
        BAIDU_ENDPOINT + "?" + qs, body,
        headers={"Content-Type": "text/plain"},
    )
    # ⚠️ 顺序：`_clean` 内部先脱敏后截断（token 出现位置若在截断点之后，
    #    先截断就会漏抹 —— v3.19.0 的缺陷）
    safe = _clean(text, secrets=(token,))
    if status == 0:
        return "fail", safe or "网络不可达", None
    remaining = None
    data = None
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        shown = _extract_response(data) or safe
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
                return "quota", shown, remaining
            return "fail", shown, remaining
        if remaining == 0:
            return "quota", shown, remaining
        if data.get("success") is not None:
            try:
                n_success = int(data["success"])
            except Exception:
                n_success = -1
            if n_success == 0:
                return "fail", shown or "上游返回 success=0", remaining
            # 成功还需 Content-Type 自证是 JSON（v3.19.1）：
            # 一个伪造的 `HTTP 200 + HTML 错误页` 此前会被记成 ok 并写入虚假配额。
            if ctype and "json" not in ctype.lower():
                return "fail", "Content-Type 非 JSON（%s）" % ctype[:60], remaining
            return "ok", shown, remaining
    # 非 JSON / 无 success 字段 → **不算成功**（v3.19.1：此前 `HTTP 200` 即判 ok）
    return "fail", safe or ("非 JSON 响应（HTTP %d）" % status), remaining


def _keylocation(host, key):
    """构造 IndexNow 的 `keyLocation`；`site_url` 不合法时返回空串。

    v3.19.1：v3.19.0 是 `"https://%s/%s.txt" % (h, key)`，`h` 直接取后台
    可填的 `site_url`——填成别的域名就等于把 key 的 URL 路径告知那个域名的持有者；
    带 path/query/userinfo 还会拼出非法或钓鱼式 URL。这里要求 scheme 合法、
    hostname 非空、无 query/fragment/userinfo。
    """
    h = (host or "").strip().rstrip("/")
    try:
        u = urllib.parse.urlsplit(h)
    except Exception:
        return ""
    if u.scheme not in ("http", "https") or not u.hostname:
        return ""
    if u.query or u.fragment or ("@" in (u.netloc or "")):
        return ""
    path = (u.path or "").rstrip("/")
    return "%s://%s%s/%s.txt" % (u.scheme, u.netloc, path, key)


def _valid_indexnow_key(key):
    """IndexNow key 规范：8–128 字符，仅 [A-Za-z0-9-]。

    管理页保存时已校验；出站前再校验一次是纵深防御——key 会被拼进 URL 路径，
    含 `/`、`..`、空格可把 keyLocation 指向站内任意路径。
    """
    import re as _re
    return bool(_re.match(r"^[A-Za-z0-9\-]{8,128}$", (key or "").strip()))


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
    if not _valid_indexnow_key(key):
        return "fail", "IndexNow key 格式不合法（应为 8–128 位 [A-Za-z0-9-]）", None
    keyloc = _keylocation(host, key)
    if not keyloc:
        return ("fail",
                "site_url 不是合法的站点地址（需形如 https://example.com，"
                "不含 query/fragment/userinfo）", None)
    h = host.split("://", 1)[-1].strip("/")
    payload = json.dumps({
        "host": h,
        "key": key,
        "keyLocation": keyloc,
        "urlList": urls[:MAX_URLS],
    }).encode("utf-8")
    status, text, _ctype = _http_post(
        INDEXNOW_ENDPOINT, payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    safe = _clean(text, secrets=(key,))
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


def submit_posts(post_ids, engine):
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
    # 容错：post_ids 里混进非数字不再抛异常（v3.19.1）。
    # 原先 `[int(i) for i in post_ids]` 会直接抛，被外层静默吞掉 →
    # 整批记录永久停在「排队中」。
    ids = []
    for i in post_ids:
        try:
            ids.append(int(i))
        except (TypeError, ValueError):
            continue
    ids = ids[:MAX_URLS]
    if not ids:
        return 0, 0, "无有效的文章 ID"
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


def _write_audit(actor_name, actor_ip, engine, ids, summary, fail):
    """写推送审计日志（**v3.19.1 改为复用项目统一的 `log_audit()`**）。

    v3.19.0 在这里手搓 `AuditLog(..., ip="")`，而 `from utils import get_client_ip`
    导入了却从未调用——「谁、从哪个 IP 烧掉了配额」事后查不到，与
    `admin/_helpers.py::log_audit`（v3.18.5 刚收口好「IP 必须走 get_client_ip」）
    自相矛盾。

    IP 必须在**请求线程**里取（后台线程没有请求上下文），由 `enqueue` 传入。

    ⚠️ `log_audit` 只能**延迟导入**：`admin/seo.py` 会导入本模块，模块顶层导入
    `admin._helpers` 会形成循环导入。
    """
    try:
        from admin._helpers import log_audit
        from models import User
        u = User.query.filter_by(username=actor_name).first() if actor_name else None
        log_audit("seo_push", engine, ids[0] if ids else None,
                  ("推送 %d 篇：" % len(ids)) + summary,
                  user=u, ip=actor_ip or "", success=(fail == 0))
    except Exception:
        # 审计失败不该影响推送结果，但**必须留痕**（不能再静默）
        try:
            from flask import current_app
            current_app.logger.warning("seo_push 审计写入失败", exc_info=True)
        except Exception:
            pass


def _spawn(post_ids, engine, actor_name="", actor_ip=""):
    """起后台线程执行推送。返回 True/False（线程是否真的起来了）。"""
    ids = list(post_ids)

    def _runner(app):
        with app.app_context():
            try:
                _ok, fail, summary = submit_posts(ids, engine)
            except Exception as e:
                # ⚠️ **不再静默**（v3.19.1）：v3.19.0 这里是外层
                # `except Exception: pass` 套内层同样的 pass。一旦 submit_posts
                # 抛出，这批记录会**永久停在 pending**——页面 refreshStatus 永远
                # 等不到结果，日志里也没有任何痕迹（首审 6.3 点名的正是这种模式）。
                fail = len(ids)
                summary = "后台线程异常：%s" % type(e).__name__
                try:
                    app.logger.exception(
                        "seo_push 后台线程异常 engine=%s post_ids=%s", engine, ids)
                except Exception:
                    pass
                for pid in ids:
                    _record(pid, engine, "fail", summary)
            _write_audit(actor_name, actor_ip, engine, ids, summary, fail)

    try:
        from flask import current_app
        app = current_app._get_current_object()
        threading.Thread(target=_runner, args=(app,), daemon=True).start()
        return True
    except Exception:
        return False


def enqueue(post_ids, engine, actor=None):
    """把推送丢给后台线程，立即返回。**这是路由唯一应调用的入口。**

    先把涉及的记录置为 pending（页面立刻能显示「排队中」），再起线程。

    v3.19.1：`_spawn` 的返回值不再被丢弃——线程起不来时把这批标 `fail` 并留痕，
    否则页面会永远显示「排队中」（v3.19.0 的缺陷）。
    """
    ids = []
    for i in post_ids:
        try:
            ids.append(int(i))
        except (TypeError, ValueError):
            continue
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
    # 来源 IP 必须在请求线程里取（后台线程无请求上下文）
    actor_ip = ""
    try:
        from utils import get_client_ip
        actor_ip = get_client_ip() or ""
    except Exception:
        actor_ip = ""
    if not _spawn(ids, engine, actor_name, actor_ip):
        for pid in ids[:MAX_URLS]:
            _record(pid, engine, "fail", "后台线程启动失败，请重试或查看服务日志")
        return 0
    return len(ids)
