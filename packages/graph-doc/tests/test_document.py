"""graph-doc 语法层：解析、字段分类、YAML 标量规则与文档内检查。示例取自 commit.md §6。"""

from __future__ import annotations

import pytest

from graph_doc import DocEdge, DocError, from_data, is_temp, load, parse

READ_VIEW = """
graph-doc: v0.1
meta:
  query: {op: Traverse, start: [claim_0004]}
  coverage: {returned: 3, truncated: false, snapshot: commit_0007}
  bindings:
    - [claim_0004, SUPPORTED_BY, exp_0001]

nodes:
  exp_0001:
    kind: Experiment
    anchors: [S5.T2, A3.T9]
    text: 在九个数据集上比较 DLinear …
    FROM:
      - {to: paper_0001, locators: ["5.2 Comparison::198:240"], _material: material_1ec346c934e6}
    EVALUATES:
      - {to: method_0016, role: target}
      - {to: method_0005, role: baseline}

  obs_0002:
    kind: Observation
    _formed_by: claude
    _formed_at: 2026-10-04T15:30:00Z
    text: 两文在 ETTh1 上的 96 步结果可比 …
    ABOUT: [exp_0001, art_0003]

  art_0003:
    _op: Check
    _title: DLinear 与 PatchTST 在 ETTh1 上的可比性
    _USED:
      - {to: exp_0001}
      - {to: paper_0001, locators: ["5.1 Experimental Settings::160:172"]}
"""

NEW_PAPER = """
graph-doc: v0.1
by: claude
confirm:
  $patchtst: {distinct_from: [method_0004]}

nodes:
  $paper:
    kind: Paper
    name: "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers"
    identifiers: ["arxiv:2211.14730"]
    year: 2023
    material: papers/2023-PatchTST/paper.md
    CITES:
      - to: paper_0001
        description: 表 3 中 DLinear 的结果引自该文
        source_refs: ["$paper::4.1 Long-term Time Series Forecasting::210:212"]

  $patchtst:
    kind: Method
    name: PatchTST
    aliases: [PatchTST/64, PatchTST/42]
    BROADER: [method_0004]

  $timesnet:
    kind: Method
    name: TimesNet
    stub: true

  $exp-t3:
    kind: Experiment
    FROM:
      - {to: $paper, locators: ["4.1 Long-term Time Series Forecasting::200:240"]}
    EVALUATES:
      - {to: $patchtst, role: target}
      - {to: method_0016, role: baseline}
      - {to: $timesnet, role: baseline}

  paper_0003:
    stub: null
    note: null

  dataset_0009:
    kind: Benchmark
    PART_OF: []

  obs_0002: null
"""


def test_read_view_separates_fields_by_spelling() -> None:
    doc = parse(READ_VIEW)
    assert doc.version == "v0.1"
    assert doc.by is None
    assert doc.meta["coverage"]["snapshot"] == "commit_0007"

    exp = doc.nodes["exp_0001"]
    assert exp.props == {"kind": "Experiment", "anchors": ["S5.T2", "A3.T9"], "text": "在九个数据集上比较 DLinear …"}
    assert set(exp.rels) == {"FROM", "EVALUATES"}
    assert exp.rels["FROM"] == [
        DocEdge("paper_0001", {"locators": ["5.2 Comparison::198:240"]}, {"_material": "material_1ec346c934e6"})
    ]
    assert [(e.to, e.props) for e in exp.rels["EVALUATES"]] == [
        ("method_0016", {"role": "target"}),
        ("method_0005", {"role": "baseline"}),
    ]

    obs = doc.nodes["obs_0002"]
    assert obs.readonly == {"_formed_by": "claude", "_formed_at": "2026-10-04T15:30:00Z"}
    assert obs.rels["ABOUT"] == [DocEdge("exp_0001"), DocEdge("art_0003")]

    art = doc.nodes["art_0003"]
    assert art.props == {} and art.rels == {}
    assert art.readonly["_USED"][1] == {"to": "paper_0001", "locators": ["5.1 Experimental Settings::160:172"]}


def test_write_document_with_new_updated_and_deleted_nodes() -> None:
    doc = parse(NEW_PAPER)
    assert doc.by == "claude"
    assert doc.confirm == {"$patchtst": {"distinct_from": ["method_0004"]}}
    assert doc.temp_refs() == ["$paper", "$patchtst", "$timesnet", "$exp-t3"]
    assert doc.deleted() == ["obs_0002"]
    assert is_temp("$paper") and not is_temp("paper_0003")

    assert doc.nodes["$paper"].props["year"] == 2023
    assert doc.nodes["$paper"].rels["CITES"][0].props["source_refs"] == [
        "$paper::4.1 Long-term Time Series Forecasting::210:212"
    ]
    assert doc.nodes["$timesnet"].props["stub"] is True
    assert doc.nodes["paper_0003"].props == {"stub": None, "note": None}
    assert doc.nodes["dataset_0009"].rels == {"PART_OF": []}
    assert [e.to for e in doc.nodes["$exp-t3"].rels["EVALUATES"]] == ["$patchtst", "method_0016", "$timesnet"]


def test_scalars_follow_the_yaml_core_schema() -> None:
    data = load(
        """
        at: 2026-10-04T15:30:00Z
        date: 2026-10-04
        yes_word: yes
        on_word: on
        clock: 12:30
        padded: 012
        int: -7
        float: 1.5e3
        dot: .5
        flag: true
        Flag: False
        nothing: null
        tilde: ~
        empty:
        inf: .inf
        """
    )
    assert data == {
        "at": "2026-10-04T15:30:00Z",
        "date": "2026-10-04",
        "yes_word": "yes",
        "on_word": "on",
        "clock": "12:30",
        "padded": 12,
        "int": -7,
        "float": 1500.0,
        "dot": 0.5,
        "flag": True,
        "Flag": False,
        "nothing": None,
        "tilde": None,
        "empty": None,
        "inf": ".inf",
    }
    assert isinstance(data["padded"], int) and isinstance(data["flag"], bool)


def test_quoted_scalars_stay_strings() -> None:
    assert load('a: "true"\nb: "12"\nc: "null"') == {"a": "true", "b": "12", "c": "null"}


@pytest.mark.parametrize(
    "text",
    [
        "graph-doc: v0.1\nnodes:\n  method_0016: {name: a}\n  method_0016: {name: b}\n",
        "graph-doc: v0.1\nnodes:\n  method_0016:\n    name: a\n    name: b\n",
    ],
)
def test_duplicate_keys_are_rejected(text: str) -> None:
    with pytest.raises(DocError) as err:
        parse(text)
    assert "duplicate key" in err.value.problems[0]


def test_invalid_yaml_is_reported() -> None:
    with pytest.raises(DocError) as err:
        parse("graph-doc: v0.1\nnodes: [unclosed\n")
    assert err.value.problems[0].startswith("invalid YAML")


def base(**nodes: object) -> dict[str, object]:
    return {"graph-doc": "v0.1", "by": "claude", "nodes": nodes}


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ([], "must be a mapping"),
        ({"nodes": {}}, "graph-doc: the format version is required"),
        ({"graph-doc": "v9"}, "unsupported version"),
        ({"graph-doc": "v0.1", "edges": []}, "edges: unknown top-level key"),
        ({"graph-doc": "v0.1", "by": ""}, "by: must be a non-empty string"),
        ({"graph-doc": "v0.1", "nodes": []}, "nodes: must be a mapping"),
        ({"graph-doc": "v0.1", "confirm": "yes"}, "confirm: must be a mapping"),
        (base(**{"bad ref": {}}), "neither an id nor a $ reference"),
        (base(**{"$": {}}), "neither an id nor a $ reference"),
        (base(method_0016="DLinear"), "a node must be a mapping"),
        (base(**{"$new": None}), "cannot be deleted"),
        (base(method_0016={"Kind": "Method"}), "field names are lowercase"),
        (base(method_0016={"camelCase": 1}), "field names are lowercase"),
        (base(method_0016={"id": "method_0017"}), "identity is its key"),
        (base(method_0016={"meta": {"a": 1}}), "scalar or a list of scalars"),
        (base(method_0016={"tags": [1, "a"]}), "one scalar type"),
        (base(method_0016={"tags": [True, 1]}), "one scalar type"),
        (base(method_0016={"tags": ["a", None]}), "one scalar type"),
        (base(method_0016={"score": float("nan")}), "scalar or a list of scalars"),
        (base(method_0016={"BROADER": None}), "write [] to remove all"),
        (base(method_0016={"BROADER": "method_0004"}), "must be a list"),
        (base(method_0016={"BROADER": ["method_0004", {"to": "method_0004"}]}), "appears more than once"),
        (base(method_0016={"BROADER": [{"role": "x"}]}), ".to: required"),
        (base(method_0016={"BROADER": [{"to": 3}]}), "neither an id nor a $ reference"),
        (base(method_0016={"BROADER": [{"to": "method_0004", "PART_OF": []}]}), "cannot have relationships"),
        (base(method_0016={"BROADER": [{"to": "method_0004", "w": {"x": 1}}]}), "scalar or a list"),
        (base(method_0016={"BROADER": [["method_0004"]]}), "a reference or a mapping"),
        (base(method_0016={"BROADER": ["$missing"]}), "$missing is not defined"),
        (base(method_0016={"BROADER": ["method_0004"]}, method_0004=None), "deleted in this document"),
    ],
)
def test_rejects(data: object, fragment: str) -> None:
    with pytest.raises(DocError) as err:
        from_data(data)
    assert any(fragment in p for p in err.value.problems), err.value.problems


def test_reports_every_problem_with_its_location() -> None:
    with pytest.raises(DocError) as err:
        from_data(base(method_0016={"Kind": "Method", "BROADER": ["$missing"]}, **{"$x": None}))
    assert sorted(err.value.problems) == sorted(
        [
            "nodes.method_0016.Kind: field names are lowercase (property), UPPERCASE (relationship), "
            "or start with _ (read-only)",
            "nodes.$x: a temporary reference names a new node and cannot be deleted",
            "nodes.method_0016.BROADER[0]: temporary reference $missing is not defined under nodes",
        ]
    )


def test_edge_props_may_be_cleared_and_readonly_fields_are_kept() -> None:
    doc = from_data(
        base(exp_0001={"EVALUATES": [{"to": "method_0016", "role": None, "_material": {"any": ["value"]}}]})
    )
    assert doc.nodes["exp_0001"].rels["EVALUATES"] == [
        DocEdge("method_0016", {"role": None}, {"_material": {"any": ["value"]}})
    ]


def test_empty_document() -> None:
    doc = parse("graph-doc: v0.1\n")
    assert doc.nodes == {} and doc.confirm == {} and doc.meta == {}
