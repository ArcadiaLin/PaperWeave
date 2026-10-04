# Intent 分解：面向 Agent 的语义访问算子

> **目的：** 从有任务依据的研究 intent 出发，确定必须取得的信息与约束，推导可组合的任务级访问算子，再共同设计语义对象、检索契约和属性图映射。
>
> **状态：** 本文规定六类代表性 intent 的分解与当前访问契约。实验访问只返回实验级记录、锚点和参与绑定；指标不作为结构化访问条件。E09 已实现部分对象解析、读取和入库能力，完整访问接口、组合流程与现行论文入库契约仍待对齐和验证。

面向 Agent 的研究任务，本研究设计建立在属性图之上的**语义数据访问层**。它在明确的输入输出与约束契约下，组织结构化查询、语义检索和关系遍历，返回候选对象、关联上下文及来源依据。外部 Agent 负责解释需求和开放语义判断，中间件执行显式操作与已声明约束。

本文负责把这一定位落实为任务分解；总体动机与研究范围见 [研究顶层设计](research_design_v2.md)。**相对稳定的是 intent 与必要信息；对象划分、检索字段、关系模式和算子表达共同调整。**

```text
研究 intent → 必要信息与约束 → 可复用的访问需求
                                    ↕
                    语义对象契约 ↔ 任务级访问算子
                                    ↓
                     图查询、索引检索与材料读取
```

## 1. 代表性 Intent 与相对稳定的信息需求

### 1.1 任务来源及采用范围

| Intent | 来源直接支持的任务 | 本文采用的范围 |
| --- | --- | --- |
| **I1 发现适合当前需求的工作与方法** | PaperFindingBench：根据包含内容和元数据条件的自然语言描述找论文集合。[S1] | 将候选论文进一步联系到方法及其前提；资源适用性判断由 Agent 完成 |
| **I2 理解方法的机制、条件与细节** | QASPER：NLP 从业者提出全文信息需求，回答者给出答案及证据。[S2] | 取得具体问题所需的知识和材料；允许长尾信息仍在原文中 |
| **I3 组织实验结果并判断比较口径** | TDMS-IE：抽取任务、数据集、指标和分数以构建 leaderboard。[S3] | 结果整理有直接依据；条件对照和可比性判断是本文扩展 |
| **I4 综合同一问题下的路线与发现** | ScholarQA-CS：多论文综合回答；ArxivDIGESTables：生成文献比较表。[S4][S5] | 组织跨论文信息与引用，不把发现原创研究问题作为数据库操作 |
| **I5 核查主张的依据与成立范围** | QASPER 的证据问答；SciFact 的支持/反驳证据及理由识别。[S2][S6] | SciFact 仅支撑任务形式，其生物医学内容不能直接证明 CS 场景覆盖度 |
| **I6 找到资源并判断能否作为实验起点** | CORE-Bench 的代码与数据执行任务；PaperBench 对代码、执行和结果匹配的不同要求。[S7][S8] | 采用资源与配置信息需求；资源发现是本文补充的前置步骤，执行与核验交给外部 Agent，其结果不入库 |

这六类覆盖候选集合、细节答案、实验对照、文献综合、证据判断和资源准备六种信息产物。它们可以组合：方法选择可以包含 I1–I3，解释异常结果可以调用 I3、I5。这里主张**有任务依据的代表性**，不主张频率代表性或对全部研究行为的完备覆盖。来源证明需求存在，不证明本文模型或混合检索优越。

### 1.2 先确定信息，再决定放在哪种节点中

| Intent | 完成任务必须取得的信息 | 必须保留的区别 |
| --- | --- | --- |
| I1 | 工作/方法候选、用途、前提、来源 | 相关不等于适用；方法不等于同名代码或模型 |
| I2 | 机制、数据与资源要求、设置、原文位置 | 对象定义与某次具体使用不同；未记录不等于不存在 |
| I3 | 被测对象、数据、指标、结果、实验条件 | 方法与实验、数值与条件一一对应到实际记录；同数据集不等于同口径 |
| I4 | 共同问题、各项回答、方法区别、具体发现和引用 | 同一问题可有不同回答；共同认识不能覆盖来源差异 |
| I5 | 待核查说法、相关主张、支持/限定/反驳材料 | 主题相关不等于同一命题；已存判断不等于本次验证 |
| I6 | 资源身份、配置、论文声明 | 论文声称公开与找到实现分开；成功运行、结果复现属于外部执行的发现，不在库中 |

这些信息可以保存为属性、独立内容单元或带依据的关系。例如，实验结果可以先作为一份实验报告中的内容，也可以在需要独立访问时拆成结果记录；**信息要求不随这种拆分自动改变，但访问路径和操作粒度会改变。**

## 2. 从信息需求到访问契约

### 2.1 算子的粒度：一个可复用的信息取得任务

“生成综述”包含开放判断，过大；“沿某条物理边走一步”暴露存储细节，过小。本稿选择能在多个 intent 中复用、可以明确输入输出的访问单元：

| 访问需求 | 候选算子 | 返回的信息产物 | 使用位置 |
| --- | --- | --- | --- |
| 说法解析 / 需求发现 | `Resolve` / `Search` | 已解析引用及诊断 / 带匹配依据的发现候选 | I1–I6 的 lookup / discover |
| 已知对象，取得与问题有关的内容和来源 | `Context` | 对象、相关内容、参与关系与来源 | I1/I2/I4/I6 |
| 按被测对象及评测资源取得实验记录 | `Experiments` | 按实验组织的对象、条件、结果材料与来源 | I3；也可供 I1/I6 使用 |
| 取得主张的已存依据和相关立场 | `Evidence` | 有方向的主张关系、支持材料及来源 | I5；也可供 I4 使用 |
| 按方法取得实现资源 | `Implementations` | 实现对应及其依据 | I6；也可供 I1 使用 |

这些是**任务级访问算子**，并非六个端到端 intent 的一一包装。它们复用 Get、索引召回、图模式匹配、关联、分组和材料读取。后续可按真实任务合并或拆分接口，不能只因起了名字就认定形成贡献。

### 2.2 为什么关系必须进入检索面

**论证条件：** 两个图中，代码资源的全部本地属性相同，但图一记录该资源实现方法 $M$，图二记录它实现另一方法。对于“找出库中已记录为实现 $M$ 的资源”，正确结果不同。只观察资源本地属性的算法无法区分这两个输入，因而无法保证回答该查询。

这证明：**对于依赖已存关系的需求，检索契约必须取得关系信息，或取得忠实维护了该信息的派生表示。** 把关系写进检索文本也是一种派生表示，但文本相似不能代替明确的关系约束，更新时还需维持一致性。

这一论证不证明三分类唯一或最优，也不证明数据库能判断实现关系是否真实；后者属于构建质量与外部核查。

### 2.3 三种约束分别处理

| 需求成分 | 中间件行为 | 外部 Agent 行为 |
| --- | --- | --- |
| 已记录的标识或关系条件 | 精确匹配、关系模式求值、返回匹配依据 | 确定应查询哪个对象及条件 |
| “与需求相关”的开放文本 | 词面与向量召回，返回候选及匹配记录 | 判断是否真正适用，必要时改写查询 |
| 实验是否可比、证据是否支持结论 | 提供描述全集与材料，不隐式推断 | 给出带依据的判断、未知项或后续操作 |

本文使用“约束求值”表示对已声明条件的执行；不把开放科学判断统称为数据库内部的“约束推理”。不存在相关边表示当前图中没有匹配记录，不等于现实中关系不成立。

## 3. 语义对象模型：描述面包含检索面

### 3.1 描述全集、检索子集与类内统一

设对象 $o$ 的描述字段全集为 $D(o)$，所属类别为 $T$，该类检索字段契约为 $R_T$：

$$
\begin{aligned}
R_T &\subseteq \mathrm{fields}(D(o)) \\
D(o) &= \text{检索字段及其值} + \text{其余描述字段及其值}
\end{aligned}
$$

这里的字段是**逻辑字段**：既可以由节点属性提供，也可以由关系或有限子图映射得到。例如 `implements` 是资源的关系字段，不要求存成节点上的字符串属性。$R_T$ 定义字段类型、缺失状态和系统可执行的匹配方式，并不要求每项都有非空值。

- **类内：** 共享检索字段、索引构建规则和关系访问契约；$\mathrm{fields}(D(o)) \setminus R_T$ 允许随 kind 或对象异构。
- **类间：** 自身特性导致检索字段不同，或同类字段的匹配、扩展与结果组织方式不同。
- **消费边界：** Agent 可以读取整个 $D(o)$，包括检索字段。系统存取整个 $D(o)$，但只按已声明契约解释其中可计算的部分。

`metadata` 至多是剩余异构字段的存储容器，**不等于整个描述面**。某个异构字段若需要直接参与数据库筛选或排序，必须显式进入检索契约；字段提升会同时影响构建、校验和算子。

### 3.2 三类候选的字段与检索差异

所有对象共享内部引用 `ref`（即 `id`，不设修订号）、`family`、`kind` 和来源引用。内部 ID 只定位记录，不证明对象同一性。以下是各类在此基础上的检索契约；关系字段返回目标引用及关联记录，不以自由文本替代。

> **工程映射。** `family` 与 `kind` 是逻辑字段，属性图中以双 Label 存储：主 Label 为 family，次级 Label 为 kind，不另存同名属性。本文中的小写 kind 值对应首字母大写的次级 Label，例如 `Content/experiment` 存为 `(:Content:Experiment)`，`Entity/dataset` 存为 `(:Entity:Dataset)`，`Entity/benchmark` 存为 `(:Entity:Benchmark)`。算子签名中的 `type`、`kind`、`kinds` 参数含义不变，执行时翻译为 Label 条件。完整映射见 [Graph Model V2](./graph_model_v2.md)。

| 类别 | 标量或文本检索字段 | 关系检索字段（逻辑角色） | 默认检索与组织方式 |
| --- | --- | --- | --- |
| **Entity：资源对象** | `identifiers`、`name`、`aliases`、`description` | `parts`、`implements`、`described_by` | 标识匹配、名称/别名匹配与资源描述召回；按实现关系过滤；返回资源及资格依据 |
| **Concept：定义对象** | `name`、`aliases`、`definition`；陈述型为 `text` | `broader`、`parts`、`addresses`、`supports`、`opposes`、`described_by` | 术语匹配与定义/范围语义召回；按显式参数扩展已存概念关系；返回概念及扩展路径 |
| **Content：来源化内容** | `text`、`source_refs`、`stated_by`、`formed_by` | `about`、`participants`、`evaluated_on`、`supports`、`opposes`、`evidence`、`described_by` | 内容全文/语义召回与来源、参与对象限制；按记录和来源组织，保留条件与实际对应 |

这三类共享底层组件，**不共享一套无差别的检索字段和通道**。Entity 与 Concept 使用 `(normalized_name_or_alias, type, kind, scope)` 唯一键精确匹配，Content 不把标题或“实验 1”当作别名，也没有默认名称身份召回通道。所有类别已知内部 ref 时都可直接 Get，这与 alias 检索不同。

关系字段集合在类内统一；不适用的角色显式标记，未记录与未加载也要区分。例如 Paper 没有实现角色并不要求它伪造 implements 值。类内不同 kind 不通过临时拼接私有字段悄悄改变检索器。

精确键在写入时强制唯一：普通注册若与另一对象冲突，拒绝该次写入并返回键、已有对象及拟注册对象，保持原键有效；唯一检查与写入原子执行，同键同对象的重复注册为幂等操作。外部可选择显式合并对象、使用经确认的另一作用域或放弃注册。仅批量导入或事后核查发现既有冲突时，将该键隔离为 `ambiguous`，暂停精确解析并保留冲突对象。唯一命中返回已解析引用和 `origin=rule`；这是以读取时直接采用身份换取构建正确性的设计取舍。构建评价（主张 A）抽样核查 alias 精度，并注入错误 alias 测量下游退化。切分名的 scope 为父数据集，方法、资源等其他对象默认全局，kind 的例外由领域配置声明。

名称规范化采用版本化配置 `name-key-v1`：按配置记录的 Unicode 版本执行 NFC，将 White_Space 属性字符组成的连续空白折叠为一个 ASCII 空格并去除首尾空白；保留大小写、连字符及其他标点，不做 NFKC 或字符删除。因此 `BM-25` 与 `BM25`、`BERT` 与 `bert` 是不同键，可经确认分别注册为同一对象的 alias。读写使用同一配置，原字符串及 `normalizer_ref={id,revision,unicode_version}` 随注册记录和 match_trace 保存。配置升级先在新索引中重算并检查冲突，再显式切换活动版本；同一活动索引内只使用一个规范化版本，也只使用一个 Unicode 版本。

> **工程映射（E09）。** Unicode 版本取实现所用字符库的实际版本并如实记录，原型使用 Python 3.12 的 `unicodedata`，即 Unicode 15.0。属性图的属性不能存 map，`normalizer_ref` 编码为单个字符串，如 `name-key-v1@unicode-15.0.0`。

**Entity。** Paper、Dataset、Benchmark、Code、Model 共用资源模型；Paper 表达书目对象，不包办整篇论文的信息。identifiers 保存 `{namespace,value}`，匹配与唯一性规则按命名空间声明。模型不表达资源版本，论文写明的版本按原文锚点读取。Paper 的摘要可直接作为 description，其他资源使用用途与内容介绍，无需改名 abstract。作者、许可细节、安装说明等其余字段允许异构。

**Concept。** Method、Task 以定义和适用范围为核心，Issue、Proposition 是陈述型（Proposition 名称待定）。当前使用 definition 建立语义索引（原型的向量输入另含名称与 alias，见 §6.2）。组件细节与解释注释可以异构。Concept 也可以拥有严谨的标识符；SKOS 已支持概念 URI、标签、定义及语义关系 [S12]，所以不能用“概念没有 ID”证明分类。区别在于资源指称与概念定义匹配所需的规则不同。一个有 ID 的概念仍可能与另一有 ID 的概念含义重叠。

**Content。** Claim 记录论文作者的主张，Experiment 记录论文报告的实验，Contribution 记录论文自述或 Agent 认为的贡献（以 `stated_by` 区分），Observation 记录阅读者或 Agent 形成的理解、结论与评估。text 是可独立理解的内容描述，必要时由外部构建过程从表格等材料生成，并保留依据；实验的具体设置、数值和结果表按来源锚点读取。Observation 来自阅读与跨论文分析，保留形成者、时间、关联对象和依据，不承载仓库检查、执行或复现结果；其自由文本不要求全部转换为 T/F/U。相似内容不自动合并来源，也不因被称为“证据”就成为已验证事实。

Issue 与 Proposition 共用 Concept 契约：一个是待回答的问题，一个是带范围的命题；Claim 经 ABOUT 关联到它们，命题之间可有正反关系（SUPPORTS / OPPOSES）。此划分需要任务检验，不因跨论文使用就独立成为第四类。

Benchmark 以独立身份表达具名评测资源。自身规定的评测流程和官方模式放在 `description` 中并附定义材料锚点；论文实际使用方式由 Experiment 描述和定位，图不维护用法汇总副本。成员数据集与任务可以分别经 PART_OF、FOR_TASK 关联，但不能由此推导每个数据集与每个任务均对应。具体入库及实验使用关联仍待确定。

### 3.3 对象、关系与物理图的映射

```text
SemanticType = {
  descriptive_contract, retrieval_contract,
  identity_and_provenance_rules, graph_mapping
}
SemanticObject(ref)      ↦ 一个节点，或有稳定引用的有限子图
SemanticAssociation(ref) ↦ 一条边，或表达关联事实的有限子图
```

映射规则声明锚点、组成角色、跨对象角色及返回边界。邻居不是自动属于对象内部，同一节点或边可以被多个视图引用，不能由此重复计数或推断共同所有权。

| 逻辑含义 | 可选物理表示 | 上层访问含义 |
| --- | --- | --- |
| 一个 Entity 及其标识 | 资源节点 + 名称键节点及关系 | Get/Search 返回资源视图，不要求 Agent 拼标识节点 |
| 一份实验 Content | 研究问题级实验节点 + 参与关系 + 来源锚点 | Experiments 返回实验级参与绑定与材料位置；结果行按原文读取 |
| 资源实现方法的关联 | 实现边，或关联节点连接资源、方法和来源 | Implementations 返回关联事实与依据 |

“实现关系”若因需要来源反查而物化成节点，并不自动新增一个语义对象类别。只有任务需要独立检索、引用其具体陈述时，才考虑将该陈述另暴露为 Content，并保留它与关联事实的对应。

SourceRef 至少包含 `{entity_ref, material_ref, locator}`；material_ref 固定材料版本，书目记录不能替代原文版本。来源不可读、缺失或已撤回需显式返回。构建者提交语义判断，中间件校验引用、端点与声明过的约束。

### 3.4 关系语义

以下为逻辑角色的一种物理词汇映射，不要求 Agent 直接使用边名：

| 逻辑角色 | 示例关系模式 | 执行限制 |
| --- | --- | --- |
| Entity.implements | 资源 → IMPLEMENTS → Concept(method) | 匹配指定方法，不由同名或共同论文来源推导 |
| Entity.parts | 成员数据集 → PART_OF → 数据集或 Benchmark | 保存成员定义、父资源及来源；不能由 Benchmark 成员关系推断任务与数据的逐项对应 |
| Concept.broader / parts / addresses | 概念 → BROADER / HAS_PART / ADDRESSES → 概念 | 声明方向、深度、循环处理；不把所有边当成等价 |
| Content.about / source_refs | 内容 → ABOUT → Entity / Concept / Content；内容 → FROM → 材料实体 | 讨论关系不表示支持；来源保留版本与定位 |
| Content.participants / evaluated_on | 实验 → EVALUATES / USES → 对象；实验 → EVALUATED_ON → Benchmark | 保留方法、数据的角色与局部对应，禁止假想笛卡尔积；指标不入结构 |
| Content.evidence | 主张 → SUPPORTED_BY → 实验/观察 | 返回已存依据，不自动验证支持关系 |
| supports / opposes | Claim → SUPPORTS / OPPOSES → Claim；Proposition → SUPPORTS / OPPOSES → Proposition | 保留方向、`description` 与 `stated_by`；不推导传递关系 |
| 对象的 described_by | 内容 → ABOUT → Entity / Concept / Content | 返回有关描述与 Observation；Observation 关联多个对象时保留完整对象集合，是否足以回答问题由外部判断 |

## 4. 算子契约与执行表达

### 4.1 共同输入、输出与组合

```text
Resolve(query={identifier?, mention?, text?}, kind, scope, mode: read | write)
  -> {stage: id | alias | semantic, status: resolved | ambiguous | candidates | none | unprocessed,
      refs, match_trace, states, coverage, execution: ok | partial | error}
Search(type, query?, kinds?, where={}, expand={}, scope, budget) -> AccessResult
Context(refs, question?, roles, scope, budget)                  -> AccessResult
Experiments(subjects, dataset={ref:d, include:{}, depth:1}?, scope, budget) -> AccessResult
Evidence(claims, include_relations, scope, budget)             -> AccessResult
Implementations(method, resource_kinds, scope, budget)         -> AccessResult

AccessResult = {
  items, bindings, witnesses, source_refs,
  match_trace, missing, states, coverage, continuation, diagnostics
}
```

Resolve 的 kind 指类内类型（如 Entity/dataset、Entity/benchmark、Concept/method），type（Entity/Concept/Content 类别）由 kind 推出；单次调用指定一个合法 kind，跨 kind 请求分别调用并保留类型。query 的分量与 §4.2 相同：`identifier` 为 `<namespace>:<value>`，`mention` 为说法，`text` 为可选的说明文字，只进入语义阶段；只给一个字符串时视为 mention。kind 属于 Content 时只支持已注册标识与内容候选通道。Resolve 按已注册标识 → 作用域唯一 name/alias → 全文/向量融合候选逐级解析。

标识的唯一性按命名空间在领域配置中声明：唯一命名空间（如 arxiv、doi、s2）的写入冲突处理与 alias 相同；非唯一命名空间（如 url，同一仓库可发布多个数据集，或同时发布代码与模型）允许重复注册。非唯一标识的命中只缩小候选、不单独确定身份：命中多个对象时返回 `stage=id,status=ambiguous` 及全部命中引用，不静默落到下一级；只命中一个对象时返回 `stage=id,status=candidates`。输入同时带名称时，与 name/alias 级结果取交集：交集唯一则 resolved，stage 记为确定身份的那一级，match_trace 记录两级依据；仍不唯一或为空则保留 ambiguous 交外部 `A_pred`。名称级命中了对象而交集为空，说明标识与名称指向不同对象，此时另记 `resolution=conflicting`；名称未注册造成的空交集只是缺信息，不记冲突。write 模式下，非唯一标识的命中只作查重候选（candidates），不直接复用。

read 模式前两级唯一命中即停止；冲突键标 ambiguous 并继续提供语义候选，语义阶段无精确冲突时返回 candidates 与 `value=U`，由外部 `A_pred` 确认。write 模式前两级命中后仍运行语义查重，`refs` 保留精确结果，近邻及其候选状态记入 match_trace，由外部判断重复对象或补 alias；stage/status 指主解析结果，语义查重过程另记 match_trace。write 模式已有精确结果而查重为空时仍为 resolved。

三级均未返回引用且无既有冲突时，返回 `stage=semantic,status=none,refs=[]`，`states.access=empty`、`resolution=missing`、`missing_in=store`，coverage 保留搜索范围与截断。**语义阶段不设阈值**：只要 scope 内有该 kind 的对象，向量通道总会给出近邻，所以库内不存在的对象通常以 candidates 而非 none 返回；none 只在 scope 内没有该 kind 的对象，或 query 没有可供语义阶段使用的 mention/text 时出现。"库内没有"因此要由外部对候选逐个作出否定判断（§4.3.4），其成本计入主张 A；是否引入阈值或"可能不存在"提示，待真实查询数据再定。执行失败单独保留：部分通道失败记 `execution=partial`；因执行失败而没有任何引用时记 `status=unprocessed`、`access=unprocessed`、`execution=error`，不作 none 处理。

`states` 沿用 §4.3.2.1 的统一维度。下游按下表路由 Resolve 结果，伪代码中"名称先 Resolve"均指这一路由：

| 返回 | states | 下游处理 |
| --- | --- | --- |
| `resolved` | `resolution=resolved`，`value=T`，`origin=rule` | 直接采用引用 |
| `ambiguous` | `resolution=ambiguous` | 交 `A_pred` 在 refs 中确认（§4.3.4），附 match_trace |
| `ambiguous` 且有数据冲突（标识与名称指向不同对象，或唯一键、唯一标识指向多个对象） | `resolution=conflicting` | 同上，并作为数据问题报告；不自动采用任一侧 |
| `candidates` | `resolution=unresolved`，`value=U` | 交 `A_pred` 确认；候选全部判 F 时记 `resolution=missing`，`missing_in=store` |
| `none` | `access=empty`，`resolution=missing`，`missing_in=store` | 保留为未解决项，需要时由写入流程新建对象 |
| `unprocessed` | `access=unprocessed`，`execution=error` | 进入错误出口，不当作 none |

同一任务中，Resolve 及其后的外部确认都按说法键 `(raw, kind, scope)` 去重：表格中重复出现的原值只解析和确认一次，结果按键复用。Resolve 承担 lookup，Search 承担 discover 和条件枚举；其他算子的引用参数接收已确认引用。新说法经确认后，通过独立显式写入注册 alias，供后续解析复用。

items 为语义对象视图，bindings 保留对象与角色对应，witnesses 是满足已声明关系条件的关联记录/路径。source_refs 指向材料；匹配路径与来源均不自动证明研究结论。`coverage={local, upstream}`；`local={call_id, snapshot, scope, candidate_depth, truncated, unprocessed_keys}`，`upstream` 保存输入覆盖记录的引用。组合按调用 ID 保留上游链并新增本步记录，分页通过 continuation 继续；完整性按具体范围查询这条链。

where 接受该类已声明的属性/关系条件，如 `implements=m`、`about=m`、`participants.dataset=d`；不接受一句自然语言后隐式调用 Agent 判断。跨角色条件默认共享同一记录绑定，即同一实验；结果行级的对应不在库中（§6.1），由 Agent 按锚点读原文确认，不能由共同实验推出。

expand 只用于声明过的可选扩展，例如 Concept 的 `narrower(depth=1)`；默认不开启。扩大候选范围不自动满足精确身份条件。硬约束缺少可用记录时不进入“已满足”结果；系统报告未匹配/数据不足，外部可另发宽松发现查询。

Context.roles 使用逻辑角色，返回相关内容及请求的上下文。带 question 时可以排序截断；不带 question 时按范围分页枚举。Experiments 按实验记录分组；Evidence 保留方向和逐条依据；Implementations 必须带已存实现对应，描述相似但无对应的资源通过 Search 单独发现。

Context 的角色也必须有有限、确定的展开规则，不能成为一句“取得相关信息”的黑箱。本稿使用以下映射；每次调用只执行请求的角色及其依赖，不递归遍历整个邻接图。

| roles | 从输入引用取得什么 | 绑定要求 |
| --- | --- | --- |
| definition | 输入 Concept 的定义与范围 | 不隐式搜寻另一个同名概念 |
| source_contents | 以输入 Entity 为来源的 Content | 保留 FROM 与材料定位 |
| descriptions / contributions / observations | ABOUT 输入对象的 Content | descriptions 不限 kind，contributions、observations 分别限定 Contribution、Observation；Observation 保留完整对象集合、形成信息与依据，某对象命中不代表结论对它单独成立 |
| discussed_objects | 输入或上述角色取得的 Content 所 ABOUT 的对象 | 保留内容作为中间绑定 |
| experiments | EVALUATES 输入对象的实验；或上述内容直接 SUPPORTED_BY 的实验；输入本身为实验时保留它 | 三种入口分别标记，不推断实验支持什么 |
| parts | 输入资源的 PART_OF 部分或切分 | 保留父资源及部分引用、路径与深度 |
| participants | 输入或本次已取得实验的 EVALUATES / USES 对象 | 每个实验分别组织，保留角色 |
| sources | 输入与本次取得记录的 SourceRef 和 FROM 来源 | 材料只定位，不在此步骤自动读取 |

角色按依赖顺序装配，集合书写次序不影响含义。不支持的角色/输入类型组合返回契约错误；合法角色无记录返回空集合及覆盖信息。`method_refs`、`claim_refs` 是从 bindings 中按类型投影得到的简写；`refs(X)` 默认只取该算子的主体 items，不能误把来源等上下文全部作为下一步目标。

Experiments 的 subjects 采用“任一被测对象命中”。dataset 默认严格匹配 ref；include 可选 parts，depth 默认 1，沿部分指向父资源的反向展开，复用 expand 的循环与深度规则。默认也报告该关系在 depth 内的额外匹配实验数量与引用，存于 `diagnostics.expandable`；显式展开的结果保留 PART_OF witness。`diagnostics.role_missing` 只统计 EVALUATES 本次 subjects、且 USES 指向当前 dataset 选择范围但 role 缺失的实验数量与引用，独立于严格结果。诊断按实验引用去重，受同一预算约束，截断时 count 是已见数量并附 coverage。实验包保留已存的切分 witness，Context 可按 parts 补取；当前论文表单不写切分关系，无记录时按缺失返回。数据条件在同一实验上绑定，指标不作为参数；结果只到实验级，不返回行级结果项（§6.1）。Implementations 在实现关联之外装配一跳描述与 Observation；Evidence 对指定主张关系查找入边和出边，返回时保留真实方向。所有装配共享预算，截断必须可见。

Benchmark 可通过 `Resolve/Search/Get` 的 Entity 契约定位和读取，定义规则随描述与来源返回。`Experiments.dataset` 仍是数据集条件，不把 Benchmark 引用自动当作 Dataset，也不隐式展开整个套件；可以先通过 `Context.parts` 取得已存成员，再显式选择数据集访问实验。取得成员实验不证明其采用了完整 Benchmark 方案。

Observation 通过 Content 的 `Search/Get` 检索和读取，通过 `Context.observations` 装配对象相关的理解与评估。读取已有结论与产生新判断分别标记；重用前需由外部检查依据是否适用于当前任务。Observation 不承载检查或执行结果，阅读判断不能当作成功运行。

Get(refs) 按对象映射装配视图；ReadEvidence(source_refs) 只读取固定材料。普通 Join/Group/Filter 按声明字段工作。上述操作可由查询模板实现，不预设新编译器或完整代数。

### 4.2 混合检索内部：关系有三种不同作用

| 作用 | 例子 | 处理方式 |
| --- | --- | --- |
| 硬约束 | 已记录实现 $M$ 的代码资源 | 对候选求值，返回满足条件的 witness；相关性分数不能抵消约束失败 |
| 召回/排序线索 | $M$ 的已存直接下位方法 | 按声明方向与深度扩展，保留来源路径及扩展标记 |
| 结果装配 | 返回实验的评测数据和材料位置 | 装配语义对象视图，不仅返回命中的单节点 |

```text
contract = 取得 type 的检索契约
Q = 校验 query、where、expand 是否符合契约
C = scope 内按类型、显式属性及关系条件取得的可行对象集合

Entity:  标识精确匹配；name/aliases 匹配；description 全文/向量召回
Concept: name/aliases 匹配；definition（陈述型为 text）全文/向量召回
Content: text 全文/向量召回；source_refs 与参与关系限制

按本类契约合并候选、处理显式关系扩展并排序
重新校验所有返回项的硬约束，装配 bindings、witnesses 与来源
返回结果及截断、缺失和续取信息
```

query 可写为 `{identifier?, mention?, text?}`；纯文本简写为 text。各类只接受本契约支持的分量，不能把 Concept/Content 查询强行套进资源标识通道。query 可省略，此时按结构条件枚举，而非对空文本编码。精确标识通道只执行已注册的匹配规则，非唯一命名空间的命中只缩小候选、不单独确定身份；满足 `(normalized_name_or_alias,type,kind,scope)` 唯一约束的命中具有精确身份语义；导入或核查发现的既有非唯一键标 ambiguous，其他词面、模糊与语义命中保留候选 `value=U`。类内相同通道使用同一预处理和编码配置，缺失文本关闭对应通道。

词面与向量排行可采用 RRF [S9]；精确匹配采用独立且声明过的优先规则，不能重复计分。关系信号若参与排序，须声明含义及权重，不能将“存在路径”默认为证据强度。跨类排行不直接比较原始分数。

逻辑上先满足硬约束再取 top-$k$；实现可以索引先行或图过滤先行。近似召回再过滤可能漏掉可行候选，固定超取倍数不保证条件内 top-$k$，需报告预算与召回限制。语义检索和图遍历已有组合实现 [S13]；本文需要检验的增量在于任务契约、对象装配、组合正确性及使用成本。

### 4.3 可替换的外部 Agent 特殊算子

**将 Agent 判断纳入算法与伪代码，不等于将其纳入中间件内部。** 本文把 $A_{\text{map}}$、$A_{\text{pred}}$、$A_{\text{policy}}$ 作为端到端组合表达中的特殊算子；其中 `Agent_pred` 与 `A_pred` 同义。它们可由外部 LLM 适配器实现，结合显式 router 规则完成流程接续。替换实现只要求遵守同一输入输出契约，不保证判断结果或质量相同。

访问算子与这些特殊算子可以出现在同一程序中。外部执行环境调用特殊算子、校验返回值并按规则路由，中间件执行显式提交的数据操作，不调度 LLM 判断。由此，连续编排可以包含模型计算，无需退回“每次工具返回后都由 Agent 临时决定如何继续”的模式。相关动机见 [研究顶层设计 §5.3](research_design_v2.md#53-从逐步调用走向可连续执行的算子组合)。

#### 4.3.1 三类责任与禁止混用的边界

| 符号 | 输入 → 输出 | 责任与边界 |
| --- | --- | --- |
| `A_map[spec]` | 显式需求、对象描述、已读材料 → 满足声明 schema 的临时记录 | 解释、抽取、组织；逐项保留对应和依据。不得以“组织答案”为名隐式完成影响筛选或结论的新谓词判断，也不自行选择并执行下一工具 |
| `A_pred[spec]` | 带键的对象/对象对、明确条件及材料 → 逐项 `T/F/U` 判断记录 | 判断同一性、适用性、可比性或支持范围；不能自行检索、补材料、合并身份或写入新关系 |
| `A_policy[spec]` | 当前显式状态、未解决项、允许动作及剩余预算 → 一个动作提案或停止 | 在声明的动作空间内决定补查策略；不得返回任意可执行代码、调用自身、改变任务目标或预算。提案经校验后由外部执行环境执行 |

字段投影、已存状态分类、引用去重、按明确条件筛选、数值计算和已规定的分支优先使用普通程序。`A_map` 产生的抽取值默认只是任务变量；只有经过单独的显式更新，才可成为持久记录或检索字段。需要积累的阅读理解、结论和评估以 Observation 保存。最终文字组织可消费已有判断，但不应改变其状态、范围或依据；若需要新判断，应再显式调用 `A_pred`。

#### 4.3.2 共同调用契约与结果结构

> **当前范围：** 本节的 `AgentCall`、`AgentResult`、`PredRow`、`MapRow`、`Action` 是伪代码中区分判断单元、条件与依据的设计记号，当前实现不做这一层细粒度结构，也不持久化；外部 Agent 的判断作为任务内输出记录。

每个调用位置都须声明 `spec`，不能仅用“理解这些材料”作为目标。契约如下，字段名是设计记号，尚非已实现 API：

```text
AgentCall = {
  spec: {id, revision, kind, task, input_schema, output_schema},
  inputs: {request, units, records, materials, prior_results},
  scope: {graph_snapshot, allowed_materials, applicable_conditions},
  limits: {model_calls, input_size, output_size, deadline, retries},
  executor: {adapter_id, model_config, prompt_revision}
}

AgentResult = {
  call_id, spec_ref,
  status: ok | partial | error,
  payload, errors, unprocessed_keys,
  trace: {input_manifest, executor_config, usage}
}

PredRow = {
  unit_key, subject_refs, condition_id,
  value: T | F | U, origin: rule | agent, rule_ref: {id, revision} | null,
  basis_refs, rationale, missing, applicability
}
MapRow = {row_key, value, input_keys, basis_refs, missing}
Action = {kind: call | stop, operator?, args?, target_keys, reason}
```

`units` 明确本次处理单元，可以是单对象、对象对或整个集合；每项有稳定的任务内键。`A_pred` 对每个单元、每个条件至多返回一条判断，未处理的 `(unit_key, condition_id)` 列入 `unprocessed_keys`；不能遗漏后默认当作 `F`。`A_map` 的一对多、多对一及集合级组织方式由 schema 声明，输出保留输入对应。规则判断与模型判断均输出 `PredRow`；`origin=rule` 必填规则引用，`origin=agent` 以 call_id 追踪实现。多条件默认强三值合取：任一 $F$ 则 $F$，全 $T$ 才 $T$，其余 $U$；未处理必需条件在汇总视图中记 $U$ 并保留执行状态。必需条件清单为空时先返回待明确项。

`basis_refs` 可以指向需求中的条件、已加载记录或固定版本材料位置；经验性主张必须有可检查的材料依据。只有 SourceRef 而未读取正文，不等于已掌握材料内容。模型不能通过调用内部工具或隐含会话记忆扩充输入；需补材料时返回缺项或动作提案。`rationale` 是简短判断说明，不要求保存模型内部推理过程。`input_manifest` 记录实际输入及版本、配对和批次组织；它用于追踪与比较，不承诺模型重跑得到完全相同结果。

`T` 表示在声明条件与输入依据下判断满足，`F` 表示有依据判断不满足，`U` 表示依据不足、冲突未解或含义不明确。执行超时、格式错误、非法引用属于 `error`；批次未完成属于 `partial`，不能伪装成语义 `U`。校验器检查 schema、键、引用范围和动作合法性，不替代对判断内容的独立质量评价。

#### 4.3.2.1 统一状态维度

每条状态记录携带 `{unit_key, field_or_condition, states, missing_in?, reason, basis_refs}`；`resolution=missing` 必填 `missing_in: request | store | material`。各维度独立，未涉及的维度省略。执行状态继续使用 `ok/partial/error`，动作提案继续使用 `Action`。

| 维度 | 取值及判定对象 |
| --- | --- |
| `access` | `matched/empty/unprocessed`：本次访问是否有命中或尚未处理；截断另记 coverage |
| `material` | `available/missing/deferred/error`：目标材料是否已成功读取、缺位置、预算待读或读取失败 |
| `value_source` | `stored/rule/temporary`：字段值来自持久记录、确定性推导或本次模型输出；派生值同时保留输入来源链 |
| `resolution` | `resolved/missing/unresolved/ambiguous/conflicting`：字段/映射已确定、缺值、有原值待解析、多候选或互斥记录 |
| `value` | `T/F/U`：由带 condition_id 的 PredRow 表达，如实现关联、适用性、可比性 |

缺请求字段时返回待明确项；缺库内角色时报告数据不足与诊断；缺材料时按已声明规则补读或停止。实现资源的相似候选与已存实现关联分别保留，只有后者可以满足实现关系硬条件。

`PredRow.origin` 表示谁作判断，`value_source` 表示值的取得方式。同一条件复核后采用最新成功且范围一致的判断（包括 $T$ 转 $U$），保留历史；执行失败保留原判断并标记复核未完成。

#### 4.3.3 router 与可连续执行的组合规则

router 是外部执行环境中的确定性分派逻辑，不是另一个隐含 LLM。它按已声明的结果状态与规则选择下一节点；只有确实需要新的策略选择时，才调用 `A_policy`。一次 `A_pred` 与相应 router 可共同实现图中一个 `Agent_pred` 环节，但判断结果与路由结果分别记录。以下以“选取满足条件的对象、对未知项补材料”为例；其他任务可以显式路由到 `F` 分支，例如取得已判定不适用的原因。

```text
checked = 校验规则或 Agent 输出的 PredRow；非法输出进入错误出口
对 resolution=missing: 按 missing_in 路由到用户补充 / 数据不足诊断 / 补读或停止
T_items, F_items, U_items = 按 value 分区合法判断
下一访问输入 = 按 unit_key 回连 T_items；保留 F 的理由
对 U 且 origin=rule: 调用 A_pred 并校验（遵守同键无新材料不重复调用的规则）
对 U 且 origin=agent: 执行已声明补材料规则，否则按预算调用 A_policy 或停止
单独保留并处理 partial/error 与 unprocessed_keys
```

组合时遵守以下规则：

1. **显式依赖。** 下一步只消费通过校验的输出及其对应输入；不能把判断记录当作图对象，也不能丢掉对象对、条件和来源绑定。`U`、错误和未处理项不得隐式进入普通否定分支。
2. **有界执行。** 调用前声明模型、材料访问、配对与重试预算，每次调用从任务总预算中扣除，不能在循环中重新获得预算；动作参数和状态转移须校验。预算耗尽保留未完成状态，不能扩大预算或无限递归。空处理单元默认直接返回空结果，不调用模型；仅有需求的解释调用仍以需求作为一个单元。
3. **无隐式副作用。** 特殊算子返回临时值或动作提案；数据读取、工具执行和持久更新均是独立可见步骤。已存判断的读取与新判断分别标记。
4. **限制重写。** 不默认允许下推、重排、拆批、合批或缓存替换特殊算子；这些改变可能影响模型所见上下文。若要应用，须单独声明适用条件并验证。相同输入下也不假定确定性、传递性或全序。
5. **控制扩张。** 每个特殊算子位置须说明为何需要新解释或判断。不能用 `A_map` 承担本可确定执行的 join/filter，也不能把整个 intent 藏入一个无结构的 `A_policy`。同一 `(unit_key,condition_id)` 没有新材料时不得重复调用 `A_pred`；保存输入材料版本清单检查这一条件。U 按 origin 路由，缺字段按 missing_in 分流。

#### 4.3.4 下文简写的具体约定

第 5 节的 `A_kind[说明](...)` 是上述契约的简写；共同的 scope、limits、executor 与结果校验由外部执行环境显式配置。`p`、`rows`、`J` 等变量指通过校验的 payload；错误和未处理项进入共同状态，不因伪代码省略而丢弃。`refs(J=T)` 表示用判断单元键回连输入后取得主体引用，不是从理由文本中提取引用。

| 调用位置 | 必须声明的 payload 与范围 |
| --- | --- |
| Resolve 候选确认（I3.1、I6.1、I6.2 及写入查重） | 单元为 `(说法键, 候选 ref)` 对，说法键为 `(raw, kind, scope)`，`condition_id=same_object`；输入带候选的 Get 视图与 match_trace。唯一 T 则采用该引用，经确认的新写法可另行显式注册 alias；全部 F 记 `resolution=missing`、`missing_in=store`；多个 T 记 `conflicting`；其余为 U。按说法键去重后批量调用 |
| I1 需求拆解 | `{method_query, paper_query, constraints}`；每个条件保留需求出处及未明确项，不擅自放宽限制 |
| I1 适用性判断 | 单元为方法/工作及关联上下文；按资源条件逐项返回 `PredRow`，声明整体合取规则，新增材料后的复核保留前次 call_id |
| I1–I6 材料取得 | `SelectSources` 消费入库时的来源锚点（I3 为实验锚点）；缺绑定记录 `material=missing`，材料解释由后续 `A_map` 完成 |
| I2 细节抽取 | 按问题项返回 `{field, value, record_ref, basis_refs, missing}`，不把不同实验设置合成一个值 |
| I3 结果行抽取与可比性 | `rows` 保留行键、被测对象、数据、指标、单位、方向、数值、条件和来源；`A_pred` 以结果行对为单元，明确检查维度，只有条件满足且数值口径明确才比较 |
| I4 问题范围与综合 | `A_pred` 逐候选判断与输入问题的范围关系；`plan={dimensions, missing}`；材料位置另由 `SelectSources` 取得；综合返回带来源的维度记录，新增共同点或分歧判断须显式列为 `A_pred` |
| I5 命题匹配与证据核查 | 命题匹配逐候选返回 `PredRow`；证据核查以主张及其绑定材料为单元，分别判断支持、反驳或限定条件，不把未支持自动解释为反驳 |
| I6 资源发现与整理 | 查询 payload 遵守 `Search.query` 契约；整理输出 `{resources, setup_facts, unresolved}`，各项关联依据 |
| 共同补查策略 | `Action` 只允许调用本轮提供的访问算子及 `ReadEvidence`，或停止；读取范围、参数类型、目标项与预算均校验，禁止自行增加可用工具 |

这些约定使算法可包含可替换的判断实现，同时保留独立评价边界：固定判断输出可检查路由和数据执行；固定输入材料可评价判断实现；端到端评价再观察二者组合。实现替换后须重新检查判断质量，不能仅凭 schema 一致认定等价。

## 5. 六类 intent 的数据流

**记号：** 下列调用均隐含固定快照 $G$、允许材料范围与预算 $B$；所有子查询遵守同一范围。$\mathrm{refs}(X)$ 提取对象引用，$\uplus$ 合并记录并保留不同路径与来源。$A$ 只消费显式传入的信息。已给出的 $m$/$a$/$b$/$d$ 是经确认的引用；下文 Resolve(read/write) 是携带目标 type、kind 与 scope 的简写。若输入只有名称，先 Resolve(read)；id/alias 唯一命中直接采用引用，语义候选交外部确认。

每个 intent 的来源证明需求存在，以下算子序列是本稿设计，不是 benchmark 自带的标准分解。若发生补查，外部执行者使用共同控制片段：

```text
while 有未解决项且 B 尚有预算:
    action = Router(当前结果, 未解决项, 已声明转移规则)
    若没有适用规则:
        action = A_policy[选择补检、读取已有来源或停止](
            u, 当前结果, 未解决项, allowed_actions, B)
    校验 action 的类型、参数、引用范围及剩余预算；非法则进入有界修正或错误出口
    若 action=停止: break
    delta = 外部执行者调用 action 指定的访问算子或 ReadEvidence
    更新当前结果与预算；仅对受影响项重新调用 A_map/A_pred
```

循环不由中间件调度；普通路由不调用模型，特殊算子无内部工具循环。停止时保留未知项、执行错误、未处理项、未访问范围与未检查配对，不能以预算耗尽代替否定答案。所有特殊调用先经过 §4.3 的校验再使用 payload；修正也计入预算。

### 5.1 共同材料选择规则与判断点审计

本节区分三类工作：**数据处理**按字段、绑定和规则执行；**语义计算**产生新的解释或判断；**编排介入**重新决定执行策略。契约明确的外部 `A_map/A_pred` 可以成为预先编排程序中的节点，其前后校验与路由也可以连续执行。连续执行段以需要新规划的位置为边界，不以每次模型调用为边界。“仍需判断”仅针对当前表示与规则，不表示该步骤永远无法结构化。

下文 `SelectSources` 是普通程序的候选辅助函数，不增加一个研究算子。`source_policy` 由任务配置给定，声明待核查项生成规则、材料优先级、稳定的同序处理规则、已读材料处理及预算。规则只消费显式字段，不判断材料是否在语义上足以回答问题。

```text
SelectSources(targets, inputs, source_policy, B)
  targets: 带 unit_key / condition_id 的待核查项
  inputs: 保留主体—记录—固定版本材料位置绑定的已有结果
  → 按绑定取得候选位置，记录 target_keys
  → 按材料版本与位置去重，保留各目标到该位置的多对多绑定
  → 按 source_policy 排序并在剩余预算内选取
  → {source_refs, bindings, states, coverage}
```

抽取 Agent 在入库时为来源化记录写入材料锚点；I3 的实验锚点覆盖表、图与正文位置，成本计入主张 A。SelectSources 只消费已有绑定，定位不足记 `material=missing`；coverage 与 AccessResult 同构。任务配置提供问题项，必要的自由需求解释显式计费；复核对象可包括已有正负判断。

| Agent 调用类 | 让渡读取时验证、提高构建正确性后的替代方式 | 不可替代的残余 |
| --- | --- | --- |
| 指称解析 | 作用域 alias 与写入唯一约束 | 新说法、冲突键的语义确认 |
| 取值规范化 | 作用域 alias 与版本化规则 | 未收录条件、作用域歧义 |
| 需求解释 | 跨任务复用的任务模板 | 模板未覆盖的自由需求 |
| 开放判断 | 复用带条件的已存判断与规则 | 新证据、新适用范围和开放结论 |

前三类通过构建正确性压缩运行时调用；开放判断是保留语义计算的主体。

#### 5.1.1 配置来源、成本与公共输入

本节审计支持主张 B 的可用性、组合语义保持及规则/词表复用；主张 A 的理解经验复用另需与每次重读对照并计入构建成本。任务配置也是评价输入，须记录来源、版本及生成成本。固定知识快照上的受控比较向算子、直接 Cypher 和查询模板基线提供相同配置、词表、材料及预算；端到端比较另计配置生成与知识构建成本。不能把人工提供的绑定规则计为算子自动发现的收益。

| 配置层 | 内容与提供者 | 成本归属 |
| --- | --- | --- |
| 跨任务领域配置 | 系统设计者维护的角色目录、规范化词表与状态转移规则 | 记录构建、修订及跨任务复用范围，不假定一次编写永久适用 |
| 任务实例输入 | 用户或 benchmark 设计者明确给出的比较条件、读取策略与预算 | 所有基线共享；缺失项保留未明确，不由默认值悄悄补齐 |
| 运行时解释 | 外部 Agent 从自然语言生成问题项、条件绑定或策略提案 | 显式 `A_map/A_policy`，校验后执行；模型调用、人工修正及失败均计入成本 |

#### 5.1.2 I3：按步骤审计实验比较

表格定义步骤契约，下文同编号伪代码给出执行顺序；所有模型输出经 §4.3 校验，空批次跳过，错误和未处理项独立保留；状态统一见 §4.3.2.1。当前逐步审计覆盖 I3/I6。

| 步骤 / 执行者 | 输入与输出 | 执行与状态约定 |
| --- | --- | --- |
| I3.1 明确条件 / 程序或外部 `A_map` | 请求 → 方法、数据引用及必需比较条件 | 读取任务配置或显式解释需求；方法与数据名称经 Resolve 解析。缺请求字段返回 `resolution=missing, missing_in=request`，不自行选择标准 |
| I3.2 实验访问 / 中间件 | 对象引用 → 实验、参与角色与来源锚点 | 按 dataset 的 include/depth 查询；额外可展开实验和缺 role 的诊断分别返回。报告值关系分析另以显式图查询取得相关论文的 CITES 线索，所有访问保留预算、分页和覆盖信息 |
| I3.3 选材与读取 / 外部程序 | 待核查项、实验及材料位置 → 已读材料与目标绑定 | 消费已有锚点；缺位置、待读和读取失败分别记 `material=missing/deferred/error`，不隐式检索新来源 |
| I3.4 结果抽取 / 外部 `A_map` | 表、图、正文和脚注 → 临时结果行 | 行保留方法、变体、数据、指标、数值、单位、方向、条件和来源，不入库；格式错误按有界修正规则处理 |
| I3.5 条件对齐 / 外部 `A_pred` 与程序 | 原值及上下文 → 带依据的条件对应判断 | Agent 读取材料判断条件说法是否等价；程序按任务内键回填，保留原值、作用域和依据。未知或冲突不强行规范化，不要求切分、协议或指标有库内节点 |
| I3.6 配对与可比性检查 / 程序及外部 `A_pred` | 临时行对、条件和材料 → 逐条件 `PredRow` | 按任务规则和预算形成候选行对；比较条件由 Agent 判断，按必需条件强三值合取。语义未知按补读或策略规则处理；共同实验不证明条件相同 |
| I3.7 数值比较与输出 / 程序及外部 `A_pred` | 条件判断、数值与材料 → 比较、报告值关系和未决项 | 只有全部必需条件为 T 且单位/方向明确时才进行数值比较。报告值的同源、独立同条件、不可比或未知由 Agent 判断，程序结合数值观测组织输出 |

图只负责定位实验与材料，结构中保存被测方法及角色、数据集和任务，不保存比较所需的条件明细。结果抽取、条件对齐与比较条件检查消费原文，输出是任务内临时记录。程序仍负责去重、预算、字段校验、三值合取与数值计算。

临时行使用任务内 `row_key`，保留所属实验引用、固定材料版本和表格位置；方法与数据能对齐到已确认引用时使用引用，否则保留原说法与未解决状态。变体、指标、切分和协议参数以带依据的临时值表达，不伪造库内 ref。

条件对齐记录为 `{raw_value, canonical_ref_or_value, scope, basis_refs, states}`，Agent 判断另以 `PredRow` 保留条件键、依据和调用记录。相同说法只在上下文与作用域一致时去重；同名不能推出相同含义。单位换算仅在口径已明确、且任务提供适用规则时由程序执行，并记录规则版本。

必需比较条件由任务与领域配置声明。例如检索评测需说明数据版本与切分、候选集合或检索语料、指标定义及重排序设置；时间序列任务需说明任务模式、回看窗口、预测长度等相关条件。未声明或材料不足的条件不能默认一致。配置的来源、版本与构建成本独立记录。

#### 5.1.3 I6：按步骤审计实现资源取得

| 步骤 / 执行者 | 必需输入与输出绑定 | 规则及可观察分支 | 剩余语义计算 / 重新规划条件 | 消除该语义调用所需表示及代价 |
| --- | --- | --- | --- | --- |
| I6.1 明确目标 / 程序或外部 `A_map` | 方法及用途要求 → 请求 | 读取目标配置或解释用途，名称经 Resolve 解析；缺请求字段 resolution=missing、missing_in=request 时返回待明确项 | 用途解释需显式调用 | 任务模板；付需求填写成本 |
| I6.2 实现取得与候选发现 / 中间件及外部程序 | 方法引用、标识/别名 → 已存实现绑定与相似候选两个集合 | Get 方法后读取显式资源说法字段；仅自由描述存在时 A_map 抽取 mention/identifier/kind/依据，再按 Entity/code 或 Entity/model Resolve，论文给出的仓库或模型链接作为 url 标识与名称一并传入；开放用途仍 Search discover；Context 装配描述、Observation 与来源 | 自由描述提取资源名计入 A_map；用途改写或确认新实现关系需显式判断；已声明搜索耗尽后，扩展来源才需策略提案 | 方法—实现—依据绑定；付关系验证与维护成本，相似命中不能替代绑定 |
| I6.3 选材与读取 / 外部程序 | 配置项—材料位置 → 有绑定的材料 | 按配置项生成 targets，选材读取，记录 `material=missing/deferred/error/available` | 已有锚点不足记 material=missing；需要新来源时按补读规则或 A_policy | 报告/记录的材料锚点；付入库提取和材料变更维护成本 |
| I6.4 配置整理与输出 / 程序或外部 `A_map` | 配置、已有记录、临时解释 → 资源/配置/未解决项 | 结构化字段投影，文本配置显式 A_map 抽取；返回未解决项与 coverage | 自然语言整理可以预编排；执行、核验或持久写入须独立工作流，本流不自动发起 | 类型化配置及字段来源；付格式适配与抽取评价成本 |

#### 5.1.4 审计后的契约与测量项

| 契约或测量项 | 对应步骤 | 约定与检查 |
| --- | --- | --- |
| 结果单元与条件身份 | I3.4–I3.6 | 入库只到实验级；行级结果由 A_map 按锚点临时抽取，不入库（§6.1） |
| Resolve 三级命中 | I3.1、I6.1、I6.2 | id/alias/semantic 命中比例待实例测量，另报冲突键、按说法键去重后的语义确认次数，以及候选被外部全部否定的比例 |
| 条件到材料的绑定 | I3.3、I6.3 | 入库提供记录级锚点并计入 A，任务按这些锚点选材；锚点足以定位的比例待实例测量 |
| 访问诊断与覆盖传播 | I3.2、两条流的选材步骤 | coverage 保留输入链；role 诊断限定 EVALUATES subjects 与已选数据范围，只回传 count/refs |
| 规则与临时判断的来源 | I3.5–I3.7 | 保存规则版本、模型调用与输入材料；按 origin 路由 U，分别记录构建、规则执行和本次语义成本 |
| 证据计数 | I3.7 | 按 I3 的关系口径检查：同源报告是否被计成两份证据，不可比的差异是否被当成矛盾；S 与 R0 分别统计这两类错误。报告值关系判定由 Agent 完成，两组的差别只在定位成本 |

**写路径前置约定。** 写入以批为单位，由 `Commit(delta, mode: dry_run | apply)` 执行，身份解析分两处：

- 外部 Agent 填写增量前，可用 Resolve(write) 逐个说法查重；精确命中后继续语义查重，由外部 A_pred 确认重复对象或补 alias。
- `Commit` 的 dry_run 对整批统一解析，既看库内也看批内：同批两个对象注册同一键、同批多个新对象共用一个非唯一标识，只有在整批层面才看得到，逐个调用 Resolve 发现不了。dry_run 返回新建、更新、不变、冲突与查重候选；有冲突时 apply 拒绝整批。

经确认的新说法以独立显式写入注册 alias，原子检查规范化配置下的作用域唯一键；新冲突拒绝写入并返回冲突对象，原键保持有效；仅导入或核查发现的既有冲突隔离为 ambiguous。唯一命名空间的标识以列表存在对象上，后端约束管不到列表元素，由 `Commit` 在写入事务内复查。入库抽取同时写入实验锚点，保留材料版本与来源；alias 与锚点成本计入主张 A。由于语义阶段不设阈值，每个新对象写入时都有语义近邻需要外部排除，这也是主张 A 的固定构建成本。

E09 已实现种子增量与部分论文增量的 `Commit`；论文编译与入库尚待对齐 paper-form-v4，并按当前抽取口径重新入库验证。论文抽取范围见 [抽取原则](./extraction_principles.md)，表单、编译规则与检查见 [Commit 契约](./commit_contract.md)。当前更新只能覆盖属性，不能撤销属性或 alias；Content 不原地修改，内容变化按冲突拒绝。Observation 等增补内容经 Commit 的增补表单写入。当前不做修订、撤回与对象合并，需要时清库重建。

这两条流可预编排到哪些位置，由上述状态及配置决定：已有处理规则的缺失、分页和错误可直接路由；没有适用规则才交给策略选择或返回未解决项。模型调用数、判断单元/条件数、重新规划次数，以及配置构建/规范化成本分别统计。本节固定设计契约，未扩展 schema 实现。

所有链条中的最终组织，若仅是投影、排序、分组或模板呈现，应直接由普通程序完成；下文保留的 `A_map` 仅覆盖需求解释、异构材料抽取或自然语言组织。把多个判断合为一次调用只减少往返，是否减少新判断还需按处理单元及条件分别统计。

### I1 发现适合需求的工作与方法

> 只有少量领域标注，寻找可用于专业文献检索的适配方法，并查清资源前提。

**依据与输入输出：** [S1] 支持需求驱动的论文发现；方法输出与资源适用性是本文扩展。输入需求 $u$；输出候选工作/方法、$T/F/U$ 适用性及依据。

**必要信息与表示：** 论文为 Entity、方法定义为 Concept、贡献、主张及实验为 Content；资源前提可能在任何对象的剩余描述字段或原文中。

```text
p = A_map[拆出发现描述与需判断的资源条件](u)
M = Search(Concept, query=p.method_query, kinds={method})
P = Search(Entity, query=p.paper_query, kinds={paper})
C = Context(refs(P), question=u, roles={source_contents, discussed_objects})
B1 = Context(refs(M) ∪ C.method_refs, question=u,
             roles={definition, descriptions, experiments, participants, sources})
J = A_pred[是否满足任务和资源限制](u, p.constraints, M ⊎ P ⊎ C ⊎ B1)
targets = 按复核规则从 J 生成待核查项，保留对象与条件键
need = SelectSources(targets, {M, P, C, B1, J}, source_policy, B)
E = ReadEvidence(need.source_refs)
受影响项 = 按 need.bindings 将成功读取的新材料回连到对象与条件键
delta_J = A_pred[仅复核新增材料影响的对象与条件，缺信息则 U](
    u, p.constraints, 受影响项, M, P, C, B1, J, E)
J2 = 按对象与条件键合并 J 与 delta_J，保留历史、未处理及错误状态
返回 {候选, J2, 来源, 覆盖范围, 未解决项}
```

source_contents/discussed_objects 是 Context 的组合角色：取得来源于论文的内容及其明确讨论对象，并保留中间绑定。未记录的资源依赖不能解释为无需资源；可由外部 $A_{\text{policy}}$ 决定继续补查。

**访问要求：** Entity 与 Concept 使用不同检索契约，Context 装配跨类视图；方法适用性留给 Agent。

### I2 理解机制、条件与细节

> 已找到方法 $M$，查明其“少样本”设置实际用了什么标注、额外语料和教师模型。

**依据与输入输出：** [S2] 支持全文信息需求与证据问答。输入 $m$、问题 $u$；输出对应实验的细节答案及未知项。

```text
M = Get({m})
C = Context({m}, question=u, roles={definition, descriptions, experiments, sources})
T = Search(Content, query=u, where={about:m})
targets = 任务声明的问题项；自由文本问题先显式调用 A_map 提取问题项
need = SelectSources(targets, {M, C, T}, source_policy, B)
E = ReadEvidence(need.source_refs)
answer = A_map[逐项解释标注、语料和模型，对应具体记录](u, M, C, T, E)
返回 {answer, 引用, 未解决项, C/T 的覆盖范围}
```

**必要信息与表示：** 定义由 Concept 提供，具体设置由 Content 及其上下文提供；不要求每种预处理步骤独立成节点。`about:m` 仅匹配已声明的 ABOUT 角色；Context 的实验分支另使用参与关系。两者覆盖不足时可显式扩大为已知来源范围搜索，不能把宽范围命中自动视为关于 $M$。

**访问要求：** 按问题取得内容与上下文，检索文本不必包含最终答案，材料解释由 $A_{\text{map}}$ 完成。

### I3 组织结果并判断可比性

> 比较方法 $A$、$B$ 在数据集 $D$ 上的结果，确认切分、候选集合和重排序设置是否一致。

**依据与输入输出：** [S3] 支持任务、数据、指标和分数整理，可比性为扩展。输入 $a$/$b$/$d$、问题 $u$；输出逐实验的数值与条件、比较或不可比较理由，以及报告值之间的关系口径。

```text
spec = 读取领域配置和任务条件（include 默认 {}，depth 默认 1）；名称先 Resolve(read) 并按 §4.1 路由，只采用 resolved 或外部确认的 a/b/d；缺项返回 missing_in=request # I3.1
X = Experiments(subjects={a,b}, dataset={ref:d, include:spec.include, depth:spec.depth})                                      # I3.2
role_diag = X.diagnostics.role_missing；仅 EVALUATES a/b 且 USES 已选数据范围的缺 role 实验 # I3.2
expandable = X.diagnostics.expandable；独立返回数量、引用及 coverage               # I3.2
dependencies = 显式图查询取得相关来源论文间的 CITES、描述与来源，保留范围和 coverage；查询模式见下文 # I3.2
targets = 按 spec 的结果字段与条件键生成待核查项                               # I3.3
need = SelectSources(targets, {X, dependencies}, source_policy, B); E = ReadEvidence(need.source_refs) # I3.3
rows = A_map 读取实验锚点，抽取临时结果行（不入库）                      # I3.4
alignment_units = 按说法、作用域与上下文去重的条件对应候选                         # I3.5
C = A_pred[条件对齐](alignment_units, rows, E)；保留原值、依据和未决项                # I3.5
aligned = 按任务内键回填 C，不以文本相等替代语义对齐，不生成虚假的库内引用             # I3.5
pairs = 按 spec 与 B 从 aligned 形成候选行对，记录未处理键                           # I3.6
J = A_pred[必需比较条件](pairs, rows, aligned, E)；按条件键强三值合取                 # I3.6
comparison = 对 J.value=T 且单位/方向已确定的行对作数值比较                          # I3.7
relation = A_pred[报告值关系](候选报告值对, rows, E, dependencies)                  # I3.7
输出程序将 relation 的预期类别与数值一致/不一致的观测组合；所有判断不入库              # I3.7
返回 {rows, comparison, relation, J, role_diag, expandable, dependencies, states, coverage, 来源, 未解决及未处理项} # I3.7
```

**必要信息与表示：** 方法为 Concept、数据集为 Entity、实验为 Content。指标不建节点；结果表由 $A_{\text{map}}$ 按锚点读取并临时抽取。Experiments 返回参与角色和对应材料，不能把实验中所有方法与数据的边直接交叉成结果行。

同一 Experiment 共现仅是配对线索，不直接给出可比结论。外部 Agent 按任务声明的条件检查数据版本与切分、评测协议、指标含义和方向等，缺字段不能视为相等，原字符串不同也不能直接判为不可比。抽取事实和判断质量独立评价。

**访问要求：** 算子保证返回满足已存对象和数据关联的实验，保留实际参与绑定；行级对应和条件判断由 Agent 读锚点建立。

**报告值之间的关系口径。** 论文之间的转引与复述常不严谨：同一组数字在另一篇论文中可能抄错、取自不同版本或印错。口径只回答"按论文自己的陈述，两个报告值**本该**是什么关系"，实际是什么关系由读表得到；所谓不一致，就是本该相同、实际不同。不判断哪个数字是对的。

**图的责任。** 图定位涉及同一方法与数据集的实验，通过 `CITES` 及描述提供论文结果依赖线索，并给出表、图和正文的位置。四类报告值关系全部由 Agent 读原文判定；该口径也是评测时的参考框架。

取结果键相同的两个报告值（方法、变体、数据集、指标，以及任务要求的其他键，如预测长度 $T$），先定**预期类别**：

| 预期类别 | 判据（Agent 读原文） | 图提供的线索 |
| --- | --- | --- |
| 同源 | 一方声明引自另一方所在的论文；或两者出自同一论文，方法、变体与条件相同 | 两篇论文之间的 `CITES` 及其描述；同一论文中评测同一方法的实验 |
| 独立、同条件 | 两者都是实际运行，变体与条件相同 | 同一方法与数据集的实验列表 |
| 不可比 | 已知有条件不同：回看窗口、单变量与多变量、监督方式、训练数据、切分 | 无，条件在原文中 |
| 未知 | 来源或条件原文未说明 | 无 |

再由读到的数值定**观测**（一致或不一致），两者组合成解释：

| 预期 \ 观测 | 一致 | 不一致 |
| --- | --- | --- |
| 同源 | 同一份证据传了两次，只算一份 | 转引偏差：候选解释为抄错、版本不同或印刷错误，只标出，不裁决 |
| 独立、同条件 | 复现一致，可算两份证据 | 复现差异，本身是有意义的发现 |
| 不可比 | 数值相同不说明什么 | 差异不构成矛盾 |
| 未知 | 可能是转引，回答中标为推断 | 不下结论 |

- **为什么有意义。** 研究者要的是证据怎样计数：一个比较结论背后有几份独立证据，哪些只是同一次运行被转述，哪些差异可以忽略。它对应同一结果被重复计数、条件被静默合并这两类组合错误。
- **S 与 R0 的差别在哪里。** 判定本身两组都靠读原文；差别在于找到该对读的两处：S 从 `CITES` 与实验分组取得定位线索："PatchTST 的哪些实验引用了 DLinear 论文的结果"，R0 要通读全文找到转引声明。小规模材料下 R0 可以通读全文；定位收益及其随规模的变化需要实测。
- **边界。** 分类在 I3.7 查询时形成临时结果，本只读流程不自动入库。外部认为值得复用时，可通过独立显式写入保存为 Observation，保留对象对、条件、材料依据和形成信息；该写入契约尚待确定。
- **不承诺。** 只有转引或重复报告让两个数字发生重叠时，不一致才能被发现，没有重叠的错误查不出来。由数值相等推出转引属于推断。版本只能作为候选解释：库只知道自己存的材料版本，转引方用的版本通常不知道。

实例（见 [I3 首个实例的问题集](../../discussions/2026-10-03-i3-first-instance-question-set.md) 的参考答案）：

- PatchTST 表 3 中的 DLinear 与 Pyraformer：同源，第 128 行写明转引自 DLinear 论文。DLinear 在 ILI 以外的数据集上数值相等，是同一份证据传了两次；Pyraformer 的 MSE 错后一格，DLinear 的 ILI 数值在库中这一版 DLinear 论文里找不到，都是转引偏差。
- PatchTST 表 8 与 DLinear 表 5 在 ETTh1、$T=720$ 上的数值：同源，转引偏差。
- DLinear 表 9 与表 2 在 ILI、$T=36$ 上的数值：同一论文内同源，转引偏差。
- PatchTST 重跑的 FEDformer 与 DLinear 表 2 中的 FEDformer：前者在六个回看窗口中取最好，后者 $L=96$，不可比，差异不构成矛盾。

定位的结构部分是一条图查询（待 E09 对齐现行入库契约后验证）：

```cypher
// 引用了 $paper 结果的论文中，评测方法 $m 的实验，以及 $paper 自己评测 $m 的实验
MATCH (a:Paper)-[c:CITES]->(b:Paper {id: $paper})
MATCH (e:Experiment)-[:FROM]->(a), (e)-[:EVALUATES]->(m:Method {id: $m})
OPTIONAL MATCH (e2:Experiment)-[:FROM]->(b), (e2)-[:EVALUATES]->(m)
RETURN a.id AS citing, c.description AS dependency, e.exp_key AS citing_experiment, collect(e2.exp_key) AS cited_experiments
```

它给出"该对读哪几处"，不给出"是否同源"：后者由 Agent 读 `CITES` 描述与两处原文判定。

### I4 综合同一问题下的路线与发现

> 围绕“少标注条件下如何改善领域检索”，整理路线、条件、实验发现与分歧。

**依据与输入输出：** [S4][S5] 支持多论文综合及比较表。输入问题 $u$、可选维度；输出带来源的表格与综合，说明覆盖范围。

```text
Q = Search(Concept, query=u, kinds={issue})
J = A_pred[是否为同一问题范围](u, Q)
C1 = Context(refs(J=T), roles={descriptions, discussed_objects, experiments, sources})
C2 = Search(Content, query=u, kinds={claim,experiment})
C3 = Context(refs(C2), roles={participants, discussed_objects, sources})
plan = 读取任务配置中的比较维度；仅自由文本维度需 A_map 提取
若维度未明确: 返回待明确项
need = SelectSources(按维度生成的待核查项, {Q, C1, C2, C3}, source_policy, B)
E = ReadEvidence(need.source_refs)
pairs = 按声明的配对规则和 B，从 C1/C2 的主体记录生成记录对，保留各自绑定
K = A_pred[按声明维度判断指定记录对的共同点或冲突，缺信息则 U](
    u, plan.dimensions, pairs, C1, C2, C3, E)
result = A_map[按维度组织记录与已有判断，保留分歧和缺项](
    u, plan.dimensions, C1, C2, C3, E, K)
返回 {result, 引用, 覆盖范围, 未解决项}
```

**必要信息与表示：** Issue 是 Concept 的可选聚合入口，来源化回答是 Content，论文是 Entity。没有已确认 Issue 时 C1 为空，但 C2 仍可发现内容。Concept 检索与 Content 检索不混为一个无类型候选池。比较维度未确定时先返回待明确项，不在组织答案时暗中增加判断标准；配对规则、每个维度的谓词及未检查配对须保留。

**访问要求：** descriptions 经 ABOUT 取得关于该问题的主张，可包含相反立场；语义分组与综合由 Agent 完成，不把共同问题等同共同结论。

### I5 核查主张的依据与成立范围

> “困难负样本能改善检索效果”有哪些依据、限定条件和不同发现？

**依据与输入输出：** [S2][S6] 支持证据核查形式；SciFact 的原领域不直接证明 CS 覆盖度。输入说法 $u$；输出来源化依据、不同发现及判断范围。

```text
P = Search(Concept, query=u, kinds={proposition})
J = A_pred[是否表达同一命题及适用范围](u, P)
C1 = Context(refs(J=T), roles={descriptions, sources})
C2 = Search(Content, query=u, kinds={claim})
V = Evidence(claims=C1.claim_refs ∪ refs(C2),
             include_relations={supports,opposes})
targets = 按本次核查要求生成逐主张待核查项，含要求复核的已有判断
need = SelectSources(targets, {C1, C2, V}, source_policy, B)
E = ReadEvidence(need.source_refs)
K = A_pred[逐主张及材料判断支持、反驳和限定条件，缺信息则 U](u, C1, C2, V, E)
answer = A_map[组织已有核查判断及其范围、依据和未知](u, C1, C2, V, E, K)
返回 {answer, 有方向的关联与引用, 覆盖范围, 未解决项}
```

**必要信息与表示：** 共同命题为 Concept，具体主张与实验/观察为 Content。Evidence 返回输入主张及一跳已存主张关系、这些主张的直接依据与来源；更深扩展需显式请求和预算，不能无限闭包。

**访问要求：** 已存支持关系不等于本次验证成功；相似度不表示支持。外部 $A_{\text{policy}}$ 可以改写查询搜寻相反发现，但单次未召回不证明不存在反例。

### I6 取得实现资源及其依据

论文声称公开、找到实现、成功运行与结果复现是不同发现。当前模型只保存实现对应及其来源；运行与复现由外部执行者完成，结果不入库。阅读形成的资源评估可作为 Observation 读取，但不能当作运行成功。

> 准备采用方法 $M$，寻找代码或模型及必要配置，并取得其原文依据。

**依据与输入输出：** [S7][S8] 支持资源与配置信息需求；资源发现是前置扩展，执行与核验不在本流程内。输入 $m$、用途 $u$；输出实现资源、潜在候选、配置依据与未解决项。

```text
spec = 读取目标配置；名称先 Resolve(read) 并按 §4.1 路由，采用已解析或外部确认的 m；自由用途 A_map 提取，缺请求字段记 missing_in=request # I6.1
M = Get({m}); R = Implementations(method=m, resource_kinds={code,model})         # I6.2
mentions = 从 M 的显式资源说法字段（若存在）读取 mention/kind/依据；仅有自由描述时显式 A_map 抽取，计入语义成本 # I6.2
H = 对 mentions 按说法键去重后分别 Resolve({identifier?: 链接, mention}, kind=code 或 model, scope=global, mode=read) # I6.2
H = resolved 直接采用；ambiguous/candidates 交 A_pred[同一对象] 确认；全部 F 或 none 保留未解决项；开放用途的额外候选由显式 Search discover 取得 # I6.2
C = Context(refs(R) ∪ refs(H), roles={descriptions,observations,sources,parts}) # I6.2
targets = 按 spec 配置字段生成待读取项                                          # I6.3
need = SelectSources(targets, {M,R,H,C}, source_policy, B); E = ReadEvidence(need.source_refs) # I6.3
answer = 投影已有字段；文本配置显式 A_map 抽取，保留来源                         # I6.4
返回 {answer, states, coverage, 未解决及未处理项}                                # I6.4
```

**必要信息与表示：** 资源共用 Entity 契约；实现对应由 `IMPLEMENTS` 表达并带来源；论文的发布声明与配置按锚点读取。

**访问要求：** Implementations 的实现关联是硬条件；Search 的相似候选不会自动升级为实现。CORE-Bench 的成功执行和 PaperBench 的结果匹配属于外部执行的发现，不由本流程产出或入库。已存 Observation 只作为带范围的阅读评估返回。

## 6. 映射到属性图：保持契约，允许改变存储

### 6.1 任务参数到图模式

以 `Experiments(subjects={a,b}, dataset={ref:d,include:{},depth:1})` 为例。固定快照中 ref 唯一确定记录；以下为实验级映射核心，尚未执行验证。先按反向 PART_OF 枚举 depth 内资源路径，得到 `$selected_ids`（严格时仅 d）与 `$extra_ids`（可展开但未选资源），保留每个目标的 witness。显式展开只采用 include 指定的边类型，循环路径按节点引用截断。三支共享 subjects、快照、范围与预算。

```cypher
MATCH (e:Content:Experiment)-[tested:EVALUATES]->(m:Concept)
WHERE m.id IN $subject_ids
MATCH (e)-[used:USES]->(d:Entity)
WHERE used.role = 'evaluation_data' AND d.id IN $selected_ids
RETURN DISTINCT 'matched' AS bucket, e, m, tested, d, used
UNION ALL
MATCH (e:Content:Experiment)-[tested:EVALUATES]->(m:Concept)
WHERE m.id IN $subject_ids
MATCH (e)-[used:USES]->(d:Entity)
WHERE used.role = 'evaluation_data' AND d.id IN $extra_ids
RETURN DISTINCT 'expandable' AS bucket, e, m, tested, d, used
UNION ALL
MATCH (e:Content:Experiment)-[tested:EVALUATES]->(m:Concept)
WHERE m.id IN $subject_ids
MATCH (e)-[used:USES]->(d:Entity)
WHERE used.role IS NULL AND d.id IN $selected_ids
RETURN DISTINCT 'role_missing' AS bucket, e, m, tested, d, used
```

`matched` 装配为结果，其余分支只按实验引用去重返回 count/refs 与 coverage；role_missing 的缺失来源为 store。extra_ids 为 parts 在 depth 内的资源集合减去 selected_ids（按引用去重），默认仍枚举其额外命中用于报告；展开后 witness 标记 PART_OF。预算截断下报告已见数量。matched 直接保留命中的 m 与 tested（含 target/baseline 角色），按完整绑定去重；装配只补取任务、来源等其余已存上下文。诊断分支在输出 count/refs 时才按实验引用去重。当前论文表单不写切分关系；I3 的版本与切分可比性由 Agent 按材料判断，不能以缺失推定相等。

**结果精度停在实验级。** `Experiments` 只返回实验及其锚点与参与绑定。行级对应由 Agent 按锚点读原文建立，作为任务内临时记录（I3.4）；实验内的共同参与不得被当作行级对应。

### 6.2 类内索引与关系访问

| 类别 | 索引配置 | 图访问配置 |
| --- | --- | --- |
| Entity | 已注册 identifier 精确索引；name/aliases；description 全文与向量 | 实现、组成、描述与观察视图 |
| Concept | name/aliases；definition（陈述型为 text）的固定编码 | 定义体系限制、指定概念关系扩展、回答/命题表达 |
| Content | text 全文与向量；来源引用定位 | 讨论对象、实验参与绑定、主张关系与依据装配 |

可共享索引引擎、编码模型和融合组件，也可按类别建立索引；同类 kind 遵守同一配置。图遍历已有后端支持，全文与向量索引采用后端接口 [S10]。异构嵌套描述可序列化或拆图存储，不能假设任意嵌套 map 都是 Neo4j 属性 [S11]。

配置需记录字段映射、文本修订、编码模型与预处理版本；关系变化也可能改变候选资格或派生文本，必须使相关派生视图失效或更新。嵌入计算部署边界待定，不影响中间件不调度语义判断 Agent 的约定。

> **原型配置（E09）。**
>
> - **名称词面通道：** 查询 NameKey 原字符串（`raw`）的全文索引，再经 `NAMES` 取得对象。对象上没有 aliases 列表（[Graph Model V2](./graph_model_v2.md) 第 5 节），所以这一通道不查对象本身。
> - **文本通道：** Entity 查 description，Concept 查 definition（陈述型为 text），Content 查 text；关系的 description 同样入库时建向量（[Graph Model V2](./graph_model_v2.md) 第 5 节）。E09 尚待补上 Content 与关系描述。
> - **向量通道：** 输入文本按类别固定，为名称、由 NameKey 装配的 alias 与该类的文本字段，note 不参与；编进名称与 alias，是为了只给称呼时语义阶段仍有可比内容。写入侧不加任务说明，查询侧加。
> - **失效：** 注册或撤销 NameKey 会改变向量输入，与文本修订一样使该对象的派生向量失效。每个对象以 `embedding_key`（模型名与输入文本的哈希）判断是否需要重算。
> - **按 kind 过滤：** 向量索引按主 Label 建立，先取较大的候选池再按 kind 过滤，可能漏掉 kind 内的可行候选（§4.2），过滤方式记入 coverage。
> - **部署：** 嵌入由外部服务计算（Qwen3-Embedding-8B），向量作为检索派生属性存于对象上，不属于内容属性。

## 7. Workload、设计取舍与验证

### 7.1 从六类 intent 提炼可评测 workload

| Workload | 固定输入与期望输出 | 主要检查 |
| --- | --- | --- |
| W1 对象定位 | 名称/标识/定义、类型、范围 → 候选与匹配方式 | 资源指称、概念含义、内容相关性分别标注 |
| W2 关系约束检索 | 查询描述 + 已确认引用/关系条件 → 满足条件的候选与 witness | 硬约束正确性、条件内召回、缺失与截断 |
| W3 上下文装配 | 对象引用 + 逻辑角色 → 内容、参与绑定与来源 | 多跳对应、对象去重及路径保留 |
| W4 实验/证据组织 | 方法或主张引用 → 实验包/依据包 | 实验级对应、关系方向、来源与未记录情况 |
| W5 材料读取与组合 | 来源引用 → 固定版本材料，再供外部判断 | 材料可用性、引用正确性、Agent 与系统错误分离 |

每个实例还必须固定数据状态、预算、参考结果及允许的信息访问。六类 intent 提供利用需求，不代替更新 workload；维护评价需另选真实增量、修订或撤回序列。

### 7.2 分类与算子如何一起调整

| 发现的问题 | 模型选择 | 算子与代价变化 |
| --- | --- | --- |
| 实验结果需要从表格解释 | 库内保存实验索引，结果按原文锚点读取 | 计入每次临时抽取与比较的成本，评价定位是否节省整体访问成本 |
| 按数值筛选 | 当前不支持库内数值过滤 | 需读取材料并在临时结果上处理，计入读取、抽取与判断成本 |
| Entity 与 Concept 接口实际无差异 | 合并公共操作，保留必要类型；或调整分类 | 不能仅靠领域名称证明三套检索契约必要 |
| 某种关联需独立引用和核查 | 为关联事实保留稳定引用，必要时暴露 Content 陈述 | 允许检索关联依据，不由物理中间节点数量决定分类 |

本稿支持三类的理由是**资源指称、定义与范围、来源化表达与上下文**分别要求不同的字段和关系处理。该理由支持一个可检验的设计选择，不宣称三类具有普遍完备性。类内统一也应接受反例：若某 kind 总需私有检索路径，需检查类别边界或契约粒度。

### 7.3 验证什么，而非只展示什么

| 设计主张 | 对照与指标方向 |
| --- | --- |
| 类内统一、类间差异有价值 | 对比无差别字段/通道、按 kind 定制、候选三类契约；检查各类召回、错误及构建维护成本 |
| 关系参与检索确有必要和收益 | 节点文本检索、关系硬过滤、关系扩展、完整视图装配消融；检查正确性与召回，不只看答案流畅度 |
| 任务级接口降低使用成本 | 同一知识、同一 Agent 和预算下，对比充分说明的 Cypher、查询模板与候选算子；计算交互、执行与修复成本 |
| 图映射保持信息语义 | 用独立参考绑定检查结果、来源与对应；不能只验证 schema 合法 |
| 混合检索和文本选择有效 | 词面、向量、融合消融；摘要直用与规范化文本比较，计入生成成本 |
| 连续组合减少编排与重复判断 | 按 §5.1 审计固定实例，分别记录重新规划次数、模型调用/往返、处理单元与条件数、材料量和成本；同时检查正确性、覆盖及构建维护成本 |
| 外部判断与执行能够分别评价 | 固定算子输入评价中间件，再独立评价 Agent 的意图转换与判断，最后评价端到端 |
| 累积知识值得维护 | 计入初始构建、增量更新、索引/视图维护及复用总成本 |

已有向量检索与图遍历组合 [S13]，所以“组合技术”不是充分的新颖性论证。候选贡献需要落到可复用契约、语义保持、对象装配或维护机制，并通过上述强基线检验。不预设比 Cypher 表达力更强，也不要求完整新代数。

### 7.4 当前验证重点

当前优先把 E09 论文入库对齐现行契约，并验证 I3 的实验定位与材料访问。资源定位、概念范围查询等实例仍需固定输入、所需信息和独立参考输出，据此检查类内契约差异与算子复用。模型、访问接口及 benchmark 的完整实现范围尚未确定。

## 来源与可追溯位置

- **[S1] AstaBench**：官方 Literature Understanding Benchmarks 中 PaperFindingBench 的任务定义。[任务说明](https://allenai.org/asta/bench)。
- **[S2] QASPER**：*A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers*，§2–3、Table 1。[论文](https://aclanthology.org/2021.naacl-main.365/)。
- **[S3] TDMS-IE**：*Identification of Tasks, Datasets, Evaluation Metrics, and Numeric Scores for Scientific Leaderboards Construction*。[论文](https://aclanthology.org/P19-1513/)。
- **[S4] ScholarQABench / ScholarQA-CS**：专家研究问题、rubric 和引用评价。[作者介绍](https://allenai.org/blog/openscilm)，[数据与评价代码](https://github.com/AkariAsai/ScholarQABench)。
- **[S5] ArxivDIGESTables**：*Synthesizing Scientific Literature into Tables using Language Models*。[论文](https://aclanthology.org/2024.emnlp-main.538/)。
- **[S6] SciFact**：*Fact or Fiction: Verifying Scientific Claims*。[论文](https://aclanthology.org/2020.emnlp-main.609/)。用于核查任务形式，领域内容与本项目有区别。
- **[S7] CORE-Bench**：使用代码和数据进行计算复现并回答输出问题。[官方说明](https://github.com/siegelz/core-bench)。
- **[S8] PaperBench**：*Evaluating AI's Ability to Replicate AI Research*，§2.2–2.4 的复现阶段与不同要求类型。[论文](https://cdn.openai.com/papers/22265bac-3191-44e5-b057-7aaacd8e90cd/paperbench.pdf)。
- **[S9] RRF**：*Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods*。[论文](https://doi.org/10.1145/1571941.1572114)。
- **[S10] 索引接口**：[Neo4j 全文索引](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/)、[向量索引](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)。
- **[S11] 属性类型限制**：[Neo4j Property, structural, and constructed values](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)。

- **[S12] 概念标识与关系**：[W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)，§3、§5、§7–8。用于说明概念可有 URI、标签、定义与关系，不作为本三分类的直接依据。
- **[S13] 图与检索组合的已有实现**：[Neo4j GraphRAG User Guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)，VectorCypherRetriever / HybridCypherRetriever。用于界定已有能力，不证明本文接口的效果。

[S1]: https://allenai.org/asta/bench
[S2]: https://aclanthology.org/2021.naacl-main.365/
[S3]: https://aclanthology.org/P19-1513/
[S4]: https://allenai.org/blog/openscilm
[S5]: https://aclanthology.org/2024.emnlp-main.538/
[S6]: https://aclanthology.org/2020.emnlp-main.609/
[S7]: https://github.com/siegelz/core-bench
[S8]: https://cdn.openai.com/papers/22265bac-3191-44e5-b057-7aaacd8e90cd/paperbench.pdf
[S9]: https://doi.org/10.1145/1571941.1572114
[S10]: https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/
[S11]: https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/

[S12]: https://www.w3.org/TR/skos-reference/
[S13]: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html
