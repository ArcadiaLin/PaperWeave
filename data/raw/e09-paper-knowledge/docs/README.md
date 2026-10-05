# e09 入库文档（graph-doc）

neo4j-e09（`infra/neo4j-e09/`）的全部内容由本目录的 graph-doc 按文件名顺序提交而成。从空库依次提交，
得到的 id 与状态是确定的。格式见 `packages/graph-doc`，写入契约见 `docs/experiments/e09/operators/commit.md`，
数据模型见 `docs/designs/v2/graph_model_v2.md`。

| 文件 | 来源标签 | 内容 |
| --- | --- | --- |
| `01-seed-tsf.yml` | `seed:tsf` | 时序预测种子：Task、方法类别、数据集 |
| `02-seed-rag.yml` | `seed:rag` | RAG 与记忆种子：Task、方法类别、数据集、基准、模型 |
| `03-2023-DLinear.yml` | `paper:2023-DLinear` | DLinear 论文、方法与引文桩、8 组实验（报告级） |
| `04-2023-PatchTST.yml` | `paper:2023-PatchTST` | PatchTST 论文、方法与引文桩、14 组实验（报告级） |

## 重建

    D=data/raw/e09-paper-knowledge/docs
    uv run python -m e09.write $D/01-seed-tsf.yml --source seed:tsf --no-dedup --apply
    uv run python -m e09.write $D/02-seed-rag.yml --source seed:rag --no-dedup --apply
    uv run python -m e09.write $D/03-2023-DLinear.yml --source paper:2023-DLinear --apply
    uv run python -m e09.write $D/04-2023-PatchTST.yml --source paper:2023-PatchTST --apply

种子是经整理的可信批量入库，不查重；论文文件开头的 `confirm` 记录了对查重候选的判断（都判为不同对象）。
每次提交记录的输入与对应文件逐字相同，文件改动后不能再用来重放已有的提交。

## 由来

01–04 于 2026-10-05 由旧格式一次性转换而来，原文件见 git 历史（删除前最后一次提交 `fbcf176`）：

- 种子 `seeds/tsf.yml`、`seeds/rag.yml`（v2 种子格式，2026-10-02 由 e08 种子改写），内容未改，只改格式。
  节点前的 `verified` / `source` 注释是核对记录，不写进图。
- 论文 `forms/2023-DLinear.yml`、`forms/2023-PatchTST.yml`（paper-form-v2，报告级）。模型中没有 Metric
  与条件字段：表单的 setting、切分约定与指标并入实验的 `text`；参与方的变体与结果来源（own / rerun / cited /
  unstated）写进 EVALUATES 边的 `description`，依据行写进 `source_refs`。

## 种子的范围与撰写约定

种子是抽取论文之前预置的共享节点，为跨论文复用提供稳定的落点：写入论文时查重命中种子就复用，而不是由每篇论文
各自造一个近义节点。

只预置 Task、Method（方法类别）与 Dataset / Benchmark / Model。不预置：

- 本批论文自己的方法（DLinear、PatchTST、GraphRAG 等），它们是抽取对象；
- Issue 与 Proposition，它们是阅读形成的理解；
- Content（Claim、Experiment、Contribution、Observation）；
- Metric：指标不建节点，写在实验描述中。

撰写约定：

- `definition` / `description` 只写对象本身：是什么、范围、边界。不写任何一篇论文如何使用它，也不写经验判断
  （某策略何时更准、某数据集上什么基线强、指标之间的取舍），这些属于论文主张。
- `name`、`aliases`、`definition`、`description` 一律使用英文，与论文原文一致，便于直接匹配原文称呼。
  文件注释与本说明可用中文。
- `note` 只放使用提醒、消歧线索与来源分歧；种子的 note 不引用本批待抽取论文的内容。
- `identifiers` 中资源的官方入口写作 `url:` 命名空间，`url` 不唯一（如 ETT 与 ETTh1–ETTm2 共用一个仓库）。
- `aliases` 只收确实指同一对象的称呼。上下位概念、相关机制、具体方案（如 RevIN）、数据集的变体
  （如 MuSiQue-Ans）都不作为别名；需要时建立节点并用关系连接。
- 名称级差异的对象分开建节点（如 Llama-3-70B-Instruct 与 Llama-3.3-70B-Instruct）。模型按模型族建节点；
  论文实际使用的型号或快照按原文锚点读取，不能由命中模型族推出。
- 事实依据只取原始出处（官方页面、原始论文、模型卡），不取本批待抽取论文的说法。Entity 带 `verified` 注释，
  说明事实性内容是否已按 `source` 注释中的出处核对。
- 种子关系只有 `BROADER`（下位 → 上位）、`OVERLAPS_WITH`、`PART_OF`、`FOR_TASK`，不带 `source_refs`，出处即本文件。
