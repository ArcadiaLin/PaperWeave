"""生成一个实验目录：通用 Agent（默认配置的 pi）在这里启动，经 MCP 使用 E09 的算子。

    python -m e09.workspace <目录> [--formed-by provider/model] [--neo4j-uri bolt://...] [--enable-commit] [--no-embed]

目录里只有 ``.pi/mcp.json``：登记 ``e09`` 服务（``python -m e09.mcp``，工具直接列给模型）。pi 会从工作目录及其
上层目录加载 ``AGENTS.md`` 等上下文文件，所以目录必须在仓库之外；目录已存在且不空时拒绝。``formed_by`` 默认取
pi 的默认模型（``$PI_CODING_AGENT_DIR`` 或 ``~/.pi/agent`` 下 ``settings.json`` 的 ``defaultProvider/defaultModel``）。
项目级的 ``.pi/mcp.json`` 只在信任该目录后加载：第一次在目录中启动 pi 时确认信任，非交互模式用 ``--approve``。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import NEO4J_URI, REPO

SERVER = "e09"


def default_formed_by() -> str | None:
    """pi 的默认模型，写成 ``provider/model``。"""
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi/agent")).expanduser()
    try:
        settings = json.loads((agent / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    provider, model = settings.get("defaultProvider"), settings.get("defaultModel")
    return f"{provider}/{model}" if provider and model else None


def mcp_config(*, formed_by: str, neo4j_uri: str, enable_commit: bool, no_embed: bool) -> dict[str, Any]:
    """``.pi/mcp.json`` 的内容。stdio 服务只拿到这里写出的环境变量，连接参数因此都写明。"""
    env = {"E09_NEO4J_URI": neo4j_uri, "E09_FORMED_BY": formed_by}
    if enable_commit:
        env["E09_ENABLE_COMMIT"] = "1"
    if no_embed:
        env["E09_NO_EMBED"] = "1"
    server = {
        "command": str(REPO / ".venv/bin/python"),
        "args": ["-m", "e09.mcp"],
        "cwd": str(REPO / "experiments/e09"),
        "env": env,
        "exposure": "direct",
        "timeout": 300,
        "description": "Knowledge store of CS papers: find, traverse and read evidence; record work as artifacts",
    }
    return {"mcpServers": {SERVER: server}}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target = Path(args.dir).expanduser().resolve()
    if target == REPO or REPO in target.parents:
        print(f"error: {target} is inside the repository; pi would load its AGENTS.md", file=sys.stderr)
        return 1
    if target.exists() and any(target.iterdir()):
        print(f"error: {target} exists and is not empty", file=sys.stderr)
        return 1
    formed_by = args.formed_by or default_formed_by()
    if not formed_by:
        print("error: no pi default model found; give --formed-by provider/model", file=sys.stderr)
        return 1
    config = mcp_config(
        formed_by=formed_by, neo4j_uri=args.neo4j_uri, enable_commit=args.enable_commit, no_embed=args.no_embed
    )
    (target / ".pi").mkdir(parents=True)
    (target / ".pi/mcp.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{target}/.pi/mcp.json  (formed_by {formed_by}, {args.neo4j_uri})")
    print(f"cd {target} && pi      # trust the directory on first start; non-interactive runs: --approve")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m e09.workspace", description=__doc__.split("\n\n")[0])
    parser.add_argument("dir", help="实验目录，须在仓库之外")
    parser.add_argument("--formed-by", help="形成者 provider/model；默认取 pi 的默认模型")
    parser.add_argument("--neo4j-uri", default=NEO4J_URI, help=f"服务连接的库（默认 {NEO4J_URI}）")
    parser.add_argument("--enable-commit", action="store_true", help="列出 Commit（改动知识本身）")
    parser.add_argument("--no-embed", action="store_true", help="关闭查询向量，写入后也不补算")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["default_formed_by", "main", "mcp_config"]
