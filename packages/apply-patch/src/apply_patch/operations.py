"""apply_patch 的操作与结果类型。

取自上游 ``src/agents/editor.py``。与上游的差异：去掉 ``ctx_wrapper``（SDK 运行上下文）；
编辑器协议改为同步，返回值不再是 ``MaybeAwaitable``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

ApplyPatchOperationType = Literal["create_file", "update_file", "delete_file"]


@dataclass(slots=True)
class ApplyPatchOperation:
    """Represents a single apply_patch editor operation requested by the model."""

    type: ApplyPatchOperationType
    path: str
    diff: str | None = None
    move_to: str | None = None


@dataclass(slots=True)
class ApplyPatchResult:
    """Optional metadata returned by editor operations."""

    status: Literal["completed", "failed"] | None = None
    output: str | None = None


@runtime_checkable
class ApplyPatchEditor(Protocol):
    """Host-defined editor that applies diffs."""

    def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult | str | None: ...

    def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult | str | None: ...

    def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult | str | None: ...


__all__ = [
    "ApplyPatchEditor",
    "ApplyPatchOperation",
    "ApplyPatchOperationType",
    "ApplyPatchResult",
]
