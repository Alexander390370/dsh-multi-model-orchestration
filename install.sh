#!/usr/bin/env bash
# 安装 multi-model-orchestration 技能到 DSH
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/multi-model-orchestration"
dst="$HOME/.agents/skills/multi-model-orchestration"

[ -d "$src" ] || { echo "找不到源目录：$src" >&2; exit 1; }
mkdir -p "$(dirname "$dst")"
if [ -d "$dst" ]; then
  bak="$dst.backup-$(date +%Y%m%d-%H%M%S)"
  cp -r "$dst" "$bak"
  echo "已备份旧版本 → $bak"
fi
cp -r "$src" "$dst"
echo "安装完成：$dst"
echo
echo "自检："
python3 "$dst/tools/modelops.py" check || true
