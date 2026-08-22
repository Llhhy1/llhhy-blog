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
#   C. 留空 → 脚本优先自动探测 supervisor 项目（PROJECT_NAME）并 restart；
#           若没有 supervisor，则「真杀 gunicorn(Term) + 用 data/start_cmd.txt 重新拉起」
# ⚠️ v3.1.2 修复：宝塔 Python 项目底层由 supervisor 以 www 身份管理 gunicorn，
#   脚本若以 root 或其他身份运行，直接 kill 该进程会 Operation not permitted。
#   因此默认优先走 supervisorctl restart（以正确身份停+起），彻底绕开跨用户 kill 权限问题。
#   如需手动指定重启命令可填：RESTART_CMD="supervisorctl restart myblog"
RESTART_CMD=""
PROJECT_NAME="myblog"                      # 宝塔 Python 项目名称（默认 myblog）；若你宝塔里的项目名不同请改这里

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
#    v3.1.2 修复：优先 supervisorctl restart（以 www 身份由 supervisor 管理，无跨用户 kill 权限问题）；
#       其次才走「读 pidfile 精确杀」。若脚本以 root 运行而 gunicorn 属主是 www，kill 会无权限，
#       故 kill/pkill 自动加 sudo -u www 保护。
#    v3.1.1 修复：优先读 gunicorn 自己的 pidfile（配置里 pidfile=/www/wwwroot/myblog/gunicorn.pid），
#       只杀「自己这个 master pid」，绝不 pkill -f "gunicorn" 粗放匹配——否则会误匹配到 root 启动的
#       其他 gunicorn 进程，导致 Operation not permitted。
SUC=""
if [ "$(id -u)" = "0" ] && command -v sudo >/dev/null 2>&1; then SUC="sudo -u www"; fi
if [ -n "$RESTART_CMD" ]; then
  log "执行重启命令..."
  eval "$RESTART_CMD"
elif command -v supervisorctl >/dev/null 2>&1; then
  # 优先 supervisor（以正确身份停+起，绕过跨用户 kill 权限问题）
  if [ -n "$PROJECT_NAME" ]; then
    if eval "$SUC supervisorctl status $PROJECT_NAME" >/dev/null 2>&1; then
      eval "$SUC supervisorctl restart $PROJECT_NAME" && log "已通过 supervisor 重启「$PROJECT_NAME」。"
      log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"
      exit 0
    fi
    log "⚠️ supervisor 中找不到项目「$PROJECT_NAME」，尝试 start_cmd.txt 兜底..."
  fi
  for conf in /etc/supervisor/conf.d/*.conf /www/server/panel/plugin/supervisor/*.conf; do
    [ -f "$conf" ] || continue
    if grep -q "$APP_DIR" "$conf" 2>/dev/null; then
      name=$(basename "$conf" .conf)
      if eval "$SUC supervisorctl status $name" >/dev/null 2>&1; then
        eval "$SUC supervisorctl restart $name" && log "已自动探测并重启 supervisor 项目「$name」。"
        log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"
        exit 0
      fi
    fi
  done
  log "⚠️ 未探测到 supervisor 项目，尝试 start_cmd.txt 兜底..."
fi
if [ -f "$APP_DIR/data/start_cmd.txt" ]; then
  # 有记录的启动命令 → 先精确真杀旧 gunicorn，再拉起
  pid=""
  pidfile="$APP_DIR/gunicorn.pid"
  KILL="kill"; PKILL="pkill"; KILL0="kill -0"
  if [ "$(id -u)" = "0" ] && command -v sudo >/dev/null 2>&1; then
    KILL="sudo -u www kill"; PKILL="sudo -u www pkill"; KILL0="sudo -u www kill -0"
  fi
  if [ -f "$pidfile" ] && [ -s "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null | tr -d '[:space:]' | head -1)
    case "$pid" in
      ''|*[!0-9]*) pid="" ;;
    esac
    if [ -n "$pid" ] && ! $KILL0 "$pid" 2>/dev/null; then pid=""; fi
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1)
  fi
  if [ -n "$pid" ]; then
    log "找到 gunicorn master pid=$pid，发送 TERM 真正停止..."
    if ! $KILL -TERM "$pid" 2>/dev/null; then
      log "❌ 无法终止进程 pid=$pid（权限不足？是否跨用户运行）。请手动在宝塔重启项目（停止→启动）。"
      exit 1
    fi
    waited=0
    while $KILL0 "$pid" 2>/dev/null && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    $KILL0 "$pid" 2>/dev/null && { $PKILL -9 -f "gunicorn.*$APP_DIR" 2>/dev/null || true; }
    sleep 1
    log "旧进程已停止。"
  else
    log "未发现运行中的 gunicorn 进程，直接进入启动。"
  fi
  start_cmd=$(cat "$APP_DIR/data/start_cmd.txt")
  log "用记录的启动命令重新拉起：$start_cmd"
  if ! eval "$start_cmd"; then
    log "⚠️ 启动命令执行失败，尝试用 gunicorn.conf 兜底..."
    conf="$APP_DIR/gunicorn.conf"
    [ -f "$conf" ] || conf="$APP_DIR/gunicorn.conf.py"
    if [ -f "$conf" ]; then
      gun="$APP_DIR/venv/bin/gunicorn"
      command -v gunicorn >/dev/null 2>&1 && gun="${gun:-gunicorn}"
      if [ -x "$APP_DIR/venv/bin/gunicorn" ] || command -v gunicorn >/dev/null 2>&1; then
        ( cd "$APP_DIR" && nohup "${gun:-gunicorn}" -c "$conf" app:app >/www/wwwroot/myblog/gunicorn.log 2>&1 & )
        sleep 2
        log "已用 gunicorn.conf 兜底重新拉起。"
      fi
    fi
  fi
else
  log "⚠️ 未配置 RESTART_CMD 且无 start_cmd.txt，代码已更新但未重启。请手动在宝塔「停止→启动」。"
fi

log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"
