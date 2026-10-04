# e09 种子概念（v2 格式）

v2 图谱（`infra/neo4j-e09/`）在抽取论文之前预置的共享节点。它们为跨论文复用提供稳定的落点：抽取时先 Resolve，命中种子就复用，而不是由每篇论文各自造一个近义节点。

本目录由 e08 种子（`data/raw/e08-paper-knowledge/seeds/`）于 2026-10-02 机械改写而来，内容未改，只改格式。数据模型见 `docs/designs/v2/graph_model_v2.md`。

## 范围

| 文件 | 主线 | 对应论文 |
|---|---|---|
| `tsf.yml` | 时序预测 | 2023-DLinear、2023-PatchTST |
| `rag.yml` | RAG 与记忆 | 2024-GraphRAG、2025-LightRAG、2024-HippoRAG、2025-HippoRAG2 |

只预置 `Concept.Task`、`Concept.Method`（方法类别）与 `Entity.Dataset / Benchmark / Model`。Metric 节点已于 2026-10-04 随模型冻结移除：指标不建节点，需要时写在实验描述中。不预置：

- 本批论文自己的方法（DLinear、PatchTST、GraphRAG 等），它们是抽取对象；
- `Concept.Issue` 与 `Concept.Proposition`，它们是阅读形成的理解；
- Content（Claim、Experiment、Contribution、Observation）。

## 由 v1 改写的内容

| v1 | v2 |
|---|---|
| `labels: [Task]` / `[MethodConcept]` | `[Concept, Task]` / `[Concept, Method]` |
| `labels: [Resource, Dataset]`（Model、Benchmark 同理） | `[Entity, Dataset]` |
| Concept 的 `description` | `definition` |
| `SUBTYPE_OF` | `BROADER` |
| `url: <地址>` | `identifiers: ["url:<地址>"]` |

## 格式

- 节点用可读的 `ref` 在文件内引用，不写 `id`；正式 `id` 由入库代码分配。
- `labels` 恰好两个：主 Label（Entity / Concept）与次级 Label（kind）。
- `name` 与 `aliases` 是**入库表单字段**：入库时各注册为一条 `NameKey`（scope 为 global），对象上只保留 `name`，不存 `aliases` 列表。
- Concept 的 `definition` 即标准定义；Entity 的 `description` 是资源介绍。
- `identifiers` 是 `"<namespace>:<value>"` 字符串列表。资源的官方入口写作 `url:` 命名空间；`url` **不唯一**：同一仓库常对应多个数据集（如 ETT 与 ETTh1–ETTm2 共用 `zhouhaoyi/ETDataset`），Resolve 命中多个时返回 ambiguous，再与名称取交集（`docs/designs/v2/graph_model_v2.md` 2.4）。
- `note`（可选，写进图）只放使用提醒、消歧线索与来源分歧，不写定义与经验判断；种子的 note 不引用本批待抽取论文的内容。
- 关系用 `from` / `to` 引用 `ref`；种子关系没有 `source_refs`，出处即本文件。
- 节点条目上、`properties` 之外可带 `sources`（核对所用的原始出处 URL）与 `verified`（事实性内容是否已按这些出处核对）。二者只记入种子增量，不写进图。Entity 必须带 `verified`；Concept 的 definition 是定义，不要求出处。

```yaml
nodes:
  - ref: task_ltsf
    labels: [Concept, Task]
    properties: {name: ..., aliases: [...], definition: ...}
relationships:
  - {from: task_ltsf, type: BROADER, to: task_tsf}
```

关系类型只有 `BROADER`（下位 → 上位）、`OVERLAPS_WITH`、`PART_OF`、`FOR_TASK`。

## 撰写约定

- `definition` / `description` 只写对象本身：是什么、范围、边界。不写任何一篇论文如何使用它；那是抽取时写进实验描述或参与关系的内容。
- 语言：`name`、`aliases`、`definition`、`description` 一律使用英文，与论文原文一致，便于直接匹配原文称呼。文件注释与本说明可用中文。
- 名称级差异的对象分开建节点（如 Llama-3-70B-Instruct 与 Llama-3.3-70B-Instruct）。API 模型按模型族建节点；模型不表达版本，论文使用的具体快照（如 `gpt-3.5-turbo-1106`）按原文锚点读取。
- 事实依据只取原始出处（数据集或模型的官方页面、原始论文、模型卡），不取本批待抽取论文的说法；引用论文与原始出处不一致时（如 MultiHop-RAG 的新闻时间范围），以原始出处为准，差异按原文锚点读取，需要积累时写成 Observation。
- `aliases` 只收确实指同一对象的称呼。上下位概念、相关机制、不同维度的限定（如 open-domain 之于 single-hop）不作为别名；需要时建立节点并用关系连接。仅为提高召回的扩展词由检索工具处理。
- 具体方案（如 RevIN）、数据集的变体（如 MuSiQue-Ans）不作为一般概念或资源的别名。
- 定义与描述不写经验判断（某策略何时更准、某数据集上什么基线强、指标之间的取舍），这些属于论文主张，由抽取写成带来源的 Claim。
- 模型族节点（如 GTR、GPT-4o-mini）只表示同一系列；实验实际使用的型号或快照按原文锚点读取，不能由命中模型族推出。

