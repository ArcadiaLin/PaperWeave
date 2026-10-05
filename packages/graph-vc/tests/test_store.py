"""VersionedGraph 在真实 Neo4j 上的行为与不变式。

这些测试会清空所连的库，因此只在设置了 ``GRAPH_VC_TEST_NEO4J_URI`` 时运行，并且要求开始时库为空。
启动测试库：``docker compose -f infra/neo4j-test/docker-compose.yml up -d``。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graph_vc import (
    Changeset,
    ChangesetError,
    ConflictError,
    EdgeChange,
    EdgeKey,
    FileIntegrityError,
    FileRef,
    GraphState,
    NodeChange,
    VersionedGraph,
)

URI = os.environ.get("GRAPH_VC_TEST_NEO4J_URI")
AUTH = (os.environ.get("GRAPH_VC_TEST_NEO4J_USER", "neo4j"), os.environ.get("GRAPH_VC_TEST_NEO4J_PASSWORD", "password"))

pytestmark = pytest.mark.skipif(URI is None, reason="GRAPH_VC_TEST_NEO4J_URI is not set")

M = ["Concept", "Method"]
E = ["Content", "Experiment"]


@pytest.fixture(scope="module")
def driver() -> Iterator[object]:
    from neo4j import GraphDatabase

    drv = GraphDatabase.driver(URI, auth=AUTH)
    count = drv.execute_query("MATCH (n) RETURN count(n) AS c").records[0]["c"]
    if count:
        drv.close()
        pytest.skip(f"refusing to run: test database at {URI} is not empty ({count} nodes)")
    yield drv
    drv.close()


@pytest.fixture
def graph(driver, tmp_path: Path) -> Iterator[VersionedGraph]:
    clock = iter(datetime(2026, 10, 5, 12, 0, s, tzinfo=UTC) for s in range(60))
    g = VersionedGraph(driver, file_root=tmp_path, clock=lambda: next(clock))
    g.setup()
    yield g
    driver.execute_query("MATCH (n) DETACH DELETE n")


def seed(graph: VersionedGraph):
    return graph.commit(
        Changeset(
            nodes=(
                NodeChange.create("method_0016", M, {"name": "DLinear", "note": "old"}),
                NodeChange.create("method_0004", M, {"name": "Transformer forecasting"}),
                NodeChange.create("exp_0001", E, {"text": "…", "anchors": ["S5.T2", "A3.T9"]}),
            ),
            edges=(
                EdgeChange.create("exp_0001", "EVALUATES", "method_0016", {"role": "target"}),
                EdgeChange.create("method_0016", "BROADER", "method_0004"),
            ),
        ),
        author="claude",
        message="seed",
        source="test",
    )


def edit() -> Changeset:
    return Changeset(
        nodes=(
            NodeChange.create("method_0022", M, {"name": "PatchTST"}),
            NodeChange.update("method_0016", M, {"note": "old"}, {"note": None}, labels_after=["Concept", "Task"]),
            NodeChange.delete("method_0004", M, {"name": "Transformer forecasting"}),
        ),
        edges=(
            EdgeChange.delete("method_0016", "BROADER", "method_0004"),
            EdgeChange.update("exp_0001", "EVALUATES", "method_0016", {"role": "target"}, {"role": "baseline"}),
            EdgeChange.create("exp_0001", "EVALUATES", "method_0022", {"role": "target"}),
        ),
    )


def test_commit_matches_in_memory_apply(graph: VersionedGraph) -> None:
    seed(graph)
    before = graph.snapshot()
    graph.commit(edit(), author="claude")
    assert graph.snapshot() == before.apply(edit())


def test_commit_record_and_chain(graph: VersionedGraph) -> None:
    first = seed(graph)
    second = graph.commit(
        edit(), author="claude", message="edit", base=first.id, input="graph-doc: v0.1\n", meta={"rounds": 2}
    )
    assert (first.id, first.parent, first.seq) == ("commit_000001", None, 1)
    assert (second.parent, second.seq) == (first.id, 2)
    assert graph.head() == second.id
    assert [c.id for c in graph.history()] == [first.id, second.id]

    stored = graph.get_commit(second.id)
    assert stored == second
    assert stored.removed == ("method_0004",)
    assert stored.touched == ("exp_0001", "method_0016", "method_0022")

    touched = graph._driver.execute_query(
        "MATCH (:Commit {id: $id})-[t:TOUCHED]->(n) RETURN n.id AS id, t.op AS op ORDER BY id", id=second.id
    ).records
    assert [(r["id"], r["op"]) for r in touched] == [
        ("exp_0001", "edge"),
        ("method_0016", "update"),
        ("method_0022", "create"),
    ]


def test_conflict_rolls_back_everything(graph: VersionedGraph) -> None:
    seed(graph)
    before, head = graph.snapshot(), graph.head()
    stale = Changeset(
        nodes=(
            NodeChange.create("method_0030", M, {"name": "should not appear"}),
            NodeChange.update("method_0016", M, {"note": "stale"}, {"note": "x"}),
        )
    )
    with pytest.raises(ConflictError) as err:
        graph.commit(stale, author="claude")
    assert [c.target for c in err.value.conflicts] == ["method_0016"]
    assert graph.snapshot() == before
    assert graph.head() == head
    assert len(graph.history()) == 1


def test_incomplete_delete_is_rejected(graph: VersionedGraph) -> None:
    seed(graph)
    with pytest.raises(ConflictError) as err:
        graph.commit(
            Changeset(nodes=(NodeChange.delete("method_0004", M, {"name": "Transformer forecasting"}),)),
            author="claude",
        )
    assert err.value.conflicts[0].reason == "relationships not deleted in this changeset"


def test_version_records_are_untouchable(graph: VersionedGraph) -> None:
    first = seed(graph)
    with pytest.raises(ChangesetError):
        graph.commit(Changeset(nodes=(NodeChange.update(first.id, ["Content"], {"a": 1}, {"a": 2}),)), author="x")


def test_revert_restores_state(graph: VersionedGraph) -> None:
    seed(graph)
    before = graph.snapshot()
    edited = graph.commit(edit(), author="claude")
    reverted = graph.revert(edited.id, author="claude")
    assert graph.snapshot() == before
    assert reverted.source == f"revert:{edited.id}"
    assert len(graph.history()) == 3


def test_replay_reproduces_state(graph: VersionedGraph, driver) -> None:
    seed(graph)
    graph.commit(edit(), author="claude")
    graph.revert(graph.head(), author="claude")
    graph.commit(edit(), author="claude")
    final = graph.snapshot()
    history = graph.history()

    driver.execute_query("MATCH (n) DETACH DELETE n")
    graph.setup()
    assert graph.snapshot() == GraphState()
    for record in history:
        graph.commit(record.changeset, author=record.author, message=record.message, source=record.source)
    assert graph.snapshot() == final


def test_every_commit_is_reversible(graph: VersionedGraph) -> None:
    seed(graph)
    graph.commit(edit(), author="claude")
    states = [GraphState()]
    for record in graph.history():
        states.append(states[-1].apply(record.changeset))
    assert states[-1] == graph.snapshot()
    for record, before, after in zip(graph.history(), states[:-1], states[1:], strict=True):
        assert after.apply(record.changeset.invert()) == before


def test_file_integrity(graph: VersionedGraph, tmp_path: Path) -> None:
    (tmp_path / "papers").mkdir()
    doc = tmp_path / "papers/paper.md"
    doc.write_text("# PatchTST\n", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    material = NodeChange.create("material_0001", ["Material"], {"path": "papers/paper.md", "content_hash": digest})

    with pytest.raises(FileIntegrityError):
        graph.commit(Changeset(nodes=(material,), files=(FileRef("papers/missing.md", digest),)), author="x")
    with pytest.raises(FileIntegrityError):
        graph.commit(Changeset(nodes=(material,), files=(FileRef("papers/paper.md", "f" * 64),)), author="x")
    assert graph.head() is None

    record = graph.commit(Changeset(nodes=(material,), files=(FileRef("papers/paper.md", digest),)), author="x")
    assert graph.get_commit(record.id).changeset.files == (FileRef("papers/paper.md", digest),)


def test_allocate_ids_continues_from_existing_and_never_reuses(graph: VersionedGraph) -> None:
    seed(graph)
    assert graph.allocate_ids("method", 2) == ["method_0017", "method_0018"]
    graph.commit(Changeset(nodes=(NodeChange.create("method_0017", M, {"name": "x"}),)), author="x")
    graph.commit(Changeset(nodes=(NodeChange.delete("method_0017", M, {"name": "x"}),)), author="x")
    assert graph.allocate_ids("method") == ["method_0019"]
    with pytest.raises(ValueError):
        graph.allocate_ids("commit")


def test_snapshot_excludes_version_records(graph: VersionedGraph) -> None:
    seed(graph)
    state = graph.snapshot()
    assert set(state.nodes) == {"method_0016", "method_0004", "exp_0001"}
    assert set(state.edges) == {
        EdgeKey("exp_0001", "EVALUATES", "method_0016"),
        EdgeKey("method_0016", "BROADER", "method_0004"),
    }


def test_unversioned_properties_are_ignored(driver) -> None:
    graph = VersionedGraph(driver, unversioned_props=frozenset({"embedding"}))
    graph.setup()
    try:
        seed(graph)
        before = graph.snapshot()
        # 提交之后由上层补算的派生属性
        driver.execute_query("MATCH (n {id: 'method_0004'}) SET n.embedding = [0.1, 0.2]")
        driver.execute_query("MATCH ({id: 'exp_0001'})-[r:EVALUATES]->() SET r.embedding = [0.3]")
        assert graph.snapshot() == before

        with pytest.raises(ChangesetError):
            graph.commit(
                Changeset(nodes=(NodeChange.update("method_0016", M, {"embedding": None}, {"embedding": [1.0]}),)),
                author="x",
            )
        # 改前状态不含派生属性，修改与删除照常通过核对
        graph.commit(edit(), author="claude")
        assert graph.snapshot() == before.apply(edit())
        evaluates = driver.execute_query(
            "MATCH ({id: 'exp_0001'})-[r:EVALUATES]->({id: 'method_0016'}) RETURN r.embedding AS e"
        ).records
        assert evaluates[0]["e"] == [0.3]
    finally:
        driver.execute_query("MATCH (n) DETACH DELETE n")


def test_id_cannot_be_unversioned(driver) -> None:
    with pytest.raises(ValueError):
        VersionedGraph(driver, unversioned_props=frozenset({"id"}))
