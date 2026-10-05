"""在内存中的文本集合上应用 patch。

本模块不是上游代码。上游的 ``WorkspaceEditor.apply_operation``（``src/agents/sandbox/apply_patch.py``）
把操作落到沙箱文件系统；这里保留它对三种操作的处理规则，改为作用在 ``{名称: 文本}`` 上的纯函数：

- ``create_file``：名称不能已存在，内容由 ``apply_diff(..., mode="create")`` 得到；
- ``update_file``：名称必须存在，``apply_diff`` 应用到原文；带 ``move_to`` 时改名（目标已存在则覆盖）；
- ``delete_file``：名称必须存在。

整份 patch 要么全部成功，要么抛出 ``ApplyPatchError`` 且不改动输入。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .apply_diff import apply_diff
from .operations import ApplyPatchOperation
from .parser import parse_patch_input


class ApplyPatchError(ValueError):
    """某个操作无法应用。``path`` 是出错的名称，``index`` 是它在操作列表中的位置。"""

    def __init__(self, message: str, *, path: str | None = None, index: int | None = None):
        super().__init__(message)
        self.path = path
        self.index = index


def apply_operations(
    texts: Mapping[str, str], operations: Iterable[ApplyPatchOperation]
) -> dict[str, str]:
    """按顺序应用操作，返回新的文本集合；输入不被修改。"""
    result = dict(texts)
    for index, op in enumerate(operations):
        try:
            _apply_one(result, op)
        except ApplyPatchError as exc:
            exc.index = index
            raise
        except ValueError as exc:
            raise ApplyPatchError(str(exc), path=op.path, index=index) from exc
    return result


def apply_patch(texts: Mapping[str, str], patch: str) -> dict[str, str]:
    """解析 patch 文本（或 JSON 形式的操作）并应用到文本集合。"""
    return apply_operations(texts, parse_patch_input(patch))


def _apply_one(texts: dict[str, str], op: ApplyPatchOperation) -> None:
    if op.type == "delete_file":
        if op.path not in texts:
            raise ApplyPatchError(f"Cannot delete missing file: {op.path}", path=op.path)
        del texts[op.path]
        return

    if op.diff is None:
        raise ApplyPatchError(
            f"Missing diff for operation type {op.type} on path {op.path}", path=op.path
        )

    if op.type == "create_file":
        if op.path in texts:
            raise ApplyPatchError(
                f"apply_patch cannot create {op.path} because it already exists. "
                "Use an update_file operation to change an existing file.",
                path=op.path,
            )
        texts[op.path] = apply_diff("", op.diff, mode="create")
        return

    if op.type == "update_file":
        if op.path not in texts:
            raise ApplyPatchError(f"Cannot update missing file: {op.path}", path=op.path)
        updated = apply_diff(texts[op.path], op.diff, mode="default")
        if op.move_to is None or op.move_to == op.path:
            texts[op.path] = updated
        else:
            del texts[op.path]
            texts[op.move_to] = updated
        return

    raise ApplyPatchError(f"Unknown operation type: {op.type}", path=op.path)


__all__ = ["ApplyPatchError", "apply_operations", "apply_patch"]
