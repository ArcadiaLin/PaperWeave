"""变更集：一次写入实际生效的修改，带改前与改后的状态。

变更集描述的是物理图（Label、属性、关系），不涉及上层的数据模型。约定：

- 节点以 ``id`` 属性标识；``id`` 不出现在 ``before`` / ``after`` 中，也不能修改。
- 属性值为 ``None`` 表示该属性不存在（Neo4j 不存储空值）。
- 边以 ``(起点 id, 类型, 终点 id)`` 标识，同一对节点之间同一类型的边至多一条。
- 新建：``before is None``；删除：``after is None``；修改：两者都有，且只列出改动的属性。
  删除时 ``before`` 是完整的属性与 Label，因此每个变更集都可以逆向执行（:meth:`Changeset.invert`）。
- 删除节点时，它的全部关系（版本记录自身的除外）都必须作为边的删除列入同一变更集。
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .errors import ChangesetError

Op = Literal["create", "update", "delete"]
PropertyValue = bool | int | float | str | list[bool] | list[int] | list[float] | list[str]
Properties = dict[str, Any]

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# 版本记录占用的 Label 与关系类型，变更集不能触及。
RESERVED_LABELS = frozenset({"Commit", "Branch", "IdCounter"})
RESERVED_TYPES = frozenset({"PARENT", "TOUCHED"})


@dataclass(frozen=True, slots=True)
class NodeChange:
    """一个节点的变化。``labels`` 是完整的 Label 集合。"""

    id: str
    labels_before: frozenset[str] | None
    labels_after: frozenset[str] | None
    before: Properties | None
    after: Properties | None

    @property
    def op(self) -> Op:
        return _op(self.before, self.after)

    @classmethod
    def create(cls, id: str, labels: Iterable[str], props: Mapping[str, Any]) -> NodeChange:
        return cls(id, None, frozenset(labels), None, dict(props))

    @classmethod
    def delete(cls, id: str, labels: Iterable[str], props: Mapping[str, Any]) -> NodeChange:
        return cls(id, frozenset(labels), None, dict(props), None)

    @classmethod
    def update(
        cls,
        id: str,
        labels: Iterable[str],
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        labels_after: Iterable[str] | None = None,
    ) -> NodeChange:
        old = frozenset(labels)
        new = old if labels_after is None else frozenset(labels_after)
        return cls(id, old, new, dict(before), dict(after))

    def invert(self) -> NodeChange:
        return NodeChange(self.id, self.labels_after, self.labels_before, self.after, self.before)


@dataclass(frozen=True, slots=True)
class EdgeKey:
    src: str
    type: str
    dst: str

    def __str__(self) -> str:
        return f"{self.src}-[{self.type}]->{self.dst}"


@dataclass(frozen=True, slots=True)
class EdgeChange:
    """一条边的变化。"""

    key: EdgeKey
    before: Properties | None
    after: Properties | None

    @property
    def op(self) -> Op:
        return _op(self.before, self.after)

    @classmethod
    def create(cls, src: str, type: str, dst: str, props: Mapping[str, Any] | None = None) -> EdgeChange:
        return cls(EdgeKey(src, type, dst), None, dict(props or {}))

    @classmethod
    def delete(cls, src: str, type: str, dst: str, props: Mapping[str, Any] | None = None) -> EdgeChange:
        return cls(EdgeKey(src, type, dst), dict(props or {}), None)

    @classmethod
    def update(cls, src: str, type: str, dst: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> EdgeChange:
        return cls(EdgeKey(src, type, dst), dict(before), dict(after))

    def invert(self) -> EdgeChange:
        return EdgeChange(self.key, self.after, self.before)


@dataclass(frozen=True, slots=True)
class FileRef:
    """变更集依赖的图外文件：相对路径与内容的 SHA-256。文件写入后不再改动。"""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Changeset:
    nodes: tuple[NodeChange, ...] = ()
    edges: tuple[EdgeChange, ...] = ()
    files: tuple[FileRef, ...] = field(default=())

    def __bool__(self) -> bool:
        return bool(self.nodes or self.edges)

    def invert(self) -> Changeset:
        """逆向变更集：在写入后的状态上执行，得到写入前的状态。不再依赖原来的文件。"""
        return Changeset(
            nodes=tuple(n.invert() for n in self.nodes),
            edges=tuple(e.invert() for e in self.edges),
        )

    def validate(
        self,
        *,
        node_labels: frozenset[str] | None = None,
        rel_types: frozenset[str] | None = None,
        unversioned_props: frozenset[str] = frozenset(),
    ) -> None:
        """检查与库状态无关的合法性；不合法时抛出 :class:`ChangesetError`。

        ``node_labels`` / ``rel_types`` 给出时，Label 与关系类型必须在其中；
        ``unversioned_props`` 中的属性不受版本管理，不能出现在变更集里。
        """
        problems = _validate(self, node_labels, rel_types, unversioned_props)
        if problems:
            raise ChangesetError(problems)

    # ── 序列化：普通 dict / list，可直接转 JSON 或 YAML ─────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [_node_to_dict(n) for n in self.nodes],
            "edges": [_edge_to_dict(e) for e in self.edges],
            "files": [{"path": f.path, "sha256": f.sha256} for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Changeset:
        try:
            return cls(
                nodes=tuple(_node_from_dict(n) for n in data.get("nodes", ())),
                edges=tuple(_edge_from_dict(e) for e in data.get("edges", ())),
                files=tuple(FileRef(f["path"], f["sha256"]) for f in data.get("files", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ChangesetError([f"malformed changeset: {exc!r}"]) from exc


def _op(before: object, after: object) -> Op:
    if before is None:
        return "create"
    if after is None:
        return "delete"
    return "update"


def _node_to_dict(n: NodeChange) -> dict[str, Any]:
    op = n.op
    out: dict[str, Any] = {"op": op, "id": n.id}
    if op == "create":
        out["labels"] = sorted(n.labels_after or ())
        out["after"] = n.after
    elif op == "delete":
        out["labels"] = sorted(n.labels_before or ())
        out["before"] = n.before
    else:
        if n.labels_before == n.labels_after:
            out["labels"] = sorted(n.labels_before or ())
        else:
            out["labels"] = {"before": sorted(n.labels_before or ()), "after": sorted(n.labels_after or ())}
        out["props"] = _props_diff_to_dict(n.before or {}, n.after or {})
    return out


def _node_from_dict(d: Mapping[str, Any]) -> NodeChange:
    op, id_ = d["op"], d["id"]
    if op == "create":
        return NodeChange.create(id_, d["labels"], d.get("after") or {})
    if op == "delete":
        return NodeChange.delete(id_, d["labels"], d.get("before") or {})
    if op == "update":
        labels = d["labels"]
        before, after = _props_diff_from_dict(d.get("props") or {})
        if isinstance(labels, Mapping):
            return NodeChange.update(id_, labels["before"], before, after, labels_after=labels["after"])
        return NodeChange.update(id_, labels, before, after)
    raise ValueError(f"unknown node op {op!r}")


def _edge_to_dict(e: EdgeChange) -> dict[str, Any]:
    op = e.op
    out: dict[str, Any] = {"op": op, "from": e.key.src, "type": e.key.type, "to": e.key.dst}
    if op == "create":
        out["after"] = e.after
    elif op == "delete":
        out["before"] = e.before
    else:
        out["props"] = _props_diff_to_dict(e.before or {}, e.after or {})
    return out


def _edge_from_dict(d: Mapping[str, Any]) -> EdgeChange:
    op, src, type_, dst = d["op"], d["from"], d["type"], d["to"]
    if op == "create":
        return EdgeChange.create(src, type_, dst, d.get("after"))
    if op == "delete":
        return EdgeChange.delete(src, type_, dst, d.get("before"))
    if op == "update":
        before, after = _props_diff_from_dict(d.get("props") or {})
        return EdgeChange.update(src, type_, dst, before, after)
    raise ValueError(f"unknown edge op {op!r}")


def _props_diff_to_dict(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    return {k: {"before": before.get(k), "after": after.get(k)} for k in keys}


def _props_diff_from_dict(d: Mapping[str, Any]) -> tuple[Properties, Properties]:
    return {k: v["before"] for k, v in d.items()}, {k: v["after"] for k, v in d.items()}


# ── 校验 ──────────────────────────────────────────────────────────────


def _validate(
    cs: Changeset,
    node_labels: frozenset[str] | None,
    rel_types: frozenset[str] | None,
    unversioned: frozenset[str],
) -> list[str]:
    problems: list[str] = []
    ops: dict[str, Op] = {}

    for n in cs.nodes:
        where = f"node {n.id!r}"
        if not isinstance(n.id, str) or not n.id:
            problems.append(f"{where}: id must be a non-empty string")
        if n.id in ops:
            problems.append(f"{where}: appears more than once")
        if n.before is None and n.after is None:
            problems.append(f"{where}: before and after are both empty")
            continue
        ops[n.id] = n.op
        if (n.labels_before is None) != (n.before is None) or (n.labels_after is None) != (n.after is None):
            problems.append(f"{where}: labels and properties disagree on the operation")
            continue
        for labels in (n.labels_before, n.labels_after):
            if labels is not None:
                problems += _check_labels(where, labels, node_labels)
        for props in (n.before, n.after):
            if props is not None:
                problems += _check_props(where, props, allow_none=n.op == "update", unversioned=unversioned)
        if n.op == "update":
            problems += _check_update(
                where, n.before or {}, n.after or {}, labels_changed=n.labels_before != n.labels_after
            )

    seen_edges: set[EdgeKey] = set()
    for e in cs.edges:
        where = f"edge {e.key}"
        if e.key in seen_edges:
            problems.append(f"{where}: appears more than once")
        seen_edges.add(e.key)
        if e.before is None and e.after is None:
            problems.append(f"{where}: before and after are both empty")
            continue
        if not IDENTIFIER.match(e.key.type):
            problems.append(f"{where}: invalid relationship type")
        elif e.key.type in RESERVED_TYPES:
            problems.append(f"{where}: relationship type {e.key.type} is reserved")
        elif rel_types is not None and e.key.type not in rel_types:
            problems.append(f"{where}: relationship type {e.key.type} is not allowed")
        for props in (e.before, e.after):
            if props is not None:
                problems += _check_props(where, props, allow_none=e.op == "update", unversioned=unversioned)
        if e.op == "update":
            problems += _check_update(where, e.before or {}, e.after or {}, labels_changed=False)
        # 端点：边存在时两端都在；同一变更集里删除的节点不能再挂新边，新建的节点不可能有旧边。
        for end in (e.key.src, e.key.dst):
            end_op = ops.get(end)
            if e.op in ("create", "update") and end_op == "delete":
                problems.append(f"{where}: endpoint {end!r} is deleted in the same changeset")
            if e.op in ("update", "delete") and end_op == "create":
                problems.append(f"{where}: endpoint {end!r} is created in the same changeset")

    for f in cs.files:
        if not f.path or f.path.startswith("/") or ".." in f.path.split("/"):
            problems.append(f"file {f.path!r}: path must be relative and stay inside the file root")
        if not SHA256.match(f.sha256):
            problems.append(f"file {f.path!r}: sha256 must be 64 lowercase hex digits")
    return problems


def _check_labels(where: str, labels: frozenset[str], allowed: frozenset[str] | None) -> list[str]:
    if not labels:
        return [f"{where}: a node needs at least one label"]
    problems = []
    for label in sorted(labels):
        if not isinstance(label, str) or not IDENTIFIER.match(label):
            problems.append(f"{where}: invalid label {label!r}")
        elif label in RESERVED_LABELS:
            problems.append(f"{where}: label {label} is reserved")
        elif allowed is not None and label not in allowed:
            problems.append(f"{where}: label {label} is not allowed")
    return problems


def _check_props(where: str, props: Mapping[str, Any], *, allow_none: bool, unversioned: frozenset[str]) -> list[str]:
    problems = []
    for key, value in props.items():
        if not isinstance(key, str) or not IDENTIFIER.match(key):
            problems.append(f"{where}: invalid property name {key!r}")
        elif key == "id":
            problems.append(f"{where}: 'id' is the node identity and cannot appear among properties")
        elif key in unversioned:
            problems.append(f"{where}: property {key} is not versioned and cannot appear in a changeset")
        elif value is None:
            if not allow_none:
                problems.append(f"{where}: property {key} is None; omit absent properties")
        elif not _storable(value):
            problems.append(f"{where}: property {key} has a value Neo4j cannot store as JSON-compatible data")
    return problems


def _check_update(
    where: str, before: Mapping[str, Any], after: Mapping[str, Any], *, labels_changed: bool
) -> list[str]:
    problems = []
    if set(before) != set(after):
        problems.append(f"{where}: update must list the same properties in before and after")
    unchanged = sorted(k for k in set(before) & set(after) if before[k] == after[k])
    if unchanged:
        problems.append(f"{where}: properties {unchanged} do not change")
    if not before and not labels_changed:
        problems.append(f"{where}: update changes nothing")
    return problems


def _storable(value: object) -> bool:
    if isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list) and value:
        kinds = {bool if isinstance(v, bool) else type(v) for v in value}
        return len(kinds) == 1 and kinds <= {bool, int, float, str} and all(_storable(v) for v in value)
    return isinstance(value, list)  # 空列表


__all__ = [
    "RESERVED_LABELS",
    "RESERVED_TYPES",
    "Changeset",
    "EdgeChange",
    "EdgeKey",
    "FileRef",
    "NodeChange",
    "Op",
    "Properties",
]
