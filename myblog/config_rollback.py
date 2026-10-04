# -*- coding: utf-8 -*-
"""配置快照与回滚（v3.25.2）。

**要解决的问题**：`Setting` 表有 65 项配置，后台各处都能改。`log_audit` 记了
「谁在什么时候改了设置」这个**事实**，但没记「改之前是什么值」—— 于是改错了
（SMTP 端口填错、限流阈值调成 1、日限流关掉）只能凭记忆手改回去。

**为什么快照进审计表而不是新建表**：项目纪律「能走 log_audit 优先走审计表」。
快照与「谁改的」同处一行，天然对齐；新建快照表则两者可能各写各的、不同步。

**三条安全设计（都是刻意为之，改代码前先读完）**：

1. **快照存 `Setting` 里的原始值，不解密。**
   敏感项（`SENSITIVE_KEYS`：OSS SecretKey / WebDAV 密码 / SCP 私钥）在落库时
   已经是 Fernet 密文（`bkenc$` 前缀）。直接存原值 → 回滚是「把密文写回去」，
   **全程不接触明文**，也就没有「解密失败」「明文进日志」「明文进内存」这三类问题。

2. **`detail` 只写摘要，绝不写值。**
   `detail` 会出现在审计列表页、CSV 导出、并显示在超管屏幕上。把值写进 detail
   等于把凭据抄进一份**可导出、可截图**的日志。detail 只写「改��哪几个 key」。

3. **回滚本身是特权操作**：`@super_required` + 全局 CSRF + 写审计，
   且**回滚前先给当前值也拍一份快照** —— 否则「回滚回滚」就没有退路了。

**回滚的语义边界**（重要）：回滚的是**本次快照覆盖到的那些 key**，
不是「全库配置回到那时」。全库回滚会连带撤销别的管理员在这期间的合法修改。
"""
import json

from models import db, AuditLog, Setting
from audit import log_audit
from _time import utcnow

# 快照的 target 标记。用 target 而非 action 区分，是为了让审计列表页
# 能按 target 过滤出「配置历史」这一类。
SNAPSHOT_TARGET = "config_snapshot"
ROLLBACK_TARGET = "config_rollback"

# 单次快照允许的 key 上限。65 项全量快照约 2~4 KB（Text 列放得下），
# 但设上限是为了防止将来有人误传一个巨大的 dict 把审计表撑爆。
_MAX_SNAPSHOT_KEYS = 200


def current_values(keys):
    """取指定 key 的当前值 → {key: value}。不存在的 key 记为 None（表示「当时没有这一项」）。"""
    if not keys:
        return {}
    keys = list(keys)
    if len(keys) > _MAX_SNAPSHOT_KEYS:
        raise ValueError("单次快照 key 数超限：%d > %d" % (len(keys), _MAX_SNAPSHOT_KEYS))
    rows = Setting.query.filter(Setting.key.in_(keys)).all()
    got = {r.key: r.value for r in rows}
    return {k: got.get(k) for k in keys}


def snapshot_settings(keys, user=None, ip="", reason=""):
    """在**改配置之前**调用：把当前值快照进审计表。

    返回快照的 audit id（回滚时要用），失败返回 None。

    ⚠️ 调用点必须在 `db.session.commit()` **之前**——否则快照记的是新值，
    回滚等于回滚到「已经改完」的状态，看上去成功、实则无效。

    **失败语义分两类**（刻意不同）：
    - **编程错误**（key 数超限）→ **抛 ValueError**。这是代码 bug，静默只会让它
      在生产上表现为「快照莫名其妙不生效」，极难排查。
    - **运行期失败**（数据库不可用等）→ 返回 None。审计是旁路，不能因它拖垮
      「保存设置」这个主流程。
    """
    # —— 参数校验放在 try 之外：编程错误不该被「尽力而为」的静默吞掉 ——
    if keys and len(list(keys)) > _MAX_SNAPSHOT_KEYS:
        raise ValueError("单次快照 key 数超限：%d > %d"
                         % (len(list(keys)), _MAX_SNAPSHOT_KEYS))
    try:
        vals = current_values(keys)
        if not vals:
            return None
        exist = [k for k, v in vals.items() if v is not None]
        detail = "变更前快照：%d 项%s" % (len(exist), ("（%s）" % reason) if reason else "")
        # 先落一行审计；log_audit 内部自己 commit，故此处不能与业务改动同事务。
        log_audit("snapshot", SNAPSHOT_TARGET, 0, detail,
                  user=user, ip=ip, payload=vals)
        rows = (db.session.query(AuditLog).filter_by(target=SNAPSHOT_TARGET)
                .order_by(AuditLog.id.desc()).limit(1).all())
        return rows[0].id if rows else None
    except Exception:
        return None


def list_snapshots(limit=30, offset=0):
    """配置快照历史（新的在前）。只取 target=config_snapshot 的行。"""
    return (AuditLog.query.filter_by(target=SNAPSHOT_TARGET)
            .order_by(AuditLog.id.desc())
            .limit(max(1, min(limit, 200))).offset(max(0, offset))
            .all())


def snapshot_count():
    return AuditLog.query.filter_by(target=SNAPSHOT_TARGET).count()


def diff_snapshot(snapshot_id, keys=None):
    """对比「快照值」与「当前值」→ [{key, before, now, changed}]，**只列有变化的**。

    回滚前必须先让人看清「会改哪些」，这是特权操作的标配。
    """
    row = db.session.get(AuditLog, snapshot_id)
    if row is None or row.target != SNAPSHOT_TARGET or not row.payload:
        return None
    try:
        before = json.loads(row.payload)
    except ValueError:
        return None
    if not isinstance(before, dict):
        return None
    now = current_values(list(before.keys()) if keys is None else keys)
    out = []
    for k, bv in before.items():
        nv = now.get(k)
        # None 与 "" 视作等价：表单里没填提交上来就是 ""，
        # 而「从未设置过」读出来是 None —— 两者语义上都是「没配」，不该报成差异。
        same = (bv == nv) or (bv in (None, "") and nv in (None, ""))
        if not same:
            out.append({"key": k, "before": bv, "now": nv})
    return out


def rollback(snapshot_id, user=None, ip="", keys=None, confirm=False):
    """把指定快照的值写回 Setting。返回 (ok, msg)。

    **先给当前值拍一份快照**（见模块 docstring 第 3 条），这样「回滚回滚」有退路。
    """
    if not confirm:
        return False, "回滚需显式确认"
    row = db.session.get(AuditLog, snapshot_id)
    if row is None or row.target != SNAPSHOT_TARGET or not row.payload:
        return False, "快照不存在或已过期"
    try:
        before = json.loads(row.payload)
    except ValueError:
        return False, "快照内容损坏，无法回滚"
    if not isinstance(before, dict) or not before:
        return False, "快照内容为空，无法回滚"
    if keys is not None:
        before = {k: v for k, v in before.items() if k in set(keys)}
        if not before:
            return False, "未选中任何可回滚的配置项"

    # 回滚前的退路快照（不含用户选择的子集 —— 退路要覆盖全部被改动的 key）
    current_values_before = current_values(list(before.keys()))
    exist_now = {k: v for k, v in current_values_before.items() if v is not None}
    if exist_now:
        log_audit("snapshot", SNAPSHOT_TARGET, 0,
                  "回滚前退路快照：%d 项" % len(exist_now),
                  user=user, ip=ip, payload=current_values_before)

    changed, restored, skipped = [], 0, 0
    try:
        for k, v in before.items():
            if v is None:
                # 快照里该 key 为 None = 当时**没有这一项**。回滚应删除而非写空串，
                # 否则「让配置回到代码默认值」会变成「显式设成空」，语义不同。
                row_s = Setting.query.filter_by(key=k).first()
                if row_s is not None:
                    changed.append(k)
                    db.session.delete(row_s)
                    restored += 1
                else:
                    skipped += 1
                continue
            row_s = Setting.query.filter_by(key=k).first()
            if row_s is None:
                db.session.add(Setting(key=k, value=v))
                changed.append(k)
            else:
                row_s.value = v
                changed.append(k)
            restored += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return False, "回滚失败：%s" % str(e)[:200]

    log_audit("update", ROLLBACK_TARGET, snapshot_id,
              "回滚配置 %d 项（快照 #%d）：%s" % (restored, snapshot_id, ", ".join(changed[:20])),
              user=user, ip=ip)
    return True, "已回滚 %d 项配置（%d 项本就是目标值）" % (restored, skipped)


def purge_snapshots(keep=100):
    """只保留最近 keep 条快照（快照会随每次设置保存增长，需定期收口）。

    审计日志本身有 90 天保留策略，但快照体积大（每条几 KB），
    不主动裁剪的话审计表会明显膨胀。返回删除条数。
    """
    keep = max(1, int(keep))
    ids = (db.session.query(AuditLog.id).filter_by(target=SNAPSHOT_TARGET)
           .order_by(AuditLog.id.desc()).offset(keep).all())
    if not ids:
        return 0
    db.session.query(AuditLog).filter(AuditLog.id.in_([i[0] for i in ids])).delete(
        synchronize_session=False)
    db.session.commit()
    return len(ids)


def last_snapshot_at():
    """上次快照时间（供后台显示「多久没备份过配置」的粗略健康提示）。"""
    row = (AuditLog.query.filter_by(target=SNAPSHOT_TARGET)
           .order_by(AuditLog.id.desc()).first())
    return row.created_at if row else None


# 便于测试与脚本触发的显式时间引用（避免各处 from datetime import 造成风格漂移）
_snapshot_time = utcnow
