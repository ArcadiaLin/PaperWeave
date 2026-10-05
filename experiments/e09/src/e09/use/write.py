"""Agent 算子的共同写入路径（docs/designs/v2/operators.md §4.1、§5）：校验 → 文档 → 一次提交。

    write_artifact(store, request, at=…) -> {artifact-result, status, artifact, commit, document, warnings, render}

请求是 ``{op, title?, abs, inputs, params, payload, session, formed_by}``。

1. **共同校验**，任一不过即整次拒绝、不写入（:class:`OperatorError`）：

   - ``inputs`` 中的对象引用、Artifact 与记录引用都在库中；来源引用格式正确，所指材料在库中、文件与登记的哈希
     一致、行号不越界；
   - ``params`` 与 ``payload`` 符合该算子的 schema，判断类的每个单元恰有一条判断（:mod:`e09.use.operators`）；
   - ``params`` 与 ``payload`` 中出现的每个引用都属于 ``inputs``。来源引用的开头写材料 id 或材料所属的节点 id
     都算同一个引用；文档头部的 ``nodes_used`` 统一写成材料 id，与 ReadEvidence 读取的写法相同。

2. **幂等**：相同 ``artifact_key``（``op``、``inputs``、``params``、``payload`` 与 ``formed_by`` 的哈希）视为重试，
   返回已有的 Artifact，不重复写入。

3. **写入**：文档按内容寻址写到材料根目录下（已存在且内容相同就不再写）；再经 graph-vc 在一个事务中写 Artifact
   节点、``USED`` 边、Material 与 ``MATERIAL_OF``，产生一个提交（``source`` 为 ``operator:<op>``，``meta`` 记
   Artifact 的 id 与会话）。事务失败时文件留在原处：它按内容寻址、没有节点引用，不影响库。

4. 提交后补算 ``title`` 与 ``abs`` 的向量；失败不影响已完成的提交，只在 ``warnings`` 中提示。

``USED`` 边：同一终点只有一条边（graph-vc 的边以起点、类型、终点标识）。对象引用连到该对象，``role`` 取它在参数
中的角色（Check、Filter 的项键，Verify 的 ``claim``）；记录引用连到记录所属的 Artifact，``role`` 是记录键；来源
引用连到材料所属的节点（论文或 Artifact），边上带 ``material_ref`` 与 ``locators``。``role`` 与 ``locators``
都是列表。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from graph_vc import Changeset, ConflictError, EdgeChange, FileRef, NodeChange

from ..read.artifacts import document_text, documents
from ..read.read_evidence import load_lines, materials
from ..read.store import Store
from ..utils.artifact_doc import Document, compose, data_of, header_of, record_keys
from ..utils.refs import Ref, parse_ref
from ..utils.schema import AGENT_OPS, ARTIFACT, LOCATOR
from ..utils.yamlfmt import dump
from .operators import OPERATORS, Output, Problems

VERSION = "v0.1"
REQUEST_KEYS = ("op", "title", "abs", "inputs", "params", "payload", "session", "formed_by")
REQUIRED = frozenset(REQUEST_KEYS) - {"title"}
PREFIX = "art"


class OperatorError(ValueError):
    """调用没有通过校验，什么也没有写入。``errors`` 是 ``[{rule, where, msg}]``。"""

    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(f"{e['where']}: {e['msg']}" for e in errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class Input:
    """``inputs`` 中的一项。``target`` 是 ``USED`` 的终点；``spelling`` 是写进 ``nodes_used`` 的写法。"""

    ref: Ref
    target: str
    spelling: str
    material: str | None = None


def write_artifact(
    store: Store,
    request: Mapping[str, Any],
    *,
    at: str,
    text: str | None = None,
    sync: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """校验并写入一次 Agent 算子调用的产物。``at`` 是形成时间；``text`` 是交上来的请求原文（记入提交），
    不给时用请求的 YAML；``sync`` 在提交后补算向量。

    Raises:
        OperatorError: 调用没有通过校验。
    """
    problems = Problems()
    _shape(request, problems)
    if problems:
        raise OperatorError(problems.items)
    op = request["op"]
    output = OPERATORS[op](request["params"], request["payload"], problems)
    inputs, spell = _resolve(store, request["inputs"], output, problems)
    if problems:
        raise OperatorError(problems.items)

    warnings = _unused(inputs, output, spell)
    key = artifact_key(request)
    found = store.query("MATCH (a:Artifact {artifact_key: $key}) RETURN a.id AS id", key=key)
    if found:
        return _existing(store, found[0]["id"], warnings, output)

    title = request.get("title") or output.title
    nodes_used = [i.spelling for i in inputs]
    document = compose(title, nodes_used, request["abs"].strip(), output.body, output.data)
    _store_file(store, document)
    art_id = store.graph.allocate_ids(PREFIX, 1)[0]
    props = {
        "op": op,
        "title": title,
        "abs": request["abs"].strip(),
        "params": json.dumps(request["params"], ensure_ascii=False, sort_keys=True, default=str),
        "formed_by": request["formed_by"],
        "formed_at": at,
        "session": request["session"],
        "artifact_key": key,
    }
    changeset = _changeset(store, art_id, props, document, _used(inputs, output, spell))
    try:
        record = store.graph.commit(
            changeset,
            author=request["formed_by"],
            message=title,
            source=f"operator:{op}",
            input=text if text is not None else dump(dict(request)),
            meta={"artifact": art_id, "session": request["session"]},
        )
    except ConflictError as exc:  # 校验之后有对象被删除或改动
        raise OperatorError([{"rule": "conflict", "where": "inputs", "msg": str(exc)}]) from exc

    if sync is not None:
        try:
            sync()
        except (httpx.HTTPError, ValueError) as exc:
            msg = f"embeddings not synced ({exc}); run make embed"
            warnings.append({"rule": "embedding", "where": art_id, "msg": msg})
    return _result("created", art_id, record.id, document.path, document.material_id, warnings, output)


def artifact_key(request: Mapping[str, Any]) -> str:
    """幂等键：``op``、``inputs``、``params``、``payload`` 与 ``formed_by`` 的哈希。"""
    keyed = {k: request.get(k) for k in ("op", "inputs", "params", "payload", "formed_by")}
    text = json.dumps(keyed, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── 校验 ──────────────────────────────────────────────────────────────


def _shape(request: Any, problems: Problems) -> None:
    if not isinstance(request, Mapping):
        problems.add("format", "request", f"a mapping with {list(REQUEST_KEYS)}")
        return
    if unknown := sorted(set(request) - set(REQUEST_KEYS)):
        problems.add("format", "request", f"unknown keys {unknown}; a call has {list(REQUEST_KEYS)}")
    for key in sorted(REQUIRED - set(request)):
        problems.add("format", key, "required")
    op = request.get("op")
    if op not in OPERATORS and "op" in request:
        msg = "not implemented yet" if op in AGENT_OPS else f"one of {list(OPERATORS)}"
        problems.add("format", "op", msg)
    for key in ("title", "abs", "session", "formed_by"):
        value = request.get(key)
        if key in request and not (isinstance(value, str) and value.strip()):
            problems.add("format", key, "a non-empty string")
    inputs = request.get("inputs")
    if "inputs" in request:
        if not isinstance(inputs, list) or not inputs or not all(isinstance(i, str) for i in inputs):
            problems.add("format", "inputs", "a non-empty list of references to what was used")
        elif len(set(inputs)) != len(inputs):
            problems.add("format", "inputs", "lists a reference more than once")
    for key in ("params", "payload"):
        if key in request and not isinstance(request[key], Mapping):
            problems.add("format", key, "a mapping")


def _resolve(
    store: Store, texts: list[str], output: Output, problems: Problems
) -> tuple[list[Input], Callable[[str], str | None]]:
    """核对 ``inputs`` 都在库中，并核对 ``params`` 与 ``payload`` 中的引用都属于 ``inputs``。

    返回 ``inputs`` 与把一个引用换成规范写法的函数（不是引用时为 ``None``）。"""
    parsed = [(i, text, parse_ref(text)) for i, text in enumerate(texts)]
    mentioned = [parse_ref(text) for _, text in output.refs]
    heads = {r.head for r in [*(r for _, _, r in parsed), *mentioned] if r is not None}
    kinds = store.kinds(heads)
    found = materials(store, {r.head for r in [*(r for _, _, r in parsed), *mentioned] if r and r.kind == "source"})

    def spell(text: str) -> str | None:
        ref = parse_ref(text)
        if ref is None:
            return None
        if ref.kind == "source" and ref.head in found:
            return f"{found[ref.head]['id']}::{ref.locator}"
        return ref.text

    inputs: list[Input] = []
    lines: dict[str, list[str] | None] = {}
    keys: dict[str, list[str]] = {}
    for i, _, ref in parsed:
        at = f"inputs[{i}]"
        if ref is None:
            msg = "an object id, <material or node>::<section>::<start>:<end>, or <artifact>#<key>"
            problems.add("reference", at, msg)
        elif ref.kind == "object":
            if ref.head not in kinds:
                problems.add("reference", at, f"{ref.head} is not in the store")
            elif kinds[ref.head] is None:
                problems.add("reference", at, f"{ref.head} is a system record; use the object it belongs to")
            else:
                inputs.append(Input(ref, ref.head, ref.text))
        elif ref.kind == "record":
            if kinds.get(ref.head) != ARTIFACT:
                problems.add("reference", at, f"{ref.head} is not an artifact in the store")
                continue
            if ref.head not in keys:
                keys[ref.head] = _record_keys(store, ref.head)
            if ref.key not in keys[ref.head]:
                problems.add("reference", at, f"{ref.head} has no record {ref.key!r}")
            else:
                inputs.append(Input(ref, ref.head, ref.text))
        else:
            material = found.get(ref.head)
            if material is None:
                problems.add("reference", at, f"{ref.head} is not a material or a node with a material")
                continue
            if material["owner"] is None:
                problems.add("reference", at, f"material {material['id']} belongs to no object")
                continue
            if material["id"] not in lines:
                lines[material["id"]] = load_lines(store, material)
            total = lines[material["id"]]
            match = LOCATOR.fullmatch(ref.locator or "")
            assert match is not None
            if total is None:
                msg = f"material {material['id']} is missing or changed since it was registered"
                problems.add("reference", at, msg)
            elif not 1 <= int(match["start"]) <= int(match["end"]) <= len(total):
                problems.add("reference", at, f"lines {match['start']}:{match['end']} are outside 1:{len(total)}")
            else:
                inputs.append(Input(ref, material["owner"], spell(ref.text) or ref.text, material["id"]))

    accepted = {i.spelling for i in inputs} | {i.ref.text for i in inputs}
    for where, text in output.refs:
        spelled = spell(text)
        if spelled is None:
            problems.add("reference", where, f"not a reference: {text!r}")
        elif text not in accepted and spelled not in accepted and not _failed(text, texts, spell):
            problems.add("reference", where, f"{text} is not among inputs")
    return inputs, spell


def _failed(text: str, inputs: list[str], spell: Callable[[str], str | None]) -> bool:
    """引用列在 inputs 中，只是自身没有通过核对（已另行报告），不再重复报告。"""
    return text in inputs or spell(text) in {spell(i) for i in inputs}


def _record_keys(store: Store, art_id: str) -> list[str]:
    info = documents(store, [art_id]).get(art_id)
    if info is None or info["material"] is None:
        return []
    text = document_text(store, info["material"])
    return record_keys(info["op"], data_of(text)) if text is not None else []


def _unused(inputs: list[Input], output: Output, spell: Callable[[str], str | None]) -> list[dict[str, str]]:
    """``inputs`` 中没有在参数或内容里出现的引用：不阻塞，提示。"""
    mentioned = {spell(text) for _, text in output.refs}
    return [
        {"rule": "unused-input", "where": f"inputs[{n}]", "msg": f"{i.ref.text} is not referenced in params or payload"}
        for n, i in enumerate(inputs)
        if i.spelling not in mentioned and i.ref.text not in mentioned
    ]


# ── 写入 ──────────────────────────────────────────────────────────────


def _used(inputs: list[Input], output: Output, spell: Callable[[str], str | None]) -> dict[str, dict[str, Any]]:
    """``USED`` 的终点 → 边属性；同一终点的角色与定位合成列表。"""
    by_spelling = {i.spelling: i for i in inputs} | {i.ref.text: i for i in inputs}
    roles: dict[str, list[str]] = {}
    locators: dict[str, list[str]] = {}
    material: dict[str, str] = {}
    for i in inputs:
        roles.setdefault(i.target, [])
        if i.ref.kind == "record" and i.ref.key is not None:
            roles[i.target].append(i.ref.key)
        if i.ref.kind == "source" and i.material is not None and i.ref.locator is not None:
            material[i.target] = i.material
            locators.setdefault(i.target, []).append(i.ref.locator)
    for text, names in output.roles.items():
        owner = by_spelling.get(text) or by_spelling.get(spell(text) or "")
        if owner is not None:
            roles[owner.target] += names
    edges: dict[str, dict[str, Any]] = {}
    for target in roles:
        props: dict[str, Any] = {}
        if roles[target]:
            props["role"] = sorted(set(roles[target]))
        if target in material:
            props["material_ref"] = material[target]
            props["locators"] = list(dict.fromkeys(locators[target]))
        edges[target] = props
    return edges


def _store_file(store: Store, document: Document) -> None:
    file = store.material_root / document.path
    if file.exists():
        if hashlib.sha256(file.read_bytes()).hexdigest() != document.sha256:
            raise RuntimeError(f"{document.path} exists with other content; artifact documents are never rewritten")
        return
    file.parent.mkdir(parents=True, exist_ok=True)
    partial = file.with_name(file.name + ".partial")
    partial.write_bytes(document.text.encode("utf-8"))
    partial.replace(file)


def _changeset(
    store: Store, art_id: str, props: dict[str, Any], document: Document, used: dict[str, dict[str, Any]]
) -> Changeset:
    nodes = [NodeChange.create(art_id, [ARTIFACT], props)]
    if document.material_id not in store.graph.local_state([document.material_id]).nodes:
        material = {"path": document.path, "format": "markdown", "content_hash": document.sha256}
        nodes.append(NodeChange.create(document.material_id, ["Material"], material))
    edges = [EdgeChange.create(document.material_id, "MATERIAL_OF", art_id)]
    edges += [EdgeChange.create(art_id, "USED", target, edge) for target, edge in used.items()]
    return Changeset(nodes=tuple(nodes), edges=tuple(edges), files=(FileRef(document.path, document.sha256),))


def _existing(store: Store, art_id: str, warnings: list[dict[str, str]], output: Output) -> dict[str, Any]:
    info = documents(store, [art_id])[art_id]
    material = info["material"] or {}
    text = document_text(store, material) if material else None
    out = _result("existing", art_id, None, material.get("path"), material.get("id"), warnings, output)
    out["render"] = _body(text) if text is not None else None
    return out


def _result(
    status: str,
    art_id: str,
    commit: str | None,
    path: str | None,
    material: str | None,
    warnings: list[dict[str, str]],
    output: Output,
) -> dict[str, Any]:
    out: dict[str, Any] = {"artifact-result": VERSION, "status": status, "artifact": art_id, "commit": commit}
    out["document"] = {"path": path, "material_ref": material}
    out["warnings"] = warnings
    if output.stats:
        out["stats"] = output.stats
    out["render"] = output.body
    return out


def _body(text: str) -> str:
    """文档去掉头部后的正文。"""
    header = header_of(text)
    if not header:
        return text
    return text.split("\n---\n", 1)[1].strip() + "\n"


__all__ = ["VERSION", "Input", "OperatorError", "artifact_key", "write_artifact"]
