"""Agent 算子的命令行入口：读一份调用（YAML），校验通过后写入 Artifact，输出结果。

    python -m e09.use <调用.yml | -> [--no-embed]
    python -m e09.use -e '{op: Filter, abs: …, inputs: […], params: {…}, payload: {…}, session: s1, formed_by: me}'

调用的键见 :mod:`e09.use.write`，各算子的 ``params`` 与 ``payload`` 见 :mod:`e09.use.operators`。连接、文档目录与
向量服务用 ``E09_NEO4J_URI`` 所指的库、``e09.config.DATA`` 与 ``EMBED_URL``；``--no-embed`` 提交后不补算向量。
没有版本记录的旧库一律拒绝。

退出码：0 表示写入或返回已有的 Artifact；1 表示没有通过校验，输出 ``{errors}``；2 表示库不能写入。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from graph_doc import GraphDocError, load

from ..read.store import Store
from ..utils.yamlfmt import dump
from ..write.database import UnversionedDatabaseError, check_versioned, open_graph, setup_database
from .write import OperatorError, write_artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.expr is not None:
        text = args.expr
    elif args.request == "-":
        text = sys.stdin.read()
    elif args.request is not None:
        text = Path(args.request).read_text(encoding="utf-8")
    else:
        print("error: give a call file, - or -e", file=sys.stderr)
        return 1

    from ..config import DATA, NEO4J_DB
    from ..utils.embedding import sync_embeddings
    from ..utils.graph import driver

    graph = open_graph(driver, database=NEO4J_DB, file_root=DATA)
    store = Store(driver, graph, DATA, database=NEO4J_DB)
    try:
        check_versioned(driver, database=NEO4J_DB)
        setup_database(graph, driver, database=NEO4J_DB)
        out = write_artifact(
            store,
            load(text),
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            text=text,
            sync=None if args.no_embed else sync_embeddings,
        )
    except UnversionedDatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OperatorError, GraphDocError) as exc:
        if isinstance(exc, OperatorError):
            errors = exc.errors
        else:
            errors = [{"rule": "format", "where": "request", "msg": str(exc)}]
        sys.stdout.write(dump({"errors": errors}))
        return 1
    finally:
        driver.close()
    sys.stdout.write(dump(out))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m e09.use", description=__doc__.split("\n\n")[0])
    parser.add_argument("request", nargs="?", help="调用文件路径；- 表示从标准输入读取")
    parser.add_argument("-e", "--expr", help="直接给出调用（YAML 文本）")
    parser.add_argument("--no-embed", action="store_true", help="提交后不补算向量")
    return parser


__all__ = ["main"]
