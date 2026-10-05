# graph-vc

图的统一写入底层：把一份**变更集**（带改前与改后状态的修改）在 Neo4j 的单个事务中执行，并写入版本记录。所有对图的修改都经过这里：Commit 工具（graph-doc）、Agent 算子写 Artifact、`Revert`，以及以后的 `Fork` / `Sync` / `Promote`。设计见 `docs/experiments/e09/operators/commit.md` §8 与 `docs/discussions/2026-10-05-versioned-knowledge-management.md`。

本包只认物理图（Label、属性、关系），不知道 graph-doc 与数据模型；从 graph-doc 求出变更集、查重、端点规则等由上层负责。

## 变更集

```python
from graph_vc import Changeset, EdgeChange, NodeChange

cs = Changeset(
    nodes=(
        NodeChange.create("method_0022", ["Concept", "Method"], {"name": "PatchTST"}),
        NodeChange.update("method_0016", ["Concept", "Method"], {"note": "old"}, {"note": None}),
    ),
    edges=(EdgeChange.create("method_0022", "BROADER", "method_0004"),),
)
```

- 节点以 `id` 属性标识，`id` 不能修改；属性值 `None` 表示不存在。
- 边以 `(起点 id, 类型, 终点 id)` 标识，同一对节点之间同一类型的边至多一条。
- 新建只有改后，删除只有改前（完整的 Label 与属性），修改只列改动的属性；`invert()` 给出逆向变更集。
- 删除节点时，它的全部关系都必须在同一变更集中删除。
- 属性值只能是 JSON 兼容、Neo4j 可存的类型：布尔、整数、有限浮点数、字符串，以及它们的同类型列表。时间请存成 ISO 字符串。
- `files` 列出变更集依赖的图外文件（相对路径与 SHA-256），提交前核对它们存在且未被改动。
- `to_dict()` / `from_dict()` 与普通 dict 互转，提交记录中以 JSON 保存。

## 写入与读取

```python
from neo4j import GraphDatabase
from graph_vc import VersionedGraph

graph = VersionedGraph(
    GraphDatabase.driver(uri, auth=auth),
    file_root=repo_root,
    unversioned_props=frozenset({"embedding", "embedding_key"}),  # 派生属性，提交后由上层补算
)
graph.setup()  # 约束与 main 分支，可重复调用
ids = graph.allocate_ids("method", 2)  # ["method_0023", "method_0024"]
record = graph.commit(cs, author="claude", message="…", source="commit-tool", meta={"rounds": 2})
graph.revert(record.id, author="claude")  # 以新提交撤销，不改写历史
graph.history()  # 分支上的提交，从最早到最新
graph.snapshot()  # 当前受版本管理的状态（GraphState）
graph.local_state(["method_0016"])  # 这些节点、它们的全部关系及另一端的节点；上层据此求变更集
```

`commit` 在一个事务中依次：锁分支节点 → 取出相关节点与边核对改前状态（不一致则抛 `ConflictError`，列出全部不一致项）→ 删边、建节点、改节点、建边与改边、删节点 → 写 `(:Commit)`、`PARENT`、`TOUCHED {op}`，推进分支头。任一步失败整体回滚。

版本记录占用 Label `Commit`、`Branch`、`IdCounter` 与关系 `PARENT`、`TOUCHED`；变更集不能触及它们，`snapshot()` 也不包含它们。

| `Commit` 属性 | 内容 |
| --- | --- |
| `id`、`branch`、`seq`、`parent` | 提交 id（`commit_000001`）、分支、分支内序号、父提交 |
| `author`、`at`、`message`、`source` | 写入者、时间（ISO）、说明、来源 |
| `base`、`input`、`meta` | 写入者读视图时所在的提交、交上来的原文、其余信息（JSON） |
| `changeset` | 变更集（JSON） |
| `touched`、`removed` | 本次触及且仍存在的节点、本次删除的节点 |

`GraphState.apply()` 在内存中执行同样的前提核对与修改，用于测试与以后的 `AsOf`。

`unversioned_props` 列出节点与关系上不受版本管理的属性（如检索用的向量）：变更集不能写它们，核对改前状态与 `snapshot()` 都忽略它们。它们随节点或关系一起被删除；修改节点时保持原值，是否过期由上层判断并补算；重放或撤销后需要重新补算。

## 已知限制

- 节点按 `id` 匹配时不带 Label，走全库扫描；论文规模下可以接受，以后可让变更集携带 Label 以使用索引。
- 没有 `id` 的节点不受版本管理；删除节点时若它连着这类节点，提交被拒绝。上层应给要纳入版本管理的节点都赋 `id`（如 `NameKey` 以其 `key` 为 `id`）。
- 计数器分配的 id 不复用；首次使用某前缀时从库中已用的最大序号起算。
- 删除节点时会一并删掉指向它的 `TOUCHED`；它的历史仍在各提交的 `changeset` 与 `removed` 中。

## 测试

```bash
uv run pytest packages/graph-vc            # 不需要数据库的测试；数据库测试在未配置时跳过
```

数据库测试会清空所连的库，因此只在显式配置时运行，并且要求开始时库为空：

```bash
docker compose -f infra/neo4j-test/docker-compose.yml up -d     # 端口 7688，不挂载数据卷
GRAPH_VC_TEST_NEO4J_URI=bolt://localhost:7688 uv run pytest packages/graph-vc
```
