# E09 · v2 数据模型的真实论文入库

按 [Graph Model V2](../../docs/designs/v2/graph_model_v2.md) 把真实论文入库，检验
[Workload 拆解](../../docs/designs/v2/intents_decompose.md) 中的访问契约。第一个实例是
I3（实验比较）：DLinear 与 PatchTST。

E08 是 v1 图谱，保留不动；E09 用独立的数据目录与 Neo4j 实例。

## 环境

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| Python 环境 | 仓库根的 uv workspace（本目录是成员） | notebook 内核同样用根 `.venv` |
| Neo4j（v2 图谱） | `infra/neo4j-e09/` | bolt 7687，浏览器 7474 |
| Neo4j（v1 图谱） | `infra/neo4j-e08/` | 端口相同，同一时间只起一个 |
| 共同配置 | `src/e09/config.py` | 路径与连接参数，脚本与 notebook 共用 |

    make setup        # 第一次，或依赖变化后
    make neo4j-up     # 不在 docker 组时：make neo4j-up DOCKER="sudo docker"
    make check        # 自检：材料与入库文档目录、连库、确认不是 v1 库
    make embed        # 建向量索引并补算向量；需要 embedding 服务（见 utils/embedding.py）
    make test         # 写入路径的检验（tests/write/）
    make lab          # JupyterLab，工作目录为 notebooks/

## 写入路径

写入路径改为统一的底层：[graph-vc](../../packages/graph-vc)（变更集与版本记录）与
[graph-doc](../../packages/graph-doc)（读写同形的 YAML 子图及求差），设计见
`docs/experiments/e09/operators/commit.md`。E09 只保留模型相关的部分（graph-doc → 物理目标状态的翻译与检查）。
neo4j-e09 的全部内容由 `data/raw/e09-paper-knowledge/docs/` 中的 graph-doc 按顺序提交而成，重建命令见该目录的 README。

命令行入口（Commit 工具）：

    uv run python -m e09.write <文档.yml> --source <来源标签>            # dry_run，输出 graph-plan
    uv run python -m e09.write <文档.yml> --source <来源标签> --apply    # 提交，输出 graph-result

- 连接、查重与向量补算都用 `E09_NEO4J_URI` 所指的库。
- 有数据却没有版本记录的库（如旧写入路径建出的库）一律拒绝，不读也不写。
- 首次提交时建立版本记录、约束、全文索引与向量索引。提交后补算向量；向量服务不可用时只给提示，之后用 `make embed` 再补。
- `--no-dedup` 关闭查重，用于种子这类可信的批量入库；`--no-embed` 跳过补算。
- 退出码：0 表示 ready / noop / committed，1 表示 blocked / conflict，2 表示库不能写入。

原先的写入路径（paper-form-v4 / supplement-form-v1 编译、Commit 的种子、论文与增补增量、`make seed` / `make ingest`）
已删除，最后状态见 tag `e09-legacy-write`。旧模型上的读取算子（Get、Experiments、ReadEvidence）、pi 的工具入口
`tools.py`、I3 的运行入口与相应的测试和 notebook 也已删除，见 git 历史。neo4j-e09 中由旧路径建出的数据已清空，按新路径重建。

## 数据

    data/raw/e09-paper-knowledge/
      papers.yml, status.yml, runs/   # 复制自 e08（2026-10-02），材料准备的原始记录
      papers/<citekey>/paper.md …     # 论文材料，复制自 e08，只读
      docs/                           # 入库的 graph-doc（版本管理）：01–02 种子，03–04 论文；说明见 docs/README.md

`papers/`、`runs/` 等材料不进版本管理，只有 `docs/` 被跟踪。原先的 `seeds/` 与 `forms/` 已转成 graph-doc 并删除，见 git 历史。

## 布局

    notebooks/            探索面（目前没有 notebook）；notebooks/_scratch/ 放导出的中间结果，不进版本管理
    src/e09/              已确定的部分，脚本与 notebook 共用
    src/e09/operators/    中间件算子，一个算子一个文件，文件名即设计中的算子名
    src/e09/utils/        算子共用的底层部件，本身不是算子
    tests/write/          写入路径的检验：内存状态上的场景；设置 GRAPH_VC_TEST_NEO4J_URI 时另在测试实例上往返
    i3/                   首个 I3 实例：questions.yml（三组共同看到的问题与答案格式）、reference.yml（参考答案）；
                          只用论文 citekey 与表格锚点，不依赖库中的 id。检验代码随旧读取算子删除，待新库建好后重写

| 位置 | 内容 |
| --- | --- |
| `config` | 路径与连接参数 |
| `env_check` | 环境自检（`make check`） |
| `write/translate` | graph-doc → 物理目标状态：kind → Label，name / aliases → NameKey（`id` 即 `key`），Paper 的 material → Material，`FROM.material_ref` 与 `source_refs` 换成材料 id，补 `formed_by` / `formed_at`、`exp_key`、`content_key`，核对只读字段 |
| `write/checks` | 写入后状态的模型检查：字段、必需关系、端点规则（改 kind 后原有的边一并复核） |
| `write/submit` | `prepare`（dry_run，只读）与 `apply`（分配 id 后经 graph-vc 单事务提交）；`write/reader` 提供内存与 Neo4j 两种读取 |
| `write/review` | 需要外部判断的检查：新 Entity / Concept 经 Resolve（写入模式）查重，未在 `confirm.<引用>.distinct_from` 中判定的候选阻塞写入；删除时提示一并删除的入边 |
| `write/report` | 返回给 Agent 的 graph-plan（状态、按节点列出的修改、阻塞项及候选与改法、提示）与 graph-result（提交 id、`$` 引用到 id 的映射、计数） |
| `write/database` | 拒绝没有版本记录的旧库；建立版本记录、约束、全文索引与向量索引 |
| `write/cli` | 命令行入口 `python -m e09.write`：dry_run 输出 graph-plan，`--apply` 提交后补算向量并输出 graph-result |
| `operators/resolve` | Resolve：id → alias → 语义三级解析，read / write 两种模式；Entity 与 Concept |
| `utils/schema` | graph_model_v2 的机器可读部分：kind、各 kind 的字段与必需项、关系端点与属性、命名空间唯一性、id 前缀、约束、全文索引、来源引用的定位格式 |
| `utils/graph` | 连接、只读查询 `q`、建约束与全文索引 |
| `utils/namekey` | 规范化配置 `name-key-v1` 与精确键 |
| `utils/embedding` | 向量服务（与 e08 共用 Qwen3-Embedding-8B）、向量索引与补算（`make embed`）：Entity、Concept、Content 的文本与带 `description` 的关系都建向量 |
| `utils/fusion` | 语义阶段的召回参数、分词与 RRF 融合 |

## 现在还不是什么

neo4j-e09 已按新写入路径重建（2026-10-05，`commit_000001`–`000004`）：两份种子与两篇论文（2023-DLinear、2023-PatchTST），共 22 组实验。读取侧只保留
Resolve（写入查重也用它）；Search、Traverse、ReadEvidence 等将按新规范重写。notebook 不能成为文档引用数字的唯一来源（AGENTS.md）。
