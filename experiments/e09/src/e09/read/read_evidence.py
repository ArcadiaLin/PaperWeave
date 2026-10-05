"""ReadEvidence：按来源引用读取固定材料中的行（docs/designs/v2/operators.md §3.4）。

    read_evidence(source_refs) -> {evidence: v0.1, items, missing, coverage}

来源引用写作 ``<材料 id>::<章节>::<start>:<end>``，与读视图 ``meta.source_refs`` 中的写法相同；材料 id 也可以换成
带材料的节点（论文）id，与 graph-doc 中 ``source_refs`` 的写法相同。只定位与读取，不解释内容。逐项记录状态：

- ``available``：读到，且文件哈希与入库时一致；``text`` 中每行带行号，便于引用其中更小的范围；
- ``missing``：引用格式不对、库中没有该材料，或文件不在；
- ``error``：文件哈希变了，或行号越界；不返回可能错位的文本。

``missing`` 列出状态为 ``missing`` 的引用；各状态的数量在 ``coverage`` 中。
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..utils.schema import LOCATOR
from .store import ContractError, Store

VERSION = "v0.1"


def read_evidence(store: Store, source_refs: list[str] | str) -> dict[str, Any]:
    refs = [source_refs] if isinstance(source_refs, str) else source_refs
    if not isinstance(refs, list) or not refs or not all(isinstance(r, str) for r in refs):
        raise ContractError([{"at": "source_refs", "msg": "a non-empty list of source references"}])
    refs = list(dict.fromkeys(refs))
    found = materials(store, {r.partition("::")[0] for r in refs})
    texts: dict[str, list[str] | None] = {}
    items = [_read(store, ref, found, texts) for ref in refs]
    states = [item["state"] for item in items]
    coverage = {s: states.count(s) for s in ("available", "missing", "error")}
    return {
        "evidence": VERSION,
        "items": items,
        "missing": [item["ref"] for item in items if item["state"] == "missing"],
        "coverage": {"requested": len(refs), **coverage},
    }


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


def _read(
    store: Store, ref: str, found: dict[str, dict[str, Any]], texts: dict[str, list[str] | None]
) -> dict[str, Any]:
    head, sep, locator = ref.partition("::")
    match = LOCATOR.fullmatch(locator) if sep else None
    if match is None:
        return {"ref": ref, "state": "missing", "reason": "not <material>::<section>::<start>:<end>"}
    material = found.get(head)
    if material is None:
        return {"ref": ref, "state": "missing", "reason": f"{head} is not a material or a node with a material"}
    start, end = int(match["start"]), int(match["end"])
    item: dict[str, Any] = {
        "ref": ref,
        "state": "available",
        "material": material["id"],
        "path": material["path"],
        "section": match["section"],
        "lines": [start, end],
    }
    if material["id"] not in texts:
        texts[material["id"]] = load_lines(store, material)
    lines = texts[material["id"]]
    if lines is None:
        file = store.material_root / material["path"]
        if not file.is_file():
            return {**item, "state": "missing", "reason": f"{material['path']} is not in the material root"}
        return {**item, "state": "error", "reason": "the file changed since it was registered (sha256 differs)"}
    if not 1 <= start <= end <= len(lines):
        return {**item, "state": "error", "reason": f"lines {start}:{end} are outside the material (1:{len(lines)})"}
    item["text"] = "\n".join(f"{n}| {lines[n - 1]}".rstrip() for n in range(start, end + 1)) + "\n"
    return item


def load_lines(store: Store, material: dict[str, Any]) -> list[str] | None:
    """材料的行；文件不在或哈希与登记的不一致时为 ``None``。"""
    file = store.material_root / material["path"]
    if not file.is_file():
        return None
    data = file.read_bytes()
    if hashlib.sha256(data).hexdigest() != material["content_hash"]:
        return None
    return data.decode("utf-8").splitlines()


__all__ = ["VERSION", "load_lines", "materials", "read_evidence"]
