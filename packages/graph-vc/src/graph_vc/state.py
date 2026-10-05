"""图状态的内存表示，以及变更集的前提核对与应用。

:class:`GraphState` 只包含受版本管理的部分：带 ``id`` 的节点和它们之间的边，不含版本记录本身。
前提核对 :func:`check_preconditions` 是纯函数，数据库写入与内存应用共用它，保证两条路径的语义一致。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .changeset import Changeset, EdgeKey, Properties
from .errors import Conflict, ConflictError


@dataclass(frozen=True, slots=True)
class NodeState:
    labels: frozenset[str]
    props: Properties


@dataclass(slots=True)
class GraphState:
    """节点按 id、边按 :class:`EdgeKey` 索引。``props`` 不含 ``id``。

    数据库路径只取出变更集涉及的节点与边，构成局部状态再交给 :func:`check_preconditions`；
    局部状态必须包含被删节点的全部关系，否则无法判断删除是否完整。
    """

    nodes: dict[str, NodeState] = field(default_factory=dict)
    edges: dict[EdgeKey, Properties] = field(default_factory=dict)

    def incident(self, node_id: str) -> set[EdgeKey]:
        return {k for k in self.edges if node_id in (k.src, k.dst)}

    def apply(self, changeset: Changeset) -> GraphState:
        """返回应用变更集后的新状态；前提不成立时抛出 :class:`ConflictError`，自身不变。"""
        conflicts = check_preconditions(changeset, self)
        if conflicts:
            raise ConflictError(conflicts)
        nodes = dict(self.nodes)
        edges = dict(self.edges)
        for e in changeset.edges:
            if e.op == "delete":
                del edges[e.key]
        for n in changeset.nodes:
            if n.op == "create":
                nodes[n.id] = NodeState(n.labels_after or frozenset(), dict(n.after or {}))
            elif n.op == "update":
                props = {**nodes[n.id].props, **(n.after or {})}
                nodes[n.id] = NodeState(n.labels_after or frozenset(), _drop_none(props))
        for e in changeset.edges:
            if e.op == "create":
                edges[e.key] = dict(e.after or {})
            elif e.op == "update":
                edges[e.key] = _drop_none({**edges[e.key], **(e.after or {})})
        for n in changeset.nodes:
            if n.op == "delete":
                del nodes[n.id]
        return GraphState(nodes, edges)


def check_preconditions(changeset: Changeset, state: GraphState) -> list[Conflict]:
    """核对变更集记录的改前状态是否与 ``state`` 一致，返回全部不一致项。

    - 新建：节点或边当前不存在；新边的两端当前存在或在本变更集中新建。
    - 修改：对象存在，Label 相同，列出的每个属性当前值等于 ``before``。
    - 删除：对象存在，Label 与全部属性等于 ``before``；节点的每条关系都在本变更集中删除。
    """
    conflicts: list[Conflict] = []
    created = {n.id for n in changeset.nodes if n.op == "create"}
    deleted_edges = {e.key for e in changeset.edges if e.op == "delete"}

    for n in changeset.nodes:
        current = state.nodes.get(n.id)
        if n.op == "create":
            if current is not None:
                conflicts.append(Conflict(n.id, "node already exists"))
            continue
        if current is None:
            conflicts.append(Conflict(n.id, "node does not exist"))
            continue
        if current.labels != n.labels_before:
            conflicts.append(Conflict(n.id, "labels differ", sorted(n.labels_before or ()), sorted(current.labels)))
        if n.op == "update":
            conflicts += _compare_listed(n.id, n.before or {}, current.props)
        else:
            if not same_props(current.props, n.before or {}):
                conflicts.append(Conflict(n.id, "properties differ", n.before, current.props))
            remaining = sorted(str(k) for k in state.incident(n.id) - deleted_edges)
            if remaining:
                conflicts.append(Conflict(n.id, "relationships not deleted in this changeset", [], remaining))

    for e in changeset.edges:
        target = str(e.key)
        current = state.edges.get(e.key)
        if e.op == "create":
            if current is not None:
                conflicts.append(Conflict(target, "relationship already exists"))
            for end in (e.key.src, e.key.dst):
                if end not in state.nodes and end not in created:
                    conflicts.append(Conflict(target, f"endpoint {end} does not exist"))
            continue
        if current is None:
            conflicts.append(Conflict(target, "relationship does not exist"))
        elif e.op == "update":
            conflicts += _compare_listed(target, e.before or {}, current)
        elif not same_props(current, e.before or {}):
            conflicts.append(Conflict(target, "properties differ", e.before, current))
    return conflicts


def same_value(a: Any, b: Any) -> bool:
    """属性值相等；区分布尔与数值（Python 中 ``True == 1``）。"""
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def same_props(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)


def _compare_listed(target: str, before: Mapping[str, Any], current: Mapping[str, Any]) -> list[Conflict]:
    return [
        Conflict(target, f"property {key} differs", expected, current.get(key))
        for key, expected in before.items()
        if not same_value(current.get(key), expected)
    ]


def _drop_none(props: Mapping[str, Any]) -> Properties:
    return {k: v for k, v in props.items() if v is not None}


__all__ = ["GraphState", "NodeState", "check_preconditions", "same_props", "same_value"]
