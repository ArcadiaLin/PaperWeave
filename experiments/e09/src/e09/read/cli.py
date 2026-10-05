"""读取算子的命令行入口：读一份请求（YAML），输出读视图或证据。

    python -m e09.read <请求.yml | -> [--no-embed]
    python -m e09.read -e '{op: Traverse, start: [method_0028], path: [{rel: EVALUATES, dir: in}]}'

请求的 ``op`` 是 ``Search``、``Traverse`` 或 ``ReadEvidence``，其余键是该算子的参数（见各模块）。连接与查询向量
用 ``E09_NEO4J_URI`` 所指的库与 ``EMBED_URL`` 的服务（见 ``e09.config``、``e09.utils.embedding``）；
``--no-embed`` 关闭语义通道。没有版本记录的旧库一律拒绝。

退出码：0 表示有结果（可以是空结果）；1 表示契约错误，输出 ``{error: contract, problems}``；2 表示库不能读取。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from graph_doc import GraphDocError, load

from ..write.database import UnversionedDatabaseError, check_versioned, open_graph
from .read_evidence import read_evidence
from .search import search
from .store import ContractError, Store
from .traverse import traverse
from .view import dump

OPS: dict[str, tuple[Callable[..., dict[str, Any]], frozenset[str]]] = {
    "Search": (
        search,
        frozenset({"type", "query", "kinds", "where", "expand", "scope", "budget", "continuation"}),
    ),
    "Traverse": (traverse, frozenset({"start", "path", "budget", "continuation"})),
    "ReadEvidence": (read_evidence, frozenset({"source_refs"})),
}


def run(request: Any, store: Store) -> dict[str, Any]:
    """执行一个请求。

    Raises:
        ContractError: 请求不符合算子契约。
    """
    if not isinstance(request, Mapping):
        raise ContractError([{"at": "request", "msg": "a mapping with op and the operator's parameters"}])
    params = dict(request)
    op = params.pop("op", None)
    if op not in OPS:
        raise ContractError([{"at": "op", "msg": f"one of {list(OPS)}"}])
    operator, accepted = OPS[op]
    if unknown := sorted(set(params) - accepted):
        raise ContractError([{"at": k, "msg": f"{op} accepts {sorted(accepted)}"} for k in unknown])
    required = {"Search": "type", "Traverse": "start", "ReadEvidence": "source_refs"}[op]
    if required not in params:
        raise ContractError([{"at": required, "msg": "required"}])
    return operator(store, **params)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.expr is not None:
        text = args.expr
    elif args.request == "-":
        text = sys.stdin.read()
    elif args.request is not None:
        text = Path(args.request).read_text(encoding="utf-8")
    else:
        print("error: give a request file, - or -e", file=sys.stderr)
        return 1

    from ..config import DATA, NEO4J_DB
    from ..utils.embedding import embed
    from ..utils.graph import driver

    store = Store(
        driver,
        open_graph(driver, database=NEO4J_DB, file_root=DATA),
        DATA,
        database=NEO4J_DB,
        embed=None if args.no_embed else embed,
    )
    try:
        check_versioned(driver, database=NEO4J_DB)
        out = run(load(text), store)
    except UnversionedDatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ContractError, GraphDocError) as exc:
        problems = exc.problems if isinstance(exc, ContractError) else [{"at": "request", "msg": str(exc)}]
        sys.stdout.write(dump({"error": "contract", "problems": problems}))
        return 1
    finally:
        driver.close()
    sys.stdout.write(dump(out))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m e09.read", description=__doc__.split("\n\n")[0])
    parser.add_argument("request", nargs="?", help="请求文件路径；- 表示从标准输入读取")
    parser.add_argument("-e", "--expr", help="直接给出请求（YAML 文本）")
    parser.add_argument("--no-embed", action="store_true", help="关闭语义通道（不调用向量服务）")
    return parser


__all__ = ["OPS", "main", "run"]
