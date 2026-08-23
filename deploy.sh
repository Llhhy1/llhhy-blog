#!/usr/bin/env bash
# =============================================================
# llhhy-blog 自动部署脚本（由 /api/webhook/deploy 触发，GitHub Webhook → 自动部署）
# 作用：从 GitHub Release 下载最新部署包 → 完整性校验 → 备份数据
#       → 覆盖代码 → 自动安装依赖 → 重启项目
#
# 修复要点（v3.4.0fix）：
#   1. 文件行尾统一 LF（旧版混入 CRLF 导致 bash 语法报错）。
#   2. 不再写死 APP_USER/GUNICORN_BIN/GUNICORN_CONF，改为从 gunicorn
#      实际进程自动探测（属主 / 二进制 / 启动 conf），避免
#      「runuser: user mw does not exist」跨环境翻车；探测失败优雅降级。
#   3. 覆盖代码后自动按 requirements.txt 安装新增 Python 依赖。
#
# 用法：
#   1. 上传本脚本到服务器：/www/wwwroot/myblog/deploy.sh
#   2. 宝塔终端执行：chmod +x /www/wwwroot/myblog/deploy.sh
#   3. 宝塔「Python项目 → 设置 → 环境变量」加：DEPLOY_SCRIPT=/www/wwwroot/myblog/deploy.sh
#   4. GitHub 仓库 Webhook 配置（见 deploy_guide.md「自动部署」章节）
# =============================================================
set -e

# ===== 按你的服务器改这几行（大多数环境可不改）=====
REPO="Llhhy1/llhhy-blog"            # GitHub 仓库（owner/repo）
APP_DIR="/www/wwwroot/myblog"       # 后端运行目录（Python 项目路径，必填）
FRONT_DIR="/www/wwwroot/vue-frontend"  # 前端静态目录（Nginx 网站根）
PROJECT_NAME="myblog"               # 宝塔 Python 项目名称；与实际不符请改
APP_USER=""                         # gunicorn 进程运行用户；留空=自动探测（也可手动指定如 www / root）
RESTART_CMD=""                      # 手动指定重启命令时填（优先使用，覆盖自动探测）

# ===== 可选：校验密钥 / GitHub 镜像（国内服务器）=====
UPDATE_HMAC_KEY="${UPDATE_HMAC_KEY:-}"
GH_MIRROR="${GH_MIRROR:-}"

# ===== 以下一般不用改 =====
WORK="/tmp/llhhy_deploy"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"
cd "$WORK"

log(){ echo "[$(date '+%F %T')] $*"; }

# ===== 以进程属主身份执行（root 时切换；用户不存在/非 root 则当前身份）=====
APP_USER_FINAL="${APP_USER:-}"
run_as() {  # run_as <cmd...>
  if [ "$(id -u)" = "0" ] && [ -n "$APP_USER_FINAL" ] && [ "$APP_USER_FINAL" != "root" ]; then
    if id "$APP_USER_FINAL" >/dev/null 2>&1; then
      if command -v runuser >/dev/null 2>&1; then
        runuser -u "$APP_USER_FINAL" -- "$@"
      elif command -v su >/dev/null 2>&1; then
        su "$APP_USER_FINAL" -c "$*"
      else
        "$@"
      fi
    else
      log "  ⚠️ 用户 $APP_USER_FINAL 不存在，以当前身份执行（可能导致文件属主不一致，但不会卡死）"
      "$@"
    fi
  else
    "$@"
  fi
}

# ===== 自动探测运行环境 =====
GUNICORN_BIN=""
GUNICORN_CONF=""
detect_runtime() {
  local pid=""
  if [ -f "$APP_DIR/gunicorn.pid" ] && [ -s "$APP_DIR/gunicorn.pid" ]; then
    pid=$(cat "$APP_DIR/gunicorn.pid" 2>/dev/null | tr -d '[:space:]' | head -1)
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1 || true)
  fi
  if [ -z "$APP_USER_FINAL" ]; then
    if [ -n "$pid" ]; then
      APP_USER_FINAL=$(ps -o user= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)
    fi
    if [ -z "$APP_USER_FINAL" ]; then
      APP_USER_FINAL=$(stat -c %U "$APP_DIR" 2>/dev/null | tr -d '[:space:]' || true)
    fi
    if [ -n "$APP_USER_FINAL" ] && [ "$APP_USER_FINAL" != "UNKNOWN" ]; then
      log "  ↳ 自动探测到运行属主: $APP_USER_FINAL"
    else
      APP_USER_FINAL=""
    fi
  fi
  if [ -n "$pid" ] && [ -r "/proc/$pid/exe" ]; then
    GUNICORN_BIN=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
  fi
  if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ]; then
    local cli
    cli=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    if [ -z "$GUNICORN_BIN" ]; then
      GUNICORN_BIN=$(echo "$cli" | awk '{print $1}' | head -1 || true)
    fi
    GUNICORN_CONF=$(echo "$cli" | grep -oE '\-c [^ ]+\.py' | awk '{print $2}' | head -1 || true)
  fi
  [ -z "$GUNICORN_BIN" ] && GUNICORN_BIN="/ww/server/pyporject_evn/blog_env/bin/gunicorn"
  [ -z "$GUNICORN_CONF" ] && { [ -f "$APP_DIR/gunicorn_conf.py" ] && GUNICORN_CONF="$APP_DIR/gunicorn_conf.py" || true; }
  log "  ↳ gunicorn: ${GUNICORN_BIN:-未探测到} | conf: ${GUNICORN_CONF:-未探测到}"
}

# ===== 网络请求：GitHub 失败自动重试 + 镜像兜底 =====
gh_fetch() {  # gh_fetch <url> <outfile|->
  local url="$1" out="$2" attempt=0 tu try_urls
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

# ===== 完整性校验（v3.1.6 双源互证 + HMAC 可选）=====
verify_checksum() {  # verify_checksum <file> <expected_name>
  local f="$1" expect_name="$2" want got
  if [ -z "$CHECKSUM_URL" ]; then
    log "   ⚠️ Release 未附带 sha256.txt，跳过哈希校验（建议发布时附带）。"
    return 0
  fi
  gh_fetch "$CHECKSUM_URL" "sha256.txt" 2>/dev/null || { log "   ⚠️ 校验文件下载失败，跳过哈希校验。"; return 0; }
  local first_line
  first_line=$(head -1 sha256.txt 2>/dev/null | tr -d '\r')
  case "$first_line" in
    "HMAC "*)
      if [ -n "$UPDATE_HMAC_KEY" ]; then
        local body sig want_sig
        body=$(tail -n +2 sha256.txt 2>/dev/null)
        want_sig=$(printf '%s' "$first_line" | awk '{print $2}')
        if command -v python3 >/dev/null 2>&1; then
          sig=$(python3 -c "import hmac,hashlib,sys;print(hmac.new(sys.argv[1].encode(),sys.argv[2].encode(),hashlib.sha256).hexdigest())" "$UPDATE_HMAC_KEY" "$body" 2>/dev/null)
          if [ -z "$sig" ] || [ "$sig" != "$want_sig" ]; then
            log "❌ sha256.txt 的 HMAC 签名校验失败：文件可能被篡改。已终止更新。"
            exit 1
          fi
          log "   ✅ HMAC 签名校验通过。"
        fi
      fi
      ;;
  esac
  want=$(grep -E "(^| )$expect_name\$" sha256.txt | awk '{print $1}' | head -1)
  if [ -z "$want" ]; then
    log "   ⚠️ sha256.txt 中未找到 $expect_name 的记录，跳过校验。"
    return 0
  fi
  got=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
  if [ "$got" != "$want" ]; then
    log "❌ $expect_name 哈希校验失败（期望 $want，实际 $got），已终止更新以防恶意包覆盖"
    exit 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    local comment_ok
    comment_ok=$(python3 -c "
import sys, hashlib
try:
    data = open(sys.argv[1], 'rb').read()
    idx = data.rfind(b'\x50\x4b\x05\x06')
    if idx < 0: sys.exit(1)
    clen = int.from_bytes(data[idx+20:idx+22], 'little')
    if clen <= 0: sys.exit(1)
    cm = data[idx+22:idx+22+clen].decode('utf-8', 'replace')
    for ln in cm.splitlines():
        if ln.strip().startswith('SHA256='):
            h = hashlib.sha256()
            h.update(data[:idx+20])
            sys.exit(0 if h.hexdigest() == ln.strip()[7:].strip().lower() == sys.argv[2].lower() else 1)
    sys.exit(1)
except Exception:
    sys.exit(1)
" "$f" "$want" 2>/dev/null)
    if [ "$comment_ok" = "0" ]; then
      log "   ✅ $expect_name 的 zip 注释内嵌哈希一致（双源互证通过）。"
    else
      log "❌ $expect_name 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。"
      exit 1
    fi
  fi
  log "   ✅ $expect_name 校验完成。"
}

# ===== 自动重启：优先 bt CLI，其次真杀+真启动（严禁 HUP）=====
auto_restart() {
  log "⑥ 重启后端服务..."
  if [ -n "$RESTART_CMD" ]; then
    if eval "$RESTART_CMD"; then log "   重启命令执行成功。"; return 0; fi
    log "   ⚠️ 重启命令执行失败，尝试自动探测..."
  fi
  if command -v bt >/dev/null 2>&1 && [ -n "$PROJECT_NAME" ]; then
    log "   尝试通过宝塔 CLI 重启项目「$PROJECT_NAME」..."
    if bt stop "$PROJECT_NAME" >/dev/null 2>&1; then
      sleep 2
      if bt start "$PROJECT_NAME" >/dev/null 2>&1; then
        log "   已通过宝塔 CLI 重启「$PROJECT_NAME」。"
        return 0
      fi
    fi
  fi
  local pid="" pidfile="$APP_DIR/gunicorn.pid"
  if [ -f "$pidfile" ] && [ -s "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null | tr -d '[:space:]' | head -1)
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    if [ -n "$pid" ] && ! run_as kill -0 "$pid" 2>/dev/null; then pid=""; fi
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1 || true)
  fi
  if [ -n "$pid" ]; then
    log "   找到 gunicorn master pid=$pid，以 ${APP_USER_FINAL:-当前身份} 发送 TERM 真正停止..."
    if ! run_as kill -TERM "$pid" 2>/dev/null; then
      log "   ⚠️ 无法终止进程 pid=$pid（权限不足）。代码已更新但未重启，请手动在宝塔「停止→启动」。"
      return 1
    fi
    local waited=0
    while run_as kill -0 "$pid" 2>/dev/null && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    run_as kill -0 "$pid" 2>/dev/null && { run_as pkill -9 -f "gunicorn.*$APP_DIR" 2>/dev/null || true; }
    sleep 1
    log "   旧进程已停止。"
  else
    log "   未发现运行中的 gunicorn 进程，直接进入启动。"
  fi
  if [ -x "$GUNICORN_BIN" ] && [ -n "$GUNICORN_CONF" ] && [ -f "$GUNICORN_CONF" ]; then
    log "   用 gunicorn 重新拉起：run_as $GUNICORN_BIN -c $GUNICORN_CONF app:app"
    ( cd "$APP_DIR" && run_as env "HOME=${APP_DIR%/*}" "$GUNICORN_BIN" -c "$GUNICORN_CONF" app:app >"$APP_DIR/gunicorn.log" 2>&1 & ) || true
    sleep 3
    if pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
      log "   已重新启动（停止→启动 完成）。"
      return 0
    fi
    log "   ⚠️ 启动后未检测到 gunicorn 进程，请检查 $APP_DIR/gunicorn.log。"
  else
    log "   ⚠️ 未找到可用的 gunicorn（${GUNICORN_BIN:-空}）或 conf（${GUNICORN_CONF:-空}）。"
  fi
  log "   ⚠️ 无法自动重启。请手动在宝塔「网站 → Python项目」点「停止」再「启动」。"
}

# ===== 安装 Python 依赖 =====
install_deps() {
  if [ ! -f "$APP_DIR/requirements.txt" ]; then
    log "   （无 requirements.txt，跳过）"
    return 0
  fi
  local py=""
  if [ -n "$GUNICORN_BIN" ]; then
    py="${GUNICORN_BIN%/bin/gunicorn}/bin/python"
    [ -x "$py" ] || py="${GUNICORN_BIN%/gunicorn}/python"
    [ -x "$py" ] || py=""
  fi
  if [ -z "$py" ]; then
    py=$(command -v python3 2>/dev/null || true)
  fi
  if [ -n "$py" ] && [ -x "$py" ]; then
    log "   自动安装依赖: $py -m pip install -r requirements.txt ..."
    if run_as "$py" -m pip install -r "$APP_DIR/requirements.txt" >/dev/null 2>&1; then
      log "   ✅ Python 依赖已安装/已满足。"
    else
      log "   ⚠️ 依赖自动安装失败，请手动执行: $py -m pip install -r $APP_DIR/requirements.txt"
    fi
  else
    log "   ⚠️ 未找到可用的 python，请手动安装依赖: pip install -r $APP_DIR/requirements.txt"
  fi
}

# ==================== 主流程 ====================
log "==============================================="
log " 自动部署 llhhy-blog（GitHub Webhook 触发）"
log "==============================================="
detect_runtime

# 1. 查询最新 Release 的下载地址（GitHub API，公开仓库无需 token）
log "① 获取最新 Release 信息..."
LATEST_JSON=$(gh_fetch "https://api.github.com/repos/$REPO/releases/latest" "-") || { log "❌ 获取 GitHub 最新版本失败。可设 GH_MIRROR。"; exit 1; }
BACKEND_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*myblog-backend.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
FRONT_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*vue-frontend-dist.zip"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
CHECKSUM_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*sha256.txt"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
TAG=$(echo "$LATEST_JSON" | grep -o '"tag_name": *"[^"]*"' | sed 's/.*"\([^"]*\)".*/\1/' | head -1)
if [ -z "$BACKEND_URL" ] || [ -z "$FRONT_URL" ]; then
  log "❌ 未找到最新 Release 的部署包（tag=$TAG），中止。"
  exit 1
fi
log "最新版本: $TAG"

# 2. 下载两个 zip + 校验
log "② 下载部署包..."
gh_fetch "$BACKEND_URL" "backend.zip" || { log "❌ 后端包下载失败。"; exit 1; }
gh_fetch "$FRONT_URL" "frontend.zip" || { log "❌ 前端包下载失败。"; exit 1; }
verify_checksum "backend.zip" "myblog-backend.zip"
verify_checksum "frontend.zip" "vue-frontend-dist.zip"
log "下载与校验完成。"

# 3. 备份数据（数据库 + 上传图片）—— 数据永远不覆盖，只备份留底
log "③ 备份数据..."
if [ -f "$APP_DIR/data/blog.db" ]; then
  mkdir -p "$APP_DIR/data/backup"
  cp "$APP_DIR/data/blog.db" "$APP_DIR/data/backup/blog_$TS.db"
  log "   数据库 → data/backup/blog_$TS.db"
fi
if [ -d "$APP_DIR/static/uploads" ]; then
  mkdir -p "$APP_DIR/data/backup"
  cp -r "$APP_DIR/static/uploads" "$APP_DIR/data/backup/uploads_$TS"
  log "   上传图片 → data/backup/uploads_$TS"
fi

# 4. 解压覆盖后端（zip 内自带一层 myblog/，跳过 data/）
log "④ 覆盖后端代码..."
rm -rf backend_extract && mkdir backend_extract
unzip -q backend.zip -d backend_extract || { log "❌ 后端包解压失败。"; exit 1; }
if command -v rsync >/dev/null 2>&1; then
  run_as rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/" 2>/dev/null \
    || rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/"
else
  find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec \
    run_as cp -r {} "$APP_DIR/" \; 2>/dev/null \
    || find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec cp -r {} "$APP_DIR/" \;
fi
log "后端代码已覆盖（跳过 data/，数据库保留）"

# 4b. 自动安装依赖
log "④b 检查 Python 依赖..."
install_deps

# 5. 解压覆盖前端（zip 根直接是 index.html + assets/）
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  rm -rf frontend_extract && mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract || { log "❌ 前端包解压失败。"; exit 1; }
  run_as cp -r "$WORK/frontend_extract/." "$FRONT_DIR/" 2>/dev/null \
    || cp -r "$WORK/frontend_extract/." "$FRONT_DIR/"
  log "前端静态文件已覆盖"
else
  log "⚠️ 前端目录 $FRONT_DIR 不存在，跳过前端覆盖（请检查路径）"
fi

# 6. 重启后端
log "⑥ 重启后端..."
auto_restart

log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"