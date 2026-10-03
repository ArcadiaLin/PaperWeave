"""中间件算子：一个算子一个文件，文件名即设计中的算子名（docs/designs/v2/intents_decompose.md §4.1）。

已实现：commit（种子增量与论文增量，后者见 docs/designs/v2/commit_contract.md）、resolve、get（目前只覆盖 Entity 与 Concept）、
experiments（报告级，纯结构匹配）、read_evidence（按来源引用读材料行）。
待实现：search、context、evidence、implementations，以及 llm_operator.md 的 decide。
"""
