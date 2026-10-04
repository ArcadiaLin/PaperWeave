"""表单编译：表单 → delta（docs/designs/v2/commit_contract.md §1、§2、§4）。

两种表单：论文表单 paper-form-v4（Compiler）写论文陈述的内容；增补表单 supplement-form-v1（SupplementCompiler）
写 Agent 形成的 Observation、Agent 认为的贡献与正反关系。compile_form 按 form 字段分派。

compile 不查库，只看表单与材料文件；同一表单与材料必得同一结果。问题分两级：
- error：表单自身写错（结构、锚点或定位不在材料中……），由 Agent 改表单；
- pending：需要 Agent 确认（称呼在实验的行范围内找不到、实验描述里出现数值）。
  Agent 判断无误时在顶层 `x-confirmed: [{rule, where}]` 中列出，该项降为 confirmed，不再阻塞，照样记入批次记录。
每个问题带稳定的规则码 rule，Agent 按它决定怎么改。
入库只到实验级：实验按研究问题分组，存描述、锚点与参与关系；主张与自述贡献同样只存描述、锚点与关联。
数值、条件与变体留在原文，按锚点读取（extraction_principles.md §4、§9）。
引用解析、查重、冲突与幂等在 Commit 的 dry_run 中判定，不在这里。

    uv run python -m e09.form <表单.yml> ...    # 打印编译摘要与问题；有 error 时返回非零（两种表单都可）
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

from .config import DATA
from .utils.namekey import name_key
from .utils.schema import FAMILY, KINDS, NAMESPACES, PAPER_RELS, PREFIX, REQUIRED, STANCE_KINDS, STANCE_RELS

FORM_VERSION = "paper-form-v4"
SUPPLEMENT_VERSION = "supplement-form-v1"
TOP_KEYS = {"form", "material", "paper", "refs", "objects", "relationships", "experiments", "claims", "contributions"}
EXP_KEYS = {"anchors", "locators", "task", "text", "participants", "data", "benchmark"}
PART_KEYS = {"subject", "role"}
CONTENT_KEYS = {"Claim": {"key", "text", "locators", "about", "supported_by"},
                "Contribution": {"key", "text", "locators", "about"}}
REL_KEYS = {"from", "type", "to", "basis", "description"}
SUPPLEMENT_KEYS = {"form", "formed_by", "refs", "observations", "contributions", "relationships"}
SUPPLEMENT_RECORD_KEYS = {"Observation": {"text", "about", "basis"}, "Contribution": {"paper", "text", "about", "basis"}}
ROLES = {"target", "baseline"}
LOCATOR = re.compile(r"(?P<section>.+)::(?P<start>\d+):(?P<end>\d+)")   # <章节>::<start>:<end>，行号从 1 起
REFERENCES = re.compile(r"#+\s*(References|Bibliography)\s*", re.I)   # 参考文献节的标题
EMPHASIS = re.compile(r"[*_$\\]")   # 核对称呼前去掉 Markdown 强调与公式记号：*DLinear*-S → DLinear-S
DECIMAL = re.compile(r"\d+\.\d+")   # 实验描述不转录数值（extraction_principles.md §4）
KIND_OF_PREFIX = {p: k for k, p in PREFIX.items()}
CONFIRMABLE = {"name-not-in-range", "decimal-in-text"}   # 只能由 Agent 表态消除的待确认项


def scalar_or_list(v) -> bool:
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v))


def str_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


class Compiler:
    def __init__(self, raw: dict, name: str):
        self.raw, self.name = raw, name
        self.issues = []
        self.lines = []
        self.kinds = {}   # ref -> kind，run 中填写

    def error(self, where, msg, rule="form"):
        self._add("error", where, msg, rule)

    def pending(self, where, msg, rule):
        self._add("pending", where, msg, rule)

    def _add(self, level, where, msg, rule):
        issue = {"level": level, "rule": rule, "where": where, "msg": msg}
        if issue not in self.issues:   # 同一问题在多处出现时只报一次
            self.issues.append(issue)

    # ── 共用检查 ──

    def locator(self, where, loc, lines=None) -> tuple[int, int] | None:
        """lines：定位所在材料的行；默认是本表单的 material。"""
        lines = self.lines if lines is None else lines
        m = LOCATOR.fullmatch(loc) if isinstance(loc, str) else None
        if not m:
            self.error(where, f"定位 {loc!r} 应为 <章节>::<start>:<end>")
            return None
        start, end = int(m["start"]), int(m["end"])
        if not 1 <= start <= end <= len(lines):
            self.error(where, f"定位 {loc!r} 超出材料范围（共 {len(lines)} 行）")
            return None
        return start, end

    def locators(self, where, locs, lines=None) -> list[tuple[int, int]]:
        """非空定位列表；返回有效的行范围。"""
        if not str_list(locs) or not locs:
            self.error(where, "locators 应为非空的定位列表")
            return []
        return [span for loc in locs if (span := self.locator(where, loc, lines))]

    def anchor_line(self, anchor) -> int | None:
        """锚点所在行（从 1 起）；材料中没有时返回 None。"""
        return next((i + 1 for i, line in enumerate(self.lines) if f'id="{anchor}"' in line), None)

    def references_block(self) -> tuple[int, int] | None:
        """参考文献节的行范围：从标题行到下一个同级或更高级标题之前。"""
        for i, line in enumerate(self.lines):
            if REFERENCES.fullmatch(line.strip()):
                level = len(line) - len(line.lstrip("#"))
                end = next((j for j in range(i + 1, len(self.lines))
                            if self.lines[j].startswith("#") and len(self.lines[j]) - len(self.lines[j].lstrip("#")) <= level),
                           len(self.lines))
                return i + 1, end
        return None

    def text_in(self, spans) -> str:
        """行范围内的原文，去掉 Markdown 强调与公式记号，供称呼核对。"""
        return EMPHASIS.sub("", "\n".join("\n".join(self.lines[a - 1:b]) for a, b in spans)).lower()

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
        self.identifiers(where, props)
        keys = {}
        for s in [props["name"], *props.get("aliases", [])]:
            keys.setdefault(name_key(s, kind), s)
        rejected = entry.get("rejected", [])
        if not isinstance(rejected, list) or not all(isinstance(x, str) for x in rejected):
            self.error(where, "rejected 应为对象 id 列表")
        return {"labels": labels, "family": family, "kind": kind, "stub": stub, "keys": keys, "rejected": rejected,
                "props": {k: v for k, v in props.items() if k != "aliases"}}

    def identifiers(self, where, props):
        for i in props.get("identifiers", []):
            ns, sep, value = i.partition(":")
            if not (sep and value and ns in NAMESPACES):
                self.error(where, f"标识 {i!r} 不是已声明命名空间的 <namespace>:<value>")

    # ── 编译 ──

    def run(self) -> dict:
        raw = self.raw
        if raw.get("form") != FORM_VERSION:
            self.error("form", f"表单版本应为 {FORM_VERSION}，实际是 {raw.get('form')!r}")
        if extra := {k for k in raw if not k.startswith("x-")} - TOP_KEYS:
            self.error("表单", f"未知字段 {sorted(extra)}")

        material = self.material(raw.get("material") or {})
        nodes, refs, fills = {}, {}, {}
        paper_entry = raw.get("paper") or {}
        if "fill" in paper_entry:   # 本文已有桩节点：dry_run 列出相似节点后，经确认补全它（commit_contract.md §2.1）
            fills["paper"] = self.paper_fill(paper_entry)
        elif paper := self.node("paper", paper_entry):
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
                if n["kind"] == "Paper" and not n["stub"]:
                    self.error(where, "其他论文只建桩节点（单篇深度）：被引论文入库时再补全")
                nodes[ref] = n
        key_owner = {}
        for ref, n in nodes.items():   # 批内两个对象注册同一精确键，逐条查库发现不了
            for k in n["keys"]:
                if key_owner.setdefault(k, ref) != ref:
                    self.error(f"objects.{ref}", f"精确键 {k!r} 同时出现在 {key_owner[k]} 与 {ref}")

        bindable = set(refs) | set(nodes) | set(fills)
        self.kinds = {r: spec.get("kind") for r, spec in refs.items()} | {r: n["kind"] for r, n in nodes.items()}
        self.kinds |= {r: f["target"].get("kind") or KIND_OF_PREFIX.get(str(f["target"].get("id", "")).rpartition("_")[0])
                       for r, f in fills.items()}
        rels = [rel for i, r in enumerate(raw.get("relationships") or []) if (rel := self.relationship(f"relationships[{i}]", r))]

        # 每个 ref 在原文中可能的称呼：引用写的 mention / printed；新对象的 name 与 aliases
        names = {r: [spec.get("mention") or spec.get("printed")] for r, spec in refs.items()}
        names |= {r: list(n["keys"].values()) for r, n in nodes.items()}
        names |= {r: [f["target"].get("mention")] for r, f in fills.items()}
        experiments = [e for i, exp in enumerate(raw.get("experiments") or [])
                       if (e := self.experiment(f"experiments[{i}]", exp, names, bindable))]
        primary = [e["anchors"][0] for e in experiments]
        if dup := sorted({a for a in primary if primary.count(a) > 1}):
            self.error("experiments", f"主锚点重复 {dup}")
        contents = [c for kind, field_ in (("Claim", "claims"), ("Contribution", "contributions"))
                    for c in self.contents(kind, field_, raw.get(field_) or [], bindable, set(primary))]
        coverage = list(dict.fromkeys(a for e in experiments for a in e["anchors"]))
        confirmed = self.confirm(raw.get("x-confirmed") or [])
        return {"name": self.name, "form": FORM_VERSION, "material": material,
                "nodes": nodes, "refs": refs, "fills": fills, "rels": rels,
                "experiments": experiments, "contents": contents, "coverage": coverage, "confirmed": confirmed}

    def confirm(self, items) -> list[dict]:
        """x-confirmed：Agent 对可表态的待确认项逐条确认；列出的项必须正好对应一条待确认项。"""
        if not isinstance(items, list) or not all(isinstance(x, dict) and set(x) == {"rule", "where"} for x in items):
            self.error("x-confirmed", "应为 [{rule, where}] 列表", rule="confirm-format")
            return []
        out = []
        for x in items:
            if x["rule"] not in CONFIRMABLE:
                self.error("x-confirmed", f"{x['rule']!r} 不能靠确认消除，只能确认 {sorted(CONFIRMABLE)}", rule="confirm-not-allowed")
                continue
            hit = [i for i in self.issues if i["level"] == "pending" and i["rule"] == x["rule"] and i["where"] == x["where"]]
            if not hit:
                self.error("x-confirmed", f"{x} 没有对应的待确认项，删去这条确认", rule="confirm-unused")
            for i in hit:
                i["level"] = "confirmed"
                out.append(i)
        return out

    def relationship(self, where, r: dict) -> dict | None:
        """论文表单中的关系：只有本文 → 被引论文的 CITES，选择性写入，须有引用上下文。"""
        if extra := set(r) - REL_KEYS:
            self.error(where, f"未知字段 {sorted(extra)}")
        if r.get("type") not in PAPER_RELS:
            self.error(where, f"论文表单只能写 {sorted(PAPER_RELS)}，实际是 {r.get('type')!r}；方法间关系不在单篇抽取中包办")
            return None
        ok = True
        if r.get("from") != "paper":
            self.error(where, "CITES 的起点只能是本文 paper")
            ok = False
        if self.kinds.get(r.get("to")) != "Paper":
            self.error(where, f"终点 {r.get('to')!r} 应为 refs 或 objects 中的 Paper")
            ok = False
        basis = r.get("basis")
        if not isinstance(basis, list) or not basis:
            self.error(where, "须给出依据 basis：定位列表，至少含一处引用上下文")
            return None
        spans = [span for loc in basis if (span := self.locator(where, loc))]
        refs_block = self.references_block()
        if len(spans) == len(basis) and refs_block and all(refs_block[0] <= a and b <= refs_block[1] for a, b in spans):
            self.error(where, "basis 只有参考文献条目：至少要有一处正文中的引用上下文")
        if r.get("description") is not None and not isinstance(r["description"], str):
            self.error(where, "description 应为文本")
        return {"from": "paper", "type": r["type"], "to": r["to"], "basis": basis,
                "description": r.get("description")} if ok else None

    def material(self, m: dict) -> dict:
        info, self.lines = self.load_material("material", m)
        return info

    def load_material(self, where, m: dict) -> tuple[dict, list[str]]:
        """材料文件：路径相对 DATA；返回 ({path, sha256}, 行)，不存在时为 ({}, [])。"""
        path = DATA / str(m.get("path", ""))
        if not m.get("path") or not path.is_file():
            self.error(where, f"材料不存在：{m.get('path')!r}（相对 {DATA}）")
            return {}, []
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if m.get("sha256") and m["sha256"] != sha:
            self.error(where, f"内容哈希不符：表单 {m['sha256'][:12]}…，文件 {sha[:12]}…")
        return {"path": m["path"], "sha256": sha}, data.decode("utf-8").splitlines()

    def ref(self, where, spec: dict) -> dict:
        if "mention" in spec:
            if FAMILY.get(spec.get("kind")) not in REQUIRED:
                self.error(where, f"kind {spec.get('kind')!r} 未知")
            if extra := set(spec) - {"mention", "kind"}:
                self.error(where, f"未知字段 {sorted(extra)}")
            return {"mention": spec.get("mention"), "kind": spec.get("kind")}
        if "id" in spec:
            kind = KIND_OF_PREFIX.get(str(spec["id"]).rpartition("_")[0])
            if FAMILY.get(kind) not in REQUIRED:
                self.error(where, f"id {spec['id']!r} 的前缀不对应任何 Entity / Concept kind")
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
        return {"target": target, "props": props, "keys": {}}

    def paper_fill(self, entry: dict) -> dict:
        """paper 写 fill：补全已有的 Paper 桩节点。本文印的标题可经 aliases 注册为该节点的称呼。"""
        target, props = entry["fill"], dict(entry.get("properties") or {})
        if not isinstance(target, dict) or set(target) != {"id"} or KIND_OF_PREFIX.get(str(target["id"]).rpartition("_")[0]) != "Paper":
            self.error("paper", "paper 的 fill 应为 {id: <Paper id>}")
        if "name" in props or "id" in props:
            self.error("paper", "fill 不改 name 与 id；本文印的标题写进 aliases")
        if bad := [k for k, v in props.items() if not scalar_or_list(v)]:
            self.error("paper", f"属性 {bad} 不是标量或标量列表")
        self.identifiers("paper", props)
        aliases = props.pop("aliases", [])
        if not str_list(aliases):
            self.error("paper", "aliases 应为称呼列表")
            aliases = []
        if not props and not aliases:
            self.error("paper", "fill 没有要补的属性")
        return {"target": dict(target, kind="Paper"), "props": props, "keys": {name_key(a, "Paper"): a for a in aliases}}

    def experiment(self, where, exp: dict, names: dict, bindable: set) -> dict | None:
        """实验级：一个研究问题一项，存描述、锚点与参与关系；数值与条件留在原文（extraction_principles.md §4）。"""
        anchors = exp.get("anchors")
        if not str_list(anchors) or not anchors:
            self.error(where, "anchors 应为非空的锚点列表，第一个为主锚点")
            return None
        where = f"experiments.{anchors[0]}"
        if extra := {k for k in exp if not k.startswith("x-")} - EXP_KEYS:
            self.error(where, f"未知字段 {sorted(extra)}；条件、变体与疑点不进表单（extraction_principles.md §4、§6）")
        spans = self.locators(f"{where}.locators", exp.get("locators"))
        if len(anchors) != len(set(anchors)):
            self.error(where, f"anchors 有重复 {anchors}")
        for a in anchors:
            line = self.anchor_line(a)
            if line is None:
                self.error(where, f"锚点 {a!r} 不在材料中")
            elif spans and not any(lo <= line <= hi for lo, hi in spans):
                self.error(where, f"锚点 {a!r}（第 {line} 行）不在该实验任一 locator 的行范围内")
        for k in ("text", "task"):
            if not exp.get(k):
                self.error(where, f"缺 {k}")
        if exp.get("task") and exp["task"] not in bindable:
            self.error(where, f"task {exp['task']!r} 不在 refs 或 objects 中")
        if isinstance(exp.get("text"), str) and (nums := DECIMAL.findall(exp["text"])):
            self.pending(where, f"实验描述中出现数值 {nums}：描述不转录数值，删去或在 x-confirmed 中确认", "decimal-in-text")
        table = self.text_in(spans)

        def printed(w, labels):
            labels = [x for x in labels or [] if x]
            if spans and labels and not any(x.lower() in table for x in labels):
                self.pending(w, f"该实验的行范围内找不到 {' / '.join(map(repr, labels))}，核对称呼与绑定对象，无误时在 x-confirmed 中确认",
                             "name-not-in-range")

        participants = []
        for i, part in enumerate(exp.get("participants") or []):
            w = f"{where}.participants[{i}]"
            if extra := set(part) - PART_KEYS:
                self.error(w, f"未知字段 {sorted(extra)}；变体、来源性质不进表单（extraction_principles.md §2、§5）")
            subj = part.get("subject")
            if subj not in bindable:
                self.error(w, f"subject {subj!r} 不在 refs 或 objects 中")
            if subj in {x["subject"] for x in participants}:
                self.error(w, f"{subj} 在同一实验中重复出现")
            if part.get("role") not in ROLES:
                self.error(w, f"role 应为 {sorted(ROLES)}")
            printed(w, names.get(subj))
            participants.append({"subject": subj, "role": part.get("role")})
        if not any(x["role"] == "target" for x in participants):
            self.error(where, "至少要有一个 role=target 的被测对象")

        data = exp.get("data") or []
        if not data:
            self.error(where, "缺 data")
        if len(data) != len(set(data)):
            self.error(where, "data 有重复")
        for r in data:
            if r not in bindable:
                self.error(where, f"data 中的 {r!r} 不在 refs 或 objects 中")
            else:
                printed(f"{where}.data", names.get(r))
        bench = exp.get("benchmark")
        if bench is not None:
            if bench not in bindable:
                self.error(where, f"benchmark {bench!r} 不在 refs 或 objects 中")
            elif self.kinds.get(bench) not in (None, "Benchmark"):
                self.error(where, f"benchmark {bench!r} 的 kind 是 {self.kinds[bench]}，应为 Benchmark")

        return {"anchors": list(anchors), "locators": list(exp.get("locators") or []), "task": exp.get("task"),
                "text": exp.get("text"), "participants": participants, "data": list(data), "benchmark": bench}

    def contents(self, kind: str, field_: str, items: list, bindable: set, primary: set) -> list[dict]:
        """主张与自述贡献：短键、描述、正文定位与关联对象；主张另有本文实验的依据（extraction_principles.md §9）。"""
        out, keys = [], set()
        for i, c in enumerate(items):
            where = f"{field_}[{i}]"
            if not isinstance(c, dict):
                self.error(where, "应为映射")
                continue
            if extra := {k for k in c if not k.startswith("x-")} - CONTENT_KEYS[kind]:
                self.error(where, f"未知字段 {sorted(extra)}")
            key = c.get("key")
            if not isinstance(key, str) or not key:
                self.error(where, "缺 key：本文内唯一的短键")
                continue
            where = f"{field_}.{key}"
            if key in keys:
                self.error(where, f"key {key!r} 在 {field_} 中重复")
            keys.add(key)
            if not isinstance(c.get("text"), str) or not c["text"].strip():
                self.error(where, "缺 text")
            self.locators(f"{where}.locators", c.get("locators"))
            about = c.get("about") or []
            if not isinstance(about, list):
                self.error(where, "about 应为对象引用列表")
                about = []
            for r in about:
                if r not in bindable:
                    self.error(where, f"about 中的 {r!r} 不在 refs 或 objects 中")
            supported = c.get("supported_by") or []
            if not isinstance(supported, list):
                self.error(where, "supported_by 应为本表单实验的主锚点列表")
                supported = []
            for a in supported:
                if a not in primary:
                    self.error(where, f"supported_by 中的 {a!r} 不是本表单实验的主锚点")
            out.append({"kind": kind, "key": key, "text": c.get("text"), "locators": list(c.get("locators") or []),
                        "about": list(dict.fromkeys(about)), "supported_by": list(dict.fromkeys(supported))})
        return out


class SupplementCompiler(Compiler):
    """增补表单 supplement-form-v1（commit_contract.md §2.2）：Agent 形成的 Observation、Agent 认为的贡献与正反关系。

    不新建 Entity、Concept，不注册 alias；refs 只能引用已在库中的对象：Entity / Concept 用 {mention, kind} 或 {id}，
    Content（Claim、Experiment 等）只能用 {id}。三段都可省略，至少一段非空。formed_by 整份表单共用，formed_at 由 apply 写入。
    """

    def run(self) -> dict:
        raw = self.raw
        if raw.get("form") != SUPPLEMENT_VERSION:
            self.error("form", f"表单版本应为 {SUPPLEMENT_VERSION}，实际是 {raw.get('form')!r}")
        if extra := {k for k in raw if not k.startswith("x-")} - SUPPLEMENT_KEYS:
            self.error("表单", f"未知字段 {sorted(extra)}；增补表单不新建对象，也不注册 alias")
        formed_by = raw.get("formed_by")
        if not isinstance(formed_by, str) or not formed_by.strip():
            self.error("formed_by", "缺 formed_by：形成者，由提交的 Agent 填写")
        if not any(raw.get(k) for k in ("observations", "contributions", "relationships")):
            self.error("表单", "observations、contributions、relationships 至少一段非空")
        refs = {ref: self.ref(f"refs.{ref}", spec) for ref, spec in (raw.get("refs") or {}).items()}
        self.kinds = {r: spec.get("kind") for r, spec in refs.items()}
        observations = [o for i, x in enumerate(raw.get("observations") or [])
                        if (o := self.record("Observation", f"observations[{i}]", x))]
        contributions = [o for i, x in enumerate(raw.get("contributions") or [])
                         if (o := self.record("Contribution", f"contributions[{i}]", x))]
        for field_, items in (("observations", observations), ("contributions", contributions)):
            seen = [record_identity(o) for o in items]
            if dup := sorted({i for i, k in enumerate(seen) if seen.index(k) != i}):
                self.error(field_, f"第 {dup} 项与前面的记录重复（同一 text 与对象集合）")
        rels = [r for i, x in enumerate(raw.get("relationships") or []) if (r := self.stance(f"relationships[{i}]", x))]
        triples = [(r["from"], r["type"], r["to"]) for r in rels]
        if dup := sorted({t for t in triples if triples.count(t) > 1}):
            self.error("relationships", f"关系重复 {dup}")
        confirmed = self.confirm(raw.get("x-confirmed") or [])
        return {"name": self.name, "form": SUPPLEMENT_VERSION, "formed_by": formed_by, "refs": refs,
                "observations": observations, "contributions": contributions, "rels": rels, "confirmed": confirmed}

    def ref(self, where, spec: dict) -> dict:
        if not isinstance(spec, dict):
            self.error(where, "引用应为 {mention, kind} 或 {id}")
            return {}
        if "id" in spec:
            kind = KIND_OF_PREFIX.get(str(spec["id"]).rpartition("_")[0])
            if kind is None:
                self.error(where, f"id {spec['id']!r} 的前缀不对应任何 kind")
            if extra := set(spec) - {"id"}:
                self.error(where, f"未知字段 {sorted(extra)}；增补表单不注册 alias")
            return {"id": spec["id"], "kind": kind, "printed": None, "register": False}
        if "mention" in spec and FAMILY.get(spec.get("kind")) == "Content":
            self.error(where, f"{spec['kind']} 没有称呼，只能用 {{id}} 引用")
            return {}
        if extra := set(spec) - {"mention", "kind"}:
            self.error(where, f"未知字段 {sorted(extra)}；增补表单不注册 alias")
        return super().ref(where, {k: v for k, v in spec.items() if k in ("mention", "kind")})

    def refs_in(self, where, refs, what) -> list:
        if not isinstance(refs, list):
            self.error(where, f"{what} 应为引用列表")
            return []
        for r in refs:
            if r not in self.kinds:
                self.error(where, f"{what} 中的 {r!r} 不在 refs 中")
        return list(dict.fromkeys(refs))

    def basis(self, where, b) -> dict | None:
        """可选的材料依据 {material: <材料路径>, locators}：编译为 FROM，终点是该材料所属的论文。"""
        if b is None:
            return None
        if not isinstance(b, dict) or set(b) != {"material", "locators"}:
            self.error(where, "basis 应为 {material: <材料路径>, locators: [...]}")
            return None
        info, lines = self.load_material(where, {"path": b["material"]})
        if not info:
            return None
        self.locators(where, b["locators"], lines)
        return {"path": info["path"], "sha256": info["sha256"], "locators": list(b["locators"] or [])}

    def record(self, kind: str, where, x) -> dict | None:
        """Observation 与 Agent 认为的贡献：text、about、可选 basis；贡献另有所属论文 paper。"""
        if not isinstance(x, dict):
            self.error(where, "应为映射")
            return None
        if extra := {k for k in x if not k.startswith("x-")} - SUPPLEMENT_RECORD_KEYS[kind]:
            self.error(where, f"未知字段 {sorted(extra)}")
        if not isinstance(x.get("text"), str) or not x["text"].strip():
            self.error(where, "缺 text")
        about = self.refs_in(where, x.get("about") or [], "about")
        if kind == "Observation" and not about:
            self.error(where, "Observation 的 about 至少关联一个对象")
        paper = x.get("paper")
        if kind == "Contribution" and self.kinds.get(paper) != "Paper":
            self.error(where, f"paper 应为 refs 中的 Paper 引用，实际是 {paper!r}")
        out = {"kind": kind, "text": x.get("text"), "about": about, "basis": self.basis(f"{where}.basis", x.get("basis"))}
        return out | ({"paper": paper} if kind == "Contribution" else {})

    def stance(self, where, r) -> dict | None:
        """正反关系：SUPPORTS / OPPOSES，两端同为 Claim 或同为 Proposition，description 必填（graph_model_v2.md §6.2.2）。"""
        if not isinstance(r, dict):
            self.error(where, "应为映射")
            return None
        if extra := set(r) - {"from", "type", "to", "description"}:
            self.error(where, f"未知字段 {sorted(extra)}")
        ok = True
        if r.get("type") not in STANCE_RELS:
            self.error(where, f"增补表单的关系只能是 {sorted(STANCE_RELS)}，实际是 {r.get('type')!r}")
            ok = False
        if not isinstance(r.get("description"), str) or not r["description"].strip():
            self.error(where, "缺 description：写明支持或反对的具体内容与限定条件")
            ok = False
        a, b = r.get("from"), r.get("to")
        for end in (a, b):
            if end not in self.kinds:
                self.error(where, f"端点 {end!r} 不在 refs 中")
                ok = False
        if ok:
            ka, kb = self.kinds[a], self.kinds[b]
            if ka != kb or ka not in STANCE_KINDS:
                self.error(where, f"两端应同为 Claim 或同为 Proposition，实际是 {ka} → {kb}", rule="stance-kinds")
                ok = False
            if a == b:
                self.error(where, "起点与终点相同")
                ok = False
        return {"from": a, "type": r["type"], "to": b, "description": r["description"]} if ok else None


def record_identity(o: dict) -> tuple:
    """Observation 与 Agent 贡献没有自然键：同一形成者下按 text、对象集合（贡献另加所属论文）判重（commit_contract.md §5）。"""
    return o["kind"], o["text"], tuple(sorted(o["about"])), o.get("paper")


def compile_form(path) -> tuple[dict, list[dict]]:
    """按 form 字段选编译器；delta 带表单文件的内容哈希 form_hash，记入批次记录（commit_contract.md §6）。"""
    path = Path(path)
    data = path.read_bytes()
    raw = yaml.safe_load(data.decode("utf-8")) or {}
    c = (SupplementCompiler if raw.get("form") == SUPPLEMENT_VERSION else Compiler)(raw, path.stem)
    delta = c.run()
    if delta:
        delta["form_hash"] = hashlib.sha256(data).hexdigest()
    return delta, c.issues


def summary(delta: dict, issues: list[dict]) -> str:
    lines = [f"== {delta.get('name', '?')} =="]
    if delta.get("form") == SUPPLEMENT_VERSION:
        lines += [f"形成者 {delta['formed_by']} · 引用 {len(delta['refs'])}",
                  f"Observation {len(delta['observations'])} · Agent 贡献 {len(delta['contributions'])} · 正反关系 {len(delta['rels'])}"]
    elif delta:
        new = [n["props"]["name"] + ("（桩）" if n["stub"] else "") for n in delta["nodes"].values()]
        lines += [f"新对象 {len(new)}：{', '.join(new)}",
                  f"引用 {len(delta['refs'])} · 补全 {len(delta['fills'])} · 关系 {len(delta['rels'])}"]
        for e in delta["experiments"]:
            parts = [f"{x['subject']}({x['role']})" for x in e["participants"]]
            bench = f" · Benchmark {e['benchmark']}" if e["benchmark"] else ""
            lines.append(f"实验 {e['anchors'][0]}：锚点 {len(e['anchors'])} · 数据集 {len(e['data'])}{bench} · 被测对象 {', '.join(parts)}")
        for kind in ("Claim", "Contribution"):
            items = [c for c in delta["contents"] if c["kind"] == kind]
            if items:
                lines.append(f"{kind} {len(items)}：{', '.join(c['key'] for c in items)}")
    errors = [i for i in issues if i["level"] == "error"]
    pend = [i for i in issues if i["level"] == "pending"]
    lines.append(f"错误 {len(errors)} · 待确认 {len(pend)} · 已确认 {sum(i['level'] == 'confirmed' for i in issues)}")
    lines += [f"  [{i['level']}] {i['rule']} @ {i['where']}：{i['msg']}" for i in issues]
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
