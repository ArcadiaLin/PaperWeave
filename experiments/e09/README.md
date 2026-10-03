# E09 · v2 数据模型的真实论文入库

按 [Graph Model V2](../../docs/designs/v2/graph_model_v2.md) 把真实论文入库，检验
[Workload 拆解](../../docs/designs/v2/intents_decompose.md) 中的访问契约。第一个实例是
I3（实验比较）：DLinear 与 PatchTST。

E08 是 v1 图谱，保留不动；E09 用独立的数据目录与 Neo4j 实例。

## 环境

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| Python 环境 | 仓库根的 uv workspace（本目录是成员） | notebook 内核同样用根 `.venv` |
| Neo4j（v2 图谱） | `infra/neo4j-e09/` | bolt 7687，浏览器 7474 |
| Neo4j（v1 图谱） | `infra/neo4j-e08/` | 端口相同，同一时间只起一个 |
| 共同配置 | `src/e09/config.py` | 路径与连接参数，脚本与 notebook 共用 |

    make setup        # 第一次，或依赖变化后
    make neo4j-up     # 不在 docker 组时：make neo4j-up DOCKER="sudo docker"
    make check        # 自检：材料与种子目录、连库、确认不是 v1 库
    make seed         # 种子入库；重跑无副作用，有冲突或复核失败时返回非零
    make embed        # 建向量索引并补算向量；需要 embedding 服务（见 utils/embedding.py）
    make compile      # 编译论文表单（不连库）；默认编译 fixtures/forms/ 下的夹具
    make lab          # JupyterLab，工作目录为 notebooks/

## 数据

    data/raw/e09-paper-knowledge/
      papers.yml, status.yml, runs/   # 复制自 e08（2026-10-02），材料准备的原始记录
      papers/<citekey>/paper.md …     # 论文材料，复制自 e08，只读
      seeds/                          # v2 种子（版本管理），格式见 seeds/README.md

`papers/`、`runs/` 等材料不进版本管理，只有 `seeds/` 被跟踪。

## 布局

    notebooks/            探索面：按步骤推进入库与检验
    notebooks/_scratch/   notebook 导出的中间结果，不进版本管理
    src/e09/              已确定的部分，脚本与 notebook 共用
    src/e09/operators/    中间件算子，一个算子一个文件，文件名即设计中的算子名
    src/e09/utils/        算子共用的底层部件，本身不是算子
    fixtures/forms/       表单夹具：只覆盖一张表的部分行，用来检验编译与 Commit，不是正式入库表单

| 位置 | 内容 |
| --- | --- |
| `config` | 路径与连接参数 |
| `env_check` | 环境自检（`make check`） |
| `seed` | 种子入库入口：固定写入顺序、读种子文件，逐批经 Commit 写入（`make seed`） |
| `form` | 论文表单编译（不连库）：表单 → delta，报告错误与待确认项（`make compile`）；契约见 `docs/designs/v2/commit_contract.md` |
| `operators/commit/` | Commit：增量检查 → plan（dry_run）→ apply → 复核。`seed` 处理种子增量；`paper` 处理论文表单编译出的增量（Experiment、ResultUnit、Material、IngestBatch），`apply_paper(commit=False)` 为演练：写入并复核后回滚 |
| `operators/resolve` | Resolve：id → alias → 语义三级解析，read / write 两种模式；Entity 与 Concept |
| `operators/get` | Get：对象视图（属性、由 NameKey 装配的 aliases、identifiers），不展开关系 |
| `utils/schema` | graph_model_v2 的机器可读部分：kind、命名空间唯一性、关系端点、id 前缀、约束、全文索引 |
| `utils/graph` | 连接、只读查询 `q`、建约束与全文索引 |
| `utils/namekey` | 规范化配置 `name-key-v1` 与精确键 |
| `utils/ids` | 按 kind 顺序分配对象 id |
| `utils/embedding` | 向量服务（与 e08 共用 Qwen3-Embedding-8B）、向量索引与补算（`make embed`） |
| `utils/fusion` | 语义阶段的召回参数、分词与 RRF 融合 |
| `utils/domain` | 领域配置：条件槽的取值语法、哪些槽印在行标签上、有名字的切分约定 |

种子入库与失败路径演示见 `notebooks/01_seed_ingest.ipynb`，Resolve 与 Get 的用例见 `notebooks/02_resolve_get.ipynb`。尚未实现的算子列在 `operators/__init__.py`。

## 现在还不是什么

还没有论文入库。表单编译（`form`）与 Commit 的论文增量（`operators/commit/paper`）已实现，只用夹具做过演练
（写入后回滚）；正式表单与入库目标（`make ingest`）待三张表全量抽取时再加。读取侧只有 Resolve 与 Get，其余算子尚未实现。notebook 只读写
`data/raw/e09-paper-knowledge/` 与 neo4j-e09，不能成为文档引用数字的唯一来源（AGENTS.md）。
