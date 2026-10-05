"""把模型给出的 patch 输入解析成操作列表。

取自上游 ``src/agents/sandbox/capabilities/tools/apply_patch_tool.py`` 的
``_parse_custom_tool_input`` 及其辅助函数，逻辑不变，只把私有函数改为公开名：

- ``parse_patch_input``：自动区分两种输入（上游 ``_parse_custom_tool_input``）；
- ``parse_patch``：``*** Begin Patch`` … ``*** End Patch`` 文本（上游 ``_parse_apply_patch_input``）；
- ``parse_patch_json``：JSON 形式的操作（上游 ``_parse_apply_patch_json``）。

解析只切分各文件的操作，不校验 hunk 内容；hunk 由 ``apply_diff`` 在应用时校验。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .operations import ApplyPatchOperation

BEGIN_PATCH = "*** Begin Patch"
END_PATCH = "*** End Patch"
ADD_FILE = "*** Add File: "
DELETE_FILE = "*** Delete File: "
UPDATE_FILE = "*** Update File: "
MOVE_TO = "*** Move to: "


def parse_patch_input(raw_input: str) -> list[ApplyPatchOperation]:
    stripped_input = raw_input.lstrip()
    if stripped_input.startswith(("{", "[")):
        return parse_patch_json(raw_input)
    return parse_patch(raw_input)


def parse_patch_json(raw_input: str) -> list[ApplyPatchOperation]:
    payload = json.loads(raw_input)
    if isinstance(payload, Mapping):
        operations = payload.get("operations")
        if isinstance(operations, Sequence) and not isinstance(operations, str | bytes):
            return [_parse_operation_json(operation) for operation in operations]
        operation = payload.get("operation")
        if operation is not None:
            return [_parse_operation_json(operation)]
        return [_parse_operation_json(payload)]
    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes):
        return [_parse_operation_json(operation) for operation in payload]
    raise ValueError("apply_patch JSON input must be an object or array")


def _parse_operation_json(operation: object) -> ApplyPatchOperation:
    if not isinstance(operation, Mapping):
        raise ValueError("apply_patch operation must be an object")

    raw_type = operation.get("type")
    raw_path = operation.get("path")
    raw_diff = operation.get("diff")
    if raw_type not in {"create_file", "update_file", "delete_file"}:
        raise ValueError(f"Invalid apply_patch operation type: {raw_type}")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("apply_patch operation is missing a path")
    if raw_type in {"create_file", "update_file"} and not isinstance(raw_diff, str):
        raise ValueError(f"apply_patch operation {raw_type} is missing a diff")
    if raw_type == "delete_file":
        raw_diff = None

    raw_move_to = operation.get("move_to")
    if raw_move_to is not None and not isinstance(raw_move_to, str):
        raise ValueError("apply_patch operation move_to must be a string")

    return ApplyPatchOperation(
        type=raw_type,
        path=raw_path,
        diff=raw_diff,
        move_to=raw_move_to,
    )


def parse_patch(raw_input: str) -> list[ApplyPatchOperation]:
    lines = raw_input.splitlines()
    if not lines or lines[0] != BEGIN_PATCH:
        raise ValueError("apply_patch input must start with '*** Begin Patch'")
    if len(lines) < 2 or lines[-1] != END_PATCH:
        raise ValueError("apply_patch input must end with '*** End Patch'")

    operations: list[ApplyPatchOperation] = []
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if line.startswith(ADD_FILE):
            parsed, index = _parse_add_file(lines, index)
        elif line.startswith(DELETE_FILE):
            parsed, index = _parse_delete_file(lines, index)
        elif line.startswith(UPDATE_FILE):
            parsed, index = _parse_update_file(lines, index)
        else:
            raise ValueError(f"Invalid apply_patch file operation header: {line}")
        operations.append(parsed)

    if not operations:
        raise ValueError("apply_patch input must include at least one file operation")
    return operations


def _parse_add_file(lines: list[str], index: int) -> tuple[ApplyPatchOperation, int]:
    path = _parse_path_header(lines[index], ADD_FILE)
    index += 1
    diff_lines: list[str] = []
    while index < len(lines) - 1 and not _is_file_operation_header(lines[index]):
        line = lines[index]
        if not line.startswith("+"):
            raise ValueError(f"Invalid Add File line: {line}")
        diff_lines.append(line)
        index += 1
    if not diff_lines:
        raise ValueError(f"Add File patch for {path} must include at least one + line")
    return (
        ApplyPatchOperation(type="create_file", path=path, diff=_join_diff(diff_lines)),
        index,
    )


def _parse_delete_file(lines: list[str], index: int) -> tuple[ApplyPatchOperation, int]:
    path = _parse_path_header(lines[index], DELETE_FILE)
    index += 1
    if index < len(lines) - 1 and not _is_file_operation_header(lines[index]):
        raise ValueError(f"Delete File patch for {path} must not include a diff")
    return ApplyPatchOperation(type="delete_file", path=path), index


def _parse_update_file(lines: list[str], index: int) -> tuple[ApplyPatchOperation, int]:
    path = _parse_path_header(lines[index], UPDATE_FILE)
    index += 1
    move_to: str | None = None
    if index < len(lines) - 1 and lines[index].startswith(MOVE_TO):
        move_to = _parse_path_header(lines[index], MOVE_TO)
        index += 1

    diff_lines: list[str] = []
    while index < len(lines) - 1 and not _is_file_operation_header(lines[index]):
        diff_lines.append(lines[index])
        index += 1
    if not diff_lines:
        raise ValueError(f"Update File patch for {path} must include a hunk")
    return (
        ApplyPatchOperation(
            type="update_file",
            path=path,
            diff=_join_diff(diff_lines),
            move_to=move_to,
        ),
        index,
    )


def _parse_path_header(line: str, prefix: str) -> str:
    path = line.removeprefix(prefix).strip()
    if not path:
        raise ValueError(f"Missing path in apply_patch header: {line}")
    return path


def _is_file_operation_header(line: str) -> bool:
    return line.startswith((ADD_FILE, DELETE_FILE, UPDATE_FILE))


def _join_diff(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


__all__ = ["parse_patch", "parse_patch_input", "parse_patch_json"]
