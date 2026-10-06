# PaperWeave: A Data Management System for Paper-Derived Research Experience for AI Agents

# 论文草稿

中文记叙事意图；英文代码块留候选短句和用语。两者都用于推进草稿，随设计继续调整。

# Abstract

暂时留空。

# Introduction

## Why：

先讲两点背景：

1. 通用 Agent 参与研究：读论文、理解方法、比较实验、辅助研究决策。
2. 阅读和使用产生的理解、抽取记录、判断与报告，是 Agent 在研究过程中持续产出的产物，值得复用：纵向上，同一项研究持续推进，后续工作应能接着已有积累往前走；横向上，围绕不同想法或主题的研究线路应能各取所需，而不是重复阅读与整理。

```text
Background: General-purpose agents help researchers read, compare, and
synthesize papers, producing records and judgments along the way.
Motivation: Later work should build on these artifacts — continuing within
an ongoing effort and selectively reusing them across lines of inquiry.
```

再用 Figure 1 展开两个问题：

3. 知识有结构：跨论文的共同对象、不同实验条件、分散在正文与表图中的依据，以及产物间的依赖。
4. 积累需要组织：不同研究线路只需要其中一部分，还会补充材料、调整判断、探索不同路线，需要明确知识范围与历史状态。

## Figure 1：从研究行为看管理需求

放在 intro 部分的场景图，让读者看到（a）研究行为在时间线上展开，（b）产物沉淀成有结构的共享积累，（c）研究线路从中选择、分叉、带历史演化，并且四个 challenge 都能指到图上某个具体元素。图中论文 A、B、C（后期加入 D）是研究过程中使用的材料，由 Agent 阅读并转化为产物；Band 1 的每类行为都由我们的算子覆盖，因此这张图同时是系统能力的走查。

```text
                     time ──────────────────────────────────────────────▶                           
                                                                                                    
     Band 1   Session 1                Session 2                 后续 sessions                      
     研究行为  读 A,B,C ──比较──┐       带新需求回来              路线 α ──┐                        
              抽取/判断          │       选 B,C·复检·补读 D       路线 β ──┤ 修订比较               
                                 ▼            │                     │      │                        
     Band 2   ┌────────────────────────── 共享积累（持续生长）──────────┐                           
     共享知识  │  [A][B][C] 记录 ─ 比较判断 ─ 报告                      │                           
              │      ↑条件/证据边        └─ +D, 评测方案 ─ +新发现, v2  │                           
              └──────────────────────────────────────────────────────┘                              
                                 ▲            │ 选择                  │ revisit                     
                                 │            ▼                       │ (回指)                      
     Band 3                      │      ┌─ line of inquiry P ──────────┐                            
     项目视图                     └──────│ v1 ──── branch α ── v2       │                           
                         上下文          │      └─ branch β ── v3       │                           
                         (虚线连 A)      └──────────────────────────────┘   

Caption:
    Figure 1: Knowledge accumulation and reuse as research progresses over                         
    time and extends across lines of inquiry. Agents read papers and produce                       
    records and judgments (top); these accumulate into shared structured                           
    knowledge (middle); a line of inquiry selects part of it with required                         
    context and evolves through versioned states and branches (bottom).   
```

Band 1（研究行为）：时间轴上是若干研究 session。每个 session 中，研究者驱动、通用 Agent 围绕材料 
执行 read / extract / compare / select / revise 等行为：Session 1 读 A、B、C 并比较方法与实验    
；Session 2 带着新需求返回，选取已有积累、复检适用性、补读 D 并形成评测方案；后续 session 沿两条 
路线继续，加入新发现并修订早先的比较。每个行为都向下产生或更新产物。                             
                                                                                                
Band 2（共享积累）：随时间向右生长的共享知识集合。其中包含按来源论文组织的抽取记录、跨论文共享的 
研究对象节点、比较判断与报告等产物；记录带有实验条件与证据链接，产物之间有输入依赖关系。随       
session 推进，集合中陆续出现 D 的记录、评测方案、以及比较判断的修订版本。                        
                                                                                                
Band 3（项目视图与历史）：一条研究线路（line of inquiry）的知识视图及其演化。视图从共享积累中选取
了 B、C 的相关产物，同时包含一个视图外但被这些产物依赖的 A 的内容，以 required context 的形式标出
。视图状态形成提交序列（v1、v2、…），中段分出两条路线分支各自前进；一个 revisit 关系从后期状态指 
回早期报告及该报告当时所用的知识，表示对历史状态的追溯。  

Band 1 的行为与算子一一对应：检索与定位已有积累（search／resolve／traverse）、阅读材料与证据（read_evidence）、抽取记录（extract）、跨论文比较（matrix_construct）、筛选子集（filter）、复检适用性（verify／check）、形成方案与报告（generate／summarize）；每次调用经统一写入（commit）把产物落入 Band 2，并把状态变化记入 Band 3 的提交序列。由此 Figure 1 同时说明系统如何支持这些行为，而不只是描述需求。

四个 challenge 在图中的落点：C1 对应共享积累中跨论文共享的对象节点；C2 对应记录上的条件、证据链接与产物依赖关系；C3 对应视图的选取关系与视图外的 required context；C4 对应提交序列、分支与 revisit 关系。

## 从案例到问题与 Challenges

过渡：已有理解怎样被找到、组合，成为研究线路的工作基础，并随着研究继续演化？

这个问题分纵向与横向两个维度。纵向是时间：同一项研究持续推进，后续工作要继承并复用此前的理解与产物；横向是范围：围绕不同想法或主题展开的研究线路，各自只需要相关的一部分积累，可以选取子集、连同必要上下文，构成自己的参照基础。

```text
How can the paper-derived knowledge and artifacts that agents produce during
research be managed and reused, accumulating over the course of ongoing work
and extending in scope across lines of inquiry?
```

四个困难，各自接回图中的研究行为：

1. **复用单位与身份：** 跨论文比较时，区分共同对象、具体实验／主张和任务产物。
2. **组合中的条件与依据：** 从抽取到比较、综合，保留条件、判断范围和输入依赖。
3. **项目选择与上下文：** 只继承相关知识，同时交代项目之外的必要依据。
4. **持续演化与历史：** 新材料、判断修订和不同路线，各自用了什么状态、产生了哪些变化。

```text
C1. Identify reusable units across papers.
C2. Preserve conditions and evidence through composition.
C3. Select project knowledge with its required context.
C4. Track changes and independent research states.
```

## Claim + Contributions：总体方法

面向外部通用 Agent，管理论文知识、使用产物和版本化项目视图。

```text
We propose a knowledge-graph-based middleware combining a semantic knowledge
and artifact model, operator contracts for agent-composed work, and versioned
project views.
```

三项机制回应四个挑战；最后留实现与评测的位置：

```text
1. Semantic Knowledge and Artifact Model (C1)
   Shared identities, source-specific records, and artifacts linked by provenance.

2. Operator Contracts for Agent-Composed Work (C2)
   Declared input/output contracts, validation, and persistent artifacts make
   agent-composed work inspectable, reusable, and further composable.

3. Versioned Project Knowledge Management (C3–C4)
   Selective inheritance from a fixed baseline, complete change records,
   independent branches, and historical access.

4. Implementation and Evaluation
   Correctness, knowledge quality, reuse, and total construction/use/maintenance costs.
```

责任边界是立论核心，值得单独说清：组合的规划在 Agent 侧——Agent 把意图翻译成算子计划，翻译是否忠实单独评估；中间件校验计划结构与引用、执行操作、持久化产物并记录谱系与状态变化。我们管理 Agent 的组合，而不是替 Agent 组合。

随后以 Figure 2 介绍整体架构：Agent 经 agent-facing 接口（MCP）调用算子契约，产物落入共享知识积累，统一提交驱动项目视图与版本历史——语义模型、算子契约与 Artifact、版本化视图三部分如何连接，并回看 Figure 1 的行为如何沿这条链路落地。评测结果出来后，在 intro 末尾补主要发现。

# 后续章节大纲

组织方式借鉴 AgenticScholar：一套工作负载分类作为全文中枢，复用三处——related work 能力矩阵的行、算子契约设计的需求来源、评测小节的组织轴；挑战编号、机制编号、评测小节一一对应；Figure 1 的场景在评测中被完整重演。Related work 前置到 intro 之后，直接叙述我们与各路线的区别，而不是文末罗列。

2. **Related Work and Positioning.** 开头先用一段简述四类工作负载——知识访问、组合与产物生成、项目视图建立与维护、历史访问与演化——作为能力矩阵的行（完整规约在 §3 展开）。随后按四条路线直接叙述区别：学术知识图谱与文献系统（以文档为中心，不管理使用产物）、Agent Memory（记录交互历史，不管知识结构与研究状态）、语义算子系统（AgenticScholar、LOTUS 等——LLM 内化于算子，我们的语义工作外置、契约内化）、provenance 与版本化数据管理（引用 `2026-Git4Data`、`2013-GraphSnapshot`——管数据版本，我们管知识状态版本）。能力矩阵区分原生支持／组合支持／需外部推理。
3. **Workloads and Problem.** 把 §2 引入的四类工作负载展开为可评测规约：各自给出具体输入、所需输出、数据状态与操作序列。明确责任边界：Agent 解释材料、判断语义、组合计划；中间件校验、执行、持久化。
4. **System Overview.** Figure 2：共享知识、产物、项目视图与版本记录的整体关系；用 Figure 1 中一个 session 的端到端走查串起各部件。
5. **Semantic Data Model.** Entity / Concept / Content / Artifact；身份与粒度规则、材料引用、来源与派生谱系；约束与校验规则（回应 C1）。
6. **Operator Contracts and Artifact Persistence.** 访问算子与 Agent 算子的输入输出契约；组合的规划在 Agent 侧，中间件校验计划、保存产物与声明依赖，使 Agent 的组合可校验、可复用、可继续组合（回应 C2）。
7. **Versioned Project Knowledge Views.** 基线与选择、必要上下文、完整提交、分支、历史访问及整合；区分产物输入谱系与提交祖先（回应 C3–C4）。
8. **Implementation.** 属性图与材料存储、算子契约到 Cypher／后端的映射、统一写入与版本实现。
9. **Evaluation.** 小节与机制一一对应：模型正确性与约束执行（§5）、契约执行与产物质量（§6）、视图构建与选择正确性（§7 前半）、历史访问与分支演化（§7 后半）；加端到端案例（完整重演 Figure 1 场景）、设计消融（去掉契约校验／版本记录的代价）、构建／复用／维护总成本；baseline 含裸 Neo4j+Cypher、RAG、Agent＋文件系统。任务与协议待定。
10. **Lessons Learned.** 责任边界的划分、契约粒度的取舍、版本记录的开销等实务经验。
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