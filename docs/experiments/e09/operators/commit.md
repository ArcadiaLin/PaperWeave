# Commit 工具设计：graph-doc

> **状态：** 草案（2026-10-05），讨论中。本文记录 Commit 新入口的设计：读写同形的 YAML 文档 graph-doc。现行契约 [commit_contract.md](../../../designs/v2/commit_contract.md) 与 [operators.md](../../../designs/v2/operators.md) 尚未同步；E09 现有的 paper-form、supplement-form 与种子以后向本格式对齐，不在本文讨论范围内。第 8 节是建立在同一写入机制上的版本管理规划，第 9 节列出尚待决定的问题。

## 1. 为什么重新设计

现行 Commit 只会新建：`create_object`、`register_name`、`add_*`、`link`，以及只填空字段的 `fill_stub`。由此带来两个缺口：

- **不能修改。** 修订、撤回、合并都只能清库重建（commit_contract §5、§8）。
- **有些对象没有写入路径。** Issue、Proposition 只能引用已有节点；Paper 之外的关系（`IMPLEMENTS`、`ADDRESSES`、方法之间的关系等）也写不进去。

模型中暂时没有写入路径的元素不删除；Commit 最终应能完成对模型的任何修改。

新设计借鉴 OpenAI Agents SDK 的 `apply_patch`（`references/repos/openai-agents-python/examples/tools/apply_patch.py`），取的是它的思路，不是它的操作：

- **读写同形。** Agent 在 Search 或 Traverse 后看到的视图是一份 YAML 文档，写入时交的也是同一种 YAML 文档。
- **交状态，不交指令。** 交上来的文档表示“这些节点应当是这个样子”，由中间件计算它与库中现状的差异，再执行。
- **不模拟文件系统。** 没有真实目录，也不按对象切分文件；一次查询的视图合成一份文档，修改时整份交回。
- **只有一种格式。** 新入库、在视图上修改、追加理解、删除、合并都写成 graph-doc，不再区分论文表单与增补表单。

## 2. graph-doc 格式

一份 graph-doc 就是图中的一个子图。

### 2.1 顶层

| 键 | 读 | 写 | 含义 |
| --- | --- | --- | --- |
| `graph-doc` | ✓ | ✓ | 格式版本 |
| `meta` | ✓ | 忽略 | 生成这份视图的查询、覆盖情况（返回数、是否截断、快照）、路径绑定与诊断信息 |
| `by` | — | 必填 | 写入者。Agent 形成的记录的 `formed_by` 取自这里 |
| `confirm` | — | 可选 | 写入时的确认，不入图：如判定新节点与查重候选不是同一对象（`distinct_from`），见 §8 |
| `nodes` | ✓ | ✓ | 节点，按引用作键；同一节点在一份文档中只出现一次 |

### 2.2 引用

| 写法 | 用于 | 说明 |
| --- | --- | --- |
| 已有 id，如 `method_0016` | 已有节点 | 写入时引用已有节点只能用 id。称呼要先经 Resolve 解析，Commit 不负责解析称呼 |
| `$` 开头，如 `$patchtst` | 新建节点 | 临时引用，文档内任何位置都可以引用它；apply 后返回 `$ → id` 的映射 |

id 由中间件生成。Agent 读得到 id，但不会编造 id：新节点一律写 `$` 引用，写入成功后从返回结果中拿到 id。

### 2.3 字段：三种拼写

字段的类别看拼写，不看位置：

| 拼写 | 类别 | 可写 | 例 |
| --- | --- | --- | --- |
| 小写 | 属性 | ✓，任何时候都可写可改 | `name`、`aliases`、`identifiers`、`definition`、`text`、`description`、`note`、`kind`、`stated_by`、`stub`、`material` |
| 全大写 | 出边，键就是关系类型，写在起点上（方向约定见 graph_model §6） | ✓ | `ABOUT`、`FROM`、`EVALUATES`、`SUPPORTS`、`CITES` |
| `_` 开头 | 自动生成、需要给读者看的信息 | 只读 | `_formed_by`、`_formed_at`、`_stale`、`_material`、Artifact 的全部字段 |

出边的值是列表，元素可以是引用，也可以是 `{to: 引用, <边属性>…}`。

纯机制用的自动生成字段不进入 graph-doc，读写时都看不到：版本哈希、`exp_key` / `content_key`、`artifact_key`、材料的内容哈希、向量。

`kind`、`stated_by` 等不限于新建时写入，之后也可以修改。

### 2.4 材料与来源引用

- **登记材料。** Paper 上写 `material: <路径>`，中间件登记 Material 并计算哈希。读到的视图中另有只读的 `_material: <material id>`。
- **写 `FROM` 边。** 写成 `{to: <paper 或 art 引用>, locators: [...]}`，由中间件补上 `material_ref`，读时显示为边上的 `_material`。
- **来源引用。** 格式为 `<material id>::<locator>`，locator 是 `<section>::<start>:<end>`。写入时也可以用 `<paper 或 art 的 id 或 $ 引用>::<locator>`，由中间件换成该节点当前的材料；这是因为新论文在入库前还没有材料 id。把读到的值原样抄回去也可以。

## 3. 写入语义：交上来的就是想要的状态

| 对象 | 出现 | `null` | 不写 |
| --- | --- | --- | --- |
| 属性 | 设为该值 | 清空 | 不动 |
| 某一关系键 | 该类型出边的完整集合：多出的边新建，缺少的边删除，边属性按写的值更新 | — | 不动 |
| 节点 | 按上两行处理；`$` 引用则新建 | 删除该节点及其全部入边与出边 | 不动（不写 ≠ 删除） |

- **集合与顺序。** `aliases`、`identifiers` 和出边列表都与顺序无关。增删 `aliases` 就是注册或撤销 NameKey。
- **读视图的完整性。** 读到的视图中，节点只要出现了某个关系键，就给出该类型的全部出边，所以原样交回不会丢边。
- **只读字段。** `_` 字段原样带回时忽略，改动则报错。
- **Artifact。** 只能由 Agent 算子写入；graph-doc 中出现的 Artifact 只供引用，修改它会报错。
- **入边。** 入边在起点上修改。Agent 先检索出子图，从而知道哪些节点指向目标节点，再修改这些节点的关系键。
- **合并。** 没有专门的操作：先把边改指到保留的节点，移过别名，再删除被并入的节点（例 W6）。
- **只交差异也可以。** 只交被修改的节点，甚至只交被修改的那一个关系键，结果与交回整份视图相同。“交一份完整的 YAML 文档”的意思是交一份 YAML 格式的子图；没改的部分带不带都可以。
- **并发。** 暂不检测，后写入的覆盖先写入的。这是已知限制；§8.6 用 `base` 加变更集中的改前值，计划解除这一限制。

## 4. 调用与返回

```text
graph-doc ──dry_run──▶ graph-plan ──(无阻塞项)──▶ apply ──▶ graph-result
    ▲                      │
    └─── Agent 按 blocking 改文档后重交 ───┘
```

| 调用 | 输入 | 职责 | 返回 |
| --- | --- | --- | --- |
| dry_run | graph-doc | 解析文档；检查格式、只读字段、端点规则与必需的边；解析引用；查重；计算与库中现状的差异 | graph-plan |
| apply | 同一份 graph-doc | 重新执行 dry_run；没有阻塞项时，在单事务中写入、写后复核、补算向量 | graph-result |

**graph-plan**

| 键 | 内容 |
| --- | --- |
| `status` | `ready`、`blocked` 或 `noop` |
| `changes` | `create`、`update`（按节点列出改动的字段与关系键）、`delete`、`edges` 的增删数 |
| `blocking` | 每项为 `{rule, at, msg, candidates, fix}`；有任何一项时 apply 拒绝整批 |
| `warnings` | 不阻塞的提示，如新建桩节点 |

**graph-result**

| 键 | 内容 |
| --- | --- |
| `status` | `committed` |
| `commit` | 本次写入产生的 Commit id（§8） |
| `ids` | `$` 引用到新 id 的映射 |
| `counts` | 节点的新建、修改、删除数，边的新建、删除数 |

## 5. 检查（初稿）

| 类别 | 规则 | 处理方 |
| --- | --- | --- |
| 格式 | 顶层键、未知字段、`by` 必填；新节点必须写 `kind` | Agent 改文档 |
| 只读 | 改了 `_` 字段；修改 Artifact | Agent 改文档 |
| 引用 | 引用既不在库中，也不是本文档的 `$` 引用 | Agent 改文档 |
| 端点 | 关系类型与起点、终点的 kind 不符（graph_model 的端点规则）；改 kind 后原有的边按新的 kind 复核 | Agent 改文档 |
| 必需边 | 例如 Observation 必须有 `ABOUT`、Content 必须有 `FROM` | Agent 改文档 |
| 材料 | locator 越界；来源引用指向的节点没有材料 | Agent 改文档 |
| 查重 | 新节点的标识、名称或语义近邻命中已有节点（含桩节点）且未判定 | Agent 判断：换成已有 id，或写 `confirm.distinct_from` |
| 删除 | 列出删除的影响面（入边、引用它的 Artifact） | 待定，见 §8 |

现行契约中的自然键冲突与“Content 不原地修改”两条不再适用：修改就是正常的写入。

## 6. 场景示例

以下各段是一组连贯的例子：R 是读到的视图，W1–W7 是各种写入，P、P′、A 是中间件的返回。

### R　Agent 读到的视图

`Traverse(claim_0004, [SUPPORTED_BY out, USES out])` 的结果，另加几个相邻节点。写入时可以从这里改起，只读字段原样带回即可。

```yaml
graph-doc: v0.1
meta:
  query: {op: Traverse, start: [claim_0004], path: [{rel: SUPPORTED_BY, dir: out}, {rel: USES, dir: out}]}
  coverage: {returned: 8, truncated: false, snapshot: commit_0007}
  bindings:
    - [claim_0004, SUPPORTED_BY, exp_0001, USES, dataset_0002]

nodes:
  paper_0001:
    kind: Paper
    name: Are Transformers Effective for Time Series Forecasting?
    aliases: []
    identifiers: ["arxiv:2205.13504"]
    year: 2023
    material: papers/2023-DLinear/paper.md
    _material: material_1ec346c934e6
    description: Questions whether Transformer-based models are effective for LTSF and introduces DLinear …
    CITES:
      - to: paper_0002
        description: 表 2 中 FEDformer、Autoformer、Informer 的结果引自该文
        source_refs: ["material_1ec346c934e6::5.1 Experimental Settings::172:172"]

  method_0016:
    kind: Method
    name: DLinear
    aliases: []
    definition: A linear forecasting model that decomposes the input into trend and remainder …
    BROADER: [method_0011]

  dataset_0002:
    kind: Dataset
    name: ETTh1
    aliases: []
    identifiers: ["url:https://github.com/zhouhaoyi/ETDataset"]
    description: Hourly electricity transformer temperature data …
    PART_OF: [dataset_0001]

  exp_0001:
    kind: Experiment
    anchors: [S5.T2, A3.T9]
    text: 在九个数据集上比较 DLinear、NLinear 与五个 Transformer 基线的多变量长程预测 …
    FROM:
      - {to: paper_0001, locators: ["5.2 Comparison of Multivariate Forecasting with Transformers::198:240"], _material: material_1ec346c934e6}
    EVALUATES:
      - {to: method_0016, role: target}
      - {to: method_0005, role: baseline}
    USES:
      - {to: dataset_0002, role: evaluation_data}
    ON_TASK: [task_0002]
    EVALUATED_ON: [bench_0001]

  claim_0004:
    kind: Claim
    text: 在九个基准上，DLinear 在大多数设置下优于现有 Transformer 方法
    FROM:
      - {to: paper_0001, locators: ["Abstract::10:14"], _material: material_1ec346c934e6}
    ABOUT: [method_0016, task_0002]
    SUPPORTED_BY: [exp_0001]

  obs_0002:
    kind: Observation
    _formed_by: claude
    _formed_at: 2026-10-04T15:30:00Z
    text: 两文在 ETTh1 上的 96 步结果可比，但 PatchTST 的回看窗口更长 …
    ABOUT: [exp_0001, exp_0014, art_0003]
    FROM:
      - {to: art_0003, locators: ["Check::12:20"], _material: material_7a02c4f9e1b3}

  art_0003:                                           # Artifact：全部只读
    _op: Check
    _title: DLinear 与 PatchTST 在 ETTh1 上的可比性
    _abs: 核对两文 ETTh1 结果在切分、回看窗口与预测长度上的可比性 …
    _formed_by: claude
    _formed_at: 2026-10-04T15:10:00Z
    _session: s-0412
    _document: artifacts/art_0003.md
    _stale: []
    _USED:
      - {to: exp_0001}
      - {to: exp_0014}
      - {to: paper_0001, locators: ["5.1 Experimental Settings::160:172"]}
      - {to: art_0002, role: dlinear-etth1-96}
```

### W1　新论文第一次入库

新建论文、本文方法、实验、主张和自述贡献。已有对象只用 id 引用（先经 Resolve 解析）；被引用但尚未入库的论文和基线方法建为桩节点。

```yaml
graph-doc: v0.1
by: claude

nodes:
  $paper:
    kind: Paper
    name: "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers"
    identifiers: ["arxiv:2211.14730"]
    year: 2023
    material: papers/2023-PatchTST/paper.md           # 登记 Material，哈希由中间件计算
    description: Proposes PatchTST, a channel-independent patch-based Transformer …
    CITES:
      - to: paper_0001
        description: 表 3 中 DLinear 的结果引自该文
        source_refs: ["$paper::4.1 Long-term Time Series Forecasting::210:212"]   # 新论文用临时引用定位

  $patchtst:
    kind: Method
    name: PatchTST
    aliases: [PatchTST/64, PatchTST/42]
    definition: A Transformer for multivariate forecasting that splits each channel into patches …
    BROADER: [method_0004]                            # Transformer-based time series forecasting
    HAS_PART: [method_0012, method_0013]              # Patching、Channel independence

  $timesnet:                                          # 桩节点：基线方法，原论文尚未入库
    kind: Method
    name: TimesNet
    stub: true

  $exp-t3:
    kind: Experiment
    anchors: [S4.T3, A1.T8]
    text: 在八个数据集上比较 PatchTST 与 DLinear 及 Transformer 基线的多变量长程预测 …
    FROM:
      - {to: $paper, locators: ["4.1 Long-term Time Series Forecasting::200:240"]}
    EVALUATES:
      - {to: $patchtst, role: target}
      - {to: method_0016, role: baseline}
      - {to: $timesnet, role: baseline}
    USES:
      - {to: dataset_0002, role: evaluation_data}
    ON_TASK: [task_0002]

  $claim-sota:
    kind: Claim
    text: PatchTST 在长程预测上显著优于此前的 Transformer 模型
    FROM:
      - {to: $paper, locators: ["Abstract::8:12"]}
    ABOUT: [$patchtst, task_0002]
    SUPPORTED_BY: [$exp-t3]

  $contrib-patch:
    kind: Contribution
    stated_by: paper
    text: 提出按子序列切块作为 Transformer 的输入单元
    FROM:
      - {to: $paper, locators: ["1 Introduction::60:66"]}
    ABOUT: [$patchtst, method_0012]
```

### P　W1 的 dry_run 返回

```yaml
graph-plan: v0.1
status: blocked                                       # ready | blocked | noop
changes:
  create: [$paper, $patchtst, $timesnet, $exp-t3, $claim-sota, $contrib-patch]
  update: {}
  delete: []
  edges: {create: 14, delete: 0}
blocking:
  - rule: paper-similar
    at: $paper
    msg: 库中有标识相同的 Paper 桩节点
    candidates: [{ref: paper_0003, name: "A Time Series is Worth 64 Words …", stub: true, channels: [identifier]}]
    fix: 是同一论文时把 $paper 换成 paper_0003（补全它）；不是则写 confirm.$paper.distinct_from
  - rule: dedup
    at: $patchtst
    msg: 语义近邻未判定
    candidates: [{ref: method_0004, name: Transformer-based time series forecasting, channels: [vector]}]
    fix: 是同一对象时换成该 id；不是则写 confirm.$patchtst.distinct_from
warnings:
  - {rule: stub-new, at: $timesnet, msg: 新建桩节点}
```

### W2　查重往返：按 P 修改后重交

- 判定是同一对象：把 `$` 引用全部换成已有 id，节点内容就变成对已有节点的修改（这里顺带补全桩节点）。
- 判定不是同一对象：在 `confirm` 中写 `distinct_from`。

```yaml
graph-doc: v0.1
by: claude
confirm:
  $patchtst: {distinct_from: [method_0004]}           # 候选 method_0004 是类别，不是 PatchTST 本身

nodes:
  paper_0003:                                         # 原来的 $paper：库中已有它的桩节点
    stub: null                                        # 清掉桩标记 = 补全
    kind: Paper
    name: "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers"
    identifiers: ["arxiv:2211.14730"]
    year: 2023
    material: papers/2023-PatchTST/paper.md
    description: Proposes PatchTST …
    CITES:
      - to: paper_0001
        description: 表 3 中 DLinear 的结果引自该文
        source_refs: ["paper_0003::4.1 Long-term Time Series Forecasting::210:212"]

  $patchtst:
    kind: Method
    name: PatchTST
    definition: …
    BROADER: [method_0004]

  # $exp-t3、$claim-sota、$contrib-patch 同 W1，其中的 $paper 全部换成 paper_0003（略）
```

### A　W2 的 apply 返回

```yaml
graph-result: v0.1
status: committed
commit: commit_0008
ids:
  $patchtst: method_0022
  $timesnet: method_0023
  $exp-t3: exp_0023
  $claim-sota: claim_0031
  $contrib-patch: contrib_0012
counts: {nodes_created: 5, nodes_updated: 1, nodes_deleted: 0, edges_created: 14, edges_deleted: 0}
```

### W3　在读到的视图上修改已有节点

这份文档从 R 改出来，只保留了改动过的节点。示例涉及：修改属性、清空属性、增删别名、增删边、修改边属性、修改 kind。

```yaml
graph-doc: v0.1
by: claude

nodes:
  method_0016:
    kind: Method
    name: DLinear
    aliases: [Decomposition-Linear]                   # 加别名：注册一条 NameKey
    definition: >                                     # 改属性
      A linear forecasting model that decomposes the input into a moving-average trend and a
      remainder, maps each with a one-layer linear layer along time, and sums the outputs.
    note: null                                        # 清空属性
    BROADER: [method_0011]

  exp_0001:
    kind: Experiment
    anchors: [S5.T2, A3.T9]
    text: 在九个数据集上比较 DLinear、NLinear 与五个 Transformer 基线的多变量长程预测 …
    FROM:
      - {to: paper_0001, locators: ["5.2 Comparison of Multivariate Forecasting with Transformers::198:240"], _material: material_1ec346c934e6}
    EVALUATES:
      - {to: method_0016, role: target}
      - {to: method_0005, role: baseline}
      - {to: method_0007, role: baseline}             # 加一条边
    USES:
      - {to: dataset_0002, role: evaluation_data}
    ON_TASK: [task_0002]
    # EVALUATED_ON 键整个不写：不动

  dataset_0009:
    kind: Benchmark                                   # 改 kind：Dataset → Benchmark；id 不变，原有边按新端点规则复核
    PART_OF: []                                       # 删掉全部 PART_OF 出边
```

### W4　依据读到的子图追加理解

示例包括：新建 Issue 并把已有 Claim 挂上去；Agent 判断的正反关系；Observation；Agent 认为的贡献。依据可以是论文原文，也可以是 Artifact 文档，后者相当于把工作产物提升为长期记录。

```yaml
graph-doc: v0.1
by: claude

nodes:
  $linear-vs-tf:
    kind: Issue
    text: 线性模型能否在长程预测上替代 Transformer
    description: 关键在回看窗口、归一化与通道处理是否一致

  claim_0004:
    ABOUT: [method_0016, task_0002, $linear-vs-tf]    # 给已有 Claim 加 ABOUT：只交这个关系键

  claim_0011:
    ABOUT: [method_0022, task_0002, $linear-vs-tf]
    SUPPORTS: []
    OPPOSES:
      - to: claim_0004
        stated_by: agent                              # Agent 判断的正反关系；_formed_by 取自 by
        description: 在回看窗口为 336 时 PatchTST 优于 DLinear，与 claim_0004 的结论相反

  $obs-comparable:
    kind: Observation
    text: 两文 ETTh1 的 96 步结果切分一致、回看窗口不同，直接比较需要说明窗口差异
    ABOUT: [exp_0001, exp_0014, art_0003]
    FROM:
      - {to: art_0003, locators: ["Check::12:20"]}    # 依据是 Artifact 文档的行
      - {to: paper_0001, locators: ["5.1 Experimental Settings::160:172"]}

  $contrib-agent:
    kind: Contribution
    stated_by: agent
    text: 这篇论文促使后续工作在比较时报告回看窗口
    FROM: [paper_0001]                                # Agent 贡献：连到所属论文，可不带定位
    ABOUT: [paper_0001]
```

### W5　删除节点

把节点写成 `null`，它的全部入边和出边一并删除。

```yaml
graph-doc: v0.1
by: claude

nodes:
  obs_0002: null
```

### P′　W5 的 dry_run 返回

```yaml
graph-plan: v0.1
status: blocked
changes:
  delete: [obs_0002]
  edges: {create: 0, delete: 4}
blocking:
  - rule: delete-impact
    at: obs_0002
    msg: 删除后以下引用将失效
    impact: {in_edges: [], used_by_artifacts: [], about_by: []}
    fix: 确认删除时写 confirm.obs_0002.delete_ok = true
```

### W6　合并（组合写法）

`method_0021` 与 `method_0016` 是同一方法，保留 `method_0016`。前提是先 Traverse，取得 `method_0021` 的全部入边、出边，以及指向它的节点。

```yaml
graph-doc: v0.1
by: claude

nodes:
  method_0016:
    aliases: [Decomposition-Linear, D-Linear]         # 把 method_0021 的名称挪过来
    BROADER: [method_0011]

  exp_0007:                                           # 原来 EVALUATES 指向 method_0021 的实验
    EVALUATES:
      - {to: method_0016, role: baseline}
      - {to: method_0002, role: target}

  claim_0019:                                         # 原来 ABOUT 指向 method_0021 的主张
    ABOUT: [method_0016]

  method_0021: null                                   # 最后删掉被并入的节点
```

### W7　会被拒绝的写法

```yaml
graph-doc: v0.1
by: claude

nodes:
  art_0003:
    _title: 改个标题                                   # 错误：Artifact 只由 Agent 算子写入
  obs_0002:
    _formed_by: someone-else                          # 错误：改了只读字段
  method_0016:
    EVALUATES: [method_0005]                          # 错误：Method 不能有 EVALUATES 出边（端点规则）
  $orphan:
    kind: Observation
    text: …                                           # 错误：Observation 必须有 ABOUT
  claim_0004:
    ABOUT: [method_9999]                              # 错误：引用不在库中，也不是本文档的 $ 引用
```

## 7. 与现行操作集的对应

| 现行操作（commit_contract §3） | graph-doc 中的写法 |
| --- | --- |
| `create_object` | 新的 `$` 节点；桩节点写 `stub: true` |
| `register_name` | 增加 `aliases` 的元素（删除元素即撤销） |
| `fill_stub` | 在已有桩节点上写属性并写 `stub: null`；不再限于只填空字段 |
| `add_material` | Paper 上的 `material` |
| `add_experiment`、`add_content` | 新的 Content `$` 节点及其关系键 |
| `link` | 关系键，任意关系类型都可写 |
| `record_batch` | 每次 apply 产生一个 Commit 记录，取代 IngestBatch（§8） |
| 修订、撤回、合并（原先不做） | 修改属性与关系键、写 `null` 删除、组合写法（W3、W5、W6） |
| Issue、Proposition（原先无写入路径） | 与其他 Concept 一样新建和修改（W4） |

## 8. 版本管理（规划）

> 本节是工程规划，尚未实现，也尚未评估。各项机制以 graph-doc 的写入语义为基础；分支的存储方式、视图选择与回流规则仍待讨论（§9）。

### 8.1 定位

我们不研究如何优化版本控制，而是让学术资源管理系统支持版本管理，并提供配套的机制。版本管理服务于两件事：

- **全局与项目两个范围的知识管理。** 全局库从 main 分出项目分支（fork）。项目在自己的分支上演进：建立项目视图、写入 Artifact、追加理解。项目分支可以吸收 main 的更新，也可以把经过检验的成果回流到 main。
- **让 Agent 的知识持久化过程可追溯。** 对某个 Method、Issue 或 Claim 的理解是如何一步步形成和修改的，由谁写入，当时依据哪些 Artifact、做过哪些查重判断，都可以按时间顺序查询。

要区分两条链：Artifact 的 `USED` 边是**输入来源**，记录一个产物用了哪些对象；Commit 的父链是**提交祖先**，记录知识状态由哪些写入演变而来。两条链各自独立。

### 8.2 Commit 记录

每次写入产生一个 Commit 记录，取代 IngestBatch。Commit 是系统记录（与 Material、NameKey 同层），只服务于数据管理机制，不进入 graph model 的学术层，graph_model 因此不需要修改。

**统一的写入底层。** 对图的修改都经过同一个底层 util：输入一份解析后的变更集，在单事务中执行这些修改并写入 Commit 记录。Commit 工具（graph-doc）和 Agent 算子（Artifact）是这个底层的两个上游：

```text
graph-doc ──dry_run / apply──┐
                             ├──▶ 变更集 ──▶ apply-changeset（单事务：改图 + 写 Commit）
Agent 算子 ──校验──▶ Artifact ─┘
```

不计空间成本，每个 Commit 保存三类内容：

| 内容 | 作用 |
| --- | --- |
| 交上来的输入原文：graph-doc，或 Agent 算子的调用参数 | 记录写入者想要什么；也用于评估 Agent 的行为，如来回轮数与查重判断 |
| 解析后的变更集：每个改动的属性和每条边，改前与改后的值；`$` 引用已换成 id | 真正的版本数据，支撑 log、diff、按时间点还原、撤销和追查改动来源 |
| 元数据：父 Commit、分支、写入者、时间、来源、`base`、`confirm`、轮数 | 提交祖先链与写入过程的记录 |

只存输入原文不够。graph-doc 的语义是“不写就不动”，`$` 引用和查重判断又依赖写入时的库状态，所以单凭输入原文无法还原历史状态，也无法撤销。

以 §6 的 W2/A 为例：

```yaml
commit: commit_0008
parents: [commit_0007]
branch: main
by: claude
at: 2026-10-05T10:12:00Z
source: {tool: Commit}                 # Agent 算子写入时为 {operator: Check, artifact: art_0004}
base: commit_0007                      # 写入者读视图时所在的 Commit
rounds: 2                              # dry_run 来回轮数
confirm:
  $patchtst: {distinct_from: [method_0004]}
ids: {$patchtst: method_0022, $timesnet: method_0023, $exp-t3: exp_0023, $claim-sota: claim_0031, $contrib-patch: contrib_0012}
input: |                               # 交上来的 graph-doc 原文
  graph-doc: v0.1
  by: claude
  …
changes:
  nodes:
    paper_0003:
      op: update
      props:
        stub: {before: true, after: null}
        year: {before: null, after: 2023}
        description: {before: null, after: Proposes PatchTST …}
    method_0022:
      op: create
      after: {kind: Method, name: PatchTST, definition: …}
    method_0023:
      op: create
      after: {kind: Method, name: TimesNet, stub: true}
    # …
  edges:
    - {op: create, type: CITES, from: paper_0003, to: paper_0001,
       after: {description: 表 3 中 DLinear 的结果引自该文, source_refs: ["material_9c41d2a07b18::4.1 …::210:212"]}}
    - {op: create, type: BROADER, from: method_0022, to: method_0004}
    # …
  names:
    - {op: register, key: patchtst, node: method_0022}
  materials:
    - {op: create, id: material_9c41d2a07b18, path: papers/2023-PatchTST/paper.md, hash: 9c41d2a07b18…, of: paper_0003}
counts: {nodes_created: 5, nodes_updated: 1, nodes_deleted: 0, edges_created: 14, edges_deleted: 0}
```

变更集的约定：

- **删除。** `op: delete` 记录被删节点的全部属性（`before`），连同的边逐条记为 `op: delete`，带边属性的 `before`，所以每个 Commit 都可以逆向执行。
- **边的标识。** 一条边由起点、类型和终点确定。修改边属性记为 `op: update`。
- **派生字段。** 自然键、向量这类可以由数据算出的字段不进入变更集，重放时重新计算。

### 8.3 Commit 在图中的表示

- **节点与父链。** Commit 是一个节点，带 `PARENT` 边指向父 Commit。线性历史只有一个父 Commit；回流合并（§8.6）时有两个。
- **指向被写入的节点。** Commit 用 `TOUCHED {op}` 边连到本次新建或修改、并且仍然存在的节点。这些边只是索引，用来快速回答“这个节点被哪些 Commit 改过”。被删的节点和边的修改只记在变更集里；以变更集为准。
- **与学术层隔离。** Search、Traverse 默认排除 Commit 节点和 `TOUCHED` 边，以免它们混进学术层的遍历结果。版本信息由 §8.4 的算子查询。
- **大字段的存放。** 输入原文和变更集可以直接存成节点属性；也可以像 Artifact 文档那样存为文件，节点上只记路径与哈希。实现时再定。

### 8.4 历史查询

这些是机制层的算子，与学术层算子分开列出。下表只是规划，契约待写。

| 算子 | 作用 |
| --- | --- |
| `Log` | 按时间顺序列出 Commit；可以按分支、写入者、来源（Commit 工具或某个 Agent 算子）、时间范围过滤，也可以只列触及某个节点的 Commit |
| `Show` | 一个 Commit 的完整记录 |
| `Diff` | 两个 Commit 之间，或一个分支相对它的分叉点，节点与边的差异，用 graph-doc 的形状给出 |
| `AsOf` | 某个 Commit 时一个节点或一个子图的状态：从当前状态出发，逆向执行之后的变更集 |
| `Blame` | 一个节点上每个属性和每个关系键最后由哪个 Commit 写入 |
| `Revert` | 把一个 Commit 的逆向变更集作为一个新 Commit 写入，不改写历史 |

### 8.5 Artifact 的特殊处理

Artifact 写入同样产生 Commit（`source: {operator: …, artifact: …}`），走同一个写入底层。区别在于它的文档存放在文件系统中，不在图里：

- **文件按内容寻址，写入后不再改动。** 文件名带上内容哈希，Commit 记录文档的路径与哈希。Artifact 只读，所以文件的版本只有一个。
- **只写不删。** 分支操作和 Revert 只改变 Artifact 节点在某个分支上是否存在，不删除文件。即使 Artifact 节点被删除，文件仍然保留，否则 `AsOf` 和重放会失效。
- **随 Commit 走。** 文档文件可以放在 git 之外，例如 `data/artifacts/`，但 Commit 链才是它的版本记录。重放时要求文件存在，并且哈希一致。
- **论文材料同理。** Paper 的材料也按路径加哈希记入变更集（`changes.materials`）。

### 8.6 分支：全局与项目

| 操作 | 含义 |
| --- | --- |
| `main` | 全局库 |
| `Fork(base, name)` | 从 main 的某个 Commit 分出项目分支。这个 Commit 就是项目的基线（AGENTS.md 所说的 defined baseline） |
| `Branch(base, name)` | 在项目内（或 main 上）分出试探线，例如对同一个 Issue 的两种整理方式 |
| `Sync(project)` | 把 main 在分叉点之后的 Commit 带进项目分支 |
| `Promote(project, commits)` | 把项目分支上选定的 Commit 回流到 main，形成一个有两个父 Commit 的合并 Commit |

**冲突检测。** 变更集记录了 `before`，所以把一个变更集应用到另一条分支时，只需逐项核对 `before` 是否等于目标分支的当前值：

- 全部一致：直接应用。
- 不一致：说明两边改了同一个属性或同一个关系键，记为冲突。同一节点上一边删除、一边修改，也是冲突。
- 冲突交给 Agent 处理：读两边的值，交一份 graph-doc 作为决议，这和平时的写入是同一流程。

同一机制也可以用于 main 上的并发检测：写入时如果带上 `base`，就能发现读到的视图已经过期（§3 中“不检测并发”的限制因此可以解除）。

**回流时还要处理：**

- **id 不冲突。** id 由全局计数器分配，与分支无关，因此回流时不会撞号。
- **重复对象。** 项目分支和 main 可能各自建了同一个对象，比如两边都入库了同一篇论文。所以回流前要按 dry_run 的规则重新查重，判定结果与 `confirm` 一并记入合并 Commit。

**项目视图与分支的关系。** 项目视图是从项目分支上按选择规则取出的一部分（选择算法待定）。分支提供独立演进与隔离，视图决定项目里用到哪些知识。

**物化方式（待定）。** 论文规模下最简单的做法是每条分支各存一份完整的图（复制），所有分支共用同一条 Commit 链。其他候选：

- main 物化存储，项目分支只存叠加的变更集，读取时合成；
- 节点和边带分支、有效区间等属性。

Neo4j 社区版只支持一个用户数据库，所以按分支复制需要多个实例，或在同一个库内用命名空间区分。

### 8.7 不变式

这几条既是实现时必须通过的检查，也是版本管理正确性的实验证据：

1. **重放一致。** 从空库按顺序重放某条分支上的全部 Commit，得到的状态与该分支的当前状态相同（派生字段重新计算）。
2. **可逆。** 对每个 Commit，从写入后的状态逆向执行它的变更集，得到写入前的状态。
3. **原子。** 图的修改与 Commit 记录在同一个事务里，不存在没有 Commit 的修改。
4. **文件完整。** Commit 引用的每个文件（材料、Artifact 文档）都存在，并且哈希一致。

## 9. 待定问题

1. **`confirm` 段。** 查重的否定判断（`distinct_from`）不属于学术层的图数据，但写入时必须给出，所以单独放在一段，并原样记入 Commit 记录（§8.2）。键名待定。
2. **删除是否需要二次确认。** P′ 中暂用 `confirm.<id>.delete_ok`。另一种做法是直接删除，只在 graph-plan 中列出影响面。
3. **来源引用读写不对称。** 读到的是 `<material id>::<locator>`，写入时也可以用 `<node 引用>::<locator>`（§2.4）。
4. **Commit 只接受 id 和 `$` 引用。** 现行表单中的 `{mention, kind}` 引用取消，入库时 Resolve 调用会增多。
5. **提交者与轮数。** 现行 `x-ingest` 的内容改记在 Commit 记录中（§8.2）：`by` 兼作提交者，dry_run 的来回轮数由中间件自己计数。需要确认中间件如何判定几次 dry_run 属于同一次提交。
6. **改 kind 时 id 不变。** id 带有类型前缀（如 `dataset_0009` 改成 Benchmark 后前缀不再相符），需要决定是否接受。
7. **`meta.bindings` 的格式。** 路径绑定目前写成交替排列的节点与关系的列表。
8. **用 `stub: null` 表示补全桩节点。** 待确认这一写法。
9. **分支的物化方式。** 见 §8.6。
10. **fork 与 branch 是否需要区分。** 两者的机制相同，区别在于用途。
11. **project 回流到 main 的粒度。** 可以按 Commit 挑选，也可以按节点或子图挑选。按子图挑选会切断 Commit 的完整性，需要重新生成变更集。
12. **graph-doc 能否删除 Artifact 节点。** 删除时文档文件保留（§8.5）。
13. **写入是否必须带 `base`。** 不带 `base` 时，冲突检测只能比较 `before` 与当前值，无法区分“被别人改过”与“读的视图已过期”。
