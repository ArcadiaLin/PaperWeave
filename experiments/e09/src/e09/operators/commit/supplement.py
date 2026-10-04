"""Commit 的增补增量：supplement-form-v1（docs/designs/v2/commit_contract.md §2.2、§4、§5）。

与论文增量同一流程：dry_run（只读）→ apply（单事务）→ 写后复核 → 补算向量，阻塞项的分类与形状也相同。
增补表单只写 Agent 形成的内容，不新建 Entity、Concept，不注册 alias，引用的对象必须已在库中：
- Observation：text、ABOUT（至少一个对象）、可选 FROM {material_ref, locators}（终点是材料所属的论文）；
- Agent 认为的贡献：Contribution {stated_by: agent}，FROM 连到所属论文，有 basis 时边上带材料与定位；
- 正反关系：SUPPORTS / OPPOSES，两端同为 Claim 或同为 Proposition，边上存 description、stated_by: agent。
Agent 形成的记录都带 formed_by（表单填写）与 formed_at（apply 时生成，同一批相同）。

幂等（§5）：Observation 与 Agent 贡献没有自然键，同一 formed_by 下按 text 与对象集合（贡献另加所属论文）判重，
命中且 FROM 相同为不变，FROM 不同为冲突；正反关系按起点、终点、类型与 formed_by 判重，description 不同为冲突。
批次记录不连到 Paper，只记出处、形成者、提交者、时间与写入统计（§6）。
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...config import NEO4J_DB
from ...form import record_identity
from ...utils.graph import driver, q
from ...utils.ids import IdAllocator
from .paper import _bind_ref, _link, _txrun, compact, issue, next_batch_id

REF_FIX = "确认后改写为 {id: …}（增补表单不注册 alias）；对象应由论文批次建立时，先提交那一批，不要从语义候选中挑选"


@dataclass
class SupplementPlan:
    delta: dict
    issues: list
    bind: dict = field(default_factory=dict)          # ref -> 已有对象 id
    materials: dict = field(default_factory=dict)     # sha256 -> {id, paper}：basis 的材料与所属论文
    records: list = field(default_factory=list)       # {where, o, view, status: new | same}：Observation 与 Agent 贡献
    rels: list = field(default_factory=list)          # {where, rel, status: new | same}
    errors: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    confirmed: list = field(default_factory=list)
    registers: list = field(default_factory=list)     # 恒为空：增补表单不注册 alias（与 _bind_ref 共用字段）
    stats: Counter = field(default_factory=Counter)

    @property
    def blocked(self) -> bool:
        return bool(self.errors or self.pending or self.conflicts)

    @property
    def empty(self) -> bool:
        return not any(x["status"] == "new" for x in self.records + self.rels)

    def ids(self) -> dict:
        return dict(self.bind)


# ── dry_run ──

def dry_run_supplement(delta: dict, issues: list, run=q, semantic: bool = True) -> SupplementPlan:
    p = SupplementPlan(delta, issues)
    p.errors += [i for i in issues if i["level"] == "error"]
    p.pending += [i for i in issues if i["level"] == "pending"]
    p.confirmed += [i for i in issues if i["level"] == "confirmed"]
    if not delta:
        return p
    for ref, spec in delta["refs"].items():
        if spec:
            _bind_ref(p, ref, spec, run, semantic, fix=REF_FIX)
    records = [(f"observations[{i}]", o) for i, o in enumerate(delta["observations"])]
    records += [(f"contributions[{i}]", o) for i, o in enumerate(delta["contributions"])]
    for where, o in records:
        if o["basis"] and o["basis"]["sha256"] not in p.materials:
            _plan_material(p, where, o["basis"], run)
    for where, o in records:
        _plan_record(p, where, o, run)
    for i, rel in enumerate(delta["rels"]):
        _plan_stance(p, f"relationships[{i}]", rel, run)
    return p


def _plan_material(p: SupplementPlan, where: str, basis: dict, run):
    rows = run("MATCH (m:Material {content_hash: $h})-[:MATERIAL_OF]->(paper:Entity:Paper) RETURN m.id AS id, paper.id AS paper",
               h=basis["sha256"])
    if len(rows) == 1:
        p.materials[basis["sha256"]] = rows[0]
    else:
        p.conflicts.append(issue("conflict", "material-missing", where,
                                 f"材料 {basis['path']} 不在库中或不属于唯一一篇论文", fix="先提交该论文的论文表单"))


def record_view(o: dict, ids: dict, materials: dict) -> dict | None:
    """记录在库中应有的样子：对象集合、所属论文（贡献）与 FROM；引用或材料未就绪时返回 None。"""
    refs = o["about"] + ([o["paper"]] if o["kind"] == "Contribution" else [])
    b = o["basis"]
    if any(r not in ids for r in refs) or (b and b["sha256"] not in materials):
        return None
    view = {"about": sorted(ids[r] for r in o["about"]), "paper": ids.get(o.get("paper")), "from": None}
    if b:
        m = materials[b["sha256"]]
        view["from"] = {"paper": m["paper"], "material_ref": m["id"], "locators": b["locators"]}
    elif o["kind"] == "Contribution":   # 贡献没有材料依据时 FROM 仍连到所属论文，边上不带定位
        view["from"] = {"paper": view["paper"]}
    return view


def stored_records(kind: str, formed_by: str, text: str, run) -> list[dict]:
    rows = run(f"""MATCH (c:Content:{kind} {{formed_by: $by, text: $text}})
                   WHERE $kind <> 'Contribution' OR c.stated_by = 'agent'
                   RETURN c.id AS id, COLLECT {{ MATCH (c)-[:ABOUT]->(o) RETURN o.id }} AS about,
                          COLLECT {{ MATCH (c)-[f:FROM]->(x) RETURN {{paper: x.id, material_ref: f.material_ref, locators: f.locators}} }} AS froms""",
               kind=kind, by=formed_by, text=text)
    return [{"id": r["id"], "about": sorted(r["about"]), "froms": [compact(f) for f in r["froms"]]} for r in rows]


def _plan_record(p: SupplementPlan, where: str, o: dict, run):
    view = record_view(o, p.ids(), p.materials)
    if view is None:   # 引用未解析或材料缺失：已报待确认或冲突
        return
    if o["kind"] == "Contribution" and view["from"].get("paper") != view["paper"]:
        p.conflicts.append(issue("conflict", "basis-paper", where,
                                 f"basis 的材料属于 {view['from']['paper']}，不是贡献所属的论文 {view['paper']}"))
        return
    same = [s for s in stored_records(o["kind"], p.delta["formed_by"], o["text"], run)
            if s["about"] == view["about"] and (o["kind"] != "Contribution" or view["paper"] in [f["paper"] for f in s["froms"]])]
    if not same:
        p.records.append({"where": where, "o": o, "view": view, "status": "new"})
    elif len(same) > 1:
        p.conflicts.append(issue("conflict", "record-duplicated", where, f"库中已有多条相同记录 {[s['id'] for s in same]}"))
    elif same[0]["froms"] != ([compact(view["from"])] if view["from"] else []):
        p.conflicts.append(issue("conflict", "content-changed", where,
                                 f"{o['kind']} {same[0]['id']} 已在库中且依据不同；当前不做修订"))
    else:
        p.records.append({"where": where, "o": o, "view": view, "status": "same"})


def stance_props(rel: dict, formed_by: str) -> dict:
    return {"description": rel["description"], "stated_by": "agent", "formed_by": formed_by}


def _plan_stance(p: SupplementPlan, where: str, rel: dict, run):
    ids = p.ids()
    a, b = ids.get(rel["from"]), ids.get(rel["to"])
    if a is None or b is None:
        return
    rows = run(f"MATCH (a {{id: $a}})-[r:{rel['type']} {{formed_by: $by}}]->(b {{id: $b}}) "
               "RETURN r.description AS description, r.stated_by AS stated_by, r.formed_by AS formed_by",
               a=a, b=b, by=p.delta["formed_by"])
    if not rows:
        p.rels.append({"where": where, "rel": rel, "status": "new"})
    elif len(rows) > 1 or rows[0] != stance_props(rel, p.delta["formed_by"]):
        p.conflicts.append(issue("conflict", "rel-changed", where, f"{a} -[{rel['type']}]-> {b} 已由同一形成者写入且说明不同"))
    else:
        p.rels.append({"where": where, "rel": rel, "status": "same"})


# ── apply ──

def _write(tx, p: SupplementPlan, alloc: IdAllocator, committed_by: str, rounds: int | None) -> dict:
    """在事务 tx 中写入一批；返回 {where: 新记录 id}。"""
    delta, run, ids = p.delta, _txrun(tx), p.ids()
    formed = {"formed_by": delta["formed_by"],
              "formed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out = {}
    for x in p.records:
        if x["status"] != "new":
            continue
        o, view = x["o"], x["view"]
        cid = alloc.new(o["kind"])
        props = {"id": cid, "text": o["text"], **({"stated_by": "agent"} if o["kind"] == "Contribution" else {}), **formed}
        tx.run(f"CREATE (c:Content:{o['kind']}) SET c = $props", props=props)
        _link(tx, o["kind"], cid, "ABOUT", "Entity|Concept|Content", [{"id": i, "props": {}} for i in view["about"]], x["where"])
        if f := view["from"]:
            _link(tx, o["kind"], cid, "FROM", "Entity:Paper",
                  [{"id": f["paper"], "props": compact({"material_ref": f.get("material_ref"), "locators": f.get("locators")})}],
                  x["where"])
        out[x["where"]] = cid
    for x in p.rels:
        if x["status"] != "new":
            continue
        rel = x["rel"]
        c = tx.run(f"""MATCH (a:Content|Concept {{id: $a}}), (b:Content|Concept {{id: $b}})
                       CREATE (a)-[r:{rel['type']}]->(b) SET r = $props RETURN count(r) AS c""",
                   a=ids[rel["from"]], b=ids[rel["to"]], props=stance_props(rel, delta["formed_by"]) | formed).single()
        if not c or c["c"] != 1:
            raise RuntimeError(f"{x['where']}：{rel['type']} 未写入（端点没匹配上）")
    bid = next_batch_id(run)
    tx.run("CREATE (b:IngestBatch) SET b = $props", props=compact({
        "id": bid, "form": delta["form"], "form_name": delta["name"], "form_hash": delta.get("form_hash"),
        "formed_by": delta["formed_by"], "committed_by": committed_by, "rounds": rounds, "created_at": formed["formed_at"],
        "confirmed": [f"{i['rule']}@{i['where']}" for i in p.confirmed] or None,
        **{f"stat_{k}": v for k, v in p.stats.items()},
        "new_observations": sum(x["status"] == "new" and x["o"]["kind"] == "Observation" for x in p.records),
        "new_contributions": sum(x["status"] == "new" and x["o"]["kind"] == "Contribution" for x in p.records),
        "new_rels": sum(x["status"] == "new" for x in p.rels)}))
    out["_batch"] = bid
    return out


def apply_supplement(p: SupplementPlan, *, commit: bool = True, committed_by: str = "agent", rounds: int | None = None,
                     embed: bool = True) -> dict:
    """写入一批：单事务；写后在同一事务内重跑 dry_run，必须无阻塞且无可写内容。commit=False 为演练，写入并复核后回滚。"""
    if p.blocked:
        raise ValueError(f"{p.delta.get('name')}：有 {len(p.errors)} 个错误、{len(p.pending)} 个待确认、"
                         f"{len(p.conflicts)} 个冲突，拒绝写入")
    if p.empty:
        return {"ids": {}, "batch": None, "committed": False, "embedded": 0}
    alloc = IdAllocator()
    with driver.session(database=NEO4J_DB) as s:
        tx = s.begin_transaction()
        try:
            ids = _write(tx, p, alloc, committed_by, rounds)
            again = dry_run_supplement(p.delta, p.issues, run=_txrun(tx), semantic=False)
            if again.blocked or not again.empty:
                raise RuntimeError(f"写后复核失败（整批回滚）：{supplement_summary(again)}")
            tx.commit() if commit else tx.rollback()
        except Exception:
            tx.rollback()
            raise
        finally:
            tx.close()
    embedded = 0
    if commit and embed:   # 新记录的 text 与关系的 description 都建向量（graph_model_v2.md §5）
        from ...utils.embedding import sync_embeddings
        embedded = sync_embeddings()
    return {"ids": ids, "batch": ids.pop("_batch"), "committed": commit, "embedded": embedded}


# ── plan 的呈现 ──

def supplement_view(p: SupplementPlan) -> dict:
    def split(items, kind=None):
        items = [x for x in items if kind is None or x["o"]["kind"] == kind]
        return {s: [x["where"] for x in items if x["status"] == s] for s in ("new", "same")}

    status = "blocked" if p.blocked else ("unchanged" if p.empty else "ready")
    return {
        "batch": p.delta.get("name"), "form": p.delta.get("form"), "status": status, "formed_by": p.delta.get("formed_by"),
        "refs": dict(p.bind),
        "writes": {"observations": split(p.records, "Observation"), "contributions": split(p.records, "Contribution"),
                   "rels": split(p.rels)} if p.delta else {},
        "blocking": p.errors + p.pending + p.conflicts,
        "confirmed": [{"rule": i["rule"], "where": i["where"]} for i in p.confirmed],
        "stats": dict(p.stats),
    }


def supplement_summary(p: SupplementPlan) -> str:
    v = supplement_view(p)
    lines = [f"== {v['batch']} ==", f"形成者  {v['formed_by']}"]
    for label, k in (("观察", "observations"), ("贡献", "contributions"), ("正反关系", "rels")):
        if v["writes"]:
            lines.append(f"{label:<8}{ {s: len(x) for s, x in v['writes'][k].items()} }")
    lines.append(f"解析    {v['stats']}")
    for i in v["blocking"]:
        lines.append(f"  [{i['level']}] {i['rule']} @ {i['where']}：{i['msg']}")
        lines += [f"      候选 {c}" for c in i.get("candidates", [])]
        if i.get("fix"):
            lines.append(f"      改法 {i['fix']}")
    lines.append({"blocked": "→ 有阻塞项，apply 会拒绝整批", "unchanged": "→ 与库内容一致，无需写入",
                  "ready": "→ 可以 apply"}[v["status"]])
    return "\n".join(lines)
