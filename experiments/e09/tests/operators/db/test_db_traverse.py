"""Traverse：路径、方向、终点与边条件、传递关系的深度、端点表检查与契约错误。"""

from __future__ import annotations

import pytest
from conftest import problems

from e09.operators.db.traverse import traverse
from e09.store import ContractError, Store


def test_an_empty_path_reads_the_start(store: Store) -> None:
    out = traverse(store, ["method_0003", "dataset_0002"])
    assert out["meta"]["items"] == ["method_0003", "dataset_0002"]
    assert out["meta"]["bindings"] == [["method_0003"], ["dataset_0002"]]
    assert out["nodes"]["method_0003"]["name"] == "DLinear"


def test_paths_keep_direction_and_intermediate_nodes(store: Store) -> None:
    out = traverse(store, ["method_0003"], [{"rel": "EVALUATES", "dir": "in"}, {"rel": "USES", "dir": "out"}])
    assert out["meta"]["bindings"] == [
        ["method_0003", "<-EVALUATES-", "exp_0001", "-USES->", "dataset_0002"],
        ["method_0003", "<-EVALUATES-", "exp_0001", "-USES->", "dataset_0003"],
        ["method_0003", "<-EVALUATES-", "exp_0002", "-USES->", "dataset_0003"],
    ]
    assert out["meta"]["items"] == ["dataset_0002", "dataset_0003"]
    assert list(out["nodes"]) == ["method_0003", "exp_0001", "dataset_0002", "dataset_0003", "exp_0002"]


def test_edge_and_end_conditions(store: Store) -> None:
    baseline = traverse(store, ["exp_0001"], [{"rel": "EVALUATES", "edge": {"role": "baseline"}}])
    assert baseline["meta"]["items"] == ["method_0002"]
    parts = traverse(store, ["exp_0001"], [{"rel": "USES", "where": {"part_of": "dataset_0001"}}])
    assert parts["meta"]["items"] == ["dataset_0002"]
    claims = traverse(store, ["method_0003"], [{"rel": "EVALUATES", "dir": "in", "kinds": ["Experiment"]}])
    assert claims["meta"]["items"] == ["exp_0001", "exp_0002"]


def test_depth_follows_transitive_relationships(store: Store) -> None:
    out = traverse(store, ["task_0001"], [{"rel": "BROADER", "dir": "in", "depth": 2}])
    assert out["meta"]["bindings"] == [["task_0001", "<-BROADER-", "task_0002"]]
    up = traverse(store, ["method_0003"], [{"rel": "BROADER", "depth": 3}])
    assert up["meta"]["items"] == ["method_0001"]


def test_budget_counts_paths(store: Store) -> None:
    first = traverse(store, ["paper_0001"], [{"rel": "FROM", "dir": "in"}], budget=1)
    assert first["meta"]["items"] == ["exp_0001"] and first["meta"]["coverage"]["matched"] == 2
    rest = traverse(store, ["paper_0001"], [{"rel": "FROM", "dir": "in"}], budget=1, continuation=1)
    assert rest["meta"]["items"] == ["exp_0002"] and rest["meta"]["continuation"] is None


def test_a_missing_start_is_data_not_an_error(store: Store) -> None:
    out = traverse(store, ["method_0099"], [{"rel": "EVALUATES", "dir": "in"}])
    assert out["meta"]["items"] == []
    assert out["meta"]["missing"] == [{"ref": "method_0099", "param": "start", "missing_in": "store"}]


@pytest.mark.parametrize(
    ("start", "path", "at"),
    [
        (["method_0003"], [{"rel": "EVALUATES", "dir": "out"}], ["path[0]"]),  # 端点表中不成立
        (["method_0003"], [{"rel": "EVALUATES", "dir": "in", "kinds": ["Claim"]}], ["path[0]"]),
        (["exp_0001"], [{"rel": "USES", "depth": 2}], ["path[0].depth"]),
        (["exp_0001"], [{"rel": "NAMES"}], ["path[0].rel"]),
        (["exp_0001"], [{"rel": "USED"}], ["path[0]"]),  # USED 只从 Artifact 出发
        (["exp_0001"], [{"rel": "USED", "dir": "in", "depth": 2}], ["path[0].depth"]),
        (["exp_0001"], [{"rel": "USES", "dir": "up"}], ["path[0].dir"]),
        (["exp_0001"], [{"rel": "USES", "as": "x"}], ["path[0]"]),
        (["exp_0001"], [{"rel": "USES", "where": {"evaluates": "method_0003"}}], ["path[0].where.evaluates"]),
    ],
)
def test_contract_errors(store: Store, start: list[str], path: list[dict], at: list[str]) -> None:
    with pytest.raises(ContractError) as exc:
        traverse(store, start, path)
    assert problems(exc) == at


def test_system_records_cannot_be_started_from(store: Store) -> None:
    material = traverse(store, ["paper_0001"])["nodes"]["paper_0001"]["_material"]
    with pytest.raises(ContractError):
        traverse(store, [material])
