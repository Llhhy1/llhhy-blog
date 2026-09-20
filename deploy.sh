#!/usr/bin/env bash
# =============================================================
# llhhy-blog 自动部署入口（由 /api/webhook/deploy 触发，GitHub Webhook → 自动部署）
#
# v3.18.7 起，本脚本**只是 update.sh 的薄封装**。
#   历史上这里是 update.sh 的一份独立副本，两份各自演化 → 完整性校验长期不同步：
#   本副本停在更弱的一版（sha256.txt 缺失 / 下载失败 / 清单里查不到该文件时会**静默跳过**
#   校验，且会自动兜底第三方镜像代理），等于给同一条更新链留了两个安全面不一致的入口。
#   现统一委派给 update.sh —— 单一实现、单一审计面；Webhook 路径自动获得同等的
#   Ed25519 发布物签名校验与 fail-closed 完整性校验。
#
# 用法不变（宝塔「Python项目 → 设置 → 环境变量」）：
#   DEPLOY_SCRIPT=/www/wwwroot/myblog/deploy.sh
# 需要不同的部署行为时，请直接改 update.sh（当前唯一实现），不要再复制一份出来。
#
# 部署三铁律（沿用）：真实目录用 ls /www/wwwroot/*/data/blog.db 定位；
#   gunicorn「停止 → 启动」（非重启）；脚本必须 LF 行尾。
# =============================================================
set -euo pipefail

DEFAULT_APP_DIR="/www/wwwroot/myblog"
APP_DIR="${APP_DIR:-$DEFAULT_APP_DIR}"

TARGET="$APP_DIR/update.sh"
if [ ! -f "$TARGET" ]; then
  # 兼容脚本被放在非默认目录的情况：退化为「与本脚本同目录的 update.sh」
  SELF_DIR=$(cd "$(dirname "$0")" && pwd)
  if [ -f "$SELF_DIR/update.sh" ]; then
    TARGET="$SELF_DIR/update.sh"
  fi
fi

if [ ! -f "$TARGET" ]; then
  echo "❌ 找不到 update.sh（已尝试 $APP_DIR/update.sh 与本脚本同目录），无法部署。" >&2
  exit 1
fi

exec bash "$TARGET"
