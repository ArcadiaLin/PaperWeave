"""目标状态 → 取局部现状 → 求差 → 提交，在真实 Neo4j 上走通。

与 graph-vc 的数据库测试相同：只在设置了 ``GRAPH_VC_TEST_NEO4J_URI`` 时运行，要求开始时库为空，结束后清空。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from graph_doc import Fragment, FragmentNode, diff
from graph_vc import ConflictError, VersionedGraph

URI = os.environ.get("GRAPH_VC_TEST_NEO4J_URI")
AUTH = (os.environ.get("GRAPH_VC_TEST_NEO4J_USER", "neo4j"), os.environ.get("GRAPH_VC_TEST_NEO4J_PASSWORD", "password"))

pytestmark = pytest.mark.skipif(URI is None, reason="GRAPH_VC_TEST_NEO4J_URI is not set")

M = frozenset({"Concept", "Method"})
E = frozenset({"Content", "Experiment"})


@pytest.fixture
def graph() -> Iterator[VersionedGraph]:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(URI, auth=AUTH)
    count = driver.execute_query("MATCH (n) RETURN count(n) AS c").records[0]["c"]
    if count:
        driver.close()
        pytest.skip(f"refusing to run: test database at {URI} is not empty ({count} nodes)")
    g = VersionedGraph(driver)
    g.setup()
    yield g
    driver.execute_query("MATCH (n) DETACH DELETE n")
    driver.close()


def submit(graph: VersionedGraph, fragment: Fragment, **kwargs: object):
    cs = diff(fragment, graph.local_state(fragment.ids()))
    return graph.commit(cs, author="claude", source="test", **kwargs)


def test_create_then_edit_then_delete(graph: VersionedGraph) -> None:
    new = Fragment(
        {
            "$dlinear": FragmentNode(labels=M, props={"name": "DLinear", "note": "old"}, new=True),
            "$tf": FragmentNode(labels=M, props={"name": "Transformer forecasting"}, new=True),
            "$exp": FragmentNode(
                labels=E, props={"text": "…"}, rels={"EVALUATES": {"$dlinear": {"role": "target"}}}, new=True
            ),
        }
    )
    ids = dict(zip(["$dlinear", "$tf"], graph.allocate_ids("method", 2), strict=True)) | {
        "$exp": graph.allocate_ids("exp")[0]
    }
    first = submit(graph, new.rename(ids))
    dlinear, tf, exp = ids["$dlinear"], ids["$tf"], ids["$exp"]

    edit = Fragment(
        {
            dlinear: FragmentNode(props={"note": None}, rels={"BROADER": {tf: {}}}),
            exp: FragmentNode(rels={"EVALUATES": {dlinear: {"role": "baseline"}}}),
        }
    )
    submit(graph, edit, base=first.id)
    state = graph.snapshot()
    assert state.nodes[dlinear].props == {"name": "DLinear"}
    assert {str(k): v for k, v in state.edges.items()} == {
        f"{exp}-[EVALUATES]->{dlinear}": {"role": "baseline"},
        f"{dlinear}-[BROADER]->{tf}": {},
    }
    assert not diff(edit, graph.local_state(edit.ids()))

    submit(graph, Fragment(deletes=frozenset({tf})))
    state = graph.snapshot()
    assert set(state.nodes) == {dlinear, exp}
    assert [str(k) for k in state.edges] == [f"{exp}-[EVALUATES]->{dlinear}"]
    assert len(graph.history()) == 3


def test_stale_read_is_caught_at_commit(graph: VersionedGraph) -> None:
    submit(graph, Fragment({"method_0001": FragmentNode(labels=M, props={"name": "DLinear"}, new=True)}))
    mine = Fragment({"method_0001": FragmentNode(props={"name": "DLinear (mine)"})})
    stale = diff(mine, graph.local_state(mine.ids()))

    submit(graph, Fragment({"method_0001": FragmentNode(props={"name": "DLinear (theirs)"})}))
    with pytest.raises(ConflictError) as err:
        graph.commit(stale, author="claude")
    assert err.value.conflicts[0].reason == "property name differs"
    assert graph.snapshot().nodes["method_0001"].props == {"name": "DLinear (theirs)"}
