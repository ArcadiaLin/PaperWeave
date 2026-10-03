# Commit 契约：论文增量的入库

> **状态：** 已定（2026-10-03），尚未实现。规定外部 Agent 写好的入库表单如何编译成增量、由 `Commit` 检查并写入；抽什么、抽到多深见 [抽取原则](./extraction_principles.md)。对应 [Graph Model V2](./graph_model_v2.md) §7 第 15 项与 [Workload 拆解](./intents_decompose.md) §5 写路径。种子入库是其中的特例，E09 已实现（`experiments/e09/src/e09/operators/commit.py`）。

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

## 2. 表单（paper-form-v1）

| 字段 | 内容 |
| --- | --- |
| `form`、`domain` | 表单版本；领域配置名（如 `ltsf`，决定可用的条件槽与切分约定） |
| `material` | 材料路径与内容哈希 |
| `paper` | 论文本身：`labels`、`properties`（name、identifiers、description） |
| `refs` | 已有对象：`{mention, kind}`；或经确认的 `{id, printed?, register?}`，`register: true` 表示把 `printed` 注册为该对象的新 alias（笔误不注册） |
| `objects` | 新对象：核心方法与桩节点（`stub: true`），带 `rejected`；补全桩节点用 `fill: {id 或 mention}` |
| `relationships` | Entity / Concept 之间的关系；论文批次按单篇深度原则通常为空 |
| `experiments` | 每张表一项：`anchor`、`section`、`lines`、`task`、`text`、`setting`、`slots`、`slot_basis`、`columns`、`rows` |

结果表、条件槽、变体、来源性质的写法见 [抽取原则](./extraction_principles.md) §2–§6。`x-` 开头的键只作 YAML 复用，编译时忽略。

## 3. 操作集

| 操作 | 写入 |
| --- | --- |
| `create_object` | Entity / Concept 节点；桩节点带 `stub: true` |
| `register_name` | `NameKey` 与 `NAMES` |
| `fill_stub` | 补全桩节点：**只填空字段**，去掉 `stub` |
| `add_material` | `Material`（路径、内容哈希）与 `MATERIAL_OF` |
| `add_experiment` | `Content:Experiment`，与 `FROM`、`ON_TASK`；实验级 `EVALUATES` / `USES` / `MEASURED_BY` 由编译器取结果行的并集 |
| `add_result` | `ResultUnit`，与 `HAS_RESULT`、`EVALUATES {role}`、`USES {role: evaluation_data}`、`MEASURED_BY`、`FROM` |
| `link` | Entity / Concept 之间的关系 |
| `record_batch` | `IngestBatch` 系统记录（第 6 节） |

ResultUnit 上的属性：`value`、`value_num`、`variant`、`origin`、`origin_basis`、`note`，以及按领域配置展开的槽 `slot_<name>`。

## 4. 检查与返回

| 阶段 | 检查 | 返回类别 |
| --- | --- | --- |
| compile | 表单结构与未知字段；槽已声明且合语法；逐格覆盖引用的列存在；行与列不同时给同一个槽；实验内行键唯一；锚点逐行核对（预测长度与数值）；依据的定位在材料范围内；桩节点不写定义、非桩必须写；`rerun` / `cited` 必须给依据；`value_num` 解析 | **错误** |
| compile | 原文印的数据名与所绑定对象不同名 | **待确认** |
| dry_run | 引用在 id / alias 级唯一命中 | 否则**待确认**（附候选） |
| dry_run | 新对象的语义近邻全部列入 `rejected`；桩节点只走 id、alias 与名称词面通道 | 否则**待确认** |
| dry_run | 新对象的精确键或唯一标识（如 arXiv 号）已被占用；新对象撞上已有桩节点（提示改用 `fill`） | **冲突** |
| dry_run | 自然键已存在：内容相同为不变，内容不同为冲突 | **不变** / **冲突** |
| dry_run | 库中有、表单中没有的结果行 | **报告**，不删除 |

三类阻塞项的处理方不同：**错误**由 Agent 改表单；**待确认**由 Agent 做语义判断；**冲突**是与库内状态矛盾，由外部决定（改为引用、`fill`、改名或交人工）。有任何一类时 apply 拒绝整批。

## 5. 自然键与幂等

| 对象 | 自然键（存为属性，带唯一约束） |
| --- | --- |
| Experiment | `exp_key = <论文 id>::<主锚点>` |
| ResultUnit | `row_key = <exp_key>::<被测对象 id>::<变体>::<数据 id>::<指标 id>::<各槽值>` |

- 同一表单重跑：全部为不变，不写入。写入中途失败时事务回滚，可直接重试。
- 值有变化：冲突，拒绝写入。Content 不原地修改；修订操作随 Q2 与维护演练再定。
- 表单删去的行：库中不删，plan 报告。撤回随维护设计再定。
- 写后复核不为空：说明 `Commit` 自身有缺陷，报错。

## 6. 批次记录

每批一个 `IngestBatch` 系统记录，连到 Paper：

- `coverage`：本批录入的表（主锚点列表）。同一论文多批的 coverage 取并集。查询时据此区分"原文没报告"与"没有录入"。
- 解析统计：引用在各级的命中数、展示的语义候选数与否定数、dry_run 来回轮数——主张 A 的构建成本。
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
