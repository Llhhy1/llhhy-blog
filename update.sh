#!/usr/bin/env bash
# =============================================================
# llhhy-blog 一键更新脚本（懒人版 · 全自动，连重启都不用点）
# 作用：自动完成「下载最新 Release → 完整性校验 → 备份数据 → 覆盖代码
#       → 自动安装依赖 → 自动重启后端」
#
# 修复要点（v3.4.0fix）：
#   1. 文件行尾统一 LF（旧版混入 CRLF 导致 bash 直接语法报错：
#      "set: -: invalid option" / "$'\r': command not found"）
#   2. 不再写死 APP_USER/GUNICORN_BIN/GUNICORN_CONF 等环境专属值，
#      改为从 gunicorn 实际进程自动探测（属主 / 二进制 / 启动 conf），
#      彻底避免「runuser: user mw does not exist」这类跨环境翻车。
#      探测失败时优雅降级为当前身份，只在必要时提示手动配置。
#   3. 覆盖代码后自动按 requirements.txt 安装新增 Python 依赖
#      （v3.4.0 起新增 cryptography 等；安装失败不阻断，仅提示手动）。
#
# 用法：
#   手动（宝塔终端）：bash /www/wwwroot/myblog/update.sh
#   后台触发：由「后台 → 系统设置 → 立即更新」自动调用，
#     脚本写状态文件 data/update_status.json（后台轮询显示进度）。
#
# 自动重启原理：
#   优先宝塔 CLI（bt stop/start 项目名，最贴近面板「停止→启动」）；
#   其次以进程属主身份真杀 master（TERM）→ 用实际 gunicorn 重新拉起。
#   严禁 HUP 热重载（master 不退出，改了 import/表结构后老 worker 仍服务旧代码）。
# =============================================================
set -e

# ===== 首次使用：按你的服务器改这几行（大多数环境可不改）=====
REPO="Llhhy1/llhhy-blog"                 # GitHub 仓库，一般不用改
APP_DIR="/www/wwwroot/myblog"            # 后端运行目录（Python 项目路径）
FRONT_DIR="/www/wwwroot/vue-frontend"    # 前端静态目录（Nginx 网站根）
PROJECT_NAME="myblog"                    # 宝塔 Python 项目名称；与实际不符请改
APP_USER=""                              # gunicorn 进程运行用户；留空=自动探测（也可手动指定如 www / root）
RESTART_CMD=""                           # 手动指定重启命令时填（优先使用，覆盖自动探测）：
                                         #   例：RESTART_CMD="bt stop myblog && bt start myblog"

# ===== 更新包完整性更强校验（v3.1.6）=====
# UPDATE_HMAC_KEY：可选。若配置（部署侧机密，与 Release 无关），update.sh 会校验 sha256.txt 首行
#   HMAC 签名是否与正文匹配（防 sha256.txt 本身被篡改后连带伪造哈希）。
#   留空则仅校验 zip 注释内嵌哈希 + sha256.txt 列表（无签名校验，向后兼容）。
UPDATE_HMAC_KEY="${UPDATE_HMAC_KEY:-}"

# ===== 网络镜像（国内服务器可选）=====
# 若服务器无法直连 GitHub，可设 GH_MIRROR，如：
#   GH_MIRROR="https://ghfast.top/"  （脚本也会自动尝试 ghfast/gh-proxy/ghproxy 兜底）
GH_MIRROR="${GH_MIRROR:-}"

WORK="/tmp/llhhy_update"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"
cd "$WORK"

log(){ echo "[$(date '+%F %T')] $*"; }

# ===== 状态文件（后台在线更新轮询用）=====
STATUS_FILE="$APP_DIR/data/update_status.json"
set_status() {  # set_status <status> <message>
  local st="$1" msg="$2"
  mkdir -p "$(dirname "$STATUS_FILE")"
  printf '{"status":"%s","version":"%s","ts":"%s","message":"%s"}\n' \
    "$st" "${TAG:-}" "$(date '+%F %T')" "$msg" > "$STATUS_FILE" 2>/dev/null || true
}
# fail_exit 记录具体失败原因；trap 只在无具体原因时才补通用信息
FAIL_MSG=""
fail_exit() {
  FAIL_MSG="$1"
  set_status "failed" "$1"
  log "❌ $1"
  exit 1
}
trap 'rc=$?; if [ $rc -ne 0 ]; then set_status "failed" "${FAIL_MSG:-脚本异常退出(码$rc)，详见后端日志 data/update_log.txt}"; fi' EXIT

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

# ===== 自动探测运行环境：进程属主 / gunicorn 二进制 / conf =====
GUNICORN_BIN=""
GUNICORN_CONF=""
detect_runtime() {
  local pid=""
  # 1. 找 gunicorn master pid：优先 pidfile，其次精确匹配本项目
  if [ -f "$APP_DIR/gunicorn.pid" ] && [ -s "$APP_DIR/gunicorn.pid" ]; then
    pid=$(cat "$APP_DIR/gunicorn.pid" 2>/dev/null | tr -d '[:space:]' | head -1)
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
  fi
  if [ -z "$pid" ]; then
    pid=$(pgrep -f "gunicorn.*$APP_DIR" 2>/dev/null | head -1 || true)
  fi
  # 2. 探测进程属主
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
  # 3. 探测 gunicorn 启动方式：读 /proc/<pid>/cmdline（零长度分隔）还原真实命令行
  #    注意：不能读 /proc/<pid>/exe（那是指向解释器 python，不是 gunicorn 本体）。
  #    支持两种形态：gunicorn -c conf app:app 与 python -m gunicorn -c conf app:app。
  local cli="" real_bin=""
  if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ]; then
    cli=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
  fi
  if [ -z "$cli" ]; then
    # 没有 /proc 权限 → 用 ps 行（含完整命令行）兜底
    cli=$(ps -o args= -p "$pid" 2>/dev/null || true)
  fi
  log "  ↳ 原进程命令行: ${cli:-（不可读）}"
  local toks=()
  if [ -n "$cli" ]; then
    # 用 bash 分词（关 glob）展开命令行，逐 token 找启动点
    set -f
    read -r -a toks <<< "$cli"
    set +f
    local i=0 cur="" prev=""
    for cur in "${toks[@]}"; do
      local base
      base=$(basename "$cur" 2>/dev/null || true)
      case "$base" in
        gunicorn)
          # gunicorn 作为 argv[0]（独立可执行）；若前一个是 -m，则是「解释器 -m gunicorn」形态
          if [ "$prev" = "-m" ]; then
            # prev 是 -m，再往前找解释器（toks 循环里已记录到 prev 是 -m，解释器在更前面）
            # 直接回查 toks：找到第一个 python* 作为解释器
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
            # 独立 gunicorn 可执行文件
            real_bin="$cur"
          fi
          break
          ;;
        python|python3|python3.*|pypy*)
          # 解释器 + -m gunicorn 形态
          if [ "$prev" = "-m" ] || [ "$prev" = "python3.13" ] || [ "$prev" = "python3" ]; then
            real_bin="$cur -m gunicorn"
            break
          fi
          ;;
      esac
      prev="$cur"
      i=$((i + 1))
    done
  fi
  # 4. 探测启动 conf（命令行中 -c 后的 .py）
  if [ -n "$cli" ]; then
    GUNICORN_CONF=$(echo "$cli" | grep -oE '\-c [^ ]+\.py' | awk '{print $2}' | head -1 || true)
  fi
  # 5. 兜底默认值（宝塔常见路径，探测不到时用；找不到会走提示而非硬崩）
  [ -z "$real_bin" ] && real_bin="/ww/server/pyporject_evn/blog_env/bin/gunicorn"
  [ -z "$GUNICORN_CONF" ] && { [ -f "$APP_DIR/gunicorn_conf.py" ] && GUNICORN_CONF="$APP_DIR/gunicorn_conf.py" || true; }
  GUNICORN_BIN="$real_bin"
  log "  ↳ 重启将使用: ${GUNICORN_BIN:-未探测到} | conf: ${GUNICORN_CONF:-未探测到}"
  # 6. 记录 master pid 供重启阶段复用（解决探测到的 pid 与重启时找不到的错位）
  GUNICORN_MASTER_PID="${pid:-}"
}

# ===== 网络请求函数：GitHub 失败时自动重试 + 镜像代理兜底（国内服务器）=====
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

# ===== 进程存活探测（本项目的 gunicorn master）=====
have_gunicorn_proc() {
  # 1. 优先精确匹配 APP_DIR 的 gunicorn 进程（含 python -m gunicorn 形态）
  pgrep -f "gunicorn.*${APP_DIR}" >/dev/null 2>&1 && return 0
  # 2. 用已记录的 master pid 存活核验
  if [ -n "${GUNICORN_MASTER_PID:-}" ]; then
    kill -0 "$GUNICORN_MASTER_PID" 2>/dev/null && return 0
  fi
  return 1
}

# ===== 停止后端（真停止：确认进程已退出才返回 0）=====
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
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "   停止后端：pid=$pid 发送 TERM..."
    run_as kill -TERM "$pid" 2>/dev/null || log "   ⚠️ TERM 失败（可能已退出），继续等待确认..."
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 20 ]; do sleep 1; waited=$((waited+1)); done
    if kill -0 "$pid" 2>/dev/null; then
      log "   ⚠️ TERM 后仍未退出，发送 KILL...（pid=$pid）"
      run_as kill -KILL "$pid" 2>/dev/null || true
      sleep 1
    fi
  fi
  # 最终确认：本项目的 gunicorn 进程已全部消失
  if have_gunicorn_proc; then
    log "   ⚠️ 仍有 gunicorn 进程残留（可能属于其他项目），视为已停止。"
  else
    log "   ✅ 后端进程已确认停止。"
  fi
}

# ===== 启动后端（真启动：探测到进程起来才返回 0）=====
start_backend() {
  if [ -z "$GUNICORN_BIN" ] || [ -z "$GUNICORN_CONF" ] || [ ! -f "$GUNICORN_CONF" ]; then
    log "   ⚠️ 缺少可用的 gunicorn 启动信息（bin=${GUNICORN_BIN:-空} conf=${GUNICORN_CONF:-空}）。"
    return 1
  fi
  # 若 bin 是「解释器 -m gunicorn」形态，拆开执行；否则按独立 gunicorn 执行
  local bin_args=()
  if [[ "$GUNICORN_BIN" == *" -m gunicorn" ]]; then
    local py="${GUNICORN_BIN% -m gunicorn}"
    bin_args=("$py" "-m" "gunicorn")
  else
    bin_args=("$GUNICORN_BIN")
  fi
  log "   启动后端：${bin_args[*]} -c $GUNICORN_CONF app:app"
  ( cd "$APP_DIR" && run_as env "HOME=${APP_DIR%/*}" "${bin_args[@]}" -c "$GUNICORN_CONF" app:app >"$APP_DIR/gunicorn.log" 2>&1 & ) || true
  # 轮询最多 15 秒等待真正起来
  sleep 2
  local waited=0
  while ! pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1 && [ $waited -lt 13 ]; do sleep 1; waited=$((waited+1)); done
  if pgrep -f "gunicorn.*$APP_DIR" >/dev/null 2>&1; then
    log "   ✅ 后端进程已确认启动（gunicorn 运行中）。"
    return 0
  fi
  log "   ⚠️ 启动后未检测到 gunicorn 进程，请检查 $APP_DIR/gunicorn.log。"
  return 1
}

# ===== 自动重启后端：先停止（确认退出）→ 再启动（确认存活）；严禁 HUP =====
auto_restart() {
  log "⑥ 重启后端服务（先停止 → 确认退出 → 再启动 → 确认存活）..."
  # 0. 手动指定重启命令（优先级最高）
  if [ -n "$RESTART_CMD" ]; then
    if eval "$RESTART_CMD"; then log "   重启命令执行成功。"; return 0; fi
    log "   ⚠️ 重启命令执行失败，尝试自动探测..."
  fi
  # 1. 停止（确认进程已退出）
  stop_backend
  # 2. 启动（确认进程起来）
  if start_backend; then
    log "   ✅ 停止→启动 完成。"
    return 0
  fi
  # 3. 启动失败 → 提示手动
  log "   ⚠️ 无法自动重启。请手动在宝塔「网站 → Python项目」点「停止」再「启动」。"
  set_status "partial" "代码已更新，但自动重启未生效，请手动在宝塔重启项目（停止→启动）"
}

# ===== 安装 Python 依赖（requirements.txt 变化时）=====
install_deps() {
  if [ ! -f "$APP_DIR/requirements.txt" ]; then
    log "   （无 requirements.txt，跳过）"
    return 0
  fi
  local py=""
  # 1. 优先用探测到的真实解释器（GUNICORN_BIN 可能是 python 解释器路径，如 /usr/bin/python3.13）
  if [ -n "$GUNICORN_BIN" ]; then
    case "$GUNICORN_BIN" in
      *python*|*/bin/python*|python*)
        # GUNICORN_BIN 本身是解释器（如 /usr/bin/python3.13 或 /xx/bin/python）
        py="${GUNICORN_BIN% -m gunicorn}"
        [ -x "$py" ] || py=""
        ;;
      *)
        # 否则从 gunicorn bin 推导同目录 python（宝塔常为 /xx/bin/python）
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
  # 直连官方 PyPI（可能慢，给 90s 超时）
  if run_as "$py" -m pip install --timeout 60 -r "$APP_DIR/requirements.txt" >/dev/null 2>&1; then
    log "   ✅ Python 依赖已安装/已满足。"
    return 0
  fi
  # 直连失败 → 阿里云镜像重试（国内服务器通常镜像更快更稳）
  log "   ⚠️ 直连 PyPI 失败，改用阿里云镜像重试..."
  if run_as "$py" -m pip install --timeout 60 -i https://mirrors.aliyun.com/pypi/simple/ -r "$APP_DIR/requirements.txt" >/dev/null 2>&1; then
    log "   ✅ Python 依赖已通过阿里云镜像安装。"
    return 0
  fi
  log "   ⚠️ 依赖安装失败，请手动执行: $py -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r $APP_DIR/requirements.txt"
}

# ===== 校验（v3.1.6 双源互证 + HMAC 可选）=====
verify_checksum() {  # verify_checksum <file> <expected_name>
  local f="$1" expect_name="$2" want got
  if [ -z "$CHECKSUM_URL" ]; then
    log "   ⚠️ Release 未附带 sha256.txt，跳过哈希校验（建议发布时附带）。"
    return 0
  fi
  gh_fetch "$CHECKSUM_URL" "sha256.txt" 2>/dev/null || { log "   ⚠️ 校验文件下载失败，跳过哈希校验。"; return 0; }
  # ① HMAC 签名校验（仅当首行是 HMAC 且配置了密钥时强制）
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
            fail_exit "❌ sha256.txt 的 HMAC 签名校验失败：文件可能被篡改（发布者密钥与本地 UPDATE_HMAC_KEY 不一致或正文被改）。已终止更新。"
          fi
          log "   ✅ HMAC 签名校验通过（sha256.txt 未被篡改）。"
        else
          log "   ⚠️ 无 python3，跳过 HMAC 校验（仅靠哈希列表比对）。"
        fi
      else
        log "   ⚠️ sha256.txt 带 HMAC 签名但未配置 UPDATE_HMAC_KEY，跳过签名校验（如有疑虑请配置密钥）。"
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
    fail_exit "❌ $expect_name 哈希校验失败（期望 $want，实际 $got），疑似下载损坏或被篡改，已终止更新以防恶意包覆盖"
  fi
  # ② zip 注释内嵌哈希校验（双源互证）：注释里写的是「内容区」哈希（剥离尾注释），
  #    这里必须同样剥离注释重算再比对（对含注释的整文件算必然对不上——自指循环）。
  if command -v python3 >/dev/null 2>&1; then
    local comment_ok
    # 注意：注释内嵌 hash == sha256_of_content 的「内容区」哈希（剥离尾注释后整包字节），
    #       而 sha256.txt 记录的是含注释的「整文件」哈希——两者故意不同。
    #       旧版误写成 内容区==注释 再 ==整文件 的三向链式比较（恒 False），
    #       python3 退出码非 0 触发 set -e 静默炸脚本（日志无 ❌ 行，仅"异常退出(码1)"）。
    #       正确做法：只用「注释内嵌 hash == 本地重算内容区 hash」双源互证，
    #       不依赖 sha256.txt（注释被单独篡改、或包内容被单独篡改都会暴露）。
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
            sys.exit(0 if h.hexdigest() == ln.strip()[7:].strip().lower() else 1)
    sys.exit(1)
except Exception:
    sys.exit(1)
" "$f" 2>/dev/null) || true
    if [ "$comment_ok" = "0" ]; then
      log "   ✅ $expect_name 的 zip 注释内嵌哈希一致（双源互证通过）。"
    else
      fail_exit "❌ $expect_name 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。"
    fi
  else
    log "   ⚠️ 无 python3，跳过 zip 注释双源校验（仅靠哈希列表比对）。"
  fi
  log "   ✅ $expect_name 校验完成。"
}

# ==================== 主流程 ====================
log "==============================================="
log " 一键更新 llhhy-blog（懒人版 · 自动下载+校验+备份+覆盖+装依赖+重启）"
log "==============================================="
set_status "started" "开始更新"
detect_runtime

# 1. 查询最新 Release 的下载地址
log "① 查询 GitHub 最新版本..."
set_status "downloading" "正在查询最新版本"
LATEST_JSON=$(gh_fetch "https://api.github.com/repos/$REPO/releases/latest" "-") || \
  fail_exit "获取 GitHub 最新版本失败（网络不通或 GitHub 被墙）。可设 GH_MIRROR，或宝塔终端手动运行：bash /www/wwwroot/myblog/update.sh"
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
gh_fetch "$BACKEND_URL" "backend.zip" || fail_exit "后端包下载失败（网络问题）。可设 GH_MIRROR 或检查服务器能否访问 GitHub"
gh_fetch "$FRONT_URL" "frontend.zip" || fail_exit "前端包下载失败（网络问题）。可设 GH_MIRROR 或检查服务器能否访问 GitHub"
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
if [ -d backend_extract ]; then
  rm -rf backend_extract 2>/dev/null || run_as rm -rf "$WORK/backend_extract" 2>/dev/null || true
fi
mkdir backend_extract
unzip -q backend.zip -d backend_extract || fail_exit "后端包解压失败（文件可能损坏）"
if command -v rsync >/dev/null 2>&1; then
  run_as rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/" 2>/dev/null \
    || rsync -a --exclude='data' --exclude='__pycache__' "$WORK/backend_extract/myblog/" "$APP_DIR/"
else
  find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec \
    run_as cp -r {} "$APP_DIR/" \; 2>/dev/null \
    || find "$WORK/backend_extract/myblog" -mindepth 1 -maxdepth 1 ! -name 'data' ! -name '__pycache__' -exec cp -r {} "$APP_DIR/" \;
fi
log "   完成（data/ 数据库保留）。"

# 4b. 自动安装 Python 依赖（新增包如 cryptography）
log "④b 检查 Python 依赖..."
install_deps

# 5. 覆盖前端
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  set_status "deploying" "正在覆盖前端文件"
  if [ -d frontend_extract ]; then
    rm -rf frontend_extract 2>/dev/null || run_as rm -rf "$WORK/frontend_extract" 2>/dev/null || true
  fi
  mkdir frontend_extract
  unzip -q frontend.zip -d frontend_extract || fail_exit "前端包解压失败"
  run_as cp -r "$WORK/frontend_extract/." "$FRONT_DIR/" 2>/dev/null \
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