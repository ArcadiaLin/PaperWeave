"""graph-doc 的语法层：把 YAML 文本解析成 :class:`Document`，检查与数据模型无关的规则。

一份 graph-doc 是图中的一个子图（设计见 ``docs/experiments/e09/operators/commit.md`` §2–§3）：

- 顶层键：``graph-doc``（版本，必填）、``meta``（读视图的说明，写入时忽略）、``by``（写入者）、
  ``confirm``（写入时的确认，内容由上层解释）、``nodes``（节点，按引用作键）。
- 引用：已有 id（如 ``method_0016``），或 ``$`` 开头的临时引用（如 ``$patchtst``），后者表示新建节点。
- 字段类别看拼写：小写是属性，全大写是出边（键是关系类型），``_`` 开头是只读字段。
- 写入语义：写了就设置，``null`` 就清除（节点写 ``null`` 即删除），没写就不动；关系键给出该类型出边的完整集合。

本模块不认识数据模型：``kind``、``aliases``、``material`` 等在这里只是普通属性，由上层翻译。

YAML 按 1.2 核心模式解析标量：只有 ``null``、``true`` / ``false``、十进制整数与有限浮点数会转换类型，
其余一律是字符串。因此 ``2026-10-04T15:30:00Z``、``yes``、``on``、``12:30``、``012`` 都保持为字符串原文。
同一映射中重复的键视为错误，而不是后者覆盖前者。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml

from .errors import DocError

VERSIONS = frozenset({"v0.1"})
TOP_LEVEL = ("graph-doc", "meta", "by", "confirm", "nodes")

TEMP_REF = re.compile(r"\$[A-Za-z0-9][A-Za-z0-9_.-]*")
ID_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")
PROPERTY = re.compile(r"[a-z][a-z0-9_]*")
RELATIONSHIP = re.compile(r"[A-Z][A-Z0-9_]*")
READONLY = re.compile(r"_[A-Za-z][A-Za-z0-9_]*")

PropertyValue = bool | int | float | str | list[Any] | None


@dataclass(frozen=True, slots=True)
class DocEdge:
    """一条出边。``props`` 中值为 ``None`` 的属性表示清除；没写的属性不动。"""

    to: str
    props: dict[str, PropertyValue] = field(default_factory=dict)
    readonly: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocNode:
    """一个节点。``rels`` 的每个键给出该类型出边的完整集合；没写的关系类型不动。"""

    props: dict[str, PropertyValue] = field(default_factory=dict)
    rels: dict[str, list[DocEdge]] = field(default_factory=dict)
    readonly: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Document:
    """``nodes`` 中值为 ``None`` 的节点表示删除。"""

    version: str
    by: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    confirm: dict[str, Any] = field(default_factory=dict)
    nodes: dict[str, DocNode | None] = field(default_factory=dict)

    def temp_refs(self) -> list[str]:
        return [ref for ref in self.nodes if is_temp(ref)]

    def deleted(self) -> list[str]:
        return [ref for ref, node in self.nodes.items() if node is None]


def is_temp(ref: str) -> bool:
    return ref.startswith("$")


def parse(text: str) -> Document:
    """解析 graph-doc 文本；不合法时抛出 :class:`DocError`，列出全部问题。"""
    return from_data(load(text))


def load(text: str) -> Any:
    """按本模块的 YAML 规则（1.2 核心标量、禁止重复键）加载文本，不做 graph-doc 检查。"""
    try:
        return yaml.load(text, Loader=_Loader)  # _Loader 继承 SafeLoader，不构造任意对象
    except yaml.YAMLError as exc:
        raise DocError([f"invalid YAML: {exc}"]) from exc


def from_data(data: Any) -> Document:
    """从已加载的数据（YAML 或 JSON 解析结果）构造 :class:`Document`。"""
    problems: list[str] = []
    if not isinstance(data, Mapping):
        raise DocError(["a graph-doc must be a mapping"])

    for key in data:
        if key not in TOP_LEVEL:
            problems.append(f"{key}: unknown top-level key (expected one of {', '.join(TOP_LEVEL)})")

    version = data.get("graph-doc")
    if version is None:
        problems.append("graph-doc: the format version is required")
    elif not isinstance(version, str) or version not in VERSIONS:
        problems.append(f"graph-doc: unsupported version {version!r}")

    by = data.get("by")
    if by is not None and (not isinstance(by, str) or not by.strip()):
        problems.append("by: must be a non-empty string")

    meta = _mapping(data.get("meta"), "meta", problems)
    confirm = _mapping(data.get("confirm"), "confirm", problems)
    raw_nodes = _mapping(data.get("nodes"), "nodes", problems)

    nodes: dict[str, DocNode | None] = {}
    for ref, value in raw_nodes.items():
        where = f"nodes.{ref}"
        if not _check_ref(ref, where, problems):
            continue
        if value is None:
            if is_temp(ref):
                problems.append(f"{where}: a temporary reference names a new node and cannot be deleted")
            nodes[ref] = None
        elif isinstance(value, Mapping):
            nodes[ref] = _node(value, where, problems)
        else:
            problems.append(f"{where}: a node must be a mapping, or null to delete it")

    problems += _check_references(nodes)
    if problems:
        raise DocError(problems)
    return Document(
        version=version,
        by=by,
        meta=dict(meta),
        confirm=dict(confirm),
        nodes=nodes,
    )


# ── 节点与边 ──────────────────────────────────────────────────────────


def _node(data: Mapping[Any, Any], where: str, problems: list[str]) -> DocNode:
    node = DocNode()
    for key, value in data.items():
        at = f"{where}.{key}"
        if not isinstance(key, str):
            problems.append(f"{at}: field names must be strings")
        elif READONLY.fullmatch(key):
            node.readonly[key] = value
        elif RELATIONSHIP.fullmatch(key):
            node.rels[key] = _edges(value, at, problems)
        elif PROPERTY.fullmatch(key):
            if key == "id":
                problems.append(f"{at}: the node's identity is its key under nodes, not a property")
            elif _check_value(value, at, problems):
                node.props[key] = value
        else:
            problems.append(_bad_field(at))
    return node


def _edges(value: Any, where: str, problems: list[str]) -> list[DocEdge]:
    if value is None:
        problems.append(f"{where}: write [] to remove all relationships of this type")
        return []
    if not isinstance(value, list):
        problems.append(f"{where}: relationships must be a list")
        return []
    edges: list[DocEdge] = []
    seen: set[str] = set()
    for i, item in enumerate(value):
        at = f"{where}[{i}]"
        edge = _edge(item, at, problems)
        if edge is None:
            continue
        if edge.to in seen:
            problems.append(f"{at}: {edge.to} appears more than once; merge the entries")
            continue
        seen.add(edge.to)
        edges.append(edge)
    return edges


def _edge(item: Any, where: str, problems: list[str]) -> DocEdge | None:
    if isinstance(item, str):
        return DocEdge(item) if _check_ref(item, where, problems) else None
    if not isinstance(item, Mapping):
        problems.append(f"{where}: an entry must be a reference or a mapping with 'to'")
        return None
    to = item.get("to")
    if to is None:
        problems.append(f"{where}.to: required")
        return None
    if not _check_ref(to, f"{where}.to", problems):
        return None
    edge = DocEdge(to)
    for key, value in item.items():
        if key == "to":
            continue
        at = f"{where}.{key}"
        if not isinstance(key, str):
            problems.append(f"{at}: field names must be strings")
        elif READONLY.fullmatch(key):
            edge.readonly[key] = value
        elif PROPERTY.fullmatch(key):
            if _check_value(value, at, problems):
                edge.props[key] = value
        elif RELATIONSHIP.fullmatch(key):
            problems.append(f"{at}: relationships cannot have relationships")
        else:
            problems.append(_bad_field(at))
    return edge


def _check_references(nodes: Mapping[str, DocNode | None]) -> list[str]:
    """文档内的一致性：临时引用必须在 ``nodes`` 中定义；不能向本文档删除的节点连边。"""
    problems = []
    deleted = {ref for ref, node in nodes.items() if node is None}
    for ref, node in nodes.items():
        if node is None:
            continue
        for rel, edges in node.rels.items():
            for i, edge in enumerate(edges):
                at = f"nodes.{ref}.{rel}[{i}]"
                if is_temp(edge.to) and edge.to not in nodes:
                    problems.append(f"{at}: temporary reference {edge.to} is not defined under nodes")
                if edge.to in deleted:
                    problems.append(f"{at}: {edge.to} is deleted in this document")
    return problems


# ── 取值与拼写 ────────────────────────────────────────────────────────


def _check_ref(ref: Any, where: str, problems: list[str]) -> bool:
    if isinstance(ref, str) and (TEMP_REF.fullmatch(ref) or ID_REF.fullmatch(ref)):
        return True
    problems.append(f"{where}: {ref!r} is neither an id nor a $ reference")
    return False


def _check_value(value: Any, where: str, problems: list[str]) -> bool:
    """属性值：``null``、布尔、整数、有限浮点数、字符串，或这些标量（非 ``null``）的同类型列表。"""
    if value is None or _scalar(value):
        return True
    if isinstance(value, list):
        kinds = {bool if isinstance(v, bool) else type(v) for v in value}
        if all(_scalar(v) for v in value) and len(kinds) <= 1:
            return True
        problems.append(f"{where}: a list must hold values of one scalar type")
        return False
    problems.append(f"{where}: a property must be a scalar or a list of scalars, got {type(value).__name__}")
    return False


def _scalar(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, bool | int | str)


def _bad_field(where: str) -> str:
    return f"{where}: field names are lowercase (property), UPPERCASE (relationship), or start with _ (read-only)"


def _mapping(value: Any, where: str, problems: list[str]) -> Mapping[Any, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    problems.append(f"{where}: must be a mapping")
    return {}


# ── YAML：1.2 核心标量，禁止重复键 ─────────────────────────────────────


class _Loader(yaml.SafeLoader):
    yaml_implicit_resolvers: dict[str, list[tuple[str, re.Pattern[str]]]] = {}  # noqa: RUF012 —— PyYAML 的类属性

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                raise yaml.constructor.ConstructorError(
                    None, None, f"unhashable key {key!r}", key_node.start_mark
                ) from None
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _construct_int(loader: _Loader, node: yaml.ScalarNode) -> int:
    return int(loader.construct_scalar(node))


def _construct_float(loader: _Loader, node: yaml.ScalarNode) -> float:
    return float(loader.construct_scalar(node))


_Loader.add_implicit_resolver("tag:yaml.org,2002:null", re.compile(r"^(?:~|null|Null|NULL|)$"), ["~", "n", "N", ""])
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
_Loader.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^[-+]?[0-9]+$"), list("-+0123456789"))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$"),
    list("-+.0123456789"),
)
_Loader.add_constructor("tag:yaml.org,2002:int", _construct_int)
_Loader.add_constructor("tag:yaml.org,2002:float", _construct_float)


__all__ = ["VERSIONS", "DocEdge", "DocNode", "Document", "from_data", "is_temp", "load", "parse"]
