# 论文草稿

中文记叙事意图；英文代码块留候选短句和用语。两者都用于推进草稿，随设计继续调整。

# Abstract

暂时留空。

# Introduction

## Why：为什么需要管理这些积累

先讲两点背景：

1. 通用 Agent 参与研究：读论文、理解方法、比较实验、辅助研究决策。
2. 阅读和使用产生的理解、抽取记录、判断与报告值得复用；后续 session 应能接着已有工作推进，减少重复阅读与整理。

```text
Background: Agents help researchers read, compare, and synthesize papers.
Motivation: Later sessions should build on earlier interpretations and artifacts.
```

再用 Figure 1 展开两个问题：

3. 知识有结构：跨论文的共同对象、不同实验条件、分散在正文与表图中的依据，以及产物间的依赖。
4. 积累需要组织：不同项目只需要其中一部分，还会补充材料、调整判断、探索不同路线，需要明确知识范围与历史状态。

## Figure 1：从研究行为看管理需求

暂用“比较方法 → 设计评测 → 探索不同路线”串联，具名论文后补。

- **Session 1：** 读 A、B、C，理解方法、抽取结果、比较条件，留下记录与判断。
- **Session 2 / 项目建立：** 研究者带着新需求回来，选 B、C 的相关经验，重新检查适用性，补读材料，形成评测方案。
- **后续 sessions：** 尝试两条研究路线，加入新发现、修订比较，需要回看早期报告用了哪些知识。

```text
Figure 1: Knowledge Reuse across Research Sessions and Projects

Read papers, compare results, and preserve earlier analyses.
Select relevant findings and adapt them to a project's experimental plan.
Explore alternatives, incorporate new evidence, and revisit earlier decisions.
```

图里画清两组联系：

- 内容：方法／实验 → 抽取记录 → 比较判断 → 报告；带出条件和证据。
- 项目：共享积累 → 选入 B、C → 新提交 → 独立路线；对应哪些产物进入哪个状态。

B、C 的已有产物可能涉及 A，用这一处说明“选择相关知识”还需要处理上下文。摘要、外部引用和历史保留的具体方案放到方法部分。

## 从案例到问题与 Challenges

过渡：已有理解怎样被找到、组合，成为项目的工作基础，并随着研究继续演化？

```text
How can paper-derived knowledge and artifacts be managed, reused,
and developed across research sessions and projects?
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

一句话定位：面向外部研究 Agent，管理论文知识、使用产物和版本化项目视图。

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
