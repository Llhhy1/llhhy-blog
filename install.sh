#!/usr/bin/env bash
# =============================================================
# llhhy-blog 半自动装机脚本
#
# 诚实边界（请务必先读完这一段）
# -------------------------------------------------------------
# 首次安装里，这三步是**宝塔面板 GUI 操作**，脚本做不到，也不该暗中代劳
# （代劳会失败得更隐蔽，排查成本远高于自己点三下）：
#     ① 创建 Python 虚拟环境
#     ② 创建 Python 项目（绑定 venv + 启动命令）
#     ③ 创建网站（Nginx 站点 / HTTPS 证书）
# 本脚本负责剩下所有能脚本化的部分：解压、依赖、迁移、Nginx 配置生成、
# 目录权限、以及**逐条告诉你剩下要点哪几下**。
#
# 两条安全设计：
#   1. 默认 dry-run：不加 --apply 只体检不动文件系统。
#   2. 检测到已部署（data/blog.db 存在）立即退出 —— 装机绝不是升级，
#      升级请跑 update.sh。这一条是为了防止有人在跑着的站上误跑装机。
#
# 用法：
#   bash install.sh                    # 体检（dry-run，只读，随时可跑）
#   bash install.sh --apply            # 真正执行
#   TAG=v4.0.0 bash install.sh --apply # 指定版本（默认最新 Release）
#
# 前置：Release 里要有 myblog-backend.zip 与 vue-frontend-dist.zip
# =============================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/www/wwwroot/myblog}"
FRONT_DIR="${FRONT_DIR:-/www/wwwroot/vue-frontend}"
REPO="${REPO:-Llhhy1/llhhy-blog}"
WORK="${WORK:-/tmp/llhhy_install}"
TAG="${TAG:-latest}"

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  ✓ %s\n' "$*"; }
bad()  { printf '  ✗ %s\n' "$*"; }
warn() { printf '  ⚠ %s\n' "$*"; }
run()  {
  if [ "$APPLY" = "1" ]; then "$@"; else printf '  [dry-run] %s\n' "$*"; fi
}
die() { printf '\n\033[1;31m✗ 中止：%s\033[0m\n' "$*"; exit 1; }

if [ "$APPLY" = "1" ]; then
  say "=============================================="
  say " llhhy-blog 装机（执行模式）"
  say " 应用目录：$APP_DIR"
  say " 前端目录：$FRONT_DIR"
  say " 目标版本：$TAG"
  say "=============================================="
else
  say "=============================================="
  say " llhhy-blog 装机（体检模式 · 不会改动任何文件）"
  say " 确认输出无误后，加 --apply 真正执行。"
  say "=============================================="
fi

# ---------- 第 0 步：安全闸 ----------
step "第 0 步：安全检查"

if [ -f "$APP_DIR/data/blog.db" ] || [ -f "$APP_DIR/instance/blog.db" ]; then
  die "检测到已有数据库（$APP_DIR/data/blog.db）。
      这是**已部署**的实例 —— 装机脚本会覆盖数据，绝不在这里继续。
      升级请改用：bash $APP_DIR/update.sh"
fi
ok "目标目录无现有数据库，可以继续装机"

if [ "$(id -u)" != "0" ]; then
  warn "当前不是 root。装依赖 / 建目录 / 写 Nginx 配置可能需要 root，建议 root 执行。"
fi

# ---------- 第 1 步：环境体检 ----------
step "第 1 步：环境体检"

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  bad "找不到 python3 —— 请先在宝塔「软件商店」安装 Python"
else
  VER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo '未知')"
  MAJ="$(echo "$VER" | cut -d. -f1)"
  MIN="$(echo "$VER" | cut -d. -f2)"
  if [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 10 ]; then
    ok "Python $VER（满足 ≥3.10 要求）"
  else
    bad "Python $VER —— 低于 3.10，requirements 会因 bleach/cryptography 的 requires_python 下限安装失败。
      请在宝塔安装 Python 3.13 或更高版本。"
  fi
fi

command -v unzip >/dev/null 2>&1 && ok "unzip 可用" || warn "缺 unzip，请先安装：apt install -y unzip"
command -v nginx  >/dev/null 2>&1 && ok "nginx 可用" || warn "缺 nginx 或不在 PATH（宝塔通常装了）"

# ---------- 第 2 步：取发布包 ----------
step "第 2 步：获取 Release 发布包"

if [ "$TAG" = "latest" ]; then
  API="https://api.github.com/repos/$REPO/releases/latest"
else
  API="https://api.github.com/repos/$REPO/releases/tags/$TAG"
fi

BACKEND_URL=""
FRONT_URL=""
if command -v curl >/dev/null 2>&1; then
  JSON="$(curl -sSL --max-time 20 "$API" 2>/dev/null || true)"
  if [ -n "$JSON" ]; then
    BACKEND_URL="$(printf '%s' "$JSON" | grep -o '"browser_download_url": *"[^"]*myblog-backend.zip"' \
                   | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)"
    FRONT_URL="$(printf '%s'   "$JSON" | grep -o '"browser_download_url": *"[^"]*vue-frontend-dist.zip"' \
                 | sed 's/.*"\(http[^"]*\)".*/\1/' | head -1)"
  fi
fi

if [ -n "$BACKEND_URL" ] && [ -n "$FRONT_URL" ]; then
  ok "后端包：$BACKEND_URL"
  ok "前端包：$FRONT_URL"
  # 注：这里不重复实现 update.sh 那套 Ed25519 签名校验。装机是全新环境，
  # 首次拿到的是干净来源；后续每次升级仍由 update.sh 负责完整性校验。
  run mkdir -p "$WORK"
  run curl -sSL --max-time 300 -o "$WORK/backend.zip"  "$BACKEND_URL"
  run curl -sSL --max-time 300 -o "$WORK/frontend.zip" "$FRONT_URL"
else
  warn "无法自动取得下载链接（GitHub 不通？）。请手动放置两个 zip 到 $WORK/"
  say "  需要：$WORK/backend.zip  和  $WORK/frontend.zip"
  run mkdir -p "$WORK"
fi

# ---------- 第 3 步：解压到站点目录 ----------
step "第 3 步：解压部署"

if [ "$APPLY" = "1" ]; then
  if [ -f "$WORK/backend.zip" ]; then
    run mkdir -p "$APP_DIR"
    run unzip -oq "$WORK/backend.zip" -d "$APP_DIR"
    ok "后端已解压到 $APP_DIR"
  else
    warn "缺少 backend.zip，跳过"
  fi
  if [ -f "$WORK/frontend.zip" ]; then
    run mkdir -p "$FRONT_DIR"
    run unzip -oq "$WORK/frontend.zip" -d "$FRONT_DIR"
    ok "前端已解压到 $FRONT_DIR"
  else
    warn "缺少 frontend.zip，跳过"
  fi
  run mkdir -p "$APP_DIR/data"
else
  say "  [dry-run] 会把 backend.zip → $APP_DIR，frontend.zip → $FRONT_DIR"
fi

# ---------- 第 4 步：虚拟环境与依赖 ----------
step "第 4 步：虚拟环境 + 依赖"

VENV="$APP_DIR/venv"
if [ -d "$VENV" ]; then
  ok "已存在虚拟环境 $VENV"
elif [ "$APPLY" = "1" ]; then
  warn "虚拟环境不存在。请先在宝塔创建（见文末「面板步骤」），"
  warn "或由本脚本创建到 $VENV："
  run "$PY" -m venv "$VENV"
else
  say "  [dry-run] 缺虚拟环境，将在 $VENV 创建（或你在宝塔创建）"
fi

REQ="$APP_DIR/requirements.txt"
if [ -f "$REQ" ]; then
  ok "requirements.txt 已就位"
  if [ -x "$VENV/bin/python" ] && [ "$APPLY" = "1" ]; then
    run "$VENV/bin/python" -m pip install --upgrade pip
    run "$VENV/bin/python" -m pip install -r "$REQ"
    ok "依赖安装完成"
  elif [ "$APPLY" = "1" ]; then
    warn "虚拟环境 python 不可用，跳过依赖安装"
  else
    say "  [dry-run] 将执行：$VENV/bin/python -m pip install -r $REQ"
  fi
else
  warn "未找到 $REQ（后端包未就位？）"
fi

# ---------- 第 5 步：数据库迁移 ----------
step "第 5 步：数据库初始化 / 迁移"

say "  ⚠ 生产禁止 db.create_all()，一律走 Alembic。"
if [ -x "$VENV/bin/python" ] && [ -d "$APP_DIR/migrations" ] && [ "$APPLY" = "1" ]; then
  run env BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app \
      "$VENV/bin/python" -m flask db upgrade
  ok "迁移完成（head 应为 c7a2f19b4d30）"
else
  say "  [dry-run] 将执行："
  say "    BLOG_MIGRATE_ONLY=1 FLASK_APP=app:create_app $VENV/bin/python -m flask db upgrade"
  say "    （需在 $APP_DIR 目录下执行）"
fi

# ---------- 第 6 步：环境变量提醒 ----------
step "第 6 步：关键环境变量"

if [ -f "$APP_DIR/.env" ]; then
  ok ".env 已存在"
else
  warn "尚无 .env。至少需要 SECRET_KEY。"
  GEN="$(openssl rand -hex 32 2>/dev/null || true)"
  if [ "$APPLY" = "1" ] && [ -n "$GEN" ]; then
    # 直接写文件、绝不落屏：密钥一旦打印就会被终端快照 / 部署日志留存
    printf 'SECRET_KEY=%s\n' "$GEN" > "$APP_DIR/.env"
    run chmod 600 "$APP_DIR/.env"
    ok "已写入 $APP_DIR/.env（权限 600），密钥不打印到终端"
  elif [ "$APPLY" = "1" ]; then
    warn "openssl 不可用，无法自动生成；请手动写入 $APP_DIR/.env 的 SECRET_KEY"
  else
    say "    [dry-run] 将生成随机 SECRET_KEY 写入 $APP_DIR/.env（chmod 600，不打印到屏幕）"
  fi
  say "    如需显式指定数据库：DATABASE_URL=sqlite:///$APP_DIR/data/blog.db"
fi
warn "提醒：2FA 密钥用 SECRET_KEY 加密落库，启用 2FA 后切勿再改 SECRET_KEY。"
warn "提醒：定时备份任务（cron）不带项目环境变量，详见 deploy_guide「第三部分：日常维护」。"

# ---------- 第 7 步：Nginx 配置 ----------
step "第 7 步：Nginx 配置模板"

NGX_OUT="$WORK/nginx-site.conf"
if [ "$APPLY" = "1" ]; then
mkdir -p "$WORK"
cat > "$NGX_OUT" <<'NGXEOF'
server {
    listen 80;
    server_name _CHANGEME_DOMAIN_;

    # 前端静态（Vue SPA）
    root _CHANGEME_FRONT_;
    index index.html;
    try_files $uri $uri/ /index.html;

    # 后端 API / 后台 / 静态资源 → gunicorn
    location /api/    { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location /admin   { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location /static/ { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location /mcp     { proxy_pass http://127.0.0.1:8686; include proxy_params; }

    # SEO 精确反代：漏了会被 SPA 兜底成 index.html
    location = /feed.xml   { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location = /feed.atom  { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location = /sitemap.xml{ proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location = /robots.txt { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location ^~ /api/og/   { proxy_pass http://127.0.0.1:8686; include proxy_params; }

    # SPA 路由固定页 302
    location = /login    { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location = /register { proxy_pass http://127.0.0.1:8686; include proxy_params; }
    location = /twofa    { proxy_pass http://127.0.0.1:8686; include proxy_params; }
}
NGXEOF
  ok "模板已生成：$NGX_OUT"
  warn "模板只是**起点**。SEO 爬虫通道（map \$http_user_agent）与攻击面收窄等完整配置"
  warn "见 myblog/deploy_guide.md 第二部分「第 4 / 4b 步」—— 请照它核对后再启用。"
else
  say "  [dry-run] 将生成 Nginx 模板到 $NGX_OUT"
  say "  （模板仅含骨架，完整口径见 deploy_guide.md）"
fi

# ---------- 收尾：必须人工完成的部分 ----------
step "剩余步骤（脚本做不到，请在宝塔面板完成）"
cat <<'EOF'
  ① 创建 Python 虚拟环境 —— 宝塔「Python 版本管理」→ 选 Python 3.13 → 创建虚拟环境
  ② 创建 Python 项目   —— 宝塔「网站」→「Python项目」→ 添加项目
                             项目目录填 /www/wwwroot/myblog
                             启动命令里用上面那个 venv 的 gunicorn，端口 8686
  ③ 创建网站           —— 宝塔「网站」→ 添加站点 → 根目录填前端目录
                             并按上面生成的 Nginx 模板合并配置
  ④ 申请 HTTPS         —— 站点设置 → SSL → Let's Encrypt
  ⑤ 首次登录后台设置管理员

  以上都完成后，日常升级就只剩一条命令：
      bash /www/wwwroot/myblog/update.sh
EOF

if [ "$APPLY" = "1" ]; then
  say ""
  ok "装机流程执行完毕。请按上面剩余步骤在面板收尾。"
else
  say ""
  say "体检完成（未改动任何文件）。确认无误后执行："
  say "    bash $0 --apply"
fi
