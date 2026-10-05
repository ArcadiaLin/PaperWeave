"""Commit 工具的命令行入口：读一份 graph-doc，dry_run 时输出 graph-plan，``--apply`` 时提交并输出 graph-result。

    python -m e09.write <文档.yml | -> --source <来源标签> [--apply] [--message 说明] [--base 提交 id]
                        [--no-dedup] [--no-embed]

连接、查重（Resolve）与向量补算都用 ``E09_NEO4J_URI`` 所指的同一个库（见 ``e09.config``）。没有版本记录的旧库
一律拒绝，所以默认地址上现有的 neo4j-e09 不会被改动。

退出码：0 表示 ``ready``、``noop`` 或 ``committed``；1 表示 ``blocked`` 或 ``conflict``；2 表示库不能写入。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from neo4j import Driver

from graph_vc import ConflictError, VersionedGraph

from .database import UnversionedDatabaseError, check_versioned, open_graph, setup_database
from .reader import Neo4jReader
from .report import conflict, plan, result
from .review import ResolveDeduper
from .submit import apply, prepare
from .translate import Context

OK = frozenset({"ready", "noop", "committed"})


def run(
    text: str,
    *,
    graph: VersionedGraph,
    driver: Driver,
    ctx: Context,
    commit: bool,
    message: str = "",
    base: str | None = None,
    database: str | None = None,
    embed: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """dry_run 或提交一份 graph-doc，返回 graph-plan 或 graph-result。

    提交后调用 ``embed`` 补算向量。向量是提交之后补算的派生属性，补算失败（如向量服务不可用）
    不影响已完成的提交，只在结果中提示；之后可以用 ``make embed`` 再补。

    Raises:
        UnversionedDatabaseError: 库中有数据但没有版本记录。
    """
    check_versioned(driver, database=database)
    if not commit:
        return plan(prepare(text, ctx), ctx.reader)
    setup_database(graph, driver, database=database)
    try:
        prepared, record = apply(text, graph, ctx, message=message, base=base)
    except ConflictError as exc:
        return conflict(exc)
    if record is None:
        return plan(prepared, ctx.reader)
    out = result(prepared, record)
    if embed is not None:
        try:
            embed()
        except (httpx.HTTPError, ValueError) as exc:
            warning = {"rule": "embedding", "at": record.id, "msg": f"embeddings not synced ({exc}); run make embed"}
            out.setdefault("warnings", []).append(warning)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    text = sys.stdin.read() if args.document == "-" else Path(args.document).read_text(encoding="utf-8")

    from ..config import DATA, NEO4J_DB
    from ..utils.embedding import sync_embeddings
    from ..utils.graph import driver

    graph = open_graph(driver, database=NEO4J_DB, file_root=DATA)
    ctx = Context(
        reader=Neo4jReader(graph, driver, database=NEO4J_DB),
        source=args.source,
        at=datetime.now(UTC).isoformat(timespec="seconds"),
        material_root=DATA,
        deduper=None if args.no_dedup else ResolveDeduper(),
    )
    try:
        out = run(
            text,
            graph=graph,
            driver=driver,
            ctx=ctx,
            commit=args.apply,
            message=args.message,
            base=args.base,
            database=NEO4J_DB,
            embed=None if args.no_embed else sync_embeddings,
        )
    except UnversionedDatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        driver.close()
    yaml.safe_dump(out, sys.stdout, allow_unicode=True, sort_keys=False, width=120)
    return 0 if out["status"] in OK else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m e09.write", description=__doc__.split("\n\n")[0])
    parser.add_argument("document", help="graph-doc 文件路径；- 表示从标准输入读取")
    parser.add_argument("--source", required=True, help="来源标签，记入提交的 source 与 NameKey.registered_from")
    parser.add_argument("--apply", action="store_true", help="提交；不加时只做 dry_run")
    parser.add_argument("--message", default="", help="提交说明")
    parser.add_argument("--base", help="写入者读视图时所在的提交 id，只记录")
    parser.add_argument("--no-dedup", action="store_true", help="不查重，用于种子这类可信的批量入库")
    parser.add_argument("--no-embed", action="store_true", help="提交后不补算向量")
    return parser


__all__ = ["main", "run"]
