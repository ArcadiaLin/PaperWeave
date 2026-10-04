# Commit 契约：论文增量的入库

> **状态：** 已定（2026-10-03）；同日第一个 I3 实例试跑后修订为 paper-form-v3：实验按研究问题分组，只存描述、锚点与参与关系（[抽取原则](./extraction_principles.md) §4、§5）。E09 的 compile（`form.py`）、dry_run 与 apply（`operators/commit/paper.py`）实现的是上一版 paper-form-v2（每张结果表一个实验，带变体、条件、疑点与逐项来源性质），DLinear 与 PatchTST 曾按 v2 入库（提交 `781832d`：22 个实验、5 条 `CITES`），**待对齐到 v3 后重新入库**；论文增量中的关系只实现了 `CITES`。行级（ResultUnit）版本见提交 `f95631b`。规定外部 Agent 写好的入库表单如何编译成增量、由 `Commit` 检查并写入；抽什么、抽到多深见 [抽取原则](./extraction_principles.md)。对应 [Graph Model V2](./graph_model_v2.md) §7 第 15 项与 [Workload 拆解](./intents_decompose.md) §5 写路径。种子入库是其中的特例，E09 已实现（`experiments/e09/src/e09/operators/commit.py`）。

## 1. 流程与职责

```text
表单 ──compile──▶ delta ──dry_run──▶ plan ──apply──▶ 写入（单事务）──▶ 复核 ──▶ 补算向量
         │                │                 │
   不查库：只读        只读查库：         plan 有错误、冲突或
   表单与材料          库内与批内         待确认项时拒绝整批
```

| 阶段 | 输入 | 职责 | 查库 |
| --- | --- | --- | --- |
| compile | 表单、材料文件、领域配置 | 结构、语法、锚点等只看表单与材料就能判定的检查；展开结果表 | 否 |
| dry_run | delta | 解析引用、查重、冲突与幂等判定，返回 plan | 只读 |
| apply | 无阻塞项的 plan | 单事务写入；写完重跑 plan，必须为空 | 写 |
| 补算向量 | 本批新建或补全的对象 | 由 apply 触发；否则下一批的语义查重看不到这些对象 | 写 |

- **批**：一篇论文的一份表单为一批，整批原子。
- **循环**：Agent 按 plan 修改表单，再次 dry_run，直到没有阻塞项。来回轮数记入批次记录，是主张 A 的构建成本。
- **跨批依赖**：靠提交顺序保证。引用的对象所在的批次尚未提交时，dry_run 报"引用无法解析"。
- **边界**：中间件只做确定性检查与执行；同一性、称呼指向、冲突怎么处理由 Agent 判断（[研究顶层设计](./research_design_v2.md)）。

## 2. 表单（paper-form-v3）

| 字段 | 内容 |
| --- | --- |
| `form` | 表单版本 `paper-form-v3`。v2 的 `domain`（领域配置：实验级条件与切分约定）随条件退出结构而去掉 |
| `material` | 材料路径与内容哈希 |
| `paper` | 论文本身：`labels`、`properties`（name、identifiers、description） |
| `refs` | 已有对象：`{mention, kind}`；或经确认的 `{id, printed?, register?}`，`register: true` 表示把 `printed` 注册为该对象的新 alias（笔误不注册） |
| `objects` | 新对象：核心方法与桩节点（`stub: true`），带 `rejected`；被引论文只能是桩节点；补全桩节点用 `fill: {id 或 mention}` |
| `relationships` | 论文表单只允许本文 → 被引论文的 `CITES`：`{from: paper, type: CITES, to: <Paper ref>, basis: [<定位>…], description?}`，选择性写入（[抽取原则](./extraction_principles.md) §8） |
| `experiments` | 每个研究问题一项：`anchors`（表、图的锚点列表，第一个为主锚点）、`locators`（全部行范围 `<章节>::<start>:<end>`，含表、图与陈述设计和结论的正文）、`task`、`text`（实验描述）、`participants`（`subject`、`role`）、`data`、`metrics` |
| `x-ingest` | `{committed_by, rounds}`：提交者与 dry_run 来回轮数，由入库入口读出写进批次记录（第 6 节） |

实验的分组与描述写法见 [抽取原则](./extraction_principles.md) §4；变体、条件、疑点与逐项来源性质都不进表单（§2、§5、§6），结果引自哪篇论文写在 `CITES` 的 `description` 中。数值留在原文。其余 `x-` 开头的键只作 YAML 复用；compile 忽略全部 `x-` 键。

## 3. 操作集

| 操作 | 写入 |
| --- | --- |
| `create_object` | Entity / Concept 节点；桩节点带 `stub: true` |
| `register_name` | `NameKey` 与 `NAMES` |
| `fill_stub` | 补全桩节点：**只填空字段**，去掉 `stub` |
| `add_material` | `Material`（路径、内容哈希）与 `MATERIAL_OF` |
| `add_experiment` | `Content:Experiment`，与 `FROM {material_ref, locators}`、`ON_TASK`、`EVALUATES {role}`、`USES {role: evaluation_data}`、`MEASURED_BY` |
| `link` | Entity / Concept 之间的关系；目前只实现 `CITES`，边上存 `source_refs`（`<material_id>::<定位>`）与 `description` |
| `record_batch` | `IngestBatch` 系统记录（第 6 节） |

Experiment 上的属性：`exp_key`、`anchors`、`text`。行范围只存在 `FROM.locators` 上。

## 4. 检查与返回

| 阶段 | 检查 | 返回类别 |
| --- | --- | --- |
| compile | 表单结构与未知字段；每个锚点都在材料中，且落在该实验某个 locator 的行范围内；locators 不越界；`text` 非空；同一实验中被测对象不重复、至少一个 target；各实验的主锚点不重复；桩节点不写定义、非桩必须写；Paper 对象只能是桩节点 | **错误** |
| compile | 关系只能是 `CITES`，起点是本文、终点是 Paper；`basis` 非空，且不能全部落在参考文献节内 | **错误** |
| compile | 表单里的方法名、数据集与指标的称呼不在该实验任一 locator 的行范围内（新对象的 name 或任一 alias 出现即可） | **待确认** |
| compile | 实验描述中出现带小数的数值（抽取原则 §4：不转录数值） | **待确认** |
| dry_run | 引用在 id / alias 级唯一命中 | 否则**待确认**（附候选） |
| dry_run | 新对象的语义近邻全部列入 `rejected`；桩节点只走 id、alias 与名称词面通道 | 否则**待确认** |
| dry_run | 新对象的精确键或唯一标识（如 arXiv 号）已被占用；新对象撞上已有桩节点（提示改用 `fill`） | **冲突** |
| dry_run | 实验的自然键已存在：`anchors`、`text`、`FROM.locators`、任务与三类参与边都相同为不变，否则为冲突 | **不变** / **冲突** |
| dry_run | `CITES` 的两端已在库中且边已存在：`source_refs` 与 `description` 都相同为不变，否则为冲突（`rel-changed`） | **不变** / **冲突** |

三类阻塞项的处理方不同：**错误**由 Agent 改表单；**待确认**由 Agent 做语义判断；**冲突**是与库内状态矛盾，由外部决定（改为引用、`fill`、改名或交人工）。有任何一类时 apply 拒绝整批。

## 5. 自然键与幂等

| 对象 | 自然键（存为属性，带唯一约束） |
| --- | --- |
| Experiment | `exp_key = <论文 id>::<主锚点>` |
| `CITES` | 起点与终点的 id（不另存键，也不加约束） |

- 同一表单重跑：全部为不变，不写入。写入中途失败时事务回滚，可直接重试。
- 实验内容有变化：冲突，拒绝写入。Content 不原地修改；修订操作随 Q2 与维护演练再定。
- 同一论文补录另一张表：论文按标识命中，新增一个 Experiment。表单中没有的实验不删除（可能来自其他批次）；撤回随维护设计再定。
- 写后复核不为空：说明 `Commit` 自身有缺陷，报错。

## 6. 批次记录

每批一个 `IngestBatch` 系统记录，连到 Paper：

- `coverage`：本批各实验的全部锚点（表、图）。同一论文多批的 coverage 取并集。查询时据此区分"原文没报告"与"没有录入"；抽取原则 §10 第 4 项的锚点覆盖检查也以它为准。
- 解析统计：引用在各级的命中数、展示的语义候选数与否定数、dry_run 来回轮数——主张 A 的构建成本。
- 写入统计：新建对象、实验与关系（`new_rels`）的数量。
- 来回轮数与提交者取自表单的 `x-ingest`，由提交者如实填写；中间件的偶发故障（如语义查重通道失败后重跑）不计入轮数，在表单注释中说明。
- 出处：表单与材料的内容哈希、提交者、时间。

## 7. 已定事项（2026-10-03）

| # | 事项 | 决定 |
| --- | --- | --- |
| 1 | 补全桩节点 | 只填空字段；改写已有内容属于修订（Q2） |
| 2 | 新对象撞上已有桩节点 | 报冲突，提示改用 `fill`；不由中间件自动合并 |
| 3 | 语义近邻未全部列入 `rejected` | 阻止 apply |
| 4 | `Material` 节点 | 现在引入 |
| 5 | 批次记录 | 图中的系统记录，不用日志文件 |
| 6 | 自然键 | 存为属性并加唯一约束 |
| 7 | 写入后的向量 | 由 apply 触发补算 |

## 8. 尚未覆盖

- 修订与撤回（Q2）、对象合并与拆分（Q4）。
- 显式的 Split 节点绑定：首个 I3 实例只用切分约定。
- Claim、Usage、Assessment 等其他 Content：首版不录。
- 被引论文本身入库时与它的 Paper 桩节点的同一性。桩节点没有标识，参考文献标题的大小写又常与原文不同，本文 `paper` 按标识和精确键都可能找不到它，于是新建出重复节点；精确键恰好相同时报 `stub-exists`，但 `paper` 目前不能写 `fill`。倾向：dry_run 对 `paper` 增加 Paper 桩节点的名称词面查重（与桩节点同一通道），命中进入待确认；`paper` 允许 `fill: {id}` 补全桩节点（[抽取原则](./extraction_principles.md) §10 第 3 项）。
- Paper 以外的关系写入（方法间关系等）：单篇抽取不写（[抽取原则](./extraction_principles.md) §1）。
