# PaperWeave

项目正在推进中...

## 概览

当前研究方向是：**面向 Agent 论文阅读的可复用经验的数据管理系统**，管理由论文阅读持续
沉淀下来的知识（解释、判断、综述等语义产物）、它们的使用产物（Artifact）与
溯源，以及项目级的知识视图和版本历史，供外部 Agent 在有界任务中发现、组合、
复用并继续积累。

核心设计：一个语义数据模型和一套操作的算子，支撑论文衍生知识及其使用
产物的表示、查询、组合与维护——通过项目知识视图和记录的版本历史——服务于
有界 CS 研究工作负载中的外部 Agent。

设计边界：外部 Agent 负责语义判断并提交显式操作；中间件负责校验、组织、持久化
与执行，内部不做关于研究结论的 LLM 推理。属性图与 Cypher 是当前的实现基础。
这里描述的模型与算子仍是设计契约，正在实现与评估中，尚不代表已完成的结论。

## 从哪里了解这个研究

- [`AGENTS.md`](AGENTS.md) — 当前研究方向、核心问题、设计边界与评估原则的权威表述。
- [`paper/narrative-draft.md`](paper/narrative-draft.md) — 正在演进的论文叙事草稿
  （动机、挑战、设计与章节大纲）。
- [`docs/discussions/`](docs/discussions/) — 设计讨论记录，最新的总体梳理见
  `2026-10-05-versioned-knowledge-management.md`；其中未与用户确认的提议均为暂定。
- [`docs/literature/`](docs/literature/) 与 [`references/`](references/) — 相关文献
  笔记与外部材料；`references/refs.bib` 是论文元数据的跟踪来源。
- `packages/`（`graph-doc`、`graph-vc` 等）与 `experiments/` — 正在搭建的实现与
  实验代码。

## Setup

```bash
make setup     # 建共享 .venv（Python 3.12）+ 装 nbstripout 的 git 过滤器
make lab       # 启动 JupyterLab
make verify    # 仓库级自检：主线阶段在无第三方依赖的隔离环境中仍能跑通
```

`make setup` 每个 clone 跑一次即可。它包含 `nbstripout --install`——过滤器命令写在
本机的 `.git/config`（不进版本管理），哪些文件走过滤器写在跟踪的 `.gitattributes`。
两边缺一不可，忘了装会导致带 cell 输出的 notebook 被提交；补救入口是 `make hooks`。

`make hooks` 还会设 `filter.nbstripout.extrakeys`，额外剥掉 `metadata.language_info.version`
——JupyterLab 会把本机的 Python 补丁版号写进 notebook，换机器就产生一行无意义的 diff。
这一项必须写进 git config，命令行的 `--extra-keys` 只对当次调用生效。

仓库根是一个 uv workspace，主线实验都是它的成员，共用一份 `uv.lock` 和一个 `.venv`。
`experiments/p4a`（历史项目，依赖冲突）与所有 TypeScript 目录不在其中。
请在仓库根目录运行 setup，不要在 workspace 成员目录中运行 `uv sync`。
