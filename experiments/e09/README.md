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
    make embed        # 建向量索引并补算向量；需要 embedding 服务（见 utils/embedding.py）
    make test         # 读取算子在现有库上的检验；期望值由正式表单独立推出
    make lab          # JupyterLab，工作目录为 notebooks/

## 写入路径（重写中）

写入路径改为统一的底层：[graph-vc](../../packages/graph-vc)（变更集与版本记录）与
[graph-doc](../../packages/graph-doc)（读写同形的 YAML 子图及求差），设计见
`docs/experiments/e09/operators/commit.md`。E09 只保留模型相关的部分（graph-doc → 物理目标状态的翻译与检查），尚未写完；
种子与论文表单将一次性转成 graph-doc 后重新入库，开发期间只写 `infra/neo4j-test` 的测试实例。

原先的写入路径（paper-form-v4 / supplement-form-v1 编译、Commit 的种子、论文与增补增量、`make seed` / `make ingest`）
已删除，最后状态见 tag `e09-legacy-write`。现有 neo4j-e09 库与 I3 实验都由它建出；需要重建该库时，在该 tag 上运行
`make seed ingest embed`。

## 数据

    data/raw/e09-paper-knowledge/
      papers.yml, status.yml, runs/   # 复制自 e08（2026-10-02），材料准备的原始记录
      papers/<citekey>/paper.md …     # 论文材料，复制自 e08，只读
      seeds/                          # v2 种子（版本管理），格式见 seeds/README.md；待转成 graph-doc
      forms/                          # 论文入库表单 paper-form-v4（版本管理）；待转成 graph-doc

`papers/`、`runs/` 等材料不进版本管理，只有 `seeds/` 与 `forms/` 被跟踪。

## 布局

    notebooks/            探索面：按步骤推进入库与检验
    notebooks/_scratch/   notebook 导出的中间结果，不进版本管理
    src/e09/              已确定的部分，脚本与 notebook 共用
    src/e09/operators/    中间件算子，一个算子一个文件，文件名即设计中的算子名
    src/e09/utils/        算子共用的底层部件，本身不是算子
    tests/                读取算子与 I3 参考答案的检验：连 neo4j-e09 现有库，库没起时跳过
    i3/                   首个 I3 实例：questions.yml（三组共同看到的问题与答案格式）、reference.yml（参考答案）

| 位置 | 内容 |
| --- | --- |
| `config` | 路径与连接参数 |
| `env_check` | 环境自检（`make check`） |
| `tools` | 外部 Agent（pi）调用读取算子的命令行入口，I3 使用 |
| `operators/resolve` | Resolve：id → alias → 语义三级解析，read / write 两种模式；Entity 与 Concept |
| `operators/get` | Get：对象视图（属性、由 NameKey 装配的 aliases、identifiers），不展开关系 |
| `operators/experiments` | Experiments：按被测对象（任一命中）、数据集（严格，或沿 PART_OF / VERSION_OF 展开）、指标与论文范围取实验报告；纯结构匹配，不走语义通道；返回参与方的角色、变体与来源性质、条件、材料定位，以及 expandable / role_missing 诊断 |
| `operators/read_evidence` | ReadEvidence：按 `<material_id>::<章节>::<start>:<end>` 读材料行，核对内容哈希，逐项给出 available / missing / error |
| `utils/schema` | graph_model_v2 的机器可读部分：kind、命名空间唯一性、关系端点、id 前缀、约束、全文索引、来源引用的定位格式 |
| `utils/graph` | 连接、只读查询 `q`、建约束与全文索引 |
| `utils/namekey` | 规范化配置 `name-key-v1` 与精确键 |
| `utils/embedding` | 向量服务（与 e08 共用 Qwen3-Embedding-8B）、向量索引与补算（`make embed`）：Entity、Concept、Content 的文本与带 `description` 的关系都建向量 |
| `utils/fusion` | 语义阶段的召回参数、分词与 RRF 融合 |

Resolve 与 Get 的用例见 `notebooks/02_resolve_get.ipynb`。尚未实现的算子列在 `operators/__init__.py`。

## 现在还不是什么

已入库两篇论文（报告级，2026-10-03）：2023-DLinear 的表 2–9 与 2023-PatchTST 的表 1、3–15，共 22 个实验，表单由 Claude
手写，作为人工样例与参考结果。读取侧已有 Resolve、Get、Experiments 与 ReadEvidence；Search、Context 等尚未实现，
"找设计相似的实验"属于 Search，不在 Experiments 中。论文增量中的关系只实现了 `CITES`。notebook 只读写 `data/raw/e09-paper-knowledge/` 与 neo4j-e09，不能成为文档引用数字的唯一来源（AGENTS.md）。
