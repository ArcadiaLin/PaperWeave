"""graph_vc 的异常类型。"""

from __future__ import annotations

from dataclasses import dataclass


class GraphVCError(Exception):
    """本包所有异常的基类。"""


class ChangesetError(GraphVCError, ValueError):
    """变更集本身不合法：结构、标识符、属性值或内部引用有误。与库的当前状态无关。"""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class Conflict:
    """一项前提不成立：变更集记录的改前状态与库中当前状态不一致。

    ``target`` 是节点 id，或 ``<起点>-[<类型>]-><终点>`` 形式的边。
    """

    target: str
    reason: str
    expected: object = None
    actual: object = None


class ConflictError(GraphVCError):
    """变更集的前提与库的当前状态不一致；整个事务已回滚，库未改动。"""

    def __init__(self, conflicts: list[Conflict]):
        super().__init__(f"{len(conflicts)} conflict(s): " + "; ".join(f"{c.target}: {c.reason}" for c in conflicts))
        self.conflicts = conflicts


class FileIntegrityError(GraphVCError):
    """变更集引用的文件不存在，或内容哈希不一致；库未改动。"""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


__all__ = ["ChangesetError", "Conflict", "ConflictError", "FileIntegrityError", "GraphVCError"]
