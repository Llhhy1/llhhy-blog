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
# 清理历史残留解压目录（尽力而为；v3.4.4 起解压目录带 $TS 唯一后缀，不再复用固定名）
rm -rf "$WORK"/backend_extract "$WORK"/frontend_extract \
       "$WORK"/backend_extract_* "$WORK"/frontend_extract_* 2>/dev/null || true

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
  # 探测 gunicorn 启动方式：读 /proc/<pid>/cmdline 还原真实命令行（不能读 /proc/exe，那是解释器）
  # 支持两种形态：gunicorn -c conf app:app 与 python -m gunicorn -c conf app:app
  local cli="" real_bin=""
  if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ]; then
    cli=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
  fi
  if [ -z "$cli" ]; then
    cli=$(ps -o args= -p "$pid" 2>/dev/null || true)
  fi
  log "  ↳ 原进程命令行: ${cli:-（不可读）}"
  local toks=()
  if [ -n "$cli" ]; then
    set -f
    read -r -a toks <<< "$cli"
    set +f
    local i=0 cur="" prev=""
    for cur in "${toks[@]}"; do
      local base
      base=$(basename "$cur" 2>/dev/null || true)
      case "$base" in
        gunicorn)
          if [ "$prev" = "-m" ]; then
            local j=0 prevprev=""
            for prevprev in "${toks[@]}"; do
              case "$(basename "$prevprev" 2>/dev/null || true)" in
                python|python3|python3.*|pypy*)
                  real_bin="$prevprev -m gunicorn"
                  break
                  ;;
              esac
              j=$((j + 1))
            done
            [ -z "$real_bin" ] && real_bin="$cur"
          else
            real_bin="$cur"
          fi
          break
          ;;
        python|python3|python3.*|pypy*)
          if [ "$prev" = "-m" ] || [ "$prev" = "python3" ] || [ "$prev" = "python3.13" ]; then
            real_bin="$cur -m gunicorn"
            break
          fi
          ;;
      esac
      prev="$cur"
      i=$((i + 1))
    done
  fi
  GUNICORN_CONF=$(echo "$cli" | grep -oE '\-c [^ ]+\.py' | awk '{print $2}' | head -1 || true)
  [ -z "$real_bin" ] && real_bin="/ww/server/pyporject_evn/blog_env/bin/gunicorn"
  [ -z "$GUNICORN_CONF" ] && { [ -f "$APP_DIR/gunicorn_conf.py" ] && GUNICORN_CONF="$APP_DIR/gunicorn_conf.py" || true; }
  GUNICORN_BIN="$real_bin"
  log "  ↳ 重启将使用: ${GUNICORN_BIN:-未探测到} | conf: ${GUNICORN_CONF:-未探测到}"
  GUNICORN_MASTER_PID="${pid:-}"
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
  want=$(tr -d '\r' < sha256.txt | grep -E "(^| )$expect_name\$" | awk '{print $1}' | head -1)
  if [ -z "$want" ]; then
    log "   ⚠️ sha256.txt 中未找到 $expect_name 的记录，跳过校验。"
    return 0
  fi
  got=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
  if [ "$got" != "$want" ]; then
    log "❌ $expect_name 哈希校验失败（期望 $want，实际 $got），已终止更新以防恶意包覆盖"
    exit 1
  fi
  # ② zip 注释内嵌哈希校验（双源互证）：注释里写的是「内容区」哈希（剥离注释），
  #    这里必须同样剥离注释重算再比对（对含注释的整文件算必然对不上——自指循环）。
  #    注意：注释内嵌 hash == «内容区»哈希；而 sha256.txt 记录的是含注释的整文件哈希，
  #    两者故意不同。旧版误写成 内容区==注释==整文件 三向链式（恒 False），
  #    python3 退出码非 0 触发 set -e 静默炸脚本（日志无 ❌ 行仅"异常退出(码1)"）。
  #    正确做法：只用「注释内嵌 hash == 本地重算内容区 hash」双源互证。
  if command -v python3 >/dev/null 2>&1; then
    local comment_ok
    # ⚠️ 输出机制陷阱（v3.4.2 初版踩坑）：不能用 sys.exit(N) 靠退出码传结果——
    #       $(...) 命令替换捕获的是 **stdout** 而非退出码，sys.exit 不产生 stdout，
    #       comment_ok 恒为空串，正常包也会误判「不一致」。必须用 print 输出 + 按内容判断。
    comment_ok=$(python3 -c "
import sys, hashlib
try:
    data = open(sys.argv[1], 'rb').read()
    idx = data.rfind(b'\x50\x4b\x05\x06')
    if idx < 0: print('NO'); sys.exit(0)
    clen = int.from_bytes(data[idx+20:idx+22], 'little')
    if clen <= 0: print('NO'); sys.exit(0)
    cm = data[idx+22:idx+22+clen].decode('utf-8', 'replace')
    for ln in cm.splitlines():
        if ln.strip().startswith('SHA256='):
            h = hashlib.sha256()
            h.update(data[:idx+20])
            print('OK' if h.hexdigest() == ln.strip()[7:].strip().lower() else 'BAD')
            sys.exit(0)
    print('NO'); sys.exit(0)
except Exception:
    print('ERR'); sys.exit(0)
" "$f" 2>/dev/null) || true
    case "$comment_ok" in
      OK)
        log "   ✅ $expect_name 的 zip 注释内嵌哈希一致（双源互证通过）。"
        ;;
      BAD)
        log "❌ $expect_name 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。"
        exit 1
        ;;
      NO|ERR)
        log "   ⚠️ $expect_name 无法完成 zip 注释双源校验（无注释或读取异常），仅靠哈希列表比对。"
        ;;
      *)
        log "   ⚠️ $expect_name 的 zip 注释校验无输出，已降级为仅靠哈希列表比对。"
        ;;
    esac
  fi
  log "   ✅ $expect_name 校验完成。"
}

# ===== 进程存活探测（本项目的 gunicorn master）=====
have_gunicorn_proc() {
  pgrep -f "gunicorn.*${APP_DIR}" >/dev/null 2>&1 && return 0
  if [ -n "${GUNICORN_MASTER_PID:-}" ]; then
    kill -0 "$GUNICORN_MASTER_PID" 2>/dev/null && return 0
  fi
  return 1
}

# ===== 停止后端（真停止：杀主进程+所有 worker，确认进程与端口都释放）=====
stop_backend() {
  local pid="" pidfile="$APP_DIR/gunicorn.pid"
  if [ -f "$pidfile" ] && [ -s "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null | tr -d '[:space:]' | head -1)
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
  fi
  if [ -z "$pid" ] && [ -n "${GUNICORN_MASTER_PID:-}" ]; then
    pid="${GUNICORN_MASTER_PID}"
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1 || true)
  fi
  # 1. 先 TERM 主进程，再 TERM 整个项目的所有 gunicorn（含 worker），避免 worker 残留占端口
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "   停止后端：master pid=$pid 发送 TERM..."
    run_as kill -TERM "$pid" 2>/dev/null || true
  fi
  pkill -TERM -f "gunicorn.*$APP_DIR" 2>/dev/null || true
  # 2. 等待本项目 gunicorn 全部退出（最多 25 秒）
  local waited=0
  while pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1 && [ $waited -lt 25 ]; do sleep 1; waited=$((waited+1)); done
  if pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
    log "   ⚠️ 25 秒内仍未退出，发送 KILL 强杀..."
    pkill -KILL -f "gunicorn.*$APP_DIR" 2>/dev/null || true
    sleep 2
  fi
  # 3. 端口释放检查（仅当 conf 的 bind 是 TCP host:port 时可解析；解析失败则跳过，不阻断）
  local bind_spec=""
  bind_spec=$(grep -oE "bind[[:space:]]*=[[:space:]]*['\"][^'\"]+['\"]" "$GUNICORN_CONF" 2>/dev/null \
              | grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]+|127\.0\.0\.1:[0-9]+|0\.0\.0\.0:[0-9]+" | head -1 || true)
  if [ -n "$bind_spec" ]; then
    local ph="${bind_spec%%:*}" pp="${bind_spec##*:}" pw=0
    while [ $pw -lt 10 ]; do
      if timeout 1 bash -c "echo > /dev/tcp/$ph/$pp" 2>/dev/null; then sleep 1; pw=$((pw+1)); else break; fi
    done
    [ $pw -ge 10 ] && log "   ⚠️ 端口 $bind_spec 停止后仍被监听（可能被其他进程占用），新 gunicorn 可能起不来。"
  fi
  if have_gunicorn_proc; then
    log "   ⚠️ 仍有 gunicorn 进程残留（可能属于其他项目），视为已停止。"
  else
    log "   ✅ 后端进程已确认停止，端口已释放。"
  fi
}

# ===== 启动后端（setsid+nohup+exec 彻底脱离脚本会话；启动后查日志致命错误）=====
start_backend() {
  if [ -z "$GUNICORN_BIN" ] || [ -z "$GUNICORN_CONF" ] || [ ! -f "$GUNICORN_CONF" ]; then
    log "   ⚠️ 缺少可用的 gunicorn 启动信息（bin=${GUNICORN_BIN:-空} conf=${GUNICORN_CONF:-空}）。"
    return 1
  fi
  # 若 bin 是「解释器 -m gunicorn」形态，拆开执行；否则按独立 gunicorn 执行
  local bin_args=()
  if [[ "$GUNICORN_BIN" == *" -m gunicorn" ]]; then
    bin_args=("${GUNICORN_BIN% -m gunicorn}" "-m" "gunicorn")
  else
    bin_args=("$GUNICORN_BIN")
  fi
  # venv bin 目录（补全 PATH，确保子进程能找到依赖）
  local venv_bin=""
  case "$GUNICORN_BIN" in
    *" -m gunicorn") venv_bin="$(dirname "${GUNICORN_BIN% -m gunicorn}")" ;;
    *) venv_bin="${GUNICORN_BIN%/*}" ;;
  esac
  local sd_prefix=""
  command -v setsid >/dev/null 2>&1 && sd_prefix="setsid"
  log "   启动后端：${bin_args[*]} -c $GUNICORN_CONF app:app（setsid 脱离会话）"
  ( cd "$APP_DIR" && run_as $sd_prefix env "HOME=${APP_DIR%/*}" "PATH=$venv_bin:$PATH" \
        "${bin_args[@]}" -c "$GUNICORN_CONF" app:app >"$APP_DIR/gunicorn.log" 2>&1 < /dev/null & ) || true
  # 轮询最多 20 秒等待真正起来
  sleep 2
  local waited=0
  while ! pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1 && [ $waited -lt 18 ]; do sleep 1; waited=$((waited+1)); done
  if ! pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
    log "   ⚠️ 启动后未检测到 gunicorn 进程，gunicorn.log 末尾："
    tail -n 15 "$APP_DIR/gunicorn.log" 2>/dev/null | while read -r l; do log "     $l"; done
    return 1
  fi
  # 进程起来了，但日志里可能有致命错误（端口被占 / 权限 / 导入失败）→ 仍视为失败
  if grep -qiE 'Address already in use|Traceback \(most recent call last\)|PermissionError|OSError' "$APP_DIR/gunicorn.log" 2>/dev/null; then
    log "   ⚠️ gunicorn 进程已起，但 gunicorn.log 含致命错误："
    tail -n 20 "$APP_DIR/gunicorn.log" 2>/dev/null | while read -r l; do log "     $l"; done
    return 1
  fi
  log "   ✅ 后端进程已确认启动（gunicorn 运行中，日志无致命错误）。"
  return 0
}

# ===== 自动重启：先停止（确认退出）→ 再启动（确认存活）；严禁 HUP =====
auto_restart() {
  log "⑥ 重启后端服务（先停止 → 确认退出 → 再启动 → 确认存活）..."
  if [ -n "$RESTART_CMD" ]; then
    if eval "$RESTART_CMD"; then log "   重启命令执行成功。"; return 0; fi
    log "   ⚠️ 重启命令执行失败，尝试自动探测..."
  fi
  stop_backend
  if start_backend; then
    log "   ✅ 停止→启动 完成。"
    return 0
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
  # 优先用探测到的真实解释器
  if [ -n "$GUNICORN_BIN" ]; then
    case "$GUNICORN_BIN" in
      *python*|*/bin/python*|python*)
        py="${GUNICORN_BIN% -m gunicorn}"
        [ -x "$py" ] || py=""
        ;;
      *)
        py="${GUNICORN_BIN%/bin/gunicorn}/bin/python"
        [ -x "$py" ] || py="${GUNICORN_BIN%/gunicorn}/python"
        [ -x "$py" ] || py=""
        ;;
    esac
  fi
  if [ -z "$py" ]; then
    py=$(command -v python3 2>/dev/null || true)
  fi
  if [ -z "$py" ] || [ ! -x "$py" ]; then
    log "   ⚠️ 未找到可用的 python，请手动安装依赖: pip install -r $APP_DIR/requirements.txt"
    return 0
  fi
  log "   自动安装依赖: $py -m pip install -r requirements.txt ..."
  if run_as "$py" -m pip install --timeout 60 -r "$APP_DIR/requirements.txt" >/dev/null 2>&1; then
    log "   ✅ Python 依赖已安装/已满足。"
    return 0
  fi
  log "   ⚠️ 直连 PyPI 失败，改用阿里云镜像重试..."
  if run_as "$py" -m pip install --timeout 60 -i https://mirrors.aliyun.com/pypi/simple/ -r "$APP_DIR/requirements.txt" >/dev/null 2>&1; then
    log "   ✅ Python 依赖已通过阿里云镜像安装。"
    return 0
  fi
  log "   ⚠️ 依赖安装失败，请手动执行: $py -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r $APP_DIR/requirements.txt"
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
  # v3.9.1：WAL 模式下直接 cp 主库会得到「缺 WAL 中已提交数据」的陈旧快照，
  # 优先用 sqlite3 在线备份产出一致性副本；无 sqlite3 命令时退化为 cp（连同 -wal 一起拷）。
  if command -v sqlite3 >/dev/null 2>&1 \
     && sqlite3 "$APP_DIR/data/blog.db" ".backup '$APP_DIR/data/backup/blog_$TS.db'" 2>/dev/null; then
    log "   数据库（一致性快照）→ data/backup/blog_$TS.db"
  else
    cp "$APP_DIR/data/blog.db" "$APP_DIR/data/backup/blog_$TS.db"
    [ -f "$APP_DIR/data/blog.db-wal" ] && cp "$APP_DIR/data/blog.db-wal" "$APP_DIR/data/backup/blog_$TS.db-wal"
    log "   数据库（直拷，含 WAL）→ data/backup/blog_$TS.db"
  fi
fi
if [ -d "$APP_DIR/static/uploads" ]; then
  mkdir -p "$APP_DIR/data/backup"
  cp -r "$APP_DIR/static/uploads" "$APP_DIR/data/backup/uploads_$TS"
  log "   上传图片 → data/backup/uploads_$TS"
fi

# 4. 解压覆盖后端（zip 内自带一层 myblog/，跳过 data/）
log "④ 覆盖后端代码..."
BX="$WORK/backend_extract_$TS"   # 唯一临时目录（v3.4.4）
rm -rf "$BX"; mkdir -p "$BX"
unzip -q backend.zip -d "$BX" || { log "❌ 后端包解压失败。"; exit 1; }
[ -f "$BX/myblog/config.py" ] || { log "❌ 解压产物异常：未找到 myblog/config.py"; exit 1; }
copied=0
if command -v rsync >/dev/null 2>&1; then
  if rsync -a --exclude='data' --exclude='__pycache__' "$BX/myblog/" "$APP_DIR/" 2>/dev/null; then
    copied=1
  else
    log "   ⚠️ rsync 覆盖失败，回退 cp"
  fi
fi
if [ "$copied" != "1" ]; then
  for item in "$BX/myblog"/*; do
    [ -e "$item" ] || continue
    b=$(basename "$item")
    [ "$b" = "data" ] && continue
    [ "$b" = "__pycache__" ] && continue
    run_as cp -rf "$item" "$APP_DIR/" || cp -rf "$item" "$APP_DIR/" || { log "❌ 覆盖失败：$item"; exit 1; }
  done
fi
TAG_VER=${TAG#v}   # tag 形如 v3.4.4，config 里是 3.4.4，去掉前缀再比
new_ver=$(grep -oE 'APP_VERSION[[:space:]]*=[[:space:]]*"[0-9.]+"' "$APP_DIR/config.py" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$new_ver" != "$TAG_VER" ]; then
  log "❌ 覆盖后版本号校验失败：期望 $TAG_VER（tag $TAG），实际 ${new_ver:-未知}（覆盖未生效，请检查 $APP_DIR 写入权限）"
  exit 1
fi
log "后端代码已覆盖（跳过 data/，数据库保留，版本已更新为 $new_ver）"

# 4b. 自动安装依赖
log "④b 检查 Python 依赖..."
install_deps

# 5. 解压覆盖前端（zip 根直接是 index.html + assets/）
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  FX="$WORK/frontend_extract_$TS"   # 唯一临时目录（v3.4.4）
  rm -rf "$FX"; mkdir -p "$FX"
  unzip -q frontend.zip -d "$FX" || { log "❌ 前端包解压失败。"; exit 1; }
  run_as cp -rf "$FX/." "$FRONT_DIR/" 2>/dev/null \
    || cp -rf "$FX/." "$FRONT_DIR/" || { log "❌ 前端覆盖失败（请检查 $FRONT_DIR 写入权限）"; exit 1; }
  log "前端静态文件已覆盖"
else
  log "⚠️ 前端目录 $FRONT_DIR 不存在，跳过前端覆盖（请检查路径）"
fi

# 6. 重启后端
log "⑥ 重启后端..."
auto_restart

log "✅ 自动部署完成（$TAG）。请用无痕窗口访问后台，左下角版本号应为 $TAG"