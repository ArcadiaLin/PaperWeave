# 挑战与经典机制：设计能否回应 C1–C4，以及 Agent 写入者带来的改变

> **记录日期：** 2026-10-10。**状态：** 讨论记录，未定稿。
>
> 承接 2026-10-09 商定的核心命题（互不协调写入者的共享积累，见 `AGENTS.md`）与 2026-10-10 重写的 [叙事草稿](../../paper/narrative-draft.md) 中的 C1–C4。本文回答三个问题：现有设计能否回应这些挑战；设计是否落在传统多写者数据库的已有机制上；是否需要引证这些前身，并说明它们在 Agent 写入者场景下要改什么。
>
> 本文列出的文献凭记忆整理，出处与年份较有把握，但尚未核对是否已在 `references/refs.bib` 中，也未下载（见 §6）。

## 1. 结论

- **能否解决：** 只能部分解决。C3（分歧与变化）缺口最大，而它恰恰与多写者关系最密切。
- **是否落在已有机制上：** 是，几乎每项机制都有直接前身。
- **是否引证：** 必须引证。前身由我们主动认领，再说明 Agent 写入者场景要求哪些改变；否则论文会被看成实体解析、PROV 与数据版本管理的拼接。
- **贡献措辞随之收紧：** 不主张新的并发、provenance 或版本理论；主张的是找出 Agent 写入者的共享积累需要哪些经典机制、它们在哪里必须改（§3），并用实验证明它们起作用（T1 及消融）。

## 2. 逐项对照

| 挑战 | 经典前身 | 当前设计 | 状态 |
|---|---|---|---|
| **C1 独立写入下的身份** | 实体解析与记录链接（Fellegi–Sunter 1969）；人在环中或众包的实体解析（CrowdER，VLDB 2012）；自然键与唯一约束；dataspaces 的按需整合（Franklin、Halevy、Maier 2005）；Wikidata 的 QID 合并与重定向 | `NameKey` 精确键与命名空间标识（[图模型](../designs/v2/graph_model_v2.md) §2.4）；dry_run 给出语义候选，Agent `confirm` 同一与否；`ambiguous` 状态 | **能防不能修。** [Commit 契约](../designs/v2/commit_contract.md) §8：对象合并与拆分当前不做，事后发现的重复与误合并只能清库重建。查重在提交锁之外（只读了代码，未实测；见 [评测草案](../designs/v2/evaluation_draft.md) §9） |
| **C2 自描述的贡献** | provenance：why/where（Buneman、Khanna、Tan 2001）、provenance semirings（Green 等 2007）；W3C PROV 的 Entity / Activity / Agent；引用完整性；科学领域的 nanopublication（Groth 等 2010）与 micropublication（Clark 等 2014） | 契约校验引用与输入；`USED` 边；`Material` 带 `content_hash`；`formed_by`、`params`、`session`；幂等的 `artifact_key`（[算子契约](../designs/v2/operators.md)、Commit 契约 §7） | 设计基本完整；Agent 算子尚未实现。记录的是声明的输入，不是完整推理轨迹，也不证明判断为真 |
| **C3 分歧与变化** | 过时：物化视图失效与维护（Gupta & Mumick 1995）、真值维护系统 TMS / ATMS（Doyle 1979；de Kleer 1986）。并存：Trio / ULDB 的备选值与 lineage（Widom 2005；VLDB 2006）、CRDT 多值寄存器（Shapiro 等 2011）、Dynamo 的兄弟版本（2007）、Wikidata 的多值 statement、rank 与 reference。修订：双时态数据库 | 读取时按依赖计算 `_stale`（算子契约 §5.6）；`SUPPORTS` / `OPPOSES` 边 | **过时有设计；并存、修订、撤回都没有。** Commit 契约 §5：内容变化即冲突，整批拒绝 |
| **C4 隔离地工作，共享地交付** | 工程数据库的 check-out / check-in 与长事务（Katz 1990）；快照隔离（Berenson 等 1995）；乐观并发控制的提交前校验（Kung & Robinson 1981）；数据版本管理（DataHub 2015、Decibel 2016、OrpheusDB 2017；仓库已有 `2026-Git4Data`、`2013-GraphSnapshot`） | Fork 闭合检查；单父合并提交；逐项核对改前值，冲突交 Agent 决议；`merged_from`（[项目视图](../designs/v2/project_views.md) §5–§6；[版本化知识管理备忘](./2026-10-05-versioned-knowledge-management.md)） | 有设计，未实现 |

C1 与 C3 的缺口性质相同：库能在写入时拦截或提示，但写入之后无法纠正。C1 缺"合并与拆分"（经典做法是重定向与墓碑），C3 缺"修订与撤回"。

## 3. Agent 写入者要求的改变

经典机制默认写入者要么是程序（错误是语法性的，可校验），要么是人（慢、少、可信）。Agent 写入者都不符合。以下五点是贡献的落点：

1. **裁决在写入时交还写入者。** 经典实体解析要么全自动，要么事后众包。这里由库在写入时提出候选，写入者当场判断，判断和理由一起留档。约束不只是拒绝写入，而是返回修复义务（dry_run → 阻塞项 → `confirm`），对象是一个能理解并执行修复的写入者。
2. **错误是语义性的，而且读起来通顺。** 结构校验拦不住误读。因此 provenance 与分歧并存比保证正确更重要，这也是我们不走 truth discovery 路线的理由（见 §4）。
3. **派生内容重算昂贵且不确定。** 物化视图可以增量维护，因为重算确定、便宜；Agent 写的比较表与报告重算一次要再调 LLM，结果也不一定相同。所以只能标记可能过时，不能自动维护。这是与增量视图维护（IVM）的清晰分界。
4. **读者不会主动查 provenance。** 经典系统把 lineage 当作单独的查询；Agent 读者上下文有限，也不会想到去问。分歧与过时必须随查询结果一起返回（`_stale` 即如此）。
5. **接口就是契约。** 通用 Agent 只看得到 MCP 工具描述，机制能否起作用取决于 Agent 是否会用、是否绕开。经典 DBMS 没有这个问题，所以要用显示偏好或绕开率来测（评测草案 §8）。

## 4. 对 C3 设计的启发

C3 的前身方向明确：Trio 的备选值、CRDT 的多值寄存器、Wikidata 的 rank 都是"冲突值带来源并存，系统不裁决"，与"库不判断谁对"的立场一致。反面参照是 truth discovery（Li 等 2016 综述）：由系统按来源可信度自动裁决冲突。我们刻意不这样做，这一对比可以写进论文。

评测草案 §9 第 1 项（分歧处理设计）可以从这三个模型出发。需要讨论的问题包括：

- 并存的单位是什么：整个 Experiment / Claim，还是其中某个结果值；
- 修订是写入新版本并标记旧版本被取代，还是只追加一个对立的判断；
- 撤回是墓碑，还是一条带理由的状态变更；
- 读取时默认返回什么：全部候选、带 rank 的首选项，还是交由读者选择；
- 对 C1 合并与拆分的处理是否采用同一套机制（重定向即"身份层面的修订"）。

## 5. 对叙事与评测的影响

- **贡献措辞：** 叙事草稿的 Claim 与贡献 1–3 要改为"经典机制的选择与改造"，并在 Related Work 中主动列出前身。
- **Related Work 的组织：** 从按路线分（学术图谱、Agent Memory、语义算子、版本管理）改为按机制分：每个挑战一行，写"经典前身 → Agent 场景下的改变 → 我们的设计"。§2 的表可以作为底稿。
- **消融的含义：** 每项消融等于拿掉一个经典机制。T1 因此回答"在 Agent 写入者场景下，哪些经典机制仍然必要"。即使结果为负（例如只有身份查重有效），也是有价值的发现。

## 6. 待核对的文献

以下按挑战分组，均为候选，需核对出处并决定是否收入 `references/refs.bib`：

- **C1：** Fellegi & Sunter, A Theory for Record Linkage (JASA 1969)；Wang 等, CrowdER (VLDB 2012)；Franklin、Halevy、Maier, From Databases to Dataspaces (SIGMOD Record 2005)；Vrandečić & Krötzsch, Wikidata (CACM 2014)。
- **C2：** Buneman、Khanna、Tan, Why and Where (ICDT 2001)；Green、Karvounarakis、Tannen, Provenance Semirings (PODS 2007)；W3C PROV-DM (2013)；Groth、Gibson、Velterop, The Anatomy of a Nanopublication (2010)；Clark、Ciccarese、Goble, Micropublications (J. Biomed. Semantics 2014)。
- **C3：** Gupta & Mumick, Maintenance of Materialized Views (IEEE Data Eng. Bull. 1995)；Doyle, A Truth Maintenance System (AI 1979)；de Kleer, An Assumption-Based TMS (AI 1986)；Widom, Trio (CIDR 2005)；Benjelloun 等, ULDBs (VLDB 2006)；Shapiro 等, CRDTs (SSS 2011)；DeCandia 等, Dynamo (SOSP 2007)；Li 等, A Survey on Truth Discovery (SIGKDD Explorations 2016)；双时态数据库（Snodgrass 一系）。
- **C4：** Katz, Version Modeling in Engineering Databases (ACM Computing Surveys 1990)；Berenson 等, A Critique of ANSI SQL Isolation Levels (SIGMOD 1995)；Kung & Robinson, Optimistic Concurrency Control (TODS 1981)；Bhardwaj 等, DataHub (CIDR 2015)；Maddox 等, Decibel (VLDB 2016)；Huang 等, OrpheusDB (VLDB 2017)；已有 `2026-Git4Data`、`2013-GraphSnapshot`。

## 7. 待定

1. 是否按 §5 修改叙事草稿的贡献措辞与 Related Work 组织；
2. C3 的分歧、修订、撤回设计（§4 的问题），同时是 T1 的前置项；
3. C1 的合并与拆分是否纳入范围，与模型冻结（不新增实体与字段）如何协调；
4. §6 文献的核对、下载与入 `refs.bib`。
