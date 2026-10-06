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
    make embed        # 建向量索引并补算向量；需要 embedding 服务（见 store/embedding.py）
    make test         # 写入管线与算子的检验（tests/）
    make workspace DIR=~/e09-runs/<名称>   # 实验目录（仓库外）：在其中运行默认的 pi，经 MCP 使用算子
    make lab          # JupyterLab，工作目录为 notebooks/

## 写入路径

写入路径改为统一的底层：[graph-vc](../../packages/graph-vc)（变更集与版本记录）与
[graph-doc](../../packages/graph-doc)（读写同形的 YAML 子图及求差），设计见
`docs/experiments/e09/operators/commit.md`。E09 只保留模型相关的部分（graph-doc → 物理目标状态的翻译与检查）。
neo4j-e09 的全部内容由 `data/raw/e09-paper-knowledge/docs/` 中的 graph-doc 按顺序提交而成，重建命令见该目录的 README。

## 算子与命令行

契约见 [算子契约](../../docs/designs/v2/operators.md)（第 9 节为实现对照）。全部算子经同一个入口调用，请求的 `op`
是算子名，其余键是它的参数：

    uv run python -m e09 <请求.yml | -> [--no-embed] [--session 会话 --formed-by 形成者]
    uv run python -m e09 -e '{op: Traverse, start: [method_0028], path: [{rel: EVALUATES, dir: in}]}'
    uv run python -m e09 <文档.yml> --source <来源标签>            # graph-doc：Commit 的 dry_run，输出 graph-plan
    uv run python -m e09 <文档.yml> --source <来源标签> --apply    # 提交，输出 graph-result

- 由中间件执行的算子（`operators/db/`）：Search、Resolve、Traverse、ReadEvidence 读取，不写库；Commit 提交 graph-doc，
  也可写成 `{op: Commit, doc, source, apply, message, base, dedup}`。
- Agent 算子（`operators/agent/`）：Extract、Summarize、Generate、Check、Verify、Filter、MatrixConstruct，每次调用写一个
  Artifact，产生一个提交。文档按标题命名写到 `data/raw/e09-paper-knowledge/artifacts/`（重名时加 ` (1)`，不进 git），登记为 Material，
  可用 ReadEvidence 读取。MatrixConstruct 由 Agent 填写矩阵，中间件只校验表格结构；Rank 已取消。
- 给通用 Agent 用的入口是 MCP 服务 PaperWeave（`python -m e09.mcp`，stdio）：每个算子一个工具，工具名即算子名，参数与
  结果与命令行相同，错误结果标为 `isError`。给模型看的全部文字（`instructions`、工具的标题与说明、参数说明）在
  `src/e09/mcp/server.yml`，启动时按它装配，对不上算子时服务不启动；算子的代码只给结构。Agent 算子的 `session` 由服务进程启动时生成，`formed_by` 取环境变量 `E09_FORMED_BY`；
  `E09_ENABLE_COMMIT=1` 时才列出 Commit。`make workspace DIR=...`（`python -m e09.workspace`）在仓库外生成实验目录，
  其中只有登记该服务的 `.pi/mcp.json`（`formed_by` 默认取 pi 的默认模型）、把会话存到 `.pi/sessions/` 的
  `.pi/settings.json` 与启动脚本 `pi.sh`（`./pi.sh` 进入交互界面，`./pi.sh -r` 选择会话继续）。第一次启动时确认信任该
  目录，非交互运行加 `--approve`。目录必须在仓库外，否则 pi 会加载仓库的 `AGENTS.md`。
- 读视图是一份 graph-doc：`nodes` 原样交回 Commit 为 `noop`，`meta` 是 AccessResult。
- 连接、查重与向量补算都用 `E09_NEO4J_URI` 所指的库。有数据却没有版本记录的库（如旧写入路径建出的库）一律拒绝。
  首次提交时建立版本记录、约束、全文索引与向量索引；Agent 算子通过校验、确实写入前同样建立。提交后补算向量，向量服务不可用时只给
  提示，之后用 `make embed` 再补。
- `--no-embed` 关闭查询向量，写入后也不补算；`--no-dedup` 关闭 Commit 的查重，用于种子这类可信的批量入库。
- 算子的参数（`Operator.parameters`）只含算子自己的参数：不含 `op`（作为工具时工具名就是算子名），也不含 `session`、
  `formed_by`（调用环境的信息，命令行用 `--session`、`--formed-by` 给出，Agent 算子写入时必需）。
- 没有完成时一律返回 `{status, errors}`：`status` 为 `rejected`、`blocked` 或 `conflict`，`errors` 每项为 `{rule, at, msg}`。
- 退出码：0 有结果（可以为空，或写入、重试命中、ready / noop / committed）；1 错误结果（rejected / blocked / conflict）；
  2 库不能使用。

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
    src/e09/operators/    算子：base.py 定义 Operator；db/ 由中间件执行，agent/ 由 Agent 给内容；每个算子一个文件
    src/e09/model/        数据模型与写法：schema、引用、名称精确键
    src/e09/store/        连接与库：Store、版本记录与约束索引、向量
    src/e09/query/        读取共用：结构条件、RRF 融合、读视图与只读字段、固定材料、Resolve 的三级解析
    src/e09/commit/       graph-doc 的写入管线
    src/e09/artifact/     Artifact 的文档、共同写入路径与可能过期
    tests/commit/         写入管线的检验：内存状态上的场景；设置 GRAPH_VC_TEST_NEO4J_URI 时另在测试实例上往返
    tests/operators/      db/ 与 agent/ 算子的检验，只在空的测试实例（GRAPH_VC_TEST_NEO4J_URI）上运行
    i3/                   首个 I3 实例：questions.yml（三组共同看到的问题与答案格式）、reference.yml（参考答案）；
                          只用论文 citekey 与表格锚点，不依赖库中的 id。检验代码随旧读取算子删除，待新库建好后重写

| 位置 | 内容 |
| --- | --- |
| `cli` | 命令行入口 `python -m e09`：按 `op` 分发；直接给 graph-doc 时视为 Commit |
| `mcp/server`、`mcp/spec`、`mcp/server.yml` | MCP 服务 PaperWeave（`python -m e09.mcp`）；按 `server.yml` 装配工具并核对；给模型看的全部文字 |
| `workspace` | 实验目录的生成 |
| `config`、`env_check` | 路径与连接参数；环境自检（`make check`） |
| `operators/base` | `Operator`（name、family、parameters、execute；只有结构，文字在 `mcp/server.yml`）、`Context`、`Result`；`db_operator`、`agent_operator` 两种构造 |
| `operators/db/search` | Search：精确命中优先，名称词面、全文与向量按 RRF 融合；`type=Artifact` 时只查 Artifact |
| `operators/db/resolve` | Resolve：id → alias → 语义三级解析，Entity 与 Concept |
| `operators/db/traverse` | Traverse：按端点表校验每一跳，传递性关系的 `depth`，路径绑定；含 `USED` |
| `operators/db/read_evidence` | ReadEvidence：按材料 id 或论文、Artifact 的 id 读行，校验文件哈希 |
| `operators/db/commit` | Commit：dry_run 输出 graph-plan，`apply` 提交后补算向量并输出 graph-result |
| `operators/agent/<算子>` | 各 Agent 算子的 `validate`（参数与内容校验、默认标题、正文与数据块）与算子定义；`_common` 为字段类型、逐项判断与表格 |
| `model/schema` | graph_model_v2 的机器可读部分：kind、各 kind 的字段与必需项、关系端点与属性、命名空间唯一性、id 前缀、约束、全文索引、来源引用的定位格式 |
| `model/refs`、`model/namekey` | 引用写法与正文中的引用识别；规范化配置 `name-key-v1` 与精确键 |
| `store/store`、`store/database` | 算子共用的环境 `Store` 与契约错误；拒绝没有版本记录的旧库，建立版本记录、约束、全文索引与向量索引 |
| `store/graph`、`store/embedding` | 连接与只读查询 `q`；向量服务（与 e08 共用 Qwen3-Embedding-8B）、向量索引与补算（`make embed`） |
| `query/conditions`、`query/fusion` | 结构条件编译为 Cypher（Search 与 Traverse 共用）；召回参数、分词与 RRF 融合 |
| `query/view`、`query/materials` | 读视图（节点带全部模型出边、只读字段以 `_` 开头）与只读字段；按引用找材料、按哈希读行 |
| `query/resolve` | Resolve 的三级解析，read / write 两种模式；Commit 的查重也用它 |
| `commit/translate`、`commit/checks` | graph-doc → 物理目标状态（kind → Label，name / aliases → NameKey，material → Material 等）；写入后状态的模型检查 |
| `commit/submit`、`commit/reader` | `prepare`（dry_run，只读）与 `apply`（分配 id 后经 graph-vc 单事务提交）；内存与 Neo4j 两种读取 |
| `commit/review`、`commit/report` | 查重与删除影响；返回给 Agent 的 graph-plan 与 graph-result |
| `artifact/document`、`artifact/write`、`artifact/stale` | Artifact 文档的头部、数据块与记录键；共同写入路径（引用核对、幂等、文档、`USED` 边与一次提交）；读取时计算的可能过期 |
| `yamlfmt` | YAML 输出格式 |

## 现在还不是什么

neo4j-e09 已按新写入路径重建（2026-10-05，`commit_000001`–`000004`）：两份种子与两篇论文（2023-DLinear、2023-PatchTST），共 22 组实验。全部算子已实现，但库中还没有 Artifact；
历史查询与 I3 的检验代码尚未实现。notebook 不能成为文档引用数字的唯一来源（AGENTS.md）。
