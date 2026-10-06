"""Agent 算子的写入：文档、USED 边与提交，幂等，记录引用，以及读取侧看到的 Artifact。

模块内的测试按顺序共享写入的 Artifact：art_0001 是 Extract，art_0002 是引用其记录的 Filter。
"""

from __future__ import annotations

from conftest import AT, EXTRACT, KEYS, MATERIAL, SOURCE, call, commit_doc, write

from e09.artifact.document import data_of, header_of
from e09.model.schema import ARTIFACT, kind_of
from e09.operators.db.read_evidence import read_evidence
from e09.operators.db.search import search
from e09.operators.db.traverse import traverse
from e09.query.view import dump, render
from e09.store import Store


def test_extract_writes_a_document_used_edges_and_a_commit(store: Store) -> None:
    head = store.graph.head()
    out = write(store, EXTRACT)
    assert out["status"] == "created" and out["artifact"] == "art_0001"
    unused = {"rule": "unused-input", "where": "inputs[0]", "msg": "exp_0001 is not referenced in params or payload"}
    assert out["warnings"] == [unused]  # 列入了实验，但记录里没有引用它

    path = out["document"]["path"]
    assert path.startswith("artifacts/") and path.endswith(".md")
    text = (store.material_root / path).read_text(encoding="utf-8")
    header = header_of(text)
    material = store.query("MATCH (m:Material)-[:MATERIAL_OF]->(:Paper) RETURN m.id AS id")[0]["id"]
    assert header["title"] == "DLinear MSE on ETTh1 and Weather"
    assert header["nodes_used"][-1] == f"{material}::5.2 Comparison::10:12"  # 来源引用统一写成材料 id
    assert [row["key"] for row in data_of(text)["rows"]] == KEYS
    assert "| method_0003-dataset_0001-96 | [method_0003] | [dataset_0001] | 96 | 0.375 | — |" in out["render"]

    record = store.graph.history()[-1]
    assert record.parent == head and record.source == "operator:Extract" and record.author == "claude"
    used = store.query(
        "MATCH (:Artifact {id: 'art_0001'})-[r:USED]->(t) RETURN t.id AS t, properties(r) AS p ORDER BY t"
    )
    assert {r["t"]: r["p"] for r in used} == {
        "dataset_0001": {},
        "dataset_0002": {},
        "exp_0001": {},
        "method_0003": {},
        "paper_0001": {"material_ref": material, "locators": ["5.2 Comparison::10:12"]},
    }
    node = store.query("MATCH (a:Artifact {id: 'art_0001'}) RETURN properties(a) AS p")[0]["p"]
    assert node["op"] == "Extract" and node["formed_at"] == AT and node["session"] == "s-test"


def test_the_same_call_is_a_retry(store: Store) -> None:
    head = store.graph.head()
    again = write(store, {**EXTRACT, "session": "another"})  # 会话不在幂等键中
    assert again["status"] == "existing" and again["artifact"] == "art_0001" and again["commit"] is None
    assert store.graph.head() == head
    assert again["render"].startswith("| key |")


def test_records_of_an_artifact_can_be_used(store: Store) -> None:
    a, b = (f"art_0001#{k}" for k in KEYS)
    out = write(
        store,
        call(
            "Filter",
            [a, b, SOURCE],
            {"items": {"etth1": a, "weather": b}, "condition": {"id": "lt-0.2", "text": "MSE is below 0.2"}},
            {
                "judgments": [
                    {"key": "etth1", "value": "F", "basis": [a]},
                    {"key": "weather", "value": "U", "reason": "The horizon of this run is not stated.", "basis": b},
                ]
            },
        ),
    )
    assert out["artifact"] == "art_0002"
    edge = store.query("MATCH (:Artifact {id: 'art_0002'})-[r:USED]->({id: 'art_0001'}) RETURN r.role AS role")
    assert edge[0]["role"] == sorted(["etth1", "weather", *KEYS])  # 记录键与项键
    assert "## U (1)\n\n- `weather` [art_0001#method_0003-dataset_0002-96]" in out["render"]
    assert out["warnings"] == [
        {"rule": "unused-input", "where": "inputs[2]", "msg": f"{SOURCE} is not referenced in params or payload"}
    ]


def test_search_finds_artifacts_only_when_asked(store: Store) -> None:
    by_op = search(store, "Artifact", where={"op": "Filter"})
    assert by_op["meta"]["items"] == ["art_0002"]
    by_text = search(store, "Artifact", "DLinear MSE Weather")
    assert by_text["meta"]["items"][0] == "art_0001"
    used = search(store, "Artifact", where={"used": "paper_0001"})
    assert used["meta"]["items"] == ["art_0001", "art_0002"]
    assert search(store, "Content", "DLinear MSE Weather")["meta"]["items"] == ["exp_0001"]


def test_artifact_views_and_used_traversal(store: Store) -> None:
    out = traverse(store, ["paper_0001"], [{"rel": "USED", "dir": "in", "kinds": ["Artifact"]}])
    assert out["meta"]["items"] == ["art_0001", "art_0002"]
    view = out["nodes"]["art_0002"]
    assert view["_op"] == "Filter" and view["_stale"] == [] and view["_document"].startswith("artifacts/")
    assert view["_params"]["condition"]["id"] == "lt-0.2"
    assert {"to": "art_0001", "role": sorted(["etth1", "weather", *KEYS])} in view["_USED"]
    assert set(view) <= {k for k in view if k.startswith("_")}  # Artifact 的字段全部只读

    chain = traverse(store, ["art_0002"], [{"rel": "USED", "kinds": ["Artifact"]}, {"rel": "USED"}])
    assert ["art_0002", "-USED->", "art_0001", "-USED->", "method_0003"] in chain["meta"]["bindings"]
    by_role = traverse(store, ["art_0002"], [{"rel": "USED", "edge": {"role": "etth1"}}])
    assert by_role["meta"]["items"] == ["art_0001"]


def test_artifact_documents_are_materials(store: Store) -> None:
    out = read_evidence(store, ["art_0001::Extract::1:3"])
    assert out["items"][0]["state"] == "available"
    assert out["items"][0]["text"].startswith("1| ---\n2| title: DLinear MSE")


def test_observation_can_cite_an_artifact(store: Store) -> None:
    doc = """
graph-doc: v0.1
by: claude
nodes:
  $obs:
    kind: Observation
    text: DLinear's MSE on Weather is far lower than on ETTh1 at horizon 96.
    ABOUT: [method_0003, art_0001]
    FROM:
      - {to: art_0001, locators: ["Extract::12:14"]}
"""
    assert commit_doc(store, doc)["status"] == "committed"
    refs = traverse(store, ["obs_0001"])["meta"]["source_refs"]
    assert read_evidence(store, refs)["items"][0]["state"] == "available"


def test_views_with_artifacts_round_trip_as_noop(store: Store) -> None:
    state = store.graph.snapshot()
    ids = sorted(i for i, n in state.nodes.items() if kind_of(n.labels) or ARTIFACT in n.labels)
    assert {"art_0001", "art_0002", "obs_0001"} <= set(ids)
    view = render(state, ids, {})
    view["by"] = "claude"
    assert commit_doc(store, dump(view), commit=False)["status"] == "noop"
    assert MATERIAL in dump(view)
