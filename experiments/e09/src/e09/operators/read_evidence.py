"""ReadEvidence(source_refs)：按来源引用读取固定材料中的行（intents_decompose.md §4.1；I3.3）。

    read_evidence(source_refs) -> {items, missing, states, coverage}

source_ref 写作 `<material_id>::<章节>::<start>:<end>`（graph_model_v2.md §1 方案 B；Experiments 的 source_refs
即此格式）。只定位并读取，不解释内容：读表、取数、判断可比性由调用方完成。

材料按 Material 节点的 path 与 content_hash 读取。逐项记录材料状态（I3.3）：
- available：读到了，且文件哈希与入库时一致；
- missing：引用格式不对、库里没有这份材料，或文件不在；
- error：文件哈希与入库时不同（材料变了，锚点可能失效），或行号越界。不返回可能错位的文本。
"""

import hashlib

from ..config import DATA
from ..form import LOCATOR
from ..utils.graph import q


def read_evidence(source_refs: list[str]) -> dict:
    parsed = {}
    for ref in dict.fromkeys(source_refs):   # 去重并保持顺序
        material, sep, loc = ref.partition("::")
        m = LOCATOR.fullmatch(loc) if sep else None
        parsed[ref] = (material, m)
    mats = {r["id"]: r for r in q("""UNWIND $ids AS id MATCH (m:Material {id: id})
                                       RETURN m.id AS id, m.path AS path, m.content_hash AS hash""",
                                    ids=sorted({mat for mat, m in parsed.values() if m}))}
    lines, items = {}, []
    for ref, (material, m) in parsed.items():
        item = {"source_ref": ref, "material_ref": material}
        if not m:
            items.append(item | {"material": "missing", "reason": "source_ref 应为 <material_id>::<章节>::<start>:<end>"})
            continue
        start, end = int(m["start"]), int(m["end"])
        item |= {"section": m["section"], "lines": [start, end]}
        if material not in mats:
            items.append(item | {"material": "missing", "reason": "库中没有这份材料"})
            continue
        path = DATA / mats[material]["path"]
        item["path"] = mats[material]["path"]
        if material not in lines:
            if not path.is_file():
                lines[material] = "missing"
            else:
                data = path.read_bytes()
                lines[material] = (data.decode("utf-8").splitlines()
                                   if hashlib.sha256(data).hexdigest() == mats[material]["hash"] else "changed")
        got = lines[material]
        if got == "missing":
            items.append(item | {"material": "missing", "reason": f"文件不存在：{item['path']}"})
        elif got == "changed":
            items.append(item | {"material": "error", "reason": "文件哈希与入库时不同，锚点可能失效"})
        elif not 1 <= start <= end <= len(got):
            items.append(item | {"material": "error", "reason": f"行号越界（共 {len(got)} 行）"})
        else:
            items.append(item | {"material": "available", "text": "\n".join(got[start - 1:end])})
    status = {s: sum(i["material"] == s for i in items) for s in ("available", "missing", "error")}
    return {"items": items, "missing": [i["source_ref"] for i in items if i["material"] != "available"],
            "states": {"access": "matched" if status["available"] else "empty", "material": status},
            "coverage": {"call": "read_evidence", "requested": len(source_refs), "distinct": len(parsed),
                         "lines": sum(i["lines"][1] - i["lines"][0] + 1 for i in items if i["material"] == "available")}}
