"""E09 的读取算子：Search、Traverse、ReadEvidence（docs/designs/v2/operators.md §3）。

Search 与 Traverse 返回读视图：一份 graph-doc，``nodes`` 是结果节点（带全部模型出边，原样交回 Commit 为 ``noop``），
``meta`` 是 AccessResult 的其余字段（请求、结果 id、取得依据、来源引用、缺失的引用、覆盖信息、续取位置、诊断）。
ReadEvidence 按来源引用读回材料中的行。读取都在当前状态上进行，不写库。
"""

from .cli import run
from .conditions import CONDITIONS, compile_where
from .read_evidence import read_evidence
from .search import search
from .store import ContractError, Embed, Store
from .traverse import traverse
from .view import dump, node_view, render

__all__ = [
    "CONDITIONS",
    "ContractError",
    "Embed",
    "Store",
    "compile_where",
    "dump",
    "node_view",
    "read_evidence",
    "render",
    "run",
    "search",
    "traverse",
]
