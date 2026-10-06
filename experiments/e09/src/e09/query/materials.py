"""固定材料：按引用开头找到材料，按登记的哈希读出它的行。ReadEvidence、Artifact 的写入与过期共用。"""

from __future__ import annotations

import hashlib
from typing import Any

from ..store.store import Store


def materials(store: Store, heads: set[str]) -> dict[str, dict[str, Any]]:
    """引用开头（材料 id 或带材料的节点 id）→ 材料 ``{id, path, content_hash, owner}``。

    ``owner`` 是材料所属的节点：开头是节点时就是它；开头是材料时取 ``MATERIAL_OF`` 指向的节点（内容相同的
    Artifact 文档只存一份，可能有多个，取 id 最小的）；材料不属于任何节点时为 ``None``。"""
    rows = store.query(
        """UNWIND $heads AS head
           OPTIONAL MATCH (m:Material {id: head})
           OPTIONAL MATCH (owned:Material)-[:MATERIAL_OF]->({id: head})
           WITH head, coalesce(m, owned) AS material, CASE WHEN m IS NULL THEN head END AS node
           WHERE material IS NOT NULL
           OPTIONAL MATCH (material)-[:MATERIAL_OF]->(o)
           WITH head, material, node, min(o.id) AS first
           RETURN head, material.id AS id, material.path AS path, material.content_hash AS content_hash,
                  coalesce(node, first) AS owner""",
        heads=sorted(heads),
    )
    return {r["head"]: {k: r[k] for k in ("id", "path", "content_hash", "owner")} for r in rows}


def load_lines(store: Store, material: dict[str, Any]) -> list[str] | None:
    """材料的行；文件不在或哈希与登记的不一致时为 ``None``。"""
    file = store.material_root / material["path"]
    if not file.is_file():
        return None
    data = file.read_bytes()
    if hashlib.sha256(data).hexdigest() != material["content_hash"]:
        return None
    return data.decode("utf-8").splitlines()


__all__ = ["load_lines", "materials"]
