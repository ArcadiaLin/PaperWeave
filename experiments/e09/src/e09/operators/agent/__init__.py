"""Agent 算子：Agent 给出内容，中间件校验声明的结构与引用，每次调用写成一个 Artifact（operators.md §4）。

每个算子一个文件：``validate(params, payload, problems) -> Output`` 检查该算子的参数与内容，给出正文与数据块；
共同校验、文档与提交都在 :mod:`e09.artifact.write`。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...artifact.write import write_artifact
from ...store.store import Store
from .check import CHECK
from .extract import EXTRACT
from .filter import FILTER
from .generate import GENERATE
from .matrix_construct import MATRIX_CONSTRUCT
from .summarize import SUMMARIZE
from .verify import VERIFY

AGENT_OPERATORS = {op.name: op for op in (EXTRACT, SUMMARIZE, GENERATE, CHECK, VERIFY, FILTER, MATRIX_CONSTRUCT)}
VALIDATORS = {name: op.validate for name, op in AGENT_OPERATORS.items() if op.validate is not None}


def write(
    store: Store,
    request: Mapping[str, Any],
    *,
    at: str,
    text: str | None = None,
    sync: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """按请求的 ``op`` 写入一个 Artifact；``op`` 不是 Agent 算子时报 ``format`` 错误。

    Raises:
        OperatorError: 调用没有通过校验。
    """
    return write_artifact(store, request, VALIDATORS, at=at, text=text, sync=sync)


__all__ = [
    "AGENT_OPERATORS",
    "CHECK",
    "EXTRACT",
    "FILTER",
    "GENERATE",
    "MATRIX_CONSTRUCT",
    "SUMMARIZE",
    "VALIDATORS",
    "VERIFY",
    "write",
]
