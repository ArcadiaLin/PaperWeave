"""I3 参考答案的自检：问题与答案对得上，数值确实出现在原文对应的表里，比较与关系的判断与数值自洽。

数值核对经库中实验的锚点读取材料（需先 make ingest）；只核对"这个字符串是表中的一个单元格"，
不核对它落在哪一行哪一列——那由参考答案的作者负责，人工抽查。
"""

from pathlib import Path

import pytest
import yaml

from e09.operators.read_evidence import read_evidence
from e09.utils.graph import driver, q

I3 = Path(__file__).resolve().parents[1] / "i3"
QUESTIONS = yaml.safe_load((I3 / "questions.yml").read_text(encoding="utf-8"))
REFERENCE = yaml.safe_load((I3 / "reference.yml").read_text(encoding="utf-8"))
REFS = {x["id"]: x for x in REFERENCE["questions"]}
ARXIV = {"dlinear": "arxiv:2205.13504", "patchtst": "arxiv:2211.14730"}
EXPECTATIONS = {"same_source", "independent_same_conditions", "not_comparable", "unknown"}
CONDITIONS = {"dataset", "metric", "split", "T", "L", "channels", "training"}


def test_questions_and_reference_align():
    assert QUESTIONS["version"] == REFERENCE["version"]
    assert [x["id"] for x in QUESTIONS["questions"]] == list(REFS)
    for qid, ref in REFS.items():
        ids = {s["id"] for s in ref["series"]}
        assert len(ids) == len(ref["series"]), qid
        for s in ref["series"]:
            assert s["paper"] in QUESTIONS["papers"] and s["metric"] in ("MSE", "MAE"), (qid, s["id"])
            assert all(isinstance(v, str) for v in s["values"].values()), (qid, s["id"], "数值按原文字符串保存")
        for c in ref["comparisons"]:
            assert {c["a"], c["b"]} <= ids and set(c["conditions"]) == CONDITIONS, (qid, c)
        for r in ref["relations"]:
            b = r["b"] if isinstance(r["b"], list) else [r["b"]]
            assert {r["a"], *b} <= ids and r["expectation"] in EXPECTATIONS, (qid, r)
            assert set(r.get("conditions", {})) <= CONDITIONS, (qid, r)
        assert ref["key_points"] and ref["must_not"], qid


def test_judgments_agree_with_values():
    for qid, ref in REFS.items():
        series = {s["id"]: s["values"] for s in ref["series"]}
        for c in ref["comparisons"]:
            a, b = series[c["a"]], series[c["b"]]
            assert set(c["lower"]) == set(a) == set(b), (qid, c)
            for t, who in c["lower"].items():
                x, y = float(a[t]), float(b[t])
                assert who == ("tie" if x == y else "a" if x < y else "b"), (qid, c["a"], t)
        for r in ref["relations"]:
            if isinstance(r["b"], list):   # 出处论文中无一相符
                assert r["observation"] == "no_match_in_source"
                assert all(series[r["a"]] != series[b] for b in r["b"]), (qid, r)
                continue
            a, b = series[r["a"]], series[r["b"]]
            shared = sorted(set(a) & set(b), key=int)
            assert shared, (qid, r)
            mismatched = [t for t in shared if float(a[t]) != float(b[t])]
            assert r["mismatched"] == mismatched, (qid, r["a"], r["b"], mismatched)
            want = "consistent" if not mismatched else (
                "inconsistent" if len(mismatched) == len(shared) else "partially_consistent")
            assert r["observation"] == want, (qid, r["a"], r["b"])


@pytest.fixture(scope="module")
def tables():
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"neo4j-e09 不可用：{e}")
    papers = {k: q("MATCH (p:Paper) WHERE $i IN p.identifiers RETURN p.id AS id", i=i)[0]["id"] for k, i in ARXIV.items()}
    rows = q("""MATCH (e:Experiment)-[f:FROM]->(p:Paper)
                RETURN p.id AS paper, e.anchor AS anchor, f.material_ref + '::' + f.locators[0] AS src""")
    texts = {r["src"]: i["text"] for r, i in zip(rows, read_evidence([r["src"] for r in rows])["items"])}
    return {(k, r["anchor"]): texts[r["src"]] for k, pid in papers.items() for r in rows if r["paper"] == pid}


def test_values_appear_in_their_tables(tables):
    for qid, ref in REFS.items():
        for s in ref["series"]:
            text = tables[(s["paper"], s["anchor"])]
            assert s["table"] == "Table " + s["anchor"].split(".T")[1], (qid, s["id"])
            cells = {c.strip() for line in text.splitlines() if line.startswith("|") for c in line.split("|")}
            for t, v in s["values"].items():
                assert v in cells, (qid, s["id"], t, v)
