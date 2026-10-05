# apply-patch（vendored）

从 [openai/openai-agents-python](https://github.com/openai/openai-agents-python) 中取出 apply_patch 的解析与应用部分（上游 v0.23.1，commit `81f0ccf`，2026-10-02，MIT，见 `LICENSE`；只读原副本在 `references/repos/openai-agents-python`）。只用标准库。

用途：固定 Commit 写入机制所依据的 patch 格式与语义（见 `docs/experiments/e09/operators/commit.md`）。本包只处理文本，不知道 graph-doc、YAML 或图；在视图上怎么用 patch，由上层决定。

## 模块与来源

| 模块 | 内容 | 来源 |
| --- | --- | --- |
| `apply_diff.py` | 把一个 V4A diff 应用到一段文本：上下文匹配（逐级放宽空白）、`@@` 锚点、`*** End of File`、保留换行风格 | `src/agents/apply_diff.py`，原样复制 |
| `operations.py` | `ApplyPatchOperation`（`create_file` / `update_file` / `delete_file`，`move_to`）、`ApplyPatchResult`、`ApplyPatchEditor` 协议 | `src/agents/editor.py`；去掉 `ctx_wrapper`，协议改为同步 |
| `parser.py` | `*** Begin Patch` … `*** End Patch` 文本与 JSON 两种输入解析为操作列表 | `src/agents/sandbox/capabilities/tools/apply_patch_tool.py` 的解析函数；逻辑不变，私有名改为公开名 |
| `tool_spec.py` | 给模型的工具说明、lark 语法与 custom tool 配置 | 同上文件中的三个常量，原文不变 |
| `patch.py` | `apply_patch(texts, patch)`：在 `{名称: 文本}` 上应用整份 patch，全部成功或不改动 | **本包新增**；三种操作的规则取自上游 `src/agents/sandbox/apply_patch.py` 的 `WorkspaceEditor.apply_operation` |

测试：`tests/test_apply_diff.py`、`tests/test_apply_diff_helpers.py` 取自上游同名文件，只改了 import；`tests/test_patch.py` 为本包新增。

## 未复制的部分

- SDK 运行时：`RunContextWrapper`、`ApplyPatchTool` 及其审批（`needs_approval`、`on_approval`）、工具调用循环、Responses API 的工具转换；
- 沙箱：`WorkspaceEditor` 的文件系统读写、路径策略、符号链接与改名的暂存处理；
- 上游 `tests/test_apply_patch_tool.py` 与 `tests/sandbox/` 下的测试，它们依赖上述运行时。

## 与上游的行为差异

- `apply_patch` 在内存副本上依次执行操作，任一操作失败就抛出 `ApplyPatchError`（带出错的 `path` 与操作序号 `index`），输入不变。上游逐个操作写盘，失败前已执行的操作不回滚。
- `update_file` 带 `move_to` 且目标已存在时直接覆盖；上游在沙箱中还要处理同一文件的别名，这里不涉及。
