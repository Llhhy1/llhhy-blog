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
PROJECT_NAME="myblog"                      # 宝塔 Python 项目名称（默认 myblog）；若你宝塔里的项目名不同请改这里
APP_USER="mw"                              # gunicorn 进程运行用户（ps -ef 看到的属主；本机实测为 mw，非 www）
# ⚠️ 重要：宝塔 Python 项目【不是】用 supervisor 管理！它用自己的进程守护，进程属主是 mw。
#   脚本若以 root 运行，必须用「与进程同身份(mw)」去 kill / 启动，否则 Operation not permitted。
#   跨用户 kill 的正确做法：runuser -u mw -- kill ...（或 su mw -c），绝不能用 www（本机无此用户）。
GUNICORN_BIN="/ww/server/pyporject_evn/blog_env/bin/gunicorn"  # 宝塔托管的 gunicorn 真实路径（非项目 venv）
GUNICORN_CONF="$APP_DIR/gunicorn_conf.py" # 宝塔实际用的 conf 名（注意是 gunicorn_conf.py，不是 gunicorn.conf）
# 手动指定重启命令时填（优先使用，覆盖自动探测）：
#   RESTART_CMD="bt stop myblog && bt start myblog"
RESTART_CMD=""

# ===== 自动以 APP_USER 身份运行（避免跨身份 rm/cp 权限失败）=====
# 若当前是 root 且不是 APP_USER，重跑本脚本为 APP_USER（保留参数）。
# mw 对 /www/wwwroot/myblog 及其下文件有完整权限，可正常 rm/cp/写状态文件。
if [ "$(id -u)" = "0" ] && [ "$(id -un)" != "$APP_USER" ]; then
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u "$APP_USER" -- bash "$0" "$@"
  elif command -v su >/dev/null 2>&1; then
    exec su "$APP_USER" -c "bash $0 $*"
  fi
fi

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
  # 0. 用户手动指定了重启命令 → 直接用（优先级最高，覆盖自动探测）
  if [ -n "$RESTART_CMD" ]; then
    if eval "$RESTART_CMD"; then log "   重启命令执行成功。"; return 0; fi
    log "   ⚠️ 重启命令执行失败，尝试自动探测..."
  fi
  # 1. 宝塔 CLI 重启（最贴近面板「停止→启动」行为，且以正确身份执行，无权限问题）
  #    bt 命令参数：bt stop <项目名> / bt start <项目名>（项目名=PROJECT_NAME）
  if command -v bt >/dev/null 2>&1 && [ -n "$PROJECT_NAME" ]; then
    log "   尝试通过宝塔 CLI 重启项目「$PROJECT_NAME」..."
    if bt stop "$PROJECT_NAME" >/dev/null 2>&1; then
      sleep 2
      if bt start "$PROJECT_NAME" >/dev/null 2>&1; then
        log "   已通过宝塔 CLI 重启「$PROJECT_NAME」。"
        return 0
      fi
      log "   ⚠️ bt stop 成功但 bt start 失败，继续用 runuser 兜底..."
    else
      log "   ⚠️ bt stop 失败，继续用 runuser 兜底..."
    fi
  fi
  # 2. 以进程属主身份真杀 + 真启动（runuser -u <APP_USER>，同身份不再跨用户权限失败）
  #    ⚠️ 关键：宝塔 gunicorn 属主是 mw（非 www），必须用 runuser -u mw 操作，绝不能用 www。
  local RU=""
  if [ "$(id -u)" = "0" ] && command -v runuser >/dev/null 2>&1; then
    RU="runuser -u $APP_USER --"
  elif [ "$(id -u)" = "0" ] && command -v su >/dev/null 2>&1; then
    RU="su $APP_USER -c"
  fi
  # 2a. 查找 master pid：优先 pidfile，其次精确匹配本项目的 gunicorn
  local pid pidfile="$APP_DIR/gunicorn.pid"
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
    log "   找到 gunicorn master pid=$pid，以 $APP_USER 身份发送 TERM 真正停止..."
    if ! $RU kill -TERM "$pid" 2>/dev/null; then
      log "   ❌ 无法终止进程 pid=$pid（权限不足）。请检查 APP_USER 是否为实际进程属主（ps -ef | grep gunicorn）。"
      set_status "partial" "代码已更新，但终止旧进程失败(权限不足)，请手动在宝塔重启项目（停止→启动）"
      return 1
    fi
    local waited=0
    while $RU kill -0 "$pid" 2>/dev/null && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    $RU kill -0 "$pid" 2>/dev/null && { $RU pkill -9 -f "gunicorn.*$APP_DIR" 2>/dev/null || true; }
    sleep 1
    log "   旧进程已停止。"
  else
    log "   未发现运行中的 gunicorn 进程（可能已停止），直接进入启动。"
  fi
  # 2b. 用宝塔真实 gunicorn 路径重新拉起（与 ps 里看到的命令行一致）
  if [ -x "$GUNICORN_BIN" ] && [ -f "$GUNICORN_CONF" ]; then
    log "   用宝塔 gunicorn 重新拉起：$RU $GUNICORN_BIN -c $GUNICORN_CONF app:app"
    ( cd "$APP_DIR" && $RU env "HOME=/www/wwwroot" "$GUNICORN_BIN" -c "$GUNICORN_CONF" app:app >/www/wwwroot/myblog/gunicorn.log 2>&1 & )
    sleep 3
    if pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
      log "   已用宝塔 gunicorn 重新启动（停止→启动 完成）。"
      return 0
    fi
    log "   ⚠️ 启动后未检测到 gunicorn 进程，请检查 gunicorn.log。"
  else
    log "   ⚠️ 未找到宝塔 gunicorn（$GUNICORN_BIN）或 conf（$GUNICORN_CONF）。"
  fi
  # 3. 都失败 → 提示手动
  log "   ⚠️ 无法自动重启。请手动在宝塔「网站 → Python项目」点「停止」再「启动」。"
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
CHECKSUM_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*sha256.txt"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
if [ -z "$TAG" ] || [ -z "$BACKEND_URL" ]; then
  fail_exit "未找到最新 Release 部署包（tag=$TAG），请稍后重试"
fi
log "   最新版本：$TAG"

# 2. 下载
log "② 下载部署包..."
set_status "downloading" "正在下载部署包（$TAG）"
gh_fetch "$BACKEND_URL" "backend.zip" || fail_exit "后端包下载失败（网络问题）。请检查服务器能否访问 GitHub 下载链接"
gh_fetch "$FRONT_URL" "frontend.zip" || fail_exit "前端包下载失败（网络问题）。请检查服务器能否访问 GitHub 下载链接"
# 2b. 完整性校验：下载 sha256.txt 并比对，防中间人篡改 / 下载损坏
verify_checksum() {  # verify_checksum <file> <expected_name>
  local f="$1" expect_name="$2" want got
  if [ -z "$CHECKSUM_URL" ]; then
    log "   ⚠️ Release 未附带 sha256.txt，跳过哈希校验（建议发布时附带）。"
    return 0
  fi
  gh_fetch "$CHECKSUM_URL" "sha256.txt" 2>/dev/null || { log "   ⚠️ 校验文件下载失败，跳过哈希校验。"; return 0; }
  want=$(grep -E "(^| )$expect_name\$" sha256.txt | awk '{print $1}' | head -1)
  if [ -z "$want" ]; then
    log "   ⚠️ sha256.txt 中未找到 $expect_name 的记录，跳过校验。"
    return 0
  fi
  got=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
  if [ "$got" = "$want" ]; then
    log "   ✅ $expect_name 哈希校验通过。"
    return 0
  else
    fail_exit "❌ $expect_name 哈希校验失败（期望 $want，实际 $got），疑似下载损坏或被篡改，已终止更新以防恶意包覆盖"
  fi
}
verify_checksum "backend.zip" "myblog-backend.zip"
verify_checksum "frontend.zip" "vue-frontend-dist.zip"
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
# 清理上一轮可能残留的 backend_extract（若之前以 mw 身份解压，当前身份可能删不掉 → 用 runuser 兜底）
if [ -d backend_extract ]; then
  rm -rf backend_extract 2>/dev/null || runuser -u "$APP_USER" -- rm -rf "$WORK/backend_extract" 2>/dev/null \
    || rm -rf "$WORK/backend_extract" 2>/dev/null \
    || fail_exit "无法清理临时目录 backend_extract（权限不足）。请手动执行: runuser -u $APP_USER -- rm -rf $WORK/backend_extract"
fi
mkdir backend_extract
unzip -q backend.zip -d backend_extract || fail_exit "后端包解压失败（文件可能损坏）"
# 统一以 APP_USER(mw) 身份覆盖，避免产生跨身份文件导致后续 rm/cp 权限失败
if command -v rsync >/dev/null 2>&1; then
  runuser -u "$APP_USER" -- rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/" \
    || rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/"
else
  # 无 rsync 时用 cp 逐个拷贝（排除 data），同样以 APP_USER 身份写
  find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec \
    runuser -u "$APP_USER" -- cp -r {} "$APP_DIR/" \; \
    || find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec cp -r {} "$APP_DIR/" \;
fi
log "   完成（data/ 数据库保留）。"

# 5. 覆盖前端
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  set_status "deploying" "正在覆盖前端文件"
  if [ -d frontend_extract ]; then
    rm -rf frontend_extract 2>/dev/null || runuser -u "$APP_USER" -- rm -rf "$WORK/frontend_extract" 2>/dev/null \
      || rm -rf "$WORK/frontend_extract" 2>/dev/null \
      || fail_exit "无法清理临时目录 frontend_extract（权限不足）。请手动: runuser -u $APP_USER -- rm -rf $WORK/frontend_extract"
  fi
  mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract || fail_exit "前端包解压失败"
  runuser -u "$APP_USER" -- cp -r "$WORK/frontend_extract/." "$FRONT_DIR/" \
    || cp -r "$WORK/frontend_extract/." "$FRONT_DIR/"
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
