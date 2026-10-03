"""Commit 的论文增量：dry_run（只读）→ apply（单事务）→ 写后复核 → 补算向量（docs/designs/v2/commit_contract.md）。

输入是 form.compile_form 的 (delta, issues)。plan 把阻塞项分三类，处理方不同：
- errors：表单自身写错（含 compile 报出的错误），Agent 改表单；
- pending：需要 Agent 做语义判断（引用未唯一命中、语义近邻未列入 rejected、印刷名与称呼不同）；
- conflicts：与库内状态矛盾（键已被占用、撞上桩节点、结果值变了……），由外部决定。
有任何阻塞项时 apply 拒绝整批。

身份规则（§4、§5）：
- 论文按唯一命名空间的标识（arXiv 等）识别；已存在即本批是重跑或补录。
- 新对象的精确键被占用：若由同一篇论文此前注册（NameKey.registered_from），视为重跑命中；
  若占用者是桩节点，提示改用 refs 或 fill；否则为 key-taken。
- Experiment 与 ResultUnit 按自然键 exp_key、row_key 判定新建、不变或冲突；Content 不原地修改。

dry_run 的查询经 `run` 执行：默认是只读会话；apply 在同一写事务里传入事务执行器做复核，
`commit=False` 时整批写入后回滚（演练），库不留改动。语义查重调用 Resolve，走只读会话，看不到未提交的写入。
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...config import NEO4J_DB
from ...utils.domain import DOMAINS
from ...utils.graph import driver, q
from ...utils.ids import IdAllocator
from ...utils.namekey import NORMALIZER, name_key, normalize
from ...utils.schema import FAMILY, NAMESPACES, PREFIX
from ..resolve import resolve

KIND_OF_PREFIX = {p: k for k, p in PREFIX.items()}
STUB_CHANNELS = {"lexical_name"}   # 桩节点只有名称：查重只走 id、alias 与名称词面（commit_contract.md §4）


def family_of(obj_id: str) -> str:
    return FAMILY[KIND_OF_PREFIX[obj_id.rpartition("_")[0]]]


def compact(d: dict) -> dict:
    """去掉值为 None 的键：Neo4j 不存 null 属性，比较前两边同样处理。"""
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class PaperPlan:
    delta: dict
    issues: list
    paper_id: str | None = None                       # 论文已在库中时的 id
    bind: dict = field(default_factory=dict)          # ref -> 已有对象 id（refs、fill 目标、重跑命中的本批对象）
    new_nodes: list = field(default_factory=list)     # 要新建的 ref（含 paper）
    same_nodes: list = field(default_factory=list)
    fills: dict = field(default_factory=dict)         # ref -> {id, props}：只填空字段
    registers: list = field(default_factory=list)     # (ref, 原字符串, kind)：新注册的精确键
    material: dict = field(default_factory=dict)      # {id, path, sha256, exists}
    experiments: list = field(default_factory=list)   # {exp, status: new | same}
    results: Counter = field(default_factory=Counter)  # new / same
    missing_in_form: list = field(default_factory=list)   # 库中有、表单中没有的结果行：只报告
    errors: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)   # 主张 A 的构建成本：解析级别、候选与否定数

    @property
    def blocked(self) -> bool:
        return bool(self.errors or self.pending or self.conflicts)

    @property
    def empty(self) -> bool:
        return not (self.new_nodes or self.fills or self.registers or not self.material.get("exists", True)
                    or any(e["status"] == "new" for e in self.experiments) or self.results["new"])

    def ids(self) -> dict:
        return dict(self.bind) | ({"paper": self.paper_id} if self.paper_id else {})


# ── dry_run ──

def dry_run(delta: dict, issues: list, run=q, semantic: bool = True) -> PaperPlan:
    p = PaperPlan(delta, issues)
    p.errors += [i for i in issues if i["level"] == "error"]
    p.pending += [i for i in issues if i["level"] == "pending"]
    if not delta:
        return p
    nodes = delta["nodes"]

    # 论文：按唯一命名空间的标识识别
    paper = nodes["paper"]
    uniq = [i for i in paper["props"].get("identifiers", []) if NAMESPACES[i.partition(":")[0]]]
    hits = run("MATCH (o:Entity:Paper) WHERE any(i IN o.identifiers WHERE i IN $ids) "
               "RETURN o.id AS id, properties(o) AS props", ids=uniq) if uniq else []
    if len(hits) > 1:
        p.conflicts.append({"where": "paper", "rule": "identifier-multi", "msg": f"标识 {uniq} 命中多篇论文 {[h['id'] for h in hits]}"})
    elif hits:
        p.paper_id = hits[0]["id"]
        _compare_existing(p, "paper", hits[0]["props"], paper["props"])
    source = f"paper:{p.paper_id}" if p.paper_id else None

    # 新对象（含 paper 的名称键）：精确键占用、重跑命中、桩节点冲突、语义查重
    keys = [k for n in nodes.values() for k in n["keys"]]
    held = defaultdict(list)
    for r in run("MATCH (k:NameKey) WHERE k.key IN $keys OPTIONAL MATCH (k)-[:NAMES]->(o) "
                 "RETURN k.key AS key, k.status AS status, k.registered_from AS src, o.id AS id, "
                 "coalesce(o.stub, false) AS stub, properties(o) AS props", keys=keys):
        held[r["key"]].append(r)
    for ref, n in nodes.items():
        where = "paper" if ref == "paper" else f"objects.{ref}"
        own = [h for k in n["keys"] for h in held[k]]
        if ref == "paper" and p.paper_id:   # 论文已在库中：已按标识比较过，只检查标题键没被别的对象占用
            if others := sorted({h["id"] for h in own if h["id"] != p.paper_id}):
                p.conflicts.append({"where": where, "rule": "key-taken", "msg": f"论文标题已注册给 {others}"})
            continue
        if not own:
            p.new_nodes.append(ref)
            if ref != "paper":
                _dedup(p, ref, n, semantic)
            continue
        if any(h["status"] != "active" for h in own):
            p.conflicts.append({"where": where, "rule": "key-ambiguous", "msg": f"称呼的精确键已隔离为 ambiguous：{sorted({h['id'] for h in own})}"})
            continue
        owners = {h["id"]: h for h in own}
        if len(owners) == 1 and source and all(h["src"] == source for h in own):
            oid, h = next(iter(owners.items()))   # 同一论文此前注册：重跑命中
            p.bind[ref] = oid
            _compare_existing(p, where, h["props"], n["props"] | ({"stub": True} if n["stub"] else {}), ref=ref)
        elif any(h["stub"] for h in owners.values()):
            p.conflicts.append({"where": where, "rule": "stub-exists",
                                "msg": f"已有同名桩节点 {sorted(owners)}：改为 refs 引用，或用 fill 补全"})
        else:
            p.conflicts.append({"where": where, "rule": "key-taken", "msg": f"称呼已注册给 {sorted(owners)}"})

    # refs：只走 id 与 alias 两级，唯一命中才绑定
    for ref, spec in delta["refs"].items():
        _bind_ref(p, ref, spec, run, semantic)

    # fill：目标必须是桩节点；只填空字段
    for ref, f in delta["fills"].items():
        _plan_fill(p, ref, f, run)

    # 结果行：绑定后重算行键（不同 ref 可能解析到同一对象）
    ids = p.ids()
    p.material = _plan_material(delta["material"], run)
    domain_slots = sorted(DOMAINS[delta["domain"]]["slots"])
    for exp in delta["experiments"]:
        _plan_experiment(p, exp, ids, domain_slots, run)
    if delta["rels"]:
        p.errors.append({"where": "relationships", "rule": "unsupported",
                         "msg": "论文批次的 Entity / Concept 关系写入尚未实现（单篇深度原则下通常为空）"})
    return p


def _compare_existing(p: PaperPlan, where: str, db: dict, form: dict, ref: str | None = None):
    """已有对象：表单写了、库里为空的字段可以补；库里已有且不同则冲突（改写属于修订，Q2）。"""
    db = {k: v for k, v in db.items() if k not in ("id", "embedding", "embedding_key")}
    changed = {k: (db[k], v) for k, v in form.items() if k in db and db[k] != v}
    if changed:
        p.conflicts.append({"where": where, "rule": "object-changed",
                            "msg": f"与库中已有内容不同：{ {k: (str(a)[:40], str(b)[:40]) for k, (a, b) in changed.items()} }"})
    elif extra := {k: v for k, v in form.items() if k not in db}:
        p.fills[ref or where] = {"id": p.bind.get(ref) or p.paper_id, "props": extra}
    elif ref:
        p.same_nodes.append(ref)


def _dedup(p: PaperPlan, ref: str, n: dict, semantic: bool):
    """新对象的语义查重：近邻须全部列入 rejected，否则待确认。"""
    if not semantic:
        return
    props = n["props"]
    query = {"mention": props["name"]}
    if not n["stub"]:
        query["text"] = props.get("definition") or props.get("description")
    r = resolve(query, kind=n["kind"], mode="write", channels=STUB_CHANNELS if n["stub"] else None)
    cands = [c["id"] for t in r["match_trace"] if t["stage"] == "semantic" for c in t["candidates"]]
    errors = [ch for ch, s in r["coverage"]["channels"].items() if s.startswith("error")]
    p.stats["semantic_candidates"] += len(cands)
    p.stats["rejected"] += len([c for c in cands if c in n["rejected"]])
    if errors:
        p.pending.append({"where": f"objects.{ref}", "rule": "dedup-unprocessed",
                          "msg": f"语义查重通道执行失败 {errors}，查重不完整"})
    if open_ := [c for c in cands if c not in n["rejected"]]:
        names = {r["id"]: r["name"] for r in q("MATCH (o) WHERE o.id IN $ids RETURN o.id AS id, o.name AS name", ids=open_)}
        p.pending.append({"where": f"objects.{ref}", "rule": "dedup",
                          "msg": f"语义近邻未判定，确认不是同一对象后列入 rejected：{[f'{c} {names.get(c)}' for c in open_]}"})


def _bind_ref(p: PaperPlan, ref: str, spec: dict, run, semantic: bool):
    where = f"refs.{ref}"
    if "id" in spec:
        rows = run("MATCH (o {id: $id}) RETURN labels(o) AS labels", id=spec["id"])
        if not rows or spec["kind"] not in rows[0]["labels"]:
            p.conflicts.append({"where": where, "rule": "ref-missing", "msg": f"库中没有 {spec['kind']} {spec['id']}"})
            return
        p.bind[ref] = spec["id"]
        p.stats["ref_id"] += 1
        if spec["register"]:
            key = name_key(spec["printed"], spec["kind"])
            owner = run("MATCH (k:NameKey {key: $k})-[:NAMES]->(o) RETURN o.id AS id", k=key)
            if not owner:
                p.registers.append((ref, spec["printed"], spec["kind"]))
            elif owner[0]["id"] != spec["id"]:
                p.conflicts.append({"where": where, "rule": "key-taken", "msg": f"{spec['printed']!r} 已注册给 {owner[0]['id']}"})
        return
    rows = run("MATCH (k:NameKey {key: $k}) OPTIONAL MATCH (k)-[:NAMES]->(o) "
               "RETURN k.status AS status, collect(o.id) AS ids", k=name_key(spec["mention"], spec["kind"]))
    if rows and rows[0]["status"] == "active" and len(rows[0]["ids"]) == 1:
        p.bind[ref] = rows[0]["ids"][0]
        p.stats["ref_alias"] += 1
        return
    p.stats["ref_unresolved"] += 1
    hint = ""
    if semantic:
        r = resolve(spec["mention"], kind=spec["kind"], mode="read")
        hint = f"；候选 {r['refs'][:3]}（{r['stage']}/{r['status']}）"
    p.pending.append({"where": where, "rule": "ref-unresolved",
                      "msg": f"{spec['mention']!r} 未在 id / alias 级唯一命中{hint}。确认后改写为 {{id: …}}；"
                             f"若它应由先前的批次建立，先提交那一批，不要从语义候选中挑选"})


def _plan_fill(p: PaperPlan, ref: str, f: dict, run):
    where = f"objects.{ref}"
    t = f["target"]
    if "id" in t:
        rows = run("MATCH (o {id: $id}) RETURN o.id AS id, properties(o) AS props", id=t["id"])
    else:
        rows = run("MATCH (k:NameKey {key: $k, status: 'active'})-[:NAMES]->(o) RETURN o.id AS id, properties(o) AS props",
                   k=name_key(t["mention"], t["kind"]))
    if len(rows) != 1:
        p.conflicts.append({"where": where, "rule": "fill-target", "msg": f"fill 目标 {t} 未唯一命中"})
        return
    oid, db = rows[0]["id"], rows[0]["props"]
    p.bind[ref] = oid
    changed = {k: v for k, v in f["props"].items() if db.get(k) not in (None, "", v)}
    if changed:
        p.conflicts.append({"where": where, "rule": "fill-overwrite", "msg": f"只能补空字段，{sorted(changed)} 已有不同内容"})
    elif todo := {k: v for k, v in f["props"].items() if db.get(k) in (None, "")}:
        if not db.get("stub"):
            p.conflicts.append({"where": where, "rule": "not-stub", "msg": f"{oid} 不是桩节点"})
        else:
            p.fills[ref] = {"id": oid, "props": todo}
    else:
        p.same_nodes.append(ref)


def _plan_material(m: dict, run) -> dict:
    rows = run("MATCH (m:Material {content_hash: $h}) RETURN m.id AS id", h=m["sha256"])
    return {"id": rows[0]["id"] if rows else f"material_{m['sha256'][:12]}", "path": m["path"],
            "sha256": m["sha256"], "exists": bool(rows)}


def row_key(exp_key: str, r: dict, ids: dict, slot_names: list) -> str:
    slots = [f"{s}={'-' if r['slots'][s] is None else r['slots'][s]}" for s in slot_names]
    return "::".join([exp_key, ids[r["subject"]], r["variant"] or "-", ids[r["data"]], ids[r["metric"]], *slots])


def result_props(r: dict, slot_names: list) -> dict:
    return compact({"value": r["value"], "value_num": r["value_num"], "variant": r["variant"], "origin": r["origin"],
                    "origin_basis": r["origin_basis"], "origin_from": r["origin_from"], "note": r["note"],
                    **{f"slot_{s}": r["slots"][s] for s in slot_names}})


def experiment_props(exp: dict, ids: dict) -> dict:
    return compact({"anchor": exp["anchor"], "section": exp["section"], "lines": exp["lines"], "text": exp["text"],
                    "setting": exp["setting"], "slot_basis": [f"{s}={loc}" for s, loc in sorted(exp["slot_basis"].items())] or None,
                    "task": ids.get(exp["task"])})


def _plan_experiment(p: PaperPlan, exp: dict, ids: dict, slot_names: list, run):
    where = f"experiments.{exp['anchor']}"
    if not p.paper_id:   # 新论文：实验必然是新的；行键在 apply 中按分配到的 id 计算
        p.experiments.append({"exp": exp, "status": "new"})
        p.results["new"] += len(exp["results"])
        return
    unbound = {r[k] for r in exp["results"] for k in ("subject", "data", "metric") if r[k] not in ids}
    exp_key = f"{p.paper_id}::{exp['anchor']}"
    rows = run("MATCH (e:Experiment {exp_key: $k}) OPTIONAL MATCH (e)-[:ON_TASK]->(t) "
               "RETURN properties(e) AS props, t.id AS task", k=exp_key)
    if not rows:
        p.experiments.append({"exp": exp, "status": "new"})
        p.results["new"] += len(exp["results"])
        return
    if unbound:
        p.conflicts.append({"where": where, "rule": "experiment-objects",
                            "msg": f"实验已在库中，但其中的对象 {sorted(unbound)} 是本批新建的"})
        return
    db = {k: v for k, v in rows[0]["props"].items() if k not in ("id", "exp_key")} | compact({"task": rows[0]["task"]})
    form = experiment_props(exp, ids)
    if db != form:
        diff = sorted(k for k in set(db) | set(form) if db.get(k) != form.get(k))
        p.conflicts.append({"where": where, "rule": "experiment-changed", "msg": f"实验已在库中且字段 {diff} 不同"})
        return
    p.experiments.append({"exp": exp, "status": "same"})
    existing = {r["row_key"]: {k: v for k, v in r["props"].items() if k != "row_key"} for r in run(
        "MATCH (:Experiment {exp_key: $k})-[:HAS_RESULT]->(r:ResultUnit) RETURN r.row_key AS row_key, properties(r) AS props",
        k=exp_key)}
    seen = set()
    for r in exp["results"]:
        key = row_key(exp_key, r, ids, slot_names)
        if key in seen:
            p.errors.append({"where": where, "rule": "row-key-duplicate", "msg": f"绑定后行键重复 {key}"})
            continue
        seen.add(key)
        if key not in existing:
            p.results["new"] += 1
        elif existing[key] == result_props(r, slot_names):
            p.results["same"] += 1
        else:
            p.conflicts.append({"where": f"{where} {r['locator']}", "rule": "result-changed",
                                "msg": f"结果行已在库中且内容不同：{key}"})
    p.missing_in_form += sorted(set(existing) - seen)


# ── apply ──

def _txrun(tx):
    return lambda cypher, **params: tx.run(cypher, params).data()


def _write(tx, p: PaperPlan, alloc: IdAllocator, committed_by: str, rounds: int | None) -> dict:
    """在事务 tx 中写入一批；返回 ref -> id。"""
    delta, run = p.delta, _txrun(tx)
    nodes = delta["nodes"]
    ids = p.ids()
    for ref in p.new_nodes:
        ids[ref] = alloc.new(nodes[ref]["kind"])
    paper_id = ids["paper"]
    source, by = f"paper:{paper_id}", f"form:{delta['name']}"

    # 对象与补全
    for ref in p.new_nodes:
        n = nodes[ref]
        props = {"id": ids[ref], **n["props"], **({"stub": True} if n["stub"] else {})}
        tx.run(f"CREATE (o:{':'.join(n['labels'])}) SET o = $props", props=props)
    for ref, f in p.fills.items():
        tx.run("MATCH (o {id: $id}) SET o += $props REMOVE o.stub", id=f["id"], props=f["props"])

    # 精确键：新对象的 name 与 aliases，以及 refs 中 register 的称呼
    rows = [(ids[ref], raw, nodes[ref]["kind"]) for ref in p.new_nodes for raw in nodes[ref]["keys"].values()]
    rows += [(ids[ref], raw, kind) for ref, raw, kind in p.registers]
    for oid, raw, kind in rows:
        key = name_key(raw, kind)
        res = run(f"""MATCH (o:{family_of(oid)} {{id: $id}})
                      MERGE (k:NameKey {{key: $key}}) ON CREATE SET k = $props
                      MERGE (k)-[:NAMES]->(o)
                      WITH k MATCH (k)-[:NAMES]->(x) RETURN k.status AS status, collect(x.id) AS owners""",
                  id=oid, key=key, props={"key": key, "normalized": normalize(raw), "raw": raw, "kind": kind,
                                          "scope": "global", "normalizer_ref": NORMALIZER, "status": "active",
                                          "registered_from": source, "registered_by": by})
        if not res or res[0]["owners"] != [oid] or res[0]["status"] != "active":
            raise RuntimeError(f"NameKey 写入冲突（整批回滚）：{key} → {res}")

    # 材料
    m = p.material
    tx.run("""MERGE (m:Material {content_hash: $h}) ON CREATE SET m.id = $id, m.path = $path, m.format = 'markdown'
              WITH m MATCH (paper:Entity:Paper {id: $paper}) MERGE (m)-[:MATERIAL_OF]->(paper)""",
           h=m["sha256"], id=m["id"], path=m["path"], paper=paper_id)

    # 实验与结果行
    slot_names = sorted(DOMAINS[delta["domain"]]["slots"])
    for e in p.experiments:
        if e["status"] != "new":
            continue
        exp = e["exp"]
        eid, exp_key = alloc.new("Experiment"), f"{paper_id}::{exp['anchor']}"
        props = {"id": eid, "exp_key": exp_key, **experiment_props(exp, ids)}
        props.pop("task", None)
        loc = f"{exp['section']}::{exp['lines'][0]}:{exp['lines'][1]}"
        tx.run("""MATCH (paper:Entity:Paper {id: $paper}), (t:Concept:Task {id: $task})
                  CREATE (e:Content:Experiment) SET e = $props
                  CREATE (e)-[:FROM {material_ref: $mat, locators: [$loc]}]->(paper)
                  CREATE (e)-[:ON_TASK]->(t)""",
               paper=paper_id, task=ids[exp["task"]], props=props, mat=m["id"], loc=loc)
        part = exp["participants"]
        tx.run("""MATCH (e:Experiment {id: $e})
                  UNWIND $ev AS ev MATCH (s:Entity|Concept {id: ev.id}) CREATE (e)-[:EVALUATES {role: ev.role}]->(s)""",
               e=eid, ev=[{"id": ids[s], "role": role} for s, role in part["evaluates"]])
        tx.run("MATCH (e:Experiment {id: $e}) UNWIND $ds AS d MATCH (x:Entity {id: d}) "
               "CREATE (e)-[:USES {role: 'evaluation_data'}]->(x)", e=eid, ds=[ids[d] for d in part["uses"]])
        tx.run("MATCH (e:Experiment {id: $e}) UNWIND $ms AS m MATCH (x:Concept {id: m}) CREATE (e)-[:MEASURED_BY]->(x)",
               e=eid, ms=[ids[x] for x in part["measured_by"]])
        rows = [{"key": row_key(exp_key, r, ids, slot_names), "props": result_props(r, slot_names),
                 "subject": ids[r["subject"]], "role": r["role"], "data": ids[r["data"]], "metric": ids[r["metric"]],
                 "loc": r["locator"]} for r in exp["results"]]
        c = tx.run("""MATCH (e:Experiment {id: $e}), (paper:Entity:Paper {id: $paper})
                      UNWIND $rows AS row
                      MATCH (s:Entity|Concept {id: row.subject}), (d:Entity {id: row.data}), (mt:Concept {id: row.metric})
                      CREATE (r:ResultUnit) SET r = row.props, r.row_key = row.key
                      CREATE (e)-[:HAS_RESULT]->(r)
                      CREATE (r)-[:EVALUATES {role: row.role}]->(s)
                      CREATE (r)-[:USES {role: 'evaluation_data'}]->(d)
                      CREATE (r)-[:MEASURED_BY]->(mt)
                      CREATE (r)-[:FROM {material_ref: $mat, locators: [row.loc]}]->(paper)
                      RETURN count(r) AS c""", e=eid, paper=paper_id, rows=rows, mat=m["id"]).single()["c"]
        if c != len(rows):
            raise RuntimeError(f"{exp['anchor']}：{len(rows)} 个结果行只写入 {c} 个（端点没匹配上）")

    # 批次记录
    last = run("MATCH (b:IngestBatch) RETURN max(toInteger(substring(b.id, 6))) AS m")[0]["m"] or 0
    bid = f"batch_{last + 1:04d}"
    tx.run("""MATCH (paper:Entity:Paper {id: $paper})
              CREATE (b:IngestBatch) SET b = $props
              CREATE (b)-[:RECORDS]->(paper)""",
           paper=paper_id, props=compact({
               "id": bid, "form": delta["form"], "form_name": delta["name"], "material_hash": m["sha256"],
               "coverage": delta["coverage"], "committed_by": committed_by, "rounds": rounds,
               "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               **{f"stat_{k}": v for k, v in p.stats.items()},
               "new_objects": len(p.new_nodes), "filled_objects": len(p.fills), "new_results": p.results["new"]}))
    ids["_batch"] = bid
    return ids


def apply_paper(p: PaperPlan, *, commit: bool = True, committed_by: str = "agent", rounds: int | None = None,
                embed: bool = True) -> dict:
    """写入一批：单事务；写后在同一事务内重跑 dry_run，必须无阻塞且无可写内容。

    commit=False 为演练：写入并复核后回滚，库不留改动。返回 {ids, batch, committed, embedded}。
    """
    if p.blocked:
        raise ValueError(f"{p.delta.get('name')}：有 {len(p.errors)} 个错误、{len(p.pending)} 个待确认、"
                         f"{len(p.conflicts)} 个冲突，拒绝写入")
    if p.empty:
        return {"ids": p.ids(), "batch": None, "committed": False, "embedded": 0}
    alloc = IdAllocator()
    with driver.session(database=NEO4J_DB) as s:
        tx = s.begin_transaction()
        try:
            ids = _write(tx, p, alloc, committed_by, rounds)
            again = dry_run(p.delta, p.issues, run=_txrun(tx), semantic=False)
            if again.blocked or not again.empty:
                raise RuntimeError(f"写后复核失败（整批回滚）：{paper_summary(again)}")
            tx.commit() if commit else tx.rollback()
        except Exception:
            tx.rollback()
            raise
        finally:
            tx.close()
    embedded = 0
    if commit and embed:   # 新建或补全的对象要有向量，下一批的语义查重才看得到（commit_contract.md §7 第 7 项）
        from ...utils.embedding import sync_embeddings
        embedded = sync_embeddings()
    return {"ids": ids, "batch": ids.pop("_batch"), "committed": commit, "embedded": embedded}


def paper_summary(p: PaperPlan) -> str:
    name = p.delta.get("name", "?")
    lines = [f"== {name} ==",
             f"论文    {'已在库中 ' + p.paper_id if p.paper_id else '新建'}",
             f"对象    新建 {len(p.new_nodes)} · 补全 {len(p.fills)} · 不变 {len(p.same_nodes)} · 新注册称呼 {len(p.registers)}",
             f"实验    {dict(Counter(e['status'] for e in p.experiments))} · 结果行 新建 {p.results['new']} · 不变 {p.results['same']}",
             f"材料    {'已在库中' if p.material.get('exists') else '新建'} {p.material.get('id', '')}",
             f"解析    {dict(p.stats)}"]
    if p.missing_in_form:
        lines.append(f"库中有、表单中没有的结果行 {len(p.missing_in_form)} 个（只报告，不删除）")
    for label, items in (("错误", p.errors), ("待确认", p.pending), ("冲突", p.conflicts)):
        lines += [f"  [{label}] {i['where']}：{i['msg']}" for i in items]
    lines.append("→ 有阻塞项，apply 会拒绝整批" if p.blocked else ("→ 与库内容一致，无需写入" if p.empty else "→ 可以 apply"))
    return "\n".join(lines)
