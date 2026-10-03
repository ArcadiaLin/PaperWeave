"""Experiments 与 ReadEvidence 在 neo4j-e09 现有库上的检验（需先 make ingest）。

期望值不复用算子的查询：由正式表单（forms/*.yml）独立推出每个实验的被测对象、数据集、指标与论文，
引用经 Resolve 的精确阶段（不开语义通道）解析为 id，再与算子结果比较。
"""

import itertools

import pytest
import yaml

from e09.config import FORMS
from e09.operators.experiments import experiments
from e09.operators.read_evidence import read_evidence
from e09.operators.resolve import resolve
from e09.utils.graph import driver, q

try:
    driver.verify_connectivity()
except Exception as e:   # 库没起：整组跳过，不当作失败
    pytest.skip(f"neo4j-e09 不可用：{e}", allow_module_level=True)


def exact(query, kind) -> str:
    r = resolve(query, kind=kind, channels=set())
    assert r["status"] == "resolved", (query, kind, r["status"])
    return r["refs"][0]


@pytest.fixture(scope="module")
def oracle() -> dict:
    """exp_key -> {paper, subjects, data, metrics}，由表单推出。"""
    out = {}
    for path in sorted(FORMS.glob("*.yml")):
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        ids = {}
        for ref, spec in (form.get("refs") or {}).items():
            ids[ref] = spec["id"] if "id" in spec else exact(spec["mention"], spec["kind"])
        for ref, obj in (form.get("objects") or {}).items():
            ids[ref] = exact(obj["properties"]["name"], obj["labels"][1])
        paper = exact({"identifier": form["paper"]["properties"]["identifiers"][0]}, "Paper")
        for exp in form["experiments"]:
            out[f"{paper}::{exp['anchor']}"] = {
                "paper": paper, "subjects": {ids[p["subject"]] for p in exp["participants"]},
                "data": {ids[d] for d in exp["data"]}, "metrics": {ids[m] for m in exp["metrics"]}}
    assert len(out) == q("MATCH (e:Experiment) RETURN count(e) AS n")[0]["n"], "表单与库中的实验数不一致，先 make ingest"
    return out


@pytest.fixture(scope="module")
def ref():
    names = {"DLinear": "Method", "PatchTST": "Method", "FEDformer": "Method", "Autoformer": "Method",
             "ETT": "Dataset", "ETTh1": "Dataset", "ETTh2": "Dataset", "ETTm1": "Dataset", "ETTm2": "Dataset",
             "Electricity": "Dataset", "Traffic": "Dataset", "ILI": "Dataset", "MSE": "Metric", "MAE": "Metric"}
    return {n: exact(n, k) for n, k in names.items()}


def expect(oracle, subjects, dataset=None, metric=None, papers=None) -> list[str]:
    return sorted(k for k, x in oracle.items()
                  if x["subjects"] & set(subjects) and (dataset is None or dataset in x["data"])
                  and (metric is None or metric in x["metrics"]) and (papers is None or x["paper"] in papers))


def keys(result) -> list[str]:
    return [i["exp_key"] for i in result["items"]]


def test_strict_matching_agrees_with_forms(oracle, ref):
    papers = sorted({x["paper"] for x in oracle.values()})
    for subjects, dataset, metric, scope in itertools.product(
            [{ref["DLinear"], ref["PatchTST"]}, {ref["FEDformer"]}, {ref["Autoformer"]}],
            [None, ref["ETTh1"], ref["Electricity"], ref["ILI"]],
            [None, ref["MSE"]],
            ["global", *[[p] for p in papers]]):
        r = experiments(subjects, dataset=dataset, metric=metric, scope=scope, budget=100)
        assert keys(r) == expect(oracle, subjects, dataset, metric, None if scope == "global" else scope), \
            (subjects, dataset, metric, scope)
        assert all(i["granularity"] == "report" for i in r["items"])
        for b in r["bindings"]:   # 绑定只含本次请求的被测对象
            assert b["subjects"] and {s["ref"] for s in b["subjects"]} <= subjects


def test_part_of_expansion_and_diagnostics(oracle, ref):
    subjects = {ref["DLinear"], ref["PatchTST"]}
    parts = [ref[n] for n in ("ETTh1", "ETTh2", "ETTm1", "ETTm2")]
    union = sorted(set().union(*(expect(oracle, subjects, d) for d in parts)))
    strict = experiments(subjects, dataset=ref["ETT"], budget=100)
    assert keys(strict) == [] and strict["states"]["access"] == "empty"   # 没有实验直接用 ETT
    assert sorted(strict["diagnostics"]["expandable"]["refs"]) == union
    assert sorted(strict["diagnostics"]["expandable"]["datasets"]) == sorted(parts)
    expanded = experiments(subjects, dataset={"ref": ref["ETT"], "include": ["parts"]}, budget=100)
    assert keys(expanded) == union and expanded["diagnostics"]["expandable"]["count"] == 0
    assert expanded["witnesses"] and all(w["path"][-2:] == ["PART_OF", ref["ETT"]] for w in expanded["witnesses"])
    assert all(d["via"] == "expanded" for b in expanded["bindings"] for d in b["datasets"])


def test_pagination_is_lossless(ref):
    subjects = {ref["DLinear"], ref["PatchTST"]}
    full, pages, cont = keys(experiments(subjects, budget=100)), [], None
    while True:
        r = experiments(subjects, budget=4, continuation=cont)
        pages += keys(r)
        assert r["coverage"]["matched"] == len(full)
        if (cont := r["continuation"]) is None:
            break
    assert pages == full


def test_same_source_by_composition():
    """转引的参与：对 origin_from 指向的论文再调一次 Experiments。被引论文入库了才有候选，只是桩节点则为空。"""
    rows = q("""MATCH (e:Experiment)-[r:EVALUATES {origin: 'cited'}]->(m)
                MATCH (p:Paper {id: r.origin_from})
                RETURN e.exp_key AS report, m.id AS m, p.id AS paper, coalesce(p.stub, false) AS stub""")
    assert rows
    for x in rows:
        r = experiments({x["m"]}, scope=[x["paper"]], budget=100)
        if x["stub"]:
            assert keys(r) == [], x
        else:
            assert keys(r) and all(k.startswith(x["paper"] + "::") for k in keys(r)), x
    dlinear_t3 = next(x for x in rows if x["report"].endswith("S4.T3") and x["paper"] == "paper_0001"
                      and x["m"] == exact("DLinear", "Method"))
    assert len(keys(experiments({dlinear_t3["m"]}, scope=["paper_0001"]))) == 7


def test_missing_and_wrong_refs(ref):
    r = experiments({ref["PatchTST"], "method_9999"}, dataset=ref["ETTh1"])
    assert r["missing"] == [{"ref": "method_9999", "param": "subjects", "missing_in": "store"}]
    assert r["states"]["resolution"] == "missing" and r["items"]
    assert experiments({"method_9999"})["states"]["access"] == "empty"
    with pytest.raises(ValueError):
        experiments({ref["PatchTST"]}, dataset=ref["MSE"])   # 数据集参数给了指标
    with pytest.raises(ValueError):
        experiments({ref["PatchTST"]}, dataset={"ref": ref["ETT"], "include": ["children"]})


def test_read_evidence_reads_every_anchor(ref):
    r = experiments({x["id"] for x in q("MATCH (:Experiment)-[:EVALUATES]->(m) RETURN DISTINCT m.id AS id")}, budget=100)
    assert r["coverage"]["matched"] == q("MATCH (e:Experiment) RETURN count(e) AS n")[0]["n"]
    ev = read_evidence(r["source_refs"])
    assert ev["missing"] == [], ev["missing"]
    by_ref = {i["source_ref"]: i for i in ev["items"]}
    for item in r["items"]:   # 每个实验的表从主锚点开始
        src = f"{item['source']['material_ref']}::{item['source']['locators'][0]}"
        assert f'id="{item["anchor"]}"' in by_ref[src]["text"].splitlines()[0], src


def test_read_evidence_failures():
    material = q("MATCH (m:Material) RETURN m.id AS id LIMIT 1")[0]["id"]
    ev = read_evidence(["no-locator", "material_000000000000::S::1:2", f"{material}::S::1:99999999"])
    assert [i["material"] for i in ev["items"]] == ["missing", "missing", "error"]
    assert ev["states"]["access"] == "empty" and len(ev["missing"]) == 3
