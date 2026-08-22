#!/usr/bin/env bash
# =============================================================
# llhhy-blog 一键更新脚本（懒人版 · 全自动，连重启都不用点）
# 作用：自动完成「下载最新 Release → 备份数据 → 覆盖代码 → 自动重启后端」
# 用法：
#   手动（宝塔终端）：bash /www/wwwroot/myblog/update.sh
#   后台触发（v2.5.0+）：由「后台 → 检测到新版本 → 确认更新」自动调用，
#     脚本会写状态文件 data/update_status.json（后台轮询显示进度）。
# 自动重启原理：宝塔「Python项目」底层用 supervisor 管理 gunicorn，
#   脚本会自动探测 supervisor 里的项目进程名并 restart；
#   若没装 supervisor，则热重载 gunicorn 兜底（加载新代码）。
# =============================================================
set -e

# ===== 首次使用：按你的服务器改这几行 =====
REPO="Llhhy1/llhhy-blog"                 # GitHub 仓库，一般不用改
APP_DIR="/www/wwwroot/myblog"            # 后端运行目录（Python 项目路径）
FRONT_DIR="/www/wwwroot/vue-frontend"    # 前端静态目录（Nginx 网站根）
PROJECT_NAME=""                          # 宝塔 Python 项目名称（如 myblog）；留空则自动探测
# 手动指定重启命令时填（优先使用，覆盖自动探测）：
#   RESTART_CMD="supervisorctl restart myblog"
RESTART_CMD=""

WORK="/tmp/llhhy_update"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"
log(){ echo "[$(date '+%F %T')] $*"; }

# ===== 状态文件（后台在线更新轮询用）=====
STATUS_FILE="$APP_DIR/data/update_status.json"
set_status() {  # set_status <status> <message>
  local st="$1" msg="$2"
  mkdir -p "$(dirname "$STATUS_FILE")"
  printf '{"status":"%s","version":"%s","ts":"%s","message":"%s"}\n' \
    "$st" "${TAG:-}" "$(date '+%F %T')" "$msg" > "$STATUS_FILE"
}
# fail_exit 记录具体失败原因；trap 只在无具体原因时才补通用信息（v2.6.3 修复覆盖 bug）
FAIL_MSG=""
fail_exit() {
  FAIL_MSG="$1"
  set_status "failed" "$1"
  log "❌ $1"
  exit 1
}
trap 'rc=$?; if [ $rc -ne 0 ]; then set_status "failed" "${FAIL_MSG:-脚本异常退出(码$rc)，详见后端日志 data/update_log.txt}"; fi' EXIT

# ===== 网络请求函数：GitHub 失败时自动重试 3 次 + 镜像代理兜底（国内服务器，v2.6.3）=====
# 若服务器无法直连 GitHub（国内常见），可把直连 URL 换成镜像代理前缀：
#   可用镜像（任选其一，必要时手动换）：
#     https://ghfast.top/https://github.com/...
#     https://gh-proxy.com/https://github.com/...
#     https://ghproxy.net/https://github.com/...
GH_MIRROR="${GH_MIRROR:-}"   # 留空则直连；可手动设为如 "https://ghfast.top/"
gh_fetch() {  # gh_fetch <url> <outfile|->
  local url="$1" out="$2" attempt=0 try_urls
  # 组装尝试列表：直连 → 镜像（若配置）→ GitHub 加速镜像（仅当直连域名是 github.com 时）
  try_urls=("$url")
  if [ -n "$GH_MIRROR" ]; then
    try_urls+=("${GH_MIRROR}${url}")
  fi
  case "$url" in
    *"//github.com/"*)
      try_urls+=("https://ghfast.top/${url}" "https://gh-proxy.com/${url}" "https://ghproxy.net/${url}")
      ;;
  esac
  for tu in "${try_urls[@]}"; do
    attempt=0
    while [ $attempt -lt 2 ]; do
      attempt=$((attempt + 1))
      log "   尝试下载: $tu (第 $attempt/2 次)"
      if [ "$out" = "-" ]; then
        if curl -fsSL --connect-timeout 20 --max-time 90 "$tu"; then return 0; fi
      else
        if curl -fsSL --connect-timeout 20 --max-time 180 -o "$out" "$tu"; then return 0; fi
      fi
      [ $attempt -lt 2 ] && sleep 2
    done
  done
  return 1
}

# ===== 自动重启函数：优先 supervisor，其次「真杀+真启动」，最后提示 =====
# ⚠️ 关键修复（v3.0.0）：严禁用 HUP 热重载！
#    HUP 只让 gunicorn master fork 新 worker，master 不退出；当改了 import / 表结构时，
#    老 worker 仍在服务旧代码，表现为「更新完不重启 / 还是旧版」。
#    正确做法 = 真杀 master（TERM）→ 等退出 → 用原启动命令重新拉起（停止→启动）。
auto_restart() {
  log "⑥ 重启后端服务..."
  # 1. 用户手动指定了重启命令 → 直接用（supervisor restart 本身是 停+起，安全）
  if [ -n "$RESTART_CMD" ]; then
    if eval "$RESTART_CMD"; then log "   重启命令执行成功。"; return 0; fi
    log "   ⚠️ 重启命令执行失败，尝试自动探测..."
  fi
  # 2. 探测 supervisor 管理的项目（宝塔 Python 项目默认走 supervisor）
  if command -v supervisorctl >/dev/null 2>&1; then
    if [ -n "$PROJECT_NAME" ]; then
      if supervisorctl status "$PROJECT_NAME" >/dev/null 2>&1; then
        supervisorctl restart "$PROJECT_NAME" && log "   已通过 supervisor 重启「$PROJECT_NAME」。"
        return 0
      fi
      log "   ⚠️ supervisor 中找不到项目「$PROJECT_NAME」，继续探测..."
    fi
    for conf in /etc/supervisor/conf.d/*.conf /www/server/panel/plugin/supervisor/*.conf; do
      [ -f "$conf" ] || continue
      if grep -q "$APP_DIR" "$conf" 2>/dev/null; then
        name=$(basename "$conf" .conf)
        if supervisorctl status "$name" >/dev/null 2>&1; then
          supervisorctl restart "$name" && log "   已自动探测并重启 supervisor 项目「$name」。"
          return 0
        fi
      fi
    done
  fi
  # 3. 兜底：真杀旧 gunicorn master（TERM）→ 等退出 → 用记住的启动命令重新拉起
  #    3a. 找到 gunicorn master（注意：master 进程本身不带 worker 计数，用 pgrep 取主）
  local pid
  pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1)
  [ -z "$pid" ] && pid=$(pgrep -f "gunicorn" 2>/dev/null | head -1)
  if [ -n "$pid" ]; then
    log "   找到 gunicorn 进程 pid=$pid，发送 TERM 真正停止..."
    kill -TERM "$pid" 2>/dev/null || pkill -TERM -f "gunicorn"
    # 等待进程真正退出（最多 15 秒）
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    pkill -9 -f "gunicorn" 2>/dev/null || true   # 兜底强杀残留 worker
    sleep 1
    log "   旧进程已停止。"
  else
    log "   未发现运行中的 gunicorn 进程（可能已停止），直接进入启动。"
  fi
  # 3b. 用记住的启动命令重新拉起（首次需手动启动一次以记录，见下方说明）
  local start_cmd
  start_cmd=$(cat "$APP_DIR/data/start_cmd.txt" 2>/dev/null)
  if [ -n "$start_cmd" ]; then
    log "   用记录的启动命令重新拉起：$start_cmd"
    eval "$start_cmd" && { log "   已重新启动（停止→启动 完成）。"; return 0; }
    log "   ⚠️ 启动命令执行失败，请检查 start_cmd.txt 内容。"
  else
    log "   ⚠️ 未发现记录的启动命令（data/start_cmd.txt）。"
  fi
  # 4. 都失败 → 提示手动（并告诉用户如何记录启动命令）
  log "   ⚠️ 无法自动重启。请手动在宝塔「网站 → Python项目」点「停止」再「启动」；"
  log "      若想以后全自动：在服务器上用你的启动命令跑一次并追加 'echo 命令 > $APP_DIR/data/start_cmd.txt' 记录它。"
  set_status "partial" "代码已更新，但自动重启未生效，请手动在宝塔重启项目（停止→启动）"
}

set_status "started" "开始更新"

log "==============================================="
log " 一键更新 llhhy-blog（懒人版 · 自动下载+备份+覆盖+重启）"
log "==============================================="
cd "$WORK"

# 1. 查询最新 Release 的下载地址
log "① 查询 GitHub 最新版本..."
set_status "downloading" "正在查询最新版本"
LATEST_JSON=$(gh_fetch "https://api.github.com/repos/$REPO/releases/latest" "-") || \
  fail_exit "获取 GitHub 最新版本失败（网络不通或 GitHub 被墙）。请检查服务器能否访问 GitHub，或用宝塔终端手动运行：bash /www/wwwroot/myblog/update.sh 查看日志"
TAG=$(echo "$LATEST_JSON" | grep -o '"tag_name": *"[^"]*"' | sed 's/.*"\([^"]*\)".*/\1/' | head -1)
BACKEND_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*myblog-backend.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
FRONT_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*vue-frontend-dist.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
if [ -z "$TAG" ] || [ -z "$BACKEND_URL" ]; then
  fail_exit "未找到最新 Release 部署包（tag=$TAG），请稍后重试"
fi
log "   最新版本：$TAG"

# 2. 下载
log "② 下载部署包..."
set_status "downloading" "正在下载部署包（$TAG）"
gh_fetch "$BACKEND_URL" "backend.zip" || fail_exit "后端包下载失败（网络问题）。请检查服务器能否访问 GitHub 下载链接"
gh_fetch "$FRONT_URL" "frontend.zip" || fail_exit "前端包下载失败（网络问题）。请检查服务器能否访问 GitHub 下载链接"
log "   下载完成。"

# 3. 备份数据（数据库 + 上传图片，永远不覆盖）
log "③ 备份数据..."
set_status "backing_up" "正在备份数据"
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
set_status "deploying" "正在覆盖后端代码"
rm -rf backend_extract && mkdir backend_extract
unzip -q backend.zip -d backend_extract || fail_exit "后端包解压失败（文件可能损坏）"
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
  set_status "deploying" "正在覆盖前端文件"
  rm -rf frontend_extract && mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract || fail_exit "前端包解压失败"
  cp -r frontend_extract/. "$FRONT_DIR/"
  log "   完成。"
else
  log "   ⚠️ 前端目录 $FRONT_DIR 不存在，跳过（请检查路径）。"
fi

# 6. 自动重启后端
set_status "restarting" "正在重启后端服务"
auto_restart

set_status "done" "更新完成，请刷新页面"
log "==============================================="
log "✅ 全部完成！代码已更新到 $TAG"
log "   后台左下角版本号应为 $TAG；若无痕窗口打开还是旧版，"
log "   请去宝塔「网站 → Python项目」手动「停止→启动」一次。"
log "==============================================="
trap - EXIT
