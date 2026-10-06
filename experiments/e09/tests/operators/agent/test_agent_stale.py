"""可能过期：在读取时按文档头部的 ``nodes_used`` 核对，不存状态。"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from conftest import EXTRACT, MATERIAL, call, commit_doc, write

from e09.artifact.stale import stale
from e09.operators.db.traverse import traverse
from e09.store import Store


def test_staleness_follows_inputs(store: Store, tmp_path: Path) -> None:
    first = write(store, EXTRACT)["artifact"]  # art_0001，用到 dataset_0002
    later = write(
        store,
        call("Generate", [first], {"purpose": "answer"}, {"text": f"Lower on Weather [{first}]."}),
    )["artifact"]
    assert stale(store, [first, later]) == {first: [], later: []}

    root = tmp_path / "root"  # 改动论文材料：用到它的行范围的产物可能过期
    shutil.copytree(store.material_root, root)
    (root / MATERIAL).write_text("edited\n" * 60, encoding="utf-8")
    edited = stale(dataclasses.replace(store, material_root=root), [first, later])
    material = store.query("MATCH (m:Material)-[:MATERIAL_OF]->(:Paper) RETURN m.id AS id")[0]["id"]
    assert edited[first] == [{"ref": f"{material}::5.2 Comparison::10:12", "reason": "material"}]
    assert edited[later] == [{"ref": first, "reason": "stale input"}]

    document = traverse(store, [first])["nodes"][first]["_document"]
    (root / MATERIAL).write_text((store.material_root / MATERIAL).read_text(encoding="utf-8"), encoding="utf-8")
    (root / document).write_text("rewritten\n", encoding="utf-8")
    assert stale(dataclasses.replace(store, material_root=root), [first])[first][0]["reason"] == "document"

    plan = commit_doc(store, "graph-doc: v0.1\nby: claude\nnodes:\n  dataset_0002: null\n", commit=False)
    impact = [w for w in plan["warnings"] if w["rule"] == "delete-impact"]
    assert "art_0001-[USED]->dataset_0002" in impact[0]["msg"] and "possibly stale" in impact[0]["msg"]
    assert commit_doc(store, "graph-doc: v0.1\nby: claude\nnodes:\n  dataset_0002: null\n")["status"] == "committed"
    view = traverse(store, [first, later])["nodes"]
    assert view[first]["_stale"] == [{"ref": "dataset_0002", "reason": "removed"}]
    assert view[later]["_stale"] == [{"ref": first, "reason": "stale input"}]
    assert {"to": "dataset_0002"} not in view[first]["_USED"] and "dataset_0002" not in view[first]["_USED"]
