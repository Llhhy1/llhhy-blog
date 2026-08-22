#!/usr/bin/env bash
# =============================================================
# llhhy-blog 自动部署脚本（D3 · 由 /api/webhook/deploy 触发）
# 作用：从 GitHub Release 下载最新部署包 → 备份数据 → 覆盖代码 → 重启项目
# 用法：
#   1. 上传本脚本到服务器：/www/wwwroot/myblog/deploy.sh
#   2. 宝塔终端执行：chmod +x /www/wwwroot/myblog/deploy.sh
#   3. 宝塔「Python项目 → 设置 → 环境变量」加：DEPLOY_SCRIPT=/www/wwwroot/myblog/deploy.sh
#   4. GitHub 仓库 Webhook 配置（见 deploy_guide.md「自动部署」章节）
# =============================================================
set -e

# ===== 以下按你的服务器实际修改 =====
REPO="Llhhy1/llhhy-blog"            # GitHub 仓库（owner/repo）
APP_DIR="/www/wwwroot/myblog"       # 后端运行目录（Python 项目路径，必填）
FRONT_DIR="/www/wwwroot/vue-frontend"  # 前端静态目录（Nginx 网站根）
# 重启后端的方式（宝塔环境任选其一）：
#   A. 宝塔已装 supervisor：sudo supervisorctl restart myblog
#   B. 宝塔计划任务/服务：/etc/init.d/myblog restart
#   C. 留空 → 脚本自动「真杀 gunicorn(Term) + 用 data/start_cmd.txt 重新拉起」
# ⚠️ v3.0.0 修复：严禁 HUP 热重载（master 不退出会导致旧代码仍在跑）。
#    首次全自动需先在服务器用你的启动命令跑一次并记录：
#      echo 'nohup /path/to/gunicorn -w 3 -b 127.0.0.1:8000 app:app >/www/wwwroot/myblog/gunicorn.log 2>&1 &' > /www/wwwroot/myblog/data/start_cmd.txt
RESTART_CMD=""

# ===== 以下一般不用改 =====
WORK="/tmp/llhhy_deploy"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"

log(){ echo "[$(date '+%F %T')] $*"; }

log "开始自动部署（$REPO）..."
cd "$WORK"

# 1. 获取最新 Release 的 zip 下载地址（GitHub API，公开仓库无需 token）
LATEST_JSON=$(curl -fsSL --connect-timeout 15 "https://api.github.com/repos/$REPO/releases/latest")
BACKEND_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*myblog-backend.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
FRONT_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*vue-frontend-dist.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
TAG=$(echo "$LATEST_JSON" | grep -o '"tag_name": *"[^"]*"' | sed 's/.*"\([^"]*\)".*/\1/' | head -1)
if [ -z "$BACKEND_URL" ] || [ -z "$FRONT_URL" ]; then
  log "❌ 未找到最新 Release 的部署包（tag=$TAG），中止。"
  exit 1
fi
log "最新版本: $TAG"

# 2. 下载两个 zip
curl -fsSL --connect-timeout 30 -o backend.zip "$BACKEND_URL"
curl -fsSL --connect-timeout 30 -o frontend.zip "$FRONT_URL"
log "下载完成（backend.zip / frontend.zip）"

# 3. 备份数据（数据库 + 上传图片）—— 数据永远不覆盖，只备份留底
if [ -f "$APP_DIR/data/blog.db" ]; then
  mkdir -p "$APP_DIR/data/backup"
  cp "$APP_DIR/data/blog.db" "$APP_DIR/data/backup/blog_$TS.db"
  log "已备份数据库 → data/backup/blog_$TS.db"
fi
if [ -d "$APP_DIR/static/uploads" ]; then
  mkdir -p "$APP_DIR/data/backup"
  cp -r "$APP_DIR/static/uploads" "$APP_DIR/data/backup/uploads_$TS"
  log "已备份上传图片 → data/backup/uploads_$TS"
fi

# 4. 解压覆盖后端（zip 内自带一层 myblog/，解压到 APP_DIR 的上一级后合并）
rm -rf backend_extract && mkdir backend_extract
unzip -q backend.zip -d backend_extract
rsync -a --exclude='data' --exclude='__pycache__' backend_extract/myblog/ "$APP_DIR/"
log "后端代码已覆盖（跳过 data/，数据库保留）"

# 5. 解压覆盖前端（zip 根直接是 index.html + assets/）
if [ -d "$FRONT_DIR" ]; then
  rm -rf frontend_extract && mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract
  cp -r frontend_extract/. "$FRONT_DIR/"
  log "前端静态文件已覆盖"
else
  log "⚠️ 前端目录 $FRONT_DIR 不存在，跳过前端覆盖（请检查路径）"
fi

# 6. 重启后端（Python 项目）—— 真杀 + 真启动（严禁 HUP）
if [ -n "$RESTART_CMD" ]; then
  log "执行重启命令..."
  eval "$RESTART_CMD"
elif [ -f "$APP_DIR/data/start_cmd.txt" ]; then
  # 有记录的启动命令 → 先真杀旧 gunicorn，再拉起
  pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1)
  [ -z "$pid" ] && pid=$(pgrep -f "gunicorn" 2>/dev/null | head -1)
  [ -n "$pid" ] && { kill -TERM "$pid" 2>/dev/null; sleep 3; pkill -9 -f "gunicorn" 2>/dev/null || true; }
  start_cmd=$(cat "$APP_DIR/data/start_cmd.txt")
  log "用记录的启动命令重新拉起：$start_cmd"
  eval "$start_cmd"
else
  log "⚠️ 未配置 RESTART_CMD 且无 start_cmd.txt，代码已更新但未重启。请手动在宝塔「停止→启动」。"
fi

log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"
