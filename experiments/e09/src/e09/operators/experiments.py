"""Experiments：按被测对象、数据集与指标取得实验报告（intents_decompose.md §4.1、§6.1；I3.2）。

    experiments(subjects, *, dataset={ref, include: [], depth: 1}?, metric?, scope="global",
                budget=50, continuation=None) -> AccessResult

只做结构匹配，不走语义通道：引用参数只接收已确认的 id（名称先经 Resolve）。返回的每个实验都满足
"库中存在这些参与关联"，不带相关度分数。找"设计相似的实验"属于 Search 的发现，不在这里（2026-10-03）。

- subjects：任一被测对象命中即可（EVALUATES 指向其中之一）。
- dataset：默认严格匹配 `USES {role: evaluation_data}` 指向 ref。include 可选 parts / versions，沿反向
  PART_OF / VERSION_OF 展开到 depth，展开命中的实验带 witness（路径）。
- metric：严格匹配 MEASURED_BY。
- scope："global"，或论文 id 列表（只取 FROM 这些论文的实验）。判断同源时由调用方组合：
  对 origin_from 指向的论文再调一次 experiments(subjects={m}, scope=[论文])。
- 诊断（与结果共用 subjects、metric、scope，只回传数量与引用）：
  - expandable：不在结果中，但 evaluation_data 落在 depth 内可展开、本次未选的数据集上；
  - role_missing：不在结果中，USES 指向已选数据集但没有 role。
- 首版入库为报告级（extraction_principles.md §4）：每项 granularity=report，数值留在原文，
  按 source_refs 由 ReadEvidence 读表。
"""

from ..utils.graph import q

INCLUDE = {"parts": "PART_OF", "versions": "VERSION_OF"}   # include 取值 -> 展开的关系类型
MAX_DEPTH = 3
CONTENT_PROPS = ("anchor", "section", "lines", "text", "setting", "note", "condition_basis")


def _existing(refs) -> dict:
    """ref -> 主 Label 与 kind；库里没有的 ref 不在结果中。"""
    rows = q("""UNWIND $refs AS ref MATCH (n {id: ref}) WHERE n:Entity OR n:Concept
                RETURN n.id AS ref, labels(n) AS labels""", refs=list(refs))
    return {r["ref"]: r["labels"] for r in rows}


def _expand(d: str, include: set[str], depth: int) -> tuple[dict, dict]:
    """沿反向 PART_OF / VERSION_OF 枚举 depth 内的数据集。返回 (selected, extra)：数据集 id -> witness 路径。

    selected 含 d 本身（路径为空）与 include 指定边类型可达的资源；extra 是两类边可达、但本次没有选的资源。
    同一资源有多条路径时取最短的一条作 witness；可变长匹配不重复走同一条边，环在此截断。
    """
    rows = q(f"""MATCH path = (x:Entity)-[:PART_OF|VERSION_OF*1..{depth}]->(:Entity {{id: $d}})
                 RETURN x.id AS id, [n IN nodes(path) | n.id] AS nodes, [r IN relationships(path) | type(r)] AS types
                 ORDER BY length(path), id""", d=d)
    allowed = {INCLUDE[i] for i in include}
    selected, extra = {d: []}, {}
    for r in rows:
        if r["id"] in selected or r["id"] in extra:
            continue
        witness = [x for pair in zip(r["nodes"], r["types"]) for x in pair] + [r["nodes"][-1]]
        (selected if set(r["types"]) <= allowed else extra)[r["id"]] = witness
    return selected, extra


def _assemble(ids: list[str]) -> dict:
    """实验视图：内容属性、条件、来源、任务与三类参与；参与按被测对象 / 数据 / 指标分组并保留边上属性。"""
    rows = q("""UNWIND $ids AS id
                MATCH (e:Content:Experiment {id: id})-[f:FROM]->(p:Entity:Paper)
                OPTIONAL MATCH (mat:Material {id: f.material_ref})
                OPTIONAL MATCH (e)-[:ON_TASK]->(t)
                CALL (e) {
                  MATCH (e)-[r:EVALUATES]->(x)
                  RETURN collect({ref: x.id, name: x.name, labels: labels(x), role: r.role, variants: r.variants,
                                  origin: r.origin, origin_basis: r.origin_basis, origin_from: r.origin_from}) AS evaluates }
                CALL (e) {
                  OPTIONAL MATCH (e)-[u:USES]->(x)
                  RETURN collect({ref: x.id, name: x.name, role: u.role, version: u.version}) AS uses }
                CALL (e) {
                  OPTIONAL MATCH (e)-[:MEASURED_BY]->(x)
                  RETURN collect({ref: x.id, name: x.name, direction: x.direction}) AS metrics }
                RETURN e.id AS ref, properties(e) AS props, p.id AS paper, p.name AS paper_name, f.material_ref AS material,
                       f.locators AS locators, mat.path AS path, t.id AS task, t.name AS task_name,
                       evaluates, uses, metrics""", ids=ids)
    out = {}
    for r in rows:
        props = r["props"]
        evaluates = [{k: v for k, v in x.items() if k != "labels" and v is not None}
                     | {"kind": next(l for l in x["labels"] if l not in ("Entity", "Concept"))}
                     for x in sorted(r["evaluates"], key=lambda x: (x["role"] != "target", x["name"]))]
        out[r["ref"]] = {
            "ref": r["ref"], "exp_key": props["exp_key"], "kind": "Experiment", "granularity": "report",
            "paper": {"ref": r["paper"], "name": r["paper_name"]},
            "task": {"ref": r["task"], "name": r["task_name"]} if r["task"] else None,
            **{k: props.get(k) for k in CONTENT_PROPS},
            "conditions": {k.removeprefix("cond_"): v for k, v in sorted(props.items()) if k.startswith("cond_")},
            "participants": {
                "evaluates": evaluates,
                "uses": sorted(({k: v for k, v in x.items() if v is not None} for x in r["uses"] if x["ref"]),
                               key=lambda x: x["name"]),
                "measured_by": sorted(({k: v for k, v in x.items() if v is not None} for x in r["metrics"] if x["ref"]),
                                      key=lambda x: x["name"]),
            },
            "source": {"material_ref": r["material"], "path": r["path"], "locators": r["locators"]},
        }
    return out


def experiments(subjects, *, dataset: dict | str | None = None, metric: str | None = None,
                scope: str | list[str] = "global", budget: int = 50, continuation: int | None = None) -> dict:
    subjects = sorted(set(subjects))
    if not subjects:
        raise ValueError("subjects 至少给一个已确认的引用")
    if isinstance(dataset, str):
        dataset = {"ref": dataset}
    dataset = dict(dataset) if dataset else None
    include, depth = set(), 1
    if dataset:
        if unknown := set(dataset) - {"ref", "include", "depth"}:
            raise ValueError(f"dataset 只接受 ref、include、depth，不接受 {sorted(unknown)}")
        include = set(dataset.get("include") or [])
        if bad := include - set(INCLUDE):
            raise ValueError(f"include 只能取 {sorted(INCLUDE)}，不能取 {sorted(bad)}")
        depth = dataset.get("depth", 1)
        if not (isinstance(depth, int) and 1 <= depth <= MAX_DEPTH):
            raise ValueError(f"depth 应为 1–{MAX_DEPTH} 的整数")
    papers = None if scope == "global" else sorted(set(scope))
    if papers is not None and not papers:
        raise ValueError('scope 为 "global" 或非空的论文 id 列表')
    if budget < 1:
        raise ValueError("budget 至少为 1")
    offset = continuation or 0

    # 引用参数：库里没有的记 missing（missing_in=store），不静默忽略
    asked = {**{s: "subjects" for s in subjects}, **({dataset["ref"]: "dataset"} if dataset else {}),
             **({metric: "metric"} if metric else {}), **{p: "scope" for p in papers or []}}
    found = _existing(asked)
    missing = [{"ref": ref, "param": param, "missing_in": "store"} for ref, param in asked.items() if ref not in found]
    wrong = [{"ref": ref, "param": param, "expected": want, "labels": found[ref]}
             for ref, param in asked.items() if ref in found
             for want in [{"dataset": "Entity", "metric": "Metric", "scope": "Paper"}.get(param)]
             if want and want not in found[ref]]
    if wrong:
        raise ValueError(f"引用的类型不符：{wrong}")

    selected, extra = _expand(dataset["ref"], include, depth) if dataset and dataset["ref"] in found else ({}, {})
    blocked = not any(s in found for s in subjects) or (dataset and dataset["ref"] not in found) \
        or (metric and metric not in found) or (papers is not None and not any(p in found for p in papers))
    rows = [] if blocked else q(f"""
        MATCH (e:Content:Experiment)-[t:EVALUATES]->(m) WHERE m.id IN $subjects
        {"MATCH (e)-[:MEASURED_BY]->(:Concept {id: $metric})" if metric else ""}
        {"MATCH (e)-[:FROM]->(p:Entity:Paper) WHERE p.id IN $papers" if papers is not None else ""}
        WITH DISTINCT e
        OPTIONAL MATCH (e)-[u:USES]->(d:Entity)
        RETURN e.id AS ref, e.exp_key AS exp_key, collect({{ref: d.id, role: u.role}}) AS data
        ORDER BY exp_key""", subjects=subjects, metric=metric, papers=papers)

    # 分桶：matched 进结果；其余只在诊断中报数量与引用
    matched, expandable, role_missing = [], [], []
    for r in rows:
        data = [d for d in r["data"] if d["ref"]]
        if not dataset:
            matched.append(r)
            if any(d["role"] is None for d in data):
                role_missing.append(r)
        elif any(d["role"] == "evaluation_data" and d["ref"] in selected for d in data):
            matched.append(r)
        elif any(d["role"] is None and d["ref"] in selected for d in data):
            role_missing.append(r)
        elif any(d["role"] == "evaluation_data" and d["ref"] in extra for d in data):
            expandable.append(r)

    page = matched[offset:offset + budget]
    views = _assemble([r["ref"] for r in page])
    items, bindings, witnesses, source_refs = [], [], [], []
    for r in page:
        v = views[r["ref"]]
        items.append(v)
        hit_data = [d for d in v["participants"]["uses"]
                    if d.get("role") == "evaluation_data" and d["ref"] in selected] if dataset else []
        bindings.append({
            "experiment": v["ref"],
            "subjects": [x for x in v["participants"]["evaluates"] if x["ref"] in subjects],
            "datasets": [{"ref": d["ref"], "name": d["name"], "via": "expanded" if selected[d["ref"]] else "exact"}
                         for d in hit_data],
            "metric": metric,
        })
        witnesses += [{"experiment": v["ref"], "dataset": d["ref"], "path": selected[d["ref"]]}
                      for d in hit_data if selected[d["ref"]]]
        source_refs += [f"{v['source']['material_ref']}::{loc}" for loc in v["source"]["locators"]]

    truncated = offset + budget < len(matched)
    snapshot = q("MATCH (b:IngestBatch) RETURN b.id AS id ORDER BY id DESC LIMIT 1")
    # 结果是结构事实（value=T）；引用缺失时 resolution=missing，空结果不等于"原文没有报告"（见 coverage 与批次记录）
    states = {"access": "matched" if items else "empty",
              "resolution": "missing" if missing else "resolved", "value": "T", "origin": "rule"}
    if missing:
        states["missing_in"] = "store"
    return {
        "items": items, "bindings": bindings, "witnesses": witnesses, "source_refs": source_refs,
        "match_trace": {"datasets": {"selected": selected, "extra": extra}} if dataset else {},
        "missing": missing, "states": states,
        "coverage": {"call": "experiments", "subjects": subjects, "dataset": dataset and {**dataset, "include": sorted(include), "depth": depth},
                     "metric": metric, "scope": scope, "budget": budget, "offset": offset,
                     "matched": len(matched), "returned": len(items), "truncated": truncated,
                     "snapshot": snapshot[0]["id"] if snapshot else None},
        "continuation": offset + budget if truncated else None,
        "diagnostics": {
            "expandable": {"count": len(expandable), "refs": [r["exp_key"] for r in expandable],
                           "datasets": sorted(extra)},
            "role_missing": {"count": len(role_missing), "refs": [r["exp_key"] for r in role_missing],
                             "missing_in": "store"},
        },
    }
