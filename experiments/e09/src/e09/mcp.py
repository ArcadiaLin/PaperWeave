"""算子的 MCP 入口：把 :data:`e09.operators.OPERATORS` 作为 MCP 工具（stdio）提供给通用 Agent。

    python -m e09.mcp       # 由 MCP 客户端启动；实验目录的 .pi/mcp.json 由 python -m e09.workspace 生成

每个算子是一个工具：工具名就是算子名，``inputSchema`` 就是 ``Operator.parameters``，调用经 ``Operator.call``，与
命令行入口（:mod:`e09.cli`）的结果相同。结果以 YAML 文本返回；``status`` 为 ``rejected``、``blocked`` 或
``conflict`` 时标为 ``isError``，内容照样交给模型。

**调用环境。** MCP 调用不带客户端的会话与模型，所以 Agent 算子的 ``session`` 由服务进程启动时生成（一个客户端
会话对应一个服务进程），``formed_by`` 由环境变量 ``E09_FORMED_BY`` 给出，二者都记在 Artifact 上。

环境变量：``E09_NEO4J_URI`` 等连接参数（:mod:`e09.config`）；``E09_FORMED_BY`` 形成者，Agent 算子写入时必需；
``E09_ENABLE_COMMIT=1`` 时才列出 ``Commit``（它改动知识本身）；``E09_NO_EMBED=1`` 时关闭查询向量，写入后也不补算。
库没有版本记录时服务不启动。
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import UTC, datetime
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .operators import OPERATORS, Context, Operator
from .operators.base import rejected
from .store import Store, UnversionedDatabaseError, check_versioned, open_graph

INSTRUCTIONS = (
    "A knowledge store built from CS papers: papers, the methods, datasets, tasks and experiments they describe, "
    "and artifacts that earlier sessions produced while using that knowledge. Search, Resolve, Traverse and "
    "ReadEvidence find objects, follow relations and read the source lines behind them. Extract, Summarize, "
    "Generate, Check, Verify, Filter and MatrixConstruct record your work: you supply the content and judgments, "
    "the store checks the declared structure and references and keeps each call as an artifact that later "
    "sessions can find and reuse. Commit, when listed, changes the stored knowledge itself."
)


def enabled() -> dict[str, Operator]:
    """列出的算子：``Commit`` 只在 ``E09_ENABLE_COMMIT=1`` 时列出。"""
    commit = os.environ.get("E09_ENABLE_COMMIT") == "1"
    return {name: op for name, op in OPERATORS.items() if name != "Commit" or commit}


def annotations(op: Operator) -> types.ToolAnnotations:
    """MCP 的行为提示：读取算子只读；Agent 算子只追加，相同调用重试返回已有的 Artifact；Commit 可修改与删除。"""
    if not op.writes:
        return types.ToolAnnotations(title=op.label, readOnlyHint=True, openWorldHint=False)
    agent = op.family == "agent"
    return types.ToolAnnotations(
        title=op.label, readOnlyHint=False, destructiveHint=not agent, idempotentHint=agent, openWorldHint=False
    )


def tool(op: Operator) -> types.Tool:
    """一个算子作为 MCP 工具：使用指南接在说明之后。"""
    description = op.description
    if op.prompt_guidelines:
        description += "\n\nGuidelines:\n" + "\n".join(f"- {g}" for g in op.prompt_guidelines)
    return types.Tool(name=op.name, description=description, inputSchema=op.parameters, annotations=annotations(op))


def serve(store: Store, *, session: str, formed_by: str | None, sync: Any) -> Server:
    """MCP 服务：调用逐个执行（同一时间只有一个写入，不与自己的写入冲突）。"""
    server: Server = Server("e09", instructions=INSTRUCTIONS)
    operators = enabled()
    lock = anyio.Lock()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [tool(op) for op in operators.values()]

    @server.call_tool(validate_input=False)  # 参数由算子核对，错误与命令行同形
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        op = operators.get(name)
        if op is None:
            result = rejected([{"rule": "format", "at": "tool", "msg": f"one of {list(operators)}"}])
        else:
            at = datetime.now(UTC).isoformat(timespec="seconds")
            ctx = Context(store, at=at, session=session, formed_by=formed_by, sync=sync)
            async with lock:
                result = await anyio.to_thread.run_sync(op.call, ctx, arguments or {})
        return types.CallToolResult(content=[types.TextContent(type="text", text=result.text)], isError=result.is_error)

    return server


def main() -> int:
    from .config import DATA, NEO4J_DB, NEO4J_URI
    from .store.embedding import embed, sync_embeddings
    from .store.graph import driver

    no_embed = os.environ.get("E09_NO_EMBED") == "1"
    formed_by = os.environ.get("E09_FORMED_BY") or None
    session = f"mcp-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    try:
        check_versioned(driver, database=NEO4J_DB)
    except UnversionedDatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        driver.close()
        return 2
    graph = open_graph(driver, database=NEO4J_DB, file_root=DATA)
    store = Store(driver, graph, DATA, database=NEO4J_DB, embed=None if no_embed else embed)
    server = serve(store, session=session, formed_by=formed_by, sync=None if no_embed else sync_embeddings)
    print(f"e09 MCP: session {session}, formed_by {formed_by}, {NEO4J_URI}", file=sys.stderr)

    async def run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    try:
        anyio.run(run)
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["INSTRUCTIONS", "annotations", "enabled", "main", "serve", "tool"]
