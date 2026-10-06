#!/usr/bin/env bash
# llhhy-blog 自动备份入口（v3.3.0）。
#
# 由宝塔「计划任务」每天调用一次，例如：
#   0 4 * * * bash /www/wwwroot/myblog/backup.sh
#
# 该脚本随后端发布包分发（位于 myblog/ 目录下），首次部署后：
#   1. 在宝塔计划任务里加一条「Shell 脚本」如上；
#   2. 如需异地容灾，在宝塔项目「环境变量」里配置 BACKUP_OSS_* / BACKUP_SCP_* /
#      BACKUP_WEBDAV_*（密钥只走环境变量，不写死）。
#
# 脚本仅依赖系统 python3（backup.py 用标准库实现，无需项目 venv）。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# v3.25.14：**必须先加载站点环境变量文件**（含 `SECRET_KEY`）。
#
# **为什么**：后台「⚙️ 备份配置」里填的 OSS Secret / WebDAV 密码是 Fernet 密文，
# 解密要用 `SECRET_KEY` 派生的密钥。gunicorn 由宝塔带 env 启动所以能解，
# 而**计划任务不带任何项目环境变量** → `decrypt_secret()` 返回空串（设计如此，不抛异常）
# → curl 拿空密码去认证 → 只得到一句 401，看不出真因。
# 结果就是「后台点测试一切正常、每天凌晨的备份却永远失败」（2026-10-06 线上实测）。
#
# 路径可用 `BACKUP_ENV_FILE` 覆盖；文件不存在就跳过（非宝塔部署不受影响）。
ENV_FILE="${BACKUP_ENV_FILE:-/www/server/pyporject_evn/myblog.env}"
if [ ! -r "$ENV_FILE" ]; then
  ENV_FILE="${BACKUP_ENV_FILE:-/www/server/python_project/vhost/env/myblog.env}"
fi
if [ -r "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "[$(date '+%F %T')] ⚠️ 未找到环境变量文件（$ENV_FILE）：若配置了异地容灾，" \
       "密文密钥将解不开（可用 BACKUP_ENV_FILE 指定路径）" >&2
fi

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[$(date '+%F %T')] 未找到 python，备份中止" >&2
  exit 1
fi

"$PY" backup.py run >> "$SCRIPT_DIR/backup.log" 2>&1
exit $?
