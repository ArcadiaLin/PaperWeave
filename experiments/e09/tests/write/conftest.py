"""写入路径测试的共用部件：内存中的图、材料文件与种子文档。"""

from __future__ import annotations

import textwrap
from collections import defaultdict
from pathlib import Path

import pytest

from e09.write import Context, Deduper, MemoryReader, Prepared, allocate_ids, prepare
from graph_vc import GraphState

AT = "2026-10-05T12:00:00+00:00"

SEED = """
graph-doc: v0.1
by: seed
nodes:
  $tsf:
    kind: Task
    name: Time series forecasting
    aliases: [TSF]
    definition: Predict future values of a series from its past.
  $ltsf:
    kind: Task
    name: Long-term time series forecasting
    aliases: [LTSF]
    definition: Forecasting with a long horizon.
    BROADER: [$tsf]
  $tf:
    kind: Method
    name: Transformer-based forecasting
    definition: Forecasting models built on Transformer architectures.
  $ett:
    kind: Dataset
    name: ETT
    description: Electricity transformer temperature data.
    identifiers: ["url:https://github.com/zhouhaoyi/ETDataset"]
    FOR_TASK: [$ltsf]
  $etth1:
    kind: Dataset
    name: ETTh1
    description: Hourly subset of ETT.
    identifiers: ["url:https://github.com/zhouhaoyi/ETDataset"]
    PART_OF: [$ett]
    FOR_TASK: [$ltsf]
"""
# 种子按文档顺序、按前缀分配：task_0001 tsf、task_0002 ltsf、method_0001 tf、dataset_0001 ett、dataset_0002 etth1

DLINEAR = """
graph-doc: v0.1
by: claude
nodes:
  $paper:
    kind: Paper
    name: Are Transformers Effective for Time Series Forecasting?
    identifiers: ["arxiv:2205.13504"]
    year: 2023
    material: papers/2023-DLinear/paper.md
    description: Questions whether Transformers are effective for LTSF and introduces DLinear.
  $dlinear:
    kind: Method
    name: DLinear
    aliases: [D-Linear]
    definition: A linear model on a trend and remainder decomposition.
    BROADER: [method_0001]
  $exp:
    kind: Experiment
    anchors: [S5.T2, A3.T9]
    text: Compare DLinear with Transformer baselines on nine datasets.
    FROM:
      - {to: $paper, locators: ["5.2 Comparison::198:240"]}
    EVALUATES:
      - {to: $dlinear, role: target}
      - {to: method_0001, role: baseline}
    USES:
      - {to: dataset_0002, role: evaluation_data}
    ON_TASK: [task_0002]
  $claim:
    kind: Claim
    text: DLinear outperforms Transformer methods in most settings.
    FROM:
      - {to: $paper, locators: ["Abstract::10:14"]}
    ABOUT: [$dlinear, task_0002]
    SUPPORTED_BY: [$exp]
  $contrib:
    kind: Contribution
    stated_by: paper
    text: Introduces a simple linear baseline for LTSF.
    FROM:
      - {to: $paper, locators: ["1 Introduction::40:44"]}
    ABOUT: [$dlinear]
"""


class Counters:
    """内存中的 id 分配，与 VersionedGraph.allocate_ids 的格式相同。"""

    def __init__(self) -> None:
        self.last: dict[str, int] = defaultdict(int)

    def allocate_ids(self, prefix: str, count: int = 1) -> list[str]:
        start = self.last[prefix]
        self.last[prefix] += count
        return [f"{prefix}_{n:04d}" for n in range(start + 1, start + count + 1)]


class MemoryGraph:
    """在内存状态上走与 apply 相同的流程：dry_run、分配 id、用真实 id 准备、应用。"""

    def __init__(self, root: Path):
        self.root = root
        self.state = GraphState()
        self.counters = Counters()
        self.deduper: Deduper | None = None

    def context(self, source: str = "test") -> Context:
        return Context(MemoryReader(self.state), source, AT, self.root, self.deduper)

    def dry_run(self, text: str, source: str = "test") -> Prepared:
        return prepare(text, self.context(source))

    def submit(self, text: str, source: str = "test") -> Prepared:
        dry = self.dry_run(text, source)
        if not dry.ok:
            return dry
        assert dry.document is not None
        prepared = prepare(text, self.context(source), allocate_ids(dry.document, self.counters))
        assert prepared.ok, prepared.errors
        assert prepared.changeset is not None
        self.state = self.state.apply(prepared.changeset)
        return prepared


def write_material(root: Path, path: str, lines: int = 300) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("".join(f"{path} line {i}\n" for i in range(1, lines + 1)), encoding="utf-8")


@pytest.fixture
def graph(tmp_path: Path) -> MemoryGraph:
    write_material(tmp_path, "papers/2023-DLinear/paper.md")
    write_material(tmp_path, "papers/2023-PatchTST/paper.md")
    g = MemoryGraph(tmp_path)
    assert g.submit(SEED, "seed:tsf").ok
    return g


@pytest.fixture
def ingested(graph: MemoryGraph) -> MemoryGraph:
    prepared = graph.submit(DLINEAR, "paper:2023-DLinear")
    assert prepared.ok, prepared.errors
    return graph


def rules(prepared: Prepared) -> set[str]:
    return {p.rule for p in prepared.errors}


def doc(body: str) -> str:
    """补上文档头；正文按两个空格缩进写在 nodes 下。"""
    return "graph-doc: v0.1\nby: claude\nnodes:\n" + textwrap.indent(textwrap.dedent(body).strip("\n"), "  ") + "\n"
