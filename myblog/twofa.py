"""双因素认证 2FA / TOTP（v3.21.0，config-gated）。

设计：
- **零新增依赖**：TOTP 即 RFC 6238（HOTP RFC 4226 + 时间步），仅用标准库
  hmac/hashlib/base64/struct/secrets 实现。本项目部署为手工 pip install，
  每加一个依赖都是一次服务器变更；且 TOTP 算法简单、可用 RFC 官方测试向量
  自证正确（见 tests/test_twofa.py::test_rfc6238_vectors）。
- **config-gated 休眠**：是否启用由 config.TWOFA_ENABLED 决定（默认 false）。
  未启用时所有入口短路，代码路径存在但不激活——与 OAuth 同款设计。
- **密钥绝不落明文**：经 backup_settings.encrypt_secret（Fernet，SECRET_KEY 派生）加密后存库。
- **防重放**：verify() 返回命中的时间窗 counter，调用方记录 last_counter，
  同一窗口的码用过即失效（避免截获后 30 秒内重放）。
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

TOTP_PERIOD = 30      # 时间步长（秒），RFC 6238 默认
TOTP_DIGITS = 6       # 动态码位数
TOTP_SKEW = 1         # 容忍前后各 1 个窗口（±30s），补偿手机与服务器的时钟漂移
RECOVERY_CODE_COUNT = 8


def generate_secret():
    """生成 160-bit（RFC 4226 建议下限 128-bit）随机密钥，base32 无填充。"""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _b32decode(secret):
    """宽松解析 base32：忽略大小写、空格与缺失的 padding（用户手抄时常带空格）。"""
    s = "".join((secret or "").split()).upper()
    return base64.b32decode(s + "=" * (-len(s) % 8), casefold=True)


def hotp(secret, counter, digits=TOTP_DIGITS):
    """RFC 4226 HMAC-SHA1 一次性口令。counter 为 64-bit 大端整数。"""
    key = _b32decode(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    # 取 31 位动态截断，再对 10^digits 取模（避免用有符号 32 位整数）
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def counter_at(ts=None):
    ts = int(time.time()) if ts is None else int(ts)
    return ts // TOTP_PERIOD


def totp_at(secret, ts=None, digits=TOTP_DIGITS):
    """给定时刻的动态码（测试与「当前码」用；digits=8 用于对齐 RFC 测试向量）。"""
    return hotp(secret, counter_at(ts), digits)


def verify(secret, code, ts=None, skew=TOTP_SKEW, last_counter=0):
    """校验动态码。命中返回该时间窗 counter（调用方须落库防重放），否则返回 None。

    last_counter：上次成功消费的时间窗；小于等于它的窗口一律不再接受。
    """
    code = "".join((code or "").split())
    if not code or not code.isdigit() or len(code) != TOTP_DIGITS:
        return None
    base = counter_at(ts)
    for offset in range(-skew, skew + 1):
        c = base + offset
        if c <= last_counter:
            continue
        if hmac.compare_digest(hotp(secret, c), code):
            return c
    return None


def provisioning_uri(secret, account_name, issuer="llhhy-blog"):
    """生成 otpauth:// URI，供 Google Authenticator / 1Password 等扫码绑定。"""
    label = quote("%s:%s" % (issuer, account_name), safe="")
    return ("otpauth://totp/%s?secret=%s&issuer=%s&digits=%d&period=%d"
            % (label, secret, quote(issuer, safe=""), TOTP_DIGITS, TOTP_PERIOD))


# ---------- 恢复码（设备丢失时的唯一救命通道，一次性消费）----------

def generate_recovery_codes(count=RECOVERY_CODE_COUNT):
    """返回 (明文码列表, 摘要列表)。明文只在此次响应中出现一次，库里只存摘要。"""
    plain, hashed = [], []
    for _ in range(count):
        code = secrets.token_urlsafe(12)          # ~96 bit 高熵，无需慢哈希
        plain.append(code)
        hashed.append(hashlib.sha256(code.encode()).hexdigest())
    return plain, hashed


def consume_recovery_code(stored_json, code):
    """校验并消费一个恢复码。命中返回 (True, 剩余摘要 JSON)，否则 (False, 原值)。"""
    code = (code or "").strip()
    if not code:
        return False, stored_json
    digest = hashlib.sha256(code.encode()).hexdigest()
    try:
        items = json.loads(stored_json or "[]")
    except Exception:# noqa: BLE001  恢复码 JSON 损坏时按「无可用恢复码」处理，不让页面 500
        items = []
    if digest not in items:
        return False, stored_json
    items.remove(digest)
    return True, json.dumps(items)


# ---------- 持久化读写（密钥加密落库）----------

def get_secret(row):
    """解密 2FA 密钥（密文缺失或解密失败返回空串——绝不抛异常到调用方）。"""
    if not row or not row.secret_enc:
        return ""
    try:
        from backup_settings import decrypt_secret
        return decrypt_secret(row.secret_enc)
    except Exception:# noqa: BLE001  解密失败（缺 cryptography / 密文损坏）→ 视为无密钥，绝不抛出
        return ""


def set_secret(row, plain_secret):
    """加密写入密钥。cryptography 未装时抛错，由调用方转成友好错误（不静默降级）。"""
    from backup_settings import encrypt_secret
    row.secret_enc = encrypt_secret(plain_secret)


# ---------- 业务操作层（API 与后台共用，避免两处各写一套安全逻辑）----------
# 返回值为状态字符串，由调用方映射成 HTTP 状态码 / 页面提示，本层不碰 Response。

def _row_for(user_id):
    from models import UserTwoFactor
    return UserTwoFactor.query.filter_by(user_id=user_id).first()


def is_active(user_id):
    """该用户是否已**确认生效**的两步验证（只 enroll 未 confirm 不算）。"""
    row = _row_for(user_id)
    return bool(row and row.enabled)


def status_for(user):
    """返回 {enrolled, recovery_codes_left}，供 API 与后台页共用。"""
    row = _row_for(user.id)
    remaining = 0
    if row and row.enabled:
        try:
            remaining = len(json.loads(row.recovery_codes or "[]"))
        except Exception:# noqa: BLE001  恢复码 JSON 解析失败只影响计数展示，按 0 处理
            remaining = 0
    return {"enrolled": bool(row and row.enabled), "recovery_codes_left": remaining}


def enroll(user):
    """生成/重置密钥。返回 (status, secret, uri)；重置会把 enabled 打回 False。"""
    from models import UserTwoFactor, db
    row = _row_for(user.id)
    if not row:
        row = UserTwoFactor(user_id=user.id, secret_enc="", enabled=False)
        db.session.add(row)
    secret = generate_secret()
    try:
        set_secret(row, secret)
    except Exception:# noqa: BLE001  加密失败转成状态串交给调用方，不向上抛
        db.session.rollback()
        return "encrypt_failed", None, None
    # 重置后必须重新确认才生效：避免「换了密钥但没验证」把用户永久锁在门外
    row.enabled = False
    row.confirmed_at = None
    row.last_counter = 0
    db.session.commit()
    return "ok", secret, provisioning_uri(secret, user.username)


def confirm(user, code):
    """用 6 位码确认绑定。返回 (status, 明文恢复码列表)；恢复码只此一次返回。"""
    from models import db
    row = _row_for(user.id)
    if not row or not row.secret_enc:
        return "no_enroll", None
    secret = get_secret(row)
    if not secret:
        return "error", None
    hit = verify(secret, code, last_counter=row.last_counter or 0)
    if hit is None:
        return "bad_code", None
    from _time import utcnow
    row.enabled = True
    row.confirmed_at = utcnow()
    row.last_counter = hit          # 该窗口已消费，防重放
    plain, hashed = generate_recovery_codes()
    row.recovery_codes = json.dumps(hashed)
    db.session.commit()
    return "ok", plain


def disable(user, password, code):
    """关闭两步验证：需密码 + 动态码（或恢复码）双重确认。"""
    from models import db
    row = _row_for(user.id)
    if not row or not row.enabled:
        return "not_enabled"
    if not user.check_password(password or ""):
        return "bad_password"
    secret = get_secret(row)
    ok = False
    if secret:
        hit = verify(secret, code or "", last_counter=row.last_counter or 0)
        if hit is not None:
            row.last_counter = hit
            ok = True
    if not ok:
        ok, remaining = consume_recovery_code(row.recovery_codes or "", code)
        if ok:
            row.recovery_codes = remaining
    if not ok:
        return "bad_code"
    db.session.delete(row)
    db.session.commit()
    return "ok"


def verify_login(user, code):
    """登录第二步：动态码或恢复码任一通过即返回 True（并消费掉它，防重放/复用）。"""
    from models import db
    row = _row_for(user.id)
    if not row or not row.enabled:
        return False
    secret = get_secret(row)
    hit = verify(secret, code or "", last_counter=row.last_counter or 0) if secret else None
    if hit is not None:
        row.last_counter = hit
    else:
        ok, remaining = consume_recovery_code(row.recovery_codes or "", code)
        if not ok:
            return False
        row.recovery_codes = remaining
    db.session.commit()
    return True
