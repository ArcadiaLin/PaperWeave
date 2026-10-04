# Graph Model V2

> **状态：** 候选清单（2026-10-02）；第 7 节第 1–10 项已与用户确认。Paper、Method、Dataset、Metric、Task、Experiment 及其参与边、`CITES` 已经两篇论文（DLinear、PatchTST）的入库检验（E09，2026-10-03，见 [Commit 契约](./commit_contract.md)）；同日第一个 I3 实例试跑后，Experiment 改为按研究问题分组、只存描述与定位（4.2、4.4、6.2.1），其余部分尚未经真实论文检验。2026-10-04 增加"定位"一节（节点只存轻度提炼、锚点与关联），据此退役 ResultUnit（4.3）；Metric 首版不建（3.1）。列出由 workload 拆解得到的候选 Node 与 Relationship，并标出需要重新考虑的 Property。Q1–Q8 指 [v2 未定模型问题与写路径](../../discussions/2026-10-01-v2-open-model-decisions-and-write-path.md) 中的编号；D1–D11 指已定决策，正文见 [Workload 拆解](./intents_decompose.md)。

`V2` 设计一个面向研究 Agent 的论文知识图：保存阅读后形成的索引（轻度提炼、原文锚点与关联），通过论文引用、共享方法、资源和命题连接不同论文，让后续研究能够查找、比较和复用已有经验。

相较于 [Graph Model V1](../v1/graph_model.md) 的设计，注重 `Entity`、`Concept`、`Content` 三类区别，Label 采用 `Entity.<sublabel>`、`Concept.<sublabel>`、`Content.<sublabel>` 来划分，且在理论上由 [Workload 拆解](./intents_decompose.md) 与实际数据（待试验，目前仍然是半成品）经验支持。

采用 Neo4j 的 Labeled Property Graph 模型，统一使用 `Node`、`Relationship`、`Label`、`Type`、`Property` 描述。概念依据见 [Neo4j 图模型](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/)。

```text
Graph Model
│
├── Node
│    ├── Entity     资源对象：Paper、Dataset、Split、Code、Model …
│    ├── Concept    定义对象：Method、Task、Protocol、Issue、Proposition（Metric 首版不建）
│    ├── Content    来源化内容：Claim、Experiment、Usage、Observation、Assessment …
│    └── 系统记录   NameKey、Material（支撑解析与来源，不是语义对象）
│
├── Relationship
│    ├── 视角一：三类之间的关联（3 × 3 矩阵）
│    └── 视角二：完整关系清单（Type、端点、Property）
```

## 定位：节点存什么（已定，2026-10-04）

图与精读稿的分工不同：

| | 精读稿 | 图 |
| --- | --- | --- |
| 范围 | 单篇论文 | 跨论文 |
| 形态 | 非结构化，高度提炼的转述 | 结构化，轻度提炼的索引 |
| 用途 | 读懂一篇论文 | 从知识关联的角度找到该读的论文、实验与位置 |

图的收益只来自**关联、检索、发现与复用**，规模越大越明显；读原文就能得到的内容，图不重复保存。精读稿不进入图。

因此节点不转录原文，存的是：

| 内容 | 写法 | 例子 |
| --- | --- | --- |
| 轻度提炼 | 用自己的话写到足以判断"要不要去读这里"为止，不写到足以替代阅读 | Experiment 的 `text`（目的、设计、论文的主张，4.2）；Concept 的 `definition`（3.2） |
| 阅读理解 | 结合任务形成的理解，开头注明任务与日期 | `note`（第 1 节） |
| 锚点 | 在原文哪里 | `FROM` 的 locators；Experiment 的 `anchors` |
| 关联 | 和谁有关、以什么角色 | 参与边、`CITES`、概念之间的关系 |

**不存锚点能直接给出的内容：** 数值、表格、超参数与实验设置、原文段落。判据来自第一个 I3 实例的试跑（2026-10-03）：一个字段如果 Agent 总要回原文核实才敢用，它就没有省下阅读。上一版实验上的 `setting`、疑点 `note`、变体标签与逐项来源都是这样，反而引入歧义，并把评测答案带进了图。

例外：

- **名称与标识**（`name`、NameKey、`identifiers`、`year`）：它们是查找的入口，必须结构化。
- **Paper 的摘要**：Paper 的 `description` 存摘要（2.2）。
- **没有原文可指的记录**（Observation 的环境与日志、Assessment 的依据）：它们本身就是第一手记录。
- **关系的说明**（如 `CITES.description`）：写这条关联为什么存在、该去读哪里，同样只写到判断"要不要读"为止。

据此修订（2026-10-04）：ResultUnit 退役（4.3）；Usage 若保留，只存概述与锚点（4.1）；实验实际采用的参数不入库（3.1、4.2、6.2.1）。

## 0. 记法与状态标记

- `Entity.Paper` 表示物理上的双 Label `(:Entity:Paper)`：主 Label 是类别，次级 Label 是类内 kind。语义对象恰好带一个主 Label 和一个次级 Label；系统记录只带自己的 Label。
- Cypher 片段只展示结构，属性值为示意。
- 本文是工程方案，名词可以与设计文档不同：设计文档中的逻辑字段（如 `kind`、`aliases`、`source_refs`）在这里映射到具体的 Label、Node 或 Relationship，映射关系在对应条目中说明。
- 与用户确认过的事项注明"已定（日期）"。

| 标记 | 含义 |
| --- | --- |
| 沿用 | v1 已有，含义不变 |
| 改写 | v1 已有，v2 契约已改变其名称、类型或语义（已定） |
| 新增 | v2 契约已要求，v1 没有（已定） |
| 候选 | 建议新增，尚未讨论确定 |
| 重审 | 值得重新考虑；给出倾向，入库前或实例后裁决 |
| 退役 | 建议不再保留，说明去向 |

## 1. 共同 Property

| Property | 含义 | 状态 | 说明 |
| --- | --- | --- | --- |
| `id` | 系统分配的无语义标识 | 沿用 | 只定位记录，不证明对象同一性 |
| `revision` | 修订号；引用写作 `ref={id, revision}` | 新增 | 修订如何产生未定（Q2）。倾向：Entity、Concept 原地修改并递增；Content 不可变，新修订经 `SUPERSEDES` 指向旧记录 |
| `kind` | 类内类型 | 改写 | **已定（2026-10-02）**：只用次级 Label 存储，不另存属性；设计文档中的逻辑字段 `kind` 由 Label 投影。`intents_decompose.md` §3.2 已加工程映射注解，§6.1 的 Cypher 已改写为 `(:Content:Experiment)` |
| `family` | Entity / Concept / Content | 改写 | 由主 Label 表达，不另存 |
| `source_refs` | 来源引用 `{entity_ref, material_ref, locator}` | 改写 | 取代 v1 的 `anchor` 字符串；存储方式见下 |
| `note` | 使用提醒、消歧线索；这一阶段也存任务相关的阅读理解 | 改写 | 不写定义。**已定（2026-10-02）**：v1 Paper `description` 中"结合当前任务对论文的理解"写入 note，开头注明任务与日期，例如 `[I3 比较 BM25 与 DPR, 2026-10-02] …`。note 不进检索面、没有版本；这类理解正是主张 A 要复用的经验，Q1 / Q5 讨论时再决定是否升级为 Content |
| `status` | `active / superseded / merged / retracted` | 候选 | 支撑 Q2 修订与 Q4 合并后的重定向；读路径默认只取 `active` |
| `committed_by` | 提交者类别（抽取 / Agent 判断 / 人工）及 call_id | 候选 | 来自 Q3 提交契约。v1 把这类信息放在增量日志中；若维护需要按提交者追溯，再提升为属性 |
| `embedding` 等派生属性 | 系统写入 | 沿用 | 不属于模型；计算位置见 Q8 |

**`source_refs` 的存储（已定，2026-10-02）。** Neo4j 属性不能是嵌套 map，SourceRef 的三个分量有两种放法：

| 方案 | 做法 | 取舍 |
| --- | --- | --- |
| A：`FROM` 关系 | `(:Content)-[:FROM {material_ref, locators: [...]}]->(:Entity:Paper)`，终点即 `entity_ref` | 可沿边按来源论文查询，`Context.source_contents` 直接使用；`intents_decompose.md` §3.4 已写"内容 → FROM → 材料实体" |
| B：字符串列表 | `source_refs: ["<material_ref>::<章节::start:end>"]`，沿用 v1 anchor 写法 | 简单；按来源论文查询需解析字符串 |

采用：**Node 用 A，Relationship 用 B**。关系不能再连出关系，而且关系的来源通常只需读取、不需导航。`locator` 沿用 v1 的 `<章节::start:end>` 口径。

B 的已知代价与应对：

- **反查困难。** "某篇论文或某份材料支持了哪些关系"无法沿边查询，只能扫描相关类型的边并匹配字符串。这主要影响维护（Q3）：材料更新或记录撤回时，查找依赖它的关系。
- **影响范围有限。** 实验参与边（`EVALUATES`、`USES` 等）的来源就是所属 Experiment 的 `FROM`，不另存；自带来源的主要是 `CITES`、`SUPPORTED_BY`、Claim 之间的关系、`IMPLEMENTS`、`ADDRESSES`。原型规模下扫描代价可以接受。
- **引用完整性。** 数据库不保证字符串中的 `material_ref` 存在，由写入契约检查。
- **升级路径。** 某类关系的来源需要频繁反查时（最可能是 `IMPLEMENTS`），把它物化为关联节点，使其也能有 `FROM`（§3.3）。

## 2. Entity：资源对象

### 2.1 次级 Label

| 次级 Label | 含义 | 状态 | v1 对应 | 说明 |
| --- | --- | --- | --- | --- |
| `Paper` | 书目对象 | 沿用 | `Paper` | 只表达书目；论文中的方法、主张、实验在其他对象中。被引但尚未入库的论文建桩节点（`stub`，只有参考文献中印的标题与引用线索，2026-10-03，[抽取原则](./extraction_principles.md) §8） |
| `Dataset` | 数据本身 | 改写 | `Resource:Dataset` | 主 Label 由 `Resource` 改为 `Entity` |
| `Split` | 数据切分 | 新增 | 写在描述中 | scope 为父数据集版本（D4），`PART_OF` 连到父版本 |
| `Code` | 代码仓库 | 改写 | `Resource:CodeRepo` | 改名 |
| `Model` | 权重、checkpoint 或 API 模型 | 沿用 | `Resource:Model` | |
| `Benchmark` | 数据 + 任务 + 评测协议 | 重审 | `Resource:Benchmark` | v2 可拆成 `Dataset` + `FOR_TASK` + `USES_PROTOCOL`，但论文常以 benchmark 名指称（如 BEIR），Resolve 需要能解析这个名称。倾向保留为 Entity，成员数据集以 `PART_OF` 连接，评测口径交给 Protocol |
| `Tool` | 非模型的软件、库、服务 | 重审 | `Resource:Tool` | v2 §3.2 未列，六类 intent 无直接需求。倾向暂不建，实例中出现再加 |

### 2.2 Property

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | 全部 | 精确键 | 改写 | **已定（2026-10-02）**：Paper 的 `title` 统一为 `name`，使 Resolve 的键在类内一致。精确键为 `(规范化 name/alias, type, kind, scope)`（D3）；`name` 留在对象上作主称呼，同时注册为一条 `NameKey` |
| `aliases` | 全部 | 精确键 | 改写 | v1：可重复，命中后再消歧；v2：写入时强制唯一，冲突拒绝（D3）。**已定（2026-10-02）**：不在对象上存列表，存为 `NameKey`（第 5 节）；`Get` 由 NameKey 装配 aliases 供阅读 |
| `identifiers` | 全部 | 精确匹配 | 新增 | 取代 v1 的 `s2_id`、`arxiv_id` 与 `url`。逻辑结构 `{namespace, value, version_scope}`。**已定（2026-10-02）**：存为字符串列表 `"<namespace>:<value>"`，如 `"arxiv:2005.11401"`、`"url:https://github.com/zhouhaoyi/ETDataset"`；唯一性按命名空间声明，重复时的处理见 2.4 |
| `description` | 全部 | 全文 / 向量 | 改写 | **已定（2026-10-02）**：Paper 的 `description` 存摘要，其他资源存内容与用途介绍。v1 中"Agent 对论文的概述"是结合当时任务形成的理解，这一阶段写入 `note`（见第 1 节） |
| `resource_version` | 版本节点 | 精确 | 新增 | 只在升级出版本节点时使用（2.3）；只用于定位，不跨资源比较大小 |
| `split_role` | Split | 否 | 候选 | train / dev / test：切分在数据集内声明的角色。实验实际怎样使用它写在 `USES.role` 上，二者不互推 |
| `year` | Paper | 否 | 沿用 | 若 I1 需要按年份过滤，再提升进检索面 |
| `paper_type` | Paper | 否 | 重审 | 六类 intent 未使用。倾向退役，或仅作描述字段 |
| `url` | Code、Dataset、Model | — | 改写 | **已定（2026-10-02）**：资源的官方入口并入 `identifiers` 的 `url` 命名空间（非唯一，见 2.4）；论文给出的具体链接属于 Usage |
| `markdown_path` | Paper | — | 退役 | 移到 `Material`（第 5 节），由 `material_ref` 引用 |
| `anchor` | Paper | — | 退役 | 摘要不需要锚点；概述的依据随 `note` 写明 |
| 作者、许可、安装说明等 | 全部 | 否 | 沿用 | 描述面，类内允许异构 |

### 2.3 版本与切分（已定，2026-10-02）

六类 intent 中只有两处关心资源版本：I3 把数据集版本作为可比性条件，I6 用 commit / checkpoint 判断核验记录是否适用（I2 仅在输出中注明版本）。版本因此不是独立需求，只在"是否可比""是否适用"两种判断中起作用。据此区分两种差异：

| 情况 | 例子 | 做法 |
| --- | --- | --- |
| 名称级差异 | FlashAttention 与 FlashAttention-2 | 不同实体，必要时以 `DERIVED_FROM` 关联；不算版本 |
| 修订级差异（默认） | 数据集 v2.0 与 v2.1、两个 commit、同一模型的两个快照 | 不建版本节点；版本字符串记在使用处的 `USES`、`EVALUATES`、`OBSERVES` 边的 `version` 属性上，来源未写则留空 |
| 修订版本自身需要挂结构 | 两个版本的切分或语料确实不同 | 才升级为版本节点：同一次级 Label，带 `resource_version` 与独立 `name`（如 `MS MARCO v2.1`），经 `VERSION_OF` 连到身份节点 |

```cypher
(:Entity:Split {name: "dev", split_role: "dev"})-[:PART_OF]->(d:Entity:Dataset {name: "MS MARCO"})
(e:Content:Experiment)-[:USES {role: "evaluation_data", version: "v2.1"}]->(d)
(o:Content:Observation)-[:OBSERVES {version: "a1b2c3d"}]->(:Entity:Code {name: "facebookresearch/DPR"})
```

- **未写版本**：自然归到原实体，不猜版本。
- **D4 不变**：切分的 scope 是 `PART_OF` 指向的节点，默认为身份节点，版本节点存在时为版本节点。上例中 `dev` 的精确键 scope 为 `MS MARCO`。
- **I3 规则**：两边 `version` 均有且相同输出 T；不同输出 U，由 Agent 判断差异是否重要，不直接判 F；任一方缺失输出 U，记 `missing_in=material`。
- **规范化**：`version` 字符串使用单独的版本化规范化配置（如统一大小写、去掉前缀 `v`），避免 `v2.1`、`V2.1`、`2.1` 被判为不同。NameKey 的 `name-key-v1` 保留大小写，不能直接套用；原字符串照常保留。
- **`include={versions}`**：只在存在版本节点时起作用。
- **实例中测量**：因数据版本被判为 U 的比较数量，及 Agent 最终判定其中多少确实不可比；若几乎都无关紧要，可进一步弱化边上的 `version`。

### 2.4 标识的唯一性与重复（已定，2026-10-02）

标识只用于匹配，不默认唯一。唯一性按命名空间在领域配置中声明，重复是正常输入，由算子报告，不靠改写模型或数据回避。

| 命名空间 | 唯一性 | 写入时重复 | 读取时多重命中 |
| --- | --- | --- | --- |
| `arxiv`、`doi`、`s2` | 唯一 | 拒绝写入，处理同 NameKey 冲突 | 正常不会发生；导入或核查发现的冲突隔离为 `ambiguous` |
| `url` | 非唯一：同一仓库可发布多个数据集（ETT 与 ETTh1–ETTm2 共用 `zhouhaoyi/ETDataset`），也可同时发布代码与模型 | 允许 | 多个命中时，Resolve 返回 `stage=id, status=ambiguous` 及全部命中，不静默落到下一级；只命中一个时返回 `candidates`，不单独确定身份 |

非唯一标识的多重命中缩小了候选范围，再按确定性规则继续缩小：

```text
id 级：   url = zhouhaoyi/ETDataset          → {ETT, ETTh1, ETTh2, ETTm1, ETTm2}
别名级：  mention = "ETTh1", kind = Dataset  → {ETTh1}
交集唯一  → status=resolved，match_trace 记录两级依据
仍不唯一或交集为空 → 保留 ambiguous，交外部 A_pred
名称命中了其他对象（如 mention = "Weather"）→ 交集为空且另记 resolution=conflicting
名称未注册 → 交集为空只是缺信息，不记冲突
```

写入模式下，非唯一标识的多重命中只作为查重候选，由外部判断新对象是其中之一还是同仓库中的另一个对象，不直接复用。同一原则适用于 alias 与 `version` 字符串：每条匹配规则都规定唯一命中、多重命中、无命中与数据冲突四种返回。

**工程实现（2026-10-02，E09）。** 唯一命名空间的标识存在对象的字符串列表里，后端唯一约束作用于整个属性值、管不到列表元素，所以由 `Commit` 在 dry_run 中检查、在写入事务内复查。如果需要由后端保证，可以仿照 NameKey，为唯一命名空间单独建键节点（第 7 节第 16 项）。上面的规则已在 E09 的种子图上逐条检验（`experiments/e09/notebooks/02_resolve_get.ipynb`）。

## 3. Concept：定义对象

### 3.1 次级 Label

| 次级 Label | 含义 | 状态 | v1 对应 | 说明 |
| --- | --- | --- | --- | --- |
| `Method` | 方法方案及方法类别 | 改写 | `Method` + `MethodConcept` | **已定（2026-10-02）**：合并为一个 kind，类别经 `BROADER` 表达（v1 的 `INSTANCE_OF` 与 `SUBTYPE_OF` 都并入）。代价是失去"具体方案 / 类别"的区分；若 I1 需要只取具体方案，加描述字段 `level: scheme / family`，不新增 kind。**`BROADER` 不承担变体（已定，2026-10-03）**：变体与配置不建节点，作为结果列的变体标签记在实验中，见 [抽取原则](./extraction_principles.md) §2 |
| `Task` | 研究任务 | 沿用 | `Task` | |
| `Metric` | 指标 | 首版不建（2026-10-04） | `Metric` | 指标在实验描述中说明，按锚点读原文。依据：LTSF 语料中几乎每个实验都测 MSE / MAE，按指标定位没有区分度；数值不入库后 `direction` 也无处可用；指标口径的可比性由 Agent 读原文判断。语料跨领域、按指标发现实验成为真实需求时再建。原设计：归入 Concept；定义必须写明影响可比性的口径，如 @k 与计算方式（D2） |
| `Protocol` | 评测协议或核验标准 | 新增 | 写在 Experiment 描述中 | 定义及修订有明确引用；一次实验实际采用的参数不入库，按锚点读原文（"定位"一节） |
| `Issue` | 研究问题 | 沿用 | `Issue` | 归类待 Q6 |
| `Proposition` | 跨来源的共同命题 | 改写 | `ClaimConcept` | 改名；归类待 Q6 |

### 3.2 Property

Method、Task、Protocol 是术语型，Issue、Proposition 是陈述型。两者的检索字段不同，这正是 Q6 的来源。

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | 术语型 | 精确键 | 沿用 | |
| `aliases` | 术语型 | 精确键 | 改写 | 同 Entity（D3） |
| `definition` | 术语型 | 全文 / 向量 | 改写 | 即 v1 的 `description`，改名后只写"是什么"，不写某篇论文怎么用 |
| `scope_note` | 术语型 | 全文 / 向量 | 候选 | 适用范围与区分边界，v1 写在 description 中。分开有利于"定义 + 范围"的固定编码，但增加抽取负担。倾向首版并入 `definition`，检索质量不足时再拆 |
| `scheme_ref` | 术语型 | 过滤 | 重审 | 外部定义体系（如某个任务分类表）。当前没有外部体系，倾向首版不设 |
| `text` | 陈述型 | 全文 / 向量 | 沿用 | 措辞中立，保留范围限定（v1 规则） |
| `description` | Issue | 否 | 沿用 | 争议所在与判断条件 |
| `direction` | Metric | 否 | 随 Metric 首版不建（2026-10-04） | 越大越好或越小越好。**已定（2026-10-02）**：放在 Metric 上，只定义一次。原则：能在定义层确定的，不让每次抽取重复判断 |
| `anchor` | Method、Metric | — | 退役 | 定义出处改由可选的 `FROM` 表达；定义由 Agent 归纳时没有单一来源 |

## 4. Content：来源化内容

### 4.1 次级 Label

| 次级 Label | 含义 | 状态 | v1 对应 | 来源责任 |
| --- | --- | --- | --- | --- |
| `Claim` | 论文作者的主张 | 沿用 | `Claim` | 作者，经抽取 |
| `Experiment` | 论文报告的一项实验 | 沿用 | `Experiment` | 作者，经抽取 |
| `Usage` | 论文对资源的描述或使用经验；若保留，只存概述与锚点，配置与原文说明按锚点读（2026-10-04） | 重审 | `ResourceRecord` | 作者，经抽取；Q5 |
| `Observation` | 一次第一手检查 | 沿用 | `Observation` | 检查执行者 |
| `Assessment` | Agent 对指定条件的判断 | 候选 | 无 | Agent，经确认；Q1 |
| `Contribution` | 论文自述的贡献 | 重审 | `Contribution` | 作者，经抽取；Q5 |

`Contribution` 的主要用途是 I1 的"论文提出了哪个方法"，这也可以由 Paper 到 Method 的带角色关系表达（Q7，见 6.2.4）。倾向首版不建 Contribution，I1 实例确有需要再加。

### 4.2 Property

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `text` | 全部 | 全文 / 向量 | 改写 | 可独立理解的内容描述。v1 中 Claim、Contribution 用 `text`，Experiment、ResourceRecord、Observation 用 `description`；v2 统一为 `text`，使 Content 类内检索字段一致。Experiment 的 `text` 是一组实验的描述：目的、设计、论文声称的结论，不写数值（[抽取原则](./extraction_principles.md) §4） |
| `source_refs`（`FROM`） | 除 Observation、Assessment | 限制条件 | 改写 | 见第 1 节 |
| `setting` | Experiment | — | 退役（2026-10-04；2026-10-03 起首版不用） | 条件与超参数是锚点能直接给出的内容，不入库（"定位"一节）；由 Agent 按锚点读原文判断，见 4.4 |
| `anchors`、`exp_key` | Experiment | 精确 | 新增（2026-10-03） | `anchors`：该组实验涉及的表、图锚点列表（如 `S4.T3`、`A1.T8`），第一个为主锚点；`exp_key = <论文 id>::<主锚点>` 是自然键。全部行范围（含正文）在 `FROM.locators` |
| `granularity` | Experiment | — | 退役（2026-10-04） | 原用于区分报告级与行级结果；ResultUnit 退役后结果只到实验级，不再区分 |
| `check_level` | Observation | 过滤 | 改写 | 即 v1 的 `kind`（repo_inspection / execution / reproduction）。v2 中 `kind` 已指类内类型，**已定（2026-10-02）**改名 |
| `observed_at` | Observation | 过滤 | 沿用 | |
| `target` | Observation | — | 改写 | 改为 `OBSERVES` 指向资源，commit 等精确版本写在 `OBSERVES.version` 上（2.3） |
| `environment` | Observation | 否 | 新增 | I6.3 适用性检查需要（§5.1.3） |
| `evidence` | Observation | 否 | 沿用 | 检查日志或产物路径，作用相当于 source_refs，但材料不是论文 |
| `condition_id`、`value`、`origin`、`rule_ref` / `call_id`、`rationale`、`made_at`、`validity` | Assessment | `condition_id` 精确 | 候选 | 即持久化的 `PredRow`：`value` 取 T / F / U，`origin` 取 rule / agent，`validity` 取 valid / stale。被判断对象与依据用关系表达（6.2.5），依据必须固定到 `{id, revision}` |

### 4.3 ResultUnit（退役，2026-10-04）

ResultUnit 曾是结果表一行的物理表示（2026-10-02 定）：D1 规定结果精度上限为表格行，行键为 `(被测对象 ref, 切分或版本 ref, 指标 ref)`，附数值、单位、方向与行锚点，由 `HAS_RESULT` 挂在 Experiment 下。2026-10-03 起首版不用；2026-10-04 按"定位"一节退役，D1 随之撤销：数值与行级对应都是锚点能直接给出的内容，结果只到实验这一级，比较时由 Agent 按锚点读原文。原设计见提交 `291375a` 中本文 4.3，行级入库的实现见提交 `f95631b`。

### 4.4 Experiment 的可比性条件哪些进入结构（已定，2026-10-02；首版修订，2026-10-03）

> **首版修订（2026-10-03）。** 第一个 I3 实例试跑后，首版只把**数据集与指标**作为参与关系存入结构（`USES`、`MEASURED_BY`），用于定位实验；切分约定 `cond_split`、版本与其余条件都不入库，由 Agent 按锚点读原文判断（[抽取原则](./extraction_principles.md) §4）。2026-10-04 起指标也不入结构（Metric 首版不建，3.1），只剩数据集。下表为 2026-10-02 的设计，保留为条件重新进入结构时的方案；其中"规则即可判定"的各项首版不运行。

D2 把四项可比性条件放进领域配置。它们在图中有不同的去处：

| 条件 | 去处 | 状态 |
| --- | --- | --- |
| 数据集版本与切分 | `USES` 指向 Split 或数据集，版本记在 `USES.version` 上（2.3）；原文只声明沿用某个切分约定时，记为 Experiment 的 `cond_split`（`convention:<name>`），见 [抽取原则](./extraction_principles.md) §4 | 已定 |
| 指标定义（含 @k） | `MEASURED_BY` 指向 Metric | 已定 |
| 候选集或语料 | `USES {role: "retrieval_corpus"}` 指向 Dataset | 已定：新增 USES role，规则即可判定 |
| 是否重排序 | `setting` 文本 | 已定：首版由 $A_{\text{pred}}$ 判断；I3 实例显示规则可以决定时再提升 |

进入结构的条件由规则判定，留在文本中的交给 Agent。这决定主张 B 的一项测量（规则与 Agent 各判定多少比较条件），而进入结构的抽取成本计入主张 A，实例中两边同时记录。`setting` 已退役（4.2），超参数不入库。

## 5. 系统记录

系统记录支撑解析与来源，不是语义对象，不进入任何类别的检索契约。

| Label | 作用 | 状态 | Property 与关系 |
| --- | --- | --- | --- |
| `NameKey` | 精确键注册表 | 新增 | **已定（2026-10-02）**。`key`（规范化名称、kind、scope 拼成的单个字符串，带唯一约束）、`normalized`、`raw`、`kind`、`scope`（global 或父对象 id）、`normalizer_ref`（属性不能存 map，编码为字符串，如 `name-key-v1@unicode-15.0.0`）、`status: active / ambiguous`、注册来源与提交者（`registered_from`、`registered_by`）；`(:NameKey)-[:NAMES]->(对象)` |
| `Material` | 固定版本的材料 | 新增（2026-10-03，[Commit 契约](./commit_contract.md)） | `path`、`format`、`content_hash`、`derived_from`（如原 PDF）、`created_at`；`(:Material)-[:MATERIAL_OF]->(:Entity:Paper)`；`FROM.material_ref` 引用其 id |

**为什么用 `NameKey`，而不是 `aliases` 列表。** 这是工程映射，不改变 D3 的设计：D3 中每个 alias 本来就是一条带属性的注册记录。

- D3 要求写入时唯一。后端唯一约束作用于整个属性值，而不作用于列表元素；`NameKey.key` 是单个字符串，唯一性可以交给数据库约束保证。
- `intents_decompose.md` §3.2 要求原字符串与 `normalizer_ref` 随注册记录保存，冲突键还要能单独标为 `ambiguous`。这些都是"每个键"的属性，放不进字符串列表。
- 对象上不另存 `aliases` 列表，避免两份副本需要同步；`Get` 由 `NAMES` 装配 aliases 供 Agent 阅读。

**对算子的影响。** `Resolve` 的三级解析和返回结构不变，第二级的查询写法改为下面这样；ambiguous 状态与 `normalizer_ref` 可以直接写入 match_trace。E09 实现后发现还有两处受影响（`intents_decompose.md` §6.2）：

- **名称词面通道：** 语义阶段的名称词面通道也改为查 NameKey 的 `raw` 全文索引，因为对象上没有 aliases。
- **向量失效：** 向量的输入文本含由 NameKey 装配的 alias，所以注册或撤销 alias 会使该对象的派生向量失效。

向量（`embedding`、`embedding_key`）作为检索派生属性存在对象上，不属于内容属性。

```cypher
MATCH (k:NameKey {key: $key})-[:NAMES]->(n)
```

增加的工作都在写入端：注册 alias 时在同一事务中建 NameKey 与 `NAMES`；合并对象（Q4）时把 `NAMES` 改指向保留的对象。

## 6. Relationship

方向约定：**Content 指向它的来源、讨论对象和参与对象；Entity 与 Concept 不指向 Content。** v1 中由 Paper 指出的 `HAS_CLAIM`、`REPORTS`、`HAS_RESOURCE_RECORD`、`HAS_CONTRIBUTION` 因此统一改为 Content 经 `FROM` 指向 Paper。

### 6.1 视角一：三类之间的关联

行为起点，列为终点。

| 起点 \ 终点 | Entity | Concept | Content |
| --- | --- | --- | --- |
| **Entity** | `VERSION_OF`、`PART_OF`、`DERIVED_FROM`、`CITES`；重审：`INTRODUCES` | `IMPLEMENTS`、`FOR_TASK`；重审：`HAS_METHOD` | 无（方向约定） |
| **Concept** | 无；重审：`PRODUCES` | `BROADER`、`HAS_PART`、`ADDRESSES`、`DERIVED_FROM`、`OVERLAPS_WITH`、`REFINES`、`IMPLIES`、`CONTRADICTS` | 无（方向约定） |
| **Content** | `FROM`、`ABOUT`、`USES`、`EVALUATES`、`OBSERVES` | `ABOUT`、`EVALUATES`、`MEASURED_BY`（首版不用）、`USES_PROTOCOL`、`ON_TASK`、`EXPRESSES`、`RESPONDS_TO` | `SUPPORTED_BY`、`SUPPORTS`、`CHALLENGES`、`QUALIFIES`、`CHECKS`；候选：`SUPERSEDES` |

此外：`ASSESSES`、`BASED_ON`（候选）从 Assessment 指向任意类别；`MERGED_INTO`（候选）连接同类对象。

从矩阵可以读出两点：

- Entity 与 Concept 之间只有少量直连（实现、任务、论文—方法角色），论文形成的理解基本都经 Content 连接到对象。这与主张 A"复用的是阅读理解"一致。
- 仍在 Entity → Concept 格中待定的 `HAS_METHOD`，就是 Q7 的"Paper–Method 角色用直连还是经 Content"。

### 6.2 视角二：完整关系清单

除另行说明外，关系可带 `description` 与 `source_refs`（字符串列表，见第 1 节方案 B）。

#### 6.2.1 实验参与与来源

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `FROM` | Content → Entity | `Content.source_refs` | `material_ref`、`locators` | 改写 | 取代 v1 的来源类关系及 Node 上的 `anchor` |
| `ABOUT` | Content → Entity / Concept | `Content.about`、`Entity.described_by` | | 沿用 | 讨论关系不表示支持；v1 的 `DESCRIBES` 并入 |
| `EVALUATES` | Experiment → Method、Model 等 | `Content.participants` | `role: target / baseline`（必填）、`version` | 沿用 | Q7：立即回补 role，§6.1 依赖它。2026-10-03 曾加 `variants`、`origin`、`origin_basis`、`origin_from`，同日试跑后退出首版：变体在实验描述中说明，结果引自哪篇论文由 `CITES` 承担（[抽取原则](./extraction_principles.md) §2、§5） |
| `USES` | Experiment → Entity | `Content.participants` | `role`：training_data / evaluation_data / analysis_input / tooling / retrieval_corpus（2026-10-02 新增）；`version` | 沿用 | role 缺失时进入 `diagnostics.role_missing` |
| `MEASURED_BY` | Experiment → Metric | `Content.participants` | | 首版不用（2026-10-04） | 随 Metric（3.1） |
| `USES_PROTOCOL` | Experiment / Observation → Protocol | `Content.protocol` | | 新增 | 实际参数不入库，按锚点读原文 |
| `ON_TASK` | Experiment → Task | | | 沿用 | Q7：立即回补 |

#### 6.2.2 主张、依据与核查

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `SUPPORTED_BY` | Claim → Experiment / Observation | `Content.evidence` | | 改写 | v1 只到 Experiment，v2 扩到 Observation |
| `SUPPORTS`、`CHALLENGES`、`QUALIFIES` | Claim → Claim | `Content.supports` 等 | | 沿用 | 不推导传递关系 |
| `EXPRESSES` | Claim → Proposition | `Concept.expressed_by` | | 沿用 | Q6 |
| `RESPONDS_TO` | Claim → Issue | `Concept.answered_by` | `stance` | 沿用 | Q6 |
| `OBSERVES` | Observation → Entity | `Entity.observed_by` | `version` | 沿用 | 记录检查的 commit 或快照（2.3） |
| `CHECKS` | Observation → Claim / Usage | `Content.checks` | `verdict` | 沿用 | |

#### 6.2.3 资源之间与资源—概念

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `VERSION_OF` | Entity → Entity | `Entity.versions` | | 新增 | 见 2.3 |
| `PART_OF` | Entity → Entity | `Entity.parts / split_of` | | 沿用 | v1 已有 Resource 间 PART_OF；v2 用于切分 |
| `DERIVED_FROM` | Entity → Entity | | | 沿用 | 数据、代码或模型的派生 |
| `CITES` | Paper → Paper | | `source_refs`（含正文中的引用位置）、`description`（这条引用支撑了什么）；不设引用意图枚举 | 沿用，已实现（2026-10-03） | 选择性写入：转引结果时必写，对方法、主张或实验有实际作用时可写，背景引用不写；没有 `CITES` 不等于没有引用（[抽取原则](./extraction_principles.md) §8）。论文结果之间的依赖只记在这里：`description` 写明哪些实验、哪些方法的结果引自对方，I3 据此定位该对读的实验（[Workload 拆解](./intents_decompose.md) I3） |
| `IMPLEMENTS` | Code / Model → Method | `Entity.implements` | 重审：依据 | 新增 | I6 区分"论文声称公开、找到实现、成功运行、结果复现"。倾向这条边只记录"已存实现对应"并带 `source_refs`；论文的发布声明另存为 Usage，供 Observation `CHECKS`。边与 Usage 需保持一致；若负担过重，改用 §3.3 的关联节点。I6 实例中裁决 |
| `FOR_TASK` | Dataset / Benchmark → Task | | | 沿用 | |

#### 6.2.4 概念之间

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `BROADER` | Concept → 同 kind Concept | `Concept.broader` | | 改写 | 合并 v1 的 `INSTANCE_OF` 与 `SUBTYPE_OF`（见 3.1）；不用于连接方法变体（已定，2026-10-03） |
| `HAS_PART` | Method → Method | `Concept.parts` | | 改写 | 即 v1 的 `USES_COMPONENT`，方向不变：整体 → 组件 |
| `ADDRESSES` | Method → Task | `Concept.addresses` | | 沿用 | v1 要求 anchor 并写"本文如何表述该任务"。这是来源化内容，重审：边上只留 `source_refs`，表述移到 Content |
| `DERIVED_FROM` | Method → Method | | | 沿用 | 类别相同不推出沿用 |
| `OVERLAPS_WITH` | Concept ↔ Concept | | | 沿用 | 语义对称 |
| `REFINES` | Proposition → Proposition；Issue → Issue | | | 沿用 | Q6 |
| `IMPLIES`、`CONTRADICTS` | Proposition → Proposition | | | 沿用 | Q6；`CONTRADICTS` 语义对称 |

#### 6.2.5 写路径候选（随 Q1、Q2、Q4 确定）

| Type | 端点 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `SUPERSEDES` | Content → 同 kind Content | | 候选 | Q2：新修订指向被取代的记录 |
| `MERGED_INTO` | 同类 → 同类 | | 候选 | Q4：被并入对象保留为重定向 |
| `ASSESSES` | Assessment → 任意 | `unit_role` | 候选 | Q1：被判断的对象，对象对时以 role 区分 |
| `BASED_ON` | Assessment → 任意 | `revision` | 候选 | Q1：判断依据；被依赖记录修订后，据此把判断标为 stale |
| `NAMES` | NameKey → Entity / Concept | | 候选 | 第 5 节 |
| `MATERIAL_OF` | Material → Entity | | 候选 | 第 5 节 |

#### 6.2.6 待重审与退役的 v1 关系

| v1 Type | 状态 | 去向 |
| --- | --- | --- |
| `HAS_CLAIM`、`REPORTS`、`HAS_RESOURCE_RECORD`、`HAS_CONTRIBUTION` | 退役 | 改为 Content `FROM` Paper |
| `DESCRIBES` | 退役 | 并入 `ABOUT` |
| `INSTANCE_OF`、`SUBTYPE_OF` | 退役 | 并入 `BROADER` |
| `USES_COMPONENT` | 退役 | 改名 `HAS_PART` |
| `DIFFERS_FROM` | 退役 | 差异维度与两方做法是来源化判断，改为 Claim `ABOUT` 两个方法 |
| `HAS_METHOD {role}` | 重审 | Q7：proposed / reused / extended / compared 对 I1 有用。倾向保留为 Paper → Method 直连，role 必填 |
| `RELATES_TO {role}` | 重审 | `introduced` 对 I6 有用，倾向保留为 Paper → Entity 的 `INTRODUCES`；`used`、`evaluated` 由实验的 `USES`、`EVALUATES` 与 Usage 表达；`cited_only` 退役 |
| `RAISES` | 重审 | 论文提出问题也是来源化表述。倾向用 Claim `RESPONDS_TO` Issue 且不填 stance 表达（v1 已允许"如何做到"类问题不填 stance） |
| `PRODUCES` | 重审 | 倾向并入 `IMPLEMENTS` |
| `HAS_METRIC` | 重审 | 倾向退役，资源采用的指标由 Usage `ABOUT` Metric 表达 |
| `EXTENDS`（Contribution 之间） | 重审 | 随 Contribution 去留（4.1） |
| Contribution 的 `ABOUT`、`HAS_CLAIM` | 重审 | 同上 |
| Method `DERIVED_FROM` Resource | 重审 | 跨类派生，六类 intent 未使用，倾向暂不保留 |
| `RELATED_TO {kind}` | 重审 | Agent 扩展关系不属于任何检索契约。倾向保留为隔离区：不参与 `where` 与 `expand`，只能被显式读取；反复出现后再升级为正式 Type |

## 7. 入库前需要定的事项

按第一个 I3 实例（两种方法、一个数据集、2–4 篇论文）的需要排序。前 9 项入库前必须定，其余可以等实例或讨论。

| # | 事项 | 倾向 | 位置 |
| --- | --- | --- | --- |
| 1 | kind 用次级 Label 还是属性 | **已定（2026-10-02）**：次级 Label；`intents_decompose.md` §3.2 已加注解、§6.1 已改写 | 第 1 节 |
| 2 | `source_refs` 的存储 | **已定（2026-10-02）**：Node 用 `FROM`，Relationship 用字符串 | 第 1 节 |
| 3 | 精确键用 `NameKey` 还是 `aliases` 列表 | **已定（2026-10-02）**：`NameKey`，对象上不存列表 | 第 5 节 |
| 4 | Paper `title` → `name`；`identifiers` 的存储；Paper `description` | **已定（2026-10-02）**：改名；字符串列表；description 存摘要，任务相关理解写入 note | 2.2 |
| 5 | 版本节点的建立时机与命名；版本未知时 Split 挂在哪里 | **已定（2026-10-02）**：修订级版本默认记在使用边的 `version` 上，只在版本自身需要挂结构时建节点；未写版本归原实体 | 2.3 |
| 6 | ResultUnit 的边名、Label、`value` 类型 | **已定（2026-10-02）**：复用参与边；只带 `ResultUnit`；原文与数值都存，数值比较不理想时回退原文交 Agent。首版不用（2026-10-03）：入库为报告级。**退役（2026-10-04）**，D1 撤销 | 4.3 |
| 7 | 可比性条件哪些进入结构 | **已定（2026-10-02）**：版本、切分、指标、语料进入结构；重排序留在文本。**首版修订（2026-10-03）**：只有数据集与指标作为参与关系入库，其余条件由 Agent 读原文；2026-10-04 起指标也不入库 | 4.4 |
| 8 | Method 与 MethodConcept 合并 | **已定（2026-10-02）**：合并，用 `BROADER`；`BROADER` 不承担变体（2026-10-03，见 [抽取原则](./extraction_principles.md) §2） | 3.1 |
| 9 | `Observation.kind` 改名为 `check_level` | **已定（2026-10-02）** | 4.2 |
| 10 | `Metric.direction` 的位置 | **已定（2026-10-02）**：放在 Metric 上。随 Metric 首版不建（2026-10-04） | 3.2 |
| 11 | Usage、Contribution、Assessment 的去留 | 等 Q5、Q1 | 4.1 |
| 12 | `revision`、`status`、`SUPERSEDES` | 等 Q2 | 第 1 节、6.2.5 |
| 13 | Issue、Proposition 的归类 | 等 Q6，用 I4、I5 实例裁决 | 3.1 |
| 14 | `IMPLEMENTS` 的依据、`INTRODUCES`、`RELATED_TO` | 等 I6 实例 | 6.2.3、6.2.6 |
| 15 | `Commit` 契约：论文增量的表单与编译规则、操作集（create_object、link、register_name、attach_source，以及更新与撤销）、dry_run 与 apply 的批级解析 | **已定（2026-10-03）**，E09 已实现并完成两篇论文的正式入库：抽取口径见 [抽取原则](./extraction_principles.md)，编译、操作集、检查分工、自然键与批次记录见 [Commit 契约](./commit_contract.md)；修订与撤回仍随 Q2 | `intents_decompose.md` §5 写路径 |
| 16 | 唯一命名空间标识的后端约束 | 倾向先保持事务内复查；需要后端保证时仿 NameKey 建键节点 | 2.4 |
| 17 | 语义候选的阈值或"可能不存在"提示 | 暂不设；等真实查询中外部否定的比例出来再定 | `intents_decompose.md` §4.1 |

I3 实例只涉及 Paper、Dataset、Split、Method、Experiment 及其参与边，第 11–14、16、17 项不阻塞它；第 15 项在论文入库前必须定。
