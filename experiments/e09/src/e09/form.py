"""论文表单编译：表单 → delta（docs/designs/v2/commit_contract.md §1、§4）。

compile 不查库，只看表单、材料文件与领域配置；同一表单与材料必得同一结果。问题分两级：
- error：表单自身写错（结构、槽语法、锚点不符、行键重复……），由 Agent 改表单；
- pending：需要 Agent 确认（原文印的数据名与引用称呼不同）。
引用解析、查重、冲突与幂等在 Commit 的 dry_run 中判定，不在这里。

    uv run python -m e09.form <表单.yml> ...    # 打印编译摘要与问题；有 error 时返回非零
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

from .config import DATA
from .utils.domain import DOMAINS, slot_form
from .utils.namekey import name_key, normalize
from .utils.schema import FAMILY, KINDS, NAMESPACES, PREFIX, REL_RULES, REQUIRED

FORM_VERSION = "paper-form-v1"
TOP_KEYS = {"form", "domain", "material", "paper", "refs", "objects", "relationships", "experiments"}
EXP_KEYS = {"ref", "anchor", "section", "lines", "task", "text", "setting", "slots", "slot_basis", "columns", "rows"}
COL_KEYS = {"subject", "variant", "role", "metrics", "origin", "slots"}
ROW_KEYS = {"data", "line", "values", "cells", "note"}
ROLES = {"target", "baseline"}
ORIGINS = {"own", "rerun", "cited", "unstated"}
LOCATOR = re.compile(r"(?P<section>.+)::(?P<start>\d+):(?P<end>\d+)")   # <章节>::<start>:<end>，行号从 1 起
NUMBER = re.compile(r"-?\d+(\.\d+)?")
KIND_OF_PREFIX = {p: k for k, p in PREFIX.items()}


def scalar_or_list(v) -> bool:
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v))


def md_cells(line: str) -> list[str]:
    """Markdown 表格行的单元格；去掉末尾的空单元格。"""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    while cells and cells[-1] == "":
        cells.pop()
    return cells


class Compiler:
    def __init__(self, raw: dict, name: str):
        self.raw, self.name = raw, name
        self.issues = []
        self.lines = []

    def error(self, where, msg):
        self._add("error", where, msg)

    def pending(self, where, msg):
        self._add("pending", where, msg)

    def _add(self, level, where, msg):
        issue = {"level": level, "where": where, "msg": msg}
        if issue not in self.issues:   # 同一问题在多个格上出现时只报一次
            self.issues.append(issue)

    # ── 共用检查 ──

    def locator(self, where, loc) -> bool:
        m = LOCATOR.fullmatch(loc) if isinstance(loc, str) else None
        if not m:
            self.error(where, f"定位 {loc!r} 应为 <章节>::<start>:<end>")
            return False
        start, end = int(m["start"]), int(m["end"])
        if not 1 <= start <= end <= len(self.lines):
            self.error(where, f"定位 {loc!r} 超出材料范围（共 {len(self.lines)} 行）")
            return False
        return True

    def slots(self, where, domain, slots: dict):
        """槽须已声明；给了值的须合语法（null 是否允许，在合并后的逐格检查中判定）。"""
        declared = DOMAINS[domain]["slots"]
        for s, v in slots.items():
            if s not in declared:
                self.error(where, f"槽 {s!r} 未在领域 {domain} 声明")
            elif v is not None and not slot_form(domain, s, v):
                self.error(where, f"槽 {s}={v!r} 不合语法 {sorted(declared[s]['forms'])}")

    def node(self, where, entry) -> dict | None:
        """paper 与新对象：Label、必填字段、桩节点规则、标识与精确键。"""
        labels, props = entry.get("labels") or [], dict(entry.get("properties") or {})
        if len(labels) != 2 or labels[0] not in REQUIRED or labels[1] not in KINDS[labels[0]]:
            self.error(where, f"labels 应为 [主 Label, kind]，实际是 {labels}")
            return None
        family, kind = labels
        stub = bool(entry.get("stub"))
        if "id" in props:
            self.error(where, "不应自带 id，id 由入库分配")
        if not props.get("name"):
            self.error(where, "缺 name")
            return None
        required = REQUIRED[family]
        if stub and props.get(required):
            self.error(where, f"桩节点不写 {required}（extraction_principles.md §3）")
        if not stub and not props.get(required):
            self.error(where, f"不是桩节点，缺 {required}")
        if bad := [k for k, v in props.items() if not scalar_or_list(v)]:
            self.error(where, f"属性 {bad} 不是标量或标量列表")
        for i in props.get("identifiers", []):
            ns, sep, value = i.partition(":")
            if not (sep and value and ns in NAMESPACES):
                self.error(where, f"标识 {i!r} 不是已声明命名空间的 <namespace>:<value>")
        keys = {}
        for s in [props["name"], *props.get("aliases", [])]:
            keys.setdefault(name_key(s, kind), s)
        rejected = entry.get("rejected", [])
        if not isinstance(rejected, list) or not all(isinstance(x, str) for x in rejected):
            self.error(where, "rejected 应为对象 id 列表")
        return {"labels": labels, "family": family, "kind": kind, "stub": stub, "keys": keys, "rejected": rejected,
                "props": {k: v for k, v in props.items() if k != "aliases"}}

    # ── 编译 ──

    def run(self) -> dict:
        raw = self.raw
        if raw.get("form") != FORM_VERSION:
            self.error("form", f"表单版本应为 {FORM_VERSION}，实际是 {raw.get('form')!r}")
        if extra := {k for k in raw if not k.startswith("x-")} - TOP_KEYS:
            self.error("表单", f"未知字段 {sorted(extra)}")
        domain = raw.get("domain")
        if domain not in DOMAINS:
            self.error("domain", f"未知领域 {domain!r}，已声明 {sorted(DOMAINS)}")
            return {}

        material = self.material(raw.get("material") or {})
        nodes, refs, fills = {}, {}, {}
        if paper := self.node("paper", raw.get("paper") or {}):
            if paper["kind"] != "Paper":
                self.error("paper", "paper 的 kind 应为 Paper")
            nodes["paper"] = paper
        for ref, spec in (raw.get("refs") or {}).items():
            refs[ref] = self.ref(f"refs.{ref}", spec)
        for ref, entry in (raw.get("objects") or {}).items():
            where = f"objects.{ref}"
            if ref in refs or ref == "paper":
                self.error(where, "ref 与 refs 或 paper 重名")
            if "fill" in entry:
                fills[ref] = self.fill(where, entry)
            elif n := self.node(where, entry):
                nodes[ref] = n
        key_owner = {}
        for ref, n in nodes.items():   # 批内两个对象注册同一精确键，逐条查库发现不了
            for k in n["keys"]:
                if key_owner.setdefault(k, ref) != ref:
                    self.error(f"objects.{ref}", f"精确键 {k!r} 同时出现在 {key_owner[k]} 与 {ref}")

        bindable = set(refs) | set(nodes) | set(fills)
        rels = []
        for i, r in enumerate(raw.get("relationships") or []):
            where = f"relationships[{i}]"
            if r.get("type") not in REL_RULES:
                self.error(where, f"关系类型 {r.get('type')!r} 不在 {sorted(REL_RULES)}")
            elif not {r.get("from"), r.get("to")} <= bindable:
                self.error(where, f"端点 {r.get('from')} / {r.get('to')} 不在 refs 或 objects 中")
            else:
                rels.append((r["from"], r["type"], r["to"]))

        experiments = [self.experiment(exp, domain, refs, bindable) for exp in raw.get("experiments") or []]
        anchors = [e["anchor"] for e in experiments if e]
        if len(anchors) != len(set(anchors)):
            self.error("experiments", f"主锚点重复 {anchors}")
        return {"name": self.name, "form": FORM_VERSION, "domain": domain, "material": material,
                "nodes": nodes, "refs": refs, "fills": fills, "rels": rels,
                "experiments": [e for e in experiments if e], "coverage": anchors}

    def material(self, m: dict) -> dict:
        path = DATA / str(m.get("path", ""))
        if not m.get("path") or not path.is_file():
            self.error("material", f"材料不存在：{m.get('path')!r}（相对 {DATA}）")
            return {}
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if m.get("sha256") and m["sha256"] != sha:
            self.error("material", f"内容哈希不符：表单 {m['sha256'][:12]}…，文件 {sha[:12]}…")
        self.lines = data.decode("utf-8").splitlines()
        return {"path": m["path"], "sha256": sha}

    def ref(self, where, spec: dict) -> dict:
        if "mention" in spec:
            if FAMILY.get(spec.get("kind")) not in REQUIRED:
                self.error(where, f"kind {spec.get('kind')!r} 未知")
            if extra := set(spec) - {"mention", "kind"}:
                self.error(where, f"未知字段 {sorted(extra)}")
            return {"mention": spec.get("mention"), "kind": spec.get("kind")}
        if "id" in spec:
            kind = KIND_OF_PREFIX.get(str(spec["id"]).rpartition("_")[0])
            if not kind:
                self.error(where, f"id {spec['id']!r} 的前缀不对应任何 kind")
            if spec.get("register") and not spec.get("printed"):
                self.error(where, "register 需要 printed：注册的是原文印的称呼")
            if extra := set(spec) - {"id", "printed", "register"}:
                self.error(where, f"未知字段 {sorted(extra)}")
            return {"id": spec["id"], "kind": kind, "printed": spec.get("printed"), "register": bool(spec.get("register"))}
        self.error(where, "引用应为 {mention, kind} 或 {id, printed?, register?}")
        return {}

    def fill(self, where, entry: dict) -> dict:
        target, props = entry["fill"], dict(entry.get("properties") or {})
        if not isinstance(target, dict) or not ({"id"} <= set(target) or {"mention", "kind"} <= set(target)):
            self.error(where, "fill 应为 {id} 或 {mention, kind}")
        if not props:
            self.error(where, "fill 没有要补的属性")
        if "name" in props or "id" in props:
            self.error(where, "fill 不改 name 与 id")
        return {"target": target, "props": props}

    def experiment(self, exp: dict, domain: str, refs: dict, bindable: set) -> dict | None:
        where = f"experiments.{exp.get('ref')}"
        if extra := {k for k in exp if not k.startswith("x-")} - EXP_KEYS:
            self.error(where, f"未知字段 {sorted(extra)}")
        anchor = exp.get("anchor")
        if not anchor or not any(f'id="{anchor}"' in line for line in self.lines):
            self.error(where, f"主锚点 {anchor!r} 不在材料中")
            return None
        for k in ("section", "text", "task"):
            if not exp.get(k):
                self.error(where, f"缺 {k}")
        if exp.get("task") and exp["task"] not in bindable:
            self.error(where, f"task {exp['task']!r} 不在 refs 或 objects 中")
        lo, hi = (exp.get("lines") or [0, 0])
        if not 1 <= lo <= hi <= len(self.lines):
            self.error(where, f"lines {exp.get('lines')} 超出材料范围")

        declared = DOMAINS[domain]["slots"]
        table_slots = dict(exp.get("slots") or {})
        self.slots(where, domain, table_slots)
        basis = dict(exp.get("slot_basis") or {})
        for s, loc in basis.items():
            self.locator(f"{where}.slot_basis.{s}", loc)

        # 列：列标识为变体标签，没有标签时用被测对象
        cols, roles = [], {}
        for i, c in enumerate(exp.get("columns") or []):
            w = f"{where}.columns[{i}]"
            if extra := set(c) - COL_KEYS:
                self.error(w, f"未知字段 {sorted(extra)}")
            subj = c.get("subject")
            if subj not in bindable:
                self.error(w, f"subject {subj!r} 不在 refs 或 objects 中")
            if c.get("role") not in ROLES:
                self.error(w, f"role 应为 {sorted(ROLES)}")
            if roles.setdefault(subj, c.get("role")) != c.get("role"):
                self.error(w, f"{subj} 在同一实验中既是 {roles[subj]} 又是 {c.get('role')}")
            for m in c.get("metrics") or []:
                if m not in bindable:
                    self.error(w, f"指标 {m!r} 不在 refs 或 objects 中")
            origin = c.get("origin", "unstated")
            origin = origin if isinstance(origin, dict) else {"kind": origin}
            if origin.get("kind") not in ORIGINS:
                self.error(w, f"origin 应为 {sorted(ORIGINS)}")
            if origin.get("kind") in ("rerun", "cited"):
                if not origin.get("basis"):
                    self.error(w, f"origin={origin['kind']} 必须给出原文依据 basis")
                else:
                    self.locator(w, origin["basis"])
                if origin["kind"] == "cited" and not origin.get("from"):
                    self.error(w, "origin=cited 必须写明转引出处 from")
            self.slots(w, domain, c.get("slots") or {})
            cols.append({**c, "id": c.get("variant") or subj, "origin": origin})
        col_ids = [c["id"] for c in cols]
        if len(col_ids) != len(set(col_ids)):
            self.error(where, f"列标识重复 {col_ids}")
        cells_per_row = [(c, m) for c in cols for m in c.get("metrics") or []]

        results, seen, printed = [], set(), None
        for row in exp.get("rows") or []:
            line = row.get("line")
            w = f"{where} 第 {line} 行"
            if extra := set(row) - ROW_KEYS - set(declared):
                self.error(w, f"未知字段 {sorted(extra)}")
            if row.get("data") not in refs:
                self.error(w, f"data {row.get('data')!r} 不在 refs 中")
            if not isinstance(line, int) or not 1 <= line <= len(self.lines):
                self.error(w, "line 超出材料范围")
                continue
            values = [str(v) for v in row.get("values") or []]
            if len(values) != len(cells_per_row):
                self.error(w, f"values 有 {len(values)} 个，列 × 指标为 {len(cells_per_row)} 个")
                continue
            # 锚点核对：原文这一行的数值与行级槽值必须与表单一致
            cells = md_cells(self.lines[line - 1])
            labels, got = cells[:len(cells) - len(values)], cells[len(cells) - len(values):]
            if got != values:
                diff = [(v, g) for v, g in zip(values, got) if v != g][:3]
                self.error(w, f"数值与原文不符（表单, 原文）：{diff}")
            row_slots = {s: row[s] for s in declared if s in row}
            self.slots(w, domain, row_slots)
            for s, v in row_slots.items():
                if declared[s]["row_label"] and v is not None and str(v) not in labels:
                    self.error(w, f"行级槽 {s}={v!r} 不在原文这一行的标签 {labels} 中")
            printed = (labels[0] if labels and labels[0] else printed)
            ref = refs.get(row.get("data"), {})
            said = ref.get("mention") or ref.get("printed")
            if printed and said and normalize(printed) != normalize(said):
                self.pending(w, f"原文印的数据名 {printed!r} 与引用称呼 {said!r} 不同，确认是否同一对象")
            if bad := set(row.get("cells") or {}) - set(col_ids):
                self.error(w, f"cells 引用了不存在的列 {sorted(bad)}")
            for (c, metric), raw_value in zip(cells_per_row, values):
                cell = dict((row.get("cells") or {}).get(c["id"]) or {})
                self.slots(w, domain, cell)
                col_slots = dict(c.get("slots") or {})
                for s in (set(col_slots) & set(row_slots)) - set(cell):
                    self.error(w, f"列 {c['id']} 与行同时给了槽 {s}，需要格级覆盖")
                merged = {s: None for s in declared} | table_slots | col_slots | row_slots | cell
                slots = {s: v for s, v in merged.items() if s in declared}   # 未声明的槽已在上面报错
                for s, v in slots.items():
                    form = slot_form(domain, s, v)
                    if form is None:
                        self.error(w, f"列 {c['id']} 的槽 {s}={v!r} 不合语法 {sorted(declared[s]['forms'])}")
                    elif form == "convention" and s not in basis:
                        self.error(where, f"槽 {s} 映射到切分约定，须在 slot_basis 中给出原文依据")
                key = (c["subject"], c.get("variant"), row.get("data"), metric, *(slots[s] for s in sorted(declared)))
                if key in seen:
                    self.error(w, f"行键重复 {key}")
                seen.add(key)
                results.append({"subject": c["subject"], "variant": c.get("variant"), "role": c.get("role"),
                                "data": row.get("data"), "metric": metric, "slots": slots,
                                "value": raw_value, "value_num": float(raw_value) if NUMBER.fullmatch(raw_value) else None,
                                "origin": c["origin"]["kind"], "origin_basis": c["origin"].get("basis"),
                                "origin_from": c["origin"].get("from"), "note": row.get("note"),
                                "locator": f"{exp.get('section')}::{line}:{line}"})

        participants = {"evaluates": sorted(roles.items()),
                        "uses": sorted({r["data"] for r in results}),
                        "measured_by": sorted({r["metric"] for r in results})}
        return {"ref": exp.get("ref"), "anchor": anchor, "section": exp.get("section"), "lines": exp.get("lines"),
                "task": exp.get("task"), "text": exp.get("text"), "setting": exp.get("setting"),
                "slot_basis": basis, "participants": participants, "results": results}


def compile_form(path) -> tuple[dict, list[dict]]:
    path = Path(path)
    c = Compiler(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, path.stem)
    delta = c.run()
    return delta, c.issues


def summary(delta: dict, issues: list[dict]) -> str:
    lines = [f"== {delta.get('name', '?')} =="]
    if delta:
        new = [n["props"]["name"] + ("（桩）" if n["stub"] else "") for n in delta["nodes"].values()]
        lines += [f"新对象 {len(new)}：{', '.join(new)}",
                  f"引用 {len(delta['refs'])} · 补全 {len(delta['fills'])} · 关系 {len(delta['rels'])}"]
        for e in delta["experiments"]:
            lines.append(f"实验 {e['anchor']}：结果行 {len(e['results'])}，被测对象 {e['participants']['evaluates']}")
    errors = [i for i in issues if i["level"] == "error"]
    pend = [i for i in issues if i["level"] == "pending"]
    lines.append(f"错误 {len(errors)} · 待确认 {len(pend)}")
    lines += [f"  [{i['level']}] {i['where']}：{i['msg']}" for i in issues]
    return "\n".join(lines)


def main(argv) -> int:
    failed = False
    for p in argv:
        delta, issues = compile_form(p)
        print(summary(delta, issues))
        failed |= any(i["level"] == "error" for i in issues)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
