"""外部 Agent（pi）调用中间件的命令行入口：一次调用一个工具，参数与结果都是 JSON。

    .venv/bin/python -m e09.tools <工具名> '<JSON 参数>'

pi 扩展（pi-configs/i3-audit/extensions/）通过 pi.exec 调用这里；退出码 0 时 stdout 是结果 JSON，
非 0 时 stderr 是给 Agent 看的错误信息（参数错误等）。工具按 I3 的组别开放（e09/i3/run.py）：

| 工具 | 组 | 对应 |
| --- | --- | --- |
| resolve、experiments、get | S | operators/ 下的同名算子 |
| cypher | S-Cypher | 只读事务中执行任意 Cypher；结果去掉向量属性、限制行数 |
| read_evidence | S、S-Cypher | operators/read_evidence |
"""

import json
import sys

from neo4j import READ_ACCESS
from neo4j.graph import Node, Path, Relationship

from .config import NEO4J_DB
from .operators.experiments import experiments
from .operators.get import get
from .operators.read_evidence import read_evidence
from .operators.resolve import resolve
from .utils.graph import driver

CYPHER_MAX_ROWS = 200
DERIVED = {"embedding", "embedding_key"}   # 检索用的派生属性：4096 维向量，不给 Agent


def _plain(v):
    """Neo4j 返回值 → 可序列化的普通结构；节点与关系带上 Label / 类型，去掉派生属性。"""
    if isinstance(v, Node):
        return {"_labels": sorted(v.labels), **{k: _plain(x) for k, x in v.items() if k not in DERIVED}}
    if isinstance(v, Relationship):
        return {"_type": v.type, "_start": v.start_node.get("id"), "_end": v.end_node.get("id"),
                **{k: _plain(x) for k, x in v.items()}}
    if isinstance(v, Path):
        return {"_path": [_plain(n) for n in v.nodes], "_rels": [r.type for r in v.relationships]}
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items() if k not in DERIVED}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def cypher(query: str, params: dict | None = None) -> dict:
    """只读事务：写操作由 Neo4j 拒绝。最多返回 CYPHER_MAX_ROWS 行，截断时标出。"""
    def work(tx):
        result = tx.run(query, params or {})
        rows = []
        for record in result:
            if len(rows) == CYPHER_MAX_ROWS:
                return rows, True
            rows.append({k: _plain(v) for k, v in record.items()})
        return rows, False
    with driver.session(database=NEO4J_DB, default_access_mode=READ_ACCESS) as s:
        rows, truncated = s.execute_read(work)
    return {"rows": rows, "row_count": len(rows), "truncated": truncated}


TOOLS = {
    "resolve": lambda a: resolve({k: a[k] for k in ("mention", "identifier", "text") if a.get(k)},
                                 kind=a["kind"], scope=a.get("scope", "global")),
    "experiments": lambda a: experiments(a["subjects"], dataset=a.get("dataset"), metric=a.get("metric"),
                                         scope=a.get("scope", "global"), budget=a.get("budget", 50),
                                         continuation=a.get("continuation")),
    "get": lambda a: get(a["refs"]),
    "read_evidence": lambda a: read_evidence(a["source_refs"]),
    "cypher": lambda a: cypher(a["query"], a.get("params")),
}


def main(argv) -> int:
    if len(argv) != 2 or argv[0] not in TOOLS:
        print(f"用法：python -m e09.tools <{'|'.join(TOOLS)}> '<JSON 参数>'", file=sys.stderr)
        return 2
    try:
        out = TOOLS[argv[0]](json.loads(argv[1]))
    except (ValueError, KeyError, TypeError) as e:   # 参数问题：原样告诉 Agent，让它改正后重试
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except Exception as e:   # Cypher 语法错误、写操作被拒等
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        driver.close()
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
