"""Commit(delta, mode: dry_run | apply)：增量检查 → plan（dry_run，只查不写）→ apply（单事务）→ 复核。

目前只接受种子增量（Entity、Concept 与它们的 NameKey、关系）；论文入库表单编译出的增量确定后也走这里。

身份按 NameKey 精确键与命名空间标识解析（graph_model_v2.md §2.4、第 5 节）：
- 对象身份看 `name` 的精确键：命中即该对象，属性差异列为更新；未命中为新对象；
- 每个精确键：未注册 → 新键；已注册给同一对象 → 不变；注册给别的对象或已隔离为 ambiguous → 冲突；
- 唯一命名空间的标识被别的对象占用 → 冲突；非唯一的 url 被别的对象持有 → 查重候选，不阻止写入。
有冲突整批拒绝。更新语义是 `SET n += props`：删掉的属性或 alias 不会从库里删除。
"""

from collections import defaultdict
from dataclasses import dataclass, field

from ...config import NEO4J_DB
from ...utils.graph import driver, q
from ...utils.ids import IdAllocator
from ...utils.namekey import NORMALIZER, name_key, normalize
from ...utils.schema import FORM_ONLY, NAMESPACES, REL_RULES, REQUIRED, SEED_KINDS, SYMMETRIC


# ── 增量检查：与库无关 ──

def scalar_or_list(v) -> bool:
    """Neo4j 属性只能是标量或标量列表。"""
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v))


def check_seed(raw: dict, name: str) -> dict:
    """返回 {name, nodes: {ref: node}, rels: [(from, type, to)]}；node 带 family、kind、写进图的 props 与精确键 keys。"""
    nodes, rels, seen_rels, key_owner, uniq_owner = {}, [], set(), {}, {}
    for n in raw.get("nodes") or []:
        ref, props = n["ref"], dict(n.get("properties") or {})
        assert ref not in nodes, f"{name}: 批内重复 ref {ref}"
        assert len(n["labels"]) == 2, f"{name}: {ref} 需要恰好两个 Label（主 Label + kind），实际是 {n['labels']}"
        family, kind = n["labels"]
        assert kind in SEED_KINDS.get(family, ()), f"{name}: {ref} 的 {n['labels']} 不在种子范围 {SEED_KINDS}"
        assert "id" not in props, f"{name}: {ref} 不应自带 id，id 由入库分配"
        assert props.get("name") and props.get(REQUIRED[family]), f"{name}: {ref} 缺 name 或 {REQUIRED[family]}"
        bad = [k for k, v in props.items() if not scalar_or_list(v)]
        assert not bad, f"{name}: {ref} 的属性 {bad} 不是标量或标量列表"
        for i in props.get("identifiers", []):
            ns, sep, value = i.partition(":")
            assert sep and value and ns in NAMESPACES, f"{name}: {ref} 的标识 {i!r} 不是已声明命名空间的 <namespace>:<value>"
            if NAMESPACES[ns]:
                assert i not in uniq_owner, f"{name}: 唯一标识 {i} 同时出现在 {uniq_owner[i]} 与 {ref}"
                uniq_owner[i] = ref
        keys = {}   # key -> 原字符串；同一节点的两个称呼规范化后相同，只注册一次
        for s in [props["name"], *props.get("aliases", [])]:
            assert "|" not in normalize(s), f"{name}: {ref} 的称呼 {s!r} 含键分隔符 |"
            k = name_key(s, kind)
            assert key_owner.get(k, ref) == ref, f"{name}: 精确键 {k!r} 同时注册给 {key_owner[k]} 与 {ref}"
            key_owner[k] = ref
            keys.setdefault(k, s)
        nodes[ref] = {"labels": n["labels"], "family": family, "kind": kind, "keys": keys,
                      "props": {k: v for k, v in props.items() if k not in FORM_ONLY}}
    for r in raw.get("relationships") or []:
        a, t, c = r["from"], r["type"], r["to"]
        assert a in nodes and c in nodes, f"{name}: 关系 {a} -{t}-> {c} 的端点不在本文件"
        assert t in REL_RULES, f"{name}: 关系类型 {t!r} 不在 {sorted(REL_RULES)}"
        fa, fc, kc = REL_RULES[t]
        ok = (nodes[a]["family"], nodes[c]["family"]) == (fa, fc) and kc in (None, nodes[c]["kind"])
        if t == "BROADER":
            ok = ok and nodes[a]["kind"] == nodes[c]["kind"]
        assert ok, f"{name}: {a} {nodes[a]['labels']} -{t}-> {c} {nodes[c]['labels']} 不符合 {t} 的端点定义"
        ident = (min(a, c), t, max(a, c)) if t in SYMMETRIC else (a, t, c)
        assert ident not in seen_rels, f"{name}: 批内重复关系 {a} -{t}- {c}"
        seen_rels.add(ident)
        rels.append((a, t, c))
    return {"name": name, "nodes": nodes, "rels": rels}


# ── plan：只查不写 ──

@dataclass
class Plan:
    batch: dict
    target: dict = field(default_factory=dict)       # ref -> 已有对象的 id；不在其中的是新对象
    new_nodes: list = field(default_factory=list)
    upd_nodes: dict = field(default_factory=dict)    # ref -> {字段: (库里的值, 种子的值)}
    same_nodes: list = field(default_factory=list)
    new_keys: list = field(default_factory=list)     # (ref, 原字符串, key)
    same_keys: int = 0
    new_rels: list = field(default_factory=list)
    same_rels: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)    # 拒绝写入的原因
    candidates: list = field(default_factory=list)   # 非唯一标识的查重候选：不阻止写入，交外部判断

    @property
    def empty(self) -> bool:
        return not (self.new_nodes or self.upd_nodes or self.new_keys or self.new_rels)


def diff_props(old: dict, new: dict) -> dict:
    """种子里写了、且和库里不同的字段。"""
    return {k: (old.get(k), v) for k, v in new.items() if old.get(k) != v}


def plan_seed(b: dict) -> Plan:
    p = Plan(b)
    nodes = b["nodes"]

    # 精确键：一次查出本批全部键的注册情况
    hits = defaultdict(list)   # key -> [{status, id}]；正常至多一个对象
    for r in q("MATCH (k:NameKey) WHERE k.key IN $keys OPTIONAL MATCH (k)-[:NAMES]->(o) "
               "RETURN k.key AS key, k.status AS status, o.id AS id",
               keys=[k for n in nodes.values() for k in n["keys"]]):
        hits[r["key"]].append(r)
    for ref, n in nodes.items():
        owners = sorted({h["id"] for h in hits[name_key(n["props"]["name"], n["kind"])] if h["id"]})
        if len(owners) == 1:
            p.target[ref] = owners[0]
        for k, raw in n["keys"].items():
            hs = hits[k]
            held = sorted({h["id"] for h in hs if h["id"]})
            if any(h["status"] != "active" for h in hs):
                p.conflicts.append({"ref": ref, "rule": "key-ambiguous", "what": k, "holders": held})
            elif not held:
                p.new_keys.append((ref, raw, k))
            elif held == [p.target.get(ref)]:
                p.same_keys += 1
            else:
                p.conflicts.append({"ref": ref, "rule": "key-taken", "what": k, "holders": held})

    # 已有对象：Label 必须一致，属性差异列为更新
    db = {r["id"]: r for r in q("MATCH (n) WHERE (n:Entity OR n:Concept) AND n.id IN $ids "
                                "RETURN n.id AS id, labels(n) AS labels, properties(n) AS props",
                                ids=sorted(set(p.target.values())))}
    for ref, nid in p.target.items():
        if set(db[nid]["labels"]) != set(nodes[ref]["labels"]):
            p.conflicts.append({"ref": ref, "rule": "label-mismatch", "what": nid, "holders": db[nid]["labels"]})
        elif d := diff_props(db[nid]["props"], nodes[ref]["props"]):
            p.upd_nodes[ref] = d
        else:
            p.same_nodes.append(ref)
    p.new_nodes = [ref for ref in nodes if ref not in p.target]

    # identifiers：库里的持有者，加上本批其他节点
    by_ident = defaultdict(list)
    for ref, n in nodes.items():
        for i in n["props"].get("identifiers", []):
            by_ident[i].append(ref)
    holders = defaultdict(list)
    for r in q("MATCH (o) WHERE (o:Entity OR o:Concept) AND any(i IN o.identifiers WHERE i IN $ids) "
               "UNWIND [i IN o.identifiers WHERE i IN $ids] AS i RETURN i, o.id AS id, o.name AS name",
               ids=list(by_ident)):
        holders[r["i"]].append(r)
    for i, refs in by_ident.items():
        unique = NAMESPACES[i.partition(":")[0]]
        for ref in refs:
            in_graph = [f"{h['id']} {h['name']}" for h in holders[i] if h["id"] != p.target.get(ref)]
            if unique and in_graph:
                p.conflicts.append({"ref": ref, "rule": "identifier-taken", "what": i, "holders": in_graph})
            elif not unique and ref not in p.target:   # 写入模式下，只有新对象需要查重
                in_batch = [r for r in refs if r != ref and r not in p.target]
                if in_graph or in_batch:
                    p.candidates.append({"identifier": i, "ref": ref, "in_graph": in_graph, "in_batch": in_batch})

    # 关系：两端都已在库里才可能已存在
    known = [{"a": p.target[a], "t": t, "c": p.target[c], "k": [a, t, c]}
             for a, t, c in b["rels"] if a in p.target and c in p.target]
    found = {tuple(r["k"]) for r in q(
        """UNWIND $rows AS row
           MATCH (a {id: row.a})-[r]-(c {id: row.c})
           WHERE type(r) = row.t AND (startNode(r) = a OR row.t IN $sym)
           RETURN DISTINCT row.k AS k""", rows=known, sym=sorted(SYMMETRIC))}
    for key in b["rels"]:
        (p.same_rels if key in found else p.new_rels).append(key)
    return p


def short(v, n=60):
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def summary(p: Plan) -> str:
    """plan 的文字摘要：计数与更新的字段差异。查重候选与冲突的明细由调用方展示。"""
    lines = [f"== {p.batch['name']} ==",
             f"对象    新建 {len(p.new_nodes)} · 更新 {len(p.upd_nodes)} · 不变 {len(p.same_nodes)}",
             f"精确键  新注册 {len(p.new_keys)} · 已注册 {p.same_keys}",
             f"关系    新建 {len(p.new_rels)} · 已存在 {len(p.same_rels)}"]
    for ref, d in p.upd_nodes.items():
        lines.append(f"更新 {ref} → {p.target[ref]}：")
        lines += [f"    {k}: {short(old)} → {short(new)}" for k, (old, new) in d.items()]
    if p.candidates:
        lines.append(f"查重候选（非唯一标识，不阻止写入）{len(p.candidates)} 条")
    if p.conflicts:
        lines.append(f"冲突 {len(p.conflicts)} 处 → apply 会拒绝整批")
    elif p.empty:
        lines.append("→ 与库内容一致，无需写入")
    return "\n".join(lines)


# ── apply：单事务写入 ──

def apply_plan(p: Plan, ids: IdAllocator) -> dict:
    """写入一批；返回 ref -> id。有冲突时不写，返回空 dict。"""
    b = p.batch
    if p.conflicts:
        print(f"{b['name']}：{len(p.conflicts)} 处冲突，拒绝写入（整批不写）")
        return {}
    if p.empty:
        print(f"{b['name']}：无变化，跳过写入")
        return dict(p.target)

    nodes = b["nodes"]
    ref2id = dict(p.target) | {ref: ids.new(nodes[ref]["kind"]) for ref in p.new_nodes}
    source = f"seed:{b['name']}"

    def work(tx):
        # 新对象：按 Label 组合分组
        groups = defaultdict(list)
        for ref in p.new_nodes:
            groups[tuple(nodes[ref]["labels"])].append({"id": ref2id[ref], **nodes[ref]["props"]})
        for labels, rows in groups.items():
            c = tx.run(f"UNWIND $rows AS row CREATE (n:{':'.join(labels)}) SET n = row RETURN count(n) AS c",
                       rows=rows).single()["c"]
            assert c == len(rows)
        # 已有对象：种子写了的属性覆盖，没写的保留
        for ref in p.upd_nodes:
            fam = nodes[ref]["family"]
            tx.run(f"MATCH (n:{fam} {{id: $id}}) SET n += $props", id=ref2id[ref], props=nodes[ref]["props"])
        # NameKey：MERGE 后在同一事务里确认该键只指向本对象且仍为 active，否则抛错、整批回滚
        groups = defaultdict(list)
        for ref, raw, k in p.new_keys:
            n = nodes[ref]
            groups[n["family"]].append({"id": ref2id[ref], "key": k, "props": {
                "key": k, "normalized": normalize(raw), "raw": raw, "kind": n["kind"], "scope": "global",
                "normalizer_ref": NORMALIZER, "status": "active", "registered_from": source, "registered_by": "seed"}})
        for fam, rows in groups.items():
            res = tx.run(f"""UNWIND $rows AS row
                             MATCH (o:{fam} {{id: row.id}})
                             MERGE (k:NameKey {{key: row.key}}) ON CREATE SET k = row.props
                             MERGE (k)-[:NAMES]->(o)
                             WITH k, row
                             MATCH (k)-[:NAMES]->(x)
                             RETURN row.key AS key, row.id AS id, k.status AS status, collect(x.id) AS owners""",
                         rows=rows).data()
            bad = [r for r in res if r["owners"] != [r["id"]] or r["status"] != "active"]
            if len(res) != len(rows) or bad:
                raise RuntimeError(f"NameKey 写入冲突（整批回滚）：{bad or '有对象没匹配上'}")
        # 唯一命名空间的标识：列表元素没有数据库约束，在事务内复查
        uniq = sorted({i for ref in p.new_nodes + list(p.upd_nodes) for i in nodes[ref]["props"].get("identifiers", [])
                       if NAMESPACES[i.partition(":")[0]]})
        if uniq:
            dup = tx.run("UNWIND $ids AS i MATCH (o) WHERE (o:Entity OR o:Concept) AND i IN o.identifiers "
                         "WITH i, collect(o.id) AS owners WHERE size(owners) > 1 RETURN i, owners", ids=uniq).data()
            if dup:
                raise RuntimeError(f"唯一标识重复（整批回滚）：{dup}")
        # 关系：按 (类型, 端点主 Label) 分组；语义对称的用无方向 MERGE
        groups = defaultdict(list)
        for a, t, c in p.new_rels:
            groups[(t, nodes[a]["family"], nodes[c]["family"])].append({"a": ref2id[a], "c": ref2id[c]})
        for (t, fa, fc), rows in groups.items():
            arrow = "-" if t in SYMMETRIC else "->"
            c = tx.run(f"UNWIND $rows AS row MATCH (a:{fa} {{id: row.a}}) MATCH (c:{fc} {{id: row.c}}) "
                       f"MERGE (a)-[r:{t}]{arrow}(c) RETURN count(r) AS c", rows=rows).single()["c"]
            assert c == len(rows), f"{t}：{len(rows)} 条里只写入 {c} 条（端点没匹配上）"

    with driver.session(database=NEO4J_DB) as s:
        s.execute_write(work)
    print(f"{b['name']}：写入 对象 {len(p.new_nodes) + len(p.upd_nodes)}，"
          f"NameKey {len(p.new_keys)}，关系 {len(p.new_rels)}")

    again = plan_seed(b)   # 复核：写完之后库内容应与本批完全一致
    if not again.empty or again.conflicts:
        raise RuntimeError(f"{b['name']}：复核失败，写入后仍有差异")
    print("  ✓ 复核通过")
    return {ref: again.target[ref] for ref in nodes}

