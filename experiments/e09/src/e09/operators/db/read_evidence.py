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

from typing import Any

from ...model.schema import LOCATOR
from ...query.materials import load_lines, materials
from ...store.store import ContractError, Store
from ..base import db_operator, schema

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


READ_EVIDENCE = db_operator(
    name="ReadEvidence",
    label="Read evidence",
    description=(
        "Read the lines a source reference points to (<material>::<section>::<start>:<end>), from paper materials "
        "or artifact documents. Each item is available, missing or error; available text carries line numbers."
    ),
    parameters=schema(
        {"source_refs": {"description": "A source reference or a list of them"}},
        ["source_refs"],
    ),
    run=read_evidence,
)


__all__ = ["READ_EVIDENCE", "VERSION", "read_evidence"]
