"""MCP 入口与实验目录：算子作为 MCP 工具列出与调用，错误结果标为 isError；实验目录只能建在仓库之外。

不连库：这里的调用都在执行前被拒绝。经 MCP 在测试实例上的写入由真实客户端检验。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp.shared.memory import create_connected_server_and_client_session

from e09.config import REPO
from e09.mcp import serve
from e09.operators import OPERATORS
from e09.workspace import main as workspace

NO_STORE: Any = None  # 被拒绝的请求不会用到库


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _tools(monkeypatch: pytest.MonkeyPatch, commit: bool) -> dict[str, Any]:
    if commit:
        monkeypatch.setenv("E09_ENABLE_COMMIT", "1")
    else:
        monkeypatch.delenv("E09_ENABLE_COMMIT", raising=False)
    server = serve(NO_STORE, session="s-test", formed_by="test/model", sync=None)
    async with create_connected_server_and_client_session(server) as client:
        return {t.name: t for t in (await client.list_tools()).tools}


@pytest.mark.anyio
async def test_each_operator_is_a_tool_and_commit_is_listed_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = await _tools(monkeypatch, commit=False)
    assert list(tools) == [n for n in OPERATORS if n != "Commit"]
    assert all(tools[n].inputSchema == OPERATORS[n].parameters for n in tools)
    assert tools["Search"].annotations.readOnlyHint is True
    assert tools["Extract"].annotations.readOnlyHint is False and tools["Extract"].annotations.idempotentHint is True
    commit = (await _tools(monkeypatch, commit=True))["Commit"].annotations
    assert commit.destructiveHint is True and commit.idempotentHint is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "arguments", "at"),
    [
        ("Search", {"type": "Entity", "nope": 1}, "nope"),  # 未知参数
        (
            "Summarize",
            {"abs": "a", "inputs": [], "params": {"focus": "f"}, "payload": {"text": "t"}, "session": "x"},
            "session",
        ),  # 调用环境不是参数
        ("Commit", {"doc": "graph-doc: v0.1", "source": "t"}, "tool"),  # 没有启用
    ],
)
async def test_rejected_calls_are_errors_with_the_unified_shape(
    monkeypatch: pytest.MonkeyPatch, name: str, arguments: dict[str, Any], at: str
) -> None:
    monkeypatch.delenv("E09_ENABLE_COMMIT", raising=False)
    server = serve(NO_STORE, session="s-test", formed_by="test/model", sync=None)
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(name, arguments)
    assert result.isError is True
    out = yaml.safe_load(result.content[0].text)
    assert out["status"] == "rejected"
    assert [(e["rule"], e["at"]) for e in out["errors"]] == [("format", at)]


def test_workspace_is_refused_inside_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert workspace([str(REPO / "experiments/e09/runs/w"), "--formed-by", "p/m"]) == 1
    assert "inside the repository" in capsys.readouterr().err
    assert not (REPO / "experiments/e09/runs/w").exists()


def test_workspace_registers_the_server(tmp_path: Path) -> None:
    target = tmp_path / "w"
    assert workspace([str(target), "--formed-by", "p/m", "--neo4j-uri", "bolt://localhost:7688"]) == 0
    assert [p.relative_to(target).as_posix() for p in sorted(target.rglob("*"))] == [".pi", ".pi/mcp.json"]
    server = json.loads((target / ".pi/mcp.json").read_text(encoding="utf-8"))["mcpServers"]["e09"]
    assert server["args"] == ["-m", "e09.mcp"] and server["exposure"] == "direct"
    assert server["env"] == {"E09_NEO4J_URI": "bolt://localhost:7688", "E09_FORMED_BY": "p/m"}
    assert workspace([str(target), "--formed-by", "p/m"]) == 1  # 已存在且不空
