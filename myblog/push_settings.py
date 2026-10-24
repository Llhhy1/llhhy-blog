"""推送渠道配置后台化管理（v4.10.0）。

把 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `WECOM_WEBHOOK_URL` 从
「只能写环境变量」改为「后台可配」——**直接照抄 `backup_settings.py` 的三条
既定约定**，不另发明一套：

1. **密钥加密落库**：Fernet（`SECRET_KEY` 派生）加密后存 `Setting` 表，
   页面只回显掩码，绝不落明文；
2. **读取优先级**：密钥字段**环境变量优先** → 库加密值兜底。
   之所以密钥让 env 优先，是为了**老部署零迁移** —— 已经配好环境变量的站点
   不会因为升级就改用库里的空值而突然停止推送；
3. **无 Flask 上下文可退化为 sqlite3 直连**（`read_setting_db` 既有能力），
   这样后台线程 / CLI 里也能读。

⚠️ **本模块不负责校验 URL 能否出站**，那是 `notify._post_json` 走
`outbound.open_url()` 时做的事。**保存前**这里只做一条轻量预检
（`precheck_url`）：把明显不合格的地址当场挡在表单里，避免管理员
填完以为配好了、实际每次推送都静默失败。

哪些算敏感（加密存储、不回显）：
- `TELEGRAM_BOT_TOKEN`：拿到即可冒用 bot；
- `WECOM_WEBHOOK_URL`：URL 里带 `?key=<secret>`，拿到即可往群里发消息。
`TELEGRAM_CHAT_ID` 本身不是凭据（单独拿到无法发消息），按非敏感处理以便回显。
"""
import os

from backup_settings import (ENC_PREFIX, decrypt_secret, encrypt_secret,
                             mask_value, read_setting_db, write_setting_db)

# Setting 键名 → 环境变量名
FIELDS = {
    "push_telegram_token": "TELEGRAM_BOT_TOKEN",
    "push_telegram_chat": "TELEGRAM_CHAT_ID",
    "push_wecom_webhook": "WECOM_WEBHOOK_URL",
}

# 加密存储 + 页面只回显掩码的键
SENSITIVE_KEYS = {"push_telegram_token", "push_wecom_webhook"}

# 保存前的轻量预检目标（键 → 是否是 URL）
_URL_KEYS = {"push_wecom_webhook"}


def get(key, env_first=None):
    """取一个字段的生效值。

    `env_first` 不传时按「是否敏感」自动判定（敏感 → env 优先）。
    """
    env_name = FIELDS.get(key)
    if not env_name:
        return ""
    if env_first is None:
        env_first = key in SENSITIVE_KEYS
    db_val = decrypt_secret(read_setting_db(key) or "")
    env_val = os.environ.get(env_name, "") or ""
    if env_first:
        return env_val if env_val else db_val
    return db_val if db_val else env_val


def source_of(key):
    """这个字段当前生效值来自哪 —— 给后台页面显示「环境变量 / 数据库」标签。

    判据与 `get()` **完全一致**（同一段逻辑），避免出现
    「标签说来自数据库、实际生效的是环境变量」这种自相矛盾的显示。
    """
    return "env" if (get(key, env_first=True) and os.environ.get(FIELDS[key])) else "db"


def for_admin(key):
    """后台表单回显值：敏感键给掩码，非敏感键给明文。"""
    v = decrypt_secret(read_setting_db(key) or "")
    return mask_value(v) if key in SENSITIVE_KEYS else (v or "")


def save(key, value):
    """保存一个字段。敏感键加密后落库。

    ⚠️ **敏感键「留空 = 保持不变」**（与 `backup_settings._persist_backup_settings`
    完全同一语义，不另立规矩）：后台页面回显的是掩码，管理员不改那个字段时
    提交上来的就是空串——若把空串当「清空」，那么「只改 chat id、不动 token」
    会把 token 一起清掉，且**没有任何提示**。要清空必须显式勾「清除」。

    另一个坑：页面回显的掩码会被原样提交回来。若不识别它直接存，
    掩码 `ab****cd` 就会变成真正的 token 值 —— 于是推送全部失败，
    而页面看起来「明明配着值」。所以这里要对掩码做识别并跳过。
    """
    if key not in FIELDS:
        return False
    val = (value or "").strip()
    if key in SENSITIVE_KEYS:
        if not val:
            return True                      # 留空 = 保持不变
        if val.startswith(ENC_PREFIX):
            return True                      # 已经是密文，不重复加密
        stored = read_setting_db(key) or ""
        if val == mask_value(decrypt_secret(stored)):
            return True                      # 提交回来的是掩码，跳过
        return write_setting_db(key, encrypt_secret(val))
    return write_setting_db(key, val)


def clear(key):
    """显式清空一个字段的库值（敏感 / 非敏感都适用）。"""
    if key not in FIELDS:
        return False
    return write_setting_db(key, "")


def precheck_url(key, value):
    """保存前的轻量预检，返回 ``(ok, reason)``。

    只挡**当场就能判定**的错误（scheme / 内嵌凭据 / 明显是内网地址）。
    DNS 是否解析到公网**不在这里查** —— 域名解析会随环境变化，且真出网时
    `open_url()` 还会再校验一次（含 IP pinning）。这里查了也替代不了那次。
    """
    val = (value or "").strip()
    if not val:
        return True, ""
    if key in _URL_KEYS:
        low = val.lower()
        if not low.startswith("https://"):
            return False, "必须以 https:// 开头（明文 http 会被出站策略拒绝）"
        if "@" in val.split("//", 1)[-1].split("/", 1)[0]:
            return False, "URL 里不允许内嵌用户名密码"
        host = val.split("//", 1)[-1].split("/", 1)[0].split(":")[0].lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.endswith(".localhost"):
            return False, "不允许填本机 / 回环地址"
        if host.startswith("169.254.") or host.startswith("10.") \
                or host.startswith("192.168."):
            return False, "不允许填内网地址"
    return True, ""


def resolve_all():
    """给 `notify.deliver()` 用：一次取出三个字段的生效值。"""
    return {k: get(k) for k in FIELDS}
