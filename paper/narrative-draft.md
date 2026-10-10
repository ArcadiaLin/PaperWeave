# PaperWeave: Shared Accumulation of Paper-Derived Knowledge by Uncoordinated Agents

（标题为候选。）

# 论文草稿

中文记叙事意图；英文代码块留候选短句和用语。两者都用于推进草稿，随设计继续调整。

> **2026-10-10 修订：** 按 2026-10-09 商定的核心命题（互不协调的写入者共同积累，shared accumulation by uncoordinated writers）重写 Introduction 与大纲。旧版以单个研究者的纵向/横向复用为动机，见 Git `df7fb2a`。评测设计见 [`docs/designs/v2/evaluation_draft.md`](../docs/designs/v2/evaluation_draft.md)。

# Abstract

暂时留空。

# Introduction

## Why：

先讲三点背景：

1. **通用 Agent 参与研究：** 读论文、抽取方法与实验、比较、形成判断与报告。这些产物持续积累，后续工作值得在它们之上继续。
2. **积累是共享的，写入者互不协调：** 同一个人或研究组在几个月里开出大量 session，彼此上下文不通；不同项目、不同成员的 Agent 各自读到同一批论文。愿景是一个公共平台（paper4agents）。共享库是写入者之间唯一的通道，读者往往是当初不在场的陌生人。
3. **单写者不需要数据库：** 一个 Agent 在一个项目里复用自己的产物，文件加 Git 是最强基线，可能已经够用。数据库的理由来自许多写入者长期写同一个库，这也是 DBMS 的经典理由：共享数据、完整性、多用户。

```text
Background: General-purpose agents read, extract, compare, and judge papers,
and their outputs accumulate.
Setting: The accumulation is shared. Many agents and sessions that never
coordinate write to one long-lived store, and later readers were not there
when it was written.
Not the setting: One agent reusing its own work within one project, where
files and Git are a strong baseline and may suffice.
```

**为什么是论文知识（暂定）：** 论文领域最初是项目起点的预设，多写者命题是后来才确立的；但选它的理由可以落在数据本身的性质上，而这些性质正好让问题既尖锐又可评测：

- **写入高度重叠：** 引用呈长尾分布，少数热门方法、数据集和 benchmark（如 PatchTST、ETTh1）几乎被每个项目、每个 Agent 反复读到，同一对象被许多写入者各写一遍，是重复与冲突的高发区（C1、T1）。
- **身份难判，但有外部锚点：** 别名、变体、子集（ETT 与 ETTh1、同一方法的不同配置）让身份判断不平凡；arXiv ID、DOI、代码仓库与数据集主页等外部标识又能给去重与误合并提供部分真值。
- **分歧与变化自然发生：** 结果依赖条件，读者可能误读；arXiv 版本更新会改数值，还有勘误、撤稿与复现不一致。C3 的事件不必全靠人工注入。
- **有客观的未来可对照：** 按时间切分，用 $t_0$ 之前的论文建库，以之后论文实际选用的 baseline、数据集与指标为金标准（L4）。
- **数据公开、金标准现成：** TDMS、AxCell、SciREX、LEGOBench、OpenAlex 等，满足可复现要求。
- **知识寿命长、重读成本高：** 每个研究 Agent 从头重读同一批论文，冗余大，是摊销的前提（T2）。

对照其他候选：代码库知识本身就是真值且已由 Git 管理，文件加 Git 基线大概率胜出；企业文档有多写者性质但数据私有、无公开金标准；个人助理记忆本质上是单写者；通用百科已有 Wikidata；医学文献性质相近，但金标准构建需要专业知识，可作推广讨论。

**主张范围（暂定）：** 写成领域系统论文。主张与实验结果只针对论文派生知识；元模型与领域词表分层，因此在 Discussion 中说明机制在设计上与领域无关，推广作为讨论而非主张。"写入高度重叠"是这一选择最关键的支撑，需在选定语料上核实（例如热门方法与数据集被多少篇论文参与）；若重叠不足，T1 测不出退化。

参照 AgenticScholar 的数据管理问题引入：
**学术知识系统管理文档与人工整理的知识，Agent Memory 管理单个 Agent 的交互历史；由许多互不协调的 Agent 持续写入的共享派生知识，尚无人管理。**

再引出可证伪的现象（对应评测 T1）：没有身份、契约、来源与版本约束时，共享积累会随写入者数和写入量增长而**退化**：

- 同一对象被建成多个节点（重复），或不同对象被并成一个（误合并）；
- 产物引用的记录不存在或已改变（悬空引用）；
- 两个写入者对同一结果给出不同读法，后写的静默覆盖前写的（冲突未被发现）；
- 来源被修订或撤回后，依赖它的比较与报告没人知道已经过时。

下游读者拿到的答案随之出错，而且错得不显眼。

```text
Without identity, contracts, provenance, and versions, shared accumulation
degrades as writers and writes grow: duplicate and wrongly merged entities,
dangling references, unnoticed conflicts, and stale artifacts. Downstream
answers become wrong without looking wrong.
```

## Figure 1：多写者共享积累及其退化

放在 intro 的场景图，让读者看到：（a）几个互不知情的写入者在时间线上交错，读到重叠的论文；（b）同一段写入历史落进两种库，一种无约束，一种有约束；（c）项目工作从共享库 fork、推回。四个 challenge 都要能指到图上的具体元素。这个场景同时是评测 T1 的设定，评测中完整重演。

```text
              time ───────────────────────────────────────────────────────▶

 Band 1   W1 项目 X   读 A,B · 抽取 · 比较表 ─┐
 写入者    W2 项目 Y          读 B,C · 对 B 的 ETTh1@720 结果给出另一读法 ─┐
          W3                         读 D（D 修订了 B 的结论）· 提交修订 ─┐
          R  陌生读者                                    问：哪个方法在 … 最好？
                              │                    │                  │
                              ▼                    ▼                  ▼
 Band 2   (a) 无约束共享库                     (b) 带身份/契约/来源/版本的共享库
 共享库    [PatchTST] [PatchTST'] 重复           [PatchTST] ← W1、W2 收敛到同一身份
          B 的结果：值 y 覆盖值 x               值 x / 值 y 并存，各带来源，冲突可见
          比较表 → B 的旧结论，未标记           比较表 ⚠ 可能过时（输入已被修订）
          报告 → [记录已不存在]                 引用可解析，指向固定版本
          R 得到错误答案，且看不出来             R 得到答案，连同分歧与过时提示

 Band 3   项目 X:  fork@v3 ── x1 ── x2 ── push ──────────▶ 共享库 v5
 项目工作  项目 Y:      fork@v4 ── y1 ── push（与 x2 冲突，需处理）
```

```text
Caption:
    Figure 1: Uncoordinated writers accumulating paper-derived knowledge.
    Writers with separate projects read overlapping papers at different times
    (top). The same write history lands in an unconstrained store, which
    degrades, and in a store that enforces identity, contracts, provenance, and
    versions, which keeps disagreement and change visible (middle). Project
    work forks from the shared store and pushes results back (bottom).
```

Band 1（写入者）：三个写入者各自做自己的事，互不知道对方存在。W1 为项目 X 读 A、B，抽取并做比较表；W2 为项目 Y 读 B、C，对 B 的同一个结果给出不同读法；W3 后来读到 D，D 修订了 B 的结论，W3 提交了这次修订。最后一个陌生读者 R 用这个库回答问题。写侧行为包括读、抽取、比较、判断、修订、撤回、fork、推回；读侧强调读者不在写入现场。

Band 2（共享库）：同一段写入历史分别落进两种库。左栏无约束：重复节点、静默覆盖、未标记的过时、悬空引用，R 得到错误答案且看不出来。右栏有约束：身份收敛、两种读法并存并各带来源、依赖已修订输入的产物被标为可能过时、引用指向固定版本。图中数值只作示意。

Band 3（项目工作）：项目 X、Y 分别从共享库的某个状态 fork，在隔离的基线上工作，再把成果推回；Y 推回时与 X 已推回的内容冲突，需要处理而不是覆盖。

四个 challenge 在图中的落点：C1 对应 PatchTST 的重复与收敛；C2 对应比较表与报告所带的输入、条件和引用；C3 对应 B 的两种读法、W3 的修订与比较表的过时提示；C4 对应 Band 3 的 fork、推回与冲突。

## 从场景到问题与 Challenges

```text
How can a long-lived store accumulate paper-derived knowledge and artifacts
written by many agents that do not coordinate, so that later readers can
still find, trust, and build on it?
```

问题的几条边界，在 Problem 节显式写出：

- **不协调指语义上互不知情，不是并发事务。** 写入者不知道别人写过什么、怎么理解的；写操作本身可以轮流执行，原子性与隔离交给后端事务，不是本文的问题。
- **领域类型词表是给定的。** 我们假定写入者共享一套领域类型（Paper、Method、Dataset、Experiment 等）；词表的设计与演化属于 ontology engineering 与 schema induction，与本文正交。我们研究的是共享积累的完整性语义，领域词表是它的一个参数；本文为 CS 论文给出一个实例。
- **库不判断谁对。** 写入者之间有分歧时，语义判断由 Agent 做；中间件只让分歧可见、可追溯、可被后来者处理。
- **主张限于论文派生知识。** 机制设计与领域无关，但评测与结论只覆盖本领域；推广留给 Discussion。

四个困难，各自接回图中的元素：

1. **独立写入下的身份：** 不同写入者在不同时间写同一个方法、数据集或结果，要收敛到同一身份，同时不能把不同对象误并。身份规则必须显式、可检查、对所有写入者一致；粒度定在哪里（例如方法变体是否单独建节点）属于领域实例化。
2. **自描述的贡献：** 写入者之间没有共享上下文，库是唯一的通道。产物必须自带条件、证据和输入依赖，不在场的读者才能使用或复查。
3. **分歧与变化：** 写入者之间有分歧，会误读后修订，会撤回；源材料也会变。库要让相互竞争的判断带着来源并存，暴露冲突与过时，既不静默覆盖，也不整批拒绝。
4. **隔离地工作，共享地交付：** 项目工作需要一个不受他人写入干扰的稳定基线，成果要能推回共享库而不破坏它，并且能回到任一历史状态。

```text
C1. Converge identities across independent writers without wrong merges.
C2. Make contributions self-describing for readers who were not there.
C3. Keep disagreement and change visible, neither overwritten nor rejected.
C4. Isolate project work while delivering results back to the shared store.
```

## Claim + Contributions：总体方法

一个面向外部通用 Agent 的共享知识积累中间件：Agent 经 MCP 读写；中间件对身份、契约、来源与版本施加约束，使互不协调的写入在长期积累中不退化。

```text
We propose a middleware for shared accumulation of paper-derived knowledge
by uncoordinated agents. It enforces identity, contracts, provenance, and
versions on every write, so that the store keeps disagreement and change
visible instead of degrading as writers and writes grow.
```

设计立场：**薄图、厚文档。** 图里只放身份锚点和引用关系；丰富内容放在 Artifact 文档中，文档结构由 Agent 按契约声明。领域 schema 因此只需回答"这是什么对象"，不必回答"怎样描述它"；装不进图的内容仍可进文档，代价是失去结构化检索。

三项机制回应四个挑战；最后留评测的位置：

```text
1. Accumulation Meta-Model (C1, C2)
   Identity, provenance, and artifact semantics independent of the domain
   vocabulary: explicit and checkable identity rules, source-referenced
   records, and artifacts with declared inputs. A thin graph of identity
   anchors and references; rich content stays in artifact documents.

2. Operator Contracts for Agent-Composed Work (C2)
   Declared input/output contracts, validation, and persistent artifacts make
   each contribution self-describing, inspectable, and further composable.

3. Versioned Shared and Project States (C3, C4)
   Every change recorded as a commit; competing judgments coexist with their
   sources; dependency-based staleness indication; projects fork from a fixed
   state, work in isolation, and push results back.

4. Evaluation
   A falsifiable degradation claim under growing writers and writes against
   strong baselines (files + Git, RAG, the same schema without constraints),
   per-mechanism ablations, and amortized construction/use cost.
```

机制 3 中"相互竞争的判断并存"尚未设计：当前 `docs/designs/v2/commit_contract.md` §5 把内容分歧视为冲突并整批拒绝，没有修订与撤回语义。这是 T1 的前置项，见评测草案 §9。

责任边界是立论核心，在新命题下更自然：组合的规划在 Agent 侧，Agent 把意图翻译成算子计划，翻译是否忠实单独评估；中间件校验计划结构与引用、执行操作、持久化产物并记录谱系与状态变化。写入者之间有分歧时，库无权判断谁对，只负责让分歧可见、可追溯。我们管理 Agent 的写入，而不是替 Agent 判断。

随后以 Figure 2 介绍整体架构：多个 Agent 经 MCP 调用算子契约；每次写入经统一提交进入共享库；项目从共享库的固定状态 fork，在隔离的状态上工作并推回。回看 Figure 1 的写入历史如何沿这条链路落地。评测结果出来后，在 intro 末尾补主要发现。

# 后续章节大纲

组织方式借鉴 AgenticScholar：一套工作负载规约作为全文中枢，复用三处：related work 能力矩阵的行、机制设计的需求来源、评测小节的组织轴。中枢由三部分组成，与评测草案对齐：**写入者模型**（轮流写、两条写路径：直写共享库，或 fork → 项目工作 → 推回）、**事件类型**（误读后修订、撤回、材料变化、写入者分歧、分支与推回、回看历史状态）、**读侧阶梯 L0–L4**（存储语义、关联检索、组合、有状态工作、端到端）。挑战编号、机制编号、评测小节一一对应；Figure 1 的场景在评测中完整重演。Related work 前置到 intro 之后，直接叙述我们与各路线的区别。

2. **Related Work and Positioning.** 先用一段简述中枢规约，作为能力矩阵的行。随后按路线叙述区别：
   - 学术知识图谱与文献系统：以文档为中心；ORKG 虽是众包多写者，但写入者是人、靠模板整理，不管理 Agent 的使用产物与项目分支。
   - 多写者共享知识库：Wikidata 固定数据模型（item、statement、qualifier、reference、rank），领域属性由社区逐步提议；相互冲突的值可以带来源并存。这是我们"元模型与领域词表分层""分歧并存"的最近先例，要正面说明差别：写入者是 Agent、产物是派生文档、有项目 fork 与推回。
   - Agent Memory，含多 Agent 共享记忆：记录交互历史，不管跨写入者的身份、来源与版本。
   - 语义算子系统（AgenticScholar、LOTUS 等）：LLM 内化于算子；我们把语义工作外置、契约内化。
   - provenance 与版本化数据管理（`2026-Git4Data`、`2013-GraphSnapshot` 等）：管数据版本；我们管多写者积累的知识状态。
   - ontology engineering 与 schema induction：与本文正交，说明领域词表问题有人在做、不是我们的贡献。

   能力矩阵区分原生支持、组合支持、需外部推理。上述多写者知识库与多 Agent 记忆的文献是否已在 `references/` 中，待核实。
3. **Problem and Workloads.** 把中枢规约展开为可评测的形式：写入者模型、事件类型、读侧阶梯，各自给出具体输入、所需输出、数据状态与操作序列。显式写出三条假设：不协调是语义上的而非并发事务；领域词表给定；库不判断谁对。明确责任边界。
4. **System Overview.** Figure 2：共享库、产物、提交历史与项目状态的整体关系；用 Figure 1 中一段写入历史端到端走查各部件。
5. **Accumulation Meta-Model.** Entity / Concept / Content / Artifact 主类与系统记录；身份规则（精确键、标识、重复与歧义的处理）、材料引用、来源与派生谱系；薄图、厚文档的分工。CS 论文的领域词表作为实例单列（回应 C1、C2）。
6. **Operator Contracts and Artifact Persistence.** 访问算子与 Agent 算子的输入输出契约；中间件校验计划、保存产物与声明依赖，使贡献自描述、可复查、可继续组合（回应 C2）。
7. **Versions, Revision, and Project States.** 统一提交与完整变更记录；竞争判断并存、修订与撤回；基于依赖的过时提示；fork、推回与冲突处理；历史访问。区分产物输入谱系与提交祖先（回应 C3、C4）。
8. **Implementation.** 属性图与材料存储、算子契约到 Cypher 与后端的映射、统一写入与版本实现。
9. **Evaluation.**
   - **T1 主实验：** 写入者数 $K$ 与写入量增长下的库健康度（重复率、误合并率、悬空引用率、冲突检出率、过时识别及误报），由独立读者以固定探针查询测下游正确性；注入事件即 Figure 1 的重演。
   - **消融：** 逐项去掉身份、契约、来源、版本。
   - **T2 成本账：** 构建成本前移、按使用者摊销，盈亏点 $N^* = C_{\text{build}}/(c_{\text{base}}-c_{\text{ours}})$；baseline 给相同预计算预算。
   - **读侧阶梯：** L0–L4，L4 为按时间切分的实验设计任务。
   - **T3（可选）：** 结构化访问是否缩小弱模型与强模型的差距。
   - **Baseline：** A0 文件 + Git（最强配置）、A1 RAG、A2 同一 schema 的裸 Neo4j + Cypher、A3 完整系统。A2 与 A3 共用 schema，二者之差只来自机制；与 A0、A1 的比较混有 schema 的作用，需如实标出。
   - **schema 覆盖不足作为观测量：** 记录写入内容装不进类型的次数与去向（Artifact 文档、描述字段或丢弃），不作为要解决的问题。
   - 任务、语料与协议见评测草案，仍待商定；结果可能为负，例如 A0 始终不输。
10. **Lessons Learned.** 责任边界的划分、身份规则粒度的取舍、分歧并存的代价、版本记录的开销等实务经验。
11. **Conclusion.** 实验完成后收束主要发现、适用范围与局限。

# 备忘

通用接口暴露方式

General-purpose Agent → Agent-facing Access Interface → PaperWeave DBMS

Agent-facing Interface
├── MCP
│   ├── tools
│   ├── resources
│   └── structured results
│
└── Skills
    ├── capability descriptions
    ├── usage semantics
    └── workflow instructions
