# E09 测试的运行方法

> **记录日期：** 2026-10-08。说明如何运行 `packages/graph-vc`、`packages/graph-doc` 与 `experiments/e09` 的测试，尤其是需要 Neo4j 的连库测试。命令都从仓库根目录执行，除非另行说明。

## 1. 测试的组成

| 测试集 | 不连库，随时可跑 | 连库，需要空的测试实例 |
| --- | --- | --- |
| `packages/graph-vc` | 45 个：变更集、内存状态 | 15 个：`tests/test_store.py`（提交、回滚、重放、可逆、`state_at` 等） |
| `packages/graph-doc` | 54 个 | 2 个：`tests/test_roundtrip.py` |
| `experiments/e09` | 105 个：写入管线的内存场景、MCP 装配、工具接口、参数修复、读取接口（`tests/interfaces/`，用内存中的版本历史） | 101 个：`tests/commit/` 的往返与命令行、`tests/operators/db/`、`tests/operators/agent/` |

数量是 2026-10-08 不设置测试实例时的结果（通过与跳过）。

连库测试只在设置了环境变量 `GRAPH_VC_TEST_NEO4J_URI` 时运行，没有设置时跳过。用户名与密码默认为 `neo4j` / `password`，可用 `GRAPH_VC_TEST_NEO4J_USER`、`GRAPH_VC_TEST_NEO4J_PASSWORD` 改。测试不需要向量服务：查询向量关闭，写入后也不补算。

以下连库测试是 2026-10-07 至 10-08 新增的，**还没有在 Neo4j 上运行过**，第一次运行即是对它们的检验：

- graph-vc `test_state_at_is_the_state_after_each_commit`：逆向重放求出的每个提交时的状态，等于从空状态正向重放的结果；
- e09 `test_db_evidence.py::test_at_resolves_references_in_a_past_state`：ReadEvidence 的 `at`；
- e09 `test_db_traverse.py::test_snapshot_is_the_head_the_view_was_read_at` 与 `test_db_search.py::test_snapshot_is_the_head_the_results_were_read_at`：读取前后核对头提交。

## 2. 安全约定

- **连库测试会清空所连的库。** 每个连库测试模块开始时要求库为空，结束时删除全部节点；e09 的模块还会删掉全部约束与索引。
- **库不空时拒绝运行。** 开始时库中有节点，测试就跳过并给出原因 `refusing to run: test database at … is not empty`，不会删除数据。因此误连到有数据的库只会全部跳过，不会造成损失；但这也意味着"全部跳过"不代表通过，要用 `-rs` 查看跳过原因。
- **不要连 neo4j-e09（bolt 7687）。** 它是实验用的库，测试不会主动连它，环境变量也不要指向它。
- **现在的 infra/neo4j-test（bolt 7688）不是空库。** 里面是 2026-10-06 MCP 试跑写入的数据（370 个节点、1062 条关系，备份在 `~/e09-runs/2026-10-06-commit-trial/neo4j-7688-after-trials.json`）。测试连它只会全部跳过。它没有挂载数据卷，**`docker compose down` 会删掉这些数据**；只停止（`docker compose stop` 或 `docker stop neo4j-test`）不会。

## 3. 推荐方式：另起一个一次性实例

用与 infra/neo4j-test 相同的镜像，另起一个端口不冲突的容器（bolt 7689，浏览器 7476）。它用完即删，不影响 7687 与 7688。

```bash
# 1. 启动；--rm 表示停止后容器连同数据一起删除
docker run -d --rm --name neo4j-test-run \
  -p 7476:7474 -p 7689:7687 -e NEO4J_AUTH=neo4j/password neo4j:ubi10

# 2. 等到 Neo4j 启动完成（日志出现 Started.）
until docker logs neo4j-test-run 2>&1 | grep -q "Started."; do sleep 2; done

# 3. 依次运行三个测试集；-rs 列出跳过的测试及原因
export GRAPH_VC_TEST_NEO4J_URI=bolt://localhost:7689
.venv/bin/python -m pytest packages/graph-vc -q -rs
.venv/bin/python -m pytest packages/graph-doc -q -rs
(cd experiments/e09 && ../../.venv/bin/python -m pytest tests -q -rs)

# 4. 停止，容器与数据一并删除
docker stop neo4j-test-run
```

当前用户不在 docker 组时，把 `docker` 换成 `sudo docker`。e09 的第 3 步也可以写成 `make -C experiments/e09 test`（它执行 `uv run pytest tests -q`，不加 `-rs`）。不要在成员目录里运行 `uv sync`（见 AGENTS.md）。

**期望结果：** 三个测试集都没有跳过，全部通过，即 graph-vc 60 个、graph-doc 56 个、e09 206 个。

**各测试集依次运行，不要并行。** 每个模块都要求开始时库为空，并行运行会互相看到对方的数据。一个模块中途失败而没有清空时，之后的模块会因库不空而跳过；这时停止容器、重新执行第 1 步，再从失败的测试集重跑。

## 4. 不连库的检查

不需要 Neo4j，随时可以运行：

```bash
.venv/bin/python -m pytest packages/graph-vc packages/graph-doc -q
(cd experiments/e09 && ../../.venv/bin/python -m pytest tests -q)
(cd experiments/e09 && uvx ruff check src tests && uvx ruff format --check src tests)
uvx ruff check packages/graph-vc && uvx ruff format --check packages/graph-vc
```

## 5. 用 7688 运行（暂不推荐）

只有 7688 可用时，要先备份其中的试跑数据，清空后运行测试，再恢复。2026-10-06 做过这样一轮，但所用的导出、清空与恢复脚本只是临时脚本，不在仓库中。若要这样做，先商定把备份脚本放进仓库（例如 `infra/neo4j-test/`），恢复后用摘要核对与备份一致。在此之前请用第 3 节的方式。

## 6. 与真实历史的只读核对

读取接口在 2026-10-07 另做过一次只读核对，用的是 7687 与 7688 的真实历史：

- `AsOf(main)` 与 Traverse 的视图逐对象一致；
- `Show` 的 `input` 分页可以拼回原文；
- `Diff(父提交, 提交)` 等于 `Show(提交, changes)`；
- 所有输出都不超过 16 KB。

核对结果记在提交 `b793426` 的说明中。所用脚本是临时的，不在仓库中；是否把它整理成仓库中的检查脚本，待讨论后再定。
