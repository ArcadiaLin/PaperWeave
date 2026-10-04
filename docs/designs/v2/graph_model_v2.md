# Graph Model V2

> **状态：** 本文规定当前图模型及其工程映射；标为“待定”的项目不属于已确认实现要求。当前论文入库范围是 Paper、Method、Dataset、Task、Experiment、来源与参与关系，以及选择性 `CITES`。E09 的论文编译与入库实现尚待对齐现行契约并重新入库验证，见 [Commit 契约](./commit_contract.md)。Q1–Q8 对应 [未定模型问题](../../discussions/2026-10-01-v2-open-model-decisions-and-write-path.md)，访问契约见 [Workload 拆解](./intents_decompose.md)。

`V2` 设计一个面向研究 Agent 的论文知识图：保存阅读后形成的索引（轻度提炼、原文锚点与关联），通过论文引用、共享方法、资源和命题连接不同论文，让后续研究能够查找、比较和复用已有经验。

模型区分 `Entity`、`Concept`、`Content` 三类对象，以主 Label 表达类别、次级 Label 表达类内类型。类别与访问契约共同设计，其有效性需通过真实 workload 检验。

采用 Neo4j 的 Labeled Property Graph 模型，统一使用 `Node`、`Relationship`、`Label`、`Type`、`Property` 描述。概念依据见 [Neo4j 图模型](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/)。

```text
Graph Model
│
├── Node
│    ├── Entity     资源对象：Paper、Dataset、Benchmark、Split、Code、Model …
│    ├── Concept    定义对象：Method、Task、Issue、Proposition
│    ├── Content    来源化内容：Claim、Experiment、Usage、Observation …
│    └── 系统记录   NameKey、Material、IngestBatch（支撑解析与来源，不是语义对象）
│
├── Relationship
│    ├── 视角一：三类之间的关联（3 × 3 矩阵）
│    └── 视角二：完整关系清单（Type、端点、Property）
```

## 定位：节点存什么

图与精读稿的分工不同：

| | 精读稿 | 图 |
| --- | --- | --- |
| 范围 | 单篇论文 | 跨论文 |
| 形态 | 非结构化，高度提炼的转述 | 结构化，轻度提炼的索引 |
| 用途 | 读懂一篇论文 | 从知识关联的角度找到该读的论文、实验与位置 |

图面向**关联、检索、发现与复用**；收益及其随规模的变化需要评价。原文数值、表格和段落通过锚点读取。精读稿不进入图。

因此节点不转录原文，存的是：

| 内容 | 写法 | 例子 |
| --- | --- | --- |
| 轻度提炼 | 用自己的话写到足以判断"要不要去读这里"为止，不写到足以替代阅读 | Experiment 的 `text`（目的、设计、论文的主张，4.2）；Concept 的 `definition`（3.2） |
| 阅读理解与评估 | 独立记录形成者、时间、任务背景、适用范围与依据 | Observation（4.5）；`note` 仅作简短提醒 |
| 锚点 | 在原文哪里 | `FROM` 的 locators；Experiment 的 `anchors` |
| 关联 | 和谁有关、以什么角色 | 参与边、`CITES`、概念之间的关系 |

**不存锚点能直接给出的内容：** 数值、表格、超参数与实验设置、原文段落。实验描述只保留理解该组实验所必需的设计概述，不转录条件明细；入库者的疑点与评价不混入论文陈述。

例外：

- **名称与标识**（`name`、NameKey、`identifiers`、`year`）：它们是查找的入口，必须结构化。
- **Paper 的摘要**：Paper 的 `description` 存摘要（2.2）。
- **阅读与分析形成的内容**：Observation 保存阅读者或 Agent 的理解、解释与评估，并引用其材料依据；这些内容不是原文转录。实际检查与运行产生的环境、日志和结果同样随 Observation 保存。
- **关系的说明**（如 `CITES.description`）：写这条关联为什么存在、该去读哪里，同样只写到判断"要不要读"为止。

实验记录只到研究问题级，实际采用的参数与结果行按锚点读取。Usage 的去留待定；若保留，其内容限于概述与锚点。

## 0. 记法与状态标记

- `Entity.Paper` 表示物理上的双 Label `(:Entity:Paper)`：主 Label 是类别，次级 Label 是类内 kind。语义对象恰好带一个主 Label 和一个次级 Label；系统记录只带自己的 Label。
- Cypher 片段只展示结构，属性值为示意。
- 本文是工程方案，名词可以与设计文档不同：设计文档中的逻辑字段（如 `kind`、`aliases`、`source_refs`）在这里映射到具体的 Label、Node 或 Relationship，映射关系在对应条目中说明。
- “已定”表示当前契约；“待定”表示尚需任务实例或讨论确定，不应据此扩大实现范围。

## 1. 共同 Property

| Property | 含义 | 状态 | 说明 |
| --- | --- | --- | --- |
| `id` | 系统分配的无语义标识 | 已定 | 只定位记录，不证明对象同一性 |
| `revision` | 修订号；引用写作 `ref={id, revision}` | 写入语义待定 | 修订如何产生未定（Q2）。倾向：Entity、Concept 原地修改并递增；Content 不可变，新修订经 `SUPERSEDES` 指向旧记录 |
| `kind` | 类内类型 | 已定 | 只用次级 Label 存储，不另存属性；逻辑字段由 Label 投影 |
| `family` | Entity / Concept / Content | 已定 | 由主 Label 表达，不另存 |
| `source_refs` | 来源引用 `{entity_ref, material_ref, locator}` | 已定 | 固定来源实体、材料版本与位置；存储方式见下 |
| `note` | 简短使用提醒与消歧线索 | 已定 | 不进检索面、没有独立版本；需要独立检索、引用和复用的阅读理解与评估写成 Observation。Experiment 不混入入库者的判断 |
| `status` | `active / superseded / merged / retracted` | 待定 | 支撑 Q2 修订与 Q4 合并后的重定向；读路径默认只取 `active` |
| `committed_by` | 提交者类别及 call_id | 待定 | 批次记录保存提交者；是否提升为对象属性取决于维护追溯需求 |
| `embedding` 等派生属性 | 系统写入 | 已定 | 不属于模型；计算位置见 Q8 |

**`source_refs` 的存储。**

- 节点来源通过 `(:Content)-[:FROM {material_ref, locators: [...]}]->(:Entity:Paper)` 表达，终点即来源实体；Concept 的定义、Benchmark 的评测规则以及 Observation 的阅读依据有明确材料出处时也使用 `FROM`。Observation 的形成者单独记录，来源材料的作者不是该观察的作者。
- 关系来源存为字符串列表 `source_refs: ["<material_ref>::<章节::start:end>"]`。
- 实验参与边的来源由所属 Experiment 的 `FROM` 提供，不另存。
- `locator` 为 `<章节::start:end>`，`material_ref` 固定材料内容版本。

关系来源使用字符串的代价与约束：

- **反查困难。** "某篇论文或某份材料支持了哪些关系"无法沿边查询，只能扫描相关类型的边并匹配字符串。这主要影响维护（Q3）：材料更新或记录撤回时，查找依赖它的关系。
- **影响范围有限。** 实验参与边（`EVALUATES`、`USES` 等）的来源就是所属 Experiment 的 `FROM`，不另存；自带来源的主要是 `CITES`、`SUPPORTED_BY`、Claim 之间的关系、`IMPLEMENTS`、`ADDRESSES`。原型规模下扫描代价可以接受。
- **引用完整性。** 数据库不保证字符串中的 `material_ref` 存在，由写入契约检查。
- **升级路径。** 某类关系的来源需要频繁反查时（最可能是 `IMPLEMENTS`），把它物化为关联节点，使其也能有 `FROM`（见 [Workload 拆解](./intents_decompose.md) §3.3）。

## 2. Entity：资源对象

### 2.1 次级 Label

| 次级 Label | 含义 | 状态 | 说明 |
| --- | --- | --- | --- |
| `Paper` | 书目对象 | 已定 | 只表达书目；论文中的方法、主张、实验在其他对象中。被引但尚未入库的论文建桩节点（`stub`，只有参考文献中印的标题与引用线索，[抽取原则](./extraction_principles.md) §8） |
| `Dataset` | 数据本身 | 已定 | 以资源身份供实验参与关系引用 |
| `Split` | 数据切分 | 已定 | scope 为父数据集版本，`PART_OF` 连到父版本 |
| `Code` | 代码仓库 | 已定 | |
| `Model` | 权重、checkpoint 或 API 模型 | 已定 | |
| `Benchmark` | 具名的评测资源或套件 | 已定 | 有独立身份、版本、评测目标与组成范围；定义规则存于描述并附来源锚点，见 2.5。论文把数据集称为 benchmark，不自动产生另一个节点 |
| `Tool` | 非模型的软件、库、服务 | 待定 | 六类 intent 无直接需求。倾向暂不建，实例中出现再加 |

### 2.2 Property

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | 全部 | 精确键 | 已定 | Paper 与其他 Entity 均以 `name` 作为主称呼。精确键为 `(规范化 name/alias, type, kind, scope)`；`name` 留在对象上作主称呼，同时注册为一条 `NameKey` |
| `aliases` | 全部 | 精确键 | 已定 | 写入时强制作用域内唯一，冲突拒绝。不在对象上存列表，存为 `NameKey`（第 5 节）；`Get` 由 NameKey 装配 aliases 供阅读 |
| `identifiers` | 全部 | 精确匹配 | 已定 | 逻辑结构 `{namespace, value, version_scope}`。存为字符串列表 `"<namespace>:<value>"`，如 `"arxiv:2005.11401"`、`"url:https://github.com/zhouhaoyi/ETDataset"`；唯一性按命名空间声明，重复时的处理见 2.4 |
| `description` | 全部 | 全文 / 向量 | 已定 | Paper 的 `description` 存摘要，其他资源存内容与用途介绍。需要持久复用的任务相关阅读理解写成 Observation（4.5） |
| `resource_version` | 版本节点 | 精确 | 已定 | 只在升级出版本节点时使用（2.3）；只用于定位，不跨资源比较大小 |
| `split_role` | Split | 否 | 待定 | train / dev / test：切分在数据集内声明的角色。实验实际怎样使用它写在 `USES.role` 上，二者不互推 |
| `year` | Paper | 否 | 已定 | 若 I1 需要按年份过滤，再提升进检索面 |
| `paper_type` | Paper | 否 | 待定 | 六类 intent 未使用。是否仅作描述字段待定 |
| 作者、许可、安装说明等 | 全部 | 否 | 已定 | 描述面，类内允许异构 |

### 2.3 版本与切分

本节规定资源版本与切分的模型语义。当前论文表单不写实验条件或 Split 绑定；I3 的条件由 Agent 读原文取得。以下带版本参与边的例子说明通用图映射，不是论文表单的抽取要求。

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
- **切分作用域**：切分的 scope 是 `PART_OF` 指向的节点，默认为身份节点，版本节点存在时为版本节点。上例中 `dev` 的精确键 scope 为 `MS MARCO`。
- **I3 条件判断**：当前由 Agent 读取材料判断数据版本及切分是否可比，缺失不视为一致。
- **规范化**：`version` 字符串使用单独的版本化规范化配置（如统一大小写、去掉前缀 `v`），避免 `v2.1`、`V2.1`、`2.1` 被判为不同。NameKey 的 `name-key-v1` 保留大小写，不能直接套用；原字符串照常保留。
- **`include={versions}`**：只在存在版本节点时起作用。
- **实例中测量**：因数据版本被判为 U 的比较数量，及 Agent 最终判定其中多少确实不可比；若几乎都无关紧要，可进一步弱化边上的 `version`。

### 2.4 标识的唯一性与重复

标识只用于匹配，不默认唯一。唯一性按命名空间在领域配置中声明，重复是正常输入，由算子报告，不靠改写模型或数据回避。

| 命名空间 | 唯一性 | 写入时重复 | 读取时多重命中 |
| --- | --- | --- | --- |
| `arxiv`、`doi`、`s2` | 唯一 | 拒绝写入，处理同 NameKey 冲突 | 正常不会发生；导入或核查发现的冲突隔离为 `ambiguous` |
| `url` | 非唯一：同一仓库可发布多个数据集，也可同时发布代码与模型 | 允许 | 多个命中时返回 `stage=id, status=ambiguous` 及全部命中，不静默落到下一级；只命中一个时返回 `candidates`，不单独确定身份 |

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

**工程实现（E09）。** 唯一命名空间的标识存在对象的字符串列表里，后端唯一约束作用于整个属性值、管不到列表元素，所以由 `Commit` 在 dry_run 中检查、在写入事务内复查。如果需要由后端保证，可以仿照 NameKey，为唯一命名空间单独建键节点（第 7 节）。上面的规则已在 E09 的种子图上逐条检验（`experiments/e09/notebooks/02_resolve_get.ipynb`）。

### 2.5 Benchmark：定义与实际使用

Benchmark 共用 Entity 的 `name`、NameKey、`identifiers`、`description` 与版本契约。`description` 概述评测目标、组成范围及发布者定义的评测流程和官方模式，定义材料以 `FROM` 固定版本与位置；目前不单列协议属性。

成员数据集可经 `PART_OF` 指向 Benchmark，Benchmark 经 `FOR_TASK` 指向任务。成员与任务的具体对应不能从两组边的笛卡尔积推导，必要时按描述与锚点确认。这些关系描述已存组成，不表示当前论文表单已支持写入 Benchmark。

论文实际采用哪种模式、作了什么必要调整，由 Experiment 的 `text` 概述，完整设置按锚点读原文。Benchmark 节点不保存各论文用法的汇总副本；使用经验从相关实验取得。独立标识 Experiment 使用某个 Benchmark 的写入和查询契约尚待实例确定，不能仅凭共享数据集推断采用了该 Benchmark 的完整方案。

## 3. Concept：定义对象

### 3.1 次级 Label

| 次级 Label | 含义 | 状态 | 说明 |
| --- | --- | --- | --- |
| `Method` | 方法方案及方法类别 | 已定 | 同属一个 kind，类别经 `BROADER` 表达。`level: scheme / family` 是否需要由 I1 实例确定；变体与配置不建节点或结构化标签，必要说明写在实验描述中 |
| `Task` | 研究任务 | 已定 | |
| `Issue` | 研究问题 | 待定 | 归类待 Q6 |
| `Proposition` | 跨来源的共同命题 | 待定 | 归类待 Q6 |

### 3.2 Property

Method、Task 是术语型，Issue、Proposition 是陈述型。两者的检索字段不同，这正是 Q6 的来源。

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | 术语型 | 精确键 | 已定 | |
| `aliases` | 术语型 | 精确键 | 已定 | 同 Entity |
| `definition` | 术语型 | 全文 / 向量 | 已定 | 只写对象是什么，不写某篇论文如何使用它 |
| `scope_note` | 术语型 | 全文 / 向量 | 待定 | 适用范围与区分边界；当前倾向并入 `definition`，是否单列需检索实例支持 |
| `scheme_ref` | 术语型 | 过滤 | 待定 | 外部定义体系（如某个任务分类表）。当前没有外部体系，当前倾向不设 |
| `text` | 陈述型 | 全文 / 向量 | 已定 | 措辞中立，保留范围限定 |
| `description` | Issue | 否 | 已定 | 争议所在与判断条件 |

## 4. Content：来源化内容

### 4.1 次级 Label

| 次级 Label | 含义 | 状态 | 来源责任 |
| --- | --- | --- | --- |
| `Claim` | 论文作者的主张 | 已定 | 作者，经抽取 |
| `Experiment` | 论文报告的一项实验 | 已定 | 作者，经抽取 |
| `Usage` | 论文对资源的描述或使用经验；若保留，只存概述与锚点，配置与原文说明按锚点读 | 待定 | 作者，经抽取；Q5 |
| `Observation` | 阅读、分析、检查或执行形成的理解、结论与评估 | 已定 | 形成该记录的阅读者、Agent 或执行者；与论文作者的 Claim 分开 |
| `Contribution` | 论文自述的贡献 | 待定 | 作者，经抽取；Q5 |

`Contribution` 的主要用途是 I1 的"论文提出了哪个方法"，这也可以由 Paper 到 Method 的带角色关系表达（Q7，见 6.2.6）。当前倾向不建 Contribution，I1 实例确有需要再加。

### 4.2 Property

| Property | 适用 | 检索面 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `text` | 全部 | 全文 / 向量 | 已定 | Content 类统一的可独立理解描述。Experiment 写一组实验的目的、设计和论文声称的结论，不写数值；见 [抽取原则](./extraction_principles.md) §4 |
| `source_refs`（`FROM`） | 有材料依据的 Content | 限制条件 | 已定 | 原文位置与材料版本；Observation 的依据不表示其内容是原作者的陈述，见第 1 节 |
| `anchors`、`exp_key` | Experiment | 精确 | 已定 | `anchors`：该组实验涉及的表、图锚点列表（如 `S4.T3`、`A1.T8`），第一个为主锚点；`exp_key = <论文 id>::<主锚点>` 是自然键。全部行范围（含正文）在 `FROM.locators` |
| `check_level` | 检查或执行类 Observation | 过滤 | 已定 | `repo_inspection / execution / reproduction`；仅适用于真实检查或执行记录。普通阅读理解不强行填写核验级别 |
| `observed_at` | Observation | 过滤 | 已定 | 观察、理解或评估形成的时间 |
| `environment` | Observation | 否 | 已定 | I6.3 适用性检查需要（[Workload 拆解](./intents_decompose.md) §5.1.3） |
| `evidence` | Observation | 否 | 已定 | 检查日志或运行产物的定位与版本；阅读材料的依据使用 `source_refs`。依据不局限于论文 |

### 4.3 实验粒度与结果访问

一个 Experiment 对应论文结果部分中的一个研究问题，可以覆盖多张表、图和正文段落。附录对正文实验的补全并入同一组，不按数据集、指标或预测长度拆分。自然键使用论文 id 与主锚点，分组与覆盖规则见 [抽取原则](./extraction_principles.md) §4。

`Experiments` 返回实验、参与对象、角色及材料位置。库内不存数值或结果行；外部 Agent 按锚点抽取临时结果行并保留条件与来源。同一实验内的共同参与只提供查找与配对线索，不建立行级对应。

### 4.4 实验条件与可比性

当前论文表单只记录方法及其 target / baseline 角色、数据集与任务。指标在必要时写入实验描述，不建 Metric 节点或指标参与边，也不作为 `Experiments` 的参数。

数据版本、切分、回看窗口、预测长度、评测协议、指标口径等具体条件由 Agent 读原文取得和比较。Benchmark 自身规定的评测规则随其描述与定义锚点保存；当前论文表单不结构化写入实验条件。条件相同、可比、同源等结论不能由共同实验或共享数据集推出。

### 4.5 Observation：持久化理解、结论与评估

Observation 保存阅读者或 Agent 自己形成的内容，包括对单篇论文的理解、跨论文综合、实验比较、资源适用性评估，以及仓库检查、执行和复现的发现。`text` 可以是自由文本，不要求每条观察都表达一个布尔条件。Claim 表达论文作者的主张，Experiment 表达论文报告的实验，Observation 则标明形成者自己的解释与结论。

每条记录需要明确：

- **内容与范围**：理解或结论是什么，在什么任务、问题或条件下成立。
- **形成信息**：由谁、何时、通过阅读分析还是实际检查或执行形成；读材料后判断可运行不能被记为运行成功。
- **对象**：经 `OBSERVES` 关联论文、方法、实验、资源或其他 Content；比较可关联多个对象，读取时保留完整对象集合，不能拆成对每个对象独立成立的判断。
- **依据**：材料版本与位置、检查日志，或被引用记录的固定修订；判断对象与判断依据分别表达。`OBSERVES` 只表达对象，不自动表示证据支持。

`A_map` 与 `A_pred` 的输出默认是任务变量。外部确认需要积累的内容后，才显式提交为 Observation；不自动保存每次中间判断。明确的条件判断可保留 `condition_id`、`value`（T / F / U）、理由及调用或规则出处，但这些不是所有 Observation 的必填结构。

上述记录职责已明确；形成信息、任务范围、对象角色和记录级依据的具体字段编码，以及写入、修订、撤回和依赖失效契约仍待确定。本文不预设自动把依赖变化解释为结论失效。读取已有 Observation 只取得一份有范围和依据的记录，是否适用于新任务由外部判断。

## 5. 系统记录

系统记录支撑解析与来源，不是语义对象，不进入任何类别的检索契约。

| Label | 作用 | 状态 | Property 与关系 |
| --- | --- | --- | --- |
| `NameKey` | 精确键注册表 | 已定 | `key`（规范化名称、kind、scope 拼成的单个字符串，带唯一约束）、`normalized`、`raw`、`kind`、`scope`（global 或父对象 id）、`normalizer_ref`（属性不能存 map，编码为字符串，如 `name-key-v1@unicode-15.0.0`）、`status: active / ambiguous`、注册来源与提交者（`registered_from`、`registered_by`）；`(:NameKey)-[:NAMES]->(对象)` |
| `Material` | 固定版本的材料 | 已定 | `path`、`format`、`content_hash`、`derived_from`（如原 PDF）、`created_at`；`(:Material)-[:MATERIAL_OF]->(:Entity:Paper)`；`FROM.material_ref` 引用其 id |
| `IngestBatch` | 论文入库批次 | 已定 | 锚点覆盖、解析与写入统计、表单和材料哈希、提交者与时间；连到 Paper，见 [Commit 契约](./commit_contract.md) §6 |

**为什么用 `NameKey`，而不是 `aliases` 列表。** 每个 alias 是一条带属性的注册记录。

- 精确键要求写入时唯一。后端唯一约束作用于整个属性值，而不作用于列表元素；`NameKey.key` 是单个字符串，唯一性可以交给数据库约束保证。
- `intents_decompose.md` §3.2 要求原字符串与 `normalizer_ref` 随注册记录保存，冲突键还要能单独标为 `ambiguous`。这些都是"每个键"的属性，放不进字符串列表。
- 对象上不另存 `aliases` 列表，避免两份副本需要同步；`Get` 由 `NAMES` 装配 aliases 供 Agent 阅读。

**对算子的影响。** `Resolve` 的名称级解析查询如下；ambiguous 状态与 `normalizer_ref` 可以直接写入 match_trace。另外两个检索约束见 `intents_decompose.md` §6.2：

- **名称词面通道：** 语义阶段的名称词面通道查询 NameKey 的 `raw` 全文索引，因为对象上没有 aliases。
- **向量失效：** 向量的输入文本含由 NameKey 装配的 alias，所以注册或撤销 alias 会使该对象的派生向量失效。

向量（`embedding`、`embedding_key`）作为检索派生属性存在对象上，不属于内容属性。

```cypher
MATCH (k:NameKey {key: $key})-[:NAMES]->(n)
```

注册 alias 时在同一事务中建 NameKey 与 `NAMES`；对象合并时如何重定向名称、处理冲突，随 Q4 确定。

## 6. Relationship

方向约定：**Content 指向它的来源、讨论对象和参与对象；Entity 与 Concept 不指向 Content。**

### 6.1 视角一：三类之间的关联

行为起点，列为终点。

| 起点 \ 终点 | Entity | Concept | Content |
| --- | --- | --- | --- |
| **Entity** | `VERSION_OF`、`PART_OF`、`DERIVED_FROM`、`CITES`、`FROM`（Benchmark 定义出处）；待定：`INTRODUCES` | `IMPLEMENTS`、`FOR_TASK`；待定：`HAS_METHOD` | 无（方向约定） |
| **Concept** | 可选 `FROM`（定义出处） | `BROADER`、`HAS_PART`、`ADDRESSES`、`DERIVED_FROM`、`OVERLAPS_WITH`、`REFINES`、`IMPLIES`、`CONTRADICTS` | 无（方向约定） |
| **Content** | `FROM`、`ABOUT`、`USES`、`EVALUATES`、`OBSERVES` | `ABOUT`、`OBSERVES`、`EVALUATES`、`ON_TASK`、`EXPRESSES`、`RESPONDS_TO` | `OBSERVES`、`SUPPORTED_BY`、`SUPPORTS`、`CHALLENGES`、`QUALIFIES`、`CHECKS`；待定：`SUPERSEDES` |

此外：`MERGED_INTO`（待定）连接同类对象。Observation 的对象关联与依据表达见 4.5。

从矩阵可以读出两点：

- Entity 与 Concept 之间只有少量直连（实现、任务、论文—方法角色），论文形成的理解基本都经 Content 连接到对象。这与主张 A"复用的是阅读理解"一致。
- 仍在 Entity → Concept 格中待定的 `HAS_METHOD`，就是 Q7 的"Paper–Method 角色用直连还是经 Content"。

### 6.2 视角二：完整关系清单

除另行说明外，关系可带 `description` 与 `source_refs`（字符串列表，见第 1 节）。

#### 6.2.1 实验参与与来源

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `FROM` | Content / 有明确出处的 Concept / Benchmark → Entity | `source_refs` | `material_ref`、`locators` | 已定 | 固定材料版本与原文位置 |
| `ABOUT` | Content → Entity / Concept | `Content.about`、`Entity.described_by` | | 已定 | 讨论关系不表示支持 |
| `EVALUATES` | Experiment → Method、Model 等 | `Content.participants` | `role: target / baseline`（必填）、`version` | 已定 | 按角色定位被测对象；当前论文表单不写版本、变体标签或逐项来源性质，结果依赖由 `CITES` 描述 |
| `USES` | Experiment → Entity | `Content.participants` | `role`：training_data / evaluation_data / analysis_input / tooling / retrieval_corpus；`version` | 已定 | role 缺失时进入 `diagnostics.role_missing` |
| `ON_TASK` | Experiment → Task | | | 已定 | 实验所属任务 |

#### 6.2.2 主张、依据与核查

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `SUPPORTED_BY` | Claim → Experiment / Observation | `Content.evidence` | | 已定 | 作者主张的已存依据，不自动验证支持关系 |
| `SUPPORTS`、`CHALLENGES`、`QUALIFIES` | Claim → Claim | `Content.supports` 等 | | 已定 | 不推导传递关系 |
| `EXPRESSES` | Claim → Proposition | `Concept.expressed_by` | | 已定 | Q6 |
| `RESPONDS_TO` | Claim → Issue | `Concept.answered_by` | `stance` | 已定 | Q6 |
| `OBSERVES` | Observation → Entity / Concept / Content | 对象的 `observed_by` | 资源 `version`；多对象角色与记录修订绑定待定 | 已定 | 表达理解或评估的对象；保留多对象绑定，不代表证据支持。资源检查保留 commit 或快照 |
| `CHECKS` | Observation → Claim / Usage | `Content.checks` | `verdict` | 已定 | |

#### 6.2.3 资源之间与资源—概念

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `VERSION_OF` | Entity → Entity | `Entity.versions` | | 已定 | 见 2.3 |
| `PART_OF` | Entity → Entity | `Entity.parts / split_of` | | 已定 | 资源组成与切分关系 |
| `DERIVED_FROM` | Entity → Entity | | | 已定 | 数据、代码或模型的派生 |
| `CITES` | Paper → Paper | | `source_refs`（含正文中的引用位置）、`description`（这条引用支撑了什么）；不设引用意图枚举 | 已定 | 选择性写入：转引结果时必写，对方法、主张或实验有实际作用时可写，背景引用不写；没有 `CITES` 不等于没有引用（[抽取原则](./extraction_principles.md) §8）。论文结果之间的依赖只记在这里：`description` 写明哪些实验、哪些方法的结果引自对方，I3 据此定位该对读的实验（[Workload 拆解](./intents_decompose.md) I3） |
| `IMPLEMENTS` | Code / Model → Method | `Entity.implements` | 待定：依据 | 已定 | I6 区分"论文声称公开、找到实现、成功运行、结果复现"。倾向这条边只记录"已存实现对应"并带 `source_refs`；论文的发布声明另存为 Usage，供 Observation `CHECKS`。边与 Usage 需保持一致；若需要独立引用关联事实，可考虑关联节点。I6 实例中裁决 |
| `FOR_TASK` | Dataset / Benchmark → Task | | | 已定 | |

#### 6.2.4 概念之间

| Type | 端点 | 逻辑角色 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `BROADER` | Concept → 同 kind Concept | `Concept.broader` | | 已定 | 表达同 kind 的上下位关系，不用于连接方法变体 |
| `HAS_PART` | Method → Method | `Concept.parts` | | 已定 | 整体 → 组件 |
| `ADDRESSES` | Method → Task | `Concept.addresses` | | 已定 | 依据表示待定：倾向边上保留 `source_refs`，论文的具体表述由 Content 承载 |
| `DERIVED_FROM` | Method → Method | | | 已定 | 类别相同不推出派生关系 |
| `OVERLAPS_WITH` | Concept ↔ Concept | | | 已定 | 语义对称 |
| `REFINES` | Proposition → Proposition；Issue → Issue | | | 已定 | Q6 |
| `IMPLIES`、`CONTRADICTS` | Proposition → Proposition | | | 已定 | Q6；`CONTRADICTS` 语义对称 |

#### 6.2.5 系统关系与待定写路径

| Type | 端点 | Property | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `SUPERSEDES` | Content → 同 kind Content | | 待定 | Q2：新修订指向被取代的记录 |
| `MERGED_INTO` | 同类 → 同类 | | 待定 | Q4：被并入对象保留为重定向 |
| `NAMES` | NameKey → Entity / Concept | | 已定 | 第 5 节 |
| `MATERIAL_OF` | Material → Entity | | 已定 | 第 5 节 |

#### 6.2.6 待定关联

| 关联 | 当前问题与倾向 |
| --- | --- |
| `HAS_METHOD {role}` | Paper → Method，角色为 proposed / reused / extended / compared；直连还是经 Content 表达由 I1 实例确定（Q7） |
| `INTRODUCES` | Paper → Entity，记录资源发布关系；依据表达由 I6 实例确定 |
| 论文提出问题 | 倾向用 Claim `RESPONDS_TO` Issue 表达，可不填 stance；随 Q6 确定 |
| Contribution 的关联 | 随 Contribution 是否保留一起确定 |
| `RELATED_TO {kind}` | Agent 扩展关系的隔离区方案待定；不得默认参与 `where` 或 `expand` |

## 7. 实现范围与待定事项

当前论文增量的对象、字段、操作集、检查与幂等规则以 [Commit 契约](./commit_contract.md) 为准。图模型列出的其他对象和关系不表示已纳入论文表单，也不表示已完成实现或真实论文验证。

| 事项 | 当前状态 |
| --- | --- |
| 论文表单与入库 | 契约为 paper-form-v3；E09 尚待对齐并重新入库验证 |
| Usage、Contribution | 是否保留待 Q5 确定 |
| Observation | 泛化理解与评估的持久化职责已定；字段编码、记录级依据、写入与维护契约待 Q1 / Q2 确定 |
| Benchmark | 保留独立身份及定义描述；实际使用关联、成员任务对应与入库范围需实例确定 |
| `revision`、`status`、`SUPERSEDES` | 修订、撤回与历史读取语义待 Q2 确定 |
| 对象合并与拆分 | 身份重定向、依赖更新与 alias 处理待 Q4 确定 |
| Issue、Proposition | 归类及访问方式待 Q6，通过 I4、I5 实例检查 |
| 实现、发布与方法角色关系 | `IMPLEMENTS` 的依据、`INTRODUCES`、`HAS_METHOD` 及扩展关系由 I1 / I6 实例确定 |
| 唯一命名空间标识 | 当前由 Commit 在事务内复查；后端键节点方案待维护与并发需求确定 |
| 语义候选阈值 | 当前不设；根据真实查询中的外部否定成本评估 |
| 嵌入计算边界 | 部署位置待 Q8 确定，不改变外部语义判断的责任边界 |
