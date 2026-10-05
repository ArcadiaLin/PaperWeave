"""Agent 算子测试的共用部件：在测试实例上写入一小份图，Artifact 文档写到临时的材料根目录。

只在设置了 ``GRAPH_VC_TEST_NEO4J_URI`` 时运行（infra/neo4j-test，端口 7688），要求开始时库为空，结束后清空库、
约束与索引。不会连 neo4j-e09。每个测试模块重建一次图，模块内的测试按顺序共享写入的 Artifact。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from e09.read import Store
from e09.use import OperatorError, write_artifact
from e09.write import Context, Neo4jReader, open_graph, setup_database
from e09.write.cli import run

TEST_URI = os.environ.get("GRAPH_VC_TEST_NEO4J_URI")
TEST_AUTH = (
    os.environ.get("GRAPH_VC_TEST_NEO4J_USER", "neo4j"),
    os.environ.get("GRAPH_VC_TEST_NEO4J_PASSWORD", "password"),
)
AT = "2026-10-05T12:00:00+00:00"
MATERIAL = "papers/2023-DLinear/paper.md"

GRAPH = """
graph-doc: v0.1
by: seed
nodes:
  $ltsf:
    kind: Task
    name: Long-term time series forecasting
    definition: Forecasting with a long horizon.
  $linear:
    kind: Method
    name: Linear forecasting model
    definition: Models that map the look-back window to the horizon with a linear layer.
  $tf:
    kind: Method
    name: Transformer-based forecasting
    definition: Forecasting models built on Transformer architectures.
  $etth1:
    kind: Dataset
    name: ETTh1
    description: Hourly electricity transformer temperature data.
  $weather:
    kind: Dataset
    name: Weather
    description: Meteorological indicators recorded every ten minutes.
  $paper:
    kind: Paper
    name: Are Transformers Effective for Time Series Forecasting?
    year: 2023
    material: papers/2023-DLinear/paper.md
    description: Questions whether Transformers are effective for LTSF and introduces DLinear.
  $dlinear:
    kind: Method
    name: DLinear
    definition: A linear model on a trend and remainder decomposition.
    BROADER: [$linear]
  $main:
    kind: Experiment
    anchors: [S5.T2]
    text: Multivariate long-term forecasting comparing DLinear with Transformer baselines.
    FROM:
      - {to: $paper, locators: ["5.2 Comparison::10:20"]}
    EVALUATES:
      - {to: $dlinear, role: target}
      - {to: $tf, role: baseline}
    USES:
      - {to: $etth1, role: evaluation_data}
      - {to: $weather, role: evaluation_data}
    ON_TASK: [$ltsf]
"""
# task_0001、method_0001 linear、method_0002 tf、dataset_0001 etth1、dataset_0002 weather、paper_0001、
# method_0003 dlinear、exp_0001
SOURCE = "paper_0001::5.2 Comparison::10:12"


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Store]:
    if TEST_URI is None:
        pytest.skip("GRAPH_VC_TEST_NEO4J_URI is not set")
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(TEST_URI, auth=TEST_AUTH, notifications_disabled_classifications=["UNRECOGNIZED"])
    count = driver.execute_query("MATCH (n) RETURN count(n) AS c").records[0]["c"]
    if count:
        driver.close()
        pytest.skip(f"refusing to run: test database at {TEST_URI} is not empty ({count} nodes)")
    root = tmp_path_factory.mktemp("materials")
    file = root / MATERIAL
    file.parent.mkdir(parents=True)
    file.write_text("".join(f"line {i}\n" for i in range(1, 61)), encoding="utf-8")
    graph = open_graph(driver, file_root=root)
    try:
        commit_doc(Store(driver, graph, root), GRAPH, source="seed:test")
        setup_database(graph, driver)
        yield Store(driver, graph, root)
    finally:
        driver.execute_query("MATCH (n) DETACH DELETE n")
        for record in driver.execute_query("SHOW CONSTRAINTS YIELD name").records:
            driver.execute_query(f"DROP CONSTRAINT {record['name']}")
        for record in driver.execute_query("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name").records:
            driver.execute_query(f"DROP INDEX {record['name']}")
        driver.close()


def commit_doc(store: Store, text: str, *, source: str = "test", commit: bool = True) -> dict[str, Any]:
    """经 Commit 写入路径提交（或 dry_run）一份 graph-doc。"""
    ctx = Context(Neo4jReader(store.graph, store.driver), source, AT, store.material_root)
    return run(text, graph=store.graph, driver=store.driver, ctx=ctx, commit=commit)


def call(op: str, inputs: list[str], params: dict[str, Any], payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    request = {"op": op, "abs": f"A {op} artifact for the tests.", "inputs": inputs, "params": params}
    request.update(payload=payload, session="s-test", formed_by="claude", **extra)
    return request


def write(store: Store, request: dict[str, Any]) -> dict[str, Any]:
    return write_artifact(store, request, at=AT)


def errors(store: Store, request: dict[str, Any]) -> list[tuple[str, str]]:
    """调用被拒绝时的 (规则, 位置)；同时确认什么也没有写入。"""
    head = store.graph.head()
    with pytest.raises(OperatorError) as exc:
        write(store, request)
    assert store.graph.head() == head
    return [(e["rule"], e["where"]) for e in exc.value.errors]


EXTRACT = call(
    "Extract",
    ["exp_0001", "method_0003", "dataset_0001", "dataset_0002", SOURCE],
    {
        "schema": {
            "fields": {"method": "ref", "dataset": "ref", "horizon": "integer", "mse": "number", "split": "string"},
            "required": ["mse"],
            "key": ["method", "dataset", "horizon"],
        }
    },
    {
        "rows": [
            {"method": "method_0003", "dataset": "dataset_0001", "horizon": 96, "mse": 0.375, "source": SOURCE},
            {"method": "method_0003", "dataset": "dataset_0002", "horizon": 96, "mse": 0.176, "source": SOURCE},
        ]
    },
    title="DLinear MSE on ETTh1 and Weather",
)
KEYS = ["method_0003-dataset_0001-96", "method_0003-dataset_0002-96"]


def write_material(root: Path, path: str, text: str) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
