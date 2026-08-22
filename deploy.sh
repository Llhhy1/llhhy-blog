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
PROJECT_NAME="myblog"                      # 宝塔 Python 项目名称（默认 myblog）；若你宝塔里的项目名不同请改这里
APP_USER="mw"                              # gunicorn 进程运行用户（ps -ef 看到的属主；本机实测为 mw，非 www）
# ⚠️ 重要：宝塔 Python 项目【不是】用 supervisor 管理！它用自己的进程守护，进程属主是 mw。
#   脚本若以 root 运行，必须用「与进程同身份(mw)」去 kill / 启动，否则 Operation not permitted。
#   跨用户 kill 的正确做法：runuser -u mw -- kill ...（或 su mw -c），绝不能用 www（本机无此用户）。
GUNICORN_BIN="/ww/server/pyporject_evn/blog_env/bin/gunicorn"  # 宝塔托管的 gunicorn 真实路径（非项目 venv）
GUNICORN_CONF="$APP_DIR/gunicorn_conf.py" # 宝塔实际用的 conf 名（注意是 gunicorn_conf.py，不是 gunicorn.conf）
# 重启后端的方式（留空 → 脚本优先 bt CLI 重启，其次 runuser -u mw 真杀+宝塔 gunicorn 重新拉起）
#   如需手动指定重启命令可填：RESTART_CMD="bt stop myblog && bt start myblog"
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
#    ⚠️ 宝塔 Python 项目【不是】supervisor 管理，gunicorn 属主是 mw（非 www）。
#    正确做法：bt CLI 重启（最贴近面板停止→启动） → 否则以 mw 身份 runuser 真杀+宝塔 gunicorn 重新拉起。
#    绝不能用 www（本机无此用户），否则跨用户 kill 报 Operation not permitted。
RU=""
if [ "$(id -u)" = "0" ] && command -v runuser >/dev/null 2>&1; then
  RU="runuser -u $APP_USER --"
elif [ "$(id -u)" = "0" ] && command -v su >/dev/null 2>&1; then
  RU="su $APP_USER -c"
fi
if [ -n "$RESTART_CMD" ]; then
  log "执行重启命令..."
  eval "$RESTART_CMD"
elif command -v bt >/dev/null 2>&1 && [ -n "$PROJECT_NAME" ]; then
  # 优先宝塔 CLI（停止→启动，以正确身份执行，无权限问题）
  log "尝试通过宝塔 CLI 重启项目「$PROJECT_NAME」..."
  if bt stop "$PROJECT_NAME" >/dev/null 2>&1; then
    sleep 2
    if bt start "$PROJECT_NAME" >/dev/null 2>&1; then
      log "已通过宝塔 CLI 重启「$PROJECT_NAME」。"
    else
      log "⚠️ bt stop 成功但 bt start 失败，继续用 runuser 兜底..."
    fi
  else
    log "⚠️ bt stop 失败，继续用 runuser 兜底..."
  fi
fi
# 兜底：以 mw 身份真杀 + 用宝塔真实 gunicorn 路径重新拉起
pid=""
pidfile="$APP_DIR/gunicorn.pid"
if [ -f "$pidfile" ] && [ -s "$pidfile" ]; then
  pid=$(cat "$pidfile" 2>/dev/null | tr -d '[:space:]' | head -1)
  case "$pid" in
    ''|*[!0-9]*) pid="" ;;
  esac
  if [ -n "$pid" ] && ! $RU kill -0 "$pid" 2>/dev/null; then pid=""; fi
fi
if [ -z "$pid" ]; then
  pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1)
fi
if [ -n "$pid" ]; then
  log "找到 gunicorn master pid=$pid，以 $APP_USER 身份发送 TERM 真正停止..."
  if ! $RU kill -TERM "$pid" 2>/dev/null; then
    log "❌ 无法终止进程 pid=$pid（权限不足）。请检查 APP_USER 是否为实际进程属主（ps -ef | grep gunicorn）。"
    log "⚠️ 代码已更新但未重启，请手动在宝塔「停止→启动」。"
  else
    waited=0
    while $RU kill -0 "$pid" 2>/dev/null && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    $RU kill -0 "$pid" 2>/dev/null && { $RU pkill -9 -f "gunicorn.*$APP_DIR" 2>/dev/null || true; }
    sleep 1
    log "旧进程已停止。"
  fi
else
  log "未发现运行中的 gunicorn 进程，直接进入启动。"
fi
# 用宝塔真实 gunicorn 路径重新拉起（与 ps 里看到的命令行一致）
if [ -x "$GUNICORN_BIN" ] && [ -f "$GUNICORN_CONF" ]; then
  log "用宝塔 gunicorn 重新拉起：$RU $GUNICORN_BIN -c $GUNICORN_CONF app:app"
  ( cd "$APP_DIR" && $RU env "HOME=/www/wwwroot" "$GUNICORN_BIN" -c "$GUNICORN_CONF" app:app >/www/wwwroot/myblog/gunicorn.log 2>&1 & )
  sleep 3
  if pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
    log "已用宝塔 gunicorn 重新启动（停止→启动 完成）。"
  else
    log "⚠️ 启动后未检测到 gunicorn 进程，请检查 gunicorn.log；或手动在宝塔「停止→启动」。"
  fi
else
  log "⚠️ 未找到宝塔 gunicorn（$GUNICORN_BIN）或 conf（$GUNICORN_CONF），代码已更新但未重启。请手动在宝塔「停止→启动」。"
fi

log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"
