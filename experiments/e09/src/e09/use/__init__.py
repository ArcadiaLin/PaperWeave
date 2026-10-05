"""E09 的 Agent 算子：Extract、Summarize、Generate、Check、Verify、Filter（docs/designs/v2/operators.md §4）。

Agent 给出内容，中间件校验声明的结构与引用，把每次调用持久化为一个 Artifact：节点、``USED`` 边与一份按内容寻址的
文档，经 graph-vc 作为一个提交写入。读取经 :mod:`e09.read`（``Search(type=Artifact)``、沿 ``USED`` 的
``Traverse``、``ReadEvidence`` 读文档）。Rank 与 MatrixConstruct 由中间件执行，尚未实现。
"""

from .operators import OPERATORS, Output, Problems
from .write import Input, OperatorError, artifact_key, write_artifact

__all__ = ["OPERATORS", "Input", "OperatorError", "Output", "Problems", "artifact_key", "write_artifact"]
