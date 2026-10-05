"""中间件算子：一个算子一个文件，文件名即设计中的算子名（docs/designs/v2/operators.md）。

已实现：resolve（Entity 与 Concept 的解析；写入路径的查重也经它的写入模式）。
Commit 的实现在 e09.write（graph-doc，见 docs/experiments/e09/operators/commit.md）。
旧模型上的 get、experiments、read_evidence 及 I3 的运行入口已删除，见 git 历史；读取算子将按新规范重写。
"""
