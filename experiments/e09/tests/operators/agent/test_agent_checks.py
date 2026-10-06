"""共同校验与各算子的 schema：不通过时整次拒绝，什么也不写入。

另含 Summarize、Generate、Check、Verify、MatrixConstruct 的写入。
"""

from __future__ import annotations

import copy

import pytest
from conftest import EXTRACT, KEYS, SOURCE, call, errors, write

from e09.artifact.document import data_of, header_of
from e09.store import Store

FILTER = call(
    "Filter",
    ["method_0003", "method_0002"],
    {"items": {"a": "method_0003", "b": "method_0002"}, "condition": {"id": "linear", "text": "Is it a linear model?"}},
    {
        "judgments": [
            {"key": "a", "value": "T", "basis": "method_0003"},
            {"key": "b", "value": "F", "basis": ["method_0002"]},
        ]
    },
)
J, R = "payload.judgments", "payload.rows"


def changed(request: dict, path: str, value: object) -> dict:
    """把 ``request`` 中 ``path``（点分）处的值换成 ``value``；``value`` 为 ``...`` 时删掉该键。"""
    out = copy.deepcopy(request)
    *parents, last = path.split(".")
    node = out
    for key in parents:
        node = node[int(key)] if isinstance(node, list) else node[key]
    if value is ...:
        del node[last]
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return out


@pytest.mark.parametrize(
    ("request_", "expected"),
    [
        (changed(FILTER, "op", "Rank"), [("format", "op")]),  # 已取消的算子
        (changed(FILTER, "abs", ...), [("format", "abs")]),
        (changed(FILTER, "inputs", []), [("format", "inputs")]),
        (changed(FILTER, "inputs", ["method_0003", "method_0003"]), [("format", "inputs")]),
        (changed(FILTER, "inputs", ["method_0003", "method_0002", "method_0099"]), [("reference", "inputs[2]")]),
        (changed(FILTER, "inputs", ["method_0003"]), [("reference", "params.items.b"), ("reference", f"{J}[1].basis")]),
        (changed(FILTER, "payload.judgments.1.basis", ...), [("judgment", "payload.judgments[1].basis")]),
        (changed(FILTER, "payload.judgments.1", {"key": "b", "value": "U"}), [("judgment", f"{J}[1].reason")]),
        (changed(FILTER, "payload.judgments.1.value", "maybe"), [("judgment", "payload.judgments[1].value")]),
        (changed(FILTER, "payload.judgments.1.key", "a"), [("judgment", f"{J}[1]"), ("judgment", J)]),
        (changed(FILTER, "payload.judgments", FILTER["payload"]["judgments"][:1]), [("judgment", J)]),
        (changed(FILTER, "params.items.b", "material_000000000000"), [("reference", "params.items.b")]),
        (changed(EXTRACT, "inputs", [*EXTRACT["inputs"], "paper_0001::5.2::59:61"]), [("reference", "inputs[5]")]),
        (changed(EXTRACT, "inputs", [*EXTRACT["inputs"], "art_0099#x"]), [("reference", "inputs[5]")]),
        (changed(EXTRACT, "inputs", [*EXTRACT["inputs"], "paper_0001::5.2"]), [("reference", "inputs[5]")]),
        (changed(EXTRACT, "payload.rows.1.horizon", "96"), [("schema", "payload.rows[1].horizon")]),
        (changed(EXTRACT, "payload.rows.1.mse", ...), [("schema", "payload.rows[1].mse")]),
        (changed(EXTRACT, "payload.rows.1.dataset", "dataset_0001"), [("schema", "payload.rows[1]")]),  # 键重复
        (changed(EXTRACT, "payload.rows.1.source", "paper_0001::5.2::30:31"), [("reference", f"{R}[1].source")]),
        (changed(EXTRACT, "payload.rows", []), [("schema", "payload.note")]),
        (changed(EXTRACT, "params.schema.fields.split", "float"), [("schema", "params.schema.fields.split")]),
    ],
)
def test_rejected_calls_write_nothing(store: Store, request_: dict, expected: list[tuple[str, str]]) -> None:
    assert errors(store, request_) == expected


def test_a_source_reference_may_name_the_material_or_its_paper(store: Store) -> None:
    material = store.query("MATCH (m:Material)-[:MATERIAL_OF]->(:Paper) RETURN m.id AS id")[0]["id"]
    request = changed(EXTRACT, "inputs.4", SOURCE.replace("paper_0001", material))
    assert write(store, request)["status"] == "created"  # 内容中仍写论文 id


def test_an_empty_extract_records_what_was_read(store: Store) -> None:
    request = changed(EXTRACT, "payload", {"rows": [], "note": "Table 3 reports only MAE for these settings."})
    out = write(store, request)
    text = (store.material_root / out["document"]["path"]).read_text(encoding="utf-8")
    assert data_of(text)["rows"] == [] and "only MAE" in out["render"]
    assert [w["where"] for w in out["warnings"]] == [f"inputs[{i}]" for i in range(5)]


def test_summarize_needs_a_reference_in_every_paragraph(store: Store) -> None:
    text = "## DLinear\n\nDLinear decomposes the series [method_0003].\n\nIt is evaluated on ETTh1 [exp_0001]."
    request = call("Summarize", ["method_0003", "exp_0001"], {"focus": "mechanism"}, {"text": text})
    assert write(store, request)["status"] == "created"  # 只有标题的段落不计
    bare = changed(request, "payload.text", text + "\n\nIt is simple.")
    assert errors(store, bare) == [("citation", "payload.text")]
    stray = changed(request, "payload.text", text + " See also [method_0002].")
    assert errors(store, stray) == [("reference", "payload.text")]


def test_generate_reports_cited_paragraphs(store: Store) -> None:
    text = "DLinear is a strong baseline [exp_0001].\n\nTry it first.\n\nSee [the paper](https://arxiv.org)."
    out = write(store, call("Generate", ["exp_0001"], {"purpose": "answer"}, {"text": text}))
    assert out["stats"] == {"cited_paragraphs": "1/3"}  # Markdown 链接不是引用


def test_check_needs_one_judgment_per_pair_and_dimension(store: Store) -> None:
    a, b = (f"art_0001#{k}" for k in KEYS)
    params = {
        "items": {"x": a, "y": b, "z": "exp_0001"},
        "pairs": [["x", "y"], ["z", "x"]],
        "dimensions": [{"id": "horizon", "question": "Same horizon?"}, {"id": "metric", "question": "Same metric?"}],
    }
    judgments = [
        {"pair": ["y", "x"], "dimension": "horizon", "value": "T", "basis": [a, b]},  # 对不计顺序
        {"pair": ["x", "y"], "dimension": "metric", "value": "T", "basis": [a, b]},
        {"pair": ["x", "z"], "dimension": "horizon", "value": "U", "reason": "The experiment spans horizons."},
        {"pair": ["z", "x"], "dimension": "metric", "value": "F", "basis": ["exp_0001"], "reason": "MAE vs MSE."},
    ]
    request = call("Check", [a, b, "exp_0001"], params, {"judgments": judgments})
    out = write(store, request)
    text = (store.material_root / out["document"]["path"]).read_text(encoding="utf-8")
    assert data_of(text)["pairs"] == [["x", "y"], ["z", "x"]]
    assert "| z ~ x | U | F |" in out["render"]
    assert errors(store, changed(request, "payload.judgments", judgments[:3])) == [("judgment", "payload.judgments")]
    twice = changed(request, "payload.judgments", [*judgments, judgments[0]])
    assert errors(store, twice) == [("judgment", "payload.judgments[4]")]


def test_verify_records_the_claim_as_a_role(store: Store) -> None:
    request = call(
        "Verify",
        ["exp_0001", SOURCE],
        {"claim": "exp_0001"},
        {"value": "U", "conditions": "Only horizon 96.", "basis": [SOURCE], "reason": "No variance is reported."},
    )
    out = write(store, request)
    assert out["render"].startswith("**Claim:** [exp_0001]\n\n**Value:** U")
    roles = store.query(
        "MATCH (a:Artifact {id: $id})-[r:USED]->({id: 'exp_0001'}) RETURN r.role AS role", id=out["artifact"]
    )
    assert roles[0]["role"] == ["claim"]
    text = (store.material_root / out["document"]["path"]).read_text(encoding="utf-8")
    assert header_of(text)["title"] == "Verify [exp_0001]"


def test_matrix_needs_one_cell_per_row_and_column(store: Store) -> None:
    a, b = (f"art_0001#{k}" for k in KEYS)
    params = {
        "rows": {"dlinear": "method_0003", "tf": "method_0002"},
        "columns": {"etth1": "dataset_0001", "weather": "dataset_0002", "avg": {"text": "Average"}},
        "cell": {"type": "number", "question": "MSE at horizon 96"},
    }
    cells = [
        {"row": "dlinear", "col": "etth1", "value": 0.375, "basis": a},
        {"row": "dlinear", "col": "weather", "value": 0.176, "basis": [b]},
        {"row": "dlinear", "col": "avg", "value": None},  # basis 与 note 都可省略
        {"row": "tf", "col": "etth1", "value": None, "note": "Not reported."},
        {"row": "tf", "col": "weather", "value": None},
        {"row": "tf", "col": "avg", "value": None},
    ]
    inputs = ["method_0003", "method_0002", "dataset_0001", "dataset_0002", a, b]
    request = call("MatrixConstruct", inputs, params, {"cells": cells})
    out = write(store, request)
    assert out["warnings"] == []
    assert "| dlinear | 0.375 [art_0001#method_0003-dataset_0001-96] | 0.176 [" in out["render"]
    assert "| tf | — | — | — |" in out["render"] and "- `tf~etth1`: Not reported." in out["render"]
    text = (store.material_root / out["document"]["path"]).read_text(encoding="utf-8")
    assert [(c["row"], c["col"]) for c in data_of(text)["cells"]][:2] == [("dlinear", "etth1"), ("dlinear", "weather")]
    assert header_of(text)["title"] == "Matrix: MSE at horizon 96"
    roles = store.query(
        "MATCH (:Artifact {id: $id})-[r:USED]->(t) RETURN t.id AS t, r.role AS role ORDER BY t", id=out["artifact"]
    )
    assert {r["t"]: r["role"] for r in roles} == {
        "art_0001": KEYS,
        "dataset_0001": ["etth1"],
        "dataset_0002": ["weather"],
        "method_0002": ["tf"],
        "method_0003": ["dlinear"],
    }

    cited = f"{out['artifact']}#dlinear~weather"  # 格子可以被引用
    answer = call("Generate", [cited], {"purpose": "answer"}, {"text": f"DLinear reaches 0.176 [{cited}]."})
    assert write(store, answer)["status"] == "created"

    at = "payload.cells"
    assert errors(store, changed(request, at, cells[:5])) == [("schema", at)]
    assert errors(store, changed(request, at, [*cells, cells[0]])) == [("schema", f"{at}[6]")]
    assert errors(store, changed(request, f"{at}.1.col", "mae")) == [("schema", f"{at}[1].col"), ("schema", at)]
    assert errors(store, changed(request, f"{at}.1.value", "0.176")) == [("schema", f"{at}[1].value")]
    assert errors(store, changed(request, f"{at}.1.basis", "exp_0001")) == [("reference", f"{at}[1].basis")]
    assert errors(store, changed(request, "params.rows.tf", "method_0001")) == [("reference", "params.rows.tf")]
    assert errors(store, changed(request, "params.cell.type", "float")) == [("schema", "params.cell.type")]
