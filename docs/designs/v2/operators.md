# 算子契约

> **状态：** 本文是 V2 的现行算子契约，规定全部算子的定义、输入输出、校验与图模式映射。算子分两部分：中间件算子（Search、Resolve、Traverse、ReadEvidence、Commit）负责对知识库的定位、导航、读原文与入库；Agent 算子（Extract、Summarize、Generate、Check、Verify、Filter、MatrixConstruct）规定 Agent 使用知识时的工作行为，每次调用的结果持久化为第四类节点 Artifact。Agent 算子的名称沿用 AgenticScholar（[S]：Table 2 与 Appendix D），定义按本项目的使用场景与职责边界重新规定。对象与关系见 [Graph Model V2](./graph_model_v2.md)，入库见 `docs/experiments/e09/operators/commit.md`（早先的表单契约见 [Commit 契约](./commit_contract.md)），intent 与数据流见 [Workload 拆解](./intents_decompose.md)。E09 的实现状态见第 9 节。

## 1. 总览

### 1.1 两部分算子

| 部分 | 算子 | 谁执行 | 结果 |
| --- | --- | --- | --- |
| 中间件算子 | `Search`、`Resolve`、`Traverse`、`ReadEvidence` | 中间件，确定性执行 | 任务内返回，不写库 |
| 中间件算子 | `Commit` | 中间件，确定性执行 | graph-doc 入库 |
| Agent 算子：生成 | `Extract`、`Summarize`、`Generate` | Agent 生成内容，中间件校验 | 每次调用写一个 Artifact |
| Agent 算子：判断 | `Check`、`Verify`、`Filter` | Agent 给出逐项判断，中间件校验 | 同上 |
| Agent 算子：组织 | `MatrixConstruct` | Agent 填写矩阵，中间件校验表格结构 | 同上 |

Agent 能用的工具就是这 12 个算子。中间件算子回答"库里有什么、原文写了什么"；Agent 算子记录"Agent 用这些做了什么"。

### 1.2 职责边界

- **中间件不调用 LLM。** Agent 算子的内容（抽取值、概述、判断）由 Agent 生成后作为参数交给中间件；中间件只校验结构、引用与出处，并持久化。跨论文的组织（`MatrixConstruct`）也由 Agent 填写：记录在 Artifact 文档中而不在图里，中间件不对其排序、分组或透视，只校验声明的表格结构。这与 AgenticScholar 不同：后者的这些算子是系统内部的一次 LLM 调用。
- **所有写入经同一版本底层。** 每次写入先校验，再经 graph-vc 在一个事务中写入并产生一个提交记录（版本历史），提交后补算向量。`Commit` 是提交 graph-doc 的算子；Agent 算子不是 `Commit`，但它们写 Artifact 时使用同一底层（第 5.5 节）。校验不通过时不写入，返回错误。
- **引用参数只接收已确认的 id。** 名称先经 `Resolve`，语义候选经 Agent 确认（通常用 `Filter`）后才能作为引用参数。
- **关系存在不是证据强度。** 路径、参与关系与 `USED` 只说明记录了这些关联；`SUPPORTED_BY`、`SUPPORTS` / `OPPOSES` 记录的是作者或 Agent 的陈述，不经验证。
- **空结果不等于原文没有。** 论文表单选择性录入，按批次记录的 `coverage` 区分"原文没有报告"与"没有录入"（[Commit 契约](./commit_contract.md) §6）。数值、条件与结果行不在库中，由 Agent 读原文后经 `Extract` 取得。

### 1.3 设计取向：质量优先

Agent 算子要求声明输入、逐项给出判断与依据、在正文中标注引用，并把每次结果持久化。这些要求使回答和报告可以核查、可以复用，代价是更多的调用与 token。因此评测与叙事以回答和报告的质量为主（正确性、可核查性、依据是否充分、能否复用），不主张单次任务的成本优势；成本作为代价如实报告。

## 2. 共同约定

### 2.1 引用

| 引用 | 形式 | 指向 |
| --- | --- | --- |
| 对象引用 | `<kind 前缀>_<序号>`，如 `method_0027`、`exp_0012`、`art_0003` | 一个节点；由入库分配，当前不修订、不合并 |
| 来源引用 `source_ref` | `<material_id>::<章节>::<start>:<end>` | 一份固定材料（论文原文或 Artifact 文档）中的行范围；由 `FROM {material_ref, locators}` 或 `USED {material_ref, locators}` 逐个定位拼出 |
| 记录引用 | `<artifact id>#<key>` | Artifact 中的一条记录（如 `Extract` 的一行、`Filter` 的一项、`MatrixConstruct` 的一格），`key` 为该记录的键 |

正文中的引用处直接写引用本身，放在方括号里，例如 `[exp_0012]`、`[art_0003#dlinear-etth1-96]`、`[material_1ec346c934e6::5.3 ...::245:290]`。Agent 算子的文本、产物文档与最终回答都用这一写法，不另设脚注编号。

### 2.2 对象视图

`Traverse` 返回的对象视图就是 graph-doc（读写同形，格式见 `docs/experiments/e09/operators/commit.md` §2 与 §6 R）：`nodes` 以对象 id 为键，字段按写入时的拼写给出，原样交回 `Commit` 为 `noop`。

- **字段。** `kind`、`name`、`aliases`（由 NameKey 装配，不含与 `name` 规范化后相同的写法）、`identifiers`、`stub`、`year`、`material`、`definition` / `description` / `text`、`anchors`、`stated_by`、`note` 等；自然键（`exp_key`、`content_key`）与 `embedding` 等派生属性不出现。
- **关系。** 每个节点带它**全部**的模型出边，一个关系键列出该类型出边的完整集合（只列一部分交回时会删掉其余的边）；边上的属性写在边里，如 `{to, role}`、`{to, locators}`。入边不出现在节点上，经 `Traverse` 沿入边走到对方节点，对方节点的出边里就有这条边。
- **只读字段**以 `_` 开头，交回时被忽略：有材料的节点与 `FROM` 边的 `_material`（材料 id），Agent 形成的记录与正反关系的 `_formed_by`、`_formed_at`。
- **Artifact** 只由 Agent 算子写入，字段全部只读：`_op`、`_title`、`_abs`、`_params`、`_formed_by`、`_formed_at`、`_session`、`_material`、`_document`（文档路径）、`_stale`（第 5.6 节）与 `_USED`（`{to, role?, locators?}`，带来源引用的边另有 `_material`）。

Observation 的 `ABOUT` 始终给出完整的对象集合：某个对象命中不代表结论对它单独成立。

### 2.3 AccessResult

`Traverse` 返回读视图：一份 graph-doc，`nodes` 是结果涉及的对象视图（第 2.2 节），`meta` 是 AccessResult。`Search` 返回结果视图（第 3.1 节），只有摘录，不带关系；它的 `meta` 是下表中的一部分，其余字段写入日志：

```text
AccessResult = {query, items, bindings, source_refs, missing, coverage, continuation, diagnostics}
```

| 字段 | 内容 |
| --- | --- |
| `query` | 本次请求的参数 |
| `items` | 主体结果的 id，按结果顺序去重；下一步取 `refs(X)` 默认只取这里的引用 |
| `bindings` | 每个结果的取得依据：`Search` 为精确命中的方式，或各通道的名次与融合分（按结果 id 给出；按结构条件枚举时为空；只写入日志），`Traverse` 为每条路径，写成节点与关系交替的列表，如 `[method_0028, <-EVALUATES-, exp_0001, -USES->, dataset_0006]`；边上属性在起点一侧节点的出边里 |
| `source_refs` | 结果涉及的来源引用（写成材料 id 的形式），按出现顺序去重；只定位，不读取 |
| `missing` | 库中不存在的引用参数：`{ref, param, missing_in: store}` |
| `coverage` | 参数、范围、预算、已匹配与返回数量、是否截断、通道状态、快照（当前提交的 id） |
| `continuation` | 截断时的续取位置；为空表示已取完 |
| `diagnostics` | 不进入结果、但调用方需要知道的数量与引用，例如角色缺失、可展开的额外匹配 |

`Traverse` 的 `nodes` 是本页路径上的全部节点（起点、中间节点与终点）。

### 2.4 预算、错误与会话

- **预算**是一次调用返回的主体结果数上限；截断必须可见（`Traverse` 在 `coverage` 中，`Search` 为非空的 `continuation`），续取时传回 `continuation`，其余参数不变。
- **契约错误**（未知参数、类型不符的引用、该类别不支持的条件、图模型中不存在的端点组合）直接报错，不返回部分结果。所有算子没有完成时的返回同形：`{status, errors}`，`status` 为 `rejected`（请求没有被执行，什么也没有写入）、`blocked`（`Commit` 的阻塞项）或 `conflict`（提交时与并发写入冲突），`errors` 的每一项为 `{rule, at, msg}`，`at` 指向出错的参数或节点，`Commit` 的阻塞项另带 `candidates` 与 `fix`。请求的顶层形状不对（未知参数、缺少必填参数）记为 `format`，参数的取值不对记为 `schema`。
- **数据缺失**（引用不在库中、关系无记录）返回空集合与覆盖信息，不当作错误。
- **执行失败**（向量服务不可用、索引缺失）记入通道状态（`Search` 为 `meta.failed`）；因失败而没有结果时不当作空结果。
- **会话**：Agent 算子的会话标识 `session` 与形成者 `formed_by` 记在 Artifact 上，用于按会话追溯产物。二者是调用环境的信息，由调用方给出（MCP 服务：进程启动时生成的会话与环境变量 `E09_FORMED_BY`；命令行：`--session`、`--formed-by`），不是算子参数；算子作为工具时，参数中也没有 `op`，工具名就是算子名。

## 3. 中间件算子

### 3.1 Search

**用途：** 在一个类别内按查询与结构条件发现对象。lookup 用 `Resolve`，沿关系走用 `Traverse`。

```text
Search(type, query?, kinds?, where={}, expand={}, scope="global", budget, continuation?) -> AccessResult
```

| 参数 | 说明 |
| --- | --- |
| `type` | `Entity`、`Concept`、`Content` 或 `Artifact`，一次一个类别 |
| `query` | `{identifier?, mention?, text?}`；只给字符串时视为 `text`。省略时按结构条件枚举，按 `id` 排序 |
| `kinds` | 类内类型，如 `{Experiment, Claim}`；Artifact 没有 kind，用 `where.op` |
| `where` | 结构条件，见下表；多个条件取合取，同一条件给列表时取析取；Content 上的多个条件绑定同一条记录 |
| `expand` | 放宽 `where` 中的引用条件：`narrower: depth`（Concept，反向 `BROADER`）、`parts: depth`（Entity，反向 `PART_OF`），深度 1–3 |
| `scope` | `"global"` 或论文 id 列表；论文列表只作用于 Content（`FROM` 这些论文的记录） |

**查询分量与通道：**

| 类别 | 接受的分量 | 通道 |
| --- | --- | --- |
| Entity | `identifier`、`mention`、`text` | 标识精确匹配；名称词面（NameKey）；description 全文与向量 |
| Concept | `mention`、`text` | 名称词面；definition（陈述型为 text）全文与向量 |
| Content | `text` | text 全文与向量 |
| Artifact | `text` | `title` 与 `abs` 的全文与向量 |

标识与 NameKey 精确命中按声明的优先规则排在前面，不参与融合计分；其余通道按 RRF 融合，跨类别不比较原始分数，不设阈值。向量索引按主 Label 建立，先超取再按 kind 与 `where` 过滤，可能漏掉条件内的可行候选，超取倍数与过滤方式记入 `coverage`。

**结构条件：**

| 类别 | 条件 | 图模式 |
| --- | --- | --- |
| Entity | `part_of: ref` | `(x)-[:PART_OF]->(ref)` |
| Entity | `for_task: ref` | `(x)-[:FOR_TASK]->(ref)` |
| Entity / Concept | `stub: bool` | `x.stub` |
| Concept | `broader: ref` | `(x)-[:BROADER]->(ref)` |
| Content | `about: ref` | `(x)-[:ABOUT]->(ref)` |
| Content | `from: paper_ref` | `(x)-[:FROM]->(paper)` |
| Content | `stated_by: paper \| agent` | Contribution 的 `stated_by` |
| Content | `formed_by: str` | Agent 形成的记录的 `formed_by` |
| Experiment | `evaluates: ref`，可加 `role: target \| baseline` | `(x)-[:EVALUATES {role}]->(ref)` |
| Experiment | `uses: ref` | `(x)-[:USES {role: evaluation_data}]->(ref)` |
| Experiment | `on_task: ref` | `(x)-[:ON_TASK]->(ref)` |
| Experiment | `evaluated_on: ref` | `(x)-[:EVALUATED_ON]->(ref)` |
| Claim | `supported_by: ref` | `(x)-[:SUPPORTED_BY]->(ref)` |
| Artifact | `op`、`formed_by`、`session` | Artifact 属性 |
| Artifact | `used: ref` | `(x)-[:USED]->(ref)` |

**诊断：** 写了 `uses` 条件时，另报 `role_missing`（`USES` 指向该数据集但没有 `role` 的实验）与 `expandable`（评测数据落在其组成部分上、本次没有用 `expand.parts` 选中的实验），只给数量与引用。

**默认不查 Artifact。** `type` 为 Entity、Concept、Content 时结果中不出现 Artifact；要找已有的工作产物，显式写 `type=Artifact`。

**输出：** 结果视图 `{results, meta}`，不是 graph-doc。Search 只负责发现：每个结果给识别字段与检索字段的开头摘录，不带关系；对象的完整字段与全部关系用 `Traverse` 读取（`path` 为空即读取起点对象），原文用 `ReadEvidence` 读取。

| 类别 | 识别字段 | 摘录字段 |
| --- | --- | --- |
| Entity | `id`、`kind`、`name`、`year` | `description` |
| Concept | `id`、`kind`、`name` | `definition` 或 `text` |
| Content | `id`、`kind`、`paper`（`FROM` 的论文 id）、`anchors`、`source_refs` | `text`，另有 `note` |
| Artifact | `id`、`op`、`title`、`document`（文档路径）、`stale`（有时） | `abs` |

摘录字段即该类别全文与向量检索的字段；Content 另带 `note`，原文中的问题（印刷错误、推断的设置）常记在这里。

**容量。** MCP 客户端会截断过长的工具结果（pi 为 20 KB，截掉中间部分，且不能配置），所以整份结果按 YAML 字节数控制在 16 KB 以内：先放下各结果的识别字段与 `meta`，放不下时从末尾去掉结果、续取位置随之前移；余下的容量平均分给各结果的摘录，摘录本来就短的结果省下的部分再平均分给其余结果；一个结果内先给 `text` 再给 `note`。超出份额的字段在 UTF-8 字符边界截断，末尾写 `…`，其后的 `<字段>_bytes` 给出原文长度。

`meta` 为 `returned`、`matched`、`continuation`、`snapshot`、`size`（`{limit, used, cut}`，`cut` 是被截断的字段数），以及非空时的 `missing`、`diagnostics`、`expanded`（`expand` 实际放宽到的引用）与 `failed`（失败的通道及原因）。取得依据与覆盖信息（通道状态、候选池、向量超取）写入日志 `e09.search`（MCP 服务写在 stderr 与 `E09_MCP_LOG`）。

**不做的事：** 不接受自然语言的 `where`；不按语义判断"是否适用"；Benchmark 引用不当作数据集条件。

### 3.2 Resolve

**用途：** 把一个说法解析为 Entity 或 Concept 的引用。`Commit` 的查重也调用它（write 模式）。

```text
Resolve(query={identifier?, mention?, text?}, kind, scope="global", mode=read | write)
  -> {stage: id | alias | semantic, status: resolved | ambiguous | candidates | none | unprocessed,
      refs, match_trace, states, coverage, execution: ok | partial | error}
```

- **只解析 Entity 与 Concept。** Content 与 Artifact 没有称呼，用 `Search` 定位。
- **三级解析：** 已注册标识（唯一命名空间单个命中即 resolved，非唯一命名空间只缩小候选）→ NameKey 精确键（active 键唯一命中即 resolved）→ 名称词面、文本、向量三通道按 RRF 融合的语义候选。标识与名称同时给出时取交集；名称命中了对象而交集为空时记 `resolution=conflicting`。
- **mode：** read 模式前两级 resolved 即停止；write 模式仍跑语义查重，近邻记入 `match_trace`。
- **不设阈值。** 库中没有的对象通常以 `candidates` 返回；"库中没有"由 Agent 对候选逐个否定（`Filter`，条件为同一对象）得出。因执行失败而没有引用时为 `unprocessed`，不当作 `none`。

| 返回 | 下游处理 |
| --- | --- |
| `resolved` | 直接采用引用 |
| `ambiguous` | Agent 在 `refs` 中确认；`resolution=conflicting` 时另作数据问题报告，不自动采用任一侧 |
| `candidates` | Agent 逐个确认；全部否定时记 `resolution=missing`、`missing_in=store` |
| `none` | 保留为未解决项，需要时经 `Commit` 新建对象 |
| `unprocessed` | 进入错误出口 |

同一任务中按说法键 `(raw, kind, scope)` 去重。新写法经确认后，经 `Commit` 的 `register` 注册为 alias。

### 3.3 Traverse

**用途：** 从已确认的引用出发，沿声明的关系走到相关对象，保留路径与边上属性。路径为空时只返回起点的对象视图（即"按 id 读取"）。

```text
Traverse(start, path=[], budget, continuation?) -> AccessResult
hop = {rel, dir: out | in | both, kinds?, where?, edge?, depth?: 1–3}
```

| 参数 | 说明 |
| --- | --- |
| `start` | 起点引用列表，可混合类别 |
| `path` | 0–3 跳；每跳一个 `hop` |
| `hop.rel` | 关系类型或其列表，只能取下表中的类型 |
| `hop.dir` | 方向；对称关系 `OVERLAPS_WITH` 忽略方向 |
| `hop.kinds` | 该跳终点的类型限制，如 `{Experiment}`、`{Artifact}` |
| `hop.where` | 终点的结构条件，与 `Search` 同表 |
| `hop.edge` | 边上属性条件，如 `{role: target}`、`{stated_by: agent}`；边上属性是列表时（`USED` 的 `role`、`locators`）按包含匹配 |
| `hop.depth` | 只用于传递性关系（`BROADER`、`PART_OF`、`HAS_PART`、`DERIVED_FROM`）的可变长匹配；不重复走同一条边，环在此截断。`USED` 不是传递性关系，沿产物的输入链往回走时逐跳写出 |

**可走的关系：** `FROM`、`ABOUT`、`EVALUATES`、`USES`、`ON_TASK`、`EVALUATED_ON`、`SUPPORTED_BY`、`SUPPORTS`、`OPPOSES`、`PART_OF`、`DERIVED_FROM`、`CITES`、`IMPLEMENTS`、`FOR_TASK`、`BROADER`、`HAS_PART`、`ADDRESSES`、`OVERLAPS_WITH`、`USED`。系统关系 `NAMES`、`MATERIAL_OF` 不对外开放：别名在视图中，文档在 Artifact 视图的 `_document` 中。

**校验：** 每一跳按图模型的端点表（[Graph Model V2](./graph_model_v2.md) §6）检查起点类型、关系、方向与终点类型能否成立，不成立是契约错误，例如从 Method 出发沿出边走 `EVALUATES`。

**输出：** 读视图（第 2.3 节）。`items` 为最后一跳的终点（去重）；`nodes` 为本页路径上的全部节点；`bindings` 为每条路径，写成节点与关系交替的列表，关系带方向（`-REL->` 或 `<-REL-`）。边上属性（`role`、`description`、`stated_by`、`locators` 等）在起点一侧节点的出边里，原样给出。正反关系保留真实方向，不推导传递关系。预算按路径计，截断时报告已见数量。

**常用路径：**

| 想取得 | `Traverse` |
| --- | --- |
| 对象本身 | `Traverse([x])` |
| 讨论某对象的主张 | `Traverse([m], [{rel: ABOUT, dir: in, kinds: {Claim}}])` |
| 评测了某方法的实验 | `Traverse([m], [{rel: EVALUATES, dir: in}])` |
| 主张的依据实验及其数据 | `Traverse([c], [{rel: SUPPORTED_BY, dir: out}, {rel: USES, dir: out}])` |
| 主张的正反关系 | `Traverse([c], [{rel: [SUPPORTS, OPPOSES], dir: both}])` |
| 论文的引用与被引 | `Traverse([p], [{rel: CITES, dir: both}])` |
| Benchmark 的成员数据集 | `Traverse([b], [{rel: PART_OF, dir: in, depth: 2}])` |
| 用过某篇论文的工作产物 | `Traverse([p], [{rel: USED, dir: in, kinds: {Artifact}}])` |

### 3.4 ReadEvidence

**用途：** 按来源引用读取固定材料中的行。论文原文与 Artifact 文档都是材料，读法相同。

```text
ReadEvidence(source_refs) -> {items, missing, coverage}
```

引用的开头写材料 id，或写带材料的节点 id（论文或 Artifact），两者等价。按 Material 节点的路径与内容哈希读取，只定位与读取，不解释内容；读到的每行带行号，便于引用其中更小的范围。逐项记录材料状态：`available`（读到，且文件哈希与入库时一致）、`missing`（引用格式不对、库中没有该材料或文件不在）、`error`（文件哈希变了或行号越界；不返回可能错位的文本）。`missing` 列出状态为 `missing` 的引用，各状态的数量在 `coverage` 中。

### 3.5 Commit

**用途：** 把论文知识与 Agent 的理解入库。提交物是 graph-doc（读写同形的子图，交上来的就是想要的状态），设计见 `docs/experiments/e09/operators/commit.md`：graph-doc → dry_run 返回 graph-plan（修改、阻塞项及候选与改法、提示）→ Agent 按阻塞项修改后重交 → apply（graph-vc 单事务提交，产生一个提交记录，提交后补算向量）返回 graph-result。新建、修改、删除与合并都用同一写法；早先的论文表单与增补表单（[Commit 契约](./commit_contract.md)）已转成 graph-doc。

graph-doc 可以引用 Artifact：Observation 的 `ABOUT` 可指向 Artifact，`FROM` 可指向 Artifact 并带其文档的行范围，这是把工作产物提升为长期记录的途径（第 5.7 节）。Artifact 本身不能经 `Commit` 新建或修改；删除被 `USED` 指向的节点时，dry_run 提示用过它的 Artifact 将显示为可能过期。

## 4. Agent 算子

### 4.1 共同契约

```text
<Op>(title?, abs, inputs, params, payload)        # 调用环境另给 session、formed_by
  -> {status: created | existing, artifact, commit, document, warnings, stats?, render}
   | {status: rejected | conflict, errors}
```

| 字段 | 说明 |
| --- | --- |
| `title` | 产物标题；省略时由中间件按 `op` 与参数生成 |
| `abs` | 几句话说明这个产物是什么、回答了什么，作为检索文本 |
| `inputs` | 用到的对象引用、来源引用、Artifact 或记录引用；每项写成一条 `USED` 边（第 5.2 节） |
| `params` | 各算子的声明参数，如抽取的 schema、检查维度、矩阵的行与列 |
| `payload` | Agent 生成的内容：记录、文本、逐项判断或矩阵的格子 |
| `session`、`formed_by` | 会话标识与形成者，由调用环境给出（第 2.4 节） |

`inputs` 必填。列入哪些输入、是否先读原文，由 Agent 的使用指南约定（实际用到的才列入，数值与判断应来自读过的原文或记录）；中间件不追踪 Agent 读过什么。

**共同校验（任一不过即整次拒绝，不写入）：**

1. `inputs` 是不重复的引用列表。其中的对象引用、Artifact 与记录引用都在库中（记录引用的键须出现在该 Artifact 文档的数据块中）；来源引用格式正确，所指材料在库中，文件与登记的哈希一致，行号不越界。
2. `params` 与 `payload` 中出现的每个引用（引用参数、`basis`、`source`、`ref` 字段与正文中方括号里的引用）都属于 `inputs`，即由 `inputs` 覆盖：与其中某一项相同；或是来源引用，所指的行落在同一材料的某个来源引用的行范围内（章节名不比较）；或是记录引用，所属的 Artifact 列在 `inputs` 中（记录须存在）；或是对象引用，正是某一项 `USED` 的终点（如论文，它的材料中的行已列在 `inputs` 中）。来源引用的开头写材料 id 或材料所属的节点 id 视为同一个引用。覆盖了某个引用的 `inputs` 项不再提示 `unused-input`。
3. `params` 与 `payload` 符合该算子的 schema；判断类的每个单元恰有一条判断（不能遗漏，也不能重复）。给了判断但不合格的单元只报不合格，不再另报遗漏。

**返回：** `status` 为 `created`，或相同调用的重试返回 `existing`（第 5.4 节，此时 `commit` 为空）；`artifact` 为 Artifact 的 id；`commit` 为本次写入的提交 id；`document` 为产物文档的路径与 `material_ref`；`stats` 为该算子的统计（目前只有 `Generate`）；`render` 是文档正文（不含头部），可以直接放进回答，引用按第 2.1 节的方括号写法；`warnings` 为不阻塞的提示：`unused-input`（某个输入没有在 `params` 与 `payload` 中被引用）、`embedding`（提交后补算向量失败，提交保留）。

**错误**的形状与 `Commit` 的阻塞项相同：`{rule, at, msg}`（第 2.4 节），`rule` 为 `format`（请求的形状）、`schema`（算子参数与内容）、`reference`（引用不在库中或不属于 `inputs`）、`judgment`（判断的取值、依据与覆盖）、`citation`（`Summarize` 的段落缺少引用）或 `conflict`（提交时与并发写入冲突）。命令行入口为 `python -m e09`（第 9 节）。

**判断的取值：** `T` 表示在声明的条件与依据下成立；`F` 表示有依据判断不成立；`U` 表示依据不足、相互冲突或条件含义不明。`T` 与 `F` 必须给出 `basis`（属于 `inputs` 的引用），`U` 必须给出 `reason`。执行中断与格式错误是 `errors`，不能写成 `U`。

**文档正文：** 每个产物的文档都是"头部 + 正文"（第 5.3 节），正文结构按算子规定，见各节的"正文"一项。需要被其他算子读取的产物（`Extract`、`Check`、`Filter`、`MatrixConstruct`）在正文末尾附一个 `yaml` 数据块，其余产物只有可读正文。

### 4.2 Extract

**用途：** 读原文后，把需要的具体信息取成结构化记录，例如结果表中的数值、实验设置、资源的发布地址。原文中的数值与条件经它进入任务。

```text
Extract(inputs, params: {schema: {fields: {name: type}, required: [...], key: [...]}},
        payload: {rows: [{<fields>, source}], note?})
```

- **字段类型：** `string`、`number`、`integer`、`boolean`、`ref`（图中对象引用）、`enum[...]`。单位、口径等写成独立字段，不混进数值。
- **`source`：** 每行的出处，为 `inputs` 中的一个引用。
- **记录键：** `key` 必填，列出决定一条记录的字段；记录键由这些字段的值依次转成小写、非字母数字换成 `-` 后用 `-` 连接，例如 `method_0003-dataset_0001-96`。
- **校验：** 字段名为标识符（字母开头，由字母、数字与 `_` 组成，`key` 与 `source` 保留）；每行只含声明的字段与 `source`，值符合类型；`required` 与 `key` 中的字段非空；记录键在本次产物中唯一；`ref` 字段与 `source` 的引用都属于 `inputs`（因而在库中）。
- **空结果：** `rows` 为空时必须写 `note`，说明读了什么、为什么没有，记录的是"材料中没有找到"。
- **正文：** 一张记录表（第一列为记录键，未填的字段写"—"，最后一列为出处）；`note`（如有）；数据块 `{schema, rows: [{key, <fields>, source}], note?}`。每条记录可用 `<artifact>#<key>` 引用。
- **不做的事：** 不跨行合并不同设置下的值，不换算单位，不补原文没有的值。

### 4.3 Summarize

**用途：** 把多份材料或记录忠实地压缩成概述，例如一个方法的机制要点、几篇论文的共同设置与差异。所有内容都可追溯到输入。

```text
Summarize(inputs, params: {focus}, payload: {text})
```

- **校验：** `text` 非空；**每个段落至少有一处引用**，引用都属于 `inputs`。段落以空行分隔，只有标题的段落不计。方括号中的内容全部是引用时才算引用（多个引用以逗号或分号分隔）；`[文字](链接)` 形式的 Markdown 链接不算。
- **正文：** `text` 原样。
- **与 Generate 的区别：** Summarize 只压缩与重组输入中已有的内容；需要推断、建议或新内容时用 `Generate`。

### 4.4 Generate

**用途：** 产出新内容：给用户的最终回答、写作草稿、研究点子、实验方案。

```text
Generate(inputs, params: {purpose: answer | draft | idea | plan | other}, payload: {text})
```

- **校验：** `text` 非空；出现的引用都属于 `inputs`。允许没有引用的段落；有引用的段落比例在返回的 `stats.cited_paragraphs` 中给出（如 `1/3`），不另存，需要时可从文档重算。
- **正文：** `text` 原样。
- **最终回答：** 回答中的数值、比较与判断应引用 `Extract`、`MatrixConstruct`、`Check`、`Verify` 的产物（第 6 节）。

### 4.5 Check

**用途：** 两条以上的记录在声明的维度上是否一致、是否可比，例如两组结果的数据集切分、预测长度、指标口径是否相同，或两篇论文的设置是否矛盾。

```text
Check(inputs, params: {items: {key: 引用}, pairs: [[k1, k2], ...] | all_pairs, dimensions: [{id, question}]},
      payload: {judgments: [{pair: [k1, k2], dimension, value: T | F | U, basis, reason}]})
```

- `items` 的引用可以是对象、记录或来源引用，至少两项。
- **校验：** 每个 `(pair, dimension)` 恰有一条判断；判断中的 `pair` 不计顺序，`[k2, k1]` 与声明的 `[k1, k2]` 是同一对。`all_pairs` 展开为 `items` 的全部两两组合。`T` 表示在该维度上一致或可比。
- **正文：** 一张判断表（行为成对的项，列为维度，单元格为 `T` / `F` / `U`）；其下逐条列出 `F` 与 `U` 的依据和原因；数据块 `{items, pairs, dimensions, judgments}`，`pairs` 按声明的顺序。每个对可用 `<artifact>#<k1>~<k2>` 引用，`k1`、`k2` 的顺序与 `pairs` 中相同。
- **不做的事：** 不给出总体结论（"这两组结果可比"）。维度的合取规则由调用方声明，或交给 `Generate` 说明。

### 4.6 Verify

**用途：** 一条主张在指定证据下是否成立，以及在什么范围内成立。例如核对论文的主张是否被它自己的实验支持，或某个结论在另一篇论文的结果下是否还成立。

```text
Verify(inputs: 证据, params: {claim: 引用 | {text}},
       payload: {value: T | F | U, conditions?, basis, reason})
```

- `claim` 可以是 Claim、Observation、记录引用，或一段写明的主张文本。
- `T` 表示证据支持，`F` 表示证据反驳，`U` 表示不足以判断。**没有找到支持不等于反驳**，应为 `U`。
- `conditions` 写成立的范围与限定，例如"仅在预测长度不超过 336 时成立"。
- **正文：** 一行结论（主张与 `T` / `F` / `U`）、成立范围、依据与原因。`claim` 为引用时，它也须属于 `inputs`，其 `USED` 边的 `role` 含 `claim`。
- 需要长期留存的结论，经 `Commit` 写成 Observation 或 Agent 的正反关系。

### 4.7 Filter

**用途：** 对一组对象逐项判断是否满足一个条件。这是最常用的判断：候选是不是同一个对象（`Resolve` 候选确认、入库查重）、方法是否适用于需求、记录是否与问题相关。

```text
Filter(inputs, params: {items: {key: 引用}, condition: {id, text}},
       payload: {judgments: [{key, value: T | F | U, basis, reason}]})
```

- **校验：** 每个 `key` 恰有一条判断。
- **正文：** 条件一行；按 `T` / `F` / `U` 分三节，每项一行（键、引用、依据或原因）；数据块 `{items, condition, judgments}`。`U` 不得当作 `F` 丢弃，必须保留。每项可用 `<artifact>#<key>` 引用。
- 后续只用 `T` 项时，在后续算子的 `inputs` 中引用这些项（`<artifact>#<key>`）。

### 4.8 MatrixConstruct

**用途：** 把跨论文的比较组织成一张矩阵，例如方法 × 数据集的结果表、Issue × Method 的研究空白矩阵、方法 × 设计要素的路线对比。矩阵由 Agent 填写，中间件只校验表格结构。

```text
MatrixConstruct(inputs,
                params: {rows: {key: 引用 | {text}}, columns: {key: 引用 | {text}},
                         cell: {type, question?}},
                payload: {cells: [{row, col, value, basis?, note?}], note?})
```

- **行与列：** 每个键对应一个引用（对象、记录或来源引用），或一段写明的标签 `{text}`。行、列中的引用写成 `USED` 边，`role` 记录键。
- **格子：** `type` 与 `Extract` 的字段类型相同（第 4.2 节），`T` / `F` / `U` 写作 `enum[T, F, U]`。`value` 可为 `null`，表示空格子。`basis` 与 `note` 可选，不由中间件强制；是否给出依据、空格子写明"未报告""不适用"还是"未查"，由使用指南引导（第 6 节）。
- **校验：** `rows`、`columns` 非空，键的写法与 `Check`、`Filter` 的项键相同；每个"行 × 列"恰有一个格子，不缺、不重复，不出现未声明的行或列；非空的 `value` 符合 `cell.type`；出现的引用（行、列、`ref` 类型的值、`basis`）都属于 `inputs`。不合格时按 `schema` 或 `reference` 报错。
- **不做的事：** 不核对格子的值是否等于所引用记录中的值，不判断同一列的值是否可比（可比性先经 `Check` 判断），不排序、不汇总。排名与结论在 `Generate` 中说明。
- **正文：** 一张矩阵表（行、列按声明的顺序，空格子写"—"，有 `basis` 的格子在值后附引用）；其下列出各格的 `note`；数据块 `{rows, columns, cell, cells}`，`cells` 按行优先、声明的顺序排列。每个格子可用 `<artifact>#<row>~<col>` 引用。

## 5. Artifact

### 5.1 定位

Artifact 是第四类节点，与 Entity、Concept、Content 并列：记录 Agent 使用知识时做出来的东西。前三类来自阅读论文，Artifact 来自使用。它是通用节点：不分子类型，不用语义关系连接其他节点，只记录"用什么产出了什么"。名称取自溯源模型 OPM 中的 Artifact（过程产出的不可变状态）。

### 5.2 节点与关系

```text
(:Artifact {id: art_<序号>, op, title, abs, params, formed_by, formed_at, session, artifact_key})
(a:Artifact)-[:USED {role?: [..], material_ref?, locators?: [..]}]->(x)    x 为任意 Entity、Concept、Content 或 Artifact
(m:Material {path, content_hash})-[:MATERIAL_OF]->(a:Artifact) 产物文档
```

| 属性 | 说明 |
| --- | --- |
| `op` | 产出它的 Agent 算子 |
| `title`、`abs` | 标题与摘要，与文档头部相同，参与检索与向量 |
| `params` | 调用参数（键排序后的 JSON 字符串） |
| `formed_by`、`formed_at`、`session` | 形成者、时间（写入时生成）与会话 |
| `artifact_key` | `op`、`inputs`、`params`、`payload` 与 `formed_by` 的哈希（SHA-256 的前 16 位），用于幂等；唯一约束 |

`USED` 的写法：

- 对象引用 → `USED` 指向该对象，`role` 取它在 `params` 中的角色（Check、Filter 的项键，Verify 的 `claim`），没有角色时省略；
- 来源引用 → `USED` 指向该材料所属的节点（论文或 Artifact），边上带 `material_ref` 与 `locators`，与 `FROM` 的写法相同；
- 记录引用 → `USED` 指向该记录所属的 Artifact，`role` 记录键。

同一 Artifact 到同一终点只有一条 `USED` 边（graph-vc 以起点、类型、终点标识一条边），所以 `role` 与 `locators` 都是列表：几个项键、记录键指向同一终点时合并为一个排序后的列表，同一材料的几个行范围合并到 `locators`。`USED` 只表示"产出时用到了它"，不表示支持、讨论或同一。

### 5.3 文档

每个 Artifact 有一份 Markdown 文档，登记为 Material（路径与内容哈希），因此可以用 `ReadEvidence` 读取、用来源引用引用其中的行。文档仿照 skill 文件，只有头部与正文：

```text
---
title: <自动生成或 Agent 撰写>
nodes_used: [<inputs 中的引用>]
abs: <Agent 撰写或自动生成>
---
<正文：结构按算子规定（第 4.2–4.8 节）>
<数据块（Extract、Check、Filter、MatrixConstruct）：正文末尾的 ```yaml 代码块>
```

- `nodes_used` 按 `inputs` 的顺序，来源引用统一写成材料 id 的形式，与 `ReadEvidence` 的写法相同。它是不可变的输入记录，读取时据此计算过期（第 5.6 节）。
- 数据块是文档中最后一个 `yaml` 代码块；记录引用按它解析。
- 文档按标题命名：存放在材料根目录下的 `artifacts/<标题>.md`，让读文件的 Agent 从文件名就能认出内容。标题中文件名不能用的字符换成空格，过长时按字节截断；文件名已被内容不同的文档占用时依次加 ` (1)`、` (2)`。对应的 Material id 仍由内容哈希给出（`material_<内容哈希前 12 位>`），与文件名无关，来源引用写的是 Material id。文件不进 git，版本由提交链记录（`docs/experiments/e09/operators/commit.md` §8.5）。
- `op`、形成者、时间与参数记在节点上，不重复写进文档。

### 5.4 身份与幂等

Artifact 没有同一性问题：不查重，不合并，只追加。相同 `artifact_key` 的调用视为重试，返回已有的 Artifact（`status: existing`），不重复写入。`session` 与 `title` 不在 `artifact_key` 中：换会话或只改标题的相同调用仍是重试。Artifact 及其文档写入后不修改，也不能经 `Commit` 修改或删除。

### 5.5 写入

Agent 算子校验通过后，经与 `Commit` 相同的版本底层（graph-vc）写入，顺序是：

1. 按 `artifact_key` 查找，已有则作为重试返回（第 5.4 节）；
2. 写文档：内容相同的文档已有 Material 时沿用它的文件；否则按标题取文件名，被内容不同的文件占用时加序号，同名文件内容相同时直接沿用；先写临时文件再改名；
3. 分配 id，在一个事务中写 Artifact 节点、`USED` 边、Material（同一文档已登记时不重复建）与 `MATERIAL_OF`，产生一个提交记录：`source` 为 `operator:<op>`，`author` 为 `formed_by`，`meta` 记 Artifact 的 id 与会话，`files` 记文档的路径与哈希；
4. 提交后补算 `title` 与 `abs` 的向量；失败不回滚，只在 `warnings` 中提示。

事务失败时文档文件留在原处：它没有节点引用，不影响库，重试时内容相同而直接复用。形成信息在节点与提交记录上。

### 5.6 检索与过期

- **默认不进入 Search 的结果**，见第 3.1 节；经 `Search(type=Artifact)` 或沿 `USED` 的 `Traverse` 取得。
- **过期在读取时计算，不存状态。** 视图的 `_stale` 逐项列出"可能过期"的原因 `{ref, reason}`：

  | `reason` | 含义 |
  | --- | --- |
  | `document` | Artifact 自己的文档文件不在，或内容与登记的哈希不同 |
  | `removed` | 文档头部 `nodes_used` 中的对象（或记录所属的 Artifact、来源引用的材料）已不在库中 |
  | `material` | 所用材料的文件不在，或哈希与登记的不同 |
  | `stale input` | 所用的 Artifact 本身可能过期（递归计算） |

  删除节点时 graph-doc 一并删掉指向它的 `USED` 边，所以 `removed` 按不可变的文档头部核对，而不是看现存的边。过期只是提示，不修改、不删除。
- **价值信号：** 被其他 Artifact `USED` 的次数、被 Observation 引用的次数，供检索排序与日后清理使用。

### 5.7 提升为长期记录

Artifact 是未经审定的工作痕迹；Observation 是由提交者明确写入的理解。需要长期留存的产物，经 `Commit` 写成 Observation：`ABOUT` 指向该 Artifact，`FROM` 指向该 Artifact 并带其文档的行范围（如 `{to: art_0003, locators: ["Check::12:20"]}`）。读取时两者分开呈现，不把 Artifact 当作已确认的结论。

## 6. 使用约定

- **按需使用。** 回答中含数值、比较或判断时使用 Agent 算子；简单的定位与阅读问题直接用中间件算子回答。
- **使用指南。** `inputs` 怎么填、何时先读原文、引用怎么写，由 Agent 配置中的使用指南简单约定（第 4.1 节），不由中间件强制。跨论文的比较与对照用 `MatrixConstruct` 整理成矩阵；格子尽量给出 `basis`，空格子在 `note` 中写明是未报告、不适用还是未查。
- **回答引用产物。** 最终回答中的数值、比较与判断应来自 Artifact，可直接粘贴其 `render`；每个数字都能经方括号中的引用追到记录与原文行。
- **结果默认折叠。** 在 Agent 应用中，Agent 算子的调用以一行摘要呈现（如"抽取 12 行结果""核对可比性：3 对可比、1 对不确定"），用户展开时再看产物。用户读的始终是对话中的回答。
- **判断与确认用 Filter。** `Resolve` 的候选确认、入库前的查重判断都以 `Filter`（条件为同一对象）记录，其成本计入构建成本。

## 7. 典型组合

以下组合用于检查算子是否覆盖六类 intent 的使用，不是固定流程。

| Intent | 组合 |
| --- | --- |
| I1 发现适合需求的方法 | `Search(Concept, kinds={Method})` → `Traverse` 取讨论它们的主张与实验 → `ReadEvidence` → `Filter`（是否适用）→ `Generate`（回答） |
| I2 理解机制与细节 | `Resolve` → `Traverse([m])` 及其 `ABOUT` 入边的 Content → `ReadEvidence` → `Extract`（设置细节）或 `Summarize`（机制要点） |
| I3 组织结果并判断可比性 | `Resolve` → `Search(Content, kinds={Experiment}, where={evaluates, uses})` → `ReadEvidence`（按锚点读表）→ `Extract`（结果行）→ `Check`（切分、长度、口径）→ `MatrixConstruct`（方法 × 数据集，可比的结果）→ `Generate` |
| I4 综合同一问题下的路线 | `Search(Concept, kinds={Issue})` → `Traverse` 取 `ABOUT` 它的主张与贡献 → `ReadEvidence` → `Extract`（路线要素）→ `MatrixConstruct`（Issue × Method）→ `Summarize` |
| I5 核查主张的依据 | `Search(Content, kinds={Claim})` → `Traverse`（`SUPPORTED_BY`、`SUPPORTS` / `OPPOSES`）→ `ReadEvidence` → `Verify` → 需要留存时经 `Commit` 写 Observation |
| I6 取得实现资源 | `Resolve` → `Traverse`（`IMPLEMENTS` 入边，当前无数据）或 `Search(Entity, kinds={Code, Model}, query)` → `ReadEvidence` → `Filter`（是否就是该实现）→ `Extract`（地址与设置） |

## 8. 本版不纳入

| 事项 | 原因与替代 |
| --- | --- |
| 预设语义的读取算子（Experiments、Evidence、Context、Implementations、Get） | 由 `Search` 的结构条件、`Traverse` 的路径与对象视图覆盖，不单列 |
| 关系检索 | 关系的 `description` 已建向量，但没有 workload 需要按关系检索；`Traverse` 返回边上的说明 |
| AgenticScholar 的 Rank、GroupBy、Aggregate 等对记录做计算的算子 | 记录在 Artifact 文档中而不在图里，中间件不对其排序、分组或计数。跨论文的组织由 Agent 经 `MatrixConstruct` 填写；排名与结论写在 `Generate` 中，可比性先经 `Check` 判断 |
| Artifact 的清理与归并 | 当前只追加；按价值信号清理留待有真实使用数据后再定 |
| Concept 精炼与整理 | 日后增加专门的工具或算子，整理 Claim 与 Issue、Proposition 并建立正反关系 |

## 9. E09 实现对照

模块都在 `experiments/e09/src/e09/` 下。每个算子一个文件，定义一个 `Operator`（`operators/base.py`：名称、参数的 JSON Schema 与执行），按名称登记在 `operators.OPERATORS` 中。
通用 Agent 经 MCP 服务 PaperWeave（`python -m e09.mcp`）使用算子：每个算子一个工具，给模型看的文字（`instructions`、
工具的标题与说明、参数说明）都在 `mcp/server.yml`，启动时与算子的结构装配成工具；`Commit` 只在 `E09_ENABLE_COMMIT=1`
时列出。工具的每个顶层参数都声明一种确定的 JSON 类型（列表参数是数组，`query` 是对象，`Commit.doc` 是 YAML 文本），
不用 `anyOf`：按 `type` 转换参数的工具调用解析器（如 sglang 解析 qwen 的工具调用）会把只有 `anyOf` 的参数当作字符串。
算子本身仍接受单个字符串、`scope="global"` 等写法。
顶层的对象与数组参数在暴露的 schema 中也接受字符串：`Operator.call` 执行前按算子的 schema 兜底修复参数（`operators/repair.py`：JSON 文本解析并补齐末尾缺少的括号、字面量转换、枚举的大小写与 `true`/`false` 判断），来源引用的写法偏差由 `model/refs.py` 的 `normalize_ref` 兜底；修复不告诉 Agent，只记在服务日志中（stderr 与 `E09_MCP_LOG`）。命令行入口 `python -m e09`
的请求以 `op` 为算子名；直接给 graph-doc 时视为 `Commit`。两个入口经同一个 `Operator.call`，结果相同。共用的支持放在与
`operators/` 同级的包中，依赖方向为 `operators → commit、artifact、query → store、model`。

| 算子 | 模块 | 状态 |
| --- | --- | --- |
| `Search` | `operators/db/search.py` | 已实现，含 `type=Artifact` |
| `Resolve` | `operators/db/resolve.py`，三级解析在 `query/resolve.py` | 已实现；`Commit` 的查重也用它 |
| `Traverse` | `operators/db/traverse.py` | 已实现，含 `USED` |
| `ReadEvidence` | `operators/db/read_evidence.py` | 已实现，可读 Artifact 文档 |
| `Commit` | `operators/db/commit.py`，写入管线在 `commit/` | 已实现：graph-doc → graph-plan / graph-result，经 graph-vc 提交 |
| `Extract`、`Summarize`、`Generate`、`Check`、`Verify`、`Filter`、`MatrixConstruct` | `operators/agent/<算子>.py`（各算子的校验、正文与数据块），共用部件在 `operators/agent/_common.py` | 已实现 |

| 支持 | 模块 |
| --- | --- |
| 结构条件、RRF 融合、读视图与只读字段、Search 的结果视图、固定材料 | `query/conditions.py`、`query/fusion.py`、`query/view.py`、`query/excerpts.py`、`query/materials.py` |
| Artifact 的文档格式、共同写入路径、可能过期 | `artifact/document.py`、`artifact/write.py`、`artifact/stale.py` |
| 数据模型、引用写法、名称精确键 | `model/schema.py`、`model/refs.py`、`model/namekey.py` |
| 算子环境、库的版本记录与约束索引、连接、向量 | `store/store.py`、`store/database.py`、`store/graph.py`、`store/embedding.py` |

测试在 `experiments/e09/tests/operators/db/` 与 `tests/operators/agent/`，只在空的测试实例（`GRAPH_VC_TEST_NEO4J_URI`）上运行；写入管线的测试在 `tests/commit/`。neo4j-e09 中还没有 Artifact；Artifact 的约束与全文、向量索引在下一次写入时建立。

**参考：** [S] Hai Lan et al. *AgenticScholar: Agentic Data Management with Pipeline Orchestration for Scholarly Corpora.* PACMMOD 4(2), Article 131, 2026（本地精读见 `references/papers/2026-AgenticScholar-reread/`）。
