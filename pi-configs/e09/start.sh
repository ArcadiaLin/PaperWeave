#!/usr/bin/env bash
set -euo pipefail

# E09 算子配置：每个算子注册为一个工具（extensions/ 中一个脚本一个算子），执行经 python -m e09。
# 不启用内置工具，也不加载仓库 AGENTS.md、skills 和 prompt 模板；Agent 只能经算子读写知识库。
#   ./pi-configs/e09/start.sh                      # 连 E09_NEO4J_URI 所指的库，默认 neo4j-e09（7687）
#   E09_ENABLE_COMMIT=1 ./pi-configs/e09/start.sh  # 同时启用 Commit（默认注册但不启用）
#   E09_NO_EMBED=1 ./pi-configs/e09/start.sh       # 不用向量服务
config_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$config_dir/../.." && pwd)"
export PI_CODING_AGENT_DIR="$config_dir/agent"
export E09_REPO="$repo"
export E09_PYTHON="$repo/.venv/bin/python"
exec pi \
  --system-prompt "$config_dir/SYSTEM.md" \
  --session-dir "$config_dir/sessions" \
  --no-builtin-tools \
  --no-context-files \
  --no-skills \
  --no-prompt-templates \
  --no-extensions \
  --extension "$config_dir" \
  "$@"
