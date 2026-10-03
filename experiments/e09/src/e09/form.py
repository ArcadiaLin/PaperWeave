"""论文表单编译：表单 → delta（docs/designs/v2/commit_contract.md §1、§4）。

compile 不查库，只看表单、材料文件与领域配置；同一表单与材料必得同一结果。问题分两级：
- error：表单自身写错（结构、条件语法、锚点或依据定位不在材料中……），由 Agent 改表单；
- pending：需要 Agent 确认（表单写的称呼在原文表格范围内找不到）。
入库是报告级：只存实验在哪张表、比了谁、在哪些数据集与指标上、实验级条件；数值留在原文，比较时按锚点读取。
引用解析、查重、冲突与幂等在 Commit 的 dry_run 中判定，不在这里。

    uv run python -m e09.form <表单.yml> ...    # 打印编译摘要与问题；有 error 时返回非零
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

from .config import DATA
from .utils.domain import DOMAINS, condition_form
from .utils.namekey import name_key
from .utils.schema import FAMILY, KINDS, NAMESPACES, PREFIX, REL_RULES, REQUIRED

FORM_VERSION = "paper-form-v2"
TOP_KEYS = {"form", "domain", "material", "paper", "refs", "objects", "relationships", "experiments"}
EXP_KEYS = {"ref", "anchor", "section", "lines", "task", "text", "setting", "note",
            "conditions", "condition_basis", "participants", "data", "metrics"}
PART_KEYS = {"subject", "role", "variants", "origin"}
ROLES = {"target", "baseline"}
ORIGINS = {"own", "rerun", "cited", "unstated"}
LOCATOR = re.compile(r"(?P<section>.+)::(?P<start>\d+):(?P<end>\d+)")   # <章节>::<start>:<end>，行号从 1 起
EMPHASIS = re.compile(r"[*_$\\]")   # 核对称呼前去掉 Markdown 强调与公式记号：*DLinear*-S → DLinear-S
KIND_OF_PREFIX = {p: k for k, p in PREFIX.items()}


def scalar_or_list(v) -> bool:
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v))


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

        # 每个 ref 在原文中可能的称呼：引用写的 mention / printed；新对象的 name 与 aliases
        names = {r: [spec.get("mention") or spec.get("printed")] for r, spec in refs.items()}
        names |= {r: list(n["keys"].values()) for r, n in nodes.items()}
        names |= {r: [f["target"].get("mention")] for r, f in fills.items()}
        experiments = [self.experiment(exp, domain, names, bindable) for exp in raw.get("experiments") or []]
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

    def experiment(self, exp: dict, domain: str, names: dict, bindable: set) -> dict | None:
        """报告级实验：表在哪、比了谁、在哪些数据集与指标上、实验级条件。数值留在原文（extraction_principles.md §4）。"""
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
            return None
        # 表格范围内的原文，去掉 Markdown 强调与公式记号，供称呼核对
        table = EMPHASIS.sub("", "\n".join(self.lines[lo - 1:hi])).lower()

        def printed(w, labels):
            labels = [x for x in labels or [] if x]
            if labels and not any(x.lower() in table for x in labels):
                self.pending(w, f"原文表格范围（第 {lo}–{hi} 行）中找不到 {' / '.join(map(repr, labels))}，确认称呼与绑定对象")

        # 实验级条件：规则可直接判定的部分；其余写进 setting
        declared = DOMAINS[domain]["conditions"]
        conditions = {c: None for c in declared} | dict(exp.get("conditions") or {})
        basis = dict(exp.get("condition_basis") or {})
        for c, v in conditions.items():
            form = condition_form(domain, c, v) if c in declared else None
            if c not in declared:
                self.error(where, f"条件 {c!r} 未在领域 {domain} 声明")
            elif form is None:
                self.error(where, f"条件 {c}={v!r} 不合语法 {sorted(declared[c])}")
            elif form == "convention" and c not in basis:
                self.error(where, f"条件 {c} 映射到切分约定，须在 condition_basis 中给出原文依据")
        for c, loc in basis.items():
            self.locator(f"{where}.condition_basis.{c}", loc)

        participants = []
        for i, part in enumerate(exp.get("participants") or []):
            w = f"{where}.participants[{i}]"
            if extra := set(part) - PART_KEYS:
                self.error(w, f"未知字段 {sorted(extra)}")
            subj = part.get("subject")
            if subj not in bindable:
                self.error(w, f"subject {subj!r} 不在 refs 或 objects 中")
            if subj in {x["subject"] for x in participants}:
                self.error(w, f"{subj} 在同一实验中重复出现；变体写进 variants")
            if part.get("role") not in ROLES:
                self.error(w, f"role 应为 {sorted(ROLES)}")
            variants = part.get("variants") or []
            if not isinstance(variants, list) or not all(isinstance(v, str) for v in variants):
                self.error(w, "variants 应为原文印的变体标签列表")
                variants = []
            origin = part.get("origin", "unstated")
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
            for labels in [[v] for v in variants] or [names.get(subj)]:
                printed(w, labels)
            participants.append({"subject": subj, "role": part.get("role"), "variants": variants,
                                 "origin": origin.get("kind"), "origin_basis": origin.get("basis"),
                                 "origin_from": origin.get("from")})
        if not any(x["role"] == "target" for x in participants):
            self.error(where, "至少要有一个 role=target 的被测对象")

        for field_ in ("data", "metrics"):
            refs_ = exp.get(field_) or []
            if not refs_:
                self.error(where, f"缺 {field_}")
            if len(refs_) != len(set(refs_)):
                self.error(where, f"{field_} 有重复")
            for r in refs_:
                if r not in bindable:
                    self.error(where, f"{field_} 中的 {r!r} 不在 refs 或 objects 中")
                else:
                    printed(f"{where}.{field_}", names.get(r))

        return {"ref": exp.get("ref"), "anchor": anchor, "section": exp.get("section"), "lines": [lo, hi],
                "task": exp.get("task"), "text": exp.get("text"), "setting": exp.get("setting"), "note": exp.get("note"),
                "conditions": conditions, "condition_basis": basis, "participants": participants,
                "data": list(exp.get("data") or []), "metrics": list(exp.get("metrics") or [])}


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
            parts = [f"{x['subject']}({x['role']}{'; ' + ','.join(x['variants']) if x['variants'] else ''})" for x in e["participants"]]
            lines.append(f"实验 {e['anchor']}：数据集 {len(e['data'])} · 指标 {len(e['metrics'])} · 被测对象 {', '.join(parts)}")
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
