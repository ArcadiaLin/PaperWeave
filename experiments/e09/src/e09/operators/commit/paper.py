"""Commit 的论文增量：dry_run（只读）→ apply（单事务）→ 写后复核 → 补算向量（docs/designs/v2/commit_contract.md）。

输入是 form.compile_form 的 (delta, issues)。plan 把阻塞项分三类，处理方不同：
- errors：表单自身写错（含 compile 报出的错误），Agent 改表单；
- pending：需要 Agent 做语义判断（引用未唯一命中、语义近邻未列入 rejected、本文与已有 Paper 相似……）；
- conflicts：与库内状态矛盾（键已被占用、撞上桩节点、已存内容变了……），由外部决定。
有任何阻塞项时 apply 拒绝整批。compile 的待确认项经 x-confirmed 确认后为 confirmed，不阻塞，记入批次记录。
每个阻塞项带稳定的规则码 rule、表单路径 where，必要时附 candidates 与改法 fix；plan_view 给出结构化的 plan。

身份规则（§4、§5）：
- 论文按唯一命名空间的标识（arXiv 等）识别；已存在即本批是重跑或补录。没有命中时，按名称词面与语义通道列出
  相似的已有 Paper（含桩节点），未列入 paper.rejected 的为待确认；确认是同一论文时改用 paper.fill 补全它。
- 新对象的精确键被占用：若由同一篇论文此前注册（NameKey.registered_from），视为重跑命中；
  若占用者是桩节点，提示改用 refs 或 fill；否则为 key-taken。
- Experiment 按 exp_key、Claim 与 Contribution 按 content_key 判定新建、不变或冲突；Content 不原地修改。
- CITES 按端点判定新建、不变或冲突；source_refs 为 <material_ref>::<定位>（graph_model_v2.md §1 关系来源）。

dry_run 的查询经 `run` 执行：默认是只读会话；apply 在同一写事务里传入事务执行器做复核，
`commit=False` 时整批写入后回滚（演练），库不留改动。语义查重调用 Resolve，走只读会话，看不到未提交的写入。
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...config import NEO4J_DB
from ...utils.graph import driver, q
from ...utils.ids import IdAllocator
from ...utils.namekey import NORMALIZER, name_key, normalize
from ...utils.schema import FAMILY, NAMESPACES, PREFIX, REL_RULES
from ..resolve import resolve

KIND_OF_PREFIX = {p: k for k, p in PREFIX.items()}
STUB_CHANNELS = {"lexical_name"}   # 桩节点只有名称：查重只走 id、alias 与名称词面（commit_contract.md §4）
DERIVED = ("id", "embedding", "embedding_key")   # 比较已存内容时忽略的属性


def family_of(obj_id: str) -> str:
    return FAMILY[KIND_OF_PREFIX[obj_id.rpartition("_")[0]]]


def compact(d: dict) -> dict:
    """去掉值为 None 的键：Neo4j 不存 null 属性，比较前两边同样处理。"""
    return {k: v for k, v in d.items() if v is not None}


def issue(level, rule, where, msg, candidates=None, fix=None) -> dict:
    return compact({"level": level, "rule": rule, "where": where, "msg": msg, "candidates": candidates, "fix": fix})


@dataclass
class PaperPlan:
    delta: dict
    issues: list
    paper_id: str | None = None                       # 论文已在库中（按标识命中或 fill 目标）时的 id
    paper_mode: str = "new"                           # new | existing | fill
    bind: dict = field(default_factory=dict)          # ref -> 已有对象 id（refs、fill 目标、重跑命中的本批对象）
    new_nodes: list = field(default_factory=list)     # 要新建的 ref（含 paper）
    same_nodes: list = field(default_factory=list)
    fills: dict = field(default_factory=dict)         # ref -> {id, props}：只填空字段
    registers: list = field(default_factory=list)     # {ref, id?, raw, kind}：新注册的精确键
    material: dict = field(default_factory=dict)      # {id, path, sha256, exists}
    experiments: list = field(default_factory=list)   # {exp, status: new | same}
    contents: list = field(default_factory=list)      # {c, status: new | same}：Claim、Contribution
    rels: list = field(default_factory=list)          # {rel, status: new | same}
    errors: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    confirmed: list = field(default_factory=list)     # compile 的待确认项中经 x-confirmed 确认的
    stats: Counter = field(default_factory=Counter)   # 主张 A 的构建成本：解析级别、候选与否定数

    @property
    def blocked(self) -> bool:
        return bool(self.errors or self.pending or self.conflicts)

    @property
    def empty(self) -> bool:
        return not (self.new_nodes or self.fills or self.registers or not self.material.get("exists", True)
                    or any(e["status"] == "new" for e in self.experiments + self.contents + self.rels))

    def ids(self) -> dict:
        return dict(self.bind) | ({"paper": self.paper_id} if self.paper_id else {})


def content_key(paper_id: str, c: dict) -> str:
    return f"{paper_id}::{c['kind']}::{c['key']}"


def exp_key(paper_id: str, anchor: str) -> str:
    return f"{paper_id}::{anchor}"


# ── dry_run ──

def dry_run(delta: dict, issues: list, run=q, semantic: bool = True) -> PaperPlan:
    p = PaperPlan(delta, issues)
    p.errors += [i for i in issues if i["level"] == "error"]
    p.pending += [i for i in issues if i["level"] == "pending"]
    p.confirmed += [i for i in issues if i["level"] == "confirmed"]
    if not delta:
        return p
    nodes = delta["nodes"]

    # 论文：fill 已有的 Paper 桩节点，或按唯一命名空间的标识识别
    if "paper" in delta["fills"]:
        p.paper_mode = "fill"
        _plan_fill(p, "paper", delta["fills"]["paper"], run)
        p.paper_id = p.bind.get("paper")
    elif "paper" in nodes:
        paper = nodes["paper"]
        uniq = [i for i in paper["props"].get("identifiers", []) if NAMESPACES[i.partition(":")[0]]]
        hits = run("MATCH (o:Entity:Paper) WHERE any(i IN o.identifiers WHERE i IN $ids) "
                   "RETURN o.id AS id, properties(o) AS props", ids=uniq) if uniq else []
        if len(hits) > 1:
            p.conflicts.append(issue("conflict", "identifier-multi", "paper", f"标识 {uniq} 命中多篇论文 {[h['id'] for h in hits]}"))
        elif hits:
            p.paper_id, p.paper_mode = hits[0]["id"], "existing"
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
                p.conflicts.append(issue("conflict", "key-taken", where, f"论文标题已注册给 {others}"))
            continue
        if not own:
            p.new_nodes.append(ref)
            _dedup(p, ref, n, semantic)
            continue
        if any(h["status"] != "active" for h in own):
            p.conflicts.append(issue("conflict", "key-ambiguous", where, f"称呼的精确键已隔离为 ambiguous：{sorted({h['id'] for h in own})}"))
            continue
        owners = {h["id"]: h for h in own}
        if len(owners) == 1 and source and all(h["src"] == source for h in own):
            oid, h = next(iter(owners.items()))   # 同一论文此前注册：重跑命中
            p.bind[ref] = oid
            _compare_existing(p, where, h["props"], n["props"] | ({"stub": True} if n["stub"] else {}), ref=ref)
        elif stubs := sorted(i for i, h in owners.items() if h["stub"]):
            fix = (f"是同一论文时改写为 paper: {{fill: {{id: {stubs[0]}}}, properties: {{...}}}}" if ref == "paper"
                   else f"改为 refs 引用 {{id: {stubs[0]}}}，或用 fill 补全")
            p.conflicts.append(issue("conflict", "stub-exists", where, f"已有同名桩节点 {stubs}",
                                     candidates=_describe(stubs, run), fix=fix))
        else:
            p.conflicts.append(issue("conflict", "key-taken", where, f"称呼已注册给 {sorted(owners)}"))

    # refs：只走 id 与 alias 两级，唯一命中才绑定
    for ref, spec in delta["refs"].items():
        _bind_ref(p, ref, spec, run, semantic)

    # fill：目标必须是桩节点；只填空字段（paper 的 fill 已在上面处理）
    for ref, f in delta["fills"].items():
        if ref != "paper":
            _plan_fill(p, ref, f, run)

    ids = p.ids()
    p.material = _plan_material(delta["material"], run)
    for exp in delta["experiments"]:
        _plan_experiment(p, exp, ids, run)
    for c in delta["contents"]:
        _plan_content(p, c, ids, run)
    for rel in delta["rels"]:
        _plan_rel(p, rel, ids, run)
    return p


def _describe(ids: list, run=q) -> list[dict]:
    """候选的可读描述：id、名称、kind、是否桩节点。"""
    rows = {r["id"]: r for r in run("MATCH (o) WHERE o.id IN $ids RETURN o.id AS id, o.name AS name, "
                                    "coalesce(o.stub, false) AS stub", ids=ids)}
    return [compact({"id": i, "name": rows.get(i, {}).get("name"), "kind": KIND_OF_PREFIX.get(i.rpartition("_")[0]),
                     "stub": rows.get(i, {}).get("stub") or None}) for i in ids]


def _compare_existing(p: PaperPlan, where: str, db: dict, form: dict, ref: str | None = None):
    """已有对象：表单写了、库里为空的字段可以补；库里已有且不同则冲突（当前不做修订）。"""
    db = {k: v for k, v in db.items() if k not in DERIVED}
    changed = {k: (db[k], v) for k, v in form.items() if k in db and db[k] != v}
    if changed:
        p.conflicts.append(issue("conflict", "object-changed", where,
                                 f"与库中已有内容不同：{ {k: (str(a)[:40], str(b)[:40]) for k, (a, b) in changed.items()} }"))
    elif extra := {k: v for k, v in form.items() if k not in db}:
        p.fills[ref or where] = {"id": p.bind.get(ref) or p.paper_id, "props": extra}
    elif ref:
        p.same_nodes.append(ref)


def _dedup(p: PaperPlan, ref: str, n: dict, semantic: bool):
    """新对象的语义查重：近邻须全部列入 rejected，否则待确认。paper 与已有 Paper（含桩节点）比较。"""
    if not semantic:
        return
    props = n["props"]
    query = {"mention": props["name"]}
    if not n["stub"]:
        query["text"] = props.get("definition") or props.get("description")
    r = resolve(query, kind=n["kind"], mode="write", channels=STUB_CHANNELS if n["stub"] else None)
    cands = [c for t in r["match_trace"] if t["stage"] == "semantic" for c in t["candidates"]]
    errors = [ch for ch, s in r["coverage"]["channels"].items() if s.startswith("error")]
    where = "paper" if ref == "paper" else f"objects.{ref}"
    p.stats["semantic_candidates"] += len(cands)
    p.stats["rejected"] += len([c for c in cands if c["id"] in n["rejected"]])
    if errors:
        p.pending.append(issue("pending", "dedup-unprocessed", where, f"语义查重通道执行失败 {errors}，查重不完整", fix="重跑 dry_run"))
    if open_ := [c for c in cands if c["id"] not in n["rejected"]]:
        described = {d["id"]: d for d in _describe([c["id"] for c in open_])}
        candidates = [described[c["id"]] | {"channels": sorted(c["evidence"])} for c in open_]
        if ref == "paper":
            p.pending.append(issue("pending", "paper-similar", where, "库中有相似的 Paper 节点，确认是否为同一论文", candidates,
                                   "是同一论文时改写为 paper: {fill: {id: …}, properties: {...}}；不是则把 id 列入 paper.rejected"))
        else:
            p.pending.append(issue("pending", "dedup", where, "语义近邻未判定", candidates, "确认不是同一对象后列入 rejected"))


REF_FIX = "确认后改写为 {id: …, printed?, register?}；若它应由先前的批次建立，先提交那一批，不要从语义候选中挑选"


def _bind_ref(p: PaperPlan, ref: str, spec: dict, run, semantic: bool, fix: str = REF_FIX):
    where = f"refs.{ref}"
    if "id" in spec:
        rows = run("MATCH (o {id: $id}) RETURN labels(o) AS labels", id=spec["id"])
        if not rows or spec["kind"] not in rows[0]["labels"]:
            p.conflicts.append(issue("conflict", "ref-missing", where, f"库中没有 {spec['kind']} {spec['id']}"))
            return
        p.bind[ref] = spec["id"]
        p.stats["ref_id"] += 1
        if spec["register"]:
            _plan_register(p, where, spec["id"], spec["printed"], spec["kind"], run)
        return
    rows = run("MATCH (k:NameKey {key: $k}) OPTIONAL MATCH (k)-[:NAMES]->(o) "
               "RETURN k.status AS status, collect(o.id) AS ids", k=name_key(spec["mention"], spec["kind"]))
    if rows and rows[0]["status"] == "active" and len(rows[0]["ids"]) == 1:
        p.bind[ref] = rows[0]["ids"][0]
        p.stats["ref_alias"] += 1
        return
    p.stats["ref_unresolved"] += 1
    candidates = None
    if semantic:
        r = resolve(spec["mention"], kind=spec["kind"], mode="read")
        candidates = _describe(r["refs"][:5]) if r["refs"] else None
    p.pending.append(issue("pending", "ref-unresolved", where, f"{spec['mention']!r} 未在 id / alias 级唯一命中", candidates, fix))


def _plan_register(p: PaperPlan, where: str, oid: str, raw: str, kind: str, run):
    """把称呼注册给已有对象：未注册则新注册，已注册给同一对象为不变，注册给别的对象为冲突。"""
    owner = run("MATCH (k:NameKey {key: $k})-[:NAMES]->(o) RETURN o.id AS id", k=name_key(raw, kind))
    if not owner:
        p.registers.append({"id": oid, "raw": raw, "kind": kind})
    elif owner[0]["id"] != oid:
        p.conflicts.append(issue("conflict", "key-taken", where, f"{raw!r} 已注册给 {owner[0]['id']}"))


def _plan_fill(p: PaperPlan, ref: str, f: dict, run):
    where = "paper" if ref == "paper" else f"objects.{ref}"
    t = f["target"]
    if "id" in t:
        rows = run("MATCH (o {id: $id}) RETURN o.id AS id, properties(o) AS props", id=t["id"])
    else:
        rows = run("MATCH (k:NameKey {key: $k, status: 'active'})-[:NAMES]->(o) RETURN o.id AS id, properties(o) AS props",
                   k=name_key(t["mention"], t["kind"]))
    if len(rows) != 1:
        p.conflicts.append(issue("conflict", "fill-target", where, f"fill 目标 {t} 未唯一命中"))
        return
    oid, db = rows[0]["id"], rows[0]["props"]
    p.bind[ref] = oid
    for raw in f.get("keys", {}).values():
        _plan_register(p, where, oid, raw, t.get("kind") or KIND_OF_PREFIX[oid.rpartition("_")[0]], run)
    changed = {k: v for k, v in f["props"].items() if db.get(k) not in (None, "", v)}
    if changed:
        p.conflicts.append(issue("conflict", "fill-overwrite", where, f"只能补空字段，{sorted(changed)} 已有不同内容"))
    elif todo := {k: v for k, v in f["props"].items() if db.get(k) in (None, "")}:
        if not db.get("stub"):
            p.conflicts.append(issue("conflict", "not-stub", where, f"{oid} 不是桩节点"))
        else:
            p.fills[ref] = {"id": oid, "props": todo}
    else:
        p.same_nodes.append(ref)


def _plan_material(m: dict, run) -> dict:
    rows = run("MATCH (m:Material {content_hash: $h}) RETURN m.id AS id", h=m["sha256"])
    return {"id": rows[0]["id"] if rows else f"material_{m['sha256'][:12]}", "path": m["path"],
            "sha256": m["sha256"], "exists": bool(rows)}


def rel_props(rel: dict, material_id: str) -> dict:
    return compact({"source_refs": [f"{material_id}::{loc}" for loc in rel["basis"]], "description": rel["description"]})


def content_props(c: dict) -> dict:
    return compact({"text": c["text"], "stated_by": "paper" if c["kind"] == "Contribution" else None})


# 实验与主张、贡献在库中应有的样子，dry_run 与库中现状逐项比较

def experiment_view(exp: dict, ids: dict) -> dict:
    return {"props": {"anchors": exp["anchors"], "text": exp["text"]}, "locators": exp["locators"], "task": ids[exp["task"]],
            "evaluates": sorted((ids[x["subject"]], x["role"]) for x in exp["participants"]),
            "uses": sorted(ids[d] for d in exp["data"]), "benchmark": [ids[exp["benchmark"]]] if exp["benchmark"] else []}


def stored_experiment(key: str, run) -> dict | None:
    rows = run("""MATCH (e:Experiment {exp_key: $k})
                  OPTIONAL MATCH (e)-[f:FROM]->()
                  OPTIONAL MATCH (e)-[:ON_TASK]->(t)
                  RETURN properties(e) AS props, f.locators AS locators, t.id AS task,
                         COLLECT { MATCH (e)-[r:EVALUATES]->(s) RETURN [s.id, r.role] } AS evaluates,
                         COLLECT { MATCH (e)-[:USES]->(d) RETURN d.id } AS uses,
                         COLLECT { MATCH (e)-[:EVALUATED_ON]->(b) RETURN b.id } AS benchmark""", k=key)
    if not rows:
        return None
    r = rows[0]
    return {"props": {k: v for k, v in r["props"].items() if k not in DERIVED + ("exp_key",)}, "locators": r["locators"],
            "task": r["task"], "evaluates": sorted(tuple(x) for x in r["evaluates"]), "uses": sorted(r["uses"]),
            "benchmark": sorted(r["benchmark"])}


def content_view(c: dict, ids: dict, paper_id: str) -> dict:
    return {"props": content_props(c), "locators": c["locators"], "about": sorted(ids[r] for r in c["about"]),
            "supported_by": sorted(exp_key(paper_id, a) for a in c["supported_by"])}


def stored_content(key: str, run) -> dict | None:
    rows = run("""MATCH (c:Content {content_key: $k})
                  OPTIONAL MATCH (c)-[f:FROM]->()
                  RETURN properties(c) AS props, f.locators AS locators,
                         COLLECT { MATCH (c)-[:ABOUT]->(o) RETURN o.id } AS about,
                         COLLECT { MATCH (c)-[:SUPPORTED_BY]->(e) RETURN e.exp_key } AS supported_by""", k=key)
    if not rows:
        return None
    r = rows[0]
    return {"props": {k: v for k, v in r["props"].items() if k not in DERIVED + ("content_key",)}, "locators": r["locators"],
            "about": sorted(r["about"]), "supported_by": sorted(r["supported_by"])}


def _unbound(refs: list, ids: dict) -> list:
    return sorted({r for r in refs if r and r not in ids})


def _plan_experiment(p: PaperPlan, exp: dict, ids: dict, run):
    where = f"experiments.{exp['anchors'][0]}"
    stored = stored_experiment(exp_key(p.paper_id, exp["anchors"][0]), run) if p.paper_id else None
    if stored is None:   # 新论文，或已有论文的新实验
        p.experiments.append({"exp": exp, "status": "new"})
        return
    refs = [x["subject"] for x in exp["participants"]] + exp["data"] + [exp["task"], exp["benchmark"]]
    if unbound := _unbound(refs, ids):
        p.conflicts.append(issue("conflict", "experiment-objects", where, f"实验已在库中，但其中的对象 {unbound} 是本批新建的"))
        return
    view = experiment_view(exp, ids)
    if diff := [k for k in view if view[k] != stored[k]]:
        p.conflicts.append(issue("conflict", "experiment-changed", where, f"实验已在库中且 {diff} 不同；当前不做修订"))
        return
    p.experiments.append({"exp": exp, "status": "same"})


def _plan_content(p: PaperPlan, c: dict, ids: dict, run):
    where = f"{'claims' if c['kind'] == 'Claim' else 'contributions'}.{c['key']}"
    stored = stored_content(content_key(p.paper_id, c), run) if p.paper_id else None
    if stored is None:
        p.contents.append({"c": c, "status": "new"})
        return
    if unbound := _unbound(c["about"], ids):
        p.conflicts.append(issue("conflict", "content-objects", where, f"{c['kind']} 已在库中，但其中的对象 {unbound} 是本批新建的"))
        return
    view = content_view(c, ids, p.paper_id)
    if diff := [k for k in view if view[k] != stored[k]]:
        p.conflicts.append(issue("conflict", "content-changed", where, f"{c['kind']} 已在库中且 {diff} 不同；当前不做修订"))
        return
    p.contents.append({"c": c, "status": "same"})


def _plan_rel(p: PaperPlan, rel: dict, ids: dict, run):
    where = f"relationships.{rel['type']}→{rel['to']}"
    a, b = ids.get(rel["from"]), ids.get(rel["to"])
    if a is None or b is None:   # 端点是本批新建的对象，关系必然是新的
        p.rels.append({"rel": rel, "status": "new"})
        return
    rows = run(f"MATCH (a {{id: $a}})-[r:{rel['type']}]->(b {{id: $b}}) RETURN properties(r) AS props", a=a, b=b)
    props = [{k: v for k, v in r["props"].items() if k not in DERIVED} for r in rows]
    if not rows:
        p.rels.append({"rel": rel, "status": "new"})
    elif len(rows) > 1 or props[0] != rel_props(rel, p.material["id"]):
        p.conflicts.append(issue("conflict", "rel-changed", where, f"{a} -[{rel['type']}]-> {b} 已在库中且依据或说明不同"))
    else:
        p.rels.append({"rel": rel, "status": "same"})


# ── apply ──

def _txrun(tx):
    return lambda cypher, **params: tx.run(cypher, params).data()


def _link(tx, src_label: str, src_id: str, rel: str, dst_label: str, rows: list[dict], what: str):
    """从一个节点向多个已有节点建同类边；rows 为 [{id, props}]，端点没匹配上则整批回滚。"""
    if not rows:
        return
    c = tx.run(f"""MATCH (s:{src_label} {{id: $s}}) UNWIND $rows AS row
                   MATCH (x:{dst_label} {{id: row.id}}) CREATE (s)-[r:{rel}]->(x) SET r = row.props
                   RETURN count(r) AS c""", s=src_id, rows=rows).single()["c"]
    if c != len(rows):
        raise RuntimeError(f"{what} 的 {rel}：{len(rows)} 条只写入 {c} 条（端点没匹配上）")


def next_batch_id(run) -> str:
    """批次 id：论文与增补批次共用一个序列。"""
    last = run("MATCH (b:IngestBatch) RETURN max(toInteger(substring(b.id, 6))) AS m")[0]["m"] or 0
    return f"batch_{last + 1:04d}"


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

    # 精确键：新对象的 name 与 aliases，refs 中 register 的称呼，fill 带来的称呼
    rows = [(ids[ref], raw, nodes[ref]["kind"]) for ref in p.new_nodes for raw in nodes[ref]["keys"].values()]
    rows += [(r["id"], r["raw"], r["kind"]) for r in p.registers]
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

    # 实验：研究问题级，描述、锚点、任务与参与边
    for e in p.experiments:
        if e["status"] != "new":
            continue
        exp = e["exp"]
        eid = alloc.new("Experiment")
        props = {"id": eid, "exp_key": exp_key(paper_id, exp["anchors"][0]), "anchors": exp["anchors"], "text": exp["text"]}
        tx.run("""MATCH (paper:Entity:Paper {id: $paper}), (t:Concept:Task {id: $task})
                  CREATE (e:Content:Experiment) SET e = $props
                  CREATE (e)-[:FROM {material_ref: $mat, locators: $locs}]->(paper)
                  CREATE (e)-[:ON_TASK]->(t)""",
               paper=paper_id, task=ids[exp["task"]], props=props, mat=m["id"], locs=exp["locators"])
        what = exp["anchors"][0]
        _link(tx, "Experiment", eid, "EVALUATES", "Entity|Concept",
              [{"id": ids[x["subject"]], "props": {"role": x["role"]}} for x in exp["participants"]], what)
        _link(tx, "Experiment", eid, "USES", "Entity", [{"id": ids[d], "props": {"role": "evaluation_data"}} for d in exp["data"]], what)
        if exp["benchmark"]:
            _link(tx, "Experiment", eid, "EVALUATED_ON", "Entity:Benchmark", [{"id": ids[exp["benchmark"]], "props": {}}], what)

    # 主张与自述贡献：描述、正文定位、关联对象；主张连到本文支撑它的实验
    for e in p.contents:
        if e["status"] != "new":
            continue
        c = e["c"]
        cid = alloc.new(c["kind"])
        props = {"id": cid, "content_key": content_key(paper_id, c), **content_props(c)}
        tx.run(f"""MATCH (paper:Entity:Paper {{id: $paper}})
                   CREATE (c:Content:{c['kind']}) SET c = $props
                   CREATE (c)-[:FROM {{material_ref: $mat, locators: $locs}}]->(paper)""",
               paper=paper_id, props=props, mat=m["id"], locs=c["locators"])
        what = f"{c['kind']} {c['key']}"
        _link(tx, c["kind"], cid, "ABOUT", "Entity|Concept", [{"id": ids[r], "props": {}} for r in c["about"]], what)
        sup = run("MATCH (e:Experiment) WHERE e.exp_key IN $keys RETURN e.id AS id",
                  keys=[exp_key(paper_id, a) for a in c["supported_by"]])
        if len(sup) != len(c["supported_by"]):
            raise RuntimeError(f"{what} 的 SUPPORTED_BY：{c['supported_by']} 只找到 {len(sup)} 个实验")
        _link(tx, c["kind"], cid, "SUPPORTED_BY", "Experiment", [{"id": r["id"], "props": {}} for r in sup], what)

    # 关系：本文 → 被引论文
    for r in p.rels:
        if r["status"] != "new":
            continue
        rel = r["rel"]
        fa, fb, kb = REL_RULES[rel["type"]]
        c = tx.run(f"""MATCH (a:{fa} {{id: $a}}), (b:{fb}:{kb} {{id: $b}})
                       CREATE (a)-[r:{rel['type']}]->(b) SET r = $props RETURN count(r) AS c""",
                   a=ids[rel["from"]], b=ids[rel["to"]], props=rel_props(rel, m["id"])).single()
        if not c or c["c"] != 1:
            raise RuntimeError(f"{rel['type']} {rel['from']} → {rel['to']} 未写入（端点没匹配上）")

    # 批次记录
    bid = next_batch_id(run)
    tx.run("""MATCH (paper:Entity:Paper {id: $paper})
              CREATE (b:IngestBatch) SET b = $props
              CREATE (b)-[:RECORDS]->(paper)""",
           paper=paper_id, props=compact({
               "id": bid, "form": delta["form"], "form_name": delta["name"], "form_hash": delta.get("form_hash"),
               "material_hash": m["sha256"],
               "coverage": delta["coverage"], "committed_by": committed_by, "rounds": rounds,
               "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "confirmed": [f"{i['rule']}@{i['where']}" for i in p.confirmed] or None,
               **{f"stat_{k}": v for k, v in p.stats.items()},
               "new_objects": len(p.new_nodes), "filled_objects": len(p.fills),
               "new_experiments": sum(e["status"] == "new" for e in p.experiments),
               "new_contents": sum(e["status"] == "new" for e in p.contents),
               "new_rels": sum(r["status"] == "new" for r in p.rels)}))
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
    if commit and embed:   # 新建或补全的对象要有向量，下一批的语义查重才看得到（commit_contract.md §1）
        from ...utils.embedding import sync_embeddings
        embedded = sync_embeddings()
    return {"ids": ids, "batch": ids.pop("_batch"), "committed": commit, "embedded": embedded}


# ── plan 的呈现 ──

def plan_view(p: PaperPlan) -> dict:
    """给 Agent 的结构化 plan：状态、apply 会写什么、阻塞项（含候选与改法）、已确认项与统计。"""
    def split(items, key):
        return {s: [key(x) for x in items if x["status"] == s] for s in ("new", "same")}

    status = "blocked" if p.blocked else ("unchanged" if p.empty else "ready")
    return {
        "batch": p.delta.get("name"), "form": p.delta.get("form"), "status": status,
        "paper": compact({"status": p.paper_mode, "id": p.paper_id}),
        "writes": {
            "objects": {"new": list(p.new_nodes), "fill": sorted(p.fills), "same": list(p.same_nodes)},
            "names": [compact({"ref": r.get("ref"), "id": r.get("id"), "raw": r["raw"]}) for r in p.registers]
                     + [{"ref": ref, "raw": raw} for ref in p.new_nodes for raw in p.delta["nodes"][ref]["keys"].values()],
            "material": "same" if p.material.get("exists") else "new",
            "experiments": split(p.experiments, lambda e: e["exp"]["anchors"][0]),
            "contents": split(p.contents, lambda e: f"{e['c']['kind'].lower()}:{e['c']['key']}"),
            "rels": split(p.rels, lambda e: f"{e['rel']['type']}→{e['rel']['to']}"),
        } if p.delta else {},
        "blocking": p.errors + p.pending + p.conflicts,
        "confirmed": [{"rule": i["rule"], "where": i["where"]} for i in p.confirmed],
        "stats": dict(p.stats),
    }


def paper_summary(p: PaperPlan) -> str:
    v = plan_view(p)
    w = v["writes"]
    lines = [f"== {v['batch']} ==", f"论文    {v['paper']['status']} {v['paper'].get('id', '')}"]
    if w:
        o = w["objects"]
        lines += [f"对象    新建 {len(o['new'])} · 补全 {len(o['fill'])} · 不变 {len(o['same'])} · 新注册称呼 {len(p.registers)}",
                  *(f"{label:<8}{ {s: len(x) for s, x in w[k].items()} }" for label, k in
                    (("实验", "experiments"), ("主张贡献", "contents"), ("关系", "rels"))),
                  f"材料    {w['material']} {p.material.get('id', '')}"]
    lines.append(f"解析    {v['stats']}")
    for i in v["blocking"]:
        lines.append(f"  [{i['level']}] {i['rule']} @ {i['where']}：{i['msg']}")
        lines += [f"      候选 {c}" for c in i.get("candidates", [])]
        if i.get("fix"):
            lines.append(f"      改法 {i['fix']}")
    lines += [f"  [confirmed] {i['rule']} @ {i['where']}" for i in v["confirmed"]]
    lines.append({"blocked": "→ 有阻塞项，apply 会拒绝整批", "unchanged": "→ 与库内容一致，无需写入",
                  "ready": "→ 可以 apply"}[v["status"]])
    return "\n".join(lines)
