"""E09 的算子（docs/designs/v2/operators.md）：``db/`` 由中间件执行，``agent/`` 由 Agent 给内容、中间件校验后写成
Artifact。每个算子是一个 :class:`Operator`（见 :mod:`e09.operators.base`），按名称登记在 ``OPERATORS`` 中。

    call(ctx, {op, ...}) -> Result
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .agent import AGENT_OPERATORS
from .base import Context, Operator, Result
from .db import DB_OPERATORS

OPERATORS: dict[str, Operator] = {**DB_OPERATORS, **AGENT_OPERATORS}


def call(ctx: Context, request: Mapping[str, Any]) -> Result:
    """按请求的 ``op`` 找到算子并执行；请求不是映射或 ``op`` 不认识时返回契约错误。"""
    op = request.get("op") if isinstance(request, Mapping) else None
    if op not in OPERATORS:
        problems = [{"at": "op", "msg": f"one of {list(OPERATORS)}"}]
        return Result({"error": "contract", "problems": problems}, is_error=True)
    return OPERATORS[op].call(ctx, request)


__all__ = ["OPERATORS", "Context", "Operator", "Result", "call"]
