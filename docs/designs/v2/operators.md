# 算子契约

> **状态：** 本文是 V2 的现行算子契约，规定全部算子的定义、输入输出、校验与图模式映射。算子分两部分：中间件算子（Search、Resolve、Traverse、ReadEvidence、Commit）负责对知识库的定位、导航、读原文与入库；Agent 算子（Extract、Summarize、Generate、Check、Verify、Filter、Rank、MatrixConstruct）规定 Agent 使用知识时的工作行为，每次调用的结果持久化为第四类节点 Artifact。Agent 算子的名称沿用 AgenticScholar（[S]：Table 2 与 Appendix D），定义按本项目的使用场景与职责边界重新规定。对象与关系见 [Graph Model V2](./graph_model_v2.md)，表单入库见 [Commit 契约](./commit_contract.md)，intent 与数据流见 [Workload 拆解](./intents_decompose.md)。E09 的实现状态见第 9 节。

## 1. 总览

### 1.1 两部分算子

| 部分 | 算子 | 谁执行 | 结果 |
| --- | --- | --- | --- |
| 中间件算子 | `Search`、`Resolve`、`Traverse`、`ReadEvidence` | 中间件，确定性执行 | 任务内返回，不写库 |
| 中间件算子 | `Commit` | 中间件，确定性执行 | 论文表单与增补表单入库 |
| Agent 算子：生成 | `Extract`、`Summarize`、`Generate` | Agent 生成内容，中间件校验 | 每次调用写一个 Artifact |
| Agent 算子：判断 | `Check`、`Verify`、`Filter` | Agent 给出逐项判断，中间件校验 | 同上 |
| Agent 算子：组织 | `Rank`、`MatrixConstruct` | 中间件对已有 Artifact 记录确定执行 | 同上 |

Agent 能用的工具就是这 13 个算子。中间件算子回答"库里有什么、原文写了什么"；Agent 算子记录"Agent 用这些做了什么"。

### 1.2 职责边界

- **中间件不调用 LLM。** Agent 算子的内容（抽取值、概述、判断）由 Agent 生成后作为参数交给中间件；中间件只校验结构、引用与出处，并持久化。`Rank` 与 `MatrixConstruct` 只对结构化记录做排序与透视，由中间件执行。这与 AgenticScholar 不同：后者的这些算子是系统内部的一次 LLM 调用。
- **所有写入经同一提交机制。** 校验、单事务写入、写后复核与补算向量。`Commit` 是提交表单的算子；Agent 算子不是 `Commit`，但它们写 Artifact 时使用同一机制（第 5.5 节）。校验不通过时不写入，返回错误。
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
| 记录引用 | `<artifact id>#<key>` | Artifact 中的一条记录（如 `Extract` 的一行、`Filter` 的一项），`key` 为该记录的键 |

正文中的引用处直接写引用本身，放在方括号里，例如 `[exp_0012]`、`[art_0003#dlinear-etth1-96]`、`[material_1ec346c934e6::5.3 ...::245:290]`。Agent 算子的文本、产物文档与最终回答都用这一写法，不另设脚注编号。

### 2.2 对象视图

中间件算子返回的对象都使用以下视图。视图不含 `embedding`、`embedding_key` 等派生属性。Content 与 Artifact 的视图带出边的一跳引用（只有 id、名称与边上的角色），方便直接沿引用继续 `Traverse`；入边与边上的说明文字只经 `Traverse` 取得。

| 类别 | 视图字段 |
| --- | --- |
| Entity / Concept | `ref`、`family`、`kind`、`name`、`aliases`（由 NameKey 装配）、`identifiers`、`stub`、`properties`（description / definition / text、note 等） |
| Content（共有） | `ref`、`family`、`kind`、`text`、`source`（`paper`、`material_ref`、`locators`）、`source_refs`、`about`（全部 `ABOUT` 目标）；自然键 `exp_key` 或 `content_key`；`stated_by`（Contribution）；`formed_by`、`formed_at`（Agent 形成的记录） |
| Experiment（另有） | `anchors`、`evaluates`（ref、name、role）、`uses`（ref、name、role）、`on_task`、`evaluated_on` |
| Claim（另有） | `supported_by`（实验或观察的 ref） |
| Artifact | `ref`、`family`、`op`、`title`、`abs`、`formed_by`、`formed_at`、`document`（`material_ref` 与路径）、`used`（ref 与 role）、`stale`（第 5.6 节） |

Observation 的 `about` 始终给出完整的对象集合：某个对象命中不代表结论对它单独成立。

### 2.3 AccessResult

`Search` 与 `Traverse` 返回：

```text
AccessResult = {items, bindings, source_refs, missing, coverage, continuation, diagnostics}
```

| 字段 | 内容 |
| --- | --- |
| `items` | 主体结果的对象视图，按结果顺序去重；下一步取 `refs(X)` 默认只取这里的引用 |
| `bindings` | 每个结果的取得依据：`Search` 为命中的条件与通道，`Traverse` 为从起点到该结果的路径（每跳的关系、方向、边上属性与中间节点） |
| `source_refs` | 结果涉及的来源引用，按出现顺序去重；只定位，不读取 |
| `missing` | 库中不存在的引用参数：`{ref, param, missing_in: store}` |
| `coverage` | 参数、范围、预算、已匹配与返回数量、是否截断、通道状态、快照（最新 `IngestBatch` 的 id） |
| `continuation` | 截断时的续取位置；为空表示已取完 |
| `diagnostics` | 不进入结果、但调用方需要知道的数量与引用，例如角色缺失、可展开的额外匹配 |

### 2.4 预算、错误与会话

- **预算**是一次调用返回的主体结果数上限；截断必须在 `coverage` 中可见，续取时传回 `continuation`，其余参数不变。
- **契约错误**（未知参数、类型不符的引用、该类别不支持的条件、图模型中不存在的端点组合）直接报错，不返回部分结果。
- **数据缺失**（引用不在库中、关系无记录）返回空集合与覆盖信息，不当作错误。
- **执行失败**（向量服务不可用、索引缺失）记入 `coverage` 的通道状态；因失败而没有结果时不当作空结果。
- **会话**：Agent 算子带会话标识 `session`，记在 Artifact 上，用于按会话追溯产物。

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

**不做的事：** 不接受自然语言的 `where`；不按语义判断"是否适用"；Benchmark 引用不当作数据集条件。

### 3.2 Resolve

**用途：** 把一个说法解析为 Entity 或 Concept 的引用。表单入库的查重也调用它（write 模式）。

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
| `none` | 保留为未解决项，需要时由表单入库新建对象 |
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
| `hop.edge` | 边上属性条件，如 `{role: target}`、`{stated_by: agent}` |
| `hop.depth` | 只用于传递性关系（`BROADER`、`PART_OF`、`HAS_PART`、`DERIVED_FROM`）的可变长匹配；不重复走同一条边，环在此截断 |

**可走的关系：** `FROM`、`ABOUT`、`EVALUATES`、`USES`、`ON_TASK`、`EVALUATED_ON`、`SUPPORTED_BY`、`SUPPORTS`、`OPPOSES`、`PART_OF`、`DERIVED_FROM`、`CITES`、`IMPLEMENTS`、`FOR_TASK`、`BROADER`、`HAS_PART`、`ADDRESSES`、`OVERLAPS_WITH`、`USED`。系统关系 `NAMES`、`MATERIAL_OF` 不对外开放：别名在视图中，文档在 Artifact 视图的 `document` 中。

**校验：** 每一跳按图模型的端点表（[Graph Model V2](./graph_model_v2.md) §6）检查起点类型、关系、方向与终点类型能否成立，不成立是契约错误，例如从 Method 出发沿出边走 `EVALUATES`。

**输出：** `items` 为最后一跳终点的对象视图（去重）；`bindings` 为每条路径 `{start, hops: [{rel, dir, edge, node}]}`，边上属性原样返回（`role`、`description`、`stated_by`、`formed_by`、`formed_at`、`source_refs`、`locators` 等）。正反关系保留真实方向，不推导传递关系。预算按路径计，截断时报告已见数量。

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
ReadEvidence(source_refs) -> {items, missing, states, coverage}
```

按 Material 节点的路径与内容哈希读取，只定位与读取，不解释内容。逐项记录材料状态：`available`（读到，且文件哈希与入库时一致）、`missing`（引用格式不对、库中没有该材料或文件不在）、`error`（文件哈希变了或行号越界；不返回可能错位的文本）。

### 3.5 Commit

**用途：** 把论文表单与增补表单入库。契约见 [Commit 契约](./commit_contract.md)：表单 → compile → dry_run 返回结构化 plan → Agent 按阻塞项修改表单并重跑 → apply（单事务、写后复核、补算向量）。论文表单与增补表单共用同一入口与阻塞项格式。

增补表单可以引用 Artifact：Observation 的 `about` 可指向 Artifact，`basis` 可指向 Artifact 文档的行范围，这是把工作产物提升为长期记录的途径（第 5.7 节）。

## 4. Agent 算子

### 4.1 共同契约

```text
<Op>(title?, abs, inputs, params, payload, session, formed_by)
  -> {artifact, document, render, warnings} | {errors}
```

| 字段 | 说明 |
| --- | --- |
| `title` | 产物标题；省略时由中间件按 `op` 与参数生成 |
| `abs` | 几句话说明这个产物是什么、回答了什么，作为检索文本；`Rank`、`MatrixConstruct` 可省略，由参数自动生成 |
| `inputs` | 用到的对象引用、来源引用、Artifact 或记录引用；每项写成一条 `USED` 边（第 5.2 节） |
| `params` | 各算子的声明参数，如抽取的 schema、检查维度、排序字段 |
| `payload` | Agent 生成的内容：记录、文本或逐项判断；`Rank`、`MatrixConstruct` 没有 |
| `session`、`formed_by` | 会话标识与形成者 |

`inputs` 必填。列入哪些输入、是否先读原文，由 Agent 的使用指南约定（实际用到的才列入，数值与判断应来自读过的原文或记录）；中间件不追踪 Agent 读过什么。

**共同校验（任一不过即整次拒绝，不写入）：**

1. `inputs` 中的对象引用、Artifact 与记录引用都在库中；来源引用格式正确，所指材料在库中。
2. `payload` 中出现的每个引用都属于 `inputs`。
3. `params` 与 `payload` 符合该算子的 schema；判断类的每个单元恰有一条判断（不能遗漏，也不能重复）。

**返回：** `artifact` 为新 Artifact 的 id；`document` 为产物文档的路径与 `material_ref`；`render` 是文档正文，可以直接放进回答，引用按第 2.1 节的方括号写法；`warnings` 为不阻塞的提示，例如某个输入没有在正文中被引用。错误的形状与 `Commit` 的阻塞项相同：`{rule, where, msg}`。

**判断的取值：** `T` 表示在声明的条件与依据下成立；`F` 表示有依据判断不成立；`U` 表示依据不足、相互冲突或条件含义不明。`T` 与 `F` 必须给出 `basis`（属于 `inputs` 的引用），`U` 必须给出 `reason`。执行中断与格式错误是 `errors`，不能写成 `U`。

**文档正文：** 每个产物的文档都是"头部 + 正文"（第 5.3 节），正文结构按算子规定，见各节的"正文"一项。需要被其他算子读取的产物（`Extract`、`Check`、`Filter`）在正文末尾附一个 `yaml` 数据块，其余产物只有可读正文。

### 4.2 Extract

**用途：** 读原文后，把需要的具体信息取成结构化记录，例如结果表中的数值、实验设置、资源的发布地址。原文中的数值与条件经它进入任务。

```text
Extract(inputs, params: {schema: {fields: {name: type}, required: [...], key: [...]}},
        payload: {rows: [{<fields>, source}], note?})
```

- **字段类型：** `string`、`number`、`integer`、`boolean`、`ref`（图中对象引用）、`enum[...]`。单位、口径等写成独立字段，不混进数值。
- **`source`：** 每行的出处，为 `inputs` 中的一个引用。
- **校验：** 每行符合 schema；`required` 字段非空；`key` 在本次产物中唯一；`ref` 字段的对象在库中。
- **空结果：** `rows` 为空时必须写 `note`，说明读了什么、为什么没有，记录的是"材料中没有找到"。
- **正文：** 一张记录表（每行一个键，最后一列为出处）；`note`（如有）；数据块 `{schema, rows}`。每条记录可用 `<artifact>#<key>` 引用。
- **不做的事：** 不跨行合并不同设置下的值，不换算单位，不补原文没有的值。

### 4.3 Summarize

**用途：** 把多份材料或记录忠实地压缩成概述，例如一个方法的机制要点、几篇论文的共同设置与差异。所有内容都可追溯到输入。

```text
Summarize(inputs, params: {focus}, payload: {text})
```

- **校验：** `text` 非空；**每个段落至少有一处引用**，引用都属于 `inputs`。
- **正文：** `text` 原样。
- **与 Generate 的区别：** Summarize 只压缩与重组输入中已有的内容；需要推断、建议或新内容时用 `Generate`。

### 4.4 Generate

**用途：** 产出新内容：给用户的最终回答、写作草稿、研究点子、实验方案。

```text
Generate(inputs, params: {purpose: answer | draft | idea | plan | other}, payload: {text})
```

- **校验：** `text` 非空；出现的引用都属于 `inputs`。允许没有引用的段落，Artifact 记录有引用的段落比例。
- **正文：** `text` 原样。
- **最终回答：** 回答中的数值、比较与判断应引用 `Extract`、`MatrixConstruct`、`Check`、`Verify` 的产物（第 6 节）。

### 4.5 Check

**用途：** 两条以上的记录在声明的维度上是否一致、是否可比，例如两组结果的数据集切分、预测长度、指标口径是否相同，或两篇论文的设置是否矛盾。

```text
Check(inputs, params: {items: {key: 引用}, pairs: [[k1, k2], ...] | all_pairs, dimensions: [{id, question}]},
      payload: {judgments: [{pair: [k1, k2], dimension, value: T | F | U, basis, reason}]})
```

- `items` 的引用可以是对象、记录或来源引用，至少两项。
- **校验：** 每个 `(pair, dimension)` 恰有一条判断。`T` 表示在该维度上一致或可比。
- **正文：** 一张判断表（行为成对的项，列为维度，单元格为 `T` / `F` / `U`）；其下逐条列出 `F` 与 `U` 的依据和原因；数据块 `{items, dimensions, judgments}`。每个对可用 `<artifact>#<k1>~<k2>` 引用。
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
- **正文：** 一行结论（主张与 `T` / `F` / `U`）、成立范围、依据与原因。
- 需要长期留存的结论，经增补表单写成 Observation 或 Agent 的正反关系。

### 4.7 Filter

**用途：** 对一组对象逐项判断是否满足一个条件。这是最常用的判断：候选是不是同一个对象（`Resolve` 候选确认、入库查重）、方法是否适用于需求、记录是否与问题相关。

```text
Filter(inputs, params: {items: {key: 引用}, condition: {id, text}},
       payload: {judgments: [{key, value: T | F | U, basis, reason}]})
```

- **校验：** 每个 `key` 恰有一条判断。
- **正文：** 条件一行；按 `T` / `F` / `U` 分三节，每项一行（键、引用、依据或原因）；数据块 `{items, condition, judgments}`。`U` 不得当作 `F` 丢弃，必须保留。
- 其他算子可用 `keep: <Filter 产物>` 只取 `T` 项（第 4.8、4.9 节）。

### 4.8 Rank

**用途：** 按可度量的字段给记录排序，例如同一数据集、同一指标下各方法的结果。由中间件执行。

```text
Rank(inputs: Extract 产物, params: {by: [{field, order: asc | desc}], group_by?, where?, keep?, top_k?})
```

- **语义：** 先按 `where`（字段相等条件）与 `keep`（Filter 产物中的 `T` 项）筛选，再按 `group_by` 分组，组内按 `by` 排序；并列取相同名次。缺少 `by` 字段的记录列入 `unranked`。
- **可比性由调用方保证。** `group_by` 应包括决定可比性的字段（如数据集、预测长度、指标）；是否真的可比由 `Check` 判断后经 `Filter` 或 `keep` 传入。Rank 本身不判断可比性。
- **正文：** 每组一张排名表（名次、记录引用、排序字段的值）；`unranked` 列表。
- **不做的事：** 不排语义准则（"哪个方法更有前景"）。这类排序先用 `Check` 或 `Filter` 做判断，再用 `Generate` 说明。

### 4.9 MatrixConstruct

**用途：** 把记录透视成表或矩阵，例如方法 × 数据集的结果表、Issue × Method 的研究空白矩阵、按方法计数的论文分布。由中间件执行。

```text
MatrixConstruct(inputs: Extract 产物（可多个，字段同名）,
                params: {rows: field, columns: field, value: field | count, aggregate?: none | count | min | max | mean,
                         where?, keep?})
```

- **语义：** 筛选同 `Rank`；以 `rows`、`columns` 字段的取值为行列，单元格放 `value` 字段的值。`aggregate=none` 时同一格有多个值就全部列出，不隐式合并；`count` 用于分组计数，覆盖 GroupBy 与 Aggregate 的用途。
- **空单元格**写"—"，表示输入的记录中没有，不表示原文或世界上不存在。
- **正文：** 一张矩阵表，每格写值与产生它的记录引用。

## 5. Artifact

### 5.1 定位

Artifact 是第四类节点，与 Entity、Concept、Content 并列：记录 Agent 使用知识时做出来的东西。前三类来自阅读论文，Artifact 来自使用。它是通用节点：不分子类型，不用语义关系连接其他节点，只记录"用什么产出了什么"。名称取自溯源模型 OPM 中的 Artifact（过程产出的不可变状态）。

### 5.2 节点与关系

```text
(:Artifact {id: art_<序号>, op, title, abs, params, formed_by, formed_at, session, artifact_key})
(a:Artifact)-[:USED {role?, material_ref?, locators?}]->(x)    x 为任意 Entity、Concept、Content 或 Artifact
(m:Material {path, content_hash})-[:MATERIAL_OF]->(a:Artifact) 产物文档
```

| 属性 | 说明 |
| --- | --- |
| `op` | 产出它的 Agent 算子 |
| `title`、`abs` | 标题与摘要，与文档头部相同，参与检索与向量 |
| `params` | 调用参数（JSON 字符串） |
| `formed_by`、`formed_at`、`session` | 形成者、时间（写入时生成）与会话 |
| `artifact_key` | `op`、`inputs`、`params`、`payload` 与 `formed_by` 的哈希，用于幂等 |

`USED` 的写法：

- 对象引用 → `USED` 指向该对象，`role` 取 `params` 中的角色（如 Check 的 item 键），可省略；
- 来源引用 → `USED` 指向该材料所属的节点（论文或 Artifact），边上带 `material_ref` 与 `locators`，与 `FROM` 的写法相同；
- 记录引用 → `USED` 指向该记录所属的 Artifact，`role` 记录键。

`USED` 只表示"产出时用到了它"，不表示支持、讨论或同一。

### 5.3 文档

每个 Artifact 有一份 Markdown 文档，登记为 Material（路径与内容哈希），因此可以用 `ReadEvidence` 读取、用来源引用引用其中的行。文档仿照 skill 文件，只有头部与正文：

```text
---
title: <自动生成或 Agent 撰写>
nodes_used: [<inputs 中的引用>]
abs: <Agent 撰写或自动生成>
---
<正文：结构按算子规定（第 4.2–4.9 节）>
```

`op`、形成者、时间与参数记在节点上，不重复写进文档。

### 5.4 身份与幂等

Artifact 没有同一性问题：不查重，不合并，只追加。相同 `artifact_key` 的调用视为重试，返回已有的 Artifact，不重复写入。Artifact 及其文档写入后不修改。

### 5.5 写入

Agent 算子校验通过后，经与 `Commit` 相同的提交机制写入（[Commit 契约](./commit_contract.md) §7）：单事务写节点、`USED` 边、Material 与 `MATERIAL_OF`；写后复核（节点与边都在，文档哈希一致）；补算 `title` 与 `abs` 的向量。文档先写到文件再登记哈希，事务失败时文件作废，不留节点。Artifact 不写 `IngestBatch`，形成信息在节点上。

### 5.6 检索与过期

- **默认不进入 Search 的结果**，见第 3.1 节；经 `Search(type=Artifact)` 或沿 `USED` 的 `Traverse` 取得。
- **过期在读取时计算，不存状态。** 视图的 `stale` 列出"可能过期"的原因：某个 `USED` 目标已不在库中、所用材料的文件哈希与登记的不同，或所用的 Artifact 本身 `stale`。过期只是提示，不修改、不删除。
- **价值信号：** 被其他 Artifact `USED` 的次数、被 Observation 引用的次数，供检索排序与日后清理使用。

### 5.7 提升为长期记录

Artifact 是未经审定的工作痕迹；Observation 是由提交者明确写入的理解。需要长期留存的产物，经增补表单写成 Observation：`about` 指向该 Artifact，`basis` 指向其文档的行范围。读取时两者分开呈现，不把 Artifact 当作已确认的结论。

## 6. 使用约定

- **按需使用。** 回答中含数值、比较或判断时使用 Agent 算子；简单的定位与阅读问题直接用中间件算子回答。
- **使用指南。** `inputs` 怎么填、何时先读原文、引用怎么写，由 Agent 配置中的使用指南简单约定（第 4.1 节），不由中间件强制。
- **回答引用产物。** 最终回答中的数值、比较与判断应来自 Artifact，可直接粘贴其 `render`；每个数字都能经方括号中的引用追到记录与原文行。
- **结果默认折叠。** 在 Agent 应用中，Agent 算子的调用以一行摘要呈现（如"抽取 12 行结果""核对可比性：3 对可比、1 对不确定"），用户展开时再看产物。用户读的始终是对话中的回答。
- **判断与确认用 Filter。** `Resolve` 的候选确认、入库前的查重判断都以 `Filter`（条件为同一对象）记录，其成本计入构建成本。

## 7. 典型组合

以下组合用于检查算子是否覆盖六类 intent 的使用，不是固定流程。

| Intent | 组合 |
| --- | --- |
| I1 发现适合需求的方法 | `Search(Concept, kinds={Method})` → `Traverse` 取讨论它们的主张与实验 → `ReadEvidence` → `Filter`（是否适用）→ `Generate`（回答） |
| I2 理解机制与细节 | `Resolve` → `Traverse([m])` 及其 `ABOUT` 入边的 Content → `ReadEvidence` → `Extract`（设置细节）或 `Summarize`（机制要点） |
| I3 组织结果并判断可比性 | `Resolve` → `Search(Content, kinds={Experiment}, where={evaluates, uses})` → `ReadEvidence`（按锚点读表）→ `Extract`（结果行）→ `Check`（切分、长度、口径）→ `MatrixConstruct` 或 `Rank`（`keep` 可比项）→ `Generate` |
| I4 综合同一问题下的路线 | `Search(Concept, kinds={Issue})` → `Traverse` 取 `ABOUT` 它的主张与贡献 → `ReadEvidence` → `Extract`（路线要素）→ `MatrixConstruct`（Issue × Method）→ `Summarize` |
| I5 核查主张的依据 | `Search(Content, kinds={Claim})` → `Traverse`（`SUPPORTED_BY`、`SUPPORTS` / `OPPOSES`）→ `ReadEvidence` → `Verify` → 需要留存时经增补表单写 Observation |
| I6 取得实现资源 | `Resolve` → `Traverse`（`IMPLEMENTS` 入边，当前无数据）或 `Search(Entity, kinds={Code, Model}, query)` → `ReadEvidence` → `Filter`（是否就是该实现）→ `Extract`（地址与设置） |

## 8. 本版不纳入

| 事项 | 原因与替代 |
| --- | --- |
| 预设语义的读取算子（Experiments、Evidence、Context、Implementations、Get） | 由 `Search` 的结构条件、`Traverse` 的路径与对象视图覆盖，不单列 |
| 关系检索 | 关系的 `description` 已建向量，但没有 workload 需要按关系检索；`Traverse` 返回边上的说明 |
| AgenticScholar 的 GroupBy、Aggregate、语义 Filter 以外的关系式算子 | 分组与计数由 `MatrixConstruct` 覆盖；确定性的字段筛选是 `Rank`、`MatrixConstruct` 的 `where` |
| Artifact 的清理与归并 | 当前只追加；按价值信号清理留待有真实使用数据后再定 |
| Concept 精炼与整理 | 日后增加专门的工具或算子，整理 Claim 与 Issue、Proposition 并建立正反关系 |

## 9. E09 实现对照

| 算子 | 模块 | 状态 |
| --- | --- | --- |
| `Commit` | `operators/commit/`，入口 `e09.commit` | 已实现，对齐冻结模型 |
| `Resolve` | `operators/resolve.py` | 已实现 |
| `ReadEvidence` | `operators/read_evidence.py` | 已实现 |
| `Traverse` | `operators/get.py` 只覆盖空路径（Entity / Concept） | 待实现；对象视图扩展到 Content 与 Artifact |
| `Search` | — | 待实现 |
| Agent 算子与 Artifact | — | 待实现；图模型见 [Graph Model V2](./graph_model_v2.md) 第 8 节，写入见 [Commit 契约](./commit_contract.md) §7。增补表单引用 Artifact（`art` 前缀、以 Artifact 文档为 `basis`）的代码尚待补上 |
| `operators/experiments.py` | — | 按旧模型实现，由 `Search` 取代后删除 |

实现顺序跟随 I3：`Traverse` 与对象视图 → `Search` → Artifact 写入机制 → `Extract`、`Check`、`MatrixConstruct`、`Rank`、`Generate` → 其余 Agent 算子。

**参考：** [S] Hai Lan et al. *AgenticScholar: Agentic Data Management with Pipeline Orchestration for Scholarly Corpora.* PACMMOD 4(2), Article 131, 2026（本地精读见 `references/papers/2026-AgenticScholar-reread/`）。
