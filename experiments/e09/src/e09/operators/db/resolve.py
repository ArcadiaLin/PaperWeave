"""Resolve：把一个说法解析为已存对象的引用（docs/designs/v2/operators.md §3.2）。

三级逐级解析（标识、名称精确键、语义候选），实现见 :mod:`e09.query.resolve`；Commit 的查重也用它。Resolve 经
``e09.store.graph`` 的连接读 ``E09_NEO4J_URI`` 所指的库，不用调用环境中的 ``store``。
"""

from __future__ import annotations

from typing import Any

from ...query.resolve import resolve
from ...store.store import ContractError, Store
from ..base import db_operator, schema


def run(
    store: Store, query: dict[str, str] | str, kind: str, scope: str = "global", mode: str = "read"
) -> dict[str, Any]:
    """解析一个说法；参数不合法（未知 kind、未声明的命名空间等）是契约错误。"""
    del store  # 见模块说明
    try:
        return resolve(query, kind=kind, scope=scope, mode=mode)
    except ValueError as exc:
        raise ContractError([{"at": "query", "msg": str(exc)}]) from exc


RESOLVE = db_operator(
    name="Resolve",
    label="Resolve",
    description=(
        "Resolve a mention, identifier or text to stored Entity or Concept references of one kind: exact identifier, "
        "exact name key, then semantic candidates. Semantic candidates are not identities; confirm them with Filter."
    ),
    parameters=schema(
        {
            "query": {"description": "A mention, or {identifier?, mention?, text?}"},
            "kind": {"type": "string"},
            "scope": {"type": "string"},
            "mode": {"enum": ["read", "write"]},
        },
        ["query", "kind"],
    ),
    run=run,
)


__all__ = ["RESOLVE", "run"]
