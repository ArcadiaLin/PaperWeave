"""写入检查报告的问题。``error`` 阻塞写入，``warning`` 只提示。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Problem:
    """``rule`` 是规则类别，``at`` 是 graph-doc 中的位置（如 ``nodes.$exp.EVALUATES[1]``），
    ``candidates`` 是与之冲突或可供选择的已有节点 id。"""

    rule: str
    at: str
    msg: str
    severity: Severity = "error"
    candidates: tuple[str, ...] = ()


__all__ = ["Problem", "Severity"]
