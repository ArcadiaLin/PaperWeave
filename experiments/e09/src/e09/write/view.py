"""由库中状态算出的、给读者看的派生信息：材料归属与只读字段。

写入时用来核对交回的只读字段；以后生成读视图（graph-doc）时也用它，保证读写一致。
"""

from __future__ import annotations

from typing import Any

from graph_vc import GraphState

from ..utils.schema import STANCE_RELS


def material_of(node_id: str, state: GraphState) -> str | None:
    """节点（Paper 或 Artifact）当前的材料 id：经 ``MATERIAL_OF`` 指向它的 Material。"""
    owners = sorted(k.src for k in state.edges if k.dst == node_id and k.type == "MATERIAL_OF")
    return owners[0] if owners else None


def node_readonly(node_id: str, state: GraphState) -> dict[str, Any]:
    """节点的只读字段：``_material``（有材料的节点）、``_formed_by``、``_formed_at``（Agent 形成的记录）。"""
    node = state.nodes[node_id]
    view: dict[str, Any] = {}
    material = material_of(node_id, state)
    if material is not None:
        view["_material"] = material
    for key in ("formed_by", "formed_at"):
        if key in node.props:
            view[f"_{key}"] = node.props[key]
    return view


def edge_readonly(rel_type: str, props: dict[str, Any]) -> dict[str, Any]:
    """关系的只读字段：``FROM`` 的 ``_material``，Agent 判断的正反关系的 ``_formed_by``、``_formed_at``。"""
    view: dict[str, Any] = {}
    if rel_type == "FROM" and "material_ref" in props:
        view["_material"] = props["material_ref"]
    if rel_type in STANCE_RELS:
        for key in ("formed_by", "formed_at"):
            if key in props:
                view[f"_{key}"] = props[key]
    return view


__all__ = ["edge_readonly", "material_of", "node_readonly"]
