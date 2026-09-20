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
RESTART_CMD=""                           # 手动指定重启命令时填（优先于自动探测）；例：
                                         #   RESTART_CMD="systemctl restart myblog" 或你手动重启用的确切命令
                                         # 注意：宝塔 bt 命令行是交互式菜单，不支持「bt stop 项目名」，请勿照抄旧范例；
                                         #   留空则走脚本内置的「进程组强杀→端口释放→setsid 拉起」自动重启。

# ===== 更新包完整性更强校验（v3.1.6）=====
# UPDATE_HMAC_KEY：可选。若配置（部署侧机密，与 Release 无关），update.sh 会校验 sha256.txt 首行
#   HMAC 签名是否与正文匹配（防 sha256.txt 本身被篡改后连带伪造哈希）。
#   留空则仅校验 zip 注释内嵌哈希 + sha256.txt 列表（无签名校验，向后兼容）。
UPDATE_HMAC_KEY="${UPDATE_HMAC_KEY:-}"

# ===== 网络镜像（国内服务器可选 · v3.18.7 起改为「必须显式配置」）=====
# 若服务器无法直连 GitHub，自行设置一个你信任的代理前缀，例如：
#   GH_MIRROR="https://your-own-proxy/"
# ⚠️ 脚本**不再**自动兜底任何第三方公共镜像——校验清单（sha256.txt）与它描述的产物
#    走同一条通道，公共代理可同时改写两者，使完整性校验形同虚设。该代理的可信度由你承担。
GH_MIRROR="${GH_MIRROR:-}"

# ===== 发布物签名校验（v3.18.7 新增 · 默认强制）=====
# 发布侧用 Ed25519 对 Release 的 sha256.txt 做**分离签名**，产出资产 sha256.txt.sig。
# 验签公钥**内置在本脚本里** → 任何人 clone 这份仓库部署，开箱即用、无需额外配置。
# 自建发布者（自己改代码自己发版）：用 `python package.py --gen-key` 生成自己的密钥对，
#   然后把公钥填到环境变量 RELEASE_PUBKEY（或直接改下面的 BUILTIN_RELEASE_PUBKEY）。
BUILTIN_RELEASE_PUBKEY="jolSxBuRPpVlwGWQGbYU7iLus4NIBT0nh0LPx1abzho="
RELEASE_PUBKEY="${RELEASE_PUBKEY:-$BUILTIN_RELEASE_PUBKEY}"
# 逃生舱（仅调试 / 自建发布链过渡期）：必须**显式**设 ALLOW_UNSIGNED=1 才允许跳过验签，
#   且会打醒目警告。默认 0 = 缺签名直接终止更新。
ALLOW_UNSIGNED="${ALLOW_UNSIGNED:-0}"
# 显式允许降级安装（默认禁止把站点覆盖成更旧的版本）。
ALLOW_DOWNGRADE="${ALLOW_DOWNGRADE:-0}"


WORK="/tmp/llhhy_update"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$WORK"
cd "$WORK"
# 清理历史残留解压目录（尽力而为；v3.4.4 起解压目录带 $TS 唯一后缀，不再复用固定名）
rm -rf "$WORK"/backend_extract "$WORK"/frontend_extract \
       "$WORK"/backend_extract_* "$WORK"/frontend_extract_* 2>/dev/null || true

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
# v3.17.2 加固：TERM/INT（手动重启后端/关闭会话）也把状态复位为 failed，避免 deploying 悬挂
trap 'FAIL_MSG="更新被中断（收到 TERM/INT 信号，可能为手动重启后端或关闭会话），请重新触发更新"; exit 1' TERM INT

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
  # v3.18.7：**不再自动兜底第三方镜像**（ghfast / gh-proxy / ghproxy）。
  #   理由：sha256.txt（校验清单）与它描述的产物走**同一条通道**，第三方代理可同时改写
  #   两者，使「双源互证」形同虚设——等价一条远程代码执行通道。
  #   若服务器确实访问不了 GitHub，请**显式**设置 GH_MIRROR（例如 GH_MIRROR="https://your-proxy/"），
  #   并自行承担该代理的可信度。
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

# ===== 发布物签名校验（v3.18.7）=====
# 找可用于验签的 python：优先项目虚拟环境（有 cryptography），其次系统 python3。
find_verify_python() {
  local c
  for c in "${APP_PY:-}" "/www/server/pyporject_evn/blog_env/bin/python" python3 python; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
      if "$c" -c "import cryptography" >/dev/null 2>&1; then printf '%s' "$c"; return 0; fi
    fi
  done
  return 1
}

# 对 sha256.txt 做 Ed25519 分离签名校验；通过返回 0，否则 fail_exit。
verify_release_signature() {
  [ -n "${_SIG_VERIFIED:-}" ] && return 0          # 两个包共用一次校验
  if [ "$ALLOW_UNSIGNED" = "1" ]; then
    log "   🚨 已显式设置 ALLOW_UNSIGNED=1 —— 跳过发布物签名校验。"
    log "      这意味着本次更新**不校验发布者身份**，仅在调试或自建发布链过渡期使用。"
    _SIG_VERIFIED=1
    return 0
  fi
  if [ -z "$RELEASE_PUBKEY" ]; then
    fail_exit "❌ 未配置发布签名公钥（RELEASE_PUBKEY / BUILTIN_RELEASE_PUBKEY 均为空），拒绝安装未经校验的包。"
  fi
  if [ -z "${SIG_URL:-}" ]; then
    fail_exit "❌ 该 Release 未附带 sha256.txt.sig（发布物签名）。拒绝安装未经签名的包。若这是自建发布链，请用 v3.18.7+ 的 package.py 重新打包，或临时设 ALLOW_UNSIGNED=1。"
  fi
  gh_fetch "$SIG_URL" "sha256.txt.sig" 2>/dev/null || \
    fail_exit "❌ 签名文件 sha256.txt.sig 下载失败。拒绝继续。"
  [ -f sha256.txt ] || fail_exit "❌ 未取到 sha256.txt，无法验签。"
  local py res
  py=$(find_verify_python) || \
    fail_exit "❌ 找不到带 cryptography 的 python，无法校验发布物签名。请确认项目虚拟环境（requirements.txt 含 cryptography）已安装依赖。"
  res=$("$py" -c "
import base64, sys
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except Exception as e:
    print('NOLIB ' + str(e)[:80]); sys.exit(0)
try:
    pub = base64.b64decode(sys.argv[1].strip())
    sig = base64.b64decode(open(sys.argv[3], 'rb').read().strip())
    data = open(sys.argv[2], 'rb').read()
    Ed25519PublicKey.from_public_bytes(pub).verify(sig, data)
    print('OK')
except Exception as e:
    print('BAD ' + str(e)[:120])
" "$RELEASE_PUBKEY" "sha256.txt" "sha256.txt.sig" 2>&1) || true
  case "$res" in
    OK*)
      log "   ✅ 发布物签名校验通过（sha256.txt 由持有对应私钥的发布者签名）。"
      _SIG_VERIFIED=1
      ;;
    NOLIB*)
      fail_exit "❌ 验签环境缺少 cryptography：$res"
      ;;
    *)
      fail_exit "❌ 发布物签名校验失败（拒绝安装）：$res —— 可能是包被篡改、发布者密钥与本地公钥不匹配，或 Release 不是本项目的官方产物。自建发布者请把公钥配到 RELEASE_PUBKEY。"
      ;;
  esac
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
  # v3.17.2 修复：启动前加载宝塔项目 env 文件（SECRET_KEY / ADMIN_PASSWORD 等），
  # 否则 create_app 会按安全护栏拒绝启动（"缺少环境变量 SECRET_KEY"）。
  local bt_env="/www/server/python_project/vhost/env/${PROJECT_NAME}.env"
  [ -f "$bt_env" ] || bt_env="$(ls /www/server/python_project/vhost/env/*.env 2>/dev/null | head -1)"
  if [ -n "$bt_env" ] && [ -f "$bt_env" ]; then log "   ↳ 已加载环境变量文件: $bt_env"; fi
  ( cd "$APP_DIR" && \
      if [ -n "$bt_env" ] && [ -f "$bt_env" ]; then set -a; . "$bt_env"; set +a; fi; \
      run_as $sd_prefix env "HOME=${APP_DIR%/*}" "PATH=$venv_bin:$PATH" \
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
  # 1. 优先用探测到的真实解释器（GUNICORN_BIN 可能是 python 解释器路径）
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
  # v3.17.2 加固：国内镜像优先 + 总超时 300s + 失败透出 pip 日志（防无限挂起无日志）
  mkdir -p "$WORK" 2>/dev/null || true
  local mirror="https://mirrors.aliyun.com/pypi/simple/"
  local plog="$WORK/pip_install_${TS:-$(date +%s)}.log"
  log "   自动安装依赖: $py -m pip install -i $mirror -r requirements.txt （总超时 300s）..."
  if run_as timeout 300 "$py" -m pip install --timeout 30 -i "$mirror" -r "$APP_DIR/requirements.txt" >"$plog" 2>&1; then
    log "   ✅ Python 依赖已安装/已满足（阿里云镜像）。"
    rm -f "$plog"; return 0
  fi
  log "   ⚠️ 镜像安装失败或超时（总超时 300s），改用官方 PyPI 重试..."
  if run_as timeout 300 "$py" -m pip install --timeout 30 -r "$APP_DIR/requirements.txt" >>"$plog" 2>&1; then
    log "   ✅ Python 依赖已安装/已满足（官方 PyPI）。"
    rm -f "$plog"; return 0
  fi
  log "   ⚠️ 依赖安装失败，pip 输出最后 8 行："
  tail -8 "$plog" 2>/dev/null | while read -r l; do log "     $l"; done
  rm -f "$plog"
  log "   请手动执行: $py -m pip install -i $mirror -r $APP_DIR/requirements.txt"
}

# ===== 校验（v3.1.6 双源互证 + HMAC 可选）=====
verify_checksum() {  # verify_checksum <file> <expected_name>
  local f="$1" expect_name="$2" want got
  # ---- 0) 发布物签名（v3.18.7 强制，唯一的「信任锚」；先于一切哈希比对）----
  verify_release_signature
  # ---- 1) 哈希清单必须取到 ----
  if [ -z "$CHECKSUM_URL" ]; then
    fail_exit "❌ 该 Release 未附带 sha256.txt，无法校验完整性，拒绝安装。"
  fi
  if [ ! -f sha256.txt ]; then
    gh_fetch "$CHECKSUM_URL" "sha256.txt" 2>/dev/null || \
      fail_exit "❌ 校验文件 sha256.txt 下载失败，拒绝在无校验的情况下安装。"
  fi
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
          fail_exit "❌ sha256.txt 带 HMAC 签名但本机无 python3，无法校验。拒绝继续。"
        fi
      else
        log "   ℹ️ sha256.txt 带 HMAC 签名，但未配置 UPDATE_HMAC_KEY → 该层跳过（完整性已由 Ed25519 发布物签名保证）。"
      fi
      ;;
  esac
  want=$(tr -d '\r' < sha256.txt | grep -E "(^| )$expect_name\$" | awk '{print $1}' | head -1)
  if [ -z "$want" ]; then
    fail_exit "❌ sha256.txt 中没有 $expect_name 的记录，无法校验该文件完整性，拒绝安装。"
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
    #       ⚠️ 输出机制陷阱（v3.4.2 初版踩坑）：不能用 sys.exit(N) 靠退出码传结果——
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
        fail_exit "❌ $expect_name 的 zip 注释内嵌 SHA256 与包内容不一致：包或注释可能被单独篡改。已终止更新。"
        ;;
      NO|ERR)
        fail_exit "❌ $expect_name 缺少 zip 注释内嵌哈希或读取异常（双源互证② 无法完成），拒绝安装。"
        ;;
      *)
        fail_exit "❌ $expect_name 的 zip 注释校验无输出，拒绝安装。"
        ;;
    esac
  else
    fail_exit "❌ 无 python3，无法完成 zip 注释双源校验（双源互证②），拒绝安装。"
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
# v3.18.7：发布物分离签名资产（sha256.txt.sig）。注意正则里的 \. 与结尾的 .sig——
# 若写成 [^"]*sha256.txt，会先匹配到 sha256.txt.sig 这一条（同样的前缀）。
SIG_URL=$(echo "$LATEST_JSON" | grep -o '"browser_download_url": *"[^"]*sha256\.txt\.sig"' | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)
if [ -z "$TAG" ] || [ -z "$BACKEND_URL" ]; then
  fail_exit "未找到最新 Release 部署包（tag=$TAG），请稍后重试"
fi
log "   最新版本：$TAG"

# 1b. 版本单调性（v3.18.7）：默认拒绝用更旧的版本覆盖现有站点（报告 §2 建议）。
#     同版本 → 直接收工；远端更低 → 需显式 ALLOW_DOWNGRADE=1 才继续。
LOCAL_VER=$(grep -o 'APP_VERSION *= *"[^"]*"' "$APP_DIR/config.py" 2>/dev/null | sed 's/.*"\([^"]*\)".*/\1/' | head -1)
if [ -n "$LOCAL_VER" ]; then
  _local_no_v="${LOCAL_VER#v}"
  _remote_no_v="${TAG#v}"
  _newest=$(printf '%s\n%s\n' "$_local_no_v" "$_remote_no_v" | sort -V | tail -1)
  if [ "$_remote_no_v" = "$_local_no_v" ]; then
    log "   ℹ️ 本地已是 $TAG（最新），无需更新。"
    set_status "success" "已是最新版本 $TAG"
    exit 0
  fi
  if [ "$_remote_no_v" != "$_newest" ]; then
    if [ "$ALLOW_DOWNGRADE" = "1" ]; then
      log "   🚨 远端 $TAG 低于本地 v$LOCAL_VER，但已显式设置 ALLOW_DOWNGRADE=1 —— 继续降级安装。"
    else
      fail_exit "❌ 远端最新版本 $TAG 低于本地 v$LOCAL_VER，默认拒绝降级覆盖。确需回退请设 ALLOW_DOWNGRADE=1 后重跑。"
    fi
  fi
fi

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
  # v3.9.1：WAL 模式下直接 cp 主库会得到「缺 WAL 中已提交数据」的陈旧快照，
  # 优先用 sqlite3 在线备份产出一致性副本；无 sqlite3 命令时退化为 cp（连同 -wal 一起拷）。
  if command -v sqlite3 >/dev/null 2>&1 \
     && sqlite3 "$APP_DIR/data/blog.db" ".backup '$BACKUP_DIR/blog_$TS.db'" 2>/dev/null; then
    log "   数据库（一致性快照）→ $BACKUP_DIR/blog_$TS.db"
  else
    cp "$APP_DIR/data/blog.db" "$BACKUP_DIR/blog_$TS.db"
    [ -f "$APP_DIR/data/blog.db-wal" ] && cp "$APP_DIR/data/blog.db-wal" "$BACKUP_DIR/blog_$TS.db-wal"
    log "   数据库（直拷，含 WAL）→ $BACKUP_DIR/blog_$TS.db"
  fi
fi
if [ -d "$APP_DIR/static/uploads" ]; then
  mkdir -p "$BACKUP_DIR"
  cp -r "$APP_DIR/static/uploads" "$BACKUP_DIR/uploads_$TS"
  log "   上传图片 → $BACKUP_DIR/uploads_$TS"
fi

# 4. 覆盖后端（跳过 data/，数据库保留）
log "④ 覆盖后端代码..."
set_status "deploying" "正在覆盖后端代码"
BX="$WORK/backend_extract_$TS"   # 唯一临时目录（v3.4.4，避免残留同名目录删不掉导致 mkdir 失败）
rm -rf "$BX"; mkdir -p "$BX"
unzip -q backend.zip -d "$BX" || fail_exit "后端包解压失败（文件可能损坏）"
[ -f "$BX/myblog/config.py" ] || fail_exit "解压产物异常：未找到 myblog/config.py"
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
    run_as cp -rf "$item" "$APP_DIR/" || cp -rf "$item" "$APP_DIR/" || fail_exit "覆盖失败：$item"
  done
fi
# 覆盖后校验：必须真的把新版本写进 $APP_DIR/config.py（杜绝“假成功”）
TAG_VER=${TAG#v}   # tag 形如 v3.4.4，config 里是 3.4.4，去掉前缀再比
new_ver=$(grep -oE 'APP_VERSION[[:space:]]*=[[:space:]]*"[0-9.]+"' "$APP_DIR/config.py" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$new_ver" != "$TAG_VER" ]; then
  fail_exit "❌ 覆盖后版本号校验失败：期望 $TAG_VER（tag $TAG），实际 ${new_ver:-未知}（覆盖未生效，请检查 $APP_DIR 写入权限或磁盘空间）"
fi
log "   完成（data/ 数据库保留，版本已更新为 $new_ver）。"

# 4b. 自动安装 Python 依赖（新增包如 cryptography）
log "④b 检查 Python 依赖..."
install_deps

# 5. 覆盖前端
if [ -d "$FRONT_DIR" ]; then
  log "⑤ 覆盖前端文件..."
  set_status "deploying" "正在覆盖前端文件"
  FX="$WORK/frontend_extract_$TS"   # 唯一临时目录（v3.4.4）
  rm -rf "$FX"; mkdir -p "$FX"
  unzip -q frontend.zip -d "$FX" || fail_exit "前端包解压失败"
  # v3.17.10：先清旧 assets/ 再覆盖——assets 文件名带内容 hash、由 index.html 引用，
  # 新包已含全部所需文件，清掉可避免历史 chunk 无限堆积（此前每次升级残留数份）。
  if [ -d "$FRONT_DIR/assets" ]; then
    run_as rm -rf "$FRONT_DIR/assets" 2>/dev/null || rm -rf "$FRONT_DIR/assets" 2>/dev/null || true
    log "   已清理旧 assets/（历史构建产物）"
  fi
  run_as cp -rf "$FX/." "$FRONT_DIR/" 2>/dev/null \
    || cp -rf "$FX/." "$FRONT_DIR/" || fail_exit "前端覆盖失败（请检查 $FRONT_DIR 写入权限）"
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