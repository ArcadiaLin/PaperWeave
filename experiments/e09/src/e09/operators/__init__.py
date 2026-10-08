"""E09 的算子（docs/designs/v2/operators.md）：``db/`` 由中间件执行，``agent/`` 由 Agent 给内容、中间件校验后写成
Artifact。每个算子是一个 :class:`Operator`（见 :mod:`e09.operators.base`），按名称登记在 ``OPERATORS`` 中；
与版本记录的读取接口一起按名称分发见 :mod:`e09.tools`。
"""

from __future__ import annotations

from .agent import AGENT_OPERATORS
from .base import Context, Operator, Result
from .db import DB_OPERATORS

OPERATORS: dict[str, Operator] = {**DB_OPERATORS, **AGENT_OPERATORS}

__all__ = ["OPERATORS", "Context", "Operator", "Result"]
