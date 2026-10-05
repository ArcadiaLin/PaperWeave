"""变更集的构造、校验、序列化与逆向。不需要数据库。"""

from __future__ import annotations

import json

import pytest

from graph_vc import Changeset, ChangesetError, EdgeChange, FileRef, NodeChange

SHA = "0" * 64


def sample() -> Changeset:
    return Changeset(
        nodes=(
            NodeChange.create("method_0022", ["Concept", "Method"], {"name": "PatchTST", "definition": "…"}),
            NodeChange.update("method_0016", ["Concept", "Method"], {"note": "old"}, {"note": None}),
            NodeChange.update("dataset_0009", ["Entity", "Dataset"], {}, {}, labels_after=["Entity", "Benchmark"]),
            NodeChange.delete("obs_0002", ["Content", "Observation"], {"text": "…", "formed_by": "claude"}),
        ),
        edges=(
            EdgeChange.create("method_0022", "BROADER", "method_0004"),
            EdgeChange.update("exp_0001", "EVALUATES", "method_0016", {"role": "baseline"}, {"role": "target"}),
            EdgeChange.delete("obs_0002", "ABOUT", "exp_0001"),
        ),
        files=(FileRef("papers/2023-PatchTST/paper.md", SHA),),
    )


def test_sample_is_valid() -> None:
    sample().validate()


def test_ops_follow_before_and_after() -> None:
    cs = sample()
    assert [n.op for n in cs.nodes] == ["create", "update", "update", "delete"]
    assert [e.op for e in cs.edges] == ["create", "update", "delete"]


def test_round_trip_through_json() -> None:
    cs = sample()
    data = json.loads(json.dumps(cs.to_dict()))
    assert Changeset.from_dict(data) == cs


def test_serialized_shape() -> None:
    data = sample().to_dict()
    assert data["nodes"][1] == {
        "op": "update",
        "id": "method_0016",
        "labels": ["Concept", "Method"],
        "props": {"note": {"before": "old", "after": None}},
    }
    assert data["nodes"][2]["labels"] == {"before": ["Dataset", "Entity"], "after": ["Benchmark", "Entity"]}
    assert data["edges"][0] == {
        "op": "create",
        "from": "method_0022",
        "type": "BROADER",
        "to": "method_0004",
        "after": {},
    }


def test_invert_is_an_involution_and_swaps_ops() -> None:
    cs = sample()
    inverse = cs.invert()
    assert [n.op for n in inverse.nodes] == ["delete", "update", "update", "create"]
    assert inverse.files == ()
    assert inverse.invert() == Changeset(nodes=cs.nodes, edges=cs.edges)


def test_empty_changeset_is_falsy() -> None:
    assert not Changeset()
    assert not Changeset(files=(FileRef("a", SHA),))


@pytest.mark.parametrize(
    ("changeset", "fragment"),
    [
        (Changeset(nodes=(NodeChange.create("x", ["Commit"], {}),)), "reserved"),
        (Changeset(nodes=(NodeChange.create("x", ["Bad-Label"], {}),)), "invalid label"),
        (Changeset(nodes=(NodeChange.create("x", [], {}),)), "at least one label"),
        (Changeset(nodes=(NodeChange.create("x", ["A"], {"id": "y"}),)), "'id' is the node identity"),
        (Changeset(nodes=(NodeChange.create("x", ["A"], {"p": None}),)), "omit absent properties"),
        (Changeset(nodes=(NodeChange.create("x", ["A"], {"p": {"nested": 1}}),)), "cannot store"),
        (Changeset(nodes=(NodeChange.create("x", ["A"], {"p": [1, "a"]}),)), "cannot store"),
        (Changeset(nodes=(NodeChange.create("x", ["A"], {"p": float("nan")}),)), "cannot store"),
        (Changeset(nodes=(NodeChange.update("x", ["A"], {"p": 1}, {"p": 1}),)), "do not change"),
        (Changeset(nodes=(NodeChange.update("x", ["A"], {"p": 1}, {"q": 1}),)), "same properties"),
        (Changeset(nodes=(NodeChange.update("x", ["A"], {}, {}),)), "changes nothing"),
        (
            Changeset(nodes=(NodeChange.create("x", ["A"], {}), NodeChange.create("x", ["A"], {}))),
            "more than once",
        ),
        (Changeset(edges=(EdgeChange.create("a", "TOUCHED", "b"),)), "reserved"),
        (Changeset(edges=(EdgeChange.create("a", "bad type", "b"),)), "invalid relationship type"),
        (
            Changeset(nodes=(NodeChange.delete("a", ["A"], {}),), edges=(EdgeChange.create("a", "R", "b"),)),
            "deleted in the same changeset",
        ),
        (
            Changeset(nodes=(NodeChange.create("a", ["A"], {}),), edges=(EdgeChange.delete("a", "R", "b"),)),
            "created in the same changeset",
        ),
        (Changeset(files=(FileRef("../escape", SHA),)), "relative"),
        (Changeset(files=(FileRef("a", "xyz"),)), "sha256"),
    ],
)
def test_validation_rejects(changeset: Changeset, fragment: str) -> None:
    with pytest.raises(ChangesetError) as err:
        changeset.validate()
    assert any(fragment in p for p in err.value.problems), err.value.problems


def test_vocabulary_restricts_labels_and_types() -> None:
    cs = Changeset(nodes=(NodeChange.create("x", ["A", "B"], {}),), edges=(EdgeChange.create("x", "R", "y"),))
    cs.validate(node_labels=frozenset({"A", "B"}), rel_types=frozenset({"R"}))
    with pytest.raises(ChangesetError):
        cs.validate(node_labels=frozenset({"A"}))
    with pytest.raises(ChangesetError):
        cs.validate(rel_types=frozenset({"S"}))


def test_unversioned_properties_cannot_be_written() -> None:
    unversioned = frozenset({"embedding"})
    Changeset(nodes=(NodeChange.create("x", ["A"], {"name": "x"}),)).validate(unversioned_props=unversioned)
    for cs in (
        Changeset(nodes=(NodeChange.create("x", ["A"], {"embedding": [0.1]}),)),
        Changeset(nodes=(NodeChange.update("x", ["A"], {"embedding": None}, {"embedding": [0.1]}),)),
        Changeset(edges=(EdgeChange.delete("x", "R", "y", {"embedding": [0.1]}),)),
    ):
        with pytest.raises(ChangesetError) as err:
            cs.validate(unversioned_props=unversioned)
        assert any("not versioned" in p for p in err.value.problems)


def test_empty_list_and_bool_lists_are_storable() -> None:
    Changeset(nodes=(NodeChange.create("x", ["A"], {"a": [], "b": [True, False], "c": 2.5}),)).validate()


def test_from_dict_rejects_malformed() -> None:
    with pytest.raises(ChangesetError):
        Changeset.from_dict({"nodes": [{"op": "create"}]})
    with pytest.raises(ChangesetError):
        Changeset.from_dict({"nodes": [{"op": "merge", "id": "x"}]})
