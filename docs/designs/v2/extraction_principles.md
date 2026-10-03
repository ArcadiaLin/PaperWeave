# 论文抽取原则

> **状态：** 草案（2026-10-03）。规定外部 Agent 读一篇论文时抽什么、抽到多深、怎样写进入库表单；表单如何编译成增量、由 `Commit` 检查与写入，见 [Commit 契约](./commit_contract.md)。第 1–8 节已与用户确认（2026-10-03），第 9 节为待定事项。依据是 DLinear Table 4 与 PatchTST Table 3 的表单试写；首版入库为**报告级**（第 4 节），行级做法试写过并保留在 Git 历史（`f95631b`）。第一个 I3 实例入库后再修订。

抽取由外部 Agent 完成，中间件只做确定性的编译与检查（[研究顶层设计](./research_design_v2.md)、[Workload 拆解](./intents_decompose.md) §5 写路径）。本文回答 Agent 一侧的问题：一篇论文读完，哪些内容以什么粒度进入图。

## 1. 单篇深度：只抽到论文自身（已定，2026-10-03）

一篇论文的抽取只做到**它自身陈述的深度**。别的方法、别的论文的内容，要读它们自己的原文才能得到准确信息，不在本篇的抽取里代为完成。

| 内容 | 本篇抽取做什么 | 不做什么 |
| --- | --- | --- |
| 本文提出的方法 | 建**一个**核心方法节点，写定义 | 不为变体、消融配置另建节点 |
| 被对比的方法（基线） | 建**桩节点**：名称与引用线索 | 不写定义，不建它与其他方法的关系 |
| 本文怎样使用基线 | 照常抽：参与角色、变体标签、重跑或转引；回看窗口等条件写进实验的 `setting` | — |
| 方法之间的语义关系（属于哪一类、由什么机制组成、继承谁） | 默认不抽 | 只有论文明确陈述且某个 intent 需要时才写，见第 7 节 |

划分依据是**信息出自谁的陈述**。"FEDformer 在本文表中取 $L=96$、数字由作者转引"是本文的陈述，属于本文的实验；"FEDformer 是什么方法"要读 FEDformer 原文，属于将来 FEDformer 论文的抽取。

## 2. 核心方法与变体（已定，2026-10-03）

- 每篇论文只抽它的核心方法作为 `Concept.Method`。DLinear 一文只有 `DLinear`，PatchTST 一文只有 `PatchTST`。
- 变体与配置（DLinear-S / DLinear-I、PatchTST/64 / PatchTST/42、FEDformer-f / FEDformer-w、有无实例归一化）**在实验中说明**：
  - 实验级 `EVALUATES` 边上记原文印的变体标签列表 `variants`，例如 DLinear 的 `[DLinear-S, DLinear-I]`；
  - 标签的含义写进 Experiment 的 `setting`，作为图例，例如 "DLinear-S shares one linear layer across all variates (default); DLinear-I uses an individual layer per variate"，让读者不必回原文就能看懂标签；
  - 原文只写母方法名、没有注明变体时（PatchTST 表中的 "DLinear"），`variants` 留空，"未注明"保持显式，不按数值去猜。
- 名称级的独立方法（后续工作单独引用、另有演进，如 FlashAttention-2）不按变体处理，单独建节点，按 [Graph Model V2](./graph_model_v2.md) §2.3 的名称级差异处理。

**依据。** 变体节点让读者看到 "DLinear-I" 仍要回原文核实，节点本身不省阅读；而且必须靠 `BROADER` 才能把变体接回母方法，`Experiments` 的被测对象又是严格匹配，没有声明下位扩展。`BROADER` 因此不承担变体（[Graph Model V2](./graph_model_v2.md) §3.1）。

## 3. 被对比方法：桩节点（已定，2026-10-03）

实验的参与边需要可引用的被测对象，跨论文的同一基线也必须落在同一节点上，才能找到所有报告过它的实验（例如 PatchTST 重跑的 FEDformer 与 DLinear 表中的 FEDformer-f）。所以被对比的方法建节点，但只建桩：

| 字段 | 桩节点写什么 |
| --- | --- |
| `name` | 原文使用的名称；只注册原文确实用过的称呼 |
| `definition` | 留空。桩节点写定义视为错误 |
| `note` | 引用线索，例如 `Cited as [29] Zhou et al., FEDformer: Frequency enhanced decomposed transformer …` |
| 标记 | `stub`，表示"尚未读原文"，而不是"没有可说的" |

- 后续论文用到同一基线时，在 alias 级命中这个节点，不重复创建。
- 这篇基线论文本身入库时，用 `fill` 补全同一节点：只填空字段并去掉 `stub`（[Commit 契约](./commit_contract.md) §3）。
- 引用线索不写进 `identifiers`：论文的 arXiv 号标识的是论文，不是方法。以后若要表达"方法由哪篇论文提出"，随 `INTRODUCES`（Graph Model V2 §7 第 14 项）一起定。

## 4. 实验：报告级（已定，2026-10-03）

首版只在结构里记录**实验在哪张表、比了谁、在哪些数据集与指标上、实验级条件**；具体数值留在原文。比较时由 `Experiments` 按被测对象与数据集找到实验，再由 Agent 按锚点读表、取数、判断可比性（[Workload 拆解](./intents_decompose.md) I3.4："缺失部分 $A_{\text{map}}$ 读取已有锚点"）。D1 规定的行级精度是上限，不是要求。

| 内容 | 去处 |
| --- | --- |
| 这张表测的是什么 | Experiment 的 `text` |
| 条件说明：回看窗口、预测长度、训练方式、变体图例 | Experiment 的 `setting`（文本） |
| 疑点 | Experiment 的 `note` |
| 表的位置 | 主锚点 `anchor`（如 `S5.T4`）与行范围 `lines`；`FROM` 的 locators |
| 比了哪些方法 | 实验级 `EVALUATES {role, variants, origin}` |
| 用了哪些数据集 | 实验级 `USES {role: evaluation_data}` |
| 用了哪些指标 | 实验级 `MEASURED_BY` |
| 任务 | `ON_TASK` |
| 规则可直接判定的实验级条件 | 领域配置声明的条件，首版只有切分约定，存为 `cond_split` |

- **为什么不录数值。** 数值本身照抄即可，真正需要判断的是每个数对应哪个方法、变体、数据集与条件。首版不在入库时做这件事，而把它留在查询时；查询时现场读表的成本与出错情况，正是"哪些知识值得结构化"（研究评估 2026-10-03 §2.1）要测的数据。行级入库作为日后对照的升级选项。
- **为什么回看窗口、预测长度不进结构。** 它们在同一张表内会变（DLinear 表 4 中 DLinear 取 $L=336$，FEDformer 取 $L=96$），实验级只能写成文本。
- **切分与切分约定。** 原文常常不写切分比例，而是声明沿用前人设置（DLinear 第 203 行 "following the experimental setting of previous work [27, 29, 28]"；PatchTST 第 128 行 "following the same experimental setup … as in the original papers"）。因此：
  - 领域配置声明**有名字的切分约定**，例如 `ltsf-autoformer`。规则只比较约定的名字，所以约定只登记名称与出处（如 Wu et al., 2021 的实验设置），内容留空，与桩节点同理：各数据集具体怎么切属于出处论文自身的抽取，等它入库或某次比较确实依赖具体比例时再补，补时按原始出处核对；
  - 抽取时如实记录三种情况之一：原文给出的具体切分（显式 Split 绑定以后再加）、原文声明沿用的约定（`split` 取 `convention:<name>`，`condition_basis` 写原文位置）、或什么都没说（`null`）；
  - "沿用前人设置"对应哪个约定，由 Agent 在抽取时一次性映射，此后的比较不再重复判断。映射可能出错：DLinear 声明沿用的是 [27, 29, 28] 三篇，三者切分若不一致，统一映射会把不同条件判成相同。因此映射须记录依据，出现争议时按需核对；
  - 规则：两边是同一个约定输出 T；任一方留空或约定不同输出 U。不静默套用默认切分。

## 5. 来源性质：作者怎样得到这些数字（已定，2026-10-03）

每个参与方法在实验级 `EVALUATES` 边上记录 `origin`：

| 取值 | 含义 | 依据 |
| --- | --- | --- |
| `own` | 本文运行的本文方法 | 约定：本文方法默认如此，原文未必明说 |
| `rerun` | 作者重跑的基线 | 须给出原文位置 `origin_basis`，如 PatchTST 附录 A.1.2 |
| `cited` | 转引自其他论文 | 须给出原文位置与出处 `origin_from`，如 DLinear 表 2 脚注 "Other results are from FEDformer" |
| `unstated` | 原文未说明 | 试写中它是最常见的取值，必须作为一等取值 |

- `origin` 只记录论文的陈述，避免同一组数字被当成两份独立证据。数值相同不能推出转引：行级试写中发现的 5 条跨论文同值线索里，2 条是三位小数的巧合。
- Agent 根据数值认定 "PatchTST 表中的 DLinear 即 DLinear-S、转引自 DLinear 原文"，是带依据的判断，归 Q1（Agent 判断的持久化）；在 Q1 定下来之前，先写进 note。

## 6. 照抄原文，疑点另记（已定，2026-10-03）

- 名称与变体标签按原文印的写。Agent 的规范化（如把 "Eletricity" 对应到 Electricity）通过引用绑定表达：`{id, printed: Eletricity}`；笔误不注册为 alias，确实是新叫法才 `register`。
- 原文自相矛盾或不合理时如实记录，在实验上写 note 说明疑点。实例：DLinear 表 4 中 ILI 的预测长度印作 96–720，但 $L=336$ 加 $T=720$ 已超过 ILI 整条序列；表 4 中 FEDformer-f 与 Autoformer 在 ILI 上的数值又与表 2 中预测长度 24–60 的数值完全相同，所以标签很可能印错、这几行基线数值很可能取自表 2。
- 编译时核对称呼：表单里的方法名或变体标签、数据集与指标的称呼，必须出现在原文这张表的行范围内，否则列为待确认。

## 7. 引用已有对象与外部否定（已定，2026-10-03）

| 写法 | 用途 | 编译行为 |
| --- | --- | --- |
| `{mention, kind}` | 引用已有对象 | 只走 id 与 alias 两级，唯一命中才通过；否则在 dry_run 中列为待确认，apply 拒绝整批 |
| `{id, printed?, register?}` | 已确认指向的引用 | `printed` 是原文印的称呼；`register: true` 时注册为新 alias |
| `new` + `rejected: [id…]` | 新建对象 | `Resolve(write)` 返回的语义近邻，必须由 Agent 逐个列入 `rejected`（判断为不是同一对象） |
| 表单内 `ref` | 本批对象互相引用 | — |

- `rejected` 只记录同一性的否定，**不顺带写方法间关系**（第 1 节）。查重时看到的近邻（如 PatchTST 的近邻 Patching、Channel independence）可能确有关系，但不在单篇抽取中包办；`rejected` 留下的"当时看过哪些候选"，留作以后 I1 / I4 实例判断要不要补关系的材料。
- 桩节点的查重只走 id、alias 与名称词面通道，不跑向量通道。桩节点只有名称，向量召回的几乎全是通用概念；名称词面的模糊匹配仍能抓到拼写变体（如参考文献中的 "Fedformer"）。
- 引用的对象应由先前批次建立而那一批尚未提交时，先提交那一批，不要从语义候选中挑选。
- 外部否定的次数是主张 A 构建成本的测量项。语义阶段不设阈值，每个新对象的近邻数由 `TOP_N` 决定，不代表真实歧义；要统计的是 Agent 实际花在否定上的判断。

## 8. 范围声明（已定，2026-10-03）

- 报告级的抽取成本低，每篇论文**所有报告结果的表**都录成 Experiment，不只首个 I3 实例用到的三张。
- 每批写明录了哪些表（批次记录的 coverage）；没有录入不等于原文没有报告，不能把缺失读作否定。
- 首版不抽 Claim、Usage、Assessment；I3 不需要它们，Q1、Q5 因此不阻塞入库。

## 9. 待定

| # | 事项 | 倾向 | 关联 |
| --- | --- | --- | --- |
| 1 | 方法由哪篇论文提出的表达 | 先写进桩节点的 note | Graph Model V2 §7 第 14 项 `INTRODUCES` |
| 2 | 原表方向不同（DLinear 表 2 的行是方法、列是数据集与预测长度）时是否需要特别处理 | 报告级不受影响；只有日后做行级时才需要声明表的朝向 | — |
