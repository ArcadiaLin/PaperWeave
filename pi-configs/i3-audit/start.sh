#!/usr/bin/env bash
set -euo pipefail

# I3 审计配置：交互式打开某一组（S、S-Cypher、R0）的 pi，调试用。
# 命令由 e09.i3.run 统一构造，批量运行用：.venv/bin/python -m e09.i3.run run ...
#   ./pi-configs/i3-audit/start.sh S
config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$config_dir/../.." && pwd)"
cd "$repo"
exec "$repo/.venv/bin/python" -m e09.i3.run shell "$@"
