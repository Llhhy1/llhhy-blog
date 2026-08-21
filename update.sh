#!/usr/bin/env bash
# =============================================================
# llhhy-blog 一键更新脚本（最简方式，无需 Webhook / 无需环境变量）
# 作用：自动完成「下载最新 Release → 备份数据 → 覆盖代码 → 提示重启」
# 用法（宝塔终端执行，一行搞定）：
#   bash /www/wwwroot/myblog/update.sh
# 效果：脚本帮你做了平时手动更新的全部步骤，唯一需要你做的
#       是最后按提示去宝塔点一下「停止→启动」（或配置自动重启）。
# =============================================================
set -e

# ===== 首次使用：按你的服务器改这 3 行 =====
REPO="Llhhy1/llhhy-blog"                 # GitHub 仓库，一般不用改
APP_DIR="/www/wwwroot/myblog"            # 后端运行目录（Python 项目路径）
FRONT_DIR="/www/wwwroot/vue-frontend"    # 前端静态目录（Nginx 网站根）
# 可选：想自动重启就填一行命令（宝塔装了 supervisor 可填：supervisorctl restart myblog）
RESTART_CMD=""

WORK="/tmp/llhhy_update"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"
log(){ echo "[$(date '+%F %T')] $*"; }

log "==============================================="
log " 一键更新 llhhy-blog（自动下载最新 Release）"
log "==============================================="
cd "$WORK"

# 1. 查询最新 Release 的下载地址
log "① 查询 GitHub 最新版本..."
LATEST_JSON=$(curl -fsSL --connect-timeout 15 "https://api.github.com/repos/$REPO/releases/latest")
TAG=$(echo "$LATEST_JSON" | grep -o '"tag_name": *"[^"]*"' | sed 's/.*"\([^"]*\)".*/\1/' | head -1)
BACKEND_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*myblog-backend.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
FRONT_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*vue-frontend-dist.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
if [ -z "$TAG" ] || [ -z "$BACKEND_URL" ]; then
  log "❌ 获取最新版本失败（网络问题或仓库名错误），请重试。"
  exit 1
fi
log "   最新版本：$TAG"

# 2. 下载
log "② 下载部署包..."
curl -fsSL --connect-timeout 30 -o backend.zip "$BACKEND_URL"
curl -fsSL --connect-timeout 30 -o frontend.zip "$FRONT_URL"
log "   下载完成。"

# 3. 备份数据（数据库 + 上传图片，永远不覆盖）
log "③ 备份数据..."
BACKUP_DIR="$APP_DIR/data/backup"
if [ -f "$APP_DIR/data/blog.db" ]; then
  mkdir -p "$BACKUP_DIR"
  cp "$APP_DIR/data/blog.db" "$BACKUP_DIR/blog_$TS.db"
  log "   数据库 → $BACKUP_DIR/blog_$TS.db"
fi
if [ -d "$APP_DIR/static/uploads" ]; then
  mkdir -p "$BACKUP_DIR"
  cp -r "$APP_DIR/static/uploads" "$BACKUP_DIR/uploads_$TS"
  log "   上传图片 → $BACKUP_DIR/uploads_$TS"
fi

# 4. 覆盖后端（跳过 data/，数据库保留）
log "④ 覆盖后端代码..."
rm -rf backend_extract && mkdir backend_extract
unzip -q backend.zip -d backend_extract
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude='data' --exclude='__pycache__' backend_extract/myblog/ "$APP_DIR/"
else
  # 无 rsync 时用 cp 逐个拷贝（排除 data）
  find backend_extract/myblog -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec cp -r {} "$APP_DIR/" \;
fi
log "   完成（data/ 数据库保留）。"

# 5. 覆盖前端
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  rm -rf frontend_extract && mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract
  cp -r frontend_extract/. "$FRONT_DIR/"
  log "   完成。"
else
  log "   ⚠️ 前端目录 $FRONT_DIR 不存在，跳过（请检查路径）。"
fi

# 6. 重启提示
log "==============================================="
log "✅ 代码已更新到 $TAG"
if [ -n "$RESTART_CMD" ]; then
  log "⑥ 自动重启后端..."
  eval "$RESTART_CMD" || log "   自动重启失败，请手动在宝塔重启。"
else
  log "⑥ 最后一步（必做）：去宝塔「网站 → Python项目」→ 点「停止」再「启动」。"
  log "   然后浏览器无痕打开后台，左下角版本号应为 $TAG。"
fi
log "==============================================="
