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

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[$(date '+%F %T')] 未找到 python，备份中止" >&2
  exit 1
fi

"$PY" backup.py run >> "$SCRIPT_DIR/backup.log" 2>&1
exit $?
