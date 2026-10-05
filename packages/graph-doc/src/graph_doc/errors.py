"""graph_doc 的异常类型。"""

from __future__ import annotations


class GraphDocError(Exception):
    """本包所有异常的基类。``problems`` 中每一项都带有出错位置，如 ``nodes.$exp.EVALUATES[1].to``。"""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class DocError(GraphDocError, ValueError):
    """文档本身不合法：YAML 语法、顶层结构、字段拼写、取值类型或文档内引用有误。与库的状态无关。"""


class DiffError(GraphDocError, ValueError):
    """目标状态与库中现状放在一起不可能成立：引用的节点不存在、新节点的 id 已被占用、向被删节点连边等。"""


__all__ = ["DiffError", "DocError", "GraphDocError"]
