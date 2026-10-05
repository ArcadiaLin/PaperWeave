"""内存状态上的前提核对与应用。不需要数据库。"""

from __future__ import annotations

import pytest

from graph_vc import Changeset, ConflictError, EdgeChange, EdgeKey, GraphState, NodeChange, NodeState
from graph_vc.state import same_value

M = frozenset({"Concept", "Method"})
E = frozenset({"Content", "Experiment"})


def base_state() -> GraphState:
    return GraphState(
        nodes={
            "method_0016": NodeState(M, {"name": "DLinear", "note": "old"}),
            "method_0004": NodeState(M, {"name": "Transformer forecasting"}),
            "exp_0001": NodeState(E, {"text": "…", "anchors": ["S5.T2"]}),
        },
        edges={
            EdgeKey("exp_0001", "EVALUATES", "method_0016"): {"role": "target"},
            EdgeKey("method_0016", "BROADER", "method_0004"): {},
        },
    )


def test_apply_create_update_delete() -> None:
    cs = Changeset(
        nodes=(
            NodeChange.create("method_0022", M, {"name": "PatchTST"}),
            NodeChange.update("method_0016", M, {"note": "old", "year": None}, {"note": None, "year": 2023}),
        ),
        edges=(
            EdgeChange.create("exp_0001", "EVALUATES", "method_0022", {"role": "baseline"}),
            EdgeChange.update("exp_0001", "EVALUATES", "method_0016", {"role": "target"}, {"role": "baseline"}),
            EdgeChange.delete("method_0016", "BROADER", "method_0004"),
        ),
    )
    after = base_state().apply(cs)
    assert after.nodes["method_0016"].props == {"name": "DLinear", "year": 2023}
    assert after.nodes["method_0022"] == NodeState(M, {"name": "PatchTST"})
    assert after.edges[EdgeKey("exp_0001", "EVALUATES", "method_0016")] == {"role": "baseline"}
    assert EdgeKey("method_0016", "BROADER", "method_0004") not in after.edges


def test_inverse_restores_previous_state() -> None:
    state = base_state()
    cs = Changeset(
        nodes=(
            NodeChange.update("method_0016", M, {"note": "old"}, {"note": "new"}, labels_after={"Concept", "Task"}),
            NodeChange.delete("method_0004", M, {"name": "Transformer forecasting"}),
        ),
        edges=(EdgeChange.delete("method_0016", "BROADER", "method_0004"),),
    )
    after = state.apply(cs)
    assert after.nodes["method_0016"].labels == {"Concept", "Task"}
    assert after.apply(cs.invert()) == state


def test_failed_apply_leaves_state_unchanged() -> None:
    state = base_state()
    snapshot = GraphState(dict(state.nodes), dict(state.edges))
    cs = Changeset(nodes=(NodeChange.update("method_0016", M, {"note": "stale"}, {"note": "new"}),))
    with pytest.raises(ConflictError):
        state.apply(cs)
    assert state == snapshot


@pytest.mark.parametrize(
    ("changeset", "reason"),
    [
        (Changeset(nodes=(NodeChange.create("method_0016", M, {}),)), "node already exists"),
        (Changeset(nodes=(NodeChange.update("method_9999", M, {"a": 1}, {"a": 2}),)), "node does not exist"),
        (Changeset(nodes=(NodeChange.update("method_0016", E, {"note": "old"}, {"note": "x"}),)), "labels differ"),
        (
            Changeset(nodes=(NodeChange.update("method_0016", M, {"note": "stale"}, {"note": "x"}),)),
            "property note differs",
        ),
        (
            Changeset(nodes=(NodeChange.update("method_0016", M, {"year": 2020}, {"year": 2021}),)),
            "property year differs",
        ),
        (
            Changeset(
                nodes=(NodeChange.delete("method_0016", M, {"name": "DLinear"}),),
                edges=(
                    EdgeChange.delete("exp_0001", "EVALUATES", "method_0016", {"role": "target"}),
                    EdgeChange.delete("method_0016", "BROADER", "method_0004"),
                ),
            ),
            "properties differ",
        ),
        (
            Changeset(nodes=(NodeChange.delete("method_0004", M, {"name": "Transformer forecasting"}),)),
            "relationships not deleted in this changeset",
        ),
        (Changeset(edges=(EdgeChange.create("exp_0001", "EVALUATES", "method_0016"),)), "relationship already exists"),
        (
            Changeset(edges=(EdgeChange.create("exp_0001", "USES", "dataset_0002"),)),
            "endpoint dataset_0002 does not exist",
        ),
        (Changeset(edges=(EdgeChange.delete("exp_0001", "USES", "method_0016"),)), "relationship does not exist"),
        (Changeset(edges=(EdgeChange.delete("exp_0001", "EVALUATES", "method_0016"),)), "properties differ"),
        (
            Changeset(edges=(EdgeChange.update("exp_0001", "EVALUATES", "method_0016", {"role": "x"}, {"role": "y"}),)),
            "property role differs",
        ),
    ],
)
def test_conflicts(changeset: Changeset, reason: str) -> None:
    with pytest.raises(ConflictError) as err:
        base_state().apply(changeset)
    assert [c.reason for c in err.value.conflicts] == [reason]


def test_all_conflicts_are_reported_together() -> None:
    cs = Changeset(
        nodes=(
            NodeChange.create("method_0016", M, {}),
            NodeChange.update("exp_0001", E, {"text": "stale"}, {"text": "x"}),
        )
    )
    with pytest.raises(ConflictError) as err:
        base_state().apply(cs)
    assert {c.target for c in err.value.conflicts} == {"method_0016", "exp_0001"}


def test_same_value_distinguishes_bool_from_int() -> None:
    assert not same_value(True, 1)
    assert not same_value([1], [True])
    assert same_value([1, 2], [1, 2])
    assert same_value(None, None)
    assert not same_value(None, 0)
