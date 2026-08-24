#!/usr/bin/env bash
# 安装 llhhy-blog L3 git 钩子（pre-commit + pre-push）
# 用法：bash tools/review/install-hooks.sh
# 卸载：删除 .git/hooks/pre-commit 与 .git/hooks/pre-push（或重跑本脚本选 2）
set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
  echo "错误：不在 git 仓库内。" >&2
  exit 1
fi

HOOKS_DIR="$ROOT/.git/hooks"
SRC_DIR="$ROOT/tools/review"

install_one() {
  local name="$1"
  if [ -e "$HOOKS_DIR/$name" ] && ! head -2 "$HOOKS_DIR/$name" 2>/dev/null | grep -q 'llhhy-blog'; then
    cp "$HOOKS_DIR/$name" "$HOOKS_DIR/$name.bak"
    echo "已备份原 $name 到 $name.bak"
  fi
  cp "$SRC_DIR/$name" "$HOOKS_DIR/$name"
  # LF 兜底：源码强制 LF，但 Windows autocrlf 可能让工作区变 CRLF；
  # .git/hooks 内文件不受 gitattributes 管控，这里统一转 LF 保证 bash 可执行
  sed -i 's/\r$//' "$HOOKS_DIR/$name"
  chmod +x "$HOOKS_DIR/$name"
  echo "✓ 已安装 $name"
}

echo "llhhy-blog L3 钩子安装器"
echo "  1) 安装（pre-commit + pre-push）"
echo "  2) 卸载（删除本项目两个钩子）"
read -r -p "选择 [1/2]：" ANS
if [ "$ANS" = "2" ]; then
  rm -f "$HOOKS_DIR/pre-commit" "$HOOKS_DIR/pre-push"
  echo "已删除 pre-commit / pre-push。原 .bak 备份未动。"
  exit 0
fi

install_one pre-commit
install_one pre-push
echo "完成。下次 commit/push 自动生效。"