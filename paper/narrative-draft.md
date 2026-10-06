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

放在 intro 部分的场景图，让读者看到（a）研究行为在时间线上展开，（b）产物沉淀成有结构的共享积累，（c）研究线路从中选择、分叉、带历史演化，并且四个 challenge 都能指到图上某个具体元素。图中论文 A、B、C（后期加入 D）是研究过程中使用的材料，由 Agent 阅读并转化为产物。

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
We propose a knowledge-graph-based middleware combining semantic knowledge
and artifacts, composable operations, and versioned project views.
```

三项机制回应四个挑战；最后留实现与评测的位置：

```text
1. Semantic Knowledge and Artifact Model (C1)
   Shared identities, source-specific records, and artifacts linked by provenance.

2. Composable Operations and Persistent Knowledge Use (C2)
   Access and analysis contracts with reusable outputs and declared dependencies.

3. Versioned Project Knowledge Management (C3–C4)
   Selective inheritance from a fixed baseline, complete change records,
   independent branches, and historical access.

4. Implementation and Evaluation
   Correctness, knowledge quality, reuse, and total construction/use/maintenance costs.
```

责任边界只交代一句：Agent 解释材料、判断语义；中间件校验结构与引用，执行操作、保存产物和状态变化。

Figure 2 画整体架构：语义模型、算子与 Artifact、项目视图与统一提交如何连接。评测结果出来后，在 intro 末尾补主要发现。

# 后续章节大纲

2. **Workloads and Problem.** 从选定研究任务导出访问、组合、项目建立与更新需求；明确输入输出和责任边界。
3. **System Overview.** Figure 2：共享知识、项目视图、操作、产物与版本记录的整体关系。
4. **Semantic Data Model.** Entity / Concept / Content / Artifact；身份、粒度、材料引用及来源谱系。
5. **Operators and Artifact Persistence.** 访问与 Agent 算子、输入输出契约、组合、产物保存与继续使用。
6. **Versioned Project Knowledge Views.** 基线与选择、上下文与摘要、完整提交、分支、历史访问及整合；区分产物输入与提交历史。
7. **Implementation.** 属性图与材料存储、操作到后端的映射、统一写入与版本实现。
8. **Evaluation.** 先检验中间件正确性，再看知识／产物质量与跨任务、跨项目使用；对照、规模和总成本。任务与协议待定。
9. **Related Work.** 学术知识管理、Agent Memory、provenance 与版本化数据管理；版本部分引用 `2026-Git4Data`、`2013-GraphSnapshot`。
10. **Conclusion.** 实验完成后收束主要发现、适用范围与局限。

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