"""Search：结构条件、查询通道与排序、续取、数据缺失、诊断与契约错误。"""

from __future__ import annotations

import dataclasses

import pytest
from conftest import problems

from e09.operators.db.search import search
from e09.store import ContractError, Store


def test_enumerates_by_structure_in_id_order(store: Store) -> None:
    out = search(store, "Content", kinds=["Experiment"], where={"evaluates": "method_0003", "role": "target"})
    assert out["meta"]["items"] == ["exp_0001", "exp_0002"]
    assert out["meta"]["coverage"]["order"] == "id"
    assert list(out["nodes"]) == ["exp_0001", "exp_0002"]

    baseline = search(store, "Content", kinds=["Experiment"], where={"evaluates": "method_0002", "role": "baseline"})
    assert baseline["meta"]["items"] == ["exp_0001"]
    stubs = search(store, "Concept", kinds=["Method"], where={"stub": False})
    assert stubs["meta"]["items"] == ["method_0001", "method_0002", "method_0003"]


def test_conditions_on_the_same_record_are_conjunctive_and_lists_disjunctive(store: Store) -> None:
    both = search(store, "Content", kinds=["Experiment"], where={"uses": "dataset_0002", "evaluates": "method_0003"})
    assert both["meta"]["items"] == ["exp_0001"]
    either = search(store, "Concept", where={"broader": ["method_0001", "task_0001"]}, kinds=["Method", "Task"])
    assert either["meta"]["items"] == ["method_0003", "task_0002"]


def test_expand_parts_relaxes_a_dataset_reference(store: Store) -> None:
    plain = search(store, "Content", kinds=["Experiment"], where={"uses": "dataset_0001"})
    assert plain["meta"]["items"] == []
    assert plain["meta"]["diagnostics"]["expandable"]["refs"] == ["exp_0001"]

    expanded = search(store, "Content", kinds=["Experiment"], where={"uses": "dataset_0001"}, expand={"parts": 1})
    assert expanded["meta"]["items"] == ["exp_0001"]
    assert expanded["meta"]["coverage"]["expanded"] == {"dataset_0001": ["dataset_0002"]}


def test_uses_requires_the_evaluation_role_and_reports_missing_roles(store: Store) -> None:
    out = search(store, "Content", kinds=["Experiment"], where={"uses": "dataset_0003"})
    assert out["meta"]["items"] == ["exp_0001"]
    assert out["meta"]["diagnostics"]["role_missing"] == {"count": 1, "refs": ["exp_0002"]}


def test_exact_name_hits_come_first(store: Store) -> None:
    out = search(store, "Concept", {"mention": "D-Linear"}, kinds=["Method"])
    meta = out["meta"]
    assert meta["items"][0] == "method_0003"
    assert meta["bindings"]["method_0003"] == {"exact": "name"}
    assert meta["coverage"]["channels"]["semantic"] == "disabled"  # 测试中没有向量服务

    by_id = search(store, "Entity", {"identifier": "arxiv:2205.13504"})
    assert by_id["meta"]["items"] == ["paper_0001"]
    assert by_id["meta"]["bindings"]["paper_0001"] == {"exact": "identifier"}


def test_text_channel_ranks_within_the_conditions(store: Store) -> None:
    out = search(store, "Content", "decomposition ablation", kinds=["Experiment"])
    assert out["meta"]["items"][0] == "exp_0002"
    assert out["meta"]["bindings"]["exp_0002"]["lexical_text"] == 1

    scoped = search(store, "Content", "decomposition ablation", where={"uses": "dataset_0002"}, kinds=["Experiment"])
    assert scoped["meta"]["items"] == []


def test_a_failing_channel_is_reported_not_treated_as_empty(store: Store) -> None:
    def embed(texts: list[str]) -> list[list[float]]:
        raise ConnectionError("embedding service unreachable")

    out = search(dataclasses.replace(store, embed=embed), "Concept", {"mention": "DLinear"})
    assert out["meta"]["coverage"]["channels"]["semantic"].startswith("error: ConnectionError")
    assert out["meta"]["items"][0] == "method_0003"


def test_budget_and_continuation(store: Store) -> None:
    first = search(store, "Entity", kinds=["Dataset"], budget=2)
    assert first["meta"]["items"] == ["dataset_0001", "dataset_0002"]
    assert first["meta"]["coverage"]["truncated"] is True
    rest = search(store, "Entity", kinds=["Dataset"], budget=2, continuation=first["meta"]["continuation"])
    assert rest["meta"]["items"] == ["dataset_0003"]
    assert rest["meta"]["continuation"] is None


def test_scope_limits_content_to_papers(store: Store) -> None:
    out = search(store, "Content", kinds=["Experiment"], scope=["paper_0001"])
    assert out["meta"]["items"] == ["exp_0001", "exp_0002"]
    assert "material_" in out["meta"]["source_refs"][0]


def test_missing_references_return_an_empty_result(store: Store) -> None:
    out = search(store, "Content", kinds=["Experiment"], where={"evaluates": "method_0099"})
    assert out["meta"]["items"] == [] and out["nodes"] == {}
    assert out["meta"]["missing"] == [{"ref": "method_0099", "param": "where.evaluates", "missing_in": "store"}]


@pytest.mark.parametrize(
    ("kwargs", "at"),
    [
        ({"type": "Paper"}, ["type"]),
        ({"type": "Artifact", "kinds": ["Check"]}, ["kinds"]),  # Artifact 没有 kind，用 where.op
        ({"type": "Artifact", "where": {"op": "Explain"}}, ["where.op"]),
        ({"type": "Artifact", "query": {"mention": "x"}}, ["query.mention"]),
        ({"type": "Concept", "where": {"evaluates": "method_0003"}}, ["where.evaluates"]),  # 只有 Experiment 能带
        ({"type": "Content", "where": {"evaluates": "method_0003"}}, ["where.evaluates"]),  # kinds 没有限定
        ({"type": "Content", "kinds": ["Experiment"], "where": {"evaluates": "dataset_0001"}}, ["where.evaluates"]),
        ({"type": "Content", "kinds": ["Experiment"], "where": {"role": "target"}}, ["where.role"]),
        ({"type": "Entity", "where": {"colour": "red"}}, ["where.colour"]),
        ({"type": "Content", "query": {"mention": "DLinear"}}, ["query.mention"]),
        ({"type": "Entity", "query": {"identifier": "isbn:123"}}, ["query.identifier"]),
        ({"type": "Entity", "scope": ["paper_0001"]}, ["scope"]),
        ({"type": "Entity", "budget": 0}, ["budget"]),
        ({"type": "Concept", "kinds": ["Dataset"]}, ["kinds"]),
    ],
)
def test_contract_errors(store: Store, kwargs: dict, at: list[str]) -> None:
    with pytest.raises(ContractError) as exc:
        search(store, **kwargs)
    assert problems(exc) == at
